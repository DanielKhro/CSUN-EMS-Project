#Adding New Features
import pandas as pd
import time as datetime
import numpy as np
df = pd.read_csv('energy_weather_090926.csv', index_col='date', parse_dates=True) #Load csv

#Get datetime column
dates = df.index.values.tolist()

dates_week = []
dates_days = []
dates_hours = []
dates_min = []

print(dates[50])
print(type(dates[50]))

for i in dates:
    dates_week.append(i.isocalendar().week)
    dates_days.append(i.weekday())
    dates_hours.append(i.hour)
    dates_min.append(i.minute)

print(dates[50])
print(dates_week[50])
print(dates_days[50])
print(dates_hours[50])
print(dates_min[50])

print(dates[2066])
print(dates_week[2066])
print(dates_days[2066])
print(dates_hours[2066])
print(dates_min[2066])


# print(dates[150])
# print(dates_days[150])
# print(dates_hours[150])

# days_sin = []
# days_cos = []

# for i in dates_days:
#     days_sin.append(np.sin(i*2.*np.pi/7))
#     days_cos.append(np.cos(i*2.*np.pi/7))

# hr_sin = []
# hr_cos = []

# for i in dates_hours:
#     hr_sin.append(np.sin(i*2.*np.pi/24))
#     hr_cos.append(np.cos(i*2.*np.pi/24))

# print(days_sin[50])
# print(hr_sin[50])

# df["day_sin"] = days_sin
# df["day_cos"] = days_cos
# df["hr_sin"] = hr_sin
# df["hr_cos"] = hr_cos

df["week"] = dates_week
df["dayOfWeek"] = dates_days
df["hour"] = dates_hours
df["minute"] = dates_min


print(df.head())
print(df.tail())

df.to_csv("energy_weather_101026.csv", index_label='date')
