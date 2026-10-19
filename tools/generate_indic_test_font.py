#!/usr/bin/env python3
"""Original geometric Devanagari fonts, with distinct basic-form GSUB stages."""
# SPDX-License-Identifier: MIT
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

ROOT = Path(__file__).resolve().parents[1]/'tests/fixtures/indic'
CMAP = {32:'space', 0x915:'ka', 0x916:'kha', 0x917:'ga', 0x91C:'ja', 0x91E:'nya',
        0x91F:'tta', 0x924:'ta', 0x926:'da', 0x928:'na', 0x92A:'pa', 0x92E:'ma',
        0x92F:'ya', 0x930:'ra', 0x932:'la', 0x937:'ssa', 0x938:'sa', 0x939:'ha',
        0x905:'a', 0x907:'i', 0x93C:'nukta', 0x94D:'virama', 0x93E:'aa', 0x93F:'matraI',
        0x940:'ii', 0x941:'u', 0x947:'e', 0x94B:'o', 0x902:'bindu', 0x903:'visarga',
        0x951:'vedic', 0x958:'qa', 0x25CC:'circle', 0x200D:'zwj', 0x200C:'zwnj'}
EXTRA = ['ga.locl','ka.half','ga.half','ta.half','ra.half','qa.half','kssa','jnya',
         'reph','rakar','preYa','postHa','kta','tka','matraI.init','reph.final']
ORDER = ['.notdef']+list(dict.fromkeys(CMAP.values()))+EXTRA
MARKS = ['nukta','virama','aa','matraI','ii','u','e','o','bindu','visarga','vedic',
         'reph','rakar','preYa','postHa','matraI.init','reph.final']


def generate(legacy):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(ORDER)
    glyphs = {}
    widths = {}
    for index, name in enumerate(ORDER):
        pen = TTGlyphPen(None)
        width = 600
        if name == 'space': width = 250
        elif name in ('zwj','zwnj','nukta','virama','u','e','bindu','vedic','reph','reph.final','rakar'): width = 0
        elif name in ('aa','ii','o','matraI','matraI.init','preYa','postHa','visarga'): width = 200
        elif name.endswith('.half'): width = 300
        elif name in ('kta','tka','kssa','jnya'): width = 700
        widths[name] = width
        if name not in ('space','zwj','zwnj'):
            right = max(80, width-50)
            height = 400+(index%7)*30
            pen.moveTo((20,0)); pen.lineTo((right,0)); pen.lineTo((right,height)); pen.lineTo((20,height)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name:(width,0) for name,width in widths.items()})
    builder.setupHorizontalHeader(ascent=900,descent=-200)
    builder.setupCharacterMap(CMAP)
    builder.setupNameTable(dict(familyName='EXR Indic Test',styleName='Legacy' if legacy else 'Modern',
        uniqueFontIdentifier='EXR-Indic-'+str(legacy),fullName='EXR Indic Test',psName='EXRIndicTest'+str(legacy),
        copyright='Copyright 2026 EXReader contributors; MIT'))
    builder.setupOS2(sTypoAscender=900,sTypoDescender=-200,usWinAscent=1000,usWinDescent=200)
    builder.setupPost()
    scripts = 'languagesystem deva dflt;' if legacy else 'languagesystem dev2 dflt; languagesystem deva dflt;'
    below = 'sub ra virama by rakar;' if legacy else 'sub virama ra by rakar;'
    pref = 'sub ya virama by preYa;' if legacy else 'sub virama ya by preYa;'
    post = 'sub ha virama by postHa;' if legacy else 'sub virama ha by postHa;'
    features = f'''
      {scripts}
      @MARK = [{' '.join(MARKS)}];
      @BASE = [{' '.join(n for n in ORDER if n not in MARKS and n not in ('zwj','zwnj'))}];
      table GDEF {{ GlyphClassDef @BASE,,@MARK,; }} GDEF;
      feature locl {{ sub ga by ga.locl; }} locl;
      feature nukt {{ sub ka nukta by qa; }} nukt;
      feature akhn {{ sub ka virama ssa by kssa; sub ja virama nya by jnya; }} akhn;
      feature rphf {{ sub ra virama by reph; }} rphf;
      feature rkrf {{ sub virama ra by rakar; }} rkrf;
      feature pref {{ {pref} }} pref;
      feature blwf {{ {below} }} blwf;
      feature pstf {{ {post} }} pstf;
      feature half {{ sub ka virama by ka.half; sub ga.locl virama by ga.half;
                      sub ta virama by ta.half; sub ra virama by ra.half; sub qa virama by qa.half; }} half;
      feature cjct {{ sub ka.half ta by kta; sub ta.half ka by tka; }} cjct;
      feature init {{ sub matraI by matraI.init; }} init;
      feature abvs {{ sub reph by reph.final; }} abvs;
      feature dist {{ pos ka 10; }} dist;
      markClass [reph.final bindu vedic] <anchor 0 0> @TOP;
      markClass [rakar u] <anchor 0 0> @BOTTOM;
      feature abvm {{ pos base [ka qa kssa kta tka circle] <anchor 300 700> mark @TOP; }} abvm;
      feature blwm {{ pos base [ka qa kssa kta tka circle] <anchor 250 -100> mark @BOTTOM; }} blwm;
    '''
    addOpenTypeFeaturesFromString(builder.font,features)
    builder.font['head'].created=builder.font['head'].modified=3800000000
    builder.font.recalcTimestamp=False
    target=ROOT/('deva-legacy.ttf' if legacy else 'dev2.ttf')
    builder.font.save(target)
    print(f'Generated original {target.name}: {target.stat().st_size} bytes')


if __name__ == '__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    generate(False); generate(True)
