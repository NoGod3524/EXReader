/* SPDX-License-Identifier: GPL-3.0-only */
/* ISO 32000-1 11.6.5.2 graphics-state soft masks: render the G form into a
   page-sized 8-bit mask. Alpha uses the group alpha; Luminosity composites the
   group over BC and takes the 0.3/0.59/0.11 luminance. TR supports Identity. */
#include "pdf_raster_internal.h"
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

exr_status exr_pdf_soft_mask_build(exr_pdf_file *file, uint32_t mask, const double set_matrix[6],
                                   unsigned width, unsigned height, unsigned char **out,
                                   size_t *work, const exr_control *control, exr_error *e) {
  uint32_t form, id, resources = EXR_PDF_NONE; const unsigned char *data = NULL; size_t size = 0, i;
  double matrix[6], local[6], box[4], bc[4] = {0, 0, 0, 0}, clip[4]; unsigned char *pixels = NULL, *result = NULL;
  const exr_pdf_value *v; int kind = 0, count = 0; exr_bitmap bitmap = {0}; exr_pdf_raster_config config = {0}; exr_status status;
  *out = NULL;
  status = exr_pdf_soft_mask_kind(file, mask, &kind, e); if (status != EXR_OK) return status;
  if (exr_pdf_resolve(file, mask, &mask, e) != EXR_OK) return e->code;
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "G"), &form, e) != EXR_OK) return e->code;
  if (exr_pdf_stream_data(file, form, &data, &size, e) != EXR_OK) return e->code;
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "BBox"), &id, e) != EXR_OK) return e->code;
  if (!numbers(file, id, box, 4) || box[0] > box[2] || box[1] > box[3]) return fail(e, EXR_FORMAT, "Invalid PDF soft mask bounding box");
  local[0] = 1; local[1] = 0; local[2] = 0; local[3] = 1; local[4] = 0; local[5] = 0;
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "Matrix"), &id, e) != EXR_OK) return e->code;
  if (id != EXR_PDF_NONE) { v = exr_pdf_value_at(file, id); if (v->kind != EXR_PDF_NULL && !numbers(file, id, local, 6)) return fail(e, EXR_FORMAT, "Invalid PDF soft mask matrix"); }
  multiply(set_matrix, local, matrix);
  if (exr_pdf_resolve(file, exr_pdf_get(file, form, "Resources"), &resources, e) != EXR_OK) return e->code;
  if (resources == EXR_PDF_NONE || exr_pdf_value_at(file, resources)->kind == EXR_PDF_NULL) resources = EXR_PDF_NONE;
  /* Device-space clip from the transformed BBox corners. */
  {
    double xs[4], ys[4]; int corner;
    for (corner = 0; corner < 4; corner++) {
      double x = box[(corner & 1) ? 2 : 0], y = box[(corner & 2) ? 3 : 1];
      xs[corner] = matrix[0] * x + matrix[2] * y + matrix[4];
      ys[corner] = matrix[1] * x + matrix[3] * y + matrix[5];
    }
    clip[0] = fmax(0, fmin(fmin(xs[0], xs[1]), fmin(xs[2], xs[3])));
    clip[1] = fmax(0, fmin(fmin(ys[0], ys[1]), fmin(ys[2], ys[3])));
    clip[2] = fmin((double)width, fmax(fmax(xs[0], xs[1]), fmax(xs[2], xs[3])));
    clip[3] = fmin((double)height, fmax(fmax(ys[0], ys[1]), fmax(ys[2], ys[3])));
    if (clip[2] <= clip[0] || clip[3] <= clip[1]) return fail(e, EXR_FORMAT, "PDF soft mask is outside the device area");
  }
  if (kind) {
    if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "BC"), &id, e) != EXR_OK) return e->code;
    if (id != EXR_PDF_NONE && exr_pdf_value_at(file, id)->kind != EXR_PDF_NULL) {
      double tmp[4];
      v = exr_pdf_value_at(file, id);
      { uint32_t at = v->first; while (at != EXR_PDF_NONE && count < 4) { uint32_t value; if (exr_pdf_resolve(file, at, &value, e) != EXR_OK || !number(file, value, &tmp[count])) return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop"); count++; at = exr_pdf_value_at(file, at)->next; } }
      if (count == 1) { bc[0] = bc[1] = bc[2] = tmp[0]; }
      else if (count == 3) { bc[0] = tmp[0]; bc[1] = tmp[1]; bc[2] = tmp[2]; }
      else if (count == 4) { bc[0] = 1 - fmin(1, tmp[0] + tmp[3]); bc[1] = 1 - fmin(1, tmp[1] + tmp[3]); bc[2] = 1 - fmin(1, tmp[2] + tmp[3]); }
      else return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop length");
    }
  }
  (void)work;
  config.width = width; config.height = height; config.channels = 4; config.background = 0;
  config.initial_clip = clip; config.mask_budget = 0;
  status = exr_pdf_raster_content(file, resources, data, size, matrix, &config, control, &bitmap, e);
  if (status != EXR_OK) return status;
  result = malloc((size_t)width * height);
  if (!result) { free(bitmap.pixels); return fail(e, EXR_MEMORY, "PDF soft mask allocation failed"); }
  pixels = bitmap.pixels;
  for (i = 0; i < (size_t)width * height; i++) {
    double a = pixels[i * 4 + 3] / 255.;
    if (kind) {
      double v0 = pixels[i * 4] / 255. * a + bc[0] * (1 - a);
      double v1 = pixels[i * 4 + 1] / 255. * a + bc[1] * (1 - a);
      double v2 = pixels[i * 4 + 2] / 255. * a + bc[2] * (1 - a);
      double lum = .3 * v0 + .59 * v1 + .11 * v2;
      result[i] = (unsigned char)fmax(0, fmin(255, floor(lum * 255 + .5)));
    } else result[i] = (unsigned char)a * 255;
  }
  free(bitmap.pixels);
  *out = result;
  return EXR_OK;
}
