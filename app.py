# -*- coding: utf-8 -*-

import json, math, os, pickle, threading, time
import pandas as pd
import numpy as np
import datetime as dt
from sensors import SensorInterface, create_logger

# 
# logger = create_logger()
# 
# 
# class WalliStat(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     datetime = db.Column(db.DateTime)
#     charging_state = db.Column(db.Integer) 
#     I_L1 = db.Column(db.Float)
#     I_L2 = db.Column(db.Float)
#     I_L3 = db.Column(db.Float)
#     temperature = db.Column(db.Float)
#     V_L1 = db.Column(db.Integer)
#     V_L2 = db.Column(db.Integer)
#     V_L3 = db.Column(db.Integer)
#     extern_lock_state = db.Column(db.Integer)
#     power_kW = db.Column(db.Float)
#     energy_pwr_on = db.Column(db.Float)
#     energy_kWh = db.Column(db.Float)
#     I_max_cfg = db.Column(db.Integer)
#     I_min_cfg = db.Column(db.Integer)
#     modbus_watchdog_timeout = db.Column(db.Integer)
#     remote_lock = db.Column(db.Integer)
#     I_max_cmd = db.Column(db.Float)
#     I_fail_safe = db.Column(db.Float)
#     campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'))
#     
#     def __repr__(self):
#         return f"WalliStat(id:{self.id}-->campaign.id:{self.campaign_id}, {self.datetime}: {self.temperature}°C, {self.power_kW}kW)"
# 
#     @classmethod
#     def from_series(cls, series):
#         """ Creates a WalliStat from a Pandas Series """
#         try:
#             ws = cls(datetime = series.datetime,
#                     charging_state = int(series.charge_state), 
#                     I_L1 = series.I_L1 / 10.,
#                     I_L2 = series.I_L2 / 10.,
#                     I_L3 = series.I_L3 / 10.,
#                     temperature = series.Temp / 10.,
#                     V_L1 = int(series.V_L1),
#                     V_L2 = int(series.V_L2),
#                     V_L3 = int(series.V_L3),
#                     extern_lock_state = int(series.ext_lock),
#                     power_kW = series.P / 1000.,
#                     energy_pwr_on = ((int(series.E_cyc_hb) << 16) + series.E_cyc_lb) / 1000.,
#                     energy_kWh = ((int(series.E_hb) << 16) + series.E_lb) / 1000.,
#                     I_max_cfg = int(series.I_max),
#                     I_min_cfg = int(series.I_max),
#                     modbus_watchdog_timeout = int(series.watchdog),
#                     remote_lock = int(series.remote_lock),
#                     I_max_cmd = series.max_I_cmd / 10.,
#                     I_fail_safe = series.FailSafe_I / 10., 
#                     campaign_id = int(series.campaign_id))
#             return ws
#         
#         except Exception as e:
#             print("Exception:", e, series.datetime)
#             return cls(datetime = series.datetime)
# 
# 
#         
#     def to_series(self):
#         """ Converts a WalliStat object into a Pandas Series """
#         keys = ["id", "datetime", "charging_state", "I_L1", "I_L2", "I_L3", "temperature", "V_L1", "V_L2", "V_L3", 
#                 "extern_lock_state", "power_kW", "energy_pwr_on", "energy_kWh", "I_max_cfg", "I_min_cfg", 
#                 "modbus_watchdog_timeout", "remote_lock", "I_max_cmd", "I_fail_safe", "campaign_id"]       
#         return pd.Series({key: getattr(self, key) for key in keys})
#      
#      
#     def to_dict(self):
#          return self.to_series().to_dict()
     
    

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