from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


SEED_FLAGGED_PLATFORMS = {
    "FlashFare": {
        "source": "seed",
        "reason": "Chargeback complaints and hidden-fee patterns",
    },
    "BargainRoost": {
        "source": "seed",
        "reason": "Bait pricing and refund dispute complaints",
    },
    "TicketBlitz": {
        "source": "seed",
        "reason": "Poor fulfillment and cancellation handling",
    },
}


DEFAULT_PROFILE = {
    "attractionTypes": {},
    "destinations": {},
    "transportPriority": {},
    "hotels": {},
    "savedAttractions": {},
    "addedCities": {},
    "skippedCities": {},
    "packingItems": {},
}


GLOBAL_SIGNAL_KEYS = {
    "attractionTypes",
    "destinations",
    "transportPriority",
    "hotels",
    "savedAttractions",
    "addedCities",
}


PROFILE_FIELD_BY_EVENT = {
    "trip_attraction_type": "attractionTypes",
    "trip_destination": "destinations",
    "transport_priority": "transportPriority",
    "hotel_hold": "hotels",
    "attraction_save": "savedAttractions",
    "city_add": "addedCities",
    "city_skip": "skippedCities",
    "packing_item": "packingItems",
}


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cluster TEXT,
                    profile_json TEXT NOT NULL,
                    last_trip_json TEXT,
                    george_previous_response_id TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    entity_value TEXT NOT NULL,
                    delta INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    payload_json TEXT
                );

                CREATE TABLE IF NOT EXISTS platform_flags (
                    platform TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    flagged_by TEXT,
                    flagged_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                """
            )

    def ensure_profile(self, session_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT profile_json, last_trip_json, george_previous_response_id, cluster FROM user_profiles WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return self._row_to_profile(row)

            now = utc_now()
            profile_json = json.dumps(deepcopy(DEFAULT_PROFILE))
            connection.execute(
                """
                INSERT INTO user_profiles (session_id, created_at, updated_at, cluster, profile_json, last_trip_json, george_previous_response_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, "", profile_json, None, None),
            )
            return {
                "profile": deepcopy(DEFAULT_PROFILE),
                "lastTrip": None,
                "georgePreviousResponseId": None,
                "cluster": "",
            }

    def get_profile_record(self, session_id: str) -> dict:
        return self.ensure_profile(session_id)

    def remember_trip(self, session_id: str, trip: dict) -> dict:
        record = self.ensure_profile(session_id)
        profile = deepcopy(record["profile"])

        for attraction_type in trip.get("attractionTypes", []):
            bump_counter(profile["attractionTypes"], attraction_type, 1)
            self.record_event(session_id, "trip_attraction_type", "attractionTypes", attraction_type, 1)

        for destination in trip.get("destinations", []):
            bump_counter(profile["destinations"], destination, 1)
            self.record_event(session_id, "trip_destination", "destinations", destination, 1)

        transport_priority = trip.get("transportPriority")
        if transport_priority:
            bump_counter(profile["transportPriority"], transport_priority, 1)
            self.record_event(session_id, "transport_priority", "transportPriority", transport_priority, 1)

        self.save_profile(
            session_id,
            profile,
            last_trip=trip,
            george_previous_response_id=record.get("georgePreviousResponseId"),
        )
        return self.build_memory_snapshot(session_id)

    def apply_feedback(self, session_id: str, event_type: str, entity_value: str, delta: int = 1, payload: dict | None = None) -> dict:
        record = self.ensure_profile(session_id)
        profile = deepcopy(record["profile"])
        field = PROFILE_FIELD_BY_EVENT.get(event_type)
        if field:
            bump_counter(profile[field], entity_value, delta)
            self.record_event(session_id, event_type, field, entity_value, delta, payload)
            self.save_profile(
                session_id,
                profile,
                last_trip=record.get("lastTrip"),
                george_previous_response_id=record.get("georgePreviousResponseId"),
            )
        return self.build_memory_snapshot(session_id)

    def record_event(
        self,
        session_id: str,
        event_type: str,
        entity_kind: str,
        entity_value: str,
        delta: int = 1,
        payload: dict | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events (session_id, event_type, entity_kind, entity_value, delta, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, event_type, entity_kind, entity_value, delta, utc_now(), json.dumps(payload or {})),
            )

    def save_profile(
        self,
        session_id: str,
        profile: dict,
        *,
        last_trip: dict | None,
        george_previous_response_id: str | None,
    ) -> None:
        cluster = determine_cluster(profile)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE user_profiles
                SET updated_at = ?, cluster = ?, profile_json = ?, last_trip_json = ?, george_previous_response_id = ?
                WHERE session_id = ?
                """,
                (
                    utc_now(),
                    cluster,
                    json.dumps(profile),
                    json.dumps(last_trip) if last_trip else None,
                    george_previous_response_id,
                    session_id,
                ),
            )

    def set_george_previous_response_id(self, session_id: str, response_id: str | None) -> None:
        record = self.ensure_profile(session_id)
        self.save_profile(
            session_id,
            record["profile"],
            last_trip=record.get("lastTrip"),
            george_previous_response_id=response_id,
        )

    def flag_platform(self, session_id: str, platform: str, reason: str, source: str = "user") -> dict:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO platform_flags (platform, reason, source, flagged_by, flagged_at, active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(platform) DO UPDATE SET
                    reason = excluded.reason,
                    source = excluded.source,
                    flagged_by = excluded.flagged_by,
                    flagged_at = excluded.flagged_at,
                    active = 1
                """,
                (platform, reason, source, session_id, utc_now()),
            )
        return self.build_memory_snapshot(session_id)

    def build_memory_snapshot(self, session_id: str) -> dict:
        record = self.ensure_profile(session_id)
        profile = deepcopy(record["profile"])
        global_signals = self._aggregate_global_signals(record["cluster"])
        flagged = deepcopy(SEED_FLAGGED_PLATFORMS)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT platform, reason, source, flagged_at FROM platform_flags WHERE active = 1"
            ).fetchall()
        for row in rows:
            flagged[row["platform"]] = {
                "source": row["source"],
                "reason": row["reason"],
                "flaggedAt": row["flagged_at"],
            }

        return {
            "flaggedPlatforms": flagged,
            "profile": profile,
            "globalSignals": global_signals,
            "lastTrip": record.get("lastTrip"),
        }

    def reset_session(self, session_id: str) -> dict:
        with self._connect() as connection:
            connection.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            connection.execute(
                """
                UPDATE user_profiles
                SET updated_at = ?, cluster = ?, profile_json = ?, last_trip_json = ?, george_previous_response_id = ?
                WHERE session_id = ?
                """,
                (utc_now(), "", json.dumps(deepcopy(DEFAULT_PROFILE)), None, None, session_id),
            )
        return self.build_memory_snapshot(session_id)

    def _aggregate_global_signals(self, cluster: str) -> dict:
        global_signals = {key: {} for key in GLOBAL_SIGNAL_KEYS}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT entity_kind, entity_value, SUM(delta) AS total
                FROM events
                GROUP BY entity_kind, entity_value
                """
            ).fetchall()
            for row in rows:
                if row["entity_kind"] in global_signals:
                    global_signals[row["entity_kind"]][row["entity_value"]] = max(0, int(row["total"]))

            if cluster:
                cluster_rows = connection.execute(
                    """
                    SELECT events.entity_kind, events.entity_value, SUM(events.delta) AS total
                    FROM events
                    JOIN user_profiles ON user_profiles.session_id = events.session_id
                    WHERE user_profiles.cluster = ?
                    GROUP BY events.entity_kind, events.entity_value
                    """,
                    (cluster,),
                ).fetchall()
                for row in cluster_rows:
                    if row["entity_kind"] in global_signals:
                        current = global_signals[row["entity_kind"]].get(row["entity_value"], 0)
                        global_signals[row["entity_kind"]][row["entity_value"]] = current + max(0, int(row["total"] * 0.35))
        return global_signals

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> dict:
        return {
            "profile": json.loads(row["profile_json"] or "{}") or deepcopy(DEFAULT_PROFILE),
            "lastTrip": json.loads(row["last_trip_json"]) if row["last_trip_json"] else None,
            "georgePreviousResponseId": row["george_previous_response_id"],
            "cluster": row["cluster"] or "",
        }


def determine_cluster(profile: dict) -> str:
    attraction_types = sorted(
        ((name, count) for name, count in profile.get("attractionTypes", {}).items() if count > 0),
        key=lambda item: (-item[1], item[0]),
    )
    if not attraction_types:
        return ""
    top_two = [name for name, _count in attraction_types[:2]]
    return "|".join(top_two)


def bump_counter(counter: dict, key: str, delta: int) -> None:
    counter[key] = max(0, int(counter.get(key, 0)) + delta)


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
