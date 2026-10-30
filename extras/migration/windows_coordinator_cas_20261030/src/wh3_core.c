/* SPDX-License-Identifier: MIT */
#include "exr_wh3.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
struct wh3_session {
    wh_binding binding;
    wh_gates gates;
    wh_provider original;
    wh3_backend backend;
    wh_session *core;
    void *cap;
    wh3_tip expected;
    wh3_tx_status last;
    int used;
};
static int equal_tip(const wh3_tip *a,const wh3_tip *b)
{
    return a->line_count==b->line_count
        && !memcmp(a->manifest_sha,b->manifest_sha,65)
        && !memcmp(a->last_line_sha,b->last_line_sha,65);
}
static wh_status refused(wh_report *r,const char *why)
{
    if (!r) return WH_INTERNAL;
    memset(r,0,sizeof(*r)); r->status=WH_REFUSED;
    snprintf(r->detail,sizeof(r->detail),"%s",why);
    return WH_REFUSED;
}
static wh_step acquire3(void *v,const wh_binding *b,const wh_gates *g,void **cap,char id[49])
{
    wh3_session *s=v;
    wh_step st=s->original.acquire(s->original.context,b,g,cap,id);
    s->cap=*cap;
    return st;
}
static wh_step reacquire3(void *v,const wh_binding *b,const wh_gates *g,const char *prior,void **cap,char id[49])
{
    wh3_session *s=v;
    wh_step st=s->original.reacquire(s->original.context,b,g,prior,cap,id);
    s->cap=*cap;
    return st;
}
static wh_step check3(void *v,void *cap)
{
    wh3_session *s=v;
    if (!cap || cap!=s->cap) return WH_STEP_UNCERTAIN;
    return s->original.check(s->original.context,cap);
}
static wh_step snapshot3(void *v,void *cap,wh_record *rows,size_t max,size_t *n)
{
    wh3_session *s=v;
    return s->original.snapshot(s->original.context,cap,rows,max,n);
}
static wh_step import3(void *v,void *cap,const wh_record *rows,size_t n,char stage[49])
{
    wh3_session *s=v;
    return s->original.import_rows(s->original.context,cap,rows,n,stage);
}
static wh_step verify3(void *v,void *cap,const char *stage,const wh_record *rows,size_t n)
{
    wh3_session *s=v;
    return s->original.verify(s->original.context,cap,stage,rows,n);
}
static wh_step publish3(void *v,void *cap,const char *stage,wh_pub *pub)
{
    wh3_session *s=v;
    return s->original.publish(s->original.context,cap,stage,pub);
}
static wh_step inspect3(void *v,void *cap,const char *stage,const char *content,wh_pub *pub)
{
    wh3_session *s=v;
    return s->original.inspect(s->original.context,cap,stage,content,pub);
}
static wh_step discard3(void *v,void *cap,const char *stage)
{
    wh3_session *s=v;
    return s->original.discard(s->original.context,cap,stage);
}
static wh_step release3(void *v,void *cap)
{
    wh3_session *s=v;
    wh_step st=s->original.release(s->original.context,cap);
    if (st==WH_STEP_OK) s->cap=NULL;
    return st;
}
static int append3(void *v,const char *line)
{
    wh3_session *s=v;
    wh3_tip actual,desired=s->expected;
    if (!s->cap || s->expected.line_count>=EXR_WH_MAX_JOURNAL) {
        s->last=WH3_TX_UNCERTAIN; return 1;
    }
    memset(&actual,0,sizeof(actual));
    desired.line_count++;
    wh_sha256_hex(line,strlen(line),desired.last_line_sha);
    s->last=s->backend.append(s->backend.context,s->cap,&s->expected,line,&actual);
    if (s->last!=WH3_TX_OK) return 1;
    if (!equal_tip(&actual,&desired)) { s->last=WH3_TX_UNCERTAIN; return 1; }
    s->expected=actual;
    return 0;
}
wh3_session *wh3_create(const wh_binding *b,const wh_gates *g,const wh_provider *p,
                       const wh3_backend *backend)
{
    wh3_session *s; wh_provider wrapped; char manifest[EXR_WH_LINE_MAX];
    if (!b || !g || !p || !backend || !wh_manifest(b,g,manifest)) return NULL;
    if (backend->abi!=EXR_WH3_ABI || !backend->append
        || p->abi!=EXR_WH_ABI || !p->identity_sha || strcmp(p->identity_sha,b->provider)
        || !p->acquire || !p->reacquire || !p->check || !p->snapshot
        || !p->import_rows || !p->verify || !p->publish || !p->inspect
        || !p->discard || !p->release) return NULL;
    s=calloc(1,sizeof(*s));
    if (!s) return NULL;
    s->binding=*b; s->gates=*g; s->original=*p; s->backend=*backend;
    s->last=WH3_TX_UNCERTAIN;
    wh_sha256_hex(manifest,strlen(manifest),s->expected.manifest_sha);
    memset(s->expected.last_line_sha,'0',64); s->expected.last_line_sha[64]=0;
    wrapped=*p; wrapped.context=s;
    wrapped.acquire=acquire3; wrapped.reacquire=reacquire3; wrapped.check=check3;
    wrapped.snapshot=snapshot3; wrapped.import_rows=import3; wrapped.verify=verify3;
    wrapped.publish=publish3; wrapped.inspect=inspect3; wrapped.discard=discard3;
    wrapped.release=release3;
    s->core=wh_create(b,g,&wrapped,append3,s);
    if (!s->core) { free(s); return NULL; }
    return s;
}
wh_status wh3_run(wh3_session *s,wh_report *r)
{
    if (!s || !r) return WH_INTERNAL;
    if (s->used) return wh_run(s->core,r);
    s->used=1;
    return wh_run(s->core,r);
}
wh_status wh3_recover(wh3_session *s,const char *const *lines,size_t n,wh_report *r)
{
    if (!s || !r) return WH_INTERNAL;
    if (s->used) return wh_recover(s->core,lines,n,r);
    if (!wh_journal_check(&s->binding,&s->gates,lines,n))
        return refused(r,"ABI3-supplied-prefix-invalid");
    s->expected.line_count=n;
    wh_sha256_hex(lines[n-1],strlen(lines[n-1]),s->expected.last_line_sha);
    s->used=1;
    return wh_recover(s->core,lines,n,r);
}
wh3_tx_status wh3_last_transaction(const wh3_session *s)
{
    return s?s->last:WH3_TX_UNCERTAIN;
}
int wh3_dispose(wh3_session *s)
{
    if (!s) return 1;
    if (!wh_dispose(s->core)) return 0;
    free(s); return 1;
}
