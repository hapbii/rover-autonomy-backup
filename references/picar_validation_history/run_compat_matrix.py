"""Reproduce compatibility probes using already prepared isolated runtimes."""
import json,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parent
configs=[('3.11.9 / ws13',r/'.venv311/Scripts/python.exe',None),
         ('3.13.5 / ws13',r/'.venv313/Scripts/python.exe',None),
         ('3.13.5 / ws14.2',r/'.venv313/Scripts/python.exe',r/'deps_ws142'),
         ('3.14.6 / ws13',Path(sys.executable),r/'.venv313/Lib/site-packages'),
         ('3.14.6 / ws14.2',Path(sys.executable),r/'deps_ws142')]
results=[]
for label,python,deps in configs:
    for mode in ['original','running_loop','adapted']:
        cmd=[str(python),str(r/'compat_probe.py'),'--mode',mode]
        if deps:cmd+=['--deps',str(deps)]
        p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=12)
        try:result=json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:result={'status':'HARNESS_ERROR','stdout':p.stdout,'stderr':p.stderr}
        result['label']=label;result['stderr']=p.stderr[-1500:]
        results.append(result);print(label,mode,result['status'],result.get('error',''))
(r/'compat_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert not any(t['status']=='HARNESS_ERROR' for t in results)
