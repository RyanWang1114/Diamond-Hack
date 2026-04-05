from __future__ import annotations

import hashlib
from copy import deepcopy


CITY_BASES = {
    "San Francisco": {
        "country": "United States",
        "region": "North America",
        "airport": "SFO",
        "lat": 37.7749,
        "lon": -122.4194,
        "types": ["Food and cuisine", "Modern architecture", "Natural landscapes", "Cultural sites"],
        "climate": "cool coastal microclimates with breezy mornings",
        "geography": "steep urban hills on the Pacific edge",
        "buffer": 92,
    },
    "Rome": {
        "country": "Italy",
        "region": "Europe",
        "airport": "FCO",
        "lat": 41.9028,
        "lon": 12.4964,
        "types": ["Historical monuments", "Food and cuisine", "Cultural sites"],
        "climate": "warm Mediterranean days with dry afternoons",
        "geography": "historic districts spread across rolling hills",
        "buffer": 74,
    },
    "Florence": {
        "country": "Italy",
        "region": "Europe",
        "airport": "FLR",
        "lat": 43.7696,
        "lon": 11.2558,
        "types": ["Historical monuments", "Cultural sites", "Food and cuisine"],
        "climate": "sunny inland heat with cooler evenings",
        "geography": "compact Renaissance core beside a river",
        "buffer": 70,
    },
    "Venice": {
        "country": "Italy",
        "region": "Europe",
        "airport": "VCE",
        "lat": 45.4408,
        "lon": 12.3155,
        "types": ["Cultural sites", "Historical monuments", "Food and cuisine"],
        "climate": "humid lagoon weather with evening breezes",
        "geography": "waterbound canals connected by bridges and ferries",
        "buffer": 76,
    },
    "Barcelona": {
        "country": "Spain",
        "region": "Europe",
        "airport": "BCN",
        "lat": 41.3874,
        "lon": 2.1686,
        "types": ["Food and cuisine", "Modern architecture", "Cultural sites", "Natural landscapes"],
        "climate": "bright coastal sunshine with warm sea air",
        "geography": "beachfront city backed by hills",
        "buffer": 78,
    },
    "Lisbon": {
        "country": "Portugal",
        "region": "Europe",
        "airport": "LIS",
        "lat": 38.7223,
        "lon": -9.1393,
        "types": ["Food and cuisine", "Cultural sites", "Historical monuments", "Natural landscapes"],
        "climate": "Atlantic sunshine with coastal wind",
        "geography": "riverfront hills and tiled neighborhoods",
        "buffer": 72,
    },
    "Paris": {
        "country": "France",
        "region": "Europe",
        "airport": "CDG",
        "lat": 48.8566,
        "lon": 2.3522,
        "types": ["Historical monuments", "Food and cuisine", "Cultural sites", "Modern architecture"],
        "climate": "mild city weather with intermittent showers",
        "geography": "dense urban districts straddling a river",
        "buffer": 88,
    },
    "Prague": {
        "country": "Czech Republic",
        "region": "Europe",
        "airport": "PRG",
        "lat": 50.0755,
        "lon": 14.4378,
        "types": ["Historical monuments", "Cultural sites", "Food and cuisine"],
        "climate": "cooler continental weather with crisp evenings",
        "geography": "river city of bridges and castle hills",
        "buffer": 62,
    },
    "Vienna": {
        "country": "Austria",
        "region": "Europe",
        "airport": "VIE",
        "lat": 48.2082,
        "lon": 16.3738,
        "types": ["Historical monuments", "Cultural sites", "Food and cuisine", "Modern architecture"],
        "climate": "mild continental weather with cooler mornings",
        "geography": "imperial boulevards and museum districts",
        "buffer": 74,
    },
    "Tokyo": {
        "country": "Japan",
        "region": "Asia",
        "airport": "HND",
        "lat": 35.6762,
        "lon": 139.6503,
        "types": ["Food and cuisine", "Modern architecture", "Cultural sites"],
        "climate": "humid urban weather with strong seasonal swings",
        "geography": "dense megacity of rail hubs and waterfront districts",
        "buffer": 84,
    },
    "Kyoto": {
        "country": "Japan",
        "region": "Asia",
        "airport": "KIX",
        "lat": 35.0116,
        "lon": 135.7681,
        "types": ["Cultural sites", "Historical monuments", "Food and cuisine", "Natural landscapes"],
        "climate": "seasonal basin weather with humid summers",
        "geography": "temple basin ringed by forested hills",
        "buffer": 68,
    },
    "Seoul": {
        "country": "South Korea",
        "region": "Asia",
        "airport": "ICN",
        "lat": 37.5665,
        "lon": 126.9780,
        "types": ["Food and cuisine", "Cultural sites", "Modern architecture"],
        "climate": "four-season weather with humid summers and dry winters",
        "geography": "high-rise districts divided by river and mountain ridges",
        "buffer": 72,
    },
    "Vancouver": {
        "country": "Canada",
        "region": "North America",
        "airport": "YVR",
        "lat": 49.2827,
        "lon": -123.1207,
        "types": ["Natural landscapes", "Food and cuisine", "Cultural sites"],
        "climate": "temperate coastal rain with mountain air",
        "geography": "harbor city between sea and forested peaks",
        "buffer": 86,
    },
    "Istanbul": {
        "country": "Turkey",
        "region": "Europe",
        "airport": "IST",
        "lat": 41.0082,
        "lon": 28.9784,
        "types": ["Historical monuments", "Food and cuisine", "Cultural sites"],
        "climate": "sea-influenced weather with warm afternoons",
        "geography": "cross-continental city divided by waterways and hills",
        "buffer": 66,
    },
    "Amsterdam": {
        "country": "Netherlands",
        "region": "Europe",
        "airport": "AMS",
        "lat": 52.3676,
        "lon": 4.9041,
        "types": ["Cultural sites", "Food and cuisine", "Modern architecture"],
        "climate": "mild maritime weather with frequent cloud cover",
        "geography": "canal ring neighborhoods and bike-first streets",
        "buffer": 82,
    },
    "Munich": {
        "country": "Germany",
        "region": "Europe",
        "airport": "MUC",
        "lat": 48.1351,
        "lon": 11.5820,
        "types": ["Historical monuments", "Food and cuisine", "Natural landscapes"],
        "climate": "temperate seasons with alpine weather shifts nearby",
        "geography": "broad avenues with easy mountain access",
        "buffer": 76,
    },
    "Budapest": {
        "country": "Hungary",
        "region": "Europe",
        "airport": "BUD",
        "lat": 47.4979,
        "lon": 19.0402,
        "types": ["Historical monuments", "Cultural sites", "Food and cuisine"],
        "climate": "warm continental summers with cool nights",
        "geography": "river city divided by hills and grand boulevards",
        "buffer": 64,
    },
    "Osaka": {
        "country": "Japan",
        "region": "Asia",
        "airport": "KIX",
        "lat": 34.6937,
        "lon": 135.5023,
        "types": ["Food and cuisine", "Modern architecture", "Cultural sites"],
        "climate": "humid city weather with hot summers",
        "geography": "canal-lined commercial neighborhoods and bayside access",
        "buffer": 70,
    },
}


COUNTRY_SOURCES = {
    "United States": [
        {"label": "U.S. Customs and Border Protection", "url": "https://www.cbp.gov/"},
        {"label": "TSA prohibited items", "url": "https://www.tsa.gov/travel/security-screening/whatcanibring/all-list"},
    ],
    "Italy": [
        {"label": "Italian Customs and Monopolies Agency", "url": "https://www.adm.gov.it/portale/en/web/english"},
        {"label": "ENAC drone rules", "url": "https://www.enac.gov.it/en/safety-security/drone"},
    ],
    "Spain": [
        {"label": "Spanish customs information", "url": "https://sede.agenciatributaria.gob.es/"},
        {"label": "AESA drone guidance", "url": "https://www.seguridadaerea.gob.es/en/ambitos/drones"},
    ],
    "Portugal": [
        {"label": "Portuguese customs information", "url": "https://info-aduaneiro.portaldasfinancas.gov.pt/"},
        {"label": "Portuguese aviation authority", "url": "https://www.anac.pt/"},
    ],
    "France": [
        {"label": "French customs", "url": "https://www.douane.gouv.fr/"},
        {"label": "French drone rules", "url": "https://www.ecologie.gouv.fr/politiques-publiques/drones-loisir-professionnel"},
    ],
    "Czech Republic": [
        {"label": "Czech Customs Administration", "url": "https://www.celnisprava.cz/en/"},
        {"label": "Civil Aviation Authority", "url": "https://www.caa.cz/en/"},
    ],
    "Austria": [
        {"label": "Austrian customs", "url": "https://www.bmf.gv.at/en/topics/customs.html"},
        {"label": "Austro Control drone guidance", "url": "https://www.dronespace.at/en/"},
    ],
    "Japan": [
        {"label": "Japan Customs prohibited items", "url": "https://www.customs.go.jp/english/summary/prohibit.htm"},
        {"label": "Japan MLIT drone rules", "url": "https://www.mlit.go.jp/koku/drone/en/"},
    ],
    "South Korea": [
        {"label": "Korea Customs Service", "url": "https://www.customs.go.kr/english/main.do"},
        {"label": "Korea drone portal", "url": "https://drone.onestop.go.kr/"},
    ],
    "Canada": [
        {"label": "Canada Border Services Agency", "url": "https://www.cbsa-asfc.gc.ca/travel-voyage/menu-eng.html"},
        {"label": "Transport Canada drone rules", "url": "https://tc.canada.ca/en/aviation/drone-safety"},
    ],
    "Turkey": [
        {"label": "Republic of Türkiye Trade Ministry", "url": "https://ticaret.gov.tr/"},
        {"label": "Turkish drone rules", "url": "https://web.shgm.gov.tr/en/s/2929-drones"},
    ],
    "Netherlands": [
        {"label": "Dutch customs", "url": "https://www.belastingdienst.nl/wps/wcm/connect/en/customs/customs"},
        {"label": "Netherlands drone rules", "url": "https://www.government.nl/topics/drone"},
    ],
    "Germany": [
        {"label": "German customs", "url": "https://www.zoll.de/EN/Home/home_node.html"},
        {"label": "German drone rules", "url": "https://www.lba.de/EN/Drone/UAS_operator/UAS_operator_node.html"},
    ],
    "Hungary": [
        {"label": "Hungarian customs", "url": "https://nav.gov.hu/en/customs"},
        {"label": "Hungarian aviation authority", "url": "https://www.kavk.hu/"},
    ],
}


ATTRACTION_TEMPLATES = {
    "Natural landscapes": [
        {"name": "{city} scenic ridge walk", "cost": 0, "hours": "Open all day"},
        {"name": "{city} waterfront outlook", "cost": 12, "hours": "08:00-20:00"},
        {"name": "{city} botanical garden circuit", "cost": 18, "hours": "09:00-18:00"},
    ],
    "Historical monuments": [
        {"name": "{city} old quarter pass", "cost": 24, "hours": "09:00-18:00"},
        {"name": "{city} citadel and heritage loop", "cost": 19, "hours": "10:00-17:30"},
        {"name": "{city} cathedral terraces", "cost": 16, "hours": "09:30-18:00"},
    ],
    "Modern architecture": [
        {"name": "{city} design district circuit", "cost": 14, "hours": "10:00-20:00"},
        {"name": "{city} skyline observation deck", "cost": 28, "hours": "10:00-22:00"},
        {"name": "{city} architecture river cruise", "cost": 22, "hours": "11:00-21:00"},
    ],
    "Cultural sites": [
        {"name": "{city} museum quarter pass", "cost": 21, "hours": "10:00-18:00"},
        {"name": "{city} neighborhood culture walk", "cost": 15, "hours": "11:00-19:00"},
        {"name": "{city} evening performance ticket", "cost": 34, "hours": "19:00-22:30"},
    ],
    "Food and cuisine": [
        {"name": "{city} market tasting trail", "cost": 26, "hours": "10:00-17:00"},
        {"name": "{city} chef-led supper crawl", "cost": 42, "hours": "18:00-22:00"},
        {"name": "{city} bakery and coffee route", "cost": 18, "hours": "08:00-13:00"},
    ],
    "Adventure activities": [
        {"name": "{city} guided outdoor challenge", "cost": 54, "hours": "08:00-15:00"},
        {"name": "{city} high-view zip or climb session", "cost": 58, "hours": "09:00-16:00"},
        {"name": "{city} dawn adrenaline circuit", "cost": 48, "hours": "06:00-10:00"},
    ],
}


HOTEL_TEMPLATES = [
    {"suffix": "Ledger House", "area": "historic core", "fits": ["Historical monuments", "Cultural sites"], "rate": 198},
    {"suffix": "Current Hotel", "area": "food district", "fits": ["Food and cuisine", "Modern architecture"], "rate": 214},
    {"suffix": "Harbor Suites", "area": "waterfront", "fits": ["Natural landscapes", "Food and cuisine"], "rate": 226},
]


MAP_LAYOUT = [
    (32, 34, 102, 66),
    (146, 42, 98, 64),
    (40, 126, 104, 62),
    (152, 132, 94, 58),
    (208, 34, 78, 56),
]


RISK_PATTERNS = [
    ["low", "low", "medium", "high", "medium"],
    ["low", "medium", "low", "high", "medium"],
    ["low", "medium", "medium", "high", "low"],
]


def _stable_hash(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _title_slug(name: str) -> str:
    return "".join(character for character in name if character.isalnum())[:14] or "City"


def get_city_profile(city_name: str) -> dict:
    base = deepcopy(CITY_BASES.get(city_name, _build_fallback_base(city_name)))
    base["name"] = city_name
    base["attractions"] = _generate_attractions(city_name, base["types"])
    base["hotels"] = _generate_hotels(city_name, base["types"])
    base["neighborhoods"] = _generate_neighborhoods(city_name, base["geography"])
    base["compliance"] = _generate_compliance(base)
    return base


def candidate_cities() -> list[dict]:
    return [get_city_profile(name) for name in CITY_BASES]


def _build_fallback_base(city_name: str) -> dict:
    seed = _stable_hash(city_name)
    return {
        "country": "Custom route",
        "region": "Flexible",
        "airport": _title_slug(city_name).upper()[:3],
        "lat": 18 + (seed % 52),
        "lon": -40 + ((seed // 17) % 140),
        "types": ["Cultural sites", "Food and cuisine", "Historical monuments"],
        "climate": "variable seasonal weather with moderate swings",
        "geography": "mixed urban surroundings with day-trip access",
        "buffer": 70,
    }


def _generate_attractions(city_name: str, attraction_types: list[str]) -> list[dict]:
    ordered_types = list(dict.fromkeys(attraction_types + ["Cultural sites", "Food and cuisine", "Historical monuments"]))
    seen = set()
    attractions = []
    for attraction_type in ordered_types:
        templates = ATTRACTION_TEMPLATES.get(attraction_type, [])
        for template in templates[:1]:
            name = template["name"].format(city=city_name.title())
            if name in seen:
                continue
            seen.add(name)
            attractions.append(
                {
                    "name": name,
                    "type": attraction_type,
                    "cost": template["cost"] + (_stable_hash(name) % 7),
                    "hours": template["hours"],
                }
            )
        if len(attractions) >= 4:
            break
    return attractions


def _generate_hotels(city_name: str, attraction_types: list[str]) -> list[dict]:
    hotels = []
    for template in HOTEL_TEMPLATES:
        hotel_name = f"{city_name.title()} {template['suffix']}"
        hotels.append(
            {
                "name": hotel_name,
                "area": template["area"],
                "rate": template["rate"] + (_stable_hash(hotel_name) % 28),
                "fits": [fit for fit in template["fits"] if fit in attraction_types] or template["fits"],
            }
        )
    return hotels


def _generate_neighborhoods(city_name: str, geography: str) -> list[dict]:
    seed = _stable_hash(city_name)
    area_names = [
        "historic core",
        "museum district",
        "market quarter",
        "transit belt",
        "waterfront" if any(word in geography.lower() for word in ["coast", "water", "river", "lagoon", "harbor"]) else "creative district",
    ]
    risks = RISK_PATTERNS[seed % len(RISK_PATTERNS)]
    neighborhoods = []
    for index, layout in enumerate(MAP_LAYOUT):
        x, y, width, height = layout
        neighborhoods.append(
            {
                "name": area_names[index].title(),
                "risk": risks[index],
                "x": x,
                "y": y,
                "w": width,
                "h": height,
            }
        )
    return neighborhoods


def _generate_compliance(profile: dict) -> dict:
    country = profile["country"]
    geometry = profile["geography"]
    destination_items = [
        "Fireworks, replica weapons, large knives, and hazardous materials may be restricted or confiscated.",
        "Drone use near dense urban areas, protected sites, or airports typically requires prior authorization.",
        "Fresh meats, plant products, undeclared cash, and some medications can trigger customs review.",
    ]
    if any(word in geometry.lower() for word in ["water", "lagoon", "coast", "harbor"]):
        destination_items.append("Glass containers, open flames, and some recreation gear can be restricted around waterfront or ferry areas.")
    sources = deepcopy(COUNTRY_SOURCES.get(country, [{"label": "IATA travel centre", "url": "https://www.iatatravelcentre.com/"}]))
    return {"destination": destination_items[:3], "sources": sources}
