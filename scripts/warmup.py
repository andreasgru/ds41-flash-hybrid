#!/usr/bin/env python3
"""Synthetic, exact-token warmup; no imported corpora or benchmark claims."""
import argparse
import importlib.util
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

SEED = 'A synthetic warmup sequence describes numbered rows and neutral symbols. '
TARGETS = (32768, 8192)

def local_base(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'http' or p.username or p.password or '@' in p.netloc or p.path not in ('', '/') or p.query or p.fragment:
        raise ValueError('WARMUP_URL_INVALID')
    try:
        spec = importlib.util.spec_from_file_location('ds41_endpoint', Path(__file__).with_name('endpoint.py'))
        endpoint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(endpoint)
        host = endpoint.resolve_host(p.hostname or '')
        port = endpoint.resolve_port(p.port)
    except ValueError as exc:
        raise ValueError('WARMUP_LOOPBACK_REQUIRED') from exc
    return endpoint.base_url(host, port)

def token_seed(response):
    tokens = response.get('tokens')
    count = response.get('count')
    if not isinstance(tokens, list) or not tokens or any(type(x) is not int or x < 0 for x in tokens) or type(count) is not int or count != len(tokens):
        raise ValueError('WARMUP_TOKENIZER_RESPONSE_INVALID')
    return tokens

def exact_ids(seed, target):
    if not seed or type(target) is not int or target <= 0:
        raise ValueError('WARMUP_TOKEN_COUNT_INVALID')
    return (seed * ((target+len(seed)-1)//len(seed)))[:target]

def completion_usage(response, expected):
    usage = response.get('usage')
    choices = response.get('choices')
    if not isinstance(usage, dict) or not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('WARMUP_COMPLETION_RESPONSE_INVALID')
    if type(usage.get('prompt_tokens')) is not int or usage['prompt_tokens'] != expected:
        raise ValueError('WARMUP_PROMPT_COUNT_MISMATCH')
    if type(usage.get('completion_tokens')) is not int or usage['completion_tokens'] != 16:
        raise ValueError('WARMUP_OUTPUT_COUNT_MISMATCH')
    if usage.get('total_tokens') != expected+16 or choices[0].get('finish_reason') != 'length':
        raise ValueError('WARMUP_COMPLETION_NOT_FINISHED')
    return usage

def post(base, endpoint, payload, timeout):
    request = urllib.request.Request(base+endpoint, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'ds41-multi-user-warmup/1.0'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('error'):
        raise ValueError('WARMUP_SERVER_ERROR')
    return result

def run(base, model, output, timeout=1200):
    base = local_base(base)
    output = Path(output)
    if output.exists():
        raise ValueError('WARMUP_OUTPUT_ALREADY_EXISTS')
    seed = token_seed(post(base, '/tokenize', {'model': model, 'prompt': SEED, 'add_special_tokens': False}, timeout))
    rows = []
    for target in TARGETS:
        ids = exact_ids(seed, target)
        started = time.monotonic()
        response = post(base, '/v1/completions', {'model': model, 'prompt': ids,
            'max_tokens': 16, 'temperature': 0, 'ignore_eos': True, 'stream': False}, timeout)
        usage = completion_usage(response, target)
        rows.append({'prompt_tokens': target, 'completion_tokens': usage['completion_tokens'],
                     'elapsed_seconds': time.monotonic()-started, 'input_kind': 'synthetic_token_ids'})
    report = {'status': 'WARM_OK', 'model': model, 'rows': rows,
              'method': '32768 then 8192 exact synthetic token ids; output 16; not a performance benchmark'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print('WARM_OK prompts=32768,8192 output_tokens=16')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base-url', required=True)
    p.add_argument('--model', default='deepseek-v41-flash-kt-tp1')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=1200)
    a = p.parse_args()
    if a.timeout <= 0:
        p.error('timeout must be positive')
    run(a.base_url, a.model, a.output, a.timeout)

if __name__ == '__main__':
    main()
