"""Restricted HTTPS probe: no credentials, redirects, proxies, or private IPs."""

import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urlsplit

from mimamori.core import Observation


def validate_target(target_id, url):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", target_id):
        raise ValueError("target ID must be 1-40 lowercase letters, digits or hyphens")
    if len(url) > 1024 or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        raise ValueError("URL must use printable ASCII; encode non-ASCII paths")
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.port not in (None, 443)
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or "\\" in url):
        raise ValueError("only HTTPS port 443 URLs without credentials, query or fragment")
    return parts


def public_addresses(host):
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = sorted({record[4][0] for record in records},
                       key=lambda value: (ipaddress.ip_address(value).version, value))
    if not addresses:
        raise socket.gaierror("no DNS answers")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise ValueError("destination must resolve only to public unicast IPs")
        if isinstance(address, ipaddress.IPv6Address) and (
            address.ipv4_mapped or address.sixtofour or address.teredo
        ):
            raise ValueError("transition IPv6 addresses are not allowed")
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout=5):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # The vetted IP is used for the socket; the original host is used for SNI
        # and hostname verification. Never resolve the hostname a second time.
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def probe(target_id, url, slot):
    parts = validate_target(target_id, url)
    observed_at = int(time.time())
    start = time.monotonic()
    connection = None
    status = None
    tls_days = None
    try:
        address = public_addresses(parts.hostname)[0]
        connection = PinnedHTTPSConnection(parts.hostname, address)
        connection.connect()
        cert = connection.sock.getpeercert()
        tls_days = int((ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) // 86400)
        connection.request("GET", parts.path or "/", headers={
            "User-Agent": "MimamoriOps/0.1 (authorized availability monitoring)",
            "Accept": "*/*", "Connection": "close",
        })
        response = connection.getresponse()
        status = response.status
        ok = 200 <= status < 300
        reason = "ok" if ok else ("redirect_not_followed" if 300 <= status < 400 else "http_error")
        # Headers suffice. Do not retain customer content or download a large body.
    except ssl.SSLError:
        ok, reason = False, "tls_error"
    except socket.gaierror:
        ok, reason = False, "dns_error"
    except (TimeoutError, socket.timeout):
        ok, reason = False, "timeout"
    except ValueError:
        ok, reason = False, "blocked_destination"
    except (OSError, http.client.HTTPException):
        ok, reason = False, "connection_error"
    finally:
        if connection:
            connection.close()
    return Observation(target_id, slot, ok, int((time.monotonic() - start) * 1000),
                       reason, status, tls_days, observed_at)
