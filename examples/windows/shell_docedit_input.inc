/* SPDX-License-Identifier: MIT */
/* All model mutations, including replacing a selection, share one transaction. */
/* Rebuilding cannot carry the paragraph's original XML template through the
   public insert API. Only rebuild when every paragraph property is modeled;
   reject the whole transaction instead of dropping styles, tabs or extensions. */
typedef struct { int depth,properties,ok; char prefix[64]; } de_xml_check;
static int de_standard_namespace(const char *key,const char *value) {
  if(strcmp(key,"xmlns") && strncmp(key,"xmlns:",6))return 0;
  return !strcmp(value,"http://schemas.openxmlformats.org/wordprocessingml/2006/main") ||
    !strcmp(value,"http://schemas.openxmlformats.org/officeDocument/2006/relationships") ||
    !strcmp(value,"http://purl.oclc.org/ooxml/wordprocessingml/main") ||
    !strcmp(value,"http://purl.oclc.org/ooxml/officeDocument/relationships");
}
static void de_check_start(void *context,const char *name,const char **attrs) {
  de_xml_check *check=context;const char *local=strrchr(name,':');local=local ? local+1:name;
  check->depth++;
  if(check->depth==1) {
    size_t length=(size_t)(local-name);
    if(strcmp(local,"p") || length>=sizeof(check->prefix)) {check->ok=0;return;}
    memcpy(check->prefix,name,length);check->prefix[length]=0;
    for(size_t i=0;attrs[i];i+=2) {
      if(de_standard_namespace(attrs[i],attrs[i+1]))continue;
      const char *key=strrchr(attrs[i],':');key=key ? key+1:attrs[i];
      if(strncmp(key,"rsid",4) && strcmp(key,"paraId") && strcmp(key,"textId"))check->ok=0;
    }
  }
  if(check->depth==2 && !strcmp(local,"pPr"))check->properties=1;
  if(!check->properties)return;
  if(strncmp(name,check->prefix,strlen(check->prefix)))check->ok=0;
  const char *allowed="";
  if(!strcmp(local,"pPr") || !strcmp(local,"numPr"))allowed="|";
  else if(!strcmp(local,"keepNext") || !strcmp(local,"keepLines") || !strcmp(local,"pageBreakBefore") ||
    !strcmp(local,"jc") || !strcmp(local,"ilvl") || !strcmp(local,"numId"))allowed="|val|";
  else if(!strcmp(local,"ind"))allowed="|left|right|firstLine|hanging|";
  else if(!strcmp(local,"spacing"))allowed="|before|after|line|lineRule|";
  else {check->ok=0;return;}
  for(size_t i=0;attrs[i];i+=2) {
    if(de_standard_namespace(attrs[i],attrs[i+1]))continue;
    const char *key=strrchr(attrs[i],':');key=key ? key+1:attrs[i];char token[96];
    snprintf(token,sizeof(token),"|%s|",key);
    if(!strstr(allowed,token))check->ok=0;
    if(!strcmp(local,"jc") && strcmp(attrs[i+1],"left") && strcmp(attrs[i+1],"center") &&
      strcmp(attrs[i+1],"right") && strcmp(attrs[i+1],"both"))check->ok=0;
  }
}
static void de_check_end(void *context,const char *name) {
  de_xml_check *check=context;(void)name;
  if(check->depth==2)check->properties=0;
  check->depth--;
}
static int de_rebuild_safe(const exr_edit_block *b) {
  if(!b->opaque_size)return 1;
  if(b->opaque_size>INT_MAX)return 0;
  void *parser=XML_ParserCreate(NULL);if(!parser)return 0;
  de_xml_check check={0,0,1,{0}};XML_SetUserData(parser,&check);
  XML_SetElementHandler(parser,de_check_start,de_check_end);
  int ok=XML_Parse(parser,b->opaque_xml,(int)b->opaque_size,1)==1 && check.ok;
  XML_ParserFree(parser);return ok;
}
static de_pos de_step(de_pos p,int direction) {
  p=de_normalize(p);const exr_edit_block *b=de_block_at(de.doc,p.block);
  if(!b)return p;
  if(direction<0) {
    if(p.run<b->run_count && b->runs[p.run].kind==EXR_EDIT_TEXT && p.byte) {
      p.byte=de_prev_byte(b->runs[p.run].text,p.byte);return de_normalize(p);
    }
    while(p.run) {
      p.run--;p.byte=b->runs[p.run].kind==EXR_EDIT_TEXT ? b->runs[p.run].text_size:0;
      if(de_run_trivia(&b->runs[p.run]))continue;
      if(p.byte)p.byte=de_prev_byte(b->runs[p.run].text,p.byte);
      return de_normalize(p);
    }
    while(p.block) {
      p.block--;
      if(de_block_at(de.doc,p.block)->kind==EXR_EDIT_PARAGRAPH)return de_end(p.block);
    }
  } else {
    for(size_t run=p.run;run<b->run_count;run++) {
      const exr_edit_run *r=&b->runs[run];size_t at=run==p.run ? p.byte:0;
      if(r->kind==EXR_EDIT_TEXT && at<r->text_size) {
        p.run=run;p.byte=de_next_byte(r->text,r->text_size,at);return de_normalize(p);
      }
      if(r->kind==EXR_EDIT_OPAQUE_RUN && !de_run_trivia(r)) {p.run=run+1;p.byte=0;return de_normalize(p);}
    }
    for(size_t i=p.block+1;i<de_block_count(de.doc);i++)
      if(de_block_at(de.doc,i)->kind==EXR_EDIT_PARAGRAPH)return de_normalize(de_start(i));
  }
  return de_normalize(p);
}
static exr_status de_replace_run(exr_edit_id id,size_t run,size_t from,size_t to,const char *text,size_t n) {
  const exr_edit_block *b=exr_edit_find_block(de.doc,id);
  if(!b || run>=b->run_count || b->runs[run].kind!=EXR_EDIT_TEXT)return EXR_UNSUPPORTED;
  const exr_edit_run *r=&b->runs[run];
  if(from>to || to>r->text_size || n>SIZE_MAX-r->text_size-1)return EXR_ARGUMENT;
  size_t length=r->text_size-(to-from)+n;
  char *buffer=malloc(length+1);if(!buffer)return EXR_MEMORY;
  memcpy(buffer,r->text,from);if(n)memcpy(buffer+from,text,n);
  memcpy(buffer+from+n,r->text+to,r->text_size-to);buffer[length]=0;
  exr_status status=exr_edit_set_run_text(de.doc,id,run,buffer,length);free(buffer);return status;
}
/* The public API has no join command. Compose a new paragraph from
   retained run templates and modeled properties, then remove the old blocks.
   Section boundaries and non-paragraph blocks are never crossed by a deletion. */
static exr_status de_join_range(de_pos a,de_pos b) {
  for(size_t i=a.block;i<=b.block;i++)if(!de_same_cell(a.block,i))return EXR_UNSUPPORTED;
  const exr_edit_block *left=de_block_at(de.doc,a.block),*right=de_block_at(de.doc,b.block);
  if(!left || !right)return EXR_ARGUMENT;
  if(!de_rebuild_safe(left))return EXR_UNSUPPORTED;
  for(size_t i=a.block;i<=b.block;i++) {
    const exr_edit_block *block=de_block_at(de.doc,i);
    if(de_block_trivia(block))continue;
    if(block->kind!=EXR_EDIT_PARAGRAPH || block->section_id!=left->section_id)return EXR_UNSUPPORTED;
    for(size_t j=0;j<block->run_count;j++) {
      de_pos before={i,j,0},after={i,j+1,0};
      if(block->runs[j].kind==EXR_EDIT_OPAQUE_RUN && !de_run_trivia(&block->runs[j]) &&
        de_compare(a,after)<0 && de_compare(b,before)>0)
        return EXR_UNSUPPORTED;
    }
  }
  size_t capacity=left->run_count+right->run_count+1,count=0;
  exr_edit_run *runs=calloc(capacity,sizeof(*runs));
  size_t id_count=b.block-a.block+1;
  exr_edit_id *ids=malloc(id_count*sizeof(*ids));
  if(!runs || !ids) {free(runs);free(ids);return EXR_MEMORY;}
  for(size_t i=0;i<id_count;i++)ids[i]=de_block_at(de.doc,a.block+i)->id;
  for(size_t i=0;i<a.run && i<left->run_count;i++)runs[count++]=left->runs[i];
  if(a.run<left->run_count && a.byte) {
    runs[count]=left->runs[a.run];runs[count++].text_size=a.byte;
  }
  size_t prefix=count;
  if(b.run<right->run_count) {
    exr_edit_run r=right->runs[b.run];
    if(r.kind==EXR_EDIT_TEXT) {r.text+=b.byte;r.text_size-=b.byte;}
    runs[count++]=r;
    for(size_t i=b.run+1;i<right->run_count;i++)runs[count++]=right->runs[i];
  }
  exr_edit_id new_id=0;
  exr_status status=exr_edit_insert_paragraph(de.doc,left->id,runs,count,&left->props,&new_id);
  free(runs);
  for(size_t i=0;i<id_count && status==EXR_OK;i++)status=exr_edit_delete_block(de.doc,ids[i]);
  free(ids);
  if(status==EXR_OK) {
    de_pos p={a.block,prefix,0};de_set_caret(de_normalize(p));
  }
  return status;
}
static exr_status de_delete_range(de_pos a,de_pos b) {
  a=de_normalize(a);b=de_normalize(b);
  if(de_compare(a,b)>0) {de_pos temp=a;a=b;b=temp;}
  if(de_compare(a,b)==0)return EXR_OK;
  if(a.block!=b.block)return de_join_range(a,b);
  const exr_edit_block *block=de_block_at(de.doc,a.block);
  if(!block || block->kind!=EXR_EDIT_PARAGRAPH)return EXR_UNSUPPORTED;
  exr_edit_id id=block->id;size_t count=block->run_count;
  for(size_t i=a.run;i<count && i<=b.run;i++) {
    block=exr_edit_find_block(de.doc,id);const exr_edit_run *r=&block->runs[i];
    size_t from=i==a.run ? a.byte:0,to=i==b.run ? b.byte:r->text_size;
    if(de_run_trivia(r))continue;
    if(r->kind==EXR_EDIT_OPAQUE_RUN) {
      if(i<b.run)return EXR_UNSUPPORTED;
    } else if(from!=to) {
      exr_status status=de_replace_run(id,i,from,to,NULL,0);if(status!=EXR_OK)return status;
    }
  }
  de_set_caret(de_normalize(a));return EXR_OK;
}
static exr_status de_insert(exr_edit_tx *tx,const char *text,size_t n) {
  de_pos p=de_normalize(de_caret_pos());const exr_edit_block *b=de_block_at(de.doc,p.block);
  if(!b || b->kind!=EXR_EDIT_PARAGRAPH)return EXR_UNSUPPORTED;
  exr_edit_run_props pending=de.pending_props;
  const exr_edit_run *at=p.run<b->run_count && b->runs[p.run].kind==EXR_EDIT_TEXT ? &b->runs[p.run]:NULL;
  exr_edit_run_props applied=at ? at->props:(exr_edit_run_props){0};
  de_merge_props(&applied,&pending);
  if(!at) {
    exr_status status=exr_edit_insert_run(de.doc,tx,b->id,p.run,text,n,&applied);
    if(status==EXR_OK) {p.byte=n;de_set_caret(p);de.pending_props=pending;}
    return status;
  }
  if(at && (!pending.present || !memcmp(&applied,&at->props,sizeof(applied)))) {
    exr_edit_id id=b->id;
    exr_status status=de_replace_run(b->id,p.run,p.byte,p.byte,text,n);
    if(status==EXR_OK && pending.present)status=exr_edit_set_run_props(de.doc,id,p.run,&applied);
    if(status==EXR_OK) {p.byte+=n;de_set_caret(p);de.pending_props=pending;}return status;
  }
  /* Isolate pending input within an existing run through M-E1's guarded
     paragraph rebuild; unsupported templates roll back. */
  if(!de_rebuild_safe(b))return EXR_UNSUPPORTED;
  exr_edit_run *runs=calloc(b->run_count+3,sizeof(*runs));if(!runs)return EXR_MEMORY;
  size_t count=0;
  for(size_t i=0;i<p.run;i++)runs[count++]=b->runs[i];
  if(at && p.byte) {runs[count]=*at;runs[count++].text_size=p.byte;}
  size_t inserted=count;
  if(at)runs[count]=*at;
  runs[count].kind=EXR_EDIT_TEXT;runs[count].text=text;runs[count].text_size=n;count++;
  if(at && p.byte<at->text_size) {
    runs[count]=*at;runs[count].text+=p.byte;runs[count++].text_size-=p.byte;
  }
  for(size_t i=p.run+(at ? 1:0);i<b->run_count;i++)runs[count++]=b->runs[i];
  exr_edit_id old=b->id,id=0;
  exr_status status=exr_edit_insert_paragraph(de.doc,old,runs,count,&b->props,&id);
  free(runs);
  if(status==EXR_OK && pending.present)status=exr_edit_set_run_props(de.doc,id,inserted,&applied);
  if(status==EXR_OK)status=exr_edit_delete_block(de.doc,old);
  if(status==EXR_OK) {p.run=inserted;p.byte=n;de_set_caret(p);de.pending_props=pending;}return status;
}
static exr_status de_history(int redo) {
  memset(&de.pending_props,0,sizeof(de.pending_props));
  exr_status status=redo ? exr_edit_redo(de.doc):exr_edit_undo(de.doc);
  if(status==EXR_OK) {
    de.dirty=1;de.layout_dirty=1;
    de_pos p=de_normalize(de_caret_pos());
    const exr_edit_block *b=de_block_at(de.doc,p.block);
    if(!b || b->kind!=EXR_EDIT_PARAGRAPH) {
      p=de_start(0);while(p.block<de_block_count(de.doc) &&
        de_block_at(de.doc,p.block)->kind!=EXR_EDIT_PARAGRAPH)p.block++;
    }
    de_set_caret(p);de_set_anchor(p);de_refresh(1);
  }
  return status;
}
#include "shell_docedit_table_history.inc"
enum { DE_TYPE,DE_BACKSPACE,DE_DELETE,DE_ENTER };
static int de_edit(int operation,const char *text,size_t n) {
  if(!de.doc)return 0;
  exr_edit_run_props pending=de.pending_props;
  de_pos caret=de_caret_pos(),anchor=de_anchor();int selected=de_selected();
  de_pos other=caret;
  if(!selected && (operation==DE_BACKSPACE || operation==DE_DELETE)) {
    other=de_step(caret,operation==DE_BACKSPACE ? -1:1);
    if(!de_compare(other,caret))return 1;
  }
  exr_edit_tx *tx=exr_edit_begin(de.doc);exr_status status=tx ? EXR_OK:EXR_MEMORY;
  if(tx) {
    if(selected)status=de_delete_range(anchor,caret);
    else if(operation==DE_BACKSPACE || operation==DE_DELETE)status=de_delete_range(caret,other);
    if(status==EXR_OK && operation==DE_TYPE)status=de_insert(tx,text,n);
    if(status==EXR_OK && operation==DE_ENTER) {
      de_pos p=de_normalize(de_caret_pos());const exr_edit_block *b=de_block_at(de.doc,p.block);
      status=b ? exr_edit_split_paragraph(de.doc,b->id,p.run,p.byte):EXR_ARGUMENT;
      if(status==EXR_OK)de_set_caret(de_normalize(de_start(p.block+1)));
    }
    if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);
  }
  if(status==EXR_OK) {
    if(operation==DE_ENTER)de.pending_props=pending;
    de.dirty=1;de.layout_dirty=1;de_set_anchor(de_caret_pos());de_refresh(1);return 1;
  }
  de_set_caret(caret);de_set_anchor(anchor);de.pending_props=pending;
  set_status(L"无法编辑此位置（受保护内容或内存不足）；此次修改已撤回。");return 0;
}
static int de_leave_table(void) {
  if(!de.caret_in_table)return 0;
  de_cell cell=de_cell_at(de.caret.view);exr_edit_id id=0;
  exr_edit_tx *tx=exr_edit_begin(de.doc);
  exr_status status=tx ? exr_edit_insert_paragraph(de.doc,cell.table,NULL,0,NULL,&id):EXR_MEMORY;
  if(tx) {if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);}
  if(status!=EXR_OK) {set_status(L"无法在表格下方插入段落。");return 0;}
  for(size_t i=0;i<de_block_count(de.doc);i++)if(de_block_at(de.doc,i)->id==id) {
    de_set_caret(de_start(i));de_set_anchor(de_caret_pos());break;
  }
  de.dirty=1;de.layout_dirty=1;de_refresh(1);return 1;
}
static int de_key_modifiers(WPARAM key,int control,int shift,int alt) {
  if(!de.doc)return 0;
  de.high_surrogate=0;
  if(control && alt && key==VK_RETURN && de.caret_in_table) {de_leave_table();return 1;}
  if(key==VK_F6) {de_table_open();return 1;}
  if(control) {
    if(key=='B' || key=='I') {de_command(key=='B' ? DE_BOLD:DE_ITALIC,0);return 1;}
    if(shift && (key==VK_OEM_PERIOD || key==VK_OEM_COMMA)) {
      de_command(key==VK_OEM_PERIOD ? DE_LARGER:DE_SMALLER,0);return 1;
    }
    if(key=='L' || key=='E' || key=='R' || key=='J') {
      de_command(key=='L' ? DE_LEFT:key=='E' ? DE_CENTER:key=='R' ? DE_RIGHT:DE_JUSTIFY,0);return 1;
    }
    if(key=='S') {de_save();return 1;}
    if(key=='Z' || key=='Y') {
      de_history(key=='Y');
      return 1;
    }
    if(key=='A') {
      size_t n=de_block_count(de.doc),first=0,last=n;
      while(first<n && de_block_at(de.doc,first)->kind!=EXR_EDIT_PARAGRAPH)first++;
      while(last>first && de_block_at(de.doc,last-1)->kind!=EXR_EDIT_PARAGRAPH)last--;
      if(first<last) {de_set_anchor(de_start(first));de_set_caret(de_end(last-1));de_refresh(1);}
      return 1;
    }
    if(key==VK_HOME || key==VK_END) {
      de_pos p=de_caret_pos();
      while(key==VK_HOME ? p.block>0:p.block+1<de_block_count(de.doc)) {
        size_t i=key==VK_HOME ? p.block-1:p.block+1;p.block=i;
      }
      if(de_block_at(de.doc,p.block)->kind==EXR_EDIT_PARAGRAPH)
        de_set_caret(key==VK_HOME ? de_start(p.block):de_end(p.block));
      if(!shift)de_set_anchor(de_caret_pos());de_refresh(1);return 1;
    }
    return 0;
  }
  if(key==VK_ESCAPE) {de_exit();return 1;}
  if(key==VK_TAB) {
    de_cell current=de_cell_at(de.caret.view);size_t count=de_block_count(de.doc);
    size_t i=de.caret.view;
    while(shift ? i>0:i+1<count) {
      i=shift ? i-1:i+1;de_cell next=de_cell_at(i);
      const exr_edit_block *b=de_block_at(de.doc,i);
      if(b->kind==EXR_EDIT_PARAGRAPH &&
        (!current.table ? next.table!=0:!de_same_cell(de.caret.view,i))) {
        if(shift && next.table)while(i && de_same_cell(i,i-1))i--;
        de_set_caret(de_start(i));de_set_anchor(de_caret_pos());de_refresh(1);break;
      }
    }
    return 1;
  }
  if(key==VK_BACK || key==VK_DELETE || key==VK_RETURN) {
    de_edit(key==VK_BACK ? DE_BACKSPACE:key==VK_DELETE ? DE_DELETE:DE_ENTER,NULL,0);return 1;
  }
  if(key==VK_PRIOR || key==VK_NEXT) {de_scroll((float)(key==VK_PRIOR ? -de.height:de.height));return 1;}
  if(key!=VK_LEFT && key!=VK_RIGHT && key!=VK_UP && key!=VK_DOWN && key!=VK_HOME && key!=VK_END)return 0;
  if(!shift && de_selected() && (key==VK_LEFT || key==VK_RIGHT)) {
    de_pos a=de_anchor(),b=de_caret_pos();int cmp=de_compare(a,b);
    de_set_caret(key==VK_LEFT ? (cmp<0 ? a:b):(cmp>0 ? a:b));
  } else if(key==VK_LEFT || key==VK_RIGHT)de_set_caret(de_step(de_caret_pos(),key==VK_LEFT ? -1:1));
  else if(key==VK_UP || key==VK_DOWN)de_vertical(key==VK_UP ? -1:1);
  else de_line_edge(key==VK_END);
  if(!shift)de_set_anchor(de_caret_pos());de_refresh(1);return 1;
}
static int de_key(WPARAM key,int control,int shift) {
  return de_key_modifiers(key,control,shift,0);
}
static void de_character(wchar_t ch) {
  if(ch<32 || ch==127)return; /* Return/Backspace handled exactly once in WM_KEYDOWN. */
  wchar_t wide[2];int length=1;
  if(ch>=0xd800 && ch<=0xdbff) {de.high_surrogate=ch;return;}
  if(ch>=0xdc00 && ch<=0xdfff) {
    if(!de.high_surrogate)return;
    wide[0]=de.high_surrogate;wide[1]=ch;length=2;
  } else wide[0]=ch;
  de.high_surrogate=0;
  char text[8];int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,length,text,sizeof(text),NULL,NULL);
  if(n)de_edit(DE_TYPE,text,(size_t)n);
}
static int de_translate(const MSG *message) {
  if(!de.doc)return 0;
  if((message->message==WM_KEYDOWN || (message->message==WM_SYSKEYDOWN &&
    message->wParam==VK_RETURN && (GetKeyState(VK_CONTROL)&0x8000))) && (message->hwnd==g.window || message->hwnd==g.page ||
    message->hwnd==de_button)) {
    int control=(GetKeyState(VK_CONTROL)&0x8000)!=0,shift=(GetKeyState(VK_SHIFT)&0x8000)!=0;
    if(de_key_modifiers(message->wParam,control,shift,(GetKeyState(VK_MENU)&0x8000)!=0))return 1;
    /* Let TranslateMessage produce WM_CHAR for printable keys. */
    TranslateMessage(message);DispatchMessageW(message);return 1;
  }
  if(message->message==WM_SYSKEYDOWN && message->wParam==VK_LEFT)return 1;
  return 0;
}
static int de_message(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  if(!de.doc)return 0;
  if(message==WM_PAINT) {de_paint(window);return 1;}
  if(message==WM_CHAR) {de_character((wchar_t)wparam);return 1;}
  if(message==WM_KEYDOWN || (message==WM_SYSKEYDOWN && wparam==VK_RETURN &&
    (GetKeyState(VK_CONTROL)&0x8000))) {
    de_key_modifiers(wparam,(GetKeyState(VK_CONTROL)&0x8000)!=0,
      (GetKeyState(VK_SHIFT)&0x8000)!=0,(GetKeyState(VK_MENU)&0x8000)!=0);return 1;
  }
  if(message==WM_TIMER && wparam==DE_TIMER) {de.blink=!de.blink;InvalidateRect(window,NULL,FALSE);return 1;}
  if(message==WM_SIZE) {de.layout_dirty=1;de_refresh(1);return 1;}
  if(message==WM_MOUSEWHEEL) {de_scroll(-(short)HIWORD(wparam)/120.f*51.f*shell_dpi/96.f);return 1;}
  if(message==WM_LBUTTONDOWN || (message==WM_MOUSEMOVE && de.mouse_down)) {
    if(message==WM_LBUTTONDOWN) {
      SetFocus(window);
      if(de_toolbar_click((float)(short)LOWORD(lparam),(float)(short)HIWORD(lparam)))return 1;
      SetCapture(window);de.mouse_down=1;
    }
    int x=(short)LOWORD(lparam),y=(short)HIWORD(lparam);
    if(y<0)de_scroll(-17);else if(y>de.height)de_scroll(17);
    de_set_caret(de_hit((float)x,(float)y));
    if(message==WM_LBUTTONDOWN && !(GetKeyState(VK_SHIFT)&0x8000))de_set_anchor(de_caret_pos());
    de_refresh(1);return 1;
  }
  if(message==WM_LBUTTONUP) {de.mouse_down=0;if(GetCapture()==window)ReleaseCapture();return 1;}
  if(message==WM_CAPTURECHANGED) {de.mouse_down=0;return 1;}
  if(message==WM_SETFOCUS || message==WM_KILLFOCUS) {de.high_surrogate=0;de_refresh(0);return 1;}
  if(message==WM_GETDLGCODE)return 0;
  /* Reading gestures/context menus must not act on the stale reading layout. */
  return message==WM_LBUTTONDBLCLK || message==WM_RBUTTONDOWN || message==WM_RBUTTONUP ||
    message==WM_CONTEXTMENU || message==WM_GESTURE;
}
