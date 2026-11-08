/* SPDX-License-Identifier: MIT */
/* Native acceptance hooks: pointer/key events are provided by selection drive. */
static int dict_drive(const char *action) {
  if(!strcmp(action,"dict_add")) {
    wchar_t *path=host_wide(drive_args[1],strlen(drive_args[1]));int ok=path && dict_directory_add(path);free(path);return ok;
  }
  if(!strcmp(action,"dict_settings")){dict_manager_open();return IsWindowVisible(dict_manager);}
  if(!strcmp(action,"dict_remove")) {
    dict_manager_open();size_t before=dict_dir_count;
    SendDlgItemMessageW(dict_manager,DICT_PATHS,LB_SETCURSEL,(WPARAM)atoi(drive_args[1]),0);
    SendMessageW(dict_manager,WM_COMMAND,DICT_REMOVE,0);ShowWindow(dict_manager,SW_HIDE);return dict_dir_count+1==before;
  }
  if(!strcmp(action,"dict_auto")) {
    dict_manager_open();CheckDlgButton(dict_manager,DICT_AUTO,atoi(drive_args[1]) ? BST_CHECKED:BST_UNCHECKED);
    SendMessageW(dict_manager,WM_COMMAND,DICT_AUTO,0);ShowWindow(dict_manager,SW_HIDE);return dict_auto==atoi(drive_args[1]);
  }
  if(!strcmp(action,"dict_close")) {
    HWND panels[]={dict_popup,dict_manager,vocab_panel};for(int i=0;i<3;i++)if(panels[i])SendMessageW(panels[i],WM_COMMAND,DICT_CLOSE,0);return 1;
  }
  if(!strcmp(action,"dict_collapse")) {
    size_t i=(size_t)atoi(drive_args[1]);if(i>=dict_count || !dict_headers[i])return 0;
    SendMessageW(dict_view,WM_COMMAND,DICT_GROUP+i,0);return dict_collapsed[i]==atoi(drive_args[2]) && IsWindowVisible(dict_bodies[i])==!dict_collapsed[i];
  }
  if(!strcmp(action,"dict_check")) {
    wchar_t raw[8192];GetWindowTextW(GetDlgItem(dict_popup,DICT_QUERY),raw,8192);char *word=host_utf8(raw);
    int ok=dict_popup && IsWindowVisible(dict_popup) && word && !strcmp(word,drive_args[1]) && dict_word && !strcmp(dict_word,word);free(word);
    cv_text j={0};size_t groups=0;cv_text_string(&j,"{\"word\":");cv_text_json(&j,dict_word ? dict_word:"");
    RECT box;GetClientRect(dict_popup,&box);cv_text_format(&j,",\"surface_width_dip\":%d,\"results\":[",(int)(box.right*96/shell_dpi)-2*SHELL_SHADOW_PAD);
    for(size_t i=0;i<dict_count;i++)if(dict_headers[i]) {
      groups++;int n=GetWindowTextLengthW(dict_bodies[i]);wchar_t *body=calloc((size_t)n+1,sizeof(wchar_t));if(!body){ok=0;break;}
      GetWindowTextW(dict_bodies[i],body,n+1);char *utf8=host_utf8(body);free(body);
      if(!utf8){ok=0;break;}char *p=utf8,*q=utf8;while(*p){if(*p!='\r')*q++=*p;p++;}*q=0;
      for(size_t k=0;k<dict_result_count;k++)if(dict_results[k].dictionary_index==i)
        ok &= strstr(utf8,dict_results[k].word)!=NULL && strstr(utf8,dict_results[k].definition)!=NULL;
      free(utf8);
    }
    for(size_t i=0;i<dict_result_count;i++) {
      if(i)cv_text_string(&j,",");
      cv_text_string(&j,"{");annot_json_string(&j,"word",dict_results[i].word);cv_text_string(&j,",");
      annot_json_string(&j,"definition",dict_results[i].definition);cv_text_string(&j,",");annot_json_string(&j,"source",dict_results[i].dictionary);cv_text_string(&j,"}");
    }
    char *sentence=dict_sentence(&dict_anchor);cv_text_format(&j,"],\"groups\":%zu,\"native_content_matches\":%s,",groups,ok ? "true":"false");
    annot_json_string(&j,"sentence",sentence ? sentence:"");free(sentence);cv_text_string(&j,"}\n");
    if(!groups){GetWindowTextW(GetDlgItem(dict_popup,DICT_STATUS),raw,8192);ok &= wcsstr(raw,L"未收录")!=NULL;}
    HMENU menu=select_context_menu();wchar_t label[32];GetMenuStringW(menu,8,label,32,MF_BYCOMMAND);ok &= wcsstr(label,L"查词")!=NULL;DestroyMenu(menu);
    ok &= groups==(size_t)atoi(drive_args[2]) && !j.failed && select_drive_write(drive_args[3],".dictionary.json",j.data,j.size);
    cv_text_free(&j);return ok;
  }
  if(!strcmp(action,"dict_save")) {
    size_t before=vocab_count;SendMessageW(dict_popup,WM_COMMAND,DICT_SAVE,0);return vocab_count==before+1;
  }
  if(!strcmp(action,"dict_copy")) {
    HWND edit=GetDlgItem(dict_popup,DICT_QUERY);SendMessageW(edit,EM_SETSEL,0,-1);SendMessageW(edit,WM_COPY,0,0);
    if(!OpenClipboard(g.window))return 0;
    HANDLE memory=GetClipboardData(CF_UNICODETEXT);wchar_t *wide=memory ? GlobalLock(memory):NULL;
    char *copy=wide ? host_utf8(wide):NULL;int ok=copy && dict_word && !strcmp(copy,dict_word);
    free(copy);if(wide)GlobalUnlock(memory);CloseClipboard();return ok;
  }
  if(!strcmp(action,"dict_pick_vocab")) {
    SendDlgItemMessageW(vocab_panel,DICT_LIST,LB_SETCURSEL,(WPARAM)atoi(drive_args[1]),0);
    SendMessageW(vocab_panel,WM_COMMAND,MAKEWPARAM(DICT_LIST,LBN_SELCHANGE),0);
    return GetWindowTextLengthW(GetDlgItem(vocab_panel,DICT_STATUS))>0;
  }
  if(!strcmp(action,"dict_vocab")) {
    vocab_open();return IsWindowVisible(vocab_panel) && vocab_count==(size_t)atoi(drive_args[1]);
  }
  if(!strcmp(action,"dict_filter")) {
    SendDlgItemMessageW(vocab_panel,DICT_FILTER,CB_SETCURSEL,(WPARAM)atoi(drive_args[1]),0);
    SendMessageW(vocab_panel,WM_COMMAND,MAKEWPARAM(DICT_FILTER,CBN_SELCHANGE),0);
    return SendDlgItemMessageW(vocab_panel,DICT_LIST,LB_GETCOUNT,0,0)==atoi(drive_args[2]);
  }
  if(!strcmp(action,"dict_export")) {
    wchar_t path[HOST_PATH],*name=host_wide(drive_args[1],strlen(drive_args[1]));if(!name)return 0;
    path_join(path,HOST_PATH,g.evidence_dir,name);free(name);return vocab_export(path);
  }
  if(!strcmp(action,"dict_roundtrip")) {
    size_t found=0;
    for(size_t i=0;i<vocab_count;i++)if(vocab[i].book_id==g.frame.book_id) {
      char *sentence=dict_sentence(&vocab[i].anchor);if(!sentence || strcmp(sentence,vocab[i].sentence)){free(sentence);return 0;}free(sentence);found++;
    }
    return found==(size_t)atoi(drive_args[1]);
  }
  return 0;
}
