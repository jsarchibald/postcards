from argparse import ArgumentParser
from io import BytesIO
from PIL import ExifTags, Image, ImageFont, ImageDraw
from pycountry import countries, subdivisions

import json
import os
import requests
import sqlite3

API_KEYS = {
    "MAPQUEST": os.environ["MAPQUEST"]
}

def get_metadata(name, desired_tags = ["GPSInfo", "DateTimeOriginal", "SubjectArea", "Orientation"]):
    """Gets EXIF metadata from image with filename name"""
    try:
        image = Image.open(name)
        exif = dict(image._getexif().items())
    except:
        return None

    metadata = {}
    for tag in ExifTags.TAGS:
        if ExifTags.TAGS[tag] in desired_tags and tag in exif:
            metadata[ExifTags.TAGS[tag]] = exif[tag]

    data = {}
    for key in metadata:
        if key == "GPSInfo":
            data["GPSInfo"] = {}
            for tag in ExifTags.GPSTAGS:
                if tag in metadata["GPSInfo"]:
                    data["GPSInfo"][ExifTags.GPSTAGS[tag]] = metadata["GPSInfo"][tag]
        else:
            data[key] = metadata[key]
    
    return data

def get_coordinates(metadata):
    """Gets lat and long coords given an exif metadata dictionary"""
    if "GPSInfo" not in metadata:
        return None

    lat = metadata["GPSInfo"]["GPSLatitude"]
    lng = metadata["GPSInfo"]["GPSLongitude"]
    latitude = (lat[0][0] / lat[0][1]
                + lat[1][0] / lat[1][1] / 60
                + lat[2][0] / lat[2][1] / 3600)
    longitude = (lng[0][0] / lng[0][1]
                 + lng[1][0] / lng[1][1] / 60
                 + lng[2][0] / lng[2][1] / 3600)

    if metadata["GPSInfo"]["GPSLatitudeRef"] != "N":
        latitude *= -1
    if metadata["GPSInfo"]["GPSLongitudeRef"] != "E":
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
                    names[field].add(countries.get(alpha_2=location[field]).name)
                elif field == "adminArea3":
                    names[field].add(subdivisions.get(code = "{0}-{1}".format(
                        countries.get(alpha_2 = location["adminArea1"]),
                        location[field]
                    )))
                else:
                    names[field].add(location[field])

    return names

def contains_digit(text):
    """Returns true if any digits exist in the text"""
    return any(c.isdigit() for c in text)

def choose_name(names):
    """Of the names extracted from Mapquest, choose the best one for the postcard"""
    preference_list = ["name", "street", "adminArea6", "adminArea5", "adminArea3", "adminArea4", "adminArea1"]
    for field in preference_list:
        if names[field]:
            if len(names[field]) < 3:
                tmp = names[field].pop()
                if field == "street":
                    if not contains_digit(tmp):
                        return tmp
                else:
                    return tmp

def get_output_size(image):
    """Returns width and height tuple based on vertical or horizontal orientation"""
    if image.width < image.height:
        return 1200, 1800
    else:
        return 1800, 1200

def get_original_image(infile, metadata):
    """Resizes the original image as necessary and returns it with the target dimensions"""
    try:
        original = Image.open(infile)
    except:
        return None
    width, height = get_output_size(original)

    # Rotate image as needed based on EXIF data
    if "Orientation" in metadata:
        if metadata["Orientation"] == 3:
            original = original.rotate(180, expand = True)
        elif metadata["Orientation"] == 6:
            original = original.rotate(270, expand = True)
        elif metadata["Orientation"] == 8:
            original = original.rotate(90, expand = True)

    # Resize original image to only slightly outsize the target dimensions (if applicable)
    if original.width > original.height:
        original = original.resize((width, round(width / original.width * original.height)))
    else:
        original = original.resize((round(height / original.height * original.width), height))

    return original, width, height

def get_text_box(x, y, font, image, text):
    """Returns the crop box of a section of image given text coords and font size"""
    est_text_width, est_text_height = font.getsize(text)
    width = min(est_text_width, image.width - x)
    height = min(est_text_height, image.height - y)

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

def get_font(name, text_coords, width, height, text):
    """Choose a reasonable font size, 20-150pt, that will fit the characters"""
    x, y = text_coords

    for font_size in range(20, 150):
        font = ImageFont.truetype(name, font_size)
        available_width = .8 * (width - x * 2)
        available_height = .8 * (height - y * 2)
        est_text_width, est_text_height = font.getsize(text)
        
        if ((est_text_width > available_width
             and est_text_height < available_height) 
            or font_size == 149):
            return ImageFont.truetype(name, font_size - 10)

def create_image(name, original, width, height, font, text_coords):
    """Create an individual image given the necessary parameters"""

    # Check the average color of the section where the text will go, and decide if dark (white text) or light (black text)
    text_section = original.copy()
    text_section = text_section.crop(box = get_text_box(text_coords[0],
                                                        text_coords[1],
                                                        font,
                                                        original,
                                                        name
                                                       ))
    average_color_metric = get_average_color(text_section)
    text_primary, text_secondary = get_font_color(average_color_metric)

    # Crop the original image to our target dimensions
    i = original.copy()
    out = i.crop(box=(0, 0, width, height))

    # Add text overlay
    draw = ImageDraw.Draw(out)
    draw.text((text_coords[0] + 5, text_coords[1] + 5), name, text_secondary, font=font)
    draw.text(text_coords, name, text_primary, font=font)

    return out

def get_text_locations(id, font, text, width, height):
    """Return a list of text coordinates based on marker"""
    w, h = font.getsize(text)
    if id == "NW":
        return {"NW": (10, 10)}
    elif id == "NE":
        return {"NE": (.8 * width - w - 10, 10)}
    elif id == "SW":
        return {"SW": (10, height - h - 10)}
    elif id == "SE":
        return {"SE": (.8 * width - w - 10, height - h - 10)}
    else:
        return {"NW": (10, 10),
                "NE": (.8 * width - w - 10, 10),
                "SW": (10, height - h - 10),
                "SE": (.8 * width - w - 10, height - h - 10)
               } 

def create_images(name, infile, metadata, filename, text_location, db):
    """Creates a set of images that could possibly be used as the final postcard"""
    try:
        original, width, height = get_original_image(infile, metadata)
    except:
        return None

    # For creating a training database, eventually these will change iteratively
    text_coords = 10, 10
    font = get_font("Roboto-Black.ttf", text_coords, width, height, name)
    coords = get_text_locations(text_location, font, name, width, height)

    source = BytesIO()
    original.save(source, format="JPEG")
    db.execute("INSERT INTO source_images (image) VALUES (?) ", (source.getvalue(), ))
    source_id = db.lastrowid
    
    i = 0
    for coord in coords:
        out = create_image(name.upper(), original, width, height, font, coords[coord])
        outname = "{0}_{1}_{2}.jpg".format(filename, i, name)
        if db is None:
            out.save("out/{0}".format(outname))
        else:
            io = BytesIO()
            out.save(io, format="JPEG")
            db.execute("INSERT INTO postcards (name, text_alignment, source_image_id, image) VALUES (?, ?, ?, ?)",
                       (outname, coord, source_id, io.getvalue()))
        i += 1

def process_image(filename, outindex, text_location, db):
    """The process for creating a set of images based on an input image"""
    metadata = get_metadata(filename)
    if metadata is None or "GPSInfo" not in metadata:
        print("Failed: lack GPS metadata for {0}".format(filename))
        return
    if db is not None:
        con = sqlite3.connect(db)
        db = con.cursor()
    
    coords = get_coordinates(metadata)
    possible_names = get_names(get_location(coords) + get_nearby_locations(coords))
    name = choose_name(possible_names)
    create_images(name, filename, metadata, outindex, text_location, db)
    con.commit()
    con.close()

def get_arguments():
    """CLI argument parser"""
    parser = ArgumentParser(description="Generate postcards based on EXIF GPS data.")
    parser.add_argument("-t",
                        dest="text_location",
                        nargs=1,
                        default="NW",
                        choices=["NW", "NE", "SW", "SE", "*"],
                        help="Location of text on postcard. * for one of each.")
    parser.add_argument("-d",
                        dest="directory",
                        nargs=1,
                        default=".",
                        help="Directory with input JPEG files. Defaults to current directory.")
    parser.add_argument("-b",
                        dest="database",
                        nargs=1,
                        help="Name of SQLite file in which to store images.")
    parser.add_argument("file_name",
                        help="Input JPEG name. * for all in the directory.")
    
    return parser.parse_args()

def main():
    args = get_arguments()

    if args.file_name != "*":
        process_image(args.filename, 0, args.text_location[0], args.database)
    else:
        i = 0
        with os.scandir(args.directory[0]) as files:
            for f in files:
                if f.is_file():
                    process_image(f.path, i, args.text_location[0], args.database[0])
                    i += 1

if __name__ == "__main__":
    main()