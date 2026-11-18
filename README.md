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

開啟操作視窗：雙擊 `start_dailywork.vbs`（全程不出現命令視窗）。也可以執行：

```bat
start_dailywork.bat
```

1. 勾選要啟用的功能（包含集結、幫助盟友、治療、採集、狩獵、捐獻與基地監測）。
2. 在參數分頁手動填入數值；時間單位皆為秒，擷取範圍單位為像素。
3. 按「執行」，操作視窗會自動最小化到 Windows 工作列。
4. 要停止時，從工作列還原視窗，按「停止」。關閉操作視窗也會先停止腳本。

執行期間設定會鎖定，停止後可修改並重新執行。錯誤輸入會在執行前提示；執行紀錄顯示於視窗下方。
按「儲存為預設」會先驗證所有參數，再把功能開關與參數存到程式旁的 `dailywork_settings.json`（打包成 exe 時存在 exe 旁），之後開啟視窗會自動載入；沒有存過或檔案損毀時使用 `DailyWork.py` 的預設值。要恢復程式預設，刪除該檔即可。畫面範圍可在「畫面」分頁調整，但既有圖片 ROI 仍採螢幕絕對座標。
介面使用 Python 內建 Tkinter，不需新增 pip 套件。`start_dailywork.bat` 檢查通過後會用 `pyw`／`pythonw` 開啟介面，不會留下命令視窗（批次檔本身的視窗只會短暫閃一下就關閉）；缺少套件時則會停在命令視窗顯示提示。`start_dailywork.vbs` 會以隱藏模式（`--hidden`，不暫停）執行同一個批次檔，因此連閃一下都沒有；檢查失敗時改跳出提示框，請改執行 `start_dailywork.bat` 查看詳細訊息。

若要使用原本無操作介面的模式：

```bat
python DailyWork.py --console
```

命令列模式可按 `Ctrl+C` 停止。

要打包成單一 exe（icon 內嵌、不開命令視窗）時，執行 `build.bat`，成品在 `dist\DailyWork.exe`。exe 版只有操作介面；因為沒有命令視窗，不要用 `--console` 啟動 exe。

> 注意：程式已關閉 PyAutoGUI 的滑鼠角落緊急停止機制，避免滑鼠經過螢幕左上角時誤停。

## 主要行為

程式會擷取 `MONITOR_REGION` 設定的畫面範圍，使用 `icon/` 內的圖片模板進行比對。預設比對門檻為 `0.80`，模板會以 95%、100%、105% 三種縮放倍率比對（`TEMPLATE_SCALES`）。

## 功能開關

操作視窗可直接勾選功能；預設開關集中在 `DailyWork.py` 頂端。Python 布林值請使用 `True` / `False`。

- `ENABLE_TAKEMYHEAL_DETECTION`：啟用 `takemyheal.png` 普通偵測
- `ENABLE_TAKEMYHEAL8LV_DETECTION`：啟用 `takemyheal8lv.png` 普通偵測
- `ENABLE_HELP_DETECTION`：啟用 `help.png` 普通偵測
- `ENABLE_EXIT_GAME_DETECTION`：啟用 `退出遊戲.png` 普通偵測
- `ENABLE_RALLY_SEQUENCE`：啟用集結序列
- `ENABLE_HEAL_SEQUENCE`：啟用治療序列
- `ENABLE_GATHER_SEQUENCE`：啟用採集序列
- `ENABLE_HUNT_ZOMBIE_SEQUENCE`：啟用狩獵金幣小殭屍序列
- `ENABLE_BASE_MONITORING`：啟用基地監測
- `ENABLE_DONATE_SEQUENCE`：啟用同盟捐獻序列

### 一般圖片點擊

一般偵測清單：

- `takemyheal.png`
- `takemyheal8lv.png`
- `help.png`
- `退出遊戲.png`

每張圖有獨立 3 秒冷卻。偵測到圖片後會二次確認，兩次都達到門檻才點擊圖片中心。

序列內標示的 `2 秒內`、`3 秒內`、`10 秒內` 都是最大等待時間；一旦偵測到目標圖片會立即點擊，不會等滿秒數才執行。
序列內的輪詢間隔由 `SEQUENCE_POLLING_INTERVAL` 控制，點擊後短暫緩衝由 `SEQUENCE_AFTER_CLICK_DELAY` 控制。

### 基地監測

每 10 秒檢查一次 `基地.png`。如果連續 5 次未偵測到基地，就按一次 `ESC`，並重置計數。

基地監測不會阻擋同一輪後續偵測。

### 集結序列

觸發條件：偵測到 `集結提醒.png` 後等待 `RALLY_ENTRY_DELAY` 設定秒數，再次偵測仍存在才進入序列。

流程：

1. 偵測到 `集結提醒.png`
2. 等待 `RALLY_ENTRY_DELAY` 設定秒數後再次確認 `集結提醒.png` 仍存在
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

每 1 分鐘檢查一次進入條件。以下條件成立就進入採集序列：

- 偵測到 `基地.png`，且未偵測到 `出征隊列.png`

流程：

1. 點擊 `尋找.png`
2. 點擊 `選擇採集.png`
3. 2 秒內若偵測到 `灰色金礦.png` 就點擊，否則跳過
4. 同時偵測 `減號.png` 與 `加號.png`，點擊兩者水平距離由左到右 60% 的位置
5. 點擊 `搜索.png`
6. 點擊 `十字鎬.png`
7. 點擊閒置隊伍，`閒置三隊.png` 優先於 `閒置二隊.png`
8. 點擊 `出征確定.png`

除灰色金礦可跳過外，任何必要步驟在設定時間內偵測不到需要的圖片，都會按 `ESC` 並結束採集序列。一般步驟使用 `GATHER_STEP_TIMEOUT`，搜索後結果、閒置隊伍與出征確認等較慢畫面使用 `GATHER_SLOW_STEP_TIMEOUT`；十字鎬後到閒置隊伍頁面的固定緩衝則使用較短的 `GATHER_FAST_STEP_DELAY`。

### 狩獵金幣小殭屍序列

每 1 分鐘檢查一次入口。偵測到 `體力108.png` 就進入狩獵金幣小殭屍序列。

流程：

1. 點擊 `基地.png`
2. 點擊 `世界.png`
3. 將滑鼠移動到螢幕中央，向下滾動 15 段，每段間隔 0.2 秒
4. 2 秒內若偵測到 `縮小15段後金幣殭屍.png` 就點擊並繼續；若沒有偵測到，就點擊 `世界視角基地.png` 並結束序列
5. 10 秒內同時偵測 `特殊事件.png` 與 `每日任務.png`，點擊兩圖中心點連線的 50% 位置
6. 點擊 `攻擊按鈕.png`
7. 2 秒內若偵測到 `閒置三隊.png` 或 `閒置二隊.png` 就先點擊，三隊優先；若沒有偵測到就跳過
8. 點擊 `出征確定.png`

除「縮小15段後金幣殭屍」可走返回基地分支外，任何步驟 2 秒內偵測不到需要的圖片，都會按 `ESC` 並結束狩獵序列。

### 同盟捐獻序列

每 `DONATE_INTERVAL` 秒執行一次（預設 7200 秒＝2 小時）；開始執行後的第一個空檔會先跑一次。

流程：

1. 點擊 `同盟.png`
2. 點擊 `同盟科技.png`
3. 點擊 `推薦科技.png`
4. 偵測 `捐獻.png` 或 `捐獻500.png`（任一張即可），按住 `DONATE_HOLD_SECONDS` 秒（預設 5 秒）
5. 放開後等待 `DONATE_AFTER_HOLD_DELAY` 秒，再連按 `DONATE_ESC_COUNT` 次 `ESC`（預設 4 次，間隔 `DONATE_ESC_INTERVAL` 秒）離開

任何步驟在 `DONATE_STEP_TIMEOUT` 秒（預設 2 秒）內偵測不到需要的圖片，都會按 `ESC` 並結束捐獻序列；中途結束也會重新計時，下次同樣等滿間隔。到期時若其他序列正在執行，會在該序列結束後的第一個空檔補做，不會被跳過。

## 偵測優先順序

每一輪主迴圈的順序如下：

1. 基地監測
2. 集結序列
3. 治療序列
4. 採集序列
5. 狩獵金幣小殭屍序列
6. 同盟捐獻序列
7. 一般圖片點擊

集結、治療、採集、狩獵、捐獻序列執行期間不會進行其他偵測；序列結束後進入下一輪主迴圈。

## 圖片模板

所有模板圖片都放在 `icon/`，依用途分在子資料夾（例如 `icon/集結序列/`、`icon/共用/`）。如果遊戲 UI 有更新、解析度改變或辨識不穩，優先更新對應圖片。

新增或替換模板時，請保持檔名與 `DailyWork.py` 內設定一致。

## 常見調整點

- `THRESHOLD`：圖片匹配門檻
- `TEMPLATE_SCALES`：模板縮放倍率
- `MONITOR_REGION`：螢幕擷取範圍
- `INDIVIDUAL_COOLDOWN`：一般圖片點擊冷卻
- `SEQUENCE_POLLING_INTERVAL` / `SEQUENCE_AFTER_CLICK_DELAY`：序列內偵測頻率與每次點擊後緩衝
- `BASE_CHECK_INTERVAL` / `BASE_MISSING_LIMIT`：基地監測頻率與容錯次數
- `RALLY_ENTRY_DELAY` / `RALLY_SEQUENCE_COOLDOWN` / `RALLY_SEQUENCE_TIMEOUT`：集結進入前的確認延遲、序列結束後冷卻與整體逾時
- `GATHER_CHECK_INTERVAL` / `GATHER_STEP_TIMEOUT` / `GATHER_SLOW_STEP_TIMEOUT`：採集檢查間隔、一般步驟逾時與慢換頁步驟逾時
- `GATHER_FAST_STEP_DELAY` / `GATHER_SLOW_STEP_DELAY` / `GATHER_QUANTITY_CLICK_RATIO`：採集序列點擊後緩衝與減號/加號點擊比例
- `HUNT_CHECK_INTERVAL` / `HUNT_STEP_TIMEOUT` / `HUNT_EVENT_MIDPOINT_TIMEOUT`：狩獵金幣小殭屍檢查間隔、一般步驟逾時與特殊事件/每日任務中心點逾時
- `HUNT_SCROLL_STEPS` / `HUNT_SCROLL_INTERVAL`：狩獵序列縮小滾輪段數與每段間隔
- `DONATE_INTERVAL` / `DONATE_STEP_TIMEOUT` / `DONATE_HOLD_SECONDS`：捐獻間隔、每步驟逾時與按住捐獻的秒數
- `DONATE_AFTER_HOLD_DELAY` / `DONATE_ESC_COUNT` / `DONATE_ESC_INTERVAL`：放開捐獻後的等待、結束時按 ESC 的次數與間隔
