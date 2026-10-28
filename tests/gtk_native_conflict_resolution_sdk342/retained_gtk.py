"""Run byte-identical retained suites with bounded native action completion."""
import hashlib,json,os,runpy,sys
from pathlib import Path
from scan_barrier import install
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session
assert os.environ.get('GITHUB_ACTIONS')=='true'
install(Session)
record={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'barrier_sha256':hashlib.sha256((Path(__file__).parent/'scan_barrier.py').read_bytes()).hexdigest(),'accepted_chooser_sha256':hashlib.sha256((ROOT/'tests/windows_gtk_conflict_recovery/retained_gtk.py').read_bytes()).hexdigest(),'delta':'Actual Scan start/refusal observation barrier, maximum 30 seconds including original key; direct preparation-cancel input and every old assertion unchanged'}
print('GTK_NATIVE_SCAN_BARRIER_IDENTITY '+json.dumps(record),flush=True)
try:runpy.run_path(str(ROOT/'tests/windows_gtk_conflict_recovery/retained_gtk.py'),run_name='__main__')
finally:
    if '--output' in sys.argv:
        out=Path(sys.argv[sys.argv.index('--output')+1]);out.mkdir(parents=True,exist_ok=True)
        (out/'scan-barrier-identity.json').write_text(json.dumps(record,indent=2))
