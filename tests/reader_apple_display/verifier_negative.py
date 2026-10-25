"""Executable rejection cases applied to authenticated original native artifacts.

Only the in-memory mutated copies are changed. Originals and expectations remain.
ZIP metadata is refreshed for semantic mutations, so they must fail semantic checks
instead of merely failing the outer checksum. These are verifier tests, NOT native
display capability tests.
"""
import copy
from datetime import datetime, timedelta, timezone
import io
import json
import zipfile
from verify import (check_jobs, load, select_artifacts, sha, verify_archive)


def reject_mutations(originals, jobs, want):
    results=[]
    kind,data,metadata,original=next(o for o in originals if o[0]=='macos')
    with zipfile.ZipFile(io.BytesIO(data)) as z: manifest=load(z.read('manifest.json'))

    def rejects(name, operation):
        try: operation()
        except (ValueError,KeyError,TypeError,zipfile.BadZipFile) as error:
            results.append({'name':name,'status':'PASS','rejection':str(error)}); return
        raise AssertionError('Verifier accepted negative: '+name)

    def forged(change=None, duplicate=None):
        files=copy.deepcopy(original); m=copy.deepcopy(manifest)
        if change: change(files,m)
        m['files']={p:{'sha256':sha(b),'size':len(b)} for p,b in sorted(files.items())}
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for path,contents in files.items(): z.writestr(path,contents)
            z.writestr('manifest.json',json.dumps(m))
            if duplicate: z.writestr(duplicate,files[duplicate])
        altered=memory.getvalue(); meta=copy.deepcopy(metadata)
        meta['digest']='sha256:'+sha(altered); meta['size_in_bytes']=len(altered)
        return verify_archive(altered,meta,want,kind)

    def edit(files,path,change):
        value=load(files[path]); change(value); files[path]=json.dumps(value).encode()

    def raw(change): return lambda f,m:edit(f,'raw-core.json',change)
    rejects('reject_duplicate_zip_member',lambda:forged(duplicate='raw-core.json'))
    rejects('reject_missing_raw_report',lambda:forged(lambda f,m:f.pop('raw-core.json')))
    rejects('reject_duplicate_json_key',lambda:forged(lambda f,m:f.__setitem__('raw-core.json',b'{"schema":1,"schema":1}')))
    rejects('reject_wrong_source',lambda:forged(raw(lambda r:r['identity'].update(source='0'*40))))
    rejects('reject_wrong_attempt',lambda:forged(raw(lambda r:r['identity'].update(attempt='999'))))
    rejects('reject_wrong_run',lambda:forged(raw(lambda r:r['identity'].update(run='0'))))
    rejects('reject_wrong_original_module_source',lambda:forged(raw(lambda r:r['identity'].update(librarySource='0'*40))))
    rejects('reject_wrong_original_module_hash',lambda:forged(raw(lambda r:r['identity'].update(librarySHA256='0'*64))))
    rejects('reject_wrong_actual_binary',lambda:forged(lambda f,m:f.__setitem__('display-probe',b'not the executed Mach-O')))
    rejects('reject_wrong_installed_archive',lambda:forged(lambda f,m:f.__setitem__('installed/lib/libAppleReaderDisplay.a',b'not original module')))
    rejects('reject_wrong_installed_header',lambda:forged(lambda f,m:f.__setitem__('installed/include/ADRDisplayLease.h',b'not original public header')))
    rejects('reject_replaced_probe_source',lambda:forged(lambda f,m:f.__setitem__('fresh-consumer/MacProbe.m',b'not original probe')))
    rejects('reject_missing_named_case',lambda:forged(raw(lambda r:r['cases'].pop())))
    rejects('reject_duplicate_named_case',lambda:forged(raw(lambda r:r['cases'].append(r['cases'][0]))))
    rejects('reject_failed_case',lambda:forged(raw(lambda r:r['cases'][0].update(status='FAIL'))))
    rejects('reject_unpermitted_pending',lambda:forged(raw(lambda r:r['cases'][0].update(status='PENDING'))))
    rejects('reject_physical_effect_overclaim',lambda:forged(raw(lambda r:r.update(physicalSleepVerified=True))))
    rejects('reject_fake_termination',lambda:forged(lambda f,m:edit(f,'termination.json',lambda t:t.update(exitCode=0))))
    rejects('reject_missing_linked_module',lambda:forged(lambda f,m:f.__setitem__('consumer.linkmap',b'not linked')))
    rejects('reject_forged_summary',lambda:forged(lambda f,m:m['summary'].update(passed=999)))

    def bad_meta(change):
        meta=copy.deepcopy(metadata); change(meta); return verify_archive(data,meta,want,kind)
    rejects('reject_wrong_api_digest',lambda:bad_meta(lambda m:m.update(digest='sha256:'+'0'*64)))
    rejects('reject_wrong_api_size',lambda:bad_meta(lambda m:m.update(size_in_bytes=1)))
    rejects('reject_empty_artifact',lambda:bad_meta(lambda m:m.update(size_in_bytes=0)))
    rejects('reject_expired_artifact',lambda:bad_meta(lambda m:m.update(expired=True)))
    rejects('reject_past_expiry',lambda:bad_meta(lambda m:m.update(expires_at='2000-01-01T00:00:00Z')))
    rejects('reject_artifact_wrong_run',lambda:bad_meta(lambda m:m['workflow_run'].update(id=0)))
    rejects('reject_artifact_wrong_source',lambda:bad_meta(lambda m:m['workflow_run'].update(head_sha='0'*40)))
    metas=[o[2] for o in originals]
    rejects('reject_duplicate_artifact_name',lambda:select_artifacts(metas+[metas[0]],want))
    dup=copy.deepcopy(metas); dup[1]['id']=dup[0]['id']
    rejects('reject_duplicate_artifact_id',lambda:select_artifacts(dup,want))
    rejects('reject_missing_artifact',lambda:select_artifacts(metas[1:],want))

    def bad_job(change):
        copied=copy.deepcopy(jobs); j=next(j for j in copied if j['name']=='native (macos)'); change(j); check_jobs(copied,want)
    rejects('reject_pending_upstream_job',lambda:bad_job(lambda j:j.update(status='in_progress',conclusion=None)))
    rejects('reject_failed_upstream_job',lambda:bad_job(lambda j:j.update(conclusion='failure')))
    rejects('reject_wrong_upstream_source',lambda:bad_job(lambda j:j.update(head_sha='0'*40)))
    rejects('reject_wrong_upstream_attempt',lambda:bad_job(lambda j:j.update(run_attempt=999)))
    rejects('reject_wrong_upstream_run',lambda:bad_job(lambda j:j.update(run_id=0)))
    rejects('reject_duplicate_upstream_job',lambda:check_jobs(jobs+[next(j for j in jobs if j['name']=='native (macos)')],want))
    if len(results)!=36: raise AssertionError('Missing required verifier rejection case')
    return results
