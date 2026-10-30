/* SPDX-License-Identifier: MIT
 * Test-helper reuse only. Legacy main is NOT run by this executable.
 * CI separately executes the unchanged ABI2 81-check executable.
 * The backend below is in-memory contract evidence, never native durability. */
#define main wh3_legacy_main_not_run
#include "../windows_coordinator_hardening_20261030/wh_test.c"
#undef main
#include <exr_wh3.h>

typedef struct {
    builder journal;
    mock owner;
    wh_provider provider;
    wh_binding binding;
    wh_gates gates;
    unsigned calls,writes;
    int revoke,mutate,fail_before,fail_after,bad_receipt;
} tx_fixture;
static tx_fixture tx;

static void actual_tip(const builder *b,wh3_tip *tip)
{
    char manifest[EXR_WH_LINE_MAX];
    memset(tip,0,sizeof(*tip));
    (void)wh_manifest(&tx.binding,&tx.gates,manifest);
    wh_sha256_hex(manifest,strlen(manifest),tip->manifest_sha);
    tip->line_count=b->n;
    if (b->n) {
        wh_sha256_hex(b->lines[0],strlen(b->lines[0]),tip->manifest_sha);
        wh_sha256_hex(b->lines[b->n-1],strlen(b->lines[b->n-1]),tip->last_line_sha);
    } else { memset(tip->last_line_sha,'0',64); tip->last_line_sha[64]=0; }
}
static int tip_same(const wh3_tip *a,const wh3_tip *b)
{
    return a->line_count==b->line_count
        && !memcmp(a->manifest_sha,b->manifest_sha,65)
        && !memcmp(a->last_line_sha,b->last_line_sha,65);
}
static wh3_tx_status memory_transaction(void *context,void *cap,const wh3_tip *expected,
                                       const char *line,wh3_tip *after)
{
    tx_fixture *f=context;
    wh3_tip observed;
    const char *p[EXR_WH_MAX_JOURNAL];
    size_t i;
    f->calls++;
    /* Faults occur inside this synthetic transaction, before actual validation. */
    if (f->revoke) f->owner.fail_check=1;
    if (f->mutate && f->journal.n) f->journal.lines[f->journal.n-1][10]^=1;
    if (cap!=&f->owner.token || f->owner.fail_check) return WH3_TX_MISMATCH;
    if (f->fail_before) return WH3_TX_UNCERTAIN;
    actual_tip(&f->journal,&observed);
    if (!tip_same(expected,&observed)) return WH3_TX_MISMATCH;
    for (i=0;i<f->journal.n;i++) p[i]=f->journal.lines[i];
    if (f->journal.n && !wh_journal_check(&f->binding,&f->gates,p,f->journal.n))
        return WH3_TX_MISMATCH;
    if (f->journal.n>=EXR_WH_MAX_JOURNAL) return WH3_TX_MISMATCH;
    p[f->journal.n]=line;
    if (!wh_journal_check(&f->binding,&f->gates,p,f->journal.n+1))
        return WH3_TX_MISMATCH;
    snprintf(f->journal.lines[f->journal.n],EXR_WH_LINE_MAX,"%s",line);
    f->journal.n++; f->writes++;
    if (f->fail_after) return WH3_TX_UNCERTAIN;
    actual_tip(&f->journal,after);
    if (f->bad_receipt) after->line_count++;
    return WH3_TX_OK;
}
static void fixture(void)
{
    memset(&tx,0,sizeof(tx));
    mock_init(&tx.owner); provider_of(&tx.provider,&tx.owner);
    tx.binding=binding_of(); tx.gates=gates_of('a');
}
static wh3_session *session3(const char *label)
{
    wh3_backend backend={EXR_WH3_ABI,&tx,memory_transaction};
    wh3_session *s=wh3_create(&tx.binding,&tx.gates,&tx.provider,&backend);
    check(s!=NULL,label,"create");
    return s;
}
static void rejected3(wh3_session *s,wh_status st,wh_report *r,const char *label)
{
    check(st==WH_UNCERTAIN,label,diag(st,r));
    check(tx.writes==0,label,"mismatch appended");
    check(tx.owner.inspect_calls==0 && tx.owner.discard_calls==0
          && tx.owner.release_calls==0 && r->live_lease==1 && wh3_dispose(s)==0,
          label,"mismatch lost custody or permitted downstream effects");
}
static void new_run(void)
{
    wh3_session *s; wh_report r; const char *p[EXR_WH_MAX_JOURNAL];
    fixture(); s=session3("new-run"); if(!s)return;
    check(wh3_run(s,&r)==WH_COMPLETED,"new-run",r.detail);
    check(wh_journal_check(&tx.binding,&tx.gates,p,view(&tx.journal,p))==1,
          "new-run","actual chain invalid");
    check(tx.owner.release_calls==1 && wh3_dispose(s)==1,"new-run","release/dispose");
}
static void matched_recovery(int yes)
{
    wh3_session *s; wh_report r; static builder supplied;
    const char *p[EXR_WH_MAX_JOURNAL]; size_t n;
    const char *label=yes?"matched-yes":"matched-no";
    fixture(); build_to_publish(&tx.binding,&tx.gates,&supplied,yes);
    tx.journal=supplied; n=view(&supplied,p); tx.owner.inspect_value=yes?WH_PUB_YES:WH_PUB_NO;
    s=session3(label); if(!s)return;
    check(wh3_recover(s,p,n,&r)==(yes?WH_COMPLETED:WH_ROLLED_BACK),label,r.detail);
    check(tx.owner.inspect_calls==1 && tx.owner.discard_calls==(yes?0:1),label,"inspect/discard");
    check(tx.owner.release_calls==1 && wh3_dispose(s)==1,label,"release/dispose");
}
static void mismatch_recovery(unsigned mode,const char *label)
{
    wh3_session *s; wh_report r; static builder supplied;
    const char *p[EXR_WH_MAX_JOURNAL]; size_t n; wh_status st;
    fixture(); build_to_publish(&tx.binding,&tx.gates,&supplied,1);
    tx.journal=supplied; n=view(&supplied,p);
    if(mode==0) memset(&tx.journal,0,sizeof(tx.journal)); /* absent */
    if(mode==1) n--; /* caller's valid prefix is older than actual store */
    if(mode==2) tx.journal.lines[0][8]^=1; /* wrong manifest */
    if(mode==3) tx.journal.lines[tx.journal.n-1][10]^=1; /* changed tail */
    if(mode==4) tx.journal.lines[1][10]^=1; /* same count+tail, corrupt interior */
    if(mode==5) tx.revoke=1; /* invalidated after acquire check, before CAS */
    if(mode==6) tx.mutate=1; /* actual store changes inside transaction boundary */
    s=session3(label); if(!s)return;
    st=wh3_recover(s,p,n,&r); rejected3(s,st,&r,label);
}
static void append_failure(unsigned mode,const char *label)
{
    wh3_session *s; wh_report r; wh_status st;
    fixture();
    tx.fail_before=mode==0; tx.fail_after=mode==1; tx.bad_receipt=mode==2;
    s=session3(label); if(!s)return;
    st=wh3_run(s,&r);
    check(st==WH_UNCERTAIN,label,diag(st,&r));
    check(tx.writes==(mode==0?0u:1u),label,"unexpected write count");
    check(tx.owner.release_calls==0 && r.live_lease==1
          && wh3_last_transaction(s)==WH3_TX_UNCERTAIN && wh3_dispose(s)==0,
          label,"failed transaction lost custody/poison");
}
static void busy3(void)
{
    wh3_session *s; wh_report r;
    fixture(); tx.owner.acquire_step=WH_STEP_FAILED;
    s=session3("busy"); if(!s)return;
    check(wh3_run(s,&r)==WH_REFUSED,"busy",r.detail);
    check(tx.calls==0 && tx.writes==0,"busy","journal called before acquire");
    check(tx.owner.release_calls==0 && wh3_dispose(s)==1,"busy","release/dispose");
}
static void expire3(void)
{
    wh3_session *s; wh_report r;
    fixture(); tx.owner.expire_after_publish=1;
    s=session3("publish-expired"); if(!s)return;
    check(wh3_run(s,&r)==WH_UNCERTAIN,"publish-expired",r.detail);
    check(!journal_has_event(&tx.journal,11u) && !journal_has_event(&tx.journal,12u),
          "publish-expired","terminal after expiry");
    check(tx.owner.release_calls==0 && r.live_lease==1 && wh3_dispose(s)==0,
          "publish-expired","custody");
}
static void nonempty_start(void)
{
    wh3_session *s; wh_report r; wh_status st;
    fixture(); build_to_publish(&tx.binding,&tx.gates,&tx.journal,1);
    s=session3("nonempty-start"); if(!s)return;
    st=wh3_run(s,&r); rejected3(s,st,&r,"nonempty-start");
}
int main(void)
{
    checks=0; failures=0;
    new_run(); matched_recovery(1); matched_recovery(0);
    mismatch_recovery(0,"absent"); mismatch_recovery(1,"advanced-prefix");
    mismatch_recovery(2,"wrong-manifest"); mismatch_recovery(3,"changed-tail");
    mismatch_recovery(4,"interior-corruption"); mismatch_recovery(5,"cap-revoked");
    mismatch_recovery(6,"preappend-mutation");
    append_failure(1,"post-write-uncertain"); append_failure(2,"bogus-readback-tip");
    busy3(); expire3(); append_failure(0,"first-manifest-failure"); nonempty_start();
    printf("{\"source\":\"%s\",\"cases\":16,\"checks\":%u,\"failed\":%u,\"passed\":%s,\"native_durability\":false}\n",
           CANDIDATE_SOURCE_SHA,checks,failures,failures?"false":"true");
    return failures?1:0;
}
