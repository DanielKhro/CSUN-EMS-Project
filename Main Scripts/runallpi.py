from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOG_DIR = PROJECT_DIR / "logs"

# These programs are continuous services. They are started in this order but
# run together; run_all.py does not wait for one to finish before starting the
# next one.
SERVICES = [
    "pylontech.py",
    "pzem _2_name.py",
    "main_script_spring25.py",
]

STARTUP_DELAY_SECONDS = 2
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883


def mqtt_is_available() -> bool:
    """Return True when the local MQTT broker accepts connections."""
    try:
        with socket.create_connection((MQTT_HOST, MQTT_PORT), timeout=2):
            return True
    except OSError:
        return False


def stop_services(processes: list[tuple[str, subprocess.Popen]]) -> None:
    """Stop every service, giving each process time to exit cleanly."""
    for name, process in reversed(processes):
        if process.poll() is None:
            print(f"Stopping {name}...")
            process.terminate()

    for name, process in reversed(processes):
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"{name} did not stop; forcing it to close.")
            process.kill()
            process.wait()


def main() -> int:
    missing = [name for name in SERVICES if not (PROJECT_DIR / name).is_file()]
    if missing:
        print("Missing required script(s):")
        for name in missing:
            print(f"  - {PROJECT_DIR / name}")
        return 1

    if not mqtt_is_available():
        print(
            f"MQTT broker is not available at {MQTT_HOST}:{MQTT_PORT}.\n"
            "Start Mosquitto before running this launcher."
        )
        return 1

    LOG_DIR.mkdir(exist_ok=True)
    processes: list[tuple[str, subprocess.Popen]] = []
    log_files = []

    try:
        for name in SERVICES:
            script_path = PROJECT_DIR / name
            log_path = LOG_DIR / f"{script_path.stem}.log"
            log_file = log_path.open("a", encoding="utf-8", buffering=1)
            log_files.append(log_file)

            print(f"Starting {name}...")
            process = subprocess.Popen(
                [sys.executable, "-u", str(script_path)],
                cwd=PROJECT_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            processes.append((name, process))

            time.sleep(STARTUP_DELAY_SECONDS)
            return_code = process.poll()
            if return_code is not None:
                print(
                    f"{name} failed during startup with code {return_code}.\n"
                    f"Read the error in: {log_path}"
                )
                return 1

            print(f"{name} is running. Log: {log_path}")

        print("All energy-management services are running.")
        print("Press Ctrl+C to stop all services safely.")

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    print(f"{name} stopped unexpectedly with code {return_code}.")
                    return 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutdown requested.")
        return 0
    finally:
        stop_services(processes)
        for log_file in log_files:
            log_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
