/* SPDX-License-Identifier: MIT */
/* ISO 32000-1 11.6.5.2 graphics-state soft masks: render the G form into a
   page-sized 8-bit mask. Alpha uses the group alpha; Luminosity composites the
   group over BC and takes the 0.3/0.59/0.11 luminance. TR uses the bounded PDF function evaluator. */
#include "pdf_raster_internal.h"
#include "icc_internal.h"
#include "pdf_function_internal.h"
#include "pixels_internal.h"
#include "vector_internal.h"
#include <float.h>
#include <math.h>
#include <string.h>
#include <stdio.h>

static exr_status fail(exr_error *e, exr_status code, const char *message) { return exr_fail(e, code, message); }
static int number(exr_pdf_file *file, uint32_t id, double *out) {
  const exr_pdf_value *v = exr_pdf_value_at(file, id);
  if (!v || (v->kind != EXR_PDF_INT && v->kind != EXR_PDF_REAL)) return 0;
  *out = v->kind == EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out) <= 1e7;
}
static int numbers(exr_pdf_file *file, uint32_t array, double *out, size_t count) {
  const exr_pdf_value *v = exr_pdf_value_at(file, array);
  uint32_t at; size_t i;
  if (!v || v->kind != EXR_PDF_ARRAY) return 0;
  at = v->first;
  for (i = 0; i < count; i++) {
    uint32_t value;
    if (at == EXR_PDF_NONE || exr_pdf_resolve(file, at, &value, NULL) != EXR_OK || !number(file, value, &out[i])) return 0;
    at = exr_pdf_value_at(file, at)->next;
  }
  return at == EXR_PDF_NONE;
}
static void multiply(const double a[6], const double b[6], double out[6]) {
  out[0] = a[0] * b[0] + a[2] * b[1]; out[1] = a[1] * b[0] + a[3] * b[1];
  out[2] = a[0] * b[2] + a[2] * b[3]; out[3] = a[1] * b[2] + a[3] * b[3];
  out[4] = a[0] * b[4] + a[2] * b[5] + a[4]; out[5] = a[1] * b[4] + a[3] * b[5] + a[5];
}

static exr_status load_transfer(exr_pdf_file *file,uint32_t mask,const exr_control *control,
                                exr_pdf_function **out,exr_error *e) {
  uint32_t id;const exr_pdf_value *v;size_t size;const unsigned char *name;
  *out=NULL;
  if(exr_pdf_resolve(file,exr_pdf_get(file,mask,"TR"),&id,e)!=EXR_OK) return e->code;
  v=exr_pdf_value_at(file,id);
  if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind==EXR_PDF_NAME) {
    name=exr_pdf_bytes(file,id,&size);
    if(size==8 && !memcmp(name,"Identity",8)) return EXR_OK;
    return exr_fail(e,EXR_FORMAT,"Invalid PDF soft mask transfer name");
  }
  return exr_pdf_function_open(file,id,1,control,out,e);
}
static int box_axis_rect(const double box[4], const double m[6], double out[4]) {
  double xs[4], ys[4], left, top, right, bottom;
  unsigned i;
  for (i = 0; i < 6; i++) if (!isfinite(m[i]) || fabs(m[i]) > 1e7) return 0;
  if (!((!m[1] && !m[2]) || (!m[0] && !m[3]))) return 0;
  for (i = 0; i < 4; i++) {
    double bx = (i & 1u) ? box[2] : box[0], by = (i & 2u) ? box[3] : box[1];
    xs[i] = m[0] * bx + m[2] * by + m[4];
    ys[i] = m[1] * bx + m[3] * by + m[5];
    if (!isfinite(xs[i]) || !isfinite(ys[i]) || fabs(xs[i]) > 1e7 || fabs(ys[i]) > 1e7) return 0;
  }
  left = right = xs[0]; top = bottom = ys[0];
  for (i = 1; i < 4; i++) {
    if (xs[i] < left) left = xs[i];
    if (xs[i] > right) right = xs[i];
    if (ys[i] < top) top = ys[i];
    if (ys[i] > bottom) bottom = ys[i];
  }
  if (left >= right || top >= bottom) return 0;
  out[0] = left; out[1] = top; out[2] = right; out[3] = bottom;
  return 1;
}
static int path_axis_rect(const exr_vector_segment *seg, size_t count, double rect[4]) {
  double x[4], y[4], left, top, right, bottom, scale, eps;
  unsigned sides = 0, prev = 0, first = 0, i;
  if (count != 5 || seg[0].verb != EXR_VECTOR_MOVE || seg[4].verb != EXR_VECTOR_CLOSE) return 0;
  for (i = 0; i < 4; i++) {
    if (i && seg[i].verb != EXR_VECTOR_LINE) return 0;
    x[i] = seg[i].points[0].x; y[i] = seg[i].points[0].y;
    if (!isfinite(x[i]) || !isfinite(y[i]) || fabs(x[i]) > 1e7 || fabs(y[i]) > 1e7) return 0;
  }
  left = right = x[0]; top = bottom = y[0];
  for (i = 1; i < 4; i++) {
    if (x[i] < left) left = x[i];
    if (x[i] > right) right = x[i];
    if (y[i] < top) top = y[i];
    if (y[i] > bottom) bottom = y[i];
  }
  if (left >= right || top >= bottom) return 0;
  scale = fmax(fmax(fabs(left), fabs(right)), fmax(fabs(top), fabs(bottom)));
  eps = fmin(1e-6, 1e-9 * fmax(1.0, scale));
  for (i = 0; i < 4; i++) {
    unsigned next = (i + 1u) & 3u, side = 0, vert;
    double x0 = x[i], y0 = y[i], x1 = x[next], y1 = y[next];
    if (fabs(x0 - x1) <= eps &&
        ((fabs(y0 - top) <= eps && fabs(y1 - bottom) <= eps) ||
         (fabs(y0 - bottom) <= eps && fabs(y1 - top) <= eps)))
      side = fabs(x0 - left) <= eps ? 1u : fabs(x0 - right) <= eps ? 2u : 0u;
    else if (fabs(y0 - y1) <= eps &&
        ((fabs(x0 - left) <= eps && fabs(x1 - right) <= eps) ||
         (fabs(x0 - right) <= eps && fabs(x1 - left) <= eps)))
      side = fabs(y0 - top) <= eps ? 4u : fabs(y0 - bottom) <= eps ? 8u : 0u;
    if (!side || (sides & side)) return 0;
    vert = side <= 2u;
    if (i && vert == prev) return 0;
    if (!i) first = vert;
    prev = vert; sides |= side;
  }
  if (sides != 15u || first == prev) return 0;
  rect[0] = left; rect[1] = top; rect[2] = right; rect[3] = bottom;
  return 1;
}
static int rect_covers_canvas(const double r[4], unsigned width, unsigned height) {
  double eps = 1e-6 * fmax(1.0, fmax((double)width, (double)height));
  return fabs(r[0]) <= eps && fabs(r[1]) <= eps &&
         fabs(r[2] - (double)width) <= eps && fabs(r[3] - (double)height) <= eps;
}
static unsigned rect_cov(const double r[4], unsigned x, unsigned y) {
  double dx = fmin(r[2], (double)x + 1.0) - fmax(r[0], (double)x);
  double dy = fmin(r[3], (double)y + 1.0) - fmax(r[1], (double)y);
  if (dx <= 0.0 || dy <= 0.0) return 0;
  if (dx >= 1.0 && dy >= 1.0) return 255u;
  if (dx >= 1.0) return (unsigned)floor(dy * 255.0 + 0.5);
  return (unsigned)floor(dx * dy * 255.0 + 0.5);
}
typedef struct { unsigned count; double rects[4][4]; } direct_clip_state;
static unsigned rects_cov(const direct_clip_state *clip, unsigned x, unsigned y) {
  unsigned cov = 255u, j;
  for (j = 0; j < clip->count; j++) {
    unsigned c = rect_cov(clip->rects[j], x, y);
    cov = j ? (cov * c + 127u) / 255u : c;
    if (!cov) break;
  }
  return cov;
}
typedef struct {
  int fallback, have_source;
  unsigned width, height, depth;
  direct_clip_state clip, saved[16];
  double rgb[512 * 3];
  exr_shading_paint_source axial;
  double inv[6];
  direct_clip_state source_clip;
} direct_mask_probe;
static exr_status dm_abort(direct_mask_probe *p) { p->fallback = 1; return EXR_CANCELLED; }
static exr_status dm_glyph(void *ctx, const exr_pdf_text_glyph *g, exr_error *e) {
  (void)g; (void)e; return dm_abort(ctx);
}
static exr_status dm_image(void *ctx, exr_pdf_file *f, uint32_t id, exr_pdf_file *rf, uint32_t res,
                           const exr_pdf_paint_state *paint, exr_error *e) {
  (void)f; (void)id; (void)rf; (void)res; (void)paint; (void)e; return dm_abort(ctx);
}
static exr_status dm_begin_group(void *ctx, const exr_pdf_paint_state *paint, unsigned flags, exr_error *e) {
  (void)paint; (void)flags; (void)e; return dm_abort(ctx);
}
static exr_status dm_end_layer(void *ctx, unsigned commit, exr_error *e) {
  (void)commit; (void)e; return dm_abort(ctx);
}
static exr_status dm_shading(void *ctx, const exr_bitmap *b, const exr_bitmap *inks, const double m[6],
                             const exr_pdf_paint_state *paint, exr_error *e) {
  (void)b; (void)inks; (void)m; (void)paint; (void)e; return dm_abort(ctx);
}
static unsigned dm_image_space(void *ctx) { (void)ctx; return EXR_GROUP_RGB; }
static exr_status dm_state(void *ctx, exr_pdf_state_event event, exr_error *e) {
  direct_mask_probe *p = ctx;
  (void)e;
  if (event == EXR_PDF_SAVE) {
    if (p->depth == 16u) return dm_abort(p);
    p->saved[p->depth++] = p->clip;
    return EXR_OK;
  }
  if (event == EXR_PDF_RESTORE) {
    if (!p->depth) return dm_abort(p);
    p->clip = p->saved[--p->depth];
    return EXR_OK;
  }
  return dm_abort(p);
}
static exr_status dm_path(void *ctx, const exr_pdf_path_paint *path, exr_error *e) {
  direct_mask_probe *p = ctx;
  double r[4];
  (void)e;
  if ((path->flags & (EXR_PDF_FILL | EXR_PDF_STROKE)) || !(path->flags & EXR_PDF_CLIP)) return dm_abort(p);
  if (!path_axis_rect(path->segments, path->count, r)) return dm_abort(p);
  if (rect_covers_canvas(r, p->width, p->height)) { p->clip.count = 0; return EXR_OK; }
  if (p->clip.count == 4u) return dm_abort(p);
  memcpy(p->clip.rects[p->clip.count++], r, sizeof(r));
  return EXR_OK;
}
static exr_status dm_source(void *ctx, const exr_paint_source *source, const double m[6],
                            const exr_pdf_paint_state *paint, exr_error *e) {
  direct_mask_probe *p = ctx;
  const exr_shading_paint_source *axial;
  double scale = 0, det, inv[6];
  unsigned k;
  (void)e;
  if (p->have_source || paint->smask != EXR_PDF_NONE || paint->blend != EXR_BLEND_NORMAL ||
      paint->alpha_is_shape || paint->fill.alpha != 1.0)
    return dm_abort(p);
  if (!source || source->struct_size != sizeof(*source) || !source->context || !source->sample)
    return dm_abort(p);
  axial = source->context;
  if (axial->magic != EXR_SHADING_SOURCE_MAGIC || axial->sample != source->sample ||
      axial->type != 2u || axial->axial_length <= 0.0 || !axial->rgb)
    return dm_abort(p);
  for (k = 0; k < 6; k++) if (!isfinite(m[k]) || fabs(m[k]) > 1e7) return dm_abort(p);
  for (k = 0; k < 4; k++) scale = fmax(scale, fabs(m[k]));
  if (!scale) return dm_abort(p);
  det = (m[0] / scale) * (m[3] / scale) - (m[1] / scale) * (m[2] / scale);
  if (!det) return dm_abort(p);
  inv[0] = (m[3] / scale) / det / scale; inv[1] = -(m[1] / scale) / det / scale;
  inv[2] = -(m[2] / scale) / det / scale; inv[3] = (m[0] / scale) / det / scale;
  inv[4] = -(inv[0] * m[4] + inv[2] * m[5]); inv[5] = -(inv[1] * m[4] + inv[3] * m[5]);
  for (k = 0; k < 6; k++) if (!isfinite(inv[k])) return dm_abort(p);
  /* Scanline-invariant vertical axial shading: every column on a row shares one colour. */
  if (inv[1] || inv[2] || axial->axial_ux) return dm_abort(p);
  memcpy(p->rgb, axial->rgb, sizeof(p->rgb));
  p->axial = *axial;
  p->axial.rgb = p->rgb;
  p->axial.inks = NULL;
  memcpy(p->inv, inv, sizeof(inv));
  p->source_clip = p->clip;
  p->have_source = 1;
  return EXR_OK;
}
static exr_status mask_byte_from_rgba(const unsigned char p[4], int kind, const double bc[3],
                                      exr_pdf_function *function, unsigned char *out, exr_error *e) {
  double a = p[3] / 255.0, value = a;
  if (kind) {
    double v0 = p[0] / 255.0 * a + bc[0] * (1.0 - a);
    double v1 = p[1] / 255.0 * a + bc[1] * (1.0 - a);
    double v2 = p[2] / 255.0 * a + bc[2] * (1.0 - a);
    value = 0.3 * v0 + 0.59 * v1 + 0.11 * v2;
  }
  if (function) {
    double output[4];
    exr_status status = exr_pdf_function_eval(function, value, output, e);
    if (status != EXR_OK) return status;
    value = output[0];
  }
  *out = (unsigned char)fmax(0.0, fmin(255.0, floor(value * 255.0 + 0.5)));
  return EXR_OK;
}
static exr_status resolve_mask_pixel(const unsigned char rgb[3], double row_alpha, double row_shape,
                                     unsigned inner_cov, unsigned bbox_cov, int isolated, int kind,
                                     const double bc[3], const unsigned char bg[4], unsigned char bc_mask,
                                     exr_pdf_function *function, unsigned char *out, exr_error *e) {
  unsigned char p[4];
  double obj_a = row_alpha * (inner_cov / 255.0), obj_s = row_shape * (inner_cov / 255.0);
  unsigned k;
  if (!bbox_cov || !inner_cov || obj_s <= 0.0 || obj_a <= 0.0) { *out = bc_mask; return EXR_OK; }
  if (!isolated) {
    float q[5];
    double bg_a = bg[3] / 255.0;
    double back[4] = { bg[0] / 255.0 * bg_a, bg[1] / 255.0 * bg_a, bg[2] / 255.0 * bg_a, bg_a };
    if (obj_a == 1.0 && obj_s == 1.0) {
      for (k = 0; k < 3; k++) q[k] = (float)(rgb[k] / 255.0);
      q[3] = q[4] = 1.0f;
    } else {
      double oa = obj_a, out1[4], a;
      out1[3] = oa + back[3] * (1.0 - oa);
      for (k = 0; k < 3; k++) out1[k] = (1.0 - oa) * back[k] + oa * (rgb[k] / 255.0);
      a = fmax(0.0, fmin(1.0, out1[3]));
      for (k = 0; k < 3; k++) q[k] = (float)fmax(0.0, fmin(a, out1[k]));
      q[3] = (float)a;
      q[4] = (float)fmax(0.0, fmin(1.0, oa));
    }
    if (q[4] == 1.0f && bbox_cov == 255u) {
      for (k = 0; k < 3; k++) {
        double v = q[k] < 0.0 ? 0.0 : q[k] < 1.0 ? (double)q[k] : 1.0;
        p[k] = (unsigned char)(int)(v * 255.0 + 0.5);
      }
      p[3] = 255u;
    } else {
      double ag = q[4], src[3], out2[4], a2;
      for (k = 0; k < 3; k++)
        src[k] = ag >= 1.0 ? fmax(0.0, fmin(1.0, (double)q[k]))
                           : (ag > 0.0 ? fmax(0.0, fmin(1.0, ((double)q[k] - (1.0 - ag) * back[k]) / ag)) : 0.0);
      ag *= bbox_cov / 255.0;
      out2[3] = ag + back[3] * (1.0 - ag);
      for (k = 0; k < 3; k++) out2[k] = (1.0 - ag) * back[k] + ag * src[k];
      a2 = fmax(0.0, fmin(1.0, out2[3]));
      for (k = 0; k < 3; k++) p[k] = a2 > 0.0 ? (unsigned char)fmax(0.0, fmin(255.0, floor(out2[k] * 255.0 / a2 + 0.5))) : 0;
      p[3] = (unsigned char)floor(a2 * 255.0 + 0.5);
    }
  } else {
    unsigned src_a = (unsigned)fmin(255.0, floor(obj_a * 255.0 + 0.5));
    exr_bitmap one = {0};
    one.width = 1; one.height = 1; one.channels = 4; one.stride = 4; one.pixels = p;
    memcpy(p, bg, 4);
    if (src_a) {
      uint32_t col = ((uint32_t)rgb[0] << 24) | ((uint32_t)rgb[1] << 16) | ((uint32_t)rgb[2] << 8) | src_a;
      exr_pixel(&one, 0, 0, col, bbox_cov);
    }
  }
  return mask_byte_from_rgba(p, kind, bc, function, out, e);
}
static int mask_row_scale_safe(const exr_shading_paint_source *axial, double v0, double v1,
                               double u_max, const double colors[3]) {
  const unsigned samples = 512u;
  double s = axial->axial_scale, ratio, max_dc[3] = {0, 0, 0};
  unsigned sy, k;
  if (u_max <= s) return 1;
  if (!isfinite(u_max) || s <= 0.0 || axial->axial_length <= 0.0 || !axial->rgb || u_max / s > 1e6) return 0;
  ratio = u_max / s;
  for (sy = 0; sy < 2; sy++) {
    double v = sy ? v1 : v0;
    double t = ((v / s - axial->axial_y) * axial->axial_uy) / axial->axial_length;
    double dt, u_t, frac, du;
    unsigned idx;
    if (!isfinite(t)) return 0;
    dt = 64.0 * DBL_EPSILON * ratio / axial->axial_length * (1.0 + fabs(t));
    if (dt >= 1e-6) return 0;
    if (t <= -dt) { if (axial->extend0) continue; return 0; }
    if (t >= 1.0 + dt) { if (axial->extend1) continue; return 0; }
    if (t <= dt || t >= 1.0 - dt) return 0;
    u_t = t * (samples - 1u); idx = (unsigned)u_t; frac = u_t - idx;
    if (idx >= samples - 1u) { idx = samples - 2u; frac = 1.0; }
    du = dt * (samples - 1u);
    for (k = 0; k < 3; k++) {
      double slope = fabs(axial->rgb[(idx + 1u) * 3u + k] - axial->rgb[idx * 3u + k]);
      if (frac <= du * 4.0 && idx > 0) {
        double prev = fabs(axial->rgb[idx * 3u + k] - axial->rgb[(idx - 1u) * 3u + k]);
        if (prev > slope) slope = prev;
      }
      if (frac >= 1.0 - du * 4.0 && idx + 2u < samples) {
        double next = fabs(axial->rgb[(idx + 2u) * 3u + k] - axial->rgb[(idx + 1u) * 3u + k]);
        if (next > slope) slope = next;
      }
      max_dc[k] += 0.5 * slope * du;
    }
  }
  for (k = 0; k < 3; k++) {
    double scaled = colors[k] * 255.0 + 0.5;
    double dist = fabs(scaled - floor(scaled + 0.5));
    double margin = fmax(1e-7, 255.0 * max_dc[k] * 16.0);
    if (dist <= margin) return 0;
  }
  return 1;
}
/* Direct single-pass soft-mask builder when the G form reduces to one
   scanline-invariant axial shading under axis-aligned clips. Avoids allocating
   full-page RGBA, clip and float[5] group buffers while matching the full
   rasterizer's pixel values, clipping and work-budget limits. */
static exr_status try_direct_axial_mask(exr_pdf_file *file, uint32_t mask, uint32_t resources,
                                        const unsigned char *data, size_t size, const double matrix[6],
                                        const double box[4], unsigned width, unsigned height,
                                        int kind, int group, const double bc[3], uint32_t background,
                                        exr_raster_work *work, size_t layer_budget, const exr_control *control,
                                        unsigned char **out, int *handled, exr_error *e) {
  direct_mask_probe probe;
  exr_pdf_draw_callbacks cb = { dm_glyph, dm_path, dm_state, dm_image, dm_shading,
                                dm_begin_group, dm_end_layer, dm_image_space, NULL, dm_source };
  double bbox_rect[4], inter[4];
  exr_raster_work probe_work = *work;
  size_t sample_cost, active_pixels, group_bytes, shade_work;
  size_t layer_limit = layer_budget ? layer_budget : (size_t)64 * 1024 * 1024;
  exr_error local_err = {0};
  exr_status status;
  exr_pdf_function *function = NULL;
  unsigned char bg[4], bc_mask = 0, *result = NULL;
  int has_bbox_clip, isolated = (group & EXR_PDF_GROUP_ISOLATED) != 0;
  unsigned active_l, active_t, active_r, active_b, in_l, in_r, j, y;
  *handled = 0;
  *out = NULL;
  if (!width || !height || width > 16384u || height > 16384u ||
      width > (size_t)64 * 1024 * 1024 / 4 / height)
    return EXR_OK;
  if (group & (EXR_PDF_GROUP_CMYK | EXR_PDF_GROUP_GRAY | EXR_PDF_GROUP_KNOCKOUT)) return EXR_OK;
  group_bytes = (size_t)width * height * (isolated ? 4u : (4u + 5u * sizeof(float)));
  if (group_bytes > layer_limit) return EXR_OK;
  if (!box_axis_rect(box, matrix, bbox_rect)) return EXR_OK;
  memset(&probe, 0, sizeof(probe));
  probe.width = width; probe.height = height;
  cb.work = &probe_work;
  status = exr_pdf_draw_ops(file, resources, data, size, matrix, &cb, &probe, control, &local_err);
  if (status != EXR_OK || probe.fallback || !probe.have_source || probe.depth) return EXR_OK;
  has_bbox_clip = !rect_covers_canvas(bbox_rect, width, height);
  inter[0] = 0.0; inter[1] = 0.0; inter[2] = (double)width; inter[3] = (double)height;
  if (has_bbox_clip) {
    if (bbox_rect[0] > inter[0]) inter[0] = bbox_rect[0];
    if (bbox_rect[1] > inter[1]) inter[1] = bbox_rect[1];
    if (bbox_rect[2] < inter[2]) inter[2] = bbox_rect[2];
    if (bbox_rect[3] < inter[3]) inter[3] = bbox_rect[3];
  }
  for (j = 0; j < probe.source_clip.count; j++) {
    if (probe.source_clip.rects[j][0] > inter[0]) inter[0] = probe.source_clip.rects[j][0];
    if (probe.source_clip.rects[j][1] > inter[1]) inter[1] = probe.source_clip.rects[j][1];
    if (probe.source_clip.rects[j][2] < inter[2]) inter[2] = probe.source_clip.rects[j][2];
    if (probe.source_clip.rects[j][3] < inter[3]) inter[3] = probe.source_clip.rects[j][3];
  }
  if (inter[0] >= inter[2] || inter[1] >= inter[3]) {
    active_l = active_r = active_t = active_b = 0;
    in_l = in_r = 0;
  } else {
    active_l = (unsigned)floor(inter[0]); active_r = (unsigned)ceil(inter[2]);
    active_t = (unsigned)floor(inter[1]); active_b = (unsigned)ceil(inter[3]);
    if (active_r > width) active_r = width;
    if (active_b > height) active_b = height;
    in_l = (unsigned)ceil(inter[0]); in_r = (unsigned)floor(inter[2]);
    if (in_l < active_l) in_l = active_l;
    if (in_r > active_r) in_r = active_r;
    if (in_l > in_r) in_l = in_r = active_l;
  }
  status = load_transfer(file, mask, control, &function, e);
  if (status != EXR_OK) return status;
  sample_cost = 1u + (kind ? 8u : 0u) + exr_pdf_function_cost(function);
  active_pixels = (size_t)(active_b - active_t) * (active_r - active_l);
  shade_work = active_pixels * (32u + (isolated ? 0u : 24u) + 16u + 4u) +
               (size_t)width * height * (sample_cost + (isolated ? 1u : 2u));
  if (!exr_vector_work(&probe_work, shade_work)) {
    exr_pdf_function_free(function);
    return EXR_OK;
  }
  bg[0] = (unsigned char)(background >> 24); bg[1] = (unsigned char)(background >> 16);
  bg[2] = (unsigned char)(background >> 8); bg[3] = (unsigned char)background;
  status = mask_byte_from_rgba(bg, kind, bc, function, &bc_mask, e);
  if (status != EXR_OK) { exr_pdf_function_free(function); return status; }
  result = exr_buffer_take(exr_pdf_buffer_pool(file), (size_t)width * height, 0);
  if (!result) { exr_pdf_function_free(function); return fail(e, EXR_MEMORY, "PDF soft mask allocation failed"); }
  if (active_t >= active_b || active_l >= active_r) {
    memset(result, bc_mask, (size_t)width * height);
    exr_pdf_function_free(function);
    *work = probe_work; *out = result; *handled = 1;
    return EXR_OK;
  }
  if (active_t > 0) memset(result, bc_mask, (size_t)active_t * width);
  if (active_b < height) memset(result + (size_t)active_b * width, bc_mask, (size_t)(height - active_b) * width);
  {
    double u_first = probe.inv[0] * ((double)active_l + 0.25) + probe.inv[4];
    double u_last = probe.inv[0] * ((double)(active_r - 1u) + 0.75) + probe.inv[4];
    double u_max = fmax(fabs(u_first), fabs(u_last)), s = probe.axial.axial_scale;
    if (!isfinite(u_first) || !isfinite(u_last)) {
      exr_buffer_put(exr_pdf_buffer_pool(file), result, (size_t)width * height);
      exr_pdf_function_free(function);
      return EXR_OK;
    }
    for (y = active_t; y < active_b; y++) {
      double py0 = (double)y + 0.25, py1 = py0 + 0.5;
      double v0 = probe.inv[3] * py0 + probe.inv[5], v1 = probe.inv[3] * py1 + probe.inv[5];
      double c0[4] = {0}, c1[4] = {0}, sh0 = 0, op0 = 0, sh1 = 0, op1 = 0;
      double colors[3] = {0}, sum_a = 0, sum_s = 0, row_a, row_s;
      unsigned char rgb_b[3], m_in = 0;
      exr_raster_work sample_work = {0};
      unsigned k, sy, sx, bbox_row_cov, inner_row_cov, x;
      int row_uniform;
      if (exr_control_cancel(control, e) != EXR_OK) { status = EXR_CANCELLED; goto fail_direct; }
      if (!isfinite(v0) || !isfinite(v1)) goto fallback_direct;
      probe.axial.work = &sample_work;
      local_err.code = EXR_OK; local_err.message[0] = 0;
      status = probe.axial.sample(&probe.axial, 0.0, v0, EXR_GROUP_RGB, c0, &sh0, &op0, &local_err);
      if (status != EXR_OK || local_err.code != EXR_OK) goto fallback_direct;
      status = probe.axial.sample(&probe.axial, 0.0, v1, EXR_GROUP_RGB, c1, &sh1, &op1, &local_err);
      if (status != EXR_OK || local_err.code != EXR_OK) goto fallback_direct;
      for (sy = 0; sy < 2; sy++) {
        double a = sy ? sh1 * op1 : sh0 * op0;
        double sh = sy ? sh1 : sh0;
        const double *cc = sy ? c1 : c0;
        for (sx = 0; sx < 2; sx++) {
          sum_a += a; sum_s += sh;
          for (k = 0; k < 3; k++) colors[k] += a * cc[k];
        }
      }
      if (sum_a) for (k = 0; k < 3; k++) colors[k] /= sum_a;
      row_a = sum_a / 4.0; row_s = sum_s / 4.0;
      for (k = 0; k < 3; k++) rgb_b[k] = (unsigned char)fmin(255.0, floor(colors[k] * 255.0 + 0.5));
      if (active_l > 0) memset(result + (size_t)y * width, bc_mask, active_l);
      if (active_r < width) memset(result + (size_t)y * width + active_r, bc_mask, width - active_r);
      row_uniform = fabs(v0) <= s && fabs(v1) <= s &&
                    (u_max <= s || (row_s == 1.0 && mask_row_scale_safe(&probe.axial, v0, v1, u_max, colors)));
      if (row_uniform) {
        if (in_r > in_l) {
          bbox_row_cov = has_bbox_clip ? rect_cov(bbox_rect, in_l, y) : 255u;
          inner_row_cov = probe.source_clip.count ? rects_cov(&probe.source_clip, in_l, y) : 255u;
          status = resolve_mask_pixel(rgb_b, row_a, row_s, inner_row_cov, bbox_row_cov, isolated, kind, bc, bg, bc_mask, function, &m_in, e);
          if (status != EXR_OK) goto fail_direct;
          memset(result + (size_t)y * width + in_l, m_in, in_r - in_l);
        }
        for (x = active_l; x < in_l; x++) {
          unsigned bc_c = has_bbox_clip ? rect_cov(bbox_rect, x, y) : 255u;
          unsigned ic_c = probe.source_clip.count ? rects_cov(&probe.source_clip, x, y) : 255u;
          status = resolve_mask_pixel(rgb_b, row_a, row_s, ic_c, bc_c, isolated, kind, bc, bg, bc_mask, function, result + (size_t)y * width + x, e);
          if (status != EXR_OK) goto fail_direct;
        }
        for (x = in_r; x < active_r; x++) {
          unsigned bc_c = has_bbox_clip ? rect_cov(bbox_rect, x, y) : 255u;
          unsigned ic_c = probe.source_clip.count ? rects_cov(&probe.source_clip, x, y) : 255u;
          status = resolve_mask_pixel(rgb_b, row_a, row_s, ic_c, bc_c, isolated, kind, bc, bg, bc_mask, function, result + (size_t)y * width + x, e);
          if (status != EXR_OK) goto fail_direct;
        }
      } else {
        for (x = active_l; x < active_r; x++) {
          double px0 = (double)x + 0.25, px1 = px0 + 0.5;
          double u0 = probe.inv[0] * px0 + probe.inv[4], u1 = probe.inv[0] * px1 + probe.inv[4];
          double pc[3] = {0}, pa = 0, ps = 0;
          unsigned char prgb[3];
          unsigned bc_c = has_bbox_clip ? rect_cov(bbox_rect, x, y) : 255u;
          unsigned ic_c = probe.source_clip.count ? rects_cov(&probe.source_clip, x, y) : 255u;
          if (fabs(v0) <= s && fabs(v1) <= s && fabs(u0) <= s && fabs(u1) <= s) {
            status = resolve_mask_pixel(rgb_b, row_a, row_s, ic_c, bc_c, isolated, kind, bc, bg, bc_mask, function, result + (size_t)y * width + x, e);
            if (status != EXR_OK) goto fail_direct;
            continue;
          }
          for (sy = 0; sy < 2; sy++) for (sx = 0; sx < 2; sx++) {
            double sc[4] = {0}, ssh = 0, sop = 0, a;
            sample_work.used = 0;
            local_err.code = EXR_OK; local_err.message[0] = 0;
            status = probe.axial.sample(&probe.axial, sx ? u1 : u0, sy ? v1 : v0, EXR_GROUP_RGB, sc, &ssh, &sop, &local_err);
            if (status != EXR_OK || local_err.code != EXR_OK) goto fallback_direct;
            a = ssh * sop; pa += a; ps += ssh;
            for (k = 0; k < 3; k++) pc[k] += a * sc[k];
          }
          if (pa) for (k = 0; k < 3; k++) pc[k] /= pa;
          for (k = 0; k < 3; k++) prgb[k] = (unsigned char)fmin(255.0, floor(pc[k] * 255.0 + 0.5));
          status = resolve_mask_pixel(prgb, pa / 4.0, ps / 4.0, ic_c, bc_c, isolated, kind, bc, bg, bc_mask, function, result + (size_t)y * width + x, e);
          if (status != EXR_OK) goto fail_direct;
        }
      }
    }
  }
  exr_pdf_function_free(function);
  *work = probe_work; *out = result; *handled = 1;
  return EXR_OK;
fallback_direct:
  exr_buffer_put(exr_pdf_buffer_pool(file), result, (size_t)width * height);
  exr_pdf_function_free(function);
  return EXR_OK;
fail_direct:
  exr_buffer_put(exr_pdf_buffer_pool(file), result, (size_t)width * height);
  exr_pdf_function_free(function);
  return status;
}
static exr_status build_mask(exr_pdf_file *file, uint32_t mask, const double set_matrix[6],
                                   unsigned width, unsigned height, unsigned char **out,
                                   exr_raster_work *work,size_t layer_budget,size_t *active_mask_bytes, const exr_control *control, exr_error *e) {
  uint32_t form, id, resources = EXR_PDF_NONE; const unsigned char *data = NULL; size_t size = 0, i; exr_raster_work local_work={0};
  double matrix[6], local[6], box[4], bc[4] = {0, 0, 0, 0},bc_cmyk[4]; unsigned char *pixels = NULL, *result = NULL;
  const exr_pdf_value *v; int kind = 0, count = 0; exr_bitmap bitmap = {0}; exr_pdf_raster_config config = {0}; exr_status status;
  exr_pdf_function *function=NULL;size_t sample_cost;int group;
  *out = NULL;
  if(!work) work=&local_work;
  status = exr_pdf_soft_mask_kind(file, mask, &kind, e); if (status != EXR_OK) return status;
  if (exr_pdf_resolve(file, mask, &mask, e) != EXR_OK) return e->code;
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "G"), &form, e) != EXR_OK) return e->code;
  if (exr_pdf_stream_data(file, form, &data, &size, e) != EXR_OK) return e->code;
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "BBox"), &id, e) != EXR_OK) return e->code;
  if (!numbers(file, id, box, 4)) return fail(e, EXR_FORMAT, "Invalid PDF soft mask bounding box");
  /* Match ordinary Form XObjects: either corner order describes the same clip. */
  for(i=0;i<2;i++) if(box[i]>box[i+2]) { double swap=box[i];box[i]=box[i+2];box[i+2]=swap; }
  local[0] = 1; local[1] = 0; local[2] = 0; local[3] = 1; local[4] = 0; local[5] = 0;
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "Matrix"), &id, e) != EXR_OK) return e->code;
  if (id != EXR_PDF_NONE) { v = exr_pdf_value_at(file, id); if (v->kind != EXR_PDF_NULL && !numbers(file, id, local, 6)) return fail(e, EXR_FORMAT, "Invalid PDF soft mask matrix"); }
  multiply(set_matrix, local, matrix);
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "Resources"), &resources, e) != EXR_OK) return e->code;
  if (resources == EXR_PDF_NONE || exr_pdf_value_at(file, resources)->kind == EXR_PDF_NULL) resources = EXR_PDF_NONE;
  if(exr_pdf_resolve(file,exr_pdf_get(file,form,"Group"),&id,e)!=EXR_OK) return e->code;
  status=exr_pdf_group_rgb(file,id,EXR_PDF_GROUP_MASK_CONTEXT,&group,e);if(status!=EXR_OK) return status;
  config.group_present=1;
  config.group_flags=(group&EXR_PDF_GROUP_ISOLATED ? EXR_GROUP_ISOLATED : 0)|
    (group&EXR_PDF_GROUP_KNOCKOUT ? EXR_GROUP_KNOCKOUT : 0)|
    (group&EXR_PDF_GROUP_RGB ? EXR_GROUP_RGB : 0)|(group&EXR_PDF_GROUP_GRAY ? EXR_GROUP_GRAY : 0)|
    (group&EXR_PDF_GROUP_CMYK ? EXR_GROUP_CMYK : 0);
  if (kind) {
    double tmp[4]={0};
    /* ISO 32000-1 table 144: BC defaults to the space's initial black. */
    if(group&EXR_PDF_GROUP_CMYK) { count=4;tmp[3]=1; }
    if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "BC"), &id, e) != EXR_OK) return e->code;
    if (id != EXR_PDF_NONE && exr_pdf_value_at(file, id)->kind != EXR_PDF_NULL) {
      count=0;
      v = exr_pdf_value_at(file, id);
      { uint32_t at = v->first; while (at != EXR_PDF_NONE && count < 4) { uint32_t value; if (exr_pdf_resolve(file, at, &value, e) != EXR_OK || !number(file, value, &tmp[count])) return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop"); count++; at = exr_pdf_value_at(file, at)->next; } }
    }
    if (count == 1) { bc[0] = bc[1] = bc[2] = tmp[0]; }
    else if (count == 3) { bc[0] = tmp[0]; bc[1] = tmp[1]; bc[2] = tmp[2]; }
    else if (count == 4 && (group&EXR_PDF_GROUP_CMYK)) { memcpy(bc_cmyk,tmp,sizeof(bc_cmyk));config.background_cmyk=bc_cmyk; }
    else if (count == 4) { exr_icc *profile=NULL;status=exr_icc_default_cmyk(control,&profile,e);if(status!=EXR_OK) return status;exr_device_cmyk_rgb(profile,tmp,bc,1);status=exr_icc_deferred_status(profile,e);exr_icc_free(profile);if(status!=EXR_OK) return status; }
  }
  config.width = width; config.height = height; config.channels = 4; config.background = 0;
  if(kind) {
    config.background=255;
    for(unsigned k=0;k<3;k++) config.background|=(uint32_t)fmax(0,fmin(255,floor(bc[k]*255+.5)))<<(24-8*k);
  }
  config.work=work;config.layer_budget=layer_budget;config.active_mask_bytes=active_mask_bytes;
  config.initial_clip=box;config.initial_clip_transform=matrix;config.mask_budget=0;
  if (!config.background_cmyk) {
    int handled = 0;
    status = try_direct_axial_mask(file, mask, resources, data, size, matrix, box, width, height,
                                   kind, group, bc, config.background, work, layer_budget, control, out, &handled, e);
    if (status != EXR_OK || handled) return status;
  }
  status = exr_pdf_raster_content(file, resources, data, size, matrix, &config, control, &bitmap, e);
  if (status != EXR_OK) return status;
  status=load_transfer(file,mask,control,&function,e);
  if(status!=EXR_OK) { exr_buffer_put(exr_pdf_buffer_pool(file),bitmap.pixels,(size_t)bitmap.stride*bitmap.height);return status; }
  sample_cost=1+(kind ? 8 : 0)+exr_pdf_function_cost(function);
  result = exr_buffer_take(exr_pdf_buffer_pool(file),(size_t)width * height,0);
  if (!result) { exr_pdf_function_free(function);exr_buffer_put(exr_pdf_buffer_pool(file),bitmap.pixels,(size_t)bitmap.stride*bitmap.height); return fail(e, EXR_MEMORY, "PDF soft mask allocation failed"); }
  pixels = bitmap.pixels;
  for(size_t y=0;y<height;y++) {
    status=exr_control_cancel(control,e);
    if(status==EXR_OK && !exr_vector_work(work,(size_t)width*sample_cost))
      status=exr_fail(e,EXR_LIMIT,"PDF soft mask samples exceed work budget");
    if(status!=EXR_OK) goto done;
    /* Axial masks can render identical RGBA rows. Reuse the resolved row
       after the usual cancellation check and work charge. */
    if(y && !memcmp(pixels+y*width*4,pixels+(y-1)*width*4,(size_t)width*4)) {
      memcpy(result+y*width,result+(y-1)*width,width);
      continue;
    }
    for(size_t x=0;x<width;x++) {
      double a,value,output[4];i=y*width+x;
      if(x && !memcmp(pixels+i*4,pixels+(i-1)*4,4)) { result[i]=result[i-1];continue; }
      a=pixels[i*4+3]/255.;
      value=a;
      if(kind) {
        double v0=pixels[i*4]/255.*a+bc[0]*(1-a);
        double v1=pixels[i*4+1]/255.*a+bc[1]*(1-a);
        double v2=pixels[i*4+2]/255.*a+bc[2]*(1-a);
        value=.3*v0+.59*v1+.11*v2;
      }
      if(function) {
        status=exr_pdf_function_eval(function,value,output,e);
        if(status!=EXR_OK) goto done;
        value=output[0];
      }
      result[i]=(unsigned char)fmax(0,fmin(255,floor(value*255+.5)));
    }
  }
  status=EXR_OK;
done:
  exr_pdf_function_free(function);
  if(status!=EXR_OK) { exr_buffer_put(exr_pdf_buffer_pool(file),result,(size_t)width*height);exr_buffer_put(exr_pdf_buffer_pool(file),bitmap.pixels,(size_t)bitmap.stride*bitmap.height);return status; }
  exr_buffer_put(exr_pdf_buffer_pool(file),bitmap.pixels,(size_t)bitmap.stride*bitmap.height);
  *out = result;
  return EXR_OK;
}

/* Bound recursive mask G/SMask graphs independently on each calling thread. */
#ifdef _MSC_VER
static __declspec(thread) unsigned mask_depth;
#else
static _Thread_local unsigned mask_depth;
#endif
exr_status exr_pdf_soft_mask_build(exr_pdf_file *file,uint32_t mask,const double matrix[6],
  unsigned width,unsigned height,unsigned char **out,exr_raster_work *work,size_t layer_budget,size_t *active_mask_bytes,const exr_control *control,exr_error *e) {
  exr_status status;*out=NULL;
  if(mask_depth==16) return exr_fail(e,EXR_LIMIT,"PDF soft mask nesting exceeds 16");
  mask_depth++;status=build_mask(file,mask,matrix,width,height,out,work,layer_budget,active_mask_bytes,control,e);mask_depth--;
  return status;
}
