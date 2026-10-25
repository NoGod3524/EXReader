"""Minimal isolated rejection controls, never product evidence."""
import copy,json,os
from contract import *
def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    cfgs=[]
    for name in CONFIGS:
        scale=int(name.split('-')[0]);cfgs.append({'configuration':name,'requested_scale':scale,'screenshots':['x.bmp'],'checks':{k:{'status':'pending','actual':{}} for k in REQUIRED}})
    base={'harness_sha':'h','run_id':'r','attempt':'a','target_sha':TARGET,'sdk_source':SDK,'accepted':False,'screen_reader_accepted':False,'program_sha256':'x','files':['x'],'configurations':cfgs}
    validate(base,'h','r','a');results=[]
    for case in ('wrong-dpi','main-window-modal-focus','missing-screenshot','incomplete-configuration'):
        r=copy.deepcopy(base);c=r['configurations'][0]
        if case=='wrong-dpi':c['checks']['dpi']={'status':'pass','actual':{'monitor_scale':{'scale_percent':150},'window_dpi':96}}
        if case=='main-window-modal-focus':c['checks']['search']={'status':'pass','actual':{'focus':[{'descendant':False,'visible':True,'enabled':True}]}}
        if case=='missing-screenshot':c['screenshots']=[]
        if case=='incomplete-configuration':r['configurations'].pop()
        try:validate(r,'h','r','a')
        except (AssertionError,KeyError):results.append({'case':case,'rejected':True});continue
        raise AssertionError('accepted negative '+case)
    print(json.dumps(results));return results
if __name__=='__main__':
    from pathlib import Path
    p=Path('build/d08-evidence');p.mkdir(parents=True,exist_ok=True);(p/'negative-controls.json').write_text(json.dumps(main(),indent=2))
