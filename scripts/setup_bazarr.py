#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

DEFAULT_PROFILE_NAME = "English + Spanish"
DEFAULT_LANGUAGES = ["en", "es"]


def wait_for_path(path: Path, label: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(2)
    raise SystemExit(f"❌ Timed out waiting for {label}: {path}")


def read_arr_api_key(path: Path) -> str:
    root = ET.parse(path).getroot()
    node = root.find("ApiKey")
    if node is None or not (node.text or "").strip():
        raise SystemExit(f"❌ Missing ApiKey in {path}")
    return node.text.strip()


def parse_bazarr_api_key(path: Path) -> str | None:
    lines = path.read_text().splitlines()
    in_auth = False
    auth_indent = 0

    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        if not in_auth:
            if stripped == "auth:":
                in_auth = True
                auth_indent = indent
            continue

        if indent <= auth_indent and stripped.endswith(":"):
            in_auth = False
            continue

        if stripped.startswith("apikey:"):
            value = stripped.split(":", 1)[1].strip().strip("\"'")
            return value or None

    return None


def wait_for_bazarr_api_key(path: Path, timeout: int = 120) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            value = parse_bazarr_api_key(path)
            if value:
                return value
        time.sleep(2)

    raise SystemExit(f"❌ Timed out waiting for auth.apikey in {path}")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"❌ {name} must be an integer, got: {value}") from exc


def request_json(url: str, apikey: str) -> object:
    req = urllib.request.Request(url, headers={"X-API-KEY": apikey})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_form(url: str, apikey: str, fields: list[tuple[str, str]]) -> None:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "X-API-KEY": apikey,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def apply_settings(url: str, apikey: str, fields: list[tuple[str, str]]) -> None:
    try:
        post_form(url, apikey, fields)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"Bazarr reset the connection while saving settings, verifying anyway: {exc}")


def wait_for_bazarr(api_url: str, apikey: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            request_json(f"{api_url}/api/system/languages", apikey)
            return
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(2)

    raise SystemExit(f"❌ Timed out waiting for Bazarr API at {api_url}: {last_error}")


def next_profile_id(existing_profiles: list[dict]) -> int:
    return max((int(profile["profileId"]) for profile in existing_profiles), default=0) + 1


def build_managed_profile(profile_id: int) -> dict:
    return {
        "profileId": profile_id,
        "name": DEFAULT_PROFILE_NAME,
        "cutoff": None,
        "items": [
            {
                "id": 1,
                "language": "en",
                "forced": "False",
                "hi": "False",
                "audio_exclude": "False",
                "audio_only_include": "False",
            },
            {
                "id": 2,
                "language": "es",
                "forced": "False",
                "hi": "False",
                "audio_exclude": "False",
                "audio_only_include": "False",
            },
        ],
        "mustContain": [],
        "mustNotContain": [],
        "originalFormat": 0,
        "tag": "",
    }


def merge_profiles(existing_profiles: list[dict]) -> tuple[list[dict], int]:
    managed = next((profile for profile in existing_profiles if profile.get("name") == DEFAULT_PROFILE_NAME), None)
    profile_id = int(managed["profileId"]) if managed else next_profile_id(existing_profiles)
    target = build_managed_profile(profile_id)

    merged: list[dict] = []
    replaced = False
    for profile in existing_profiles:
        if not replaced and (int(profile.get("profileId", 0)) == profile_id or profile.get("name") == DEFAULT_PROFILE_NAME):
            merged.append(target)
            replaced = True
        else:
            merged.append(profile)

    if not replaced:
        merged.append(target)

    return merged, profile_id


def merge_enabled_languages(existing_languages: list[dict]) -> list[str]:
    enabled_codes = [lang["code2"] for lang in existing_languages if lang.get("enabled")]
    for code in DEFAULT_LANGUAGES:
        if code not in enabled_codes:
            enabled_codes.append(code)
    return enabled_codes


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: setup_bazarr.py <CONFIG_ROOT>")

    config_root = Path(sys.argv[1]).expanduser()
    bazarr_config = config_root / "bazarr" / "config" / "config.yaml"
    sonarr_config = config_root / "sonarr" / "config.xml"
    radarr_config = config_root / "radarr" / "config.xml"

    wait_for_path(bazarr_config, "Bazarr config")
    wait_for_path(sonarr_config, "Sonarr config.xml")
    wait_for_path(radarr_config, "Radarr config.xml")

    bazarr_apikey = wait_for_bazarr_api_key(bazarr_config)
    sonarr_apikey = read_arr_api_key(sonarr_config)
    radarr_apikey = read_arr_api_key(radarr_config)

    bazarr_port = env_int("BAZARR_PORT", 6767)
    sonarr_port = env_int("SONARR_PORT", 8989)
    radarr_port = env_int("RADARR_PORT", 7878)
    bazarr_url = os.environ.get("BAZARR_URL", f"http://127.0.0.1:{bazarr_port}").rstrip("/")

    print(f"Waiting for Bazarr at {bazarr_url}...")
    wait_for_bazarr(bazarr_url, bazarr_apikey)

    existing_profiles = request_json(f"{bazarr_url}/api/system/languages/profiles", bazarr_apikey)
    if not isinstance(existing_profiles, list):
        raise SystemExit("❌ Unexpected Bazarr languages/profiles response")

    existing_languages = request_json(f"{bazarr_url}/api/system/languages", bazarr_apikey)
    if not isinstance(existing_languages, list):
        raise SystemExit("❌ Unexpected Bazarr languages response")

    merged_profiles, profile_id = merge_profiles(existing_profiles)
    enabled_languages = merge_enabled_languages(existing_languages)

    fields: list[tuple[str, str]] = [
        ("languages-profiles", json.dumps(merged_profiles)),
        ("settings-general-use_sonarr", "true"),
        ("settings-general-use_radarr", "true"),
        ("settings-general-serie_default_enabled", "true"),
        ("settings-general-serie_default_profile", str(profile_id)),
        ("settings-general-movie_default_enabled", "true"),
        ("settings-general-movie_default_profile", str(profile_id)),
        ("settings-general-single_language", "false"),
        ("settings-sonarr-ip", "127.0.0.1"),
        ("settings-sonarr-port", str(sonarr_port)),
        ("settings-sonarr-base_url", "/"),
        ("settings-sonarr-ssl", "false"),
        ("settings-sonarr-apikey", sonarr_apikey),
        ("settings-radarr-ip", "127.0.0.1"),
        ("settings-radarr-port", str(radarr_port)),
        ("settings-radarr-base_url", "/"),
        ("settings-radarr-ssl", "false"),
        ("settings-radarr-apikey", radarr_apikey),
    ]
    fields.extend(("languages-enabled", code) for code in enabled_languages)

    print(f"Configuring Bazarr default profile '{DEFAULT_PROFILE_NAME}'...")
    apply_settings(f"{bazarr_url}/api/system/settings", bazarr_apikey, fields)

    wait_for_bazarr(bazarr_url, bazarr_apikey)
    final_profiles = request_json(f"{bazarr_url}/api/system/languages/profiles", bazarr_apikey)
    if not isinstance(final_profiles, list):
        raise SystemExit("❌ Unexpected Bazarr languages/profiles response after update")

    if not any(int(profile.get("profileId", 0)) == profile_id and profile.get("name") == DEFAULT_PROFILE_NAME for profile in final_profiles):
        raise SystemExit("❌ Bazarr profile update did not stick")

    print(f"Configured Bazarr default profile '{DEFAULT_PROFILE_NAME}' (profileId={profile_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
