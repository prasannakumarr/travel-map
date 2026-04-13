An interactive map of locations from my photographs.

## How it works

A Python script extracts GPS data from photo EXIF metadata and plots each location on an interactive map.

- **EXIF extraction** — [Pillow](https://python-pillow.org/) reads GPS coordinates embedded in each photo
- **Reverse geocoding** — coordinates are converted to place names (neighbourhood, city, country) using [Nominatim](https://nominatim.org/) (OpenStreetMap), with a ~200m radius cache to avoid redundant lookups
- **Map rendering** — [Folium](https://python-folium.readthedocs.io/) generates the interactive map as a standalone HTML file

The map shows only place names — no coordinates, timestamps, or device info are exposed.
