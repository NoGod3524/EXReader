/* SPDX-License-Identifier: MIT */
#undef NDEBUG
#include "../src/glyph_atlas_internal.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
  exr_glyph_atlas atlas={0};exr_atlas_key a={0},b;exr_atlas_entry *entry;size_t entry_bytes;
  unsigned char pixels[4]={0,127,128,255};exr_bitmap mask={0};
  exr_atlas_bound(&atlas,100);
  atlas.entry_limit=2;atlas.byte_limit=1024*1024;
  mask.width=mask.height=2;mask.stride=2;mask.channels=1;mask.pixels=pixels;
  a.face=1;a.glyph=a.character=65;a.size=12*64;a.phase=1;a.matrix[0]=a.matrix[3]=.012;a.matrix[4]=.25;
  assert(!exr_atlas_find(&atlas,&a));
  entry=exr_atlas_store(&atlas,&a,&mask,-2,3,123,100);
  assert(entry && entry->left==-2 && entry->top==3 && entry->work==123);
  assert(!memcmp(entry->mask.pixels,pixels,4));
  b=a;b.glyph++;b.character++;assert(exr_atlas_store(&atlas,&b,&mask,0,0,0,100));
  assert(exr_atlas_find(&atlas,&a)==entry); /* A is now MRU. */
  b.glyph++;b.character++;assert(exr_atlas_store(&atlas,&b,&mask,0,0,0,100));
  b.glyph--;b.character--;assert(!exr_atlas_find(&atlas,&b)); /* B, not A, evicted. */
  assert(exr_atlas_find(&atlas,&a)==entry && atlas.count==2 && atlas.evictions==1);
  b=a;b.face++;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.scope=1;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.glyph++;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.size++;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.phase++;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.flags++;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.character++;assert(!exr_atlas_find(&atlas,&b));
  b=a;b.glyph=UINT32_MAX;assert(exr_atlas_find(&atlas,&b)==entry);
  b=a;b.matrix[4]+=.001;assert(!exr_atlas_find(&atlas,&b)); /* Same quarter-phase, different exact coverage. */
  b=a;b.matrix[2]=.001;assert(!exr_atlas_find(&atlas,&b)); /* Shear is part of identity. */
  entry_bytes=entry->bytes;atlas.byte_limit=sizeof(atlas)+entry_bytes;
  assert(exr_atlas_store(&atlas,&a,&mask,0,0,0,100));
  assert(atlas.count==1 && atlas.bytes+sizeof(atlas)<=atlas.byte_limit);
  atlas.byte_limit=sizeof(atlas)+entry_bytes-1;
  assert(!exr_atlas_store(&atlas,&a,&mask,0,0,0,100));
  exr_atlas_bound(&atlas,100);assert(!atlas.count && !atlas.bytes);
  atlas.entry_limit=0;assert(!exr_atlas_store(&atlas,&a,&mask,0,0,0,100));
  exr_atlas_clear(&atlas);
  atlas.entry_limit=2;atlas.byte_limit=1024*1024;
  assert(exr_atlas_store(&atlas,&a,&mask,0,0,0,100));
  b=a;b.scope=1;assert(exr_atlas_store(&atlas,&b,&mask,0,0,0,100));
  exr_atlas_clear_scope(&atlas,1);assert(atlas.count==1 && exr_atlas_find(&atlas,&a));
  assert(!exr_atlas_find(&atlas,&b));exr_atlas_clear(&atlas);
  puts("{\"lru_entry_byte_bounds_and_key_isolation\":true}");
  return 0;
}
