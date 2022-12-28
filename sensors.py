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



class ModbusReadError(Exception):
    pass

class Wallbox(threading.Thread):
    """ Heidelberg Wallbox Energy Control
    """
    SENSORX = {
            "charging_state": 
                {'name': 'charging state',
                'state_class': 'measurement',
                'icon': 'mdi:state-machine'}, 
            
            "I_L1": 
                {'name': 'L1 current',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:current-ac'}, 
            
            "I_L2": 
                {'name': 'L2 current',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:current-ac'}, 
            
            "I_L3": 
                {'name': 'L3 current',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:current-ac'}, 
            
            "temperature": 
                {'name': 'PCB temperature',
                'device_class': 'temperature',
                'unit': '°C',
                'state_class': 'measurement',
                'icon': 'mdi:thermometer'}, 
            
            "V_L1": 
                {'name': 'L1 voltage',
                'device_class': 'voltage',
                'unit': 'V',
                'state_class': 'measurement',
                'icon': 'mdi:sine-wave'}, 
                        
            "V_L2": 
                {'name': 'L2 voltage',
                'device_class': 'voltage',
                'unit': 'V',
                'state_class': 'measurement',
                'icon': 'mdi:sine-wave'}, 
            
            "V_L3": 
                {'name': 'L3 voltage',
                'device_class': 'voltage',
                'unit': 'V',
                'state_class': 'measurement',
                'icon': 'mdi:sine-wave'}, 
            
            "extern_lock_state": 
                {'name': 'external lock state',
                'state_class': 'measurement',
                'icon': 'mdi:state-machine'}, 
            
            "power_kW": 
                {'name': 'charging power',
                'device_class': 'power',
                'unit': 'kW',
                'state_class': 'measurement',
                'icon': 'mdi:flash-triangle'}, 
        
            "energy_pwr_on": 
                {'name': 'energy since powerup',
                'device_class': 'power',
                'unit': 'kWh',
                'state_class': 'total',
                'icon': 'mdi:battery-charging-full'}, 
            
            "energy_kWh": 
                {'name': 'energy total',
                'device_class': 'power',
                'unit': 'kWh',
                'state_class': 'total',
                'icon': 'mdi:battery-charging-full'}, 
            
            "I_max_cfg": 
                {'name': 'max current HW config',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:current-ac'}, 
                        
            "I_min_cfg": 
                {'name': 'min current HW config',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:current-ac'}, 
                                    
            "modbus_watchdog_timeout": 
                {'name': 'ModBus watchdog timeout',
                'device_class': 'duration',
                'unit': 's',
                'state_class': 'measurement',
                'icon': 'mdi:timer-outline'}, 
                           
            "remote_lock": 
                {'name': 'remote lock',
                'state_class': 'measurement',
                'icon': 'mdi:lock-outline'}, 
                            
            "I_max_cmd": 
                {'name': 'max current command',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:sine-wave'}, 
            
            "I_fail_safe": 
                {'name': 'FailSafe current',
                'device_class': 'current',
                'unit': 'A',
                'state_class': 'measurement',
                'icon': 'mdi:sine-wave'}, 
        }
    
    def __init__(self, auto_connect=True):
        super().__init__()
        self.connected = False
        self.exiting = False
        self.task_queue = Queue(maxsize=10)
        self.start()     
        if auto_connect:
            self.task_queue.put_nowait({"func": "connect"})   


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
                    logger.error(f"task {task} caused '{e}'")
                    task["callback"]({"rc": f"Exception during {task}"})
                    continue
                
                if "callback" in task:
                    try: 
                        task["callback"](return_dct)
                    except Exception as e:
                        logger.error(e)
                    
        logger.info(f"Sensor thread exiting for '{self.type}'")
        
        
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
        # step 1: Read registers raw
        read_attempts = 0
        regs = []
        funcs = [lambda: self.mb.read_input_registers(4, count=15, unit=BUS_ID),
                 lambda: self.mb.read_input_registers(100, count=2, unit=BUS_ID),
                 lambda: self.mb.read_holding_registers(257, count=3, unit=BUS_ID),
                 lambda: self.mb.read_holding_registers(261, count=2, unit=BUS_ID)]
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
        raw = {k: v for k, v in zip(keys, regs)}
        
        # step 2: Preprocess registers
        dct = {
            "charging_state": int(raw["charge_state"]), 
            "I_L1": raw["I_L1"] / 10.,
            "I_L2": raw["I_L2"] / 10.,
            "I_L3": raw["I_L3"] / 10.,
            "temperature": raw["Temp"] / 10.,
            "V_L1": int(raw["V_L1"]),
            "V_L2": int(raw["V_L2"]),
            "V_L3": int(raw["V_L3"]),
            "extern_lock_state": int(raw["ext_lock"]),
            "power_kW": raw["P"] / 1000.,
            "energy_pwr_on": ((int(raw["E_cyc_hb"]) << 16) + raw["E_cyc_lb"]) / 1000.,
            "energy_kWh": ((int(raw["E_hb"]) << 16) + raw["E_lb"]) / 1000.,
            "I_max_cfg": int(raw["I_max"]),
            "I_min_cfg": int(raw["I_max"]),
            "modbus_watchdog_timeout": int(raw["watchdog"]),
            "remote_lock": int(raw["remote_lock"]),
            "I_max_cmd": raw["max_I_cmd"] / 10.,
            "I_fail_safe": raw["FailSafe_I"] / 10., 
        }
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
        self.mb.close()
        self.exiting = True
