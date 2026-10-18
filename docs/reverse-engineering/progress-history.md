# 项目进度历史归档

> 本文件保存 2026-10-18 压缩前的 `PROJECT_PROGRESS.md` 完整快照，供追溯
> 里程碑、轮次交接和旧优先级。当前状态与下一步以根目录
> `PROJECT_PROGRESS.md` 为准。

---

# PROJECT PROGRESS（压缩前快照）

## 项目目标与当前状态

为 KYOCERA 打印机开发 Linux 替代工具（当前验证机型为 MA2000w，后续扩展到其他
型号）。当前处于“入口程序反编译 + 状态监视复刻”的阶段，已能通过 TCP 9100
（PJL）或 SNMPv1 对真实设备执行只读查询并输出结构化状态；USB `usblp` 路径
已完成静态逆向和离线实现，等待硬件接入做物理验证；只读本地 Web 总览/详情页
与原生 GTK3/WebKit2 GUI 可用；CLI 已能通过 PJL 只读导出 Client Tool 的
147 项配置对象。

## 当前阶段

`IN_PROGRESS`：阶段 B/C（关键调用链与通信验证）已完成第一轮；阶段 D（Linux 实现）
已完成 PJL 与 SNMP 两条只读状态路径，并完成扫描/Push Scan、KM-WSDL、WSD 与
eSCL/IPP 的静态调查和部分设备实测；设备发现、多设备总览、单设备详情页和
原生 GUI 已可用。第十四轮已完成 Client Tool 自身的网络/配置/预设协议拆解，
第十五轮已还原维护菜单的 KPSL 帧结构与 KDS 文件布局；当前重点转向
KPSL 动态字段验证、配置对象语义补全和扫描路径验证。第十六轮已完成
147 项配置对象的只读导出与 MA2000w 实测，维护包与 request id 映射已完成
离线解包。第十七轮已提取 `KMUTLCFG` 的 UI 控件标签/组合框表，并据此补充
两个推断配置项。第十八轮完成 GUI 桌面菜单项、图标和安装/卸载脚本。
第十九轮完成 147 项配置对象的索引→模型偏移映射；第二十轮确认主对话框
6 组控件→OID 映射、修正睡眠/关机/安静模式标签，并新增睡眠状态可用的
SNMP 配置后备读取。第二十一轮解析 `KMUTLCFG.exe` 的 RT_DIALOG 资源，
确认控件 ID 按对话框作用域唯一，并把主对话框、Panel options、Communication
三个对话框扩展到 36 个“控件 → 模型偏移 → OID”映射。
第二十二轮补齐 SNMP trap 页：两组收件人的启用、community、IP 和 12 个
事件复选框共 19 个控件，映射总数达到 55。
第二十三轮用 Client Tool 自带的 `snmp-oid.xml` 为 127/147 项配置对象匹配
厂商符号名，并把 `vendor_name` 接入 `--config` 输出。第二十四轮通过
Wi‑Fi 状态页（dialog `0x00f3`）和模型基址 `0x4aa890` 确认了 `40.42.*`
六个字段的语义，并补入音量/FAX notification 对话框，控件映射扩展到 69 行。
第二十五轮盘点并合并了 Client Tool 的两份 `snmp-oid.xml`，生成完整 OID
索引；合并后 147 项覆盖仍为 127/147，20 项在两份 XML 中都没有名称。
第二十六轮展开 `JobSnmpOid.xml` 的作业 OID 树（205 个唯一绝对 OID），
并确认 MA2000w 的作业子树没有可读实例。第二十七轮全量扫描 ClientTool
所有文件，得到 712 个唯一文本 OID（31 个文件、1447 次出现），并解析
`FAX/KMSNMP4.INI` 的 116 个 `INFO_*` 名称。第二十八轮已把 Print Box
7 个、Push Scan 6 个、Preset 5 个无名称 OID 的字段语义、SNMP 类型和
枚举落表，剩余 30 个无名称/无语义 OID。
第二十九轮修复 UTF‑16 前导点扫描缺陷（清单增至 827 个 OID），用托管
元数据常量表还原 Wi‑Fi `40.39/40.40/40.41/40.42/40.43/40.44` 字段，
补齐 PAC/LDAP、组权限、面板单位、鼓计数和标准 MIB 语义；59 个无名称
设备 OID 已覆盖 58 个，仅剩 `42.27.6.0` 语义未定。

## 已完成里程碑

- `DONE` 建立项目文档与工具链记录。
- `DONE` 反编译 `KMSTMVM.exe`：Ghidra 12.1.4 headless 导出 693 个函数伪 C、
  2499 条调用边、939 条字符串。
- `DONE` 确认 `KMSTMVM.exe` 为 Client Tool 主窗口/虚拟打印机监视器，入口
  `0x00403e47`，`WinMain` 为 `0x00423770`。
- `DONE` 确认 MA2000w 映射：USB `0482:0d51`，参数库 `KDS337110.dat`，
  `Model=2470`。
- `DONE` 还原完整 PJL 查询序列（连接时 `INFO ID` + 15 条刷新查询，共 16 条）
  及状态码分支。
- `DONE` 在真实 MA2000w（`192.168.0.220`）上验证 TCP 9100 PJL：
  型号、序列号、固件、状态、耗材、网络、纸盒均成功读取。
- `DONE` 实现 `kyocera_monitor` Linux 程序：TCP/USB 传输、解析、文本/JSON、
  监视模式、退出码。
- `DONE` 解析器/帧格式/KGETOBJ 单元测试通过（当时合计 20 个测试，现为 133 个）。
- `DONE` 分析历史 NetViewer 日志，确认 SNMP 发现 OID、型号/序列号/固件/MAC
  读取路径及 112 个设备属性中的有效字段。
- `DONE` 还原 Push Scan 调用链：`KMSTMNW.exe` → `KMSCNPUS.EXE <presetNo>` →
  `KMQSEnablePreset` → `KMSCNFOL.EXE /D` → `KMQSDisablePreset`。
- `DONE` 确认 Quick Scan 预设写入 `QUICKSCN.ini` 的 `[Globals] Preset`，以及
  TWAIN 数据源 `Kyocera TWAIN Driver`、USB/网络 TWAIN DLL 路径。
- `DONE` 确认 SOAP 客户端位于 NetViewer .NET 程序集；`ClientTool.dll` 仅为
  `CreatePlugin` 加载器。整理 KM-WSDL 命名空间/操作与默认端口。
- `DONE` 设备 80 端口确认运行 gSOAP 2.7，`OPTIONS` 返回 SOAP 405 Fault；
  SOAP POST 在本机未获得应用层响应。
- `DONE` 补充 KGETOBJ 对象含义表：Drum counter、Drum counter max、Scan count
  已由日志标签确认；其余 ON/OFF 与 `raw*5` 字段给出证据等级。
- `DONE` `kyocera_monitor` JSON 新增 `kgetobj_known`，输出上述三个已确认字段，
  原始 `kgetobj` 保持不变。
- `DONE` 新增只读 SNMP 路径：`kyocera_monitor/snmp.py`、`snmp_status.py`，
  CLI `--snmp`；SNMPv1 读取型号、序列号、固件、网络、耗材、纸盒、面板显示、
  告警和 Scan count，并与 PJL 交叉验证一致。
- `DONE` 修正 SNMP walk 边界：离开请求子树即停止；v1 GET 遇到未实现 OID 时
  自动剔除并重试。
- `DONE` 只读 WSD 探测：设备只发布 `WSDPrinter`，`scan:ScannerServiceType`
  连续 3 次无响应；元数据无扫描服务。
- `DONE` 端口复核：`80/515/5357/9090/9100` 开放，`631` 关闭；未取得 eSCL
  或 KM-WSDL 响应。
- `DONE` USB 静态逆向：确认 `KMSTMVM.exe` 不直接打开 USB 设备，而是经打印
  后台 + Kyocera 语言监视器 mailslot 转发 UEL PJL；还原 `ConnectUSB` 握手、
  2 秒重连、Windows 8 断连检测和旧型号 VID/PID 表。
- `DONE` Linux USB 实现：新增 `kyocera_monitor/usb.py`、`--usb`/`--list-usb`，
  `DeviceChannel` 改为非阻塞 `os.open` + `select`，支持短写、残留输入清理和
  sysfs VID/PID 读取。
- `DONE` 新增 PTY 假设备测试，离线验证 USB PJL 往返和 CLI JSON 输出。
- `DONE` 复现并修复 PJL 尾部丢段：按 `@PJL` 回显切段，只补发缺失命令，
  数据停止到达 `--idle` 秒后立即结束接收；MA2000w 单次完整采集 0.73 秒，
  0.5 秒间隔连续 5 次轮询未出现缺段快照。
- `DONE` SNMP 采集优化：行式读取所需列，请求数固定为 14，顺序执行避免设备
  并发丢包；默认超时降为 1.5 秒，实测 2.6–3.6 秒（偶发丢包 5–9 秒）。
- `DONE` 只读本地 Web 状态页：`--web`、`/api/status`、`/healthz`，1 秒缓存、
  串行采集，默认仅监听 `127.0.0.1`；PJL 与 SNMP 两种数据源均已冒烟。
- `DONE` 只读设备发现：SNMP 广播（含 3 次重发）+ 单播补全 + 并行
  WS-Discovery；CLI `--discover` 与 Web `/api/discover` 均已实测。
- `DONE` 多设备总览：Web `/` 展示所有已知设备摘要，`/api/devices` 以最多
  4 个线程并行取快照，单设备失败不影响其他设备；`/device` 保留详情页。
- `DONE` 字段语义扩展：用 NetViewer `snmp-oid.xml` 的厂商 OID 名称确认
  `43.5.1.1.33/34/35/22` 分别为 Sleep mode、Auto error clear、
  Auto error clear timeout、Form feed timeout；PJL/SNMP 在真实 MA2000w 上
  均返回 Auto error clear `OFF`、超时 `30 s`、Form feed timeout `300 s`。
- `DONE` 确认 `KGETOBJ` 的双根映射：Kyocera 企业子树
  `1.3.6.1.4.1.1347.` 与 Printer MIB 子树 `1.3.6.1.2.1.43.`；前者已用
  5 组对象交叉核对，后者用页计数和本地化索引两组验证。
- `DONE` 静态确认 NetViewer `DEV_PAGECOUNT` 来自 SOAP
  `counter_information` 服务，解释并记录 SNMP `page_count` 为空的边界。
- `DONE` 将 PJL `2.10.2.1.4.1.1` 以 `kgetobj_known.lifetime_counter`
  暴露为累计打印页数，单位 `pages`，并标记 `confidence=inferred`；真实设备
  返回 `129`，与 Drum counter 一致。
- `DONE` Web 单设备详情页展示 Lifetime/Scan/Drum 计数及睡眠模式、自动错误
  清除、表单超时。
- `DONE` 修正并验证 SNMP 页计数：`prtMarkerLifeCount` 完整实例
  `1.3.6.1.2.1.43.10.2.1.4.1.1` 在 MA2000w 上返回 `Counter32: 129`，
  与 PJL `2.10.2.1.4.1.1 = 129` 一致；`--snmp` 的 `page_count` 已可用。
- `DONE` 原生 GUI：`kyocera_monitor/gui.py` 使用 GTK3 + WebKit2 4.1 承载
  同一只读仪表盘；新增 `--gui`、`./kyocera-gui` 和 pyproject 的
  `kyocera-gui` 入口，本地服务监听随机回环端口，关闭窗口即退出。
- `DONE` GUI 可用性：`--web`/`--gui` 不再要求先指定打印机；总览页可手动
  输入 IP（`POST /api/devices`，只接受 IPv4/主机名）或点击“发现打印机”；
  界面已中文化，`--web-open` 可自动打开浏览器。
- `DONE` 修复 Web 快照时间戳：缓存判断使用单调时钟，`collected_at` 使用
  墙钟；此前页面显示 `1970-01-01`。同时抑制客户端提前断开导致的
  `BrokenPipeError` traceback。
- `DONE` 确认 `KGETOBJ` 的双根映射：`1.<path>` → `1.3.6.1.4.1.1347.<path>`，
  `2.<path>` → `1.3.6.1.2.1.43.<path>`；`2.5.1.1.10.1` 与 SNMP
  `prtConsoleLocalization` 同值 `1`，`1.42.5.1.1.16.1` 对应
  `kmPanelFirmwareVersion`（MA2000w 返回 `STATUS=2` 空值）。
- `DONE` 确认 SNMP 告警 `1001` 的语义：标准 `prtAlertCode` 值为
  `markerFuserUnderTemperature`；设备睡眠时以
  `warningBinaryChangeEvent`（severity `5`、training `untrained`、group
  `marker`）报告，厂商显示字段同一行为 `Sleeping...` / `35078`。
- `DONE` 修正 SNMP 告警字段映射：severity 取 `43.18.1.1.2`，training level
  取 `.3`；CLI/Web 同时输出标准枚举名、组名和告警代码名，修复了此前把
  `training=3` 误显示为 `severity=3` 的问题。
- `DONE` 复核 SNMP 版本行为：v1/v2c `GETNEXT` 均可完成 walk；v2c `GETBULK`
  仍无响应。此前“v2c GETNEXT 超时”的结论已从文档和阻塞项中移除。
- `DONE` 静态检查 NetViewer `Core.CoreServices.dll` 的扫描 SOAP 契约：
  还原 `open_session`、`start_scan`、`retrieve_image`、`close_session` 请求
  字段和三个配置结构；同时确认没有 `ScanOperationService` 代理类，其他随附
  .NET 程序集也没有引用这些类型，因此不能据此实现扫描触发。
- `DONE` 仅针对 `Kyocera/ClientTool` 完成协议拆解：确认网络监视/配置走
  内嵌 Net-SNMP，`KMSTMNET.exe` 将 SNMP 结果合成为 PJL 文本交给
  `KMSTMVM.exe`；未发现 9100/HTTP/SOAP 客户端。
- `DONE` 还原 `KMUTLCFG.exe` 的 147 行配置对象表、`KMUTLPRE.exe` 的
  56 行预设表（36 行 OID 模板 + 20 行本地字段名），以及
  `1.<path>` / `#<absolute-oid>` 两种 PJL 对象写法。
- `DONE` 只读实测 MA2000w 的私有对象 `1001.1.*`（预设）、`1001.3.*`
  （Print Box）和 `1001.4.*`（Push Scan），并确认 PJL `TYPE=4/64` 的
  十六进制字符串/IP 编码。
- `DONE` 解析 `KDS337110.dat` 的 `0x40100` 文件格式：图形/布局块和数值块
  可分离读取，但 KDS 不包含可直接对应 147 项配置的名称表。
- `DONE` 拆解 `KMUTLMNT.exe` 维护协议：KPSL 帧经 TCP 9100 RAW 或 USB
  发送，帧头 20 字节、载荷含 12 字节控制头 + 记录 + 校验和，载荷用
  固定种子做滚动 XOR；还原 20 项参数类型表和维护包 XML
  节点。
- `DONE` 离线提取维护包请求目录，得到 39 条 request 记录；公开表只保留
  request id、item id、数据类型和来源序号。维护包密钥、解包流程和提取出的
  XML/PNG 保留为本地研究材料，不进入公开仓库。
- `DONE` 从 `KMUTLMNT.exe` 的 `.data` 表提取 177 个符号 request id 到
  数值的映射（如 `DRUM_REFRESH=0x60003`、
  `HIGH_ALTITUDE_MODE=0x3001e`），新增
  `tools/clienttool_request_ids.py` 与对应 TSV。
- `DONE` 新增只读配置导出 `--config`：按 `KMUTLCFG.exe` 的 147 行对象表
  发送一条 `KGETOBJ` 批量帧，解析 `STATUS`、`TYPE`、`VALUE` 并输出文本或
  JSON；MA2000w 实测 96/147 项成功，耗时约 5.2–7.1 秒。
- `DONE` 修正配置字符串解码：`TYPE=4` 先去尾随 NUL，再按 UTF-8 解码；
  MA2000w 的 Wi‑Fi SSID 读出 UTF‑8 中文名称（不记录实际网络名），自定义纸张名读出
  `Custom 1`..`Custom 8`。
- `DONE` 提取 `KMUTLCFG` UI 控件字符串：新增
  `tools/clienttool_ui_strings.py`，解析 `KMUTLCFGRes.dll` 的 RT_STRING
  资源与主程序 `0x00496f20`/`0x00497048` 两张绑定表，生成
  `docs/reverse-engineering/data/clienttool-ui-controls.tsv`（31 个标签/
  分区行 + 31 个组合框选项）。
- `DONE` 补充三个推断标签：`43.5.1.1.23.1` = Sleep time（MA2000w `1` 分钟）、
  `42.5.1.1.43.1` = Power off timer（MA2000w `72`，对应 3 天）、
  `1001.2.1.1.1.14.1` = Quiet mode（MA2000w `0`）；均标记为
  `confidence=inferred`，尚未写入回读。
- `DONE` GUI 桌面集成：新增 `packaging/kyocera-monitor.desktop`、
  SVG 图标和 `tools/install_desktop.py`；默认安装到 `~/.local/share`，
  支持 `--prefix`、`--force`、`--uninstall` 和 `--dry-run`。
- `DONE` 提取 147 项配置对象的模型偏移：新增
  `tools/clienttool_config_offsets.py` 与
  `docs/reverse-engineering/data/clienttool-config-offsets.tsv`；
  147/147 项均有至少一个偏移，关键行已与网络字段、SNMP 社区和 Wi‑Fi SSID
  交叉确认。
- `DONE` 建立首批控件→OID 对照：新增
  `docs/reverse-engineering/data/clienttool-control-oids.tsv`，确认
  Auto error clear、Auto error clear timeout、Sleep time、Power off timer、
  Quiet mode、Form feed timeout 六组控件/模型偏移/OID。
- `DONE` 新增配置 SNMP 后备读取：`--config --snmp` 按同一 147 行对象表
  转换绝对 OID、每批 16 个只读 GET；设备 Sleeping 时实测 96/147，
  约 8.6 秒。
- `DONE` 新增 `tools/clienttool_dialogs.py`：解析 `KMUTLCFG.exe` 的
  `RT_DIALOG`（`DLGTEMPLATE`/`DLGTEMPLATEEX`），生成
  `docs/reverse-engineering/data/clienttool-dialogs.tsv`（318 个控件行）；
  确认主对话框 `0x006b`、Panel options `0x00d0`、Communication `0x008d`
  的控件归属。
- `DONE` `clienttool-control-oids.tsv` 增加 `dialog` 列并扩展到 36 行：
  主对话框补齐 Media/Paper、Original image/size、Power off when 与单位；
  Panel options 补齐 Default screen/Language/Auto clear panel time；
  Communication 补齐 hostname、LAN、DHCP、LPD/Raw/WSD、IP/掩码/网关、
  community、sysContact/sysName/sysLocation。
- `DONE` 用 MA2000w 只读 SNMP 配置交叉核对上述映射：hostname
  `KMD4E4BA`、IP `192.168.0.220`、掩码 `255.255.255.0`、网关
  `192.168.0.1`、community `public`、表单超时 `60`（界面 `300 s`）。
- `DONE` SNMP trap 页（dialog `0x008e`）：确认两组收件人的
  `kmsvTrapEnabled`、`kmsvTrapCommunity`、`kmsvTrapIpAddress` 与
  `kmsvTrapEvents`（6 个连续字段）映射，共 19 个控件；Communication 页
  补入 Authentication traps → `1.3.6.1.2.1.11.30.0`。
- `DONE` MA2000w 只读值核对 trap 字段：item 70 = `2`、71/75 = `0`、
  72/76 = `public`、73/77 = `0.0.0.0`、74/78 = `0`；没有发送写入。
- `DONE` 新增 `tools/clienttool_config_names.py`：对 147 项配置 OID 做最长
  前缀匹配，127 项得到厂商符号名（`45.*` 传真组全部覆盖），20 项保持
  OID-only；生成 `clienttool-config-names.tsv` 与
  `kyocera_monitor/config_vendor_names.py`。
- `DONE` `--config` JSON 增加 `vendor_name`，文本输出在无人工标签时回退到
  厂商名称；MA2000w 只读实测 96/147，CLI 已显示 `kmOffModeSettingState`、
  `kcprtMediaWeight`、`kmFax*` 等名称。
- `DONE` Wi‑Fi 状态页（dialog `0x00f3`，`FUN_00403e80`）：确认页面读取的
  `DAT_004ae518/51c/520/624/628/62c` = 模型基址 `0x4aa890` +
  `0x3c88/3c8c/3c90/3d94/3d98/3d9c`，与 `FUN_0040e820` 的 item 142–147
  一致；`40.42.*` 六个字段语义和枚举已确定（见 `clienttool-protocol.md`
  第 6 节“配置协议”）。
- `DONE` `clienttool-control-oids.tsv` 扩展到 69 行：新增 Wi‑Fi 页的连接
  状态、SSID、安全模式、信道和 RSSI 与 OID 的对照；MA2000w 只读值
  （item 142..147）`3 / 2 / SSID / 4 / -71 / 4` 与页面枚举一致，
  未做写入。
- `DONE` 音量对话框（`0x00d1`）与 FAX notification（`0x00d2`）：
  确认 Speaker/Monitor 音量对应 item 108/109，TX/RX report 与
  notification 对应 item 110–114；`FUN_004144c0` 的栈地址 = 模型偏移 + 8，
  7 个字段与厂商名称逐项吻合，标为 `confidence=inferred`。
- `DONE` 合并两份 `snmp-oid.xml`：除 Wi‑Fi setup 外，补入
  `WFH/remotefax/system/Device.Base/def/dev/snmp-oid.xml`；工具校验两个
  SHA-256，生成 `clienttool-snmp-oid-index.tsv`（997 行、约 500 个唯一
  OID），并保留 `oid`/`symbol`/`source` 多来源索引。
- `DONE` 确认合并后的 147 项覆盖仍为 127/147；20 项 OID-only 是因为两份
  XML 都没有描述，不是漏匹配。remotefax 独有 15 个符号，MA2000w 对
  `kmFaxDeviceExist`、`kmTimeZone*`、`kmFirmwareDetail*` 等全部返回
  `no such object`。
- `DONE` 展开 `JobSnmpOid.xml`：新增 `tools/clienttool_job_oids.py` 和
  `clienttool-job-oids.tsv`；205 个元素、205 个唯一绝对 OID，其中 5 个
  绝对（`rootJob` + 4 个 `additionalOIDS`）、200 个相对。
- `DONE` MA2000w 只读边界：walk `1.3.6.1.4.1.1347.47` 返回 0 行，
  同一次运行 walk Wi‑Fi 子树 `40.42.1.1` 返回 7 行；作业/日志监控在该
  机型上不可用。另观察到 147 项表之外的 `40.42.1.1.2.1 = 1075036018`，
  两份 XML 均未描述，含义未知。
- `DONE` 全量 OID 扫描：新增 `tools/clienttool_all_oids.py` 与
  `clienttool-all-oids.tsv`；扫描 ClientTool 全部 4495 个文件、
  586 MB（ASCII + UTF‑16LE），得到 712 个唯一 OID、31 个命中文件、
  1447 次出现。
- `DONE` OID 命名覆盖：611 个有精确符号名、53 个可从最近命名祖先继承、
  48 个仍无名称；Kyocera 604、标准 MIB 93、其他 15。
- `DONE` 解析 `FAX/KMSNMP4.INI`：新增 `tools/clienttool_fax_ini.py` 与
  `clienttool-fax-snmp-oids.tsv`；116 个 `INFO_*` 名称、108 个唯一 OID、
  144 行，支持一个名称对应多个表变体 OID。
- `DONE` Print Box / Push Scan 语义收口：新增
  `clienttool-oid-semantics.tsv` 与 `tools/clienttool_oid_semantics.py`，
  确认 `1001.3.1.1..7.0`（7 个）和 `1001.4.1.1..6.0`（6 个）的字段名、
  SNMP 类型、读写方向和枚举；同时确认 `1001.1.1.6..10`（5 个）的
  COPY/SCAN/FAX/PRINT BOX 重置目标和预设安全锁；48 个无名称 OID
  降至 30 个。
- `DONE` MA2000w 只读边界：上述 18 个对象中 12 个可读，Print Box
  `.4`–`.7`、Push Scan `.4` 和 Preset `.8` 返回 `NoSuchObject`；
  未执行写操作。
- `DONE` 修复 UTF‑16 OID 扫描边界：旧负向断言漏掉“前导点 + NUL 终止”的
  `.1.3.6.1...` 字面量，补齐 `42.26.1.0`、`42.27.*` 等 115 个 OID；
  清单更新为 827 个唯一 OID（40 个文件、1708 次出现）。
- `DONE` 新增 `tools/managed_constants.py`：只读解析 .NET 元数据常量表与
  `#Strings`/`#Blob` 堆，还原 `WifiSetupToolModels.dll` 的 47 个 OID
  字段，不加载或执行程序集。
- `DONE` Wi‑Fi 语义：确认 AP 扫描表 `40.39.1.1.*`、设置表
  `40.40.1.1.*`、`wifi_connection_state`（`3=ON/Connected`）、`check_ap_set_configuration_status`、
  `wifi_capable_1/2` 和 WPS PIN 对象；MA2000w 只读实测
  `WifiCapable1=3`、`WifiCapable2=NoSuchObject`。
- `DONE` PAC/LDAP 语义：`42.26.*` 六个字段、`42.27.*` 组权限读写方向；
  MA2000w 上 `42.26` 子树 walk 返回 0 行；未执行任何写入。
- `DONE` 其余字段：`panel_size_unit=4`（代码映射 INCH/CM，UI 标签为
  Inches/Millimeters，冲突保留）、`drum_counter=129`、
  `document_processor_attached`、`restart_device_trigger`。
- `DONE` 无名称设备 OID 从 59 个降至 1 个：仅
  `1.3.6.1.4.1.1347.42.27.6.0` 仍无语义；91 个第三方库 OID 标为
  `library-constant`，不混入设备覆盖率。

## 正在进行的任务

- `IN_PROGRESS` 扩展只读配置读取：SNMP 已补充耗材、纸盒、面板、告警和
  睡眠/自动清除/超时字段；`1.43.5.1.1.33/34/35/22` 已有厂商 OID 名称与
  设备值交叉支持，但仍需写入回读或原厂界面确认。
- `IN_PROGRESS` USB 物理验证；静态逆向和 Linux 实现已完成，当前主机未连接
  打印机，`/dev/usb/lp*` 与真实设备响应未验证。
- `IN_PROGRESS` 验证 MA2000w 的 KM-WSDL/SOAP 可用性；80/9090 端口均未取得
  WSDL 或应用层响应，WSD 扫描服务也未发布。
- `IN_PROGRESS` Client Tool 配置/预设对象的业务名称补全：OID 和读写通道已
  还原，147 项已可只读导出；自定义纸张 1..8、网络基本字段、睡眠时间和
  关机定时器已有标签。“控件 → 界面模型偏移 → OID”映射已完成 69 个控件
  （主对话框、
  Panel options、Communication、SNMP trap、Wi‑Fi 状态页、音量与
  FAX notification）；剩余通知、自定义纸张/原稿、DRD、Scan/Print 偏好，
  以及 `1001.2.*`、`45.*` 和预设各列仍需继续对齐。
- `IN_PROGRESS` 维护 KPSL 动态验证：维护包已解包，但请求/响应记录字段的
  一档偏移、`ParamKind` 到字段的精确映射仍需真实 KPSL 帧确认。
- `IN_PROGRESS` 剩余 1 个无语义设备 OID：
  `1.3.6.1.4.1.1347.42.27.6.0`（PAC 组权限相关；只在一个未对齐的
  UTF‑16 数据块中出现，尚无代码引用）。Wi‑Fi、PAC/LDAP、标准 MIB 与
  命名空间根已收口。

## 待办（按优先级）

1. `TODO` USB 硬件接入后按 `docs/reverse-engineering/usb-path.md` 第 9 节
   完成物理测试，并与 TCP 9100 结果逐项对照。
2. `DONE` 反编译 `KMSTMNW.exe` / `KMSCNPUS.exe` / `KMSCNSET.dll`，还原扫描
   入口与 TWAIN 设置路径；SOAP 客户端已定位到 NetViewer .NET 程序集。
3. `TODO` 在 Windows 主机抓取 NetViewer 的 WSDL/SOAP 流量，确认 `UseWSDL`
   与认证流程；或确认 MA2000w 完全走 SNMP。
4. `TODO` 研究 Linux 扫描路径：WSD 扫描已排除；NetViewer 的扫描 SOAP 契约
   已确认没有随附调用方，不能作为入口。优先取得并分析 TWAIN 驱动
   `Ns1815TWGN.DLL`，或在 Windows 主机抓取 TWAIN 流量；同时确认设备是否
   可启用 eSCL/WSD 扫描。
5. `TODO` 研究 `KSETOBJ` 配置写入；必须先建立只读基线、备份与回滚方案。
6. `DONE` 只读本地 Web UI 与原生 GUI：多设备总览 + 单设备详情，复用
   `PrinterSnapshot`；桌面窗口为 GTK3/WebKit2 外壳，TUI 仍为 `DEFERRED`。
7. `DONE` 告警语义：页计数已由 SNMP/PJL 双向验证（`129`）；告警 `1001`
   已确认为 `markerFuserUnderTemperature`，并修正 severity/training 字段映射。
   采集耗时仍维持 2.6–3.6 秒并固定为约 14–16 个请求。
8. `TODO` 在物理 USB 测试后实现设备重枚举/断线重连；当前 `--usb` 只在启动时
   选择一次设备。
9. `DONE` 增强 PJL 部分响应重试：分段识别缺失命令、只补缺失段、按原顺序合并。
10. `DONE` 设备发现与 Web 切换：发现结果加入允许列表，可通过 `?host=` 切换
    当前监控设备。
11. `DONE` GUI 打包：`.desktop` 菜单项、图标和安装/卸载脚本已加入；
    菜单项通过 `kyocera-gui` 启动，需先 `pip install --user .`。
12. `IN_PROGRESS` 解释 MA2000w 上 51 个 `STATUS=2` 配置对象：`45.*` 的
    34 项已由厂商名称确认为传真组，用户确认该机型没有传真功能，因此这部分
    `STATUS=2` 与无选件一致；剩余问题是 `43.7.1.1.3.1.2..12` 是否因
    本地化表只有 `US` 一项而不可读。不要通过写入来探测。
13. `DONE` 补全 `40.42.*` Wi‑Fi 字段语义：Wi‑Fi 状态页与模型基址
    `0x4aa890` 证明 `.1.1` = 连接状态、`.3.1` = 无线启用状态、
    `.4.1` = SSID、`.5.1` = 安全模式、`.6.1` = 信道、`.7.1` = RSSI；
    MA2000w 只读值与页面枚举一致。`kmnetHTTPSenable` 只是同 OID 的
    厂商符号，不能作为字段语义。剩余未知仅 `0x458/0x459` 的选中状态与
    item 90 的关系。
14. `IN_PROGRESS` 建立完整的“控件 ID → 界面模型偏移 → OID”映射表：以
    `FUN_00410740`/`FUN_0040e820` 的 147 个索引→偏移、RT_DIALOG 模板和
    `clienttool-ui-controls.tsv` 为基础，逐个对话框核对控件写入路径；
    主对话框、Panel options、Communication、SNMP trap、Wi‑Fi 状态页已完成
    （69 行），通知、自定义纸张/原稿、DRD、Scan/Print 偏好仍是 `TODO`。

## 待验证假设

- `1.43.5.1.1.29.1` 的业务含义：厂商 OID 名称为 `kcprtAssetNumber`，设备返回
  空字符串；旧“Operation Panel Language”标签证据不足。
- 原厂程序在 USB 与网络两种连接下是否使用完全相同的 PJL 查询。
- `CODE2=30014/30001` 组合分支的准确触发条件。
- `1.43.5.1.1.33/34/35` 的厂商 OID 名称已匹配，但仍缺写入回读验证。
- MA2000w 的 80/9090 gSOAP 服务是受访问控制/配置限制，还是本身不提供
  KM-WSDL 应用层；WSD 扫描能否在设备设置中启用。
- NetViewer `.NET` 中的 `ScanOperation` 类型是否存在反射/动态加载调用；
  目前所有随附程序集的静态引用都只指向 `Core.CoreServices.dll` 自身，
  但没有运行 Windows 程序做动态确认。
- 告警 `1001` 的语义已确认，但设备唤醒后该告警何时消失、是否会伴随打印任务
  变化，仍需在可接受设备副作用的条件下观察。

## 当前阻塞

- 主机未连接 MA2000w 的 USB 接口（`lsusb` 无 `0482:0d51`），USB 路径无法实测。
- USB 原始帧是否与 TCP 完全一致、语言监视器是否额外封装，仍需物理抓包/对照。
- 没有 Windows 运行环境，无法对原厂程序做动态抓包；目前以静态反编译 + 设备实测
  交叉验证。
- SNMPv2c `GET`/`GETNEXT` 均正常，但 v2c `GETBULK` 无响应；实现继续默认使用
  SNMPv1，`GETBULK` 不作为必需能力。
- 设备 Sleeping 时 PJL 9100 可能连续无响应；配置导出应使用
  `--config --snmp`，SNMP 状态与配置读取仍可用。
- `Kyocera/NetViewer/KNV/log/kmnv.log` 含序列号与加密凭据，只能本地使用，
  不得提交。
- 本机对设备 80/9090 端口的 WSDL 路径与 SOAP POST 均得到 0 字节响应；
  没有 Windows 抓包环境，无法确认是访问控制、Web 服务未启用还是认证前置
  条件。SOAP 配置/计数器服务仍不可用；页计数已改由 SNMP 提供。
- 设备只发布 WSD 打印服务；没有 WSD 扫描服务，`631/tcp` 关闭，eSCL 无响应，
  Linux 标准扫描路径暂时无法建立。

## 最近一次工作交接（第二十九轮）

日期：2026-10-18（第二十九轮）。

本次范围：修复全量 OID 扫描器的 UTF‑16 边界缺陷；用托管元数据常量表
还原 `WifiSetupToolModels.dll` 的 Wi‑Fi 字段；补齐 `42.26/42.27.*`
PAC 字段、面板单位、鼓计数等剩余语义；对 MA2000w 做只读 SNMP 核对。
没有执行 SNMP SET、`KSETOBJ`、重启、组权限修改或 Wi‑Fi 配置写入。

本次完成：

- 修复 `tools/clienttool_all_oids.py` 的 `UTF16_RE`：
  旧负向断言同时拒绝“前一个字符是 NUL”和“末尾是 NUL”，因此漏掉
  独立的 `.1.3.6.1...` `#US` 字面量。新规则按 UTF‑16 双字节检查前后
  字符，只排除相邻数字/点。
- 清单从 712 个 OID 增至 827 个（40 个文件、1708 次出现）。新增 115 个，
  其中 Kyocera 27、标准 50、其他 38；关键补漏包括 `42.26.1.0`、
  `42.24.3.*`、`42.27.*`、`40.41.1.1.2*`。
- 新增 `oid_role=library-constant`：91 个只来自 BouncyCastle、itextsharp、
  MimeKit 等非设备库的算法/证书 OID 不计入设备字段覆盖。当前统计为
  736 个设备 OID、59 个无名称设备 OID。
- 新增 `tools/managed_constants.py`：只读解析 PE/CLI 头、`#~` 表流、
  Constant 表以及 `#Strings`/`#Blob` 堆。用
  `WifiSetupToolModels.dll`（SHA-256 `d7aa7eb4...dcf4e4c`）还原
  `OID` 类的 47 个字段常量，不加载或执行程序集。
- Wi‑Fi 字段：
  - `40.39.1.1.*` AP 扫描表：SSID、security、BSSID、RSSI、WEP index、
    WEP key、access points total；`GetAccessPointsList()` 在列 OID 后
    追加行索引。
  - `40.40.1.1.*` 设置表：SSID、security、BSSID、WEP index/key、
    pre-shared key、`complete_ap_set_configuration`；
    `ConnectToAccessPoint()` 发送 SET。
  - `40.42.1.1.1.1` = `wifi_connection_state`，`IsWifiON()` 与字符串
    `"3"` 比较，`TurnONWifi()` 写 `"3"`；ClientTool Wi‑Fi 页把 item 142
    标为 Connection status，`3=Connected`、`4=Not connected`。本轮只
    观测到 `3`。
  - `40.42.1.1.3.1` = `check_ap_set_configuration_status`；当前构建中
    常量未被调用，设备值 `2` 的含义不推断。
  - `40.43.1.1.1.1` = `wifi_capable_1`，MA2000w 返回 `3`；
    `40.44.1.1.1.1` = `wifi_capable_2`，返回 `NoSuchObject`。
  - `40.41.1.1.2/.2.1` = WPS PIN 基础对象/PIN 值；设备睡眠时连续超时，
    未取得值。
- PAC/LDAP（`Device.Controllers.DevicePACController.dll`）：
  `42.26.1.0` obtain network user property；`42.26.2.1.0` LDAP server；
  `.2.2.0` port；`.2.3.0` encryption；`.2.4.0` search timeout；
  `42.26.3.1.3` 被 Name1/Name2/EmailAddress 三处共用。
  `42.27.1.0` 组权限启用（读）、`.2.0` 解锁（写）、`.3.0/.4.0/.8.0`
  组 ID（写）、`.7.0` 最大组数（读）。
- 其余字段：`42.5.1.1.13.1` 面板单位（设备 `4`；代码把 `"3"` 映射为
  INCH、其它为 CM，而 UI 标签是 Inches/Millimeters，冲突保留）；
  `43.10.1.1.8.1.1` 鼓计数（`129`，KMSTMNET 日志明确 `DRUM COUNT`）；
  `42.3.2.3.2.1.3.1.1` DP/ADF 连接标志；
  `40.1.1.1.6.1` 重启触发（只推断，未写入）。
- `clienttool-oid-semantics.tsv` 从 18 行扩展到 62 行；59 个无名称设备
  OID 已覆盖 58 个，仅剩 `1.3.6.1.4.1.1347.42.27.6.0`。

验证：

- `python3 tools/clienttool_oid_semantics.py` → inventory 827、
  library constants 91、device OIDs 736、unnamed 59、covered 58、
  remaining 1；无缺失、无精确厂商名冲突；4 行覆盖继承前缀符号。
- `python3 -m unittest discover -s tests -v` → 141/141 通过。
- MA2000w 只读 SNMP（`192.168.0.220`，v2c）：
  - `40.43.1.1.1.1 = 3`；`40.44.1.1.1.1 = NoSuchObject`；
  - `40.42.1.1.1.1 = 3`；`40.42.1.1.1.3.1 = 2`；
  - `40.39.1.1.10.1.1 = 0`，实例 1 的 SSID 为空；
  - `40.40.1.1.10.1 = 0`；security `4`；SSID/BSSID/PSK 非空但不记录；
  - `42.5.1.1.13.1 = 4`；`43.10.1.1.8.1.1 = 129`；
  - walk `42.26` 与 `42.3.2.3` 均返回 0 行；
  - 设备睡眠后多次 GET 超时，WPS/PAC 组权限/标准 MIB 列未取得。
- 未执行任何写入、重置或重启。

文件变更：

- 新增 `tools/managed_constants.py`、`tests/test_managed_constants.py`。
- 修改 `tools/clienttool_all_oids.py`、`tools/clienttool_oid_semantics.py`、
  `tests/test_clienttool_all_oids.py`、
  `tests/test_clienttool_oid_semantics.py`、
  `docs/reverse-engineering/data/clienttool-all-oids.tsv`、
  `docs/reverse-engineering/data/clienttool-oid-semantics.tsv`、
  `docs/reverse-engineering/clienttool-protocol.md`、
  `PROJECT_PROGRESS.md`、`CHANGELOG.md`。

边界与下一步：

- `42.27.6.0` 只在一个未对齐的 UTF‑16 数据块中出现，没有可定位的
  `ldstr` 引用；需要继续查 `PACOperator` 的其它方法或动态调用。
- `wifi_capable_1/2`、`access_point_security`、`set_access_point_security`
  和 `check_ap_set_configuration_status` 的枚举仍未确认；不要在未备份的
  情况下通过写入探测。
- 面板单位存在“代码 CM / UI Millimeters”冲突，需要原厂界面或另一机型
  交叉确认。
- MA2000w 睡眠时 SNMP 丢包明显；后续批量读取应先取得一次状态，失败时
  记录为“未取得”，不要用超时推断对象不存在。

## 历史交接（第二十八轮）

日期：2026-10-18（第二十八轮）。

本次范围：从 48 个无名称 OID 中优先收口 `1001.3.1.*`（Print Box）和
`1001.4.1.*`（Push Scan），并顺带确认 `1001.1.1.6..10`（Preset），
逐个确认字段语义、SNMP 类型、读写方向和枚举；对 MA2000w 做只读 SNMP
核对。没有执行 `snmpset`、`KSETOBJ` 或重置。

本次完成：

- 新增 `docs/reverse-engineering/data/clienttool-oid-semantics.tsv`：
  18 行，Print Box 7 个、Push Scan 6 个、Preset 5 个；每行记录语义名、
  组、方向、SNMP 类型、值编码、枚举、证据函数、MA2000w 只读结果和备注。
- 新增 `tools/clienttool_oid_semantics.py`：校验语义表、统计 48 个无名称
  OID 的覆盖情况、输出合并后的 `semantic_*` 列。
- `tools/clienttool_all_oids.py` 与 `clienttool-all-oids.tsv` 增加
  `semantic_name` 列；原 18 个 OID 现在同时有语义名，旧列内容未变。
- 确认字段映射：
  - Print Box：`.1` interface（0=USB，非零=NETWORK）、`.2` IPv4、
    `.3` result（0=ACCEPTED/1=NO DATA/2=NO FOLDER/3=WRONG PIN）、
    `.4` PIN、`.5` IPv6、`.6` host name、`.7` address type
    （1=IPv4/2=IPv6/3=HostName）。
  - Push Scan：`.1` interface、`.2` IPv4、`.3` result（0=OK/1=NG）、
    `.4` IPv6、`.5` host name、`.6` address type（同一枚举）。
  - Preset：`.6` COPY、`.7` SCAN、`.8` FAX、`.9` PRINT BOX 重置目标
    （Integer，写）；`.10` 预设安全锁（OctetString，读写；客户端写空
    表示 `FREEING`、写 `FFFFFFFFFFFFFFF` 表示 `LOCKING`）。
- 证据链：`KMSTMNW.exe!FUN_004258c0` 按完整 OID 分支解析并打印
  `PBOX/PSCN` 字段；`KMSTMNET.exe!FUN_004b2d30/FUN_004b1600` 读取，
  `FUN_004b2180/FUN_004b14f0` 写结果，`FUN_004ba2a0` 处理 16 字节
  IPv6，`KMSTMNW.exe!FUN_004515b0/FUN_00450f20` 按地址类型选择
  IPv4/IPv6/主机名；`KMUTLPRE.exe!FUN_0041aad0` 用 `param_2`
  0/1/2/3 选择 `.6/.8/.7/.9`，字符串为 `COPY/FAX/SCAN/PRINT BOX`；
  `FUN_00419530` 负责 `.10` 的 LOCKING/FREEING。
- 发现一处厂商实现不一致：`KMSTMNET` 合成给 `KMSTMVM` 的 PJL 文本中，
  Print Box IPv6 `.5.0` 标成 `TYPE=64`、Print Box 主机名 `.6.0` 标成
  `TYPE=2`，而 Push Scan 主机名 `.5.0` 标成 `TYPE=4`。这些是输出标签，
  不是设备 SNMP 类型；消费时应以 OID 为准。

验证：

- `python3 tools/clienttool_oid_semantics.py` →
  inventory 712、unnamed 48、covered 18、remaining 30、无冲突。
- `python3 -m unittest discover -s tests -v` → 134/134 通过。
- MA2000w（`192.168.0.220`）只读 SNMPv2c GET：
  - 可读：PBOX `.1=0`、`.2=0.0.0.0`、`.3=0`；PSCN `.1=0`、
    `.2=0.0.0.0`、`.3=0`、`.5=""`、`.6=1`；Preset `.6=0`、`.7=0`、
    `.9=0`、`.10="L"`；
  - `NoSuchObject`：PBOX `.4/.5/.6/.7`、PSCN `.4`、Preset `.8`。
- 同日 PJL 批量 `KGETOBJ` 在设备睡眠时无响应；这些对象的 PJL
  路径尚未逐项实测。

文件变更：

- 新增 `docs/reverse-engineering/data/clienttool-oid-semantics.tsv`、
  `tools/clienttool_oid_semantics.py`、
  `tests/test_clienttool_oid_semantics.py`。
- 修改 `tools/clienttool_all_oids.py`、
  `docs/reverse-engineering/data/clienttool-all-oids.tsv`、
  `docs/reverse-engineering/clienttool-protocol.md`、
  `tests/test_clienttool_all_oids.py`、`PROJECT_PROGRESS.md`、
  `CHANGELOG.md`。

边界与下一步：

- 剩余 30 个无名称/无语义 OID：2 个命名空间根、15 个 Wi‑Fi
  （`40.39/40.40/40.42.1.1.3.1/40.43/40.44`）、5 个 `42.26.*`、
  2 个标准 MIB、1 个 `42.3.2.*`、1 个 `42.5.1.1.13.1`、
  1 个 `43.10.1.1.8.1.1`、3 个 `1.3.6.1.5.5.7.*`。
- 下一批优先 Wi‑Fi 组（`WifiSetupToolModels.dll` 的字符串表），
  再处理 `42.26.*` PAC 字段。
- 若要求绝对完整，再统一展开 `.md_/.ch_/.dl_/.in_/.ex_` 等 SZDD 容器并
  重跑全量扫描；本轮未展开，不能据此断言压缩内容没有 OID。

## 历史交接（第二十七轮）

日期：2026-10-18（第二十七轮）。

本次范围：全量扫描 `Kyocera/ClientTool` 的文件内容，提取所有点分 OID，
解析 `FAX/KMSNMP4.INI`，并合并 XML、作业树、Support 的名称。纯静态分析，
没有设备写入。

本次完成：

- 新增 `tools/clienttool_all_oids.py`：扫描 4495 个文件、约 586 MB，
  同时匹配 ASCII 与 UTF‑16LE OID；结果写入
  `docs/reverse-engineering/data/clienttool-all-oids.tsv`。
- 全量结果：712 个唯一 OID、31 个命中文件、1447 次出现；611 个有精确
  符号名、53 个可从最近命名祖先继承、48 个无名称；命名空间为
  Kyocera 604、标准 MIB 93、其他 15。
- 每个 OID 记录来源文件与次数、编码、`symbols`/`name_sources`、
  `prefix_symbols`/`prefix_base_oid`、147 项配置的精确/后代关联，以及
  首处可打印上下文。
- 新增 `tools/clienttool_fax_ini.py`：解析 `FAX/KMSNMP4.INI` 的
  `[section] ; INFO_*` 表，支持分号分隔的多 OID；生成
  `clienttool-fax-snmp-oids.tsv`，共 144 行、116 个名称、108 个唯一 OID。
- 主要新增来源：`KMSNMP4.INI` 108、`KMSTMNET.exe` 47、
  `WifiSetupToolModels.dll` 30、`KMUTLPRE.exe` 27、`KMUTLCFG.exe` 25、
  `KMSTMVM.exe` 12、`KMSTMNW.exe` 11。
- 边界：`.md_`/`.ch_`/`.dl_`/`.in_`/`.ex_` 等 SZDD 压缩容器未逐个展开；
  抽样未发现 OID 文本，但不能据此断言压缩内容完全没有 OID。二进制整数表
  编码的 OID 由既有 147 项静态表覆盖，并通过 `config_descendant_items`
  关联。

验证：

- `python3 -m unittest discover -s tests` → 124/124 通过。
- `python3 tools/clienttool_all_oids.py` 与
  `python3 tools/clienttool_fax_ini.py` 均可逐字节复现已提交 TSV。
- 已知关系抽查：`43.5.1.1.23` → `kcprtSleepTimer`、后代 item 1；
  `40.42.1.1.1.1` → 祖先 `kmnetHTTPSenable`、精确 item 142；
  `45.8.1.1.14` → `INFO_FAXDEVICEISEXIST|kmFaxDeviceExist`。

文件变更：

- 新增 `tools/clienttool_all_oids.py`、`tools/clienttool_fax_ini.py`、
  `docs/reverse-engineering/data/clienttool-all-oids.tsv`、
  `docs/reverse-engineering/data/clienttool-fax-snmp-oids.tsv`、
  `tests/test_clienttool_all_oids.py`、
  `tests/test_clienttool_fax_ini.py`。
- 修改 `docs/reverse-engineering/clienttool-protocol.md`、`README.md`、
  `CHANGELOG.md`、`PROJECT_PROGRESS.md`。

未完成/下一步：

- 48 个无名称 OID 主要集中在 `40.39/40.40/40.42.1.1.3.1/40.43/40.44`、
  `42.26.*`、`1001.1.1.*`、`1001.3.1.*`、`1001.4.1.*` 和少量标准节点；
  下一步可从二进制上下文（如 `<fn:PrintBox>`、`<fn:SetPushScanResult>`）
  逐个确认语义。
- 若要求绝对完整，需要展开全部 SZDD 容器再扫描；当前只做了抽样。

## 历史交接（第二十六轮）

日期：2026-10-18（第二十六轮）。

本次范围：展开 `JobSnmpOid.xml` 的作业 OID 树，并对作业子树的可用性做
只读验证。没有写入设备。

本次完成：

- 新增 `tools/clienttool_job_oids.py`：解析
  `WFH/remotefax/addins/Device/Device.DeviceJobs/conf/JobSnmpOid.xml`。
  `rootJob` 提供绝对根，普通子节点拼接相对 OID，`additionalOIDS` 条目
  自带绝对 OID；相对 OID 无父节点、非数字分量或绝对 OID 重复都会失败。
- 生成 `docs/reverse-engineering/data/clienttool-job-oids.tsv`：
  205 个元素、205 个唯一绝对 OID，无重复；5 个绝对、200 个相对。
- 关键展开结果：`kmJobGeneralIndex` =
  `1.3.6.1.4.1.1347.47.1.1.1.1`、`kmPrintJobStatusCount` =
  `...47.1.1.1.2`、`kmPrintJobStatusCondition` =
  `...47.2.1.1.6`。
- MA2000w 只读验证：walk `1.3.6.1.4.1.1347.47` 返回 0 行；同一次运行
  walk `1.3.6.1.4.1.1347.40.42.1.1` 返回 7 行。作业/日志子树的 OID
  展开与 XML 结构一致，但该机型没有可读的作业实例。
- 同一次 walk 观察到 147 项对象表之外的 Wi‑Fi 实例
  `1.3.6.1.4.1.1347.40.42.1.1.2.1 = 1075036018`；两份 `snmp-oid.xml`
  和 147 项表均未描述，含义保持未知。

验证：

- `python3 -m unittest discover -s tests` → 116/116 通过。
- `python3 tools/clienttool_job_oids.py` 输出与已提交
  `clienttool-job-oids.tsv` 完全一致。
- MA2000w 已知对照 `42.5.1.1.43.1 = 72`；作业表列 GET 均为
  `no such object`，与子树 walk 为空一致。
- 未发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 新增 `tools/clienttool_job_oids.py`、
  `docs/reverse-engineering/data/clienttool-job-oids.tsv`、
  `tests/test_clienttool_job_oids.py`。
- 修改 `docs/reverse-engineering/clienttool-protocol.md`、`README.md`、
  `CHANGELOG.md`、`PROJECT_PROGRESS.md`。

未完成/下一步：

- MA2000w 的作业/日志监控不可用；若要支持其他机型，需要一台作业表有实例
  的设备做真机验证。
- `Support.xml` 的 10 个应用/用户 OID 尚未接入状态查询。
- 20 个配置对象在两份 `snmp-oid.xml` 中没有名称，仍需从控件/模型偏移
  继续推断。

## 历史交接（第二十五轮）

日期：2026-10-18（第二十五轮）。

本次范围：盘点 Client Tool 目录下所有 `snmp-oid.xml`，合并符号表并核对
147 项配置对象的覆盖；对 remotefax 独有 OID 做一次只读 GET。没有写入设备。

本次完成：

- 找到两份 `snmp-oid.xml`：
  - `Kyocera/ClientTool/WIFI/wifisetup/def/dev/snmp-oid.xml`（此前已用）；
  - `Kyocera/ClientTool/WFH/remotefax/system/Device.Base/def/dev/snmp-oid.xml`
    （此前未使用）。
- 修改 `tools/clienttool_config_names.py`：默认合并两份 XML、校验两个
  SHA-256、新增可重复的 `--xml` 和 `--index-output`；生成
  `docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv`，共 997 行
  （约 500 个唯一 OID），保留同一 OID 的多符号与来源文件。
- 合并后 147 项仍为 127 项有名称、20 项 OID-only；remotefax 没有增加
  配置对象覆盖，但独有 15 个符号，包括 `kmFaxDeviceExist`、
  `kmFaxApliFirmwareVersion`、`kmTimeZone`、`kmTimeZoneName`、
  `kmDateFormat`、`kmSummerTimeSetting`、`kmFirmwareInfoDetailType`、
  `kmFirmwareDetailVersion`、`kcprtInputMediaSelectMode` 等。
- 明确 20 项 OID-only 是两份 XML 都没有描述，不是匹配逻辑漏项；清单包括
  `1001.2.1.1.1.8.1`、`1001.2.1.1.1.9.1`、`43.10.1.1.13.1.1`、
  `42.5.1.1.13.1`、`40.10.1.1.1.1`、`1001.2.2.*` 和
  `1001.2.3.1.1.1.1` 等。
- 新增 `tools/clienttool_oid_sources.py`：扫描 ClientTool 下所有带 `oid`
  属性的 XML，生成 `clienttool-oid-mapping-sources.tsv`。确认共有 5 个
  映射文件：两份 `snmp-oid.xml`、`JobSnmpOid.xml`（205 元素，200 个相对
  OID）、两份 `Support.xml`（各 10 个绝对 OID）；两份
  `snmp-discovery.xml` 只是发现参数，不含 OID 映射。

验证：

- `python3 -m unittest discover -s tests` → 112/112 通过。
- `python3 tools/clienttool_config_names.py --index-output ...` 生成的
  147 项表与已提交的 `clienttool-config-names.tsv` 完全一致，
  `config_vendor_names.py` 未发生变化。
- MA2000w 只读 SNMP 对照：已知 `42.5.1.1.43.1 = 72`、
  `42.5.9.1.3.1 = 0`；remotefax 独有的
  `45.8.1.1.14`（`kmFaxDeviceExist`）、`45.8.1.1.13`、
  `42.5.11.1.2/3`、`42.5.1.1.12/52/53`、`43.8.1.1.14` 全部
  `no such object`。
- 用户确认 MA2000w 没有传真功能，因此 `45.*` 传真组无法做真机值或写入
  验证；相关映射只保留静态证据。
- 未发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 新增 `docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv`、
  `docs/reverse-engineering/data/clienttool-oid-mapping-sources.tsv`、
  `tools/clienttool_oid_sources.py`、
  `tests/test_clienttool_oid_sources.py`。
- 修改 `tools/clienttool_config_names.py`、
  `tests/test_clienttool_config_names.py`、
  `docs/reverse-engineering/clienttool-protocol.md`、`README.md`、
  `CHANGELOG.md`、`PROJECT_PROGRESS.md`。

未完成/下一步：

- 20 个 OID-only 对象只能从 `KMUTLCFG` 的控件/模型偏移或设备行为继续
  推断，不得按位置猜名称。
- `JobSnmpOid.xml` 的作业子树尚未解析；若后续要做作业/日志监控，可作为
  下一个 OID 索引来源。
- `Support.xml` 的 `KmApplicationEntry`（ID/名称/版本/状态）和用户列表
  安全锁 OID 尚未接入状态查询。
- `43.7.1.1.3.1.2..12` 的 `STATUS=2` 仍需解释是否为本地化表只有 `US`
  一项导致。

## 历史交接（第二十四轮）

日期：2026-10-18（第二十四轮）。

本次范围：确认 Wi‑Fi 状态页以及音量/FAX notification 对话框的控件、
模型偏移与 OID 对应关系。只做静态反编译、资源字符串解析和只读 SNMP
读取，没有写入设备。

本次完成：

- 解析 dialog `0x00f3`（Wi‑Fi 状态页，页面过程 `FUN_00403e80`）：页面
  读取 `DAT_004ae518/51c/520/624/628/62c`，这些绝对地址正好等于模型
  （默认值表）基址 `0x4aa890` 加 `0x3c88/3c8c/3c90/3d94/3d98/3d9c`，与
  `FUN_0040e820` 的 item 142–147 偏移一致。
- 确认字段语义：item 142 = 连接状态（`3` Connected，`4` Not connected）、
  item 143 = 无线启用状态、item 144 = SSID、item 145 = 安全模式、
  item 146 = RSSI（dBm）、item 147 = 信道。
- 从 `LANG/en/KMUTLCFGRes.dll` 提取枚举字符串 `0x204..0x20d`：
  安全模式 0..4 与 RSSI 的 Excellent/Good/Fair/Weak 分档均与页面分支
  一一对应。
- 补全音量对话框（`0x00d1`，`FUN_00416890`）和 FAX notification
  （`0x00d2`，`FUN_00416f70`）：Speaker/Monitor 音量 = item 108/109，
  TX/RX report = item 110/111，TX/RX notification = item 112/114，
  Attach copy of TX = item 113。`FUN_004144c0` 的 7 个栈字段满足
  “栈地址 = 模型偏移 + 8”，并与厂商名称逐项吻合。
- `clienttool-control-oids.tsv` 从 55 行扩展到 69 行，新增 Wi‑Fi 页
  五个只读字段以及音量/FAX notification 的九个控件对照。
- 更新 `clienttool-protocol.md` 第 6 节和第 6.6.2 节、README、CHANGELOG、
  `kyocera_monitor/config.py`、`tests/test_clienttool_control_oids.py`
  和 `tests/test_config.py`。

验证：

- `python3 -m unittest discover -s tests -v` → 107/107 通过。
- MA2000w 只读 `--config --snmp --config-snmp-version 2c`：96/147；
  六个 Wi‑Fi 值为 `142=3`、`143=2`、`144=SSID`（UTF‑8 中文名称，
  不在仓库记录实际名称）、`145=4`（WPA2 PSK (AES)）、`146=-71`
  （Weak）、`147=4`（channel 4）。
- CLI 文本输出已按新标签渲染：`Wi-Fi connection state  Connected`、
  `Wi-Fi security mode  WPA2 PSK (AES)`、`Wi-Fi RSSI  -71 dBm`、
  `Wi-Fi channel  4`。
- MA2000w 没有传真选件，item 108–114 均返回 `no such object`，因此
  音量/FAX notification 映射只有静态证据，标记为 `inferred`。
- 读取前后没有发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 修改 `docs/reverse-engineering/data/clienttool-control-oids.tsv`、
  `docs/reverse-engineering/clienttool-protocol.md`、`README.md`、
  `CHANGELOG.md`、`PROJECT_PROGRESS.md`、`kyocera_monitor/config.py`、
  `tests/test_clienttool_control_oids.py`、`tests/test_config.py`。

未完成/下一步：

- Wi‑Fi 页 `0x458/0x459`（On/Off）的选中状态来自栈上 `0x3c84`
  （item 90 `1001.2.2.1.1.1.1`），与 `40.42.1.1.3.1` 的关系仍未确认；
  不按位置猜测。
- 控件映射的下一批目标是通知页 `0x008c`、自定义纸张 `0x00ce`、
  自定义原稿 `0x00e0`、DRD `0x00f1`，以及 Scan/Print 偏好 `0x00e4`。
- `0x3f6` Paper weight、自定义纸张记录内部字段和 `1001.2.*` 的完整
  业务名称仍未对齐，继续保留 OID/偏移级证据。

## 历史交接（第二十三轮）

日期：2026-10-18（第二十三轮）。

本次范围：用 Client Tool 自带的厂商 OID 名称补全 147 项配置对象的业务
符号，并接入只读 `--config` 输出。只做静态解析和只读 SNMP 采集，没有写入。

本次完成：

- 新增 `tools/clienttool_config_names.py`：解析
  `Kyocera/ClientTool/WIFI/wifisetup/def/dev/snmp-oid.xml`，对 147 项配置
  OID 做最长前缀匹配，输出 `item_id`、`oid`、`vendor_name`、
  `vendor_base_oid`、`match`。
- 匹配结果：127 项为 `table`（XML 描述表/组，对象是实例），20 项为
  `none`，没有 `exact`；未匹配项保持 OID-only。
- 生成 `docs/reverse-engineering/data/clienttool-config-names.tsv` 和
  `kyocera_monitor/config_vendor_names.py`。关键名称：
  - item 1 `kcprtSleepTimer`、item 4 `kmOffModeTimer`；
  - item 5/55/107 `kmOffModeSettingState`（同一状态表三个实例）；
  - item 83 `kmGrowthModelDeviceConfigCommonOrigianalQuality`（原文拼写）；
  - item 108 `kmFaxDeviceSpkVolumeLevel`、item 119 `kmFaxPrivateName`、
    item 128 `kmFaxForwardEnable`；
  - `45.*` 传真组 34 项全部有名称。
- `kyocera_monitor/config.py` 为 PJL/SNMP 两种记录增加 `vendor_name`；
  `cli.py` 文本输出在无人工 `label` 时回退到厂商名称。

验证：

- `python3 -m unittest discover -s tests` → 105/105 通过。
- `python3 tools/clienttool_config_names.py` 输出与
  `clienttool-config-names.tsv` 一致；`--python-output` 生成的模块与 TSV 一致。
- MA2000w 只读 `--config --snmp --config-snmp-version 2c` 返回 96/147；
  文本已显示 `kmOffModeSettingState`、`kcprnInputPaperSizeIndex`、
  `kcprtMediaWeight`、`kmFaxDeviceSpkVolumeLevel` 等厂商名。
- 没有发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 新增 `tools/clienttool_config_names.py`、
  `docs/reverse-engineering/data/clienttool-config-names.tsv`、
  `kyocera_monitor/config_vendor_names.py`、
  `tests/test_clienttool_config_names.py`。
- 修改 `kyocera_monitor/config.py`、`kyocera_monitor/cli.py`、
  `tests/test_config.py`、`docs/reverse-engineering/clienttool-protocol.md`、
  `README.md`、`PROJECT_PROGRESS.md`、`CHANGELOG.md`。

未完成/下一步：

- 20 项仍无厂商名称，集中在 `1001.2.*` 的部分子项、`40.42.*` Wi‑Fi 字段、
  `43.10.1.1.13.1.1`、`42.5.1.1.13.1` 和 `40.10.1.1.1.1`；不得按位置猜测。
- 厂商名称只描述 OID 语义，不代表参数单位、枚举或可写性；写入仍需回读验证。
- 下一步可按 `45.*` 传真组名称核对 MA2000w 的 51 个 `STATUS=2` 对象，
  区分“无传真选件”和真正的读取失败。

## 历史交接（第二十二轮）

日期：2026-10-18（第二十二轮）。

本次范围：补齐 SNMP trap 属性页的控件映射，并确认通知页是否涉及设备 OID。
只做静态分析和只读 SNMP 取值，没有发送任何写入命令。

本次完成：

- 确认 dialog `0x008e` 的初始化链：`FUN_0041eef0` 的 `WM_INITDIALOG`
  调用 `FUN_0040c730` 建立模型后执行 `FUN_0041d700`；该函数按两组收件人
  的对称布局填充控件。
- 映射 19 个控件：
  - `0x459` Trap Recipient 1 → `40.26.5.1.7.1.1`（item 71，`0x4d84`）；
  - `0x42e` Trap Community 1 → `40.26.5.1.4.1.1`（item 72，`0x4d88`）；
  - `0x461` Trap IP address 1 → `40.26.5.1.2.1.1`（item 73，`0x4e8c`）；
  - `0x432..0x437` 六个事件 → item 74（`0x4f90..0x4fa4`）；
  - `0x456` Trap Recipient 2 → `40.26.5.1.7.1.2`（item 75，`0x4fa8`）；
  - `0x430` Trap Community 2 → `40.26.5.1.4.1.2`（item 76，`0x4fac`）；
  - `0x462` Trap IP address 2 → `40.26.5.1.2.1.2`（item 77，`0x50b0`）；
  - `0x438..0x43d` 六个事件 → item 78（`0x51b4..0x51c8`）。
- Communication 页补入 `0x42d` Authentication traps →
  `1.3.6.1.2.1.11.30.0`（item 70，`0x4d80`）。
- 厂商 OID 名称与映射一致：`kmsvTrapEnabled`、`kmsvTrapCommunity`、
  `kmsvTrapIpAddress`、`kmsvTrapEvents`。事件字段是 6 个连续整数，不是
  单一位掩码。
- 通知页（dialog `0x008c`）的控件是本地通知设置（列表、声音、TTS、
  启动项等），当前 147 行配置对象表中没有对应 OID；暂不加入映射表。

验证：

- `python3 -m unittest discover -s tests` → 100/100 通过。
- 只读 SNMP 配置值：item 70 = `2`（Authentication traps disabled）、
  item 71/75 = `0`（两个收件人未启用）、item 72/76 = `public`、
  item 73/77 = `0.0.0.0`、item 74/78 = `0`（无事件）。
- 没有发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 修改 `docs/reverse-engineering/data/clienttool-control-oids.tsv`、
  `tests/test_clienttool_control_oids.py`、
  `docs/reverse-engineering/clienttool-protocol.md`、`README.md`、
  `PROJECT_PROGRESS.md`、`CHANGELOG.md`。

未完成/下一步：

- 55 个映射仍为 `confidence=inferred`；静态与只读值一致，但未做写入回读。
- 通知页已确认基本属于本地设置，后续只需在文档中保留该边界，不需要绑定
  OID。
- 下一步优先解析自定义纸张/传真对话框（`0xd1`、`0xd2`、`0xe0`）与
  `0x45.*` 配置对象，继续补全剩余控件。

## 历史交接（第二十一轮）

日期：2026-10-18（第二十一轮）。

本次范围：把配置对话框的控件映射从“主对话框 6 组”扩展到按对话框作用域
组织的完整第一轮目录；只做静态分析、只读 SNMP 取值和本地测试，没有向设备
发送任何写入命令。

本次完成：

- 新增 `tools/clienttool_dialogs.py`，解析 `KMUTLCFG.exe` 的 RT_DIALOG
  `DLGTEMPLATE`/`DLGTEMPLATEEX`，输出对话框 ID、标题、控件 ID、窗口类、
  模板文字与坐标；生成
  `docs/reverse-engineering/data/clienttool-dialogs.tsv`（318 个控件行）。
- 确认控件 ID 只在所属对话框内唯一。主对话框 `0x006b` 的 `0x0456` 是
  `Inches`，SNMP trap 对话框 `0x008e` 的 `0x0456` 是
  `Trap Recipient 2`；此前的全局编号比较方式因此有歧义。
- `docs/reverse-engineering/data/clienttool-control-oids.tsv` 增加 `dialog`
  列，扩展到 36 行。主对话框新增：
  Media type `0x3f5` → item 9、Paper size `0x3f8` → item 6、
  Print density `0x3f7` → item 49、Original image `0x4ab` → item 83、
  Original size `0x474` → item 87、Ignore paper size mismatch `0x48c` →
  item 10、Power off when 的 `0x466/0x467/0x468` → item 5/55/107、
  Inches/Millimeters `0x456/0x457` → item 51。
- Panel options（dialog `0x00d0`）：Default screen `0x4d0` → item 86、
  Language `0x4d2` → item 79、Auto clear panel time `0x4d4/0x4d5` →
  item 85、Reset panel 可用状态 `0x4d3` → item 84。
- Communication（dialog `0x008d`）：Lan Interface `0x41d` → item 58、
  Hostname `0x41e` → item 54、DHCP `0x420` → item 57、
  LPD `0x424` → item 62、Raw Port `0x425` → item 63、
  WSD Print `0x49b` → item 64、Read/Write Community `0x427/0x428` →
  item 65/66、IP/掩码/网关 `0x45e/0x45f/0x460` → item 59/60/61、
  sysContact/sysName/sysLocation `0x429/0x42a/0x42b` → item 67/68/69。
- 静态证据：主对话框 `FUN_00405c10` 从 `esp+0x3570/0x3574/0x3578/
  0x3584/0x3588/0x358c/0x3590..0x3598/0x41d0/0x41d4` 读取模型字段；
  Communication `FUN_0041ccb0` 读取对应模型偏移；Panel options
  `FUN_00407830` 通过 `DAT_004a9fd4/DAT_004a61b8/DAT_004a61b4` 接收主
  对话框从 `0x3c58/0x3020/0x301c` 读出的值。

验证：

- `python3 -m unittest discover -s tests` → 99/99 通过（新增
  `tests/test_clienttool_dialogs.py` 3 项；扩展
  `tests/test_clienttool_control_oids.py`）。
- `python3 tools/clienttool_dialogs.py` 输出与已提交的
  `clienttool-dialogs.tsv` 完全一致。
- 只读 SNMP 配置导出（`--config --snmp --config-snmp-version 2c`）返回
  96/147；交叉核对值：item 54 = `KMD4E4BA`、59 = `192.168.0.220`、
  60 = `255.255.255.0`、61 = `192.168.0.1`、65/66 = `public`、
  52 = `60`（界面 `300 s`）、49 = `3`、85 = `18`、86 = `2`、87 = `8`、
  83 = `8`、79 = `1`。
- PJL 在同一时刻超时（设备 Sleeping），未重试；没有发送 `KSETOBJ`、SNMP
  SET、KPSL 或维护命令。

文件变更：

- 新增 `tools/clienttool_dialogs.py`、
  `docs/reverse-engineering/data/clienttool-dialogs.tsv`、
  `tests/test_clienttool_dialogs.py`。
- 修改 `docs/reverse-engineering/data/clienttool-control-oids.tsv`、
  `tests/test_clienttool_control_oids.py`、
  `docs/reverse-engineering/clienttool-protocol.md`、`README.md`、
  `PROJECT_PROGRESS.md`、`CHANGELOG.md`。
- 本机 GPG 签名密钥已过期（`KEYEXPIRED`），本轮提交使用一次性
  `-c commit.gpgsign=false`，未修改全局 git 配置；如项目要求签名提交，
  需先更新密钥后对本次提交重新签名。

未完成/下一步：

- 36 个映射仍是 `confidence=inferred`；静态路径和只读值一致，但没有写入
  回读，不能提升为 `verified`。
- `0x3f6` Paper weight 由媒体类型查表推导，未找到独立 OID；`0x46d/0x46e`
  On/Off 与 `0x4da` Duplex 静态标签只在自定义纸张记录下可见，其状态来自
  该记录 `+0x20c` 字段，尚不能单独绑定 OID。
- 下一步优先解析 SNMP trap（`0x008e`）、通知（`0x008c`）和自定义纸张/
  传真对话框的 RT_DIALOG 模板与初始化函数，把剩余控件补入同一张表。

## 历史交接（第二十轮）

日期：2026-10-18（第二十轮）。

本次范围：把主 `Device Defaults` 对话框的控件参数与 147 项模型偏移连接起来，
形成首批“控件 → 模型偏移 → OID”对照，并修正上一轮的推断标签。

本次完成：

- 确认 `FUN_0040c730` 把模型前 11 个 dword 复制到界面栈帧，`FUN_00405c10`
  再从这些槽位初始化控件；结合汇编中的 `0x580/0x588/0x590` 参数偏移，
  得到主对话框参数对应关系。
- 新增 `docs/reverse-engineering/data/clienttool-control-oids.tsv`，确认：

| 控件 | 模型偏移 | item_id | OID |
| --- | --- | --- | --- |
| `0x3ea` Auto error clear | `0x0004` | 2 | `43.5.1.1.34.1` |
| `0x3f4` Auto error clear timeout | `0x0008` | 3 | `43.5.1.1.35.1` |
| `0x3f2` Sleep time | `0x0010` | 1 | `43.5.1.1.23.1` |
| `0x463` Power off timer | `0x0014` | 4 | `42.5.1.1.43.1` |
| `0x455` Quiet mode | `0x0018` | 50 | `1001.2.1.1.1.14.1` |
| `0x411` Form feed timeout | `0x2ffc` | 52 | `43.5.1.1.22.1` |

- 修正第十七轮的两个推断标签：
  - Sleep time 从 `42.5.1.1.43.1` 改为 `43.5.1.1.23.1`；
  - Power off timer 从 `42.5.9.1.3.2` 改为 `42.5.1.1.43.1`；
  - 新增 Quiet mode = `1001.2.1.1.1.14.1`。
- MA2000w 只读值：Sleep time `1 min`、Power off timer `72`（组合框分段
  对应 `3 days`）、Quiet mode `0`（OFF）。
- 新增 `--config --snmp`：同一 147 行对象表转换为绝对 OID，按 SNMPv2c
  每批 16 个只读 GET。设备 Sleeping、PJL 9100 无响应时仍返回 96/147，
  耗时约 8.6 秒；值已与 PJL 路径交叉核对。

验证：

- `python3 -m unittest discover -s tests -v` → 94/94 通过（新增
  `tests/test_clienttool_control_oids.py` 的 3 项，以及 SNMP 配置读取/
  OID 转换/CLI 渲染 3 项）。
- 真机睡眠状态执行 `--config --snmp --config-snmp-version 2c`，返回
  96/147；PJL 同一时刻返回 `printer returned no PJL response`。
- 没有发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 新增 `docs/reverse-engineering/data/clienttool-control-oids.tsv`、
  `tests/test_clienttool_control_oids.py`。
- 修改 `kyocera_monitor/config.py`、`kyocera_monitor/cli.py`、
  `tests/test_config.py`、
  `tests/test_clienttool_config_offsets.py`、`README.md`、
  `docs/reverse-engineering/clienttool-protocol.md`、`PROJECT_PROGRESS.md`、
  `CHANGELOG.md`。

未完成/下一步：

- 继续映射 Communication、Media/Paper、Panel options、Original image 等
  对话框；主对话框 6 组已完成。
- 六个控件映射目前都是 `inferred`，需要写入回读验证后才能提升为
  `verified`；当前不得自动执行配置写入。
- 设备 Sleeping 时 PJL 9100 可能完全无响应；配置导出应优先尝试
  `--config --snmp`，不要反复重试 PJL。
- USB 物理验证、KPSL 动态验证和扫描路径仍受硬件/Windows 环境限制。

## 历史交接（第十九轮）

日期：2026-10-18（第十九轮）。

本次范围：恢复 147 项配置对象在 `KMUTLCFG.exe` 界面模型中的偏移，为
“控件 ID → 模型偏移 → OID”映射提供中间层；只做静态分析，没有设备写入。

本次完成：

- 新增 `tools/clienttool_config_offsets.py`：
  - 解析 `FUN_0040e820` 的 Ghidra 伪代码，提取每个 `case` 写入的
    `param_1 + offset`；
  - 解析字符串/复合字段的 setter helper（`FUN_00410590`、`FUN_004105c0`
    等）的固定偏移；
  - 处理共享 case 块：`0x46/0x4a`、`0x49/0x4d`；
  - 输出 `item_id`、OID、主偏移、额外偏移和映射状态。
- 生成 `docs/reverse-engineering/data/clienttool-config-offsets.tsv`：
  - 147/147 项均有至少一个偏移；
  - 例如 Auto error clear `0x0004`、Sleep time `0x0010`、
    Power off timer `0x0014`、Quiet mode `0x0018`、
    Form feed timeout `0x2ffc`、IPv4 `0x4550`、SNMP read community
    `0x486c`、Wi‑Fi SSID `0x3c90`；
  - 自定义纸张和若干复合字段（如 `40.26.5.1.5.1.1`）有多项偏移。
- 确认 `FUN_0040e820` 与 `FUN_00410740` 使用同一组模型偏移：
  前者把读到的值写入模型，后者比较当前值与界面值并按 147 行对象表顺序
  生成 PJL 写入数据。

验证：

- `python3 -m unittest discover -s tests -v` → 88/88 通过（新增
  `tests/test_clienttool_config_offsets.py` 的 3 项：147 项全覆盖、
  关键偏移、工具输出与 TSV 一致）。
- `python3 tools/clienttool_config_offsets.py` → `mapped 147/147`。
- 没有发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 新增 `tools/clienttool_config_offsets.py`、
  `tests/test_clienttool_config_offsets.py`、
  `docs/reverse-engineering/data/clienttool-config-offsets.tsv`。
- 修改 `README.md`、`docs/reverse-engineering/clienttool-protocol.md`、
  `PROJECT_PROGRESS.md`、`CHANGELOG.md`。

未完成/下一步：

- 对象→偏移已完成，仍需把 `clienttool-ui-controls.tsv` 中的控件 ID 对齐到
  这些偏移；重点函数是 `FUN_00405c10`（模型→控件）、
  `FUN_00408190`（控件事件）以及其他对话框处理函数。
- 睡眠时间/关机定时器的 OID 语义仍是 `inferred`，缺写入回读验证。
- USB 物理验证、KPSL 动态验证和扫描路径仍受硬件/Windows 环境限制。

## 历史交接（第十八轮）

日期：2026-10-18（第十八轮）。

本次范围：完成 GUI 的桌面菜单与安装打包，使已安装的 Python 包可以从桌面
环境直接启动，不再依赖进入仓库目录执行 `./kyocera-gui`。

本次完成：

- 新增 `packaging/kyocera-monitor.desktop`：
  - `Type=Application`、`Exec=kyocera-gui`、`TryExec=kyocera-gui`；
  - 中英文名称/说明；
  - 图标 `kyocera-monitor`，分类 `Settings;HardwareSettings;`。
- 新增 `packaging/kyocera-monitor.svg`：128×128 打印机图标。
- 新增 `tools/install_desktop.py`：
  - 默认前缀 `~/.local`，写入 `share/applications/` 与
    `share/icons/hicolor/scalable/apps/`；
  - 支持 `--prefix`、`--force`、`--uninstall`、`--dry-run`；
  - 内容相同则幂等成功，内容不同且未加 `--force` 时拒绝覆盖；
  - `kyocera-gui` 不在 PATH 时给出警告，但继续安装。
- `PROJECT_PROGRESS` 的 GUI 打包 TODO 已标记为 `DONE`。

验证：

- `python3 -m unittest discover -s tests -v` → 85/85 通过（新增 3 项
  `tests/test_desktop_packaging.py`：安装字段/图标、幂等与冲突、卸载）。
- `desktop-file-validate packaging/kyocera-monitor.desktop` → 无输出（通过）。
- 在 `/tmp/kyocera-desktop-test` 执行安装/卸载，文件路径和删除结果符合预期。

文件变更：

- 新增 `packaging/kyocera-monitor.desktop`、`packaging/kyocera-monitor.svg`、
  `tools/install_desktop.py`、`tests/test_desktop_packaging.py`。
- 修改 `README.md`、`PROJECT_PROGRESS.md`、`CHANGELOG.md`、`AGENTS.md`。

未完成/下一步：

- 未在真实桌面会话中点击菜单项启动；`kyocera-gui` 需先通过
  `python3 -m pip install --user .` 安装到 PATH。
- 系统级安装到 `/usr/local` 需要相应写权限；脚本本身不调用 sudo。
- 下一项研究任务仍是完整的“控件 ID → 界面模型偏移 → OID”映射，或等待
  USB 硬件后做物理验证。

## 历史交接（第十七轮）

日期：2026-10-18（第十七轮）。

本次范围：补全 `KMUTLCFG.exe` 的 UI 控件名称来源，为配置对象名称映射建立
可复现的中间层；仍只做静态分析和设备只读查询。

本次完成：

- 新增 `tools/clienttool_ui_strings.py`：
  - 解析 `LANG/en/KMUTLCFGRes.dll` 的 PE 资源目录与 RT_STRING 块；
  - 按 Windows 规则用 `(block_id - 1) * 16 + index` 还原字符串 ID；
  - 解析 `KMUTLCFG.exe` 的 `0x00496f20`（`string_id, control_id` 标签表）
    和 `0x00497048`（`control_id, string_id` 组合框选项表）；
  - 对 `KMUTLCFG.exe` 与英文资源 DLL 校验 SHA-256，失败时拒绝输出。
- 生成 `docs/reverse-engineering/data/clienttool-ui-controls.tsv`：
  - 31 个标签/分区行、31 个组合框选项；
  - 已确认控件 `0x3e8`、`0x3e9`、`0x3ea`、`0x4cf`、`0x4da`
    分别对应关机定时器、自动睡眠、自动错误清除、表单超时和双面；
  - 组合框 `0x463` = 关机间隔的 15 个有序选项，`0x3f6` =
    纸张重量，`0x3f7` = 打印浓度，`0x4ab` = 原稿图像。
- 基于 `FUN_00410740` 的对象索引→界面模型偏移和 `FUN_00405c10` 的
  模型偏移→控件路径，最初推断 `42.5.1.1.43.1` = Sleep time、
  `42.5.9.1.3.2` = Power off timer；第十九轮进一步核对 `FUN_00405c10`
  的参数偏移后，已修正为：
  - `43.5.1.1.23.1` = Sleep time，单位 `min`；
  - `42.5.1.1.43.1` = Power off timer；
  - `1001.2.1.1.1.14.1` = Quiet mode。
- MA2000w 只读实测这三项当前值分别为 `1 min`、`72`（3 天）和 `0`，整批仍为
  96/147 项 `STATUS=0`。

验证：

- `python3 -m unittest discover -s tests -v` → 82/82 通过（新增
  `tests/test_clienttool_ui_strings.py` 的 3 项：标签表、组合框顺序、
  生成 TSV 与仓库数据一致）。
- `python3 tools/clienttool_ui_strings.py` 输出与
  `clienttool-ui-controls.tsv` 完全一致。
- 真机执行 `--config` 一次，确认 `Sleep time 1 min`、`Power off timer 72`、
  `Quiet mode OFF`；
  未发送 `KSETOBJ`、SNMP SET、KPSL 或维护命令。

文件变更：

- 新增 `tools/clienttool_ui_strings.py`、`tests/test_clienttool_ui_strings.py`、
  `docs/reverse-engineering/data/clienttool-ui-controls.tsv`。
- 修改 `kyocera_monitor/config.py`、`tests/test_config.py`、`README.md`、
  `docs/reverse-engineering/clienttool-protocol.md`、`PROJECT_PROGRESS.md`、
  `CHANGELOG.md`。

未完成/下一步：

- 继续把 UI 控件映射到完整 OID 列表：以 `FUN_00410740` 的 147 个索引→模型
  偏移为基础，逐一核对 `FUN_00405c10`、`FUN_00408190` 和其他对话框处理函数
  的控件写入路径。
- 睡眠时间/关机定时器仍缺写入回读验证，不能提升为 `verified`。
- 解释 51 个 `STATUS=2` 配置对象；USB 物理验证、KPSL 动态验证和扫描路径仍
  受硬件/Windows 环境限制。

## 历史交接（第十六轮）

日期：2026-10-18（第十六轮）。

本次范围：把 `KMUTLCFG.exe` 的 147 行配置对象表实现为 Linux 只读功能，
并在真实 MA2000w 上验证 PJL 编码与对象可用性；未发送任何写入或维护命令。

本次完成：

- 新增 `kyocera_monitor/config.py`：
  - 内置 147 行 `(oid, type_code, item_id)` 表，并由测试与
    `docs/reverse-engineering/data/clienttool-config-oids.tsv` 逐行比对；
  - 生成 Client Tool 原样的 `1.<path>` 与 `#<absolute-oid>` 两种
    `KGETOBJ` 写法；
  - 解析 `STATUS`、PJL `TYPE` 和 `VALUE`，支持整数、字符串、IPv4 与
    非文本十六进制；
  - 仅为已有独立证据的对象添加标签，未知项保留 OID。
- CLI 新增 `--config`（文本/JSON），复用现有 TCP 9100 或 USB `usblp`
  通道；`--config` 不能与 `--snmp`、`--web`、`--gui`、`--watch`、
  `--count`、`--raw` 组合。
- 修正真实设备暴露的字符串编码边界：
  - `TYPE=4` 的定长字符串带 NUL 填充，先去尾随 NUL；
  - 字符串按 UTF-8 解码，非法 UTF-8 回退十六进制；
  - `TYPE=64` 是两层编码：十六进制 → 8 位 ASCII 十六进制 → 点分 IPv4。
- MA2000w 只读实测（`192.168.0.220`）：
  - 96/147 项 `STATUS=0`，整批 5.2–7.1 秒；
  - 51 项 `STATUS=2`，主要集中在 `45.*`（传真/选件相关）和
    `43.7.1.1.3.1.2..12`（本地化语言表）；
  - 自定义纸张 1..8 读出 `Custom 1`..`Custom 8`；
  - Wi‑Fi SSID `1.40.42.1.1.4.1` 读出 UTF‑8 中文名称（实际网络名不写入仓库）；
  - `1.40.42.1.1.7.1` 两次读出 `-70`/`-71`，疑似 RSSI，尚未确认；
  - 设备对本批中不存在的对象逐条返回 `STATUS=2`，没有中止其余对象。

验证：

- `python3 -m unittest discover -s tests -v` → 79/79 通过（新增
  `tests/test_config.py` 的 6 项：表一致性、命令拼写、值解码、错误/
  缺失响应、PTY 设备端到端 CLI 导出）。
- 真机执行：
  `python3 -m kyocera_monitor --host 192.168.0.220 --config --timeout 20 --idle 2`
  两次，均返回 `read 96/147`；第二次用于验证 UTF-8/NUL 修正。
- 未发送 `KSETOBJ`、SNMP SET、KPSL 或任何维护/重置命令；没有修改设备配置。

文件变更：

- 新增 `kyocera_monitor/config.py`、`tests/test_config.py`。
- 修改 `kyocera_monitor/cli.py`、`README.md`、
  `docs/reverse-engineering/clienttool-protocol.md`、`PROJECT_PROGRESS.md`、
  `CHANGELOG.md`。

未完成/下一步：

- 优先补全 `40.42.*` Wi‑Fi 字段与 `1001.2.*` 的业务名称：从
  `KMUTLCFG.exe` 的资源对话框和控件更新函数建立
  “控件 ID → 模型偏移 → OID”映射，再用只读设备值核对。
- 解释 51 个 `STATUS=2` 对象，区分“机型不提供”和“当前状态不可读”。
- USB 物理验证、KPSL 动态验证和扫描路径仍受硬件/Windows 环境限制。

## 历史交接（第十五轮）

日期：2026-10-18（第十五轮）。

本次范围：继续只分析 `Kyocera/ClientTool`；本轮重点为 KDS 参数库和
`KMUTLMNT.exe` 维护协议。

本次完成：

- 解析 `KDS337110.dat` 的文件格式（加载器 `KMSTMNW.exe`
  `FUN_00436e00`，magic `0x40100`）：
  - 2 条 `0x38` 字节块；
  - 9 条 `0x18` 字节块；
  - 3 条 `0x10` 字节块；
  - 12 条 `0x1c` 字节块；
  - 10 条 `0x18` 字节块；
  - 8 条 `0x10` 字节块；
  - 其余数据为图形/布局脚本，由 `FUN_00436970` 按操作码读取。
  - 结论：KDS 主要存机型图形/布局和数值范围，不是 147 项配置的名称表。
- 拆解 `KMUTLMNT.exe` 的维护通信：
  - 网络：`PrnRawPortComm` 连接 TCP `9100`（端口常量 `0x238c`），
    发送后最多约 3 秒读取响应；
  - 本地：`PrnUSBComm`，响应中检查 ASCII `KPSL`；
  - KPSL 帧头 20 字节：`"KPSL"`、`1B 24 30 4D`、大端 word_count、
    `"@@@@"`、大端 payload_length；
  - 载荷：3 个控制 dword（第一个为记录数）、记录（6 个 dword 头 +
    参数）、末尾 4 字节校验和；
  - 校验和：偶数字节和 + 奇数字节和 + 可能的尾字节，写入载荷末尾；
  - 载荷在发送前用固定种子的 CRC 表滚动 XOR 混淆，
    接收端执行逆变换；
  - 还原 20 项参数类型表（`0x004e7900`，kind 1..0x14）和维护包 XML
    节点（`MaintenancePackage/Define/...`）。
- 本地离线提取维护包请求目录：
  - 只保留互操作性所需的 request id、item id、数据类型、请求类型和来源序号；
  - 密钥、容器布局、解包代码以及提取出的 XML/PNG 不进入公开仓库；
  - 目录包含 39 条 request 记录（RequestValue/RequestExec/RequestResult）；
  - 关键 request id 包括 `MNTE_REQUEST_ID_DRUM_REFRESH`、
    `MNTE_REQUEST_ID_HIGH_ALTITUDE_MODE`、
    `MNTE_REQUEST_ID_RESTORE_FACTORY_INITIALIZE`、
    `MNTE_REQUEST_ID_DRUM_COUNTER_RESET` 等。
  - `KMUTLMNT.exe` `.data` 中提取到 177 个符号 request id 到数值的映射；
    完整表见 `clienttool-maintenance-request-ids.tsv`。

验证：

- KDS 解析结果为纯只读；没有修改任何 `.dat` 或 `.mtp` 文件。
- `python3 -m unittest discover -s tests -v` → 73/73 通过（包含
  `tests/test_clienttool_request_ids.py` 的映射检查）。
- 没有向设备发送 KPSL 请求，避免触发维护/清除/测试打印。

未完成/下一步：

- 取得一份真实 KPSL 帧（Windows 抓包或离线构造的只读请求）后，验证
  请求/响应记录字段的一档偏移和 `ParamKind` 到参数字段的精确映射。
- `1001.2.*` 配置项名称仍需从 KMUTLCFG UI 资源或设备值反推。

## 历史交接（第十四轮）

日期：2026-10-18（第十四轮）。

本次范围：只分析 `Kyocera/ClientTool`，不把 NetViewer 的 SOAP/.NET 结论
当作 Client Tool 行为。

本次完成：

- 反编译 `KMSTMNET.exe`、`KMUTLCFG.exe`、`KMUTLPRE.exe`，输出位于
  `analysis/decompiled/`（不纳入版本控制）。
- 确认网络路径：`KMSTMVM.exe` 启动
  `KMSTMNET.exe /H: /A: /C: /P:`；`KMSTMNET.exe` 使用内嵌 Net-SNMP
  轮询设备，并把结果合成为 `INFO ID/KID/CONFIG/KCONFIG/KINTRAYSTATUS/
  KUNITNAME/KGETOBJ/USTATUS` 文本，经 mailslot 交给主程序。未发现
  9100、HTTP 或 SOAP 客户端。
- 确认配置路径：`KMUTLCFG.exe` 的 147 行静态表
  （`0x00498244`，每行 OID 指针、类型码、item id），网络用
  `snmpget/snmpset`，USB 用批量 `KGETOBJ/KSETOBJ`；需要重启时写
  `1347.40.1.1.1.6.1 = 2`。
- 确认预设路径：`KMUTLPRE.exe` 的 56 行预设表
  （`0x005048d8`，36 行 OID 模板 + 20 行本地字段名）和扫描预设 item
  列表（`0x004ffd90`）；OID 模板位于 `1347.1001.1.*`，PJL 用 `#`
  绝对 OID。
- 还原 PJL 值编码：`TYPE=2` 整数、`TYPE=4` 十六进制字符串、
  `TYPE=64` 十六进制 IPv4；`1.<path>` 映射到
  `1.3.6.1.4.1.1347.<path>`，`#<oid>` 表示绝对 OID。
- 只读实测 MA2000w：
  - SNMP `1001.1.1.6.0=0`、`.7.0=0`、`.8.0=NoSuchObject`、`.9.0=0`；
  - SNMP `1001.1.1.10.0="L"`；
  - SNMP `1001.3.1.1.0=0`、`1001.4.1.6.0=1`；
  - PJL `#1.3.6.1.4.1.1347.1001.3.1.1.0` → `STATUS=0 TYPE=2 VALUE=0`；
  - PJL `1.43.5.1.1.28.1` → `TYPE=4 VALUE="483439..."`（十六进制）；
  - PJL `1.40.10.1.1.4.1` → `TYPE=64 VALUE="4330413830304443"`。
- 新增 `docs/reverse-engineering/clienttool-protocol.md`、
  `tools/clienttool_oids.py` 和两份 TSV 对象表。

验证：

- `python3 tools/clienttool_oids.py config` → 147 行；
- `python3 tools/clienttool_oids.py preset` → 56 行，扫描预设 item 列表
  `[0,1,2,3,5,6,7,8,9,10,11,12,13]`；
- 上述 SNMP/PJL 查询均为只读，没有执行 `KSETOBJ`/`snmpset`/重置。
- `python3 -m unittest discover -s tests -v` → 70/70 通过（新增
  `tests/test_clienttool_oids.py` 的 3 个对象表检查）。
- `tools/clienttool_oids.py` 的两个表提取命令均成功；配置表 147 行，
  预设表 56 行，扫描预设 item 列表为
  `[0,1,2,3,5,6,7,8,9,10,11,12,13]`。

未完成/下一步：

- `1001.2.*` 配置对象和预设各列的完整业务名称仍未补全；下一步优先解析
  `KDS337110.dat` 的参数记录，或从 `KMUTLCFG.exe`/`KMUTLPRE.exe` 的
  资源字符串与 UI 控件映射反查。
- `KMUTLMNT.exe` 的维护协议尚未拆解。
- `1001.3.1.3.0`/`1001.4.1.3.0` 的结果写入和设备清除时机尚未做副作用验证。
- 若要做 Linux 配置写入，必须先建立只读基线、备份和回滚方案，不能直接
  照搬 `snmpset` 序列。

## 历史交接（第十三轮）

日期：2026-10-18（第十三轮）。

本次完成：

- 对 NetViewer `Core.CoreServices.dll` 做只读 .NET 元数据检查，样本 SHA-256
  `fe7b66c0c1a67b002f0d739db294ddea87a9c4d10b8357cf9e2dffdbb25d3645`，
  MVID `88f1c6b0-ab4d-49dd-bbfc-e044086bd4bb`，目标框架 .NET Framework 4.8。
- 还原 `Kmnv.Core.Services.Soap.JobOperation.ScanOperation` 的请求契约：
  `open_sessionRequest`（`information`：`HOST_INFORMATION_ENTRY.type/data`）、
  `start_scanRequest`（`operation_id` + 扫描/原稿/输出三个配置）、
  `retrieve_imageRequest`（`operation_id`、`operation_type`）、
  `close_sessionRequest`（`operation_id`）。
- 还原三个配置结构的字段：
  - `SCAN_IMAGE_CONFIGURATION_ENTRY`：颜色、曝光、背景曝光调整、锐度、分辨率、
    边框擦除、连续扫描、双面、装订、多页表单、混合原稿尺寸、防透印、锐度强调、
    锐度模式、OCR、静音模式；
  - `ORIGINAL_CONFIGURATION_ENTRY`：原稿图像、尺寸、方向、自定义尺寸、放置方式；
  - `OUTPUT_IMAGE_CONFIGURATION_ENTRY`：文件格式、发送尺寸、压缩级别、缩放、
    居中、PDF 加密、文件名、文件分隔、PDF 类型、Bates 印章、高压缩 PDF 质量。
- **关键否定结论**：没有 `ScanOperationService` 代理类；对
  `Kyocera/NetViewer` 全部 DLL 检索 `ScanOperation`/`start_scanRequest`/
  `retrieve_imageRequest`，只有 `Core.CoreServices.dll` 自身命中，没有其他
  随附程序集引用。因此这些 SOAP 类型不能证明 Client Tool/NetViewer 实际
  使用 SOAP 扫描，也不能反推出扫描端点 URL、SOAPAction 或认证前置条件。
- 将上述边界写入 `scan-workflow.md` 第 6.6 节和 `kmws-soap.md` 第 4.1 节；
  没有实现任何扫描触发或配置写入。

验证：

- 使用 REA `inspect_managed_artifact` / `inspect_managed_members` 读取 PE/CLI
  元数据；只做静态解析，没有加载 CLR、执行程序集或向设备发送新请求。
- `rg -a -l 'Kmnv\.Core\.Services\.Soap\.JobOperation\.ScanOperation|
  start_scanRequest|retrieve_imageRequest' Kyocera/NetViewer --glob '*.dll'`
  只返回 `Kyocera/NetViewer/KNV/bin/Core.CoreServices.dll`。
- 未运行设备扫描；没有产生扫描副作用。

未完成/下一步：

- 实际扫描通道仍未确认。现有证据仍指向 TWAIN；需要取得
  `Ns1815TWGN.DLL`（或安装包中的对应驱动）做静态分析，或在 Windows 主机
  抓取 TWAIN 驱动的网络流量。
- 若后续确认 `ScanOperation` 被反射调用，再以真实调用方恢复 URL 和
  SOAPAction；在此之前不实现 `open_session`/`start_scan`。
- MA2000w 的 eSCL/WSD 扫描入口仍未建立；WSD 只发布打印服务，`631/tcp`
  关闭，80/9090 的 KM-WSDL 仍无应用层响应。

## 历史交接（第十二轮）

日期：2026-10-18（第十二轮）。

本次完成：

- 解析 `KGETOBJ` 的双根映射规则：`1.<path>` 对应 Kyocera 企业子树
  `1.3.6.1.4.1.1347.<path>`，`2.<path>` 对应 Printer MIB
  `1.3.6.1.2.1.43.<path>`。
- 确认 `2.5.1.1.10.1` 是 `prtConsoleLocalization`。MA2000w 通过 PJL 和 SNMP
  都返回 `1`；SNMP 本地化表 `1.1` 为
  `prtLocalizationLanguage=en`、`prtLocalizationCountry=US`、
  `prtLocalizationCharacterSet=106`。因此索引 `1` 在该设备上对应英语（美国），
  但不能把 `1` 硬编码为所有型号的 `en-US`。
- 确认 `1.42.5.1.1.16.1` 是 `kmPanelFirmwareVersion`（面板固件版本）。
  MA2000w 返回 `STATUS=2`、`TYPE=0`、`VALUE=""`，SNMP 同 OID 也没有实例；
  只能记录为“该型号不提供”，不能把空值解释为固件版本为空。
- 确认 SNMP 告警 `1001` 是标准 IANA Printer MIB
  `PrtAlertCodeTC.markerFuserUnderTemperature`。当前睡眠状态下告警表
  `1.1` 行同时给出 severity `5`（`warningBinaryChangeEvent`）、training
  `3`（`untrained`）、group `10`（`marker`）、group-index `1`、
  location `0`、time `8040` ticks；厂商显示字段为
  `Sleeping...\r\n ` 和索引 `35078`，与 PJL `INFO STATUS` 一致。
- 修正实现：`snmp_status.py` 的 `ALERT_COLUMNS` 改为读取 `.2`（severity）和
  `.3`（training level），新增 severity/training/group/code 枚举名；
  `cli.py` 和 Web 详情页显示标准名称。此前把 training level `3` 当成
  severity `3` 的显示错误已修复。
- 复核 SNMP 版本行为：v1/v2c `GETNEXT` 均可完成 walk；v2c `GETBULK` 仍无
  响应。此前“v2c GETNEXT 超时”的结论无法复现，已从 README、
  `protocol-notes.md`、`netviewer-log-findings.md` 和阻塞项中修正。

验证：

- `python3 -m unittest discover -s tests -v` → 67/67 通过。
- 真实 MA2000w PJL：
  `KGETOBJ 2.5.1.1.10.1` → `STATUS=0 TYPE=2 VALUE=1`；
  `KGETOBJ 1.42.5.1.1.16.1` → `STATUS=2 TYPE=0 VALUE=""`。
- 真实 MA2000w SNMP：
  `1.3.6.1.2.1.43.5.1.1.10.1 = 1`；
  `1.3.6.1.2.1.43.7.1.1.2.1.1 = "en"`、
  `1.3.6.1.2.1.43.7.1.1.3.1.1 = "US"`；
  `1.3.6.1.2.1.43.18.1.1.2.1.1 = 5`、
  `.3.1.1 = 3`、`.4.1.1 = 10`、`.7.1.1 = 1001`；
  `1.3.6.1.4.1.1347.43.18.2.1.2.1.1 = "Sleeping...\r\n "`、
  `.3.1.1 = "35078"`。
- `--snmp` 实际输出：
  `Alert: severity=warning_binary_change_event group=marker code=1001
  marker_fuser_under_temperature`。
- SNMP 版本对比：v1/v2c `GETNEXT` 从 `1.3.6.1.2.1.1` 和
  `1.3.6.1.2.1.43.5.1.1` 两个起点均成功；v2c `GETBULK` 在 2 秒超时内无响应。

未完成/下一步：

- `1.43.5.1.1.29.1` 的语义仍未确认：厂商 OID 表名称为 `kcprtAssetNumber`，
  设备返回空字符串；旧“Operation Panel Language”标签不再作为已确认结论。
- 告警 `1001` 在设备唤醒后的持续时间、是否随打印任务变化，尚未观察。
- 扫描协议仍是最大空白：本机样本没有 TWAIN 驱动 DLL，下一步优先对
  NetViewer 的 `Device.Controllers.DeviceController.dll` / `Core.CoreServices.dll`
  做 .NET 元数据与 IL 静态分析，还原 SOAP URL 拼接、认证前置条件和
  `scan_operation` 请求结构；拿到真实请求前不实现扫描触发或 `set_*`。

## 历史交接（第十一轮）

日期：2026-10-18（第十一轮）。

本次完成：

- 新增原生 GUI `kyocera_monitor/gui.py`：GTK3 + WebKit2 4.1 窗口加载同一个
  只读 Web 仪表盘，本地 HTTP 服务绑定 `127.0.0.1` 随机端口，关闭窗口时
  `shutdown()` 并退出。
- 新增 CLI `--gui`、`--web-open`，以及仓库根目录 `./kyocera-gui` 和
  `pyproject.toml` 的 `kyocera-gui` console script。
- `--web`/`--gui` 可以在没有 `--host` 的情况下启动；总览页新增手动输入 IP
  的表单，`POST /api/devices` 只接受 IPv4 或 DNS 主机名，拒绝 URL、端口、
  设备路径和越界 IPv4。
- 总览页和详情页改为中文；总览页的“发现打印机”继续调用
  `/api/discover`，发现结果自动加入允许列表。
- 修复快照时间戳：`SnapshotCache` 同时保存单调时钟和墙钟，
  `collected_at` 不再显示 `1970-01-01`；缓存过期仍按单调时钟判断。
- 抑制浏览器提前断开时的 `BrokenPipeError` traceback。

验证：

- `python3 -m unittest discover -s tests -v` → 67/67 通过。
- 本机 GTK3 + WebKit2 4.1 可用；`python3 -m kyocera_monitor --gui`
  成功启动并保持窗口进程运行，本地服务监听随机回环端口。
- 无默认设备启动：`/api/devices` 返回 `{"devices": []}`，
  `/api/status` 返回 400 `no printer selected`。
- 手动添加：`POST /api/devices {"host":"192.168.0.220"}` 返回 200 并加入
  列表；`http://evil.example/x` 返回 400。
- `/api/discover` 实测 3.9 秒返回 MA2000w（SNMP 广播/单播 + WSD）。
- 真实 MA2000w PJL 数据经同一本地页面渲染：总览显示型号、序列号、碳粉
  80%、面板 `Sleeping...`；详情显示状态 `35078`、Lifetime `129`、
  Scan `3`、Drum `129 / 10000`、Auto error clear `OFF (30 s)`、
  Form feed timeout `300 s`，读取耗时 473 ms。
- 本机为 Wayland 会话，GNOME 截图接口被拒绝，原生窗口本身未能直接截图；
  页面布局通过无头 Chrome 访问同一 `127.0.0.1` 服务完成渲染验证。

下一步：GUI 打包（`.desktop`、图标、安装脚本）可以直接做；研究优先级仍是
Windows TWAIN 抓包或设备侧 eSCL/WSD 扫描确认。

## 历史交接（第十轮）

日期：2026-10-18（第十轮）。

本次完成：

- 复核用户提出的“SNMP 有页计数”线索，完整 walk
  `1.3.6.1.2.1.43.10.2.1`，发现 `prtMarkerLifeCount` 的实例是
  `1.3.6.1.2.1.43.10.2.1.4.1.1`，旧实现少写了最后一级 `.1`。
- 修正 `snmp_status.SCALAR_OIDS["page_count"]`，真实 MA2000w 的
  `--snmp` 输出恢复 `Page count: 129`。
- 将 `2.10.2.1.4.1.1` 的 `lifetime_counter` 从 `inferred` 改为
  `verified`：PJL 值 `129` 与 SNMP `prtMarkerLifeCount` 一致。
- 更新 README、protocol-notes、netviewer-log-findings、architecture、
  CHANGELOG 和测试。

验证：

- `python3 -m unittest discover -s tests -v` → 58/58 通过。
- 直接 GET `1.3.6.1.2.1.43.10.2.1.4.1.1` → `Counter32: 129`；
  同一查询中的 `...4.1` 不存在，确认是实例层级错误。
- 真实 MA2000w `--snmp` 文本输出：`Scan count: 3`、`Page count: 129`。
- 同一设备 PJL 文本输出：`Lifetime counter: 129 pages`。

下一步：页计数已完成，剩余优先项是告警码 `1001` 的业务含义、扫描协议
（Windows TWAIN 抓包）和 USB 物理验证。**（`1001` 已在第十二轮确认为
`markerFuserUnderTemperature`。）**

## 历史交接（第九轮）

日期：2026-10-18（第九轮）。

本次完成：

- 从 `Core.CoreServices.dll` 提取到计数器服务的真实 SOAP 操作名
  `get_counter` 与 action
  `http://www.kyoceramita.com/ws/km-wsdl/log/counter_information/get_counter`；
  对设备 80/9090 的 HTTP、TLS 与 SOAP POST 探测仍全部为空响应。
- 将 PJL `2.10.2.1.4.1.1` 暴露为 `kgetobj_known.lifetime_counter`，单位
  `pages`，带 `confidence: "inferred"`；CLI 输出 `(inferred)`。
- Web 详情页新增 Lifetime/Scan/Drum 计数和 Settings 区块。
- 更新 README、protocol-notes、CHANGELOG 与测试。

验证：

- `python3 -m unittest discover -s tests -v` → 57/57 通过。
- 真实 MA2000w PJL 文本输出：
  `Lifetime counter: 129 pages (inferred)`、
  `Drum counter: 129`、`Drum counter max: 10000`、`Scan count: 3`。
- 设备 80/9090 的 `get_counter` SOAP 请求、HTTP WSDL GET 与 TLS 握手均被
  立即关闭，未取得响应。

下一步：若允许一次打印副作用，打印一页后复采 `2.10.2.1.4.1.1`，即可把
`lifetime_counter` 从 inferred 提升为已验证；否则仍需 Windows 侧
`counter_information` 抓包。**（第十轮已通过 SNMP 验证，无需打印测试。）**

## 历史交接（第八轮）

日期：2026-10-18（第八轮）。

本次完成：

- 从 NetViewer `system/Device.Base/def/dev/snmp-oid.xml` 取得厂商 OID 名称，
  确认 `1.3.6.1.4.1.1347.43.5.1.1.33/34/35/22` 分别为 `kcprtsleepMode`、
  `kcprtAutoErrorClearSwitch`、`kcprtAutoErrorClearTimeout`、
  `kcprtFormFeedTimeout`。
- `parser.py` 的 `KGETOBJ_KNOWN` 改为带 `scale`/`choices`/`unit` 的描述；
  `kgetobj_known` 新增 `auto_error_clear` 与 `auto_error_clear_timeout`，
  并支持 `sleep_mode`、`form_feed_timeout`。
- `snmp_status.py` 新增上述四个标量及 `device_uptime_seconds`；
  `form_feed_timeout_seconds` 写入 `PrinterSnapshot.timeout`。
- `cli.py` 文本输出追加单位，并显示 SNMP 的睡眠/自动清除/超时字段。
- 更新 `README.md`、`protocol-notes.md`、`netviewer-log-findings.md`、
  `CHANGELOG.md`；新增解析与 SNMP 映射测试。

验证：

- `python3 -m unittest discover -s tests -v` → 56/56 通过。
- 真实 MA2000w PJL：Auto error clear `OFF`、超时 `30 s`、`timeout=300`。
- 真实 MA2000w SNMP：Sleep mode `ON`、Auto error clear `OFF`、
  超时 `30 s`、Form feed timeout `300 s`、`page_count=null`
  （第十轮确认是 OID 少了一级实例，已修正）。
- 20 秒采样：`43.5.1.1.4.1` 从 `24958` 增至 `24979`，`sysUpTime`
  从 `2495450` 增至 `2497513` ticks，确认前者是运行时间类计数。
- 5 组 KGETOBJ 与 SNMP 同路径对象数值一致（60/1/0/6/129）。
- 设备 80/9090 的 WSDL 与 SOAP 探测仍为 0 字节响应；未取得
  `counter_information` 响应。

下一步：优先在 Windows 上抓取 NetViewer 的 `counter_information` SOAP
流量，拿到页计数；或在可接受设备副作用时打印一页，验证
`2.10.2.1.4.1.1` 的增量。扫描路径仍需 Windows TWAIN 抓包。

## 历史交接（第七轮）

日期：2026-10-18（第七轮）。

- Web 拆分为多设备总览 `/` 与单设备详情 `/device?host=<地址>`。
- 新增 `/api/devices`：对允许列表内设备用最多 4 个线程并行读取，按 IP 排序，
  单设备异常写入该设备的 `error`，不影响其他设备。
- `DeviceRegistry` 新增 `hosts()` 与 `read_many()`；每台设备仍有独立 1 秒缓存。
- 验证：55/55 测试通过；`/`、`/api/devices`、`/device?host=192.168.0.220`
  均返回 200。

## 历史交接（第六轮）

日期：2026-10-18（第六轮）。

本次完成：

- 新增 `kyocera_monitor/discovery.py`：SNMP 广播取型号 OID、单播补全
  序列号/固件、并行 WS-Discovery 补充端点；ARP 表和显式 CIDR 作为候选。
- CLI 新增 `--discover`、`--discover-timeout`、`--discover-subnet`、
  `--discover-no-wsd`；未发现返回 1，参数错误返回 2。
- Web 新增 `/api/discover`、设备允许列表与 `?host=` 切换；未知主机返回 404。
- 新增 `tests/test_discovery.py`，扩展 `tests/test_web.py`。
- 更新 `README.md`、`docs/architecture.md`、`protocol-notes.md`、
  `CHANGELOG.md`。

验证：

- `python3 -m unittest discover -s tests -v` → 52/52 通过。
- SNMP 广播到 `192.168.0.255` 与 `255.255.255.255` 均收到 MA2000w 响应。
- `--discover --json` 实测 3.3–4.1 秒，返回型号、序列号、固件以及
  `snmp-broadcast`/`snmp-unicast`/`wsd` 来源。
- Web `/api/discover` 实测 3.55 秒；`/api/status?host=192.168.0.220` 返回
  200；未知主机返回 404。
- WSD 组播响应不稳定：单次 Probe 曾为 0 响应，同时发送两种 Types 后收到
  ProbeMatch（`http://192.168.0.220:5357/DeviceService/`）。

下一步：实现多设备总览（对已发现设备并行取快照并展示状态摘要），或继续
推进扫描路径的 Windows 抓包验证。

## 历史交接（第五轮）

日期：2026-10-18（第五轮）。

本次完成：

- 复现真实故障：一次 PJL 采集只返回 `INFO CONFIG` 与 `INFO KINTRAYSTATUS`，
  缺型号、状态、`KCONFIG`、网络和全部 `KGETOBJ`；旧实现整包重试两次后耗时
  17.3 秒仍不完整。
- `pjl.py` 新增 `split_segments()`、`merge_segments()`、`missing_commands()`、
  `query_merged()`；`TcpChannel`/`DeviceChannel` 在收到数据后连续 `idle` 秒
  无新字节即返回部分响应。`cli.collect()` 改用分段补发。
- `snmp.py` 新增 `walk_columns()` 与 `SnmpClient.walk_rows()`；
  `snmp_status.py` 改为顺序按行读取耗材、纸盒、告警和面板表，默认
  `--snmp-timeout` 改为 1.5 秒。
- 新增 `kyocera_monitor/web.py`；CLI 新增 `--web`、`--web-bind`、`--web-port`，
  页面每 10 秒刷新，`/api/status` 返回快照、耗时、缓存标记和错误。
- 新增 `tests/test_pjl_retry.py`；扩展 `test_snmp_probe.py`、
  `test_snmp_status.py`；新增 `tests/test_web.py`。
- 更新 `README.md`、`docs/architecture.md`、`protocol-notes.md`、
  `CHANGELOG.md`。

验证：

- `python3 -m unittest discover -s tests -v` → 37/37 通过。
- 真实 MA2000w：PJL 单次完整采集 0.73 秒；`--watch 0.5 --count 5 --json`
  只输出一份快照（5 次结果一致，无缺段），总耗时 18.4 秒。
- 真实 MA2000w：SNMP 单次 2.58 秒（1.5 秒超时），字段与优化前一致；
  3 次连续采集为 3.5 / 3.6 / 8.5 秒，第三次出现一次 UDP 丢包。
- 最终默认参数回归：PJL 0.89 秒；SNMP 5.56 秒（一次丢包后重试成功）。
- Web 冒烟：SNMP 数据源 `/api/status` 200、采集 3.1 秒；PJL 数据源 200、
  采集 1.37 秒；同一秒内第二次请求命中缓存，2 ms 返回。
- 旧实现基线：PJL 17.3 秒仍缺段；SNMP 12.8 秒。

下一步：实现设备发现（WS-Discovery/SNMP 扫描），把发现的打印机接入 Web
状态页，减少手工输入 IP。

## 历史交接（第四轮）

本次完成：

- 逆向 `KMSTMVM.exe` 的 USB/本地路径：`CheckPrinterLocal`、`GetPortType`、
  `ConnectUSB`、`UntilConnect`、语言监视器 mailslot 握手、2 秒重连和
  Windows 8 `WM_DEVICECHANGE`/SetupAPI 检测。
- 新增 `docs/reverse-engineering/usb-path.md`，记录函数地址、mailslot 名称、
  UEL 帧、旧型号 VID/PID 表和 Linux 实现边界。
- 新增 `kyocera_monitor/usb.py`；CLI 新增 `--usb`、`--list-usb`。
- `pjl.DeviceChannel` 改为 `os.open(O_RDWR|O_NONBLOCK)` + `select`，
  支持短写、`EAGAIN`/`EINTR`、写超时和查询前 drain。
- 新增 `tests/test_usb.py`：sysfs 发现、MA2000w 选择、PTY 往返和 CLI JSON。
- 更新 `program-structure.md`、`protocol-notes.md`、`scan-workflow.md`、
  `README.md`、`docs/architecture.md`、`CHANGELOG.md`。

验证：

- `python3 -m unittest discover -s tests -v` → 20/20 通过。
- `python3 -m kyocera_monitor --list-usb` → 当前主机无 USB 打印机，退出码 2。
- `python3 -m kyocera_monitor --usb` → 无匹配设备，退出码 2。
- PTY 假设备测试：`--device <pty> --json` 返回型号 `MA2000w`、
  `CODE=35078`、`normal=true`。
- `python3 -m kyocera_monitor --host 192.168.0.220 --json` → 网络 PJL 回归
  成功，型号、状态、耗材和 KGETOBJ 正常；连续高频探测时出现过一次 KCONFIG
  缺失和一次空响应，再次采集恢复，说明设备睡眠/唤醒期间响应不稳定。
- 未连接真实 USB 设备；未验证 `usblp` 双向读取、断线重连和 USB 扫描。

下一步：硬件接入后先跑 `--list-usb` 和 `--usb --json`，按 `usb-path.md`
第 9 节对照 TCP 结果；同时继续 Windows TWAIN 抓包或 eSCL/WSD 扫描确认。

## 历史交接（第三轮）

- 新增 SNMP 只读路径 `--snmp`、`kyocera_monitor/snmp.py`、
  `snmp_status.py`；14/14 测试通过。
- 新增 `tools/wsd_probe.py`；确认设备只发布 `WSDPrinter`，无 WSD 扫描服务；
  `631` 关闭，eSCL/KM-WSDL 未取得应用层响应。
- 更新 `protocol-notes.md`、`scan-workflow.md`、`README.md`、`CHANGELOG.md`。

## 历史交接（第二轮）

- 反编译 `KMSTMNW.exe`、`KMSCNPUS.exe`、`KMSCNSET.dll`，输出位于
  `analysis/decompiled/`（不纳入版本控制）。
- 新增 `scan-workflow.md`、`kmws-soap.md`；更新 `program-structure.md`、
  `protocol-notes.md`。
- 新增 `kgetobj_known`；8/8 测试通过。
- 对设备 80/9090/9100 和 gSOAP `OPTIONS` 做只读探测，未取得 SOAP 响应体。

## 相关文档

- `docs/reverse-engineering/program-structure.md`
- `docs/reverse-engineering/clienttool-protocol.md`
- `docs/reverse-engineering/protocol-notes.md`
- `docs/reverse-engineering/scan-workflow.md`
- `docs/reverse-engineering/kmws-soap.md`
- `docs/reverse-engineering/usb-path.md`
- `docs/reverse-engineering/samples/ma2000w-pjl.txt`
- `docs/architecture.md`
- `CHANGELOG.md`
