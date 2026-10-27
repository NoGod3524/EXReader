"""Actions-only strict 3.41 adapter, preserving the original sync driver."""
import hashlib, json, os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
root=Path(__file__).resolve().parents[2]
original=root/'tests/reader_host_session_android/java/org/exreader/host/HostSyncTest.java'
driver=root/'tests/reader_host_session_android/run_ui.py'
source=original.read_text(encoding='utf-8'); run=driver.read_text(encoding='utf-8')
old_class='public final class HostSyncTest extends Instrumentation'
new_class='public final class HostSync341Test extends Instrumentation'
old_runner="package+'.test/'+package+'.HostSyncTest'"
new_runner="package+'.test/'+package+'.HostSync341Test'"
assert source.count(old_class)==1 and run.count(old_runner)==1
candidate=source.replace(old_class,new_class)
candidate_run=run.replace(old_runner,new_runner)
assert candidate.replace(new_class,old_class)==source
assert candidate_run.replace(new_runner,old_runner)==run
out=root/'build/android-organization-sync/candidate/java/org/exreader/host/HostSync341Test.java'
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(candidate,encoding='utf-8')
script=root/'tests/reader_android_organization_sync/host_sync_341.py'
script.write_text(candidate_run,encoding='utf-8')
def sha(data):return hashlib.sha256(data.encode()).hexdigest()
proof={'source':os.environ['GITHUB_SHA'],'original_java_sha256':sha(source),'candidate_java_sha256':sha(candidate),
       'original_driver_sha256':sha(run),'candidate_driver_sha256':sha(candidate_run),
       'changes':['class and runner names'], 'original_unchanged':True}
(root/'build/android-organization-sync/candidate/provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
