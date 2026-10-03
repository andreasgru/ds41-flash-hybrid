#!/usr/bin/env python3
"""Resolve local bind endpoints shared by the launcher and its probes."""
import ipaddress
import re
import socket
import sys


_IPV4_LOOPBACK = ipaddress.ip_network('127.0.0.0/8')
_IPV6_LOOPBACK = ipaddress.IPv6Address('::1')


def resolve_host(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('BIND_HOST_INVALID')
    if any(char in value for char in '/\\@?#[]%'):
        raise ValueError('BIND_HOST_INVALID')
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError('BIND_HOST_INVALID') from exc
    if isinstance(address, ipaddress.IPv4Address):
        if address not in _IPV4_LOOPBACK:
            raise ValueError('BIND_HOST_LOOPBACK_REQUIRED')
    elif address != _IPV6_LOOPBACK:
        raise ValueError('BIND_HOST_LOOPBACK_REQUIRED')
    return address.compressed


def resolve_port(value):
    if type(value) is int:
        port = value
    elif isinstance(value, str) and re.fullmatch(r'[0-9]{1,5}', value):
        port = int(value, 10)
    else:
        raise ValueError('BIND_PORT_INVALID')
    if not 1 <= port <= 65535:
        raise ValueError('BIND_PORT_INVALID')
    return port


def resolve_endpoint(host, port):
    return resolve_host(host), resolve_port(port)


def base_url(host, port):
    host, port = resolve_endpoint(host, port)
    authority = f'[{host}]' if ':' in host else host
    return f'http://{authority}:{port}'


def address_family(host):
    host = resolve_host(host)
    return socket.AF_INET6 if ':' in host else socket.AF_INET


def socket_address(host, port):
    host, port = resolve_endpoint(host, port)
    if ':' in host:
        return host, port, 0, 0
    return host, port


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print('ENDPOINT_ARGUMENTS_INVALID', file=sys.stderr)
        return 2
    try:
        host, port = resolve_endpoint(argv[0], argv[1])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f'{host}\t{port}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
