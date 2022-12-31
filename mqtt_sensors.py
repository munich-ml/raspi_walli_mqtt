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
    if attr["type"] == "number":
        payload += f'"min":"{attr["min"]}",' if 'min' in attr else ''
        payload += f'"max":"{attr["max"]}",' if 'max' in attr else ''
        payload += f'"step":"{attr["step"]}",' if 'step' in attr else ''    
    payload += f'"device":{{"identifiers":["{devicename}"],"name":"{devicename}"}},'
    payload += f'"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else ''
    payload += '}' 
    return topic, payload
    
    
class MqttDevice:
    def __init__(self, hostname, port, devicename, client_id, entities):
        self.devicename = devicename     
        self._entities = entities
        for entity in entities.values():
            entity.update({"value_updated": False})
        self.client = mqtt.Client(client_id=client_id)
        self.client._on_connect = self._on_connect
        self.client._on_message = self._on_message
        self.client.will_set(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)

        with open('secrets.yaml', 'r') as f:
            mqtt_auth = yaml.safe_load(f)['mqtt_auth']
            self.client.username_pw_set(mqtt_auth['user'], mqtt_auth['password'])
            del mqtt_auth

        self.client.connect(hostname, port)
        self._publish_config()
        self.client.loop_start()
    

    def exit(self):
        logging.info('Exiting MQTT thread and running cleanup code')
        self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'offline', retain=True)
        self.client.disconnect()
        self.client.loop_stop()

 
    def publish_updates(self, ignore_updated_flag=False):
        for type_ in ("sensor", "switch", "number"):
            any_update = False
            payload = '{'
            for entity, attr in self._entities.items():
                if attr["type"] == type_:
                    if ignore_updated_flag or attr["value_updated"]:
                        payload += '"{}": "{}",'.format(entity, attr["value"])
                        attr["value_updated"] = False
                        any_update = True
            if any_update:
                payload = payload[:-1] + '}'
                topic = f'homeassistant/{type_}/{self.devicename}/state'
                pub_ret = self.client.publish(topic=topic, payload=payload, qos=1, retain=False)
                logging.info(f"{pub_ret} from publish(topic={topic}, payload={payload})")            
    
    
    def get_states(self):
        return {k: v["value"] for k, v in self._entities.items()}
    
    
    def set_states(self, states_dict):
        for entity, value in states_dict.items():
            if entity in self._entities:
                if value.isnumeric():
                    value = int(value)
                else:
                    try:
                        value = float(value)
                    except:
                        pass
                if value != self._entities[entity]["value"]:
                    self._entities[entity]["value"] = value
                    self._entities[entity]["value_updated"] = True
            
                
    def _publish_config(self):
        for entity, attr in self._entities.items():
            topic, payload = make_config_message(self.devicename, entity, attr)
            logging.info(f"publish config topic={topic}, payload={payload}")           
            self.client.publish(topic=topic, payload=payload, qos=1, retain=True)          
        self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)


    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info('Successfully connected to broker')
            self.client.subscribe('hass/status')
            self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'online', retain=True)
            self.client.subscribe(f"homeassistant/sensor/{self.devicename}/command") #subscribe
            for entity, attrs in self._entities.items():
                if attrs["type"] in ("switch", "number"):
                    self.client.subscribe(f"homeassistant/{attrs['type']}/{self.devicename}/{entity}")  # subscribe to setters
            self.client.publish(f"homeassistant/sensor/{self.devicename}/command", "setup", retain=True)
            self.publish_updates(ignore_updated_flag=True)  # send initial sensor values
            
        elif rc == 5:
            logging.info('Authentication failed. Exiting...')
            self.exit()
        else:
            logging.info(f'Connection failed with return code {rc}.')
            self.exit()
            

    def _on_message(self, client, userdata, message):
        msg = message.payload.decode()
        logging.info(f"Message received: topic='{message.topic}', message='{msg}'")
        entity = str(message.topic).split("/")[-1]
        if entity in self._entities:
            self.set_states({entity: msg})
            self.publish_updates()  # send confirmation to homeassistant          
        elif message.payload.decode() == 'online':
            logging.info("reconfiguring")
            self._publish_config()


if __name__ == '__main__':
    import random
    with open("settings.yaml") as f:
        settings = yaml.safe_load(f)

    with open('entities.yaml', 'r') as f:
        entities = yaml.safe_load(f)
    
    device = MqttDevice(hostname=settings['mqtt']['hostname'], port=settings['mqtt']['port'], 
                        devicename=settings["devicename"], client_id=settings['client_id'],
                        entities=entities)
    
    FOLLOW_RATE = 0.2
    
    try:
        while True:
            stat = device.get_states()
            if stat["power_switch"] == "ON":
                delta = stat["set_temperature"] - stat["temperature"]
                new_temperature = stat["temperature"] + delta * FOLLOW_RATE
                device.set_states({"temperature": new_temperature})
                device.publish_updates()
            time.sleep(1)
            #time.sleep(settings["update_interval"])
            #device.set_states({"temperature": random.choice((13.1, 15.7, 21.3, 37.9)),
            #                   "set_temperature": random.choice((19, 21.4, 27.9)),
            #                   "power_switch": random.choice(("OFF", "ON"))})
    except KeyboardInterrupt:
        pass
    
    device.exit()
    logging.info("exiting main")
