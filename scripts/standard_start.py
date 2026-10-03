#!/usr/bin/env python3
"""Start the selected service, wait for READY and run the synthetic warmup.

Origin: own portable standard-start implementation. Apache-2.0.
"""
import importlib.util
import json
import os
import time
from pathlib import Path

def load(root,name):
    spec=importlib.util.spec_from_file_location(name,root/'scripts'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def await_ready(run,clock=time.monotonic,sleep=time.sleep):
    started=clock()
    while clock()-started<5400:
        path=run/'status.txt';text=path.read_text() if path.exists() else ''
        if ' EXIT rc=' in text or (run/'exit.code').exists():raise ValueError('SERVICE_EXITED_BEFORE_WARMUP')
        if any(line.endswith(' READY') for line in text.splitlines()):return
        sleep(2)
    raise ValueError('STANDARD_READY_TIMEOUT')

def standard(env):
    root=Path(env['DS41_ROOT']);endpoint=load(root,'endpoint')
    host,port=endpoint.resolve_endpoint(env['DS41_BIND_HOST'],env['SGLANG_PORT'])
    env=dict(env,DS41_BIND_HOST=host,SGLANG_PORT=str(port))
    base=endpoint.base_url(host,port)
    supervisor=load(root,'supervisor');warmup=load(root,'warmup')
    run=supervisor.start(env);await_ready(run)
    warmup.run(base,'deepseek-v41-flash-kt-tp1',run/'warmup.json')
    report=json.loads((run/'warmup.json').read_text())
    if report.get('status')!='WARM_OK':raise ValueError('STANDARD_WARMUP_FAILED')
    with (run/'status.txt').open('a') as stream:stream.write(time.strftime('%Y-%m-%d %H:%M:%S')+' WARM_OK\n')
    print('STANDARD_READY run='+str(run))

if __name__=='__main__':standard(dict(os.environ))
