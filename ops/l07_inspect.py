from pathlib import Path
import subprocess
print(subprocess.check_output(['tasklist'], text=True)[-3000:])
for p in Path('build/l07-a11y/CMakeFiles').glob('*.yaml'):
    print(p, p.read_text(encoding='utf-8')[-2000:])
