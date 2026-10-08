# RPi Health Monitor

Automatic daily health check for a Raspberry Pi, run from a Windows PC on the same network.
It checks **power**, **internet** and a **website**, saves timestamped logs and screenshots,
and creates a **weekly report** showing how many times each problem happened.

Runs fully unattended: the Windows PC only needs power and Ethernet.

---

## How it works

| # | Test | How | If it fails |
|---|------|-----|-------------|
| 1 | **Power** | Windows pings the RPi | Tests 2 and 3 are marked `FAIL-BLOCKED` |
| 2 | **Internet** | Windows SSHes into the RPi and pings `8.8.8.8` / `1.1.1.1` from the RPi | Test 3 is marked `FAIL-BLOCKED` |
| 3 | **Website** | Chrome (headless) opens the URL, waits 50 s, takes a screenshot | Website problem only |

Each test retries several times (up to ~5 minutes) before failing, so an RPi or router that is
still booting after a power cut is not reported as a failure.

### Result meaning

| Power | Internet | Website | Root cause |
|-------|----------|---------|------------|
| FAIL | FAIL-BLOCKED | FAIL-BLOCKED | Power off / RPi not reachable |
| PASS | FAIL | FAIL-BLOCKED | Internet down (or "SSH error" if login to the RPi failed) |
| PASS | PASS | FAIL | Website not loading |
| PASS | PASS | PASS | All OK |

---

## Files

| File | Purpose |
|------|---------|
| `rpi_daily_check.py` | Main script: runs the 3 tests, writes logs, screenshot, CSV |
| `weekly_report.py` | Builds the weekly (or N-day) report from the CSV |
| `run_daily_check.bat` | Used by Task Scheduler to run the daily check |
| `run_weekly_report.bat` | Used by Task Scheduler to run the weekly report |
| `install_tasks.bat` | Creates both scheduled tasks (run once as Administrator) |

---

## Requirements

- Windows 10 / 11 (has the built-in OpenSSH client)
- Python 3.8+
- Google Chrome
- Raspberry Pi with SSH enabled, on the same network as the PC

---

## Setup (one time)

### 1. Download
Click **Code → Download ZIP** on this page and extract the files into `C:\RPi_Monitor\`.
(If you use a different folder, change `BASE_DIR` in both `.py` files and the paths in the `.bat` files.)

### 2. Install Python and Selenium
1. Install Python from https://www.python.org — tick **"Add Python to PATH"** during install.
2. Open Command Prompt and run:
   ```
   pip install selenium
   ```
   Selenium downloads the matching ChromeDriver automatically.

### 3. Password-less SSH to the RPi
The script runs unattended, so it cannot type a password. Open **PowerShell** and run
(replace `pi` and `192.168.1.50` with your RPi user and IP):
```powershell
ssh-keygen -t ed25519
```
Press Enter for every question (no passphrase). Then copy the key to the RPi:
```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh pi@192.168.1.50 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```
Test it — this must print `ok` **without** asking for a password:
```powershell
ssh pi@192.168.1.50 "echo ok"
```

### 4. Edit the config
Open `rpi_daily_check.py` and edit the CONFIG block at the top:
```python
RPI_IP = "192.168.1.50"          # your RPi IP
RPI_USER = "pi"                  # your RPi SSH user
WEBSITE_URL = "http://192.168.1.50"   # website to check
EXPECTED_TEXT = ""               # optional text that must appear on the page
PAGE_WAIT_SECONDS = 50
```

### 5. Test it manually
```
cd C:\RPi_Monitor
py -3 rpi_daily_check.py
py -3 weekly_report.py
```
Check that a folder like `C:\RPi_Monitor\Reports\2026-10-08\` was created with a log, summary and screenshot.

### 6. Schedule it
Right-click `install_tasks.bat` → **Run as administrator**. This creates:
- **RPi Daily Check** — every day at 09:00
- **RPi Weekly Report** — every Monday at 09:30

Then open **Task Scheduler**, and for **both** tasks:
- General tab: select **"Run whether user is logged on or not"**
- Triggers → Edit: tick **"Delay task for: 5 minutes"** (gives RPi and router time to boot after a power cut)
- Settings tab: tick **"Run task as soon as possible after a scheduled start is missed"**

> Want to measure *how long* outages last? Run the check every hour: in `install_tasks.bat`
> change `/sc daily /st 09:00` to `/sc hourly`. The weekly report supports multiple runs per day.

### 7. Make the PC fully unattended
- BIOS: set **"Restore on AC Power Loss" = Power On** (PC boots by itself after a power cut)
- Windows power settings: **Sleep = Never**
- Windows Update: set active hours so it does not restart during the check

---

## Output

```
C:\RPi_Monitor\
├── all_results.csv                          one row per run (open in Excel)
├── scheduler_output.txt                     console output from scheduled runs
└── Reports\
    ├── 2026-10-08\
    │   ├── log_09-00-00.txt                 every step with timestamp
    │   ├── screenshot_09-00-00.png          website screenshot
    │   └── summary_09-00-00.txt             short result
    └── Weekly\
        └── report_2026-10-02_to_2026-10-08.txt
```

### Example log
```
2026-10-08 09:00:01 | INFO    | TEST 1 - POWER: checking if RPi 192.168.1.50 is powered on
2026-10-08 09:00:04 | INFO    |   attempt 1/8: ping=OK, ssh_port_22=OPEN | ...
2026-10-08 09:00:04 | INFO    | TEST 1 RESULT: PASS - RPi replies to ping (SSH port open)
2026-10-08 09:00:05 | INFO    | TEST 2 - INTERNET: pinging 8.8.8.8, 1.1.1.1 from the RPi via SSH
2026-10-08 09:00:09 | INFO    | TEST 2 RESULT: PASS - RPi reached 8.8.8.8
2026-10-08 09:00:09 | INFO    | TEST 3 - WEBSITE: opening http://192.168.1.50 in Chrome
2026-10-08 09:01:01 | INFO    |   screenshot saved: C:\RPi_Monitor\Reports\2026-10-08\screenshot_09-00-00.png
2026-10-08 09:01:01 | INFO    | TEST 3 RESULT: PASS - Website loaded
```

### Weekly report
Run any time:
```
py -3 weekly_report.py        # last 7 days
py -3 weekly_report.py 30     # last 30 days
```
The report shows total runs, availability %, failures by root cause, failures per test,
a day-by-day table, and days with no run at all.

> **Days with "NO RUN"**: if the PC shares the power line with the RPi, a missing day usually means a power cut
> (both were off). Put the PC on a small UPS if you want it to log power failures itself.

---

## Tips for frequent power cuts

Sudden power loss can corrupt the RPi's SD card, and then it may not boot at all. To prevent this:

1. **Mini 5V UPS / UPS HAT** for the RPi — best fix.
2. **Read-only filesystem**: `sudo raspi-config` → Performance → Overlay File System → Enable.
3. **Hardware watchdog** (auto-reboot if the RPi freezes):
   add `dtparam=watchdog=on` to `/boot/firmware/config.txt`
   and set `RuntimeWatchdogSec=15` in `/etc/systemd/system.conf`.
4. Use a **high-endurance SD card** (or USB SSD) and the **official power supply**.
5. Keep a **backup image** of the SD card.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Test 2 says "SSH to RPi failed" | Redo step 3; make sure `ssh pi@IP "echo ok"` works with no password |
| Scheduled task does nothing | Check `C:\RPi_Monitor\scheduler_output.txt`; make sure the task runs as the same Windows user that created the SSH key |
| `py` not found | Reinstall Python with "Add to PATH", or replace `py -3` with the full path to `python.exe` in the `.bat` files |
| Selenium / Chrome error | Update Chrome and run `pip install -U selenium` |
| Screenshot is blank | Increase `PAGE_WAIT_SECONDS` |
