"""Actions-only installed-process test of the authenticated original 3.41 wire."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tests/reader_android_record_interop'))
from bundle import folder

bundle = root / 'build/android-sdk342-record/input'
out = root / 'build/android-sdk342-record/evidence'
out.mkdir(parents=True, exist_ok=True)
verified = folder(bundle)
sender = verified['manifest']['sender']
assert sender['source_sha'] == 'b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7'
assert str(sender['run_id']) == '40181402323' and str(sender['attempt']) == '1'
assert sender['platform'] == 'android' and sender['exr_version'] == '3.41.0'
attestation = dict(source_sha=sender['source_sha'], run_id=str(sender['run_id']),
                   attempt=str(sender['attempt']), manifest_sha256=verified['manifest_sha256'],
                   artifact_id=12594712144, artifact_digest='sha256:08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3')
(out / 'attestation.json').write_text(json.dumps(attestation, indent=2)+'\n')
package = 'org.exreader.host'
def adb(*args, input=None):
    return subprocess.check_output(['adb', *map(str,args)], input=input, stderr=subprocess.STDOUT, timeout=120)
def push(path, relative):
    tmp='/data/local/tmp/sdk342-'+hashlib.sha256(relative.encode()).hexdigest()
    adb('push', path, tmp)
    adb('exec-out','run-as',package,'mkdir','-p','files/'+str(Path(relative).parent))
    adb('exec-out','run-as',package,'cp',tmp,'files/'+relative)

adb('install','-r','-t',root/'examples/android/app/build/outputs/apk/debug/app-debug.apk')
adb('install','-r','-t',root/'examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk')
installed=adb('shell','pm','path',package).decode().strip()
assert installed.startswith('package:') and '\n' not in installed
pulled=out/'installed.apk'
adb('pull',installed[len('package:'):],pulled)
installed_sha=hashlib.sha256(pulled.read_bytes()).hexdigest()
assert installed_sha==hashlib.sha256((root/'examples/android/app/build/outputs/apk/debug/app-debug.apk').read_bytes()).hexdigest()
assert adb('shell','pm','clear',package).strip() == b'Success'
adb('shell','am','start','-W','-n',package+'/.MainActivity')
adb('shell','am','force-stop',package)
for name in verified['files']:
    push(bundle/name, 'interop-incoming/'+name)
push(out/'attestation.json', 'interop-incoming-attestation.json')
identity = {key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
args=['adb','shell','am','instrument','-w','-r']
for key,value in identity.items(): args += ['-e',key,value]
args += [package+'.test/'+package+'.Sdk342WireProbe']
process=subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1500)
(out/'instrumentation.txt').write_bytes(process.stdout)
raw=adb('exec-out','run-as',package,'cat','files/sdk342-wire-report.json')
(out/'report.json').write_bytes(raw)
report=json.loads(raw)
print(raw.decode('utf-8'), flush=True)
print(process.stdout.decode('utf-8', errors='replace'), flush=True)
assert process.returncode==0 and b'SDK342_WIRE_PROBE_PASS' in process.stdout and b'INSTRUMENTATION_CODE: -1' in process.stdout
assert report['passed'] is True and report['host_compatibility_accepted'] is True
assert all(report[k]==v for k,v in identity.items())
assert report['receiver']['exr_version']=='3.42.0' and report['receiver']['parser_version']=='exreader-sdk-3.42.0'
assert report['receiver']['apk_sha256']==installed_sha
assert len(report['resolutions']) >= 11
assert {r['role'] for r in report['resolutions']} == {'txt','epub','pdf','cbz'}
assert [row['name'] for row in report['checks']] == ['actual_341_wire_sdk342_host_resolve', 'actual_341_bookmarks_navigate_on_four_real_hosts']
print(json.dumps(dict(identity, semantic_probe_passed=True, host_compatibility_accepted=True,
                      count=len(report['resolutions']), sender=attestation), indent=2))
