/* Reuse the reviewed report/SDK helpers from the copied G08 consumer. Every
   production include and linked target still comes from the installed prefix. */
#define main original_composition_main
#include "composition_probe.cpp"
#undef main
#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#include <reader_annotation_export.h>
#include <reader_thumbnails.h>
#include <reader_local_downloads.h>

int main(int argc, char **argv) {
  if (argc != 4) return 2;
  try {
    const fs::path fixtures = fs::u8path(argv[1]), work = fs::u8path(argv[2]);
    require_directory(work);
    require_directory(work / "cache");
    require_directory(work / "local");
    const std::string source = (fixtures / "sample.txt").u8string();
    const std::string original = read_file(source);
    char sha[65]{};
    rth_sha256_hex(original.data(), original.size(), sha);
    const std::string key = std::string("txt:") + sha;
    store_side side;
    side.name = "g1";
    side.library_path = (work / "sdk.sqlite").u8string();
    side.product_path = (work / "product.sqlite").u8string();
    open_side(side);
    exr_sideload_result imported{};
    imported.struct_size = sizeof imported;
    SDK(exr_sideload_import_file(side.library, EXR_TXT, source.c_str(), "G1", nullptr, &imported, &sdk_error));
    check(imported.created == 1 && imported.book_id > 0, "sideload commits the chain original");
    reader_book_command book{};
    book.operation = READER_COMMAND_PUT; book.book_key = key.c_str(); book.format = "txt";
    book.source_sha256 = sha; book.source_bytes = original.size();
    book.title = "G1 composed"; book.author = "integration"; book.sort_title = "g1 composed";
    reader_command_context bc{side.revisions, nullptr, nullptr, 0};
    reader_command_result br{}; reader_command_error be{};
    check(reader_command_apply_book(&bc, &book, &br, &be) == READER_COMMAND_OK && br.created,
          "typed book command commits the chain metadata", be.message);
    reader_catalog_book mapping{};
    mapping.format = "txt"; mapping.sha256 = sha; mapping.source_bytes = original.size();
    mapping.title = book.title; mapping.author = book.author; mapping.sort_title = book.sort_title;
    mapping.sdk_book_id = imported.book_id; mapping.location_kind = "reflow";
    reader_catalog_error ce{};
    check(reader_catalog_attach(side.catalog, &mapping, &ce) == 0,
          "verified original attaches to the same product provider", ce.message);
    exr_document *doc = nullptr;
    SDK(exr_library_document(side.library, imported.book_id, &doc, &sdk_error));
    const std::string query = "\xE5\xBC\x95\xE6\x93\x8E\xE6\x8E\x8C\xE6\x8E\xA7";
    reader_search_options so{}; so.struct_size = sizeof so; so.source_key = key.c_str();
    reader_search *search = nullptr; reader_search_error se{};
    check(reader_search_open_reflow(doc, query.data(), query.size(), &so, &search, &se) == READER_SEARCH_OK,
          "search opens on the chain original", se.message);
    reader_search_result hits{};
    check(reader_search_next(search, 1, &hits, &se) == READER_SEARCH_OK && hits.count == 1,
          "search supplies one genuine SDK range", se.message);
    if (hits.count != 1) return 2;
    reader_rs_capture capture{}; capture.mode = READER_RS_REFLOW_GLOBAL; capture.anchor = &hits.hits[0].anchor;
    const std::string revision = new_revision_id();
    reader_rc_context rc{side.revisions, revision.c_str(), nullptr, 0, "exreader-sdk-3.40.0"};
    reader_rc_command command{};
    command.kind = READER_RC_HIGHLIGHT; command.operation = READER_RC_PUT;
    command.book_key = key.c_str(); command.capture = &capture; command.text = "shared product note";
    reader_rc_result rr{}; reader_rc_error re{};
    check(reader_rc_apply(&rc, &command, &rr, &re) == READER_RC_OK && rr.created,
          "reading command commits the search capture", re.message);
    const std::string annotation = rr.annotation_id;
    reader_rc_result retry{};
    check(reader_rc_apply(&rc, &command, &retry, &re) == READER_RC_OK && !retry.created &&
          annotation == retry.annotation_id, "lost-response retry creates no second annotation", re.message);
    reader_search_result_free(&hits);
    reader_search_close(&search, &se);
    exr_document_free(doc); doc = nullptr;

    reader_av_view *view = nullptr; reader_av_error ve{};
    check(reader_av_open(side.revisions, key.c_str(), nullptr, &view, &ve) == READER_AV_OK,
          "annotation view opens over reading-command history", ve.message);
    reader_av_cursor cursor{}; reader_av_page page{};
    check(reader_av_cursor_start(view, 1, &cursor, &ve) == READER_AV_OK &&
          reader_av_page_get(view, &cursor, 32, &page, &ve) == READER_AV_OK && page.count == 1,
          "annotation view returns exactly the committed note", ve.message);
    if (page.count != 1) return 2;
    check(page.items[0].kind == READER_AV_KIND_NOTE && annotation == page.items[0].annotation_id &&
          page.items[0].exact && query == page.items[0].exact && page.items[0].note_text &&
          std::string(page.items[0].note_text) == "shared product note" &&
          page.items[0].resolution == READER_AV_RESOLUTION_NOT_ATTEMPTED,
          "list snapshot preserves note selector without inventing resolution");
    reader_av_close(&view, &ve);
    // The page owns its values after the view closes.
    check(page.items[0].exact && query == page.items[0].exact, "snapshot survives view close");
    reader_av_page_free(&page);
    const std::string jsonl = (work / "before.jsonl").u8string(), md = (work / "before.md").u8string();
    reader_annotation_export_options eo{}; eo.struct_size = sizeof eo;
    eo.revisions = side.revisions; eo.book_key = key.c_str(); eo.book_title = book.title;
    eo.jsonl_path = jsonl.c_str(); eo.markdown_path = md.c_str();
    reader_annotation_export_stats es{}; reader_annotation_export_error ee{};
    check(reader_annotation_export_run(&eo, &es, &ee) == READER_ANNOTATION_EXPORT_OK &&
          es.annotations == 1 && es.current == 1 && es.jsonl_published && es.markdown_published,
          "export reads the same command and view history", ee.message);
    const std::string before = read_file(jsonl);

    // Preview is cached from a separate, real SDK PDF reader in this process.
    const std::string pdf = (fixtures / "pdf-public-text.pdf").u8string();
    exr_sideload_result pi{}; pi.struct_size = sizeof pi;
    SDK(exr_sideload_import_file(side.library, EXR_PDF, pdf.c_str(), "preview", nullptr, &pi, &sdk_error));
    exr_fixed_document *fixed = nullptr;
    SDK(exr_library_fixed(side.library, pi.book_id, nullptr, &fixed, &sdk_error));
    rth_book pb{}; pb.format = EXR_PDF; const std::string pdf_bytes = read_file(pdf);
    rth_sha256_hex(pdf_bytes.data(), pdf_bytes.size(), pb.sha256);
    rth_cache *cache = nullptr; rth_error te{}; rth_limits limits = rth_limits_defaults();
    const std::string cache_dir = (work / "cache").u8string();
    check(rth_cache_open(cache_dir.c_str(), &limits, &cache, &te) == RTH_OK,
          "thumbnail cache opens beside the product modules", te.message);
    rth_request request = rth_request_defaults(); request.width = 64; request.height = 64;
    rth_thumbnail thumb{}, cached{};
    check(rth_preview_from_fixed(cache, fixed, &pb, &request, nullptr, &thumb, &te) == RTH_OK &&
          thumb.pixels && thumb.width <= 64 && thumb.height <= 64,
          "thumbnail renders an actual SDK fixed page", te.message);
    check(rth_cache_find(cache, &pb, RTH_ORIGIN_FIRST_PAGE_PREVIEW, &request, &cached, &br.applied, &te) == RTH_OK &&
          br.applied && cached.from_cache && thumb.pixels && cached.pixels &&
          thumb.width == cached.width && thumb.height == cached.height &&
          std::memcmp(thumb.pixels, cached.pixels, size_t(thumb.stride) * thumb.height) == 0,
          "cache returns exactly the rendered preview bytes", te.message);
    rth_thumbnail_free(&thumb); rth_thumbnail_free(&cached); rth_cache_close(cache); exr_fixed_free(fixed);

    const std::string local_dir = (work / "local").u8string();
    reader_ld_options lo{}; reader_ld_options_init(&lo);
    lo.library = side.library; lo.catalog = side.catalog; lo.state_dir = local_dir.c_str();
    reader_ld_result lr{}; reader_ld_result_init(&lr); reader_ld_error le{};
    check(reader_ld_remove(&lo, key.c_str(), &lr, &le) == READER_LD_OK && lr.outcome == READER_LD_OUTCOME_REMOVED,
          "local removal removes only the original and mapping", le.message);
    check(reader_annotation_export_run(&eo, &es, &ee) == READER_ANNOTATION_EXPORT_OK &&
          read_file(jsonl) == before, "removal preserves annotation history and export bytes", ee.message);
    reader_ld_result_init(&lr);
    check(reader_ld_reimport(&lo, key.c_str(), source.c_str(), &lr, &le) == READER_LD_OK &&
          lr.outcome == READER_LD_OUTCOME_ATTACHED, "same immutable original reimports after removal", le.message);
    const int64_t restored_id = lr.sdk_book_id;
    close_side(side); open_side(side);
    SDK(exr_library_document(side.library, restored_id, &doc, &sdk_error));
    char *wire = nullptr; size_t wire_bytes = 0; reader_revision_info wi{};
    reader_revision_selection selected{}; reader_revision_error we{};
    const std::string entity = key + ":" + annotation;
    check(reader_revision_selected(side.revisions, "annotation", entity.c_str(), &wire, &wire_bytes,
          &wi, &selected, &we) == READER_REV_OK && selected.kind == READER_SELECTION_SAFE,
          "reopened product selects the same retained annotation", we.message);
    reader_rs_record record{}; reader_rs_error rse{}; exr_anchor_match match{};
    check(wire && reader_rs_decode(side.revisions, wire, wire_bytes, &record, &rse) == READER_RS_OK &&
          reader_rs_resolve_reflow(doc, &record, nullptr, &match, &rse) == READER_RS_OK && match.state == EXR_ANCHOR_FOUND,
          "fresh SDK resolves the preserved selector after reimport", rse.message);
    reader_rs_record_free(&record); reader_revision_bytes_free(wire);
    exr_document_free(doc); close_side(side);
    const std::string report = object().num("failures", failures).num("check_count", checks.size())
        .str("book_key", key).str("resolved_state", match.state == EXR_ANCHOR_FOUND ? "FOUND" : "MISSING")
        .set("checks", array(checks)).dump();
    write_file(argv[3], report + "\n");
    std::printf("g1 checks=%zu failures=%zu\n", checks.size(), failures);
    return failures ? 1 : 0;
  } catch (const std::exception &e) {
    std::fprintf(stderr, "%s\n", e.what()); return 2;
  }
}
