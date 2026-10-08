"""
RPi Daily Health Check  (runs on the Windows PC)
-------------------------------------------------
Test 1 - POWER    : Is the RPi powered on?  (ping RPi from Windows + SSH port check)
Test 2 - INTERNET : Does the RPi have internet? (SSH into RPi, ping 8.8.8.8 / 1.1.1.1 from the RPi)
Test 3 - WEBSITE  : Open website in Chrome, wait 50 sec, take screenshot

Dependency rule:
  Test 1 FAIL  -> Test 2 and Test 3 are marked FAIL-BLOCKED (not run)
  Test 2 FAIL  -> Test 3 is marked FAIL-BLOCKED (not run)
  Test 1+2 PASS, Test 3 FAIL -> website problem only

Output (per run):
  C:\\RPi_Monitor\\Reports\\YYYY-MM-DD\\log_HH-MM-SS.txt         full timestamped log
  C:\\RPi_Monitor\\Reports\\YYYY-MM-DD\\screenshot_HH-MM-SS.png  website screenshot
  C:\\RPi_Monitor\\Reports\\YYYY-MM-DD\\summary_HH-MM-SS.txt     short result
  C:\\RPi_Monitor\\all_results.csv                              one row per run (used for weekly report)
"""

import csv
import logging
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ============================ CONFIG - EDIT THESE ============================
RPI_IP = "192.168.1.50"                 # IP of the Raspberry Pi
RPI_USER = "pi"                         # SSH username on the RPi
SSH_KEY = str(Path.home() / ".ssh" / "id_ed25519")   # SSH key (no password)
INTERNET_TARGETS = ["8.8.8.8", "1.1.1.1"]           # pinged FROM the RPi
WEBSITE_URL = "http://192.168.1.50"     # website to open in Chrome
EXPECTED_TEXT = ""                      # optional: text that must be on the page ("" = skip check)
PAGE_WAIT_SECONDS = 50                  # wait after opening website before screenshot
HEADLESS = True                         # True = Chrome runs invisible (needed when no one is logged in)
RETRIES = 8                             # attempts for test 1 and 2 (covers RPi/router boot time after power cut)
RETRY_GAP_SECONDS = 30
WEBSITE_ATTEMPTS = 2
BASE_DIR = Path(r"C:\RPi_Monitor")      # everything is saved here
# ============================================================================

REPORTS_DIR = BASE_DIR / "Reports"
MASTER_CSV = BASE_DIR / "all_results.csv"
CSV_HEADER = ["date", "start_time", "end_time", "duration_sec",
              "test1_power", "test2_internet", "test3_website",
              "overall", "root_cause", "details", "screenshot", "log_file"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def setup_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("rpi_check")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def run(cmd, timeout=60):
    """Run a command, return (exit_code, output). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=timeout, creationflags=NO_WINDOW)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return -2, f"Command not found: {e}"


def port_open(host, port, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def last_lines(text, n=3):
    return " / ".join([l.strip() for l in text.splitlines() if l.strip()][-n:])


# ------------------------------- TEST 1 -------------------------------------
def test1_power(log):
    log.info("TEST 1 - POWER: checking if RPi %s is powered on", RPI_IP)
    detail = ""
    for attempt in range(1, RETRIES + 1):
        code, out = run(["ping", "-n", "4", "-w", "2000", RPI_IP], timeout=30)
        ping_ok = code == 0 and "TTL=" in out.upper()   # Windows ping can return 0 on 'unreachable'
        ssh_port = port_open(RPI_IP, 22)
        log.info("  attempt %d/%d: ping=%s, ssh_port_22=%s | %s",
                 attempt, RETRIES, "OK" if ping_ok else "NO REPLY",
                 "OPEN" if ssh_port else "CLOSED", last_lines(out, 2))
        if ping_ok:
            return True, f"RPi replies to ping (SSH port {'open' if ssh_port else 'closed'})"
        detail = "RPi not replying to ping - power off, RPi crashed, or Ethernet cable issue"
        if attempt < RETRIES:
            log.info("  retrying in %ds ...", RETRY_GAP_SECONDS)
            time.sleep(RETRY_GAP_SECONDS)
    return False, detail


# ------------------------------- TEST 2 -------------------------------------
def test2_internet(log):
    """Returns (passed, detail, ssh_problem)"""
    log.info("TEST 2 - INTERNET: pinging %s from the RPi via SSH", ", ".join(INTERNET_TARGETS))
    detail, ssh_problem = "", False
    for attempt in range(1, RETRIES + 1):
        for target in INTERNET_TARGETS:
            cmd = ["ssh", "-i", SSH_KEY,
                   "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                   "-o", "StrictHostKeyChecking=accept-new",
                   f"{RPI_USER}@{RPI_IP}", f"ping -c 4 -W 3 {target}"]
            code, out = run(cmd, timeout=60)
            log.info("  attempt %d/%d -> %s: exit=%s | %s",
                     attempt, RETRIES, target, code, last_lines(out, 2))
            if code == 0:
                return True, f"RPi reached {target}", False
            if code == 255 or code < 0:      # 255 = SSH itself failed
                ssh_problem = True
                detail = f"SSH to RPi failed: {last_lines(out, 1)}"
            else:
                ssh_problem = False
                detail = f"RPi cannot reach {', '.join(INTERNET_TARGETS)} (no internet)"
        if attempt < RETRIES:
            log.info("  retrying in %ds ...", RETRY_GAP_SECONDS)
            time.sleep(RETRY_GAP_SECONDS)
    return False, detail, ssh_problem


# ------------------------------- TEST 3 -------------------------------------
def test3_website(log, shot_path: Path):
    log.info("TEST 3 - WEBSITE: opening %s in Chrome", WEBSITE_URL)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        return False, "selenium not installed (run: pip install selenium)"

    detail = ""
    for attempt in range(1, WEBSITE_ATTEMPTS + 1):
        opts = Options()
        if HEADLESS:
            opts.add_argument("--headless=new")
        for a in ["--window-size=1920,1080", "--disable-gpu", "--no-sandbox",
                  "--ignore-certificate-errors", "--disable-dev-shm-usage"]:
            opts.add_argument(a)
        driver = None
        try:
            driver = webdriver.Chrome(options=opts)
            driver.set_page_load_timeout(PAGE_WAIT_SECONDS + 30)
            t0 = time.time()
            try:
                driver.get(WEBSITE_URL)
                log.info("  attempt %d/%d: page responded in %.1fs, waiting %ds to fully load ...",
                         attempt, WEBSITE_ATTEMPTS, time.time() - t0, PAGE_WAIT_SECONDS)
            except Exception as e:
                log.warning("  page load timed out / errored: %s", str(e).splitlines()[0])
            time.sleep(PAGE_WAIT_SECONDS)

            driver.save_screenshot(str(shot_path))
            log.info("  screenshot saved: %s", shot_path)

            title = driver.title or ""
            src = driver.page_source.lower()
            log.info("  page title: '%s'", title)
            if 'id="main-frame-error"' in src or "neterror" in src:
                detail = "Chrome showed an error page (site unreachable)"
            elif EXPECTED_TEXT and EXPECTED_TEXT.lower() not in src:
                detail = f"Page loaded but expected text '{EXPECTED_TEXT}' not found"
            else:
                return True, f"Website loaded, title='{title}'"
            log.warning("  %s", detail)
        except Exception as e:
            detail = f"Chrome/Selenium error: {str(e).splitlines()[0]}"
            log.error("  %s", detail)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        if attempt < WEBSITE_ATTEMPTS:
            log.info("  retrying website in %ds ...", RETRY_GAP_SECONDS)
            time.sleep(RETRY_GAP_SECONDS)
    return False, detail


# -------------------------------- MAIN --------------------------------------
def append_csv(row):
    new = not MASTER_CSV.exists()
    with open(MASTER_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new:
            w.writeheader()
        w.writerow(row)


def main():
    start = datetime.now()
    day_dir = REPORTS_DIR / start.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    tag = start.strftime("%H-%M-%S")
    log_file = day_dir / f"log_{tag}.txt"
    shot_path = day_dir / f"screenshot_{tag}.png"
    log = setup_logger(log_file)

    log.info("=" * 70)
    log.info("RPi HEALTH CHECK STARTED  (RPi=%s, URL=%s)", RPI_IP, WEBSITE_URL)
    log.info("=" * 70)

    r = {"T1": "NOT RUN", "T2": "NOT RUN", "T3": "NOT RUN"}
    details = []
    try:
        ok1, d1 = test1_power(log)
        r["T1"] = "PASS" if ok1 else "FAIL"
        details.append(f"T1: {d1}")
        log.info("TEST 1 RESULT: %s - %s", r["T1"], d1)

        if not ok1:
            r["T2"] = r["T3"] = "FAIL-BLOCKED"
            root = "POWER OFF / RPi NOT REACHABLE"
        else:
            ok2, d2, ssh_problem = test2_internet(log)
            r["T2"] = "PASS" if ok2 else "FAIL"
            details.append(f"T2: {d2}")
            log.info("TEST 2 RESULT: %s - %s", r["T2"], d2)

            if not ok2:
                r["T3"] = "FAIL-BLOCKED"
                root = "RPi SSH ERROR (RPi on, cannot log in)" if ssh_problem else "INTERNET DOWN"
            else:
                ok3, d3 = test3_website(log, shot_path)
                r["T3"] = "PASS" if ok3 else "FAIL"
                details.append(f"T3: {d3}")
                log.info("TEST 3 RESULT: %s - %s", r["T3"], d3)
                root = "ALL OK" if ok3 else "WEBSITE NOT LOADING"
    except Exception as e:                       # script must never die silently
        log.exception("SCRIPT ERROR: %s", e)
        root = "SCRIPT ERROR"
        details.append(f"ERROR: {e}")

    end = datetime.now()
    overall = "PASS" if all(v == "PASS" for v in r.values()) else "FAIL"
    if r["T2"] == "FAIL-BLOCKED":
        log.info("TEST 2 RESULT: FAIL-BLOCKED (because Test 1 failed)")
    if r["T3"] == "FAIL-BLOCKED":
        log.info("TEST 3 RESULT: FAIL-BLOCKED (because an earlier test failed)")

    summary = (
        f"Date       : {start:%Y-%m-%d}\n"
        f"Start/End  : {start:%H:%M:%S} -> {end:%H:%M:%S} ({(end - start).seconds}s)\n"
        f"Test 1 Power    : {r['T1']}\n"
        f"Test 2 Internet : {r['T2']}\n"
        f"Test 3 Website  : {r['T3']}\n"
        f"OVERALL    : {overall}\n"
        f"ROOT CAUSE : {root}\n"
        f"Details    : {' | '.join(details)}\n"
    )
    (day_dir / f"summary_{tag}.txt").write_text(summary, encoding="utf-8")

    append_csv({
        "date": f"{start:%Y-%m-%d}", "start_time": f"{start:%H:%M:%S}",
        "end_time": f"{end:%H:%M:%S}", "duration_sec": (end - start).seconds,
        "test1_power": r["T1"], "test2_internet": r["T2"], "test3_website": r["T3"],
        "overall": overall, "root_cause": root, "details": " | ".join(details),
        "screenshot": str(shot_path) if shot_path.exists() else "",
        "log_file": str(log_file),
    })

    log.info("-" * 70)
    for line in summary.strip().splitlines():
        log.info(line)
    log.info("=" * 70)
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
