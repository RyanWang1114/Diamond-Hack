from __future__ import annotations

import json
import mimetypes
import os
import traceback
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent


def load_local_env(root: Path) -> None:
    for env_name in (".env", ".env.local"):
        env_path = root / env_name
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env(ROOT)

from backend.openai_client import OpenAIClient
from backend.live_data import LiveDataClient
from backend.planner import PlannerValidationError, TravelPlanner
from backend.storage import Storage

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "atlas_lane.db"
HOST = os.getenv("ATLAS_LANE_HOST", "127.0.0.1")
PORT = int(os.getenv("ATLAS_LANE_PORT", "8000"))


storage = Storage(DB_PATH)
ai_client = OpenAIClient()
live_data_client = LiveDataClient()
planner = TravelPlanner(storage, ai_client, live_data_client)


class AtlasLaneServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class AtlasLaneHandler(SimpleHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(20)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "openaiConfigured": ai_client.configured,
                    "liveData": live_data_client.live_sources_summary,
                    "dbPath": str(DB_PATH),
                    "apiBase": f"http://{HOST}:{PORT}",
                },
            )
            return

        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if body is None:
            return
        if not isinstance(body, dict):
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Body must be a JSON object"})
            return

        session_id = str(body.get("sessionId", "")).strip()
        if parsed.path != "/api/health" and not session_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "sessionId is required"})
            return

        try:
            if parsed.path == "/api/bootstrap":
                response = planner.bootstrap(session_id)
            elif parsed.path == "/api/suggestions":
                response = planner.suggestions(session_id, body.get("trip") or {})
            elif parsed.path == "/api/plan":
                response = planner.plan(session_id, body.get("trip") or {}, body.get("acceptedSuggestions") or [])
            elif parsed.path == "/api/feedback":
                response = planner.feedback(session_id, body)
            elif parsed.path == "/api/platform/flag":
                response = planner.flag_platform(session_id, str(body.get("platform", "")), str(body.get("reason", "User marked as suspicious")))
            elif parsed.path == "/api/george/chat":
                response = planner.george_chat(session_id, body)
            elif parsed.path == "/api/compliance":
                response = planner.refresh_compliance(session_id, body)
            elif parsed.path == "/api/reset":
                response = planner.reset(session_id)
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {parsed.path}"})
                return
        except PlannerValidationError as error:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "Atlas Lane hit an unexpected backend error. Please try again.",
                    "detail": str(error),
                },
            )
            return

        self._write_json(HTTPStatus.OK, response)

    def log_message(self, format: str, *args) -> None:
        return super().log_message(format, *args)

    def guess_type(self, path: str) -> str:
        content_type, _encoding = mimetypes.guess_type(path)
        return content_type or "application/octet-stream"

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Body must be valid JSON"})
            return None

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        super().end_headers()


def main() -> None:
    with AtlasLaneServer((HOST, PORT), AtlasLaneHandler) as server:
        print(f"Atlas Lane server running at http://{HOST}:{PORT}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
