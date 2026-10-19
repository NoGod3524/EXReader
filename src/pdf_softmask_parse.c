/* SPDX-License-Identifier: MIT */
/* Validation of ISO 32000-1 11.6.5.2 soft-mask dictionaries; no raster deps. */
#include "pdf_internal.h"
#include <math.h>
#include <string.h>

static exr_status fail(exr_error *e, exr_status code, const char *message) { return exr_fail(e, code, message); }
static int name_is(exr_pdf_file *file, uint32_t id, const char *name) {
  const unsigned char *bytes; size_t size;
  bytes = exr_pdf_bytes(file, id, &size);
  return bytes && strlen(name) == size && !memcmp(bytes, name, size);
}
static int number(exr_pdf_file *file, uint32_t id, double *out) {
  const exr_pdf_value *v = exr_pdf_value_at(file, id);
  if (!v || (v->kind != EXR_PDF_INT && v->kind != EXR_PDF_REAL)) return 0;
  *out = v->kind == EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out) <= 1e7;
}


/* Validate a mask dictionary and report Alpha (0) or Luminosity (1). */
exr_status exr_pdf_soft_mask_kind(exr_pdf_file *file, uint32_t mask, int *kind, exr_error *e) {
  uint32_t id, g; const exr_pdf_value *v;
  *kind = 0;
  if (exr_pdf_resolve(file, mask, &mask, e) != EXR_OK) return e->code;
  v = exr_pdf_value_at(file, mask);
  if (!v || v->kind != EXR_PDF_DICT) return fail(e, EXR_FORMAT, "PDF soft mask is not a dictionary");
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "S"), &id, e) != EXR_OK) return e->code;
  if (name_is(file, id, "Luminosity")) *kind = 1;
  else if (!name_is(file, id, "Alpha")) return fail(e, EXR_FORMAT, "PDF soft mask subtype must be Alpha or Luminosity");
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "G"), &g, e) != EXR_OK) return e->code;
  v = exr_pdf_value_at(file, g);
  if (!v || v->kind != EXR_PDF_STREAM) return fail(e, EXR_FORMAT, "PDF soft mask group must be a form stream");
  /* ISO 32000-1 11.6.5.2: the group colour space decides how BC and the mask
     luminance are interpreted. Only device RGB and grey are supported. */
  if (exr_pdf_resolve(file, exr_pdf_get(file, g, "Group"), &id, e) != EXR_OK) return e->code;
  if (id != EXR_PDF_NONE && exr_pdf_value_at(file, id)->kind != EXR_PDF_NULL) {
    uint32_t cs;
    const exr_pdf_value *group = exr_pdf_value_at(file, id);
    if (group->kind != EXR_PDF_DICT) return fail(e, EXR_FORMAT, "PDF soft mask group must be a dictionary");
    if (exr_pdf_resolve(file, exr_pdf_get(file, id, "CS"), &cs, e) != EXR_OK) return e->code;
    if (cs != EXR_PDF_NONE && exr_pdf_value_at(file, cs)->kind != EXR_PDF_NULL &&
        !name_is(file, cs, "DeviceRGB") && !name_is(file, cs, "DeviceGray"))
      return fail(e, EXR_UNSUPPORTED, "PDF soft mask group colour space is not device RGB or grey");
  }
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "TR"), &id, e) != EXR_OK) return e->code;
  if (id != EXR_PDF_NONE && exr_pdf_value_at(file, id)->kind != EXR_PDF_NULL && !name_is(file, id, "Identity")) {
    /* Only the exponential function (type 2) is supported; anything else is a
       declared boundary rather than a silent approximation. */
    const exr_pdf_value *tr = exr_pdf_value_at(file, id);
    uint32_t type;
    double probe;
    if (tr->kind != EXR_PDF_DICT) return fail(e, EXR_FORMAT, "PDF soft mask transfer function must be a dictionary");
    if (exr_pdf_resolve(file, exr_pdf_get(file, id, "FunctionType"), &type, e) != EXR_OK) return e->code;
    if (type == EXR_PDF_NONE || !number(file, type, &probe) || probe != 2)
      return fail(e, EXR_UNSUPPORTED, "Only exponential PDF soft mask transfer functions are implemented");
  }
  if (exr_pdf_resolve(file, exr_pdf_get(file, mask, "BC"), &id, e) != EXR_OK) return e->code;
  if (id != EXR_PDF_NONE && exr_pdf_value_at(file, id)->kind != EXR_PDF_NULL) {
    double bc[4]; unsigned count = 0;
    v = exr_pdf_value_at(file, id);
    if (v->kind != EXR_PDF_ARRAY) return fail(e, EXR_FORMAT, "PDF soft mask backdrop must be an array");
    { uint32_t at = v->first; while (at != EXR_PDF_NONE) { uint32_t value; if (count == 4 || exr_pdf_resolve(file, at, &value, e) != EXR_OK || !number(file, value, &bc[count])) return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop"); count++; at = exr_pdf_value_at(file, at)->next; } }
    if (count != 1 && count != 3 && count != 4) return fail(e, EXR_FORMAT, "Invalid PDF soft mask backdrop length");
  }
  return EXR_OK;
}


