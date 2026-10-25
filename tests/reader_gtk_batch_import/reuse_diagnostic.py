# SPDX-License-Identifier: MIT
"""Actions-only artifact diagnostic, with separate program and probe identities."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    run_id = int(sys.argv[1])
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True)
    repo = os.environ['GITHUB_REPOSITORY']
    headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'}
    api = 'https://api.github.com/repos/' + repo

    def get(path):
        with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=60) as response:
            return json.load(response)

    run = get('/actions/runs/' + str(run_id))
    assert run['status'] == 'completed' and run['path'] == '.github/workflows/reader-gtk-batch-import.yml'
    source = run['head_sha']
    subprocess.run(['git', 'cat-file', '-e', source + '^{commit}'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', source, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'apps/reader/batch-import', 'extras/sideload'], check=True)
    host_changes = subprocess.check_output(['git', 'diff', '--name-only', source, 'HEAD', '--', 'examples/linux', 'apps/reader/desktop'], text=True).splitlines()
    rows = get('/actions/runs/' + str(run_id) + '/artifacts')['artifacts']
    expected = 'reader-gtk-batch-import-%d-%d' % (run_id, run['run_attempt'])
    artifacts = [row for row in rows if row['name'] == expected]
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact['expired'] is False and artifact['size_in_bytes'] > 0 and artifact['digest'].startswith('sha256:')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, response_headers, new_url):
            return None

    request = urllib.request.Request(api + '/actions/artifacts/%d/zip' % artifact['id'], headers=headers)
    try:
        urllib.request.build_opener(NoRedirect()).open(request, timeout=60)
        raise AssertionError('artifact did not redirect to signed storage')
    except urllib.error.HTTPError as redirect:
        assert redirect.code == 302
        location = redirect.headers['Location']
    assert urllib.parse.urlsplit(location).scheme == 'https'
    # The bearer token goes only to api.github.com, never to signed blob storage.
    with urllib.request.urlopen(location, timeout=120) as response:
        data = response.read()
    assert len(data) == artifact['size_in_bytes']
    assert 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest']
    archive = output / 'archive'
    archive.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        for name in bundle.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts
        bundle.extractall(archive)
    original = json.loads((archive / 'gtk-batch-ui/report.json').read_text())
    assert original['source_sha'] == source and str(original['run_id']) == str(run_id)
    payload = output / 'payload'
    payload.mkdir()
    with tarfile.open(archive / 'account-package/EXReader-Linux.tar.gz') as bundle:
        for entry in bundle.getmembers():
            path = PurePosixPath(entry.name)
            assert not path.is_absolute() and '..' not in path.parts and (entry.isfile() or entry.isdir())
        bundle.extractall(payload)
    binary = payload / 'bin/exreader-linux'
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert digest == original['program_sha256']
    record = dict(accepted=False, diagnostic_only=True, test_source=os.environ['GITHUB_SHA'], program_source=source,
                  host_tree_equal=not host_changes, changed_host_paths=host_changes,
                  previous_run=run_id, artifact={key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                  program_sha256=digest, payload=str(payload))
    (output / 'input.json').write_text(json.dumps(record, indent=2) + '\n')
    with open(os.environ['GITHUB_ENV'], 'a') as environment:
        environment.write('DIAGNOSTIC_PAYLOAD=' + str(payload) + '\n')
        environment.write('DIAGNOSTIC_PROGRAM_SOURCE=' + source + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
