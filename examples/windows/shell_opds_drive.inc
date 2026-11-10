/* SPDX-License-Identifier: MIT */
/* Source-browser acceptance actions. Clicks are the production button
   commands; only the data they act on (a typed address or search word) is
   injected. Asynchronous steps wait through drive_expect_idle. */
static int opds_drive_dump(const char *name) {
  cv_text j={0};
  cv_text_format(&j,"{\"visible\":%d,\"busy\":%ld,\"depth\":%d,\"entries\":%zu,\"has_next\":%d,\"has_search\":%d,",
    opds_visible && IsWindowVisible(opds_view),(long)opds_busy,opds_depth,opds_feed.entry_count,opds_feed.next_url!=NULL,
    opds_search_template[0]!=0 || opds_search_description[0]!=0);
  annot_json_string(&j,"title",opds_feed.title);cv_text_string(&j,",");
  annot_json_string(&j,"url",opds_url);cv_text_string(&j,",");
  annot_json_string(&j,"next_url",opds_feed.next_url);cv_text_string(&j,",");
  annot_json_string(&j,"search_template",opds_search_template[0] ? opds_search_template:NULL);
  char *status=host_utf8(opds_status);
  cv_text_string(&j,",");annot_json_string(&j,"status",status);free(status);
  cv_text_format(&j,",\"last\":{\"op\":%d,\"code\":\"%s\",\"http\":%d,\"win_error\":%lu,\"from_cache\":%d,",
    opds_last_op,onet_name(opds_last_result.code),opds_last_result.http_status,opds_last_result.win_error,opds_last_from_cache);
  annot_json_string(&j,"message",opds_last_result.message);cv_text_string(&j,",");
  annot_json_string(&j,"final_url",opds_last_result.final_url);
  char *path=host_utf8(opds_download_path);
  WIN32_FILE_ATTRIBUTE_DATA info;LARGE_INTEGER bytes={0};
  int exists=GetFileAttributesExW(opds_download_path,GetFileExInfoStandard,&info);
  if(exists){bytes.HighPart=(LONG)info.nFileSizeHigh;bytes.LowPart=info.nFileSizeLow;}
  cv_text_format(&j,"},\"download\":{\"done\":%u,\"cancelled\":%u,\"failed\":%u,\"imports_started\":%u,\"file_exists\":%d,\"file_bytes\":%lld,\"part_exists\":0,",
    opds_downloads_done,opds_downloads_cancelled,opds_downloads_failed,opds_imports_started,exists,(long long)bytes.QuadPart);
  annot_json_string(&j,"path",path);free(path);
  wchar_t part[HOST_PATH+8];swprintf(part,HOST_PATH+8,L"%ls.part",opds_download_path);
  cv_text_format(&j,",\"part_file_present\":%d},\"cache\":{\"hits\":%u,\"misses\":%u,\"ttl_ms\":%llu},\"feeds_loaded\":%u,\"shelf_books\":%zu,\"entries_list\":[",
    GetFileAttributesW(part)!=INVALID_FILE_ATTRIBUTES,onet_cache_hits,onet_cache_misses,(unsigned long long)onet_cache_ttl_ms,opds_feeds_loaded,g.shelf_count);
  for(size_t i=0;i<opds_feed.entry_count && i<60;i++) {
    const exr_opds_entry *e=&opds_feed.entries[i];
    if(i)cv_text_string(&j,",");
    cv_text_string(&j,"{");annot_json_string(&j,"title",e->title);cv_text_string(&j,",");annot_json_string(&j,"author",e->author);
    cv_text_string(&j,",");annot_json_string(&j,"summary",e->summary);cv_text_string(&j,",");annot_json_string(&j,"format",e->format);
    cv_text_string(&j,",");annot_json_string(&j,"download_url",e->download_url);cv_text_string(&j,",");annot_json_string(&j,"detail_url",e->detail_url);
    cv_text_format(&j,",\"size\":%llu}",(unsigned long long)e->size);
  }
  cv_text_string(&j,"],\"shelf\":[");
  for(size_t i=0;i<g.shelf_count;i++) {
    if(i)cv_text_string(&j,",");
    cv_text_string(&j,"{");annot_json_string(&j,"title",g.shelf[i].title);cv_text_string(&j,",");annot_json_string(&j,"author",g.shelf[i].author);
    cv_text_format(&j,",\"id\":%lld}",(long long)g.shelf[i].id);
  }
  cv_text_string(&j,"]}\n");
  int ok=!j.failed && select_drive_write(name,".opds.json",j.data,j.size);cv_text_free(&j);return ok;
}
static int opds_drive(const char *action) {
  const char *a=action+5;
  if(!strcmp(a,"show")){opds_show();return opds_visible && IsWindowVisible(opds_view);}
  if(!opds_visible && strcmp(a,"dump") && strcmp(a,"timeout") && strcmp(a,"cache_ttl") && strcmp(a,"cache_clear"))return 0;
  if(!strcmp(a,"dump"))return opds_drive_dump(drive_args[1]);
  if(!strcmp(a,"timeout")){opds_receive_override=(unsigned)atoi(drive_args[1]);return 1;}
  if(!strcmp(a,"cache_ttl")){onet_cache_ttl_ms=(ULONGLONG)strtoull(drive_args[1],NULL,10);return 1;}
  if(!strcmp(a,"cache_clear")){onet_cache_clear();return 1;}
  if(!strcmp(a,"close")){SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(OPDS_ID_CLOSE,BN_CLICKED),0);return !opds_visible;}
  if(!strcmp(a,"load")) {
    wchar_t *w=host_wide(drive_args[1],strlen(drive_args[1]));
    SetWindowTextW(opds_url_edit,w ? w:L"");free(w);
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(OPDS_ID_GO,BN_CLICKED),0);drive_expect_idle=1;return opds_busy!=0;
  }
  if(!strcmp(a,"search")) {
    wchar_t *w=host_wide(drive_args[1],strlen(drive_args[1]));
    SetWindowTextW(opds_query_edit,w ? w:L"");free(w);
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(OPDS_ID_SEARCH,BN_CLICKED),0);drive_expect_idle=1;return opds_busy!=0;
  }
  if(!strcmp(a,"next") || !strcmp(a,"back") || !strcmp(a,"refresh")) {
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(!strcmp(a,"next") ? OPDS_ID_NEXT:!strcmp(a,"back") ? OPDS_ID_BACK:OPDS_ID_REFRESH,BN_CLICKED),0);
    drive_expect_idle=1;return opds_busy!=0;
  }
  if(!strcmp(a,"open") || !strcmp(a,"download")) { /* opds_open|index  /  opds_download|index[|nowait] */
    int index=atoi(drive_args[1]);
    if(index<0 || (size_t)index>=opds_feed.entry_count)return 0;
    SendMessageW(opds_list,LB_SETCURSEL,(WPARAM)index,0);
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(OPDS_ID_LIST,LBN_SELCHANGE),0);
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(OPDS_ID_ACTION,BN_CLICKED),0);
    if(!opds_busy)return 0;
    if(drive_argc>2 && !strcmp(drive_args[2],"nowait"))return 1;
    drive_expect_idle=1;return 1;
  }
  if(!strcmp(a,"cancel")) {
    SendMessageW(opds_view,WM_COMMAND,MAKEWPARAM(OPDS_ID_CANCEL,BN_CLICKED),0);return opds_cancel!=0;
  }
  if(!strcmp(a,"wait")){drive_expect_idle=1;return 2;}
  if(!strcmp(a,"sleep")){Sleep((DWORD)atoi(drive_args[1]));return 1;}
  return 0;
}
