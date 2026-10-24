# SPDX-License-Identifier: MIT
"""Actions-only real GTK settings, pixels, gestures and installed F3 readback."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_gtk_receive'))
import atspi_client as bus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('payload', 'output', 'consumer', 'fixed-inputs'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args();assert os.environ.get('GITHUB_ACTIONS') == 'true'
    os.environ.pop('NO_AT_BRIDGE', None);os.environ.pop('GTK_MODULES', None);os.environ['GTK_A11Y'] = 'atspi'
    output = args.output.resolve();output.mkdir()
    profile = output / 'profile';profile.mkdir()
    (profile / 'reader.ini').write_text('[reader]\nfont=31\nzoom=175\n', encoding='utf-8')
    source = output / 'Long paragraphs.txt'
    source.write_text(('A paragraph of native readable text. This sentence supplies repeatable page geometry. ' * 3 + '\n\n') * 4000, encoding='utf-8')
    before_source = hashlib.sha256(source.read_bytes()).hexdigest()
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), output)
    settings = profile / 'preferences.json';checks, keys = [], []
    report = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks,
              'program_sha256': hashlib.sha256(host.binary.read_bytes()).hexdigest(),
              'scope': 'Linux GTK installed F3 settings and actual native effects',
              'sdk_changed': False, 'schema_changed': False, 'orca_accepted': False,
              'physical_device_execution': False, 'six_platform_accepted': False, 'complete_product': False}

    def observed():
        value = configparser.ConfigParser(interpolation=None);value.read(host.observe)
        return dict(value['preferences']) if value.has_section('preferences') else {}

    def wait(predicate=lambda value: True, seconds=60):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            value = observed()
            assert host.process.poll() is None, 'host exited'
            if value and value['running'] == '0' and not host.read().get('busy') and predicate(value): return value
            time.sleep(.05)
        raise TimeoutError('settings readiness: ' + repr(observed()))

    def element(name, roles=None):
        end = time.monotonic() + 20
        while time.monotonic() < end:
            found = bus.find_one(app, text=name, roles=roles)
            if found: return found
            time.sleep(.1)
        raise TimeoutError('missing native control: ' + name)

    def key(*values):
        host.key(*values);keys.extend(values)

    def click(name, roles=None):
        rectangle = bus.extents(element(name, roles));assert rectangle and rectangle['width'] > 0
        command('xdotool', 'mousemove', '--sync', str(rectangle['x'] + rectangle['width'] // 2),
                str(rectangle['y'] + rectangle['height'] // 2));command('xdotool', 'click', '1')

    def open_settings():
        command('xdotool', 'windowactivate', '--sync', host.window);key('ctrl+comma')
        wait(lambda value: value['visible'] == '1')
        target = command('xdotool', 'search', '--onlyvisible', '--name', '^Reading settings$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', target);return element('Reading settings', {'dialog'})

    def close_settings():
        key('Escape');wait(lambda value: value['visible'] == '0')

    def field(name, value):
        click(name, {'spin button', 'text'});key('ctrl+a');host.paste(str(value));key('Tab')
        target = element(name, {'spin button', 'text'})
        print(json.dumps({'field_input': name, 'requested': value, 'role': bus.role(target),
                          'actual_text': bus.accessible_text(target),
                          'actual_value': bus._safe(lambda: target.get_value_iface().get_current_value()),
                          'focus': [bus.name(node) for node in bus.focused_all(app)]}), flush=True)

    def combo(name, index):
        click(name, {'combo box'});key('Home', *(['Down'] * index), 'Return')

    def button(mnemonic):
        before = int(observed()['actions']);key('alt+' + mnemonic)
        return wait(lambda value: int(value['actions']) > before)

    def save():
        result = button('s')
        dialog = element('Reading settings', {'dialog'})
        assert any(bus.name(node) and bus.is_ancestor(dialog, node) for node in bus.focused_all(app)), 'settings save lost exposed control focus'
        return result

    def defaults():
        button('d');save();return wait()

    def record(name, condition=True, observed_value=None, strict=True):
        item = {'name': name, 'pass': bool(condition), 'observed': observed_value};checks.append(item)
        print(json.dumps(item), flush=True)
        if strict: assert condition, item

    def shot(name):
        path = output / (name + '.png');command('import', '-window', host.window, str(path));return path

    def pixels(name, color):
        path = shot(name);frame = host.read();prefs = observed()
        width, height = int(prefs['bitmap_width']), int(prefs['bitmap_height'])
        image = Image.open(path).convert('RGB')
        x = frame['page_x'] + (frame['page_width'] - width) // 2
        y = frame['page_y'] + (frame['page_height'] - height) // 2
        crop = image.crop((x, y, x + width, y + height))
        count = sum(1 for pixel in crop.getdata() if max(abs(pixel[i] - color[i]) for i in range(3)) <= 3)
        return {'matching_pixels': count, 'bitmap_width': width, 'bitmap_height': height,
                'outer_margin_pixel': crop.getpixel((5, 5)),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def installed():
        value = subprocess.run([str(args.consumer.resolve()), str(settings)], capture_output=True, text=True, timeout=30)
        assert value.returncode == 0, value.stdout + value.stderr
        return json.loads(value.stdout)

    def panel_pixels(name, color):
        path = shot(name);rectangle = bus.extents(element('Selectable page text', {'text'}))
        frame = bus.extents(element('EXReader Linux', {'frame'}))
        x, y = rectangle['x'] - frame['x'], rectangle['y'] - frame['y']
        crop = Image.open(path).convert('RGB').crop((x, y, x + rectangle['width'], y + rectangle['height']))
        count = sum(1 for pixel in crop.getdata() if max(abs(pixel[i] - color[i]) for i in range(3)) <= 3)
        return {'matching_pixels': count, 'rectangle': rectangle, 'frame': frame,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def page_click(x_fraction=.8, y_fraction=.5):
        rectangle = bus.extents(element('Rendered page; selectable text is in the adjacent panel', {'image'}))
        x, y = rectangle['x'] + int(rectangle['width'] * x_fraction), rectangle['y'] + int(rectangle['height'] * y_fraction)
        command('xdotool', 'mousemove', '--sync', str(x), str(y));command('xdotool', 'click', '1');host.wait(lambda value: True)

    def swipe(vertical=False, reverse=False):
        rectangle = bus.extents(element('Rendered page; selectable text is in the adjacent panel', {'image'}))
        x, y = rectangle['x'] + rectangle['width'] // 2, rectangle['y'] + rectangle['height'] // 2
        delta = 100 if reverse else -100
        command('xdotool', 'mousemove', '--sync', str(x), str(y));command('xdotool', 'mousedown', '1')
        command('xdotool', 'mousemove', '--sync', str(x if vertical else x + delta), str(y + delta if vertical else y))
        command('xdotool', 'mouseup', '1');host.wait(lambda value: True)

    try:
        assert bus.init()[0]
        host.launch();app = bus.wait_application('exreader-linux')
        record('f3_defaults_do_not_import_or_replace_legacy_font_zoom',
               observed()['font'] == '24.000' and observed()['zoom'] == '100' and not settings.exists(), observed())
        host.dialog(source);host.wait(lambda value: value['book'] > 0 and value['end'] > 0)
        wait();base_end = host.read()['end']
        dialog = open_settings();focused = bus.focused_all(app)
        record('native_secondary_modal_panel_has_initial_named_focus', bus.states(dialog).get('modal') and
               any(bus.name(node) and bus.is_ancestor(dialog, node) for node in focused))
        command('xdotool', 'windowactivate', '--sync', host.window);key('F1', 'F4', 'ctrl+shift+c')
        record('settings_modal_blocks_background_actions', host.read()['page'] == 0 and
               not bus.find_one(app, text='Library collections', roles={'dialog'}) and
               not bus.find_one(app, text='Import book', roles={'file chooser'}))
        target = command('xdotool', 'search', '--onlyvisible', '--name', '^Reading settings$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', target);close_settings()
        frame = element('EXReader Linux', {'frame'})
        record('settings_escape_restores_internal_focus', any(bus.is_ancestor(frame, node) for node in bus.focused_all(app)))
        for title, value, expected_key in (('Font size', 30, 'font'), ('Line spacing', 2.5, 'line'),
                                           ('Paragraph spacing', 48, 'paragraph'), ('Page margin', 85, 'margin')):
            open_settings();defaults();field(title, value);save();close_settings()
            measure = {'before_end': base_end, 'after_end': host.read()['end'], 'installed': installed()}
            record('actual_reflow_' + expected_key, measure['after_end'] < base_end and
                   abs(installed()[expected_key] - value) < .001, measure)
            open_settings();defaults();close_settings()
        open_settings();field('Font size', 25.5);save();close_settings()
        record('fractional_font_is_applied_and_saved', observed()['font'] == '25.500' and installed()['font'] == 25.5)
        open_settings();defaults();field('Light foreground', '#D02020FF');field('Light background', '#FDF4DCFF');save();close_settings()
        fg = pixels('light-foreground', (208, 32, 32));bg = pixels('light-background', (253, 244, 220))
        panel_fg = panel_pixels('light-panel-foreground', (208, 32, 32));panel_bg = panel_pixels('light-panel-background', (253, 244, 220))
        record('light_foreground_and_background_change_page_pixels', fg['matching_pixels'] > 100 and bg['matching_pixels'] > 1000,
               {'foreground': fg, 'background': bg, 'foreground_passed': fg['matching_pixels'] > 100,
                'background_passed': bg['matching_pixels'] > 1000,
                'native_panel_foreground': panel_fg, 'native_panel_background': panel_bg}, strict=False)
        report['reflow_outer_margin'] = {'actual_pixel': bg['outer_margin_pixel'], 'requested_background': [253, 244, 220],
                                         'whole_page_background_accepted': bg['outer_margin_pixel'] == (253, 244, 220),
                                         'limitation': 'Public reflow renderer fixes the canvas to white; user CSS controls content background. No white-pixel replacement or image recoloring is performed.'}
        open_settings();field('Dark foreground', '#14E66EFF');field('Dark background', '#141E46FF');combo('Theme', 1);save();close_settings()
        fg = pixels('dark-foreground', (20, 230, 110));bg = pixels('dark-background', (20, 30, 70))
        panel_fg = panel_pixels('dark-panel-foreground', (20, 230, 110));panel_bg = panel_pixels('dark-panel-background', (20, 30, 70))
        record('dark_theme_and_palette_change_page_pixels', fg['matching_pixels'] > 100 and bg['matching_pixels'] > 1000,
               {'foreground': fg, 'background': bg, 'foreground_passed': fg['matching_pixels'] > 100,
                'background_passed': bg['matching_pixels'] > 1000,
                'native_panel_foreground': panel_fg, 'native_panel_background': panel_bg}, strict=False)
        assert panel_fg['matching_pixels'] > 100 and panel_bg['matching_pixels'] > 1000, 'native dark panel palette did not apply'
        open_settings();combo('Theme', 2);save();close_settings()
        command('gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', 'prefer-dark')
        dark = wait(lambda value: value['effective_theme'] == '2' and int(value['portal_events']) > 0)
        dark_pixels = panel_pixels('system-dark-panel-background', (20, 30, 70))
        dark_page = pixels('system-dark-light-page', (208, 32, 32))
        command('gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', 'prefer-light')
        light = wait(lambda value: value['effective_theme'] == '1' and int(value['portal_events']) > int(dark['portal_events']))
        light_pixels = panel_pixels('system-light-panel-background', (253, 244, 220))
        light_page = pixels('system-light-light-page', (208, 32, 32))
        record('system_theme_tracks_real_portal_preference_changes', int(light['portal_version']) >= 1 and
               dark_pixels['matching_pixels'] > 1000 and light_pixels['matching_pixels'] > 1000 and
               dark_page['matching_pixels'] > 100 and light_page['matching_pixels'] > 100,
               {'dark': dark, 'light': light, 'dark_interface_pixels': dark_pixels, 'light_interface_pixels': light_pixels,
                'dark_state_light_page': dark_page, 'light_state_light_page': light_page, 'reading_page_dark_accepted': False})
        open_settings();defaults();close_settings()
        page_click();record('ltr_tap_turns_to_next_page', host.read()['page'] == 1)
        key('F3');host.wait(lambda value: value['page'] == 0)
        open_settings();combo('Page turn direction', 1);save();close_settings()
        page_click(.2);record('rtl_tap_reverses_the_horizontal_target', host.read()['page'] == 1)
        key('F3');open_settings();combo('Page turn input', 1);save();close_settings()
        page_click(.2);record('swipe_mode_rejects_tap', host.read()['page'] == 0)
        swipe(reverse=True);record('rtl_swipe_uses_actual_drag_direction', host.read()['page'] == 1)
        key('F3');open_settings();combo('Page turn direction', 2);save();close_settings()
        swipe(vertical=True);record('vertical_swipe_uses_vertical_axis', host.read()['page'] == 1)
        key('F3');open_settings();combo('Page turn input', 2);save();close_settings()
        page_click(.5, .8);record('combined_input_accepts_tap', host.read()['page'] == 1)
        key('F3');swipe(vertical=True);record('combined_input_accepts_swipe', host.read()['page'] == 1)
        key('F3');open_settings();combo('Page turn input', 3);save();close_settings()
        page_click(.5, .8);swipe(vertical=True);record('hardware_only_rejects_page_surface_gestures', host.read()['page'] == 0)
        click('Next F4');key('F3');command('xdotool', 'windowactivate', '--sync', host.window)
        key('Down');host.wait(lambda value: value['page'] == 1)
        record('hardware_vertical_key_turns_page', host.read()['page'] == 1)
        host.dialog((args.fixed_inputs / 'Pages.pdf').resolve());host.wait(lambda value: value['fixed'] == 1)
        before = observed();open_settings();field('Fixed page zoom', 125);save();close_settings();after = observed()
        record('fixed_zoom_changes_actual_sdk_bitmap_dimensions', int(after['bitmap_width']) > int(before['bitmap_width']) and
               int(after['bitmap_height']) > int(before['bitmap_height']), {'before': before, 'after': after})
        key('F5');wait();record('fixed_zoom_toolbar_updates_authoritative_record', installed()['zoom'] == 150)
        host.close();host.launch();app = bus.wait_application('exreader-linux');wait()
        record('new_process_reopens_saved_appearance_and_fixed_zoom', observed()['zoom'] == '150' and host.read()['zoom'] == 150)
        open_settings();button('i');save();close_settings()
        record('legacy_import_is_explicit_and_keeps_original_values_available', installed()['font'] == 31 and installed()['zoom'] == 175)
        open_settings();defaults();close_settings()
        old = settings.read_bytes();current = dict(observed());settings.write_bytes(b'{broken')
        open_settings();button('r');close_settings()
        record('failed_reload_keeps_current_state_and_bad_file_bytes', observed()['font'] == current['font'] and settings.read_bytes() == b'{broken')
        settings.write_bytes(old);open_settings();field('Page margin', 1024);save()
        record('composed_geometry_refusal_preserves_file_and_active_values', settings.read_bytes() == old and observed()['margin'] == current['margin'])
        defaults();old = settings.read_bytes();field('Font size', 29);profile.chmod(0o500)
        try: failed = save()
        finally: profile.chmod(0o700)
        record('real_atomic_save_failure_retains_previous_file_and_active_record', int(failed['save_status']) != 0 and settings.read_bytes() == old and observed()['font'] == '24.000')
        save();close_settings();record('retry_saves_the_retained_draft', installed()['font'] == 29)
        host.close();bad = json.loads(settings.read_text());bad['format_version'] = 99;settings.write_text(json.dumps(bad));unknown = settings.read_bytes()
        host.launch();app = bus.wait_application('exreader-linux');wait()
        record('unknown_version_reopen_retains_file_and_uses_valid_defaults', int(observed()['load_status']) == 4 and observed()['font'] == '24.000' and settings.read_bytes() == unknown)
        open_settings();defaults();close_settings()
        record('defaults_are_saved_through_installed_f3_api', installed() == {'status': 0, 'font': 24, 'line': 1.6, 'paragraph': 12, 'margin': 48, 'theme': 1, 'direction': 1, 'input': 1, 'zoom': 100})
        legacy = configparser.ConfigParser();legacy.read(profile / 'reader.ini')
        record('old_appearance_values_are_not_silently_overwritten', legacy.getint('reader', 'font') == 31 and legacy.getint('reader', 'zoom') == 175)
        key('F2', 'Home', 'Return');host.wait(lambda value: value['fixed'] == 0 and value['reader_visible'] == 1)
        open_settings();field('Font size', 4);field('Line spacing', 1);field('Paragraph spacing', 0);field('Page margin', 0)
        sender = subprocess.Popen(['xdotool', 'key', '--clearmodifiers', 'alt+s'])
        end = time.monotonic() + 5;running_seen = False
        while time.monotonic() < end:
            if observed().get('running') == '1': running_seen = True;break
            time.sleep(.002)
        assert running_seen, 'did not observe the real owner settings barrier'
        command('wmctrl', '-ic', hex(int(host.window)));sender.wait(timeout=10)
        code = host.process.wait(timeout=45);host.log.close()
        record('parent_close_waits_for_observed_settings_owner_barrier', code == 0 and int(observed()['deferred_closes']) > 0 and installed()['font'] == 4, observed())
        host.launch();app = bus.wait_application('exreader-linux');wait()
        record('barrier_close_reopens_the_complete_saved_record', observed()['font'] == '4.000' and host.read()['font'] == 4)
        record('original_source_bytes_unchanged', hashlib.sha256(source.read_bytes()).hexdigest() == before_source)
        assert len(checks) == 35
        passed = sum(bool(item['pass']) for item in checks)
        report.update(accepted=passed == len(checks), count=len(checks), passed=passed,
                      failed=len(checks) - passed, preferences=installed(),
                      pending_fields=['light_background_on_reflow_canvas', 'dark_reading_page_palette'])
    finally:
        if profile.exists(): profile.chmod(0o700)
        if host.process and host.process.poll() is None:
            if not report['accepted']:
                shot('failure')
                if 'app' in locals(): (output / 'failure-tree.json').write_text(json.dumps(bus.dump(app), indent=2), encoding='utf-8')
                print((output / 'application.log').read_text(errors='replace')[-8000:], flush=True)
            host.process.kill();host.process.wait(timeout=15)
        if host.log: host.log.close()
        report['last_observation'] = observed()
        (output / 'keys.json').write_text(json.dumps(keys, indent=2), encoding='utf-8')
        (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        bus.exit_bus()
    print(json.dumps(report), flush=True)
    raise SystemExit(0 if report['accepted'] else 1)


if __name__ == '__main__': main()
