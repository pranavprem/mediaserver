#!/usr/bin/env python3
from __future__ import annotations

import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

DEFAULT_STASH_PORT = "9998"
DEFAULT_STASHARR_PORT = "3000"
DEFAULT_STASHARR_IMAGE_TAG = "latest"
DEFAULT_STASHARR_DB_NAME = "stasharr"
DEFAULT_STASHARR_DB_USER = "stasharr"
DEFAULT_STASHARR_ADMIN_USERNAME = "admin"
DEFAULT_STASHARR_CATALOG_PROVIDER = "STASHDB"
DEFAULT_STASHARR_STASH_BASE_URL = "http://stash:9999"
DEFAULT_STASHARR_SESSION_COOKIE_SECURE = "false"
PROFILE_NAME = "stasharr"


class HttpFailure(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def env_file_path() -> Path:
    return repo_root() / ".env"


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env

    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        env[key.strip()] = strip_matching_quotes(value.strip())
    return env


def strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def merged_env(path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key, value in load_env_file(path).items():
        if value or key not in env or not env[key]:
            env[key] = value
    return env


def random_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)[:length]


def default_catalog_base_url(provider: str) -> str:
    normalized = provider.strip().upper()
    if normalized == "FANSDB":
        return "https://fansdb.cc"
    return "https://stashdb.org"


def append_profile(existing: str, profile: str) -> str:
    values = [item.strip() for item in existing.split(",") if item.strip()]
    if profile not in values:
        values.append(profile)
    return ",".join(values)


def upsert_env_values(path: Path, updates: dict[str, str]) -> set[str]:
    lines = path.read_text().splitlines() if path.exists() else []
    changed_keys: set[str] = set()
    appended_block_started = False

    def match_key(raw_line: str, key: str) -> bool:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            return False
        existing_key, _ = raw_line.split("=", 1)
        return existing_key.strip() == key

    for key, value in updates.items():
        rendered = f"{key}={value}"
        for index, raw_line in enumerate(lines):
            if not match_key(raw_line, key):
                continue
            _, existing_value = raw_line.split("=", 1)
            if existing_value.strip() == value:
                break
            lines[index] = rendered
            changed_keys.add(key)
            break
        else:
            if not appended_block_started and lines and lines[-1].strip():
                lines.append("")
            appended_block_started = True
            lines.append(rendered)
            changed_keys.add(key)

    if changed_keys:
        path.write_text("\n".join(lines).rstrip() + "\n")
    return changed_keys


def ensure_local_env(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    if not path.exists():
        raise SystemExit("❌ Missing .env. Copy example.env to .env first.")

    current = load_env_file(path)
    provider = (current.get("STASHARR_CATALOG_PROVIDER") or DEFAULT_STASHARR_CATALOG_PROVIDER).strip().upper()
    if provider not in {"STASHDB", "FANSDB"}:
        raise SystemExit(
            f"❌ STASHARR_CATALOG_PROVIDER must be STASHDB or FANSDB, got: {provider}"
        )

    defaults: dict[str, str] = {
        "STASH_PORT": current.get("STASH_PORT") or DEFAULT_STASH_PORT,
        "STASHARR_PORT": current.get("STASHARR_PORT") or DEFAULT_STASHARR_PORT,
        "STASHARR_IMAGE_TAG": current.get("STASHARR_IMAGE_TAG") or DEFAULT_STASHARR_IMAGE_TAG,
        "STASHARR_DB_NAME": current.get("STASHARR_DB_NAME") or DEFAULT_STASHARR_DB_NAME,
        "STASHARR_DB_USER": current.get("STASHARR_DB_USER") or DEFAULT_STASHARR_DB_USER,
        "STASHARR_POSTGRES_PASSWORD": current.get("STASHARR_POSTGRES_PASSWORD") or random_secret(),
        "STASHARR_ADMIN_USERNAME": current.get("STASHARR_ADMIN_USERNAME") or DEFAULT_STASHARR_ADMIN_USERNAME,
        "STASHARR_ADMIN_PASSWORD": current.get("STASHARR_ADMIN_PASSWORD") or random_secret(),
        "STASHARR_CATALOG_PROVIDER": provider,
        "STASHARR_CATALOG_BASE_URL": current.get("STASHARR_CATALOG_BASE_URL") or default_catalog_base_url(provider),
        "STASHARR_CATALOG_API_KEY": current.get("STASHARR_CATALOG_API_KEY", ""),
        "STASHARR_SESSION_COOKIE_SECURE": current.get("STASHARR_SESSION_COOKIE_SECURE") or DEFAULT_STASHARR_SESSION_COOKIE_SECURE,
        "STASHARR_STASH_BASE_URL": current.get("STASHARR_STASH_BASE_URL") or DEFAULT_STASHARR_STASH_BASE_URL,
        "STASHARR_WHISPARR_BASE_URL": current.get("STASHARR_WHISPARR_BASE_URL") or f"http://gluetun:{current.get('WHISPARR_PORT') or '6969'}",
        "STASHARR_TRIGGER_INITIAL_SCAN": current.get("STASHARR_TRIGGER_INITIAL_SCAN") or "true",
        "STASHARR_RESCAN": current.get("STASHARR_RESCAN") or "false",
        "COMPOSE_PROFILES": append_profile(current.get("COMPOSE_PROFILES", ""), PROFILE_NAME),
    }

    changed = upsert_env_values(path, defaults)
    generated: dict[str, str] = {}
    for key in ("STASHARR_POSTGRES_PASSWORD", "STASHARR_ADMIN_PASSWORD"):
        if key in changed and not current.get(key):
            generated[key] = defaults[key]
    if "STASHARR_ADMIN_USERNAME" in changed and not current.get("STASHARR_ADMIN_USERNAME"):
        generated["STASHARR_ADMIN_USERNAME"] = defaults["STASHARR_ADMIN_USERNAME"]

    return defaults, generated


def require_path(env: dict[str, str], key: str) -> Path:
    value = (env.get(key) or "").strip()
    if not value or value.startswith("/path/to/"):
        raise SystemExit(f"❌ Set {key} in .env first.")
    return Path(value).expanduser()


def env_int(env: dict[str, str], key: str, default: int) -> int:
    value = (env.get(key) or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"❌ {key} must be an integer, got: {value}") from exc


def env_bool(env: dict[str, str], key: str, default: bool) -> bool:
    value = (env.get(key) or "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise SystemExit(f"❌ {key} must be a boolean, got: {value}")


def ensure_directories(config_root: Path, adult_root: Path) -> None:
    required = [
        adult_root,
        config_root / "stash" / "config",
        config_root / "stash" / "metadata",
        config_root / "stash" / "cache",
        config_root / "stash" / "blobs",
        config_root / "stash" / "generated",
        config_root / "stasharr" / "app",
        config_root / "stasharr" / "postgres",
    ]
    for path in required:
        path.mkdir(parents=True, exist_ok=True)


def run_compose_up(env: dict[str, str]) -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            PROFILE_NAME,
            "up",
            "-d",
            "gluetun",
            "whisparr",
            "stash",
            "stasharr-postgres",
            "stasharr",
        ],
        cwd=repo_root(),
        check=True,
        env=env,
    )


def container_status(name: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
            name,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def wait_for_container(name: str, timeout: int = 240) -> None:
    deadline = time.time() + timeout
    last_status = "unknown"
    while time.time() < deadline:
        try:
            last_status = container_status(name)
        except subprocess.CalledProcessError:
            last_status = "missing"
        if last_status in {"healthy", "running"}:
            return
        if last_status in {"exited", "dead", "unhealthy"}:
            raise SystemExit(f"❌ Container {name} is {last_status}")
        time.sleep(3)
    raise SystemExit(f"❌ Timed out waiting for {name} (last status: {last_status})")


def wait_for_path(path: Path, label: str, timeout: int = 180) -> None:
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


class JsonSession:
    def __init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        payload: Any | None = None,
        timeout: int = 30,
    ) -> Any:
        request_headers = dict(headers or {})
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type or raw[:1] in {"{", "["}:
                    return json.loads(raw)
                return raw
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise HttpFailure(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise HttpFailure(f"{method} {url} failed: {exc}") from exc


def wait_for_json_url(
    session: JsonSession,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 180,
) -> Any:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return session.request(url, headers=headers)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    raise SystemExit(f"❌ Timed out waiting for {url}: {last_error}")


def whisparr_headers(api_key: str) -> dict[str, str]:
    return {"X-Api-Key": api_key}


def normalize_url(url: str) -> str:
    return url.rstrip("/")


def ensure_whisparr_root_folder(base_url: str, api_key: str, target_path: str) -> None:
    session = JsonSession()
    url = f"{normalize_url(base_url)}/api/v3/rootfolder"
    payload = wait_for_json_url(session, url, headers=whisparr_headers(api_key))
    if not isinstance(payload, list):
        raise SystemExit("❌ Unexpected Whisparr rootfolder response")

    target = target_path.rstrip("/")
    for folder in payload:
        if str(folder.get("path", "")).rstrip("/") == target:
            if folder.get("accessible") is False:
                raise SystemExit(
                    f"❌ Whisparr root folder {target} exists but is not accessible."
                )
            return

    session.request(
        url,
        method="POST",
        headers=whisparr_headers(api_key),
        payload={"path": target},
    )

    payload = wait_for_json_url(session, url, headers=whisparr_headers(api_key))
    if not isinstance(payload, list) or not any(
        str(folder.get("path", "")).rstrip("/") == target and folder.get("accessible") is not False
        for folder in payload
    ):
        raise SystemExit(f"❌ Failed to create accessible Whisparr root folder {target}")


def stash_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["ApiKey"] = api_key
    return headers


class StashClient:
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = normalize_url(base_url)
        self.api_key = api_key.strip() if api_key else None
        self.session = JsonSession()

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self.session.request(
            f"{self.base_url}/graphql",
            method="POST",
            headers=stash_headers(self.api_key),
            payload={"query": query, "variables": variables or {}},
        )
        if not isinstance(payload, dict):
            raise HttpFailure("Unexpected Stash GraphQL response")
        errors = payload.get("errors")
        if errors:
            raise HttpFailure(json.dumps(errors))
        return payload

    def wait_ready(self, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                self.graphql("query ConnectivityCheck { __typename }")
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2)
        raise SystemExit(f"❌ Timed out waiting for Stash GraphQL: {last_error}")

    def current_stashes(self) -> list[dict[str, Any]] | None:
        try:
            payload = self.graphql(
                """
                query Configuration {
                  configuration {
                    general {
                      stashes {
                        path
                        excludeVideo
                        excludeImage
                      }
                    }
                  }
                }
                """
            )
        except HttpFailure:
            return None

        stashes = (
            payload.get("data", {})
            .get("configuration", {})
            .get("general", {})
            .get("stashes")
        )
        return stashes if isinstance(stashes, list) else []

    def setup_initial_library(self, target_path: str) -> bool:
        current = self.current_stashes()
        desired_entry = {
            "path": target_path,
            "excludeVideo": False,
            "excludeImage": False,
        }

        if current is None:
            self.graphql(
                """
                mutation Setup($input: SetupInput!) {
                  setup(input: $input)
                }
                """,
                {
                    "input": {
                        "configLocation": "",
                        "stashes": [desired_entry],
                        "sfwContentMode": False,
                        "databaseFile": "",
                        "generatedLocation": "/generated",
                        "cacheLocation": "/cache",
                        "storeBlobsInDatabase": False,
                        "blobsLocation": "/blobs",
                    }
                },
            )
            return True

        normalized_target = target_path.rstrip("/")
        updated: list[dict[str, Any]] = []
        changed = False
        found = False
        for entry in current:
            entry_path = str(entry.get("path", "")).rstrip("/")
            if entry_path == normalized_target:
                found = True
                merged = {
                    "path": target_path,
                    "excludeVideo": False,
                    "excludeImage": False,
                }
                if entry.get("excludeVideo") or entry.get("excludeImage") or entry_path != target_path:
                    changed = True
                updated.append(merged)
            else:
                updated.append(
                    {
                        "path": entry.get("path") or entry_path,
                        "excludeVideo": bool(entry.get("excludeVideo")),
                        "excludeImage": bool(entry.get("excludeImage")),
                    }
                )

        if not found:
            updated.append(desired_entry)
            changed = True

        if changed:
            self.graphql(
                """
                mutation ConfigureGeneral($input: ConfigGeneralInput!) {
                  configureGeneral(input: $input) {
                    stashes {
                      path
                    }
                  }
                }
                """,
                {"input": {"stashes": updated}},
            )
        return changed

    def scan_library(self, target_path: str, *, rescan: bool = False) -> str | None:
        payload = self.graphql(
            """
            mutation Scan($input: ScanMetadataInput!) {
              metadataScan(input: $input)
            }
            """,
            {"input": {"paths": [target_path], "rescan": rescan}},
        )
        job_id = payload.get("data", {}).get("metadataScan")
        return str(job_id) if job_id else None


def wait_for_stasharr(base_url: str) -> dict[str, Any]:
    session = JsonSession()
    payload = wait_for_json_url(session, f"{normalize_url(base_url)}/api/auth/status")
    if not isinstance(payload, dict):
        raise SystemExit("❌ Unexpected Stasharr auth status response")
    return payload


def ensure_stasharr_session(base_url: str, username: str, password: str) -> JsonSession:
    session = JsonSession()
    auth_status_url = f"{normalize_url(base_url)}/api/auth/status"
    payload = wait_for_json_url(session, auth_status_url)
    if not isinstance(payload, dict):
        raise SystemExit("❌ Unexpected Stasharr auth status response")

    if payload.get("bootstrapRequired"):
        payload = session.request(
            f"{normalize_url(base_url)}/api/auth/bootstrap",
            method="POST",
            payload={"username": username, "password": password},
        )
    elif not payload.get("authenticated"):
        payload = session.request(
            f"{normalize_url(base_url)}/api/auth/login",
            method="POST",
            payload={"username": username, "password": password},
        )

    if not isinstance(payload, dict) or not payload.get("authenticated"):
        raise SystemExit(
            "❌ Failed to authenticate to Stasharr. Check STASHARR_ADMIN_USERNAME / STASHARR_ADMIN_PASSWORD in .env."
        )

    return session


def configure_stasharr_integrations(
    session: JsonSession,
    base_url: str,
    env: dict[str, str],
    whisparr_api_key: str,
) -> None:
    setup_status = session.request(f"{normalize_url(base_url)}/api/setup/status")
    if not isinstance(setup_status, dict):
        raise SystemExit("❌ Unexpected Stasharr setup status response")

    desired_provider = (env.get("STASHARR_CATALOG_PROVIDER") or DEFAULT_STASHARR_CATALOG_PROVIDER).strip().upper()
    current_provider = setup_status.get("catalogProvider")
    if current_provider and current_provider != desired_provider:
        session.request(
            f"{normalize_url(base_url)}/api/integrations/{current_provider}",
            method="DELETE",
        )

    integrations: list[tuple[str, dict[str, Any]]] = [
        (
            desired_provider,
            {
                "baseUrl": env.get("STASHARR_CATALOG_BASE_URL") or default_catalog_base_url(desired_provider),
                "apiKey": env.get("STASHARR_CATALOG_API_KEY", ""),
            },
        ),
        (
            "STASH",
            {
                "enabled": True,
                "name": "Local Stash",
                "baseUrl": env.get("STASHARR_STASH_BASE_URL") or DEFAULT_STASHARR_STASH_BASE_URL,
                "apiKey": env.get("STASH_API_KEY", ""),
            },
        ),
        (
            "WHISPARR",
            {
                "enabled": True,
                "name": "Whisparr",
                "baseUrl": env.get("STASHARR_WHISPARR_BASE_URL") or f"http://gluetun:{env.get('WHISPARR_PORT') or '6969'}",
                "apiKey": whisparr_api_key,
            },
        ),
    ]

    for integration_type, payload in integrations:
        session.request(
            f"{normalize_url(base_url)}/api/integrations/{integration_type}",
            method="PUT",
            payload=payload,
        )
        test_response = session.request(
            f"{normalize_url(base_url)}/api/integrations/{integration_type}/test",
            method="POST",
            payload=payload,
        )
        if not isinstance(test_response, dict):
            raise SystemExit(f"❌ Unexpected Stasharr response while testing {integration_type}")
        if test_response.get("status") != "CONFIGURED":
            detail = test_response.get("lastErrorMessage") or f"{integration_type} test failed"
            raise SystemExit(f"❌ {integration_type} integration failed: {detail}")

    final_status = session.request(f"{normalize_url(base_url)}/api/setup/status")
    if not isinstance(final_status, dict) or not final_status.get("setupComplete"):
        raise SystemExit("❌ Stasharr setup is still incomplete after integration bootstrap.")


def main() -> int:
    env_path = env_file_path()
    _, generated = ensure_local_env(env_path)
    env = merged_env(env_path)

    config_root = require_path(env, "CONFIG_ROOT")
    adult_root = require_path(env, "ADULT_ROOT")

    ensure_directories(config_root, adult_root)

    compose_env = dict(os.environ)
    compose_env.update(env)
    compose_env["COMPOSE_PROFILES"] = append_profile(env.get("COMPOSE_PROFILES", ""), PROFILE_NAME)

    print("🚀 Starting Stash / Stasharr services...")
    run_compose_up(compose_env)

    for container_name in ["gluetun", "whisparr", "stash", "stasharr-postgres", "stasharr"]:
        wait_for_container(container_name)

    whisparr_config = config_root / "whisparr" / "config.xml"
    wait_for_path(whisparr_config, "Whisparr config.xml")
    whisparr_api_key = read_arr_api_key(whisparr_config)
    whisparr_port = env_int(env, "WHISPARR_PORT", 6969)
    whisparr_base_url = f"http://127.0.0.1:{whisparr_port}"
    wait_for_json_url(
        JsonSession(),
        f"{normalize_url(whisparr_base_url)}/api/v3/system/status",
        headers=whisparr_headers(whisparr_api_key),
    )
    ensure_whisparr_root_folder(whisparr_base_url, whisparr_api_key, "/adult")

    stash_port = env_int(env, "STASH_PORT", 9998)
    stash_host_url = f"http://127.0.0.1:{stash_port}"
    stash_api_key = (env.get("STASH_API_KEY") or "").strip() or None
    stash = StashClient(stash_host_url, stash_api_key)
    stash.wait_ready()
    stash_changed = stash.setup_initial_library("/data")

    should_scan = env_bool(env, "STASHARR_TRIGGER_INITIAL_SCAN", True)
    force_rescan = env_bool(env, "STASHARR_RESCAN", False)
    scan_job_id: str | None = None
    if should_scan and (stash_changed or force_rescan):
        scan_job_id = stash.scan_library("/data", rescan=force_rescan)

    stasharr_port = env_int(env, "STASHARR_PORT", 3000)
    stasharr_url = f"http://127.0.0.1:{stasharr_port}"
    wait_for_stasharr(stasharr_url)
    username = env.get("STASHARR_ADMIN_USERNAME") or DEFAULT_STASHARR_ADMIN_USERNAME
    password = env.get("STASHARR_ADMIN_PASSWORD") or ""
    if len(password) < 12:
        raise SystemExit("❌ STASHARR_ADMIN_PASSWORD must be at least 12 characters.")

    stasharr_session = ensure_stasharr_session(stasharr_url, username, password)
    configure_stasharr_integrations(stasharr_session, stasharr_url, env, whisparr_api_key)

    print("✅ Stasharr bootstrap complete.")
    print(f"   Stash:     {stash_host_url}")
    print(f"   Stasharr:  {stasharr_url}")
    if scan_job_id:
        print(f"   Stash scan job queued: {scan_job_id}")
    else:
        print("   Stash scan not triggered (library already configured and STASHARR_RESCAN=false).")

    if generated:
        print("\n🔐 Generated local-only Stasharr credentials/settings were written to .env:")
        for key in sorted(generated):
            if key.endswith("PASSWORD"):
                print(f"   {key}=<generated>")
            else:
                print(f"   {key}={generated[key]}")
        if "STASHARR_ADMIN_PASSWORD" in generated:
            print("\n⚠️  Save this Stasharr login now:")
            print(f"   username: {username}")
            print(f"   password: {generated['STASHARR_ADMIN_PASSWORD']}")
            print("   Rotate it later if you want, but this gets you in immediately.")

    print("\n💡 Future deploys can use plain `make up` / `make down`; setup enabled the stasharr compose profile in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
