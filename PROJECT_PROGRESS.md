# PROJECT PROGRESS

> 最后更新：2026-10-29。详细轮次记录已归档到
> [`docs/reverse-engineering/progress-history.md`](docs/reverse-engineering/progress-history.md)；
> 本文件只保留当前状态、优先级、阻塞和可执行的下一步。

## 项目目标与当前状态

本项目研究京瓷 MA2000w 多功能打印机及 Windows 版 KYOCERA Client Tool 的
功能和通信行为，并在 Linux 上实现可移植、可测试的替代工具；长期目标不限于
MA2000w。

当前结论：**扫描路径已从“材料缺失”推进到“客户端协议明确、等待真机响应”。**
只读监控、设备发现、本地 Web/GUI 和配置只读导出已经可用。2026-10-29
从京瓷官方安装包补齐网络 TWAIN 驱动，确认其通过 KM-WSDL/gSOAP 扫描，并
新增只读服务信息探针；设备离线，9090/9091 响应、SOAP 版本和认证仍未实测。

当前产品边界：

- 已验证：TCP 9100 PJL、SNMPv1/v2c、设备发现、多设备 Web 总览、原生 GUI、
  147 项配置对象只读导出（MA2000w 实测 96/147 返回 `STATUS=0`）。
- 静态已验证：网络 TWAIN 使用 `Ns1815TWGN -> KMNETSCN3 -> KMSCNAPI`；
  KM-WSDL 使用 HTTP 9090 或 HTTPS 9091，扫描 action 已还原。
- 已提供但未真机验证：只读 `get_service_information` KM-WSDL 探针。
- 离线实现：USB `usblp` 路径、PJL 分段补发、PTY 假设备往返。
- 未闭环：KM-WSDL 真机响应与 Linux 取图、物理 USB 验证、配置写入、
  其他机型的兼容性验证。

## 计划对齐检查

| 检查项 | 事实 | 判断 |
| --- | --- | --- |
| 研究范围 | 仍限定在 `Kyocera/ClientTool` 及 Linux 实现所需协议 | 未偏移 |
| 产品目标 | 仍以复刻设备侧可验证功能为目标，没有转向通用 SNMP 工具 | 未偏移 |
| 用户可见能力 | 扫描尚未闭环，但已新增可执行的只读 KM-WSDL 探针 | 持续对齐 |
| 阶段重点 | 已取得原厂网络 TWAIN 驱动并还原客户端协议 | 转入真机验证 |
| 进度记录 | 详细交接继续归档，总览保留当前事实和阻塞 | 保持 |

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
| 网络 TWAIN/KM-WSDL 客户端静态还原 | `DONE` | 官方 2.1.4412 安装包；DLL 哈希；9090/9091 路由与 8 个 action |
| KM-WSDL 只读服务信息探针 | `DONE` | 生成请求、Fault/result 处理、JSON 输出；10 个专项测试 |
| KM-WSDL 只读能力探针 | `DONE` | 空 capability 请求；三类能力树、缺项/Fault/非法 XML 处理；专项测试 |
| Linux 扫描端到端 | `IN_PROGRESS` | 客户端已实现；等待设备在线验证响应、能力、会话和取图 |
| USB 物理验证 | `BLOCKED` | 物理连接未确认；仅完成离线 PTY 测试 |
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
- **网络 TWAIN**：官方 `Kyocera TWAIN Driver GX 2.1.4412` 已取得并校验；
  `KMSCNAPI.dll` 使用 gSOAP 2.7 调用 KM-WSDL。明文 HTTP 路径为 9090，
  HTTPS 路径为 9091，scan operation 路径及 action 已落表。
- **OID 语义**：827 个唯一文本 OID，其中 91 个为第三方库常量；736 个设备
  OID 中 735 个已有名称或语义，仅 `1.3.6.1.4.1.1347.42.27.6.0` 未知。

## 当前优先级

1. **P0：完成 KM-WSDL 真机验证。** 设备在线时先运行只读
   `tools/kmscn_probe.py`，依次核对服务信息和 capability 的 HTTP 9090、
   HTTPS 9091、SOAP 1.1/1.2；保存脱敏响应后再实现
   open/start/retrieve/close。
2. **P1：USB 硬件验证。** 接入设备后跑 `--list-usb`、`--usb --json`，与 TCP
   结果逐项对照；同时验证断线重连和睡眠唤醒。
3. **P2：配置写入前置设计。** 先建立只读基线、备份、最小写入、回读和回滚；
   没有回滚方案前不发送 `KSETOBJ` 或 `snmpset`。
4. **P3：按需补字段语义。** OID 全量清点冻结；只有阻塞扫描或写入时才查新字段。

## 待验证假设

- KM-WSDL 客户端默认使用 SOAP 1.1；该结论来自 gSOAP 初始化字段和响应版本
  分支，但尚无设备接受或拒绝的实测响应。
- `get_service_informationRequest` 为空元素、HTTPS 证书处理方式以及服务信息
  响应 XML 结构，需要设备在线时由探针确认。
- `get_capabilityRequest` 为空元素，响应应含 `result` 与三类能力项；这些
  结构来自官方驱动的序列化函数，能力项内部字段仍需真机响应确认。
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
- 2026-10-29 复核时 `192.168.0.220` 不在线，无法验证 KM-WSDL 9090/9091、
  SOAP 版本、认证、能力响应和实际取图。
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

## 最近一次工作交接（第三十一轮）

日期：2026-10-29。范围：补齐网络 TWAIN 驱动，静态还原 KM-WSDL 扫描客户端，
新增只读服务信息和能力探针，并以通用树形解析保留尚不确定的能力字段结构。
没有执行扫描会话、扫描、取图、SNMP SET、`KSETOBJ`、重启或配置写入。

完成与证据：

- 从京瓷官方站点取得 TWAIN Driver 2.1.4412：
  `92912ad89d780bfe39fa4b82d9d469ea9eef4c5b74de7fb97f693103451e801e`。
- 从 PE 资源无损取出 16,235,106 字节内嵌 ZIP，完整性测试通过；
  `Ns1815TWGN.dll` SHA-256 为
  `b277ff4b1bf31f0cc39b63fc8c5fbdd4770a44261cadaddb102f4d9517cfae09`。
- 确认调用链 `Ns1815TWGN -> KMNETSCN3 -> KMSCNAPI`；`KMSCNAPI.dll`
  导入 `WININET.dll`、静态链接 gSOAP 2.7 与 OpenSSL。
- 确认 HTTP 9090、HTTPS 9091、三个 KM-WSDL 服务路径、八个扫描 action，
  以及 service info → capability → open → start → retrieve → close 顺序。
- 新增 `kyocera_monitor/kmscn.py`、`tools/kmscn_probe.py`、
  `tools/ghidra_scripts/InspectScanApi.java` 和 10 个专项测试；探针只发送
  `get_service_information`。
- 从 `KMSCNAPI.dll` 的 gSOAP 序列化函数确认 `get_capabilityRequest` 为空，
  响应根包含 `result`、`scan_image_configuration_capability`、
  `original_configuration_capability` 和
  `output_image_configuration_capability`。
- `--capability` 新增为只读操作；响应保留 XML 元素名、属性和子节点树，
  不猜测数组语义。缺少预期项、Fault、非零 result、非 2xx 或非法 XML 均失败。
- 解析器新增 DTD/实体声明拒绝和 2 MiB 响应上限测试；新增 6 个 capability
  请求、响应和网络边界测试。
- 验证：`python3 -m unittest discover -s tests -v` → 156/156 通过；
  `python3 tools/check_publication.py` 通过。
- 真机复核：通过 `pkexec nmap` 再次检查 `192.168.0.220` 的
  80/9090/9091，未发现在线主机，因此未发送 KM-WSDL 请求。

遗留问题：

- 设备在线后才能确认 SOAP 版本、HTTPS 证书、认证前置条件和真实响应。
- 能力响应仅由静态契约和合成 XML 验证，尚未确认真实设备的重复元素、
  可选字段、数值单位或枚举。
- 尚未验证 `start_scan` 枚举值、取图分页、末页标记和失败码的真机语义。
- Windows TWAIN 动态流量仍未抓取；当前网络协议依据官方二进制静态分析。

上一轮文档整理已把原有里程碑和 29 轮交接完整移入
`docs/reverse-engineering/progress-history.md`；本文件继续只保留当前结论。

## 下一步

优先执行：设备恢复在线后运行
`python3 tools/kmscn_probe.py <device> --json --raw`，成功后运行
`python3 tools/kmscn_probe.py <device> --capability --json --raw`；再根据结果
测试 `--https --insecure` 和 `--soap-version 1.2`。确认服务信息与能力响应后，
才进入扫描会话状态机。

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
