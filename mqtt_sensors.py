#!/usr/bin/env python3
import time, yaml, logging
import paho.mqtt.client as mqtt

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
    def __init__(self, hostname, port, devicename, client_id, entities):
        self.devicename = devicename     
        self.entities = entities
        self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self.on_connect                      #attach function to callback
        self.client.on_message = self.on_message
        self.client.will_set(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)

        with open('secrets.yaml', 'r') as f:
            mqtt_auth = yaml.safe_load(f)['mqtt_auth']
            self.client.username_pw_set(mqtt_auth['user'], mqtt_auth['password'])
            del mqtt_auth

        self.client.connect(hostname, port)
        self.send_config_message()
        self.client.loop_start()
    

    def exit(self):
        logging.info('Exiting MQTT thread and running cleanup code')
        self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'offline', retain=True)
        self.client.disconnect()
        self.client.loop_stop()


    def update_states(self, update_sensors=True, update_switches=True, update_numbers=True):
        if update_sensors:
            any_update = False
            payload = '{'
            for entity, attr in self.entities.items():
                if attr["type"] == "sensor":        
                    payload += '"{}": "{}",'.format(entity, sensors[entity]["value"])
                    any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/sensor/{self.devicename}/state'
                pub_ret = self.client.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")

        if update_switches:
            any_update = False
            payload = '{'
            for entity, attr in self.entities.items():
                if attr["type"] == "switch":        
                    payload += '"{}": "{}",'.format(entity, sensors[entity]["value"])
                    any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/switch/{self.devicename}/state'
                pub_ret = self.client.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")
                
        if update_numbers:
            any_update = False
            payload = '{'
            for entity, attr in self.entities.items():
                if attr["type"] == "number":        
                    payload += '"{}": "{}",'.format(entity, sensors[entity]["value"])
                    any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/number/{self.devicename}/state'
                pub_ret = self.client.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")
    
    def update(self, entity, value):
        pass
    
                
    def send_config_message(self):
        logging.info('Sending config message to host...')

        for entity, attr in self.entities.items():
            try:
                topic, payload = make_config_message(self.devicename, entity, attr)
                logging.info(f"publish topic: {topic}")
                logging.info(f"publish payload: {payload}")           
                self.client.publish(topic=topic, payload=payload, qos=1, retain=True)          
            
            except Exception as e:
                logging.warning('An error was produced while processing ' + str(entity) + ' with exception: ' + str(e))
                logging.warning(str(settings))
                raise
            
        self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)


    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info('Successfully connected to broker')
            self.client.subscribe('hass/status')
            self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)
            self.client.subscribe(f"homeassistant/sensor/{self.devicename}/command") #subscribe
            for entity, attrs in self.entities.items():
                if attrs["type"] in ("switch", "number"):
                    self.client.subscribe(f"homeassistant/{attrs['type']}/{self.devicename}/{entity}")  # subscribe to setters
            self.client.publish(f"homeassistant/sensor/{self.devicename}/command", "setup", retain=True)
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
        if entity in self.entities:
            self.entities[entity]["value"] = msg
            self.update_states(update_sensors=False)  # send confirmation
                    
        elif message.payload.decode() == 'online':
            logging.info("reconfiguring")
            self.send_config_message()


if __name__ == '__main__':
    with open("settings.yaml") as f:
        settings = yaml.safe_load(f)

    with open('entities.yaml', 'r') as f:
        entities = yaml.safe_load(f)
    
    device = MqttDevice(hostname=settings['mqtt']['hostname'], port=settings['mqtt']['port'], 
                        devicename=settings["devicename"], client_id=settings['client_id'])
    try:
        while True:
            device.update_states()
            time.sleep(settings["update_interval"])
    except KeyboardInterrupt:
        pass
    
    device.exit()
    logging.info("exiting main")
