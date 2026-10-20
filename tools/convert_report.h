/* SPDX-License-Identifier: MIT */
#ifndef EXREADER_CONVERT_REPORT_H
#define EXREADER_CONVERT_REPORT_H
#include "convert_json.h"
#include "exreader.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum { CV_PROFILE_TEXT = 1, CV_PROFILE_PRESERVE = 2 } cv_profile;
typedef struct {
  char *id, *input, *output, *entry_path;
  const char *input_format, *input_variant, *format_source;
  cv_profile profile;
  const char *target_format;
  const char *stage, *status;
  int error_code;
  char *error_message;
  int published, reopen_verified, cancel_requested;
  char input_sha[65], output_sha[65];
  unsigned long long input_bytes, output_bytes;
  size_t chapters, resources;
  cv_text degradations;
  cv_text notes;
  unsigned long long elapsed_ms;
} cv_result;
void cv_result_init(cv_result *r);
void cv_result_free(cv_result *r);
const char *cv_status_name(exr_status status);
const char *cv_profile_name(cv_profile profile);
void cv_timestamp_now(char out[32]);
/* Fixed capability/degradation declaration for one profile/target pair. */
void cv_degradations(cv_text *json, cv_profile profile, const char *target,
                     const char *input_format, size_t chapters, size_t resources);
void cv_report_json(cv_text *json, const char *mode, const char *manifest,
                    const char *report_path, int overwrite, int profile_defaulted,
                    int cancel_requested, int batch_complete, int report_written,
                    const cv_result *items, size_t count, const char *started,
                    const char *finished, size_t peak_rss, unsigned long long elapsed_ms);
void cv_capabilities_json(cv_text *json);
#ifdef __cplusplus
}
#endif
#endif
