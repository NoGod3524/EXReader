/* SPDX-License-Identifier: MIT
 * Native accessibility for the Windows product host.
 *
 * The painted page is a custom control: Windows can only answer for it when the
 * host provides an element itself. This module implements one - a UI Automation
 * provider on EXReaderPage that exposes the text the public SDK projection
 * already produced for the current page and the host's own selection as a text
 * selection range. It reads the same frame text the copy command reads; there is
 * no second text pipeline and nothing is invented for assistive technology.
 *
 * It also owns the keyboard-continuity helpers the audit needs: a focus guard for
 * commands that disable themselves, a truthful owner-disabled state for modal
 * dialogs, and change events for the status line and the page.
 */
/* MIDL-generated headers spell their C interfaces as "interface"; C has no such
   keyword, and the standard workaround is to define it before the include. */
#ifndef interface
#define interface struct
#endif
#include <uiautomationcore.h>
#include <uiautomationcoreapi.h>
#include <uiautomationclient.h>
#include <oleacc.h>
#pragma comment(lib, "uiautomationcore.lib")
#pragma comment(lib, "oleacc.lib")
#pragma comment(lib, "oleaut32.lib")

typedef struct host_a11y_page host_a11y_page;
typedef struct host_a11y_range host_a11y_range;

struct host_a11y_range {
  ITextRangeProvider iface;
  host_a11y_page *owner;
  int start, end; /* UTF-16 code units inside the current page text */
};

struct host_a11y_page {
  IRawElementProviderSimple simple; /* first member: the element identity */
  ITextProvider text;
  IValueProvider value;
  LONG refs;
};

static host_a11y_page *host_a11y_element;

static void host_a11y_page_changed(int selection_only);

/* ---- page text: the public SDK projection, exactly as the copy path reads it ---- */
static int host_a11y_page_text(const char **utf8, size_t *bytes, size_t *base) {
  *utf8 = NULL; *bytes = 0; *base = 0;
  if (!g.has_current || !g.frame.valid) return 0;
  if (g.frame.fixed) {
    if (!g.frame.fixed_text) return 0;
    *utf8 = exr_fixed_text_string(g.frame.fixed_text, bytes);
    *base = 0;
    return *utf8 != NULL;
  }
  if (!g.frame.utf8 || !g.frame.text_bytes) return 0;
  *utf8 = g.frame.utf8; *bytes = g.frame.text_bytes; *base = g.frame.range_start;
  return 1;
}

static int host_a11y_units(const char *utf8, size_t bytes) {
  if (!utf8 || !bytes) return 0;
  return MultiByteToWideChar(CP_UTF8, 0, utf8, (int)bytes, NULL, 0);
}
/* Byte length of the first `units` UTF-16 characters: a four-byte UTF-8 sequence
   is one surrogate pair, every other leading byte is one BMP character. */
static size_t host_a11y_bytes(const char *utf8, int units) {
  const char *at = utf8;
  int remaining = units;
  if (!utf8 || units <= 0) return 0;
  while (remaining > 0 && *at) {
    unsigned char lead = (unsigned char)*at;
    int width = lead < 0x80 ? 1 : (lead >> 5) == 6 ? 2 : (lead >> 4) == 14 ? 3 : (lead >> 3) == 30 ? 4 : 1;
    at += width;
    remaining -= (width == 4) ? 2 : 1;
  }
  return (size_t)(at - utf8);
}

static int host_a11y_page_units(void) {
  const char *utf8; size_t bytes, base;
  if (!host_a11y_page_text(&utf8, &bytes, &base)) return 0;
  return host_a11y_units(utf8, bytes);
}

static void host_a11y_selection(int *start, int *end) {
  const char *utf8; size_t bytes, base, a, b;
  *start = *end = 0;
  if (!host_a11y_page_text(&utf8, &bytes, &base)) return;
  if (!g.selection.active) return;
  a = g.selection.start; b = g.selection.end;
  if (a > b) { size_t swap = a; a = b; b = swap; }
  if (a < base) a = base;
  if (b > base + bytes) b = base + bytes;
  if (b < a) b = a;
  *start = host_a11y_units(utf8, a - base);
  *end = host_a11y_units(utf8, b - base);
}

static void host_a11y_apply_selection(int start, int end) {
  const char *utf8; size_t bytes, base; int total;
  if (!host_a11y_page_text(&utf8, &bytes, &base)) return;
  total = host_a11y_units(utf8, bytes);
  if (start < 0) start = 0;
  if (end > total) end = total;
  if (end < start) end = start;
  g.selection.start = base + host_a11y_bytes(utf8, start);
  g.selection.end = base + host_a11y_bytes(utf8, end);
  g.selection.page = g.frame.page;
  g.selection.fixed = g.frame.fixed;
  g.selection.active = g.selection.start < g.selection.end;
  InvalidateRect(g.page, NULL, FALSE);
  host_a11y_page_changed(1);
}

/* ---- object lifetime ------------------------------------------------ */
static LONG host_a11y_addref(host_a11y_page *self) { return InterlockedIncrement(&self->refs); }

static LONG host_a11y_release(host_a11y_page *self) {
  LONG left = InterlockedDecrement(&self->refs);
  if (!left) { if (host_a11y_element == self) host_a11y_element = NULL; free(self); }
  return left;
}

static HRESULT host_a11y_qi(host_a11y_page *owner, void *value, REFIID id, void **out, const IID *iid) {
  if (!out) return E_INVALIDARG;
  if (IsEqualIID(id, &IID_IUnknown) || IsEqualIID(id, iid)) {
    host_a11y_addref(owner);
    *out = value;
    return S_OK;
  }
  *out = NULL;
  return E_NOINTERFACE;
}

static host_a11y_page *host_a11y_from_text(ITextProvider *self) {
  return (host_a11y_page *)((char *)self - offsetof(host_a11y_page, text));
}

static host_a11y_page *host_a11y_from_value(IValueProvider *self) {
  return (host_a11y_page *)((char *)self - offsetof(host_a11y_page, value));
}

/* ---- IRawElementProviderSimple -------------------------------------- */
static HRESULT STDMETHODCALLTYPE host_a11y_simple_query(IRawElementProviderSimple *self, REFIID id, void **out) {
  return host_a11y_qi((host_a11y_page *)self, self, id, out, &IID_IRawElementProviderSimple);
}

static ULONG STDMETHODCALLTYPE host_a11y_simple_addref(IRawElementProviderSimple *self) {
  return (ULONG)host_a11y_addref((host_a11y_page *)self);
}

static ULONG STDMETHODCALLTYPE host_a11y_simple_release(IRawElementProviderSimple *self) {
  return (ULONG)host_a11y_release((host_a11y_page *)self);
}

static HRESULT STDMETHODCALLTYPE host_a11y_simple_options(IRawElementProviderSimple *self, enum ProviderOptions *out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  *out = ProviderOptions_ServerSideProvider;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_simple_pattern(IRawElementProviderSimple *self, PROPERTYID pattern, IUnknown **out) {
  host_a11y_page *owner = (host_a11y_page *)self;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (pattern == UIA_TextPatternId) { host_a11y_addref(owner); *out = (IUnknown *)&owner->text; return S_OK; }
  if (pattern == UIA_ValuePatternId) { host_a11y_addref(owner); *out = (IUnknown *)&owner->value; return S_OK; }
  return S_OK;
}

static HRESULT host_a11y_bstr(VARIANT *out, const wchar_t *text) {
  out->vt = VT_BSTR;
  out->bstrVal = SysAllocString(text);
  return out->bstrVal ? S_OK : E_OUTOFMEMORY;
}

static HRESULT STDMETHODCALLTYPE host_a11y_simple_property(IRawElementProviderSimple *self, PROPERTYID id, VARIANT *out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  VariantInit(out);
  /* The UIA_* ids are const variables in C, so they cannot label a case. */
  if (id == UIA_NamePropertyId) return host_a11y_bstr(out, L"\u9605\u8bfb\u533a\u57df");
  if (id == UIA_AutomationIdPropertyId) return host_a11y_bstr(out, L"IDC_PAGE");
  if (id == UIA_ClassNamePropertyId) return host_a11y_bstr(out, L"EXReaderPage");
  if (id == UIA_FrameworkIdPropertyId) return host_a11y_bstr(out, L"Win32");
  if (id == UIA_LocalizedControlTypePropertyId) return host_a11y_bstr(out, L"\u6b63\u6587");
  if (id == UIA_HelpTextPropertyId) return host_a11y_bstr(out, L"\u9009\u62e9\u6587\u5b57\u540e\u53ef\u590d\u5236\u5f15\u7528\u6216\u6dfb\u52a0\u6807\u6ce8");
  if (id == UIA_ControlTypePropertyId) { out->vt = VT_I4; out->lVal = UIA_DocumentControlTypeId; return S_OK; }
  if (id == UIA_IsKeyboardFocusablePropertyId) { out->vt = VT_BOOL; out->boolVal = VARIANT_TRUE; return S_OK; }
  if (id == UIA_HasKeyboardFocusPropertyId) {
    out->vt = VT_BOOL; out->boolVal = (GetFocus() == g.page) ? VARIANT_TRUE : VARIANT_FALSE; return S_OK;
  }
  if (id == UIA_IsEnabledPropertyId) {
    out->vt = VT_BOOL; out->boolVal = (g.page && IsWindowEnabled(g.page)) ? VARIANT_TRUE : VARIANT_FALSE; return S_OK;
  }
  if (id == UIA_IsControlElementPropertyId || id == UIA_IsContentElementPropertyId ||
      id == UIA_IsTextPatternAvailablePropertyId || id == UIA_IsValuePatternAvailablePropertyId) {
    out->vt = VT_BOOL; out->boolVal = VARIANT_TRUE; return S_OK;
  }
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_simple_host(IRawElementProviderSimple *self, IRawElementProviderSimple **out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (!g.page) return S_OK;
  return UiaHostProviderFromHwnd(g.page, out);
}

static IRawElementProviderSimpleVtbl host_a11y_simple_vtbl = {
  host_a11y_simple_query, host_a11y_simple_addref, host_a11y_simple_release,
  host_a11y_simple_options, host_a11y_simple_pattern, host_a11y_simple_property,
  host_a11y_simple_host
};

/* ---- ITextRangeProvider --------------------------------------------- */
static host_a11y_range *host_a11y_new_range(host_a11y_page *owner, int start, int end) {
  host_a11y_range *range;
  if (!owner) return NULL;
  range = (host_a11y_range *)calloc(1, sizeof(*range));
  if (!range) return NULL;
  range->iface.lpVtbl = NULL; /* filled below by the caller's table */
  range->owner = owner;
  host_a11y_addref(owner);
  range->start = start;
  range->end = end;
  return range;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_query(ITextRangeProvider *self, REFIID id, void **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  return host_a11y_qi(range->owner, self, id, out, &IID_ITextRangeProvider);
}

static ULONG STDMETHODCALLTYPE host_a11y_range_addref(ITextRangeProvider *self) {
  host_a11y_range *range = (host_a11y_range *)self;
  host_a11y_addref(range->owner);
  return 1;
}

static ULONG STDMETHODCALLTYPE host_a11y_range_release(ITextRangeProvider *self) {
  host_a11y_range *range = (host_a11y_range *)self;
  host_a11y_page *owner = range->owner;
  free(range);
  host_a11y_release(owner);
  return 1;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_clone(ITextRangeProvider *self, ITextRangeProvider **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  host_a11y_range *copy;
  if (!out) return E_INVALIDARG;
  copy = host_a11y_new_range(range->owner, range->start, range->end);
  if (!copy) { *out = NULL; return E_OUTOFMEMORY; }
  copy->iface.lpVtbl = range->iface.lpVtbl;
  *out = &copy->iface;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_compare(ITextRangeProvider *self, ITextRangeProvider *other, BOOL *same) {
  host_a11y_range *a = (host_a11y_range *)self, *b = (host_a11y_range *)other;
  if (!same || !b) return E_INVALIDARG;
  *same = (a->start == b->start && a->end == b->end) ? TRUE : FALSE;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_compare_endpoints(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    ITextRangeProvider *other, enum TextPatternRangeEndpoint other_endpoint, int *result) {
  host_a11y_range *a = (host_a11y_range *)self, *b = (host_a11y_range *)other;
  int left, right;
  if (!result || !b) return E_INVALIDARG;
  left = endpoint == TextPatternRangeEndpoint_Start ? a->start : a->end;
  right = other_endpoint == TextPatternRangeEndpoint_Start ? b->start : b->end;
  *result = left < right ? -1 : left > right ? 1 : 0;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_expand(ITextRangeProvider *self, enum TextUnit unit) {
  host_a11y_range *range = (host_a11y_range *)self;
  int total = host_a11y_page_units();
  (void)unit;
  if (range->start < 0) range->start = 0;
  if (range->end > total) range->end = total;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_find_attribute(ITextRangeProvider *self, TEXTATTRIBUTEID id, VARIANT value,
    BOOL backwards, ITextRangeProvider **out) {
  (void)self; (void)id; (void)value; (void)backwards;
  if (out) *out = NULL;
  return UIA_E_NOTSUPPORTED;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_find_text(ITextRangeProvider *self, BSTR needle, BOOL backwards,
    BOOL ignore_case, ITextRangeProvider **out) {
  (void)self; (void)needle; (void)backwards; (void)ignore_case;
  if (out) *out = NULL;
  return UIA_E_NOTSUPPORTED;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_attribute(ITextRangeProvider *self, TEXTATTRIBUTEID id, VARIANT *out) {
  (void)self; (void)id;
  if (!out) return E_INVALIDARG;
  VariantInit(out);
  return UIA_E_NOTSUPPORTED;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_rects(ITextRangeProvider *self, SAFEARRAY **out) {
  SAFEARRAY *array; double *data; RECT bounds;
  (void)self;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (!g.page || !GetWindowRect(g.page, &bounds)) return S_OK;
  array = SafeArrayCreateVector(VT_R8, 0, 4);
  if (!array) return E_OUTOFMEMORY;
  if (FAILED(SafeArrayAccessData(array, (void **)&data))) { SafeArrayDestroy(array); return E_OUTOFMEMORY; }
  data[0] = (double)bounds.left; data[1] = (double)bounds.top;
  data[2] = (double)(bounds.right - bounds.left); data[3] = (double)(bounds.bottom - bounds.top);
  SafeArrayUnaccessData(array);
  *out = array;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_element(ITextRangeProvider *self, IRawElementProviderSimple **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  if (!out) return E_INVALIDARG;
  host_a11y_addref(range->owner);
  *out = &range->owner->simple;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_text(ITextRangeProvider *self, int max, BSTR *out) {
  host_a11y_range *range = (host_a11y_range *)self;
  const char *utf8; size_t bytes, base, prefix; int start, end, total, want;
  wchar_t *wide;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (!host_a11y_page_text(&utf8, &bytes, &base)) { *out = SysAllocString(L""); return *out ? S_OK : E_OUTOFMEMORY; }
  total = host_a11y_units(utf8, bytes);
  start = range->start; end = range->end;
  if (start < 0) start = 0;
  if (end > total) end = total;
  if (end < start) end = start;
  if (max >= 0 && end - start > max) end = start + max;
  if (end == start) { *out = SysAllocString(L""); return *out ? S_OK : E_OUTOFMEMORY; }
  prefix = host_a11y_bytes(utf8, start);
  want = end - start;
  wide = (wchar_t *)calloc((size_t)want + 1, sizeof(wchar_t));
  if (!wide) return E_OUTOFMEMORY;
  if (MultiByteToWideChar(CP_UTF8, 0, utf8 + prefix, (int)(host_a11y_bytes(utf8, end) - prefix), wide, want) <= 0) {
    free(wide);
    return E_FAIL;
  }
  wide[want] = 0;
  *out = SysAllocString(wide);
  free(wide);
  return *out ? S_OK : E_OUTOFMEMORY;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_move(ITextRangeProvider *self, enum TextUnit unit, int count, int *moved) {
  host_a11y_range *range = (host_a11y_range *)self;
  int total = host_a11y_page_units();
  (void)unit;
  if (moved) *moved = 0;
  if (!count) return S_OK;
  if (range->start + count < 0) count = -range->start;
  if (range->end + count > total) count = total - range->end;
  range->start += count; range->end += count;
  if (moved) *moved = count;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_move_endpoint(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    enum TextUnit unit, int count, int *moved) {
  host_a11y_range *range = (host_a11y_range *)self;
  int total = host_a11y_page_units();
  (void)unit;
  if (moved) *moved = 0;
  if (endpoint == TextPatternRangeEndpoint_Start) {
    int next = range->start + count;
    if (next < 0) next = 0;
    if (next > range->end) next = range->end;
    if (moved) *moved = next - range->start;
    range->start = next;
  } else {
    int next = range->end + count;
    if (next > total) next = total;
    if (next < range->start) next = range->start;
    if (moved) *moved = next - range->end;
    range->end = next;
  }
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_move_endpoint_by_range(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    ITextRangeProvider *other, enum TextPatternRangeEndpoint other_endpoint) {
  host_a11y_range *a = (host_a11y_range *)self, *b = (host_a11y_range *)other;
  int value;
  if (!b) return E_INVALIDARG;
  value = other_endpoint == TextPatternRangeEndpoint_Start ? b->start : b->end;
  if (endpoint == TextPatternRangeEndpoint_Start) {
    a->start = value;
    if (a->start > a->end) a->start = a->end;
  } else {
    a->end = value;
    if (a->end < a->start) a->end = a->start;
  }
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_select(ITextRangeProvider *self) {
  host_a11y_range *range = (host_a11y_range *)self;
  if (!g.page) return E_FAIL;
  if (GetFocus() != g.page) SetFocus(g.page);
  host_a11y_apply_selection(range->start, range->end);
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_add_to_selection(ITextRangeProvider *self) { return host_a11y_range_select(self); }

static HRESULT STDMETHODCALLTYPE host_a11y_range_remove_from_selection(ITextRangeProvider *self) { (void)self; return S_OK; }

static HRESULT STDMETHODCALLTYPE host_a11y_range_scroll(ITextRangeProvider *self, BOOL align) { (void)self; (void)align; return S_OK; }

static HRESULT STDMETHODCALLTYPE host_a11y_range_text_pattern(ITextRangeProvider *self, ITextProvider **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  if (!out) return E_INVALIDARG;
  host_a11y_addref(range->owner);
  *out = &range->owner->text;
  return S_OK;
}

static ITextRangeProviderVtbl host_a11y_range_vtbl = {
  host_a11y_range_query, host_a11y_range_addref, host_a11y_range_release,
  host_a11y_range_clone, host_a11y_range_compare, host_a11y_range_compare_endpoints,
  host_a11y_range_expand, host_a11y_range_find_attribute, host_a11y_range_find_text,
  host_a11y_range_attribute, host_a11y_range_rects, host_a11y_range_element,
  host_a11y_range_text, host_a11y_range_move, host_a11y_range_move_endpoint,
  host_a11y_range_move_endpoint_by_range, host_a11y_range_select,
  host_a11y_range_add_to_selection, host_a11y_range_remove_from_selection,
  host_a11y_range_scroll, host_a11y_range_text_pattern
};

static host_a11y_range *host_a11y_range_make(host_a11y_page *owner, int start, int end) {
  host_a11y_range *range = host_a11y_new_range(owner, start, end);
  if (range) range->iface.lpVtbl = &host_a11y_range_vtbl;
  return range;
}

/* ---- ITextProvider --------------------------------------------------- */
static HRESULT STDMETHODCALLTYPE host_a11y_text_query(ITextProvider *self, REFIID id, void **out) {
  host_a11y_page *owner = host_a11y_from_text(self);
  return host_a11y_qi(owner, self, id, out, &IID_ITextProvider);
}
static ULONG STDMETHODCALLTYPE host_a11y_text_addref(ITextProvider *self) { return (ULONG)host_a11y_addref(host_a11y_from_text(self)); }
static ULONG STDMETHODCALLTYPE host_a11y_text_release(ITextProvider *self) { return (ULONG)host_a11y_release(host_a11y_from_text(self)); }

static HRESULT host_a11y_range_array(host_a11y_range *range, SAFEARRAY **out) {
  SAFEARRAY *array; ITextRangeProvider **slot;
  if (!range) return E_OUTOFMEMORY;
  array = SafeArrayCreateVector(VT_UNKNOWN, 0, 1);
  if (!array) { host_a11y_range_release(&range->iface); return E_OUTOFMEMORY; }
  if (FAILED(SafeArrayAccessData(array, (void **)&slot))) {
    SafeArrayDestroy(array);
    host_a11y_range_release(&range->iface);
    return E_OUTOFMEMORY;
  }
  slot[0] = &range->iface;
  SafeArrayUnaccessData(array);
  *out = array;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_selection(ITextProvider *self, SAFEARRAY **out) {
  int start, end;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  host_a11y_selection(&start, &end);
  return host_a11y_range_array(host_a11y_range_make(host_a11y_from_text(self), start, end), out);
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_visible(ITextProvider *self, SAFEARRAY **out) {
  if (!out) return E_INVALIDARG;
  *out = NULL;
  return host_a11y_range_array(host_a11y_range_make(host_a11y_from_text(self), 0, host_a11y_page_units()), out);
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_from_child(ITextProvider *self, IRawElementProviderSimple *child, ITextRangeProvider **out) {
  (void)self; (void)child;
  if (out) *out = NULL;
  return UIA_E_NOTSUPPORTED;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_from_point(ITextProvider *self, struct UiaPoint point, ITextRangeProvider **out) {
  host_a11y_range *range; int start, end;
  (void)point;
  if (!out) return E_INVALIDARG;
  host_a11y_selection(&start, &end);
  range = host_a11y_range_make(host_a11y_from_text(self), start, end);
  if (!range) { *out = NULL; return E_OUTOFMEMORY; }
  *out = &range->iface;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_document(ITextProvider *self, ITextRangeProvider **out) {
  host_a11y_range *range;
  if (!out) return E_INVALIDARG;
  range = host_a11y_range_make(host_a11y_from_text(self), 0, host_a11y_page_units());
  if (!range) { *out = NULL; return E_OUTOFMEMORY; }
  *out = &range->iface;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_supported(ITextProvider *self, enum SupportedTextSelection *out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  *out = SupportedTextSelection_Single;
  return S_OK;
}

static ITextProviderVtbl host_a11y_text_vtbl = {
  host_a11y_text_query, host_a11y_text_addref, host_a11y_text_release,
  host_a11y_text_selection, host_a11y_text_visible, host_a11y_text_from_child,
  host_a11y_text_from_point, host_a11y_text_document, host_a11y_text_supported
};

/* ---- IValueProvider -------------------------------------------------- */
static HRESULT STDMETHODCALLTYPE host_a11y_value_query(IValueProvider *self, REFIID id, void **out) {
  host_a11y_page *owner = host_a11y_from_value(self);
  return host_a11y_qi(owner, self, id, out, &IID_IValueProvider);
}
static ULONG STDMETHODCALLTYPE host_a11y_value_addref(IValueProvider *self) { return (ULONG)host_a11y_addref(host_a11y_from_value(self)); }
static ULONG STDMETHODCALLTYPE host_a11y_value_release(IValueProvider *self) { return (ULONG)host_a11y_release(host_a11y_from_value(self)); }
static HRESULT STDMETHODCALLTYPE host_a11y_value_set(IValueProvider *self, LPCWSTR value) { (void)self; (void)value; return UIA_E_NOTSUPPORTED; }

static HRESULT STDMETHODCALLTYPE host_a11y_value_get(IValueProvider *self, BSTR *out) {
  host_a11y_page *owner = host_a11y_from_value(self);
  host_a11y_range *range; HRESULT result;
  if (!out) return E_INVALIDARG;
  range = host_a11y_range_make(owner, 0, host_a11y_page_units());
  if (!range) { *out = NULL; return E_OUTOFMEMORY; }
  result = host_a11y_range_text(&range->iface, -1, out);
  host_a11y_range_release(&range->iface);
  return result;
}

static HRESULT STDMETHODCALLTYPE host_a11y_value_readonly(IValueProvider *self, BOOL *out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  *out = TRUE;
  return S_OK;
}

static IValueProviderVtbl host_a11y_value_vtbl = {
  host_a11y_value_query, host_a11y_value_addref, host_a11y_value_release,
  host_a11y_value_set, host_a11y_value_get, host_a11y_value_readonly
};

static host_a11y_page *host_a11y_ensure_element(void) {
  if (host_a11y_element) return host_a11y_element;
  host_a11y_element = (host_a11y_page *)calloc(1, sizeof(host_a11y_page));
  if (!host_a11y_element) return NULL;
  host_a11y_element->simple.lpVtbl = &host_a11y_simple_vtbl;
  host_a11y_element->text.lpVtbl = &host_a11y_text_vtbl;
  host_a11y_element->value.lpVtbl = &host_a11y_value_vtbl;
  host_a11y_element->refs = 1;
  return host_a11y_element;
}

/* WM_GETOBJECT entry point for EXReaderPage. */
static LRESULT host_a11y_page_object(HWND window, WPARAM wparam, LPARAM lparam) {
  host_a11y_page *element;
  if ((LONG)lparam != UiaRootObjectId) return DefWindowProcW(window, WM_GETOBJECT, wparam, lparam);
  element = host_a11y_ensure_element();
  if (!element) return 0;
  host_a11y_addref(element);
  return UiaReturnRawElementProvider(window, wparam, lparam, &element->simple);
}

static void host_a11y_raise_page(int selection_only) {
  if (!host_a11y_element) return;
  if (UiaClientsAreListening()) {
    UiaRaiseAutomationEvent(&host_a11y_element->simple, UIA_Text_TextChangedEventId);
    if (selection_only) UiaRaiseAutomationEvent(&host_a11y_element->simple, UIA_Text_TextSelectionChangedEventId);
  }
  if (g.page) {
    NotifyWinEvent(EVENT_OBJECT_VALUECHANGE, g.page, OBJID_CLIENT, CHILDID_SELF);
    if (selection_only) NotifyWinEvent(EVENT_OBJECT_SELECTION, g.page, OBJID_CLIENT, CHILDID_SELF);
  }
}

static void host_a11y_page_changed(int selection_only) { host_a11y_raise_page(selection_only); }

/* Status line: one change event per real text change. */
static void host_a11y_status_changed(void) {
  static wchar_t previous[768];
  if (!g.status) return;
  if (!wcscmp(previous, g.status_text)) return;
  wcsncpy(previous, g.status_text, 767);
  previous[767] = 0;
  NotifyWinEvent(EVENT_OBJECT_NAMECHANGE, g.status, OBJID_CLIENT, CHILDID_SELF);
}

/* ---- keyboard continuity --------------------------------------------- */
/* Enabled tab stop after (or before) a control, in the same z-order the dialog
   manager walks. */
static HWND host_a11y_tab_stop(HWND from, int backwards) {
  HWND list[256];
  HWND child;
  int count = 0, index = -1, i;
  if (!g.window) return NULL;
  for (child = GetWindow(g.window, GW_CHILD); child && count < 256; child = GetWindow(child, GW_HWNDNEXT)) {
    LONG_PTR style = GetWindowLongPtrW(child, GWL_STYLE);
    if (!(style & WS_TABSTOP) || !IsWindowVisible(child) || !IsWindowEnabled(child)) continue;
    if (child == from) index = count;
    list[count++] = child;
  }
  if (!count) return NULL;
  if (index < 0) index = backwards ? count : -1;
  for (i = 1; i <= count; i++) {
    int at = ((index + (backwards ? -i : i)) % count + count) % count;
    if (list[at] != from) return list[at];
  }
  return NULL;
}

/* A command that disables itself while it holds focus must hand focus on. */
static void host_a11y_focus_guard(HWND before) {
  HWND next;
  if (!before || !IsWindow(before) || IsWindowEnabled(before)) return;
  if (GetFocus() != before) return;
  next = host_a11y_tab_stop(before, 0);
  if (!next) next = host_a11y_tab_stop(before, 1);
  if (next && next != before) SetFocus(next);
}

/* Truthful owner-disabled state for modal dialogs: Win32 disables only the parent
   window while UI Automation reports each child's own enabled state. */
static HWND host_a11y_modal[64];
static int host_a11y_modal_count;
static int host_a11y_modal_active;

static void host_a11y_owner_reapply(void) {
  int i;
  if (!host_a11y_modal_active) return;
  for (i = 0; i < host_a11y_modal_count; i++)
    if (IsWindow(host_a11y_modal[i])) EnableWindow(host_a11y_modal[i], FALSE);
}

static void host_a11y_owner_enabled(int enabled) {
  HWND child;
  if (!g.window) return;
  EnableWindow(g.window, enabled ? TRUE : FALSE);
  if (!enabled) {
    if (host_a11y_modal_active) { host_a11y_owner_reapply(); return; }
    host_a11y_modal_count = 0;
    for (child = GetWindow(g.window, GW_CHILD); child && host_a11y_modal_count < 64; child = GetWindow(child, GW_HWNDNEXT)) {
      if (!IsWindowEnabled(child)) continue;
      host_a11y_modal[host_a11y_modal_count++] = child;
      EnableWindow(child, FALSE);
    }
    host_a11y_modal_active = 1;
  } else {
    int i;
    for (i = 0; i < host_a11y_modal_count; i++)
      if (IsWindow(host_a11y_modal[i])) EnableWindow(host_a11y_modal[i], TRUE);
    host_a11y_modal_count = 0;
    host_a11y_modal_active = 0;
  }
}

/* Multiline comment editor: keep multi-line editing, stop swallowing Tab so the
   dialog manager can traverse out of it. */
static WNDPROC host_a11y_note_previous;

static LRESULT CALLBACK host_a11y_note_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (message == WM_GETDLGCODE) return DLGC_WANTCHARS | DLGC_WANTARROWS;
  return CallWindowProcW(host_a11y_note_previous, window, message, wparam, lparam);
}

static void host_a11y_prepare_note(void) {
  if (!g.note_edit || host_a11y_note_previous) return;
  host_a11y_note_previous = (WNDPROC)SetWindowLongPtrW(g.note_edit, GWLP_WNDPROC, (LONG_PTR)host_a11y_note_procedure);
}
