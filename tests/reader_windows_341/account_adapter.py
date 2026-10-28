"""Actions-only version adapter; retained Windows account judge stays unchanged."""
import difflib, hashlib, os, runpy, sys
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
source = Path("tests/reader_windows_account/check_account_ui.py")
original = source.read_text(encoding="utf-8")
text = original
before = """        RB = new_device('device-reading-b')
        dialog = RB.open_account()
        RB.fill(dialog, reading_root, user, password, False);RB.apply(dialog, '仅本次会话')
        RB.run_sync(dialog)
        RB.wait(lambda: len(sql('device-reading-b', 'SELECT sdk_book_id FROM reader_local_books')) == 4, timeout=240)
"""
after = """        RB = new_device('device-reading-b')
        dialog = RB.open_account()
        RB.fill(dialog, reading_root, user, password, False);RB.apply(dialog, '仅本次会话')
        expected_original = (args.reading_fixtures / roles['txt']).read_bytes()
        with dav.lock:
            matches = [p for p, data in dav.entries.items() if p.startswith('/reading/' + OBJECTS) and data == expected_original]
            assert len(matches) == 1, matches
            missing_path = matches[0]
            removed = dav.entries.pop(missing_path)
        assert hashlib.sha256(removed).hexdigest() == manifest['txt']['sha256']
        RB.press(dialog, SYNC);RB.wait_note(dialog, '接收尚未完成', 240)
        detail = RB.detail(dialog)
        assert '等待原件 1' in detail and RB.enabled(dialog, RETRY), detail
        assert not sql('device-reading-b', 'SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (reading_keys['txt'],))
        with dav.lock:
            assert missing_path not in dav.entries
            dav.entries[missing_path] = removed
        RB.press(dialog, RETRY);RB.wait_note(dialog, '同步完成', 240)
        RB.wait(lambda: len(sql('device-reading-b', 'SELECT sdk_book_id FROM reader_local_books')) == 4, timeout=240)
        assert len(sql('device-reading-b', 'SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (reading_keys['txt'],))) == 1
        print(json.dumps({'real_missing_original_retry': True, 'sha256': manifest['txt']['sha256'], 'bytes': len(removed)}, ensure_ascii=False), flush=True)
"""
assert text.count(before) == 1
text = text.replace(before, after, 1)
before = """        receive_record('device-reading-b', planted)
        RB = new_device('device-reading-b', existing=True)
        dialog = RB.open_account()
        RB.fill(dialog, reading_root, user, password, False);RB.apply(dialog, '仅本次会话')
        RB.run_sync(dialog);RB.close_account(dialog)
"""
after = """        receive_record('device-reading-b', planted)
        RB = new_device('device-reading-b', existing=True)
        dialog = RB.open_account()
        RB.fill(dialog, reading_root, user, password, False);RB.apply(dialog, '仅本次会话')
        RB.press(dialog, SYNC);RB.wait_note(dialog, '接收尚未完成', 240)
        detail = RB.detail(dialog)
        assert '等待原件 1' in detail and RB.enabled(dialog, RETRY), detail
        assert not sql('device-reading-b', 'SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (planted_key,))
        RB.close_account(dialog)
"""
assert text.count(before) == 1
text = text.replace(before, after, 1)
before = """        dialog = RB.open_account()
        RB.run_sync(dialog)
        detail = RB.detail(dialog)
        print(json.dumps({'planted_receive': detail}, ensure_ascii=False), flush=True)
"""
after = """        dialog = RB.open_account()
        RB.press(dialog, SYNC);RB.wait_note(dialog, '接收尚未完成', 240)
        detail = RB.detail(dialog)
        assert RB.enabled(dialog, RETRY), detail
        print(json.dumps({'planted_receive': detail}, ensure_ascii=False), flush=True)
"""
assert text.count(before) == 1
text = text.replace(before, after, 1)
before = "'complete_product': False}"
after = "'versioned_account_adapter': True, 'original_account_judge_passed': False, 'complete_product': False}"
assert text.count(before) == 1
text = text.replace(before, after, 1)
output = Path("build/account-adapter")
output.mkdir(parents=True, exist_ok=True)
(output / "source.diff").write_text("".join(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile=str(source), tofile="adapted-account-ui")), encoding="utf-8")
(output / "source.sha256").write_text(hashlib.sha256(original.encode()).hexdigest() + "\n")
generated = source.with_name("_actions_account_adapter.py")
generated.write_text(text, encoding="utf-8")
try:
    sys.argv[0] = str(generated)
    runpy.run_path(str(generated), run_name="__main__")
finally:
    generated.unlink(missing_ok=True)
