#CSV Editing File 1
# Victor Baron
# 09/07/226
# The purpose of this file is to downsample an existing csv file into 15 minute buckets

import pandas as pd #Using pandas library
df = pd.read_csv('energy_weather_090326.csv', index_col='date', parse_dates=True) #Load csv
#data = df.head(n=17)
#print(data)

#Need to delete lines 0 to 10
Time_to_drop = ["2022-11-05 14:05:00", "2022-11-05 14:06:00", "2022-11-05 14:07:00", "2022-11-05 14:08:00", "2022-11-05 14:09:00",
         "2022-11-05 14:10:00", "2022-11-05 14:11:00", "2022-11-05 14:12:00", "2022-11-05 14:13:00", "2022-11-05 14:14:00"] #List of timestamps in string format
Timestamp_list = [] #empty list
#Iterate through list of strings and convert each one to timestamp
for x in Time_to_drop:
    y = pd.Timestamp(x)
    Timestamp_list.append(y)
#use timestampt to drop indexes
df.drop(Timestamp_list, inplace = True)
#print(df.head())


#Resample to 15 minute intervals
df = df.resample('15min', label = 'right',origin = "start").mean()
print(df.head(n = 10))

#Save dataframe as csv
df.to_csv("energy_weather_090726.csv", index_label='date')