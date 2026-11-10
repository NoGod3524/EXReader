/* SPDX-License-Identifier: MIT */
/* Keep unrelated shelf/settings keys. Replace atomically after a complete write. */
typedef struct { char name[128];exr_reader_style style; } shell_style_preset;
static shell_style_preset shell_presets[16];
static int shell_preset_count;
static const char *style_keys[]={"font_size","line_height","paragraph_spacing","top","right","bottom","left","letter_spacing"};
static float *style_value(exr_reader_style *s,int i) {
  switch(i) {
    case 0:return &s->font_size;case 1:return &s->line_height;case 2:return &s->paragraph_spacing;
    case 3:return &s->top;case 4:return &s->right;case 5:return &s->bottom;case 6:return &s->left;
    default:return &s->letter_spacing;
  }
}
static int style_valid(exr_reader_style s) {
  exr_layout_config c=exr_layout_config_defaults();char css[1024];
  return exr_reader_style_config(&s,1024,1024,1,&c,css,NULL)==EXR_OK;
}
static int style_read(const cv_json *o,exr_reader_style *s) {
  if(!o || o->type!=CV_JSON_OBJECT) return 0;
  for(int i=0;i<8;i++) {
    const cv_json *v=cv_json_get(o,style_keys[i]);if(!v || v->type!=CV_JSON_NUMBER)return 0;
    *style_value(s,i)=(float)v->number;
  }
  return style_valid(*s);
}
static void style_json(cv_text *out,exr_reader_style s) {
  cv_text_string(out,"{");
  for(int i=0;i<8;i++) cv_text_format(out,"%s\"%s\":%.9g",i?",":"",style_keys[i],(double)*style_value(&s,i));
  cv_text_string(out,"}");
}
static void style_json_copy(cv_text *out,const cv_json *v) {
  if(!v) {cv_text_string(out,"null");return;}
  switch(v->type) {
    case CV_JSON_NULL:cv_text_string(out,"null");break;
    case CV_JSON_BOOL:cv_text_string(out,v->boolean?"true":"false");break;
    case CV_JSON_NUMBER:cv_text_format(out,"%.17g",v->number);break;
    case CV_JSON_STRING:cv_text_json(out,v->string);break;
    default:
      cv_text_string(out,v->type==CV_JSON_ARRAY?"[":"{");
      for(size_t i=0;i<v->count;i++) {
        if(i)cv_text_string(out,",");
        if(v->type==CV_JSON_OBJECT){cv_text_json(out,v->keys[i]);cv_text_string(out,":");}
        style_json_copy(out,v->items[i]);
      }
      cv_text_string(out,v->type==CV_JSON_ARRAY?"]":"}");break;
  }
}
static void shell_shelf_path(wchar_t path[HOST_PATH]) {
  DWORD n=GetEnvironmentVariableW(L"EXREADER_SHELF_PATH",path,HOST_PATH);
  if(!n || n>=HOST_PATH)path_join(path,HOST_PATH,g.data_dir,L"shelf.json");
}
static cv_json *style_shelf_read(int *ok) {
  wchar_t path[HOST_PATH];shell_shelf_path(path);
  FILE *f=_wfopen(path,L"rb");*ok=0;
  if(!f) {*ok=GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES;return NULL;}
  if(fseek(f,0,SEEK_END)!=0){fclose(f);return NULL;}
  long n=ftell(f);if(n<0 || n>16*1024*1024){fclose(f);return NULL;}rewind(f);
  char *bytes=malloc((size_t)n+1),*error=NULL;
  if(!bytes){fclose(f);return NULL;}
  size_t got=fread(bytes,1,(size_t)n,f);int closed=fclose(f);bytes[got]=0;
  cv_json *root=got==(size_t)n && !closed ? cv_json_parse(bytes,got,&error):NULL;
  free(bytes);free(error);
  if(root && root->type==CV_JSON_OBJECT) *ok=1;
  else {cv_json_free(root);root=NULL;}
  return root;
}
static void shell_style_load(void) {
  int ok;cv_json *root=style_shelf_read(&ok);
  const cv_json *settings=cv_json_get(root,"settings"),*list=cv_json_get(settings,"style_presets");
  exr_reader_style s;shell_preset_count=0;
  if(style_read(cv_json_get(settings,"reader_style"),&s)){shell_style=s;shell_font=s.font_size;}
  else {shell_style=exr_reader_style_defaults();shell_font=shell_style.font_size;}
  if(list && list->type==CV_JSON_ARRAY && list->count<=16) for(size_t i=0;i<list->count;i++) {
    const cv_json *name=cv_json_get(list->items[i],"name");
    if(name && name->type==CV_JSON_STRING && strlen(name->string)<128 &&
       style_read(cv_json_get(list->items[i],"style"),&s)) {
      shell_style_preset *p=&shell_presets[shell_preset_count++];strcpy(p->name,name->string);p->style=s;
    }
  }
  cv_json_free(root);
}
static int shell_style_save(void) {
  int ok;cv_json *root=style_shelf_read(&ok);if(!ok)return 0;
  const cv_json *settings=cv_json_get(root,"settings");cv_text out={0};int comma=0;
  if(settings && settings->type!=CV_JSON_OBJECT){cv_json_free(root);return 0;}
  cv_text_string(&out,"{");
  if(root)for(size_t i=0;i<root->count;i++)if(strcmp(root->keys[i],"settings")) {
    if(comma++){cv_text_string(&out,",");}
    cv_text_json(&out,root->keys[i]);cv_text_string(&out,":");style_json_copy(&out,root->items[i]);
  }
  if(comma){cv_text_string(&out,",");}
  cv_text_string(&out,"\"settings\":{");
  if(settings)for(size_t i=0;i<settings->count;i++)if(strcmp(settings->keys[i],"reader_style") && strcmp(settings->keys[i],"style_presets")) {
    cv_text_json(&out,settings->keys[i]);cv_text_string(&out,":");style_json_copy(&out,settings->items[i]);cv_text_string(&out,",");
  }
  shell_style.font_size=shell_font;cv_text_string(&out,"\"reader_style\":");style_json(&out,shell_style);
  cv_text_string(&out,",\"style_presets\":[");
  for(int i=0;i<shell_preset_count;i++) {
    if(i){cv_text_string(&out,",");}
    cv_text_string(&out,"{\"name\":");cv_text_json(&out,shell_presets[i].name);
    cv_text_string(&out,",\"style\":");style_json(&out,shell_presets[i].style);cv_text_string(&out,"}");
  }
  cv_text_string(&out,"]}}\n");cv_json_free(root);
  wchar_t path[HOST_PATH],temp[HOST_PATH];shell_shelf_path(path);
  /* A page turn saves the same settings. Avoid an atomic write-through when
     the complete serialized file is already identical. */
  FILE *existing=out.failed?NULL:_wfopen(path,L"rb");
  if(existing) {
    unsigned char bytes[1024];size_t offset=0;int same=1;
    while(offset<out.size) {
      size_t count=out.size-offset;if(count>sizeof(bytes))count=sizeof(bytes);
      if(fread(bytes,1,count,existing)!=count || memcmp(bytes,out.data+offset,count)) {same=0;break;}
      offset+=count;
    }
    same=same && fgetc(existing)==EOF && !ferror(existing);
    if(fclose(existing)!=0)same=0;
    if(same){cv_text_free(&out);return 1;}
  }
  swprintf(temp,HOST_PATH,L"%ls.tmp",path);FILE *f=out.failed?NULL:_wfopen(temp,L"wb");ok=0;
  if(f){ok=fwrite(out.data,1,out.size,f)==out.size;if(fclose(f)!=0)ok=0;}
  if(ok)ok=MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
  cv_text_free(&out);return ok;
}
