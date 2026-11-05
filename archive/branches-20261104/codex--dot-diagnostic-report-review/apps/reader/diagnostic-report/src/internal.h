/* SPDX-License-Identifier: MIT */
#ifndef READER_DIAG_INTERNAL_H
#define READER_DIAG_INTERNAL_H

#include "reader_diagnostic_report.h"

/* One same-directory temporary name is tried per attempt. The name carries the
   process id and the attempt index, so a leftover from a killed process never
   blocks a later writer; no clock and no global mutable state are needed. */
#define RD_TEMP_TAG ".reader-diagnostic.tmp-"
#define RD_TEMP_ATTEMPTS 16u
#define RD_CHUNK_BYTES 4096u

struct reader_diag_report {
  char json[READER_DIAG_MAX_JSON_BYTES + 1u];
  size_t json_size;
  char summary[READER_DIAG_MAX_SUMMARY_BYTES + 1u];
  size_t summary_size;
};

/* Test-only instrumentation. This header is never installed and the package
   build never defines the macro, so the shipped library has no such symbols, no
   environment switch and no clock. Only the cloud test worker links the library
   variant that is compiled with READER_DIAGNOSTIC_TEST_HOOKS. */
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
typedef struct {
  size_t json;    /* 0 = contract hard limit */
  size_t summary; /* 0 = contract hard limit */
} rd_test_limits;
extern rd_test_limits rd_test_output_limits;
extern void rd_test_pause_before_commit(void);
extern void rd_test_pause_after_commit(void);
extern int rd_test_io_failure(unsigned stage);
#endif

void rd_error_set(reader_diag_error *error, reader_diag_status status, int system_error,
                  const char *message);
int rd_cancel_requested(const reader_diag_control *control);

/* Publishes data as a new file; never replaces an existing path. */
reader_diag_status rd_write_new_file(const char *utf8_path, const void *data, size_t size,
                                     const reader_diag_control *control,
                                     reader_diag_error *error);

#endif
