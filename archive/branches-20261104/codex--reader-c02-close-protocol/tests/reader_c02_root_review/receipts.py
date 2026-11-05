"""Additional input/visible-surface contract; old sample and aggregate rules remain required."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_final_c02'))
import common as K

STRATEGY='warm-catalog-snapshot-clean-settings-v1'
COUNTS={'cold':4,'warm':4,'resume':4,'import':3}


def diagnostic_identity(value,expected):
    K.require(value.get('schema')==1 and value.get('source_sha')==expected['source'] and
      str(value.get('run_id'))==str(expected['run']) and str(value.get('attempt'))==str(expected['attempt']),
      'Foreign diagnostic timeline identity')


def startup_fault(value):
    # CreateWindow exposes initially-enabled buttons before ShowWindow/reload_shelf.
    # Partial rows do not prove completion; only the frozen readiness helper
    # decides when >=50 product rows are ready.
    if not value['window_visible'] or value['minimized']:return None
    if not value['query_empty']:return 'C02_STARTUP_QUERY_NOT_CLEAN'
    if value['reading_visible'] and value['page_key']:
        return 'C02_STARTUP_READING_SURFACE_INSTEAD_OF_LIBRARY'
    return None


def natural(value):
    K.require(value.get('window_visible') is True and value.get('minimized') is False and
      value.get('books_visible') is True and value.get('reading_visible') is False and
      value.get('query_empty') is True,'Natural visible library/query-empty surface missing')


def validate(data,loaded,expected,preparations):
    K.require(data.get('schema')==1 and data.get('input_strategy')==STRATEGY,'Old/shared input strategy cannot count')
    K.require(data.get('source_sha')==expected['source'] and str(data.get('run_id'))==str(expected['run']) and
              str(data.get('attempt'))==str(expected['attempt']),'Foreign input receipt identity')
    K.require(data.get('launch_counts')==COUNTS and sorted(data.get('sizes',[]))==[500,5000], 'Sampling plan differs')
    K.require(data.get('startup_navigation_injected') is False and data.get('startup_query_modified') is False,
              'Synthetic startup navigation/query modification is forbidden')
    launches=loaded['launches'];inputs=data.get('inputs',{});starts=data.get('starts',{})
    K.require(len(launches)==30 and len({row['launch'] for row in launches})==30,'Incomplete/duplicate Windows launches')
    for size in (500,5000):
        for cohort,count in COUNTS.items():
            selected=[row for row in launches if row['shelf_size']==size and row['cohort']==cohort]
            K.require(len(selected)==count and sorted(row['index'] for row in selected)==list(range(count)),
                      'Per-size/cohort frozen sampling plan differs')
    K.require(set(inputs)=={row['launch'] for row in launches},'Missing/extra per-launch input receipts')
    expected_starts={row['launch'] for row in launches if row['cohort']!='resume'}
    K.require(set(starts)==expected_starts and len(starts)==22,'Missing/extra natural startup receipts')
    for launch in launches:
        name=launch['launch'];size=launch['shelf_size'];cohort=launch['cohort'];item=inputs[name]
        K.require(item['launch']==name and item['cohort']==cohort and item['size']==size,'Input receipt launch differs')
        K.require(item['status']=='ok' and item['profile_strategy']==launch['profile_strategy'],'Failed input preparation')
        if cohort=='warm':
            K.require(item['profile_strategy']==STRATEGY and item.get('settings_absent') is True and
              item.get('catalog_preserved') is True and item.get('catalog_source_sha256')==preparations[size]['catalog_sha256'] and
              item.get('catalog_copy_sha256')==item.get('catalog_source_sha256'),'Warm catalog snapshot/settings proof missing')
            K.require(item['profile_relative'].endswith('/'+name),'Warm launch reused an old/shared profile')
        if cohort=='resume':continue
        value=starts[name]
        K.require(value.get('status')=='ok' and value.get('input_strategy')==STRATEGY,'Startup observation failed')
        K.assert_identity(value['identity'],expected['source'],expected['run'],expected['attempt'])
        K.require(value['identity']['input_strategy']==STRATEGY and value['identity']['shelf_size']==size,
                  'Startup receipt strategy/size differs')
        K.require(value.get('navigation_injected') is False and value.get('query_modified') is False,'Fabricated startup surface')
        natural(value['before_original']);natural(value['after_original'])
        after=value['after_original']
        K.require(after['metadata_enabled'] and after['book_rows']>=50 and not after['legacy_rows'], 'Original ready/rows not met')
        marks=value['marks']
        for metric,key in (('start_window','window_ms'),('start_first_rows','rows_ms'),('start_interactive','first_screen_interactive_ms')):
            rows=[row for row in loaded['rows'] if row['launch']==name and row['metric']==metric]
            K.require(len(rows)==1 and rows[0]['status']=='ok' and rows[0]['ms']==round(marks[key],3),'Raw sample not bound to real startup receipt')
    for row in loaded['rows']:
        if row['metric']=='page_turn' and row['status']=='ok':
            K.require(row.get('direction')=='forward','169 forward turns were mixed with backward data')
    K.require(loaded['identity'].get('input_strategy')==STRATEGY,'Round identity lacks strategy segregation')
    return dict(input_strategy=STRATEGY,launches=30,natural_starts=22,warm_catalog_launches=8,
                resume_direction='four-forward',startup_navigation_injected=False)
