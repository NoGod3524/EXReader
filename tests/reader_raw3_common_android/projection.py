"""Only the reviewed source-guard and strict entry points may differ."""
ORIGINAL = 'caa84411ae79c866c28cf982243b6cb80b4bbe49'
ORIGINAL_WORKFLOW = '.github/workflows/reader-android-raw3.yml'
WORKFLOW = '.github/workflows/reader-raw3-common-android.yml'
OLD_GUARD = '          python tests/reader_android_raw3/guard.py\n'
NEW_GUARD = ('          python tests/reader_raw3_common_android/guard.py\n'
             '          python tests/reader_raw3_common_android/selftest.py\n')
OLD_STRICT = ('          python tests/reader_android_record_interop/check_evidence.py\n'
              '          python tests/reader_android_raw3/strict.py\n')
NEW_STRICT = '          python tests/reader_raw3_common_android/strict.py\n'
SUMMARY_CHECKOUT = ('      - uses: actions/checkout@v4\n'
                    '      - name: Authenticate original 130 plus actual sender bundle and parent-negative graph\n')
COMMON_SUMMARY_CHECKOUT = ('      - uses: actions/checkout@v4\n'
                           '        with: {fetch-depth: 0}\n'
                           '      - name: Authenticate original 130 plus actual sender bundle and parent-negative graph\n')


def source_upload(job):
    return (f'      - name: Preserve explicit common source guard for {job}\n'
            '        uses: actions/upload-artifact@v4\n'
            '        if: always()\n'
            '        with:\n'
            f'          name: reader-common-android-source-{job}-${{{{ github.run_id }}}}-${{{{ github.run_attempt }}}}\n'
            f'          path: build/reader-raw3-common-android/{job}/\n'
            '          if-no-files-found: error\n')


STRICT_UPLOAD = ('      - name: Preserve added common-kind strict provenance\n'
                 '        uses: actions/upload-artifact@v4\n'
                 '        if: always()\n'
                 '        with:\n'
                 '          name: reader-common-android-strict-${{ github.run_id }}-${{ github.run_attempt }}\n'
                 '          path: build/reader-raw3-common-android/strict/\n'
                 '          if-no-files-found: error\n')


def original_projection(text):
    changes = (
        ('name: Common source Android complete raw3 chain',
         'name: Android explicit raw3 native host candidate', 1),
        ('branches: [codex/reader-raw3-common-integration]',
         'branches: [codex/reader-android-raw3-candidate]', 1),
        (NEW_GUARD, OLD_GUARD, 2),
        (NEW_STRICT, OLD_STRICT, 1),
        (COMMON_SUMMARY_CHECKOUT, SUMMARY_CHECKOUT, 1),
        (source_upload('android'), '', 1),
        (source_upload('protocol'), '', 1),
        (STRICT_UPLOAD, '', 1),
    )
    for current, prior, count in changes:
        if text.count(current) != count:
            raise RuntimeError('workflow projection substitution count differs: ' + current)
        text = text.replace(current, prior)
    return text
