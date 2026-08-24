import tkinter as tk
import sys
import paho.mqtt.client as mqtt
import json
import board
import busio
import time
from gpiozero import LED, Button
from datetime import datetime
import pandas as pd
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn

import openpyxl

import threading

# Emergency button on Pin 4
EMERGENCY_PIN = 4

emergency_button = Button(EMERGENCY_PIN,pull_up=False,bounce_time=0.1)

last_mode = 0  # Default to Grid Mode

em_mode = 0

# Emergency Mode Function
def emergency_mode():
    global last_mode, em_mode
    print("Grid Power Lost! Switching to Emergency Mode.")
    em_mode = 1

# Restore Power Function
def restore_power():
    global last_mode, em_mode
    # print("Grid Power Restored. Returning to Last Mode.")
    em_mode = 0

button_state = False

def emergency_monitor():
    global button_state
    while True:
        if button_state:
            emergency_mode()
        else:
            restore_power()
        time.sleep(0.1)

def button_pressed():
    global button_state
    button_state = True
    print(f"Button Pressed")

def button_released():
    global button_state
    button_state = False
    print(f"Button Released")

# Configuration
broker = "127.0.0.1"
port = 1883

# Acquire initial current time to be used in relay control parameters
present_time = datetime.now()
present_hour = present_time.hour
present_minute = present_time.minute


def update_time():
    global present_time, present_hour, present_minute
    present_time = datetime.now()
    present_hour = present_time.hour
    present_minute = present_time.minute

volt_grid = 0
curr_grid = 0
pf_load = 0
pw_load = 0
volt_load = 0
curr_load = 0
pw_threshold = 700
pw_grid = 0
pf_grid = 0 # power factor
soc = 50  # Initial SOC value, will be updated from MQTT

# MQTT Callback for message receipt
def on_message(client, userdata, message):
    global soc, pf_grid, pw_grid, volt_grid, curr_grid, pf_load, pw_load, volt_load, curr_load, relay_mode
    update_time()
    payload = message.payload.decode("utf-8")
    data = json.loads(payload)
    soc = data.get("SOC", soc)
    relay_mode = data.get("mode", relay_mode)
    pf_grid = data.get("Grid powerFactor", pf_grid)
    pw_grid = data.get("Grid power", pw_grid)
    volt_grid = data.get("Grid voltage", volt_grid)
    curr_grid = data.get("Grid amperage", curr_grid)
    pf_load = data.get("Load powerFactor", pf_load)
    pw_load = data.get("Load power", pw_load)
    volt_load = data.get("Load voltage", volt_load)
    curr_load = data.get("Load amperage", curr_load)
    print(f"Updated DATA from MQTT: SOC:{soc}%, Grid PF:{pf_grid}, Grid Pw:{pw_grid}W, Load PF:{pf_load}, Load "
          f"Pw:{pw_load}W, Present Minute:{present_minute}, Relay Mode = {relay_mode}")

# MQTT Callback for publish
def on_publish(client, userdata, mid):
    print(f"mqtt published, message id: {mid}")
    pass

# Specify the MQTT version and create the client instance
client = mqtt.Client(client_id="battery_reader")
client.on_publish = on_publish  # Assign the callback for publish
client.on_message = on_message  # Assign the callback for message receipt

client.connect(broker, port)
# topics = [("solar/battery/#",0), ("pzem/#",0)]
topics = [("solar/battery/#",0), ("pzem/#",0), ("relay___mode/mode_select",0), ("emergency/#",0)]
client.subscribe(topics)
client.loop_start()  # Start the MQTT loop

# GPIO setup for relays using gpiozero
relay1 = LED(5)
relay2 = LED(6)
relay3 = LED(13)

relay4 = LED(17)
relay5 = LED(22)
relay6 = LED(27)

# Ensure relays are off initially
relay1.off()
relay2.off()
relay3.off()

# Define your sensor's calibration factor (0.333V per 5A)
sensor_output_voltage_per_current = 0.333  # Voltage output for 5A
sensor_calibration_factor = 5  # Current scaling [not used?!]

# Variable to later be setup to contain the value that is passed from the blynk relay control template
# default to 0 for auto mode, 1 = battery power, 2 = grid power
relay_mode = 0

def relays_on():
    relay2.on()
    relay3.on()
    time.sleep(0.25)
    relay1.on()

def relays_off():
    relay2.off()
    relay3.off()
    time.sleep(0.25)
    relay1.off()

# Function to control relays based on SOC and load
def control_relays(soc, present_minute, relay_mode, em_mode, pw_load):
    print(f"Relay Mode == {relay_mode}")
    if em_mode == 0:
        if relay_mode != 1 and relay_mode != 2:
            print(f"CURRENTLY IN AUTO MODE")
            if pw_load < pw_threshold:
                if soc > 20 and present_minute > 6:
                    relays_on()
                else:
                    # charge battery from midnight to 6am (switch present_minute to present_hour)
                    if soc != 100 and present_minute < 6:
                        relays_off()
                    # switch to battery when at 100% to avoid over charging
                    elif soc == 100 and present_minute < 6:
                        relays_on()
                    # redundant elif to ensure system is switched to battery during normal hours when over 80%
                    elif soc > 80 and present_minute > 6:
                        relays_on()
                    # charge battery when below 20%
                    elif soc < 20:
                        relays_off()
            else:
                relays_on()
        elif relay_mode == 1:
            print(f"CURRENTLY IN BATTERY MODE")
            relays_on()
        elif relay_mode == 2:
            print(f"CURRENTLY IN GRID MODE")
            relays_off()
    else:
        relays_off()

    # Update labels
    relay1_label.config(text=f"Relay 1: {'ON' if relay1.is_active else 'OFF'}")
    relay2_label.config(text=f"Relay 2: {'ON' if relay2.is_active else 'OFF'}")
    relay3_label.config(text=f"Relay 3: {'ON' if relay3.is_active else 'OFF'}")

# Function to read values, update the labels, and control relays in the Tkinter window
def update_readings():
    # Get the current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Log the data to DataFrame (you can optionally save data periodically)
    new_row = {
        "Timestamp": timestamp,
        "Grid Power Factor": pf_grid,
        "Grid Power (W)": pw_grid,
        "Grid Voltage (V)": volt_grid,
        "Grid Current (A)": curr_grid,
        "Load Power Factor": pf_load,
        "Load Power (W)": pw_load,
        "Load Voltage (V)": volt_load,
        "Load Current (A)": curr_load,
        "SOC (%)": soc,
        "Relay 1": "ON" if relay1.is_active else "OFF",
        "Relay 2": "ON" if relay2.is_active else "OFF",
        "Relay 3": "ON" if relay3.is_active else "OFF"
    }
    df.loc[len(df)] = new_row  # Append the new row to the DataFrame

    # Save DataFrame to Excel file (overwrite or append)
    df.to_excel(output_file, index=False)

    # Update the labels
    pf_grid_label.config(text=f"Grid PF: {pf_grid:.4f}")
    pw_grid_label.config(text=f"Grid Power: {pw_grid:.2f} W")
    curr_grid_label.config(text=f"Grid Current: {curr_grid:.2f} A")
    soc_label.config(text=f"SOC: {soc}%")
    pf_load_label.config(text=f"Load PF: {pf_load:.4f}")
    pw_load_label.config(text=f"Load Power: {pw_load:.2f} W")
    curr_load_label.config(text=f"Load Current: {curr_load:.2f} A")

    # Control relays based on SOC and load
    control_relays(soc, present_minute, relay_mode, em_mode, pw_load)

    # Schedule the next update in 5 seconds
    window.after(5000, update_readings)

# Function to dynamically update the font size based on the window size
def update_font_size(event=None):
    # Set a minimum font size of 12, and scale it with window width
    new_font_size = max(12, int(window.winfo_width() / 40))
    font = ("Helvetica", new_font_size)

    # Apply the updated font to all labels
    pf_grid_label.config(font=font)
    pw_grid_label.config(font=font)
    curr_grid_label.config(font=font)
    soc_label.config(font=font)
    pf_load_label.config(font=font)
    pw_load_label.config(font=font)
    curr_load_label.config(font=font)
    relay1_label.config(font=font)
    relay2_label.config(font=font)
    relay3_label.config(font=font)

# Function to exit fullscreen mode
def exit_fullscreen(event=None):
    window.attributes("-fullscreen", False)

# Attach Event Listeners (Detects Grid Power Loss)
emergency_button.when_released = button_released
emergency_button.when_pressed = button_pressed

# Tkinter window setup
window = tk.Tk()
window.title("Power Monitoring with Relays")
window.attributes("-fullscreen", True)
window.bind("<Escape>", exit_fullscreen)  # Bind Escape key to exit fullscreen
window.bind("<Configure>", update_font_size)  # Bind resize event to adjust font size

# Labels for display
pf_grid_label = tk.Label(window, text="Grid PF: ", font=("Helvetica", 14))
pf_grid_label.pack(pady=10, fill='both', expand=True)
pw_grid_label = tk.Label(window, text="Grid Power: ", font=("Helvetica", 14))
pw_grid_label.pack(pady=10, fill='both', expand=True)
curr_grid_label = tk.Label(window, text="Grid Current: ", font=("Helvetica", 14))
curr_grid_label.pack(pady=10, fill='both', expand=True)
soc_label = tk.Label(window, text=f"SOC: {soc}% ", font=("Helvetica", 14))
soc_label.pack(pady=10, fill='both', expand=True)
pf_load_label = tk.Label(window, text="Load PF: ", font=("Helvetica", 14))
pf_load_label.pack(pady=10, fill='both', expand=True)
pw_load_label = tk.Label(window, text="Load Power: ", font=("Helvetica", 14))
pw_load_label.pack(pady=10, fill='both', expand=True)
curr_load_label = tk.Label(window, text="Load Current: ", font=("Helvetica", 14))
curr_load_label.pack(pady=10, fill='both', expand=True)
relay1_label = tk.Label(window, text="Relay 1: OFF", font=("Helvetica", 14))
relay1_label.pack(pady=10, fill='both', expand=True)
relay2_label = tk.Label(window, text="Relay 2: OFF", font=("Helvetica", 14))
relay2_label.pack(pady=10, fill='both', expand=True)
relay3_label = tk.Label(window, text="Relay 3: OFF", font=("Helvetica", 14))
relay3_label.pack(pady=10, fill='both', expand=True)

# DataFrame for logging
columns = ["Timestamp","Grid Power Factor", "Grid Power (W)", "Grid Voltage (V)", "Grid Current (A)", "Load Power Factor", "Load Power (W)", "Load Voltage (V)", "Load Current (A)", "SOC (%)", "Relay 1", "Relay 2", "Relay 3"]
df = pd.DataFrame(columns=columns)


# Output file path for Excel
output_file = "power_readings.xlsx"

# Start reading and updating
update_readings()

button_thread = threading.Thread(target=emergency_monitor, daemon=True)
button_thread.start()

# Start the Tkinter event loop
try:
    window.mainloop()
except KeyboardInterrupt:
    print("Process interrupted by user.")
finally:
    client.loop_stop()
    client.disconnect()
