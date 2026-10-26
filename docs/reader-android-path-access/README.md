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
