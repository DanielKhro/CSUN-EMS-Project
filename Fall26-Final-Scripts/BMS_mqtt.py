import os
import can
import cantools
import paho.mqtt.client as paho
import time
import json
from paho.mqtt.client import CallbackAPIVersion, MQTTv5


# ==========================================
# CONFIGURATION
# ==========================================
broker = "127.0.0.1"
port = 1883

dbcfile = "/home/ece493/Desktop/Main_Scripts/pylontech_ao.dbc"
caninterface = "can0"

BATTERY_TOPIC = "solar/battery/status"

# Publish one combined message every 1 second
PUBLISH_INTERVAL = 1.0


# ==========================================
# MQTT CALLBACK
# ==========================================
def on_publish(client, userdata, mid, reason_code, properties):
    print(f"MQTT published, message ID: {mid}")


# ==========================================
# CREATE MQTT CLIENT
# ==========================================
client1 = paho.Client(
    callback_api_version=CallbackAPIVersion.VERSION2,
    client_id="pylontech_battery_pi",
    protocol=MQTTv5
)

client1.on_publish = on_publish

client1.connect(
    broker,
    port
)

client1.loop_start()


# ==========================================
# CAN BUS SETUP
# ==========================================
try:
    can_bus = can.interface.Bus(
        channel=caninterface,
        interface="socketcan"
    )

except Exception as e:
    print(f"Error initializing CAN interface: {e}")
    exit(1)


# ==========================================
# LOAD DBC FILE
# ==========================================
if not os.path.exists(dbcfile):
    print(f"DBC file {dbcfile} not found!")
    exit(1)

db = cantools.database.load_file(dbcfile)


# ==========================================
# LATEST BATTERY DATA
# ==========================================
battery_data = {
    "SOC": 0,
    "SOH": 0,

    "Battery_Voltage": 0.0,
    "Battery_Current": 0.0,
    "Battery_Temperature": 0.0,

    "Battery_Charge_Voltage": 0.0,
    "Charge_Current_Limitation": 0.0,
    "Discharge_Current_Limitation": 0.0,
    "Low_Voltage_Limit": 0.0,

    "AlarmWarn_Raw": 0
}


last_publish_time = 0


# ==========================================
# MAIN LOOP
# ==========================================
while True:

    try:
        # Wait for a CAN message
        message = can_bus.recv()

        try:
            # Find the message definition in the DBC
            message_def = db.get_message_by_frame_id(
                message.arbitration_id
            )

            canname = message_def.name

            # Only decode the useful messages
            if canname not in {
                "BMS_DC_Parameter",
                "BMS_State",
                "BMS_Battery",
                "BMS_Alarm_Warn_Extended"
            }:
                continue

            decoded_data = db.decode_message(
                message.arbitration_id,
                message.data
            )

            # Update the latest battery values
            battery_data.update(decoded_data)

            # Check if it is time to publish
            current_time = time.time()

            if current_time - last_publish_time >= PUBLISH_INTERVAL:

                payload = json.dumps(battery_data)

                print()
                print("Battery Status")
                print(battery_data)

                ret = client1.publish(
                    BATTERY_TOPIC,
                    payload
                )

                if ret.rc != paho.MQTT_ERR_SUCCESS:
                    print(
                        f"Error publishing battery status: "
                        f"{ret.rc}"
                    )

                last_publish_time = current_time

        except Exception as e:
            print(f"Error decoding CAN message: {e}")


    except KeyboardInterrupt:
        print("Terminating program.")
        break


    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep(1)


# ==========================================
# CLEANUP
# ==========================================
client1.loop_stop()
client1.disconnect()