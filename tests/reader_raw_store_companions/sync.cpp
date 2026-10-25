/* Reuse the original native UTF-16 command boundary and real TLS consumer;
   only explicit capability API names change in this independent test target. */
#include <reader_sync.h>
#define reader_revisions_open reader_revisions_open_raw_v3
#define reader_sync_create reader_sync_create_raw_v3
#define reader_sync_step reader_sync_step_raw_v3
#include "../reader_sync/consumer/main.cpp"
