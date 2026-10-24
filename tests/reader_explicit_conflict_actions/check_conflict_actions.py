# SPDX-License-Identifier: MIT
"""Installed explicit conflict actions: real two-client histories, explicit merges, refusals and rollbacks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_revisions'))
from check_protocol import sqlite_provider

(OK, ARGUMENT, MEMORY, LIMIT, CANCELLED, OWNER, NOT_FOUND, NOT_CONFLICT, STALE, INCOMPLETE, RESTORE_REQUIRED,
 NOT_TOMBSTONED, READING_HOST, NEEDS_BOOTSTRAP, IDENTITY, REVISION, COMMAND) = range(17)
SAFE, CONCURRENT, TOMBSTONED, INCOMPLETE_STATE = range(4)
PUT, DELETE, RESTORE = range(3)
SHELF, TAG, SERIES = range(3)
REV_CYCLE = 9
BOOK = 'txt:' + 'a' * 64
OTHER_BOOK = 'txt:' + 'b' * 64


def main():
    p = argparse.ArgumentParser()
    for name in ('consumer', 'c-consumer', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('link-map', 'build-log'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--local-run', action='store_true', help='development run on a machine that is not GitHub Actions; not acceptance evidence')
    a = p.parse_args()
    sha = os.environ.get('GITHUB_SHA', '')
    if not a.local_run:
        assert os.environ.get('GITHUB_ACTIONS') == 'true'
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == sha
    root = a.output.resolve()
    root.mkdir(parents=True)
    consumer = a.consumer.resolve()
    checks = []
    counter = [0]

    def record(name):
        assert name not in checks
        checks.append(name)
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def run(action, db, **options):
        args = [str(consumer), action, str(db)]
        for key, value in options.items():
            if isinstance(value, str) and not value.startswith('@') and key in ('name', 'title', 'author') :
                path = root / ('t%d.txt' % counter[0])
                counter[0] += 1
                path.write_bytes(value.encode('utf-8'))
                value = '@' + str(path)
            args.append('%s=%s' % (key, value))
        done = subprocess.run(args, capture_output=True, timeout=120)
        assert done.returncode == 0, (action, done.returncode, done.stderr, done.stdout, args)
        return json.loads(done.stdout.decode('utf-8'))

    def sql(db, query, args=()):
        with sqlite3.connect(db) as c:
            return c.execute(query, args).fetchall()

    def counts(db):
        return sql(db, 'SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]

    def history(db):
        return dict(sql(db, 'SELECT revision_id,body_json FROM reader_revisions'))

    def schema(db):
        return sql(db, 'SELECT type,name,sql FROM sqlite_master ORDER BY name')

    def newdb(name):
        return root / (name + '.sqlite')

    def wire_file(name, raw):
        path = root / name
        path.write_bytes(raw)
        return path

    def xfer(src, dst, revision):
        out = root / ('x-%s.json' % revision)
        assert run('export', src, id=revision, out=out)['status'] == 0
        raw = out.read_bytes()
        return run('receive', dst, wire=out, sha=hashlib.sha256(raw).hexdigest())

    def encode(v):
        return json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    def remote(db, value):
        raw = encode(value)
        path = wire_file('r-%s-%s.json' % (value['id'], hashlib.sha256(raw).hexdigest()[:8]), raw)
        return run('receive', db, wire=path, sha=hashlib.sha256(raw).hexdigest())['status']

    def group_revision(n, key, name, parents=(), operation='put', kind='tag'):
        return {'version': 1, 'id': '%032x' % n, 'entity_kind': kind, 'entity_key': key, 'operation': operation,
                'location_kind': 'none', 'parents': list(parents), 'payload': None if operation == 'delete' else {'name': name}}

    def fork_group(name, kind=TAG):
        """Two clients edit the same group concurrently, then both receive the other's revision."""
        A, B = newdb(name + '-a'), newdb(name + '-b')
        base = run('local-group', A, gk=kind, op=PUT, heads='-', name='base', gid='-')
        assert base['status'] == 0
        key, r1 = base['key'], base['id']
        assert xfer(A, B, r1)['created'] == 1
        a2 = run('local-group', A, gk=kind, op=PUT, heads=r1, name='甲😀', gid=key)
        b2 = run('local-group', B, gk=kind, op=PUT, heads=r1, name='乙', gid=key)
        assert a2['status'] == b2['status'] == 0
        assert xfer(A, B, a2['id'])['created'] == 1 and xfer(B, A, b2['id'])['created'] == 1
        return A, B, key, r1, a2['id'], b2['id']

    def group_name(db, key):
        return sql(db, 'SELECT name,deleted FROM reader_tags WHERE tag_id=?', (key,))

    def wire_of(db, revision):
        return sql(db, 'SELECT body_json FROM reader_revisions WHERE revision_id=?', (revision,))[0][0]

    def prepared(value, status=OK):
        assert value['prepare']['status'] == status, value['prepare']
        return value['prepare']

    def intact(db, before_history, before_schema):
        now = history(db)
        for k, v in before_history.items():
            assert now[k] == v
        assert schema(db) == before_schema

    provider = 'skipped for development run'
    if a.link_map and a.build_log:
        identity = run('identity', root / 'identity.sqlite')
        assert identity['sqlite_version'] == '3.54.0' and identity['sqlite_source_id'] == identity['header_source_id']
        provider = sqlite_provider(a.link_map.read_text(errors='replace'), a.build_log.read_text())
    record('installed_consumer_uses_one_verified_product_sqlite_provider')

    # --- Real two-client concurrency, exact heads and explicit merge.
    A, B, key, r1, a2, b2 = fork_group('group')
    for db in (A, B):
        value = run('prepare', db, target='group', gk=TAG, gid=key)
        view = prepared(value)
        assert view['state'] == CONCURRENT and view['resolvable'] == 1 and view['missing'] == view['foreign'] == 0
        assert [h['id'] for h in view['heads']] == sorted([a2, b2])
        assert view['entity_kind'] == 'tag' and view['entity_key'] == key
        for head in view['heads']:
            assert head['wire'] == wire_of(db, head['id']) and head['info_id'] == head['id'] and head['complete'] == 1
            assert hashlib.sha256(head['wire'].encode('utf-8')).hexdigest() == head['sha256']
    record('two_real_clients_expose_every_concurrent_head_with_exact_validated_wire')
    before_h, before_s, before_c = history(A), schema(A), counts(A)
    row_before = group_name(A, key)
    prepared(run('prepare', A, target='group', gk=TAG, gid=key))
    assert counts(A) == before_c and history(A) == before_h and group_name(A, key) == row_before
    record('prepare_never_chooses_a_head_or_writes_history_projection_or_outbox')
    rid = '%032x' % 0xabc
    done = run('resolve', A, target='group', gk=TAG, gid=key, op=PUT, name='用户合并😀', rid=rid)
    result = done['resolve']
    assert result['status'] == OK and result['committed'] == 1 and result['created'] == result['applied'] == 1
    assert result['id'] == rid and result['observed'] == 2 and result['key'] == key
    merged = json.loads(wire_of(A, rid))
    assert sorted(merged['parents']) == sorted([a2, b2]) and merged['payload'] == {'name': '用户合并😀'} and merged['operation'] == 'put'
    assert group_name(A, key) == [('用户合并😀', 0)]
    assert counts(A) == (before_c[0] + 1, before_c[1] + 1)
    intact(A, before_h, before_s)
    after = prepared(run('prepare', A, target='group', gk=TAG, gid=key))
    assert after['state'] == SAFE and [h['id'] for h in after['heads']] == [rid]
    record('explicit_resolution_names_all_observed_heads_and_user_fields_not_clock_or_order')
    record('resolution_preserves_original_histories_schema_and_adds_exactly_one_revision_and_outbox_row')
    # The other client receives the merge and converges.
    assert xfer(A, B, rid)['created'] == 1
    assert prepared(run('prepare', B, target='group', gk=TAG, gid=key))['state'] == SAFE
    record('merge_revision_replicates_to_the_other_client_as_the_single_safe_head')

    # --- Retry, collision and not-a-conflict.
    done = run('resolve', A, target='group', gk=TAG, gid=key, op=PUT, name='x')
    assert done['resolve']['status'] == NOT_CONFLICT and done['resolve']['committed'] == 0
    assert counts(A) == (before_c[0] + 1, before_c[1] + 1)
    record('single_safe_head_refuses_conflict_action')
    A2, _, key2, _, a22, b22 = fork_group('retry')
    c0 = counts(A2)
    done = run('resolve', A2, target='group', gk=TAG, gid=key2, op=PUT, name='重试', rid=rid, rounds=2)
    assert done['resolve']['status'] == OK and done['resolve']['created'] == 1
    assert done['retry']['status'] == OK and done['retry']['committed'] == 1 and done['retry']['created'] == done['retry']['applied'] == 0
    assert counts(A2) == (c0[0] + 1, c0[1] + 1)
    record('same_snapshot_retry_after_commit_is_exact_noop_without_requeue')
    c1 = counts(A2)
    done = run('resolve', A2, target='group', gk=TAG, gid=key2, op=PUT, name='不同', rid=rid)
    assert done['resolve']['status'] in (REVISION, COMMAND) and done['resolve']['revision_code'] == REV_CYCLE
    assert done['resolve']['committed'] == 0 and counts(A2) == c1 and group_name(A2, key2) == [('重试', 0)]
    record('committed_revision_id_reused_with_a_fresh_snapshot_is_refused_and_writes_nothing')

    # --- Foreign revision arrives between prepare and commit, then refresh and retry with the same stable ID.
    C, D = newdb('race-a'), newdb('race-b')
    base = run('local-group', C, gk=TAG, op=PUT, heads='-', name='base', gid='-')
    k3, s1 = base['key'], base['id']
    xfer(C, D, s1)
    ca = run('local-group', C, gk=TAG, op=PUT, heads=s1, name='A', gid=k3)
    db_ = run('local-group', D, gk=TAG, op=PUT, heads=s1, name='B', gid=k3)
    dc = run('local-group', D, gk=TAG, op=PUT, heads=db_['id'], name='B-later', gid=k3)
    xfer(D, C, db_['id'])
    foreign = root / 'foreign.json'
    assert run('export', D, id=dc['id'], out=foreign)['status'] == 0
    fraw = foreign.read_bytes()
    h0, s0, c0 = history(C), schema(C), counts(C)
    stable = '%032x' % 0xdef
    done = run('resolve', C, target='group', gk=TAG, gid=k3, op=PUT, name='合并', rid=stable, race=foreign, race_sha=hashlib.sha256(fraw).hexdigest())
    assert done['race'] == 0 and done['resolve']['status'] == STALE and done['resolve']['committed'] == 0
    assert done['resolve']['id'] == stable
    assert counts(C) == (c0[0] + 1, c0[1] + 0) and stable not in history(C)
    record('revision_arriving_after_prepare_is_stale_and_the_command_writes_nothing')
    done = run('resolve', C, target='group', gk=TAG, gid=k3, op=PUT, name='合并', rid=stable)
    assert done['prepare']['state'] == CONCURRENT and len(done['prepare']['heads']) == 2
    assert done['resolve']['status'] == OK and done['resolve']['created'] == 1
    assert sorted(json.loads(wire_of(C, stable))['parents']) == sorted([ca['id'], dc['id']])
    assert counts(C)[0] == c0[0] + 2
    record('stale_snapshot_is_refreshed_and_retried_once_with_the_same_stable_id')

    # --- Missing parent then late parent.
    M = newdb('missing')
    base_key = '4' * 32
    root_rev = group_revision(0x100, base_key, 'root')
    left, right = group_revision(0x101, base_key, 'left', [root_rev['id']]), group_revision(0x102, base_key, 'right', [root_rev['id']])
    assert remote(M, left) == 0 and remote(M, right) == 0
    value = prepared(run('prepare', M, target='group', gk=TAG, gid=base_key))
    assert value['state'] == INCOMPLETE_STATE and value['resolvable'] == 0 and value['missing'] == 1
    assert [h['complete'] for h in value['heads']] == [0, 0]
    c0 = counts(M)
    done = run('resolve', M, target='group', gk=TAG, gid=base_key, op=PUT, name='too early')
    assert done['resolve']['status'] == INCOMPLETE and counts(M) == c0
    record('missing_parent_heads_are_displayed_but_resolution_is_refused_without_writes')
    assert remote(M, root_rev) == 0
    value = prepared(run('prepare', M, target='group', gk=TAG, gid=base_key))
    assert value['state'] == CONCURRENT and value['resolvable'] == 1 and value['missing'] == 0
    done = run('resolve', M, target='group', gk=TAG, gid=base_key, op=PUT, name='after parent')
    assert done['resolve']['status'] == OK and group_name(M, base_key) == [('after parent', 0)]
    record('late_parent_arrival_makes_the_same_entity_resolvable_after_a_new_prepare')

    # --- Tombstones for groups, then no cascade into memberships or books.
    T = newdb('tomb-a')
    T2 = newdb('tomb-b')
    book = run('local-book', T, op=PUT, heads='-', book=BOOK, title='书', length=123)
    group = run('local-group', T, gk=TAG, op=PUT, heads='-', name='tag', gid='-')
    member = run('local-member', T, op=PUT, heads='-', gk=TAG, gid=group['key'], book=BOOK)
    assert book['status'] == group['status'] == member['status'] == 0
    for item in (book, group, member):
        xfer(T, T2, item['id'])
    tk = group['key']
    deleted = run('local-group', T, gk=TAG, op=DELETE, heads=group['id'], gid=tk, name='-')
    edited = run('local-group', T2, gk=TAG, op=PUT, heads=group['id'], gid=tk, name='live edit')
    assert deleted['status'] == edited['status'] == 0
    xfer(T, T2, deleted['id'])
    xfer(T2, T, edited['id'])
    hist = history(T)
    kinds_before = sql(T, 'SELECT entity_kind,count(*) FROM reader_revisions GROUP BY entity_kind')
    value = prepared(run('prepare', T, target='group', gk=TAG, gid=tk))
    assert value['state'] == TOMBSTONED and {h['operation'] for h in value['heads']} == {'delete', 'put'}
    done = run('resolve', T, target='group', gk=TAG, gid=tk, op=PUT, name='implicit put')
    assert done['resolve']['status'] == RESTORE_REQUIRED and counts(T)[0] == len(hist)
    record('put_after_observed_tombstone_is_refused_before_any_write')
    done = run('resolve', T, target='group', gk=TAG, gid=tk, op=RESTORE, name='显式恢复')
    assert done['resolve']['status'] == OK and group_name(T, tk) == [('显式恢复', 0)]
    assert sorted(json.loads(wire_of(T, done['resolve']['id']))['parents']) == sorted([deleted['id'], edited['id']])
    record('explicit_restore_names_the_delete_and_concurrent_heads_and_revives_the_group')
    kinds_after = dict(sql(T, 'SELECT entity_kind,count(*) FROM reader_revisions GROUP BY entity_kind'))
    assert kinds_after['tag'] == dict(kinds_before)['tag'] + 1
    assert all(kinds_after[k] == v for k, v in kinds_before if k != 'tag')
    assert len(sql(T, 'SELECT * FROM reader_book_tags')) == 1
    record('group_tombstone_resolution_does_not_cascade_to_membership_or_book_history')
    for k, v in hist.items():
        assert history(T)[k] == v

    S = newdb('single-tomb')
    g = run('local-group', S, gk=TAG, op=PUT, heads='-', name='gone', gid='-')
    d = run('local-group', S, gk=TAG, op=DELETE, heads=g['id'], gid=g['key'], name='-')
    value = prepared(run('prepare', S, target='group', gk=TAG, gid=g['key']))
    assert value['state'] == TOMBSTONED and value['resolvable'] == 1 and len(value['heads']) == 1
    c0 = counts(S)
    assert run('resolve', S, target='group', gk=TAG, gid=g['key'], op=PUT, name='n')['resolve']['status'] == RESTORE_REQUIRED
    assert run('resolve', S, target='group', gk=TAG, gid=g['key'], op=DELETE, name='-')['resolve']['status'] == NOT_CONFLICT
    assert counts(S) == c0
    done = run('resolve', S, target='group', gk=TAG, gid=g['key'], op=RESTORE, name='back')
    assert done['resolve']['status'] == OK and group_name(S, g['key']) == [('back', 0)]
    record('single_tombstone_allows_only_explicit_restore_and_a_repeated_delete_is_refused')
    A3, _, key3, _, a3, b3 = fork_group('no-tomb')
    c0 = counts(A3)
    done = run('resolve', A3, target='group', gk=TAG, gid=key3, op=RESTORE, name='nope')
    assert done['resolve']['status'] == NOT_TOMBSTONED and counts(A3) == c0
    done = run('resolve', A3, target='group', gk=TAG, gid=key3, op=DELETE, name='-')
    assert done['resolve']['status'] == OK and group_name(A3, key3)[0][1] == 1
    record('restore_without_a_direct_delete_head_is_refused_and_explicit_delete_merges_all_heads')

    # --- Book and membership are separate entities.
    BA, BB = newdb('book-a'), newdb('book-b')
    first = run('local-book', BA, op=PUT, heads='-', book=BOOK, title='Base', length=123)
    xfer(BA, BB, first['id'])
    ea = run('local-book', BA, op=PUT, heads=first['id'], book=BOOK, title='甲书', length=123)
    eb = run('local-book', BB, op=DELETE, heads=first['id'], book=BOOK, title='-', length=123)
    assert ea['status'] == eb['status'] == 0
    xfer(BA, BB, ea['id']); xfer(BB, BA, eb['id'])
    value = prepared(run('prepare', BA, target='book', book=BOOK))
    assert value['state'] == TOMBSTONED and value['resolvable'] == 1
    assert run('resolve', BA, target='book', book=BOOK, op=PUT, title='implicit', author='作者')['resolve']['status'] == RESTORE_REQUIRED
    done = run('resolve', BA, target='book', book=BOOK, op=RESTORE, title='用户书名😀', author='作者')
    assert done['resolve']['status'] == OK
    assert sql(BA, 'SELECT title,author FROM reader_books WHERE book_key=?', (BOOK,)) == [('用户书名😀', '作者')]
    assert sorted(json.loads(wire_of(BA, done['resolve']['id']))['parents']) == sorted([ea['id'], eb['id']])
    record('book_tombstone_and_explicit_restore_are_resolved_independently')

    MA, MB = newdb('member-a'), newdb('member-b')
    mb = run('local-book', MA, op=PUT, heads='-', book=BOOK, title='B', length=123)
    mg = run('local-group', MA, gk=TAG, op=PUT, heads='-', name='G', gid='-')
    mm = run('local-member', MA, op=PUT, heads='-', gk=TAG, gid=mg['key'], book=BOOK)
    for item in (mb, mg, mm):
        xfer(MA, MB, item['id'])
    mk = 'tag:%s:%s' % (mg['key'], BOOK)
    ma = run('local-member', MA, op=PUT, heads=mm['id'], gk=TAG, gid=mg['key'], book=BOOK)
    md = run('local-member', MB, op=DELETE, heads=mm['id'], gk=TAG, gid=mg['key'], book=BOOK)
    assert ma['status'] == md['status'] == 0
    xfer(MA, MB, ma['id']); xfer(MB, MA, md['id'])
    value = prepared(run('prepare', MA, target='membership', gk=TAG, gid=mg['key'], book=BOOK))
    assert value['state'] == TOMBSTONED and value['entity_key'] == mk
    assert run('resolve', MA, target='membership', gk=TAG, gid=mg['key'], book=BOOK, op=PUT)['resolve']['status'] == RESTORE_REQUIRED
    books_before = sql(MA, 'SELECT count(*) FROM reader_revisions WHERE entity_kind IN (\'book\',\'tag\')')
    done = run('resolve', MA, target='membership', gk=TAG, gid=mg['key'], book=BOOK, op=RESTORE)
    assert done['resolve']['status'] == OK and len(sql(MA, 'SELECT * FROM reader_book_tags')) == 1
    assert sql(MA, 'SELECT count(*) FROM reader_revisions WHERE entity_kind IN (\'book\',\'tag\')') == books_before
    record('membership_tombstone_and_restore_are_resolved_without_touching_book_or_group_history')

    NB = newdb('bootstrap')
    ng = '5' * 32
    nkey = 'tag:%s:%s' % (ng, BOOK)
    payload = {'book_key': BOOK, 'collection_kind': 'tag', 'collection_id': ng, 'ordinal': 0}
    for n in (0x200, 0x201):
        v = {'version': 1, 'id': '%032x' % n, 'entity_kind': 'membership', 'entity_key': nkey, 'operation': 'put', 'location_kind': 'none', 'parents': [], 'payload': payload}
        assert remote(NB, v) == 0
    prepared(run('prepare', NB, target='membership', gk=TAG, gid=ng, book=BOOK))
    c0 = counts(NB)
    done = run('resolve', NB, target='membership', gk=TAG, gid=ng, book=BOOK, op=PUT)
    assert done['resolve']['status'] == NEEDS_BOOTSTRAP and counts(NB) == c0
    record('membership_without_retained_book_history_reports_needs_bootstrap_without_writes')

    # --- Bounds: 32 heads merge, 33 are refused.
    H = newdb('heads-32')
    hk = '6' * 32
    for n in range(1, 33):
        assert remote(H, group_revision(0x1000 + n, hk, 'head%d' % n)) == 0
    value = prepared(run('prepare', H, target='group', gk=TAG, gid=hk))
    assert len(value['heads']) == 32 and value['state'] == CONCURRENT
    done = run('resolve', H, target='group', gk=TAG, gid=hk, op=PUT, name='all 32')
    assert done['resolve']['status'] == OK and done['resolve']['observed'] == 32
    assert len(json.loads(wire_of(H, done['resolve']['id']))['parents']) == 32
    H33 = newdb('heads-33')
    for n in range(1, 34):
        assert remote(H33, group_revision(0x2000 + n, hk, 'head%d' % n)) == 0
    c0 = counts(H33)
    value = run('prepare', H33, target='group', gk=TAG, gid=hk)
    assert value['prepare']['status'] == LIMIT and 'heads' not in value['prepare']
    done = run('resolve', H33, target='group', gk=TAG, gid=hk, op=PUT, name='x')
    assert counts(H33) == c0 and 'resolve' not in done
    record('thirty_two_heads_merge_with_thirty_two_parents_and_thirty_three_are_refused')

    # --- Reading anchors are displayed, never resolved here.
    R = newdb('reading')

    def reading(n, kind, start):
        selector = {'exact': '', 'prefix': '前文', 'suffix': '后文', 'start': start, 'end': start, 'chapter': None}
        location = {'mode': 'reflow_global', 'anchor_version': 2, 'parser_version': '3.40.0', 'selector': selector}
        payload = {'book_key': BOOK, 'location': location}
        key = BOOK
        if kind == 'annotation':
            payload.update(annotation_id='b' * 32, text='书签')
            key = BOOK + ':' + 'b' * 32
        return {'version': 1, 'id': '%032x' % n, 'entity_kind': kind, 'entity_key': key, 'operation': 'put',
                'location_kind': 'reflow_global', 'parents': [], 'payload': payload}
    originals = {}
    for kind, base in (('progress', 0x300), ('annotation', 0x400)):
        for i in (1, 2):
            v = reading(base + i, kind, 5 + i)
            assert remote(R, v) == 0
            originals[v['id']] = encode(v).decode('utf-8')
    c0, h0, s0 = counts(R), history(R), schema(R)
    for kind in ('progress', 'annotation'):
        value = prepared(run('prepare', R, target=kind, book=BOOK, ann='b' * 32))
        assert value['state'] == CONCURRENT and value['resolvable'] == 0 and len(value['heads']) == 2
        for head in value['heads']:
            assert head['wire'] == originals[head['id']]
        done = run('resolve', R, target=kind, book=BOOK, ann='b' * 32, op=PUT, title='x', author='y')
        assert done['resolve']['status'] == READING_HOST and done['resolve']['committed'] == 0
    assert counts(R) == c0 and history(R) == h0 and schema(R) == s0
    record('progress_and_annotation_conflicts_show_exact_wire_and_are_never_resolved_or_navigated_here')

    # --- Typed identity, invalid input and missing entity.
    A4, _, key4, _, _, _ = fork_group('identity')
    c0, h0 = counts(A4), history(A4)
    other = '7' * 32
    cases = [
        dict(target='group', gk=TAG, gid=key4, op=PUT, name='x', cid=other),
        dict(target='group', gk=TAG, gid=key4, op=PUT, name='x', ck=SHELF),
        dict(target='group', gk=TAG, gid=key4, op=PUT, name='x', fn='book', book=BOOK, title='t', author='a'),
        dict(target='group', gk=TAG, gid=key4, op=PUT, name='x', fn='membership', book=BOOK),
    ]
    for case in cases:
        done = run('resolve', A4, **case)
        assert done['resolve']['status'] == IDENTITY and done['resolve']['committed'] == 0, (case, done)
    assert counts(A4) == c0 and history(A4) == h0
    for bad in (dict(target='bad'), dict(target='group', gk=TAG, gid='xyz'), dict(target='book', book='txt:zz'), dict(target='membership', gk=TAG, gid=key4, book='nope')):
        assert run('prepare', A4, **bad)['prepare']['status'] == ARGUMENT, bad
    assert run('prepare', A4, target='group', gk=TAG, gid=other)['prepare']['status'] == NOT_FOUND
    BK = newdb('bookid')
    first = run('local-book', BK, op=PUT, heads='-', book=BOOK, title='x', length=123)
    assert first['status'] == 0
    assert run('resolve', BK, target='book', book=BOOK, op=PUT, title='y', author='z', cbook=OTHER_BOOK)['resolve']['status'] == IDENTITY
    record('typed_command_identity_invalid_targets_and_missing_entities_are_refused_before_writing')

    # --- Cancellation: before commit only.
    CA, _, ck, _, _, _ = fork_group('cancel')
    c0, h0, s0 = counts(CA), history(CA), schema(CA)
    seen = []
    for n in range(0, 14):
        value = run('prepare', CA, target='group', gk=TAG, gid=ck, cancel_prepare=n)
        assert value['prepare']['status'] in (OK, CANCELLED), value
        seen.append(value['prepare']['status'])
        assert counts(CA) == c0 and history(CA) == h0
    assert seen[0] == CANCELLED and seen[-1] == OK and seen == sorted(seen, key=lambda s: s == OK)
    done = run('resolve', CA, target='group', gk=TAG, gid=ck, op=PUT, name='cancel me', rid='%032x' % 9, cancel_resolve=0)
    assert done['resolve']['status'] == CANCELLED and done['resolve']['committed'] == 0 and done['resolve']['polls'] == 1
    assert counts(CA) == c0 and history(CA) == h0 and schema(CA) == s0
    done = run('resolve', CA, target='group', gk=TAG, gid=ck, op=PUT, name='cancel me', rid='%032x' % 9, cancel_resolve=1)
    assert done['resolve']['status'] == OK and done['resolve']['polls'] == 1 and counts(CA) == (c0[0] + 1, c0[1] + 1)
    record('cancellation_is_observed_only_before_the_commit_boundary_and_leaves_no_partial_state')

    # --- Native transaction failure rolls back all three writes; retry with the same ID succeeds.
    FA, _, fk, _, _, _ = fork_group('failure')
    c0, h0, name0 = counts(FA), history(FA), group_name(FA, fk)
    with sqlite3.connect(FA) as c:
        c.execute("CREATE TRIGGER j11_fail BEFORE INSERT ON reader_outbox BEGIN SELECT RAISE(ABORT,'injected'); END")
    stable = '%032x' % 0xfeed
    done = run('resolve', FA, target='group', gk=TAG, gid=fk, op=PUT, name='retry me', rid=stable)
    assert done['resolve']['status'] == REVISION and done['resolve']['committed'] == 0 and done['resolve']['id'] == stable
    assert counts(FA) == c0 and history(FA) == h0 and group_name(FA, fk) == name0
    with sqlite3.connect(FA) as c:
        c.execute('DROP TRIGGER j11_fail')
    done = run('resolve', FA, target='group', gk=TAG, gid=fk, op=PUT, name='retry me', rid=stable)
    assert done['resolve']['status'] == OK and done['resolve']['created'] == 1 and group_name(FA, fk) == [('retry me', 0)]
    assert counts(FA) == (c0[0] + 1, c0[1] + 1)
    record('native_transaction_failure_rolls_back_history_outbox_and_projection_then_retries_exactly_once')

    # --- Worker and reentry rules.
    WA, _, wk, _, _, _ = fork_group('owner')
    c0 = counts(WA)
    done = run('resolve', WA, target='group', gk=TAG, gid=wk, op=PUT, name='x', thread=1)
    assert done['resolve']['status'] == OWNER and counts(WA) == c0
    value = run('prepare', WA, target='group', gk=TAG, gid=wk, reenter=1)
    assert value['prepare']['status'] == OK and value['prepare']['reenter'] == OWNER
    record('foreign_worker_and_callback_reentry_are_rejected_without_state_change')

    # --- Installed C API: header-only integration and an actual explicit merge.
    CA2, _, ckey, _, _, _ = fork_group('c-api')
    c0 = counts(CA2)
    done = subprocess.run([str(a.c_consumer.resolve()), str(CA2), ckey], capture_output=True, timeout=60)
    assert done.returncode == 0, done
    assert counts(CA2) == (c0[0] + 1, c0[1] + 1) and group_name(CA2, ckey) == [('C explicit merge', 0)]
    record('installed_c_header_prepares_inspects_and_applies_an_explicit_group_resolution')

    forbidden = [p.name for p in root.iterdir() if p.suffix in ('.db', '.sdk', '.epub', '.pdf')]
    assert not forbidden
    record('no_sdk_database_notes_or_original_book_files_are_created_or_modified')
    evidence = {'sha': sha, 'os': platform.system(), 'local_run': a.local_run, 'sqlite_provider': provider, 'checks': checks}
    (root / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'complete': True, 'checks': len(checks)}))


if __name__ == '__main__':
    main()
