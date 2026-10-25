"""Report-byte identity checks; exercised with real-run negative mutations in Actions."""
import hashlib
TARGET='803098e9df1a365a9b8e206805c2d179aca8501f'
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

CONFIGS=('ON-normal','ON-scale2','ON-dark','ON-large')
REQUIRED={'bridge','scale-readback','compact-mode','coordinate-calibration','tab-forward-reverse','tab-focus-names','import-cancel','keyboard-import-open','next-page','more-text-leaves','search-dialog-focus','search-escape','directory-dialog-focus','directory-escape','records-dialog-focus','record-save','records-escape','settings-dialog-focus','settings-escape','return-shelf-search'}
def modal_focus_ok(observation):
    path=observation.get('dialog_path','')
    ds=observation.get('dialog_states',{})
    if not path or not ds.get('modal') or not ds.get('active') or not ds.get('showing'): return False
    return any(f.get('descendant') is True and f.get('path','').startswith(path+'/')
        and all(f.get('states',{}).get(k) is True for k in ('enabled','sensitive','visible','showing','focused'))
        for f in observation.get('focus',[]))
def coordinate_ok(c):
    scale=c.get('scale');samples=c.get('samples',[])
    if scale not in (1,2) or len(samples)!=3:return False
    for row in samples:
        p=row.get('physical',{});a=row.get('logical') or {}
        if not all(k in p for k in ('X','Y','WIDTH','HEIGHT')) or not all(k in a for k in ('x','y','width','height')):return False
        if any(abs(p[k.upper()]-a[k]*scale)>max(4,scale*2) for k in ('x','y','width','height')):return False
    first,moved,restored=samples
    for axis in ('x','y'):
        pd=moved['physical'][axis.upper()]-first['physical'][axis.upper()]
        ad=moved['logical'][axis]-first['logical'][axis]
        if abs(pd-40)>2 or abs(pd-ad*scale)>scale*2:return False
        if abs(restored['physical'][axis.upper()]-first['physical'][axis.upper()])>2:return False
    return True

def scope_ready(reports):
    if set(reports)!=set(CONFIGS):return False
    for d in reports.values():
        checks={x['name']:x for x in d['checks']}
        if not REQUIRED<=set(checks) or not all(checks[n]['passed'] for n in REQUIRED):return False
        if not d.get('program_sha256') or not d.get('snapshots') or not d.get('audit_completed'):return False
        if not coordinate_ok(d.get('coordinate_calibration',{})):return False
        for name in ('search','directory','records','settings'):
            if not modal_focus_ok(checks[name+'-dialog-focus']['actual']):return False
            if not {name+'-before-open',name+'-dialog',name+'-before-close',name+'-after-close'} <= {s['name'] for s in d['snapshots']}:return False
    return True

def semantic_refusals():
    import copy
    good={'dialog_path':'application/dialog[Reading records]#1','dialog_states':{'active':True,'modal':True,'showing':True},'focus':[{'path':'application/dialog[Reading records]#1/button[Close]#0','descendant':True,'states':dict.fromkeys(('enabled','sensitive','visible','showing','focused'),True)}]}
    assert modal_focus_ok(good)
    refused=[]
    bad=copy.deepcopy(good);bad['focus'][0]['path']='application/frame[EXReader Linux]#0/button[Import F1]#0';bad['focus'][0]['descendant']=False
    assert not modal_focus_ok(bad);refused.append('main-frame-focus-rejected')
    for state in ('enabled','sensitive','visible','showing','focused'):
        bad=copy.deepcopy(good);bad['focus'][0]['states'].pop(state)
        assert not modal_focus_ok(bad);refused.append('missing-'+state+'-rejected')
    samples=[dict(physical=dict(X=x,Y=x,WIDTH=800,HEIGHT=600),logical=dict(x=x//2,y=x//2,width=400,height=300)) for x in (100,140,100)]
    goodc=dict(scale=2,samples=samples);assert coordinate_ok(goodc)
    bad=copy.deepcopy(goodc);bad['scale']=1;assert not coordinate_ok(bad);refused.append('scale2-unconverted-rejected')
    assert not coordinate_ok({'scale':2,'verified':True});refused.append('unmeasured-coordinate-claim-rejected')
    assert not scope_ready({});refused.append('missing-configurations-rejected')
    return refused
