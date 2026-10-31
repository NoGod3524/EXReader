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
    "stage=%s pid=%lu tid=%lu range_refs=%ld snapshot_refs=%ld units=%d start=%d end=%d max=%d hr=0x%08lx\n",
    stage,(unsigned long)GetCurrentProcessId(),(unsigned long)GetCurrentThreadId(),
    range?(long)range->refs:-1L,snapshot?(long)snapshot->refs:-1L,snapshot?snapshot->units:-1,
    range?range->start:-1,range?range->end:-1,max,(unsigned long)hr);
  if(n<=0 || n>=(int)sizeof(line))return;
  file=CreateFileA(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return;
  WriteFile(file,line,(DWORD)n,&written,NULL);
  CloseHandle(file);
}
#define F09_TRACE(range,stage,max,hr) host_a11y_f09_trace(range,stage,max,hr)
#else
#define F09_TRACE(range,stage,max,hr) ((void)0)
#endif
