#!/usr/bin/env python3
import yaml, time, logging
from mqtt_device import MqttDevice, YamlInterface

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    level=logging.INFO)

if __name__ == '__main__':
    yaml_settings = YamlInterface(filename="settings.yaml")
    settings = yaml_settings.load()

    yaml_entities = YamlInterface(filename='entities_temp_controller.yaml')
    entities = yaml_entities.load()
    
    def on_message_callback(entity, message):
        device.set_states({entity: message})
        device.publish_updates()  # send confirmation to homeassistant 
    
    device = MqttDevice(hostname=settings['mqtt']['hostname'], 
                        port=settings['mqtt']['port'], 
                        devicename=settings["devicename"], 
                        client_id=settings['client_id'],
                        entities=entities,
                        on_message_callback=on_message_callback)
    
    FOLLOW_RATE = 0.1
    PUBLISH_ALL_INTERVAL = 10
    last_publish = time.time()
    try:
        while True:
            if time.time() > last_publish + PUBLISH_ALL_INTERVAL:
                last_publish = time.time()
                device.publish_updates()
                
            stat = device.get_states()
            if stat["power_switch"] == "ON":
                delta = stat["set_temperature"] - stat["temperature"]
                new_temperature = round(stat["temperature"] + delta * FOLLOW_RATE, 1)
                device.set_states({"temperature": new_temperature})
                device.publish_updates()
            time.sleep(1)
            
    except KeyboardInterrupt:
        pass
    
    device.exit()
    logging.info("exiting main")