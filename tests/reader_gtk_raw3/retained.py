"""Unchanged legacy collectors with fixed workflow/pin and explicit new jobs."""
import importlib.util
import os
from pathlib import Path
import sys
from guard import PRODUCTION,WORKFLOW,BASE,ON_STEP

ROOT=Path(__file__).resolve().parents[2]
RAW_JOB='Actual GTK raw3 installed families native owner and authenticated Mac packet'
FINAL_JOB='Authenticate GTK raw3 host packet and complete retained compact OFF scopes'


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    sys.path.insert(0,str(ROOT/'tests/reader_gtk_341_final'))
    import navigation_contract
    navigation_contract.MERGED=PRODUCTION
    if '--off' in sys.argv:
        path=ROOT/'tests/reader_gtk_341_final/aggregate.py';text=path.read_text();literal="'.github/workflows/reader-gtk-341-final.yml'";assert text.count(literal)==1
        module=type(sys)('raw3_retained_complete_off');module.__file__=str(path)
        exec(compile(text.replace(literal,repr(WORKFLOW)),str(path),'exec'),module.__dict__);module.main();return
    path=ROOT/'tests/reader_gtk_compact/aggregate.py'
    spec=importlib.util.spec_from_file_location('raw3_retained_compact',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    actual_pages=module.pages
    def scope_pages(endpoint,key):
        rows=actual_pages(endpoint,key)
        if key=='jobs':
            expected={'preflight',module.HOST,module.OLD_STRICT,module.DIAGNOSTIC,module.SUMMARY,RAW_JOB}
            actual={r['name'] for r in rows}
            # The final job depends on this collector and may not exist yet.
            # Its own collector subsequently requires all seven actual jobs.
            module.require(len(rows)==len(actual) and actual in (expected,expected|{FINAL_JOB}),'retained-scope topology differs')
            return [r for r in rows if r['name'] not in (RAW_JOB,FINAL_JOB)]
        return rows
    module.pages=scope_pages;module.main()


if __name__=='__main__':main()
