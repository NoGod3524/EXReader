// SPDX-License-Identifier: MIT
// Actions-only: seeds removed (tombstoned) books through the installed typed-command API.
// usage: j03-seed <product-db> <keys.tsv>   (lines: book_key<TAB>title)
#include <reader_commands.h>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
static void need(bool value, const char *why) { if (!value) throw std::runtime_error(why); }
int main(int argc, char **argv) {
  try {
    need(argc == 3 && std::getenv("GITHUB_ACTIONS") && std::string(std::getenv("GITHUB_ACTIONS")) == "true", "Actions only");
    std::ifstream in(argv[2]);
    std::vector<std::pair<std::string, std::string>> rows;
    std::string line;
    while (std::getline(in, line)) {
      auto tab = line.find('\t');
      need(tab != std::string::npos, "bad line");
      rows.emplace_back(line.substr(0, tab), line.substr(tab + 1));
    }
    reader_revisions *revision = nullptr; reader_revision_error re{};
    need(reader_revisions_open(argv[1], &revision, &re) == READER_REV_OK, "open revisions");
    for (auto &row : rows) {
      const std::string digest = row.first.substr(4);
      reader_book_command input{READER_COMMAND_PUT, row.first.c_str(), "txt", digest.c_str(), row.second.c_str(), "Author", "Sort", 123, 0};
      reader_command_context context{revision, nullptr, nullptr, 0};
      reader_command_result result{}; reader_command_error error{};
      need(reader_command_apply_book(&context, &input, &result, &error) == READER_COMMAND_OK && result.created && result.applied, "typed put");
      std::string parent = result.revision_id;
      const char *parents[] = {parent.c_str()};
      context.expected_heads = parents; context.expected_count = 1;
      input.operation = READER_COMMAND_DELETE;
      need(reader_command_apply_book(&context, &input, &result, &error) == READER_COMMAND_OK && result.created && result.applied, "typed delete");
      std::printf("{\"seeded\":\"%s\",\"delete_revision\":\"%s\"}\n", row.first.c_str(), result.revision_id);
    }
    need(reader_revisions_close(&revision, &re) == READER_REV_OK, "close revisions");
    return 0;
  } catch (const std::exception &e) { std::cerr << e.what() << "\n"; return 1; }
}
