"""Actions-only adaptation of the owner fixture for automatic book bootstrap."""
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get("GITHUB_ACTIONS") == "true"
root = Path(__file__).resolve().parents[2]
java_path = root / "examples/android/app/src/androidTest/java/org/exreader/host/ProductOwnerTest.java"
driver_path = root / "tests/reader_session_android/run_roundtrip.py"
original = java_path.read_text(encoding="utf-8")
driver = driver_path.read_text(encoding="utf-8")

def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)

candidate = replace_once(original, "public final class ProductOwnerTest extends Instrumentation",
                         "public final class ProductOwnerCurrentTest extends Instrumentation")
candidate = replace_once(candidate, "sdk.finalizeImport(source);\n            if(bootstrap)",
                         "catalog.attach(source);\n            if(bootstrap)")
candidate = replace_once(candidate,
    'try(BookStore sdk=new BookStore(context,new File(directory,"library.db"))){ok(sdk.bootstrapBook(source.book.id,id(50),empty(),new HostTask(()->false)));}',
    'try(BookStore sdk=new BookStore(context,new File(directory,"library.db"))){String[] head=NativeCatalog.selection(owner(),"book",source.key);require(head.length==4&&"4".equals(head[0]),"unique auto-created head");ok(sdk.bootstrapBook(source.book.id,id(50),new String[]{head[3]},new HostTask(()->false)));}')
candidate = replace_once(candidate,
    '"sdkDatabaseRefusedWithoutModification", "opensClosedLegacySystemCatalog"};',
    '"sdkDatabaseRefusedWithoutModification", "opensClosedLegacySystemCatalog", "finalizeImportAutomaticallyBootstrapsOnce"};')
candidate = replace_once(candidate,
    'this::sdkDatabaseRefusedWithoutModification,this::opensClosedLegacySystemCatalog};',
    'this::sdkDatabaseRefusedWithoutModification,this::opensClosedLegacySystemCatalog,this::finalizeImportAutomaticallyBootstrapsOnce};')
auto = r'''
    private void finalizeImportAutomaticallyBootstrapsOnce()throws Exception{
        File original=new File(directory,"auto-original.txt");
        Files.write(original.toPath(),"Automatic verified original bootstrap.\n".getBytes(StandardCharsets.UTF_8));
        BookStore.VerifiedSource source;
        try(BookStore sdk=new BookStore(context,new File(directory,"library.db"))){
            NativeLibrary.ImportResult imported=sdk.importFile(original.getPath(),NativeLibrary.FORMAT_TXT,"Auto title");
            source=sdk.verifySource(imported.id,null,0,new HostTask(()->false));
            sdk.finalizeImport(source);
            counts(1,1,0);
            equal(1,scalar("SELECT count(*) FROM reader_local_books"));
            JSONObject payload=new JSONObject(text("SELECT body_json FROM reader_revisions WHERE entity_kind='book'")).getJSONObject("payload");
            equal(source.sha256,payload.getString("source_sha256"));equal(source.bytes,payload.getLong("source_bytes"));
            require(!payload.has("sdk_book_id"),"automatic wire excludes local SDK identity");
            String[] head=NativeCatalog.selection(owner(),"book",source.key);
            require(head.length==4&&"4".equals(head[0]),"one verified book head");
            sdk.finalizeImport(source);counts(1,1,0);
        }
        try(BookStore reopened=new BookStore(context,new File(directory,"library.db"))){
            require(!reopened.metadataRepairPending(),"automatic bootstrap survives reopen");
            equal(1,scalar("SELECT count(*) FROM reader_local_books"));counts(1,1,0);
        }
    }
'''
candidate = replace_once(candidate, "    private void membershipNeedsExplicitBookBootstrap()throws Exception{",
                         auto + "    private void membershipNeedsExplicitBookBootstrap()throws Exception{")

adapted = replace_once(driver, "org.exreader.host.test/org.exreader.host.ProductOwnerTest",
                       "org.exreader.host.test/org.exreader.host.ProductOwnerCurrentTest")
adapted = replace_once(adapted, "OK (17 tests)", "OK (18 tests)")
adapted = replace_once(adapted, "report['count']==17", "report['count']==18")
adapted = replace_once(adapted, "unchanged_original_product_owner_17_and_two_process_phases",
                       "adapted_owner_17_plus_auto_bootstrap_and_two_process_phases")
adapted = replace_once(adapted, "the original host's unchanged owner suite",
                       "the explicitly adapted owner suite")

out = root / "build/android-owner-current"
java_out = out / "java/org/exreader/host/ProductOwnerCurrentTest.java"
java_out.parent.mkdir(parents=True, exist_ok=False)
java_out.write_text(candidate, encoding="utf-8")
(out / "run_roundtrip_current.py").write_text(adapted, encoding="utf-8")
sha = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
(out / "provenance.json").write_text(json.dumps({
    "source": os.environ["GITHUB_SHA"],
    "original_java_sha256": sha(original), "adapted_java_sha256": sha(candidate),
    "original_driver_sha256": sha(driver), "adapted_driver_sha256": sha(adapted),
    "changes": ["distinct runner class", "manual attach for no-bootstrap fixture",
                "explicit current head on reopened bootstrap", "one auto-bootstrap case",
                "driver runner, count and evidence label"],
    "original_test_modified": False,
}, indent=2)+"\n", encoding="utf-8")
