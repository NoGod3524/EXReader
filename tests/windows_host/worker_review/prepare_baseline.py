#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only reverse verification: add observation/fault gates to original host."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASE = '2d99fcd3a912eb05ad6df8257a13a6c929c860a8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a fresh baseline directory')
    args.output.mkdir(parents=True)
    original = subprocess.check_output(['git', 'show', BASE+':examples/reader.c']).decode('utf-8')
    text = original
    changes = []

    def replace(old, new, label):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError('Baseline instrumentation anchor differs: '+label)
        text = text.replace(old, new)
        changes.append(label)

    replace('static host_state g;', 'static host_state g;\nstatic int dragging;\nstatic int review_query_failure(int kind);', 'forward observation declarations')
    replace('static int job_cancel_check(void *context) {', '#include EXR_HOST_WORKER_REVIEW_HEADER\n\nstatic int job_cancel_check(void *context) {', 'shared observation header')
    replace('static LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {',
            'static LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {\n  if(message == WM_APP+30) return review_message(window,wparam,lparam);', 'read-only observation and gate message')
    replace('    status = exr_library_fixed_note(g.library, &note, NULL, &id, &error);',
            '    review_pause(1,NULL);\n    status = exr_library_fixed_note(g.library, &note, NULL, &id, &error);', 'fixed note call thread gate')
    replace('    status = exr_library_fixed_note(g.library, &note, NULL, &note.id, &error);',
            '    review_pause(1,NULL);\n    status = exr_library_fixed_note(g.library, &note, NULL, &note.id, &error);', 'fixed update call thread gate')
    replace('  if (job->status == EXR_CANCELLED) frame_clear(&job->frame);',
            '  if(job->status == EXR_OK) review_pause(job->kind == JOB_OPEN ? 4 : job->kind == JOB_GO ? 2 : 0,job);\n  if (job->status == EXR_CANCELLED) frame_clear(&job->frame);', 'pause completed result before UI acceptance')
    replace('  free(path);\n  free(data);\n  if (status == EXR_OK && job_cancel_flag(job)) {',
            '  free(path);\n  free(data);\n  if(status == EXR_OK) review_pause(3,job);\n  if (status == EXR_OK && job_cancel_flag(job)) {', 'pause import after real SQL commit')
    start = text.index('static exr_status page_for_offset(')
    end = text.index('static exr_status reflow_restore(', start)
    segment = text[start:end]
    if segment.count('exr_pager_get(') != 4:
        raise RuntimeError('Baseline offset call inventory differs')
    text = text[:start]+segment.replace('exr_pager_get(', 'review_offset_get(')+text[end:]
    changes.append('inject public page error only after real cache operations')
    replace('  status = exr_library_books(g.library, "", &books, &count, &error);',
            '  if(review_query_failure(2)) status=EXR_DATABASE; else\n  status = exr_library_books(g.library, "", &books, &count, &error);', 'public shelf query failure')
    replace('  if (g.session.fixed)\n    status = exr_library_fixed_notes(',
            '  if(review_query_failure(1)) status=EXR_DATABASE; else\n  if (g.session.fixed)\n    status = exr_library_fixed_notes(', 'public notes query failure')
    replace('static void host_cleanup(void) {', 'static void host_cleanup(void) {\n  review_shutdown();', 'close test gate handle')
    (args.output/'reader-baseline.c').write_text(text, encoding='utf-8')
    (args.output/'instrumentation.json').write_text(json.dumps({'base_sha': BASE,
        'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'instrumented_sha256': hashlib.sha256(text.encode()).hexdigest(), 'observation_only_changes': changes}, indent=2)+'\n')


if __name__ == '__main__':
    main()
