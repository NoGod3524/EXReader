"""Actions-only: derive the SDK 3.42 runner from the unchanged original Sync UI driver.

Only the class/runner names and the supported-version allow-list change; every
check, fixture and assertion of the original suite is preserved byte for byte."""
import hashlib, json, os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[2]
java = root / 'tests/reader_host_session_android/java/org/exreader/host/HostSyncTest.java'
driver = root / 'tests/reader_host_session_android/run_ui.py'
source = java.read_text(encoding='utf-8'); run = driver.read_text(encoding='utf-8')
edits_java = [('public final class HostSyncTest extends Instrumentation', 'public final class HostSync342Test extends Instrumentation'),
              ('expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0")', 'expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0")||expectedSdk.equals("3.42.0")')]
edits_run = [("package+'.test/'+package+'.HostSyncTest'", "package+'.test/'+package+'.HostSync342Test'"),
             ("choices=('3.40.0','3.41.0')", "choices=('3.40.0','3.41.0','3.42.0')")]
candidate, candidate_run = source, run
for old, new in edits_java:
    assert candidate.count(old) == 1, old; candidate = candidate.replace(old, new)
for old, new in edits_run:
    assert candidate_run.count(old) == 1, old; candidate_run = candidate_run.replace(old, new)
out = root / 'build/installed-sync/candidate'
(out / 'java/org/exreader/host').mkdir(parents=True, exist_ok=True)
(out / 'java/org/exreader/host/HostSync342Test.java').write_text(candidate, encoding='utf-8')
(Path(__file__).resolve().parent / 'run_ui_342.py').write_text(candidate_run, encoding='utf-8')
sha = lambda text: hashlib.sha256(text.encode()).hexdigest()
proof = {'source_sha': os.environ['GITHUB_SHA'], 'original_java_sha256': sha(source), 'candidate_java_sha256': sha(candidate),
         'original_driver_sha256': sha(run), 'candidate_driver_sha256': sha(candidate_run),
         'changes': [dict(file='HostSyncTest.java', old=o, new=n) for o, n in edits_java] +
                    [dict(file='run_ui.py', old=o, new=n) for o, n in edits_run],
         'assertions_relaxed': False, 'budgets_changed': False}
(out / 'provenance.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(proof))
