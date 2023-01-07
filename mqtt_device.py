#!/usr/bin/env python3
import logging
import paho.mqtt.client as mqtt
from ruamel.yaml import YAML


class YamlInterface:
    """Helper class for load and dump yaml files. Preserves comments and quotes.
    """
    def __init__(self, filename):
        self.filename = filename
        
        # create a ruamel.yaml object
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        
    def load(self):
        with open(self.filename, 'r') as f:
            data = self._yaml.load(f)
        return data
    
    def dump(self, data):
        with open(self.filename, 'w') as f:
            self._yaml.dump(data, f)
            

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
    def __init__(self, hostname, port, devicename, client_id, entities, on_message_callback=None):
        self.devicename = devicename     
        self._entities = entities
        self._on_message_callback = on_message_callback
        for entity in entities.values():
            entity.update({"value_updated": False})
        self.client = mqtt.Client(client_id=client_id)
        self.client._on_connect = self._on_connect
        self.client._on_message = self._on_message
        self.client.will_set(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)

        mqtt_auth = YamlInterface(filename='secrets.yaml').load()['mqtt_auth']
        self.client.username_pw_set(mqtt_auth['user'], mqtt_auth['password'])
        del mqtt_auth

        self.client.connect(hostname, port)
        self.client.loop_start()
    

    def exit(self):
        logging.info('Exiting MQTT thread and running cleanup code')
        self.client.publish(f'homeassistant/sensor/{self.devicename}/availability', 'offline', retain=True)
        self.client.disconnect()
        self.client.loop_stop()

 
    def publish_updates(self, publish_all=False):
        for type_ in ("sensor", "switch", "number"):
            any_update = False
            payload = '{'
            for entity, attr in self._entities.items():
                if attr["type"] == type_:
                    if publish_all or attr["value_updated"]:
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
            self._publish_config()
            self.client.subscribe(f"homeassistant/sensor/{self.devicename}/command") #subscribe
            for entity, attrs in self._entities.items():
                if attrs["type"] in ("switch", "number"):
                    self.client.subscribe(f"homeassistant/{attrs['type']}/{self.devicename}/{entity}")  # subscribe to setters
            self.client.publish(f"homeassistant/sensor/{self.devicename}/command", "setup", retain=True)
            self.publish_updates(publish_all=True)  # send initial sensor values
            
        elif rc == 5:
            logging.info('Authentication failed. Exiting...')
            self.exit()
        else:
            logging.info(f'Connection failed with return code {rc}.')
            self.exit()
            

    def _on_message(self, client, userdata, message):
        def try_int_float_conversion(value):
            if isinstance(value, str):
                if value.isnumeric():
                    return(int(value))
                try:
                    return(float(value))
                except ValueError:
                    pass         
            return value
           
        msg = try_int_float_conversion(message.payload.decode())
        logging.debug(f"Message received: topic='{message.topic}', message='{msg}'")
        entity = str(message.topic).split("/")[-1]
        if entity in self._entities:
            if self._on_message_callback is not None:
                self._on_message_callback(entity, msg)
            else:
                logging.info(f"No on_message_callback defined, entity={entity}, message={msg}.")         
        elif msg == 'online':
            logging.debug("reconfiguring")
            self._publish_config()