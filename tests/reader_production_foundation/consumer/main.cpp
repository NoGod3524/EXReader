#include <reader_annotation_export.h>
#include <reader_annotation_import.h>
#include <reader_font_library.h>
#include <reader_original_export.h>
#include <reader_jump_history.h>
#include <reader_sync_view.h>
#include <cstdio>
int main() {
  auto volatile annotation_export = &reader_annotation_export_run;
  auto volatile annotation_import = &reader_annotation_import_run;
  auto volatile original = &roe_run;
  auto volatile history = &reader_jh_commit_wire;
  auto volatile view = &reader_sync_view_capture;
  auto volatile fonts = &rfl_open;
  if (!annotation_export || !annotation_import || !original || !history || !view || !fonts) return 1;
  std::puts("shared-install-six-targets-linked");
  return 0;
}
