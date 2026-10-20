/* SPDX-License-Identifier: MIT */
#include "convert_report.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif

void cv_result_init(cv_result *r) {
  memset(r, 0, sizeof(*r));
  cv_text_init(&r->degradations);
  cv_text_init(&r->notes);
  r->stage = "preflight";
  r->status = "unfinished";
}
void cv_result_free(cv_result *r) {
  free(r->id); free(r->input); free(r->output); free(r->entry_path);
  free(r->error_message);
  cv_text_free(&r->degradations);
  cv_text_free(&r->notes);
  memset(r, 0, sizeof(*r));
}
const char *cv_profile_name(cv_profile profile) {
  return profile == CV_PROFILE_PRESERVE ? "preserve" : "text";
}
const char *cv_status_name(exr_status status) {
  switch (status) {
  case EXR_OK: return "ok";
  case EXR_ARGUMENT: return "argument";
  case EXR_MEMORY: return "memory";
  case EXR_IO: return "io";
  case EXR_ENCODING: return "encoding";
  case EXR_FORMAT: return "format";
  case EXR_LIMIT: return "limit";
  case EXR_DATABASE: return "database";
  case EXR_FONT: return "font";
  case EXR_CANCELLED: return "cancelled";
  case EXR_PASSWORD: return "password";
  case EXR_UNSUPPORTED: return "unsupported";
  default: return "unknown";
  }
}
void cv_timestamp_now(char out[32]) {
  time_t now = time(NULL);
  struct tm tm;
#ifdef _WIN32
  gmtime_s(&tm, &now);
#else
  gmtime_r(&now, &tm);
#endif
  strftime(out, 32, "%Y-%m-%dT%H:%M:%SZ", &tm);
}
static void capability(cv_text *j, const char *name, const char *status, const char *note) {
  cv_text_string(j, "{\"capability\":");
  cv_text_json(j, name);
  cv_text_string(j, ",\"status\":");
  cv_text_json(j, status);
  if (note && *note) {
    cv_text_string(j, ",\"note\":");
    cv_text_json(j, note);
  }
  cv_text_string(j, "}");
}
static const char *title_status(const char *target) {
  if (!strcmp(target, "html") || !strcmp(target, "xhtml") || !strcmp(target, "fb2") ||
      !strcmp(target, "epub"))
    return "preserved";
  return "unsupported";
}
static const char *target_note(const char *target, cv_profile profile) {
  if (profile == CV_PROFILE_PRESERVE && !strcmp(target, "html"))
    return "Single ZIP resource bundle; extract it and open the reported entry_path.";
  if (!strcmp(target, "txt")) return "Plain text contains the declared body text only.";
  if (!strcmp(target, "rtf")) return "RTF paragraphs come from body line breaks; no title part.";
  if (!strcmp(target, "docx")) return "Minimal WordprocessingML paragraph stream.";
  if (!strcmp(target, "epub")) return "Single generated XHTML content document using the text exporter.";
  if (!strcmp(target, "html") || !strcmp(target, "xhtml")) return "Single XHTML document using the text exporter.";
  if (!strcmp(target, "fb2")) return "Single FictionBook section using the text exporter.";
  return "";
}
void cv_degradations(cv_text *j, cv_profile profile, const char *target,
                     const char *input_format, size_t chapters, size_t resources) {
  int preserve = profile == CV_PROFILE_PRESERVE;
  cv_text_string(j, "[");
  if (preserve) {
    capability(j, "text", "preserved", "");
    cv_text_string(j, ","); capability(j, "paragraphs", "preserved", "");
    cv_text_string(j, ","); capability(j, "reading_order", "preserved", "");
    cv_text_string(j, ","); capability(j, "unicode", "preserved", "");
    cv_text_string(j, ","); capability(j, "title", "preserved", "");
    cv_text_string(j, ","); capability(j, "chapters", "preserved", "");
    cv_text_string(j, ","); capability(j, "images", "preserved", "");
    cv_text_string(j, ","); capability(j, "tables", "preserved", "Tree and CSS bytes are copied; this is not a layout-fidelity claim.");
    cv_text_string(j, ","); capability(j, "css", "preserved", "Stylesheets and inline style attributes are copied as resources/tree data.");
    cv_text_string(j, ","); capability(j, "fonts", "preserved", "Font resources are copied byte-for-byte; target rendering is not asserted.");
    cv_text_string(j, ","); capability(j, "links", "preserved", "Internal targets retained when the model can resolve them; external URIs are copied as attributes.");
    cv_text_string(j, ","); capability(j, "footnotes", "preserved", "Note elements and their resources are copied in the tree.");
    cv_text_string(j, ","); capability(j, "annotations", "unsupported", "Document annotations are not part of the exported package model.");
    if (!strcmp(target, "epub")) {
      cv_text_string(j, ",");
      capability(j, "metadata", "degraded",
                 "Title is retained; language, identifiers and other package metadata are regenerated.");
    } else {
      cv_text_string(j, ",");
      capability(j, "metadata", "unsupported", "HTML bundle has no package metadata container.");
    }
  } else {
    capability(j, "text", "preserved", "Declared body text only.");
    cv_text_string(j, ","); capability(j, "paragraphs", "preserved", "Block boundaries become paragraphs/line breaks where the target has them.");
    cv_text_string(j, ","); capability(j, "reading_order", "preserved", "Blocks are emitted in document order.");
    cv_text_string(j, ","); capability(j, "unicode", "preserved", "UTF-8 scalars are retained unless XML 1.0 forbids them; such input is rejected.");
    cv_text_string(j, ","); capability(j, "title", title_status(target), "Title comes from the loaded document model.");
    cv_text_string(j, ","); capability(j, "metadata", "degraded", "Only a minimal generated metadata set exists; input metadata is not round-tripped.");
    cv_text_string(j, ","); capability(j, "chapters", "degraded", "Chapter structure is flattened to one content stream.");
    cv_text_string(j, ","); capability(j, "images", "unsupported", "Text profile never copies images.");
    cv_text_string(j, ","); capability(j, "tables", "degraded", "Cell text survives in reading order; table structure and spans do not.");
    cv_text_string(j, ","); capability(j, "css", "unsupported", "No stylesheet is produced or copied.");
    cv_text_string(j, ","); capability(j, "fonts", "unsupported", "No font resource is copied.");
    cv_text_string(j, ","); capability(j, "links", "degraded", "Link text survives; href/relationship targets are dropped.");
    cv_text_string(j, ","); capability(j, "footnotes", "degraded", "Note text may survive in reading order; note association is lost.");
    cv_text_string(j, ","); capability(j, "annotations", "unsupported", "Annotations are outside the text profile.");
  }
  cv_text_string(j, ",{\"capability\":\"transparency\",\"status\":\"declared\",\"profile\":");
  cv_text_json(j, preserve ? "preserve" : "text");
  cv_text_string(j, ",\"input_format\":");
  cv_text_json(j, input_format);
  cv_text_string(j, ",\"chapters\":");
  cv_text_format(j, "%zu", chapters);
  cv_text_string(j, ",\"package_resources\":");
  cv_text_format(j, "%zu", resources);
  cv_text_string(j, ",\"note\":");
  cv_text_json(j, target_note(target, profile));
  cv_text_string(j, "}");
  cv_text_string(j, "]");
}
static void item_json(cv_text *j, const cv_result *r) {
  cv_text_string(j, "{\"id\":");
  cv_text_json(j, r->id ? r->id : "");
  cv_text_string(j, ",\"profile\":");
  cv_text_json(j, cv_profile_name(r->profile));
  cv_text_string(j, ",\"input\":");
  cv_text_json(j, r->input ? r->input : "");
  cv_text_string(j, ",\"input_format\":");
  cv_text_json(j, r->input_format ? r->input_format : "unknown");
  cv_text_string(j, ",\"input_variant\":");
  cv_text_json(j, r->input_variant ? r->input_variant : "none");
  cv_text_string(j, ",\"format_source\":");
  cv_text_json(j, r->format_source ? r->format_source : "extension");
  cv_text_string(j, ",\"output_format\":");
  cv_text_json(j, r->target_format ? r->target_format : "unknown");
  cv_text_string(j, ",\"output\":");
  cv_text_json(j, r->output ? r->output : "");
  cv_text_string(j, ",\"entry_path\":");
  if (r->entry_path) cv_text_json(j, r->entry_path); else cv_text_string(j, "null");
  cv_text_string(j, ",\"stage\":");
  cv_text_json(j, r->stage ? r->stage : "");
  cv_text_string(j, ",\"status\":");
  cv_text_json(j, r->status ? r->status : "");
  cv_text_string(j, ",\"error_code\":");
  cv_text_format(j, "%d", r->error_code);
  cv_text_string(j, ",\"error_name\":");
  cv_text_json(j, cv_status_name((exr_status)r->error_code));
  cv_text_string(j, ",\"error\":");
  cv_text_json(j, r->error_message ? r->error_message : "");
  cv_text_string(j, ",\"published\":");
  cv_text_string(j, r->published ? "true" : "false");
  cv_text_string(j, ",\"reopen_verified\":");
  cv_text_string(j, r->reopen_verified ? "true" : "false");
  cv_text_string(j, ",\"cancel_requested\":");
  cv_text_string(j, r->cancel_requested ? "true" : "false");
  cv_text_string(j, ",\"input_sha256\":");
  cv_text_json(j, r->input_sha);
  cv_text_string(j, ",\"output_sha256\":");
  cv_text_json(j, r->output_sha);
  cv_text_string(j, ",\"input_bytes\":");
  cv_text_format(j, "%llu", r->input_bytes);
  cv_text_string(j, ",\"output_bytes\":");
  cv_text_format(j, "%llu", r->output_bytes);
  cv_text_string(j, ",\"chapters\":");
  cv_text_format(j, "%zu", r->chapters);
  cv_text_string(j, ",\"package_resources\":");
  cv_text_format(j, "%zu", r->resources);
  cv_text_string(j, ",\"elapsed_ms\":");
  cv_text_format(j, "%llu", r->elapsed_ms);
  cv_text_string(j, ",\"degradations\":");
  if (r->degradations.size) cv_text_append(j, r->degradations.data, r->degradations.size);
  else cv_text_string(j, "[]");
  cv_text_string(j, ",\"notes\":");
  if (r->notes.size && r->notes.data[r->notes.size - 1] == ']')
    cv_text_append(j, r->notes.data, r->notes.size);
  else
    cv_text_string(j, "[]");
  cv_text_string(j, "}");
}
void cv_report_json(cv_text *j, const char *mode, const char *manifest,
                    const char *report_path, int overwrite, int profile_defaulted,
                    int cancel_requested, int batch_complete, int report_written,
                    const cv_result *items, size_t count, const char *started,
                    const char *finished, size_t peak_rss, unsigned long long elapsed_ms) {
  size_t i, expected = count, ok = 0, rejected = 0, failed = 0, cancelled = 0;
  size_t published = 0, unfinished = 0, reopen = 0;
  for (i = 0; i < count; i++) {
    const cv_result *r = &items[i];
    if (!strcmp(r->status, "ok")) ok++;
    else if (!strcmp(r->status, "rejected")) rejected++;
    else if (!strcmp(r->status, "failed")) failed++;
    else if (!strcmp(r->status, "cancelled")) cancelled++;
    else unfinished++;
    if (r->published) published++;
    if (r->reopen_verified) reopen++;
  }
  cv_text_string(j, "{\"schema\":1,\"tool\":\"exreader-convert\",\"engine_version\":");
  cv_text_json(j, exr_version());
  cv_text_string(j, ",\"abi\":");
  cv_text_format(j, "%u", exr_abi_version());
  cv_text_string(j, ",\"mode\":");
  cv_text_json(j, mode);
  cv_text_string(j, ",\"manifest\":");
  if (manifest) cv_text_json(j, manifest); else cv_text_string(j, "null");
  cv_text_string(j, ",\"report_path\":");
  if (report_path) cv_text_json(j, report_path); else cv_text_string(j, "null");
  cv_text_string(j, ",\"report_written\":");
  cv_text_string(j, report_written ? "true" : "false");
  cv_text_string(j, ",\"overwrite\":");
  cv_text_string(j, overwrite ? "true" : "false");
  cv_text_string(j, ",\"profile_defaulted\":");
  cv_text_string(j, profile_defaulted ? "true" : "false");
  cv_text_string(j, ",\"cancel_requested\":");
  cv_text_string(j, cancel_requested ? "true" : "false");
  cv_text_string(j, ",\"started_utc\":");
  cv_text_json(j, started);
  cv_text_string(j, ",\"finished_utc\":");
  cv_text_json(j, finished);
  cv_text_string(j, ",\"elapsed_ms\":");
  cv_text_format(j, "%llu", elapsed_ms);
  cv_text_string(j, ",\"peak_rss_bytes\":");
  cv_text_format(j, "%zu", peak_rss);
  cv_text_string(j, ",\"counts\":{\"expected\":");
  cv_text_format(j, "%zu", expected);
  cv_text_string(j, ",\"actual\":");
  cv_text_format(j, "%zu", count);
  cv_text_string(j, ",\"succeeded\":");
  cv_text_format(j, "%zu", ok);
  cv_text_string(j, ",\"rejected\":");
  cv_text_format(j, "%zu", rejected);
  cv_text_string(j, ",\"failed\":");
  cv_text_format(j, "%zu", failed);
  cv_text_string(j, ",\"cancelled\":");
  cv_text_format(j, "%zu", cancelled);
  cv_text_string(j, ",\"published\":");
  cv_text_format(j, "%zu", published);
  cv_text_string(j, ",\"reopen_verified\":");
  cv_text_format(j, "%zu", reopen);
  cv_text_string(j, ",\"unfinished\":");
  cv_text_format(j, "%zu", unfinished);
  cv_text_string(j, "},\"batch_complete\":");
  cv_text_string(j, batch_complete ? "true" : "false");
  cv_text_string(j, ",\"published_outputs\":[");
  {
    int first = 1;
    for (i = 0; i < count; i++) if (items[i].published) {
      if (!first) cv_text_string(j, ",");
      cv_text_json(j, items[i].output);
      first = 0;
    }
  }
  cv_text_string(j, "],\"items\":[");
  for (i = 0; i < count; i++) {
    if (i) cv_text_string(j, ",");
    item_json(j, &items[i]);
  }
  cv_text_string(j, "]}\n");
}
void cv_capabilities_json(cv_text *j) {
  cv_text_string(j, "{\"schema\":1,\"tool\":\"exreader-convert\",\"engine_version\":");
  cv_text_json(j, exr_version());
  cv_text_string(j, ",\"abi\":");
  cv_text_format(j, "%u", exr_abi_version());
  cv_text_string(j,
      ",\"profiles\":{"
      "\"text\":{\"description\":\"Declared body text, paragraph and reading order. Not lossless/high-fidelity.\","
      "\"inputs\":[\"txt\",\"html\",\"xhtml\",\"fb2\",\"epub\",\"docx\",\"rtf\",\"mobi\",\"kf8\"],"
      "\"outputs\":[\"txt\",\"html\",\"xhtml\",\"fb2\",\"epub\",\"docx\",\"rtf\"],"
      "\"aliases\":{\"html\":[\"html\",\"xhtml\",\"htm\"],\"mobi\":[\"mobi\",\"prc\",\"azw\"],\"kf8\":[\"kf8\",\"azw3\"]}},"
      "\"preserve\":{\"description\":\"Structure and resource preserving package export.\","
      "\"inputs\":[\"epub\",\"html\",\"xhtml\"],\"outputs\":[\"epub\",\"html\",\"xhtml\"],"
      "\"combinations\":[[\"epub\",\"epub\"],[\"epub\",\"html\"],[\"html\",\"epub\"],[\"html\",\"html\"],[\"xhtml\",\"epub\"],[\"xhtml\",\"html\"]],"
      "\"html_output\":\"single ZIP resource bundle; use the reported entry_path after extraction\"}},"
      "\"unsupported\":{\"targets\":[\"mobi\",\"kf8\",\"azw3\",\"pdf\",\"cbz\",\"audio\"],"
      "\"inputs_for_preserve\":[\"txt\",\"fb2\",\"docx\",\"rtf\",\"mobi\",\"kf8\",\"pdf\",\"cbz\"],"
      "\"features\":[\"ocr\",\"drm\",\"audio transcription\",\"full Word/PDF layout\",\"legacy UI database migration\",\"MOBI/KF8 write-back\"]},"
      "\"limitations\":{\"text\":[\"images/tables/css/fonts/links/annotations are not preserved\",\"chapter structure is flattened\",\"XML 1.0 forbidden scalars are rejected\"],"
      "\"preserve\":[\"render fidelity is declared separately from resource copying\",\"external/unsafe links are not fetched\",\"metadata beyond title is regenerated or dropped\"]},"
      "\"exit_codes\":{\"0\":\"all requested items converted and verified\",\"2\":\"usage or invocation error\","
      "\"3\":\"one or more items rejected, failed, cancelled or unfinished\",\"4\":\"report publication failed\"}}");
}
