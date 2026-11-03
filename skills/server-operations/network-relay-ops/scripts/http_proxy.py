#!/usr/bin/env python3
"""CONNECT proxy for mainland->overseas relay (e.g. let a mainland box reach
api.openai.com via a Singapore box that has direct access).

Usage: python3 http_proxy.py [PORT]   # default 3128
Supports HTTP CONNECT (HTTPS tunnels) only; plain HTTP requests get 405.
Access-restrict via UFW to the calling box's public IPs (open proxy = abuse
magnet). Test from the calling box:
  curl -x http://<singapore-ip>:3128 -o /dev/null -w '%{http_code}' https://api.openai.com/v1/models
  # 401 = tunnel works (401 is OpenAI's unauth response, means you reached it)
Then set HTTPS_PROXY=http://<singapore-ip>:3128 for codex/claude on the calling box.
"""
import socket
import threading
import sys

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3128


def forward(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def handle(client):
    try:
        request = b""
        while b"\r\n" not in request:
            chunk = client.recv(4096)
            if not chunk:
                break
            request += chunk
        if not request:
            client.close()
            return
        line = request.split(b"\r\n")[0]
        parts = line.split()
        if len(parts) < 3 or parts[0].upper() != b"CONNECT":
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            client.close()
            return
        hostport = parts[1].decode().split(":")
        host, port = hostport[0], int(hostport[1]) if len(hostport) > 1 else 443
        upstream = socket.create_connection((host, port), timeout=15)
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        t1 = threading.Thread(target=forward, args=(client, upstream), daemon=True)
        t2 = threading.Thread(target=forward, args=(upstream, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(64)
    print(f"CONNECT proxy listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
