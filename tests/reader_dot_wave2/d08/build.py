"""Fresh target build; no identity environment substitution or old guards invoked."""
import os,sys,json,subprocess,hashlib,shutil
from pathlib import Path
from contract import TARGET,SDK
ROOT=Path.cwd();SOURCE=ROOT/'target';OUT=ROOT/'build/d08-evidence';BUILD=ROOT/'build/d08-build'
def run(args,label,cwd=SOURCE):
    p=subprocess.run(list(map(str,args)),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace')
    (OUT/'logs'/f'{label}.log').write_text(p.stdout,encoding='utf-8');print(label,p.returncode,flush=True)
    if p.returncode: print(p.stdout[-22000:]);raise RuntimeError(label)
def configure(src,name,opts):
    b=BUILD/name;run(['cmake','-S',src,'-B',b,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',*opts],name+'-configure')
    run(['cmake','--build',b,'--parallel','2','--verbose'],name+'-build');return b
def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'logs').mkdir(exist_ok=True)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==TARGET
    run(['git','diff','--exit-code',SDK,'HEAD','--','src','include','cmake','CMakeLists.txt','bindings','tests/fixtures'],'approved-sdk-source')
    sdk=BUILD/'sdk-stage';stage=BUILD/'stage'
    run(['cmake','--preset','reading-library','-B',BUILD/'sdk','-DCMAKE_INSTALL_PREFIX='+str(sdk)],'sdk-configure')
    run(['cmake','--build',BUILD/'sdk','--parallel','2','--verbose'],'sdk-build');run(['cmake','--install',BUILD/'sdk'],'sdk-install')
    b=configure(SOURCE/'apps/reader/store/native','product',['-DCMAKE_INSTALL_PREFIX='+str(stage)]);run(['cmake','--install',b],'product-install')
    modules=('extras/webdav extras/credentials extras/sideload apps/reader/revisions apps/reader/commands apps/reader/desktop-metadata apps/reader/sync apps/reader/session apps/reader/reading-state apps/reader/reading-commands apps/reader/annotation-view apps/reader/search apps/reader/navigation apps/reader/cloud-import apps/reader/bulk-organization apps/reader/preferences').split()
    common=['-DEXR_SDK_VERSION=3.41.0','-DEXR_SDK='+str(sdk),'-DCMAKE_PREFIX_PATH='+str(stage)+';'+str(sdk),'-DREADER_PRODUCT_PREFIX='+str(stage),'-DCMAKE_INSTALL_PREFIX='+str(stage)]
    for module in modules:
        name=Path(module).name;b=configure(SOURCE/module,name,common+['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=OFF']);run(['cmake','--install',b],name+'-install')
    flags=['-DEXR_READER_WINDOWS_'+x+'=ON' for x in ('SEARCH','NAVIGATION','RECORDS','IMPORT_ORGANIZE','PREFERENCES','COMPACT')]
    b=configure(SOURCE/'apps/reader/windows-account','host',common+flags+['-DREADER_METADATA_PREFIX='+str(stage),'-DREADER_ACCOUNT_PREFIX='+str(stage),'-DEXR_READER_WINDOWS_RAW3=OFF','-DEXR_READER_PREFS_COMMIT_REVIEW_BUILD=OFF'])
    run([sys.executable,'-m','pip','install','uiautomation==2.0.29'],'uia')
    run([sys.executable,'-c',"from tools.host_font import fetch; fetch('build/host-font-cache')"],'font')
    run([sys.executable,SOURCE/'tests/reader_windows_preferences/make_fixtures.py','--output',OUT/'fixtures'],'fixtures')
    programs=OUT/'programs';programs.mkdir();shutil.copy2(b/'EXReaderProduct.exe',programs/'EXReaderProduct.exe');shutil.copy2(SOURCE/'build/host-font-cache/Reader.otf',programs/'Reader.otf')
    for p in BUILD.rglob('*'):
        if p.is_file() and (p.name in ('CMakeCache.txt','build.ninja','compile_commands.json') or p.suffix in ('.map','.dll')):
            dest=OUT/'build-identity'/p.relative_to(BUILD);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    identity={'target_sha':TARGET,'sdk_source':SDK,'harness_sha':os.environ['GITHUB_SHA'],'program_sha256':hashlib.sha256((programs/'EXReaderProduct.exe').read_bytes()).hexdigest(),'sdk_linkage':'installed static library; DLL inventory retained','configuration':'compact ON, raw3 OFF, review OFF','commands':'logs plus all CMakeCache/build.ninja/compile_commands retained'}
    (OUT/'build-identity.json').write_text(json.dumps(identity,indent=2));print(json.dumps(identity))
if __name__=='__main__':main()
