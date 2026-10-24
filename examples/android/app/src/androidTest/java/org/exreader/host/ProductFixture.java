// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.database.Cursor;
import android.database.MatrixCursor;
import java.io.File;
import java.util.LinkedHashMap;
import java.util.Map;

/** Instrumentation-only SQL/fault injection through the exact product native provider. */
final class ProductFixture implements AutoCloseable {
    static { System.loadLibrary("exreader_product"); }
    private static final Map<String,ProductFixture> opened=new LinkedHashMap<>();
    private final String path;
    private final Thread owner=Thread.currentThread();
    private long handle;
    private boolean transaction,successful;
    private ProductFixture(String path) { this.path=path;handle=openNative(path); }
    static ProductFixture of(CatalogStore catalog) { return open(catalog.file()); }
    static ProductFixture open(File file) {
        String path=file.getAbsolutePath();ProductFixture value=opened.get(path);
        if(value==null){value=new ProductFixture(path);opened.put(path,value);}return value;
    }
    static void closeAll() { for(ProductFixture value:opened.values().toArray(new ProductFixture[0]))value.close(); }
    static boolean deleteDatabase(File file) {
        ProductFixture found=opened.get(file.getAbsolutePath());if(found!=null)found.close();
        for(String suffix:new String[]{"-wal","-shm","-journal"})new File(file.getAbsolutePath()+suffix).delete();
        return !file.exists() || file.delete();
    }
    void execSQL(String sql) { execSQL(sql,null); }
    void execSQL(String sql,Object[] args) { check();execNative(handle,sql,args); }
    Cursor rawQuery(String sql,String[] args) {
        check();String[][] values=queryNative(handle,sql,args);MatrixCursor rows=new MatrixCursor(values[0]);
        for(int i=1;i<values.length;i++)rows.addRow(values[i]);return rows;
    }
    void beginTransaction() { check();if(transaction)throw new IllegalStateException("Nested fixture transaction");execSQL("BEGIN IMMEDIATE");transaction=true;successful=false; }
    void setTransactionSuccessful() { if(!transaction)throw new IllegalStateException("No fixture transaction");successful=true; }
    void endTransaction() { if(!transaction)throw new IllegalStateException("No fixture transaction");execSQL(successful?"COMMIT":"ROLLBACK");transaction=false; }
    private void check() { if(Thread.currentThread()!=owner || handle==0)throw new IllegalStateException("Fixture requires its owner"); }
    @Override public void close() { check();closeNative(handle);handle=0;opened.remove(path); }
    static native void failNextMigration();
    private static native long openNative(String path);
    private static native void closeNative(long handle);
    private static native void execNative(long handle,String sql,Object[] args);
    private static native String[][] queryNative(long handle,String sql,String[] args);
}
