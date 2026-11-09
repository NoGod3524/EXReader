/* SPDX-License-Identifier: MIT */
/* Production style store and config mapping: shelf.json settings presets keep
   unrelated keys, reject invalid or corrupt input, and margins map one-to-one. */
static void style_write(const wchar_t *path,const char *text) {
  FILE *f=_wfopen(path,L"wb");assert(f);fwrite(text,1,strlen(text),f);fclose(f);
}
static char *style_slurp(const wchar_t *path) {
  FILE *f=_wfopen(path,L"rb");assert(f);fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);
  char *s=calloc((size_t)n+1,1);assert(s && fread(s,1,(size_t)n,f)==(size_t)n);fclose(f);return s;
}
static int style_same(exr_reader_style a,exr_reader_style b) {
  for(int i=0;i<8;i++)if(*style_value(&a,i)!=*style_value(&b,i))return 0;
  return 1;
}
static void test_style(void) {
  wchar_t temp[HOST_PATH],shelf[HOST_PATH];GetTempPathW(HOST_PATH,temp);
  swprintf(g.data_dir,HOST_PATH,L"%lsexreader-style-check-%lu",temp,(unsigned long)GetCurrentProcessId());
  CreateDirectoryW(g.data_dir,NULL);path_join(shelf,HOST_PATH,g.data_dir,L"shelf.json");
  style_write(shelf,"{\"books\":[{\"id\":7,\"title\":\"紅樓夢\"}],\"settings\":{\"theme\":\"dark\",\"n\":1.5}}");
  exr_reader_style a={14,1.4f,.2f,10,20,30,40,-.01f},b={28,2.1f,1.2f,120,0,60,8,.05f};
  shell_preset_count=0;shell_style=a;shell_font=a.font_size;assert(shell_preset_save(L"阅读 A"));
  shell_style=b;shell_font=b.font_size;assert(shell_preset_save(L"夜读 B"));
  shell_style=a;shell_font=a.font_size;assert(shell_preset_save(L"阅读 A") && shell_preset_count==2);
  shell_preset_count=0;shell_style=exr_reader_style_defaults();shell_style_load();
  assert(shell_preset_count==2 && !strcmp(shell_presets[0].name,"阅读 A") && !strcmp(shell_presets[1].name,"夜读 B"));
  assert(style_same(shell_presets[0].style,a) && style_same(shell_presets[1].style,b) && style_same(shell_style,a));
  char *saved=style_slurp(shelf),*error=NULL;cv_json *root=cv_json_parse(saved,strlen(saved),&error);assert(root);
  const cv_json *books=cv_json_get(root,"books"),*settings=cv_json_get(root,"settings");
  assert(books && books->count==1 && !strcmp(cv_json_get(books->items[0],"title")->string,"紅樓夢"));
  assert(!strcmp(cv_json_get(settings,"theme")->string,"dark") && cv_json_get(settings,"n")->number==1.5);
  cv_json_free(root);free(error);
  /* Out-of-range values and corrupt files: load falls back, save refuses to overwrite. */
  style_write(shelf,"{\"settings\":{\"reader_style\":{\"font_size\":99,\"line_height\":1.75,\"paragraph_spacing\":0.5,"
    "\"top\":40,\"right\":48,\"bottom\":40,\"left\":48,\"letter_spacing\":0}}}");
  shell_preset_count=0;shell_style=b;shell_style_load();assert(style_same(shell_style,exr_reader_style_defaults()));
  style_write(shelf,"{broken");assert(!shell_style_save());
  free(saved);saved=style_slurp(shelf);assert(!strcmp(saved,"{broken"));free(saved);
  /* Physical edges: only the changed edge moves the content rectangle. */
  shell_geometry geometry={1,1000,700,0,96,18,exr_reader_style_defaults()};
  exr_layout_config one=exr_layout_config_defaults(),two=one;shell_apply_config(&one,geometry);
  geometry.width-=72;geometry.style.left=120;shell_apply_config(&two,geometry);
  assert(one.page.width-two.page.width==72 && one.page.height==two.page.height && strstr(two.user_css,"letter-spacing"));
  DeleteFileW(shelf);RemoveDirectoryW(g.data_dir);
  puts("STYLE presets 2/2 round-trip; unrelated shelf keys kept; invalid style rejected; corrupt shelf preserved; left edge only 1/1");
}
