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
        'NativeReadingProbe.receive(store.productOwner(),wire);need(NativeReadingProbe.receive(store.productOwner(),wire)==0,"duplicate original wire is idempotent");need(Arrays.equals(wire,RecordWireProbe.retained(store.productOwner(),row.getString("id")))')
replace('input=new JSONObject().put("books",sourceRows);seed();java.util.Set<String> ids=',
        'input=new JSONObject().put("books",sourceRows);seed();byte[][] outboxBefore=owner(store->RecordWireProbe.outbox(store.productOwner()));java.util.Set<String> ids=')
replace('need(RecordWireProbe.outbox(store.productOwner()).length==0,"remote receive creates no product outbox")',
        'need(Arrays.deepEquals(outboxBefore,RecordWireProbe.outbox(store.productOwner())),"remote receive changes no preexisting outbox bytes")')
start = text.index('    @Override public void onStart(){')
text = text[:start] + '''    private NativeReadingSdk.Match probeLegacy(BookStore store,long book,ReadingCapture capture)throws Exception {
        BookStore.VerifiedSource source=store.verifySource(book,null,0,task());
        need(source.key.equals(capture.bookKey),"old capture belongs to independently verified original");
        int mode=source.book.fixed()?ReadingCapture.FIXED:source.location.equals("epub_chapter")?ReadingCapture.EPUB:ReadingCapture.REFLOW;
        need(capture.mode==mode,"old capture mode matches real current original");
        need(NativeReadingSdk.acceptsParser(capture.parser),"actual host admits the proven 3.41 Android tag");
        return resolve(store,book,capture);
    }
    private void navigateOldBookmarks()throws Exception {
        JSONObject bundle=new JSONObject(new String(Files.readAllBytes(incomingFile("manifest.json").toPath()),StandardCharsets.UTF_8));
        JSONArray records=bundle.getJSONArray("reading_records");
        for(String role:new String[]{"txt","epub","pdf","cbz"}){
            JSONObject bookmark=null;for(int i=0;i<records.length();i++){JSONObject row=records.getJSONObject(i);if(row.getString("role").equals(role)&&row.getString("kind").equals("bookmark"))bookmark=row;}
            need(bookmark!=null,"actual sender bookmark present");ReadingCapture expected=captureFrom(bookmark.getJSONObject("capture"));
            open(role);idle();long token=frame().getLong("accepted_token");String before=snapshot();
            panel();contains("Android actual sender point");click("跳转到此处");
            long end=SystemClock.elapsedRealtime()+120000;JSONObject landed=null;
            while(SystemClock.elapsedRealtime()<end){JSONObject view=frame();if(view.optLong("accepted_token",0)>token){landed=view;break;}SystemClock.sleep(60);}
            need(landed!=null&&landed.getLong("book")==book(role),"actual host publishes navigated original");
            if(expected.mode==ReadingCapture.FIXED)need(landed.getLong("index")==expected.unit,"actual fixed renderer publishes the sender page");
            else {if(expected.mode==ReadingCapture.EPUB)need(landed.getLong("part")==expected.unit&&landed.getString("path").equals(expected.partPath),"actual EPUB spine/path");need(landed.getLong("start")<=expected.start&&landed.getLong("end")>=expected.end,"actual rendered page contains sender location");}
            need(snapshot().equals(before),"actual navigation leaves SDK and outbox unchanged");
        }
    }
    @Override public void onStart(){
        context=getTargetContext();phase="sdk342-legacy-semantic-probe";Throwable failure=null;Bundle result=new Bundle();JSONObject observation=null;
        try {
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            launch();until(node->id(node,"sdk_label")&&text(node).contains("3.42.0"),null,"actual SDK 3.42 owner",120000);
            sender=programIdentity();
            final JSONObject[] observed=new JSONObject[1];check("actual_341_wire_sdk342_host_resolve",()->observed[0]=receiveActualApple());observation=observed[0];
            check("actual_341_bookmarks_navigate_on_four_real_hosts",this::navigateOldBookmarks);
        }catch(Throwable error){failure=error;try{capture("sdk342-wire-failure");}catch(Throwable diagnostic){error.addSuppressed(diagnostic);}}
        try {
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("resolutions",resolutionRows).put("receiver",sender).put("observation",observation).put("host_compatibility_accepted",failure==null);
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
    'scope':'actual host resolution and navigation of authenticated Android 3.41 wires'}, indent=2)+'\n')
