/* Test-only provider instrumentation; no text, secret, or memory dump. */
#ifdef EXR_F09_DIAGNOSTICS
static void host_a11y_f09_trace(host_a11y_range *range, const char *stage, int max, HRESULT hr) {
  char path[512], line[320];
  DWORD length=GetEnvironmentVariableA("F09_PROVIDER_LOG",path,sizeof(path));
  HANDLE file; DWORD written;
  host_a11y_snapshot *snapshot=range?range->snapshot:NULL;
  int n;
  if(!length || length>=sizeof(path))return;
  n=snprintf(line,sizeof(line),
    "stage=%s object=%p pid=%lu tid=%lu range_refs=%ld snapshot_refs=%ld units=%d start=%d end=%d max=%d hr=0x%08lx\n",
    stage,(void*)range,(unsigned long)GetCurrentProcessId(),(unsigned long)GetCurrentThreadId(),
    range?(long)range->refs:-1L,snapshot?(long)snapshot->refs:-1L,snapshot?snapshot->units:-1,
    range?range->start:-1,range?range->end:-1,max,(unsigned long)hr);
  if(n<=0 || n>=(int)sizeof(line))return;
  file=CreateFileA(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return;
  WriteFile(file,line,(DWORD)n,&written,NULL);
  CloseHandle(file);
}
static void host_a11y_f09_array(SAFEARRAY *array, host_a11y_range *range) {
  char path[512],line[320]; DWORD written;
  DWORD length=GetEnvironmentVariableA("F09_PROVIDER_LOG",path,sizeof(path));
  VARTYPE vt=VT_EMPTY; LONG low=-1,high=-1;
  HRESULT type_result=SafeArrayGetVartype(array,&vt);
  HRESULT low_result=SafeArrayGetLBound(array,1,&low);
  HRESULT high_result=SafeArrayGetUBound(array,1,&high);
  HANDLE file; int n;
  if(!length || length>=sizeof(path))return;
  n=snprintf(line,sizeof(line),
    "stage=array-publish object=%p pid=%lu tid=%lu vt=%u dim=%u low=%ld high=%ld type_hr=0x%08lx low_hr=0x%08lx high_hr=0x%08lx\n",
    (void*)range,(unsigned long)GetCurrentProcessId(),(unsigned long)GetCurrentThreadId(),
    (unsigned)vt,(unsigned)SafeArrayGetDim(array),(long)low,(long)high,
    (unsigned long)type_result,(unsigned long)low_result,(unsigned long)high_result);
  if(n<=0 || n>=(int)sizeof(line))return;
  file=CreateFileA(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return;
  WriteFile(file,line,(DWORD)n,&written,NULL);CloseHandle(file);
}
/* After decrement another owner may free the range: never dereference it here. */
static void host_a11y_f09_count(const void *object, LONG count) {
  char path[512],line[160]; DWORD written;
  DWORD length=GetEnvironmentVariableA("F09_PROVIDER_LOG",path,sizeof(path));
  HANDLE file; int n;
  if(!length || length>=sizeof(path))return;
  n=snprintf(line,sizeof(line),"stage=release-result object=%p pid=%lu tid=%lu count=%ld\n",
    object,(unsigned long)GetCurrentProcessId(),(unsigned long)GetCurrentThreadId(),(long)count);
  if(n<=0 || n>=(int)sizeof(line))return;
  file=CreateFileA(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return;
  WriteFile(file,line,(DWORD)n,&written,NULL);CloseHandle(file);
}
#define F09_COUNT(object,count) host_a11y_f09_count(object,count)
#define F09_ARRAY(array,range) host_a11y_f09_array(array,range)
#define F09_TRACE(range,stage,max,hr) host_a11y_f09_trace(range,stage,max,hr)
#else
#define F09_COUNT(object,count) ((void)0)
#define F09_ARRAY(array,range) ((void)0)
#define F09_TRACE(range,stage,max,hr) ((void)0)
#endif
