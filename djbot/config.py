"""Load API credentials from env vars or a local config file.

Lookup order (later wins): config file -> environment variable. Nothing is ever
committed — config lives at ~/.config/djbot/config.json. Get free keys at:
  - Discogs:     https://www.discogs.com/settings/developers  (personal token)
  - GetSongBPM:  https://getsongbpm.com/api                  (free, needs a backlink)
  - cosine.club: https://cosine.club/account/api             (free, audio-similarity)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path.home() / ".config" / "djbot" / "config.json"

# config-key -> environment variable name
_ENV = {
    "discogs_token": "DISCOGS_TOKEN",
    "getsongbpm_key": "GETSONGBPM_API_KEY",
    "cosine_key": "COSINE_API_KEY",
    "tidal_client_id": "TIDAL_CLIENT_ID",
    "tidal_client_secret": "TIDAL_CLIENT_SECRET",
    "spotify_client_id": "SPOTIFY_CLIENT_ID",
}


def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    for key, env in _ENV.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


def get_key(name: str) -> Optional[str]:
    return load_config().get(name)


def set_key(name: str, value: str) -> None:
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    cfg[name] = value
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
