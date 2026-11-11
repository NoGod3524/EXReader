/* SPDX-License-Identifier: MIT */
#include <exr/layout.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_publication *publication = NULL;
  const exr_toc_entry *entries = NULL;
  size_t count = 0;
  exr_error error = {0};
  exr_status status;
  if (argc != 2) { fprintf(stderr, "usage: toc book.epub\n"); return 2; }
  status = exr_publication_open(argv[1], &publication, &error);
  if (status == EXR_OK) status = exr_publication_toc(publication, &entries, &count, &error);
  if (status == EXR_OK) {
    for (size_t i = 0; i < count; ++i)
      printf("level=%zu part=%zu %s\n", entries[i].level, entries[i].target.part, entries[i].title);
  } else fprintf(stderr, "%s\n", error.message);
  /* entries and their strings belong to publication. */
  exr_publication_free(publication);
  return status == EXR_OK ? 0 : 1;
}
