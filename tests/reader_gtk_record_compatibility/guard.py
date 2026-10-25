"""Actions-only explicit immutable old SDK/owner and new candidate source pair."""
import json
import os
from pathlib import Path
import subprocess
from run import BASE, OLD_HOST, OLD_SDK, NEW_SDK

assert os.environ.get('GITHUB_ACTIONS') == 'true'
git = lambda *args: subprocess.check_output(['git', *args], text=True).strip()
source = os.environ['GITHUB_SHA']
assert git('rev-parse', 'HEAD') == source
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], check=True)
protected = ['src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml']
for path in protected:
    assert git('rev-parse', source + ':' + path) == git('rev-parse', NEW_SDK + ':' + path), path
    assert git('rev-parse', OLD_HOST + ':' + path) == git('rev-parse', OLD_SDK + ':' + path), path
for path in ('apps', 'examples', 'extras', 'tests/reader_gtk_reading_records', 'tests/reader_gtk_page_background'):
    assert git('rev-parse', source + ':' + path) == git('rev-parse', BASE + ':' + path), path
allowed = ('tests/reader_gtk_record_compatibility/', '.github/workflows/reader-gtk-record-compatibility.yml',
           'docs/READER-GTK-RECORD-COMPATIBILITY.md', 'docs/validation/reader-gtk-record-compatibility.json')
paths = git('diff', '--name-only', BASE, source).splitlines()
assert all(path.startswith(allowed[0]) or path in allowed[1:] for path in paths)
report = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
              accepted=True, base=BASE, old_host=OLD_HOST, old_sdk=OLD_SDK, new_sdk=NEW_SDK,
              owner_trees={name: git('rev-parse', sha + ':examples/linux') for name, sha in [('old', OLD_HOST), ('new', source)]},
              protected_trees={name: {path: git('rev-parse', sha + ':' + path) for path in protected}
                               for name, sha in [('old', OLD_SDK), ('new', NEW_SDK)]}, paths=paths)
out = Path('build/gtk-record-compatibility-guard.json');out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
