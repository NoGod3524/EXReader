"""Actions-only immutable historical archive inventory; never manufacture records."""
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
import urllib.parse
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
REPO = 'NoGod3524/EXReader'
EXPECTED = [
    (40131364703, '047648865e509d5835b7d6e1389681e314d94e28',
     'codex/reader-android-reading-ui', 12575367601, 136598458,
     '9519c0c26d219322cbd95d3914733661aaff40df6c0c2d7214969a72fa81cbd2'),
    (40428878676, 'd1b97161461f8fec6f6bdfebedd67a8ac9d0911e',
     'codex/windows-android-combined', 12701815512, 108012399,
     'c7415f88fdd80481bf1cd24ceb544bad4a3d49f0c138a680babbeb4675c809c1'),
]
out = Path('build/android340-sender-inventory')
out.mkdir(parents=True, exist_ok=True)

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        assert parsed.scheme == 'https', 'artifact redirect must remain HTTPS'
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if parsed.hostname != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected

opener = urllib.request.build_opener(SafeRedirect())

def fetch(path, binary=False):
    request = urllib.request.Request(
        f'https://api.github.com/repos/{REPO}/{path}',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    with opener.open(request, timeout=120) as response:
        data = response.read()
    return data if binary else json.loads(data)

results = []
for run_id, source, branch, artifact_id, size, digest in EXPECTED:
    run = fetch(f'actions/runs/{run_id}')
    assert run['head_sha'] == source and run['head_branch'] == branch
    assert run['run_attempt'] == 1 and run['status'] == 'completed'
    assert run['conclusion'] == 'success'
    artifact = fetch(f'actions/artifacts/{artifact_id}')
    assert artifact['workflow_run']['id'] == run_id
    assert artifact['workflow_run']['head_sha'] == source
    assert not artifact['expired'] and artifact['size_in_bytes'] == size
    assert artifact['digest'] == 'sha256:' + digest
    data = fetch(f'actions/artifacts/{artifact_id}/zip', binary=True)
    assert len(data) == size and hashlib.sha256(data).hexdigest() == digest
    entries = []
    selected = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        for info in archive.infolist():
            name = info.filename
            assert not name.startswith('/') and '..' not in Path(name).parts
            if info.is_dir():
                continue
            raw = archive.read(info)
            entries.append({'name': name, 'bytes': len(raw),
                            'sha256': hashlib.sha256(raw).hexdigest()})
            # Publish only selected test evidence, never arbitrary private files.
            if name.endswith(('/android-reading/ui/result.json',
                              '/android-reading/ui/killed-pending-request.json',
                              '/android-reading/ui/first-report.json')):
                selected[name] = json.loads(raw)
    result = {'run_id': run_id, 'attempt': 1, 'source_sha': source,
              'branch': branch, 'artifact_id': artifact_id,
              'artifact_bytes': size, 'artifact_sha256': digest,
              'authenticated': True, 'entries': entries, 'selected_reports': selected,
              'sender_bundle_accepted': False,
              'limit': 'Inventory is not a complete wire/HTTPS sender proof.'}
    (out / f'{run_id}.json').write_text(json.dumps(result, indent=2) + '\n')
    candidates = [row for row in entries if any(word in row['name'].lower()
                  for word in ('revision', 'outbox', '.db', 'bundle', 'pending-request'))]
    print(json.dumps({'run_id': run_id, 'artifact_id': artifact_id,
                     'authenticated': True, 'candidate_entries': candidates}), flush=True)
    results.append({key: value for key, value in result.items()
                    if key not in ('entries', 'selected_reports')})
(out / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
