#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real-book step-6 checks. Offscreen, DPI-aware PrintWindow; no desktop input.
Usage: check_toc_panel.py EXE BASELINE FONT HONGLOUMENG PACHINKO SHAKESPEARE OUT
The empty-book exception uses the existing no-TOC complex-text.epub fixture.
"""
import csv, ctypes as C, hashlib, json, os, shutil, subprocess, sys, time, zipfile, re
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageChops
from check_step5 import run, dump, client, hx, rgb, contrast, HIDDEN, U

# Must precede all Win32 coordinate queries, also in the imported runner.
assert U.SetThreadDpiAwarenessContext(C.c_void_p(-4))

def read(folder,name): return json.loads((folder/(name+'.json')).read_text(encoding='utf-8'))
def trace(folder): return list(csv.reader((folder/'paint.csv').read_text().splitlines()))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def open_book(book,title):
    return (f'import|{book}\nopen|{title}\nwait_idle\nshell|on\nshell_dpi|96\nshell_font|17\n'
            'shell_client|1280|800\nwait_idle\nshell_click|light\nui_cues|hide\n')

def main():
    exe,baseline,font,hong,pachinko,longbook,out=(Path(p).resolve() for p in sys.argv[1:])
    out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[3]
    result={'books':{str(p):sha(p) for p in (hong,pachinko,longbook)},'binary_sha256':sha(exe),'jumps':{}}
    # Five actual WM_LBUTTONDOWN/UP pairs in each book, SDK-owned page evidence.
    for slug,book,title,picks in [('hongloumeng',hong,'紅樓夢',[0,2,8,20,1]),('pachinko',pachinko,'PACHINKO',[6,17,28,42,7])]:
        assert len(set(picks))==5
        dest=out/slug;s=open_book(book,title)+'shell_measure|cover\nsnapshot|cover\n'
        s+='shell_click|toc\nprobe_wait|230\ntoc_measure|initial\n'
        for i,row in enumerate(picks):
            if i:s+='shell_click|toc\nprobe_wait|230\n'
            s+=f'toc_click|{row}\nwait_idle\nprobe_wait|230\ntoc_measure|jump-{i}\nshell_measure|page-{i}\nsnapshot|jump-{i}\n'
        s+='shell_measure|before-panel\nsnapshot|before-panel\nshell_click|toc\nprobe_wait|230\ntoc_scroll|0\ntoc_state|normal|0\n'
        for theme in ('light','dark'):
            s+=f'shell_click|{theme}\nui_cues|hide\nshell_render_focus|none\ntoc_measure|{theme}\nshell_measure|body-{theme}\nsnapshot|{theme}\n'
            for state,row in [('normal',0),('hover',3),('pressed',4)]:
                s+=f'toc_state|normal|0\ntoc_state|{state}|{row}\nsnapshot|{theme}-{state}\n'
            s+=f'toc_state|normal|0\ntoc_state|pressed|{picks[-1]}\nsnapshot|{theme}-selected-pressed\n'
            s+='toc_state|normal|0\ntoc_focus|list\ntoc_key|home\n'
            s+=f'snapshot|{theme}-focus\ntoc_state|normal|0\n'
        s+='shell_click|light\ntoc_state|normal|0\ntoc_scroll_hover\nsnapshot|scroll-hover\n'
        s+='toc_focus|list\ntoc_key|home\ntoc_measure|key-before\ntoc_key|down\ntoc_measure|key-down\ntoc_key|up\ntoc_measure|key-up\ntoc_key|down\ntoc_key|enter\nwait_idle\nprobe_wait|230\ntoc_measure|key-enter\n'
        s+='shell_click|toc\nprobe_wait|230\ntoc_key|escape\nprobe_wait|230\ntoc_measure|key-escape\n'
        s+='shell_click|toc\nprobe_wait|230\ntoc_focus|toc\n'
        for i in range(4):s+=f'toc_key|tab\ntoc_measure|tab-{i}\n'
        s+='toc_key|tab|1\ntoc_measure|shift-tab\ntoc_measure|outside-before\ntoc_outside\nprobe_wait|230\ntoc_measure|outside-after\n'
        s+='shell_click|toc\nprobe_wait|230\nshell_click|settings\nprobe_wait|230\ntoc_measure|exclusive\nshell_click|settings\nprobe_wait|230\n'
        s+='probe_key\n'*20+'wait_idle\ntoc_measure|twenty-pages\nsnapshot|twenty-pages\n'
        s+='shell_click|toc\nprobe_wait|230\ntoc_measure|wheel-before\ntoc_wheel_outside|-1\nprobe_wait|100\nwait_idle\ntoc_measure|wheel-after\ntoc_busy|1\nprobe_wait|500\nwait_idle\ntoc_measure|busy-after\nquit\n'
        run(exe,font,s,dest/'profile',dest,timeout_seconds=180)
        initial=read(dest,'initial');rows=[]
        assert (initial['width'],initial['row_height'],initial['text_x'])==(280,34,20)
        # Independent original ZIP spine/fragment proof, rather than trusting UI labels.
        with zipfile.ZipFile(book) as z:
            container=ET.fromstring(z.read('META-INF/container.xml'))
            opf=container.find('.//{*}rootfile').get('full-path');package=ET.fromstring(z.read(opf));base=Path(opf).parent
            manifest={e.get('id'):str(base/e.get('href')).replace('\\','/') for e in package.findall('.//{*}manifest/{*}item')}
            spine=[manifest[e.get('idref')] for e in package.findall('.//{*}spine/{*}itemref')]
            # The public publication places the cover before the reading spine for this PG input.
            for i,row in enumerate(picks):
                landed=read(dest,f'jump-{i}');body=read(dest,f'page-{i}');entry=landed['rows'][row]
                assert landed['open']==0 and landed['current']==row and body['part']==entry['part'],(slug,row,landed['current'])
                text=body['text'];image=body['image']
                assert body['range'][0]<=entry['offset']<body['range'][1] or (body['range']==[0,0] and image[2]>image[0])
                if slug=='hongloumeng':
                    # Each recovered label must occur in the untouched EPUB's own paragraph text.
                    first=entry['label'].split()[0].split('\u3000')[0]
                    originals=[n for n in z.namelist() if n.endswith(('.html','.xhtml')) and
                               re.search(r'(?m)^[ \t\u3000]*'+re.escape(first),''.join(ET.fromstring(z.read(n)).itertext()))]
                    assert originals and first in text[:150],(first,text[:150])
                else:
                    path=spine[entry['part']];xml=ET.fromstring(z.read(path));original=' '.join(' '.join(xml.itertext()).split())
                    # Check a real phrase from the rendered target against its original spine item.
                    phrase=' '.join(text.split())[:80]
                    if phrase:assert phrase in original,(path,phrase)
                    else:assert xml.find('.//{*}img') is not None
                    ncx=ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.ncx'))))
                    href=ncx.findall('.//{*}navPoint')[row].find('{*}content').get('src').split('#')[0]
                    assert Path(href).name==Path(path).name,(href,path)
                rows.append({'row':row,'label':entry['label'],'part':body['part'],'offset':entry['offset'],'first_line':body['lines'][0][0] if body['lines'] else None,'image':image,'pass':True})
        result['jumps'][slug]=rows
        for theme in ('light','dark'):
            m=read(dest,'body-'+theme);im=client(dest,theme,m)
            surface,line,accent,selected,hover,pressed=('#ffffff','#ededee','#4553e0','#f4f5fd','#efeeea','#e7e6e1') if theme=='light' else ('#1e1e21','#2f2f32','#7c88ff','#262835','#28282c','#313136')
            assert all(im.getpixel((279,y))==rgb(line) for y in range(56,800))
            assert all(im.getpixel((x,102))==rgb(line) for x in range(279))
            bg='#f5f5f2' if theme=='light' else '#141416'
            assert all(im.getpixel((x,y))==rgb(bg) for x in range(280,290) for y in range(56,800))
            selectedrow=read(dest,theme)['current'];y=111+selectedrow*34+17
            assert im.getpixel((10,y))==rgb(accent) and im.getpixel((11,y))==rgb(accent),(slug,theme,y,im.getpixel((10,y)))
            assert im.getpixel((12,y))==rgb(selected)
            # Beyond the text, the exact solid background and inward focus are sampled.
            for state,row,color in [('normal',0,surface),('hover',3,hover),('pressed',4,pressed)]:
                shot=client(dest,f'{theme}-{state}',m);assert shot.getpixel((260,111+row*34+17))==rgb(color),(slug,theme,state,shot.getpixel((260,111+row*34+17)))
            focus=client(dest,theme+'-focus',m);assert focus.getpixel((10,128))==rgb(accent)
            pressed_selected=client(dest,theme+'-selected-pressed',m)
            assert pressed_selected.getpixel((12,y))==rgb('#eceefc' if theme=='light' else '#2d2f45')
        before=read(dest,'before-panel');a=client(dest,'before-panel',before);b=client(dest,'light',read(dest,'body-light'))
        assert ImageChops.difference(a.crop((351,96,929,736)),b.crop((351,96,929,736))).getbbox() is None
        # Counterexample: a one-pixel body mutation must be detected.
        neg=b.copy();q=neg.getpixel((600,400));neg.putpixel((600,400),((q[0]+1)%256,*q[1:]));assert ImageChops.difference(a.crop((351,96,929,736)),neg.crop((351,96,929,736))).getbbox()
        neg.save(dest/'negative-one-pixel.png')
        down,up,start=(read(dest,n) for n in ('key-down','key-up','key-before'))
        assert down['focus']==start['focus']+1 and up['focus']==start['focus']
        assert down['current']==up['current']==start['current'] and down['range']==up['range']==start['range']
        assert read(dest,'key-enter')['open']==0 and read(dest,'key-enter')['focus_target']=='page'
        assert read(dest,'key-escape')['open']==0 and read(dest,'key-escape')['focus_target']=='toc'
        tabs=[read(dest,f'tab-{i}')['focus_target'] for i in range(4)]
        assert tabs==['settings','list','page','toc'] and read(dest,'shift-tab')['focus_target']=='page'
        outsidebefore,outsideafter=read(dest,'outside-before'),read(dest,'outside-after')
        assert outsideafter['open']==0 and outsidebefore['range']==outsideafter['range'] and outsidebefore['part']==outsideafter['part']
        assert read(dest,'exclusive')['open']==0
        wheel_before,wheel_after=read(dest,'wheel-before'),read(dest,'wheel-after')
        assert wheel_after['open']==1 and (wheel_before['range'],wheel_before['part'])!=(wheel_after['range'],wheel_after['part'])
        assert read(dest,'busy-after')['open']==0 and read(dest,'busy-after')['current']==1
        frames=trace(dest);assert sum(r[0]=='blank' for r in frames)==0
        result[slug]={'toc_count':initial['count'],'keyboard_passes':4,'tab_order':tabs,'blank':0,'presented':sum(r[0]=='presented' for r in frames),'closed_children':read(dest,'twenty-pages')['children']}
        result[slug]['geometry']={'width':initial['width'],'row_height':initial['row_height'],'text_x':initial['text_x'],'border_width':1,'themes_rgb_error':0,'selection_bar_width':2,'selected_weight':read(dest,'dark')['typography'][3],'body_pixel_difference':0}
        assert result[slug]['closed_children']==3
        dump(out/'result-partial.json',result)
    # Long list: the unmodified real Shakespeare EPUB has 1169 authored nav rows.
    dest=out/'long';s=open_book(longbook,'The Complete Works')+'shell_click|toc\nprobe_wait|230\ntoc_measure|open\nshell_measure|body\nsnapshot|open\n'
    for i in range(80):s+='toc_wheel|-1\nprobe_wait|25\n'
    s+='toc_scroll_hover\nsnapshot|hover\ntoc_key|end\ntoc_measure|end\nsnapshot|end\nquit\n'
    run(exe,font,s,dest/'profile',dest,timeout_seconds=120)
    frames=[float(r[2]) for r in trace(dest) if r[0]=='toc_frame_ms'];p95=sorted(frames)[int(.95*(len(frames)-1))]
    assert read(dest,'open')['count']>=500 and p95<=4,(len(frames),p95)
    m=read(dest,'body');im=client(dest,'open',m);thumb=[x for x in range(268,279) if im.getpixel((x,120))==rgb('#e0e0e2')]
    assert thumb==[271,272,273,274,275],thumb
    hover=client(dest,'hover',m)
    hotys=[y for y in range(105,798) if hover.getpixel((273,y))==rgb('#8b8b94')];assert hotys
    hoty=hotys[len(hotys)//2];assert [x for x in range(268,279) if hover.getpixel((x,hoty))==rgb('#8b8b94')]==thumb
    assert all(im.getpixel((x,500))==rgb('#ffffff') for x in range(269,279))
    assert im.getpixel((271,105))==rgb('#ffffff') and im.getpixel((273,105))!=rgb('#ffffff')
    result['long']={'count':read(dest,'open')['count'],'frames':len(frames),'scroll_p95_ms':p95,'thumb_columns':thumb,'width':5,'hover_width':5,'hover_color':'#8b8b94','transparent_track':True}
    # Explicitly permitted existing fixture, with no navigation resource.
    dest=out/'empty';empty=root/'tests/fixtures/complex-text.epub'
    # Use the OPF title instead of inventing a test book.
    with zipfile.ZipFile(empty) as z:
        opf=next(n for n in z.namelist() if n.endswith('.opf'));title=ET.fromstring(z.read(opf)).find('.//{*}title').text
    s=open_book(empty,title)+'shell_click|toc\nprobe_wait|230\nshell_measure|body\nsnapshot|empty\ntoc_measure|empty\ntoc_key|escape\nprobe_wait|230\nquit\n'
    run(exe,font,s,dest/'profile',dest)
    assert read(dest,'empty')['count']==0
    assert read(dest,'empty')['typography'][:2]==[16,650],read(dest,'empty')['typography']
    result['empty']={'text':'这本书没有目录','font':16,'weight':650,'count':0,'fixture':str(empty.relative_to(root))}
    dump(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
