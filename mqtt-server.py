import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe("/esp32/#")  # 订阅 esp32 所有 topic

def on_message(client, userdata, msg):
    print("========== MQTT MESSAGE RECEIVED ==========")
    print(f"Topic: {msg.topic}")
    print(f"Payload: {msg.payload.decode()}")
    print("===========================================")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("192.168.77.93", 1883)
client.loop_forever()

