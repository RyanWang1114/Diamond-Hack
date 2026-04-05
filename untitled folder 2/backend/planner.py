from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus, urlparse

from .catalog import candidate_cities, get_city_profile
from .openai_client import OpenAIClient, OpenAIError


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


class TravelPlanner:
    def __init__(self, storage, ai_client: OpenAIClient) -> None:
        self.storage = storage
        self.ai_client = ai_client

    def bootstrap(self, session_id: str) -> dict:
        return {"memorySnapshot": self.storage.build_memory_snapshot(session_id)}

    def suggestions(self, session_id: str, trip: dict) -> dict:
        normalized_trip = normalize_trip(trip)
        memory = self.storage.remember_trip(session_id, normalized_trip)
        suggestions = suggest_cities(normalized_trip, memory)
        return {
            "trip": normalized_trip,
            "suggestions": suggestions,
            "memorySnapshot": memory,
        }

    def plan(self, session_id: str, trip: dict, accepted_city_names: list[str]) -> dict:
        normalized_trip = normalize_trip(trip)
        memory = self.storage.build_memory_snapshot(session_id)
        candidate_suggestions = suggest_cities(normalized_trip, memory)
        accepted = [suggestion for suggestion in candidate_suggestions if suggestion["name"] in set(accepted_city_names)]
        route = build_final_route(normalized_trip, accepted)
        legs = build_transport(route, normalized_trip, memory)
        plans = build_plans(route, normalized_trip, legs, memory)
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
        delta = int(payload.get("delta", 1))
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
        trip = payload.get("trip") or record.get("lastTrip")
        plans = payload.get("plans") or []
        legs = payload.get("legs") or []

        if not prompt:
            return {"message": "Ask George about the route, a plan, a packing list, or the compliance panel."}

        if not self.ai_client.configured:
            fallback = george_fallback(prompt, trip, plans, legs, self.storage.build_memory_snapshot(session_id))
            return fallback

        instructions = george_system_prompt()
        schema = george_response_schema()
        use_search = looks_like_live_lookup(prompt)
        allowed_domains = []
        if use_search and trip:
            for city_name in trip.get("destinations", []):
                for source in get_city_profile(city_name).get("compliance", {}).get("sources", []):
                    hostname = urlparse(source["url"]).netloc.replace("www.", "")
                    if hostname:
                        allowed_domains.append(hostname)

        user_input = json.dumps(
            {
                "prompt": prompt,
                "trip": trip,
                "legs": legs,
                "plans": plans[:1],
                "memory": self.storage.build_memory_snapshot(session_id),
            },
            ensure_ascii=True,
        )
        try:
            structured, response_id, sources = self.ai_client.create_structured_response(
                instructions=instructions,
                user_input=user_input,
                schema_name="atlas_lane_george",
                schema=schema,
                previous_response_id=record.get("georgePreviousResponseId"),
                use_web_search=use_search,
                allowed_domains=allowed_domains or None,
                safety_identifier=session_id[:64],
            )
            self.storage.set_george_previous_response_id(session_id, response_id)
            message = structured.get("message", "").strip() or "I can help with the route, packing, or compliance details."
            packing_list = structured.get("packingList", [])
            return {
                "message": message,
                "packingList": packing_list,
                "sources": structured.get("sources", []) or sources,
            }
        except OpenAIError:
            return george_fallback(prompt, trip, plans, legs, self.storage.build_memory_snapshot(session_id))

    def refresh_compliance(self, session_id: str, payload: dict) -> dict:
        cities = payload.get("cities", [])
        transport_modes = payload.get("transportModes", [])
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


def normalize_trip(trip: dict) -> dict:
    origin = str(trip.get("origin", "")).strip()
    return_destination = str(trip.get("returnDestination", "")).strip() or origin
    destinations = unique_list(trip.get("destinations", []))
    attraction_types = unique_list(trip.get("attractionTypes", []))
    specific_places = unique_list(trip.get("specificPlaces", []))
    start_date = str(trip.get("startDate", "")).strip()
    end_date = str(trip.get("endDate", "")).strip()
    trip_days = int(trip.get("tripDays", 0) or 0)

    return {
        "origin": origin,
        "returnDestination": return_destination,
        "destinations": destinations,
        "startDate": start_date,
        "endDate": end_date,
        "tripDays": trip_days,
        "attractionTypes": attraction_types,
        "specificPlaces": specific_places,
        "bagCount": int(trip.get("bagCount", 0) or 0),
        "bagDimensions": str(trip.get("bagDimensions", "")).strip(),
        "bagWeight": str(trip.get("bagWeight", "")).strip(),
        "transportPriority": str(trip.get("transportPriority", "Cheapest")).strip() or "Cheapest",
        "flightInfo": str(trip.get("flightInfo", "Show")).strip() or "Show",
    }


def suggest_cities(trip: dict, memory: dict) -> list[dict]:
    route = [trip["origin"], *trip["destinations"], trip["returnDestination"]]
    route_profiles = [get_city_profile(city) for city in route]
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


def build_transport(route: list[str], trip: dict, memory: dict) -> list[dict]:
    legs = []
    for index, (from_name, to_name) in enumerate(zip(route[:-1], route[1:])):
        from_profile = get_city_profile(from_name)
        to_profile = get_city_profile(to_name)
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
        leg["flightOptions"] = generate_flight_options(leg, trip, memory)
        leg["groundOptions"] = generate_ground_options(leg, trip)
        leg["history"] = generate_price_history(leg["flightOptions"][0]["bestOffer"]["price"] if leg["flightOptions"] else base_fare, seed)
        leg["forecast"] = forecast_prices(leg["history"])
        legs.append(leg)
    return legs


def generate_flight_options(leg: dict, trip: dict, memory: dict) -> list[dict]:
    rng = seeded_random(f"{leg['seed']}:flight")
    bag_weight = extract_number(trip.get("bagWeight", "0"))
    flagged_platforms = memory.get("flaggedPlatforms", {})
    options = []
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


def build_plans(route: list[str], trip: dict, legs: list[dict], memory: dict) -> list[dict]:
    city_stops = route[1:-1]
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
            profile = get_city_profile(city_name)
            days = day_allocation[index]
            check_in = cursor
            check_out = cursor + timedelta(days=max(1, days - 1))
            cursor = check_out + timedelta(days=1)
            hotels = pick_hotels(profile, days, theme, trip, memory, flagged_platforms)
            attractions = pick_attractions(profile, theme, trip, assigned_places.get(city_name, []), memory, flagged_platforms)
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


def pick_hotels(profile: dict, days: int, theme: dict, trip: dict, memory: dict, flagged_platforms: dict) -> list[dict]:
    nights = max(1, days - 1)
    hotels = []
    for hotel in profile["hotels"]:
        theme_fit = overlap_count(hotel["fits"], theme["emphasis"]) + overlap_count(hotel["fits"], trip["attractionTypes"])
        learned_boost = counter(memory["profile"].get("hotels", {}), hotel["name"]) + counter(memory["globalSignals"].get("hotels", {}), hotel["name"]) * 0.3
        offers = generate_offers("hotel", round(hotel["rate"] * nights), {"city": profile["name"], "hotel": hotel["name"]})
        best_offer = select_best_trusted_offer("hotel", offers, flagged_platforms, {"city": profile["name"], "hotel": hotel["name"]})
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


def george_fallback(prompt: str, trip: dict | None, plans: list[dict], legs: list[dict], memory: dict) -> dict:
    lowered = prompt.lower()
    if "packing" in lowered:
        return {
            "message": "I drafted a packing list using your route, activities, transport modes, and document basics.",
            "packingList": heuristic_packing_list(trip, plans, legs),
            "sources": [],
        }
    if "suggest" in lowered or "city" in lowered:
        if trip:
            suggestions = suggest_cities(normalize_trip(trip), memory)
            message = " ".join(
                f"{item['name']} fits because it stays efficient on the route and matches {', '.join(tag.lower() for tag in item['matchingTags']) or 'your learned pattern'}."
                for item in suggestions
            ) or "Once you share a route, I can explain which stopovers fit best."
            return {"message": message, "packingList": [], "sources": []}
    if "compliance" in lowered or "prohibited" in lowered:
        return {
            "message": "Use the prohibited items button inside any plan card. The panel separates destination rules from transport restrictions and can be refreshed from official sources when OpenAI live search is enabled.",
            "packingList": [],
            "sources": [],
        }
    if plans:
        top_plan = plans[0]
        return {
            "message": f"{top_plan['name']} is the most balanced option right now: it spreads the trip across {len(top_plan['cities'])} cities, keeps hotels close to your priorities, and surfaces trusted lowest-price booking links.",
            "packingList": [],
            "sources": [],
        }
    return {
        "message": "I can explain route logic, build a packing list, or help you understand transport and compliance details.",
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
        "Be friendly, concise, and useful. Answer questions about the route, explain recommendations, "
        "and when the user asks for packing help produce a practical packing list based on climate, geography, "
        "planned activities, transport modes, and documents. Never tell the user to leave the page."
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
    parts = [platform, category]
    for key in ("fromName", "toName", "city", "hotel", "attraction", "airline", "operator"):
        value = context.get(key)
        if value:
            parts.append(str(value))
    return f"https://www.google.com/search?q={quote_plus(' '.join(parts))}"


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


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
