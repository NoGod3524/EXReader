
        # F05 additive diagnostic: peers write only their OWN offline stores.
        # All remote revisions below must originate in a native conditional PUT.
        a = device('f05-peer-a')
        b = device('f05-peer-b', account=a['account'])
        b.update(space=a['space'], url=a['url'])
        key = 'f5' * 16
        va = revision(1001, shard=18, key=key, payload={'name': 'peer A offline'})
        vb = revision(1002, shard=18, key=key, payload={'name': 'peer B offline'})
        start_requests = len(requests)
        seed(a, 'f05-a-local', va)
        seed(b, 'f05-b-local', vb)
        assert len(requests) == start_requests
        assert counting(a)() == (1, 1) and counting(b)() == (1, 1)
        for spec in (a, b):
            idle = Session(spec)
            assert idle.created == 0
            idle.close()
        assert len(requests) == start_requests
        assert counting(a)() == (1, 1) and counting(b)() == (1, 1)
        assert step(a)['status'] == 0
        assert step(b)['status'] == 0
        pa, pb = revision_path(a, va), revision_path(a, vb)
        assert entries[pa] == raw(va) and entries[pb] == raw(vb)
        assert counting(a)() == (1, 0) and counting(b)() == (2, 0)
        record('f05_two_offline_peers_publish_their_own_wire',
               'Independent local stores survive process reopen offline, then publish exact immutable wire through native HTTPS.',
               {'peer_a_counts': list(counting(a)()), 'peer_b_counts': list(counting(b)()),
                'wire_sha256': {pa: digest(entries[pa]), pb: digest(entries[pb])},
                'requests_before_online': 0})

        held = gate('GET', pb, 'partial_body', partial=12)
        receiving = Session(a, timeout=15000)
        assert receiving.command('start')['code'] == 0
        assert held['event'].wait(120), 'peer B revision GET did not reach partial body'
        assert receiving.command('cancel')['code'] == 0
        cancelled = receiving.wait(3)
        held['release'].set()
        receiving.close()
        assert counting(a)() == (1, 0)
        record('f05_partial_peer_revision_cancel_keeps_atomic_history',
               'Cancel at the observed partial wire response cannot receive a partial revision or erase the existing head.',
               {'state': cancelled['state'], 'counts': list(counting(a)()),
                'remote_sha256': digest(entries[pb])})

        held = gate('GET', pb, 'partial_body', partial=12)
        receiving = Session(a, timeout=15000)
        assert receiving.command('start')['code'] == 0
        assert held['event'].wait(120)
        killed = receiving.kill()
        held['release'].set()
        assert killed['returncode'] != 0 and counting(a)() == (1, 0)
        resumed = Session(a)
        assert resumed.command('start')['code'] == 0
        resumed.wait(4)
        resumed.close()
        assert counting(a)() == (2, 0)
        heads = protocol_call(a, 'heads', 'tag', key)
        assert heads['state']['heads'] == 2
        assert heads['state']['projection_safe'] == 0
        expected_ids = sorted([va['id'], vb['id']])
        assert sorted(h['id'] for h in heads['heads']) == expected_ids
        for spec in (a, b):
            assert step(spec)['status'] == 0
            assert counting(spec)() == (2, 0)
            for value in (va, vb):
                output = spec['base'] / (value['id'] + '-exact.json')
                protocol_call(spec, 'get', value['id'], output)
                assert output.read_bytes() == raw(value)
        record('f05_peer_conflict_survives_hard_kill_and_idempotent_rescan',
               'A hard kill at partial peer GET preserves old state; restart and repeated scans converge to exactly the two original immutable heads.',
               {'exit': killed, 'head_ids': expected_ids, 'projection_safe': 0,
                'peer_a_counts': list(counting(a)()), 'peer_b_counts': list(counting(b)()),
                'resume_contract': 'idempotent rescan; not persisted cursor'})

        deletion = revision(1003, shard=18, key=key, operation='delete', parents=expected_ids)
        seed(b, 'f05-b-delete', deletion)
        assert step(b)['status'] == 0
        assert step(a)['status'] == 0
        pd = revision_path(a, deletion)
        assert entries[pd] == raw(deletion)
        for spec in (a, b):
            assert counting(spec)() == (3, 0)
            hs = protocol_call(spec, 'heads', 'tag', key)
            assert hs['state']['heads'] == 1
            assert hs['heads'][0]['id'] == deletion['id']
            assert hs['heads'][0]['operation'] == 'delete'
            assert step(spec)['status'] == 0
            assert counting(spec)() == (3, 0)
        own_requests = requests[start_requests:]
        puts = [r for r in own_requests if r['method'] == 'PUT']
        assert {r['path'] for r in puts} == {pa, pb, pd}
        assert all(r['if_none_match'] == '*' for r in puts)
        assert all(r['status'] == 201 for r in puts), puts
        assert len(puts) == 3
        record('f05_peer_tombstone_crosses_wire_without_history_loss',
               'An explicit tombstone with both observed parents travels by native HTTPS; each peer retains all three history records and repeated scans publish nothing.',
               {'tombstone_id': deletion['id'], 'parents': expected_ids,
                'wire_sha256': digest(entries[pd]), 'conditional_put_count': len(puts),
                'peer_a_counts': list(counting(a)()), 'peer_b_counts': list(counting(b)())})
