#!/usr/bin/env python3
"""Actions-only process driver; stdout and exit codes are retained verbatim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('GitHub Actions only')
p = argparse.ArgumentParser()
p.add_argument('--platform', choices=['linux','windows'], required=True)
p.add_argument('--binary', required=True)
p.add_argument('--output', required=True)
p.add_argument('--mode', choices=['native','real','termination','real_termination'], required=True)
a = p.parse_args()
root = Path(a.output); root.mkdir(parents=True, exist_ok=True)
exe = str(Path(a.binary).resolve())
def record(name, result, detail):
    return {'case':name, 'result':result, 'detail':detail, 'module':os.environ['GITHUB_SHA']}
if a.mode == 'real_termination':
    import dbus
    import concurrent.futures
    session = dbus.SessionBus()
    try:
        manager = dbus.Interface(session.get_object('org.gnome.SessionManager','/org/gnome/SessionManager'), 'org.gnome.SessionManager')
        baseline = set(map(str, manager.GetInhibitors()))
    except dbus.exceptions.DBusException:
        records = [record('real_service_process_cleanup','UNAVAILABLE','No actual GNOME session manager; deterministic fixture cannot substitute')]
    else:
        child = subprocess.Popen([exe,'--child'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                future=pool.submit(child.stdout.readline)
                try: ready=future.result(timeout=15)
                except concurrent.futures.TimeoutError:
                    child.kill(); ready=future.result(timeout=5)
            observed=set(map(str,manager.GetInhibitors()))
            added=observed-baseline
            idle_only=False
            if len(added)==1:
                inhibitor=dbus.Interface(session.get_object('org.gnome.SessionManager',next(iter(added))),'org.gnome.SessionManager.Inhibitor')
                idle_only=int(inhibitor.GetFlags())==8 and str(inhibitor.GetAppId())=='org.exreader.DesktopDisplay'
            child.kill(); code=child.wait(timeout=10)
            after=observed
            stop=time.monotonic()+5
            while time.monotonic()<stop:
                after=set(map(str,manager.GetInhibitors()))
                if not (after & added): break
                time.sleep(.05)
            passed=ready.startswith(b'READY ') and int(ready.split()[1])>0 and code!=0 and idle_only and len(added)==1 and not (after & added) and baseline<=after
            records=[record('real_service_process_cleanup','PASS' if passed else 'FAIL',f'actual GNOME session; pid={child.pid}; {ready.decode().strip()}; added={sorted(added)}; remaining={sorted(after)}; idle_only={idle_only}; exit={code}')]
            (root/'real-child.stderr').write_bytes(child.stderr.read())
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=5)
    (root/'real_termination.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in records))
    code=0 if all(x['result']!='FAIL' for x in records) else 1
    (root/'real_termination.exit').write_text(str(code))
    print((root/'real_termination.jsonl').read_text())
    sys.exit(code)
if a.mode != 'termination':
    command = [exe] + (['--real'] if a.mode == 'real' else [])
    r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    (root / f'{a.mode}.jsonl').write_bytes(r.stdout)
    (root / f'{a.mode}.stderr').write_bytes(r.stderr)
    (root / f'{a.mode}.exit').write_text(str(r.returncode))
    print(r.stdout.decode(errors='replace'), end='')
    sys.exit(r.returncode)

# Keep stdin/stdout identities, actual signal/exit code and native service count.
child = subprocess.Popen([exe, '--child'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    # A separate reader thread bounds a child that dies before READY or hangs.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        future = pool.submit(child.stdout.readline)
        try: ready = future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            child.kill(); ready = future.result(timeout=5)
    (root / 'child-ready.txt').write_bytes(ready)
    ok = ready.startswith(b'READY ') and int(ready.split()[1]) > 0 and child.poll() is None
    before = after = None
    if a.platform == 'linux':
        import dbus
        iface = dbus.Interface(dbus.SessionBus().get_object('org.exreader.DisplayFixture','/org/gnome/SessionManager'), 'org.exreader.DisplayFixture')
        before = int(iface.Count())
    else:
        before_cmd = subprocess.run(['powercfg','/requests'], capture_output=True)
        (root / 'powercfg-before.txt').write_bytes(before_cmd.stdout+before_cmd.stderr)
        before = 'EXReader display-only acceptance' in before_cmd.stdout.decode(errors='replace')
    child.kill(); code = child.wait(timeout=10)
    stderr = child.stderr.read(); (root / 'child.stderr').write_bytes(stderr)
    if a.platform == 'linux':
        stop = time.monotonic()+5
        while time.monotonic()<stop:
            after = int(iface.Count())
            if after == 0: break
            time.sleep(.05)
        cleanup = before == 1 and after == 0
        detail = f'fixture sender cleanup before={before} after={after}; not real-service capability'
        cleanup_result = 'PASS' if cleanup else 'FAIL'
    else:
        time.sleep(.3)
        after_cmd = subprocess.run(['powercfg','/requests'], capture_output=True)
        (root / 'powercfg-after.txt').write_bytes(after_cmd.stdout+after_cmd.stderr)
        after = 'EXReader display-only acceptance' in after_cmd.stdout.decode(errors='replace')
        cleanup_result = ('PASS' if not after else 'FAIL') if before else 'UNAVAILABLE'
        detail = 'powercfg request disappearance' if before else 'powercfg did not expose child request; kernel termination alone not physical evidence'
    records = [record('real_process_termination','PASS' if ok and code != 0 else 'FAIL',f'pid={child.pid}; native_ready={ready.decode().strip()}; returncode={code}'), record('process_native_cleanup',cleanup_result,detail)]
    (root/'termination.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in records))
    (root/'termination.exit').write_text('0' if all(x['result']!='FAIL' for x in records) else '1')
    print((root/'termination.jsonl').read_text())
    sys.exit(0 if all(x['result']!='FAIL' for x in records) else 1)
finally:
    if child.poll() is None: child.kill(); child.wait(timeout=5)
