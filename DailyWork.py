import cv2
import numpy as np
import mss
import pyautogui
import time
import random
from pathlib import Path

# 關閉 PyAutoGUI 角落緊急停止機制（避免滑鼠路徑經過 (0,0) 時被誤觸停止）
# 副作用：失去「滑鼠甩角落停腳本」這個熱鍵，要中止請用 Ctrl+C
pyautogui.FAILSAFE = False

# ================= 配置設定 =================
# 圖片路徑以 DailyWork.py 所在資料夾為基準，方便整包資料夾搬移。
BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / 'icon'


def _icon_path(filename):
    return ICON_DIR / filename


TARGET_IMAGES = [_icon_path('takemyheal.png'), _icon_path('takemyheal8lv.png'), _icon_path('help.png')]
THRESHOLD = 0.85 
TEMPLATE_SCALES = (1.0, 0.5)

MONITOR_REGION = {"top": 0, "left": 0, "width": 1920, "height": 1080}

CLICK_MODE = 'center' 
FIXED_CLICK_X = 1000  
FIXED_CLICK_Y = 1000

# 獨立冷卻時間設定（秒）
INDIVIDUAL_COOLDOWN = 3.0

# 集結序列圖片
RALLY_NOTIFY_IMAGE = _icon_path('集結提醒.png')
RALLY_JOIN_IMAGE = _icon_path('加入集結+.png')
RALLY_CONFIRM_IMAGE = _icon_path('出征確定.png')
RALLY_BACK_IMAGE = _icon_path('返回.png')

# 集結序列冷卻：序列結束後 N 秒內不再進入序列（期間其他偵測照常運作）
RALLY_SEQUENCE_COOLDOWN = 10.0

# 集結序列硬性超時：序列若未透過正常路徑結束，超過 N 秒強制中止
RALLY_SEQUENCE_TIMEOUT = 8.0

# 治療序列圖片
HEAL_START_IMAGE = _icon_path('startmyheal.png')
HEAL_CONFIRM_IMAGE = _icon_path('confirmheal_PC.png')
HEAL_LOOKFORHELP_IMAGE = _icon_path('lookforhelp.png')

# 治療序列冷卻與硬性超時
HEAL_SEQUENCE_COOLDOWN = 5.0
HEAL_SEQUENCE_TIMEOUT = 8.0

# 序列中偵測頻率 (秒)：每秒 4 次 = 0.25 秒
SEQUENCE_POLLING_INTERVAL = 0.25

# 基地監測：每隔 BASE_CHECK_INTERVAL 秒檢查畫面是否出現「基地」，
# 連續 BASE_MISSING_LIMIT 次未出現就按一下 ESC 並把計數歸零重新開始
BASE_IMAGE = _icon_path('基地.png')
BASE_CHECK_INTERVAL = 10.0
BASE_MISSING_LIMIT = 5
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
    return {'variants': variants, 'name': path, 'last_clicked': 0}


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
    return best_val, best_loc, best_variant


def _detect_and_click_within(sct, t, timeout):
    """在 timeout 秒內持續偵測 t 並二次確認後點擊；回傳是否點擊成功。"""
    start = time.time()
    while time.time() - start < timeout:
        frame = _grab_frame(sct)
        max_val, _, _ = _match(frame, t)
        if max_val >= THRESHOLD:
            time.sleep(0.2)
            frame2 = _grab_frame(sct)
            max_val2, max_loc2, matched_variant2 = _match(frame2, t)
            if max_val2 >= THRESHOLD:
                print(f"✅ {t['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                _click_template(t, max_loc2, matched_variant2)
                time.sleep(0.5)
                return True
            else:
                print(f"⚠️ {t['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})")
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
    # 預先讀取圖片並初始化每個圖片的「上次點擊時間」為 0
    templates = []
    for path in TARGET_IMAGES:
        t = _load_template(path)
        if t is not None:
            templates.append(t)

    if not templates:
        print("【錯誤】沒有有效圖片。")
        return

    # 載入集結序列圖片
    rally_notify = _load_template(RALLY_NOTIFY_IMAGE)
    rally_join = _load_template(RALLY_JOIN_IMAGE)
    rally_confirm = _load_template(RALLY_CONFIRM_IMAGE)
    rally_back = _load_template(RALLY_BACK_IMAGE)
    rally_ready = all(x is not None for x in (rally_notify, rally_join, rally_confirm, rally_back))

    # 載入治療序列圖片
    heal_start = _load_template(HEAL_START_IMAGE)
    heal_confirm = _load_template(HEAL_CONFIRM_IMAGE)
    heal_lookforhelp = _load_template(HEAL_LOOKFORHELP_IMAGE)
    heal_ready = all(x is not None for x in (heal_start, heal_confirm, heal_lookforhelp))

    # 載入基地監測圖片
    base_t = _load_template(BASE_IMAGE)
    base_ready = base_t is not None

    print(f"--- 獨立冷卻模式啟動 ---")
    print(f"每張圖片獨立冷卻: {INDIVIDUAL_COOLDOWN} 秒")
    print(f"模板縮放倍率: {', '.join(f'{scale * 100:.0f}%' for scale in TEMPLATE_SCALES)}")
    if rally_ready:
        print("--- 集結序列功能已啟用 ---")
    else:
        print("【警告】集結序列圖片不齊全，已停用該功能")
    if heal_ready:
        print("--- 治療序列功能已啟用 ---")
    else:
        print("【警告】治療序列圖片不齊全，已停用該功能")
    if base_ready:
        print(f"--- 基地監測功能已啟用（每 {BASE_CHECK_INTERVAL:.0f} 秒檢查，連續 {BASE_MISSING_LIMIT} 次未出現按 ESC）---")
    else:
        print("【警告】找不到基地圖片，已停用基地監測")

    # 基地監測狀態：上次檢查時間 + 連續未出現次數
    last_base_check = time.time()
    base_missing_count = 0

    with mss.mss() as sct:
        while True:
            current_time = time.time()  # 取得當前系統時間

            # 1. 擷取螢幕
            screenshot = sct.grab(MONITOR_REGION)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # 1.4 基地監測：每隔 BASE_CHECK_INTERVAL 秒檢查一次「基地」是否出現，
            #     連續 BASE_MISSING_LIMIT 次未出現就按 ESC 並把計數歸零重新開始
            if base_ready and current_time - last_base_check >= BASE_CHECK_INTERVAL:
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

            # 1.5 集結序列優先檢查：偵測到「集結提醒」就進入序列，期間不偵測其他動作
            if rally_ready and current_time - rally_notify['last_clicked'] >= RALLY_SEQUENCE_COOLDOWN:
                max_val, _, _ = _match(frame, rally_notify)
                if max_val >= THRESHOLD:
                    time.sleep(0.2)
                    frame2 = _grab_frame(sct)
                    max_val2, max_loc2, matched_variant2 = _match(frame2, rally_notify)
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {rally_notify['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _run_rally_sequence(sct, rally_notify, rally_join, rally_confirm, rally_back, max_loc2, matched_variant2)
                        continue
                    else:
                        print(f"⚠️ {rally_notify['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})")

            # 1.6 治療序列優先檢查：偵測到 startmyheal 就進入序列，期間不偵測其他動作
            if heal_ready and current_time - heal_start['last_clicked'] >= HEAL_SEQUENCE_COOLDOWN:
                max_val, _, _ = _match(frame, heal_start)
                if max_val >= THRESHOLD:
                    time.sleep(0.2)
                    frame2 = _grab_frame(sct)
                    max_val2, max_loc2, matched_variant2 = _match(frame2, heal_start)
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {heal_start['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _run_heal_sequence(sct, heal_start, heal_confirm, heal_lookforhelp, max_loc2, matched_variant2)
                        continue
                    else:
                        print(f"⚠️ {heal_start['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})")

            # 2. 檢查清單中的每一張圖
            for t in templates:
                # 檢查冷卻時間：如果現在時間距離上次點擊還不到 3 秒，直接跳過這張圖不偵測
                if current_time - t['last_clicked'] < INDIVIDUAL_COOLDOWN:
                    continue

                max_val, _, _ = _match(frame, t)

                if max_val >= THRESHOLD:
                    # 二次確認機制：短暫等待後再次檢測，避免誤判
                    time.sleep(0.2)

                    # 重新擷取螢幕並進行第二次匹配
                    screenshot2 = sct.grab(MONITOR_REGION)
                    frame2 = np.array(screenshot2)
                    frame2 = cv2.cvtColor(frame2, cv2.COLOR_BGRA2BGR)

                    max_val2, max_loc2, matched_variant2 = _match(frame2, t)

                    # 只有兩次都檢測到才點擊
                    if max_val2 >= THRESHOLD:
                        print(f"✅ {t['name']} 二次確認成功 (匹配度: {max_val:.2f} -> {max_val2:.2f})")
                        _click_template(t, max_loc2, matched_variant2)

                        time.sleep(0.5)  # 點擊後短暫等待，避免連續點擊過快
                    else:
                        print(f"⚠️ {t['name']} 二次確認失敗 (首次: {max_val:.2f}, 二次: {max_val2:.2f})") 
            
            # 降低 CPU 負擔
            time.sleep(3)   # 每次迴圈結束後等待 3 秒，這樣每張圖的冷卻時間就不會被過度觸發

if __name__ == "__main__":
    try:
        solve_screen_detection()
    except KeyboardInterrupt:
        print("\n--- 腳本已停止 ---")
