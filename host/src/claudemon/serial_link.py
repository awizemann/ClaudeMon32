"""USB serial transport to the ESP32 (newline-delimited JSON protocol).

The firmware prints log lines ([INIT] ..., [BLE RX] ...) on the same port, so
the reader skips any line that doesn't parse as JSON. Never hardcode a port —
the old /dev/cu.usbmodem83201 in platformio.ini is stale.
"""

from __future__ import annotations

import glob
import json
import logging
import time

import serial

log = logging.getLogger(__name__)

BAUD = 115200
PORT_PATTERNS = ("/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/cu.SLAB*", "/dev/cu.wchusbserial*")
RESPONSE_TIMEOUT_S = 3.0
SETTLE_S = 2.0  # firmware setup() delays ~1s after USB-CDC comes up


def candidate_ports() -> list[str]:
    ports: list[str] = []
    for pattern in PORT_PATTERNS:
        ports.extend(sorted(glob.glob(pattern)))
    return ports


class DeviceLink:
    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self.port: str | None = None

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> bool:
        """Find and open the device port; verify with a ping. Returns success."""
        self.close()
        for port in candidate_ports():
            try:
                # Default DTR/RTS-asserted open: the device's USB-CDC gates its
                # TX on DTR, so deasserting it silences all responses. This
                # board does not auto-reset on a normal open.
                s = serial.Serial(port, BAUD, timeout=0.25)
            except (serial.SerialException, OSError) as e:
                log.debug("open %s failed: %s", port, e)
                continue
            time.sleep(SETTLE_S)
            self._serial = s
            self.port = port
            if self._ping():
                log.info("connected to device on %s", port)
                return True
            self.close()
        return False

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except (serial.SerialException, OSError):
                pass
        self._serial = None
        self.port = None

    def _ping(self) -> bool:
        resp = self.send_command({"cmd": "ping"})
        return bool(resp) and resp.get("status") == "ok"

    def send_command(self, command: dict) -> dict | None:
        """Write one JSON command; return the first JSON response line with a
        'status' key, or None on timeout/disconnect."""
        if not self.connected:
            return None
        assert self._serial is not None
        line = json.dumps(command, separators=(",", ":")) + "\n"
        try:
            # Terminate any stale partial line in the device's serial buffer
            # (leftovers from an interrupted prior session corrupt the next
            # command), let the device emit its "invalid JSON" complaint, and
            # discard it before sending the real command.
            self._serial.write(b"\n")
            self._serial.flush()
            time.sleep(0.15)
            self._serial.reset_input_buffer()
            self._serial.write(line.encode())
            self._serial.flush()
        except (serial.SerialException, OSError) as e:
            log.warning("serial write failed: %s", e)
            self.close()
            return None

        deadline = time.monotonic() + RESPONSE_TIMEOUT_S
        buffer = b""
        while time.monotonic() < deadline:
            try:
                chunk = self._serial.read(256)
            except (serial.SerialException, OSError) as e:
                log.warning("serial read failed: %s", e)
                self.close()
                return None
            if chunk:
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
                    if isinstance(obj, dict) and "status" in obj:
                        return obj
        log.warning("no JSON response to %s within %.1fs", command.get("cmd"), RESPONSE_TIMEOUT_S)
        return None
