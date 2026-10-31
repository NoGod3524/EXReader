/* SPDX-License-Identifier: MIT */
/* Debug process fixture only: no migration writes, publication or journal.
   Recovery proves the single immutable fixture original after owner death. */
#ifdef READER_C02_TEST
typedef struct { pc02_lease *lease; pc02_cap *cap; pc02_pending_record record; int events; } c02_test_owner;
static const char c02_fixture_original[] = "C02 Android actual SDK original.\n";
static const char c02_fixture_manifest[] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
static const char c02_fixture_input[] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
static const char c02_fixture_terminal[] = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
static void c02_test_phase(void *context, unsigned phase) {
  int fd = *(int *)context; char event[48]; pc02_identity empty = {0, 0};
  snprintf(event, sizeof(event), "native_phase_%u", phase);
  admission_event(fd, event, empty);
}
static int c02_test_proof(void *context, const char *path, int fd,
    const pc02_pending_record *pending, const char *terminal) {
  exr_library *library = NULL; exr_book *books = NULL; exr_source source = {0};
  exr_error error = {0}; size_t count = 0; char content[sizeof(c02_fixture_original)];
  struct stat held, actual; int pinned = -1, ok = 0; (void)context;
  if (!pending || strcmp(pending->manifest, c02_fixture_manifest) ||
      strcmp(pending->input, c02_fixture_input) || !terminal ||
      strcmp(terminal, c02_fixture_terminal)) goto done;
  pinned = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (pinned < 0 || fstat(fd, &held) || fstat(pinned, &actual) ||
      held.st_dev != actual.st_dev || held.st_ino != actual.st_ino) goto done;
  if (exr_library_open(path, &library, &error) != EXR_OK ||
      exr_library_books(library, NULL, &books, &count, &error) != EXR_OK ||
      count != 1 || exr_library_source(library, books[0].id, &source, &error) != EXR_OK ||
      source.size != sizeof(c02_fixture_original) - 1 || !source.read_at || !source.release) goto done;
  if (source.read_at(source.context, 0, content, sizeof(c02_fixture_original) - 1) != sizeof(c02_fixture_original) - 1 ||
      memcmp(content, c02_fixture_original, sizeof(c02_fixture_original) - 1)) goto done;
  ok = 1;
done:
  if (source.release) source.release(source.context);
  exr_books_free(books, count); exr_library_close(library);
  if (pinned >= 0) close(pinned);
  return ok;
}
JNIEXPORT jboolean JNICALL Java_org_exreader_host_C02Probe_nativeCanOwn(
    JNIEnv *env, jclass type, jint fd, jlong device, jlong inode, jstring relative) {
  pc02_scope *scope = NULL; pc02_lease *lease = NULL; char *path = input_string(env, relative);
  int ok = 0; (void)type;
  if (path && (scope = admission_scope(env, fd, device, inode)))
    ok = pc02_open_in(scope, ANDROID_C02_AUTHORITY, path, PC02_OWNER, NULL, NULL, &lease);
  if (lease) pc02_close(lease);
  if (scope) pc02_scope_close(scope);
  free(path); return ok ? JNI_TRUE : JNI_FALSE;
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_C02Probe_nativeBegin(
    JNIEnv *env, jclass type, jint fd, jlong device, jlong inode, jstring relative) {
  pc02_scope *scope = NULL; char *path = input_string(env, relative);
  c02_test_owner *owner = calloc(1, sizeof(*owner));
  pc02_controls controls = {0}; (void)type;
  if (owner) owner->events = -1;
  if (!owner || !path) goto fail;
  owner->events = admission_events(fd); controls.context = &owner->events; controls.phase = c02_test_phase;
  if (!(scope = admission_scope(env, fd, device, inode)) ||
      !pc02_open_in(scope, ANDROID_C02_AUTHORITY, path, PC02_OWNER, NULL, &controls, &owner->lease) ||
      !pc02_begin(owner->lease, c02_fixture_manifest, c02_fixture_input, &owner->cap) ||
      !pc02_pending(owner->lease, &owner->record)) goto fail;
  pc02_scope_close(scope); free(path);
  return (jlong)(intptr_t)owner;
fail:
  /* A live PENDING capability cannot be dropped. Fail closed until this debug
     process dies, just like the production owner lifecycle. */
  if (owner && !owner->cap) {
    if (owner->lease) pc02_close(owner->lease);
    if (owner->events >= 0) close(owner->events);
    free(owner);
  }
  if (scope) pc02_scope_close(scope);
  free(path); admission_error(env, "Cannot begin native pending fixture"); return 0;
}
JNIEXPORT jbyteArray JNICALL Java_org_exreader_host_C02Probe_pending(JNIEnv *env, jclass type, jlong handle) {
  c02_test_owner *owner = (c02_test_owner *)(intptr_t)handle;
  jbyteArray out; (void)type;
  if (!owner || !owner->cap) return NULL;
  out = (*env)->NewByteArray(env, sizeof(owner->record));
  if (out) (*env)->SetByteArrayRegion(env, out, 0, sizeof(owner->record), (jbyte *)&owner->record);
  return out;
}
JNIEXPORT jboolean JNICALL Java_org_exreader_host_C02Probe_nativeRecover(
    JNIEnv *env, jclass type, jint fd, jlong device, jlong inode, jstring relative, jbyteArray exact) {
  pc02_scope *scope = NULL; pc02_lease *lease = NULL; pc02_cap *cap = NULL;
  pc02_pending_record record; pc02_controls controls = {0}; pc02_grant grant;
  char *path = input_string(env, relative); int events = admission_events(fd), ok = 0; (void)type;
  controls.context = &events; controls.phase = c02_test_phase;
  if (!path || !exact || (*env)->GetArrayLength(env, exact) != sizeof(record)) goto done;
  (*env)->GetByteArrayRegion(env, exact, 0, sizeof(record), (jbyte *)&record);
  if ((*env)->ExceptionCheck(env) || !(scope = admission_scope(env, fd, device, inode)) ||
      !pc02_open_in(scope, ANDROID_C02_AUTHORITY, path, PC02_RECOVER, NULL, &controls, &lease) ||
      !pc02_resume(lease, &record, &cap)) goto done;
  ok = pc02_finish(lease, cap, c02_fixture_terminal, c02_test_proof, NULL, &grant);
done:
  if (lease && (!cap || ok)) pc02_close(lease);
  if (scope) pc02_scope_close(scope);
  if (events >= 0) close(events);
  free(path); return ok ? JNI_TRUE : JNI_FALSE;
}
#endif
