from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from werkzeug.security import generate_password_hash


def _default_config_file() -> Path:
    explicit = os.getenv("CFDDNS_CONFIG_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    if os.geteuid() == 0:
        return Path("/usr/share/cfddns/config.json")

    return Path("~/.config/cfddns/config.json").expanduser()


def _legacy_config_file() -> Path:
    return Path("data/config.json")


@dataclass
class ProfileConfig:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Default"
    api_token: str = ""
    zone_id: str = ""
    record_type: str = "A"
    record_names_csv: str = ""
    ttl: int = 1
    proxied: bool = False
    interval_seconds: int = 300
    enabled: bool = True


@dataclass
class AuthConfig:
    username: str = "admin"
    password_hash: str = field(default_factory=lambda: generate_password_hash("admin"))


@dataclass
class AppData:
    profiles: list[ProfileConfig] = field(default_factory=list)
    selected_profile_id: str | None = None
    auth: AuthConfig = field(default_factory=AuthConfig)


class ConfigStore:
    def __init__(self, config_file: Path | None = None) -> None:
        self.config_file = config_file or _default_config_file()
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        legacy = _legacy_config_file()
        if not self.config_file.exists() and legacy.exists():
            self.config_file.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")

        if not self.config_file.exists():
            default_profile = ProfileConfig(name="Default")
            self.save(
                AppData(
                    profiles=[default_profile],
                    selected_profile_id=default_profile.id,
                    auth=AuthConfig(),
                )
            )

    def load(self) -> AppData:
        with self._lock:
            with self.config_file.open("r", encoding="utf-8") as f:
                raw = json.load(f)

        if "api_token" in raw:
            migrated_profile = ProfileConfig(
                name="Default",
                api_token=raw.get("api_token", ""),
                zone_id=raw.get("zone_id", ""),
                record_type=raw.get("record_type", "A"),
                record_names_csv=raw.get("record_names_csv", ""),
                ttl=int(raw.get("ttl", 1) or 1),
                proxied=bool(raw.get("proxied", False)),
                interval_seconds=max(30, int(raw.get("interval_seconds", 300) or 300)),
                enabled=bool(raw.get("enabled", True)),
            )
            migrated = AppData(
                profiles=[migrated_profile],
                selected_profile_id=migrated_profile.id,
                auth=AuthConfig(),
            )
            self.save(migrated)
            return migrated

        profiles = [ProfileConfig(**item) for item in raw.get("profiles", [])]
        if not profiles:
            profiles = [ProfileConfig(name="Default")]

        selected_profile_id = raw.get("selected_profile_id")
        if selected_profile_id not in {p.id for p in profiles}:
            selected_profile_id = profiles[0].id

        auth_raw = raw.get("auth", {})
        auth = AuthConfig(
            username=auth_raw.get("username", "admin"),
            password_hash=auth_raw.get("password_hash") or generate_password_hash("admin"),
        )

        return AppData(
            profiles=profiles,
            selected_profile_id=selected_profile_id,
            auth=auth,
        )

    def save(self, data: AppData) -> None:
        with self._lock:
            with self.config_file.open("w", encoding="utf-8") as f:
                json.dump(asdict(data), f, indent=2)
