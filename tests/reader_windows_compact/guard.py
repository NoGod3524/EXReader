"""Actions-only candidate boundary; original default-OFF source and jobs stay exact."""
import os
from pathlib import Path
import re
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[2]
BASE='25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
WORKFLOW='.github/workflows/reader-windows-compact.yml'
OLD_WORKFLOW='.github/workflows/reader-windows-341-common.yml'
git=lambda *args:subprocess.check_output(['git',*args],text=True,encoding='utf-8').replace('\r\n','\n')


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    source=os.environ['GITHUB_SHA'];assert git('rev-parse','HEAD').strip()==source
    subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
    allowed={'examples/reader.c','apps/reader/windows-account/CMakeLists.txt',
             'apps/reader/desktop/windows_compact_ui.inc',WORKFLOW,'docs/READER-WINDOWS-COMPACT.md',
             'docs/validation/reader-windows-compact.json'}
    changed=git('diff','--name-only',BASE,source).splitlines()
    assert all(path in allowed or path.startswith('tests/reader_windows_compact/') for path in changed),changed
    for path in ('src','include','cmake','CMakeLists.txt','bindings','tests/fixtures','licenses','apps/reader/store/001_catalog.sql'):
        assert git('rev-parse',BASE+':'+path)==git('rev-parse',source+':'+path),path
    reader=(ROOT/'examples/reader.c').read_text(encoding='utf-8')
    stripped,count=re.subn(r'^#ifdef EXR_READER_WINDOWS_COMPACT\n.*?^#endif\n','',reader,flags=re.M|re.S)
    assert count>=7 and stripped==git('show',BASE+':examples/reader.c'),'default-OFF host changed'
    cmake=(ROOT/'apps/reader/windows-account/CMakeLists.txt').read_text(encoding='utf-8')
    option='option(EXR_READER_WINDOWS_COMPACT "Enable the independent compact native library/reading interface" OFF)\n'
    block='  if(EXR_READER_WINDOWS_COMPACT)\n    target_compile_definitions(${target} PRIVATE EXR_READER_WINDOWS_COMPACT=1)\n  endif()\n'
    assert cmake.count(option)==cmake.count(block)==1
    assert cmake.replace(option,'').replace(block,'')==git('show',BASE+':apps/reader/windows-account/CMakeLists.txt')
    ui=(ROOT/'apps/reader/desktop/windows_compact_ui.inc').read_text(encoding='utf-8')
    assert not re.search(r'\b(?:exr_[a-z_]+|reader_(?:rc|rs|revision|command)_[a-z_]+)\s*\(',ui),'UI calls SDK or product storage directly'
    old=yaml.load(git('show',BASE+':'+OLD_WORKFLOW),Loader=yaml.BaseLoader)
    new=yaml.load((ROOT/WORKFLOW).read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    assert set(old['jobs'])==set(new['jobs'])
    added='Build the independent compact candidate against the same installed providers'
    for name,before in old['jobs'].items():
        after=new['jobs'][name]
        assert {k:v for k,v in before.items() if k!='steps'}=={k:v for k,v in after.items() if k!='steps'}
        steps=[step for step in after['steps'] if step.get('name')!=added]
        assert len(steps)==len(before['steps'])
        for left,right in zip(before['steps'],steps):
            expected=dict(left)
            if left.get('run')=='python3 tests/reader_windows_341/guard.py':
                expected['run']='python3 -m pip install PyYAML==6.0.3\npython3 tests/reader_windows_compact/guard.py\n'
            if left.get('name')=='Parse common wrappers and original strict refusal protocols in Actions':
                expected['run']+='python3 -m py_compile tests/reader_windows_compact/*.py\npython3 tests/reader_windows_compact/verify.py --self-test\n'
            if left.get('run')=='python3 tests/reader_windows_341/verify.py':expected['run']='python3 tests/reader_windows_compact/verify.py'
            if left.get('id')=='upload':
                expected['with']=dict(left['with']);expected['with']['path']=expected['with']['path'].replace(
                    'build/windows-341-guard/\n','build/windows-341-guard/\nbuild/compact-ui/\nbuild/compact-host/EXReaderProduct.exe\nbuild/compact-host/windows-host.map\nbuild/compact-host/CMakeCache.txt\n')
            if left.get('name')=='Preserve strict summary including rejections':
                expected['with']=dict(left['with']);expected['with']['path']+='build/compact-summary/result.json\n'
            assert right==expected,(name,left.get('name'))
    assert sum(step.get('name')==added for job in new['jobs'].values() for step in job['steps'])==1
    print('Exact original OFF source and all retained jobs authenticated; independent compact candidate only')


if __name__=='__main__':main()
