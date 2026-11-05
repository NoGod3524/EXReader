"""Synthetic refusal protocol for the gate logic. It grants nothing: real evidence is collected only from live runs."""
import copy
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

import final_gate as gate

NOW=datetime(2026,10,26,tzinfo=timezone.utc)
SOURCE='1'*40


class Fake:
    def __init__(self):
        blob=io.BytesIO()
        image=bytearray(128);image[:2]=b'MZ';image[60:64]=(64).to_bytes(4,'little');image[64:68]=b'PE\0\0';image[86:88]=(2).to_bytes(2,'little')
        with zipfile.ZipFile(blob,'w') as archive:
            archive.writestr('bin/reader.exe',image)
            archive.writestr('bin/static.a',b'!<arch>\n')
            archive.writestr('report.json',json.dumps({'source_sha':SOURCE,'run_id':11,'attempt':1,'accepted':True}))
        self.data=blob.getvalue();self.sha=hashlib.sha256(self.data).hexdigest()
        self.program=hashlib.sha256(image).hexdigest()
        self.run_row=dict(id=11,head_sha=SOURCE,path='.github/workflows/x.yml@refs/heads/b',status='completed',conclusion='success',run_attempt=1)
        self.job_rows=[dict(id=i,name=name,head_sha=SOURCE,run_id=11,run_attempt=1,status='completed',conclusion='success',
                            started_at='2026-10-25T10:00:00Z',completed_at='2026-10-25T10:10:00Z',steps=[]) for i,name in ((1,'build'),(2,'summary'))]
        self.artifact_rows=[dict(id=101,name='x-11-1',expired=False,expires_at='2027-01-01T00:00:00Z',workflow_run=dict(id=11,head_sha=SOURCE),
                                 digest='sha256:'+self.sha,size_in_bytes=len(self.data),created_at='2026-10-25T10:05:00Z')]

    def run(self,run_id):return self.run_row

    def jobs(self,run_id,attempt):return self.job_rows

    def artifacts(self,run_id):return self.artifact_rows

    def zip(self,artifact_id,folder):
        path=Path(folder)/('%d.zip'%artifact_id);path.write_bytes(self.data);return path

    def entry(self,**changes):
        value=dict(scope='host',platform='windows',policy_id='synthetic-windows',kind='native_host',run_id=11,attempt=1,workflow='.github/workflows/x.yml',source_sha=SOURCE,
                   jobs=['build','summary'],artifacts=[dict(id=101,name='x-11-1',sha256=self.sha,bytes=len(self.data),
                   programs={'bin/reader.exe':self.program},
                   reports=[dict(member='report.json',equals={'source_sha':'$source','run_id':'$run','attempt':'$attempt'})])])
        value.update(changes);return value


def must_refuse(label,call):
    try:call()
    except gate.GateError:return
    raise AssertionError('accepted: '+label)


def run_tests():
    gate.APPROVED_POLICIES={'synthetic-windows':dict(scope='host',cell='windows',workflow='.github/workflows/x.yml',report='report.json',
        identity=dict(source='source_sha',run='run_id',attempt='attempt'),requirements=dict(accepted=True),programs=['bin/reader.exe'])}
    with tempfile.TemporaryDirectory() as folder:
        def auth(entry,api=None,now=NOW):return gate.authenticate(entry,api or Fake(),now,folder)
        good=auth(Fake().entry())
        assert good['programs_verified'] and gate.classify(Fake().entry(),good,SOURCE)==('counts','')
        assert gate.classify(Fake().entry(),good,None)[0]=='authentic_not_counted'
        assert gate.classify(Fake().entry(),good,'2'*40)[0]=='refused'
        assert gate.classify(Fake().entry(),dict(programs_verified=False),SOURCE)[0]!='counts'
        static=Fake().entry();static['artifacts'][0]['programs']={'bin/static.a':hashlib.sha256(b'!<arch>\n').hexdigest()}
        static_auth=auth(static)
        assert static_auth['programs_verified'] is False and gate.classify(static,static_auth,SOURCE)[0]!='counts'
        missing=Fake().entry();missing['artifacts'][0]['reports']=[]
        assert gate.classify(missing,auth(missing),SOURCE)[0]=='refused'
        assert gate.classify(Fake().entry(policy_id='unapproved'),good,SOURCE)[0]!='counts'
        need_result=copy.deepcopy(good);need_result['artifacts'][0]['reports'][0]['document']['accepted']=False
        assert gate.classify(Fake().entry(),need_result,SOURCE)[0]=='refused'
        fake=Fake();fake.entry()
        must_refuse('declared source differs',lambda:auth(fake.entry(source_sha='2'*40)))
        api=Fake();api.run_row['head_sha']='2'*40
        must_refuse('run source differs',lambda:auth(api.entry(),api))
        must_refuse('attempt does not exist',lambda:auth(Fake().entry(attempt=2)))
        api=Fake();api.job_rows[1]['run_attempt']=2
        must_refuse('mixed-attempt job',lambda:auth(api.entry(),api))
        api=Fake();api.artifact_rows[0]['created_at']='2026-10-26T10:05:00Z'
        must_refuse('artifact outside attempt window',lambda:auth(api.entry(),api))
        must_refuse('missing job',lambda:auth(Fake().entry(jobs=['build','summary','device'])))
        api=Fake();api.job_rows[0]['conclusion']='failure'
        must_refuse('failed job',lambda:auth(api.entry(),api))
        api=Fake();api.run_row['conclusion']='failure'
        must_refuse('failed run',lambda:auth(api.entry(),api))
        api=Fake();api.artifact_rows[0]['expired']=True
        must_refuse('expired flag',lambda:auth(api.entry(),api))
        must_refuse('expired by time',lambda:auth(Fake().entry(),None,datetime(2028,1,1,tzinfo=timezone.utc)))
        api=Fake();api.artifact_rows[0]['digest']='sha256:'+'0'*64
        must_refuse('API digest differs',lambda:auth(api.entry(),api))
        api=Fake();entry=api.entry();entry['artifacts'][0]['sha256']='0'*64
        must_refuse('declared digest differs',lambda:auth(entry,api))
        api=Fake();api.data=api.data+b'tamper'
        must_refuse('downloaded bytes differ',lambda:auth(api.entry(),api))
        api=Fake();entry=api.entry();entry['artifacts'][0]['programs']['bin/reader.exe']='0'*64
        must_refuse('program hash wrong',lambda:auth(entry,api))
        api=Fake();entry=api.entry();entry['artifacts'][0]['programs']={'bin/other.exe':api.program}
        must_refuse('program member absent',lambda:auth(entry,api))
        api=Fake();entry=api.entry();entry['artifacts'][0]['reports'][0]['equals']['attempt']=2
        must_refuse('report identity differs',lambda:auth(entry,api))
        entry=Fake().entry();entry['artifacts'].append(copy.deepcopy(entry['artifacts'][0]))
        must_refuse('duplicate artifact',lambda:auth(entry))
    ok=dict(programs_verified=True)
    assert gate.classify(Fake().entry(scope='physical_device',platform='android',kind='emulator'),ok,SOURCE)[0]=='refused'
    assert gate.classify(Fake().entry(scope='physical_device',platform='android',kind='physical_device'),ok,SOURCE)[0]!='counts'
    assert gate.classify(Fake().entry(scope='performance',budget=dict(approved=False,sha256='0'*64)),ok,SOURCE)[0]=='refused'
    assert gate.classify(Fake().entry(scope='performance',budget=dict(approved=True,sha256='0'*64)),ok,SOURCE)[0]!='counts'
    assert gate.classify(Fake().entry(scope='sdk',platform='sdk'),ok,SOURCE)[0]=='refused'
    assert gate.classify(Fake().entry(scope='sdk',platform='sdk',sdk_source=gate.SDK_341,frozen_sdk_source=gate.SDK_340),ok,SOURCE)[0]!='counts'
    assert gate.classify(Fake().entry(scope='nowhere'),ok,SOURCE)[0]=='refused'
    row=lambda scope,key,value:(dict(scope=scope,**{gate.SCOPES[scope]['key']:value}),'counts','')
    full=[row(name,spec['key'],value) for name,spec in gate.SCOPES.items() for value in spec['values']]
    assert all(item['status']=='verified' for item in gate.evaluate(full).values())
    assert gate.evaluate([r for r in full if r[0].get('direction')!='apple_to_android'])['bidirectional']['status']=='pending'
    assert gate.evaluate([r for r in full if r[0].get('platform')!='ipad' or r[0]['scope']!='physical_device'])['physical_device']['status']=='pending'
    assert gate.evaluate([r for r in full if r[0].get('platform')!='iphone'])['host']['status']=='pending'
    assert gate.evaluate([r for r in full if r[0].get('platform')!='ipad'])['host']['status']=='pending'
    assert gate.evaluate([r for r in full if r[0]['scope']!='packaging'])['packaging']['missing']
    with tempfile.TemporaryDirectory() as folder:
        table=dict(schema=1,product_source=None,entries=[Fake().entry()],negative_controls=[Fake().entry(source_sha='2'*40)])
        result=gate.collect(table,Fake(),NOW,folder,True)
        assert result['gate_accepted'] and result['complete_product'] is False and result['scopes']['host']['status']=='pending',result
        assert result['entries'][0]['status']=='authentic_not_counted' and all(row['refused'] for row in result['derived_controls'])
        assert len(result['derived_controls'])==9 and result['negative_controls'][0]['refused']
        bad=gate.collect(dict(schema=1,product_source=None,entries=[],negative_controls=[Fake().entry()]),Fake(),NOW,folder)
        assert bad['gate_accepted'] is False and bad['problems']
        assert gate.collect(dict(schema=2),Fake(),NOW,folder)['problems']
    print('C01 gate refusal protocol: all synthetic controls passed; no product evidence granted')
