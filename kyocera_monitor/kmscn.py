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
from dataclasses import asdict, dataclass, field
from email import policy
from email.parser import BytesParser
from urllib.parse import urlsplit
from xml.sax.saxutils import escape, quoteattr

SCAN_PATH = "/ws/km-wsdl/job/scan_operation"
SCAN_NAMESPACE = (
    "http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation"
)
GET_SERVICE_INFORMATION_ACTION = f"{SCAN_NAMESPACE}/get_service_information"
GET_CAPABILITY_ACTION = f"{SCAN_NAMESPACE}/get_capability"
GET_DEFAULT_CONFIGURATION_ACTION = f"{SCAN_NAMESPACE}/get_default_configuration"

_READ_ONLY_OPERATIONS = {
    "get_service_information",
    "get_capability",
    "get_default_configuration",
}

_SCAN_SESSION_OPERATIONS = {
    "open_session",
    "start_scan",
    "retrieve_image",
    "cancel_scan",
    "close_session",
}

_SUPPORTED_OPERATIONS = _READ_ONLY_OPERATIONS | _SCAN_SESSION_OPERATIONS

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

_OFFICIAL_NAMESPACE_DECLARATIONS = (
    ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/'
    'oasis-200401-wss-wssecurity-utility-1.0.xsd"'
    ' xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
    ' xmlns:discovery="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
    ' xmlns:eventing="http://schemas.xmlsoap.org/ws/2004/08/eventing"'
    ' xmlns:addressing="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
    ' xmlns:kmauth="http://www.kyoceramita.com/ws/km-wsdl/security/'
    'authentication_authorization"'
    ' xmlns:kmboxinfo="http://www.kyoceramita.com/ws/km-wsdl/setting/'
    'box_information"'
    ' xmlns:kmsavedata="http://www.kyoceramita.com/ws/km-wsdl/job/'
    'stored_data_operation"'
    f' xmlns:kmscn="{SCAN_NAMESPACE}"'
    ' xmlns:kmuserlist="http://www.kyoceramita.com/ws/km-wsdl/setting/'
    'user_list"'
    ' xmlns:kmdevinf="http://www.kyoceramita.com/ws/km-wsdl/information/'
    'device_information"'
    ' xmlns:c14n="http://www.w3.org/2001/10/xml-exc-c14n#"'
    ' xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/'
    'oasis-200401-wss-wssecurity-secext-1.0.xsd"'
    ' xmlns:wsa="http://www.w3.org/2005/08/addressing"'
    ' xmlns:xop="http://www.w3.org/2004/08/xop/include"'
    ' xmlns:ns1="http://www.w3.org/2005/05/xmlmime"'
)


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
class DefaultConfigurationResult:
    ok: bool
    endpoint: str
    http_status: int
    soap_version: str
    result: str | None
    configuration: XmlNode | None
    fault_code: str | None
    fault_reason: str | None
    raw: str | None = None


@dataclass(frozen=True)
class ScanResponse:
    ok: bool
    operation: str
    endpoint: str
    http_status: int
    soap_version: str
    result: str | None
    operation_id: str | None
    image_data: str | None
    file_type: str | None
    file_size: int | None
    content_type: str | None
    body_length: int
    fault_code: str | None
    fault_reason: str | None
    raw: str | None = None
    body: bytes | None = field(default=None, repr=False, compare=False)


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
    operation: str, soap_version: str = "1.2"
) -> tuple[bytes, dict[str, str]]:
    """Build one of the driver's empty read-only operation requests."""
    if operation not in _READ_ONLY_OPERATIONS:
        raise ValueError(f"unsupported read-only operation: {operation}")
    content = (
        f"<kmscn:{operation}Request>"
        f"</kmscn:{operation}Request>"
    )
    return build_operation_request_body(operation, content, soap_version)


def build_operation_request_body(
    operation: str,
    request_content: str,
    soap_version: str = "1.2",
) -> tuple[bytes, dict[str, str]]:
    """Build a scan-operation request with caller-provided body content."""
    if operation not in _SUPPORTED_OPERATIONS:
        raise ValueError(f"unsupported scan operation: {operation}")
    try:
        envelope_ns, encoding_ns = _ENVELOPES[soap_version]
    except KeyError as error:
        raise ValueError(f"unsupported SOAP version: {soap_version}") from error

    action = f"{SCAN_NAMESPACE}/{operation}"
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{envelope_ns}"'
        f' xmlns:SOAP-ENC="{encoding_ns}"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"'
        f"{_OFFICIAL_NAMESPACE_DECLARATIONS}>"
        f"<SOAP-ENV:Header><wsa:Action>{action}</wsa:Action>"
        "</SOAP-ENV:Header>"
        f"<SOAP-ENV:Body>{request_content}</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    )
    headers = {
        "User-Agent": "gSOAP/2.7",
        "Content-Type": (
            "text/xml; charset=utf-8"
            if soap_version == "1.1"
            else "application/soap+xml; charset=utf-8"
        ),
        "SOAPAction": f'"{action}"',
    }
    return body.encode("utf-8"), headers


def build_request(soap_version: str = "1.2") -> tuple[bytes, dict[str, str]]:
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


def _result_is_success(result: str | None) -> bool:
    return result is None or result.strip().upper() in {"0", "SUCCESS"}


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
    result_ok = _result_is_success(result)
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
            and result is not None
            and _result_is_success(result)
            and any(value is not None for value in capabilities.values())
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


def parse_default_configuration_response(
    body: bytes,
    *,
    endpoint: str,
    http_status: int,
    soap_version: str,
    include_raw: bool = False,
) -> DefaultConfigurationResult:
    """Parse the device's default scan configuration as an XML tree."""
    text = body.decode("utf-8", "replace")
    try:
        root = _parse_xml(text)
    except ET.ParseError:
        return DefaultConfigurationResult(
            ok=False,
            endpoint=endpoint,
            http_status=http_status,
            soap_version=soap_version,
            result=None,
            configuration=None,
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
            if _local_name(element.tag) == "get_default_configurationResponse"
        ),
        None,
    )
    configuration = _xml_node(response) if response is not None else None
    http_ok = 200 <= http_status < 300
    return DefaultConfigurationResult(
        ok=(
            http_ok
            and fault_code is None
            and fault_reason is None
            and result is not None
            and _result_is_success(result)
            and configuration is not None
        ),
        endpoint=endpoint,
        http_status=http_status,
        soap_version=soap_version,
        result=result,
        configuration=configuration,
        fault_code=fault_code,
        fault_reason=fault_reason,
        raw=text if include_raw else None,
    )


def _render_xml_node(node: XmlNode) -> str:
    attributes = "".join(
        f" {name}={quoteattr(value)}"
        for name, value in node.attributes.items()
    )
    text = escape(node.text) if node.text else ""
    children = "".join(_render_xml_node(child) for child in node.children)
    return (
        f"<kmscn:{node.name}{attributes}>"
        f"{text}{children}"
        f"</kmscn:{node.name}>"
    )


def _configuration_sections(configuration: XmlNode) -> str:
    allowed = {
        "scan_image_configuration",
        "original_configuration",
        "output_image_configuration",
    }
    sections = [child for child in configuration.children if child.name in allowed]
    if len(sections) != 3:
        raise ValueError("default configuration is missing a required section")
    return "".join(_render_xml_node(section) for section in sections)


def replace_configuration_value(
    node: XmlNode,
    name: str,
    value: str,
) -> XmlNode:
    """Return a copy of a configuration tree with one field replaced."""
    return XmlNode(
        name=node.name,
        attributes=node.attributes,
        text=value if node.name == name else node.text,
        children=tuple(
            replace_configuration_value(child, name, value)
            for child in node.children
        ),
    )


def build_open_session_request(
    soap_version: str = "1.2",
) -> tuple[bytes, dict[str, str]]:
    """Build the driver's unauthenticated open_session request."""
    content = (
        "<kmscn:open_sessionRequest>"
        "</kmscn:open_sessionRequest>"
    )
    return build_operation_request_body("open_session", content, soap_version)


def build_start_scan_request(
    operation_id: str,
    configuration: XmlNode,
    soap_version: str = "1.2",
) -> tuple[bytes, dict[str, str]]:
    """Build start_scan from the device's default configuration."""
    content = (
        "<kmscn:start_scanRequest>"
        f"<kmscn:operation_id>{escape(operation_id)}</kmscn:operation_id>"
        f"{_configuration_sections(configuration)}"
        "</kmscn:start_scanRequest>"
    )
    return build_operation_request_body("start_scan", content, soap_version)


def build_retrieve_image_request(
    operation_id: str,
    soap_version: str = "1.2",
) -> tuple[bytes, dict[str, str]]:
    """Build one image retrieval request for an active scan operation."""
    content = (
        "<kmscn:retrieve_imageRequest>"
        f"<kmscn:operation_id>{escape(operation_id)}</kmscn:operation_id>"
        "</kmscn:retrieve_imageRequest>"
    )
    return build_operation_request_body("retrieve_image", content, soap_version)


def build_close_session_request(
    operation_id: str,
    soap_version: str = "1.2",
) -> tuple[bytes, dict[str, str]]:
    """Build close_session for an active scan operation."""
    content = (
        "<kmscn:close_sessionRequest>"
        f"<kmscn:operation_id>{escape(operation_id)}</kmscn:operation_id>"
        "</kmscn:close_sessionRequest>"
    )
    return build_operation_request_body("close_session", content, soap_version)


def _parse_multipart(
    content_type: str,
    body: bytes,
) -> tuple[ET.Element, bytes | None]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode(
            "ascii"
        )
        + body
    )
    if not message.is_multipart():
        raise ValueError("response is not valid multipart data")

    root = None
    image_bytes = None
    for part in message.iter_parts():
        payload = part.get_payload(decode=True) or b""
        part_type = part.get_content_type().lower()
        if part_type in {"application/xop+xml", "application/soap+xml"}:
            charset = part.get_content_charset() or "utf-8"
            root = _parse_xml(payload.decode(charset, "replace"))
        elif image_bytes is None and payload:
            image_bytes = payload
    if root is None:
        raise ValueError("multipart response has no SOAP XML part")
    return root, image_bytes


def parse_scan_response(
    body: bytes,
    *,
    operation: str,
    endpoint: str,
    http_status: int,
    soap_version: str,
    content_type: str | None = None,
    include_raw: bool = False,
) -> ScanResponse:
    """Parse open/start/retrieve/close responses for the scan session."""
    text = body.decode("utf-8", "replace")
    image_bytes = None
    try:
        if content_type and content_type.lower().startswith("multipart/"):
            root, image_bytes = _parse_multipart(content_type, body)
            text = ET.tostring(root, encoding="unicode")
        else:
            root = _parse_xml(text)
    except (ET.ParseError, ValueError):
        return ScanResponse(
            ok=False,
            operation=operation,
            endpoint=endpoint,
            http_status=http_status,
            soap_version=soap_version,
            result=None,
            operation_id=None,
            image_data=None,
            file_type=None,
            file_size=None,
            content_type=content_type,
            body_length=len(body),
            fault_code="invalid_xml",
            fault_reason="response is not well-formed XML",
            raw=text if include_raw else None,
            body=body,
        )

    fault_code, fault_reason = _fault_fields(root)
    result = _first_text(root, "result")
    response = next(
        (
            element
            for element in root.iter()
            if _local_name(element.tag) == f"{operation}Response"
        ),
        None,
    )
    operation_id = (
        _first_text(response, "operation_id")
        if response is not None
        else None
    )
    image_data = (
        _first_text(response, "image_data")
        if response is not None
        else None
    )
    file_type = (
        _first_text(response, "file_type")
        if response is not None
        else None
    )
    file_size_text = (
        _first_text(response, "file_size")
        if response is not None
        else None
    )
    try:
        file_size = int(file_size_text) if file_size_text is not None else None
    except ValueError:
        file_size = None
    http_ok = 200 <= http_status < 300
    retrieval_pending = result == "IMAGE_CREATING_NOW"
    retrieval_complete = result == "ALL_GET_COMPLETE"
    return ScanResponse(
        ok=(
            http_ok
            and fault_code is None
            and fault_reason is None
            and result is not None
            and (
                _result_is_success(result)
                or retrieval_pending
                or retrieval_complete
            )
        ),
        operation=operation,
        endpoint=endpoint,
        http_status=http_status,
        soap_version=soap_version,
        result=result,
        operation_id=operation_id,
        image_data=image_data,
        file_type=file_type,
        file_size=file_size,
        content_type=content_type,
        body_length=len(body),
        fault_code=fault_code,
        fault_reason=fault_reason,
        raw=text if include_raw else None,
        body=image_bytes if image_bytes is not None else body,
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
    max_response_bytes: int = 2 * 1024 * 1024,
) -> tuple[int, bytes]:
    status, _, body = _post_response(
        endpoint,
        payload,
        headers,
        timeout=timeout,
        insecure=insecure,
        max_response_bytes=max_response_bytes,
    )
    return status, body


def _post_response(
    endpoint: str,
    payload: bytes,
    headers: dict[str, str],
    *,
    timeout: float,
    insecure: bool,
    max_response_bytes: int = 2 * 1024 * 1024,
) -> tuple[int, dict[str, str], bytes]:
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
        body = response.read(max_response_bytes + 1)
        status = response.status
        response_headers = {
            name.lower(): value for name, value in response.getheaders()
        }
    finally:
        connection.close()
    if len(body) > max_response_bytes:
        raise ValueError(
            f"KM-WSDL response exceeds {max_response_bytes} bytes"
        )
    return status, response_headers, body


def probe(
    endpoint: str,
    *,
    soap_version: str = "1.2",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> ProbeResult:
    """Send one read-only get_service_information request."""
    payload, headers = build_request(soap_version)
    status, response_headers, body = _post_response(
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
    soap_version: str = "1.2",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> CapabilityResult:
    """Send one read-only get_capability request."""
    payload, headers = build_operation_request("get_capability", soap_version)
    status, response_headers, body = _post_response(
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


def probe_default_configuration(
    endpoint: str,
    *,
    soap_version: str = "1.2",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> DefaultConfigurationResult:
    """Send the read-only get_default_configuration request."""
    payload, headers = build_operation_request(
        "get_default_configuration", soap_version
    )
    status, body = _post(
        endpoint,
        payload,
        headers,
        timeout=timeout,
        insecure=insecure,
    )
    return parse_default_configuration_response(
        body,
        endpoint=endpoint,
        http_status=status,
        soap_version=soap_version,
        include_raw=include_raw,
    )


def _perform_scan_operation(
    endpoint: str,
    operation: str,
    request: tuple[bytes, dict[str, str]],
    *,
    soap_version: str,
    timeout: float,
    insecure: bool,
    include_raw: bool,
    max_response_bytes: int = 2 * 1024 * 1024,
) -> ScanResponse:
    payload, headers = request
    status, response_headers, body = _post_response(
        endpoint,
        payload,
        headers,
        timeout=timeout,
        insecure=insecure,
        max_response_bytes=max_response_bytes,
    )
    return parse_scan_response(
        body,
        operation=operation,
        endpoint=endpoint,
        http_status=status,
        soap_version=soap_version,
        content_type=response_headers.get("content-type"),
        include_raw=include_raw,
    )


def open_session(
    endpoint: str,
    *,
    soap_version: str = "1.2",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> ScanResponse:
    """Open an unauthenticated scan operation session."""
    return _perform_scan_operation(
        endpoint,
        "open_session",
        build_open_session_request(soap_version),
        soap_version=soap_version,
        timeout=timeout,
        insecure=insecure,
        include_raw=include_raw,
    )


def start_scan(
    endpoint: str,
    operation_id: str,
    configuration: XmlNode,
    *,
    soap_version: str = "1.2",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> ScanResponse:
    """Start one scan using a device-provided configuration tree."""
    return _perform_scan_operation(
        endpoint,
        "start_scan",
        build_start_scan_request(operation_id, configuration, soap_version),
        soap_version=soap_version,
        timeout=timeout,
        insecure=insecure,
        include_raw=include_raw,
    )


def retrieve_image(
    endpoint: str,
    operation_id: str,
    *,
    soap_version: str = "1.2",
    timeout: float = 30.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> ScanResponse:
    """Retrieve the next page or completion status from an active scan."""
    return _perform_scan_operation(
        endpoint,
        "retrieve_image",
        build_retrieve_image_request(operation_id, soap_version),
        soap_version=soap_version,
        timeout=timeout,
        insecure=insecure,
        include_raw=include_raw,
        max_response_bytes=64 * 1024 * 1024,
    )


def close_session(
    endpoint: str,
    operation_id: str,
    *,
    soap_version: str = "1.2",
    timeout: float = 5.0,
    insecure: bool = False,
    include_raw: bool = False,
) -> ScanResponse:
    """Close an active scan operation session."""
    return _perform_scan_operation(
        endpoint,
        "close_session",
        build_close_session_request(operation_id, soap_version),
        soap_version=soap_version,
        timeout=timeout,
        insecure=insecure,
        include_raw=include_raw,
    )


def preflight(
    endpoint: str,
    *,
    soap_version: str = "1.2",
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


def _print_default_configuration(result: DefaultConfigurationResult) -> None:
    print(f"endpoint: {result.endpoint}")
    print(f"HTTP: {result.http_status}")
    print(f"SOAP: {result.soap_version}")
    if result.result is not None:
        print(f"result: {result.result}")
    if result.fault_code is not None:
        print(f"fault_code: {result.fault_code}")
    if result.fault_reason is not None:
        print(f"fault_reason: {result.fault_reason}")
    if result.configuration is not None:
        print("configuration:")
        print(
            json.dumps(
                asdict(result.configuration),
                ensure_ascii=False,
                indent=2,
            )
        )
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
    operation_group.add_argument(
        "--default-configuration",
        action="store_true",
        help="send the read-only get_default_configuration request",
    )
    parser.add_argument(
        "--soap-version",
        choices=tuple(_ENVELOPES),
        default="1.2",
        help="SOAP envelope version (default: 1.2, observed from the driver)",
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
        elif args.default_configuration:
            default_configuration = probe_default_configuration(
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

    if args.default_configuration:
        if args.json:
            print(
                json.dumps(
                    asdict(default_configuration),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_default_configuration(default_configuration)
            if not default_configuration.ok:
                print(
                    "get_default_configuration was not accepted",
                    file=sys.stderr,
                )
        return 0 if default_configuration.ok else 1

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        _print_human(result)
        if not result.ok:
            print("get_service_information was not accepted", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
