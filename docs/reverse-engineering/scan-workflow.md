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
本次没有 Windows 运行环境，也没有抓取扫描数据流量；因此“Windows 内部调用链”
属于已验证的静态事实，“设备侧扫描数据使用何种协议”仍属未知。

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

- 设备侧网络扫描的数据通道（TWAIN 驱动内部使用 SOAP、WSD、eSCL 或其他私有
  协议）。
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
采集图像，NetViewer 日志中 `KM-WSDL version` 为空并回退到 SNMP。现阶段不应
基于这些未接入的契约编写扫描触发实现。下一步仍是取得 Windows TWAIN 驱动的
真实流量，或取得安装包中的 `Ns1815TWGN.DLL` 做静态/动态分析。

## 7. 对 Linux 实现的含义

不能直接复用 Windows TWAIN DLL。可行的后续路线：

1. 先在设备上验证是否存在 eSCL（`/eSCL/ScannerCapabilities`）或 WSD Scan
   服务；这需要设备 Web 服务可达。
2. 若设备只支持 TWAIN，则需要在 Linux 上寻找同型号的 SANE backend，或通过
   Windows 侧抓包确认 TWAIN 驱动实际使用的网络协议。
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
