# 程序结构与关键函数

## 1. 样本与版本

| 文件 | SHA-256 | 版本/说明 |
| --- | --- | --- |
| `Kyocera/ClientTool/KMSTMVM.exe` | `238440f5e71a113505cbae40eaa4abede578094a3f1705afb83cf9df369df4e3` | 1.4.11.2，`Client Tool main window` |
| `Kyocera/ClientTool/KMSTMNET.exe` | `2994606907429ac7a518bc451287d00a5677df2910042e72ea082b8edab43108` | 1.4.10.17，`Client Tool network component` |
| `Kyocera/ClientTool/KMSTMNW.exe` | `59f39e6749d1590cb687a092fe097c5c6cfbd5cebbe1be9bfe440baef89a5fa4` | 状态监视/设备管理 GUI（版本未单独提取） |
| `Kyocera/ClientTool/ClientTool.dll` | `eddfa5457bfb987823730aeb641433d55f85c6126e0090876bfa74f879a667f1` | Client Tool 包处理 DLL |
| `Kyocera/ClientTool/KDS337110.dat` | `f0eb6f0a1e5e3461234dbc02218786f52e217aca12d824adbb28e51f5a686f37` | MA2000/MA2000w 参数库 |

包版本来自 `Kyocera/ClientTool/ClientTool.pnf`：`11/09/2022, 1.4.11.2`。

所有 PE 均为 32 位 i386。`KMSTMVM.exe` 映像基址 `0x00400000`，入口
`0x00403e47`，GUI 子系统。

## 2. MA2000w 的模型映射（已验证）

- `KMVIDPID.ini`：`[Kyocera MA2000w GX]` → `VID=0x0482`，`PID=0x0d51`。
- `KMSTMNET.ini`：`[MA2000w]` → `KDS337110.DAT`、`Model=2470`、`Scan=1`、
  `Net=1`、`NetworkScan=1`、`WifiSetupTool=1`。
- 实测设备 `192.168.0.220` 对 `@PJL INFO ID` 返回 `"MA2000w"`，MAC
  `00:17:C8:XX:XX:XX`（已脱敏）。

## 3. KMSTMVM.exe 的角色

入口点 `0x00403e47` 调用 CRT `___tmainCRTStartup`（`0x00403cca`），后者以
`(HINSTANCE, hPrevInstance, lpCmdLine, nCmdShow)` 调用 `FUN_00423770`
（`0x00423770`），即实际的 `WinMain`。

`WinMain` 的行为（伪 C 见 `analysis/decompiled/KMSTMVM/c/00423770_FUN_00423770.c`）：

1. 初始化日志 `clienttool_kmstmvm.log`，默认打印机名 `Kyocera FS-1300D KX`。
2. 解析命令行：`/A:`、`/B:`、`/GDI`、`/H`、`/L:`、`/M:`、`/O:`、`/T:`、`/P:`。
3. 创建互斥量 `kyoceramita_kmstmvm300_monitor_<printer>`，防止同一打印机重复实例。
4. 构造 `CMainWindow` 并调用 `FUN_00421fc0` 创建隐藏主窗口。
5. 进入 `GetMessageW`/`DispatchMessageW` 消息循环。

关键函数：

| 地址 | 作用 | 证据 |
| --- | --- | --- |
| `0x00421fc0` | 枚举打印机、匹配 `/P:` 名称、创建隐藏窗口、读取 `KMSTMNET.ini` | 反编译；`EnumPrintersW(6,...)`，要求属性含 `0x800`（双向支持）且不含 `0x4000`（FAX） |
| `0x0041c6b0` | `CVirtualPrn::Create`，区分本地 USB 与网络路径，建立 mailslot | 反编译；本地路径创建 `kmstmvm300\send|notify|recv` 邮箱 |
| `0x0041a3a0` | `Refresh`：发送完整 PJL 查询序列 | 反编译；查询字符串直接可见 |
| `0x0041a960` | 收到 `INFO ID` 后提取型号并补发 `KINTRAYSTATUS` 等查询 | 反编译；按双引号截取型号 |
| `0x0041b290` | 解析状态响应、分类状态码、投递窗口消息 | 反编译；`CODE=`/`CODE2=` 分支 |
| `0x0041af60` | 定时器：刷新与“仍在打印”检测 | 反编译；定时器 ID `0x65`/`0x66` |
| `0x0041d500` | `ConnectUSB`，语言监视器握手/线程与 Windows 8 空打印作业 | 反编译；mailslot + `StartDocPrinterW`/`WritePrinter` |
| `0x00416830` | 启动 `KMSTMNET.exe` | 反编译；命令行格式见下 |

`KMSTMVM.exe` 并不是单纯的前台 GUI：它承担虚拟打印机/状态监视器的设备侧轮询，
并通过 Windows 打印后台（`OpenPrinterW`/`StartDocPrinterW`/`WritePrinter`）向
本地打印机发送 PJL。

### 3.1 USB/本地路径（已验证）

- `FUN_00418650`（`CheckPrinterLocal`）根据端口名 `USB`/`LPT`/`COM`/`FILE:`
  及端口描述判定本地路径；`FUN_0041e170` 返回 `0=USB`、`1=TCP/IP`、
  `2=Internet Port`。
- 本地路径不启动 `KMSTMNET.exe`，而是在 `FUN_0041c6b0` 中设置 2 秒定时器；
  定时器 `FUN_0041af60` 在 spooler 未打印时调用 `FUN_0041d500`
  （`ConnectUSB`）。
- `ConnectUSB` 通过 `\\.\mailslot\kyocera\mita\langmonitor\rx`（或
  `...\GDI\rx`）与 Kyocera 语言监视器握手，从
  `\\.\mailslot\kyocera\mita\utility\%08x` 获取通道名，随后把 UEL PJL 帧写入
  `\\.\mailslot\kyocera\mita\<channel>`。
- `KMSTMVM.exe` 没有直接打开 USB 设备节点；真正的 USB 批量传输由打印机驱动/
  语言监视器完成。Windows 8 分支中的 `SetupAPI` + 空打印作业用于断连检测与
  打印后台唤醒兼容处理。

USB 端口判定、mailslot 握手、Windows 8 workaround 和 VID/PID 表的完整证据见
`docs/reverse-engineering/usb-path.md`。

## 4. 网络路径与 KMSTMNET.exe

当打印机名为空（网络路径）时，`FUN_0041c6b0` 从注册表读取 SNMP 读社区名，
默认 `public`，然后调用：

```text
KMSTMNET.exe /H:<hwnd> /A:<mailslot> /C:<community> /P:<printer>
```

对应反编译 `0x00416830`：

```c
_swprintf_s(cmd, ..., L"%s /H:%d /A:%s /C:%s /P:%s", ...);
CreateProcessW(NULL, cmd, ..., 0x04000020, ...);
```

`KMSTMNET.exe` 是网络后台组件，字符串中包含 `SNMP`、`SNMPv1/v2c`、`SNMPv3`、
`Read Community`、`Write Community`，并有定时器检查 Client Tool 是否仍在运行。
其父子进程/mailslot 关系是 Windows 内部 IPC；Linux 复刻不需要照搬。

第十四轮进一步确认：`KMSTMNET.exe` 不连接设备 9100，也不使用 HTTP/SOAP；
它通过内嵌 Net-SNMP 读取设备，再把结果合成为 `INFO ID`、`INFO CONFIG`、
`INFO KCONFIG`、`KINTRAYSTATUS`、`KGETOBJ` 和 `USTATUS DEVICE` 文本，经
mailslot 交给 `KMSTMVM.exe`。因此，网络路径中看到的 PJL 字符串是
Client Tool 的内部中间格式，不一定是设备实际返回的字节。完整对象表和
命令规则见 `docs/reverse-engineering/clienttool-protocol.md`。

`KMUTLMNT.exe` 是维护菜单解释器，读取 `UserPackage.mtp` / 用户维护包，
把 `MaintenancePackage` XML 定义序列化为 KPSL 二进制帧，经 TCP 9100 RAW
或 USB 发送；它不使用 PJL 或 SNMP。KPSL 帧头、校验和、载荷混淆和 20 项
参数类型表见同一份协议文档的第 9 节。维护包的密钥、解包流程和提取出的
XML/PNG 属于本地研究材料，不进入公开仓库；公开目录只保留 request id、
item id 和数据类型。

## 5. KMSTMNW.exe 与扫描

`KMSTMNW.exe` 是状态监视/设备管理 GUI，字符串包含：

- `c_print.html`、`c_device.html`、`c_scan.html`、`c_fax.html` 等本地页面名；
- `TonerA`/`TonerB`/`TonerC`/`TonerM`/`TonerY`、纸张/卡纸/缺纸事件；
- `ScanSource`、`PushScan`、`TWAIN PATH`、`NetworkScanModel`；
- `.\WIFI\wifisetup\WifiSetupToolMain.exe`。

这些字符串说明 GUI 负责展示与扫描入口。进一步的静态分析确认：

- Push Scan 由 `FUN_00450f20` 处理，最终启动
  `.\KMSCN\KMSCNPUS.EXE <presetNo>`；
- `KMSCNPUS.exe` 启用 `KMSCNSET.dll` 的预设，启动
  `KMSCNFOL.exe /D`，等待结束后禁用预设；
- 扫描设置通过 TWAIN 数据源 `Kyocera TWAIN Driver` 完成；
- USB/网络分别使用 `NS1815TW3.DLL` 与 `Ns1815TWGN.DLL`。

完整调用链、注册表/INI 路径和未确认项见
`docs/reverse-engineering/scan-workflow.md`。

历史 NetViewer 日志进一步显示 `KmwsDeviceController` 使用 SOAP/HTTP(S) 进行
配置读写（`AdaptorSoapParams.IsUseSSL`），而发现/轮询使用 SNMP；详见
`netviewer-log-findings.md`。该日志含敏感信息，未纳入仓库。

需要修正的一点：SOAP 客户端不在 `KMSTMNW.exe`/`ClientTool.dll` 中，而在
NetViewer 的 .NET 程序集（`Device.Controllers.*`、`Core.CoreServices.dll`）。
`ClientTool.dll` 只导出 `CreatePlugin`，是插件加载器。KM-WSDL 命名空间、
默认端口和 MA2000w 的 SNMP 回退证据见
`docs/reverse-engineering/kmws-soap.md`。

## 6. 工具与复现

- 反编译工具：Ghidra 12.1.4 PUBLIC（headless）+ OpenJDK 21。
- 导出脚本：`tools/ghidra_scripts/DecompileProgram.java`。
- 复现命令：

```bash
env XDG_CONFIG_HOME=/tmp/ghidra_config \
  .tools/ghidra_12.1.4_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra_proj KMSTMVM \
  -import Kyocera/ClientTool/KMSTMVM.exe \
  -scriptPath tools/ghidra_scripts \
  -postScript DecompileProgram.java analysis/decompiled/KMSTMVM \
  -deleteProject
```

输出包括 `functions.tsv`、`calls.tsv`、`callers.tsv`、`strings.tsv`、`symbols.tsv`
和 `c/` 下的逐函数伪 C。`analysis/` 为生成目录，不纳入版本控制。

## 7. 证据等级

- 已验证：PE 元数据、导入表、反编译控制流、字符串地址、PJL 实测响应。
- 较高可信度：`KMSTMVM.exe` 作为虚拟打印机/状态轮询器的角色，以及网络路径
  通过 `KMSTMNET.exe` 使用 SNMP。
- 待验证假设：KGETOBJ 中尚未确认对象的具体业务含义、Windows GUI 的完整
  交互流程、USB 与网络路径在扫描/配置写入上的差异。
