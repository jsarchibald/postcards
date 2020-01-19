import piexif
from pycountry import countries, subdivisions

import json
import os
import requests

API_KEYS = {
    "MAPQUEST": os.environ["MAPQUEST"]
}

def get_metadata(name):
    """Gets metadata from image with filename name"""
    with open(name, "rb") as f:
        image = piexif.load(name)
    
    if image["GPS"] != {}:
        i = image["GPS"]
        data = {"gps_latitude": i[2],
                "gps_longitude": i[4],
                "gps_latitude_ref": i[1].decode("utf-8"),
                "gps_longitude_ref": i[3].decode("utf-8")
               }

        return data
    else:
        return None

def get_coordinates(image):
    """Gets lat and long coords given an exif Image"""
    latitude = (image["gps_latitude"][0][0] / image["gps_latitude"][0][1]
                + image["gps_latitude"][1][0] / image["gps_latitude"][1][1] / 60
                + image["gps_latitude"][2][0] / image["gps_latitude"][2][1] / 3600)
    longitude = (image["gps_longitude"][0][0] / image["gps_longitude"][0][1]
                 + image["gps_longitude"][1][0] / image["gps_longitude"][1][1] / 60
                 + image["gps_longitude"][2][0] / image["gps_longitude"][2][1] / 3600)

    if image["gps_latitude_ref"] != "N":
        latitude *= -1
    if image["gps_longitude_ref"] != "E":
        longitude *= -1

    return (latitude, longitude)

def get_location(latLng):
    """Asks Mapquest for the name of a long-lat coordinate"""
    params = {"key": API_KEYS["MAPQUEST"],
              "location": "{0},{1}".format(latLng[0], latLng[1]),
              "includeNearestIntersection": True}
    request = requests.get("http://www.mapquestapi.com/geocoding/v1/reverse", params=params)
    data = json.loads(request.text)

    return data["results"][0]["locations"]

def get_nearby_locations(latLng, radius = 3, units = "wmin", maxMatches = 5):
    """Asks Mapquest for nearby locations"""
    params = {"key": API_KEYS["MAPQUEST"],
              "origin": "{0},{1}".format(latLng[0], latLng[1]),
              "radius": radius,
              "units": units,
              "maxMatches": maxMatches,
              "hostedData": ["mqap.ntpois"]
             }
    request = requests.get("http://www.mapquestapi.com/search/v2/radius", params=params)
    data = json.loads(request.text)

    if data["resultsCount"] > 0:
        return data["searchResults"]
    
    return []

def get_names(locations):
    """Returns a set of possible location names from the Mapquest results"""
    names = {"street": set(),
             "adminArea6": set(),
             "adminArea5": set(),
             "adminArea4": set(),
             "adminArea3": set(),
             "adminArea2": set(),
             "adminArea1": set(),
             "name": set()}
    
    for location in locations:
        for field in names:
            if field in location and location[field] != "":
                if field == "adminArea1":
                    names[field].add(countries.get(alpha_2=location[field]).official_name)
                elif field == "adminArea3":
                    names[field].add(subdivisions.get(code="{0}-{1}".format(location["adminArea1"], location[field])))
                else:
                    names[field].add(location[field])

    return names

def main():
    image = get_metadata("images/nh.jpg")
    if image is None:
        print("Failed")
        return
    
    coords = get_coordinates(image)
    possible_names = get_names(get_location(coords) + get_nearby_locations(coords))

    # TODO

if __name__ == "__main__":
    main()