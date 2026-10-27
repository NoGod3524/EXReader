# SPDX-License-Identifier: MIT
"""Exercise actual account session terminal callbacks against the native TLS fixture."""
import base64
import os
from pathlib import Path
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(Path('tests/apple_host/account').resolve()))
from check_account import with_fixture

password = 'terminal-fixture-password'
authorization = 'Basic ' + base64.b64encode(('reader:' + password).encode()).decode()
output = Path('build/account-terminal').resolve()
output.mkdir(parents=True, exist_ok=True)

def run(root, entries, requests, certificate):
    env = dict(os.environ, READER_ACCOUNT_TEST_PASSWORD=password)
    subprocess.run([str(output / 'account-terminal'), root, str(output / 'accounts'),
                    str(Path('apps/reader/store/001_catalog.sql').resolve())], env=env, check=True)
    assert any(row['authenticated'] for row in requests)
    assert any(not row['authenticated'] for row in requests)

with_fixture(output / 'fixture', authorization, run, shard_delay=0.5)
