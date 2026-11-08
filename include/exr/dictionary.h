/* SPDX-License-Identifier: MIT */
#ifndef EXR_DICTIONARY_H
#define EXR_DICTIONARY_H
#include <exr/base.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct exr_dictionary exr_dictionary;
typedef struct {
  const char *bookname, *version, *sametypesequence;
  uint64_t wordcount, synwordcount, idxfilesize, data_size;
  unsigned idxoffsetbits, chunk_length, chunk_count;
} exr_dictionary_info;
typedef enum {
  EXR_DICT_EXACT, EXR_DICT_PREFIX, EXR_DICT_SYNONYM, EXR_DICT_FOLDED
} exr_dictionary_match;
typedef struct {
  char *word, *definition, *part_of_speech, *dictionary;
  size_t dictionary_index, entry_index;
  exr_dictionary_match match;
} exr_dictionary_result;
typedef struct {
  uint64_t blocks_inflated, compressed_bytes_read, bytes_inflated;
} exr_dictionary_io;
/* UTF-8 .ifo (StarDict 2.4.2/3.0.0) or .index (dictd) path. Companions
   have the same basename. Indexes are loaded, definitions remain on disk.
   .dict.dz must have a dictzip RA table; ordinary gzip is not expanded.
   Objects are single-thread owned. No dictionary file is modified. */
EXR_API exr_status exr_dictionary_open(const char *path, exr_dictionary **out, exr_error *error);
EXR_API void exr_dictionary_free(exr_dictionary *dictionary);
/* Borrowed metadata, valid until free. Counters exclude index/header reads. */
EXR_API const exr_dictionary_info *exr_dictionary_get_info(const exr_dictionary *dictionary);
EXR_API exr_dictionary_io exr_dictionary_get_io(const exr_dictionary *dictionary);
/* Per dictionary: exact, then prefix, then synonym, then Unicode full case
   folding (exact/prefix/synonym). Stop at the first nonempty stage. Dictionaries
   retain caller order; duplicate headwords retain original index order.
   limit is 1..256 results PER dictionary, dictionaries <=64. Empty query gives
   no results. On failure outputs are empty. All result strings are owned,
   including dictionary names; definitions are plain UTF-8 with line breaks,
   paragraphs/lists retained. Nontext media are skipped. No markup executes. */
EXR_API exr_status exr_dictionary_query(exr_dictionary *const *dictionaries, size_t count,
  const char *query, size_t limit, exr_dictionary_result **out, size_t *result_count, exr_error *error);
EXR_API void exr_dictionary_results_free(exr_dictionary_result *results, size_t count);
#ifdef __cplusplus
}
#endif
#endif
