#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""SMask retention and single group application, with analytic constant masks."""
from pathlib import Path
import json
from generate_nested_group_fixtures import write, stream

ROOT = Path(__file__).resolve().parent.parent/'tests/fixtures/pdf-blend'


def scene(name, alpha, kind):
    extra = '/Group << /S /Transparency /I true /CS /DeviceRGB >>'
    child = '1 0 0 rg 0 0 16 16 re f 0 0 1 rg 0 0 16 16 re f'
    if kind in ['retain', 'null', 'clear', 'restore']:
        tail = {'retain': '/A gs', 'null': '/N gs', 'clear': '/C gs', 'restore': 'q /C gs Q /A gs'}[kind]
        body = '/M gs '+tail+' 1 0 0 rg 0 0 16 16 re f'
    else:
        body = '/M gs /F Do'
        if kind == 'ordinary':
            extra = ''
        if kind == 'inner-alpha':
            child = '/A gs 1 0 0 rg 0 0 16 16 re f 0 0 1 rg 0 0 16 16 re f'
        if kind == 'nested':
            child = '/A gs /Inner Do'
    dictionary = '/ExtGState << /M << /SMask << /S /Alpha /G 6 0 R >> >> /A << /ca .5 >> /N << /SMask null /ca .5 >> /C << /SMask /None /ca .5 >> >>'
    mask = stream('/A gs 1 1 1 rg 0 0 16 16 re f',
                  '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /CS /DeviceRGB >> '
                  '/Resources << /ExtGState << /A << /ca %.12g >> >> >>' % (alpha/255))
    if kind == 'bad-mask':
        mask = b'<< /Type /XObject /Subtype /Form >>'
    if kind == 'bad-content':
        child = 'q /Missing Do Q'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R '
         '/Group << /S /Transparency /I true /CS /DeviceRGB >> /Resources << %s /XObject << /F 5 0 R >> >> >>' % dictionary).encode(),
        stream(body),
        stream(child, '/Type /XObject /Subtype /Form /BBox [0 0 16 16] %s /Resources << %s /XObject << /Inner 7 0 R >> >>' % (extra, dictionary)),
        mask,
        stream('1 0 0 rg 0 0 16 16 re f 0 0 1 rg 0 0 16 16 re f',
               '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /CS /DeviceRGB >> /Resources << >>'),
    ]
    return write(name, objects)


def main():
    rows = []
    for kind in ['retain', 'null', 'clear', 'restore', 'ordinary', 'group', 'inner-alpha', 'nested']:
        for alpha in [64, 128, 192]:
            name = 'mask-scope-%s-%d.pdf' % (kind, alpha)
            digest = scene(name, alpha, kind)
            m = alpha/255
            if kind in ['retain', 'null', 'restore']:
                pm = [m*.5, 0, 0, m*.5]
            elif kind == 'clear':
                pm = [.5, 0, 0, .5]
            elif kind == 'ordinary':
                pm = [m*(1-m), 0, m, m+m*(1-m)]
            elif kind == 'group':
                pm = [0, 0, m, m]
            elif kind == 'inner-alpha':
                a = 128/255
                pm = [m*a*(1-a), 0, m*a, m*(a+a*(1-a))]
            else:
                pm = [0, 0, m*.5, m*.5]
            byte = lambda v: max(0, min(255, int(v*255+.5)))
            rows.append({'file': name, 'sha256': digest, 'kind': kind, 'mask': alpha,
                         'premultiplied': list(map(byte, pm)),
                         'white': [byte(v+1-pm[3]) for v in pm[:3]]+[255]})
    for kind in ['shape-iso', 'shape-noniso', 'shape-nested']:
        name = 'mask-scope-'+kind+'.pdf'
        child_group = '/S /Transparency /I false' if kind == 'shape-noniso' else '/S /Transparency /I true /CS /DeviceRGB'
        shape_body = '/A gs 0 0 1 rg 0 0 8.5 16 re f'
        objects = [
            b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Resources << /XObject << /F 5 0 R >> >> >>',
            stream('/F Do'),
            stream('1 0 0 rg 0 0 16 16 re f /Child Do',
                   '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /K true /CS /DeviceRGB >> '
                   '/Resources << /XObject << /Child 6 0 R >> >>'),
            stream('/Inner Do' if kind == 'shape-nested' else shape_body,
                   '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << %s >> '
                   '/Resources << /ExtGState << /A << /ca .5 >> >> /XObject << /Inner 7 0 R >> >>' % child_group),
            stream(shape_body, '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /CS /DeviceRGB >> '
                   '/Resources << /ExtGState << /A << /ca .5 >> >> >>'),
        ]
        rows.append({'file': name, 'sha256': write(name, objects), 'kind': kind,
                     'probe_type': 'analytic-half-coverage-edge',
                     'premultiplied': [128, 0, 64, 192], 'white': [191, 64, 128, 255]})
    for kind in ['bad-mask', 'bad-content']:
        name = 'mask-scope-'+kind+'.pdf';scene(name, 128, kind)
    budget = [
        b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Resources << /ExtGState << /M 5 0 R >> /XObject << /F 7 0 R >> >> >>',
        stream('/M gs /F Do'),b'<< /SMask << /S /Alpha /G 6 0 R >> >>',
        stream('', '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /CS /DeviceRGB >> /Resources << >>'),
    ]
    for depth in range(20):
        budget.append(stream('/M gs /F Do' if depth<19 else '',
                             '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /CS /DeviceRGB >> '
                             '/Resources << /ExtGState << /M 5 0 R >> /XObject << /F %d 0 R >> >>' % (depth+8)))
    write('mask-scope-budget.pdf', budget)
    (ROOT/'mask-scope-manifest.json').write_text(json.dumps({'scenes': rows}, indent=2)+'\n', encoding='utf-8')
    (ROOT/'mask-scope-oracle.bin').write_bytes(bytes(v for row in rows for key in ['premultiplied', 'white'] for v in row[key]))
    print('Generated 27 mask/shape-scope scenes and three rejected inputs')


if __name__ == '__main__':
    main()
