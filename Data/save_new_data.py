import datetime as dt
import pandas as pd
import weather_data_aquis as weather

def get_current_time():
    now = dt.datetime.now()
    now = pd.Timestamp(now)
    now = now.floor('15min')
    return now

def get_current_power():
    #Placeholder
    #Needs current power data from PZEM
    power = 500
    return 500


def add_time_data(time_val):
    new_vals = []
    new_vals.append(time_val.isocalendar().week)
    new_vals.append(time_val.weekday())
    new_vals.append(time_val.hour)
    new_vals.append(time_val.minute)
    return new_vals

def add_to_csv(array_vals):
    df = pd.DataFrame([array_vals])
    df.to_csv('log.csv', mode='a', index=False, header=False)

def create_row():
    NOW_TIME = get_current_time()
    NOW_POW = get_current_power()
    NOW_VALS = add_time_data(NOW_TIME)
    NOW_DEW = weather.get_dewPoint()
    full_array = [NOW_TIME, NOW_POW, NOW_DEW]
    full_array = full_array+ NOW_VALS
    add_to_csv(full_array)

create_row()