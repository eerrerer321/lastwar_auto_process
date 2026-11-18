"""不擷取遊戲、不送出滑鼠操作的介面與停止流程驗證。"""
import json
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import DailyWork as engine
from dailywork_gui import DailyWorkWindow, PARAMETERS, parse_settings


def default_values():
    values = {
        name: str(engine.MONITOR_REGION[name] if group == '畫面' else getattr(engine, name))
        for group, fields in PARAMETERS.items() for name, *_ in fields
    }
    values['TEMPLATE_SCALES'] = ', '.join(map(str, engine.TEMPLATE_SCALES))
    return values


class SettingsTests(unittest.TestCase):
    def test_defaults_and_negative_monitor_origin(self):
        values = default_values()
        values['left'] = '-1920'
        parsed = parse_settings(values)
        self.assertEqual(parsed['left'], -1920)
        self.assertEqual(parsed['THRESHOLD'], engine.THRESHOLD)

    def test_invalid_values_cannot_reach_automation(self):
        for name, value in (
            ('THRESHOLD', 'nan'), ('THRESHOLD', '1.1'),
            ('RALLY_ENTRY_DELAY', '-1'), ('width', '0'),
            ('BASE_MISSING_LIMIT', '1.5'), ('HUNT_SCROLL_STEPS', 'inf'),
            ('TEMPLATE_SCALES', ''), ('TEMPLATE_SCALES', '1, nan'),
        ):
            with self.subTest(name=name, value=value):
                values = default_values()
                values[name] = value
                with self.assertRaises(ValueError):
                    parse_settings(values)


class StopTests(unittest.TestCase):
    def tearDown(self):
        engine.STOP_EVENT.clear()

    def test_stop_releases_held_mouse(self):
        template = {'last_clicked': 0}
        with patch.object(engine.pyautogui, 'moveTo'), \
                patch.object(engine.pyautogui, 'mouseDown', side_effect=engine.STOP_EVENT.set), \
                patch.object(engine.pyautogui, 'mouseUp') as release:
            with self.assertRaises(engine.AutomationStopped):
                engine._hold_template(template, (0, 0), {'w': 10, 'h': 10}, 60)
            release.assert_called_once()

    def test_runtime_click_delay_uses_current_setting(self):
        with patch.object(engine, 'SEQUENCE_AFTER_CLICK_DELAY', 0.37), \
                patch.object(engine, '_grab_frame'), \
                patch.object(engine, '_match', return_value=(1, (0, 0), {})), \
                patch.object(engine, '_click_template'), \
                patch.object(engine, '_sleep') as sleep:
            self.assertTrue(engine._detect_and_click_within(None, {'name': 'test'}, 1))
            sleep.assert_called_once_with(0.37)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.saved = {name: value for name, value in vars(engine).items() if name.isupper()}
        self.saved['MONITOR_REGION'] = dict(engine.MONITOR_REGION)
        # 設定檔改寫到暫存目錄，避免讀到或覆蓋使用者真正存下的預設。
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings_path = Path(directory.name) / 'settings.json'
        patcher = patch('dailywork_gui.SETTINGS_PATH', self.settings_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = tk.Tk()
        self.window = DailyWorkWindow(self.root, engine)
        self.root.update()

    def tearDown(self):
        engine.STOP_EVENT.set()
        if self.window.worker is not None:
            self.window.worker.join(timeout=3)
        try:
            self.root.after_cancel(self.window.poll_id)
            self.root.destroy()
        except tk.TclError:
            pass
        for name, value in self.saved.items():
            setattr(engine, name, value)
        engine.STOP_EVENT.clear()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_start_minimizes_applies_options_and_can_restart(self):
        entered = threading.Event()

        def fake_run():
            entered.set()
            engine._sleep(60)

        for variable in self.window.features.values():
            variable.set(False)
        self.window.features['ENABLE_HELP_DETECTION'].set(True)
        self.window.values['RALLY_ENTRY_DELAY'].set('1.25')
        with patch.object(engine, 'solve_screen_detection', side_effect=fake_run) as run:
            self.window.start()
            self.root.update()
            self.assertEqual(self.root.state(), 'iconic')
            self.assertEqual(engine.TARGET_IMAGES, [engine.HELP_IMAGE])
            self.assertEqual(engine.RALLY_ENTRY_DELAY, 1.25)
            self.window.start()
            self.pump_until(entered.is_set)
            self.assertEqual(run.call_count, 1)
            self.window.stop()
            self.pump_until(lambda: self.window.worker is None)
            self.assertEqual(self.root.state(), 'normal')
            entered.clear()
            self.window.start()
            self.pump_until(entered.is_set)
            self.assertEqual(run.call_count, 2)
            self.window.close()
            self.pump_until(lambda: self.window.worker is None)
            with self.assertRaises(tk.TclError):
                self.root.winfo_exists()

    def test_invalid_input_keeps_window_open_and_engine_unchanged(self):
        self.window.values['THRESHOLD'].set('nan')
        with patch('dailywork_gui.messagebox.showerror') as error:
            self.window.start()
            error.assert_called_once()
        self.assertIsNone(self.window.worker)
        self.assertEqual(self.root.state(), 'normal')
        self.assertEqual(engine.THRESHOLD, self.saved['THRESHOLD'])

    def reopen(self):
        self.root.after_cancel(self.window.poll_id)
        self.root.destroy()
        self.root = tk.Tk()
        self.window = DailyWorkWindow(self.root, engine)
        self.root.update()

    def test_saved_settings_become_next_defaults(self):
        self.window.features['ENABLE_GATHER_SEQUENCE'].set(True)
        self.window.features['ENABLE_HELP_DETECTION'].set(False)
        self.window.values['RALLY_ENTRY_DELAY'].set('2.5')
        self.window.values['left'].set('-1920')
        self.window.values['TEMPLATE_SCALES'].set('0.9, 1.1')
        self.window.click_mode.set('固定座標')
        self.window.save()
        self.assertTrue(self.settings_path.exists())
        self.assertEqual(engine.RALLY_ENTRY_DELAY, self.saved['RALLY_ENTRY_DELAY'])  # 儲存不直接改執行中的設定
        self.reopen()
        self.assertTrue(self.window.features['ENABLE_GATHER_SEQUENCE'].get())
        self.assertFalse(self.window.features['ENABLE_HELP_DETECTION'].get())
        self.assertEqual(self.window.values['RALLY_ENTRY_DELAY'].get(), '2.5')
        self.assertEqual(self.window.values['left'].get(), '-1920')
        self.assertEqual(self.window.values['TEMPLATE_SCALES'].get(), '0.9, 1.1')
        self.assertEqual(self.window.click_mode.get(), '固定座標')
        self.assertIn('已載入', self.window.notice.cget('text'))

    def test_invalid_values_are_not_saved(self):
        self.window.values['THRESHOLD'].set('2')
        with patch('dailywork_gui.messagebox.showerror') as error:
            self.window.save()
        error.assert_called_once()
        self.assertFalse(self.settings_path.exists())

    def test_damaged_settings_file_falls_back_to_defaults(self):
        self.settings_path.write_text('{損毀', encoding='utf-8')
        self.reopen()
        self.assertEqual(self.window.values['THRESHOLD'].get(), str(engine.THRESHOLD))
        self.assertIn('無法讀取', self.window.notice.cget('text'))

    def test_saved_values_with_wrong_types_are_ignored(self):
        self.settings_path.write_text(json.dumps({
            'features': {'ENABLE_HELP_DETECTION': 'yes'},
            'values': {'THRESHOLD': 'abc', 'RALLY_ENTRY_DELAY': 1.5, 'TEMPLATE_SCALES': 'x'},
            'click_mode': 'nowhere',
        }), encoding='utf-8')
        self.reopen()
        self.assertEqual(self.window.features['ENABLE_HELP_DETECTION'].get(), engine.ENABLE_HELP_DETECTION)
        self.assertEqual(self.window.values['THRESHOLD'].get(), str(engine.THRESHOLD))
        self.assertEqual(self.window.values['RALLY_ENTRY_DELAY'].get(), '1.5')
        self.assertEqual(self.window.values['TEMPLATE_SCALES'].get(), ', '.join(map(str, engine.TEMPLATE_SCALES)))

    def test_worker_error_restores_window_and_reports_failure(self):
        with patch.object(engine, 'solve_screen_detection', side_effect=RuntimeError('測試錯誤')), \
                patch('dailywork_gui.messagebox.showerror') as error:
            self.window.start()
            self.pump_until(lambda: self.window.worker is None)
            self.assertIn('測試錯誤', self.window.failure)
            self.assertEqual(self.root.state(), 'normal')
            error.assert_called_once()


if __name__ == '__main__':
    unittest.main()
