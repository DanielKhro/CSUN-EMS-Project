# Data Folder Log
This file is used to track the descriptions of the data that is used for training any algorithm.
When a dataset is modified for use, a copy of the modified data should be uploaded to this folder and the changes made recorded below.
This will make it easier for progress to be tracked and reverted if necessary, as it is much more difficult to update a long csv file than it is to upload a new copy.

**Added 9/2/26:** `Household_energy_consumption_w_weather_data.zip`

Contains data taken directly from https://www.kaggle.com/datasets/orvile/household-energy-consumption-with-weather-data/data .
No changes made to the data.

**Added 9/4/26:** `Energy_weather_090426.zip`

Contains certain columns from the previous file: date, active power, current, voltage, apparent power, power factor, temperature, "feels like" temperature, minimum temperature, maximum temperature, and humidity.

**Added 9/7/26:** `Energy_weather_090726.csv`

Contains data from previous file but downsampled to 15 minute intervals. Leading rows have been removed to ensure data is in 15 minute increments.

**Added 9/8/26:** `Energy_weather_090826.csv`

Contains data from `Energy_weather_090426.zip` but with NaN values filled using interpolation, then resampled to 15 minute increments.

**Added 9/9/26:** `Energy_weather_090926.csv`

Contains data from `Energy_weather_090826.csv` with only date and active power data columns, with added calculated dew point temperature data.
The script used to edit and plot this data was `data_plotting.m`.

**Added 10/20/26:**
`CSV Editing File 1.p` has been edited to remove outliers, defined as a value that has a z score more than 3 within a 60 minute window.
`energy_weather_102026_1.csv` is the original file (`Energy_weather_090426.zip`), with outliers removed, resampled to 15 minute increments.
`energy_weather_102026_2.csv` is the previous file with extraneous data removed.
`energy_weather_102026_3.csv` is the previous file with time data added.
