/* SPDX-License-Identifier: MIT */
#include <exr/dictionary.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_dictionary *dictionary = NULL;
  exr_dictionary_result *results = NULL;
  size_t count = 0;
  exr_error error = {0};
  exr_status status;
  if (argc != 3) { fprintf(stderr, "usage: dictionary book.ifo word\n"); return 2; }
  status = exr_dictionary_open(argv[1], &dictionary, &error);
  if (status == EXR_OK)
    status = exr_dictionary_query(&dictionary, 1, argv[2], 8, &results, &count, &error);
  if (status == EXR_OK) {
    for (size_t i = 0; i < count; ++i) printf("%s: %s\n", results[i].word, results[i].definition);
  } else fprintf(stderr, "%s\n", error.message);
  exr_dictionary_results_free(results, count);
  exr_dictionary_free(dictionary);
  return status == EXR_OK ? 0 : 1;
}
