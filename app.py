import logging, math, threading, time
from mqtt_device import MqttDevice, YamlInterface
from wallbox import Wallbox

SETTINGS = 'settings.yaml'
ENTITIES = 'entities.yaml'

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    level=logging.INFO)

class CaptureTimer:
    def __init__(self, interval, function):
        self.__interval = interval
        self.__function = function
        self.__start_timer()
        
    def update_interval(self, interval):
        self.__interval = interval
        self.__timer.cancel()
        self.__timer.join()
        self.__start_timer()
        
    def exit(self):
        self.__timer.cancel()
        self.__timer.join()        
        
    def __start_timer(self):
        now = time.time()
        sleep_time = math.ceil(now / self.__interval) * self.__interval - now        
        self.__timer = threading.Timer(sleep_time, self.__timer_expired)
        self.__timer.start()  
    
    def __timer_expired(self):
        self.__function()     # execute timer function
        self.__start_timer()  # schedule the next timer
        

if __name__ == "__main__":
    yaml_settings = YamlInterface(SETTINGS)
    settings = yaml_settings.load()

    entities = YamlInterface(ENTITIES).load()
    
    def on_message_callback(entity, message):
        logging.info(f"{entity}, {message}")
        mqtt.set_states({entity: message})
        mqtt.publish_updates()  # send confirmation to homeassistant 
    
    mqtt = MqttDevice(hostname=settings['mqtt']['hostname'], 
                        port=settings['mqtt']['port'], 
                        devicename=settings["devicename"], 
                        client_id=settings['client_id'],
                        entities=entities,
                        on_message_callback=on_message_callback)    
    
    wb = Wallbox(port=settings["modbus"]["PORT"],
                 bus_id=settings["modbus"]["BUS_ID"],
                 max_read_attempts=settings["modbus"]["MAX_READ_ATTEMPTS"])
    
    
    def after_capture(data: dict):
        """Callback function executed after wallbox capture to process the return data.
        """
        logging.debug("after capture: " + str(data))
        mqtt.set_states(data)
        mqtt.publish_updates()
        
    
    def do_capture():
        task = {"func": "capture", "callback": after_capture}
        wb.task_queue.put_nowait(task)

    timer = CaptureTimer(settings["update_interval"], do_capture)
    
    try:
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        pass
    
    wb.exit()
    mqtt.exit()
    timer.exit()
    logging.info("exiting main")
    