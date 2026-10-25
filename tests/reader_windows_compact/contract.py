"""Shared report contract; no native UI or artifact operations on import."""
FORMATS={'txt':'Reading sample.txt','epub':'Picture book.epub','pdf':'Fixed page.pdf','cbz':'Large comic.cbz'}
REQUIRED=['library-default-minimal','native-menu-capabilities','system-picker-cancel-preserves-library']
REQUIRED += [kind+'-'+scope for kind in FORMATS for scope in ('native-import','reading-view')]
REQUIRED += ['reading-next-and-previous','keyboard-library-and-resume','expanded-panel-retains-controls',
             'expanded-panel-note-commit','compact-resize-and-focus','small-window-note-editor-remains-reachable','search-native-dialog','navigation-native-dialog',
             'records-native-dialog','settings-native-dialog','restart-restores-compact-reading']


def validate(report,source,run,attempt,candidate):
    assert report['source_sha']==source and str(report['run_id'])==str(run) and str(report['attempt'])==str(attempt)
    assert report['consumer_sha256']==candidate and report['accepted'] is True and not report['problems']
    assert [row['name'] for row in report['checks']]==REQUIRED and all(row['passed'] is True for row in report['checks'])
    assert report['count']==len(REQUIRED) and len({row['name'] for row in report['checks']})==len(REQUIRED)
    assert all(type(row['pid']) is int and row['pid']>0 for row in report['checks'])
    assert report['performance_accepted'] is False and report['complete_product'] is False


def selftest():
    import copy
    good=dict(source_sha='source',run_id=1,attempt=2,consumer_sha256='candidate',accepted=True,problems=[],
              checks=[dict(name=name,passed=True,pid=1) for name in REQUIRED],count=len(REQUIRED),performance_accepted=False,complete_product=False)
    validate(good,'source',1,2,'candidate')
    for mutation in (dict(source_sha='foreign'),dict(attempt=1),dict(consumer_sha256='other'),dict(checks=good['checks'][:-1]),
                     dict(performance_accepted=True),dict(complete_product=True)):
        bad=copy.deepcopy(good);bad.update(mutation)
        try:validate(bad,'source',1,2,'candidate')
        except (AssertionError,KeyError):continue
        raise AssertionError('compact protocol admitted '+str(mutation))
    return 6
