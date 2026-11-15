/* SPDX-License-Identifier: MIT */
/* Production atomic writer failure/cleanup and abrupt-process residue probe. */
#include <sddl.h>
static void privacy_assert_credential_acl(const wchar_t *path) {
  DWORD needed=0;GetFileSecurityW(path,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,NULL,0,&needed);
  assert(needed);PSECURITY_DESCRIPTOR sd=malloc(needed);assert(sd);
  assert(GetFileSecurityW(path,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,sd,needed,&needed));
  SECURITY_DESCRIPTOR_CONTROL control=0;DWORD revision=0;
  assert(GetSecurityDescriptorControl(sd,&control,&revision) && (control&SE_DACL_PROTECTED));
  PACL dacl=NULL;BOOL present=FALSE,defaulted=FALSE;
  assert(GetSecurityDescriptorDacl(sd,&present,&dacl,&defaulted) && present && dacl && dacl->AceCount==2);
  HANDLE token=NULL;assert(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token));
  needed=0;GetTokenInformation(token,TokenUser,NULL,0,&needed);
  TOKEN_USER *user=malloc(needed);assert(user && GetTokenInformation(token,TokenUser,user,needed,&needed));
  PSID owner=NULL;assert(GetSecurityDescriptorOwner(sd,&owner,&defaulted) && owner && EqualSid(owner,user->User.Sid));
  BYTE system[SECURITY_MAX_SID_SIZE];DWORD system_size=sizeof(system);
  assert(CreateWellKnownSid(WinLocalSystemSid,NULL,system,&system_size));
  int users=0,systems=0;
  for(DWORD i=0;i<dacl->AceCount;i++) {
    ACCESS_ALLOWED_ACE *ace=NULL;assert(GetAce(dacl,i,(void **)&ace));
    assert(ace->Header.AceType==ACCESS_ALLOWED_ACE_TYPE && !(ace->Header.AceFlags&INHERITED_ACE));
    assert(ace->Mask==FILE_ALL_ACCESS);
    if(EqualSid(&ace->SidStart,user->User.Sid)) users++;
    else {assert(EqualSid(&ace->SidStart,system));systems++;}
  }
  assert(users==1 && systems==1);free(user);CloseHandle(token);
  LPWSTR sddl=NULL;assert(ConvertSecurityDescriptorToStringSecurityDescriptorW(sd,SDDL_REVISION_1,
    OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&sddl,NULL));
  char *acl=host_utf8(sddl);assert(acl);printf("PRIVACY sync.cred protected current-user/SYSTEM owner/DACL=%s\n",acl);
  free(acl);LocalFree(sddl);free(sd);
}
static void test_privacy(void) {
  wchar_t root[HOST_PATH],path[HOST_PATH],temp[HOST_PATH],base[HOST_PATH];
  assert(GetTempPathW(HOST_PATH,base));
  swprintf(root,HOST_PATH,L"%lsexreader-privacy-%lu",base,(unsigned long)GetCurrentProcessId());
  assert(CreateDirectoryW(root,NULL));path_join(path,HOST_PATH,root,L"state.json");
  wcscpy(g.data_dir,root);sy_default_paths();
  assert(sy_cred_save("audit-user","audit-only-password"));
  privacy_assert_credential_acl(sy_cred_file);
  assert(sy_cred_save("audit-user-2","replacement-password"));
  privacy_assert_credential_acl(sy_cred_file);
  assert(sy_cred_load() && !strcmp(sy_user,"audit-user-2") && !strcmp(sy_pass,"replacement-password"));
  wchar_t cred_temp[HOST_PATH],sentinel[HOST_PATH];swprintf(cred_temp,HOST_PATH,L"%ls.tmp",sy_cred_file);
  path_join(sentinel,HOST_PATH,root,L"sentinel");assert(sy_write_private(sentinel,"keep",4));
  assert(CreateHardLinkW(cred_temp,sentinel,NULL));assert(!sy_cred_save("changed","must-not-publish"));
  assert(!sy_cred_recover_temp() && GetFileAttributesW(cred_temp)!=INVALID_FILE_ATTRIBUTES);
  size_t n=0;char *b=sy_read(sentinel,&n);assert(b && n==4 && !memcmp(b,"keep",4));free(b);
  assert(DeleteFileW(cred_temp));assert(DeleteFileW(sentinel));
  assert(CreateDirectoryW(cred_temp,NULL));assert(!sy_cred_save("changed","must-not-publish"));
  assert(!sy_cred_recover_temp() && GetFileAttributesW(cred_temp)!=INVALID_FILE_ATTRIBUTES);
  assert(RemoveDirectoryW(cred_temp));
  assert(sy_write(cred_temp,"unowned-stage",13));
  assert(!sy_cred_recover_temp() && GetFileAttributesW(cred_temp)!=INVALID_FILE_ATTRIBUTES);
  assert(DeleteFileW(cred_temp));
  HANDLE locked=CreateFileW(sy_cred_file,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
  assert(locked!=INVALID_HANDLE_VALUE && !sy_cred_save("changed","must-not-publish"));
  assert(GetFileAttributesW(cred_temp)==INVALID_FILE_ATTRIBUTES);assert(CloseHandle(locked));
  assert(sy_cred_load() && !strcmp(sy_user,"audit-user-2") && !strcmp(sy_pass,"replacement-password"));
  privacy_assert_credential_acl(sy_cred_file);
  puts("PRIVACY private credential replacement: hard-link/directory collision refused; failed publish preserved old blob and removed owned .tmp");
  wchar_t exe[HOST_PATH],command[HOST_PATH*3],event_name[128];assert(GetModuleFileNameW(NULL,exe,HOST_PATH));
  swprintf(event_name,128,L"Local\\EXReader-privacy-ready-%lu",(unsigned long)GetCurrentProcessId());
  HANDLE ready=CreateEventW(NULL,TRUE,FALSE,event_name);assert(ready && GetLastError()!=ERROR_ALREADY_EXISTS);
  swprintf(command,HOST_PATH*3,L"\"%ls\" --privacy-credential-crash \"%ls\" \"%ls\"",exe,root,event_name);
  STARTUPINFOW si={0};PROCESS_INFORMATION pi={0};si.cb=sizeof(si);
  assert(CreateProcessW(NULL,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi));
  HANDLE waits[2]={ready,pi.hProcess};assert(WaitForMultipleObjects(2,waits,FALSE,10000)==WAIT_OBJECT_0);
  assert(!sy_cred_recover_temp()); /* A live writer owns the exclusive handle. */
  assert(TerminateProcess(pi.hProcess,77) && WaitForSingleObject(pi.hProcess,10000)==WAIT_OBJECT_0);
  DWORD code=0;assert(GetExitCodeProcess(pi.hProcess,&code) && code==77);
  CloseHandle(pi.hThread);CloseHandle(pi.hProcess);CloseHandle(ready);
  assert(GetFileAttributesW(cred_temp)!=INVALID_FILE_ATTRIBUTES);
  privacy_assert_credential_acl(cred_temp);
  sy_init(); /* Real production initialization, not test-owned directory cleanup. */
  assert(GetFileAttributesW(cred_temp)==INVALID_FILE_ATTRIBUTES);
  assert(sy_user && sy_pass && !strcmp(sy_user,"audit-user-2") && !strcmp(sy_pass,"replacement-password"));
  assert(sy_cred_save("audit-user-2","replacement-password"));
  assert(GetFileAttributesW(cred_temp)==INVALID_FILE_ATTRIBUTES);
  puts("PRIVACY credential forced termination=77 after production flush: sync initialization removed protected stage; old credential loaded; subsequent save succeeded");
  puts("PRIVACY sync initialization recovery refused live writer, hard link, directory and nonprivate DACL; no unrelated temp scan");
  sy_cred_delete();
  assert(GetFileAttributesW(sy_cred_file)==INVALID_FILE_ATTRIBUTES);
  swprintf(temp,HOST_PATH,L"%ls.tmp",path);
  assert(sy_write(path,"old",3));assert(GetFileAttributesW(temp)==INVALID_FILE_ATTRIBUTES);
  HANDLE held=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
  assert(held!=INVALID_HANDLE_VALUE);assert(!sy_write(path,"new",3));
  assert(GetFileAttributesW(temp)==INVALID_FILE_ATTRIBUTES);assert(CloseHandle(held));
  b=sy_read(path,&n);assert(b && n==3 && !memcmp(b,"old",3));free(b);
  puts("PRIVACY atomic publish failure: original preserved; .tmp absent");
  swprintf(command,HOST_PATH*3,L"\"%ls\" --privacy-crash \"%ls\"",exe,temp);
  memset(&si,0,sizeof(si));memset(&pi,0,sizeof(pi));si.cb=sizeof(si);
  assert(CreateProcessW(NULL,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi));
  assert(WaitForSingleObject(pi.hProcess,10000)==WAIT_OBJECT_0);
  code=0;assert(GetExitCodeProcess(pi.hProcess,&code) && code==77);
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
