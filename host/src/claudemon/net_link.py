"""TCP transport to the device — the WiFi counterpart to serial_link.DeviceLink.

Speaks the exact same newline-delimited JSON protocol as the serial link (the
firmware dispatches both through the same handler), so this class mirrors
DeviceLink's interface — `connected` / `connect` / `close` / `send_command` /
`port` — and the daemon can drive either transport interchangeably.

Discovery is by mDNS: the device advertises `claudemon.local`, which macOS
resolves via Bonjour, so the default host just works on a home LAN. An explicit
host/IP can be passed when mDNS isn't available.
"""

from __future__ import annotations

import json
import logging
import socket
import time

log = logging.getLogger(__name__)

DEFAULT_HOST = "claudemon.local"
DEFAULT_PORT = 8781
RESPONSE_TIMEOUT_S = 3.0


class NetworkLink:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self.port = f"{host}:{port}"   # display name, mirrors DeviceLink.port

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> bool:
        """Open the TCP connection and verify with a ping. Returns success."""
        self.close()
        try:
            s = socket.create_connection((self._host, self._port), timeout=RESPONSE_TIMEOUT_S)
        except OSError as e:
            log.debug("tcp connect %s failed: %s", self.port, e)
            return False
        s.settimeout(RESPONSE_TIMEOUT_S)
        self._sock = s
        if self._ping():
            log.info("connected to device at %s", self.port)
            return True
        self.close()
        return False

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def _ping(self) -> bool:
        resp = self.send_command({"cmd": "ping"})
        return bool(resp) and resp.get("status") == "ok"

    def send_command(self, command: dict) -> dict | None:
        """Write one JSON command; return the matching JSON response, or None on
        timeout/disconnect. Matches the reply by echoed `cmd` (ping -> pong),
        exactly like the serial link, so a stale line can't be misattributed."""
        if self._sock is None:
            return None
        expected_cmd = "pong" if command.get("cmd") == "ping" else command.get("cmd")
        line = json.dumps(command, separators=(",", ":")) + "\n"
        try:
            self._sock.sendall(line.encode())
        except OSError as e:
            log.warning("tcp write failed: %s", e)
            self.close()
            return None

        deadline = time.monotonic() + RESPONSE_TIMEOUT_S
        buffer = b""
        unmatched_error: dict | None = None
        while time.monotonic() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                break
            except OSError as e:
                log.warning("tcp read failed: %s", e)
                self.close()
                return None
            if not chunk:                # peer closed the connection
                self.close()
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                text = raw.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    log.debug("skipping non-JSON line: %s", text[:120])
                    continue
                if not (isinstance(obj, dict) and "status" in obj):
                    continue
                if obj.get("cmd") == expected_cmd:
                    return obj
                if "cmd" not in obj:
                    unmatched_error = obj
        if unmatched_error is not None:
            return unmatched_error
        log.warning("no JSON response to %s within %.1fs", command.get("cmd"), RESPONSE_TIMEOUT_S)
        return None
