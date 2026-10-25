"""Report-byte identity checks; exercised with real-run negative mutations in Actions."""
import hashlib
TARGET='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
def validate(report,sha,run,attempt,mode,program,read):
    assert report['harness_sha']==sha and report['target_sha']==TARGET and report['sdk_source']==SDK
    assert report['run_id']==run and report['attempt']==attempt and report['compact']==mode
    assert report['program_sha256']==program
    assert report['files'] and report['snapshots'] and report['checks']
    names=[r['name'] for r in report['checks']];assert len(names)==len(set(names))
    names=[r['name'] for r in report['snapshots']];assert len(names)==len(set(names))
    for path,m in report['files'].items():
        assert not path.startswith('/') and '..' not in path.split('/') and '\\' not in path
        b=read(path);assert len(b)==m['bytes'] and hashlib.sha256(b).hexdigest()==m['sha256'],path
    for snap in report['snapshots']:
        for ext,key in (('png','png_sha256'),('json','tree_sha256')):
            path=snap['name']+'.'+ext
            assert path in report['files'] and hashlib.sha256(read(path)).hexdigest()==snap[key]
def refusals(report,sha,run,attempt,mode,program,read):
    import copy
    count=0
    for field,value in [('harness_sha','wrong'),('target_sha','wrong'),('sdk_source','wrong'),('run_id','0'),('attempt','0'),('compact','UNKNOWN'),('program_sha256','0'*64),('files',{}),('snapshots',[]),('checks',[])]:
        bad=copy.deepcopy(report);bad[field]=value
        try:validate(bad,sha,run,attempt,mode,program,read)
        except (AssertionError,KeyError):count+=1
        else:raise AssertionError('accepted negative mutation '+field)
    for key in ('snapshots','checks'):
        bad=copy.deepcopy(report);bad[key].append(bad[key][0])
        try:validate(bad,sha,run,attempt,mode,program,read)
        except AssertionError:count+=1
        else:raise AssertionError('accepted duplicate '+key)
    try:validate(report,sha,run,attempt,mode,program,lambda path:read(path)+b'tampered')
    except AssertionError:count+=1
    else:raise AssertionError('accepted altered bytes')
    assert count==13
    return count
