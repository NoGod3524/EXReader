"""Preserve the five omitted G1 suites, their raw reports and actual binaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PHASES = ('fresh', 'relocated')
REPORT_TAILS = ('phase.json', 'result.json', 'chain.json', 'codec/result.json',
    'thumbnails/result.json', 'thumbnails/probe.json',
    'reading-commands/summary.json', 'reading-commands/report.json',
    'annotation-view/summary.json', 'annotation-view/work/report.json',
    'annotation-export/result.json', 'local-downloads/report.json',
    'local-regressions/regressions.json')
BUILDS = {
    'chain': ('g1-chain', 'g1-codec-only'),
    'thumbnails': ('thumb-probe', 'thumb-c-consumer', 'thumb-regress', 'thumb-fault'),
    'reading-commands': ('reading-commands-probe', 'reading-commands-c-consumer'),
    'annotation-view': ('annotation-view-probe', 'annotation-view-c-consumer'),
    'annotation-export': ('annotation-export-probe', 'annotation-export-c-consumer'),
    'local-downloads': ('ld-probe', 'ld-cpp-consumer'),
    'old-consumer': ('ld-probe',),
}
BINARY_KEYS = {(folder + '/' + name): ('old-ld-probe' if folder == 'old-consumer' else name)
               for folder, names in BUILDS.items() for name in names}
RAW_TAILS = ('g1-chain.map', 'g1-codec.map') + tuple('binaries/' + key for key in BINARY_KEYS.values())
REPORTS = ['g1/' + phase + '/' + name for phase in PHASES for name in REPORT_TAILS]
RAW = ['g1/' + phase + '/' + name for phase in PHASES for name in RAW_TAILS]


def load(folder, filename):
    path = ROOT / 'tests' / folder / filename
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('g1_review_' + folder + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(doc, hashes, source, run, attempt, platform):
    def need(ok, message):
        if not ok:
            raise ValueError('retained G1: ' + message)

    def identity(report):
        value = report.get('identity', report)
        need(value.get('GITHUB_SHA', value.get('source_sha', value.get('source'))) == source,
             'source differs')
        need(str(value.get('GITHUB_RUN_ID', value.get('run_id', value.get('run')))) == str(run) and
             str(value.get('GITHUB_RUN_ATTEMPT', value.get('attempt'))) == str(attempt), 'run/attempt differs')

    def passed(rows, field='pass'):
        names = [row['name'] for row in rows]
        need(bool(names) and len(names) == len(set(names)) and all(row.get(field) is True for row in rows),
             'missing/duplicate/failing named check')
        return names

    original = load('reader_g1_integration', 'aggregate.py')
    thumb = load('reader_thumbnails', 'check_thumbnails.py')
    commands = load('reader_reading_commands', 'check_reading_commands.py')
    view = load('reader_annotation_view', 'check_annotation_view.py')
    local = load('reader_local_downloads', 'check_local_downloads.py')
    counts = {}
    for phase in PHASES:
        base = 'g1/' + phase + '/'
        d = lambda name: doc[base + name]
        h = lambda name: hashes[base + name]
        b = lambda name: h('binaries/' + name)
        pr = d('phase.json'); identity(pr)
        need(pr.get('phase') == phase and pr.get('platform') == platform and pr.get('accepted') is True,
             'phase/platform/refusal differs')
        # The immutable original runner's initial mode includes all five judges;
        # invoke that exact mode at both physical prefix locations.
        original.validate(d('result.json'), 'initial', source, run, attempt)
        need(d('result.json')['platform'] == platform, 'original platform differs')
        for name, digest in d('result.json')['consumers'].items():
            need('/' not in name and '\\' not in name, 'unsafe original consumer key')
            key = name[:-4] if name.endswith('.exe') else name
            need(digest == (b(key) if key in BINARY_KEYS.values() else h(name)), 'original consumer hash differs')
        chain = d('chain.json')
        need(chain.get('failures') == 0 and chain.get('resolved_state') == 'FOUND' and
             chain.get('check_count') == len(chain.get('checks', [])) and len(chain['checks']) >= 20,
             'chain failed')
        passed(chain['checks'])
        codec = d('codec/result.json'); identity(codec)
        need(codec.get('accepted') is True and codec.get('sdk_symbols') is False and
             len(codec.get('sqlite_providers', [])) == 1 and
             codec['consumer_sha256'] == b('g1-codec-only') and codec['map_sha256'] == h('g1-codec.map'),
             'SDK-free codec or actual bytes differ')
        tr = d('thumbnails/result.json'); identity(tr)
        need(tr.get('accepted') is True and tr.get('granted_platform') == platform.lower() and
             tr.get('checks') == len(tr.get('check_names', [])), 'thumbnail summary refused')
        names = passed(d('thumbnails/probe.json')['checks'])
        need(names == tr['check_names'] and d('thumbnails/probe.json')['failures'] == 0,
             'thumbnail raw checks differ')
        need(all(sum(n.startswith(prefix) for n in names) >= count for prefix, count in thumb.REQUIRED_PREFIXES.items()) and
             set(thumb.REQUIRED_EXACT).issubset(names),
             'thumbnail original categories missing')
        for field, required in [('regress_results', thumb.REQUIRED_REGRESS), ('fault_results', thumb.REQUIRED_FAULT)]:
            need(set(required).issubset(passed(tr[field])), 'thumbnail regression/fault missing')
        for field, name in [('probe_sha256', 'thumb-probe'), ('c_consumer_sha256', 'thumb-c-consumer'),
                            ('regress_sha256', 'thumb-regress'), ('fault_sha256', 'thumb-fault')]:
            need(tr[field] == b(name), 'thumbnail binary differs')
        cr = d('reading-commands/summary.json'); identity(cr)
        raw = d('reading-commands/report.json'); names = passed(raw['checks'])
        need(cr.get('reading_commands_accepted') is True and not cr.get('problems') and
             cr.get('checks_failed') == raw.get('failures') == 0 and cr.get('checks_total') == len(names),
             'reading commands refused')
        need(all(any(n.startswith(required) for n in names) for required in commands.REQUIRED_CHECKS),
             'reading command original checks missing')
        need({r['label'] for r in raw['cases']} == set(commands.LABELS) and
             all(r.get('passed') is True for r in raw['cases']), 'reading command cases differ')
        need(cr['probe_sha256'] == b('reading-commands-probe') and
             cr['c_consumer_sha256'] == b('reading-commands-c-consumer') and
             cr['report_sha256'] == pr['reports']['reading-commands/report.json'], 'reading command actual bytes differ')
        vr = d('annotation-view/summary.json'); identity(vr)
        raw = d('annotation-view/work/report.json'); names = passed(raw['checks'])
        need(vr.get('annotation_view_accepted_on_this_platform') is True and not vr.get('problems') and
             raw.get('complete') is True and raw.get('checks_failed') == 0 and
             set(view.REQUIRED).issubset(names), 'annotation view refused')
        need(vr['probe_sha256'] == b('annotation-view-probe') and
             vr['c_consumer_sha256'] == b('annotation-view-c-consumer') and
             vr['report_sha256'] == pr['reports']['annotation-view/work/report.json'], 'annotation view actual bytes differ')
        er = d('annotation-export/result.json'); identity(er)
        need(er.get('accepted') is True and er.get('database_unchanged') is True and
             er.get('count') == len(er.get('checks', [])) and er.get('count', 0) > 0 and
             len(er['checks']) == len(set(er['checks'])), 'annotation export refused')
        lr = d('local-downloads/report.json'); identity(lr)
        need(lr.get('ok') is True and passed(lr['checks'], 'ok') == local.EXPECTED_CHECKS,
             'local download original checks differ')
        need(lr['consumer_sha256']['probe'] == b('ld-probe') and lr['consumer_sha256']['cpp'] == b('ld-cpp-consumer'),
             'local download binary differs')
        rr = d('local-regressions/regressions.json'); identity(rr)
        need(rr.get('ok') is True and not rr.get('failures') and rr['old_probe_sha256'] == b('old-ld-probe') and
             rr['new_probe_sha256'] == b('ld-probe'), 'local old-build control differs')
        counts[phase] = dict(chain=len(chain['checks']), thumbnails=tr['checks'],
            thumbnail_regressions=tr['regress_checks'], thumbnail_faults=tr['fault_checks'],
            reading_commands=cr['checks_total'], annotation_view=vr['checks_total'],
            annotation_export=er['count'], local_downloads=len(lr['checks']),
            local_regressions=len(rr['cases']))
    return counts
