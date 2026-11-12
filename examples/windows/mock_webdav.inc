/* SPDX-License-Identifier: MIT */
/* Minimal in-memory WebDAV server for the sync acceptance (rclone is not
   installed). Real TCP on 127.0.0.1; PROPFIND / GET / PUT / MKCOL, Basic
   auth, ETag + If-Match / If-None-Match. One thread per connection,
   "Connection: close". Test-only: knobs below simulate slow / broken servers. */
#include <winsock2.h>
#include <ws2tcpip.h>
typedef struct { char path[600]; int collection; char *data; size_t size; unsigned long etag; } mock_node;
static mock_node mock_nodes[512];
static int mock_node_count;
static CRITICAL_SECTION mock_lock;
static SOCKET mock_listener=INVALID_SOCKET;
static HANDLE mock_thread;
static volatile LONG mock_running;
static int mock_port;
static char mock_user[64],mock_pass[64];
static volatile LONG mock_delay_ms,mock_force_status,mock_force_count;
static volatile LONG mock_n_propfind,mock_n_get,mock_n_put,mock_n_mkcol,mock_n_denied;
static unsigned long mock_etag_counter;
static volatile LONG mock_active,mock_n_if_match,mock_n_forced;
#define MOCK_BASE "/dav/"

static mock_node *mock_find(const char *path) {
  for(int i=0;i<mock_node_count;i++) if(!strcmp(mock_nodes[i].path,path)) return &mock_nodes[i];
  return NULL;
}
static mock_node *mock_put_node(const char *path,int collection,const char *data,size_t size) {
  mock_node *n=mock_find(path);
  if(!n) {
    if(mock_node_count>=512) return NULL;
    n=&mock_nodes[mock_node_count++];memset(n,0,sizeof(*n));snprintf(n->path,sizeof(n->path),"%s",path);
  }
  free(n->data);n->data=NULL;n->size=0;n->collection=collection;
  if(size) {n->data=malloc(size);if(!n->data) return NULL;memcpy(n->data,data,size);n->size=size;}
  n->etag=++mock_etag_counter;return n;
}
static void mock_reset(void) {
  EnterCriticalSection(&mock_lock);
  for(int i=0;i<mock_node_count;i++) free(mock_nodes[i].data);
  mock_node_count=0;mock_etag_counter=0;mock_put_node(MOCK_BASE,1,NULL,0);
  LeaveCriticalSection(&mock_lock);
}
static int mock_b64(const char *in,char *out) {
  static const char t[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t n=strlen(in),o=0;
  for(size_t i=0;i<n;i+=3) {
    unsigned v=(unsigned char)in[i]<<16|(i+1<n ? (unsigned char)in[i+1]<<8:0)|(i+2<n ? (unsigned char)in[i+2]:0);
    out[o++]=t[v>>18&63];out[o++]=t[v>>12&63];out[o++]=i+1<n ? t[v>>6&63]:'=';out[o++]=i+2<n ? t[v&63]:'=';
  }
  out[o]=0;return (int)o;
}
static void mock_send(SOCKET s,int status,const char *reason,const char *extra,const char *body,size_t size) {
  char head[1024];
  int n=snprintf(head,sizeof(head),"HTTP/1.1 %d %s\r\n%sContent-Length: %zu\r\nConnection: close\r\n\r\n",status,reason,extra ? extra:"",size);
  send(s,head,n,0);
  if(size) send(s,body,(int)size,0);
}
/* Case-insensitive header lookup inside the request head. */
static int mock_header(const char *head,const char *name,char *out,size_t cap) {
  size_t len=strlen(name);
  for(const char *p=strstr(head,"\r\n");p;p=strstr(p+2,"\r\n")) {
    const char *line=p+2;
    if(!_strnicmp(line,name,len) && line[len]==':') {
      line+=len+1;while(*line==' ')line++;
      const char *end=strstr(line,"\r\n");size_t n=end ? (size_t)(end-line):strlen(line);
      if(n>=cap) n=cap-1;
      memcpy(out,line,n);out[n]=0;return 1;
    }
  }
  return 0;
}
static void mock_handle(SOCKET s) {
  char *buf=malloc(8*1024*1024);size_t have=0,head_end=0,content=0;
  if(!buf) {closesocket(s);return;}
  for(;;) {
    int got=recv(s,buf+have,(int)(8*1024*1024-1-have),0);
    if(got<=0) goto done;
    have+=(size_t)got;buf[have]=0;
    if(!head_end) {
      char *e=strstr(buf,"\r\n\r\n");
      if(e) {
        head_end=(size_t)(e-buf)+4;char len[32];
        if(mock_header(buf,"Content-Length",len,sizeof(len))) content=(size_t)strtoul(len,NULL,10);
      }
    }
    if(head_end && have>=head_end+content) break;
  }
  {
    char method[16]={0},path[600]={0};
    if(sscanf(buf,"%15s %599s",method,path)!=2) goto done;
    LONG delay=mock_delay_ms;if(delay) Sleep((DWORD)delay);
    if(mock_force_count>0 && (mock_force_status!=412 || !strcmp(method,"PUT"))) {
      LONG left=InterlockedDecrement(&mock_force_count);
      if(left>=0) {InterlockedIncrement(&mock_n_forced);mock_send(s,(int)mock_force_status,"Forced","",NULL,0);goto done;}
    }
    if(mock_user[0]) {
      char auth[256]={0},want[256],enc[200];
      char cred[140];snprintf(cred,sizeof(cred),"%s:%s",mock_user,mock_pass);mock_b64(cred,enc);
      snprintf(want,sizeof(want),"Basic %s",enc);
      if(!mock_header(buf,"Authorization",auth,sizeof(auth)) || strcmp(auth,want)) {
        InterlockedIncrement(&mock_n_denied);
        mock_send(s,401,"Unauthorized","WWW-Authenticate: Basic realm=\"mock\"\r\n",NULL,0);goto done;
      }
    }
    EnterCriticalSection(&mock_lock);
    mock_node *n=mock_find(path);
    char match[200]={0},none[200]={0},depth[16]={0};
    mock_header(buf,"If-Match",match,sizeof(match));mock_header(buf,"If-None-Match",none,sizeof(none));mock_header(buf,"Depth",depth,sizeof(depth));
    char etag[64]="";if(n) snprintf(etag,sizeof(etag),"\"%lu\"",n->etag);
    if(!strcmp(method,"PROPFIND")) {
      InterlockedIncrement(&mock_n_propfind);
      if(!n || !n->collection) mock_send(s,404,"Not Found","",NULL,0);
      else {
        cv_text xml={0};cv_text_string(&xml,"<?xml version=\"1.0\"?><D:multistatus xmlns:D=\"DAV:\">");
        cv_text_format(&xml,"<D:response><D:href>%s</D:href><D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>",n->path);
        if(strcmp(depth,"0")) for(int i=0;i<mock_node_count;i++) {
          const char *p=mock_nodes[i].path;size_t pl=strlen(n->path);
          if(strncmp(p,n->path,pl) || !p[pl]) continue;
          const char *rest=p+pl;const char *slash=strchr(rest,'/');
          if(slash && slash[1]) continue; /* depth 1 only */
          cv_text_format(&xml,"<D:response><D:href>%s</D:href><D:propstat><D:prop>%s</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>",
            p,mock_nodes[i].collection ? "<D:resourcetype><D:collection/></D:resourcetype>":"<D:resourcetype/>");
        }
        cv_text_string(&xml,"</D:multistatus>");
        mock_send(s,207,"Multi-Status","Content-Type: application/xml\r\n",xml.data,xml.size);cv_text_free(&xml);
      }
    } else if(!strcmp(method,"GET")) {
      InterlockedIncrement(&mock_n_get);
      if(!n || n->collection) mock_send(s,404,"Not Found","",NULL,0);
      else {char extra[96];snprintf(extra,sizeof(extra),"ETag: %s\r\nContent-Type: application/json\r\n",etag);mock_send(s,200,"OK",extra,n->data,n->size);}
    } else if(!strcmp(method,"MKCOL")) {
      InterlockedIncrement(&mock_n_mkcol);
      char parent[600];snprintf(parent,sizeof(parent),"%s",path);size_t pl=strlen(parent);
      if(pl>1 && parent[pl-1]=='/') parent[--pl]=0;
      char *cut=strrchr(parent,'/');if(cut) cut[1]=0;
      if(n) mock_send(s,405,"Method Not Allowed","",NULL,0);
      else if(!mock_find(parent)) mock_send(s,409,"Conflict","",NULL,0);
      else {mock_put_node(path,1,NULL,0);mock_send(s,201,"Created","",NULL,0);}
    } else if(!strcmp(method,"PUT")) {
      InterlockedIncrement(&mock_n_put);
      if(match[0]) InterlockedIncrement(&mock_n_if_match);
      char parent[600];snprintf(parent,sizeof(parent),"%s",path);char *cut=strrchr(parent,'/');if(cut) cut[1]=0;
      if(!mock_find(parent)) mock_send(s,409,"Conflict","",NULL,0);
      else if(none[0] && n) mock_send(s,412,"Precondition Failed","",NULL,0);
      else if(match[0] && (!n || strcmp(match,etag))) mock_send(s,412,"Precondition Failed","",NULL,0);
      else {
        mock_node *w=mock_put_node(path,0,buf+head_end,content);
        if(!w) mock_send(s,507,"Insufficient Storage","",NULL,0);
        else {char extra[64];snprintf(extra,sizeof(extra),"ETag: \"%lu\"\r\n",w->etag);mock_send(s,n ? 204:201,n ? "No Content":"Created",extra,NULL,0);}
      }
    } else mock_send(s,405,"Method Not Allowed","",NULL,0);
    LeaveCriticalSection(&mock_lock);
  }
done:
  free(buf);shutdown(s,SD_BOTH);closesocket(s);
}
static unsigned __stdcall mock_conn(void *arg) {mock_handle((SOCKET)(UINT_PTR)arg);InterlockedDecrement(&mock_active);return 0;}
static unsigned __stdcall mock_accept(void *arg) {
  (void)arg;
  while(mock_running) {
    SOCKET c=accept(mock_listener,NULL,NULL);
    if(c==INVALID_SOCKET) break;
    InterlockedIncrement(&mock_active);
    uintptr_t t=_beginthreadex(NULL,0,mock_conn,(void *)(UINT_PTR)c,0,NULL);
    if(t) CloseHandle((HANDLE)t);else {closesocket(c);InterlockedDecrement(&mock_active);}
  }
  return 0;
}
/* port 0 picks a free port. Returns the bound port, or 0. */
static int mock_start(int port,const char *user,const char *pass) {
  WSADATA wsa;if(WSAStartup(MAKEWORD(2,2),&wsa)) return 0;
  static int once;if(!once){InitializeCriticalSection(&mock_lock);once=1;}
  snprintf(mock_user,sizeof(mock_user),"%s",user ? user:"");snprintf(mock_pass,sizeof(mock_pass),"%s",pass ? pass:"");
  mock_delay_ms=0;mock_force_count=0;
  if(!mock_node_count) mock_reset();
  mock_listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
  struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_port=htons((u_short)port);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
  int yes=1;setsockopt(mock_listener,SOL_SOCKET,SO_REUSEADDR,(const char *)&yes,sizeof(yes));
  if(bind(mock_listener,(struct sockaddr *)&a,sizeof(a)) || listen(mock_listener,16)) {closesocket(mock_listener);mock_listener=INVALID_SOCKET;return 0;}
  int len=sizeof(a);getsockname(mock_listener,(struct sockaddr *)&a,&len);mock_port=ntohs(a.sin_port);
  mock_running=1;mock_thread=(HANDLE)_beginthreadex(NULL,0,mock_accept,NULL,0,NULL);
  return mock_port;
}
/* Closing the listener makes the port refuse connections: a real network failure. */
static void mock_stop(void) {
  mock_running=0;
  if(mock_listener!=INVALID_SOCKET){closesocket(mock_listener);mock_listener=INVALID_SOCKET;}
  if(mock_thread){assert(WaitForSingleObject(mock_thread,5000)==WAIT_OBJECT_0);CloseHandle(mock_thread);mock_thread=NULL;}
  DWORD end=GetTickCount()+10000;
  while(mock_active && (LONG)(end-GetTickCount())>0) Sleep(10);
  assert(!mock_active);
  WSACleanup();
}
