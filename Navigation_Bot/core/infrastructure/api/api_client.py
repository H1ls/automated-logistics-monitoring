from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests


class NavigationApiError(RuntimeError):
    pass


class NavigationApiClient:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout = timeout

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=json)

    def put(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return self._request("PUT", path, json=json)

    def login(self, username: str, password: str) -> dict[str, Any]:
        payload = self.post("/api/v1/auth/login", json={"username": username, "password": password})
        if isinstance(payload, dict):
            api_key = payload.get("api_key", "")
            if api_key:
                self.api_key = str(api_key)
        return payload

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        url = urljoin(self.base_url, path.lstrip("/"))
        try:
            response = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                try:
                    detail = f": {response.json()}"
                except ValueError:
                    detail = f": {response.text}"
            raise NavigationApiError(f"{method} {url} failed: {exc}{detail}") from exc
        if not response.content:
            return None
        return response.json()
