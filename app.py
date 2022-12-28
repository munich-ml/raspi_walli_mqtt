import time, yaml
from wallbox import Wallbox

SETTINGS = 'settings.yaml'

if __name__ == "__main__":
    with open(SETTINGS, 'r') as f:
        settings = yaml.safe_load(f)
    wb = Wallbox()
    task = {"func": "capture", "callback": print}
    wb.task_queue.put_nowait(task)
    time.sleep(1)
    wb.exit()
