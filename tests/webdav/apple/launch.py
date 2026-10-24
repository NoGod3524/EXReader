#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only command adapter; all requests execute inside a UIKit app worker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

assert os.environ.get('GITHUB_ACTIONS') == 'true'
udid, bundle = os.environ['EXR_DAV_IOS_UDID'], 'org.exreader.webdav.probe'
documents = Path(os.environ['EXR_DAV_IOS_CONTAINER']) / 'Documents'
documents.mkdir(exist_ok=True)
request, result = documents / 'request.json', documents / 'result.json'
subprocess.run(['xcrun', 'simctl', 'terminate', udid, bundle], capture_output=True)
result.unlink(missing_ok=True)
arguments = ['WebDAVProbe'] + sys.argv[1:]
assert len(arguments) == 12
original = Path(arguments[5])
private = documents / 'case'
if private.exists():
    shutil.rmtree(private)
shutil.copytree(original, private, symlinks=True)
arguments[5] = str(private)
request.write_text(json.dumps(arguments), encoding='utf-8')
try:
    subprocess.run(['xcrun', 'simctl', 'launch', udid, bundle], check=True, capture_output=True)
    deadline = time.monotonic() + 130
    while not result.is_file():
        assert time.monotonic() < deadline, 'native simulator request exceeded its outer deadline'
        time.sleep(.05)
    value = json.loads(result.read_text(encoding='utf-8'))
    assert 'probe_failure' not in value, 'native installed consumer failed'
    # Mirror the app-private publication back for the unchanged original checks.
    for child in original.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(private, original, symlinks=True, dirs_exist_ok=True)
    print(json.dumps(value, ensure_ascii=False))
finally:
    request.unlink(missing_ok=True)
