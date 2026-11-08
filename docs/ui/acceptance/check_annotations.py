#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Production HWND annotations acceptance. Screenshots use ops/capture_window.py.
Usage: check_annotations.py EXE SERIF_FONT OUTPUT
"""
import hashlib,json,os,sys
from pathlib import Path
from check_selection import launch_capture,shot,ptr,read
from check_step5 import run,dump
ROOT=Path(__file__).resolve().parents[3]

def setup(title='紅樓夢',chapter=True):
    s=f'open|{title}\nwait_idle\nshell|on\nshell_dpi|96\nshell_client|1280|800\nshell_font|18\nwait_idle\nshell_click|light\n'
    if chapter:s+='shell_click|toc\nprobe_wait|230\ntoc_click|1\nwait_idle\n'
    return s

def select(start,end):
    return 'annot_close\nselect_key|escape\n'+ptr('down',start)+ptr('move',end,1)+ptr('up',end,1)

def main():
    exe,font,out=[Path(x).resolve() for x in sys.argv[1:]];out.mkdir(parents=True,exist_ok=True)
    profile=out/'profile';store=out/'store';os.environ['EXREADER_ANNOTATIONS_DIR']=str(store)
    books={b['id']:b for b in read(ROOT/'tools/regress/corpus.json')['books']};hong=books['hongloumeng-24264']
    def launch(script,name,shots=(),title='紅樓夢',chapter=True,p=profile):
        folder=out/name
        launch_capture(exe,font,script,p,folder,shots)
        return folder
    discover=launch(f'import|{hong["path"]}\n'+setup()+'shell_page|10\nwait_idle\nshell_measure|base\nnext\nwait_idle\nshell_measure|next\nquit\n','discover')
    meta=read(discover/'base.json');following=read(discover/'next.json')
    ranges=[]
    for line in meta['lines'][:8]:
        glyphs=meta['glyphs'][line[2]:line[2]+line[3]]
        glyphs=[g for g in glyphs if not g[7]&(4|2048)]
        ranges.append((glyphs[1][8],glyphs[min(10,len(glyphs)-2)][8]))
    script=setup()+f'annotgoto|1|{meta["range"][0]}\nwait_idle\n'
    for i,(start,end) in enumerate(ranges):
        script+=select(start,end)
        if i<5:script+=f'annot_command|{3+i%3}\n'
        else:
            script+='annot_command|6\n'+f'annot_edit|笔记 {i-4}：原文与锚点|{i%3}|preview\n'
            if i==5:script+=shot('note-input')
            script+=f'annot_edit|笔记 {i-4}：原文与锚点|{i%3}\n'
    script+='annot_close\nselect_key|escape\nannot_dump|created\n'+shot('three-colors')+'quit\n'
    created=launch(script,'create',('note-input','three-colors'));before=read(created/'created.annotations.json')
    assert before['count']==8 and all(x['found'] and x['visible'] for x in before['items']),before
    assert sum(bool(x['text']) for x in before['items'])==3
    assert sum(x['marker'][0] for x in before['items'])==3
    expected=[(x['start'],x['end']) for x in before['items']]
    def verify(folder,name,count=8):
        value=read(folder/(name+'.annotations.json'));assert value['count']==count,value
        if count==8:assert [(x['start'],x['end']) for x in value['items']]==expected and all(x['found'] for x in value['items']),value
        return value
    script=setup()+f'annotgoto|1|{meta["range"][0]}\nwait_idle\nannot_dump|restored\n'+shot('restored')
    for size in (24,18):script+=f'shell_font|{size}\nwait_idle\nannot_dump|size-{size}\n'+shot(f'size-{size}')
    sans=Path('C:/Windows/Fonts/msyh.ttc')
    for label,path in [('sans',sans),('serif',font)]:
        script+=f'annotfont|{path}\nwait_idle\nannot_dump|{label}\n'+shot(label)
    # Open the actual 6px marker, edit through native EDIT + Save.
    script+='annot_pick|5|marker\nannot_edit|编辑后的笔记 😀|2\nannot_close\nannot_dump|edited\nquit\n'
    restored=launch(script,'restore',('restored','size-24','size-18','sans','serif'))
    for name in ('restored','size-24','size-18','sans','serif'):
        assert all(x['visible'] for x in verify(restored,name)['items'])
    assert verify(restored,'edited')['items'][5]['text']=='编辑后的笔记 😀'
    # A separate cross-page annotation spans exactly the next viewport boundary.
    g=[g for g in meta['glyphs'] if not g[7]&(4|2048)];start=g[-9][8]
    g=[g for g in following['glyphs'] if not g[7]&(4|2048)];end=g[8][8]
    script=setup()+f'annotgoto|1|{meta["range"][0]}\nwait_idle\nannot_close\nselect_key|escape\n'+ptr('down',start)+ptr('move',start,1)+'select_edge\nwait_idle\n'+ptr('move',end,1)+ptr('up',end,1)+'annot_command|4\nannot_close\nannot_dump|cross-right\n'+shot('cross-right')+'prev\nwait_idle\nannot_dump|cross-left\n'+shot('cross-left')+'annot_pick|8\nannot_command|7\nannot_dump|deleted-left\n'+shot('deleted-left')+'next\nwait_idle\nannot_dump|deleted-right\n'+shot('deleted-right')+'quit\n'
    cross=launch(script,'cross',('cross-right','cross-left','deleted-left','deleted-right'))
    for name in ('cross-left','cross-right'):
        value=verify(cross,name,9);assert value['items'][8]['visible'],value
    verify(cross,'deleted-left');verify(cross,'deleted-right')
    # Vertical book: two selections in separate columns.
    vertical=books['kusamakura-japanese-vertical-writing'];vp=out/'vertical-profile'
    vd=launch(f'import|{vertical["path"]}\n'+setup('草枕',False)+'shell_page|5\nwait_idle\nshell_measure|base\nquit\n','vertical-discover',p=vp)
    vm=read(vd/'base.json');assert vm['mode']==1
    script=setup('草枕',False)+f'annotgoto|{vm["part"]}|{vm["range"][0]}\nwait_idle\n'
    for i,line in enumerate(vm['lines'][:2]):
        glyphs=vm['glyphs'][line[2]:line[2]+line[3]];glyphs=[g for g in glyphs if not g[7]&(4|2048)]
        script+=select(glyphs[1][8],glyphs[min(8,len(glyphs)-1)][8])+f'annot_command|{3+i}\n'
    script+='annot_close\nselect_key|escape\nannot_dump|vertical\n'+shot('vertical')+'quit\n'
    vert=launch(script,'vertical',('vertical',),p=vp);v=verify(vert,'vertical',2)
    assert all(x['found'] and x['visible'] for x in v['items'])
    vr=launch(setup('草枕',False)+f'annotgoto|{vm["part"]}|{vm["range"][0]}\nwait_idle\nannot_dump|vertical-restored\n'+shot('vertical-restored')+'quit\n','vertical-restore',('vertical-restored',),p=vp)
    vv=verify(vr,'vertical-restored',2);assert [(x['start'],x['end']) for x in v['items']]==[(x['start'],x['end']) for x in vv['items']]
    # Source rename/import into another library retains the identical raw-byte key.
    moved=out/'moved.epub';moved.write_bytes(Path(hong['path']).read_bytes())
    mp=out/'moved-profile';mf=launch(f'import|{moved}\n'+setup()+'annot_dump|moved\nquit\n','moved',p=mp)
    assert verify(mf,'moved')['book_sha256']==before['book_sha256']==hashlib.sha256(moved.read_bytes()).hexdigest()
    files=list(store.glob('*.json'));assert len(files)==2
    source=next(p for p in files if p.stem==before['book_sha256'])
    (out/'sample.json').write_bytes(source.read_bytes())
    result=dict(restore='8/8',font_sizes='8/8 at 18→24→18',font_families='8/8 at serif→Microsoft YaHei→serif',cross_page='2/2 views; delete 2/2',vertical='2/2',notes='3/3 markers; marker open/edit 1/1',moved='8/8 same SHA-256 in separate library',ranges=expected,book_sha256=before['book_sha256'])
    dump(out/'result.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
