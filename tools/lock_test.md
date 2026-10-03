# Manual Protocol: Excel File-Lock Test (E9 Verification)

> [!IMPORTANT]
> **Automated unit tests simulate file locks via monkeypatching `open` and `os.replace`, but they do NOT substitute for physical OS kernel-level and OLE file locking behavior in Microsoft Excel or LibreOffice.**
> Windows and macOS file-system semantics differ in mandatory vs advisory file locking. This manual test must be executed on the actual demo workstation.

---

## Purpose
Verify that when Microsoft Excel or LibreOffice has `logs/inspections.xlsx` or `logs/inspections.csv` open with an active write lock:
1. The real-time vision loop and inspection pipeline **never block or drop frame rate**.
2. SQLite continues logging every record as the authoritative source of truth.
3. The CSV appender retains pending records in memory, sets `log_status=locked`, and flushes them as soon as the file is unlocked.
4. The Excel writer generates timestamped fallback files `logs/billet_log_<timestamp>.xlsx` without losing records.
5. Once Excel is closed, the system automatically recovers and updates `logs/inspections.xlsx`.

---

## Prerequisites
- The BilletVision backend running with synthetic or real camera source.
- Microsoft Excel (or LibreOffice Calc) installed on the demo machine.
- Terminal with access to `data/` and `logs/`.

---

## Step-by-Step Test Procedure

### 1. Pre-Run Zeroing
1. Stop the backend if running.
2. Clean existing demo logs:
   ```bash
   rm -f logs/inspections.csv logs/inspections.xlsx logs/billet_log_*.xlsx
   ```
3. Start the backend:
   ```bash
   cd backend && source .venv/bin/activate && python -m billetvision.main
   ```
4. Verify that `logs/inspections.csv` and `logs/inspections.xlsx` are created after the first inspection.

### 2. Introduce Active File Lock in Excel
1. Open `logs/inspections.xlsx` directly in **Microsoft Excel**.
2. Click inside any cell and begin editing (e.g. type `TEST` but do not press enter, or simply keep the file open in Excel on Windows where Excel obtains an exclusive `FILE_SHARE_READ` lock).
3. Observe the web dashboard header:
   - Within 5 seconds, the UI writer status banner should display **"Writer Blocked / File Locked"**.

### 3. Run 200 Consecutive Inspections
1. Run a 200-billet stream or synthetic generator batch:
   ```bash
   # Synthetic loop continues delivering billets at ~1 per 2 seconds
   ```
2. Monitor pipeline processing FPS on the UI health strip.
   - **Verification Point A:** The FPS counter must stay steady ($\ge 15\text{ FPS}$). The vision processing thread MUST NOT freeze or drop below normal throughput.
3. Check the `logs/` directory while Excel is still open:
   - Notice that fallback workbooks `logs/billet_log_<timestamp>.xlsx` are created automatically.
   - No error crashes occur in the backend log.

### 4. Release Lock & Assert Total Row Equality
1. Save and close Microsoft Excel completely.
2. Wait 5 seconds for the next sync debounce cycle.
3. Verify that the UI writer status indicator turns green (**"Writer OK"**).
4. Run row count verification across all three stores:
   ```bash
   # 1. SQLite count
   sqlite3 data/billetvision.db "SELECT count(*) FROM inspections;"

   # 2. CSV line count (minus header)
   wc -l logs/inspections.csv

   # 3. XLSX row count (via python one-liner)
   python -c "import openpyxl; wb = openpyxl.load_workbook('logs/inspections.xlsx'); ws = wb['Inspections']; print(ws.max_row - 1)"
   ```
5. **Pass Criteria:**
   - SQLite row count == CSV row count == XLSX row count ($\ge 200$).
   - Exactly zero inspections missing.
   - No duplicate record IDs.
