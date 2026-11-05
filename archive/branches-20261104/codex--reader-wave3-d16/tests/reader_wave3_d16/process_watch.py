"""Actions-only passive native PID/executable observation while XCTest owns launch."""
import datetime, hashlib, json, os, subprocess, sys, time
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
output = Path(sys.argv[1]); seen=set()
while True:
    result = subprocess.run(['ps','-axo','pid=,ppid=,comm='],text=True,capture_output=True)
    for line in result.stdout.splitlines():
        fields=line.strip().split(None,2)
        if len(fields)!=3 or Path(fields[2]).name!='EXReaderHost': continue
        pid,ppid,command=fields
        if pid in seen: continue
        path=Path(command)
        row=dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=int(pid),ppid=int(ppid),command=command,
            source=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        if not path.is_file():
            native=subprocess.run(['lsof','-a','-p',pid,'-d','txt','-Fn'],text=True,capture_output=True)
            choices=[Path(value[1:]) for value in native.stdout.splitlines() if value.startswith('n') and Path(value[1:]).name=='EXReaderHost']
            if choices: path=choices[0];row['executable_path_from_lsof']=str(path)
        if path.is_file(): row['executable_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        else: row['identity_gap']='native ps path not readable'
        with output.open('a') as out: out.write(json.dumps(row)+'\n');out.flush()
        print('D16_NATIVE_PROCESS '+json.dumps(row),flush=True);seen.add(pid)
    time.sleep(1)
