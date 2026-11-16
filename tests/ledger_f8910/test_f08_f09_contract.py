"""Stdlib checks for missing frame evidence, shelf telemetry, and AT-SPI events."""
import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


gtk = module('tests/reader_perf_gtk/summarize.py')
windows = module('tests/reader_perf_windows/render_budget.py')
a11y = module('tests/reader_a11y_gtk/expectations.py')


class Contract(unittest.TestCase):
    def test_atspi_dispatch(self):
        queued = []
        context = SimpleNamespace(pending=lambda: bool(queued),
                                  iteration=lambda blocking: queued.pop(0)())
        glib = SimpleNamespace(MainContext=SimpleNamespace(default=lambda: context))
        gi = SimpleNamespace(require_version=lambda *args: None)
        with patch.dict(sys.modules, {'gi': gi, 'gi.repository': SimpleNamespace(Atspi=SimpleNamespace(), GLib=glib)}):
            client = module('tests/reader_a11y_gtk/atspi_client.py')
        recorder = client.Recorder()
        source = SimpleNamespace(get_role_name=lambda: 'label', get_name=lambda: 'Failed')
        event = SimpleNamespace(type='object:property-change:accessible-name', detail1=0, detail2=0, source=source)
        queued.append(lambda: recorder._callback(event))
        # A callback queries its source through _safe; dispatch must not recurse.
        self.assertEqual(recorder.mark(), 1)
        queued.append(lambda: recorder._callback(event))
        self.assertEqual(recorder.since(1)[0]['source_name'], 'Failed')
        self.assertFalse(queued)
        self.assertFalse(client._dispatching)

    def test_frames(self):
        rows = [dict(frame=i, frame_time_us=i * 16000, update_us=i * 16000,
                     after_paint_us=i * 16000 + 1000) for i in range(4)]
        result = gtk.frame_metrics(rows)
        self.assertEqual(result['frame_p95_ms'], 1)
        self.assertEqual(result['interval_p50_ms'], 16)
        for bad in ([], rows[:1], rows[::-1], rows[::2],
                    [rows[0], dict(rows[1], after_paint_us=0)]):
            with self.assertRaises(ValueError):
                gtk.frame_metrics(bad)

    def test_shelf(self):
        text = ('SHELF-BUDGET corpus books=2202 import_setup_ms=1\n'
                'SHELF-BUDGET shelf_load_ms=1 first_paint_ms=2 first_interactive_ms=3 hits=2202 books=2202\n'
                'SHELF-BUDGET peak_working_set_bytes=1024\n')
        for name, count in [('grid_move', 256), ('list_move', 128)]:
            text += 'SHELF-BUDGET raw_' + name + '_ms=' + json.dumps([1.0] * count) + '\n'
            text += 'SHELF-BUDGET ' + name + ' n=%d p50_ms=1 p95_ms=1 max_ms=1 scrolled_to=200\n' % count
        self.assertTrue(windows.shelf_metrics(text)['passed'])
        self.assertFalse(windows.shelf_metrics(text.replace('first_interactive_ms=3', 'first_interactive_ms=3000'))['passed'])
        for bad in (text + text, text.replace('books=2202', 'books=2000'),
                    text.replace('scrolled_to=200', 'scrolled_to=0'),
                    text.replace('p95_ms=1', 'p95_ms=2'), text.replace('[1.0,', '[0,')):
            with self.assertRaises(ValueError):
                windows.shelf_metrics(bad)

    def test_status_event(self):
        event = dict(type='object:property-change:accessible-name', detail1='0', source_name='Failed')
        self.assertTrue(a11y.status_name_event(event, 'Failed'))
        self.assertFalse(a11y.status_name_event(event, 'Ready'))
        self.assertFalse(a11y.status_name_event(dict(event, type='object:state-changed:focused'), 'Failed'))


if __name__ == '__main__':
    unittest.main()
