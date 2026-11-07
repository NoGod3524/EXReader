#!/usr/bin/env python3
"""Ordinary positional-book startup, specified DLL, physical outer sizes.

Usage: check_real_exe.py EXE OWNER_EXE BOOK FONT ORIGINAL_CAPTURE_SCRIPT OUT
No --drive, harness, focus activation, or rewritten EPUB is involved.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image, ImageChops, ImageStat
from capture_window import U, window, capture
from check_step6_real import publication, sha

U.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
U.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]


def main():
    exe, owner, book, font, original_capture, out = [Path(p).resolve() for p in sys.argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    record = out/'record'; record.mkdir(exist_ok=True)
    original_sha = sha(book)
    assert original_sha == '325fef5fb561a258ee4e0ded25821a55d77f7b4b627ae0ecac03410802ea6ec7'
    source = publication(book)[3]
    result = dict(inputs={str(p):sha(p) for p in (exe,owner,book,font,exe.parent/'libexreader.dll')},
                  foreground_observations=0, images=[], rendering_behavior_changed=False)
    assert sha(exe.parent/'libexreader.dll') == sha(owner.parent/'libexreader.dll')
    reference = {}
    for label, binary in [('owner',owner), ('rebuilt',exe)]:
        profile = record/(label+'-profile'); profile.mkdir(exist_ok=True)
        (profile/'host.ini').write_text('[Host]\nWindowWidth=1552\nWindowHeight=928\nShellTheme=2\nShellFont=17\n')
        trace = record/(label+'-paint.csv')
        trace.write_text('')
        env = dict(os.environ, EXR_PAINT_TRACE=str(trace))
        p = subprocess.Popen([str(binary),'--offscreen','--data',str(profile),'--font',str(font),str(book)],
                             env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        def wait(seconds):
            end = time.monotonic()+seconds
            while time.monotonic()<end:
                found = W.DWORD(); U.GetWindowThreadProcessId(U.GetForegroundWindow(), C.byref(found))
                result['foreground_observations'] += found.value == p.pid
                assert p.poll() is None, p.returncode
                time.sleep(.02)
        try:
            wait(10)
            hwnd = window(p.pid)
            initial = record/(label+'-initial.png')
            initial_meta = capture(p.pid,initial)
            result[label+'_initial'] = initial_meta
            if label == 'owner':
                # Execute the user's exact unmodified script in an unaware child.
                wrong = out/'real-exe-before-1242x742.png'
                subprocess.run([sys.executable,'-X','utf8',str(original_capture),str(p.pid),str(wrong)],check=True)
                small,full = Image.open(wrong),Image.open(initial)
                assert ImageChops.difference(small,full.crop((0,0,*small.size))).getbbox() is None
                result['capture_reproducer'] = dict(sha256=sha(wrong),unaware=list(small.size),
                    physical=list(full.size),identical_to_top_left_crop=True)
                assert sha(wrong) == 'ff3f4377c652f2a94cba58d3328784bcded9115f926aa7ed25bf298a631e7478'
            for width,height,kind in [(1242,742,'outer'),(900,600,'outer'),(1280,800,'outer'),(1242,711,'client')]:
                if kind=='client':
                    r,c = W.RECT(),W.RECT()
                    U.GetWindowRect(hwnd,C.byref(r));U.GetClientRect(hwnd,C.byref(c))
                    outer_w,outer_h = width+r.right-r.left-c.right,height+r.bottom-r.top-c.bottom
                else:
                    outer_w,outer_h = width,height
                # At 125% DPI the interactive minimum is larger than 900x600.
                # Bypass WM_WINDOWPOSCHANGING's size clamp for the requested
                # physical viewport; WM_SIZE still runs the real reader path.
                assert U.SetWindowPos(hwnd,None,0,0,outer_w,outer_h,0x416) # NOSENDCHANGING|NOACTIVATE|NOZORDER|NOMOVE
                wait(2)
                name = f'real-exe-{width}x{height}'
                target = out/(name+'.png') if label=='rebuilt' and kind=='outer' else record/(label+'-'+name+'-'+kind+'.png')
                meta = capture(p.pid,target)
                assert meta['position']==[-32000,-32000]
                assert meta['window' if kind=='outer' else 'client']==[width,height],meta
                x,y,w,h = meta['client_box']; dpi = meta['dpi']
                px = lambda n:int(n*dpi/96+.5)
                top,bottom = px(96),h-px(64)
                shot = Image.open(target).convert('RGB').crop((x,y,x+w,y+h))
                area = shot.crop((0,top,w,bottom))
                channels = area.split()
                mask = ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2]).point(lambda v:255 if v>80 else 0)
                l,t,r,b = mask.getbbox();t+=top;b+=top
                dx,dy = abs((l+r-w)/2),abs((t+b-top-bottom)/2)
                assert dx<=1 and dy<=1,(meta,(l,t,r,b),dx,dy)
                assert t>=top and b<=bottom and l>0 and r<w
                assert abs((r-l)/(b-t)-source.width/source.height)<.01
                diff = ImageChops.difference(source.resize((r-l,b-t),Image.Resampling.BILINEAR),shot.crop((l,t,r,b)))
                mean = sum(ImageStat.Stat(diff).mean)/3
                edges = max(sum(ImageStat.Stat(diff.crop(box)).mean)/3 for box in
                    [(0,0,r-l,1),(0,b-t-1,r-l,b-t),(0,0,1,b-t),(r-l-1,0,r-l,b-t)])
                assert mean<6 and edges<12,(mean,edges)
                key = (width,height,kind)
                if label=='owner': reference[key] = shot.copy()
                else:
                    assert ImageChops.difference(reference[key],shot).getbbox() is None
                    events = [line.split(',') for line in trace.read_text().splitlines()]
                    first = lambda event:next(float(v) for e,_,v in events if e==event)
                    last = lambda event:next(float(v) for e,_,v in reversed(events) if e==event)
                    result['images'].append(dict(**meta,kind=kind,image=[l,t,r,b],body=[0,top,w,bottom],
                        horizontal_error_px=dx,vertical_error_px=dy,source_mean_rgb_error=mean,
                        source_edge_mean_rgb_error=edges,clipped=False,owner_pixel_difference=0,
                        heights=dict(open_geometry=first('open_shell_geometry_height'),
                            current_client=last('image_client_height'),fit_body=last('image_fit_body_height'))))
        finally:
            U.PostMessageW(window(p.pid),0x10,0,0)
            p.wait(timeout=15)
        assert p.returncode==0
    assert result['foreground_observations']==0
    assert sha(book)==original_sha
    result['pass'] = True
    (out/'real-exe-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
