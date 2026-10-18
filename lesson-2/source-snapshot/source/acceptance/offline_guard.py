"""Process-level offline guard for the synthetic acceptance command."""
import os
from pathlib import Path
import socket
import subprocess

class OfflineNetworkError(RuntimeError):
    pass

_installed = False

def install():
    global _installed
    if _installed:
        return
    _installed = True
    allowed = {'127.0.0.1', '::1', 'localhost'}
    def check(address):
        if isinstance(address, tuple) and str(address[0]) not in allowed:
            raise OfflineNetworkError('offline acceptance blocked outbound socket')
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    def guarded_connect(self, address):
        check(address)
        return connect(self, address)
    def guarded_connect_ex(self, address):
        check(address)
        return connect_ex(self, address)
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    resolve = socket.getaddrinfo
    def guarded_resolve(host, *args, **kwargs):
        if host is not None and str(host) not in allowed:
            raise OfflineNetworkError('offline acceptance blocked DNS')
        return resolve(host, *args, **kwargs)
    socket.getaddrinfo = guarded_resolve
    popen = subprocess.Popen
    def guarded_popen(args, *rest, **kwargs):
        parts = [args] if isinstance(args, str) else list(args)
        command = Path(str(parts[0])).name.lower() if parts else ''
        if kwargs.get('shell') or command in {'curl', 'wget', 'hithink-finance', 'npm', 'npx'}:
            raise OfflineNetworkError('offline acceptance blocked external network command')
        return popen(args, *rest, **kwargs)
    subprocess.Popen = guarded_popen
    if '__file__' in globals():
        here = Path(__file__).resolve().parent
        child = here / 'guard_child'
        if child.is_dir():
            os.environ['PYTHONPATH'] = str(child)
    os.environ['EARNINGS_REVIEW_OFFLINE_ACCEPTANCE'] = '1'
