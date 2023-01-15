import logging, math, threading, time
from mqtt_device import MqttDevice, YamlInterface
from wallbox import Wallbox

SETTINGS = 'settings.yaml'
ENTITIES = 'entities.yaml'

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    handlers=[logging.FileHandler("logging.txt"), logging.StreamHandler(),],
                    level=logging.INFO)

class CaptureTimer:
    def __init__(self, interval, function):
        self.__interval = int(interval)
        self.__function = function
        self.__start_timer()
        
    def update_interval(self, interval):
        self.__interval = int(interval)
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
    def do_capture():
        """Puts a capture task into the wallbox task queue. 
        """
        task = {"func": "capture", "callback": after_capture}
        wb.task_queue.put_nowait(task)


    def after_capture(data: dict):
        """Callback function executed after wallbox capture to process the return data.
        """
        # load yaml entities (e.g. for polling_interval)
        entities = {e: v["value"] for e, v in entities_interface.load().items()}  
        
        # update yaml entities with the values from the Wallbox read
        entities.update(data) 
        
        mqtt.set_states(entities)
        mqtt.publish_updates()
        logging.debug(f"after capture: {entities}")
        
    
    def do_write(entity, value):
        """Puts a write task into the wallbox task queue. 
        """
        logging.info(f"entity={entity}, value={value}")
        if entity in wb.WRITEABLE_REGS:   # for entities within the Wallbox
            task = {"func": "write", "callback": after_write, 
                    "kwargs": {"entity": entity, "value": value}}
            wb.task_queue.put_nowait(task)        
            
        else:                             # for entities within this app
            if entity == "polling_interval":   # periodic polling
                entities = entities_interface.load()
                entities[entity]["value"] = value
                entities_interface.dump(entities)
                timer.update_interval(value)
                after_write()
            elif entity == "polling_request":   # manual polling
                do_capture()

    
    def after_write(return_value=None):
        """Callback function executed after wallbox capture to process the return data.
        """
        time.sleep(0.2)  # wait a little to allow the wallbox doing the changes
        do_capture()


    entities_interface = YamlInterface(ENTITIES)
    settings_interface = YamlInterface(SETTINGS)
    settings = settings_interface.load()
    mqtt = MqttDevice(entities=entities_interface.load(), on_message_callback=do_write,
                      **settings['mqtt'])    
    wb = Wallbox(**settings["modbus"])
    timer = CaptureTimer(interval=entities_interface.load()["polling_interval"]["value"], 
                         function=do_capture)
        
    try:
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        pass
    
    wb.exit()
    mqtt.exit()
    timer.exit()
    logging.info("exiting main")
    