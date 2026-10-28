"""Actions-only generated semantic probe from the unchanged interop driver."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[2]
os.chdir(root)
subprocess.run([sys.executable, 'tests/reader_android_record_interop/candidate.py'], check=True)
source = root / 'build/android-page-theme/candidate/preferences/java/org/exreader/host/RecordInteropTest.java'
original = source.read_text()
text = original
def replace(old, new):
    global text
    assert text.count(old) == 1, (old, text.count(old))
    text = text.replace(old, new)

replace('public final class RecordInteropTest', 'public final class Sdk342WireProbe')
replace('peer.getString("platform").equals("macos")&&peer.getString("exr_version").equals("3.41.0")&&peer.getString("parser_version").equals("3.41.0")',
        'peer.getString("platform").equals("android")&&peer.getString("exr_version").equals("3.41.0")&&peer.getString("parser_version").equals("exreader-sdk-3.41.0")')
replace('actual.capture.parser.equals("3.41.0")', 'actual.capture.parser.equals("exreader-sdk-3.41.0")')
replace('NativeReadingSdk.Match found=resolve(store,book(role),actual.capture);',
        'NativeReadingSdk.Match found=probeLegacy(store,book(role),actual.capture);')
replace('found.recaptured.parser.equals("exreader-sdk-3.41.0")', 'found.recaptured.parser.equals("exreader-sdk-3.42.0")')
replace('NativeReadingProbe.receive(store.productOwner(),wire);need(Arrays.equals(wire,RecordWireProbe.retained(store.productOwner(),row.getString("id")))',
        'NativeReadingProbe.receive(store.productOwner(),wire);NativeReadingProbe.receive(store.productOwner(),wire);need(Arrays.equals(wire,RecordWireProbe.retained(store.productOwner(),row.getString("id")))')
start = text.index('    @Override public void onStart(){')
text = text[:start] + '''    private NativeReadingSdk.Match probeLegacy(BookStore store,long book,ReadingCapture capture)throws Exception {
        BookStore.VerifiedSource source=store.verifySource(book,null,0,task());
        need(source.key.equals(capture.bookKey),"old capture belongs to independently verified original");
        int mode=source.book.fixed()?ReadingCapture.FIXED:source.location.equals("epub_chapter")?ReadingCapture.EPUB:ReadingCapture.REFLOW;
        need(capture.mode==mode,"old capture mode matches real current original");
        need(!NativeReadingSdk.acceptsParser(capture.parser),"unchanged production policy still refuses 3.41");
        boolean refused=false;try{NativeReadingSdk.resolve(store,book,capture,fontBytesForInterop(),24,task(),control());}catch(IllegalStateException expected){refused=true;}
        need(refused,"production host rejects the old parser before the semantic probe");
        return NativeReadingSdk.resolveForCallback(store,book,capture,fontBytesForInterop(),24,task(),control());
    }
    @Override public void onStart(){
        context=getTargetContext();phase="sdk342-legacy-semantic-probe";Throwable failure=null;Bundle result=new Bundle();JSONObject observation=null;
        try {
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            launch();until(node->id(node,"sdk_label")&&text(node).contains("3.42.0"),null,"actual SDK 3.42 owner",120000);
            sender=programIdentity();
            final JSONObject[] observed=new JSONObject[1];check("actual_341_wire_sdk342_semantics",()->observed[0]=receiveActualApple());observation=observed[0];
        }catch(Throwable error){failure=error;try{capture("sdk342-wire-failure");}catch(Throwable diagnostic){error.addSuppressed(diagnostic);}}
        try {
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("resolutions",resolutionRows).put("receiver",sender).put("observation",observation).put("host_compatibility_accepted",false);
            if(failure!=null)report.put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));
            durable(new File(context.getFilesDir(),"sdk342-wire-report.json"),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"SDK342_WIRE_PROBE_PASS":"SDK342_WIRE_PROBE_FAIL");finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","SDK342 wire evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
'''
replace('actual[0].equals("3.41.0")', 'actual[0].equals("3.42.0")')
out = root / 'build/android-sdk342-record/java/org/exreader/host/Sdk342WireProbe.java'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text)
(out.parents[4] / 'generation.json').write_text(json.dumps({'base_sha256':hashlib.sha256(original.encode()).hexdigest(),
    'probe_sha256':hashlib.sha256(text.encode()).hexdigest(), 'source':'tests/reader_android_record_interop/candidate.py',
    'scope':'semantic probe; production parser policy remains unchanged'}, indent=2)+'\n')
