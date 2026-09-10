clc, clear, close all
%%
%Read data from csv as a table
data = readtable("energy_weather_090826.csv");
%Extract temperature and humidity values for dew point calculation
temp_vec = table2array(data(:,"temp"));
humidity_vec = table2array(data(:, "humidity"));
power_vec = table2array(data(:, "active_power"));

%Read data as timetable
data_tt = readtimetable("energy_weather_090826.csv");

%Calculate dew point
b = 17.625;
c = 243.04;
gamma = log(humidity_vec./100) + (b.*temp_vec)./(temp_vec + c);
dew_point = (c*gamma)./(b - gamma);

%Add dew point as new column to time table
data_tt2 = addvars(data_tt, dew_point);

%Remove unneeded variables
data_tt3 = removevars(data_tt2, ["apparent_power", "current", "voltage", "power_factor","temp","feels_like","temp_min","temp_max","humidity"]);

%Write new timetable to csv
writetimetable(data_tt3,"energy_weather_090926.csv");
%% Seasonality
%Data starts 2022-11-05 14:30:00
% Data ends 2021-01-06 00:00:00


%Max usage is 1500W
% Min usage is 0W
% Max dew point is 20 deg
% min dew point is -45 deg
y_power_lim = [0, 1500];
y_dew_lim = [-45, 30];

%Quarter 1
%Create datetime values for start and end of quarter
% then create a range of datetime values
start_2023_Q1 = datetime(2023, 1, 1, 0, 0, 0);
end_2023_Q1 = datetime(2023,3,31, 23, 45, 0);
range_Q1 = timerange(start_2023_Q1, end_2023_Q1, 'closed');

%Use datetime range to extract first quarter from timetable
data_2023_Q1 = data_tt3(range_Q1,:);

%Create tiled plot for first quarter
Q1 = figure(3);
tiledlayout(2,1);

%Plot first quarter power
nexttile
plot(data_2023_Q1.date,data_2023_Q1.active_power);
title("Active Power Usage, 2023 Q1")
xlabel("Time (dt = 15min)")
ylabel("Active Power (W)")
ylim(y_power_lim)

%Plot first quarter dew point
nexttile
plot(data_2023_Q1.date,data_2023_Q1.dew_point);
title("Dew Point Temperature, 2023 Q1")
xlabel("Time (dt = 15min)")
ylabel("Dew Point (Degrees Celsius)")
ylim(y_dew_lim)

%Quarter 2
start_2023_Q2 = datetime(2023,3,31, 23, 45, 0);
end_2023_Q2 = datetime(2023,6,30, 23, 45, 0);
range_Q2 = timerange(start_2023_Q2, end_2023_Q2, 'closedright');

data_2023_Q2 = data_tt3(range_Q2,:);

Q2 = figure(4);
tiledlayout(2,1);

nexttile
plot(data_2023_Q2.date,data_2023_Q2.active_power);
title("Active Power Usage, 2023 Q2")
xlabel("Time (dt = 15min)")
ylabel("Active Power (W)")
ylim(y_power_lim)

nexttile
plot(data_2023_Q2.date,data_2023_Q2.dew_point);
title("Dew Point Temperature, 2023 Q2")
xlabel("Time (dt = 15min)")
ylabel("Dew Point (Degrees Celsius)")
ylim(y_dew_lim)

%Quarter 3
start_2023_Q3 = datetime(2023,6,30, 23, 45, 0);
end_2023_Q3 = datetime(2023,9,30, 23, 45, 0);
range_Q3 = timerange(start_2023_Q3, end_2023_Q3, 'closedright');

data_2023_Q3 = data_tt3(range_Q3,:);

Q3 = figure(5);
tiledlayout(2,1);

nexttile
plot(data_2023_Q3.date,data_2023_Q3.active_power);
title("Active Power Usage, 2023 Q3")
xlabel("Time (dt = 15min)")
ylabel("Active Power (W)")
ylim(y_power_lim)

nexttile
plot(data_2023_Q3.date,data_2023_Q3.dew_point);
title("Dew Point Temperature, 2023 Q3")
xlabel("Time (dt = 15min)")
ylabel("Dew Point (Degrees Celsius)")
ylim(y_dew_lim)

%Quarter 4
start_2023_Q4 = datetime(2023,9,30, 23, 45, 0);
end_2023_Q4 = datetime(2023,12,31, 23, 45, 0);
range_Q4 = timerange(start_2023_Q4, end_2023_Q4, 'closedright');

data_2023_Q4 = data_tt3(range_Q4,:);

Q4 = figure(6);
tiledlayout(2,1);

nexttile
plot(data_2023_Q4.date,data_2023_Q4.active_power);
title("Active Power Usage, 2023 Q4")
xlabel("Time (dt = 15min)")
ylabel("Active Power (W)")
ylim(y_power_lim)

nexttile
plot(data_2023_Q4.date,data_2023_Q4.dew_point);
title("Dew Point Temperature, 2023 Q4")
xlabel("Time (dt = 15min)")
ylabel("Dew Point (Degrees Celsius)")
ylim(y_dew_lim)

%% Save figures
saveas(Q1,"Q1_plots.jpg");
saveas(Q2,"Q2_plots.jpg");
saveas(Q3,"Q3_plots.jpg");
saveas(Q4,"Q4_plots.jpg");