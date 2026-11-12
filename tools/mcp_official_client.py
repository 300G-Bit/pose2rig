"""Minimal client for Blender 5.2's official MCP extension (TCP 9896).

Protocol: null-byte-delimited JSON, request {"type":"execute","code":...,"strict_json":true}.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys


def call(code: str, host: str = "127.0.0.1", port: int = 9896, timeout: float = 120.0) -> dict:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        request = json.dumps({"type": "execute", "code": code, "strict_json": True}).encode("utf-8") + b"\0"
        sock.sendall(request)
        data = bytearray()
        while b"\0" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data.extend(chunk)
    return json.loads(bytes(data).split(b"\0", 1)[0].decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", default=None)
    parser.add_argument("--file", default=None)
    parser.add_argument("--port", type=int, default=9896)
    args = parser.parse_args()
    code = args.code
    if args.file:
        with open(args.file, "r", encoding="utf-8") as handle:
            code = handle.read()
    if not code:
        print("provide --code or --file", file=sys.stderr)
        return 2
    print(json.dumps(call(code, port=args.port), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
