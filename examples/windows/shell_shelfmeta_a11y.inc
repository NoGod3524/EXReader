/* SPDX-License-Identifier: MIT */
/* F09: the custom-drawn shelf view ("系列、标签与阅读统计") as an MSAA object
   with one simple child per keyboard stop, so UI Automation (through its MSAA
   bridge) sees every painted target as its own element: name, role, state,
   bounding rectangle, keyboard focus, hit testing, navigation and the default
   action. Child ids follow the keyboard order (sm_key_order), 1-based. The
   view itself delegates to the standard client object. Calls arrive on the UI
   thread (single-threaded apartment of the window). oleacc.dll is resolved at
   run time so no build target gains a link dependency. */
typedef LRESULT (WINAPI *sm_acc_lresult_fn)(REFIID,WPARAM,LPUNKNOWN);
typedef HRESULT (WINAPI *sm_acc_std_fn)(HWND,LONG,REFIID,void **);
static const GUID sm_acc_iid_accessible={0x618736e0,0x3c3d,0x11cf,{0x81,0x0c,0x00,0xaa,0x00,0x38,0x9b,0x71}};
static const GUID sm_acc_iid_dispatch={0x00020400,0x0000,0x0000,{0xc0,0x00,0x00,0x00,0x00,0x00,0x00,0x46}};
static const GUID sm_acc_iid_unknown={0x00000000,0x0000,0x0000,{0xc0,0x00,0x00,0x00,0x00,0x00,0x00,0x46}};
typedef struct { IAccessible iface; LONG refs; IAccessible *standard; } sm_acc;

static sm_acc *sm_acc_of(IAccessible *self) { return (sm_acc *)self; }
/* Hit index of a 1-based child id, or -1. */
static int sm_acc_hit(VARIANT child) {
  if(child.vt!=VT_I4 || child.lVal<=0) return -1;
  int *order=sm_order_buf,n=sm_key_order(order);
  return child.lVal<=n ? order[child.lVal-1]:-1;
}
static LONG sm_acc_child_of_hit(int hit) {
  int *order=sm_order_buf,n=sm_key_order(order);
  for(int i=0;i<n;i++) if(order[i]==hit) return i+1;
  return CHILDID_SELF;
}
static int sm_acc_self(VARIANT child) { return child.vt==VT_I4 && child.lVal==CHILDID_SELF; }
static HRESULT sm_acc_bstr(BSTR *out,const wchar_t *text) {
  if(!out) return E_POINTER;
  *out=SysAllocString(text);return *out ? S_OK:E_OUTOFMEMORY;
}

static HRESULT STDMETHODCALLTYPE sm_acc_query(IAccessible *self,REFIID id,void **out) {
  if(!out) return E_POINTER;
  if(IsEqualGUID(id,&sm_acc_iid_unknown) || IsEqualGUID(id,&sm_acc_iid_dispatch) || IsEqualGUID(id,&sm_acc_iid_accessible)) {
    *out=self;self->lpVtbl->AddRef(self);return S_OK;
  }
  *out=NULL;return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE sm_acc_addref(IAccessible *self) { return (ULONG)InterlockedIncrement(&sm_acc_of(self)->refs); }
static ULONG STDMETHODCALLTYPE sm_acc_release(IAccessible *self) {
  sm_acc *acc=sm_acc_of(self);LONG left=InterlockedDecrement(&acc->refs);
  if(!left) { if(acc->standard) acc->standard->lpVtbl->Release(acc->standard);free(acc); }
  return (ULONG)left;
}
static HRESULT STDMETHODCALLTYPE sm_acc_type_count(IAccessible *self,UINT *out) { (void)self;if(out)*out=0;return S_OK; }
static HRESULT STDMETHODCALLTYPE sm_acc_type_info(IAccessible *self,UINT index,LCID locale,ITypeInfo **out) {
  (void)self;(void)index;(void)locale;if(out)*out=NULL;return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE sm_acc_ids(IAccessible *self,REFIID id,LPOLESTR *names,UINT count,LCID locale,DISPID *out) {
  (void)self;(void)id;(void)names;(void)count;(void)locale;(void)out;return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE sm_acc_invoke(IAccessible *self,DISPID member,REFIID id,LCID locale,WORD flags,
                                               DISPPARAMS *params,VARIANT *result,EXCEPINFO *exception,UINT *argument) {
  (void)self;(void)member;(void)id;(void)locale;(void)flags;(void)params;(void)result;(void)exception;(void)argument;
  return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE sm_acc_parent(IAccessible *self,IDispatch **out) {
  sm_acc *acc=sm_acc_of(self);return acc->standard->lpVtbl->get_accParent(acc->standard,out);
}
static HRESULT STDMETHODCALLTYPE sm_acc_count(IAccessible *self,long *out) {
  (void)self;if(!out) return E_POINTER;
  *out=sm_hit_count;return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_child(IAccessible *self,VARIANT child,IDispatch **out) {
  (void)self;if(!out) return E_POINTER;
  *out=NULL;return sm_acc_hit(child)>=0 ? S_FALSE:E_INVALIDARG; /* simple elements */
}
static HRESULT STDMETHODCALLTYPE sm_acc_name(IAccessible *self,VARIANT child,BSTR *out) {
  sm_acc *acc=sm_acc_of(self);
  wchar_t label[320];(void)acc;
  if(sm_acc_self(child)) {
    /* The view keeps mirroring the focused stop (sm_key_announce) for clients
       that read only the focused window. */
    int at=sm_key_index();
    if(at<0) swprintf(label,320,L"系列、标签与阅读统计");else sm_key_label(&sm_hits[at],label,320);
    return sm_acc_bstr(out,label);
  }
  int hit=sm_acc_hit(child);if(hit<0) return E_INVALIDARG;
  sm_key_label(&sm_hits[hit],label,320);return sm_acc_bstr(out,label);
}
static HRESULT STDMETHODCALLTYPE sm_acc_value(IAccessible *self,VARIANT child,BSTR *out) {
  sm_acc *acc=sm_acc_of(self);if(out)*out=NULL;
  if(sm_acc_self(child)) return acc->standard->lpVtbl->get_accValue(acc->standard,child,out);
  return sm_acc_hit(child)>=0 ? DISP_E_MEMBERNOTFOUND:E_INVALIDARG;
}
static HRESULT STDMETHODCALLTYPE sm_acc_description(IAccessible *self,VARIANT child,BSTR *out) {
  sm_acc *acc=sm_acc_of(self);if(out)*out=NULL;
  if(sm_acc_self(child)) return acc->standard->lpVtbl->get_accDescription(acc->standard,child,out);
  return sm_acc_hit(child)>=0 ? DISP_E_MEMBERNOTFOUND:E_INVALIDARG;
}
static HRESULT STDMETHODCALLTYPE sm_acc_role(IAccessible *self,VARIANT child,VARIANT *out) {
  (void)self;if(!out) return E_POINTER;
  VariantInit(out);out->vt=VT_I4;
  if(sm_acc_self(child)) {out->lVal=ROLE_SYSTEM_LIST;return S_OK;}
  int hit=sm_acc_hit(child);if(hit<0) {out->vt=VT_EMPTY;return E_INVALIDARG;}
  int kind=sm_hits[hit].kind;
  out->lVal=kind==SM_HIT_BOOK ? ROLE_SYSTEM_LISTITEM:kind==SM_HIT_TAG ? ROLE_SYSTEM_RADIOBUTTON:ROLE_SYSTEM_PUSHBUTTON;
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_state(IAccessible *self,VARIANT child,VARIANT *out) {
  sm_acc *acc=sm_acc_of(self);if(!out) return E_POINTER;
  if(sm_acc_self(child)) return acc->standard->lpVtbl->get_accState(acc->standard,child,out);
  int hit=sm_acc_hit(child);VariantInit(out);if(hit<0) return E_INVALIDARG;
  RECT client,overlap;GetClientRect(sm_view,&client);
  long state=STATE_SYSTEM_FOCUSABLE;
  if(sm_hits[hit].kind==SM_HIT_BOOK) state|=STATE_SYSTEM_SELECTABLE;
  if(sm_hits[hit].kind==SM_HIT_TAG && sm_filter==sm_hits[hit].arg) state|=STATE_SYSTEM_CHECKED;
  if(hit==sm_key_index()) { state|=STATE_SYSTEM_SELECTED;if(GetFocus()==sm_view) state|=STATE_SYSTEM_FOCUSED; }
  if(!IntersectRect(&overlap,&client,&sm_hits[hit].r) || !IsWindowVisible(sm_view)) state|=STATE_SYSTEM_OFFSCREEN|STATE_SYSTEM_INVISIBLE;
  out->vt=VT_I4;out->lVal=state;return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_help(IAccessible *self,VARIANT child,BSTR *out) {
  (void)self;if(out)*out=NULL;
  if(sm_acc_self(child)) return sm_acc_bstr(out,L"Tab 或方向键移动，Enter 激活，菜单键打开书籍菜单");
  return sm_acc_hit(child)>=0 ? DISP_E_MEMBERNOTFOUND:E_INVALIDARG;
}
static HRESULT STDMETHODCALLTYPE sm_acc_help_topic(IAccessible *self,BSTR *file,VARIANT child,long *topic) {
  (void)self;(void)child;if(file)*file=NULL;if(topic)*topic=0;return DISP_E_MEMBERNOTFOUND;
}
static HRESULT STDMETHODCALLTYPE sm_acc_shortcut(IAccessible *self,VARIANT child,BSTR *out) {
  sm_acc *acc=sm_acc_of(self);if(out)*out=NULL;
  if(sm_acc_self(child)) return acc->standard->lpVtbl->get_accKeyboardShortcut(acc->standard,child,out);
  return sm_acc_hit(child)>=0 ? DISP_E_MEMBERNOTFOUND:E_INVALIDARG;
}
static HRESULT STDMETHODCALLTYPE sm_acc_focus(IAccessible *self,VARIANT *out) {
  (void)self;if(!out) return E_POINTER;
  VariantInit(out);
  if(GetFocus()!=sm_view) return S_FALSE;
  int hit=sm_key_index();out->vt=VT_I4;out->lVal=hit>=0 ? sm_acc_child_of_hit(hit):CHILDID_SELF;return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_selection(IAccessible *self,VARIANT *out) {
  (void)self;if(!out) return E_POINTER;
  VariantInit(out);int hit=sm_key_index();
  if(hit<0) return S_FALSE;
  out->vt=VT_I4;out->lVal=sm_acc_child_of_hit(hit);return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_default_action(IAccessible *self,VARIANT child,BSTR *out) {
  sm_acc *acc=sm_acc_of(self);if(out)*out=NULL;
  if(sm_acc_self(child)) return acc->standard->lpVtbl->get_accDefaultAction(acc->standard,child,out);
  int hit=sm_acc_hit(child);if(hit<0) return E_INVALIDARG;
  return sm_acc_bstr(out,sm_hits[hit].kind==SM_HIT_BOOK ? L"打开":sm_hits[hit].kind==SM_HIT_TAG ? L"筛选":L"按下");
}
static HRESULT STDMETHODCALLTYPE sm_acc_select(IAccessible *self,long flags,VARIANT child) {
  sm_acc *acc=sm_acc_of(self);
  if(sm_acc_self(child)) return acc->standard->lpVtbl->accSelect(acc->standard,flags,child);
  int hit=sm_acc_hit(child);if(hit<0) return E_INVALIDARG;
  if(flags&(SELFLAG_TAKEFOCUS|SELFLAG_TAKESELECTION)) {
    sm_key_kind=sm_hits[hit].kind;sm_key_arg=sm_hits[hit].arg;
    if(flags&SELFLAG_TAKEFOCUS) SetFocus(sm_view);
    sm_key_reveal();sm_key_announce();
  }
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_location(IAccessible *self,long *x,long *y,long *w,long *h,VARIANT child) {
  sm_acc *acc=sm_acc_of(self);
  if(sm_acc_self(child)) return acc->standard->lpVtbl->accLocation(acc->standard,x,y,w,h,child);
  int hit=sm_acc_hit(child);if(hit<0) return E_INVALIDARG;
  if(!x || !y || !w || !h) return E_POINTER;
  RECT r=sm_hits[hit].r;MapWindowPoints(sm_view,NULL,(POINT *)&r,2);
  *x=r.left;*y=r.top;*w=r.right-r.left;*h=r.bottom-r.top;return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_navigate(IAccessible *self,long direction,VARIANT start,VARIANT *out) {
  sm_acc *acc=sm_acc_of(self);if(!out) return E_POINTER;
  VariantInit(out);int *order=sm_order_buf,n=sm_key_order(order);
  if(sm_acc_self(start)) {
    if(direction==NAVDIR_FIRSTCHILD || direction==NAVDIR_LASTCHILD) {
      if(!n) return S_FALSE;
      out->vt=VT_I4;out->lVal=direction==NAVDIR_FIRSTCHILD ? 1:n;return S_OK;
    }
    return acc->standard->lpVtbl->accNavigate(acc->standard,direction,start,out);
  }
  if(sm_acc_hit(start)<0) return E_INVALIDARG;
  long next=start.lVal;
  if(direction==NAVDIR_NEXT || direction==NAVDIR_DOWN || direction==NAVDIR_RIGHT) next++;
  else if(direction==NAVDIR_PREVIOUS || direction==NAVDIR_UP || direction==NAVDIR_LEFT) next--;
  else return E_INVALIDARG;
  if(next<1 || next>n) return S_FALSE;
  out->vt=VT_I4;out->lVal=next;return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_hit_test(IAccessible *self,long x,long y,VARIANT *out) {
  sm_acc *acc=sm_acc_of(self);if(!out) return E_POINTER;
  POINT p={x,y};ScreenToClient(sm_view,&p);int hit=sm_hit_at(p.x,p.y);
  if(hit<0) return acc->standard->lpVtbl->accHitTest(acc->standard,x,y,out);
  VariantInit(out);out->vt=VT_I4;out->lVal=sm_acc_child_of_hit(hit);return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_do_default(IAccessible *self,VARIANT child) {
  sm_acc *acc=sm_acc_of(self);
  if(sm_acc_self(child)) return acc->standard->lpVtbl->accDoDefaultAction(acc->standard,child);
  int hit=sm_acc_hit(child);if(hit<0) return E_INVALIDARG;
  sm_key_kind=sm_hits[hit].kind;sm_key_arg=sm_hits[hit].arg;sm_key_activate(0);return S_OK;
}
static HRESULT STDMETHODCALLTYPE sm_acc_put_name(IAccessible *self,VARIANT child,BSTR value) {
  (void)self;(void)child;(void)value;return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE sm_acc_put_value(IAccessible *self,VARIANT child,BSTR value) {
  (void)self;(void)child;(void)value;return E_NOTIMPL;
}
static IAccessibleVtbl sm_acc_vtbl={
  .QueryInterface=sm_acc_query,.AddRef=sm_acc_addref,.Release=sm_acc_release,
  .GetTypeInfoCount=sm_acc_type_count,.GetTypeInfo=sm_acc_type_info,.GetIDsOfNames=sm_acc_ids,.Invoke=sm_acc_invoke,
  .get_accParent=sm_acc_parent,.get_accChildCount=sm_acc_count,.get_accChild=sm_acc_child,.get_accName=sm_acc_name,
  .get_accValue=sm_acc_value,.get_accDescription=sm_acc_description,.get_accRole=sm_acc_role,.get_accState=sm_acc_state,
  .get_accHelp=sm_acc_help,.get_accHelpTopic=sm_acc_help_topic,.get_accKeyboardShortcut=sm_acc_shortcut,
  .get_accFocus=sm_acc_focus,.get_accSelection=sm_acc_selection,.get_accDefaultAction=sm_acc_default_action,
  .accSelect=sm_acc_select,.accLocation=sm_acc_location,.accNavigate=sm_acc_navigate,.accHitTest=sm_acc_hit_test,
  .accDoDefaultAction=sm_acc_do_default,.put_accName=sm_acc_put_name,.put_accValue=sm_acc_put_value,
};
/* WM_GETOBJECT for OBJID_CLIENT; 0 lets DefWindowProc answer anything else. */
static LRESULT sm_acc_object(HWND window,WPARAM wp,LPARAM lp) {
  static HMODULE oleacc;static sm_acc_lresult_fn lresult;static sm_acc_std_fn standard;
  if((LONG)lp!=OBJID_CLIENT) return 0;
  if(!oleacc && (oleacc=LoadLibraryW(L"oleacc.dll"))) {
    lresult=(sm_acc_lresult_fn)(void *)GetProcAddress(oleacc,"LresultFromObject");
    standard=(sm_acc_std_fn)(void *)GetProcAddress(oleacc,"CreateStdAccessibleObject");
  }
  if(!lresult || !standard) return 0;
  sm_acc *acc=calloc(1,sizeof(*acc));if(!acc) return 0;
  acc->iface.lpVtbl=&sm_acc_vtbl;acc->refs=1;
  if(FAILED(standard(window,OBJID_CLIENT,&sm_acc_iid_accessible,(void **)&acc->standard)) || !acc->standard) {free(acc);return 0;}
  LRESULT result=lresult(&sm_acc_iid_accessible,wp,(LPUNKNOWN)&acc->iface);
  acc->iface.lpVtbl->Release(&acc->iface);
  return result;
}
