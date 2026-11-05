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

# The complete second-run evidence is preserved separately, including the
# original overly broad "missing observation" classification of PDF selection.
if __name__=='__main__':
 run=fetch('actions/runs/40225581164');require(run['status']=='completed' and run['head_sha']=='db6c726c2f5bcee03d697e90b4865e7874e6b2a0' and run['run_attempt']==1 and run['conclusion']=='failure','second original run')
 meta=fetch('actions/artifacts/12610882911');require(meta['size_in_bytes']==13057721 and meta['digest']=='sha256:3c02037dc478d8dcf6602a1f12a42419cb708c139e37bbc66455c6317743fda7','second original ZIP')
 b=Bundle(meta)
 try:
  result=b.report('result.json');require(result['harness_source']==run['head_sha'] and result['accepted'] is False,'second original report identity')
  for path,entry in result['files'].items():
   data=b.bytes('evidence/'+path,128*1024**2);require(len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],'second run evidence hash')
  summary={'artifact':meta,'producer_job':121266108707,'authentication_job':121266585174,'original_accepted':False,'positive':result['positive'],'NULL':result['null'],'all_evidence_hashes_verified':True,'classification_correction':'Nonempty original highlights have observed selection 0 versus expected TXT/EPUB 1 and PDF 14. These are observed mismatches, not merely missing observations.'}
  (ROOT/'build/d12/prior-run2.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary),flush=True)
 finally:b.close()
