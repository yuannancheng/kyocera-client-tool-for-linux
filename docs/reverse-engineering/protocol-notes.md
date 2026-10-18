# 协议记录：MA2000w

## 1. 传输与帧格式（已验证）

测试设备：`192.168.0.220`，型号 `MA2000w`，MAC `00:17:C8:XX:XX:XX`（已脱敏）。

PJL 可通过 TCP 9100 直接访问。帧格式与反编译 `FUN_00417150` 一致：

```text
<UEL>\r\n
@PJL <command>\r\n
...
<UEL>\r\n
```

其中 `<UEL>` 为 `ESC %-12345X`（字节 `1b 25 2d 31 32 33 34 35 58`）。
设备在每个响应段后返回 `0x0c`（form feed）。

该帧格式由 `KMSTMVM.exe` 的 `0x00417150` 汇编直接确认：函数两次压入 `0x1b`
和字符串 `%-12345X`，格式串位于 `0x0042925c`，内容为
`%c%s\r\n%s\r\n%c%s`。

实测：

```text
@PJL INFO ID
"MA2000w"
```

```text
@PJL INFO STATUS
CODE=35078
DISPLAY="Sleeping...
 "
ONLINE=TRUE
```

`CODE=35078` 在反编译逻辑中属于非警告状态码；显示文本表示设备处于睡眠。

### 1.1 USB/本地路径

Windows 端 USB 打印机不使用 TCP 9100，也不由 `KMSTMVM.exe` 直接打开 USB
设备节点。程序通过 Kyocera 语言监视器的 mailslot 通道发送同一套 UEL PJL 帧：

- 连接时发送 `@PJL USTATUS DEVICE=ON`、`@PJL USTATUS JOB=ON`、
  `@PJL INFO ID`；
- 之后 `Refresh`（`FUN_0041a3a0`）在本地路径发送 14 条查询，不重复发送
  `INFO ID`，也不发送 `KINTRAYSTATUS`；
- PJL 帧由 `FUN_00417150` 构造后，经 `CreateFileW`/`WriteFile` 写入
  `\\.\mailslot\kyocera\mita\<channel>`；
- 真正的 USB 批量传输在语言监视器/打印机驱动侧，静态分析无法确认其是否对帧
  做额外封装。

Linux 复刻使用 `/dev/usb/lp*` 的 `usblp` 字符设备直接发送同样的 UEL 帧；
`--usb` 会自动读取 sysfs 中的 VID/PID，并把 `@PJL INFO ID` 放在聚合序列
最前（随后 15 条查询，含 `KINTRAYSTATUS`）；只读实现不发送 `USTATUS`。
该路径的物理一致性尚未验证，详见
`docs/reverse-engineering/usb-path.md`。

## 2. 原程序的查询序列

从 `KMSTMVM.exe` 的 `FUN_0041a3a0` 与 `FUN_0041a960` 还原：

```text
@PJL INFO CONFIG
@PJL INFO KCONFIG
@PJL INFO KNETWORKSTATUS
@PJL INQUIRE TIMEOUT
@PJL INFO KUNITNAME
@PJL INFO KINTRAYSTATUS
@PJL INFO ID
@PJL INFO STATUS
@PJL KGETOBJ OBJ="1.42.5.1.1.16.1"
@PJL KGETOBJ OBJ="2.5.1.1.10.1"
@PJL KGETOBJ OBJ="1.43.5.1.1.34.1"
@PJL KGETOBJ OBJ="1.43.5.1.1.35.1"
@PJL KGETOBJ OBJ="2.10.2.1.4.1.1"
@PJL KGETOBJ OBJ="1.43.10.1.1.8.1.1"
@PJL KGETOBJ OBJ="1.43.10.1.1.14.1.1"
@PJL KGETOBJ OBJ="1.46.10.1.1.5.3"
```

原程序在连接时还会发送 `@PJL USTATUS DEVICE=ON` 与 `@PJL USTATUS JOB=ON`
启用异步状态上报。Linux 复刻默认不发送这两条，因为它们会改变设备的通知状态；
当前实现只做只读轮询。

### 2.1 网络路径修正（第十四轮）

上述 PJL 查询序列来自 `KMSTMVM.exe` 的 USB/本地语言监视器路径。Windows
Client Tool 的网络路径由 `KMSTMNET.exe` 负责，它使用内嵌 Net-SNMP 轮询
设备，不连接 TCP 9100；`KMSTMNET.exe` 会把 SNMP 值合成为
`INFO ID`/`INFO CONFIG`/`KGETOBJ`/`USTATUS DEVICE` 文本，再经 mailslot
交给 `KMSTMVM.exe`。因此，网络路径中的 PJL 文本是内部中间格式，不是设备
实际返回的 PJL。

Linux 侧继续使用 TCP 9100 PJL 是可行的协议等价路径（已在 MA2000w 验证），
但不应把它描述成 Client Tool 网络路径的原样复刻。完整拆解见
`docs/reverse-engineering/clienttool-protocol.md`。

## 3. 实测响应（MA2000w，2026-10-18）

完整查询的响应要点：

- `INFO CONFIG`：2 个进纸盒（Single Bypass、Main Tray），A4/PLAIN；
  序列号存在（本文档脱敏为 `H4933*****`）；固件
  `2022.08.22 2YW_2000.001.101`。
- `INFO KCONFIG`：`BLACK TONER LEVEL=80%`、`BLACK COVERAGE=6.17%`、
  `ENGINE VERSION=2Y8_1000.001.302`。
- `INFO KNETWORKSTATUS`：`NET 192.168.0.220 / 192.168.0.1 / 255.255.255.0`。
- `INQUIRE TIMEOUT`：`300`。
- `INFO KUNITNAME`：`"?"`。
- `INFO KINTRAYSTATUS`：两个纸盒均为 `OK`，`REMAIN=UNKNOWN`。
- `KGETOBJ`：原样保留 `STATUS`/`TYPE`/`VALUE`，见
  `kyocera_monitor/parser.py` 的 JSON 输出。

原始文本样本见 `docs/reverse-engineering/samples/ma2000w-pjl.txt`（序列号已脱敏）。

### 3.1 部分响应与分段重试（2026-10-18 实测）

设备在唤醒或高频轮询时会丢弃一批查询的尾部。同一天连续两次采集得到：

- 一次只返回 `INFO CONFIG` 与 `INFO KINTRAYSTATUS`，型号、状态、`KCONFIG`、
  网络和全部 `KGETOBJ` 缺失；旧实现整包重试两次后耗时 17.3 秒，第二次仍然
  缺段。
- 另一次返回全部 16 段，耗时 5.1 秒（等待尾部静默直到总超时）。

复刻实现现在按 `@PJL` 回显把响应切成独立段，只重发缺失的命令，并按原查询
顺序合并。接收端在出现数据后若连续 `--idle` 秒没有新字节，就返回已收到的
部分响应，不再等满 `--timeout`。因此：

- 单次完整采集实测 0.73 秒；
- 以 0.5 秒间隔连续轮询 5 次，输出保持同一份完整快照，没有出现缺段快照
  （总耗时 18.4 秒，说明部分轮次触发了补发）。

该行为只证明“缺段可被检测并补发”，不代表设备保证每批查询都完整。

## 4. 状态码处理

反编译 `FUN_0041b290` 显示：

- 被视为非警告的 `CODE`：`10001`、`10002`、`30014`、`35078`、`38001`、
  `10036`、`30001`。
- 另有一条 `CODE2=30014`/`CODE2=30001` 的组合分支；具体触发条件尚未完全还原。
- `CODE=40038`、`CODE=10023` 会设置 toner alert 标志。
- `CODE=10006` 或 `CODE=40038` 与启动标志组合时，会启动 60 秒的 toner 刷新定时器。

复刻程序只把上述集合用于 `normal/warning` 分类，不对未确认的状态码赋予业务含义。

## 5. SNMP（只读路径已实现）

### 5.1 版本与传输行为（2026-10-18 复核）

- 设备开放 `161/udp`，社区名 `public` 可读。
- SNMPv2c `GET` 正常：`1.3.6.1.2.1.1.1.0` 返回
  `KYOCERA Document Solutions Printing System`，`sysObjectID` 为
  `1.3.6.1.4.1.1347.41`。
- 设备在 `1.3.6.1.4.1.1347.40.26.1.1.2.1` 声明支持 `1,2c`。
- 2026-10-18 复核：SNMPv1 `GETNEXT` 与 SNMPv2c `GETNEXT` 均可完成表
  walk；`1.3.6.1.2.1.1` 和 `1.3.6.1.2.1.43.5.1.1` 两个起点都返回了正常
  的下一实例。此前“v2c GETNEXT 超时”的结论无法复现，不再作为设备限制。
- SNMPv2c `GETBULK` 仍然没有任何响应；对 v1 发送 `GETBULK`（该版本未定义此
  PDU）同样超时。因此实现默认使用 SNMPv1，但配置和代码路径不应再把 v2c
  `GETNEXT` 视为不可用。
- SNMPv1 对一个未实现 OID 的 `GET` 会以 `error-status=noSuchName` 拒绝整个
  请求；`kyocera_monitor` 的客户端会剔除该 OID 后重试，保留其余字段。
- 旧实现逐 OID walk 整棵子树并并行发送 5 路请求，单次采集实测 12.8 秒。
  2026-10-18 的三轮优化结果：

  | 方案 | 请求数 | 实测耗时 | 结论 |
  | --- | --- | --- | --- |
  | 整棵子树 walk，5 路并行（旧） | 未统计 | 12.8 s | 逐单元格请求，开销最大 |
  | 所需列合并进 GETNEXT，5 路并行 | 10 | 6.7 s | 耗材表跨表终止探测触发 3 s 超时 |
  | 单列枚举行实例 + 逐行多 OID GET，顺序执行 | 14 | 2.6–3.6 s；偶发丢包 5–9 s | 当前默认 |

  耗材表最后一列（`43.11` 的 column 9）的 `GETNEXT` 会跳到 `43.12`，设备对该
  跨表回答常超过 3 秒；因此行实例由 column 8 枚举，再用 `GET` 取整行所需列。
  5 路并发会让设备丢包（行式版本并发实测 12.7 秒），所以表读取改为顺序执行。
- 设备仍会偶发丢弃单次 UDP 请求。默认 `--snmp-timeout 1.5`、`--snmp-retries 2`；
  一次丢包约增加 1.5 秒。观测到的正常响应均不超过约 1.1 秒，因此 1.5 秒足够，
  但慢网络可通过参数调大。

### 5.2 已验证 OID 与字段

| 字段 | OID | 2026-10-18 实测值 | 证据等级 |
| --- | --- | --- | --- |
| `sysDescr` | `1.3.6.1.2.1.1.1.0` | `KYOCERA Document Solutions Printing System` | 已验证 |
| `sysUpTime` | `1.3.6.1.2.1.1.3.0` | `2207587` ticks（约 6.13 小时） | 已验证 |
| `hrDeviceStatus` | `1.3.6.1.2.1.25.3.2.1.5.1` | `2`（running） | 已验证 |
| `hrPrinterStatus` | `1.3.6.1.2.1.25.3.5.1.1.1` | `3`（idle） | 已验证 |
| 型号 | `1.3.6.1.4.1.1347.43.5.1.1.1.1` | `MA2000w` | 已验证 |
| Base model | `1.3.6.1.4.1.1347.43.5.1.1.36.1` | `MA2000w` | 已验证 |
| 序列号 | `1.3.6.1.4.1.1347.43.5.1.1.28.1` | `H4933*****`（脱敏） | 已验证 |
| 系统固件 | `1.3.6.1.4.1.1347.43.5.4.1.5.1.1` | `2YW_2000.001.101` | 已验证 |
| IPv4 | `1.3.6.1.4.1.1347.40.10.1.1.4.1` | `192.168.0.220` | 已验证 |
| 子网掩码 | `1.3.6.1.4.1.1347.40.10.1.1.6.1` | `255.255.255.0` | 已验证 |
| 网关 | `1.3.6.1.4.1.1347.40.10.1.1.7.1` | `192.168.0.1` | 已验证 |
| MAC | `1.3.6.1.2.1.2.2.1.6.1` | `00:17:C8:XX:XX:XX`（脱敏） | 已验证 |
| Scan count | `1.3.6.1.4.1.1347.46.10.1.1.5.3` | `3` | 已验证，与 PJL KGETOBJ 一致 |
| 耗材描述/单位/上限/当前 | `1.3.6.1.2.1.43.11.1.1.6/7/8/9.1.1` | `TK` / `7`（percent）/ `700` / `560` | 已验证 |
| 进纸盒名称/介质 | `1.3.6.1.2.1.43.8.2.1.15/18/12.1.1` | `Cassette 1` / `Cassette 1` / `PLAIN` | 已验证 |
| 进纸盒最大容量/当前 | `1.3.6.1.2.1.43.8.2.1.9/10.1.1` | `150` / `-2`（unknown） | 已验证 |
| 告警严重性 | `1.3.6.1.2.1.43.18.1.1.2.1.1` | `5`（`warningBinaryChangeEvent`） | 已验证 |
| 告警培训级别 | `1.3.6.1.2.1.43.18.1.1.3.1.1` | `3`（`untrained`） | 已验证 |
| 告警组/组索引 | `1.3.6.1.2.1.43.18.1.1.4/5.1.1` | `10`（`marker`）/ `1` | 已验证 |
| 告警位置 | `1.3.6.1.2.1.43.18.1.1.6.1.1` | `0` | 已验证 |
| 告警代码 | `1.3.6.1.2.1.43.18.1.1.7.1.1` | `1001`（`markerFuserUnderTemperature`） | 已验证，标准 IANA 编码 |
| 告警描述/时间 | `1.3.6.1.2.1.43.18.1.1.8/9.1.1` | 空字符串 / `8040` ticks（约 80.4 s） | 已验证 |
| 厂商告警显示/索引 | `1.3.6.1.4.1.1347.43.18.2.1.2/3.1.1` | `Sleeping...\r\n ` / `35078` | 已验证；与 PJL `INFO STATUS` 一致 |
| 面板显示 | `1.3.6.1.2.1.43.16.5.1.2.1.1` | `Sleeping...` | 已验证，与 PJL `DISPLAY` 一致 |
| 设备运行时间类计数 | `1.3.6.1.4.1.1347.43.5.1.1.4.1` | `24958` → `24979`（20 秒后） | 已验证随 `sysUpTime` 同步增长；不是页计数 |
| Sleep mode | `1.3.6.1.4.1.1347.43.5.1.1.33.1` | `1`（ON） | 较高可信度；名称来自 NetViewer `snmp-oid.xml` |
| Auto error clear | `1.3.6.1.4.1.1347.43.5.1.1.34.1` | `0`（OFF） | 较高可信度；名称来自同一 OID 表 |
| Auto error clear timeout | `1.3.6.1.4.1.1347.43.5.1.1.35.1` | `6`，程序显示 `30 s` | 较高可信度；原始值乘以 5 |
| Form feed timeout | `1.3.6.1.4.1.1347.43.5.1.1.22.1` | `60`，程序显示 `300 s` | 已验证；与 PJL `INQUIRE TIMEOUT` 的 `300` 一致 |

耗材百分比由 `level / max_capacity * 100` 计算：`560 / 700 = 80%`，与 PJL
`BLACK TONER LEVEL=80%` 一致。

#### 5.2.1 告警 `1001` 的语义（2026-10-18 确认）

告警表的第 `1.1` 行（`hrDeviceIndex=1`、`prtAlertIndex=1`）当前为：

```text
prtAlertSeverityLevel  = 5   warningBinaryChangeEvent
prtAlertTrainingLevel  = 3   untrained
prtAlertGroup          = 10  marker
prtAlertGroupIndex     = 1
prtAlertLocation       = 0
prtAlertCode           = 1001 markerFuserUnderTemperature
prtAlertDescription    = ""（空）
prtAlertTime           = 8040 ticks（约 80.4 秒）
```

`1001` 不是厂商私有“睡眠”代码，而是 IANA Printer MIB
`PrtAlertCodeTC` 的标准值 `markerFuserUnderTemperature`；`prtAlertGroup=10`
也正好对应 `marker`。设备此时处于睡眠，厂商告警显示表同一行返回
`kcprtAlertStateDisplay="Sleeping...\r\n "` 和
`kcprtAlertStateDisplayIndex="35078"`，与 PJL `INFO STATUS` 的
`CODE=35078`、`DISPLAY="Sleeping..."` 一致。

因此可以把当前状态解释为：设备睡眠时定影器温度低于工作温度，设备以
`warningBinaryChangeEvent` 级别报告 `markerFuserUnderTemperature`，面板显示
“Sleeping...”。这不表示卡纸、缺粉或其他故障；但也不能把 `1001` 直接等同于
“睡眠模式”，它描述的是定影器温度条件。若设备已唤醒而该告警仍长期存在，
需要结合 `prtAlertTime`、面板显示和打印测试另行判断。

实现边界：`prtAlertSeverityLevel` 是列 `.2`，`prtAlertTrainingLevel` 是列
`.3`。此前实现把 `.3` 当作 severity 并显示为 `3`，既取错了列，也把
`untrained` 误当成了严重级别；现已修正为 `.2`，并同时输出培训级别和组名。

### 5.3 与 PJL 的交叉验证

2026-10-18 同一时段分别通过 PJL 9100 与 SNMPv1 采集，以下字段一致：

- 型号 `MA2000w`、固件 `2YW_2000.001.101`、序列号（脱敏后相同）；
- 碳粉 80%；
- 面板显示 `Sleeping...`；
- 网络地址、网关、掩码、MAC；
- Scan count `3`；
- Page count `129`（SNMP `prtMarkerLifeCount` 与 PJL
  `KGETOBJ 2.10.2.1.4.1.1` 一致）。

SNMP 路径没有 PJL `CODE`，不能把 `hrDeviceStatus`/`hrPrinterStatus` 或告警代码
直接映射为 PJL 状态码。

### 5.4 未确认与不要误用

#### 5.4.1 页计数 OID 修正（2026-10-18，已否定旧结论）

此前本文记录 `prtMarkerLifeCount` 在本机不可用，实际是查询 OID 少写了
实例的最后一级：查询 `1.3.6.1.2.1.43.10.2.1.4.1` 返回
`NoSuchInstance`，而设备把该行暴露为
`1.3.6.1.2.1.43.10.2.1.4.1.1`。对
`1.3.6.1.2.1.43.10.2.1` 做完整 walk 返回 14 个对象，其中：

```text
1.3.6.1.2.1.43.10.2.1.4.1.1 = Counter32: 129   # prtMarkerLifeCount
1.3.6.1.2.1.43.10.2.1.5.1.1 = Counter32: 0     # power-on count
```

因此 `kyocera_monitor --snmp` 的 `page_count` 现在返回 `129`，与 PJL
`@PJL KGETOBJ OBJ="2.10.2.1.4.1.1"` 的 `129` 一致。旧结论“SNMP 没有页
计数”已被否定；这是 OID 实例层级错误，不是设备功能缺失。

NetViewer 的 `DEV_PAGECOUNT`（属性 5036）仍然映射到 SOAP
`counter_information` 服务，这与设备同时通过标准 Printer MIB 暴露
`prtMarkerLifeCount` 并不矛盾：两者是同一设备的两个可用数据源，NetViewer
选择了 SOAP 属性路径。见
`netviewer-log-findings.md` 第 3 节的静态映射证据。

PJL `2.10.2.1.4.1.1 = 129` 也因此从“较高可信度”提升为已验证：原厂资源
DLL 的 `Lifetime counter`/`pages` 标签、PJL 值和 SNMP
`prtMarkerLifeCount` 三者相互吻合。实现把它放入
`kgetobj_known.lifetime_counter`，单位 `pages`，`confidence` 为
`verified`。

#### 5.4.2 其他边界

- `1.3.6.1.4.1.1347.43.5.1.1.4.1` 在 20 秒间隔采样中从 `24958` 增至
  `24979`，与 `sysUpTime`（`2495450` → `2497513` ticks）同步增长；它是
  设备运行时间类计数，不能当作页计数或累计打印量。
- SNMP 输入表在本机只返回一行 `Cassette 1`（最大容量 `150`），而 PJL
  `INFO CONFIG` 报告 `Single Bypass` 与容量 `250` 的 `Main Tray`。两套数据
  的口径不同，SNMP 纸盒容量暂不作为权威值。
- 告警代码 `1001` 已确认是标准 `markerFuserUnderTemperature`，见 5.2.1；
  `prtAlertDescription` 本身为空，不能依赖该字段做本地化显示。
- WSD 元数据会未认证地暴露型号、固件、序列号和主机名；公开文档必须脱敏。

历史 NetViewer 日志中的发现/轮询 OID 见
`docs/reverse-engineering/netviewer-log-findings.md`。当前实现位于
`kyocera_monitor/snmp.py` 与 `kyocera_monitor/snmp_status.py`，CLI 使用
`--snmp` 启用。

### 5.5 设备发现实测（2026-10-18）

NetViewer 的发现流程是 SNMP 广播 + `GETNEXT 1.3.6.1.2.1.25.3.2.1.4`
（`hrDeviceDescr`），再用型号/序列号 OID 确认设备。Linux 复刻改为直接 GET
型号 OID；该 OID 是 Kyocera 专有地址，能回答即可确认是京瓷设备。

实测结果：

- 对 `192.168.0.255:161` 和 `255.255.255.255:161` 各发送一次
  `GET 1.3.6.1.4.1.1347.43.5.1.1.1.1`，两者都收到
  `192.168.0.220` 的响应，值为 `MA2000w`。
- 广播只取型号，随后对响应者做一次单播 GET，补全序列号和固件；再与
  ARP/显式子网候选合并。
- WS-Discovery 组播 `239.255.255.250:3702` 的响应不稳定：单次
  `wsdp:Device` Probe 曾得到 0 个响应；同时发送 `wsdp:Device` 与
  `print:PrintDeviceType` 后收到 ProbeMatch，包含
  `Types=devprof:Device print:PrintDeviceType`、`XAddrs=http://192.168.0.220:5357/DeviceService/`
  和 `uuid:...` 端点。因此 WSD 只作为补充信息源，不能作为唯一发现方式。
- 测试主机的 `/proc/net/arp` 为空，发现实现不依赖 ARP 表；ARP 仅作为可选
  候选。显式 `--discover-subnet` 会扫描 IPv4 主机（最大 /22），默认不扫描。

耗时：`--discover --json` 实测 3.3–4.1 秒（2.5 秒收集窗口 + 单播补全）；
Web `/api/discover` 实测 3.55 秒。发现结果同时包含
`snmp-broadcast`、`snmp-unicast` 和可用的 `wsd` 来源。

边界：广播可能被路由器/主机防火墙过滤；WSD 响应可能丢失；WSD 端点与
Types/Scopes 是设备自报数据，不能当作已认证事实。

## 6. KGETOBJ 对象含义

`KMSTMNW.exe` 的 `FUN_004258c0`（日志标记 `PickUpDeviceSetting`）对
KGETOBJ 返回值做分支处理。结合该函数的比较字符串、日志标签和资源中的设置
标签，可以整理出以下对应关系：

| 对象 | 含义 | 证据 | 状态 |
| --- | --- | --- | --- |
| `1.43.5.1.1.29.1` | 厂商 OID 表名为 `kcprtAssetNumber`；设备返回空字符串 | NetViewer `snmp-oid.xml` + 设备实测；旧“Operation Panel Language”标签证据不足 | 名称较高可信度，语义未确认 |
| `1.43.5.1.1.33.1` | Sleep mode（`kcprtsleepMode`） | 代码显式映射 ON/OFF；NetViewer `snmp-oid.xml` 同名 OID；设备实测 `1`（ON）且处于睡眠 | 较高可信度 |
| `1.43.5.1.1.34.1` | Auto error clear（`kcprtAutoErrorClearSwitch`） | 代码显式映射 ON/OFF；NetViewer OID 名称匹配；设备实测 `0` | 较高可信度 |
| `1.43.5.1.1.35.1` | Auto error clear timeout（`kcprtAutoErrorClearTimeout`） | OID 名称匹配；代码乘 5；设备实测 `6`→`30 s` | 较高可信度 |
| `1.43.5.1.1.22.1` | Form feed timeout（`kcprtFormFeedTimeout`） | OID 名称匹配；代码乘 5；SNMP `60`→`300 s` 且与 PJL `INQUIRE TIMEOUT=300` 一致 | 已验证（换算与语义） |
| `2.10.2.1.4.1.1` | 累计打印页数（lifetime counter） | 资源含 `Lifetime counter`/`pages`；PJL `129`；SNMP `prtMarkerLifeCount = 129` | 已验证 |
| `1.43.10.1.1.8.1.1` | Drum counter | 日志字符串 `Drum counter`；设备实测 `129` | 已验证 |
| `1.43.10.1.1.14.1.1` | Drum counter max | 日志字符串 `Drum counter max`；设备实测 `10000` | 已验证 |
| `1.46.10.1.1.5.3` | Scan count | 日志字符串 `Scan count`；设备实测 `3` | 已验证 |
| `2.5.1.1.10.1` | Console localization（`prtConsoleLocalization`）；MA2000w 返回索引 `1`，本地化表 `1.1` 为 `en`/`US` | OID 映射 + 设备 PJL/SNMP 同值 `1` | 已验证 |
| `1.42.5.1.1.16.1` | Panel firmware version（`kmPanelFirmwareVersion`）；MA2000w 返回 `STATUS=2`、`TYPE=0`、空 `VALUE` | NetViewer `snmp-oid.xml` + 设备实测 | 名称较高可信度；该型号不提供值 |

补充说明：

- `KGETOBJ` 对象路径带一个协议前缀，不能一律拼到同一个根：
  - `1.<path>` → `1.3.6.1.4.1.1347.<path>`（Kyocera 企业子树）；
  - `2.<path>` → `1.3.6.1.2.1.43.<path>`（Printer MIB）。
  前者已用五组对象交叉核对数值一致：`43.5.1.1.22.1`（60）、
  `43.5.1.1.33.1`（1）、`43.5.1.1.34.1`（0）、`43.5.1.1.35.1`（6）、
  `43.10.1.1.8.1.1`（129）。后者已用两组验证：
  `2.10.2.1.4.1.1` ↔ `43.10.2.1.4.1.1`（均为 129），
  `2.5.1.1.10.1` ↔ `43.5.1.1.10.1`（均为 1）。
- `2.10.2.1.4.1.1` 不在 Kyocera 企业子树内；它对应标准 Printer MIB 的
  `prtMarkerLifeCount`，SNMP 完整实例为
  `1.3.6.1.2.1.43.10.2.1.4.1.1`，值与 PJL 相同。
- 默认刷新序列只查询 `1.43.5.1.1.34.1` 与 `1.43.5.1.1.35.1`；`33.1` 和
  `22.1` 不在该序列中，`--snmp` 可以读取它们。解析器也支持这四个对象，
  以便未来扩展查询序列或其他型号返回这些字段。
- `1.43.5.1.1.33.1`、`34.1`、`35.1` 的 OID 名称来自 NetViewer 的
  `def/dev/snmp-oid.xml`，属于厂商自己的映射，但尚未通过逐项写入/回读验证，
  因此保持“较高可信度”。
- `STATUS=2` 的具体协议含义尚未确认；不能仅凭一次空值断言对象不存在。
  当前样本中 `STATUS=0` 均返回有效值，`STATUS=2` 均返回空 `VALUE`；
  `TYPE=2` 对应整数，`TYPE=4` 对应字符串。这些是观察到的对应关系，
  不是完整的状态码规格。
- `2.5.1.1.10.1` 返回的是本地化**索引**，不是语言字符串。MA2000w 的
  `prtLocalizationTable` 当前只有 `1.1` 一行：`prtLocalizationLanguage=en`、
  `prtLocalizationCountry=US`、`prtLocalizationCharacterSet=106`。其他型号的
  索引表可能不同，不能把 `1` 硬编码为所有设备的 `en-US`。
- `1.43.5.1.1.29.1` 在 NetViewer `snmp-oid.xml` 中的名称是
  `kcprtAssetNumber`（资产编号）；MA2000w 对该对象返回 `STATUS=0`、
  `TYPE=4`、空字符串。旧文档把它标为“Operation Panel Language”缺少直接
  证据，暂按未确认处理，不能据此实现面板语言读取。
- `Form feed timeout` 的 `raw * 5` 与 PJL `INQUIRE TIMEOUT` 一致，可以确认
  单位是秒；`Auto error clear timeout` 的 `raw * 5` 也按秒解释，但尚未做
  界面或写入回读验证。
- 未执行任何 `KSETOBJ` 写入。

## 7. 未确认事项

- `1.43.5.1.1.29.1` 的业务含义：厂商 OID 名称指向资产编号，旧文档的
  “Operation Panel Language”标签缺少直接证据；设备返回空字符串，暂时无法
  用值反推。
- `1.43.5.1.1.33/34/35.1` 的厂商名称已匹配，但仍缺写入回读或原厂界面确认。
- 配置写入（`KSETOBJ`）的字段、权限与回滚行为；未做任何写入测试。
- USB 路径的实际表现：本次测试时 USB 总线未连接打印机。
- 原厂程序在 Windows 上是否总是经打印后台发送上述 PJL，还是网络时改用 SNMP
  获取部分字段；目前只能确认查询文本来自 `KMSTMVM.exe`，且设备接受 TCP 9100。
