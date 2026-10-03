#!/usr/bin/env python3
"""Ownership-checked reservations using the shared .flock convention.

Origin: own implementation of atomic reservation/release. Apache-2.0.
"""
import argparse
import fcntl
import json
import os
import re
from pathlib import Path

def run_path(env,run):
    root=Path(env['DS41_RUN_ROOT']).resolve(); supplied=Path(run)
    if supplied.is_symlink():raise ValueError('RUN_PATH_INVALID')
    path=supplied.resolve()
    if path.parent!=root or not path.name.startswith('ds41-serving-') or path.is_symlink():
        raise ValueError('RUN_PATH_INVALID')
    return path

class Reservation:
    def __init__(self,env):
        self.path=Path(env['DS41_LOCK_FILE']);self.owner=env['DS41_LOCK_OWNER'];self.env=env
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',self.owner):raise ValueError('LOCK_OWNER_INVALID')
    def update(self,operation,record):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        guard=self.path.with_name(self.path.name+'.flock')
        if self.path.is_symlink() or guard.is_symlink():raise ValueError('LOCK_SYMLINK_REJECTED')
        with guard.open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            raw=self.path.read_text() if self.path.exists() else ''
            lines=raw.splitlines();own=[]
            for i,line in enumerate(lines):
                if line.startswith(self.owner+' '):
                    try:own.append((i,json.loads(line[len(self.owner)+1:])))
                    except ValueError:raise ValueError('OWN_LOCK_RECORD_INVALID')
            if operation=='reserve':
                if any(line.strip() for line in lines):raise ValueError('GPU_LOCK_BUSY')
                lines=[self.owner+' '+json.dumps(record,separators=(',',':'))]
            elif operation=='release':
                matches=[i for i,value in own if value==record]
                if len(matches)!=1:raise ValueError('LOCK_RELEASE_OWNERSHIP_MISMATCH')
                lines=[line for i,line in enumerate(lines) if i!=matches[0]]
            elif operation=='handoff':
                old=record['from'];new=record['to']
                if len(lines)!=1 or own!=[(0,old)]:raise ValueError('HANDOFF_LOCK_INVALID')
                lines=[self.owner+' '+json.dumps(new,separators=(',',':'))]
            else:raise ValueError('LOCK_OPERATION_INVALID')
            # Same convention as the historical helper; rewrite under shared flock.
            with self.path.open('w') as output:
                output.write(''.join(line+'\n' for line in lines));output.flush();os.fsync(output.fileno())

def record(env,run):
    path=run_path(env,run)
    value=json.loads((path/'reservation.json').read_text())
    if value.get('run')!=str(path) or not re.fullmatch(r'ds41-serving-[a-f0-9]{32}\.service',value.get('unit','')) or not re.fullmatch(r'[a-f0-9]{32}',value.get('token','')):
        raise ValueError('RESERVATION_RECORD_INVALID')
    return value

def release(env,run):
    path=run_path(env,run);value=record(env,run)
    if (path/'retain-gpu-lock').exists():
        print('LOCK_RETAINED_FOR_HANDOFF');return
    Reservation(env).update('release',value);print('LOCK_RELEASED')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['release']);parser.add_argument('--run-dir',required=True)
    args=parser.parse_args();env=dict(os.environ);release(env,args.run_dir)
    path=run_path(env,args.run_dir)
    with (path/'status.txt').open('a') as stream:stream.write('UNIT_STOP_POST\n')
    if env.get('SERVICE_RESULT') and not (path/'exit.code').exists():
        code=0 if env['SERVICE_RESULT']=='success' else 1
        (path/'exit.code').write_text(str(code)+'\n')
