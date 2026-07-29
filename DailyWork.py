import cv2
import numpy as np
import mss
import pyautogui
import time
import random
import sys
from pathlib import Path

# 關閉 PyAutoGUI 角落緊急停止機制（避免滑鼠路徑經過 (0,0) 時被誤觸停止）
# 副作用：失去「滑鼠甩角落停腳本」這個熱鍵，要中止請用 Ctrl+C
pyautogui.FAILSAFE = False
# 降低 PyAutoGUI 每次 click / move / press 後的內建停頓，避免序列動作疊出遲鈍感。
pyautogui.PAUSE = 0.02

# 讓主控台能正確輸出 log 中的 emoji（✅⚠️ℹ️）與中文。
# 打包成 exe 後主控台預設常為 cp950 等非 UTF-8 編碼，直接 print emoji 會丟
# UnicodeEncodeError 導致整個程式崩潰閃退；這裡先切到 UTF-8，並對無法編碼的
# 字元改為替換而非報錯，確保在任何使用者的環境都不會因為輸出而中斷。
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# ================= 配置設定 =================
# 圖片路徑解析：
# - 一般以 .py 執行時，以本檔所在資料夾為基準（icon/ 與本檔同層）。
# - 打包成單一 exe（PyInstaller frozen）後，icon 以資料檔內嵌在 exe 內，
#   執行時由 PyInstaller 解壓到 sys._MEIPASS 暫存目錄，故從該處讀取。
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
else:
    BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / 'icon'


def _icon_path(filename):
    return ICON_DIR / filename


# 功能開關：要停用某項功能時，將 True 改成 False。
ENABLE_TAKEMYHEAL_DETECTION = True
ENABLE_TAKEMYHEAL8LV_DETECTION = True
ENABLE_HELP_DETECTION = True
ENABLE_EXIT_GAME_DETECTION = True
ENABLE_RALLY_SEQUENCE = True
ENABLE_HEAL_SEQUENCE = True
ENABLE_GATHER_SEQUENCE = True
ENABLE_HUNT_ZOMBIE_SEQUENCE = True
ENABLE_BASE_MONITORING = True

# 普通偵測圖片
TAKEMYHEAL_IMAGE = _icon_path('takemyheal.png')
TAKEMYHEAL8LV_IMAGE = _icon_path('takemyheal8lv.png')
HELP_IMAGE = _icon_path('help.png')
EXIT_GAME_IMAGE = _icon_path('退出遊戲.png')
TARGET_IMAGES = []
if ENABLE_TAKEMYHEAL_DETECTION:
    TARGET_IMAGES.append(TAKEMYHEAL_IMAGE)
if ENABLE_TAKEMYHEAL8LV_DETECTION:
    TARGET_IMAGES.append(TAKEMYHEAL8LV_IMAGE)
if ENABLE_HELP_DETECTION:
    TARGET_IMAGES.append(HELP_IMAGE)
if ENABLE_EXIT_GAME_DETECTION:
    TARGET_IMAGES.append(EXIT_GAME_IMAGE)

THRESHOLD = 0.80
# 模板縮放倍率：每多一階就多一次全螢幕 matchTemplate，成本幾乎線性成長。
# 原本 80%~120% 共 9 階，單張圖比對就要約 2 秒，主迴圈一輪累積到 13 秒以上，
# 導致集結提醒從出現到進入序列可能延遲 20 秒。遊戲視窗解析度固定的前提下，
# 只需保留 1.0 與前後各一階容錯即可。
TEMPLATE_SCALES = (0.95, 1.0, 1.05)

MONITOR_REGION = {"top": 0, "left": 0, "width": 1920, "height": 1080}

CLICK_MODE = 'center' 
FIXED_CLICK_X = 1000  
FIXED_CLICK_Y = 1000

# 獨立冷卻時間設定（秒）
INDIVIDUAL_COOLDOWN = 1.0

# 集結序列圖片
RALLY_NOTIFY_IMAGE = _icon_path('集結提醒.png')
RALLY_JOIN_IMAGE = _icon_path('加入集結+.png')
RALLY_CONFIRM_IMAGE = _icon_path('出征確定.png')
RALLY_BACK_IMAGE = _icon_path('返回.png')

# 集結序列冷卻：序列結束後 N 秒內不再進入序列（期間其他偵測照常運作）
RALLY_SEQUENCE_COOLDOWN = 10.0

# 集結序列進入前延遲：初次偵測到集結提醒後，等待 N 秒再確認仍存在才進入序列
RALLY_ENTRY_DELAY = 3.0

# 集結序列硬性超時：序列若未透過正常路徑結束，超過 N 秒強制中止
RALLY_SEQUENCE_TIMEOUT = 8.0

# 採集序列相關圖片
GATHER_FIND_IMAGE = _icon_path('尋找.png')
GATHER_SELECT_GATHER_IMAGE = _icon_path('選擇採集.png')
GATHER_GOLD_MINE_IMAGE = _icon_path('灰色金礦.png')
GATHER_MINUS_IMAGE = _icon_path('減號.png')
GATHER_PLUS_IMAGE = _icon_path('加號.png')
GATHER_SEARCH_IMAGE = _icon_path('搜索.png')
GATHER_PICKAXE_IMAGE = _icon_path('十字鎬.png')
GATHER_SQUAD3_IMAGE = _icon_path('閒置三隊.png')
GATHER_SQUAD2_IMAGE = _icon_path('閒置二隊.png')
GATHER_QUEUE_IMAGE = _icon_path('出征隊列.png')

# 採集序列配置
GATHER_CHECK_INTERVAL = 60.0   # 1 分鐘檢查一次
GATHER_STEP_TIMEOUT = 2.0      # 每一步驟的逾時時間
GATHER_SLOW_STEP_TIMEOUT = 2.0 # 搜索後、出征頁等較慢換頁步驟的逾時時間
GATHER_FAST_STEP_DELAY = 0.30  # 採集序列一般點擊後的換頁緩衝
GATHER_SLOW_STEP_DELAY = 0.80  # 採集序列較慢換頁按鈕點擊後的緩衝
GATHER_QUANTITY_CLICK_RATIO = 0.50

# 狩獵金幣小殭屍序列相關圖片
HUNT_STAMINA_IMAGE = _icon_path('體力108.png')
HUNT_WORLD_IMAGE = _icon_path('世界.png')
HUNT_ZOOMED_ZOMBIE_IMAGE = _icon_path('縮小15段後金幣殭屍.png')
HUNT_WORLD_BASE_IMAGE = _icon_path('世界視角基地.png')
HUNT_SPECIAL_EVENT_IMAGE = _icon_path('特殊事件.png')
HUNT_DAILY_TASK_IMAGE = _icon_path('每日任務.png')
HUNT_ATTACK_IMAGE = _icon_path('攻擊按鈕.png')

# 狩獵金幣小殭屍序列配置
HUNT_CHECK_INTERVAL = 60.0
HUNT_STEP_TIMEOUT = 2.0
HUNT_EVENT_MIDPOINT_TIMEOUT = 10.0
HUNT_SCROLL_STEPS = 15
HUNT_SCROLL_INTERVAL = 0.2

# 治療序列圖片
HEAL_START_IMAGE = _icon_path('startmyheal.png')
HEAL_CONFIRM_IMAGE = _icon_path('confirmheal_PC.png')
HEAL_LOOKFORHELP_IMAGE = _icon_path('lookforhelp.png')

# 治療序列冷卻與硬性超時
HEAL_SEQUENCE_COOLDOWN = 5.0
HEAL_SEQUENCE_TIMEOUT = 8.0

# 序列中偵測頻率與點擊後緩衝。
SEQUENCE_POLLING_INTERVAL = 0.10
SEQUENCE_AFTER_CLICK_DELAY = 0.10

# 基地監測：每隔 BASE_CHECK_INTERVAL 秒檢查畫面是否出現「基地」，
# 連續 BASE_MISSING_LIMIT 次未出現就按一下 ESC 並把計數歸零重新開始
BASE_IMAGE = _icon_path('基地.png')
BASE_CHECK_INTERVAL = 10.0
BASE_MISSING_LIMIT = 5

# 需要「彩色」比對的圖片。
# 灰階比對只有單通道，速度約為彩色的 4 倍，但會丟失顏色資訊；靠顏色區分同形狀
# UI 的圖片（例如灰色金礦與其他顏色的礦點）轉灰階會誤判，必須留在這份清單裡。
# 不在清單內的圖片一律以灰階比對。採集序列所有步驟都列入，包含與其他序列共用的
# 「出征確定」「閒置三隊/二隊」「基地」（採集進入條件會用到）。
COLOR_REQUIRED_IMAGES = {
    GATHER_FIND_IMAGE,
    GATHER_SELECT_GATHER_IMAGE,
    GATHER_GOLD_MINE_IMAGE,
    GATHER_MINUS_IMAGE,
    GATHER_PLUS_IMAGE,
    GATHER_SEARCH_IMAGE,
    GATHER_PICKAXE_IMAGE,
    GATHER_SQUAD3_IMAGE,
    GATHER_SQUAD2_IMAGE,
    GATHER_QUEUE_IMAGE,
    RALLY_CONFIRM_IMAGE,
    BASE_IMAGE,
}

# 圖示搜尋區域（ROI）：固定出現在畫面某一塊的圖示，只比對那一塊即可，
# 比對成本與面積成正比，縮小範圍是目前效益最大的加速手段。
# - 座標為螢幕絕對座標，格式同 MONITOR_REGION；超出畫面的部分會自動裁掉。
# - 未列在這裡的圖片一律搜尋整個 MONITOR_REGION。
# - 用 roi_finder.py 量測：python roi_finder.py 集結提醒.png
# 目前的值 = 實測圖示位置四周各放寬 200px，容納每次開視窗的位置偏移。
# 若遊戲視窗位置變動超過這個範圍會直接偵測不到，屆時重新量測或再放寬。
IMAGE_ROIS = {
    # 實測位置 (1710,652)-(1742,681)，±200px
    RALLY_NOTIFY_IMAGE: {"top": 452, "left": 1510, "width": 410, "height": 429},
    # 實測位置 (1660,945)-(1776,984)，±200px（右下角，往右往下已到畫面邊界）
    BASE_IMAGE: {"top": 745, "left": 1460, "width": 460, "height": 335},
    # 實測位置 (22,796)-(60,831)，±200px（左下角，往左已到畫面邊界）
    GATHER_FIND_IMAGE: {"top": 596, "left": 0, "width": 260, "height": 435},
    # 實測位置 (12,220)-(130,246)，±200px（左側，往左已到畫面邊界）
    GATHER_QUEUE_IMAGE: {"top": 20, "left": 0, "width": 330, "height": 426},
    # 實測位置 (1708,111)-(1747,171)，±200px（右上角，往上往右已到畫面邊界）
    HUNT_SPECIAL_EVENT_IMAGE: {"top": 0, "left": 1508, "width": 412, "height": 371},
    # 實測位置 (15,870)-(43,924)，±200px（左下角，往左往下已到畫面邊界）
    HUNT_DAILY_TASK_IMAGE: {"top": 670, "left": 0, "width": 243, "height": 410},
    # 實測位置 (11,113)-(52,133)，±200px（左上角，往左往上已到畫面邊界）
    # 註：體力數字會變動，匹配度本來就會浮動（實測 0.69~0.83），但位置固定
    HUNT_STAMINA_IMAGE: {"top": 0, "left": 0, "width": 252, "height": 333},
}
# ===========================================


def _imread_unicode(path):
    """支援含中文路徑的圖片讀取（cv2.imread 在 Windows 不支援非 ASCII 路徑）。"""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except (FileNotFoundError, OSError):
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _load_template(path):
    img = _imread_unicode(path)
    if img is None:
        print(f"【警告】找不到圖片檔案: {path}")
        return None
    use_gray = path not in COLOR_REQUIRED_IMAGES
    if use_gray:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]
    variants = []
    seen_sizes = set()
    for scale in TEMPLATE_SCALES:
        scaled_w = max(1, int(round(w * scale)))
        scaled_h = max(1, int(round(h * scale)))
        if (scaled_w, scaled_h) in seen_sizes:
            continue
        seen_sizes.add((scaled_w, scaled_h))
        if scale == 1.0:
            scaled_img = img
        else:
            scaled_img = cv2.resize(img, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
        variants.append({'img': scaled_img, 'w': scaled_w, 'h': scaled_h, 'scale': scale})
    roi = IMAGE_ROIS.get(path)
    if roi is not None:
        # ROI 比模板還小的話，該圖示會永遠比對不到，且不會有任何錯誤訊息，
        # 這裡先擋下來，避免設錯 ROI 後功能靜默失效。
        max_w = max(v['w'] for v in variants)
        max_h = max(v['h'] for v in variants)
        if roi['width'] < max_w or roi['height'] < max_h:
            print(f"【警告】{path} 的 ROI ({roi['width']}x{roi['height']}) 小於模板 "
                  f"({max_w}x{max_h})，已忽略 ROI 改為全畫面搜尋")
            roi = None
    return {'variants': variants, 'name': path, 'last_clicked': 0, 'gray': use_gray, 'roi': roi}


def _grab_frame(sct):
    screenshot = sct.grab(MONITOR_REGION)
    frame = np.array(screenshot)
    return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)


def _click_template(t, max_loc, matched_variant):
    if matched_variant is None:
        return
    if CLICK_MODE == 'center':
        target_x = MONITOR_REGION["left"] + max_loc[0] + matched_variant['w'] // 2
        target_y = MONITOR_REGION["top"] + max_loc[1] + matched_variant['h'] // 2
    else:
        target_x = FIXED_CLICK_X
        target_y = FIXED_CLICK_Y
    final_x = target_x + random.randint(-3, 3)
    final_y = target_y + random.randint(-3, 3)
    pyautogui.click(final_x, final_y)
    pyautogui.moveTo(10, 10)
    t['last_clicked'] = time.time()


def _match(frame, t):
    # 灰階模板需要單通道畫面；呼叫端一律傳 BGR，這裡就地轉換（約 1ms），
    # 讓所有呼叫端不必關心自己手上的圖是哪種模板要用的。
    if t['gray'] and frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 有設 ROI 就只比對那一塊；裁切後座標會位移，最後把偏移量加回去，
    # 讓回傳的 loc 仍然是相對 MONITOR_REGION 的座標，呼叫端不必知道 ROI 存在。
    offset_x = offset_y = 0
    roi = t['roi']
    if roi is not None:
        x0 = max(0, roi['left'] - MONITOR_REGION["left"])
        y0 = max(0, roi['top'] - MONITOR_REGION["top"])
        x1 = min(frame.shape[1], x0 + roi['width'])
        y1 = min(frame.shape[0], y0 + roi['height'])
        if x1 > x0 and y1 > y0:
            frame = frame[y0:y1, x0:x1]
            offset_x, offset_y = x0, y0

    frame_h, frame_w = frame.shape[:2]
    best_val = -1.0
    best_loc = (0, 0)
    best_variant = None
    for variant in t['variants']:
        if variant['w'] > frame_w or variant['h'] > frame_h:
            continue
        result = cv2.matchTemplate(frame, variant['img'], cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_variant = variant
    return best_val, (best_loc[0] + offset_x, best_loc[1] + offset_y), best_variant


def _detect_and_click_within(sct, t, timeout, after_click_delay=SEQUENCE_AFTER_CLICK_DELAY):
    """在 timeout 秒內持續偵測 t，偵測到就立即點擊；回傳是否點擊成功。"""
    start = time.time()
    while time.time() - start < timeout:
        frame = _grab_frame(sct)
        max_val, max_loc, matched_variant = _match(frame, t)
        if max_val >= THRESHOLD:
            print(f"✅ {t['name']} 偵測到 (匹配度: {max_val:.2f})")
            _click_template(t, max_loc, matched_variant)
            time.sleep(after_click_delay)
            return True
        time.sleep(SEQUENCE_POLLING_INTERVAL)
    return False


def _fallback_press_back(sct, back_t, total_seconds=2):
    """在 total_seconds 秒內以序列頻率持續偵測「返回」，偵測到就點。

    回傳是否曾偵測並點擊過「返回」。
    """
    print(f"--- Fallback：連續偵測 {back_t['name']} 共 {total_seconds} 秒 ---")
    clicked = False
    start = time.time()
    while time.time() - start < total_seconds:
        frame = _grab_frame(sct)
        max_val, max_loc, matched_variant = _match(frame, back_t)
        if max_val >= THRESHOLD:
            print(f"✅ {back_t['name']} 偵測到 (匹配度: {max_val:.2f})")
            _click_template(back_t, max_loc, matched_variant)
            clicked = True
        time.sleep(SEQUENCE_POLLING_INTERVAL)
    return clicked


def _run_rally_sequence(sct, notify_t, join_t, confirm_t, back_t, notify_loc, notify_variant):
    """集結提醒 → 加入集結+ → 出征確定 流程。

    - 加入集結+ 失敗：fallback 連續按返回 3 秒
    - 出征確定 失敗：先 fallback 連續按返回 3 秒；若 3 秒內也沒按到返回才按 ESC
    - 整體 RALLY_SEQUENCE_TIMEOUT 秒內未透過正常路徑結束，強制中止
    """
    start = time.time()

    def _expired():
        return time.time() - start >= RALLY_SEQUENCE_TIMEOUT

    print("=== 進入集結序列 ===")
    # 步驟 1：點擊集結提醒
    _click_template(notify_t, notify_loc, notify_variant)
    print(f"✅ 已點擊 {notify_t['name']}")

    # 步驟 2：3 秒內偵測「加入集結+」
    if _detect_and_click_within(sct, join_t, timeout=3):
        # 步驟 3：2 秒內偵測「出征確定」
        if not _expired() and not _detect_and_click_within(sct, confirm_t, timeout=2):
            # 步驟 3.5：連續 2 秒偵測「返回」；若期間從未偵測到才按 ESC
            if not _expired() and not _fallback_press_back(sct, back_t, total_seconds=2):
                if not _expired():
                    print(f"⚠️ 2 秒內未偵測到 {back_t['name']}，按 ESC 結束序列")
                    pyautogui.press('esc')
    elif not _expired():
        _fallback_press_back(sct, back_t, total_seconds=3)

    if _expired():
        print(f"⚠️ 集結序列超過 {RALLY_SEQUENCE_TIMEOUT:.0f} 秒未正常結束，強制中止")
        pyautogui.press('esc')

    # 序列結束時刷新時間戳，後續以此為冷卻起點
    notify_t['last_clicked'] = time.time()
    print(f"=== 集結序列結束（{RALLY_SEQUENCE_COOLDOWN:.0f} 秒內不再進入序列）===")


def _run_gather_sequence(sct, find_t, select_t, gold_t, minus_t, plus_t, search_t, pickaxe_t, squad3_t, squad2_t, confirm_t):
    """採集序列：尋找 → 選擇採集 → 灰色金礦 → 數量位置 → 搜索 → 十字鎬 → 閒置隊伍 → 出征確定。"""

    def _seconds_label(seconds):
        return f"{seconds:g} 秒"

    def _abort(message):
        print(f"⚠️ {message}，按 ESC 結束採集序列")
        pyautogui.press('esc')
        return False

    def _click_required(t, timeout=GATHER_STEP_TIMEOUT, after_click_delay=GATHER_FAST_STEP_DELAY):
        if _detect_and_click_within(sct, t, timeout=timeout, after_click_delay=after_click_delay):
            return True
        return _abort(f"{_seconds_label(timeout)}內未偵測到 {t['name']}")

    def _click_quantity_point():
        start = time.time()
        while time.time() - start < GATHER_STEP_TIMEOUT:
            frame = _grab_frame(sct)
            minus_val, minus_loc, minus_variant = _match(frame, minus_t)
            plus_val, plus_loc, plus_variant = _match(frame, plus_t)
            if minus_val >= THRESHOLD and plus_val >= THRESHOLD:
                minus_x = MONITOR_REGION["left"] + minus_loc[0] + minus_variant['w'] // 2
                plus_x = MONITOR_REGION["left"] + plus_loc[0] + plus_variant['w'] // 2
                minus_y = MONITOR_REGION["top"] + minus_loc[1] + minus_variant['h'] // 2
                plus_y = MONITOR_REGION["top"] + plus_loc[1] + plus_variant['h'] // 2
                left_x = min(minus_x, plus_x)
                right_x = max(minus_x, plus_x)
                target_x = int(round(left_x + (right_x - left_x) * GATHER_QUANTITY_CLICK_RATIO))
                target_y = int(round((minus_y + plus_y) / 2))
                print(f"✅ 減號/加號偵測到 (匹配度: {minus_val:.2f}/{plus_val:.2f})")
                pyautogui.click(target_x, target_y)
                pyautogui.moveTo(10, 10)
                time.sleep(GATHER_FAST_STEP_DELAY)
                return True
            time.sleep(SEQUENCE_POLLING_INTERVAL)
        return _abort(f"{_seconds_label(GATHER_STEP_TIMEOUT)}內未同時偵測到 {minus_t['name']} 與 {plus_t['name']}")

    def _click_idle_squad(timeout=GATHER_SLOW_STEP_TIMEOUT):
        start = time.time()
        while time.time() - start < timeout:
            frame = _grab_frame(sct)
            squad3_val, squad3_loc, squad3_variant = _match(frame, squad3_t)
            squad2_val, squad2_loc, squad2_variant = _match(frame, squad2_t)
            if squad3_val >= THRESHOLD:
                print(f"✅ {squad3_t['name']} 偵測到 (匹配度: {squad3_val:.2f})")
                _click_template(squad3_t, squad3_loc, squad3_variant)
                time.sleep(GATHER_FAST_STEP_DELAY)
                return True
            if squad2_val >= THRESHOLD:
                print(f"✅ {squad2_t['name']} 偵測到 (匹配度: {squad2_val:.2f})")
                _click_template(squad2_t, squad2_loc, squad2_variant)
                time.sleep(GATHER_FAST_STEP_DELAY)
                return True
            time.sleep(SEQUENCE_POLLING_INTERVAL)
        return _abort(f"{_seconds_label(timeout)}內未偵測到 {squad3_t['name']} 或 {squad2_t['name']}")

    print("=== 進入採集序列 ===")

    if not _click_required(find_t):
        return
    if not _click_required(select_t):
        return

    if gold_t is None:
        print("ℹ️ 灰色金礦圖片未載入，跳過可選步驟")
    elif _detect_and_click_within(sct, gold_t, timeout=GATHER_STEP_TIMEOUT, after_click_delay=GATHER_FAST_STEP_DELAY):
        print(f"✅ 已點擊可選步驟 {gold_t['name']}")
    else:
        print(f"ℹ️ 2 秒內未偵測到 {gold_t['name']}，跳過可選步驟")

    if not _click_quantity_point():
        return
    if not _click_required(search_t, after_click_delay=GATHER_SLOW_STEP_DELAY):
        return
    if not _click_required(pickaxe_t, timeout=GATHER_SLOW_STEP_TIMEOUT, after_click_delay=GATHER_FAST_STEP_DELAY):
        return
    if not _click_idle_squad():
        return
    if not _click_required(confirm_t, timeout=GATHER_SLOW_STEP_TIMEOUT):
        return

    print("=== 採集序列結束 ===")


def _run_hunt_zombie_sequence(sct, base_t, world_t, zoomed_zombie_t, world_base_t, special_event_t, daily_task_t, idle_squad_ts, attack_t, confirm_t):
    """狩獵金幣小殭屍序列：基地 → 世界 → 縮小 → 金幣殭屍 → 攻擊 → 出征確定。"""

    def _abort(message):
        print(f"⚠️ {message}，按 ESC 結束狩獵金幣小殭屍序列")
        pyautogui.press('esc')
        return False

    def _click_required(t):
        if _detect_and_click_within(sct, t, timeout=HUNT_STEP_TIMEOUT):
            return True
        return _abort(f"2 秒內未偵測到 {t['name']}")

    def _click_event_midpoint_required():
        start = time.time()
        while time.time() - start < HUNT_EVENT_MIDPOINT_TIMEOUT:
            frame = _grab_frame(sct)
            special_val, special_loc, special_variant = _match(frame, special_event_t)
            daily_val, daily_loc, daily_variant = _match(frame, daily_task_t)
            if special_val >= THRESHOLD and daily_val >= THRESHOLD:
                special_x = MONITOR_REGION["left"] + special_loc[0] + special_variant['w'] // 2
                special_y = MONITOR_REGION["top"] + special_loc[1] + special_variant['h'] // 2
                daily_x = MONITOR_REGION["left"] + daily_loc[0] + daily_variant['w'] // 2
                daily_y = MONITOR_REGION["top"] + daily_loc[1] + daily_variant['h'] // 2
                target_x = int(round((special_x + daily_x) / 2))
                target_y = int(round((special_y + daily_y) / 2))
                print(f"✅ 特殊事件/每日任務偵測到 (匹配度: {special_val:.2f}/{daily_val:.2f})，點擊中心連線 50% 位置")
                pyautogui.click(target_x, target_y)
                pyautogui.moveTo(10, 10)
                time.sleep(SEQUENCE_AFTER_CLICK_DELAY)
                return True
            time.sleep(SEQUENCE_POLLING_INTERVAL)
        return _abort(f"{HUNT_EVENT_MIDPOINT_TIMEOUT:.0f} 秒內未同時偵測到 {special_event_t['name']} 與 {daily_task_t['name']}")

    def _click_optional_idle_squad():
        if not idle_squad_ts:
            print("ℹ️ 閒置隊伍圖片未載入，跳過狩獵出征前隊伍選擇")
            return

        start = time.time()
        while time.time() - start < HUNT_STEP_TIMEOUT:
            frame = _grab_frame(sct)
            for idle_t in idle_squad_ts:
                max_val, max_loc, matched_variant = _match(frame, idle_t)
                if max_val >= THRESHOLD:
                    print(f"✅ {idle_t['name']} 偵測到 (匹配度: {max_val:.2f})")
                    _click_template(idle_t, max_loc, matched_variant)
                    time.sleep(SEQUENCE_AFTER_CLICK_DELAY)
                    return
            time.sleep(SEQUENCE_POLLING_INTERVAL)

        print("ℹ️ 2 秒內未偵測到閒置三隊或閒置二隊，跳過狩獵出征前隊伍選擇")

    def _scroll_down_from_center():
        target_x = MONITOR_REGION["left"] + MONITOR_REGION["width"] // 2
        target_y = MONITOR_REGION["top"] + MONITOR_REGION["height"] // 2
        pyautogui.moveTo(target_x, target_y)
        for _ in range(HUNT_SCROLL_STEPS):
            pyautogui.scroll(-1)
            time.sleep(HUNT_SCROLL_INTERVAL)

    print("=== 進入狩獵金幣小殭屍序列 ===")

    if not _click_required(base_t):
        return
    if not _click_required(world_t):
        return

    _scroll_down_from_center()

    if not _detect_and_click_within(sct, zoomed_zombie_t, timeout=HUNT_STEP_TIMEOUT):
        print(f"ℹ️ 2 秒內未偵測到 {zoomed_zombie_t['name']}，嘗試返回世界視角基地並結束序列")
        if not _detect_and_click_within(sct, world_base_t, timeout=HUNT_STEP_TIMEOUT):
            _abort(f"2 秒內未偵測到 {world_base_t['name']}")
            return
        print("=== 狩獵金幣小殭屍序列結束 ===")
        return

    if not _click_event_midpoint_required():
        return
    if not _click_required(attack_t):
        return
    _click_optional_idle_squad()
    if not _click_required(confirm_t):
        return

    print("=== 狩獵金幣小殭屍序列結束 ===")


def _run_heal_sequence(sct, start_t, confirm_t, lookforhelp_t, start_loc, start_variant):
    """治療序列：startmyheal → confirmheal → lookforhelp。

    任一步驟失敗（偵測不到下一張圖）就直接結束序列。
    整體 HEAL_SEQUENCE_TIMEOUT 秒內若未透過正常路徑結束，強制中止。
    """
    start = time.time()

    def _expired():
        return time.time() - start >= HEAL_SEQUENCE_TIMEOUT

    print("=== 進入治療序列 ===")
    # 步驟 1：點擊 startmyheal
    _click_template(start_t, start_loc, start_variant)
    print(f"✅ 已點擊 {start_t['name']}")

    # 步驟 2：2 秒內偵測 confirmheal
    if not _expired() and _detect_and_click_within(sct, confirm_t, timeout=2):
        # 步驟 3：2 秒內偵測 lookforhelp
        if not _expired():
            _detect_and_click_within(sct, lookforhelp_t, timeout=2)

    if _expired():
        print(f"⚠️ 治療序列超過 {HEAL_SEQUENCE_TIMEOUT:.0f} 秒未正常結束，強制中止")

    # 序列結束時刷新時間戳，後續以此為冷卻起點
    start_t['last_clicked'] = time.time()
    print(f"=== 治療序列結束（{HEAL_SEQUENCE_COOLDOWN:.0f} 秒內不再進入序列）===")


def solve_screen_detection():
    if not (
        TARGET_IMAGES
        or ENABLE_RALLY_SEQUENCE
        or ENABLE_HEAL_SEQUENCE
        or ENABLE_GATHER_SEQUENCE
        or ENABLE_HUNT_ZOMBIE_SEQUENCE
        or ENABLE_BASE_MONITORING
    ):
        print("【錯誤】所有功能開關皆為 False，沒有可執行項目。")
        return

    # 預先讀取圖片並初始化每個圖片的「上次點擊時間」為 0
    templates = []
    for path in TARGET_IMAGES:
        t = _load_template(path)
        if t is not None:
            templates.append(t)

    # 載入集結序列圖片
    rally_notify = None
    rally_join = None
    rally_confirm = None
    rally_back = None
    if ENABLE_RALLY_SEQUENCE or ENABLE_GATHER_SEQUENCE or ENABLE_HUNT_ZOMBIE_SEQUENCE:
        rally_confirm = _load_template(RALLY_CONFIRM_IMAGE)
    if ENABLE_RALLY_SEQUENCE:
        rally_notify = _load_template(RALLY_NOTIFY_IMAGE)
        rally_join = _load_template(RALLY_JOIN_IMAGE)
        rally_back = _load_template(RALLY_BACK_IMAGE)
    rally_ready = ENABLE_RALLY_SEQUENCE and all(x is not None for x in (rally_notify, rally_join, rally_confirm, rally_back))

    # 載入治療序列圖片
    heal_start = None
    heal_confirm = None
    heal_lookforhelp = None
    if ENABLE_HEAL_SEQUENCE:
        heal_start = _load_template(HEAL_START_IMAGE)
        heal_confirm = _load_template(HEAL_CONFIRM_IMAGE)
        heal_lookforhelp = _load_template(HEAL_LOOKFORHELP_IMAGE)
    heal_ready = ENABLE_HEAL_SEQUENCE and all(x is not None for x in (heal_start, heal_confirm, heal_lookforhelp))

    # 載入基地監測圖片
    base_t = None
    if ENABLE_BASE_MONITORING or ENABLE_GATHER_SEQUENCE or ENABLE_HUNT_ZOMBIE_SEQUENCE:
        base_t = _load_template(BASE_IMAGE)
    base_ready = base_t is not None
    base_monitor_ready = ENABLE_BASE_MONITORING and base_ready

    # 載入採集序列圖片
    gather_find = None
    gather_select = None
    gather_gold = None
    gather_minus = None
    gather_plus = None
    gather_search = None
    gather_pickaxe = None
    gather_s3 = None
    gather_s2 = None
    gather_queue = None
    if ENABLE_GATHER_SEQUENCE:
        gather_find = _load_template(GATHER_FIND_IMAGE)
        gather_select = _load_template(GATHER_SELECT_GATHER_IMAGE)
        gather_gold = _load_template(GATHER_GOLD_MINE_IMAGE)
        gather_minus = _load_template(GATHER_MINUS_IMAGE)
        gather_plus = _load_template(GATHER_PLUS_IMAGE)
        gather_search = _load_template(GATHER_SEARCH_IMAGE)
        gather_pickaxe = _load_template(GATHER_PICKAXE_IMAGE)
        gather_queue = _load_template(GATHER_QUEUE_IMAGE)
    if ENABLE_GATHER_SEQUENCE or ENABLE_HUNT_ZOMBIE_SEQUENCE:
        gather_s3 = _load_template(GATHER_SQUAD3_IMAGE)
        gather_s2 = _load_template(GATHER_SQUAD2_IMAGE)
    gather_ready = ENABLE_GATHER_SEQUENCE and base_ready and all(x is not None for x in (
        gather_find,
        gather_select,
        gather_minus,
        gather_plus,
        gather_search,
        gather_pickaxe,
        gather_s3,
        gather_s2,
        gather_queue,
        rally_confirm,
    ))
    idle_squads = [x for x in (gather_s3, gather_s2) if x is not None]

    # 載入狩獵金幣小殭屍序列圖片
    hunt_stamina = None
    hunt_world = None
    hunt_zoomed_zombie = None
    hunt_world_base = None
    hunt_special_event = None
    hunt_daily_task = None
    hunt_attack = None
    if ENABLE_HUNT_ZOMBIE_SEQUENCE:
        hunt_stamina = _load_template(HUNT_STAMINA_IMAGE)
        hunt_world = _load_template(HUNT_WORLD_IMAGE)
        hunt_zoomed_zombie = _load_template(HUNT_ZOOMED_ZOMBIE_IMAGE)
        hunt_world_base = _load_template(HUNT_WORLD_BASE_IMAGE)
        hunt_special_event = _load_template(HUNT_SPECIAL_EVENT_IMAGE)
        hunt_daily_task = _load_template(HUNT_DAILY_TASK_IMAGE)
        hunt_attack = _load_template(HUNT_ATTACK_IMAGE)
    hunt_ready = ENABLE_HUNT_ZOMBIE_SEQUENCE and base_ready and all(x is not None for x in (
        hunt_stamina,
        hunt_world,
        hunt_zoomed_zombie,
        hunt_world_base,
        hunt_special_event,
        hunt_daily_task,
        hunt_attack,
        rally_confirm,
    ))

    print(f"--- 獨立冷卻模式啟動 ---")
    print(f"每張圖片獨立冷卻: {INDIVIDUAL_COOLDOWN} 秒")
    print(f"模板縮放倍率: {', '.join(f'{scale * 100:.0f}%' for scale in TEMPLATE_SCALES)}")
    if TARGET_IMAGES:
        if templates:
            print(f"--- 普通偵測功能已啟用（{len(templates)}/{len(TARGET_IMAGES)} 張圖片載入）---")
        else:
            print("【警告】普通偵測圖片皆無法載入，已停用普通偵測")
    else:
        print("--- 普通偵測功能已全部停用 ---")
    if not ENABLE_RALLY_SEQUENCE:
        print("--- 集結序列功能已停用 ---")
    elif rally_ready:
        print("--- 集結序列功能已啟用 ---")
    else:
        print("【警告】集結序列圖片不齊全，已停用該功能")
    if not ENABLE_HEAL_SEQUENCE:
        print("--- 治療序列功能已停用 ---")
    elif heal_ready:
        print("--- 治療序列功能已啟用 ---")
    else:
        print("【警告】治療序列圖片不齊全，已停用該功能")
    if not ENABLE_GATHER_SEQUENCE:
        print("--- 採集序列功能已停用 ---")
    elif gather_ready:
        print("--- 採集序列功能已啟用 ---")
    else:
        print("【警告】採集序列必要圖片不齊全，已停用該功能")
    if not ENABLE_HUNT_ZOMBIE_SEQUENCE:
        print("--- 狩獵金幣小殭屍序列功能已停用 ---")
    elif hunt_ready:
        print("--- 狩獵金幣小殭屍序列功能已啟用 ---")
    else:
        print("【警告】狩獵金幣小殭屍序列必要圖片不齊全，已停用該功能")
    if not ENABLE_BASE_MONITORING:
        print("--- 基地監測功能已停用 ---")
    elif base_monitor_ready:
        print(f"--- 基地監測功能已啟用（每 {BASE_CHECK_INTERVAL:.0f} 秒檢查，連續 {BASE_MISSING_LIMIT} 次未出現按 ESC）---")
    else:
        print("【警告】找不到基地圖片，已停用基地監測")

    if not templates and not any((rally_ready, heal_ready, gather_ready, hunt_ready, base_monitor_ready)):
        print("【錯誤】沒有任何已啟用且可載入的功能。")
        return


    # 基地監測狀態：上次檢查時間 + 連續未出現次數
    last_base_check = time.time()
    base_missing_count = 0
    last_gather_check = time.time() - GATHER_CHECK_INTERVAL
    last_hunt_check = time.time() - HUNT_CHECK_INTERVAL

    with mss.mss() as sct:
        while True:
            current_time = time.time()  # 取得當前系統時間

            # 1. 擷取螢幕
            screenshot = sct.grab(MONITOR_REGION)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # 1.4 基地監測：每隔 BASE_CHECK_INTERVAL 秒檢查一次「基地」是否出現，
            #     連續 BASE_MISSING_LIMIT 次未出現就按 ESC 並把計數歸零重新開始
            if base_monitor_ready and current_time - last_base_check >= BASE_CHECK_INTERVAL:
                last_base_check = current_time
                base_val, _, _ = _match(frame, base_t)
                if base_val >= THRESHOLD:
                    base_missing_count = 0
                    print(f"🏠 偵測到 {base_t['name']}（匹配度: {base_val:.2f}），基地計數歸零")
                else:
                    base_missing_count += 1
                    print(f"⚠️ 未偵測到 {base_t['name']}（匹配度: {base_val:.2f}），連續未出現 {base_missing_count}/{BASE_MISSING_LIMIT}")
                    if base_missing_count >= BASE_MISSING_LIMIT:
                        print(f"🔄 連續 {BASE_MISSING_LIMIT} 次未偵測到基地，按下 ESC 並重置計數")
                        pyautogui.press('esc')
                        base_missing_count = 0

            # 1.5 集結序列優先檢查：偵測到「集結提醒」後延遲確認，仍存在才進入序列
            #     這裡不沿用迴圈開頭的 frame，改重抓一張最新畫面：迴圈開頭那張在跑完
            #     前面步驟後已經過期，集結提醒若在本輪中途才彈出就會被漏掉，必須等下
            #     一輪才看得到。重抓一次約 30ms，遠小於漏掉一輪的代價。
            if rally_ready and current_time - rally_notify['last_clicked'] >= RALLY_SEQUENCE_COOLDOWN:
                rally_frame = _grab_frame(sct)
                max_val, _, _ = _match(rally_frame, rally_notify)
                if max_val >= THRESHOLD:
                    print(f"✅ 偵測到 {rally_notify['name']} (匹配度: {max_val:.2f})，等待 {RALLY_ENTRY_DELAY:.0f} 秒後再次確認")
                    time.sleep(RALLY_ENTRY_DELAY)
                    frame2 = _grab_frame(sct)
                    max_val2, max_loc2, matched_variant2 = _match(frame2, rally_notify)
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {rally_notify['name']} 延遲確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _run_rally_sequence(sct, rally_notify, rally_join, rally_confirm, rally_back, max_loc2, matched_variant2)
                        continue
                    else:
                        print(f"⚠️ {rally_notify['name']} 延遲確認失敗 (首次: {max_val:.2f}, 延遲後: {max_val2:.2f})")
                        continue

            # 1.6 治療序列優先檢查：偵測到 startmyheal 就進入序列，期間不偵測其他動作
            if heal_ready and current_time - heal_start['last_clicked'] >= HEAL_SEQUENCE_COOLDOWN:
                max_val, _, _ = _match(frame, heal_start)
                if max_val >= THRESHOLD:
                    time.sleep(0.1)
                    frame2 = _grab_frame(sct)
                    max_val2, max_loc2, matched_variant2 = _match(frame2, heal_start)
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {heal_start['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _run_heal_sequence(sct, heal_start, heal_confirm, heal_lookforhelp, max_loc2, matched_variant2)
                        continue
                    else:
                        print(f"⚠️ {heal_start['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})")

            # 1.7 採集序列檢查：每 1 分鐘偵測一次，基地存在且沒有出征隊列時進入序列
            if gather_ready and current_time - last_gather_check >= GATHER_CHECK_INTERVAL:
                last_gather_check = current_time
                val_base, _, _ = _match(frame, base_t)
                val_queue, _, _ = _match(frame, gather_queue)

                if val_base >= THRESHOLD and val_queue < THRESHOLD:
                    print(f"✅ 採集條件成立：偵測到基地 ({val_base:.2f}) 且未偵測到出征隊列 ({val_queue:.2f})")
                    _run_gather_sequence(
                        sct,
                        gather_find,
                        gather_select,
                        gather_gold,
                        gather_minus,
                        gather_plus,
                        gather_search,
                        gather_pickaxe,
                        gather_s3,
                        gather_s2,
                        rally_confirm,
                    )
                    continue

            # 1.8 狩獵金幣小殭屍序列檢查：每 1 分鐘偵測一次體力入口
            if hunt_ready and current_time - last_hunt_check >= HUNT_CHECK_INTERVAL:
                last_hunt_check = current_time
                max_val, _, _ = _match(frame, hunt_stamina)
                if max_val >= THRESHOLD:
                    time.sleep(0.1)
                    frame2 = _grab_frame(sct)
                    max_val2, max_loc2, matched_variant2 = _match(frame2, hunt_stamina)
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {hunt_stamina['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _run_hunt_zombie_sequence(
                            sct,
                            base_t,
                            hunt_world,
                            hunt_zoomed_zombie,
                            hunt_world_base,
                            hunt_special_event,
                            hunt_daily_task,
                            idle_squads,
                            hunt_attack,
                            rally_confirm,
                        )
                        continue
                    else:
                        print(f"⚠️ {hunt_stamina['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})")

            # 2. 檢查清單中的每一張圖
            for t in templates:
                # 檢查冷卻時間：如果現在時間距離上次點擊還不到 3 秒，直接跳過這張圖不偵測
                if current_time - t['last_clicked'] < INDIVIDUAL_COOLDOWN:
                    continue

                max_val, _, _ = _match(frame, t)

                if max_val >= THRESHOLD:
                    # 二次確認機制：短暫等待後再次檢測，避免誤判
                    time.sleep(0.1)

                    # 重新擷取螢幕並進行第二次匹配
                    screenshot2 = sct.grab(MONITOR_REGION)
                    frame2 = np.array(screenshot2)
                    frame2 = cv2.cvtColor(frame2, cv2.COLOR_BGRA2BGR)

                    max_val2, max_loc2, matched_variant2 = _match(frame2, t)

                    # 只有兩次都檢測到才點擊
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {t['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _click_template(t, max_loc2, matched_variant2)

                        time.sleep(0.1)  # 點擊後短暫等待，避免連續點擊過快
                    else:
                        print(f"⚠️ {t['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})") 
            
            # 降低 CPU 負擔
            time.sleep(1)   # 每次迴圈結束後等待 3 秒，這樣每張圖的冷卻時間就不會被過度觸發

if __name__ == "__main__":
    try:
        solve_screen_detection()
    except KeyboardInterrupt:
        print("\n--- 腳本已停止 ---")
