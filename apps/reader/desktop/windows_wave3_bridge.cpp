/* SPDX-License-Identifier: MIT */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <reader_reading_state.h>
#include "windows_wave3_types.h"
#include <cstdio>
#include <cstring>
extern "C" reader_sync_view_status w3_sync_capture(reader_session *session,const char *database,
    reader_sync_view_snapshot **out,reader_sync_view_error *error) {
  if (out) *out = nullptr;
  if (error) *error = {};
  if (!session || !database || !database[0] || !out) {
    if (error) {
      error->status = READER_SYNC_VIEW_ARGUMENT;
      std::snprintf(error->message,sizeof(error->message),"Missing session or product database");
    }
    return READER_SYNC_VIEW_ARGUMENT;
  }
  /* Keep the existing catalog from being deleted/replaced while opening it.
     revisions_open may create or initialize a database; a status view must not. */
  wchar_t path[32768];
  HANDLE existing = INVALID_HANDLE_VALUE;
  if (MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,database,-1,path,32768))
    existing = CreateFileW(path,GENERIC_READ,FILE_SHARE_READ | FILE_SHARE_WRITE,
      nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
  if (existing == INVALID_HANDLE_VALUE) {
    if (error) {
      error->status = READER_SYNC_VIEW_REVISIONS;
      error->revision_code = READER_REV_DATABASE;
      std::snprintf(error->message,sizeof(error->message),"Product database is unavailable");
    }
    return READER_SYNC_VIEW_REVISIONS;
  }
  unsigned char header[100];
  DWORD bytes = 0;
  auto big_endian = [](const unsigned char *p) -> uint32_t {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) |
      (uint32_t(p[2]) << 8) | uint32_t(p[3]);
  };
  if (!ReadFile(existing,header,sizeof(header),&bytes,nullptr) || bytes != sizeof(header) ||
      std::memcmp(header,"SQLite format 3",16) || big_endian(header + 68) != 1163416144u ||
      (big_endian(header + 60) < 1u || big_endian(header + 60) > 3u)) {
    CloseHandle(existing);
    if (error) {
      error->status = READER_SYNC_VIEW_REVISIONS;
      error->revision_code = READER_REV_DATABASE;
      std::snprintf(error->message,sizeof(error->message),"Product database identity/version is unavailable");
    }
    return READER_SYNC_VIEW_REVISIONS;
  }
  reader_revisions *store = nullptr;
  reader_revision_error revision_error{};
  reader_revision_status opened = reader_revisions_open_raw_v3(database,&store,&revision_error);
  if (opened != READER_REV_OK) {
    CloseHandle(existing);
    if (error) {
      error->status = READER_SYNC_VIEW_REVISIONS;
      error->revision_code = opened;
      std::snprintf(error->message,sizeof(error->message),"Cannot read the product pending queue");
    }
    return READER_SYNC_VIEW_REVISIONS;
  }
  reader_sync_view_options options{};
  options.row_limit = READER_SYNC_VIEW_MAX_ROWS;
  options.detect_conflicts = 1;
  reader_sync_view_status status = reader_sync_view_capture(session,store,&options,out,error);
  reader_revisions_close(&store,nullptr);
  CloseHandle(existing);
  return status;
}
