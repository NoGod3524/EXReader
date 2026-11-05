"""Actions-only deterministic checks of diagnostic completion after classification."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch
import gtk_adapter as T


def case(launch_error=False,close_error=False,diagnostic_error=False):
    events=[];token=object();close_token=object();fault=RuntimeError('original launch error')
    close_fault=RuntimeError('original close error');diagnostic_fault=RuntimeError('diagnostic error')
    watch=T.TraceWatch.__new__(T.TraceWatch);watch.folder=Path('controlled-stub');watch.failure=None
    sampler=T.DiagnosticSampler.__new__(T.DiagnosticSampler);sampler.launches=[]
    assert not T.PENDING_DIAGNOSTICS
    def original_close(value):
        assert value is watch;events.append('original-close');value.failure='real-observation-failure'
        if close_error:raise close_fault
        return close_token
    def original_launch(value,index):
        assert value is sampler and index==7;events.append('original-launch')
        assert watch.close() is close_token
        assert events==['original-launch','original-close'],'Diagnostic waited inside close'
        events.append('read-original-failure')
        sampler.launches.append(dict(observation_failure=watch.failure))
        events.append('original-classification-complete')
        if launch_error:raise fault
        return token
    def finish(value,classification):
        assert value is watch
        assert classification==sampler.launches
        assert watch.failure=='real-observation-failure'
        assert close_error or events[-1]=='original-classification-complete'
        events.extend(('diagnostic-join','diagnostic-write'))
        if diagnostic_error:raise diagnostic_fault
    output=io.StringIO();observed=None
    with patch.object(T.OriginalWatch,'close',original_close),\
         patch.object(T.S.Sampler,'launch_once',original_launch),\
         patch.object(T.TraceWatch,'finish_diagnostics',finish),contextlib.redirect_stdout(output):
        try:result=sampler.launch_once(7)
        except RuntimeError as error:observed=error
        else:assert result is token
    assert observed is (close_fault if close_error else fault if launch_error else None)
    assert watch.failure=='real-observation-failure','Original failure was cleared or downgraded'
    assert sampler.launches==([] if close_error else [dict(observation_failure='real-observation-failure')])
    assert events[-2:]==['diagnostic-join','diagnostic-write']
    assert not T.PENDING_DIAGNOSTICS
    if diagnostic_error:assert 'C02_DIAGNOSTIC_FINALIZE_FAILURE' in output.getvalue()
    return dict(launch_error=launch_error,close_error=close_error,diagnostic_error=diagnostic_error,
                order=events,original_failure_preserved=True)


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    cases=[case(),case(launch_error=True),case(close_error=True),case(diagnostic_error=True),
           case(launch_error=True,diagnostic_error=True),case(close_error=True,diagnostic_error=True)]
    report=dict(schema=1,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
      attempt=os.environ['GITHUB_RUN_ATTEMPT'],ok=True,checks=cases,check_count=len(cases),
      scope='diagnostic completion control flow only',performance_accepted=False,
      original_three_full_rounds_accepted=False,full_performance_round_started=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':main()
