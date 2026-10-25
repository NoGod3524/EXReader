"""Actions-only actual installed SDK, single DSO and old-header rejection evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
out=Path('build/android-page-theme/native');out.mkdir(parents=True,exist_ok=True)
stage=Path('build/session-android/sdk-stage');header=(stage/'include/exr/base.h').read_text();assert '#define EXR_VERSION "3.41.0"' in header
ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
def tool(name,*args):return subprocess.check_output([str(ndk/name),*map(str,args)],text=True)
sdk=stage/'lib/libexreader.so';exports=tool('llvm-nm','-D','--defined-only',sdk);assert re.search(r'\bexr_render_page_background$',exports,re.M)
owners=list(Path('examples/android/app/build/intermediates/cxx/Debug').rglob('libexreader_host.so'));owner,=owners
undefined=tool('llvm-nm','-D','--undefined-only',owner);needed=tool('llvm-readelf','-d',owner)
assert re.search(r'\bexr_render_page_background$',undefined,re.M) and len(re.findall(r'NEEDED.*\[libexreader.so\]',needed))==1
(out/'installed-sdk-defined.txt').write_text(exports);(out/'host-undefined.txt').write_text(undefined);(out/'host-needed.txt').write_text(needed)
archive=out/'old-public-headers.tar';subprocess.run(['git','archive','--format=tar','--output='+str(archive),'9854061be331fe603a1822d9b2b36ee357154927','include'],check=True)
old=out/'old-headers';old.mkdir(exist_ok=True)
with tarfile.open(archive) as tar:tar.extractall(old,filter='data')
probe=out/'requires-background.c';probe.write_text('#include <exreader.h>\nvoid probe(void){ (void)&exr_render_page_background; }\n')
command=[str(ndk/'x86_64-linux-android26-clang'),'-Werror','-fsyntax-only','-I'+str(old/'include'),str(probe)]
negative=subprocess.run(command,text=True,capture_output=True,check=False);assert negative.returncode!=0 and 'exr_render_page_background' in negative.stderr
(out/'sdk340-rejected.txt').write_text(negative.stdout+negative.stderr)
positive=subprocess.run([str(ndk/'x86_64-linux-android26-clang'),'-Werror','-fsyntax-only','-I'+str(stage/'include'),str(probe)],text=True,capture_output=True,check=False);assert positive.returncode==0
report={**{key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},'accepted':True,'installed_sdk':'3.41.0','shared_sdk_sha256':hashlib.sha256(sdk.read_bytes()).hexdigest(),'host_sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),'sdk340_public_header_rejected':True,'single_shared_sdk_needed':True,'actual_background_import':True}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
