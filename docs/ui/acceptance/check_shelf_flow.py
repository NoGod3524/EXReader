#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shelf/reading interaction acceptance against the real Win32 HWND handlers.
Usage: check_shelf_flow.py EXE FONT OUTPUT
Screenshots are captured exclusively by ops/capture_window.py.
"""
import hashlib,json,os,sys
from pathlib import Path
from check_selection import launch_capture,shot,ptr,read
from check_step5 import dump
ROOT=Path(__file__).resolve().parents[3]

def main():
    exe,font,out=(Path(x).resolve() for x in sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
    profile=out/'profile';os.environ['EXREADER_ANNOTATIONS_DIR']=str(out/'annotations')
    corpus={b['id']:b for b in read(ROOT/'tools/regress/corpus.json')['books']}
    def launch(script,name,shots=(),p=profile):
        folder=out/name;launch_capture(exe,font,script,p,folder,shots);return folder
    def state(folder,name):return read(folder/(name+'.state.json'))
    def same(a,b):return all(a[k]==b[k] for k in ('book','part','page','range','raster_fnv'))
    setup='shell|on\nshell_dpi|96\nshell_client|1280|800\nshell_font|18\nwait_idle\nshell_click|light\n'
    s=setup+'shelf_dump|empty\n'
    for key in ('hongloumeng-24264','a-raisin-in-the-sun','between-the-world-and-me'):
        s+=f'import|{corpus[key]["path"]}\nwait_idle\n'
    # Open each actual book, advance, and return; records carry real nonzero progress.
    for title in ('A Raisin in the Sun','Between the World and Me','紅樓夢'):
        s+=f'open|{title}\nwait_idle\nshell_page|20\nwait_idle\nshelf_return\nwait_idle\n'
    s+=shot('shelf')+'shelf_dump|shelf\nshelf_open|0\nwait_idle\nshelf_dump|initial\n'
    for i,method in enumerate(('button','escape','ctrlw')):
        s+=f'shelf_return|{method}\nwait_idle\nshelf_dump|out-{i}\nshelf_open|0\nwait_idle\nshelf_dump|in-{i}\n'
    s+=shot('reading')+'gesture_tap|50\nshelf_dump|hidden\n'+shot('hidden')+'gesture_tap|50\ngesture_overlay|1\n'+shot('regions')+'gesture_overlay|0\n'
    for edge in (25,20):
        s+=f'gesture_ratio|{edge}\nshelf_dump|ratio-{edge}\n'
        for zone,pct in [('left',10),('right',90),('center',50)]:
            for i in range(5):s+=f'gesture_tap|{pct}\nwait_idle\nshelf_dump|tap-{edge}-{zone}-{i}\n'
    # Ten independent single clicks (right zone), then ten swipes each way.
    s+='shelf_dump|single-base\n'
    for i in range(10):s+=f'gesture_tap|90\nwait_idle\nshelf_dump|single-{i}\n'
    for direction,dx in [('left',-120),('right',120)]:
        for i in range(10):s+=f'gesture_swipe|{dx}\nwait_idle\nshelf_dump|swipe-{direction}-{i}\n'
    s+='shelf_dump|rapid-base\n'
    for i in range(2):
        s+='gesture_pointer|double|1152|8\ngesture_pointer|up|1152|8\nwait_idle\n'+f'shelf_dump|rapid-{i}\n'
    s+='shell_measure|select-base\nshelf_dump|before-restart\nquit\n'
    f=launch(s,'flow',('shelf','reading','hidden','regions'))
    initial=state(f,'initial');assert initial['reading']==1 and initial['books']==3
    assert state(f,'empty')['shelf']==1 and state(f,'empty')['books']==0
    for i in range(3):
        assert state(f,f'out-{i}')['shelf']==1
        assert same(initial,state(f,f'in-{i}')),(initial,state(f,f'in-{i}'))
        assert initial['builds']==state(f,f'in-{i}')['builds']
    assert state(f,'hidden')['bar_hidden']==1 and same(initial,state(f,'hidden'))
    previous=initial;tap_count={}
    for edge in (25,20):
        count=0;previous=state(f,f'ratio-{edge}')
        for zone,delta in [('left',-1),('right',1),('center',0)]:
            for i in range(5):
                current=state(f,f'tap-{edge}-{zone}-{i}');assert current['edge']==edge
                assert current['part']==previous['part'] and current['page']==previous['page']+delta,(zone,previous,current)
                if zone=='center':assert current['bar_hidden']==1-previous['bar_hidden'] and same(previous,current)
                else:assert current['range']!=previous['range']
                assert current['builds']==previous['builds'];previous=current;count+=1
        tap_count[str(edge)]=f'{count}/15'
    previous=state(f,'single-base')
    for i in range(10):
        current=state(f,f'single-{i}');assert current['page']==previous['page']+1 and not current['selection'];previous=current
    for direction,delta in [('left',1),('right',-1)]:
        for i in range(10):
            current=state(f,f'swipe-{direction}-{i}');assert current['page']==previous['page']+delta and current['part']==previous['part'];previous=current
    previous=state(f,'rapid-base')
    for i in range(2):
        current=state(f,f'rapid-{i}');assert current['page']==previous['page']+1 and not current['selection'];previous=current
    # Fresh process: do not use a goto/page index before checking the restored anchor.
    r=launch('wait_idle\n'+setup+'shelf_dump|restart\nquit\n','restart');assert same(state(f,'before-restart'),state(r,'restart')),(state(f,'before-restart'),state(r,'restart'))
    assert state(r,'restart')['edge']==20
    meta=read(f/'select-base.json');line=meta['lines'][2];glyphs=[g for g in meta['glyphs'][line[2]:line[2]+line[3]] if not g[7]&(4|2048)]
    start,end=glyphs[1][8],glyphs[min(12,len(glyphs)-2)][8]
    s=setup+'shelf_dump|drag-base\n'
    for i in range(10):
        s+=ptr('down',start)+ptr('move',end,1)+ptr('up',end,1)+f'shelf_dump|drag-{i}\nselect_key|escape\n'
    # Unsaved native EDIT draft: returning by Ctrl+W must invoke Save before hiding.
    s+=ptr('down',start)+ptr('move',end,1)+ptr('up',end,1)+'annot_command|6\nannot_edit|退出前尚未按保存的笔记 😀|2|preview\nshelf_return|ctrlw\nwait_idle\nshelf_dump|draft-out\nshelf_open|0\nwait_idle\nannot_dump|draft-saved\nquit\n'
    d=launch(s,'selection')
    for i in range(10):assert state(d,f'drag-{i}')['selection']==1 and same(state(d,'drag-base'),state(d,f'drag-{i}'))
    assert state(d,'draft-out')['shelf']==1
    a=read(d/'draft-saved.annotations.json');assert a['count']==1 and a['items'][0]['text']=='退出前尚未按保存的笔记 😀' and a['items'][0]['found']
    # New process also reloads the note from the flushed JSON file.
    n=launch(setup+'annot_dump|note-restart\nshelf_return\nwait_idle\nquit\n','note-restart')
    note=read(n/'note-restart.annotations.json');assert note['items'][0]['text']==a['items'][0]['text']
    recent=read(profile/'recent-books.json');assert len(recent['books'])==3
    assert all(b['path'] and len(b['cover_hash'])==64 and b['anchor'] for b in recent['books'])
    def no_page(o):
        if isinstance(o,dict):
            assert not any(k in ('page','page_number','page_index') for k in o)
            for x in o.values():no_page(x)
        elif isinstance(o,list):
            for x in o:no_page(x)
    no_page(recent)
    # Application restarted after exiting book must display the shelf, without an open.
    t=launch(setup+'shelf_dump|startup\nquit\n','shelf-startup');assert state(t,'startup')['shelf']==1
    # Another title replaces the cached session; reopening still resolves the content point.
    s=setup+'shelf_open|0\nwait_idle\nshelf_dump|before\nshelf_return\nwait_idle\nshelf_open|1\nwait_idle\nshelf_dump|other\nshelf_return\nwait_idle\nshelf_open|1\nwait_idle\nshelf_dump|after\nquit\n'
    switch=launch(s,'switch-book')
    assert state(switch,'other')['book']!=state(switch,'before')['book']
    assert same(state(switch,'before'),state(switch,'after'))
    # Vertical-rl actual Kusamakura, five taps in each physical zone, five swipes each way.
    vp=out/'vertical-profile';vbook=corpus['kusamakura-japanese-vertical-writing']
    s=f'import|{vbook["path"]}\nwait_idle\nopen|草枕\nwait_idle\n'+setup+'shell_page|8\nwait_idle\nshell_measure|vertical\nshelf_dump|base\n'
    for name,pct in [('left',10),('right',90)]:
        for i in range(5):s+=f'gesture_tap|{pct}\nwait_idle\nshelf_dump|{name}-{i}\n'
    for name,dx in [('left',-120),('right',120)]:
        for i in range(5):s+=f'gesture_swipe|{dx}\nwait_idle\nshelf_dump|swipe-{name}-{i}\n'
    s+=shot('vertical')+'quit\n';v=launch(s,'vertical',('vertical',),p=vp)
    assert read(v/'vertical.json')['mode']==1;previous=state(v,'base')
    for name,delta in [('left',1),('right',-1),('swipe-left',-1),('swipe-right',1)]:
        for i in range(5):
            current=state(v,f'{name}-{i}');assert current['page']==previous['page']+delta,(name,previous,current);previous=current
    # A fixed-page source makes both whole-book bounds explicit, without spine ambiguity.
    fixed=ROOT/'tests/fixtures/comic.cbz';bp=out/'bounds-profile'
    s=f'import|{fixed}\nwait_idle\nopen|SDK Comic\nwait_idle\n'+setup+'shell_page|1\nwait_idle\nshelf_dump|first\n'
    for i in range(3):s+=f'gesture_swipe|120\nwait_idle\nshelf_dump|first-{i}\n'
    s+='shell_page|4\nwait_idle\nshelf_dump|last\n'
    for i in range(3):s+=f'gesture_swipe|-120\nwait_idle\nshelf_dump|last-{i}\n'
    s+='shelf_return\nwait_idle\nshelf_open|0\nwait_idle\nshelf_dump|fixed-cached\nquit\n'
    bounds=launch(s,'bounds',p=bp)
    for name in ('first','last'):
        for i in range(3):assert same(state(bounds,name),state(bounds,f'{name}-{i}'))
    assert same(state(bounds,'last'),state(bounds,'fixed-cached'))
    br=launch(setup+'shelf_dump|fixed-restored\nquit\n','fixed-restart',p=bp)
    assert same(state(bounds,'last'),state(br,'fixed-restored'))
    result=dict(roundtrips='3/3; same content range, page and raster; no pager rebuild',tap_zones=tap_count,
        single_clicks='10/10',drag_selection='10/10; long text drags never flip',swipes='20/20',
        vertical_taps='10/10',vertical_swipes='10/10 extra',unsaved_note='saved on Ctrl+W; verified after process restart',
        restart='1/1 identical content range/page/raster; open settles before shell activation',startup_shelf='1/1',uncached_reopen='1/1 after reading another title',shelf_books=3,
        screenshots=['flow/shelf.png','flow/reading.png','flow/hidden.png','flow/regions.png','vertical/vertical.png'],
        boundaries='6/6 ignored; fixed stable page-id restore 2/2',rapid_taps='2/2 DBLCLK gutter messages turn pages',capture='ops/capture_window.py',exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    dump(out/'result.json',result);dump(out/'recent-sample.json',recent);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
