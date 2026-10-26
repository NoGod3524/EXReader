# Android intermediate directory access candidate

Root candidate based on `7752663d285ce9d47621b12a4e902d4da4f5cb6d`.
The frozen SDK, both C ABI headers, module versions, all existing drivers,
budgets and prior failure evidence remain unchanged.

Android app sandboxes cannot open filesystem ancestors for directory reading.
Font-library and original-export currently request `O_RDONLY` from `/`, before
reaching the app-owned directory, and their actual UI run `40352736333` failed.
This candidate uses Android `O_PATH` only for root/intermediate descriptors.
Every intermediate component still requires `O_DIRECTORY | O_NOFOLLOW`;
font-library retains descriptor type/identity inspection. Final directories
remain `O_RDONLY` for enumeration, locking and durability. Input font files
remain `O_RDONLY`, and exported files keep the original creation/publication
flags. Other platforms retain their prior access flags.

This does not resolve or retry the blocked D13 path-replacement experiment.
There is no race-safety or physical-device acceptance claim.

The new source guard pins the two exact implementation blobs, checks the whole
tree against the admitted baseline and exercises six source-mutation refusals.
The original guard and UI drivers are kept unchanged; the independent workflow
reuses all real installed-APK suites including the quick-size cancellation and
save-failure checks. All build/runtime/evidence parsing occurs in Actions.

Validation pending; no module or full-product acceptance is granted.

## First actual result and next candidate

Run `40364381911/1`, source `3afaec0d70285b28e115e5258d2f7984d8d1826e`, failed.
The quick-size cancellation and settings-save failure invariants passed on the
real installed APK. Original root-directory opening no longer blocks font-library
initialization, but font import and original publication still fail. The first
cancellation helper passed Android's uncanonicalized app-files alias and was
rejected before polling cancellation; that one fixture directory now uses its
canonical app-owned parent, matching the production host's existing policy.
All cancellation and receipt assertions are unchanged, and the source guard pins
this single exact driver edit alongside the two module files.

The next Android backend uses `renameat2(RENAME_NOREPLACE)` for exclusive
publication, preserving the no-overwrite contract without requiring a hard link.
There is no unsafe fallback when that syscall or flag is unavailable. Rename
consumes the temporary name, so the original-export receipt clears its temporary
cleanup state on that path. Font manifest replacement remains the original
atomic rename. On any platform a failed publication now reports IO unless the
OS reports an actual existing target; only that collision enters hash comparison.
The original failure was misleadingly reporting a conflict for every link error.
This candidate still needs real compilation and runtime verification.

## Second actual result and save-confirmation candidate

Run `40371294601/1`, source `5a9c0c3c`, failed. The first ten of fifteen
initial UI cases passed, including real local font import and selection,
original export, and both quick-size rollback cases. Annotation export first
failed while creating its bookmark: a successful write immediately refreshed
the records list and replaced the save confirmation with the list count.
The following four cases failed after the panel remained open. Later phases
were not executed; this is no overall phase or product acceptance.

ReadingPanel now carries a request-local save confirmation into its successful
list refresh, alongside the refreshed count. Ordinary refresh clears it, and
failed/cancelled refresh still reports the existing error. Explicit pending
request confirmation uses the same path. Request epochs, cancellation, owner
operations and all existing UI assertions/timeouts remain unchanged. The guard
pins the exact additional Java blob. Verification remains pending in Actions.

## Third result and follow-up candidate

Run `40378926513/1`, source `7bd73855f5bd5372cf3d7003ae413db13c4ce951`,
failed overall. The unchanged walkthrough (45/45), review (10/10), bounded
(11/11), navigation (18 checks) and reading (16 checks) passed. Wave3 passed
the first eleven checks, including annotation export and both saves; the next
check failed waiting for the shelf. Later checks also failed, and cancel and
restore phases were not reached. Its artifact is
`reader-wave3-c11-android-40378926513-1`. Audits `40383312035`,
`40383464071` and `40383795120` inspected it in Actions.

The shelf helper now waits within its existing 30-second deadline for either
the shelf or an enabled back button, instead of sampling the button only once.
All original checks and timeouts remain. The saved confirmation also survives
a failed or cancelled list refresh, with separate messages for each outcome.
Two added real UI checks pause the post-save list read, cancel it or let its
existing debug gate fail, and verify the saved bookmark remains. This candidate
requires a fresh complete Actions run; no acceptance is claimed yet.

The original sync check compared counts across a real sync start, whose source
preparation can create book revisions and outbox entries. The test now checks
full revision and outbox rows as well as counts around the idle view and again
around a failed-session view refresh. It records both snapshots spanning the
separate sync preparation and the reported failure in device logcat, rather
than attributing preparation to the read-only view.

## Import identity follow-up

Run `40393784913/1`, source `63a835e4976ce5e7081547759a47829326d333aa`,
passed the first 15 wave3 checks and the walkthrough 45/45, review 10/10,
bounded 11/11, navigation 18 and reading 19 checks. The cancel preview failed
before input parsing: the fresh target had no retained book identity. Its
export artifact contains two annotation heads; no cancellation or restore
acceptance was obtained. Audit `40398326030` records the same attempt.

The candidate now creates a book revision for a verified original on completed
import or when repairing a previously unmapped or unversioned local book. It
reuses the existing stable sync request identity and only bootstraps when there
are no book heads; existing heads and deleted/conflicted graphs are not replaced.
The new revision enters the sync outbox. The cancel check also compares the full
revision and outbox snapshots around preview, preserving the no-write contract.
Full Actions verification is pending.

## Verified Android handoff

Actions run `40404143400/1` passed on source
`2bb0c9e1fec118ca9e49b7530b205d5fcb3aed3b`; independent Actions audit
`40407736690/1` read that attempt's uploaded bytes and reported acceptance with
no problems or missing operations. Artifact
`reader-wave3-c11-android-40404143400-1`, ID `12690229796`, is retained with
SHA-256 `b973e986d169979c70fe7a35e1d32856eb7e7ec08762a75a5cf1d4cee684860d`.
The built and installed APK both hash to
`5aafe17c22328d857e5004956c26e700584e12139e3afd2a9964ab36bbff6020`.

The same run passed walkthrough 45/45, review 10/10, bounded 11/11, navigation
18/18, wave3 20/20 (first 15, cancel 1, restore 4), and reading 19/19 (first
17, retry 1, reopen 1). Reading includes a real process stop at the postcommit
gate and exact-request retry; wave3 used CheckJNI and finished each phase with
zero font leases. The two post-save refresh outcomes and conflict access with
bookmarks and pagination passed. The legacy projection fixture now uses the
existing verified book head and still asserts rejection of the wrong projection.

Prior failures remain recorded: `40371294601` failed after ten wave3 checks on
the overwritten save confirmation and also had review/bounded failures;
`40378926513` passed those regressions but failed returning to the shelf;
`40384044799` and `40384463098` reached the old cross-sync count assertion;
`40385854867` and `40388731881` reached the font status mismatch;
`40389883877` exposed the missing book identity and a reading list visibility
failure; `40393784913` confirmed missing identity as the cancel-preview cause;
`40399321442` failed to compile due to a missing parenthesis; `40400268625`
passed wave3 but exposed the legacy fixture's empty-head assumption.

This is an API 34 x86_64 emulator result, not physical-device or six-platform
acceptance. Wave3 picker results use framework activity-result stubs rather than
driving DocumentsUI; share intent, performance and TalkBack speech are not
accepted by this run. The separate D13 path-replacement experiment remains
blocked and no race-safety claim is made. Book identity creation queues a book
revision on import or repair as explicitly approved; no existing heads are
automatically replaced. The default branch, PRs, tags and releases were not
modified, and `sync_jni.cpp` was not changed.
