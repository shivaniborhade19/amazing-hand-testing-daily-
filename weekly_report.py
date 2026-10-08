"""
Weekly (or N-day) report from C:\\RPi_Monitor\\all_results.csv

Usage:
    python weekly_report.py          -> last 7 days
    python weekly_report.py 30       -> last 30 days

Saves: C:\\RPi_Monitor\\Reports\\Weekly\\report_<from>_to_<to>.txt
"""
import csv
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(r"C:\RPi_Monitor")     # must match rpi_daily_check.py
MASTER_CSV = BASE_DIR / "all_results.csv"
OUT_DIR = BASE_DIR / "Reports" / "Weekly"


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    to_day = date.today()
    from_day = to_day - timedelta(days=days - 1)

    if not MASTER_CSV.exists():
        print(f"No data yet: {MASTER_CSV} not found")
        return 1

    with open(MASTER_CSV, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if from_day <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= to_day]

    total = len(rows)
    passed = sum(r["overall"] == "PASS" for r in rows)
    failed = total - passed
    causes = Counter(r["root_cause"] for r in rows if r["overall"] != "PASS")

    def count(col, val):
        return sum(r[col] == val for r in rows)

    all_dates = [from_day + timedelta(days=i) for i in range(days)]
    dates_with_runs = {r["date"] for r in rows}
    missing = [d for d in all_dates if d.isoformat() not in dates_with_runs]

    L = []
    L.append("=" * 78)
    L.append(f"  RPi HEALTH REPORT   {from_day} to {to_day}   ({days} days)")
    L.append(f"  Generated: {datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append("=" * 78)
    L.append(f"Total runs          : {total}")
    L.append(f"Passed (all 3 OK)   : {passed}")
    L.append(f"Failed              : {failed}")
    if total:
        L.append(f"Availability        : {passed / total * 100:.1f}%")
    L.append("")
    L.append("FAILURES BY ROOT CAUSE")
    L.append("-" * 78)
    if causes:
        for c, n in causes.most_common():
            L.append(f"  {c:<45} {n} time(s)")
    else:
        L.append("  None - everything passed")
    L.append("")
    L.append("PER TEST")
    L.append("-" * 78)
    L.append(f"  Test 1 Power    : FAIL {count('test1_power', 'FAIL')}")
    L.append(f"  Test 2 Internet : FAIL {count('test2_internet', 'FAIL')}"
             f"   (+{count('test2_internet', 'FAIL-BLOCKED')} blocked by Test 1)")
    L.append(f"  Test 3 Website  : FAIL {count('test3_website', 'FAIL')}"
             f"   (+{count('test3_website', 'FAIL-BLOCKED')} blocked by Test 1/2)")
    L.append("")
    L.append("DAY BY DAY")
    L.append("-" * 78)
    L.append(f"  {'Date':<11}{'Time':<10}{'Power':<14}{'Internet':<14}{'Website':<14}Root cause")
    for d in all_dates:
        day_rows = [r for r in rows if r["date"] == d.isoformat()]
        if not day_rows:
            L.append(f"  {d.isoformat():<11}{'--':<10}NO RUN (PC was off / task did not run)")
            continue
        for r in day_rows:
            L.append(f"  {r['date']:<11}{r['start_time']:<10}{r['test1_power']:<14}"
                     f"{r['test2_internet']:<14}{r['test3_website']:<14}{r['root_cause']}")
    if missing:
        L.append("")
        L.append(f"NOTE: {len(missing)} day(s) with no run: {', '.join(d.isoformat() for d in missing)}")
        L.append("      If the PC shares power with the RPi, this usually means a power cut.")
    L.append("")
    L.append("FAILURE DETAILS")
    L.append("-" * 78)
    fails = [r for r in rows if r["overall"] != "PASS"]
    for r in fails:
        L.append(f"  {r['date']} {r['start_time']}  {r['details']}")
        L.append(f"      log: {r['log_file']}")
    if not fails:
        L.append("  None")
    L.append("=" * 78)

    text = "\n".join(L)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"report_{from_day}_to_{to_day}.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
