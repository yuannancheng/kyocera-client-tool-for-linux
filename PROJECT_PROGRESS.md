# PROJECT PROGRESS

> 最后更新：2026-10-18。详细轮次记录已归档到
> [`docs/reverse-engineering/progress-history.md`](docs/reverse-engineering/progress-history.md)；
> 本文件只保留当前状态、优先级、阻塞和可执行的下一步。

## 项目目标与当前状态

本项目研究京瓷 MA2000w 多功能打印机及 Windows 版 KYOCERA Client Tool 的
功能和通信行为，并在 Linux 上实现可移植、可测试的替代工具；长期目标不限于
MA2000w。

当前结论：**总体方向仍在计划内，但近三轮的执行重心有偏移。** 只读监控、
设备发现、本地 Web/GUI 和配置只读导出已经可用；扫描、配置写入和 USB 物理
验证尚未闭环。第 27–29 轮把主要精力放在全量 OID 清点和剩余字段命名上，
覆盖率已接近收尾，但产品能力没有同步增加，继续投入的边际收益很低。

当前产品边界：

- 已验证：TCP 9100 PJL、SNMPv1/v2c、设备发现、多设备 Web 总览、原生 GUI、
  147 项配置对象只读导出（MA2000w 实测 96/147 返回 `STATUS=0`）。
- 离线实现：USB `usblp` 路径、PJL 分段补发、PTY 假设备往返。
- 未闭环：物理 USB 验证、Linux 扫描、配置写入、其他机型的兼容性验证。

## 计划对齐检查

| 检查项 | 事实 | 判断 |
| --- | --- | --- |
| 研究范围 | 仍限定在 `Kyocera/ClientTool` 及 Linux 实现所需协议 | 未偏移 |
| 产品目标 | 仍以复刻设备侧可验证功能为目标，没有转向通用 SNMP 工具 | 未偏移 |
| 用户可见能力 | 近三轮新增的是 OID 清单和字段语义，扫描/写入仍未实现 | 有偏移 |
| 阶段重点 | 736 个设备 OID 中仅剩 `42.27.6.0` 无语义，收尾成本高于收益 | 应冻结清点 |
| 进度记录 | 原文件 1751 行、约 97 KB，混入 29 轮详细交接和重复里程碑 | 已压缩归档 |

判断依据不是工作量多少，而是这些工作是否直接解除当前产品阻塞。OID 命名对
配置写入和扫描仍有支撑价值，但应改为“遇到具体字段再查”，不再作为主攻方向。

## 当前阶段

`IN_PROGRESS`：阶段 D，Linux 实现。

| 里程碑 | 状态 | 验收依据 |
| --- | --- | --- |
| 只读状态监控（PJL/SNMP） | `DONE` | MA2000w 实测；型号、状态、耗材、纸盒、计数可读 |
| 设备发现与 Web/GUI | `DONE` | `/api/discover`、多设备总览、GTK3/WebKit2 窗口实测 |
| Client Tool 配置只读导出 | `DONE` | 147 项对象表；MA2000w 96/147；PJL 与 SNMP 后备路径 |
| 维护协议静态拆解 | `DONE` | KPSL 帧、维护包、request id 已落表；动态字段未验证 |
| USB 物理验证 | `BLOCKED` | 物理连接未确认；仅完成离线 PTY 测试 |
| Linux 扫描路径 | `BLOCKED` | WSD 无扫描服务，631 关闭，eSCL/KM-WSDL 无响应；TWAIN 未取得 |
| 配置写入与回滚 | `TODO` | 尚无只读基线、备份、写入、回读和恢复流程 |

## 已验证能力

- **PJL 状态路径**：TCP 9100 使用 Client Tool 的 16 条查询序列；分段识别
  缺失命令并只补缺失段，修复过尾部丢段。MA2000w 单次完整采集约 0.73 秒。
- **SNMP 状态路径**：顺序读取 14 个请求，输出型号、序列号、固件、网络、
  耗材、纸盒、告警、面板和计数；MA2000w 单次约 2.6–3.6 秒，睡眠时可能丢包。
- **计数交叉验证**：PJL `2.10.2.1.4.1.1` 与 SNMP
  `1.3.6.1.2.1.43.10.2.1.4.1.1` 均为 `129`，`lifetime_counter` 已验证。
- **设备发现**：SNMP 广播/单播、WS-Discovery、ARP 和显式 CIDR；WSD 只发布
  打印服务，未发现扫描服务。
- **本地界面**：`--web` 提供只读总览和详情页；`--gui` 使用 GTK3/WebKit2
  承载同一页面；默认只监听 `127.0.0.1`。
- **USB 静态与离线实现**：原厂 USB 经打印后台和语言监视器转发 UEL PJL；
  Linux 使用 `/dev/usb/lp*`、非阻塞 I/O 和 sysfs VID/PID 选择设备。真实 USB
  帧一致性和断线重连仍未验证。
- **Client Tool 协议**：确认网络监视/配置走内嵌 Net-SNMP，`KMSTMNET.exe`
  将结果合成为 PJL 文本；还原 147 项配置对象、56 行预设表、
  `KGETOBJ` 双根映射及 `1.<path>`/`#<oid>` 写法。
- **维护协议**：KPSL 帧头、12 字节控制头、滚动 XOR 和 20 项参数类型已静态
  还原；维护包已离线提取出 39 条 request 和 177 个 request id 映射；
  公开仓库只保留 request id、item id 和数据类型，不包含密钥、解包工具或
  提取出的 XML/PNG。动态帧字段仍待真实设备确认。
- **OID 语义**：827 个唯一文本 OID，其中 91 个为第三方库常量；736 个设备
  OID 中 735 个已有名称或语义，仅 `1.3.6.1.4.1.1347.42.27.6.0` 未知。

## 当前优先级

1. **P0：打通 Linux 扫描路径。** 取得 `Ns1815TWGN.DLL` 做静态分析，或在
   Windows 主机抓取 TWAIN 流量；没有调用方和真实请求前不实现扫描触发。
2. **P1：USB 硬件验证。** 接入设备后跑 `--list-usb`、`--usb --json`，与 TCP
   结果逐项对照；同时验证断线重连和睡眠唤醒。
3. **P2：配置写入前置设计。** 先建立只读基线、备份、最小写入、回读和回滚；
   没有回滚方案前不发送 `KSETOBJ` 或 `snmpset`。
4. **P3：按需补字段语义。** OID 全量清点冻结；只有阻塞扫描或写入时才查新字段。

## 待验证假设

- USB 原始 UEL 帧是否与 TCP 9100 完全一致；语言监视器是否增加额外封装。
- 原厂程序在 USB 与网络连接下是否使用相同的 PJL 查询序列。
- `43.5.1.1.33/34/35` 的厂商名称虽已匹配，仍需写入回读或原厂界面确认。
- `1.43.5.1.1.29.1` 是否为 `kcprtAssetNumber`；设备返回空字符串，旧标签证据不足。
- `CODE2=30014/30001` 组合分支的准确触发条件。
- NetViewer `.NET` 的 `ScanOperation` 是否存在反射或动态加载调用；当前静态引用
  只指向 `Core.CoreServices.dll` 自身。
- MA2000w 的 80/9090 gSOAP 是访问控制、服务未启用，还是认证前置条件未满足。

## 当前阻塞

- 当前主机没有 Windows 运行环境，无法对原厂程序做动态抓包。
- USB 物理验证受硬件接入限制；历史检查未发现 `0482:0d51`，本次 `lsusb`
  因执行环境无法初始化 libusb（`-99`）而未能复核，接入时需重新确认。
- 本机样本缺少 TWAIN 驱动 `Ns1815TWGN.DLL`；扫描入口无法继续静态追踪。
- 设备只发布 WSD 打印服务，`631/tcp` 关闭，eSCL/KM-WSDL 无应用层响应。
- SNMPv2c `GET`/`GETNEXT` 正常，`GETBULK` 无响应；实现继续默认 SNMPv1。
- 设备睡眠时 PJL 9100 可能连续无响应，配置读取应使用 `--config --snmp`。
- `Kyocera/NetViewer/KNV/log/kmnv.log` 含序列号和加密凭据，只能本地使用，
  不得提交到仓库。

## 公开内容整理（2026-10-18）

状态：`IN_PROGRESS`。目标是让公开树只保留独立实现、协议事实摘要和脱敏数据。

已完成：

- 接入远程 MIT `LICENSE`；新增 `NOTICE`、`THIRD_PARTY_NOTICES.md`、
  `CONTRIBUTING.md` 和 `docs/legal/compliance.md`。
- README 正文说明独立、非官方，加入非关联、按现状提供、不作担保和责任
  限制声明；项目标题和仓库名保持 `kyocera-client-tool-for-linux`。
- 移除公开表中的原厂 UI 文本、对话框标题、菜单描述和原始字节上下文；
  UI/对话框表只保留结构、类名、几何位置、文本存在性和长度。
- 维护包密钥、解包流程、解包工具和提取物移入被忽略的
  `analysis/local-only/`；公开维护表只保留 request id、item id、数据类型和
  来源序号。
- 新增 `tools/check_publication.py`，检查许可证/声明、忽略规则、禁止路径、
  数据表列名和公开 Python 文件中的解包代码。
- 验证：公开树检查通过；`python3 -m unittest discover -s tests -v`
  → 140/140 通过；本地解包回归测试 2/2 通过。

不影响项目推进的措施：运行时、PJL/SNMP、配置读取、Web/GUI 和测试均未改变；
原始文本导出和解包能力保留在 `analysis/local-only/`，包括
`clienttool_all_oids_raw.py`、`clienttool_ui_strings_raw.py`、
`clienttool_dialogs_raw.py` 和 `unpack_mtp.py`。

历史状态：

- 当前分支已切换为不含旧解包工具的干净快照；
  `python3 tools/check_publication.py --history` 通过。
- GitHub 可能仍保留不可达的旧提交对象。若需要法律意义上的彻底删除，应由
  仓库所有者联系 GitHub 支持，或删除并重建仓库。
- 干净归档和 Git bundle 位于 `/tmp/kyocera-client-tool-for-linux-20261018.tar.gz`
  和 `/tmp/kyocera-client-tool-for-linux-20261018.bundle`。

## 最近一次工作交接（第二十九轮）

日期：2026-10-18。范围：修复 UTF‑16 OID 扫描边界，解析托管元数据常量，
补齐 Wi‑Fi/PAC/LDAP/面板单位/鼓计数语义，并对 MA2000w 做只读核对。
没有执行 SNMP SET、`KSETOBJ`、重启、组权限或 Wi‑Fi 配置写入。

完成与证据：

- `tools/clienttool_all_oids.py` 修复“前导点 + NUL 终止”的 UTF‑16 漏扫，
  OID 从 712 增至 827（40 个文件、1708 次出现）。
- 新增 `tools/managed_constants.py`，只读解析 PE/CLI 常量表和
  `#Strings`/`#Blob` 堆，还原 `WifiSetupToolModels.dll` 的 47 个 OID 字段。
- 确认 Wi‑Fi AP 扫描表 `40.39.1.1.*`、设置表 `40.40.1.1.*`、
  `wifi_connection_state=3`、`wifi_capable_1/2` 和 WPS PIN 对象。
- 确认 PAC/LDAP `42.26.*`、组权限 `42.27.*`、面板单位、鼓计数、
  DP/ADF 连接标志和重启触发对象；MA2000w 的 `42.26` walk 返回 0 行。
- `clienttool-oid-semantics.tsv` 扩展到 62 行；设备 OID 命名覆盖 735/736。
- 验证：`python3 -m unittest discover -s tests -v` → 140/140 通过
  （合规改造后；移除了 2 个本地解包公开测试，新增 1 个发布检查测试）。
- 真实 MA2000w 只读值：`WifiCapable1=3`、`WifiCapable2=NoSuchObject`、
  `40.42.1.1.1.1=3`、`panel_size_unit=4`、`drum_counter=129`；未写入。

遗留问题：

- `42.27.6.0` 只出现在一个未对齐的 UTF‑16 数据块中，没有可定位的 `ldstr`
  引用；按当前优先级暂不继续追查。
- 面板单位存在“代码映射 CM / UI 标签 Millimeters”的冲突，需原厂界面或
  另一机型交叉确认。
- Wi‑Fi 枚举、WPS/PAC 组权限和标准 MIB 部分列因设备睡眠未取得，不能据此
  推断对象不存在。

本次文档整理：把原有里程碑和 29 轮交接完整移入
`docs/reverse-engineering/progress-history.md`，本文件只保留当前结论。

## 下一步

优先执行：在现有 Windows 安装包或 Windows 主机中取得
`Ns1815TWGN.DLL`，按 `docs/reverse-engineering/scan-workflow.md` 继续追踪
TWAIN 初始化、传输方式和图像回收；若拿不到 DLL，则改用 Windows 侧抓包。
扫描路径取得真实请求前，不新增猜测性的扫描实现。

## 相关文档

- `docs/reverse-engineering/progress-history.md`：压缩前的完整进度与轮次记录
- `docs/reverse-engineering/program-structure.md`
- `docs/reverse-engineering/clienttool-protocol.md`
- `docs/reverse-engineering/protocol-notes.md`
- `docs/reverse-engineering/scan-workflow.md`
- `docs/reverse-engineering/kmws-soap.md`
- `docs/reverse-engineering/usb-path.md`
- `docs/reverse-engineering/netviewer-log-findings.md`
- `docs/reverse-engineering/samples/ma2000w-pjl.txt`
- `docs/architecture.md`
- `CHANGELOG.md`
