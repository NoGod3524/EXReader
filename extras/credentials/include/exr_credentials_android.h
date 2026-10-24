/* SPDX-License-Identifier: MIT */
#ifndef EXR_CREDENTIALS_ANDROID_H
#define EXR_CREDENTIALS_ANDROID_H
#include <jni.h>
#include "exr_credentials.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Binds the C ABI to org.exreader.credentials.CredentialStore from the
   Android library. Call once from a Java thread (for example from the host's
   own JNI entry) with any Context; the application context is retained.
   Until it succeeds every C operation returns EXR_CRED_UNAVAILABLE. Returns
   ARGUMENT for NULL arguments and UNAVAILABLE when the class is not packaged. */
exr_credentials_status exr_credentials_android_initialize(JNIEnv *env, jobject context);
#ifdef __cplusplus
}
#endif
#endif
