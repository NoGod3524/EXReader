#!/usr/bin/env python3
"""Generate original OpenType shaping fixtures (developer-only fontTools dependency).

No system font outlines are used. The committed fonts are sufficient for C tests.
"""
# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import struct

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildCoverage, buildSinglePosSubtable, buildSingleSubstSubtable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import ValueRecord

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/shaping'
ORDER = [
    '.notdef', 'space', 'A', 'V', 'f', 'i', 'ffi', 'fi', 'a', 'b', 'c', 'd',
    'x', 'y', 'z', 'acute', 'grave', 'dot', 'beh', 'beh.isol', 'beh.init',
    'beh.medi', 'beh.fina', 'lam', 'lam.isol', 'lam.init', 'lam.medi',
    'lam.fina', 'alef', 'alef.isol', 'alef.fina', 'lamalef', 'lamalef.fina',
    'fatha', 'zwj', 'zwnj', 'hebrew_alef', 'hebrew_bet', 'hebrew_gimel',
    'parenleft', 'parenright',
]
CMAP = {
    32: 'space', 65: 'A', 86: 'V', 102: 'f', 105: 'i', 97: 'a', 98: 'b',
    99: 'c', 100: 'd', 120: 'x', 121: 'y', 122: 'z', 0x301: 'acute',
    0x300: 'grave', 0x307: 'dot', 0x628: 'beh', 0x644: 'lam', 0x627: 'alef',
    0x64E: 'fatha', 0x200D: 'zwj', 0x200C: 'zwnj', 0x5D0: 'hebrew_alef',
    0x5D1: 'hebrew_bet', 0x5D2: 'hebrew_gimel', 40: 'parenleft', 41: 'parenright',
}
WIDTHS = {name: 500 for name in ORDER}
WIDTHS.update(space=250, A=600, V=600, f=300, i=200, ffi=750, fi=450,
              acute=0, grave=0, dot=0, fatha=0, zwj=0, zwnj=0,
              lamalef=700, **{'lamalef.fina': 750})
for name in ORDER:
    if name.startswith(('beh', 'lam.')) or name == 'lam':
        WIDTHS[name] = 600
    if name.startswith('alef'):
        WIDTHS[name] = 400

FEATURES = r'''
languagesystem DFLT dflt;
languagesystem latn dflt;
languagesystem arab dflt;

@BASE = [A V f i a b c d x y z beh beh.isol beh.init beh.medi beh.fina
         lam lam.isol lam.init lam.medi lam.fina alef alef.isol alef.fina
         hebrew_alef hebrew_bet hebrew_gimel parenleft parenright];
@LIGATURE = [ffi fi lamalef lamalef.fina];
@MARK = [acute grave dot fatha];
table GDEF { GlyphClassDef @BASE, @LIGATURE, @MARK, ; } GDEF;

lookup LatinLigatures {
    lookupflag IgnoreMarks;
    sub f f i by ffi;
    sub f i by fi;
} LatinLigatures;
feature liga { lookup LatinLigatures; } liga;
feature isol {
    script arab;
    sub beh by beh.isol; sub lam by lam.isol; sub alef by alef.isol;
} isol;
feature init {
    script arab;
    sub beh by beh.init; sub lam by lam.init;
} init;
feature medi {
    script arab;
    sub beh by beh.medi; sub lam by lam.medi;
} medi;
feature fina {
    script arab;
    sub beh by beh.fina; sub lam by lam.fina; sub alef by alef.fina;
} fina;
feature rlig {
    lookupflag IgnoreMarks;
    sub lam.init alef.fina by lamalef;
    sub lam.medi alef.fina by lamalef.fina;
} rlig;

markClass [acute grave fatha] <anchor 0 0> @TOP;
markClass dot <anchor 20 10> @DOT;
feature mark {
    pos base a <anchor 300 700> mark @TOP;
    pos base A <anchor 350 800> mark @TOP;
    pos base [beh beh.isol beh.init beh.medi beh.fina]
        <anchor 300 600> mark @TOP;
    pos ligature fi <anchor 100 650> mark @TOP
        ligComponent <anchor 380 650> mark @TOP;
    pos ligature ffi <anchor 100 650> mark @TOP
        ligComponent <anchor 350 650> mark @TOP
        ligComponent <anchor 650 650> mark @TOP;
} mark;
feature mkmk {
    pos mark [acute grave fatha] <anchor 100 200> mark @DOT;
} mkmk;
feature kern { pos A V -100; } kern;

feature ss01 { sub x by a b; } ss01;
feature ss02 { sub y from [a b c]; } ss02;
feature ss03 { sub z by d; } ss03;
feature ss04 { sub a b' by c; } ss04;
feature ss05 { sub a b' c by d; } ss05;
feature ss06 { rsub a b' c by d; } ss06;
lookup ExtendedSubstitution useExtension { sub z by x; } ExtendedSubstitution;
feature ss07 { lookup ExtendedSubstitution; } ss07;
feature ss08 { pos x <20 30 40 50>; } ss08;
@LEFT = [a b];
@RIGHT = [c d];
feature ss09 { pos @LEFT @RIGHT -80; } ss09;
lookup ContextPosition { pos b <20 30 0 0>; } ContextPosition;
feature ss10 { pos a b' lookup ContextPosition c; } ss10;
lookup ExtendedPosition useExtension { pos z <30 40 0 0>; } ExtendedPosition;
feature ss11 { lookup ExtendedPosition; } ss11;
feature ss12 {
    pos cursive x <anchor 0 0> <anchor 450 100>;
    pos cursive y <anchor 50 20> <anchor 480 120>;
} ss12;
'''


def build(features=FEATURES):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(ORDER)
    glyphs = {}
    for name in ORDER:
        pen = TTGlyphPen(None)
        if name not in ('space', 'zwj', 'zwnj'):
            width = WIDTHS[name] or 120
            pen.moveTo((20, 0))
            pen.lineTo((max(40, width - 20), 0))
            pen.lineTo((max(40, width - 20), 400))
            pen.lineTo((20, 400))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (WIDTHS[name], 0) for name in ORDER})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap(CMAP)
    builder.setupNameTable({
        'familyName': 'EXR Shaping Oracle', 'styleName': 'Regular',
        'uniqueFontIdentifier': 'EXRShapingOracle', 'fullName': 'EXR Shaping Oracle',
        'psName': 'EXRShapingOracle',
        'copyright': 'Copyright 2026 EXReader contributors; GPL-3.0-only',
    })
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                     usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    addOpenTypeFeaturesFromString(builder.font, features)
    context_formats(builder.font)
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.font.recalcTimestamp = False
    return builder.font


def context_formats(font):
    """Encode the same independent rule using each OpenType context representation."""
    glyph_map = font.getReverseGlyphMap()

    def object_of(name, **fields):
        obj = getattr(ot, name)()
        obj.__dict__.update(fields)
        return obj

    def coverage(glyph):
        return buildCoverage([glyph], glyph_map)

    def add_lookup(table, kind, subtable):
        lookups = table.LookupList.Lookup
        index = len(lookups)
        lookups.append(object_of('Lookup', LookupType=kind, LookupFlag=0,
                                 SubTable=[subtable], SubTableCount=1))
        table.LookupList.LookupCount = len(lookups)
        return index

    def feature(table, tag, index):
        records = table.FeatureList.FeatureRecord
        number = len(records)
        records.append(object_of('FeatureRecord', FeatureTag=tag,
                                 Feature=object_of('Feature', FeatureParams=None,
                                                  LookupListIndex=[index], LookupCount=1)))
        table.FeatureList.FeatureCount = len(records)
        for record in table.ScriptList.ScriptRecord:
            systems = [record.Script.DefaultLangSys]
            systems.extend(item.LangSys for item in record.Script.LangSysRecord)
            for system in systems:
                if system is not None:
                    system.FeatureIndex.append(number)
                    system.FeatureCount = len(system.FeatureIndex)

    for position, table_tag in enumerate(('GSUB', 'GPOS')):
        table = font[table_tag].table
        prefix, record_name, record_count = (('Sub', 'SubstLookupRecord', 'SubstCount')
                                             if not position else ('Pos', 'PosLookupRecord', 'PosCount'))
        if not position:
            target = add_lookup(table, 1, buildSingleSubstSubtable({'b': 'd'}))
        else:
            value = ValueRecord()
            value.XPlacement, value.YPlacement = 20, 30
            target = add_lookup(table, 1, buildSinglePosSubtable(
                {'b': value}, glyph_map))

        def records(sequence):
            return [object_of(record_name, SequenceIndex=sequence, LookupListIndex=target)]

        for fmt in (1, 2, 3):
            sub = object_of('Context' + ('Subst' if not position else 'Pos'), Format=fmt)
            if fmt == 1:
                rule = object_of(prefix + 'Rule', GlyphCount=2, Input=['b'],
                                 **{record_count: 1, record_name: records(1)})
                sub.Coverage = coverage('a')
                setattr(sub, prefix + 'RuleSet', [object_of(prefix + 'RuleSet',
                        **{prefix + 'RuleCount': 1, prefix + 'Rule': [rule]})])
                setattr(sub, prefix + 'RuleSetCount', 1)
            elif fmt == 2:
                rule = object_of(prefix + 'ClassRule', GlyphCount=2, Class=[2],
                                 **{record_count: 1, record_name: records(1)})
                sub.Coverage = coverage('a')
                sub.ClassDef = object_of('ClassDef', classDefs={'a': 1, 'b': 2})
                setattr(sub, prefix + 'ClassSet', [None, object_of(prefix + 'ClassSet',
                        **{prefix + 'ClassRuleCount': 1, prefix + 'ClassRule': [rule]})])
                setattr(sub, prefix + 'ClassSetCount', 2)
            else:
                sub.GlyphCount = 2
                sub.Coverage = [coverage('a'), coverage('b')]
                setattr(sub, record_name, records(1))
                setattr(sub, record_count, 1)
            index = add_lookup(table, 5 if not position else 7, sub)
            feature(table, 'zz%02d' % (1 + position*5 + fmt-1), index)

        for fmt in (2, 3):
            sub = object_of('ChainContext' + ('Subst' if not position else 'Pos'), Format=fmt)
            if fmt == 2:
                sub.Coverage = coverage('b')
                sub.BacktrackClassDef = object_of('ClassDef', classDefs={'a': 1})
                sub.InputClassDef = object_of('ClassDef', classDefs={'b': 1})
                sub.LookAheadClassDef = object_of('ClassDef', classDefs={'c': 1})
                rule = object_of('Chain' + prefix + 'ClassRule', BacktrackGlyphCount=1,
                                 Backtrack=[1], InputGlyphCount=1, Input=[],
                                 LookAheadGlyphCount=1, LookAhead=[1],
                                 **{record_count: 1, record_name: records(0)})
                setattr(sub, 'Chain' + prefix + 'ClassSet', [None,
                        object_of('Chain' + prefix + 'ClassSet',
                                  **{'Chain' + prefix + 'ClassRuleCount': 1,
                                     'Chain' + prefix + 'ClassRule': [rule]})])
                setattr(sub, 'Chain' + prefix + 'ClassSetCount', 2)
            else:
                sub.BacktrackGlyphCount = sub.InputGlyphCount = sub.LookAheadGlyphCount = 1
                sub.BacktrackCoverage = [coverage('a')]
                sub.InputCoverage = [coverage('b')]
                sub.LookAheadCoverage = [coverage('c')]
                setattr(sub, record_name, records(0))
                setattr(sub, record_count, 1)
            index = add_lookup(table, 6 if not position else 8, sub)
            feature(table, 'zz%02d' % (4 + position*5 + fmt-2), index)


def broken_lookup(source, tag, field=8):
    data = bytearray(source)
    count = struct.unpack_from('>H', data, 4)[0]
    for i in range(count):
        entry = 12 + 16 * i
        if data[entry:entry+4] == tag.encode('ascii'):
            offset, size = struct.unpack_from('>II', data, entry+8)
            assert size > 10
            # Corrupt a relative table offset; outlines/cmap remain loadable.
            struct.pack_into('>H', data, offset+field, 0xFFFF)
            return data
    raise AssertionError(tag)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    font = build()
    path = ROOT / 'shaping.ttf'
    font.save(path)
    original = path.read_bytes()
    for tag in ('GSUB', 'GPOS'):
        (ROOT / ('broken-' + tag.lower() + '.ttf')).write_bytes(broken_lookup(original, tag))
    boundary_features = FEATURES.replace('feature kern { pos A V -100; } kern;', r'''
feature kern { pos A <0 0 -100 0> V <120 80 -50 0>; } kern;
feature curs {
    pos cursive x <anchor 0 0> <anchor 450 100>;
    pos cursive y <anchor 50 20> <anchor 480 120>;
    pos cursive [beh.isol beh.init beh.medi beh.fina]
        <anchor 20 30> <anchor 550 100>;
} curs;
''')
    build(boundary_features).save(ROOT / 'line-boundary.ttf')
    flags_features = FEATURES + r"""
@TOPFILTER = [acute grave fatha];
feature ss13 { lookupflag IgnoreBaseGlyphs; sub f i by fi; } ss13;
feature ss14 { lookupflag IgnoreLigatures; sub fi by a; } ss14;
feature ss15 {
    lookupflag MarkAttachmentType @TOPFILTER;
    sub a dot' by grave; sub a acute' by grave;
} ss15;
feature ss16 {
    lookupflag UseMarkFilteringSet @TOPFILTER;
    sub a dot' by grave; sub a acute' by grave;
} ss16;
feature ss17 { lookupflag RightToLeft; sub a by b; } ss17;
feature ss18 { sub a dot' by grave; } ss18;
"""
    build(flags_features).save(ROOT / 'lookup-flags.ttf')
    (ROOT / 'broken-gdef.ttf').write_bytes(broken_lookup(original, 'GDEF', 4))
    (ROOT / 'broken-mark-sets.ttf').write_bytes(broken_lookup((ROOT / 'lookup-flags.ttf').read_bytes(), 'GDEF', 12))
    lookups = {}
    for tag in ('GSUB', 'GPOS'):
        lookups[tag] = [{'type': lookup.LookupType,
                         'formats': [getattr(subtable, 'Format', None)
                                     for subtable in lookup.SubTable]}
                        for lookup in font[tag].table.LookupList.Lookup]
    manifest = {'units_per_em': 1000, 'glyph_order': ORDER, 'widths': WIDTHS,
                'lookups': lookups,
                'sha256': {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                           for file in sorted(ROOT.glob('*.ttf'))}}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Generated original shaping fonts, line-boundary variant and invalid lookup variants.')


if __name__ == '__main__':
    main()
