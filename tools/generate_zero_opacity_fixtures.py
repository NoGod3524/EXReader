#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""ISO 32000-1 11.4.6 zero opacity with nonzero shape in knockout groups."""
from decimal import Decimal as D
import json
import hashlib
from generate_alpha_source_fixtures import scene, PRIMITIVES
from generate_nested_group_fixtures import ROOT
from generate_knockout_fixtures import scenes, expected_pixels


def main():
    rows = []
    for mask_zero in [False, True]:
        for isolated in [False, True]:
            for shape in [False, True]:
                for primitive in PRIMITIVES:
                    a = D(128)/255 if mask_zero else D(0)
                    m = D(9)/16 if primitive in ['soft', 'explicit', 'key'] else D(0)
                    alpha = a*m
                    f = alpha if shape else m if primitive in ['explicit', 'key'] else D(1)
                    rgba = [int(((1-f)*r+alpha*b+(f-alpha)*bg)+D('.5')) for r, b, bg in zip([255, 0, 0], [0, 0, 255], [51, 102, 153])]+[255]
                    name = 'zero-%s-%s-%s-%s.pdf' % ('mask' if mask_zero else 'opacity', 'iso' if isolated else 'noniso', 'shape' if shape else 'opacity', primitive)
                    rows.append({'file': name, 'sha256': scene(name, isolated, shape, primitive, 128 if mask_zero else 0, backdrop=True, mask_rate=0 if mask_zero else 128),
                                 'probe_type': ('mask-' if mask_zero else 'constant-')+('shape-' if shape else 'opacity-')+primitive,
                                 'premultiplied': rgba, 'white': rgba})
    cells, isolated, knockout, background, mask = scenes()['knockout-shapes']
    alpha, white = expected_pixels(len(cells)*16, 16, cells, isolated, knockout, background, mask, zero_opacity_shape=True)
    corrections = {}
    for suffix, data in [('alpha', alpha), ('white', white)]:
        name = 'knockout-shapes-zero-opacity-'+suffix+'.rgba';old = (ROOT/('knockout-shapes-'+suffix+'.rgba')).read_bytes()
        (ROOT/name).write_bytes(data)
        corrections[suffix] = {'file': name, 'sha256': hashlib.sha256(data).hexdigest(), 'legacy_sha256': hashlib.sha256(old).hexdigest(),
                               'changed_pixels': sum(data[i:i+4]!=old[i:i+4] for i in range(0, len(data), 4))}
    (ROOT/'zero-opacity-manifest.json').write_text(json.dumps({'scenes': rows, 'corrected_legacy_reference': corrections}, indent=2)+'\n', encoding='utf-8')
    (ROOT/'zero-opacity-oracle.bin').write_bytes(bytes(v for row in rows for v in row['white']))
    print('%d zero-opacity scenes' % len(rows))


if __name__=='__main__':
    main()
