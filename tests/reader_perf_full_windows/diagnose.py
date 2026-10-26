#!/usr/bin/env python3
"""Run the retained TXT diagnostic, preserving failures before classification."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
import diagnose_txt_import as diagnostic
import full_ui

diagnostic.import_original = full_ui.diagnostic_import

original = diagnostic.classify

def classify_with_failure_evidence(run):
    facts = run['facts']
    if 'error' in facts or not all(key in facts for key in ('import', 'probes', 'open')):
        output = Path(sys.argv[sys.argv.index('--output') + 1])
        (output / 'unclassified-failure.json').write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding='utf-8')
        print('UNCLASSIFIED OBSERVER FAILURE ' + json.dumps(run, ensure_ascii=False), flush=True)
        raise RuntimeError('TXT diagnosis failed before classification; original facts preserved')
    return original(run)

diagnostic.classify = classify_with_failure_evidence
sys.exit(diagnostic.main())
