/* SPDX-License-Identifier: MIT */
/* --drive inputs for reading-style and footnote acceptance. Each action goes
   through the production control (EDIT/BUTTON/COMBOBOX) or posts real mouse and
   key messages through the message loop; telemetry only reads state. */
static int style_drive_dump(const char *name) {
  cv_text j={0};RECT page={0},client={0};compute_view();
  if(g.page)GetClientRect(g.page,&page);
  GetClientRect(g.window,&client);
  int minx=-1,maxx=-1,miny=-1,maxy=-1,bw=g.view.bw,bh=g.view.bh;
  for(int y=0;g.frame.dib && y<bh;y++)for(int x=0;x<bw;x++) {
    uint32_t px=g.frame.dib[(size_t)y*bw+x]&0xffffff,bg=g.frame.dib[0]&0xffffff;
    if(px==bg)continue;
    if(minx<0 || x<minx)minx=x;
    if(x>maxx)maxx=x;
    if(miny<0)miny=y;
    maxy=y;
  }
  cv_text_format(&j,"{\"style\":{");
  shell_style.font_size=shell_font;
  for(int i=0;i<8;i++)cv_text_format(&j,"%s\"%s\":%.9g",i?",":"",style_keys[i],(double)*style_value(&shell_style,i));
  cv_text_format(&j,"},\"fields\":[");
  for(int i=0;i<8;i++) {
    wchar_t text[32]={0};char *utf8;if(style_edits[i])GetWindowTextW(style_edits[i],text,32);
    utf8=host_utf8(text);cv_text_format(&j,"%s",i?",":"");cv_text_json(&j,utf8?utf8:"");free(utf8);
  }
  cv_text_format(&j,"],\"presets\":[");
  for(int i=0;i<shell_preset_count;i++){if(i)cv_text_string(&j,",");cv_text_json(&j,shell_presets[i].name);}
  cv_text_format(&j,"],\"dpi\":%u,\"client\":[%ld,%ld],\"page_client\":[%ld,%ld],\"config\":[%.6f,%.6f,%.6f,%.6f,%.6f],",
    shell_dpi,client.right,client.bottom,page.right,page.bottom,(double)g.session.config.page.width,(double)g.session.config.page.height,
    (double)g.session.config.page.font_size,(double)g.session.config.page.line_height,(double)g.session.config.page.paragraph_spacing);
  /* Content rectangle in page-HWND pixels, and the four gaps to the page edges
     (bottom gap includes the fixed page-number strip). Ink box from the frame. */
  cv_text_format(&j,"\"view\":[%d,%d,%d,%d],\"gaps\":{\"left\":%d,\"top\":%d,\"right\":%ld,\"bottom\":%ld},",
    g.view.dx,g.view.dy,bw,bh,g.view.dx,g.view.dy,page.right-g.view.dx-bw,page.bottom-g.view.dy-bh);
  cv_text_format(&j,"\"ink\":[%d,%d,%d,%d],\"ink_gaps\":{\"left\":%d,\"right\":%ld},",
    minx,miny,maxx,maxy,minx<0?-1:g.view.dx+minx,maxx<0?-1:page.right-(g.view.dx+maxx+1));
  cv_text_format(&j,"\"builds\":%lu,\"epoch\":%lu,\"frame_epoch\":%lu,\"valid\":%d,\"glyphs\":%zu,\"mode\":%d,\"part\":%zu,\"page\":%zu,\"range\":[%zu,%zu],",
    shell_pager_builds,shell_epoch,g.frame.shell_epoch,g.frame.valid,g.frame.glyph_count,g.frame.writing_mode,
    g.frame.part,g.frame.page,g.frame.range_start,g.frame.range_end);
  cv_text_string(&j,"\"panel_open\":");cv_text_format(&j,"%d}\n",shell_panel_open);
  int ok=!j.failed && select_drive_write(name,".style.json",j.data,j.size);cv_text_free(&j);return ok;
}
static int footnote_drive_refs(const char *name) {
  const exr_footnote *notes;const exr_footnote_reference *refs;size_t n,r;cv_text j={0};
  exr_publication *p=select_publication();
  if(!p || exr_publication_footnotes(p,&notes,&n,&refs,&r,NULL)!=EXR_OK)return 0;
  cv_text_string(&j,"{\"footnotes\":[");
  for(size_t i=0;i<n;i++) {
    cv_text_format(&j,"%s{\"id\":",i?",":"");cv_text_json(&j,notes[i].id);cv_text_string(&j,",\"label\":");
    cv_text_json(&j,notes[i].label);cv_text_format(&j,",\"target_part\":%zu,\"target_offset\":%zu,\"text\":",notes[i].target_part,notes[i].target_offset);
    cv_text_json(&j,notes[i].text);cv_text_string(&j,"}");
  }
  cv_text_string(&j,"],\"references\":[");
  for(size_t i=0;i<r;i++)cv_text_format(&j,"%s[%zu,%zu,%zu,%zu]",i?",":"",refs[i].part,refs[i].start,refs[i].end,refs[i].footnote);
  cv_text_string(&j,"]}\n");int ok=!j.failed && select_drive_write(name,".footnotes.json",j.data,j.size);cv_text_free(&j);return ok;
}
/* Click the visible marker of reference i, as a posted (queued) mouse press. */
static int footnote_drive_click(size_t index) {
  const exr_footnote *notes;const exr_footnote_reference *refs;size_t n,r;
  exr_publication *p=select_publication();
  if(!p || exr_publication_footnotes(p,&notes,&n,&refs,&r,NULL)!=EXR_OK || index>=r || refs[index].part!=g.frame.part)return 0;
  compute_view();
  for(size_t i=0;i<g.frame.shell_line_count;i++) {
    const exr_line *line=&g.frame.shell_lines[i];
    for(size_t k=line->glyph_start;k<line->glyph_start+line->glyph_count;k++) {
      const exr_glyph *q=&g.frame.glyphs[k];
      if(q->cluster_start<refs[index].start || q->cluster_start>=refs[index].end || q->flags&(EXR_GLYPH_HIDDEN|EXR_GLYPH_GENERATED))continue;
      float x=q->x+q->advance*.5f,y=line->y+line->height*.5f;
      if(q->flags&EXR_GLYPH_VERTICAL){x=line->x+line->width*.5f;y=q->baseline+q->advance*.5f;}
      LPARAM at=MAKELPARAM((int)lroundf(g.view.dx+x*g.view.scale),(int)lroundf(g.view.dy+y*g.view.scale));
      PostMessageW(g.page,WM_LBUTTONDOWN,MK_LBUTTON,at);PostMessageW(g.page,WM_LBUTTONUP,0,at);return 1;
    }
  }
  return 0;
}
static int footnote_drive_dump(const char *name) {
  cv_text j={0};RECT box={0};int visible=footnote_panel && IsWindowVisible(footnote_panel);
  wchar_t *text=NULL;char *utf8=NULL,*title=host_utf8(footnote_title);
  if(visible) {
    int length=GetWindowTextLengthW(footnote_text);text=calloc((size_t)length+1,sizeof(*text));
    if(text){GetWindowTextW(footnote_text,text,length+1);utf8=host_utf8(text);}
    GetWindowRect(footnote_panel,&box);MapWindowPoints(NULL,g.window,(POINT *)&box,2);
    box.left+=shell_px(SHELL_SHADOW_PAD,shell_dpi);box.right-=shell_px(SHELL_SHADOW_PAD,shell_dpi);
    box.top+=shell_px(SHELL_SHADOW_TOP,shell_dpi);box.bottom-=shell_px(SHELL_SHADOW_PAD,shell_dpi);
  }
  RECT client;GetClientRect(g.window,&client);
  SCROLLINFO scroll={sizeof(scroll),SIF_ALL,0,0,0,0,0};
  if(visible)GetScrollInfo(footnote_text,SB_VERT,&scroll);
  cv_text_format(&j,"{\"visible\":%d,\"index\":%lld,\"box\":[%ld,%ld,%ld,%ld],\"client\":[%ld,%ld],\"dpi\":%u,"
    "\"scroll\":[%d,%d,%u],\"mode\":%d,\"part\":%zu,\"page\":%zu,\"range\":[%zu,%zu],\"title\":",
    visible,footnote_index==SIZE_MAX?-1LL:(long long)footnote_index,box.left,box.top,box.right,box.bottom,
    client.right,client.bottom,shell_dpi,scroll.nMin,scroll.nMax,scroll.nPage,g.frame.writing_mode,
    g.frame.part,g.frame.page,g.frame.range_start,g.frame.range_end);
  cv_text_json(&j,title?title:"");cv_text_string(&j,",\"text\":");cv_text_json(&j,utf8?utf8:"");cv_text_string(&j,"}\n");
  int ok=!j.failed && select_drive_write(name,".popup.json",j.data,j.size);
  cv_text_free(&j);free(text);free(utf8);free(title);return ok;
}
/* Returns 1 when the step waits for reflow, 0 when it already finished. */
static int style_drive(const char *action) {
  if(!strcmp(action,"style_field")) {
    int i=atoi(drive_args[1]);if(i<0 || i>=8 || !style_edits[i]){drive_step_finish(0,"no such field");return 0;}
    wchar_t *value=host_wide(drive_args[2],strlen(drive_args[2]));if(!value){drive_step_finish(0,"value");return 0;}
    SetWindowTextW(style_edits[i],value);free(value);
    SendMessageW(shell_panel,WM_COMMAND,MAKEWPARAM(IDC_STYLE_BASE+3*i+2,EN_KILLFOCUS),(LPARAM)style_edits[i]);
    drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"style_step")) {
    int i=atoi(drive_args[1]),plus=!strcmp(drive_args[2],"plus");
    if(i<0 || i>=8){drive_step_finish(0,"no such field");return 0;}
    SendMessageW(style_buttons[2*i+plus],BM_CLICK,0,0);drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"style_reset")){SendMessageW(style_reset,BM_CLICK,0,0);drive_expect_idle=1;return 1;}
  if(!strcmp(action,"style_save")) {
    wchar_t *name=host_wide(drive_args[1],strlen(drive_args[1]));if(!name){drive_step_finish(0,"name");return 0;}
    int before=shell_preset_count;SetWindowTextW(style_preset,name);free(name);SendMessageW(style_save,BM_CLICK,0,0);
    drive_step_finish(shell_preset_count>=before && shell_preset_count>0,"preset saved");return 0;
  }
  if(!strcmp(action,"style_pick")) {
    int i=atoi(drive_args[1]);if(i<0 || i>=shell_preset_count){drive_step_finish(0,"no such preset");return 0;}
    shell_preset_pick(i);
    drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"style_dump")){drive_step_finish(style_drive_dump(drive_args[1]),"style captured");return 0;}
  if(!strcmp(action,"footnote_refs")){drive_step_finish(footnote_drive_refs(drive_args[1]),"footnotes listed");return 0;}
  if(!strcmp(action,"footnote_click")) {
    if(!footnote_drive_click((size_t)strtoull(drive_args[1],NULL,10))){drive_step_finish(0,"reference not on page");return 0;}
    drive_expect_idle=1;return 1; /* yield: the posted press runs through the message loop */
  }
  if(!strcmp(action,"footnote_dump")){drive_step_finish(footnote_drive_dump(drive_args[1]),"popup captured");return 0;}
  if(!strcmp(action,"footnote_key")) {
    HWND focus=GetFocus();PostMessageW(focus?focus:footnote_text,WM_KEYDOWN,VK_ESCAPE,0);
    drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"footnote_outside")) {
    /* A press on the page's left margin: outside the popup and every marker. */
    LPARAM at=MAKELPARAM(max(1,g.view.dx/2),g.view.dy+4);
    PostMessageW(g.page,WM_LBUTTONDOWN,MK_LBUTTON,at);PostMessageW(g.page,WM_LBUTTONUP,0,at);
    drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"footnote_scroll")) {
    SendMessageW(footnote_text,WM_VSCROLL,SB_BOTTOM,0);drive_step_finish(1,"popup scrolled");return 0;
  }
  drive_step_finish(0,"unknown style action");return 0;
}
