#!/usr/bin/env python3
"""Read-only WS-Discovery probe for WSD printer/scanner services.

The probe sends a standards-based SOAP ``Probe`` message to the WS-Discovery
multicast group and, when a host is supplied, to that host directly. It only
parses the discovery response; it does not call any WSD device operation.

This uses the Python standard library so the experiment is reproducible on a
fresh Linux system.
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time
import uuid
import xml.etree.ElementTree as ET

DISCOVERY_ADDRESS = "239.255.255.250"
DISCOVERY_PORT = 3702

PROBE_TYPES = {
    "device": "wsdp:Device",
    "printer": "print:PrintDeviceType",
    "scanner": "scan:ScannerServiceType",
}

NAMESPACES = (
    'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
    'xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof" '
    'xmlns:print="http://schemas.microsoft.com/windows/2006/08/wdp/print" '
    'xmlns:scan="http://schemas.microsoft.com/windows/2006/08/wdp/scan"'
)


def build_probe(service_type: str) -> bytes:
    message_id = f"urn:uuid:{uuid.uuid4()}"
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope {NAMESPACES}>
  <soap:Header>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>{message_id}</wsa:MessageID>
  </soap:Header>
  <soap:Body>
    <wsd:Probe>
      <wsd:Types>{service_type}</wsd:Types>
    </wsd:Probe>
  </soap:Body>
</soap:Envelope>
"""
    return body.encode("utf-8")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def summarize(xml_text: str) -> dict[str, list[str]]:
    """Extract the discovery fields worth recording for later analysis."""
    fields: dict[str, list[str]] = {
        "endpoint": [],
        "types": [],
        "scopes": [],
        "xaddrs": [],
    }
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return fields
    for element in root.iter():
        name = local_name(element.tag)
        text = (element.text or "").strip()
        if not text:
            continue
        if name in ("Address", "EndpointReference"):
            key = "endpoint"
        elif name == "Types":
            key = "types"
        elif name == "Scopes":
            key = "scopes"
        elif name == "XAddrs":
            key = "xaddrs"
        else:
            continue
        if text not in fields[key]:
            fields[key].append(text)
    return fields


def probe(host: str | None, service_type: str, timeout: float) -> int:
    packet = build_probe(service_type)
    targets = [(DISCOVERY_ADDRESS, DISCOVERY_PORT)]
    if host:
        targets.append((host, DISCOVERY_PORT))

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(("", 0))
        sock.settimeout(0.5)
        for address, port in targets:
            sock.sendto(packet, (address, port))

        deadline = time.monotonic() + timeout
        seen: set[str] = set()
        responses = 0
        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(65535)
            except socket.timeout:
                continue
            text = data.decode("utf-8", "replace")
            if text in seen:
                continue
            seen.add(text)
            responses += 1
            fields = summarize(text)
            print(f"--- response {responses} from {sender[0]}:{sender[1]} ---")
            for key in ("endpoint", "types", "scopes", "xaddrs"):
                for value in fields[key]:
                    print(f"{key}: {value}")
            print(re.sub(r"\s+", " ", text).strip())
            print()

    if not responses:
        print("no WS-Discovery response", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="also send a unicast probe to this host")
    parser.add_argument(
        "--type",
        choices=tuple(PROBE_TYPES),
        default="scanner",
        help="service type to probe for (default: scanner)",
    )
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()
    return probe(args.host, PROBE_TYPES[args.type], args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
