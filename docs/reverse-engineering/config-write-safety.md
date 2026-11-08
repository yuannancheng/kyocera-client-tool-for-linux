# 配置写入安全基线

## 当前状态

已实现**两个受控写入实验**：MA2000w 的 item 2 `Auto error clear` 和 item 50
`Quiet mode` 均通过 SNMPv2c 从 `OFF` 写为 `ON`，回读确认后立即恢复
`OFF`。当前工具提供：

- 147 项配置对象的只读 PJL/SNMP 采集；
- 带 SHA-256 完整性校验的本地快照；
- 传输通道和目标绑定；
- 基线/当前值的只读差异检查。
- `Auto error clear` 单字段 dry-run 写入计划、命令预览、回滚预演和确认令牌。
- `Quiet mode` 的 dry-run 计划、命令预览、回滚预演和确认令牌。
- 仅限 SNMPv2c、相同计划与匹配确认令牌的 item 2/item 50
  `OFF -> ON -> OFF` 执行器。
- `--config-audit-safe` 的无害整数字段白名单、逐项目标回读和自动恢复。
- Web/GUI 配置工作台：按官方主要页面划分的七个配置分区、敏感值脱敏、
  面板/Wi‑Fi 状态、`0600` 私有基线和完整配置差异比较。
- Web/GUI 27 个已审核整数属性的正常设置写入：旧值一致性检查、明确确认、
  SET 后回读以及失败恢复。

其他字段、设备属性的通用 PJL `KSETOBJ` 写入、SNMPv1 SET、密码/网络字段和
设备重置仍不可写。Wi‑Fi 专用连接流程是单独的官方复刻路径，不属于通用属性
写入。

### Web/GUI 配置入口

Network 模式的 Web/GUI 使用 SNMPv2c 配置工作台。页面只显示脱敏后的对象值；
SNMP community、Wi‑Fi SSID、系统联系人和位置不会返回给浏览器。基线保存在
`$XDG_CONFIG_HOME/kyocera-monitor/baselines/<目标哈希>.json`，文件权限为
`0600`。

配置对象分为 `general`、`paper`、`communication`、`snmp_traps`、`panel`、
`fax`、`wifi` 七个互斥分区，覆盖 item 1–147 各一次。
`GET /api/config/categories` 只返回分区元数据；`GET /api/config?category=`
仅请求当前分区。TCP 主机通过 `collect_config_snmp(item_ids=...)` 读取；
`libusb:` 或 `/dev/` USB 设备通过 `open_channel(device=...)` 和
`collect_config(item_ids=...)` 使用 PJL，不能把 USB selector 送进 SNMP
名称解析。Web/GUI 为同一 USB selector 的状态、配置和 Wi-Fi 通道共享锁，
防止异步状态刷新与配置读取同时 claim Printer interface。PJL 与 SNMP 记录
都包含相对 OID 和绝对 OID，视图不依赖 transport 专有字段。该项限制避免只在
页面层隐藏但仍拉取整表。只有用户明确保存或比较完整基线时，工作台才读取全部
147 项。

页面可编辑以下 27 个整数属性：

- item 1 `Sleep time`；
- item 2 `Auto error clear`；
- item 3 `Auto error clear timeout`；
- item 10 `Ignore paper size mismatch`；
- item 11/12/14/15/17/18/19/20/24–32 的 17 个介质重量行；
- item 49 `Print density`；
- item 50 `Quiet mode`；
- item 51 `Units`；
- item 52 `Form feed timeout`；
- item 84 `Auto clear panel`；
- item 85 `Auto clear panel time`。

这些字段均来自已还原的官方控件/差异表；item 2 和 item 50 已做独立真机写入
与恢复，其余 25 个字段属于已执行的 MA2000w 无害整数批量审计。介质重量行只
开放审计中成功写入并恢复的设备值 `11/12/13`，不把设备索引猜译成纸重名称。
`POST /api/config/apply` 只接受上述 item、整数目标值、页面实际读取的
`expected_value` 和 `confirm=true`。设备当前值变化时在写入前拒绝；SET 前的
旧值检查与 SET 后的回读都只请求目标 item，回读不一致或写入异常时尝试恢复
旧值并报告恢复结果。页面不提供全表批量提交或自动重启。

Wi‑Fi 状态、SSID、安全模式、信号和信道在设备配置的 `wifi` 分区显示；附近
AP 扫描和连接控件也在同一分区内，但连接写入继续使用
`WifiWorkbench.connect()` 的专用顺序，不经过通用整数属性接口。设备页不再在
扫描区下方重复显示英文 `Auto error clear`/`Form feed timeout` 摘要。

USB 设备当前只开放分区读取。PJL 写入尚未完成与网络路径同等的失败恢复和
真机审计，因此 `writer_available` 对 USB 目标返回 `false`，页面不会展示
可提交按钮。

CLI 的 `--config-plan` / `--config-apply` 仍是独立的强约束
`OFF -> ON -> OFF` 研究流程，要求相同基线、目标、赋值和匹配令牌；正式页面
不调用这两个实验方法。网络可达性、SNMP community/trap、Wi-Fi、传真、
字符串、重置触发、计数器和未知语义字段继续排除。

设备 Push Scan 的接口、IPv4/IPv6/主机名目标和地址类型对象只有官方读取调用
证据；未找到 Client Tool 的可复现 SET 路径，因此不纳入设备属性写入。界面中的
Push Scan 槽位仅是 `89xxx` 设备触发号到 Linux 本地预设的产品层映射。

## item 2 Auto error clear

当前执行器只允许 item 2 `Auto error clear` 和 item 50 `Quiet mode`：

| 属性 | 值 |
| --- | --- |
| 相对 OID | `43.5.1.1.34.1` |
| 绝对 OID | `1.3.6.1.4.1.1347.43.5.1.1.34.1` |
| PJL 对象 | `1.43.5.1.1.34.1` |
| 类型 | Integer |
| 枚举 | `0=OFF`、`1=ON` |
| UI 证据 | 主对话框控件 `0x03ea` → 模型偏移 `0x0004` |

选择它的原因是状态空间小、不改变 IP/Wi-Fi/SNMP 认证等网络可达性，且当前值
可直接作为回滚值。2026-11-01 已完成一次成功写入、回读和恢复。

## item 50 的设备验证与候选报告

`--config-candidates` 只审查 item 50 `Quiet mode`：

| 属性 | 值 |
| --- | --- |
| 相对 OID | `1001.2.1.1.1.14.1` |
| 绝对 OID | `1.3.6.1.4.1.1347.1001.2.1.1.1.14.1` |
| PJL 对象 | `1.1001.2.1.1.1.14.1` |
| 类型 | Integer |
| 当前已知枚举 | `0=OFF`、`1=ON` |
| UI 证据 | 主对话框 `0x006b` 的控件 `0x0455` → 模型偏移 `0x0018` → item 50 |
| 映射证据 | `device_verified` |

2026-11-01 对 MA2000w `192.168.0.220` 连续执行两次 SNMPv2c 全表只读采集，
两次均为 `96/147` 项可读，item 50 均为 `STATUS=0`、值 `0/OFF`。报告会区分：

- `review.current_read_valid`：对象可读、目录类型匹配、值为整数且落在已记录
  枚举内；
- `write.allowed`：表示是否已有足够证据和授权执行写入。

同 OID 写入回读和恢复已经由 MA2000w 真机验证。后一项仍固定为 `false`，
因为候选报告本身不能授权后续写入；剩余 blockers 是设备失败恢复行为尚未
实测，以及每次实验仍需要用户明确授权。候选命令本身不生成计划或确认令牌。

### item 50 计划与执行边界

`--config-plan` 可以读取 item 50 的基线与当前完整只读采集，生成当前值、目标值、
回滚值、PJL/SNMP 预览和 SHA-256 令牌：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-plan kyocera-config-baseline.json --config-set 50=ON
```

计划前置条件有效时，item 50 的 `execution.allowed=true`，授权范围为
`quiet-mode-off-to-on-then-off-v1`。执行还要求相同基线、目标、赋值和 SHA-256
令牌，并只允许 `0/OFF -> 1/ON -> 0/OFF`。计划器拒绝 no-op、配置漂移、
读取状态变化和目标/传输不匹配；现有执行器拒绝 item 50 的反向转换或其他字段。

### item 50 静态读写数据流

分析对象仍为哈希已校验的 `KMUTLCFG.exe`。保存的 Ghidra 导出和原始 PE
`objdump` 相互核对得到以下路径：

| 阶段 | 证据 |
| --- | --- |
| 模型 → 控件 | `FUN_00405c10` 在 `0x00405fe5..0x00405ffd` 对控件 `0x455` 发送 `BM_SETCHECK (0x00f1)`，值来自栈上的模型 `+0x18` |
| 控件 → 快照 | `FUN_0040b6f0` 在 `0x0040b869..0x0040b885` 对控件 `0x455` 发送 `BM_GETCHECK (0x00f0)`，把结果归一化后写入快照 `+0x18` |
| 差异 → OID | `FUN_00410740` 的 case `0x31` 在 `0x00411b79..0x00411bc7` 比较模型 `+0x18`，变化时写入 OID `1001.2.1.1.1.14.1`，值由 `setne` 归一化为 `0/1` |
| 值类型 | 类型字节为 `0x69`，即 Net-SNMP/PJL 路径使用的字符 `i` |
| 网络写入 | `FUN_00401b20` 在 `0x00401b57` 调用差异生成器，随后把变化记录交给 Net-SNMP SET |
| USB 写入 | `FUN_00402ec0` 使用相对 OID 前缀 `1.` 和 `@PJL KSETOBJ OBJ="%s%s" VALUE =%s\r\n` |
| 重启请求 | item 50 的差异分支不写 `[application+0x57ec]`；原厂程序不会因该字段单独设置其控制器重置请求标志 |
| SNMP 失败处理 | `FUN_00401b20` 对 error-status 非零记录失败原因和失败对象，对无响应标记 timeout；`FUN_00402ec0` 等待 USB 响应最长 50 秒并把 `STATUS!=0` 计为失败 |

结论边界：静态路径证明官方程序的控件值、OID、整数 `0/1` 编码以及网络/USB
消费者一致。MA2000w 后续实测确认该 OID 接受 SET、同 OID 回读为预期值并成功
恢复；`config.py` 因而将该字段标为 `confidence=verified`。官方错误分支仍只
说明客户端如何报告失败；真实设备拒绝、超时或恢复失败仍未实测。

真机验证命令（仅发送配置 GET）：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-candidates
```

两次运行中的第二次约 20 秒完成全表读取，只输出候选摘要，未发送
`KSETOBJ`、SNMP SET 或设备复位。`--json` 同样只输出
`candidate_report`，不附带完整配置对象表。

### item 50 真机写入证据

日期：2026-11-01。环境：MA2000w，SNMPv2c，主机 `192.168.0.220`。

基线文件为本地 `/tmp` 中的 `0600` 快照，SHA-256 为
`73f601ec4706ee5ab49aad275cb223875b8d108cd1a1b5c94f319b8c76b5153c`。
基线及计划前的当前读取均为 `96/147`，item 50 均为 `0/OFF`。确认令牌
为 `sha256:362f7173a67c9bc168784cc958a3410fcadbedc0c9d12af3f35c20cbd9870e3e`。

运行范围：

```text
1.3.6.1.4.1.1347.1001.2.1.1.1.14.1 = 1
SET response: success, echoed Integer 1
readback: 1
1.3.6.1.4.1.1347.1001.2.1.1.1.14.1 = 0
SET response: success, echoed Integer 0
readback: 0
```

结果：

- SET ON、回读 ON、SET OFF、回读 OFF 全部成功，执行状态为 `success`；
- 随后完整 147 项只读比较为 0 个配置变化、1 个易变观测变化、
  0 个读取状态变化、146 项不变；
- 唯一变化是 Wi-Fi RSSI `-69 dBm -> -68 dBm`，属于已区分的只读遥测；
- 写入和回滚后设备仍可正常响应 SNMP，未观察到断网或需要控制器重置；
- 该结果确认 MA2000w 上 item 50 的整数 `0/1` 写入、同 OID 回读和恢复路径。

尚未实测设备拒绝 SET、写后超时、USB `KSETOBJ` 失败或回滚失败时的行为。

### 无害整数字段批量审计

日期：2026-11-01。环境与 item 50 实验相同。2026-11-01 使用同一私密基线执行：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-audit-safe kyocera-config-baseline.json
```

白名单固定为 25 个当前可读、可恢复的整数字段：

- item 1 `Sleep time`；
- item 3 `Auto error clear timeout`；
- item 10 `Ignore paper size mismatch`；
- item 11/12/14/15/17/18/19/20/24-32 媒体重量/类型行；
- item 49 `Print density`；
- item 51 `Units`；
- item 52 `Form feed timeout`；
- item 84 `Auto clear panel`；
- item 85 `Auto clear panel time`。

执行器从同一完整性基线建立计划，逐项执行 `SET target -> verify target ->
SET original -> verify original`。设备结果为 25/25 成功，目标值和恢复值均
回读正确；逐项证据见
[`clienttool-safe-write-audit-20261101.tsv`](data/clienttool-safe-write-audit-20261101.tsv)。
随后完整 147 项比较为 0 个配置变化、0 个易变观测变化、0 个读取状态变化，
147 项全部不变。

明确排除：网络可达性、IPv4/DHCP/协议开关、SNMP community/trap、Wi-Fi 设置、
传真身份/通知、重置触发、计数器、字符串字段、未知语义和当前不可读对象。
该白名单覆盖当前可安全恢复的代表性大部分整数字段，不代表其他对象可写。

## Dry-run 计划

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-plan kyocera-config-baseline.json --config-set 2=OFF
```

计划器会读取当前 147 项并执行：

- 快照完整性、目标、传输和 item/OID 校验；
- 全表持久配置漂移检查；
- 所有对象的读取状态变化检查；
- Wi-Fi RSSI 等易变遥测单独记录，不阻断计划；
- 请求值必须是候选字段的已知枚举；
- 当前值已经等于请求值时标记为 blocked/no-op。

输出包含 `pjl_line`、`pjl_rollback_line`、SNMP Integer 参数、同 OID 回读目标
和确定性 SHA-256 确认令牌。无 blockers 时 `execution.allowed` 为 `true`，
但真正写入还要求显式 `--config-apply`、相同基线和匹配令牌。

## 首次真机写入证据

日期：2026-11-01。环境：MA2000w，SNMPv2c，单播主机 `192.168.0.220`。

运行范围：

```text
1.3.6.1.4.1.1347.43.5.1.1.34.1 = 1
SET response: success, echoed Integer 1
readback: 1
1.3.6.1.4.1.1347.43.5.1.1.34.1 = 0
SET response: success, echoed Integer 0
readback: 0
```

结果：

- 写入前为 `0/OFF`，第一次 SET 成功并回读 `1/ON`；
- 回滚 SET 成功并回读 `0/OFF`；
- 随后完整 147 项只读比较为 0 个配置变化、0 个易变观测变化、
  0 个读取状态变化，147 项一致；
- 该字段的完整操作耗时约 20.9 秒（包含完整配置读取），未观察到重启或断网；
- 该结果确认 `Auto error clear` 的整数编码和成功 SET 响应。

尚未观察真实错误响应、设备拒绝、写入中途断线或重启需求；这些仍由合成测试
覆盖，不能宣称为真机兼容结论。

## 官方证据

分析对象：

| 文件 | SHA-256 |
| --- | --- |
| `Kyocera/ClientTool/KMUTLCFG.exe` | `63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea` |

已确认的静态行为：

1. `FUN_00401b20` 网络写入路径逐个处理配置项，使用 Net-SNMP 的
   `snmpset` 错误文本，并从对象表读取类型字符。
2. `FUN_00402ec0` USB 写入路径只把发生变化的对象加入一个 UEL 帧。
3. USB 命令模板位于 `0x00499ce4`：

   ```text
   @PJL KSETOBJ OBJ="%s%s" VALUE =%s\r\n
   ```

   其中绝对 OID 使用 `#` 前缀（`0x004997d0`），相对 OID 使用 `1.` 前缀
   （`0x004997f0`）。
4. 响应解析模板位于 `0x00499e64`，同样使用 `VALUE =%s` 和
   `STATUS=%d`。
5. 写入后存在设备控制器重置对象 `1.3.6.1.4.1.1347.40.1.1.1.6.1`；
   原厂路径写入值 `2`。重置的实际副作用、适用字段和断电风险尚未验证。

以上是静态代码观察，不是对设备执行写入后的响应记录。`KMUTLPRE.exe` 的
写入实现是另一条代码路径，空格、引号或类型编码不能未经核对直接复用。

## 快照格式

`--config-save PATH` 保存一份完整快照。文件包含：

- 固定的格式名和版本号；
- UTC 创建时间；
- `pjl` 或 `snmp` 传输通道；
- 调用时显式选择的主机或 USB 设备；
- 147 个对象的状态、解码值、原始传输值和已知敏感字段标记；
- Wi-Fi 连接状态、RSSI 和信道的易变观测标记；
- 对规范化 JSON 计算的 SHA-256 校验和。

文件以 `0600` 原子写入，默认拒绝覆盖。快照可能含 SNMP community、Wi-Fi
SSID、系统联系人/位置等站点数据，不得提交到公开仓库。

`--config-compare PATH` 会在以下条件满足后比较语义值：

- 快照校验和有效；
- 文件不是组/其他用户可读；
- 传输通道一致；
- 目标一致，除非显式传入 `--config-allow-target-mismatch`。

比较按对象 `item_id` 和 OID 对齐，不按输出行号或文本格式对齐。只比较
`status`、`value_kind` 和 `value`；展示标签变化不算设备配置变化。

读取状态变化与配置值变化分开报告。Wi-Fi 连接状态（item 142）、RSSI
（item 146）和信道（item 147）属于只读易变遥测，单独报告且不导致配置比较
失败。2026-11-01 的 MA2000w 只读连续采集中曾观察到 RSSI 从 `-69 dBm`
变为 `-71 dBm`，直接证明全表严格字节比较会产生非配置误报。

## 后续单字段写入前置条件

在扩展其他字段前，必须至少满足：

1. 在相同传输和目标上建立基线，并连续两次只读结果一致。
2. 只选择一个已有独立语义证据、类型简单且不会改变网络可达性的字段。
3. 计划中同时记录当前值、目标值、回滚值和原厂写入模板。
4. 写入前要求用户显式确认对象、旧值、新值和重启副作用。
5. 写入后重新读取完全相同 OID，要求状态和值都符合预期。
6. 回读不一致时停止后续字段，并按已确认的回滚值恢复。
7. 设备重置与批量写入分开执行；当前执行器不得自动触发。

## 扩展下一字段前的证据清单

即使 `--config-candidates` 显示当前读取有效，也仍需补齐：

1. 复核官方二进制中控件到模型偏移和 OID 的完整读写路径；
2. 至少连续两次只读采集确认当前值稳定；
3. 为具体旧值→新值构造独立的写入/回读/恢复计划；
4. 由用户明确确认目标、对象、值、预期回滚和可能的设备副作用；
5. 写入实验中至少记录 SET 响应、同 OID 回读、全表恢复和断线/超时行为。

仅凭“看起来是布尔的 UI 控件”不能把字段升级为可写。

## 尚未解决的问题

- `KMUTLCFG.exe` 与其它 Client Tool 组件在 `VALUE` 空格、字符串编码和
  IP 编码上的差异；
- 每个字段的成功响应、失败响应和延迟；
- 哪些字段需要控制器重启；
- 重启期间网络断开、睡眠和恢复时间；
- 写入中断后的原子性与可恢复性；
- Wi-Fi、IP、SNMP community 等字段修改后是否会立即切断当前连接；
- 其他机型的对象可写性和取值范围。

现有真机样本覆盖 `Auto error clear` 和 `Quiet mode` 的成功写入与回滚；
其他对象、失败恢复、USB 写入和其他机型仍有未知项，不得把更广泛的配置写入
标记为兼容或可用。
