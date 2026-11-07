#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Shakespeare: third-book jumps, measured cubic easing/reversal and DPI.
Usage: check_step6_motion.py EXE FONT REAL_LONG_EPUB OUT
"""
import ctypes as C,json,sys,math
from pathlib import Path
from check_step5 import run,dump,U
from check_toc_panel import open_book,read,trace

def ease(x):
    lo,hi=0.,1.
    for _ in range(30):
        t=(lo+hi)/2;u=1-t
        if .6*u*u*t+.6*u*t*t+t*t*t<x:lo=t
        else:hi=t
    return 2.4*u*u*t+3*u*t*t+t*t*t

def main():
    exe,font,book,out=(Path(p).resolve() for p in sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
    old=C.c_int();assert U.SystemParametersInfoW(0x1042,0,C.byref(old),0)
    result={}
    try:
        assert U.SystemParametersInfoW(0x1043,0,C.c_void_p(1),0)
        s=open_book(book,'The Complete Works')+'shell_click|toc\nprobe_wait|250\nshell_click|toc\nprobe_wait|250\n'
        # Reverse twice from the currently displayed position.
        s+='shell_click|toc\nprobe_wait|45\nshell_click|toc\nprobe_wait|40\nshell_click|toc\nprobe_wait|250\ntoc_measure|reversed\n'
        for i,row in enumerate((10,250,550,900,1100)):
            if i:s+='shell_click|toc\nprobe_wait|230\n'
            s+=f'toc_click|{row}\nwait_idle\nprobe_wait|230\ntoc_measure|jump-{i}\nshell_measure|page-{i}\nsnapshot|jump-{i}\n'
        s+='quit\n';dest=out/'motion';run(exe,font,s,dest/'profile',dest,timeout_seconds=120)
        curve=[];durations=[];state={};start=None;ticks=[]
        for k,t,v in trace(dest):
            t,v=float(t),float(v)
            if k=='toc_start_ms':start=v;state={};ticks=[v]
            elif k=='toc_from':state['from']=v
            elif k=='toc_duration':state['duration']=v
            elif k=='toc_target':state['target']=v
            elif k=='toc_offset' and start is not None and state.get('duration',0)>0:
                ticks.append(t)
                x=min(1,max(0,(t-start)/state['duration']));expected=(state['from']+(state['target']-state['from'])*ease(x)-1)*280
                curve.append(abs(expected-v))
            elif k=='toc_animation_ms':
                frame=max([16.667,t-ticks[-1]]+[b-a for a,b in zip(ticks,ticks[1:])])
                durations.append({'expected':state['duration'],'measured':v,'frame_ms':frame})
                assert abs(v-state['duration'])<=17,(v,state,frame)
        assert curve and max(curve)<=4,max(curve)
        assert read(dest,'reversed')['open']==1 and read(dest,'reversed')['value']==1
        jumps=[]
        for i,row in enumerate((10,250,550,900,1100)):
            m=read(dest,f'jump-{i}');body=read(dest,f'page-{i}');entry=m['rows'][row]
            assert m['open']==0 and m['current']==row and body['part']==entry['part'] and body['text'].strip(),(row,m['current'])
            jumps.append({'row':row,'part':body['part'],'offset':entry['offset'],'label':entry['label'],'pass':True})
        result['animation']={'configured_ms':180,'durations':durations,'curve_samples':len(curve),'max_curve_error_px':max(curve),'reversal':True,'blank':sum(r[0]=='blank' for r in trace(dest))}
        assert result['animation']['blank']==0;result['third_book_jumps']=jumps
        assert U.SystemParametersInfoW(0x1043,0,None,0)
        dest=out/'reduced';s=open_book(book,'The Complete Works')+'shell_click|toc\ntoc_measure|opened\nsnapshot|opened\nshell_click|toc\ntoc_measure|closed\n'
        for dpi in (96,120,144,192):
            s+=f'shell_dpi|{dpi}\nwait_idle\nshell_measure|before-{dpi}\nshell_click|toc\ntoc_measure|dpi-{dpi}\nshell_measure|after-{dpi}\nsnapshot|dpi-{dpi}\nshell_click|toc\n'
        s+='shell_client|320|600\nwait_idle\nshell_click|toc\ntoc_measure|narrow\nshell_measure|narrow-body\nsnapshot|narrow\nshell_key|left\nwait_idle\ntoc_measure|legacy\nshell_key|right\nwait_idle\nquit\n'
        run(exe,font,s,dest/'profile',dest,timeout_seconds=120)
        assert read(dest,'opened')['value']==1 and read(dest,'opened')['animation_ms']==0
        assert read(dest,'closed')['value']==0 and read(dest,'closed')['animation_ms']==0
        assert not any(r[0]=='toc_offset' for r in trace(dest))
        dpirows=[]
        for dpi in (96,120,144,192):
            m=read(dest,f'dpi-{dpi}');a=read(dest,f'before-{dpi}');b=read(dest,f'after-{dpi}')
            assert m['width']==round(280*dpi/96) and m['row_height']==math.floor(34*dpi/96+.5)
            assert a['builds']==b['builds'] and a['range']==b['range']
            dpirows.append({'dpi':dpi,'width':m['width'],'row_height':m['row_height'],'pagination_build_delta':0})
        result['reduced_motion']={'duration_ms':0,'intermediate_frames':0};result['dpi']=dpirows
        client_width=read(dest,'narrow-body')['client'][0]
        result['narrow']={'requested_width':320,'actual_client_width':client_width,'dpi':192,'panel_width':read(dest,'narrow')['width']}
        assert read(dest,'narrow')['width']==min(560,client_width-112) and read(dest,'legacy')['open']==0
    finally:assert U.SystemParametersInfoW(0x1043,0,C.c_void_p(old.value),0)
    dump(out/'result.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
