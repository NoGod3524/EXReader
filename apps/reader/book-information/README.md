# EXReaderBookInformation 0.1.0

Optional installed C package that produces one read-only snapshot for a
low-frequency "book information" panel: product title/author, format, verified
bytes and identity, local availability, and the attributes a format really
exposes through the public SDK.

Product fields and parser fields are separate. Nothing is guessed: an unknown
page count, language or author stays unknown (`page_count_known=0`,
`author_known=0`, `parser_title=NULL`), and the parser never overwrites a
product value. The SDK book ID stays inside the module; `book_key`
(`format:sha256`) is the only identity in the view.

## API

```c
reader_book_information_status reader_book_information_read(
    reader_catalog *catalog, exr_library *library, const char *book_key,
    const reader_book_information_options *options,
    reader_book_information **out, reader_book_information_error *error);
const reader_book_information_view *reader_book_information_get(const reader_book_information *);
void reader_book_information_free(reader_book_information *);
```

`catalog` and `library` are borrowed and must run on their creating owner
thread. `library` may be NULL, in which case no SDK call happens. The product
row is read with `reader_catalog_metadata`; original bytes with
`exr_library_source`; parser fields with `exr_library_fixed_source` (PDF/CBZ)
or `exr_library_epub_info_get` (EPUB). Neither store is written, no SDK SQL is
read, nothing is imported, attached, edited or hashed for another book.

`*out` is a deep copy owned by the caller until
`reader_book_information_free`. Its immutable view stays valid after the
catalog, library, source and fixed document are closed, and may be read from any
thread. The module keeps no state between calls and never commits, so a failure
or cancellation leaves both stores and every borrowed handle untouched.

## Availability and identity

| availability | meaning |
| --- | --- |
| `CLOUD_ONLY` | product metadata only; the catalog has no local mapping |
| `LOCAL_UNCHECKED` | mapping exists; the caller supplied no SDK handle |
| `LOCAL_PRESENT` | public SDK source exists and passed the identity level below |
| `LOCAL_MISSING` | mapping exists but the SDK cannot supply the original |
| `LOCAL_MISMATCH` | the stored bytes are not this product book |

| identity | meaning |
| --- | --- |
| `NOT_CHECKED` | no SDK source was opened |
| `SIZE_ONLY` | stored size equals the product size and hashing was not requested |
| `SHA256` | size and SHA-256 equal the digest inside `book_key` |
| `MISMATCH` | size or digest differ; `verified_bytes=0` and no digest |

`SIZE_ONLY` is deliberately weaker: two different books with the same byte
count cannot be told apart without `verify_source`. Hashed reads stay bounded by
hashing only the requested original, 64 KiB at a time.

## Parser fields

| format | fields |
| --- | --- |
| `pdf`, `cbz` | page count, title, key/value metadata (8 PDF Info keys and XMP; ComicInfo properties) |
| `epub` | bounded-storage / global-extent mode only; page count and title stay unknown |
| `txt`, `html`, `fb2`, `docx`, `rtf`, `mobi` | `NO_PUBLIC_FIELDS` |

A password-protected original reports `PASSWORD_REQUIRED`; an unreadable
parser reports `FAILED`. In both cases the view keeps the real page count and
title when the fixed reader opened, and product fields are untouched.

## Limits

| item | hard maximum |
| --- | ---: |
| `book_key` UTF-8 bytes | 128 |
| title, author, parser title UTF-8 bytes | 1024 each |
| metadata key UTF-8 bytes | 128 |
| metadata value UTF-8 bytes | 1024 |
| metadata properties kept | 32 |
| hash chunk | 64 KiB |
| one snapshot, including view and property array | < 48 KiB |

Text is cut only at a UTF-8 scalar boundary and flagged (`title_truncated`,
`author_truncated`, `parser_title_truncated`, `key_truncated`,
`value_truncated`); a cut value is never reported as complete. Properties beyond
the 32-property cap, empty-key entries and entries that are not valid UTF-8 are
counted in `properties_omitted` instead of being silently dropped.

## Build

```
cmake -S apps/reader/book-information -B build/book-information -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=/path/to/reading-library/stage \
  -DCMAKE_PREFIX_PATH="/path/to/product-prefix;/path/to/reading-library/stage" \
  -DCMAKE_INSTALL_PREFIX=/path/to/prefix
cmake --build build/book-information
cmake --install build/book-information
```

The public header is `reader_book_information.h` and the CMake target is
`EXReaderBookInformation::reader_book_information`.

## Acceptance

`tests/reader_book_information` and `.github/workflows/reader-book-information.yml`
exercise the installed package on Windows, Linux and macOS. See
`docs/READER-BOOK-INFORMATION.md`.
