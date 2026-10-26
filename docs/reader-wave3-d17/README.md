# D17 exact-source native cancellation / rejection evidence

Fixed seed `d263ce5228838ac90c0a0dc13a5193d4a7739681`; SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e` (include/src/bindings frozen separately).

The original D11 remains unchanged at `da3ba2d1544edff6dc5004dd9d9d88aa732f9b12`, tested `e0e898e1df372fa3b3de4145cf2f1f4ddec01eb4`, run40229380899/1, macOS15/17, pickerCancel precondition failed. No prior result is credited to D17.

All executable work is Actions-only. The new scope guard allows only this package's tests/workflow/docs/handoff. Actual app is built from the same GITHUB_SHA as the driver and independent observer, without review macros; page-theme ON, raw3 OFF. SDK public API observations never SQL-open the SDK. Product DB alone is opened mode=ro and query_only. Each before/after snapshot is read twice to prove quiescent logical state. SDK original bytes are read via exr_library_source and hashed; progress and notes retain NULL-vs-empty distinctions. All product rows (including revisions/outbox) are retained.

Original17 are unchanged: import is fixture native entry; settings is page theme only; resume is actual book reopen, not dedicated Continue. Next/previous/continue must write SDK progress, never originals/notes/product. Import must add one actual SDK source and matching product/local mapping, without revision/outbox writes. All other operations must preserve full SDK and product logical state. Setup transitions are independently observed too. Actual Cancel requires one visible enabled hittable physical control frame, not a Touch Bar alias, and actual dismissal returning the book control. Existing malformed file selection is separately classified rejection, never called cancellation.

No grants for physical keyboard, keyboard modal focus, screen reader, signing, full product, release or another source. Every round retains its own artifacts; maximum3 complete Actions rounds including reruns.
