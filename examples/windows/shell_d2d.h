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
enum { SHELL_TEXT_TITLE = 0, /* 17, weight 600, left, one line with ellipsis */
       SHELL_TEXT_ICON = 1,  /* icon font 20, centred */
       SHELL_TEXT_STYLES = 2 };

/* One owner-drawn round icon button. Colours are 0xRRGGBB. */
typedef struct shell_d2d_button {
  uint32_t background; /* the layer the button sits on */
  uint32_t fill;       /* hover / pressed overlay, used when has_fill */
  uint32_t icon;
  uint32_t ring;       /* focus outline, used when has_ring */
  int has_fill, has_ring;
  float diameter;      /* the circle; the outline sits outside it */
  float ring_width;    /* drawn just outside the circle */
} shell_d2d_button;

HRESULT shell_d2d_create(HWND window, shell_d2d **out);
void shell_d2d_destroy(shell_d2d *shell);
HRESULT shell_d2d_resize(shell_d2d *shell, UINT width, UINT height);
HRESULT shell_d2d_begin(shell_d2d *shell, uint32_t background);
void shell_d2d_fill(shell_d2d *shell, float x, float y, float width, float height, uint32_t color);
HRESULT shell_d2d_text(shell_d2d *shell, int style, const wchar_t *text, float x, float y, float width,
                       float height, uint32_t color);
/* S_FALSE: the device was lost and the target dropped; draw the frame again. */
HRESULT shell_d2d_end(shell_d2d *shell);
unsigned shell_d2d_recreated(const shell_d2d *shell);

/* Paints a round icon button into box on dc, centred in the box. */
HRESULT shell_d2d_icon_button(shell_d2d *shell, HDC dc, const RECT *box, wchar_t glyph,
                              const shell_d2d_button *look);

/* DWRITE_FONT_SIMULATIONS of the faces the title style resolves to for Latin
   text (its own family) and for CJK text (Microsoft YaHei UI); 0 = a real
   face, anything else is synthetic (fake bold). */
HRESULT shell_d2d_title_faces(shell_d2d *shell, unsigned *latin, unsigned *cjk);
/* Family name actually used for a text style. */
const wchar_t *shell_d2d_family(const shell_d2d *shell, int style);

#ifdef __cplusplus
}
#endif
#endif
