from __future__ import annotations

import sys

from cfddns.cloudflare_ddns import CloudflareDDNS
from cfddns.config_store import ConfigStore


def run_profile(profile) -> int:
    updater = CloudflareDDNS(profile.api_token, profile.zone_id)
    result = updater.update_records(
        [name.strip() for name in profile.record_names_csv.split(",") if name.strip()],
        record_type=profile.record_type,
        ttl=profile.ttl,
        proxied=profile.proxied,
    )
    print(f"[{profile.name}] {result.message}")
    if result.current_ip:
        print(f"[{profile.name}] Current IP: {result.current_ip}")
    return 0 if result.success else 1


def main() -> int:
    data = ConfigStore().load()
    args = [arg.strip() for arg in sys.argv[1:] if arg.strip()]

    if args and args[0] == "--all-enabled":
        exit_code = 0
        for profile in data.profiles:
            if profile.enabled:
                exit_code = max(exit_code, run_profile(profile))
        return exit_code

    target_key = args[0] if args else data.selected_profile_id
    profile = next(
        (item for item in data.profiles if item.id == target_key or item.name == target_key),
        None,
    )
    if profile is None:
        print("Profile not found. Use a profile ID/name or --all-enabled.")
        return 1

    return run_profile(profile)


if __name__ == "__main__":
    raise SystemExit(main())
