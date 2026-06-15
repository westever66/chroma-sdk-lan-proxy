"""HTTP proxy server for the Razer Chroma REST SDK."""

from __future__ import annotations

import json
import logging
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from .config import ProxyConfig


LOG = logging.getLogger("chroma-sdk-lan-proxy")
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass
class ProxiedResponse:
    """HTTP response returned by the local SDK."""

    status: int
    reason: str
    headers: dict[str, str]
    body: bytes


class SessionRegistry:
    """Tracks local SDK session ports and their public proxy ports."""

    def __init__(self, config: ProxyConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._local_to_public: dict[int, int] = {}
        self._servers: dict[int, ThreadingHTTPServer] = {}

    def ensure_session_proxy(self, local_port: int) -> int:
        """Create or reuse a public listener for a local Chroma session port."""

        with self._lock:
            if local_port in self._local_to_public:
                return self._local_to_public[local_port]

            for public_port in range(
                self._config.session_port_start, self._config.session_port_end + 1
            ):
                if public_port in self._servers:
                    continue

                server = build_server(
                    SessionHandler,
                    self._config.bind_host,
                    public_port,
                    self._config,
                    self,
                    local_session_port=local_port,
                )
                thread = threading.Thread(
                    target=server.serve_forever,
                    name=f"chroma-session-proxy-{public_port}",
                    daemon=True,
                )
                thread.start()

                self._servers[public_port] = server
                self._local_to_public[local_port] = public_port
                LOG.info(
                    "session proxy listening on %s:%s -> %s:%s",
                    self._config.bind_host,
                    public_port,
                    self._config.local_host,
                    local_port,
                )
                return public_port

        raise RuntimeError("no free public session ports available")

    def snapshot(self) -> dict[str, object]:
        """Return diagnostic session mapping state."""

        with self._lock:
            return {
                "session_count": len(self._local_to_public),
                "sessions": dict(self._local_to_public),
            }


class ProxyHandler(BaseHTTPRequestHandler):
    """Base HTTP proxy handler."""

    config: ClassVar[ProxyConfig]
    registry: ClassVar[SessionRegistry]
    local_session_port: ClassVar[int | None] = None

    server_version = "ChromaSdkLanProxy/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        if not self._client_allowed():
            self._send_forbidden()
            return

        try:
            response = self._forward()
            self._send(response)
        except Exception as exc:
            LOG.exception("proxy request failed: %s", exc)
            body = json.dumps({"result": -1, "error": str(exc)}).encode("utf-8")
            self.send_response(502, "Bad Gateway")
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _client_allowed(self) -> bool:
        allowed = self.config.allowed_clients
        return not allowed or self.client_address[0] in allowed

    def _send_forbidden(self) -> None:
        body = json.dumps({"error": "client is not allowed"}).encode("utf-8")
        self.send_response(403, "Forbidden")
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward(self) -> ProxiedResponse:
        body = self.rfile.read(int(self.headers.get("content-length", "0") or "0"))
        url = self._local_url()
        headers = self._forward_headers()

        request = urllib.request.Request(
            url,
            data=body if body else None,
            headers=headers,
            method=self.command,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as res:
                response_body = res.read()
                return ProxiedResponse(
                    status=res.status,
                    reason=res.reason,
                    headers=dict(res.headers.items()),
                    body=response_body,
                )
        except urllib.error.HTTPError as exc:
            return ProxiedResponse(
                status=exc.code,
                reason=exc.reason,
                headers=dict(exc.headers.items()),
                body=exc.read(),
            )

    def _local_url(self) -> str:
        raise NotImplementedError

    def _forward_headers(self) -> dict[str, str]:
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "host"
        }
        headers["Host"] = "localhost"
        return headers

    def _send(self, response: ProxiedResponse) -> None:
        self.send_response(response.status, response.reason)
        for name, value in response.headers.items():
            if name.lower() not in HOP_BY_HOP_HEADERS:
                self.send_header(name, value)
        self.send_header("content-length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)


class MainHandler(ProxyHandler):
    """Handles the public SDK bootstrap endpoint."""

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._send_health()
            return
        super().do_GET()

    def _local_url(self) -> str:
        return f"http://{self.config.local_host}:{self.config.local_port}{self.path}"

    def _send(self, response: ProxiedResponse) -> None:
        if self.command == "POST" and self.path.rstrip("/") == "/razer/chromasdk":
            response = self._rewrite_init_response(response)
        super()._send(response)

    def _rewrite_init_response(self, response: ProxiedResponse) -> ProxiedResponse:
        if response.status >= 400 or not response.body:
            return response

        try:
            payload = json.loads(response.body.decode("utf-8"))
        except json.JSONDecodeError:
            return response

        local_port = extract_session_port(payload)
        if local_port is None:
            return response

        public_port = self.registry.ensure_session_proxy(local_port)
        payload = rewrite_init_payload(payload, public_port, self._advertise_host())

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = dict(response.headers)
        headers["content-type"] = "application/json"
        return ProxiedResponse(response.status, response.reason, headers, body)

    def _advertise_host(self) -> str:
        if self.config.advertise_host:
            return self.config.advertise_host

        host_header = self.headers.get("host", "")
        if host_header:
            return host_header.rsplit(":", 1)[0]

        return get_lan_ip()

    def _send_health(self) -> None:
        if not self._client_allowed():
            self._send_forbidden()
            return

        local = check_local_sdk(self.config)
        body = json.dumps(
            {
                "ok": local["ok"],
                "local_sdk": local,
                "proxy": {
                    "bind_host": self.config.bind_host,
                    "public_port": self.config.public_port,
                    "session_port_start": self.config.session_port_start,
                    "session_port_end": self.config.session_port_end,
                    **self.registry.snapshot(),
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")

        self.send_response(200 if local["ok"] else 503)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SessionHandler(ProxyHandler):
    """Handles a rewritten Chroma SDK session port."""

    def _local_url(self) -> str:
        if self.local_session_port is None:
            raise RuntimeError("session handler has no local session port")
        return (
            f"http://{self.config.local_host}:{self.local_session_port}"
            f"{self.path}"
        )


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with address reuse enabled."""

    allow_reuse_address = True


def extract_session_port(payload: dict[str, object]) -> int | None:
    """Extract the local SDK session port from an init payload."""

    uri = payload.get("uri")
    if isinstance(uri, str):
        parsed = urllib.parse.urlparse(uri)
        if parsed.port:
            return parsed.port

    sessionid = payload.get("sessionid")
    if isinstance(sessionid, int):
        return sessionid
    if isinstance(sessionid, str) and sessionid.isdigit():
        return int(sessionid)

    return None


def rewrite_init_payload(
    payload: dict[str, object],
    public_port: int,
    advertise_host: str,
) -> dict[str, object]:
    """Rewrite a Chroma SDK init response to point clients at the LAN proxy."""

    rewritten = dict(payload)
    rewritten["sessionid"] = public_port
    rewritten["uri"] = f"http://{advertise_host}:{public_port}/chromasdk"
    return rewritten


def build_server(
    handler_base: type[ProxyHandler],
    bind_host: str,
    port: int,
    config: ProxyConfig,
    registry: SessionRegistry,
    local_session_port: int | None = None,
) -> ThreadingHTTPServer:
    """Build an HTTP server bound to a handler-specific proxy target."""

    class BoundHandler(handler_base):
        pass

    BoundHandler.config = config
    BoundHandler.registry = registry
    BoundHandler.local_session_port = local_session_port

    return ReusableThreadingHTTPServer((bind_host, port), BoundHandler)


def build_main_server(config: ProxyConfig) -> ThreadingHTTPServer:
    """Build the main public proxy server."""

    registry = SessionRegistry(config)
    return build_server(
        MainHandler,
        config.bind_host,
        config.public_port,
        config,
        registry,
    )


def check_local_sdk(config: ProxyConfig) -> dict[str, object]:
    """Check whether the local SDK bootstrap endpoint is reachable."""

    url = f"http://{config.local_host}:{config.local_port}/razer/chromasdk"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=min(config.timeout, 2.0)) as res:
            return {"ok": True, "url": url, "status": res.status}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def get_lan_ip() -> str:
    """Return the best-effort LAN IP address for this machine."""

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return socket.gethostbyname(socket.gethostname())
