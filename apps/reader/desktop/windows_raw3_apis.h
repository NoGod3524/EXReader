/* App-private opt-in routing. All declarations come from installed public APIs;
 * unchanged/free/cancel functions intentionally keep their shared names. */
#ifndef EXR_WINDOWS_RAW3_APIS_H
#define EXR_WINDOWS_RAW3_APIS_H
#ifdef EXR_READER_WINDOWS_RAW3
#include <reader_metadata.h>
#include <reader_session.h>
#include <reader_projection.h>
#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#if !defined(EXR_READER_SELECTOR_BYTES_CANDIDATE) || !defined(EXR_READER_METADATA_RAW3)
#error Raw Windows host requires the exact installed raw module family
#endif
#define reader_metadata_open reader_metadata_open_raw_v3
#define reader_revisions_open reader_revisions_open_raw_v3
#define reader_revision_get reader_revision_get_raw_v3
#define reader_revision_heads reader_revision_heads_raw_v3
#define reader_revision_book_identity reader_revision_book_identity_raw_v3
#define reader_revision_entities_page reader_revision_entities_page_raw_v3
#define reader_revision_annotations_page reader_revision_annotations_page_raw_v3
#define reader_revision_book_title reader_revision_book_title_raw_v3
#define reader_revision_project reader_revision_project_raw_v3
#define reader_revision_selected reader_revision_selected_raw_v3
#define reader_command_apply_book reader_command_apply_book_raw_v3
#define reader_command_apply_group reader_command_apply_group_raw_v3
#define reader_command_apply_membership reader_command_apply_membership_raw_v3
#define reader_session_create reader_session_create_raw_v3
#define reader_rs_decode reader_rs_decode_raw_v3
#define reader_av_open reader_av_open_raw_v3
#define reader_av_page_get reader_av_page_get_raw_v3
#endif
#endif
