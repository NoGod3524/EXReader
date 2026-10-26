"""D18 scoped acceptance; every behavioral value originates in this Actions attempt."""
import hashlib, json, os, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/d18'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK_SOURCE = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
ACTIONS = ('back','resume','import','cancel','next','previous','search','directory','records','settings','close.search','close.directory','close.records','close.settings','disabled_noop','continue_after_return','no_unexpected_revision')
REJECTS = ('cancel', 'reject.badfile', 'disabled_noop')
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'))
def hashed(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def identity():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    sha = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    assert sha == os.environ['GITHUB_SHA']
    return dict(source_sha=sha, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])
def write(path, data):
    path=pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
def unchanged(before, after):
    return before['semantic'] == after['semantic']
