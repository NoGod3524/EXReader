#!/usr/bin/env python3
"""Original FB2 fixture with a generated 2x2 PNG; no third-party book content."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import base64, struct, zlib

def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,6,0,0,0))
png+=chunk(b'IDAT',zlib.compress(b'\0'+bytes([255,0,0,255,0,255,0,255])+b'\0'+bytes([0,0,255,255,255,255,255,255])))+chunk(b'IEND',b'')
book='''<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<stylesheet type="text/css">p {color:#224466} .large {font-size:24px} img {width:24px;height:24px}</stylesheet>
<description><title-info><book-title>Book &amp; 图</book-title><author><nickname>Metadata only</nickname></author><coverpage><image l:href="#封面"/></coverpage></title-info></description>
<body><section id="main"><title><p>Heading</p></title>
<p>Normal <strong>bold</strong> and <emphasis>italic</emphasis>, <a type="note" l:href="#note">note</a>.</p>
<image l:href="#%E5%B0%81%E9%9D%A2"/>
<table><tr><th>A</th><th>B</th></tr><tr><td colspan="2">Merged</td></tr></table>
<poem><stanza><v>Verse one</v><v>Verse two</v></stanza></poem><p><style name="large">Large</style></p>
</section></body><body name="notes"><section id="note"><p>Footnote text.</p></section></body>
<binary id="封面" content-type="image/png">BINARY</binary></FictionBook>'''.replace('BINARY',base64.b64encode(png).decode())
(Path(__file__).resolve().parent/'fixtures'/'rich.fb2').write_text(book,encoding='utf-8')
