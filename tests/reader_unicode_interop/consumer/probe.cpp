/* SPDX-License-Identifier: MIT
 * G14 Unicode interop consumer. Public installed headers only.
 *
 * Every Unicode scalar enters through reader_command_utf16 from the binary
 * request container, so no Windows argv/ANSI round trip can corrupt it. The
 * consumer performs no normalization, no case folding and no expected-value
 * computation: it records exactly what the public API returns.
 */
#include <catalog.h>
#include <reader_commands.h>
#include <reader_projection.h>
#include <reader_revisions.h>

#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct item {
  int kind;
  std::string payload;
};

struct document {
  std::map<std::string, item> items;
  std::vector<std::string> item_order;
  std::map<std::string, std::string> aux;
  std::vector<std::string> ops;
};

document DOC;
std::map<std::string, std::string> TEXT;
std::vector<std::string> UTF16_ORDER;
std::map<std::string, int> U16_STATUS;
std::map<std::string, size_t> U16_BYTES;
std::map<std::string, std::string> U16_HEX;
std::vector<std::string> RECEIVED;

std::string OUT;

struct emitter {
  void rec(const std::string &id) {
    OUT += "#";
    OUT += id;
    OUT += "\n";
  }
  void f(const std::string &key, const std::string &value) {
    OUT += key;
    OUT += "=";
    for (size_t i = 0; i < value.size(); i++) OUT += (value[i] == '\n' ? '.' : value[i]);
    OUT += "\n";
  }
  void fn(const std::string &key, long long value) { f(key, std::to_string(value)); }
  void fh(const std::string &key, const char *data, size_t size) {
    static const char *digits = "0123456789abcdef";
    OUT += key;
    OUT += "=";
    for (size_t i = 0; i < size; i++) {
      unsigned char value = (unsigned char)data[i];
      OUT += digits[value >> 4];
      OUT += digits[value & 15];
    }
    OUT += "\n";
  }
  void fhs(const std::string &key, const std::string &value) { fh(key, value.data(), value.size()); }
  void fs(const std::string &key, const char *value) {
    if (value) f(key, value);
    else f(key, "null");
  }
};

emitter o;

std::string hexof(const char *data, size_t size) {
  static const char *digits = "0123456789abcdef";
  std::string out;
  out.reserve(size * 2);
  for (size_t i = 0; i < size; i++) {
    unsigned char value = (unsigned char)data[i];
    out += digits[value >> 4];
    out += digits[value & 15];
  }
  return out;
}

std::string prefix_row(int index) {
  char buffer[16];
  std::snprintf(buffer, sizeof buffer, "row%04d.", index);
  return std::string(buffer);
}

void load(const std::string &path) {
  std::ifstream in(path.c_str(), std::ios::binary);
  if (!in) throw std::runtime_error("cannot open request container");
  std::string data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  size_t off = 0;
  if (data.size() < 8 || data.compare(0, 4, "G141") != 0)
    throw std::runtime_error("bad request container magic");
  off = 4;
  struct reader {
    const std::string &data;
    size_t &off;
    void need(size_t count) {
      if (off + count > data.size()) throw std::runtime_error("truncated request container");
    }
    uint32_t u32() {
      need(4);
      uint32_t value = (uint32_t)(unsigned char)data[off]
        | ((uint32_t)(unsigned char)data[off + 1] << 8)
        | ((uint32_t)(unsigned char)data[off + 2] << 16)
        | ((uint32_t)(unsigned char)data[off + 3] << 24);
      off += 4;
      return value;
    }
    std::string str() {
      uint32_t size = u32();
      need(size);
      std::string value(data, off, size);
      off += size;
      return value;
    }
  } reader{data, off};
  if (reader.u32() != 1) throw std::runtime_error("unsupported request version");
  uint32_t count = reader.u32();
  for (uint32_t i = 0; i < count; i++) {
    std::string id = reader.str();
    reader.need(1);
    int kind = (unsigned char)data[off];
    off += 1;
    std::string payload = reader.str();
    item entry;
    entry.kind = kind;
    entry.payload = payload;
    DOC.items[id] = entry;
    DOC.item_order.push_back(id);
  }
  uint32_t aux_count = reader.u32();
  for (uint32_t i = 0; i < aux_count; i++) {
    std::string key = reader.str();
    DOC.aux[key] = reader.str();
  }
  uint32_t op_count = reader.u32();
  for (uint32_t i = 0; i < op_count; i++) DOC.ops.push_back(reader.str());
}

const std::string &A(const std::string &key) {
  std::map<std::string, std::string>::const_iterator found = DOC.aux.find(key);
  if (found == DOC.aux.end()) throw std::runtime_error("missing request key " + key);
  return found->second;
}

bool HA(const std::string &key) { return DOC.aux.find(key) != DOC.aux.end(); }

const std::string &TX(const std::string &name) {
  std::map<std::string, std::string>::const_iterator found = TEXT.find(name);
  if (found == TEXT.end()) throw std::runtime_error("missing converted text " + name);
  return found->second;
}

std::string REF(const std::string &name) {
  std::map<std::string, std::string>::const_iterator found = TEXT.find(name);
  if (found != TEXT.end()) return found->second;
  std::map<std::string, item>::const_iterator raw = DOC.items.find(name);
  if (raw != DOC.items.end()) return raw->second.payload;
  throw std::runtime_error("missing text or raw item " + name);
}

int kind_of(const std::string &name) {
  if (name == "shelf") return READER_GROUP_SHELF;
  if (name == "tag") return READER_GROUP_TAG;
  if (name == "series") return READER_GROUP_SERIES;
  throw std::runtime_error("unknown collection kind " + name);
}

int op_of(const std::string &name) {
  if (name == "put") return READER_COMMAND_PUT;
  if (name == "delete") return READER_COMMAND_DELETE;
  if (name == "restore") return READER_COMMAND_RESTORE;
  throw std::runtime_error("unknown command operation " + name);
}

std::vector<std::string> heads_of(const std::string &label) {
  const std::string &value = A("heads." + label);
  std::vector<std::string> out;
  size_t start = 0;
  while (start < value.size()) {
    size_t comma = value.find(',', start);
    if (comma == std::string::npos) {
      out.push_back(value.substr(start));
      break;
    }
    out.push_back(value.substr(start, comma - start));
    start = comma + 1;
  }
  return out;
}

void emit_command(const std::string &label, reader_command_status status,
                  const reader_command_result &result, const reader_command_error &error) {
  o.rec("cmd." + label);
  o.fn("status", (int)status);
  o.fn("created", result.created);
  o.fn("applied", result.applied);
  o.fn("revision_code", (int)error.revision.code);
  if (status == READER_COMMAND_OK) {
    o.f("revision_id", result.revision_id);
    o.f("entity_key", result.entity_key);
    o.f("sha256", result.revision.sha256);
    o.fn("bytes", (long long)result.revision.bytes);
    o.f("entity_kind", result.revision.entity_kind);
    o.f("operation", result.revision.operation);
    o.f("book_key", result.revision.book_key);
    o.fn("source_bytes", (long long)result.revision.source_bytes);
    o.fn("parent_count", (long long)result.revision.parent_count);
  }
}

void cmd_book(reader_revisions *store, const std::string &label) {
  std::string tag = A("book." + label);
  std::string op = A("act." + label);
  int operation = op_of(op);
  std::string original = A(tag + ".format");
  std::string format = HA("format." + label) ? A("format." + label) : original;
  std::string sha = A(tag + ".sha");
  /* The host passes the verified original identity; metadata must agree with it. */
  std::string key = original + ":" + sha;
  std::string title, author, sort;
  if (operation != READER_COMMAND_DELETE) {
    title = REF(A("title." + label));
    author = REF(A("author." + label));
    sort = REF(A("sort." + label));
  }
  reader_book_command command;
  std::memset(&command, 0, sizeof command);
  command.operation = (reader_command_operation)operation;
  command.book_key = key.c_str();
  if (operation != READER_COMMAND_DELETE) {
    command.format = format.c_str();
    command.source_sha256 = sha.c_str();
    command.title = title.c_str();
    command.author = author.c_str();
    command.sort_title = sort.c_str();
    command.source_bytes = (uint64_t)std::stoull(A(tag + ".bytes"));
    command.favorite = std::stoi(A(tag + ".favorite"));
  }
  std::vector<std::string> owned = heads_of(label);
  std::vector<const char *> pointers;
  for (size_t i = 0; i < owned.size(); i++) pointers.push_back(owned[i].c_str());
  std::string revision_id = A("rev." + label);
  reader_command_context context;
  std::memset(&context, 0, sizeof context);
  context.store = store;
  context.revision_id = revision_id.c_str();
  context.expected_heads = pointers.empty() ? nullptr : &pointers[0];
  context.expected_count = pointers.size();
  reader_command_result result;
  reader_command_error error;
  reader_command_status status = reader_command_apply_book(&context, &command, &result, &error);
  emit_command(label, status, result, error);
  if (status == READER_COMMAND_OK && result.created) RECEIVED.push_back(label);
}

void cmd_group(reader_revisions *store, const std::string &label) {
  std::string gid = A("gid." + label);
  std::string kind = A("gkind." + label);
  std::string op = A("act." + label);
  int operation = op_of(op);
  std::string name, parent;
  uint64_t ordinal = 0;
  if (operation != READER_COMMAND_DELETE) {
    name = REF(A("name." + label));
    parent = A("parent." + label);
    ordinal = (uint64_t)std::stoull(A("ordinal." + label));
  }
  reader_group_command command;
  std::memset(&command, 0, sizeof command);
  command.operation = (reader_command_operation)operation;
  command.kind = (reader_group_kind)kind_of(kind);
  command.id = gid.c_str();
  if (operation != READER_COMMAND_DELETE) {
    command.name = name.c_str();
    command.parent_id = parent.empty() ? nullptr : parent.c_str();
    command.ordinal = ordinal;
  }
  std::vector<std::string> owned = heads_of(label);
  std::vector<const char *> pointers;
  for (size_t i = 0; i < owned.size(); i++) pointers.push_back(owned[i].c_str());
  std::string revision_id = A("rev." + label);
  reader_command_context context;
  std::memset(&context, 0, sizeof context);
  context.store = store;
  context.revision_id = revision_id.c_str();
  context.expected_heads = pointers.empty() ? nullptr : &pointers[0];
  context.expected_count = pointers.size();
  reader_command_result result;
  reader_command_error error;
  reader_command_status status = reader_command_apply_group(&context, &command, &result, &error);
  emit_command(label, status, result, error);
  if (status == READER_COMMAND_OK && result.created) RECEIVED.push_back(label);
}

void cmd_membership(reader_revisions *store, const std::string &label) {
  std::string gid = A("gid." + label);
  std::string book_key = A("bkey." + label);
  std::string kind = A("gkind." + label);
  std::string op = A("act." + label);
  int operation = op_of(op);
  reader_membership_command command;
  std::memset(&command, 0, sizeof command);
  command.operation = (reader_command_operation)operation;
  command.kind = (reader_group_kind)kind_of(kind);
  command.group_id = gid.c_str();
  command.book_key = book_key.c_str();
  command.ordinal = (uint64_t)std::stoull(A("ordinal." + label));
  std::vector<std::string> owned = heads_of(label);
  std::vector<const char *> pointers;
  for (size_t i = 0; i < owned.size(); i++) pointers.push_back(owned[i].c_str());
  std::string revision_id = A("rev." + label);
  reader_command_context context;
  std::memset(&context, 0, sizeof context);
  context.store = store;
  context.revision_id = revision_id.c_str();
  context.expected_heads = pointers.empty() ? nullptr : &pointers[0];
  context.expected_count = pointers.size();
  reader_command_result result;
  reader_command_error error;
  reader_command_status status = reader_command_apply_membership(&context, &command, &result, &error);
  emit_command(label, status, result, error);
  if (status == READER_COMMAND_OK && result.created) RECEIVED.push_back(label);
}

void run_ops(reader_revisions *store) {
  for (size_t i = 0; i < DOC.ops.size(); i++) {
    const std::string &label = DOC.ops[i];
    std::string type = A("type." + label);
    if (type == "book") cmd_book(store, label);
    else if (type == "group") cmd_group(store, label);
    else cmd_membership(store, label);
  }
}

/* ---------------------------------------------------------------- attach */

int attach_case(reader_catalog *catalog, const std::string &format, const std::string &sha,
                const std::string &title, const std::string &author, const std::string &sort,
                const std::string &location, uint64_t bytes, int64_t sdk, int favorite) {
  reader_catalog_book book;
  std::memset(&book, 0, sizeof book);
  book.format = format.c_str();
  book.sha256 = sha.c_str();
  book.title = title.c_str();
  book.author = author.c_str();
  book.sort_title = sort.c_str();
  book.location_kind = location.c_str();
  book.source_bytes = bytes;
  book.sdk_book_id = sdk;
  book.favorite = favorite;
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  return reader_catalog_attach(catalog, &book, &error);
}

void attach_all(reader_catalog *catalog) {
  for (int n = 1;; n++) {
    std::string tag = "b" + std::to_string(n);
    if (!HA(tag + ".sha")) break;
    std::string format = A(tag + ".format");
    std::string sha = A(tag + ".sha");
    std::string location = A(tag + ".location");
    std::string title = REF(A(tag + ".title"));
    std::string author = REF(A(tag + ".author"));
    std::string sort = REF(A(tag + ".sort"));
    std::string key = format + ":" + sha;
    int status = attach_case(catalog, format, sha, title, author, sort, location,
                             (uint64_t)std::stoull(A(tag + ".bytes")),
                             (int64_t)std::stoll(A(tag + ".sdk")),
                             std::stoi(A(tag + ".favorite")));
    o.rec("attach." + tag);
    o.fn("status", status);
    o.f("key", key);
  }

  const std::string empty;
  const char *raws[] = {"raw.title_lone_cont", "raw.title_overlong", "raw.title_truncated",
                        "raw.title_surrogate", "raw.title_beyond"};
  const char *names[] = {"title_lone_cont", "title_overlong", "title_truncated",
                         "title_surrogate", "title_beyond"};
  for (int i = 0; i < 5; i++) {
    std::string bad = REF(raws[i]);
    int status = attach_case(catalog, "txt", A("neg.sha"), bad, empty, empty,
                             "reflow_global", 1, 900 + i, 0);
    o.rec(std::string("attach.neg.") + names[i]);
    o.fn("status", status);
  }
  {
    std::string bad = REF("raw.title_truncated");
    o.rec("attach.neg.author_badutf8");
    o.fn("status", attach_case(catalog, "txt", A("neg.sha"), "ok", bad, empty,
                               "reflow_global", 1, 910, 0));
    o.rec("attach.neg.sort_badutf8");
    o.fn("status", attach_case(catalog, "txt", A("neg.sha"), "ok", empty, bad,
                               "reflow_global", 1, 911, 0));
  }
  {
    std::string wide = REF("t.over_cjk_4097");
    o.rec("attach.neg.over_scalars_title");
    o.fn("status", attach_case(catalog, "txt", A("neg.sha"), wide, empty, empty,
                               "reflow_global", 1, 912, 0));
    o.rec("attach.neg.over_scalars_sort");
    o.fn("status", attach_case(catalog, "txt", A("neg.sha"), "ok", empty, wide,
                               "reflow_global", 1, 913, 0));
  }
  o.rec("attach.neg.format");
  o.fn("status", attach_case(catalog, "exe", A("neg.sha"), "ok", empty, empty,
                             "reflow_global", 1, 914, 0));
  {
    std::string upper = A("neg.sha");
    for (size_t i = 0; i < upper.size(); i++) upper[i] = (char)std::toupper((unsigned char)upper[i]);
    o.rec("attach.neg.sha_upper");
    o.fn("status", attach_case(catalog, "txt", upper, "ok", empty, empty,
                               "reflow_global", 1, 915, 0));
  }
  o.rec("attach.neg.favorite2");
  o.fn("status", attach_case(catalog, "txt", A("neg.sha"), "ok", empty, empty,
                             "reflow_global", 1, 916, 2));
  {
    std::string format = A("b1.format");
    std::string sha = A("b1.sha");
    std::string key = format + ":" + sha;
    uint64_t bytes = (uint64_t)std::stoull(A("b1.bytes")) + 1;
    o.rec("attach.neg.bytes_conflict");
    o.fn("status", attach_case(catalog, format, sha, REF(A("b1.title")), REF(A("b1.author")),
                               REF(A("b1.sort")), A("b1.location"), bytes,
                               (int64_t)std::stoll(A("b1.sdk")), 0));
    o.rec("attach.neg.sdk_conflict");
    o.fn("status", attach_case(catalog, A("b2.format"), A("b2.sha"), REF(A("b2.title")),
                               REF(A("b2.author")), REF(A("b2.sort")), A("b2.location"),
                               (uint64_t)std::stoull(A("b2.bytes")),
                               (int64_t)std::stoll(A("b1.sdk")), 0));
    (void)key;
  }
  {
    reader_catalog_error removal;
    std::memset(&removal, 0, sizeof removal);
    o.rec("remove_local.b14");
    o.fn("status", reader_catalog_remove_local(catalog, (int64_t)std::stoll(A("b14.sdk")),
                                               &removal));
  }
}

/* ------------------------------------------------------------- revisions */

struct head_sink {
  emitter *out;
  int index;
};

int visit_head(void *raw, const reader_revision_head *head) {
  head_sink *sink = (head_sink *)raw;
  std::string prefix = prefix_row(sink->index);
  sink->out->f(prefix + "revision_id", head->revision_id);
  sink->out->f(prefix + "operation", head->operation);
  sink->out->f(prefix + "sha256", head->sha256);
  sink->out->fn(prefix + "complete", head->complete);
  sink->out->fn(prefix + "requires_restore", head->requires_restore);
  sink->index++;
  return 0;
}

struct entity_sink {
  emitter *out;
  int index;
};

int visit_entity(void *raw, const reader_revision_entity_row *row) {
  entity_sink *sink = (entity_sink *)raw;
  std::string prefix = prefix_row(sink->index);
  sink->out->f(prefix + "key", row->entity_key);
  sink->out->fn(prefix + "kind", (int)row->selection.kind);
  sink->out->f(prefix + "operation", row->info.operation);
  sink->out->f(prefix + "sha256", row->info.sha256);
  sink->out->fn(prefix + "bytes", (long long)row->info.bytes);
  sink->index++;
  return 0;
}

void read_revisions(reader_revisions *store, const std::string &prefix) {
  std::map<std::string, std::string> wires;
  for (size_t i = 0; i < RECEIVED.size(); i++) {
    const std::string &label = RECEIVED[i];
    char *wire = nullptr;
    size_t bytes = 0;
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    reader_revision_status status = reader_revision_get(store, A("rev." + label).c_str(),
                                                        &wire, &bytes, &info, &error);
    o.rec(prefix + "rev.get." + label);
    o.fn("status", (int)status);
    if (status == READER_REV_OK) {
      o.fn("bytes", (long long)bytes);
      o.fh("hex", wire, bytes);
      o.f("sha256", info.sha256);
      o.f("entity_kind", info.entity_kind);
      o.f("entity_key", info.entity_key);
      o.f("operation", info.operation);
      o.f("book_key", info.book_key);
      o.fn("source_bytes", (long long)info.source_bytes);
      o.fn("parent_count", (long long)info.parent_count);
      wires[label] = std::string(wire, bytes);
    }
    if (wire) reader_revision_bytes_free(wire);
  }

  static const char *HEADS[][2] = {
    {"book", "b1"}, {"book", "b2"}, {"book", "b6"}, {"book", "b13"},
    {"shelf", "s1"}, {"shelf", "s4"}, {"tag", "t3"}, {"series", "r1"},
    {"membership", "m.s1.b1"}, {"membership", "m.t2.b9"}};
  for (int i = 0; i < 10; i++) {
    std::string kind = HEADS[i][0];
    std::string key = A(std::string("ek.") + HEADS[i][1]);
    reader_revision_state state;
    std::memset(&state, 0, sizeof state);
    head_sink sink;
    sink.out = &o;
    sink.index = 0;
    o.rec(prefix + "rev.heads." + key);
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    reader_revision_status status = reader_revision_heads(store, kind.c_str(), key.c_str(),
                                                          visit_head, &sink, &state, &error);
    o.fn("status", (int)status);
    o.fn("revisions", (long long)state.revisions);
    o.fn("heads", (long long)state.heads);
    o.fn("missing_parents", (long long)state.missing_parents);
    o.fn("foreign_parents", (long long)state.foreign_parents);
    o.fn("projection_safe", state.projection_safe);
    o.fn("deleted", state.deleted);
    o.fn("requires_restore", state.requires_restore);
  }
  for (int i = 0; i < 10; i++) {
    std::string kind = HEADS[i][0];
    std::string key = A(std::string("ek.") + HEADS[i][1]);
    char *wire = nullptr;
    size_t bytes = 0;
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    reader_revision_selection selection;
    std::memset(&selection, 0, sizeof selection);
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    reader_revision_status status = reader_revision_selected(store, kind.c_str(), key.c_str(),
                                                             &wire, &bytes, &info, &selection, &error);
    o.rec(prefix + "rev.selected." + key);
    o.fn("status", (int)status);
    o.fn("kind", (int)selection.kind);
    if (status == READER_REV_OK) {
      o.f("revision_id", info.revision_id);
      o.fn("bytes", (long long)bytes);
      o.fh("hex", wire, bytes);
      o.f("sha256", info.sha256);
    }
    if (wire) reader_revision_bytes_free(wire);
  }

  static const char *TITLES[] = {"put.b1", "put.b1.3", "put.b13", "put.b11"};
  for (int i = 0; i < 4; i++) {
    std::string label = TITLES[i];
    char *title = nullptr;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    reader_revision_status status = reader_revision_book_title(store, A("rev." + label).c_str(),
                                                               &title, &error);
    o.rec(prefix + "rev.title." + label);
    o.fn("status", (int)status);
    if (status == READER_REV_OK) o.fh("hex", title, std::strlen(title));
    if (title) reader_revision_bytes_free(title);
  }

  {
    const std::string &wire = wires["put.b1.3"];
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    reader_revision_status status = reader_revision_validate(store, wire.data(), wire.size(),
                                                             A("sha.put.b1.3").c_str(), &info, &error);
    o.rec(prefix + "rev.validate.ok");
    o.fn("status", (int)status);
    if (status == READER_REV_OK) {
      o.f("sha256", info.sha256);
      o.fn("bytes", (long long)info.bytes);
      o.f("entity_key", info.entity_key);
      o.f("operation", info.operation);
    }
  }
  {
    const std::string &wire = wires["put.b1.3"];
    std::string zeros(64, '0');
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec(prefix + "rev.validate.bad_sha");
    o.fn("status", (int)reader_revision_validate(store, wire.data(), wire.size(),
                                                 zeros.c_str(), nullptr, &error));
  }
  {
    std::string broken = REF("raw.wire_badutf8");
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec(prefix + "rev.validate.bad_utf8");
    o.fn("status", (int)reader_revision_validate(store, broken.data(), broken.size(),
                                                 A("sha.raw.wire_badutf8").c_str(), nullptr, &error));
  }
  {
    std::string truncated = REF("raw.wire_truncated");
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec(prefix + "rev.validate.truncated");
    o.fn("status", (int)reader_revision_validate(store, truncated.data(), truncated.size(),
                                                 A("sha.raw.wire_truncated").c_str(), nullptr, &error));
  }

  static const char *KINDS[] = {"book", "shelf", "tag", "series", "membership"};
  for (int i = 0; i < 5; i++) {
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    entity_sink sink;
    sink.out = &o;
    sink.index = 0;
    o.rec(prefix + "rev.entities." + KINDS[i]);
    reader_revision_status status = reader_revision_entities_page(store, KINDS[i], nullptr, 1, 100,
                                                                  visit_entity, &sink, &error);
    o.fn("status", (int)status);
    o.fn("rows", sink.index);
  }
}

/* --------------------------------------------------------------- catalog */

struct book_sink {
  emitter *out;
  int index;
  bool with_local;
  std::string first_sort;
  std::string first_key;
  std::string last_sort;
  std::string last_key;
};

int visit_book(void *raw, const reader_catalog_row *row) {
  book_sink *sink = (book_sink *)raw;
  std::string prefix = prefix_row(sink->index);
  sink->out->f(prefix + "key", row->book_key);
  sink->out->f(prefix + "format", row->format);
  sink->out->fn(prefix + "source_bytes", (long long)row->source_bytes);
  sink->out->fn(prefix + "favorite", row->favorite);
  sink->out->fh(prefix + "title", row->title, std::strlen(row->title));
  sink->out->fh(prefix + "sort_title", row->sort_title, std::strlen(row->sort_title));
  sink->out->fh(prefix + "author", row->author, std::strlen(row->author));
  sink->out->fn(prefix + "deleted", row->deleted);
  if (sink->with_local) {
    sink->out->fn(prefix + "sdk_book_id", (long long)row->sdk_book_id);
    sink->out->fs(prefix + "location_kind", row->location_kind);
  }
  if (sink->index == 0) {
    sink->first_sort = row->sort_title;
    sink->first_key = row->book_key;
  }
  sink->last_sort = row->sort_title;
  sink->last_key = row->book_key;
  sink->index++;
  return 0;
}

struct page_sum {
  int status;
  int count;
  std::string first_sort;
  std::string first_key;
  std::string last_sort;
  std::string last_key;
};

void begin_sink(book_sink &sink, bool with_local) {
  sink.out = &o;
  sink.index = 0;
  sink.with_local = with_local;
  sink.first_sort.clear();
  sink.first_key.clear();
  sink.last_sort.clear();
  sink.last_key.clear();
}

page_sum finish_sink(int status, const book_sink &sink) {
  o.fn("status", status);
  o.fn("rows", sink.index);
  page_sum sum;
  sum.status = status;
  sum.count = sink.index;
  sum.first_sort = sink.first_sort;
  sum.first_key = sink.first_key;
  sum.last_sort = sink.last_sort;
  sum.last_key = sink.last_key;
  return sum;
}

page_sum run_query(reader_catalog *catalog, const std::string &id, const char *cursor_title,
                   const char *cursor_key, const char *query, int direction, size_t limit,
                   int local, bool with_local) {
  book_sink sink;
  begin_sink(sink, with_local);
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = local
    ? reader_catalog_local_page(catalog, cursor_title, cursor_key, query, direction, limit,
                                visit_book, &sink, &error)
    : reader_catalog_query_page(catalog, cursor_title, cursor_key, query, direction, limit,
                                visit_book, &sink, &error);
  return finish_sink(status, sink);
}

page_sum run_canonical(reader_catalog *catalog, const std::string &id, const char *cursor_title,
                      const char *cursor_key, const char *nfc, const char *nfd, int direction,
                      int inclusive, size_t limit) {
  book_sink sink;
  begin_sink(sink, true);
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_local_canonical_page(catalog, cursor_title, cursor_key, nfc, nfd,
                                                   direction, inclusive, limit, visit_book, &sink,
                                                   &error);
  return finish_sink(status, sink);
}

void run_find(reader_catalog *catalog, const std::string &id, const char *key, const char *query) {
  book_sink sink;
  begin_sink(sink, false);
  int found = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_find(catalog, key, query, visit_book, &sink, &found, &error);
  o.fn("status", status);
  o.fn("found", found);
  o.fn("rows", sink.index);
}

void run_meta(reader_catalog *catalog, const std::string &id, const char *key, bool with_local) {
  book_sink sink;
  begin_sink(sink, with_local);
  int found = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_metadata(catalog, key, visit_book, &sink, &found, &error);
  o.fn("status", status);
  o.fn("found", found);
  o.fn("rows", sink.index);
}

struct group_sink {
  emitter *out;
  int index;
};

int visit_group(void *raw, const reader_catalog_group_row *row) {
  group_sink *sink = (group_sink *)raw;
  std::string prefix = prefix_row(sink->index);
  sink->out->f(prefix + "id", row->id);
  sink->out->fh(prefix + "name", row->name, std::strlen(row->name));
  sink->out->fs(prefix + "parent_id", row->parent_id);
  sink->out->fn(prefix + "ordinal", (long long)row->ordinal);
  sink->out->fn(prefix + "deleted", row->deleted);
  sink->index++;
  return 0;
}

void run_groups(reader_catalog *catalog, const std::string &id, int kind, const char *parent,
                int direction, size_t limit) {
  group_sink sink;
  sink.out = &o;
  sink.index = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_groups_page(catalog, (reader_catalog_group_kind)kind, parent,
                                          nullptr, direction, limit, visit_group, &sink, &error);
  o.fn("status", status);
  o.fn("rows", sink.index);
}

void run_removed(reader_catalog *catalog, const std::string &id, int kind, int direction,
                 size_t limit) {
  group_sink sink;
  sink.out = &o;
  sink.index = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_removed_groups_page(catalog, (reader_catalog_group_kind)kind,
                                                  nullptr, direction, limit, visit_group, &sink,
                                                  &error);
  o.fn("status", status);
  o.fn("rows", sink.index);
}

struct gb_sink {
  emitter *out;
  int index;
  bool with_local;
};

int visit_group_book(void *raw, const reader_catalog_group_book_row *row) {
  gb_sink *sink = (gb_sink *)raw;
  std::string prefix = prefix_row(sink->index);
  sink->out->f(prefix + "key", row->book.book_key);
  sink->out->f(prefix + "format", row->book.format);
  sink->out->fn(prefix + "source_bytes", (long long)row->book.source_bytes);
  sink->out->fn(prefix + "favorite", row->book.favorite);
  sink->out->fh(prefix + "title", row->book.title, std::strlen(row->book.title));
  sink->out->fh(prefix + "sort_title", row->book.sort_title, std::strlen(row->book.sort_title));
  sink->out->fh(prefix + "author", row->book.author, std::strlen(row->book.author));
  sink->out->fn(prefix + "deleted", row->book.deleted);
  if (sink->with_local) {
    sink->out->fn(prefix + "sdk_book_id", (long long)row->book.sdk_book_id);
    sink->out->fs(prefix + "location_kind", row->book.location_kind);
  }
  sink->out->fn(prefix + "ordinal", (long long)row->ordinal);
  sink->index++;
  return 0;
}

void run_group_books(reader_catalog *catalog, const std::string &id, int kind, const char *gid,
                     const char *query, int local_only, size_t limit, bool with_local) {
  gb_sink sink;
  sink.out = &o;
  sink.index = 0;
  sink.with_local = with_local;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_group_books_page(catalog, (reader_catalog_group_kind)kind, gid,
                                               nullptr, query, local_only, 1, limit,
                                               visit_group_book, &sink, &error);
  o.fn("status", status);
  o.fn("rows", sink.index);
}

struct member_sink {
  emitter *out;
  int index;
};

int visit_membership(void *raw, const reader_catalog_membership_row *row) {
  member_sink *sink = (member_sink *)raw;
  sink->out->f("group_id", row->group_id);
  sink->out->f("book_key", row->book_key);
  sink->out->fn("ordinal", (long long)row->ordinal);
  sink->out->fn("group_deleted", row->group_deleted);
  sink->out->fn("book_deleted", row->book_deleted);
  sink->index++;
  return 0;
}

void run_membership(reader_catalog *catalog, const std::string &id, int kind, const char *gid,
                    const char *key) {
  member_sink sink;
  sink.out = &o;
  sink.index = 0;
  o.rec(id);
  int found = 0;
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_membership_find(catalog, (reader_catalog_group_kind)kind, gid, key,
                                              visit_membership, &sink, &found, &error);
  o.fn("status", status);
  o.fn("found", found);
}

void run_group_find(reader_catalog *catalog, const std::string &id, int kind, const char *gid) {
  group_sink sink;
  sink.out = &o;
  sink.index = 0;
  int found = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_group_find(catalog, (reader_catalog_group_kind)kind, gid,
                                         visit_group, &sink, &found, &error);
  o.fn("status", status);
  o.fn("found", found);
  if (!found) o.fn("rows", 0);
}

void run_lookup_sdk(reader_catalog *catalog, const std::string &id, long long sdk) {
  book_sink sink;
  begin_sink(sink, true);
  int found = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_local_lookup(catalog, (int64_t)sdk, nullptr, visit_book, &sink,
                                           &found, &error);
  o.fn("status", status);
  o.fn("found", found);
  o.fn("rows", sink.index);
}

void run_lookup_title(reader_catalog *catalog, const std::string &id, const char *title) {
  book_sink sink;
  begin_sink(sink, true);
  int found = 0;
  o.rec(id);
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_local_lookup(catalog, 0, title, visit_book, &sink, &found, &error);
  o.fn("status", status);
  o.fn("found", found);
  o.fn("rows", sink.index);
}

void run_has_local(reader_catalog *catalog, const std::string &id, long long sdk) {
  int present = 0;
  reader_catalog_error error;
  std::memset(&error, 0, sizeof error);
  int status = reader_catalog_has_local(catalog, (int64_t)sdk, &present, &error);
  o.rec(id);
  o.fn("status", status);
  o.fn("present", present);
}

void read_catalog(reader_catalog *catalog, const std::string &prefix, bool no_local) {
  page_sum sum;
  run_query(catalog, prefix + "page.all", nullptr, nullptr, nullptr, 1, 200, 0, false);
  sum = run_query(catalog, prefix + "page.p0", nullptr, nullptr, nullptr, 1, 5, 0, false);
  sum = run_query(catalog, prefix + "page.p1", sum.last_sort.c_str(), sum.last_key.c_str(),
                  nullptr, 1, 5, 0, false);
  sum = run_query(catalog, prefix + "page.p2", sum.last_sort.c_str(), sum.last_key.c_str(),
                  nullptr, 1, 5, 0, false);
  sum = run_query(catalog, prefix + "page.rev0", nullptr, nullptr, nullptr, -1, 4, 0, false);
  run_query(catalog, prefix + "page.rev1", sum.last_sort.c_str(), sum.last_key.c_str(),
            nullptr, -1, 4, 0, false);

  run_query(catalog, prefix + "query.cjk", nullptr, nullptr, TX("t.search_cjk").c_str(), 1, 200, 0, false);
  run_query(catalog, prefix + "query.ascii_fold", nullptr, nullptr, TX("t.search_ascii").c_str(), 1, 200, 0, false);
  run_query(catalog, prefix + "query.upper", nullptr, nullptr, TX("t.search_upper").c_str(), 1, 200, 0, false);
  run_query(catalog, prefix + "query.nfd", nullptr, nullptr, TX("t.nfd_cafe").c_str(), 1, 200, 0, false);
  run_query(catalog, prefix + "query.ru", nullptr, nullptr, TX("t.ru_title").c_str(), 1, 200, 0, false);
  run_query(catalog, prefix + "query.rtl", nullptr, nullptr, TX("t.mixed_rtl").c_str(), 1, 200, 0, false);
  run_query(catalog, prefix + "query.empty", nullptr, nullptr, TX("t.empty").c_str(), 1, 200, 0, false);

  if (!no_local) {
    run_query(catalog, prefix + "local.page", nullptr, nullptr, nullptr, 1, 200, 1, true);
    page_sum canon = run_canonical(catalog, prefix + "local.canon", nullptr, nullptr,
                                   TX("t.nfc_cafe").c_str(), TX("t.nfd_cafe").c_str(), 1, 0, 200);
    run_canonical(catalog, prefix + "local.canon.inc", canon.first_sort.c_str(),
                  canon.first_key.c_str(), TX("t.nfc_cafe").c_str(), TX("t.nfd_cafe").c_str(),
                  1, 1, 200);
    run_canonical(catalog, prefix + "local.canon.exc", canon.first_sort.c_str(),
                  canon.first_key.c_str(), TX("t.nfc_cafe").c_str(), TX("t.nfd_cafe").c_str(),
                  1, 0, 200);
    run_lookup_sdk(catalog, prefix + "local_lookup.sdk101", 101);
    run_lookup_sdk(catalog, prefix + "local_lookup.sdk114", 114);
    run_lookup_title(catalog, prefix + "local_lookup.title_nfc", TX("t.nfc_cafe").c_str());
    run_lookup_title(catalog, prefix + "local_lookup.title_nfd", TX("t.nfd_cafe").c_str());
    run_has_local(catalog, prefix + "has_local.b1", 101);
    run_has_local(catalog, prefix + "has_local.b14", 114);
  }

  run_find(catalog, prefix + "find.b1", A("ek.b1").c_str(), TX("t.nfc_cafe").c_str());
  run_find(catalog, prefix + "find.b6", A("ek.b6").c_str(), TX("t.empty").c_str());
  run_find(catalog, prefix + "find.miss", A("ek.b1").c_str(), TX("t.ru_title").c_str());
  run_find(catalog, prefix + "find.b14", A("ek.b14").c_str(), TX("t.empty").c_str());

  run_meta(catalog, prefix + "meta.b1", A("ek.b1").c_str(), false);
  run_meta(catalog, prefix + "meta.b6", A("ek.b6").c_str(), false);
  run_meta(catalog, prefix + "meta.b13", A("ek.b13").c_str(), false);
  run_meta(catalog, prefix + "meta.absent", A("absent.book_key").c_str(), false);
  if (!no_local) run_meta(catalog, prefix + "meta.local14", A("ek.b14").c_str(), true);

  run_groups(catalog, prefix + "groups.shelf.roots", READER_CATALOG_SHELF, nullptr, 1, 200);
  run_groups(catalog, prefix + "groups.shelf.children", READER_CATALOG_SHELF,
             A("g.s1.id").c_str(), 1, 200);
  run_groups(catalog, prefix + "groups.tag", READER_CATALOG_TAG, nullptr, 1, 200);
  run_groups(catalog, prefix + "groups.series", READER_CATALOG_SERIES, nullptr, 1, 200);
  run_removed(catalog, prefix + "removed.shelf", READER_CATALOG_SHELF, 1, 200);
  run_removed(catalog, prefix + "removed.tag", READER_CATALOG_TAG, 1, 200);

  static const char *GBS[] = {"s1", "s2", "s3", "t1", "t2", "r1", "r2"};
  for (int i = 0; i < 7; i++) {
    std::string name = GBS[i];
    run_group_books(catalog, prefix + "gb." + name, kind_of(A("g." + name + ".kind")),
                    A("g." + name + ".id").c_str(), nullptr, 0, 200, false);
  }
  if (!no_local)
    run_group_books(catalog, prefix + "gb.s1.local", READER_CATALOG_SHELF,
                    A("g.s1.id").c_str(), nullptr, 1, 200, true);
  run_group_books(catalog, prefix + "gbq.s1", READER_CATALOG_SHELF, A("g.s1.id").c_str(),
                  TX("t.nfc_cafe").c_str(), 0, 200, false);

  run_membership(catalog, prefix + "membership.s1.b1", READER_CATALOG_SHELF,
                 A("g.s1.id").c_str(), A("ek.b1").c_str());
  run_membership(catalog, prefix + "membership.t2.b9", READER_CATALOG_TAG,
                 A("g.t2.id").c_str(), A("ek.b9").c_str());
  run_group_find(catalog, prefix + "group_find.s4", READER_CATALOG_SHELF, A("g.s4.id").c_str());
  run_group_find(catalog, prefix + "group_find.absent", READER_CATALOG_SHELF,
                 A("absent.group_id").c_str());
}

/* -------------------------------------------------------------- transport */

std::string retained(reader_revisions *store, const std::string &label) {
  char *wire = nullptr;
  size_t bytes = 0;
  reader_revision_info info;
  std::memset(&info, 0, sizeof info);
  reader_revision_error error;
  std::memset(&error, 0, sizeof error);
  reader_revision_status status = reader_revision_get(store, A("rev." + label).c_str(), &wire,
                                                      &bytes, &info, &error);
  if (status != READER_REV_OK) throw std::runtime_error("retained revision unavailable: " + label);
  std::string copy(wire, bytes);
  reader_revision_bytes_free(wire);
  return copy;
}

void run_transport(reader_revisions *local, reader_revisions *mirror) {
  /* Receive and project each revision in causal order so every expected head
     is the current unique head when it is applied, exactly as the writer saw it. */
  for (size_t i = 0; i < RECEIVED.size(); i++) {
    const std::string &label = RECEIVED[i];
    std::string wire = retained(local, label);
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    int created = 0;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    reader_revision_status status = reader_revision_receive(mirror, wire.data(), wire.size(),
                                                            A("sha." + label).c_str(), &info,
                                                            &created, &error);
    o.rec("rx." + label);
    o.fn("status", (int)status);
    o.fn("created", created);
    if (status == READER_REV_OK) {
      o.fn("bytes", (long long)info.bytes);
      o.f("sha256", info.sha256);
    }
    if (status != READER_REV_OK) continue;
    std::string kind = A("entity_kind." + label);
    std::string key = A("key." + label);
    std::string head = A("rev." + label);
    const char *sort = nullptr;
    std::string sort_storage;
    if (HA("sort." + label)) {
      sort_storage = REF(A("sort." + label));
      sort = sort_storage.c_str();
    }
    reader_revision_info projected;
    std::memset(&projected, 0, sizeof projected);
    reader_revision_error projection;
    std::memset(&projection, 0, sizeof projection);
    reader_revision_status applied = reader_revision_project(mirror, kind.c_str(), key.c_str(),
                                                             head.c_str(), sort, &projected,
                                                             &projection);
    o.rec("proj." + label);
    o.fn("status", (int)applied);
    if (applied == READER_REV_OK) {
      o.f("revision_id", projected.revision_id);
      o.f("sha256", projected.sha256);
      o.f("entity_key", projected.entity_key);
    }
  }
}

void transport_negatives(reader_revisions *local, reader_revisions *mirror) {
  if (RECEIVED.empty()) throw std::runtime_error("no local revision was created");
  std::string wire = retained(local, RECEIVED[0]);
  {
    std::string zeros(64, '0');
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    int created = 0;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec("rx.neg.bad_sha");
    o.fn("status", (int)reader_revision_receive(mirror, wire.data(), wire.size(), zeros.c_str(),
                                                &info, &created, &error));
    o.fn("created", created);
  }
  {
    std::string broken = wire;
    size_t mark = broken.find("\"source_bytes\":");
    if (mark == std::string::npos) throw std::runtime_error("sample wire lacks source_bytes");
    char &digit = broken[mark + 16];
    digit = (digit == '5') ? '6' : '5';
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    int created = 0;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec("rx.neg.corrupt");
    o.fn("status", (int)reader_revision_receive(mirror, broken.data(), broken.size(),
                                                A("sha." + RECEIVED[0]).c_str(), &info, &created,
                                                &error));
    o.fn("created", created);
  }
  {
    std::string invalid = REF("raw.wire_badutf8");
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    int created = 0;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec("rx.neg.bad_utf8");
    o.fn("status", (int)reader_revision_receive(mirror, invalid.data(), invalid.size(),
                                                A("sha.raw.wire_badutf8").c_str(), &info, &created,
                                                &error));
    o.fn("created", created);
  }
  {
    std::string truncated = REF("raw.wire_truncated");
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    int created = 0;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec("rx.neg.truncated");
    o.fn("status", (int)reader_revision_receive(mirror, truncated.data(), truncated.size(),
                                                A("sha.raw.wire_truncated").c_str(), &info,
                                                &created, &error));
    o.fn("created", created);
  }
  {
    reader_revision_info info;
    std::memset(&info, 0, sizeof info);
    int created = 0;
    reader_revision_error error;
    std::memset(&error, 0, sizeof error);
    o.rec("rx.neg.duplicate");
    o.fn("status", (int)reader_revision_receive(mirror, wire.data(), wire.size(),
                                                A("sha." + RECEIVED[0]).c_str(), &info, &created,
                                                &error));
    o.fn("created", created);
    o.fn("bytes", (long long)info.bytes);
    o.f("sha256", info.sha256);
  }
}

/* ----------------------------------------------------------------- escape */

void run_escape(reader_revisions *store, reader_catalog *catalog, const std::string &label) {
  std::string wire = REF("escwire." + label);
  reader_revision_info info;
  std::memset(&info, 0, sizeof info);
  int created = 0;
  reader_revision_error error;
  std::memset(&error, 0, sizeof error);
  reader_revision_status status = reader_revision_receive(store, wire.data(), wire.size(),
                                                          A("esc." + label + ".sha").c_str(),
                                                          &info, &created, &error);
  if (status != READER_REV_OK) throw std::runtime_error("escape receive failed: " + label);
  reader_revision_info projected;
  std::memset(&projected, 0, sizeof projected);
  std::string sort = REF(A("esc." + label + ".sort"));
  status = reader_revision_project(store, "book", A("esc." + label + ".key").c_str(),
                                   A("esc." + label + ".rev").c_str(), sort.c_str(), &projected,
                                   &error);
  if (status != READER_REV_OK) throw std::runtime_error("escape projection failed: " + label);
  char *body = nullptr;
  size_t bytes = 0;
  reader_revision_info stored;
  std::memset(&stored, 0, sizeof stored);
  status = reader_revision_get(store, A("esc." + label + ".rev").c_str(), &body, &bytes,
                               &stored, &error);
  o.rec("esc." + label + ".get");
  o.fn("status", (int)status);
  if (status == READER_REV_OK) {
    o.fn("bytes", (long long)bytes);
    o.fh("hex", body, bytes);
    o.f("sha256", stored.sha256);
    o.f("entity_kind", stored.entity_kind);
    o.f("entity_key", stored.entity_key);
    o.f("operation", stored.operation);
    o.f("book_key", stored.book_key);
    o.fn("source_bytes", (long long)stored.source_bytes);
    o.fn("parent_count", (long long)stored.parent_count);
  }
  if (body) reader_revision_bytes_free(body);
  o.rec("esc." + label + ".proj");
  o.fn("status", 0);
  o.f("revision_id", projected.revision_id);
  o.f("sha256", projected.sha256);
  o.f("entity_key", projected.entity_key);
  book_sink sink;
  begin_sink(sink, false);
  int found = 0;
  o.rec("esc." + label + ".meta");
  reader_catalog_error cerr;
  std::memset(&cerr, 0, sizeof cerr);
  int rc = reader_catalog_metadata(catalog, A("esc." + label + ".key").c_str(), visit_book,
                                   &sink, &found, &cerr);
  o.fn("status", rc);
  o.fn("found", found);
  o.fn("rows", sink.index);
  char *title = nullptr;
  reader_revision_error terr;
  std::memset(&terr, 0, sizeof terr);
  status = reader_revision_book_title(store, A("esc." + label + ".rev").c_str(), &title, &terr);
  o.rec("esc." + label + ".title");
  o.fn("status", (int)status);
  if (status == READER_REV_OK) o.fh("hex", title, std::strlen(title));
  if (title) reader_revision_bytes_free(title);
}

void escape_negative(reader_revisions *store) {
  std::string wire = REF("escwire.esc1");
  std::string zeros(64, '0');
  reader_revision_info info;
  std::memset(&info, 0, sizeof info);
  int created = 0;
  reader_revision_error error;
  std::memset(&error, 0, sizeof error);
  o.rec("esc.neg.bad_sha");
  o.fn("status", (int)reader_revision_receive(store, wire.data(), wire.size(), zeros.c_str(),
                                              &info, &created, &error));
}

int run(const std::string &input, const std::string &output) {
  load(input);

  for (size_t i = 0; i < DOC.item_order.size(); i++) {
    const std::string &name = DOC.item_order[i];
    if (DOC.items[name].kind != 0) continue;
    const std::string &payload = DOC.items[name].payload;
    if (payload.size() % 2 != 0) throw std::runtime_error("odd UTF-16 payload " + name);
    std::vector<uint16_t> units(payload.size() / 2);
    if (!units.empty()) std::memcpy(&units[0], payload.data(), units.size() * 2);
    char buffer[16385];
    size_t bytes = 0;
    reader_command_error error;
    std::memset(&error, 0, sizeof error);
    reader_command_status status = reader_command_utf16(units.empty() ? nullptr : &units[0],
                                                        units.size(), buffer, sizeof buffer,
                                                        &bytes, &error);
    UTF16_ORDER.push_back(name);
    U16_STATUS[name] = (int)status;
    U16_BYTES[name] = bytes;
    U16_HEX[name] = (status == READER_COMMAND_OK) ? hexof(buffer, bytes) : std::string();
    if (status == READER_COMMAND_OK) TEXT[name] = std::string(buffer, bytes);
  }

  for (size_t i = 0; i < UTF16_ORDER.size(); i++) {
    const std::string &name = UTF16_ORDER[i];
    if (name.compare(0, 2, "t.") != 0) continue;
    o.rec("utf16." + name);
    o.fn("status", U16_STATUS[name]);
    o.fn("bytes", (long long)U16_BYTES[name]);
    o.f("hex", U16_HEX[name]);
  }
  {
    const std::string &payload = DOC.items["t.cjk"].payload;
    std::vector<uint16_t> units(payload.size() / 2);
    if (!units.empty()) std::memcpy(&units[0], payload.data(), units.size() * 2);
    char buffer[16385];
    size_t bytes = 0;
    reader_command_error error;
    std::memset(&error, 0, sizeof error);
    reader_command_status status = reader_command_utf16(&units[0], units.size(), buffer, 4,
                                                        &bytes, &error);
    o.rec("utf16.capacity_small");
    o.fn("status", (int)status);
    o.fn("bytes", (long long)bytes);
    o.f("hex", "");
  }
  {
    char buffer[16385];
    size_t bytes = 0;
    reader_command_error error;
    std::memset(&error, 0, sizeof error);
    reader_command_status status = reader_command_utf16(nullptr, 0, buffer, sizeof buffer,
                                                        &bytes, &error);
    o.rec("utf16.null_input");
    o.fn("status", (int)status);
    o.fn("bytes", (long long)bytes);
    o.f("hex", "");
  }

  std::string database = TX("p.db_a");
  reader_revision_error revision_error;
  std::memset(&revision_error, 0, sizeof revision_error);
  reader_revisions *store = nullptr;
  reader_revision_status status = reader_revisions_open(database.c_str(), &store, &revision_error);
  if (status != READER_REV_OK)
    throw std::runtime_error(std::string("open first store failed: ") + revision_error.message);

  reader_catalog *catalog = nullptr;
  reader_catalog_error catalog_error;
  std::memset(&catalog_error, 0, sizeof catalog_error);
  if (reader_catalog_open(database.c_str(), &catalog, &catalog_error) != 0)
    throw std::runtime_error(std::string("open first catalog failed: ") + catalog_error.message);

  attach_all(catalog);
  run_ops(store);
  read_revisions(store, "");
  read_catalog(catalog, "", false);

  std::memset(&catalog_error, 0, sizeof catalog_error);
  if (reader_catalog_close(&catalog, &catalog_error) != 0)
    throw std::runtime_error("catalog close failed");
  std::memset(&revision_error, 0, sizeof revision_error);
  if (reader_revisions_close(&store, &revision_error) != READER_REV_OK)
    throw std::runtime_error("store close failed");

  std::memset(&revision_error, 0, sizeof revision_error);
  status = reader_revisions_open(database.c_str(), &store, &revision_error);
  if (status != READER_REV_OK) throw std::runtime_error("reopen store failed");
  std::memset(&catalog_error, 0, sizeof catalog_error);
  if (reader_catalog_open(database.c_str(), &catalog, &catalog_error) != 0)
    throw std::runtime_error("reopen catalog failed");
  read_revisions(store, "re.");
  read_catalog(catalog, "re.", false);

  /* mirror database: transport, incremental projection, catalog equality */
  std::string mirror_path = TX("p.db_b");
  reader_revisions *mirror = nullptr;
  std::memset(&revision_error, 0, sizeof revision_error);
  status = reader_revisions_open(mirror_path.c_str(), &mirror, &revision_error);
  if (status != READER_REV_OK) throw std::runtime_error("open mirror store failed");
  run_transport(store, mirror);
  transport_negatives(store, mirror);
  reader_catalog *mirror_catalog = nullptr;
  std::memset(&catalog_error, 0, sizeof catalog_error);
  if (reader_catalog_open(mirror_path.c_str(), &mirror_catalog, &catalog_error) != 0)
    throw std::runtime_error("open mirror catalog failed");
  read_catalog(mirror_catalog, "b.", true);
  read_revisions(mirror, "b.");

  /* escape retention database: exact retained bytes, decoded text, no normalization */
  std::string escape_path = TX("p.db_c");
  reader_revisions *escaped = nullptr;
  std::memset(&revision_error, 0, sizeof revision_error);
  status = reader_revisions_open(escape_path.c_str(), &escaped, &revision_error);
  if (status != READER_REV_OK) throw std::runtime_error("open escape store failed");
  escape_negative(escaped);
  for (int i = 0; i < 2; i++) {
    std::string label = i == 0 ? "esc1" : "esc2";
    reader_catalog *escape_catalog = nullptr;
    std::memset(&catalog_error, 0, sizeof catalog_error);
    if (reader_catalog_open(escape_path.c_str(), &escape_catalog, &catalog_error) != 0)
      throw std::runtime_error("open escape catalog failed");
    run_escape(escaped, escape_catalog, label);
    std::memset(&catalog_error, 0, sizeof catalog_error);
    reader_catalog_close(&escape_catalog, &catalog_error);
  }

  std::memset(&catalog_error, 0, sizeof catalog_error);
  reader_catalog_close(&mirror_catalog, &catalog_error);
  std::memset(&revision_error, 0, sizeof revision_error);
  reader_revisions_close(&mirror, &revision_error);
  reader_revisions_close(&escaped, &revision_error);
  std::memset(&catalog_error, 0, sizeof catalog_error);
  reader_catalog_close(&catalog, &catalog_error);
  std::memset(&revision_error, 0, sizeof revision_error);
  if (reader_revisions_close(&store, &revision_error) != READER_REV_OK)
    throw std::runtime_error("final store close failed");

  std::ofstream file(output.c_str(), std::ios::binary);
  if (!file) throw std::runtime_error("cannot write observations");
  file.write(OUT.data(), (std::streamsize)OUT.size());
  file.close();
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  std::string input;
  std::string output;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string flag = argv[i];
    if (flag == "--input") input = argv[i + 1];
    else if (flag == "--output") output = argv[i + 1];
  }
  if (input.empty() || output.empty()) {
    std::fprintf(stderr, "usage: unicode-consumer --input <cases.bin> --output <observations>\n");
    return 2;
  }
  try {
    return run(input, output);
  } catch (const std::exception &failure) {
    std::fprintf(stderr, "PROBE-FAILURE: %s\n", failure.what());
    return 3;
  }
}
