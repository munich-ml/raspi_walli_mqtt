#!/usr/bin/env python3
import sys, threading, time, yaml, logging
import paho.mqtt.client as mqtt
import datetime as dt
from sensors import sensors



logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    level=logging.INFO)

tsw = "ON"


def make_config_message(devicename: str, sensor: str, attr: dict) -> tuple:
    """Creates MQTT config message (consiting of topic and payload) 
    """
    topic = f'homeassistant/sensor/{devicename}/{sensor}/config'
    payload =  '{'
    payload += f'"device_class":"{attr["device_class"]}",' if 'device_class' in attr else ''
    payload += f'"state_class":"{attr["state_class"]}",' if 'state_class' in attr else ''
    payload += f'"name":"{devicename} {attr["name"]}",'
    payload += f'"state_topic":"homeassistant/sensor/{devicename}/state",'
    payload += f'"unit_of_measurement":"{attr["unit"]}",' if 'unit' in attr else ''
    payload += f'"value_template":"{{{{value_json.{sensor}}}}}",'
    payload += f'"unique_id":"{devicename}_{sensor}",'
    payload += f'"availability_topic":"homeassistant/sensor/{devicename}/availability",'
    payload += f'"device":{{"identifiers":["{devicename}_sensor"],"name":"{devicename}"}},'
    payload += f'"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else ''
    payload += '}' 
    return topic, payload


def make_command_message(devicename: str, sensor: str, attr: dict):
    """Creates MQTT config message (consiting of topic and payload) 
    """
    topic = f'homeassistant/switch/{devicename}/{sensor}/config'
    payload =  '{'
    payload += f'"device_class":"{attr["device_class"]}",' if 'device_class' in attr else ''
    payload += f'"state_class":"{attr["state_class"]}",' if 'state_class' in attr else ''
    payload += f'"name":"{devicename} {attr["name"]}",'
    payload += f'"state_topic":"homeassistant/switch/{devicename}/state",'
    payload += f'"value_template":"{{{{value_json.{sensor}}}}}",'
    payload += f'"command_topic":"homeassistant/switch/{devicename}/{sensor}",'
    payload += f'"unique_id":"{devicename}_{sensor}",'
    payload += f'"availability_topic":"homeassistant/sensor/{devicename}/availability",'
    payload += f'"device":{{"identifiers":["{devicename}_switch"],"name":"{devicename}"}}'
    payload += f'"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else ''
    payload += '}' 
    return topic, payload
    
    
class MqttInterface(threading.Thread):
    def __init__(self, devicename):
        self.devicename = devicename
        super().__init__()
        self.exiting = False
        
        self.mqttClient = mqtt.Client(client_id=settings['client_id'])
        self.mqttClient.on_connect = self.on_connect                      #attach function to callback
        self.mqttClient.on_message = self.on_message
        self.mqttClient.will_set(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)
        
        logging.warning("take care of the secrets")
        with open('secrets.yaml', 'r') as f:
            mqtt_auth = yaml.safe_load(f)['mqtt_auth']
            self.mqttClient.username_pw_set(mqtt_auth['user'], mqtt_auth['password'])
            del mqtt_auth

        while True:
            try:
                self.mqttClient.connect(settings['mqtt']['hostname'], settings['mqtt']['port'])
                break
            except ConnectionRefusedError:
                # sleep for 2 minutes if broker is unavailable and retry.
                # Make this value configurable?
                # this feels like a dirty hack. Is there some other way to do this?
                time.sleep(120)
            except OSError:
                # sleep for 10 minutes if broker is not reachable, i.e. network is down
                # Make this value configurable?
                # this feels like a dirty hack. Is there some other way to do this?
                time.sleep(600)

        self.send_config_message()
        self.mqttClient.loop_start()
        self.start()
    
    
    def run(self):
        while not self.exiting:
            self.update_sensors()
            time.sleep(60)


    def exit(self):
        logging.info('Exiting MQTT thread and running cleanup code')
        self.mqttClient.publish(f'homeassistant/sensor/{self.devicename}/availability', 'offline', retain=True)
        self.mqttClient.disconnect()
        self.mqttClient.loop_stop()
        self.exiting = True
        

    def update_sensors(self):
        payload = '{'
        for sensor, attr in sensors.items():        
            payload += f'"{sensor}": "{attr["function"]()}",'
        payload = payload[:-1] + '}'
        topic = f'homeassistant/sensor/{self.devicename}/state'
        pub_ret = self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=False)
        logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")
    

    def send_config_message(self):
        logging.info('Sending config message to host...')

        for sensor, attr in sensors.items():
            try:
                topic, payload = make_config_message(self.devicename, sensor, attr)
                logging.info(f"publish topic: {topic}")
                logging.info(f"publish payload: {payload}")           
                self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=True)          
            
            except Exception as e:
                logging.warning('An error was produced while processing ' + str(sensor) + ' with exception: ' + str(e))
                logging.warning(str(settings))
                raise
            
        topic, payload = make_command_message(self.devicename, "tsw", attr={"name": "TSwitch"})    
        logging.info(f"publish topic: {topic}")
        logging.info(f"publish payload: {payload}")           
        self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=True)  
            
        self.mqttClient.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)


    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info('Connected to broker')
            client.subscribe('hass/status')
            logging.debug("Clearify the difference of the two clients")
            self.mqttClient.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)
            client.subscribe(f"homeassistant/sensor/{self.devicename}/command") #subscribe
            client.subscribe(f"homeassistant/switch/{self.devicename}/.")  # command topic trial
            client.subscribe("homeassistant/sensor/to_wallbox")  # proprietary, remove later, when command topic works
            client.publish(f"homeassistant/sensor/{self.devicename}/command", "setup", retain=True)
        elif rc == 5:
            logging.info('Authentication failed.\n Exiting.')
            self.exit()
        else:
            logging.info(f'Connection failed with return code {rc}.')
            self.exit()
            

    def on_message(self, client, userdata, message):
        msg = message.payload.decode()
        logging.info(f"Message received: topic='{message.topic}', message='{msg}', userdata={userdata}")
        if msg in ("ON", "OFF"):
            global tsw
            tsw = msg
            payload = '{"tsw":"' + tsw + '"}'
            topic = f'homeassistant/switch/{self.devicename}/state'
            pub_ret = self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=False)
            logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")
                    
        if message.payload.decode() == 'online':
            logging.info("reconfiguring")
            self.send_config_message()


if __name__ == '__main__':


    with open("settings.yaml") as f:
        settings = yaml.safe_load(f)
    
    mqtt_if = MqttInterface(devicename=settings["devicename"])

    try:
        while True:
            sys.stdout.flush()
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    
    mqtt_if.exit()
    logging.info("exiting main")


            