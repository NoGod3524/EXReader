// SPDX-License-Identifier: MIT
// Read-only per-book annotation list snapshots over the unchanged product revision
// history. Only reader_revision_annotations_page and reader_rs_decode are used.
#include <reader_annotation_view.h>
#include <reader_projection.h>
#include <reader_reading_state.h>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <initializer_list>
#include <memory>
#include <new>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr size_t kRowOverhead = 512; // accounted per row on top of its retained wire bytes

struct failure {
  reader_av_status code; int revision_code, decode_code; std::string message;
};
[[noreturn]] void fail(reader_av_status code, const char *message, int revision_code = 0, int decode_code = 0) {
  throw failure{code, revision_code, decode_code, message};
}
void put_error(reader_av_error *error, reader_av_status code, int revision_code, int decode_code, const std::string &message) {
  if (!error) return;
  error->code = code; error->revision_code = revision_code; error->decode_code = decode_code;
  const size_t n = message.size() < sizeof(error->message) - 1 ? message.size() : sizeof(error->message) - 1;
  std::memcpy(error->message, message.data(), n);
  error->message[n] = 0;
}
void clear_error(reader_av_error *error) { put_error(error, READER_AV_OK, 0, 0, ""); }

template <class F> reader_av_status call(reader_av_error *error, F &&body) {
  clear_error(error);
  try { body(); return READER_AV_OK; }
  catch (const failure &f) { put_error(error, f.code, f.revision_code, f.decode_code, f.message); return f.code; }
  catch (const std::bad_alloc &) { put_error(error, READER_AV_MEMORY, 0, 0, "Out of memory"); return READER_AV_MEMORY; }
  catch (const std::exception &e) { put_error(error, READER_AV_CONTRACT, 0, 0, e.what()); return READER_AV_CONTRACT; }
}

bool valid_id(const char *s) {
  if (!s || std::strlen(s) != 32) return false;
  for (size_t i = 0; i < 32; i++) if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return false;
  return true;
}
uint64_t bind_book(const std::string &book) {
  uint64_t h = 14695981039346656037ull;
  const std::string text = "EXRAV1:" + book;
  for (unsigned char c : text) { h ^= c; h *= 1099511628211ull; }
  return h;
}
template <size_t N> void copy_field(char (&out)[N], const char *in) {
  size_t n = in ? std::strlen(in) : 0;
  if (n >= N) fail(READER_AV_CONTRACT, "Store field exceeds its fixed buffer");
  std::memcpy(out, in, n); out[n] = 0;
}
}

struct reader_av_view {
  const bool raw_api;explicit reader_av_view(bool raw=false):raw_api(raw){}
  reader_revisions *store = nullptr;
  std::thread::id owner = std::this_thread::get_id();
  bool active = false;
  std::string book;
  reader_av_cancel_fn cancel = nullptr;
  void *cancel_context = nullptr;
  size_t budget = READER_AV_PAGE_BYTES_DEFAULT;
  uint64_t binding = 0;
};

namespace {
struct guard {
  reader_av_view *view;
  explicit guard(reader_av_view *v) : view(v) {
    if (!v) fail(READER_AV_ARGUMENT, "Missing view");
    if (v->owner != std::this_thread::get_id()) fail(READER_AV_OWNER, "The view requires its creating thread");
    if (v->active) fail(READER_AV_BUSY, "The view is inside one of its calls");
    v->active = true;
  }
  ~guard() { view->active = false; }
};

struct run {
  reader_av_view *view; uint64_t polls = 0; bool cancelled = false;
  bool poll() {
    if (cancelled) return true;
    polls++;
    if (view->cancel && view->cancel(view->cancel_context)) cancelled = true;
    return cancelled;
  }
  void check() { if (poll()) fail(READER_AV_CANCELLED, "Cancelled by the caller"); }
};

struct captured {
  std::string id; reader_revision_selection selection{}; reader_revision_info info{}; std::string wire;
};
struct collect {
  run *r = nullptr; const std::string *book = nullptr; int direction = 1;
  bool have_last = false; std::string last;
  std::vector<captured> rows; size_t seen = 0, bytes = 0, budget = 0;
  bool bad = false, stopped = false, too_big = false, oom = false;
};
int visit(void *context, const reader_revision_annotation_row *row) {
  collect &c = *static_cast<collect *>(context);
  try {
    if (c.r->poll()) return 1;
    c.seen++;
    if (!row || !valid_id(row->annotation_id)) { c.bad = true; return 1; }
    const std::string id = row->annotation_id;
    if (c.have_last && (c.direction == 1 ? !(id > c.last) : !(id < c.last))) { c.bad = true; return 1; }
    const bool safe = row->selection.kind == READER_SELECTION_SAFE;
    if (safe && (!row->wire || std::strcmp(row->info.book_key, c.book->c_str()) != 0 ||
                 row->info.bytes == 0 || row->info.bytes > READER_AV_ITEM_BYTES_MAX)) { c.bad = true; return 1; }
    const size_t cost = kRowOverhead + (safe ? row->info.bytes : 0);
    if (cost > c.budget) { c.too_big = true; return 1; }
    if (c.bytes + cost > c.budget) { c.stopped = true; c.seen--; return 1; }
    captured item; item.id = id; item.selection = row->selection;
    if (safe) { item.info = row->info; item.wire.assign(row->wire, row->info.bytes); }
    c.rows.push_back(std::move(item)); c.bytes += cost; c.have_last = true; c.last = id;
    return 0;
  } catch (...) { c.oom = true; return 1; }
}

struct text { bool has = false; std::string s; };
struct built {
  reader_av_item item{};
  text part_path, page_id, exact, prefix, suffix, chapter, note;
};
struct record_guard {
  reader_rs_record record{}; bool owned = false;
  ~record_guard() { if (owned) reader_rs_record_free(&record); }
};
void take(text &out, const char *s, size_t n) { if (s) { out.has = true; out.s.assign(s, n); } }

reader_av_state state_of(reader_selection_kind kind) {
  switch (kind) {
    case READER_SELECTION_SAFE: return READER_AV_STATE_SAFE;
    case READER_SELECTION_CONCURRENT: return READER_AV_STATE_CONCURRENT;
    case READER_SELECTION_PENDING_PARENTS: return READER_AV_STATE_PENDING_PARENTS;
    case READER_SELECTION_BLOCKED_RESTORE: return READER_AV_STATE_BLOCKED_RESTORE;
    default: return READER_AV_STATE_MISSING;
  }
}

void build(reader_revisions *store, const std::string &book, const captured &row, built &out, run &r) {
  reader_av_item &it = out.item;
  copy_field(it.annotation_id, row.id.c_str());
  it.state = state_of(row.selection.kind);
  it.kind = READER_AV_KIND_UNAVAILABLE;
  const reader_revision_state &g = row.selection.graph;
  it.revisions = g.revisions; it.heads = g.heads; it.missing_parents = g.missing_parents; it.foreign_parents = g.foreign_parents;
  it.deleted = g.deleted ? 1 : 0; it.requires_restore = g.requires_restore ? 1 : 0;
  if (it.state != READER_AV_STATE_SAFE) return;
  r.check();
  record_guard rg; reader_rs_error e{};
    reader_rs_status st;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(r.view->raw_api)st=reader_rs_decode_raw_v3(store,row.wire.data(),row.wire.size(),&rg.record,&e);else
#endif
  st=reader_rs_decode(store,row.wire.data(),row.wire.size(),&rg.record,&e);
  if (st != READER_RS_OK) fail(READER_AV_DECODE, e.message, e.revision_code, (int)st);
  rg.owned = true;
  r.check();
  const reader_rs_record &rec = rg.record;
  const bool tombstone = std::strcmp(rec.operation, "delete") == 0;
  if (std::strcmp(rec.entity_kind, "annotation") != 0 || std::strcmp(rec.book_key, book.c_str()) != 0 ||
      row.id != rec.annotation_id || std::strcmp(rec.operation, row.info.operation) != 0 ||
      (tombstone && rec.has_location) || (!tombstone && !rec.has_location))
    fail(READER_AV_CONTRACT, "Decoded record differs from the store row identity");
  copy_field(it.revision_id, row.info.revision_id); copy_field(it.operation, row.info.operation); copy_field(it.sha256, row.info.sha256);
  it.wire_bytes = row.info.bytes;
  it.mode = rec.mode == READER_RS_REFLOW_GLOBAL ? READER_AV_MODE_REFLOW : rec.mode == READER_RS_EPUB_CHAPTER ? READER_AV_MODE_EPUB : READER_AV_MODE_FIXED;
  if (tombstone) { it.kind = READER_AV_KIND_TOMBSTONE; return; }
  it.has_location = 1; it.anchor_version = rec.anchor_version; it.legacy_anchor = rec.anchor_version < 2 ? 1 : 0;
  copy_field(it.parser_version, rec.parser_version);
  it.has_part = (it.mode == READER_AV_MODE_EPUB && rec.anchor_version >= 2) ? 1 : 0; it.part = it.has_part ? rec.part : 0;
  it.has_page = it.mode == READER_AV_MODE_FIXED ? 1 : 0; it.page = it.has_page ? rec.page : 0;
  it.start = rec.start; it.end = rec.end;
  if ((!r.view->raw_api&&(!rec.exact||!rec.prefix||!rec.suffix))||!rec.note_text) fail(READER_AV_CONTRACT, "Decoded annotation lacks a selector or text");
  take(out.part_path, rec.part_path, rec.part_path ? std::strlen(rec.part_path) : 0);
  take(out.page_id, rec.page_id, rec.page_id ? std::strlen(rec.page_id) : 0);
  take(out.exact, rec.exact, rec.exact_size); take(out.prefix, rec.prefix, rec.prefix_size); take(out.suffix, rec.suffix, rec.suffix_size);
  take(out.chapter, rec.chapter, rec.chapter ? std::strlen(rec.chapter) : 0);
  take(out.note, rec.note_text, std::strlen(rec.note_text));
  it.exact_size = rec.exact_size; it.prefix_size = rec.prefix_size; it.suffix_size = rec.suffix_size; it.note_size = out.note.s.size();
  const bool point = rec.exact_size == 0 && rec.start == rec.end;
  it.kind = point ? READER_AV_KIND_BOOKMARK : it.note_size ? READER_AV_KIND_NOTE : READER_AV_KIND_HIGHLIGHT;
  it.content_available = rec.exact ? 1 : 0;
}

void make_cursor(reader_av_cursor &c, const reader_av_cursor &base, int direction, const char *after, bool complete) {
  c = base; c.direction = direction; c.complete = complete ? 1 : 0;
  std::memset(c.after_id, 0, sizeof(c.after_id));
  c.has_after = after ? 1 : 0;
  if (after) std::memcpy(c.after_id, after, 32);
}
}

static reader_av_status open_view(bool raw_api,reader_revisions *store, const char *book_key, const reader_av_options *options,
    reader_av_view **out, reader_av_error *error) {
  if (out) *out = nullptr;
  return call(error, [&] {
    if (!store || !book_key || !out) fail(READER_AV_ARGUMENT, "Missing store, book key or output");
    const size_t n = std::strlen(book_key);
    if (n < 66 || n > 72 || !std::strchr(book_key, ':')) fail(READER_AV_ARGUMENT, "Book key must be a global format:sha256 identity");
    size_t budget = READER_AV_PAGE_BYTES_DEFAULT;
    reader_av_cancel_fn cancel = nullptr; void *context = nullptr;
    if (options) {
      if (options->struct_size != sizeof(reader_av_options)) fail(READER_AV_ARGUMENT, "Unexpected options size");
      cancel = options->cancel; context = options->cancel_context;
      if (options->max_page_bytes) {
        if (options->max_page_bytes < READER_AV_PAGE_BYTES_MIN || options->max_page_bytes > READER_AV_PAGE_BYTES_MAX)
          fail(READER_AV_ARGUMENT, "Page budget is outside the allowed range");
        budget = options->max_page_bytes;
      }
    }
    std::unique_ptr<reader_av_view> view(new reader_av_view(raw_api));
    view->store = store; view->book = book_key; view->cancel = cancel; view->cancel_context = context;
    view->budget = budget; view->binding = bind_book(view->book);
    *out = view.release();
  });
}

extern "C" reader_av_status reader_av_cursor_start(const reader_av_view *view, int direction, reader_av_cursor *cursor, reader_av_error *error) {
  if (cursor) std::memset(cursor, 0, sizeof(*cursor));
  return call(error, [&] {
    if (!view || !cursor || (direction != 1 && direction != -1)) fail(READER_AV_ARGUMENT, "Missing view or cursor, or direction is not +/-1");
    cursor->version = 1; cursor->direction = direction; cursor->binding = view->binding;
    std::memcpy(cursor->book_key, view->book.c_str(), view->book.size());
  });
}

static reader_av_status page_get(bool raw_api,reader_av_view *view, const reader_av_cursor *from, size_t limit,
    reader_av_page *page, reader_av_error *error) {
  if (page) std::memset(page, 0, sizeof(*page));
  return call(error, [&] {
    guard owner(view);
    if(view->raw_api!=raw_api)fail(READER_AV_ARGUMENT,"Use the explicit view API matching this capability" );
    if (!from || !page || limit < 1 || limit > READER_AV_BATCH_MAX) fail(READER_AV_ARGUMENT, "Page requires a cursor, output and limit 1..100");
    if (from->version != 1 || (from->direction != 1 && from->direction != -1) || from->binding != view->binding ||
        std::strncmp(from->book_key, view->book.c_str(), sizeof(from->book_key)) != 0 || from->has_after > 1 || from->complete > 1 ||
        (from->has_after ? !valid_id(from->after_id) : from->after_id[0] != 0))
      fail(READER_AV_CURSOR, "Cursor belongs to another view, book or direction, or is malformed");
    const int direction = from->direction;
    run r{view};
    r.check();
    std::vector<captured> rows; bool complete = false, stopped = false; size_t seen = 0, wire_bytes = 0;
    if (from->complete) complete = true;
    else {
      r.check();
      collect c; c.r = &r; c.book = &view->book; c.direction = direction; c.budget = view->budget;
      if (from->has_after) { c.have_last = true; c.last = from->after_id; }
      reader_revision_error rerr{};
            auto enumerate=reader_revision_annotations_page;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
      if(raw_api)enumerate=reader_revision_annotations_page_raw_v3;
#endif
      reader_revision_status st = enumerate(view->store, view->book.c_str(), from->has_after ? from->after_id : nullptr,
        direction, limit, visit, &c, &rerr);
      if (r.cancelled) fail(READER_AV_CANCELLED, "Cancelled by the caller");
      if (st != READER_REV_OK) fail(READER_AV_REVISION, rerr.message, (int)st);
      if (c.oom) throw std::bad_alloc();
      if (c.too_big) fail(READER_AV_LIMIT, "A single row cannot fit the page budget");
      if (c.bad) fail(READER_AV_CONTRACT, "Store page violated order, identity or size rules");
      stopped = c.stopped; seen = c.seen; wire_bytes = c.bytes;
      complete = !stopped && seen < limit;
      rows = std::move(c.rows);
    }
    std::vector<built> items(rows.size());
    for (size_t i = 0; i < rows.size(); i++) build(view->store, view->book, rows[i], items[i], r);
    size_t strings = 0;
    for (const built &b : items)
      for (const text *t : {&b.part_path, &b.page_id, &b.exact, &b.prefix, &b.suffix, &b.chapter, &b.note}) if (t->has) strings += t->s.size() + 1;
    const size_t total = sizeof(reader_av_item) * items.size() + strings;
    if (total > view->budget) fail(READER_AV_LIMIT, "Page output exceeds the page budget");
    void *block = nullptr; reader_av_item *array = nullptr;
    if (!items.empty()) {
      block = std::malloc(total);
      if (!block) throw std::bad_alloc();
      array = static_cast<reader_av_item *>(block);
      char *cursor = static_cast<char *>(block) + sizeof(reader_av_item) * items.size();
      for (size_t i = 0; i < items.size(); i++) {
        array[i] = items[i].item;
        auto place = [&](const text &t, char *&slot) {
          if (!t.has) { slot = nullptr; return; }
          std::memcpy(cursor, t.s.data(), t.s.size()); cursor[t.s.size()] = 0; slot = cursor; cursor += t.s.size() + 1;
        };
        place(items[i].part_path, array[i].part_path); place(items[i].page_id, array[i].page_id);
        place(items[i].exact, array[i].exact); place(items[i].prefix, array[i].prefix); place(items[i].suffix, array[i].suffix);
        place(items[i].chapter, array[i].chapter); place(items[i].note, array[i].note_text);
      }
    }
    if (r.poll()) { std::free(block); fail(READER_AV_CANCELLED, "Cancelled by the caller"); }
    page->items = array; page->count = items.size(); page->complete = complete ? 1 : 0; page->budget_stopped = stopped ? 1 : 0;
    page->output_bytes = total; page->wire_bytes = wire_bytes; page->revision_rows = items.size(); page->polls = r.polls;
    if (items.empty()) {
      make_cursor(page->next, *from, direction, from->has_after ? from->after_id : nullptr, complete);
      make_cursor(page->reverse, *from, -direction, from->has_after ? from->after_id : nullptr, complete && !from->has_after);
    } else {
      make_cursor(page->next, *from, direction, items.back().item.annotation_id, complete);
      make_cursor(page->reverse, *from, -direction, items.front().item.annotation_id, false);
    }
  });
}

extern "C" reader_av_status reader_av_page_set_resolution(reader_av_page *page, size_t index, reader_av_resolution resolution, reader_av_error *error) {
  return call(error, [&] {
    if (!page || index >= page->count || (unsigned)resolution > (unsigned)READER_AV_RESOLUTION_LEGACY) fail(READER_AV_ARGUMENT, "Bad page, index or resolution");
    page->items[index].resolution = resolution;
  });
}

extern "C" void reader_av_page_free(reader_av_page *page) {
  if (!page) return;
  std::free(page->items);
  std::memset(page, 0, sizeof(*page));
}

extern "C" reader_av_status reader_av_close(reader_av_view **view, reader_av_error *error) {
  return call(error, [&] {
    if (!view || !*view) fail(READER_AV_ARGUMENT, "Missing view");
    reader_av_view *v = *view;
    if (v->owner != std::this_thread::get_id()) fail(READER_AV_OWNER, "The view requires its creating thread");
    if (v->active) fail(READER_AV_BUSY, "The view is inside one of its calls");
    delete v; *view = nullptr;
  });
}

extern "C" reader_av_status reader_av_open(reader_revisions *s,const char *b,const reader_av_options *o,reader_av_view **v,reader_av_error *e){return open_view(false,s,b,o,v,e);}
extern "C" reader_av_status reader_av_page_get(reader_av_view *v,const reader_av_cursor *c,size_t n,reader_av_page *p,reader_av_error *e){return page_get(false,v,c,n,p,e);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_av_status reader_av_open_raw_v3(reader_revisions *s,const char *b,const reader_av_options *o,reader_av_view **v,reader_av_error *e){return open_view(true,s,b,o,v,e);}
extern "C" reader_av_status reader_av_page_get_raw_v3(reader_av_view *v,const reader_av_cursor *c,size_t n,reader_av_page *p,reader_av_error *e){return page_get(true,v,c,n,p,e);}
#endif