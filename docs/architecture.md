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
  snmp.py      SNMP v1/v2c BER 编解码、GET/GETNEXT walk
  snmp_status.py  SNMP OID 到 PrinterSnapshot 的只读映射
  web.py       只读 HTTP 状态页、JSON API 与快照缓存
  gui.py       GTK3/WebKit2 原生窗口，内嵌同一个本地 Web 仪表盘
  cli.py       CLI、JSON、监视模式、退出码
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
   再建立一次新连接完整重试。
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
   设备，此时页面先显示空状态，再由用户发现或手动添加。
9. `--gui` 在 `127.0.0.1` 的随机端口启动同一个 `create_server()`，由
   GTK3/WebKit2 窗口加载总览页；关闭窗口时停止本地服务。GTK/WebKit 是可选
   依赖，缺失时 CLI 返回退出码 2 并提示改用 `--web`。
10. `--discover` 并行执行 SNMP 广播和 WS-Discovery；广播只取型号 OID，随后用
   单播 GET 补全序列号/固件。ARP 表和可选的子网 CIDR 作为额外单播候选。
   Web 页面的 `/api/discover` 复用同一实现，并把发现的主机加入允许列表。

USB 设备选择由 `usb.discover_usb_printers()` 完成：扫描 `/dev/usb/lp*`，从
`/sys/class/usbmisc/lpN/device` 向上读取 `idVendor`/`idProduct`，优先选择
MA2000w（`0482:0d51`），多个候选时要求显式 `--device`。

## 设计边界

- 不实现 Windows 打印后台、mailslot、注册表和 GUI；这些是平台适配层。
- 只发送只读查询；`KSETOBJ`/`DINQUIRE` 等写入能力未实现，避免误改设备配置。
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
- WSD 只发现打印服务，未发现扫描服务；Linux 扫描协议仍未确认。
- Windows Client Tool 的 USB 路径经打印后台 + Kyocera 语言监视器 mailslot
  转发 PJL，未直接打开 USB 设备；Linux 使用 `usblp` 发送同一 UEL 帧，属于
  原生等价实现。
- USB 原始帧是否与 TCP 完全一致仍是待验证假设；物理 USB 接入后再做完整对照。
- Web 界面只读，默认绑定 `127.0.0.1`，没有认证；不提供配置写入或扫描。
  多设备总览和手动添加主机已实现，主机允许列表只保存在当前进程内存中。
- 原生 GUI 是 Web 仪表盘的 GTK3/WebKit2 外壳，不复制状态解析逻辑；需要
  无界面运行或未安装 WebKit 时使用 `--web`。
- 设备发现只发送 SNMP GET 和 WS-Discovery Probe；子网扫描必须显式指定
  `--discover-subnet`，上限 /22，不使用端口扫描。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 查询成功且状态正常 |
| 2 | 连接、超时或协议错误 |
| 3 | 查询成功但状态码不在原程序的正常集合，或 SNMP `hrDeviceStatus` 不是 running |
| 4 | `--expect-model` 不匹配 |
