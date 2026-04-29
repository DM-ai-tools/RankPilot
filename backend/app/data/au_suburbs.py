"""
Curated AU suburb lists by metro label (city).
Used to seed rp_suburb_grid on onboarding.
Extend with real postcode DB later; this covers the top ~25 suburbs per major metro.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

METRO_SUBURBS: dict[str, list[dict]] = {
    "Melbourne, VIC": [
        {"suburb": "Melbourne CBD",  "state": "VIC", "postcode": "3000", "lat": -37.8136, "lng": 144.9631, "population": 28000},
        {"suburb": "South Yarra",    "state": "VIC", "postcode": "3141", "lat": -37.8390, "lng": 144.9930, "population": 25000},
        {"suburb": "St Kilda",       "state": "VIC", "postcode": "3182", "lat": -37.8610, "lng": 144.9810, "population": 22000},
        {"suburb": "Fitzroy",        "state": "VIC", "postcode": "3065", "lat": -37.7990, "lng": 144.9780, "population": 15000},
        {"suburb": "Richmond",       "state": "VIC", "postcode": "3121", "lat": -37.8180, "lng": 145.0020, "population": 32000},
        {"suburb": "Collingwood",    "state": "VIC", "postcode": "3066", "lat": -37.8040, "lng": 144.9870, "population": 12000},
        {"suburb": "Footscray",      "state": "VIC", "postcode": "3011", "lat": -37.8000, "lng": 144.9000, "population": 91000},
        {"suburb": "Northcote",      "state": "VIC", "postcode": "3070", "lat": -37.7700, "lng": 145.0000, "population": 45000},
        {"suburb": "Essendon",       "state": "VIC", "postcode": "3040", "lat": -37.7600, "lng": 144.9200, "population": 110000},
        {"suburb": "Williamstown",   "state": "VIC", "postcode": "3016", "lat": -37.8600, "lng": 144.8900, "population": 28000},
        {"suburb": "Brunswick",      "state": "VIC", "postcode": "3056", "lat": -37.7680, "lng": 144.9620, "population": 27000},
        {"suburb": "Prahran",        "state": "VIC", "postcode": "3181", "lat": -37.8510, "lng": 144.9870, "population": 14000},
        {"suburb": "Preston",        "state": "VIC", "postcode": "3072", "lat": -37.7450, "lng": 145.0030, "population": 40000},
        {"suburb": "Hawthorn",       "state": "VIC", "postcode": "3122", "lat": -37.8230, "lng": 145.0340, "population": 22000},
        {"suburb": "Glen Waverley",  "state": "VIC", "postcode": "3150", "lat": -37.8780, "lng": 145.1640, "population": 47000},
        {"suburb": "Doncaster",      "state": "VIC", "postcode": "3108", "lat": -37.7880, "lng": 145.1260, "population": 21000},
        {"suburb": "Box Hill",       "state": "VIC", "postcode": "3128", "lat": -37.8210, "lng": 145.1240, "population": 22000},
        {"suburb": "Frankston",      "state": "VIC", "postcode": "3199", "lat": -38.1460, "lng": 145.1240, "population": 40000},
        {"suburb": "Dandenong",      "state": "VIC", "postcode": "3175", "lat": -37.9870, "lng": 145.2140, "population": 37000},
        {"suburb": "Ringwood",       "state": "VIC", "postcode": "3134", "lat": -37.8160, "lng": 145.2270, "population": 18000},
        {"suburb": "Werribee",       "state": "VIC", "postcode": "3030", "lat": -37.8990, "lng": 144.6640, "population": 41000},
        {"suburb": "Craigieburn",    "state": "VIC", "postcode": "3064", "lat": -37.6020, "lng": 144.9420, "population": 55000},
        {"suburb": "Sunshine",       "state": "VIC", "postcode": "3020", "lat": -37.7900, "lng": 144.8310, "population": 20000},
        {"suburb": "Hoppers Crossing","state": "VIC","postcode": "3029", "lat": -37.8820, "lng": 144.7010, "population": 33000},
        {"suburb": "Tarneit",        "state": "VIC", "postcode": "3029", "lat": -37.8580, "lng": 144.6680, "population": 48000},
    ],
    "Sydney, NSW": [
        {"suburb": "Sydney CBD",     "state": "NSW", "postcode": "2000", "lat": -33.8688, "lng": 151.2093, "population": 25000},
        {"suburb": "Parramatta",     "state": "NSW", "postcode": "2150", "lat": -33.8148, "lng": 151.0017, "population": 32000},
        {"suburb": "Bondi",          "state": "NSW", "postcode": "2026", "lat": -33.8915, "lng": 151.2767, "population": 11000},
        {"suburb": "Newtown",        "state": "NSW", "postcode": "2042", "lat": -33.8978, "lng": 151.1793, "population": 14000},
        {"suburb": "Chatswood",      "state": "NSW", "postcode": "2067", "lat": -33.7969, "lng": 151.1822, "population": 19000},
        {"suburb": "Blacktown",      "state": "NSW", "postcode": "2148", "lat": -33.7700, "lng": 150.9060, "population": 46000},
        {"suburb": "Liverpool",      "state": "NSW", "postcode": "2170", "lat": -33.9200, "lng": 150.9230, "population": 38000},
        {"suburb": "Penrith",        "state": "NSW", "postcode": "2750", "lat": -33.7517, "lng": 150.6940, "population": 20000},
        {"suburb": "Hornsby",        "state": "NSW", "postcode": "2077", "lat": -33.7010, "lng": 151.0990, "population": 18000},
        {"suburb": "Manly",          "state": "NSW", "postcode": "2095", "lat": -33.7967, "lng": 151.2874, "population": 15000},
        {"suburb": "Surry Hills",    "state": "NSW", "postcode": "2010", "lat": -33.8856, "lng": 151.2101, "population": 16000},
        {"suburb": "Redfern",        "state": "NSW", "postcode": "2016", "lat": -33.8926, "lng": 151.2059, "population": 10000},
        {"suburb": "Marrickville",   "state": "NSW", "postcode": "2204", "lat": -33.9124, "lng": 151.1570, "population": 19000},
        {"suburb": "Bankstown",      "state": "NSW", "postcode": "2200", "lat": -33.9170, "lng": 151.0350, "population": 30000},
        {"suburb": "Campbelltown",   "state": "NSW", "postcode": "2560", "lat": -34.0650, "lng": 150.8140, "population": 26000},
        {"suburb": "Castle Hill",    "state": "NSW", "postcode": "2154", "lat": -33.7285, "lng": 151.0060, "population": 24000},
        {"suburb": "Kogarah",        "state": "NSW", "postcode": "2217", "lat": -33.9658, "lng": 151.1335, "population": 10000},
        {"suburb": "Hurstville",     "state": "NSW", "postcode": "2220", "lat": -33.9666, "lng": 151.1034, "population": 22000},
        {"suburb": "Miranda",        "state": "NSW", "postcode": "2228", "lat": -34.0332, "lng": 151.1005, "population": 11000},
        {"suburb": "Sutherland",     "state": "NSW", "postcode": "2232", "lat": -34.0310, "lng": 151.0560, "population": 11000},
    ],
    "Brisbane, QLD": [
        {"suburb": "Brisbane CBD",   "state": "QLD", "postcode": "4000", "lat": -27.4698, "lng": 153.0251, "population": 12000},
        {"suburb": "South Brisbane", "state": "QLD", "postcode": "4101", "lat": -27.4800, "lng": 153.0171, "population": 10000},
        {"suburb": "Fortitude Valley","state": "QLD","postcode": "4006", "lat": -27.4570, "lng": 153.0344, "population": 8000},
        {"suburb": "Toowong",        "state": "QLD", "postcode": "4066", "lat": -27.4850, "lng": 152.9870, "population": 11000},
        {"suburb": "Chermside",      "state": "QLD", "postcode": "4032", "lat": -27.3870, "lng": 153.0340, "population": 15000},
        {"suburb": "Carindale",      "state": "QLD", "postcode": "4152", "lat": -27.4970, "lng": 153.0970, "population": 12000},
        {"suburb": "Logan City",     "state": "QLD", "postcode": "4114", "lat": -27.6380, "lng": 153.1090, "population": 25000},
        {"suburb": "Ipswich",        "state": "QLD", "postcode": "4305", "lat": -27.6140, "lng": 152.7600, "population": 20000},
        {"suburb": "Redcliffe",      "state": "QLD", "postcode": "4020", "lat": -27.2250, "lng": 153.1050, "population": 13000},
        {"suburb": "Indooroopilly",  "state": "QLD", "postcode": "4068", "lat": -27.5000, "lng": 152.9750, "population": 11000},
        {"suburb": "Springwood",     "state": "QLD", "postcode": "4127", "lat": -27.6140, "lng": 153.1030, "population": 14000},
        {"suburb": "Everton Park",   "state": "QLD", "postcode": "4053", "lat": -27.4200, "lng": 152.9930, "population": 10000},
        {"suburb": "North Lakes",    "state": "QLD", "postcode": "4509", "lat": -27.2540, "lng": 153.0200, "population": 22000},
        {"suburb": "Caboolture",     "state": "QLD", "postcode": "4510", "lat": -27.0770, "lng": 152.9510, "population": 21000},
        {"suburb": "Strathpine",     "state": "QLD", "postcode": "4500", "lat": -27.2980, "lng": 152.9930, "population": 13000},
    ],
    "Perth, WA": [
        {"suburb": "Perth CBD",      "state": "WA",  "postcode": "6000", "lat": -31.9505, "lng": 115.8605, "population": 16000},
        {"suburb": "Fremantle",      "state": "WA",  "postcode": "6160", "lat": -32.0569, "lng": 115.7439, "population": 10000},
        {"suburb": "Joondalup",      "state": "WA",  "postcode": "6027", "lat": -31.7450, "lng": 115.7680, "population": 16000},
        {"suburb": "Rockingham",     "state": "WA",  "postcode": "6168", "lat": -32.2830, "lng": 115.7330, "population": 15000},
        {"suburb": "Mandurah",       "state": "WA",  "postcode": "6210", "lat": -32.5320, "lng": 115.7220, "population": 21000},
        {"suburb": "Morley",         "state": "WA",  "postcode": "6062", "lat": -31.8880, "lng": 115.9040, "population": 9000},
        {"suburb": "Midland",        "state": "WA",  "postcode": "6056", "lat": -31.8880, "lng": 116.0040, "population": 11000},
        {"suburb": "Cannington",     "state": "WA",  "postcode": "6107", "lat": -31.9900, "lng": 115.9380, "population": 8000},
        {"suburb": "Armadale",       "state": "WA",  "postcode": "6112", "lat": -32.1470, "lng": 116.0120, "population": 10000},
        {"suburb": "Baldivis",       "state": "WA",  "postcode": "6171", "lat": -32.3300, "lng": 115.8080, "population": 24000},
    ],
    "Adelaide, SA": [
        {"suburb": "Adelaide CBD",   "state": "SA",  "postcode": "5000", "lat": -34.9285, "lng": 138.6007, "population": 23000},
        {"suburb": "Glenelg",        "state": "SA",  "postcode": "5045", "lat": -34.9820, "lng": 138.5140, "population": 7000},
        {"suburb": "Norwood",        "state": "SA",  "postcode": "5067", "lat": -34.9240, "lng": 138.6250, "population": 6000},
        {"suburb": "Elizabeth",      "state": "SA",  "postcode": "5112", "lat": -34.7100, "lng": 138.6750, "population": 12000},
        {"suburb": "Salisbury",      "state": "SA",  "postcode": "5108", "lat": -34.7570, "lng": 138.6330, "population": 11000},
        {"suburb": "Morphett Vale",  "state": "SA",  "postcode": "5162", "lat": -35.1350, "lng": 138.5320, "population": 17000},
        {"suburb": "Marion",         "state": "SA",  "postcode": "5043", "lat": -35.0070, "lng": 138.5560, "population": 7000},
        {"suburb": "Mount Barker",   "state": "SA",  "postcode": "5251", "lat": -35.0670, "lng": 138.8560, "population": 16000},
    ],
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres (WGS84 sphere approximation)."""
    r_e = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r_e * math.asin(min(1.0, math.sqrt(a)))


def resolve_metro_key(metro_label: str) -> str:
    label = (metro_label or "").strip()
    for key in METRO_SUBURBS:
        city = key.split(",")[0].strip()
        if label.lower().startswith(city.lower()):
            return key
    return "Melbourne, VIC"


def metro_cbd_lat_lng(metro_label: str) -> tuple[float, float]:
    """CBD pin for distance checks: first curated suburb for that metro."""
    key = resolve_metro_key(metro_label)
    cbd = METRO_SUBURBS[key][0]
    return float(cbd["lat"]), float(cbd["lng"])


def filter_suburbs_by_radius_km(
    suburbs: Sequence[Mapping[str, object]],
    metro_label: str,
    radius_km: int,
) -> list[dict]:
    """Keep suburbs within radius_km of the metro CBD. Returns at least one row if input non-empty."""
    rmax = max(5, min(150, int(radius_km)))
    try:
        cla, clo = metro_cbd_lat_lng(metro_label)
    except (KeyError, IndexError, TypeError, ValueError):
        return [dict(s) for s in suburbs]
    out: list[dict] = []
    for s in suburbs:
        try:
            la = float(s["lat"])  # type: ignore[arg-type]
            lo = float(s["lng"])  # type: ignore[arg-type]
        except (TypeError, ValueError, KeyError):
            continue
        if haversine_km(cla, clo, la, lo) <= rmax:
            out.append(dict(s))
    if not out and suburbs:
        return [dict(suburbs[0])]
    return out


def get_suburbs_for_metro(metro_label: str, *, radius_km: int | None = None) -> list[dict]:
    """Return suburbs for a metro within radius_km of that metro's CBD (default 25 km)."""
    r = max(5, min(150, int(radius_km or 25)))
    key = resolve_metro_key(metro_label)
    suburbs = list(METRO_SUBURBS[key])
    return filter_suburbs_by_radius_km(suburbs, metro_label, r)
