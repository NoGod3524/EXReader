# SPDX-License-Identifier: MIT
"""Check saved text manifests and the actual measured binary inputs."""
import argparse,hashlib,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--text-only',action='store_true');args=ap.parse_args()
H=Path(__file__).resolve().parent
s=json.loads((H/'summary.json').read_text());b=json.loads((H/'build.json').read_text())
assert not list((H/'raw').glob('*.partial.json'))
for mapping in (s['files'],s['scripts']):
    for name,expected in mapping.items():
        data=(H/name).read_bytes();data=data if name.endswith('.gz') else data.replace(b'\r\n',b'\n')
        assert hashlib.sha256(data).hexdigest()==expected,name
for name,expected in ({} if args.text_only else b['files']).items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
result={'accepted_children':len(s['files']),'matching_diagnostic_page_hashes':s['matching_page_hashes'],'verified_binary_and_build_input_files':0 if args.text_only else len(b['files']),'verified_raw_and_source_artifacts':len(s['files'])+len(s['scripts']),'partial_files':0}
if not args.text_only:(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
