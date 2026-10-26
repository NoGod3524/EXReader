import hashlib, io, json, os, sqlite3, subprocess, zipfile
from pathlib import Path

out=Path('build/organization-summary');out.mkdir(parents=True,exist_ok=True)
result={'accepted':False,'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'problems':[]}
try:
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ['WINDOWS_RESULT']=='success'
    identity=os.environ['ARTIFACT_ID'];digest=os.environ['ARTIFACT_DIGEST'].removeprefix('sha256:')
    api='repos/%s/actions/artifacts/%s'%(os.environ['GITHUB_REPOSITORY'],identity)
    meta=json.loads(subprocess.check_output(['gh','api',api],text=True))
    assert str(meta['workflow_run']['id'])==result['run'] and meta['workflow_run']['head_sha']==result['source'] and not meta['expired']
    assert meta['name']=='windows-organization-%s-%s'%(result['run'],result['attempt'])
    raw=subprocess.check_output(['gh','api',api+'/zip'],timeout=360)
    assert len(raw)==meta['size_in_bytes'] and hashlib.sha256(raw).hexdigest()==digest and meta['digest']=='sha256:'+digest
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        def read(path):return z.read(path)
        def sha(path):return hashlib.sha256(read(path)).hexdigest()
        report=json.loads(read('organization-ui/report.json'));built=json.loads(read('c09/report.json'))
        assert report['accepted'] and not report['problems'] and report['source_sha']==result['source'] and str(report['run_id'])==result['run'] and str(report['attempt'])==result['attempt']
        assert built['accepted'] and not built['failures'] and built['source_sha']==result['source'] and str(built['run_id'])==result['run'] and str(built['attempt'])==result['attempt']
        assert built['cloud_content_bound'] and report['program_sha256']==built['program_sha256']==sha('c09/package/EXReader/EXReader.exe')
        assert 'reader_organization_project_page_raw_v3' in read('c09/wave3-host/windows-host.map').decode('utf-8',errors='replace')
        cloud=json.loads(read('cloud-ui/report.json'))
        assert cloud['accepted'] and not cloud['problems'] and cloud['source_sha']==result['source'] and str(cloud['run_id'])==result['run'] and str(cloud['attempt'])==result['attempt']
        assert cloud['program_sha256']==report['program_sha256'] and cloud['probe_sha256']==sha('cloud-readback/cloud-probe.exe')
        assert cloud['installed_libraries'] and all(sha(path)==value for path,value in cloud['installed_libraries'].items())
        for audit_name,folder in (('public_readback','readback'),('public_readback_after','readback-after')):
            audit=cloud[audit_name];assert audit['ok']==1 and len(audit['books'])==9 and all(book['read_ok']==1 for book in audit['books'])
            assert {sha('cloud-ui/'+folder+'/book-%d.bin'%book['id']) for book in audit['books']}==set(cloud['inputs'].values())
        expected={'producer-book-sync','unresolved-history-not-complete','hierarchy-and-pagination','three-memberships','unsafe-tags-not-projected','native-organizer-shows-remote-tag','native-organizer-shows-hierarchy','native-organizer-shows-series','retry-after-history-resolution','membership-tombstone-applied','book-tombstone-soft-deletes','deleted-book-removed-from-shelf','deleted-book-original-retained','book-explicit-restore','restored-book-visible','group-tombstones-applied','group-explicit-restores','pending-local-intent-blocks-receive','retry-after-local-recovery','cancel-active-original-read','resume-import-without-duplicate','cancel-resume-original-hashes','mapping-repair-reaches-shelf-without-reimport','authenticated-webdav-traffic'}
        expected.update({'native-recover-staged-group','native-empty-group-name-refused','native-long-group-name-refused','native-256-scalar-group-name-preserved','native-create-shelf-tag-series-and-child','native-created-groups-sync-to-second-host'})
        expected.update({'native-tag-browse-shows-only-members','native-group-search-stays-within-group','native-empty-group-shows-no-books','native-return-to-all-books'})
        assert set(report['checks'])==expected and len(report['checks'])==len(expected)
        assert report['metadata_consumer_sha256']==sha('organization-consumer/metadata-consumer.exe')
        paged=json.loads(read('group-page-ui/result.json'))
        assert paged['accepted'] and not paged['problems'] and paged['source_sha']==result['source'] and str(paged['run_id'])==result['run'] and str(paged['attempt'])==result['attempt']
        assert paged['program_sha256']==report['program_sha256'] and paged['seed_sha256']==sha('cloud-readback/group-page-seed.exe')
        catalog_path='group-page-ui/profile/library.sqlite.product.sqlite'
        assert paged['fixture_catalog_sha256']==sha(catalog_path)
        catalog_file=out/'fixture-catalog.sqlite';catalog_file.write_bytes(read(catalog_path))
        with sqlite3.connect('file:'+str(catalog_file.resolve())+'?mode=ro',uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)
            assert db.execute('SELECT count(*) FROM reader_local_books').fetchone()==(2202,)
            for table,column,ident in (('reader_book_shelves','shelf_id','a'*32),('reader_book_tags','tag_id','b'*32),('reader_book_series','series_id','c'*32)):
                assert db.execute('SELECT count(*) FROM '+table+' WHERE '+column+'=?',(ident,)).fetchone()==(170,)
            titles=db.execute('SELECT b.title FROM reader_book_series m JOIN reader_books b ON b.book_key=m.book_key WHERE m.series_id=? ORDER BY m.ordinal,m.book_key',('c'*32,)).fetchall()
            assert titles[0]==('Shelf 0169',) and titles[-1]==('Shelf 0000',)
        catalog_file.unlink()
        assert paged['originals']==2202 and paged['members_per_group']==170
        for name in ('removed-anchor.bmp','removed-tail.bmp','removed-all.bmp'):
            assert read('group-page-ui/'+name).startswith(b'BM')
        assert set(paged['checks'])=={'shelf-forward-reverse-bounded-170','tag-forward-reverse-bounded-170','series-forward-reverse-bounded-170','shelf-literal-search','tag-literal-search','series-literal-search','return-to-all-books-after-each-group','removed-top-anchor-keeps-neighbor','removed-tail-falls-back-to-predecessors','removed-all-shows-empty','moved-anchor-follows-current-order','predecessor-page-retains-reverse-continuation'} and len(paged['checks'])==12
        audit=report['cancel_readback'];assert audit['ok']==1 and len(audit['books'])==2 and all(item['read_ok']==1 for item in audit['books'])
        assert {sha('organization-ui/cancel-readback/book-%d.bin'%item['id']) for item in audit['books']}==set(report['cancel_input_hashes'])
        deleted=report['deleted_readback'];assert deleted['ok']==1 and len(deleted['books'])==1 and deleted['books'][0]['read_ok']==1
        assert sha('organization-ui/deleted-readback/book-%d.bin'%deleted['books'][0]['id'])==report['deleted_original_sha256']==sha('organization-ui/Book.txt')
        assert report['server']['base'].startswith('https://127.0.0.1:') and report['server']['certificate_sha256']==sha('organization-ui/certificates/server.crt')
        assert report['server']['source_sha256']==hashlib.sha256(Path('tests/reader_windows_account/check_account_ui.py').read_bytes()).hexdigest()
        for name in ('unresolved.bmp','organizer.bmp','pending.bmp'):assert read('organization-ui/'+name).startswith(b'BM')
        dependencies={p:subprocess.check_output(['git','rev-parse',result['source']+':'+p],text=True).strip() for p in ('apps/reader/revisions','apps/reader/desktop','extras/webdav','extras/sideload','src','include')}
        result.update(accepted=True,checks=report['checks'],cloud_checks=cloud['checks'],program_sha256=report['program_sha256'],installed_libraries=cloud['installed_libraries'],dependencies=dependencies,server=report['server'],artifact={'id':identity,'digest':digest},retained_build=built)
except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
if not result['accepted']:raise SystemExit('Organization evidence rejected')
