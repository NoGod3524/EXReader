#include <jni.h>
int platform_probe(const char *, const char *, const char *, int);
JNIEXPORT jint JNICALL Java_org_exreader_platformprobe_MainActivity_probe(
    JNIEnv *env, jclass type, jstring book, jstring font, jstring directory, jboolean reopen) {
  (void)type;
  const char *b = (*env)->GetStringUTFChars(env, book, NULL);
  if (!b) return 2;
  const char *f = (*env)->GetStringUTFChars(env, font, NULL);
  const char *d = f ? (*env)->GetStringUTFChars(env, directory, NULL) : NULL;
  int result = d ? platform_probe(b, f, d, reopen) : 2;
  if (d) (*env)->ReleaseStringUTFChars(env, directory, d);
  if (f) (*env)->ReleaseStringUTFChars(env, font, f);
  (*env)->ReleaseStringUTFChars(env, book, b);
  return result;
}
