#!/usr/bin/env python3
import os
from pathlib import Path
import sys
from xml.etree import ElementTree as ET


def read_api_key(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"❌ Missing {path}")

    root = ET.parse(path).getroot()
    node = root.find("ApiKey")
    if node is None or not (node.text or "").strip():
        raise SystemExit(f"❌ Missing ApiKey in {path}")
    return node.text.strip()


def write_owner_only(path: Path, content: str) -> None:
    # The rendered file holds live API keys. Creating it 0600 up front avoids
    # the window where write_text() leaves it readable at the default umask;
    # the chmod covers a pre-existing file, whose mode O_CREAT does not change.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
    os.chmod(path, 0o600)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: render_recyclarr_config.py <CONFIG_ROOT>")

    config_root = Path(sys.argv[1]).expanduser()
    repo_root = Path(__file__).resolve().parent.parent
    template_path = repo_root / "recyclarr.yml"
    output_path = config_root / "recyclarr" / "recyclarr.yml"

    rendered = template_path.read_text()
    rendered = rendered.replace("__SONARR_API_KEY__", read_api_key(config_root / "sonarr" / "config.xml"))
    rendered = rendered.replace("__RADARR_API_KEY__", read_api_key(config_root / "radarr" / "config.xml"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_owner_only(output_path, rendered)
    print(f"Rendered {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
