/* SPDX-License-Identifier: MIT
 * S12 Unicode path and library-state regression consumer.
 *
 * C++17 against the installed raw-capability metadata profile
 * (EXReaderProductCatalog 0.1.0, EXReaderRevisions 0.4.0, EXReaderCommands
 * 0.2.0, EXReaderDesktopMetadata 0.2.0) and the unchanged
 * EXReaderAccountProfiles 0.1.0 package. Only installed public headers and
 * public targets are used.
 *
 * Every Unicode text and every Unicode path component travels in the binary
 * request container as UTF-16LE code units and enters through the documented
 * reader_command_utf16 boundary, so argv carries ASCII switches only and no
 * ANSI code page can damage a path.
 */
#include <catalog.h>
#include <reader_account_profiles.h>
#include <reader_commands.h>
#include <reader_metadata.h>
#include <reader_projection.h>
#include <reader_revisions.h>

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

/* ---------------------------------------------------------------- records */
struct observation {
  std::string name;
  std::vector<std::pair<std::string, std::string>> fields;
};
static std::vector<observation> observations;
static size_t current = 0;
static bool have_current = false;

static void record(const char *name) {
  observations.push_back(observation{name, {}});
  current = observations.size() - 1;
  have_current = true;
}
static void field(const std::string &key, const std::string &value) {
  if (!have_current) throw std::runtime_error("field before record");
  observations[current].fields.emplace_back(key, value);
}
static void number(const char *key, long long value) { field(key, std::to_string(value)); }
static std::string literal(const char *value) { return value ? std::string(value) : std::string("<null>"); }
static std::string flag(bool value) { return value ? "1" : "0"; }

static std::string hex(const std::string &bytes) {
  static const char *digits = "0123456789abcdef";
  std::string out;
  out.reserve(bytes.size() * 2);
  for (unsigned char value : bytes) {
    out += digits[value >> 4];
    out += digits[value & 15];
  }
  return out;
}
static std::string hex(const char *bytes) { return bytes ? hex(std::string(bytes)) : std::string("<null>"); }

/* -------------------------------------------------------------- container */
struct item {
  int kind; /* 0 = ASCII, 1 = UTF-16LE units, 2 = UTF-16LE units carrying a NUL */
  std::string bytes;
};
static std::map<std::string, item> items;

static uint32_t read32(const unsigned char *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void load_container(const std::string &path) {
  std::ifstream input(fs::u8path(path), std::ios::binary);
  if (!input) throw std::runtime_error("cannot open the request container");
  std::string blob((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  if (blob.size() < 12 || blob.compare(0, 4, "S121") != 0) throw std::runtime_error("bad container magic");
  const unsigned char *base = (const unsigned char *)blob.data();
  if (read32(base + 4) != 1) throw std::runtime_error("bad container version");
  uint32_t count = read32(base + 8);
  size_t at = 12;
  for (uint32_t index = 0; index < count; ++index) {
    if (at + 4 > blob.size()) throw std::runtime_error("truncated container");
    uint32_t name_length = read32(base + at);
    at += 4;
    if (at + (size_t)name_length + 8 > blob.size()) throw std::runtime_error("truncated container record");
    std::string name(blob.data() + at, name_length);
    at += name_length;
    uint32_t kind = read32(base + at);
    at += 4;
    uint32_t length = read32(base + at);
    at += 4;
    if (at + (size_t)length > blob.size()) throw std::runtime_error("truncated container payload");
    items[name] = item{(int)kind, blob.substr(at, length)};
    at += length;
  }
}
static const item &need(const char *id) {
  auto found = items.find(id);
  if (found == items.end()) throw std::runtime_error(std::string("missing container item ") + id);
  return found->second;
}
static std::string ascii(const char *id) {
  const item &value = need(id);
  if (value.kind != 0) throw std::runtime_error(std::string("container item is not ASCII: ") + id);
  return value.bytes;
}
static long long integer(const char *id) { return std::stoll(ascii(id)); }
static std::vector<uint16_t> units_of(const item &value) {
  if (value.bytes.size() % 2) throw std::runtime_error("odd UTF-16 little-endian payload");
  std::vector<uint16_t> units(value.bytes.size() / 2);
  for (size_t index = 0; index < units.size(); ++index) {
    const unsigned char *pair = (const unsigned char *)value.bytes.data() + index * 2;
    units[index] = (uint16_t)((uint16_t)pair[0] | ((uint16_t)pair[1] << 8));
  }
  return units;
}
static std::string decode(const char *id, int *status_out = nullptr, size_t *bytes_out = nullptr) {
  std::vector<uint16_t> units = units_of(need(id));
  std::vector<char> output(units.size() * 4 + 8);
  size_t bytes = 0;
  reader_command_error error{};
  int status = (int)reader_command_utf16(units.data(), units.size(), output.data(), output.size(), &bytes, &error);
  if (status_out) *status_out = status;
  if (bytes_out) *bytes_out = bytes;
  return status == READER_COMMAND_OK ? std::string(output.data(), bytes) : std::string();
}

/* ------------------------------------------------------------- page rows */
static std::string row_text(const reader_catalog_row *row) {
  return "titlehex=" + hex(row->title) + ";authorhex=" + hex(row->author) + ";sorthex=" + hex(row->sort_title) +
         ";key=" + literal(row->book_key) + ";format=" + literal(row->format) +
         ";bytes=" + std::to_string(row->source_bytes) + ";fav=" + std::to_string(row->favorite) +
         ";sdk=" + std::to_string(row->sdk_book_id) + ";loc=" + literal(row->location_kind) +
         ";deleted=" + std::to_string(row->deleted);
}
struct page {
  std::vector<std::string> rows;
};
static int collect_head(void *context, const reader_revision_head *head) {
  ((std::vector<std::string> *)context)->push_back(std::string(head->revision_id));
  return 0;
}
static int collect_row(void *context, const reader_catalog_row *row) {
  ((page *)context)->rows.push_back(row_text(row));
  return 0;
}
static std::string joined(const page &value) {
  std::string out;
  for (size_t index = 0; index < value.rows.size(); ++index) {
    if (index) out += '|';
    out += value.rows[index];
  }
  return out;
}
static void page_record(const char *name, int status, const page &value, const reader_catalog_error &error) {
  record(name);
  number("status", status);
  number("error", error.code);
  number("rows", (long long)value.rows.size());
  field("joined", joined(value));
}
/* Split one delivered row back into the sort_title bytes and the book key. */
static void cursor_of(const std::string &row, std::string *title, std::string *key) {
  size_t sort_at = row.find("sorthex=");
  size_t key_at = row.find(";key=");
  if (sort_at == std::string::npos || key_at == std::string::npos) throw std::runtime_error("row without cursor");
  std::string encoded = row.substr(sort_at + 8, row.find(';', sort_at) - sort_at - 8);
  title->clear();
  for (size_t index = 0; index + 1 < encoded.size(); index += 2)
    title->push_back((char)std::stoi(encoded.substr(index, 2), nullptr, 16));
  *key = row.substr(key_at + 5, row.find(';', key_at + 5) - key_at - 5);
}

static bool same_file(const fs::path &left, const fs::path &right, std::string *why) {
  std::error_code code;
  if (!fs::is_regular_file(left, code) || !fs::is_regular_file(right, code)) {
    if (why) *why = "missing snapshot";
    return false;
  }
  if (fs::file_size(left, code) != fs::file_size(right, code)) {
    if (why) *why = "size differs";
    return false;
  }
  std::ifstream a(left, std::ios::binary), b(right, std::ios::binary);
  std::string x((std::istreambuf_iterator<char>(a)), std::istreambuf_iterator<char>());
  std::string y((std::istreambuf_iterator<char>(b)), std::istreambuf_iterator<char>());
  if (x != y) {
    if (why) *why = "bytes differ";
    return false;
  }
  return true;
}

struct workspace {
  fs::path root, base, library, originals, accounts, snapshots;
  fs::path main_db, mirror_db, probe_db, pending;
};
static void snapshot(const workspace &where, const fs::path &source, const char *label) {
  std::error_code code;
  if (!fs::is_regular_file(source, code)) throw std::runtime_error(std::string("snapshot source missing: ") + label);
  fs::create_directories(where.snapshots, code);
  fs::copy_file(source, where.snapshots / (std::string(label) + ".bin"), fs::copy_options::overwrite_existing, code);
  if (code) throw std::runtime_error(std::string("snapshot failed: ") + label);
}
static void stability_record(const char *name, const workspace &where, const char *left, const char *right) {
  std::string why;
  bool equal = same_file(where.snapshots / (std::string(left) + ".bin"), where.snapshots / (std::string(right) + ".bin"),
                         &why);
  record(name);
  field("equal", flag(equal));
  field("reason", equal ? std::string("identical") : why);
}

/* ------------------------------------------------------------- book input */
struct book_fixture {
  std::string key, format, sha, title, author, sort, location;
  uint64_t bytes = 0;
  int favorite = 0;
  int64_t sdk = 0;
};
static book_fixture book(const char *prefix) {
  std::string name(prefix);
  book_fixture value;
  value.key = ascii((name + ".key").c_str());
  value.format = ascii((name + ".format").c_str());
  value.sha = ascii((name + ".sha").c_str());
  value.location = ascii((name + ".loc").c_str());
  value.bytes = (uint64_t)integer((name + ".bytes").c_str());
  value.favorite = (int)integer((name + ".fav").c_str());
  value.sdk = integer((name + ".sdk").c_str());
  value.title = decode((name + ".title").c_str());
  value.author = decode((name + ".author").c_str());
  value.sort = decode((name + ".sort").c_str());
  return value;
}
static reader_catalog_book catalog_book(const book_fixture &value) {
  reader_catalog_book input{};
  input.format = value.format.c_str();
  input.sha256 = value.sha.c_str();
  input.title = value.title.c_str();
  input.author = value.author.c_str();
  input.sort_title = value.sort.c_str();
  input.source_bytes = value.bytes;
  input.sdk_book_id = value.sdk;
  input.favorite = value.favorite;
  input.location_kind = value.location.c_str();
  return input;
}
static int attach_book(reader_catalog *catalog, const book_fixture &value, reader_catalog_error *error) {
  reader_catalog_book input = catalog_book(value);
  return reader_catalog_attach(catalog, &input, error);
}

int main(int argc, char **argv) {
  try {
    std::string input_path, root_path, output_path, local_path;
    for (int index = 1; index + 1 < argc; index += 2) {
      std::string switch_name = argv[index];
      if (switch_name == "--input") input_path = argv[index + 1];
      else if (switch_name == "--root") root_path = argv[index + 1];
      else if (switch_name == "--output") output_path = argv[index + 1];
      else if (switch_name == "--local") local_path = argv[index + 1];
      else return 2;
    }
    if (input_path.empty() || root_path.empty() || output_path.empty()) return 2;

    load_container(input_path);

    workspace where;
    where.root = fs::absolute(fs::u8path(root_path));
    where.base = where.root / fs::u8path(decode("dir.workspace")) / fs::u8path(decode("dir.space"));
    where.library = where.base / fs::u8path(decode("dir.library"));
    where.originals = where.library / fs::u8path(decode("dir.book"));
    where.accounts = where.base / fs::u8path(decode("dir.accounts"));
    where.snapshots = where.root / "snapshots";
    where.main_db = where.library / fs::u8path(decode("file.main"));
    where.mirror_db = where.library / fs::u8path(decode("file.mirror"));
    where.probe_db = where.originals / fs::u8path(decode("file.probe"));
    where.pending = where.library / fs::u8path(decode("file.pending"));
    std::error_code fs_error;
    fs::create_directories(where.library, fs_error);
    fs::create_directories(where.originals, fs_error);
    fs::create_directories(where.accounts, fs_error);
    fs::create_directories(where.snapshots, fs_error);
    if (fs_error) throw std::runtime_error("cannot create the Unicode workspace");

    /* --------------------------------------------------------- UTF-16 area */
    static const char *const conversions[] = {
        "dir.workspace", "dir.space",  "dir.library",     "dir.book",      "dir.accounts",
        "file.main",     "file.mirror", "file.probe",     "file.long",     "file.pending",
        "title.nfc",     "title.nfd",  "title.upper",     "title.spaces",  "title.tab",
        "title.quotes",  "title.long", "author.ascii",    "author.cjk",    "author.upper",
        "author.empty",  "title.empty", "account.name.nfc", "account.name.nfd",
        "account.name.upper", "account.name.lower", "account.name.rename"};
    for (const char *id : conversions) {
      int status = 0;
      size_t bytes = 0;
      std::string value = decode(id, &status, &bytes);
      record((std::string("utf16.") + id).c_str());
      number("status", status);
      number("bytes", (long long)bytes);
      field("hex", hex(value));
    }
    {
      std::vector<uint16_t> units = units_of(need("nul.product"));
      std::vector<char> output(units.size() * 4 + 8);
      size_t bytes = 999;
      reader_command_error error{};
      int status = (int)reader_command_utf16(units.data(), units.size(), output.data(), output.size(), &bytes, &error);
      record("utf16.nul.rejected");
      number("status", status);
      number("bytes", (long long)bytes);
      field("hex", hex(std::string(output.data(), bytes)));
    }
    for (const char *name : {"utf16.surrogate.high", "utf16.surrogate.low"}) {
      std::vector<uint16_t> units = units_of(need(name));
      char output[64];
      size_t bytes = 999;
      reader_command_error error{};
      int status = (int)reader_command_utf16(units.data(), units.size(), output, sizeof(output), &bytes, &error);
      record(name);
      number("status", status);
      number("bytes", (long long)bytes);
      field("hex", hex(std::string(output, status == 0 ? bytes : 0)));
    }
    {
      std::vector<uint16_t> units = units_of(need("utf16.pair"));
      std::string expected = decode("utf16.pair");
      char output[16];
      size_t bytes = 999;
      reader_command_error error{};
      int status = (int)reader_command_utf16(units.data(), units.size(), output, sizeof(output), &bytes, &error);
      record("utf16.nonbmp.pair");
      number("status", status);
      number("bytes", (long long)bytes);
      field("hex", hex(std::string(output, bytes)));
      int short_status = (int)reader_command_utf16(units.data(), units.size(), output, expected.size(), &bytes, &error);
      record("utf16.capacity.short");
      number("status", short_status);
      number("bytes", (long long)bytes);
      int exact = (int)reader_command_utf16(units.data(), units.size(), output, expected.size() + 1, &bytes, &error);
      record("utf16.capacity.exact");
      number("status", exact);
      number("bytes", (long long)bytes);
      field("hex", hex(std::string(output, exact == 0 ? bytes : 0)));
    }
    {
      std::vector<uint16_t> units(16385, (uint16_t)'a');
      std::vector<char> output(units.size() * 4 + 8);
      size_t bytes = 999;
      reader_command_error error{};
      int status = (int)reader_command_utf16(units.data(), units.size(), output.data(), output.size(), &bytes, &error);
      record("utf16.units.over");
      number("status", status);
      number("bytes", (long long)bytes);
    }
    {
      char output[8];
      size_t bytes = 999;
      reader_command_error error{};
      int status = (int)reader_command_utf16(nullptr, 0, output, sizeof(output), &bytes, &error);
      record("utf16.null.zero");
      number("status", status);
      number("bytes", (long long)bytes);
      field("hex", hex(std::string(output, status == 0 ? bytes : 0)));
    }
    {
      int status = 0;
      size_t bytes = 0;
      std::string value = decode("utf16.long", &status, &bytes);
      record("utf16.long");
      number("status", status);
      number("bytes", (long long)bytes);
      field("hex", hex(value));
    }

    /* -------------------------------------------------- account isolation */
    {
      reader_account_profiles_error error{};
      error.struct_size = sizeof(error);
      reader_account_profile first{};
      first.struct_size = sizeof(first);
      std::snprintf(first.profile_id, sizeof(first.profile_id), "%s", ascii("account.id.1").c_str());
      std::snprintf(first.account_id, sizeof(first.account_id), "%s", ascii("account.acct.1").c_str());
      std::snprintf(first.root_url, sizeof(first.root_url), "%s", ascii("account.url.one").c_str());
      std::snprintf(first.display_name, sizeof(first.display_name), "%s", decode("account.name.nfc").c_str());
      const std::string store = where.accounts.u8string();

      record("account.validate.nfc");
      number("status", (int)reader_account_profiles_validate(&first, &error));

      uint64_t generation = 0;
      record("account.add.nfc");
      number("status", (int)reader_account_profiles_add(store.c_str(), &first, nullptr, &generation, &error));
      field("generation", std::to_string(generation));

      reader_account_profile second = first;
      std::snprintf(second.profile_id, sizeof(second.profile_id), "%s", ascii("account.id.2").c_str());
      std::snprintf(second.account_id, sizeof(second.account_id), "%s", ascii("account.acct.2").c_str());
      std::snprintf(second.root_url, sizeof(second.root_url), "%s", ascii("account.url.two").c_str());
      std::snprintf(second.display_name, sizeof(second.display_name), "%s", decode("account.name.nfd").c_str());
      record("account.add.nfd");
      number("status", (int)reader_account_profiles_add(store.c_str(), &second, nullptr, &generation, &error));
      field("generation", std::to_string(generation));

      reader_account_profile third = first;
      std::snprintf(third.profile_id, sizeof(third.profile_id), "%s", ascii("account.id.3").c_str());
      std::snprintf(third.account_id, sizeof(third.account_id), "%s", ascii("account.acct.3").c_str());
      std::snprintf(third.root_url, sizeof(third.root_url), "%s", ascii("account.url.three").c_str());
      std::snprintf(third.display_name, sizeof(third.display_name), "%s", decode("account.name.upper").c_str());
      record("account.add.upper");
      number("status", (int)reader_account_profiles_add(store.c_str(), &third, nullptr, &generation, &error));
      field("generation", std::to_string(generation));

      reader_account_profile fourth = third;
      std::snprintf(fourth.profile_id, sizeof(fourth.profile_id), "%s", ascii("account.id.4").c_str());
      std::snprintf(fourth.account_id, sizeof(fourth.account_id), "%s", ascii("account.acct.4").c_str());
      std::snprintf(fourth.root_url, sizeof(fourth.root_url), "%s", ascii("account.url.four").c_str());
      std::snprintf(fourth.display_name, sizeof(fourth.display_name), "%s", decode("account.name.lower").c_str());
      record("account.add.lower");
      number("status", (int)reader_account_profiles_add(store.c_str(), &fourth, nullptr, &generation, &error));
      field("generation", std::to_string(generation));

      std::vector<char> storage(sizeof(reader_account_profiles_list) + 64);
      reader_account_profiles_list *list = (reader_account_profiles_list *)storage.data();
      std::memset(list, 0, storage.size());
      list->struct_size = sizeof(reader_account_profiles_list);
      int loaded = (int)reader_account_profiles_load(store.c_str(), list, nullptr, &error);
      record("account.load.base");
      number("status", loaded);
      number("count", (long long)list->count);
      field("generation", std::to_string(list->generation));
      for (uint32_t index = 0; index < list->count && index < 4; ++index) {
        field("name." + std::to_string(index), hex(list->profiles[index].display_name));
        field("id." + std::to_string(index), literal(list->profiles[index].profile_id));
      }

      reader_account_profile duplicate = first;
      std::snprintf(duplicate.profile_id, sizeof(duplicate.profile_id), "%s", ascii("account.id.5").c_str());
      record("account.add.duplicate_pair");
      number("status", (int)reader_account_profiles_add(store.c_str(), &duplicate, nullptr, &generation, &error));
      std::memset(list, 0, storage.size());
      list->struct_size = sizeof(reader_account_profiles_list);
      reader_account_profiles_load(store.c_str(), list, nullptr, &error);
      number("count_after", (long long)list->count);
      field("generation_after", std::to_string(list->generation));

      reader_account_profile probe_profile = second;
      std::snprintf(probe_profile.profile_id, sizeof(probe_profile.profile_id), "%s", ascii("account.id.6").c_str());
      std::snprintf(probe_profile.account_id, sizeof(probe_profile.account_id), "%s", ascii("account.acct.6").c_str());
      std::snprintf(probe_profile.root_url, sizeof(probe_profile.root_url), "%s", ascii("account.url.secret").c_str());
      record("account.validate.userinfo");
      number("status", (int)reader_account_profiles_validate(&probe_profile, &error));
      std::snprintf(probe_profile.root_url, sizeof(probe_profile.root_url), "%s", ascii("account.url.query").c_str());
      record("account.validate.query");
      number("status", (int)reader_account_profiles_validate(&probe_profile, &error));
      std::snprintf(probe_profile.root_url, sizeof(probe_profile.root_url), "%s", ascii("account.url.http").c_str());
      record("account.validate.http");
      number("status", (int)reader_account_profiles_validate(&probe_profile, &error));
      std::snprintf(probe_profile.root_url, sizeof(probe_profile.root_url), "%s", ascii("account.url.space").c_str());
      record("account.validate.space");
      number("status", (int)reader_account_profiles_validate(&probe_profile, &error));
      std::snprintf(probe_profile.root_url, sizeof(probe_profile.root_url), "%s", ascii("account.url.two").c_str());
      std::snprintf(probe_profile.display_name, sizeof(probe_profile.display_name), "%s", "");
      record("account.validate.empty_name");
      number("status", (int)reader_account_profiles_validate(&probe_profile, &error));

      auto relative = [&store](const char *path) {
        std::string value = path;
        std::replace(value.begin(), value.end(), '\\', '/');
        std::string prefix = store;
        std::replace(prefix.begin(), prefix.end(), '\\', '/');
        if (value.compare(0, prefix.size(), prefix) == 0) value = value.substr(prefix.size());
        while (!value.empty() && value[0] == '/') value.erase(value.begin());
        return value;
      };
      std::vector<char> one_storage(sizeof(reader_account_profiles_activation) + 64);
      std::vector<char> two_storage(sizeof(reader_account_profiles_activation) + 64);
      reader_account_profiles_activation *plan_one = (reader_account_profiles_activation *)one_storage.data();
      reader_account_profiles_activation *plan_two = (reader_account_profiles_activation *)two_storage.data();
      std::memset(plan_one, 0, one_storage.size());
      plan_one->struct_size = sizeof(reader_account_profiles_activation);
      int one_status = (int)reader_account_profiles_prepare_activation(store.c_str(), ascii("account.id.1").c_str(),
                                                                      nullptr, plan_one, &error);
      record("account.plan.one");
      number("status", one_status);
      field("product", relative(plan_one->product_path));
      field("private", relative(plan_one->private_directory));
      field("originals", relative(plan_one->original_directory));
      field("profile", literal(plan_one->profile.profile_id));

      std::memset(plan_two, 0, two_storage.size());
      plan_two->struct_size = sizeof(reader_account_profiles_activation);
      int two_status = (int)reader_account_profiles_prepare_activation(store.c_str(), ascii("account.id.2").c_str(),
                                                                      nullptr, plan_two, &error);
      record("account.plan.two");
      number("status", two_status);
      field("product", relative(plan_two->product_path));
      field("distinct", flag(one_status == 0 && two_status == 0 &&
                             std::string(plan_one->product_path) != std::string(plan_two->product_path) &&
                             std::string(plan_one->private_directory) != std::string(plan_two->private_directory)));

      record("account.plan.verify");
      number("status", (int)reader_account_profiles_verify_activation(store.c_str(), plan_one, nullptr, &error));
      std::string tampered = plan_one->product_path;
      tampered += "x";
      std::snprintf(plan_one->product_path, sizeof(plan_one->product_path), "%s", tampered.c_str());
      record("account.plan.tampered");
      number("status", (int)reader_account_profiles_verify_activation(store.c_str(), plan_one, nullptr, &error));

      record("account.rename");
      number("status", (int)reader_account_profiles_rename(store.c_str(), ascii("account.id.4").c_str(),
                                                          decode("account.name.rename").c_str(), nullptr, &generation,
                                                          &error));
      field("generation", std::to_string(generation));
      std::memset(list, 0, storage.size());
      list->struct_size = sizeof(reader_account_profiles_list);
      reader_account_profiles_load(store.c_str(), list, nullptr, &error);
      field("name.3", hex(list->profiles[3].display_name));

      record("account.remove");
      number("status", (int)reader_account_profiles_remove(store.c_str(), ascii("account.id.4").c_str(), nullptr,
                                                          &generation, &error));
      field("generation", std::to_string(generation));
      std::memset(list, 0, storage.size());
      list->struct_size = sizeof(reader_account_profiles_list);
      reader_account_profiles_load(store.c_str(), list, nullptr, &error);
      number("count_after", (long long)list->count);

      record("account.store.relative");
      number("status", (int)reader_account_profiles_load("s12-relative", list, nullptr, &error));

      /* An embedded NUL cannot name the isolated store. The truncated prefix is a
       * directory this run never created, so a silent adoption would show up. */
      fs::path nul_store = where.accounts.parent_path() / fs::u8path(decode("dir.accounts") + "-nul");
      std::string nul_store_bytes = nul_store.u8string();
      nul_store_bytes.push_back('\0');
      nul_store_bytes += "tail";
      reader_account_profile nul_profile = first;
      std::snprintf(nul_profile.profile_id, sizeof(nul_profile.profile_id), "%s", ascii("account.id.7").c_str());
      std::snprintf(nul_profile.account_id, sizeof(nul_profile.account_id), "%s", ascii("account.acct.7").c_str());
      record("account.nul.store");
      number("status", (int)reader_account_profiles_add(nul_store_bytes.c_str(), &nul_profile, nullptr, &generation,
                                                        &error));
      field("truncated_created", flag(fs::exists(nul_store)));
    }

    /* ------------------------------------------------ original book entry */
    const book_fixture books[6] = {book("book.1"), book("book.2"), book("book.3"),
                                   book("book.4"), book("book.5"), book("book.6")};
    const book_fixture &book_one = books[0];

    reader_catalog *catalog = nullptr;
    reader_catalog_error catalog_error{};
    int status = reader_catalog_open(where.main_db.u8string().c_str(), &catalog, &catalog_error);
    record("attach.open");
    number("status", status);
    number("error", catalog_error.code);
    if (status != 0) throw std::runtime_error("the product catalog did not open on a Unicode path");
    for (int index = 0; index < 6; ++index) {
      record((std::string("attach.seed.") + std::to_string(index + 1)).c_str());
      number("status", attach_book(catalog, books[index], &catalog_error));
      number("error", catalog_error.code);
    }
    {
      page all;
      reader_catalog_error error{};
      page_record("attach.page.all", reader_catalog_page(catalog, nullptr, nullptr, 200, collect_row, &all, &error),
                  all, error);
    }
    {
      page first_page;
      reader_catalog_error error{};
      int first_status = reader_catalog_page(catalog, nullptr, nullptr, 2, collect_row, &first_page, &error);
      page_record("attach.page.forward.0", first_status, first_page, error);
      std::string title, key;
      int second_status = -1, third_status = -1;
      page second_page, third_page;
      reader_catalog_error second_error{}, third_error{};
      if (first_page.rows.size() == 2) {
        cursor_of(first_page.rows.back(), &title, &key);
        second_status = reader_catalog_page(catalog, title.c_str(), key.c_str(), 2, collect_row, &second_page,
                                           &second_error);
        if (second_page.rows.size() == 2) {
          cursor_of(second_page.rows.back(), &title, &key);
          third_status = reader_catalog_page(catalog, title.c_str(), key.c_str(), 2, collect_row, &third_page,
                                            &third_error);
        }
      }
      page_record("attach.page.forward.1", second_status, second_page, second_error);
      page_record("attach.page.forward.2", third_status, third_page, third_error);
    }
    {
      page tail;
      reader_catalog_error error{};
      int tail_status = reader_catalog_query_page(catalog, nullptr, nullptr, nullptr, -1, 200, collect_row, &tail, &error);
      page_record("attach.page.reverse.all", tail_status, tail, error);
      page first_page;
      reader_catalog_error first_error{};
      int first_status = reader_catalog_query_page(catalog, nullptr, nullptr, nullptr, -1, 2, collect_row, &first_page,
                                                  &first_error);
      page_record("attach.page.reverse.0", first_status, first_page, first_error);
      std::string title, key;
      int next_status = -1;
      page next;
      reader_catalog_error next_error{};
      if (first_page.rows.size() == 2) {
        cursor_of(first_page.rows.back(), &title, &key);
        next_status = reader_catalog_query_page(catalog, title.c_str(), key.c_str(), nullptr, -1, 2, collect_row, &next,
                                                &next_error);
      }
      page_record("attach.page.reverse.1", next_status, next, next_error);
    }
    auto query_record = [&](const char *name, const char *query_id, int query_kind) {
      std::string value;
      const char *pointer = nullptr;
      if (query_kind == 1) {
        value = decode(query_id);
        pointer = value.c_str();
      } else if (query_kind == 2) {
        value = ascii(query_id);
        pointer = value.c_str();
      } else if (query_kind == 3) {
        value = "";
        pointer = value.c_str();
      }
      page found;
      reader_catalog_error error{};
      int result = reader_catalog_query_page(catalog, nullptr, nullptr, pointer, 1, 200, collect_row, &found, &error);
      page_record(name, result, found, error);
    };
    query_record("attach.query.ascii", "query.ascii", 1);
    query_record("attach.query.unicode", "query.unicode", 1);
    query_record("attach.query.nfd", "book.2.title", 1);
    query_record("attach.query.empty", "", 3);
    query_record("attach.query.null", "", 4);
    auto canonical_record = [&](const char *name, const std::string *nfc, const std::string *nfd) {
      page found;
      reader_catalog_error error{};
      int result = reader_catalog_local_canonical_page(catalog, nullptr, nullptr, nfc ? nfc->c_str() : nullptr,
                                                       nfd ? nfd->c_str() : nullptr, 1, 0, 200, collect_row, &found,
                                                       &error);
      page_record(name, result, found, error);
    };
    const std::string nfc = books[0].sort, nfd = books[1].sort, empty_text;
    canonical_record("attach.canonical.nfc", &nfc, &nfd);
    canonical_record("attach.canonical.nfd", &nfd, &nfc);
    canonical_record("attach.canonical.null", nullptr, &nfd);
    canonical_record("attach.canonical.empty", &empty_text, &empty_text);
    {
      page found;
      reader_catalog_error error{};
      int present = -1;
      int result = reader_catalog_local_lookup(catalog, books[2].sdk, nullptr, collect_row, &found, &present, &error);
      record("attach.lookup.id");
      number("status", result);
      number("found", present);
      number("rows", (long long)found.rows.size());
      field("joined", joined(found));
      page by_title;
      reader_catalog_error title_error{};
      int title_present = -1;
      int title_status = reader_catalog_local_lookup(catalog, 0, books[3].title.c_str(), collect_row, &by_title,
                                                    &title_present, &title_error);
      record("attach.lookup.title");
      number("status", title_status);
      number("found", title_present);
      number("rows", (long long)by_title.rows.size());
      field("joined", joined(by_title));
      page missing;
      reader_catalog_error missing_error{};
      int missing_present = -1;
      int missing_status = reader_catalog_local_lookup(catalog, 0, nullptr, collect_row, &missing, &missing_present,
                                                      &missing_error);
      record("attach.lookup.null");
      number("status", missing_status);
      number("found", missing_present);
      page empty_name;
      reader_catalog_error empty_error{};
      int empty_present = -1;
      int empty_status = reader_catalog_local_lookup(catalog, 0, "", collect_row, &empty_name, &empty_present,
                                                    &empty_error);
      record("attach.lookup.empty");
      number("status", empty_status);
      number("found", empty_present);
      number("rows", (long long)empty_name.rows.size());
    }
    auto metadata_of = [&](const char *name, const std::string &key) {
      page found;
      reader_catalog_error error{};
      int present = -1;
      int result = reader_catalog_metadata(catalog, key.c_str(), collect_row, &found, &present, &error);
      record(name);
      number("status", result);
      number("found", present);
      number("rows", (long long)found.rows.size());
      field("joined", joined(found));
    };
    metadata_of("attach.metadata.one", books[0].key);
    metadata_of("attach.metadata.two", books[1].key);
    metadata_of("attach.metadata.three", books[2].key);
    metadata_of("attach.metadata.missing", "txt:" + std::string(64, '0'));
    {
      page found;
      reader_catalog_error error{};
      int present = -1;
      record("attach.metadata.null");
      number("status", reader_catalog_metadata(catalog, nullptr, collect_row, &found, &present, &error));
      number("found", present);
      record("attach.metadata.empty");
      number("status", reader_catalog_metadata(catalog, "", collect_row, &found, &present, &error));
      number("found", present);
    }
    snapshot(where, where.main_db, "main.after_seed");
    record("attach.repeat");
    number("status", attach_book(catalog, books[0], &catalog_error));
    number("error", catalog_error.code);
    snapshot(where, where.main_db, "main.after_reattach");
    stability_record("stability.main.reattach", where, "main.after_seed", "main.after_reattach");
    reader_catalog_close(&catalog, &catalog_error);

    /* ------------------------------------------- raw metadata 0.2 profile */
    record("metadata.version");
    field("metadata", READER_METADATA_VERSION);
    field("revisions", READER_REVISIONS_VERSION);
    field("commands", READER_COMMANDS_VERSION);
    field("raw", flag(std::string(READER_METADATA_VERSION) == "0.2.0"));

    reader_metadata_owner *owner = nullptr;
    reader_metadata_error metadata_error{};
    record("metadata.open.legacy");
    number("status", (int)reader_metadata_open(where.main_db.u8string().c_str(), where.pending.u8string().c_str(),
                                               &owner, &metadata_error));
    number("handle", owner ? 1 : 0);
    if (owner) reader_metadata_close(&owner, &metadata_error);
    record("metadata.open.raw");
    number("status", (int)reader_metadata_open_raw_v3(where.main_db.u8string().c_str(),
                                                      where.pending.u8string().c_str(), &owner, &metadata_error));
    if (!owner) throw std::runtime_error("the raw metadata profile did not open");
    record("metadata.open.same_path");
    {
      reader_metadata_owner *same = nullptr;
      number("status", (int)reader_metadata_open_raw_v3(where.main_db.u8string().c_str(),
                                                        where.main_db.u8string().c_str(), &same, &metadata_error));
      number("handle", same ? 1 : 0);
      if (same) reader_metadata_close(&same, &metadata_error);
    }
    record("metadata.open.second");
    {
      reader_metadata_owner *second = nullptr;
      number("status", (int)reader_metadata_open_raw_v3(where.main_db.u8string().c_str(),
                                                        where.pending.u8string().c_str(), &second, &metadata_error));
      number("handle", second ? 1 : 0);
      if (second) reader_metadata_close(&second, &metadata_error);
    }

    auto view_fields = [](const reader_metadata_view *view) {
      if (!view) {
        field("present", "-1");
        return;
      }
      number("present", view->present);
      number("deleted", view->deleted);
      number("needs_bootstrap", view->needs_bootstrap);
      number("heads", (long long)view->head_count);
      field("titlehex", hex(view->book.title));
      field("authorhex", hex(view->book.author));
      field("sorthex", hex(view->book.sort_title));
      field("author_null", flag(view->book.author == nullptr));
    };

    reader_metadata_snapshot *prepared = nullptr;
    record("metadata.prepare.book1.bootstrap");
    number("status", (int)reader_metadata_prepare_book(owner, book_one.key.c_str(), &prepared, &metadata_error));
    view_fields(reader_metadata_snapshot_view(prepared));
    reader_metadata_result metadata_result{};
    record("metadata.stage.book1.ordinary");
    {
      reader_book_command input{READER_COMMAND_PUT, book_one.key.c_str(), book_one.format.c_str(),
                                book_one.sha.c_str(), book_one.title.c_str(), book_one.author.c_str(),
                                book_one.sort.c_str(), book_one.bytes, book_one.favorite};
      number("status", (int)reader_metadata_stage_book(owner, prepared, &input, &metadata_result, &metadata_error));
      number("error", (int)metadata_error.code);
    }
    record("metadata.pending.none");
    number("status", (int)reader_metadata_pending(owner, &metadata_result, &metadata_error));
    record("metadata.stage.book1.badsource");
    {
      const std::string wrong_sha(64, 'b');
      reader_metadata_verified_source source{book_one.format.c_str(), wrong_sha.c_str(), book_one.bytes};
      number("status", (int)reader_metadata_stage_bootstrap(owner, prepared, &source, &metadata_result,
                                                           &metadata_error));
      number("error", (int)metadata_error.code);
    }
    record("metadata.stage.book1.bootstrap");
    {
      reader_metadata_verified_source source{book_one.format.c_str(), book_one.sha.c_str(), book_one.bytes};
      number("status", (int)reader_metadata_stage_bootstrap(owner, prepared, &source, &metadata_result,
                                                           &metadata_error));
      number("revision_len", (long long)std::strlen(metadata_result.command.revision_id));
      field("key", literal(metadata_result.command.entity_key));
    }
    const std::string revision_one = metadata_result.command.revision_id;
    reader_metadata_snapshot_free(prepared);
    prepared = nullptr;
    snapshot(where, where.pending, "sidecar.staged");
    record("metadata.pending.staged");
    {
      reader_metadata_result staged{};
      int pending_status = (int)reader_metadata_pending(owner, &staged, &metadata_error);
      number("status", pending_status);
      number("pending", staged.pending);
      number("committed", staged.committed);
      field("same_revision", flag(std::string(staged.command.revision_id) == revision_one));
    }
    record("metadata.apply.book1");
    {
      reader_metadata_result applied{};
      int apply_status = (int)reader_metadata_apply_pending(owner, &applied, &metadata_error);
      number("status", apply_status);
      number("committed", applied.committed);
      number("created", applied.command.created);
    }
    /* Reopen with the durable intent still queued: the journal bytes must not move. */
    reader_metadata_close(&owner, &metadata_error);
    owner = nullptr;
    record("metadata.reopen.pending");
    {
      int reopened = (int)reader_metadata_open_raw_v3(where.main_db.u8string().c_str(),
                                                      where.pending.u8string().c_str(), &owner, &metadata_error);
      number("status", reopened);
      number("sidecar_present", (int)fs::exists(where.pending));
      if (reopened == 0) {
        reader_metadata_result pending{};
        number("pending_status", (int)reader_metadata_pending(owner, &pending, &metadata_error));
        number("pending", pending.pending);
        field("same_revision", flag(std::string(pending.command.revision_id) == revision_one));
      }
      snapshot(where, where.pending, "sidecar.reopened");
      stability_record("stability.sidecar", where, "sidecar.staged", "sidecar.reopened");
      reader_metadata_result finished{};
      record("metadata.finish.book1");
      number("status", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      number("committed", finished.committed);
      number("pending", finished.pending);
      number("sidecar_absent", (int)!fs::exists(where.pending));
      record("metadata.pending.after_finish");
      {
        reader_metadata_result pending{};
        number("status", (int)reader_metadata_pending(owner, &pending, &metadata_error));
        number("pending", pending.pending);
      }
      record("metadata.prepare.book1.after");
      reader_metadata_snapshot *after = nullptr;
      number("status", (int)reader_metadata_prepare_book(owner, book_one.key.c_str(), &after, &metadata_error));
      const reader_metadata_view *view = reader_metadata_snapshot_view(after);
      view_fields(view);
      field("head_matches", flag(view && view->head_count == 1 && std::string(view->heads[0]) == revision_one));
      reader_metadata_snapshot_free(after);
    }

    /* The exact retained wire, read through the shared installed store. */
    reader_revisions *shared = nullptr;
    reader_revision_error revision_error{};
    record("metadata.shared.open");
    number("status", (int)reader_revisions_open_raw_v3(where.main_db.u8string().c_str(), &shared, &revision_error));
    if (!shared) throw std::runtime_error("the shared revision store did not open");
    std::string wire_one, wire_digest;
    {
      char *wire = nullptr;
      size_t wire_bytes = 0;
      reader_revision_info info{};
      int get_status = (int)reader_revision_get_raw_v3(shared, revision_one.c_str(), &wire, &wire_bytes, &info,
                                                       &revision_error);
      record("metadata.get.book1");
      number("status", get_status);
      number("bytes", (long long)wire_bytes);
      field("entity", literal(info.entity_kind));
      field("operation", literal(info.operation));
      number("parents", (long long)info.parent_count);
      field("book_key", literal(info.book_key));
      /* The assigned revision ID is random by contract, so the exact bytes are
       * recorded separately and reconstructed structurally by the checker. */
      record("metadata.wire.book1");
      field("revision", literal(info.revision_id));
      field("sha", literal(info.sha256));
      field("hex", wire ? hex(std::string(wire, wire_bytes)) : std::string("<null>"));
      wire_digest.assign(info.sha256);
      if (wire) wire_one.assign(wire, wire_bytes);
      reader_revision_bytes_free(wire);
    }

    /* Empty author is a real value; a NULL author is refused. */
    {
      record("metadata.book4.bootstrap");
      reader_metadata_snapshot *fresh = nullptr;
      int prepare_status = (int)reader_metadata_prepare_book(owner, books[3].key.c_str(), &fresh, &metadata_error);
      number("prepare", prepare_status);
      reader_metadata_result staged{};
      int stage_status = -1;
      if (fresh && prepare_status == READER_METADATA_NEEDS_BOOTSTRAP) {
        reader_metadata_verified_source source{books[3].format.c_str(), books[3].sha.c_str(), books[3].bytes};
        stage_status = (int)reader_metadata_stage_bootstrap(owner, fresh, &source, &staged, &metadata_error);
      }
      number("stage", stage_status);
      number("revision_len", (long long)std::strlen(staged.command.revision_id));
      reader_metadata_result finished{};
      if (stage_status == 0) number("finish", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;
      record("metadata.book4.null_author");
      int after_prepare = (int)reader_metadata_prepare_book(owner, books[3].key.c_str(), &fresh, &metadata_error);
      number("prepare", after_prepare);
      if (fresh) {
        reader_book_command input{READER_COMMAND_PUT, books[3].key.c_str(), books[3].format.c_str(),
                                  books[3].sha.c_str(), books[3].title.c_str(), nullptr, books[3].sort.c_str(),
                                  books[3].bytes, books[3].favorite};
        number("status", (int)reader_metadata_stage_book(owner, fresh, &input, &staged, &metadata_error));
        number("error", (int)metadata_error.code);
      }
      record("metadata.book4.empty_author");
      int empty_status = -1;
      if (fresh) {
        reader_book_command input{READER_COMMAND_PUT, books[3].key.c_str(), books[3].format.c_str(),
                                  books[3].sha.c_str(), books[3].title.c_str(), "", books[3].sort.c_str(),
                                  books[3].bytes, books[3].favorite};
        empty_status = (int)reader_metadata_stage_book(owner, fresh, &input, &staged, &metadata_error);
        number("status", empty_status);
        number("revision_len", (long long)std::strlen(staged.command.revision_id));
        if (empty_status == 0)
          number("finish", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      }
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;
      record("metadata.book4.view");
      int view_status = (int)reader_metadata_prepare_book(owner, books[3].key.c_str(), &fresh, &metadata_error);
      number("status", view_status);
      if (fresh) {
        const reader_metadata_view *view = reader_metadata_snapshot_view(fresh);
        field("authorhex", hex(view->book.author));
        field("author_null", flag(view->book.author == nullptr));
        number("heads", (long long)view->head_count);
      }
      reader_metadata_snapshot_free(fresh);
    }

    /* NFC and NFD titles stay two distinct retained byte sequences. */
    {
      record("metadata.book2.bootstrap");
      reader_metadata_snapshot *fresh = nullptr;
      int prepare_status = (int)reader_metadata_prepare_book(owner, books[1].key.c_str(), &fresh, &metadata_error);
      number("prepare", prepare_status);
      reader_metadata_result staged{};
      int stage_status = -1;
      if (fresh && prepare_status == READER_METADATA_NEEDS_BOOTSTRAP) {
        reader_metadata_verified_source source{books[1].format.c_str(), books[1].sha.c_str(), books[1].bytes};
        stage_status = (int)reader_metadata_stage_bootstrap(owner, fresh, &source, &staged, &metadata_error);
      }
      number("stage", stage_status);
      reader_metadata_result finished{};
      if (stage_status == 0) number("finish", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      const std::string retained = staged.command.revision_id;
      number("revision_len", (long long)retained.size());
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;
      /* Rewrite the same book with the NFC title: a new revision, not a rewrite. */
      record("metadata.book2.edit");
      int edit_status = -1;
      std::string edited_id;
      int reopen_status = (int)reader_metadata_prepare_book(owner, books[1].key.c_str(), &fresh, &metadata_error);
      if (reopen_status == READER_METADATA_OK && fresh) {
        reader_book_command input{READER_COMMAND_PUT, books[1].key.c_str(), books[1].format.c_str(),
                                  books[1].sha.c_str(), books[0].title.c_str(), books[1].author.c_str(),
                                  books[0].sort.c_str(), books[1].bytes, books[1].favorite};
        edit_status = (int)reader_metadata_stage_book(owner, fresh, &input, &staged, &metadata_error);
        edited_id = staged.command.revision_id;
      }
      number("status", edit_status);
      number("revision_len", (long long)edited_id.size());
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;
      if (edit_status == 0) number("finish", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      char *title = nullptr;
      record("metadata.book2.retained_title");
      number("status", (int)reader_revision_book_title_raw_v3(shared, retained.c_str(), &title, &revision_error));
      field("hex", hex(std::string(title ? title : "")));
      reader_revision_bytes_free(title);
      title = nullptr;
      record("metadata.book2.new_title");
      number("status", (int)reader_revision_book_title_raw_v3(shared, edited_id.c_str(), &title, &revision_error));
      field("hex", hex(std::string(title ? title : "")));
      reader_revision_bytes_free(title);
    }

    /* A stale observed head set is staged as an intent only: the commit is
     * refused with CONFLICT and the product row keeps the newer metadata. */
    {
      record("metadata.book3.bootstrap");
      reader_metadata_snapshot *fresh = nullptr;
      int prepare_status = (int)reader_metadata_prepare_book(owner, books[2].key.c_str(), &fresh, &metadata_error);
      number("prepare", prepare_status);
      reader_metadata_result staged{};
      int stage_status = -1;
      if (fresh && prepare_status == READER_METADATA_NEEDS_BOOTSTRAP) {
        reader_metadata_verified_source source{books[2].format.c_str(), books[2].sha.c_str(), books[2].bytes};
        stage_status = (int)reader_metadata_stage_bootstrap(owner, fresh, &source, &staged, &metadata_error);
      }
      number("stage", stage_status);
      number("revision_len", (long long)std::strlen(staged.command.revision_id));
      reader_metadata_result finished{};
      if (stage_status == 0) number("finish", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;

      record("metadata.book3.stale");
      int stale_prepare = (int)reader_metadata_prepare_book(owner, books[2].key.c_str(), &fresh, &metadata_error);
      number("status", stale_prepare);
      std::string head;
      if (fresh) {
        const reader_metadata_view *view = reader_metadata_snapshot_view(fresh);
        if (view && view->head_count == 1) head = view->heads[0];
        number("heads", view ? (long long)view->head_count : -1);
      }
      record("metadata.book3.external");
      const std::string external_id = ascii("revision.external");
      const std::string external_title = decode("title.external");
      int external_status = -1;
      if (!head.empty()) {
        const char *observed[1] = {head.c_str()};
        reader_command_context command_context{shared, external_id.c_str(), observed, 1};
        reader_book_command input{READER_COMMAND_PUT, books[2].key.c_str(), books[2].format.c_str(),
                                  books[2].sha.c_str(), external_title.c_str(), books[2].author.c_str(),
                                  books[2].sort.c_str(), books[2].bytes, books[2].favorite};
        reader_command_result committed{};
        reader_command_error command_error{};
        external_status = (int)reader_command_apply_book_raw_v3(&command_context, &input, &committed, &command_error);
        field("revision", literal(committed.revision_id));
        number("created", committed.created);
      }
      number("status", external_status);

      record("metadata.book3.stage");
      int stage_only = -1;
      if (fresh) {
        reader_book_command stale{READER_COMMAND_PUT, books[2].key.c_str(), books[2].format.c_str(),
                                  books[2].sha.c_str(), books[2].title.c_str(), books[2].author.c_str(),
                                  books[2].sort.c_str(), books[2].bytes, books[2].favorite};
        reader_metadata_result queued{};
        stage_only = (int)reader_metadata_stage_book(owner, fresh, &stale, &queued, &metadata_error);
        number("error", (int)metadata_error.code);
      }
      number("status", stage_only);
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;

      record("metadata.book3.apply_conflict");
      {
        reader_metadata_result refused{};
        int apply_status = (int)reader_metadata_apply_pending(owner, &refused, &metadata_error);
        number("status", apply_status);
        number("committed", refused.committed);
        number("pending", refused.pending);
        number("error", (int)metadata_error.code);
      }
      record("metadata.book3.pending_after_conflict");
      {
        reader_metadata_result pending{};
        number("status", (int)reader_metadata_pending(owner, &pending, &metadata_error));
        number("pending", pending.pending);
      }
      record("metadata.book3.row_after_conflict");
      int row_prepare = (int)reader_metadata_prepare_book(owner, books[2].key.c_str(), &fresh, &metadata_error);
      number("status", row_prepare);
      if (fresh) {
        const reader_metadata_view *view = reader_metadata_snapshot_view(fresh);
        field("titlehex", hex(view->book.title));
        field("head_is_external", flag(view->head_count == 1 && std::string(view->heads[0]) == external_id));
        number("heads", (long long)view->head_count);
      }
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;
      record("metadata.book3.abandon");
      number("status", (int)reader_metadata_abandon_pending(owner, &metadata_error));
      record("metadata.book3.pending_after_abandon");
      {
        reader_metadata_result pending{};
        number("status", (int)reader_metadata_pending(owner, &pending, &metadata_error));
        number("pending", pending.pending);
      }
    }

    /* Two competing heads for one book are reported, never merged. */
    {
      record("metadata.book5.bootstrap");
      reader_metadata_snapshot *fresh = nullptr;
      int prepare_status = (int)reader_metadata_prepare_book(owner, books[4].key.c_str(), &fresh, &metadata_error);
      number("prepare", prepare_status);
      reader_metadata_result staged{};
      int stage_status = -1;
      if (fresh && prepare_status == READER_METADATA_NEEDS_BOOTSTRAP) {
        reader_metadata_verified_source source{books[4].format.c_str(), books[4].sha.c_str(), books[4].bytes};
        stage_status = (int)reader_metadata_stage_bootstrap(owner, fresh, &source, &staged, &metadata_error);
      }
      number("stage", stage_status);
      const std::string book5_head = staged.command.revision_id;
      reader_metadata_result finished{};
      if (stage_status == 0) number("finish", (int)reader_metadata_finish_pending(owner, &finished, &metadata_error));
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;

      /* Two received revisions that both name the same retained parent. */
      char *wire = nullptr;
      size_t wire_bytes = 0;
      reader_revision_info info{};
      int get_status = (int)reader_revision_get_raw_v3(shared, book5_head.c_str(), &wire, &wire_bytes, &info,
                                                       &revision_error);
      record("metadata.book5.wire");
      number("status", get_status);
      number("bytes", (long long)wire_bytes);
      std::string base = wire ? std::string(wire, wire_bytes) : std::string();
      reader_revision_bytes_free(wire);
      const std::string id_one = ascii("revision.compete.1");
      const std::string id_two = ascii("revision.compete.2");
      auto competing = [&](const std::string &identity, const char *name) {
        std::string copy = base;
        const std::string original_id = "\"id\":\"" + book5_head + "\"";
        size_t at = copy.find(original_id);
        if (at == std::string::npos) throw std::runtime_error("retained wire has no identity field");
        copy.replace(at, original_id.size(), "\"id\":\"" + identity + "\"");
        size_t parents = copy.find("\"parents\":[]");
        if (parents == std::string::npos) throw std::runtime_error("retained wire has no empty parent set");
        copy.replace(parents, std::strlen("\"parents\":[]"), "\"parents\":[\"" + book5_head + "\"]");
        reader_revision_info received{};
        int created = -1;
        record(name);
        number("status", (int)reader_revision_receive_raw_v3(shared, copy.data(), copy.size(), nullptr, &received,
                                                             &created, &revision_error));
        number("created", created);
        field("revision", literal(received.revision_id));
      };
      competing(id_one, "metadata.book5.receive.one");
      competing(id_two, "metadata.book5.receive.two");
      record("metadata.book5.prepare");
      int concurrent_prepare = (int)reader_metadata_prepare_book(owner, books[4].key.c_str(), &fresh, &metadata_error);
      number("status", concurrent_prepare);
      if (fresh) {
        const reader_metadata_view *view = reader_metadata_snapshot_view(fresh);
        number("heads", view ? (long long)view->head_count : -1);
        std::vector<std::string> heads;
        if (view)
          for (size_t index = 0; index < view->head_count; ++index) heads.push_back(view->heads[index]);
        std::sort(heads.begin(), heads.end());
        field("head0", heads.size() > 0 ? heads[0] : std::string("<none>"));
        field("head1", heads.size() > 1 ? heads[1] : std::string("<none>"));
        field("titlehex", view ? hex(view->book.title) : std::string("<null>"));
      }
      record("metadata.book5.stage");
      int concurrent_stage = -1;
      if (fresh) {
        reader_book_command input{READER_COMMAND_PUT, books[4].key.c_str(), books[4].format.c_str(),
                                  books[4].sha.c_str(), books[4].title.c_str(), books[4].author.c_str(),
                                  books[4].sort.c_str(), books[4].bytes, books[4].favorite};
        reader_metadata_result refused{};
        concurrent_stage = (int)reader_metadata_stage_book(owner, fresh, &input, &refused, &metadata_error);
        number("error", (int)metadata_error.code);
      }
      number("status", concurrent_stage);
      reader_metadata_snapshot_free(fresh);
      fresh = nullptr;
      record("metadata.book5.pending");
      {
        reader_metadata_result pending{};
        number("status", (int)reader_metadata_pending(owner, &pending, &metadata_error));
        number("pending", pending.pending);
      }
    }
    reader_revisions_close(&shared, &revision_error);

    reader_metadata_close(&owner, &metadata_error);
    owner = nullptr;
    snapshot(where, where.main_db, "main.settled");
    record("metadata.reopen");
    {
      int reopened = (int)reader_metadata_open_raw_v3(where.main_db.u8string().c_str(),
                                                      where.pending.u8string().c_str(), &owner, &metadata_error);
      number("status", reopened);
      if (reopened == 0) {
        reader_metadata_result pending{};
        number("pending_status", (int)reader_metadata_pending(owner, &pending, &metadata_error));
        reader_metadata_snapshot *again = nullptr;
        number("prepare", (int)reader_metadata_prepare_book(owner, book_one.key.c_str(), &again, &metadata_error));
        const reader_metadata_view *view = reader_metadata_snapshot_view(again);
        field("head_matches", flag(view && view->head_count == 1 && std::string(view->heads[0]) == revision_one));
        field("titlehex", view ? hex(view->book.title) : std::string("<null>"));
        reader_metadata_snapshot_free(again);
      }
      number("sidecar_absent", (int)!fs::exists(where.pending));
      reader_metadata_close(&owner, &metadata_error);
    }
    snapshot(where, where.main_db, "main.after_reopen");
    stability_record("stability.main.reopen", where, "main.settled", "main.after_reopen");
    record("stability.wire.reopen");
    {
      reader_revisions *reopened = nullptr;
      reader_revision_error reopen_error{};
      int opened = (int)reader_revisions_open_raw_v3(where.main_db.u8string().c_str(), &reopened, &reopen_error);
      char *wire = nullptr;
      size_t wire_bytes = 0;
      reader_revision_info info{};
      int get_status = -1;
      if (opened == 0) {
        get_status = (int)reader_revision_get_raw_v3(reopened, revision_one.c_str(), &wire, &wire_bytes, &info,
                                                     &reopen_error);
      }
      number("status", get_status);
      field("equal", flag(get_status == 0 && wire && wire_one == std::string(wire, wire_bytes)));
      reader_revision_bytes_free(wire);
      if (reopened) reader_revisions_close(&reopened, &reopen_error);
    }

    /* ------------------------------------ re-sync into a second product DB */
    reader_revisions *mirror = nullptr;
    reader_revision_error mirror_error{};
    record("resync.open");
    int mirror_status = (int)reader_revisions_open_raw_v3(where.mirror_db.u8string().c_str(), &mirror, &mirror_error);
    number("status", mirror_status);
    if (mirror_status != 0) throw std::runtime_error("the mirror store did not open");
    {
      const std::string wire_sha = wire_digest;
      reader_revision_info received{};
      int created = -1;
      record("resync.receive.first");
      number("status", (int)reader_revision_receive_raw_v3(mirror, wire_one.data(), wire_one.size(), wire_sha.c_str(),
                                                          &received, &created, &mirror_error));
      number("created", created);
      number("revision_len", (long long)std::strlen(received.revision_id));
      snapshot(where, where.mirror_db, "mirror.receive1");
      int created_again = -1;
      record("resync.receive.second");
      number("status", (int)reader_revision_receive_raw_v3(mirror, wire_one.data(), wire_one.size(), wire_sha.c_str(),
                                                          &received, &created_again, &mirror_error));
      number("created", created_again);
      snapshot(where, where.mirror_db, "mirror.receive2");
      stability_record("stability.mirror.receive", where, "mirror.receive1", "mirror.receive2");
      const std::string wrong_sha(64, 'c');
      record("resync.receive.badsha");
      number("status", (int)reader_revision_receive_raw_v3(mirror, wire_one.data(), wire_one.size(), wrong_sha.c_str(),
                                                          &received, &created, &mirror_error));
      std::string tampered = wire_one;
      size_t at = tampered.find("\"title\":\"");
      if (at == std::string::npos) throw std::runtime_error("unexpected retained wire document");
      at += 9;
      tampered[at] = (tampered[at] == 'X') ? 'Y' : 'X';
      record("resync.receive.tampered");
      number("status", (int)reader_revision_receive_raw_v3(mirror, tampered.data(), tampered.size(), wire_sha.c_str(),
                                                          &received, &created, &mirror_error));
    }
    reader_revisions_close(&mirror, &mirror_error);
    record("resync.reopen");
    {
      int reopened = (int)reader_revisions_open_raw_v3(where.mirror_db.u8string().c_str(), &mirror, &mirror_error);
      number("status", reopened);
      if (reopened == 0) {
        reader_revision_info received{};
        int created = -1;
        const std::string wire_sha = wire_digest;
        number("receive", (int)reader_revision_receive_raw_v3(mirror, wire_one.data(), wire_one.size(),
                                                             wire_sha.c_str(), &received, &created, &mirror_error));
        number("created", created);
      }
      snapshot(where, where.mirror_db, "mirror.after_reopen");
      stability_record("stability.mirror.reopen", where, "mirror.receive2", "mirror.after_reopen");
      record("resync.project");
      if (reopened == 0) {
        reader_revision_info projected{};
        number("status", (int)reader_revision_project_raw_v3(mirror, "book", book_one.key.c_str(), revision_one.c_str(),
                                                            book_one.sort.c_str(), &projected, &mirror_error));
        number("revision_len", (long long)std::strlen(projected.revision_id));
      } else {
        number("status", -1);
      }
    }
    record("resync.heads");
    {
      std::vector<std::string> heads;
      reader_revision_state graph{};
      int heads_status = (int)reader_revision_heads_raw_v3(mirror, "book", book_one.key.c_str(), collect_head,
                                                          &heads, &graph, &mirror_error);
      number("status", heads_status);
      number("heads", (long long)heads.size());
      field("head_is_primary", flag(heads.size() == 1 && heads[0] == revision_one));
    }
    record("resync.selected");
    {
      char *wire = nullptr;
      size_t bytes = 0;
      reader_revision_info info{};
      reader_revision_selection selection{};
      int selected = (int)reader_revision_selected_raw_v3(mirror, "book", book_one.key.c_str(), &wire, &bytes, &info,
                                                         &selection, &mirror_error);
      number("status", selected);
      number("selection", (int)selection.kind);
      field("equal_wire", flag(wire && wire_one == std::string(wire, bytes)));
      reader_revision_bytes_free(wire);
    }
    reader_revisions_close(&mirror, &mirror_error);
    {
      reader_catalog *mirror_catalog = nullptr;
      reader_catalog_error mirror_catalog_error{};
      record("resync.catalog");
      int opened = reader_catalog_open(where.mirror_db.u8string().c_str(), &mirror_catalog, &mirror_catalog_error);
      number("status", opened);
      if (opened == 0) {
        page found;
        reader_catalog_error error{};
        int present = -1;
        int result = reader_catalog_metadata(mirror_catalog, book_one.key.c_str(), collect_row, &found, &present,
                                            &error);
        record("resync.metadata");
        number("status", result);
        number("found", present);
        number("rows", (long long)found.rows.size());
        field("joined", joined(found));
        page local;
        reader_catalog_error local_error{};
        int local_status = reader_catalog_local_page(mirror_catalog, nullptr, nullptr, nullptr, 1, 200, collect_row,
                                                    &local, &local_error);
        record("resync.local.rows");
        number("status", local_status);
        number("rows", (long long)local.rows.size());
        reader_catalog_close(&mirror_catalog, &mirror_catalog_error);
      }
    }

    /* ------------------------------------------- negative original entries */
    const book_fixture probe_one = book("probe.1");
    const book_fixture probe_two = book("probe.2");
    reader_catalog *probe = nullptr;
    reader_catalog_error probe_error{};
    record("probe.open");
    number("status", reader_catalog_open(where.probe_db.u8string().c_str(), &probe, &probe_error));
    if (!probe) throw std::runtime_error("the probe catalog did not open");
    record("probe.seed");
    number("one", attach_book(probe, probe_one, &probe_error));
    number("two", attach_book(probe, probe_two, &probe_error));
    {
      page rows;
      reader_catalog_error error{};
      page_record("probe.page", reader_catalog_page(probe, nullptr, nullptr, 200, collect_row, &rows, &error), rows,
                  error);
    }
    {
      std::string upper = probe_one.sha;
      for (char &value : upper) value = (char)std::toupper((unsigned char)value);
      reader_catalog_book input = catalog_book(probe_one);
      input.sha256 = upper.c_str();
      input.sdk_book_id = 900;
      record("probe.upper_sha");
      number("status", reader_catalog_attach(probe, &input, &probe_error));
      number("error", probe_error.code);
    }
    {
      reader_catalog_book input = catalog_book(probe_one);
      input.source_bytes = 0;
      input.sdk_book_id = 901;
      record("probe.zero_bytes");
      number("status", reader_catalog_attach(probe, &input, &probe_error));
      number("error", probe_error.code);
    }
    {
      reader_catalog_book input = catalog_book(probe_two);
      input.sdk_book_id = 0;
      record("probe.zero_sdk");
      number("status", reader_catalog_attach(probe, &input, &probe_error));
    }
    {
      reader_catalog_book input = catalog_book(probe_one);
      input.title = nullptr;
      input.sdk_book_id = 902;
      record("probe.null_title");
      number("status", reader_catalog_attach(probe, &input, &probe_error));
      number("error", probe_error.code);
    }
    {
      reader_catalog_book input = catalog_book(probe_one);
      input.source_bytes = probe_one.bytes + 1;
      record("probe.conflict.bytes");
      number("status", reader_catalog_attach(probe, &input, &probe_error));
      number("error", probe_error.code);
    }
    {
      reader_catalog_book input = catalog_book(probe_two);
      input.sdk_book_id = probe_one.sdk;
      record("probe.conflict.sdk");
      number("status", reader_catalog_attach(probe, &input, &probe_error));
      number("error", probe_error.code);
    }
    {
      page rows;
      reader_catalog_error error{};
      page_record("probe.after_negatives", reader_catalog_page(probe, nullptr, nullptr, 200, collect_row, &rows, &error),
                  rows, error);
      page found;
      reader_catalog_error metadata_error_at_probe{};
      int present = -1;
      int result = reader_catalog_metadata(probe, probe_two.key.c_str(), collect_row, &found, &present,
                                          &metadata_error_at_probe);
      record("probe.metadata.empty_title");
      number("status", result);
      number("found", present);
      number("rows", (long long)found.rows.size());
      field("joined", joined(found));
    }
    reader_catalog_close(&probe, &probe_error);

    /* ---------------------------------------------------------- long paths */
    std::string failure_note;
    fs::path long_dir = where.base;
    long long long_segments = integer("dir.long.count");
    for (long long index = 0; index < long_segments; ++index) long_dir /= fs::u8path(decode("dir.long.segment"));
    std::error_code long_error;
    fs::create_directories(long_dir, long_error);
    fs::path long_db = long_dir / fs::u8path(decode("file.long"));
    record("path.long.create");
    number("status", long_error ? 1 : 0);
    record("path.long.open");
    reader_catalog *long_catalog = nullptr;
    reader_catalog_error long_catalog_error{};
    int long_status = reader_catalog_open(long_db.u8string().c_str(), &long_catalog, &long_catalog_error);
    number("status", long_status);
    number("error", long_catalog_error.code);
    if (long_catalog) {
      record("path.long.attach");
      number("status", attach_book(long_catalog, probe_one, &long_catalog_error));
      reader_catalog_close(&long_catalog, &long_catalog_error);
      record("path.long.reopen");
      int reopened = reader_catalog_open(long_db.u8string().c_str(), &long_catalog, &long_catalog_error);
      number("status", reopened);
      if (reopened == 0) {
        page rows;
        reader_catalog_error error{};
        reader_catalog_page(long_catalog, nullptr, nullptr, 200, collect_row, &rows, &error);
        number("rows", (long long)rows.rows.size());
        reader_catalog_close(&long_catalog, &long_catalog_error);
      }
    }
    fs::path overlong_dir = where.base;
    long long overlong_segments = integer("dir.overlong.count");
    for (long long index = 0; index < overlong_segments; ++index)
      overlong_dir /= fs::u8path(decode("dir.overlong.segment"));
    std::error_code overlong_error;
    fs::create_directories(overlong_dir, overlong_error);
    fs::path overlong_db = overlong_dir / fs::u8path(decode("file.overlong"));
    reader_catalog *overlong = nullptr;
    reader_catalog_error overlong_catalog_error{};
    int overlong_status = reader_catalog_open(overlong_db.u8string().c_str(), &overlong, &overlong_catalog_error);
    bool overlong_exists = fs::exists(overlong_db);
    if (overlong) reader_catalog_close(&overlong, &overlong_catalog_error);

    /* Embedded NUL cannot name a product database: the counted boundary is the
     * only accepted entry, and a truncated path never converts an unrelated
     * file into a product database. */
    record("nul.product");
    {
      fs::path decoy = where.originals / fs::u8path(decode("file.notadb"));
      {
        std::ofstream output(decoy, std::ios::binary);
        output << "this file is not a product database\n";
      }
      std::ifstream before_input(decoy, std::ios::binary);
      std::string before((std::istreambuf_iterator<char>(before_input)), std::istreambuf_iterator<char>());
      std::string nul_path = decoy.u8string();
      nul_path.push_back('\0');
      nul_path += "tail.sqlite";
      reader_catalog *nul_catalog = nullptr;
      reader_catalog_error nul_error{};
      int opened = reader_catalog_open(nul_path.c_str(), &nul_catalog, &nul_error);
      number("status", opened);
      if (nul_catalog) reader_catalog_close(&nul_catalog, &nul_error);
      std::ifstream after_input(decoy, std::ios::binary);
      std::string after((std::istreambuf_iterator<char>(after_input)), std::istreambuf_iterator<char>());
      field("decoy_unchanged", flag(before == after));
      reader_metadata_owner *nul_owner = nullptr;
      reader_metadata_error nul_metadata{};
      number("metadata_status", (int)reader_metadata_open_raw_v3(nul_path.c_str(),
                                                                where.pending.u8string().c_str(), &nul_owner,
                                                                &nul_metadata));
      number("handle", nul_owner ? 1 : 0);
      if (nul_owner) reader_metadata_close(&nul_owner, &nul_metadata);
    }

    snapshot(where, where.main_db, "main.final");
    {
      std::ofstream sink(fs::u8path(output_path), std::ios::binary);
      if (!sink) throw std::runtime_error("cannot open the observation file");
      for (const observation &entry : observations) {
        sink << '#' << entry.name << '\n';
        for (const auto &pair : entry.fields) sink << pair.first << '=' << pair.second << '\n';
      }
    }
    {
      std::ofstream local(local_path.empty() ? fs::u8path(root_path + "/platform-local.txt") : fs::u8path(local_path),
                          std::ios::binary);
      local << "workspace_relative=" << where.base.lexically_relative(where.root).u8string() << '\n';
      local << "workspace_path_bytes=" << where.base.u8string().size() << '\n';
      local << "long_db_relative=" << long_db.lexically_relative(where.base).u8string() << '\n';
      local << "long_db_bytes=" << long_db.u8string().size() << '\n';
      local << "overlong_db_bytes=" << overlong_db.u8string().size() << '\n';
      local << "overlong_status=" << overlong_status << '\n';
      local << "overlong_exists=" << (overlong_exists ? 1 : 0) << '\n';
      local << "overlong_note=" << (failure_note.empty() ? "none" : failure_note) << '\n';
      local << "records=" << observations.size() << '\n';
      local << "note=absolute paths, path byte lengths and host path limits stay out of the cross-platform file\n";
    }
    return 0;
  } catch (const std::exception &failure) {
    std::cerr << "s12 consumer failure: " << failure.what() << std::endl;
    return 1;
  }
}
