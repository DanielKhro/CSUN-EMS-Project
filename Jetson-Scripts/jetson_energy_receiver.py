import os
from datetime import datetime
import paho.mqtt.client as mqtt

BROKER_IP = "192.168.8.236"   # <-- IP of device running Mosquitto
TOPIC = "load/power"

OUT_FILE = "/home/ece493/Desktop/ECE 493 PROJECT/BEMS_ProfileService_FINAL_NEW CSV/BEMS_ProfileService/BEMS_ProfileService/current_watts.txt"

def on_connect(client, userdata, flags, rc):
    print("Connected to broker")
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        watts = float(msg.payload.decode())
    except:
        return

    with open(OUT_FILE, "w") as f:
        f.write(str(watts))

    print(f"{datetime.now()} → Load: {watts} W")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER_IP, 1883, 60)
client.loop_forever()