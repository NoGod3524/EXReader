"""Actions-only inherited 130 authentication plus real sender ZIP and complete graph."""
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import zipfile
from bundle import verify,parse
assert os.environ.get('GITHUB_ACTIONS')=='true'
old=runpy.run_path('tests/reader_android_page_theme/check_evidence.py')
identity,api,source,run,attempt=old['identity'],old['api'],old['source'],old['run'],old['attempt']
artifacts=api('actions/runs/'+run+'/artifacts?per_page=100')['artifacts']
bundle,=[row for row in artifacts if row['name']=='reader-android-record-bundle-'+run+'-'+attempt]
assert bundle['workflow_run']['head_sha']==source and bundle['workflow_run']['id']==int(run) and not bundle['expired'] and 0<bundle['size_in_bytes']<=16*1024**2
assert datetime.fromisoformat(bundle['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
import subprocess
body=subprocess.check_output(['gh','api',old['repo']+'actions/artifacts/'+str(bundle['id'])+'/zip'])
assert len(body)==bundle['size_in_bytes'] and 'sha256:'+hashlib.sha256(body).hexdigest()==bundle['digest']
with zipfile.ZipFile(io.BytesIO(body)) as archive:
 names=archive.namelist();assert len(names)==len(set(names))
 def read(name):
  candidates=[value for value in names if value==name or value.endswith('/'+name)];path,=candidates;info=archive.getinfo(path);assert 0<info.file_size<=32*1024**2;return archive.read(path)
 verified=verify(read)
 sender=verified['manifest']['sender'];assert sender['platform']=='android' and all(sender.get(key)==value for key,value in identity.items())
 with zipfile.ZipFile(io.BytesIO(old['apk'])) as apk:
  sdk,=[name for name in apk.namelist() if name=='lib/x86_64/libexreader.so'];assert hashlib.sha256(apk.read(sdk)).hexdigest()==sender['sdk_dso_sha256']
 assert hashlib.sha256(old['apk']).hexdigest()==sender['apk_sha256']
with zipfile.ZipFile(io.BytesIO(old['body'])) as archive:
 def report(suffix):
  name,=[name for name in archive.namelist() if name.endswith(suffix)];return parse(archive.read(name))
 observed=report('android-record-interop/ui/result.json');assert observed['sender_export_accepted'] is True and observed['checks']==8 and observed['incoming_apple_status']=='pending' and observed['bidirectional_interoperability_accepted'] is False
 assert all(observed.get(key)==value for key,value in identity.items()) and len({phase['pid'] for phase in observed['phases']})==2
 assert [phase['count'] for phase in observed['phases']]==[6,2] and all(phase['passed'] is True and all(check['pass'] is True for check in phase['checks']) for phase in observed['phases'])
 assert observed['phases'][0]['manifest_sha256']==verified['manifest_sha256'] and len(observed['phases'][0]['resolutions'])==11
 native=report('android-record-interop/native/result.json');assert native['accepted'] is True and all(native.get(key)==value for key,value in identity.items())
 assert native['checks'][0]['probe_exported'] is True and native['checks'][1]['probe_exported'] is False
result={**identity,'sender_export_accepted':True,'inherited_130_accepted':True,'checks':138,'incoming_apple_status':'pending','bidirectional_interoperability_accepted':False,'actual_sdk':'3.41.0','bundle':{key:bundle[key] for key in ('id','name','size_in_bytes','digest','expires_at')},'manifest_sha256':verified['manifest_sha256'],'originals':verified['originals'],'revisions':verified['revisions'],'reading_records':verified['reading_records'],'actual_sender':sender,'inherited_summary':old['result'],'physical_device':False,'complete_product':False}
output=Path('build/android-record-interop-summary/summary.json');output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
