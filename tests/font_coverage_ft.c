/* SPDX-License-Identifier: MIT */
/* Independent acceptance oracle, linked to the SDK's pinned FreeType build.
   Input bytes remain owned by Python until fc_close(). No manager cmap used. */
#include <ft2build.h>
#include FT_FREETYPE_H
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif
API FT_Library fc_init(void) {
  FT_Library library = NULL;
  return FT_Init_FreeType(&library) ? NULL : library;
}
API void fc_done(FT_Library library) { FT_Done_FreeType(library); }
API FT_Face fc_open(FT_Library library, const unsigned char *data, long size, long index) {
  FT_Face face = NULL;
  if (FT_New_Memory_Face(library, data, size, index, &face)) return NULL;
  if (index >= 0 && FT_Select_Charmap(face, FT_ENCODING_UNICODE)) {
    FT_Done_Face(face); return NULL;
  }
  return face;
}
API void fc_close(FT_Face face) { FT_Done_Face(face); }
API long fc_count(FT_Face face) { return face->num_faces; }
API const char *fc_family(FT_Face face) { return face->family_name; }
API unsigned fc_index(FT_Face face, unsigned cp) { return FT_Get_Char_Index(face, cp); }
API int fc_load(FT_Face face, unsigned glyph) {
  return FT_Load_Glyph(face, glyph, FT_LOAD_NO_SCALE | FT_LOAD_NO_HINTING);
}
