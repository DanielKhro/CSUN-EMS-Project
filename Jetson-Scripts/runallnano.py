
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent

# These scripts finish and must succeed before startup continues.
ONE_TIME_SCRIPTS = [
    "ems_realtime_jetson.py",
    "inject_history.py",
]

# These scripts intentionally run forever. They are started in this order and
# then supervised together.
CONTINUOUS_SCRIPTS = [
    "jetson_energy_receiver.py",
    "Load Prediction.py",
]

STARTUP_DELAY_SECONDS = 2


def stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    """Stop all continuous scripts cleanly, in reverse startup order."""
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
    scripts = ONE_TIME_SCRIPTS + CONTINUOUS_SCRIPTS
    missing = [name for name in scripts if not (PROJECT_DIR / name).is_file()]

    if missing:
        print("Missing required script(s):")
        for name in missing:
            print(f"  - {PROJECT_DIR / name}")
        print("The filenames must match exactly, including spaces and capitals.")
        return 1

    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        for name in ONE_TIME_SCRIPTS:
            print(f"Running {name}...")
            result = subprocess.run(
                [sys.executable, "-u", str(PROJECT_DIR / name)],
                cwd=PROJECT_DIR,
            )
            if result.returncode != 0:
                print(f"{name} failed with code {result.returncode}. Stopping.")
                return result.returncode
            print(f"{name} finished successfully.")

        for name in CONTINUOUS_SCRIPTS:
            print(f"Starting {name}...")
            process = subprocess.Popen(
                [sys.executable, "-u", str(PROJECT_DIR / name)],
                cwd=PROJECT_DIR,
            )
            processes.append((name, process))

            time.sleep(STARTUP_DELAY_SECONDS)
            return_code = process.poll()
            if return_code is not None:
                print(f"{name} failed during startup with code {return_code}.")
                return return_code or 1
            print(f"{name} is running.")

        print("All Jetson programs started in the requested order.")
        print("Press Ctrl+C to stop the receiver and load-prediction services.")

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    print(f"{name} stopped unexpectedly with code {return_code}.")
                    return return_code or 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutdown requested.")
        return 0
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
