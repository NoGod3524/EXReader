/* SPDX-License-Identifier: MIT */
#ifndef EXR_DROP_INTERNAL_H
#define EXR_DROP_INTERNAL_H
#include "exr_desktop_drop.h"

typedef struct {
  exr_drop_item_status status;
  char *path;
  char *source;
} drop_tmp_item;

typedef struct {
  drop_tmp_item *items;
  size_t count, capacity, duplicates, overflow;
  exr_drop_origin origin;
  exr_drop_control control;
  exr_drop_status failure;
} drop_builder;

void drop_builder_init(drop_builder *builder, exr_drop_origin origin, const exr_drop_control *control);
/* Nonzero once cancelled or failed; callers stop feeding entries. */
int drop_builder_stopped(drop_builder *builder);
/* Frees everything and reports the failure (or EXR_DROP_CANCELLED/EMPTY). */
exr_drop_status drop_builder_finish(drop_builder *builder, exr_drop_request **out);
void drop_builder_free(drop_builder *builder);
/* One entry: a native absolute path or a URI, as UTF-8 / UTF-16. */
void drop_add_utf8_entry(drop_builder *builder, const char *entry, size_t size);
void drop_add_utf16_entry(drop_builder *builder, const uint16_t *units, size_t count);
void drop_add_virtual(drop_builder *builder, const uint16_t *name_units, size_t count);
exr_drop_status drop_utf16_split(const uint16_t *units, size_t count, exr_drop_utf16_layout layout,
    drop_builder *builder);

/* Delivery objects shared by every platform. base must be the first member
   of the platform struct. */
struct exr_drop_target {
  void (*on_drop)(void *context, exr_drop_status status, exr_drop_request *request);
  void *context;
  exr_drop_control control;
  int dead, in_callback, destroy_pending;
  int (*owner_thread)(const struct exr_drop_target *target);
  void (*release)(struct exr_drop_target *target); /* detach + free the whole object */
};
void drop_target_init(struct exr_drop_target *target, const exr_drop_target_options *options,
    int (*owner_thread)(const struct exr_drop_target *), void (*release)(struct exr_drop_target *));
int drop_target_options_valid(const exr_drop_target_options *options);
/* The target's copy of the caller's control, always struct_size-valid. */
const exr_drop_control *drop_target_control(const struct exr_drop_target *target);
void drop_target_deliver(struct exr_drop_target *target, exr_drop_status status, exr_drop_request *request);

#endif
