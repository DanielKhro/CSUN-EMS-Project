#CSV Editing File 1
# Victor Baron
# 09/07/226
# The purpose of this file is to downsample an existing csv file into 15 minute buckets

import pandas as pd #Using pandas library
import statistics as stats
import numpy as np
import matplotlib.pyplot as plt
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
df = df.interpolate()

contains_nan = df.isnull().values.any()
print(contains_nan)

window_size = 60 #Takes into account past 60 minutes
i = 0

while i < df.index.size - window_size + 1:
    # Store elements from i to i+window_size
    # in list to get the current window
    #[i : i + window_size],[0]
    rows = list(range(i,i+window_size))
    window = df.iloc[rows,[0]].to_numpy()
    mean_window = np.nanmean(window)
    dev_window = np.nanstd(window)

    #Compare the values in the window range 
    #Using the data frame
    #Any that are greater than ( |x_t - MA_t| > k*MS_t 
    #Should be replaced by NaN
    j = 0

    for y in window:
        if (abs(y - mean_window)) > 3*dev_window:
            df.iloc[[i+j],[0]] = np.nan
        j = j + 1

    print(i)
    
    i = i + 1
    

df = df.ffill()

contains_nan = df.isnull().values.any()
print(contains_nan)


#Resample to 15 minute intervals
df = df.resample('15min', label = 'right',origin = "start").mean()
print(df.head(n = 10))
print(df.tail())

#Save dataframe as csv
df.to_csv("energy_weather_102026_1.csv", index_label='date')