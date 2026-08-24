import time
import ssl
import blynklib
from paho.mqtt.client import Client, CallbackAPIVersion
import json

# Blynk configuration provided from blynk template
BLYNK_TEMPLATE_ID   = "TMPL2tI0YO8kc"
BLYNK_TEMPLATE_NAME = "Relays"
BLYNK_AUTH_TOKEN = '_CJqq63zzurnhVhZ2Yn9j7mkc2tANX7B'

MQTT_BROKER = "blynk.cloud"
MQTT_PORT = 8883

# Local MQTT broker setup
broker_local = "192.168.8.2"
port_local = 1883

# Initialize Blynk
blynk = blynklib.Blynk(BLYNK_AUTH_TOKEN)
mqtt = Client(CallbackAPIVersion.VERSION2)
mqtt_local = Client(CallbackAPIVersion.VERSION2)

mode_select = 0
auto = 1
grid = 0
battery = 0


# MQTT callback to handle successful connection
def on_connect(mqtt, obj, flags, reason_code, properties):
    mqtt.publish("get/ds", "Auto, Battery, Grid")
    mqtt.publish("ds/Auto", auto)
    mqtt.publish("ds/Grid", grid)
    mqtt.publish("ds/Battery", battery)
    print(f"Auto = {auto}, Grid = {grid}, Battery = {battery}")
    if reason_code == 0:
        print("Connected to MQTT broker")
        mqtt.subscribe("downlink/#", qos=0)  # Subscribe to the battery topics
    else:
        print(f"MQTT connection failed with reason code {reason_code}")
        mqtt.disconnect()

# MQTT callback to handle incoming messages
def on_message(mqtt, obj, msg):
    global auto, battery, grid, mode_select
    payload = msg.payload.decode("utf-8")
    topic = msg.topic
    if topic == "downlink/ds/Auto":
        auto = int(payload)
        battery = 0
        grid = 0
        mode_select = '0'
        mqtt.publish("ds/Battery", battery)
        mqtt.publish("ds/Grid", grid)
        print(f"Auto = {auto}, Grid = {grid}, Battery = {battery}")
    elif topic == "downlink/ds/Battery":
        battery = int(payload)
        auto = 0
        grid = 0
        mode_select = 1
        mqtt.publish("ds/Grid", grid)
        mqtt.publish("ds/Auto", auto)
        print(f"Auto = {auto}, Grid = {grid}, Battery = {battery}")
    elif topic == "downlink/ds/Grid":
        grid = int(payload)
        auto = 0
        battery = 0
        mode_select = 2
        mqtt.publish("ds/Battery", battery)
        mqtt.publish("ds/Auto", auto)
        print(f"Auto = {auto}, Grid = {grid}, Battery = {battery}")

def publish_mode_select_to_local():
    while True:
        data = {"mode": mode_select}
        payload = json.dumps(data)
        if mqtt_local.is_connected():
            mqtt_local.publish("relay___mode/mode_select", payload)
            print(f"Pushed mode_select = {payload} to local broker")
        else:
            print("Local MQTT broker is not connected")
        time.sleep(1)


# Main function to initialize the MQTT connection and handle the Blynk updates
def main():
    mqtt.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
    mqtt.on_connect = on_connect
    mqtt.on_message = on_message

    # Set username and password for MQTT connection
    mqtt.username_pw_set("device", BLYNK_AUTH_TOKEN)

    # Connect to MQTT broker
    mqtt.connect_async(MQTT_BROKER, MQTT_PORT, 45)
    mqtt.loop_start()  # Start the MQTT loop

    mqtt_local.connect(broker_local, port_local)
    mqtt_local.loop_start()

    try:
        while True:
            # This loop will keep Blynk running
            blynk.run()
            publish_mode_select_to_local()
            time.sleep(0.1)  # Sleep to prevent high CPU usage
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        mqtt.loop_stop()  # Stop MQTT loop
        mqtt.disconnect()  # Disconnect from the MQTT broker


if __name__ == "__main__":
    main()