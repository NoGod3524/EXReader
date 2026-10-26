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
