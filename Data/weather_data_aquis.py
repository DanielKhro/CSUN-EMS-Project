import requests
import json

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

# data = {
#     "address": "18111 Nordhoff St, Northridge, CA 91330",
#     "lat": 34.2356,
#     "lon": -118.5278,
#     "stationURL": "https://api.weather.gov/gridpoints/LOX/146,55/stations",
#     "stationID": "KVNY"
# }
# with open("NWSdata.json", "w") as f:
#     json.dump(data, f)

stationID = get_stationID()
if stationID is not None:
   print(f"Station ID: {stationID}")
else:
   print("Failed to retrieve data.")

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

dewPoint = get_dewPoint()
if dewPoint is not None:
   print(f"Current dew point: {dewPoint} DegC")
else:
   print("Failed to retrieve data.")

