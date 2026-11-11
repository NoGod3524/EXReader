"""Read-only, commit-pinned checks for the orchestrator review."""
from pathlib import Path
import collections, hashlib, io, json, subprocess, tarfile, sys
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TEMP = Path('C:/tmp/exr-r1-review-20261110')
TEMP.mkdir(exist_ok=True, parents=True)

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def blob(ref, path):
    return git('show', f'{ref}:{path}')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(name, json.dumps(value, ensure_ascii=False)[:1800], flush=True)

def done(number, text):
    with (ROOT/'OUT.txt').open('a', encoding='utf-8') as f:
        f.write(f'\n[R1 #{number}] {text}\n')

def snapshot(ref, paths, name):
    dest = TEMP/name
    dest.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(git('archive', ref, *paths))) as archive:
        archive.extractall(dest, filter='data')
    return dest

def release():
    path = 'tests/check_reading_release.py'
    refs = ['95100501', 'ff3fa0cb', '66bcbe37', '6000a89d', '6cb452da']
    hashes = {r: sha(blob(r, path)) for r in refs}
    patches = {r: git('show', '--format=', r, '--', path).decode() for r in refs[1:3]}
    assert len(set(hashes.values())) == 1, hashes
    rows = json.loads(blob('6000a89d', 'tools/version_literal_exceptions.json'))
    bound = [r for r in rows if r['file'] == path]
    assert bound and all(r['frozen_fixture']['sha256'] == hashes['6000a89d'] for r in bound)
    original = snapshot('6cb452da', ['tools', path], 'release-before')
    p = subprocess.run([sys.executable, path], cwd=original, capture_output=True, text=True)
    (HERE/'02-release-run.txt').write_text(p.stdout+p.stderr, encoding='utf-8')
    save('02-release.json', dict(hashes=hashes, patches=patches, bound_exceptions=len(bound), exit=p.returncode))
    done(2, f'字节还原正确，但执行 exit={p.returncode}；哈希及恢复掉的 closing 改动见 evidence/r1-orchestrator-20261110/02-release.json；原始运行见 02-release-run.txt。')

def cleanup():
    ref = '5d642281'
    parent = git('rev-parse', ref+'^').decode().strip()
    base = git('merge-base', ref, '6000a89d').decode().strip()
    changed = git('diff', '--name-status', base, ref).decode().splitlines()
    deleted = [s.split('\t')[1] for s in changed if s.startswith('D\t')]
    assert len(deleted) == 133 and all(p.startswith('.github/workflows/') for p in deleted)
    original = git('log', '--format=%H', '-2', ref).decode().splitlines()[1]
    # The retained tests must be byte-identical to the common main ancestor.
    assert not git('diff', base, ref, '--', 'tests')
    removed_text = {p: blob(base,p).decode() for p in deleted}
    import re
    targets = sorted(set(m.group(0).rstrip('.,:') for text in removed_text.values()
                         for m in re.finditer(r'tests/[A-Za-z0-9_.\-/]+', text)))
    files = git('ls-tree','-r','--name-only',ref).decode().splitlines()
    remaining = [p for p in files if p.startswith('.github/workflows/')]
    texts = {p: blob(ref,p).decode(errors='replace') for p in remaining}
    consumers = {t: [p for p,text in texts.items() if t in text] for t in targets}
    save('05-cleanup.json', dict(ref=ref, base=base, deleted=len(deleted), tests_byte_identical=True,
         retained_test_targets=consumers, workflow_only_targets=[t for t,ps in consumers.items() if not ps]))
    done(5, '正确：只删除 133 个 workflow，tests 相对共同 main 祖先逐字节无差异；保留脚本及剩余 workflow 引用清单见 05-cleanup.json。部分脚本失去 workflow 入口，仍可手工运行。')
    before = json.loads(blob(base,'tools/version_literal_exceptions.json'))
    after = json.loads(blob(ref,'tools/version_literal_exceptions.json'))
    expected = [r for r in before if r['file'] not in deleted]
    assert after == expected
    missing = sorted({r['file'] for r in after} - set(files))
    assert not missing
    save('06-exceptions.json',dict(before=len(before), after=len(after), removed=len(before)-len(after),
         exact_filter=True, missing_files=missing))
    done(6, '正确：587 -> 552，恰好等于按 133 个已删 workflow 过滤，剩余目标均存在；见 06-exceptions.json。')
    dest = snapshot(ref, ['.github','tools','tests/check_ci_hygiene.py'], 'cleanup')
    p = subprocess.run([sys.executable,'tools/check_ci_hygiene.py'],cwd=dest,capture_output=True,text=True)
    (HERE/'07-hygiene-run.txt').write_text(p.stdout+p.stderr,encoding='utf-8')
    rows = json.loads(blob(ref,'tools/ci_hygiene_baseline.json'))
    meta = json.loads(blob(ref,'tools/ci_hygiene_baseline.meta.json'))
    observed = dict(entries=len(rows), rule_bindings=sum(len(r['patterns']) for r in rows),
         patterns=dict(collections.Counter(k for r in rows for k in r['patterns'])),
         baseline_sha256=sha(blob(ref,'tools/ci_hygiene_baseline.json')),
         checker_sha256=sha(blob(ref,'tools/check_ci_hygiene.py')))
    mismatches={k:dict(expected=v,actual=meta.get(k)) for k,v in observed.items() if meta.get(k)!=v}
    save('07-hygiene.json',dict(ref=ref,exit=p.returncode,observed=observed,meta=meta,mismatches=mismatches))
    done(7, f'检查 exit={p.returncode}，{len(rows)} 条身份；meta 字段差异={mismatches}；见 07-hygiene.json 和原始日志。')

def moves():
    lines=git('diff-tree','--no-commit-id','-r','-M','--name-status','4d14e5eb').decode().splitlines()
    renames=[s.split('\t')[1:] for s in lines if s.startswith('R100\t')]
    dirs=sorted({a.split('/')[1] for a,b in renames if a.startswith('tests/') and b.startswith('evidence/')})
    hits=[]
    for d in dirs:
        p=subprocess.run(['git','-C',str(ROOT),'grep','-n','-I','tests/'+d,'HEAD','--',':(exclude)evidence',':(exclude)archive'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        hits += p.stdout.splitlines()
    save('08-moves.json',dict(ref='4d14e5eb',exact_renames=len(renames),directories=dirs,old_path_hits=hits))

if __name__ == '__main__':
    for name in sys.argv[1:]:
        globals()[name]()
