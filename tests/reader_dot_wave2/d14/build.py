"""Actions-only actual fixed-source compact build; no review injection."""
import os, subprocess, sys, shutil
from pathlib import Path
from contract import TARGETS,SDK,digest,write
assert os.environ.get('GITHUB_ACTIONS')=='true'
platform=sys.argv[1];root=Path('target').resolve();out=Path('evidence').resolve();out.mkdir(exist_ok=True)
def run(*args):subprocess.run(list(map(str,args)),cwd=root,check=True,timeout=1800)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==TARGETS[platform]
run('git','diff','--exit-code',SDK,'HEAD','--','src','include','cmake','CMakeLists.txt')
prefix=root/'build/d14-stage';sdk=root/'build/reading-library/stage'
run('cmake','--preset','reading-library','-B','build/reading-library',f'-DCMAKE_INSTALL_PREFIX={sdk}')
run('cmake','--build','build/reading-library','--parallel','4');run('cmake','--install','build/reading-library')
modules=['apps/reader/store/native','extras/webdav','extras/credentials','extras/sideload','apps/reader/revisions','apps/reader/commands','apps/reader/desktop-metadata','apps/reader/sync','apps/reader/session','apps/reader/reading-state','apps/reader/reading-commands','apps/reader/annotation-view','apps/reader/search','apps/reader/navigation','apps/reader/preferences']
modules+=['apps/reader/cloud-import','apps/reader/bulk-organization'] if platform=='windows' else ['apps/reader/batch-import','extras/desktop-drop']
for module in modules:
    build=root/('build/d14-'+module.replace('/','-'))
    run('cmake','-S',module,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DEXR_SDK_VERSION=3.41.0',f'-DEXR_SDK={sdk}',f'-DREADER_PRODUCT_PREFIX={prefix}',f'-DCMAKE_PREFIX_PATH={prefix};{sdk}',f'-DCMAKE_INSTALL_PREFIX={prefix}')
    run('cmake','--build',build,'--parallel','4');run('cmake','--install',build)
flags=[f'-DEXR_SDK={sdk}','-DEXR_SDK_VERSION=3.41.0',f'-DCMAKE_PREFIX_PATH={prefix};{sdk}',f'-DREADER_METADATA_PREFIX={prefix}',f'-DREADER_ACCOUNT_PREFIX={prefix}']
if platform=='windows':
    source='apps/reader/windows-account';program='EXReaderProduct.exe';target='EXReaderProduct'
    flags += [f'-DEXR_READER_WINDOWS_{name}=ON' for name in ('COMPACT','SEARCH','NAVIGATION','RECORDS','IMPORT_ORGANIZE','PREFERENCES')]
else:
    source='apps/reader/desktop';program='gtk-host/exreader-linux';target='exreader-linux'
    flags += [f'-DEXR_READER_GTK_{name}=ON' for name in ('COMPACT','SEARCH','NAVIGATION','READING_RECORDS','PREFERENCES','ACCOUNT','BATCH_IMPORT','DROP_IMPORT')]
    flags += ['-DEXR_READER_BUILD_GTK=ON','-DEXR_READER_PAGE_BACKGROUND=ON']
    flags += [f'-DREADER_{name}_PREFIX={prefix}' for name in ('PREFERENCES','SEARCH','NAVIGATION','READING_RECORDS','BATCH_IMPORT','DESKTOP_DROP')]
run('cmake','-S',source,'-B','build/d14-host','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',*flags)
run('cmake','--build','build/d14-host','--target',target,'--parallel','4','--verbose')
shutil.copy2(root/'build/d14-host'/program,out/Path(program).name)
shutil.copy2(root/'build/d14-host/CMakeCache.txt',out/'CMakeCache.txt')
sys.path.insert(0,str(root/'tools'));from host_font import fetch
font=fetch(str(root/'build/d14-font'))
shutil.copy2(root/'build/d14-font/Reader.otf',out/'Reader.otf')
# Shared four-format fixtures generated only on Actions, identically on each platform.
(out/'fixtures').mkdir()
import importlib.util
spec=importlib.util.spec_from_file_location('fixture_maker',root/'tests/reader_windows_preferences/make_fixtures.py');maker=importlib.util.module_from_spec(spec);spec.loader.exec_module(maker)
maker.epub(out/'fixtures/D14 EPUB.epub','D14 EPUB','<p>D14 independently authored lifecycle reading paragraph.</p>'*300)
run(sys.executable,'tests/linux_host/generate_fixed.py',out/'fixtures/fixed')
shutil.copyfile(out/'fixtures/fixed/Pages.pdf',out/'fixtures/Fixed.pdf')
shutil.copyfile(out/'fixtures/fixed/Pages.cbz',out/'fixtures/Comic.cbz')
(out/'fixtures/Reading.txt').write_text('D14 bounded native reading, cancellation, and durable progress.\n\n'*160,encoding='utf-8')
(out/'fixtures/Processing.txt').write_text('D14 real chapter scanning without any review gates.\n'*180000,encoding='utf-8')
write(out/'build-identity.json',dict(platform=platform,target=TARGETS[platform],harness=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],sdk_source=SDK,program=Path(program).name,program_sha256=digest(out/Path(program).name),font_sha256=digest(out/'Reader.otf')))
