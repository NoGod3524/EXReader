"""Execute the unchanged full OFF judges at one explicitly pinned candidate."""
from pathlib import Path
import sys
from guard import PRODUCTION,WORKFLOW

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_gtk_341_final'))
import navigation_contract
navigation_contract.MERGED=PRODUCTION
path=ROOT/'tests/reader_gtk_341_final/aggregate.py'
source=path.read_text(encoding='utf-8')
old="'.github/workflows/reader-gtk-341-final.yml'"
assert source.count(old)==1
value=type(sys)('original_complete_off_judge');value.__file__=str(path)
exec(compile(source.replace(old,repr(WORKFLOW)),str(path),'exec'),value.__dict__)
value.main()
