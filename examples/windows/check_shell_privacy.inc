/* SPDX-License-Identifier: MIT */
/* Production atomic writer failure/cleanup and abrupt-process residue probe. */
#include <sddl.h>
static void test_privacy(void) {
  wchar_t root[HOST_PATH],path[HOST_PATH],temp[HOST_PATH],base[HOST_PATH];
  assert(GetTempPathW(HOST_PATH,base));
  swprintf(root,HOST_PATH,L"%lsexreader-privacy-%lu",base,(unsigned long)GetCurrentProcessId());
  assert(CreateDirectoryW(root,NULL));path_join(path,HOST_PATH,root,L"state.json");
  wcscpy(g.data_dir,root);sy_default_paths();
  assert(sy_cred_save("audit-user","audit-only-password"));
  DWORD needed=0;GetFileSecurityW(sy_cred_file,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,NULL,0,&needed);
  assert(needed);PSECURITY_DESCRIPTOR sd=malloc(needed);assert(sd);
  assert(GetFileSecurityW(sy_cred_file,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,sd,needed,&needed));
  LPWSTR sddl=NULL;assert(ConvertSecurityDescriptorToStringSecurityDescriptorW(sd,SDDL_REVISION_1,
    OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&sddl,NULL));
  char *acl=host_utf8(sddl);assert(acl);printf("PRIVACY sync.cred DPAPI current-user; actual inherited owner/DACL=%s\n",acl);
  free(acl);LocalFree(sddl);free(sd);sy_cred_delete();
  assert(GetFileAttributesW(sy_cred_file)==INVALID_FILE_ATTRIBUTES);
  swprintf(temp,HOST_PATH,L"%ls.tmp",path);
  assert(sy_write(path,"old",3));assert(GetFileAttributesW(temp)==INVALID_FILE_ATTRIBUTES);
  HANDLE held=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
  assert(held!=INVALID_HANDLE_VALUE);assert(!sy_write(path,"new",3));
  assert(GetFileAttributesW(temp)==INVALID_FILE_ATTRIBUTES);assert(CloseHandle(held));
  size_t n=0;char *b=sy_read(path,&n);assert(b && n==3 && !memcmp(b,"old",3));free(b);
  puts("PRIVACY atomic publish failure: original preserved; .tmp absent");
  wchar_t exe[HOST_PATH],command[HOST_PATH*3];assert(GetModuleFileNameW(NULL,exe,HOST_PATH));
  swprintf(command,HOST_PATH*3,L"\"%ls\" --privacy-crash \"%ls\"",exe,temp);
  STARTUPINFOW si={0};PROCESS_INFORMATION pi={0};si.cb=sizeof(si);
  assert(CreateProcessW(NULL,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi));
  assert(WaitForSingleObject(pi.hProcess,10000)==WAIT_OBJECT_0);
  DWORD code=0;assert(GetExitCodeProcess(pi.hProcess,&code) && code==77);
  CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
  assert(GetFileAttributesW(temp)!=INVALID_FILE_ATTRIBUTES);
  b=sy_read(path,&n);assert(b && n==3 && !memcmp(b,"old",3));free(b);
  puts("PRIVACY abrupt exit=77: original preserved; .tmp remains (startup scavenger MISSING)");
  /* Test owns this directory. Cleanup does not imply product crash recovery. */
  assert(DeleteFileW(temp));assert(DeleteFileW(path));
  wchar_t pattern[HOST_PATH];path_join(pattern,HOST_PATH,root,L"*");
  WIN32_FIND_DATAW fd;HANDLE find=FindFirstFileW(pattern,&fd);assert(find!=INVALID_HANDLE_VALUE);
  do {assert(!wcscmp(fd.cFileName,L".") || !wcscmp(fd.cFileName,L".."));} while(FindNextFileW(find,&fd));
  FindClose(find);assert(RemoveDirectoryW(root));puts("PRIVACY isolated test directory empty and removed");
}
