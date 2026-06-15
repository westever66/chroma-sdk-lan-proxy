"""Command-line interface for the Chroma SDK LAN proxy."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ProxyConfig, build_config
from .server import LOG, build_main_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Expose the local Razer Chroma REST SDK to LAN clients."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a TOML config file. CLI options override file values.",
    )
    parser.add_argument("--bind-host", default=None)
    parser.add_argument("--advertise-host", default=None)
    parser.add_argument("--public-port", type=int, default=None)
    parser.add_argument("--local-host", default=None)
    parser.add_argument("--local-port", type=int, default=None)
    parser.add_argument("--session-port-start", type=int, default=None)
    parser.add_argument("--session-port-end", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument(
        "--allowed-clients",
        default=None,
        help="Comma-separated client IP allowlist. Empty means allow all clients.",
    )
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable debug logging.",
    )
    parser.add_argument("--log-file", default=None)
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the effective config and exit.",
    )
    return parser.parse_args(argv)


def build_cli_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Convert argparse values into config overrides."""

    return {
        "bind_host": args.bind_host,
        "advertise_host": args.advertise_host,
        "public_port": args.public_port,
        "local_host": args.local_host,
        "local_port": args.local_port,
        "session_port_start": args.session_port_start,
        "session_port_end": args.session_port_end,
        "timeout": args.timeout,
        "debug": args.debug,
        "log_file": args.log_file,
        "allowed_clients": args.allowed_clients,
    }


def setup_logging(config: ProxyConfig) -> None:
    """Configure console and optional rotating file logging."""

    level = logging.DEBUG if config.debug else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if config.log_file:
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_path,
                maxBytes=1_000_000,
                backupCount=5,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def run(config: ProxyConfig) -> int:
    """Run the proxy server until interrupted."""

    setup_logging(config)
    LOG.info("effective config: %s", config.to_json().replace("\n", " "))

    try:
        server = build_main_server(config)
    except OSError as exc:
        LOG.error(
            "failed to bind %s:%s: %s",
            config.bind_host,
            config.public_port,
            exc,
        )
        return 1

    LOG.info(
        "main proxy listening on %s:%s -> %s:%s",
        config.bind_host,
        config.public_port,
        config.local_host,
        config.local_port,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("stopping proxy")
    finally:
        server.server_close()

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)

    try:
        config = build_config(args.config, build_cli_overrides(args))
    except Exception as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if args.print_config:
        print(config.to_json())
        return 0

    return run(config)
