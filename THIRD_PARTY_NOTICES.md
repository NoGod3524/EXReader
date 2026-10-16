# Native C dependencies

EXReader's own C sources are GPL-3.0-only. Third-party code keeps its original license.

| Component | Pinned source | License | Use |
| --- | --- | --- | --- |
| FreeType | VER-2-14-1, freetype/freetype | FreeType License OR GPL-2.0-only; FreeType License selected | Font loading, glyph metrics and rasterization |
| Expat | R_2_9_0, libexpat/libexpat | MIT | XML parsing with external entity resolution disabled |
| miniz | 3.1.2, richgel999/miniz | MIT | ZIP containers and decompression |
| SQLite | 3.54.0 amalgamation, sqlite.org | Public domain | Local bookshelf and annotations |

CMake verifies every source archive using the SHA-256 values in cmake/deps.cmake. Line breaking, pagination, document positions, the document model and format extraction are EXReader C code. FreeType supplies glyph metrics and rasterization; it is not an ebook layout engine.

The old JavaScript framework and reader are retained in Git history and their respective reader branches. They are not linked into this native engine.
