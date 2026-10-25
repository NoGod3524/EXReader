"""Actions-only read-only diagnosis of a completed failed compact raw artifact."""
import hashlib
import json
import os
from aggregate import Bundle,fetch,identity,pages,require,WORKFLOW


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    run=int(os.environ['FAILED_RUN']);metadata=fetch('actions/runs/'+str(run))
    require(metadata['status']=='completed' and metadata['conclusion']=='failure' and
            metadata['path'].split('@')[0]==WORKFLOW,'not a completed compact failure')
    attempt=metadata['run_attempt'];source=metadata['head_sha']
    name='reader-gtk-341-final-%d-%d'%(run,attempt)
    meta,=[row for row in pages('actions/runs/%d/artifacts'%run,'artifacts') if row['name']==name]
    require(meta['workflow_run']['head_sha']==source and meta['workflow_run']['id']==run,'foreign artifact')
    bundle=Bundle(meta)
    try:
        report=bundle.report('compact-ui/report.json');identity(report,source,run,attempt)
        require(report['accepted'] is False and report.get('failure'),'missing actual failure')
        visibility=bundle.report('compact-ui/failure-visibility.json')
        controls=[row for row in visibility['controls'] if row['states'].get('showing') or row['states'].get('focused')]
        screenshots=[]
        for row in report.get('failure_screenshots',[]):
            data=bundle.bytes('compact-ui/'+row['path'],32*1024**2)
            require(data.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(data).hexdigest()==row['sha256'],'failure screenshot differs')
            screenshots.append(row)
        print(json.dumps(dict(diagnostic_only=True,accepted=False,source_sha=source,run_id=run,attempt=attempt,
            artifact=meta,failure=report['failure'],passed_checks=[row['name'] for row in report['checks'] if row['passed']],
            state=visibility['state'],visible_or_focused=controls,screenshots=screenshots),ensure_ascii=True,indent=2),flush=True)
    finally:bundle.close()


if __name__=='__main__':main()
