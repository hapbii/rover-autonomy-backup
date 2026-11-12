"""Run each probe in a fresh process, with optional isolated websocket package."""
import argparse,ast,asyncio,json,logging,platform,sys,threading,warnings
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--deps')
parser.add_argument('--mode',choices=['original','running_loop','adapted'],default='original')
args=parser.parse_args()
if args.deps:sys.path.insert(0,args.deps)
import websockets
server_errors=[]
class Capture(logging.Handler):
    def emit(self,record):
        if record.exc_info:server_errors.append(type(record.exc_info[1]).__name__+': '+str(record.exc_info[1]))
logger=logging.getLogger('websockets.server')
logger.handlers=[Capture()];logger.propagate=False;logger.setLevel(logging.ERROR)
root=Path(__file__).resolve().parent
ns={}
async def permit(ws):return True
async def receive(ws):
    await ws.send('ok')
ns.update(check_permit=permit,recv_msg=receive)
tree=ast.parse((root/'source/web/WebServer.py').read_text(encoding='utf-8-sig'))
fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='main_logic')
if args.mode=='adapted':fn.args.defaults=[ast.Constant(None)]
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'WebServer.py','exec'),ns)
async def talk(server):
    port=server.sockets[0].getsockname()[1]
    async with websockets.connect(f'ws://127.0.0.1:{port}') as ws:
        return await asyncio.wait_for(ws.recv(),2)
async def run_inside_loop():
    async with websockets.serve(ns['main_logic'],'127.0.0.1',0) as server:
        return await talk(server)
result={'python':platform.python_version(),'websockets':websockets.__version__,'mode':args.mode,
        'scope':'original startup idiom and original handler signature; hardware-free handler bodies'}
try:
    if args.mode=='original':
        # Original API invocation order, changing only bind IP and port.
        start_server=websockets.serve(ns['main_logic'],'127.0.0.1',0)
        loop=asyncio.get_event_loop()
        server=loop.run_until_complete(start_server)
        try:answer=loop.run_until_complete(talk(server))
        finally:
            server.close();loop.run_until_complete(server.wait_closed());loop.close()
    else:answer=asyncio.run(run_inside_loop())
    result.update(status='PASS',answer=answer)
except Exception as e:result.update(status='INCOMPATIBLE',error=type(e).__name__+': '+str(e))
result['threading_Event_isSet']=hasattr(threading.Event(),'isSet')
result['server_errors']=server_errors
print(json.dumps(result))
