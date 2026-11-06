/* SPDX-License-Identifier: MIT */
/* Direct2D surface for the Windows reader shell (EXR_READER_WINDOWS_SHELL).
   Self-contained: it knows nothing about the SDK or the host state, so it can
   be compiled and linked on its own. The render target is created on the first
   begin and dropped when Direct2D reports a lost device. */
#ifndef EXR_SHELL_D2D_H
#define EXR_SHELL_D2D_H

#include <windows.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct shell_d2d shell_d2d;

HRESULT shell_d2d_create(HWND window, shell_d2d **out);
void shell_d2d_destroy(shell_d2d *shell);
HRESULT shell_d2d_resize(shell_d2d *shell, UINT width, UINT height);
/* Colors are 0xRRGGBB. */
HRESULT shell_d2d_begin(shell_d2d *shell, uint32_t background);
void shell_d2d_fill(shell_d2d *shell, float x, float y, float width, float height, uint32_t color);
/* S_FALSE: the device was lost and the target dropped; draw the frame again. */
HRESULT shell_d2d_end(shell_d2d *shell);
unsigned shell_d2d_recreated(const shell_d2d *shell);

#ifdef __cplusplus
}
#endif
#endif
