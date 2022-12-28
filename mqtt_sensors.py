#!/usr/bin/env python3
import argparse, sys, threading, time, yaml
import paho.mqtt.client as mqtt
import datetime as dt
from sensors import sensors


mqttClient = None
devicename = None
settings = {}


def print_w_flush(message):
    print(message)
    sys.stdout.flush()
    
    
class Job(threading.Thread):
    def __init__(self, interval, execute, *args, **kwargs):
        threading.Thread.__init__(self)
        self.daemon = False
        self.stopped = threading.Event()
        self.interval = interval
        self.execute = execute
        self.args = args
        self.kwargs = kwargs

    def stop(self):
        self.stopped.set()
        self.join()

    def run(self):
        while not self.stopped.wait(self.interval.total_seconds()):
            self.execute(*self.args, **self.kwargs)


def update_sensors():
    payload = '{'
    for sensor, attr in sensors.items():        
        payload += f'"{sensor}": "{attr["function"]()}",'
    payload = payload[:-1] + '}'
    topic = f'homeassistant/sensor/{devicename}/state'
    pub_ret = mqttClient.publish(topic=topic, payload=payload, qos=1, retain=False)
    print(f"{pub_ret} from publish(topic={topic}, payload={payload})")


def send_config_message(mqttClient):

    print_w_flush('Sending config message to host...')

    for sensor, attr in sensors.items():
        try:
            topic = f'homeassistant/{attr["sensor_type"]}/{devicename}/{sensor}/config'
            payload =  f'{{'
            payload += f'"device_class":"{attr["device_class"]}",' if 'device_class' in attr else ''
            payload += f'"state_class":"{attr["state_class"]}",' if 'state_class' in attr else ''
            payload += f'"name":"{devicename} {attr["name"]}",'
            payload += f'"state_topic":"homeassistant/sensor/{devicename}/state",'
            payload += f'"unit_of_measurement":"{attr["unit"]}",' if 'unit' in attr else ''
            payload += f'"value_template":"{{{{value_json.{sensor}}}}}",'
            payload += f'"unique_id":"{devicename}_{attr["sensor_type"]}_{sensor}",'
            payload += f'"availability_topic":"homeassistant/sensor/{devicename}/availability",'
            payload += f'"device":{{"identifiers":["{devicename}_sensor"],'
            payload += f'"name":"{devicename}"}}'
            payload += f',"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else ''
            payload += f',{attr["prop"]}' if 'prop' in attr else ''
            payload += f'}}'    
                            
            print("publish topic=", topic)
            print("publish payload=", payload)           
            mqttClient.publish(topic=topic, payload=payload, qos=1, retain=True)
        except Exception as e:
            print_w_flush('An error was produced while processing ' + str(sensor) + ' with exception: ' + str(e))
            print(str(settings))
            raise
        
    mqttClient.publish(f'homeassistant/sensor/{devicename}/availability', 'online', retain=True)


def _parser():
    """Generate argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument('settings', help='path to the settings file')
    return parser


def check_settings(settings):
    for value in ['mqtt', 'timezone', 'devicename', 'client_id', 'update_interval']:
        if value not in settings:
            print_w_flush(value + ' not defined in settings.yaml! Please check the documentation')
            sys.exit()
    if 'hostname' not in settings['mqtt']:
        print_w_flush('hostname not defined in settings.yaml! Please check the documentation')
        sys.exit()
    if 'user' in settings['mqtt'] and 'password' not in settings['mqtt']:
        print_w_flush('password not defined in settings.yaml! Please check the documentation')
        sys.exit()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print_w_flush('Connected to broker')
        print("subscribing : hass/status")
        client.subscribe('hass/status')
        print("subscribing : " + f"homeassistant/sensor/{devicename}/availability")
        mqttClient.publish(f'homeassistant/sensor/{devicename}/availability', 'online', retain=True)
        print("subscribing : " + f"homeassistant/sensor/{devicename}/command")
        client.subscribe(f"homeassistant/sensor/{devicename}/command") #subscribe
        client.subscribe("homeassistant/sensor/to_wallbox")
        client.publish(f"homeassistant/sensor/{devicename}/command", "setup", retain=True)
    elif rc == 5:
        print_w_flush('Authentication failed.\n Exiting.')
        sys.exit()
    else:
        print_w_flush('Connection failed')


def on_message(client, userdata, message):
    print (f'Message received: {message.payload.decode()} userdata={userdata}')
    if message.payload.decode() == 'online':
        send_config_message(client)


if __name__ == '__main__':
    try:
        args = _parser().parse_args()
        settings_file = args.settings
    except:
        print_w_flush('Could not find settings.yaml. Please check the documentation')
        exit()

    with open(settings_file) as f:
        settings = yaml.safe_load(f)

    # Make settings file keys all lowercase
    settings = {k.lower(): v for k,v in settings.items()}
    # Check for settings that will prevent the script from communicating with MQTT broker or break the script
    check_settings(settings)

    devicename = settings['devicename'].replace(' ', '').lower()   
    
    mqttClient = mqtt.Client(client_id=settings['client_id'])
    mqttClient.on_connect = on_connect                      #attach function to callback
    mqttClient.on_message = on_message
    mqttClient.will_set(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)
    
    print("warning: secrets")
    with open('secrets.yaml', 'r') as f:
        mqtt_auth = yaml.safe_load(f)['mqtt_auth']
        mqttClient.username_pw_set(mqtt_auth['user'], mqtt_auth['password'])
        del mqtt_auth


    while True:
        try:
            mqttClient.connect(settings['mqtt']['hostname'], settings['mqtt']['port'])
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
    try:
        send_config_message(mqttClient)
    except Exception as e:
        print_w_flush('Error while attempting to send config to MQTT host: ' + str(e))
        exit()
    try:
        update_sensors()
    except Exception as e:
        print_w_flush('Error while attempting to perform inital sensor update: ' + str(e))
        exit()

    job = Job(interval=dt.timedelta(seconds=settings["update_interval"]), execute=update_sensors)
    job.start()

    mqttClient.loop_start()

    while True:
        try:
            sys.stdout.flush()
            time.sleep(1)
        except KeyboardInterrupt:
            print_w_flush('Program killed: running cleanup code')
            mqttClient.publish(f'homeassistant/sensor/{devicename}/availability', 'offline', retain=True)
            mqttClient.disconnect()
            mqttClient.loop_stop()
            sys.stdout.flush()
            job.stop()
            break