/* SPDX-License-Identifier: MIT */
/* Undefine after imported PUBLIC definitions to test each header guard. */
#if defined(PURE_HEADER_RAW_ZERO) || defined(PURE_HEADER_RAW_UNDEFINED)
#undef EXR_READER_SELECTOR_BYTES_CANDIDATE
#ifdef PURE_HEADER_RAW_ZERO
#define EXR_READER_SELECTOR_BYTES_CANDIDATE 0
#endif
#else
#undef EXR_READER_PURE_CAPTURE_CANDIDATE
#ifdef PURE_HEADER_ZERO
#define EXR_READER_PURE_CAPTURE_CANDIDATE 0
#endif
#endif
#include <reader_reading_state_capture_raw_candidate.h>
int main(void) { return 0; }
