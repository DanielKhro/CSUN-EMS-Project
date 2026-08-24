import time
import ssl
import json
import blynklib
from paho.mqtt.client import Client, CallbackAPIVersion

######################## Settings for local MQTT broker #############################
# MQTT Local Broker configuration
broker_local = "192.168.8.2"  # Replace with your MQTT broker IP or hostname
port_local = 1883
topic_local = "pzem/#"  # Topic to subscribe to

grid_voltage = 0
grid_power = 0
grid_pf = 0
load_power = 0
load_pf = 0

# Callback function for MQTT DATA updates
def on_message_local(client, userdata, message):
   global grid_voltage, grid_power, grid_pf, load_pf, load_power
   try:
       payload = message.payload.decode("utf-8")
       data = json.loads(payload)
       grid_voltage = data.get("Grid voltage", grid_voltage)
       grid_pf = data.get("Grid powerFactor", grid_pf)
       grid_power = data.get("Grid power", grid_power)
       load_pf = data.get("Load powerFactor", load_pf)
       load_power = data.get("Load power", load_power)
   except (json.JSONDecodeError, KeyError) as e:
       print(f"Error parsing MQTT message: {e}")

# Setup Local MQTT client
client_local = mqtt_local = Client(CallbackAPIVersion.VERSION2)
client_local.connect(broker_local, port_local)
client_local.subscribe(topic_local)
client_local.on_message= on_message_local
client_local.loop_start()
#####################################################################################


# Blynk configuration provided from blynk template
BLYNK_TEMPLATE_ID   = "TMPL2xqrlfj9U"
BLYNK_TEMPLATE_NAME = "pzem"
BLYNK_AUTH_TOKEN = '1oSq1PqLi8Rb5p4jntNf2i70Farpr6AI'

MQTT_BROKER = "blynk.cloud"
MQTT_PORT = 8883

# Initialize Blynk
blynk = blynklib.Blynk(BLYNK_AUTH_TOKEN)
mqtt = Client(CallbackAPIVersion.VERSION2)

# MQTT callback to handle successful connection
def on_connect(mqtt, obj, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT broker")
        mqtt.subscribe("downlink/#", qos=0)  # Subscribe to the battery topics
    else:
        print(f"MQTT connection failed with reason code {reason_code}")
        mqtt.disconnect()

def push_updated_values():
    mqtt.publish("ds/grid voltage", grid_voltage)
    mqtt.publish("ds/grid power", grid_power)
    mqtt.publish("ds/grid pf", grid_pf)
    mqtt.publish("ds/load pf", load_pf)
    mqtt.publish("ds/load power", load_power)
    print(f"Updated BMS DATA: Grid voltage: {grid_voltage}V, Grid pf: {grid_pf}, Grid power: {grid_power}W, Load Power: {load_power}W, Load pf: {load_pf}")

# MQTT callback to handle incoming messages
# on_message currently unused since blynk pzem data template only displays data
# and does not have commands available for end-user
# def on_message(mqtt, obj, msg):
#     payload = msg.payload.decode("utf-8")
#     topic = msg.topic
#     try:
#         print(
#             f"Updated DATA from MQTT: {soc}% , {soh}% , {volt}V , {temp}C, {curr}A")
#     except ValueError:
#         print(f"ffffff")

# Main function to initialize the MQTT connection and handle the Blynk updates
def main():
    # Set up TLS encryption for secure MQTT connection
    mqtt.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
    mqtt.on_connect = on_connect
    # mqtt.on_message = on_message # not used

    # Set username and password for MQTT connection
    mqtt.username_pw_set("device", BLYNK_AUTH_TOKEN)

    # Connect to MQTT broker
    mqtt.connect_async(MQTT_BROKER, MQTT_PORT, 45)
    mqtt.loop_start()  # Start the MQTT loop

    try:
        while True:
            # This loop will keep Blynk running
            push_updated_values()
            blynk.run()
            time.sleep(0.1)  # Sleep to prevent high CPU usage
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        mqtt.loop_stop()  # Stop MQTT loop
        mqtt.disconnect()  # Disconnect from the MQTT broker

if __name__ == "__main__":
    main()