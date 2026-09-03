#!/usr/bin/env python3
"""Outbound-network helper for containers that run in an isolated network namespace.

Rootless apptainer can give a container its own netns (`--net --network none`, loopback only), which
restores Docker's port isolation, but attaching slirp4netns/pasta needs /dev/net/tun, which AppArmor
denies here. Filesystem unix sockets cross network namespaces, so instead:

  host side   (`pbproxy.py serve <sock>`)  — an HTTP proxy (GET/POST forwarding + CONNECT tunnelling)
                                            listening on a unix socket, run once per Slurm job.
  container   (`pbproxy.py relay <sock> <port>`) — listens on 127.0.0.1:<port> inside the netns and
                                            pipes each TCP connection to the unix socket.

The shim exports HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:<port> in the container, so pip, apt, curl,
git, cargo, go and reqwest/requests-based test code reach the internet; raw sockets/DNS to the
outside do not (they would not in a hermetic CI either).
"""

import socket
import socketserver
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit


def pump(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def bridge(a: socket.socket, b: socket.socket) -> None:
    t = threading.Thread(target=pump, args=(b, a), daemon=True)
    t.start()
    pump(a, b)
    t.join()


def read_head(conn: socket.socket) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = conn.recv(65536)
        if not chunk:
            return buf
        buf += chunk
    return buf


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        head = read_head(self.request)
        if not head:
            return
        line, _, rest = head.partition(b"\r\n")
        method, target, version = line.decode("latin1").split(" ", 2)
        try:
            if method == "CONNECT":
                host, port = target.rsplit(":", 1)
                upstream = socket.create_connection((host, int(port)), timeout=30)
                self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                # bytes after the header block belong to the tunnel (TLS client hello)
                if (tail := head.split(b"\r\n\r\n", 1)[1]):
                    upstream.sendall(tail)
            else:  # absolute-URI plain HTTP request: rewrite to origin form and forward
                u = urlsplit(target)
                upstream = socket.create_connection((u.hostname, u.port or 80), timeout=30)
                path = (u.path or "/") + (f"?{u.query}" if u.query else "")
                upstream.sendall(f"{method} {path} {version}\r\n".encode("latin1") + rest)
        except OSError as e:
            self.request.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}\r\n".encode())
            return
        upstream.settimeout(None)
        bridge(self.request, upstream)


class RelayHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        up = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        up.connect(self.server.sock_path)  # type: ignore[attr-defined]
        bridge(self.request, up)


class Threaded(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class ThreadedUnix(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main() -> None:
    mode, sock_path = sys.argv[1], sys.argv[2]
    if mode == "serve":
        Path(sock_path).unlink(missing_ok=True)
        srv = ThreadedUnix(sock_path, ProxyHandler)
        Path(sock_path).chmod(0o666)
    else:
        srv = Threaded(("127.0.0.1", int(sys.argv[3])), RelayHandler)
        srv.sock_path = sock_path  # type: ignore[attr-defined]
    srv.serve_forever()


if __name__ == "__main__":
    main()
