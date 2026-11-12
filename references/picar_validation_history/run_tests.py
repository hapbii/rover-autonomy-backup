"""Offline tests of vendor PiCar code. Never imports or runs setup.py.

Hardware bus/GPIO/camera interfaces are simulated; Adafruit PWM, motor and servo
drivers, Flask, OpenCV and websockets are real installed packages. Original source
is loaded unchanged, with AST selection where import-time hardware side effects
would otherwise run. Test outcomes describe observations, not physical success.
"""
from __future__ import annotations
import ast, asyncio, contextlib, hashlib, importlib.util, io, json, logging
import math, os, platform, random, re, statistics, sys, threading, time, traceback
import types, warnings
from collections import Counter, deque
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
SOURCE = ROOT / 'source'
RESULTS = []
EVENTS = []

def module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m

class MemoryI2C:
    """Byte-addressed memory with the bus methods used by I2CDevice.

    This models register reads/writes, not chip timing, electrical behavior or
    the hardware's auto-increment/sleep/restart semantics.
    """
    memory = {0x5f: bytearray(256)}
    writes = []
    fail = False
    def __init__(self, *a, **kw): pass
    def try_lock(self): return True
    def unlock(self): pass
    def writeto(self, address, buffer, *, start=0, end=None, stop=True):
        if self.fail: raise OSError('SIMULATED I2C unavailable')
        b = bytes(buffer[start:end])
        if not b: return
        if len(b) > 1:
            self.memory.setdefault(address, bytearray(256))[b[0]:b[0]+len(b)-1] = b[1:]
            self.writes.append({'address':address,'register':b[0],'data':list(b[1:])})
    def readfrom_into(self, address, buffer, *, start=0, end=None):
        if self.fail: raise OSError('SIMULATED I2C unavailable')
        end = len(buffer) if end is None else end
        buffer[start:end] = bytes(end-start)
    def writeto_then_readfrom(self, address, out_buffer, in_buffer,
                             *, out_start=0, out_end=None, in_start=0, in_end=None, stop=False):
        if self.fail: raise OSError('SIMULATED I2C unavailable')
        reg = out_buffer[out_start]
        in_end = len(in_buffer) if in_end is None else in_end
        in_buffer[in_start:in_end] = self.memory.setdefault(address, bytearray(256))[reg:reg+in_end-in_start]
    def deinit(self): pass

sys.modules['busio'] = module('busio', I2C=MemoryI2C, SPI=object, UART=object)
sys.modules['board'] = module('board', SCL='SIM_SCL', SDA='SIM_SDA')
sys.modules['pwmio'] = module('pwmio', PWMOut=object)
from adafruit_pca9685 import PCA9685
from adafruit_motor import motor, servo
import cv2
import numpy as np
import websockets

def read(name): return (SOURCE / name).read_text(encoding='utf-8-sig')

def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, SOURCE / rel)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

def selected(rel, env, names=None, classes=True):
    """Compile unmodified function/class nodes, preserving original line numbers."""
    tree = ast.parse(read(rel))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef,ast.AsyncFunctionDef))
             or (classes and isinstance(n,ast.ClassDef))]
    if names is not None: nodes = [n for n in nodes if n.name in names]
    env.setdefault('__file__', str(SOURCE / rel))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE / rel),'exec'),env)
    return env

move = load_module('move', 'web/move.py')
rs = load_module('RPIservo', 'web/RPIservo.py')

def observe(id, group, title, func, severity=''):
    start = time.perf_counter()
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            status, detail = func()
        row = dict(id=id,group=group,title=title,status=status,detail=detail,
                   severity=severity,elapsed_ms=round((time.perf_counter()-start)*1000,2),
                   warnings=list(dict.fromkeys(str(w.message) for w in ws)))
    except Exception as e:
        row = dict(id=id,group=group,title=title,status='HARNESS_ERROR',
                   detail={'error':repr(e),'traceback':traceback.format_exc()},severity=severity)
    if captured.getvalue(): row['stdout'] = captured.getvalue()[-5000:]
    RESULTS.append(row)
    print(id, row['status'], title, flush=True)
    return row

def must(condition, detail):
    assert condition, detail
    return 'PASS', detail

def defect(condition, detail):
    assert condition, detail
    return 'DEFECT', detail

def expect_error(fn, cls):
    try: fn()
    except cls as e: return type(e).__name__ + ': ' + str(e)
    raise AssertionError('Expected '+str(cls))

class StopReplay(Exception): pass
class SimTime:
    def __init__(self, limit=1000): self.sleeps=[];self.limit=limit
    def sleep(self, seconds):
        if seconds < 0: raise ValueError('sleep length must be non-negative')
        self.sleeps.append(seconds)
        if len(self.sleeps)>self.limit: raise StopReplay('bounded replay')
    def time(self): return 100.0+sum(self.sleeps)

class NullPeripheral:
    def __getattr__(self, name):
        return lambda *a, **kw: EVENTS.append((name,*a))

def init_motor():
    MemoryI2C.fail=False
    MemoryI2C.memory={0x5f:bytearray(256)}
    MemoryI2C.writes.clear()
    move.setup()

def server_env():
    init_motor()
    selected_servo = dict(rs.__dict__)
    selected_servo['time'] = SimTime()
    selected('web/RPIservo.py',selected_servo,names=['ServoCtrl'])
    S = selected_servo['ServoCtrl']
    cam = NullPeripheral()
    env = dict(time=SimTime(),json=json,move=move,scGear=S(),P_sc=S(),T_sc=S(),
               speed_set=100,direction_command='no',turn_command='no',functionMode=0,
               modeSelect='PT',init_pwm0=90,init_pwm1=90,init_pwm2=90,init_pwm3=90,init_pwm4=90,
               RL=NullPeripheral(),WS2812=NullPeripheral(),switch=NullPeripheral(),
               fuc=NullPeripheral(),speech=NullPeripheral(),
               flask_app=types.SimpleNamespace(camera=cam,modeselect=cam.modeselect,
                                               colorFindSet=cam.colorFindSet),
               info=types.SimpleNamespace(get_cpu_tempfunc=lambda:'42.0',
                                         get_cpu_use=lambda:'5',get_ram_info=lambda:'20'),
               thisPath=str(SOURCE/'web'))
    selected('web/WebServer.py',env)
    env['replace_num'] = lambda *a: EVENTS.append(('persist_calibration',*a))
    return env

class ScriptSocket:
    def __init__(self, messages): self.messages=deque(messages);self.sent=[]
    async def recv(self):
        if not self.messages: raise StopReplay('end of scripted messages')
        return self.messages.popleft()
    async def send(self,x): self.sent.append(x)

async def replay_async(env, messages):
    sock=ScriptSocket(messages)
    try: await env['recv_msg'](sock)
    except StopReplay: pass
    return sock

def static_checks():
    files=sorted(SOURCE.rglob('*.py'))
    for version in [(3,11),(3,13),(3,14)]:
        def check(version=version):
            for p in files:
                ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p),feature_version=version)
                compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
            return must(True,{'files':len(files),'grammar':str(version),'runtime':platform.python_version(),
                              'note':'grammar check only; not runtime or target OS compatibility'})
        observe('SYN-'+str(version[1]),'static','All vendor Python files parse',check)
    def assets():
        html=read('web/dist/index.html')
        refs=re.findall(r'(?:src|href)=["\']([^"\']+)',html)
        missing=[r for r in refs if r.startswith('/') and not (SOURCE/'web/dist'/r.lstrip('/')).exists()]
        return must(not missing,{'references':len(refs),'missing':missing})
    observe('ASSET-01','static','Frontend index references exist',assets)
    def interface():
        js=''.join(p.read_text(encoding='utf-8') for p in (SOURCE/'web/dist/js').glob('app*.js'))
        return must('location.hostname+":8888"' in js and ':5000/video_feed' in js,
                    {'video_port':5000,'control_port':8888,'home_button':'"HOME","home"' in js,
                     'meaning':'video HTTP and command WebSocket are separate'})
    observe('ASSET-02','static','Frontend control and camera routes',interface)
    def unused_gpu():
        env={'psutil':None};selected('web/info.py',env)
        e=expect_error(env['get_gpu_tempfunc'],NameError)
        return defect(True,{'error':e,'note':'unused by normal get_info command; optional helper only'})
    observe('INFO-01','static','Optional GPU helper missing os import',unused_gpu,'low')

def motor_tests():
    for speed in [-10,0,1,20,50,100,110]:
        for direction in [-1,1]:
            def check(speed=speed,direction=direction):
                init_motor();move.move(speed,direction,'mid')
                got=move.motor1.throttle
                expected=min(100,max(0,speed))/100*direction
                if expected==0: expected=0
                return must(got==expected,{'speed':speed,'direction':direction,'throttle':got,
                                          'duty_channels_15_14':[move.pwm_motor.channels[i].duty_cycle for i in [15,14]]})
            observe(f'MOTOR-{speed}-{direction}','motor','Speed clamp and direction',check)
    def stop():
        init_motor()
        for i in range(1,5):move.Motor(i,1,80)
        move.motorStop()
        vals=[getattr(move,f'motor{i}').throttle for i in range(1,5)]
        return must(vals==[0]*4,{'throttle':vals,'note':'driver braking PWM state; physical stopping not measured'})
    observe('MOTOR-STOP','motor','Stop all four driver outputs',stop)
    def routing():
        init_motor();move.move(50,1,'left')
        return must(move.motor1.throttle==.5 and move.motor2.throttle is None,
                    {'normal_move_m1':move.motor1.throttle,'normal_move_m2':move.motor2.throttle,
                     'note':'normal driving uses M1 only; correctness depends on actual wiring'})
    observe('MOTOR-ROUTE','motor','Normal driving motor port behavior',routing)
    def vroute():
        init_motor();move.video_Tracking_Move(45,1)
        return must((move.motor1.throttle,move.motor2.throttle)==(.45,-.45),
                    {'video_tracking_throttle':[move.motor1.throttle,move.motor2.throttle]})
    observe('MOTOR-VIDEO','motor','Video tracking drives M1 and M2',vroute)
    def invaliddir():
        init_motor();move.move(50,1,'mid');move.move(50,0,'mid')
        return defect(move.motor1.throttle==.5,{'invalid_direction':0,'retained_throttle':move.motor1.throttle,
                                                'note':'internal API robustness; normal UI sends +1/-1'})
    observe('MOTOR-DIR','motor','Invalid direction retains previous drive',invaliddir,'medium')

def servo_tests():
    for angle in [-1000,-90,-30,0,30,90,1000]:
        def check(angle=angle):
            init_motor();s=rs.ServoCtrl();s.moveAngle(0,angle)
            return must(s.nowPos[0]==min(180,max(0,90+angle)),
                        {'relative_angle':angle,'clamped_absolute':s.nowPos[0]})
        observe('SERVO-'+str(angle),'servo','Steering angle clamp',check)
    def home():
        e=server_env();err=expect_error(lambda:e['robotCtrl']('home',{}),IndexError)
        return defect(True,{'error':err,'passed_servo_ids':[90], 'valid_servo_ids':list(range(8)),
                            'source':'web/WebServer.py:255-258'})
    observe('SERVO-HOME','servo','HOME passes angle as channel index',home,'high')
    def autotime():
        e=dict(rs.__dict__);e['time']=SimTime();selected('web/RPIservo.py',e,['ServoCtrl'])
        s=e['ServoCtrl']();err=expect_error(s.moveAuto,ValueError)
        return defect(True,{'error':err,'sleep_seconds':s.scTime/s.scSteps-s.scMoveTime,
                            'note':'default auto interpolation only; not ordinary left/right'})
    observe('SERVO-AUTO','servo','Auto interpolation negative sleep',autotime,'medium')
    def upper():
        e=server_env()
        for _ in range(90):e['configPWM']('SiRight 0',{})
        err=expect_error(lambda:e['configPWM']('SiRight 0',{}),ValueError)
        return defect(True,{'error':err,'init_pwm0':e['init_pwm0'],'trigger':'91 right fine-tune clicks from 90'})
    observe('SERVO-CAL','servo','Fine tuning lacks angle bound',upper,'medium')
    def initconsistency():
        e=server_env();s=e['scGear'];s.initPos[0]=77;s.initPos[2]=111
        e['servoPosInit']()
        assert s.initPos[0]==77 and s.initPos[2]==90
        return 'OBSERVATION', (
                       {'steering_command_channel':0,'servoPosInit_steering_mapping':2,
                        'result_init_positions':s.initPos[:3],
                        'note':'mixed channel mappings in initialization; verify physical wiring'})
    observe('SERVO-MAP','servo','Initialization and steering channel mismatch',initconsistency,'medium')
    def resource():
        init_motor();s=rs.ServoCtrl();before=len(MemoryI2C.writes)
        for a in [0,10,20]:s.moveAngle(0,a)
        writes=MemoryI2C.writes[before:]
        resets=[w for w in writes if w['register']==0 and w['data']==[0]]
        return ('OBSERVATION' if len(resets)>=3 else 'HARNESS_ERROR'), {'servo_updates':3,'mode1_zero_writes':len(resets),
                      'shared_address':'0x5f','note':'register writes observed; electrical jitter and thread races not modeled'}
    observe('SERVO-BUS','servo','Every servo update reinitializes shared PWM chip',resource,'medium')

def command_tests():
    for command in ['forward','backward','left','right','DS','TS','lookleft','lookright','LRstop','up','down','UDstop']:
        def check(command=command):
            e=server_env();e['robotCtrl'](command,{})
            return must(True,{'command':command,'motor1':move.motor1.throttle,
                              'steering':e['scGear'].nowPos[0],
                              'pan_wiggle':e['P_sc'].wiggleID,'tilt_wiggle':e['T_sc'].wiggleID})
        observe('CMD-'+command,'command','Normal UI command replay',check)
    def ts():
        e=server_env();e['robotCtrl']('forward',{});e['robotCtrl']('left',{});e['robotCtrl']('TS',{})
        assert move.motor1.throttle==0 and e['direction_command']=='forward'
        return 'OBSERVATION', (
                      {'sequence':['forward','left','TS'],'motor1':move.motor1.throttle,
                       'logical_direction':e['direction_command'],
                       'meaning':'releasing steering also stops motor while forward state remains'})
    observe('CMD-RELEASE','command','Steering release stops forward drive',ts,'medium')
    for command in ['scan','findColor','motionGet','stopCV','KD','automatic','automaticOff','trackLine','trackLineOff','police','policeOff','speech','speechOff']:
        def check(command=command):
            e=server_env();EVENTS.clear();e['functionSelect'](command,{})
            return must(bool(EVENTS),{'command':command,'peripheral_calls':list(EVENTS),
                                      'note':'dispatch only; real algorithm tested separately'})
        observe('MODE-'+command,'command','Feature command dispatch',check)
    for port in [1,2,3]:
        for state in ['on','off']:
            def check(port=port,state=state):
                e=server_env();EVENTS.clear();e['switchCtrl'](f'Switch_{port}_{state}',{})
                return must(EVENTS==[('switch',port,int(state=='on'))],{'calls':list(EVENTS)})
            observe(f'SWITCH-{port}-{state}','command','Switch dispatch',check)
    def credentials():
        e=server_env();sock=ScriptSocket(['admin:123456'])
        good=asyncio.run(e['check_permit'](sock))
        return must(good is True and len(sock.sent)==1,{'authenticated':good})
    observe('AUTH-VALID','protocol','Valid vendor credentials',credentials)
    def authbad():
        e=server_env();sock=ScriptSocket(['admin'])
        err=expect_error(lambda:asyncio.run(e['check_permit'](sock)),IndexError)
        return defect(True,{'error':err,'input':'admin (no colon)'})
    observe('AUTH-MALFORMED','protocol','Malformed credentials crash handler',authbad,'medium')
    for text in ['SiLeft x','SiRight ','PWMMS NaN','CVFLL1 x','CVFLColorSet NaN','CVFLSP']:
        def check(text=text):
            e=server_env();err=expect_error(lambda:asyncio.run(replay_async(e,[text])),(ValueError,IndexError))
            return defect(True,{'input':text,'error':err})
        observe('INPUT-'+text.replace(' ','_'),'protocol','Malformed numeric command',check,'medium')
    for value in [{'data':[1]},{'title':'findColorSet'},{'title':'findColorSet','data':[1]}]:
        def check(value=value):
            e=server_env();err=expect_error(lambda:asyncio.run(replay_async(e,[json.dumps(value)])),(KeyError,IndexError))
            return defect(True,{'input':value,'error':err})
        observe('JSON-'+str(len(RESULTS)),'protocol','Malformed JSON object',check,'medium')
    def unknown():
        e=server_env();s=asyncio.run(replay_async(e,['unknown-command']))
        data=json.loads(s.sent[0])
        assert data['status']=='ok'
        return 'OBSERVATION', {'unknown_command_response':data,'meaning':'ack is not proof of action'}
    observe('INPUT-ACK','protocol','Unknown command acknowledged OK',unknown,'low')
    def speeds():
        e=server_env();s=asyncio.run(replay_async(e,['wsB 99999','forward']))
        return must(e['speed_set']==99999 and move.motor1.throttle==1,
                    {'stored_speed':e['speed_set'],'actual_driver_throttle':move.motor1.throttle,
                     'note':'server lacks bound but move.Motor clamps output'})
    observe('INPUT-SPEED','protocol','Excessive speed clamped by motor layer',speeds)
    def failure():
        e=server_env();MemoryI2C.fail=True
        try:err=expect_error(lambda:asyncio.run(replay_async(e,['forward'])),(OSError,ValueError))
        finally:MemoryI2C.fail=False
        return 'OBSERVATION', {'error':err,'meaning':'I2C failure propagates; no structured response'}
    observe('I2C-FAIL','protocol','I2C unavailable at command startup',failure,'high')
    def fuzz():
        rng=random.Random(20261016)
        messages=['admin','',':','admin:',None,0,[],{}, {'title':'findColorSet','data':[]}]
        for prefix in ['SiLeft','SiRight','PWMMS','CVFLL1','CVFLL2','CVFLSP','CVFLColorSet']:
            messages += [prefix+' '+x for x in ['','x','-1','999','0.5']]
        messages += [''.join(rng.choices('ABC123 :',k=rng.randrange(1,20))) for _ in range(20)]
        errors=Counter();samples=[]
        for value in messages:
            e=server_env()
            wire=json.dumps(value) if not isinstance(value,str) else value
            try:asyncio.run(replay_async(e,[wire]))
            except Exception as ex:
                errors[type(ex).__name__]+=1;samples.append({'input':value,'error':str(ex)})
        return defect(bool(errors),{'cases':len(messages),'unhandled':sum(errors.values()),
                                   'types':dict(errors),'examples':samples[:12]})
    observe('INPUT-FUZZ','protocol','Deterministic malformed-input campaign',fuzz,'medium')

def functions_env():
    init_motor();e=server_env()
    env=dict(threading=threading,move=move,scGear=e['scGear'],time=SimTime(),
             last_status=0,lightADC=127,lightThreshold=15,
             ultra=types.SimpleNamespace(checkdist=lambda:100))
    selected('web/functions.py',env,['Functions'])
    return env

def algorithm_tests():
    for bits in range(8):
        def check(bits=bits):
            e=functions_env();e['last_status']=-1
            for name,bit in [('left',2),('middle',1),('right',0)]:
                e['track_line_'+name]=types.SimpleNamespace(value=(bits>>bit)&1)
            f=e['Functions']();f.trackLineProcessing()
            return must(move.motor1.throttle==.28,{'sensor_bits':format(bits,'03b'),
                        'steering':e['scGear'].nowPos[0],'motor1':move.motor1.throttle,
                        'note':'vendor truth table replay; real sensor polarity and line quality not verified'})
        observe('LINE-'+format(bits,'03b'),'algorithm','Line sensor truth table',check)
    def initialzero():
        e=functions_env()
        for name in ['left','middle','right']:e['track_line_'+name]=types.SimpleNamespace(value=0)
        e['Functions']().trackLineProcessing()
        return defect(move.motor1.throttle is None,{'initial_last_status':0,'sensor_bits':'000',
                     'motor1':move.motor1.throttle,'meaning':'initial identical sample skipped; mode can appear inactive'})
    observe('LINE-INITIAL','algorithm','Initial 000 sensor sample skipped',initialzero,'medium')
    for distance in [20,30,35,40,50]:
        def check(distance=distance):
            e=functions_env();f=e['Functions']();f.distRedress=lambda:distance
            f.keepDisProcessing()
            expected=-.4 if distance<30 else .4 if distance>40 else 0
            return must(move.motor1.throttle==expected,{'distance_cm':distance,'motor1':move.motor1.throttle})
        observe('DIST-'+str(distance),'algorithm','Keep-distance boundaries',check)
    for distance,side in [(100,None),(20,None),(50,'left'),(50,'right')]:
        def check(distance=distance,side=side):
            e=functions_env();f=e['Functions']()
            seq=iter([50,80,20] if side=='left' else [50,20,80] if side else [distance])
            f.distRedress=lambda:next(seq)
            f.automaticProcessing()
            return must(True,{'front_cm':distance,'free_side':side,'motor1':move.motor1.throttle,
                              'steering':e['scGear'].nowPos[0],
                              'note':'branch replay only; no real obstacle or vehicle physics'})
        observe('AUTO-'+str(distance)+'-'+str(side),'algorithm','Obstacle avoidance branches',check)
    def exact200():
        e=functions_env();calls=[0]
        def dist():
            calls[0]+=1
            if calls[0]>10000: raise StopReplay('10000 reads exceeded')
            return 200
        e['ultra'].checkdist=dist
        err=expect_error(e['Functions']().distRedress,StopReplay)
        return defect(True,{'distance_cm':200,'reads_before_abort':calls[0],'error':err,
                            'reason':'conditions use >200 or <200, equality has no exit',
                            'note':'physical occurrence of exact 200 is unverified; configured sensor max is 2m'})
    observe('DIST-200','algorithm','Exact 200 cm sample loops without exit',exact200,'high')
    for value in [80,127,180]:
        def check(value=value):
            e=functions_env();e['adc']=types.SimpleNamespace(analogRead=lambda ch:value)
            e['Functions']().trackLightProcessing()
            return must(True,{'adc':value,'steering':e['scGear'].nowPos[0],'motor1':move.motor1.throttle})
        observe('LIGHT-'+str(value),'algorithm','Light tracking branches',check)

def vision_env():
    e=dict(cv2=cv2,np=np,threading=threading,datetime=__import__('datetime'),
           Kalman_filter=load_module('Kalman_filter','web/Kalman_filter.py'),
           RPIservo=rs,move=move,time=SimTime(),APPMode=None,
           colorUpper=np.array([44,255,255]),colorLower=np.array([24,100,100]),
           FLCV_Status=0,findLineMove=1,tracking_servo_status=0,findLineError=20,
           linePos_1=440,linePos_2=380,lineColorSet=255,Threshold=80,
           CVRun=1,turn_speed=45,forward_speed=20,frameRender=1,
           BaseCamera=object)
    selected('web/camera_opencv.py',e,['CVThread','Camera','map'])
    return e

def vision_tests():
    for x in [100,320,540]:
        def check(x=x):
            init_motor();e=vision_env();f=e['CVThread']()
            image=np.zeros((480,640,3),dtype=np.uint8);image[:,x-20:x+20]=255
            f.findlineCV(image)
            center=f.center
            return ('PASS' if center is not None and abs(center-x)<3 else 'DEFECT'), {
                'white_line_x':x,'detected_center':center,'motor1':move.motor1.throttle,
                'numpy':np.__version__,'note':'synthetic high-contrast image; no optics/lighting model'}
        observe('CV-LINE-'+str(x),'vision','Synthetic white-line frame',check,'high')
    def blank():
        init_motor();e=vision_env();f=e['CVThread']();f.findlineCV(np.zeros((480,640,3),np.uint8))
        return must(f.center is None and move.motor1.throttle==0,{'center':f.center,'motor1':move.motor1.throttle})
    observe('CV-BLANK','vision','No-line image stops with no previous direction',blank)
    def row():
        init_motor();e=vision_env();e['linePos_1']=999
        err=expect_error(lambda:e['CVThread']().findlineCV(np.zeros((480,640,3),np.uint8)),IndexError)
        return defect(True,{'row':999,'frame_height':480,'error':err})
    observe('CV-ROW','vision','Out-of-frame scan row unhandled',row,'medium')
    def color():
        init_motor();e=vision_env();f=e['CVThread']()
        img=np.zeros((480,640,3),np.uint8);cv2.circle(img,(450,200),40,(0,255,255),-1)
        f.findColor(img)
        return must(f.findColorDetection==1,{'yellow_target':[450,200],
                    'detected_center':[round(f.box_x,1),round(f.box_y,1)],'radius':round(f.radius,1)})
    observe('CV-COLOR','vision','Synthetic yellow object detection',color)
    def nocolor():
        init_motor();e=vision_env();f=e['CVThread']();f.findColor(np.zeros((480,640,3),np.uint8))
        return must(f.findColorDetection==0,{'detected':f.findColorDetection})
    observe('CV-NOCOLOR','vision','Blank image has no yellow object',nocolor)
    def cvmap():
        e=vision_env();v=e['map'](150,100,200,0,10)
        return defect(v!=5,{'input':150,'range':[100,200],'output_range':[0,10],
                            'actual':v,'expected':5,'note':'helper not used by ordinary manual drive'})
    observe('CV-MAP','vision','Optional linear-map formula wrong',cvmap,'low')

def http_tests():
    class Camera:
        modeSelect='none'
        def get_frame(self):
            img=np.zeros((480,640,3),np.uint8)
            return cv2.imencode('.jpg',img)[1].tobytes()
        def colorFindSet(self,*a):pass
        def colorFindSetApp(self,*a):pass
    fake=module('camera_opencv',Camera=Camera)
    with patch.dict(sys.modules,{'camera_opencv':fake}):
        app=load_module('vendor_http_app','web/app.py')
    client=app.app.test_client()
    for route in ['/','/js/'+next((SOURCE/'web/dist/js').glob('app*.js')).name,
                  '/css/'+next((SOURCE/'web/dist/css').glob('app*.css')).name,
                  '/does-not-exist.txt']:
        def check(route=route):
            response=client.get(route)
            expected=404 if route=='/does-not-exist.txt' else 200
            return must(response.status_code==expected,{'path':route,'http':response.status_code,'bytes':len(response.data)})
        observe('HTTP-'+str(len(RESULTS)),'http','Flask original route response',check)
    def stream():
        response=client.get('/video_feed',buffered=False)
        first=next(iter(response.response));response.close()
        return must(b'Content-Type: image/jpeg' in first and b'\xff\xd8' in first,
                    {'http':response.status_code,'first_chunk_bytes':len(first),
                     'mime':response.content_type,'note':'synthetic JPEG; camera driver replaced'})
    observe('HTTP-MJPEG','http','MJPEG stream with simulated camera',stream)

def websocket_tests():
    logging.getLogger('websockets.server').setLevel(logging.CRITICAL)
    async def normal():
        e=server_env()
        async with websockets.serve(e['main_logic'],'127.0.0.1',0) as server:
            port=server.sockets[0].getsockname()[1]
            async with websockets.connect(f'ws://127.0.0.1:{port}') as sock:
                await sock.send('admin:123456');auth=await asyncio.wait_for(sock.recv(),2)
                replies=[]
                for command in ['wsB 20','forward','left','DS']:
                    await sock.send(command);replies.append(json.loads(await asyncio.wait_for(sock.recv(),2)))
        return must('congratulation' in auth and all(r['status']=='ok' for r in replies),
                    {'library':websockets.__version__,'python':platform.python_version(),
                     'transport':'real loopback WebSocket','commands':4,'final_throttle':move.motor1.throttle})
    observe('WS-ROUNDTRIP','network','Real WebSocket auth and command exchange',lambda:asyncio.run(normal()))
    async def disconnect():
        e=server_env()
        async with websockets.serve(e['main_logic'],'127.0.0.1',0) as server:
            port=server.sockets[0].getsockname()[1]
            async with websockets.connect(f'ws://127.0.0.1:{port}') as sock:
                await sock.send('admin:123456');await sock.recv()
                await sock.send('wsB 20');await sock.recv()
                await sock.send('forward');await sock.recv()
            await asyncio.sleep(.08)
            val=move.motor1.throttle
        return defect(val==.2,{'closed_client':True,'throttle_after_close':val,
                              'meaning':'no disconnect cleanup or command timeout observed; no physical motion measured'})
    observe('WS-DISCONNECT','network','Closing client leaves last motor command active',lambda:asyncio.run(disconnect()),'high')
    async def led_failure():
        e=server_env()
        class FailLight:
            def __getattr__(self,name):return lambda *a:(_ for _ in ()).throw(RuntimeError('SIMULATED LED fault'))
        e['RL']=FailLight()
        err=expect_error(lambda:e['robotCtrl']('forward',{}),RuntimeError)
        return defect(move.motor1.throttle==1,{'error':err,'retained_throttle':move.motor1.throttle,
                     'meaning':'actuator write precedes peripheral error; handler has no stop finally'})
    observe('WS-PERIPHERAL','network','Peripheral exception after drive retains motor output',lambda:asyncio.run(led_failure()),'high')
    async def multi():
        e=server_env()
        async with websockets.serve(e['main_logic'],'127.0.0.1',0) as server:
            port=server.sockets[0].getsockname()[1]
            async with websockets.connect(f'ws://127.0.0.1:{port}') as a:
                await a.send('admin:123456');await a.recv();await a.send('forward');await a.recv()
                before=move.motor1.throttle
                async with websockets.connect(f'ws://127.0.0.1:{port}') as b:
                    await b.send('admin:123456');await b.recv()
                    await b.send('DS');await b.recv();after=move.motor1.throttle
        assert before==1 and after==0
        return 'OBSERVATION', {'client_A_forward':before,'client_B_stop':after,
                      'meaning':'shared global controller; no exclusive ownership'}
    observe('WS-MULTI','network','Second client changes shared motor state',lambda:asyncio.run(multi()),'medium')

def setup_tests():
    def dryrun():
        tree=ast.parse(read('setup.py'));blocks=[]
        for n in tree.body:
            if isinstance(n,(ast.Assign,ast.For)):
                if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='commands_apt' for t in n.targets):blocks.append(n)
                elif isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='mark_apt' for t in n.targets):blocks.append(n)
                elif isinstance(n,ast.For) and 'commands_apt' in ast.unparse(n):blocks.append(n)
        commands=[]
        env={'os':types.SimpleNamespace(system=lambda cmd:(commands.append(cmd) or 1)),'print':lambda *a:None}
        exec(compile(ast.Module(body=blocks,type_ignores=[]),'setup.py','exec'),env)
        footer='installed, disconnected and restarted' in read('setup.py') and 'os.system("sudo reboot")' in read('setup.py')
        return defect(env['mark_apt']==1 and footer,{'simulated_failed_apt_calls':len(commands),
                      'recorded_only':True,'commands_actually_run':0,
                      'final_success_print_is_unconditional':True,'reboot_is_unconditional':True,
                      'meaning':'reboot cannot establish installation success'})
    observe('SETUP-FAIL','install','Installation failure does not gate success message/reboot',dryrun,'high')
    def resetflag():
        tree=ast.parse(read('setup.py'));nodes=[]
        for n in tree.body:
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ['commands_apt','mark_apt'] for t in n.targets):nodes.append(n)
            elif isinstance(n,ast.For) and 'commands_apt' in ast.unparse(n):nodes.append(n)
        calls=[]
        def fake(cmd):calls.append(cmd);return 1 if len(calls)==1 else 0
        env={'os':types.SimpleNamespace(system=fake),'print':lambda *a:None}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'setup.py','exec'),env)
        return defect(len(calls)==27 and env['mark_apt']==1,
                      {'one_initial_failure_then_success':True,'calls':len(calls),
                       'retained_error_flag':env['mark_apt'],'note':'retry flag not cleared between rounds'})
    observe('SETUP-RETRY','install','Retry success does not reset failure marker',resetflag,'low')
    def paths():
        text=read('web/VoiceIdentify.py')+read('web/Voice_Command.py')
        hardcoded=bool(re.search(r'/home/pi/',text))
        assets=list(SOURCE.rglob('*ncnn*'))
        assert hardcoded and not assets
        return 'OBSERVATION', {'hardcoded_home':'/home/pi',
                      'sherpa_model_or_binary_present':bool(assets),
                      'note':'voice runtime assets absent from Code tree; voice worker captures its error'}
    observe('VOICE-PATH','install','Voice runtime path/assets are external prerequisites',paths,'medium')
    def service():
        s=read('setup.py')
        return must('Restart=no' in s and 'web/WebServer.py' in s,
                    {'service':'Adeept_Robot.service','restart_policy':'no','http_port':5000,'websocket_port':8888,
                     'meaning':'inspect journal and both ports; service active alone is insufficient'})
    observe('SERVICE-01','install','Service configuration review',service)
    def ledexcept():
        # Execute only original SPI-LED initialization try/except with injected failure.
        tree=ast.parse(read('web/WebServer.py'))
        main=next(n for n in tree.body if isinstance(n,ast.If) and '__name__' in ast.unparse(n.test))
        block=next(n for n in main.body if isinstance(n,ast.Try))
        def boom(*a):raise OSError('SIMULATED LED constructor failure')
        env={'robotLight':types.SimpleNamespace(Adeept_SPI_LedPixel=boom),'WS2812_mark':None}
        err=expect_error(lambda:exec(compile(ast.Module(body=[block],type_ignores=[]),'WebServer.py','exec'),env),NameError)
        return defect(True,{'error':err,'meaning':'exception path references WS2812 before assignment; server startup aborted'})
    observe('STARTUP-LED','install','LED initialization exception masks original error',ledexcept,'high')

def misc_tests():
    def battery():
        e={'threading':threading,'average_voltage':0,'WarningThreshold':6.3,'full_voltage':8.4}
        selected('web/Voltage.py',e,['BatteryLevelMonitor'])
        obj=object.__new__(e['BatteryLevelMonitor'])
        values={}
        for v in [0,6.0,6.3,7.4,8.4,9.0]:
            e['average_voltage']=v;values[str(v)]=obj.get_battery_percentage()
        return defect(int(values['0'])<0 and int(values['9.0'])>100,
                      {'percentages':values,'note':'display helper lacks 0..100 bounds; voltage not measured'})
    observe('BATTERY-PCT','other','Battery display percentage outside 0..100',battery,'low')
    def event():
        e={'threading':threading,'time':SimTime(),'get_ident':lambda:1}
        selected('web/base_camera.py',e,['CameraEvent'])
        ev=e['CameraEvent']();ev.events[1]=[threading.Event(),0]
        try:ev.set();return must(ev.events[1][0].is_set(),{'legacy_isSet_present':hasattr(threading.Event(),'isSet')})
        except AttributeError as ex:return 'DEFECT',{'error':str(ex),'python':platform.python_version()}
    observe('CAMERA-EVENT','other','CameraEvent legacy threading method',event,'medium')
    def ir():
        e={'TOLERANCE':.5,'MIN_NORMAL_PULSES':20,'REPEAT_PULSES':25,'repeat_code':'repeat','pulse_timestamps':[]}
        selected('web/ir_control.py',e,['calculate_time_diff','is_within_tolerance','decode_nec_debug'])
        address=0;data=0x18
        bits=''.join(format(v,'08b') for v in [address,address^255,data,data^255])
        times=[0,9000,13500]
        for b in bits:times.extend([times[-1]+560,times[-1]+560+(1690 if b=='1' else 560)])
        times.append(times[-1]+560)
        e['pulse_timestamps']=[(i%2,t) for i,t in enumerate(times)]
        got=e['decode_nec_debug']()
        return must(got==(address,data),{'synthetic_decoded':got,'note':'decoder fixture follows vendor bit order; no remote hardware tested'})
    observe('IR-VALID','other','Synthetic NEC pulse integrity decoding',ir)

def extra_fault_tests():
    def full_installer():
        # Full script execution against in-memory filesystem and fake OS/process
        # modules. Every external command is recorded only, never executed.
        commands=[];files={}
        class Writer(io.StringIO):
            def __init__(self,path):super().__init__();self.path=path
            def close(self):
                if not self.closed:files[self.path]=self.getvalue()
                super().close()
        def fakeopen(path,mode='r',*a,**kw):
            return Writer(str(path)) if 'w' in mode else io.StringIO(files.get(str(path),''))
        def popen(cmd):
            return io.StringIO('/home/pi\n' if 'getent passwd' in cmd else 'pi\n')
        def system(cmd):commands.append(cmd);return 0 if cmd=='sudo reboot' else 1
        fakeos=module('os',popen=popen,system=system,path=types.SimpleNamespace(
            realpath=lambda p:'/home/pi/adeept_picar-b2/setup.py',dirname=lambda p:'/home/pi/adeept_picar-b2'),
            chmod=lambda *a:None)
        def fake_run(cmd,**kw):
            commands.append(cmd)
            return types.SimpleNamespace(stdout='inactive\n',returncode=0)
        class Popen:
            def __init__(self,cmd,**kw):self.stdout=io.BytesIO(b'13\n');commands.append(cmd)
            def poll(self):return 0
        fakeproc=module('subprocess',run=fake_run,Popen=Popen,PIPE=-1,STDOUT=-2,CalledProcessError=RuntimeError)
        e={'__file__':'/home/pi/adeept_picar-b2/setup.py','__name__':'__main__','open':fakeopen}
        with patch.dict(sys.modules,{'os':fakeos,'subprocess':fakeproc}):
            exec(compile(read('setup.py'),'setup.py','exec'),e)
        apt=[c for c in commands if isinstance(c,str) and c.startswith('sudo apt-get')]
        pip=[c for c in commands if isinstance(c,str) and c.startswith('sudo pip3')]
        return defect(len(apt)==27 and len(pip)==33 and 'sudo reboot' in commands,
                      {'apt_commands_failed':len(apt),'pip_commands_failed':len(pip),
                       'reboot_requested':True,'service_files_in_memory':list(files),
                       'real_os_commands_executed':0,'real_system_files_written':0})
    observe('SETUP-FULL','install','Full installer sandbox: all package failures still reach reboot',full_installer,'high')
    def disconnect_after_home():
        e=server_env();sock=ScriptSocket(['forward','home'])
        err=expect_error(lambda:asyncio.run(e['recv_msg'](sock)),IndexError)
        return defect(move.motor1.throttle==1,{'sequence':['forward','home'],
                      'error':err,'motor_after_exception':move.motor1.throttle})
    observe('FAULT-HOME-MOVING','fault','HOME exception after driving retains output',disconnect_after_home,'high')
    for value in [201,float('nan')]:
        def check(value=value):
            e=functions_env();calls=[0]
            def sample():
                calls[0]+=1
                if calls[0]>1000:raise StopReplay('1000-read test limit')
                return value
            e['ultra'].checkdist=sample
            err=expect_error(e['Functions']().distRedress,StopReplay)
            return defect(True,{'sample':str(value),'reads':calls[0],'error':err,
                               'note':'injected out-of-range sensor fault; physical occurrence not established'})
        observe('DIST-FAULT-'+str(value),'fault','Invalid distance replay has no retry limit',check,'medium')
    def timeout():
        e=server_env()
        async def scenario():
            async def silent_recv():await asyncio.Future()
            sock=ScriptSocket(['forward'])
            original=sock.recv
            async def recv():
                if sock.messages:return await original()
                return await silent_recv()
            sock.recv=recv
            task=asyncio.create_task(e['recv_msg'](sock))
            await asyncio.sleep(.08)
            val=move.motor1.throttle
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            return val
        val=asyncio.run(scenario())
        return defect(val==1 and move.motor1.throttle==1,{'quiet_connection_observation_ms':80,
                      'output_before_and_after_task_cancel':[val,move.motor1.throttle],
                      'note':'no real timeout threshold measured; source has bare recv with no wait_for/watchdog'})
    observe('FAULT-SILENT','fault','Silent connection and task cancellation retain motor command',timeout,'high')
    def original_source_hashes():
        import zipfile
        path=next((ROOT/'working_copy').glob('ADR012*.zip'))
        mismatch=[]
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if '/Code/adeept_picar-b2/' in n and n.endswith('.py'):
                    rel=n.split('/Code/adeept_picar-b2/',1)[1]
                    if (SOURCE/rel).read_bytes()!=z.read(n):mismatch.append(rel)
        return must(not mismatch,{'vendor_python_files':35,'baseline_mismatches':mismatch})
    observe('INTEGRITY-SOURCE','integrity','Test baseline matches full ZIP copy byte for byte',original_source_hashes)

def main():
    for fn in [static_checks,motor_tests,servo_tests,command_tests,algorithm_tests,vision_tests,http_tests,websocket_tests,setup_tests,misc_tests,extra_fault_tests]:fn()
    metadata=dict(python=sys.version,platform=platform.platform(),websockets=websockets.__version__,
                  numpy=np.__version__,opencv=cv2.__version__,
                  source_sha256={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(SOURCE.rglob('*.py'))})
    summary=dict(Counter(r['status'] for r in RESULTS))
    result={'metadata':metadata,'summary':summary,'tests':RESULTS}
    (ROOT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUMMARY',summary)
    return 1 if summary.get('HARNESS_ERROR') else 0

if __name__=='__main__':sys.exit(main())
