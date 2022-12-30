sensors = {
          'hostname':
                {'name': 'Hostname',
                 'icon': 'card-account-details',
                 'function': ""},
          'host_ip':
                {'name': 'Host IP',
                 'icon': 'lan',
                 'function': ""},
          'wifi_strength':
                {"device_class": 'signal_strength',
                 'state_class':'measurement',
                 'name':'Wifi Strength',
                 'unit': 'dBm',
                 'icon': 'wifi',
                 'function': ""},
          'temperature':
                {'name':'Temperature',
                 'device_class': 'temperature',
		         'state_class':'measurement',
                 'unit': '°C',
                 'icon': 'thermometer',
                 'function': ""},
          }


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

devicename = "walli13"
for sensor, attr in sensors.items():
    print(sensor)
    topic, payload = make_config_message(devicename, sensor, attr)
    print(topic)
    print(type(payload), payload)
    print()