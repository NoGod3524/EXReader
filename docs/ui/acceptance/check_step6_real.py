#!/usr/bin/env python3
"""Real EPUBs only; never rewrites book bytes or generates an EPUB.

Usage: check_step6_real.py EXE BASELINE FONT HONGLOUMENG PACHINKO XINGSHI KUSAMAKURA OUT
BASELINE uses the same SDK. All windows stay offscreen; snapshots use PrintWindow.
"""
import hashlib
import io
import json
import posixpath
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image, ImageChops, ImageStat
from check_step5 import run, client, dump, rgb

# Pin the reviewed real inputs so a generated substitute cannot pass this suite.
REAL_BOOKS = {
    'hongloumeng':'325fef5fb561a258ee4e0ded25821a55d77f7b4b627ae0ecac03410802ea6ec7',
    'pachinko':'7f8a2a6c4b25a620b5370bdc602d0cf83c564e04f03243308cc532c438357033',
    'xingshihengyan':'c229b87ef790da1b50636381bbf23e63c2dd9f3f8f7a893bf165bc2ff0933372',
    'kusamakura':'6d4d4ed5eda3f612e3263c54fa0f74ccfa87260f43e81bb58ea658636e52eeb7',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publication(path):
    with zipfile.ZipFile(path) as archive:
        opf = ET.fromstring(archive.read('META-INF/container.xml')).find('.//{*}rootfile').get('full-path')
        root = ET.fromstring(archive.read(opf))
        items = {i.get('id'): posixpath.normpath(posixpath.join(posixpath.dirname(opf), i.get('href')))
                 for i in root.findall('.//{*}manifest/{*}item')}
        spine = [items[i.get('idref')] for i in root.findall('.//{*}spine/{*}itemref')]
        title = root.find('.//{*}title').text
        cover = ET.fromstring(archive.read(spine[0]))
        images = [i for i in cover.iter() if i.tag.split('}')[-1] in ('img', 'image')]
        if len(images) == 1:
            src = images[0].get('src') or images[0].get('{http://www.w3.org/1999/xlink}href')
            image_path = posixpath.normpath(posixpath.join(posixpath.dirname(spine[0]), src))
            image = Image.open(io.BytesIO(archive.read(image_path))).convert('RGBA')
            white = Image.new('RGBA', image.size, 'white'); white.alpha_composite(image)
            image = white.convert('RGB')
        else:
            image_path, image = None, None
    return title, spine, image_path, image


def edge_samples(shot, body, dpi=96):
    left, top, right, bottom = body
    width, height = shot.size
    points = [(left-4,y) for y in range(top,bottom)] + [(right+4,y) for y in range(top,bottom)]
    points += [(x,top-4) for x in range(left,right)] + [(x,bottom+4) for x in range(left,right)]
    bar = round(56*dpi/96)
    points += [(x,y) for x in range(width) for y in (bar,bar+1,height-2,height-1)]
    points += [(x,y) for x in (0,1,width-2,width-1) for y in range(bar,height)]
    error = max(abs(c-e) for p in points for c,e in zip(shot.getpixel(p),rgb('#141416')))
    assert error == 0, error
    return dict(count=len(points), expected='#141416', max_rgb_error=error)


def main():
    exe, baseline, font, hong, pachinko, xingshi, kusa, out = [Path(s).resolve() for s in sys.argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    record = out/'record'; record.mkdir(exist_ok=True)
    result = dict(inputs=[], images=[], bodies=[], focus=[])
    for label, book in [('hongloumeng',hong), ('pachinko',pachinko), ('xingshihengyan',xingshi), ('kusamakura',kusa)]:
        title, spine, image_path, source = publication(book)
        original_sha = sha(book)
        assert original_sha == REAL_BOOKS[label], (label,original_sha)
        result['inputs'].append(dict(label=label,path=str(book),sha256=original_sha,
                                     cover_path=spine[0],image_path=image_path))
        if source is not None:
            for dpi in (96,120):
                target = record/f'{label}-{dpi}'
                sizes = ((1242,742),(1280,800),(900,600)) if dpi==96 else ((1242,742),(1280,800))
                # Enable shell before opening, matching the ordinary startup order.
                script = f'shell|on\nshell_dpi|{dpi}\nimport|{book}\nopen|{title}\nwait_idle\nshell_click|system\n'
                for width,height in sizes:
                    name = f'{width}x{height}'
                    script += f'shell_client|{width}|{height}\nwait_idle\nshell_measure|{name}\nsettings_measure|theme-{name}\nsnapshot|{name}\n'
                run(exe,font,script+'quit\n',target/'profile',target)
                with sqlite3.connect(target/'profile/library.sqlite') as db:
                    stored = db.execute('select source from books').fetchone()[0]
                    assert hashlib.sha256(stored).hexdigest() == original_sha
                for width,height in sizes:
                    name = f'{width}x{height}'
                    meta = json.loads((target/(name+'.json')).read_text('utf8'))
                    theme = json.loads((target/('theme-'+name+'.json')).read_text('utf8'))
                    assert meta['client']==[width,height] and theme['dark']==1 and theme['theme']==2
                    assert meta['part']==0 and not meta['glyphs']
                    probe = meta['image_probe']
                    assert probe == dict(image_count=1,visible_text=0,flags=0,source_available=1,fitted=1), probe
                    l,t,r,b = meta['image']; left,top,right,bottom = meta['body']
                    assert meta['image_source']==list(source.size)
                    dx,dy = abs((l+r-left-right)/2),abs((t+b-top-bottom)/2)
                    aspect = abs((r-l)/(b-t)-source.width/source.height)
                    assert dx<=1 and dy<=1 and aspect<=.01
                    assert left<=l<r<=right and top<=t<b<=bottom
                    shot = client(target,name,meta)
                    # Independent source identity/cropping check: compare the whole decoded
                    # original with PrintWindow pixels, including all four source edges.
                    expected = source.resize((r-l,b-t),Image.Resampling.BILINEAR)
                    actual = shot.crop((l,t,r,b))
                    diff = ImageChops.difference(expected,actual)
                    mean = sum(ImageStat.Stat(diff).mean)/3
                    edge = max(sum(ImageStat.Stat(diff.crop(box)).mean)/3 for box in
                               [(0,0,r-l,1),(0,b-t-1,r-l,b-t),(0,0,1,b-t),(r-l-1,0,r-l,b-t)])
                    assert mean<6 and edge<12,(label,name,mean,edge)
                    row=dict(book=label,dpi=dpi,client=[width,height],image=meta['image'],body=meta['body'],
                             source=list(source.size),probe=probe,horizontal_error_px=dx,vertical_error_px=dy,
                             aspect_error=aspect,clipped=False,source_mean_rgb_error=mean,source_edge_mean_rgb_error=edge)
                    row['exterior']=edge_samples(shot,meta['body'],dpi)
                    result['images'].append(row)
                    if label=='hongloumeng' and dpi==96 and width==1242:
                        shot.save(out/'cover-dark-1242x742.png')
        # Compare original text/mixed pages with the previous binary, same SDK.
        part = {'hongloumeng':15,'pachinko':10,'xingshihengyan':4,'kusamakura':2}[label]
        target = record/(label+'-body'); profile = target/'profile'
        run(exe,font,f'import|{book}\nwait_idle\nquit\n',profile,target/'import')
        with sqlite3.connect(profile/'library.sqlite') as db:
            book_id = db.execute('select id from books').fetchone()[0]
            db.execute('insert or replace into epub_progress(book_id,part,path,position) values(?,?,?,0)',
                       (book_id,part,spine[part]))
        script = f'shell|on\nshell_dpi|96\nopen|{title}\nwait_idle\nshell_client|1242|742\nwait_idle\nshell_click|system\nui_cues|show\nshell_measure|body\nsettings_measure|theme\nsnapshot|body\n'
        if label=='pachinko':
            for control in ('toc','settings'):
                script += f'shell_render_focus|{control}\nsnapshot|focus-{control}\nui_cues|hide\nsnapshot|mouse-{control}\nshell_render_focus|none\nui_cues|show\n'
        for binary, dest in ((exe,target/'changed'),(baseline,target/'baseline')):
            run(binary,font,script+'quit\n',profile,dest)
        meta = json.loads((target/'changed/body.json').read_text('utf8'))
        old = json.loads((target/'baseline/body.json').read_text('utf8'))
        assert meta['part']==part and meta['glyphs'] and meta['image_source']==[0,0]
        assert meta['glyphs']==old['glyphs'] and meta['lines']==old['lines'] and meta['text']==old['text']
        shot = client(target/'changed','body',meta)
        before = client(target/'baseline','body',old)
        assert ImageChops.difference(shot,before).getbbox() is None, label
        result['bodies'].append(dict(book=label,part=part,glyphs=len(meta['glyphs']),
                                     changed_pixels=0,exterior=edge_samples(shot,meta['body'])))
        if label=='pachinko':
            shot.save(out/'body-dark-1242x742.png')
            theme = json.loads((target/'changed/theme.json').read_text('utf8'))
            for control in ('toc','settings'):
                focused = client(target/'changed','focus-'+control,meta)
                mouse = client(target/'changed','mouse-'+control,meta)
                x,y,r,b = theme['icons'][control]
                for offset,colour in ((-3,'#7c88ff'),(-4,'#7c88ff'),(-5,'#1e1e21'),(-2,'#1e1e21'),(-1,'#1e1e21')):
                    assert focused.getpixel(((x+r)//2,y+offset))==rgb(colour)
                assert mouse.getpixel(((x+r)//2,y-3))==rgb('#1e1e21')
                focused.save(out/f'keyboard-focus-{control}.png')
                result['focus'].append(dict(control=control,width_px=2,offset_px=2,mouse_ring=False))
        assert sha(book)==original_sha
    result['pass']=True
    dump(out/'real-result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
