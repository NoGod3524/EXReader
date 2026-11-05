#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions adapter: the complete SDK/session probe executes on an iOS worker."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

assert os.environ.get('GITHUB_ACTIONS') == 'true'
udid, bundle = os.environ['EXR_DAV_IOS_UDID'], 'org.exreader.session.probe'
documents = Path(os.environ['EXR_DAV_IOS_CONTAINER']) / 'Documents'
documents.mkdir(exist_ok=True)
arguments = ['ReaderSessionProbe'] + sys.argv[1:]
locations = {arguments[i]: Path(arguments[i + 1]) for i in range(1, len(arguments) - 1, 2)
             if arguments[i] in ('--fixtures', '--font', '--work', '--report')}
assert len(locations) == 4
for name in ('fixtures', 'work'):
    destination = documents / name
    if destination.exists(): shutil.rmtree(destination)
    shutil.copytree(locations['--' + name], destination)
shutil.copyfile(locations['--font'], documents / 'font.ttf')
replacements = {'--fixtures': documents / 'fixtures', '--font': documents / 'font.ttf',
                '--work': documents / 'work', '--report': documents / 'probe.json'}
for i in range(1, len(arguments) - 1, 2):
    if arguments[i] in replacements: arguments[i + 1] = str(replacements[arguments[i]])
subprocess.run(['xcrun', 'simctl', 'terminate', udid, bundle], capture_output=True)
completion = documents / 'completion.json'; completion.unlink(missing_ok=True)
request = documents / 'request.json'
request.write_text(json.dumps({'arguments': arguments, 'authorization': os.environ['READER_TEST_AUTH']}), encoding='utf-8')
try:
    launched = subprocess.run(['xcrun', 'simctl', 'launch', udid, bundle], capture_output=True, text=True, check=True)
    process = int(re.search(r':\s*(\d+)\s*$', launched.stdout).group(1))
    deadline = time.monotonic() + 1100
    while not completion.is_file():
        assert time.monotonic() < deadline, 'iOS account probe outer deadline'
        try: os.kill(process, 0)
        except ProcessLookupError: raise AssertionError('native app exited before completing SDK/account probe')
        time.sleep(.1)
    value = json.loads(completion.read_text(encoding='utf-8'))
    assert value['code'] == 0 and value['main_thread_ticks'] > 0, value
    shutil.copytree(documents / 'work', locations['--work'], dirs_exist_ok=True)
    shutil.copyfile(documents / 'probe.json', locations['--report'])
    shutil.copyfile(documents / 'probe.json.sessions.json', str(locations['--report']) + '.sessions.json')
    shutil.copyfile(completion, str(locations['--report']) + '.lifecycle.json')
finally:
    request.unlink(missing_ok=True)
    if (documents / 'probe.log').is_file():
        print((documents / 'probe.log').read_text(encoding='utf-8', errors='replace')[-10000:])
