#!/usr/bin/env python3


from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None  # type: ignore


# ---------------------------
# Timestamp + column detection
# ---------------------------

TS_FORMATS = (
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
)


def parse_ts(s: str, tz_name: Optional[str]) -> datetime:
    s = (s or "").strip()
    for fmt in TS_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if tz_name and ZoneInfo is not None:
                try:
                    return dt.replace(tzinfo=ZoneInfo(tz_name))
                except Exception:
                    # If timezone not found, just return naive datetime
                    return dt
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unrecognized timestamp: {s!r}")


def detect_cols(fieldnames: List[str]) -> Tuple[str, Optional[str], str]:
    """
    Returns (timestamp_col, units_col_or_None, value_col)

    - timestamp: prefers 'timestamp' then any column containing 'time'
    - units: optional per-row scaling column (e.g., units_wh) applied as watts/units
    - value_col: prefer columns indicating watts/power then fallbacks
    """
    lower = [c.lower() for c in fieldnames]

    # timestamp
    ts_col = None
    for c, lc in zip(fieldnames, lower):
        if lc == "timestamp" or "timestamp" in lc:
            ts_col = c
            break
    if ts_col is None:
        for c, lc in zip(fieldnames, lower):
            if "time" in lc:
                ts_col = c
                break
    if ts_col is None:
        raise ValueError(f"No timestamp column found. Columns={fieldnames}")

    # units optional (e.g., units_wh or units)
    units_col = None
    for c, lc in zip(fieldnames, lower):
        if lc == "units_wh" or ("units" in lc and "wh" in lc) or lc == "units":
            units_col = c
            break

    # value column: prefer watt/power indicators
    value_col = None

    # 1) explicit watt/power names
    for c, lc in zip(fieldnames, lower):
        if "watt" in lc or "watts" in lc or "power" in lc or lc.endswith("_w"):
            # avoid reactive/var/voltage/current
            if any(x in lc for x in ("reactive", "var", "voltage", "current")):
                continue
            value_col = c
            break

    # 2) fallback: avoid reactive/var, prefer anything numeric
    if value_col is None:
        for c, lc in zip(fieldnames, lower):
            if any(x in lc for x in ("reactive", "var")):
                continue
            if any(x in lc for x in ("voltage", "current")):
                continue
            if "total" in lc and "kwh" in lc:
                # not ideal, but last resort
                value_col = c
                break

    # 3) final fallback: last column
    if value_col is None:
        value_col = fieldnames[-1]

    return ts_col, units_col, value_col


# ---------------------------
# 15-min slot math
# ---------------------------


def slot_index(dt: datetime, dt_minutes: int) -> int:
    """Return 0..(slots_per_day-1) for a dt_minutes profile."""
    return (dt.hour * 60 + dt.minute) // dt_minutes


def floor_to_boundary(dt: datetime, dt_minutes: int) -> datetime:
    """Floor a datetime to the start of its interval boundary."""
    minute = (dt.minute // dt_minutes) * dt_minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def seconds_until_next_boundary(dt: datetime, dt_minutes: int) -> float:
    """Seconds until the next interval boundary."""
    floored = floor_to_boundary(dt, dt_minutes)
    nxt = floored + timedelta(minutes=dt_minutes)
    return max(0.0, (nxt - dt).total_seconds())


# ---------------------------
# SQLite schema (watts-native)
# ---------------------------

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Baseline: full-year profile (template year) at interval resolution
CREATE TABLE IF NOT EXISTS baseline_year (
  ts TEXT PRIMARY KEY,
  month INTEGER NOT NULL,
  day INTEGER NOT NULL,
  weekday INTEGER NOT NULL,
  slot INTEGER NOT NULL,
  baseline_watts REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_base_mdslot ON baseline_year(month, day, slot);
CREATE INDEX IF NOT EXISTS idx_base_wdslot ON baseline_year(weekday, slot);

-- Refined: updated using live PZEM measurements (EMA or overwrite)
CREATE TABLE IF NOT EXISTS refined_year (
  month INTEGER NOT NULL,
  day INTEGER NOT NULL,
  slot INTEGER NOT NULL,
  refined_watts REAL NOT NULL,
  n_updates INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (month, day, slot)
);

-- Measurements log (for ML training/debug)
CREATE TABLE IF NOT EXISTS measurements (
  real_ts TEXT PRIMARY KEY,
  month INTEGER NOT NULL,
  day INTEGER NOT NULL,
  weekday INTEGER NOT NULL,
  slot INTEGER NOT NULL,
  watts REAL NOT NULL,
  method TEXT NOT NULL
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    need_create = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)

    # If DB exists, check for existing schema_version
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('baseline_year','refined_year','measurements')"
    )
    exists = cur.fetchone() is not None

    # If tables exist, check schema_version
    if exists:
        try:
            cur.execute("SELECT value FROM meta WHERE key='schema_version'")
            row = cur.fetchone()
            if not row or row[0] != "2":
                raise RuntimeError(
                    "Database schema version is incompatible. Please delete the DB file '"
                    + os.path.abspath(db_path)
                    + "' and re-run with --init to recreate it (schema_version=2)."
                )
        except sqlite3.OperationalError:
            # meta table missing or inaccessible
            raise RuntimeError(
                "Database appears to be an older schema. Please delete the DB file '"
                + os.path.abspath(db_path)
                + "' and re-run with --init to recreate it (schema_version=2)."
            )
    else:
        # Fresh DB: create schema and set schema_version
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        cur.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            ("schema_version", "2"),
        )
        conn.commit()

    return conn


def meta_get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def already_loaded(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(1) FROM baseline_year").fetchone()
    return bool(row and row[0] > 0)


# ---------------------------
# Import (one-time)
# ---------------------------


def import_csv_once(csv_path: str, db_path: str, tz_name: str) -> Tuple[int, int]:
    """
    Import baseline profile (watts per interval) and seed refined profile.

    Returns: (dt_minutes, target_year)
    """
    conn = init_db(db_path)

    # If already loaded, just report success
    if already_loaded(conn):
        dt_minutes = int(meta_get(conn, "dt_minutes") or "15")
        target_year = int(meta_get(conn, "target_year") or "0")
        conn.close()
        print("Load profile loaded correctly")
        return dt_minutes, target_year

    # Read header and infer dt_minutes from first two valid timestamp rows
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV missing header row.")

        ts_col, units_col, value_col = detect_cols(reader.fieldnames)

        # find first two timestamp rows
        t_vals: List[datetime] = []
        for row in reader:
            try:
                t = parse_ts(row[ts_col], tz_name)
                t_vals.append(t)
                if len(t_vals) >= 2:
                    break
            except Exception:
                continue
        if len(t_vals) < 2:
            dt_minutes = 15
        else:
            t1, t2 = t_vals[0], t_vals[1]
            dt_minutes = int(round((t2 - t1).total_seconds() / 60.0))
            if dt_minutes <= 0:
                dt_minutes = 15

    # Determine dominant year
    year_counts: Dict[int, int] = {}
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        ts_col, units_col, value_col = detect_cols(reader.fieldnames or [])
        for row in reader:
            try:
                t = parse_ts(row[ts_col], tz_name)
                year_counts[t.year] = year_counts.get(t.year, 0) + 1
            except Exception:
                continue
    if not year_counts:
        raise ValueError("Could not parse any timestamps.")
    target_year = max(year_counts.items(), key=lambda kv: kv[1])[0]

    # Import only that year
    batch: List[Tuple[str, int, int, int, int, float]] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        ts_col, units_col, value_col = detect_cols(fieldnames)
        
        print(f"\nDEBUG: Column detection:")
        print(f"  Timestamp col: {ts_col}")
        print(f"  Value col: {value_col}")
        print(f"  Units col: {units_col}")
        print(f"  Target year: {target_year}\n")

        sample_count = 0
        
        for row in reader:
            try:
                t = parse_ts(row[ts_col], tz_name)
            except Exception:
                continue

            if t.year != target_year:
                continue

            # Get the watt value directly from the detected value column
            try:
                watts = float(row[value_col]) if value_col in fieldnames and row.get(value_col) else None
            except Exception:
                watts = None

            if watts is None or watts <= 0:
                continue

            # Normalize timestamp to the start of the interval boundary
            t_use = floor_to_boundary(t, dt_minutes)
            month, day, weekday = t_use.month, t_use.day, t_use.weekday()
            slot = slot_index(t_use, dt_minutes)

            batch.append((t_use.isoformat(sep=" "), month, day, weekday, slot, float(watts)))
            
            # Print first 5 samples for debugging
            sample_count += 1
            if sample_count <= 5:
                print(f"DEBUG: Sample {sample_count}: ts={t_use.isoformat(sep=' ')}, watts={watts:.2f}W, slot={slot}")

            if len(batch) >= 2000:
                conn.executemany(
                    "INSERT OR REPLACE INTO baseline_year(ts,month,day,weekday,slot,baseline_watts) "
                    "VALUES(?,?,?,?,?,?)",
                    batch,
                )
                batch.clear()

        if batch:
            conn.executemany(
                "INSERT OR REPLACE INTO baseline_year(ts,month,day,weekday,slot,baseline_watts) "
                "VALUES(?,?,?,?,?,?)",
                batch,
            )
            batch.clear()
        
        print(f"\nDEBUG: Imported {sample_count} intervals total\n")

    # Seed refined_year from baseline (start refined == baseline)
    conn.execute("DELETE FROM refined_year;")
    now_iso = datetime.now().isoformat(sep=" ")
    conn.execute(
        "INSERT INTO refined_year(month,day,slot,refined_watts,n_updates,updated_at) "
        "SELECT month, day, slot, baseline_watts, 0, ? FROM baseline_year",
        (now_iso,),
    )

    meta_set(conn, "dt_minutes", str(dt_minutes))
    meta_set(conn, "target_year", str(target_year))
    meta_set(conn, "timestamp_col", ts_col)
    meta_set(conn, "value_col", value_col)
    if units_col:
        meta_set(conn, "units_col", units_col)
    meta_set(conn, "units_col", units_col or "")
    meta_set(conn, "value_col", value_col)
    meta_set(conn, "csv_path", os.path.abspath(csv_path))

    conn.commit()
    
    # Verify data was inserted
    count = conn.execute("SELECT COUNT(*) FROM baseline_year").fetchone()[0]
    avg_watts = conn.execute("SELECT AVG(baseline_watts) FROM baseline_year").fetchone()[0]
    max_watts = conn.execute("SELECT MAX(baseline_watts) FROM baseline_year").fetchone()[0]
    print(f"\nVerification: {count} rows inserted")
    print(f"Average baseline watts: {avg_watts:.2f}W")
    print(f"Max baseline watts: {max_watts:.2f}W\n")
    
    conn.close()

    print("Load profile loaded correctly")
    return dt_minutes, target_year


# ---------------------------
# Live watts source
# ---------------------------


def read_watts(source: str) -> Optional[float]:
    """
    Read live watts from:
    - file:/tmp/current_watts.txt  (recommended)
    - stdin
    - constant:1500
    """
    source = (source or "").strip()

    if source.startswith("constant:"):
        return float(source.split(":", 1)[1])

    if source == "stdin":
        s = input("Enter watts (blank skip): ").strip()
        if not s:
            return None
        return float(s)

    if source.startswith("file:"):
        path = source.split(":", 1)[1].strip()
        try:
            # If a relative path is provided, resolve it relative to the script
            if not os.path.isabs(path):
                base_dir = os.path.dirname(os.path.abspath(__file__))
                path = os.path.join(base_dir, path)

            with open(path, "r") as f:
                s = f.read().strip()
            if not s:
                print(f"read_watts: file '{path}' is empty")
                return None
            return float(s)
        except Exception:
            print(f"read_watts: failed to read/parse file '{path}'")
            return None

    # Unknown source
    return None


def update_slot_refined(
    conn: sqlite3.Connection,
    month: int,
    day: int,
    slot: int,
    new_watts: float,
    method: str,
):
    now_iso = datetime.now().isoformat(sep=" ")

    row = conn.execute(
        "SELECT refined_watts, n_updates FROM refined_year WHERE month=? AND day=? AND slot=?",
        (month, day, slot),
    ).fetchone()

    if row is None:
        # If missing, insert it
        conn.execute(
            "INSERT OR REPLACE INTO refined_year(month,day,slot,refined_watts,n_updates,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (month, day, slot, float(new_watts), 1, now_iso),
        )
        return

    _, n = float(row[0]), int(row[1])
    conn.execute(
        "UPDATE refined_year SET refined_watts=?, n_updates=?, updated_at=? "
        "WHERE month=? AND day=? AND slot=?",
        (float(new_watts), n + 1, now_iso, month, day, slot),
    )


def run_live(
    db_path: str,
    tz_name: str,
    watts_source: str,
    alpha: float,
    overwrite: bool,
    once: bool,
) -> None:
    conn = init_db(db_path)

    dt_minutes = int(meta_get(conn, "dt_minutes") or "15")

    tz = None
    if tz_name and ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None

    # clamp alpha
    try:
        alpha = float(alpha)
    except Exception:
        alpha = 0.2
    alpha = max(0.0, min(1.0, alpha))

    last_watts = None  # Cache last successfully read watts value

    def one_step() -> None:
        nonlocal last_watts

        now = datetime.now(tz=tz) if tz else datetime.now()
        now_slot = floor_to_boundary(now, dt_minutes)

        # Get baseline using the SAME MONTH/DAY from the template year (stored in baseline_year table)
        # This handles when current year differs from template year
        month, day, weekday = now_slot.month, now_slot.day, now_slot.weekday()
        slot = slot_index(now_slot, dt_minutes)

        # Baseline lookup
        base_row = conn.execute(
            "SELECT baseline_watts FROM baseline_year WHERE month=? AND day=? AND slot=?",
            (month, day, slot),
        ).fetchone()
        base_watts = float(base_row[0]) if base_row else 0.0
        
        # Debug: if baseline is 0, check if month/day combination exists at all
        if base_watts == 0.0:
            debug_row = conn.execute(
                "SELECT COUNT(*) FROM baseline_year WHERE month=? AND day=?",
                (month, day),
            ).fetchone()
            if debug_row and debug_row[0] == 0:
                print(f"DEBUG: No baseline data found for month={month}, day={day} (slot={slot})")
            else:
                print(f"DEBUG: Baseline exists for month={month}, day={day}, but slot={slot} returned 0")

        ref_row = conn.execute(
            "SELECT refined_watts, n_updates FROM refined_year WHERE month=? AND day=? AND slot=?",
            (month, day, slot),
        ).fetchone()
        ref_watts = float(ref_row[0]) if ref_row else base_watts
        n_updates = int(ref_row[1]) if ref_row else 0

        watts = read_watts(watts_source)
        if watts is None:
            if last_watts is not None:
                print(f"No watts from source; using cached value: {last_watts} W")
                watts = last_watts
            else:
                # Print baseline/refined information even when no live watts
                ts_str = now_slot.strftime("%Y-%m-%d %H:%M:%S")
                date_str = now_slot.strftime("%m-%d")
                id_str = f"(M={month}, D={day}, slot={slot:02d})"

                print(
                    f"\n"
                    f"ID: {id_str}\n"
                    f"Date & Time: {date_str} {now_slot.strftime('%H:%M:%S')}\n"
                    f"Measured Watts: N/A\n"
                    f"Baseline Watts: {base_watts:.2f} W\n"
                    f"Refined Watts: {ref_watts:.2f} W\n"
                    f"Updates: {n_updates}\n"
                )
                print("No watts value available from source; skipping update")
                return
        else:
            last_watts = watts  # Cache successful read

        measured_watts = float(watts)

        # Refined now equals measured immediately (no EMA smoothing)
        new_ref = measured_watts
        method = "direct"

        update_slot_refined(conn, month, day, slot, new_ref, method)

        # Log measurement
        conn.execute(
            "INSERT OR REPLACE INTO measurements(real_ts,month,day,weekday,slot,watts,method) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                now_slot.isoformat(sep=" "),
                month,
                day,
                weekday,
                slot,
                float(measured_watts),
                method,
            ),
        )
        conn.commit()

        # Fetch updated values to display after update
        ref_row_updated = conn.execute(
            "SELECT refined_watts, n_updates FROM refined_year WHERE month=? AND day=? AND slot=?",
            (month, day, slot),
        ).fetchone()
        ref_watts_updated = float(ref_row_updated[0]) if ref_row_updated else base_watts
        n_updates_updated = int(ref_row_updated[1]) if ref_row_updated else 0

        ts_str = now_slot.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now_slot.strftime("%m-%d")
        id_str = f"(M={month}, D={day}, slot={slot:02d})"

        print(
            f"\n"
            f"ID: {id_str}\n"
            f"Date & Time: {date_str} {now_slot.strftime('%H:%M:%S')}\n"
            f"Measured Watts: {measured_watts:.2f} W\n"
            f"Baseline Watts: {base_watts:.2f} W\n"
            f"Refined Watts: {ref_watts_updated:.2f} W\n"
            f"Updates: {n_updates_updated}\n"
        )

    if once:
        one_step()
        conn.close()
        return

    # Startup banner removed to avoid verbose output on launch

    while True:
        one_step()
        now2 = datetime.now(tz=tz) if tz else datetime.now()
        time.sleep(seconds_until_next_boundary(now2, dt_minutes) + 0.05)


# ---------------------------
# CLI
# ---------------------------


def main() -> int:
    # Ensure we're in the script's directory so relative paths work
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    ap = argparse.ArgumentParser(description="Load profile importer + live refiner (watts-native).")
    ap.add_argument("--csv", default="singlefamilyhome_loadprofile.csv", help="Path to yearly interval CSV")
    ap.add_argument("--db", default="profile_cache/profile.db", help="SQLite DB path")
    ap.add_argument("--tz", default="", help="Timezone name")

    mode = ap.add_mutually_exclusive_group(required=False)
    mode.add_argument("--init", action="store_true", help="Import CSV once and seed refined profile")
    mode.add_argument("--run", action="store_true", help="Run live refinement loop")

    ap.add_argument("--watts-source", default="file:current_watts.txt",
                    help="file:/path | stdin | constant:1234")
    ap.add_argument("--alpha", type=float, default=0.2, help="EMA alpha (0..1)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite refined slot instead of EMA")
    ap.add_argument("--once", action="store_true", help="Run one update step and exit")


    args = ap.parse_args()

    # Default to run if neither provided
    if not (args.init or args.run):
        args.run = True

    if args.init:
        import_csv_once(args.csv, args.db, args.tz)
        return 0

    if args.run:
        run_live(args.db, args.tz, args.watts_source, args.alpha, args.overwrite, args.once)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
