# -*- coding: utf-8 -*-
from sensors import SensorInterface, logger



if __name__ == "__main__":    
    sensor_interface = SensorInterface()
    task = {"sensor": "walli", 
            "func": "capture", 
            "callback": print}
    sensor_interface.do_task(task)
    
    sensor_interface.exit()