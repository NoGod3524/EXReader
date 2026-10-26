/* SPDX-License-Identifier: MIT */
#ifndef READER_READING_STATE_CAPTURE_RAW_CANDIDATE_H
#define READER_READING_STATE_CAPTURE_RAW_CANDIDATE_H
#include <reader_reading_state.h>
#if !defined(EXR_READER_SELECTOR_BYTES_CANDIDATE) || EXR_READER_SELECTOR_BYTES_CANDIDATE != 1 || \
    !defined(EXR_READER_PURE_CAPTURE_CANDIDATE) || EXR_READER_PURE_CAPTURE_CANDIDATE != 1
#error "Use the explicitly installed pure raw capture candidate target"
#endif
#define READER_RS_PURE_CAPTURE_CANDIDATE_VERSION "0.1.0"
#ifdef __cplusplus
extern "C" {
#endif
/* Pure encode/validate, no revision/history/outbox insertion. Preserve the
   supplied actual anchor version 1/2; version 3 is fixed_page only. All
   existing representability and byte limits apply. Raw stores only.
   On failure wire/count are cleared; release successful output with
   reader_rs_free. part is the actual EPUB spine index, ignored otherwise. */
reader_rs_status reader_rs_encode_capture_raw_candidate(
  reader_revisions *store, const reader_rs_envelope *envelope,
  const reader_rs_capture *capture, unsigned anchor_version, size_t part,
  char **wire, size_t *bytes, reader_rs_error *error);
#ifdef __cplusplus
}
#endif
#endif
