# SPDX-License-Identifier: MIT
"""Check saved text manifests, the replica derivation and the measured binary inputs."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--text-only',action='store_true');args=ap.parse_args()
H=Path(__file__).resolve().parent
s=json.loads((H/'summary.json').read_text());b=json.loads((H/'build.json').read_text())
assert not list((H/'raw').glob('*.partial.json'))
def text_sha(p):d=p.read_bytes();return hashlib.sha256(d if p.suffix=='.gz' else d.replace(b'\r\n',b'\n')).hexdigest()
for mapping in (s['files'],s['scripts']):
    for name,expected in mapping.items():assert text_sha(H/name)==expected,name
# replica.c must be exactly what make_replica.py derives from the checked-out src/affine_image.c.
saved=(H/'replica.c').read_bytes().replace(b'\r\n',b'\n')
subprocess.run([sys.executable,str(H/'make_replica.py')],check=True,capture_output=True)
assert (H/'replica.c').read_bytes().replace(b'\r\n',b'\n')==saved,'replica.c differs from its derivation'
for name,expected in ({} if args.text_only else b['files']).items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
result={'accepted_children':sum(1 for k in s['files'] if k.endswith('.json.gz')),'matching_diagnostic_page_hashes':s['matching_page_hashes'],
        'verified_binary_and_build_input_files':0 if args.text_only else len(b['files']),'verified_raw_and_source_artifacts':len(s['files'])+len(s['scripts']),
        'replica_rederived':True,'partial_files':0}
if not args.text_only:(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
