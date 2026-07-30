"""ROI 座標量測工具（開發輔助用，不影響 DailyWork 主程式）。

用途：找出某張圖示實際會出現在螢幕的哪個範圍，以便日後把該圖示的搜尋區域
從全螢幕縮小成一小塊 ROI（面積縮小 8 倍 ≈ 比對快 8 倍）。

用法：
    # 盯著「集結提醒」，每次出現就印座標；Ctrl+C 結束並輸出建議 ROI
    python roi_finder.py 集結提醒.png

    # 同時盯多張（適合同一位置的不同狀態，例如閒置三隊／二隊）
    python roi_finder.py 閒置三隊.png 閒置二隊.png

    # 掃描目前畫面，列出所有能匹配到的圖示位置（遊戲畫面要先擺好）
    python roi_finder.py --scan

選項：
    --margin N     建議 ROI 四周各留的緩衝像素（預設 200）
    --interval N   每次比對的間隔秒數（預設 0.3；圖示只短暫出現時調小）
    --seconds N    跑 N 秒自動結束（預設 0 = 一直跑到 Ctrl+C）
    --delay N      倒數 N 秒才開始掃，用來把遊戲視窗切到最前面

注意：比對的是「螢幕實際看到的畫面」，其他視窗（包含終端機本身）蓋住遊戲的
部分一律偵測不到。量測前先確認目標圖示沒有被任何視窗遮住，必要時用 --delay。

只在序列中短暫出現的圖示（閒置三隊／二隊、出征確定、十字鎬…），建議自己手動
操作到那一頁停住不動再跑，比等程式跑到那一步容易抓得多。
"""
import sys
import time

import mss

import DailyWork as D


# watch 模式每次比對的間隔。彩色模板單次比對就要約 0.6 秒，實際採樣率會被比對
# 本身拖慢，抓短暫畫面時可用 --interval 0 讓它盡可能連續掃。
SCAN_INTERVAL = 0.3
# 產生建議 ROI 時四周各留的緩衝像素。預設 200 是為了容納每次開遊戲視窗的位置偏移。
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


def _countdown(delay):
    if not delay:
        return
    print(f"--- {delay:.0f} 秒後開始，請把遊戲視窗切到最前面 ---")
    for remain in range(int(delay), 0, -1):
        print(f"    {remain}...", end='\r', flush=True)
        time.sleep(1)
    print("    開始              ")


def scan_once(delay=0):
    """掃描目前畫面，列出所有 icon 的匹配度與位置。"""
    paths = sorted(D.ICON_DIR.glob('*.png'))
    if not paths:
        print(f"【錯誤】{D.ICON_DIR} 下找不到任何 png")
        return

    _countdown(delay)

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


def _suggest_roi(filename, hits, margin):
    """把累積到的命中框換算成建議 ROI，並印出可貼進 IMAGE_ROIS 的一行。"""
    lefts = [b['left'] for b in hits]
    tops = [b['top'] for b in hits]
    rights = [b['right'] for b in hits]
    bottoms = [b['bottom'] for b in hits]

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

    print(f"[{filename}] 共 {len(hits)} 次命中，實際出現範圍："
          f"左上({min(lefts)},{min(tops)}) 右下({max(rights)},{max(bottoms)})")
    print(f"  四周各留 {margin}px 緩衝，比對面積約可縮小 {ratio:.1f} 倍：")
    print(f'    # 實測位置 ({min(lefts)},{min(tops)})-({max(rights)},{max(bottoms)})，±{margin}px')
    print(f'    _icon_path(\'{filename}\'): '
          f'{{"top": {roi_top}, "left": {roi_left}, "width": {roi_w}, "height": {roi_h}}},\n')


def watch(filenames, margin=ROI_MARGIN, interval=SCAN_INTERVAL, seconds=0, delay=0):
    # 量測時要掃全畫面才知道圖示真正會出現在哪，暫時忽略已設定的 ROI
    saved_rois = D.IMAGE_ROIS
    D.IMAGE_ROIS = {}
    targets = []
    for name in filenames:
        t = D._load_template(D.ICON_DIR / name)
        if t is not None:
            targets.append({'name': name, 't': t, 'hits': []})
    D.IMAGE_ROIS = saved_rois
    if not targets:
        return

    for tg in targets:
        print(f"--- 盯著 {tg['name']}（{'灰階' if tg['t']['gray'] else '彩色'}比對）---")
    limit_desc = f"，{seconds} 秒後自動結束" if seconds else "，按 Ctrl+C 結束"
    print(f"--- 門檻 {D.THRESHOLD}，間隔 {interval} 秒{limit_desc} ---")

    _countdown(delay)
    print()

    start = time.time()
    rounds = 0
    try:
        with mss.mss() as sct:
            while not (seconds and time.time() - start >= seconds):
                frame = D._grab_frame(sct)
                rounds += 1
                for tg in targets:
                    val, loc, variant = D._match(frame, tg['t'])
                    if val >= D.THRESHOLD:
                        box = _center_and_box(loc, variant)
                        tg['hits'].append(box)
                        print(f"[{tg['name']} #{len(tg['hits']):3d}] 匹配 {val:.2f} "
                              f"scale {variant['scale']:.2f}  "
                              f"左上({box['left']},{box['top']}) 右下({box['right']},{box['bottom']}) "
                              f"中心({box['cx']},{box['cy']})")
                if interval:
                    time.sleep(interval)
    except KeyboardInterrupt:
        pass

    elapsed = time.time() - start
    rate = rounds / elapsed if elapsed else 0
    print(f"\n--- 共掃 {rounds} 輪 / {elapsed:.1f} 秒（每秒 {rate:.1f} 次）---")
    if rate < 1:
        hint = "可加 --interval 0，或手動停在該頁面再量" if interval else "建議手動停在該頁面再量"
        print(f"--- 提示：採樣率偏低，短暫出現的圖示可能被錯過；{hint} ---")
    print()

    for tg in targets:
        if tg['hits']:
            _suggest_roi(tg['name'], tg['hits'], margin)
        else:
            print(f"[{tg['name']}] 全程沒有偵測到，無法產生 ROI\n")


def _parse_args(argv):
    opts = {'margin': ROI_MARGIN, 'interval': SCAN_INTERVAL, 'seconds': 0, 'delay': 0}
    files = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--margin', '--interval', '--seconds', '--delay'):
            if i + 1 >= len(argv):
                print(f"【錯誤】{a} 後面要接數值")
                return None, None
            opts[a[2:]] = float(argv[i + 1])
            i += 2
        else:
            files.append(a)
            i += 1
    opts['margin'] = int(opts['margin'])
    return files, opts


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == '--scan':
        _, opts = _parse_args(args[1:])
        scan_once(opts['delay'] if opts else 0)
    elif args:
        files, opts = _parse_args(args)
        if files:
            watch(files, opts['margin'], opts['interval'], opts['seconds'], opts['delay'])
        elif files is not None:
            print(__doc__)
    else:
        print(__doc__)
