# POSIX C02 migration native protocol (2026-10-31)

The ordinary admission A120 / B304 / S368 formats and strict reader behavior are unchanged. These optional provider operations require an independently opened OWNER/RECOVER lease. They do not prove SDK content, promote an interrupted temp file, clear PENDING, or repair a partial state/head tail.

All integers below are unsigned little endian. Native IDs are device u64 then inode u64. SHA fields contain exactly 64 lowercase hexadecimal bytes without a trailing NUL. A seal is SHA256 of all bytes preceding that seal, represented as 64 hex bytes. SHA256 of the whole raw file is a separate value.

## Immutable metadata

Files are euid-owned mode0600 with one link. The envelope is 568 header bytes, payload (1..65536), then seal64:

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 8 | PC02M001 |
| 8 | 8 | phase: INPUT=1, PREPARED=2, FLOOR=3 |
| 16 | 8 | generation |
| 24 | 8 | payload bytes |
| 32 | 16 | this actual metadata file native ID |
| 48 | 304 | original independently registered Binding |
| 352 | 64 | original INPUT payload SHA |
| 416 | 64 | INPUT: zero SHA; others: exact original B seal |
| 480 | 8 | INPUT/PREPARED:0; FLOOR: count1..256 |
| 488 | 64 | this payload SHA |
| 552 | 16 | independently registered commit-head native ID |
| 568 | variable | payload |
| end-64 | 64 | envelope seal |

INPUT requires clean OWNER without a cap and captures generation+1. Its payload SHA is the input accepted by pc02_begin. PREPARED and FLOOR require the same live capability, original INPUT selection and original B seal. Readers require exact original B descriptor, including after C/Binding publication: the original Binding root/parent/lease/state/route fields, old grant and old target must match that actual B's previous CLEAN and target. Updating Binding never rewrites INPUT or PREPARED.

Names: input-GGGGGGGGGGGGGGGG-INPUTSHA, prepared-GGGGGGGGGGGGGGGG-INPUTSHA, floor-GGGGGGGGGGGGGGGG-NNN. G is canonical 16-digit lowercase hex, NNN is canonical 001..256. Every complete metadata file is created as a unique .metadata-PID-SERIAL temp, written/fsynced, independently reopened/read back, NOREPLACE-renamed, then the route directory is fsynced and the actual final object read back. Linux uses SYS_renameat2(RENAME_NOREPLACE), Darwin renameatx_np(RENAME_EXCL); no link/unlink fallback exists. Temp bytes remain and are never promoted.

## Independent committed-prefix head

Before INPUT publication, commit-head-GGGGGGGGGGGGGGGG-INPUTSHA is created O_EXCL, flushed, independently read back and directory-fsynced. INPUT captures its actual native ID. Its immutable header is 464 bytes: magic PC02F001 at0, generation u64 at8, INPUT SHA64 at16, origin Binding304 at80, self nativeID16 at384, seal64 at400.

Each append is272 bytes: magic PC02H001 at0, count u64 at8, last lineSHA64 at16, whole immutable FLOOR fileSHA64 at80, previous head seal64 at144, seal64 at208. The first previous seal is the header seal. All complete records count; partial or contradictory bytes refuse.

FLOOR payload272: previous count u64 at0, previous last lineSHA64 at8, previous whole FLOOR fileSHA64 at72, next count u64 at136, next lineSHA64 at144, exact manifestSHA64 at208. Empty floor is count0 with zero last/chain and the exact manifest.

Reads enumerate actual final floor names, reject holes/noncanonical names, check every envelope/native ID/hashchain, and require the complete head prefix to match these exact immutable floors. Losing the final FLOOR cannot make the head's committed count disappear. Complete immutable floors beyond a shorter valid head are retained in the observed floor; explicit fresh recovery must prove the actual journal prefix before appending/catching up head. Advance requires exact count/manifest/line/chain CAS; stale expected values never upgrade automatically.

The actual journal ACK must be completely and durably published before advancing FLOOR. FLOOR is durable before head append. A successful advance requires head pwrite/fsync/independent readback and a fresh full floor/head scan. Native controls1401/1402/1403 cover metadata write/publish/durable and1501/1502 cover head write/durable.

pc02_floor_confirm requires a live fresh capability and exact full-floor CAS. It only completes the independently registered head through that exact floor count; it creates no floor, never upgrades expected state, and cannot discard a complete record. The seventeenth native API case actually kills a fresh process at the first FLOOR's1402 publication: recovery observes complete floor1 and the same464-byte head, refuses old count0, then confirms that exact floor and independently observes the same head nativeID grow to736 bytes.

## Production ACK profile

The synchronous production owner uses FLOOR payload352: original272-byte prefix, actual ACK device/inode16 at272, whole raw ACK SHA64 at288. The old pc02_floor_advance API is explicitly the component272 profile. Production pc02_floor_advance_ack requires every earlier floor to be352 and binds actual ACK identity/raw SHA; pc02_floor_check_ack independently compares a selected immutable floor to the actual observed ACK. Common chain/head logic includes the full raw352 envelope hash. The production journal refuses any272 floor, even when its count/line hashes otherwise match.

Actual ACK files use the fixed296-byte PC02ACK1 header documented in ../posix_c02_migration_20261031/README.md. INPUT/B seal, manifest, ordinal, actual self nativeID, complete raw seal and canonical ABI2 line all match independently. The full raw ACK SHA includes its footer. Neither component272 receipts nor supplied line hashes alone prove this production journal binding.

## Native members and lifetime

The only targets are the registered library basename and its .legacy-map.json mirror. Stage and retained names are distinct canonical sibling basenames. The exact native states are original+stage/no-retained, retained+stage/no-target, or retained+published/no-stage. An originally absent mirror never gains a retained original. Unknown objects, identities or errors refuse.

Publication requires live cap, prepare_publish, zero borrows, independent actual original/prepared proof, and NOREPLACE native renames with parent fsync. All original bytes/IDs remain in retained objects. Controls1301/1302/1303 cover old-retained/new-published/member-durable. Any failed/unknown rename poisons the current owner; fresh explicit recovery independently observes exact state.

pc02_abandon only invalidates the exact current in-memory cap when borrows=0 and poisons the lease. No disk bytes change; close can then release handles. Original close with an active cap still refuses.

The original28 admission and10 scope cases remain. The additional17 native API cases exercise actual metadata/head/floor bytes and IDs, contradictory records, last-floor rollback, exact publication, and real process kills at1301/1302. They are component tests: actual_sdk=false and host_wiring=false. They preserve every raw source/failure object via the original Actions inventory.

Required next qualification: actual synchronous SDK owner and canonical per-line journal; explicit archived/protected repair for partial B/C/head tails. Ordinary open still refuses those tails. No power-loss claim is made.
