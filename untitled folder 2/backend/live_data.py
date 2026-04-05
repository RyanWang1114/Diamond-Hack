from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import date, datetime
from urllib.parse import urlencode


REGION_BY_COUNTRY = {
    "United States": "North America",
    "Canada": "North America",
    "Mexico": "North America",
    "Italy": "Europe",
    "Spain": "Europe",
    "Portugal": "Europe",
    "France": "Europe",
    "Czech Republic": "Europe",
    "Austria": "Europe",
    "Turkey": "Europe",
    "Netherlands": "Europe",
    "Germany": "Europe",
    "Hungary": "Europe",
    "Japan": "Asia",
    "South Korea": "Asia",
    "China": "Asia",
    "Thailand": "Asia",
    "Vietnam": "Asia",
    "Indonesia": "Asia",
    "Australia": "Oceania",
    "New Zealand": "Oceania",
    "Brazil": "South America",
    "Argentina": "South America",
    "Chile": "South America",
    "South Africa": "Africa",
    "Morocco": "Africa",
    "Egypt": "Africa",
}


class LiveDataClient:
    def __init__(self) -> None:
        self.openweather_api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
        self.google_places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
        self.rapid_api_key = os.getenv("RAPID_API_KEY", "").strip() or os.getenv("RAPIDAPI_KEY", "").strip()
        self.rapid_api_host = os.getenv("RAPID_API_HOST", "booking-com15.p.rapidapi.com").strip() or "booking-com15.p.rapidapi.com"
        self.mapbox_token = os.getenv("MAPBOX_TOKEN", "").strip()
        self.secret_key = os.getenv("SECRET_KEY", "").strip()
        self.timeout_seconds = max(5, int(os.getenv("ATLAS_LANE_DATA_TIMEOUT", "10") or "10"))
        self.cache_ttl_seconds = max(300, int(os.getenv("ATLAS_LANE_CACHE_TTL", "1800") or "1800"))
        self._cache: dict[str, tuple[float, object]] = {}

    @property
    def live_sources_summary(self) -> dict:
        return {
            "openweather": bool(self.openweather_api_key),
            "googlePlaces": bool(self.google_places_api_key),
            "placesProvider": self.places_provider,
            "rapidApi": bool(self.rapid_api_key),
            "rapidApiHost": self.rapid_api_host if self.rapid_api_key else "",
            "mapbox": bool(self.mapbox_token),
            "secretKey": bool(self.secret_key),
        }

    @property
    def places_provider(self) -> str:
        if not self.google_places_api_key:
            return "none"
        if self.google_places_api_key.startswith("apify_api_"):
            return "apify"
        return "google"

    def enrich_city_profile(self, profile: dict) -> dict:
        enriched = deepcopy(profile)
        geo = self.resolve_city(enriched["name"])
        if geo:
            enriched["lat"] = geo["lat"]
            enriched["lon"] = geo["lon"]
            if geo.get("country"):
                enriched["country"] = geo["country"]
                enriched["region"] = infer_region(geo["country"], enriched.get("region"))
            if geo.get("displayName"):
                enriched["displayName"] = geo["displayName"]
        enriched["mapImageUrl"] = self.build_static_map_url(enriched.get("lat"), enriched.get("lon"))
        live_hotels = self.search_places(
            enriched["name"],
            query=f"hotels in {enriched['name']}",
            kind="hotel",
            lat=enriched.get("lat"),
            lon=enriched.get("lon"),
            limit=4,
        )
        if live_hotels:
            enriched["hotels"] = merge_live_hotels(live_hotels, enriched["hotels"], enriched["types"])
        live_attractions = self.search_places(
            enriched["name"],
            query=f"top tourist attractions in {enriched['name']}",
            kind="attraction",
            lat=enriched.get("lat"),
            lon=enriched.get("lon"),
            limit=5,
        )
        if live_attractions:
            enriched["attractions"] = merge_live_attractions(live_attractions, enriched["attractions"], enriched["types"])
        return enriched

    def resolve_city(self, city_name: str) -> dict | None:
        if not self.mapbox_token or not city_name:
            return None
        cache_key = f"geo:{city_name.lower()}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        query = urllib.parse.quote(city_name)
        url = (
            f"https://api.mapbox.com/search/geocode/v6/forward?q={query}"
            f"&types=place&limit=1&language=en&access_token={self.mapbox_token}"
        )
        try:
            payload = self._request_json(url)
        except RuntimeError:
            self._write_cache(cache_key, None)
            return None
        features = payload.get("features") or []
        if not features:
            self._write_cache(cache_key, None)
            return None
        feature = features[0]
        coordinates = ((feature.get("geometry") or {}).get("coordinates") or [None, None])
        properties = feature.get("properties") or {}
        context = properties.get("context") or {}
        country = ""
        if isinstance(context, dict):
            country_context = context.get("country") or {}
            if isinstance(country_context, dict):
                country = country_context.get("name", "")
        result = {
            "lat": coordinates[1],
            "lon": coordinates[0],
            "country": country,
            "displayName": properties.get("full_address") or properties.get("name") or city_name,
        }
        self._write_cache(cache_key, result)
        return result

    def build_static_map_url(self, lat: float | None, lon: float | None) -> str | None:
        if not self.mapbox_token or lat is None or lon is None:
            return None
        return (
            "https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/"
            f"pin-s+116b72({lon},{lat})/{lon},{lat},11.2/640x360"
            f"?access_token={self.mapbox_token}"
        )

    def weather_for_trip(self, city_name: str, lat: float | None, lon: float | None, start_date: str, end_date: str) -> dict | None:
        if not self.openweather_api_key or lat is None or lon is None:
            return None
        cache_key = f"weather:{city_name.lower()}:{start_date}:{end_date}:{round(lat, 2)}:{round(lon, 2)}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        url = (
            "https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={lat}&lon={lon}&appid={self.openweather_api_key}&units=imperial"
        )
        try:
            payload = self._request_json(url)
        except RuntimeError:
            self._write_cache(cache_key, None)
            return None
        entries = payload.get("list") or []
        if not entries:
            self._write_cache(cache_key, None)
            return None
        requested_start = parse_iso_date(start_date)
        requested_end = parse_iso_date(end_date)
        grouped: dict[str, list[dict]] = {}
        for entry in entries:
            dt_txt = str(entry.get("dt_txt", ""))
            day_key = dt_txt[:10]
            if day_key:
                grouped.setdefault(day_key, []).append(entry)
        matching_days = [day for day in sorted(grouped) if requested_start <= parse_iso_date(day) <= requested_end]
        selected_days = matching_days or sorted(grouped)[: min(3, len(grouped))]
        day_cards = []
        all_temps = []
        conditions = []
        for day in selected_days:
            day_entries = grouped.get(day, [])
            temps = [float(item.get("main", {}).get("temp", 0)) for item in day_entries if item.get("main")]
            descriptions = [
                str((item.get("weather") or [{}])[0].get("description", "")).strip()
                for item in day_entries
                if item.get("weather")
            ]
            winds = [float(item.get("wind", {}).get("speed", 0)) for item in day_entries if item.get("wind")]
            rain = [
                float(item.get("rain", {}).get("3h", 0))
                for item in day_entries
                if isinstance(item.get("rain"), dict)
            ]
            if temps:
                all_temps.extend(temps)
            if descriptions:
                conditions.extend(descriptions)
            day_cards.append(
                {
                    "date": day,
                    "lowF": round(min(temps)) if temps else None,
                    "highF": round(max(temps)) if temps else None,
                    "condition": most_common_text(descriptions) or "mixed conditions",
                    "windMph": round(max(winds), 1) if winds else 0,
                    "rainMm": round(sum(rain), 1) if rain else 0,
                }
            )
        coverage_start = parse_iso_date(selected_days[0]) if selected_days else requested_start
        coverage_end = parse_iso_date(selected_days[-1]) if selected_days else requested_end
        summary = {
            "source": "OpenWeather 5-day forecast",
            "headline": build_weather_headline(day_cards, coverage_start, coverage_end),
            "note": "" if matching_days else "Live forecast coverage is limited to the next 5 days, so this is a near-term preview.",
            "days": day_cards,
            "packHint": build_pack_hint(all_temps, conditions),
        }
        self._write_cache(cache_key, summary)
        return summary

    def search_hotel_offers(
        self,
        city_name: str,
        *,
        lat: float | None,
        lon: float | None,
        arrival_date: str,
        departure_date: str,
        adults: int,
        room_qty: int,
        currency_code: str = "USD",
    ) -> list[dict]:
        if not self.rapid_api_key:
            return []
        cache_key = f"rapid:hotel:{city_name.lower()}:{arrival_date}:{departure_date}:{adults}:{room_qty}:{currency_code}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        results = []
        destination = self._rapid_search_hotel_destination(city_name)
        try:
            if destination:
                params = {
                    "dest_id": destination.get("dest_id") or destination.get("destId") or destination.get("id"),
                    "search_type": destination.get("search_type") or destination.get("searchType") or destination.get("dest_type") or destination.get("destType"),
                    "arrival_date": arrival_date,
                    "departure_date": departure_date,
                    "adults": adults,
                    "room_qty": room_qty,
                    "page_number": 1,
                    "units": "metric",
                    "temperature_unit": "c",
                    "languagecode": "en-us",
                    "currency_code": currency_code,
                }
                payload = self._rapid_request_json("/api/v1/hotels/searchHotels", params)
                results = normalize_rapid_hotel_results(payload, arrival_date, departure_date)
            elif lat is not None and lon is not None:
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "arrival_date": arrival_date,
                    "departure_date": departure_date,
                    "radius": 25,
                    "adults": adults,
                    "room_qty": room_qty,
                    "page_number": 1,
                    "units": "metric",
                    "temperature_unit": "c",
                    "languagecode": "en-us",
                    "currency_code": currency_code,
                }
                payload = self._rapid_request_json("/api/v1/hotels/searchHotelsByCoordinates", params)
                results = normalize_rapid_hotel_results(payload, arrival_date, departure_date)
        except RuntimeError:
            results = []

        enriched = []
        for hotel in results[:4]:
            if not hotel.get("url") and hotel.get("hotelId"):
                try:
                    details = self._rapid_request_json(
                        "/api/v1/hotels/getHotelDetails",
                        {
                            "hotel_id": hotel["hotelId"],
                            "arrival_date": arrival_date,
                            "departure_date": departure_date,
                            "adults": adults,
                            "room_qty": room_qty,
                            "units": "metric",
                            "temperature_unit": "c",
                            "languagecode": "en-us",
                            "currency_code": currency_code,
                        },
                    )
                    hotel["url"] = extract_best_url(details, allow_booking_only=True) or hotel.get("url", "")
                except RuntimeError:
                    pass
            enriched.append(hotel)
        self._write_cache(cache_key, enriched)
        return enriched

    def search_flight_offers(
        self,
        *,
        from_id: str,
        to_id: str,
        depart_date: str,
        return_date: str,
        adults: int,
        currency_code: str = "USD",
        sort: str = "CHEAPEST",
        cabin_class: str = "ECONOMY",
    ) -> list[dict]:
        if not self.rapid_api_key:
            return []
        cache_key = f"rapid:flight:{from_id}:{to_id}:{depart_date}:{return_date}:{adults}:{currency_code}:{sort}:{cabin_class}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        try:
            payload = self._rapid_request_json(
                "/api/v1/flights/searchFlights",
                {
                    "fromId": from_id,
                    "toId": to_id,
                    "departDate": depart_date,
                    "returnDate": return_date,
                    "stops": "none",
                    "pageNo": 1,
                    "adults": adults,
                    "children": "0,17",
                    "sort": sort,
                    "cabinClass": cabin_class,
                    "currency_code": currency_code,
                },
            )
        except RuntimeError:
            self._write_cache(cache_key, [])
            return []
        offers = normalize_rapid_flight_results(payload)
        for offer in offers[:4]:
            if not offer.get("url") and offer.get("token"):
                try:
                    details = self._rapid_request_json(
                        "/api/v1/flights/getFlightDetails",
                        {"token": offer["token"], "currency_code": currency_code},
                    )
                    offer["url"] = extract_best_url(details, allow_booking_only=False) or offer.get("url", "")
                except RuntimeError:
                    pass
        self._write_cache(cache_key, offers[:4])
        return offers[:4]

    def search_places(
        self,
        city_name: str,
        *,
        query: str,
        kind: str,
        lat: float | None,
        lon: float | None,
        limit: int,
    ) -> list[dict]:
        if not self.google_places_api_key:
            return []
        cache_key = f"places:{city_name.lower()}:{kind}:{query.lower()}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        if self.places_provider == "apify":
            results = self._search_places_via_apify(city_name, query=query, kind=kind, limit=limit)
            self._write_cache(cache_key, results)
            return results
        results = self._search_places_via_google(query=query, kind=kind, lat=lat, lon=lon, limit=limit)
        self._write_cache(cache_key, results)
        return results

    def _search_places_via_google(
        self,
        *,
        query: str,
        kind: str,
        lat: float | None,
        lon: float | None,
        limit: int,
    ) -> list[dict]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.google_places_api_key,
            "X-Goog-FieldMask": ",".join(
                [
                    "places.id",
                    "places.displayName",
                    "places.formattedAddress",
                    "places.location",
                    "places.rating",
                    "places.userRatingCount",
                    "places.priceLevel",
                    "places.primaryType",
                    "places.googleMapsUri",
                    "places.websiteUri",
                    "places.regularOpeningHours",
                ]
            ),
        }
        body: dict[str, object] = {
            "textQuery": query,
            "languageCode": "en",
            "pageSize": limit,
        }
        if kind == "attraction":
            body["includedType"] = "tourist_attraction"
            body["strictTypeFiltering"] = False
        if lat is not None and lon is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": 8500.0,
                }
            }
        try:
            payload = self._request_json(
                "https://places.googleapis.com/v1/places:searchText",
                method="POST",
                headers=headers,
                payload=body,
            )
        except RuntimeError:
            return []
        places = [normalize_google_place(item, kind) for item in (payload.get("places") or [])]
        return [place for place in places if place]

    def _search_places_via_apify(self, city_name: str, *, query: str, kind: str, limit: int) -> list[dict]:
        keywords = [query.split(" in ", 1)[0].strip() or kind]
        payload = {
            "locations": [city_name],
            "keywords": keywords,
            "urls": [],
            "maxCrawledPlacesPerSearch": limit,
            "language": "en",
            "proxyConfiguration": {"useApifyProxy": False},
        }
        url = (
            "https://api.apify.com/v2/acts/scraper-engine~google-maps-scraper/"
            f"run-sync-get-dataset-items?token={urllib.parse.quote(self.google_places_api_key)}&timeout=90"
        )
        try:
            items = self._request_json(url, method="POST", headers={"Content-Type": "application/json"}, payload=payload)
        except RuntimeError:
            return []
        if not isinstance(items, list):
            return []
        results = [normalize_apify_place(item, kind) for item in items]
        return [item for item in results if item]

    def _rapid_search_hotel_destination(self, city_name: str) -> dict | None:
        cache_key = f"rapid:hotel-destination:{city_name.lower()}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        try:
            payload = self._rapid_request_json(
                "/api/v1/hotels/searchDestination",
                {"query": city_name, "locale": "en-us"},
            )
        except RuntimeError:
            self._write_cache(cache_key, None)
            return None
        destination = normalize_rapid_destination(payload)
        self._write_cache(cache_key, destination)
        return destination

    def _rapid_request_json(self, path: str, params: dict) -> dict:
        query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
        url = f"https://{self.rapid_api_host}{path}?{query}" if query else f"https://{self.rapid_api_host}{path}"
        return self._request_json(
            url,
            headers={
                "x-rapidapi-key": self.rapid_api_key,
                "x-rapidapi-host": self.rapid_api_host,
            },
        )

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        payload: dict | None = None,
    ):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=headers or {},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Live data API error {error.code}: {body}") from error
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            raise RuntimeError(f"Live data request failed: {error}") from error

    def _read_cache(self, cache_key: str):
        cached = self._cache.get(cache_key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at < time.time():
            self._cache.pop(cache_key, None)
            return None
        return deepcopy(value)

    def _write_cache(self, cache_key: str, value) -> None:
        self._cache[cache_key] = (time.time() + self.cache_ttl_seconds, deepcopy(value))


def normalize_google_place(place: dict, kind: str) -> dict | None:
    display_name = place.get("displayName") or {}
    name = display_name.get("text") if isinstance(display_name, dict) else str(display_name or "")
    if not name:
        return None
    address = str(place.get("formattedAddress", "")).strip()
    opening_hours = place.get("regularOpeningHours") or {}
    price_level = str(place.get("priceLevel", "")).strip()
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    location = place.get("location") or {}
    return {
        "id": str(place.get("id", "")).strip(),
        "name": name,
        "address": address,
        "primaryType": str(place.get("primaryType", "")).strip(),
        "rating": float(rating) if isinstance(rating, (int, float)) else None,
        "reviewCount": int(review_count) if isinstance(review_count, (int, float)) else None,
        "priceLevel": price_level,
        "googleMapsUri": str(place.get("googleMapsUri", "")).strip(),
        "websiteUri": str(place.get("websiteUri", "")).strip(),
        "hours": summarize_opening_hours(opening_hours),
        "lat": location.get("latitude"),
        "lon": location.get("longitude"),
        "kind": kind,
    }


def normalize_apify_place(place: dict, kind: str) -> dict | None:
    if not isinstance(place, dict):
        return None
    name = str(place.get("title") or place.get("name") or "").strip()
    if not name:
        return None
    address = str(place.get("address") or place.get("street") or "").strip()
    rating = place.get("totalScore") or place.get("rating") or place.get("stars")
    review_count = place.get("reviewsCount") or place.get("reviewCount") or place.get("reviews")
    hours = place.get("openingHours") or place.get("openingHoursText") or place.get("opening_hours")
    if isinstance(hours, list):
        hours = " · ".join(str(item) for item in hours[:2])
    return {
        "id": str(place.get("placeId") or place.get("cid") or "").strip(),
        "name": name,
        "address": address,
        "primaryType": str(place.get("categoryName") or place.get("category") or "").strip(),
        "rating": float(rating) if isinstance(rating, (int, float)) else None,
        "reviewCount": int(review_count) if isinstance(review_count, (int, float)) else None,
        "priceLevel": "",
        "googleMapsUri": str(place.get("url") or place.get("googleUrl") or "").strip(),
        "websiteUri": str(place.get("website") or place.get("websiteUrl") or "").strip(),
        "hours": str(hours or "").strip(),
        "lat": place.get("location", {}).get("lat") if isinstance(place.get("location"), dict) else place.get("latitude"),
        "lon": place.get("location", {}).get("lng") if isinstance(place.get("location"), dict) else place.get("longitude"),
        "kind": kind,
    }


def normalize_rapid_destination(payload: dict) -> dict | None:
    items = find_candidate_items(payload, preferred_keys={"data", "result", "results", "destinations"})
    for item in items:
        dest_id = item.get("dest_id") or item.get("destId") or item.get("id")
        search_type = item.get("search_type") or item.get("searchType") or item.get("dest_type") or item.get("destType")
        if dest_id and search_type:
            return {
                "dest_id": dest_id,
                "search_type": search_type,
                "name": item.get("name") or item.get("city_name") or item.get("label") or "",
            }
    return None


def normalize_rapid_hotel_results(payload: dict, arrival_date: str, departure_date: str) -> list[dict]:
    items = find_candidate_items(payload, preferred_keys={"hotels", "property", "properties", "results", "result"})
    hotels = []
    seen = set()
    for item in items:
        name = first_non_empty_string(
            item,
            [
                ("property", "name"),
                ("hotel_name",),
                ("name",),
                ("wishlistName",),
                ("hotelName",),
                ("title",),
            ],
        )
        if not name:
            continue
        normalized_name = name.lower()
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        nightly = first_number(
            item,
            [
                ("property", "priceBreakdown", "grossPrice", "value"),
                ("priceBreakdown", "grossPrice", "value"),
                ("property", "composite_price_breakdown", "gross_amount", "value"),
                ("composite_price_breakdown", "gross_amount", "value"),
                ("min_total_price",),
                ("price",),
            ],
        )
        total = nightly
        if total is None:
            total = first_number(
                item,
                [
                    ("priceBreakdown", "allInclusivePrice", "value"),
                    ("property", "priceBreakdown", "allInclusivePrice", "value"),
                ],
            )
        if nightly is None and total is not None:
            nights = max(1, (parse_iso_date(departure_date) - parse_iso_date(arrival_date)).days)
            nightly = round(total / max(nights, 1))
        url = extract_best_url(item, allow_booking_only=True)
        hotels.append(
            {
                "hotelId": first_non_empty_string(item, [("hotel_id",), ("hotelId",), ("property", "id"), ("id",)]),
                "name": name,
                "area": short_area(
                    first_non_empty_string(item, [("accessibilityLabel",), ("address",), ("property", "address"), ("city",)])
                ),
                "address": first_non_empty_string(item, [("address",), ("property", "address"), ("city",)]),
                "nightlyRate": round(nightly) if nightly is not None else None,
                "totalCost": round(total) if total is not None else round(nightly or 0),
                "rating": first_number(item, [("reviewScore",), ("reviewScoreValue",), ("property", "reviewScore")]),
                "reviewCount": first_int(item, [("reviewCount",), ("reviewsCount",), ("review_nr",)]),
                "source": "RapidAPI Booking.com",
                "url": url or "",
            }
        )
        if len(hotels) >= 6:
            break
    return hotels


def normalize_rapid_flight_results(payload: dict) -> list[dict]:
    items = find_candidate_items(payload, preferred_keys={"flightOffers", "flights", "results", "result", "offers"})
    offers = []
    for item in items:
        airline = first_non_empty_string(
            item,
            [
                ("segments", 0, "legs", 0, "carriers", "marketing", 0, "name"),
                ("segments", 0, "legs", 0, "carriers", "marketing", "name"),
                ("carrierName",),
                ("airline",),
                ("carrier",),
                ("companyName",),
            ],
        )
        if not airline:
            continue
        price = first_number(
            item,
            [
                ("priceBreakdown", "total", "units"),
                ("priceBreakdown", "total", "value"),
                ("price", "amount"),
                ("price",),
                ("totalPrice",),
            ],
        )
        token = first_non_empty_string(item, [("token",), ("offerToken",), ("searchToken",)])
        offers.append(
            {
                "token": token,
                "airline": airline,
                "aircraft": first_non_empty_string(
                    item,
                    [
                        ("segments", 0, "legs", 0, "equipment", "name"),
                        ("segments", 0, "legs", 0, "aircraftType", "name"),
                        ("aircraft",),
                    ],
                )
                or "Aircraft details pending",
                "price": round(price) if price is not None else None,
                "durationHours": round((first_int(item, [("segments", 0, "totalTime"), ("travelTime",)]) or 0) / 60, 1) or None,
                "stops": first_int(item, [("segments", 0, "legs",)]),
                "checkedAllowance": first_int(
                    item,
                    [
                        ("extraProductDisplayRequirements", "baggage", "checked", "quantity"),
                        ("baggageAllowance", "checked"),
                    ],
                ),
                "carryOn": first_non_empty_string(
                    item,
                    [
                        ("extraProductDisplayRequirements", "baggage", "carryOn", "description"),
                        ("baggageAllowance", "carryOn"),
                    ],
                )
                or "",
                "url": extract_best_url(item, allow_booking_only=False) or "",
            }
        )
        if len(offers) >= 6:
            break
    return offers


def merge_live_hotels(live_places: list[dict], fallback_hotels: list[dict], attraction_types: list[str]) -> list[dict]:
    hotels = []
    seen = set()
    for place in live_places:
        seen.add(place["name"].lower())
        hotels.append(
            {
                "name": place["name"],
                "area": short_area(place["address"]),
                "rate": hotel_rate_from_price_level(place["priceLevel"]),
                "fits": attraction_types[:2] or ["Food and cuisine", "Cultural sites"],
                "source": "Google Places",
                "address": place["address"],
                "rating": place["rating"],
                "reviewCount": place["reviewCount"],
                "placeUrl": place["googleMapsUri"] or place["websiteUri"],
                "hours": place["hours"],
            }
        )
    for hotel in fallback_hotels:
        if hotel["name"].lower() in seen:
            continue
        hotels.append(hotel)
    return hotels[:4]


def merge_live_attractions(live_places: list[dict], fallback_attractions: list[dict], attraction_types: list[str]) -> list[dict]:
    attractions = []
    seen = set()
    default_type = attraction_types[0] if attraction_types else "Cultural sites"
    for place in live_places:
        seen.add(place["name"].lower())
        attractions.append(
            {
                "name": place["name"],
                "type": infer_attraction_type(place.get("primaryType", ""), default_type),
                "cost": attraction_cost_from_price_level(place["priceLevel"]),
                "hours": place["hours"] or "Check Google Maps schedule",
                "source": "Google Places",
                "address": place["address"],
                "rating": place["rating"],
                "reviewCount": place["reviewCount"],
                "placeUrl": place["googleMapsUri"] or place["websiteUri"],
            }
        )
    for attraction in fallback_attractions:
        if attraction["name"].lower() in seen:
            continue
        attractions.append(attraction)
    return attractions[:5]


def infer_region(country_name: str, fallback_region: str | None = None) -> str:
    return REGION_BY_COUNTRY.get(country_name, fallback_region or "Flexible")


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def most_common_text(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        normalized = value.strip().lower()
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


def build_weather_headline(day_cards: list[dict], requested_start: date, requested_end: date) -> str:
    if not day_cards:
        return "No live weather coverage available."
    low_values = [card["lowF"] for card in day_cards if card.get("lowF") is not None]
    high_values = [card["highF"] for card in day_cards if card.get("highF") is not None]
    if not low_values or not high_values:
        return "Live weather coverage is available for this city."
    low = min(low_values)
    high = max(high_values)
    lead_condition = day_cards[0].get("condition", "mixed conditions")
    return (
        f"{human_date(requested_start)} to {human_date(requested_end)} looks roughly "
        f"{low}F to {high}F with {lead_condition}."
    )


def build_pack_hint(temperatures: list[float], conditions: list[str]) -> str:
    if not temperatures:
        return "Pack flexible layers."
    low = min(temperatures)
    high = max(temperatures)
    condition_text = " ".join(conditions).lower()
    if "rain" in condition_text or "storm" in condition_text:
        return "Bring a light rain layer and shoes that can handle wet pavement."
    if high >= 85:
        return "Expect heat. Pack breathable clothing, sun coverage, and a refillable bottle."
    if low <= 45:
        return "Expect cooler stretches. Bring a warm layer and a compact jacket."
    return "Pack light layers for changing temperatures across the day."


def summarize_opening_hours(opening_hours: dict) -> str:
    if not isinstance(opening_hours, dict):
        return ""
    weekday_descriptions = opening_hours.get("weekdayDescriptions") or []
    if weekday_descriptions:
        return " · ".join(str(item) for item in weekday_descriptions[:2])
    return ""


def short_area(address: str) -> str:
    if not address:
        return "central area"
    pieces = [piece.strip() for piece in address.split(",") if piece.strip()]
    if len(pieces) >= 2:
        return pieces[1]
    return pieces[0]


def hotel_rate_from_price_level(price_level: str) -> int:
    mapping = {
        "PRICE_LEVEL_INEXPENSIVE": 135,
        "PRICE_LEVEL_MODERATE": 195,
        "PRICE_LEVEL_EXPENSIVE": 265,
        "PRICE_LEVEL_VERY_EXPENSIVE": 355,
    }
    return mapping.get(price_level, 210)


def attraction_cost_from_price_level(price_level: str) -> int:
    mapping = {
        "PRICE_LEVEL_INEXPENSIVE": 12,
        "PRICE_LEVEL_MODERATE": 26,
        "PRICE_LEVEL_EXPENSIVE": 38,
        "PRICE_LEVEL_VERY_EXPENSIVE": 52,
    }
    return mapping.get(price_level, 24)


def infer_attraction_type(primary_type: str, fallback_type: str) -> str:
    lowered = primary_type.lower()
    if "museum" in lowered or "art" in lowered:
        return "Cultural sites"
    if "tourist" in lowered or "monument" in lowered:
        return "Historical monuments"
    if "park" in lowered or "natural" in lowered:
        return "Natural landscapes"
    if "restaurant" in lowered or "food" in lowered:
        return "Food and cuisine"
    return fallback_type


def human_date(value: date) -> str:
    return value.strftime("%b %d").replace(" 0", " ")


def find_candidate_items(payload, preferred_keys: set[str]) -> list[dict]:
    candidates: list[tuple[int, list[dict]]] = []

    def walk(node, key_hint: str = "") -> None:
        if isinstance(node, list):
            dict_items = [item for item in node if isinstance(item, dict)]
            if dict_items:
                score = len(dict_items)
                if key_hint.lower() in preferred_keys:
                    score += 20
                candidates.append((score, dict_items))
            for item in node[:12]:
                walk(item, key_hint)
            return
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, str(key))

    walk(payload)
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def first_non_empty_string(node, paths: list[tuple]) -> str:
    for path in paths:
        value = dig(node, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in flatten_values(node):
        if isinstance(value, str) and value.strip().startswith("http"):
            continue
    return ""


def first_number(node, paths: list[tuple]) -> float | None:
    for path in paths:
        value = dig(node, path)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re_number(value)
            if match is not None:
                return match
    return None


def first_int(node, paths: list[tuple]) -> int | None:
    for path in paths:
        value = dig(node, path)
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return max(0, len(value) - 1)
        if isinstance(value, str):
            match = re_number(value)
            if match is not None:
                return int(round(match))
    return None


def extract_best_url(node, *, allow_booking_only: bool) -> str:
    urls = []
    for value in flatten_values(node):
        if isinstance(value, str) and value.startswith("http"):
            urls.append(value.strip())
    if not urls:
        return ""
    preferred_domains = ["booking.com", "trip.com", "expedia.", "kiwi.com", "skyscanner.", "airline.", "google.com"]
    if allow_booking_only:
        preferred_domains = ["booking.com", "expedia.", "trip.com", "agoda.com", "hotels.com"]
    for domain in preferred_domains:
        for url in urls:
            if domain in url:
                return url
    return urls[0]


def dig(node, path: tuple):
    current = node
    for part in path:
        if isinstance(part, int):
            if isinstance(current, list) and len(current) > part:
                current = current[part]
            else:
                return None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
    return current


def flatten_values(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from flatten_values(value)
    elif isinstance(node, list):
        for value in node[:20]:
            yield from flatten_values(value)
    else:
        yield node


def re_number(value: str) -> float | None:
    cleaned = []
    seen_digit = False
    for character in value:
        if character.isdigit() or character in {".", ","}:
            if character != ",":
                cleaned.append(character)
            seen_digit = True
        elif seen_digit:
            break
    try:
        return float("".join(cleaned)) if cleaned else None
    except ValueError:
        return None
