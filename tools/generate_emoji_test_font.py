#!/usr/bin/env python3
"""Original emoji substitution rules on the original bitmap-only fixture."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import hashlib
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

ROOT=Path(__file__).resolve().parents[1]/'tests/fixtures/fonts'
FEATURES='''
languagesystem DFLT dflt;
languagesystem latn dflt;
table GDEF { GlyphClassDef [color plain], [exact256], [blue], ; } GDEF;
feature ccmp {
    sub color huge plain by exact256;
    sub color blue foreground red by exact256;
    sub plain hugeColor foreground by exact256;
    sub color plain by foreground;
} ccmp;
feature ss01 { sub color' huge plain by blue; } ss01;
feature ss02 { sub huge color' plain by blue; } ss02;
feature ss03 { rsub huge color' plain by blue; } ss03;
feature ss04 { sub [color red]' [huge hugeColor] [plain foreground] by blue; } ss04;
feature ss05 { sub huge plain by exact256; } ss05;
feature ss06 { sub color tooMany plain by exact256; } ss06;
feature ss07 { lookupflag IgnoreMarks; sub color blue foreground red by exact256; } ss07;
'''

def main():
    font=TTFont(ROOT/'cbdt.ttf',recalcTimestamp=False)
    for table in font['cmap'].tables:
        if table.isUnicode():
            # Keep BMP additions in 16-bit cmap formats; format 12 covers emoji.
            cmap={0x200d:'huge',0x200c:'tooMany',0xfe0f:'hugeColor',0x20e3:'foreground',ord('1'):'plain'}
            if table.format in (12,13):
                cmap.update({0x1f469:'color',0x1f4bb:'plain',0x1f3f4:'color',0xe0067:'blue',0xe0062:'foreground',0xe007f:'red'})
            table.cmap.update(cmap)
    addOpenTypeFeaturesFromString(font,FEATURES)
    path=ROOT/'emoji.ttf';font.save(path)
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())

if __name__=='__main__':
    main()
