import logging, threading, time
from pymodbus.client.sync import ModbusSerialClient
from queue import Queue


class ModbusReadError(Exception):
    pass

class Wallbox(threading.Thread):
    """ Heidelberg Wallbox Energy Control
    """
    def __init__(self, port, bus_id, max_read_attempts, auto_connect=True):
        super().__init__()
        self.port = port                # Serial port of Modbus interface
        self.bus_id = bus_id            # Modbus ID
        self.max_read_attempts = max_read_attempts   # Max number of attempts for a Modbus read
        self.connected = False
        self.exiting = False
        self.task_queue = Queue(maxsize=10)
        self.start()     
        if auto_connect:
            self.task_queue.put_nowait({"func": "connect"})   


    def run(self):
        logging.info("Wallbox modbus thread started'")
        while not self.exiting:
            time.sleep(0.01)    # don't go crazy timer
            while not self.task_queue.empty():
                try:
                    task = self.task_queue.get()
                except Exception as e:
                    logging.error(f"task {task} caused {e}")
                    
                func = getattr(self, task["func"])
                if "kwargs" in task.keys():
                    kwargs = task["kwargs"]
                else:
                    kwargs = {}
                
                try:
                    func(**kwargs)
                except Exception as e:
                    logging.error(f"task {task} caused '{e}'")
                    task["callback"]({"rc": f"Exception during {task}"})
                    continue
                
                if "callback" in task:
                    try: 
                        task["callback"]()
                    except Exception as e:
                        logging.error(e)
                    
        logging.info("Wallbox thread ist exiting")
        
        
    def connect(self, ): 
        self.mb = ModbusSerialClient(method="rtu",
                                        port=self.port,
                                        baudrate=19200,
                                        stopbits=1,
                                        bytesize=8,
                                        parity="E",
                                        timeout=10)

        if not self.mb.connect():
            raise ModbusReadError('Could not connect to the wallbox')       
             
        self.connected = True
        logging.debug(f"Modbus connected")


    def capture(self):
        # step 1: Read registers raw
        read_attempts = 0
        regs = []
        funcs = [lambda: self.mb.read_input_registers(4, count=15, unit=self.bus_id),
                 lambda: self.mb.read_input_registers(100, count=2, unit=self.bus_id),
                 lambda: self.mb.read_holding_registers(257, count=3, unit=self.bus_id),
                 lambda: self.mb.read_holding_registers(261, count=2, unit=self.bus_id)]
        for func in funcs:
            while True:
                r = func()
                if r.isError():
                    read_attempts += 1
                    if read_attempts > self.max_read_attempts:
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
            "modbus_watchdog_timeout": raw["watchdog"] / 1000.,
            "remote_lock": int(raw["remote_lock"]),
            "I_max_cmd": raw["max_I_cmd"] / 10.,
            "I_fail_safe": raw["FailSafe_I"] / 10., 
        }
        return dct
        
        
    def write(self, entity, value):
        if entity == "modbus_watchdog_timeout":
            adr, val = 257, int(value * 1000)
        elif entity == "remote_lock":
            adr, val = 259, value
        elif entity == "I_max_cmd":
            adr, val = 261, int(value * 10)
        elif entity == "I_fail_safe":
            adr, val = 262, int(value * 10)
        else:
            logging.error(f"Unknown entity {entity} with value {value}")
        self._reg_write(adr, val)
            
        
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
                    r = read_func(int(adr), count=1, unit=self.bus_id)
                    if r.isError():
                        read_attempts += 1
                        if read_attempts > self.max_read_attempts:
                            raise ModbusReadError
                    else:
                        vals.append((adr, r.registers[0]))
                        break            
        
        return {"reg_read": vals}
    

    def _reg_write(self, adr: str, val: int):
        self.mb.write_register(int(adr), int(val), unit=self.bus_id)       
    

    def exit(self):
        self.mb.close()
        self.exiting = True
