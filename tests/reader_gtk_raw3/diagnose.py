"""Authenticate a failed raw ZIP and print only retained window startup evidence."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_hosts_integration'))
from final import Bundle,fetch,require


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    run=int(os.environ['FAILED_RUN']);require(run==40222901619,'fixed failed run only')
    metadata=fetch('actions/runs/'+str(run))
    require(metadata['head_sha']=='8cc9f4eb49ad31f743f2bef762d4b2ec0c72f6b4' and metadata['run_attempt']==1 and metadata['status']=='completed','foreign failed run')
    meta=fetch('actions/artifacts/12610671429')
    require(meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==metadata['head_sha'] and
      meta['size_in_bytes']==79157514 and meta['digest']=='sha256:7c45a74a1ab8af6e444b386213fc433b016e1883c12a2e4e4655e60b26254231','foreign failed ZIP')
    bundle=Bundle(meta)
    try:
        report=json.loads(bundle.zip.read('result.json'))
        require(report['accepted'] is False and report['source_sha']==metadata['head_sha'] and int(report['run_id'])==run and int(report['attempt'])==1,'foreign failed report')
        for path,row in report['files'].items():
            data=bundle.zip.read(path)
            require(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'failed inventory differs: '+path)
        print(json.dumps(dict(diagnostic_only=True,accepted=False,source_sha=metadata['head_sha'],run_id=run,artifact=meta['id'])))
        for path in ('mac11-display/openbox.log','mac11-display/account/application.log','mac11-display/account/state.ini',
                     'mac11-display/account/report.json','mac11-display/account/window-tree.txt'):
            print('\nFILE '+path,flush=True)
            if path not in report['files']:print('not retained',flush=True);continue
            print(bundle.zip.read(path).decode('utf-8','replace')[-65536:],flush=True)
    finally:bundle.close()


if __name__=='__main__':main()
