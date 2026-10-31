# POSIX C02 protected Repair protocol

The desktop owner runs explicit `recover /absolute/LIBRARY` before ordinary native RECOVER admission. Reader and OWNER admission never modify partial state or head bytes. The callback schema parses the original provider INPUT/PREPARED; it does no SDK work or source mutation.

Repair holds the registered route's exclusive lease, root/parent pins and exact original Binding/state identities. It independently reads actual bytes through descriptors. Every complete S record, ACK296, production FLOOR352 and head record remains authoritative. The scanner rejects complete contradictions, missing ACKs/floors, noncanonical names and incompatible simultaneous state/head tails.

A partial B is admissible only when one canonical original INPUT uniquely explains all tail bytes, its original grant equals the registered CLEAN, its stages are still empty, and its journal/head have no accepted records. Repair restores the exact original CLEAN prefix and Binding. It issues no capability or new grant. Multiple matching orphan INPUTs refuse.

A partial C must match the unique C derived from the last complete B, complete terminal ABI2 ACK history and exact original/prepared target identity. Ordinarily its incomplete bytes are trimmed to that full B; fresh recovery then proves the original descriptor and completes normally. If Binding already selects the exact canonical complete C, Repair restores that C instead. It never downgrades a selected complete C.

A partial head record must be the exact prefix of the record determined by the complete corresponding FLOOR352 and actual ACK. Trimming preserves every complete head record and floor; fresh exact floor confirmation catches the head up later. No storage temp is promoted.

## Object envelope and native observations

All integers are unsigned little endian. Native ID16 is device u64 followed by inode u64. Repair payload structs contain only byte/char arrays; they have no padding. Unlike the original A/B/S seals, SHA65 below includes its trailing NUL. Fixed text buffers have zero padding.

Repair objects use a 112-byte header, payload and footer64:

| Offset | Bytes | Meaning |
|---:|---:|---|
| 0 | 8 | PC02R001 |
| 8 | 8 | kind: PLAN1, APPLIED2, DONE3, GUARD4 |
| 16 | 8 | sequence |
| 24 | 8 | payload length |
| 32 | 16 | actual self native ID |
| 48 | 64 | payload SHA256 hex |
| 112 | variable | payload |
| end-64 | 64 | SHA256 of header and payload, hex |

The storage helper creates a private unique `repair-next-PID-SERIAL`, writes/fsyncs it, independently reopens and reads it back, publishes with native NOREPLACE, fsyncs the directory and reads the final actual object back. It retains the creating FD through final readback. Named opens use NOFOLLOW/NONBLOCK and then require a regular file. Raw reads perform two independent preads, EOF checks and three fstats including nanosecond timestamps. The maximum raw object is 4 MiB. Directories are euid-owned0700; files are euid-owned0600 and single-link. Darwin ACL_ALLOW and unsupported/error ACL observations refuse.

REF185 is identity16, size8, whole raw SHA65, leaf96. PART452 is original identity16, original size8, original SHA65, original leaf256, space1, role1, saved identity16, saved size8, saved SHA65, saved leaf16. Spaces are route1/journal2; roles are state1/head2/Binding3/INPUT4/PREPARED5/ACK6/FLOOR7. Original identity belongs to the actual source FD; saved identity belongs to the separate archive copy. The two identities are independently observed.

## PLAN5039 plus PART array

`repair-plan-NNNNNN` has this fixed payload followed by count PART452 values:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 8 | sequence1..256 |
| 8 | 8 | first plan sequence in this epoch |
| 16 | 16 | route native ID |
| 32 | 185 | previous global PLAN REF, zero for first |
| 217 | 185 | previous epoch DONE REF, zero initially |
| 402 | 185 | this epoch GUARD REF |
| 587 | 16 | archive directory native ID |
| 603 | 96 | archive directory leaf |
| 699 | 304 | original INPUT's Binding |
| 1003 | 2951 | canonical provider description |
| 3954 | 8 | pending generation |
| 3962 | 65 | original B seal |
| 4027 | 65 | manifest SHA |
| 4092 | 65 | INPUT payload SHA |
| 4157 | 65 | last complete ACK line SHA |
| 4222 | 1 each | before-BEGIN, publish-intent, committed, aborted, terminal |
| 4227 | 2 | member states, each0..2 |
| 4229 | 8 each | state keep, head keep, state extra, head extra |
| 4261 | 368 | canonical C bytes for selected-C restoration |
| 4629 | 272 | canonical next head record |
| 4901 | 65 each | state target SHA, head target SHA |
| 5031 | 8 | PART count1..520 |
| 5039 | count*452 | PART array |

Description2951 is binding296, gates325, original grant88, original files2*89, prepared files2*89, private pack89, members2*801, journal64, pack leaf64, token49, journal identity16, mirror-present1, prepared-present1. File89 is identity16/size8/SHA65. Member801 is target256/stage256/retained256/present1/originalID16/preparedID16.

Head extra is always0. State extra is0, or368 only when restoring a C already selected by Binding.

The archive leaf is `repair-archive-NNNNNN-PID-SERIAL`. It contains independent `raw-0000` etc copies of original state, head, Binding, INPUT, optional PREPARED and every complete ACK/FLOOR. All originals remain unchanged until archives and protected plan are durable and read back.

The first durable authority object is fixed `repair.guard`: kind4, sequence=epoch first, payload=the full proposed PLAN+PARTs with GUARD REF zero. The canonical PLAN then references that actual guard. An interruption between these publications can finish only the exact already durable proposal. Existing protected plans are never overwritten.

## SDK proof, apply and completion

After PLAN durability, the provider copies actual original DB/mirror, and prepared DB/mirror when publish intent exists, into private `proof-PID-ORDINAL-SERIAL.image` files in the archive. Ordinals0/1 are originals and2/3 prepared. It holds all source and clone FDs until all SDK owners and sources close. Descriptor hashes and exact names/native IDs are checked before and after SDK proof. The original/prepared full source, notes, progress and ledger audio are read through the frozen SDK, and prepared images also pass independent pack verification. Source originals are never opened by this proof's SDK.

Only then may Repair trim the verified unacknowledged tails or restore the selected canonical C. State/head actual IDs remain unchanged. Every write is fsynced and independently read back. On retry the source must exactly match a permitted original/target prefix and may never be shorter than its protected complete prefix.

APPLIED363 is PLAN REF185; state ID16/size8; head ID16/size8; state SHA65/head SHA65. It is immutable `repair-applied-NNNNNN`. Without its exact durable APPLIED, a plan blocks every ordinary lease. With APPLIED, only explicit RECOVER may continue. A later interrupted recovery appends the next PLAN and APPLIED; it must preserve and validate every preceding APPLIED and minimum prefix.

DONE1254 is first8/last8/routeID16; GUARD, last PLAN, last APPLIED and previous DONE REF185 each; final Binding304; state ID16/size8; head ID16/size8; state-prefix SHA65/head-prefix SHA65. Only internal finish/reconcile after actual terminal SDK proof, or explicit pre-BEGIN restoration after original SDK proof, can publish DONE. The fixed guard then moves by NOREPLACE to `repair-guard-FIRST.retired`, preserving its actual identity and raw bytes.

Each subsequent admission checks the complete authority chain, archives, all historical APPLIED minima and current original ACK/FLOOR identities/hashes. A completed epoch also re-reads its entire actual terminal ACK296/FLOOR352/head history and binds it to the exact C. Removing a newly appended terminal ACK cannot reopen an older CLEAN state. Complete head bytes for that epoch cannot grow or disappear after DONE.

A pre-BEGIN DONE is different: it preserves an empty old journal and its exact old464-byte independent head. A later legitimate INPUT can reuse that proposed generation with a different INPUT SHA; its floors belong to the new transaction. The old pre-BEGIN proposal never acquires those floors.

## Preserved namespaces and qualification

Referenced archives contain only exact PART raw leaves, private proof images and their known SQLite companions, plus storage temps. Unreferenced pre-plan archives contain a consecutive raw prefix and storage temps, including an empty archive. They remain evidence and never supply authority. Unknown Repair names and orphan/malformed PLAN/APPLIED/DONE/retired markers refuse admission.

Controls1701..1706 are archive durable, plan durable, state applied, head applied, APPLIED durable and guard retired. The Actions producer keeps the original36 actual-owner and65 historical cases and writes a separate20-case Repair result. It records actual process PID/euid, pipe barrier bytes, ps parent/child observations, SIGKILL/wait results and fresh recovery commands. Damaged, every pre-apply1702, applied-cut, successful DONE and refusal snapshots retain actual source FD identities/raw bytes independently of archive-copy identities. Independent ZIP decoding uses these native observations rather than result booleans. These process-interruption tests make no power-loss guarantee.
