/* Actions-only fixture: write a valid point with deliberately different text. */
#include <reader_txt_progress.h>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
  if (argc != 4) return 2;
  reader_txt_progress *store = nullptr;
  reader_txp_error error{};
  reader_txp_position position{};
  reader_txp_result result{};
  const char context[] = "mismatched retained text";
  reader_txp_status status = reader_txp_open(argv[1], std::strcmp(argv[2], "raw") == 0, &store, &error);
  if (status == READER_TXP_OK)
    status = reader_txp_capture(&position, 0, context, sizeof(context) - 1, &error);
  if (status == READER_TXP_OK)
    status = reader_txp_save(store, argv[3], "3.41.0", &position, &result, &error);
  reader_txp_close(&store);
  if (status != READER_TXP_OK || !result.created) {
    std::fprintf(stderr, "inject status=%d: %s\n", static_cast<int>(status), error.message);
    return 1;
  }
  return 0;
}
