"""Synchronize a native Scan action with its real post-start GTK observation.
The TLS worker may signal a request before GTK serializes session_generation.
No observations, assertions, commands, product bytes or timeouts are replaced.
Preparation-cancel tests use direct xdotool input and remain unaffected.
"""
import configparser,hashlib,json,os,time
from pathlib import Path

def install(Session):
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    original=Session.key
    def account(host):
        c=configparser.ConfigParser(interpolation=None);c.read(host.observe)
        return dict(c['account']) if c.has_section('account') else {}
    def key(host,*keys):
        for value in keys:
            before=account(host) if value=='alt+s' else {}
            # A preexisting refusal is not evidence of this Scan; leave that
            # old negative-test path unchanged instead of accepting stale state.
            watched=before.get('visible')=='1' and before.get('stage_status')=='0'
            started=time.monotonic();original(host,value)
            if not watched:continue
            deadline=started+30;prior_generation=int(before['session_generation'])
            while time.monotonic()<deadline:
                assert host.process.poll() is None,'GTK exited during native Scan action'
                after=account(host)
                ready=after.get('owner_busy')=='0' and after.get('preparing')=='0'
                observed_start=int(after.get('session_generation','0'))>prior_generation
                observed_refusal=after.get('stage_status','0')!='0'
                if ready and (observed_start or observed_refusal):
                    event={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'pid':host.process.pid,'before':before,'after':after,'elapsed':time.monotonic()-started,'budget_seconds':30,'real_native_start':observed_start,'real_native_refusal':observed_refusal,'program_sha256':hashlib.sha256(host.binary.read_bytes()).hexdigest()}
                    with (host.folder/'native-scan-barrier.jsonl').open('a') as output:output.write(json.dumps(event)+'\n')
                    break
                time.sleep(.01)
            else:raise TimeoutError('Native Scan did not publish its real start/refusal within 30 seconds')
    Session.key=key
    return original
