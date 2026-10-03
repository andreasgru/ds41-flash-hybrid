#!/usr/bin/env python3
"""Service ownership, memory limits and parser readiness for the live r3 path.

Origin: own portable implementation of the live safety checks. Apache-2.0.
"""
import argparse
import importlib.util
import json
import os
import shlex
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

GIB=1024**3
def module(root,name):
    spec=importlib.util.spec_from_file_location(name,root/'scripts'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def fields(path):
    result={}
    for line in path.read_text().splitlines():
        parts=line.replace(':','').split()
        if parts[0]=='Node':result[parts[2]]=int(parts[3])
        else:result[parts[0]]=int(parts[1])
    return result

def memory(cgroup):
    system=fields(Path('/proc/meminfo'));nodes=[fields(Path(f'/sys/devices/system/node/node{i}/meminfo')) for i in (0,1)]
    cg=fields(cgroup/'memory.stat')
    return {'available':system['MemAvailable']*1024,'swap':(system['SwapTotal']-system['SwapFree'])*1024,
            'nodes':[(n['MemFree']+n['FilePages'])*1024 for n in nodes],
            'current':int((cgroup/'memory.current').read_text()),'anon_shmem':cg['anon']+cg['shmem']}

def resource_guard(stats,baseline,maximum):
    if stats['available']<60*GIB or any(n<2*GIB for n in stats['nodes']) or stats['swap']-baseline>GIB or stats['anon_shmem']>(maximum-20)*GIB:
        raise ValueError('RESOURCE_STOP')

def parser_ready(info):
    expected={'tool_call_parser':'deepseekv41','reasoning_parser':'deepseek-v41'}
    states=info.get('internal_states')
    if not isinstance(states,list) or not states or {k:info.get(k) for k in expected}!=expected or any(not isinstance(s,dict) or {k:s.get(k) for k in expected}!=expected for s in states):
        raise ValueError('PARSER_CHECK_FAILED')
    return True

def cgroup_owner(env,read=Path.read_text):
    if not env.get('INVOCATION_ID'):raise ValueError('SERVICE_INVOCATION_REQUIRED')
    unit=env['DS41_UNIT'];entries=read(Path('/proc/self/cgroup')).splitlines()
    paths=[line.split(':',2)[2] for line in entries if line.startswith('0::')]
    if len(paths)!=1 or not paths[0].endswith('/'+unit):raise ValueError('SERVICE_CGROUP_MISMATCH')
    path=Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    if int(read(path/'memory.max'))!=360*GIB or int(read(path/'memory.swap.max'))!=0:
        raise ValueError('SERVICE_MEMORY_LIMIT_MISMATCH')
    return path

def request(url):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=5) as response:return json.load(response)

def preflight(root,env,runner=subprocess.run):
    endpoint=module(root,'endpoint')
    host,port=endpoint.resolve_endpoint(env['DS41_BIND_HOST'],env['SGLANG_PORT'])
    model=Path(env['DS41_MODEL_DIR'])
    module(root,'verify_runtime').validate_runtime(root)
    module(root,'verify_model_shards').validate_readiness(model)
    if not (Path(env['DS41_ENGRAM_DIR'])/'engram-manifest.json').is_file():raise ValueError('ENGRAM_NOT_READY')
    runner([env['DS41_PYTHON'],str(root/'tools/check-cache-paths.py'),'--resolve'],env=env,check=True,capture_output=True,text=True,timeout=30)
    cache=Path(env['DS41_CACHE_ROOT'])/'flashinfer'
    if not (root/'first-start.at').exists() and cache.exists() and any(cache.iterdir()):raise ValueError('FIRST_START_CACHE_NOT_EMPTY')
    if fields(Path('/proc/meminfo'))['MemAvailable']*1024<420*GIB:raise ValueError('RAM_BUDGET_UNAVAILABLE')
    gpu=runner(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader'],check=True,capture_output=True,text=True,timeout=10)
    if gpu.stdout.strip():raise ValueError('GPU_COMPUTE_BUSY')
    units=runner(['systemctl','list-units','ds41-serving-*','--state=active','--no-legend'],check=True,capture_output=True,text=True,timeout=10)
    if units.stdout.strip():raise ValueError('ACTIVE_SERVICE_BUSY')
    with socket.socket(endpoint.address_family(host)) as probe:probe.bind(endpoint.socket_address(host,port))

def start(env):
    root=Path(env['DS41_ROOT']).resolve();endpoint=module(root,'endpoint')
    host,port=endpoint.resolve_endpoint(env['DS41_BIND_HOST'],env['SGLANG_PORT'])
    env=dict(env,DS41_BIND_HOST=host,SGLANG_PORT=str(port))
    resolved=module(root,'resolve_launcher').resolve(env)
    preflight(root,resolved['environment'])
    key=uuid.uuid4().hex;unit='ds41-serving-'+key+'.service'
    run=Path(env['DS41_RUN_ROOT']).resolve()/('ds41-serving-'+key);run.mkdir(parents=True)
    lock=module(root,'gpu_lock');value={'unit':unit,'run':str(run),'token':uuid.uuid4().hex}
    (run/'reservation.json').write_text(json.dumps(value)+'\n');(run/'unit.txt').write_text(unit+'\n')
    state=lock.Reservation(env)
    if env.get('DS41_HANDOFF_LOCK','0')=='1':
        old=lock.run_path(env,env['DS41_HANDOFF_FROM']);prior=lock.record(env,str(old))
        if not (old/'retain-gpu-lock').is_file():raise ValueError('HANDOFF_MARKER_MISSING')
        pid=subprocess.check_output(['systemctl','show',prior['unit'],'-p','MainPID','--value'],text=True,timeout=10).strip()
        if pid!='0':raise ValueError('OLD_UNIT_RUNNING')
        state.update('handoff',{'from':prior,'to':value})
    else:state.update('reserve',value)
    transferred=False
    try:
        preflight(root,resolved['environment'])
        service_env=dict(resolved['environment'],DS41_UNIT=unit,DS41_RUN_DIR=str(run))
        command=['sudo','-n','systemd-run','--unit='+unit,'--uid='+env['DS41_SERVICE_USER'],'--service-type=exec',
            '-p','MemoryMax=360G','-p','MemorySwapMax=0','-p','KillMode=control-group','-p','OOMPolicy=stop','-p','TimeoutStopSec=30',
            '-p','ExecStopPost='+shlex.join([env['DS41_PYTHON'],str(root/'scripts/gpu_lock.py'),'release','--run-dir',str(run)]),
            '--working-directory='+str(root)]
        command += ['--setenv='+k+'='+v for k,v in service_env.items()]
        command += [env['DS41_PYTHON'],str(root/'scripts/supervisor.py'),'--supervise']
        subprocess.run(command,check=True,timeout=30);transferred=True
        (root/'first-start.at').touch(exist_ok=True)
        print(json.dumps({'unit':unit,'run_dir':str(run)}));return run
    finally:
        if not transferred:state.update('release',value)

def supervise(env):
    root=Path(env['DS41_ROOT']).resolve();endpoint=module(root,'endpoint')
    host,port=endpoint.resolve_endpoint(env['DS41_BIND_HOST'],env['SGLANG_PORT'])
    env=dict(env,DS41_BIND_HOST=host,SGLANG_PORT=str(port))
    lock=module(root,'gpu_lock');run=lock.run_path(env,env['DS41_RUN_DIR'])
    value=lock.record(env,str(run))
    if value['unit']!=env['DS41_UNIT']:raise ValueError('SERVICE_RESERVATION_MISMATCH')
    cg=cgroup_owner(env);resolved=module(root,'resolve_launcher').resolve(env)
    base=endpoint.base_url(host,port)
    def status(message):
        with (run/'status.txt').open('a') as stream:stream.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+message+'\n')
    baseline=memory(cg)['swap'];started=time.monotonic();ready=False
    previous={}
    def interrupted(number,frame):raise SystemExit(128+number)
    for number in (signal.SIGTERM,signal.SIGINT):
        previous[number]=signal.signal(number,interrupted)
    with (run/'server.log').open('a') as log:
        child=subprocess.Popen(resolved['command'],env=resolved['environment'],stdout=log,stderr=log)
        (run/'server.pid').write_text(str(child.pid)+'\n')
        try:
            while child.poll() is None:
                stats=memory(cg);resource_guard(stats,baseline,360)
                status('MEM '+json.dumps(stats,separators=(',',':')))
                if not ready:
                    try:
                        # A successful health request precedes parser resolution.
                        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base+'/health',timeout=5):pass
                    except OSError:pass
                    else:
                        try:
                            info=request(base+'/get_server_info')
                        except OSError as exc:
                            if isinstance(exc,urllib.error.HTTPError):raise
                            reason=getattr(exc,'reason',exc)
                            if not isinstance(reason,OSError):raise
                            status('SERVER_INFO_RETRY '+type(exc).__name__)
                        else:
                            parser_ready(info)
                            keys=('tool_call_parser','reasoning_parser')
                            filtered={'server':{k:info[k] for k in keys},'workers':[{k:s[k] for k in keys} for s in info['internal_states']]}
                            (run/'resolved-parsers.json').write_text(json.dumps(filtered)+'\n');ready=True;status('READY')
                    if not ready and time.monotonic()-started>=5400:raise ValueError('LOAD_TIMEOUT')
                time.sleep(2)
            rc=child.wait();status('EXIT rc='+str(rc));(run/'exit.code').write_text(str(rc)+'\n')
            return rc
        except BaseException as exc:
            code=exc.code if isinstance(exc,SystemExit) and type(exc.code) is int else 1
            status('ABORT '+type(exc).__name__);status('EXIT rc='+str(code));(run/'exit.code').write_text(str(code)+'\n')
            raise
        finally:
            # Only the Popen child created here is signalled; service kills its cgroup.
            if child.poll() is None:child.terminate()
            for number,handler in previous.items():signal.signal(number,handler)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['--run','--supervise'])
    # Flags are handled explicitly to avoid treating --run as an argparse option.
    import sys
    if len(sys.argv)!=2 or sys.argv[1] not in ('--run','--supervise'):parser.error('expected --run or --supervise')
    if sys.argv[1]=='--run':start(dict(os.environ))
    else:sys.exit(supervise(dict(os.environ)))
