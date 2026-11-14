/* SPDX-License-Identifier: MIT */
/* L11: included by shell_docedit.inc in place of its original de_save(). */
static DWORD de_save_error;
static int de_save_to(const char *destination) {
  void *bytes=NULL;size_t size=0;exr_error error={0};
  wchar_t absolute[MAX_PATH],temp[MAX_PATH]=L"",directory[MAX_PATH];
  HANDLE file=INVALID_HANDLE_VALUE;int ok=0;DWORD failure=ERROR_SUCCESS;
  char *path=NULL;
  if(!de.doc)return 0;
  de_save_error=0;
  wchar_t *input=destination ? host_wide(destination,strlen(destination)):NULL;
  DWORD length=input ? GetFullPathNameW(input,MAX_PATH,absolute,NULL):0;
  free(input);
  if(!length || length>=MAX_PATH) {failure=ERROR_BAD_PATHNAME;goto done;}
  path=host_utf8(absolute);
  if(!path || strlen(path)>=sizeof(de.path)) {
    failure=ERROR_FILENAME_EXCED_RANGE;goto done;
  }
  exr_status status=exr_edit_docx_write(de.doc,&bytes,&size,&error);
  if(status!=EXR_OK) {free(path);de_error(L"无法生成 DOCX",status,&error);return 0;}
  wcscpy(directory,absolute);
  wchar_t *slash=wcsrchr(directory,L'\\');
  if(!slash) {failure=ERROR_BAD_PATHNAME;goto done;}
  slash[1]=0;
  if(!GetTempFileNameW(directory,L"exr",0,temp))goto system_error;
  file=CreateFileW(temp,GENERIC_WRITE,0,NULL,TRUNCATE_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)goto system_error;
  for(size_t at=0;at<size;) {
    DWORD written=0,want=(DWORD)((size-at)>0x100000 ? 0x100000:size-at);
    if(!WriteFile(file,(char *)bytes+at,want,&written,NULL))goto system_error;
    if(written!=want) {failure=ERROR_WRITE_FAULT;goto done;}
    at+=written;
  }
  if(!FlushFileBuffers(file))goto system_error;
  if(!CloseHandle(file)) {file=INVALID_HANDLE_VALUE;goto system_error;}
  file=INVALID_HANDLE_VALUE;
  /* Respect the destination's read-only attribute even if rename is permitted. */
  DWORD attributes=GetFileAttributesW(absolute);
  if(attributes!=INVALID_FILE_ATTRIBUTES && (attributes&FILE_ATTRIBUTE_READONLY)) {
    failure=ERROR_ACCESS_DENIED;goto done;
  }
  ok=ReplaceFileW(absolute,temp,NULL,0,NULL,NULL)!=0;
  if(!ok && GetLastError()==ERROR_FILE_NOT_FOUND)
    ok=MoveFileExW(temp,absolute,MOVEFILE_WRITE_THROUGH)!=0;
  if(!ok)goto system_error;
  goto done;
system_error:
  failure=GetLastError();
done:
  if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
  if(!ok && temp[0])DeleteFileW(temp);
  exr_free(bytes);
  if(!ok) {
    wchar_t reason[512]=L"",message[768];
    de_save_error=failure ? failure:ERROR_WRITE_FAULT;
    FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM|FORMAT_MESSAGE_IGNORE_INSERTS,NULL,
      de_save_error,0,reason,512,NULL);
    swprintf(message,768,L"无法保存 DOCX（%lu）：%ls 修改仍保留在编辑器中。",
      (unsigned long)de_save_error,reason);
    free(path);set_status(message);return 0;
  }
  strcpy(de.path,path);free(path);
  const wchar_t *name=wcsrchr(absolute,L'\\');
  copy_wstring(de.title,512,name ? name+1:absolute);
  de.dirty=0;de.saved=1;de_title();
  set_status(L"DOCX 已保存。");
  if(g.has_current) {
    shelf_book *book=shelf_find(g.current.id);
    if(book) {
      char *recent_path=host_strdup(de.path);
      if(recent_path) {free(book->path);book->path=recent_path;}
      book->book_hash[0]=0;
      shelf_opened();shelf_refresh();
    }
  }
  return 1;
}
static int de_save(void) {return de_save_to(de.path);}
/* UTF-8 injection is the same path used by the native dialog and console tests. */
static int de_save_as(const char *injected_path) {
  if(!de.doc)return 0;
  if(injected_path)return de_save_to(injected_path);
  if(!g.window) {set_status(L"另存为需要目标路径。");return 0;}
  wchar_t path[MAX_PATH]=L"";
  wchar_t *current=host_wide(de.path,strlen(de.path));
  if(current) {copy_wstring(path,MAX_PATH,current);free(current);}
  OPENFILENAMEW dialog={0};dialog.lStructSize=sizeof(dialog);dialog.hwndOwner=g.window;
  dialog.lpstrTitle=L"另存为 DOCX";
  dialog.lpstrFilter=L"Word 文档 (*.docx)\0*.docx\0\0";
  dialog.lpstrFile=path;dialog.nMaxFile=MAX_PATH;dialog.lpstrDefExt=L"docx";
  dialog.Flags=OFN_OVERWRITEPROMPT|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
  if(!GetSaveFileNameW(&dialog)) {
    DWORD failure=CommDlgExtendedError();
    if(failure) {
      wchar_t message[160];swprintf(message,160,L"无法打开另存为对话框（%lu）。",(unsigned long)failure);
      set_status(message);
    }
    return 0;
  }
  char *utf8=host_utf8(path);
  if(!utf8) {set_status(L"另存为路径转换失败。");return 0;}
  int ok=de_save_to(utf8);free(utf8);return ok;
}
