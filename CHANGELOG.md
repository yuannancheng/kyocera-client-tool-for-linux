# CHANGELOG

## 2026-10-18

### Changed — publication content cleanup and licensing

- 保留并接入 MIT `LICENSE`；新增 `NOTICE`、`THIRD_PARTY_NOTICES.md`、
  `CONTRIBUTING.md` 和 `docs/legal/compliance.md`。
- README 正文明确独立、非官方，与 Kyocera Corporation 无隶属、授权、赞助
  或背书关系，并加入担保与责任限制；项目标题保持原名。
- 公开研究表移除原厂 UI 文本、对话框标题、菜单描述和原始字节上下文；
  `clienttool-ui-controls.tsv` 与 `clienttool-dialogs.tsv` 只保留结构、
  文本存在性和长度，`clienttool-all-oids.tsv` 移除 `sample_context`。
- 维护包密钥、解包流程、解包工具和提取出的 XML/PNG 移出公开树，保留在
  被忽略的 `analysis/local-only/` 中；公开表只保留 request id、item id、
  数据类型和来源序号。
- 增加 `tools/check_publication.py` 与对应测试，检查许可证、声明、忽略规则、
  禁止路径、数据表列名和公开 Python 文件中的解包代码。
- 验证：公开树合规检查通过；`python3 -m unittest discover -s tests -v`
  → 140/140 通过；本地 `analysis/local-only/test_unpack_mtp.py` → 2/2 通过。

Git 历史已切换为不含旧解包工具的干净快照；
`python3 tools/check_publication.py --history` 通过。GitHub 可能在一段时间内
保留不可达的旧提交对象；如需法律意义上的彻底删除，仍需联系 GitHub 支持或
删除并重建仓库。

## 2026-10-18

### Changed — progress overview compressed and realigned

- `PROJECT_PROGRESS.md` 从 1751 行、约 97 KB 压缩到 160 行、约 9.5 KB，
  改为“目标对齐、阶段验收、当前优先级、阻塞、最近交接”结构。
- 压缩前的完整里程碑、29 轮交接和旧优先级原样归档到
  `docs/reverse-engineering/progress-history.md`，未丢失历史证据。
- 明确近期全量 OID 清点已接近收尾，应将主攻方向转回扫描、USB 物理验证
  和配置写入前置设计；OID 字段改为按需查询。

### Fixed — UTF-16 OID scan gaps and completed Wi-Fi / PAC semantics

- 修复 `clienttool_all_oids.py` 的 UTF‑16 边界断言：此前“前导点 + NUL
  终止”的 `.1.3.6.1...` 字面量会被漏扫。清单由 712 增至 827 个唯一
  OID（40 个文件、1708 次出现），补回 `42.26.1.0`、`42.27.*`、
  `42.24.3.*` 等真实设备字段。
- 新增 `oid_role=library-constant`：91 个 BouncyCastle/itextsharp/MimeKit
  等第三方库 OID 与设备对象分开统计；设备 OID 736 个，无名称 59 个。
- 新增 `tools/managed_constants.py`：只读解析 .NET 元数据常量表，
  不加载程序集；还原 `WifiSetupToolModels.dll` 的 47 个 OID 字段。
- Wi‑Fi：确认 AP 扫描表 `40.39.1.1.*`、设置表 `40.40.1.1.*`、
  `wifi_connection_state`（`3=ON/Connected`）、`check_ap_set_configuration_status`、
  `wifi_capable_1/2` 与 WPS PIN 对象；MA2000w 只读实测
  `WifiCapable1=3`、`WifiCapable2=NoSuchObject`。
- PAC/LDAP：确认 `42.26.*` 的 network user property、LDAP server/port/
  encryption/search timeout/attribute name，以及 `42.27.*` 组权限字段；
  MA2000w 上 `42.26` 子树 walk 返回 0 行，未执行写入。
- 其余：`panel_size_unit=4`（代码 CM 与 UI Millimeters 冲突保留）、
  `drum_counter=129`、`document_processor_attached`、
  `restart_device_trigger`。
- `clienttool-oid-semantics.tsv` 扩展到 62 行；59 个无名称设备 OID 已覆盖
  58 个，仅剩 `1.3.6.1.4.1.1347.42.27.6.0`。
- 测试总数 141。

### Added — Print Box / Push Scan OID semantics

- 新增 `docs/reverse-engineering/data/clienttool-oid-semantics.tsv`，
  收口 `1001.3.1.*` Print Box 7 个、`1001.4.1.*` Push Scan 6 个和
  `1001.1.1.6..10` Preset 5 个无名称 OID 的字段名、SNMP 类型、
  读写方向、枚举、证据函数和设备只读结果。
- 确认字段：interface、IPv4、IPv6、host name、address type
  （1=IPv4/2=IPv6/3=HostName）、PIN code，以及
  Print Box 结果 `ACCEPTED/NO DATA/NO FOLDER/WRONG PIN`、Push Scan
  结果 `OK/NG`，以及 COPY/SCAN/FAX/PRINT BOX 重置目标和预设安全锁。
- 新增 `tools/clienttool_oid_semantics.py`；`clienttool-all-oids.tsv`
  增加 `semantic_name` 列。48 个无名称 OID 降为 30 个，剩余分组和
  下一批优先级已写入进度文档。
- MA2000w 只读 SNMPv2c：18 个对象中 12 个可读，Print Box `.4`–`.7`、
  Push Scan `.4` 和 Preset `.8` 返回 `NoSuchObject`；未执行任何写操作。
- 记录 `KMSTMNET` 合成 PJL 文本中的 `TYPE` 标签不一致：Print Box
  IPv6 标成 `TYPE=64`、Print Box 主机名标成 `TYPE=2`，Push Scan 主机名
  标成 `TYPE=4`；字段语义应以 OID 和 SNMP 类型为准。
- 新增语义表校验与覆盖测试；SZDD 容器本轮仍未展开。
- 测试总数 134。

### Added — full ClientTool OID inventory

- 新增 `tools/clienttool_all_oids.py`：扫描 ClientTool 全部 4495 个文件、
  约 586 MB，匹配 ASCII 与 UTF‑16LE 点分 OID；生成
  `docs/reverse-engineering/data/clienttool-all-oids.tsv`。
- 结果：712 个唯一 OID、31 个命中文件、1447 次出现；611 个精确名称、
  53 个祖先名称、48 个无名称；Kyocera 604、标准 MIB 93、其他 15。
- 新增 `tools/clienttool_fax_ini.py`：解析 `FAX/KMSNMP4.INI`，生成
  `clienttool-fax-snmp-oids.tsv`（144 行、116 个 `INFO_*` 名称、
  108 个唯一 OID）。
- 主要新增来源：`KMSNMP4.INI` 108、`KMSTMNET.exe` 47、
  `WifiSetupToolModels.dll` 30、`KMUTLPRE.exe` 27、`KMUTLCFG.exe` 25。
- 边界：SZDD 压缩容器未逐个展开，抽样未见 OID；二进制整数表 OID 仍由
  147 项静态表覆盖。
- 测试总数 124。

### Added — job OID tree expansion

- 新增 `tools/clienttool_job_oids.py`，把 `JobSnmpOid.xml` 的
  `rootJob`、相对子 OID 和 `additionalOIDS` 绝对条目展开为 205 个唯一
  绝对 OID，生成 `docs/reverse-engineering/data/clienttool-job-oids.tsv`。
- 相对 OID 无父节点、非数字分量或绝对 OID 重复时失败关闭。
- MA2000w 只读验证：walk `1.3.6.1.4.1.1347.47` 返回 0 行，对照 Wi‑Fi
  子树返回 7 行；该机型没有可读的作业/日志实例。
- 观察到 147 项表之外的 `40.42.1.1.2.1 = 1075036018`，两份 XML 均未
  描述，含义未知，不做猜测。
- 测试总数 116。

### Added — merged snmp-oid.xml index

- 盘点 Client Tool 的两份 `snmp-oid.xml`：除 Wi‑Fi setup 外，补入
  `WFH/remotefax/system/Device.Base/def/dev/snmp-oid.xml`。
- `tools/clienttool_config_names.py` 改为默认合并两份 XML、校验两个
  SHA-256，并新增 `--index-output`；生成
  `docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv`
  （`oid`/`symbol`/`source`，997 行）。
- 合并后 147 项配置的覆盖仍为 127/147；20 项 OID-only 是因为两份 XML
  都没有描述，不是漏匹配。
- remotefax 独有 15 个符号（`kmFaxDeviceExist`、`kmTimeZone*`、
  `kmFirmwareDetail*`、`kcprtInputMediaSelectMode` 等）；MA2000w 对这些
  OID 全部返回 `no such object`。用户确认该机型没有传真功能，相关映射只保留
  静态证据。
- 新增 `tools/clienttool_oid_sources.py` 和
  `docs/reverse-engineering/data/clienttool-oid-mapping-sources.tsv`，
  盘点 ClientTool 中全部带 `oid` 属性的 XML：两份 `snmp-oid.xml`、
  205 元素/200 相对 OID 的 `JobSnmpOid.xml`、两份 `Support.xml`，以及不含
  OID 映射的 `snmp-discovery.xml`。
- 测试总数 112。

### Added — Wi‑Fi status field semantics

- 解析 dialog `0x00f3`（Wi‑Fi 状态页，页面过程 `FUN_00403e80`），确认页面
  读取的 `DAT_004ae518/51c/520/624/628/62c` 就是模型基址 `0x4aa890` 加上
  `0x3c88/0x3c8c/0x3c90/0x3d94/0x3d98/0x3d9c`，与 `FUN_0040e820` 的
  item 142–147 偏移一致。
- 确认 `40.42.1.1.1.1` = 连接状态（`3` Connected，`4` Not connected）、
  `.3.1` = 无线启用状态、`.4.1` = SSID、`.5.1` = 安全模式、
  `.6.1` = 信道、`.7.1` = RSSI（dBm）。安全模式枚举与 RSSI 分档字符串
  来自 `KMUTLCFGRes.dll` 的 `0x204..0x20d`。
- `clienttool-control-oids.tsv` 增加到 69 行；MA2000w 只读值
  （item 142..147）为 `3 / 2 / SSID / 4 / -71 / 4`，与页面枚举一致。
  未做任何写入。
- 补入音量对话框（dialog `0x00d1`）：Speaker/Monitor 音量 =
  item 108/109；以及 FAX notification（dialog `0x00d2`）：TX/RX report =
  item 110/111、TX/RX notification = item 112/114、
  Attach copy of TX = item 113。依据 `FUN_004144c0` 的
  “栈地址 = 模型偏移 + 8”和厂商名称，标为 `inferred`；MA2000w 无传真
  选件，这些对象返回 `no such object`，无法做真机值核对。
- `--config` 为六个 Wi‑Fi 对象新增标签、连接状态/安全模式枚举和 RSSI
  单位 `dBm`；文本输出从 `kmnetHTTPSenable` 改为
  `Wi-Fi connection state  Connected`。
- 新增 Wi‑Fi、音量与 FAX notification 控件断言；`40.42.*` 的语义不再
  标为待验证假设。

### Added — vendor names for 127 configuration objects

- 新增 `tools/clienttool_config_names.py`：用 Client Tool 自带的
  `snmp-oid.xml` 对 147 项配置 OID 做最长前缀匹配，生成
  `docs/reverse-engineering/data/clienttool-config-names.tsv` 和
  `kyocera_monitor/config_vendor_names.py`。
- 127/147 项得到厂商符号名，包括完整 `45.*` 传真组；其余 20 项保持
  OID-only，不做位置猜测。关键对照：`42.5.1.1.43.1` = `kmOffModeTimer`、
  `42.5.9.1.3.1/2/3` = `kmOffModeSettingState`、
  `1001.2.1.1.1.10.1` = `kmGrowthModelDeviceConfigCommonOrigianalQuality`
  （原文拼写）、`45.5.1.1.3.4` = `kmFaxPrivateName`、
  `45.10.2.1.1.1.4` = `kmFaxForwardEnable`。
- `--config` 的 JSON 记录新增 `vendor_name`；文本输出在缺少人工标签时
  回退到厂商名称。MA2000w 只读实测 96/147，文本已显示厂商名。
- 新增 `tests/test_clienttool_config_names.py` 并扩展配置测试，测试总数 105。

### Added — SNMP trap control mapping

- 解析 dialog `0x008e`（SNMP trap 页）的初始化函数 `FUN_0041eef0` /
  `FUN_0041d700`，把两个收件人的启用开关、community、IP 地址和每个 6 个
  事件复选框映射到模型偏移与 OID。
- 确认 `40.26.5.1.7` = `kmsvTrapEnabled`、`.4` = `kmsvTrapCommunity`、
  `.2` = `kmsvTrapIpAddress`、`.5` = `kmsvTrapEvents`；事件在模型中是
  6 个连续字段，分别对应 Add paper、Toner near empty、Add toner、
  Cover open、Paper jam、All other errors。
- Communication 页新增 `0x42d` Authentication traps →
  `1.3.6.1.2.1.11.30.0` 映射。
- `clienttool-control-oids.tsv` 扩展到 55 行；MA2000w 只读值
  `item 70 = 2`、`71/75 = 0`、`72/76 = public`、`73/77 = 0.0.0.0`、
  `74/78 = 0` 与页面语义一致。测试总数 100。

### Added — dialog-scoped control mapping

- 新增 `tools/clienttool_dialogs.py`：解析 `KMUTLCFG.exe` 的 `RT_DIALOG`
  `DLGTEMPLATE`/`DLGTEMPLATEEX` 资源，输出对话框 ID、标题、控件 ID、窗口类、
  模板文字与坐标；生成 `docs/reverse-engineering/data/clienttool-dialogs.tsv`。
- 确认控件 ID 只在所属对话框内唯一：主对话框为 `0x006b`，Panel options 为
  `0x00d0`，Communication 为 `0x008d`；此前按全局编号比较会混淆
  `0x0456`（主对话框 `Inches`）与 `0x0456`（trap 页 `Trap Recipient 2`）。
- `clienttool-control-oids.tsv` 增加 `dialog` 列并扩展到 36 个控件，覆盖主
  对话框的 Media/Paper、Original image/size、Power off when、单位选择，
  Panel options 的 Default screen/Language/Auto clear panel time，以及
  Communication 的 hostname、LAN interface、DHCP、LPD/Raw/WSD、IP/掩码/网关、
  community 和 sysContact/sysName/sysLocation。
- 用 MA2000w 的只读 SNMP 配置导出交叉核对：hostname `KMD4E4BA`、IP
  `192.168.0.220`、掩码 `255.255.255.0`、网关 `192.168.0.1`、community
  `public`、表单超时 `60`（界面 `model * 5` = `300 s`）。全部映射仍标记为
  `confidence: "inferred"`，因为尚未做写入回读。
- 新增 `tests/test_clienttool_dialogs.py`；扩展
  `tests/test_clienttool_control_oids.py`，测试总数 99。

### Added — first control-to-OID map

- 新增 `docs/reverse-engineering/data/clienttool-control-oids.tsv`：确认主
  `Device Defaults` 对话框 6 组“控件 → 模型偏移 → OID”，包括
  Auto error clear、Auto error clear timeout、Sleep time、Power off timer、
  Quiet mode 和 Form feed timeout。
- 根据 `FUN_0040c730` 的模型→栈帧复制和 `FUN_00405c10` 的参数偏移，修正
  第十七轮的推断：Sleep time 为 `43.5.1.1.23.1`，Power off timer 为
  `42.5.1.1.43.1`，Quiet mode 为 `1001.2.1.1.1.14.1`。
- 新增 `tests/test_clienttool_control_oids.py`，交叉校验控件偏移、对象偏移
  和 UI 标签资源。
- 新增 `--config --snmp` 配置后备读取：按同一 147 行对象表转换绝对 OID，
  SNMPv2c 每批 16 个只读 GET；设备 Sleeping 时实测 96/147，约 8.6 秒。
  新增 SNMP 配置解码/分批/CLI 渲染测试，测试总数 94。

### Added — configuration model offset catalog

- 新增 `tools/clienttool_config_offsets.py`：解析 `FUN_0040e820` 的
  Ghidra 伪代码，提取 147 项配置对象在 `KMUTLCFG.exe` 模型中的偏移，
  并处理共享 case 块与字符串 setter。
- 新增 `docs/reverse-engineering/data/clienttool-config-offsets.tsv`：
  147/147 项均有至少一个偏移；关键字段如 Auto error clear `0x0004`、
  Sleep time `0x0010`、Power off timer `0x0014`、Quiet mode `0x0018`、
  Form feed timeout `0x2ffc`、IPv4 `0x4550`、
  SNMP read community `0x486c`、Wi‑Fi SSID `0x3c90`。
- 确认 `FUN_0040e820` 与 `FUN_00410740` 共用同一组模型偏移，为后续
  “控件 ID → 模型偏移 → OID”映射提供中间层。
- 新增 `tests/test_clienttool_config_offsets.py`，测试总数 88。

### Added — desktop menu packaging

- 新增 `packaging/kyocera-monitor.desktop` 与 `packaging/kyocera-monitor.svg`：
  中英文菜单项、`Exec=kyocera-gui`、`TryExec` 和
  `Settings;HardwareSettings;` 分类。
- 新增 `tools/install_desktop.py`：默认安装到 `~/.local/share`，支持
  `--prefix`、`--force`、`--uninstall` 和 `--dry-run`；内容冲突默认拒绝覆盖。
- 新增 `tests/test_desktop_packaging.py`，覆盖安装字段、幂等/冲突和卸载；
  测试总数 85。`desktop-file-validate` 通过。

### Added — KMUTLCFG UI control catalog

- 新增 `tools/clienttool_ui_strings.py`：解析 `KMUTLCFGRes.dll` 的
  RT_STRING 资源和 `KMUTLCFG.exe` 的 `0x00496f20`/`0x00497048` 控件绑定表，
  输出静态标签与组合框选项。
- 新增 `docs/reverse-engineering/data/clienttool-ui-controls.tsv`：31 个
  标签/分区行和 31 个组合框选项，包括 `Power off timer`、`Auto sleep`、
  `Auto error clear`、`Quiet mode`、`Form feed timeout`、`Duplex` 等，
  以及 `0x463` 的 15 个有序时间选项。
- 基于界面模型偏移补充推断配置项标签（第十九轮修正为）：
  `43.5.1.1.23.1` = Sleep time（`1 min`）、
  `42.5.1.1.43.1` = Power off timer（`72`，对应 3 天）、
  `1001.2.1.1.1.14.1` = Quiet mode（`0`）；均保持
  `confidence: "inferred"`，等待写入回读验证。
- 新增 `tests/test_clienttool_ui_strings.py`，测试总数 82。

### Added — read-only Client Tool configuration export

- 新增 `kyocera_monitor/config.py` 与 CLI `--config`：按 `KMUTLCFG.exe`
  的 147 行对象表生成只读 `KGETOBJ` 批量查询，输出文本或 JSON；不发送
  `KSETOBJ`、SNMP SET 或维护命令。
- `--config` 支持 TCP 9100 与 USB `usblp`；MA2000w 实测 96/147 项
  `STATUS=0`，整批约 5.2–7.1 秒。其余 51 项主要为 `45.*` 传真/选件对象
  和 `43.7.1.1.3.1.2..12` 本地化语言项。
- 修正配置字符串解码：`TYPE=4` 先去尾随 NUL 再按 UTF-8 解码，
  `TYPE=64` 按“十六进制 → 8 位 ASCII 十六进制 → IPv4”两层解码。
  MA2000w 因此正确读出 `Custom 1`..`Custom 8` 和 UTF‑8 中文 Wi‑Fi SSID
  （实际网络名不写入仓库）。
- 新增 `tests/test_config.py`，覆盖对象表一致性、命令拼写、值解码、
  错误响应和 PTY 设备端到端 CLI 导出；测试总数 79。

### Added — Client Tool protocol dissection

- Client Tool 协议拆解文档
  `docs/reverse-engineering/clienttool-protocol.md`，范围限定在
  `Kyocera/ClientTool`，不依赖 NetViewer。
- 可复现对象表提取工具 `tools/clienttool_oids.py`，从
  `KMUTLCFG.exe` 提取 147 行配置 OID 表，从 `KMUTLPRE.exe` 提取 56 行
  预设表（36 行 OID 模板 + 20 行本地字段名）；生成数据位于
  `docs/reverse-engineering/data/`。
- 确认 Client Tool 网络路径使用内嵌 Net-SNMP，`KMSTMNET.exe` 将 SNMP
  结果合成为 PJL 文本后交给 `KMSTMVM.exe`；未发现 9100、HTTP 或 SOAP
  客户端。
- 还原 PJL 值编码：`TYPE=4` 为十六进制字符串，`TYPE=64` 为十六进制
  IPv4；确认 `1.<path>` 与 `#<absolute-oid>` 两种对象写法。
- 只读实测私有对象：`1001.1.1.6/7/8/9.0` 预设类别、`1001.1.2.1.1.*`
  扫描预设、`1001.3.1.*` Print Box、`1001.4.1.*` Push Scan 均能在
  MA2000w 上读取。
- 解析 `KDS337110.dat` 的 `0x40100` 文件布局；确认其主要存机型图形/布局
  和数值块，不提供 147 项配置的名称映射。
- 拆解 `KMUTLMNT.exe` 维护协议：KPSL 帧经 TCP 9100 RAW 或 USB 发送，
  20 字节帧头、记录表、校验和及固定种子滚动 XOR；
  还原 20 项参数类型表和维护包 XML 节点。
- 离线提取维护包请求目录，得到 39 条 request 记录，并生成只含 request id、
  item id、数据类型和来源序号的
  `docs/reverse-engineering/data/clienttool-maintenance-requests.tsv`。
  维护包密钥、解包流程和提取出的 XML/PNG 保留为本地研究材料，不进入公开仓库。
- 提取 `KMUTLMNT.exe` 的 177 项符号 request id → 数值映射，新增
  `tools/clienttool_request_ids.py` 与
  `docs/reverse-engineering/data/clienttool-maintenance-request-ids.tsv`。

### Added

- Linux 状态监视器 `kyocera_monitor`，复刻 `KMSTMVM.exe` 的 PJL 查询序列。
- TCP 9100 与 USB `usblp` 字符设备传输。
- 型号、序列号、固件、状态码、耗材、覆盖率、网络、纸盒和 KGETOBJ 解析。
- `--json`、`--watch`、`--expect-model` 与明确退出码。
- Ghidra headless 反编译导出脚本，以及 PJL/SNMP 探测工具。
- MA2000w 程序结构、协议记录和脱敏响应样本。
- 扫描与 Push Scan 工作流记录：`docs/reverse-engineering/scan-workflow.md`。
- KM-WSDL/SOAP 调查记录：`docs/reverse-engineering/kmws-soap.md`。
- 只读 SNMP 状态路径：`kyocera_monitor/snmp.py`、`snmp_status.py` 与 CLI
  `--snmp`；支持型号、序列号、固件、网络、耗材、纸盒、面板、告警和扫描计数。
- WS-Discovery 只读探测工具 `tools/wsd_probe.py`。
- USB 静态逆向记录 `docs/reverse-engineering/usb-path.md`：还原 Windows
  Client Tool 的本地端口判定、语言监视器 mailslot 握手、2 秒重连、Windows 8
  断连检测和旧型号 VID/PID 表。
- Linux USB 支持：`kyocera_monitor/usb.py`、CLI `--usb`/`--list-usb`；
  `DeviceChannel` 改为非阻塞 `os.open` + `select`，处理短写、残留输入和超时；
  物理 USB 设备尚未接入验证。
- PJL 分段补发：按 `@PJL` 回显切分响应，只重发缺失命令并按原顺序合并；
  接收端在数据停止到达 `--idle` 秒后立即返回部分响应。
- SNMP 行式表读取：`SnmpClient.walk_rows()` 先用单列 `GETNEXT` 枚举行实例，
  再用一次多 OID `GET` 取整行所需列；新增 `walk_columns()` 作为多列 walk 原语。
- 只读本地 Web 状态页 `kyocera_monitor/web.py`：CLI `--web`/`--web-bind`/
  `--web-port`，提供 `/`、`/api/status`、`/healthz`，带 1 秒快照缓存和串行采集。
- 设备发现 `kyocera_monitor/discovery.py`：SNMP 广播 + 单播补全 + 并行
  WS-Discovery；CLI `--discover`、`--discover-timeout`、`--discover-subnet`、
  `--discover-no-wsd`；Web `/api/discover` 与发现结果切换。
- 多设备总览：Web `/` 展示所有已知设备的型号、状态、耗材和告警摘要，
  `/device?host=<地址>` 展示单设备详情；`/api/devices` 用最多 4 个线程并行
  读取，单设备错误不会影响其他设备。
- `kgetobj_known` 新增 `auto_error_clear`（ON/OFF）与
  `auto_error_clear_timeout`（秒，原始值 ×5）；解析器同时支持
  `sleep_mode` 与 `form_feed_timeout`。
- SNMP 输出新增 `sleep_mode`、`auto_error_clear`、
  `auto_error_clear_timeout_seconds`、`form_feed_timeout_seconds` 和
  `device_uptime_seconds`；`form_feed_timeout_seconds` 同时写入
  `PrinterSnapshot.timeout`。
- `kgetobj_known` 新增 `lifetime_counter`（`2.10.2.1.4.1.1`，单位
  `pages`），标记 `confidence: "verified"`。
- Web 单设备详情页新增 Lifetime/Scan/Drum 计数和 Settings（睡眠模式、
  自动错误清除、表单超时）展示。
- 原生 GUI：`kyocera_monitor/gui.py` 用 GTK3/WebKit2 窗口承载同一个只读
  Web 仪表盘，新增 `--gui`、`./kyocera-gui` 和 `pyproject.toml` 的
  `kyocera-gui` 入口；本地服务使用随机端口，关闭窗口即退出。
- Web/GUI 支持无默认设备启动：总览页可直接手动输入打印机 IP，
  `POST /api/devices` 校验 IPv4/主机名后加入允许列表；GTK/WebKit 缺失时
  `--gui` 明确报错并建议使用 `--web`。
- Web 总览与详情页改为中文界面；CLI 新增 `--web-open`，启动后自动在默认
  浏览器打开。

### Verified

- MA2000w（`192.168.0.220`）通过 TCP 9100 返回型号 `"MA2000w"`、
  `CODE=35078`、`ONLINE=TRUE`、碳粉 80%。
- 8 个单元测试通过（解析、PJL 帧、响应完成度、KGETOBJ 结构化字段）。
- Push Scan 静态链路：`KMSTMNW.exe` → `KMSCNPUS.EXE <presetNo>` →
  `KMQSEnablePreset` → `KMSCNFOL.EXE /D` → `KMQSDisablePreset`。
- Quick Scan 预设写入 `QUICKSCN.ini` 的 `[Globals] Preset`；TWAIN 数据源为
  `Kyocera TWAIN Driver`。
- 设备 80 端口运行 gSOAP 2.7；`OPTIONS` 返回 SOAP 405 Fault，SOAP POST
  在本机未获得应用层响应。
- KGETOBJ 的 Drum counter、Drum counter max、Scan count 已由程序日志标签确认。
- JSON 输出新增 `kgetobj_known`，结构化上述三个字段；原始 `kgetobj` 保留。
- SNMPv1 在 MA2000w 上完成整表 walk；耗材 `560/700 = 80%`、面板
  `Sleeping...`、Scan count `3` 与 PJL 结果一致。
- WSD 元数据确认设备只托管 `WSDPrinter`；`scan:ScannerServiceType` 连续
  3 次无响应。端口 `80/515/5357/9090/9100` 开放，`631` 关闭。
- 单元测试从 8 个增加到 14 个，新增 SNMP walk、v1 容错 GET 与
  SNMP 到 `PrinterSnapshot` 的字段映射。
- USB PTY 假设备往返和 `--device --json` 全链路测试通过；测试总数达到 20。
- 网络 PJL 回归通过，USB 改动未影响 TCP 9100 路径。
- MA2000w 上复现了 PJL 尾部丢段：旧实现缺 14 段、整包重试两次后耗时 17.3 秒
  仍不完整；新实现单次完整采集 0.73 秒，0.5 秒间隔连续 5 次轮询输出未出现
  缺段快照。
- SNMP 单次采集从旧实现 12.8 秒降到 2.6–3.6 秒；3 次连续采集中一次因 UDP
  丢包约为 8.5 秒。行式采集每轮固定 14 个请求。
- Web 状态页在真实 MA2000w 上分别用 SNMP 与 PJL 两种数据源完成冒烟：
  `/api/status` 返回 200，型号/状态/耗材正确；第二次请求命中缓存，耗时 2 ms。
- SNMP 广播到 `192.168.0.255` 和 `255.255.255.255` 均收到 MA2000w 的
  `MA2000w` 型号响应；`--discover --json` 实测 3.3–4.1 秒，返回序列号、
  固件及 `snmp-broadcast`/`snmp-unicast`/`wsd` 来源。
- Web `/api/discover` 实测 3.55 秒；发现的主机可用 `?host=` 切换，未知主机
  返回 404。
- 多设备总览冒烟：`/` 与 `/device?host=192.168.0.220` 返回 200，
  `/api/devices` 返回 MA2000w 快照，单设备错误隔离由单元测试覆盖。
- 用 NetViewer `def/dev/snmp-oid.xml` 的厂商 OID 名称确认
  `43.5.1.1.33/34/35/22` 分别为 Sleep mode、Auto error clear、
  Auto error clear timeout、Form feed timeout；其中 Form feed timeout
  的 SNMP `60 × 5 = 300 s` 与 PJL `INQUIRE TIMEOUT=300` 交叉一致。
- `KGETOBJ` 对象路径与 Kyocera 企业 OID 的前缀映射已用五组对象交叉核对：
  `1.3.6.1.4.1.1347.` + 对象路径，数值完全一致。
- 20 秒间隔采样确认 `43.5.1.1.4.1` 与 `sysUpTime` 同步增长（`24958`→
  `24979`），是设备运行时间类计数，不是页计数。
- 静态确认 NetViewer 的 `DEV_PAGECOUNT`（5036）来自 SOAP
  `counter_information` 服务；当时用错误的实例层级查询
  `prtMarkerLifeCount`，得到 `NoSuchInstance`，后续已在 `Fixed` 中修正。
- 真实设备验证：PJL 与 SNMP 均返回 Auto error clear `OFF`、超时 `30 s`、
  Form feed timeout `300 s`；SNMP 返回 Sleep mode `ON`。
- 真实设备 PJL 输出新增 `Lifetime counter: 129 pages`；SNMP
  `prtMarkerLifeCount` 也返回 `129`，两个独立协议共同确认该字段。
- 确认 `KGETOBJ` 的双根映射：`1.<path>` → `1.3.6.1.4.1.1347.<path>`，
  `2.<path>` → `1.3.6.1.2.1.43.<path>`；`2.5.1.1.10.1` 与
  `prtConsoleLocalization` 同值 `1`，`1.42.5.1.1.16.1` 对应
  `kmPanelFirmwareVersion`。
- 确认 SNMP 告警 `1001` 为标准 `markerFuserUnderTemperature`；设备睡眠时
  severity 为 `5`（`warningBinaryChangeEvent`）、training 为 `3`
  （`untrained`）、group 为 `10`（`marker`），厂商显示为
  `Sleeping...` / `35078`。
- CLI/Web 告警输出新增 severity、training level、group 和 code 的标准枚举名。
- 静态还原 NetViewer `Core.CoreServices.dll` 的扫描 SOAP 数据契约：
  `open_session`、`start_scan`、`retrieve_image`、`close_session` 的请求字段，
  以及扫描图像、原稿、输出三个配置结构的字段清单。
- 确认扫描 SOAP 契约没有随附调用方：没有 `ScanOperationService` 代理类，
  其他 .NET 程序集也不引用这些类型；扫描实际路径仍以 TWAIN 证据为准。

### Changed

- 修正 SOAP 分析目标：SOAP 客户端位于 NetViewer .NET 程序集，不在
  `ClientTool.dll`/`KMSTMNW.exe`。
- 单元测试从 6 个增加到 8 个，覆盖 KGETOBJ 结构化字段和不支持状态过滤。
- `tools/snmp_probe.py` 改为调用 `kyocera_monitor.snmp` 的共享实现，默认
  SNMP 版本改为 `1`；walk 在离开请求子树时停止。
- SNMP 采集默认使用 SNMPv1 GETNEXT；复核确认 MA2000w 的 v1/v2c GETNEXT
  均可用，v2c GETBULK 无响应。
- 扫描协议调查更新：不再把 NetViewer 的 `ScanOperation` 类型视为可用扫描入口；
  下一步转为 TWAIN 驱动 DLL 或 Windows TWAIN 抓包。
- `KMSTMVM.exe` 的 USB 路径确认经打印后台/语言监视器转发，不直接打开 USB
  设备；Linux 使用 `usblp` 发送同一 UEL PJL 帧，物理一致性仍待硬件验证。
- `collect()` 改用 `query_merged()`；旧 `query()` 仍保留给探测脚本和单元测试。
- SNMP 表读取从“并行 walk 整棵子树”改为“顺序按行读取所需列”，默认
  `--snmp-timeout` 从 3.0 秒降为 1.5 秒。
- 单元测试从 20 个增加到 55 个，新增分段补发、合并顺序、SNMP 多列 walk、
  行实例枚举、v1 列剔除、ARP/子网候选、WSD 解析与发现结果合并，以及 Web
  缓存、设备允许列表、多设备并发读取、JSON 载荷和 CLI 参数组合测试。
- 单元测试从 55 个增加到 58 个，新增 KGETOBJ 设置字段解析、Lifetime
  counter、SNMP 设置字段映射、页计数完整实例 OID 和详情页计数/设置元素
  检查；CLI 文本输出为带单位的字段追加单位。
- 单元测试从 58 个增加到 67 个，新增无默认设备启动、手动添加主机校验、
  GUI 参数与依赖缺失回退，以及快照时间戳使用墙钟而非单调时钟的回归测试。

### Fixed

- 修正 SNMP 告警字段映射：severity 应读取 `43.18.1.1.2`，旧实现读取了
  `43.18.1.1.3`（training level），因此把 `untrained(3)` 误显示为
  severity `3`。现在同时输出 severity、training level、group 和 code。
- 修正 SNMP 页计数 OID：`prtMarkerLifeCount` 的完整实例是
  `1.3.6.1.2.1.43.10.2.1.4.1.1`，旧实现使用 `...4.1`，少了一级实例，
  导致设备返回 `NoSuchInstance`、`page_count` 被误判为空。修正后真实
  MA2000w 返回 `129`。
- 修正 Web 快照时间戳：缓存过期判断继续使用单调时钟，`collected_at`
  改用墙钟，避免页面显示 `1970-01-01`。浏览器提前断开连接时不再输出
  `BrokenPipeError` traceback。
