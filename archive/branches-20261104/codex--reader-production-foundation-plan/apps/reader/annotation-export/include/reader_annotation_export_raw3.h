/* SPDX-License-Identifier: MIT */
#ifndef READER_ANNOTATION_EXPORT_RAW3_H
#define READER_ANNOTATION_EXPORT_RAW3_H
#include <reader_annotation_export.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
#error "reader_annotation_export_raw3.h is the explicit raw0.2 family; build with EXR_READER_SELECTOR_BYTES_CANDIDATE"
#endif
#define READER_ANNOTATION_EXPORT_RAW3_VERSION "0.2.0"
#define READER_ANNOTATION_EXPORT_RAW3_FORMAT "exreader-annotation-export-raw3"
#define READER_ANNOTATION_EXPORT_RAW3_FORMAT_VERSION 1u

/* Explicit raw3 portable export (see docs/reader-next-c06/RAW3-PORTABLE-ANNOTATIONS.md).
   Same options, statistics, error type, ownership, cancellation, streaming,
   output-alias refusal and atomic publication as reader_annotation_export_run,
   but the store must be a reader_revisions_open_raw_v3 store (a legacy store is
   refused with REVISION and nothing is created) and the JSONL uses the distinct
   format exreader-annotation-export-raw3: it adds the original byte length and,
   per head, an independently decoded "location" that preserves NULL / allocated
   empty / NUL bytes with their byte sizes and the source anchor 1/2/3, parser
   and route identity. The legacy entry keeps format 1 and refuses raw stores. */
reader_annotation_export_status reader_annotation_export_raw3_run(const reader_annotation_export_options *,
  reader_annotation_export_stats *,reader_annotation_export_error *);
#ifdef __cplusplus
}
#endif
#endif
