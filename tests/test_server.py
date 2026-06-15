from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chroma_sdk_lan_proxy.server import extract_session_port, rewrite_init_payload


class ServerTests(unittest.TestCase):
    def test_extracts_session_port_from_uri(self) -> None:
        payload = {
            "sessionid": 62021,
            "uri": "http://localhost:62021/chromasdk",
        }

        self.assertEqual(extract_session_port(payload), 62021)

    def test_extracts_session_port_from_numeric_session_id(self) -> None:
        self.assertEqual(extract_session_port({"sessionid": 62021}), 62021)

    def test_extracts_session_port_from_string_session_id(self) -> None:
        self.assertEqual(extract_session_port({"sessionid": "62021"}), 62021)

    def test_rewrite_init_payload(self) -> None:
        rewritten = rewrite_init_payload(
            {"sessionid": 62021, "uri": "http://localhost:62021/chromasdk"},
            public_port=15436,
            advertise_host="192.168.0.52",
        )

        self.assertEqual(rewritten["sessionid"], 15436)
        self.assertEqual(rewritten["uri"], "http://192.168.0.52:15436/chromasdk")


if __name__ == "__main__":
    unittest.main()
