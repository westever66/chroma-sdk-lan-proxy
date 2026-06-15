from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chroma_sdk_lan_proxy.config import (
    ProxyConfig,
    build_config,
    normalize_allowed_clients,
)


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid_for_lan_proxy(self) -> None:
        config = build_config()

        self.assertEqual(config.public_port, 15435)
        self.assertEqual(config.local_port, 54235)
        self.assertEqual(config.session_port_start, 15436)
        self.assertEqual(config.session_port_end, 15499)

    def test_config_file_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                '\n'.join(
                    [
                        'bind_host = "192.168.0.52"',
                        "public_port = 15435",
                        "session_port_start = 15436",
                        "session_port_end = 15499",
                    ]
                ),
                encoding="utf-8",
            )

            config = build_config(path, {"public_port": 16435})

        self.assertEqual(config.bind_host, "192.168.0.52")
        self.assertEqual(config.public_port, 16435)

    def test_allowed_clients_accepts_comma_separated_string(self) -> None:
        self.assertEqual(
            normalize_allowed_clients("192.168.0.66, 192.168.0.67"),
            ("192.168.0.66", "192.168.0.67"),
        )

    def test_rejects_public_port_inside_session_range(self) -> None:
        with self.assertRaises(ValueError):
            build_config(
                overrides={
                    "public_port": 15436,
                    "session_port_start": 15436,
                    "session_port_end": 15499,
                }
            )

    def test_json_serialization_includes_allowed_clients_as_list(self) -> None:
        config = ProxyConfig(allowed_clients=("192.168.0.66",))

        self.assertIn('"allowed_clients": [', config.to_json())


if __name__ == "__main__":
    unittest.main()
