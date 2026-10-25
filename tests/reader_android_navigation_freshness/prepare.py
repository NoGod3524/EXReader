"""Auditable trace-only Java and runner projections; original assertions remain exact."""
import hashlib
import json
from pathlib import Path

from authenticate import BASE, ROOT, OUT, need

JAVA = 'tests/reader_android_navigation/java/org/exreader/host/NavigationUiTest.java'
RUNNER = 'tests/reader_android_navigation/run_ui.py'


def prepare():
    original = (ROOT / JAVA).read_text(encoding='utf-8')
    start = original.index('    private void result(String label,boolean select)')
    end = original.index('\n    private void contains(', start)
    old = original[start:end]
    replacement = '''    private void result(String label,boolean select){long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){
        try{traceDirectory(label,"before-cache",null,null);Boolean cleared=null;
            if("fresh".equals(arguments.getString("diagnostic_cache","trace")))cleared=getUiAutomation().clearCache();
            traceDirectory(label,"after-cache",cleared,null);
            if(act(node->id(node,"text1")&&node.isVisibleToUser()&&node.isEnabled()&&text(node).contains(label),select?this::tap:null)){traceDirectory(label,"matched",null,null);return;}
            boolean[] scrolled={false};act(node->description(node,"目录条目"),node->scrolled[0]=node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD));
            traceDirectory(label,"after-scroll",null,scrolled[0]);
        }catch(RuntimeException error){throw error;}catch(Exception error){throw new AssertionError("trace unavailable",error);}
        SystemClock.sleep(100);}throw new AssertionError("Actual visible directory row missing: "+label);}
'''.rstrip('\n')
    helpers = (ROOT / 'tests/reader_android_navigation_freshness/trace.java.inc').read_text(encoding='utf-8')
    marker = '    private Bundle arguments;'
    report_marker = '        try{\n            JSONObject report='
    need(original.count(marker) == original.count(report_marker) == 1, 'original Java projection markers differ')
    projected = original[:start] + replacement + original[end:]
    projected = projected.replace(marker, helpers + '\n' + marker, 1)
    projected = projected.replace(report_marker, '        try{\n            flushDirectoryTrace();\n            JSONObject report=', 1)
    restored = projected.replace(helpers + '\n', '', 1).replace(replacement, old, 1).replace(
        '        try{\n            flushDirectoryTrace();\n            JSONObject report=', report_marker, 1)
    need(restored == original, 'an original Java assertion or wait was changed outside the reviewed helper')
    target = OUT / 'generated/org/exreader/host/NavigationUiTest.java'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(projected, encoding='utf-8')
    runner = (ROOT / RUNNER).read_text(encoding='utf-8')
    old_command = "command=['adb','shell','am','instrument','-w','-r','-e','phase',phase]"
    new_command = "command=['adb','shell','am','instrument','-w','-r','-e','phase',phase,'-e','diagnostic_cache',os.environ['NAV_DIAGNOSTIC_CACHE']]"
    need(runner.count(old_command) == 1, 'runner instrumentation entry differs')
    transformed = runner.replace(old_command, new_command, 1)
    need(transformed.replace(new_command, old_command, 1) == runner, 'runner assertion or 900s limit changed')
    (OUT / 'projected_runner.py').write_text(transformed, encoding='utf-8')
    proof = {'producer_source': BASE, 'original_java_sha256': hashlib.sha256(original.encode()).hexdigest(),
             'trace_java_sha256': hashlib.sha256(projected.encode()).hexdigest(),
             'original_runner_sha256': hashlib.sha256(runner.encode()).hexdigest(),
             'projected_runner_sha256': hashlib.sha256(transformed.encode()).hexdigest(),
             'java_reverse_projection_exact': True, 'runner_reverse_projection_exact': True,
             'original_expected_checks': 18, 'original_phase_timeout_seconds': 900,
             'original_result_wait_ms': 30000, 'owner_modified': False, 'accepted': False}
    (OUT / 'evidence/projection.json').write_text(json.dumps(proof, indent=2) + '\n')


if __name__ == '__main__':
    prepare()
