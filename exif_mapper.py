#!/usr/bin/env python3
"""
EXIF Mapper: Extract EXIF data from photos, plot GPS locations on an interactive map,
and export all EXIF data to CSV.

The public map shows only place names (reverse geocoded) — no coordinates,
timestamps, or device info.

Geocoding uses a 200m radius cache: photos within the same ~200m grid cell
share one API call instead of making redundant requests.
"""

import sys
import time
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import folium
import pandas as pd
import requests
import certifi

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.tiff', '.tif', '.heic', '.png'}

NOMINATIM_URL    = 'https://nominatim.openstreetmap.org/reverse'
NOMINATIM_HEADERS = {'User-Agent': 'exif-mapper/1.0'}

# 200m ≈ 0.0018 degrees latitude. Using 0.002 gives a ~220m grid cell.
CACHE_RADIUS_DEG = 0.002


def find_images(folder: Path) -> list[Path]:
    """Recursively find all image files in folder."""
    images = []
    for path in sorted(folder.rglob('*')):
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
    return images


def parse_gps_dms(dms_tuple, ref: str) -> float:
    """Convert (degrees, minutes, seconds) + reference to decimal degrees."""
    degrees, minutes, seconds = dms_tuple
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if ref in ('S', 'W'):
        decimal = -decimal
    return round(decimal, 7)


def geo_cache_key(lat: float, lon: float) -> tuple:
    """Snap coordinates to the nearest ~200m grid cell for cache lookup."""
    r = CACHE_RADIUS_DEG
    return (round(round(lat / r) * r, 6), round(round(lon / r) * r, 6))


def reverse_geocode(lat: float, lon: float) -> dict:
    """Return place name components for a coordinate pair via Nominatim."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={'lat': lat, 'lon': lon, 'format': 'json', 'accept-language': 'en'},
            headers=NOMINATIM_HEADERS,
            verify=certifi.where(),
            timeout=10,
        )
        resp.raise_for_status()
        addr = resp.json().get('address', {})
        return {
            'place':    addr.get('amenity') or addr.get('tourism') or
                        addr.get('building') or addr.get('shop') or '',
            'area':     addr.get('neighbourhood') or addr.get('suburb') or
                        addr.get('quarter') or '',
            'district': addr.get('city_district') or addr.get('borough') or
                        addr.get('city') or addr.get('town') or addr.get('village') or '',
            'city':     addr.get('state') or addr.get('region') or '',
            'country':  addr.get('country', ''),
        }
    except Exception:
        return {}


def format_place(geo: dict) -> str:
    """Build a short readable place string from geocode components."""
    parts = [geo.get('area') or geo.get('district'), geo.get('city'), geo.get('country')]
    return ', '.join(p for p in parts if p)


def format_place_full(geo: dict) -> str:
    """Build a full place string including specific place name if available."""
    parts = [geo.get('place'), geo.get('area') or geo.get('district'),
             geo.get('city'), geo.get('country')]
    return ', '.join(p for p in parts if p)


def extract_exif(image_path: Path) -> dict:
    """Extract all EXIF tags from an image. Returns dict with flat key/value pairs."""
    record = {'filename': image_path.name, 'filepath': str(image_path)}

    try:
        img = Image.open(image_path)
        raw_exif = img._getexif()
    except Exception as e:
        record['error'] = str(e)
        return record

    if not raw_exif:
        return record

    gps_raw = None

    for tag_id, value in raw_exif.items():
        tag = TAGS.get(tag_id, str(tag_id))

        if tag == 'GPSInfo':
            gps_raw = value
            continue

        # Skip binary blobs and very long values
        if isinstance(value, bytes):
            continue
        if isinstance(value, str) and len(value) > 200:
            continue

        record[tag] = value

    # Parse GPS sub-IFD
    if gps_raw:
        gps = {GPSTAGS.get(k, k): v for k, v in gps_raw.items()}
        try:
            lat = parse_gps_dms(gps['GPSLatitude'], gps['GPSLatitudeRef'])
            lon = parse_gps_dms(gps['GPSLongitude'], gps['GPSLongitudeRef'])
            record['gps_lat'] = lat
            record['gps_lon'] = lon
        except (KeyError, TypeError, ZeroDivisionError):
            pass

        if 'GPSAltitude' in gps:
            try:
                alt = float(gps['GPSAltitude'])
                if gps.get('GPSAltitudeRef') == b'\x01':
                    alt = -alt
                record['gps_altitude_m'] = round(alt, 2)
            except (TypeError, ZeroDivisionError):
                pass

    return record


def build_csv(records: list[dict], output_path: Path):
    """Write all EXIF records to CSV."""
    df = pd.DataFrame(records)

    priority_cols = ['filename', 'filepath', 'gps_lat', 'gps_lon', 'gps_altitude_m',
                     'place_full', 'place_short',
                     'DateTime', 'DateTimeOriginal', 'Make', 'Model', 'LensModel',
                     'FocalLength', 'FNumber', 'ExposureTime', 'ISOSpeedRatings']
    existing_priority = [c for c in priority_cols if c in df.columns]
    other_cols = [c for c in df.columns if c not in existing_priority]
    df = df[existing_priority + other_cols]

    df.to_csv(output_path, index=False)
    print(f"CSV saved:  {output_path}  ({len(df)} images)")


def build_map(records: list[dict], output_path: Path):
    """Build a privacy-safe map: pins show place names only, no coordinates or EXIF."""
    geotagged = [r for r in records if 'gps_lat' in r and 'gps_lon' in r]

    if not geotagged:
        print("No GPS data found in any images — map not generated.")
        return

    avg_lat = sum(r['gps_lat'] for r in geotagged) / len(geotagged)
    avg_lon = sum(r['gps_lon'] for r in geotagged) / len(geotagged)

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13, tiles='CartoDB positron')

    for r in geotagged:
        geo = r.get('_geo', {})
        place_full  = format_place_full(geo) or 'Unknown location'
        place_short = format_place(geo)      or 'Unknown location'

        popup_html = f"<b>{r['filename']}</b><br>{place_full}"

        folium.Marker(
            location=[r['gps_lat'], r['gps_lon']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=place_short,
        ).add_to(m)

    m.save(str(output_path))
    print(f"Map saved:  {output_path}  ({len(geotagged)}/{len(records)} images have GPS)")


def geocode_all(records: list[dict]) -> int:
    """
    Reverse geocode all geotagged records using a 200m radius cache.
    Returns the number of actual API calls made.
    """
    geotagged  = [r for r in records if 'gps_lat' in r and 'gps_lon' in r]
    cache: dict[tuple, dict] = {}
    api_calls  = 0
    cache_hits = 0

    print(f"Reverse geocoding {len(geotagged)} location(s) "
          f"(~200m cache, 1 req/sec for new locations)...")

    for r in geotagged:
        key = geo_cache_key(r['gps_lat'], r['gps_lon'])

        if key in cache:
            geo = cache[key]
            cache_hits += 1
            status = 'cache'
        else:
            geo = reverse_geocode(r['gps_lat'], r['gps_lon'])
            cache[key] = geo
            api_calls += 1
            status = 'API'
            time.sleep(1)   # Nominatim rate limit — only for real requests

        r['_geo']        = geo
        r['place_full']  = format_place_full(geo)
        r['place_short'] = format_place(geo)
        print(f"  [{status:5s}]  {r['filename']:30s}  →  {r['place_full'] or 'not found'}")

    print(f"\n  {api_calls} API call(s), {cache_hits} cache hit(s) "
          f"(saved ~{cache_hits}s)")
    return api_calls


def main():
    root          = Path(__file__).parent
    images_folder = root / 'images'

    if not images_folder.exists():
        print(f"Error: images folder not found at {images_folder}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning: {images_folder}")
    image_paths = find_images(images_folder)
    print(f"Found {len(image_paths)} image(s)\n")

    records = []
    for path in image_paths:
        print(f"  Processing: {path.name}")
        records.append(extract_exif(path))

    print()
    geocode_all(records)

    print()
    build_csv(records, root / 'exif_data.csv')
    build_map(records, root / 'map.html')


if __name__ == '__main__':
    main()
