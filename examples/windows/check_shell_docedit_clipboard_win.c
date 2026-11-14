/* SPDX-License-Identifier: MIT */
/* Console check of real Windows UTF conversion/global-memory paths, with an
   isolated clipboard shim so acceptance never overwrites the user's clipboard.
   gcc -std=c11 -Wall -Wextra -Werror -DEXR_STATIC -Iinclude
     examples/windows/check_shell_docedit_clipboard_win.c src/docx_edit.c -o clipboard-win-check.exe */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <limits.h>
#include <assert.h>
#include <string.h>
static struct { HWND window; } g;
static HGLOBAL clipboard_memory;
static DWORD clipboard_sequence=1;
static int clipboard_busy;
static BOOL test_open(HWND window) {(void)window;return !clipboard_busy;}
static BOOL test_close(void) {return TRUE;}
static BOOL test_empty(void) {
  if(clipboard_memory)GlobalFree(clipboard_memory);
  clipboard_memory=NULL;clipboard_sequence++;return TRUE;
}
static HANDLE test_set(UINT format,HANDLE memory) {
  assert(format==CF_UNICODETEXT);clipboard_memory=memory;clipboard_sequence++;return memory;
}
static HANDLE test_get(UINT format) {assert(format==CF_UNICODETEXT);return clipboard_memory;}
static DWORD test_sequence(void) {return clipboard_sequence;}
#define OpenClipboard test_open
#define CloseClipboard test_close
#define EmptyClipboard test_empty
#define SetClipboardData test_set
#define GetClipboardData test_get
#define GetClipboardSequenceNumber test_sequence
#define DE_CLIPBOARD_TRANSPORT_ONLY
#define main clipboard_model_main
#include "check_shell_docedit_clipboard.c"
#undef main
static void external(const wchar_t *s,size_t n) {
  test_empty();clipboard_memory=GlobalAlloc(GMEM_MOVEABLE,n*sizeof(wchar_t));assert(clipboard_memory);
  wchar_t *p=GlobalLock(clipboard_memory);assert(p);
  for(size_t i=0;i<GlobalSize(clipboard_memory)/sizeof(wchar_t);i++)p[i]=L'x';
  memcpy(p,s,n*sizeof(wchar_t));GlobalUnlock(clipboard_memory);
}
int main(void) {
  assert(clipboard_model_main()==0);de_clip_text=NULL;de_clip_size=0;
  const char *utf8="\xe4\xb8\xad\xf0\x9f\x99\x82";
  assert(de_clip_append(&de_clip_text,&de_clip_size,utf8,7));de_clipboard_publish();
  size_t n=0;char *read=de_clipboard_read(&n);assert(read && n==7 && !strcmp(read,utf8));free(read);
  assert(de_clip_sequence==clipboard_sequence);puts("PASS Windows UTF-8/CJK/emoji -> UTF-16 -> UTF-8");
  char *owned=NULL;const char *payload=de_clipboard_payload(&n,&owned);
  assert(payload==de_clip_text && !owned && n==7);
  external(L"a\r\nb\rc\n",8);read=de_clipboard_read(&n);
  assert(read && !strcmp(read,"a\nb\nc\n"));free(read);
  assert(de_clip_sequence!=clipboard_sequence);puts("PASS external clipboard sequence and CRLF/CR normalization");
  payload=de_clipboard_payload(&n,&owned);
  assert(owned && payload==owned && !strcmp(payload,"a\nb\nc\n"));free(owned);
  clipboard_busy=1;payload=de_clipboard_payload(&n,&owned);
  assert(payload==de_clip_text && !owned && n==7);clipboard_busy=0;
  puts("PASS internal copy preferred; readable external changes used; busy external falls back internally");
  clipboard_busy=1;assert(!de_clipboard_read(&n));clipboard_busy=0;
  external(L"\xd800",2);assert(!de_clipboard_read(&n));
  external(L"no terminator",3);assert(!de_clipboard_read(&n));
  puts("PASS busy clipboard, malformed surrogate, unterminated global memory rejected");
  test_empty();free(de_clip_text);puts("L04 Windows clipboard transport acceptance PASS (isolated clipboard / no GUI)");return 0;
}
