import unittest
from unittest import mock

from kyocera_monitor import kmscn


class RequestTests(unittest.TestCase):
    def test_official_scan_enum_tokens_are_explicit(self):
        self.assertEqual(
            kmscn.COLOR_SELECTIONS,
            (
                "FULL_COLOR",
                "GRAYSCALE",
                "BLACK_AND_WHITE",
                "AUTO_BLACK_AND_WHITE",
                "AUTO_GRAYSCALE",
            ),
        )
        self.assertEqual(
            kmscn.SCAN_RESOLUTIONS,
            (
                "RESOLUTION_150X150",
                "RESOLUTION_200X100",
                "RESOLUTION_200X200",
                "RESOLUTION_200X400",
                "RESOLUTION_300X300",
                "RESOLUTION_400X400",
                "RESOLUTION_600X600",
            ),
        )
        self.assertEqual(
            kmscn.DUPLEX_MODES,
            ("SIMPLEX", "DUPLEX", "BOOKLET"),
        )
        self.assertEqual(
            kmscn.ORIGINAL_PLACEMENTS,
            ("AUTO", "PLATEN", "ADF"),
        )
        self.assertEqual(
            kmscn.CONTINUOUS_SCAN_MODES,
            ("OFF", "ON"),
        )
        self.assertEqual(
            kmscn.ORIGINAL_IMAGES,
            (
                "TEXT",
                "TEXT_AND_PHOTO",
                "PHOTO",
                "FOR_OCR",
                "MAP",
                "LIGHT_TEXT",
            ),
        )
        self.assertEqual(
            kmscn.IMAGE_FILE_FORMATS,
            (
                "PDF",
                "TIFF",
                "JPEG",
                "HIGH_COMPRESSION_PDF",
                "XPS",
                "RAW",
            ),
        )

    def test_soap_11_keeps_official_wsa_action_header(self):
        payload, headers = kmscn.build_request("1.1")
        text = payload.decode("utf-8")
        self.assertIn(
            'xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"',
            text,
        )
        self.assertIn(
            "<SOAP-ENV:Header><wsa:Action>"
            f"{kmscn.GET_SERVICE_INFORMATION_ACTION}"
            "</wsa:Action></SOAP-ENV:Header>",
            text,
        )
        self.assertIn(
            "<kmscn:get_service_informationRequest>"
            "</kmscn:get_service_informationRequest>",
            text,
        )
        self.assertEqual(headers["Content-Type"], "text/xml; charset=utf-8")
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.GET_SERVICE_INFORMATION_ACTION}"',
        )

    def test_soap_12_matches_captured_driver_headers(self):
        payload, headers = kmscn.build_request("1.2")
        self.assertIn(
            b"http://www.w3.org/2003/05/soap-envelope",
            payload,
        )
        self.assertEqual(
            headers["Content-Type"],
            "application/soap+xml; charset=utf-8",
        )
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.GET_SERVICE_INFORMATION_ACTION}"',
        )

    def test_default_is_captured_soap_12_profile(self):
        payload, headers = kmscn.build_request()
        self.assertIn(b"http://www.w3.org/2003/05/soap-envelope", payload)
        self.assertEqual(
            headers["Content-Type"],
            "application/soap+xml; charset=utf-8",
        )
        self.assertIn(
            b'xmlns:wsa="http://www.w3.org/2005/08/addressing"',
            payload,
        )
        self.assertIn(
            b"<SOAP-ENV:Header><wsa:Action>",
            payload,
        )

    def test_rejects_unknown_soap_version(self):
        with self.assertRaises(ValueError):
            kmscn.build_request("1.0")

    def test_capability_request_matches_driver_operation(self):
        payload, headers = kmscn.build_operation_request("get_capability")
        text = payload.decode("utf-8")
        self.assertIn(
            "<kmscn:get_capabilityRequest></kmscn:get_capabilityRequest>",
            text,
        )
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.GET_CAPABILITY_ACTION}"',
        )

    def test_non_read_only_operation_is_rejected(self):
        with self.assertRaises(ValueError):
            kmscn.build_operation_request("start_scan")


class EndpointTests(unittest.TestCase):
    def test_default_ports_follow_driver(self):
        self.assertEqual(
            kmscn.build_endpoint("192.0.2.1", False, None),
            ("192.0.2.1", f"http://192.0.2.1:9090{kmscn.SCAN_PATH}"),
        )
        self.assertEqual(
            kmscn.build_endpoint("192.0.2.1", True, None),
            ("192.0.2.1", f"https://192.0.2.1:9091{kmscn.SCAN_PATH}"),
        )

    def test_ipv6_is_bracketed(self):
        _, endpoint = kmscn.build_endpoint("2001:db8::1", False, None)
        self.assertEqual(
            endpoint,
            f"http://[2001:db8::1]:9090{kmscn.SCAN_PATH}",
        )

    def test_fixed_scan_path_is_accepted(self):
        _, endpoint = kmscn.build_endpoint(
            f"https://192.0.2.1:9443{kmscn.SCAN_PATH}",
            False,
            None,
        )
        self.assertEqual(
            endpoint,
            f"https://192.0.2.1:9443{kmscn.SCAN_PATH}",
        )


class ResponseTests(unittest.TestCase):
    RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body>
  <kmscn:get_service_informationResponse>
   <kmscn:result>0</kmscn:result>
   <kmscn:information>
    <kmscn:version>1.0</kmscn:version>
    <kmscn:release_date>01/02/2023</kmscn:release_date>
    <kmscn:model_name>MA2000w</kmscn:model_name>
   </kmscn:information>
  </kmscn:get_service_informationResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

    def test_extracts_service_information(self):
        result = kmscn.parse_response(
            self.RESPONSE,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.1",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "0")
        self.assertEqual(result.version, "1.0")
        self.assertEqual(result.release_date, "01/02/2023")
        self.assertEqual(result.model_name, "MA2000w")

    def test_soap_fault_is_not_success(self):
        response = b"""<SOAP-ENV:Envelope
 xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
 <SOAP-ENV:Body><SOAP-ENV:Fault>
  <faultcode>SOAP-ENV:Client</faultcode>
  <faultstring>unsupported</faultstring>
 </SOAP-ENV:Fault></SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        result = kmscn.parse_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=500,
            soap_version="1.1",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.fault_code, "SOAP-ENV:Client")
        self.assertEqual(result.fault_reason, "unsupported")

    def test_nonzero_result_is_not_success(self):
        response = self.RESPONSE.replace(
            b"<kmscn:result>0</kmscn:result>",
            b"<kmscn:result>7</kmscn:result>",
        )
        result = kmscn.parse_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.1",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.result, "7")

    def test_device_success_token_is_accepted(self):
        response = self.RESPONSE.replace(
            b"<kmscn:result>0</kmscn:result>",
            b"<kmscn:result>SUCCESS</kmscn:result>",
        )
        result = kmscn.parse_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.2",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "SUCCESS")

    def test_rejects_dtd_instead_of_expanding_entities(self):
        response = b"""<?xml version="1.0"?>
<!DOCTYPE response [<!ENTITY payload "unexpected">]>
<response>&payload;</response>"""
        result = kmscn.parse_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.1",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.fault_code, "invalid_xml")


class CapabilityResponseTests(unittest.TestCase):
    RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body>
  <kmscn:get_capabilityResponse>
   <kmscn:result>0</kmscn:result>
   <kmscn:scan_image_configuration_capability>
    <kmscn:color_selection_capability>
     <kmscn:value>1</kmscn:value>
     <kmscn:value>2</kmscn:value>
    </kmscn:color_selection_capability>
   </kmscn:scan_image_configuration_capability>
   <kmscn:original_configuration_capability>
    <kmscn:original_size_capability>
     <kmscn:value>A4</kmscn:value>
    </kmscn:original_size_capability>
   </kmscn:original_configuration_capability>
   <kmscn:output_image_configuration_capability>
    <kmscn:image_file_format_capability>
     <kmscn:value>PDF</kmscn:value>
    </kmscn:image_file_format_capability>
   </kmscn:output_image_configuration_capability>
  </kmscn:get_capabilityResponse>
 </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

    def test_preserves_three_capability_trees(self):
        result = kmscn.parse_capability_response(
            self.RESPONSE,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.1",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "0")
        self.assertEqual(result.missing_capabilities, ())
        scan = result.capabilities["scan_image_configuration_capability"]
        self.assertIsNotNone(scan)
        self.assertEqual(scan.name, "scan_image_configuration_capability")
        self.assertEqual(scan.children[0].name, "color_selection_capability")
        self.assertEqual(
            [child.text for child in scan.children[0].children],
            ["1", "2"],
        )

    def test_missing_optional_capability_is_explicit_but_successful(self):
        response = self.RESPONSE.replace(
            b"<kmscn:original_configuration_capability>",
            b"<kmscn:unexpected_capability>",
        ).replace(
            b"</kmscn:original_configuration_capability>",
            b"</kmscn:unexpected_capability>",
        )
        result = kmscn.parse_capability_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.1",
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            result.missing_capabilities,
            ("original_configuration_capability",),
        )

    def test_response_without_capability_blocks_preflight(self):
        response = self.RESPONSE
        for name in kmscn.CAPABILITY_ENTRY_NAMES:
            start = response.index(f"<kmscn:{name}>".encode("ascii"))
            end = response.index(f"</kmscn:{name}>".encode("ascii"))
            end += len(f"</kmscn:{name}>")
            response = response[:start] + response[end:]
        result = kmscn.parse_capability_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.2",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.missing_capabilities, kmscn.CAPABILITY_ENTRY_NAMES)

    def test_device_success_token_is_accepted(self):
        response = self.RESPONSE.replace(
            b"<kmscn:result>0</kmscn:result>",
            b"<kmscn:result>SUCCESS</kmscn:result>",
        )
        result = kmscn.parse_capability_response(
            response,
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.2",
        )
        self.assertTrue(result.ok)


class SessionRequestTests(unittest.TestCase):
    CONFIGURATION = kmscn.XmlNode(
        name="get_default_configurationResponse",
        attributes={},
        text=None,
        children=(
            kmscn.XmlNode("result", {}, "SUCCESS", ()),
            kmscn.XmlNode(
                "scan_image_configuration",
                {},
                None,
                (
                    kmscn.XmlNode(
                        "color_selection",
                        {},
                        "FULL_COLOR",
                        (),
                    ),
                    kmscn.XmlNode(
                        "scan_resolution",
                        {},
                        "RESOLUTION_300X300",
                        (),
                    ),
                    kmscn.XmlNode(
                        "duplex_mode",
                        {},
                        "SIMPLEX",
                        (),
                    ),
                ),
            ),
            kmscn.XmlNode(
                "original_configuration",
                {},
                None,
                (kmscn.XmlNode("original_size", {}, "A4", ()),),
            ),
            kmscn.XmlNode(
                "output_image_configuration",
                {},
                None,
                (
                    kmscn.XmlNode(
                        "image_file_format",
                        {},
                        "RAW",
                        (),
                    ),
                ),
            ),
        ),
    )

    def test_start_scan_uses_defaults_and_operation_id(self):
        payload, headers = kmscn.build_start_scan_request(
            "17",
            self.CONFIGURATION,
        )
        text = payload.decode("utf-8")
        self.assertIn("<kmscn:operation_id>17</kmscn:operation_id>", text)
        self.assertIn(
            "<kmscn:color_selection>FULL_COLOR</kmscn:color_selection>",
            text,
        )
        self.assertIn(
            "<kmscn:image_file_format>RAW</kmscn:image_file_format>",
            text,
        )
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.SCAN_NAMESPACE}/start_scan"',
        )

    def test_configuration_replace_preserves_tree(self):
        changed = kmscn.replace_configuration_value(
            self.CONFIGURATION,
            "image_file_format",
            "JPEG",
        )
        self.assertEqual(changed.name, self.CONFIGURATION.name)
        self.assertEqual(changed.children[-1].children[0].text, "JPEG")

    def test_multiple_configuration_replacements_are_serialized(self):
        changed = kmscn.replace_configuration_value(
            self.CONFIGURATION,
            "scan_resolution",
            "RESOLUTION_200X200",
        )
        changed = kmscn.replace_configuration_value(
            changed,
            "duplex_mode",
            "DUPLEX",
        )
        payload, _ = kmscn.build_start_scan_request("18", changed)
        text = payload.decode("utf-8")
        self.assertIn(
            "<kmscn:scan_resolution>RESOLUTION_200X200</kmscn:scan_resolution>",
            text,
        )
        self.assertIn(
            "<kmscn:duplex_mode>DUPLEX</kmscn:duplex_mode>",
            text,
        )

    def test_missing_field_is_inserted_in_official_order(self):
        changed = kmscn.set_configuration_value(
            self.CONFIGURATION,
            "continuous_scan_mode",
            "ON",
        )
        text = kmscn._render_xml_node(changed)
        self.assertLess(
            text.index("<kmscn:scan_resolution>"),
            text.index("<kmscn:continuous_scan_mode>"),
        )
        self.assertLess(
            text.index("<kmscn:continuous_scan_mode>"),
            text.index("<kmscn:duplex_mode>"),
        )
        self.assertEqual(text.count("continuous_scan_mode"), 2)


class SessionResponseTests(unittest.TestCase):
    MIME_RESPONSE = b"""--test-boundary\r
Content-Type: application/xop+xml; charset=utf-8; type="application/soap+xml"\r
Content-Transfer-Encoding: binary\r
Content-ID: <SOAP-ENV:Envelope>\r
\r
<?xml version="1.0" encoding="UTF-8"?>\n
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation" xmlns:xop="http://www.w3.org/2004/08/xop/include">\n
<SOAP-ENV:Body><kmscn:retrieve_imageResponse><kmscn:result>SUCCESS</kmscn:result><kmscn:file_type>RAW</kmscn:file_type><kmscn:file_size>3</kmscn:file_size><kmscn:image_data><xop:Include href="cid:id1"/></kmscn:image_data></kmscn:retrieve_imageResponse></SOAP-ENV:Body>\n
</SOAP-ENV:Envelope>\r
--test-boundary\r
Content-Type: image/x-raw\r
Content-ID: <id1>\r
\r
\x00\x7f\xff\r
--test-boundary--\r
"""

    def test_multipart_xop_image_is_extracted(self):
        result = kmscn.parse_scan_response(
            self.MIME_RESPONSE,
            operation="retrieve_image",
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.2",
            content_type='multipart/related; boundary="test-boundary"',
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "SUCCESS")
        self.assertEqual(result.file_type, "RAW")
        self.assertEqual(result.file_size, 3)
        self.assertEqual(result.body, b"\x00\x7f\xff")

    def test_all_get_complete_is_a_successful_terminal_state(self):
        response = b"""<SOAP-ENV:Envelope
 xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body><kmscn:retrieve_imageResponse>
  <kmscn:result>ALL_GET_COMPLETE</kmscn:result>
 </kmscn:retrieve_imageResponse></SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        result = kmscn.parse_scan_response(
            response,
            operation="retrieve_image",
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.2",
            content_type="application/soap+xml; charset=utf-8",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "ALL_GET_COMPLETE")

    def test_continue_scan_is_a_successful_pending_state(self):
        response = b"""<SOAP-ENV:Envelope
 xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope"
 xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation">
 <SOAP-ENV:Body><kmscn:retrieve_imageResponse>
  <kmscn:result>CONTINUE_SCAN</kmscn:result>
 </kmscn:retrieve_imageResponse></SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        result = kmscn.parse_scan_response(
            response,
            operation="retrieve_image",
            endpoint="http://192.0.2.1:9090/scan",
            http_status=200,
            soap_version="1.2",
            content_type="application/soap+xml; charset=utf-8",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "CONTINUE_SCAN")
        self.assertIsNone(result.image_data)

    def test_retrieve_rejects_nonpositive_response_limit(self):
        with self.assertRaisesRegex(ValueError, "must be positive"):
            kmscn.retrieve_image(
                "http://192.0.2.1:9090/scan",
                "17",
                max_response_bytes=0,
            )


class NetworkTests(unittest.TestCase):
    class Response:
        status = 200

        def read(self, limit):
            return ResponseTests.RESPONSE

        def getheaders(self):
            return [("Content-Type", "text/xml; charset=utf-8")]

    class Connection:
        def __init__(self):
            self.request = None
            self.headers = []
            self.body = None
            self.closed = False

        def putrequest(self, method, path, skip_accept_encoding):
            self.request = (method, path, skip_accept_encoding)

        def putheader(self, name, value):
            self.headers.append((name, value))

        def endheaders(self, body):
            self.body = body

        def getresponse(self):
            return NetworkTests.Response()

        def close(self):
            self.closed = True

    def test_probe_posts_the_read_only_operation(self):
        endpoint = f"http://192.0.2.1:9090{kmscn.SCAN_PATH}"
        with mock.patch.object(
            kmscn.http.client, "HTTPConnection", return_value=self.Connection()
        ) as created:
            result = kmscn.probe(endpoint, timeout=1)
        connection = created.return_value
        self.assertEqual(
            connection.request,
            ("POST", kmscn.SCAN_PATH, True),
        )
        headers = dict(connection.headers)
        self.assertEqual(headers["Host"], "192.0.2.1:9090")
        self.assertEqual(headers["User-Agent"], "gSOAP/2.7")
        self.assertEqual(headers["Connection"], "close")
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.GET_SERVICE_INFORMATION_ACTION}"',
        )
        self.assertIn(b"get_service_informationRequest", connection.body)
        self.assertTrue(connection.closed)
        self.assertTrue(result.ok)

    def test_capability_probe_posts_only_get_capability(self):
        endpoint = f"http://192.0.2.1:9090{kmscn.SCAN_PATH}"
        with mock.patch.object(
            kmscn.http.client,
            "HTTPConnection",
            return_value=self.Connection(),
        ) as created:
            result = kmscn.probe_capability(endpoint, timeout=1)
        connection = created.return_value
        headers = dict(connection.headers)
        self.assertIn(b"get_capabilityRequest", connection.body)
        self.assertNotIn(b"start_scanRequest", connection.body)
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.GET_CAPABILITY_ACTION}"',
        )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.missing_capabilities,
            kmscn.CAPABILITY_ENTRY_NAMES,
        )

    def test_truncated_chunked_response_is_a_structured_error(self):
        class TruncatedResponse:
            status = 200

            def read(self, limit):
                raise kmscn.http.client.IncompleteRead(b"partial", 10157)

            def getheaders(self):
                return [("Content-Type", "application/soap+xml")]

        connection = self.Connection()
        connection.getresponse = lambda: TruncatedResponse()
        with mock.patch.object(
            kmscn.http.client,
            "HTTPConnection",
            return_value=connection,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "ended before its declared length",
            ):
                kmscn._post_response(
                    f"http://192.0.2.1:9090{kmscn.SCAN_PATH}",
                    b"request",
                    {},
                    timeout=1,
                    insecure=False,
                )
        self.assertTrue(connection.closed)


class PreflightTests(unittest.TestCase):
    def test_service_failure_stops_before_capability(self):
        service_result = mock.Mock(ok=False)
        with mock.patch.object(
            kmscn,
            "probe",
            return_value=service_result,
        ), mock.patch.object(kmscn, "probe_capability") as capability:
            result = kmscn.preflight(
                f"http://192.0.2.1:9090{kmscn.SCAN_PATH}"
            )
        self.assertFalse(result.ok)
        self.assertIs(result.service_information, service_result)
        self.assertIsNone(result.capability)
        self.assertEqual(result.failed_stage, "service_information")
        capability.assert_not_called()

    def test_service_success_then_capability(self):
        service_result = mock.Mock(ok=True)
        capability_result = mock.Mock(ok=True)
        with mock.patch.object(
            kmscn,
            "probe",
            return_value=service_result,
        ), mock.patch.object(
            kmscn,
            "probe_capability",
            return_value=capability_result,
        ) as capability:
            result = kmscn.preflight(
                f"http://192.0.2.1:9090{kmscn.SCAN_PATH}"
            )
        self.assertTrue(result.ok)
        self.assertIs(result.service_information, service_result)
        self.assertIs(result.capability, capability_result)
        capability.assert_called_once()

    def test_connection_failure_is_structured_and_stops_early(self):
        with mock.patch.object(
            kmscn,
            "probe",
            side_effect=ConnectionResetError("closed without response"),
        ), mock.patch.object(kmscn, "probe_capability") as capability:
            result = kmscn.preflight(
                f"http://192.0.2.1:9090{kmscn.SCAN_PATH}"
            )
        self.assertFalse(result.ok)
        self.assertIsNone(result.service_information)
        self.assertIsNone(result.capability)
        self.assertEqual(result.failed_stage, "service_information")
        self.assertIn("closed without response", result.error)
        capability.assert_not_called()


if __name__ == "__main__":
    unittest.main()
