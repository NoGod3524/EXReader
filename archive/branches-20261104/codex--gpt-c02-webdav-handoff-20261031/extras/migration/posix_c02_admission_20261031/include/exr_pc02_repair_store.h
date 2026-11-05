/* SPDX-License-Identifier: MIT */
#ifndef EXR_PC02_REPAIR_STORE_H
#define EXR_PC02_REPAIR_STORE_H
#include <exr_pc02.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
 pc02_identity identity;
 uint64_t bytes;
 char sha256[65];
} pc02rp_info;
typedef struct {
 pc02rp_info info;
 unsigned char *data;
 size_t bytes;
} pc02rp_blob;
/* All raw objects are <=4MiB. Caller owns native EX custody and pins the
   directory namespace independently. File descriptors are borrowed, never
   closed or repositioned. Files must be euid-owned0600/single-link and ACL-safe;
   destination directory must be euid-owned0700 and ACL-safe. Zero raw bytes are
   allowed. maximum is an additional <=4MiB bound (zero admits only empty raw).
   read_raw compares two independent full preads/hashes and stable fstat. */
int pc02rp_read_raw(int fd,size_t maximum,pc02rp_blob *);
void pc02rp_free(pc02rp_blob *);
/* Original bytes are copied unchanged. Both original and archive are read
   back independently. No overwrite, source mutation or evidence cleanup. */
int pc02rp_archive(int source_fd,int archive_directory,const char *new_leaf,
 size_t maximum,pc02rp_info *original,pc02rp_info *saved);
/* PC02R001: kind8,sequence16,payloadSize24,selfID32,payloadSHA48,
   payload112,footer SHA256(header+payload). kind/sequence/payload must be
   nonzero. Full wrapped object including footer remains <=4MiB.
   O_EXCL temp -> fsync -> independent readback -> native NOREPLACE final ->
   directory fsync -> independent final readback. Failures retain all names. */
int pc02rp_write(int directory,const char *final_leaf,uint64_t kind,
 uint64_t sequence,const void *payload,size_t bytes,pc02rp_info *saved);
/* Validates actual self ID, complete wire, kind/sequence, payload/footer SHA,
   plus exact whole-file info if supplied. Returns payload bytes only;
   payload.info still describes the complete raw stored object.
   Any absent/invalid/uncertain object returns zero, never an empty success. */
int pc02rp_read(int directory,const char *leaf,uint64_t kind,uint64_t sequence,
 const pc02rp_info *exact_or_NULL,pc02rp_blob *payload);
#ifdef __cplusplus
}
#endif
#endif
