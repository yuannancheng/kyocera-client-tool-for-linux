"""Read-only KM-WSDL scan service probe.

The Kyocera network TWAIN driver first calls KM-WSDL
``get_service_information`` before it requests scanner capabilities or starts a
scan. This module implements those two read-only discovery calls.
"""

from __future__ import annotations

import argparse
import http.client
import json
import ssl
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

SCAN_PATH = "/ws/km-wsdl/job/scan_operation"
SCAN_NAMESPACE = (
    "http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation"
)
GET_SERVICE_INFORMATION_ACTION = f"{SCAN_NAMESPACE}/get_service_information"
GET_CAPABILITY_ACTION = f"{SCAN_NAMESPACE}/get_capability"

_READ_ONLY_OPERATIONS = {
    "get_service_information",
    "get_capability",
}

CAPABILITY_ENTRY_NAMES = (
    "scan_image_configuration_capability",
    "original_configuration_capability",
    "output_image_configuration_capability",
)

_ENVELOPES = {
    "1.1": (
        "http://schemas.xmlsoap.org/soap/envelope/",
        "http://schemas.xmlsoap.org/soap/encoding/",
    ),
    "1.2": (
        "http://www.w3.org/2003/05/soap-envelope",
        "http://www.w3.org/2003/05/soap-encoding",
    ),
}


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    endpoint: str
    http_status: int
    soap_version: str
    result: str | None
    version: str | None
    release_date: str | None
    model_name: str | None
    fault_code: str | None
    fault_reason: str | None
    raw: str | None = None


@dataclass(frozen=True)
class XmlNode:
    """Namespace-neutral XML value that preserves unknown nested fields."""

    name: str
    attributes: dict[str, str]
    text: str | None
    children: tuple["XmlNode", ...]


@dataclass(frozen=True)
class CapabilityResult:
    ok: bool
    endpoint: str
    http_status: int
    soap_version: str
    result: str | None
    capabilities: dict[str, XmlNode | None]
    missing_capabilities: tuple[str, ...]
    fault_code: str | None
    fault_reason: str | None
    raw: str | None = None


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    endpoint: str
    soap_version: str
    service_information: ProbeResult | None
    capability: CapabilityResult | None
    failed_stage: str | None
    error: str | None


def build_operation_request(
    operation: str, soap_version: str = "1.1"
) -> tuple[bytes, dict[str, str]]:
    """Build one of the driver's read-only scan-operation requests."""
    if operation not in _READ_ONLY_OPERATIONS:
        raise ValueError(f"unsupported read-only operation: {operation}")
    try:
        envelope_ns, encoding_ns = _ENVELOPES[soap_version]
    except KeyError as error:
        raise ValueError(f"unsupported SOAP version: {soap_version}") from error

    action = f"{SCAN_NAMESPACE}/{operation}"
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="{envelope_ns}"
 xmlns:SOAP-ENC="{encoding_ns}"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
 xmlns:kmscn="{SCAN_NAMESPACE}">
 <SOAP-ENV:Body>
  <kmscn:{operation}Request/>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""
    headers = {"User-Agent": "gSOAP/2.7"}
    if soap_version == "1.1":
        headers["Content-Type"] = "text/xml; charset=utf-8"
        headers["SOAPAction"] = f'"{action}"'
    else:
        headers["Content-Type"] = (
            "application/soap+xml; charset=utf-8; "
            f'action="{action}"'
        )
    return body.encode("utf-8"), headers


def build_request(soap_version: str = "1.1") -> tuple[bytes, dict[str, str]]:
    """Build the original driver's empty get_service_information request."""
    return build_operation_request("get_service_information", soap_version)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(root: ET.Element, local_name: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) != local_name:
            continue
        text = (element.text or "").strip()
        if text:
            return text
    return None


def _parse_xml(text: str) -> ET.Element:
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise ET.ParseError("DTD and entity declarations are not accepted")
    return ET.fromstring(text)


def _fault_fields(root: ET.Element) -> tuple[str | None, str | None]:
    fault = next(
        (element for element in root.iter() if _local_name(element.tag) == "Fault"),
        None,
    )
    if fault is None:
        return None, None
    code = _first_text(fault, "Value") or _first_text(fault, "faultcode")
    reason = _first_text(fault, "Text") or _first_text(fault, "faultstring")
    return code, reason


def _xml_node(element: ET.Element) -> XmlNode:
    text = (element.text or "").strip()
    return XmlNode(
        name=_local_name(element.tag),
        attributes=dict(element.attrib),
        text=text or None,
        children=tuple(_xml_node(child) for child in element),
    )


def parse_response(
    body: bytes,
    *,
    endpoint: str,
    http_status: int,
    soap_version: str,
    include_raw: bool = False,
) -> ProbeResult:
    """Parse a KM-WSDL response without treating XML alone as success."""
    text = body.decode("utf-8", "replace")
    try:
        root = _parse_xml(text)
    except ET.ParseError:
        return ProbeResult(
            ok=False,
            endpoint=endpoint,
            http_status=http_status,
            soap_version=soap_version,
            result=None,
            version=None,
            release_date=None,
            model_name=None,
            fault_code="invalid_xml",
            fault_reason="response is not well-formed XML",
            raw=text if include_raw else None,
        )

    fault_code, fault_reason = _fault_fields(root)

    result = _first_text(root, "result")
    version = _first_text(root, "version")
    release_date = _first_text(root, "release_date")
    model_name = _first_text(root, "model_name")
    http_ok = 200 <= http_status < 300
    result_ok = result is None or result == "0"
    return ProbeResult(
        ok=http_ok and fault_code is None and fault_reason is None and result_ok,
        endpoint=endpoint,
        http_status=http_status,
        soap_version=soap_version,
        result=result,
        version=version,
        release_date=release_date,
        model_name=model_name,
        fault_code=fault_code,
        fault_reason=fault_reason,
        raw=text if include_raw else None,
    )


def parse_capability_response(
    body: bytes,
    *,
    endpoint: str,
    http_status: int,
    soap_version: str,
    include_raw: bool = False,
) -> CapabilityResult:
    """Parse capability entries while retaining their nested XML structure."""
    text = body.decode("utf-8", "replace")
    empty_capabilities = {name: None for name in CAPABILITY_ENTRY_NAMES}
    try:
        root = _parse_xml(text)
    except ET.ParseError:
        return CapabilityResult(
            ok=False,
            endpoint=endpoint,
            http_status=http_status,
            soap_version=soap_version,
            result=None,
            capabilities=empty_capabilities,
            missing_capabilities=CAPABILITY_ENTRY_NAMES,
            fault_code="invalid_xml",
            fault_reason="response is not well-formed XML",
            raw=text if include_raw else None,
        )

    fault_code, fault_reason = _fault_fields(root)
    result = _first_text(root, "result")
    response = next(
        (
            element
            for element in root.iter()
            if _local_name(element.tag) == "get_capabilityResponse"
        ),
        root,
    )
    direct_children = {
        _local_name(child.tag): child for child in response
    }
    capabilities = {
        name: (
            _xml_node(direct_children[name])
            if name in direct_children
            else None
        )
        for name in CAPABILITY_ENTRY_NAMES
    }
    missing = tuple(name for name, value in capabilities.items() if value is None)
    http_ok = 200 <= http_status < 300
    return CapabilityResult(
        ok=(
            http_ok
            and fault_code is None
            and fault_reason is None
            and result == "0"
            and not missing
        ),
        endpoint=endpoint,
        http_status=http_status,
        soap_version=soap_version,
        result=result,
        capabilities=capabilities,
        missing_capabilities=missing,
        fault_code=fault_code,
        fault_reason=fault_reason,
        raw=text if include_raw else None,
    )


def build_endpoint(target: str, https: bool, port: int | None) -> tuple[str, str]:
    """Return a normalized host and the fixed KM-WSDL scan endpoint."""
    if "://" in target:
        parsed = urlsplit(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("target URL must use http:// or https:// and a host")
        if parsed.path not in {"", "/", SCAN_PATH}:
            raise ValueError(f"target URL path must be {SCAN_PATH}")
        https = parsed.scheme == "https"
        port = parsed.port
        target = parsed.hostname

    hostname = f"[{target}]" if ":" in target and not target.startswith("[") else target
    scheme = "https" if https else "http"
    if port is None:
        port = 9091 if https else 9090
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return hostname, f"{scheme}://{hostname}:{port}{SCAN_PATH}"


def _post(
    endpoint: str,
    payload: bytes,
    headers: dict[str, str],
    *,
    timeout: float,
    insecure: bool,
) -> tuple[int, bytes]:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must use http:// or https:// and a host")
    context = None
    if parsed.scheme == "https":
        context = ssl.create_default_context()
        if insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port,
            timeout=timeout,
            context=context,
        )
    else:
        connection = http.client.HTTPConnection(
            parsed.hostname,
            parsed.port,
            timeout=timeout,
        )
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        connection.putrequest("POST", path, skip_accept_encoding=True)
        connection.putheader("Host", parsed.netloc)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(payload)))
        connection.putheader("Connection", "close")
        connection.endheaders(payload)
        response = connection.getresponse()
        body = response.read(2 * 1024 * 1024 + 1)
        status = response.status
    finally:
        connection.close()
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("KM-WSDL response exceeds 2 MiB")
    return status, body


def probe(
    endpoint: str,
    *,
    soap_version: str = "1.1",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> ProbeResult:
    """Send one read-only get_service_information request."""
    payload, headers = build_request(soap_version)
    status, body = _post(
        endpoint,
        payload,
        headers,
        timeout=timeout,
        insecure=insecure,
    )
    return parse_response(
        body,
        endpoint=endpoint,
        http_status=status,
        soap_version=soap_version,
        include_raw=include_raw,
    )


def probe_capability(
    endpoint: str,
    *,
    soap_version: str = "1.1",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> CapabilityResult:
    """Send one read-only get_capability request."""
    payload, headers = build_operation_request("get_capability", soap_version)
    status, body = _post(
        endpoint,
        payload,
        headers,
        timeout=timeout,
        insecure=insecure,
    )
    return parse_capability_response(
        body,
        endpoint=endpoint,
        http_status=status,
        soap_version=soap_version,
        include_raw=include_raw,
    )


def preflight(
    endpoint: str,
    *,
    soap_version: str = "1.1",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> PreflightResult:
    """Reproduce the driver's ordered service-info/capability preflight."""
    try:
        service_information = probe(
            endpoint,
            soap_version=soap_version,
            timeout=timeout,
            insecure=insecure,
            include_raw=include_raw,
        )
    except (OSError, ValueError) as error:
        return PreflightResult(
            ok=False,
            endpoint=endpoint,
            soap_version=soap_version,
            service_information=None,
            capability=None,
            failed_stage="service_information",
            error=str(error),
        )
    if not service_information.ok:
        return PreflightResult(
            ok=False,
            endpoint=endpoint,
            soap_version=soap_version,
            service_information=service_information,
            capability=None,
            failed_stage="service_information",
            error=None,
        )
    try:
        capability = probe_capability(
            endpoint,
            soap_version=soap_version,
            timeout=timeout,
            insecure=insecure,
            include_raw=include_raw,
        )
    except (OSError, ValueError) as error:
        return PreflightResult(
            ok=False,
            endpoint=endpoint,
            soap_version=soap_version,
            service_information=service_information,
            capability=None,
            failed_stage="capability",
            error=str(error),
        )
    return PreflightResult(
        ok=capability.ok,
        endpoint=endpoint,
        soap_version=soap_version,
        service_information=service_information,
        capability=capability,
        failed_stage=None if capability.ok else "capability",
        error=None,
    )


def _print_human(result: ProbeResult) -> None:
    print(f"endpoint: {result.endpoint}")
    print(f"HTTP: {result.http_status}")
    print(f"SOAP: {result.soap_version}")
    for key in ("result", "version", "release_date", "model_name"):
        value = getattr(result, key)
        if value is not None:
            print(f"{key}: {value}")
    if result.fault_code is not None:
        print(f"fault_code: {result.fault_code}")
    if result.fault_reason is not None:
        print(f"fault_reason: {result.fault_reason}")
    if result.raw is not None:
        print(result.raw)


def _print_preflight(
    result: PreflightResult,
) -> None:
    print(f"endpoint: {result.endpoint}")
    print(f"SOAP: {result.soap_version}")
    if result.failed_stage is not None:
        print(f"failed_stage: {result.failed_stage}")
    if result.error is not None:
        print(f"error: {result.error}")
    if result.service_information is None:
        print("service information: not received")
        print("capability: not sent")
        return
    print("service information:")
    _print_human(result.service_information)
    if result.capability is None:
        print("capability: skipped because service information failed")
        return
    print("capability:")
    _print_capability(result.capability)


def _print_capability(result: CapabilityResult) -> None:
    print(f"endpoint: {result.endpoint}")
    print(f"HTTP: {result.http_status}")
    print(f"SOAP: {result.soap_version}")
    if result.result is not None:
        print(f"result: {result.result}")
    if result.fault_code is not None:
        print(f"fault_code: {result.fault_code}")
    if result.fault_reason is not None:
        print(f"fault_reason: {result.fault_reason}")
    if result.missing_capabilities:
        print("missing capabilities: " + ", ".join(result.missing_capabilities))
    for name, capability in result.capabilities.items():
        if capability is None:
            continue
        print(f"{name}:")
        print(json.dumps(asdict(capability), ensure_ascii=False, indent=2))
    if result.raw is not None:
        print(result.raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="printer IPv4/IPv6 address or http(s) URL")
    parser.add_argument(
        "--https",
        action="store_true",
        help="use HTTPS and the driver's default port 9091",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="override the endpoint port (defaults: HTTP 9090, HTTPS 9091)",
    )
    operation_group = parser.add_mutually_exclusive_group()
    operation_group.add_argument(
        "--capability",
        action="store_true",
        help=(
            "send the read-only get_capability request instead of "
            "get_service_information"
        ),
    )
    operation_group.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "send get_service_information, then get_capability only if the "
            "first response is accepted"
        ),
    )
    parser.add_argument(
        "--soap-version",
        choices=tuple(_ENVELOPES),
        default="1.1",
        help="SOAP envelope version (default: 1.1, the driver's initialization)",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable HTTPS certificate verification for a local test device",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--raw", action="store_true", help="include response XML")
    args = parser.parse_args(argv)

    try:
        _, endpoint = build_endpoint(args.target, args.https, args.port)
        if args.preflight:
            preflight_result = preflight(
                endpoint,
                soap_version=args.soap_version,
                timeout=args.timeout,
                insecure=args.insecure,
                include_raw=args.raw,
            )
        elif args.capability:
            capability = probe_capability(
                endpoint,
                soap_version=args.soap_version,
                timeout=args.timeout,
                insecure=args.insecure,
                include_raw=args.raw,
            )
        else:
            result = probe(
                endpoint,
                soap_version=args.soap_version,
                timeout=args.timeout,
                insecure=args.insecure,
                include_raw=args.raw,
            )
    except (OSError, ValueError) as error:
        print(f"KM-WSDL probe failed: {error}", file=sys.stderr)
        return 2

    if args.preflight:
        if args.json:
            print(
                json.dumps(
                    asdict(preflight_result),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_preflight(preflight_result)
            if not preflight_result.ok:
                print("KM-WSDL preflight was not accepted", file=sys.stderr)
        return 0 if preflight_result.ok else 1

    if args.capability:
        if args.json:
            print(json.dumps(asdict(capability), ensure_ascii=False, indent=2))
        else:
            _print_capability(capability)
            if not capability.ok:
                print("get_capability was not accepted", file=sys.stderr)
        return 0 if capability.ok else 1

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        _print_human(result)
        if not result.ok:
            print("get_service_information was not accepted", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
