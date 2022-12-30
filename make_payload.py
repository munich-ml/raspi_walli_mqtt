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


from mqtt_sensors import make_config_message

devicename = "walli13"
for sensor, attr in sensors.items():
    print(sensor)
    topic, payload = make_config_message(devicename, sensor, attr)
    print(topic)
    print(payload)
    print()