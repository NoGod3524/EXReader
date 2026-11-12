/* SPDX-License-Identifier: MIT */
/* Sole visual token table: DECKMARK-TOKENS.md (owner handoff, 2026-11-06).
   RGB is 0xRRGGBB; alpha retains the source's exact fractional value. */
#ifndef EXR_SHELL_TOKENS_H
#define EXR_SHELL_TOKENS_H
#include <stdint.h>
#include <stddef.h>
typedef struct shell_theme {
  uint32_t layer_page, layer_side, layer_float, surface2, surface3, desk;
  uint32_t text, text_secondary, text_disabled, accent, accent_hover, on_accent, line_rgb;
} shell_theme;
/* Windows high contrast: the host fills this from GetSysColor; the Direct2D layer
   draws with it when told the theme is 2. Defined once, in shell_d2d.cpp. */
#ifdef __cplusplus
extern "C" shell_theme shell_theme_contrast;
#else
extern shell_theme shell_theme_contrast;
#endif
static const shell_theme shell_theme_light = {
  0xf5f5f2, 0xffffff, 0xffffff, 0xefeeea, 0xe7e6e1, 0xebeae6,
  0x1b1b1f, 0x5c5c65, 0x8b8b94, 0x4553e0, 0x3946cc, 0xffffff, 0x141420};
static const shell_theme shell_theme_dark = {
  0x141416, 0x1e1e21, 0x1e1e21, 0x28282c, 0x313136, 0x0e0e10,
  0xf2f2f4, 0xb3b3bc, 0x7d7d87, 0x7c88ff, 0x929cff, 0xffffff, 0xffffff};
/* Annotation categories need distinguishable hues. Yellow/green are new semantic
   tokens; blue shares accent's hue. Soft coverage preserves the reading ink. */
static const uint32_t SHELL_ANNOT_RGB[3]={0xd7a900,0x249b62,0x4553e0};
static const uint32_t SHELL_ANNOT_DARK_RGB[3]={0xf1cc54,0x66c795,0x7c88ff};
static const float SHELL_ANNOT_ALPHA=.26f, SHELL_ANNOT_DARK_ALPHA=.28f;
static const float SHELL_LINE_ALPHA=.075f, SHELL_LINE_STRONG_ALPHA=.13f;
/* Dark overrides inherit the root accent-soft/softer values verbatim. */
static const uint32_t SHELL_ACCENT_SOFT_RGB=0x4553e0;
static const float SHELL_ACCENT_SOFT_ALPHA=.10f, SHELL_ACCENT_SOFTER_ALPHA=.06f;
static const float SHELL_DISABLED_ALPHA=.4f, SHELL_PRIMARY_HIGHLIGHT_ALPHA=.16f;
static const float SHELL_PRESSED_Y=.5f, SHELL_UI_LINE_HEIGHT=1.45f;
static const float SHELL_EASE[4]={.2f,.8f,.2f,1.f};
typedef struct shell_shadow { float x,y,blur,spread,alpha; uint32_t rgb; } shell_shadow;
static const shell_shadow SHELL_SHADOW_SM[]={{0,1,1,0,.04f,0x10101c},{0,1,3,0,.06f,0x10101c}};
static const shell_shadow SHELL_SHADOW_MD[]={{0,1,2,0,.05f,0x10101c},{0,8,20,-6,.12f,0x10101c}};
static const shell_shadow SHELL_SHADOW_LG[]={{0,2,6,0,.06f,0x10101c},{0,22,48,-12,.24f,0x10101c}};
static const shell_shadow SHELL_PAGE_SHADOW[]={{0,0,0,1,.05f,0x10101c},{0,2,10,-2,.12f,0x10101c}};
static const wchar_t *const SHELL_UI_FONTS[]={L"SF Pro Text",L"Segoe UI Variable Text",L"Segoe UI",
  L"PingFang SC",L"Microsoft YaHei UI",L"Microsoft YaHei"};
static const wchar_t *const SHELL_ICON_FONTS[]={L"Segoe Fluent Icons",L"Segoe MDL2 Assets"};
static const int SHELL_FONT_STEPS[]={12,13,14,15,16,17,18,20,22,24,28,32};
enum {
  SHELL_SPACE_1=8,SHELL_SPACE_2=16,SHELL_SPACE_3=24,SHELL_SPACE_4=32,SHELL_SPACE_5=48,
  SHELL_TOPBAR_H=56,SHELL_BODY_DEFAULT_FONT=18,SHELL_BODY_MIN_FONT=12,SHELL_BODY_MAX_FONT=32,
  SHELL_BODY_MIN_EM=28,SHELL_BODY_MAX_EM=34,SHELL_BODY_TOP=40,SHELL_BODY_GAP=24,
  SHELL_PAGE_NUMBER_H=40,SHELL_REFLOW_MS=150,SHELL_MIN_CLIENT_W=720,SHELL_MIN_CLIENT_H=560,
  SHELL_TARGET=40,SHELL_FOCUS_STROKE=2,SHELL_RADIUS_SM=9,SHELL_RADIUS=14,SHELL_RADIUS_LG=18,
  SHELL_CONTROL_H=34,SHELL_CONTROL_PAD=14,SHELL_CONTROL_WEIGHT=550,SHELL_UI_FONT=14,
  SHELL_TITLE_FONT=15,SHELL_TITLE_WEIGHT=650,SHELL_ICON_FONT=18,SHELL_PAGE_FONT=12,SHELL_PAGE_WEIGHT=500,
  SHELL_ICON_SIZE=32,SHELL_ICON_GAP=6,SHELL_BAR_RIGHT=12,SHELL_TITLE_LEFT=20,
  SHELL_PANEL_W=360,SHELL_PANEL_H=588,SHELL_PANEL_PAD=20,SHELL_SHADOW_PAD=64,SHELL_SHADOW_TOP=24,SHELL_ANIMATION_MS=180,
  SHELL_ANIMATION_TICK=10,SHELL_STEPPER_W=34,SHELL_SEGMENT_W=96,SHELL_SEGMENT_H=26,SHELL_CONTROL_FRAME=4,
  SHELL_LABEL_H=16,SHELL_LABEL_FONT=12,SHELL_VALUE_FONT=13,SHELL_SEGMENT_PAD=3
};
#define SHELL_BODY_LINE_HEIGHT 1.6f
#define SHELL_BODY_PARAGRAPH_EM .8f
static inline uint32_t shell_blend(uint32_t base,uint32_t top,float alpha) {
  uint32_t out=0;
  for(int shift=16;shift>=0;shift-=8) {
    unsigned b=(base>>shift)&255,t=(top>>shift)&255;
    out|=(uint32_t)(b*(1-alpha)+t*alpha+.5f)<<shift;
  }
  return out;
}
#endif
