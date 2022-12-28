import time
from sensors import Wallbox


if __name__ == "__main__":
    wb = Wallbox()
    task = {"sensor": "walli", "func": "capture", "callback": print}
    wb.task_queue.put_nowait(task)
    time.sleep(1)
    wb.exit()
