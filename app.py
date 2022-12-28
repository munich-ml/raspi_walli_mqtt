import time, yaml
from wallbox import Wallbox

SETTINGS = 'settings.yaml'

if __name__ == "__main__":
    with open(SETTINGS, 'r') as f:
        settings = yaml.safe_load(f)
    
    wb = Wallbox(port=settings["modbus"]["PORT"],
                 bus_id=settings["modbus"]["BUS_ID"],
                 max_read_attempts=settings["modbus"]["MAX_READ_ATTEMPTS"])
    
    task = {"func": "capture", "callback": print}
    wb.task_queue.put_nowait(task)
    time.sleep(1)
    wb.exit()
