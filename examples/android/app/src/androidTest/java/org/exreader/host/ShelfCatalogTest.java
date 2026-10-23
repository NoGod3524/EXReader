// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.OperationCanceledException;
import android.os.SystemClock;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

/** Thousands of real public-SDK imports, followed by the unchanged production mapping repair. */
public final class ShelfCatalogTest extends Instrumentation {
    private static final int TXT_BOOKS=2200, TOTAL=TXT_BOOKS+2;
    private static final String NFD_TITLE="Cafe\u0301 source", NFD_AUTHOR="Shelf Author Re\u0301ne\u0301";
    private static final String[] NAMES={"realSdkImportsAndProductionRepair", "forwardKeysetHasNoMissingOrRepeatedBooks",
            "reverseKeysetMatchesForwardOrder", "sameTitleUsesSourceKeyTieBreak", "titleAuthorAndLiteralSearch",
            "cancelsQueriesAndRejectsWrongOwner", "hidesUnmappedAndDeletedProducts", "repairsNewImportBeforeRefresh",
            "canceledOldSearchCannotReplaceNewResults", "missingEndAnchorFallsBackWithinSameFilter",
            "pendingRestoreRetainsOnlySameQueryAnchor", "canonicalSearchPreservesDisplayBytes"};
    private interface Check { void run() throws Exception; }
    private Context context;
    private File directory;
    private Bundle arguments;
    private BookStore store;
    private Set<String> expected=new HashSet<>();

    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); this.arguments=arguments; start(); }
    @Override public void onStart() {
        context=getTargetContext();
        if (arguments!=null && "seed-ui".equals(arguments.getString("phase"))) { seedUi(); return; }
        int failures=0;
        Check[] checks={this::realSdkImportsAndProductionRepair,this::forwardKeysetHasNoMissingOrRepeatedBooks,
                this::reverseKeysetMatchesForwardOrder,this::sameTitleUsesSourceKeyTieBreak,this::titleAuthorAndLiteralSearch,
                this::cancelsQueriesAndRejectsWrongOwner,this::hidesUnmappedAndDeletedProducts,this::repairsNewImportBeforeRefresh,
                this::canceledOldSearchCannotReplaceNewResults,this::missingEndAnchorFallsBackWithinSameFilter,
                this::pendingRestoreRetainsOnlySameQueryAnchor,this::canonicalSearchPreservesDisplayBytes};
        try {
            directory=new File(context.getCacheDir(),"shelf-catalog"); remove(directory); require(directory.mkdirs(),"test folder");
            seed(directory,false);
            store=new BookStore(context,new File(directory,"library.db"));
            for (int index=0;index<checks.length;index++) {
                sendStatus(1,status(NAMES[index],index+1));
                Bundle result=status(NAMES[index],index+1);
                try { checks[index].run(); result.putString("stream","."); sendStatus(0,result); }
                catch (Throwable error) {
                    failures++; result.putString("stack",Log.getStackTraceString(error));
                    result.putString("stream","Failure in "+NAMES[index]+": "+error); sendStatus(-2,result);
                }
            }
        } catch (Throwable error) { failures++; Log.e("EXRShelfTest","Setup failed",error); }
        finally {
            if (store!=null) store.close();
            try { if(directory!=null)remove(directory); } catch(Exception error) { failures++; }
        }
        Bundle result=new Bundle();
        result.putString("stream",failures==0 ? "\nOK ("+NAMES.length+" tests)\n"
                : "\nFAILURES!!! Tests run: "+NAMES.length+", Failures: "+failures+"\n");
        finish(failures==0 ? Activity.RESULT_OK : Activity.RESULT_CANCELED,result);
    }

    private Bundle status(String name,int index) {
        Bundle value=new Bundle(); value.putString("id","InstrumentationTestRunner");
        value.putString("class",getClass().getName()); value.putString("test",name);
        value.putInt("numtests",NAMES.length); value.putInt("current",index); return value;
    }

    private void seed(File root,boolean prefs) throws Exception {
        File sources=new File(root,"books"); require(sources.isDirectory() || sources.mkdirs(),"source folder");
        android.content.SharedPreferences.Editor editor=context.getSharedPreferences("host",Context.MODE_PRIVATE).edit();
        try(NativeLibrary sdk=new NativeLibrary(new File(root,"library.db").getPath())) {
            for(int index=0;index<TXT_BOOKS+1;index++) {
                String title=index==TXT_BOOKS ? "100%_literal" : index<130 ? "Tie title" : index==1999 ? NFD_TITLE : String.format(Locale.ROOT,"Book %04d",index);
                byte[] bytes=("Real short TXT source "+index+". Read, paginate, search and reopen this book.\n").getBytes(StandardCharsets.UTF_8);
                File file=new File(sources,"source-"+index+".txt"); write(file,bytes);
                NativeLibrary.ImportResult imported=sdk.importFile(file.getPath(),NativeLibrary.FORMAT_TXT,title);
                require(imported.created,"unique SDK TXT import");
                expected.add("txt:"+sha(bytes));
                if(prefs)editor.putString("path_"+imported.id,file.getPath()).putLong("size_"+imported.id,bytes.length);
            }
            File authored=new File(sources,"authored.pdf"); pdf(authored);
            NativeLibrary.ImportResult imported=sdk.importFile(authored.getPath(),NativeLibrary.FORMAT_PDF,"Authored sample");
            require(imported.created,"real authored PDF import");
            expected.add("pdf:"+sha(read(authored)));
            if(prefs)editor.putString("path_"+imported.id,authored.getPath()).putLong("size_"+imported.id,authored.length());
        }
        if(prefs)require(editor.commit(),"seeded host path preferences");
    }

    private List<CatalogStore.ShelfBook> all(String query) {
        List<CatalogStore.ShelfBook> result=new ArrayList<>(); CatalogStore.ShelfKey after=null;
        while(true) {
            List<CatalogStore.ShelfBook> page=store.shelfPage(query,after,false,false,new CancellationSignal());
            require(page.size()<=50,"strict page bound"); result.addAll(page);
            if(page.size()<50)break;
            after=page.get(page.size()-1).key;
            require(result.size()<=TOTAL+1,"keyset did not advance");
        }
        return result;
    }

    private void realSdkImportsAndProductionRepair() {
        require(!store.metadataRepairPending(),"all real SDK sources mapped");
        require(expected.size()==TOTAL,"independent source identity count");
        require(all("").size()==TOTAL,"real imported product count");
    }
    private void forwardKeysetHasNoMissingOrRepeatedBooks() {
        List<CatalogStore.ShelfBook> rows=all(""); Set<String> observed=new HashSet<>();
        CatalogStore.ShelfBook previous=null;
        for(CatalogStore.ShelfBook book:rows) {
            require(observed.add(book.key.bookKey),"duplicate source across keysets");
            if(previous!=null)require(compare(previous.key,book.key)<0,"strict stable ordering");
            previous=book;
        }
        require(observed.equals(expected),"all actual SDK sources appear exactly once");
    }
    private void reverseKeysetMatchesForwardOrder() {
        List<CatalogStore.ShelfBook> expectedRows=all("");
        CatalogStore.ShelfKey before=new CatalogStore.ShelfKey("\uffff","txt:"+"f".repeat(64));
        int end=expectedRows.size();
        while(end>0) {
            List<CatalogStore.ShelfBook> page=store.shelfPage("",before,true,false,new CancellationSignal());
            require(page.size()==Math.min(50,end),"reverse page size");
            for(int at=0;at<page.size();at++)require(page.get(at).key.bookKey.equals(expectedRows.get(end-page.size()+at).key.bookKey),"reverse page content");
            before=page.get(0).key; end-=page.size();
        }
        require(store.shelfPage("",before,true,false,new CancellationSignal()).isEmpty(),"first-page boundary");
    }
    private void sameTitleUsesSourceKeyTieBreak() {
        List<CatalogStore.ShelfBook> rows=all("Tie title"); require(rows.size()==130,"same-title corpus size");
        for(int at=1;at<rows.size();at++)require(rows.get(at-1).key.bookKey.compareTo(rows.get(at).key.bookKey)<0,"source identity tie-break");
    }
    private void titleAuthorAndLiteralSearch() {
        require(all("BOOK 0200").size()==1,"title case-insensitive search");
        require(all("Shelf Author").size()==1,"author from real PDF SDK import");
        require(all("100%_").size()==1,"percent and underscore are literal user input");
        require(all("absent title").isEmpty(),"empty search results");
    }
    private void canonicalSearchPreservesDisplayBytes() {
        List<CatalogStore.ShelfBook> composedTitle=all("Caf\u00e9 source"), decomposedTitle=all(NFD_TITLE);
        List<CatalogStore.ShelfBook> composedAuthor=all("R\u00e9n\u00e9"), decomposedAuthor=all("Re\u0301ne\u0301");
        require(composedTitle.size()==1 && decomposedTitle.size()==1
                && composedTitle.get(0).key.bookKey.equals(decomposedTitle.get(0).key.bookKey),
                "NFC and NFD title queries identify the same real SDK source");
        require(composedAuthor.size()==1 && decomposedAuthor.size()==1
                && composedAuthor.get(0).key.bookKey.equals(decomposedAuthor.get(0).key.bookKey),
                "NFC and NFD author queries identify the same real PDF source");
        require(java.util.Arrays.equals(composedTitle.get(0).title.getBytes(StandardCharsets.UTF_8),NFD_TITLE.getBytes(StandardCharsets.UTF_8))
                && java.util.Arrays.equals(composedAuthor.get(0).author.getBytes(StandardCharsets.UTF_8),NFD_AUTHOR.getBytes(StandardCharsets.UTF_8)),
                "catalog preserves the public SDK's original decomposed display title and author bytes");
    }
    private void cancelsQueriesAndRejectsWrongOwner() throws Exception {
        CancellationSignal canceled=new CancellationSignal(); canceled.cancel();
        try { store.shelfPage("",null,false,false,canceled); throw new AssertionError("canceled query returned"); }
        catch(OperationCanceledException expected) { }
        AtomicReference<Throwable> result=new AtomicReference<>();
        Thread other=new Thread(()->{try {store.shelfPage("",null,false,false,new CancellationSignal());}catch(Throwable error){result.set(error);}});
        other.start(); other.join(5000);
        require(!other.isAlive() && result.get() instanceof IllegalStateException,"owner thread confinement");
    }
    private void hidesUnmappedAndDeletedProducts() throws Exception {
        CatalogStore.ShelfBook book=all("").get(0);
        try(CatalogStore product=new CatalogStore(context,new File(directory,"reader-catalog.db"))) {
            product.database().execSQL("UPDATE reader_books SET deleted=1 WHERE book_key=?",new Object[]{book.key.bookKey});
            require(store.localShelfBook(book.sdkBookId)==null && all("").size()==TOTAL-1,"deleted products hidden");
            product.database().execSQL("UPDATE reader_books SET deleted=0 WHERE book_key=?",new Object[]{book.key.bookKey});
            product.removeLocalBook(book.sdkBookId);
            require(store.localShelfBook(book.sdkBookId)==null && all("").size()==TOTAL-1,"unmapped products hidden");
        }
        store.repairMissingMappings(); require(all("").size()==TOTAL,"production repair recovers the real local source");
    }
    private void repairsNewImportBeforeRefresh() throws Exception {
        File source=new File(directory,"new.txt"); write(source,"A genuinely new source after the initial shelf snapshot.\n".getBytes(StandardCharsets.UTF_8));
        NativeLibrary.ImportResult book=store.importFile(source.getPath(),NativeLibrary.FORMAT_TXT,"New arrival");
        require(book.created && store.localShelfBook(book.id)==null,"SDK commit precedes product mapping");
        store.repairMissingMappings();
        require(all("New arrival").size()==1 && store.localShelfBook(book.id)!=null,"refreshed page sees production repair");
    }

    private void canceledOldSearchCannotReplaceNewResults() throws Exception {
        java.util.concurrent.ConcurrentLinkedQueue<Runnable> scheduled=new java.util.concurrent.ConcurrentLinkedQueue<>();
        AtomicReference<CatalogShelf> controller=new AtomicReference<>();
        AtomicReference<android.widget.EditText> input=new AtomicReference<>();
        AtomicReference<Throwable> failure=new AtomicReference<>();
        runOnMainSync(()->{
            android.widget.EditText search=new android.widget.EditText(context); input.set(search);
            android.content.SharedPreferences preferences=context.getSharedPreferences("shelf-race-test",Context.MODE_PRIVATE);
            preferences.edit().clear().commit();
            CatalogShelf shelf=new CatalogShelf(context,new android.widget.ListView(context),search,
                    new android.widget.TextView(context),preferences,scheduled::add,
                    (query,anchor,before,inclusive,signal)->store.shelfPage(query,anchor,before,inclusive,signal),failure::set);
            controller.set(shelf); shelf.start(); search.setText("Book 0200");
        });
        try {
            long deadline=SystemClock.uptimeMillis()+5000;
            while(scheduled.size()<2 && SystemClock.uptimeMillis()<deadline)SystemClock.sleep(25);
            require(scheduled.size()==2,"old and debounced replacement requests queued independently");
            scheduled.remove().run(); waitForIdleSync();
            runOnMainSync(()->{
                try { require(new JSONObject(controller.get().observation()).getInt("cached_rows")==0,
                        "canceled old search never flashes back while replacement is pending"); }
                catch(Exception error){throw new IllegalStateException(error);}
            });
            scheduled.remove().run(); waitForIdleSync();
            AtomicReference<String> observed=new AtomicReference<>();
            runOnMainSync(()->observed.set(controller.get().observation()));
            JSONObject value=new JSONObject(observed.get());
            require(failure.get()==null && value.getString("query").equals("Book 0200")
                    && value.getInt("cached_rows")==1 && value.getLong("discarded_results")>=1,
                    "actual new catalog result wins and canceled result is discarded");
            require(value.getJSONArray("keys").getString(0).equals(all("Book 0200").get(0).key.bookKey),
                    "replacement source identity is from the real product catalog");
        } finally { runOnMainSync(()->controller.get().close()); }
    }

    private void missingEndAnchorFallsBackWithinSameFilter() throws Exception {
        java.util.concurrent.ConcurrentLinkedQueue<Runnable> scheduled=new java.util.concurrent.ConcurrentLinkedQueue<>();
        AtomicReference<CatalogShelf> controller=new AtomicReference<>();AtomicReference<Throwable> failure=new AtomicReference<>();
        List<String> queries=new ArrayList<>();
        runOnMainSync(()->{
            android.content.SharedPreferences preferences=context.getSharedPreferences("shelf-fallback-test",Context.MODE_PRIVATE);
            preferences.edit().clear().putString("catalog_query","Book 0200").putString("catalog_top_sort","\uffff")
                    .putString("catalog_top_key","txt:"+"f".repeat(64)).commit();
            CatalogShelf shelf=new CatalogShelf(context,new android.widget.ListView(context),new android.widget.EditText(context),
                    new android.widget.TextView(context),preferences,scheduled::add,(query,anchor,before,inclusive,signal)->{
                        queries.add(query);return store.shelfPage(query,anchor,before,inclusive,signal);
                    },failure::set);
            controller.set(shelf);shelf.start();
        });
        try {
            require(scheduled.size()==1,"restore request is bounded to one scheduled query");
            scheduled.remove().run();waitForIdleSync();
            require(scheduled.size()==1,"missing end anchor schedules one reverse fallback");
            scheduled.remove().run();waitForIdleSync();
            AtomicReference<String> observed=new AtomicReference<>();runOnMainSync(()->observed.set(controller.get().observation()));
            JSONObject value=new JSONObject(observed.get());
            require(failure.get()==null && queries.size()==2 && queries.get(0).equals("Book 0200") && queries.get(1).equals("Book 0200"),
                    "reverse fallback never broadens or changes the restored filter");
            require(value.getInt("cached_rows")==1 && !value.getBoolean("has_after")
                    && value.getJSONArray("keys").getString(0).equals(all("Book 0200").get(0).key.bookKey),
                    "missing end anchor returns the actual filtered predecessor, without unrelated books");
        } finally {runOnMainSync(()->controller.get().close());}
    }

    private void pendingRestoreRetainsOnlySameQueryAnchor() throws Exception {
        CatalogStore.ShelfKey anchor=all("Book 0200").get(0).key;
        java.util.concurrent.ConcurrentLinkedQueue<Runnable> scheduled=new java.util.concurrent.ConcurrentLinkedQueue<>();
        android.content.SharedPreferences preferences=context.getSharedPreferences("shelf-lifecycle-test",Context.MODE_PRIVATE);
        AtomicReference<Throwable> failure=new AtomicReference<>();
        runOnMainSync(()->{
            preferences.edit().clear().putString("catalog_query","Book 0200").putString("catalog_top_sort",anchor.sortTitle)
                    .putString("catalog_top_key",anchor.bookKey).putInt("catalog_top_y",-4).commit();
            CatalogShelf unopened=new CatalogShelf(context,new android.widget.ListView(context),new android.widget.EditText(context),
                    new android.widget.TextView(context),preferences,scheduled::add,
                    (query,key,before,inclusive,signal)->store.shelfPage(query,key,before,inclusive,signal),failure::set);
            unopened.save();unopened.close();
            require(anchor.bookKey.equals(preferences.getString("catalog_top_key",null)),
                    "destroy while SDK is still opening cannot erase a previously saved cursor");
            CatalogShelf shelf=new CatalogShelf(context,new android.widget.ListView(context),new android.widget.EditText(context),
                    new android.widget.TextView(context),preferences,scheduled::add,
                    (query,key,before,inclusive,signal)->store.shelfPage(query,key,before,inclusive,signal),failure::set);
            shelf.start();shelf.save();shelf.close();
        });
        require(anchor.bookKey.equals(preferences.getString("catalog_top_key",null)) && preferences.getInt("catalog_top_y",0)==-4,
                "close while the actual restore request is pending retains the same-filter cursor");
        scheduled.remove().run();waitForIdleSync();
        runOnMainSync(()->{
            android.widget.EditText search=new android.widget.EditText(context);
            CatalogShelf shelf=new CatalogShelf(context,new android.widget.ListView(context),search,
                    new android.widget.TextView(context),preferences,scheduled::add,
                    (query,key,before,inclusive,signal)->store.shelfPage(query,key,before,inclusive,signal),failure::set);
            shelf.start();search.setText("absent title");shelf.save();shelf.close();
        });
        require(preferences.getString("catalog_query","").equals("absent title")
                && preferences.getString("catalog_top_key",null)==null,
                "a changed filter immediately removes the previous filter's cursor even before debounce");
        scheduled.remove().run();waitForIdleSync();require(failure.get()==null,"canceled lifecycle requests never publish a failure");
    }

    private void seedUi() {
        try {
            directory=context.getFilesDir(); seed(directory,true);
            try(BookStore product=new BookStore(context,new File(directory,"library.db"))) {
                store=product; require(all("").size()==TOTAL && !product.metadataRepairPending(),"UI corpus production mapping");
            }
            store=null;
            File output=new File(context.getExternalFilesDir(null),"shelf-tests"); require(output.isDirectory() || output.mkdirs(),"UI seed evidence folder");
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id"))
                    .put("attempt",arguments.getString("attempt")).put("books",TOTAL).put("txt_books",TXT_BOOKS+1)
                    .put("pdf_books",1).put("source_keys",new JSONArray(expected)).put("production_mapping_complete",true);
            write(new File(output,"seed.json"),report.toString(2).getBytes(StandardCharsets.UTF_8));
            Bundle result=new Bundle(); result.putString("stream","EXR_SHELF_SEEDED "+TOTAL+"\n"); finish(Activity.RESULT_OK,result);
        } catch(Throwable error) {
            Bundle result=new Bundle(); result.putString("stream","EXR_SHELF_SEED_FAILED "+error+"\n"); finish(Activity.RESULT_CANCELED,result);
        }
    }

    private static int compare(CatalogStore.ShelfKey a,CatalogStore.ShelfKey b) {
        int title=a.sortTitle.compareTo(b.sortTitle); return title==0 ? a.bookKey.compareTo(b.bookKey) : title;
    }
    private static String sha(byte[] raw) throws Exception {
        byte[] digest=MessageDigest.getInstance("SHA-256").digest(raw); StringBuilder value=new StringBuilder();
        for(byte part:digest)value.append(String.format(Locale.ROOT,"%02x",part&255)); return value.toString();
    }
    private static void write(File file,byte[] bytes) throws Exception { try(FileOutputStream out=new FileOutputStream(file)){out.write(bytes);} }
    private static byte[] read(File file) throws Exception { try(java.io.FileInputStream in=new java.io.FileInputStream(file)){return in.readAllBytes();} }
    private static void require(boolean value,String message) { if(!value)throw new AssertionError(message); }
    private static void remove(File file) throws Exception {
        if(!file.exists())return;
        if(file.isDirectory())for(File child:file.listFiles())remove(child);
        require(file.delete(),"fixture cleanup");
    }
    private static void pdf(File file) throws Exception {
        String content="BT /F1 14 Tf 20 100 Td (A real PDF with an author) Tj ET\n";
        StringBuilder author=new StringBuilder("FEFF");
        for(byte value:NFD_AUTHOR.getBytes(StandardCharsets.UTF_16BE))author.append(String.format(Locale.ROOT,"%02X",value&255));
        String[] objects={"<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                "<< /Length "+content.length()+" >>\nstream\n"+content+"endstream",
                "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>","<< /Title (Authored sample) /Author <"+author+"> >>"};
        java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
        bytes.write("%PDF-1.4\n".getBytes(StandardCharsets.US_ASCII)); int[] offsets=new int[objects.length];
        for(int at=0;at<objects.length;at++){offsets[at]=bytes.size();bytes.write(((at+1)+" 0 obj\n"+objects[at]+"\nendobj\n").getBytes(StandardCharsets.US_ASCII));}
        int xref=bytes.size();bytes.write(("xref\n0 "+(objects.length+1)+"\n0000000000 65535 f \n").getBytes(StandardCharsets.US_ASCII));
        for(int offset:offsets)bytes.write(String.format(Locale.ROOT,"%010d 00000 n \n",offset).getBytes(StandardCharsets.US_ASCII));
        bytes.write(("trailer\n<< /Size "+(objects.length+1)+" /Root 1 0 R /Info 6 0 R >>\nstartxref\n"+xref+"\n%%EOF\n").getBytes(StandardCharsets.US_ASCII));
        write(file,bytes.toByteArray());
    }
}
