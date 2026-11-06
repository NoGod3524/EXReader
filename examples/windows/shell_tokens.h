/* SPDX-License-Identifier: MIT */
/* Design tokens of the Windows reader shell (docs/ui/UI-SPEC-20261104.md,
   flat revision of 2026-11-05). Every colour, size and gap the shell draws
   comes from here; nothing else may hold a literal. Colours are 0xRRGGBB. */
#ifndef EXR_SHELL_TOKENS_H
#define EXR_SHELL_TOKENS_H

#include <stdint.h>

typedef struct shell_theme {
  uint32_t layer_page;  /* layer 0: reading page, top bar */
  uint32_t layer_side;  /* layer 1: docked side panels */
  uint32_t layer_float; /* layer 2: floating panels */
  uint32_t text;
  uint32_t text_secondary;
  uint32_t text_disabled;
  uint32_t accent;      /* the only accent colour */
  uint32_t on_accent;
  uint32_t hairline;    /* top bar bottom edge, already blended */
} shell_theme;

static const shell_theme shell_theme_light = {
  0xFFFFFF, 0xF7F7F8, 0xFFFFFF, 0x1D1D1F, 0x6E6E73, 0xAEAEB2, 0x1A73E8, 0xFFFFFF, 0xF0F0F0};
static const shell_theme shell_theme_dark = {
  0x121316, 0x191A1D, 0x222327, 0xE8E8EA, 0xA1A1A6, 0x5C5D63, 0x1A73E8, 0xFFFFFF, 0x202124};

enum {
  SHELL_SPACE_1 = 8, SHELL_SPACE_2 = 16, SHELL_SPACE_3 = 24, SHELL_SPACE_4 = 32, SHELL_SPACE_5 = 48,
  SHELL_TOPBAR_H = 56,
  SHELL_BODY_DEFAULT_FONT = 17, SHELL_BODY_MIN_FONT = 14, SHELL_BODY_MAX_FONT = 32,
  SHELL_BODY_MIN_EM = 28, SHELL_BODY_MAX_EM = 34,
  SHELL_BODY_TOP = 32, SHELL_BODY_BOTTOM = 32, SHELL_BODY_GAP = 32,
  SHELL_PAGE_NUMBER_H = 24, SHELL_REFLOW_MS = 150,
  SHELL_MIN_CLIENT_W = 720, SHELL_MIN_CLIENT_H = 560,
  SHELL_TARGET = 40,       /* round icon button diameter */
  SHELL_FOCUS_STROKE = 2,  /* focus outline width, drawn 2 outside the shape */
  SHELL_HOVER_PERCENT = 6, /* accent over the layer colour */
  SHELL_PRESSED_PERCENT = 12
};

#define SHELL_BODY_LINE_HEIGHT 1.6f
#define SHELL_BODY_PARAGRAPH_EM 0.8f

/* The accent laid over a layer colour at a percentage, rounded per channel. */
static inline uint32_t shell_mix(uint32_t base, uint32_t top, unsigned percent) {
  uint32_t out = 0;
  for (int shift = 16; shift >= 0; shift -= 8) {
    unsigned b = (base >> shift) & 0xFF, t = (top >> shift) & 0xFF;
    out |= (uint32_t)((b * (100 - percent) + t * percent + 50) / 100) << shift;
  }
  return out;
}

#endif
