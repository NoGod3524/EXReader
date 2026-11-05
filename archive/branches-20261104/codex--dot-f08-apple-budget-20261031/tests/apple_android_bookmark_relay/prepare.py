"""Actions-only fixed F5 real EPUB acquisition; never select after SDK results."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

assert os.environ.get('GITHUB_ACTIONS') == 'true'
out = Path('build/apple-android/original')
out.mkdir(parents=True, exist_ok=True)
commit = '278d63691a4c73e7aa932d71a40a5938c5427514'
manifest = subprocess.check_output(['git', 'show', commit + ':tests/reader_real_corpus/manifest.json'])
assert hashlib.sha256(manifest).hexdigest() == 'be300d9a54329ab227ac7060bc39e0117de722ae3c60d6c0d998418eba994bf6'
entry = next(row for row in json.loads(manifest)['files'] if row['id'] == 'epub-alice')
source = entry['source']
assert source['sha256'] == '4f81245d31380ac1d6eafb9a321e3691369bc70985736ae4bccf849a4f784036'
assert source['bytes'] == 189249
with urllib.request.urlopen(source['url'], timeout=90) as response:
    body = response.read(2 * 1024 * 1024)
    final_url = response.url
assert len(body) == source['bytes'], 'Fixed F5 original length changed; do not silently replace'
assert hashlib.sha256(body).hexdigest() == source['sha256'], 'Fixed F5 original hash changed'
(out / 'epub-alice.epub').write_bytes(body)
(out / 'provenance.json').write_text(json.dumps({
    'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
    'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'manifest_commit': commit,
    'manifest_sha256': hashlib.sha256(manifest).hexdigest(), 'entry': entry,
    'retrieved_url': final_url, 'sha256': source['sha256'], 'bytes': len(body),
}, indent=2), encoding='utf-8')
print(json.dumps({'real_original': entry['id'], 'sha256': source['sha256'], 'bytes': len(body)}))
