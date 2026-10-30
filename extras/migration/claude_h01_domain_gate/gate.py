"""H01 domain gate: validate the externally supplied admission-domain binding.

Pure validation. Opens no lease, reads no credentials, never grants admission:
BINDING_VALID only says the caller's domain->lease_identity mapping is
well-formed, unambiguous and agrees with an independently supplied registry.

CLI:  gate.py --binding BINDING.json --registry REGISTRY.json
stdout: exactly one line  H01-GATE {json}  (sorted keys, no spaces)
exit:   0 BINDING_VALID, 1 REFUSED, 2 usage/unreadable input (also REFUSED)
"""
import argparse, json, re, sys

GATE = 'claude_h01_domain_gate'
C01_PROVIDER = 'ccd7fec67eb8aa463b09533ce320820f2da472d9'
IDENT = re.compile(r'^[0-9a-f]{48}$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')
BINDING_KEYS = {'domain', 'lease_identity', 'expected_generation', 'run_id',
                'run_attempt', 'provider_sha', 'gates'}
REGISTRY_KEYS = {'domains'}
U64 = 2**64 - 1


class Refusal(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_registry(reg):
    if not isinstance(reg, dict) or set(reg) != REGISTRY_KEYS:
        raise Refusal('registry-schema')
    doms = reg['domains']
    if not isinstance(doms, dict) or not doms:
        raise Refusal('registry-empty')
    seen = {}
    for d, ident in doms.items():
        if not isinstance(d, str) or not d:
            raise Refusal('registry-domain')
        if not isinstance(ident, str) or not IDENT.match(ident):
            raise Refusal('registry-identity-format')
        if ident in seen:
            raise Refusal('registry-identity-shared')  # two domains, one lease
        seen[ident] = d
    return doms


def check_binding(b, reg):
    doms = check_registry(reg)
    if not isinstance(b, dict):
        raise Refusal('binding-schema')
    if set(b) != BINDING_KEYS:
        raise Refusal('binding-keys')
    if not isinstance(b['domain'], str) or not b['domain']:
        raise Refusal('binding-domain')
    if not isinstance(b['lease_identity'], str) or not IDENT.match(b['lease_identity']):
        raise Refusal('binding-identity-format')
    g = b['expected_generation']
    if not _is_int(g) or g < 0 or g > U64:
        raise Refusal('binding-generation')
    if not _is_int(b['run_id']) or b['run_id'] <= 0:
        raise Refusal('binding-run-id')
    if not _is_int(b['run_attempt']) or b['run_attempt'] <= 0:
        raise Refusal('binding-run-attempt')
    if not isinstance(b['provider_sha'], str) or not HEX40.match(b['provider_sha']):
        raise Refusal('binding-provider-format')
    if b['provider_sha'] != C01_PROVIDER:
        raise Refusal('binding-provider-mismatch')
    gt = b['gates']
    if (not isinstance(gt, list) or not gt
            or any(not isinstance(x, str) or not x for x in gt)
            or len(set(gt)) != len(gt)):
        raise Refusal('binding-gates')
    if b['domain'] not in doms:
        raise Refusal('domain-unknown')
    if doms[b['domain']] != b['lease_identity']:
        raise Refusal('domain-identity-mismatch')
    return 'ok'


def evaluate(binding, registry):
    try:
        check_binding(binding, registry)
        return {'gate': GATE, 'verdict': 'BINDING_VALID', 'reason': 'ok',
                'admission_granted': False}
    except Refusal as e:
        return {'gate': GATE, 'verdict': 'REFUSED', 'reason': e.code,
                'admission_granted': False}


def _load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def emit(result):
    sys.stdout.write('H01-GATE ' + json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--binding', required=True)
    ap.add_argument('--registry', required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        emit({'gate': GATE, 'verdict': 'REFUSED', 'reason': 'usage', 'admission_granted': False})
        return 2
    try:
        b, r = _load(a.binding), _load(a.registry)
    except (OSError, ValueError):
        emit({'gate': GATE, 'verdict': 'REFUSED', 'reason': 'input-unreadable', 'admission_granted': False})
        return 2
    res = evaluate(b, r)
    emit(res)
    return 0 if res['verdict'] == 'BINDING_VALID' else 1


if __name__ == '__main__':
    sys.exit(main())
