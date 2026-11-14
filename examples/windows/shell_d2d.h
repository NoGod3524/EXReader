/* SPDX-License-Identifier: MIT */
/* Direct2D drawing layer for the Windows reader shell (EXR_READER_WINDOWS_SHELL).
   Self-contained: it knows nothing about the SDK or the host state, so it can
   be compiled and linked on its own. One unit is one physical pixel (96 dpi
   render targets). The window target is created on the first begin and
   dropped when Direct2D reports a lost device; owner-drawn controls are
   painted through a DC target bound to the control's own HDC. */
#ifndef EXR_SHELL_D2D_H
#define EXR_SHELL_D2D_H

#include <windows.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct shell_d2d shell_d2d;


/* Text styles from UI-SPEC sections 3 and 9. */
enum { SHELL_TEXT_TITLE = 0, /* 15, weight 650, left, one line with ellipsis */
       SHELL_TEXT_ICON = 1,  /* vector glyph 18, centred */
       SHELL_TEXT_PAGE_NUMBER = 2,
       SHELL_TEXT_UI = 3,
       SHELL_TEXT_LABEL = 4,
       SHELL_TEXT_CENTER = 5,
       SHELL_TEXT_STYLES = 6 };

/* One owner-drawn rounded icon button. Colours are 0xRRGGBB. */
typedef struct shell_d2d_button {
  uint32_t background; /* the layer the button sits on */
  uint32_t fill;       /* hover / pressed overlay, used when has_fill */
  uint32_t icon;
  uint32_t ring;       /* focus outline, used when has_ring */
  int has_fill, has_ring;
  float diameter;      /* the 32px visual; the outline sits outside it */
  float ring_width;    /* drawn just outside the circle */
  float offset_y;
} shell_d2d_button;

/* Text controls. Kinds are the DECKMARK-TOKENS buttons; a SEGMENT is one slice
   of a segmented track, laid out as `count` equal boxes edge to edge. A
   SELECTED ghost is a toggle that is on. Each control keeps its own BUTTON
   window, and so its native UIA proxy. */
enum { SHELL_CONTROL_STANDARD, SHELL_CONTROL_PRIMARY, SHELL_CONTROL_GHOST, SHELL_CONTROL_SEGMENT,
       SHELL_CONTROL_FIELD /* the frame around a borderless EDIT; no text */ };
enum { SHELL_STATE_HOVER = 1, SHELL_STATE_PRESSED = 2, SHELL_STATE_FOCUS = 4, SHELL_STATE_DISABLED = 8,
       SHELL_STATE_SELECTED = 16 };
typedef struct shell_d2d_look {
  int kind;
  unsigned state;
  uint32_t under;   /* 0xRRGGBB of the surface the control sits on */
  int index, count; /* SEGMENT: this box's place in its track */
} shell_d2d_look;
HRESULT shell_d2d_control(shell_d2d *, HDC, const RECT *, const wchar_t *, int dark, const shell_d2d_look *);
/* Floating surface with its static text. x/y/width/height are DIPs from the
   visible surface's corner; width 0 runs to the right padding. The style is
   SHELL_TEXT_TITLE (text colour) or SHELL_TEXT_LABEL (secondary). */
typedef struct shell_d2d_label { const wchar_t *text; float x, y, width, height; int style; } shell_d2d_label;
HRESULT shell_d2d_surface(shell_d2d *, HDC, const RECT *, int dark, const uint32_t *background,
                          const shell_d2d_label *labels, int count);
/* TOC state: hover 1, pressed 2, keyboard focus 4, current chapter 8.
   Negative row IDs are uncached header/empty-state text, at the given size. */
HRESULT shell_d2d_toc_row(shell_d2d *, HDC, const RECT *, const wchar_t *, int dark,
                          unsigned state, int row, float size, unsigned weight, int align);
void shell_d2d_toc_clear(shell_d2d *);
HRESULT shell_d2d_toc_begin(shell_d2d *,HDC,const RECT *,int dark);
HRESULT shell_d2d_toc_end(shell_d2d *);
void shell_d2d_toc_metrics(shell_d2d *,float values[4]);

HRESULT shell_d2d_create(HWND window, shell_d2d **out);
void shell_d2d_destroy(shell_d2d *shell);
void shell_d2d_target_dpi(const shell_d2d *shell, float values[4]);
HRESULT shell_d2d_set_dpi(shell_d2d *shell, unsigned dpi);
/* Page footer: text[strong_start, +strong_length) in `current`, the rest in `rest`. */
HRESULT shell_d2d_dc_text(shell_d2d *shell, HDC dc, const RECT *box, const wchar_t *text,
                          unsigned strong_start, unsigned strong_length, uint32_t current, uint32_t rest);
/* Cropped SDK image, centred by the caller; BGRA pixels retain their colours. */
HRESULT shell_d2d_page_image(shell_d2d *, HDC, const RECT *area, const RECT *image,
                             unsigned source_width, unsigned source_height,
                             const uint32_t *pixels, unsigned pitch, uint32_t background);
HRESULT shell_d2d_resize(shell_d2d *shell, UINT width, UINT height);
HRESULT shell_d2d_begin(shell_d2d *shell, uint32_t background);
void shell_d2d_fill(shell_d2d *shell, float x, float y, float width, float height, uint32_t color);
HRESULT shell_d2d_text(shell_d2d *shell, int style, const wchar_t *text, float x, float y, float width,
                       float height, uint32_t color);
/* S_FALSE: the device was lost and the target dropped; draw the frame again. */
HRESULT shell_d2d_end(shell_d2d *shell);
unsigned shell_d2d_recreated(const shell_d2d *shell);

/* Paints a rounded icon button into box on dc, centred in the box. */
HRESULT shell_d2d_icon_button(shell_d2d *shell, HDC dc, const RECT *box, wchar_t glyph,
                              const shell_d2d_button *look);

/* DWRITE_FONT_SIMULATIONS of the faces the title style resolves to for Latin
   text (its own family) and for CJK text (Microsoft YaHei UI); 0 = a real
   face, anything else is synthetic (fake bold). */
HRESULT shell_d2d_title_faces(shell_d2d *shell, unsigned *latin, unsigned *cjk);
/* Family name actually used for a text style. */
const wchar_t *shell_d2d_family(const shell_d2d *shell, int style);
void shell_d2d_metrics(const shell_d2d *shell, float values[8]);
void shell_d2d_page_metrics(shell_d2d *shell, float values[12]);

/* Editor layouts are disposable views; positions here are paragraph-local UTF-16. */
HRESULT shell_d2d_edit_layout(shell_d2d *, const wchar_t *, const wchar_t *family,
                             float size, float width, void **layout, float *height);
/* Range styling stays in the host drawing layer; family_missing reports fallback. */
HRESULT shell_d2d_edit_style(shell_d2d *, void *layout, unsigned start, unsigned length,
  const wchar_t *family, float size, unsigned bold, unsigned italic,
  int has_color, uint32_t color, int *family_missing);
HRESULT shell_d2d_edit_align(void *layout, unsigned alignment, float *height);
void shell_d2d_edit_release(void *layout);
unsigned shell_d2d_edit_hit(void *layout, float x, float y);
void shell_d2d_edit_position(void *layout, unsigned at, float box[4]);
typedef struct shell_d2d_edit_row {
  void *layout;
  float y, height;
  unsigned start, length, caret;
  int show_caret, selected_break;
} shell_d2d_edit_row;
HRESULT shell_d2d_edit_paint(shell_d2d *, HDC, const RECT *, int dark,
                            const shell_d2d_edit_row *, size_t count, float inset, float scroll, float top);
/* Overlay straight RGBA pixels without clearing the text underneath. Units
   are physical pixels; clip to the editor body below top. */
HRESULT shell_d2d_edit_image(shell_d2d *, HDC, const RECT *, int dark,
  const unsigned char *rgba, unsigned width, unsigned height, unsigned stride,
  float x, float y, float display_width, float display_height, float top, int selected);

#ifdef __cplusplus
}
#endif
#endif
