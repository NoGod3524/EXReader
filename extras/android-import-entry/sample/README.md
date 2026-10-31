# Installed integration sample

This bridge uses the OS application Context as its native scope. Its fixed routes
are `files/library.db` and `no_backup/c02-admission`; a migration package cannot
select either root. The reader and migrator must use this same native authority.

Call `NativeBridge.create(context)` only for an explicit new-library action, or
`NativeBridge.enroll(context)` for explicit verification of an existing library.
These are separate from ordinary `NativeBridge.open(context)`, which never
creates a database, adopts an existing root or repairs PENDING state. Missing,
partial, replaced and pending authority all refuse before SDK open.

```java
// Fields and method in the host owner:
long handle;
ImportEntry entry;
ExecutorService sdkOwner = Executors.newSingleThreadExecutor();

void openAdmittedLibrary(Context context) {
    sdkOwner.execute(() -> {
        handle = NativeBridge.open(context); // after an explicit initialization action
        if (handle == 0) throw new IllegalStateException("Library admission is unavailable");
        entry = ImportEntry.create(context, context.getFilesDir(), sdkOwner, new ImportOwner() {
            public void onReady(ImportTicket t, ReadyRequest r) {
                long[] result = NativeBridge.commit(handle, r.file().getAbsolutePath(),
                        r.format().exrCode(), r.title(), r.size());
                if (result[0] == 0) entry.release(r);
            }
            public void onFailed(ImportTicket t, ImportError e) { /* show e.code() */ }
        });
    });
}
```

The bridge retains SH through all synchronous SDK work and closes the actual SDK
owner before releasing its admission. The old String path API refuses; it cannot
open an unprotected library. No source or deferred worker escapes this sample.

Compile the installed `host_bridge.c` and link the installed C02 SDK adapter,
native admission and ABI2 archives in addition to import-entry/sideload. When
using the shared SDK, consume these archives by file to avoid a second static SDK
provider. The probe CMake under `tests/reader_android_import_entry` is the complete
installed-prefix recipe. Use the Context scope for Android; the desktop strict
POSIX path API intentionally does not accept Android system ancestors.
