from __future__ import annotations

import ast
import difflib
import hashlib
import json
import math
import operator
import re
from copy import deepcopy
from datetime import date, datetime, timedelta
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import quote_plus, urlparse

from .catalog import candidate_cities, get_city_profile
from .live_data import LiveDataClient
from .openai_client import OpenAIClient, OpenAIError


class PlannerValidationError(ValueError):
    pass


PLATFORM_LIBRARY = {
    "SkyBridge": {"trusted": True, "score": 93, "categories": ["flight"]},
    "TripNest": {"trusted": True, "score": 89, "categories": ["flight", "hotel", "attraction", "ground"]},
    "OrbitCart": {"trusted": True, "score": 86, "categories": ["flight"]},
    "StayHarbor": {"trusted": True, "score": 92, "categories": ["hotel"]},
    "TicketMint": {"trusted": True, "score": 88, "categories": ["attraction"]},
    "RailCanvas": {"trusted": True, "score": 90, "categories": ["ground"]},
    "GetGoBus": {"trusted": True, "score": 84, "categories": ["ground"]},
    "FlashFare": {"trusted": False, "score": 22, "categories": ["flight", "hotel"]},
    "BargainRoost": {"trusted": False, "score": 18, "categories": ["hotel"]},
    "TicketBlitz": {"trusted": False, "score": 26, "categories": ["attraction"]},
}


AIRLINES = [
    {"name": "Aurora Atlantic", "aircraft": ["Boeing 787-9", "Airbus A350-900"], "baseChecked": 1, "carryOn": "1 cabin bag + personal item", "pace": 0.94},
    {"name": "Cinder Air", "aircraft": ["Airbus A330-900neo", "Boeing 777-300ER"], "baseChecked": 1, "carryOn": "1 carry-on", "pace": 0.92},
    {"name": "North Arrow", "aircraft": ["Boeing 737 MAX 8", "Airbus A321neo"], "baseChecked": 0, "carryOn": "Personal item only", "pace": 1.03},
    {"name": "Lumen Sky", "aircraft": ["Airbus A320neo", "Boeing 787-8"], "baseChecked": 1, "carryOn": "1 cabin bag", "pace": 0.99},
    {"name": "Meridian One", "aircraft": ["Boeing 767-300ER", "Airbus A321LR"], "baseChecked": 2, "carryOn": "1 cabin bag + personal item", "pace": 0.96},
]


GROUND_OPERATORS = {
    "train": "RailCanvas",
    "coach": "GetGoBus",
    "ferry": "TripNest",
}


GEORGE_KNOWLEDGE_BASE = [
    {
        "title": "workflow",
        "text": "Atlas Lane works in three steps: travel window search, detailed trip brief, and a results page with optional city suggestions and foldable transport, hotel, and tour sections.",
        "keywords": ["workflow", "how", "use", "steps", "search", "page", "results"],
    },
    {
        "title": "suggestions",
        "text": "City suggestions are based on attraction preferences, route geography, prior accepted cities, and skipped cities. Users can accept or decline suggestions before refreshing results.",
        "keywords": ["suggestion", "city", "stopover", "route", "add", "skip"],
    },
    {
        "title": "transport",
        "text": "Transportation results include flights and public transport where practical. Each transportation item can show price, aircraft or transport mode, duration, stops, baggage allowances, and purchase links.",
        "keywords": ["flight", "transport", "plane", "train", "bus", "ferry", "baggage", "bag", "luggage"],
    },
    {
        "title": "hotels",
        "text": "Hotel results prioritize locations near planned attractions and are weighted by personal and global learning signals from prior user choices.",
        "keywords": ["hotel", "stay", "room", "accommodation"],
    },
    {
        "title": "tours",
        "text": "Tour and attraction results include requested places first, then additional recommendations aligned with attraction types, saved preferences, and current pricing.",
        "keywords": ["tour", "attraction", "ticket", "place", "museum", "landmark"],
    },
    {
        "title": "compliance",
        "text": "The prohibited-items panel separates destination restrictions from transport restrictions and can refresh from official sources when OpenAI live search is enabled.",
        "keywords": ["compliance", "prohibited", "restricted", "banned", "customs", "law"],
    },
    {
        "title": "george",
        "text": "George is the embedded assistant. He can explain results, help with packing, answer simple questions, understand typos through fuzzy matching, and stay on the current page.",
        "keywords": ["george", "assistant", "help", "chat", "question"],
    },
]


INTENT_SYNONYMS = {
    "packing": ["packing", "pack", "pakcing", "pakc", "lugage", "luggage", "what should i bring"],
    "suggestions": ["suggestion", "suggest", "city", "stopover", "recommend", "recomend"],
    "compliance": ["compliance", "prohibited", "restriction", "restricted", "banned", "customs", "visa", "entry"],
    "transport": ["flight", "transport", "plane", "train", "bus", "ferry", "airline", "bag", "baggage"],
    "hotel": ["hotel", "stay", "room", "accommodation"],
    "attraction": ["tour", "attraction", "place", "ticket", "museum", "landmark"],
    "help": ["help", "use the app", "what can you do", "how does this work"],
    "smalltalk": ["hello", "hi", "hey", "thanks", "thank you", "who are you", "how are you", "good morning", "good evening"],
    "math": ["calculate", "plus", "minus", "times", "divide", "=", "percent"],
}


SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


class TravelPlanner:
    def __init__(self, storage, ai_client: OpenAIClient, live_data_client: LiveDataClient | None = None) -> None:
        self.storage = storage
        self.ai_client = ai_client
        self.live_data_client = live_data_client

    def bootstrap(self, session_id: str) -> dict:
        return {"memorySnapshot": self.storage.build_memory_snapshot(session_id)}

    def suggestions(self, session_id: str, trip: dict) -> dict:
        normalized_trip = normalize_trip(trip, validate_required=True)
        memory = self.storage.remember_trip(session_id, normalized_trip)
        profile_cache: dict[str, dict] = {}
        suggestions = suggest_cities(normalized_trip, memory, self.live_data_client, profile_cache)
        return {
            "trip": normalized_trip,
            "suggestions": suggestions,
            "memorySnapshot": memory,
        }

    def plan(self, session_id: str, trip: dict, accepted_city_names: list[str]) -> dict:
        normalized_trip = normalize_trip(trip, validate_required=True)
        memory = self.storage.build_memory_snapshot(session_id)
        profile_cache: dict[str, dict] = {}
        candidate_suggestions = suggest_cities(normalized_trip, memory, self.live_data_client, profile_cache)
        accepted_names = sanitize_city_names(accepted_city_names)
        accepted = [suggestion for suggestion in candidate_suggestions if suggestion["name"] in accepted_names]
        route = build_final_route(normalized_trip, accepted)
        legs = build_transport(route, normalized_trip, memory, self.live_data_client, profile_cache)
        plans = build_plans(route, normalized_trip, legs, memory, self.live_data_client, profile_cache)
        return {
            "trip": normalized_trip,
            "acceptedSuggestions": accepted,
            "legs": legs,
            "plans": plans,
            "memorySnapshot": self.storage.build_memory_snapshot(session_id),
        }

    def feedback(self, session_id: str, payload: dict) -> dict:
        event_type = payload.get("eventType", "")
        entity_value = payload.get("entityValue", "")
        delta = safe_int(payload.get("delta", 1), default=1)
        return {
            "memorySnapshot": self.storage.apply_feedback(
                session_id,
                event_type,
                entity_value,
                delta,
                payload=payload,
            )
        }

    def flag_platform(self, session_id: str, platform: str, reason: str) -> dict:
        return {"memorySnapshot": self.storage.flag_platform(session_id, platform, reason)}

    def reset(self, session_id: str) -> dict:
        return {"memorySnapshot": self.storage.reset_session(session_id)}

    def george_chat(self, session_id: str, payload: dict) -> dict:
        record = self.storage.get_profile_record(session_id)
        prompt = str(payload.get("prompt", "")).strip()
        trip = safe_trip_context(payload.get("trip") or record.get("lastTrip"))
        plans = payload.get("plans") or []
        legs = payload.get("legs") or []
        conversation = sanitize_conversation(payload.get("conversation") or [])

        if not prompt:
            return {"message": "Ask George about the route, a plan, a packing list, or the compliance panel."}

        corrected_prompt = normalize_and_correct_prompt(prompt, trip, plans)
        george_context = build_george_context(corrected_prompt, trip, plans, legs, self.storage.build_memory_snapshot(session_id))

        if not self.ai_client.configured:
            fallback = george_fallback(
                corrected_prompt,
                trip,
                plans,
                legs,
                self.storage.build_memory_snapshot(session_id),
                conversation,
            )
            return fallback

        instructions = george_system_prompt()
        use_search = looks_like_live_lookup(corrected_prompt)
        allowed_domains = []
        if use_search and trip:
            for city_name in trip.get("destinations", []):
                for source in get_city_profile(city_name).get("compliance", {}).get("sources", []):
                    hostname = urlparse(source["url"]).netloc.replace("www.", "")
                    if hostname:
                        allowed_domains.append(hostname)
        if use_search and "weather" in corrected_prompt.lower():
            allowed_domains = None

        user_input = json.dumps(
            {
                "prompt": prompt,
                "normalizedPrompt": corrected_prompt,
                "trip": trip,
                "legs": legs,
                "plans": plans[:1],
                "memory": self.storage.build_memory_snapshot(session_id),
                "retrievedContext": george_context,
                "conversation": conversation,
            },
            ensure_ascii=True,
        )
        try:
            if detect_george_intent(corrected_prompt, trip, plans) == "packing":
                structured, response_id, sources = self.ai_client.create_structured_response(
                    instructions=instructions,
                    user_input=user_input,
                    schema_name="atlas_lane_george",
                    schema=george_response_schema(),
                    previous_response_id=record.get("georgePreviousResponseId"),
                    use_web_search=use_search,
                    allowed_domains=allowed_domains or None,
                    safety_identifier=session_id[:64],
                )
                self.storage.set_george_previous_response_id(session_id, response_id)
                message = structured.get("message", "").strip() or "I can help with the route, packing, or compliance details."
                return {
                    "message": message,
                    "packingList": structured.get("packingList", []),
                    "sources": structured.get("sources", []) or sources,
                }

            message, response_id, sources = self.ai_client.create_text_response(
                instructions=instructions,
                user_input=user_input,
                previous_response_id=record.get("georgePreviousResponseId"),
                use_web_search=use_search,
                allowed_domains=allowed_domains or None,
                safety_identifier=session_id[:64],
            )
            self.storage.set_george_previous_response_id(session_id, response_id)
            return {
                "message": message.strip() or "I can help with the route, pricing, or simple questions.",
                "packingList": [],
                "sources": sources,
            }
        except OpenAIError:
            return george_fallback(prompt, trip, plans, legs, self.storage.build_memory_snapshot(session_id), conversation)

    def refresh_compliance(self, session_id: str, payload: dict) -> dict:
        cities = [city for city in payload.get("cities", []) if isinstance(city, dict) and city.get("name")]
        transport_modes = unique_list(payload.get("transportModes", []))
        if not self.ai_client.configured:
            return build_seeded_compliance(cities, transport_modes)

        allowed_domains = []
        for city in cities:
            profile = get_city_profile(city["name"])
            for source in profile["compliance"]["sources"]:
                hostname = urlparse(source["url"]).netloc.replace("www.", "")
                if hostname:
                    allowed_domains.append(hostname)
        allowed_domains.extend(["tsa.gov", "iata.org"])
        try:
            structured, _response_id, sources = self.ai_client.create_structured_response(
                instructions=compliance_system_prompt(),
                user_input=json.dumps({"cities": cities, "transportModes": transport_modes}, ensure_ascii=True),
                schema_name="atlas_lane_compliance",
                schema=compliance_schema(),
                use_web_search=True,
                allowed_domains=sorted(set(allowed_domains)),
                safety_identifier=session_id[:64],
            )
            if sources and not structured.get("sources"):
                structured["sources"] = sources
            structured["live"] = True
            return structured
        except OpenAIError:
            return build_seeded_compliance(cities, transport_modes)


def normalize_trip(trip: dict, *, validate_required: bool) -> dict:
    if not isinstance(trip, dict):
        raise PlannerValidationError("Trip details were missing or malformed.")
    origin = str(trip.get("origin", "")).strip()
    return_destination = str(trip.get("returnDestination", "")).strip() or origin
    destinations = unique_list(trip.get("destinations", []))
    attraction_types = unique_list(trip.get("attractionTypes", []))
    specific_places = unique_list(trip.get("specificPlaces", []))
    start_date = str(trip.get("startDate", "")).strip()
    end_date = str(trip.get("endDate", "")).strip()
    trip_days = safe_int(trip.get("tripDays", 0))

    normalized = {
        "origin": origin,
        "returnDestination": return_destination,
        "destinations": destinations,
        "startDate": start_date,
        "endDate": end_date,
        "tripDays": trip_days,
        "attractionTypes": attraction_types,
        "specificPlaces": specific_places,
        "bagCount": max(0, safe_int(trip.get("bagCount", 0))),
        "bagDimensions": str(trip.get("bagDimensions", "")).strip(),
        "bagWeight": str(trip.get("bagWeight", "")).strip(),
        "transportPriority": str(trip.get("transportPriority", "Cheapest")).strip() or "Cheapest",
        "flightInfo": str(trip.get("flightInfo", "Show")).strip() or "Show",
    }
    if validate_required:
        validate_trip(normalized)
    return normalized


def safe_trip_context(trip: dict | None) -> dict | None:
    if not trip:
        return None
    try:
        return normalize_trip(trip, validate_required=False)
    except PlannerValidationError:
        return None


def validate_trip(trip: dict) -> None:
    if not trip["origin"]:
        raise PlannerValidationError("Origin is required.")
    if not trip["destinations"] and trip["returnDestination"] == trip["origin"]:
        raise PlannerValidationError("Add at least one destination, or set a final destination that differs from the origin.")
    if not trip["startDate"] or not trip["endDate"]:
        raise PlannerValidationError("Start and end dates are required.")
    start = parse_date(trip["startDate"])
    end = parse_date(trip["endDate"])
    if end < start:
        raise PlannerValidationError("The end date must be on or after the start date.")
    if trip["tripDays"] <= 0:
        raise PlannerValidationError("Trip length must be at least 1 day.")
    available_days = (end - start).days + 1
    if trip["tripDays"] > available_days:
        raise PlannerValidationError("Trip length cannot be longer than the selected date window.")
    if trip["transportPriority"] not in {"Cheapest", "Fastest", "No preference"}:
        raise PlannerValidationError("Transport priority must be Cheapest, Fastest, or No preference.")
    if trip["flightInfo"] not in {"Show", "Hide"}:
        raise PlannerValidationError("Flight detail preference must be Show or Hide.")


def safe_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip() or default)
    except (TypeError, ValueError):
        return default


def sanitize_city_names(values) -> set[str]:
    if not isinstance(values, list):
        return set()
    names = []
    for value in values:
        if isinstance(value, str):
            names.append(value.strip())
        elif isinstance(value, dict):
            names.append(str(value.get("name", "")).strip())
    return {name for name in names if name}


def resolve_city_profile(
    city_name: str,
    live_data_client: LiveDataClient | None = None,
    profile_cache: dict[str, dict] | None = None,
) -> dict:
    cache = profile_cache if profile_cache is not None else {}
    if city_name in cache:
        return cache[city_name]
    profile = deepcopy(get_city_profile(city_name))
    if live_data_client:
        profile = live_data_client.enrich_city_profile(profile)
    cache[city_name] = profile
    return profile


def suggest_cities(
    trip: dict,
    memory: dict,
    live_data_client: LiveDataClient | None = None,
    profile_cache: dict[str, dict] | None = None,
) -> list[dict]:
    route = [trip["origin"], *trip["destinations"], trip["returnDestination"]]
    route_profiles = [resolve_city_profile(city, live_data_client, profile_cache) for city in route]
    preferred_types = trip["attractionTypes"] or top_keys(memory["profile"].get("attractionTypes", {}), 2)
    candidates = [city for city in candidate_cities() if city["name"] not in route]
    ranked = []

    for candidate in candidates:
        best_segment_score = -1e9
        best_segment_index = 0
        for index in range(len(route_profiles) - 1):
            segment_score = score_route_fit(route_profiles[index], route_profiles[index + 1], candidate)
            if segment_score > best_segment_score:
                best_segment_score = segment_score
                best_segment_index = index
        overlap = overlap_count(candidate["types"], preferred_types)
        learned_boost = (
            counter(memory["profile"].get("destinations", {}), candidate["name"]) * 5
            + counter(memory["profile"].get("addedCities", {}), candidate["name"]) * 6
            + counter(memory["globalSignals"].get("addedCities", {}), candidate["name"]) * 2
            - counter(memory["profile"].get("skippedCities", {}), candidate["name"]) * 7
        )
        score = best_segment_score + overlap * 16 + learned_boost
        ranked.append(
            {
                "name": candidate["name"],
                "score": round(score, 2),
                "segmentIndex": best_segment_index,
                "profile": candidate,
                "matchingTags": [item for item in candidate["types"] if item in preferred_types][:3],
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    suggestions = ranked[:2]
    for suggestion in suggestions:
        from_city = route[suggestion["segmentIndex"]]
        to_city = route[suggestion["segmentIndex"] + 1]
        tags = suggestion["matchingTags"]
        suggestion["reason"] = (
            f"{suggestion['name']} keeps the route efficient between {from_city} and {to_city} "
            f"while overlapping with {', '.join(tag.lower() for tag in tags) if tags else 'your learned preference mix'}."
        )
        suggestion["declined"] = False
    return suggestions


def build_final_route(trip: dict, accepted_suggestions: list[dict]) -> list[str]:
    base_route = [trip["origin"], *trip["destinations"], trip["returnDestination"]]
    route = [base_route[0]]
    accepted_by_segment: dict[int, list[dict]] = {}
    for suggestion in accepted_suggestions:
        accepted_by_segment.setdefault(int(suggestion["segmentIndex"]), []).append(suggestion)
    for index, next_city in enumerate(base_route[1:]):
        for suggestion in sorted(accepted_by_segment.get(index, []), key=lambda item: item["score"], reverse=True):
            if suggestion["name"] not in route:
                route.append(suggestion["name"])
        if next_city not in route or next_city == trip["returnDestination"]:
            route.append(next_city)
    return route


def build_transport(
    route: list[str],
    trip: dict,
    memory: dict,
    live_data_client: LiveDataClient | None = None,
    profile_cache: dict[str, dict] | None = None,
) -> list[dict]:
    legs = []
    for index, (from_name, to_name) in enumerate(zip(route[:-1], route[1:])):
        from_profile = resolve_city_profile(from_name, live_data_client, profile_cache)
        to_profile = resolve_city_profile(to_name, live_data_client, profile_cache)
        distance_km = haversine(from_profile["lat"], from_profile["lon"], to_profile["lat"], to_profile["lon"])
        seed = f"{from_name}-{to_name}-{trip['startDate']}-{trip['transportPriority']}"
        rng = seeded_random(seed)
        base_fare = round(120 + distance_km * 0.16 + rng() * 80)
        leg = {
            "id": f"{slugify(from_name)}-{slugify(to_name)}-{index}",
            "index": index,
            "from": from_profile,
            "to": to_profile,
            "fromName": from_name,
            "toName": to_name,
            "distanceKm": round(distance_km, 2),
            "seed": seed,
            "baseFare": base_fare,
        }
        leg["flightOptions"] = generate_flight_options(leg, trip, memory, live_data_client)
        leg["groundOptions"] = generate_ground_options(leg, trip)
        leg["history"] = generate_price_history(leg["flightOptions"][0]["bestOffer"]["price"] if leg["flightOptions"] else base_fare, seed)
        leg["forecast"] = forecast_prices(leg["history"])
        legs.append(leg)
    return legs


def generate_flight_options(leg: dict, trip: dict, memory: dict, live_data_client: LiveDataClient | None = None) -> list[dict]:
    rng = seeded_random(f"{leg['seed']}:flight")
    bag_weight = extract_number(trip.get("bagWeight", "0"))
    flagged_platforms = memory.get("flaggedPlatforms", {})
    options = []
    live_offers = []
    if live_data_client:
        try:
            live_offers = live_data_client.search_flight_offers(
                from_id=f"{leg['from']['airport']}.AIRPORT",
                to_id=f"{leg['to']['airport']}.AIRPORT",
                depart_date=trip["startDate"],
                return_date=trip["endDate"],
                adults=1,
                currency_code="USD",
                sort="CHEAPEST" if trip["transportPriority"] == "Cheapest" else "FASTEST" if trip["transportPriority"] == "Fastest" else "BEST",
                cabin_class="ECONOMY",
            )
        except Exception:  # noqa: BLE001
            live_offers = []
    for offer in live_offers:
        checked_allowance = offer.get("checkedAllowance")
        bag_shortfall = max(0, trip["bagCount"] - checked_allowance) if checked_allowance is not None else 0
        baggage_fee = bag_shortfall * (48 + max(0, bag_weight - 20) * 2)
        best_price = round((offer.get("price") or leg["baseFare"]) + baggage_fee)
        options.append(
            {
                "airline": offer.get("airline") or "Flight option",
                "aircraft": offer.get("aircraft") or "Aircraft details pending",
                "durationHours": offer.get("durationHours") or round((leg["distanceKm"] / 820) + 2.4, 1),
                "stops": max(0, offer.get("stops") or 0),
                "checkedAllowance": checked_allowance if checked_allowance is not None else 0,
                "carryOn": offer.get("carryOn") or "Check carrier policy",
                "baggageFee": baggage_fee,
                "bagShortfall": bag_shortfall,
                "basePrice": offer.get("price") or best_price,
                "bestOffer": {
                    "platform": "RapidAPI travel partner" if offer.get("url") else "Provider link unavailable",
                    "price": best_price,
                    "url": offer.get("url", ""),
                },
                "offers": ([{"platform": "RapidAPI travel partner", "price": best_price, "url": offer.get("url", "")}] if offer.get("url") else []),
                "baggageStatus": "good" if bag_shortfall == 0 else "warn" if bag_shortfall == 1 else "alert",
                "source": "RapidAPI",
            }
        )
    for airline in AIRLINES:
        aircraft = airline["aircraft"][int(rng() * len(airline["aircraft"])) % len(airline["aircraft"])]
        stops = int(rng() * 2) if leg["distanceKm"] <= 2600 else int(rng() * 2) + 1
        checked_allowance = max(0, airline["baseChecked"] + (1 if rng() > 0.76 else 0))
        bag_shortfall = max(0, trip["bagCount"] - checked_allowance)
        baggage_fee = bag_shortfall * (48 + max(0, bag_weight - 20) * 2)
        duration_hours = round((leg["distanceKm"] / 820) * airline["pace"] + stops * 1.35 + 1.1 + rng(), 1)
        fare = round(leg["baseFare"] * (0.84 + rng() * 0.18))
        offers = generate_offers("flight", fare + baggage_fee, {"fromName": leg["fromName"], "toName": leg["toName"], "airline": airline["name"]})
        best_offer = select_best_trusted_offer("flight", offers, flagged_platforms, {"airline": airline["name"], "from": leg["fromName"], "to": leg["toName"]})
        options.append(
            {
                "airline": airline["name"],
                "aircraft": aircraft,
                "durationHours": duration_hours,
                "stops": stops,
                "checkedAllowance": checked_allowance,
                "carryOn": airline["carryOn"],
                "baggageFee": baggage_fee,
                "bagShortfall": bag_shortfall,
                "basePrice": fare,
                "bestOffer": best_offer,
                "offers": offers,
                "baggageStatus": "good" if bag_shortfall == 0 else "warn" if bag_shortfall == 1 else "alert",
                "source": "Seeded fallback",
            }
        )
    options.sort(key=lambda option: sort_transport(option, trip["transportPriority"]))
    return options[:3]


def generate_ground_options(leg: dict, trip: dict) -> list[dict]:
    if leg["distanceKm"] > 1450 or leg["from"]["region"] != leg["to"]["region"]:
        return []
    modes = ["train", "coach"]
    geography_text = f"{leg['from']['geography']} {leg['to']['geography']}".lower()
    if any(token in geography_text for token in ["water", "coast", "lagoon", "harbor", "ferry"]):
        modes.append("ferry")
    rng = seeded_random(f"{leg['seed']}:ground")
    options = []
    for mode in modes[:3]:
        multiplier = 0.012 if mode == "train" else 0.018 if mode == "coach" else 0.015
        duration_hours = round(2.2 + leg["distanceKm"] * multiplier + rng() * 1.1, 1)
        cost = round(22 + leg["distanceKm"] * (0.12 if mode == "train" else 0.08 if mode == "coach" else 0.11) + rng() * 24)
        operator = GROUND_OPERATORS[mode]
        offers = generate_offers("ground", cost, {"fromName": leg["fromName"], "toName": leg["toName"], "operator": operator})
        best_offer = select_best_trusted_offer("ground", offers, {}, {"operator": operator, "from": leg["fromName"], "to": leg["toName"]})
        options.append(
            {
                "mode": mode,
                "operator": operator,
                "durationHours": duration_hours,
                "cost": cost,
                "bestOffer": best_offer,
                "scenic": mode != "coach",
            }
        )
    if trip["transportPriority"] == "Cheapest":
        options.sort(key=lambda option: (option["cost"], option["durationHours"]))
    elif trip["transportPriority"] == "Fastest":
        options.sort(key=lambda option: (option["durationHours"], option["cost"]))
    else:
        options.sort(key=lambda option: (option["durationHours"], option["cost"]))
    return options


def build_plans(
    route: list[str],
    trip: dict,
    legs: list[dict],
    memory: dict,
    live_data_client: LiveDataClient | None = None,
    profile_cache: dict[str, dict] | None = None,
) -> list[dict]:
    city_stops = route[1:-1]
    if not city_stops and len(route) == 2 and route[0] != route[1]:
        city_stops = [route[1]]
    assigned_places = assign_specific_places(city_stops, trip.get("specificPlaces", []))
    themes = [
        {
            "id": "balanced",
            "name": "Balanced Explorer",
            "description": "Good pacing, central hotels, and equal weight across landmarks, food, and breathing room.",
            "emphasis": trip["attractionTypes"] or ["Historical monuments", "Food and cuisine", "Cultural sites"],
        },
        {
            "id": "iconic",
            "name": "Landmark Sprint",
            "description": "Front-loads headline sights and faster transfers for travelers maximizing iconic coverage.",
            "emphasis": ["Historical monuments", "Modern architecture", "Cultural sites"],
        },
        {
            "id": "immersive",
            "name": "Cuisine and Culture Drift",
            "description": "Leans into slower neighborhood days, strong food picks, and local cultural texture.",
            "emphasis": ["Food and cuisine", "Cultural sites", "Natural landscapes"],
        },
    ]
    plans = []
    for offset, theme in enumerate(themes):
        day_allocation = allocate_days(city_stops, trip["tripDays"], theme["emphasis"], memory)
        start_offset = max(0, min(offset, inclusive_day_span(trip["startDate"], trip["endDate"]) - trip["tripDays"]))
        cursor = parse_date(trip["startDate"]) + timedelta(days=start_offset)
        cities = []
        flagged_platforms = memory.get("flaggedPlatforms", {})
        for index, city_name in enumerate(city_stops):
            profile = resolve_city_profile(city_name, live_data_client, profile_cache)
            days = day_allocation[index]
            check_in = cursor
            check_out = cursor + timedelta(days=max(1, days - 1))
            cursor = check_out + timedelta(days=1)
            live_hotel_results = []
            if live_data_client:
                try:
                    live_hotel_results = live_data_client.search_hotel_offers(
                        city_name,
                        lat=profile.get("lat"),
                        lon=profile.get("lon"),
                        arrival_date=iso_date(check_in),
                        departure_date=iso_date(check_out),
                        adults=1,
                        room_qty=1,
                        currency_code="USD",
                    )
                except Exception:  # noqa: BLE001
                    live_hotel_results = []
            hotels = pick_hotels(profile, days, theme, trip, memory, flagged_platforms, live_hotel_results)
            attractions = pick_attractions(profile, theme, trip, assigned_places.get(city_name, []), memory, flagged_platforms)
            weather = None
            if live_data_client:
                weather = live_data_client.weather_for_trip(
                    city_name,
                    profile.get("lat"),
                    profile.get("lon"),
                    iso_date(check_in),
                    iso_date(check_out),
                )
            cities.append(
                {
                    "name": city_name,
                    "profile": profile,
                    "days": days,
                    "checkIn": iso_date(check_in),
                    "checkOut": iso_date(check_out),
                    "nights": max(1, days - 1),
                    "hotels": hotels,
                    "attractions": attractions,
                    "weather": weather,
                    "mapId": f"{theme['id']}-{slugify(city_name)}",
                }
            )
        flight_cost = sum(leg["flightOptions"][0]["bestOffer"]["price"] if leg["flightOptions"] else 0 for leg in legs)
        hotel_cost = sum(city["hotels"][0]["totalCost"] for city in cities if city["hotels"])
        attraction_cost = sum(sum(attraction["cost"] for attraction in city["attractions"][:2]) for city in cities)
        ground_cost = sum((leg["groundOptions"][0]["bestOffer"]["price"] if leg["groundOptions"] else 0) for leg in legs)
        ground_cost += sum(round(city["profile"]["buffer"] * 0.16) for city in cities)
        buffer = round(sum(city["profile"]["buffer"] for city in cities) / max(len(cities), 1)) * trip["tripDays"]
        start_date = parse_date(trip["startDate"]) + timedelta(days=start_offset)
        plans.append(
            {
                "id": theme["id"],
                "name": theme["name"],
                "description": theme["description"],
                "route": route,
                "startDate": iso_date(start_date),
                "endDate": iso_date(start_date + timedelta(days=trip["tripDays"] - 1)),
                "theme": theme,
                "legs": deepcopy(legs),
                "cities": cities,
                "costBreakdown": {
                    "flights": flight_cost,
                    "accommodation": hotel_cost,
                    "ground": ground_cost,
                    "attractions": attraction_cost,
                    "buffer": buffer,
                },
                "totalCost": flight_cost + hotel_cost + ground_cost + attraction_cost + buffer,
            }
        )
    return plans


def pick_hotels(profile: dict, days: int, theme: dict, trip: dict, memory: dict, flagged_platforms: dict, live_hotel_results: list[dict] | None = None) -> list[dict]:
    nights = max(1, days - 1)
    hotels = []
    live_results_by_name = {item["name"].lower(): item for item in live_hotel_results or [] if item.get("name")}
    for hotel in live_hotel_results or []:
        nightly_rate = hotel.get("nightlyRate") if hotel.get("nightlyRate") is not None else round((hotel.get("totalCost") or 0) / max(nights, 1))
        total_cost = hotel.get("totalCost") if hotel.get("totalCost") is not None else round(nightly_rate * nights)
        theme_fit = overlap_count(hotel.get("fits", []), theme["emphasis"]) + overlap_count(hotel.get("fits", []), trip["attractionTypes"])
        hotels.append(
            {
                "name": hotel["name"],
                "area": hotel.get("area") or "central area",
                "fits": hotel.get("fits") or profile["types"][:2] or ["Cultural sites"],
                "nightlyRate": nightly_rate,
                "totalCost": total_cost,
                "bestOffer": {
                    "platform": hotel.get("source", "RapidAPI travel partner") if hotel.get("url") else "Provider link unavailable",
                    "price": total_cost,
                    "url": hotel.get("url", ""),
                },
                "score": theme_fit * 4 + (hotel.get("rating") or 0),
                "rating": hotel.get("rating"),
                "reviewCount": hotel.get("reviewCount"),
                "address": hotel.get("address", ""),
                "hours": hotel.get("hours", ""),
                "source": hotel.get("source", "RapidAPI Booking.com"),
            }
        )
    for hotel in profile["hotels"]:
        if hotel["name"].lower() in live_results_by_name:
            continue
        theme_fit = overlap_count(hotel["fits"], theme["emphasis"]) + overlap_count(hotel["fits"], trip["attractionTypes"])
        learned_boost = counter(memory["profile"].get("hotels", {}), hotel["name"]) + counter(memory["globalSignals"].get("hotels", {}), hotel["name"]) * 0.3
        offers = generate_offers("hotel", round(hotel["rate"] * nights), {"city": profile["name"], "hotel": hotel["name"]})
        best_offer = select_best_trusted_offer("hotel", offers, flagged_platforms, {"city": profile["name"], "hotel": hotel["name"]})
        if hotel.get("placeUrl"):
            best_offer = {
                "platform": hotel.get("source", "Google Places"),
                "price": round(hotel["rate"] * nights),
                "url": hotel["placeUrl"],
            }
        hotels.append(
            {
                **hotel,
                "nightlyRate": hotel["rate"],
                "totalCost": round(hotel["rate"] * nights),
                "bestOffer": best_offer,
                "score": theme_fit * 4 + learned_boost,
            }
        )
    hotels.sort(key=lambda hotel: (-hotel["score"], hotel["nightlyRate"]))
    return hotels[:3]


def pick_attractions(profile: dict, theme: dict, trip: dict, must_see: list[str], memory: dict, flagged_platforms: dict) -> list[dict]:
    attractions = []
    seen = set()
    for place in must_see:
        entry = create_specific_place_entry(place, profile, flagged_platforms)
        attractions.append(entry)
        seen.add(entry["name"].lower())
    for attraction in profile["attractions"]:
        if attraction["name"].lower() in seen:
            continue
        score = (
            overlap_count([attraction["type"]], theme["emphasis"]) * 8
            + overlap_count([attraction["type"]], trip["attractionTypes"]) * 5
            + counter(memory["profile"].get("savedAttractions", {}), attraction["name"]) * 2
            + counter(memory["globalSignals"].get("savedAttractions", {}), attraction["name"]) * 0.3
        )
        offers = generate_offers("attraction", attraction["cost"], {"city": profile["name"], "attraction": attraction["name"]})
        best_offer = select_best_trusted_offer("attraction", offers, flagged_platforms, {"city": profile["name"], "attraction": attraction["name"]})
        if attraction.get("placeUrl"):
            best_offer = {
                "platform": attraction.get("source", "Google Places"),
                "price": attraction["cost"],
                "url": attraction["placeUrl"],
            }
        attractions.append({**attraction, "mustSee": False, "bestOffer": best_offer, "score": score})
    attractions.sort(key=lambda item: (-item.get("mustSee", False), -item.get("score", 0), item["cost"]))
    return attractions[:4]


def create_specific_place_entry(place: str, profile: dict, flagged_platforms: dict) -> dict:
    estimated_cost = 18 + (stable_hash(place) % 28)
    offers = generate_offers("attraction", estimated_cost, {"city": profile["name"], "attraction": place})
    best_offer = select_best_trusted_offer("attraction", offers, flagged_platforms, {"city": profile["name"], "attraction": place})
    return {
        "name": place,
        "type": profile["types"][0] if profile["types"] else "Cultural sites",
        "cost": estimated_cost,
        "hours": "Check venue schedule",
        "mustSee": True,
        "bestOffer": best_offer,
    }


def assign_specific_places(city_stops: list[str], places: list[str]) -> dict:
    assigned = {city_name: [] for city_name in city_stops}
    if not city_stops:
        return assigned
    for index, place in enumerate(places):
        matched_city = None
        for city_name in city_stops:
            profile = get_city_profile(city_name)
            if city_name.lower() in place.lower() or any(attraction["name"].lower() == place.lower() for attraction in profile["attractions"]):
                matched_city = city_name
                break
        if matched_city is None:
            matched_city = city_stops[index % len(city_stops)]
        assigned[matched_city].append(place)
    return assigned


def generate_offers(category: str, base_price: int, context: dict) -> list[dict]:
    rng = seeded_random(f"{category}:{json.dumps(context, sort_keys=True)}")
    platforms = [name for name, details in PLATFORM_LIBRARY.items() if category in details["categories"]]
    offers = []
    for platform in platforms:
        variance = 0.08 if PLATFORM_LIBRARY[platform]["trusted"] else -0.1
        price = max(0, round(base_price * (1 + variance + (rng() - 0.5) * 0.1)))
        offers.append(
            {
                "platform": platform,
                "price": price,
                "url": booking_url(category, context, platform),
            }
        )
    return offers


def select_best_trusted_offer(category: str, offers: list[dict], flagged_platforms: dict, context: dict) -> dict:
    trusted = [
        offer
        for offer in offers
        if PLATFORM_LIBRARY.get(offer["platform"], {}).get("trusted") and offer["platform"] not in flagged_platforms
    ]
    trusted.sort(key=lambda offer: offer["price"])
    if trusted:
        return trusted[0]
    label = context.get("hotel") or context.get("attraction") or context.get("airline") or context.get("operator") or "Direct booking"
    return {
        "platform": f"{label} direct" if category == "flight" else "Direct booking",
        "price": offers[0]["price"] if offers else 0,
        "url": booking_url(category, context, label),
    }


def generate_price_history(base_price: int, seed: str) -> list[dict]:
    rng = seeded_random(f"{seed}:history")
    history = []
    price = base_price * (0.88 + rng() * 0.12)
    for day in range(-20, 1):
        price = max(60, price * (1 + (rng() - 0.45) * 0.08))
        history.append({"label": f"{abs(day)}d", "day": day, "price": round(price)})
    return history


def forecast_prices(history: list[dict]) -> dict:
    returns = []
    for previous, current in zip(history[:-1], history[1:]):
        if previous["price"] > 0:
            returns.append(math.log(current["price"] / previous["price"]))
    drift = average(returns)
    volatility = max(0.01, standard_deviation(returns))
    last_price = history[-1]["price"]
    projected = []
    for day in range(1, 8):
        simulations = []
        for run in range(160):
            rng = seeded_random(f"{last_price}:{day}:{run}")
            move = drift + (rng() - 0.5) * volatility * 2
            next_price = max(55, last_price * math.exp(move * day))
            simulations.append(next_price)
        simulations.sort()
        projected.append(
            {
                "day": day,
                "mean": round(average(simulations)),
                "low": round(percentile(simulations, 0.1)),
                "high": round(percentile(simulations, 0.9)),
            }
        )
    final_projection = projected[-1]
    trend = "up" if final_projection["mean"] > last_price + 8 else "down" if final_projection["mean"] < last_price - 8 else "flat"
    confidence = max(52, min(89, round(100 - ((final_projection["high"] - final_projection["low"]) / max(final_projection["mean"], 1)) * 100)))
    return {"projected": projected, "trend": trend, "confidence": confidence}


def build_seeded_compliance(cities: list[dict], transport_modes: list[str]) -> dict:
    destination_panels = []
    sources = []
    for city in cities:
        profile = get_city_profile(city["name"])
        destination_panels.append(
            {
                "city": profile["name"],
                "country": profile["country"],
                "items": profile["compliance"]["destination"],
                "sources": profile["compliance"]["sources"],
            }
        )
        sources.extend(profile["compliance"]["sources"])

    transport_items = [
        "Compressed gas, fireworks, replica weapons, and large lithium battery packs can be rejected by air carriers.",
        "Sharp objects, fuels, corrosives, and hazardous chemicals are commonly prohibited across flights and many rail operators.",
    ]
    if any(mode in {"train", "coach", "ferry"} for mode in transport_modes):
        transport_items.append("Oversized battery devices, fuel canisters, and some sporting equipment may be banned on rail, coach, or ferry lines.")
    transport_sources = [
        {"label": "TSA prohibited items", "url": "https://www.tsa.gov/travel/security-screening/whatcanibring/all-list"},
        {"label": "IATA dangerous goods guidance", "url": "https://www.iata.org/en/programs/cargo/dgr/"},
    ]
    return {
        "live": False,
        "destinationPanels": destination_panels,
        "transportPanel": {"items": transport_items, "sources": transport_sources},
        "sources": dedupe_sources(sources + transport_sources),
    }


def george_fallback(
    prompt: str,
    trip: dict | None,
    plans: list[dict],
    legs: list[dict],
    memory: dict,
    conversation: list[dict] | None = None,
) -> dict:
    lowered = prompt.lower()
    detected_intent = detect_george_intent(lowered, trip, plans)
    generic_answer = answer_general_question(prompt, conversation or [], trip, plans)
    if generic_answer:
        return {"message": generic_answer, "packingList": [], "sources": []}

    if detected_intent == "math":
        answer = try_solve_math(prompt)
        if answer is not None:
            return {
                "message": f"I read that as `{prompt}` and the answer is {answer}.",
                "packingList": [],
                "sources": [],
            }

    if detected_intent == "smalltalk":
        return {
            "message": answer_smalltalk(lowered),
            "packingList": [],
            "sources": [],
        }

    if detected_intent == "packing":
        return {
            "message": "I drafted a packing list using your route, activities, transport modes, and document basics.",
            "packingList": heuristic_packing_list(trip, plans, legs),
            "sources": [],
        }
    if detected_intent == "suggestions":
        if trip:
            suggestions = suggest_cities(normalize_trip(trip, validate_required=True), memory)
            message = " ".join(
                f"{item['name']} fits because it stays efficient on the route and matches {', '.join(tag.lower() for tag in item['matchingTags']) or 'your learned pattern'}."
                for item in suggestions
            ) or "Once you share a route, I can explain which stopovers fit best."
            return {"message": message, "packingList": [], "sources": []}
    if detected_intent == "compliance":
        return {
            "message": "Use the prohibited items button inside any plan card. The panel separates destination rules from transport restrictions and can be refreshed from official sources when OpenAI live search is enabled.",
            "packingList": [],
            "sources": [],
        }
    if detected_intent in {"transport", "hotel", "attraction", "help"}:
        contextual_answer = answer_from_retrieval(prompt, trip, plans, legs, memory)
        return {
            "message": contextual_answer,
            "packingList": [],
            "sources": [],
        }
    return {
        "message": answer_from_retrieval(prompt, trip, plans, legs, memory),
        "packingList": [],
        "sources": [],
    }


def heuristic_packing_list(trip: dict | None, plans: list[dict], legs: list[dict]) -> list[dict]:
    if not trip:
        return []
    city_plans = plans[0]["cities"] if plans else []
    items = []
    for city in city_plans:
        items.append({"name": f"{city['name']}: layers for {city['profile']['climate']}", "detail": city["profile"]["geography"]})
        if city.get("weather", {}).get("packHint"):
            items.append({"name": f"{city['name']}: weather prep", "detail": city["weather"]["packHint"]})
    attraction_types = unique_list([attraction["type"] for city in city_plans for attraction in city["attractions"]])
    if "Natural landscapes" in attraction_types:
        items.append({"name": "Trail-ready shoes", "detail": "Useful for scenic routes, hills, or long outdoor walks."})
    if "Food and cuisine" in attraction_types:
        items.append({"name": "Fold-flat tote", "detail": "Helpful for markets, snacks, and quick grocery stops."})
    if legs:
        items.append({"name": "Portable power bank", "detail": "Useful for mobile boarding passes and long transfers."})
        items.append({"name": "Eye mask and compression pouch", "detail": "Improves comfort on long-haul travel days."})
    items.append({"name": "Passport", "detail": "Required for international travel and most border checks."})
    items.append({"name": "Travel insurance details", "detail": "Keep policy number and emergency contacts available."})
    items.append({"name": "Visa or entry confirmation if required", "detail": "Check each destination before departure."})
    deduped = []
    seen = set()
    for item in items:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        deduped.append(item)
    return deduped


def compliance_system_prompt() -> str:
    return (
        "You generate travel compliance panels for a booking application. "
        "Return concise, practical prohibited-item summaries by destination and transport mode. "
        "Only cite official sources surfaced by web search. Keep the tone neutral and useful."
    )


def compliance_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "destinationPanels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "country": {"type": "string"},
                        "items": {"type": "array", "items": {"type": "string"}},
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"label": {"type": "string"}, "url": {"type": "string"}},
                                "required": ["label", "url"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["city", "country", "items", "sources"],
                    "additionalProperties": False,
                },
            },
            "transportPanel": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"label": {"type": "string"}, "url": {"type": "string"}},
                            "required": ["label", "url"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["items", "sources"],
                "additionalProperties": False,
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                    "required": ["title", "url"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["destinationPanels", "transportPanel", "sources"],
        "additionalProperties": False,
    }


def george_system_prompt() -> str:
    return (
        "You are George, the embedded assistant inside a travel planning app. "
        "Behave like a helpful, natural chat assistant first, and a travel specialist second. "
        "Understand typos, shorthand, and lightly ungrammatical messages. "
        "Answer direct user questions directly instead of forcing the conversation back to destinations or itineraries. "
        "When the user asks a general simple question, answer it like a normal assistant would. "
        "When trip context is relevant, ground your answer in the actual route, plans, hotels, attractions, and transport options. "
        "When the user asks for packing help, produce a practical packing list based on climate, geography, planned activities, transport modes, and required documents. "
        "Keep the tone warm, concise, and human. Never tell the user to leave the current page. "
        "If web sources are available, use them for current restrictions or weather-style questions and cite them briefly."
    )


def george_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "packingList": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "detail": {"type": "string"}},
                    "required": ["name", "detail"],
                    "additionalProperties": False,
                },
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "url": {"type": "string"}},
                    "required": ["label", "url"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["message", "packingList", "sources"],
        "additionalProperties": False,
    }


def looks_like_live_lookup(prompt: str) -> bool:
    lowered = prompt.lower()
    live_terms = ["today", "latest", "current", "weather", "visa", "entry", "restriction", "compliance", "prohibited"]
    return any(term in lowered for term in live_terms)


def normalize_and_correct_prompt(prompt: str, trip: dict | None, plans: list[dict]) -> str:
    tokens = re.findall(r"[a-zA-Z0-9']+", prompt.lower())
    vocabulary = set()
    for keywords in INTENT_SYNONYMS.values():
        vocabulary.update(re.findall(r"[a-zA-Z0-9']+", " ".join(keywords)))
    for article in GEORGE_KNOWLEDGE_BASE:
        vocabulary.update(article["keywords"])
    if trip:
        vocabulary.update(re.findall(r"[a-zA-Z0-9']+", trip.get("origin", "").lower()))
        vocabulary.update(re.findall(r"[a-zA-Z0-9']+", trip.get("returnDestination", "").lower()))
        for destination in trip.get("destinations", []):
            vocabulary.update(re.findall(r"[a-zA-Z0-9']+", destination.lower()))
    for plan in plans:
        vocabulary.update(re.findall(r"[a-zA-Z0-9']+", plan.get("name", "").lower()))
    corrected_tokens = []
    for token in tokens:
        if len(token) < 4 or token in vocabulary:
            corrected_tokens.append(token)
            continue
        matches = difflib.get_close_matches(token, sorted(vocabulary), n=1, cutoff=0.82)
        corrected_tokens.append(matches[0] if matches else token)
    return " ".join(corrected_tokens) or prompt


def detect_george_intent(prompt: str, trip: dict | None, plans: list[dict]) -> str:
    lowered = prompt.lower()
    tokens = set(re.findall(r"[a-zA-Z0-9']+", lowered))
    scores = {}
    for intent, phrases in INTENT_SYNONYMS.items():
        score = 0.0
        for phrase in phrases:
            phrase_tokens = set(re.findall(r"[a-zA-Z0-9']+", phrase.lower()))
            if phrase in lowered:
                score += 1.7
            elif phrase_tokens:
                overlap = len(tokens & phrase_tokens)
                if overlap:
                    score += overlap / max(len(phrase_tokens), 1)
        scores[intent] = score
    if any(symbol in lowered for symbol in ["+", "-", "*", "/", "="]) or re.search(r"\b\d+\s*(plus|minus|times|multiplied|divided)\s*\d+\b", lowered):
        scores["math"] = scores.get("math", 0) + 2.4
    if is_general_question(lowered) and not contains_travel_signal(tokens):
        scores["general"] = scores.get("general", 0) + 2.0
    best_intent = max(scores, key=scores.get)
    return best_intent if scores[best_intent] >= 1.1 else "general"


def build_george_context(prompt: str, trip: dict | None, plans: list[dict], legs: list[dict], memory: dict) -> dict:
    context_chunks = []
    for article in GEORGE_KNOWLEDGE_BASE:
        article_score = retrieval_score(prompt, f"{article['title']} {article['text']} {' '.join(article['keywords'])}")
        if article_score > 0:
            context_chunks.append((article_score, article["text"]))
    if trip:
        context_chunks.append((1.4, f"Trip route: {trip.get('origin')} -> {', '.join(trip.get('destinations', []))} -> {trip.get('returnDestination')}."))
        if trip.get("attractionTypes"):
            context_chunks.append((1.2, f"Preferred attraction types: {', '.join(trip['attractionTypes'])}."))
    if plans:
        top_plan = plans[0]
        context_chunks.append((1.6, f"Top plan: {top_plan.get('name')} with cities {', '.join(city['name'] for city in top_plan.get('cities', []))}."))
        for city in top_plan.get("cities", [])[:2]:
            context_chunks.append(
                (
                    1.3,
                    f"{city['name']} has hotels like {', '.join(hotel['name'] for hotel in city.get('hotels', [])[:2])} and attractions like {', '.join(attraction['name'] for attraction in city.get('attractions', [])[:2])}.",
                )
            )
            if city.get("weather", {}).get("headline"):
                context_chunks.append((1.15, f"Live weather for {city['name']}: {city['weather']['headline']}"))
    if legs:
        first_leg = legs[0]
        context_chunks.append(
            (
                1.2,
                f"First transport leg is {first_leg['fromName']} to {first_leg['toName']} with leading airline option {first_leg['flightOptions'][0]['airline'] if first_leg.get('flightOptions') else 'none'} and baggage-sensitive ranking.",
            )
        )
    top_memory = top_keys(memory.get("profile", {}).get("destinations", {}), 3)
    if top_memory:
        context_chunks.append((0.9, f"User often selects destinations like {', '.join(top_memory)}."))
    context_chunks.sort(key=lambda item: item[0], reverse=True)
    return {"snippets": [chunk for _score, chunk in context_chunks[:6]]}


def answer_from_retrieval(prompt: str, trip: dict | None, plans: list[dict], legs: list[dict], memory: dict) -> str:
    detected_intent = detect_george_intent(prompt, trip, plans)
    if "weather" in prompt.lower() and plans:
        weather_bits = [
            f"{city['name']}: {city['weather']['headline']}"
            for city in plans[0].get("cities", [])
            if city.get("weather", {}).get("headline")
        ]
        if weather_bits:
            return " ".join(weather_bits[:2])
    if detected_intent == "help":
        return "Start on the search page, continue to the detailed trip form, then review results on the separate plans page where transport, hotels, and tour places each live inside foldable sections."
    if detected_intent == "transport" and legs:
        first_leg = legs[0]
        top_flight = first_leg["flightOptions"][0] if first_leg.get("flightOptions") else None
        if top_flight:
            return (
                f"For the first leg from {first_leg['fromName']} to {first_leg['toName']}, "
                f"the leading option is {top_flight['airline']} on a {top_flight['aircraft']} at {top_flight['bestOffer']['price']} with "
                f"{top_flight['checkedAllowance']} free checked bag(s) and {top_flight['carryOn'].lower()}."
            )
    if detected_intent == "hotel" and plans:
        first_city = plans[0]["cities"][0]
        first_hotel = first_city["hotels"][0]
        return (
            f"In {first_city['name']}, the strongest hotel match right now is {first_hotel['name']} in the {first_hotel['area']} area at "
            f"{first_hotel['nightlyRate']} per night, chosen because it fits your attraction mix and learned preferences."
        )
    if detected_intent == "attraction" and plans:
        first_city = plans[0]["cities"][0]
        first_attraction = first_city["attractions"][0]
        return (
            f"A strong tour pick in {first_city['name']} is {first_attraction['name']}, "
            f"which matches {first_attraction['type'].lower()} and is currently estimated at {first_attraction['cost']}."
        )
    if plans:
        top_plan = plans[0]
        return (
            f"{top_plan['name']} is the leading itinerary right now. "
            f"It covers {len(top_plan['cities'])} cities and keeps transport, stays, and attractions grouped on this page."
        )
    if trip:
        return (
            f"I can help with your route from {trip.get('origin')} through {', '.join(trip.get('destinations', [])) or 'your selected destinations'}. "
            "You can ask about hotels, transport, attractions, packing, pricing, or why a city was suggested."
        )
    return "I can answer simple questions, explain the app flow, and help with transport, hotels, attractions, packing, and compliance even if your message has typos."


def answer_general_question(prompt: str, conversation: list[dict], trip: dict | None, plans: list[dict]) -> str | None:
    lowered = prompt.lower().strip()
    if not lowered:
        return None
    if any(phrase in lowered for phrase in ["talk to me", "chat with me", "can you answer questions", "can you talk", "are you working"]):
        return "Yes. Ask me directly and I’ll answer more like a chat assistant instead of switching back to destinations."
    if any(word in lowered for word in ["date", "today", "time now"]) and not contains_travel_signal(set(re.findall(r"[a-zA-Z0-9']+", lowered))):
        return f"It is {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}."
    if "joke" in lowered:
        return "Travel joke: I packed so efficiently for my trip that my suitcase asked for its own itinerary."
    if lowered.startswith(("what is ", "who is ", "who was ", "tell me about ", "explain ")) and not contains_travel_signal(set(re.findall(r"[a-zA-Z0-9']+", lowered))):
        ddg_summary = lookup_duckduckgo_summary(prompt)
        if ddg_summary:
            return ddg_summary
        topic = extract_general_topic(lowered)
        summary = lookup_wikipedia_summary(topic) or lookup_wikipedia_search_summary(topic)
        if summary:
            return summary
    if is_general_question(lowered) and not contains_travel_signal(set(re.findall(r"[a-zA-Z0-9']+", lowered))):
        ddg_summary = lookup_duckduckgo_summary(prompt)
        if ddg_summary:
            return ddg_summary
        searched_summary = lookup_wikipedia_search_summary(prompt)
        if searched_summary:
            return searched_summary
    if is_general_question(lowered) and not contains_travel_signal(set(re.findall(r"[a-zA-Z0-9']+", lowered))):
        recent_user = next((item["content"] for item in reversed(conversation) if item.get("role") == "user"), "")
        if recent_user and recent_user.lower() != lowered and looks_like_follow_up(lowered):
            return f"I’m following you. If you mean your last topic, ask it as a full sentence and I’ll answer it directly."
        return "I can chat and answer simple questions directly. If you want a general answer, ask it plainly and I’ll stay on that topic instead of jumping back to the itinerary."
    return None


def extract_general_topic(prompt: str) -> str:
    topic = re.sub(r"^(what is|who is|who was|tell me about|explain)\s+", "", prompt.strip(), flags=re.IGNORECASE)
    return topic.strip(" ?.!")


def lookup_wikipedia_summary(topic: str) -> str | None:
    if not topic:
        return None
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(topic.replace(" ", "_"))
        request = urllib.request.Request(url, headers={"User-Agent": "AtlasLane/1.0"})
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    extract = str(payload.get("extract", "")).strip()
    if not extract:
        return None
    return extract


def lookup_wikipedia_search_summary(topic: str) -> str | None:
    query = topic.strip()
    if not query:
        return None
    search_url = (
        "https://en.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "opensearch",
                "search": query,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            }
        )
    )
    try:
        request = urllib.request.Request(search_url, headers={"User-Agent": "AtlasLane/1.0"})
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    title = str(payload[1][0]).strip()
    if not title:
        return None
    return lookup_wikipedia_summary(title)


def lookup_duckduckgo_summary(topic: str) -> str | None:
    query = topic.strip()
    if not query:
        return None
    url = (
        "https://api.duckduckgo.com/?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
                "no_redirect": "1",
            }
        )
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AtlasLane/1.0"})
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    for key in ("Answer", "AbstractText", "Definition"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    related = payload.get("RelatedTopics") or []
    for item in related[:5]:
        if isinstance(item, dict):
            text = str(item.get("Text", "")).strip()
            if text:
                return text
            for nested in item.get("Topics", []) or []:
                if isinstance(nested, dict):
                    text = str(nested.get("Text", "")).strip()
                    if text:
                        return text
    return None


def sanitize_conversation(conversation) -> list[dict]:
    cleaned = []
    if not isinstance(conversation, list):
        return cleaned
    for item in conversation[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content[:500]})
    return cleaned


def is_general_question(prompt: str) -> bool:
    stripped = prompt.strip().lower()
    if "?" in stripped:
        return True
    return stripped.startswith(("what", "who", "why", "when", "where", "how", "can you", "do you", "is ", "are "))


def contains_travel_signal(tokens: set[str]) -> bool:
    travel_tokens = {
        "trip",
        "travel",
        "hotel",
        "flight",
        "plane",
        "train",
        "bus",
        "tour",
        "route",
        "city",
        "destination",
        "packing",
        "pack",
        "baggage",
        "visa",
        "itinerary",
        "transport",
        "booking",
        "price",
    }
    return bool(tokens & travel_tokens)


def looks_like_follow_up(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    if lowered.startswith(("and ", "what about", "how about", "why that", "why so", "tell me more", "more on that")):
        return True
    return lowered in {"why", "how", "what else", "more", "and?"}


def retrieval_score(query: str, text: str) -> float:
    query_tokens = set(re.findall(r"[a-zA-Z0-9']+", query.lower()))
    text_tokens = set(re.findall(r"[a-zA-Z0-9']+", text.lower()))
    overlap = len(query_tokens & text_tokens)
    fuzzy = difflib.SequenceMatcher(None, query.lower(), text.lower()).ratio()
    return overlap + fuzzy


def try_solve_math(prompt: str) -> str | None:
    expression = prompt.lower()
    replacements = {
        "plus": "+",
        "minus": "-",
        "times": "*",
        "multiplied by": "*",
        "x": "*",
        "divided by": "/",
    }
    for source, target in replacements.items():
        expression = expression.replace(source, target)
    expression = re.sub(r"[^0-9\.\+\-\*\/\(\)\s]", "", expression)
    expression = expression.strip()
    if not expression or not re.search(r"\d", expression):
        return None
    try:
        value = evaluate_math_ast(ast.parse(expression, mode="eval").body)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def evaluate_math_ast(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
        return SAFE_OPERATORS[type(node.op)](evaluate_math_ast(node.left), evaluate_math_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
        return SAFE_OPERATORS[type(node.op)](evaluate_math_ast(node.operand))
    raise ValueError("Unsupported expression")


def answer_smalltalk(lowered_prompt: str) -> str:
    if any(token in lowered_prompt for token in ["thank", "thanks"]):
        return "Happy to help. If you want, I can explain a plan, unpack a transport choice, or build a smarter packing list next."
    if "who are you" in lowered_prompt:
        return "I’m George, the in-app travel assistant. I help explain plans, compare options, answer simple questions, and build packing lists without sending you away from the page."
    if "how are you" in lowered_prompt:
        return "Doing well and ready to plan. Ask me about the route, a hotel, a flight, or even a typo-filled question and I’ll do my best to interpret it."
    return "Hi. I’m here to help with the trip, the app, or simple questions you want answered quickly."


def seeded_random(seed_value: str):
    state = stable_hash(seed_value) & 0xFFFFFFFF

    def rng() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        temp = (state ^ (state >> 15)) * (1 | state)
        temp = (temp + ((temp ^ (temp >> 7)) * (61 | temp))) ^ temp
        return ((temp ^ (temp >> 14)) & 0xFFFFFFFF) / 4294967296

    return rng


def stable_hash(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371
    lat_delta = math.radians(lat2 - lat1)
    lon_delta = math.radians(lon2 - lon1)
    a = math.sin(lat_delta / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(lon_delta / 2) ** 2
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def score_route_fit(from_profile: dict, to_profile: dict, candidate: dict) -> float:
    from_distance = haversine(from_profile["lat"], from_profile["lon"], candidate["lat"], candidate["lon"])
    to_distance = haversine(to_profile["lat"], to_profile["lon"], candidate["lat"], candidate["lon"])
    same_region_boost = 24 if from_profile["region"] == candidate["region"] or to_profile["region"] == candidate["region"] else 0
    return same_region_boost + 1400 / (from_distance + 120) + 1400 / (to_distance + 120)


def allocate_days(city_stops: list[str], trip_days: int, emphasis: list[str], memory: dict) -> list[int]:
    if not city_stops:
        return []
    weights = []
    for city_name in city_stops:
        profile = get_city_profile(city_name)
        weight = (
            1
            + overlap_count(profile["types"], emphasis) * 1.8
            + counter(memory["profile"].get("destinations", {}), city_name) * 0.8
            + counter(memory["profile"].get("addedCities", {}), city_name) * 1.2
            + counter(memory["globalSignals"].get("destinations", {}), city_name) * 0.1
        )
        weights.append(weight)
    days = [1 for _ in city_stops]
    remaining = max(0, trip_days - len(city_stops))
    while remaining > 0:
        scores = [weight / (days[index] + 0.75) for index, weight in enumerate(weights)]
        best_index = max(range(len(scores)), key=lambda idx: scores[idx])
        days[best_index] += 1
        remaining -= 1
    return days


def sort_transport(option: dict, priority: str) -> tuple:
    if priority == "Cheapest":
        return (option["bestOffer"]["price"], option["durationHours"])
    if priority == "Fastest":
        return (option["durationHours"], option["bestOffer"]["price"])
    return (option["durationHours"], option["bestOffer"]["price"])


def booking_url(category: str, context: dict, platform: str) -> str:
    return ""


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise PlannerValidationError("Dates must use the YYYY-MM-DD format.") from error


def iso_date(value: date) -> str:
    return value.isoformat()


def inclusive_day_span(start: str, end: str) -> int:
    return (parse_date(end) - parse_date(start)).days + 1


def extract_number(value: str) -> float:
    digits = []
    current = []
    for character in value:
        if character.isdigit() or character == ".":
            current.append(character)
        elif current:
            break
    if current:
        return float("".join(current))
    return 0.0


def unique_list(values) -> list:
    if isinstance(values, str):
        raw_values = [item.strip() for item in values.replace("\n", ",").split(",")]
    else:
        raw_values = [str(item).strip() for item in values]
    seen = set()
    unique = []
    for value in raw_values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def overlap_count(first: list[str], second: list[str]) -> int:
    return sum(1 for item in first if item in second)


def counter(mapping: dict, key: str) -> int:
    return int(mapping.get(key, 0) or 0)


def top_keys(mapping: dict, limit: int) -> list[str]:
    return [name for name, count in sorted(mapping.items(), key=lambda item: (-item[1], item[0]))[:limit] if count > 0]


def slugify(value: str) -> str:
    return "-".join("".join(character.lower() if character.isalnum() else " " for character in value).split())


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def standard_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = average(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def percentile(values: list[float], amount: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int(len(values) * amount)))
    return values[index]


def dedupe_sources(sources: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for source in sources:
        url = source.get("url")
        label = source.get("label") or source.get("title") or url
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append({"label": label, "url": url})
    return unique
