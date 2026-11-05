# SPDX-License-Identifier: MIT
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
PACKAGE = 'tests/apple_password_privacy_20261028/'
WORKFLOW = '.github/workflows/apple-password-privacy-20261028.yml'
DOC = 'docs/apple-password-privacy-20261028/STATUS.md'
BUNDLE = 'org.exreader.password-privacy-20261028'
CASE = 'testRememberThenUncheckUpdateDoesNotPersistSessionCredential'
STAGES = ['remember_closed', 'remember_reopened', 'session_closed', 'session_reopened_missing']

def require(value, message):
    if not value: raise RuntimeError(message)

def sha(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as file:
        for data in iter(lambda: file.read(1024 * 1024), b''): checksum.update(data)
    return checksum.hexdigest()

def case_name(value):
    require(re.findall(r'\btest[A-Za-z0-9_]+\b', value or '') == [CASE], 'unexpected native case identity')
    return CASE

def guard():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(source == os.environ['GITHUB_SHA'], 'checkout differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    changes = subprocess.check_output(['git', 'diff', '--name-status', BASE, source], cwd=ROOT, text=True).splitlines()
    require(bool(changes), 'empty scope')
    for change in changes:
        action, path = change.split('\t')
        require(action == 'A' and (path.startswith(PACKAGE) or path in (WORKFLOW, DOC)), 'old or foreign path changed')
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True).strip(), 'dirty source')
    return changes

def attachments(directory):
    stages, images = None, {}
    for group in json.loads((directory / 'manifest.json').read_text()):
        case_name(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item['exportedFileName']
            require(Path(filename).name == filename, 'unsafe attachment')
            path = directory / filename
            name = item['suggestedHumanReadableName']
            if name.startswith('privacy-stages.json'):
                require(stages is None, 'duplicate native stages')
                stages = json.loads(path.read_text())
            for stage in STAGES:
                role = 'privacy-' + stage
                if name.startswith(role + '_') or name == role + '.png':
                    require(stage not in images and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'invalid native screenshot')
                    images[stage] = {'file': str(path.relative_to(directory.parent)), 'sha256': sha(path)}
    require(stages is not None and stages['stages'] == STAGES and set(images) == set(STAGES), 'native stages/screenshots incomplete')
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', stages['profile']) is not None, 'invalid actual profile')
    require(stages['operation'] == 'real Remember off and Update; not a dedicated Forget action', 'operation mislabeled')
    return stages, images

if __name__ == '__main__': print(json.dumps(guard(), indent=2))
