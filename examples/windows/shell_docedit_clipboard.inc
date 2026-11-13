/* SPDX-License-Identifier: MIT */
/* Include after de_edit, before de_key; dispatch de_clipboard_key(key) for
   Ctrl+C/X/V. Table UI can use de_clipboard_copy/insert with paragraph IDs.
   Define DE_CLIPBOARD_MODEL_ONLY for the console model acceptance. */
typedef struct { exr_edit_id block; size_t run,byte; } de_clip_pos;
typedef struct { exr_edit_id *ids; size_t count,capacity; } de_clip_blocks;
static char *de_clip_text;
static size_t de_clip_size;

static int de_clip_collect(de_clip_blocks *out,const exr_edit_block *b) {
  if(b->kind==EXR_EDIT_TABLE && b->table) {
    for(size_t r=0;r<b->table->row_count;r++)
      for(size_t c=0;c<b->table->rows[r].cell_count;c++) {
        const exr_edit_cell *cell=&b->table->rows[r].cells[c];
        for(size_t p=0;p<cell->block_count;p++)
          if(!de_clip_collect(out,&cell->blocks[p]))return 0;
      }
  } else if(b->kind==EXR_EDIT_PARAGRAPH) {
    if(out->count==out->capacity) {
      size_t capacity=out->capacity ? out->capacity*2:16;
      if(capacity<out->capacity || capacity>SIZE_MAX/sizeof(*out->ids))return 0;
      void *ids=realloc(out->ids,capacity*sizeof(*out->ids));if(!ids)return 0;
      out->ids=ids;out->capacity=capacity;
    }
    out->ids[out->count++]=b->id;
  }
  return 1;
}
static int de_clip_valid(exr_edit_doc *doc,de_clip_pos p) {
  const exr_edit_block *b=exr_edit_find_block(doc,p.block);
  if(!b || b->kind!=EXR_EDIT_PARAGRAPH || p.run>b->run_count)return 0;
  if(p.run==b->run_count)return p.byte==0;
  const exr_edit_run *r=&b->runs[p.run];
  if(r->kind!=EXR_EDIT_TEXT)return p.byte==0;
  return p.byte<=r->text_size && (p.byte==r->text_size ||
    ((unsigned char)r->text[p.byte]&0xc0)!=0x80);
}
static int de_clip_append(char **text,size_t *size,const char *s,size_t n) {
  if(n>SIZE_MAX-*size-1)return 0;
  char *next=realloc(*text,*size+n+1);if(!next)return 0;
  if(n)memcpy(next+*size,s,n);
  *size+=n;next[*size]=0;*text=next;return 1;
}
/* Plain text only. Paragraph and cell boundaries become LF. Cutting clears
   selected text in place, retaining cell grids, paragraphs and opaque XML. */
static int de_clipboard_copy(exr_edit_doc *doc,de_clip_pos a,de_clip_pos z,int cut) {
  de_clip_blocks blocks={0};char *text=NULL;size_t size=0,first=SIZE_MAX,last=SIZE_MAX;
  int ok=0;exr_edit_tx *tx=NULL;
  if(!de_clip_valid(doc,a) || !de_clip_valid(doc,z))return 0;
  for(size_t i=0;i<exr_edit_block_count(doc);i++)
    if(!de_clip_collect(&blocks,exr_edit_block_at(doc,i)))goto done;
  for(size_t i=0;i<blocks.count;i++) {
    if(blocks.ids[i]==a.block)first=i;
    if(blocks.ids[i]==z.block)last=i;
  }
  if(first==SIZE_MAX || last==SIZE_MAX)goto done;
  if(first>last || (first==last && (a.run>z.run || (a.run==z.run && a.byte>z.byte)))) {
    size_t swap=first;first=last;last=swap;de_clip_pos p=a;a=z;z=p;
  }
  if(first==last && a.run==z.run && a.byte==z.byte)goto done;
  if(cut) {tx=exr_edit_begin(doc);if(!tx)goto done;}
  for(size_t i=first;i<=last;i++) {
    const exr_edit_block *b=exr_edit_find_block(doc,blocks.ids[i]);
    size_t count=b->run_count;
    if(i>first && !de_clip_append(&text,&size,"\n",1))goto done;
    for(size_t j=0;j<count;j++) {
      b=exr_edit_find_block(doc,blocks.ids[i]);const exr_edit_run *r=&b->runs[j];
      if((i==first && j<a.run) || (i==last && j>z.run))continue;
      size_t from=i==first && j==a.run ? a.byte:0;
      size_t to=i==last && j==z.run ? z.byte:r->text_size;
      if(r->kind!=EXR_EDIT_TEXT)continue;
      if(!de_clip_append(&text,&size,r->text+from,to-from))goto done;
      if(cut && from!=to) {
        size_t n=r->text_size-(to-from);char *keep=malloc(n+1);if(!keep)goto done;
        memcpy(keep,r->text,from);memcpy(keep+from,r->text+to,r->text_size-to);keep[n]=0;
        exr_status status=exr_edit_set_run_text(doc,b->id,j,keep,n);free(keep);
        if(status!=EXR_OK)goto done;
      }
    }
  }
  if(!text && !de_clip_append(&text,&size,"",0))goto done;
  if(tx) {exr_status status=exr_edit_commit(tx);tx=NULL;if(status!=EXR_OK)goto done;}
  free(de_clip_text);de_clip_text=text;de_clip_size=size;text=NULL;ok=1;
done:
  if(tx)exr_edit_rollback(tx);
  free(blocks.ids);free(text);return ok;
}
/* A single-run insertion retains the destination's properties/template and all
   sibling cell paragraphs. The caller owns any surrounding transaction. */
static exr_status de_clipboard_insert(exr_edit_doc *doc,de_clip_pos *p,const char *text,size_t n) {
  if(!de_clip_valid(doc,*p) || (!text && n))return EXR_ARGUMENT;
  const exr_edit_block *b=exr_edit_find_block(doc,p->block);
  size_t run=p->run,at=p->byte;
  if(run==b->run_count && run && b->runs[run-1].kind==EXR_EDIT_TEXT) {
    run--;at=b->runs[run].text_size;
  }
  if(run>=b->run_count || b->runs[run].kind!=EXR_EDIT_TEXT)return EXR_UNSUPPORTED;
  const exr_edit_run *r=&b->runs[run];
  if(n>SIZE_MAX-r->text_size-1)return EXR_MEMORY;
  char *joined=malloc(r->text_size+n+1);if(!joined)return EXR_MEMORY;
  memcpy(joined,r->text,at);if(n)memcpy(joined+at,text,n);
  memcpy(joined+at+n,r->text+at,r->text_size-at);joined[r->text_size+n]=0;
  exr_status status=exr_edit_set_run_text(doc,b->id,run,joined,r->text_size+n);free(joined);
  if(status==EXR_OK) {p->run=run;p->byte=at+n;}return status;
}

#ifndef DE_CLIPBOARD_MODEL_ONLY
static DWORD de_clip_sequence;
static void de_clipboard_publish(void) {
  if(de_clip_size>INT_MAX)return;
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,de_clip_text,(int)de_clip_size,NULL,0);
  if(!n && de_clip_size)return;
  HGLOBAL memory=GlobalAlloc(GMEM_MOVEABLE,((size_t)n+1)*sizeof(wchar_t));if(!memory)return;
  wchar_t *wide=GlobalLock(memory);if(!wide) {GlobalFree(memory);return;}
  MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,de_clip_text,(int)de_clip_size,wide,n);wide[n]=0;
  GlobalUnlock(memory);
  if(OpenClipboard(g.window)) {
    if(EmptyClipboard() && SetClipboardData(CF_UNICODETEXT,memory))memory=NULL;
    CloseClipboard();
  }
  if(memory)GlobalFree(memory);
  de_clip_sequence=GetClipboardSequenceNumber();
}
static char *de_clipboard_read(size_t *size) {
  char *text=NULL;*size=0;
  if(!OpenClipboard(g.window))return NULL;
  HANDLE memory=GetClipboardData(CF_UNICODETEXT);
  const wchar_t *wide=memory ? GlobalLock(memory):NULL;
  if(wide) {
    size_t capacity=GlobalSize(memory)/sizeof(wchar_t),n=0;
    while(n<capacity && wide[n])n++;
    if(n<capacity && n<=INT_MAX) {
      int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,(int)n,NULL,0,NULL,NULL);
      if(bytes || !n) {
        text=malloc((size_t)bytes+1);
        if(text) {
          WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,(int)n,text,bytes,NULL,NULL);
          /* Normalize Windows and old Mac line endings to the internal LF. */
          for(int i=0;i<bytes;i++) {
            if(text[i]=='\r') {text[(*size)++]='\n';if(i+1<bytes && text[i+1]=='\n')i++;}
            else text[(*size)++]=text[i];
          }
          text[*size]=0;
        }
      }
    }
    GlobalUnlock(memory);
  }
  CloseClipboard();return text;
}
#ifndef DE_CLIPBOARD_TRANSPORT_ONLY
/* Keep multiline paste and selection replacement in one undo entry. */
static int de_clipboard_paste_text(const char *text,size_t n) {
  if(!memchr(text,'\n',n))return de_edit(DE_TYPE,text,n);
  de_pos caret=de_caret(),anchor=de_anchor();
  exr_edit_run_props pending=de.pending_props;
  exr_edit_tx *tx=exr_edit_begin(de.doc);exr_status status=tx ? EXR_OK:EXR_MEMORY;
  if(tx) {
    if(de_selected())status=de_delete_range(anchor,caret);
    for(size_t from=0;from<=n && status==EXR_OK;) {
      size_t to=from;while(to<n && text[to]!='\n')to++;
      if(to>from)status=de_insert(text+from,to-from);
      if(status!=EXR_OK || to==n)break;
      exr_edit_run_props inherited=de_current_props();de_merge_props(&inherited,&de.pending_props);
      de_pos p=de_normalize(de_caret());const exr_edit_block *b=exr_edit_block_at(de.doc,p.block);
      status=exr_edit_split_paragraph(de.doc,b->id,p.run,p.byte);
      if(status==EXR_OK) {de_set_caret(de_normalize(de_start(p.block+1)));de.pending_props=inherited;}
      from=to+1;
    }
    if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);
  }
  if(status!=EXR_OK) {
    de_set_caret(caret);de_set_anchor(anchor);de.pending_props=pending;
    set_status(L"无法粘贴到此位置；此次修改已撤回。");return 0;
  }
  de.dirty=1;de.layout_dirty=1;de_set_anchor(de_caret());de_refresh(1);return 1;
}
static int de_clipboard_key(WPARAM key) {
  if(key!='C' && key!='X' && key!='V')return 0;
  if(key=='C' || key=='X') {
    if(!de_selected())return 1;
    de_pos a=de_normalize(de_anchor()),z=de_normalize(de_caret());
    const exr_edit_block *left=exr_edit_block_at(de.doc,a.block),*right=exr_edit_block_at(de.doc,z.block);
    de_clip_pos start={left->id,a.run,a.byte},end={right->id,z.run,z.byte};
    if(de_clipboard_copy(de.doc,start,end,key=='X')) {
      de_clipboard_publish();
      if(key=='X') {
        de_set_caret(de_compare(a,z)<0 ? a:z);de_set_anchor(de_caret());
        de.dirty=1;de.layout_dirty=1;de_refresh(1);
      }
    } else set_status(L"无法复制或剪切此选区；原文已保留。");
    return 1;
  }
  size_t n=de_clip_size;char *external=NULL;const char *text=de_clip_text;
  if(!text || de_clip_sequence!=GetClipboardSequenceNumber()) {
    external=de_clipboard_read(&n);text=external;
  }
  if(text && n)de_clipboard_paste_text(text,n);
  free(external);return 1;
}
#endif
#endif
