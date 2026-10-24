/* SPDX-License-Identifier: MIT */
#ifndef EXR_WEBDAV_ANDROID_H
#define EXR_WEBDAV_ANDROID_H
#include <jni.h>
#include "exr_webdav.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Bind once from a Java-origin JNI entry so the support class is resolved by
 * the host class loader. No Activity/Context is retained and no I/O occurs.
 * Install the optional Android library and its pinned runtime dependencies.
 * Returns IO while the support class/VM is unavailable; the existing C ABI and
 * its status enum do not change. Create/call/free clients on one native worker,
 * never the UI thread; native-created threads attach only around Java calls. */
exr_webdav_status exr_webdav_android_initialize(JNIEnv *env);
#ifdef __cplusplus
}
#endif
#endif
