#!/usr/bin/env python3
import sys, time, yaml, logging
import paho.mqtt.client as mqtt
import datetime as dt
from sensors import entities


logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    level=logging.INFO)


def make_config_message(devicename: str, entity: str, attr: dict) -> tuple:
    """Creates MQTT config message (consiting of topic and payload) 
    """
    topic = f'homeassistant/{attr["type"]}/{devicename}/{entity}/config'
    payload =  '{'
    payload += f'"device_class":"{attr["device_class"]}",' if 'device_class' in attr else ''
    payload += f'"state_class":"{attr["state_class"]}",' if 'state_class' in attr else ''
    payload += f'"name":"{devicename} {attr["name"]}",'
    payload += f'"state_topic":"homeassistant/{attr["type"]}/{devicename}/state",'
    if attr["type"] in ("switch", "number"):
        payload += f'"command_topic":"homeassistant/{attr["type"]}/{devicename}/{entity}",'
    payload += f'"availability_topic":"homeassistant/sensor/{devicename}/availability",'
    payload += f'"unit_of_measurement":"{attr["unit"]}",' if 'unit' in attr else ''
    payload += f'"value_template":"{{{{value_json.{entity}}}}}",'
    payload += f'"unique_id":"{devicename}_{entity}",'
    payload += f'"device":{{"identifiers":["{devicename}"],"name":"{devicename}"}},'
    payload += f'"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else ''
    payload += '}' 
    return topic, payload
    
    
class MqttDevice:
    def __init__(self, hostname, port, devicename):
        self.devicename = devicename     
        self.mqttClient = mqtt.Client(client_id=settings['client_id'])
        self.mqttClient.on_connect = self.on_connect                      #attach function to callback
        self.mqttClient.on_message = self.on_message
        self.mqttClient.will_set(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)

        with open('secrets.yaml', 'r') as f:
            mqtt_auth = yaml.safe_load(f)['mqtt_auth']
            self.mqttClient.username_pw_set(mqtt_auth['user'], mqtt_auth['password'])
            del mqtt_auth

        self.mqttClient.connect(hostname, port)
        self.send_config_message()
        self.mqttClient.loop_start()
    

    def exit(self):
        logging.info('Exiting MQTT thread and running cleanup code')
        self.mqttClient.publish(f'homeassistant/sensor/{self.devicename}/availability', 'offline', retain=True)
        self.mqttClient.disconnect()
        self.mqttClient.loop_stop()


    def update_states(self, update_sensors=True, update_switches=True, update_numbers=True):
        if update_sensors:
            any_update = False
            payload = '{'
            for entity, attr in entities.items():
                if attr["type"] == "sensor":        
                    payload += f'"{entity}": "{attr["function"]()}",'
                    any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/sensor/{self.devicename}/state'
                pub_ret = self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")

        if update_switches:
            any_update = False
            payload = '{'
            for entity, attr in entities.items():
                if attr["type"] == "switch":        
                    payload += '"{}": "{}",'.format(entity, entities[entity]["value"])
                    any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/switch/{self.devicename}/state'
                pub_ret = self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")
                
        if update_numbers:
            any_update = False
            payload = '{'
            for entity, attr in entities.items():
                if attr["type"] == "number":        
                    payload += '"{}": "{}",'.format(entity, entities[entity]["value"])
                    any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/number/{self.devicename}/state'
                pub_ret = self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")
                
                
    def send_config_message(self):
        logging.info('Sending config message to host...')

        for entity, attr in entities.items():
            try:
                topic, payload = make_config_message(self.devicename, entity, attr)
                logging.info(f"publish topic: {topic}")
                logging.info(f"publish payload: {payload}")           
                self.mqttClient.publish(topic=topic, payload=payload, qos=1, retain=True)          
            
            except Exception as e:
                logging.warning('An error was produced while processing ' + str(entity) + ' with exception: ' + str(e))
                logging.warning(str(settings))
                raise
            
        self.mqttClient.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)


    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info('Connected to broker')
            self.mqttClient.subscribe('hass/status')
            logging.debug("Clearify the difference of the two clients")
            self.mqttClient.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)
            self.mqttClient.subscribe(f"homeassistant/sensor/{self.devicename}/command") #subscribe
            for entity, attrs in entities.items():
                if attrs["type"] in ("switch", "number"):
                    self.mqttClient.subscribe(f"homeassistant/{attrs['type']}/{self.devicename}/{entity}")  # subscribe to setter
            self.mqttClient.publish(f"homeassistant/sensor/{self.devicename}/command", "setup", retain=True)
        elif rc == 5:
            logging.info('Authentication failed. Exiting...')
            self.exit()
        else:
            logging.info(f'Connection failed with return code {rc}.')
            self.exit()
            

    def on_message(self, client, userdata, message):
        msg = message.payload.decode()
        logging.info(f"Message received: topic='{message.topic}', message='{msg}'")
        entity = str(message.topic).split("/")[-1]
        logging.info(f"entity: {entity}")
        global entities
        if entity in entities:
            entities[entity]["value"] = msg
            self.update_states(update_sensors=False)  # send confirmation
                    
        elif message.payload.decode() == 'online':
            logging.info("reconfiguring")
            self.send_config_message()


if __name__ == '__main__':
    with open("settings.yaml") as f:
        settings = yaml.safe_load(f)
    
    device = MqttDevice(hostname=settings['mqtt']['hostname'],
                            port=settings['mqtt']['port'], 
                            devicename=settings["devicename"])

    try:
        while True:
            device.update_states()
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    
    device.exit()
    logging.info("exiting main")
