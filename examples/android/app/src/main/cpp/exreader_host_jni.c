/* SPDX-License-Identifier: MIT */
/* Local Android host bridge: SDK library rows, selectors and annotations.
   Only installed public headers are used; no engine internals. */
#include <jni.h>
#include <exreader.h>

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void throw_status(JNIEnv *env, exr_status status, const exr_error *error, const char *fallback) {
  char message[512];
  const char *detail = (error && error->message[0]) ? error->message : fallback;
  jclass type;
  if ((*env)->ExceptionCheck(env)) return;
  snprintf(message, sizeof(message), "%s (code %d)", detail, (int)status);
  type = (*env)->FindClass(env, "java/lang/RuntimeException");
  if (!type) return;
  (*env)->ThrowNew(env, type, message);
  (*env)->DeleteLocalRef(env, type);
}

static void throw_argument(JNIEnv *env, const char *message) {
  jclass type;
  if ((*env)->ExceptionCheck(env)) return;
  type = (*env)->FindClass(env, "java/lang/IllegalArgumentException");
  if (!type) return;
  (*env)->ThrowNew(env, type, message);
  (*env)->DeleteLocalRef(env, type);
}

static char *copy_string(const char *text) {
  size_t size = strlen(text) + 1;
  char *copy = (char *)malloc(size);
  if (copy) memcpy(copy, text, size);
  return copy;
}

static char *input_string(JNIEnv *env, jstring value) {
  const jchar *chars;
  char *copy; jsize length, i; size_t out=0;
  if (!value) return NULL;
  length=(*env)->GetStringLength(env,value);
  chars = (*env)->GetStringChars(env, value, NULL);
  if (!chars) return NULL;
  copy=malloc((size_t)length*3+1);
  if(!copy) { (*env)->ReleaseStringChars(env,value,chars); throw_argument(env,"Cannot allocate UTF-8 input"); return NULL; }
  for(i=0;i<length;i++) {
    uint32_t cp=chars[i];
    if(cp>=0xd800 && cp<=0xdbff && i+1<length && chars[i+1]>=0xdc00 && chars[i+1]<=0xdfff)
      { cp=0x10000+((cp-0xd800)<<10)+(chars[++i]-0xdc00); }
    else if(!cp || (cp>=0xd800 && cp<=0xdfff)) {
      free(copy); (*env)->ReleaseStringChars(env,value,chars);
      throw_argument(env,"Text contains NUL or an unpaired UTF-16 surrogate"); return NULL;
    }
    if(cp<0x80) copy[out++]=(char)cp;
    else if(cp<0x800) { copy[out++]=(char)(0xc0|(cp>>6)); copy[out++]=(char)(0x80|(cp&63)); }
    else if(cp<0x10000) { copy[out++]=(char)(0xe0|(cp>>12)); copy[out++]=(char)(0x80|((cp>>6)&63)); copy[out++]=(char)(0x80|(cp&63)); }
    else { copy[out++]=(char)(0xf0|(cp>>18)); copy[out++]=(char)(0x80|((cp>>12)&63)); copy[out++]=(char)(0x80|((cp>>6)&63)); copy[out++]=(char)(0x80|(cp&63)); }
  }
  copy[out]=0;
  (*env)->ReleaseStringChars(env, value, chars);
  return copy;
}

static int note_owner(JNIEnv *env,exr_library *store,jlong book,jlong id,int fixed) {
  exr_error error={0}; exr_status status; size_t count=0,i; int found=0;
  if(fixed) {
    exr_fixed_note *notes=NULL; status=exr_library_fixed_notes(store,(int64_t)book,&notes,&count,&error);
    if(status==EXR_OK) for(i=0;i<count;i++) if(notes[i].id==(int64_t)id) found=1;
    exr_fixed_notes_free(notes,count);
  } else {
    exr_note *notes=NULL; status=exr_library_notes(store,(int64_t)book,&notes,&count,&error);
    if(status==EXR_OK) for(i=0;i<count;i++) if(notes[i].id==(int64_t)id) found=1;
    exr_notes_free(notes,count);
  }
  if(status!=EXR_OK) { throw_status(env,status,&error,"Cannot verify annotation ownership"); return 0; }
  if(!found) throw_argument(env,"Annotation does not belong to the selected book");
  return found;
}

static jstring output_bytes(JNIEnv *env, const char *text,size_t length) {
  size_t index = 0, produced = 0;
  jchar *units;
  jstring result;
  if (!text) text = "";
  units = (jchar *)malloc((length + 1) * sizeof(jchar));
  if (!units) {
    jclass type = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
    if (type) {
      (*env)->ThrowNew(env, type, "Cannot allocate a Java string");
      (*env)->DeleteLocalRef(env, type);
    }
    return NULL;
  }
  while (index < length) {
    unsigned char lead = (unsigned char)text[index++];
    uint32_t code = 0xfffd;
    unsigned extra = 0, k;
    if (lead < 0x80) {
      code = lead;
    } else if (lead >= 0xc2 && lead <= 0xdf) {
      code = lead & 0x1f;
      extra = 1;
    } else if (lead >= 0xe0 && lead <= 0xef) {
      code = lead & 0x0f;
      extra = 2;
    } else if (lead >= 0xf0 && lead <= 0xf4) {
      code = lead & 0x07;
      extra = 3;
    }
    if (extra) {
      if (index + extra > length) {
        code = 0xfffd;
        extra = 0;
      } else {
        for (k = 0; k < extra; k++) {
          unsigned char part = (unsigned char)text[index + k];
          if ((part & 0xc0) != 0x80) {
            code = 0xfffd;
            break;
          }
          code = (code << 6) | (part & 0x3f);
        }
        index += extra;
        if ((extra == 1 && code < 0x80) || (extra == 2 && code < 0x800) ||
            (extra == 3 && code < 0x10000) || code > 0x10ffff ||
            (code >= 0xd800 && code <= 0xdfff))
          code = 0xfffd;
      }
    }
    if (code > 0xffff) {
      code -= 0x10000;
      units[produced++] = (jchar)(0xd800 + (code >> 10));
      units[produced++] = (jchar)(0xdc00 + (code & 0x3ff));
    } else {
      units[produced++] = (jchar)code;
    }
  }
  result = (*env)->NewString(env, units, (jsize)produced);
  free(units);
  return result;
}

static jstring output_string(JNIEnv *env,const char *text) { return output_bytes(env,text ? text : "",text ? strlen(text) : 0); }

static unsigned char *read_entire_file(const char *path, size_t *size) {
  FILE *file;
  long length;
  unsigned char *data;
  size_t read;
  *size = 0;
  file = fopen(path, "rb");
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  length = ftell(file);
  if (length < 0 || (unsigned long)length > 128u * 1024u * 1024u) { fclose(file); return NULL; }
  if (fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
  data = (unsigned char *)malloc((size_t)length ? (size_t)length : 1);
  if (!data) { fclose(file); return NULL; }
  read = fread(data, 1, (size_t)length, file);
  fclose(file);
  if (read != (size_t)length) { free(data); return NULL; }
  *size = (size_t)length;
  return data;
}

static exr_library *library(JNIEnv *env, jlong handle) {
  if (!handle) {
    jclass type = (*env)->FindClass(env, "java/lang/IllegalStateException");
    if (type) {
      (*env)->ThrowNew(env, type, "Library handle is closed");
      (*env)->DeleteLocalRef(env, type);
    }
    return NULL;
  }
  return (exr_library *)(intptr_t)handle;
}

static jobjectArray new_rows(JNIEnv *env, jsize count) {
  jclass type = (*env)->FindClass(env, "[Ljava/lang/String;");
  jobjectArray rows;
  if (!type) return NULL;
  rows = (*env)->NewObjectArray(env, count, type, NULL);
  (*env)->DeleteLocalRef(env, type);
  return rows;
}

static jobjectArray new_row(JNIEnv *env, jsize columns) {
  jclass type = (*env)->FindClass(env, "java/lang/String");
  jobjectArray row;
  if (!type) return NULL;
  row = (*env)->NewObjectArray(env, columns, type, NULL);
  (*env)->DeleteLocalRef(env, type);
  return row;
}

static int set_cell(JNIEnv *env, jobjectArray row, jsize column, const char *value) {
  jstring text = output_string(env, value);
  if (!text) return 0;
  (*env)->SetObjectArrayElement(env, row, column, text);
  (*env)->DeleteLocalRef(env, text);
  return (*env)->ExceptionCheck(env) ? 0 : 1;
}

static int set_cell_bytes(JNIEnv *env,jobjectArray row,jsize column,const char *value,size_t size) {
  jstring text=output_bytes(env,value,size);
  if(!text) return 0;
  (*env)->SetObjectArrayElement(env,row,column,text);
  (*env)->DeleteLocalRef(env,text);
  return (*env)->ExceptionCheck(env) ? 0 : 1;
}

static int set_number(JNIEnv *env, jobjectArray row, jsize column, long long value) {
  char buffer[32];
  snprintf(buffer, sizeof(buffer), "%lld", value);
  return set_cell(env, row, column, buffer);
}

JNIEXPORT jstring JNICALL Java_org_exreader_host_NativeLibrary_nativeIdentity(JNIEnv *env, jclass type) {
  char buffer[128];
  (void)type;
  snprintf(buffer, sizeof(buffer), "%s/%u", exr_version(), exr_abi_version());
  return output_string(env, buffer);
}

JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeLibrary_nativeOpen(JNIEnv *env, jclass type, jstring path) {
  char *name = input_string(env, path);
  exr_library *handle = NULL;
  exr_error error;
  exr_status status;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!name) {
    if (!(*env)->ExceptionCheck(env)) throw_argument(env, "Library path is required");
    return 0;
  }
  status = exr_library_open(name, &handle, &error);
  free(name);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot open the library");
    return 0;
  }
  return (jlong)(intptr_t)handle;
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeClose(JNIEnv *env, jclass type, jlong handle) {
  (void)env;
  (void)type;
  if (handle) exr_library_close((exr_library *)(intptr_t)handle);
}

JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeLibrary_nativeBooks(JNIEnv *env, jclass type, jlong handle) {
  exr_library *store = library(env, handle);
  exr_book *books = NULL;
  size_t count = 0, i;
  exr_error error;
  exr_status status;
  jobjectArray rows;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return NULL;
  status = exr_library_books(store, NULL, &books, &count, &error);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot read the shelf");
    return NULL;
  }
  if (count > INT_MAX) {
    exr_books_free(books, count);
    throw_argument(env, "Too many books");
    return NULL;
  }
  rows = new_rows(env, (jsize)count);
  for (i = 0; rows && i < count; i++) {
    jobjectArray row = new_row(env, 8);
    if (!row) break;
    if (!set_number(env, row, 0, (long long)books[i].id) ||
        !set_number(env, row, 1, (long long)books[i].format) ||
        !set_cell(env, row, 2, books[i].title) ||
        !set_cell(env, row, 3, books[i].author) ||
        !set_cell(env, row, 4, books[i].tags) ||
        !set_number(env, row, 5, books[i].favorite) ||
        !set_number(env, row, 6, books[i].status) ||
        !set_number(env, row, 7, (long long)books[i].position)) {
      (*env)->DeleteLocalRef(env, row);
      break;
    }
    (*env)->SetObjectArrayElement(env, rows, (jsize)i, row);
    (*env)->DeleteLocalRef(env, row);
  }
  exr_books_free(books, count);
  return (*env)->ExceptionCheck(env) ? NULL : rows;
}

JNIEXPORT jlongArray JNICALL Java_org_exreader_host_NativeLibrary_nativeImportFile(
    JNIEnv *env, jclass type, jlong handle, jstring path, jint format, jstring title) {
  exr_library *store = library(env, handle);
  char *file = NULL, *name = NULL;
  int64_t id = 0;
  int created = 0;
  exr_error error;
  exr_status status;
  jlong values[2];
  jlongArray result;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return NULL;
  if (format < EXR_TXT || format > EXR_CBZ) {
    throw_argument(env, "Unsupported import format");
    return NULL;
  }
  /* Allocate the Java result before a database insert can commit. */
  result = (*env)->NewLongArray(env, 2);
  if (!result) return NULL;
  file = input_string(env, path);
  name = input_string(env, title);
  if (!file || !name) {
    free(file);
    free(name);
    if (!(*env)->ExceptionCheck(env)) throw_argument(env, "Import path and title are required");
    return NULL;
  }
  if (!name[0]) {
    free(name);
    name = copy_string("Untitled");
    if (!name) {
      free(file);
      throw_argument(env, "Cannot allocate a title");
      return NULL;
    }
  }
  if (format == EXR_PDF || format == EXR_CBZ) {
    status = exr_library_import_file_unique(store, (exr_format)format, file, name, &id, &created, &error);
  } else {
    size_t size = 0;
    unsigned char *data = read_entire_file(file, &size);
    if (!data) {
      free(file);
      free(name);
      throw_status(env, EXR_IO, NULL, "Cannot read the selected book");
      return NULL;
    }
    status = exr_library_import_unique(store, (exr_format)format, data, size, name, &id, &created, &error);
    free(data);
  }
  free(file);
  free(name);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot import the book");
    return NULL;
  }
  values[0] = (jlong)id;
  values[1] = (jlong)created;
  if (result) (*env)->SetLongArrayRegion(env, result, 0, 2, values);
  return result;
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeSetPosition(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong position) {
  exr_library *store = library(env, handle);
  exr_book *books = NULL;
  size_t count = 0, i;
  int found = 0;
  exr_error error;
  exr_status status = EXR_OK;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return;
  if (book_id <= 0 || position < 0) {
    throw_argument(env, "Invalid reading position");
    return;
  }
  status = exr_library_books(store, NULL, &books, &count, &error);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot read the shelf");
    return;
  }
  for (i = 0; i < count; i++) {
    if (books[i].id != book_id) continue;
    books[i].position = (size_t)position;
    status = exr_library_update(store, &books[i], &error);
    found = 1;
    break;
  }
  exr_books_free(books, count);
  if (!found) {
    throw_argument(env, "Book is missing from the shelf");
    return;
  }
  if (status != EXR_OK) throw_status(env, status, &error, "Cannot save the reading position");
}

JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeLibrary_nativeNotes(
    JNIEnv *env, jclass type, jlong handle, jlong book_id) {
  exr_library *store = library(env, handle);
  exr_note *notes = NULL;
  size_t count = 0, i;
  exr_error error;
  exr_status status;
  jobjectArray rows;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return NULL;
  status = exr_library_notes(store, (int64_t)book_id, &notes, &count, &error);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot read annotations");
    return NULL;
  }
  if (count > INT_MAX) {
    exr_notes_free(notes, count);
    throw_argument(env, "Too many annotations");
    return NULL;
  }
  {
    exr_document *document = NULL;
    for (i = 0; i < count; i++) {
      exr_anchor_match match;
      if (!notes[i].anchor.exact) continue; /* Legacy offsets. */
      if (!document) {
        status = exr_library_document(store, (int64_t)book_id, &document, &error);
        if (status != EXR_OK) break;
      }
      memset(&match, 0, sizeof(match));
      status = exr_anchor_resolve(document, &notes[i].anchor, &match, &error);
      if (status != EXR_OK) break;
      notes[i].start = match.state == EXR_ANCHOR_FOUND ? match.start : SIZE_MAX;
      notes[i].end = match.state == EXR_ANCHOR_FOUND ? match.end : SIZE_MAX;
    }
    exr_document_free(document);
    if (status != EXR_OK) {
      exr_notes_free(notes, count);
      throw_status(env, status, &error, "Cannot resolve annotations");
      return NULL;
    }
  }
  rows = new_rows(env, (jsize)count);
  for (i = 0; rows && i < count; i++) {
    jobjectArray row = new_row(env, 5);
    if (!row) break;
    if (!set_number(env, row, 0, (long long)notes[i].id) ||
        !set_number(env, row, 1, notes[i].start == SIZE_MAX ? -1 : (long long)notes[i].start) ||
        !set_number(env, row, 2, notes[i].end == SIZE_MAX ? -1 : (long long)notes[i].end) ||
        !set_cell(env, row, 3, notes[i].text) ||
        !set_cell(env, row, 4, notes[i].anchor.exact)) {
      (*env)->DeleteLocalRef(env, row);
      break;
    }
    (*env)->SetObjectArrayElement(env, rows, (jsize)i, row);
    (*env)->DeleteLocalRef(env, row);
  }
  exr_notes_free(notes, count);
  return (*env)->ExceptionCheck(env) ? NULL : rows;
}

JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeLibrary_nativeSaveNote(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong note_id,
    jlong start, jlong end, jstring comment) {
  exr_library *store = library(env, handle);
  exr_note note;
  char *text = NULL;
  int64_t id = 0;
  exr_error error;
  exr_status status;
  (void)type;
  memset(&note, 0, sizeof(note));
  memset(&error, 0, sizeof(error));
  if (!store) return 0;
  if (book_id <= 0 || start < 0 || end < start || note_id < 0) {
    throw_argument(env, "Invalid annotation range");
    return 0;
  }
  text = input_string(env, comment);
  if (!text) {
    if (!(*env)->ExceptionCheck(env)) throw_argument(env, "Comment is required");
    return 0;
  }
  note.id = (int64_t)note_id;
  note.book_id = (int64_t)book_id;
  note.start = (size_t)start;
  note.end = (size_t)end;
  note.text = text;
  status = exr_library_note(store, &note, &id, &error);
  free(text);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot save the annotation");
    return 0;
  }
  return (jlong)id;
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeUpdateNoteText(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong note_id, jstring comment) {
  exr_library *store = library(env, handle);
  char *text;
  exr_error error;
  exr_status status;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return;
  if (!note_owner(env,store,book_id,note_id,0)) return;
  if (note_id <= 0) {
    throw_argument(env, "Invalid annotation id");
    return;
  }
  text = input_string(env, comment);
  if (!text) {
    if (!(*env)->ExceptionCheck(env)) throw_argument(env, "Comment is required");
    return;
  }
  status = exr_library_note_text(store, (int64_t)note_id, text, &error);
  free(text);
  if (status != EXR_OK) throw_status(env, status, &error, "Cannot update the annotation");
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeRemoveNote(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong note_id) {
  exr_library *store = library(env, handle);
  exr_error error;
  exr_status status;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return;
  if (!note_owner(env,store,book_id,note_id,0)) return;
  status = exr_library_remove_note(store, (int64_t)note_id, &error);
  if (status != EXR_OK) throw_status(env, status, &error, "Cannot remove the annotation");
}

JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeLibrary_nativeFixedNotes(
    JNIEnv *env, jclass type, jlong handle, jlong book_id) {
  exr_library *store = library(env, handle);
  exr_fixed_note *notes = NULL;
  size_t count = 0, i;
  exr_error error;
  exr_status status;
  jobjectArray rows;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return NULL;
  status = exr_library_fixed_notes(store, (int64_t)book_id, &notes, &count, &error);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot read page annotations");
    return NULL;
  }
  if (count > INT_MAX) {
    exr_fixed_notes_free(notes, count);
    throw_argument(env, "Too many annotations");
    return NULL;
  }
  if (count) {
    exr_fixed_document *document = NULL;
    exr_fixed_open_options options;
    const exr_fixed_page *pages;
    size_t page_count = 0;
    memset(&options, 0, sizeof(options));
    options.struct_size = sizeof(options);
    status = exr_library_fixed(store, (int64_t)book_id, &options, &document, &error);
    pages = status == EXR_OK ? exr_fixed_pages(document, &page_count) : NULL;
    for (i = 0; status == EXR_OK && i < count; i++) {
      exr_fixed_text *text = NULL;
      exr_anchor_match match;
      size_t page;
      for (page = 0; page < page_count; page++)
        if (strcmp(pages[page].id, notes[i].anchor.page_id) == 0) break;
      notes[i].start = notes[i].end = SIZE_MAX;
      if (page == page_count) { notes[i].page = SIZE_MAX; continue; }
      notes[i].page = page;
      status = exr_fixed_load_text(document, page, NULL, &text, &error);
      if (status == EXR_OK) {
        memset(&match, 0, sizeof(match));
        status = exr_fixed_anchor_resolve(pages[page].id, text, &notes[i].anchor, NULL, &match, &error);
        if (status == EXR_OK && match.state == EXR_ANCHOR_FOUND) {
          notes[i].start = match.start;
          notes[i].end = match.end;
        }
      }
      exr_fixed_text_free(text);
    }
    exr_fixed_free(document);
    if (status != EXR_OK) {
      exr_fixed_notes_free(notes, count);
      throw_status(env, status, &error, "Cannot resolve page annotations");
      return NULL;
    }
  }
  rows = new_rows(env, (jsize)count);
  for (i = 0; rows && i < count; i++) {
    jobjectArray row = new_row(env, 6);
    if (!row) break;
    if (!set_number(env, row, 0, (long long)notes[i].id) ||
        !set_number(env, row, 1, notes[i].page == SIZE_MAX ? -1 : (long long)notes[i].page) ||
        !set_number(env, row, 2, notes[i].start == SIZE_MAX ? -1 : (long long)notes[i].start) ||
        !set_number(env, row, 3, notes[i].end == SIZE_MAX ? -1 : (long long)notes[i].end) ||
        !set_cell(env, row, 4, notes[i].text) ||
        !set_cell_bytes(env, row, 5, notes[i].anchor.exact,notes[i].anchor.exact_size)) {
      (*env)->DeleteLocalRef(env, row);
      break;
    }
    (*env)->SetObjectArrayElement(env, rows, (jsize)i, row);
    (*env)->DeleteLocalRef(env, row);
  }
  exr_fixed_notes_free(notes, count);
  return (*env)->ExceptionCheck(env) ? NULL : rows;
}

JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeLibrary_nativeSaveFixedNote(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong note_id,
    jlong page, jlong start, jlong end, jstring comment) {
  exr_library *store = library(env, handle);
  exr_fixed_note note;
  char *text = NULL;
  int64_t id = 0;
  exr_error error;
  exr_status status;
  (void)type;
  memset(&note, 0, sizeof(note));
  memset(&error, 0, sizeof(error));
  if (!store) return 0;
  if (book_id <= 0 || page < 0 || start < 0 || end < start || note_id < 0) {
    throw_argument(env, "Invalid page annotation range");
    return 0;
  }
  text = input_string(env, comment);
  if (!text) {
    if (!(*env)->ExceptionCheck(env)) throw_argument(env, "Comment is required");
    return 0;
  }
  note.id = (int64_t)note_id;
  note.book_id = (int64_t)book_id;
  note.page = (size_t)page;
  note.start = (size_t)start;
  note.end = (size_t)end;
  note.text = text;
  status = exr_library_fixed_note(store, &note, NULL, &id, &error);
  free(text);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot save the page annotation");
    return 0;
  }
  return (jlong)id;
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeRemoveFixedNote(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong note_id) {
  exr_library *store = library(env, handle);
  exr_error error;
  exr_status status;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return;
  if (!note_owner(env,store,book_id,note_id,1)) return;
  status = exr_library_remove_fixed_note(store, (int64_t)note_id, &error);
  if (status != EXR_OK) throw_status(env, status, &error, "Cannot remove the page annotation");
}

JNIEXPORT jlongArray JNICALL Java_org_exreader_host_NativeLibrary_nativeProgress(
    JNIEnv *env, jclass type, jlong handle, jlong book_id) {
  exr_library *store = library(env, handle);
  exr_anchor point;
  exr_anchor_state state = EXR_ANCHOR_MISSING;
  exr_error error;
  exr_status status;
  jlong values[2];
  jlongArray result;
  (void)type;
  memset(&point, 0, sizeof(point));
  memset(&error, 0, sizeof(error));
  if (!store) return NULL;
  status = exr_library_progress_get(store, (int64_t)book_id, &point, &state, &error);
  if (status != EXR_OK) {
    throw_status(env, status, &error, "Cannot read the saved position");
    return NULL;
  }
  /* The stored state only records that a selector exists. Resolve it against
     the stored document so the host can distinguish FOUND from AMBIGUOUS. */
  if (state != EXR_ANCHOR_LEGACY && point.exact) {
    exr_document *document = NULL;
    exr_error resolve_error;
    memset(&resolve_error, 0, sizeof(resolve_error));
    status=exr_library_document(store, (int64_t)book_id, &document, &resolve_error);
    if (status == EXR_OK) {
      exr_anchor_match match;
      memset(&match, 0, sizeof(match));
      status=exr_anchor_resolve(document, &point, &match, &resolve_error);
      if (status == EXR_OK) {
        state = match.state;
        point.start = state == EXR_ANCHOR_FOUND ? match.start : SIZE_MAX;
      }
      exr_document_free(document);
    }
    if(status!=EXR_OK) { exr_anchor_free(&point);throw_status(env,status,&resolve_error,"Cannot resolve saved progress");return NULL; }
  }
  values[0] = (jlong)state;
  values[1] = point.start == SIZE_MAX ? -1 : (jlong)point.start;
  exr_anchor_free(&point);
  result = (*env)->NewLongArray(env, 2);
  if (result) (*env)->SetLongArrayRegion(env, result, 0, 2, values);
  return result;
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeSaveProgress(
    JNIEnv *env, jclass type, jlong handle, jlong book_id, jlong offset) {
  exr_library *store = library(env, handle);
  exr_document *document = NULL;
  exr_anchor point;
  exr_error error;
  exr_status status;
  (void)type;
  memset(&point, 0, sizeof(point));
  memset(&error, 0, sizeof(error));
  if (!store) return;
  if (book_id <= 0 || offset < 0) {
    throw_argument(env, "Invalid reading offset");
    return;
  }
  status = exr_library_document(store, (int64_t)book_id, &document, &error);
  if (status == EXR_OK)
    status = exr_anchor_create(document, (size_t)offset, (size_t)offset, &point, &error);
  if (status == EXR_OK)
    status = exr_library_progress(store, (int64_t)book_id, &point, &error);
  exr_anchor_free(&point);
  exr_document_free(document);
  if (status != EXR_OK) throw_status(env, status, &error, "Cannot save the reading position");
}

JNIEXPORT void JNICALL Java_org_exreader_host_NativeLibrary_nativeDeleteBook(
    JNIEnv *env, jclass type, jlong handle, jlong book_id) {
  exr_library *store = library(env, handle);
  exr_error error;
  exr_status status;
  (void)type;
  memset(&error, 0, sizeof(error));
  if (!store) return;
  status = exr_library_delete(store, (int64_t)book_id, &error);
  if (status != EXR_OK) throw_status(env, status, &error, "Cannot remove the book");
}
