"""Actions-only refusal regressions for the additional root-review contract."""
import copy
import os
from pathlib import Path
import guard as G
import receipts as R


def refused(operation):
    try:operation()
    except (ValueError,KeyError,TypeError):return
    raise AssertionError('Spoiled evidence was accepted')


def fixture():
    expected=dict(source='f'*40,run='17',attempt='1')
    identity=dict(platform='windows',round=1,consumer_sha=expected['source'],run_id='17',attempt='1',
      job='windows-measure',program_sha256='a'*64,producer_source=G.START,sdk_version='3.41.0',
      stratum='windows/test/4c',shelf_size=500,input_strategy=R.STRATEGY)
    data=dict(schema=1,input_strategy=R.STRATEGY,source_sha=expected['source'],run_id='17',attempt='1',
      launch_counts=dict(R.COUNTS),sizes=[500,5000],startup_navigation_injected=False,
      startup_query_modified=False,inputs={},starts={})
    loaded=dict(identity={key:value for key,value in identity.items() if key!='shelf_size'},launches=[],rows=[])
    preparations={size:dict(catalog_sha256=str(size)[0]*64) for size in (500,5000)}
    surface=dict(window_visible=True,minimized=False,books_visible=True,reading_visible=False,
      query_empty=True,metadata_enabled=True,book_rows=50,legacy_rows=False)
    for size in (500,5000):
        for cohort,count in R.COUNTS.items():
            for index in range(count):
                name='w1-n%d-%s-%02d'%(size,cohort,index)
                strategy=R.STRATEGY if cohort=='warm' else 'original-'+cohort
                loaded['launches'].append(dict(launch=name,shelf_size=size,cohort=cohort,index=index,
                                               profile_strategy=strategy,ok=True))
                item=dict(status='ok',launch=name,size=size,cohort=cohort,profile_strategy=strategy,
                          profile_relative='n%d/profiles/'%size+name)
                if cohort=='warm':item.update(settings_absent=True,catalog_preserved=True,
                  catalog_source_sha256=preparations[size]['catalog_sha256'],
                  catalog_copy_sha256=preparations[size]['catalog_sha256'])
                data['inputs'][name]=item
                if cohort!='resume':
                    marks=dict(window_ms=1.111,rows_ms=2.222,first_screen_interactive_ms=3.333)
                    data['starts'][name]=dict(status='ok',identity=dict(identity,shelf_size=size),
                      input_strategy=R.STRATEGY,navigation_injected=False,query_modified=False,
                      before_original=dict(surface),after_original=dict(surface),marks=marks)
                    for metric,key in (('start_window','window_ms'),('start_first_rows','rows_ms'),
                                       ('start_interactive','first_screen_interactive_ms')):
                        loaded['rows'].append(dict(launch=name,metric=metric,status='ok',ms=marks[key]))
                if cohort!='import':
                    for slot in range(4 if cohort=='resume' else 8):
                        loaded['rows'].append(dict(launch=name,metric='page_turn',slot=slot,status='ok',
                                                  ms=1.0,direction='forward'))
    return data,loaded,expected,preparations


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
    before={'old/source.c':'100644 blob '+'a'*40}
    after=dict(before,**{path:'100644 blob '+'b'*40 for path in G.FILES})
    G.validate_tree(before,after)
    for changed in (dict(after,**{'old/source.c':'100644 blob '+'c'*40}),
                    {key:value for key,value in after.items() if key!='old/source.c'},
                    dict(after,extra='100644 blob '+'d'*40),
                    {key:value for key,value in after.items() if key!=G.WORKFLOW},
                    dict(after,**{G.WORKFLOW:'120000 blob '+'b'*40})):
        refused(lambda changed=changed:G.validate_tree(before,changed))
    original=G.git('show',G.BASE+':'+G.ORIGINAL).decode()
    workflow=(G.ROOT/G.WORKFLOW).read_text(encoding='utf-8')
    assert G.project(workflow)==original
    for old,new in (('timeout-minutes: 170','timeout-minutes: 171'),
                    ('--sdk-version 3.41.0','--sdk-version 3.40.0'),
                    ('max-parallel: 2','max-parallel: 1'),
                    ('python3 tests/reader_final_c02/aggregate.py --self-test','true'),
                    ('--round ${{ matrix.round }}','--round 1')):
        assert old in workflow
        def check(old=old,new=new):G.require(G.project(workflow.replace(old,new))==original,'Projection differs')
        refused(check)
    data,loaded,expected,preparations=fixture()
    assert R.validate(data,loaded,expected,preparations)['launches']==30
    first=next(iter(data['starts']));warm=next(key for key in data['inputs'] if '-warm-' in key)
    surface=dict(data['starts'][first]['before_original'],page_key='')
    assert R.startup_fault(surface) is None
    assert R.startup_fault(dict(surface,window_visible=False,book_rows=0)) is None
    assert R.startup_fault(dict(surface,book_rows=0)) is None
    assert R.startup_fault(dict(surface,book_rows=1,legacy_rows=True)) is None
    assert R.startup_fault(dict(surface,book_rows=1,metadata_enabled=False)) is None
    assert R.startup_fault(dict(surface,book_rows=1,books_visible=False)) is None
    assert R.startup_fault(dict(surface,book_rows=1)) is None
    assert R.startup_fault(dict(surface,query_empty=False))=='C02_STARTUP_QUERY_NOT_CLEAN'
    assert R.startup_fault(dict(surface,reading_visible=True,books_visible=False,page_key='1'))==\
      'C02_STARTUP_READING_SURFACE_INSTEAD_OF_LIBRARY'
    def spoil_data(mutate):
        broken=copy.deepcopy(data);mutate(broken)
        refused(lambda:R.validate(broken,loaded,expected,preparations))
    spoil_data(lambda value:value.update(input_strategy='shared-warm-profile'))
    spoil_data(lambda value:value.update(source_sha='e'*40))
    spoil_data(lambda value:value.update(run_id='18'))
    spoil_data(lambda value:value.update(startup_navigation_injected=True))
    spoil_data(lambda value:value.update(startup_query_modified=True))
    spoil_data(lambda value:value['inputs'].pop(warm))
    spoil_data(lambda value:value['starts'].pop(first))
    spoil_data(lambda value:value['inputs'][warm].update(catalog_copy_sha256='0'*64))
    spoil_data(lambda value:value['inputs'][warm].update(settings_absent=False))
    spoil_data(lambda value:value['inputs'][warm].update(profile_relative='profiles/warm-shared'))
    spoil_data(lambda value:value['starts'][first].update(navigation_injected=True))
    spoil_data(lambda value:value['starts'][first]['after_original'].update(books_visible=False,reading_visible=True))
    spoil_data(lambda value:value['starts'][first]['before_original'].update(query_empty=False))
    spoil_data(lambda value:value['starts'][first]['after_original'].update(book_rows=1))
    spoil_data(lambda value:value['starts'][first]['marks'].update(window_ms=9.0))
    for mutate in (lambda value:value['launches'].pop(),
                   lambda value:value['launches'][0].update(cohort='warm'),
                   lambda value:next(row for row in value['rows'] if row['metric']=='page_turn').update(direction='backward')):
        broken=copy.deepcopy(loaded);mutate(broken)
        refused(lambda:R.validate(data,broken,expected,preparations))
    print('root-review source projection and receipt refusal controls ok')


if __name__=='__main__':main()
