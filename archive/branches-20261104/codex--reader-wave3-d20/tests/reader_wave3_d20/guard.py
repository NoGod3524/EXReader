"""Independent fixed-seed guard: never invokes or changes historical guards."""
import json
import os
from pathlib import Path
import subprocess
from contract import BASE, SDK


def git(*args):
    return subprocess.check_output(['git',*args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = git('rev-parse','HEAD'); assert source == os.environ['GITHUB_SHA']
    subprocess.run(['git','merge-base','--is-ancestor',BASE,source], check=True)
    changed = git('diff','--name-only',BASE,source).splitlines()
    allowed = ('tests/reader_wave3_d20/','docs/reader-wave3-d20/')
    assert changed and all(p.startswith(allowed) or p in ('.github/workflows/reader-wave3-d20.yml','HANDOFF-RESULT-D20.md') for p in changed), changed
    subprocess.run(['git','diff','--exit-code',SDK,source,'--','src','include','cmake','CMakeLists.txt','CMakePresets.json','bindings','tests/fixtures'], check=True)
    out=Path('build/d20-evidence');out.mkdir(parents=True,exist_ok=True)
    r=dict(source_sha=source,seed=BASE,frozen_sdk=SDK,changed=changed,workflow=os.environ['GITHUB_WORKFLOW_REF'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    (out/'guard.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))


if __name__ == '__main__': main()
