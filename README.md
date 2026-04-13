An interactive map of locations from my photographs.

EXIF MAPPER
===========

A Python script that recursively scans a folder of photographs, extracts GPS
data from EXIF metadata, and plots each location on an interactive map. All
EXIF data is also exported to a CSV file.

The map shows only place names — no coordinates, timestamps, or device info
are exposed.


OUTPUT FILES
------------
  map.html        Interactive map, open in any browser
  exif_data.csv   All EXIF fields, one row per image (keep this private)


REQUIREMENTS
------------
  - Python 3.10+
  - pip packages: Pillow, folium, pandas, requests, certifi


SETUP
-----
  Create a virtual environment and install dependencies:

    python3 -m venv venv
    venv/bin/pip install Pillow folium pandas requests certifi


USAGE
-----
  1. Put your photos in the images/ folder
     (subfolders are scanned recursively)

  2. Run the script:

       venv/bin/python3 exif_mapper.py

  The script will:
    - Extract EXIF data from all .jpg .jpeg .tiff .tif .heic .png files
    - Reverse geocode GPS coordinates to place names via Nominatim
      (free, no API key needed)
    - Use a ~200m radius cache to avoid redundant geocoding requests
    - Save map.html and exif_data.csv in the project root


PERFORMANCE (1000 photos)
--------------------------
  EXIF extraction      ~1-2 min
  Reverse geocoding    ~1 min (with cache)

  Geocoding uses a ~200m grid cache — photos taken within the same area
  share one API call. Without the cache it would be ~17 min at Nominatim's
  1 req/sec rate limit.


PRIVACY
-------
  map.html is safe to share publicly — it contains only place names.

  exif_data.csv contains raw GPS coordinates, timestamps, and device info.
  Keep it local. Do not upload it to a public repository.


DEPENDENCIES
------------
  Pillow      EXIF extraction
  Folium      Interactive HTML map
  Pandas      CSV export
  Requests    Nominatim API calls with SSL
  Certifi     SSL certificate bundle (fixes macOS Python cert issue)
