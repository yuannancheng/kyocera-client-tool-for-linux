# KM-WSDL / SOAP 接口调查

## 1. 结论摘要

此前 TODO 中“反编译 `KMSTMNW.exe` / `ClientTool.dll` 还原 SOAP 设置接口”的
方向需要修正：

- `ClientTool.dll` 不是 SOAP 客户端。它只导出 `CreatePlugin`，导入表也没有
  WinHTTP/WinINet/WS2_32 网络 API。
- `KMSTMNW.exe` 是原生 MFC GUI，扫描设置通过 TWAIN DLL，未静态链接
  WinHTTP/WinINet。
- SOAP 客户端位于 **NetViewer 的 .NET 程序集**：
  `Kyocera/NetViewer/KNV/system/Device.*` 与
  `Kyocera/NetViewer/KNV/bin/Core.CoreServices.dll`。这些程序集还包含
  `127.0.0.1:9090` 的本地服务 URL 和 SOAP 服务包装类型，但本地服务端
  尚未单独验证。
- 历史 NetViewer 日志显示 MA2000w 的 `KM-WSDL version` 为空，登录/轮询回退到
  SNMP；因此 MA2000w 的只读配置不应优先依赖 SOAP。

## 2. 样本

| 文件 | SHA-256 |
| --- | --- |
| `Kyocera/ClientTool/ClientTool.dll` | `eddfa5457bfb987823730aeb641433d55f85c6126e0090876bfa74f879a667f1` |
| `Kyocera/NetViewer/KNV/bin/Core.CoreServices.dll` | `fe7b66c0c1a67b002f0d739db294ddea87a9c4d10b8357cf9e2dffdbb25d3645` |
| `Kyocera/NetViewer/KNV/system/Device.Base/Device.Controllers.DeviceController.dll` | `6987055c27dbd90b4ea0c1dcb1d279a508fc3b23f8125052e9be340ce0a202d1` |
| `Kyocera/NetViewer/KNV/system/Device.Base/Device.Services.DeviceSettings.dll` | `11c23b402e7114b5d68e4e88d9bcea0fae607452f2b8b419ce3b3e68fd593de3` |

`Device.Controllers.DeviceController.dll` 的元数据包含
`Kmnv.Device.Controllers.SOAP.*`、`System.Web.Services.Protocols.SoapHttpClientProtocol`
和 `SoapDocumentMethodAttribute`，确认它是 .NET SOAP 客户端。

## 3. 默认连接参数

`Kyocera/NetViewer/KNV/system/Device.Base/conf/DefaultSettings.xml`：

```xml
<TcpIpPort>9100</TcpIpPort>
<SnmpTimeout>10</SnmpTimeout>
<ReadCommunity>public</ReadCommunity>
<WsdlPort>9090</WsdlPort>
<WsdlTimeout>100</WsdlTimeout>
<UseWSDL>false</UseWSDL>
<UseSSL>true</UseSSL>
```

`Device.Services.DeviceConnection.dll` 的数据库表 `DEV_CONNECTION_KMWSDL`
保存每台设备的 `USE_WSDL`、`WSDL_PORT`、`WSDL_TIMEOUT`、`USE_SSL`。
这说明 WSDL 是可选连接方式，不是所有型号默认启用。

`Device.Controllers.DeviceController.dll` 中出现的默认 URL 为：

```text
http://127.0.0.1:9090/ws/km-wsdl/setting/device_setting
http://127.0.0.1:9090/ws/km-wsdl/setting/panel_setting
```

这些是 NetViewer 进程内/本机服务地址，不能直接当作打印机地址。实际设备地址
由 `DeviceConnection` 根据设备 IP、端口和 `USE_WSDL` 组合决定；本次未还原
完整的 URL 拼接函数。

## 4. KM-WSDL 命名空间与操作

从 `Core.CoreServices.dll` 和 `Device.Controllers.DeviceController.dll`
的字符串/元数据中可直接读出以下命名空间：

```text
http://www.kyoceramita.com/ws/km-wsdl/information/device_information
http://www.kyoceramita.com/ws/km-wsdl/information/device_control
http://www.kyoceramita.com/ws/km-wsdl/information/maintenance
http://www.kyoceramita.com/ws/km-wsdl/status/device_status
http://www.kyoceramita.com/ws/km-wsdl/setting/device_setting
http://www.kyoceramita.com/ws/km-wsdl/setting/panel_setting
http://www.kyoceramita.com/ws/km-wsdl/setting/fax_setting
http://www.kyoceramita.com/ws/km-wsdl/setting/address_book
http://www.kyoceramita.com/ws/km-wsdl/setting/account_management
http://www.kyoceramita.com/ws/km-wsdl/setting/authentication_authorization_setting
http://www.kyoceramita.com/ws/km-wsdl/setting/box_information
http://www.kyoceramita.com/ws/km-wsdl/setting/certificate_management
http://www.kyoceramita.com/ws/km-wsdl/setting/user_list
http://www.kyoceramita.com/ws/km-wsdl/job/job_management
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation
http://www.kyoceramita.com/ws/km-wsdl/job/stored_data_operation
http://www.kyoceramita.com/ws/km-wsdl/log/counter_information
http://www.kyoceramita.com/ws/km-wsdl/security/authentication_authorization
```

`device_setting` 命名空间下直接可见的 SOAP action 包括：

```text
get_service_information
get_system_setting / set_system_setting
get_network_setting / set_network_setting
get_printer_setting / set_printer_setting
get_copy_setting / set_copy_setting
get_job_setting / set_job_setting
```

`scan_operation` 命名空间下可见的字段/消息名包括：

```text
get_scan_setting / set_scan_setting
get_scan_setting_entry
get_table_scan_setting / set_table_scan_setting
get_scanner_information
get_scanner_cover_information
get_scan_image_configuration
get_scan_color_mode / set_scan_color_mode
get_scan_resolution / set_scan_resolution
get_continuous_scan / set_continuous_scan
get_wsd_scan
cancel_scan (cancel_scanRequest / cancel_scanResponse)
```

这些名称证明 NetViewer 具备远程/本地扫描配置和扫描取消的 SOAP 表面；它们
不等于 MA2000w 已启用这些操作，也不等于请求格式已经还原。

### 4.1 扫描数据契约存在，但没有找到调用方

进一步检查 `Core.CoreServices.dll` 的托管元数据，可以还原
`Kmnv.Core.Services.Soap.JobOperation.ScanOperation` 下的请求类型：
`open_sessionRequest`、`start_scanRequest`、`retrieve_imageRequest`、
`cancel_scanRequest` 和 `close_sessionRequest`，以及扫描图像、原稿和输出
配置的字段。字段清单见 `scan-workflow.md` 第 6.6 节。

但该程序集没有 `ScanOperationService` 代理类，其他随附 .NET 程序集也没有
引用 `ScanOperation`、`start_scanRequest` 或 `retrieve_imageRequest`。
因此这些类型只能证明“库中存在扫描 SOAP 数据契约”，不能证明 Client Tool
或 NetViewer 实际使用 SOAP 扫描，也不能据此得到端点 URL 和 SOAPAction。
实际扫描路径仍以 TWAIN 证据为准。

## 5. MA2000w 的实际回退行为

历史日志 `Kyocera/NetViewer/KNV/log/kmnv.log`（含敏感数据，不提交）显示：

```text
LoginController.Login(): Model Name: MA2000w
LoginController.Login(): KM-WSDL version:
LoginController.Login(): Requesting XML_BMSEC_SUPPORT_PARAM...
LoginController.SendGetIntMessage(): OID is 1.3.6.1.4.1.1347.40.26.2.1.4.1
```

`KM-WSDL version` 为空，随后通过 SNMP OID 读取登录/安全参数。这与
`DefaultSettings.xml` 中 `UseWSDL=false` 的默认值一致。

结论（较高可信度）：

- MA2000w 在 NetViewer 中没有协商出可用的 KM-WSDL 版本。
- 设备状态与多数设置读取应优先使用 SNMP；SOAP 设置接口不是该型号的默认路径。
- 不能因为设备开放了 gSOAP 端口就推断设置读写可用。

## 6. 设备 HTTP/SOAP 探测

2026-10-18 对 `192.168.0.220` 的只读探测：

```text
nmap -Pn -p 80,443,8080,9090,9091,9100,161 --open 192.168.0.220
PORT     STATE SERVICE
80/tcp   open  http
9090/tcp open  zeus-admin
9100/tcp open  jetdirect
```

`nmap -sV` 将 80 端口识别为 `gSOAP 2.7`。复现其 `OPTIONS *` 探测后，设备返回：

```text
HTTP/1.1 405 Method Not Allowed
Server: gSOAP/2.7
Content-Type: text/xml; charset=utf-8
...
<SOAP-ENV:Fault>
  <faultcode>SOAP-ENV:Client</faultcode>
  <faultstring>HTTP Error: 405 Method Not Allowed</faultstring>
</SOAP-ENV:Fault>
```

响应信封的命名空间中包含：

```text
xmlns:kmscn="http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation"
```

但以下 POST 请求全部在应用层得到 **0 字节响应**（连接被关闭）：

- SOAP 1.1（`text/xml` + `SOAPAction`）与 SOAP 1.2
  （`application/soap+xml` + `action`）；
- 路径 `/`、`/ws/km-wsdl/setting/device_setting`、
  `/ws/km-wsdl/job/scan_operation`；
- `get_service_information` 与 `get_scanner_information`。

因此：

- 已验证：设备 80 端口存在 gSOAP 2.7 监听器，能返回 SOAP Fault。
- 未知：为什么合法格式的 POST 被静默关闭。可能是 Web 服务未启用、访问控制、
  认证前置条件，或该型号只接受特定来源。
- 未验证：任何真实的 SOAP 请求/响应体、WSDL 内容、登录 token 和设置字段。

WSD `5357/tcp` 只发布打印服务、没有扫描服务；相关探测与结论见
`docs/reverse-engineering/scan-workflow.md` 第 6 节，本文不重复记录。

不应把“空响应”解释为“设备不支持 SOAP”，也不应据此编写配置写入实现。

## 7. 下一步

优先级从高到低：

1. 在 Windows 主机上用 NetViewer 打开单台 MA2000w 的“设备设置”，同时抓取
   HTTP/HTTPS；确认 `UseWSDL` 是否为 false，以及是否完全不发 SOAP。
2. 若设备 Web UI 可用，直接请求
   `/ws/km-wsdl/setting/device_setting?wsdl` 或对应 WSDL 路径，保存 WSDL。
3. 检查设备 Web 服务是否被禁用、是否限制来源 IP、是否需要管理员登录。
4. 对 MA2000w 的只读配置优先扩展 SNMP；SOAP 仅作为其他型号/固件的可选路径。
5. 在拿到真实请求前，不实现 `set_*` 操作，也不发送 `cancel_scan`。

## 8. 复现与工具

静态字符串检查：

```bash
strings -a -el -n 5 \
  Kyocera/NetViewer/KNV/bin/Core.CoreServices.dll |
  rg 'km-wsdl|scan_operation|get_scan_setting|set_scan_setting'
```

设备探测：

```bash
nmap -Pn -sV -p 80 192.168.0.220
printf 'OPTIONS * HTTP/1.1\r\n\r\n' | nc 192.168.0.220 80
```

本次没有保存 WSDL 或 SOAP 响应体；设备对 POST 的空响应不作为协议样本保存。
