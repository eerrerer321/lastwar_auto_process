# LastWar 日常自動化

這個專案使用螢幕截圖與圖片模板比對，自動處理 LastWar 的日常操作，例如參加集結、幫助盟友、分批治療與採集。

## 執行環境

- Windows
- Python 3
- 依賴套件列在 `requirements.txt`

第一次使用前安裝依賴：

```bat
py -3 -m pip install -r requirements.txt
```

如果系統沒有 `py -3`，可改用：

```bat
python -m pip install -r requirements.txt
```

## 啟動方式

先檢查 Python 與依賴是否可用：

```bat
start_dailywork.bat --check
```

啟動自動化：

```bat
start_dailywork.bat
```

執行期間要停止程式，請在命令視窗按 `Ctrl+C`。

> 注意：程式已關閉 PyAutoGUI 的滑鼠角落緊急停止機制，避免滑鼠經過螢幕左上角時誤停。

## 主要行為

程式會擷取 `MONITOR_REGION` 設定的畫面範圍，使用 `icon/` 內的圖片模板進行比對。預設比對門檻為 `0.85`，模板會同時使用 100% 與 50% 兩種縮放倍率。

## 功能開關

功能開關集中在 `DailyWork.py` 頂端。Python 布林值請使用 `True` / `False`。

- `ENABLE_TAKEMYHEAL_DETECTION`：啟用 `takemyheal.png` 普通偵測
- `ENABLE_TAKEMYHEAL8LV_DETECTION`：啟用 `takemyheal8lv.png` 普通偵測
- `ENABLE_HELP_DETECTION`：啟用 `help.png` 普通偵測
- `ENABLE_RALLY_SEQUENCE`：啟用集結序列
- `ENABLE_HEAL_SEQUENCE`：啟用治療序列
- `ENABLE_GATHER_SEQUENCE`：啟用採集序列
- `ENABLE_BASE_MONITORING`：啟用基地監測

### 一般圖片點擊

一般偵測清單：

- `takemyheal.png`
- `takemyheal8lv.png`
- `help.png`

每張圖有獨立 3 秒冷卻。偵測到圖片後會二次確認，兩次都達到門檻才點擊圖片中心。

### 基地監測

每 10 秒檢查一次 `基地.png`。如果連續 5 次未偵測到基地，就按一次 `ESC`，並重置計數。

基地監測不會阻擋同一輪後續偵測。

### 集結序列

觸發條件：偵測到 `集結提醒.png` 後等待 15 秒，再次偵測仍存在才進入序列。

流程：

1. 偵測到 `集結提醒.png`
2. 等待 15 秒後再次確認 `集結提醒.png` 仍存在
3. 點擊 `集結提醒.png`
4. 3 秒內尋找並點擊 `加入集結+.png`
5. 2 秒內尋找並點擊 `出征確定.png`
6. 如果找不到出征確定，會嘗試連續偵測 `返回.png`
7. 序列超過 8 秒未正常結束時按 `ESC`

集結序列結束後 10 秒內不會再次進入。

### 治療序列

觸發條件：偵測到 `startmyheal.png`。

流程：

1. 點擊 `startmyheal.png`
2. 2 秒內尋找並點擊 `confirmheal_PC.png`
3. 2 秒內尋找並點擊 `lookforhelp.png`

治療序列結束後 5 秒內不會再次進入。

### 採集序列

每 1 分鐘檢查一次進入條件。以下任一條件成立就進入採集序列：

- 偵測到 `基地.png`，且未偵測到 `出征隊列.png`
- 同時偵測到 `基地.png`、`出征隊列.png`、`0隊使用中.png`

流程：

1. 點擊 `尋找.png`
2. 點擊 `選擇採集.png`
3. 2 秒內若偵測到 `灰色金礦.png` 就點擊，否則跳過
4. 同時偵測 `減號.png` 與 `加號.png`，點擊兩者水平距離由左到右 55% 的位置
5. 點擊 `搜索.png`
6. 點擊 `十字鎬.png`
7. 點擊閒置隊伍，`閒置三隊.png` 優先於 `閒置二隊.png`
8. 點擊 `出征確定.png`

除灰色金礦可跳過外，任何步驟 2 秒內偵測不到需要的圖片，都會按 `ESC` 並結束採集序列。

## 偵測優先順序

每一輪主迴圈的順序如下：

1. 基地監測
2. 集結序列
3. 治療序列
4. 採集序列
5. 一般圖片點擊

集結、治療、採集序列執行期間不會進行其他偵測；序列結束後進入下一輪主迴圈。

## 圖片模板

所有模板圖片都放在 `icon/`。如果遊戲 UI 有更新、解析度改變或辨識不穩，優先更新對應圖片。

新增或替換模板時，請保持檔名與 `DailyWork.py` 內設定一致。

## 常見調整點

- `THRESHOLD`：圖片匹配門檻
- `TEMPLATE_SCALES`：模板縮放倍率
- `MONITOR_REGION`：螢幕擷取範圍
- `INDIVIDUAL_COOLDOWN`：一般圖片點擊冷卻
- `BASE_CHECK_INTERVAL` / `BASE_MISSING_LIMIT`：基地監測頻率與容錯次數
- `GATHER_CHECK_INTERVAL` / `GATHER_STEP_TIMEOUT`：採集檢查間隔與步驟逾時
