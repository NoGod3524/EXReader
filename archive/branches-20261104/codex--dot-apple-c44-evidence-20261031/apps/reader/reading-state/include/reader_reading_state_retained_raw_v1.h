/* SPDX-License-Identifier: MIT */
#ifndef READER_READING_STATE_RETAINED_RAW_V1_H
#define READER_READING_STATE_RETAINED_RAW_V1_H
#include "reader_reading_state.h"
#if !defined(EXR_READER_PUBLIC_RETAINED_RAW_V1) || EXR_READER_PUBLIC_RETAINED_RAW_V1 != 1
#error "Use the installed raw ReadingState target with retained API v1"
#endif
#define READER_RS_RETAINED_RAW_API_VERSION "1.0.0"
#ifdef __cplusplus
extern "C" {
#endif
/* API revision v1, not an anchor/store version. Requires a raw-v3 store;
 * permits anchor wire 1/2, or fixed_page-only 3. part is the actual EPUB spine
 * index, never inferred. Pure encode/validation: no revision/history/outbox
 * mutation and no claim of historical provenance (the caller checks the head).
 * Output is cleared on failure and freed with reader_rs_free on success.
 * Availability uses only the existing raw-family switch, not PURE_CAPTURE.
 */
reader_rs_status reader_rs_encode_retained_raw_v1(
    reader_revisions *store,const reader_rs_envelope *envelope,
    const reader_rs_capture *capture,unsigned anchor_version,size_t part,
    char **wire,size_t *bytes,reader_rs_error *error);
#ifdef __cplusplus
}
#endif
#endif
