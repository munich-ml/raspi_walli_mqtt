#!/usr/bin/env python3
import yaml, time, logging
from mqtt_device import MqttDevice

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    level=logging.INFO)

if __name__ == '__main__':
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
                new_temperature = round(stat["temperature"] + delta * FOLLOW_RATE, 1)
                device.set_states({"temperature": new_temperature})
                device.publish_updates()
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    
    device.exit()
    logging.info("exiting main")