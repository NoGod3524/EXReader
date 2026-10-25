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


def main():
    guard.check()
    meta=V.gh('repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID'])[0]
    R.K.require(meta['path'].split('@')[0]==guard.WORKFLOW,'Wrong actual workflow identity')
    original=V.A.load_round;validated=[];errors=[]
    def load(directory,platform,expected):
        try:
            # V.main has authenticated this run's actual ZIP digest/size/source;
            # original load_round additionally checks its complete member bundle.
            loaded=original(directory,platform,expected)
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
        report=dict(schema=1,input_strategy=R.STRATEGY,validated_windows_rounds=validated,errors=errors,
          source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
          zip_binding='original verifier authenticates actual same-run ZIP before receipt loading',
          current_common_product_performance_accepted=False,budget_approved=False)
        (output/'root-review-inputs.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
