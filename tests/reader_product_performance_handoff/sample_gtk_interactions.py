#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""GTK product interaction sampler: shelf scroll, font change, continuous page turns.

Reuses the unchanged reader_perf_gtk Sampler (fixed 2202-original corpus, real X11
input, inotify observation, RSS high water). Latency ends at the first host
observation that shows the effect and a real repaint (painted_generation). The
host exposes no frame clock, so inter-paint intervals are a proxy, never a frame
time. Navigation jump is not compiled into this GTK build and is not sampled.
Actions-only; any failed or missing planned sample fails the run.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_perf_gtk'))
import sample  # noqa: E402
from observe import SampleError  # noqa: E402

SCROLLS = 6
FONT_STEPS = 3
BURST_TURNS = 20


class Interactions(sample.Sampler):
    def write_settings(self, profile, book):
        super().write_settings(profile, self.long_id if self.kind == 'reader_interact' else 0)

    def run(self):
        self.output.mkdir(parents=True)
        (self.output / 'raw').mkdir(parents=True, exist_ok=True)
        self.collect_environment()
        self.seed()
        self.calibrate()
        for index in range(self.arguments.launches):
            self.launch_once(index)
        self.write_evidence()

    def effect_and_paint(self, watch, since, predicate, stamp, handle, what, timeout=180, need_paint=True):
        previous = self.current_paint(watch)
        index, event, _ = self.wait_after(
            watch, lambda s: predicate(s) and sample.settled(s), timeout, since, stamp)
        if index is None:
            self.record(handle, 'failed', note='%s: %s' % (what, event))
            return None
        if not need_paint:
            # The shelf list box is not the page widget whose draw advances painted_generation:
            # this sample ends at the host observation showing the new top row, not at a repaint.
            self.record(handle, 'ok', start=stamp, end=event['at'], event=event,
                        note='state observation; no repaint evidence for the shelf widget')
            return event
        paint_index, paint_event, detail = self.first_paint(watch, previous, since, index, timeout, stamp)
        if paint_index is None:
            self.record(handle, 'failed', start=stamp, end=event['at'],
                        note='%s observed without a repaint: %s' % (what, detail))
            return None
        self.record(handle, 'ok', start=stamp, end=max(event['at'], paint_event['at']), event=paint_event)
        return paint_event


    def quiet_shelf(self, watch, deadline):
        # The frozen host saves its scroll viewport after a 300 ms idle timer.
        # Require an unchanged viewport across that publication before new input.
        signature, stable_at = None, None
        while time.monotonic() < deadline:
            event = watch.latest()
            state = event['state'] if event else {}
            host = state.get('host') or {}
            ready = (sample.settled(state) and not host.get('shelf_loading')
                     and not host.get('shelf_restoring') and not host.get('shelf_pending'))
            current = (host.get('shelf_first_id'), host.get('shelf_last_id'),
                       host.get('shelf_top_id'), (state.get('shelf') or {}).get('top_offset'))
            now = time.monotonic()
            if ready and current == signature and stable_at is not None:
                if now - stable_at >= 0.35:
                    return event
            else:
                signature, stable_at = current if ready else None, now if ready else None
            time.sleep(0.01)
        raise SampleError('shelf viewport did not settle within the original operation budget')

    def save_scroll_trace(self, watch, since, phase, **details):
        if not hasattr(self, 'scroll_traces'):
            self.scroll_traces = []
        self.scroll_traces.append(dict(launch=self.launch, phase=phase, details=details,
                                       events=list(watch.events)[since:]))
        (self.output / 'scroll-input-traces.json').write_text(
            json.dumps(self.scroll_traces, indent=2) + '\n')

    def prepare_interior_scroll(self, host, watch):
        deadline = time.monotonic() + 180
        for step in range(24):
            event = self.quiet_shelf(watch, deadline)
            state = event['state']['host']
            if state.get('shelf_before') and state.get('shelf_after'):
                self.save_scroll_trace(watch, watch.mark(), 'interior-ready', state=event['state'])
                return
            if not state.get('shelf_after'):
                raise SampleError('fixed 2202-book shelf has no forward interior')
            since = watch.mark()
            subprocess.run(['xdotool', 'click', '--repeat', '4', '--delay', '0', '5'],
                           check=True, timeout=30)
            # This is a declared preparation step, not a measured/retried sample.
            self.wait_after(watch, lambda value: sample.settled(value),
                            max(0, deadline - time.monotonic()), since)
            self.save_scroll_trace(watch, since, 'interior-preparation', step=step)
        raise SampleError('bounded interior preparation did not complete')

    def scenario_shelf(self, index, host, watch, kind):
        if kind == 'reader_interact':
            return self.scenario_reader(index, host, watch)
        handle = self.expect('startup_shelf_rows', 'first_publication' if index == 0 else 'warm_catalog')
        try:
            _, event = self.await_state(host, watch, sample.shelf_ready, 600, 0, 'first shelf page')
            self.record(handle, 'ok', start=self.launch_stamp, end=event['at'], event=event)
            self.start_host(host)
            geometry = host.geometry()
            subprocess.run(['xdotool', 'mousemove', '--window', str(host.window),
                            str(geometry['WIDTH'] // 3), str(geometry['HEIGHT'] // 2)], check=True, timeout=30)
        except (SampleError, subprocess.SubprocessError) as error:
            if handle['status'] == 'pending':
                self.record(handle, 'failed', note=str(error))
            return
        self.prepare_interior_scroll(host, watch)
        for name, button in (('shelf_scroll_down', '5'), ('shelf_scroll_up', '4')):
            for _ in range(SCROLLS):
                metric = self.expect(name)
                deadline = time.monotonic() + 180
                try:
                    baseline = self.quiet_shelf(watch, deadline)
                except SampleError as error:
                    self.record(metric, 'failed', note=str(error))
                    return
                top = baseline['state']['host'].get('shelf_top_id')
                since = watch.mark()
                stamp = time.monotonic()
                subprocess.run(['xdotool', 'click', '--repeat', '4', '--delay', '0', button],
                               check=True, timeout=30)
                observed = self.effect_and_paint(
                    watch, since, lambda s: s['host'].get('shelf_top_id') != top,
                    stamp, metric, 'shelf top row change',
                    timeout=max(0, deadline - time.monotonic()), need_paint=False)
                self.save_scroll_trace(watch, since, 'measured-scroll',
                                       metric=name, slot=metric['slot'], baseline=baseline['state'])
                if observed is None:
                    return

    def scenario_reader(self, index, host, watch):
        resumed = self.expect('resume_frame_painted')
        try:
            at, _ = self.await_state(host, watch, lambda s: (
                s['host'].get('book') == self.long_id and s['host'].get('reader_visible') == 1
                and sample.settled(s)), 600, 0, 'resumed long book')
            painted, paint, detail = self.first_paint(watch, 0, 0, at, 300)
            if painted is None:
                raise SampleError('resumed frame without a repaint: %s' % detail)
            self.record(resumed, 'ok', start=self.launch_stamp, end=paint['at'], event=paint)
            self.start_host(host)
        except (SampleError, subprocess.SubprocessError) as error:
            self.record(resumed, 'failed', note=str(error))
            return
        for name, key, delta in (('font_bigger', 'F5', 2), ('font_smaller', 'F6', -2)):
            for _ in range(FONT_STEPS):
                metric = self.expect(name)
                font = watch.latest()['state']['host'].get('font')
                since = watch.mark()
                stamp = host.press(key)
                if self.effect_and_paint(watch, since, lambda s: s['host'].get('font') == font + delta,
                                         stamp, metric, 'font %+d' % delta) is None:
                    return
        self.turns(host, watch, BURST_TURNS, 0)


def stats(values):
    ordered = sorted(values)
    rank = max(1, -(-95 * len(ordered) // 100))
    return {'n': len(ordered), 'p50': statistics.median(ordered), 'p95': ordered[rank - 1],
            'max': ordered[-1], 'samples': values}


def summarize(output, launches, planned):
    rows = json.loads((output / 'samples.json').read_text())['samples']
    metrics = {}
    for row in rows:
        if row['outcome'] == 'ok':
            metrics.setdefault(row['metric'], []).append(row['latency_ms'])
    intervals = []
    for launch in launches:
        offsets = launch.get('paint_offsets_ms') or []
        intervals += [round(b - a, 3) for a, b in zip(offsets, offsets[1:])]
    problems = [r for r in rows if r['outcome'] != 'ok']
    expected_counts = {'startup_shelf_rows': 6, 'shelf_scroll_down': 36, 'shelf_scroll_up': 36,
                       'resume_frame_painted': 6, 'font_bigger': 18, 'font_smaller': 18,
                       'page_turn_forward': 120}
    for name, expected in expected_counts.items():
        actual = len(metrics.get(name, []))
        if actual != expected:
            problems.append({'outcome': 'incomplete-coverage', 'metric': name,
                             'expected': expected, 'observed': actual})
    summary = {'schema': 1, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
               'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'launches': len(launches),
               'planned_launches': planned, 'expected_counts': expected_counts, 'metrics': {k: stats(v) for k, v in sorted(metrics.items())},
               'rss_high_water_kb': [l.get('vm_hwm_kb') for l in launches],
               'inter_paint_interval_ms': stats(intervals) if intervals else None,
               'problems': problems, 'frame_time_measured': False, 'jump_measured': False,
               'note': 'inter-paint intervals include idle gaps and are not frame times'}
    (output / 'interaction-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    for name, value in summary['metrics'].items():
        print('METRIC %s n=%d p50=%s p95=%s max=%s' % (name, value['n'], value['p50'], value['p95'], value['max']))
    print('PROBLEMS %d launches %d/%d rss_kb=%s' % (len(problems), len(launches), planned,
                                                   summary['rss_high_water_kb']))
    return not problems and len(launches) == planned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tarball', type=Path)
    parser.add_argument('--launches', type=int, default=12)
    arguments = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or arguments.output.exists():
        parser.error('Actions only, with a new output directory')
    sample.KINDS = ('shelf_scroll', 'reader_interact')
    sampler = Interactions(arguments)
    sampler.run()
    sys.exit(0 if summarize(arguments.output, sampler.launches, arguments.launches) else 1)


if __name__ == '__main__':
    main()
