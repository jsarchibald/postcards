import piexif
from PIL import Image, ImageFont, ImageDraw
from pycountry import countries, subdivisions

import json
import os
import requests
import sys

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

def choose_name(names):
    """Of the names extracted from Mapquest, choose the best one for the postcard"""
    preference_list = ["name", "street", "adminArea6", "adminArea5", "adminArea3", "adminArea4", "adminArea1"]
    for field in preference_list:
        if names[field]:
            return names[field].pop()

def get_output_size(image):
    """Returns width and height tuple based on vertical or horizontal orientation"""
    if image.width < image.height:
        return 1200, 1800
    else:
        return 1800, 1200

def get_text_box(x, y, font_size, image, characters):
    """Returns the crop box of a section of image given text coords and font size"""
    estimated_text_width = .8 * font_size * characters
    width = min(estimated_text_width, image.width - x)
    height = min(font_size, image.height - y)

    return x, y, width, height

def get_average_color(image):
    """Returns the RGB tuple (and average RGB) representing the average color of a section of an image"""
    image = image.resize((1, 1))
    rgb = image.getpixel((0, 0))
    average_color_metric = sum(rgb) / 3

    return rgb[0], rgb[1], rgb[2], average_color_metric

def get_font_color(average_color_metric):
    """Returns tuple of primary and secondary colors depending on average color metric"""
    if average_color_metric[3] < 128:
        return (255, 255, 255), average_color_metric[:3]
    else:
        return (0, 0, 0), average_color_metric[:3]

def create_images(name, infile):
    """Creates a set of images that could possibly be used as the final postcard"""
    original = Image.open(infile)
    width, height = get_output_size(original)

    # For creating a training database, eventually these will change iteratively
    font_size = 150
    font = ImageFont.truetype("Bebas-Regular.otf", font_size)
    text_coords = 10, 0
    
    # Check the average color of the section where the text will go, and decide if dark (white text) or light (black text)
    text_section = original.copy()
    text_section = text_section.crop(box = get_text_box(text_coords[0], text_coords[1], font_size, original, len(name)))
    average_color_metric = get_average_color(text_section)
    text_primary, text_secondary = get_font_color(average_color_metric)

    # Crop the original image to our target dimensions
    i = original.copy()
    out = i.crop(box=(0, 0, width, height))

    # Add text overlay
    draw = ImageDraw.Draw(out)
    draw.text((text_coords[0] + 5, text_coords[1] + 5), name, text_secondary, font=font)
    draw.text(text_coords, name, text_primary, font=font)
    
    out.save("{0}.jpg".format(name))

def main():
    fn = "images/" + sys.argv[1]
    image = get_metadata(fn)
    if image is None:
        print("Failed")
        return
    
    coords = get_coordinates(image)
    possible_names = get_names(get_location(coords) + get_nearby_locations(coords))
    name = choose_name(possible_names)
    create_images(name, fn)

if __name__ == "__main__":
    main()