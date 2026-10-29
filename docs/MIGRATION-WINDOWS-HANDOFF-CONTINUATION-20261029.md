# Windows migration native fixture continuation — 2026-10-29

The exact original source 5db9c2c0b574b0e63675a38b0653f3a9bdd2cb1c failed
[40888673546](https://github.com/NoGod3524/EXReader/actions/runs/40888673546):
43/43 frozen preflight + 21/24 Windows groups = 64/67. Retained inspection
[40935211059](https://github.com/NoGod3524/EXReader/actions/runs/40935211059)
rehashed original artifact 12904771798 (3,639,934 bytes,
SHA-256 3538655a45319332ef8f197deeaa25815737aed3feeeeab66c3b78bf240f3143)
and read the three exact tracebacks. g10, g15 and g17 failed at Python
Path.rename, before their required downstream predicates could be evaluated.

This continuation follows the user's 2026-10-29 instruction to repair the
problems and advance the mainline. The old one-SHA/30-minute authorization
and its failed result remain historical and are not rerun or overwritten.
This new source gets one independent 67-group/30-minute Actions round,
without increasing any helper, record, byte, group or runner budget.

Only the new Windows qualification driver changes. No SDK, adapter, production
owner, frozen preflight byte/assertion, share flag or pin lifetime changes.
The added test-only rename stimulus uses native FileRenameInformation class 10,
NULL RootDirectory and a single destination leaf, no replacement and no fallback.
It first pins the same private test fixture root and checks full volume/FileID,
non-reparse regular/directory metadata, direct actual normalized volume-GUID
parent membership, bounded leaf names, and a metadata reopen's exact source ID.
It retains those handles through the operation and checks the destination entry,
source handle and root after success. The g11 additions independently check
successful exact-identity publication, occupied-destination refusal and rejection
of nested/different-parent requests. These are additive controls inside g11;
all original 24 group assertions remain.

The four call sites formerly using absolute-path Python rename now use this
equivalent no-replace sibling operation. In g10 the baseline file read handle
has closed, while parent namespace pins remain; the required equal-byte foreign
replacement must still be detected before COMMIT. Request/output mutations occur
before the child's output pin. In g15 the original SDK-live output-pin rename
refusal remains unchanged; only the separately paused pre-I/O/pre-pin child's
output-disappearance stimulus changes. In g17 the actual child wait has completed
before the absent/partial-result stimulus. No object pin is removed to create a
negative state. Actual refusal at any native call fails directly.

The inferred cause is incompatibility of the absolute-target rename route with
the intentionally pinned parent namespace; the old error does not uniquely prove
an internal Windows open sequence. The new syscall's runtime result remains a
measurement, not an assumed pass. No D13 experiment or user data is involved.

This remains a test-only Windows prerequisite. Product admission, full P0,
physical power-loss qualification, directory-fsync equivalence and F12 stay
false until the separate integration and complete delivery gates pass.

## Setup failure retained

The first continuation workflow [40936057156](https://github.com/NoGod3524/EXReader/actions/runs/40936057156),
source ecbe0123e4a3ce943f6569c29b9791b92dd9cbab, stopped in the source guard:
Windows Python attempted cp1252 decoding of the original UTF-8 driver from git
show and raised UnicodeDecodeError. No SDK build or qualification group ran
(0/67 executed, not a 67-group behavioral failure). The guard now specifies
encoding='utf-8'. The reviewed driver and every native assertion remain unchanged;
the next source still requires the exact 67 groups and original 30-minute job.
