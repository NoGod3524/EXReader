/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
#undef free
#undef malloc
#undef calloc
#undef realloc
#ifndef NDEBUG
#ifdef _WIN32
#include <windows.h>
static SRWLOCK registry_lock = SRWLOCK_INIT;
static void lock_registry(void) { AcquireSRWLockExclusive(&registry_lock); }
static void unlock_registry(void) { ReleaseSRWLockExclusive(&registry_lock); }
#else
#include <stdatomic.h>
static atomic_flag registry_lock = ATOMIC_FLAG_INIT;
static void lock_registry(void) { while (atomic_flag_test_and_set(&registry_lock)) {} }
static void unlock_registry(void) { atomic_flag_clear(&registry_lock); }
#endif
typedef union { exr_allocation_alignment align; uint64_t magic; } object_header;
typedef struct object_record object_record;
struct object_record {
  object_header *allocation;
  void *object;
  size_t size, kind, active;
  int released, releasing, loaned;
  object_record *parents[4], *next, *hash_next;
};
typedef struct buffer_record buffer_record;
typedef struct borrowed_record {
  uintptr_t address;
  size_t size;
  object_record *owner;
  buffer_record *buffer;
  struct borrowed_record *next;
} borrowed_record;
struct buffer_record {
  void *data;
  size_t size, active;
  int exposed, dead;
  object_record *parents[4];
  buffer_record *next, *hash_next, **previous;
};
static buffer_record *buffers, *buffer_buckets[4096];
#define COUNT(type) { #type, 0, 0, 0 }
static exr_lifetime_count counts[] = {
  COUNT(exr_aac), COUNT(exr_audio), COUNT(exr_audio_output), COUNT(exr_audio_player),
  COUNT(exr_bidi), COUNT(exr_canvas), COUNT(exr_cfi), COUNT(exr_dictionary),
  COUNT(exr_document), COUNT(exr_fixed_document), COUNT(exr_fixed_text), COUNT(exr_flac),
  COUNT(exr_font), COUNT(exr_font_manager), COUNT(exr_hyphenation), COUNT(exr_hyphenator),
  COUNT(exr_layout), COUNT(exr_library), COUNT(exr_m4b), COUNT(exr_m4b_inspection),
  COUNT(exr_mp3), COUNT(exr_pager), COUNT(exr_pcm), COUNT(exr_publication),
  COUNT(exr_session), COUNT(exr_sevenz), COUNT(exr_stretch), COUNT(exr_text_index),
  COUNT(exr_text_query), COUNT(exr_txt_cursor), COUNT(exr_wave), COUNT(sdk_buffer)
};
#undef COUNT
static object_record *objects, *buckets[4096];
static borrowed_record *borrows;
static int registered_exit;
static size_t bucket(const void *p) { return ((uintptr_t)p >> 4) % 4096; }
static uint64_t magic(size_t kind) { return UINT64_C(0x4558524c49564500) + kind; }
static void violation(const char *message) {
#ifdef _MSC_VER
  _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
#endif
  fprintf(stderr, "EXR_LIFETIME_ASSERT: %s\n", message);
  fflush(stderr); abort();
}
static object_record *exact(const void *p) {
  object_record *r;
  for (r = buckets[bucket(p)]; r; r = r->hash_next) if (r->object == p) return r;
  return NULL;
}
static object_record *lookup(const void *p) {
  borrowed_record *b;
  object_record *r = exact(p);
  uintptr_t address = (uintptr_t)p;
  if (r || !p) return r;
  for (b = borrows; b; b = b->next)
    if (address >= b->address && address - b->address < b->size) {
      if (b->buffer && b->buffer->dead) violation("对象已释放");
      return b->owner;
    }
  return NULL;
}
static buffer_record *buffer_at(const void *p) {
  buffer_record *b;
  for (b = buffer_buckets[bucket(p)]; b; b = b->hash_next) if (b->data == p) return b;
  return NULL;
}
static buffer_record *buffer_containing(const void *p) {
  buffer_record *b = buffer_at(p);
  if (b || !p) return b;
  for (b = buffers; b; b = b->next)
    if ((uintptr_t)p >= (uintptr_t)b->data &&
        (uintptr_t)p - (uintptr_t)b->data < b->size) return b;
  return NULL;
}
static void check_buffer(const void *p) {
  buffer_record *b = buffer_at(p);
  if (b && b->dead) violation("对象已释放");
}
static void check_record(object_record *r) {
  if (!r->allocation->magic) violation("对象已释放");
  if (r->allocation->magic != magic(r->kind)) violation("对象魔术字损坏");
}
/* Quarantine reserves handle addresses until the diagnostic epoch ends. Only
   handle shells remain: destructors release their payloads immediately. */
static void cleanup(int exiting) {
  object_record *r, *next;
  borrowed_record *b, *bn;
  buffer_record *buffer, *buffer_next;
  lock_registry();
  if (!exiting)
    for (r = objects; r; r = r->next)
      if (r->allocation->magic || r->active) violation("清理时仍有活动对象");
  if (!exiting)
    for (buffer = buffers; buffer; buffer = buffer->next)
      if (!buffer->dead || buffer->active) violation("清理时仍有活动缓冲区");
  for (b = borrows; b; b = bn) { bn = b->next; free(b); }
  borrows = NULL;
  for (r = objects; r; r = next) {
    next = r->next;
    /* Drop live registry roots at exit, so LSan sees leaks. Never destroy an
       unreleased client object or conceal it with automatic cleanup. */
    if (!r->allocation->magic) free(r->allocation);
    free(r);
  }
  objects = NULL; memset(buckets, 0, sizeof(buckets));
  for (buffer = buffers; buffer; buffer = buffer_next) {
    buffer_next = buffer->next;
    if (buffer->dead) free(buffer->data);
    free(buffer);
  }
  buffers = NULL; memset(buffer_buckets, 0, sizeof(buffer_buckets));
  unlock_registry();
}
static void exit_cleanup(void) { cleanup(1); }
static void register_exit(void) {
  if (!registered_exit) {
    if (atexit(exit_cleanup)) violation("无法注册生命周期清理");
    registered_exit = 1;
  }
}
static buffer_record *track_buffer(void *p, size_t size) {
  buffer_record *b = calloc(1, sizeof(*b));
  size_t kind = sizeof(counts)/sizeof(*counts)-1, hash = bucket(p);
  if (!b) return NULL;
  register_exit();
  b->data = p; b->size = size;
  b->hash_next = buffer_buckets[hash]; buffer_buckets[hash] = b;
  b->next = buffers; b->previous = &buffers;
  if (buffers) buffers->previous = &b->next;
  buffers = b; counts[kind].created++; counts[kind].live++;
  return b;
}
void *exr_lifetime_malloc(size_t size) {
  void *p = malloc(size ? size : 1);
  if (!p) return NULL;
  lock_registry();
  if (!track_buffer(p, size ? size : 1)) { free(p); p = NULL; }
  unlock_registry(); return p;
}
void *exr_lifetime_calloc(size_t count, size_t size) {
  void *p;
  if (size && count > SIZE_MAX / size) return NULL;
  p = exr_lifetime_malloc(count * size);
  if (p) memset(p, 0, count * size);
  return p;
}
void exr_lifetime_own(void *p, size_t size) {
  buffer_record *b;
  borrowed_record **link;
  if (!p) return;
  lock_registry();
  b = buffer_at(p);
  if (!b && !exact(p)) b = track_buffer(p, size ? size : 1);
  if (b) {
    if (b->dead) violation("对象已释放");
    b->exposed = 1;
    /* take() can transfer a previously borrowed canvas allocation. Its new
       owner is the returned value, so the old canvas must not invalidate it. */
    for (link = &borrows; *link;) {
      borrowed_record *view = *link;
      if (view->buffer == b) { *link = view->next; free(view); }
      else link = &view->next;
    }
  }
  unlock_registry();
}
static void unhash_buffer(buffer_record *b) {
  buffer_record **link = &buffer_buckets[bucket(b->data)];
  while (*link != b) link = &(*link)->hash_next;
  *link = b->hash_next;
}
void *exr_lifetime_realloc(void *p, size_t size) {
  buffer_record *b;
  void *result;
  if (!p) return exr_lifetime_malloc(size);
  if (!size) { exr_lifetime_delete(p); return NULL; }
  lock_registry(); b = buffer_at(p);
  if (b && b->dead) violation("对象已释放");
  if (b && b->exposed) {
    size_t old_size = b->size;
    unlock_registry();
    result = exr_lifetime_malloc(size);
    if (result) { memcpy(result, p, size < old_size ? size : old_size); exr_lifetime_delete(p); }
    return result;
  }
  result = realloc(p, size);
  if (result) {
    if (b) {
      unhash_buffer(b); b->data = result; b->size = size;
      b->hash_next = buffer_buckets[bucket(result)]; buffer_buckets[bucket(result)] = b;
    } else if (!track_buffer(result, size)) violation("无法登记缓冲区");
  }
  unlock_registry(); return result;
}
void *exr_lifetime_new(size_t size, const char *type) {
  object_header *h; object_record *r; size_t kind, index;
  if (size > SIZE_MAX - sizeof(*h)) return NULL;
  h = calloc(1, sizeof(*h) + size); r = calloc(1, sizeof(*r));
  if (!h || !r) { free(h); free(r); return NULL; }
  lock_registry();
  for (kind = 0; kind < sizeof(counts)/sizeof(*counts); kind++)
    if (!strcmp(counts[kind].type, type)) break;
  if (kind == sizeof(counts)/sizeof(*counts)) violation("未登记的对象类型");
  register_exit();
  h->magic = magic(kind);
  r->allocation = h; r->object = h + 1; r->size = size; r->kind = kind;
  index = bucket(r->object); r->hash_next = buckets[index]; buckets[index] = r;
  r->next = objects; objects = r;
  counts[kind].created++; counts[kind].live++;
  unlock_registry(); return h + 1;
}
void exr_lifetime_delete(void *p) {
  object_record *r;
  buffer_record *b;
  size_t kind = sizeof(counts)/sizeof(*counts)-1;
  if (!p) return;
  lock_registry(); r = exact(p);
  if (!r) {
    b = buffer_at(p);
    if (!b) { unlock_registry(); free(p); return; }
    if (b->dead) violation("对象已释放");
    b->dead = 1; counts[kind].freed++; counts[kind].live--;
    if (!b->exposed) {
      unhash_buffer(b); *b->previous = b->next;
      if (b->next) b->next->previous = b->previous;
      free(b->data); free(b);
    }
    unlock_registry(); return;
  }
  check_record(r); r->allocation->magic = 0;
  counts[r->kind].freed++; counts[r->kind].live--;
  unlock_registry();
}
void exr_lifetime_depend(const void *p, unsigned slot, const void *parent) {
  object_record *r, *owner;
  buffer_record *b;
  lock_registry(); r = exact(p); owner = lookup(parent);
  if (slot >= 4) violation("对象依赖槽溢出");
  if (r) { check_record(r); if (owner) check_record(owner); r->parents[slot] = owner; }
  else if ((b = buffer_at(p)) != NULL) {
    if (b->dead) violation("对象已释放");
    if (owner) check_record(owner);
    b->parents[slot] = owner;
  }
  unlock_registry();
}
void exr_lifetime_release_public(const void *p) {
  object_record *r;
  if (!p) return;
  lock_registry(); r = exact(p);
  if (r) {
    check_record(r);
    if (r->released) violation("对象已释放");
    if (r->loaned) violation("借用对象不能释放");
    /* CLOSE notifications may observe the last committed audio state. Reentry
       that destroys/mutates still fails on active; retire the caller reference
       when the outer destruction scope returns. */
    r->releasing = 1;
  }
  unlock_registry();
}
void exr_lifetime_expect(const void *p, const char *type) {
  object_record *r;
  if (!p) return;
  lock_registry(); r = exact(p);
  if (r) {
    check_record(r);
    if (strcmp(type, counts[r->kind].type)) violation("对象类型或释放函数错误");
  }
  unlock_registry();
}
void exr_lifetime_loan(const void *owner, const void *p) {
  object_record *r, *parent;
  if (!owner || !p) return;
  lock_registry(); r = exact(p); parent = lookup(owner);
  if (r && parent && r != parent) {
    check_record(r); check_record(parent);
    r->loaned = 1; r->parents[3] = parent;
  }
  unlock_registry();
}
void exr_lifetime_borrow(const void *owner, const void *data, size_t size) {
  object_record *r; borrowed_record *b;
  buffer_record *buffer;
  if (!owner || !data || !size) return;
  lock_registry(); r = lookup(owner);
  if (!r) { unlock_registry(); return; }
  check_record(r);
  buffer = buffer_containing(data);
  if (buffer) {
    if (buffer->dead) violation("对象已释放");
    buffer->exposed = 1;
  }
  for (b = borrows; b; b = b->next)
    if (b->owner == r && b->address == (uintptr_t)data) {
      if (size > b->size) b->size = size;
      unlock_registry(); return;
    }
  b = malloc(sizeof(*b));
  if (!b) violation("无法登记借用指针");
  *b = (borrowed_record){(uintptr_t)data, size, r, buffer, borrows}; borrows = b;
  unlock_registry();
}
static void collect(exr_lifetime_scope *scope, object_record *r, int dependencies,
                    object_record **path, size_t depth) {
  size_t i;
  if (!r) return;
  check_record(r);
  for (i = 0; i < depth; i++) if (path[i] == r) violation("对象依赖链存在环");
  for (i = 0; i < scope->count; i++) if (scope->records[i] == r) return;
  if (scope->count == 64 || depth == 64) violation("对象依赖链过深");
  scope->records[scope->count++] = r;
  if (!dependencies) return;
  path[depth++] = r;
  for (i = 0; i < 4; i++) collect(scope, r->parents[i], 1, path, depth);
}
int exr_lifetime_begin(exr_lifetime_scope *scope, const void *const *p, size_t count, int mode) {
  size_t i, j; object_record *path[64];
  scope->count = scope->buffer_count = 0; lock_registry();
  for (i = 0; i < count; i++) {
    buffer_record *b = buffer_at(p[i]);
    object_record *owner;
    check_buffer(p[i]); owner = lookup(p[i]);
    if (owner && owner->released) violation("对象已释放");
    if (mode == 2 && owner && !exact(p[i])) violation("借用指针不能释放");
    collect(scope, owner, mode != 2, path, 0);
    if (b) {
      b->exposed = 1;
      if (mode != 2)
        for (j = 0; j < 4; j++) collect(scope, b->parents[j], 1, path, 0);
      for (j = 0; j < scope->buffer_count; j++) if (scope->buffers[j] == b) break;
      if (j == scope->buffer_count) {
        if (j == 64) violation("活动缓冲区过多");
        scope->buffers[scope->buffer_count++] = b;
      }
    }
  }
  for (i = 0; i < scope->count; i++) {
    object_record *r = scope->records[i];
    if (r->active && mode != 1) {
      if (mode == 2) violation("重入：不能释放活动对象");
      scope->count = 0; unlock_registry(); return 0;
    }
  }
  for (i = 0; i < scope->buffer_count; i++) {
    buffer_record *b = scope->buffers[i];
    if (b->active && mode != 1) {
      if (mode == 2) violation("重入：不能释放活动缓冲区");
      scope->count = scope->buffer_count = 0; unlock_registry(); return 0;
    }
  }
  for (i = 0; i < scope->count; i++) ((object_record *)scope->records[i])->active++;
  for (i = 0; i < scope->buffer_count; i++) ((buffer_record *)scope->buffers[i])->active++;
  unlock_registry(); return 1;
}
void exr_lifetime_end(exr_lifetime_scope *scope) {
  size_t i; lock_registry();
  for (i = 0; i < scope->count; i++) {
    object_record *r = scope->records[i];
    if (!--r->active && r->releasing) { r->released = 1; r->releasing = 0; }
  }
  for (i = 0; i < scope->buffer_count; i++) ((buffer_record *)scope->buffers[i])->active--;
  unlock_registry();
}
int exr_validate(const void *p) {
  exr_lifetime_scope scope = {0}; object_record *path[64], *r;
  int found;
  lock_registry(); check_buffer(p); r = lookup(p);
  if (r && r->released) violation("对象已释放");
  collect(&scope, r, 1, path, 0);
  if (!r) {
    buffer_record *b = buffer_at(p);
    size_t i;
    if (b) for (i = 0; i < 4; i++) collect(&scope, b->parents[i], 1, path, 0);
  }
  found = r != NULL || buffer_at(p) != NULL;
  unlock_registry(); return found;
}
size_t exr_debug_counts(exr_lifetime_count *out, size_t capacity) {
  size_t count = sizeof(counts)/sizeof(*counts), n = capacity < count ? capacity : count;
  lock_registry(); if (out) memcpy(out, counts, n * sizeof(*out)); unlock_registry(); return count;
}
void exr_debug_cleanup(void) { cleanup(0); }
#else
int exr_validate(const void *p) { (void)p; return 1; }
size_t exr_debug_counts(exr_lifetime_count *out, size_t capacity) { (void)out; (void)capacity; return 0; }
void exr_debug_cleanup(void) {}
#endif
