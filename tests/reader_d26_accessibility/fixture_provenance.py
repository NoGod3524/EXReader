"""Actions-only proof that original generators produced real refusal objects."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
assert os.environ.get('GITHUB_ACTIONS') == 'true'
rows = []
for suite, folder, count in [('batch_import', 'd26-retained-batch-inputs', 3),
                             ('drop_import', 'd26-retained-drop-inputs', 1)]:
    script = 'tests/reader_gtk_' + suite + '/make_inputs.py'
    root = Path('build') / folder
    links = {str(p.relative_to(root)): os.readlink(p) for p in root.rglob('*') if p.is_symlink()}
    assert len(links) == count, links
    fifos = [str(p.relative_to(root)) for p in root.rglob('*') if stat.S_ISFIFO(p.lstat().st_mode)]
    assert len(fifos) == 1, fifos
    rows.append(dict(script=script, git_blob=subprocess.check_output(['git','rev-parse','HEAD:'+script],text=True).strip(),
        script_sha256=hashlib.sha256(Path(script).read_bytes()).hexdigest(), directory=str(root),
        symlinks=links, fifos=fifos, verified=True))
r = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
         attempt=os.environ['GITHUB_RUN_ATTEMPT'], generators=rows)
Path('build/d26-fixture-provenance.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r),flush=True)
