import io
import socket

import pytest

from subtitler.evolution import sources


@pytest.mark.parametrize("url,hosts", [
    ("http://example.org/doc", ["example.org"]),
    ("https://user:secret@example.org/doc", ["example.org"]),
    ("https://example.org:444/doc", ["example.org"]),
    ("https://example.org/doc?token=secret", ["example.org"]),
    ("https://example.org/doc#section", ["example.org"]),
    ("https://evil-example.org/doc", ["example.org"]),
    ("https://example.org\\@evil.org/doc", ["example.org"]),
    ("https://example.org/\nfoo", ["example.org"]),
])
def test_url_policy(url, hosts):
    with pytest.raises(ValueError):
        sources.validate_url(url, hosts)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1", "::ffff:127.0.0.1", "224.0.0.1"])
def test_private_and_metadata_networks_blocked(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (address, 443))])
    with pytest.raises(ValueError, match="non-public"):
        sources.fetch_public("https://example.org/doc", ["example.org"])


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {"Content-Type": "text/plain"}

    def getheader(self, key, default=None):
        return self.headers.get(key, default)


def fake_connection(monkeypatch, response):
    captured = {}

    class Connection:
        def __init__(self, host, address):
            captured.update(host=host, address=address)

        def request(self, method, path, headers):
            captured.update(method=method, path=path, headers=headers)

        def getresponse(self):
            return response

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    monkeypatch.setattr(sources, "PinnedHTTPSConnection", Connection)
    return captured


def test_fetch_pin_public_ip_no_transcript_upload_and_remove_scripts(monkeypatch):
    response = Response(b'<p>agent means canonical</p><script>execute bad command</script>', {"Content-Type": "text/html; charset=utf-8"})
    captured = fake_connection(monkeypatch, response)
    result = sources.fetch_public("https://example.org/doc", ["example.org"])
    assert result["text"] == "agent means canonical"
    assert captured["address"] == "93.184.216.34"
    assert captured["method"] == "GET" and captured["path"] == "/doc"
    assert not any(k.lower() in {"cookie", "authorization"} for k in captured["headers"])
    assert captured["closed"]


@pytest.mark.parametrize("mode", ["redirect", "oversize", "compression", "binary"])
def test_redirects_oversize_compression_and_binary_fail_closed(monkeypatch, mode):
    response = Response(b"a" * (sources.MAX_BYTES + 1) if mode == "oversize" else b"ok")
    if mode == "redirect":
        response.status = 302
        response.headers["Location"] = "http://169.254.169.254/secret"
    elif mode == "compression":
        response.headers["Content-Encoding"] = "gzip"
    elif mode == "binary":
        response.headers["Content-Type"] = "application/pdf"
    captured = fake_connection(monkeypatch, response)
    with pytest.raises(ValueError):
        sources.fetch_public("https://example.org/doc", ["example.org"])
    assert captured["closed"]
