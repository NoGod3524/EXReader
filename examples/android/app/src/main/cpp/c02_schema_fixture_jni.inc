/* SPDX-License-Identifier: MIT */
/* This private Debug image is not an admitted reader or a migration target.
   The source's existing SH stays live for the entire public SDK backup. */
JNIEXPORT jstring JNICALL Java_org_exreader_host_NativeAdmission_nativeSchemaBackup(
    JNIEnv *env, jclass type, jint context, jlong device, jlong inode, jlong handle) {
#ifdef READER_C02_SCHEMA_FIXTURE
  android_library_owner *owner = (android_library_owner *)(intptr_t)handle;
  unsigned char random[16]; size_t offset = 0;
  char name[64] = "schema6-review-", relative[128], parent[PATH_MAX], path[PATH_MAX], descriptor[64];
  struct stat folder, target, actual;
  int entropy = -1, files = -1, directory = -1, output = -1, observed = -1, ok = 0;
  exr_error error = {0}; exr_status status; ssize_t size;
  (void)type;
  if (!owner || !owner->library || owner->closed || !pc02_check(owner->lease) ||
      !admission_context(context, device, inode)) goto done;
  files = openat(context, "files", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (files < 0 || fstat(files, &folder) || !S_ISDIR(folder.st_mode) ||
      folder.st_uid != geteuid() || (folder.st_mode & 0022)) goto done;
  entropy = open("/dev/urandom", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (entropy < 0) goto done;
  while (offset < sizeof(random)) {
    do { size = read(entropy, random + offset, sizeof(random) - offset); } while (size < 0 && errno == EINTR);
    if (size <= 0) goto done;
    offset += (size_t)size;
  }
  close(entropy); entropy = -1;
  for (size_t k = 0; k < sizeof(random); ++k) snprintf(name + 15 + k * 2, 3, "%02x", random[k]);
  if (mkdirat(files, name, 0700)) goto done; /* no adoption or overwrite */
  directory = openat(files, name, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (directory < 0 || fstat(directory, &folder) || folder.st_uid != geteuid() ||
      (folder.st_mode & 0777) != 0700) goto done;
  output = openat(directory, "library.db", O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (output < 0 || fstat(output, &target) || target.st_uid != geteuid() ||
      !S_ISREG(target.st_mode) || target.st_nlink != 1 || target.st_size != 0) goto done;
  snprintf(descriptor, sizeof(descriptor), "/proc/self/fd/%d", directory);
  size = readlink(descriptor, parent, sizeof(parent) - 1);
  if (size <= 0 || (size_t)size >= sizeof(parent) - 1) goto done;
  parent[size] = 0;
  if (snprintf(path, sizeof(path), "%s/library.db", parent) >= (int)sizeof(path)) goto done;
  admission_event(owner->events, "schema_fixture_backup_begin", owner->target);
  /* VACUUM INTO accepts an empty existing file. O_EXCL reserves its exact ID. */
  status = exr_library_backup(owner->library, path, &error);
  if (status != EXR_OK) { throw_status(env, status, &error, "Cannot create private schema fixture"); goto done; }
  observed = openat(directory, "library.db", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (observed < 0 || fstat(observed, &actual) || actual.st_dev != target.st_dev ||
      actual.st_ino != target.st_ino || actual.st_uid != geteuid() ||
      actual.st_nlink != 1 || actual.st_size <= 0 || (actual.st_mode & 0777) != 0600 ||
      !pc02_check(owner->lease) || fsync(output) || fsync(directory) || fsync(files)) goto done;
  if (snprintf(relative, sizeof(relative), "files/%s/library.db", name) >= (int)sizeof(relative)) goto done;
  admission_event(owner->events, "schema_fixture_backup_complete", owner->target);
  ok = 1;
done:
  if (observed >= 0) close(observed);
  if (output >= 0) close(output);
  if (directory >= 0) close(directory);
  if (files >= 0) close(files);
  if (entropy >= 0) close(entropy);
  if (!ok) { admission_error(env, "Private schema fixture failed; source library was retained"); return NULL; }
  return (*env)->NewStringUTF(env, relative);
#else
  (void)type; (void)context; (void)device; (void)inode; (void)handle;
  admission_error(env, "Schema fixture requires a Debug host");
  return NULL;
#endif
}
