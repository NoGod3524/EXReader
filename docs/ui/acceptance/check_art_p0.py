#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""P0 pixel/SDK measurements; all host runs are offscreen PrintWindow captures.

Usage: check_art_p0.py EXE FONT HONGLOUMENG OUT
The vertical input changes writing-mode CSS only. Original chapter text and
attributes are checked independently; no quotation marks are substituted.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageChops
from check_step5 import run, dump, client, rgb, hx, blend


def measure(folder, name):
    return json.loads((folder / (name+'.json')).read_text(encoding='utf-8'))


def lines(m):
    data=m['text'].encode()
    return [(line, data[line[0]-m['range'][0]:line[1]-m['range'][0]].decode()) for line in m['lines']]


def glyph(m, line):
    return [g for g in m['glyphs'][line[2]:line[2]+line[3]] if g[2] not in (32, 0x3000, 9, 10, 13)][0]


def main():
    exe,font,original,out=(Path(p).resolve() for p in sys.argv[1:])
    out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[3]
    spec=importlib.util.spec_from_file_location('fixtures',root/'tests/windows_host/make_fixtures.py')
    fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
    title='P0 mixed script charset measurement and ellipsis '+('Long title ' * 18)
    text='春日讀書，窗前有花。讀到「山水」，便想起遠方的朋友。'
    paragraphs=(f'</p><h2>章節標題</h2><p lang="en">甲段{text*2}</p>'
                '<p style="text-align:center">居中段</p>'
                f'<p lang="en" style="margin-top:1em">乙段{text*2}</p><blockquote><p>引文中的文字。</p></blockquote>'
                f'<p lang="en">丙段{text*2}</p>'
                '<p lang="zh">Latin words keep their line height and paragraph spacing. '
                'The language attribute intentionally disagrees with the actual characters. '
                'Reading letters has no first line indent.</p>'
                f'<p lang="en">混排Latin文字{text}</p><p>　　已有全角縮進{text}</p><p>')
    book=out/'Mixed-script.epub';fixtures.epub(book,title,paragraphs)
    opening=(f'import|{book}\nopen|P0 mixed script\nwait_idle\nshell|on\nshell_dpi|96\n'
             'shell_font|18\nshell_client|1280|1000\nwait_idle\nshell_click|light\nui_cues|hide\n')
    script=opening+'shell_measure|mixed-18\nsnapshot|mixed-18\nshell_font|17\nwait_idle\nshell_measure|mixed-17\n'
    script+='shell_font|18\nwait_idle\nshell_client|1280|800\nwait_idle\n'
    for theme in ('light','dark'):
        script+=f'shell_click|{theme}\nwait_idle\nsettings_measure|{theme}-bar\n'
        for state in ('normal','hover','pressed','focus','disabled'):
            script+='shell_enable|toc|1\nshell_press|toc|0\nshell_hover|none\nshell_render_focus|none\nui_cues|hide\n'
            if state in ('hover','pressed'):script+='shell_hover|toc\n'
            if state=='pressed':script+='shell_press|toc|1\n'
            if state=='focus':script+='ui_cues|show\nshell_render_focus|toc\n'
            if state=='disabled':script+='shell_enable|toc|0\n'
            script+=f'snapshot|{theme}-icon-{state}\n'
        script+='shell_enable|toc|1\nshell_press|toc|0\nshell_hover|none\nshell_render_focus|none\n'
        script+=f'shell_click|settings\nwait_idle\nui_cues|hide\nsettings_measure|{theme}-panel\nsnapshot|{theme}-panel\nshell_click|settings\nwait_idle\n'
    run(exe,font,script+'quit\n',out/'profile',out/'controls')
    dest=out/'controls';m=measure(dest,'mixed-18');rows=lines(m)
    cjk_rows=[line for line,s in rows if s.startswith(('甲段','乙段','丙段','混排'))]
    assert len(cjk_rows)==4,[(s[:20],line) for line,s in rows]
    # All three following-paragraph cases and the mixed-script paragraph.
    assert all(abs(glyph(m,l)[3]-36)<.001 for l in cjk_rows),cjk_rows
    assert all(abs(l[7]-32)<.001 for l in cjk_rows),cjk_rows
    latin=[(line,s) for line,s in rows if s.startswith(('Latin words','The language','Reading letters'))]
    assert latin and abs(latin[0][0][4])<.001 and abs(latin[0][0][7]-28.8)<.001,latin
    source_prefix=[line for line,s in rows if s.startswith('　　已有全角')]
    assert source_prefix and abs(glyph(m,source_prefix[0])[3]-36)<.001
    chinese_gap=[];latin_gap=[]
    for i,(line,s) in enumerate(rows[:-1]):
        next_line,next_text=rows[i+1]
        if next_text.startswith(('乙段','丙段','居中段','混排','　　已有全角')):
            gap=next_line[5]-line[5]-line[7]
            (latin_gap if next_text.startswith('混排') else chinese_gap).append(gap)
    assert chinese_gap and all(abs(v-9)<.001 for v in chinese_gap),chinese_gap
    assert latin_gap and all(abs(v-14.4)<.001 for v in latin_gap),latin_gap
    seventeen=measure(dest,'mixed-17')
    assert all(abs(l[7]-30)<.001 for l,s in lines(seventeen) if s.startswith(('甲段','乙段','丙段','混排')))
    result={'cjk':{'font18_leading':32,'font17_leading':30,'indent':36,'paragraph_gaps':chinese_gap,
                   'following_paragraph_cases':3,'mixed_script_indent':36,'authored_prefix_indent':36},
            'latin':{'leading':latin[0][0][7],'indent':latin[0][0][4],'paragraph_gaps':latin_gap},'icons':[],'panels':{}}
    for theme in ('light','dark'):
        bar=measure(dest,theme+'-bar');panel=measure(dest,theme+'-panel')
        surface,bg,secondary,ink,s2,s3,accent,line=(
            ('#ffffff','#f5f5f2','#5c5c65','#1b1b1f','#efeeea','#e7e6e1','#4553e0','#141420') if theme=='light' else
            ('#1e1e21','#141416','#b3b3bc','#f2f2f4','#28282c','#313136','#7c88ff','#ffffff'))
        normal=client(dest,theme+'-icon-normal',bar)
        assert hx(normal.getpixel((8,20)))==surface
        assert hx(normal.getpixel((8,300)))==bg
        assert hx(normal.getpixel((8,55)))==hx(blend(surface,line,.075))
        toc=bar['icons']['toc'];settings=bar['icons']['settings'];x,y,r,b=toc
        assert [r-x,b-y,settings[0]-r,1280-settings[2]]==[32,32,6,12]
        assert bar['typography']==[15,650,13,550,12,550,20,-.15],bar
        # Actual raster ink begins at the specified x=20 title origin.
        title_ink=[xx for yy in range(8,48) for xx in range(0,x-10) if normal.getpixel((xx,yy))==rgb(ink)]
        assert min(title_ink)==22,min(title_ink)
        assert sum(normal.getpixel((xx,y+16))!=rgb(surface) for xx in range(x,r))==18
        stroke=sum((rgb(surface)[0]-normal.getpixel((x+16,yy))[0])/(rgb(surface)[0]-rgb(secondary)[0]) for yy in range(y+13,y+20))
        assert abs(stroke-1.5)<.01,stroke
        for state in ('normal','hover','pressed','focus','disabled'):
            im=client(dest,f'{theme}-icon-{state}',bar)
            fill=s2 if state=='hover' else s3 if state=='pressed' else surface
            colour=ink if state in ('hover','pressed') else secondary
            colour=hx(blend(surface,secondary,.4)) if state=='disabled' else colour
            assert hx(im.getpixel((x+4,y+16)))==fill
            assert rgb(colour) in list(im.crop((x+7,y+7,r-7,b-7)).getdata())
            if state=='focus':
                assert hx(im.getpixel((x+16,y-3)))==accent
                assert hx(im.getpixel((x+16,y-1)))==surface
            if state=='hover':
                # Hover coverage is exactly 32x32; the 9px corner matches an
                # independently rasterized circular-arc coverage mask.
                crop=im.crop((x-4,y-4,r+4,b+4));diff=ImageChops.difference(crop,Image.new('RGB',crop.size,rgb(surface)))
                assert diff.getbbox()==(4,4,36,36),diff.getbbox()
                assert im.getpixel((x,y))==rgb(surface) and im.getpixel((x+9,y))==rgb(fill)
                errors={}
                for radius in (8,9,10):
                    cost=0
                    for yy in range(9):
                        for xx in range(9):
                            coverage=sum((xx+(i+.5)/16-radius)**2+(yy+(j+.5)/16-radius)**2<=radius**2 for i in range(16) for j in range(16))/256
                            want=rgb(surface)[0]+(rgb(fill)[0]-rgb(surface)[0])*coverage
                            cost+=(im.getpixel((x+xx,y+yy))[0]-want)**2
                    errors[radius]=cost
                assert min(errors,key=errors.get)==9,errors
            result['icons'].append({'theme':theme,'state':state,'fill':fill,'glyph':colour,'focus':accent if state=='focus' else None})
        result[theme+'-geometry']={'button':[32,32],'radius':9,'gap':6,'right':12,'glyph_width':18,'stroke':stroke,
                                  'title_font':15,'title_weight':650,'title_left':20,'title_spacing_em':-.01,
                                  'bar':surface,'body':bg,'hairline':hx(blend(surface,line,.075))}
        im=client(dest,theme+'-panel',panel);l,t,r,b=panel['panel']
        assert [r-l,b-t]==[360,172]
        border=hx(blend(surface,line,.075))
        assert hx(im.getpixel((l,t+50)))==border
        assert hx(im.getpixel((l+1,t+50)))==surface
        assert hx(im.getpixel((l+25,t+119)))==s2
        track_border=hx(blend(s2,line,.075))
        assert hx(im.getpixel((l+80,t+118)))==track_border
        active=panel['controls'][theme]
        assert hx(im.getpixel((active[0]+6,active[1]+13)))==surface
        for control in ('minus','plus'):
            a,c,d,e=panel['controls'][control];assert [d-a-8,e-c-8]==[34,34]
        assert panel['controls']['minus'][1]+4-t==44
        assert panel['controls']['plus'][2]-4-(panel['controls']['minus'][0]+4)==138
        result['panels'][theme]={'border':border,'border_width':1,'shadow':'--shadow-lg','radius':14,
            'padding_top':20,'padding_bottom':b-(t+152),'padding_left':20,'padding_right':20,
            'track':s2,'track_border':track_border,'selected':surface,'selected_text':ink,
            'stepper':[34,34],'label_control_gap':8,'section_gap':16,'size':[360,172]}
    # Read the specified original, choose a body chapter with real <p> breaks.
    with zipfile.ZipFile(original) as z:
        opf=next(n for n in z.namelist() if n.endswith('.opf'));package=ET.fromstring(z.read(opf))
        manifest={e.attrib['id']:e.attrib.get('href') for e in package.iter() if e.tag.endswith('item')}
        spine=[manifest[e.attrib['idref']] for e in package.iter() if e.tag.endswith('itemref')]
        body_path=next(n for n in z.namelist() if n.endswith('24264-0-16.txt.html'))
        part=spine.index(body_path.split('/')[-1])
        quotation_counts={c:sum(z.read(n).decode('utf-8').count(c) for n in z.namelist() if n.endswith('.html')) for c in ('。','，','「','」','“','”')}
        vertical=out/'Hongloumeng-vertical-css.epub'
        with zipfile.ZipFile(vertical,'w') as v:
            for info in z.infolist():
                data=z.read(info.filename)
                if info.filename.endswith('.html'):
                    modified=data.replace(b'</head>',b'<style>html{writing-mode:vertical-rl}</style></head>')
                    assert ''.join(ET.fromstring(modified).itertext()).replace('html{writing-mode:vertical-rl}','')==''.join(ET.fromstring(data).itertext())
                    data=modified
                v.writestr(info,data)
    result['original']={'path':str(original),'sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
                        'part':part,'chapter':body_path,'punctuation_counts':quotation_counts,
                        'vertical_change':'writing-mode CSS only; chapter text equal'}
    for mode,book in (('horizontal',original),('vertical',vertical)):
        target=out/mode;profile=target/'profile'
        run(exe,font,f'import|{book}\nwait_idle\nquit\n',profile,target/'import')
        with sqlite3.connect(profile/'library.sqlite') as db:
            book_id=db.execute('select id from books').fetchone()[0]
            db.execute('insert or replace into epub_progress(book_id,part,path,position) values(?,?,?,0)',(book_id,part,body_path))
        script='open|紅樓夢\nwait_idle\nshell|on\nshell_dpi|96\nshell_font|18\nshell_client|1280|800\nwait_idle\nshell_click|light\nui_cues|hide\n'
        widths=(1280,2560) if mode=='horizontal' else (1280,)
        for width in widths:
            name=f'{mode}-{width}'
            script+=f'shell_client|{width}|{800 if width==1280 else 1440}\nwait_idle\nshell_measure|{name}\nsnapshot|{name}\n'
        run(exe,font,script+'quit\n',profile,target)
        for width in widths:
            name=f'{mode}-{width}';m=measure(target,name)
            assert m['font']==18 and m['mode']==(1 if mode=='vertical' else 0)
            assert '。' in m['text'] and '，' in m['text'] and '\n' in m['text']
            assert m['page'][0]==612
            if mode=='horizontal':
                assert all(abs(l[7]-32)<.001 for l in m['lines'])
                assert abs(glyph(m,m['lines'][0])[3]-m['lines'][1][4]-36)<.001
                paragraph_lines=[(a,b) for a,b in zip(m['lines'],m['lines'][1:]) if b[0]>a[1]]
                assert paragraph_lines and all(abs(b[5]-a[5]-a[7]-9)<.001 for a,b in paragraph_lines)
            else:
                # SDK line.height is the used inline extent, so paragraph tails
                # and compressed punctuation may be shorter than the capacity.
                inline_limit=m['page'][1]-2*m['font']
                assert abs(max(l[7] for l in m['lines'])-inline_limit)<.001,m['lines']
                assert all(abs(l[5]-27)<.001 for l in m['lines']),m['lines']
                assert abs(glyph(m,m['lines'][0])[4]-m['lines'][0][5]-36)<.001
            im=client(target,name,m);im.save(out.parent/(name+'.png'))
            result[name]={'client':m['client'],'page':m['page'],'paragraphs':len(m['text'].split('\n')),
                          'line_or_column_sizes':sorted(set(round(l[6 if mode=='vertical' else 7],5) for l in m['lines']))}
            if mode=='vertical':result[name].update(inline_limit=inline_limit,inline_origin=27)
    dump(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
