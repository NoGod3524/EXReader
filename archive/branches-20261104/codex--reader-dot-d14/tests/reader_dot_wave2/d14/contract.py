"""D14 closed-world bounded lifecycle contract. No performance grant."""
import copy
import hashlib
import json
from pathlib import Path
TARGETS={'windows':'9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08','gtk':'803098e9df1a365a9b8e206805c2d179aca8501f'}
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
FORMATS=('txt','epub','pdf','cbz')
ROUNDS=3
DWELL_SECONDS=30
ACTIONS=('open','forward','backward','library','resume','search','directory','records','settings','import_cancel')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
def expected():
    rows=[]
    for s in (1,2):
        if s==2:rows.append('2/no_replay')
        rows.extend(f'{s}/{r}/{k}/{a}' for r in range(ROUNDS) for k in FORMATS for a in ACTIONS)
        rows.append('1/close_processing' if s==1 else '2/final_close')
    return rows+['originals_unchanged']
def validate(v,identity):
    assert all(v[k]==identity[k] for k in ('platform','harness','run','attempt','target','program_sha256')),'identity mismatch'
    assert v['target']==TARGETS[v['platform']] and v['sdk_source']==SDK
    assert v['plan']==dict(stages=2,rounds=ROUNDS,formats=list(FORMATS),actions=list(ACTIONS),ceiling_seconds=2700,dwell_seconds_per_cycle=DWELL_SECONDS)
    assert not v['failures'] and not v['sampler_errors'],'failures retained'
    assert 2*ROUNDS*4*DWELL_SECONDS<=v['duration_seconds']<=2700
    rows=v['actions'];assert [r['id'] for r in rows]==expected(),'missing/reordered action'
    assert all(r['status']=='completed' and r['after'] is not None for r in rows),'noncompleted action'
    assert v['completed_cycles']==2*ROUNDS*4,'fabricated completed count'
    stages=v['stages'];assert [s['stage'] for s in stages]==[1,2] and len({s['pid'] for s in stages})==2,'missing/duplicate process stage'
    for s in stages:
        assert s['exit_code']==0 and s['completed_cycles']==ROUNDS*4
        assert s['program_sha256']==identity['program_sha256'],'actual process program mismatch'
        dwells=s['dwells'];assert len(dwells)==ROUNDS*4 and all(d['status']=='completed' and d['elapsed_seconds']>=DWELL_SECONDS for d in dwells),'sustained dwell incomplete'
        assert [d['cycle'] for d in dwells]==[f'{s["stage"]}/{r}/{k}' for r in range(ROUNDS) for k in FORMATS]
        for d in dwells:
            assert d['finished_seconds']-d['started_seconds']>=DWELL_SECONDS
            assert len([r for r in v['resources'] if r['stage']==s['stage'] and d['started_seconds']<=r['monotonic_seconds']<=d['finished_seconds']])>=2,'dwell resource coverage missing'
        samples=[r for r in v['resources'] if r['stage']==s['stage']]
        assert len(samples)>=2 and all(r['pid']==s['pid'] and r['create_time']==s['create_time'] for r in samples),'resource/PID mismatch'
        assert all(all(type(r[k]) in (int,float) and r[k]>=0 for k in ('rss_bytes','cpu_user_seconds','cpu_system_seconds','threads','handles' if v['platform']=='windows' else 'fds')) for r in samples)
        if v['platform']=='windows':assert all(type(r['gdi']) is int and r['gdi']>=0 for r in samples)
        assert all(r['pid']==s['pid'] for r in rows if r.get('stage')==s['stage'])
    assert all(not v[k] for k in ('performance_accepted','physical_device_accepted','screenreader_accepted','leak_free_claim'))
    return True

def selftest():
    identity=dict(platform='gtk',harness='h'*40,run='1',attempt='1',target=TARGETS['gtk'],program_sha256='a'*64)
    v=dict(identity,sdk_source=SDK,plan=dict(stages=2,rounds=ROUNDS,formats=list(FORMATS),actions=list(ACTIONS),ceiling_seconds=2700,dwell_seconds_per_cycle=DWELL_SECONDS),failures=[],sampler_errors=[],duration_seconds=740,completed_cycles=24,performance_accepted=False,physical_device_accepted=False,screenreader_accepted=False,leak_free_claim=False)
    v['stages']=[dict(stage=s,pid=s,create_time=s,exit_code=0,completed_cycles=12,program_sha256=identity['program_sha256'],dwells=[dict(cycle=f'{s}/{r}/{k}',status='completed',elapsed_seconds=DWELL_SECONDS,started_seconds=(s-1)*360+(r*4+i)*30,finished_seconds=(s-1)*360+(r*4+i+1)*30) for r in range(ROUNDS) for i,k in enumerate(FORMATS)]) for s in (1,2)]
    v['resources']=[dict(stage=s,pid=s,create_time=s,rss_bytes=1,cpu_user_seconds=0,cpu_system_seconds=0,threads=1,fds=1,monotonic_seconds=(s-1)*360+i*30+t) for s in (1,2) for i in range(12) for t in (1,29)]
    v['actions']=[dict(id=i,status='completed',after={},stage=int(i[0]) if i[0].isdigit() else None,pid=int(i[0]) if i[0].isdigit() else None) for i in expected()]
    validate(v,identity)
    mutations={'missing_dwell':lambda x:x['stages'][0]['dwells'].pop(),'missing_stage':lambda x:x['stages'].pop(),'fake_completed_count':lambda x:x.update(completed_cycles=25),'pid_mismatch':lambda x:x['resources'][0].update(pid=99),'lost_failure':lambda x:x['actions'][0].update(status='failed'),'missing_resources':lambda x:x.update(resources=[]),'artifact_mismatch':lambda x:x.update(program_sha256='b'*64)}
    for name,change in mutations.items():
        broken=copy.deepcopy(v);change(broken)
        try:validate(broken,identity)
        except (AssertionError,KeyError):print('REJECTED '+name)
        else:raise AssertionError('negative accepted: '+name)
if __name__=='__main__':selftest()
