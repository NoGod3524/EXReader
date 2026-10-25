# Installed integration sample

`host_bridge.c` and `java/.../NativeBridge.java` are a complete minimal host binding.

```java
ExecutorService sdkOwner = Executors.newSingleThreadExecutor();   // the only thread that touches the SDK
ImportEntry entry = ImportEntry.create(context, context.getFilesDir(), sdkOwner, new ImportOwner() {
    public void onReady(ImportTicket t, ReadyRequest r) {          // runs on sdkOwner
        long[] res = NativeBridge.commit(handle, r.file().getAbsolutePath(), r.format().exrCode(), r.title(), r.size());
        if (res[0] == 0) entry.release(r);                         // EXR_OK: durable book id res[1]
    }
    public void onFailed(ImportTicket t, ImportError e) { /* show e.code() */ }
});
for (ReadyRequest r : entry.pendingReady()) { /* re-deliver files left by a killed process */ }
// In the Activity that receives VIEW/SEND or a picker result:  entry.submit(getIntent());
```

Open `handle` with `NativeBridge.open` on that same `sdkOwner` thread.

CMake: `find_package(EXReaderAndroidImportEntry CONFIG REQUIRED)`, compile
`${EXR_ANDROID_IMPORT_ENTRY_SAMPLE_DIR}/host_bridge.c` into your JNI library and link
`EXReaderAndroidImportEntry::exr_android_import_entry`.
