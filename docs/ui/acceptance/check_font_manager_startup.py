#!/usr/bin/env python3
"""Six real host starts, plus isolated fallback/explicit/missing-font checks."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('sans', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    script = args.output/'quit.drive'
    script.write_text('quit\n', encoding='utf-8')

    def run(name, extra=(), expected=0):
        profile = args.output/name/'profile'
        cmd = [str(args.exe.resolve()), '--offscreen', '--drive', str(script.resolve()),
               '--data', str(profile.resolve()), *map(str, extra)]
        result = subprocess.run(cmd, capture_output=True, timeout=45)
        assert result.returncode == expected, (cmd, result.returncode, result.stderr)
        if expected:
            return dict(exit=result.returncode)
        log = (profile/'typography.log').read_text(encoding='utf-8')
        (args.output/(name+'.txt')).write_text(log, encoding='utf-8')
        return dict(line.split('=', 1) for line in log.splitlines()[1:] if '=' in line)

    results = []
    for i in range(1, 4):
        name = f'pair-{i}'
        assert not (args.output/name).exists(), 'benchmark output must be fresh'
        for state in ('cold', 'hot'):
            result = run(name)
            (args.output/f'{name}-{state}.txt').write_text(
                (args.output/(name+'.txt')).read_text(encoding='utf-8'), encoding='utf-8')
            assert result['cache'] == ('1' if state == 'cold' else '3'), result
            if state == 'hot':
                assert float(result['manager_ms']) <= 150 and result['parsed_files'] == '0', result
            results.append(dict(run=i, state=state, **result))
    for fallback in (False, True):
        config = args.output/f'sans-{int(fallback)}.conf'
        config.write_text('version = 1\nfont_file = '+args.sans.resolve().as_posix()+
                          '\nplatform_dirs = no\nserif = Noto Serif SC, SimSun\n'
                          'sans_serif = Noto Sans CJK SC\n'+
                          ('fallback = Noto Sans CJK SC\n' if fallback else ''), encoding='utf-8')
        result = run('sans-'+str(int(fallback)), ('--font-config', config.resolve()))
        assert result['body_font'] == 'fallback-sans' and result['family'] == 'Noto Sans CJK SC', result
    explicit = run('explicit', ('--font', args.sans.resolve()))
    assert explicit['family'] == 'Noto Sans CJK SC' and explicit['faces'] == '1', explicit
    config = args.output/'missing.conf'
    config.write_text('version = 1\nfont_dir = absent-required-fonts\nplatform_dirs = no\n', encoding='utf-8')
    missing = run('missing', ('--font-config', config.resolve()), expected=2)
    output = dict(startup=results, sans_only='pass', configured_sans_fallback='pass',
                  explicit=explicit, missing=missing)
    (args.output/'results.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
