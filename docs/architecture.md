# 独立 Linux 兼容实现架构

## 目标

实现与 Kyocera 打印机设备侧协议兼容的独立 Linux 工具：发现/连接打印机、
读取型号与状态、解析耗材与纸盒信息，并提供稳定的 CLI/JSON 输出，供后续
TUI、Web UI 或守护进程使用。项目与 Kyocera Corporation 无官方关联。

## 模块

```text
kyocera_monitor/
  pjl.py       PJL 帧构造、TCP 9100 与 USB usblp 传输
  usb.py       /dev/usb/lp* 发现、sysfs VID/PID 读取与设备选择
  parser.py    响应分段、状态/耗材/网络/纸盒/KGETOBJ 解析
  discovery.py SNMP 广播/单播与 WS-Discovery 的只读设备发现
  snmp.py      SNMP v1/v2c BER 编解码、GET/GETNEXT walk 与受限 Integer SET
  snmp_status.py  SNMP OID 到 PrinterSnapshot 的只读映射
  config_web.py  配置分区、脱敏视图、基线及已审核整数写入编排
  i18n.py      语言协商、自动/手动偏好和页面翻译资源
  updates.py   手动版本检查、语义版本比较、元数据校验与短时缓存
  web.py       HTTP 状态/扫描 API、页面与快照缓存
  gui.py       GTK3/WebKit2 原生窗口，内嵌同一个本地 Web 仪表盘
  scan.py      KM-WSDL 扫描编排、后台任务、RAW 解码与本地格式导出
  cli.py       CLI、JSON、监视模式、退出码
  config_snapshot.py  配置基线、完整性校验、目标绑定和只读差异
  config_write_candidates.py 下一个写入候选的只读资格审查
  config_write_plan.py 单字段 dry-run、回滚字段和确认令牌
  config_write_executor.py 获准字段的 SNMPv2c 写入、回读和回滚
  config_write_audit.py 无害整数字段白名单、逐项写入、回读和恢复
tools/
  pjl_probe.py          原始 PJL 探测
  snmp_probe.py         调用 kyocera_monitor.snmp 的 SNMP 命令行
  wsd_probe.py          WS-Discovery 只读探测
  ghidra_scripts/       本地分析辅助脚本（导出物不进入公开仓库）
```

## 数据流

1. `pjl.build_request()` 生成设备可接受的 UEL 帧。
2. `TcpChannel` 连接 9100，或 `DeviceChannel` 以非阻塞方式打开
   `/dev/usb/lp*`；USB 写入用 `select` 等待可写并处理短写，读取前丢弃残留输入。
3. `query()` 发送查询序列（USB 使用 `INFO ID` 在前的 16 条聚合序列），按
   “所有查询段是否都已回显”判断完成度。`query_merged()` 把响应按 `@PJL`
   回显切段，只补发缺失命令并按原顺序合并；接收端在出现数据后连续 `--idle`
   秒无新字节就返回部分响应，不再等满总超时。`collect()` 在核心字段仍缺失时
   再建立一次新连接完整重试；若一轮查询完全无响应，也会关闭并重新打开通道，
   以恢复 USB 端点或 `usblp` 驱动的短暂停顿。该恢复不改变查询帧或设备状态。
4. `parser.parse_response()` 按 `@PJL` 段切分，生成 `PrinterSnapshot`。
5. `parser` 把已确认的 KGETOBJ 字段放入 `kgetobj_known`，推断字段保留原始值并
   附加 `confidence: "inferred"`；其余对象仍原样保留在 `kgetobj`。
6. `--snmp` 分支由 `snmp_status.collect_snmp_snapshot()` 顺序执行 1 次标量 GET
   和 4 个表的行式读取：先用单列 `GETNEXT` 枚举行实例，再用一次多 OID `GET`
   取该行所需列，避开设备对跨表 `GETNEXT` 的慢响应。标准 Printer MIB 与已确认
   的 Kyocera OID 映射到同一个 `PrinterSnapshot`；原始 SNMP 明细保留在
   `snapshot.snmp`。
7. `cli.main()` 输出文本或 JSON；`--watch` 仅在变化时输出。
8. `--web` 为每台允许设备建立独立 `SnapshotCache`：`/api/status` 返回单设备
   快照，`/api/devices` 用最多 4 个线程并行读取所有已知设备；`/` 是总览页，
   `/device?host=<地址>` 是详情页。缓存默认 1 秒，同一设备的读取仍串行化。
   `POST /api/devices` 接受手动输入的主机并加入允许列表；启动时允许没有默认
   设备，此时页面先显示空状态，再由用户发现或手动添加。手动添加和发现结果
   都会原子写入用户设置中的 `saved_printers`，服务启动时自动恢复。
9. 配置工作台按官方对话框把 147 项对象拆成七个互斥分区。
   `GET /api/config/categories` 只返回导航元数据；`GET /api/config?category=`
   按当前设备 transport 选择读取路径：TCP 主机使用
   `collect_config_snmp(item_ids=...)`，`libusb:`/`/dev/` 设备使用
   `open_channel(device=...) + collect_config(item_ids=...)`，二者都只请求
   所选分区。USB selector 在 SNMP 入口会被提前拒绝，不能进入
   `getaddrinfo`。同一 USB 设备的状态、配置和 Wi-Fi 通道共用按 selector
   分配的 `RLock`，避免多个 Web 请求并发 claim Printer interface。PJL
   解析记录和 SNMP 记录都带相对/绝对 OID，配置视图不依赖 transport 猜测
   字段是否存在。单字段网络写入使用 SNMP SET，USB 写入使用官方
   `KSETOBJ ... VALUE =<integer>` 行；两者的旧值校验和 SET 后回读都只请求
   目标 item。USB 写入与其他状态/读取操作共用 selector 锁。基线保存/比较
   仍显式执行完整 147 项读取。读取层的
   超时/socket/结果异常统一转换为 `ConfigWorkbenchError`，HTTP 路由始终返回
   JSON 错误，不让 WebKit 只看到断连式 `TypeError: Load failed`。页面以分区
   卡片展示 27 个审核属性，完整配置只出现在基线维护区。Wi‑Fi 状态和连接配置
   位于 `wifi` 分区，专用 AP 扫描/连接操作仍走官方 `KGETOBJ/KSETOBJ` 顺序；
   扫描区不再重复显示设备设置摘要。
10. 设备详情页提交 `POST /api/scans` 后，`ScanJobManager` 在后台线程执行
   `preflight -> default_configuration -> open_session -> start_scan ->
   retrieve_image -> decode_raw -> export -> close_session`。同一设备已有
   扫描时返回忙状态。`GET /api/scans/<id>` 返回阶段和结果元数据，
   `GET /api/scans/<id>/files/<n>` 下载结果。任务只接受页面暴露的官方扫描
   token，并固定请求经过真机验证的 RAW 设备格式。
11. `kyocera_monitor.scan` 把设备请求格式和本地导出格式分开：RAW 经已还原的
   分带解码器转为 RGB，再输出 PNG/PDF/JPEG/TIFF/高压缩 PDF/XPS/BMP；
   RAW 保留为高级选项。PNG/PDF/BMP/RAW 使用标准库，JPEG/TIFF 及 JPEG
   内嵌 PDF/XPS 通过 Pillow 编码。Web 与 CLI 共用同一服务层。
12. `--gui` 在 `127.0.0.1` 的随机端口启动同一个 `create_server()`，由
   GTK3/WebKit2 窗口加载总览页；关闭窗口时停止本地服务。GTK/WebKit 是可选
   依赖，缺失时 CLI 返回退出码 2 并提示改用 `--web`。
13. Web/GUI 的语言偏好保存在用户设置中，取值为 `auto`、`zh-CN` 或
   `en-US`。`auto` 使用请求的 `Accept-Language`，按质量值匹配 `zh*` 或
   `en*`，其他语言回退 `zh-CN`；手动值优先于设备语言。页面初始 HTML 带有
   有效 locale 和翻译表，详情页、总览页和原生窗口标题共用同一结果。
   `POST /api/language` 只更新语言字段，不影响扫描目录、预设或设备列表。
14. `--discover` 并行执行 SNMP 广播和 WS-Discovery；广播只取型号 OID，随后用
   单播 GET 补全序列号/固件。ARP 表和可选的子网 CIDR 作为额外单播候选。
   Web 页面的 `/api/discover` 复用同一实现，并把发现的主机加入允许列表和
   持久化设备列表。
15. `--check-update` 或 Web/GUI 的“检查更新”按钮调用 `/api/update`，从固定
    `updater` Release 下载 `update.json`。版本号必须是稳定的
   `MAJOR.MINOR.PATCH`，按数值比较；发布页必须是 HTTPS。后端和页面各缓存
    60 秒，启动时不自动联网。GTK 只允许通过消息桥打开 GitHub HTTPS 链接。

USB 设备选择由 `usb.discover_usb_printers()` 完成：扫描 `/dev/usb/lp*`，从
`/sys/class/usbmisc/lpN/device` 向上读取 `idVendor`/`idProduct`，优先选择
MA2000w（`0482:0d51`），多个候选时要求显式 `--device`。

## 设计边界

- 不实现 Windows 打印后台、mailslot、注册表和 GUI；这些是平台适配层。
- 默认路径只发送只读查询；PJL `KSETOBJ`/`DINQUIRE` 和设备重置未实现。
- 配置基线以 `0600` 权限原子保存，使用规范化 JSON SHA-256 校验；比较前验证
  传输和目标，避免把一个设备的备份误用于另一个设备。快照可能包含敏感站点
  配置，因此不进入仓库。写入边界详见
  `docs/reverse-engineering/config-write-safety.md`。
- `--config-plan` 只生成审计用计划；item 2 `Auto error clear` 和 item 50
  `Quiet mode` 都能生成命令预览、回滚值和确认令牌。`--config-apply` 只接受
  这两个字段的 SNMPv2c `OFF -> ON -> OFF` 实验，scope 与字段必须匹配。
- `--config-apply` 要求相同计划、匹配的 SHA-256 确认令牌和 SNMPv2c。执行器
  在正向写入或回读失败时仍尝试回滚，并要求最终同 OID 回读为 `0`。
- `--config-candidates` 只评估 item 50 `Quiet mode` 的读取状态、类型和枚举，
  不直接生成写入计划或确认令牌；`write.allowed` 固定为 `false`。候选报告
  记录已核对的 `BM_GETCHECK → model +0x18 → OID → integer 0/1` 数据流、
  网络/USB 失败处理、未设置原厂重启请求标志，以及 MA2000w 的
  `OFF -> ON -> OFF` 写入回读结果；设备失败恢复和再次授权仍保留为 blockers。
- `--config-audit-safe` 只处理静态映射已审查的无害整数字段。每个字段都从
  同一私密基线和当前全表读取生成计划，执行改值、目标回读、恢复和原值回读；
  恢复失败立即停止。网络可达性、SNMP/Wi-Fi 凭据、传真身份、重置触发、字符串
  和未知语义对象不在白名单中。
- 不把 KGETOBJ 的数值无标记地解释成未经验证的业务字段；推断字段必须带
  `confidence` 标记，原始键值始终保留。
- Windows 原工具的网络路径使用 SNMP；Linux 实现优先使用已验证的 PJL 9100
  （响应更快、可直接读取私有 `1001.*` 对象），SNMP 作为等价的只读路径，
  默认 SNMPv1。两者不是同一条 Windows 传输链路，见
  `docs/reverse-engineering/clienttool-protocol.md`。
- SNMP 的 `prtMarkerLifeCount` 完整实例是
  `1.3.6.1.2.1.43.10.2.1.4.1.1`，MA2000w 返回 `129`；PJL
  `2.10.2.1.4.1.1` 也返回 `129`，两者共同确认 `lifetime_counter`。
  Client Tool 的网络监视也读取同一 SNMP 对象。SNMP 纸盒容量与 PJL 口径
  不同，不作为权威值。
- WSD 只发现打印服务，未发现扫描服务。网络 TWAIN 驱动使用 KM-WSDL
  （HTTP 9090/HTTPS 9091）；Linux 端已独立实现 SOAP 1.2 预检、扫描会话、
  XOP 多页取图、彩色/灰度 RAW 分带解调以及 PNG/PDF/JPEG/TIFF/高压缩
  PDF/XPS/BMP/RAW 本地导出。ADF/双面参数只使用官方枚举；MA2000w 无输稿器，
  跨机型硬件路径仍待验证。正式路径不加载官方 DLL。
- `retrieve_imageResponse/file_size` 在官方实现中只被反序列化和清零，未用于
  图像指针或长度计算；Linux 客户端不得把它当作传输总长。
- Windows Client Tool 的 USB 路径经打印后台 + Kyocera 语言监视器 mailslot
  转发 PJL，未直接打开 USB 设备；Linux 使用 `usblp` 发送同一 UEL 帧，属于
  原生等价实现。
- USB 原始帧是否与 TCP 完全一致仍是待验证假设；物理 USB 接入后再做完整对照。
- Web 界面默认绑定 `127.0.0.1`，没有认证；提供扫描、分区配置读取，以及
  九个已审核整数属性的单字段写入和回读恢复。完整配置只用于显式基线维护。
  `tools/kmscn_probe.py` 是独立的只读 KM-WSDL 协议探针；
  `tools/kmscn_scan.py` 只是包内扫描服务的兼容命令行适配器。
  多设备总览和手动添加主机已实现，主机列表与扫描预设、保存目录一起保存在
  `0600` 原子写入的用户设置中。
- 原生 GUI 是 Web 仪表盘的 GTK3/WebKit2 外壳，不复制状态解析逻辑；需要
  无界面运行或未安装 WebKit 时使用 `--web`。HTML 内的当前语言标题会同步到
  GTK 窗口标题，下载结果对话框使用同一有效语言。
- 设备发现只发送 SNMP GET 和 WS-Discovery Probe；子网扫描必须显式指定
  `--discover-subnet`，上限 /22，不使用端口扫描。
- 版本号只维护在 `pyproject.toml` 的 `[project].version`，格式为
  `MAJOR.MINOR.PATCH`；Debian 构建从该字段读取。普通提交和 PR 只运行测试，
  发布构建仅由匹配的 `vX.Y.Z` Git 标签触发，工作流在构建前验证标签一致性。
- 版本检查是显式网络操作，不参与状态/扫描启动路径；远端元数据只包含版本和
  发布页 URL，不下载或执行更新包，也不宣称自动升级能力。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 查询成功且状态正常 |
| 2 | 连接、超时或协议错误 |
| 3 | 查询成功但状态码不在原程序的正常集合，或 SNMP `hrDeviceStatus` 不是 running |
| 4 | `--expect-model` 不匹配 |
