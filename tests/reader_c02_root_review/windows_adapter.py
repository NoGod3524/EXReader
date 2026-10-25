"""Natural Windows startup with explicit warm-catalog fixtures; no startup Back/clear."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import receipts as R

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('frozen_c02_windows',ROOT/'tests/reader_final_c02/win_perf.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
PW=B.PW
K=B.K


class Round(B.Round):
    def __init__(self,args):
        super().__init__(args);self.inputs={};self.starts={}
        self.sizes=[int(value) for value in args.sizes.split(',')]
        if args.round==2:self.sizes.reverse()
        self.counts=dict(cold=args.cold,warm=args.warm,resume=args.resume,import_=args.imports)
        self.counts['import']=self.counts.pop('import_')
        K.require(sorted(self.sizes)==[500,5000] and self.counts==R.COUNTS,'Complete frozen sampling plan required')

    def identity_for(self,size):
        return dict(super().identity_for(size),input_strategy=R.STRATEGY)

    def environment(self):
        result=super().environment();result.update(input_strategy=R.STRATEGY,
          strategy_scope='copied prebuilt catalog with clean host settings; not a shared warm session',
          startup_navigation_injected=False,startup_query_modified=False)
        return result

    def profile_for(self,size,cohort,launch):
        if cohort=='warm':
            template=self.corpora[size]['template'];profile=self.corpora[size]['folder']/'profiles'/launch
            if profile.exists():raise PW.MeasurementFault('C02_WARM_PROFILE_NAMESPACE_ALREADY_EXISTS')
            shutil.copytree(template,profile)
            for name in ('host.ini','application.log'):(profile/name).unlink(missing_ok=True)
            source=template/'library.sqlite.product.sqlite';copy=profile/source.name
            source_hash=PW.sha256(source);copy_hash=PW.sha256(copy)
            if source_hash!=copy_hash or source_hash!=self.corpora[size]['prep']['catalog_sha256']:
                raise PW.MeasurementFault('C02_WARM_CATALOG_SNAPSHOT_DIFFERS')
            strategy=R.STRATEGY
            receipt=dict(catalog_source_sha256=source_hash,catalog_copy_sha256=copy_hash,catalog_preserved=True,
                         settings_absent=not (profile/'host.ini').exists())
        else:
            profile,strategy=super().profile_for(size,cohort,launch);receipt={}
        receipt.update(status='ok',launch=launch,size=size,cohort=cohort,profile_strategy=strategy,
                       profile_relative=profile.relative_to(self.work).as_posix())
        self.inputs[launch]=receipt
        return profile,strategy

    def add(self,state,metric,ms,status='ok',note=''):
        super().add(state,metric,ms,status,note)
        if metric=='page_turn':self.rows[-1]['direction']='forward'

    @staticmethod
    def surface(host):
        books=host.control('books');page=host.control('page');query=host.text(host.control('search'),512,300)
        rows=host.lb_count(300);first=host.lb_item(0,300) if rows else ''
        return dict(window_visible=bool(PW.U.IsWindowVisible(host.window)),minimized=bool(PW.U.IsIconic(host.window)),
          books_visible=bool(PW.U.IsWindowVisible(books)),reading_visible=bool(PW.U.IsWindowVisible(page)),
          query_empty=not query,query_characters=len(query),book_rows=rows,
          metadata_enabled=host.enabled('metadata'),legacy_rows='偏移' in first,
          page_key=PW.page_key(host.label(300)))

    @staticmethod
    def reject_contradiction(value):
        if not value['query_empty']:raise PW.MeasurementFault('C02_STARTUP_QUERY_NOT_CLEAN')
        ready=value['metadata_enabled'] and not value['legacy_rows']
        if ready and value['reading_visible'] and value['page_key']:
            raise PW.MeasurementFault('C02_STARTUP_READING_SURFACE_INSTEAD_OF_LIBRARY')
        if ready and value['book_rows']<50:
            raise PW.MeasurementFault('C02_READY_UNFILTERED_SHELF_TOO_SMALL')

    def run_start(self,host,state):
        receipt=dict(status='failed',identity=state['identity'],input_strategy=R.STRATEGY,
          navigation_injected=False,query_modified=False,timer_origin='actual-process-perf-counter-t0')
        self.starts[state['launch']]=receipt
        try:
            first=PW.op_window(host,B.COLD_BUDGET_S)
            def visible():
                value=self.surface(host);self.reject_contradiction(value)
                if value['window_visible'] and not value['minimized'] and value['books_visible'] and not value['reading_visible']:
                    return (value,)
                return None
            (before,)=host.poll(visible,B.COLD_BUDGET_S,interval=0.004)
            receipt['before_original']=before
            # The frozen helper still owns all row/ready/roundtrip predicates.
            marks=PW.op_first_screen(host,B.COLD_BUDGET_S)
            after=self.surface(host);self.reject_contradiction(after);R.natural(after)
            marks['window_ms']=first['window_ms'];marks['controls_ms']=first['controls_ms']
            receipt.update(after_original=after,marks=marks,
                           status='ok' if marks.get('first_screen_interactive_ms') is not None else 'failed')
            self.add(state,'start_window',marks['window_ms']);self.add(state,'start_first_rows',marks['rows_ms'])
            if marks.get('first_screen_interactive_ms') is None:
                self.add(state,'start_interactive',None,'failed','round trip timed out')
            else:self.add(state,'start_interactive',marks['first_screen_interactive_ms'])
            return marks
        except Exception as error:
            receipt.update(fault_class=type(error).__name__,fault=str(error));raise

    def flush(self):
        for size in self.sizes:K.write_json(self.out/('identity-n%d.json'%size),self.identity_for(size))
        for name,key,value in (('samples.json','rows',self.rows),('launches.json','launches',self.launches),('memory.json','records',self.memory)):
            K.write_json(self.out/name,dict(schema=K.SCHEMA,**{key:value}))
        K.write_json(self.out/'plan.json',dict(schema=K.SCHEMA,sizes=self.sizes,plan=B.PLAN,launch_counts=self.counts,
                                             input_strategy=R.STRATEGY,page_turn_direction='forward'))
        K.write_json(self.out/'input-receipts.json',dict(schema=1,input_strategy=R.STRATEGY,
          source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
          sizes=self.sizes,launch_counts=self.counts,startup_navigation_injected=False,startup_query_modified=False,
          inputs=self.inputs,starts=self.starts))
        K.write_json(self.out/'bundle.json',K.bundle_for(self.out))

    def launch(self,size,cohort,index):
        try:return super().launch(size,cohort,index)
        finally:self.flush()

    def run(self):
        try:return super().run()
        finally:
            if self.out.exists():self.flush()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True);parser.add_argument('--seed',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--round',type=int,choices=(1,2),required=True)
    parser.add_argument('--sizes',default='500,5000');parser.add_argument('--cold',type=int,default=4)
    parser.add_argument('--warm',type=int,default=4);parser.add_argument('--resume',type=int,default=4)
    parser.add_argument('--imports',type=int,default=3);parser.add_argument('--producer-source',required=True)
    parser.add_argument('--sdk-version',required=True);args=parser.parse_args()
    K.require(os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true','Windows Actions only')
    K.require(not args.output.exists(),'Choose a new evidence directory')
    K.require(Round.run_resume is B.Round.run_resume and B.COLD_BUDGET_S==3600,'Frozen resume/deadline differs')
    PW.U.IsWindowVisible.argtypes=[PW.W.HWND];PW.U.IsWindowVisible.restype=PW.W.BOOL
    PW.U.IsIconic.argtypes=[PW.W.HWND];PW.U.IsIconic.restype=PW.W.BOOL
    Round(args).run()


if __name__=='__main__':main()
