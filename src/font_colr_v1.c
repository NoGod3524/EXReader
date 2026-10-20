/* SPDX-License-Identifier: MIT */
#include "font_internal.h"
#include "font_outline_internal.h"
#include "vector_internal.h"
#include FT_COLOR_H
#include FT_OUTLINE_H
#include FT_TRUETYPE_TABLES_H

/* COLR v1 paint traversal. Geometry stays in 1000-em design units (the same
   space as exr_font_outline); the canvas matrix maps that space to device
   pixels. All limits are per glyph and charged to the shared raster budget. */
#define COLR_MAX_DEPTH 64u
#define COLR_MAX_NODES 4096u
#define COLR_MAX_GLYPHS 16u
#define COLR_MAX_STOPS 256u
#define COLR_MAX_REGION 8192u
#define COLR_MAX_PIXELS ((size_t)8*1024*1024)

typedef struct {
  exr_face *face;
  exr_error *error;
  const exr_control *control;
  size_t *work;
  uint32_t foreground;
  double em;      /* 1000 / units_per_EM */
  double scale;   /* device pixels per 1000-em unit */
  unsigned nodes;
  int measuring;  /* first pass: validate and accumulate bounds */
  unsigned has_bounds;
  double bounds[4];
  unsigned glyphs[COLR_MAX_GLYPHS];
  unsigned glyph_depth;
  FT_Color *palette;
  unsigned palette_entries;
} colr_context;

typedef struct {
  unsigned kind;          /* 1 linear, 2 radial, 3 sweep */
  unsigned extend;
  unsigned stop_count;
  double geometry[6];
  /* offset and premultiplied sRGB components */
  double stops[COLR_MAX_STOPS][5];
} colr_gradient;

static void matrix_multiply(const double a[6], const double b[6], double out[6]) {
  out[0] = a[0]*b[0] + a[2]*b[1];
  out[1] = a[1]*b[0] + a[3]*b[1];
  out[2] = a[0]*b[2] + a[2]*b[3];
  out[3] = a[1]*b[2] + a[3]*b[3];
  out[4] = a[0]*b[4] + a[2]*b[5] + a[4];
  out[5] = a[1]*b[4] + a[3]*b[5] + a[5];
}

static int finite_matrix(const double m[6]) {
  unsigned i;
  for (i = 0; i < 6; i++)
    if (!isfinite(m[i]) || fabs(m[i]) > 1e7) return 0;
  return 1;
}

static exr_status fail(colr_context *c, exr_status status, const char *message) {
  return exr_fail(c->error, status, "%s", message);
}

/* CPAL entry 0 is the instance palette; a missing CPAL is legal as long as
   every paint uses the text foreground index 0xffff. */
static exr_status select_palette(colr_context *c) {
  FT_Palette_Data data;
  if (c->palette || c->palette_entries) return EXR_OK;
  if (FT_Palette_Data_Get(c->face->face, &data)) return fail(c, EXR_FONT, "Cannot read font color palettes");
  if (!data.num_palettes || !data.num_palette_entries) {
    c->palette_entries = 0;
    return EXR_OK;
  }
  if (!c->face->palette_ready || c->face->palette_index != 0) {
    c->face->palette_ready = 0;
    if (FT_Palette_Select(c->face->face, 0, &c->face->color_palette) || !c->face->color_palette)
      return fail(c, EXR_FONT, "Cannot select font color palette");
    c->face->palette_index = 0;
    c->face->palette_ready = 1;
  }
  c->palette = c->face->color_palette;
  c->palette_entries = data.num_palette_entries;
  return EXR_OK;
}

/* Straight sRGB and alpha for a COLRv1 ColorIndex. */
static exr_status color_index(colr_context *c, const FT_ColorIndex *index, double rgba[4]) {
  double alpha = (double)index->alpha / 16384.0;
  exr_status status;
  if (alpha < 0) alpha = 0;
  if (alpha > 1) alpha = 1;
  if (index->palette_index == 0xffff) {
    rgba[0] = (double)((c->foreground >> 24) & 255) / 255.0;
    rgba[1] = (double)((c->foreground >> 16) & 255) / 255.0;
    rgba[2] = (double)((c->foreground >> 8) & 255) / 255.0;
    rgba[3] = alpha;
    return EXR_OK;
  }
  status = select_palette(c);
  if (status != EXR_OK) return status;
  if (!c->palette_entries || index->palette_index >= c->palette_entries)
    return fail(c, EXR_FONT, "Color palette index is outside the palette");
  rgba[0] = (double)c->palette[index->palette_index].red / 255.0;
  rgba[1] = (double)c->palette[index->palette_index].green / 255.0;
  rgba[2] = (double)c->palette[index->palette_index].blue / 255.0;
  rgba[3] = ((double)c->palette[index->palette_index].alpha / 255.0) * alpha;
  return EXR_OK;
}

static exr_status read_stops(colr_context *c, const FT_ColorLine *line, colr_gradient *gradient) {
  FT_ColorStopIterator iterator = line->color_stop_iterator;
  FT_ColorStop stop;
  unsigned count = 0;
  double previous = -1;
  if (iterator.num_color_stops > COLR_MAX_STOPS) return fail(c, EXR_LIMIT, "Gradient exceeds 256 color stops");
  if (!exr_vector_work(c->work, iterator.num_color_stops)) return fail(c, EXR_LIMIT, "Gradient stop work exceeds budget");
  while (FT_Get_Colorline_Stops(c->face->face, &stop, &iterator)) {
    double rgba[4] = {0, 0, 0, 0}, offset = (double)stop.stop_offset / 65536.0;
    exr_status status;
    if (count == COLR_MAX_STOPS) return fail(c, EXR_LIMIT, "Gradient exceeds 256 color stops");
    if (!(offset >= 0 && offset <= 1) || offset < previous) return fail(c, EXR_FONT, "Invalid gradient stop offset");
    status = color_index(c, &stop.color, rgba);
    if (status != EXR_OK) return status;
    gradient->stops[count][0] = offset;
    gradient->stops[count][1] = rgba[0] * rgba[3];
    gradient->stops[count][2] = rgba[1] * rgba[3];
    gradient->stops[count][3] = rgba[2] * rgba[3];
    gradient->stops[count][4] = rgba[3];
    previous = offset;
    count++;
  }
  if (!count) return fail(c, EXR_FONT, "Gradient has no color stops");
  if (count != iterator.num_color_stops) return fail(c, EXR_FONT, "Gradient stop count mismatch");
  gradient->stop_count = count;
  gradient->extend = (unsigned)line->extend;
  if (gradient->extend > 2) return fail(c, EXR_FONT, "Unknown gradient extend mode");
  return EXR_OK;
}

static double wrap_extend(double t, unsigned extend) {
  if (extend == 0) return t < 0 ? 0 : t > 1 ? 1 : t;
  if (extend == 1) return t - floor(t);
  t = fmod(t, 2.0);
  if (t < 0) t += 2.0;
  return t > 1 ? 2.0 - t : t;
}

static exr_status sample_gradient(void *context, double x, double y, unsigned space,
                                  double components[4], double *shape, double *opacity, exr_error *error) {
  colr_gradient *gradient = context;
  double t = 0, r = 0, g = 0, b = 0, a = 0;
  unsigned i;
  (void)space;
  if (gradient->kind == 1) {
    double p0x = gradient->geometry[0], p0y = gradient->geometry[1];
    double p1x = gradient->geometry[2], p1y = gradient->geometry[3];
    double p2x = gradient->geometry[4], p2y = gradient->geometry[5];
    double d1x = p1x - p0x, d1y = p1y - p0y, d2x = p2x - p0x, d2y = p2y - p0y;
    double det = d1x*d2y - d1y*d2x;
    if ((p2x == p0x && p2y == p0y) || fabs(det) <= 1e-12*(fabs(d1x*d2y) + fabs(d1y*d2x) + 1)) {
      double length = d1x*d1x + d1y*d1y;
      if (length <= 1e-24) t = 0;
      else t = ((x - p0x)*d1x + (y - p0y)*d1y) / length;
    } else {
      double px = x - p0x, py = y - p0y;
      t = (px*d2y - py*d2x) / det;
    }
  } else if (gradient->kind == 2) {
    double c0x = gradient->geometry[0], c0y = gradient->geometry[1], r0 = gradient->geometry[2];
    double c1x = gradient->geometry[3], c1y = gradient->geometry[4], r1 = gradient->geometry[5];
    double dcx = c1x - c0x, dcy = c1y - c0y, dr = r1 - r0;
    double dx = x - c0x, dy = y - c0y;
    double qa = dcx*dcx + dcy*dcy - dr*dr;
    double qb = dx*dcx + dy*dcy + r0*dr;
    double qc = dx*dx + dy*dy - r0*r0;
    double disc = qb*qb - qa*qc;
    {
      double roots[2], best = 0;
      unsigned count = 0, k;
      int found = 0;
      if (fabs(qa) <= 1e-12) {
        roots[count++] = fabs(qb) <= 1e-12 ? 0 : qc / (2*qb);
      } else if (disc >= 0) {
        double root = sqrt(disc);
        roots[count++] = (qb - root) / qa;
        roots[count++] = (qb + root) / qa;
      }
      for (k = 0; k < count; k++) {
        double radius = r0 + roots[k]*dr;
        if (!isfinite(roots[k]) || radius < -1e-6) continue;
        if (!found || fabs(roots[k]) < fabs(best)) { best = roots[k]; found = 1; }
      }
      if (!found) {
        /* No circle of the family passes through this point. */
        components[0] = components[1] = components[2] = components[3] = 0;
        *shape = 0;
        *opacity = 0;
        if (error) { error->code = EXR_OK; error->message[0] = 0; }
        return EXR_OK;
      }
      t = best;
    }
  } else {
    /* Sweep angles are measured counter-clockwise from the positive x axis in
       font space, with the 180-degree bias of the colour-line encoding. */
    double cx = gradient->geometry[0], cy = gradient->geometry[1];
    double start = gradient->geometry[2], span = gradient->geometry[3] - start;
    double theta = atan2(y - cy, x - cx);
    if (fabs(span) <= 1e-12) t = 0;
    else {
      if (span > 0) {
        while (theta < start) theta += 2*3.14159265358979323846;
        while (theta >= start + 2*3.14159265358979323846) theta -= 2*3.14159265358979323846;
      } else {
        while (theta > start) theta -= 2*3.14159265358979323846;
        while (theta <= start - 2*3.14159265358979323846) theta += 2*3.14159265358979323846;
      }
      t = (theta - start) / span;
    }
  }
  t = wrap_extend(t, gradient->extend);
  a = gradient->stops[gradient->stop_count-1][4];
  r = gradient->stops[gradient->stop_count-1][1];
  g = gradient->stops[gradient->stop_count-1][2];
  b = gradient->stops[gradient->stop_count-1][3];
  for (i = 0; i + 1 < gradient->stop_count; i++) {
    double t0 = gradient->stops[i][0], t1 = gradient->stops[i+1][0];
    if (t <= t0) {
      a = gradient->stops[i][4]; r = gradient->stops[i][1]; g = gradient->stops[i][2]; b = gradient->stops[i][3];
      break;
    }
    if (t <= t1) {
      double f = t1 > t0 ? (t - t0) / (t1 - t0) : 0;
      a = gradient->stops[i][4] + (gradient->stops[i+1][4] - gradient->stops[i][4]) * f;
      r = gradient->stops[i][1] + (gradient->stops[i+1][1] - gradient->stops[i][1]) * f;
      g = gradient->stops[i][2] + (gradient->stops[i+1][2] - gradient->stops[i][2]) * f;
      b = gradient->stops[i][3] + (gradient->stops[i+1][3] - gradient->stops[i][3]) * f;
      break;
    }
  }
  if (a <= 0) {
    components[0] = components[1] = components[2] = 0;
    *opacity = 0;
  } else {
    components[0] = fmin(1, fmax(0, r / a));
    components[1] = fmin(1, fmax(0, g / a));
    components[2] = fmin(1, fmax(0, b / a));
    *opacity = fmin(1, a);
  }
  components[3] = 0;
  *shape = 1;
  if (error) { error->code = EXR_OK; error->message[0] = 0; }
  return EXR_OK;
}

static uint32_t pack_rgba(const double rgba[4]) {
  unsigned r = (unsigned)floor(fmin(1, fmax(0, rgba[0]))*255 + 0.5);
  unsigned g = (unsigned)floor(fmin(1, fmax(0, rgba[1]))*255 + 0.5);
  unsigned b = (unsigned)floor(fmin(1, fmax(0, rgba[2]))*255 + 0.5);
  unsigned a = (unsigned)floor(fmin(1, fmax(0, rgba[3]))*255 + 0.5);
  return (r << 24) | (g << 16) | (b << 8) | a;
}

static void union_point(colr_context *c, double x, double y) {
  if (!isfinite(x) || !isfinite(y) || fabs(x) > 1e7 || fabs(y) > 1e7) {
    c->has_bounds = 2;
    return;
  }
  if (!c->has_bounds) {
    c->bounds[0] = c->bounds[2] = x;
    c->bounds[1] = c->bounds[3] = y;
    c->has_bounds = 1;
    return;
  }
  if (x < c->bounds[0]) c->bounds[0] = x;
  if (y < c->bounds[1]) c->bounds[1] = y;
  if (x > c->bounds[2]) c->bounds[2] = x;
  if (y > c->bounds[3]) c->bounds[3] = y;
}

static exr_status glyph_bounds(colr_context *c, uint32_t glyph, const double matrix[6]) {
  FT_BBox box;
  double points[4][2];
  unsigned i;
  if (glyph >= (uint32_t)c->face->face->num_glyphs) return fail(c, EXR_FONT, "COLR paint references an invalid glyph");
  FT_Set_Transform(c->face->face, NULL, NULL);
  if (FT_Load_Glyph(c->face->face, glyph, FT_LOAD_NO_SCALE|FT_LOAD_NO_HINTING|FT_LOAD_NO_BITMAP|FT_LOAD_IGNORE_TRANSFORM))
    return fail(c, EXR_FONT, "Cannot load COLR paint glyph outline");
  if (c->face->face->glyph->format != FT_GLYPH_FORMAT_OUTLINE ||
      !c->face->face->glyph->outline.n_points) return EXR_OK;
  FT_Outline_Get_CBox(&c->face->face->glyph->outline, &box);
  points[0][0] = box.xMin*c->em; points[0][1] = box.yMin*c->em;
  points[1][0] = box.xMin*c->em; points[1][1] = box.yMax*c->em;
  points[2][0] = box.xMax*c->em; points[2][1] = box.yMin*c->em;
  points[3][0] = box.xMax*c->em; points[3][1] = box.yMax*c->em;
  for (i = 0; i < 4; i++) {
    double x = matrix[0]*points[i][0] + matrix[2]*points[i][1] + matrix[4];
    double y = matrix[1]*points[i][0] + matrix[3]*points[i][1] + matrix[5];
    union_point(c, x, y);
  }
  return EXR_OK;
}

static exr_status clip_box_bounds(exr_face *face, double em, uint32_t glyph, int *has, double box[4], exr_error *error) {
  FT_ClipBox clip;
  FT_F26Dot6 restore = face->metric_size ? face->metric_size : (FT_F26Dot6)face->design_units*64;
  int found;
  if (face->bitmap_only || !face->face->units_per_EM) { *has = 0; return EXR_OK; }
  if (FT_Set_Char_Size(face->face, 0, (FT_F26Dot6)face->face->units_per_EM*64, 72, 72))
    return exr_fail(error, EXR_FONT, "Cannot query COLR clip box");
  found = FT_Get_Color_Glyph_ClipBox(face->face, glyph, &clip);
  FT_Set_Char_Size(face->face, 0, restore, 72, 72);
  if (!found) { *has = 0; return EXR_OK; }
  box[0] = (double)clip.bottom_left.x/64*em;
  box[1] = (double)clip.bottom_left.y/64*em;
  box[2] = (double)clip.top_right.x/64*em;
  box[3] = (double)clip.top_right.y/64*em;
  if (!(box[2] > box[0] && box[3] > box[1])) return exr_fail(error, EXR_FONT, "Invalid COLR clip box");
  *has = 1;
  return EXR_OK;
}

static exr_status render_solid(colr_context *c, exr_canvas *canvas, const double rgba[4], unsigned width, unsigned height) {
  exr_path_segment rect[5];
  exr_draw_style style = exr_draw_style_defaults();
  if (rgba[3] <= 0) return EXR_OK;
  memset(rect, 0, sizeof(rect));
  rect[0].verb = EXR_PATH_MOVE; rect[0].points[0] = (exr_path_point){0, 0};
  rect[1].verb = EXR_PATH_LINE; rect[1].points[0] = (exr_path_point){width, 0};
  rect[2].verb = EXR_PATH_LINE; rect[2].points[0] = (exr_path_point){width, height};
  rect[3].verb = EXR_PATH_LINE; rect[3].points[0] = (exr_path_point){0, height};
  rect[4].verb = EXR_PATH_CLOSE;
  style.fill = pack_rgba(rgba);
  style.flags = EXR_DRAW_FILL;
  style.rule = EXR_FILL_NONZERO;
  return exr_canvas_path(canvas, rect, 5, NULL, &style, c->error);
}

static exr_status build_gradient(colr_context *c, const FT_COLR_Paint *paint, colr_gradient *built) {
  colr_gradient gradient;
  exr_status status;
  memset(&gradient, 0, sizeof(gradient));
  if (paint->format == FT_COLR_PAINTFORMAT_LINEAR_GRADIENT) {
    const FT_PaintLinearGradient *g = &paint->u.linear_gradient;
    if (!g->p1.x && !g->p1.y && !g->p2.x && !g->p2.y) return fail(c, EXR_FONT, "Degenerate linear gradient");
    gradient.kind = 1;
    gradient.geometry[0] = (double)g->p0.x/65536.0*c->em;
    gradient.geometry[1] = (double)g->p0.y/65536.0*c->em;
    gradient.geometry[2] = (double)g->p1.x/65536.0*c->em;
    gradient.geometry[3] = (double)g->p1.y/65536.0*c->em;
    gradient.geometry[4] = (double)g->p2.x/65536.0*c->em;
    gradient.geometry[5] = (double)g->p2.y/65536.0*c->em;
    status = read_stops(c, &g->colorline, &gradient);
  } else if (paint->format == FT_COLR_PAINTFORMAT_RADIAL_GRADIENT) {
    const FT_PaintRadialGradient *g = &paint->u.radial_gradient;
    if (g->r0 < 0 || g->r1 < 0) return fail(c, EXR_FONT, "Negative radial gradient radius");
    gradient.kind = 2;
    gradient.geometry[0] = (double)g->c0.x/65536.0*c->em;
    gradient.geometry[1] = (double)g->c0.y/65536.0*c->em;
    gradient.geometry[2] = (double)g->r0/65536.0*c->em;
    gradient.geometry[3] = (double)g->c1.x/65536.0*c->em;
    gradient.geometry[4] = (double)g->c1.y/65536.0*c->em;
    gradient.geometry[5] = (double)g->r1/65536.0*c->em;
    status = read_stops(c, &g->colorline, &gradient);
  } else {
    const FT_PaintSweepGradient *g = &paint->u.sweep_gradient;
    gradient.kind = 3;
    gradient.geometry[0] = (double)g->center.x/65536.0*c->em;
    gradient.geometry[1] = (double)g->center.y/65536.0*c->em;
    /* FreeType returns the raw F2Dot14 value; the encoded angle carries a
       180-degree bias, so zero in the table means -180 degrees. */
    gradient.geometry[2] = ((double)g->start_angle/65536.0 + 1.0)*3.14159265358979323846;
    gradient.geometry[3] = ((double)g->end_angle/65536.0 + 1.0)*3.14159265358979323846;
    status = read_stops(c, &g->colorline, &gradient);
  }
  if (status != EXR_OK) return status;
  if (!exr_vector_work(c->work, gradient.stop_count * 2)) return fail(c, EXR_LIMIT, "Gradient work exceeds budget");
  *built = gradient;
  return EXR_OK;
}

static exr_status paint_gradient(colr_context *c, exr_canvas *canvas, colr_gradient *gradient,
                                 const double matrix[6]) {
  exr_paint_source source;
  memset(&source, 0, sizeof(source));
  source.struct_size = sizeof(source);
  source.sample = sample_gradient;
  source.context = gradient;
  return exr_canvas_paint(canvas, &source, matrix, 1.0, c->error);
}

static int blend_mode(FT_Composite_Mode mode, exr_blend_mode *out) {
  switch (mode) {
    case FT_COLR_COMPOSITE_SRC_OVER: *out = EXR_BLEND_NORMAL; return 1;
    case FT_COLR_COMPOSITE_SCREEN: *out = EXR_BLEND_SCREEN; return 1;
    case FT_COLR_COMPOSITE_OVERLAY: *out = EXR_BLEND_OVERLAY; return 1;
    case FT_COLR_COMPOSITE_DARKEN: *out = EXR_BLEND_DARKEN; return 1;
    case FT_COLR_COMPOSITE_LIGHTEN: *out = EXR_BLEND_LIGHTEN; return 1;
    case FT_COLR_COMPOSITE_COLOR_DODGE: *out = EXR_BLEND_COLOR_DODGE; return 1;
    case FT_COLR_COMPOSITE_COLOR_BURN: *out = EXR_BLEND_COLOR_BURN; return 1;
    case FT_COLR_COMPOSITE_HARD_LIGHT: *out = EXR_BLEND_HARD_LIGHT; return 1;
    case FT_COLR_COMPOSITE_SOFT_LIGHT: *out = EXR_BLEND_SOFT_LIGHT; return 1;
    case FT_COLR_COMPOSITE_DIFFERENCE: *out = EXR_BLEND_DIFFERENCE; return 1;
    case FT_COLR_COMPOSITE_EXCLUSION: *out = EXR_BLEND_EXCLUSION; return 1;
    case FT_COLR_COMPOSITE_MULTIPLY: *out = EXR_BLEND_MULTIPLY; return 1;
    case FT_COLR_COMPOSITE_HSL_HUE: *out = EXR_BLEND_HUE; return 1;
    case FT_COLR_COMPOSITE_HSL_SATURATION: *out = EXR_BLEND_SATURATION; return 1;
    case FT_COLR_COMPOSITE_HSL_COLOR: *out = EXR_BLEND_COLOR; return 1;
    case FT_COLR_COMPOSITE_HSL_LUMINOSITY: *out = EXR_BLEND_LUMINOSITY; return 1;
    default: return 0;
  }
}

static exr_status paint_glyph(colr_context *c, uint32_t glyph, const FT_OpaquePaint *child,
                              const double matrix[6], exr_canvas *canvas, unsigned depth);

static exr_status walk(colr_context *c, FT_OpaquePaint opaque, const double matrix[6],
                       exr_canvas *canvas, unsigned depth) {
  FT_COLR_Paint paint;
  FT_OpaquePaint child;
  FT_LayerIterator layers;
  exr_status status;
  if (depth >= COLR_MAX_DEPTH) return fail(c, EXR_LIMIT, "COLR paint graph exceeds 64 levels");
  if (++c->nodes > COLR_MAX_NODES) return fail(c, EXR_LIMIT, "COLR paint graph exceeds 4096 nodes");
  if (!exr_vector_work(c->work, 1)) return fail(c, EXR_LIMIT, "COLR paint work exceeds budget");
  if (!(c->nodes & 63)) {
    status = exr_control_cancel(c->control, c->error);
    if (status != EXR_OK) return status;
  }
  if (!finite_matrix(matrix)) return fail(c, EXR_LIMIT, "COLR paint transform exceeds precision");
  if (!FT_Get_Paint(c->face->face, opaque, &paint)) return fail(c, EXR_FONT, "Cannot read COLR paint node");
  switch (paint.format) {
    case FT_COLR_PAINTFORMAT_COLR_LAYERS:
      layers = paint.u.colr_layers.layer_iterator;
      while (FT_Get_Paint_Layers(c->face->face, &layers, &child)) {
        status = walk(c, child, matrix, canvas, depth + 1);
        if (status != EXR_OK) return status;
      }
      return EXR_OK;
    case FT_COLR_PAINTFORMAT_SOLID: {
      double rgba[4] = {0, 0, 0, 0};
      status = color_index(c, &paint.u.solid.color, rgba);
      if (status != EXR_OK) return status;
      if (!canvas || c->measuring) return EXR_OK;
      {
        const exr_bitmap *target = exr_canvas_bitmap(canvas);
        if (!target) return fail(c, EXR_FONT, "COLR v1 canvas is unavailable");
        return render_solid(c, canvas, rgba, target->width, target->height);
      }
    }
    case FT_COLR_PAINTFORMAT_LINEAR_GRADIENT:
    case FT_COLR_PAINTFORMAT_RADIAL_GRADIENT:
    case FT_COLR_PAINTFORMAT_SWEEP_GRADIENT: {
      colr_gradient gradient;
      status = build_gradient(c, &paint, &gradient);
      if (status != EXR_OK) return status;
      if (!canvas || c->measuring) return EXR_OK;
      return paint_gradient(c, canvas, &gradient, matrix);
    }
    case FT_COLR_PAINTFORMAT_GLYPH:
      return paint_glyph(c, paint.u.glyph.glyphID, &paint.u.glyph.paint, matrix, canvas, depth);
    case FT_COLR_PAINTFORMAT_COLR_GLYPH: {
      unsigned i;
      uint32_t glyph = paint.u.colr_glyph.glyphID;
      FT_OpaquePaint root = {0};
      if (c->glyph_depth >= COLR_MAX_GLYPHS) return fail(c, EXR_LIMIT, "COLR paint glyph recursion exceeds 16");
      for (i = 0; i < c->glyph_depth; i++)
        if (c->glyphs[i] == glyph) return fail(c, EXR_FONT, "Cyclic COLR paint glyph reference");
      if (!FT_Get_Color_Glyph_Paint(c->face->face, glyph, FT_COLOR_NO_ROOT_TRANSFORM, &root))
        return fail(c, EXR_FONT, "COLR paint references a missing color glyph");
      c->glyphs[c->glyph_depth++] = glyph;
      status = walk(c, root, matrix, canvas, depth + 1);
      c->glyph_depth--;
      return status;
    }
    case FT_COLR_PAINTFORMAT_TRANSFORM: {
      double t[6], next[6];
      FT_Affine23 a = paint.u.transform.affine;
      t[0] = (double)a.xx/65536.0; t[1] = (double)a.yx/65536.0;
      t[2] = (double)a.xy/65536.0; t[3] = (double)a.yy/65536.0;
      t[4] = (double)a.dx/65536.0*c->em; t[5] = (double)a.dy/65536.0*c->em;
      matrix_multiply(matrix, t, next);
      return walk(c, paint.u.transform.paint, next, canvas, depth + 1);
    }
    case FT_COLR_PAINTFORMAT_TRANSLATE: {
      double t[6] = {1, 0, 0, 1, (double)paint.u.translate.dx/65536.0*c->em,
                     (double)paint.u.translate.dy/65536.0*c->em}, next[6];
      matrix_multiply(matrix, t, next);
      return walk(c, paint.u.translate.paint, next, canvas, depth + 1);
    }
    case FT_COLR_PAINTFORMAT_SCALE: {
      double sx = (double)paint.u.scale.scale_x/65536.0, sy = (double)paint.u.scale.scale_y/65536.0;
      double cx = (double)paint.u.scale.center_x/65536.0*c->em, cy = (double)paint.u.scale.center_y/65536.0*c->em;
      double t[6] = {sx, 0, 0, sy, cx - sx*cx, cy - sy*cy}, next[6];
      if (!finite_matrix(t)) return fail(c, EXR_LIMIT, "COLR scale exceeds precision");
      matrix_multiply(matrix, t, next);
      return walk(c, paint.u.scale.paint, next, canvas, depth + 1);
    }
    case FT_COLR_PAINTFORMAT_ROTATE: {
      double angle = (double)paint.u.rotate.angle/65536.0*3.14159265358979323846;
      double cx = (double)paint.u.rotate.center_x/65536.0*c->em, cy = (double)paint.u.rotate.center_y/65536.0*c->em;
      double cs = cos(angle), sn = sin(angle), t[6], next[6];
      t[0] = cs; t[1] = sn; t[2] = -sn; t[3] = cs;
      t[4] = cx - cs*cx + sn*cy; t[5] = cy - sn*cx - cs*cy;
      matrix_multiply(matrix, t, next);
      return walk(c, paint.u.rotate.paint, next, canvas, depth + 1);
    }
    case FT_COLR_PAINTFORMAT_SKEW: {
      double ax = (double)paint.u.skew.x_skew_angle/65536.0*3.14159265358979323846;
      double ay = (double)paint.u.skew.y_skew_angle/65536.0*3.14159265358979323846;
      double cx = (double)paint.u.skew.center_x/65536.0*c->em, cy = (double)paint.u.skew.center_y/65536.0*c->em;
      double tx = tan(ax), ty = tan(ay), t[6], next[6];
      /* Counter-clockwise skew in font coordinates: the vertical axis tilts
         left while the horizontal axis tilts up. */
      t[0] = 1; t[1] = ty; t[2] = -tx; t[3] = 1;
      t[4] = tx*cy; t[5] = -ty*cx;
      if (!isfinite(tx) || !isfinite(ty) || fabs(tx) > 1e7 || fabs(ty) > 1e7)
        return fail(c, EXR_LIMIT, "COLR skew exceeds precision");
      matrix_multiply(matrix, t, next);
      return walk(c, paint.u.skew.paint, next, canvas, depth + 1);
    }
    case FT_COLR_PAINTFORMAT_COMPOSITE: {
      exr_blend_mode mode;
      if (!blend_mode(paint.u.composite.composite_mode, &mode))
        return fail(c, EXR_UNSUPPORTED, "COLR composite mode is unsupported");
      status = walk(c, paint.u.composite.backdrop_paint, matrix, canvas, depth + 1);
      if (status != EXR_OK) return status;
      if (!canvas || c->measuring) return walk(c, paint.u.composite.source_paint, matrix, canvas, depth + 1);
      if (mode == EXR_BLEND_NORMAL) return walk(c, paint.u.composite.source_paint, matrix, canvas, depth + 1);
      status = exr_canvas_begin_group(canvas, 1.0, mode, 0, c->error);
      if (status != EXR_OK) return status;
      status = walk(c, paint.u.composite.source_paint, matrix, canvas, depth + 1);
      {
        exr_status end = exr_canvas_end_layer(canvas, status == EXR_OK, c->error);
        if (status == EXR_OK) status = end;
      }
      return status;
    }
    default:
      return fail(c, EXR_UNSUPPORTED, "COLR paint format is unsupported");
  }
}

static exr_status paint_glyph(colr_context *c, uint32_t glyph, const FT_OpaquePaint *child,
                              const double matrix[6], exr_canvas *canvas, unsigned depth) {
  exr_status status;
  if (c->measuring) {
    status = glyph_bounds(c, glyph, matrix);
    if (status != EXR_OK) return status;
    return walk(c, *child, matrix, canvas, depth + 1);
  }
  if (!canvas) return EXR_OK;
  {
    exr_path_segment *segments = NULL;
    size_t count = 0;
    status = exr_font_outline(c->face->face, glyph, &segments, &count, c->work, c->control, c->error);
    if (status != EXR_OK) return status;
    if (!count) { free(segments); return EXR_OK; }
    status = exr_canvas_save(canvas, c->error);
    if (status == EXR_OK)
      status = exr_canvas_clip(canvas, segments, count, matrix, EXR_FILL_NONZERO, c->error);
    free(segments);
    if (status != EXR_OK) return status;
    status = walk(c, *child, matrix, canvas, depth + 1);
    {
      exr_status restore = exr_canvas_restore(canvas, c->error);
      if (status == EXR_OK) status = restore;
    }
    return status;
  }
}

static void clear_context(colr_context *c) {
  c->nodes = 0;
  c->has_bounds = 0;
  c->glyph_depth = 0;
  c->measuring = 0;
}

exr_status exr_font_colrv1(exr_face *face, uint32_t glyph, float pixels, uint32_t foreground,
                           exr_color_surface *out, size_t *work, const exr_control *control, exr_error *error) {
  colr_context c;
  FT_OpaquePaint root = {0};
  exr_status status;
  double clip[4];
  int has_clip = 0;
  size_t local_work = 0;
  memset(out, 0, sizeof(*out));
  if (!face || !work) return exr_fail(error, EXR_ARGUMENT, "Invalid COLR v1 render input");
  if (!(pixels > 0) || !isfinite(pixels) || pixels > 4096) return exr_fail(error, EXR_ARGUMENT, "Invalid COLR v1 glyph size");
  if (glyph >= (uint32_t)face->face->num_glyphs) return exr_fail(error, EXR_ARGUMENT, "Invalid COLR v1 glyph index");
  if (exr_control_cancel(control, error) != EXR_OK) return EXR_CANCELLED;
  if (!FT_Get_Color_Glyph_Paint(face->face, glyph, FT_COLOR_NO_ROOT_TRANSFORM, &root)) return EXR_OK;
  if (!face->face->units_per_EM) return exr_fail(error, EXR_FONT, "COLR v1 glyph lacks design units");
  memset(&c, 0, sizeof(c));
  c.face = face; c.error = error; c.control = control; c.work = work ? work : &local_work;
  c.foreground = foreground; c.em = 1000.0 / face->face->units_per_EM;
  c.scale = (double)pixels / 1000.0;
  c.measuring = 1;
  c.glyphs[c.glyph_depth++] = glyph;
  status = walk(&c, root, (const double[6]){1, 0, 0, 1, 0, 0}, NULL, 0);
  if (status != EXR_OK) return status;
  if (!c.has_bounds) return EXR_OK;
  if (c.has_bounds == 2) return exr_fail(error, EXR_LIMIT, "COLR v1 paint bounds exceed precision");
  status = clip_box_bounds(face, c.em, glyph, &has_clip, clip, error);
  if (status != EXR_OK) return status;
  if (has_clip) {
    c.bounds[0] = clip[0]; c.bounds[1] = clip[1]; c.bounds[2] = clip[2]; c.bounds[3] = clip[3];
  }
  {
    double scale = c.scale;
    double left = floor(c.bounds[0]*scale), right = ceil(c.bounds[2]*scale);
    double top = ceil(c.bounds[3]*scale), bottom = floor(c.bounds[1]*scale);
    long width = (long)(right - left), height = (long)(top - bottom);
    exr_canvas_config config;
    exr_canvas *canvas = NULL;
    exr_bitmap bitmap = {0};
    if (!(width > 0 && height > 0)) return EXR_OK;
    if (width > (long)COLR_MAX_REGION || height > (long)COLR_MAX_REGION ||
        (uint64_t)width*(uint64_t)height > COLR_MAX_PIXELS)
      return exr_fail(error, EXR_LIMIT, "COLR v1 glyph surface exceeds limits");
    if (!exr_vector_work(work, (size_t)width*(size_t)height))
      return exr_fail(error, EXR_LIMIT, "COLR v1 glyph surface exceeds raster budget");
    memset(&config, 0, sizeof(config));
    config.width = (uint32_t)width; config.height = (uint32_t)height; config.channels = 4;
    config.background = 0;
    if (control) config.control = *control;
    status = exr_canvas_create(&config, &canvas, error);
    if (status != EXR_OK) return status;
    clear_context(&c);
    status = walk(&c, root, (const double[6]){scale, 0, 0, -scale, -left, top}, canvas, 0);
    if (status == EXR_OK) status = exr_canvas_take(canvas, &bitmap, error);
    exr_canvas_free(canvas);
    if (status != EXR_OK) return status;
    out->bitmap = bitmap;
    out->left = (float)left;
    out->top = (float)-top;
  }
  return EXR_OK;
}

exr_status exr_font_color_info_get(exr_font *font, size_t index, uint32_t glyph,
                                   exr_font_color_info *out, const exr_control *control, exr_error *error) {
  exr_face *face;
  FT_OpaquePaint root = {0};
  FT_ULong size = 0;
  unsigned char header[34];
  double clip[4];
  int has_clip = 0;
  exr_status status;
  size_t local_work = 0;
  if (!out || !out->struct_size) return exr_fail(error, EXR_ARGUMENT, "Missing font color info output");
  if (out->struct_size < sizeof(*out)) return exr_fail(error, EXR_ARGUMENT, "Font color info output is too small");
  if (out->struct_size > sizeof(*out)) {
    size_t i;
    for (i = sizeof(*out); i < out->struct_size; i++)
      if (((const unsigned char *)out)[i]) return exr_fail(error, EXR_ARGUMENT, "Unsupported font color info extension");
  }
  memset(out, 0, sizeof(*out));
  out->struct_size = sizeof(*out);
  if (!font || index >= font->count || glyph >= (uint32_t)font->faces[index].face->num_glyphs)
    return exr_fail(error, EXR_ARGUMENT, "Invalid font color info query");
  face = &font->faces[index];
  if (exr_control_cancel(control, error) != EXR_OK) return EXR_CANCELLED;
  if (FT_Get_Color_Glyph_Paint(face->face, glyph, FT_COLOR_NO_ROOT_TRANSFORM, &root)) {
    out->kind = EXR_FONT_COLOR_COLR_V1;
  } else {
    FT_LayerIterator iterator = {0};
    FT_UInt layer, color;
    if (FT_Get_Color_Glyph_Layer(face->face, glyph, &layer, &color, &iterator)) {
      out->kind = EXR_FONT_COLOR_COLR_V0;
      if (iterator.num_layers > 256) return exr_fail(error, EXR_LIMIT, "Color glyph exceeds 256 layers");
    } else if (exr_font_svg_covers(face, glyph, &local_work, control, error)) {
      out->kind = EXR_FONT_COLOR_SVG;
    } else {
      return exr_fail(error, EXR_OK, "");
    }
  }
  if (out->kind != EXR_FONT_COLOR_COLR_V1) return exr_fail(error, EXR_OK, "");
  status = clip_box_bounds(face, 1000.0/face->face->units_per_EM, glyph, &has_clip, clip, error);
  if (status != EXR_OK) return status;
  if (has_clip) {
    out->has_clip_box = 1;
    out->clip_box[0] = (float)clip[0]; out->clip_box[1] = (float)clip[1];
    out->clip_box[2] = (float)clip[2]; out->clip_box[3] = (float)clip[3];
  }
  if (!FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('C', 'O', 'L', 'R'), 0, NULL, &size) && size >= 34) {
    FT_ULong length = sizeof(header);
    if (!FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('C', 'O', 'L', 'R'), 0, header, &length) && length >= 34) {
      unsigned version = (unsigned)header[0] << 8 | header[1];
      uint32_t var_map = (uint32_t)header[26] << 24 | (uint32_t)header[27] << 16 | (uint32_t)header[28] << 8 | header[29];
      uint32_t var_store = (uint32_t)header[30] << 24 | (uint32_t)header[31] << 16 | (uint32_t)header[32] << 8 | header[33];
      if (version == 1 && (var_map || var_store)) out->variable = 1;
    }
  }
  return exr_fail(error, EXR_OK, "");
}
