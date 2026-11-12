"""Make and validate narrow candidate fixes ONLY in the full ZIP working copy.

This is an offline experiment, not a deployment or a claim that all faults are
fixed. Uses the same real Adafruit drivers and memory I2C as run_tests.py.
"""
import ast,asyncio,contextlib,difflib,io,json,math
from pathlib import Path
import run_tests as t

root=t.ROOT
working=root/'working_copy/code'
changes={}

def edit(rel, old, new):
    p=working/rel
    s=p.read_text(encoding='utf-8-sig')
    assert old in s,(rel,old)
    changes.setdefault(rel,s)
    s=s.replace(old,new,1)
    p.write_text(s,encoding='utf-8',newline='\n')

# Rebuild only the candidate files from the preserved full archive copy, making
# reruns reproducible; SOURCE is never written.
import zipfile
with zipfile.ZipFile(next((root/'working_copy').glob('ADR012*.zip'))) as z:
    for rel in ['web/WebServer.py','web/RPIservo.py','web/functions.py','web/base_camera.py']:
        n=next(n for n in z.namelist() if n.endswith('/adeept_picar-b2/'+rel))
        (working/rel).write_bytes(z.read(n))

edit('web/WebServer.py',
     'P_sc.moveServoInit([init_pwm1])\n        T_sc.moveServoInit([init_pwm0])\n        scGear.moveServoInit([init_pwm2])',
     'P_sc.moveServoInit([1])\n        T_sc.moveServoInit([2])\n        scGear.moveServoInit([0])')
edit('web/RPIservo.py','time.sleep((self.scTime/self.scSteps - self.scMoveTime))',
     'time.sleep(max(0.0, self.scTime/self.scSteps - self.scMoveTime))')
edit('web/base_camera.py','event[0].isSet()','event[0].is_set()')

original=(working/'web/functions.py').read_text(encoding='utf-8')
tree=ast.parse(original)
f=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='distRedress')
lines=original.splitlines(keepends=True)
new='''\tdef distRedress(self):
\t\t# Candidate: bounded sensor reads; stop on sustained invalid samples.
\t\tfor _ in range(6):
\t\t\tvalue = ultra.checkdist()
\t\t\tif isinstance(value, (int, float)) and 0 <= value <= 200:
\t\t\t\treturn round(value, 2)
\t\tmove.motorStop()
\t\traise RuntimeError("No valid distance after 6 samples")
'''
old=''.join(lines[f.lineno-1:f.end_lineno])
edit('web/functions.py',old,new)

patches=[]
for rel,before in changes.items():
    after=(working/rel).read_text(encoding='utf-8')
    patches.extend(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),
                                     fromfile='a/'+rel,tofile='b/'+rel))
(root/'candidate_fixes.patch').write_text(''.join(patches),encoding='utf-8')

results=[]
def case(id,fn):
    try:
        with contextlib.redirect_stdout(io.StringIO()):detail=fn()
        results.append(dict(id=id,status='PASS',detail=detail))
    except Exception as e:results.append(dict(id=id,status='FAIL',error=repr(e)))

def selected_candidate(rel,env,names):
    tree=ast.parse((working/rel).read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(working/rel),'exec'),env)

def home():
    e=t.server_env()
    selected_candidate('web/WebServer.py',e,['robotCtrl'])
    e['scGear'].initPos[0]=80;e['P_sc'].initPos[1]=100;e['T_sc'].initPos[2]=110
    e['robotCtrl']('home',{})
    vals=[e['scGear'].nowPos[0],e['P_sc'].nowPos[1],e['T_sc'].nowPos[2]]
    assert vals==[80,100,110],vals
    return {'returned_positions':vals,'mapping':'same channels as original manual commands'}
case('FIX-HOME',home)

def auto():
    e=dict(t.rs.__dict__);e['time']=t.SimTime()
    selected_candidate('web/RPIservo.py',e,['ServoCtrl'])
    s=e['ServoCtrl']();s.autoSpeed([0],[30]);s.moveAuto()
    assert s.nowPos[0]==120
    return {'final_angle':s.nowPos[0],'minimum_requested_sleep':min(e['time'].sleeps),
            'note':'duration and smoothness require real hardware'}
case('FIX-AUTO',auto)

for value in [0,20,199.5,200,201,float('nan'),None]:
    def dist(value=value):
        e=t.functions_env();count=[0]
        def sample():count[0]+=1;return value
        e['ultra'].checkdist=sample
        selected_candidate('web/functions.py',e,['Functions'])
        f=e['Functions']()
        if isinstance(value,(float,int)) and 0<=value<=200:
            assert f.distRedress()==round(value,2)
        else:
            t.move.move(20,1,'mid')
            try:f.distRedress()
            except RuntimeError:pass
            else:raise AssertionError('no bounded failure')
            assert count[0]==6 and t.move.motor1.throttle==0
        return {'sample':str(value),'reads':count[0],'motor1':t.move.motor1.throttle}
    case('FIX-DIST-'+str(value),dist)

def event():
    e={'threading':t.threading,'time':t.SimTime(),'get_ident':lambda:1}
    selected_candidate('web/base_camera.py',e,['CameraEvent'])
    v=e['CameraEvent']();v.events[1]=[t.threading.Event(),0];v.set()
    assert v.events[1][0].is_set()
    return {'new_frame_event_set':True}
case('FIX-EVENT',event)

for rel in changes:
    case('FIX-SYNTAX-'+rel,lambda rel=rel:(compile((working/rel).read_text(encoding='utf-8'),rel,'exec') and {'file':rel}))

result={'scope':'four narrow fixes in extracted full ZIP working copy; not deployed; not all identified defects repaired',
        'files_changed':list(changes),'tests':results}
(root/'candidate_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for r in results:print(r['id'],r['status'])
assert all(r['status']=='PASS' for r in results),results
