# SPDX-License-Identifier: MIT
"""Generate original layout samples; Pillow is needed only to encode the JPEG fixture."""
from pathlib import Path
from io import BytesIO
import struct
import zipfile
import zlib
from PIL import Image

DEST = Path(__file__).parent / "fixtures"


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(width, height):
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            pixels.extend((220, 40, 30, 255) if x < width // 3 else
                          (30, 180, 60, 255) if x < width * 2 // 3 else (20, 50, 220, 128))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


image = Image.new("RGB", (96, 48), (32, 128, 192))
stream = BytesIO()
image.save(stream, format="JPEG", quality=95)
css = '''
body { font-size: 20px; color: #243449; }
h1 { font-size: 32px; color: #174d70; text-align: center; margin: 0 0 16px; }
p { margin: 0 0 10px; line-height: 1.4; }
.panel { padding: 12px; border: 1px solid #a5b8c8; background: #edf4f8; margin-bottom: 12px; }
.panel > p { font-size: 18px; }
.note { font-size: 14px; }
p#intro.note { font-size: 24px; text-indent: 1em; }
#priority { color: #008000 !important; }
#order { color: #ff0000; }
#order { color: #0000ff; }
.hidden { display: none; }
#invalid { font-size: 23px; font-size: nonsense; }
strong { font-size: 1.25em; }
img.hero { width: 192px; max-width: 90%; margin: 8px auto; }
table { width: 100%; margin: 8px 0; }
th, td { padding: 6px; border: 1px solid #8094a8; font-size: 16px; text-indent: 0; }
th { background-color: #e1edf6; text-align: left; }
.caption { font-size: 16px; color: #607080; text-align: center; }
@media (unsupported: condition) { #intro { font-size: 100px; } }
'''


def html(body, styled=True, embedded=""):
    head = '<link rel="stylesheet" href="style.css"/>' if styled else ''
    return ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Native layout</title>'
            + head + f'<style>{embedded}</style></head><body>{body}</body></html>')


def write(name, body, extra=None, second=None):
    manifest = '''<item id="main" href="main.xhtml" media-type="application/xhtml+xml"/>
<item id="css" href="style.css" media-type="text/css"/>
<item id="png" href="sample.png" media-type="image/png"/>
<item id="jpeg" href="sample.jpg" media-type="image/jpeg"/>
<item id="bad" href="bad.jpg" media-type="image/jpeg"/>
<item id="huge" href="huge.png" media-type="image/png"/>'''
    if second:
        manifest += '<item id="second" href="second.xhtml" media-type="application/xhtml+xml"/>'
    opf = ('<package><metadata><title>Native styled sample</title></metadata><manifest>' + manifest
           + '</manifest><spine><itemref idref="main"/>' + ('<itemref idref="second"/>' if second else '')
           + '</spine></package>')
    data = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": '<container><rootfiles><rootfile full-path="package.opf"/></rootfiles></container>',
        "package.opf": opf, "main.xhtml": body, "style.css": css, "sample.png": png(96, 48),
        "sample.jpg": stream.getvalue(), "bad.jpg": b"broken jpeg",
        "huge.png": b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8192, 8192, 8, 6, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b""),
    }
    if second:
        data["second.xhtml"] = second
    data.update(extra or {})
    with zipfile.ZipFile(DEST / name, "w") as z:
        for path, content in data.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if path == "mimetype" else zipfile.ZIP_DEFLATED
            z.writestr(info, content.encode("utf-8") if isinstance(content, str) else content)


write("layout.epub", html('''
<h1 id="heading">Native C layout</h1>
<p id="intro" class="note">中文排版 <strong id="bold">Bold</strong> and <em id="italic">italic</em>.</p>
<div class="panel"><p id="panel">Styled paragraphs share an open document model.</p></div>
<p class="hidden" id="hidden">Hidden by stylesheet.</p>
<p id="priority" style="color: #ff8000">Important cascade</p>
<p id="order">Source order</p><p id="invalid">Invalid declarations fall back.</p>
<img id="png" class="hero" src="sample.png"/><p class="caption">PNG with alpha, scaled in C</p>
<table id="table"><tr><th>Format</th><th>Output</th></tr>
<tr><td id="span" rowspan="2">Native C</td><td id="right">PNG image</td></tr>
<tr><td id="lower">JPEG image</td></tr><tr><td id="wide" colspan="2">Merged cell</td></tr></table>
<img id="jpeg" class="hero" src="sample.jpg"/>
''', embedded='.panel p { color: #243449; }'), second=html('<p class="note" id="scope">Chapter without book styles.</p>', False))
long_rows = ''.join(f'<tr><td id="left{i}">Row {i}</td><td id="right{i}">Value {i}</td></tr>' for i in range(30))
write("layout-table.epub", html('<table>' + long_rows + '</table>'))
write("layout-tall.epub", html('<table><tr><td>' + '<p>A tall row.</p>' * 100 + '</td></tr></table>'))
write("layout-image.epub", html('<img id="image" class="hero" src="sample.png"/>'))
write("layout-placeholder.epub", html('<img src="bad.jpg"/><img src="missing.png"/>'))
write("layout-huge.epub", html('<img src="huge.png"/>'))
write("layout-break.epub", html('<p id="before">Before</p><p id="after" style="break-before:page">After</p>'))
write("layout-malformed-css.epub", html('<p id="target">Visible</p>'), {
    'style.css': '/* comment */ p {color:#123456; bad:"};";font-size:20px} @unknown { p {display:none} } p {color:garbage; } /* tail'})
write("layout-padding.epub", html('<p style="line-height:200px;margin:0">Before</p>'
      '<p style="padding:20px;border:2px solid red;background:#eef">After</p>'))
write("layout-damaged.epub", html('<img src="sample.png"/>'), {
    "sample.png": (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 96, 48, 8, 6, 0, 0, 0))
                   + chunk(b"IDAT", b"invalid zlib stream") + chunk(b"IEND", b""))})
