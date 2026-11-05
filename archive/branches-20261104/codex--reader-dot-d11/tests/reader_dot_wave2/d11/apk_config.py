"""Inspect actual installed-input APK DEX constants, never infer flags from source."""
import hashlib,json,os,pathlib,subprocess,sys,zipfile
assert os.environ.get('GITHUB_ACTIONS')=='true'
apk=pathlib.Path(sys.argv[1]);out=pathlib.Path('build/d11/apk-config');out.mkdir(parents=True,exist_ok=True)
root=pathlib.Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','/usr/local/lib/android/sdk')))
tools=sorted(root.glob('build-tools/*/dexdump'));assert tools,'DEX observer not installed'
blocks=[]
with zipfile.ZipFile(apk) as z:
 for name in z.namelist():
  if '/' in name or not name.startswith('classes') or not name.endswith('.dex'):continue
  path=out/name;path.write_bytes(z.read(name));done=subprocess.run([str(tools[-1]),'-f',str(path)],capture_output=True,text=True);assert done.returncode==0,done.stderr
  (out/(name+'.dump.txt')).write_text(done.stdout)
  for block in done.stdout.split('Class #'):
   if "Lorg/exreader/host/BuildConfig;" in block:blocks.append(block)
assert len(blocks)==1,'actual BuildConfig constants unavailable or ambiguous'
report={'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'observer':str(tools[-1]),'buildconfig_raw':blocks[0]}
(out/'actual-config.json').write_text(json.dumps(report,indent=2));print('ACTUAL_APK_CONFIG '+json.dumps(report),flush=True)
