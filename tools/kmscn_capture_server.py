#!/usr/bin/env python3
"""Capture one official KM-WSDL request on loopback and return a test response."""

from __future__ import annotations

import argparse
import json
import socketserver
from pathlib import Path

RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body>
  <kmscn:get_service_informationResponse>
   <kmscn:result>0</kmscn:result>
   <kmscn:information>
    <kmscn:version>1.0</kmscn:version>
    <kmscn:release_date>1970-01-01</kmscn:release_date>
    <kmscn:model_name>TEST_SCANNER</kmscn:model_name>
   </kmscn:information>
  </kmscn:get_service_informationResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""

CAPABILITY_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body xml:space="preserve">
  <kmscn:get_capabilityResponse>
   <kmscn:result>SUCCESS</kmscn:result>
   <kmscn:scan_image_configuration_capability>
    <kmscn:duplex_mode>DUPLEX</kmscn:duplex_mode>
   </kmscn:scan_image_configuration_capability>
  </kmscn:get_capabilityResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""

OPEN_SESSION_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body xml:space="preserve">
  <kmscn:open_sessionResponse>
   <kmscn:result>SUCCESS</kmscn:result>
   <kmscn:operation_id>1</kmscn:operation_id>
  </kmscn:open_sessionResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""

START_SCAN_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body xml:space="preserve">
  <kmscn:start_scanResponse>
   <kmscn:result>SUCCESS</kmscn:result>
  </kmscn:start_scanResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""

RETRIEVE_IMAGE_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body xml:space="preserve">
  <kmscn:retrieve_imageResponse>
   <kmscn:result>SUCCESS</kmscn:result>
   <kmscn:image_data></kmscn:image_data>
  </kmscn:retrieve_imageResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""

CLOSE_SESSION_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body xml:space="preserve">
  <kmscn:close_sessionResponse>
   <kmscn:result>SUCCESS</kmscn:result>
  </kmscn:close_sessionResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""


class CaptureServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.captures: list[bytes] = []


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(10)
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(65536)
            if not chunk:
                break
            data.extend(chunk)
        header_end = data.find(b"\r\n\r\n")
        if header_end < 0:
            self.server.captures.append(bytes(data))
            return
        header_end += 4
        headers = data[:header_end].decode("iso-8859-1", "replace")
        content_length = 0
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        body_needed = content_length - (len(data) - header_end)
        while body_needed > 0:
            chunk = self.request.recv(min(65536, body_needed))
            if not chunk:
                break
            data.extend(chunk)
            body_needed -= len(chunk)
        self.server.captures.append(bytes(data))
        response = RESPONSE
        if b"get_capabilityRequest" in data:
            response = CAPABILITY_RESPONSE
        elif b"open_sessionRequest" in data:
            response = OPEN_SESSION_RESPONSE
        elif b"start_scanRequest" in data:
            response = START_SCAN_RESPONSE
        elif b"retrieve_imageRequest" in data:
            response = RETRIEVE_IMAGE_RESPONSE
        elif b"close_sessionRequest" in data:
            response = CLOSE_SESSION_RESPONSE
        self.request.sendall(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/xml; charset=utf-8\r\n"
            + f"Content-Length: {len(response)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + response
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--requests", type=int, default=1)
    args = parser.parse_args()

    with CaptureServer((args.host, args.port), Handler) as server:
        print(
            json.dumps(
                {
                    "listening": f"http://{args.host}:{args.port}",
                    "output": str(args.output),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        for _ in range(args.requests):
            server.handle_request()
        capture = b"\n\n===== REQUEST =====\n\n".join(server.captures)
    args.output.write_bytes(capture)
    print(
        json.dumps(
            {
                "requests": len(server.captures),
                "captured_bytes": len(capture),
            }
        ),
        flush=True,
    )
    return 0 if server.captures else 1


if __name__ == "__main__":
    raise SystemExit(main())
