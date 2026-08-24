import os
import can
import cantools
import paho.mqtt.client as paho
from pprint import pprint
import time
import json
from datetime import datetime

# Configuration
broker = "127.0.0.1"
port = 1883
dbcfile = "/home/pi/pylontech.dbc"
caninterface = "can0"

# MQTT Callback for publish
def on_publish(client, userdata, mid):
    print(f"mqtt published, message id: {mid}")
    pass

# Specify the MQTT version and create the client instance
client1 = paho.Client(client_id="battery", protocol=paho.MQTTv5)
client1.on_publish = on_publish  # Assign the callback for publish
client1.connect(broker, port)

client1.loop_start()  # Start the MQTT loop

# CAN Bus setup
try:
    can_bus = can.interface.Bus(channel=caninterface, interface='socketcan')
except Exception as e:
    print(f"Error initializing CAN interface: {e}")
    exit(1)

# Load DBC file
if not os.path.exists(dbcfile):
    print(f"DBC file {dbcfile} not found!")
    exit(1)

db = cantools.database.load_file(dbcfile)

# MQTT Topic and Value Templates
binary_sensor_topic_template = 'homeassistant/binary_sensor/battery/{}/config'
binary_sensor_value_template = '''{
    "name": "Battery {sensor}",
    "unique_id": "battery_#_{sensor}",
    "state_topic": "solar/battery/{sensor}",
    "pl_on": "1",
    "pl_off": "0",
    "value_template": "{{ value_json.{sensor} }}",
    "device": {
        "name": "battery",
        "ids": "battery",
        "cu": "http://solaranzeige.fritz.box",
        "mf": "PYLON",
        "mdl": "US2000, US3000, US5000",
        "sw": "00000001"
    }
}'''

sensor_topic_template = 'homeassistant/sensor/battery/{}/config'
sensor_value_template = '''{
    "name": "Battery {sensor}",
    "unique_id": "battery_#_{sensor}",
    "state_topic": "solar/battery/{sensor}",
    "value_template": "{{ value_json.{sensor} }}",
    "device": {
        "name": "battery",
        "ids": "battery",
        "cu": "http://solaranzeige.fritz.box",
        "mf": "PYLON",
        "mdl": "US2000, US3000, US5000",
        "sw": "00000001"
    },
    "expire_after": 45,
    "state_class": "measurement"
}'''

# Function to publish alarms/warnings
def publish_alarm_warns():
    alarms_and_warns = [
        "Alarm_Over_Current_Discharge", "Alarm_Under_Temperature", "Alarm_Over_Temperature", 
        "Alarm_Under_Voltage", "Alarm_Over_Voltage", "Alarm_Internal", 
        "Alarm_Over_Current_Charge", "Warn_High_Current_Discharge", "Warn_Low_Temperature",
        "Warn_High_Temperature", "Warn_Low_Voltage", "Warn_High_Voltage", 
        "Warn_Internal", "Warn_High_Current_Charge", "Charge_Immediately",
        "Discharge_Enable", "Charge_Enable"
    ]

    for alarm in alarms_and_warns:
        topic = binary_sensor_topic_template.format(alarm)
        value = binary_sensor_value_template.format(sensor=alarm)
        ret = client1.publish(topic, value)
        if ret.rc != paho.MQTT_ERR_SUCCESS:
            print(f"Error publishing {alarm}: {ret.rc}")

# Function to publish sensor data
def publish_sensor_data():
    sensor_data = {
        "Battery_Voltage": {'device_class': 'voltage', 'unit_of_measurement': 'V', 'min': 44.5, 'max': 53.5},
        "Battery_Current": {'device_class': 'current', 'unit_of_measurement': 'A', 'min': -148, 'max': 148},
        "Battery_Temperature": {'device_class': 'temperature', 'unit_of_measurement': '°C', 'min': 0, 'max': 40},
        "SOC": {'device_class': 'battery', 'unit_of_measurement': '%'},
        "SOH": {'device_class': 'battery', 'unit_of_measurement': '%'},
        "Battery_Charge_Voltage": {'device_class': 'voltage', 'unit_of_measurement': 'V'},
        "Charge_Current_Limitation": {'device_class': 'current', 'unit_of_measurement': 'A'},
        "Discharge_Current_Limitation": {'device_class': 'current', 'unit_of_measurement': 'A'}
    }

    for sensor, params in sensor_data.items():
        topic = sensor_topic_template.format(sensor)
        value = sensor_value_template.format(sensor=sensor)

        # Add additional sensor parameters
        value = value.replace("}", f', "device_class": "{params["device_class"]}", "unit_of_measurement": "{params["unit_of_measurement"]}"}}')

        if "min" in params and "max" in params:
            value = value.replace("}}", f', "min": {params["min"]}, "max": {params["max"]}}}')

        ret = client1.publish(topic, value)
        if ret.rc != paho.MQTT_ERR_SUCCESS:
            print(f"Error publishing {sensor}: {ret.rc}")

# Main loop to process CAN messages and publish to MQTT
while True:
    try:
        # Receive CAN message
        message = can_bus.recv()

        # Decode the message
        try:
            canname = db.get_message_by_frame_id(message.arbitration_id).name
            test = db.decode_message(message.arbitration_id, message.data)
            ret = client1.publish(f"solar/battery/{canname}", str(test).replace("'", "\""))
            if ret.rc != paho.MQTT_ERR_SUCCESS:
                print(f"Error publishing CAN message {canname}: {ret.rc}")
        except Exception as e:
            print(f"Error decoding CAN message: {e}")

    except KeyboardInterrupt:
        print("Terminating program.")
        break  # Break out of the while loop when the user presses Ctrl+C
    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep(1)

# Stop the MQTT loop after the main loop is finished
client1.loop_stop()
