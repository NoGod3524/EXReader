#!/usr/bin/env python3
"""Original cmap 14 variant/default mappings, with no GSUB or GPOS tables."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import hashlib
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

ROOT=Path(__file__).resolve().parents[1]/'tests/fixtures/fonts'

def main():
    font=TTFont(ROOT/'fallback.ttf',recalcTimestamp=False)
    font['hmtx'].metrics.update(V=(700,0),beta=(1100,0),a=(500,0))
    variants=CmapSubtable.newSubtable(14)
    variants.platformID=0;variants.platEncID=5;variants.language=0;variants.cmap={}
    variants.uvsDict={0xfe0e:[(0x41,None)],0xfe0f:[(0x41,'V'),(0x61,None)],
                      0xe0100:[(0x4e00,'beta'),(0x7532,'beta')],0xe0101:[(0x7532,None)]}
    font['cmap'].tables.append(variants)
    path=ROOT/'uvs.ttf';font.save(path)
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())

if __name__=='__main__':
    main()
