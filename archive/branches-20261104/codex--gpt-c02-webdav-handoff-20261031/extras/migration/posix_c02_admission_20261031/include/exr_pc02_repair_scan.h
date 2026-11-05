/* SPDX-License-Identifier: MIT */
#ifndef EXR_PC02_REPAIR_SCAN_H
#define EXR_PC02_REPAIR_SCAN_H
#include <exr_pc02.h>
#include <exr_wh.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Pure byte scanners. The caller owns EX custody, obtains identity from actual
   fstat, reads exact bytes twice, and independently pins every namespace.
   None of these functions opens a file, changes evidence or grants admission. */
typedef struct {
 pc02_identity identity;
 const unsigned char *data;
 size_t bytes;
} pc02rs_blob;
typedef struct {
 size_t count,keep_bytes,tail_bytes;
 unsigned char kind;
 uint64_t sequence,generation;
 pc02_identity target;
 char seal[65],previous_clean[65],terminal[65],raw_sha256[65],prefix_sha256[65];
 pc02_pending_record pending;
} pc02rs_state;

/* Every complete S368 is checked. A remaining 1..367 bytes is described only;
   success does not authorize dropping or reconstructing it. Initial I must be
   complete. Complete malformed records are never treated as a partial tail. */
int pc02rs_state_prefix(const pc02rs_blob *,pc02rs_state *);
/* Construct one legal exact B/C after the verified complete prefix. A B must
   leave capacity for its eventual C. Caller independently proves each supplied
   tuple and target; the constructed bytes do not establish authority. */
int pc02rs_state_next(const pc02rs_state *,unsigned char kind,
 const char manifest[65],const char input[65],const char terminal[65],
 const pc02_identity *,unsigned char out[368]);
/* Re-scans the original blob and requires the nonempty partial tail to equal
   the prefix of that one canonical next B/C. Does not adopt a descriptor. */
int pc02rs_state_tail(const pc02rs_blob *,const pc02rs_state *,
 const unsigned char expected[368]);

typedef struct {
 size_t ack_count,floor_count,head_count,head_keep_bytes,head_tail_bytes;
 char manifest_sha256[65],last_line_sha256[65],head_raw_sha256[65],head_prefix_sha256[65];
 int publish_intent,committed,aborted,terminal;
 unsigned char next_head[272];
} pc02rs_tx;

/* The caller independently constructs expected_header464 from immutable INPUT
   origin Binding, generation/input and registered actual head ID. floors and
   ACKs are canonical namespace inventories, sorted ordinal 1..N; embedded
   ordinals, slots, self IDs and complete hashes are verified again here.
   Production FLOOR352 only. All complete ACK lines pass wh_journal_check.
   Only one interrupted append is admitted: a-f in {0,1}, h<=f, f-h in {0,1};
   a must equal f if h<f or the head has a partial record. A partial R272 must
   match exactly the one next record reconstructed from the real final floor.
   A shorter complete head is preserved and may be explicitly caught up later. */
int pc02rs_transaction(const pc02rs_blob *head,
 const unsigned char expected_header[464],
 const pc02rs_blob *floors,size_t floor_count,
 const pc02rs_blob *acks,size_t ack_count,
 const wh_binding *,const wh_gates *,const pc02_pending_record *exact,
 pc02rs_tx *);

#ifdef __cplusplus
}
#endif
#endif
