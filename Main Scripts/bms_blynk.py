import time
import ssl
import json
import blynklib
from paho.mqtt.client import Client, CallbackAPIVersion

######################## Settings for local MQTT broker #############################
# MQTT Local Broker configuration
broker_local = "192.168.8.2"  # Replace with your MQTT broker IP or hostname
port_local = 1883
topic_local = "solar/battery/#"  # Topic to subscribe to

soc = 0
soh = 0
volt = 0
temp = 0
curr = 0

# Callback function for MQTT DATA updates
def on_message_local(client, userdata, message):
   global soc, soh, volt, temp, curr
   try:
       payload = message.payload.decode("utf-8")
       data = json.loads(payload)
       soc = data.get("SOC", soc)
       soh = data.get("SOH", soh)
       volt = data.get("Battery_Voltage", volt)
       temp = data.get("Battery_Temperature", temp)
       curr = data.get("Battery_Current", curr)
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
BLYNK_TEMPLATE_ID   = "#############"
BLYNK_TEMPLATE_NAME = "##############"
BLYNK_AUTH_TOKEN = '####################'

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
    mqtt.publish("ds/Voltage", volt)
    mqtt.publish("ds/Current", curr)
    mqtt.publish("ds/SOH", soh)
    mqtt.publish("ds/SOC", soc)
    mqtt.publish("ds/Temperature", temp)
    print(f"Updated BMS DATA: SOC: {soc}%, SOH: {soh}%, {volt}V, {temp}C, {curr}A")

# MQTT callback to handle incoming messages
# on_message currently unused since blynk BMS data template only displays data
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
