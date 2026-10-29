"""本地启动：python -m library.api --port 18908"""

from __future__ import annotations

import argparse
from wsgiref.simple_server import make_server

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="校园图书馆借阅服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18908)
    args = parser.parse_args()
    with make_server(args.host, args.port, create_app()) as server:
        print(f"campus-library listening on http://{args.host}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
