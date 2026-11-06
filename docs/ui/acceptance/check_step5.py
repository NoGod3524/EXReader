#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offscreen step-5 acceptance. All children use CREATE_NO_WINDOW.

Usage: check_step5.py EXE BASELINE_EXE FONT BOOK OUT
The baseline is the pre-change reader built from the same SDK. Never activates
a window or moves the pointer. PrintWindow snapshots come from --drive.
"""
import contextlib
import io
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from PIL import Image, ImageChops

U=C.windll.user32
U.SetProcessDpiAwarenessContext(C.c_void_p(-4))
U.GetForegroundWindow.restype=W.HWND
U.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
U.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.IsWindowVisible.argtypes=[W.HWND]
CALLBACK=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
U.EnumWindows.argtypes=[CALLBACK,W.LPARAM]
HIDDEN=subprocess.CREATE_NO_WINDOW

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def run(exe,font,script,data,out,allowed_failures=0,timeout_seconds=180):
    out.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    drive=out/'run.drive';drive.write_text(script,encoding='utf-8')
    env=dict(os.environ,EXREADER_HOST_ACCEPTANCE='1',EXR_PAINT_TRACE=str(out/'paint.csv'))
    command=[str(exe),'--offscreen','--drive',str(drive),'--evidence',str(out),
             '--data',str(data),'--library',str(data/'library.sqlite'),'--font',str(font),'--phase','1']
    p=subprocess.Popen(command,env=env,creationflags=HIDDEN,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    positions=set();foreground=0;start=time.monotonic()
    @CALLBACK
    def visit(hwnd,_):
        pid=W.DWORD();U.GetWindowThreadProcessId(hwnd,C.byref(pid))
        if pid.value==p.pid and U.IsWindowVisible(hwnd):
            box=W.RECT();U.GetWindowRect(hwnd,C.byref(box));positions.add((box.left,box.top))
        return True
    while p.poll() is None:
        pid=W.DWORD();U.GetWindowThreadProcessId(U.GetForegroundWindow(),C.byref(pid))
        foreground+=pid.value==p.pid;U.EnumWindows(visit,0)
        if time.monotonic()-start>timeout_seconds: p.kill();raise RuntimeError('drive timeout')
        time.sleep(.02)
    stdout,stderr=p.communicate()
    result=dict(exit=p.returncode,foreground_observations=foreground,positions=sorted(positions),
                elapsed_seconds=time.monotonic()-start,stderr=stderr.decode(errors='replace'))
    dump(out/'process.json',result)
    assert foreground==0 and positions=={(-32000,-32000)},result
    steps=[l for l in (out/'drive.log').read_text(encoding='utf-8').splitlines() if l.startswith('STEP\t')]
    failed=[l for l in steps if l.split('\t')[3]!='PASS']
    assert steps and len(failed)<=allowed_failures and p.returncode==(1 if failed else 0),(result,failed)
    return result

def client(out,name,meta):
    x,y,w,h=meta['client_box'];return Image.open(out/(name+'.png')).convert('RGB').crop((x,y,x+w,y+h))

def rgb(value): return tuple(bytes.fromhex(value.lstrip('#')))
def hx(p): return '#'+''.join(f'{v:02x}' for v in p[:3])
def blend(a,b,t): return tuple(int(x*(1-t)+y*t+.5) for x,y in zip(rgb(a),rgb(b)))
def contrast(a,b):
    def lum(c):
        q=[v/255 for v in c];q=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in q]
        return sum(v*w for v,w in zip(q,(.2126,.7152,.0722)))
    x,y=sorted((lum(a),lum(b)));return (y+.05)/(x+.05)

def remaining(exe,baseline,font,book,out):
    result={}
    # Exercise a real nonzero page head, not just the trivial offset-zero case.
    script=f'import|{book}\nopen|EXReader benchmark\nwait_idle\nshell|on\nshell_dpi|96\nshell_client|1280|800\nwait_idle\n'
    script+='probe_key\n'*3+'shell_measure|head-before\n'
    for i in range(6):script+=f'shell_click|plus\nwait_idle\nshell_measure|head-{i}\n'
    script+='quit\n'
    run(exe,font,script,out/'head-profile',out/'head')
    heads=[json.loads(p.read_text()) for p in sorted((out/'head').glob('head*.json'))]
    result['nonzero_head_offsets']={p.stem:json.loads(p.read_text())['lines'][0][0] for p in sorted((out/'head').glob('head*.json'))}
    result['nonzero_head_preserved']=len({m['lines'][0][0] for m in heads})==1
    # Legacy INI: no active book, so startup cannot legitimately save progress.
    data=out/'profile';db=data/'library.sqlite'
    with sqlite3.connect(db) as conn:before_dump='\n'.join(conn.iterdump())
    before_hash=hashlib.sha256(db.read_bytes()).hexdigest()
    legacy='[Host]\nFontPercent=150\nZoomPercent=100\nWindowWidth=1180\nWindowHeight=900\nActiveBook=0\n'
    (data/'host.ini').write_text(legacy);(out/'legacy-before.ini').write_text(legacy)
    run(exe,font,'settings_measure|defaults\nquit\n',data,out/'old-ini')
    with sqlite3.connect(db) as conn:after_dump='\n'.join(conn.iterdump())
    result['old_ini']={'before_sha256':before_hash,'after_sha256':hashlib.sha256(db.read_bytes()).hexdigest(),
                       'logical_shelf_equal':before_dump==after_dump,
                       'defaults':json.loads((out/'old-ini/defaults.json').read_text())}
    assert result['old_ini']['logical_shelf_equal'] and result['old_ini']['before_sha256']==result['old_ini']['after_sha256']
    assert result['old_ini']['defaults']['font']==17 and result['old_ini']['defaults']['theme']==2
    (out/'legacy-after.ini').write_text((data/'host.ini').read_text())
    # Actual system selection, persistence, and setting-change delivery.
    script='open|EXReader benchmark\nwait_idle\nshell|on\nshell_click|system\nsettings_measure|system\nsnapshot|system\nquit\n'
    run(exe,font,script,data,out/'system')
    run(exe,font,'settings_measure|system-restart\nquit\n',data,out/'system-restart')
    result['system']=json.loads((out/'system/system.json').read_text())
    restarted=json.loads((out/'system-restart/system-restart.json').read_text())
    assert result['system']['theme']==restarted['theme']==2
    (out/'system-after-restart.ini').write_text((data/'host.ini').read_text())
    test=out/'selftest';test.mkdir(exist_ok=True)
    cbz=Path(__file__).resolve().parents[3]/'tests/fixtures/comic.cbz'
    p=subprocess.run([str(exe),'--self-test',str(font),str(book),str(cbz),str(test/'report.json'),str(test/'page.png')],
                     capture_output=True,creationflags=HIDDEN,timeout=60)
    result['selftest']={'exit':p.returncode,**json.loads((test/'report.json').read_text())}
    assert result['selftest']['exit']==0 and result['selftest']['checks']==26
    # Eight old-layout screenshots, independently imported profiles, same SDK.
    legacy_script=f'import|{book}\nwait_idle\nui_cues|hide\nsnapshot|01\nopen|EXReader benchmark\nwait_idle\nsnapshot|02\nprobe_key\nsnapshot|03\nprobe_key\nsnapshot|04\nsnapshot|05\nquit\n'
    for label,binary in [('baseline',baseline),('changed',exe),('control',baseline)]:
        target=out/'regression'/label
        run(binary,font,legacy_script,target/'profile',target/'A')
        run(binary,font,'wait_idle\nui_cues|hide\nsnapshot|10\nprobe_key\nsnapshot|11\nquit\n',target/'profile',target/'B')
        run(binary,font,'wait_idle\nui_cues|hide\nsnapshot|20\nquit\n',target/'profile',target/'C')
    from compare_shots import compare,self_test
    rows=[];a=out/'regression/baseline'
    counts={}
    for label in ('control','changed'):
        def record(*args):rows.append(label+' '+' '.join(map(str,args)))
        count,failed=compare(a,out/'regression'/label,38,record)
        counts[label]={'images':count,'nonzero':failed}
    (out/'regression/comparison.txt').write_text('\n'.join(rows))
    capture=io.StringIO()
    with contextlib.redirect_stdout(capture):negative=self_test()
    (out/'regression/negative.txt').write_text(capture.getvalue())
    counts['negative_selftest_exit']=negative;result['regression']=counts
    assert all(counts[label]=={'images':8,'nonzero':0} for label in ('control','changed')) and negative==0,counts
    return result

def main():
    exe,baseline,font,book,out=map(lambda v:Path(v).resolve(),sys.argv[1:])
    out.mkdir(parents=True,exist_ok=True)
    data=out/'profile';evidence=out/'settings'
    opening=f'import|{book}\nopen|EXReader benchmark\nwait_idle\nshell|on\nshell_dpi|96\nshell_client|1280|800\nwait_idle\n'
    script=opening+'shell_click|settings\nwait_idle\n'
    for theme in ('light','dark'):
        script+=f'shell_click|{theme}\nwait_idle\nsettings_measure|{theme}\nshell_measure|body-{theme}\nsnapshot|{theme}\n'
        for kind,control in (('stepper','plus'),('ghost','system'),('primary',theme)):
            for state in ('normal','hover','pressed','focus','disabled'):
                name=f'{theme}-{kind}-{state}'
                script+=f'shell_enable|{control}|1\nshell_press|{control}|0\nshell_hover|none\nshell_render_focus|none\nui_cues|hide\n'
                if state in ('hover','pressed'): script+=f'shell_hover|{control}\n'
                if state=='pressed': script+=f'shell_press|{control}|1\n'
                if state=='focus': script+=f'shell_render_focus|{control}\n'
                if state=='disabled': script+=f'shell_enable|{control}|0\n'
                script+=f'snapshot|{name}\nshell_enable|{control}|1\nshell_press|{control}|0\n'
    script+='shell_hover|none\nui_cues|hide\nshell_click|settings\nwait_idle\nshell_measure|font-before\n'
    for i in range(6): script+=f'shell_click|plus\nwait_idle\nshell_measure|font-up-{i}\n'
    for i in range(9): script+=f'shell_click|minus\nwait_idle\nshell_measure|font-down-{i}\n'
    for i in range(9): script+=f'shell_click|plus\nwait_idle\nshell_measure|font-all-{i}\n'
    script+='shell_click|minus\nwait_idle\nsettings_measure|saved\n'
    for i in range(20): script+='probe_key\n'
    script+='probe_wheel_burst\nwait_idle\nsnapshot|dark-final\nquit\n'
    old=W.BOOL();assert U.SystemParametersInfoW(0x1042,0,C.byref(old),0)
    try:
        assert U.SystemParametersInfoW(0x1043,0,None,0)
        process=run(exe,font,script,data,evidence)
    finally:
        assert U.SystemParametersInfoW(0x1043,0,C.c_void_p(old.value),0)
    result={'process':process,'colours':{},'states':[]}
    for theme in ('light','dark'):
        m=json.loads((evidence/(theme+'.json')).read_text());im=client(evidence,theme,m)
        bg,surface,text,secondary,line,accent,accent_hover=(
          ('#f5f5f2','#ffffff','#1b1b1f','#5c5c65','#141420','#4553e0','#3946cc') if theme=='light' else
          ('#141416','#1e1e21','#f2f2f4','#b3b3bc','#ffffff','#7c88ff','#929cff'))
        surface2='#efeeea' if theme=='light' else '#28282c'
        result['colours'][theme]={'bg':hx(im.getpixel((8,300))),'surface':hx(im.getpixel((m['panel'][2]-20,m['panel'][1]+50)))}
        assert result['colours'][theme]=={'bg':bg,'surface':surface}
        assert m['class_bg']==int.from_bytes(bytes(rgb(bg)),'little')
        for kind,control in (('stepper','plus'),('ghost','system'),('primary',theme)):
            x,y,r,b=m['controls'][control];w,h=r-x,b-y
            for state in ('normal','hover','pressed','focus','disabled'):
                shot=client(evidence,f'{theme}-{kind}-{state}',m)
                base=surface if kind=='stepper' else surface2
                fill=surface2 if kind=='ghost' else surface
                if state=='hover' and kind=='stepper':fill=surface2
                if state=='pressed':fill='#e7e6e1' if theme=='light' else '#313136'
                expected=blend(base,fill,.4) if state=='disabled' else rgb(fill)
                actual=shot.getpixel((x+(8 if kind=='stepper' else 5),y+h//2))
                # Find an un-antialiased glyph interior inside the text box.
                ink=secondary if kind=='ghost' and state not in ('hover','pressed') else text
                want_ink=blend(base,ink,.4) if state=='disabled' else rgb(ink)
                pixels=list(shot.crop((x+10,y+8,r-10,b-8)).getdata())
                assert want_ink in pixels,(theme,kind,state,'ink',want_ink)
                row=dict(theme=theme,control=kind,state=state,fill=hx(actual),expected_fill=hx(expected),
                         text=hx(want_ink),expected_text=hx(want_ink))
                assert actual==expected,row
                if state=='focus':
                    row['ring']=hx(shot.getpixel((x+w//2,y+(2 if kind=='stepper' else 1))));assert row['ring']==accent,row
                if kind=='stepper':
                    border=blend(fill,line,.13*(.4 if state=='disabled' else 1))
                    row['border']=hx(shot.getpixel((x+4,y+h//2)));row['expected_border']=hx(border)
                    assert row['border']==row['expected_border'],row
                result['states'].append(row)
        body=json.loads((evidence/f'body-{theme}.json').read_text());ox,oy=body['origin']
        crop=im.crop((ox,oy,ox+body['page'][0],oy+body['page'][1]))
        assert rgb(text) in list(crop.getdata())
        result['colours'][theme]['body_text']=text
        result['colours'][theme]['contrast']=contrast(rgb(bg),rgb(text))
        assert result['colours'][theme]['contrast']>=12
    fonts=[json.loads(p.read_text()) for p in evidence.glob('font-*.json')]
    before=json.loads((evidence/'font-before.json').read_text())
    def first(m):
        start,end=m['lines'][0][:2];return m['text'].encode()[start-m['range'][0]:end-m['range'][0]].decode()
    result['font_steps']=sorted({m['font'] for m in fonts})
    result['first_line_start_offsets']=sorted({m['lines'][0][0] for m in fonts})
    # Changing measure changes line length; preserve the first line's starting text.
    result['first_line_prefix_preserved']=all(first(m).startswith(first(before)[:12]) for m in fonts)
    assert result['font_steps']==[14,15,16,17,18,20,22,24,28,32]
    assert result['first_line_prefix_preserved']
    saved=json.loads((evidence/'saved.json').read_text());result['saved']=saved
    before_ini=(data/'host.ini').read_text();(out/'host-before-restart.ini').write_text(before_ini)
    run(exe,font,'settings_measure|restarted\nquit\n',data,out/'restart')
    after=json.loads((out/'restart/restarted.json').read_text());result['restart']={'font':after['font'],'theme':after['theme']}
    assert (after['font'],after['theme'])==(saved['font'],saved['theme'])
    (out/'host-after-restart.ini').write_text((data/'host.ini').read_text())
    trace=[l.split(',') for l in (evidence/'paint.csv').read_text().splitlines()]
    result['animation_ms']=[float(l[2]) for l in trace if l[0]=='settings_animation_ms']
    assert result['animation_ms'] and set(result['animation_ms'])=={0}
    result['dark_presented']=sum(l[0]=='dark_presented' for l in trace)
    result['presented']=sum(l[0]=='presented' for l in trace);result['blank']=sum(l[0]=='blank' for l in trace)
    assert result['presented']>0 and result['blank']==0
    result.update(remaining(exe,baseline,font,book,out))
    from check_font_anchors import check
    result['font_anchors']=check(exe,font,out/'font-anchors')
    result['pass']=result['nonzero_head_preserved'] and result['font_anchors']['pass_']
    dump(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['pass'] else 1

if __name__=='__main__':sys.exit(main())
