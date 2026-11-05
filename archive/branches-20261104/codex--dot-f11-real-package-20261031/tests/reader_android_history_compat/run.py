"""Separate API34 installed-host bootstrap observations; never alters old130 verdicts."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('build/current-android/history-compat');out.mkdir(parents=True,exist_ok=True)
identity={k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
args=['adb','shell','am','instrument','-w','-r']
for k,v in identity.items():args+=['-e',k,v]
args+=['org.exreader.host.test/org.exreader.host.HistoryCompatTest']
raw=subprocess.check_output(args,stderr=subprocess.STDOUT,timeout=240)
(out/'instrumentation.txt').write_bytes(raw)
body=subprocess.check_output(['adb','exec-out','run-as','org.exreader.host','cat','files/history-compat-report.json'],timeout=30)
(out/'raw-report.json').write_bytes(body)
report=json.loads(body)
assert b'INSTRUMENTATION_CODE: -1' in raw and b'FAILURES' not in raw and report['passed'] is True,raw.decode(errors='replace')
assert all(report.get(k)==v for k,v in identity.items()) and report['api']==34
assert len(report['observations'])==8
(out/'result.json').write_text(json.dumps(dict(**identity,accepted=True,checks=8,physical_device=False,
 report_sha256=hashlib.sha256(body).hexdigest(),report=report),indent=2)+'\n')
print(json.dumps(report),flush=True)
