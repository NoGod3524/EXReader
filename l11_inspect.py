from pathlib import Path
import subprocess
for line in subprocess.check_output(['tasklist','/fo','csv'],text=True).splitlines():
    if any(name in line.lower() for name in ['cc1','ninja','cmake','g++','gcc','c++.exe']):
        print(line,flush=True)
import shutil
overlay=Path('build/l11-save/source')
(overlay/'tools').mkdir(exist_ok=True)
for name in ['convert_json.c','convert_json.h']:
    shutil.copy2(Path('tools')/name,overlay/'tools'/name)
p=Path('examples/windows/l11_save_integration.patch')
p.write_text(p.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
raise SystemExit
import shutil
for name, tokens in [('examples/reader.c', ['shell_recent.inc','shell_docedit.inc','shelf_opened','shelf_refresh']), ('examples/windows/shell_docedit_input.inc', ['de_key','de_save'])]:
    lines=Path(name).read_text(encoding='utf-8').splitlines()
    for i,line in enumerate(lines):
        if any(t in line for t in tokens):
            print(name, i+1, '\n'.join(lines[max(0,i-2):i+4]))
root=Path('C:/Users/Oscar/Documents/Codex')
for d in ['EXReader-docedit-20261112','EXReader-e6-20261113','exr-demo-main']:
    p=root/d
    print(d, [str(x) for x in p.glob('*') if x.is_dir()])
for exe in ['gcc','cmake','ninja']:
    print(exe,shutil.which(exe))
