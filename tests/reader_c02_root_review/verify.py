"""Require actual ZIP-bound input receipts before unchanged original aggregation."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import guard
import receipts as R

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('frozen_c02_verifier',ROOT/'tests/reader_final_c02/verify.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)


def diagnostic_summary(directory,platform,expected):
    root=Path(directory)
    if platform=='windows':
        value=V.K.read_json(root/'operation-trace.json');R.diagnostic_identity(value,expected)
        operations=value['operations']
        failed=[item for item in operations if item['status']!='ok']
        report=dict(platform=platform,operations=len(operations),failed_operations=failed,
          resumes=[item for item in operations if item['operation']=='op_resume'])
    else:
        paths=sorted(root.glob('raw/n*/raw/launch-*/diagnostic-timeline.json'))
        V.K.require(len(paths)==24,'GTK launch diagnostic timeline missing')
        imports=[];observer_faults=[]
        for path in paths:
            value=V.K.read_json(path);R.diagnostic_identity(value,expected)
            if value['independent_failure']:observer_faults.append(dict(path=str(path.relative_to(root)),fault=value['independent_failure']))
            events=value['original_observations'];operations=value['operations']
            for item in operations:
                if item['operation']!='await_state' or item['what']!='import worker start':continue
                open_calls=[entry for entry in operations if entry['operation']=='open_import_dialog' and
                            entry['returned_at']<=item['entered_at']]
                opened=max(open_calls,key=lambda entry:entry['returned_at']) if open_calls else None
                start=opened['entered_at'] if opened else item['entered_at'];end=item['returned_at']
                original=[event for event in events[item['since']:] if event['at']<=end]
                file_events=[event for event in value['independent_file_events'] if
                  event['name'].startswith('state.ini') and start<=event['snapshot_read_at']<=end]
                busy=[event for event in original if event['state']['host'].get('busy')==1]
                independent_busy=[event for event in file_events if (event['latest_state'] or {}).get('host',{}).get('busy')==1]
                sequences=[event['state']['host'].get('sequence') for event in original]
                gaps=[right-left for left,right in zip(sequences,sequences[1:]) if isinstance(left,int) and isinstance(right,int)]
                result=dict(path=str(path.relative_to(root)),wait_status=item['status'],timeout=item['timeout'],
                  original_busy_observations=len(busy),independent_busy_snapshots=len(independent_busy),
                  original_observations=len(original),file_events=len(file_events),max_sequence_gap=max(gaps,default=0),
                  interpretation='busy captured by original observer' if busy else
                    'independent snapshot saw busy while original observer did not' if independent_busy else
                    'no captured busy; cannot distinguish unstarted worker from overwritten/missed snapshots')
                if item['status']!='ok':result.update(wait=item,open_import=opened,
                  input_operations=[entry for entry in operations if entry['operation']=='press' and start<=entry['entered_at']<=end],
                  first_events=original[:3],last_events=original[-3:],file_tail=file_events[-3:])
                imports.append(result)
        report=dict(platform=platform,launch_timelines=len(paths),imports=imports,observer_faults=observer_faults,
          independent_snapshot_limit='latest snapshots read after file notification; not a reconstruction of every write')
    print('C02_ZIP_BOUND_DIAGNOSTICS '+json.dumps(report),flush=True)
    return report


def main():
    guard.check()
    meta=V.gh('repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID'])[0]
    R.K.require(meta['path'].split('@')[0]==guard.WORKFLOW,'Wrong actual workflow identity')
    original=V.A.load_round;validated=[];errors=[];diagnostics=[]
    def load(directory,platform,expected):
        try:
            # V.main has authenticated this run's actual ZIP digest/size/source;
            # original load_round additionally checks its complete member bundle.
            loaded=original(directory,platform,expected)
            diagnostics.append(dict(round=loaded['round'],**diagnostic_summary(directory,platform,expected)))
            if platform=='windows':
                path=Path(directory)
                proof=R.validate(V.K.read_json(path/'input-receipts.json'),loaded,expected,
                  {size:V.K.read_json(path/('prepare-n%d.json'%size)) for size in (500,5000)})
                validated.append(dict(round=loaded['round'],**proof))
            return loaded
        except (V.K.Rejected,OSError,KeyError,TypeError,ValueError) as error:
            errors.append(dict(platform=platform,fault_class=type(error).__name__,message=str(error)))
            raise V.K.Rejected('root input receipt/old round validation: '+str(error)) from error
    V.A.load_round=load
    try:V.main()
    finally:
        output=ROOT/'build/c02-verify';output.mkdir(parents=True,exist_ok=True)
        report=dict(schema=1,input_strategy=R.STRATEGY,validated_windows_rounds=validated,errors=errors,diagnostics=diagnostics,
          source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
          zip_binding='original verifier authenticates actual same-run ZIP before receipt loading',
          current_common_product_performance_accepted=False,budget_approved=False)
        (output/'root-review-inputs.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
