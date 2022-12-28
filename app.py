import logging, time, yaml
from wallbox import Wallbox

SETTINGS = 'settings.yaml'

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    level=logging.INFO)


if __name__ == "__main__":
    with open(SETTINGS, 'r') as f:
        settings = yaml.safe_load(f)
    
    wb = Wallbox(port=settings["modbus"]["PORT"],
                 bus_id=settings["modbus"]["BUS_ID"],
                 max_read_attempts=settings["modbus"]["MAX_READ_ATTEMPTS"])
    
    try:
        while True:
            task = {"func": "capture", "callback": print}
            wb.task_queue.put_nowait(task)
            time.sleep(settings["update_interval"])
    
    except KeyboardInterrupt as e:
        logging.info(e)
    
    logging.info("exiting main")
    wb.exit()
