#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native UIA snapshot while an offscreen, DPI-aware PrintWindow drive runs.
Usage: check_step6_uia.py EXE FONT REAL_LONG_EPUB OUT
"""
import json,sys,time,threading
from pathlib import Path
import uiautomation as auto
from check_step5 import run,dump
from check_shell_2a import uia,main_window
from check_toc_panel import open_book,read

def main():
    exe,font,book,out=(Path(p).resolve() for p in sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
    s=open_book(book,'The Complete Works')+'toc_measure|closed\nprobe_wait|5000\nshell_click|toc\nprobe_wait|230\ntoc_measure|opened\nsnapshot|opened\nprobe_wait|10000\nquit\n'
    errors=[]
    def drive():
        try:run(exe,font,s,out/'profile',out,timeout_seconds=120)
        except BaseException as e:errors.append(e)
    thread=threading.Thread(target=drive);thread.start();result={}
    for marker in ('closed','opened'):
        start=time.monotonic()
        while not (out/(marker+'.json')).exists():
            assert thread.is_alive() and time.monotonic()-start<60,errors;time.sleep(.05)
        lines=(out/'drive.log').read_text(encoding='utf8').splitlines();pid=int(next(l for l in lines if l.startswith('HOST\t')).split('pid=')[1].split('\t')[0]);hwnd=main_window(pid);assert hwnd
        if marker=='closed':
            rows=uia(hwnd,out/'uia-closed.json');operable=[r for r in rows if r['operable'] and not r['offscreen']]
            assert len(operable)==3 and all(r['name'] for r in operable),rows
            result['closed_operable']=[{'type':r['type'],'name':r['name']} for r in operable]
        else:
            root=auto.ControlFromHandle(hwnd)
            def find(control):
                for c in control.GetChildren():
                    if c.ControlTypeName=='ListControl' and c.AutomationId=='168':return c
                    x=find(c)
                    if x:return x
            control=find(root);assert control
            items=control.GetChildren();m=read(out,'opened')
            assert len(items)==m['count'] and items[0].Name==m['rows'][0]['label'] and items[-1].Name==m['rows'][-1]['label']
            result['open_list']={'count':len(items),'first':items[0].Name,'last':items[-1].Name,'one_tab_stop':control.IsKeyboardFocusable}
    thread.join();assert not errors,errors;dump(out/'result.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
