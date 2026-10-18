"""Read-only printer discovery through SNMP broadcast and WS-Discovery.

NetViewer discovers devices with SNMP; the MA2000w answers a broadcast GET for
its model OID with ``MA2000w``. WS-Discovery is sent in parallel because other
models may publish a WSD device even when they do not answer broadcast SNMP.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Iterable

from . import snmp

DISCOVERY_ADDRESS = "239.255.255.250"
DISCOVERY_PORT = 3702
SNMP_PORT = 161

MODEL_OID = "1.3.6.1.4.1.1347.43.5.1.1.1.1"
SERIAL_OID = "1.3.6.1.4.1.1347.43.5.1.1.28.1"
FIRMWARE_OID = "1.3.6.1.4.1.1347.43.5.4.1.5.1.1"
IDENTITY_OIDS = (MODEL_OID, SERIAL_OID, FIRMWARE_OID)

WSD_NAMESPACES = (
    'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
    'xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof" '
    'xmlns:print="http://schemas.microsoft.com/windows/2006/08/wdp/print"'
)
WSD_TYPES = ("wsdp:Device", "print:PrintDeviceType")


@dataclass
class DiscoveredPrinter:
    address: str
    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    sources: list[str] = field(default_factory=list)
    endpoint: str | None = None
    xaddrs: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)

    def merge(self, other: "DiscoveredPrinter") -> None:
        for name in ("model", "serial", "firmware", "endpoint"):
            if getattr(self, name) is None:
                setattr(self, name, getattr(other, name))
        for name in ("sources", "xaddrs", "types", "scopes"):
            target = getattr(self, name)
            for value in getattr(other, name):
                if value not in target:
                    target.append(value)

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "model": self.model,
            "serial": self.serial,
            "firmware": self.firmware,
            "sources": self.sources,
            "endpoint": self.endpoint,
            "xaddrs": self.xaddrs,
            "types": self.types,
            "scopes": self.scopes,
        }


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", "replace").replace("\x00", "").strip()
    else:
        text = str(value).strip()
    return text or None


def printer_from_varbinds(
    address: str, varbinds: Iterable[snmp.VarBind], source: str
) -> DiscoveredPrinter | None:
    values = {varbind.oid: _text(varbind.value) for varbind in varbinds}
    model = values.get(MODEL_OID)
    if not model:
        return None
    return DiscoveredPrinter(
        address=address,
        model=model,
        serial=values.get(SERIAL_OID),
        firmware=values.get(FIRMWARE_OID),
        sources=[source],
    )


def arp_candidates(path: str = "/proc/net/arp") -> list[str]:
    """Return IPv4 neighbours that have a resolved hardware address."""
    hosts: list[str] = []
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            next(handle, None)
            for line in handle:
                columns = line.split()
                if len(columns) < 6:
                    continue
                address, flags = columns[0], columns[2]
                try:
                    resolved = int(flags, 16) & 0x2
                except ValueError:
                    continue
                if resolved and address not in hosts:
                    hosts.append(address)
    except OSError:
        return []
    return hosts


def subnet_candidates(cidr: str) -> tuple[list[str], str]:
    """Expand a small IPv4 network into host addresses plus its broadcast."""
    network = ipaddress.ip_network(cidr, strict=False)
    if network.version != 4:
        raise ValueError("discovery subnet must be IPv4")
    if network.num_addresses > 1026:
        raise ValueError("discovery subnet is too large (maximum /22)")
    return [str(host) for host in network.hosts()], str(network.broadcast_address)


def build_wsd_probe(service_type: str) -> bytes:
    message_id = f"urn:uuid:{uuid.uuid4()}"
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope {WSD_NAMESPACES}>
  <soap:Header>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>{message_id}</wsa:MessageID>
  </soap:Header>
  <soap:Body>
    <wsd:Probe><wsd:Types>{service_type}</wsd:Types></wsd:Probe>
  </soap:Body>
</soap:Envelope>
"""
    return body.encode("utf-8")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def summarize_wsd(xml_text: str) -> dict[str, list[str]]:
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
        name = _local_name(element.tag)
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


def wsd_discover(timeout: float) -> list[DiscoveredPrinter]:
    """Send WS-Discovery probes and collect responses until the deadline."""
    found: dict[str, DiscoveredPrinter] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    except OSError:
        return []
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(("", 0))
        sock.settimeout(0.2)
        for service_type in WSD_TYPES:
            sock.sendto(
                build_wsd_probe(service_type),
                (DISCOVERY_ADDRESS, DISCOVERY_PORT),
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            fields = summarize_wsd(data.decode("utf-8", "replace"))
            if not any(fields.values()):
                continue
            address = sender[0]
            printer = DiscoveredPrinter(
                address=address,
                sources=["wsd"],
                endpoint=(fields["endpoint"][0] if fields["endpoint"] else None),
                xaddrs=list(fields["xaddrs"]),
                types=list(fields["types"]),
                scopes=list(fields["scopes"]),
            )
            if address in found:
                found[address].merge(printer)
            else:
                found[address] = printer
    except OSError:
        pass
    finally:
        sock.close()
    return list(found.values())


def probe_snmp_broadcast(
    timeout: float, *, community: str, targets: Iterable[str]
) -> list[DiscoveredPrinter]:
    found: dict[str, DiscoveredPrinter] = {}
    targets = list(targets)
    packet = snmp.build_request(0, community, 0xA0, 1, [MODEL_OID])
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return []
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        sock.settimeout(0.2)
        for attempt in range(3):
            for target in targets:
                sock.sendto(packet, (target, SNMP_PORT))
            if attempt < 2:
                time.sleep(0.2)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                _, error_index, varbinds = snmp.parse_response(data)
            except (snmp.BerError, ValueError):
                continue
            if error_index:
                continue
            printer = printer_from_varbinds(
                sender[0], varbinds, "snmp-broadcast"
            )
            if printer is not None:
                found[printer.address] = printer
    except OSError:
        pass
    finally:
        sock.close()
    return list(found.values())


def probe_snmp_hosts(
    hosts: Iterable[str], *, timeout: float, community: str, workers: int = 32
) -> list[DiscoveredPrinter]:
    addresses = list(dict.fromkeys(hosts))
    if not addresses:
        return []

    def probe(address: str) -> DiscoveredPrinter | None:
        try:
            client = snmp.SnmpClient(
                address,
                community=community,
                version="1",
                timeout=timeout,
                retries=0,
            )
            varbinds = client.get(IDENTITY_OIDS)
        except (OSError, TimeoutError, snmp.BerError, ValueError):
            return None
        return printer_from_varbinds(address, varbinds, "snmp-unicast")

    with ThreadPoolExecutor(max_workers=min(workers, len(addresses))) as pool:
        results = pool.map(probe, addresses)
        return [printer for printer in results if printer is not None]


def _sort_key(printer: DiscoveredPrinter) -> tuple:
    try:
        return tuple(int(part) for part in printer.address.split("."))
    except ValueError:
        return (999,)


def discover(
    *,
    timeout: float = 2.5,
    community: str = "public",
    subnet: str | None = None,
    hosts: Iterable[str] = (),
    use_wsd: bool = True,
    use_arp: bool = True,
) -> list[DiscoveredPrinter]:
    """Discover Kyocera printers without sending write commands."""
    if timeout <= 0:
        raise ValueError("discovery timeout must be positive")
    broadcast_targets = ["255.255.255.255"]
    unicast = {host for host in hosts if host}
    if subnet:
        subnet_hosts, broadcast = subnet_candidates(subnet)
        unicast.update(subnet_hosts)
        broadcast_targets.append(broadcast)
    if use_arp:
        unicast.update(arp_candidates())

    wsd_thread: threading.Thread | None = None
    wsd_results: list[DiscoveredPrinter] = []
    if use_wsd:
        def run_wsd() -> None:
            wsd_results.extend(wsd_discover(timeout))

        wsd_thread = threading.Thread(target=run_wsd, daemon=True)
        wsd_thread.start()

    found: dict[str, DiscoveredPrinter] = {}
    for printer in probe_snmp_broadcast(
        timeout, community=community, targets=broadcast_targets
    ):
        found[printer.address] = printer

    # Broadcast only asks for the model OID; give known responders a longer
    # unicast window to return serial and firmware.
    if found:
        for printer in probe_snmp_hosts(
            found, timeout=max(0.8, min(1.5, timeout)), community=community
        ):
            if printer.address in found:
                found[printer.address].merge(printer)
            else:
                found[printer.address] = printer

    # Explicit, ARP and subnet candidates get a short probe; a live host
    # answers a small GET quickly, and a /24 sweep must stay bounded.
    remaining = unicast - set(found)
    for printer in probe_snmp_hosts(
        remaining, timeout=min(0.6, timeout), community=community
    ):
        if printer.address in found:
            found[printer.address].merge(printer)
        else:
            found[printer.address] = printer

    if wsd_thread is not None:
        wsd_thread.join(timeout + 0.5)
    for printer in wsd_results:
        if printer.address in found:
            found[printer.address].merge(printer)
        else:
            found[printer.address] = printer

    return sorted(found.values(), key=_sort_key)
