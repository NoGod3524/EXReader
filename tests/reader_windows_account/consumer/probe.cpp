/* SPDX-License-Identifier: MIT */
/* Installed native consumer for the G01 Windows account round trip.

   Installed public APIs only: frozen SDK 3.40.0 (document, pager, fixed-page and
   source calls), the product revisions module, the schema1 product catalog and
   the reading-state adapter (reader_rs_encode_v2 / reader_rs_decode /
   reader_rs_resolve_*). The eighteen cases are the unchanged
   tests/reader_reading_v2 definition over four real originals: seventeen FOUND
   and one planted ambiguity. No selector is guessed, no SDK table is read and no
   retained byte is rewritten: every selector comes from a public capture call on
   the real document and every receiver state from the public resolve call.

   Subcommands (fixed positional arguments):
     capture  <sdk-library> <product-db> <font> <scratch-library> <book-key> <kind> <case> <wire-out>
     resolve  <sdk-library> <product-db> <font> <scratch-library> <revision-id>
     notes    <sdk-library> <product-db> <book-key>
     identity
*/
#define main legacy_reading_state_probe_main
#include "../../reader_reading_state/consumer/probe.cpp"
#undef main
#include <cstring>
#include <filesystem>

namespace {
using std::string;

struct host_side {
  side h;    /* the host's own SDK library, product revisions and catalog */
  side g;    /* whole-book reflow EPUB scratch library; never a host file */
  bool g_open = false;
};

string aformat(const string &book_key) { return book_key.substr(0, book_key.find(':')); }

int64_t sdk_book(host_side &s, const string &book_key) {
  keys["book"] = book_key;
  return catalog_id(s.h, "book");
}

/* Exact original bytes through the public SDK source, in one bounded copy. */
string original_bytes(exr_library *library, int64_t id) {
  exr_source source{};
  SDK(exr_library_source(library, id, &source, &e_));
  string bytes((size_t)source.size, '\0');
  uint64_t done = 0;
  while (done < source.size) {
    size_t got = source.read_at(source.context, done, &bytes[(size_t)done], bytes.size() - (size_t)done);
    if (!got) { source.release(source.context); fatal("short original read"); }
    done += got;
  }
  source.release(source.context);
  return bytes;
}

/* Whole-book reflow EPUB exists only as a memory import, and the host stores EPUB
   originals bounded (chapter-local). This scratch library is built from the
   host's own verified original bytes and is never opened by any product. */
int64_t reflow_epub(host_side &s, const string &book_key) {
  if (!s.g_open) {
    exr_error error{};
    if (exr_library_open(s.g.lib_path.c_str(), &s.g.lib, &error) != EXR_OK) fatal("scratch library open");
    s.g_open = true;
  }
  string bytes = original_bytes(s.h.lib, sdk_book(s, book_key));
  int64_t id = 0;
  int created = 0;
  exr_error error{};
  if (exr_library_import_unique(s.g.lib, EXR_EPUB, bytes.data(), bytes.size(), "reading-v2-global",
                                &id, &created, &error) != EXR_OK) fatal("scratch EPUB import");
  return id;
}

/* Only the scratch library is opened there; its revisions/catalog were never used. */
void close_scratch(host_side &s) {
  if (!s.g_open) return;
  exr_library_close(s.g.lib);
  s.g.lib = nullptr;
  s.g_open = false;
}

void open_host(host_side &s, const string &sdk, const string &product, const string &scratch) {
  s.h.name = "host";
  s.h.lib_path = sdk;
  s.h.product_path = product;
  open_side(s.h);
  s.g.name = "scratch";
  s.g.lib_path = scratch;
}

std::vector<std::string> observed_heads(reader_revisions *store, const char *kind, const string &key) {
  std::vector<std::string> heads;
  reader_revision_state state{};
  reader_revision_error error{};
  if (reader_revision_heads(store, kind, key.c_str(),
        [](void *context, const reader_revision_head *head) {
          ((std::vector<std::string> *)context)->push_back(head->revision_id);
          return 0;
        }, &heads, &state, &error) != READER_REV_OK) fatal("heads");
  return heads;
}

struct case_state {
  reader_rs_capture capture{};
  size_t part = 0;
  string chapter, part_path;
  bool has_chapter = false;
  size_t start = 0, end = 0;
  const char *mode = "";
};

/* Encodes the live public capture with the public v2 codec, writes the exact wire
   bytes and records the identity of everything that produced them. */
void encode_write(host_side &s, const string &kind, const string &book_key, const string &name,
                  case_state &built, const string &wire_out, object &report) {
  const string aid = kind == "annotation" ? new_id() : "";
  const string entity = kind == "annotation" ? book_key + ":" + aid : book_key;
  auto heads = observed_heads(s.h.store, kind.c_str(), entity);
  std::vector<const char *> parents;
  std::vector<string> parent_list;
  for (const auto &head : heads) { parent_list.push_back(head); parents.push_back(parent_list.back().c_str()); }
  const string id = new_id();
  reader_rs_envelope envelope{};
  envelope.revision_id = id.c_str();
  envelope.operation = "put";
  envelope.entity_kind = kind.c_str();
  envelope.book_key = book_key.c_str();
  envelope.annotation_id = aid.empty() ? nullptr : aid.c_str();
  envelope.parents = parents.data();
  envelope.parent_count = parents.size();
  envelope.note_text = name.c_str();
  envelope.parser_version = parser_version.c_str();
  char *wire = nullptr;
  size_t bytes = 0;
  reader_rs_error error{};
  if (reader_rs_encode_v2(s.h.store, &envelope, &built.capture, built.part, &wire, &bytes, &error) != READER_RS_OK)
    fatal(name + " encode: " + std::string(error.message));
  std::ofstream output(std::filesystem::u8path(wire_out), std::ios::binary);
  output.write(wire, (std::streamsize)bytes);
  output.close();
  if (!output) fatal("wire write");
  report.set("classify", esc(gap_name(reader_rs_classify(&built.capture))));
  report.set("anchor_version", num(2));
  report.set("wire_bytes", num(bytes));
  reader_rs_free(wire);
  report.str("case", name)
        .str("mode", built.mode)
        .str("kind", kind)
        .str("book_key", book_key)
        .str("entity_key", entity)
        .str("revision_id", id)
        .str("operation", "put")
        .set("part", num(built.part))
        .set("start", num(built.start))
        .set("end", num(built.end))
        .set("has_chapter", boolean(built.has_chapter));
  if (built.has_chapter) report.str("chapter", built.chapter);
  if (!built.part_path.empty()) report.str("part_path", built.part_path);
  std::string parents_json = "[";
  for (size_t i = 0; i < parent_list.size(); i++) { if (i) parents_json += ","; parents_json += esc(parent_list[i]); }
  report.set("parents", parents_json + "]");
  if (!aid.empty()) report.str("annotation_id", aid);
}

/* The unchanged eighteen-case definition of tests/reader_reading_v2. */
void build_case(host_side &s, const string &book_key, const string &kind, const string &name,
                exr_font *font, const string &wire_out, object &report) {
  case_state built;
  if (name.rfind("txt-", 0) == 0) {
    exr_document *document = nullptr;
    SDK(exr_library_document(s.h.lib, sdk_book(s, book_key), &document, &e_));
    size_t size = 0;
    const char *text = exr_document_text(document, &size);
    string body(text, size);
    exr_anchor anchor{};
    if (name == "txt-progress-start") built.start = built.end = 0;
    else if (name == "txt-progress-multibyte") built.start = built.end = locate(body, "\xF0\x9F\x99\x82");
    else if (name == "txt-progress-end") built.start = built.end = size;
    else if (name == "txt-bookmark") built.start = built.end = locate(body, "Tail alpha");
    else if (name == "txt-highlight") { built.start = locate(body, "\xF0\x9F\x99\x82"); built.end = built.start + 4; }
    else if (name == "txt-ambiguous") { built.start = locate(body, "AMBIGUOUS TARGET", 1); built.end = built.start + 16; }
    else fatal("unknown txt case " + name);
    SDK(exr_anchor_create(document, built.start, built.end, &anchor, &e_));
    built.capture.mode = READER_RS_REFLOW_GLOBAL;
    built.capture.anchor = &anchor;
    built.mode = "reflow_global";
    report.str("capture_source", "exr_library_document + exr_anchor_create");
    report.set("document_bytes", num(size));
    encode_write(s, kind, book_key, name, built, wire_out, report);
    exr_anchor_free(&anchor);
    exr_document_free(document);
    return;
  }
  if (name.rfind("epub-global-", 0) == 0) {
    exr_document *document = nullptr;
    SDK(exr_library_document(s.g.lib, reflow_epub(s, book_key), &document, &e_));
    size_t size = 0;
    const char *text = exr_document_text(document, &size);
    string body(text, size);
    const char *marker = "\xE7\xAC\xAC\xE4\xBA\x8C\xE7\xAB\xA0\xE8\x8A\x82\xE7\x8B\xAC\xE6\x9C\x89\xE6\x96\x87\xE5\xAD\x97";
    size_t at = locate(body, marker);
    exr_anchor anchor{};
    built.start = at;
    built.end = name == "epub-global-highlight" ? at + strlen(marker) : at;
    SDK(exr_anchor_create(document, built.start, built.end, &anchor, &e_));
    if (!anchor.chapter || !anchor.chapter[0]) fatal("global EPUB capture lost its chapter scope");
    built.capture.mode = READER_RS_REFLOW_GLOBAL;
    built.capture.anchor = &anchor;
    built.mode = "reflow_global";
    built.chapter = anchor.chapter;
    built.has_chapter = true;
    report.str("capture_source", "exr_library_document + exr_anchor_create (whole-book reflow)");
    report.set("document_bytes", num(size));
    encode_write(s, kind, book_key, name, built, wire_out, report);
    exr_anchor_free(&anchor);
    exr_document_free(document);
    return;
  }
  if (name.rfind("epub-", 0) == 0) {
    exr_source source{};
    SDK(exr_library_source(s.h.lib, sdk_book(s, book_key), &source, &e_));
    exr_publication *publication = nullptr;
    exr_error open_error{};
    if (exr_publication_open_source(&source, &publication, &open_error) != EXR_OK) fatal("publication open");
    size_t count = 0;
    const exr_part *parts = exr_publication_parts(publication, &count);
    if (count < 3) fatal("fixture spine changed");
    built.part = name == "epub-bookmark-part-0" ? 0 : name == "epub-bookmark-part-2" ? 2 : 1;
    exr_layout_config config = exr_layout_config_defaults();
    exr_chapter_options options = exr_chapter_options_defaults();
    exr_pager *pager = nullptr;
    SDK(exr_publication_pager_create(publication, built.part, font, &config, &options, &pager, &e_));
    exr_anchor anchor{};
    SDK(exr_pager_anchor_create(pager, 0, 0, nullptr, &anchor, &e_));
    built.capture.mode = READER_RS_EPUB_CHAPTER;
    built.capture.anchor = &anchor;
    built.capture.part_path = parts[built.part].path;
    built.part_path = parts[built.part].path;
    built.mode = "epub_chapter";
    report.str("capture_source", "exr_publication_pager_create + exr_pager_anchor_create");
    report.set("spine_parts", num(count));
    report.str("part_path", parts[built.part].path);
    encode_write(s, kind, book_key, name, built, wire_out, report);
    exr_anchor_free(&anchor);
    exr_pager_free(pager);
    exr_publication_free(publication);
    return;
  }
  exr_fixed_open_options fix_options{};
  fix_options.struct_size = sizeof(fix_options);
  exr_fixed_document *document = nullptr;
  SDK(exr_library_fixed(s.h.lib, sdk_book(s, book_key), &fix_options, &document, &e_));
  size_t pages_count = 0;
  const exr_fixed_page *pages = exr_fixed_pages(document, &pages_count);
  size_t page = 0;
  if (name == "pdf-highlight" || name == "pdf-bookmark") page = 0;
  else if (name == "pdf-textless-bookmark") page = 2;
  else if (name == "pdf-progress" || name == "cbz-bookmark" || name == "cbz-progress") page = 1;
  else fatal("unknown fixed case " + name);
  exr_fixed_text *page_text = nullptr;
  SDK(exr_fixed_load_text(document, page, nullptr, &page_text, &e_));
  if (name == "pdf-highlight" || name == "pdf-bookmark") {
    size_t size = 0;
    const char *text = exr_fixed_text_string(page_text, &size);
    size_t at = locate(string(text, size), "Shared quote across pages.");
    built.start = at;
    built.end = name == "pdf-highlight" ? at + strlen("Shared quote across pages.") : at;
  }
  exr_fixed_anchor anchor{};
  SDK(exr_fixed_anchor_create(pages[page].id, page_text, built.start, built.end, &anchor, &e_));
  built.capture.mode = READER_RS_FIXED_PAGE;
  built.capture.fixed = &anchor;
  built.capture.page = page;
  built.mode = "fixed_page";
  report.str("capture_source", "exr_library_fixed + exr_fixed_anchor_create");
  report.set("pages", num(pages_count));
  report.str("page_id", pages[page].id);
  report.set("page", num(page));
  encode_write(s, kind, book_key, name, built, wire_out, report);
  exr_fixed_anchor_free(&anchor);
  exr_fixed_text_free(page_text);
  exr_fixed_free(document);
}

/* Public resolve only: retained bytes -> public decode -> public resolve. */
void resolve_one(host_side &s, const string &font_path, const string &revision_id) {
  char *wire = nullptr;
  size_t bytes = 0;
  reader_revision_info info{};
  reader_revision_error revision_error{};
  if (reader_revision_get(s.h.store, revision_id.c_str(), &wire, &bytes, &info, &revision_error) != READER_REV_OK)
    fatal("revision get: " + std::string(revision_error.message));
  reader_rs_record record{};
  reader_rs_error error{};
  if (reader_rs_decode(s.h.store, wire, bytes, &record, &error) != READER_RS_OK)
    fatal("decode: " + std::string(error.message));
  reader_revision_bytes_free(wire);
  object report;
  report.str("revision_id", revision_id)
        .str("wire_sha256", info.sha256)
        .set("wire_bytes", num(bytes))
        .set("decoded", "true")
        .set("anchor_version", num(record.anchor_version))
        .str("mode", record.mode == READER_RS_REFLOW_GLOBAL ? "reflow_global"
                  : record.mode == READER_RS_EPUB_CHAPTER ? "epub_chapter" : "fixed_page")
        .str("kind", record.entity_kind)
        .str("book_key", record.book_key)
        .set("record_start", num(record.start))
        .set("record_end", num(record.end))
        .set("part", num(record.part))
        .set("has_chapter", boolean(record.chapter != nullptr));
  if (record.part_path) report.str("part_path", record.part_path);
  if (record.chapter) report.str("chapter", record.chapter);
  exr_anchor_match match{};
  reader_rs_status status = READER_RS_ARGUMENT;
  bool attempted = false;
  if (record.mode == READER_RS_REFLOW_GLOBAL) {
    exr_document *document = nullptr;
    if (aformat(record.book_key) == "epub")
      SDK(exr_library_document(s.g.lib, reflow_epub(s, record.book_key), &document, &e_));
    else
      SDK(exr_library_document(s.h.lib, sdk_book(s, record.book_key), &document, &e_));
    attempted = true;
    status = reader_rs_resolve_reflow(document, &record, nullptr, &match, &error);
    report.str("resolve_source", aformat(record.book_key) == "epub"
               ? "exr_library_document(whole-book reflow) + reader_rs_resolve_reflow"
               : "exr_library_document + reader_rs_resolve_reflow");
    exr_document_free(document);
  } else if (record.mode == READER_RS_EPUB_CHAPTER) {
    exr_source source{};
    SDK(exr_library_source(s.h.lib, sdk_book(s, record.book_key), &source, &e_));
    exr_publication *publication = nullptr;
    exr_error open_error{};
    if (exr_publication_open_source(&source, &publication, &open_error) != EXR_OK) fatal("publication open");
    size_t part = 0;
    reader_rs_error route{};
    status = reader_rs_epub_record_part(publication, &record, &part, &route);
    if (status == READER_RS_OK) {
      exr_font *font = nullptr;
      SDK(exr_font_open(font_path.c_str(), &font, &e_));
      exr_layout_config config = exr_layout_config_defaults();
      exr_chapter_options options = exr_chapter_options_defaults();
      exr_pager *pager = nullptr;
      SDK(exr_publication_pager_create(publication, part, font, &config, &options, &pager, &e_));
      attempted = true;
      status = reader_rs_resolve_epub(publication, pager, part, &record, nullptr, &match, &error);
      report.set("routed_part", num(part));
      exr_pager_free(pager);
      exr_font_free(font);
    }
    report.str("resolve_source", "reader_rs_epub_record_part + reader_rs_resolve_epub");
    exr_publication_free(publication);
  } else {
    exr_fixed_open_options options{};
    options.struct_size = sizeof(options);
    exr_fixed_document *document = nullptr;
    SDK(exr_library_fixed(s.h.lib, sdk_book(s, record.book_key), &options, &document, &e_));
    size_t page = 0;
    attempted = true;
    status = reader_rs_resolve_fixed(document, &record, nullptr, &page, &match, &error);
    report.set("resolved_page", num(page));
    report.str("resolve_source", "reader_rs_resolve_fixed");
    exr_fixed_free(document);
  }
  report.str("status", rs_name(status))
        .str("state", attempted ? state_name(match.state) : "NOT_RESOLVED")
        .set("match_start", match.state == EXR_ANCHOR_FOUND ? num(match.start) : string("null"))
        .set("match_end", match.state == EXR_ANCHOR_FOUND ? num(match.end) : string("null"));
  reader_rs_record_free(&record);
  std::printf("%s\n", report.dump().c_str());
}

/* Product-owned annotations must leave the SDK note tables untouched. */
void notes_one(host_side &s, const string &book_key) {
  const int64_t id = sdk_book(s, book_key);
  const string format = aformat(book_key);
  size_t count = 0;
  const char *api = "none";
  if (format == "epub") { count = count_epub(s.h, id); api = "exr_library_epub_notes"; }
  else if (format == "pdf" || format == "cbz") { count = count_fixed(s.h, id); api = "exr_library_fixed_notes"; }
  else { count = count_notes(s.h, id); api = "exr_library_notes"; }
  object report;
  report.str("book_key", book_key).set("sdk_notes", num(count)).str("api", api);
  std::printf("%s\n", report.dump().c_str());
}
}  /* namespace */

int main(int argc, char **argv) {
  std::vector<string> args;
  for (int i = 0; i < argc; i++) args.emplace_back(argv[i]);
  if (args.size() < 2) fatal("usage: probe <capture|resolve|notes|identity> ...");
  parser_version = string("exreader-sdk-") + exr_version();
  host_side s;
  if (args[1] == "identity") {
    if (args.size() != 2) fatal("identity takes no arguments");
    object report;
    report.str("reading_state_version", READER_READING_STATE_VERSION)
          .str("sdk_version", exr_version())
          .str("parser_version", parser_version)
          .str("consumer", "reader-windows-account reading-capture-probe");
    std::printf("%s\n", report.dump().c_str());
    return 0;
  }
  if (args[1] == "notes") {
    if (args.size() != 5) fatal("notes needs sdk, product and book key");
    open_host(s, args[2], args[3], args[3] + "-unused-scratch");
    notes_one(s, args[4]);
    close_side(s.h);
    return 0;
  }
  if (args[1] == "capture") {
    if (args.size() != 10) fatal("capture needs sdk, product, font, scratch, book key, kind, case and wire path");
    open_host(s, args[2], args[3], args[5]);
    exr_font *font = nullptr;
    SDK(exr_font_open(args[4].c_str(), &font, &e_));
    object report;
    build_case(s, args[6], args[7], args[8], font, args[9], report);
    std::printf("%s\n", report.dump().c_str());
    exr_font_free(font);
    close_scratch(s);
    close_side(s.h);
    return 0;
  }
  if (args[1] == "resolve") {
    if (args.size() != 7) fatal("resolve needs sdk, product, font, scratch and revision id");
    open_host(s, args[2], args[3], args[5]);
    resolve_one(s, args[4], args[6]);
    close_scratch(s);
    close_side(s.h);
    return 0;
  }
  fatal("unknown subcommand " + args[1]);
}
