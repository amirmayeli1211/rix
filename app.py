import argparse
import signal
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import ConfigStore, _Handler

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="RixPanel local MVP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), _Handler)
    httpd.store = ConfigStore(args.data_dir)
    httpd.web_root = ROOT

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    print(f"RixPanel MVP 1.0.0 listening on http://{args.host}:{httpd.server_address[1]}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
