# USB 路径逆向记录

## 1. 范围与样本

本文分析 Windows 版 Client Tool 在 USB/本地端口上的设备访问方式，重点样本：

| 文件 | SHA-256 | 说明 |
| --- | --- | --- |
| `Kyocera/ClientTool/KMSTMVM.exe` | `238440f5e71a113505cbae40eaa4abede578094a3f1705afb83cf9df369df4e3` | 状态监视器/虚拟打印机 |
| `Kyocera/ClientTool/KMSTMNW.exe` | `59f39e6749d1590cb687a092fe097c5c6cfbd5cebbe1be9bfe440baef89a5fa4` | 状态/扫描 GUI |
| `Kyocera/ClientTool/KMVIDPID.ini` | 见仓库文件 | 型号到 USB VID/PID 的映射 |
| `Kyocera/ClientTool/KMSTMNET.ini` | 见仓库文件 | 型号能力与参数库映射 |

分析方式：Ghidra 12.1.4 headless 反编译 + PE 导入表/字符串 + `objdump`
汇编核对。未连接 USB 设备，本文不包含 USB 物理抓包结果。

## 2. 结论摘要

已验证：

- `KMSTMVM.exe` **没有直接打开 USB 设备节点**。USB/本地打印机的 PJL 通过
  Windows 打印后台和 Kyocera 语言监视器（language monitor）的 mailslot
  通道发送，真正的 USB 批量传输发生在驱动侧。
- `KMSTMVM.exe` 用打印机端口名/端口描述区分本地与网络路径；USB、LPT、COM、
  `FILE:` 端口按本地路径处理，并走 `ConnectUSB`。
- `ConnectUSB` 通过 `\\.\mailslot\kyocera\mita\langmonitor\rx`（或
  `...\GDI\rx`）向语言监视器请求通道，响应从
  `\\.\mailslot\kyocera\mita\utility\%08x` 返回，随后拼出
  `\\.\mailslot\kyocera\mita\<channel>` 作为 PJL 写通道。
- PJL 帧仍为 UEL 包裹的 `@PJL ...` 文本；`FUN_00417150` 的格式串为
  `%c%s\r\n%s\r\n%c%s`，与网络路径使用的帧构造一致。
- USB 连接成功后原程序会发送：

  ```text
  @PJL USTATUS DEVICE=ON
  @PJL USTATUS JOB=ON
  @PJL INFO ID
  ```

  然后由 `Refresh`（`0x0041a3a0`）按本地路径的 14 条查询刷新状态；连接时
  已发送的 `@PJL INFO ID` 不重复发送，`KINTRAYSTATUS` 在该本地分支中也不发送。

未验证：

- 语言监视器在写入 USB 前是否对 PJL 字节做额外封装、分片或重试。
- Linux `usblp` 原始读写能否与 MA2000w 的 USB 固件完成同样的双向 PJL 交互。
- USB 扫描是否使用与打印相同的语言监视器通道。

## 3. 关键函数

| 地址 | 作用 | 证据 |
| --- | --- | --- |
| `0x0041c6b0` | `CVirtualPrn::Create`，区分本地/网络并建立 mailslot | 反编译；本地分支设置 2 秒重连定时器 |
| `0x00418650` | `CheckPrinterLocal`，判定端口是否为本地/USB | 反编译；`EnumPrintersW`/`EnumPortsW` |
| `0x0041e170` | `GetPortType`：USB=0、TCP/IP=1、Internet Port=2 | 反编译 |
| `0x00422bc0` | `IsSupportedPort`，USB/TCP/IP/Internet Port 返回 1 | 反编译 |
| `0x0041d500` | `ConnectUSB`，建立事件、读/写/重连线程 | 反编译；日志字符串 `[VPRN] <fn:ConnectUSB>` |
| `0x0041c4d0` | `procThread_UntilConnect`，最多 5 秒握手 | 反编译；每 1 秒重试，超时 0x1389 ms |
| `0x00417290` | 打开打印机、读取驱动信息、向语言监视器发握手请求 | 反编译；`OpenPrinterW`/`GetPrinterDriverW` |
| `0x0041c33b` | 从 utility mailslot 读取通道名 | 反编译；`ReadFile` 后调用 `FUN_00417780` |
| `0x00417780` | 构造 `\\.\mailslot\kyocera\mita\%s` | 反编译 |
| `0x00417150` | 构造 UEL PJL 帧并写入 mailslot | 反编译；`FUN_00416b20` 用 `CreateFileW`+`WriteFile` |
| `0x0041bf00` | 发送 USTATUS/INFO ID 并启动发送 mailslot 线程 | 反编译 |
| `0x0041a3a0` | `Refresh`，本地路径逐条发送 14 条 PJL 查询 | 反编译 |
| `0x0041af60` | 2 秒定时器；未在打印时重新调用 `ConnectUSB` | 反编译；定时器 ID `0x66` |
| `0x004180c0` | `IsStatusPrinting`，读取 spooler `PRINTER_INFO_2` | 反编译 |
| `0x00417dd0` | Windows 8 USB 断连检测，SetupAPI 枚举 USBPRINT 接口 | 反编译 + 汇编 |
| `0x0041d310` | `DisconnectCheckWndProc`，处理 `WM_DEVICECHANGE` | 反编译 |
| `0x00420a50` | `WndProc` 的 PAUSE/RESUME/BREAK/LAHUS 分支 | 反编译；`PausedUtilCnt` 控制 USB R/W |

## 4. 本地/USB 端口判定

`CheckPrinterLocal`（`0x00418650`）的两个判定阶段：

1. `EnumPrintersW(6, ..., level=2)` 枚举打印机，匹配端口名；若端口名以
   `USB`、`LPT`、`COM` 开头或为 `FILE:`，返回本地。
2. 若打印机枚举不能给出结论，则 `EnumPortsW` 枚举端口：
   - 端口描述包含 `USB` 或等于 `Local Port` → 本地；
   - 描述包含 `TCP/IP`、`KPrint`、`Port Set Up` → 网络；
   - Windows 11 workaround：描述包含 `Kyocera` 或 `TA_UTAX`，且端口名包含
     `USB` → 本地。

`GetPortType`（`0x0041e170`）的返回值为：

| 返回值 | 含义 |
| --- | --- |
| `0` | USB/本地 |
| `1` | TCP/IP |
| `2` | Internet Port |

`Create`（`0x0041c6b0`）的第三个字符串参数是网络通知 mailslot 名（存入
`+0x5d0`，网络分支作为 `KMSTMNET.exe /A:` 参数）。该 mailslot 名为空时，
`Create` 调用 `CheckPrinterLocal`：本地检查成功则设置 2 秒定时器，由
`ConnectUSB` 建立语言监视器通道；检查失败且端口名不以 `http://` 开头时，
发送 `WM_USER_NOTCONNECT[NET]`。mailslot 名非空时直接走 `KMSTMNET.exe`
网络分支。

## 5. USB 连接与 mailslot 握手

`ConnectUSB` 的实际顺序（已从反编译控制流还原）：

1. 创建事件 `+0x1c`，创建读 mailslot
   `\\.\mailslot\kyocera\mita\utility\%08x`（`%08x` 为窗口句柄）。
2. 启动读线程、`UntilConnect` 线程、写线程。
3. `UntilConnect` 每秒调用一次 `FUN_00417290`，最多约 5 秒：
   - `OpenPrinterW` 打开打印机；
   - `GetPrinterDriverW(level=3)` 读取驱动名；
   - 若驱动名包含 `Monitor T`，选择
     `\\.\mailslot\kyocera\mita\langmonitor\GDI\rx`，否则选择
     `\\.\mailslot\kyocera\mita\langmonitor\rx`；
   - 把 `utility\%08x` 和端口名等打包后写入语言监视器 rx mailslot；
   - 等待事件或线程结束，单次最长 10 秒。
4. 语言监视器把通道名写回 utility mailslot。读线程检查消息首部
   `type=1, subtype=0`，用 `FUN_00417780` 拼出
   `\\.\mailslot\kyocera\mita\<channel>`，保存到对象 `+0x3c0`，并 `SetEvent`。
5. 写线程在事件就绪后发送：

   ```text
   @PJL USTATUS DEVICE=ON
   @PJL USTATUS JOB=ON
   @PJL INFO ID
   ```

6. 之后 `FUN_0041a3a0` 的 `Refresh` 逐条发送本地路径查询序列（14 条，
   不含连接时的 `INFO ID` 和 `KINTRAYSTATUS`）。每条查询都通过
   `FUN_00417150` 构造 UEL 帧，再 `CreateFileW` 打开通道 mailslot 并
   `WriteFile`。
7. `FUN_0041b020` 同时创建
   `\\.\mailslot\kyoceramita\kmstmvm300\send\<printer>`，接收外部发给
   虚拟打印机的消息；`Create` 还构造 `notify\<hwnd>` 与 `recv\<printer>`
   两个 mailslot 名称，用于 UI/设备管理进程之间的通知和响应转发。

超时或线程失败时，程序向主窗口发送 `WM_USER_NOTCONNECT`（`0x46e`），
并记录 `[VPRN] <fn:procThread_UntilConnect> ERROR POST WM_USER_NOTCONNECT[USB]`。

## 6. Windows 8 断连检测

`ConnectUSB` 仅在 `GetVersionExW` 报告 `6.2`（Windows 8）时执行以下 workaround：

1. 注册窗口类 `DISCONNECT_CHECK_CLASS`，创建隐藏窗口
   `DisconnectCheckWindow`。
2. `WM_DEVICECHANGE`/`0x7` 到达时，`DisconnectCheckWndProc` 调用
   `FUN_00417dd0`。
3. `FUN_00417dd0` 使用 GUID
   `{28D78FAD-5A12-11D1-AE5B-0000F803A8C2}`（USBPRINT 设备接口）调用
   `SetupDiGetClassDevsW(..., DIGCF_PRESENT|DIGCF_DEVICEINTERFACE)`。
4. 对每个接口读取 `SPDRP_HARDWAREID`，检查其中是否同时包含
   `VID_%04x` 和 `PID_%04x`。
5. 若在线，打开打印机并发送一个空打印作业：

   ```text
   StartDocPrinterW(level=1, "Document1")
   WritePrinter(handle, NULL, 0, &written)
   EndDocPrinter(handle)
   ```

该 workaround 的 VID/PID 来自 `KMSTMVM.exe` 内置的 22 条旧型号表
（`0x429860`，每条 `0x20c` 字节）：

```text
Kyocera FS-1040 GX / FS-1040 GX (XPS)      0482:0493
Kyocera FS-1060DN GX / (XPS)               0482:0494
Kyocera FS-1020MFP GX / (XPS)              0482:0495
Kyocera FS-1025MFP GX / (XPS)              0482:0496
Kyocera FS-1120MFP GX / (XPS)              0482:0497
Kyocera FS-1125MFP GX / (XPS)              0482:0498
Kyocera FS-1041 GX / (XPS)                 0482:04fb
Kyocera FS-1061DN GX / (XPS)               0482:04fc
Kyocera FS-1220MFP GX / (XPS)              0482:04fd
Kyocera FS-1320MFP GX / (XPS)              0482:04fe
Kyocera FS-1325MFP GX / (XPS)              0482:04ff
```

MA2000w 不在这 22 条表中；其 USB 映射来自 `KMVIDPID.ini`：

```ini
[Kyocera MA2000w GX]
 VID=0x0482
 PID=0x0d51
```

因此不能把 Windows 8 workaround 的旧型号表当作 MA2000w 的 USB 识别依据。

## 7. 暂停/恢复与重连

- `FUN_0041af60` 的 `ID_STILLPRINTING_TIMER`（`0x66`，2000 ms）检查
  spooler 是否仍在打印；不在打印时重新调用 `ConnectUSB`。
- 主窗口的 `PAUSE`/`RESUME`/`BREAK`/`LAHUS` 消息维护
  `PausedUtilCnt`；归零时销毁并重建虚拟打印机对象，重新执行 `Create`。
- 这解释了原程序为何能在 USB 插拔、打印作业切换后自动恢复；Linux 侧需要在
  后续物理测试中验证 `usblp` 的断连/重连行为。

## 8. 对 Linux 实现的含义

Windows 端的 mailslot 和 Kyocera 语言监视器无法移植。Linux 侧采用
`/dev/usb/lp*`（内核 `usblp`）直接发送同样的 UEL PJL 帧，作为原生等价路径：

- 设备发现：扫描 `/dev/usb/lp*`，从
  `/sys/class/usbmisc/lpN/device` 向上读取 `idVendor`/`idProduct`；
  MA2000w 预期为 `0482:0d51`。
- 传输：`os.open(O_RDWR|O_NONBLOCK)`，用 `select` 等待可读写；
  处理短写、`EAGAIN`、`EINTR`、`EIO`/`ENODEV`。
- 每次查询前丢弃残留输入，避免上一次 USTATUS/响应的尾部污染。
- Linux 聚合序列把 `@PJL INFO ID` 放在最前，随后是 15 条查询
  （含 `KINTRAYSTATUS`），与“先 ID、后 15 条”的原厂顺序对应。
- 只读实现不发送 `@PJL USTATUS DEVICE=ON`/`JOB=ON`，因为这两条会改变设备
  通知状态；需要完全复刻原厂连接行为时再单独提供显式开关。
- USB 原始帧是否与 TCP 完全一致仍是**待验证假设**；语言监视器可能在驱动侧
  增加分片或控制信息。物理接入后必须用 `--usb --json` 与网络结果对照。

## 9. 物理测试清单（待硬件接入）

1. `lsusb` 应出现 `0482:0d51`；`dmesg` 应出现 `usblp` 绑定。
2. `python3 -m kyocera_monitor --list-usb` 应列出 `/dev/usb/lp*` 和
   `0482:0d51`。
3. `python3 -m kyocera_monitor --usb --json` 应返回型号、状态、耗材、纸盒、
   KGETOBJ；与 `--host` 结果逐项对照。
4. 检查权限：当前用户需能读写 `/dev/usb/lp*`；不要在 CUPS 正在占用设备时
   并发读取。
5. 插拔、打印中查询、设备睡眠、错误状态各测一次，记录 `EIO`/超时行为。
6. 若 USB 无响应，先用 `--raw` 保存请求/响应，再检查语言监视器是否改变了
   帧格式；在未取得证据前不要修改帧格式。

## 10. 证据等级

- 已验证：函数控制流、mailslot 路径、UEL 帧格式、端口分类、Windows 8
  workaround、旧型号 VID/PID 表、MA2000w 的 `0482:0d51` 映射。
- 较高可信度：USB 路径的实际数据由语言监视器转发；其上层仍是同一套 PJL
  查询序列。
- 待验证假设：语言监视器是否对 USB 字节做额外封装；`usblp` 双向读取是否
  与设备固件兼容。
