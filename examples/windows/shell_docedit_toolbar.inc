/* SPDX-License-Identifier: MIT */
/* Toolbar and keyboard commands share these model transactions. */
enum { DE_BOLD,DE_ITALIC,DE_SMALLER,DE_SIZE,DE_LARGER,DE_COLOR,
  DE_LEFT,DE_CENTER,DE_RIGHT,DE_JUSTIFY,DE_TEXT_BUTTONS,
  DE_ADD_ROW=DE_TEXT_BUTTONS,DE_REMOVE_ROW,DE_WIDER,DE_NARROWER,DE_REMOVE_TABLE,DE_BUTTONS };
static const uint32_t de_colors[]={0x000000,0x808080,0xff0000,0x008000,0x0000ff,0xff8000,0x800080,0xffffff};
static const wchar_t *de_color_names[]={L"黑",L"灰",L"红",L"绿",L"蓝",L"橙",L"紫",L"白"};
static void de_merge_props(exr_edit_run_props *to,const exr_edit_run_props *from) {
  if((from->present&EXR_EDIT_FONT) && from->font[0])memcpy(to->font,from->font,sizeof(to->font));
  if((from->present&EXR_EDIT_SIZE) && from->size_half_points)to->size_half_points=from->size_half_points;
  if(from->present&EXR_EDIT_BOLD)to->bold=from->bold;
  if(from->present&EXR_EDIT_ITALIC)to->italic=from->italic;
  if(from->present&EXR_EDIT_COLOR)to->color_rgb=from->color_rgb;
  to->present|=from->present;
}
static const char *de_local(const char *name) {
  const char *colon=strrchr(name,':');return colon ? colon+1:name;
}
static const char *de_attribute(const char **attrs,const char *name) {
  for(size_t i=0;attrs[i];i+=2)if(!strcmp(de_local(attrs[i]),name))return attrs[i+1];
  return "";
}
typedef struct {
  int depth,run_depth,defaults,failed,collect;
  size_t style;
  char reference[128];
} de_style_parse;
static void de_style_start(void *context,const char *name,const char **attrs) {
  de_style_parse *parse=context;name=de_local(name);parse->depth++;
  if((!strcmp(name,"pStyle") || !strcmp(name,"rStyle")) && parse->depth==3)
    snprintf(parse->reference,sizeof(parse->reference),"%s",de_attribute(attrs,"val"));
  if(!parse->collect)return;
  if(!strcmp(name,"docDefaults"))parse->defaults=1;
  if(!strcmp(name,"style")) {
    de_style *styles=realloc(de.styles,(de.style_count+1)*sizeof(*styles));
    if(!styles) {parse->failed=1;return;}
    de.styles=styles;parse->style=de.style_count++;
    de_style *style=&styles[parse->style];memset(style,0,sizeof(*style));
    snprintf(style->id,sizeof(style->id),"%s",de_attribute(attrs,"styleId"));
    if(!strcmp(de_attribute(attrs,"type"),"paragraph") && !strcmp(de_attribute(attrs,"default"),"1"))
      snprintf(de.default_style,sizeof(de.default_style),"%s",style->id);
  }
  if(!strcmp(name,"basedOn") && parse->style<de.style_count)
    snprintf(de.styles[parse->style].base,128,"%s",de_attribute(attrs,"val"));
  if(!strcmp(name,"rPr"))parse->run_depth=parse->depth;
  if(!parse->run_depth || parse->depth!=parse->run_depth+1)return;
  exr_edit_run_props *props=parse->style<de.style_count ? &de.styles[parse->style].props:
    parse->defaults ? &de.default_props:NULL;
  if(!props)return;
  const char *val=de_attribute(attrs,"val");
  if(!strcmp(name,"rFonts")) {
    const char *font=de_attribute(attrs,"ascii");
    if(!*font)font=de_attribute(attrs,"hAnsi");if(!*font)font=de_attribute(attrs,"eastAsia");
    if(*font) {props->present|=EXR_EDIT_FONT;snprintf(props->font,128,"%s",font);}
  } else if(!strcmp(name,"sz")) {
    unsigned long size=strtoul(val,NULL,10);
    if(size && size<=3276) {props->present|=EXR_EDIT_SIZE;props->size_half_points=(uint32_t)size;}
  } else if(!strcmp(name,"b") || !strcmp(name,"i")) {
    unsigned enabled=strcmp(val,"0") && strcmp(val,"false") && strcmp(val,"off");
    if(!strcmp(name,"b")) {props->present|=EXR_EDIT_BOLD;props->bold=enabled;}
    else {props->present|=EXR_EDIT_ITALIC;props->italic=enabled;}
  } else if(!strcmp(name,"color") && strlen(val)==6) {
    char *end=NULL;unsigned long color=strtoul(val,&end,16);
    if(end==val+6) {props->present|=EXR_EDIT_COLOR;props->color_rgb=(uint32_t)color;}
  }
}
static void de_style_end(void *context,const char *name) {
  de_style_parse *parse=context;name=de_local(name);
  if(parse->run_depth==parse->depth)parse->run_depth=0;
  if(!strcmp(name,"style"))parse->style=SIZE_MAX;
  if(!strcmp(name,"docDefaults"))parse->defaults=0;
  parse->depth--;
}
static int de_parse_style_xml(const void *xml,size_t size,char reference[128]) {
  if(!xml || !size || size>INT_MAX)return 0;
  void *parser=XML_ParserCreate(NULL);if(!parser)return 0;
  de_style_parse parse={0};parse.style=SIZE_MAX;parse.collect=reference==NULL;
  XML_SetUserData(parser,&parse);XML_SetElementHandler(parser,de_style_start,de_style_end);
  int ok=XML_Parse(parser,xml,(int)size,1)==1 && !parse.failed;
  XML_ParserFree(parser);if(reference)memcpy(reference,parse.reference,128);return ok;
}
static void de_load_styles(void) {
  if(de.styles_loaded)return;
  de.styles_loaded=1;memset(&de.default_props,0,sizeof(de.default_props));de.default_style[0]=0;
  size_t count=0;const exr_edit_part *parts=exr_edit_parts(de.doc,&count);
  for(size_t i=0;i<count;i++)if(!strcmp(parts[i].name,"word/styles.xml")) {
    if(!de_parse_style_xml(parts[i].data,parts[i].size,NULL)) {
      free(de.styles);de.styles=NULL;de.style_count=0;
      memset(&de.default_props,0,sizeof(de.default_props));de.default_style[0]=0;
    }
    break;
  }
}
static void de_inherit_style(exr_edit_run_props *props,const char *id) {
  exr_edit_run_props chain={0};
  for(size_t depth=0;*id && depth<de.style_count;depth++) {
    size_t i=0;while(i<de.style_count && strcmp(de.styles[i].id,id))i++;
    if(i==de.style_count)break;
    exr_edit_run_props parent=de.styles[i].props;de_merge_props(&parent,&chain);chain=parent;
    id=de.styles[i].base; /* Bound cycles without recursive stack growth. */
  }
  de_merge_props(props,&chain);
}
static exr_edit_run_props de_resolve_props(const exr_edit_block *block,const exr_edit_run *run) {
  de_load_styles();exr_edit_run_props props={0};props.size_half_points=24;
  de_merge_props(&props,&de.default_props);
  char style[128]={0};
  if(block)de_parse_style_xml(block->opaque_xml,block->opaque_size,style);
  de_inherit_style(&props,*style ? style:de.default_style);
  if(run) {
    style[0]=0;de_parse_style_xml(run->opaque_xml,run->opaque_size,style);
    de_inherit_style(&props,style);de_merge_props(&props,&run->props);
  }
  return props;
}
static exr_edit_run_props de_current_props(void) {
  de_pos p=de_normalize(de_caret());const exr_edit_block *b=de_block_at(de.doc,p.block);
  const exr_edit_run *r=b && p.run<b->run_count && b->runs[p.run].kind==EXR_EDIT_TEXT ? &b->runs[p.run]:NULL;
  exr_edit_run_props props=de_resolve_props(b,r);
  de_merge_props(&props,&de.pending_props);return props;
}
static int de_apply_run(const exr_edit_run_props *change) {
  if(!de_selected()) {
    de_merge_props(&de.pending_props,change);de_refresh(0);return 1;
  }
  de_pos a=de_normalize(de_anchor()),b=de_normalize(de_caret());
  if(de_compare(a,b)>0) {de_pos temp=a;a=b;b=temp;}
  exr_edit_tx *tx=exr_edit_begin(de.doc);exr_status status=tx ? EXR_OK:EXR_MEMORY;
  for(size_t i=a.block;tx && status==EXR_OK && i<=b.block;i++) {
    const exr_edit_block *block=de_block_at(de.doc,i);
    if(block->kind!=EXR_EDIT_PARAGRAPH)continue;
    size_t count=block->run_count;exr_edit_id id=block->id;
    for(size_t j=0;j<count && status==EXR_OK;j++) {
      block=exr_edit_find_block(de.doc,id);const exr_edit_run *r=&block->runs[j];
      if(r->kind!=EXR_EDIT_TEXT || !r->text_size)continue;
      de_pos start={i,j,0},end={i,j,r->text_size};
      if(de_compare(a,end)>=0 || de_compare(b,start)<=0)continue;
      /* Public API has no split-run: a partial selection formats the whole run. */
      exr_edit_run_props props=r->props;de_merge_props(&props,change);
      status=exr_edit_set_run_props(de.doc,id,j,&props);
    }
  }
  if(tx) {if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);}
  if(status!=EXR_OK) {set_status(L"无法应用文字格式；此次修改已撤回。");return 0;}
  memset(&de.pending_props,0,sizeof(de.pending_props));
  de.dirty=1;de.layout_dirty=1;de_refresh(1);return 1;
}
static int de_command(int command,uint32_t color) {
  if(!de.doc)return 0;
  if(command>=DE_ADD_ROW) {
    de_cell cell=de_cell_at(de.caret_block);if(!cell.table)return 0;
    const exr_edit_block *owner=exr_edit_find_block(de.doc,cell.table);
    const exr_edit_table *t=owner->table;size_t target=de.caret_block;
    /* Keep the caret on a surviving ID when rows move around it. */
    exr_edit_id caret_id=de_block_at(de.doc,target)->id;
    exr_edit_tx *tx=exr_edit_begin(de.doc);exr_status status=tx ? EXR_OK:EXR_MEMORY;
    if(tx) {
      if(command==DE_ADD_ROW)status=exr_edit_table_insert_row(de.doc,cell.table,cell.row);
      else if(command==DE_REMOVE_ROW)status=exr_edit_table_delete_row(de.doc,cell.table,cell.row);
      else if(command==DE_REMOVE_TABLE)status=exr_edit_delete_table(de.doc,cell.table);
      else {
        int32_t old=t->column_widths ? t->column_widths[cell.col]:t->width_twips/(int32_t)t->column_count;
        int64_t value=((int64_t)(old>0 ? old:2400)*(command==DE_WIDER ? 105:100)+
          (command==DE_WIDER ? 50:52))/(command==DE_WIDER ? 100:105);
        status=value>INT32_MAX ? EXR_ARGUMENT:exr_edit_table_set_column_width(de.doc,tx,cell.table,cell.col,(int32_t)value);
      }
      if(status==EXR_OK && !de_block_count(de.doc)) {
        exr_edit_id id=0;status=exr_edit_insert_paragraph(de.doc,0,NULL,0,NULL,&id);
      }
      if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);
    }
    if(status!=EXR_OK) {set_status(L"无法修改此表格；此次修改已撤回。");return 0;}
    size_t count=de_block_count(de.doc),i=0;
    for(;i<count;i++)if(de_block_at(de.doc,i)->id==caret_id)break;
    if(i==count) {
      if(target>=count)target=count ? count-1:0;i=target;
      while(i && de_block_at(de.doc,i)->kind!=EXR_EDIT_PARAGRAPH)i--;
    }
    de_set_caret(de_start(i));de_set_anchor(de_caret());
    de.dirty=1;de.layout_dirty=1;de_refresh(1);return 1;
  }
  if(command>=DE_LEFT && command<=DE_JUSTIFY) {
    const exr_edit_block *b=de_block_at(de.doc,de.caret_block);
    if(!b || b->kind!=EXR_EDIT_PARAGRAPH)return 0;
    exr_edit_para_props props=b->props;props.present|=EXR_EDIT_ALIGN;
    props.alignment=(exr_edit_alignment)(command-DE_LEFT);
    exr_status status=exr_edit_set_paragraph_props(de.doc,b->id,&props);
    if(status!=EXR_OK) {set_status(L"无法应用段落对齐。");return 0;}
    de.dirty=1;de.layout_dirty=1;de_refresh(1);return 1;
  }
  exr_edit_run_props current=de_current_props(),change={0};
  if(command==DE_BOLD) {change.present=EXR_EDIT_BOLD;change.bold=!current.bold;}
  else if(command==DE_ITALIC) {change.present=EXR_EDIT_ITALIC;change.italic=!current.italic;}
  else if(command==DE_SMALLER || command==DE_LARGER) {
    change.present=EXR_EDIT_SIZE;
    uint32_t size=current.size_half_points ? current.size_half_points:24;
    change.size_half_points=command==DE_LARGER ? (size<3274 ? size+2:3276):(size>3 ? size-2:2);
  } else if(command==DE_COLOR) {change.present=EXR_EDIT_COLOR;change.color_rgb=color;}
  else return 0;
  return de_apply_run(&change);
}
static float de_toolbar_height(void) {return (float)shell_px(de_cell_at(de.caret_block).table ? 88:44,shell_dpi);}
static RECT de_toolbar_box(int index) {
  if(index>=DE_TEXT_BUTTONS) {
    int x=8+(index-DE_TEXT_BUTTONS)*76;
    RECT box={shell_px(x,shell_dpi),shell_px(48,shell_dpi),shell_px(x+74,shell_dpi),shell_px(84,shell_dpi)};return box;
  }
  const int widths[]={34,34,56,48,56,64,40,52,40,52};
  int x=8;for(int i=0;i<index;i++)x+=widths[i]+2;
  RECT box={shell_px(x,shell_dpi),shell_px(4,shell_dpi),
    shell_px(x+widths[index],shell_dpi),shell_px(40,shell_dpi)};return box;
}
static RECT de_color_box(int index) {
  RECT box=de_toolbar_box(DE_COLOR);int size=shell_px(36,shell_dpi);
  box.left+=index*size;box.right=box.left+size;
  box.top=(LONG)de_toolbar_height();box.bottom=box.top+size;return box;
}
static HRESULT de_toolbar_paint(HDC dc) {
  const wchar_t *labels[]={L"B",L"I",L"字号−",L"",L"字号+",L"颜色▾",L"左",L"居中",L"右",L"两端",
    L"+行",L"−行",L"列宽+",L"列宽−",L"删表"};
  exr_edit_run_props props=de_current_props();wchar_t size[32];
  swprintf(size,32,L"%g",props.size_half_points/2.0);labels[DE_SIZE]=size;
  const exr_edit_block *b=de_block_at(de.doc,de.caret_block);
  int align=b && (b->props.present&EXR_EDIT_ALIGN) ? b->props.alignment:EXR_EDIT_LEFT;
  HRESULT hr=S_OK;
  int buttons=de_cell_at(de.caret_block).table ? DE_BUTTONS:DE_TEXT_BUTTONS;
  for(int i=0;i<buttons && SUCCEEDED(hr);i++) {
    int selected=(i==DE_BOLD && props.bold) || (i==DE_ITALIC && props.italic) ||
      (i>=DE_LEFT && i<DE_TEXT_BUTTONS && i-DE_LEFT==align) || (i==DE_COLOR && de.color_panel);
    shell_d2d_look look={SHELL_CONTROL_GHOST,selected ? SHELL_STATE_SELECTED:0,shell_colors->layer_page,0,0};
    RECT box=de_toolbar_box(i);hr=shell_d2d_control(host_shell,dc,&box,labels[i],shell_is_dark(),&look);
  }
  for(int i=0;de.color_panel && i<8 && SUCCEEDED(hr);i++) {
    RECT box=de_color_box(i);
    shell_d2d_look look={SHELL_CONTROL_GHOST,0,de_colors[i],0,0};
    hr=shell_d2d_control(host_shell,dc,&box,de_color_names[i],shell_is_dark(),&look);
  }
  return hr;
}
static int de_toolbar_click(float x,float y) {
  POINT point={(LONG)x,(LONG)y};int was_panel=de.color_panel;
  if(de.color_panel) {
    de.color_panel=0;
    for(int i=0;i<8;i++) {RECT box=de_color_box(i);if(PtInRect(&box,point)) {
      de_command(DE_COLOR,de_colors[i]);de_refresh(0);return 1;
    }}
    de_refresh(0);
  }
  if(y>=de_toolbar_height())return 0;
  int buttons=de_cell_at(de.caret_block).table ? DE_BUTTONS:DE_TEXT_BUTTONS;
  for(int i=0;i<buttons;i++) {RECT box=de_toolbar_box(i);if(PtInRect(&box,point)) {
    if(i==DE_COLOR) {de.color_panel=!was_panel;de_refresh(0);}
    else de_command(i,0);
    return 1;
  }}
  return 1;
}
