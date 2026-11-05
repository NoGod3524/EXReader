/* SPDX-License-Identifier: MIT
 * Read-only startup admission for the Windows product host.
 * Existing recovery policy always wins over ordinary SDK open/auto-upgrade.
 * This does not parse/adopt receipts or implement a recovery transaction.
 */
#ifndef EXR_WINDOWS_MIGRATION_GATE_H
#define EXR_WINDOWS_MIGRATION_GATE_H
#include <windows.h>
#include <wchar.h>
#include <string.h>

#define READER_WINDOWS_MIGRATION_GATE_PATH 4096
typedef struct {
  const wchar_t *marker_suffix;
  DWORD native_error;
} reader_windows_migration_gate_result;

static int reader_windows_migration_startup_allowed(
    const wchar_t *library,reader_windows_migration_gate_result *result) {
  static const wchar_t *suffixes[]={
    L".migration-recovery",L".migration-pending.json",L".migrate-lock"
  };
  wchar_t path[READER_WINDOWS_MIGRATION_GATE_PATH];
  size_t n,i;
  if(!result) return 0;
  result->marker_suffix=L"";
  result->native_error=ERROR_INVALID_PARAMETER;
  if(!library || !library[0]) return 0;
  n=wcslen(library);
  for(i=0;i<sizeof(suffixes)/sizeof(suffixes[0]);++i) {
    size_t extra=wcslen(suffixes[i]);
    DWORD attributes,error;
    result->marker_suffix=suffixes[i];
    if(n>=READER_WINDOWS_MIGRATION_GATE_PATH ||
       extra>=READER_WINDOWS_MIGRATION_GATE_PATH-n) {
      result->native_error=ERROR_FILENAME_EXCED_RANGE;return 0;
    }
    memcpy(path,library,n*sizeof(wchar_t));
    memcpy(path+n,suffixes[i],(extra+1)*sizeof(wchar_t));
    SetLastError(ERROR_SUCCESS);
    attributes=GetFileAttributesW(path);
    error=attributes==INVALID_FILE_ATTRIBUTES?GetLastError():ERROR_SUCCESS;
    if(attributes!=INVALID_FILE_ATTRIBUTES) {
      /* Files, directories and reparse entries are all retained policy.
       * No following, content read, deletion, ACL change or lock breaking. */
      result->native_error=ERROR_SUCCESS;return 0;
    }
    if(error!=ERROR_FILE_NOT_FOUND && error!=ERROR_PATH_NOT_FOUND) {
      result->native_error=error;return 0;
    }
  }
  result->marker_suffix=L"";
  result->native_error=ERROR_SUCCESS;
  return 1;
}
#endif
