/* SPDX-License-Identifier: MIT */
#include <exr/textindex.h>
#include <stdio.h>

int main(void) {
  const char text[] = "A searchable paragraph.";
  exr_text_index *index = NULL;
  exr_text_query *query = NULL;
  exr_text_hit hit = {0};
  exr_error error = {0};
  exr_status status;
  int found = 0;
  if (!exr_text_index_available()) { puts("Text index unavailable in this build"); return 0; }
  status = exr_text_index_open(":memory:", &index, &error);
  if (status == EXR_OK)
    status = exr_text_index_put(index, "book-1", "chapter-1", text, sizeof(text) - 1, NULL, &error);
  if (status == EXR_OK)
    status = exr_text_index_query(index, "book-1", "searchable", 10, NULL, &query, &error);
  if (status == EXR_OK) status = exr_text_query_next(query, &hit, &found, &error);
  if (status == EXR_OK && found) printf("%s [%zu, %zu)\n", hit.part, hit.start, hit.end);
  if (status != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_text_query_free(query);
  exr_text_index_close(index);
  return status == EXR_OK ? 0 : 1;
}
