#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Step-5 regression on the original real HLM (no generated EPUBs).
Usage: check_step6_regression.py EXE BASELINE FONT HONGLOUMENG REAL_PDF PACHINKO OUT
"""
import json,sys,os,ctypes as C,subprocess,shutil,io,contextlib,urllib.request,hashlib
from pathlib import Path
from PIL import Image,ImageChops
from check_step5 import run,dump,client,rgb,hx,blend,contrast,U,HIDDEN
from check_toc_panel import read,trace,open_book

def main():
    exe,baseline,font,book,pdf,coverbook,out=(Path(x).resolve() for x in sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
    result={};dest=out/'settings'
    s=open_book(book,'紅樓夢')+'shell_click|toc\nprobe_wait|230\ntoc_click|8\nwait_idle\nprobe_wait|230\nprobe_key\nwait_idle\nshell_click|settings\nprobe_wait|230\n'
    for theme in ('light','dark'):
        s+=f'shell_click|{theme}\nwait_idle\nsettings_measure|{theme}\nshell_measure|body-{theme}\nsnapshot|{theme}\n'
        for kind,control in (('stepper','plus'),('ghost','system'),('primary',theme)):
            for state in ('normal','hover','pressed','focus','disabled'):
                s+=f'shell_enable|{control}|1\nshell_press|{control}|0\nshell_hover|none\nshell_render_focus|none\nui_cues|hide\n'
                if state in ('hover','pressed'):s+=f'shell_hover|{control}\n'
                if state=='pressed':s+=f'shell_press|{control}|1\n'
                if state=='focus':s+=f'ui_cues|show\nshell_render_focus|{control}\n'
                if state=='disabled':s+=f'shell_enable|{control}|0\n'
                s+=f'snapshot|{theme}-{kind}-{state}\nshell_enable|{control}|1\nshell_press|{control}|0\n'
    s+='shell_hover|none\nshell_render_focus|none\nshell_click|settings\nwait_idle\n'
    s+='probe_key\n'*20+'wait_idle\nshell_font|28\nwait_idle\nshell_click|dark\nsettings_measure|saved\nquit\n'
    old=C.c_int();assert U.SystemParametersInfoW(0x1042,0,C.byref(old),0)
    try:
        assert U.SystemParametersInfoW(0x1043,0,None,0)
        run(exe,font,s,out/'profile',dest,timeout_seconds=180)
    finally:assert U.SystemParametersInfoW(0x1043,0,C.c_void_p(old.value),0)
    colors={};states=[]
    for theme in ('light','dark'):
        m=read(dest,theme);im=client(dest,theme,m)
        bg,surface,text,secondary,line,accent=('#f5f5f2','#ffffff','#1b1b1f','#5c5c65','#141420','#4553e0') if theme=='light' else ('#141416','#1e1e21','#f2f2f4','#b3b3bc','#ffffff','#7c88ff')
        surface2='#efeeea' if theme=='light' else '#28282c'
        assert im.getpixel((8,300))==rgb(bg) and im.getpixel((m['panel'][2]-20,m['panel'][1]+50))==rgb(surface)
        colors[theme]={'bg':bg,'surface':surface,'contrast':contrast(rgb(bg),rgb(text))}
        body=read(dest,'body-'+theme);ox,oy=body['origin'];assert rgb(text) in list(im.crop((ox,oy,ox+body['page'][0],oy+body['page'][1])).getdata())
        for kind,control in (('stepper','plus'),('ghost','system'),('primary',theme)):
            x,y,r,b=m['controls'][control];w,h=r-x,b-y
            for state in ('normal','hover','pressed','focus','disabled'):
                shot=client(dest,f'{theme}-{kind}-{state}',m);base=surface if kind=='stepper' else surface2
                fill=surface2 if kind=='ghost' else surface
                if state=='hover' and kind=='stepper':fill=surface2
                if state=='pressed':fill='#e7e6e1' if theme=='light' else '#313136'
                expected=blend(base,fill,.4) if state=='disabled' else rgb(fill)
                actual=shot.getpixel((x+(8 if kind=='stepper' else 5),y+h//2));assert actual==expected,(theme,kind,state,actual,expected)
                ink=secondary if kind=='ghost' and state not in ('hover','pressed') else text
                want=blend(base,ink,.4) if state=='disabled' else rgb(ink)
                assert want in list(shot.crop((x+10,y+8,r-10,b-8)).getdata())
                if state=='focus':assert shot.getpixel((x+w//2,y+(2 if kind=='stepper' else 1)))==rgb(accent)
                if kind=='stepper':assert shot.getpixel((x+4,y+h//2))==blend(fill,line,.13*(.4 if state=='disabled' else 1))
                states.append({'theme':theme,'control':kind,'state':state,'rgb_error':0})
    result['1_colors']=colors;result['2_states']={'passed':len(states),'rows':states}
    frames=trace(dest);animations=[float(r[2]) for r in frames if r[0]=='settings_animation_ms'];assert animations and set(animations)=={0}
    result['3_reduced_motion_ms']=animations;result['4_contrast']={k:v['contrast'] for k,v in colors.items()}
    assert all(x>=12 for x in result['4_contrast'].values())
    assert not any(r[0]=='blank' for r in frames);result['5_frames']={'blank':0,'presented':sum(r[0]=='presented' for r in frames)}
    saved=read(dest,'saved');run(exe,font,'settings_measure|restarted\nquit\n',out/'profile',out/'restart')
    restarted=read(out/'restart','restarted');assert (saved['font'],saved['theme'])==(restarted['font'],restarted['theme'])==(28,1)
    result['6_restart']={'font':28,'theme':1}
    # Real reflow and real fixed-page inputs for the original 26-check self-test.
    st=out/'selftest';st.mkdir(exist_ok=True)
    # The original self-test explicitly requires text on page zero; an EPUB
    # cover cannot satisfy that. Use Gutenberg's complete, unmodified text edition.
    source='https://www.gutenberg.org/ebooks/24264.txt.utf-8';textbook=st/'hongloumeng-24264.txt'
    if not textbook.exists():urllib.request.urlretrieve(source,textbook)
    p=subprocess.run([str(exe),'--self-test',str(font),str(textbook),str(pdf),str(st/'report.json'),str(st/'page.png')],capture_output=True,creationflags=HIDDEN,timeout=120)
    assert p.returncode==0 and read(st,'report')['checks']==26,(p.returncode,p.stderr)
    result['7_selftest']={**read(st,'report'),'real_text_source':source,'text_sha256':hashlib.sha256(textbook.read_bytes()).hexdigest(),'fixed_book':pdf.name}
    # Exactly the original eight legacy screenshots, now using a real book.
    script=f'import|{book}\nwait_idle\nui_cues|hide\nsnapshot|01\nopen|紅樓夢\nwait_idle\nsnapshot|02\nprobe_key\nsnapshot|03\nprobe_key\nsnapshot|04\nsnapshot|05\nquit\n'
    for label,binary in [('baseline',baseline),('changed',exe)]:
        target=out/'legacy'/label
        run(binary,font,script,target/'profile',target/'A')
        run(binary,font,'wait_idle\nui_cues|hide\nsnapshot|10\nprobe_key\nsnapshot|11\nquit\n',target/'profile',target/'B')
        run(binary,font,'wait_idle\nui_cues|hide\nsnapshot|20\nquit\n',target/'profile',target/'C')
    from compare_shots import compare,self_test
    rows=[];count,failed=compare(out/'legacy/baseline',out/'legacy/changed',38,lambda *x:rows.append(' '.join(map(str,x))))
    (out/'legacy/comparison.txt').write_text('\n'.join(rows));assert count==8 and failed==0,(count,failed)
    capture=io.StringIO()
    with contextlib.redirect_stdout(capture):negative=self_test()
    assert negative==0;(out/'legacy/negative.txt').write_text(capture.getvalue())
    result['8_legacy_pixels']={'images':count,'changed_pixels':failed,'negative_exit':negative}
    # Two nonzero heads of the untouched real novel, each through all six sizes.
    anchors=[]
    for page in (5,20):
        target=out/'anchors'/str(page)
        s=open_book(book,'紅樓夢')+'shell_click|toc\nprobe_wait|230\ntoc_click|8\nwait_idle\nprobe_wait|230\n'
        s+=f'shell_page|{page}\nwait_idle\nshell_measure|before\n'
        for i,size in enumerate((18,20,22,24,28,32)):s+=f'shell_font|{size}\nwait_idle\nshell_measure|step-{i}\nsnapshot|step-{i}\n'
        s+='quit\n';run(exe,font,s,target/'profile',target,timeout_seconds=180)
        before=read(target,'before');head=before['lines'][0][0];original=before['text'].encode()[head-before['range'][0]:]
        for i,size in enumerate((18,20,22,24,28,32)):
            m=read(target,f'step-{i}');start,end,first,count=m['lines'][0][:4]
            glyphs=m['glyphs'][first:first+count];prefix=m['text'].encode()[start-m['range'][0]:end-m['range'][0]]
            assert start==head and min(g[0] for g in glyphs)==head and original.startswith(prefix),(page,size,head,start)
            anchors.append({'page':page,'font':size,'head':head,'pass':True})
    result['font_anchors']={'passed':len(anchors),'rows':anchors}
    dump(out/'result-partial.json',result)
    # Same-SDK baseline cover + keyboard outline, light/dark: exact client pixels.
    covers=[]
    for label,binary in [('baseline',baseline),('changed',exe)]:
        target=out/'cover'/label;s=open_book(coverbook,'PACHINKO')+'shell_page|1\nwait_idle\n'
        for theme in ('light','dark'):
            s+=f'shell_click|{theme}\nshell_render_focus|none\nui_cues|hide\nshell_measure|{theme}\nsnapshot|{theme}\nui_cues|show\nshell_render_focus|toc\nsnapshot|{theme}-focus\n'
        run(binary,font,s+'quit\n',target/'profile',target)
    for theme in ('light','dark'):
        m=read(out/'cover/changed',theme);image=m['image'];assert image[2]>image[0] and image[3]>image[1]
        for suffix in ('','-focus'):
            a=client(out/'cover/baseline',theme+suffix,read(out/'cover/baseline',theme));b=client(out/'cover/changed',theme+suffix,m)
            assert ImageChops.difference(a,b).getbbox() is None,(theme,suffix)
            if suffix:assert rgb('#4553e0' if theme=='light' else '#7c88ff') in list(b.crop((1194,8,1234,48)).getdata())
            covers.append({'theme':theme,'focus':bool(suffix),'pixel_difference':0,'image':image})
    result['cover_focus']={'passed':4,'rows':covers};result['pass']=True;dump(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
