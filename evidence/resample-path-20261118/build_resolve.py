"""Build main and the resolved trial with the same Release configuration."""
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'resolve-256'
OUT.mkdir(exist_ok=True)
BASE = 'acfcdd4f92bff41cc7b67ae0ae5f884962e57e19'
TRIAL = '3e77007f33252961ac5efb181bc61de7fc1420b1'
source = ROOT / 'src/affine_image.c'
candidate = source.read_bytes()
identity = {'main': BASE, 'trial': TRIAL}
try:
    for tag in ('main', 'trial'):
        ref = BASE if tag == 'main' else TRIAL
        source.write_bytes(subprocess.check_output(['git', 'show', f'{ref}:src/affine_image.c']))
        with (OUT / f'build-{tag}.txt').open('w') as log:
            subprocess.run(['cmake', '--build', 'build/perf', '--parallel', '4'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        data = (ROOT / 'build/perf/libexreader.dll').read_bytes()
        (OUT / f'{tag}.dll').write_bytes(data)
        identity[tag + '_dll_sha256'] = hashlib.sha256(data).hexdigest()
        print(tag, identity[tag + '_dll_sha256'], flush=True)
finally:
    source.write_bytes(candidate)
(OUT / 'build-identity.json').write_text(json.dumps(identity, indent=2))
