import logging, random, threading, time
import datetime as dt
from pymodbus.client.sync import ModbusSerialClient
from smbus import SMBus
from queue import Queue

PORT = '/dev/ttyAMA0'              # Serial port of Modbus interface
BUS_ID = 1                         # Modbus ID
MAX_READ_ATTEMPTS = 8              # Max number of attempts for a Modbus read


# configure logging
def create_logger(fn='logging.txt', level_file_logger=logging.INFO, level_stream_logger=logging.INFO):
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)

    # create file handler and stream handler
    handlers = [{"handler": lambda: logging.FileHandler(fn), 
                 "level": level_file_logger,
                 "formatter": logging.Formatter('%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s thread=%(thread)s | %(message)s')},
                {"handler": logging.StreamHandler, 
                 "level": level_stream_logger,
                 "formatter": logging.Formatter('%(levelname)-8s | %(message)s')},            
               ]
    for h in handlers:
        handler = h["handler"]()
        handler.setLevel(h["level"])
        handler.setFormatter(h["formatter"])
        logger.addHandler(handler)
  
    return logger

logger = create_logger()

class SensorBase(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connected = False
        self.exiting = False
        self.task_queue = Queue(maxsize=10)
        self.start()
        
    def __repr__(self):
        connected = {True: "connected", False: "not connected"}[self.connected]
        return f"{self.type}, {connected}"
        
    def connect(self):
        """ connect function to be implemented in sensor subclass """
        raise NotImplementedError()
        
    def capture(self):
        """ capture function to be implemented in sensor subclass """
        raise NotImplementedError()
    
    def exit(self):
        self.exiting = True
    
    def run(self):
        logger.info(f"Sensor thread started for '{self.type}'")
        while not self.exiting:
            time.sleep(0.01)    # don't go crazy timer
            while not self.task_queue.empty():
                try:
                    task = self.task_queue.get()
                except Exception as e:
                    logger.error(f"task {task} caused {e}")
                    
                func = getattr(self, task["func"])
                if "kwargs" in task.keys():
                    kwargs = task["kwargs"]
                else:
                    kwargs = {}
                
                try:
                    return_dct = func(**kwargs)
                except Exception as e:
                    logger.error(f"task {task} caused {e}")
                    task["callback"]({"rc": f"Exception during {task}"})
                    continue
                
                if "callback" in task:
                    try: 
                        task["callback"](return_dct)
                    except Exception as e:
                        logger.error(e)
                    
        logger.info(f"Sensor thread exiting for '{self.type}'")


class LightSensor(SensorBase):
    """ BH1750 digital light sensor 
    """ 
    def __init__(self, *args, **kwargs):
        self.type = "LightSensor BH1570"
        super().__init__(*args, **kwargs)
        
    def connect(self):
        self.sensor = SMBus(1)  # Rev 2 Pi uses 1
        self.connected = True
        logger.debug(f"{self.type} connected")
        
    def capture(self):
        """ Returns light level in Lux
        """
        I2C_BH1750 = 0x23
        ONE_TIME_HIGH_RES_MODE_1 = 0x20  
        d = self.sensor.read_i2c_block_data(I2C_BH1750, ONE_TIME_HIGH_RES_MODE_1)
        lux = (d[1] + (256 * d[0])) / 1.2
        return {"lux": lux}


class ModbusReadError(Exception):
    pass

class Wallbox(SensorBase):
    """ Heidelberg Wallbox Energy Control
    """
    def __init__(self, *args, **kwargs):
        self.type = "Heidelberg Wallbox Energy Control"
        super().__init__(*args, **kwargs)
        
    def connect(self, ): 
        self.mb = ModbusSerialClient(method="rtu",
                                        port=PORT,
                                        baudrate=19200,
                                        stopbits=1,
                                        bytesize=8,
                                        parity="E",
                                        timeout=10)

        if not self.mb.connect():
            raise ModbusReadError('Could not connect to the wallbox')       
             
        self.connected = True
        logger.debug(f"{self.type} connected")


    def capture(self):
        read_attempts = 0
        regs = []
        funcs = [lambda: self.mb.read_input_registers(4, count=15, unit=BUS_ID),
                    lambda: self.mb.read_input_registers(100, count=2, unit=BUS_ID),
                    lambda: self.mb.read_holding_registers(257, count=3, unit=BUS_ID),
                    lambda: self.mb.read_holding_registers(261, count=2, unit=BUS_ID),
                ]
        for func in funcs:
            while True:
                r = func()
                if r.isError():
                    read_attempts += 1
                    if read_attempts > MAX_READ_ATTEMPTS:
                        raise ModbusReadError
                else:
                    regs.extend(r.registers)
                    break
        
        keys = ['ver', 'charge_state', 'I_L1', 'I_L2', 'I_L3', 'Temp', 'V_L1', 'V_L2', 
                'V_L3', 'ext_lock', 'P', 'E_cyc_hb', 'E_cyc_lb', 'E_hb', 'E_lb', 'I_max', 'I_min', 
                'watchdog', 'standby', 'remote_lock', 'max_I_cmd', 'FailSafe_I']
        dct = {k: v for k, v in zip(keys, regs)}
        return dct
        
        
    def _reg_read(self, input_regs: list, holding_regs: list) -> dict[str, list[tuple[str, int]]]:
        """Reads current data from the wallbox

        Args:
            input_regs (list): Register addresses of the input registers to be read
            holding_regs (list): Register addresses of the holding registers to be read

        Returns:
            dict[str, list[tuple[str, int]]]: (adr, value) tuples in a list in a dict with just one item
        """
        vals = []
        read_attempts = 0
        for regs, read_func in zip((input_regs, holding_regs),
                                   (self.mb.read_input_registers, self.mb.read_holding_registers)):
            for adr in regs:
                while True:
                    r = read_func(int(adr), count=1, unit=BUS_ID)
                    if r.isError():
                        read_attempts += 1
                        if read_attempts > MAX_READ_ATTEMPTS:
                            raise ModbusReadError
                    else:
                        vals.append((adr, r.registers[0]))
                        break            
        
        return {"reg_read": vals}
    

    def _reg_write(self, adr: str, val: int):
        self.mb.write_register(int(adr), int(val), unit=BUS_ID)       
        return {}
    

    def exit(self):
        """ Overwrite exit method of base class to support Modbus closing
        """
        self.mb.close()
        logger.info("in exit")
        super().exit()
        logger.info("after exit")


class SensorInterface(dict):
    """Container holding all sensors"""
    def __init__(self):
        self["light"] = LightSensor()
        self["walli"] = Wallbox()
        
        # connect all sensors
        for sensor in self.values():
            sensor.task_queue.put({"func": "connect"})
        
        logger.info("SensorInterface initialized")
        for key, value in self.items():
            logger.info(f"- '{key}': {value}")
        
    def do_task(self, task):
        """
        Executes a task 
        
        task is a <dict> with the items:
            "sensor": <str> sensor key like "light", "walli" or "cam"
            "func": <str> function key like "capture", "connect" or "exit"
            "campaign_id": <int> e.g. 42
            "callback": <func> callback function line process_return_data
        """
        sensor_key = task["sensor"]
        sensor = self[sensor_key]
        if sensor.task_queue.full():
            logger.warning(f"Queue is full! Skipping {task}")
        else:    
            sensor.task_queue.put(task, timeout=1)
        
