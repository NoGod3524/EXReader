# SPDX-License-Identifier: MIT
"""Inspect the real live GTK status widget over AT-SPI on the private bus."""
import json
import os
from pathlib import Path
import sys
import time

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_a11y_gtk'))
import atspi_client as bus

pid = int(sys.argv[1])
expected = sys.argv[2]
assert bus.init()[0]
try:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        apps = [app for app in bus.applications() if app.get_process_id() == pid]
        if apps:
            node = bus.find_one(apps[0], roles={'text'}, text='Sync status details', exact=True)
            if node and bus.states(node).get('showing'):
                text = bus.accessible_text(node)
                states = bus.states(node)
                if text and text['text'] == expected:
                    assert not states.get('editable'), states
                    print(json.dumps({'pid': pid, 'role': bus.role(node), 'editable': False,
                                      'text': text['text'], 'states': states}), flush=True)
                    break
        time.sleep(.1)
    else:
        raise AssertionError('live status widget and displayed text not available on AT-SPI')
finally:
    bus.exit_bus()
