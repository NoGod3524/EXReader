#!/usr/bin/env python3
"""Single-image/focus pixels in real offscreen HWNDs, captured with PrintWindow.

Usage: check_step6.py EXE MAIN_BASELINE FONT REAL_EPUB OUT
Focus screenshots inject the owner-draw focus state; no foreground/input is used.
"""
import io
import json
from pathlib import Path
import sqlite3
import sys
import zipfile
from PIL import Image, ImageDraw, ImageChops
from check_step5 import run, client, dump, rgb, hx


def fixture(path, width, height):
    image = Image.new('RGB', (width, height), '#c4beff')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width-1, height-1), outline='#ff7400', width=24)
    draw.rectangle((40, 40, width-41, height-41), outline='#12dba0', width=24)
    stream = io.BytesIO(); image.save(stream, format='PNG')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr('package.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">step6</dc:identifier><dc:title>Step6 image</dc:title></metadata><manifest><item id="c" href="cover.xhtml" media-type="application/xhtml+xml"/><item id="i" href="image.png" media-type="image/png"/></manifest><spine><itemref idref="c"/></spine></package>')
        # Deliberately disagree with the decoded aspect, and add a page offset.
        archive.writestr('cover.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Cover</title></head><body><p style="margin-top:80px"><img src="image.png" style="width:600px;height:900px"/></p></body></html>')
        archive.writestr('image.png', stream.getvalue())


def main():
    exe, baseline, font, original, out = (Path(p).resolve() for p in sys.argv[1:])
    out.mkdir(parents=True, exist_ok=True)
    record = out/'record'; record.mkdir(exist_ok=True)
    result = {'images': [], 'focus': [], 'edge_samples': []}
    sizes = ((1242,742), (1280,800), (900,600), (720,560))
    books = [('real-cover', original, '紅樓夢')]
    for name, width, height in (('portrait',600,900), ('landscape',2400,600), ('square',1200,1200)):
        book = record/(name+'.epub'); fixture(book,width,height)
        books.append((name,book,'Step6 image'))
    for label, book, title in books:
        for dpi in (96,120):
            target = record/f'{label}-{dpi}'
            # At 125%, the native minimum client is 900x700 physical pixels.
            target_sizes = sizes if dpi==96 else sizes[:2]
            script = f'import|{book}\nopen|{title}\nwait_idle\nshell|on\nshell_dpi|{dpi}\nshell_click|system\n'
            for width,height in target_sizes:
                name = f'{width}x{height}'
                script += f'shell_client|{width}|{height}\nwait_idle\nshell_measure|{name}\nsettings_measure|theme-{name}\nsnapshot|{name}\n'
            run(exe,font,script+'quit\n',target/'profile',target)
            for width,height in target_sizes:
                name = f'{width}x{height}'
                meta = json.loads((target/(name+'.json')).read_text(encoding='utf-8'))
                theme = json.loads((target/('theme-'+name+'.json')).read_text(encoding='utf-8'))
                assert meta['client'] == [width,height] and theme['theme'] == 2 and theme['dark'] == 1
                l,t,r,b = meta['image']; left,top,right,bottom = meta['body']
                iw,ih = meta['image_source']
                dx,dy = abs((l+r-left-right)/2),abs((t+b-top-bottom)/2)
                aspect = abs((r-l)/(b-t)-iw/ih)
                assert dx<=1 and dy<=1 and aspect<=.01, (label,name,meta)
                assert left<=l<r<=right and top<=t<b<=bottom
                assert min(l,t,width-r,height-b) >= 16
                shot = client(target,name,meta)
                crop = shot.crop((left,top,right,bottom))
                bands = crop.split()
                mask = ImageChops.lighter(ImageChops.lighter(bands[0],bands[1]),bands[2]).point(lambda v:255 if v>80 else 0)
                x,y,rr,bb = mask.getbbox()
                bounds = [x+left,y+top,rr+left,bb+top]
                assert max(abs(a-b) for a,b in zip(bounds,(l,t,r,b)))<=1, (label,name,bounds)
                assert abs((bounds[0]+bounds[2]-left-right)/2)<=1
                assert abs((bounds[1]+bounds[3]-top-bottom)/2)<=1
                assert abs((bounds[2]-bounds[0])/(bounds[3]-bounds[1])-iw/ih)<=.01
                # The coloured outer edge on all four sides proves no source edge was cropped.
                if label != 'real-cover':
                    points = ((l+1,(t+b)//2),(r-2,(t+b)//2),((l+r)//2,t+1),((l+r)//2,b-2))
                    assert all(shot.getpixel(p)==rgb('#ff7400') for p in points), (label,name,points)
                result['images'].append(dict(book=label,dpi=dpi,client=[width,height],image=[l,t,r,b],
                    source=[iw,ih],body=meta['body'],pixel_bounds=bounds,horizontal_error_px=dx,vertical_error_px=dy,
                    aspect_error=aspect,clipped=False))
                if label=='real-cover' and dpi==96 and width==1242:
                    shot.save(out/'cover-dark-1242x742.png')
    # A deterministic failure on the same main binary: distorted source aspect.
    before = record/'before-main'
    script = f'import|{record}/landscape.epub\nopen|Step6 image\nwait_idle\nshell|on\nshell_dpi|96\nshell_client|1242|742\nwait_idle\nshell_measure|cover\nsnapshot|cover\nquit\n'
    run(baseline,font,script,before/'profile',before)
    m = json.loads((before/'cover.json').read_text(encoding='utf-8')); l,t,r,b = m['image']
    result['main_reproducer'] = dict(image=m['image'],source=[2400,600],aspect_error=abs((r-l)/(b-t)-4))
    assert result['main_reproducer']['aspect_error'] > .01
    # Use the original book's real body chapter, without editing EPUB bytes.
    target = record/'body'; profile = target/'profile'
    run(exe,font,f'import|{original}\nwait_idle\nquit\n',profile,target/'import')
    with sqlite3.connect(profile/'library.sqlite') as db:
        book_id = db.execute('select id from books').fetchone()[0]
        db.execute('insert or replace into epub_progress(book_id,part,path,position) values(?,?,?,0)',
            (book_id,15,'OEBPS/2878037014660817796_24264-0-16.txt.html'))
    script = 'open|紅樓夢\nwait_idle\nshell|on\nshell_dpi|96\nshell_client|1242|742\nwait_idle\nshell_click|system\nui_cues|show\nshell_measure|body\nsettings_measure|theme\nsnapshot|body\n'
    for control in ('toc','settings'):
        script += f'ui_cues|show\nshell_render_focus|{control}\nsnapshot|focus-{control}\nui_cues|hide\nsnapshot|mouse-{control}\nshell_render_focus|none\n'
    script += 'ui_cues|hide\nsnapshot|mouse\nquit\n'
    run(exe,font,script,profile,target)
    m = json.loads((target/'body.json').read_text(encoding='utf-8')); theme = json.loads((target/'theme.json').read_text(encoding='utf-8'))
    assert m['part']==15 and m['glyphs'] and theme['theme']==2 and theme['dark']==1
    shot = client(target,'body',m); shot.save(out/'body-dark-1242x742.png')
    left,top,right,bottom = m['body']
    # Body exterior at exactly 4px, plus the page HWND perimeter that used to get a ring.
    points = [(left-4,y) for y in range(top,bottom)] + [(right+4,y) for y in range(top,bottom)]
    points += [(x,top-4) for x in range(left,right)] + [(x,bottom+4) for x in range(left,right)]
    points += [(x,y) for x in range(1242) for y in (56,57,740,741)]
    points += [(x,y) for x in (0,1,1240,1241) for y in range(56,742)]
    assert all(shot.getpixel(p)==rgb('#141416') for p in points)
    result['edge_samples'] = dict(count=len(points),expected='#141416',max_rgb_error=0,indigo_pixels=0)
    for control in ('toc','settings'):
        focused = client(target,'focus-'+control,m)
        x,y,r,b = theme['icons'][control]
        assert hx(focused.getpixel(((x+r)//2,y-3)))=='#7c88ff'
        assert hx(focused.getpixel(((x+r)//2,y-4)))=='#7c88ff'
        assert hx(focused.getpixel(((x+r)//2,y-5)))=='#1e1e21'
        assert hx(focused.getpixel(((x+r)//2,y-2)))=='#1e1e21'
        assert hx(focused.getpixel(((x+r)//2,y-1)))=='#1e1e21'
        assert hx(shot.getpixel(((x+r)//2,y-3)))=='#1e1e21'
        mouse = client(target,'mouse-'+control,m)
        assert hx(mouse.getpixel(((x+r)//2,y-3)))=='#1e1e21'
        focused.save(out/f'keyboard-focus-{control}.png')
        result['focus'].append(dict(control=control,ring='#7c88ff',width_px=2,offset_px=2,
            method='offscreen owner-draw focus state with keyboard cues shown'))
    result['pass'] = True
    dump(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
