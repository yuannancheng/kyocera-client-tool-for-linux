import unittest
from unittest import mock

from kyocera_monitor import kmscn


class RequestTests(unittest.TestCase):
    def test_soap_11_request_matches_driver_operation(self):
        payload, headers = kmscn.build_request("1.1")
        text = payload.decode("utf-8")
        self.assertIn(
            'xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"',
            text,
        )
        self.assertIn(
            "<kmscn:get_service_informationRequest/>",
            text,
        )
        self.assertEqual(headers["Content-Type"], "text/xml; charset=utf-8")
        self.assertEqual(
            headers["SOAPAction"],
            f'"{kmscn.GET_SERVICE_INFORMATION_ACTION}"',
        )

    def test_soap_12_uses_soap_action_media_parameter(self):
        payload, headers = kmscn.build_request("1.2")
        self.assertIn(
            b"http://www.w3.org/2003/05/soap-envelope",
            payload,
        )
        self.assertEqual(
            headers["Content-Type"],
            "application/soap+xml; charset=utf-8; "
            f'action="{kmscn.GET_SERVICE_INFORMATION_ACTION}"',
        )
        self.assertNotIn("SOAPAction", headers)

    def test_rejects_unknown_soap_version(self):
        with self.assertRaises(ValueError):
            kmscn.build_request("1.0")

    def test_capability_request_matches_driver_operation(self):
        payload, headers = kmscn.build_operation_request("get_capability")
        text = payload.decode("utf-8")
        self.assertIn("<kmscn:get_capabilityRequest/>", text)
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

    def test_missing_capability_is_explicit_and_not_success(self):
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
        self.assertFalse(result.ok)
        self.assertEqual(
            result.missing_capabilities,
            ("original_configuration_capability",),
        )


class NetworkTests(unittest.TestCase):
    class Response:
        status = 200

        def read(self, limit):
            return ResponseTests.RESPONSE

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
