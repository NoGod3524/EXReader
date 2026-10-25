// SPDX-License-Identifier: MIT
// C++ consumer of the installed package, built by the acceptance project.
#include <exr_desktop_drop.h>
#include <cstdio>
#include <cstring>

int main() {
  const char payload[] = "file:///exr/missing.epub\nhttps://example.invalid/x.epub\n";
  exr_drop_request *raw = nullptr;
  if (exr_drop_request_from_uri_list(payload, sizeof(payload) - 1, EXR_DROP_ORIGIN_CLIPBOARD, nullptr, &raw)
      != EXR_DROP_OK)
    return 2;
  exr_drop_request_info info{};
  info.struct_size = sizeof(info);
  if (exr_drop_request_get_info(raw, &info) != EXR_DROP_OK || info.item_count != 2) {
    exr_drop_request_release(raw);
    return 3;
  }
  int files = 0;
  for (std::size_t index = 0; index < info.item_count; ++index) {
    exr_drop_item item{};
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_item(raw, index, &item) != EXR_DROP_OK) {
      exr_drop_request_release(raw);
      return 4;
    }
    if (item.status == EXR_DROP_ITEM_MISSING && std::strcmp(item.path, "/exr/missing.epub") == 0) ++files;
  }
  exr_drop_request_release(raw);
  std::printf("cpp_consumer files=%d\n", files);
  return files == 1 ? 0 : 5;
}
