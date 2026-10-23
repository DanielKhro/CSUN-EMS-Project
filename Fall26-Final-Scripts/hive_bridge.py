
import json
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion, MQTTv5


# ==========================================
# LOCAL MQTT SETTINGS
# ==========================================
LOCAL_BROKER = "127.0.0.1"
LOCAL_PORT = 1883


# ==========================================
# HIVEMQ CLOUD SETTINGS
# ==========================================
HIVE_BROKER = "ba37807526404d90b709b31aaac053a2.s1.eu.hivemq.cloud"
HIVE_PORT = 8883

HIVE_USERNAME = "ems_pi5"
HIVE_PASSWORD = "ece493Fall"


# ==========================================
# CONTROL STATE
# ==========================================
app_mode = "auto"

# Stores the latest Jetson command.
last_jetson_payload = None


# ==========================================
# LOCAL MQTT CALLBACKS
# ==========================================
def on_local_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to local MQTT broker")

        client.subscribe("solar/battery/#")
        client.subscribe("pzem/#")
        client.subscribe("prediction/mode_select")

        # Actual EMS power-source status
        client.subscribe("ems/status/current_mode")

        print("Subscribed to:")
        print("  solar/battery/#")
        print("  pzem/#")
        print("  prediction/mode_select")
        print("  ems/status/current_mode")

    else:
        print(f"Local MQTT connection failed: {reason_code}")


def on_local_message(client, userdata, message):
    global last_jetson_payload

    topic = message.topic
    payload = message.payload.decode("utf-8")

    # ======================================
    # JETSON CONTROL MESSAGE
    # ======================================
    if topic == "prediction/mode_select":
        last_jetson_payload = payload

        print(f"Jetson command received: {payload}")

        if app_mode == "auto":
            local_client.publish(
                "relay___mode/mode_select",
                payload,
                qos=1
            )

            print("AUTO mode active: Jetson command forwarded to EMS")

        else:
            print(
                f"{app_mode.upper()} override active: "
                "Jetson command ignored"
            )

        return

    # ======================================
    # BATTERY / PZEM / EMS STATUS DATA
    # ======================================
    print(f"Local topic: {topic}")
    print(f"Payload: {payload}")

    # Keep the actual EMS mode available
    # for newly connected Flutter clients.
    retain_status = (topic == "ems/status/current_mode")

    result = cloud_client.publish(
        topic,
        payload,
        qos=1,
        retain=retain_status
    )

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("Forwarded to HiveMQ")
    else:
        print(f"Failed to forward to HiveMQ: {result.rc}")

    print()


# ==========================================
# HIVEMQ CALLBACKS
# ==========================================
def on_cloud_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to HiveMQ Cloud")

        client.subscribe(
            "ems/control/mode",
            qos=1
        )

        print("Subscribed to ems/control/mode")

    else:
        print(f"HiveMQ connection failed: {reason_code}")


def on_cloud_message(client, userdata, message):
    global app_mode
    global last_jetson_payload

    mode = message.payload.decode("utf-8").lower().strip()

    print(f"App requested mode: {mode}")

    # ======================================
    # MANUAL BATTERY
    # ======================================
    if mode == "battery":
        app_mode = "battery"

        payload = json.dumps({
            "source": "flutter_app",
            "mode_text": "BATTERY",
            "mode": 1
        })

        local_client.publish(
            "relay___mode/mode_select",
            payload,
            qos=1
        )

        print("Manual BATTERY mode activated")

    # ======================================
    # MANUAL GRID
    # ======================================
    elif mode == "grid":
        app_mode = "grid"

        payload = json.dumps({
            "source": "flutter_app",
            "mode_text": "GRID",
            "mode": 2
        })

        local_client.publish(
            "relay___mode/mode_select",
            payload,
            qos=1
        )

        print("Manual GRID mode activated")

    # ======================================
    # AUTO
    # ======================================
    elif mode == "auto":
        app_mode = "auto"

        print("AUTO mode activated")

        if last_jetson_payload is not None:
            local_client.publish(
                "relay___mode/mode_select",
                last_jetson_payload,
                qos=1
            )

            print("Latest Jetson command restored")

    else:
        print(f"Unknown mode received: {mode}")


# ==========================================
# CREATE HIVEMQ CLIENT
# ==========================================
cloud_client = mqtt.Client(
    callback_api_version=CallbackAPIVersion.VERSION2,
    client_id="hive_bridge_cloud",
    protocol=MQTTv5
)

cloud_client.username_pw_set(
    HIVE_USERNAME,
    HIVE_PASSWORD
)

cloud_client.tls_set()

cloud_client.on_connect = on_cloud_connect
cloud_client.on_message = on_cloud_message

cloud_client.connect(
    HIVE_BROKER,
    HIVE_PORT
)

cloud_client.loop_start()


# ==========================================
# CREATE LOCAL MQTT CLIENT
# ==========================================
local_client = mqtt.Client(
    callback_api_version=CallbackAPIVersion.VERSION2,
    client_id="hive_bridge_local",
    protocol=MQTTv5
)

local_client.on_connect = on_local_connect
local_client.on_message = on_local_message

local_client.connect(
    LOCAL_BROKER,
    LOCAL_PORT
)

print("Hive bridge is running...")

local_client.loop_forever()
