"""Exact historical D08 source reuse, materialized and executed only in Actions.

Only repository/evidence/build roots are adapted. The old methods and judgments
are byte-preserved; the old run_all (with obsolete SPI requests) is never called.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types
from contract import D08
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/d20-evidence'
REUSE = ROOT / 'build/d20-reuse'


def module(name, substitutions=()):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    path = 'tests/reader_dot_wave2/d08/' + name + '.py'
    raw = subprocess.check_output(['git','show',D08 + ':' + path], cwd=ROOT)
    original = raw.decode('utf-8'); adapted = original
    for before, after in substitutions:
        assert adapted.count(before) == 1, ('non-unique projection', name, before)
        adapted = adapted.replace(before, after, 1)
    reversed_source = adapted
    for before, after in reversed(substitutions):
        assert reversed_source.count(after) == 1
        reversed_source = reversed_source.replace(after, before, 1)
    assert reversed_source == original
    REUSE.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    target = REUSE / (name + '.py'); target.write_text(adapted, encoding='utf-8')
    proof = {'historical_source':D08,'historical_path':path,'original_sha256':hashlib.sha256(raw).hexdigest(),
             'adapted_sha256':hashlib.sha256(adapted.encode()).hexdigest(),'substitutions':substitutions,
             'reverse_projection_exact':True,'old_acceptance_reused':False}
    (OUT / ('reuse-' + name + '.json')).write_text(json.dumps(proof, indent=2), encoding='utf-8')
    loaded = types.ModuleType(name); loaded.__file__ = str(target); sys.modules[name] = loaded
    exec(compile(adapted, str(target), 'exec'), loaded.__dict__)
    return loaded


def driver():
    module('prior_driver', [("ROOT=Path(__file__).resolve().parents[3]/'target'", 'ROOT=Path.cwd()')])
    return module('audit', [("OUT=ROOT/'build/d08-evidence'", "OUT=ROOT/'build/d20-evidence'")])


def build():
    old = "ROOT=Path.cwd();SOURCE=ROOT/'target';OUT=ROOT/'build/d08-evidence';BUILD=ROOT/'build/d08-build'"
    new = "ROOT=Path.cwd();SOURCE=ROOT;OUT=ROOT/'build/d20-evidence';BUILD=ROOT/'build/d20-build'"
    module('build', [(old,new)]).main()


if __name__ == '__main__':
    assert sys.argv[1:] == ['build']
    build()
