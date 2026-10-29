# 扫描与 Push Scan 工作流

## 1. 范围与样本

本文记录 KYOCERA Client Tool 中与本机扫描相关的静态证据，重点是
`KMSTMNW.exe` 的 Push Scan 入口、`KMSCN` 组件和 TWAIN 数据源。

本次分析样本：

| 文件 | SHA-256 | 说明 |
| --- | --- | --- |
| `Kyocera/ClientTool/KMSTMNW.exe` | `59f39e6749d1590cb687a092fe097c5c6cfbd5cebbe1be9bfe440baef89a5fa4` | 状态监视/设备管理 GUI |
| `Kyocera/ClientTool/KMSCN/KMSCNPUS.exe` | `0a2cd14a87add56199c41a85b1f1118af5de11dd0f93659e38f2ae3fa6573b02` | Push Scan 启动器 |
| `Kyocera/ClientTool/KMSCN/KMSCNSET.dll` | `7c6a19e49d9341e3e50ff4019971ffbb0c343701a4d52de6caa902fc9b0381d9` | Quick Scan 设置库 |
| `Kyocera/ClientTool/KMSCN/KMSCNFOL.exe` | `19b144be1b52ad9f68f9729d984ab4c51322f04dce91f1f9fa4ce6f4ee4185b5` | Scan to Folder 应用 |

分析方式：Ghidra 12.1.4 headless 静态反编译 + PE 导入表/字符串核对。
2026-10-29 又取得京瓷官方发布的 `Kyocera TWAIN Driver GX 2.1.4412`，
补齐了网络 TWAIN 驱动栈。本文没有 Windows 运行环境，也没有抓取扫描数据
流量；因此 Windows 内部调用链和客户端协议构造属于已验证的静态事实，设备
实际接受的 SOAP 版本、认证前置条件和完整响应仍待真机验证。

## 2. Push Scan 调用链（已验证）

`KMSTMNW.exe` 的 `FUN_00450f20`（日志字符串标记为 `OnRecvPushScan`）处理
Push Scan 通知。其关键行为：

1. 从通知数据中读取接口类型和预设地址：
   - 类型 `1` 表示 `NETWORK`，其他值表示 `USB`；
   - 地址分支包括 IPv4、IPv6 和 HostName；
   - 只有当预设地址与本机地址匹配时，才继续处理。
2. 检查当前 Client Tool 的接口类型与预设接口类型是否一致；不一致时记录
   `NOT PROCESSING PRESET[...] CLIENT TOOL[...]` 并退出。
3. 调用 `FUN_00442110(".\\KMSCN\\KMSCNPUS.EXE")` 检查文件是否存在。
4. 若预设模式已启用，则执行：

```text
.\KMSCN\KMSCNPUS.EXE <presetNo>
```

其中 `<presetNo>` 来自对象偏移 `+0x2e810`。启动使用 `ShellExecuteExW`，
参数为十进制预设号。

`KMSCNPUS.exe` 的入口 `FUN_00401000` 进一步调用：

```text
argv[1] -> KMQSEnablePreset(index)
        -> CreateProcessW("KMSCNFOL.exe /D")
        -> WaitForSingleObject(...)
        -> KMQSDisablePreset()
```

这段控制流直接出现在 `analysis/decompiled/KMSCNPUS/c/00401000_FUN_00401000.c`。
`KMQSEnablePreset` 和 `KMQSDisablePreset` 从 `KMSCNSET.DLL` 导入。

因此可以确认：

- Push Scan 的预设入口最终启动的是 **Scan to Folder** 可执行文件
  `KMSCNFOL.exe`，命令行为 `/D`。
- `KMSCNPUS.exe` 只负责启用/禁用预设并等待扫描应用退出，本身不实现扫描传输。

## 3. Quick Scan 设置存储

`KMSCNSET.dll` 的 `KMQSEnablePreset`（`0x100026f0`）接受 `0 <= index <= 30`
的预设号，并调用 `FUN_10007610` 写入：

```ini
[Globals]
Preset=<index>
```

`KMQSDisablePreset`（`0x10002720`）把 `Preset` 写回 `-1`。

文件路径由 `FUN_10005dd0` 选择，代码先调用 `GetVersionExW`：

| 系统版本判断 | 基目录 | 最终路径 |
| --- | --- | --- |
| `dwMajorVersion == 5` | `CSIDL_APPDATA` (`0x1a`) | `%APPDATA%\Kyocera\KM_TWAIN2\QUICKSCN.ini` |
| `dwMajorVersion == 6` | `CSIDL_COMMON_DOCUMENTS` (`0x2e`) | `%PUBLIC%\Documents\Kyocera\KM_TWAIN2\QUICKSCN.ini` |
| 其他 | `GetWindowsDirectoryW` | `%WINDIR%\Kyocera\KM_TWAIN2\QUICKSCN.ini` |

注意：程序未在 manifest 中声明 Windows 10 兼容性时，`GetVersionExW` 可能仍报告
6.x；实际落到哪一个目录需要在 Windows 上复核。这里记录的是代码分支，不是对
本机目录的实测结果。

`KMSCNSET.dll` 还导出 `KMQSGet`、`KMQSSet`、`KMQSAddSource`、
`KMQSMakeDefaultSource`、`KMQSRestoreDefaults` 等接口；目前只确认了导出名和
预设写入路径，未逐个还原参数结构。

## 4. TWAIN 数据源

`KMSTMNW.exe` 的 `FUN_00449ca0`（`ShowScanPreferences`）根据接口类型选择
TWAIN 动态库：

```text
USB:     %WINDIR%\TWAIN_32\KMTWAIN\NS1815TW3.DLL
NETWORK: %WINDIR%\TWAIN_32\KMTWAIN\Ns1815TWGN.DLL
```

随后调用 `LoadLibraryW`，再通过 `GetProcAddress(..., "fnOpenSettingsUI")`
打开设置界面。这些 DLL 不在当前 `Kyocera/ClientTool` 样本目录中，而由
`Kyocera/Twain.pnf` 安装包安装到 `%WINDIR%\TWAIN_32\KMTWAIN`。

`KMSCNSET.dll` 自身不静态链接 TWAIN，而是运行时加载 `TWAIN_32.DLL`，
取得 `DSM_Entry`。`KMQSGetDefaultSourceName` 中的 TWAIN 身份字符串为：

```text
Kyocera Mita Corporation
Kyocera TWAIN Driver
QuickScanSettings
```

这说明扫描图像采集走 TWAIN 数据源，而不是 Client Tool 自己实现的一套
网络扫描协议。`KMSCNFOL.exe` 的字符串还包含 `Scan to Folder`、
`KM_QuickScan_Mutex`、`Scanning in progress...` 以及
`C:\Logs\LogService\ScanOutput` 日志路径。

2026-10-29 的后续分析确认，网络 TWAIN 数据源内部使用 KM-WSDL/gSOAP
客户端（第 9 节）；这不改变“Client Tool 通过 TWAIN 采集”的上层调用关系。

### 4.1 USB 分支（静态证据）

`KMSTMNW.exe` 的 Push Scan 入口 `FUN_00450f20` 用接口类型区分网络与 USB：

- `local_10[0] == 1` 表示网络，其他值表示 USB；
- 对 USB 分支，只有本地检查 `FUN_004463f0(...) != 0` 时才继续；否则记录
  `[PSCN] NOT PROCESSING PRESET[USB] CLIENTTOOL[NETWORK]`；
- 对网络分支，若本地检查为真则记录
  `[PSCN] NOT PROCESSING PRESET[NETWORK] CLIENT TOOL[USB]`；
- `ShowScanPreferences`（`FUN_00449ca0`）在端口名以 `USB` 开头时加载
  `%WINDIR%\TWAIN_32\KMTWAIN\NS1815TW3.DLL`，否则加载
  `Ns1815TWGN.DLL`。

这说明 USB 扫描的图像采集仍走 Kyocera TWAIN 数据源；本次没有证据表明
`KMSTMNW.exe` 直接通过 USB 批量端点发送扫描命令。打印/状态路径的语言监视器
链路见 `docs/reverse-engineering/usb-path.md`。

## 5. 证据等级与未确认项

已验证：

- `KMSTMNW.exe` 中存在 Push Scan 入口、预设号校验和
  `KMSCNPUS.EXE <presetNo>` 启动命令。
- `KMSCNPUS.exe` 调用 `KMQSEnablePreset`、启动 `KMSCNFOL.exe /D`、等待、
  再调用 `KMQSDisablePreset`。
- `KMSCNSET.dll` 的 `QUICKSCN.ini` 写入位置与 `Preset` 键。
- TWAIN 库路径、`fnOpenSettingsUI` 导出名和 TWAIN 数据源身份字符串。

较高可信度：

- `KMSCNFOL.exe` 是 Push Scan 的 Scan-to-Folder 执行端。
- 扫描图像实际通过 Kyocera TWAIN 数据源采集。

未知：

- 早期样本中设备侧网络扫描的数据通道未知；2026-10-29 已由官方驱动补齐
  KM-WSDL 客户端证据，只剩真机协商和响应验证，见第 9 节。
- `KMSCNFOL.exe` 如何把 TWAIN 图像保存到目标目录，以及是否还有中间服务。
- Push Scan 通知消息的完整字段布局；目前只还原了消费端读取的偏移和分支。
- 当前 Linux 主机能否通过 SANE/eSCL/WSD 直接触发同类扫描。

## 6. 网络扫描协议实测（2026-10-18）

对 `192.168.0.220` 做了只读端口与服务探测，目标是确认 Linux 能否绕过 TWAIN，
直接使用 WSD、eSCL 或 IPP Scan。

### 6.1 端口

```text
80/tcp    open  http (gSOAP/2.7)
515/tcp   open  printer (LPR)
5357/tcp  open  wsdapi
9090/tcp  open  (未识别)
9100/tcp  open  jetdirect
631/tcp   closed
```

`631/tcp` 关闭，因此本机没有 IPP/IPP Scan 入口。

### 6.2 WS-Discovery 与 WSD 元数据

`tools/wsd_probe.py` 向 `239.255.255.250:3702` 和目标单播发送标准 WS-Discovery
`Probe`：

- 探测 `print:PrintDeviceType` 时，设备返回
  `XAddrs=http://192.168.0.220:5357/DeviceService/`，类型为
  `devprof:Device print:PrintDeviceType`。
- 探测 `scan:ScannerServiceType` 时，连续 3 次（每次 6 秒）均无响应。
- 对 `http://192.168.0.220:5357/DeviceService/` 发送只读 WS-Transfer `Get`
  成功，元数据列出：
  - `ThisDevice`：型号、固件、序列号（本文脱敏）；
  - `ThisModel`：`MA2000w`；
  - 唯一托管服务：`http://192.168.0.220:5357/WSDPrinter/`，
    类型 `print:PrinterServiceType`。

结论（已验证）：该设备当前只发布 **WSD 打印**服务，没有发布 WSD 扫描服务。
WS-Discovery 包络中虽然出现 `kmscn` 命名空间，但元数据没有对应的扫描服务。

### 6.3 eSCL 与 KM-WSDL

- `GET /eSCL/ScannerCapabilities`、`/eSCL/ScannerStatus`、`/eSCL/ScanJobs`
  在 80 端口均得到 0 字节响应（连接被关闭）。
- 80 端口 `OPTIONS *` 返回 `405 Method Not Allowed` 和 gSOAP Fault；对
  KM-WSDL 路径的 GET/POST 仍为空响应。
- 9090 端口可建立 TCP 连接，但 HTTP GET 空响应，KM-WSDL `get_scanner_information`
  POST 在 5 秒内无任何响应。

由于 80 端口对普通 GET 一概关闭，不能仅凭 eSCL 路径的空响应断言“设备不实现
eSCL”；可以确认的是：本次没有得到任何 eSCL 或 KM-WSDL 响应，也没有拿到 WSDL。

### 6.4 对扫描结论的影响

- 已验证：MA2000w 当前不发布 WSD 扫描服务；`631/tcp` 关闭。
- 未验证：eSCL 是否存在；80 端口服务是否被访问控制或配置关闭。
- 仍未确认：Kyocera TWAIN 驱动实际使用的网络协议。
- 现阶段不能基于 WSD/eSCL 编写 Linux 扫描实现；优先在 Windows 上抓取 TWAIN
  驱动的网络流量，或在设备 Web 设置中确认“WSD 扫描”是否被禁用。

### 6.5 复现

```bash
nmap -Pn -p 80,515,5357,9090,9100,631 --open 192.168.0.220
python3 tools/wsd_probe.py 192.168.0.220 --type printer --timeout 5
python3 tools/wsd_probe.py 192.168.0.220 --type scanner --timeout 6
```

WS-Transfer `Get` 的请求体与响应已在分析过程中核对；文档只保留结构结论，不保存
包含真实序列号和主机名的原始响应。

### 6.6 NetViewer .NET 扫描 SOAP 契约（静态，未接入）

为确认能否绕过 TWAIN、直接从 SOAP 触发扫描，本次对
`Kyocera/NetViewer/KNV/bin/Core.CoreServices.dll` 做了只读托管元数据检查。
样本 SHA-256 为
`fe7b66c0c1a67b002f0d739db294ddea87a9c4d10b8357cf9e2dffdbb25d3645`，
MVID 为 `88f1c6b0-ab4d-49dd-bbfc-e044086bd4bb`，目标框架 .NET Framework 4.8。
检查使用 REA 的 `inspect_managed_artifact` / `inspect_managed_members`，
没有加载 CLR、执行程序集或访问设备。

该程序集确实包含完整的扫描作业数据契约，命名空间为
`Kmnv.Core.Services.Soap.JobOperation.ScanOperation`。类型名给出的操作序列为：

```text
get_service_information
get_capability
get_default_configuration
open_session
start_scan
retrieve_image
cancel_scan
close_session
```

请求类型及字段（字段名来自属性 getter，`*Specified` 是 SOAP 可选字段标记）：

| 请求类型 | 字段 |
| --- | --- |
| `open_sessionRequest` | `information`（`HOST_INFORMATION_ENTRY`：`type`、`data`） |
| `start_scanRequest` | `operation_id`、`scan_image_configuration`、`original_configuration`、`output_image_configuration` |
| `retrieve_imageRequest` | `operation_id`、`operation_type`、`operation_typeSpecified` |
| `close_sessionRequest` | `operation_id` |

`cancel_scanRequest`、`get_capabilityRequest` 和
`get_default_configurationRequest` 类型也存在，本次未展开其字段；在没有调用方
证据前，它们同样不能作为已实现的设备接口。

三个配置结构的字段为：

- `SCAN_IMAGE_CONFIGURATION_ENTRY`：`color_selection`、`exposure_level`、
  `background_exposure_adjust`、`sharpness`、`scan_resolution`、`border_erase`、
  `continuous_scan_mode`、`duplex_mode`、`binding`、`multi_page_form`、
  `original_size_mixed`、`prevent_bleed_through`、`sharpness_emphasis`、
  `sharpness_mode`、`ocr`、`silent_mode`。
- `ORIGINAL_CONFIGURATION_ENTRY`：`original_image`、`original_size`、
  `original_orientation`、`original_custom_size`、`original_placement`。
- `OUTPUT_IMAGE_CONFIGURATION_ENTRY`：`image_file_format`、`sending_size`、
  `image_compress_level`、`zoom`、`centering`、`encrypt_pdf`、`file_name`、
  `file_separation`、`pdf_type`、`bates_stamp`、
  `high_compression_pdf_quality`。

**关键否定证据（已验证）：** 这些类型没有对应的
`ScanOperationService` 代理类；`Core.CoreServices.dll` 中继承
`SoapClientService`/`SoapHttpClientProtocol` 的服务类包括计数器、设备设置、
任务状态等，但没有扫描服务。对 `Kyocera/NetViewer` 全部 DLL 做字符串检索：

```text
Kmnv.Core.Services.Soap.JobOperation.ScanOperation
start_scanRequest
retrieve_imageRequest
```

只有 `Core.CoreServices.dll` 自身命中；没有任何其他随附程序集引用这些类型。
因此：

- 可以确认“程序集里存在扫描 SOAP 数据契约”。
- **不能**据此确认 Client Tool 或 NetViewer 实际通过 SOAP 执行扫描。
- 不能从这些契约反推出扫描端点 URL、SOAPAction 或认证前置条件；通用
  `SoapClientService` 的构造函数接收完整 URL 字符串，真正的 URL 由调用方
  传入，而扫描调用方不在随附二进制中。

这与已观察到的 Client Tool 路径一致：原生 `KMSTMNW.exe` 通过 TWAIN 数据源
采集图像，NetViewer 日志中 `KM-WSDL version` 为空并回退到 SNMP。2026-10-29
已从官方 TWAIN 安装包取得 `Ns1815TWGN.DLL`，并确认其网络实现使用 KM-WSDL，
详见第 9 节。NetViewer 中这组未被引用的契约仍不能作为 NetViewer 扫描入口。

## 7. 对 Linux 实现的含义

不能直接复用 Windows TWAIN DLL。可行的后续路线：

1. 先在设备上验证是否存在 eSCL（`/eSCL/ScannerCapabilities`）或 WSD Scan
   服务；这需要设备 Web 服务可达。
2. 若设备只支持 TWAIN，则需要在 Linux 上寻找同型号的 SANE backend，或通过
   Windows 侧抓包确认 TWAIN 驱动实际使用的网络协议。该静态空白现已由第 9
   节补齐：网络 TWAIN 使用 KM-WSDL，不再需要把 WSD/eSCL 当作唯一候选。
3. 在协议未确认前，不在 Linux 端实现“发送扫描预设”或“伪造 Push Scan”功能。
4. 现有 `kyocera_monitor` 仍只做只读状态查询，不包含扫描能力。

## 8. 复现

```bash
env XDG_CONFIG_HOME=/tmp/ghidra_config \
  .tools/ghidra_12.1.4_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra_proj KMSTMNW \
  -import Kyocera/ClientTool/KMSTMNW.exe \
  -scriptPath tools/ghidra_scripts \
  -postScript DecompileProgram.java analysis/decompiled/KMSTMNW \
  -deleteProject
```

对 `KMSCNPUS.exe` 和 `KMSCNSET.dll` 使用同一命令，替换导入路径和输出目录即可。
生成目录 `analysis/` 不纳入版本控制。

## 9. 网络 TWAIN 驱动栈与 KM-WSDL（2026-10-29）

### 9.1 样本取得与完整性

此前仓库只含 `Kyocera/Twain.pnf`，没有其中列出的 TWAIN 二进制。2026-10-29
从京瓷官方下载中心取得与本机清单匹配的
`MA 2000\W Series TWAIN Driver (2.1.4412)`：

- 官方页面：
  <https://www.kyoceradocumentsolutions.us/en/support/downloads.name-L3VzL2VuL21mcC9NQTIwMDBX.html>
- 安装包：`Kyocera_TWAINDriver_2.1.4412.exe`
- 安装包 SHA-256：
  `92912ad89d780bfe39fa4b82d9d469ea9eef4c5b74de7fb97f693103451e801e`
- 内嵌 `KmSFX.zip` SHA-256：
  `e7691763e81a9765ade115ea80246ce9969e13907cd65276420f60dcb549fb54`

安装包使用自定义自解压 PE；无需执行安装器，可从 PE 资源
`RT_RCDATA/1` 取出内嵌 ZIP。核心成员已解出到被忽略的
`analysis/local-only/twain-2.1.4412/Scanner/TWAIN/`：

| 文件 | SHA-256 |
| --- | --- |
| `Ns1815TWGN.dll` | `b277ff4b1bf31f0cc39b63fc8c5fbdd4770a44261cadaddb102f4d9517cfae09` |
| `KMNETSCN3.dll` | `99dcd56e9f1948066e13f2136b0cd711e3bf1303e023d405d595c7e135c4a29b` |
| `KMSCNAPI.dll` | `d3e276ebe284351e46549fc1c5145c4241fa41e70f4aca306a5abc94b20f2d7a` |
| `KMWSDLTWAING.ds` | `b054e5daf8adae18ac5e63c1885e21231a492b9500c2ce7d18e391d9fad45d5c` |

这些第三方二进制只保存在本地分析目录，不进入公开树。

### 9.2 驱动调用链（已验证）

网络 TWAIN 的调用层级是：

```text
Ns1815TWGN.dll
  -> LoadLibrary("%WINDIR%\\TWAIN_32\\KMTWAIN\\KMNETSCN3.dll")
  -> KMNETSCN3.dll LoadLibrary("KMSCNAPI.dll")
  -> KMSCNAPI.dll 实现 KM-WSDL/gSOAP 网络客户端
```

`KMNETSCN3.dll` 在初始化时解析以下 `KMSCNAPI.dll` 导出：

```text
KMSCNInit
KMSCNGetServiceInfo
KMSCNGetCapability
KMSCNOpenSession
KMSCNStartScan
KMSCNRetrieveImage
KMSCNCancelScan
KMSCNCloseSession
KMSCNExit
```

`KmNetScnThread` 的实际顺序是：

1. `KMSCNGetServiceInfo`，最多重试一次。
2. 检查型号信息是否属于该驱动支持的设备。
3. `KMSCNGetCapability`，并检查自动输稿器是否受支持。
4. 建立扫描子线程；收到扫描请求后调用 `KMSCNOpenSession`。
5. 调用 `KMSCNStartScan`。
6. 循环调用 `KMSCNRetrieveImage`，直到收到末页标记。
7. 调用 `KMSCNCloseSession`；取消路径调用 `KMSCNCancelScan`。

这说明网络扫描并不依赖 WSD Scan 或 eSCL，而是 TWAIN 数据源内部的私有
KM-WSDL 接口。

### 9.3 地址、端口和 TLS 路由（已验证的静态事实）

`Ns1815TWGN.dll` 从 TWAIN 配置读取 `ScannerAddress` 和 `SSL`：

- `SSL=1`：地址写成 `https://<host>`，IPv6 写成 `https://[<host>]`。
- `SSL=0`：地址写成 `http://<host>`，IPv6 写成 `http://[<host>]`。

`KMSCNAPI.dll` 在初始化时根据输入 URL 是否为 HTTPS 选择端口：

| 传输 | 端口 | 根路径 |
| --- | --- | --- |
| HTTP | `9090` | `/ws/km-wsdl/` |
| HTTPS | `9091` | `/ws/km-wsdl/` |

三个服务路径为：

```text
/ws/km-wsdl/job/scan_operation
/ws/km-wsdl/security/authentication_authorization
/ws/km-wsdl/information/device_information
```

扫描客户端使用的操作与 SOAP action 为：

```text
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/get_service_information
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/get_capability
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/get_default_configuration
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/open_session
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/start_scan
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/retrieve_image
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/cancel_scan
http://www.kyoceramita.com/ws/km-wsdl/job/scan_operation/close_session
```

`KMSCNAPI.dll` 导入 `WININET.dll`，同时静态链接 gSOAP 2.7 与 OpenSSL。
内部初始化字段不能直接等同于实际线协议。用 32 位 MinGW 诊断宿主加载官方
`KMSCNAPI.dll` 后捕获到：实际扫描请求使用 **SOAP 1.2**，Content-Type 为
`application/soap+xml; charset=utf-8`，同时仍发送带引号的 SOAPAction。
因此 Linux 实现默认使用 SOAP 1.2；SOAP 1.1 仅保留为兼容性选项。

HTTP 传输层使用以下已还原的 gSOAP 2.7 特征：

- 请求行为 `POST /ws/km-wsdl/job/scan_operation HTTP/1.1`，`Host` 包含
  非默认端口。
- `User-Agent` 固定为 `gSOAP/2.7`（`.rdata:0x10159634`）。
- 实际 SOAP 1.2 使用 `application/soap+xml; charset=utf-8` 和带引号的
  `SOAPAction: "<action>"`；后者由 `0x1009be40` 附近的格式化逻辑生成。
- 显式发送 `Content-Length`；非 keep-alive 路径发送 `Connection: close`。
- Linux 探针使用低层 `http.client` 构造这些头部，避免自动附加额外的
  `Accept-Encoding: identity`。
- Envelope 还包含完整的 WS-* namespace 集，以及
  `<SOAP-ENV:Header><wsa:Action>...</wsa:Action></SOAP-ENV:Header>`。
  只发送简化 Envelope 会被设备直接关闭连接。

官方 `get_service_information` 请求体已逐字节复刻：1657 字节，SHA-256
`ae4f8f9a43f2f46a3b76e2a1190dd5990d62d1699aaaeb14ac1264def76f3a0c`。
Linux 构建器使用 `tests/test_kmscn.py` 锁定该结构。

capability 契约的关键静态证据（地址均相对 `KMSCNAPI.dll` 映像基址）：

- `0x1007eee0` 设置 `get_capability` SOAPAction，序列化空的
  `kmscn:get_capabilityRequest`，随后反序列化
  `kmscn:get_capabilityResponse`。
- `0x1003ff80` 在响应中依次查找 `kmscn:result`、
  `kmscn:scan_image_configuration_capability`、
  `kmscn:original_configuration_capability` 和
  `kmscn:output_image_configuration_capability`。
- `0x1003fe00` 进入扫描图像能力子树，并保留后续原稿/输出图像能力所需状态；
  `0x1005b120` 和 `0x1000fcb0` 分别出现在 gSOAP 响应处理与分发路径。

上述函数确认顶层结构，但未对真实 XML 中的数组、可选节点或枚举作额外推断。

### 9.4 只读 Linux 探针

`kyocera_monitor/kmscn.py` 与 `tools/kmscn_probe.py` 只发送
`get_service_information` 或 `get_capability`，不打开扫描会话、不启动扫描、
不取图，也不修改任何设备设置。默认请求为 HTTP 9090 + SOAP 1.2：

```bash
python3 tools/kmscn_probe.py 192.168.0.220
python3 tools/kmscn_probe.py 192.168.0.220 --json
python3 tools/kmscn_probe.py 192.168.0.220 --capability --json
python3 tools/kmscn_probe.py 192.168.0.220 --preflight --json --raw
python3 tools/kmscn_probe.py 192.168.0.220 --https --insecure
python3 tools/kmscn_probe.py 192.168.0.220 --soap-version 1.2
```

探针会检查 HTTP 状态、SOAP Fault、顶层 `result` 以及
`version`/`release_date`/`model_name`。安装包后也可使用
`kyocera-kmscn-probe` 命令。

`--capability` 发送与驱动相同的空 `get_capabilityRequest`，并解析响应中的
三个顶层能力项：

```text
scan_image_configuration_capability
original_configuration_capability
output_image_configuration_capability
```

每个能力项以保留元素名、属性和子节点的树形 JSON 输出。这样可以在真实响应
出现后核对重复值、可选节点和嵌套结构，而不在缺少样本时猜测 XML 数组映射。
非零 `result`、SOAP Fault、非 2xx 状态或非法 XML 均报告为失败；顶层能力项
按设备实际返回保留，缺席项显式列出但不单独判失败。解析器拒绝 DTD/实体声明，
普通响应体上限为 2 MiB，取图响应上限为 64 MiB。

`--preflight` 复刻 `KmNetScnConnect` 经 `KmNetScnThread` 执行的原厂校验顺序：

1. 调用 `KMSCNGetServiceInfo`，失败时最多重试一次。
2. 检查返回型号是否属于该驱动支持范围。
3. 调用 `KMSCNGetCapability`，并读取 ADF/双面等能力位。
4. 两项成功后才允许进入后续 open/start/retrieve/close 会话。

Linux 预检目前实现第 1 和第 3 步；服务信息失败时不会发送 capability。
网络异常同样进入结构化结果，记录 `failed_stage`、异常文本，并将 capability
保持为 `null`。型号接受列表和 ADF/双面解释要在取得真实响应后再补入。

### 9.5 证据等级和待验证项

已验证：

- 官方驱动安装包与内嵌载荷的 SHA-256、成员完整性和核心 DLL 哈希。
- `Ns1815TWGN -> KMNETSCN3 -> KMSCNAPI` 动态加载关系。
- 9090/9091 端口选择、三个 KM-WSDL 服务路径和八个扫描 action。
- 官方真实请求使用 SOAP 1.2、完整 namespace 和 `wsa:Action` Header。
- MA2000w 的 9090 KM-WSDL 在设备睡眠状态下仍可用；官方和 Linux 都不需要
  先手动按面板唤醒。
- 真机 `get_service_information` 返回 `SUCCESS`、版本 `30.0.134.1`、
  发布日期 `2022.08.22`、型号 `MA2000w`。
- MA2000w capability 至少返回
  `scan_image_configuration_capability/duplex_mode=DUPLEX`；另外两个顶层能力
  块可选且本次未返回。
- `get_default_configuration` 返回 FULL_COLOR、300x300、A4、RAW 等默认值。
- 真机会话顺序已验证：
  `open_session -> start_scan -> retrieve_image* -> ALL_GET_COMPLETE -> close_session`。
- `retrieve_image` 使用 XOP multipart；图像生成期间返回
  `IMAGE_CREATING_NOW` 和 0 字节 attachment，必须继续轮询。
- 最终 RAW 为 2496×3520、三颜色平面分带；暗/亮校准块分别为 `8A`
  子类型 `8A/8B`，图像块为 `82/81`。
- 独立 Python 实现已完成 RAW 解析、阴影校正、RGB 合并和 24 位 BMP 输出。

仍未验证：

- HTTPS 9091。本次设备未监听该端口。
- 其他型号、固件或双面/ADF 多页路径的状态和分页语义。
- 官方 KMIP 色彩矩阵与设备色彩管理表的完整等价性；当前独立实现已复刻分带、
  校准均值和阴影校正公式，复杂色彩配置仍需跨设备样本验证。
- 取消扫描和异常中断后的恢复路径。

2026-10-29 真机对照证明：手动“激活”不是必要条件；此前失败来自 SOAP 1.1
简化请求缺少官方 SOAP 1.2 Header 和 namespace，而不是设备睡眠。

### 9.6 独立 Linux 扫描实现

正式实现不依赖 Wine 或官方 DLL：

```bash
python3 tools/kmscn_scan.py 192.168.0.220 \
  --format RAW \
  --output /tmp/kyocera-scan.raw \
  --decoded-output /tmp/kyocera-scan.bmp
```

流程严格按官方观察行为执行：

1. `--preflight`：服务信息和 capability。
2. 读取设备默认配置，不自行编造扫描枚举。
3. 打开会话并取得 `operation_id`。
4. 使用默认配置启动扫描。
5. 反复取图，直到 `ALL_GET_COMPLETE`。
6. 关闭会话。

真机成功样本：RAW 28,275,026 字节；独立解码得到 2496×3520、24 位 BMP，
26,357,814 字节；`close_session=SUCCESS`。

### 9.7 RAW 分带与独立解码

`KMNETSCN3.dll!CScanData::PrepareImageData` 的行为已还原：

- 每个块：4 字节大端长度 + 1 字节命令 + 1 字节子命令 + 1 字节颜色通道
  + 2 字节宽 + 2 字节高 + 数据。
- `8A/8A` 与 `8A/8B` 是每通道暗/亮校准块，官方按列求均值并四舍五入。
- `82/81` 是图像分带；颜色值 `2/3/4` 分别进入三个颜色平面。
- 每像素按官方阴影校正公式归一化：以暗、亮两倍差为分母并截断到 0..255。
- 三个平面按相同总高度合并；MA2000w 为每通道 8 带 × 440 行 = 3520 行。
- 流末尾 `00000004 8282 0db3` 表示页结束。

实现位于 `kyocera_monitor/kmscn_raw.py`。它不加载官方 KMIP DLL，输出标准
24 位 BMP。官方 KMIP 色彩矩阵的复杂路径尚未用非默认色彩配置交叉验证，
目前不得宣称与所有官方画质模式逐像素一致。

### 9.8 复现

提取内嵌 ZIP 的核心命令如下（输出保持在忽略目录）：

```bash
dd if=analysis/local-only/Kyocera_TWAINDriver_2.1.4412.exe \
  of=/tmp/kyocera-twain-payload.bin bs=1 skip=365196 count=16235106
unzip -t /tmp/kyocera-twain-payload.bin
mkdir -p analysis/local-only/twain-2.1.4412
unzip -q /tmp/kyocera-twain-payload.bin 'Scanner/TWAIN/*' \
  -d analysis/local-only/twain-2.1.4412
```

聚焦反编译：

```bash
env XDG_CONFIG_HOME=/tmp/ghidra_config \
  .tools/ghidra_12.1.4_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra_proj KMSCNAPI \
  -import analysis/local-only/twain-2.1.4412/Scanner/TWAIN/KMSCNAPI.dll \
  -scriptPath tools/ghidra_scripts \
  -postScript InspectScanApi.java analysis/decompiled/KMSCNAPI \
  -deleteProject
```
