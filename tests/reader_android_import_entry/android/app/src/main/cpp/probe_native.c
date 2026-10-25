/* SPDX-License-Identifier: MIT
   Probe JNI: the INSTALLED sample bridge (single translation unit, so it can see the handle) plus one read-back
   check that streams the stored original through exr_library_source and compares it with the staged file. */
#include "host_bridge.c"
#include <stdio.h>

JNIEXPORT jboolean JNICALL Java_org_exreader_importprobe_ProbeNative_equalsStaged(JNIEnv *env, jclass cls,
    jlong handle, jlong book_id, jstring path) {
  bridge *b = (bridge *)(intptr_t)handle;
  const char *p = (*env)->GetStringUTFChars(env, path, NULL);
  exr_source source;
  exr_error error;
  FILE *file;
  unsigned char got[65536], want[65536];
  uint64_t offset = 0;
  int equal = 0;
  (void)cls;
  if (!p || !on_owner(b)) { if (p) (*env)->ReleaseStringUTFChars(env, path, p); return JNI_FALSE; }
  memset(&source, 0, sizeof(source));
  file = fopen(p, "rb");
  if (file && exr_library_source(b->library, book_id, &source, &error) == EXR_OK) {
    equal = 1;
    fseek(file, 0, SEEK_END);
    if ((uint64_t)ftell(file) != source.size) equal = 0;
    fseek(file, 0, SEEK_SET);
    while (equal && offset < source.size) {
      size_t n = source.size - offset > sizeof(got) ? sizeof(got) : (size_t)(source.size - offset);
      if (source.read_at(source.context, offset, got, n) != n || fread(want, 1, n, file) != n || memcmp(got, want, n)) equal = 0;
      offset += n;
    }
    source.release(source.context);
  }
  if (file) fclose(file);
  (*env)->ReleaseStringUTFChars(env, path, p);
  return equal ? JNI_TRUE : JNI_FALSE;
}
