"""Configuration loading and validation."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CONFIG_KEYS = {
    "bind_host",
    "public_port",
    "local_host",
    "local_port",
    "advertise_host",
    "session_port_start",
    "session_port_end",
    "timeout",
    "debug",
    "log_file",
    "allowed_clients",
}


@dataclass(frozen=True)
class ProxyConfig:
    """Runtime configuration for the Chroma SDK LAN proxy."""

    bind_host: str = "0.0.0.0"
    public_port: int = 15435
    local_host: str = "127.0.0.1"
    local_port: int = 54235
    advertise_host: str | None = None
    session_port_start: int = 15436
    session_port_end: int = 15499
    timeout: float = 10.0
    debug: bool = False
    log_file: str | None = None
    allowed_clients: tuple[str, ...] = ()

    def to_json(self) -> str:
        """Return a stable JSON representation for diagnostics."""

        data = asdict(self)
        data["allowed_clients"] = list(self.allowed_clients)
        return json.dumps(data, indent=2, sort_keys=True)


def load_config(path: str | Path | None) -> dict[str, Any]:
    """Load a TOML configuration file."""

    if not path:
        return {}

    config_path = Path(expand_path(path))
    if not config_path.exists():
        raise FileNotFoundError(f"config file does not exist: {config_path}")

    with config_path.open("rb") as file:
        data = tomllib.load(file)

    unknown_keys = set(data) - CONFIG_KEYS
    if unknown_keys:
        keys = ", ".join(sorted(unknown_keys))
        raise ValueError(f"unknown config option(s): {keys}")

    return data


def build_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> ProxyConfig:
    """Build the effective configuration from defaults, file, and CLI values."""

    data: dict[str, Any] = {}
    data.update(load_config(config_path))

    for key, value in (overrides or {}).items():
        if value is not None:
            data[key] = value

    data = normalize_config_data(data)
    config = ProxyConfig(**data)
    validate_config(config)
    return config


def normalize_config_data(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize values loaded from TOML or argparse."""

    normalized = dict(data)

    if "log_file" in normalized and normalized["log_file"]:
        normalized["log_file"] = expand_path(str(normalized["log_file"]))

    if "allowed_clients" in normalized:
        normalized["allowed_clients"] = normalize_allowed_clients(
            normalized["allowed_clients"]
        )

    for key in (
        "public_port",
        "local_port",
        "session_port_start",
        "session_port_end",
    ):
        if key in normalized and normalized[key] is not None:
            normalized[key] = int(normalized[key])

    if "timeout" in normalized and normalized["timeout"] is not None:
        normalized["timeout"] = float(normalized["timeout"])

    if "debug" in normalized and normalized["debug"] is not None:
        normalized["debug"] = bool(normalized["debug"])

    return normalized


def normalize_allowed_clients(value: object) -> tuple[str, ...]:
    """Normalize allowed client entries to a tuple of IP strings."""

    if value in (None, "", []):
        return ()

    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise TypeError("allowed_clients must be a string or list of strings")

    return tuple(str(item).strip() for item in items if str(item).strip())


def validate_config(config: ProxyConfig) -> None:
    """Validate user-facing configuration values."""

    validate_port("public_port", config.public_port)
    validate_port("local_port", config.local_port)
    validate_port("session_port_start", config.session_port_start)
    validate_port("session_port_end", config.session_port_end)

    if config.session_port_start > config.session_port_end:
        raise ValueError("session_port_start must be less than or equal to session_port_end")

    if config.public_port in range(
        config.session_port_start, config.session_port_end + 1
    ):
        raise ValueError("public_port must not be inside the session port range")

    if config.timeout <= 0:
        raise ValueError("timeout must be greater than 0")


def validate_port(name: str, value: int) -> None:
    """Validate a TCP port number."""

    if value < 1 or value > 65535:
        raise ValueError(f"{name} must be between 1 and 65535")


def expand_path(path: str | Path) -> str:
    """Expand environment variables and user home markers in a path."""

    return os.path.abspath(os.path.expanduser(os.path.expandvars(str(path))))
