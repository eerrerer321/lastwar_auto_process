"""ROI 座標量測工具（開發輔助用，不影響 DailyWork 主程式）。

用途：找出某張圖示實際會出現在螢幕的哪個範圍，以便日後把該圖示的搜尋區域
從全螢幕縮小成一小塊 ROI（面積縮小 8 倍 ≈ 比對快 8 倍）。

用法：
    # 盯著「集結提醒」，每次出現就印座標；Ctrl+C 結束並輸出建議 ROI
    python roi_finder.py 集結提醒.png

    # 掃描目前畫面，列出所有能匹配到的圖示位置（遊戲畫面要先擺好）
    python roi_finder.py --scan
"""
import sys
import time

import mss

import DailyWork as D


SCAN_INTERVAL = 0.5   # watch 模式每次比對的間隔
# 產生建議 ROI 時四周各留的緩衝像素。預設 200 是為了容納每次開遊戲視窗的位置偏移，
# 可用第二個命令列參數覆寫：python roi_finder.py 集結提醒.png 300
ROI_MARGIN = 200


def _center_and_box(loc, variant):
    left = D.MONITOR_REGION["left"] + loc[0]
    top = D.MONITOR_REGION["top"] + loc[1]
    return {
        'left': left,
        'top': top,
        'right': left + variant['w'],
        'bottom': top + variant['h'],
        'cx': left + variant['w'] // 2,
        'cy': top + variant['h'] // 2,
    }


def scan_once():
    """掃描目前畫面，列出所有 icon 的匹配度與位置。"""
    paths = sorted(D.ICON_DIR.glob('*.png'))
    if not paths:
        print(f"【錯誤】{D.ICON_DIR} 下找不到任何 png")
        return

    with mss.mss() as sct:
        frame = D._grab_frame(sct)

    print(f"畫面尺寸: {frame.shape[1]}x{frame.shape[0]}  門檻: {D.THRESHOLD}\n")
    hits, misses = [], []
    for p in paths:
        t = D._load_template(p)
        if t is None:
            continue
        val, loc, variant = D._match(frame, t)
        if val >= D.THRESHOLD:
            box = _center_and_box(loc, variant)
            hits.append((val, p.name, box, variant['scale']))
        else:
            misses.append((val, p.name))

    print(f"=== 有匹配到（{len(hits)} 張）===")
    for val, name, box, scale in sorted(hits, reverse=True):
        print(f"  {name:24s} 匹配 {val:.2f} scale {scale:.2f}  "
              f"左上({box['left']},{box['top']}) 右下({box['right']},{box['bottom']}) "
              f"中心({box['cx']},{box['cy']})")

    print(f"\n=== 未達門檻（{len(misses)} 張，僅列最高 10 筆）===")
    for val, name in sorted(misses, reverse=True)[:10]:
        print(f"  {name:24s} 匹配 {val:.2f}")


def watch(filename, margin=ROI_MARGIN):
    path = D.ICON_DIR / filename
    # 量測時要掃全畫面才知道圖示真正會出現在哪，暫時忽略已設定的 ROI
    saved_rois = D.IMAGE_ROIS
    D.IMAGE_ROIS = {}
    t = D._load_template(path)
    D.IMAGE_ROIS = saved_rois
    if t is None:
        return

    mode = "灰階" if t['gray'] else "彩色"
    print(f"--- 盯著 {filename}（{mode}比對，門檻 {D.THRESHOLD}，每 {SCAN_INTERVAL} 秒一次）---")
    print("--- 讓該圖示出現幾次後按 Ctrl+C 結束，會輸出建議 ROI ---\n")

    lefts, tops, rights, bottoms = [], [], [], []
    count = 0
    try:
        with mss.mss() as sct:
            while True:
                frame = D._grab_frame(sct)
                val, loc, variant = D._match(frame, t)
                if val >= D.THRESHOLD:
                    box = _center_and_box(loc, variant)
                    lefts.append(box['left'])
                    tops.append(box['top'])
                    rights.append(box['right'])
                    bottoms.append(box['bottom'])
                    count += 1
                    print(f"[{count:3d}] 匹配 {val:.2f} scale {variant['scale']:.2f}  "
                          f"左上({box['left']},{box['top']}) 右下({box['right']},{box['bottom']}) "
                          f"中心({box['cx']},{box['cy']})")
                time.sleep(SCAN_INTERVAL)
    except KeyboardInterrupt:
        pass

    print()
    if not count:
        print("--- 全程沒有偵測到，無法產生 ROI ---")
        return

    screen_w = D.MONITOR_REGION["left"] + D.MONITOR_REGION["width"]
    screen_h = D.MONITOR_REGION["top"] + D.MONITOR_REGION["height"]
    roi_left = max(D.MONITOR_REGION["left"], min(lefts) - margin)
    roi_top = max(D.MONITOR_REGION["top"], min(tops) - margin)
    roi_right = min(screen_w, max(rights) + margin)
    roi_bottom = min(screen_h, max(bottoms) + margin)
    roi_w = roi_right - roi_left
    roi_h = roi_bottom - roi_top

    full_area = D.MONITOR_REGION["width"] * D.MONITOR_REGION["height"]
    ratio = full_area / max(1, roi_w * roi_h)

    print(f"--- 共 {count} 次命中，實際出現範圍："
          f"左上({min(lefts)},{min(tops)}) 右下({max(rights)},{max(bottoms)}) ---")
    print(f"--- 建議 ROI（四周各留 {margin}px 緩衝），比對面積約可縮小 {ratio:.1f} 倍 ---")
    print("--- 貼進 DailyWork.py 的 IMAGE_ROIS： ---\n")
    print(f'    # 實測位置 ({min(lefts)},{min(tops)})-({max(rights)},{max(bottoms)})，±{margin}px')
    print(f'    _icon_path(\'{filename}\'): '
          f'{{"top": {roi_top}, "left": {roi_left}, "width": {roi_w}, "height": {roi_h}}},')


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == '--scan':
        scan_once()
    elif args:
        margin = int(args[1]) if len(args) > 1 else ROI_MARGIN
        watch(args[0], margin)
    else:
        print(__doc__)
