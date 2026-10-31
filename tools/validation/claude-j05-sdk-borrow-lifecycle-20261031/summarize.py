# SPDX-License-Identifier: MIT
"""J05: bind the lifecycle event log to the installed SDK identity. Actions only."""
import hashlib, json, subprocess, sys
from pathlib import Path
sdk, log, out, sdk_src = (Path(a) for a in sys.argv[1:5])
rows = [json.loads(l) for l in log.read_text().splitlines() if l.startswith('{')]
checks = [r for r in rows if 'check' in r]
failed = [r for r in checks if not r['pass']]
files = {str(p.relative_to(sdk)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(sdk.rglob('*')) if p.is_file() and (p.suffix in ('.a', '.so', '.h') or 'lib' in p.parts[:1])}
matrix = {}
for r in checks:
    matrix.setdefault(r['scenario'], []).append({'check': r['check'], 'pass': r['pass'], 'db_fds': r['db_fds'], 'seq': r['seq']})
summary = {'sdk_commit': subprocess.check_output(['git', '-C', str(sdk_src), 'rev-parse', 'HEAD'], text=True).strip(),
           'sdk_version_reported': next((r['sdk_version'] for r in rows if 'sdk_version' in r), None),
           'checks': len(checks), 'failed': len(failed), 'failed_detail': failed, 'matrix': matrix,
           'installed_files_sha256': files, 'observation': '/proc/self/fd entries for the library database and its -wal/-shm/-journal sidecars',
           'binding_scope': 'C ABI, Linux x86_64 only; not Android/JNI, Swift, Windows or six-platform',
           'not_tested': 'repeated close/release (undefined by header contract); delete-book invalidation',
           'gate_integration': False}
out.mkdir(parents=True, exist_ok=True)
(out / 'summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps({k: summary[k] for k in ('sdk_commit', 'sdk_version_reported', 'checks', 'failed')}))
sys.exit(1 if failed or summary['sdk_commit'] != '8357eafa28423a7ab93ba08b823af80f01ad1505' else 0)
