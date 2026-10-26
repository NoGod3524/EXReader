/* SPDX-License-Identifier: MIT */
#include <reader_projection.h>
#include <cstring>
#include <cstdio>
#include <new>
#include <vector>

namespace {
struct item { reader_revision_info info; reader_revision_selection selection; char key[257]; };
struct batch { std::vector<item> items; bool failed = false; };
int collect(void *context, const reader_revision_entity_row *row) {
  auto *batch = static_cast<struct batch *>(context);
  item value{};
  value.info = row->info; value.selection = row->selection;
  size_t length = std::strlen(row->entity_key);
  if (length >= sizeof(value.key)) { batch->failed = true; return 1; }
  std::memcpy(value.key, row->entity_key, length + 1);
  try { batch->items.push_back(value); } catch (...) { batch->failed = true; return 1; }
  return 0;
}
reader_revision_status failure(reader_revision_error *error,reader_revision_status status,const char *message) {
  if (error) { std::memset(error,0,sizeof(*error)); error->code=status; std::snprintf(error->message,sizeof(error->message),"%s",message); }
  return status;
}
reader_revision_status page(bool raw, reader_revisions *store, const char *kind, const char *after,
    size_t capacity, reader_organization_projection_row *rows, size_t *count, reader_revision_error *error) {
  if (count) *count = 0;
  if (error) std::memset(error,0,sizeof(*error));
  if (!kind || (std::strcmp(kind,"shelf") && std::strcmp(kind,"tag") &&
      std::strcmp(kind,"series") && std::strcmp(kind,"membership")) || !rows || !count || !capacity || capacity > 100)
    return failure(error,READER_REV_ARGUMENT,"Organization page requires kind, rows, count and capacity 1..100");
  batch copied;
  try { copied.items.reserve(capacity); } catch (...) { return failure(error,READER_REV_MEMORY,"Cannot allocate organization page"); }
  reader_revision_status status;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if (raw) status = reader_revision_entities_page_raw_v3(store,kind,after,1,capacity,collect,&copied,error);
  else
#else
  (void)raw;
#endif
    status = reader_revision_entities_page(store,kind,after,1,capacity,collect,&copied,error);
  if (status != READER_REV_OK) return status;
  if (copied.failed) return failure(error,READER_REV_MEMORY,"Cannot copy organization page");
  for (const auto &value : copied.items) {
    auto &row = rows[*count]; std::memset(&row,0,sizeof(row));
    std::strcpy(row.entity_key,value.key); row.selection = value.selection;
    row.info = value.info;
    if (value.selection.kind != READER_SELECTION_SAFE) {
      row.result = READER_ORGANIZATION_UNSAFE_HISTORY;
    } else {
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
      if (raw) status = reader_revision_project_raw_v3(store,kind,value.key,value.info.revision_id,nullptr,nullptr,error);
      else
#endif
        status = reader_revision_project(store,kind,value.key,value.info.revision_id,nullptr,nullptr,error);
      if (status == READER_REV_OK) row.result = READER_ORGANIZATION_PROJECTED;
      else if (status == READER_REV_UNSAFE) {
        char *wire = nullptr; size_t bytes = 0; reader_revision_info current{}; reader_revision_selection selection{};
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
        if (raw) status = reader_revision_selected_raw_v3(store,kind,value.key,&wire,&bytes,&current,&selection,error);
        else
#endif
          status = reader_revision_selected(store,kind,value.key,&wire,&bytes,&current,&selection,error);
        reader_revision_bytes_free(wire);
        if (status != READER_REV_OK && status != READER_REV_UNSAFE && status != READER_REV_NOT_FOUND) return status;
        if (status != READER_REV_OK || std::strcmp(current.revision_id,value.info.revision_id)) {
          row.result = READER_ORGANIZATION_HEAD_CHANGED; row.selection = selection;
        } else row.result = READER_ORGANIZATION_PENDING_DEPENDENCY;
      } else return status;
    }
    ++*count;
  }
  if (error) std::memset(error,0,sizeof(*error));
  return READER_REV_OK;
}
}
extern "C" reader_revision_status reader_organization_project_page(reader_revisions *s,const char *k,const char *a,size_t n,reader_organization_projection_row *r,size_t *c,reader_revision_error *e) { return page(false,s,k,a,n,r,c,e); }
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_revision_status reader_organization_project_page_raw_v3(reader_revisions *s,const char *k,const char *a,size_t n,reader_organization_projection_row *r,size_t *c,reader_revision_error *e) { return page(true,s,k,a,n,r,c,e); }
#endif
