import base64
import json
import re
import uuid
from typing import Any
from urllib.parse import quote, urlencode

HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$")
PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")


def _clean(value: Any, field: str, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field} باید رشته باشد")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field} الزامی است")
    return value


def _validate_host(value: Any, field: str) -> str:
    value = _clean(value, field)
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError(f"{field} معتبر نیست")
    try:
        import ipaddress
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if not HOST_RE.fullmatch(value):
        raise ValueError(f"{field} معتبر نیست")
    return value


def generate_artifacts(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("بدنه درخواست باید JSON object باشد")

    name = _clean(raw.get("name") or "RixPanel Config", "name")
    remark = _clean(raw.get("remark"), "remark", required=False)

    domain = raw.get("domain")
    server_value = raw.get("server") or domain
    if not server_value:
        raise ValueError("domain یا server الزامی است")
    server = _validate_host(server_value, "domain" if domain and not raw.get("server") else "server")

    raw_port = raw.get("port", 443)
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("port باید عدد باشد") from exc
    if not 1 <= port <= 65535:
        raise ValueError("port باید بین 1 و 65535 باشد")

    user_uuid = raw.get("uuid") or str(uuid.uuid4())
    if not isinstance(user_uuid, str):
        raise ValueError("uuid باید رشته باشد")
    try:
        user_uuid = str(uuid.UUID(user_uuid))
    except (ValueError, AttributeError) as exc:
        raise ValueError("uuid معتبر نیست") from exc

    sni = _validate_host(raw.get("sni") or server, "sni")
    host = _validate_host(raw.get("host") or server, "host")
    path = _clean(raw.get("path") or "/rix-ws", "path")
    if not PATH_RE.fullmatch(path) or "#" in path or "?" in path:
        raise ValueError("path معتبر نیست")

    tls = raw.get("tls", True)
    if not isinstance(tls, bool):
        raise ValueError("tls باید true یا false باشد")
    allow_insecure = raw.get("allow_insecure", 0)
    if allow_insecure not in (0, False, "0"):
        raise ValueError("allow_insecure در نسخه ۱ فقط ۰ است")

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"udp": True},
                "tag": "socks-in",
            },
            {
                "listen": "127.0.0.1",
                "port": 10809,
                "protocol": "http",
                "tag": "http-in",
            },
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": server,
                            "port": port,
                            "users": [{"id": user_uuid, "encryption": "none", "level": 0}],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls" if tls else "none",
                    "tlsSettings": {"serverName": sni, "allowInsecure": False},
                    "wsSettings": {"path": path, "headers": {"Host": host}},
                },
            }
        ],
    }
    if not tls:
        config["outbounds"][0]["streamSettings"].pop("tlsSettings")

    query = urlencode(
        [
            ("encryption", "none"),
            ("security", "tls" if tls else "none"),
            ("type", "ws"),
            ("host", host),
            ("path", path),
            ("sni", sni),
            ("allowInsecure", "0"),
        ]
    )
    vless_uri = f"vless://{user_uuid}@{server}:{port}?{query}#{quote(name)}"
    subscription = base64.b64encode((vless_uri + "\n").encode("utf-8")).decode("ascii")
    return {
        "name": name,
        "server": server,
        "port": port,
        "uuid": user_uuid,
        "sni": sni,
        "host": host,
        "path": path,
        "tls": tls,
        "allow_insecure": 0,
        "remark": remark,
        "config": config,
        "vless_uri": vless_uri,
        "subscription_base64": subscription,
        "subscription_json": {
            "version": 1,
            "configs": [
                {
                    "name": name,
                    "remark": remark,
                    "config": config,
                    "vless_uri": vless_uri,
                }
            ],
        },
    }
