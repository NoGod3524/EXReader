/* SPDX-License-Identifier: MIT */
/* F10 identity probes for the shell credential store and HTTPS path. These
   are run explicitly by the ledger workflow on a disposable runner, never by
   CTest: they need a second local account and public network access.

   --f10-unavailable DIR   run by a process that lives in a network logon
                           session (WinRM as the probe account). Credential
                           Manager has no credential set there, so CredWriteW
                           fails for real; the shell must fall back to its
                           DPAPI file (or refuse) without writing a CM record.
   --f10-cross-user        run as the runner account with EXR_F10_USER and
                           EXR_F10_PASSWORD naming a second, non-admin local
                           account. The runner's Credential Manager record,
                           private-DACL sync.cred and DPAPI blob must all be
                           unreadable to that account.
   --f10-public-tls        the shell's own WinHTTP request (sy_http_once) and
                           error classification (sy_explain) against public
                           origins, with no credential loaded. */
#include <stdarg.h>
#include <ntsecapi.h>
#include <userenv.h>

static void f10_json_text(const char *key,const char *value,int comma) {
  printf("%s\"%s\":\"",comma ? ",":"",key);
  for(const unsigned char *c=(const unsigned char *)(value ? value:"");*c;c++) {
    if(*c=='"' || *c=='\\') printf("\\%c",*c); else if(*c<0x20) printf("\\u%04x",*c); else putchar(*c);
  }
  putchar('"');
}
static int f10_checks,f10_failed;
static void f10_check(const char *name,int pass,const char *format,...) {
  char detail[512];va_list list;va_start(list,format);vsnprintf(detail,sizeof(detail),format,list);va_end(list);
  printf("F10CHECK {\"name\":\"%s\",\"pass\":%s",name,pass ? "true":"false");f10_json_text("detail",detail,1);puts("}");
  f10_checks++;if(!pass) f10_failed++;
}
static int f10_finish(const char *mode) {
  printf("F10RESULT {\"mode\":\"%s\",\"checks\":%d,\"failed\":%d,\"accepted\":%s}\n",mode,f10_checks,f10_failed,
         f10_checks && !f10_failed ? "true":"false");
  return f10_checks && !f10_failed ? 0:1;
}
/* Logon type of the current thread's effective token (3 = Network). */
static ULONG f10_logon_type(char sid_text[200]) {
  HANDLE token=NULL;ULONG type=0;sid_text[0]=0;
  if(!OpenThreadToken(GetCurrentThread(),TOKEN_QUERY,TRUE,&token) && !OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)) return 0;
  TOKEN_STATISTICS stats;DWORD needed=0;
  if(GetTokenInformation(token,TokenStatistics,&stats,sizeof(stats),&needed)) {
    PSECURITY_LOGON_SESSION_DATA data=NULL;
    if(LsaGetLogonSessionData(&stats.AuthenticationId,&data)==0 && data) {type=data->LogonType;LsaFreeReturnBuffer(data);}
  }
  BYTE buffer[256];TOKEN_USER *user=(TOKEN_USER *)buffer;LPSTR sid=NULL;
  if(GetTokenInformation(token,TokenUser,buffer,sizeof(buffer),&needed) && ConvertSidToStringSidA(user->User.Sid,&sid)) {
    snprintf(sid_text,200,"%s",sid);LocalFree(sid);
  }
  CloseHandle(token);return type;
}
static int f10_cm_read_raw(DWORD *error) {
  PCREDENTIALW cred=NULL;*error=0;
  if(CredReadW(SY_CRED_TARGET,CRED_TYPE_GENERIC,0,&cred)) {CredFree(cred);return 1;}
  *error=GetLastError();return 0;
}

static int test_f10_unavailable(const char *directory) {
  char sid[200];ULONG type=f10_logon_type(sid);
  f10_check("process_runs_in_network_logon_session",type==Network,"LogonType=%lu (3=Network) user=%s",(unsigned long)type,sid);
  /* The real platform refusal, observed before any product code runs. */
  char blob[]="probe";CREDENTIALW probe;memset(&probe,0,sizeof(probe));
  probe.Type=CRED_TYPE_GENERIC;probe.TargetName=(LPWSTR)L"EXReader/ledger-f10-unavailable-probe";
  probe.Persist=CRED_PERSIST_LOCAL_MACHINE;probe.CredentialBlob=(LPBYTE)blob;probe.CredentialBlobSize=5;
  BOOL wrote=CredWriteW(&probe,0);DWORD write_error=wrote ? 0:GetLastError();
  if(wrote) CredDeleteW(probe.TargetName,CRED_TYPE_GENERIC,0);
  f10_check("credential_manager_write_refused_by_platform",!wrote && write_error==ERROR_NO_SUCH_LOGON_SESSION,
            "CredWriteW=%d GetLastError=%lu (1312=ERROR_NO_SUCH_LOGON_SESSION)",(int)wrote,(unsigned long)write_error);
  wchar_t *root=host_wide(directory,strlen(directory));assert(root);
  wcscpy(g.data_dir,root);sy_default_paths();free(root);
  privacy_backend("");
  sy_wipe(&sy_user);sy_wipe(&sy_pass);
  int saved=sy_cred_save("network-session-user","network-session-secret");
  DWORD read_error=0;int cm_present=f10_cm_read_raw(&read_error);
  int file_present=GetFileAttributesW(sy_cred_file)!=INVALID_FILE_ATTRIBUTES;
  f10_check("shell_save_wrote_no_credential_manager_record",!cm_present,
            "CredReadW(EXReader/WebDAV) present=%d error=%lu",cm_present,(unsigned long)read_error);
  if(saved) {
    sy_wipe(&sy_user);sy_wipe(&sy_pass);
    int loaded=sy_cred_load() && sy_user && !strcmp(sy_user,"network-session-user") && sy_pass && !strcmp(sy_pass,"network-session-secret");
    f10_check("shell_fell_back_to_private_dpapi_file",file_present && loaded,
              "sy_cred_save=1 sync.cred present=%d reloaded=%d",file_present,loaded);
    if(file_present) {privacy_assert_credential_acl(sy_cred_file);f10_check("fallback_file_private_dacl",1,"owner=this account, DACL=account+SYSTEM, protected");}
  } else {
    DWORD protect_error=0;
    DATA_BLOB in={5,(BYTE *)blob},out={0};
    if(CryptProtectData(&in,L"probe",NULL,NULL,NULL,CRYPTPROTECT_UI_FORBIDDEN,&out)) LocalFree(out.pbData); else protect_error=GetLastError();
    f10_check("shell_refused_without_writing_anything",!file_present,
              "sy_cred_save=0 sync.cred present=%d; DPAPI in this session error=%lu",file_present,(unsigned long)protect_error);
  }
  sy_cred_delete();
  f10_check("cleanup_left_no_credential",GetFileAttributesW(sy_cred_file)==INVALID_FILE_ATTRIBUTES && !f10_cm_read_raw(&read_error),
            "sync.cred and CM record absent after sy_cred_delete");
  return f10_finish("unavailable");
}

static int test_f10_cross_user(void) {
  const char *user_a=getenv("EXR_F10_USER"),*password_a=getenv("EXR_F10_PASSWORD");
  assert(user_a && user_a[0] && password_a && password_a[0]);
  wchar_t *user=host_wide(user_a,strlen(user_a)),*password=host_wide(password_a,strlen(password_a));assert(user && password);
  wchar_t base[HOST_PATH],root[HOST_PATH];assert(GetTempPathW(HOST_PATH,base));
  swprintf(root,HOST_PATH,L"%lsexreader-f10-cross-%lu",base,(unsigned long)GetCurrentProcessId());
  assert(CreateDirectoryW(root,NULL));wcscpy(g.data_dir,root);sy_default_paths();
  f10_saved_cm saved;f10_cm_backup(&saved);
  char sid[200];f10_logon_type(sid);printf("F10 runner account sid=%s\n",sid);
  /* Runner identity: Credential Manager record and the DPAPI fallback file. */
  privacy_backend("");
  assert(sy_cred_save("runner-cm-user","runner-cm-secret"));
  DWORD error=0;assert(f10_cm_read_raw(&error));
  privacy_backend("dpapi");
  assert(sy_cred_save("runner-file-user","runner-file-secret"));
  privacy_assert_credential_acl(sy_cred_file);
  size_t blob_size=0;char *blob=sy_read(sy_cred_file,&blob_size);assert(blob && blob_size);
  /* Second identity with a real credential set. */
  static const DWORD types[]={LOGON32_LOGON_INTERACTIVE,LOGON32_LOGON_BATCH,LOGON32_LOGON_NETWORK_CLEARTEXT};
  static const char *type_names[]={"interactive","batch","network_cleartext"};
  HANDLE token=NULL;int used=-1;DWORD logon_errors[3]={0};
  for(int i=0;i<3 && !token;i++) {
    if(LogonUserW(user,L".",password,types[i],LOGON32_PROVIDER_DEFAULT,&token)) used=i; else {logon_errors[i]=GetLastError();token=NULL;}
  }
  SecureZeroMemory(password,wcslen(password)*sizeof(wchar_t));
  f10_check("second_local_account_logon",token!=NULL,"logon=%s errors interactive=%lu batch=%lu cleartext=%lu",
            used>=0 ? type_names[used]:"none",(unsigned long)logon_errors[0],(unsigned long)logon_errors[1],(unsigned long)logon_errors[2]);
  if(token) {
    PROFILEINFOW profile;memset(&profile,0,sizeof(profile));profile.dwSize=sizeof(profile);profile.lpUserName=user;
    int profile_loaded=LoadUserProfileW(token,&profile)!=0;DWORD profile_error=profile_loaded ? 0:GetLastError();
    assert(ImpersonateLoggedOnUser(token));
    char other_sid[200];f10_logon_type(other_sid);
    f10_check("impersonating_a_different_account",strcmp(other_sid,sid)!=0,"runner=%s other=%s profile_loaded=%d error=%lu",
              sid,other_sid,profile_loaded,(unsigned long)profile_error);
    DWORD cm_error=0;int cm_visible=f10_cm_read_raw(&cm_error);
    f10_check("runner_credential_manager_record_invisible_to_other_account",!cm_visible && cm_error==ERROR_NOT_FOUND,
              "CredReadW present=%d error=%lu (1168=ERROR_NOT_FOUND)",cm_visible,(unsigned long)cm_error);
    HANDLE file=CreateFileW(sy_cred_file,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    DWORD open_error=file==INVALID_HANDLE_VALUE ? GetLastError():0;if(file!=INVALID_HANDLE_VALUE) CloseHandle(file);
    f10_check("runner_sync_cred_file_denied_by_private_dacl",file==INVALID_HANDLE_VALUE && open_error==ERROR_ACCESS_DENIED,
              "CreateFileW(GENERIC_READ) error=%lu (5=ERROR_ACCESS_DENIED)",(unsigned long)open_error);
    DATA_BLOB in={(DWORD)blob_size,(BYTE *)blob},entropy={14,(BYTE *)"EXReader-sync1"},out={0};
    BOOL opened=CryptUnprotectData(&in,NULL,&entropy,NULL,NULL,CRYPTPROTECT_UI_FORBIDDEN,&out);
    DWORD unprotect_error=opened ? 0:GetLastError();
    if(opened) {SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);}
    f10_check("runner_dpapi_blob_undecryptable_by_other_account",!opened,"CryptUnprotectData=%d error=%lu",(int)opened,(unsigned long)unprotect_error);
    sy_wipe(&sy_user);sy_wipe(&sy_pass);privacy_backend("");
    int loaded=sy_cred_load();
    f10_check("shell_credential_load_as_other_account_yields_nothing",!loaded && !sy_user && !sy_pass,"sy_cred_load=%d",loaded);
    int other_saved=sy_cred_cm_write("other-account-user","other-account-secret");DWORD other_error=other_saved ? 0:GetLastError();
    assert(RevertToSelf());
    char *u=NULL,*p=NULL;int runner_read=sy_cred_cm_read(&u,&p);
    f10_check("runner_record_unchanged_by_other_account_write",runner_read && u && !strcmp(u,"runner-cm-user"),
              "other account CredWriteW=%d error=%lu; runner reads user=%s",other_saved,(unsigned long)other_error,u ? u:"(none)");
    sy_wipe(&u);sy_wipe(&p);
    if(other_saved) {assert(ImpersonateLoggedOnUser(token));sy_cred_cm_delete();assert(RevertToSelf());}
    if(profile_loaded) UnloadUserProfile(token,profile.hProfile);
    CloseHandle(token);
  }
  SecureZeroMemory(blob,blob_size);free(blob);
  privacy_backend("");sy_cred_delete();f10_cm_restore(&saved);
  assert(RemoveDirectoryW(root));free(user);free(password);
  return f10_finish("cross-user");
}

static int test_f10_public_tls(void) {
  static const struct { const char *url; int refuse; } cases[]={
    {"https://www.github.com/",0},{"https://example.com/",0},{"https://badssl.com/",0},
    {"https://expired.badssl.com/",1},{"https://wrong.host.badssl.com/",1},
    {"https://self-signed.badssl.com/",1},{"https://untrusted-root.badssl.com/",1},
  };
  sy_wipe(&sy_user);sy_wipe(&sy_pass); /* never send an Authorization header to a public origin */
  for(size_t i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
    sy_target t;assert(sy_target_parse(cases[i].url,&t) && t.secure);
    sy_resp r;int ok=sy_http_once(&t,L"PROPFIND","","",0,L"Depth: 0\r\n",&r);
    sy_status s;memset(&s,0,sizeof(s));int code=sy_explain(&r,"probe",&s);
    int pass=cases[i].refuse ? (!ok && code==SY_TLS):(ok && r.status>0);
    char name[96];snprintf(name,sizeof(name),"%s %s",cases[i].refuse ? "refuse":"accept",cases[i].url);
    f10_check(name,pass,"http_status=%d winhttp_error=%lu class=%s",r.status,(unsigned long)r.werr,code==SY_TLS ? "SY_TLS":"other");
    sy_resp_free(&r);
  }
  return f10_finish("public-tls");
}
