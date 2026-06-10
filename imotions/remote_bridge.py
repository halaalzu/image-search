import io
import os
import socket
import time

class ImotionsBridge:
    """Lightweight iMotions remote-control bridge for MATB lifecycle events."""

    def __init__(self):
        self.enabled = os.getenv("IMOTIONS_BRIDGE_ENABLED", "1").strip().lower() not in ("0", "false", "no")
        self.host = os.getenv("IMOTIONS_HOST", "127.0.0.1")
        self.port = int(os.getenv("IMOTIONS_PORT", "8087"))
        self.connect_timeout = float(os.getenv("IMOTIONS_CONNECT_TIMEOUT", "0.25"))
        self._socket = None
        self._stream = None
        self._last_connect_attempt = 0.0
        self._min_reconnect_interval_sec = 2.0
        self._cmd_id = 1

    def _next_command_id(self) -> str:
        cmd_id = f"{self._cmd_id:07d}"
        self._cmd_id += 1
        if self._cmd_id > 9_999_999:
            self._cmd_id = 1
        return cmd_id

    def _send(self, msg: list[str]):
        if not self.enabled:
            return None
        if not self._ensure_connected():
            return None

        try:
            self._socket.sendall(f"{';'.join(msg)}\r\n".encode("utf-8"))
            raw_line = self._stream.readline()
            if raw_line == "":
                self.close()
                return None
            line = raw_line.rstrip("\n").split(";")
            if len(line) >= 8 and line[6] == "0":
                # Command rejected by iMotions: keep bridge alive, just report.
                print(f"[iMotions bridge] Command failed: {line[7]}")
            return line
        except (OSError, TimeoutError):
            self.close()
            return None

    def send_command(self, command: str, *params: str):
        # Remote control format: R;version;id;command;...
        msg = ["R", "1", self._next_command_id(), command]
        msg.extend(str(p) for p in params)
        return self._send(msg)

    def _ensure_connected(self):
        if self._socket is not None and self._stream is not None:
            return True

        now = time.time()
        if now - self._last_connect_attempt < self._min_reconnect_interval_sec:
            return False
        self._last_connect_attempt = now

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            sock.connect((self.host, self.port))
            self._socket = sock
            self._stream = sock.makefile(mode="r", encoding="utf-8")
            print(f"[iMotions bridge] Connected to {self.host}:{self.port}")
            return True
        except (OSError, TimeoutError):
            self.close()
            return False

    def next_stimulus(self):
        return self.send_command("SLIDESHOWNEXT")

    def on_task_start(self):
        # Move iMotions from "Press SPACE to continue" to actual stimulus at task start.
        self.next_stimulus()

    def on_task_end(self):
        # Advance iMotions when MATB reaches end-of-task summary.
        self.next_stimulus()

    def on_quit(self):
        # "Q to quit" in MATB should stop bridge traffic, not shutdown iMotions.
        self.close()

    def close(self):
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
        self._stream = None
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
