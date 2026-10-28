#!/usr/bin/env python3
"""Original MIT fixtures. Execute ONLY in GitHub Actions, never developer hosts.

Expectations below are handwritten, not obtained from either SDK implementation.
OpenType tables are constructed explicitly so compiler heuristics cannot select
another contextual format. The serialized tables are re-read and authenticated.
"""
import argparse
import hashlib
import json
import os
import fontTools
from pathlib import Path
import struct
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildCoverage, buildSingleSubstSubtable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot

ORDER = ['.notdef', 'space', 'a', 'b', 'c', 'd', 'x', 'y', 'z', 'p', 'q', 'r',
         'a.alt', 'c.alt', 'x.alt', 'z.alt', 'p.alt', 'b.alt']
ORDER += ['filler%d' % n for n in range(len(ORDER), 258)]
ORDER += ['collision']  # gid258 collides with gid2 for every lookup address.
ORDER += ['filler%d' % n for n in range(len(ORDER), 514)]
ORDER += ['collision.miss']  # gid514 first-misses and evicts the gid2 cache entry.
GIDS = {name: index for index, name in enumerate(ORDER)}
CMAP = {32: 'space', **{ord(c): c for c in 'abcdxyzpqr'}, 0xE000: 'collision', 0xE001: 'collision.miss'}

def obj(name, **fields):
    value = getattr(ot, name)()
    value.__dict__.update(fields)
    return value

def cov(name):
    return buildCoverage([name], GIDS)

def chain(inputs, look, target, back=(), sequence=0):
    return obj('ChainContextSubst', Format=3,
               BacktrackGlyphCount=len(back), BacktrackCoverage=[cov(c) for c in back],
               InputGlyphCount=len(inputs), InputCoverage=[cov(c) for c in inputs],
               LookAheadGlyphCount=len(look), LookAheadCoverage=[cov(c) for c in look],
               SubstCount=1, SubstLookupRecord=[obj('SubstLookupRecord',
                   SequenceIndex=sequence, LookupListIndex=target)])

def base_font():
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(ORDER)
    glyphs = {}
    for name in ORDER:
        pen = TTGlyphPen(None)
        if name != 'space':
            pen.moveTo((20, 0)); pen.lineTo((480, 0)); pen.lineTo((480, 400))
            pen.lineTo((20, 400)); pen.closePath()
        glyphs[name] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (500, 0) for name in ORDER})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupCharacterMap(CMAP)
    fb.setupNameTable({'familyName': 'EXReader OT Cache Acceptance',
                      'styleName': 'Regular', 'uniqueFontIdentifier': 'EXReaderOTCacheAcceptance',
                      'fullName': 'EXReader OT Cache Acceptance', 'psName': 'EXReaderOTCacheAcceptance',
                      'copyright': 'Copyright 2026 EXReader contributors; MIT; original outlines'})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost(); fb.setupMaxp()
    fb.font['head'].created = fb.font['head'].modified = 3800000000
    fb.font.recalcTimestamp = False
    table = obj('GSUB', Version=0x00010000,
                ScriptList=obj('ScriptList', ScriptCount=1, ScriptRecord=[obj('ScriptRecord',
                    ScriptTag='DFLT', Script=obj('Script', LangSysCount=0, LangSysRecord=[],
                        DefaultLangSys=obj('LangSys', LookupOrder=None, ReqFeatureIndex=0xffff,
                                           FeatureIndex=[], FeatureCount=0)))]),
                FeatureList=obj('FeatureList', FeatureCount=0, FeatureRecord=[]),
                LookupList=obj('LookupList', LookupCount=0, Lookup=[]))
    fb.font['GSUB'] = newTable('GSUB'); fb.font['GSUB'].table = table
    return fb.font

def lookup(font, kind, subtables):
    table = font['GSUB'].table
    index = len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(obj('Lookup', LookupType=kind, LookupFlag=0,
                                     SubTableCount=len(subtables), SubTable=subtables))
    table.LookupList.LookupCount = index + 1
    return index

def feature(font, tag, index):
    table = font['GSUB'].table
    number = len(table.FeatureList.FeatureRecord)
    table.FeatureList.FeatureRecord.append(obj('FeatureRecord', FeatureTag=tag,
        Feature=obj('Feature', FeatureParams=None, LookupCount=1, LookupListIndex=[index])))
    table.FeatureList.FeatureCount = number + 1
    lang = table.ScriptList.ScriptRecord[0].Script.DefaultLangSys
    lang.FeatureIndex.append(number); lang.FeatureCount = number + 1

def normal_font():
    font = base_font()
    single = lookup(font, 1, [buildSingleSubstSubtable({
        'a': 'a.alt', 'c': 'c.alt', 'x': 'x.alt', 'z': 'z.alt', 'p': 'p.alt', 'b': 'b.alt', 'collision': 'x.alt'})])
    # At least three distinct subtables: all must first-miss for safe memoization.
    main = lookup(font, 6, [chain(['a', 'b'], [], single),
                            chain(['c'], ['d'], single), chain(['x'], ['y'], single)])
    feature(font, 'c001', main)
    # Same glyph, different lookup pointer and different matching context.
    feature(font, 'c002', lookup(font, 6, [chain(['z'], ['a'], single),
                                         chain(['p'], ['q'], single), chain(['collision'], [], single)]))
    # Backtrack must prevent caching a context-dependent miss.
    feature(font, 'c003', lookup(font, 6, [chain(['b'], ['c'], single, back=['a'])]))
    nested = lookup(font, 6, [chain(['p'], ['q'], single)])
    feature(font, 'c004', lookup(font, 6, [chain(['p', 'q'], [], nested)]))
    rule = obj('ChainSubRule', BacktrackGlyphCount=0, Backtrack=[], InputGlyphCount=2,
               Input=['b'], LookAheadGlyphCount=0, LookAhead=[], SubstCount=1,
               SubstLookupRecord=[obj('SubstLookupRecord', SequenceIndex=0, LookupListIndex=single)])
    fmt1 = obj('ChainContextSubst', Format=1, Coverage=cov('a'), ChainSubRuleSetCount=1,
               ChainSubRuleSet=[obj('ChainSubRuleSet', ChainSubRuleCount=1, ChainSubRule=[rule])])
    feature(font, 'c005', lookup(font, 6, [fmt1]))
    classrule = obj('ChainSubClassRule', BacktrackGlyphCount=0, Backtrack=[], InputGlyphCount=2,
                   Input=[2], LookAheadGlyphCount=0, LookAhead=[], SubstCount=1,
                   SubstLookupRecord=[obj('SubstLookupRecord', SequenceIndex=0, LookupListIndex=single)])
    fmt2 = obj('ChainContextSubst', Format=2, Coverage=cov('a'),
               BacktrackClassDef=obj('ClassDef', classDefs={}),
               InputClassDef=obj('ClassDef', classDefs={'a': 1, 'b': 2}),
               LookAheadClassDef=obj('ClassDef', classDefs={}), ChainSubClassSetCount=2,
               ChainSubClassSet=[None, obj('ChainSubClassSet', ChainSubClassRuleCount=1,
                                          ChainSubClassRule=[classrule])])
    feature(font, 'c006', lookup(font, 6, [fmt2]))
    extension = obj('ExtensionSubst', Format=1, ExtensionLookupType=6,
                    ExtSubTable=chain(['a', 'b'], [], single))
    feature(font, 'c007', lookup(font, 7, [extension]))
    return font

def table_offset(data, tag):
    for i in range(struct.unpack_from('>H', data, 4)[0]):
        at = 12 + 16 * i
        if data[at:at+4] == tag:
            return struct.unpack_from('>II', data, at+8)
    raise AssertionError(tag)

def lookup_offset(data, index):
    start, _ = table_offset(data, b'GSUB')
    ll = start + struct.unpack_from('>H', data, start+8)[0]
    return ll + struct.unpack_from('>H', data, ll+2+2*index)[0]

def subtable_offset(data, index, subindex=0):
    at = lookup_offset(data, index)
    return at + struct.unpack_from('>H', data, at+6+2*subindex)[0]

def save(font, root, name, provenance):
    path = root / name
    font.save(path)
    reread = TTFont(path, recalcTimestamp=False)
    raw = path.read_bytes()
    kinds = []
    for i, item in enumerate(reread['GSUB'].table.LookupList.Lookup):
        entry = {'index': i, 'type': item.LookupType, 'subtable_count': item.SubTableCount,
                 'formats': [s.Format if hasattr(s, 'Format') else None for s in item.SubTable]}
        if item.LookupType == 6 and all(s.Format == 3 for s in item.SubTable):
            entry['first_coverage'] = [list(s.InputCoverage[0].glyphs) for s in item.SubTable]
            entry['backtrack_counts'] = [s.BacktrackGlyphCount for s in item.SubTable]
        kinds.append(entry)
    provenance[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'lookups': kinds}
    return raw

def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Fixture generation is restricted to GitHub Actions')
    if fontTools.version != '4.61.1':
        raise SystemExit('Expected fontTools4.61.1, got ' + fontTools.version)
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); root = args.output; root.mkdir(parents=True, exist_ok=True)
    provenance = {}
    normal = normal_font(); raw = save(normal, root, 'cache.ttf', provenance)
    assert provenance['cache.ttf']['lookups'][1]['formats'] == [3, 3, 3]
    assert provenance['cache.ttf']['lookups'][1]['first_coverage'] == [['a'], ['c'], ['x']]
    # Same lookup address: glyph IDs differing by256 collide under actual &255 hash.
    assert GIDS['collision'] - GIDS['a'] == 256
    assert GIDS['collision.miss'] - GIDS['a'] == 512
    # Invalid GSUB offset remains a valid outline/cmap SFNT, reaching SDK table reader.
    damaged = bytearray(raw); start, _ = table_offset(damaged, b'GSUB')
    struct.pack_into('>H', damaged, start+8, 0xffff)
    (root/'broken-lookup.ttf').write_bytes(damaged)
    damaged = bytearray(raw); sub = subtable_offset(damaged, 1, 2)
    # Last subtable is corrupt: earlier valid first misses must NOT cache away error.
    # fmt3: format, backtrackCount0, inputCount, inputCoverageOffset...
    coverage_at = sub + struct.unpack_from('>H', damaged, sub+6)[0]
    struct.pack_into('>H', damaged, coverage_at, 99)
    (root/'broken-coverage.ttf').write_bytes(damaged)
    damaged = bytearray(raw); sub = subtable_offset(damaged, 1)
    struct.pack_into('>H', damaged, sub+4, 257)
    (root/'context-limit.ttf').write_bytes(damaged)
    # A recursive nested lookup must stop at unchanged OT_DEPTH16.
    cycle = base_font(); lookup(cycle, 6, [chain(['a'], [], 0)]); feature(cycle, 'c001', 0)
    save(cycle, root, 'depth-limit.ttf', provenance)
    # 1024 identical first-miss subtables: 65536 glyphs exceed fixed64M work budget.
    budget = base_font(); inner = lookup(budget, 1, [buildSingleSubstSubtable({'a':'a.alt'})])
    feature(budget, 'c001', lookup(budget, 6, [chain(['a'], [], inner) for _ in range(1024)]))
    save(budget, root, 'work-limit.ttf', provenance)
    for name in ('broken-lookup.ttf', 'broken-coverage.ttf', 'context-limit.ttf'):
        data = (root/name).read_bytes()
        provenance[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                            'deliberately_malformed': True}
    cases = []
    def add(name, text, expected, tag='c001', font='cache.ttf', status=0, repeat=1, category='normal'):
        ranges = []; at = 0
        for ch in text:
            end = at + len(ch.encode('utf8')); ranges.append([at, end]); at = end
        case = {'id':name, 'font':font, 'text_hex':text.encode('utf8').hex(), 'feature':tag,
                'repeat':repeat, 'expected_status':status, 'category':category}
        if expected is not None:
            case.update(expected_glyphs=expected, expected_ranges=ranges, expected_flags=[0]*len(expected),
                        expected_advances=[[10.0,0.0] for _ in expected],
                        expected_offsets=[[0.0,0.0] for _ in expected])
        cases.append(case)
    add('all_miss', 'zz', [8,8])
    add('first_matches_input_misses', 'ac', [2,4])
    add('first_matches_lookahead_misses', 'cx', [4,6])
    add('match_first_subtable', 'ab', [12,3])
    add('match_second_subtable', 'cd', [13,5])
    add('match_third_subtable', 'xy', [14,7])
    add('different_glyph_miss', 'rr', [11,11])
    add('collision_low', 'a', [2], 'c002')
    add('collision_high', '\ue000', [14], 'c002')
    add('collision_evict', '\ue001', [514], 'c002')
    add('collision_mix', 'a\ue000ab', [2,14,2,3], 'c002')
    add('other_lookup_hit', 'za', [15,2], 'c002')
    add('other_lookup_miss', 'zb', [8,3], 'c002')
    add('backtrack_absent', 'bc', [3,4], 'c003')
    add('backtrack_wrong', 'xbc', [6,3,4], 'c003')
    add('backtrack_hit', 'abc', [2,17,4], 'c003')
    add('nested_miss', 'pr', [9,11], 'c004')
    add('nested_hit', 'pq', [16,10], 'c004')
    for tag in ('c005', 'c006', 'c007'):
        add(tag+'_miss', 'ac', [2,4], tag)
        add(tag+'_hit', 'ab', [12,3], tag)
    add('broken_lookup', 'ab', None, font='broken-lookup.ttf', status=8, category='malformed')
    add('broken_coverage', 'z', None, font='broken-coverage.ttf', status=8, category='malformed')
    add('context_limit', 'ab', None, font='context-limit.ttf', status=6, category='limit')
    add('depth_limit', 'a', None, font='depth-limit.ttf', status=6, category='limit')
    add('work_limit', 'z', None, font='work-limit.ttf', status=6, repeat=65536, category='work_limit')
    add('cancellation_work', 'z', None, font='work-limit.ttf', status=0, repeat=4096, category='cancel_source')
    scenarios = [
        {'id':'alternating_contexts', 'steps':['all_miss','first_matches_input_misses','match_first_subtable',
             'first_matches_lookahead_misses','match_second_subtable','match_third_subtable','all_miss']},
        {'id':'cache_collision', 'steps':['collision_low','collision_evict','collision_low','collision_evict','collision_high',
             'collision_mix','match_first_subtable']},
        {'id':'lookup_identity', 'steps':['all_miss','other_lookup_hit','other_lookup_miss','other_lookup_hit','all_miss']},
        {'id':'backtrack_context', 'steps':['backtrack_absent','backtrack_wrong','backtrack_hit','backtrack_absent','backtrack_hit']},
        {'id':'nested_context', 'steps':['nested_miss','nested_hit','nested_miss','nested_hit']},
        {'id':'other_formats', 'steps':[x for tag in ('c005','c006','c007') for x in (tag+'_miss',tag+'_hit')]},
    ]
    manifest = {'schema':1, 'font_size':20, 'units_per_em':1000, 'glyph_order':ORDER,
                'license':'MIT; original rectangular outlines; no downloaded font data',
                'generator_dependency':'fontTools==4.61.1', 'generator_dependency_actual':fontTools.version,
                'acceptance_source_sha':os.environ.get('GITHUB_SHA'),
                'generator_normalized_lf_sha256':hashlib.sha256(Path(__file__).read_text(encoding='utf8').replace('\r\n','\n').encode('utf8')).hexdigest(),
                'fonts':provenance,
                'expected_method':'Handwritten glyph IDs and geometry, never derived from baseline/candidate SDK output',
                'cache_collision_proof':{'glyph_ids':[2,258,514], 'formula':'(((uintptr_t)lookup >> 4) ^ glyph) & 255',
                    'same_slot_for_all_lookup_addresses':True},
                'cases':cases, 'scenarios':scenarios}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'generated':str(root), 'case_count':len(cases), 'fonts':list(provenance)},sort_keys=True))

if __name__ == '__main__':
    main()
