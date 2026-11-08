# SPDX-License-Identifier: MIT
"""Windows search acceptance through native controls, with DPI-aware PID captures.
Run: python -X utf8 examples/windows/check_shell_search.py EXE FONT OUTPUT
Local real-book paths come from tools/regress/corpus.json. Originals stay local.
"""
import ctypes as c
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_document_search import SearchSDK,Error

def run(exe,font,out,script,captures=()):
    out.mkdir(parents=True,exist_ok=True)
    logpath=out/'drive.log'
    if logpath.exists():logpath.unlink()
    (out/'run.drive').write_text('\n'.join(script)+'\n',encoding='utf8')
    env=os.environ.copy();env['EXR_PAINT_TRACE']=str(out/'paint.csv')
    p=subprocess.Popen([str(exe),'--offscreen','--font',str(font),'--drive',str(out/'run.drive'),
      '--data',str(out/'profile'),'--evidence',str(out),'--phase','search'],env=env,
      creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    begin=time.perf_counter();captured=set();metadata={}
    try:
        while p.poll() is None:
            log=logpath.read_text(encoding='utf8') if logpath.exists() else ''
            for match,name in captures:
                if name not in captured and match in log:
                    value=subprocess.check_output([sys.executable,'-X','utf8',str(ROOT/'ops/capture_window.py'),str(p.pid),str(out/(name+'.png'))],text=True)
                    metadata[name]=json.loads(value);captured.add(name)
            if time.perf_counter()-begin>180:raise TimeoutError(log[-3000:])
            time.sleep(.025)
    finally:
        if p.poll() is None:p.terminate();p.wait()
    log=logpath.read_text(encoding='utf8');failures=[line for line in log.splitlines() if '\tFAIL\t' in line]
    assert p.returncode==0 and not failures,(p.returncode,failures)
    assert len(captured)==len(captures),(captured,captures)
    checks=[line for line in log.splitlines() if '\tsearch_check\t' in line]
    result={'exit':p.returncode,'checks':checks,'captures':metadata,'elapsed_seconds':time.perf_counter()-begin}
    input_ms=[float(x) for x in re.findall(r'native_edit_ms=([\d.]+)',log)]
    if input_ms:
        assert len(input_ms)==10
        # The first query warms the cache. Empty text performs no search.
        first=int(re.search(r'calls=(\d+)',checks[0]).group(1));last=int(re.search(r'calls=(\d+)',checks[-1]).group(1));assert last-first==1
        result['typing']={'characters':10,'interval_requested_ms':30,'actual_searches':last-first,'native_edit_ms':input_ms,
          'max_edit_ms':max(input_ms),'edit_sum_ms':sum(input_ms),'total_ms':float(re.search(r'total_ms=([\d.]+)',checks[-1]).group(1)),
          'search_ms':float(re.search(r'search_ms=([\d.]+)',checks[-1]).group(1))}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(out.name,json.dumps(result.get('typing',{'checks':len(checks)})),flush=True)
    return result

def setup():return ['shell|on','shell_client|1280|800','shell_click|settings','shell_click|light','shell_click|settings']
def main():
    exe,font,out=[Path(x).resolve() for x in sys.argv[1:4]];out.mkdir(parents=True,exist_ok=True)
    books={x['id']:x for x in json.loads((ROOT/'tools/regress/corpus.json').read_text())['books']}
    results={}
    hong=books['hongloumeng-24264']
    script=['import|'+hong['path'],'open|紅樓夢']+setup()+['search_query|的','search_check|13989|1|1','probe_wait|10000',
      'search_key|enter','wait_idle','search_check|13989|2|1','probe_wait|10000','search_key|shift_enter','wait_idle','search_check|13989|1|1',
      'search_key|esc','wait_idle','search_check|13989|1|0','search_query|','probe_wait|250']
    for char in '一二三四五六七八九十':script+=['search_append|'+char,'probe_wait|30']
    script+=['wait_idle','search_check|0||1','quit']
    results['hong']=run(exe,font,out/'hong',script,[('current=1 open=1','expanded-current'),('current=2 open=1','next-current')])
    phases=[('english','a-raisin-in-the-sun','A Raisin','Nemiroff','10'),
      ('vertical','kusamakura-japanese-vertical-writing','草枕','住み','positive'),
      ('pdf','the-autobiography-of-malcolm-x.','Autobiography','Malcolm','positive'),
      ('mobi','zami-a-new-spelling-of-my-name---a-biomythography','Zami','Lorde','positive')]
    for label,bid,title,query,expected in phases:
        script=['import|'+books[bid]['path'],'open|'+title]+setup()+['search_query|'+query,'search_check|'+expected+'|1|1','probe_wait|10000' if label=='vertical' else 'probe_wait|100','quit']
        results[label]=run(exe,font,out/label,script,[('current=1 open=1','vertical-current')] if label=='vertical' else [])
    # Exercise the older whole-document EPUB storage path as well as source import.
    legacy=out/'whole-document';profile=legacy/'profile';profile.mkdir(parents=True,exist_ok=True)
    sdk=SearchSDK(exe.parent/'libexreader.dll');ptr=c.c_void_p;err=c.POINTER(Error)
    for name,restype,args in [('library_open',c.c_int,[c.c_char_p,c.POINTER(ptr),err]),
      ('library_import',c.c_int,[ptr,c.c_int,ptr,c.c_size_t,c.c_char_p,c.POINTER(c.c_int64),err]),('library_close',None,[ptr])]:
        fn=getattr(sdk.dll,'exr_'+name);fn.restype,fn.argtypes=restype,args;setattr(sdk,name,fn)
    lib=ptr();sdk.check('library_open',str(profile/'library.sqlite').encode(),c.byref(lib));data=Path(hong['path']).read_bytes();bookid=c.c_int64()
    sdk.check('library_import',lib,4,data,len(data),'紅樓夢 memory'.encode(),c.byref(bookid));sdk.library_close(lib)
    results['whole-document']=run(exe,font,legacy,['open|紅樓夢 memory']+setup()+['search_query|的','search_check|13989|1|1','quit'])
    (out/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
