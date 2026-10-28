"""Ephemeral CI re-signing; require every non-signature APK entry identical."""
import hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('build/diagnostic');apk=Path('build/wave3/artifacts/app-debug.apk');original=out/'producer-original.apk';shutil.copyfile(apk,original)
tool=Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0/apksigner'
subprocess.run([str(tool),'sign','--ks',str(Path.home()/'.android/debug.keystore'),'--ks-key-alias','androiddebugkey','--ks-pass','pass:android','--key-pass','pass:android',str(apk)],check=True)
subprocess.run([str(tool),'verify','--verbose',str(apk)],check=True)
def entries(path):
 with zipfile.ZipFile(path) as z:
  return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not (n.upper()=='META-INF/MANIFEST.MF' or (n.upper().startswith('META-INF/') and n.upper().endswith(('.SF','.RSA','.DSA','.EC'))))}
before,after=entries(original),entries(apk);assert before==after
proof={'diagnostic_only':True,'producer_apk_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'resigned_diagnostic_apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'all_non_signature_entries_identical':True,'entries':before,'native_and_dex':{n:h for n,h in before.items() if n.endswith(('.dex','.so'))},'ephemeral_ci_debug_key_only':True}
assert proof['native_and_dex'];(out/'apk-payload-proof.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,indent=2))
