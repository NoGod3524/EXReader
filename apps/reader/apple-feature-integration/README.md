# Apple five-module integration (D15)

This additive host profile uses installed AnnotationImport raw 0.2, FontLibrary 0.1,
OriginalExport 0.1, JumpHistory raw 0.2 and SyncView raw 0.2, plus the installed
AnnotationExport prerequisite. It does not modify SDK, product schemas or modules.

`tools/build_apple_wave3.py` is the Actions-only installer. The D15 project wrapper
preserves the old Xcode generator and old assertions, and enables
`EXR_APPLE_WAVE3` with the explicit raw profile. Both profiles retain the unchanged product checker and its original build phase.
The importer FOUND callback uses the existing HostSDK public dynamic-SDK wrappers;
no static product resolver or SDK is introduced. SDK calls resolve to libexreader.dylib.

Font leases use an OS-thread owner, with synchronous admission from the existing
SDK serial owner. Layout/fixed wrappers retain HostFont; borrowed fonts are never
freed with exr_font_free. Replacement is rendered before publication and rolls back
on any failure. A legacy handle is opened transiently on the *same catalog* only for
public v2 history encoding; no second store/schema/writer is introduced. History
cursor completion follows an accepted FOUND frame, not a speculative target.

The tools sheet lives under More. Import previews retain the exact input and native
fingerprint and require an explicit second confirmation. NULL is preserved by the
native importer, never synthesized into a navigable selector. Original exports use
hash names, explicit directory/security scope and native receipts, never overwrite.
Sync snapshots are read-only and never interpret one sweep as full synchronization.

CI retains every round's original artifacts and authenticates them within Actions.
Device signing and physical devices remain outside the ad-hoc simulator/macOS scope.
