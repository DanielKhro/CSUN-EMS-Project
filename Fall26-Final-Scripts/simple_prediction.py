
import json
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion, MQTTv5

# Local Raspberry Pi MQTT broker
BROKER = "127.0.0.1"
PORT = 1883

# Existing prediction topic used by hive_bridge.py
TOPIC = "prediction/mode_select"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to Raspberry Pi MQTT")
    else:
        print(f"Connection failed: {reason_code}")


client = mqtt.Client(
    callback_api_version=CallbackAPIVersion.VERSION2,
    client_id="simple_prediction",
    protocol=MQTTv5
)

client.on_connect = on_connect

client.connect(BROKER, PORT)
client.loop_start()

print("Simple Prediction is ready.")
print("Enter 'grid' or 'battery' to publish a prediction.")
print("Enter 'q' to quit.")

try:
    while True:
        mode = input("\nPredicted mode: ").strip().lower()

        if mode == "q":
            break

        if mode == "grid":
            mode_number = 2

        elif mode == "battery":
            mode_number = 1

        else:
            print("Invalid mode. Enter grid or battery.")
            continue

        payload = json.dumps({
            "source": "simple_prediction",
            "mode_text": mode.upper(),
            "mode": mode_number
        })

        result = client.publish(
            TOPIC,
            payload,
            qos=1,
            retain=False
        )

        result.wait_for_publish()

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Published prediction: {mode.upper()}")
        else:
            print(f"Publish failed: {result.rc}")

except KeyboardInterrupt:
    print("\nStopping Simple Prediction.")

finally:
    client.loop_stop()
    client.disconnect()
