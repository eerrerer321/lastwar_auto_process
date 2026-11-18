"""DailyWork 的桌面操作介面，沿用原有偵測與序列。"""
import json
import math
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import messagebox, ttk


FEATURES = (
    ('ENABLE_RALLY_SEQUENCE', '參加集結'),
    ('ENABLE_HELP_DETECTION', '幫助盟友'),
    ('ENABLE_HEAL_SEQUENCE', '分批治療'),
    ('ENABLE_TAKEMYHEAL_DETECTION', '領取治療（一般）'),
    ('ENABLE_TAKEMYHEAL8LV_DETECTION', '領取治療（8 級）'),
    ('ENABLE_GATHER_SEQUENCE', '自動採集'),
    ('ENABLE_HUNT_ZOMBIE_SEQUENCE', '狩獵金幣小殭屍'),
    ('ENABLE_DONATE_SEQUENCE', '同盟捐獻'),
    ('ENABLE_BASE_MONITORING', '基地監測'),
    ('ENABLE_EXIT_GAME_DETECTION', '退出遊戲圖片偵測'),
)

# 欄位：名稱、中文標籤、數值型別、下限（含）、上限（含，None 表示不限制）。
PARAMETERS = {
    '一般': (
        ('THRESHOLD', '圖片匹配門檻（0.01～1）', float, 0.01, 1),
        ('INDIVIDUAL_COOLDOWN', '一般圖片點擊冷卻（秒）', float, 0, None),
        ('SEQUENCE_POLLING_INTERVAL', '序列偵測間隔（秒）', float, 0.01, None),
        ('SEQUENCE_AFTER_CLICK_DELAY', '序列點擊後緩衝（秒）', float, 0, None),
        ('FIXED_CLICK_X', '固定點擊 X（像素）', int, None, None),
        ('FIXED_CLICK_Y', '固定點擊 Y（像素）', int, None, None),
    ),
    '集結': (
        ('RALLY_ENTRY_DELAY', '集結進入前延遲（秒）', float, 0, None),
        ('RALLY_SEQUENCE_COOLDOWN', '集結冷卻（秒）', float, 0, None),
        ('RALLY_SEQUENCE_TIMEOUT', '集結逾時（秒）', float, 0.01, None),
    ),
    '治療': (
        ('HEAL_SEQUENCE_COOLDOWN', '治療冷卻（秒）', float, 0, None),
        ('HEAL_SEQUENCE_TIMEOUT', '治療逾時（秒）', float, 0.01, None),
    ),
    '採集': (
        ('GATHER_CHECK_INTERVAL', '採集檢查間隔（秒）', float, 0.01, None),
        ('GATHER_STEP_TIMEOUT', '一般步驟逾時（秒）', float, 0.01, None),
        ('GATHER_SLOW_STEP_TIMEOUT', '慢換頁步驟逾時（秒）', float, 0.01, None),
        ('GATHER_FAST_STEP_DELAY', '一般點擊後緩衝（秒）', float, 0, None),
        ('GATHER_SLOW_STEP_DELAY', '慢換頁點擊後緩衝（秒）', float, 0, None),
        ('GATHER_QUANTITY_CLICK_RATIO', '採集數量位置比例（0～1）', float, 0, 1),
    ),
    '狩獵': (
        ('HUNT_CHECK_INTERVAL', '狩獵檢查間隔（秒）', float, 0.01, None),
        ('HUNT_STEP_TIMEOUT', '一般步驟逾時（秒）', float, 0.01, None),
        ('HUNT_EVENT_MIDPOINT_TIMEOUT', '特殊事件中心點逾時（秒）', float, 0.01, None),
        ('HUNT_SCROLL_STEPS', '縮小滾輪段數', int, 1, None),
        ('HUNT_SCROLL_INTERVAL', '每段滾輪間隔（秒）', float, 0, None),
    ),
    '捐獻': (
        ('DONATE_INTERVAL', '捐獻間隔（秒；7200＝2 小時）', float, 0.01, None),
        ('DONATE_STEP_TIMEOUT', '捐獻步驟逾時（秒）', float, 0.01, None),
        ('DONATE_HOLD_SECONDS', '捐獻長按時間（秒）', float, 0.01, None),
        ('DONATE_AFTER_HOLD_DELAY', '捐獻放開後等待（秒）', float, 0, None),
        ('DONATE_ESC_COUNT', '捐獻結束 ESC 次數', int, 1, None),
        ('DONATE_ESC_INTERVAL', 'ESC 間隔（秒）', float, 0, None),
    ),
    '基地': (
        ('BASE_CHECK_INTERVAL', '基地檢查間隔（秒）', float, 0.01, None),
        ('BASE_MISSING_LIMIT', '基地連續未出現次數', int, 1, None),
    ),
    '畫面': (
        ('left', '擷取範圍左側 X（像素）', int, None, None),
        ('top', '擷取範圍頂端 Y（像素）', int, None, None),
        ('width', '擷取範圍寬度（像素）', int, 1, None),
        ('height', '擷取範圍高度（像素）', int, 1, None),
    ),
}

CLICK_MODES = (('center', '圖片中心'), ('fixed', '固定座標'))

# 「儲存為預設」寫入的設定檔放在程式旁邊；打包成 exe 時放 exe 旁，而不是每次都會清掉的解壓暫存目錄。
if getattr(sys, 'frozen', False):
    SETTINGS_PATH = Path(sys.executable).resolve().parent / 'dailywork_settings.json'
else:
    SETTINGS_PATH = Path(__file__).resolve().parent / 'dailywork_settings.json'


def parse_settings(values):
    """先驗證所有輸入，避免只套用部分設定就開始執行。"""
    parsed = {}
    for fields in PARAMETERS.values():
        for name, label, kind, minimum, maximum in fields:
            try:
                value = kind(values[name])
                if not math.isfinite(value):
                    raise ValueError()
                if minimum is not None and value < minimum:
                    raise ValueError()
                if maximum is not None and value > maximum:
                    raise ValueError()
            except (ValueError, OverflowError):
                bounds = '整數' if kind is int else '數字'
                if minimum is not None:
                    bounds += f'，最小 {minimum}'
                if maximum is not None:
                    bounds += f'，最大 {maximum}'
                raise ValueError(f'{label}：請輸入有效{bounds}。') from None
            parsed[name] = value
    try:
        scales = tuple(float(item.strip()) for item in values['TEMPLATE_SCALES'].split(','))
        if not scales or any(not math.isfinite(v) or not 0.1 <= v <= 3 for v in scales):
            raise ValueError()
    except ValueError:
        raise ValueError('模板倍率：請用逗號分隔 0.1～3 的數字，例如 0.95, 1.0, 1.05。') from None
    parsed['TEMPLATE_SCALES'] = scales
    return parsed


def load_saved_settings(path):
    """讀取「儲存為預設」的設定；沒有檔案回傳空 dict，檔案損毀丟 ValueError。"""
    try:
        with open(path, encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError(f'無法讀取設定檔 {path}：{error}') from None
    if not isinstance(data, dict):
        raise ValueError(f'設定檔格式不正確：{path}')
    return data


def write_saved_settings(path, data):
    """先寫暫存檔再取代，避免寫到一半中斷留下損毀的設定檔。"""
    temporary = path.with_name(path.name + '.tmp')
    with open(temporary, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def _section(data, key):
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _split_label(label):
    """「集結冷卻（秒）」→（「集結冷卻」,「秒」），括號內容改成右側的單位提示。"""
    if label.endswith('）') and '（' in label:
        name, hint = label[:-1].split('（', 1)
        return name, hint
    return label, ''


class LogWriter:
    def __init__(self, messages):
        self.messages = messages

    def write(self, text):
        if text:
            try:
                self.messages.put_nowait(text)
            except queue.Full:
                pass  # 僅限制畫面紀錄量，不阻塞自動化或停止操作。
        return len(text)

    def flush(self):
        pass


# ---------------------------------------------------------------- 外觀主題 --
# 只用 tkinter 內建的 ttk：圓角、開關等外觀以程式繪製的反鋸齒圖片當作 ttk 圖像元素（九宮格拉伸）。
C = {
    'bg': '#0E1014', 'card': '#161A21', 'line': '#262B35', 'field': '#0F1217', 'field_line': '#2C323D',
    'nav_line': '#232831', 'hover': '#1C2129', 'tab_on': '#262C37', 'chip': '#1F242D', 'note': '#1A1F27',
    'console': '#0B0D11', 'console_line': '#1C2028', 'text': '#E7EAF0', 'soft': '#C5CBD6',
    'muted': '#8B93A3', 'dim': '#6F7787', 'console_text': '#AEB6C2', 'accent': '#F2A93B',
    'accent_hover': '#FFB950', 'accent_down': '#D9912B', 'on_accent': '#14110A', 'ok': '#4ADE80',
    'warn': '#F2C14E',
}
STATUS_TONES = {
    'idle': ('#1F242D', '#A3ABB9'),
    'run': ('#11291A', '#4ADE80'),
    'warn': ('#2B2210', '#F2C14E'),
    'fail': ('#2D1416', '#FF7B72'),
}
UI_FONT = 'Microsoft JhengHei UI'
LOG_FONT = (UI_FONT, -17, 'bold')  # 紀錄多為中文，用等寬字型時中文會落到細明體類的後備字型。


def _font(size):
    return (UI_FONT, -size, 'bold')  # 全介面粗體；負數為像素，與繪製的圖片同比例縮放。


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _coverage(px, py, width, height, radius):
    """像素中心到圓角矩形的有號距離換算成覆蓋率，用於反鋸齒。"""
    qx = abs(px - width / 2) - (width / 2 - radius)
    qy = abs(py - height / 2) - (height / 2 - radius)
    distance = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius
    return min(max(0.5 - distance, 0), 1)


def _box(left, top, width, height, radius, fill, line=None):
    """一個圓角矩形圖層；有 line 時先畫 1px 外框再畫內部。"""
    if line is None:
        return [(left, top, width, height, radius, _rgb(fill))]
    return [
        (left, top, width, height, radius, _rgb(line)),
        (left + 1, top + 1, width - 2, height - 2, max(radius - 1, 0), _rgb(fill)),
    ]


def _paint(master, width, height, background, layers):
    rows = []
    base = _rgb(background)
    for y in range(height):
        row = []
        for x in range(width):
            color = base
            for left, top, w, h, radius, fill in layers:
                alpha = _coverage(x + 0.5 - left, y + 0.5 - top, w, h, radius)
                if alpha:
                    color = tuple(round(a + (b - a) * alpha) for a, b in zip(color, fill))
            row.append('#%02x%02x%02x' % color)
        rows.append('{%s}' % ' '.join(row))
    image = tk.PhotoImage(master=master, width=width, height=height)
    image.put(' '.join(rows))
    return image


def _widen(master, small, border, room=120):
    """把九宮格圖的中段擴大 room 像素（用 Tk 內建的 photo copy 平鋪，速度快）。

    ttk 圖像元素是用圖片中段「平鋪」填滿元件；中段只有幾像素時，一張卡片每次重繪
    要呼叫上千次繪圖，而開窗時子元件排版會讓外層反覆重繪，實測整個視窗開啟要數十秒以上。
    """
    if border == 0:
        return small
    if isinstance(border, int):
        border = (border, border)
    left, top = border[0], border[1]
    right, bottom = (border[2], border[3]) if len(border) == 4 else (left, top)
    width, height = small.width(), small.height()
    big = tk.PhotoImage(master=master, width=width + room, height=height + room)
    columns = ((0, left, 0, left), (left, width - right, left, width - right + room),
               (width - right, width, width - right + room, width + room))
    rows = ((0, top, 0, top), (top, height - bottom, top, height - bottom + room),
            (height - bottom, height, height - bottom + room, height + room))
    for sx0, sx1, dx0, dx1 in columns:
        for sy0, sy1, dy0, dy1 in rows:
            big.tk.call(big, 'copy', small, '-from', sx0, sy0, sx1, sy1, '-to', dx0, dy0, dx1, dy1)
    return big


def _mix(color, other, amount):
    return '#%02x%02x%02x' % tuple(round(a + (b - a) * amount) for a, b in zip(_rgb(color), _rgb(other)))


def _build_theme(root):
    """建立所有 ttk 樣式，回傳圖片（呼叫端需保留參照，否則圖片會被回收）。"""
    style = ttk.Style(root)
    style.theme_use('clam')
    images = {}

    def image(name, width, height, background, layers):
        images[name] = _paint(root, width, height, background, layers)
        return images[name]

    def element(name, border, default, *states):
        # padding 明確設 0：預設會沿用 border 當內距，讓元件莫名變高；內距一律由各樣式的 padding 控制。
        # width/height 設回小圖尺寸：否則元件最小尺寸會變成擴大後的圖片大小。
        width, height = default.width(), default.height()
        default = images[f'{name}#0'] = _widen(root, default, border)
        states = list(states)
        for index, (*state, picture) in enumerate(states, start=1):
            states[index - 1] = (*state, _widen(root, picture, border))
            images[f'{name}#{index}'] = states[index - 1][-1]
        style.element_create(name, 'image', default, *states, border=border, padding=0, sticky='nsew',
                             width=width, height=height)

    def wrapped(inner):
        return lambda name: [(name, {'sticky': 'nsew', 'children': inner})]

    style.configure('.', background=C['bg'], foreground=C['text'], font=_font(19), borderwidth=0)
    style.configure('App.TFrame', background=C['bg'])
    style.configure('Surface.TFrame', background=C['card'])
    style.configure('ConsoleSurface.TFrame', background=C['console'])
    for name, background, foreground, font in (
        ('Title', C['bg'], C['text'], _font(26)),
        ('Subtitle', C['bg'], C['muted'], _font(16)),
        ('Footer', C['bg'], C['muted'], _font(16)),
        ('Section', C['card'], C['text'], _font(20)),
        ('FieldName', C['card'], C['soft'], _font(19)),
        ('Hint', C['card'], C['muted'], _font(16)),
        ('ConsoleTitle', C['console'], C['text'], _font(18)),
        ('ConsoleHint', C['console'], C['muted'], _font(16)),
        ('Note', C['note'], '#AEB6C2', _font(17)),
    ):
        style.configure(f'{name}.TLabel', background=background, foreground=foreground, font=font)
    for name, color in (('muted', C['muted']), ('ok', C['ok']), ('warn', C['warn'])):
        style.configure(f'{name}.Notice.TLabel', background=C['bg'], foreground=color, font=_font(16))

    # 圓角容器：卡片、紀錄區、分頁列、提示框。
    for name, size, radius, background, fill, line, border in (
        ('Card', 36, 14, C['bg'], C['card'], C['line'], 15),
        ('Console', 36, 14, C['bg'], C['console'], C['line'], 15),
        ('Nav', 26, 10, C['card'], C['field'], C['nav_line'], 11),
        ('SegBox', 24, 9, C['card'], C['field'], C['field_line'], 10),
        ('NoteBox', 24, 9, C['card'], C['note'], C['line'], 10),
    ):
        element(f'{name}.bg', border, image(name, size, size, background, _box(0, 0, size, size, radius, fill, line)))
        style.layout(f'{name}.TFrame', [(f'{name}.bg', {'sticky': 'nsew'})])

    label_layout = wrapped([('Label.padding', {'sticky': 'nsew', 'children': [('Label.label', {'sticky': 'nsew'})]})])

    # 狀態膠囊與計數小標。
    for tone, (fill, foreground) in STATUS_TONES.items():
        element(f'{tone}.Pill.bg', (14, 13), image(f'pill_{tone}', 36, 28, C['bg'], _box(0, 0, 36, 28, 14, fill)))
        style.layout(f'{tone}.Pill.TLabel', label_layout(f'{tone}.Pill.bg'))
        style.configure(f'{tone}.Pill.TLabel', foreground=foreground, font=_font(16), padding=(12, 3))
    element('Chip.bg', (13, 12), image('chip', 32, 26, C['card'], _box(0, 0, 32, 26, 13, C['chip'])))
    style.layout('Chip.TLabel', label_layout('Chip.bg'))
    style.configure('Chip.TLabel', foreground='#A3ABB9', font=_font(16), padding=(11, 2))

    # 按鈕：主要（執行）、危險（停止）、次要（儲存為預設）。
    button_layout = wrapped([('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})])
    for name, normal, hover, down, disabled, foreground, foreground_disabled in (
        ('Accent', (C['accent'], None), (C['accent_hover'], None), (C['accent_down'], None),
         ('#2A271F', None), C['on_accent'], '#6F6857'),
        ('Danger', ('#2A1719', '#5A272C'), ('#361C1F', '#6E2F35'), ('#221214', '#5A272C'),
         ('#151920', '#232831'), '#FF8A80', '#5B6270'),
        ('Ghost', (C['bg'], C['field_line']), (C['hover'], '#3A414E'), ('#13161C', C['field_line']),
         (C['bg'], '#1E232B'), C['text'], C['dim']),
    ):
        states = [image(f'{name}_{state}', 28, 28, C['bg'], _box(0, 0, 28, 28, 11, *colors))
                  for state, colors in (('normal', normal), ('hover', hover), ('down', down), ('disabled', disabled))]
        element(f'{name}.bg', 12, states[0], ('disabled', states[3]), ('pressed', states[2]), ('active', states[1]))
        style.layout(f'{name}.TButton', button_layout(f'{name}.bg'))
        style.configure(f'{name}.TButton', foreground=foreground, font=_font(19), padding=(16, 7), anchor='center')
        style.map(f'{name}.TButton', foreground=[('disabled', foreground_disabled)])

    # 輸入框：一般 / 聚焦 / 停用。
    field = [image(f'field_{state}', 24, 24, C['card'], _box(0, 0, 24, 24, 10, fill, line))
             for state, fill, line in (('normal', C['field'], C['field_line']), ('focus', C['field'], C['accent']),
                                       ('disabled', '#12151B', C['nav_line']))]
    element('Field.bg', 11, field[0], ('disabled', field[2]), ('focus', field[1]))
    style.layout('Field.TEntry', wrapped([('Entry.padding', {'sticky': 'nsew', 'children': [
        ('Entry.textarea', {'sticky': 'nsew'})]})])('Field.bg'))
    style.configure('Field.TEntry', foreground=C['text'], insertcolor=C['text'], padding=(12, 5),
                    selectbackground=C['accent'], selectforeground=C['on_accent'])
    style.map('Field.TEntry', foreground=[('disabled', C['dim'])])

    # 分頁列與點擊位置的分段按鈕（底色同輸入框）。
    tab_on = image('tab_on', 24, 24, C['field'], _box(0, 0, 24, 24, 9, C['tab_on']))
    tab_off = image('tab_off', 24, 24, C['field'], [])
    element('Tab.bg', 10, tab_off, ('selected', tab_on))
    radio_layout = wrapped([('Radiobutton.padding', {'sticky': 'nsew', 'children': [
        ('Radiobutton.label', {'sticky': ''})]})])
    for name, padding in (('Tab', (8, 5)), ('Seg', (8, 3))):
        style.layout(f'{name}.TRadiobutton', radio_layout('Tab.bg'))
        style.configure(f'{name}.TRadiobutton', foreground=C['muted'], font=_font(19), padding=padding)
        style.map(f'{name}.TRadiobutton', foreground=[
            ('disabled', C['dim']), ('selected', '#FFFFFF'), ('active', C['text'])])

    # 功能開關列：整列可點、滑過有底色，右側為開關。
    row = image('row', 24, 24, C['card'], [])
    row_hover = image('row_hover', 24, 24, C['card'], _box(0, 0, 24, 24, 10, C['hover']))
    element('Switch.row', 11, row, ('disabled', row), ('active', row_hover))

    def switch(name, background, track, knob, on):
        return image(name, 46, 26, background, _box(0, 0, 46, 26, 13, track) + _box(23 if on else 3, 3, 20, 20, 10, knob))

    dim_on, dim_knob = _mix(C['accent'], C['card'], 0.55), _mix('#FFFFFF', C['card'], 0.55)
    element('Switch.indicator', 0,
            switch('sw_off', C['card'], C['field_line'], C['muted'], False),
            ('disabled', 'selected', switch('sw_on_dis', C['card'], dim_on, dim_knob, True)),
            ('disabled', switch('sw_off_dis', C['card'], '#1E232B', '#3C4350', False)),
            ('active', 'selected', switch('sw_on_hover', C['hover'], C['accent'], '#FFFFFF', True)),
            ('active', switch('sw_off_hover', C['hover'], C['field_line'], C['muted'], False)),
            ('selected', switch('sw_on', C['card'], C['accent'], '#FFFFFF', True)))
    style.layout('Switch.TCheckbutton', wrapped([('Checkbutton.padding', {'sticky': 'nsew', 'children': [
        ('Switch.indicator', {'side': 'right', 'sticky': ''}),
        ('Checkbutton.label', {'side': 'left', 'sticky': 'w', 'expand': 1}),
    ]})])('Switch.row'))
    style.configure('Switch.TCheckbutton', foreground=C['text'], font=_font(20), padding=(14, 12))
    style.map('Switch.TCheckbutton', foreground=[('disabled', C['dim'])])

    # 紀錄區捲軸：無箭頭的細捲軸。
    style.layout('Log.Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
        ('Vertical.Scrollbar.thumb', {'expand': 1, 'sticky': 'nsew'})]})])
    style.configure('Log.Vertical.TScrollbar', troughcolor=C['console'], background=C['field_line'],
                    bordercolor=C['console'], lightcolor=C['field_line'], darkcolor=C['field_line'],
                    gripcount=0, arrowsize=10)
    style.map('Log.Vertical.TScrollbar', background=[('active', '#3A414E')],
              lightcolor=[('active', '#3A414E')], darkcolor=[('active', '#3A414E')])

    # 標題旁的準星圖示：以 42px 設計，等比放大到 46px 配合標題字級。
    k, dark, accent = 46 / 42, C['on_accent'], C['accent']
    shapes = ((0, 0, 42, 42, 11, accent), (13.7, 13.7, 14.6, 14.6, 7.3, dark), (15.5, 15.5, 11, 11, 5.5, accent),
              (20.1, 10.9, 1.8, 5.5, 0.9, dark), (20.1, 25.6, 1.8, 5.5, 0.9, dark), (10.9, 20.1, 5.5, 1.8, 0.9, dark),
              (25.6, 20.1, 5.5, 1.8, 0.9, dark), (19.5, 19.5, 3, 3, 1.5, dark))
    image('logo', 46, 46, C['bg'], [layer for x, y, w, h, r, color in shapes
                                    for layer in _box(x * k, y * k, w * k, h * k, r * k, color)])
    return images


def _dark_title_bar(root):
    """Windows 10/11 讓標題列跟著深色主題；其他平台或舊版 Windows 直接略過。"""
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
    except (AttributeError, OSError):
        pass


class DailyWorkWindow:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.worker = None
        self.closing = False
        self.failure = None
        self.messages = queue.Queue(maxsize=2000)
        self.inputs = []
        self.features = {}
        self.values = {}
        self.pages = {}
        root.title('LastWar 日常自動化')
        root.geometry('1000x760')
        root.minsize(980, 740)
        root.configure(bg=C['bg'])
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.images = _build_theme(root)
        _dark_title_bar(root)

        try:
            saved = load_saved_settings(SETTINGS_PATH)
            notice = ('已載入上次儲存的設定', 'ok') if saved else (
                '設定只套用於本次開啟；按「儲存為預設」可保留到下次。', 'muted')
        except ValueError as error:
            saved = {}
            notice = ('設定檔無法讀取，已改用程式預設值', 'warn')
            self.messages.put_nowait(f'{error}\n')

        body = ttk.Frame(root, padding=(18, 12, 18, 10), style='App.TFrame')
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)
        self.build_header(body)
        self.build_features(body, _section(saved, 'features'))
        right = ttk.Frame(body, style='App.TFrame')
        right.grid(row=1, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.build_parameters(right, _section(saved, 'values'), saved.get('click_mode'))
        self.build_log(right)
        footer = ttk.Frame(body, style='App.TFrame')
        footer.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        ttk.Label(footer, text='從工作列還原視窗可按「停止」；關閉視窗也會停止。', style='Footer.TLabel').pack(side='left')
        self.notice = ttk.Label(footer)
        self.notice.pack(side='right')
        self.set_notice(*notice)
        self.poll_id = root.after(100, self.poll)

    # ------------------------------------------------------------ 版面 --
    def build_header(self, body):
        header = ttk.Frame(body, style='App.TFrame')
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        tk.Label(header, image=self.images['logo'], bg=C['bg'], bd=0).pack(side='left')
        # 按鈕要比標題區先 pack：pack 依先後分配空間，先排的永遠拿到完整寬度，
        # 狀態文字再長也只會壓縮標題區，不會把「儲存為預設」擠掉。
        self.start_button = ttk.Button(header, text='▶  執行', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='right')
        self.stop_button = ttk.Button(header, text='■  停止', style='Danger.TButton', command=self.stop, state='disabled')
        self.stop_button.pack(side='right', padx=8)
        self.save_button = ttk.Button(header, text='儲存為預設', style='Ghost.TButton', command=self.save)
        self.save_button.pack(side='right')
        titles = ttk.Frame(header, style='App.TFrame')
        titles.pack(side='left', fill='x', expand=True, padx=12)
        title_row = ttk.Frame(titles, style='App.TFrame')
        title_row.pack(anchor='w')
        ttk.Label(title_row, text='LastWar 日常自動化', style='Title.TLabel').pack(side='left')
        self.status = tk.StringVar(self.root)
        self.status_pill = ttk.Label(title_row)
        self.status_pill.pack(side='left', padx=10)
        self.set_status('尚未執行', 'idle')
        ttk.Label(titles, text='勾選功能並調整參數；按執行後會自動縮小到工作列。', style='Subtitle.TLabel').pack(anchor='w')

    def build_features(self, body, saved):
        card = ttk.Frame(body, style='Card.TFrame', padding=(6, 12, 6, 6))
        card.grid(row=1, column=0, sticky='nsw', padx=(0, 12))
        card.columnconfigure(0, minsize=290)
        head = ttk.Frame(card, style='Surface.TFrame', padding=(14, 0, 14, 4))
        head.grid(row=0, column=0, sticky='ew')
        ttk.Label(head, text='啟用功能', style='Section.TLabel').pack(side='left')
        self.feature_count = ttk.Label(head, style='Chip.TLabel')
        self.feature_count.pack(side='right')
        for index, (name, label) in enumerate(FEATURES, start=1):
            value = saved.get(name)
            variable = tk.BooleanVar(self.root, value=value if isinstance(value, bool) else getattr(self.engine, name))
            variable.trace_add('write', lambda *_: self.update_feature_count())
            self.features[name] = variable
            widget = ttk.Checkbutton(card, text=label, variable=variable, style='Switch.TCheckbutton')
            widget.grid(row=index, column=0, sticky='ew')
            self.inputs.append(widget)
        self.update_feature_count()

    def build_parameters(self, parent, saved, saved_click_mode):
        card = ttk.Frame(parent, style='Card.TFrame', padding=(16, 12, 16, 2))
        card.grid(row=0, column=0, sticky='ew')
        card.columnconfigure(0, weight=1)
        nav = ttk.Frame(card, style='Nav.TFrame', padding=4)
        nav.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        self.page = tk.StringVar(self.root, value='一般')
        stack = ttk.Frame(card, style='Surface.TFrame')
        stack.grid(row=2, column=0, sticky='nsew')
        stack.columnconfigure(0, weight=1)
        for title, fields in PARAMETERS.items():
            ttk.Radiobutton(nav, text=title, value=title, variable=self.page, style='Tab.TRadiobutton',
                            command=self.show_page).pack(side='left', fill='x', expand=True)
            page = ttk.Frame(stack, style='Surface.TFrame')
            page.grid(row=0, column=0, sticky='nsew')
            page.columnconfigure((0, 1), weight=1, uniform='field')
            self.pages[title] = page
            cells = []
            for name, label, *_rest in fields:
                default = self.engine.MONITOR_REGION[name] if title == '畫面' else getattr(self.engine, name)
                value = saved.get(name)
                cells.append(self.add_entry(page, name, label, value if _is_number(value) else default))
            if title == '一般':
                scales = saved.get('TEMPLATE_SCALES')
                if not (isinstance(scales, list) and scales and all(_is_number(v) for v in scales)):
                    scales = self.engine.TEMPLATE_SCALES
                cells.append(self.add_entry(page, 'TEMPLATE_SCALES', '模板倍率（逗號分隔）', ', '.join(map(str, scales))))
                cells.append(self.add_click_mode(page, saved_click_mode))
            for index, cell in enumerate(cells):
                cell.grid(row=index // 2, column=index % 2, sticky='ew', pady=(0, 8),
                          padx=(0, 8) if index % 2 == 0 else (8, 0))
            if title == '畫面':
                note = ttk.Frame(page, style='NoteBox.TFrame', padding=(12, 7))
                note.grid(row=len(cells), column=0, columnspan=2, sticky='ew', pady=(0, 8))
                ttk.Label(note, text='ⓘ  既有圖片搜尋區域仍使用螢幕絕對座標；\n     遊戲位置改變時，需另行量測 ROI。',
                          style='Note.TLabel').pack(anchor='w')
        self.show_page()

    def field_cell(self, page, label):
        cell = ttk.Frame(page, style='Surface.TFrame')
        name, hint = _split_label(label)
        head = ttk.Frame(cell, style='Surface.TFrame')
        head.pack(fill='x', pady=(0, 3))
        ttk.Label(head, text=name, style='FieldName.TLabel').pack(side='left')
        ttk.Label(head, text=hint, style='Hint.TLabel').pack(side='right')
        return cell

    def add_entry(self, page, name, label, value):
        cell = self.field_cell(page, label)
        variable = tk.StringVar(self.root, value=str(value))
        self.values[name] = variable
        widget = ttk.Entry(cell, textvariable=variable, style='Field.TEntry', font=_font(20), width=6)
        widget.pack(fill='x')
        self.inputs.append(widget)
        return cell

    def add_click_mode(self, page, saved_mode):
        cell = self.field_cell(page, '一般圖片點擊位置')
        mode = saved_mode if saved_mode in dict(CLICK_MODES) else self.engine.CLICK_MODE
        self.click_mode = tk.StringVar(self.root, value=dict(CLICK_MODES).get(mode, '固定座標'))
        box = ttk.Frame(cell, style='SegBox.TFrame', padding=3)
        box.pack(fill='x')
        for _mode, text in CLICK_MODES:
            widget = ttk.Radiobutton(box, text=text, value=text, variable=self.click_mode, style='Seg.TRadiobutton')
            widget.pack(side='left', fill='x', expand=True)
            self.inputs.append(widget)
        return cell

    def build_log(self, parent):
        card = ttk.Frame(parent, style='Console.TFrame', padding=5)
        card.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        head = ttk.Frame(card, style='ConsoleSurface.TFrame', padding=(11, 3, 11, 4))
        head.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(head, text='›_  執行紀錄', style='ConsoleTitle.TLabel').pack(side='left')
        ttk.Label(head, text='保留最近 1000 行', style='ConsoleHint.TLabel').pack(side='right')
        tk.Frame(card, height=1, bg=C['console_line']).grid(row=1, column=0, columnspan=2, sticky='ew')
        self.log = tk.Text(card, width=1, height=6, state='disabled', wrap='word', font=LOG_FONT, bg=C['console'],
                           fg=C['console_text'], relief='flat', bd=0, highlightthickness=0, padx=11, pady=6,
                           selectbackground='#2C3A52', selectforeground=C['text'], spacing1=1, spacing3=1,
                           insertbackground=C['text'])
        self.log.grid(row=2, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(card, orient='vertical', command=self.log.yview, style='Log.Vertical.TScrollbar')
        scrollbar.grid(row=2, column=1, sticky='ns', pady=(6, 4))
        self.log.configure(yscrollcommand=scrollbar.set)

    # ------------------------------------------------------------ 狀態 --
    def show_page(self):
        self.pages[self.page.get()].tkraise()

    def update_feature_count(self):
        enabled = sum(variable.get() for variable in self.features.values())
        self.feature_count.configure(text=f'已啟用 {enabled} / {len(FEATURES)}')

    def set_status(self, text, tone):
        self.status.set(text)
        self.status_pill.configure(text=f'●  {text}', style=f'{tone}.Pill.TLabel')

    def set_notice(self, text, tone):
        self.notice.configure(text=text, style=f'{tone}.Notice.TLabel')

    def current_values(self):
        return {name: variable.get() for name, variable in self.values.items()}

    def selected_click_mode(self):
        return 'center' if self.click_mode.get() == '圖片中心' else 'fixed'

    # ------------------------------------------------------------ 動作 --
    def save(self):
        try:
            settings = parse_settings(self.current_values())
        except ValueError as error:
            messagebox.showerror('參數有誤', str(error), parent=self.root)
            return
        settings['TEMPLATE_SCALES'] = list(settings['TEMPLATE_SCALES'])
        data = {
            'version': 1,
            'features': {name: variable.get() for name, variable in self.features.items()},
            'values': settings,
            'click_mode': self.selected_click_mode(),
        }
        try:
            write_saved_settings(SETTINGS_PATH, data)
        except OSError as error:
            messagebox.showerror('儲存失敗', f'無法寫入設定檔：{error}', parent=self.root)
            return
        self.set_notice('已儲存為預設，下次開啟會自動載入', 'ok')

    def start(self):
        if self.worker is not None:
            return
        try:
            if not any(variable.get() for variable in self.features.values()):
                raise ValueError('請至少勾選一個功能。')
            settings = parse_settings(self.current_values())
        except ValueError as error:
            messagebox.showerror('參數有誤', str(error), parent=self.root)
            return
        for name, variable in self.features.items():
            setattr(self.engine, name, variable.get())
        for name, value in settings.items():
            if name in self.engine.MONITOR_REGION:
                self.engine.MONITOR_REGION[name] = value
            else:
                setattr(self.engine, name, value)
        self.engine.CLICK_MODE = self.selected_click_mode()
        self.engine.TARGET_IMAGES = [
            getattr(self.engine, image) for flag, image in (
                ('ENABLE_TAKEMYHEAL_DETECTION', 'TAKEMYHEAL_IMAGE'),
                ('ENABLE_TAKEMYHEAL8LV_DETECTION', 'TAKEMYHEAL8LV_IMAGE'),
                ('ENABLE_HELP_DETECTION', 'HELP_IMAGE'),
                ('ENABLE_EXIT_GAME_DETECTION', 'EXIT_GAME_IMAGE'),
            ) if getattr(self.engine, flag)
        ]
        self.engine.STOP_EVENT.clear()
        self.failure = None
        for widget in self.inputs:
            widget.state(['disabled'])
        self.start_button.state(['disabled'])
        self.stop_button.state(['!disabled'])
        self.set_status('執行中', 'run')
        self.worker = threading.Thread(target=self.run, daemon=False)
        self.root.iconify()
        self.worker.start()

    def run(self):
        with redirect_stdout(LogWriter(self.messages)):
            try:
                self.engine._sleep(0.5)  # 留時間讓視窗完成最小化。
                self.engine.solve_screen_detection()
            except self.engine.AutomationStopped:
                print('\n--- 腳本已停止 ---')
            except Exception:
                self.failure = traceback.format_exc()
                print(self.failure)

    def stop(self):
        if self.worker is not None:
            self.engine.STOP_EVENT.set()
            self.stop_button.state(['disabled'])
            self.set_status('停止中…', 'warn')

    def close(self):
        self.closing = True
        if self.worker is None:
            self.root.after_cancel(self.poll_id)
            self.root.destroy()
        else:
            self.stop()

    def poll(self):
        chunks = []
        for _ in range(300):
            try:
                chunks.append(self.messages.get_nowait())
            except queue.Empty:
                break
        if chunks:
            self.log.configure(state='normal')
            self.log.insert('end', ''.join(chunks))
            if int(self.log.index('end-1c').split('.')[0]) > 1000:
                self.log.delete('1.0', 'end-1000l')
            self.log.see('end')
            self.log.configure(state='disabled')
        if self.worker is not None and not self.worker.is_alive():
            self.worker.join()
            self.worker = None
            if self.closing:
                self.root.destroy()
                return
            for widget in self.inputs:
                widget.state(['!disabled'])
            self.start_button.state(['!disabled'])
            self.stop_button.state(['disabled'])
            if self.failure:
                self.set_status('執行失敗', 'fail')  # 隨後的錯誤對話框會說明要看下方紀錄
            else:
                self.set_status('已停止', 'idle')
            self.root.deiconify()
            if self.failure:
                messagebox.showerror('執行失敗', '腳本已停止，詳細錯誤請查看下方紀錄。', parent=self.root)
        self.poll_id = self.root.after(100, self.poll)


def run_gui(engine):
    root = tk.Tk()
    window = DailyWorkWindow(root, engine)
    try:
        root.mainloop()
    finally:
        engine.STOP_EVENT.set()
        if window.worker is not None:
            window.worker.join()
