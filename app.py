# -*- coding: utf-8 -*-
from sensors import SensorInterface, create_logger


logger = create_logger()


if __name__ == "__main__":    
    sensor_interface = SensorInterface()
    task = {"sensor": "walli", 
            "func": "capture", 
            "callback": print}
    sensor_interface.do_task(task)
    task = {"sensor": "light", 
            "func": "capture", 
            "callback": print}
    sensor_interface.do_task(task)
    
    sensor_interface.exit()