/* SPDX-License-Identifier: MIT */
#ifndef EXR_FORMATS_H
#define EXR_FORMATS_H
#include "document.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct exr_sevenz exr_sevenz;
typedef struct {
  size_t struct_size;
  size_t max_unpack_size; /* Default 128 MiB: packed input AND each decoded stage. */
  size_t max_header_size; /* Default 16 MiB: packed and decoded header. */
} exr_sevenz_options;
typedef struct {
  const char *path; /* UTF-8, separators normalized to '/', borrowed. */
  uint64_t size;
  int is_directory;
} exr_sevenz_entry;
/* Read-only 7Z container, independent of document format detection. Supports
   Copy, LZMA, LZMA2 and Delta chains, compressed headers and solid blocks.
   Paths with '..' or '.' components, absolute paths, drive names and ADS are
   rejected at open. At most 10000 entries and four coders per block. Encryption,
   multi-input coders, external names/folder tables and anti-items return EXR_UNSUPPORTED.
   A solid block is decoded in full for each extraction; max_unpack_size bounds
   the whole block, not just the requested file. Oversized body blocks may be
   listed but cannot be extracted. Peak decode buffers <= 2*the applicable limit,
   plus metadata and at most 6 MiB of LZMA probability tables. No disk writes.
   Source ownership transfers only on success. Reads retry short callbacks and
   honor source.control cancellation. Calls on an object must be serialized. */
EXR_API exr_sevenz_options exr_sevenz_options_defaults(void);
EXR_API exr_status exr_sevenz_open(const char *path,const exr_sevenz_options *options,
  exr_sevenz **out,exr_error *error);
EXR_API exr_status exr_sevenz_open_source(const exr_source *source,const exr_sevenz_options *options,
  exr_sevenz **out,exr_error *error);
EXR_API const exr_sevenz_entry *exr_sevenz_entries(const exr_sevenz *archive,size_t *count);
/* Index addresses entries(). Directory indexes return EXR_ARGUMENT. On failure
   data=NULL,size=0. Release the returned buffer with exr_free(). */
EXR_API exr_status exr_sevenz_extract(exr_sevenz *archive,size_t index,
  void **data,size_t *size,exr_error *error);
EXR_API void exr_sevenz_free(exr_sevenz *archive);

/* Scan an immutable source without retaining it. Callbacks receive nonempty,
   trimmed paragraphs and their whole-document normalized UTF-8 byte offset;
   consecutive paragraphs are separated by one LF. Views last only for the call.
   This primitive does not create a document, pager, identity, or durable anchor.
   A decoded paragraph including whitespace must fit within 64 KiB. Reads retry
   short results; cancellation is checked during reads and before success. A
   callback error stops the scan. On failure extent is zero; callbacks already
   delivered cannot be rolled back. Source context remains owned by the caller. */
typedef exr_status (*exr_txt_paragraph_fn)(void *context,uint64_t offset,
  const char *text,size_t size,exr_error *error);
EXR_API exr_status exr_txt_scan_source(const exr_source *source,exr_txt_paragraph_fn paragraph,
  void *context,uint64_t *extent,exr_error *error);

/* Resumable projection cursor for continuous readers. The source and callback
   context must outlive the cursor and remain immutable. Paragraph views remain
   valid until the next cursor operation. Checkpoints are valid only for the
   same source and originate at a returned paragraph boundary. */
typedef struct exr_txt_cursor exr_txt_cursor;
typedef struct {
  uint64_t source_offset, projection_offset;
  unsigned encoding, pending_cr;
} exr_txt_checkpoint;
EXR_API exr_status exr_txt_cursor_create(const exr_source *source,exr_txt_cursor **out,exr_error *error);
EXR_API exr_status exr_txt_cursor_next(exr_txt_cursor *cursor,uint64_t *offset,
  const char **text,size_t *size,exr_error *error);
EXR_API exr_status exr_txt_cursor_checkpoint(const exr_txt_cursor *cursor,exr_txt_checkpoint *checkpoint,exr_error *error);
EXR_API exr_status exr_txt_cursor_restore(exr_txt_cursor *cursor,const exr_txt_checkpoint *checkpoint,exr_error *error);
EXR_API void exr_txt_cursor_free(exr_txt_cursor *cursor);

/* Exact UTF-8 byte search across the whole projected text, including paragraph
   separators. The complete source is validated even after a match. A missing
   match returns EXR_OK and UINT64_MAX in both outputs. `from` is a normalized
   byte offset and may not exceed the extent. Query scratch is bounded to 4 MiB;
   the paragraph budget and cancellation rules of the scanner also apply. */
EXR_API exr_status exr_txt_find_source(const exr_source *source,const char *query,uint64_t from,
  uint64_t *start,uint64_t *end,exr_error *error);

/* Create the same quote and 32-scalar context selector as exr_anchor_create
   for normalized whole-source byte offsets. The complete immutable source is
   validated; the host must associate the selector with the original source's
   identity. Uses at most a 64 KiB quote plus context and scanner scratch.
   The caller frees the result with exr_anchor_free. */
EXR_API exr_status exr_txt_anchor_create_source(const exr_source *source,size_t start,size_t end,
  exr_anchor *anchor,exr_error *error);

/* Resolve a captured selector against normalized TXT without constructing a
   whole-document buffer. Ranking, ambiguity and empty-context boundary rules
   follow exr_anchor_resolve_ex. Source bytes are fully validated even after a
   match. The caller retains the immutable source and associates it with its
   original identity. Scratch is bounded by the public selector limits. */
EXR_API exr_status exr_txt_anchor_resolve_source(const exr_source *source,const exr_anchor *anchor,
  exr_anchor_match *match,exr_error *error);

/* Read document-subject XMP simple literals, Seq/Bag values and preferred Alt. */
EXR_API exr_status exr_metadata_read_xmp(const void *data,size_t size,const exr_control *control,
  exr_metadata_entry **entries,size_t *count,exr_error *error);

/* EPUB package edits preserve chapter/resource bytes. A NULL cover leaves its
   designation unchanged; a zero-data cover clears the designation, keeping the
   old resource. Replacement accepts PNG/JPEG and preserves an existing cover URI. */
typedef struct {
  size_t struct_size;
  const void *data; size_t size;
  const char *media_type;
} exr_epub_cover;
/* Patches DC title/creator/subject/description/publisher/contributor/date/type/
   format/source/language/relation/coverage/rights using dcterms URI keys. Each
   key replaces all its values/refinements; NULL deletes optional properties,
   empty string is a value. Required title/language cannot be empty or deleted.
   Identifier edits, signed/rights-controlled packages and encrypted cover edits
   are rejected. No-op returns an independent identical copy. Free with exr_free. */
EXR_API exr_status exr_epub_metadata_write(const void *data,size_t size,
  const exr_metadata_entry *changes,size_t count,const exr_epub_cover *cover,
  const exr_control *control,void **out,size_t *out_size,exr_error *error);
EXR_API exr_status exr_document_open(const char *path, exr_document **out, exr_error *error);
EXR_API exr_status exr_document_open_memory(exr_format format, const void *data, size_t size,
                                            exr_document **out, exr_error *error);
/* Strict EPUB/OCF structure check for validation tools; default open paths stay
   tolerant and are unchanged. Requires: first stored "mimetype" member holding exactly
   "application/epub+zip" and no local-header extra field; unique member names;
   every central-directory entry matching its local header and CRC-32; a readable
   container, OPF and spine; every manifest item present under its exact path.
   Structural errors return EXR_FORMAT with a message naming the member, the
   expected value and what was found. Other argument, I/O and limit errors keep
   their usual status codes. */
EXR_API exr_status exr_epub_validate(const char *path, exr_error *error);
EXR_API exr_status exr_epub_validate_memory(const void *data, size_t size, exr_error *error);
/* Owned navigation snapshot; valid after document_free. Release with navigation_free.
   Returns authored nav/NCX resources, or an empty array when none are present. */
EXR_API exr_status exr_document_navigation(const exr_document *doc, exr_navigation **entries,
                                            size_t *count, exr_error *error);
EXR_API void exr_navigation_free(exr_navigation *entries, size_t count);
/* Copies an embedded resource; free the returned bytes with exr_free(). No network access. */
EXR_API exr_status exr_document_resource(const exr_document *doc, size_t resource, void **data,
                                         size_t *size, exr_error *error);
/* Resolve a local chapter-relative URI to a resource and, if parsed, a node.
   Missing targets return EXR_OK with SIZE_MAX; external/unsafe URIs return EXR_ARGUMENT. */
EXR_API exr_status exr_document_resolve(const exr_document *doc, size_t chapter, const char *uri,
                                        size_t *resource, size_t *node, exr_error *error);
/* Structure-preserving EPUB: serializes the tree and copies all declared resources.
   Chapter paths, attributes and resource bytes are retained. Missing resources,
   non-XML names and conflicting/reserved paths fail atomically. No network access.
   The legacy export() below remains a text-only conversion. */
EXR_API exr_status exr_document_export_epub(const exr_document *doc, const exr_control *control,
                                            void **data, size_t *size, exr_error *error);
/* Structure-preserving HTML directory in a ZIP, with a collision-free XHTML
   entrypoint/reading order. Retains chapter/asset paths, styles, fonts and links.
   Extract together before opening entry_path. Both allocations are owned;
   release data and entry_path with exr_free. Failure clears every output. */
EXR_API exr_status exr_document_export_html_bundle(const exr_document *doc,const exr_control *control,
                                                   void **data,size_t *size,char **entry_path,exr_error *error);
EXR_API exr_status exr_document_export(const exr_document *doc, exr_format format, void **data,
                                       size_t *size, exr_error *error);
/* Text-profile export with cooperative cancellation. The original export() is
   this call with control=NULL. Cancellation is observed before each block batch
   (64 blocks), around RTF scalar loops (4096 scalars) and before archive
   publication; it is not a per-byte hook. EXR_CANCELLED clears the output pointer and size. */
EXR_API exr_status exr_document_export_control(const exr_document *doc, exr_format format,
                                               const exr_control *control, void **data,
                                               size_t *size, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
