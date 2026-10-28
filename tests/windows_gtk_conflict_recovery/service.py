"""Reuse retained DAV protocol, preserving each real profile's bound HTTPS root.
Only endpoint allocation differs; no revision/object payload is synthesized.
"""
import configparser,hashlib
from pathlib import Path
from urllib.parse import urlsplit
import relay

def start(folder,previous):
    config=configparser.ConfigParser(interpolation=None);config.read(Path(folder)/'profile/account.ini',encoding='utf-8-sig')
    root=config['account']['root'];url=urlsplit(root)
    assert url.scheme=='https' and url.hostname=='127.0.0.1' and url.port and url.path=='/dav/'
    original=relay.ThreadingHTTPServer
    class BoundServer(original):
        allow_reuse_address=True
        def __init__(self,address,handler):super().__init__(('127.0.0.1',url.port),handler)
    relay.ThreadingHTTPServer=BoundServer
    try:result=relay.start(folder,previous)
    finally:relay.ThreadingHTTPServer=original
    assert result[0].base+'/dav/'==root
    return result
