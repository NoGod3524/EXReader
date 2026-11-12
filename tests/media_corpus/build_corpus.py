"""Builds the four media EPUBs used by the D2 acceptance run (needs ffmpeg and Pillow).

usage: python build_corpus.py OUTPUT_DIR
Media are synthetic (sine tones, ffmpeg test patterns); nothing third-party is bundled.
"""
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

XHTML = ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
         'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{t}</title></head><body>{b}</body></html>')
LOREM = ('<p>The lamp on the desk threw a small circle of light across the page, and the rest of the '
         'room went quietly dark around it. She read until the words began to blur.</p>')
STORED = ('mp3', 'm4a', 'mp4', 'flv', 'wmv', 'png')


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args], check=True)


def media(work):
    ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:duration=4', '-c:a', 'libmp3lame', '-b:a', '64k', str(work / 'tone.mp3'))
    ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:duration=3', '-c:a', 'aac', str(work / 'theme.m4a'))
    ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=2', '-f', 'lavfi', '-i', 'sine=duration=2',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(work / 'clip.mp4'))
    ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=220:duration=6', '-c:a', 'libmp3lame', '-b:a', '48k', str(work / 'narration.mp3'))
    ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=64x48:rate=5:duration=1', '-c:v', 'flv1', str(work / 'old.flv'))
    ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=64x48:rate=5:duration=1', '-c:v', 'wmv2', str(work / 'old.wmv'))
    Image.new('RGB', (160, 120), (60, 90, 140)).save(work / 'poster.png')
    return {p.name: p.read_bytes() for p in work.iterdir()}


def epub(path, title, items, spine, files, extra_meta=''):
    manifest = ''.join(
        f'<item id="{i}" href="{h}" media-type="{m}"{(" " + a) if a else ""}/>' for i, h, m, a in items)
    spine_xml = ''.join(f'<itemref idref="{i}"/>' for i in spine)
    opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="id">urn:media-corpus:{title.replace(" ", "-").lower()}</dc:identifier>'
           f'<dc:title>{title}</dc:title><dc:language>en</dc:language>'
           f'<meta property="dcterms:modified">2026-11-10T00:00:00Z</meta>{extra_meta}</metadata>'
           f'<manifest>{manifest}</manifest><spine>{spine_xml}</spine></package>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml',
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('OPS/book.opf', opf, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files.items():
            z.writestr('OPS/' + name, data,
                       compress_type=zipfile.ZIP_STORED if name.rsplit('.', 1)[-1] in STORED else zipfile.ZIP_DEFLATED)


def page(title, body):
    return XHTML.format(t=title, b=body)


def smil(chapter, prefix, count, first):
    pars = ''.join(
        f'<par id="{prefix}{i + 1}"><text src="{chapter}#{prefix}{i + 1}"/>'
        f'<audio src="audio/narration.mp3" clipBegin="0:00:{first + i:02d}.000" clipEnd="0:00:{first + i + 1:02d}.000"/></par>'
        for i in range(count))
    return ('<?xml version="1.0"?><smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">'
            f'<body><seq id="seq" epub:textref="{chapter}" epub:type="bodymatter chapter">{pars}</seq></body></smil>')


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        m = media(Path(tmp))
    xh, mp3, m4a, mp4 = 'application/xhtml+xml', 'audio/mpeg', 'audio/mp4', 'video/mp4'

    # 1. audio + video elements, including a <source> fallback list
    epub(out / 'media-av.epub', 'Media AV', [
        ('c1', 'c1.xhtml', xh, ''), ('tone', 'audio/tone.mp3', mp3, ''), ('theme', 'audio/theme.m4a', m4a, ''),
        ('clip', 'video/clip.mp4', mp4, ''), ('poster', 'img/poster.png', 'image/png', '')], ['c1'], {
        'c1.xhtml': page('AV', '<h1>Audio and video</h1>' + LOREM +
                         '<p>Listen to the tone:</p><audio src="audio/tone.mp3" controls="controls">Audio is not supported.</audio>'
                         '<p>The theme, with a fallback source list:</p><audio controls="controls">'
                         '<source src="audio/theme.ogg" type="audio/ogg"/><source src="audio/theme.m4a" type="audio/mp4"/></audio>'
                         '<p>A short clip:</p><video controls="controls" poster="img/poster.png" width="160" height="120">'
                         '<source src="video/clip.mp4" type="video/mp4"/>Video is not supported.</video>' + LOREM),
        'audio/tone.mp3': m['tone.mp3'], 'audio/theme.m4a': m['theme.m4a'], 'video/clip.mp4': m['clip.mp4'],
        'img/poster.png': m['poster.png']})

    # 2. media overlay (SMIL): two chapters, three synchronised paragraphs each
    words = ['It was a quiet morning.', 'The kettle began to sing.', 'Somewhere a door closed.',
             'She opened the window.', 'Rain had started again.', 'The day began.']
    body1 = '<h1>Chapter One</h1>' + ''.join(f'<p id="s{i + 1}">{w}</p>' for i, w in enumerate(words[:3]))
    body2 = '<h1>Chapter Two</h1>' + ''.join(f'<p id="t{i + 1}">{w}</p>' for i, w in enumerate(words[3:]))
    epub(out / 'media-smil.epub', 'Media Overlay', [
        ('c1', 'c1.xhtml', xh, 'media-overlay="o1"'), ('c2', 'c2.xhtml', xh, 'media-overlay="o2"'),
        ('o1', 'c1.smil', 'application/smil+xml', ''), ('o2', 'c2.smil', 'application/smil+xml', ''),
        ('nar', 'audio/narration.mp3', mp3, '')], ['c1', 'c2'], {
        'c1.xhtml': page('One', body1), 'c2.xhtml': page('Two', body2),
        'c1.smil': smil('c1.xhtml', 's', 3, 0), 'c2.smil': smil('c2.xhtml', 't', 3, 3),
        'audio/narration.mp3': m['narration.mp3']},
        extra_meta='<meta property="media:duration" refines="#o1">0:00:03.000</meta>'
                   '<meta property="media:duration" refines="#o2">0:00:03.000</meta>'
                   '<meta property="media:duration">0:00:06.000</meta>'
                   '<meta property="media:active-class">-epub-media-overlay-active</meta>')

    # 3. cover video and background music
    epub(out / 'media-cover-bgm.epub', 'Cover Video and Background Music', [
        ('cover', 'cover.xhtml', xh, ''), ('c1', 'c1.xhtml', xh, ''), ('clip', 'video/clip.mp4', mp4, ''),
        ('theme', 'audio/theme.m4a', m4a, ''), ('poster', 'img/poster.png', 'image/png', '')], ['cover', 'c1'], {
        'cover.xhtml': page('Cover', '<section epub:type="cover"><h1>Cover Video</h1>'
                            '<video src="video/clip.mp4" autoplay="autoplay" loop="loop" muted="muted" poster="img/poster.png" '
                            'width="160" height="120"/></section>'),
        'c1.xhtml': page('Chapter', '<h1>Chapter with music</h1><audio src="audio/theme.m4a" autoplay="autoplay" loop="loop"/>' + LOREM),
        'video/clip.mp4': m['clip.mp4'], 'audio/theme.m4a': m['theme.m4a'], 'img/poster.png': m['poster.png']})

    # 4. legacy, missing, remote and source-less media
    epub(out / 'media-legacy.epub', 'Legacy and Missing Media', [
        ('c1', 'c1.xhtml', xh, ''), ('swf', 'movie.swf', 'application/x-shockwave-flash', ''),
        ('flv', 'old.flv', 'video/x-flv', ''), ('wmv', 'old.wmv', 'video/x-ms-wmv', ''),
        ('svg', 'art.svg', 'image/svg+xml', '')], ['c1'], {
        'c1.xhtml': page('Legacy', '<h1>Legacy and missing media</h1>' + LOREM +
                         '<p>Missing audio file:</p><audio src="audio/gone.mp3" controls="controls"/>'
                         '<p>Flash movie:</p><object data="movie.swf" type="application/x-shockwave-flash">'
                         '<param name="movie" value="movie.swf"/><p>Install Flash to see this.</p></object>'
                         '<p>Flash video:</p><embed src="old.flv" type="video/x-flv"/>'
                         '<p>Windows video:</p><video src="old.wmv" controls="controls"/>'
                         '<p>Online video:</p><video src="https://example.com/v.mp4" controls="controls"/>'
                         '<p>No source:</p><audio controls="controls"/>' + LOREM),
        'movie.swf': b'FWS\x09' + bytes(40), 'old.flv': m['old.flv'], 'old.wmv': m['old.wmv'],
        'art.svg': '<svg xmlns="http://www.w3.org/2000/svg"/>'})
    print('built', *sorted(p.name for p in out.glob('*.epub')))


if __name__ == '__main__':
    main(sys.argv[1])
