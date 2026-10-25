"""Actions-only: add one C07 Android export phase to the generated raw3 instrumentation class.

The original generated tests/reader_android_raw3 harness is kept byte-for-byte; this wrapper
only adds a phase after it was generated and records both digests.
"""
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
target = Path('build/android-raw3/candidate/java/org/exreader/host/Raw3InteropTest.java')
original = target.read_text(encoding='utf-8')

METHOD = r'''
    private void c07NullExport()throws Exception{
        loadInput(false);open("pdf");panel();
        File root=new File(context.getFilesDir(),"c07-null-outgoing");
        String[] ids=owner(store->{
            family(store);
            PageSnapshot live=(PageSnapshot)ReadingReview.field(activity(),"current");
            ReadingCapture captured=NativeReadingSdk.capture(store,live,0,0,fontBytesForInterop(),24,originalPath(book("pdf")),task(),control());
            need(nul(captured.bytes()[2]),"C07 NULL source starts from the genuine public SDK NUL point");
            NativeCatalog.Result boot=store.bootstrapBook(book("pdf"),NativeCatalog.newId(),new String[0],task());need(boot.status==0,"C07 actual PDF original fact");
            String annotation=NativeCatalog.newId(),put=NativeCatalog.newId();
            NativeReadingProduct.Result written=NativeReadingProduct.applyVersioned(store,put,new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,key("pdf"),annotation,captured.mode,captured,"C07 NULL protocol negative source",3);need(written.saved(),"C07 counted source exists before the NULL expression");
            JSONObject protocol=new JSONObject(ReadingCapture.decode(RecordWireProbe.retained(store.productOwner(),put)));String id=NativeCatalog.newId(),other=NativeCatalog.newId();
            protocol.put("id",id).put("entity_key",key("pdf")+":"+other);protocol.getJSONObject("payload").put("annotation_id",other).getJSONObject("location").getJSONObject("selector").put("exact",new JSONObject().put("base64",JSONObject.NULL).put("size",0));
            byte[] nullBytes=protocol.toString().getBytes(StandardCharsets.UTF_8);
            NativeReadingProbe.receive(store.productOwner(),nullBytes);
            byte[] retainedNull=RecordWireProbe.retained(store.productOwner(),id);need(Arrays.equals(retainedNull,nullBytes),"C07 actual retained NULL wire keeps the received bytes");
            BookStore.VerifiedSource source=store.verifySource(book("pdf"),null,0,task());
            File original=new File(root,"originals/pdf.pdf");need(original.getParentFile().isDirectory()||original.getParentFile().mkdirs(),"C07 original directory");
            need(store.nativeLibrary().exportOriginal(book("pdf"),original.getPath(),task())==source.bytes,"C07 public exact original export");
            byte[] originalBytes=Files.readAllBytes(original.toPath());need(originalBytes.length==source.bytes&&digest(originalBytes).equals(source.sha256),"C07 exported original binds the SDK bytes");
            JSONArray revisions=new JSONArray();
            for(byte[] wire:RecordWireProbe.outbox(store.productOwner())){
                JSONObject value=new JSONObject(ReadingCapture.decode(wire));if(!value.getString("entity_kind").equals("book"))continue;
                String revision=value.getString("id");durable(new File(root,"revisions/"+revision+".json"),wire);
                revisions.put(new JSONObject().put("file","revisions/"+revision+".json").put("id",revision).put("entity_kind","book").put("entity_key",value.getString("entity_key")).put("book_key",source.key).put("parents",value.getJSONArray("parents")).put("bytes",wire.length).put("sha256",digest(wire)));
            }
            need(revisions.length()==1,"C07 NULL graph carries exactly the actual PDF book wire");
            JSONObject nullWire=new JSONObject(ReadingCapture.decode(retainedNull));durable(new File(root,"revisions/"+id+".json"),retainedNull);
            revisions.put(new JSONObject().put("file","revisions/"+id+".json").put("id",id).put("entity_kind","annotation").put("entity_key",nullWire.getString("entity_key")).put("book_key",source.key).put("parents",nullWire.getJSONArray("parents")).put("bytes",retainedNull.length).put("sha256",digest(retainedNull)));
            JSONObject row=new JSONObject().put("role","pdf").put("file","originals/pdf.pdf").put("format","pdf").put("book_key",source.key).put("bytes",originalBytes.length).put("sha256",source.sha256);
            JSONObject manifest=new JSONObject().put("schema",1).put("purpose","authentic-android-null-negative").put("originals",new JSONArray().put(row)).put("revisions",revisions).put("null_revision",id).put("annotation_id",other);
            durable(new File(root,"manifest.json"),manifest.toString(2).getBytes(StandardCharsets.UTF_8));
            return new String[]{id,other};
        });
        JSONObject sealed=new JSONObject(new String(Files.readAllBytes(new File(root,"manifest.json").toPath()),StandardCharsets.UTF_8));
        sealed.put("sender",programIdentity());durable(new File(root,"manifest.json"),sealed.toString(2).getBytes(StandardCharsets.UTF_8));
        rawDetails.put("c07_null_revision",ids[0]).put("c07_null_annotation",ids[1]).put("c07_null_manifest_sha256",digest(Files.readAllBytes(new File(root,"manifest.json").toPath())));
    }
'''

source = original
anchor = '    private void runRawPhase()throws Exception{'
assert source.count(anchor) == 1
source = source.replace(anchor, METHOD + anchor)
branch = '        else throw new AssertionError("unknown actual raw phase");'
assert source.count(branch) == 1
source = source.replace(branch, '        else if(phase.equals("c07-null-export"))check("c07_android_actual_null_negative_export_for_mac",this::c07NullExport);\n' + branch)
gate = '||phase.equals("apple-null-reopen-again"),"explicit actual sender or incoming phase")'
assert source.count(gate) == 1
source = source.replace(gate, '||phase.equals("apple-null-reopen-again")||phase.equals("c07-null-export"),"explicit actual sender or incoming phase")')
target.write_text(source, encoding='utf-8')
Path('build/android-raw3/c07-harness.json').write_text(json.dumps({
    'original_generated_sha256': hashlib.sha256(original.encode()).hexdigest(),
    'patched_sha256': hashlib.sha256(source.encode()).hexdigest(),
    'added_phase': 'c07-null-export',
    'added_method_sha256': hashlib.sha256(METHOD.encode()).hexdigest()}, indent=2) + '\n')
