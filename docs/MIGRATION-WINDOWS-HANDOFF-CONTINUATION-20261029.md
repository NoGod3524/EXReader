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

## Real first native result and preserved race

Native continuation 40936421939 at ed734a879c933b78006ce9e78e89921d3c44fe69
completed **66/67**: 43/43 frozen + 23/24 native. g15/g17 and the added g11
stimulus controls passed. g10's original downstream assertion remained failed.
Exact retained-artifact inspection 40937534551 found the 10-request child
refused with regular-open / native FILE_NOT_FOUND (2), before target SDK open.
It observed the gap between the old request's rename and the new identity's
creation, before its initial envelope check. That is a real refusal but does
not prove the specified post-GO foreign-identity rejection.

The test-only native probe now publishes one complete child-envelope-checked
marker after its initial request/target check and before GO ReadFile, before
any output pin or SDK open. Only g10 waits for that actual observation before
creating the original identity-replacement stimulus. The post-GO checks,
all original reason assertions, pin/sharing protections and 120/115-second
bounds remain. The qualification source guard allows precisely this new
probe addition and the source-only product-next document; every other old
source byte is still frozen. No product feature is enabled by the marker.
