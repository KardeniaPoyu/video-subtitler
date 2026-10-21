"""Bounded, public HTTPS evidence snapshots; no browser cookies or transcript uploads."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import os
import socket
import ssl
import stat
import time
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

MAX_BYTES = 1_048_576


def read_local(path):
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise ValueError("knowledge input must be a regular file, not a symlink/device")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("knowledge input is not a regular file")
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("knowledge input exceeds 1 MiB")
    return raw.decode("utf-8-sig")


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def public_address(address):
    ip = ipaddress.ip_address(address)
    return ip.is_global and not (ip.is_multicast or ip.is_unspecified or ip.is_reserved)


def validate_url(url, allowed_hosts):
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
        raise ValueError("invalid evidence URL")
    parts = urlsplit(url)
    host = parts.hostname
    if (parts.scheme != "https" or not host or parts.port not in (None, 443)
            or parts.username is not None or parts.password is not None or parts.fragment or parts.query):
        raise ValueError("evidence needs public HTTPS without credentials, query, fragment or custom port")
    host = host.encode("idna").decode("ascii").lower()
    allowed = {h.encode("idna").decode("ascii").lower() for h in allowed_hosts}
    if host not in allowed:
        raise ValueError("host is not explicitly allowed (exact hostname required)")
    return parts, host


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout=10):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the validated numeric IP; SNI/certificate verification still use hostname.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch_public(url, allowed_hosts):
    parts, host = validate_url(url, allowed_hosts)
    addresses = sorted({x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)},
                       key=lambda address: (ipaddress.ip_address(address).version, address))
    if not addresses or not all(public_address(a) for a in addresses):
        raise ValueError("DNS resolved to a non-public address")
    connection = PinnedHTTPSConnection(host, addresses[0])
    start = time.monotonic()
    try:
        connection.request("GET", quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~"), headers={
            "User-Agent": "video-subtitler-evidence/0.5", "Accept": "text/plain,text/html,application/json",
            "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"evidence HTTP {response.status}; redirects are not followed")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("compressed evidence responses are unsupported")
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].lower()
        if content_type not in {"application/json", "text/plain", "text/html", "text/markdown"}:
            raise ValueError("only UTF-8 text, HTML, Markdown and JSON evidence is supported")
        chunks, size = [], 0
        while True:
            if time.monotonic() - start > 20:
                raise TimeoutError("evidence download exceeded 20 seconds")
            block = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not block:
                break
            chunks.append(block)
            size += len(block)
            if size > MAX_BYTES:
                raise ValueError("evidence exceeds 1 MiB")
        if getattr(response, "length", None) not in (None, 0):
            raise ValueError("incomplete evidence response; Content-Length was not satisfied")
        if time.monotonic() - start > 20:
            raise TimeoutError("evidence download exceeded 20 seconds")
        raw = b"".join(chunks)
    except http.client.HTTPException as exc:
        raise ValueError(f"invalid evidence HTTP response: {exc}") from exc
    finally:
        connection.close()
    text = raw.decode("utf-8-sig")
    if content_type == "text/html":
        parser = VisibleText()
        parser.feed(text)
        text = "\n".join(parser.parts)
    if not text.strip():
        raise ValueError("evidence has no readable text")
    return {"text": text, "url": url, "raw_sha256": hashlib.sha256(raw).hexdigest(), "content_type": content_type}
