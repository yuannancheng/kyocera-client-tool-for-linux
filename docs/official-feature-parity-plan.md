# Official Client Tool 功能复刻计划

## 1. 目标与判定规则

本计划以已校验的 ClientTool 1.4.11.2 二进制、保存的反编译导出和真机证据
为依据，定义 Linux 替代工具需要复刻的用户功能。一个功能只有同时具备以下
条件才算完成：

1. 官方入口、调用链或设备协议已有可复现证据；
2. Linux 实现不加载或分发官方二进制；
3. CLI/UI 入口可由普通用户实际使用；
4. 有错误处理、自动测试和真机或受控协议样本；
5. 读取、写入、恢复及硬件限制被明确记录。

状态定义：

- `REPLICATED`：用户流程已经独立实现并通过真机验证。
- `PARTIAL`：协议或部分能力已实现，但用户入口、格式、错误处理或验证不完整。
- `STATIC_ONLY`：官方调用链/字段已还原，但 Linux 尚无可执行流程。
- `NOT_STARTED`：官方功能已确认，尚未实现。
- `BLOCKED`：依赖当前没有的硬件或样本。
- `NOT_CORE`：Windows/安装器/外部网页适配，不作为 Linux 核心功能。

进度以完整用户工作流计算，不以 OID、控件或提交数量计算。

## 2. 官方模块证据

| 模块 | 已确认职责 | 当前证据 |
| --- | --- | --- |
| `KMSTMVM.exe` | 状态监视、虚拟打印机、PJL 轮询、Windows 打印后台/语言监视器集成 | `program-structure.md`、`clienttool-protocol.md` |
| `KMSTMNET.exe` | 网络 SNMP 监视、状态文本合成、Print Box/Push Scan 结果 | 反编译调用链与 OID 表 |
| `KMSTMNW.exe` | 主设备管理 GUI、页签入口、启动配置/扫描/传真/维护工具 | `Show*` 启动函数、页面资源名与扫描调用链 |
| `KMUTLCFG.exe` | 147 项设备配置的 SNMP/USB 读写 | 控件/OID/真机写入证据 |
| `KMUTLPRE.exe` | Copy/Scan/Fax/Print Box 预设和 Quick Scan 设置 | 预设对象表与 `KMSCNSET` 调用 |
| `KMUTLMNT.exe` | 维护菜单解释器和 KPSL 请求 | 帧结构、request id、参数类型表 |
| `KMSCN*` | TWAIN、Quick Scan、Scan to Folder/Email/PDF/Push Scan | 网络 TWAIN/KM-WSDL 与组件入口 |
| `FAX/*` | 地址簿、传真配置和远程传真 | 地址簿导出与传真 OID 表 |
| `WIFI/wifisetup` | Wi-Fi 发现、连接、WPS/PIN 与设置 | .NET 元数据与 OID |
| `WFH/countermonitor` | 设备计数查看、导出和计划发送 | 托管程序结构与计数器 OID |
| `DataMasking.exe` | PDF 内容遮罩/脱敏 | 可选组件存在，行为尚未复刻 |

## 3. 功能覆盖矩阵

| ID | 官方用户功能 | 证据 | Linux 当前状态 | 优先级 | 完成标准 |
| --- | --- | --- | --- | --- | --- |
| F01 | 发现并选择打印机 | `KMSTMVM` 枚举 Windows 打印队列；项目另有 SNMP/WSD | `REPLICATED` | 已完成 | 网络发现、手动添加与多设备选择可用 |
| F02 | 实时设备状态 | 型号、固件、网络、耗材、纸盒、告警、面板和计数 OID | `REPLICATED` | P1 | 所有适用状态有稳定字段，并能在 GUI 刷新 |
| F03 | 作业/日志状态 | `USTATUS JOB`、`JobSnmpOid.xml` | `PARTIAL` | P2 | 作业树非空的机型可列出作业和日志；MA2000w 保持明确不可用 |
| F04 | 状态通知/托盘提示 | `KMSTMNW` 系统托盘、告警和打印机状态回调 | `REPLICATED` | P1 | 有可关闭的本地通知策略，不依赖 Windows 托盘 |
| F05 | 设备配置读取 | 147 项对象表、SNMP/USB 两条路径 | `REPLICATED` | 已完成 | 全量读取、基线、差异和脱敏保存可用 |
| F06 | 设备配置写入 | 字段差异、SET/KSETOBJ、回读/恢复 | `REPLICATED` | P1 | 安全字段有 GUI，危险字段分级并明确确认 |
| F07 | 网络/SNMP/trap 配置 | Communication、trap 页面和对象 | `PARTIAL` | P2 | 只读完整；写入具备断线恢复和逐字段回滚 |
| F08 | 面板/Wi-Fi 状态 | Panel options、Wi-Fi 状态页 OID | `REPLICATED` | P1 | 状态和可安全修改项进入统一设置页 |
| F09 | Wi-Fi AP 扫描/连接/WPS | `WifiSetupTool*`、AP/设置/WPS OID | `STATIC_ONLY` | P2 | 支持扫描 AP、连接和恢复，失败不丢失旧配置 |
| F10 | 设备重启/恢复出厂 | reset/restore OID 和官方菜单入口 | `STATIC_ONLY` | P3 | 有独立危险操作确认、断线恢复和重新发现流程 |
| F11 | 维护菜单 | `KMUTLMNT`、KPSL、39 条 request 定义 | `STATIC_ONLY` | P3 | 先实现只读诊断；破坏性请求逐项真机验证 |
| F12 | 固件升级 | `ShowFirmwareUpgrade` 入口及语言资源；升级主体不全 | `STATIC_ONLY` | P3 | 官方升级文件和校验行为确认后才实现 |
| F13 | 扫描图像采集 | TWAIN/KM-WSDL、会话、取图、RAW 解码 | `REPLICATED` | 已完成 | Web 主程序和 CLI 完成彩色/灰度扫描并输出可用文件 |
| F14 | 设备格式与本地导出 | 官方格式枚举、`file_type`、RAW 分带 | `REPLICATED` | 已完成 | 设备请求与本地 PNG/PDF/JPEG/TIFF/高压缩 PDF/XPS/BMP/RAW 分离 |
| F15 | 扫描参数界面 | 颜色、分辨率、尺寸、原稿类型、单双面、ADF、连续扫描 | `PARTIAL` | P0 | Web/GUI 参数完整，默认值来自设备，能力不足时禁用 |
| F16 | Scan to Folder | `KMSCNFOL`、地址簿/文件名/保存路径字段 | `REPLICATED` | P1 | 扫描后按预设命名保存到用户选择目录 |
| F17 | Scan to PDF | `KMSCNPDF`、HCPDF、PDF 输出字段 | `REPLICATED` | 已完成 | RAW 解码后生成 PDF/高压缩 PDF，并保留原始 RAW 选项 |
| F18 | Scan to Email | `KMSCNEML`、本机邮件集成 | `NOT_STARTED` | P2 | 生成附件并调用用户选择的邮件客户端；无凭据内置 |
| F19 | Quick Scan 预设 | `KMUTLPRE`、`1001.1.*`、`QUICKSCN.ini` | `REPLICATED` | P1 | 可读取、编辑、保存扫描预设并用于新扫描 |
| F20 | Push Scan | `OnRecvPushScan`、`KMSCNPUS`、结果 OID | `PARTIAL` | P2 | Linux 监听设备请求，执行指定预设并回写结果 |
| F21 | Print Box 远程操作 | `1001.3.*`、结果/PIN/地址语义 | `STATIC_ONLY` | P2 | 支持读取和已确认的操作，不暴露未知 PIN 行为 |
| F22 | Counter Monitor | `CounterMonitor.exe`、打印/扫描计数和导出 | `REPLICATED` | P1 | 多设备计数、CSV/表格导出和失败重试可用 |
| F23 | 计数器计划发送 | `CounterFileSending`、Quartz、server/folder settings | `STATIC_ONLY` | P3 | 明确本地文件或服务器协议后再实现；先不做后台上传 |
| F24 | FAX 地址簿 | `KMADRBK.exe`、个人/组/限制号码接口 | `BLOCKED` | P3 | 在带传真选件的设备上验证读取、写入和导入 |
| F25 | FAX 偏好/远程传真 | `ShowFaxPreferences`、远程传真组件、45.* OID | `BLOCKED` | P3 | 硬件可用后复刻；MA2000w 不提供 |
| F26 | SNMPv3 | `KMSTMNET` 注册表认证/加密设置 | `NOT_STARTED` | P2 | 支持 noAuth/authPriv、错误提示和凭据安全存储 |
| F27 | USB 设备路径 | Windows mailslot→Linux `usblp` 等价实现 | `PARTIAL` | BLOCKED | 物理 USB 设备测通状态、扫描、断线重连和睡眠唤醒 |
| F28 | 错误/帮助/外部链接 | 帮助、驱动下载、FAQ、耗材购买入口 | `NOT_CORE` | P4 | 只提供项目自己的帮助与安全链接，不复刻厂商网页流程 |
| F29 | 打印首选项/属性 | Windows 打印驱动与 shell 集成 | `NOT_CORE` | P4 | 交给 Linux 打印队列/CUPS，不在 GUI 内伪造 |
| F30 | Content Redactor | `ShowContentRedactor`、`DataMasking.exe` | `NOT_STARTED` | P4 | 先逆向 PDF 遮罩规则和输出证据，再决定是否实现 |

## 4. 重点任务与交付顺序

### 阶段 E1：扫描产品闭环（P0，已完成）

状态：`DONE`（2026-11-01）。MA2000w 真机完成彩色 PNG、PDF、JPEG；
Web 单进程任务、阶段反馈和下载已通过实际 API 扫描验证。

交付：

1. 将 `tools/kmscn_scan.py` 的编排提取到 Python 包内服务层；
2. 将设备请求格式和本地导出格式解耦；
3. MA2000w RAW 解码后默认导出 PNG/PDF，RAW 保留为高级选项；
4. Web/GUI 提供颜色、分辨率、原稿类型、页数和输出格式；
5. 显示预检、扫描、取图、解码和关闭会话阶段，错误可操作；
6. MA2000w 真机完成一次彩色 PNG/PDF 扫描。

验收：单进程启动 GUI 或 Web，选择已发现设备，点击扫描，得到可打开的
PNG/PDF，不运行仓库内独立脚本。该阶段完成前不扩展维护、传真或更多配置。

### 阶段 E2：核心设备管理（P1）

状态：`DONE`（2026-11-01）。状态通知、多设备计数 CSV、扫描预设、目录保存、
统一配置基线/差异、九个已审核整数属性写入和面板/Wi‑Fi 状态均已进入同一
设备页。令牌化 `OFF -> ON -> OFF` 回滚实验仍是 CLI 研究工具，不进入正式
Web/GUI。MA2000w 真机完成预设驱动灰度 HCPDF 自动落盘，HTTP 下载与落盘
字节一致；147 项读取、私有基线、item 2/50 写入恢复和 25 项无害整数审计
已验证。新增页面写入编排已由自动测试覆盖，尚未在 MA2000w 页面点击复测。

交付：

1. 状态页补齐适用字段和通知策略；
2. 配置读取与差异检查统一到 GUI；九个已审核整数属性可写入，回滚实验保持
   CLI 隔离；
3. Quick Scan 预设可读、可编辑并用于扫描；
4. Scan to Folder/PDF 使用预设；
5. Counter Monitor 支持多设备计数与导出。

验收：状态、扫描、预设、计数、配置读取/基线/差异及已审核属性写入均可从
统一设备页面操作；令牌化回滚实验不进入正式页面。

### 阶段 E3：设备驱动工作流（P2）

进度（2026-11-01）：Push Scan 已增加只读状态探针和统一设备页入口，读取
接口、IPv4/IPv6/主机名目标、地址类型及上次结果；MA2000w 实测当前目标为
USB，明确显示网络未就绪。静态与真实表项验证确认触发码为
`89000 + preset`，`--push-scan-listen` 只读轮询厂商告警状态列。本地预设可
显式绑定设备槽位 `0–30`；`--push-scan-run` 会通过普通扫描任务执行匹配预设，
未映射或忙碌时不执行。真实网络触发和结果回写仍未闭环，因此 F20 保持
`PARTIAL`。

交付：

1. Push Scan 通知与预设执行；
2. Print Box 已确认操作；
3. Wi-Fi AP 扫描/连接/WPS；
4. SNMPv3；
5. 作业/日志读取及不可用状态处理。

验收：每个功能先有官方路径证据，再有真机结果；没有硬件或样本时保持
`BLOCKED`，不以模拟测试宣称兼容。

### 阶段 E4：维护与高风险操作（P3）

维护菜单、重启、恢复出厂、固件升级、传真和计划发送。先做只读诊断，
再逐项验证破坏性请求；禁止批量试探。

### 阶段 E5：可选/平台专用（P4）

内容遮罩、打印首选项、帮助网页和耗材购买等。不得挤占 E1/E2。

## 5. 不再采用的工作方式

- 不再按 OID 数量、控件数量或单独测试数量衡量核心进度；
- 不再为每个中间步骤单独提交；一个端到端功能通常合并为 1–3 个提交；
- 不重复分析已有保存导出，除非二进制哈希变化或证据缺口明确；
- 不在没有用户入口的情况下继续扩大协议覆盖；
- 不在硬件阻塞项上消耗主线时间。
