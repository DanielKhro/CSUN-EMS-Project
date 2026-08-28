import sqlite3
import pandas as pd
import numpy as np
import os

# ==========================================
# CONFIGURATION
# ==========================================
DB_PATH = "/home/ece493/Desktop/ECE 493 PROJECT/BEMS_ProfileService_FINAL_NEW CSV/BEMS_ProfileService/BEMS_ProfileService/profile_cache/profile.db"
CSV_PATH = "lowload_2015_2025_ramped.csv"
ROWS_TO_INJECT = 800  # ~8 days of 15-minute data

def generate_smart_history():
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: Could not find {CSV_PATH}")
        return

    print("1. Reading your 10-year CSV to learn your load habits...")
    df = pd.read_csv(CSV_PATH)
    
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time", "Load_Watts"])
    df["time_of_day"] = df["Time"].dt.strftime("%H:%M")
    
    print("2. Calculating the Mean and Standard Deviation for every 15-min bucket...")
    profile_stats = df.groupby("time_of_day")["Load_Watts"].agg(["mean", "std"]).fillna(0)
    
    now_la = pd.Timestamp.now(tz='America/Los_Angeles').tz_localize(None).floor("15min")
    timestamps = pd.date_range(end=now_la, periods=ROWS_TO_INJECT, freq="15min")
    
    print(f"3. Connecting to database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # --- FOOLPROOF SCHEMA CHECK ---
    cursor.execute("PRAGMA table_info(measurements)")
    columns_info = cursor.fetchall()
    actual_columns = [info[1] for info in columns_info]
    print(f"-> Database expects these columns: {actual_columns}")
    
    cursor.execute("DELETE FROM measurements")
    
    print(f"4. Generating {ROWS_TO_INJECT} rows of statistically accurate synthetic data...")
    inserted_count = 0
    
    for ts in timestamps:
        time_str = ts.strftime("%H:%M")
        
        if time_str in profile_stats.index:
            bucket_mean = profile_stats.loc[time_str, "mean"]
            bucket_std = profile_stats.loc[time_str, "std"]
        else:
            bucket_mean, bucket_std = 30.0, 5.0
            
        synthetic_watts = max(0.0, np.random.normal(loc=bucket_mean, scale=bucket_std))
        
        # We now include the exact columns your database asked for, including 'slot'
        row_data = {
            "real_ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "watts": float(synthetic_watts),
            "method": "smart_synthetic",
            "month": ts.month,
            "day": ts.day,
            "weekday": ts.dayofweek,
            "slot": (ts.hour * 4) + (ts.minute // 15),
            "hour": ts.hour,
            "minute": ts.minute,
            "year": ts.year
        }
        
        insert_cols = []
        insert_vals = []
        for col in actual_columns:
            if col in row_data:
                insert_cols.append(col)
                insert_vals.append(row_data[col])
                
        placeholders = ", ".join(["?"] * len(insert_cols))
        col_str = ", ".join(insert_cols)
        query = f"INSERT INTO measurements ({col_str}) VALUES ({placeholders})"
        
        cursor.execute(query, tuple(insert_vals))
        inserted_count += 1

    conn.commit()
    conn.close()
    
    print(f"SUCCESS! Injected {inserted_count} rows of smart synthetic data.")
    print(f"The simulated history ends seamlessly at: {now_la.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    generate_smart_history()