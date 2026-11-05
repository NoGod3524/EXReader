"""D20 evidence contract. Coverage is granted only after actual native readback."""
import os
BASE = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
TARGET = os.environ.get('GITHUB_SHA', '')
D08 = '30158c44dcd9ebf27e028b85f60c4fe374b9c90b'
FORMATS = {'txt': 'Reading sample.txt'}
CONFIGS = [f'{s}-{h}-{w}' for s in (100,150,200) for h in ('normal','high') for w in ('default','small')]
LEGACY = ['dpi','layout','contrast','import-open','search','directory','records','settings','return-focus']
REQUIRED = LEGACY + ['shelf-search','keyboard-shelf','keyboard-reading','page-turn','more','status-shelf','status-reading','status-more']


def actual_scale(readback, percent):
    primary = [m for m in readback.get('monitors', []) if m['primary']]
    return len(primary) == 1 and primary[0]['scale_percent'] == percent and primary[0]['probe_awareness'] == 2 and primary[0]['probe_dpi'] == percent * 96 // 100


def native_focus(value):
    return all(value.get(k) is True for k in ('descendant','visible','enabled'))


def validate(r, source, run, attempt):
    assert r['source_sha'] == r['target_sha'] == source
    assert str(r['run_id']) == str(run) and str(r['attempt']) == str(attempt)
    assert r['seed'] == BASE and r['sdk_source'] == SDK and r['historical_source'] == D08
    assert r['accepted'] is False and r['screen_reader_accepted'] is False
    assert len(r['program_sha256']) == 64 and r['files'] and r['restoration']['high_contrast_restored']
    assert r['restoration']['scale_restored'] and r['restoration']['mode_restored']
    configs = r['configurations']
    assert len(configs) == len(CONFIGS) and {x['configuration'] for x in configs} == set(CONFIGS)
    for c in configs:
        assert set(c['checks']) == set(REQUIRED)
        assert all(v['status'] in ('pass','fail','error','pending') for v in c['checks'].values())
        if c['execution'] == 'not-run-capability-pending':
            assert c['capability']['available'] is False
            assert not c['screenshots'] and all(v['status'] == 'pending' for v in c['checks'].values())
            continue
        assert c['execution'] == 'executed' and c['capability']['available'] is True
        assert actual_scale(c['capability']['readback'], c['requested_scale'])
        assert bool(c['contrast_readback']['flags'] & 1) == (c['requested_contrast'] == 'high')
        assert c['screenshots'] and c['loaded_modules'] and c['actual_transport'] == 'sendinput'
        if c['checks']['dpi']['status'] == 'pass':
            a = c['checks']['dpi']['actual']
            assert a['window_dpi'] == c['requested_scale'] * 96 // 100 and a['monitor_scale']['scale_percent'] == c['requested_scale']
        for key in ('search','directory','records','settings','shelf-search'):
            if c['checks'][key]['status'] == 'pass':
                a = c['checks'][key]['actual']
                assert len(a['focus']) == 3 and all(native_focus(f) for f in a['focus']) and native_focus(a['after'])
        for key in ('keyboard-shelf','keyboard-reading'):
            if c['checks'][key]['status'] == 'pass':
                a = c['checks'][key]['actual']
                assert len(a['forward']) > 1 and len(a['reverse']) > 1
                assert all(native_focus(f) for f in a['forward'] + a['reverse'])
        for key in ('status-shelf','status-reading','status-more'):
            if c['checks'][key]['status'] == 'pass':
                a = c['checks'][key]['actual']
                assert a['visible'] and a['contained'] and a['text'] and a['uia_name'] and a['paint_colors'] > 1
    # 100% is mandatory baseline; unavailable 150/200 is never a green coverage grant.
    assert all(c['execution'] == 'executed' for c in configs if c['requested_scale'] == 100)
    assert r['coverage'] == {str(s): sum(c['execution'] == 'executed' for c in configs if c['requested_scale'] == s) for s in (100,150,200)}
