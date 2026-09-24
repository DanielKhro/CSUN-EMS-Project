import requests
import json
import time
import datetime as dt

def get_station_list():
    with open("NWSdata.json", "r") as file: #Open JSON containing permanent data
        NWSdata = json.load(file)
    lat = NWSdata["lat"]
    lon = NWSdata["lon"]
    url = f"https://api.weather.gov/points/{lat},{lon}"
    response = requests.get(url)

    if response.status_code == 200:
        data_meta = response.json()
        station_url = data_meta["properties"]["observationStations"]

        NWSdata["stationURL"] = station_url
        with open("NWSdata.json", "w") as file:
            json.dump(NWSdata, file, indent=4)
        return station_url
    else:
        return None


#This function retrieves the Station ID using the NWS API
def get_stationID():
    with open("NWSdata.json", "r") as file: #Open JSON containing permanent data
        NWSdata = json.load(file)
    station_url = NWSdata["stationURL"] #Get required stations URL

    response = requests.get(station_url) #Use station url to get json file

    if response.status_code == 200:
        data = response.json()
        stationID = data["features"][0]["properties"]["stationIdentifier"] #get station ID

        NWSdata["stationID"] = stationID #Save and update station ID in dict
        with open("NWSdata.json", "w") as file:
            json.dump(NWSdata, file, indent=4)
        return stationID
    else:
        return None


def get_dewPoint():
    with open("NWSdata.json", "r") as file: #Open JSON containing permanent data
        NWSdata = json.load(file)
    stationId = NWSdata["stationID"]

    url = f"https://api.weather.gov/stations/{stationId}/observations/latest"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        dewPoint = data["properties"]["dewpoint"]["value"]
        return dewPoint
    else:
        return None


def main():
    #Bulk of the code
    get_station_list()
    get_stationID()

    try:
        while True:
            # This loop will keep script running
            dewPointVal = get_dewPoint()
            currentTime = dt.datetime.now().isoformat(timespec='hours')

            dewMeas = [currentTime, dewPointVal]

            with open('dewPointVals.csv','a') as fd:
                fd.write(dewMeas)

            time.sleep(3600)  # Sleep to prevent high CPU usage
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        #What to do when loop stops
        print("Ending weather data loop.")

if __name__ == "__main__":
    main()
