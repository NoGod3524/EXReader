"""Retain and authenticate the entire first failed run before further acceptance."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'target/tests/reader_hosts_integration'))
from final import Bundle,fetch,require

def main():
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 run=fetch('actions/runs/40225059154');require(run['status']=='completed' and run['conclusion']=='failure' and run['head_sha']=='bba0fe12d28f1996764eb20aca971302c6af16da' and run['run_attempt']==1,'original failed run')
 meta=fetch('actions/artifacts/12611470429');require(meta['size_in_bytes']==11952632 and meta['digest']=='sha256:26afe8e99c90b4b57462d5d561c624a3036c737893dab26c0903b1be1e0971ad','first failed original ZIP')
 b=Bundle(meta)
 try:
  report=b.report('result.json');require(report['harness_source']==run['head_sha'] and report['accepted'] is False,'retained failure identity')
  for path,entry in report['files'].items():
   data=b.bytes('evidence/'+path,128*1024**2);require(len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],'retained failed evidence hash')
  out=ROOT/'build/d12';out.mkdir(parents=True,exist_ok=True)
  summary={'artifact':meta,'producer_job':121264564040,'original_accepted':False,'positive_receive':report['positive_receive'],'positive_gui_count':len(report['positive']),'NULL':report['null'],'original_NULL_graph':report['null_original_graph'],'all_evidence_hashes_verified':True}
  (out/'prior-failure.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary),flush=True)
 finally:b.close()
if __name__=='__main__':main()
