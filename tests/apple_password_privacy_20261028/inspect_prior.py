#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only, pinned prior setup diagnosis. Never native/privacy acceptance."""
import json
import os
import re
import subprocess
from contract import ROOT, guard, require, sha
from archive_contract import safe_extract

RUN = '40773724953'
SOURCE = '7dc199ce383877aee1f45a44be8453b7d4268219'
ARTIFACT = 12853503868
DIGEST = '19d09f33f3bd30e6637a1acf1d3c4b94938bd194688e13fcb275baa2f8c1855b'


def sanitized(value):
    value = re.sub(r'Privacy-[0-9a-f]{64}!%:\+|privacy-user-[0-9a-f]{32}|Basic\s+[A-Za-z0-9+/=_-]+', '<redacted>', value)
    token = os.environ.get('GH_TOKEN', '')
    return value.replace(token, '<redacted>') if token else value


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    guard()
    out = ROOT / 'build/apple-password-privacy-prior'; out.mkdir(parents=True, exist_ok=False)
    endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(ARTIFACT)
    record = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    require(record['id'] == ARTIFACT and record['name'] == 'password-native-macos-' + RUN + '-1' and
            str(record['workflow_run']['id']) == RUN and record['workflow_run']['head_sha'] == SOURCE and
            record['digest'] == 'sha256:' + DIGEST and record['expired'] is False, 'prior artifact identity differs')
    original = out / 'original-upload.zip'
    with original.open('wb') as file:
        subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=file, check=True)
    require(original.stat().st_size == record['size_in_bytes'] == 5516 and sha(original) == DIGEST, 'prior original ZIP differs')
    folder = out / 'retained'; safe_extract(original, folder)
    files = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}
    require(files == {'sdk-identity.json', 'fixtures.log', 'source.epub', 'resource-manifest.json', 'project.log', 'result.json'},
            'not the expected precredential setup-only evidence')
    result = json.loads((folder / 'result.json').read_text())
    require((result['source_sha'], result['run_id'], result['attempt'], result['platform'], result['accepted']) ==
            (SOURCE, RUN, '1', 'macos', False), 'prior failed result differs')
    require(result['checkpoints'] == {} and [row['role'] for row in result['commands']] == ['fixtures', 'project'] and
            result['commands'][0]['exit'] == 0 and result['commands'][1]['exit'] != 0, 'not a precredential project failure')
    require(set(result['files']) == files - {'result.json'}, 'prior evidence inventory differs')
    for name, item in result['files'].items():
        path = folder / name
        require(path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'prior member differs')
    report = {'diagnostic_only': True, 'native_accepted': False, 'full_f10_accepted': False,
              'old_source_sha': SOURCE, 'old_run_id': RUN, 'old_attempt': 1,
              'artifact': record, 'commands': result['commands'], 'failure': result['failure']}
    (out / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('diagnostic_only', 'old_source_sha', 'old_run_id', 'commands', 'failure')}), flush=True)
    print('BEGIN RETAINED PRE-CREDENTIAL PROJECT LOG', flush=True)
    require((folder / 'project.log').stat().st_size <= 1024 * 1024, 'project diagnostic log unexpectedly large')
    print(sanitized((folder / 'project.log').read_text()), flush=True)
    print('END RETAINED PRE-CREDENTIAL PROJECT LOG', flush=True)


if __name__ == '__main__': main()
