import time
import json
import paho.mqtt.client as paho
from pymodbus.client import ModbusSerialClient as ModbusClient

# MQTT Configuration
broker = "127.0.0.1"
port = 1883

# MQTT Callback for publish
def on_publish(client, userdata, mid):
    print(f"MQTT published, message ID: {mid}")

# Specify the MQTT version and create the client instance
mqtt_client = paho.Client(client_id="pzem", protocol=paho.MQTTv5)
mqtt_client.on_publish = on_publish
mqtt_client.connect(broker, port)
mqtt_client.loop_start()

def scaleFactor(registers, sf):
    if len(registers) == 1:
        return registers[0] / sf
    else:
        return ((registers[1] << 8) + registers[0]) / sf

def readAcPZEM(chanPort, chanAddr):
    client = ModbusClient(port=chanPort, stopbits=1, bytesize=8, parity='N', baudrate=9600, timeout=1)
    client.unit_id = chanAddr  # Set the unit ID (slave address)

    data = {
        "voltage": 0,
        "amperage": 0,
        "power": 0,
        "energy": 0,
        "frequency": 0,
        "powerFactor": 0,
        "alarmStatus": 0
    }
    
    if client.connect():
        try:
            result = client.read_input_registers(address=0, count=10)
            if not result.isError():
                data["voltage"] = scaleFactor(result.registers[0:1], 10)
                data["amperage"] = scaleFactor(result.registers[1:3], 1000)
                data["power"] = scaleFactor(result.registers[3:5], 10)
                data["energy"] = scaleFactor(result.registers[5:7], 1)
                data["frequency"] = scaleFactor(result.registers[7:8], 10)
                data["powerFactor"] = scaleFactor(result.registers[8:9], 100)
                data["alarmStatus"] = int(result.registers[9])
        except Exception as e:
            print(f'Error reading AC PZEM on {chanPort}: {e}')
        finally:
            client.close()
    return data

def publish_pzem_data(mqtt_client, topic, chanPort, chanAddr, prefix, interval=1):
    while True:
        raw_data = readAcPZEM(chanPort, chanAddr)
        data = {f"{prefix} {k}": v for k, v in raw_data.items()}
        payload = json.dumps(data)
        ret = mqtt_client.publish(topic, payload)
        if ret.rc != paho.MQTT_ERR_SUCCESS:
            print(f"Error publishing data from {chanPort}: {ret.rc}")
        else:
            print(f"Published from {chanPort}: {payload}")
        time.sleep(interval)

if __name__ == "__main__":
    MQTT_TOPIC_1 = "pzem/ac_data_1"
    MQTT_TOPIC_2 = "pzem/ac_data_2"
    chanPort1 = "/dev/ttySC0"
    chanPort2 = "/dev/ttySC1"
    chanAddr = 0x01
    
    print(f"Starting MQTT publishing loop to {broker}:{port}")
    
    from threading import Thread
    
    thread1 = Thread(target=publish_pzem_data, args=(mqtt_client, MQTT_TOPIC_1, chanPort1, chanAddr, "Grid"))
    thread2 = Thread(target=publish_pzem_data, args=(mqtt_client, MQTT_TOPIC_2, chanPort2, chanAddr, "Load"))
    
    thread1.start()
    thread2.start()
    
    thread1.join()
    thread2.join()
