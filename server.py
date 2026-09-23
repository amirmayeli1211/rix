from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config_builder import generate_artifacts

MAX_BODY_BYTES = 64 * 1024


class ConfigStore:
    def __init__(self, storage_dir: Path):
        self.path = storage_dir / "configs.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            document = json.loads(self.path.read_text("utf-8"))
            return document.get("configs", [])

    def add(self, config: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            configs = self.list()
            configs.append(config)
            self._write(configs)
            return config

    def get(self, config_id: str):
        return next((item for item in self.list() if item["id"] == config_id), None)

    def delete(self, config_id: str) -> bool:
        with self._lock:
            configs = self.list()
            remaining = [item for item in configs if item["id"] != config_id]
            if len(remaining) == len(configs):
                return False
            self._write(remaining)
            return True

    def _write(self, configs: list[dict[str, Any]]):
        temporary = self.path.with_suffix(".json.tmp")
        document = {"version": 1, "configs": configs}
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            "utf-8",
        )
        temporary.replace(self.path)


class _Handler(BaseHTTPRequestHandler):
    server_version = "RixPanel/1"

    def do_GET(self):
        if self.path == "/api/health":
            self._json(200, {"service": "rixpanel", "status": "ok", "version": 1})
            return
        elif self.path == "/api/v1/configs":
            configs = self.server.store.list()
            self._json(200, {"version": 1, "configs": configs})
            return
        elif self.path.startswith("/api/v1/subscriptions/"):
            config_id = self.path.removeprefix("/api/v1/subscriptions/")
            config = self.server.store.get(config_id) if config_id else None
            if config is None:
                self._json(404, {"error": "not_found", "message": "اشتراک پیدا نشد"})
                return
            body = config["subscription_base64"].encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", 'attachment; filename="rixpanel-subscription.txt"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        elif self.path.startswith("/api/v1/configs/"):
            config_id = self.path.removeprefix("/api/v1/configs/")
            config = self.server.store.get(config_id) if config_id else None
            if config is None:
                self._json(404, {"error": "not_found", "message": "کانفیگ پیدا نشد"})
                return
            else:
                self._json(200, config)
            return
        if self.path.startswith("/api/"):
            self._json(404, {"error": "not_found", "message": "مسیر پیدا نشد"})
            return
        if self.path == "/":
            relative = "index.html"
        else:
            relative = self.path.lstrip("/")
        try:
            file_path = self.server.web_root / relative
            file_path = file_path.resolve()
            file_path.relative_to(self.server.web_root.resolve())
        except (ValueError, OSError):
            self._json(404, {"error": "not_found", "message": "فایل پیدا نشد"})
            return
        if not file_path.is_file():
            self._json(404, {"error": "not_found", "message": "فایل پیدا نشد"})
            return
        content_types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(file_path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/v1/configs/generate":
            self._json(404, {"error": "not_found", "message": "مسیر پیدا نشد"})
            return
        try:
            payload = self._read_json_body()
            if not payload.get("domain") and not payload.get("server"):
                forwarded_host = self.headers.get("X-Forwarded-Host", "").split(",", 1)[0].strip()
                host = forwarded_host or self.headers.get("Host", "").split(":", 1)[0].strip()
                if host:
                    payload["domain"] = host
            artifacts = generate_artifacts(payload)
        except ValueError as exc:
            self._json(422, {"error": "validation_error", "message": str(exc)})
            return
        record = {
            "id": str(uuid.uuid4()),
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **artifacts,
        }
        self.server.store.add(record)
        self._json(201, record)

    def do_DELETE(self):
        prefix = "/api/v1/configs/"
        if not self.path.startswith(prefix):
            self._json(404, {"error": "not_found", "message": "مسیر پیدا نشد"})
            return
        config_id = self.path.removeprefix(prefix)
        if not self.server.store.delete(config_id):
            self._json(404, {"error": "not_found", "message": "کانفیگ پیدا نشد"})
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("Content-Type باید application/json باشد")
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else 0
        except ValueError as exc:
            raise ValueError("Content-Length معتبر نیست") from exc
        if length <= 0:
            raise ValueError("بدنه درخواست خالی است")
        if length > MAX_BODY_BYTES:
            raise ValueError("بدنه درخواست نباید بیشتر از ۶۴ کیلوبایت باشد")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("بدنه درخواست JSON معتبر نیست") from exc
        if not isinstance(payload, dict):
            raise ValueError("بدنه درخواست باید JSON object باشد")
        return payload

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


class RixPanelServer:
    def __init__(self, storage_dir):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.store = ConfigStore(Path(storage_dir))
        self._server.web_root = Path(__file__).resolve().parent
        self._thread = None

    @property
    def base_url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def storage_dir(self):
        return self._server.store.path.parent

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=3)
