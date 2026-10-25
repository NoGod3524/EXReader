"""Actions-only compact UI inputs; reuse the original fixed/page EPUB makers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    target=Path(sys.argv[1]);target.mkdir(parents=True,exist_ok=False)
    text=target/'Compact reading.txt'
    text.write_text(('Compact selection target. Native reading, bookmarks and library. 中文阅读。\n\n'*50),encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'tests/reader_gtk_page_background/make_inputs.py'),str(target/'epub')],check=True)
    subprocess.run([sys.executable,str(ROOT/'tests/linux_host/generate_fixed.py'),str(target/'fixed')],check=True)
    paths={'txt':text,'epub':target/'epub/Authored white and original image.epub','pdf':target/'fixed/Pages.pdf','cbz':target/'fixed/Pages.cbz'}
    rows={kind:dict(path=path.relative_to(target).as_posix(),bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fixed=kind in ('pdf','cbz'),min_units=2) for kind,path in paths.items()}
    rows['epub']['parts']=2;rows['pdf']['pages']=rows['cbz']['pages']=3
    (target/'manifest.json').write_text(json.dumps(rows,indent=2)+'\n')


if __name__=='__main__':main()
