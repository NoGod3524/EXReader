/* SPDX-License-Identifier: MIT */
#ifndef PC02_JOURNAL_H
#define PC02_JOURNAL_H
#include <exr_pc02.h>
#include <exr_wh3.h>
typedef struct {
 pc02_lease *lease;const pc02_pending_record *pending;
 const wh_binding *binding;const wh_gates *gates;
 int parent,directory;pc02_identity identity;char leaf[64];
 wh3_tip tip;pc02_floor floor;size_t count;unsigned temps,serial;
 char manifest_sha[65];pc02_identity ack_identity[256];char ack_raw_sha[256][65];
 char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX];
 const char *pointers[EXR_WH_MAX_JOURNAL];
 void *context;void (*phase)(void *,unsigned);
} pc02_journal;
int pc02j_open(pc02_journal *,pc02_lease *,int parent,const char *leaf,const pc02_identity *,
 const wh_binding *,const wh_gates *,const pc02_pending_record *);
int pc02j_scan(pc02_journal *);
int pc02j_catchup(pc02_journal *,pc02_cap *);
wh3_tx_status pc02j_append(pc02_journal *,pc02_cap *,const wh3_tip *,const char *,wh3_tip *);
int pc02j_close(pc02_journal *);
#endif
