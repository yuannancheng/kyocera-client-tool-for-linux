# PROJECT PROGRESS

> 最后更新：2026-11-01。详细轮次记录已归档到
> [`docs/reverse-engineering/progress-history.md`](docs/reverse-engineering/progress-history.md)；
> 本文件只保留当前状态、优先级、阻塞和可执行的下一步。

## 项目目标与当前状态

本项目研究京瓷 MA2000w 多功能打印机及 Windows 版 KYOCERA Client Tool 的
功能和通信行为，并在 Linux 上实现可移植、可测试的替代工具；长期目标不限于
MA2000w。

当前结论：**MA2000w 网络扫描产品闭环已在 Web 端独立打通。** 只读监控、
设备发现、统一 Web/GUI、配置只读导出、配置安全基线、单页扫描和两项受控配置
写入均可用；彩色与灰度 RAW、官方扫描参数覆盖和多页状态机处理均已实现。
扫描编排已移入 `kyocera_monitor.scan`，Web 详情页可提交后台任务、查看阶段并
下载 PNG/PDF/JPEG/TIFF/高压缩 PDF/XPS/BMP/RAW。MA2000w 真机已取得
2496×3520 PNG、PDF 和 JPEG；最大风险转为其他机型、ADF/双面、USB、复杂色彩
管理，以及 TIFF/XPS 在真实查看器或其他设备上的验证。

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
  `ALL_GET_COMPLETE`、关会话，以及彩色 RAW→PNG/PDF/JPEG 和灰度路径。
- 已验证协议/模拟：`CONTINUE_SCAN` 官方返回码、ADF/双面/连续扫描字段、
  多页逐页保存和最终关会话。
- 离线实现：USB `usblp` 路径、PJL 分段补发、PTY 假设备往返。
- 已验证写入：MA2000w `Auto error clear` 经 SNMPv2c 从 OFF→ON→OFF，
  SET echo 和同 OID 回读均成功；`Quiet mode` 同样完成回读和恢复；另有 25 个
  无害整数字段完成批量写入、目标回读和自动恢复，最终全表一致。
- 未闭环：物理 USB、其他机型兼容性、完整色彩管理、TIFF/XPS 真实查看器
  验证，以及 ADF/双面/多页硬件验证。MA2000w 本身没有输稿器。

## 计划对齐检查

| 检查项 | 事实 | 判断 |
| --- | --- | --- |
| 研究范围 | 仍限定在 `Kyocera/ClientTool` 及 Linux 实现所需协议 | 未偏移 |
| 产品目标 | 仍以复刻设备侧可验证功能为目标，没有转向通用 SNMP 工具 | 未偏移 |
| 用户可见能力 | Web 单进程可选择设备并完成 MA2000w 彩色/灰度扫描，下载 PNG/PDF/JPEG 等 | 已对齐 |
| 阶段重点 | P0 扫描产品闭环已完成；格式与文件长度行为均由官方证据驱动 | 转入安装发布与回归 |
| 进度记录 | 详细交接继续归档，总览保留当前事实和阻塞 | 保持 |

判断依据不是工作量多少，而是这些工作是否直接解除当前产品阻塞。OID 命名对
配置写入和扫描仍有支撑价值，但应改为“遇到具体字段再查”，不再作为主攻方向。

## 当前阶段

`IN_PROGRESS`：阶段 E，产品化收口。P0 扫描产品闭环已完成，下一步转入 P1
安装与发布收口，同时补齐 P2 集成失败路径。

阶段 D 的核心能力已经可用。当前不再继续扩大协议研究或配置字段覆盖；
扫描能力已经收束成一个普通用户实际可用的产品闭环：

> 安装一次后，从一个 Web/GUI 入口发现或选择打印机、查看状态、发起扫描并取得
> PNG/PDF/JPEG 等文件，不要求用户另行运行 `tools/kmscn_scan.py`。

该验收已于 2026-11-01 在 MA2000w 上完成：同一 Web 服务创建扫描任务、显示
阶段、生成 JPEG 下载，并验证 PNG/PDF 也可由集成 CLI 与服务层生成。Web 页面
的 GTK 容器与浏览器共用同一 `create_server()` 页面；本轮未在图形桌面中人工
点击 GTK 窗口，但 Web API、页面资源、任务状态和文件下载均已执行验证。

### 2026-11-01 重规划决议

复盘事实：

- 本地领先 `origin/main` 的 9 个提交全部属于配置基线/写入/审计；
- 配置区域已有两个受控写入闭环、25 个无害字段恢复测试和 216 项全量测试，
  已达到当前产品所需的可信度；
- 扫描协议已经真机打通，但主程序 Web/GUI 仍是只读状态页，扫描入口仍为
  仓库内独立脚本 `tools/kmscn_scan.py`；
- 当前最影响用户使用的不是再验证第 26 个配置字段，而是缺少集成入口、
  安装后可用性和端到端验收。

阶段闸门：

1. **立即冻结配置扩展。** 除现有功能缺陷或明确的新字段需求外，不再提交新的
   OID、配置写入或配置研究改动。
2. **一次任务只推进一个主目标。** 先完成扫描产品闭环，再做打包和发布整理。
3. **按可交付阶段提交。** 一个端到端里程碑通常 1–3 个提交；测试和文档随功能
   一并提交，不再为每个中间步骤单独提交。
4. **硬件阻塞项不占用主线。** ADF、双面、USB 和其他机型在对应硬件出现后再做，
   不继续用模拟结果填充进度。

| 新优先级 | 主任务 | 完成标准 | 状态 |
| --- | --- | --- | --- |
| P0 | 扫描能力产品化 | 扫描编排移入 Python 包；解耦设备格式与本地导出格式；单进程 Web/GUI 默认提供 PNG/PDF/JPEG 等下载；MA2000w 真机成功 | `DONE` |
| P0 | 核心工作流整合 | 发现/手动添加设备、状态页、扫描页共享同一设备选择，无需手工复制路径或运行独立脚本 | `DONE` |
| P1 | 安装与发布收口 | 干净环境 `pip install .` 后可启动 GUI/Web 并扫描；入口、桌面文件、README 与实际功能一致 | `TODO` |
| P2 | 集成回归 | 扫描超时、设备忙、解码失败、重复扫描和输出文件错误均有自动测试 | `IN_PROGRESS` |
| BLOCKED | ADF/双面/其他机型 | 获得对应硬件后验证真实行为 | `BLOCKED` |
| BLOCKED | USB 物理路径 | 获得可访问的 `usblp` 设备后验证断线、重连和睡眠唤醒 | `BLOCKED` |
| FROZEN | 配置字段扩展 | 当前 25 字段与写入安全边界足够；仅缺陷或明确需求触发 | `FROZEN` |

P0 已完成：扫描编排位于 `kyocera_monitor.scan`，Web API 与 CLI 共用服务层；
Web 详情页提供参数、阶段、忙保护和文件下载。MA2000w 真机返回 RAW 后已生成
PNG、PDF 和 JPEG；TIFF、高压缩 PDF、XPS 已通过本地编码/结构测试。官方设备
token 与本地导出格式已分离，RAW 保留为高级选项。

下一主目标是 P1：在干净虚拟环境执行 `pip install .`，验证 Pillow 依赖、
CLI/GUI/Web 入口、桌面文件、首次发现/手动添加和一次扫描。P2 仅补与本阶段
直接相关的超时、输出文件和重复扫描测试；不再扩展配置字段。

官方程序完整能力、证据和逐项覆盖状态见
[`docs/official-feature-parity-plan.md`](docs/official-feature-parity-plan.md)。
功能复刻按以下波次推进：

- **E1/P0 扫描闭环**：F13 图像采集、F14 本地导出、F15 参数界面、F17 PDF；
- **E2/P1 核心设备管理**：F02 状态、F04 通知、F06 安全配置写入、F08 面板/
  Wi-Fi 状态、F16 保存目录、F19 Quick Scan 预设、F22 计数导出；
- **E3/P2 设备驱动工作流**：F03 作业、F07 网络配置、F09 Wi-Fi、F20 Push Scan、
  F21 Print Box、F26 SNMPv3；F18 邮件为可选出口，F27 USB 在硬件出现后验证；
- **E4/P3 高风险或硬件依赖**：F10–F12 重启/维护/固件、F23 计划发送、
  F24–F25 传真；
- **E5/P4 可选或平台专用**：F28–F30 外部链接、打印驱动集成、Content Redactor。

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
| 扫描产品闭环 | `DONE` | 包内服务、Web 后台任务/阶段/下载；MA2000w 真机 PNG/PDF/JPEG |
| 官方格式本地导出 | `DONE` | PNG/PDF/JPEG/TIFF/高压缩 PDF/XPS/BMP/RAW；PNG/PDF/JPEG 真机通过 |
| 扫描非默认颜色与灰度 RAW | `DONE` | MA2000w 真机 `GRAYSCALE`；9,425,014 字节 RAW，独立输出 2496×3520 BMP |
| 官方扫描参数覆盖 | `DONE` | 官方 DLL 枚举表与请求；CLI 仅接受已知 token，序列化顺序有测试 |
| ADF/双面/多页客户端路径 | `DONE` | 官方 `CONTINUE_SCAN=10010` 证据；多页模拟覆盖两页、ADF/BOOKLET/ON 和关会话 |
| ADF/双面其他机型真机 | `BLOCKED` | 当前只有 MA2000w，无输稿器；不能据模拟测试宣称硬件兼容 |
| USB 物理验证 | `BLOCKED` | 物理连接未确认；仅完成离线 PTY 测试 |
| 配置只读基线与差异 | `DONE` | 147 项私密快照、SHA-256、通道/目标绑定、只读差异测试 |
| 配置单字段写入计划 | `DONE` | item 2 dry-run、漂移阻断、回滚预演和确认令牌；不执行写入 |
| 配置写入与回滚 | `DONE` | MA2000w item 2 SNMPv2c OFF→ON→OFF；SET echo、双重回读和全表恢复一致 |
| item 50 审计写入计划 | `DONE` | OFF/ON 计划、回滚、预览和令牌；测试覆盖 3 项 |
| item 50 写入与回滚 | `DONE` | MA2000w SNMPv2c OFF→ON→OFF；双重回读成功，全表无持久漂移 |
| 无害整数字段批量审计 | `DONE` | 25/25 写入、目标回读、恢复、原值回读成功；最终 147 项一致 |

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
- **配置写入计划**：`--config-plan` 支持 item 2 `Auto error clear` 和
  item 50 `Quiet mode` 的 OFF/ON 计划，要求全表无持久配置漂移和读取状态
  变化，并生成当前值、目标值、回滚值、PJL/SNMP 预览及确认令牌。
- **单字段配置写入**：SNMPv2c `Auto error clear` 和 `Quiet mode` 的
  `OFF -> ON -> OFF` 可由匹配令牌、基线和 scope 的 `--config-apply` 执行。
  MA2000w 两个字段的 SET/回读/回滚均成功；操作后完整 147 项比较均无持久
  配置变化，未观察到重启或断网。PJL 写入和其他字段未开放。
- **item 50 候选与设备证据**：`--config-candidates` 评估读取状态、Integer
  类型和 `OFF/ON` 枚举；`mapping_confidence=device_verified`。候选报告中的
  `write.allowed` 仍固定为 `false`，保留设备失败恢复和再次明确授权边界。
- **item 50 写入路径**：官方控件 `0x455` → 模型 `+0x18` → 差异 case `0x31`
  → OID `1001.2.1.1.1.14.1`，整数 `0/1`；MA2000w SNMPv2c 已写入 `1`、
  回读 `1`、恢复 `0`、回读 `0`。设备仍可访问，全表无持久漂移。
- **无害字段批量写入**：`--config-audit-safe` 固定覆盖 25 个已审查整数字段，
  逐项改值、目标回读、恢复和原值回读；MA2000w 25/25 成功，最终 147 项
  完全一致。网络/Wi-Fi、凭据、trap、传真、重置、字符串和未知语义均排除。

## 当前优先级

1. **P1：完成安装和发布收口。** 在干净环境验证 Pillow 依赖、安装、桌面入口、
   Web/GUI 启动和首次扫描，修正文档与实际能力不一致之处。
2. **P2：补齐扫描集成失败路径。** 超时、设备忙、解码失败、重复扫描和输出
   文件错误必须有自动测试与清晰用户提示。
3. **DONE：扫描产品闭环。** 包内服务、Web 后台任务、阶段反馈和多格式下载
   已由 MA2000w 真机验证。
4. **FROZEN：配置字段扩展。** 当前覆盖已经足够，不再主动扩大。
5. **BLOCKED：ADF/双面、其他机型和 USB。** 等待对应硬件后单独验证，不进入
   主线排期。

## 待验证假设

- 官方 KMIP 完整色彩矩阵在更复杂颜色/画质模式下是否会影响当前 RAW→RGB。
- ADF、双面和第二页在其他机型上的 `retrieve_image` 结果序列和硬件行为。
- MA2000w 接受 `RESOLUTION_200X200` 但返回尺寸/字节数未变化；是否钳制参数未知。
- 请求 JPEG 时 MA2000w 仍返回 RAW；其他设备原生输出格式的行为未知。Linux
  已实现 RAW→PNG/PDF/JPEG/TIFF/高压缩 PDF/XPS/BMP 本地导出。
- HTTPS 9091 的证书和认证行为；MA2000w 当前未监听 9091。
- USB 原始 UEL 帧是否与 TCP 9100 完全一致；语言监视器是否增加额外封装。
- 原厂程序在 USB 与网络连接下是否使用相同的 PJL 查询序列。
- `43.5.1.1.33/35` 仍需写入回读或原厂界面确认；`.34.1` 已完成
  SNMPv2c ON/OFF 写入回读。
- `1.43.5.1.1.29.1` 是否为 `kcprtAssetNumber`；设备返回空字符串，旧标签证据不足。
- `CODE2=30014/30001` 组合分支的准确触发条件。
- NetViewer `.NET` 的 `ScanOperation` 是否存在反射或动态加载调用；当前静态引用
  只指向 `Core.CoreServices.dll` 自身。
- 其他型号是否同样接受空 `open_session` 和默认配置直传。
- `KMUTLCFG.exe` 与 `KMUTLPRE.exe` 的 `KSETOBJ` 空格、引号和类型编码是否
  由设备端等价接受。
- 各配置字段的真实成功响应、失败响应、延迟和重启副作用。
- MA2000w `retrieve_imageResponse/file_size=958464` 的业务含义未知；官方代码
  已确认它不参与图像数据指针或长度计算。
- TIFF、高压缩 PDF/XPS 已通过编码/结构测试，但尚未完成 MA2000w 真机文件查看
  与其他设备原生格式验证。

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

## 最近一次工作交接（第四十三轮）

日期：2026-11-01。范围：P0 扫描产品闭环、官方格式本地导出、真机验收和
`retrieve_imageResponse/file_size` 证据复核。

完成与证据：

- 新增 `kyocera_monitor.scan`，把扫描编排、后台任务和格式转换移入包内；
  `tools/kmscn_scan.py` 改为兼容 CLI。
- Web/GUI 设备详情页新增扫描表单、阶段反馈和下载。`POST /api/scans` 创建
  per-device 独占后台任务，`GET /api/scans/<id>` 查询，
  `GET /api/scans/<id>/files/<n>` 下载。
- 官方 `image_file_format` 的六种 token 均提供本地对应输出：
  PDF/TIFF/JPEG/高压缩 PDF/XPS/RAW；另保留 PNG 与 BMP。JPEG/TIFF 和
  内嵌 JPEG 的 PDF/XPS 使用 Pillow。
- 重新分析哈希匹配的 `KMSCNAPI.dll`
  （`d3e276ebe284351e46549fc1c5145c4241fa41e70f4aca306a5abc94b20f2d7a`）：
  `FUN_1003c520` 将 `file_size` 写入响应 `+0x24`；`FUN_1007a450` 的图像
  指针和长度来自 `image_data` 对象 `+0x28` 内的 `+4/+8`，未读取 `+0x24`；
  `KMNETSCN3::FUN_10005ba0` 再返回实际图像指针/长度。因此 `file_size`
  不用于传输总长，但其设备侧业务含义仍未知。
- MA2000w 真机成功完成三次集成彩色单页扫描：
  - PNG 18,901,007 字节，SHA-256
    `ab5716a4be1f87918ffc4f7f40b3d25f952c9f14518aa9aaa5f2aeb52a6d1d50`；
  - PDF 18,878,382 字节，SHA-256
    `03236afc6094d20216f54e7accfba5258e9363f9e268c35adf3be2b1aafe0332`，
    Poppler 识别为单页 A4、解析和渲染成功；
  - JPEG 2,319,913 字节，SHA-256
    `a12ba1cecf479a49a616e75bbe91cb1759646face177c08b372c8fcd8ddf00de`，
    2496×3520，人工查看清晰。
  三次设备均返回 RAW，`close_session=SUCCESS`。
- 单进程 Web 服务再完成一次灰度 JPEG 任务：任务阶段到 `complete`，下载文件
  2,146,104 字节、2496×3520，SHA-256
  `67bce9c7ca505a37968e9f6f0fa524944405b7b716d9394e1f54751f71195fa2`，
  MIME 与下载文件名一致。

验证：

- `python3 -m unittest discover -s tests -v` → 234/234 通过；
  `python3 tools/check_publication.py` 通过；`git diff --check` 和
  `compileall` 通过。
- 真机验证使用 MA2000w `192.168.0.220`；没有发送配置写入、维护或重置命令。
- PNG/PDF/JPEG 真机通过；TIFF/高压缩 PDF/XPS 当前为编码/结构测试，
  尚未覆盖真实查看器和其他机型。
- 详细证据与复现命令见 `docs/reverse-engineering/scan-workflow.md`
  第 9.9.7/9.9.8 节。

下一步：P1 干净环境安装与发布收口。

## 历史交接（第四十二轮）

日期：2026-11-01。范围：项目节奏复盘、官方 ClientTool 功能重盘和下一阶段重排；
没有修改设备状态。

完成与证据：

- 核对最近 9 个本地领先提交，全部属于配置基线/写入/审计；确认配置工作已达到
  当前产品阈值，继续扩展会挤占真正缺失的用户工作流。
- 从已保存的 `KMSTMVM`、`KMSTMNET`、`KMSTMNW`、`KMUTLCFG`、`KMUTLPRE`、
  `KMUTLMNT`、`KMSCN*`、`FAX`、Wi-Fi 和 Counter Monitor 证据整理 30 项
  官方功能及当前覆盖状态，落到
  `docs/official-feature-parity-plan.md`。
- 将主线改为扫描产品闭环，随后是统一设备管理、Push Scan/Print Box/Wi-Fi/
  SNMPv3，维护与传真等高风险或硬件依赖功能后置。
- 只读复核 MA2000w：`get_capability` 未返回 output image format 能力块，
  默认配置为 `RAW`，此前请求 JPEG 后响应仍为 RAW；当前客户端只实现 RAW→BMP。
  下一阶段必须分离设备请求格式和本地导出格式。
- 冻结配置字段扩展；普通功能按 1–3 个提交的端到端里程碑交付。

验证：本轮为规划和证据整理，未发送扫描、配置写入或维护命令。最终执行公开树
检查与 diff 检查后提交。

## 历史交接（第四十一轮）

日期：2026-11-01。范围：按要求完成配置写入区域的代表性无害字段批量验证并收尾。

完成与证据：

- 新增 `--config-audit-safe PATH` 和 `config_write_audit.py`，从不含漂移的
  私密基线生成固定白名单，逐项执行目标 SET、目标回读、原值 SET、原值回读。
- 白名单 25 个字段：item 1、3、10、11/12/14/15/17/18/19/20/24-32、
  49、51、52、84、85；覆盖睡眠、自动清除超时、纸张不匹配策略、媒体重量、
  浓度、单位、送纸超时和面板自动清除。
- MA2000w 结果 25/25 成功；目标值和恢复值全部同 OID 回读正确。
  逐项证据位于
  `docs/reverse-engineering/data/clienttool-safe-write-audit-20261101.tsv`。
- 批量审计后完整 147 项比较：0 个配置变化、0 个易变观测、0 个读取状态变化、
  147 项不变。
- 网络/Wi-Fi、IPv4/DHCP/协议开关、SNMP community/trap、传真身份、重置触发、
  计数器、字符串和未知语义均明确排除。
- 失败语义：目标值被拒绝但恢复成功时继续；恢复失败立即停止后续字段。
- 6 个专项测试；全量测试 216/216；Python 编译和公开树检查通过。

遗留问题：

- 本次不是全 147 项批量写入；未知语义、字符串和其他风险类别仍单独审查。
- 其他机型、USB 写入和真实设备失败/断线恢复仍未验证。

## 历史交接（第四十轮）

日期：2026-11-01。范围：在用户明确确认后实现并执行一次 MA2000w item 50
`Quiet mode` SNMPv2c `OFF -> ON -> OFF` 实验。

完成与证据：

- 新增 `Quiet mode` 专项执行器和 CLI 分发；只接受
  `quiet-mode-off-to-on-then-off-v1`、item 50、同 OID 和精确
  `OFF -> ON -> OFF`，并保留令牌、目标、基线及预写值检查。
- 本地基线为 `/tmp/kyocera-quiet-mode.59mM4w/baseline.json`，权限 `0600`；
  文件 SHA-256 为
  `73f601ec4706ee5ab49aad275cb223875b8d108cd1a1b5c94f319b8c76b5153c`。
  基线和计划前读取均为 `96/147`，item 50 为 `0/OFF`。
- 计划令牌为
  `sha256:362f7173a67c9bc168784cc958a3410fcadbedc0c9d12af3f35c20cbd9870e3e`。
  执行结果：SET ON 成功，回读 `1`；SET OFF 成功，回读 `0`；状态 `success`。
- 实验后完整 147 项比较为 0 个持久配置变化、1 个易变观测变化、0 个读取
  状态变化、146 项不变。唯一变化为 Wi-Fi RSSI `-69 dBm -> -68 dBm`；
  设备持续可访问，未观察到断网或控制器重置。
- `Quiet mode` 业务标签升级为 `confidence=verified`；候选报告升级为
  `mapping_confidence=device_verified`，移除同 OID 写入回读 blocker，保留
  设备失败恢复和再次授权 blockers。
- 专项测试 20/20；全量测试 210/210；公开树检查通过。本次只发送了已授权的
  item 50 SNMP SET/回读和只读全表采集，没有发送 PJL `KSETOBJ` 或重置命令。

遗留问题：

- 尚未实测设备拒绝 SET、写后超时、回滚失败或断线恢复。
- 尚未比较 item 50 的 USB `KSETOBJ` 与 SNMP SET 实际设备行为。
- 其他字段写入仍需逐项静态审查、计划、真机回读和新的明确授权。

## 历史交接（第三十九轮）

日期：2026-11-01。范围：把 item 50 从只读候选推进到审计计划和静态失败边界
核对；没有发送设备配置写入或重置命令。

完成与证据：

- `--config-plan` 新增 item 50 `Quiet mode`：接受 `0/OFF`、`1/ON`，生成
  当前值、目标值、回滚值、PJL/SNMP 预览和确定性 SHA-256 令牌。
- item 50 计划固定 `execution.allowed=false`，保留
  `same_oid_write_readback_unverified`、
  `device_failure_and_reboot_behavior_unverified`、`executor_not_implemented`
  和 `explicit_user_authorization_required`。
- dry-run 退出码改为依据 `plan_preconditions_valid`，因此“计划有效但尚无
  执行器”返回 `0`；no-op、漂移、读取状态变化仍返回 `1`。
- 官方 `KMUTLCFG.exe` 哈希仍为
  `63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea`。
  静态复核确认 SNMP error-status 非零和 timeout 有独立错误分支；
  USB 写入等待响应最长 50 秒，`STATUS!=0` 计为失败。静态分支不代表设备端
  接受或拒绝 item 50。
- 新增 3 个计划/CLI 测试；全量测试 207/207；Python 编译检查和公开树检查通过。

遗留问题：

- 尚未观察 MA2000w 接受 item 50 SET 后的响应、回读延迟和实际设备副作用。
- 尚无获准的 item 50 执行器；需要用户显式授权后才能实现和运行。
- 尚未比较 item 50 的 USB `KSETOBJ` 与 SNMP SET 实际设备行为。

## 历史交接（第三十八轮）

日期：2026-11-01。范围：核对 item 50 的官方静态读写路径；没有发送设备
配置写入或重置命令。

完成与证据：

- 官方 `KMUTLCFG.exe` SHA-256 仍为
  `63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea`。
- `FUN_00405c10` 从模型 `+0x18` 初始化控件 `0x455`；`FUN_0040b6f0` 用
  `BM_GETCHECK` 读回并归一化为快照 `+0x18`。
- `FUN_00410740` case `0x31` 比较该槽位，变化时生成 OID
  `1001.2.1.1.1.14.1`，类型字节 `0x69`（整数），值为 `0/1`。
- 网络 `FUN_00401b20` 与 USB `FUN_00402ec0` 都消费同一变化记录；USB 相对
  OID 前缀为 `1.`，模板为 `@PJL KSETOBJ OBJ="%s%s" VALUE =%s\r\n`。
- item 50 分支不设置应用对象 `+0x57ec` 的控制器重置请求；通信页部分网络
  字段才会设置该标志。官方程序不会因 item 50 单独发送重置 OID。
- 候选报告升级为 `mapping_confidence=static_verified`；
  `write.allowed` 仍为 `false`，剩余 blockers 是设备写入回读、设备失败/
  重启行为未验证和缺少用户明确授权。

遗留问题：

- 尚未观察 MA2000w 接受该字段 SET 后的响应、回读延迟和实际设备副作用。
- 尚未比较 USB `KSETOBJ` 和 SNMP SET 的实际设备行为。
- 真机写入需要新的明确授权。

## 历史交接（第三十七轮）

日期：2026-11-01。范围：实现下一配置字段的只读候选审查；没有发送任何
配置写入或设备复位命令。

完成与证据：

- 新增 `config_write_candidates.py` 和 `--config-candidates`，只评估 item 50
  `Quiet mode`（`1001.2.1.1.1.14.1`）。
- 候选证据来自主对话框控件 `0x0455` → 模型偏移 `0x0018` → item 50；映射
  仍标记为 `inferred`。
- 报告将 `review.current_read_valid` 与 `write.allowed` 分离；后者固定为
  `false`，并列出推断映射、缺少同 OID 写入回读、失败/重启副作用未知和用户
  授权缺失。
- 新增专项测试 3/3：正常 `OFF` 读取、不可读/未知值阻断、CLI JSON 报告。
- 验证：全量测试 204/204；公开树检查通过；Python 编译检查通过。
- MA2000w `192.168.0.220` 连续两次 SNMPv2c 只读采集均为 `96/147`；
  item 50 两次均为 `STATUS=0`、`0/OFF`，当前读取稳定。
- 当前只证明报告逻辑和字段只读状态；尚未证明该字段可写或写入后安全。

遗留问题：

- item 50 的官方读写路径、SET 响应、回读延迟、失败恢复和重启副作用未知。
- 真实设备写实验需要新的明确授权；该命令本身不提供执行路径。

## 历史交接（第三十六轮）

日期：2026-11-01。范围：执行用户明确授权的 MA2000w 单字段 SNMPv2c 写入；
没有执行 PJL、其他对象或设备重置。

完成与证据：

- 新增 SNMPv2c Integer SET BER 编码、`error-status`/`error-index` 校验和
  响应回显验证。
- 新增 `--config-apply`，要求相同基线、相同赋值、匹配 SHA-256 确认令牌、
  SNMPv2c，并限制为 `Auto error clear OFF -> ON -> OFF`。
- 执行器在正向写入或回读失败时仍尝试写回 `OFF`，并记录每一步结果。
- MA2000w 真机：写入前 `0/OFF`；SET `1` 成功并回读 `1/ON`；SET `0`
  成功并回读 `0/OFF`。执行状态 `success`，未观察到重启或断网。
- 操作后完整 147 项只读比较：0 个配置变化、0 个易变观测变化、
  0 个读取状态变化，147 项一致。
- `clienttool-control-oids.tsv` 将 item 2 的控件/OID 映射升级为已验证。
- 验证：全量测试 201/201；公开树检查通过。

遗留问题：

- 已真机观察成功路径；真实 SNMP 错误响应、断线、commitFailed 和重启条件
  尚未观察到。
- PJL `KSETOBJ` 和 `KMUTLPRE.exe` 的参数差异仍未验证。
- 其他配置字段未获写入授权。

## 历史交接（第三十五轮）

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
输出。没有此类硬件时，对下一个配置字段做只读候选评估；在用户再次明确授权
之前不发送新的 SET，也不扩展 PJL 写入。

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
