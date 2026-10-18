# Client Tool 协议拆解

## 1. 范围与样本

本文只分析 `Kyocera/ClientTool` 目录内的 Client Tool 组件，不把
`Kyocera/NetViewer` 的 SOAP/.NET 实现作为结论依据。

分析样本（ClientTool 1.4.11.2，包日期 2022-11-09）：

| 文件 | SHA-256 | 作用 |
| --- | --- | --- |
| `KMSTMVM.exe` | `238440f5e71a113505cbae40eaa4abede578094a3f1705afb83cf9df369df4e3` | 主监视器/虚拟打印机，维护 PJL 与语言监视器通道 |
| `KMSTMNET.exe` | `2994606907429ac7a518bc451287d00a5677df2910042e72ea082b8edab43108` | 网络监视子进程，内嵌 Net-SNMP |
| `KMUTLCFG.exe` | `63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea` | 设备配置工具，SNMP + USB PJL |
| `KMUTLPRE.exe` | `4635fb4f85e2204e15dd937cfc08411de47fc7a4a857ec78beb8a2a40e3d499e` | 预设/Quick Scan 设置工具，SNMP + USB PJL |
| `KMSTMNW.exe` | `59f39e6749d1590cb687a092fe097c5c6cfbd5cebbe1be9bfe440baef89a5fa4` | 状态监视 GUI，枚举 Windows 已安装打印机 |

反编译输出位于 `analysis/decompiled/`（不纳入版本控制）。对象表的可复现
提取工具为 `tools/clienttool_oids.py`，生成的数据位于：

- `docs/reverse-engineering/data/clienttool-config-oids.tsv`
- `docs/reverse-engineering/data/clienttool-preset-objects.tsv`

证据边界：本文新增的调用链、对象表和命令格式全部来自 ClientTool 二进制与
设备只读实测。睡眠模式、自动错误清除、表单超时等少数参数名称沿用项目此前
已由 PJL/SNMP 设备值交叉验证的结论；本轮没有继续分析 NetViewer 文件，也未
把 NetViewer 的 SOAP 类型当作 Client Tool 的行为证据。

## 2. 结论摘要

本轮得到的关键结论：

1. **网络路径是 SNMP，不是 TCP 9100，也不是 HTTP/SOAP。**
   `KMSTMVM.exe` 在网络打印机上启动 `KMSTMNET.exe`；`KMSTMNET.exe` 内嵌
   Net-SNMP，负责网络监视轮询；配置读写由 `KMUTLCFG.exe`/`KMUTLPRE.exe`
   的 SNMP 路径完成。静态分析未在 `KMSTMNET.exe` 中发现 9100 端口、
   HTTP 客户端或 SOAP 调用。
2. **`KMSTMNET.exe` 把 SNMP 结果合成为 PJL 文本。**
   它按 `@PJL INFO ID`、`@PJL INFO CONFIG`、`@PJL INFO KCONFIG`、
   `@PJL KGETOBJ ...`、`@PJL USTATUS DEVICE` 的格式生成字符串，再通过
   mailslot 交给 `KMSTMVM.exe`。这些字符串不是从设备收到的原始 PJL。
3. **USB 路径是打印后台 + Kyocera 语言监视器。**
   `KMSTMVM.exe` 通过 mailslot 写入 UEL PJL；真正的 USB 批量传输由驱动/语言
   监视器完成。Linux 侧直接用 `/dev/usb/lp*` 或 TCP 9100 发送同样的 UEL 帧，
   是协议等价实现，不必复制 Windows 的 mailslot。
4. **配置和预设工具使用两套等价通道。**
   网络：SNMP GET/SET；本地 USB：`@PJL KGETOBJ`/`@PJL KSETOBJ`。两者操作
   同一组对象 OID。
5. **厂商私有对象集中在 `1.3.6.1.4.1.1347.1001.*`。**
   已确认四个子域：
   - `1001.1.*`：预设（Copy/Scan/Fax/Print Box）
   - `1001.2.*`：设备配置/状态项
   - `1001.3.*`：Print Box 远程操作
   - `1001.4.*`：Push Scan 远程操作
6. **Client Tool 自身不做局域网发现。**
   它枚举 Windows 已安装打印机（`EnumPrintersW`/`EnumPortsW`），网络地址来自
   打印端口。项目现有的 SNMP 广播/WS-Discovery 属于 Linux 复刻新增能力。
7. **维护菜单使用独立的 KPSL 二进制协议。**
   `KMUTLMNT.exe` 不走 SNMP/PJL，而是把维护包定义序列化为 KPSL 帧，通过
   TCP 9100 RAW 端口或 USB 发送。帧头、校验和、参数类型表已还原；
   维护请求目录已提取为只含 request id、item id 和数据类型的互操作性表。
   维护包的密钥、解包流程和提取出的 XML/PNG 不进入公开仓库。

## 3. 传输与通道

### 3.1 网络：SNMP

- `KMSTMNET.exe`、`KMUTLCFG.exe`、`KMUTLPRE.exe` 都静态链接了 Net-SNMP
  （字符串中包含 `..\..\snmplib\snmp_api.c`、`NET-SNMP version` 等）。
- 默认端口 `161/udp`。未发现 Client Tool 使用 SNMP trap 端口或私有 UDP
  发现协议。
- 支持 SNMPv1/v2c 和 SNMPv3。注册表配置位于：

```text
HKCU\Software\Kyocera Mita\StatusMonitor\<打印机名>\
  SNMP                  = "v1v2c" 或 "v3"
  Read Community
  Write Community
  SNMPv3 Username
  SNMPv3 Password
  SNMPv3 Authentication = Off / MD5 / SHA1
  SNMPv3 Privacy        = Off / DES / AES
```

上述键名来自 `KMSTMNET.exe` 的 `CConnectInfo::GetSNMPSettingFromReg()`
（`0x004b8b50`）。不同版本的键值可能变化，读取时应当按能力探测，不应硬编码。

### 3.2 本地：UEL PJL

`KMSTMVM.exe` 的 `FUN_00417150` 构造以下帧：

```text
ESC%-12345X\r\n
@PJL <command>\r\n
...
ESC%-12345X
```

其中 `ESC` 为 `0x1b`，`ESC%-12345X` 即 UEL（Universal Exit Language）。
网络配置工具在 USB 路径下使用同一帧；`KMUTLPRE.exe` 的
`FUN_00419e40` 直接给出 GET/SET 模板：

```text
ESC%-12345X@PJL\r\n
@PJL KGETOBJ OBJ="#<oid>"\r\n
ESC%-12345X
```

```text
ESC%-12345X@PJL\r\n
@PJL KSETOBJ OBJ="#<oid>" VALUE=<value>\r\n
ESC%-12345X
```

### 3.3 内部 IPC

`KMSTMVM.exe` 启动网络组件：

```text
KMSTMNET.exe /H:<hwnd> /A:<mailslot> /C:<community> /P:<printer>
```

`KMSTMNET.exe` 按 `/A:` 打开 mailslot，把合成后的 PJL 文本写入；
`KMSTMVM.exe` 的 mailslot 读取线程解析后更新 UI。该 IPC 是 Windows 内部
实现细节，Linux 复刻不需要照搬。

## 4. PJL 对象语法与值编码

### 4.1 两种对象路径

| 写法 | 含义 | 示例 |
| --- | --- | --- |
| `1.<path>` | 相对 Kyocera 企业根，等价于 `1.3.6.1.4.1.1347.<path>` | `1.43.5.1.1.34.1` |
| `#<oid>` | 绝对 OID | `#1.3.6.1.4.1.1347.1001.3.1.1.0` |

`KMUTLCFG.exe` 的 147 行配置表同时使用两种写法：以 `1.3.6.1...` 开头的
绝对 OID 使用 `#`，其余使用 `1.`。这与反编译中的前缀选择完全一致
（绝对 OID 索引集合与 `#` 分支索引集合一致）。

### 4.2 响应格式

```text
@PJL KGETOBJ OBJ="<object>"\r\n
STATUS=<status>\r\n
TYPE=<type>\r\n
VALUE=<value>\r\n
\f
```

`STATUS=0` 表示成功；`STATUS=2` 表示对象不存在/不可读。

已由 MA2000w 实测的 `TYPE`：

| TYPE | 含义 | VALUE 形式 |
| --- | --- | --- |
| `2` | 整数 | 十进制文本，如 `VALUE=1` |
| `4` | 八位字节串 | 十六进制文本，如序列号 `483439...` |
| `64` (`0x40`) | IPv4 地址 | 十六进制文本，如 `4330413830304443` = `192.168.0.220` |

**注意：PJL 的字符串和 IP 值不是直接可读文本。** 字符串要先做十六进制解码；
IP 地址要先解码成 4 字节再转点分十进制。SNMP 返回的同一对象通常已经是
可读字符串或 `IpAddress`，两者编码不同。

实测例：

```text
@PJL KGETOBJ OBJ="1.43.5.1.1.28.1"
STATUS=0
TYPE=4
VALUE="48343933333435373935"      # ASCII: H493345795
```

```text
@PJL KGETOBJ OBJ="1.40.10.1.1.4.1"
STATUS=0
TYPE=64
VALUE="4330413830304443"          # 192.168.0.220
```

## 5. 网络监视协议（KMSTMVM + KMSTMNET）

### 5.1 轮询与刷新

- `KMSTMNET.exe` 的窗口定时器 `0x66` 首次间隔 1500 ms，之后每 3000 ms
  触发一次（构造函数中 `+0x96c = 3000`），用于检查 Client Tool 主窗口是否
  仍在运行并刷新状态。
- 定时器 `0x65` 间隔 60000 ms（`+0x964 = 60000`），触发时会关闭
  `KMSTMNET.exe`，属于进程级看门狗。
- `WM_COPYDATA`/`SendMessage(0x4a, ...)` 的子命令包括：

| 命令 | 动作 |
| --- | --- |
| `0x0e` | 完整刷新（`FUN_004b7740`） |
| `0x0f` | 设备电源循环/重置（`prtGeneralReset=4`） |
| `0x10` | 恢复默认/初始化（`prtGeneralReset=6`） |
| `0x17` | 读取耗材信息 |
| `0x18` | 读取 Print Box 配置 |
| `0x19` | 写 Print Box 结果 |
| `0x1a` | 写 Push Scan 结果 |
| `0x1b` | 读取 Push Scan 配置 |
| `0x1c` | 读取 Print Box/PIN 配置 |
| `0x1d` | 写 PIN 结果 |

### 5.2 SNMP 对象表（监视）

`KMSTMNET.exe` 读取的主要对象如下。表中“含义”只写已有证据支持的名称。

| OID（完整） | 含义 | 证据 |
| --- | --- | --- |
| `1.3.6.1.4.1.1347.43.5.1.1.1.1` | 型号名（`INFO ID`） | `FUN_004b5c30` |
| `1.3.6.1.4.1.1347.43.5.1.1.36.1` | KID/设备标识 | `FUN_004b5c30` |
| `1.3.6.1.4.1.1347.43.5.1.1.28.1` | 序列号 | `FUN_004b5e60` + 实测 |
| `1.3.6.1.4.1.1347.43.5.4.1.5.1.1` | 固件版本/日期信息 | `FUN_004b5e60` |
| `1.3.6.1.4.1.1347.42.5.4.1.5.2` | 引擎版本 | `FUN_004b5120` |
| `1.3.6.1.4.1.1347.43.5.1.1.33.1` | 睡眠模式 | `FUN_004b3990` |
| `1.3.6.1.4.1.1347.43.5.1.1.34.1` | 自动错误清除开关 | `FUN_004b3990` |
| `1.3.6.1.4.1.1347.43.5.1.1.35.1` | 自动错误清除超时 | `FUN_004b3990` |
| `1.3.6.1.4.1.1347.43.5.1.1.22.1` | 表单进纸超时 | `FUN_004b3990` |
| `1.3.6.1.2.1.43.5.1.1.10.1` | 控制台本地化索引 | `FUN_004b3990` |
| `1.3.6.1.2.1.43.7.1.1.3.1.<n>` | 本地化国家/语言 | `FUN_004b3990` |
| `1.3.6.1.2.1.2.2.1.6.1` | 网络接口 MAC 地址 | `FUN_004b3990` |
| `1.3.6.1.2.1.43.10.2.1.4.1.1` | 累计打印页数 | `FUN_004b3990` |
| `1.3.6.1.4.1.1347.43.10.1.1.8.1.1` | Drum 计数 | `FUN_004b3990` |
| `1.3.6.1.4.1.1347.43.10.1.1.14.1.1` | Drum 计数上限 | `FUN_004b3990` |
| `1.3.6.1.4.1.1347.46.10.1.1.5.3` | 扫描计数 | `FUN_004b3990` |
| `1.3.6.1.2.1.43.11.1.1.3/5/6/8/9` | 耗材表（类型/单位/容量/余量/名称） | `FUN_004b5120` |
| `1.3.6.1.2.1.43.12.1.1.4` | 通道/语言索引 | `FUN_004b5120` |
| `1.3.6.1.2.1.43.8.2.1.6/7/9/10/12` | 进纸盒表（类型/容量/状态/余量） | `FUN_004b5e60` |
| `1.3.6.1.2.1.43.8.2.1.15` | 进纸盒名称/描述 | `FUN_004bb190` |
| `1.3.6.1.2.1.43.9.2.1.9` | 出纸/输出状态 | `FUN_004baf30` |
| `1.3.6.1.2.1.43.18.1.1.2..7` | 告警表（severity/training/group/index/location/time） | `FUN_004b70a0` |
| `1.3.6.1.4.1.1347.43.18.2.1.3` | 厂商告警文本 | `FUN_004bae20` |
| `1.3.6.1.4.1.1347.43.23.1.1.3` | 面板显示行 | `FUN_004bb060` |

### 5.3 SNMP → PJL 合成

`FUN_004b3990`、`FUN_004b5120`、`FUN_004b5c30`、`FUN_004b5e60` 负责把
SNMP 值写进 PJL 响应文本。典型映射：

| 合成后的 PJL 对象 | SNMP 来源 |
| --- | --- |
| `INFO ID` / `INFO KID` | `1347.43.5.1.1.1.1` / `1347.43.5.1.1.36.1` |
| `INFO KCONFIG` 的墨粉行 | `43.11.1.1.*` |
| `KGETOBJ 1.42.5.1.1.16.1` | `1347.42.5.1.1.16.1` |
| `KGETOBJ 1.43.5.1.1.33.1/34.1/35.1` | `1347.43.5.1.1.33.1/34.1/35.1` |
| `INQUIRE TIMEOUT` | `1347.43.5.1.1.22.1` × 5 |
| `INFO KNETWORKSTATUS` | `1.3.6.1.2.1.2.2.1.6.1` |
| `KGETOBJ 2.10.2.1.4.1.1` | `43.10.2.1.4.1.1` |
| `KGETOBJ 1.43.10.1.1.8.1.1` | `1347.43.10.1.1.8.1.1` |
| `KGETOBJ 1.43.10.1.1.14.1.1` | `1347.43.10.1.1.14.1.1` |
| `KGETOBJ 1.46.10.1.1.5.3` | `1347.46.10.1.1.5.3` |

`FUN_004b5e60` 还会把 `1.3.6.1.4.1.1347.42.3.1.1.1.1.2` 等对象用于机型判断，
例如把以 `DP-`/`Doc` 开头的型号视为带文档处理器。

### 5.4 状态与告警

`FUN_004b70a0` 读取告警表并生成状态码。关键行为：

- 告警行由 6 个整数组成：
  `severity`、`training`、`group`、`group-index`、`location`、`code`。
- 代码 `1001`（`0x3e9`）和 `503`（`0x1f7`）在状态判断中有特殊处理；具体
  业务分支尚未完全还原。
- `FUN_004b0890` 生成：

```text
@PJL USTATUS DEVICE
CODE=35078
```

或带第二码：

```text
@PJL USTATUS DEVICE
CODE=35078
CODE2=30014
```

- `FUN_004b09c0` 生成逐行告警：

```text
@PJL USTATUS DEVICE
ALERT0=_<severity>_<training>_<group>_<group-index>_<location>_<code>
```

这些文本由 `KMSTMVM.exe` 的 `FUN_0041b290` 解析；Linux 实现可直接用 SNMP
告警表，不需要复制文本中间层。

## 6. 配置协议（KMUTLCFG.exe）

### 6.1 147 行对象表

`KMUTLCFG.exe` 的静态表位于 `0x00498244`，每行 12 字节：

```text
uint32 oid_string_pointer
uint32 type_code
uint32 item_id
```

共 147 行。完整表见
`docs/reverse-engineering/data/clienttool-config-oids.tsv`。

`type_code` 的已验证/较高可信度含义：

| code | 类型 | 依据 |
| --- | --- | --- |
| `0` | 整数 | 大量整型对象，如超时、开关 |
| `3` | IPv4 地址 | `40.10.1.1.4/6/7` 实测为 IP/掩码/网关 |
| `5` | 字符串 | SNMP community、SSID、主机名等 |
| `6` | MAC 地址 | 仅从位置和编码推断，尚未取得有效设备值 |

### 6.2 读取

网络路径（`FUN_00401120`）：

- 通过 `snmpget` 批量读取表中对象；单个对象失败不影响其余对象。
- 读取结果按对象名写入 UI 数据模型。
- 面板语言先读 `1.3.6.1.2.1.43.5.1.1.10.1`，再读对应的
  `1.3.6.1.2.1.43.7.1.1.3.1.<n>`。

USB 路径（`FUN_00402300`、`FUN_004026d0`）：

- 把整张表中适用的对象拼成一个 UEL 帧，逐行发送 `KGETOBJ`。
- 解析 `@PJL KGETOBJ OBJ="..." STATUS=... TYPE=... VALUE=...`。
- 对面板语言对象有单独的处理和计数。

### 6.3 写入

网络路径（`FUN_00401b20`）：

- 对每个变更项调用 Net-SNMP `snmpset`，按对象类型传入字符串/IP/整数。
- 若“需要重启”标志置位，再发送：

```text
1.3.6.1.4.1.1347.40.1.1.1.6.1 = 2
```

USB 路径（`FUN_00402ec0`）：

- 只把发生变化的项拼进一个 UEL 帧，逐行发送 `KSETOBJ`。
- 解析 `STATUS=0` 判断成功；任一对象失败会记录失败计数。
- 成功后若需要重启，发送：

```text
@PJL KSETOBJ OBJ="1.40.1.1.1.6.1" VALUE=2
```

注意：`40.1.1.1.6.1` 是相对路径，完整 OID 为
`1.3.6.1.4.1.1347.40.1.1.1.6.1`，不是标准 Printer MIB 的重置对象。

### 6.4 已确认的配置对象示例

| OID（完整） | 含义 | 实测值（MA2000w） |
| --- | --- | --- |
| `1.3.6.1.4.1.1347.40.10.1.1.4.1` | IPv4 地址 | `192.168.0.220` |
| `1.3.6.1.4.1.1347.40.10.1.1.6.1` | 子网掩码 | `255.255.255.0` |
| `1.3.6.1.4.1.1347.40.10.1.1.7.1` | 默认网关 | `192.168.0.1` |
| `1.3.6.1.4.1.1347.40.10.1.1.5.1` | 主机名 | `KMD4E4BA` |
| `1.3.6.1.4.1.1347.40.26.2.1.3.1` | SNMP 读社区 | `public` |
| `1.3.6.1.4.1.1347.40.26.2.1.4.1` | SNMP 写社区 | `public` |
| `1.3.6.1.4.1.1347.43.21.1.1.2.1.15` | 自定义纸张名称 | `Custom 1` |
| `1.3.6.1.4.1.1347.43.21.1.1.3.1.15` | 自定义纸张重量/类型索引 | `11` |
| `1.3.6.1.4.1.1347.43.5.1.1.23.1` | 睡眠时间（分钟，推断） | `1` |
| `1.3.6.1.4.1.1347.42.5.1.1.43.1` | 关机定时器（推断，值 72 对应 3 天） | `72` |
| `1.3.6.1.4.1.1347.1001.2.1.1.1.14.1` | Quiet mode（推断） | `0`（OFF） |

### 6.4.1 厂商符号名

Client Tool 自带两份 `snmp-oid.xml`，都以 `<symbol oid="prefix"/>` 形式
保存厂商 OID 名称：

- `Kyocera/ClientTool/WIFI/wifisetup/def/dev/snmp-oid.xml`
- `Kyocera/ClientTool/WFH/remotefax/system/Device.Base/def/dev/snmp-oid.xml`

工具会合并两份文件，对 147 行对象表做“最长前缀”匹配。合并后仍是 127 项
有名称、20 项 OID-only；第二份文件没有增加配置对象的覆盖。两份文件合计
约 500 个 OID；remotefax 独有 15 个符号，主要是
`kmFaxDeviceExist`、`kmFaxApliFirmwareVersion`、`kmTimeZone*`、
`kmDateFormat`、`kmFirmwareDetailVersion`、`kcprtInputMediaSelectMode`
等。MA2000w 对这批独有 OID 全部返回 `no such object`，且该机型没有传真
选件，因此这些名称只作为静态映射保留。可复现工具：

```bash
python3 tools/clienttool_config_names.py
python3 tools/clienttool_config_names.py \
  --python-output kyocera_monitor/config_vendor_names.py \
  --index-output docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv
```

生成数据：`docs/reverse-engineering/data/clienttool-config-names.tsv`
（`item_id`、`oid`、`vendor_name`、`vendor_base_oid`、`match`）和
`docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv`
（`oid`、`symbol`、`source`，保留同一 OID 的多符号和多来源）。匹配规则：

- 对象 OID 等于 XML 中的 OID → `exact`；
- 对象 OID 以 XML OID 加 `.` 开头 → `table`，表示 XML 描述的是表/组，
  对象是该表的一个实例；
- 无匹配 → `none`，不猜测名称。

关键结果：

| item_id | OID | 厂商名称 |
| --- | --- | --- |
| 1 | `43.5.1.1.23.1` | `kcprtSleepTimer` |
| 4 | `42.5.1.1.43.1` | `kmOffModeTimer` |
| 5 / 55 / 107 | `42.5.9.1.3.1/2/3` | `kmOffModeSettingState`（同一状态表的三个实例） |
| 83 | `1001.2.1.1.1.10.1` | `kmGrowthModelDeviceConfigCommonOrigianalQuality`（原文拼写） |
| 108 | `45.8.1.1.11.4` | `kmFaxDeviceSpkVolumeLevel` |
| 119 | `45.5.1.1.3.4` | `kmFaxPrivateName` |
| 128 | `45.10.2.1.1.1.4` | `kmFaxForwardEnable` |

`45.*` 传真组 34 项全部有厂商名称，解释了 MA2000w 上大量 `STATUS=2` /
`no such object` 的对象不是解析失败，而是该机型没有安装传真选件。
`1001.2.1.1.1.8.1`、`1001.2.1.1.1.9.1`、`43.10.1.1.13.1.1`、
`42.5.1.1.13.1`、`40.10.1.1.1.1` 等 20 项在两份 XML 中都没有名称，
继续以 OID 输出；这是“XML 未描述”，不是工具漏匹配。

实现中 `kyocera_monitor/config_vendor_names.py` 由工具生成并随包安装；
`--config` 的 JSON 记录新增 `vendor_name`，文本输出在缺少人工标签时回退到
厂商名称，人工 `label` 仍优先。

### 6.4.2 OID 映射源清单

`tools/clienttool_oid_sources.py` 扫描 ClientTool 下所有带 `oid` 属性的
XML，生成 `docs/reverse-engineering/data/clienttool-oid-mapping-sources.tsv`：

| 来源 | 类型 | `oid` 元素 | 绝对 / 相对 | 当前状态 |
| --- | --- | --- | --- | --- |
| `WIFI/.../snmp-oid.xml` | prefix-symbol | 494 | 494 / 0 | 已合并 |
| `WFH/remotefax/.../snmp-oid.xml` | prefix-symbol | 508 | 508 / 0 | 已合并 |
| `JobSnmpOid.xml` | hierarchical-job | 205 | 5 / 200 | 已展开 |
| `Support.xml`（两份） | support-info | 各 10 | 10 / 0 | 未整合 |
| `snmp-discovery.xml`（两份） | discovery-settings | 0 | — | 不含 OID 映射 |

`oid` 元素数是 XML 元素数量，不是唯一 OID 数；`snmp-oid.xml` 中同一 OID
可能被多个符号引用（例如 `40.42.1.1.1` 同时出现在多个 Wi‑Fi 符号下）。

`JobSnmpOid.xml` 的根是 `1.3.6.1.4.1.1347.47`，子节点使用相对 OID；
展开结果见 6.4.3。`Support.xml` 的 10 个 OID 主要描述
`KmApplicationEntry` 和用户列表安全锁，尚未接入状态查询。

### 6.4.3 作业 OID 树

`tools/clienttool_job_oids.py` 展开
`WFH/remotefax/addins/Device/Device.DeviceJobs/conf/JobSnmpOid.xml`：
`rootJob` 提供绝对根，子节点逐级拼接相对 OID，`additionalOIDS` 中的条目
自带绝对 OID。结果写入
`docs/reverse-engineering/data/clienttool-job-oids.tsv`：

- 205 个元素、205 个唯一绝对 OID，无重复；
- 5 个 `oid_kind=absolute`（`rootJob` + 4 个 `additionalOIDS`）；
- 200 个 `oid_kind=relative`。

关键行：

| 符号 | 绝对 OID |
| --- | --- |
| `kmJobGeneralIndex` | `1.3.6.1.4.1.1347.47.1.1.1.1` |
| `kmPrintJobStatusCount` | `1.3.6.1.4.1.1347.47.1.1.1.2` |
| `kmPrintJobStatusCondition` | `1.3.6.1.4.1.1347.47.2.1.1.6` |
| `kmFaxDeviceExist` | `1.3.6.1.4.1.1347.45.8.1.1.14` |
| `kmAddrBookSecurityAuth` | `1.3.6.1.4.1.1347.42.23.1.8.0` |

MA2000w 只读边界：walk `1.3.6.1.4.1.1347.47` 返回 0 行；同一次运行
walk `1.3.6.1.4.1.1347.40.42.1.1` 返回 7 行，说明不是 walk 实现问题，而是
该机型的作业子树没有可读实例。作业/日志监控在该设备上尚未验证。

同一轮 Wi‑Fi 子树还观察到 147 项对象表之外的实例
`1.3.6.1.4.1.1347.40.42.1.1.2.1 = 1075036018`；两份 XML 和 147 项表都没有
描述它，含义保持未知，不按数值形态猜测。

### 6.4.4 全量 OID 清单

`tools/clienttool_all_oids.py` 扫描 `Kyocera/ClientTool` 下所有文件，同时
匹配 ASCII 与 UTF‑16LE 的 `1.3.6.1.*` 文本，并合并 XML、作业树、
`Support.xml` 和 `KMSNMP4.INI` 的名称。输出
`docs/reverse-engineering/data/clienttool-all-oids.tsv`：

- 827 个唯一 OID，分布在 40 个文件，共 1708 次出现；
- 616 个有精确符号名，61 个只能从最近命名祖先继承（`prefix_symbols`），
  150 个没有任何名称；其中 91 个是随附第三方库的算法/证书 OID，
  59 个是设备相关 OID；
- 命名空间：Kyocera `631`、标准 MIB `143`、其他 `53`；
- 每个 OID 带 `sources`（文件:次数）、`encodings`、`occurrences`、
  `config_items` / `config_descendant_items` 和首处上下文。

`oid_role=library-constant` 标记只出现在 `BouncyCastle`、`itextsharp`、
`MimeKit` 等非设备库中的 OID；它们不参与设备字段覆盖率统计。

本轮修掉了扫描器的一处 UTF‑16 边界错误：旧负向断言把“前导点 + NUL 终止”
的 `.1.3.6.1...` 字面量排除在外，导致 `42.26.1.0`、`42.27.*` 等真实
设备对象漏扫。修复后清单从 712 个 OID 增至 827 个；新增项已按来源分类，
第三方库常量与设备对象分开统计。

`FAX/KMSNMP4.INI` 单独解析为
`docs/reverse-engineering/data/clienttool-fax-snmp-oids.tsv`：116 个
`INFO_*` 名称、108 个唯一 OID、144 行（一个名称可对应多个表变体 OID）。
关键行：`INFO_MODELNAME` = `43.5.1.1.1`、`INFO_FAXDEVICEISEXIST` =
`45.8.1.1.14`、`INFO_FAXPORTNUM` = `45.8.1.1.18`。

新增的主要二进制来源：

| 文件 | 唯一 OID |
| --- | --- |
| `FAX/KMSNMP4.INI` | 108 |
| `KMSTMNET.exe` | 47 |
| `WIFI/wifisetup/WifiSetupToolModels.dll` | 30 |
| `KMUTLPRE.exe` | 27 |
| `KMUTLCFG.exe` | 25 |
| `KMSTMVM.exe` | 12 |
| `KMSTMNW.exe` | 11 |

修复后，59 个无名称设备 OID 中已有 58 个写入
`clienttool-oid-semantics.tsv`（Print Box、Push Scan、Preset、Wi‑Fi、
PAC/LDAP、组权限、面板单位、鼓计数、标准 MIB 和命名空间根）。
唯一剩余的 `1.3.6.1.4.1.1347.42.27.6.0` 只出现在一个未对齐的
UTF‑16 数据块中，当前无法从代码引用确定其语义。

扫描边界：只匹配文件中的点分文本 OID；以二进制整数表编码的 OID（例如
147 项配置表）由既有静态分析覆盖，并通过 `config_descendant_items`
关联。`.md_`/`.ch_`/`.dl_`/`.in_`/`.ex_` 等 SZDD 压缩容器未逐个展开；
抽样检查未发现 OID 文本，因此不能据此断言压缩内容中绝对没有 OID。

### 6.4.5 Print Box 与 Push Scan 字段语义

`1001.3.1.*` 和 `1001.4.1.*` 没有出现在两份 `snmp-oid.xml` 中，但
`KMSTMNW.exe` 的设备设置接收函数 `FUN_004258c0` 按完整 OID 分支解析这些
值，并给出 `PBOX`/`PSCN` 字段名；`KMSTMNET.exe` 的读取函数
`FUN_004b2d30`（Print Box）、`FUN_004b1600`（Push Scan）、写入函数
`FUN_004b2180`/`FUN_004b14f0`、SNMP 值转换 `FUN_004ba2a0` 和地址类型
选择 `FUN_004515b0`/`FUN_00450f20` 与之相互印证。完整数据表见
`data/clienttool-oid-semantics.tsv`。

| OID 后缀（`1.3.6.1.4.1.1347.` 之后） | 语义 | SNMP 类型 | 取值 / 方向 | MA2000w 只读结果 |
| --- | --- | --- | --- | --- |
| `1001.3.1.1.0` | `print_box_interface` | Integer | `0=USB`；非零=`NETWORK`；读 | `0` |
| `1001.3.1.2.0` | `print_box_ipv4_address` | IpAddress | 点分 IPv4；读 | `0.0.0.0` |
| `1001.3.1.3.0` | `print_box_result` | Integer | `0=ACCEPTED`、`1=NO DATA`、`2=NO FOLDER`、`3=WRONG PIN`；读写 | `0`（上次结果） |
| `1001.3.1.4.0` | `print_box_pin_code` | OctetString | PIN 文本；读 | `NoSuchObject` |
| `1001.3.1.5.0` | `print_box_ipv6_address` | OctetString | 16 字节 IPv6；读 | `NoSuchObject` |
| `1001.3.1.6.0` | `print_box_host_name` | OctetString | 主机名文本；读 | `NoSuchObject` |
| `1001.3.1.7.0` | `print_box_address_type` | Integer | `1=IPv4`、`2=IPv6`、`3=HostName`；读 | `NoSuchObject` |
| `1001.4.1.1.0` | `push_scan_interface` | Integer | `0=USB`；非零=`NETWORK`；读 | `0` |
| `1001.4.1.2.0` | `push_scan_ipv4_address` | IpAddress | 点分 IPv4；读 | `0.0.0.0` |
| `1001.4.1.3.0` | `push_scan_result` | Integer | `0=OK`、`1=NG`；读写 | `0`（上次结果） |
| `1001.4.1.4.0` | `push_scan_ipv6_address` | OctetString | 16 字节 IPv6；读 | `NoSuchObject` |
| `1001.4.1.5.0` | `push_scan_host_name` | OctetString | 主机名文本；读 | 空字符串 |
| `1001.4.1.6.0` | `push_scan_address_type` | Integer | `1=IPv4`、`2=IPv6`、`3=HostName`；读 | `1`（IPv4） |

`1001.1.1.6..10` 预设字段：

| OID 后缀（`1.3.6.1.4.1.1347.` 之后） | 语义 | SNMP 类型 | 取值 / 方向 | MA2000w 只读结果 |
| --- | --- | --- | --- | --- |
| `1001.1.1.6.0` | `preset_reset_copy` | Integer | COPY 重置目标；写 | `0` |
| `1001.1.1.7.0` | `preset_reset_scan` | Integer | SCAN 重置目标；写 | `0` |
| `1001.1.1.8.0` | `preset_reset_fax` | Integer | FAX 重置目标；写 | `NoSuchObject` |
| `1001.1.1.9.0` | `preset_reset_print_box` | Integer | PRINT BOX 重置目标；写 | `0` |
| `1001.1.1.10.0` | `preset_security_lock` | OctetString | 空=`FREEING`、`FFFFFFFFFFFFFFF`=`LOCKING`；读写 | `L` |

关键证据：

- `KMSTMNW.exe!FUN_004258c0` 对 `#1.3.6.1.4.1.1347.1001.3.1.1.0` 分支
  记录 `PBOX IF`，对 `.2/.4/.5/.6/.7` 分别记录 `PBOX IpAddr`、
  `PBOX PIN Code`、`PBOX Ipv6Addr`、`PBOX HostName`、`PBOX ADDRTYPE`；
  对 `1001.4.1.*` 记录同构的 `PSCN IF/IpAddr/Ipv6Addr/HostName/ADDRTYPE`。
- `KMSTMNET.exe!FUN_004ba2a0` 把 `1001.3.1.5.0` 和 `1001.4.1.4.0`
  的 SNMP `OctetString` 按 16 字节格式化为 32 个十六进制字符；其它
  `OctetString` 直接截取文本。
- `KMSTMNET.exe!FUN_004b2180` 写入 Print Box `.3.0` 的值 0–3，并映射为
  `ACCEPTED/NO DATA/NO FOLDER/WRONG PIN`；`FUN_004b2070` 另以 4/5 写入
  同一对象并在日志中显示 `OFF/ON`，这两个值的设备端语义尚未验证。
- `KMSTMNET.exe!FUN_004b14f0` 写入 Push Scan `.3.0` 的 0/1，字符串为
  `OK/NG`。
- `KMSTMNW.exe!FUN_004515b0` 和 `FUN_00450f20` 用地址类型 0/1/2 分别选择
  IPv4、IPv6 和主机名；对应设备原始值 1/2/3。
- `KMUTLPRE.exe!FUN_0041aad0` 的 `param_2` 0/1/2/3 分别选择
  `1001.1.1.6.0`/`.8.0`/`.7.0`/`.9.0`，对应字符串
  `COPY`/`FAX`/`SCAN`/`PRINT BOX`；USB 走 `FUN_0041a370` 的
  `KSETOBJ`，SNMP 走 `FUN_0043f160` 的 `SetData`，类型均为整数。
- `KMUTLPRE.exe!FUN_00419530` 在申请预设锁时写
  `1001.1.1.10.0 = FFFFFFFFFFFFFFFF`，释放时写空字符串，日志为
  `LOCKING/FREEING`。MA2000w 当前返回 `L`，与这两个写入值都不同，
  因此把它当作不透明锁状态，不推断 `L` 的具体含义。

需要特别注意的静态不一致：`KMSTMNET.exe` 合成给 `KMSTMVM.exe` 的 PJL
文本里，Print Box IPv6 `.5.0` 被标成 `TYPE=64`，Print Box 主机名 `.6.0`
被标成 `TYPE=2`，而 Push Scan 主机名 `.5.0` 标成 `TYPE=4`。这些是
`KMSTMNET` 的输出标签，不是设备 SNMP 类型；消费这些文本时应以 OID 和
上表的 SNMP 类型为准，不能仅凭 `TYPE` 判断字符串/IP。

2026-10-18 对 MA2000w（`192.168.0.220`）做只读 SNMPv2c GET：18 个对象中
12 个可读，6 个返回 `NoSuchObject`（Print Box `.4`–`.7`、Push Scan
`.4`、Preset `.8`）。
本次没有执行 `snmpset`/`KSETOBJ`；同日 PJL 批量 `KGETOBJ` 在设备睡眠时
没有响应，因此这些对象的 PJL 路径尚未逐项实测。按当前证据，
Print Box/Push Scan/Preset 的字段语义和枚举已可由静态代码确认，但部分对象在
MA2000w 上只能通过厂商程序或其它机型验证。

### 6.4.6 Wi‑Fi、PAC/LDAP 与其余字段

`WifiSetupToolModels.dll` 的 `OID` 类把 47 个 `static readonly` 字段保存为
托管元数据常量。程序集没有被加载或执行；`tools/managed_constants.py`
直接解析 PE/CLI 头、`#~` 表流以及 `#Strings`/`#Blob` 堆，得到
“字段名 → OID”的精确对应。`WifiSetupToolViewModels.dll` 的
`GetAccessPointsList()`、`GetNumberOfAccessPoints()`、
`ConnectToAccessPoint()`、`IsSetAPSuccessful()`、`IsWifiON()` 和
`GeneratePINSuccessful()` 提供读写方向与状态比较证据。

访问点扫描表 `40.39.1.1.*`（实例 1）：

| OID 后缀（`1.3.6.1.4.1.1347.` 之后） | 语义 | 类型 / 方向 | MA2000w 只读 |
| --- | --- | --- | --- |
| `40.39.1.1.1.1.1` | `access_point_ssid` | OctetString / 读 | 空字符串 |
| `40.39.1.1.2.1.1` | `access_point_security` | Integer / 读 | `0` |
| `40.39.1.1.3.1.1` | `access_point_bssid` | OctetString(6) / 读 | `00:00:00:00:00:00` |
| `40.39.1.1.6.1.1` | `access_point_rssi` | Integer / 读 | `0` |
| `40.39.1.1.7.1.1` | `access_point_wep_key_index` | Integer / 读 | `0` |
| `40.39.1.1.8.1.1` | `access_point_wep_key` | OctetString / 读 | 空字符串 |
| `40.39.1.1.10.1.1` | `access_points_total` | Integer / 读 | `0` |

设置表 `40.40.1.1.*`（实例 1）：

| OID 后缀 | 语义 | 类型 / 方向 | MA2000w 只读 |
| --- | --- | --- | --- |
| `40.40.1.1.1.1` | `set_access_point_ssid` | OctetString / 读写 | 非空（不记录） |
| `40.40.1.1.2.1` | `set_access_point_security` | Integer / 读写 | `4` |
| `40.40.1.1.3.1` | `set_access_point_bssid` | OctetString(6) / 读写 | 6 字节（不记录） |
| `40.40.1.1.7.1` | `set_access_point_wep_key_index` | Integer / 读写 | `0` |
| `40.40.1.1.8.1` | `set_access_point_wep_key` | OctetString / 读写 | 空字符串 |
| `40.40.1.1.9.1` | `set_access_point_pre_shared_key` | OctetString / 读写 | 非空（不记录） |
| `40.40.1.1.10.1` | `complete_ap_set_configuration` | Integer / 读写 | `0` |

`IsSetAPSuccessful()` 把 `40.40.1.1.10.1` 的响应与字符串 `"0"` 比较，
因此只确认 `0=成功`；其它值未确认。`wifi_connection_state`
（`40.42.1.1.1.1`）由 `IsWifiON()` 与 `"3"` 比较，`TurnONWifi()` 也写入
`"3"`；ClientTool Wi‑Fi 页把同一字段标为 Connection status，
`3=Connected`、`4=Not connected`。本轮只观测到 `3`，Wi‑Fi Setup Tool
把任何非 `"3"` 响应都当作 `Wi-Fi is OFF`，因此 `4=Not connected` 与
“关闭”的对应关系仍是推断。`check_ap_set_configuration_status`
（`40.42.1.1.1.3.1`）在 MA2000w 返回 `2`，但该常量在当前 ViewModel
构建中没有调用方，`2` 的含义不推断。

AP 能力与 WPS：

| OID | 语义 | 结果 |
| --- | --- | --- |
| `40.43.1.1.1.1` | `wifi_capable_1`（设备发现集合第 7 项） | `3` |
| `40.44.1.1.1.1` | `wifi_capable_2`（设备发现集合第 8 项） | `NoSuchObject` |
| `40.41.1.1.2` | `wps_pin_base`（`WPSPin_DUMMY`） | 未取得（设备睡眠超时） |
| `40.41.1.1.2.1` | `wps_pin` | 未取得（设备睡眠超时） |

`DeviceDiscoveryService.dll!DeviceInfo` 的构造函数把型号、序列号、固件、
`WifiCapable1`、`WifiCapable2` 等 8 个 OID 放入同一发现集合；两个能力值的
具体枚举尚未确认，只保留“读取”和观测值。

PAC/LDAP（`42.26.*`，MA2000w 上 walk 返回 0 行）：

| OID 后缀 | 语义 | 类型 / 方向 |
| --- | --- | --- |
| `42.26.1.0` | `obtain_network_user_property` | Integer / 读写 |
| `42.26.2.1.0` | `ldap_server_name` | OctetString / 读写 |
| `42.26.2.2.0` | `ldap_port_number` | Integer / 读写 |
| `42.26.2.3.0` | `ldap_encryption` | Integer / 读写 |
| `42.26.2.4.0` | `ldap_search_timeout` | Integer / 读写 |
| `42.26.3.1.3` | `ldap_attribute_name` | OctetString / 读写 |

`42.26.3.1.3` 在厂商代码中被 Name1、Name2、EmailAddress 三处共用，
静态上无法区分每个字段，记录为“同 OID 复用”，不当作三个独立对象。
`42.27.*` 是 PAC 组权限：`.1.0` 读启用状态，`.2.0` 解锁，`.3.0`/`.4.0`/
`.8.0` 写组 ID，`.7.0` 读最大组数；本轮没有执行任何写入。

其余关键字段：

- `42.5.1.1.13.1` = `panel_size_unit`，MA2000w 返回 `4`；
  `KMUTLPRE.exe!FUN_00419700` 把 `"3"` 映射为 `INCH`，其它值记录为
  `CM`，而 `KMUTLCFG` 对话框 0x006b 的标签是 Inches/Millimeters，
  两者存在冲突，暂不强行统一。
- `43.10.1.1.8.1.1` = `drum_counter`，MA2000w 返回 `129`；
  `KMSTMNET.exe!FUN_004b3990` 的日志明确写 `DRUM COUNT`。
- `42.3.2.3.2.1.3.1.1` = `document_processor_attached`；
  `KMUTLPRE.exe!FUN_00419ae0` 的 `IsDPAttached` 以非空响应表示已连接。
  MA2000w 上该子树没有实例。
- `40.1.1.1.6.1` 出现在 `SNMPRestartDeviceController.RestartDevice()`
  中，推断为重启触发对象；没有执行重启。

命名冲突：两份 `snmp-oid.xml` 把 `40.39.1.1.1` 标为
`kmnetEnhancedWSDssl`、把 `40.40.1.1.1` 标为 `kmnetIPPSenable`，但设备
walk 显示真实 AP 表实例是 `40.39.1.1.1.1.1` 和 `40.40.1.1.1.1.1`，类型为
字符串 SSID，而不是布尔值。XML 中的对象是更上层的节点，不能把继承的
前缀符号当作表列语义；同理，`40.42.1.1.1.1` 的 `kmnetHTTPSenable` 只是
前缀符号，Wi‑Fi 工具把它读取为 `wifi_connection_state`。

### 6.5 Linux 只读配置导出

`kyocera_monitor --config` 直接复用 6.1 的 147 行对象表，按原顺序生成
147 条 `KGETOBJ` 并放在一个 UEL 帧中发送。解析结果保留
`item_id`、OID、`STATUS`、PJL `TYPE`、原始 `VALUE` 和解码值；
`item_id` 等于表行号加一，不是 Windows 控件 ID。

2026-10-18 在 MA2000w（`192.168.0.220`）上只读实测：

- 96/147 项返回 `STATUS=0`，整批耗时约 5.2–7.1 秒；
- 51 项返回 `STATUS=2`，主要集中在 `45.*`（传真相关对象）和
  `43.7.1.1.3.1.2..12`（本地化语言表），另有少量自定义纸张/预设相关对象；
- 设备对不存在的对象逐条返回 `STATUS=2`，没有因单个对象失败而中止整批；
- 没有发送 `KSETOBJ`、SNMP SET 或维护命令。

2026-10-18 复测时设备处于 Sleeping，PJL 9100 连续返回
`printer returned no PJL response`，而 SNMP 状态查询仍正常。使用
`--config --snmp --config-snmp-version 2c` 按同一 147 行对象表转换为绝对
OID、每批 16 个做只读 GET，成功返回同样的 96/147 项，耗时约 8.6 秒。
缺失对象在 SNMP 中表现为 `NoSuchObject`/`NoSuchInstance`，不会像 SNMPv1
那样使整包失败。配置 SNMP 路径已与 PJL 路径交叉核对 Sleep time `1 min`、
Power off timer `72`、Quiet mode `OFF`、IPv4、SNMP 社区和 Wi‑Fi SSID（名称
不记录）。

PJL 值解码的两个实际边界：

1. `TYPE=4` 的 `VALUE` 是十六进制文本。定长字符串会在尾部填充 NUL，
   必须先解码再去除尾随 NUL；自定义纸张 1..8 因此得到
   `Custom 1`..`Custom 8`。
2. 字符串不一定是 ASCII。Wi‑Fi SSID 对象 `40.42.1.1.4.1` 在本机实测为
   UTF‑8 中文名称；仓库不记录实际网络名与原始十六进制。若字节不是合法
   UTF‑8 或含控制字符，实现回退为十六进制。

`TYPE=64` 是两层编码：先做十六进制解码得到 8 位 ASCII 十六进制
（如 `C0A800DC`），再按 4 个字节转为 `192.168.0.220`。实现同时接受
直接给出的 8 位十六进制和点分十进制形式。

本轮只给已有独立证据的对象添加业务标签，其余保持 OID 输出。新增确认的标签
是自定义纸张 1..8 的名称；`43.21.1.1.3.1.15` 的重量/类型索引只标注第 1 项。
Wi‑Fi 对象 `40.42.*` 已由 dialog `0x00f3`（Wi‑Fi 状态页）与模型偏移确认，
MA2000w 只读实测值如下：

| 对象 | item_id | 模型偏移 | 含义 | MA2000w 值 |
| --- | --- | --- | --- | --- |
| `1.40.42.1.1.1.1` | 142 | `0x3c88` | 连接状态；`3` = Connected，`4` = Not connected | `3` |
| `1.40.42.1.1.3.1` | 143 | `0x3c8c` | 无线启用状态；页面把 `0/1` 视为关闭，其他值才显示连接信息 | `2` |
| `1.40.42.1.1.4.1` | 144 | `0x3c90` | SSID（UTF‑8） | UTF‑8 中文名称（不记录） |
| `1.40.42.1.1.5.1` | 145 | `0x3d94` | 安全模式枚举 | `4` = WPA2 PSK (AES) |
| `1.40.42.1.1.6.1` | 147 | `0x3d98` | 信道号 | `4` |
| `1.40.42.1.1.7.1` | 146 | `0x3d9c` | RSSI（dBm） | `-70` / `-71` |

配置模型（默认值表）基址是 `0x4aa890`：`DAT_004ae518 = model + 0x3c88`、
`DAT_004ae624 = model + 0x3d94`、`DAT_004ae628 = model + 0x3d98`、
`DAT_004ae62c = model + 0x3d9c`。Wi‑Fi 页直接读取这些绝对地址，
而 `FUN_0040e820` 用相同的模型偏移接收 `KGETOBJ` 结果，因此控件与
`40.42.*` 对象是同一组字段。

安全模式枚举（字符串 ID `0x204..0x209`）：`0` = Open (Disable)、
`1` = Open (WEP)、`2` = WPA2/WPA PSK (AES)、`3` = WPA2/WPA PSK (Auto)、
`4` = WPA2 PSK (AES)、其他 = Unknown。RSSI 分档（`0x20a..0x20d`）：
`>=-49` Excellent、`-60..-50` Good、`-70..-61` Fair、`<=-71` Weak。

厂商符号表把 `40.42.1.1.1.1` 标成 `kmnetHTTPSenable`，但该 OID 是
Wi‑Fi 状态页的连接状态字段；`vendor_name` 只是同 OID 的符号匹配，
不能单独作为字段语义。本表的含义以页面代码和模型偏移为准。

### 6.6 UI 控件字符串表

`KMUTLCFG.exe` 的界面文字保存在
`LANG/<locale>/KMUTLCFGRes.dll` 的 RT_STRING 资源中。主程序里有两张控件绑定表：

| 地址 | 结构 | 用途 |
| --- | --- | --- |
| `0x00496f20` | `(string_id, control_id)` | 静态标签绑定 |
| `0x00497048` | `(control_id, string_id)` | 组合框选项绑定 |

RT_STRING 的 ID 规则是 `(block_id - 1) * 16 + index`。`0x497048` 表按顺序排列，
同一 `control_id` 的连续行就是组合框的选项顺序。可复现工具：

```bash
python3 tools/clienttool_ui_strings.py
```

生成数据：`docs/reverse-engineering/data/clienttool-ui-controls.tsv`。公开表只
保留控件 ID、字符串资源 ID、文本是否存在和文本长度，不复制本地化标签或
选项内容。英文资源当前提取出 31 个标签/分区行和 31 个组合框选项；关键控件
的类别如下：

| control_id | 自写类别 |
| --- | --- |
| `0x3e8` | power_off_timer |
| `0x3e9` | auto_sleep |
| `0x3ea` | auto_error_clear |
| `0x455` | quiet_mode |
| `0x4cf` | form_feed_timeout |
| `0x4da` | duplex |
| `0x463` | power_off_interval（15 个有序选项） |
| `0x3f6` | print_density（7 个有序选项） |
| `0x3f7` | print_density_detail（5 个有序选项） |
| `0x4ab` | original_image（4 个有序选项） |

控件 ID 与 147 行对象表**没有固定偏移关系**。要把控件名补到 OID 上，仍需沿
`FUN_00410740` 的“对象索引 → 界面模型偏移”和 `FUN_00405c10` 的
“界面模型偏移 → 控件”两条路径对齐。基于这两条路径和真机值，本轮新增三个
推断标签：

- `43.5.1.1.23.1` → Sleep time（`0x3f2` 分钟输入框；MA2000w 返回 `1`）；
- `42.5.1.1.43.1` → Power off timer（`0x463` 小时/天组合框；MA2000w 返回
  `72`，按组合框分段对应 `3 days`）；
- `1001.2.1.1.1.14.1` → Quiet mode（`0x455` 复选框；MA2000w 返回 `0`）。

三项均未做写入回读验证，因此实现中标记为 `confidence: "inferred"`。其余控件
保持 OID 输出，避免按位置猜名字。

### 6.6.1 对话框资源与控件归属

控件 ID 只在所属对话框内唯一，不能在所有窗口中按编号直接比较。例如主对话框
的 `0x456` 是 `Inches`，而 SNMP trap 对话框的 `0x456` 是
`Trap Recipient 2`。`KMUTLCFG.exe` 的 `RT_DIALOG` 资源保存了每个对话框的
标题、控件类、坐标和模板内文字，可直接确定归属。可复现工具：

```bash
python3 tools/clienttool_dialogs.py
```

生成数据：`docs/reverse-engineering/data/clienttool-dialogs.tsv`。本轮确认的关键
对话框：

| dialog | 自写类别 | 作用 |
| --- | --- | --- |
| `0x006b` | main_defaults | 主设备默认值页 |
| `0x008d` | communication | TCP‑IP / SNMP 通信设置 |
| `0x00d0` | panel_options | 面板默认画面、语言、自动清除时间 |

对话框初始化路径分别为 `FUN_00405c10`（主对话框，由 `FUN_00407d40` 的
`WM_INITDIALOG` 调用）、`FUN_0041ccb0`（Communication，由
`FUN_0041e800` 调用）和 `FUN_00407830`（Panel options，由
`FUN_0040a640` 调用）。

### 6.6.2 控件 → 模型偏移 → OID

完整的“对话框 + 控件 → 模型偏移 → OID”见
`docs/reverse-engineering/data/clienttool-control-oids.tsv`。主对话框已确认：

| 控件 | 模型偏移 | item_id | OID |
| --- | --- | --- | --- |
| `0x3ea` Auto error clear | `0x0004` | 2 | `43.5.1.1.34.1` |
| `0x3f4` Auto error clear timeout（`0x3f3` 为 spinner） | `0x0008` | 3 | `43.5.1.1.35.1` |
| `0x3f2` Sleep time（`0x3f1` 为 spinner） | `0x0010` | 1 | `43.5.1.1.23.1` |
| `0x463` Power off timer | `0x0014` | 4 | `42.5.1.1.43.1` |
| `0x455` Quiet mode | `0x0018` | 50 | `1001.2.1.1.1.14.1` |
| `0x411` Form feed timeout（`0x410` 为 spinner） | `0x2ffc` | 52 | `43.5.1.1.22.1` |
| `0x3f5` Media type | `0x300c` | 9 | `43.8.1.1.4.1.1` |
| `0x3f8` Paper size | `0x3000` | 6 | `43.8.1.1.11.1.1` |
| `0x3f7` Print density | `0x2ff8` | 49 | `43.10.1.1.13.1.1` |
| `0x4ab` Original image | `0x3014` | 83 | `1001.2.1.1.1.10.1` |
| `0x474` Original size | `0x3c5c` | 87 | `46.8.1.1.6.3.1` |
| `0x48c` Ignore paper size mismatch | `0x3010` | 10 | `1001.2.1.1.1.15.1` |
| `0x466` USB is connected | `0x001c` | 5 | `42.5.9.1.3.2` |
| `0x467` Network is connected | `0x0020` | 55 | `42.5.9.1.3.1` |
| `0x468` FAX is installed | `0x0024` | 107 | `42.5.9.1.3.3` |
| `0x456` / `0x457` Inches / Millimeters | `0x0028` | 51 | `42.5.1.1.13.1` |

Panel options（dialog `0x00d0`）：

| 控件 | 模型偏移 | item_id | OID |
| --- | --- | --- | --- |
| `0x4d0` Default screen | `0x3c58` | 86 | `42.5.1.1.3.1` |
| `0x4d2` Language | `0x3020` | 79 | `1.3.6.1.2.1.43.5.1.1.10.1` |
| `0x4d3` Reset panel（可用状态） | `0x3018` | 84 | `42.5.1.1.4.1` |
| `0x4d4` / `0x4d5` Auto clear panel time | `0x301c` | 85 | `42.5.1.1.5.1` |

Communication（dialog `0x008d`）：

| 控件 | 模型偏移 | item_id | OID |
| --- | --- | --- | --- |
| `0x41d` Lan Interface | `0x4444` | 58 | `40.1.1.1.9.1` |
| `0x41e` Hostname | `0x444c` | 54 | `40.10.1.1.5.1` |
| `0x420` DHCP（`kmAddressSource`） | `0x485c` | 57 | `40.10.1.1.2.1` |
| `0x424` LPD Setting | `0x4860` | 62 | `40.20.1.1.1.1` |
| `0x425` Raw Port | `0x4864` | 63 | `40.21.1.1.1.1` |
| `0x49b` WSD Print | `0x4868` | 64 | `40.36.1.1.1.1` |
| `0x427` Read Community | `0x486c` | 65 | `40.26.2.1.3.1` |
| `0x428` Write Community | `0x4970` | 66 | `40.26.2.1.4.1` |
| `0x45e` IP address | `0x4550` | 59 | `40.10.1.1.4.1` |
| `0x45f` Subnet mask | `0x4654` | 60 | `40.10.1.1.6.1` |
| `0x460` Default Gateway | `0x4758` | 61 | `40.10.1.1.7.1` |
| `0x429` sysContact | `0x4a74` | 67 | `1.3.6.1.2.1.1.4.0` |
| `0x42a` sysName | `0x4b78` | 68 | `1.3.6.1.2.1.1.5.0` |
| `0x42b` sysLocation | `0x4c7c` | 69 | `1.3.6.1.2.1.1.6.0` |
| `0x42d` Authentication traps | `0x4d80` | 70 | `1.3.6.1.2.1.11.30.0` |

SNMP trap 页（dialog `0x008e`）由 `FUN_0041eef0` 的 `WM_INITDIALOG` 调用
`FUN_0041d700` 初始化。两组收件人的结构完全对称：

| 控件 | 模型偏移 | item_id | OID |
| --- | --- | --- | --- |
| `0x459` Trap Recipient 1（启用） | `0x4d84` | 71 | `40.26.5.1.7.1.1` |
| `0x42e` Trap Community 1 | `0x4d88` | 72 | `40.26.5.1.4.1.1` |
| `0x461` Trap IP address 1 | `0x4e8c` | 73 | `40.26.5.1.2.1.1` |
| `0x432` Add paper | `0x4f90` | 74 | `40.26.5.1.5.1.1` |
| `0x433` Toner near empty | `0x4f94` | 74 | `40.26.5.1.5.1.1` |
| `0x434` Add toner | `0x4f98` | 74 | `40.26.5.1.5.1.1` |
| `0x435` Cover open | `0x4f9c` | 74 | `40.26.5.1.5.1.1` |
| `0x436` Paper jam | `0x4fa0` | 74 | `40.26.5.1.5.1.1` |
| `0x437` All other errors | `0x4fa4` | 74 | `40.26.5.1.5.1.1` |
| `0x456` Trap Recipient 2（启用） | `0x4fa8` | 75 | `40.26.5.1.7.1.2` |
| `0x430` Trap Community 2 | `0x4fac` | 76 | `40.26.5.1.4.1.2` |
| `0x462` Trap IP address 2 | `0x50b0` | 77 | `40.26.5.1.2.1.2` |
| `0x438` Add paper | `0x51b4` | 78 | `40.26.5.1.5.1.2` |
| `0x439` Toner near empty | `0x51b8` | 78 | `40.26.5.1.5.1.2` |
| `0x43a` Add toner | `0x51bc` | 78 | `40.26.5.1.5.1.2` |
| `0x43b` Cover open | `0x51c0` | 78 | `40.26.5.1.5.1.2` |
| `0x43c` Paper jam | `0x51c4` | 78 | `40.26.5.1.5.1.2` |
| `0x43d` All other errors | `0x51c8` | 78 | `40.26.5.1.5.1.2` |

厂商 OID 名称直接支持该分组：`40.26.5.1.7` = `kmsvTrapEnabled`、
`.4` = `kmsvTrapCommunity`、`.2` = `kmsvTrapIpAddress`、
`.5` = `kmsvTrapEvents`。事件项在模型中是 6 个连续字段，不是单一位掩码；
`item 74` 的偏移依次为 `0x4f90/0x4f94/0x4f98/0x4f9c/0x4fa0/0x4fa4`，
`item 78` 为 `0x51b4/0x51b8/0x51bc/0x51c0/0x51c4/0x51c8`。

MA2000w 只读配置值：`item 70 = 2`（`snmpEnableAuthenTraps` disabled）、
`item 71/75 = 0`（两个收件人均未启用）、`item 72/76 = public`、
`item 73/77 = 0.0.0.0`、`item 74/78 = 0`（无事件）。这些值来自只读 SNMP，
没有据此做任何写入。

静态路径依据：主对话框在 `FUN_00405c10` 中从 `esp+0x3570/0x3574/
0x3578/0x3584/0x3588/0x358c/0x3590..0x3598/0x41d0/0x41d4` 读取模型字段并
设置对应控件；Communication 在 `FUN_0041ccb0` 中读取
`0x4444/0x444c/0x485c/0x4860/0x4864/0x4868/0x486c/0x4970/0x4550/0x4654/
0x4758/0x4a74/0x4b78/0x4c7c`；Panel options 通过共享全局
`DAT_004a9fd4/DAT_004a61b8/DAT_004a61b4` 接收主对话框从
`0x3c58/0x3020/0x301c` 读出的值。

这些映射仍是 `confidence=inferred`：静态路径直接、且与 MA2000w 的只读值一致，
但尚未做写入回读。只读值交叉核对包括：item 54 = `KMD4E4BA`（hostname，实际
名称不写入仓库）、59/60/61 = `192.168.0.220 / 255.255.255.0 / 192.168.0.1`、
65/66 = `public`、52 = `60`（界面显示 `300 s`，即 `model * 5`）、49 = `3`
（打印浓度组合框 index `2`）、85 = `18`（面板自动清除 `90 s`）、86 = `2`、
87 = `8`、83 = `8`。

`0x3f6` Paper weight 由媒体类型查表推导，未找到独立 OID；`0x46d/0x46e`
（On/Off）与 `0x4da`（`Duplex` 静态标签）只在自定义纸张记录下可见，其状态来自
该记录的 `+0x20c` 字段，尚不能把它单独绑定到某个 OID，继续保留为未知。

Wi‑Fi 状态页（dialog `0x00f3`，页面过程 `FUN_00403e80`）：

| 控件 | 模型偏移 | item_id | OID | 页面语义 |
| --- | --- | --- | --- | --- |
| `0x4fa` Connection status | `0x3c88` | 142 | `40.42.1.1.1.1` | `3` = Connected，其余 = Not connected |
| `0x4fb` SSID | `0x3c90` | 144 | `40.42.1.1.4.1` | `FUN_0040dae0` 读取 `DAT_004ae520` |
| `0x4fc` Security Information | `0x3d94` | 145 | `40.42.1.1.5.1` | 枚举 `0..4`，其他为 Unknown |
| `0x4fd` Channel | `0x3d98` | 147 | `40.42.1.1.6.1` | 十进制信道号 |
| `0x4fe` RSSI | `0x3d9c` | 146 | `40.42.1.1.7.1` | 负值 dBm，按 `-49/-60/-70` 分档 |

`0x458/0x459`（Wi‑Fi On/Off）由 `DAT_004aa074` 和栈上的 `0x3c84` 状态控制；
`0x3c84` 对应 item 90（`1001.2.2.1.1.1.1`），但尚未确认它与
`40.42.1.1.3.1` 的关系，因此这两个单选按钮继续保留为未知，不按位置猜测。

音量对话框（dialog `0x00d1`，`FUN_00416890`）：

| 控件 | 模型偏移 | item_id | OID | 说明 |
| --- | --- | --- | --- | --- |
| `0x4d7` Speaker volume | `0x3da0` | 108 | `45.8.1.1.11.4` | 数字编辑框，`DAT_004a6a40`，范围 `0..5` |
| `0x4d8` Speaker slider | `0x3da0` | 108 | `45.8.1.1.11.4` | `0x4d7` 的 trackbar |
| `0x4da` Monitor volume | `0x3da4` | 109 | `45.8.1.1.10.4` | 数字编辑框，`DAT_004a6a3c`，范围 `0..5` |
| `0x4db` Monitor slider | `0x3da4` | 109 | `45.8.1.1.10.4` | `0x4da` 的 trackbar |

FAX notification 对话框（dialog `0x00d2`，`FUN_00416f70`）：

| 控件 | 模型偏移 | item_id | OID | 说明 |
| --- | --- | --- | --- | --- |
| `0x4dd` Transmission notification | `0x3db0` | 112 | `45.10.3.1.2.4` | combo index = model - 1 |
| `0x4de` Attach copy of TX | `0x3db4` | 113 | `45.10.3.1.3.4` | 初始化时 model `3` = checked |
| `0x4e0` Receiving notification | `0x3db8` | 114 | `45.9.3.1.2.4` | combo index = model - 1 |
| `0x4e2` TX report | `0x3da8` | 110 | `45.10.3.1.1.4` | 初始化时 model `3` = checked |
| `0x4e3` RX report | `0x3dac` | 111 | `45.9.3.1.1.4` | 初始化时 model `3` = checked |

FAX 设置页 `FUN_004144c0` 从栈地址 `0x3da8..0x3dc0` 读取这些值；该栈帧中的
模型副本满足“栈地址 = 模型偏移 + 8”（如 `0x3da8 - 8 = 0x3da0`）。在这个统一
偏移下，7 个字段分别落到 item 108–114，并与厂商名称
`kmFaxDeviceSpkVolumeLevel`、`kmFaxDeviceLMvolumeLevel`、
`kmFaxTxReportEnable`、`kmFaxRxReportEnable`、`kmFaxTxResultReportEnable`、
`kmFaxTxResultReportAttachedImage`、`kmFaxRxResultReportEnable` 逐项吻合。
因此这些映射标为 `confidence=inferred`：静态路径和名称一致，但尚未做写入回读。

### 6.7 对象索引与模型偏移

`FUN_0040e820` 在收到一个配置值后，先由 `FUN_00410380` 把 OID 转成
0..146 的对象索引，再把值写入 `param_1 + offset`。`FUN_00410740` 则用同一组
偏移比较“当前值”和“界面值”，并把变化项按 147 行对象表顺序编码成
`KGETOBJ`/`KSETOBJ` 数据。两条路径的偏移一致，因此这张表是控件与 OID 之间的
关键中间层。

可复现工具：

```bash
python3 tools/clienttool_config_offsets.py
```

生成数据：
`docs/reverse-engineering/data/clienttool-config-offsets.tsv`。当前 147/147 项
都有至少一个模型偏移；自定义纸张和若干位图/复合字段有多项偏移。

关键行：

| item_id | OID（相对 1347） | 模型偏移 | 含义 |
| --- | --- | --- | --- |
| 2 | `43.5.1.1.34.1` | `0x0004` | Auto error clear |
| 3 | `43.5.1.1.35.1` | `0x0008` | Auto error clear timeout |
| 1 | `43.5.1.1.23.1` | `0x0010` | Sleep time |
| 4 | `42.5.1.1.43.1` | `0x0014` | Power off timer |
| 50 | `1001.2.1.1.1.14.1` | `0x0018` | Quiet mode |
| 52 | `43.5.1.1.22.1` | `0x2ffc` | Form feed timeout |
| 59 | `40.10.1.1.4.1` | `0x4550` | IPv4 address |
| 60 | `40.10.1.1.6.1` | `0x4654` | Subnet mask |
| 61 | `40.10.1.1.7.1` | `0x4758` | Default gateway |
| 65 | `40.26.2.1.3.1` | `0x486c` | SNMP read community |
| 66 | `40.26.2.1.4.1` | `0x4970` | SNMP write community |
| 144 | `40.42.1.1.4.1` | `0x3c90` | Wi‑Fi SSID |

生成工具依赖本地 Ghidra 导出的
`analysis/decompiled/KMUTLCFG/c/0040e820_FUN_0040e820.c`；该目录不进入版本
控制。数据表本身已提交，测试会检查 147 行、关键偏移以及工具输出与数据表一致。
主对话框、Panel options 和 Communication 三个对话框的控件映射已完成第一轮；
剩余对话框（SNMP trap、通知、传真/纸张自定义等）仍需按对话框模板和各自的
初始化函数逐个对齐。

## 7. 预设协议（KMUTLPRE.exe）

### 7.1 对象模型

`KMUTLPRE.exe` 的预设对象表位于 `0x005048d8`，每行 16 字节：

```text
uint32 item_id
char  *oid_format
uint32 flags
uint32 tag
```

完整表见
`docs/reverse-engineering/data/clienttool-preset-objects.tsv`。
表中混合了两类行：

- 36 行是 OID 模板，均位于 `1.3.6.1.4.1.1347.1001.1.*`，PJL 写法使用
  `#<绝对 OID>`；
- 20 行是本地字段名（`SavePath`、`FileFormat`、`OutputName`、
  `JpegQuality`、`ImgSize`、`ImgPos`、`ClrMode`、`Rez`、`ImgType`、
  `Sharpen`、`Invert`、`Bright`、`Orientation`、`AutoDensity`、
  `HCPdfQuality`、`FileSeparation`、`PdfA1Type`、`PINCode%d`、
  `PrtBox%d` 等），用于 UI 数据模型与 OID 行的关联，不是可直接发送的
  设备对象。

已还原的子域：

| 子域 | 作用 | 列/索引 |
| --- | --- | --- |
| `1001.1.2.1.1.<col>.<preset>` | 扫描基础设置 | col 2..15 |
| `1001.1.3.1.1.<col>.<preset>` | 输出图像/文件设置 | col 2..7 |
| `1001.1.4.1.1.<col>.<preset>` | 原稿设置 | col 2..5 |
| `1001.1.4.2.1.1.<col>.<a>.<b>` | 原稿尺寸/多页相关 | col 2..5、8 |
| `1001.1.5.1.1.<col>.<preset>` | Print Box/传真预设 | col 2..8 |

### 7.2 当前预设与类别

`FUN_0041aad0` 的“恢复默认”逻辑给出类别到对象的映射：

| 类别 | 对象 | MA2000w 实测 |
| --- | --- | --- |
| Copy | `1001.1.1.6.0` | `0` |
| Scan | `1001.1.1.7.0` | `0` |
| Fax | `1001.1.1.8.0` | `NoSuchObject`（机型无传真） |
| Print Box | `1001.1.1.9.0` | `0` |

值为 `0` 表示当前没有选中预设。

### 7.3 预设启用/锁定

| 对象（完整） | 作用 | 证据 |
| --- | --- | --- |
| `1.3.6.1.4.1.1347.1001.1.4.1.1.1.6.<preset>` | 预设启用标志 | `FUN_0041a840`/`FUN_0041a990` |
| `1.3.6.1.4.1.1347.1001.1.1.10.0` | 预设安全锁 | `FUN_00419530`；MA2000w 返回 `L` |

`FUN_00419530` 在解锁时写入空字符串，在加锁时写入 15 个 `F` 字符
（`FFFFFFFFFFFFFFF`）。MA2000w 当前值 `L` 的完整业务含义尚未确认，只能
确定它是预设安全锁对象。

### 7.4 读取/写入通道

- 网络：`snmpget`/`snmpset`，对象为完整绝对 OID。
- USB：`@PJL KGETOBJ OBJ="#<oid>"` / `@PJL KSETOBJ OBJ="#<oid>" VALUE=<value>`。
- `KMQSEnablePreset`、`KMQSDisablePreset`、`KMQSSet`、`KMQSGet` 等符号位于
  `KMUTLPRE.exe` 字符串中，对应预设启用/禁用和读写封装；具体导出/调用边界
  尚未完全还原。

## 8. Print Box 与 Push Scan 远程操作

### 8.1 私有对象

`KMSTMNET.exe` 和 `KMSTMVM.exe` 共同使用以下对象：

| 子域 | 对象 | 含义 | 实测/证据 |
| --- | --- | --- | --- |
| Print Box | `1001.3.1.1.0` | 网络接口/命令类型 | 实测 `0` |
| Print Box | `1001.3.1.2.0` | 网络目标 IP | 实测 `0.0.0.0` |
| Print Box | `1001.3.1.3.0` | 操作结果 | 写入 0..5 |
| Print Box | `1001.3.1.4.0` | PIN 输入 | - |
| Print Box | `1001.3.1.5.0` | IPv6 地址 | - |
| Print Box | `1001.3.1.6.0` | 主机名 | - |
| Print Box | `1001.3.1.7.0` | 默认网络源 | - |
| Push Scan | `1001.4.1.1.0` | 网络接口 | 实测 `0` |
| Push Scan | `1001.4.1.2.0` | 目标 IP | 实测 `0.0.0.0` |
| Push Scan | `1001.4.1.3.0` | 操作结果 | 写入 0/1 |
| Push Scan | `1001.4.1.4.0` | IPv4 地址（字符串形式） | - |
| Push Scan | `1001.4.1.5.0` | IPv6 地址 | 实测空字符串 |
| Push Scan | `1001.4.1.6.0` | 接口/目标类型 | 实测 `1` |

### 8.2 结果码

`FUN_004b2070`/`FUN_004b2180` 写 `1001.3.1.3.0`：

```text
0 = ACCEPTED
1 = NO DATA
2 = NO FOLDER
3 = WRONG PIN
4/5 = PIN 结果分支
```

`FUN_004b14f0` 写 `1001.4.1.3.0`：

```text
0 = NG
1 = OK
```

### 8.3 KPUSHSCAN

`KMSTMVM.exe` 的 `FUN_00419570` 在 USB/本地路径发送：

```text
@PJL KPUSHSCAN STATUS=OK
```

或：

```text
@PJL KPUSHSCAN STATUS=NG
```

网络路径则通过 `KMSTMNET.exe` 写 `1001.4.1.3.0`，不再发送 TCP PJL。

## 9. 维护协议（KMUTLMNT.exe）

`KMUTLMNT.exe` 是维护菜单解释器。它读取维护包（`UserPackage.mtp` 或用户
选择的 `*.mtp`），把包中的 `MaintenancePackage/Define/...` 定义转换成
请求记录，再通过两条通道发送：

- 网络：`PrnRawPortComm`，TCP **9100** RAW 端口；
- 本地：`PrnUSBComm`，通过 USB 锁和打印机通道发送。

网络发送函数 `FUN_0040ce20` 直接调用 Winsock `connect`/`send`/`recv`；
端口常量 `0x238c` = 9100。接收缓冲区为 `0x14000` 字节，发送后最多等待
约 3 秒读取响应。USB 路径读取响应后检查其中是否包含 ASCII `KPSL`。

### 9.1 KPSL 帧头

帧头由 `FUN_004ab0a0` 构造，固定 20 字节：

```text
offset  size  value / meaning
0x00    4     "KPSL"
0x04    4     1B 24 30 4D        (ESC $ 0 M)
0x08    4     uint32 BE word_count
0x0c    4     40 40 40 40        ("@@@@")
0x10    4     uint32 BE payload_length
0x14    ...   payload
```

`word_count` 的计算方式为：

```text
aligned = payload_length aligned up to 4 bytes
word_count = aligned / 4 + 1
```

`word_count` 和 `payload_length` 都按大端写入。响应解析函数
`FUN_004aa180` 会校验 `"KPSL"`、`1B 24 30 4D`、`"@@@@"` 三个固定标记。

### 9.2 载荷与校验和

载荷由三部分组成：

```text
12 字节控制头（3 个 uint32 BE）
N 个记录（每条 0x18 字节头 + 参数数据）
4 字节校验和（uint32 BE）
```

控制头的第一个 dword 是记录数；解码器 `FUN_004a9ef0` 用它循环解析记录。
另外两个 dword 的含义尚未通过动态样本确认。

每条记录头为 6 个 uint32 BE，编码函数 `FUN_004aac90` 设置的请求字段为：

| 偏移 | 请求中的含义 | 证据 |
| --- | --- | --- |
| `0x00` | action | `# Request # action:[%d]` |
| `0x04` | request id | `req_id:[0x%08X]` |
| `0x08` | result/保留（请求为 0） | 编码函数置 0 |
| `0x0c` | prohibition 位图 | `prohibition:[0x%08X]` |
| `0x10` | 保留（请求为 0） | 编码函数置 0 |
| `0x14` | 参数类型 `param_kind` | `param_kind:[%d]` |

响应解码器 `FUN_004aa480` 读取同样的 6 个字段，但日志顺序是
`Act/Req/Result/proh/kind`，即它把 `[1]` 当作 action、`[2]` 当作 req_id、
`[3]` 当作 result、`[4]` 当作 prohibition、`[5]` 当作 kind。请求与响应的
字段对齐存在一档偏移，需用真实维护包/设备响应确认；目前只把“6 个
大端 dword + 参数”作为已验证的通用结构。

校验和由 `FUN_004aaed0` 写入、`FUN_004aa2e0` 校验：

- 对载荷中除最后 4 字节外的数据按偶数字节、奇数字节分别求和；
- 若剩余一个字节，也加入总和；
- 把总和按大端写入载荷最后 4 字节。

### 9.3 载荷混淆

发送前 `FUN_004ab110` 对载荷做原地滚动 XOR；接收后
`FUN_004ab1c0` 做逆变换。变换使用一张 256 项 CRC 表和一个固定种子字符串
（具体值不公开）。因此 KPSL 帧不是明文 XML，
也不是简单 zlib；直接按文本搜索维护项不会得到结果。编码顺序是“先写
校验和，再混淆整个载荷”，解码顺序相反。

### 9.4 参数类型表

`0x004e7900` 处有 20 项参数类型表，每项 0x18 字节：

```text
uint32 kind
uint32 fixed_size       (0xffffffff = variable)
void  *create/decode
void  *free
void  *encode
void  *size
```

已还原的 kind 与尺寸：

| kind | 固定尺寸 | 对应构造/处理 | 含义 |
| --- | --- | --- | --- |
| 1 | 4 | `mnte_CreateFixedLengthParam` | 4 字节定长值 |
| 2 | 0xc | 同上 | 3 个 dword |
| 3 | 变长 | `mnte_CreateStringData` | 字符串 |
| 4 | 变长 | `mnte_CreateBinaryData` | 二进制块 |
| 5 | 0xc | 定长 | 3 个 dword |
| 6 | 变长 | `mnte_CreateEngineIFVariableData` | 引擎接口变量 |
| 7 | 变长 | `mnte_CreateEngineIFOperationData` | 引擎接口操作 |
| 8 | 8 | 定长 | 2 个 dword |
| 9 | 0x14 | 定长 | 5 个 dword |
| 10 | 0xc | 定长 | 3 个 dword |
| 11 | 8 | 定长 | 2 个 dword |
| 12 | 变长 | `mnte_CreateEntityGetString_Response` | 读字符串响应 |
| 13 | 变长 | `mnte_CreateEntitySetString` | 写字符串 |
| 14 | 8 | 定长 | 2 个 dword |
| 15 | 变长 | `mnte_CreateEntityGetBinary_Response` | 读二进制响应 |
| 16 | 变长 | `mnte_CreateEntitySetBinary` | 写二进制 |
| 17 | 4 | 定长 | 4 字节值 |
| 18 | 4 | 定长 | 4 字节值 |
| 19 | 8 | 定长 | 2 个 dword |
| 20 | 0x48 | 定长 | 0x48 字节结构 |

kind 3/4/12/13/15/16 的实际长度由参数内的长度字段决定；kind 6/7 还带有
引擎接口操作/变量结构。

### 9.5 维护包

`KMUTLMNT.exe` 用 Expat 解析 `MaintenancePackage` XML，关键节点包括：

```text
MaintenancePackage/Define/ItemData
MaintenancePackage/Define/ExecutePreprocess
MaintenancePackage/Define/ExecutePolling
MaintenancePackage/Define/ExecuteDispEnter
MaintenancePackage/Define/ExecuteDispExit
MaintenancePackage/Define/ExecuteTerminate
MaintenancePackage/Define/RequestParameter
MaintenancePackage/Define/RequestParameter/ItemID
MaintenancePackage/Define/RequestParameter/ParamKind
MaintenancePackage/Define/RequestParameter/Str
MaintenancePackage/Define/RequestParameter/Value
```

维护包是加密容器。公开资料只保留请求类型、request id、item id、数据类型
和来源序号；密钥、IV、容器布局、解包代码以及提取出的 XML/PNG 均按本地
研究材料处理，不进入公开仓库。完整的 39 行互操作性清单见
`docs/reverse-engineering/data/clienttool-maintenance-requests.tsv`。

可按类别理解维护请求：

| 类别（自写说明） | 主要 request id |
| --- | --- |
| 图像质量参数与刷新 | `MNTE_REQUEST_ID_CHARGER_CORRECTION_VALUE`、`MNTE_REQUEST_ID_HIGH_ALTITUDE_MODE`、`MNTE_REQUEST_ID_DRUM_REFRESH` |
| 计数器复位 | `MNTE_REQUEST_ID_DRUM_COUNTER_RESET` |
| 打印位置校准 | `LEFT_PRINT_TIMING`、`TOP_PRINT_TIMING`、`LEFT_DUPLEX_PRINT_TIMING`、`TOP_DUPLEX_PRINT_TIMING`、`C_SIZE_CUT_AMOUNT`、`A_SIZE_CUT_AMOUNT`、`LEAD_SIZE_CUT_AMOUNT`、`TRAIL_SIZE_CUT_AMOUNT` |
| 扫描位置校准 | `PLATEN_LEAD_TIMING`、`DP_LEAD_TIMING`、`A/B/C/D_MARGIN_SIZE_CUT_AMOUNT_PLATEN`、`A/B/C/D_MARGIN_SIZE_CUT_AMOUNT_DP` |
| 恢复出厂与同步 | `MNTE_REQUEST_ID_RESTORE_FACTORY_INITIALIZE`、`MNTE_REQUEST_ID_SYNC` |

符号 request id 到数值的映射位于 `KMUTLMNT.exe` 的 `.data` 表，共 177 项。
例如：

| 符号 | 数值 |
| --- | --- |
| `MNTE_REQUEST_ID_HIGH_ALTITUDE_MODE` | `0x0003001e` |
| `MNTE_REQUEST_ID_DRUM_REFRESH` | `0x00060003` |
| `MNTE_REQUEST_ID_DRUM_COUNTER_RESET` | `0x0006000f` |
| `MNTE_REQUEST_ID_RESTORE_FACTORY_INITIALIZE` | `0x00030031` |

完整映射见
`docs/reverse-engineering/data/clienttool-maintenance-request-ids.tsv`，
可用 `tools/clienttool_request_ids.py` 重新提取。

请求类型分为：

- `RequestValue`：读写一个值（如 Drum charge、Altitude、打印/扫描位置）；
- `RequestExec`：执行动作（如鼓组件刷新、计数器复位、恢复出厂设置）；
- `RequestResult`：读取执行结果。

恢复出厂设置、计数器复位和鼓组件刷新都会改变设备状态，本轮没有向设备发送
这些请求。

### 9.6 与 PJL/SNMP 的边界

- 维护菜单不发送 `@PJL`，也不使用 SNMP。
- 它使用的 TCP 9100 只是 RAW 传输端口；载荷是 KPSL 二进制帧，不是 PJL。
- USB 路径同样使用 KPSL；`PrnUSBComm` 明确检查响应中的 `KPSL` 标记。
- 本轮没有向设备发送任何 KPSL 请求，避免触发维护/清除动作。

## 10. 设备发现与打印机枚举

静态分析未发现 Client Tool 自己的局域网发现协议：

- `KMSTMVM.exe` 用 `EnumPrintersW` 枚举本机打印机，要求端口支持双向通信。
- `KMSTMNW.exe` 的日志函数为 `EnumInstalledPrinters`。
- `KMUTLCFG.exe` 使用 `EnumPortsW` 和打印端口信息。
- 网络地址来自 Windows 打印端口，不来自 SNMP 广播或 WSD。

因此，项目现有的 SNMP 广播 + WS-Discovery 发现是 Linux 复刻新增能力，
不是对 Client Tool 行为的复刻。文档中不应把二者混为一谈。

## 11. Linux 实现映射

### 11.1 只读监视

推荐优先级：

1. SNMP 读取（与 Client Tool 网络路径最接近）：机型、状态、耗材、纸盒、
   告警、计数器、网络信息。
2. TCP 9100 PJL `KGETOBJ`（设备支持时）：作为补充，特别是私有
   `1001.*` 对象。
3. USB `usblp` + UEL PJL：物理验证后启用。

### 11.2 配置读取

- SNMP 批量 GET 是首选；按对象类型解码。
- 若要兼容只开放 9100 的设备，使用 `KGETOBJ` 批量帧，并按 `TYPE=4/64`
  做十六进制解码。
- 需要处理单对象失败：SNMPv1 的 `noSuchName` 会使整个请求失败，应退回
  单对象或 v2c；PJL 则在每段响应中单独给出 `STATUS`。

### 11.3 配置写入

本轮没有实现任何写入。若后续实现，必须：

- 先读取完整基线并保存；
- 只写变更项；
- 处理 `STATUS`/SNMP error-index；
- 明确重置对象的副作用（`1347.40.1.1.1.6.1=2` 或
  `prtGeneralReset=4/6`）；
- 提供回滚路径。

### 11.4 维护菜单

维护包已可离线解包，可先实现只读的菜单/request 清单展示。不建议在 KPSL
字段对齐和副作用验证完成前实现维护写入；恢复出厂设置、计数器复位和鼓组件
刷新可能清除计数器、改写引擎参数或触发
测试动作，必须提供完整基线、备份和回滚方案。

## 12. 证据等级

| 结论 | 等级 | 证据 |
| --- | --- | --- |
| 网络监视使用 SNMP，不使用 9100/HTTP/SOAP | 已验证 | `KMSTMNET.exe` 反编译、导入表、无 9100/HTTP 字符串 |
| `KMSTMNET` 合成 PJL 文本 | 已验证 | `0x004b3990`、`0x004b5c30`、`0x004b5e60`、`0x004b5120` |
| 147 行配置对象表 | 已验证 | `0x00498244` 静态表 + `tools/clienttool_oids.py` |
| `1.`/`#` 前缀规则 | 已验证 | 反编译分支 + 设备 PJL 实测 |
| `TYPE=4/64` 十六进制编码 | 已验证 | 设备 PJL 实测 |
| 私有 `1001.1/1001.3/1001.4` 对象存在 | 已验证 | 设备 SNMP/PJL 只读实测 |
| 维护协议使用 KPSL over TCP 9100/USB | 已验证 | `FUN_0040ce20` 端口 `0x238c`、`PrnUSBComm` KPSL 检查 |
| KPSL 帧头/校验和/混淆 | 已验证（静态） | `FUN_004ab0a0`、`FUN_004aaed0`、`FUN_004ab110` |
| 20 项维护参数类型表 | 已验证（静态） | `0x004e7900`、构造/编解码函数 |
| Print Box/Push Scan 结果码语义 | 较高可信度 | 反编译分支 + 字符串标签，尚未逐一写入验证 |
| `type_code=6` 为 MAC | 待验证假设 | 表位置与编码推断 |
| 预设安全锁 `L` 的具体含义 | 未知 | 只确认对象存在和加/解锁写法 |
| 维护包目录提取 | 已验证（本地离线） | 只公开 request id、item id 和数据类型；密钥与提取物不公开 |
| 维护 request id / item id | 已验证（来自包内 XML） | 39 行请求清单，`clienttool-maintenance-requests.tsv` |
| 符号 request id → 数值 | 已验证（静态表） | 177 项，`clienttool_request_ids.py` |
| 147 项配置只读导出 | 已验证 | MA2000w 96/147 `STATUS=0`，`--config` 实测 |
| `TYPE=4` NUL 填充与 UTF-8 | 已验证 | 自定义纸张名称、Wi‑Fi SSID 实测 |
| `40.42.1.1.7.1` 为 RSSI | 已验证（静态 + 真机值） | Wi‑Fi 页 `0x4fe` 读取 `DAT_004ae62c` 并按 `-49/-60/-70` 分档；真机 `-70/-71` |
| `40.42.*` 六个字段的语义 | 已验证（静态 + 真机值） | `FUN_00403e80` 控件、模型基址 `0x4aa890`、`FUN_0040e820` 偏移和 MA2000w 只读值一致 |
| 两份 `snmp-oid.xml` 合并覆盖 | 已验证（静态） | 约 500 个唯一 OID；147 项中 127 有名称，20 项两份均未描述 |
| remotefax 独有 OID 在 MA2000w 上不可用 | 已验证（只读） | `kmFaxDeviceExist`、`kmTimeZone*`、`kmFirmwareDetail*` 等全部 `no such object`；同请求已知 OID 正常返回 |
| `JobSnmpOid.xml` 展开 | 已验证（静态） | 205 个唯一绝对 OID；5 个绝对、200 个相对，无重复 |
| MA2000w 作业子树可读性 | 已验证（只读） | walk `1347.47` 返回 0 行，对照 Wi‑Fi 子树返回 7 行 |
| ClientTool 全量文本 OID | 已验证（静态扫描） | 827 个唯一 OID、40 个文件、1708 次出现；616 精确名称、61 祖先名称、91 个第三方库常量、59 个无名称设备 OID |
| `KMSNMP4.INI` 名称表 | 已验证（静态） | 116 个 `INFO_*` 名称、108 个唯一 OID、144 行 |
| UI 控件标签/组合框表 | 已验证（静态） | `KMUTLCFGRes.dll` RT_STRING + `0x496f20`/`0x497048` |
| Sleep time / Power off timer / Quiet mode | 较高可信度（推断） | 控件语义 + 模型偏移 + 真机值 `1`/`72`/`0`，未写入回读 |
| 147 项对象索引→模型偏移 | 已验证（静态） | `FUN_0040e820` + `FUN_00410740`，147/147 映射 |
| 147 项配置 SNMP 后备读取 | 已验证 | 睡眠状态 96/147，SNMPv2c，约 8.6 秒 |
| KPSL 请求/响应字段对齐 | 待验证假设 | 请求编码器与响应解码器日志顺序存在一档偏移 |

## 13. 未解决问题

1. `KMSTMNET.exe` 的 SNMPv1/v2c 选择策略：是否先试 v2c、失败回退 v1。
2. `1001.2.*` 各配置对象的完整业务名称；147 项已可只读导出，UI 控件字符串
   表和对象→模型偏移表已提取，下一步是把控件 ID 对齐到模型偏移。
3. `1001.1.2/3/4/5` 各列的完整设置语义和取值范围。`KDS337110.dat` 已按
   `0x40100` 格式解析出图形/布局和数值块，但没有可直接对应 147 项配置的
   名称表。
4. `KPUSHSCAN` 的完整状态机，以及设备何时清除 `1001.4.1.3.0`。
5. 维护包已解包，但 KPSL 请求/响应记录字段的一档偏移、`ParamKind` 到
   JSON/XML 字段的精确映射仍需真实帧验证；恢复出厂设置、计数器复位等动作
   也未做设备副作用测试。
6. Wi‑Fi 页 `0x458/0x459`（On/Off）的选中状态来自栈上 `0x3c84`（item 90），
   它与 `40.42.1.1.3.1` 的关系尚未确认；字段本身已可只读。
7. 没有 Windows 运行环境，未对真实 Client Tool 做动态抓包；SNMP PDU 的
   精确顺序、重试和超时来自静态代码与 Linux 侧等价查询，尚未逐包对照。

