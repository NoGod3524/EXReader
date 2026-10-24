/* SPDX-License-Identifier: MIT
 * Native accessibility for the Windows product host.
 *
 * EXReaderPage is a custom control, so Windows can only answer for it when the
 * host provides an element. This module implements a real server-side UI
 * Automation provider over the text the public SDK projection already produced
 * for the current page, with the host's own selection as the text selection.
 * There is no second text pipeline and nothing is invented for assistive
 * technology.
 *
 * Rules enforced here:
 *  - Every text range owns a stable snapshot of the page text plus the frame
 *    generation that produced it. Reading always works; anything that would act
 *    on the live frame refuses with UIA_E_ELEMENTNOTAVAILABLE once the frame
 *    changed, so an old range can never select inside another page or book.
 *  - Ranges carry their own interlocked reference count; QI on the element
 *    returns one canonical IUnknown and every interface it really implements.
 *  - Frame state is only read on the UI thread; other threads are marshalled
 *    through a page message.
 *  - Capabilities that are not implemented return the exact UI Automation error
 *    instead of a plausible but false result.
 */
#ifndef interface
#define interface struct
#endif
#include <uiautomationcore.h>
#include <uiautomationcoreapi.h>
#include <uiautomationclient.h>
#include <oleacc.h>
#include <wctype.h>
#include <usp10.h>
#include <limits.h>
#pragma comment(lib, "uiautomationcore.lib")
#pragma comment(lib, "oleacc.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "usp10.lib")

#define HOST_A11Y_CALL (WM_APP + 40)

typedef struct host_a11y_page host_a11y_page;
typedef struct host_a11y_range host_a11y_range;
typedef struct host_a11y_snapshot host_a11y_snapshot;

/* One immutable page text with the frame identity that produced it. */
struct host_a11y_snapshot {
  LONG refs;
  unsigned long generation;
  int fixed;
  int64_t book_id;
  size_t page, part;
  size_t base;   /* first byte offset of this page in the frame coordinate system */
  size_t bytes;  /* UTF-8 byte length of the page text */
  wchar_t *text;
  unsigned char *boundaries; /* native Uniscribe character/word stops */
  int units;
};

struct host_a11y_range {
  ITextRangeProvider iface; /* first member: the range identity */
  host_a11y_page *owner;
  host_a11y_snapshot *snapshot;
  LONG refs;
  int start, end;
};

struct host_a11y_page {
  IRawElementProviderSimple simple;
  ITextProvider text;
  IValueProvider value;
  LONG refs;
};

/* Private interface id: this provider recognises its own ranges through it and
   never casts a foreign COM object to a structure it does not own. */
static const GUID host_a11y_range_iid =
  {0x6f1d5c25, 0x8a44, 0x4b1e, {0x9d, 0x2f, 0x35, 0x6e, 0x27, 0xc1, 0x44, 0x0b}};

static host_a11y_page *host_a11y_element;
static host_a11y_snapshot *host_a11y_current;
static DWORD host_a11y_ui_thread;

typedef void (*host_a11y_task_fn)(void *context);
typedef struct { host_a11y_task_fn fn; void *context; } host_a11y_task;

/* forward declarations */
static void host_a11y_page_changed(int selection_only);
static LONG host_a11y_addref(host_a11y_page *self);
static LONG host_a11y_release(host_a11y_page *self);
static LONG host_a11y_snapshot_addref(host_a11y_snapshot *snapshot);
static void host_a11y_snapshot_release(host_a11y_snapshot *snapshot);
static int host_a11y_clamp_unit(const host_a11y_snapshot *snapshot, int value);
static HRESULT host_a11y_advance(const host_a11y_snapshot *snapshot, enum TextUnit unit, int value, int forward, int *out);
static size_t host_a11y_bytes_of(const wchar_t *text, int units);
static host_a11y_range *host_a11y_range_new(host_a11y_page *owner, host_a11y_snapshot *snapshot, int start, int end);
static ULONG STDMETHODCALLTYPE host_a11y_range_addref(ITextRangeProvider *self);
static ULONG STDMETHODCALLTYPE host_a11y_range_release(ITextRangeProvider *self);
static host_a11y_range *host_a11y_range_of(ITextRangeProvider *other);

/* ---- UI-thread marshalling -------------------------------------------- */
static int host_a11y_ui_current(void) {
  return host_a11y_ui_thread == GetCurrentThreadId();
}

/* Runs on the UI thread: directly there, otherwise through the page's queue.
   Returns 0 when the window is already gone. */
static int host_a11y_on_ui(host_a11y_task_fn fn, void *context) {
  host_a11y_task task;
  if (!g.page || !IsWindow(g.page)) return 0;
  if (host_a11y_ui_current()) { fn(context); return 1; }
  task.fn = fn;
  task.context = context;
  SendMessageW(g.page, HOST_A11Y_CALL, 0, (LPARAM)&task);
  return 1;
}

typedef struct { HWND window; BOOL focused, enabled; } host_a11y_window_state;
static void host_a11y_window_task(void *context) {
  host_a11y_window_state *state = (host_a11y_window_state *)context;
  state->window = g.page;
  state->focused = GetFocus() == g.page;
  state->enabled = IsWindowEnabled(g.page);
}

/* ---- page text: the public SDK projection, exactly as the copy path reads it */
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

static void host_a11y_snapshot_free(host_a11y_snapshot *snapshot) {
  if (!snapshot) return;
  free(snapshot->text);
  free(snapshot->boundaries);
  free(snapshot);
}

static LONG host_a11y_snapshot_addref(host_a11y_snapshot *snapshot) {
  return snapshot ? InterlockedIncrement(&snapshot->refs) : 0;
}

static void host_a11y_snapshot_release(host_a11y_snapshot *snapshot) {
  if (snapshot && !InterlockedDecrement(&snapshot->refs)) host_a11y_snapshot_free(snapshot);
}

static int host_a11y_make_boundaries(host_a11y_snapshot *snapshot) {
  SCRIPT_ITEM *items;
  SCRIPT_LOGATTR *attributes;
  int count = 0, i;
  snapshot->boundaries = (unsigned char *)calloc((size_t)snapshot->units + 1, 1);
  if (!snapshot->boundaries) return 0;
  snapshot->boundaries[0] = snapshot->boundaries[snapshot->units] = 3;
  if (!snapshot->units) return 1;
  items = (SCRIPT_ITEM *)calloc((size_t)snapshot->units + 1, sizeof(*items));
  attributes = (SCRIPT_LOGATTR *)calloc((size_t)snapshot->units, sizeof(*attributes));
  if (!items || !attributes) { free(items); free(attributes); return 0; }
  if (FAILED(ScriptItemize(snapshot->text, snapshot->units, snapshot->units + 1, NULL, NULL, items, &count))) {
    free(items); free(attributes); return 0;
  }
  for (i = 0; i < count; ++i) {
    int from = items[i].iCharPos, length = items[i + 1].iCharPos - from;
    if (FAILED(ScriptBreak(snapshot->text + from, length, &items[i].a, attributes + from))) {
      free(items); free(attributes); return 0;
    }
  }
  for (i = 1; i < snapshot->units; ++i)
    snapshot->boundaries[i] = (unsigned char)((attributes[i].fCharStop ? 1 : 0) |
                                             (attributes[i].fWordStop && attributes[i].fCharStop && !attributes[i].fWhiteSpace ? 2 : 0));
  free(items);
  free(attributes);
  return 1;
}

static host_a11y_snapshot *host_a11y_snapshot_build(void) {
  const char *utf8; size_t bytes, base;
  host_a11y_snapshot *snapshot;
  int units;
  if (!host_a11y_page_text(&utf8, &bytes, &base)) return NULL;
  if (bytes > INT_MAX - 1) return NULL;
  units = MultiByteToWideChar(CP_UTF8, 0, utf8, (int)bytes, NULL, 0);
  if (units < 0) return NULL;
  snapshot = (host_a11y_snapshot *)calloc(1, sizeof(*snapshot));
  if (!snapshot) return NULL;
  snapshot->text = (wchar_t *)calloc((size_t)units + 1, sizeof(wchar_t));
  if (!snapshot->text) { free(snapshot); return NULL; }
  if (units && MultiByteToWideChar(CP_UTF8, 0, utf8, (int)bytes, snapshot->text, units) != units) {
    host_a11y_snapshot_free(snapshot);
    return NULL;
  }
  snapshot->refs = 1;
  snapshot->units = units;
  if (!host_a11y_make_boundaries(snapshot)) { host_a11y_snapshot_free(snapshot); return NULL; }
  snapshot->base = base;
  snapshot->bytes = bytes;
  snapshot->generation = g.frame.generation;
  snapshot->fixed = g.frame.fixed;
  snapshot->book_id = g.frame.book_id;
  snapshot->page = g.frame.page;
  snapshot->part = g.frame.part;
  return snapshot;
}

static int host_a11y_snapshot_matches(const host_a11y_snapshot *snapshot) {
  return snapshot && g.frame.valid && snapshot->generation == g.frame.generation &&
         snapshot->fixed == g.frame.fixed && snapshot->book_id == g.frame.book_id &&
         snapshot->page == g.frame.page && snapshot->part == g.frame.part;
}

static void host_a11y_acquire_task(void *context) {
  host_a11y_snapshot **out = (host_a11y_snapshot **)context;
  host_a11y_snapshot *fresh;
  if (host_a11y_current && host_a11y_snapshot_matches(host_a11y_current)) {
    *out = host_a11y_current;
    host_a11y_snapshot_addref(*out);
    return;
  }
  fresh = host_a11y_snapshot_build();
  if (!fresh) return;
  host_a11y_snapshot_release(host_a11y_current);
  host_a11y_current = fresh;
  *out = fresh;
  host_a11y_snapshot_addref(*out);
}

/* ---- UTF-16 helpers ---------------------------------------------------- */
/* Unsupported valid text units fall forward to the next supported larger unit,
   as required by the UIA TextRange contract. No new text parser is involved. */
static int host_a11y_unit(enum TextUnit unit) {
  if (unit == TextUnit_Character) return TextUnit_Character;
  if (unit == TextUnit_Format || unit == TextUnit_Word) return TextUnit_Word;
  if (unit >= TextUnit_Line && unit <= TextUnit_Document) return TextUnit_Document;
  return -1;
}

static int host_a11y_boundary(const host_a11y_snapshot *snapshot, int unit, int at) {
  if (at == 0 || at == snapshot->units) return 1;
  return (snapshot->boundaries[at] & (unit == TextUnit_Character ? 1 : 2)) != 0;
}

/* UTF-8 byte length of the first 'units' UTF-16 characters. */
static size_t host_a11y_bytes_of(const wchar_t *text, int units) {
  int bytes;
  if (!text || units <= 0) return 0;
  bytes = WideCharToMultiByte(CP_UTF8, 0, text, units, NULL, 0, NULL, NULL);
  return bytes > 0 ? (size_t)bytes : 0;
}

static int host_a11y_clamp_unit(const host_a11y_snapshot *snapshot, int value) {
  if (value < 0) return 0;
  if (snapshot && value > snapshot->units) return snapshot->units;
  return value;
}

static HRESULT host_a11y_advance(const host_a11y_snapshot *snapshot, enum TextUnit unit, int value, int forward, int *out) {
  int at = value;
  if (!snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  if (host_a11y_unit(unit) < 0) return E_INVALIDARG;
  unit = (enum TextUnit)host_a11y_unit(unit);
  at = host_a11y_clamp_unit(snapshot, at);
  if (unit == TextUnit_Document) at = forward ? snapshot->units : 0;
  else if (forward && at < snapshot->units) {
    do { ++at; } while (at < snapshot->units && !host_a11y_boundary(snapshot, unit, at));
  } else if (!forward && at > 0) {
    do { --at; } while (at > 0 && !host_a11y_boundary(snapshot, unit, at));
  }
  *out = at;
  return S_OK;
}

static void host_a11y_unit_span(const host_a11y_snapshot *snapshot, enum TextUnit unit,
                                int point, int *start, int *end) {
  int at = host_a11y_clamp_unit(snapshot, point);
  if (unit == TextUnit_Document) { *start = 0; *end = snapshot->units; return; }
  if (at == snapshot->units && at) host_a11y_advance(snapshot, unit, at, 0, &at);
  while (at > 0 && !host_a11y_boundary(snapshot, unit, at)) --at;
  *start = at;
  host_a11y_advance(snapshot, unit, at, 1, end);
}

/* ---- element identity -------------------------------------------------- */
static LONG host_a11y_addref(host_a11y_page *self) { return InterlockedIncrement(&self->refs); }

static LONG host_a11y_release(host_a11y_page *self) {
  LONG left = InterlockedDecrement(&self->refs);
  if (!left) { if (host_a11y_element == self) host_a11y_element = NULL; free(self); }
  return left;
}

/* One canonical IUnknown; every interface this element really implements is
   reachable from it as well as from every sibling interface. */
static HRESULT host_a11y_page_query(host_a11y_page *owner, REFIID id, void **out) {
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (IsEqualIID(id, &IID_IUnknown) || IsEqualIID(id, &IID_IRawElementProviderSimple)) {
    host_a11y_addref(owner);
    *out = &owner->simple;
    return S_OK;
  }
  if (IsEqualIID(id, &IID_ITextProvider)) { host_a11y_addref(owner); *out = &owner->text; return S_OK; }
  if (IsEqualIID(id, &IID_IValueProvider)) { host_a11y_addref(owner); *out = &owner->value; return S_OK; }
  return E_NOINTERFACE;
}

static host_a11y_page *host_a11y_from_text(ITextProvider *self) {
  return (host_a11y_page *)((char *)self - offsetof(host_a11y_page, text));
}

static host_a11y_page *host_a11y_from_value(IValueProvider *self) {
  return (host_a11y_page *)((char *)self - offsetof(host_a11y_page, value));
}

static HRESULT host_a11y_bstr(VARIANT *out, const wchar_t *text) {
  out->vt = VT_BSTR;
  out->bstrVal = SysAllocString(text);
  return out->bstrVal ? S_OK : E_OUTOFMEMORY;
}

static HRESULT STDMETHODCALLTYPE host_a11y_simple_query(IRawElementProviderSimple *self, REFIID id, void **out) {
  return host_a11y_page_query((host_a11y_page *)self, id, out);
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

static HRESULT STDMETHODCALLTYPE host_a11y_simple_pattern(IRawElementProviderSimple *self, PATTERNID pattern, IUnknown **out) {
  host_a11y_page *owner = (host_a11y_page *)self;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (pattern == UIA_TextPatternId) { host_a11y_addref(owner); *out = (IUnknown *)&owner->text; return S_OK; }
  if (pattern == UIA_ValuePatternId) { host_a11y_addref(owner); *out = (IUnknown *)&owner->value; return S_OK; }
  return S_OK;
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
  if (id == UIA_HasKeyboardFocusPropertyId || id == UIA_IsEnabledPropertyId) {
    host_a11y_window_state state = {0};
    if (!host_a11y_on_ui(host_a11y_window_task, &state) || !state.window) return UIA_E_ELEMENTNOTAVAILABLE;
    out->vt = VT_BOOL;
    out->boolVal = (id == UIA_HasKeyboardFocusPropertyId ? state.focused : state.enabled) ? VARIANT_TRUE : VARIANT_FALSE;
    return S_OK;
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
  if (!g.page || !IsWindow(g.page)) return S_OK;
  return UiaHostProviderFromHwnd(g.page, out);
}

static IRawElementProviderSimpleVtbl host_a11y_simple_vtbl = {
  host_a11y_simple_query, host_a11y_simple_addref, host_a11y_simple_release,
  host_a11y_simple_options, host_a11y_simple_pattern, host_a11y_simple_property,
  host_a11y_simple_host
};

/* ---- range identity ---------------------------------------------------- */
static HRESULT STDMETHODCALLTYPE host_a11y_range_query(ITextRangeProvider *self, REFIID id, void **out) {
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (IsEqualIID(id, &IID_IUnknown) || IsEqualIID(id, &IID_ITextRangeProvider) ||
      IsEqualIID(id, &host_a11y_range_iid)) {
    host_a11y_range_addref(self);
    *out = self;
    return S_OK;
  }
  return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE host_a11y_range_addref(ITextRangeProvider *self) {
  host_a11y_range *range = (host_a11y_range *)self;
  return (ULONG)InterlockedIncrement(&range->refs);
}

static ULONG STDMETHODCALLTYPE host_a11y_range_release(ITextRangeProvider *self) {
  host_a11y_range *range = (host_a11y_range *)self;
  LONG left;
  if (!range) return 0;
  left = InterlockedDecrement(&range->refs);
  if (left) return (ULONG)left;
  if (range->snapshot) host_a11y_snapshot_release(range->snapshot);
  if (range->owner) host_a11y_release(range->owner);
  free(range);
  return 0;
}

/* Tentative declaration: the initialised table follows the method definitions. */
static ITextRangeProviderVtbl host_a11y_range_vtbl;

static host_a11y_range *host_a11y_range_new(host_a11y_page *owner, host_a11y_snapshot *snapshot, int start, int end) {
  host_a11y_range *range = (host_a11y_range *)calloc(1, sizeof(*range));
  if (!range) { host_a11y_snapshot_release(snapshot); return NULL; }
  range->iface.lpVtbl = &host_a11y_range_vtbl;
  range->owner = owner;
  host_a11y_addref(owner);
  range->snapshot = snapshot; /* takes the caller's reference */
  range->refs = 1;
  range->start = start;
  range->end = end;
  return range;
}

/* Recognises only this provider's ranges; a foreign COM object is never cast. */
static host_a11y_range *host_a11y_range_of(ITextRangeProvider *other) {
  void *found = NULL;
  if (!other || !other->lpVtbl || !other->lpVtbl->QueryInterface) return NULL;
  if (other->lpVtbl->QueryInterface(other, &host_a11y_range_iid, &found) != S_OK) return NULL;
  return (host_a11y_range *)found; /* caller releases the reference */
}

/* ---- range vtable and methods ----------------------------------------- */
static HRESULT STDMETHODCALLTYPE host_a11y_range_clone(ITextRangeProvider *self, ITextRangeProvider **out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_compare(ITextRangeProvider *self, ITextRangeProvider *other, BOOL *same);
static HRESULT STDMETHODCALLTYPE host_a11y_range_compare_endpoints(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    ITextRangeProvider *other, enum TextPatternRangeEndpoint other_endpoint, int *result);
static HRESULT STDMETHODCALLTYPE host_a11y_range_expand(ITextRangeProvider *self, enum TextUnit unit);
static HRESULT STDMETHODCALLTYPE host_a11y_range_find_attribute(ITextRangeProvider *self, TEXTATTRIBUTEID id, VARIANT value,
    BOOL backwards, ITextRangeProvider **out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_find_text(ITextRangeProvider *self, BSTR needle, BOOL backwards,
    BOOL ignore_case, ITextRangeProvider **out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_attribute(ITextRangeProvider *self, TEXTATTRIBUTEID id, VARIANT *out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_rects(ITextRangeProvider *self, SAFEARRAY **out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_element(ITextRangeProvider *self, IRawElementProviderSimple **out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_text(ITextRangeProvider *self, int max, BSTR *out);
static HRESULT STDMETHODCALLTYPE host_a11y_range_move(ITextRangeProvider *self, enum TextUnit unit, int count, int *moved);
static HRESULT STDMETHODCALLTYPE host_a11y_range_move_endpoint(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    enum TextUnit unit, int count, int *moved);
static HRESULT STDMETHODCALLTYPE host_a11y_range_move_endpoint_by_range(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    ITextRangeProvider *other, enum TextPatternRangeEndpoint other_endpoint);
static HRESULT STDMETHODCALLTYPE host_a11y_range_select(ITextRangeProvider *self);
static HRESULT STDMETHODCALLTYPE host_a11y_range_add_to_selection(ITextRangeProvider *self);
static HRESULT STDMETHODCALLTYPE host_a11y_range_remove_from_selection(ITextRangeProvider *self);
static HRESULT STDMETHODCALLTYPE host_a11y_range_scroll(ITextRangeProvider *self, BOOL align);
static HRESULT STDMETHODCALLTYPE host_a11y_range_children(ITextRangeProvider *self, SAFEARRAY **out);

static ITextRangeProviderVtbl host_a11y_range_vtbl = {
  host_a11y_range_query, host_a11y_range_addref, host_a11y_range_release,
  host_a11y_range_clone, host_a11y_range_compare, host_a11y_range_compare_endpoints,
  host_a11y_range_expand, host_a11y_range_find_attribute, host_a11y_range_find_text,
  host_a11y_range_attribute, host_a11y_range_rects, host_a11y_range_element,
  host_a11y_range_text, host_a11y_range_move, host_a11y_range_move_endpoint,
  host_a11y_range_move_endpoint_by_range, host_a11y_range_select,
  host_a11y_range_add_to_selection, host_a11y_range_remove_from_selection,
  host_a11y_range_scroll, host_a11y_range_children
};

static HRESULT STDMETHODCALLTYPE host_a11y_range_clone(ITextRangeProvider *self, ITextRangeProvider **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  host_a11y_range *copy;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  host_a11y_snapshot_addref(range->snapshot);
  copy = host_a11y_range_new(range->owner, range->snapshot, range->start, range->end);
  if (!copy) return E_OUTOFMEMORY;
  *out = &copy->iface;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_compare(ITextRangeProvider *self, ITextRangeProvider *other, BOOL *same) {
  host_a11y_range *a = (host_a11y_range *)self, *b;
  if (!same) return E_INVALIDARG;
  b = host_a11y_range_of(other);
  if (!b) return E_INVALIDARG;
  *same = (a->snapshot == b->snapshot && a->start == b->start && a->end == b->end) ? TRUE : FALSE;
  host_a11y_range_release(&b->iface);
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_compare_endpoints(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    ITextRangeProvider *other, enum TextPatternRangeEndpoint other_endpoint, int *result) {
  host_a11y_range *a = (host_a11y_range *)self, *b;
  int left, right;
  if (!result) return E_INVALIDARG;
  if ((endpoint != TextPatternRangeEndpoint_Start && endpoint != TextPatternRangeEndpoint_End) ||
      (other_endpoint != TextPatternRangeEndpoint_Start && other_endpoint != TextPatternRangeEndpoint_End)) return E_INVALIDARG;
  b = host_a11y_range_of(other);
  if (!b) return E_INVALIDARG;
  if (a->snapshot != b->snapshot) { host_a11y_range_release(&b->iface); return E_INVALIDARG; }
  left = endpoint == TextPatternRangeEndpoint_Start ? a->start : a->end;
  right = other_endpoint == TextPatternRangeEndpoint_Start ? b->start : b->end;
  host_a11y_range_release(&b->iface);
  *result = left < right ? -1 : left > right ? 1 : 0;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_expand(ITextRangeProvider *self, enum TextUnit unit) {
  host_a11y_range *range = (host_a11y_range *)self;
  const host_a11y_snapshot *snapshot = range->snapshot;
  if (!snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  if (host_a11y_unit(unit) < 0) return E_INVALIDARG;
  host_a11y_unit_span(snapshot, (enum TextUnit)host_a11y_unit(unit), range->start, &range->start, &range->end);
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_move(ITextRangeProvider *self, enum TextUnit unit, int count, int *moved) {
  host_a11y_range *range = (host_a11y_range *)self;
  const host_a11y_snapshot *snapshot = range->snapshot;
  int at, end, done = 0, next, nonempty;
  int64_t steps;
  if (!moved) return E_INVALIDARG;
  *moved = 0;
  if (!snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  if (host_a11y_unit(unit) < 0) return E_INVALIDARG;
  if (!count) return S_OK;
  unit = (enum TextUnit)host_a11y_unit(unit);
  nonempty = range->start != range->end;
  at = range->start;
  if (nonempty) host_a11y_unit_span(snapshot, unit, at, &at, &end);
  steps = count > 0 ? (int64_t)count : -(int64_t)count;
  while (done < steps) {
    host_a11y_advance(snapshot, unit, at, count > 0, &next);
    if (next == at || (nonempty && next == snapshot->units)) break;
    at = next;
    done++;
  }
  end = at;
  if (nonempty) host_a11y_advance(snapshot, unit, at, 1, &end);
  range->start = at;
  range->end = end;
  *moved = count > 0 ? done : -done;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_move_endpoint(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    enum TextUnit unit, int count, int *moved) {
  host_a11y_range *range = (host_a11y_range *)self;
  const host_a11y_snapshot *snapshot = range->snapshot;
  int at, done = 0, next;
  int64_t steps;
  if (!moved) return E_INVALIDARG;
  *moved = 0;
  if (!snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  if (host_a11y_unit(unit) < 0 ||
      (endpoint != TextPatternRangeEndpoint_Start && endpoint != TextPatternRangeEndpoint_End)) return E_INVALIDARG;
  if (!count) return S_OK;
  at = endpoint == TextPatternRangeEndpoint_Start ? range->start : range->end;
  steps = count > 0 ? (int64_t)count : -(int64_t)count;
  while (done < steps) {
    host_a11y_advance(snapshot, unit, at, count > 0, &next);
    if (next == at) break;
    at = next;
    done++;
  }
  if (endpoint == TextPatternRangeEndpoint_Start) {
    range->start = at;
    if (range->start > range->end) range->end = at;
  } else {
    range->end = at;
    if (range->end < range->start) range->start = at;
  }
  if (moved) *moved = count > 0 ? done : -done;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_move_endpoint_by_range(ITextRangeProvider *self, enum TextPatternRangeEndpoint endpoint,
    ITextRangeProvider *other, enum TextPatternRangeEndpoint other_endpoint) {
  host_a11y_range *a = (host_a11y_range *)self, *b;
  int value;
  if ((endpoint != TextPatternRangeEndpoint_Start && endpoint != TextPatternRangeEndpoint_End) ||
      (other_endpoint != TextPatternRangeEndpoint_Start && other_endpoint != TextPatternRangeEndpoint_End)) return E_INVALIDARG;
  b = host_a11y_range_of(other);
  if (!b) return E_INVALIDARG;
  if (a->snapshot != b->snapshot) { host_a11y_range_release(&b->iface); return E_INVALIDARG; }
  value = other_endpoint == TextPatternRangeEndpoint_Start ? b->start : b->end;
  host_a11y_range_release(&b->iface);
  if (endpoint == TextPatternRangeEndpoint_Start) {
    a->start = value;
    if (a->start > a->end) a->end = value;
  } else {
    a->end = value;
    if (a->end < a->start) a->start = value;
  }
  return S_OK;
}

/* Attributes and ranges of other providers are not measurable here. */
static HRESULT STDMETHODCALLTYPE host_a11y_range_attribute(ITextRangeProvider *self, TEXTATTRIBUTEID id, VARIANT *out) {
  (void)self; (void)id;
  if (!out) return E_INVALIDARG;
  VariantInit(out);
  return UIA_E_NOTSUPPORTED;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_find_attribute(ITextRangeProvider *self, TEXTATTRIBUTEID id, VARIANT value,
    BOOL backwards, ITextRangeProvider **out) {
  (void)self; (void)id; (void)value; (void)backwards;
  if (out) *out = NULL;
  return UIA_E_NOTSUPPORTED;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_find_text(ITextRangeProvider *self, BSTR needle, BOOL backwards,
    BOOL ignore_case, ITextRangeProvider **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  host_a11y_snapshot *snapshot = range->snapshot;
  int length, from, to, index;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (!snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  if (!needle) return E_INVALIDARG;
  length = (int)wcslen(needle);
  if (!length) return E_INVALIDARG;
  from = host_a11y_clamp_unit(snapshot, range->start);
  to = host_a11y_clamp_unit(snapshot, range->end);
  for (index = backwards ? to - length : from; backwards ? index >= from : index + length <= to;
       index += backwards ? -1 : 1) {
    int equal = ignore_case ? !_wcsnicmp(snapshot->text + index, needle, (size_t)length)
                            : !wcsncmp(snapshot->text + index, needle, (size_t)length);
    if (equal) {
      host_a11y_range *copy;
      host_a11y_snapshot_addref(snapshot);
      copy = host_a11y_range_new(range->owner, snapshot, index, index + length);
      if (!copy) return E_OUTOFMEMORY;
      *out = &copy->iface;
      return S_OK;
    }
  }
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_text(ITextRangeProvider *self, int max, BSTR *out) {
  host_a11y_range *range = (host_a11y_range *)self;
  const host_a11y_snapshot *snapshot = range->snapshot;
  int from, to, at, count;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  if (!snapshot) { *out = SysAllocString(L""); return *out ? S_OK : E_OUTOFMEMORY; }
  from = host_a11y_clamp_unit(snapshot, range->start);
  to = host_a11y_clamp_unit(snapshot, range->end);
  if (to < from) to = from;
  if (max >= 0) {
    /* maxLength counts characters; a surrogate pair is one character. */
    at = from;
    count = 0;
    while (at < to && count < max) {
      host_a11y_advance(snapshot, TextUnit_Character, at, 1, &at);
      if (at > to) at = to;
      count++;
    }
    to = at;
  }
  *out = SysAllocStringLen(snapshot->text + from, (UINT)(to - from));
  return *out ? S_OK : E_OUTOFMEMORY;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_element(ITextRangeProvider *self, IRawElementProviderSimple **out) {
  host_a11y_range *range = (host_a11y_range *)self;
  if (!out) return E_INVALIDARG;
  host_a11y_addref(range->owner);
  *out = &range->owner->simple;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_children(ITextRangeProvider *self, SAFEARRAY **out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  /* The final ITextRangeProvider slot is GetChildren, not GetTextProvider. */
  *out = SafeArrayCreateVector(VT_UNKNOWN, 0, 0);
  return *out ? S_OK : E_OUTOFMEMORY;
}

/* ---- operations that act on the live frame ----------------------------- */
typedef struct {
  host_a11y_range *range;
  HRESULT result;
  SAFEARRAY *rects;
  double px, py;
  host_a11y_snapshot *snapshot;
  int start, end;
} host_a11y_frame_task;

static void host_a11y_select_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  host_a11y_snapshot *snapshot = task->range->snapshot;
  size_t start, end;
  task->result = UIA_E_ELEMENTNOTAVAILABLE;
  if (!host_a11y_snapshot_matches(snapshot)) return;
  start = snapshot->base + host_a11y_bytes_of(snapshot->text, task->range->start);
  end = snapshot->base + host_a11y_bytes_of(snapshot->text, task->range->end);
  if (end < start) end = start;
  g.selection.start = start;
  g.selection.end = end;
  g.selection.page = g.frame.page;
  g.selection.fixed = g.frame.fixed;
  g.selection.active = start < end;
  if (GetFocus() != g.page) SetFocus(g.page);
  InvalidateRect(g.page, NULL, FALSE);
  host_a11y_page_changed(1);
  task->result = S_OK;
}

static int host_a11y_append_rect(RECT *boxes, size_t *count, const RECT *piece, const RECT *clip, int same_line) {
  RECT visible;
  if (!IntersectRect(&visible, piece, clip)) return 0;
  if (same_line && *count) {
    RECT *last = &boxes[*count - 1];
    if (visible.left < last->left) last->left = visible.left;
    if (visible.top < last->top) last->top = visible.top;
    if (visible.right > last->right) last->right = visible.right;
    if (visible.bottom > last->bottom) last->bottom = visible.bottom;
  } else boxes[(*count)++] = visible;
  return 1;
}

static void host_a11y_rect_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  host_a11y_snapshot *snapshot = task->range->snapshot;
  size_t start, end;
  RECT *boxes = NULL;
  RECT piece, clip, bitmap;
  POINT origin = {0};
  size_t used = 0;
  double *data;
  SAFEARRAY *array;
  task->result = UIA_E_ELEMENTNOTAVAILABLE;
  task->rects = NULL;
  if (!host_a11y_snapshot_matches(snapshot) || !g.page || !compute_view()) return;
  GetClientRect(g.page, &clip);
  bitmap.left = g.view.dx; bitmap.top = g.view.dy;
  bitmap.right = bitmap.left + (LONG)(g.frame.bitmap.width * g.view.scale);
  bitmap.bottom = bitmap.top + (LONG)(g.frame.bitmap.height * g.view.scale);
  if (!IntersectRect(&clip, &clip, &bitmap)) return;
  start = snapshot->base + host_a11y_bytes_of(snapshot->text, task->range->start);
  end = snapshot->base + host_a11y_bytes_of(snapshot->text, task->range->end);
  if (end < start) end = start;
  if (start == end) {
    /* An empty range has no geometry; the contract is zero rectangles. */
    array = SafeArrayCreateVector(VT_R8, 0, 0);
    if (!array) { task->result = E_OUTOFMEMORY; return; }
    task->rects = array;
    task->result = S_OK;
    return;
  }
  if (!g.frame.fixed) {
    const exr_glyph *glyphs = NULL;
    size_t count = 0, i;
    double last_baseline = 0;
    int have_line = 0;
    if (g.frame.bounded) { glyphs = g.frame.glyphs; count = g.frame.glyph_count; }
    else if (g.frame.hit_layout) glyphs = exr_layout_glyphs(g.frame.hit_layout, &count);
    if (!glyphs || g.session.page != g.frame.page || g.session.book_id != g.frame.book_id) return;
    if (count > SIZE_MAX / sizeof(*boxes) || count > ULONG_MAX / 4) { task->result = E_OUTOFMEMORY; return; }
    boxes = (RECT *)calloc(count ? count : 1, sizeof(*boxes));
    if (!boxes) { task->result = E_OUTOFMEMORY; return; }
    for (i = 0; i < count; i++) {
      const exr_glyph *glyph = &glyphs[i];
      int left, top, width, height;
      if (glyph->flags & EXR_GLYPH_HIDDEN) continue;
      if (glyph->cluster_end <= start || glyph->cluster_start >= end) continue;
      left = g.view.dx + (int)(glyph->x * g.view.scale);
      top = g.view.dy + (int)((glyph->baseline - glyph->size) * g.view.scale);
      width = (int)(glyph->advance * g.view.scale); if (width < 1) width = 1;
      height = (int)(glyph->size * 1.25 * g.view.scale); if (height < 1) height = 1;
      piece.left = left; piece.top = top; piece.right = left + width; piece.bottom = top + height;
      if (host_a11y_append_rect(boxes, &used, &piece, &clip, have_line && fabs(glyph->baseline - last_baseline) < 0.5)) {
        last_baseline = glyph->baseline;
        have_line = 1;
      }
    }
  } else {
    exr_text_region *regions = NULL;
    size_t count = 0, i;
    exr_error error = {0};
    exr_viewport viewport;
    if (!g.frame.fixed_text || g.session.page != g.frame.page) return;
    if (exr_fixed_text_select(g.frame.fixed_text, start, end, NULL, &regions, &count, &error) != EXR_OK) return;
    if (exr_viewport_create(&g.frame.geometry, g.frame.render_scale, &viewport, &error) != EXR_OK) { exr_free(regions); return; }
    if (count > SIZE_MAX / sizeof(*boxes) || count > ULONG_MAX / 4) {
      exr_free(regions); task->result = E_OUTOFMEMORY; return;
    }
    boxes = (RECT *)calloc(count ? count : 1, sizeof(*boxes));
    if (!boxes) { exr_free(regions); task->result = E_OUTOFMEMORY; return; }
    for (i = 0; i < count; i++) {
      int j;
      for (j = 0; j < 4; j++) {
        double sx = regions[i].quad[j * 2], sy = regions[i].quad[j * 2 + 1];
        double vx = viewport.matrix[0] * sx + viewport.matrix[2] * sy + viewport.matrix[4];
        double vy = viewport.matrix[1] * sx + viewport.matrix[3] * sy + viewport.matrix[5];
        LONG px = g.view.dx + (LONG)(vx * g.view.scale);
        LONG py = g.view.dy + (LONG)(vy * g.view.scale);
        if (!j) { piece.left = piece.right = px; piece.top = piece.bottom = py; }
        else {
          if (px < piece.left) piece.left = px;
          if (py < piece.top) piece.top = py;
          if (px > piece.right) piece.right = px;
          if (py > piece.bottom) piece.bottom = py;
        }
      }
      /* Each SDK text quad supplies its own visible region; never union separate
         lines or PDF columns into one rectangle containing unrelated whitespace. */
      host_a11y_append_rect(boxes, &used, &piece, &clip, 0);
    }
    exr_free(regions);
  }
  array = SafeArrayCreateVector(VT_R8, 0, (ULONG)(used * 4));
  if (!array) { free(boxes); task->result = E_OUTOFMEMORY; return; }
  if (FAILED(SafeArrayAccessData(array, (void **)&data))) {
    free(boxes); SafeArrayDestroy(array); task->result = E_OUTOFMEMORY; return;
  }
  ClientToScreen(g.page, &origin);
  {
    size_t i;
    for (i = 0; i < used; ++i) {
      data[i * 4] = (double)(boxes[i].left + origin.x);
      data[i * 4 + 1] = (double)(boxes[i].top + origin.y);
      data[i * 4 + 2] = (double)(boxes[i].right - boxes[i].left);
      data[i * 4 + 3] = (double)(boxes[i].bottom - boxes[i].top);
    }
  }
  free(boxes);
  SafeArrayUnaccessData(array);
  task->rects = array;
  task->result = S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_rects(ITextRangeProvider *self, SAFEARRAY **out) {
  host_a11y_frame_task task;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  memset(&task, 0, sizeof(task));
  task.range = (host_a11y_range *)self;
  task.result = UIA_E_ELEMENTNOTAVAILABLE;
  if (!host_a11y_on_ui(host_a11y_rect_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result == S_OK) *out = task.rects;
  return task.result;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_select(ITextRangeProvider *self) {
  host_a11y_frame_task task;
  memset(&task, 0, sizeof(task));
  task.range = (host_a11y_range *)self;
  task.result = UIA_E_ELEMENTNOTAVAILABLE;
  if (!host_a11y_on_ui(host_a11y_select_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result != S_OK) return task.result;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_add_to_selection(ITextRangeProvider *self) {
  return host_a11y_range_select(self);
}

/* Exactly one selection is supported, so removing a range from it is not an
   operation this provider can perform. */
static HRESULT STDMETHODCALLTYPE host_a11y_range_remove_from_selection(ITextRangeProvider *self) {
  (void)self;
  return UIA_E_INVALIDOPERATION;
}

static void host_a11y_scroll_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  /* This control fits the complete current page in its client area. Its live
     page ranges need no scrolling; an old page must never navigate a new one. */
  task->result = host_a11y_snapshot_matches(task->range->snapshot) ? S_OK : UIA_E_ELEMENTNOTAVAILABLE;
}

static HRESULT STDMETHODCALLTYPE host_a11y_range_scroll(ITextRangeProvider *self, BOOL align) {
  host_a11y_frame_task task = {0};
  (void)align;
  task.range = (host_a11y_range *)self;
  task.result = UIA_E_ELEMENTNOTAVAILABLE;
  if (!host_a11y_on_ui(host_a11y_scroll_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  return task.result;
}

/* ---- text provider ------------------------------------------------------ */
static void host_a11y_from_point_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  POINT point;
  size_t offset;
  host_a11y_snapshot *snapshot = NULL;
  const char *utf8; size_t bytes, page_base;
  int units;
  task->result = UIA_E_ELEMENTNOTAVAILABLE;
  task->snapshot = NULL;
  if (!g.page || !g.frame.valid) return;
  point.x = (LONG)task->px;
  point.y = (LONG)task->py;
  ScreenToClient(g.page, &point);
  offset = point_offset(point.x, point.y, 1);
  if (offset == SIZE_MAX) return;
  host_a11y_acquire_task(&snapshot);
  if (!snapshot) return;
  if (!host_a11y_page_text(&utf8, &bytes, &page_base)) { host_a11y_snapshot_release(snapshot); return; }
  if (offset < page_base) offset = page_base;
  if (offset > page_base + bytes) offset = page_base + bytes;
  units = MultiByteToWideChar(CP_UTF8, 0, utf8, (int)(offset - page_base), NULL, 0);
  if (units < 0) units = 0;
  task->snapshot = snapshot;
  task->start = units;
  task->end = units;
  task->result = S_OK;
}

static HRESULT host_a11y_range_array(host_a11y_range *range, SAFEARRAY **out) {
  SAFEARRAY *array;
  ITextRangeProvider **slot;
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

static void host_a11y_selection_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  host_a11y_snapshot *snapshot = NULL;
  const char *utf8; size_t bytes, page_base;
  size_t a, b;
  int start = 0, end = 0;
  task->result = UIA_E_ELEMENTNOTAVAILABLE;
  task->snapshot = NULL;
  host_a11y_acquire_task(&snapshot);
  if (!snapshot) return;
  if (g.selection.active && host_a11y_snapshot_matches(snapshot) &&
      host_a11y_page_text(&utf8, &bytes, &page_base)) {
    a = g.selection.start;
    b = g.selection.end;
    if (a > b) { size_t swap = a; a = b; b = swap; }
    if (a < page_base) a = page_base;
    if (a > page_base + bytes) a = page_base + bytes;
    if (b < page_base) b = page_base;
    if (b > page_base + bytes) b = page_base + bytes;
    if (b < a) b = a;
    start = MultiByteToWideChar(CP_UTF8, 0, utf8, (int)(a - page_base), NULL, 0);
    end = MultiByteToWideChar(CP_UTF8, 0, utf8, (int)(b - page_base), NULL, 0);
    if (start < 0) start = 0;
    if (end < start) end = start;
  }
  task->snapshot = snapshot;
  task->start = start;
  task->end = end;
  task->result = S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_selection(ITextProvider *self, SAFEARRAY **out) {
  host_a11y_frame_task task;
  host_a11y_range *range;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  memset(&task, 0, sizeof(task));
  if (!host_a11y_on_ui(host_a11y_selection_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result != S_OK || !task.snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  range = host_a11y_range_new(host_a11y_from_text(self), task.snapshot, task.start, task.end);
  if (!range) return E_OUTOFMEMORY;
  return host_a11y_range_array(range, out);
}

static void host_a11y_document_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  host_a11y_snapshot *snapshot = NULL;
  task->result = UIA_E_ELEMENTNOTAVAILABLE;
  host_a11y_acquire_task(&snapshot);
  if (!snapshot) return;
  task->snapshot = snapshot;
  task->start = 0;
  task->end = snapshot->units;
  task->result = S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_visible(ITextProvider *self, SAFEARRAY **out) {
  host_a11y_frame_task task;
  host_a11y_range *range;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  memset(&task, 0, sizeof(task));
  if (!host_a11y_on_ui(host_a11y_document_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result != S_OK || !task.snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  range = host_a11y_range_new(host_a11y_from_text(self), task.snapshot, task.start, task.end);
  if (!range) return E_OUTOFMEMORY;
  return host_a11y_range_array(range, out);
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_from_child(ITextProvider *self, IRawElementProviderSimple *child, ITextRangeProvider **out) {
  (void)self; (void)child;
  if (out) *out = NULL;
  return UIA_E_NOTSUPPORTED; /* the page has no child elements */
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_from_point(ITextProvider *self, struct UiaPoint point, ITextRangeProvider **out) {
  host_a11y_frame_task task;
  host_a11y_range *range;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  memset(&task, 0, sizeof(task));
  task.px = point.x;
  task.py = point.y;
  if (!host_a11y_on_ui(host_a11y_from_point_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result != S_OK || !task.snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  range = host_a11y_range_new(host_a11y_from_text(self), task.snapshot, task.start, task.end);
  if (!range) return E_OUTOFMEMORY;
  *out = &range->iface;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_document(ITextProvider *self, ITextRangeProvider **out) {
  host_a11y_frame_task task;
  host_a11y_range *range;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  memset(&task, 0, sizeof(task));
  if (!host_a11y_on_ui(host_a11y_document_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result != S_OK || !task.snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  range = host_a11y_range_new(host_a11y_from_text(self), task.snapshot, task.start, task.end);
  if (!range) return E_OUTOFMEMORY;
  *out = &range->iface;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_supported(ITextProvider *self, enum SupportedTextSelection *out) {
  (void)self;
  if (!out) return E_INVALIDARG;
  *out = SupportedTextSelection_Single;
  return S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_text_query(ITextProvider *self, REFIID id, void **out) {
  return host_a11y_page_query(host_a11y_from_text(self), id, out);
}

static ULONG STDMETHODCALLTYPE host_a11y_text_addref(ITextProvider *self) { return (ULONG)host_a11y_addref(host_a11y_from_text(self)); }
static ULONG STDMETHODCALLTYPE host_a11y_text_release(ITextProvider *self) { return (ULONG)host_a11y_release(host_a11y_from_text(self)); }

static ITextProviderVtbl host_a11y_text_vtbl = {
  host_a11y_text_query, host_a11y_text_addref, host_a11y_text_release,
  host_a11y_text_selection, host_a11y_text_visible, host_a11y_text_from_child,
  host_a11y_text_from_point, host_a11y_text_document, host_a11y_text_supported
};

/* ---- value provider ---------------------------------------------------- */
static HRESULT STDMETHODCALLTYPE host_a11y_value_query(IValueProvider *self, REFIID id, void **out) {
  return host_a11y_page_query(host_a11y_from_value(self), id, out);
}
static ULONG STDMETHODCALLTYPE host_a11y_value_addref(IValueProvider *self) { return (ULONG)host_a11y_addref(host_a11y_from_value(self)); }
static ULONG STDMETHODCALLTYPE host_a11y_value_release(IValueProvider *self) { return (ULONG)host_a11y_release(host_a11y_from_value(self)); }
static HRESULT STDMETHODCALLTYPE host_a11y_value_set(IValueProvider *self, LPCWSTR value) { (void)self; (void)value; return UIA_E_NOTSUPPORTED; }

static void host_a11y_value_task(void *context) {
  host_a11y_frame_task *task = (host_a11y_frame_task *)context;
  host_a11y_snapshot *snapshot = NULL;
  task->result = UIA_E_ELEMENTNOTAVAILABLE;
  host_a11y_acquire_task(&snapshot);
  if (!snapshot) return;
  task->snapshot = snapshot;
  task->start = 0;
  task->end = snapshot->units;
  task->result = S_OK;
}

static HRESULT STDMETHODCALLTYPE host_a11y_value_get(IValueProvider *self, BSTR *out) {
  host_a11y_frame_task task;
  host_a11y_range *range;
  HRESULT result;
  if (!out) return E_INVALIDARG;
  *out = NULL;
  memset(&task, 0, sizeof(task));
  if (!host_a11y_on_ui(host_a11y_value_task, &task)) return UIA_E_ELEMENTNOTAVAILABLE;
  if (task.result != S_OK || !task.snapshot) return UIA_E_ELEMENTNOTAVAILABLE;
  range = host_a11y_range_new(host_a11y_from_value(self), task.snapshot, 0, task.snapshot->units);
  if (!range) return E_OUTOFMEMORY;
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

/* ---- entry point, events and keyboard continuity ------------------------ */
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

static LRESULT host_a11y_page_object(HWND window, WPARAM wparam, LPARAM lparam) {
  host_a11y_page *element;
  host_a11y_ui_thread = GetCurrentThreadId();
  if ((LONG)lparam != UiaRootObjectId) return DefWindowProcW(window, WM_GETOBJECT, wparam, lparam);
  element = host_a11y_ensure_element();
  if (!element) return 0;
  return UiaReturnRawElementProvider(window, wparam, lparam, &element->simple);
}

static void host_a11y_page_destroyed(void) {
  host_a11y_page *element = host_a11y_element;
  host_a11y_element = NULL;
  host_a11y_snapshot_release(host_a11y_current);
  host_a11y_current = NULL;
  if (element) { UiaDisconnectProvider(&element->simple); host_a11y_release(element); }
}

static void host_a11y_page_changed(int selection_only) {
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

/* Status line: one change event per real text change. */
static void host_a11y_status_changed(void) {
  static wchar_t previous[768];
  if (!g.status) return;
  if (!wcscmp(previous, g.status_text)) return;
  wcsncpy(previous, g.status_text, 767);
  previous[767] = 0;
  NotifyWinEvent(EVENT_OBJECT_NAMECHANGE, g.status, OBJID_CLIENT, CHILDID_SELF);
}
/* ---- keyboard continuity ------------------------------------------------ */
/* A command that disables itself while it holds focus must hand focus on. */
static void host_a11y_focus_guard(HWND before) {
  HWND next, current;
  if (!before || !IsWindow(before) || IsWindowEnabled(before)) return;
  /* EnableWindow can clear focus before this guard runs. Preserve any valid
     redirect (including a modal dialog); restore only this active owner's lost
     focus or the disabled command itself, using native dialog tab order. */
  current = GetFocus();
  if (current && current != before && IsWindowEnabled(current)) return;
  if (!g.window || !IsWindowEnabled(g.window) || GetActiveWindow() != g.window) return;
  next = GetNextDlgTabItem(g.window, before, FALSE);
  if (!next || next == before) next = GetNextDlgTabItem(g.window, before, TRUE);
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
   dialog manager can traverse in and out. */
static WNDPROC host_a11y_note_previous;

static LRESULT CALLBACK host_a11y_note_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (message == WM_GETDLGCODE) return DLGC_WANTCHARS | DLGC_WANTARROWS;
  return CallWindowProcW(host_a11y_note_previous, window, message, wparam, lparam);
}

static void host_a11y_prepare_note(void) {
  if (!g.note_edit || host_a11y_note_previous) return;
  host_a11y_note_previous = (WNDPROC)SetWindowLongPtrW(g.note_edit, GWLP_WNDPROC, (LONG_PTR)host_a11y_note_procedure);
}

