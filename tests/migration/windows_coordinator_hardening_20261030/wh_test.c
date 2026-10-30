/* SPDX-License-Identifier: MIT
 *
 * Installed-consumer checks for the coordinator hardening layer. Every case
 * drives the public API only; the private provider contract is satisfied by a
 * mock that records which calls happened, so the six hardened behaviours can be
 * asserted instead of inferred:
 *   1. the journal has a real state machine (illegal order refused even when the
 *      seal of the forged line is correct);
 *   2. recovery must obtain a fresh exclusive capability (reacquire, never a
 *      reused acquire) and is refused when that cannot be proven;
 *   3. nothing is released before the commit/abort record is durable;
 *   4. a failed append poisons the session permanently;
 *   5. a failed admission record keeps the capability instead of dropping it;
 *   6. UNCERTAIN never degrades into rollback or release.
 * The five gate digests are bound into the manifest line, so a journal checked
 * against different gates is refused.
 *
 * Event numbers of the journal FSM are private to the archive; the planted
 * defect cases use them deliberately and say so.
 */
#include <exr_wh.h>
#include <stdio.h>
#include <string.h>

#ifndef CANDIDATE_SOURCE_SHA
#define CANDIDATE_SOURCE_SHA "0000000000000000000000000000000000000000"
#endif

#define HX64 "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
#define HX40 "0123456789abcdef0123456789abcdef01234567"

static unsigned checks, failures;

static void check(int ok, const char *case_name, const char *what)
{
    checks++;
    if (!ok) { failures++; printf("FAIL %s: %s\n", case_name, what); }
}

/* ---------------- journal builder (forged but correctly sealed) ------------- */

typedef struct {
    char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX];
    size_t n;
    char bind[65];
    char prev[65];
    unsigned seq;
} builder;

static const char *jval(const char *s) { return (s && s[0]) ? s : "-"; }

static int builder_start(builder *b, const wh_binding *bind, const wh_gates *g)
{
    if (!wh_manifest(bind, g, b->lines[0])) return 0;
    b->n = 1;
    wh_sha256_hex(b->lines[0], strlen(b->lines[0]), b->bind);
    memcpy(b->prev, b->bind, sizeof b->prev);
    b->seq = 1;
    return 1;
}

static int builder_event(builder *b, unsigned event, const char *lease,
                         const char *stage, const char *snap, const char *content)
{
    char body[EXR_WH_LINE_MAX];
    char seal[65];
    int k = snprintf(body, sizeof body, "EXRWH2 %u %u %s %s %s %s %s %s",
                     b->seq, event, jval(lease), jval(stage), jval(snap),
                     jval(content), b->prev, b->bind);
    if (k <= 0 || (size_t)k >= EXR_WH_LINE_MAX - 66) return 0;
    if (b->n >= EXR_WH_MAX_JOURNAL) return 0;
    wh_sha256_hex(body, (size_t)k, seal);
    snprintf(b->lines[b->n], EXR_WH_LINE_MAX, "%s %s", body, seal);
    memcpy(b->prev, seal, sizeof b->prev);
    b->seq++;
    b->n++;
    return 1;
}

static size_t view(const builder *b, const char **out)
{
    size_t i;
    for (i = 0; i < b->n; i++) out[i] = b->lines[i];
    return b->n;
}

/* private FSM event numbers, used only to plant defects */
enum { EV_ADMIT_BEGIN = 1, EV_ADMIT_OK = 2, EV_SNAP_BEGIN = 3, EV_SNAP_OK = 4,
       EV_IMPORT_BEGIN = 5, EV_IMPORT_OK = 6, EV_VERIFY_BEGIN = 7,
       EV_VERIFY_OK = 8, EV_PUBLISH_BEGIN = 9, EV_COMMIT = 11 };

/* ---------------- mock provider -------------------------------------------- */

typedef struct {
    int token;
    int acquire_calls, reacquire_calls, release_calls, discard_calls;
    int check_calls, publish_calls, inspect_calls;
    int acquire_step, reacquire_step, release_step;
    int publish_step, publish_value, inspect_step, inspect_value;
    int fail_check;
} mock;

static mock *as_mock(void *ctx) { return (mock *)ctx; }

static wh_step m_acquire(void *ctx, const wh_binding *b, const wh_gates *g, void **cap, char id[49])
{
    mock *m = as_mock(ctx);
    (void)b; (void)g;
    m->acquire_calls++;
    if (m->acquire_step == WH_STEP_FAILED) { *cap = NULL; id[0] = 0; return WH_STEP_FAILED; }
    *cap = &m->token;
    snprintf(id, 49, "%s", HX40 "01234567");
    return m->acquire_step;
}

static wh_step m_reacquire(void *ctx, const wh_binding *b, const wh_gates *g, const char *prior, void **cap, char id[49])
{
    mock *m = as_mock(ctx);
    (void)b; (void)g; (void)prior;
    m->reacquire_calls++;
    if (m->reacquire_step == WH_STEP_FAILED) { *cap = NULL; id[0] = 0; return WH_STEP_FAILED; }
    *cap = &m->token;
    snprintf(id, 49, "%s", HX40 "01234567");
    return m->reacquire_step;
}

static wh_step m_check(void *ctx, void *cap)
{
    mock *m = as_mock(ctx);
    m->check_calls++;
    if (cap != &m->token) return WH_STEP_UNCERTAIN;
    return m->fail_check ? WH_STEP_FAILED : WH_STEP_OK;
}

static wh_step m_snapshot(void *ctx, void *cap, wh_record *rows, size_t max, size_t *n)
{
    mock *m = as_mock(ctx);
    if (cap != &m->token || max < 2) return WH_STEP_UNCERTAIN;
    snprintf(rows[0].id, sizeof rows[0].id, "%048d", 1);
    rows[0].size = 11;
    snprintf(rows[0].sha, sizeof rows[0].sha, "%s", HX64);
    snprintf(rows[0].path, sizeof rows[0].path, "books/a.epub");
    snprintf(rows[1].id, sizeof rows[1].id, "%048d", 2);
    rows[1].size = 22;
    snprintf(rows[1].sha, sizeof rows[1].sha, "%s", HX64);
    snprintf(rows[1].path, sizeof rows[1].path, "books/b.epub");
    *n = 2;
    return WH_STEP_OK;
}

static wh_step m_import(void *ctx, void *cap, const wh_record *rows, size_t n, char stage[49])
{
    mock *m = as_mock(ctx);
    if (cap != &m->token || !rows || n != 2) return WH_STEP_UNCERTAIN;
    snprintf(stage, 49, "%s", HX40 "89abcdef");
    return WH_STEP_OK;
}

static wh_step m_verify(void *ctx, void *cap, const char *stage, const wh_record *rows, size_t n)
{
    mock *m = as_mock(ctx);
    if (cap != &m->token || !stage || !stage[0] || !rows || n != 2) return WH_STEP_UNCERTAIN;
    return WH_STEP_OK;
}

static wh_step m_publish(void *ctx, void *cap, const char *stage, wh_pub *pub)
{
    mock *m = as_mock(ctx);
    if (cap != &m->token || !stage || !stage[0]) { *pub = WH_PUB_UNKNOWN; return WH_STEP_UNCERTAIN; }
    m->publish_calls++;
    *pub = (wh_pub)m->publish_value;
    return (wh_step)m->publish_step;
}

static wh_step m_inspect(void *ctx, void *cap, const char *stage, const char *content, wh_pub *pub)
{
    mock *m = as_mock(ctx);
    if (cap != &m->token) { *pub = WH_PUB_UNKNOWN; return WH_STEP_UNCERTAIN; }
    (void)stage; (void)content;
    m->inspect_calls++;
    *pub = (wh_pub)m->inspect_value;
    return (wh_step)m->inspect_step;
}

static wh_step m_discard(void *ctx, void *cap, const char *stage)
{
    mock *m = as_mock(ctx);
    if (cap != &m->token || !stage || !stage[0]) return WH_STEP_UNCERTAIN;
    m->discard_calls++;
    return WH_STEP_OK;
}

static wh_step m_release(void *ctx, void *cap)
{
    mock *m = as_mock(ctx);
    if (cap != &m->token) return WH_STEP_UNCERTAIN;
    m->release_calls++;
    return (wh_step)m->release_step;
}

static void mock_init(mock *m)
{
    memset(m, 0, sizeof *m);
    m->acquire_step = WH_STEP_OK;
    m->reacquire_step = WH_STEP_OK;
    m->release_step = WH_STEP_OK;
    m->publish_step = WH_STEP_OK;
    m->publish_value = WH_PUB_YES;
    m->inspect_step = WH_STEP_OK;
    m->inspect_value = WH_PUB_YES;
}

static void provider_of(wh_provider *p, mock *m)
{
    memset(p, 0, sizeof *p);
    p->abi = EXR_WH_ABI;
    p->identity_sha = HX64;
    p->context = m;
    p->acquire = m_acquire;
    p->reacquire = m_reacquire;
    p->check = m_check;
    p->snapshot = m_snapshot;
    p->import_rows = m_import;
    p->verify = m_verify;
    p->publish = m_publish;
    p->inspect = m_inspect;
    p->discard = m_discard;
    p->release = m_release;
}

/* ---------------- sink ------------------------------------------------------ */

typedef struct {
    builder b;
    size_t calls;
    long fail_at; /* 1-based call index that fails, 0 = never */
} sink_state;

static int sink_append(void *ctx, const char *line)
{
    sink_state *s = (sink_state *)ctx;
    s->calls++;
    if (s->fail_at > 0 && s->calls == (size_t)s->fail_at) return 1;
    if (s->b.n >= EXR_WH_MAX_JOURNAL) return 1;
    snprintf(s->b.lines[s->b.n], EXR_WH_LINE_MAX, "%s", line);
    memcpy(s->b.prev, line + strlen(line) - 64, 65);
    s->b.seq++;
    s->b.n++;
    return 0;
}

/* ---------------- fixtures ------------------------------------------------- */

static sink_state recovery_sink;

static wh_binding binding_of(void)
{
    wh_binding b;
    memset(&b, 0, sizeof b);
    snprintf(b.source, sizeof b.source, "%s", HX40);
    snprintf(b.run, sizeof b.run, "%s", "4100000000");
    snprintf(b.attempt, sizeof b.attempt, "%s", "1");
    snprintf(b.artifact, sizeof b.artifact, "%s", HX64);
    snprintf(b.platform, sizeof b.platform, "%s", "ubuntu-22.04");
    snprintf(b.sdk, sizeof b.sdk, "%s", "3.42.0");
    snprintf(b.provider, sizeof b.provider, "%s", HX64);
    return b;
}

static wh_gates gates_of(char digit)
{
    wh_gates g;
    memset(&g, 0, sizeof g);
    memset(g.admission, digit, 64); g.admission[64] = 0;
    memset(g.publisher, digit, 64); g.publisher[64] = 0;
    memset(g.recovery, digit, 64); g.recovery[64] = 0;
    memset(g.observer, digit, 64); g.observer[64] = 0;
    memset(g.fault, digit, 64); g.fault[64] = 0;
    return g;
}

/* ---------------- cases ---------------------------------------------------- */

static void case_binding(void)
{
    wh_binding b = binding_of();
    wh_gates g = gates_of('a');
    char line[EXR_WH_LINE_MAX];
    wh_binding bad = b;
    check(wh_binding_valid(&b) == 1, "binding", "valid binding rejected");
    check(wh_manifest(&b, &g, line) == 1, "binding", "manifest refused");
    check(strstr(line, "|admission=") && strstr(line, "|publisher=") && strstr(line, "|recovery=") &&
          strstr(line, "|observer=") && strstr(line, "|fault="), "binding", "five gates not bound into the manifest");
    memcpy(bad.source, "ABCDEF", 6);
    check(wh_binding_valid(&bad) == 0, "binding", "uppercase source accepted");
    g.fault[63] = 'z';
    check(wh_manifest(&b, &g, line) == 0, "binding", "non-hex gate accepted");
    check(strcmp(wh_status_name(WH_UNCERTAIN), "uncertain") == 0, "binding", "status name");
}

static void case_positive(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n;
    mock_init(&m); provider_of(&p, &m);
    memset(&s, 0, sizeof s);
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "positive", "session not created");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_COMPLETED, "positive", "run did not complete");
    check(m.release_calls == 1, "positive", "release not called exactly once");
    check(m.acquire_calls == 1 && m.reacquire_calls == 0, "positive", "wrong acquisition path");
    n = view(&s.b, ptrs);
    check(wh_journal_check(&b, &g, ptrs, n) == 1, "positive", "own journal rejected");
    check(wh_dispose(sess) == 1, "positive", "dispose refused a clean session");
}

static void case_illegal_transition(void)
{
    wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n;
    /* correctly sealed line, illegal order: COMMIT straight after START */
    check(builder_start(&j, &b, &g) == 1, "illegal-transition", "manifest");
    check(builder_event(&j, EV_COMMIT, NULL, NULL, NULL, NULL) == 1, "illegal-transition", "line");
    n = view(&j, ptrs);
    check(wh_journal_check(&b, &g, ptrs, n) == 0, "illegal-transition", "out-of-order but sealed journal accepted");
    /* legal order is accepted, so the refusal above is about order, not format */
    check(builder_start(&j, &b, &g) == 1, "illegal-transition", "manifest2");
    check(builder_event(&j, EV_ADMIT_BEGIN, NULL, NULL, NULL, NULL) == 1, "illegal-transition", "line2");
    n = view(&j, ptrs);
    check(wh_journal_check(&b, &g, ptrs, n) == 1, "illegal-transition", "legal prefix rejected");
}

static void case_gate_binding(void)
{
    wh_binding b = binding_of(); wh_gates g = gates_of('a'), other = gates_of('b');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n;
    check(builder_start(&j, &b, &g) == 1, "gate-binding", "manifest");
    check(builder_event(&j, EV_ADMIT_BEGIN, NULL, NULL, NULL, NULL) == 1, "gate-binding", "line");
    n = view(&j, ptrs);
    check(wh_journal_check(&b, &g, ptrs, n) == 1, "gate-binding", "same gates rejected");
    check(wh_journal_check(&b, &other, ptrs, n) == 0, "gate-binding", "journal accepted under different gates");
}

static void case_tampered_seal(void)
{
    wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n;
    check(builder_start(&j, &b, &g) == 1, "tampered-seal", "manifest");
    check(builder_event(&j, EV_ADMIT_BEGIN, NULL, NULL, NULL, NULL) == 1, "tampered-seal", "line");
    j.lines[j.n - 1][strlen(j.lines[j.n - 1]) - 1] ^= 0x1;
    n = view(&j, ptrs);
    check(wh_journal_check(&b, &g, ptrs, n) == 0, "tampered-seal", "tampered seal accepted");
}

static void case_sink_poison(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    memset(&s, 0, sizeof s); s.fail_at = 5;
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "sink-poison", "session");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_UNCERTAIN, "sink-poison", "sink failure did not end UNCERTAIN");
    check(r.live_lease == 1, "sink-poison", "capability not retained");
    check(m.release_calls == 0, "sink-poison", "released after a failed append");
    check(wh_dispose(sess) == 0, "sink-poison", "poisoned session was freed");
}

static void case_admission_journal_failure(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    memset(&s, 0, sizeof s);
    s.fail_at = 3; /* 1 manifest, 2 admit-intent, 3 admission record */
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "admission-record", "session");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_UNCERTAIN, "admission-record", "status");
    check(r.live_lease == 1, "admission-record", "lease identity dropped with the failed record");
    check(m.release_calls == 0, "admission-record", "released without an admission record");
}

static void case_publish_uncertain(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    m.publish_step = WH_STEP_UNCERTAIN; m.publish_value = WH_PUB_UNKNOWN;
    memset(&s, 0, sizeof s);
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "publish-uncertain", "session");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_UNCERTAIN, "publish-uncertain", "status");
    check(m.release_calls == 0 && m.discard_calls == 0, "publish-uncertain", "UNCERTAIN degraded into rollback/release");
    check(r.live_lease == 1, "publish-uncertain", "capability not retained");
}

static void case_publish_no(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    m.publish_value = WH_PUB_NO;
    memset(&s, 0, sizeof s);
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "publish-no", "session");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_ROLLED_BACK, "publish-no", "status");
    check(m.discard_calls == 1 && m.release_calls == 1, "publish-no", "known abort did not discard then release");
}

static void case_acquire_failed(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    m.acquire_step = WH_STEP_FAILED;
    memset(&s, 0, sizeof s);
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "acquire-failed", "session");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_REFUSED, "acquire-failed", "status");
    check(r.live_lease == 0 && m.release_calls == 0, "acquire-failed", "refusal invented a capability");
    check(wh_dispose(sess) == 1, "acquire-failed", "clean refusal could not be freed");
}

static void case_acquire_uncertain(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static sink_state s; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    m.acquire_step = WH_STEP_UNCERTAIN;
    memset(&s, 0, sizeof s);
    sess = wh_create(&b, &g, &p, sink_append, &s);
    check(sess != NULL, "acquire-uncertain", "session");
    if (!sess) return;
    check(wh_run(sess, &r) == WH_UNCERTAIN, "acquire-uncertain", "status");
    check(m.release_calls == 0, "acquire-uncertain", "released an uncertain capability");
}

static void build_to_publish(const wh_binding *b, const wh_gates *g, builder *j, int with_intent)
{
    builder_start(j, b, g);
    builder_event(j, EV_ADMIT_BEGIN, NULL, NULL, NULL, NULL);
    builder_event(j, EV_ADMIT_OK, HX40 "01234567", NULL, NULL, NULL);
    builder_event(j, EV_SNAP_BEGIN, NULL, NULL, NULL, NULL);
    builder_event(j, EV_SNAP_OK, NULL, NULL, HX64, NULL);
    builder_event(j, EV_IMPORT_BEGIN, NULL, NULL, NULL, HX64);
    builder_event(j, EV_IMPORT_OK, NULL, HX40 "89abcdef", NULL, NULL);
    builder_event(j, EV_VERIFY_BEGIN, NULL, NULL, NULL, NULL);
    builder_event(j, EV_VERIFY_OK, NULL, NULL, NULL, NULL);
    if (with_intent) builder_event(j, EV_PUBLISH_BEGIN, NULL, NULL, NULL, NULL);
}

static void case_recover_yes(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    build_to_publish(&b, &g, &j, 1);
    n = view(&j, ptrs);
    memset(&recovery_sink, 0, sizeof recovery_sink);
    sess = wh_create(&b, &g, &p, sink_append, &recovery_sink);
    check(sess != NULL, "recover-yes", "session");
    if (!sess) return;
    check(wh_recover(sess, ptrs, n, &r) == WH_COMPLETED, "recover-yes", "status");
    check(m.reacquire_calls == 1 && m.acquire_calls == 0, "recover-yes", "recovery did not take fresh exclusive custody");
    check(m.release_calls == 1, "recover-yes", "release count");
}

static void case_recover_yes_without_intent(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    build_to_publish(&b, &g, &j, 0);
    n = view(&j, ptrs);
    memset(&recovery_sink, 0, sizeof recovery_sink);
    sess = wh_create(&b, &g, &p, sink_append, &recovery_sink);
    check(sess != NULL, "recover-no-intent", "session");
    if (!sess) return;
    check(wh_recover(sess, ptrs, n, &r) == WH_UNCERTAIN, "recover-no-intent", "publication accepted without a recorded intent");
    check(m.release_calls == 0, "recover-no-intent", "released on contradiction");
}

static void case_recover_no(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    build_to_publish(&b, &g, &j, 0);
    n = view(&j, ptrs);
    m.inspect_value = WH_PUB_NO;
    memset(&recovery_sink, 0, sizeof recovery_sink);
    sess = wh_create(&b, &g, &p, sink_append, &recovery_sink);
    check(sess != NULL, "recover-no", "session");
    if (!sess) return;
    check(wh_recover(sess, ptrs, n, &r) == WH_ROLLED_BACK, "recover-no", "status");
    check(m.discard_calls == 1 && m.release_calls == 1, "recover-no", "known abort path");
}

static void case_recover_reacquire_failed(void)
{
    mock m; wh_provider p; wh_binding b = binding_of(); wh_gates g = gates_of('a');
    static builder j; const char *ptrs[EXR_WH_MAX_JOURNAL]; size_t n; wh_session *sess; wh_report r;
    mock_init(&m); provider_of(&p, &m);
    m.reacquire_step = WH_STEP_FAILED;
    build_to_publish(&b, &g, &j, 1);
    n = view(&j, ptrs);
    memset(&recovery_sink, 0, sizeof recovery_sink);
    sess = wh_create(&b, &g, &p, sink_append, &recovery_sink);
    check(sess != NULL, "recover-failed", "session");
    if (!sess) return;
    check(wh_recover(sess, ptrs, n, &r) == WH_REFUSED, "recover-failed", "status");
    check(m.release_calls == 0 && r.live_lease == 0, "recover-failed", "refused recovery released something");
}

int main(void)
{
    case_binding();
    case_positive();
    case_illegal_transition();
    case_gate_binding();
    case_tampered_seal();
    case_sink_poison();
    case_admission_journal_failure();
    case_publish_uncertain();
    case_publish_no();
    case_acquire_failed();
    case_acquire_uncertain();
    case_recover_yes();
    case_recover_yes_without_intent();
    case_recover_no();
    case_recover_reacquire_failed();
    printf("{\"source\":\"%s\",\"checks\":%u,\"failed\":%u,\"passed\":%s}\n",
           CANDIDATE_SOURCE_SHA, checks, failures, failures ? "false" : "true");
    return failures ? 1 : 0;
}
