from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request


class OpenAIError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
        self.use_web_search = os.getenv("ATLAS_LANE_ENABLE_WEB_SEARCH", "0").strip() == "1"
        self.timeout_seconds = max(5, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "12") or "12"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def create_text_response(
        self,
        *,
        instructions: str,
        user_input: str,
        previous_response_id: str | None = None,
        use_web_search: bool = False,
        allowed_domains: list[str] | None = None,
        safety_identifier: str | None = None,
    ) -> tuple[str, str | None, list[dict]]:
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": user_input,
            "reasoning": {"effort": "low"},
            "text": {"format": {"type": "text"}},
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if safety_identifier:
            payload["safety_identifier"] = safety_identifier
        if use_web_search and self.use_web_search:
            payload["tools"] = [self._web_search_tool(allowed_domains)]
            payload["tool_choice"] = "auto"
            payload["include"] = ["web_search_call.action.sources"]
        response = self._post_json(payload)
        return extract_output_text(response), response.get("id"), extract_sources(response)

    def create_structured_response(
        self,
        *,
        instructions: str,
        user_input: str,
        schema_name: str,
        schema: dict,
        previous_response_id: str | None = None,
        use_web_search: bool = False,
        allowed_domains: list[str] | None = None,
        safety_identifier: str | None = None,
    ) -> tuple[dict, str | None, list[dict]]:
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": user_input,
            "reasoning": {"effort": "low"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if safety_identifier:
            payload["safety_identifier"] = safety_identifier
        if use_web_search and self.use_web_search:
            payload["tools"] = [self._web_search_tool(allowed_domains)]
            payload["tool_choice"] = "auto"
            payload["include"] = ["web_search_call.action.sources"]
        response = self._post_json(payload)
        text = extract_output_text(response)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise OpenAIError(f"Structured response was not valid JSON: {error}") from error
        return parsed, response.get("id"), extract_sources(response)

    def _web_search_tool(self, allowed_domains: list[str] | None) -> dict:
        tool = {
            "type": "web_search",
            "user_location": {
                "type": "approximate",
                "country": "US",
                "timezone": "America/Los_Angeles",
            },
        }
        if allowed_domains:
            tool["filters"] = {"allowed_domains": allowed_domains[:100]}
        return tool

    def _post_json(self, payload: dict) -> dict:
        if not self.api_key:
            raise OpenAIError("OPENAI_API_KEY is not configured.")

        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise OpenAIError(f"OpenAI API error {error.code}: {body}") from error
        except TimeoutError as error:
            raise OpenAIError("OpenAI request timed out, so Atlas Lane used a fallback response.") from error
        except socket.timeout as error:
            raise OpenAIError("OpenAI request timed out, so Atlas Lane used a fallback response.") from error
        except urllib.error.URLError as error:
            raise OpenAIError(f"Failed to reach OpenAI API: {error}") from error


def extract_output_text(response: dict) -> str:
    if isinstance(response.get("output_text"), str) and response["output_text"]:
        return response["output_text"]

    parts = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def extract_sources(response: dict) -> list[dict]:
    sources = []
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                for annotation in content.get("annotations", []) or []:
                    if annotation.get("type") == "url_citation":
                        sources.append(
                            {
                                "title": annotation.get("title", ""),
                                "url": annotation.get("url", ""),
                            }
                        )
        if item.get("type") == "web_search_call":
            action = item.get("action", {}) or {}
            for source in action.get("sources", []) or []:
                sources.append(
                    {
                        "title": source.get("title", ""),
                        "url": source.get("url", ""),
                    }
                )
    deduped = []
    seen = set()
    for source in sources:
        url = source.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(source)
    return deduped
