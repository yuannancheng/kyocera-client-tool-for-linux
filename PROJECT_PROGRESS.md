# PROJECT PROGRESS

> 最后更新：2026-11-01。详细轮次记录已归档到
> [`docs/reverse-engineering/progress-history.md`](docs/reverse-engineering/progress-history.md)；
> 本文件只保留当前状态、优先级、阻塞和可执行的下一步。

## 项目目标与当前状态

本项目研究京瓷 MA2000w 多功能打印机及 Windows 版 KYOCERA Client Tool 的
功能和通信行为，并在 Linux 上实现可移植、可测试的替代工具；长期目标不限于
MA2000w。

当前结论：**MA2000w 网络扫描已在 Linux 端独立打通。** 只读监控、设备发现、
本地 Web/GUI、配置只读导出、配置安全基线和单页扫描均可用；彩色与灰度 RAW、
官方扫描参数覆盖和多页状态机处理均已实现。2026-10-29 使用 32 位 Wine
诊断宿主捕获官方 DLL 的真实 SOAP 1.2 请求，随后在不依赖官方 DLL 的 Python
实现中完成预检、默认配置读取、开会话、启动扫描、XOP 取图、RAW 分带解码、
BMP 输出和关会话。最大风险已从“协议方法猜测”转为“其他输出格式、其他机型
和 ADF/双面硬件路径的验证”。

**最高优先级工程约束：** 官方二进制可观察到的行为优先于项目自身推断；
正式 Linux 功能只复刻行为，不在运行时依赖官方 DLL/EXE。详细规则见
`AGENTS.md` 第 0 节。

当前产品边界：

- 已验证：TCP 9100 PJL、SNMPv1/v2c、设备发现、多设备 Web 总览、原生 GUI、
  147 项配置对象只读导出（MA2000w 实测 96/147 返回 `STATUS=0`），以及
  带完整性校验和设备绑定的配置基线/差异检查。
- 静态已验证：网络 TWAIN 使用 `Ns1815TWGN -> KMNETSCN3 -> KMSCNAPI`；
  KM-WSDL 使用 HTTP 9090 或 HTTPS 9091，扫描 action 已还原。
- 已真机验证：KM-WSDL SOAP 1.2 预检、默认配置、扫描会话、XOP 取图、
  `ALL_GET_COMPLETE`、关会话以及彩色/灰度独立 RAW→BMP 解调。
- 已验证协议/模拟：`CONTINUE_SCAN` 官方返回码、ADF/双面/连续扫描字段、
  多页逐页保存和最终关会话。
- 离线实现：USB `usblp` 路径、PJL 分段补发、PTY 假设备往返。
- 未闭环：物理 USB、配置写入、其他机型兼容性、完整色彩管理，以及
  ADF/双面/多页硬件验证。MA2000w 本身没有输稿器。

## 计划对齐检查

| 检查项 | 事实 | 判断 |
| --- | --- | --- |
| 研究范围 | 仍限定在 `Kyocera/ClientTool` 及 Linux 实现所需协议 | 未偏移 |
| 产品目标 | 仍以复刻设备侧可验证功能为目标，没有转向通用 SNMP 工具 | 未偏移 |
| 用户可见能力 | Linux 已可独立完成 MA2000w 彩色/灰度单页网络扫描并输出 BMP | 已对齐 |
| 阶段重点 | SOAP 1.2、会话、XOP、参数枚举和多页状态均由官方证据驱动 | 转入跨机型验证 |
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
| 官方扫描预检顺序复刻 | `DONE` | service info 成功后才请求 capability；失败阶段结构化记录 |
| Linux 扫描端到端 | `DONE` | MA2000w 真机单页：SOAP 1.2、XOP、RAW 解码、2496×3520 BMP、正常关会话 |
| 扫描非默认颜色与灰度 RAW | `DONE` | MA2000w 真机 `GRAYSCALE`；9,425,014 字节 RAW，独立输出 2496×3520 BMP |
| 官方扫描参数覆盖 | `DONE` | 官方 DLL 枚举表与请求；CLI 仅接受已知 token，序列化顺序有测试 |
| ADF/双面/多页客户端路径 | `DONE` | 官方 `CONTINUE_SCAN=10010` 证据；多页模拟覆盖两页、ADF/BOOKLET/ON 和关会话 |
| ADF/双面其他机型真机 | `BLOCKED` | 当前只有 MA2000w，无输稿器；不能据模拟测试宣称硬件兼容 |
| USB 物理验证 | `BLOCKED` | 物理连接未确认；仅完成离线 PTY 测试 |
| 配置只读基线与差异 | `DONE` | 147 项私密快照、SHA-256、通道/目标绑定、只读差异测试 |
| 配置单字段写入计划 | `DONE` | item 2 dry-run、漂移阻断、回滚预演和确认令牌；不执行写入 |
| 配置写入与回滚 | `TODO` | 尚无最小写入、回读验证和真实设备回滚样本 |

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
- **Linux 网络扫描**：`tools/kmscn_scan.py` 独立执行预检、默认配置、会话、
  启动、轮询取图、`ALL_GET_COMPLETE` 和关闭；`kmscn_raw.py` 按官方
  `CScanData::PrepareImageData` 状态机解析校准和颜色分带。真机样本为
  2496×3520 BMP，原始流 28,275,026 字节。
- **扫描参数与灰度**：颜色、分辨率、单双面、原稿位置、连续扫描、原稿类型
  和输出格式只暴露官方 token。MA2000w 灰度 RAW 为单平面颜色值 `1`，
  9,425,014 字节；真机解码为清晰 2496×3520 BMP。请求 JPEG 时设备仍返回
  RAW，客户端按响应 `file_type` 选择解码器。
- **多页状态机**：官方宿主实测 `CONTINUE_SCAN=10010`、无图像；官方线程继续
  取图。Linux 客户端支持 `CONTINUE_SCAN`、`IMAGE_CREATING_NOW`、
  每页 `SUCCESS` 和 `ALL_GET_COMPLETE`，逐页命名并支持 `--max-pages`；
  模拟测试已覆盖两页和 `ADF/BOOKLET/ON` 请求。
- **OID 语义**：827 个唯一文本 OID，其中 91 个为第三方库常量；736 个设备
  OID 中 735 个已有名称或语义，仅 `1.3.6.1.4.1.1347.42.27.6.0` 未知。
- **配置安全基线**：`--config-save` 以 `0600` 原子保存完整 147 项快照，
  规范化 JSON 带 SHA-256；`--config-compare` 校验权限、通道和目标后只比较
  设备语义值。官方 `KMUTLCFG.exe` USB 模板已复核为 `VALUE =`，且没有发送
  任何写命令。
- **配置写入计划**：`--config-plan` 仅允许 item 2 `Auto error clear` 的
  `OFF/ON` 转换，要求全表无持久配置漂移和读取状态变化，并生成当前值、
  目标值、回滚值、PJL/SNMP 预览及确认令牌；`execution.allowed=false`。

## 当前优先级

1. **P0：在有 ADF/双面硬件的其他机型上验证已实现的协议路径。** MA2000w
   没有输稿器；可在其他机型测试 `ADF + SIMPLEX/DUPLEX/BOOKLET + 多页`，
   对照官方 KMIP 输出。没有相应硬件时不得标记为跨机型兼容已验证。
2. **P1：USB 硬件验证。** 接入设备后跑 `--list-usb`、`--usb --json`，与 TCP
   结果逐项对照；同时验证断线重连和睡眠唤醒。
3. **P2：实现受控单字段写入器。** 基线、差异检查和 item 2 dry-run 已完成；
   下一步必须先让用户明确批准一次真机写入实验，再实现确认令牌校验、写入后
   同 OID 回读和失败回滚。未经批准仍不得发送 `KSETOBJ` 或 `snmpset`。
4. **P3：按需补字段语义。** OID 全量清点冻结；只有阻塞扫描或写入时才查新字段。

## 待验证假设

- 官方 KMIP 完整色彩矩阵在更复杂颜色/画质模式下是否会影响当前 RAW→RGB。
- ADF、双面和第二页在其他机型上的 `retrieve_image` 结果序列和硬件行为。
- MA2000w 接受 `RESOLUTION_200X200` 但返回尺寸/字节数未变化；是否钳制参数未知。
- 请求 JPEG 时 MA2000w 仍返回 RAW；其他输出格式的返回类型和设备支持范围未知。
- HTTPS 9091 的证书和认证行为；MA2000w 当前未监听 9091。
- USB 原始 UEL 帧是否与 TCP 9100 完全一致；语言监视器是否增加额外封装。
- 原厂程序在 USB 与网络连接下是否使用相同的 PJL 查询序列。
- `43.5.1.1.33/34/35` 的厂商名称虽已匹配，仍需写入回读或原厂界面确认。
- `1.43.5.1.1.29.1` 是否为 `kcprtAssetNumber`；设备返回空字符串，旧标签证据不足。
- `CODE2=30014/30001` 组合分支的准确触发条件。
- NetViewer `.NET` 的 `ScanOperation` 是否存在反射或动态加载调用；当前静态引用
  只指向 `Core.CoreServices.dll` 自身。
- 其他型号是否同样接受空 `open_session` 和默认配置直传。
- `KMUTLCFG.exe` 与 `KMUTLPRE.exe` 的 `KSETOBJ` 空格、引号和类型编码是否
  由设备端等价接受。
- 各配置字段的真实成功响应、失败响应、延迟和重启副作用。

## 当前阻塞

- 当前没有真实 Windows 主机；已安装 Wine/32 位 MinGW 作为本地行为观测
  环境，但它不能覆盖所有 Windows TWAIN UI 和驱动动态路径。
- 当前 MA2000w 没有输稿器；ADF、双面和真正多页只能完成协议构造与模拟状态机
  验证，跨机型硬件验证阻塞。
- USB 物理验证受硬件接入限制；历史检查未发现 `0482:0d51`，本次 `lsusb`
  因执行环境无法初始化 libusb（`-99`）而未能复核，接入时需重新确认。
- MA2000w 的 9090 在睡眠状态可正常完成扫描；此前失败已确认是简化 SOAP 1.1
  请求不匹配官方 SOAP 1.2 封装，不再是阻塞。
- 设备只发布 WSD 打印服务，`631/tcp` 关闭；扫描使用 KM-WSDL，而非 eSCL。
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

## 最近一次工作交接（第三十五轮）

日期：2026-11-01。范围：实现配置单字段 dry-run 计划；没有执行 SNMP SET、
`KSETOBJ`、重启或配置写入。

完成与证据：

- 新增 `config_write_plan.py`。首个候选固定为 item 2 `Auto error clear`
  （`43.5.1.1.34.1`，Integer，`0=OFF/1=ON`），理由和 UI 映射写入计划。
- 计划器复验快照、目标、传输和全表持久配置差异；读取状态变化与配置变化
  都会阻断，Wi-Fi RSSI 等易变遥测只记录不阻断。
- 计划包含当前值、目标值、回滚值、`@PJL KSETOBJ ... VALUE =` 预览、
  SNMP Integer 参数、同 OID 回读要求及 SHA-256 确认令牌。
- `execution.allowed` 固定为 `false`；CLI 明确显示 dry run，且没有设备写通道。
- 验证：计划专项 5/5；全量测试 190/190；公开树检查通过。

遗留问题：

- 尚无经用户明确授权的真机写入实验。
- 写入响应、延迟、是否需要重启以及中断恢复仍未知。
- 在真实设备样本前不得移除 `write_executor_disabled` blocker。

## 历史交接（第三十四轮）

日期：2026-11-01。范围：配置只读基线、差异检查和写入前置证据；没有执行
SNMP SET、`KSETOBJ`、重启或配置写入。

完成与证据：

- 官方 `KMUTLCFG.exe` 哈希仍为
  `63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea`。
- 复核 `FUN_00402ec0`：USB 写入只收集变化对象，命令模板
  `0x00499ce4` 为 `@PJL KSETOBJ OBJ="%s%s" VALUE =%s\r\n`；绝对和相对
  OID 前缀分别为 `#` 与 `1.`。响应解析模板同样使用 `VALUE =%s`。
- 新增 `config_snapshot.py`：147 项完整快照、固定 schema、UTC 时间、
  传输/目标绑定、规范化 JSON SHA-256、重复键检测、组/其他用户可读拒绝、
  `0600` 原子写入和默认不覆盖。
- CLI 新增 `--config-save`、`--config-compare`、`--config-force` 和
  `--config-allow-target-mismatch`；差异比较按 item id/OID 对齐，只比较
  `status`、`value_kind`、`value`，有差异返回退出码 `1`。
- 快照保留 raw wire value，并标记 community、SSID、sysContact、sysLocation
  等敏感字段；文档明确快照不得进入公开仓库。
- Wi-Fi 连接状态、RSSI、信道被分类为只读易变观测。只读实测捕获 RSSI
  `-69 dBm -> -71 dBm` 的自然变化，因此不把此类波动计为配置差异；读取状态
  变化仍单独报告并 fail closed。
- 新增配置写入安全文档，明确未来单字段写入必须具备基线稳定、显式确认、
  set 后同 OID 回读、失败停止和回滚；设备重置不自动发送。
- 验证：配置专项 17/17；全量测试 185/185；公开树检查通过。MA2000w 只读
  基线保存和后续比较均为 96/147；最终比较为 0 个配置变化、0 个易变观测、
  0 个读取状态变化。未发送任何写命令。

遗留问题：

- 尚未实现任何写入执行器，也没有成功/失败 `KSETOBJ` 或 SNMP SET 真机样本。
- 每个字段需要重启的条件、超时、断网风险和中断恢复仍未知。
- `KMUTLPRE.exe` 写入格式与 `KMUTLCFG.exe` 的空格/类型差异尚未比较。

## 历史交接（第三十三轮）

日期：2026-10-31。范围：补齐扫描参数、多页状态机与灰度 RAW；没有执行
SNMP SET、`KSETOBJ`、重启或配置写入。

完成与证据：

- 官方 `KMSCNAPI.dll` 哈希仍为
  `d3e276ebe284351e46549fc1c5145c4241fa41e70f4aca306a5abc94b20f2d7a`。
- 从枚举表和官方 `start_scanRequest` 固化颜色、分辨率、双面、原稿位置、
  连续扫描、原稿类型和输出格式 token；`continuous_scan_mode` 为 `OFF/ON`。
- 官方 DLL 对本地假服务返回 `CONTINUE_SCAN` 时，
  `KMSCNRetrieveImage=10010`、无图像；客户端改为等待后继续取图。
- 新增分辨率、颜色、双面、原稿位置、连续扫描和原稿类型限制选项；新增多页
  逐页保存测试，覆盖两页和 `ADF/BOOKLET/ON`。
- MA2000w `GRAYSCALE + RAW` 真机成功：RAW 9,425,014 字节，单平面 8 带；
  BMP 2496×3520、26,357,814 字节，图像清晰；关会话成功。
- 请求 JPEG 的一次真机运行仍返回 RAW 分带体；解码改为以响应
  `file_type` 为准。另一次格式协商在读取 11.7 MB 后 chunked 响应中断，
  客户端已把该异常转为结构化错误。
- 中断后的最终只读预检仍返回 `SUCCESS`，服务能力可读，未观察到遗留扫描会话。
- 用户确认 MA2000w 没有输稿器；ADF/多页保留用于其他机型，未宣称为本机
  或跨机型硬件验证完成。
- 验证：扫描专项 38/38；全量测试 178/178；公开树检查通过。

遗留问题：

- ADF、双面、BOOKLET 和真正多页需其他有输稿器的机型验证。
- 600 DPI、非 RAW 输出、取消和异常中断恢复仍需真机样本。
- MA2000w 的 200 DPI 请求未改变输出尺寸；参数钳制行为未知。
- HTTPS 9091、认证和跨机型兼容性未验证。

Wine 捕获环境、`CONTINUE_SCAN` 返回码实验和端口绕法已写入
`docs/reverse-engineering/tooling.md`。

## 下一步

优先执行：在具备 ADF/双面的其他机型上验证
`ADF + DUPLEX/BOOKLET + 多页` 和响应 `file_type`；逐项对照官方 KMIP
输出。没有此类硬件时，由用户明确批准一次 item 2 `Auto error clear` 真机
写入实验；确认实际值、写入响应、同 OID 回读和回滚结果后才能实现执行器。

## 相关文档

- `docs/reverse-engineering/progress-history.md`：压缩前的完整进度与轮次记录
- `docs/reverse-engineering/program-structure.md`
- `docs/reverse-engineering/clienttool-protocol.md`
- `docs/reverse-engineering/config-write-safety.md`
- `docs/reverse-engineering/protocol-notes.md`
- `docs/reverse-engineering/scan-workflow.md`
- `docs/reverse-engineering/tooling.md`
- `docs/reverse-engineering/kmws-soap.md`
- `docs/reverse-engineering/usb-path.md`
- `docs/reverse-engineering/netviewer-log-findings.md`
- `docs/reverse-engineering/samples/ma2000w-pjl.txt`
- `docs/architecture.md`
- `CHANGELOG.md`
