"""Independent strict comparisons for actual sender transport and SDK recapture.

HostReadingRecords.decoded reconstructs ONLY EPUB's SDK chapter field from
the retained part_path. The transport keeps chapter NULL in that mode.
"""


def judge(row, expected):
    failures = []
    for field in ('revision_id', 'role', 'kind', 'mode', 'anchor_version'):
        if row.get(field) != expected.get(field):
            failures.append('record.' + field)
    transport, recapture, reconstruction = (row.get(key) for key in
                                           ('transport_capture', 'recapture', 'reconstruction'))
    captures = (transport, recapture, reconstruction, expected.get('capture'))
    if not all(isinstance(value, dict) and set(value) == {'numbers', 'route', 'selectors'} and
               isinstance(value['numbers'], list) and len(value['numbers']) == 4 and
               isinstance(value['route'], list) and len(value['route']) == 5 and
               isinstance(value['selectors'], list) and len(value['selectors']) == 3
               for value in captures):
        return failures + ['capture.shape']
    if transport != expected['capture']:
        failures.append('transport.sender_manifest')
    if transport['numbers'] != recapture['numbers']:
        failures.append('capture.numbers')
    if transport['selectors'] != recapture['selectors']:
        failures.append('capture.selectors')
    wanted_route = list(transport['route'])
    if expected['role'] == 'epub' and expected['mode'] == 2:
        # Exact existing owner contract, not a blanket EPUB route exception.
        if (transport['numbers'][0] != '2' or not isinstance(wanted_route[2], str) or
                not wanted_route[2] or wanted_route[3] is not None or wanted_route[4] is not None):
            failures.append('route.epub_transport_contract')
        wanted_route[4] = wanted_route[2]
    if recapture['route'] != wanted_route:
        failures.append('capture.route_contract')
    if reconstruction != recapture:
        failures.append('capture.reconstruction')
    return failures
