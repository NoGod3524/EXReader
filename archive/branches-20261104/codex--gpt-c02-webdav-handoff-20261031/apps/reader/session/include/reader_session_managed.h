/* SPDX-License-Identifier: MIT */
#ifndef READER_SESSION_MANAGED_H
#define READER_SESSION_MANAGED_H
#include "reader_session.h"
#include <exr_webdav_managed.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_SESSION_MANAGED_VERSION "0.1.0"
/* Copies profile before starting the worker. SDK/UI handles never cross it.
 * The old constructors retain their original staging behavior. */
reader_session_status reader_session_create_managed_raw_v3(const reader_session_config *,const char *profile,reader_session **);
reader_session_status reader_session_managed_observe(reader_session *,exr_webdav_managed_snapshot *);
/* Idle-only, asynchronous cleanup retry. Closes the network connection and
 * performs offline recovery on that same worker; no download, import or PUT.
 * Closing/destroying still follows request_close -> CLOSED -> destroy. */
reader_session_status reader_session_managed_retry_cleanup(reader_session *);
#ifdef __cplusplus
}
#endif
#endif
