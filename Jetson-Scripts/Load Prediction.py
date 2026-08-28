import time
import sqlite3
import os
import warnings
import json
from contextlib import closing

import pandas as pd
import numpy as np
import joblib
import paho.mqtt.client as mqtt

# ---> IMPORT THE EMS CONTROLLER <---
from ems_realtime_jetson import EMSController

warnings.filterwarnings("ignore")

# ==========================================
# CONFIGURATION
# ==========================================
# Database & Model
DB_PATH = "/home/ece493/Desktop/ECE 493 PROJECT/BEMS_ProfileService_FINAL_NEW CSV/BEMS_ProfileService/BEMS_ProfileService/profile_cache/profile.db"
MODEL_BUNDLE_PATH = os.path.expanduser("~/Desktop/jetson_hgbr_ramped_bundle.pkl")

# MQTT Settings
PI_MQTT_BROKER_IP = "192.168.8.144" # Make sure this matches your Pi's IP!
PI_MQTT_PORT = 1883
MQTT_TOPIC = "relay___mode/mode_select"

# Safety Caps & Weights
MAX_PREDICTION_WATTS = 8000.0
LAMBDA_FORECAST = 0.5
LAMBDA_ACTUAL = 0.5

# Same lag structure used during training
LAGS = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 96, 192, 672]
NEEDED_ROWS = max(LAGS) + 5

# Poll timing
SLEEP_NO_DB = 2.0
SLEEP_NO_DATA = 1.0
SLEEP_SAME_BUCKET = 0.5
SLEEP_ON_ERROR = 2.0

print("\n==================================================")
print("    STANDALONE AI + EMS MASTER CONTROLLER         ")
print("==================================================")
print("Relay switching is NATIVE via MQTT (BRUTE-FORCE PUBLISH).")
print("==================================================")

if abs((LAMBDA_FORECAST + LAMBDA_ACTUAL) - 1.0) > 1e-6:
    print("[!] WARNING: LAMBDA_FORECAST and LAMBDA_ACTUAL do not sum to 1.0!")

# ==========================================
# LOAD MODEL BUNDLE
# ==========================================
if not os.path.exists(DB_PATH):
    print(f"\n[!] ERROR: Cannot find database at {DB_PATH}")
    raise SystemExit(1)

if not os.path.exists(MODEL_BUNDLE_PATH):
    print(f"\n[!] ERROR: Cannot find model bundle at {MODEL_BUNDLE_PATH}")
    raise SystemExit(1)

try:
    bundle = joblib.load(MODEL_BUNDLE_PATH)
    model = bundle["model"]
    feature_cols = bundle["feature_cols"]
    ema_alpha = float(bundle.get("ema_alpha_features", 0.0))
    print("-> AI Model loaded successfully.")
except Exception as e:
    print(f"\n[!] ERROR: Failed to load model bundle: {e}")
    raise SystemExit(1)


# ==========================================
# ROBUST MQTT SETUP
# ==========================================
mqtt_connected = False

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print(f"\n-> [MQTT] Connected to {PI_MQTT_BROKER_IP} successfully (rc={rc})")
    else:
        print(f"\n[!] MQTT Connection refused with rc={rc}")

def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    print(f"\n[!] MQTT Disconnected (rc={rc}). Will attempt to auto-reconnect...")

print("\n[LIVE] Initializing MQTT Client...")
mqtt_client = mqtt.Client(client_id="jetson")
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)

try:
    mqtt_client.connect(PI_MQTT_BROKER_IP, PI_MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"[!] MQTT Initial Connection Exception: {e}")
    print("-> Continuing offline. Will try to connect in the background.")


# ==========================================
# FEATURE ENGINEERING & DATA PREP
# ==========================================
def build_features(df):
    df = df.copy().sort_values("timestamp").reset_index(drop=True)
    df["watts_raw"] = pd.to_numeric(df["watts"], errors="coerce").astype(float)

    if ema_alpha > 0:
        df["watts_feat"] = df["watts_raw"].ewm(alpha=ema_alpha, adjust=False).mean()
    else:
        df["watts_feat"] = df["watts_raw"]

    y = df["watts_feat"]
    feat = pd.DataFrame(index=df.index)

    for lag in LAGS:
        feat[f"lag_{lag}"] = y.shift(lag)

    feat["roll_mean_4"] = y.shift(1).rolling(4).mean()
    feat["roll_mean_16"] = y.shift(1).rolling(16).mean()
    feat["roll_mean_96"] = y.shift(1).rolling(96).mean()
    feat["roll_std_16"] = y.shift(1).rolling(16).std()

    feat["ramp_1"] = y.shift(1) - y.shift(2)
    feat["ramp_4"] = y.shift(1) - y.shift(5)

    dt = pd.to_datetime(df["timestamp"], errors="coerce").dt
    feat["hour"] = dt.hour
    feat["minute"] = dt.minute
    feat["dayofweek"] = dt.dayofweek
    feat["month"] = dt.month
    feat["is_weekend"] = (feat["dayofweek"] >= 5).astype(int)

    feat["hour_sin"] = np.sin(2 * np.pi * feat["hour"] / 24.0)
    feat["hour_cos"] = np.cos(2 * np.pi * feat["hour"] / 24.0)
    feat["dow_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7.0)
    feat["dow_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7.0)

    return feat

def to_15min_series(meas):
    meas = meas.copy()
    meas["timestamp"] = pd.to_datetime(meas["timestamp"], errors="coerce")
    meas["watts"] = pd.to_numeric(meas["watts"], errors="coerce")
    meas = meas.dropna(subset=["timestamp", "watts"]).sort_values("timestamp")

    if meas.empty:
        return pd.DataFrame(columns=["timestamp", "watts"])

    meas["bucket"] = meas["timestamp"].dt.floor("15min")
    series = meas.groupby("bucket", as_index=False)["watts"].mean()
    series = series.rename(columns={"bucket": "timestamp"})
    return series.sort_values("timestamp").reset_index(drop=True)

def get_latest_completed_buckets(series15):
    if series15.empty:
        return series15.copy()
    latest_active_bucket = series15["timestamp"].max()
    completed = series15[series15["timestamp"] < latest_active_bucket].copy()
    return completed.sort_values("timestamp").reset_index(drop=True)


# ==========================================
# MAIN LOOP INITIALIZATION
# ==========================================
print("\n[LIVE] Starting EMS Controller...")
ems = EMSController(dtHours=0.25)

print("[LIVE] Watching profile.db for incoming sensor data...")

last_seen_bucket_ts = None
previous_prediction = None
previous_prediction_ts = None
last_heartbeat_time = 0.0

while True:
    try:
        if not os.path.exists(DB_PATH):
            time.sleep(SLEEP_NO_DB)
            continue

        with closing(sqlite3.connect(DB_PATH, check_same_thread=False)) as conn:
            query = """
                SELECT real_ts AS timestamp, watts
                FROM measurements
                WHERE real_ts >= datetime((SELECT MAX(real_ts) FROM measurements), '-8 days')
                ORDER BY real_ts ASC
            """
            meas = pd.read_sql(query, conn)

        if meas.empty:
            time.sleep(SLEEP_NO_DATA)
            continue

        if not {"timestamp", "watts"}.issubset(meas.columns):
            print("Database query missing required columns.")
            time.sleep(SLEEP_ON_ERROR)
            continue

        series15 = to_15min_series(meas)
        completed = get_latest_completed_buckets(series15)

        if len(completed) < NEEDED_ROWS:
            print(f"Waiting for history... Need {NEEDED_ROWS} 15-min buckets, have {len(completed)}.", end="\r")
            time.sleep(SLEEP_NO_DATA)
            continue

        ts_now = pd.Timestamp(completed["timestamp"].iloc[-1])

        # --- THROTTLED HEARTBEAT TICKER ---
        if last_seen_bucket_ts is not None and ts_now == last_seen_bucket_ts:
            current_time = time.time()
            if current_time - last_heartbeat_time > 5.0:  
                print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] AI is actively waiting for the current 15-min bucket to close...", end="\r")
                last_heartbeat_time = current_time
            time.sleep(SLEEP_SAME_BUCKET)
            continue
        # ----------------------------------

        last_seen_bucket_ts = ts_now
        actual_load = float(completed["watts"].iloc[-1])

        completed_start = ts_now
        completed_end = ts_now + pd.Timedelta(minutes=15)
        next_bucket_ts = completed_end
        next_bucket_end = next_bucket_ts + pd.Timedelta(minutes=15)

        print(" " * 80, end="\r")
        print(f"\n--- Latest completed bucket: {completed_start.strftime('%Y-%m-%d')} [{completed_start.strftime('%H:%M')} - {completed_end.strftime('%H:%M')}] ---")

        # --- UPDATED ACCURACY CHECK ---
        if previous_prediction is not None and previous_prediction_ts == ts_now:
            diff = actual_load - previous_prediction
            abs_err = abs(diff)
            pct_err = (abs_err / abs(actual_load) * 100.0) if abs(actual_load) > 1e-6 else 0.0
            
            print(f"[ACCURACY CHECK] Predicted: {previous_prediction:.2f} W | Actual: {actual_load:.2f} W")
            print(f"                 Error: {diff:+.2f} W | Abs Error: {abs_err:.2f} W ({pct_err:.1f}%)")
        else:
            print(f"Current Actual Load: {actual_load:.2f} W")

        # --- RUN ML PREDICTION ---
        feat = build_features(completed)
        latest = feat.iloc[[-1]].copy()

        for col in feature_cols:
            if col not in latest.columns:
                latest[col] = 0.0

        latest = latest[feature_cols].astype("float32")

        if latest.isnull().values.any():
            print("Feature row contains NaN values. Waiting for more clean history...")
            time.sleep(SLEEP_NO_DATA)
            continue

        forecast_load = float(model.predict(latest)[0])
        forecast_load = max(0.0, min(forecast_load, MAX_PREDICTION_WATTS))
        forecast_load = round(forecast_load, 2)

        previous_prediction = forecast_load
        previous_prediction_ts = next_bucket_ts

        print(f"-> AI FORECAST for window [{next_bucket_ts.strftime('%H:%M')} - {next_bucket_end.strftime('%H:%M')}]: {forecast_load:.2f} W")

        # --- PROFESSOR'S 50/50 LAMBDA LOGIC ---
        effective_load_W = (LAMBDA_FORECAST * forecast_load) + (LAMBDA_ACTUAL * actual_load)
        print(f"-> Effective Blended Load: {effective_load_W:.2f} W")

        # ==========================================
        # EMS PHYSICAL DECISION ENGINE
        # ==========================================
        ems_command = ems.step(
            now=next_bucket_ts,
            load_kW=(effective_load_W / 1000.0),
            grid_ok=1,
            soc_kWh_meas=None
        )

        raw_ems_mode = ems_command['mode']
        
        # --- EXPLICIT MODE TRANSLATION FOR PI RECEIVER ---
        if raw_ems_mode == "DISCHARGE":
            mode_numeric = 1
            pi_mode_text = "BATTERY"
        elif raw_ems_mode in ["GRID", "CHARGE"]:
            mode_numeric = 2
            pi_mode_text = "GRID"
        else:
            mode_numeric = 0
            pi_mode_text = "AUTO"

        print(f"-> TOU Rate: {ems_command['tou_period']} (${ems_command['price']:.4f}/kWh) | Reason: {ems_command['reason']}")
        print(f"[DECISION ENGINE] AI chose >>> {raw_ems_mode} <<< (Mapped to Pi: '{pi_mode_text}')")
        # print(f"[BATTERY STATE] Target Pbatt: {ems_command['Pbatt_kW']:+.2f} kW | Estimated SOC: {ems_command['SOC_kWh']:.2f} kWh")

        # ==========================================
        # BRUTE-FORCE MQTT PUBLISH TO RASPBERRY PI
        # ==========================================
        payload = {
            "timestamp": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            "decision_for_bucket": next_bucket_ts.strftime('%Y-%m-%d %H:%M:%S'),
            "source": "jetson_ai_master",
            "mode_text": pi_mode_text,
            "mode": mode_numeric,
            "raw_ems_mode": raw_ems_mode
        }
        
        if mqtt_connected:
            # WE NOW PUBLISH EVERY SINGLE TIME
            info = mqtt_client.publish(MQTT_TOPIC, json.dumps(payload), qos=1, retain=True)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"-> [MQTT] Mode '{pi_mode_text}' published to Raspberry Pi successfully.")
            else:
                print(f"-> [!] MQTT publish failed with return code: {info.rc}")
        else:
            print("-> [MQTT] Skipped publish because broker is currently disconnected.")

    except KeyboardInterrupt:
        print("\nStopping Master Controller...")
        mqtt_client.loop_stop()
        try:
            mqtt_client.disconnect()
        except Exception:
            pass
        break

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(SLEEP_ON_ERROR)