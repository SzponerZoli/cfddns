from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


CF_API_BASE = "https://api.cloudflare.com/client/v4"
IP_SOURCES = {
    "A": "https://api.ipify.org",
    "AAAA": "https://api6.ipify.org",
}


@dataclass
class UpdateResult:
    success: bool
    message: str
    changed_records: int = 0
    current_ip: str | None = None


class CloudflareDDNS:
    def __init__(self, api_token: str, zone_id: str, timeout: int = 20) -> None:
        self.api_token = api_token.strip()
        self.zone_id = zone_id.strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def get_public_ip(self, record_type: str) -> str:
        source = IP_SOURCES.get(record_type)
        if not source:
            raise ValueError("record_type must be A or AAAA")
        response = requests.get(source, timeout=self.timeout)
        response.raise_for_status()
        return response.text.strip()

    def _cf_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{CF_API_BASE}{path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            errors = payload.get("errors", [])
            raise RuntimeError(f"Cloudflare API error: {errors}")
        return payload

    def update_records(
        self,
        record_names: list[str],
        record_type: str = "A",
        ttl: int = 1,
        proxied: bool = False,
    ) -> UpdateResult:
        if not self.api_token or not self.zone_id:
            return UpdateResult(False, "Missing API token or zone ID")

        cleaned_names = [name.strip() for name in record_names if name.strip()]
        if not cleaned_names:
            return UpdateResult(False, "No record names configured")

        try:
            ip = self.get_public_ip(record_type)
        except Exception as exc:
            return UpdateResult(False, f"Could not detect public IP: {exc}")

        changed = 0
        errors: list[str] = []

        for name in cleaned_names:
            try:
                record_resp = self._cf_request(
                    "GET",
                    f"/zones/{self.zone_id}/dns_records",
                    params={"type": record_type, "name": name, "per_page": 1},
                )
                records = record_resp.get("result", [])
                if not records:
                    errors.append(f"Record not found: {name} ({record_type})")
                    continue

                record = records[0]
                if record.get("content") == ip and record.get("proxied") == proxied:
                    continue

                self._cf_request(
                    "PATCH",
                    f"/zones/{self.zone_id}/dns_records/{record['id']}",
                    json={
                        "type": record_type,
                        "name": name,
                        "content": ip,
                        "ttl": ttl,
                        "proxied": proxied,
                    },
                )
                changed += 1
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if errors:
            message = "; ".join(errors)
            if changed:
                message = f"Updated {changed} records, with errors: {message}"
            return UpdateResult(False, message, changed_records=changed, current_ip=ip)

        return UpdateResult(True, f"Updated {changed} records", changed_records=changed, current_ip=ip)
