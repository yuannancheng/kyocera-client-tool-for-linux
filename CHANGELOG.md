# CHANGELOG

## 2026-11-08

### Fixed — USB PJL transient no-response recovery and v0.3.4

- 修复自动 USB 设备首次查询完全没有 PJL 响应时异常直接冒泡的问题。旧实现
  只在连接成功但响应不完整时重开通道；现在 `collect()` 会在无响应错误后关闭
  并重新打开同一 USB 通道，再按原查询序列重试一次。该行为对应官方本地 USB
  路径的定时重连证据，不改变 UEL/PJL 帧或任何设备状态。
- 新增“首次无响应、重开后成功”的回归测试。全量测试 391/391 通过；修复后的
  仓库代码在 MA2000w 物理 USB 上返回型号、状态、耗材、纸盒、计数和网络信息。
- 版本升级为 `0.3.4`。尚不能证明所有 `printer returned no PJL response`
  都由瞬时端点停顿引起；若重开后仍连续无响应，仍按设备唤醒、USB 重枚举或
  其他传输故障排查。

### Docs — bilingual, task-oriented README

- 根目录 `README.md` 继续作为默认简体中文入口，并新增完整英文版本
  `README.en.md`；两份文档顶部互相链接。
- README 从长篇研究记录整理为安装、快速开始、Web/GUI、扫描、配置、USB/Wi-Fi、
  多语言、版本检查、发布流程、测试、研究资料和安全边界等产品导向章节；详细
  协议证据继续保留在 `docs/reverse-engineering/`。
- 英文 README 加入 Python sdist 清单和 Debian 文档目录，安装包同时携带中英文
  说明。
- 验证：全量测试 390/390 通过，新增 README 入口和语言互链测试。

### Fixed — update-check API fallback and v0.3.3

- `v0.3.2` 发布成功且 `updater/update.json` 可经 GitHub API 读取，但当前网络
  区域访问 GitHub Release 下载域持续返回 HTTP 504。版本检查现在先读取固定
  `update.json`，失败后回退到 GitHub Releases API 的 latest release 元数据。
- API 回退仍要求稳定版本标签、非 draft/prerelease、HTTPS 发布链接，并沿用
  16 KiB 响应上限、双端 60 秒缓存和手动触发边界。
- 版本升级为 `0.3.3`。验证：全量测试 389/389 通过，新增下载域失败后 API
  回退测试；GitHub Test（Python 3.10/3.12）与 Release workflow 均成功，发布
  wheel、sdist、Debian 包和指向 `v0.3.3` 的 updater 元数据；真实
  `--check-update` 返回当前/最新均为 `0.3.3`。`v0.3.2` 保持已发布状态，
  不重写历史标签。

### Fixed — clean-checkout release CI and v0.3.2

- GitHub `Test` 在推送 `v0.3.1` 标签后发现，部分 Client Tool 研究测试直接读取
  被 Git 忽略的 `Kyocera/ClientTool` 样本；本地有样本时通过，干净 runner 中
  因文件不存在而失败。`v0.3.1` 标签保留原提交，没有创建对应 Release。
- 配置名称、对话框、FAX、Job OID、OID 来源清单和 UI 字符串测试现在各自检查
  所需样本；样本缺失时跳过依赖原厂文件的回归，但仍运行基于已提交 TSV、
  生成模块和解析器的可移植检查。
- Release workflow 新增显式 `workflow_dispatch` 和 `release_tag` 输入；
  如果标签推送事件未生成运行，可对既有 `vX.Y.Z` 标签手动触发同一构建。
- 版本升级为 `0.3.2`。验证：本地全量测试 388/388；去掉 `Kyocera/`、`analysis/`
  和 `.tools/` 的干净副本中，所有剩余测试通过，样本相关测试按预期跳过。

### Added — manual semantic-version update check

- Web 总览页和设备详情页顶部新增“检查更新”。当前版本来自安装元数据、源码
  `pyproject.toml` 或 Debian 包内生成版本文件；点击后才访问固定的 `update.json`，
  不会在启动、设备轮询或扫描流程中自动联网。
- 新增 `kyocera_monitor.updates`：校验版本、HTTPS 发布链接和 16 KiB 响应上限，
  按 `MAJOR.MINOR.PATCH` 数值比较。前后端各缓存 60 秒；
  更新元数据格式错误或网络失败时只返回检查失败，不影响打印和扫描。
- 发现新版本时显示当前版本、最新版本和发布页链接。普通浏览器打开新标签页；
  GTK/WebKit 通过受限消息桥只允许打开 `github.com` 的 HTTPS 链接。
- 新增 `--check-update` 与 `--check-update --json`，并支持
  `KYOCERA_UPDATE_URL` 指向兼容镜像。
- 发布 workflow 在主 Release 完成后写入固定 `updater` Release 的
  `update.json`，内容为 `{"version":"x.y.z","htmlUrl":"..."}`；随后恢复语义
  版本 Release 为 GitHub 最新版本。
- Debian 构建会生成 `kyocera_monitor/_build_version.py`，使手工打包安装后也能
  显示真实版本，不依赖 wheel 的 `.dist-info`。

验证：全量测试 388/388 通过；覆盖版本数值比较、当前版本解析、元数据伪造/
超限/非 HTTPS 拒绝、缓存与强制刷新、Web API、CLI、GTK 外链限制、翻译键和
发布 workflow。页面 JavaScript、Python 编译、工作流 YAML、公开树检查和
`git diff --check` 通过。未连接打印机；当前尚无已发布的 `updater` 元数据，
因此真实远端检查需在首次标签发布后验收。

### Added — bilingual Web/GUI interface

- Web 总览页和设备详情页新增“自动（设备语言） / 简体中文 / English”选择。
  `auto` 按浏览器或 WebKit 请求的 `Accept-Language` 质量顺序匹配 `zh*` 和
  `en*`，不支持的语言回退简体中文；手动选择优先并持久化到用户设置。
- 新增 `POST /api/language`，只更新 `language` 字段，不覆盖扫描目录、预设和
  已保存设备；旧设置缺少该字段时保持兼容并解析为 `auto`。
- 页面静态文字、动态状态、扫描/配置/Wi‑Fi/Push Scan 提示、后端配置标签和
  Push Scan 状态均有英文翻译；GTK 窗口标题与下载结果对话框跟随有效语言。
- 新增语言协商、设置迁移、API、翻译键完整性和页面控件测试。

### Changed — release-only GitHub Actions builds

- 普通 `main` 推送和拉取请求只运行 Python 3.10/3.12 测试与公开树检查，
  不再为每次小变动生成 wheel、源码包或 `.deb`。
- 新增 `release.yml`：只有推送 `vX.Y.Z` 标签时才校验标签与
  `pyproject.toml` 版本一致，运行发布测试，构建三类产物，上传 Actions
  artifact，并创建或更新 GitHub Release。
- 新增 `tools/release.py`，提供 `version`、`check --tag` 和
  `bump major|minor|patch`；版本号继续以 `pyproject.toml` 为唯一来源，
  Debian 包版本自动从该字段读取。

验证：全量测试 371/371 通过；Python 编译、两页 JavaScript 语法、工作流 YAML、
公开树检查和 `git diff --check` 通过。尚未在真实 GitHub runner 上执行发布
标签流程，也未连接打印机；本环境只验证了本地 wheel 和 `.deb` 构建。

### Fixed — reviewed device properties on USB

- USB/PJL 连接不再把同一组 27 个已审核整数属性整体标记为只读。写入使用
  官方配置工具已还原的 `@PJL KSETOBJ OBJ="1.<relative-oid>" VALUE =<int>`
  行，并要求设备返回 `STATUS=0`；随后沿用目标 item 回读和失败恢复保护。
- USB 写入与状态查询、分区读取和 Wi‑Fi 通道共用每个 selector 的访问锁，
  避免写入期间另一个请求 claim 同一 Printer interface。
- 对 MA2000w 的 27 个已审核字段重新执行只读核对，27/27 均为
  `status=0`、`value_kind=integer`；sleep time 当前为 `1`。本轮没有发送
  配置写入，USB 字段级真机写入仍待设备接入后验收。
- 版本升级为 `0.3.1`，使桌面安装包可与仍使用旧配置页的 `0.3.0-1` 明确区分。

### Changed — friendly official device configuration and tray labels

- 设备配置页不再列出设备返回 `STATUS!=0` 或缺失的不可读对象，只在技术详情
  摘要中保留隐藏数量；不可读的可写属性也不会显示成禁用编辑卡。
- 纸张尺寸、介质类型和纸张重量改用官方 Client Tool 1.4.11.2 枚举，而不是
  `设备值 11` 一类占位文案。新增可复现工具
  `tools/clienttool_media_values.py`，校验 `KMUTLCFG.exe` 与简体中文资源 DLL
  的 SHA-256 后从 `0x00497458`、`0x00497c68` 表提取映射。
- “介质/纸张”相关对象重新归入“纸张与介质”分区；普通可读设置使用只读卡片
  展示，原始 OID 表移到折叠的技术详情中。
- PJL 纸盒解析保留 `INFO CONFIG` 的 `NAME` 列，并与
  `INFO KINTRAYSTATUS` 的 `INTRAYn` 标识合并。界面显示“主纸盒”“手送纸盒”
  或“纸盒 n”，介质显示“A4 · 普通纸”，`UNKNOWN` 被替换为破折号。
- 扫描颜色、分辨率和原稿类型未指定时改称“使用设备当前设置”，避免把省略值
  显示成含糊的“设备默认”。
- 验证：全量测试 348/348 通过；官方映射提取结果与公开 TSV 逐字一致；
  页面 JavaScript 语法、Python 编译、公开树检查和 `git diff --check` 通过。
  当前环境无浏览器宿主且本地服务监听被沙盒拒绝，未完成人工截图验收；本轮
  未连接 MA2000w，也未执行设备写入。

### Changed — unified Wi-Fi and device configuration UI

- 设备页将独立的“Wi‑Fi 状态与配置”卡片合并到“设备配置 → Wi‑Fi”分区；
  连接状态、SSID、安全模式、信号和信道随分区读取展示，AP 扫描与连接使用
  同一分区内的专用官方 `KGETOBJ/KSETOBJ` 流程。
- 移除扫描区下方重复的“设备设置”摘要。该摘要把配置页已有的
  `Auto error clear` 和 `Form feed timeout` 再以英文对象名显示，既重复又与
  页面中文文案不一致；分区状态改用中文标签，技术详情仍保留官方对象名。
- 在已有 9 个属性编辑器基础上，开放无危害整数审计中已确认可写并可恢复的
  item 10 与 17 个介质重量行，共 27 个可修改整数属性。介质重量只允许
  MA2000w 已审计的设备值 `11/12/13`，不根据猜测扩展枚举名称或取值范围。
- 网络分区的可修改属性卡片会替换重复的只读状态卡；USB/PJL 通用写入仍保持
  只读，并明确说明 Wi‑Fi 专用连接流程不受该限制。
- 验证：全量测试 343/343 通过；页面 JavaScript 语法、Python 编译和
  `git diff --check` 通过。本轮未连接 MA2000w，未执行设备写入或 Wi‑Fi 切换。

### Fixed — configuration read errors and section action layout

- 修复 USB 配置读取与页面状态刷新并发占用同一 Printer interface 导致的
  `PjlError: claim USB printer interface: busy`。Web/GUI 现在为每个 USB
  设备共享一把访问锁，状态、分区配置和 Wi-Fi 操作都必须串行打开 USB 通道。
- 修复 USB/PJL 配置记录缺少 `absolute_oid` 导致的
  `KeyError: 'absolute_oid'`。PJL 解析记录现在直接包含由相对 OID 展开的
  absolute OID，配置视图和写入保护也保留兼容回退。
- 修复 USB 设备配置读取被错误发送到 SNMP 的根本原因：自动发现的设备使用
  `libusb:bus:address` 标识，SNMP 名称解析因此返回
  `gaierror: [Errno -2]`。Web/GUI 配置读取现按目标分派，USB/PJL 设备通过
  `open_channel(device=...) + collect_config()` 读取，TCP 主机才使用 SNMP。
- 显式 `--usb` 或自动 USB 设备也会创建配置工作台；USB 分区读取只发送所选项的
  `KGETOBJ`，完整基线仍可按需读取 147 项。USB 配置写入在页面明确标记为
  不可用，不会切换到未验证通道。
- `collect_config_snmp()` 在任何名称解析前拒绝 `libusb:` 和 `/dev/` selector，
  防止其他调用方再次把 USB 标识交给 `getaddrinfo`。
- 修复分区配置读取在 SNMP 超时、socket 异常或结果异常时直接中断 HTTP
  连接的问题。工作台现在统一包装读取错误，配置路由也会返回 JSON 502，
  WebKit 不再只显示底层 `TypeError: Load failed`。
- 前端配置请求区分后台连接失败、非 JSON 响应和设备错误；连接失败提示
  “无法连接本机后台服务”，合法 JSON 错误则保留具体原因。
- “读取此分区”所在标题区改为 `minmax(0, 1fr) max-content` 两列网格，
  按钮固定右对齐且不换行，长标题和说明只会挤压左侧文本列。
- 验证：全量测试 339/339 通过；页面 JavaScript、公开树检查和
  `git diff --check` 通过。

### Changed — GUI configuration workflow and toast feedback

- Web/GUI 顶部的常驻错误栏改为固定定位的 toast 弹出层，错误、成功和普通
  提示使用不同对比度；相同错误不会在自动刷新时连续堆叠。概览页和设备页同步。
- 147 项配置按官方主默认值、Communication、SNMP Trap、Panel options、
  Wi‑Fi 及传真相关页面拆成七个分区。切换分区时只读取该分区的对象，不再默认
  读取整表。
- 九个已审核写入属性改为分区内的独立设置卡片，显示说明、当前值、单位和
  枚举选项；只有值发生变化时才能提交。带 5 秒缩放的时间属性直接在界面输入
  秒数，提交时还原为设备整数。
- 单字段写入的旧值校验、SET 后回读和失败恢复现在只读取目标 item；完整
  147 项读取只保留在用户明确展开的基线保存、基线比较等维护操作中。
- 新增 `/api/config/categories` 和 `GET /api/config?category=<key>`；分区
  覆盖 147 项且每项只属于一个分区，非法分区 fail closed。
- 验证：全量测试 330/330 通过；Python 编译、页面 JavaScript 语法和
  `git diff --check` 通过。当前环境没有可用浏览器宿主或图形桌面，因此未完成
  人工浏览器截图验收。

### Added — physical USB, Wi-Fi setup and Linux driver integration

- USB 状态路径完成 MA2000w 真机验证。用户无 `lp` 组权限时，新增纯 `ctypes`
  libusb Printer-class 回退；它自动分离并恢复 `usblp`，发送相同的 UEL/PJL，
  Linux 不依赖 Windows mailslot、语言监视器或官方 DLL。
- 新增 Wi-Fi 状态、AP 扫描和连接协议实现，来自官方 Wi-Fi Setup Tool 的
  `KGETOBJ/KSETOBJ` 顺序。AP 扫描、安全模式、信道和 RSSI 已在 USB 与 TCP
  9100 两条真机路径验证；连接写入按 SSID、security、BSSID、WEP、PSK 顺序
  执行并回读状态。
- Web/GUI 设备页新增 Wi-Fi 状态、扫描结果选择、手动 SSID、安全模式和密码
  输入；连接需要显式确认。密码只存在于单次请求，不持久化，写 API 只接受
  回环客户端。默认 GUI/Web 在没有网络目标时自动枚举 USB 打印机，因此可在
  Wi-Fi 尚未配置、设备没有 IP 地址时通过 USB 完成首次 Wi-Fi 配置。
- 逆向社会 `KMUSBSCN3.dll` 的 Windows `usbscan.sys` 调用，恢复
  `IOCTL_SEND_USB_REQUEST` 到 Linux vendor control transfer 的映射；真机
  验证 scanner interface 的 connect、machine-info、version 和 disconnect。
  `--usb-scan-info` 可独立执行该只读诊断握手；control 响应现在校验命令码和
  成功状态，打开失败会释放 libusb 资源。另从 `Ns1815TW3.dll` 与
  `KMUSBSCN3.dll` 恢复 20-DWORD 扫描参数和 `0x81` ScanReq、`0x82` PageData、
  `0x83` JobEnd、6 字节 ACK 状态，并加入实验性 `--usb-scan-capture` 单页捕获
  和合成分帧测试；真机 ACK/RAW 流验证前，图像取回不能标记为已完成。
- 新增 Debian 包内的 Kyocera USB `uaccess` udev 规则和打印队列安装辅助
  脚本。当前机器已验证 `kyodialog 10.1-0`、`MA2000w-2` USB CUPS 队列和
  `usb://Kyocera/MA2000w?serial=...` 设备 URI；辅助脚本默认 dry-run，
  同名队列指向其他 URI 时拒绝覆盖，只有 `--force` 才更新。包依赖补充
  `libusb-1.0-0` 和 `cups-client`，辅助入口直接作为可执行文件安装。
- 版本升级为 `0.3.0`；构建 `dist/kyocera-monitor_0.3.0-1_all.deb`，
  SHA-256 `c9fb3afbac63351455e3af44aac34c34caa6668da950ede6f2ba7dfa0bcc7a39`；
  使用相同 `SOURCE_DATE_EPOCH` 两次构建逐字节一致。
- 通过 `pkexec` 将系统包从 `0.2.6-1` 升级为 `0.3.0-1`；CUPS `MA2000w-2`
  USB 队列重新启用，当前为 idle/enabled/accepting。设备已从 USB 总线消失，
  因此尚未验证实际打印输出。
- 全量测试 323/323 通过，公开树检查、`compileall`、页面 JavaScript、
  udev 规则和 `git diff --check` 通过。

## 2026-11-01

### Added — reviewed device property editing

- Web/GUI 设备页新增九个已审核整数属性编辑器：睡眠时间、自动错误清除、
  自动错误清除超时、打印浓度、静音模式、长度单位、送纸超时、面板自动清除
  和面板清除时间。此前页面只有读取、基线和差异按钮，无法设置任何属性。
- 新增 `POST /api/config/apply`。请求必须携带页面观察到的当前值、目标值、
  已审核 item id 和 `confirm=true`；旧值变化时 fail closed，SET 后重新读取
  同一 OID，写入或回读失败时尝试恢复旧值。
- 写入范围限定为官方控件/差异表已有映射且经过 MA2000w 单字段或 25 项无害
  整数审计的字段；网络、SNMP 凭据、Wi‑Fi、传真、字符串、重置和未知字段
  保持只读。`/api/config/plan` 与 CLI 令牌化回滚实验仍不进入正式页面。
- Push Scan 页面明确区分设备目标与本地槽位：官方 Client Tool 仅读取
  `1001.4.1.1/2/4/5/6.0`，没有可复现 SET 路径，因此不会盲写设备接口或目标；
  可设置项只表示 `89xxx` 到本地扫描预设的映射。
- 新增配置编辑 API、旧值冲突、回读失败恢复和确认要求测试；版本升级为
  `0.2.6`。

### Added — mapped Push Scan preset execution

- 本地扫描预设新增可选 `push_scan_slot`（`0–30`）绑定，对应官方
  `KMQSEnablePreset` 接受的 Quick Scan 槽位；重复槽位、越界值和错误类型在
  设置载入时拒绝，旧预设保持未绑定。
- Web/GUI 设备页的预设编辑区可设置并显示 Push Scan 槽位。绑定是 Linux 产品
  层的显式映射，不宣称与 Windows 预设内容等价。
- CLI 新增 `--push-scan-run`，必须与 `--push-scan-listen` 同时使用。观察到
  `89xxx` 后，监听器通过现有 `ScanJobManager` 执行槽位匹配的本地预设，继承
  单设备忙保护、扫描阶段、格式导出和配置目录自动保存。执行前重新读取目标，
  只在目标仍匹配本机且状态为 `ready` 时继续，避免为发往其他主机的请求启动扫描。
- 未绑定槽位返回 `unmapped`，设备忙返回 `busy`，测试映射不会启动扫描；
  JSON 事件记录本地任务 ID、阶段和落盘结果。
- 原始字符串字节确认 Push Scan 结果码为 `0=OK`、`1=NG`，修正协议文档中的
  冲突。仍未找到扫描应用决定成功/失败并触发结果写入的上游调用方，因此
  `1001.4.1.3.0` 自动回写继续禁用。
- 尚未取得真实网络 Push Scan 触发；本次不能据此宣称 F20 硬件闭环完成。
- 版本升级为 `0.2.5`。

### Added — Push Scan trigger detection

- 通过原始指令和反编译复核确认 Push Scan 触发码为 `89000–89999`，预设号为
  `CODE - 89000`；`KMSTMNW.exe!FUN_0044fac0` 在 `0x0044fc45` 执行减法并写入
  `OnRecvPushScan` 使用的对象偏移。
- 确认网络 Client Tool 从厂商告警文本列
  `1.3.6.1.4.1.1347.43.18.2.1.3` 读取状态码；MA2000w 真机该列返回
  `OctetString: 35078`。
- CLI 新增 `--push-scan-listen`、`--push-scan-poll-interval` 和
  `--push-scan-max-polls`。监听器使用只读 SNMP GETNEXT，只在首个状态码改变
  并进入 `89xxx` 时产生事件；相同状态不重复触发。
- JSON 事件包含设备、状态码、预设号、官方 0–30 范围判断和执行限制；不发送
  PJL `USTATUS=ON`、不启动本地预设、不回写结果 OID。
- MA2000w 两次真机轮询均为 `35078`，无虚假事件。版本升级为 `0.2.4`；
  构建并安装 `dist/kyocera-monitor_0.2.4-1_all.deb`，SHA-256
  `61935edadf40ea526fe8a36bc25dfce869175a8105d7a8a385778cfa6b60ece7`。

### Added — read-only Push Scan readiness

- 新增 `kyocera_monitor.push_scan` 和 `--push-scan`，通过一次 SNMP GET 读取
  官方已确认的接口、IPv4/IPv6/主机名目标、地址类型及上次结果对象。
- 就绪判断区分 USB 目标、网络目标未配置、目标匹配本机、目标属于其他主机和
  无法验证等状态；IPv6 使用 16 字节地址转换，主机名比较不区分大小写。
- Web/GUI 设备详情页新增“Push Scan 就绪状态”只读区域和
  `/api/push-scan`；不接收设备触发、不执行预设、不回写结果 OID。
- MA2000w 真机只读结果：接口 `USB`、IPv4 目标 `0.0.0.0`、地址类型 `IPv4`、
  主机名为空、上次结果 `OK`，IPv6 对象返回 `NoSuchObject`；页面状态为
  `usb_destination`，明确不是网络就绪。
- 官方 `OnRecvPushScan` 的预设号来源（对象偏移 `+0x2e810`）、设备触发时序和
  Linux 结果回写仍未知；功能状态从 `STATIC_ONLY` 调整为 `PARTIAL`。
- 新增 11 个 Push Scan 专项测试；版本升级为 `0.2.3`。
- 构建并安装 `dist/kyocera-monitor_0.2.3-1_all.deb`，SHA-256
  `f7d8377b0f449071c31f39de6ef62ec9db36e46d8d0c7d8e8214008de550cc53`；
  已安装入口和回环 Web API 均完成 MA2000w 只读验证。

### Fixed — remove development configuration experiments from GUI

- 从正式 Web/GUI 移除“安全回滚实验”整块开发测试控件、写权限列、计划/授权/
  执行按钮和对应 JavaScript。
- Web 服务不再注册 `/api/config/plan` 与 `/api/config/apply`；正式界面只保留
  147 项配置只读采集、敏感值隐藏、`0600` 私有基线和差异比较。
- `ConfigWorkbench` 改为纯只读组件，不再持有 SNMP 写入客户端工厂；受控
  item 2/50 实验继续只通过显式 CLI 工作流提供。
- 新增页面与 API 回归测试，断言正式 GUI/API 中不存在实验入口；版本升级为
  `0.2.2`。
- 构建并安装 `dist/kyocera-monitor_0.2.2-1_all.deb`，SHA-256
  `f6d0cfdbf0a8c62669c297eb61f902e60980c02638a2dab3b84886e60411448b`；
  已安装页面只保留读取、基线和比较按钮，两条开发写入 API 均实际返回 `404`。

### Fixed — dark status contrast and persistent printers

- 修复总览页“0 台设备”、加载状态和详情页等待状态在深色主题下继承浅色
  背景与浅色文字、导致对比度不足的问题。中性、正常和警告标签现在分别为
  浅色/深色主题定义明确的前景色和背景色。
- 手动添加和发现得到的打印机现在写入
  `$XDG_CONFIG_HOME/kyocera-monitor/settings.json` 的 `saved_printers`；
  Web/GUI 下次启动时自动恢复，不再要求每次重新发现。旧版设置文件缺少该字段
  时按空列表兼容加载。
- 保存扫描目录或预设不会清空已保存设备列表；设备列表更新使用设置锁内读取、
  修改和原子替换，保留 `0600` 权限。
- 新增旧设置兼容、主机名/`IPv4` 校验、重启恢复、发现持久化和设置交叉保存
  回归测试；版本升级为 `0.2.1`。
- 构建并安装 `dist/kyocera-monitor_0.2.1-1_all.deb`，SHA-256
  `e2a1b29cfb653124769085188800fa9fdda695ae8eeaa1fbf4618066cbf6a036`；
  使用无界面 Chrome 在强制深色模式下核对总览与设备详情截图，并通过临时
  回环 HTTP 服务验证设备写入 `0600` 设置后可在进程重启时恢复。

### Added — complete E2 device-management workflow

- 设备详情页新增统一配置工作台：只读采集 147 项配置，展示面板设置、
  Wi‑Fi 连接状态、RSSI、信道和安全模式，并提供完整本地基线与语义差异比较。
- 页面和 API 对 SNMP community、Wi‑Fi SSID、系统联系人/位置等敏感字段统一
  脱敏；修复了 Wi‑Fi SSID 的敏感 OID 使用相对形式但快照检查绝对形式，导致
  SSID 未被标记的问题。
- 147 项表格增加“可回滚实验/只读”写权限分类。只有 item 2
  `Auto error clear` 和 item 50 `Quiet mode` 可生成 `OFF -> ON -> OFF`
  计划，计划必须重新读取全表、无漂移、令牌匹配且用户在页面单独勾选授权。
- 新增 `config_web.py` 和 `/api/config`、`/api/config/baseline`、
  `/api/config/compare`、`/api/config/plan`、`/api/config/apply`；SNMP
  配置读取/恢复闭环接入 Web 与 GTK 共用的服务器实例。
- MA2000w 真机只读采集 96/147，Wi‑Fi 状态正确返回、SSID 显示为隐藏；临时
  `0600` 基线保存成功，item 2 和 item 50 的回滚计划均 `allowed=true`、
  无 blockers，未发送任何 SET。
- MA2000w 真机完成预设驱动灰度 HCPDF 扫描：设备返回 RAW，自动落盘 775,467
  字节，HTTP 下载与落盘文件逐字节一致，SHA-256
  `f96a559b9f8c1e0d7560c52d5e4f7ab50c178d126721965a40293feb4c27f1b1`。
- 版本升级为 `0.2.0`；构建并安装 `0.2.0-1` Debian 包，SHA-256
  `30430a0b6fdaa6e0f12474afdaabbe8cafeaec9a9c428f698e8809a55ded085f`。

### Fixed — scan completion contrast and download failure

- 修复深色主题下扫描完成提示继承白色文字、同时使用浅色内联背景造成不可读的
  问题。进展、成功、警告和失败现在使用明确的前景/背景/边框组合，不再覆盖
  主题背景后保留错误文字颜色。
- 原生 GTK/WebKit 窗口新增内部下载桥：点击扫描结果文件名后，直接从对应后台
  任务取得产物，以 `0600` 权限和冲突安全的文件名保存到 `~/Downloads`，并显示
  实际保存路径；普通浏览器继续使用 HTTP 附件下载。
- `/api/scans/<id>/files/<n>` 现在同时发送 ASCII `filename` 和 UTF-8
  `filename*` 两种附件文件名，提高 WebKit/浏览器兼容性。
- 新增文件名字段化、路径穿越、独占写入、消息桥接、结果颜色和附件头测试；
  使用真实隐藏 GTK/WebKit 窗口完成一次消息桥接落盘验证。
- 版本升级为 `0.1.1`，Debian 包为 `0.1.1-1`，可由已安装的 `0.1.0-1`
  直接升级。

### Added — E2 onboarding workflows and Debian package

- Web/GUI 新增最多 30 个本地扫描预设；预设复用官方扫描 token，可保存、
  更新、删除并应用到下一次扫描。设置保存在
  `$XDG_CONFIG_HOME/kyocera-monitor/settings.json`（默认
  `~/.config/kyocera-monitor/settings.json`），文件权限为 `0600`，写入采用
  临时文件原子替换。
- 新增用户选择扫描保存目录；启用后后台任务在设备会话关闭、文件生成后自动
  写入该目录，并把实际路径显示在任务结果中。默认目录为
  `~/Pictures/Kyocera Scans`。
- 总览页新增多设备计数 CSV 导出，包含型号、序列号、状态、页数、扫描计数、
  鼓计数、读取时间和错误；对设备返回的公式前缀做转义。
- 总览页新增可关闭的浏览器状态通知。通知基于页面轮询到的状态变化，不声称
  复刻 Windows 托盘主动回调。
- 新增 `tools/build_deb.py`，构建架构无关 `.deb`，声明
  `python3-pil`、GTK3 和 WebKit2 4.1 运行依赖；包内只包含本项目 Python
  源码、三个入口、桌面文件、图标和许可证，不包含原厂二进制。
- 新增 Debian 包字段/内容测试、设置持久化、预设合并、自动落盘和计数 CSV
  测试。

### Added — integrated scan workflow and official-format local export

- 新增 `kyocera_monitor.scan`，把预检、默认配置、开会话、启动扫描、轮询取图、
  RAW 解码、导出和关会话从独立脚本移入包内；`tools/kmscn_scan.py` 改为兼容
  适配器。
- Web/GUI 设备详情页提供颜色、分辨率、原稿类型、页数和输出格式；扫描在后台
  线程执行，页面轮询预检、取图、解码、导出和关会话阶段，并从同源 URL 下载。
  同一设备已有活动扫描时返回忙状态。
- 设备 RAW 与用户文件格式已解耦。新增 PNG、PDF、JPEG、多页 TIFF、高压缩
  PDF、XPS 本地导出，保留 BMP 和 RAW；PNG/PDF/BMP/RAW 使用标准库，
  JPEG/TIFF 与内嵌 JPEG 的 PDF/XPS 使用 Pillow。
- 修正真机发现：MA2000w `retrieve_imageResponse/file_size` 曾返回 `958464`，
  而实际图像远大于该值。重新分析同一哈希 `KMSCNAPI.dll` 后确认官方
  `SoapScanModuleImpl::RetrieveImage` 使用 `image_data` 二进制对象内部长度，
  XML `file_size` 只被反序列化和清零；Linux 客户端不再把它当传输总长。
- MA2000w 真机完成集成彩色扫描：PNG 18,901,007 字节
  （SHA-256 `ab5716a4be1f87918ffc4f7f40b3d25f952c9f14518aa9aaa5f2aeb52a6d1d50`），
  PDF 18,878,382 字节并经 Poppler 解析/渲染，JPEG 2,319,913 字节并可正常查看。
  三者均为 2496×3520，设备返回 RAW，`close_session=SUCCESS`。
- 单进程 Web API 已完成一次真机灰度扫描任务和 JPEG 下载；下载响应的长度、
  SHA-256、MIME 和文件名与任务结果一致。
- 新增扫描导出、工作流、忙保护、`file_size` 非传输长度、Web 任务/下载和兼容
  CLI 测试。
- TIFF、高压缩 PDF、XPS 最小样本分别通过 ImageMagick 多页读取、
  Poppler `pdfinfo` 和 ZIP 完整性检查；尚未在 Windows XPS 查看器验证。
- 在 `/tmp` 的全新安装目标执行 `pip install .`，自动安装 Pillow 13.0.0，
  构建出包含扫描服务的 wheel；三个 console entry 均可启动。安装后的
  `kyocera-monitor` 在 MA2000w 上完成一次灰度 JPEG 扫描，
  2,148,644 字节、2496×3520、`close_session=SUCCESS`。
- 桌面菜单文案移除“只读”限制并加入扫描关键词；安装到临时 prefix 的正常、
  冲突保护和卸载路径继续通过测试。
- 补齐扫描轮询超时、完成后再次扫描、设备忙和输出写入失败临时文件清理测试；
  安装后的 Web 页面/状态 API 和 GTK 进程启动也完成验证。

### Added — official feature parity plan

- 从已校验的 ClientTool 1.4.11.2 模块、保存的反编译调用链和真机证据整理
  30 项官方用户功能，区分已复刻、部分实现、仅静态还原、未开始、硬件阻塞和
  非核心平台功能。
- 将下一阶段按扫描闭环、核心设备管理、设备驱动工作流、高风险维护和可选项
  五个波次排序，明确每项验收标准。
- 记录 MA2000w 扫描仍以 RAW 为主的原因：设备未返回输出格式 capability、
  默认配置为 RAW、请求 JPEG 后响应仍为 RAW；Linux 侧目前只实现 RAW→BMP。
- 扫描产品化要求将设备请求格式与本地导出格式分离，默认提供 PNG/PDF，不再把
  `--format` 误当作最终文件格式。

### Changed — product-focused delivery plan

- 完成阶段性复盘：扫描协议与状态功能已可用，但 Web/GUI 仍只读，扫描入口仍是
  独立工具；配置写入区域已超过当前产品所需的覆盖阈值。
- 冻结配置字段扩展，停止以字段数量衡量核心进度，后续只处理缺陷或明确需求。
- 将下一阶段主攻目标改为扫描产品闭环：包内扫描服务、Web/GUI 参数与执行、
  BMP 下载、真机验收，然后进行安装和发布收口。
- ADF/双面、其他机型和 USB 物理验证移入硬件阻塞 backlog，不占用主线。
- 新提交策略：端到端里程碑通常合并为 1–3 个提交，测试和文档随功能提交。

### Added — reversible harmless-field write audit

- 新增 `--config-audit-safe PATH`，从完整性基线生成固定白名单，逐项执行
  目标 SET、目标回读、原值 SET 和原值回读。
- MA2000w 上 25/25 个字段成功完成写入、回读和恢复，覆盖睡眠、自动清除超时、
  纸张不匹配策略、17 个媒体重量/类型行、打印浓度、单位、送纸超时和面板清除。
- 恢复失败会立即停止后续字段；设备拒绝目标值但恢复成功时继续下一项。
- 完整 147 项比较最终为 0 个持久配置变化、0 个易变观测、0 个读取状态变化。
- 网络/Wi-Fi、SNMP 凭据/trap、传真、重置、计数器、字符串和未知语义对象不在
  白名单中。逐项结果见
  `docs/reverse-engineering/data/clienttool-safe-write-audit-20261101.tsv`。
- 新增 6 个专项测试；全量测试 216/216；公开树检查通过。

### Added — verified Quiet mode write and rollback

- 扩展 `--config-plan` 和 `--config-apply`，item 50 `Quiet mode` 可生成
  当前值、目标值、回滚值、PJL/SNMP 预览和 SHA-256 令牌，并交给只接受
  `OFF -> ON -> OFF` 的专项执行器。
- 新增 `quiet-mode-off-to-on-then-off-v1` scope 和 CLI 分发；令牌、基线、
  目标、字段、旧值及新值必须全部匹配，预写值不是 `OFF` 时不会发送 SET。
- 修正 dry-run CLI 退出码：计划前置条件有效时返回 `0`，不再把“该字段尚无
  执行器”误报为命令失败；no-op、漂移或读取不稳定仍返回 `1`。
- 在哈希匹配的 `KMUTLCFG.exe` 导出上复核失败处理：SNMP error-status 非零
  会记录失败原因/对象，无响应单独记录 timeout；USB 等待响应最长 50 秒并把
  `STATUS!=0` 计为失败。
- MA2000w 真机完成 item 50 `OFF -> ON -> OFF`：两次 SET 成功，同 OID 回读
  分别为 `1` 和 `0`。随后 147 项比较无持久配置变化、无读取状态变化；
  唯一变化为 Wi-Fi RSSI 自然波动。
- `Quiet mode` 目录标签升级为 `verified`，候选报告升级为
  `device_verified`；候选审查仍不允许替代后续明确授权或证明失败恢复行为。
- 专项测试 20/20；全量测试 210/210；公开树检查通过。本次只发送已授权的
  item 50 SNMP SET/回读和只读全表采集，没有发送 PJL `KSETOBJ` 或重置命令。

### Added — read-only next configuration write candidate review

- 新增 `--config-candidates`：从一次完整只读配置采集评估 item 50
  `Quiet mode`（`1001.2.1.1.1.14.1`）是否适合作下一次写入授权评审。
- 报告核对官方 UI 到模型偏移/OID 映射、对象可读状态、Integer 类型和
  `OFF/ON` 枚举，并把当前读取有效性与写入许可分开。
- `write.allowed` 固定为 `false`；缺少同 OID 写入回读、失败/重启副作用证据
  和用户授权缺失均保留为 blockers。
- 该命令不生成写入计划或确认令牌，不发送 `KSETOBJ`、SNMP SET 或设备复位。
- `--config-candidates --json` 只输出候选摘要，不附带完整 147 项对象表。
- MA2000w 连续两次只读 SNMPv2c 采集均为 `96/147`，item 50 均为
  `STATUS=0`、`0/OFF`；仅证明当前读取连续稳定，不证明可写。
- 验证：新增 3 个候选审查专项测试；全量测试 204/204；公开树检查通过。

### Verified static — Quiet mode write serialization

- 在已校验的 `KMUTLCFG.exe` 上复核 item 50 完整静态数据流：
  `BM_GETCHECK(0x455)` → 快照 `+0x18` → 差异 case `0x31` →
  OID `1001.2.1.1.1.14.1`，类型字符 `0x69`（整数），值归一化为 `0/1`。
- 网络 `FUN_00401b20` 和 USB `FUN_00402ec0` 写入器都消费该变化记录；USB
  格式为 `@PJL KSETOBJ OBJ="1.1001.2.1.1.1.14.1" VALUE =<0|1>`。
- item 50 分支不设置原厂应用的控制器重置请求标志 `[app+0x57ec]`；因此官方
  程序不会为该字段单独追加重置 OID，但设备内部是否重启仍未验证。
- 候选报告将静态映射升级为 `static_verified`，继续禁止写入；剩余 blockers
  为同 OID 写入回读未验证、设备失败/重启行为未知和缺少用户明确授权。

### Added — integrity-checked configuration baselines

- 新增 `--config-save PATH`：把一次完整的 147 项只读配置采集保存为规范化
  JSON 快照，使用 SHA-256 校验和、UTC 时间、传输通道和目标绑定；文件以
  `0600` 权限原子写入，默认拒绝覆盖。
- 新增 `--config-compare PATH`：验证快照完整性和文件权限后，按 item id/OID
  比较当前配置；拒绝跨传输或跨目标比较，差异以退出码 `1` 报告。
- Wi-Fi 连接状态、RSSI 和信道被标记为只读易变观测，与配置值变化及读取状态
  变化分开报告；MA2000w 只读实测捕获到 RSSI `-69 -> -71 dBm` 的自然波动。
- 快照保留解码值与设备传输值，并标记 SNMP community、Wi-Fi SSID、
  `sysContact`、`sysLocation` 等已知敏感字段；快照不得提交到仓库。
- 复核已校验的 `KMUTLCFG.exe`：`FUN_00402ec0` 的 USB 写入模板实际为
  `@PJL KSETOBJ OBJ="%s%s" VALUE =%s`（等号前有空格），与旧文档中的通用
  示例不同；`KMUTLPRE.exe` 仍需单独核对，不能直接复用。
- 新增 `docs/reverse-engineering/config-write-safety.md`，记录官方静态证据、
  快照格式、未来单字段写入/回读/回滚条件以及未知项。
- 该阶段未发送 `KSETOBJ`、SNMP SET、设备重置或其他写命令。
- 验证：配置专项 17/17；全量测试 185/185；公开树检查通过。MA2000w 只读
  基线保存和后续比较均为 96/147；最终比较为 0 个配置变化、0 个易变观测、
  0 个读取状态变化。

### Added — reviewed single-field write plans

- 新增 `--config-plan PATH --config-set ITEM_ID=VALUE`，把基线与当前只读采集
  合成为可审计的 dry-run 写入计划。
- 首个且唯一开放的候选是 item 2 `Auto error clear`，只接受 `0/OFF` 和
  `1/ON`；其他对象或值直接拒绝。
- 计划包含当前值、目标值、回滚值、官方 `KMUTLCFG.exe` PJL 命令预览、
  SNMP Integer 参数、回读条件、漂移 blockers 和 SHA-256 确认令牌。
- 初始计划器不提供写入执行路径；后续获准真机实验后增加严格受限的
  `--config-apply`。
- 验证：新增 5 个计划专项测试；全量测试 190/190 通过；公开树检查通过。

### Verified — Auto error clear write and rollback

- 新增 SNMPv2c Integer SET BER 编码、error-status/error-index 解析和同 OID
  回读校验。
- 新增 `--config-apply`，仅接受匹配的 confirmation token、同一基线、
  SNMPv2c 和 `Auto error clear OFF -> ON -> OFF`；正向失败也会尝试回滚。
- MA2000w 真机写入 `1` 后回读为 `ON`，立即写回 `0` 并回读为 `OFF`；
  随后全表比较 147/147 一致，未观察到重启或断网。
- `clienttool-control-oids.tsv` 中 `Auto error clear` 映射升级为已验证。
- 验证：新增 11 个 SET/executor/CLI 测试；全量测试 201/201；公开树检查通过。

## 2026-10-31

### Added — scan option parity, multipage handling, and grayscale RAW

- 以校验后的官方 `KMSCNAPI.dll` 枚举表和 `start_scanRequest` 为依据，限制
  扫描 CLI 只接受官方 token：颜色、分辨率、`SIMPLEX/DUPLEX/BOOKLET`、
  `AUTO/PLATEN/ADF`、连续扫描 `OFF/ON`、原稿类型和输出格式。
- 新增按官方序列化顺序插入缺失配置字段的逻辑；默认仍以设备返回配置为准。
- 官方 DLL 诊断实测 `CONTINUE_SCAN` 返回码 `10010` 且无图像；
  `KMNETSCN3` 对非终止状态继续取图。Linux 客户端现将该状态作为等待，
  并支持逐页保存到 `ALL_GET_COMPLETE`。
- 新增多页模拟测试，覆盖
  `CONTINUE_SCAN -> 第1页 -> 第2页 -> ALL_GET_COMPLETE`、
  `ADF/BOOKLET/ON` 请求字段和 `close_session`。
- MA2000w 真机完成 `GRAYSCALE + RAW` 扫描：RAW 9,425,014 字节，单平面
  8 带 2496×440；独立解码为 2496×3520、清晰可见的 24 位灰度 BMP。
- 修复解码格式选择：以响应 `file_type` 为准。MA2000w 请求 JPEG 时仍返回
  RAW，客户端会按实际 RAW 解码。
- `http.client.IncompleteRead` 现在转换为结构化传输错误，不再输出未处理的
  Python traceback；不解析不完整图像。
- 新增 `--max-response-bytes`，允许高分辨率场景显式提高单次取图的内存上限；
  默认仍为 64 MiB。
- 官方 DLL 诊断宿主新增受控 dword 配置覆盖实验参数，捕获服务器新增
  `--retrieve-result`。
- 验证：扫描专项 38/38；全量测试 178/178；公开树检查通过。

## 2026-10-29

### Added — network TWAIN/KM-WSDL evidence and read-only probe

- 从京瓷官方下载中心取得 `Kyocera TWAIN Driver GX 2.1.4412`，在不执行安装器
  的情况下定位并校验内嵌 `KmSFX.zip`，补齐 `Ns1815TWGN.dll`、
  `KMNETSCN3.dll`、`KMSCNAPI.dll` 和 `KMWSDLTWAING.ds`。原厂二进制只保存在
  被忽略的 `analysis/local-only/`。
- 确认网络 TWAIN 的实际调用链为
  `Ns1815TWGN -> KMNETSCN3 -> KMSCNAPI`，并由 `KMSCNAPI.dll` 实现
  KM-WSDL/gSOAP：HTTP 使用 9090，HTTPS 使用 9091，固定服务路径为
  `/ws/km-wsdl/job/scan_operation`。
- 还原服务信息、能力、默认配置、开会话、开始扫描、取图、取消和关会话的
  SOAP action，以及驱动实际调用顺序。
- 新增 `kyocera_monitor/kmscn.py`、`tools/kmscn_probe.py` 和
  `kyocera-kmscn-probe` 命令。探针只发送 `get_service_information` 或
  `--capability` 对应的 `get_capability`，不会打开扫描会话、开始扫描、取图
  或写入设置。能力响应保留完整 XML 层级，缺失项、Fault、非零结果和非法 XML
  均显式报错。
- HTTP 传输改为显式构造 gSOAP 2.7 风格的 HTTP/1.1 请求，避免标准库自动
  添加额外请求头；新增 `--preflight`，严格按服务信息成功后再请求 capability
  的顺序执行，并结构化记录失败阶段。
- 新增聚焦 Ghidra 脚本 `tools/ghidra_scripts/InspectScanApi.java`，仅导出
  扫描导出函数、网络 API 调用者和相关协议字符串交叉引用。
- 新增 `tools/ghidra_scripts/DecompileAddresses.java`，用于按地址聚焦导出
  官方驱动的 URL、HTTP 和 SOAP 封装函数。
- 使用 Wine 10.0 和 32 位 MinGW 诊断宿主加载官方 DLL，捕获并逐字节复刻
  SOAP 1.2、WS-Addressing Header、完整 namespace、SOAPAction 和 gSOAP
  HTTP 头；请求样本已写入测试。
- 新增 `tools/kmscn_scan.py`，独立完成预检、默认配置、开会话、启动扫描、
  XOP 轮询取图、`ALL_GET_COMPLETE` 和关会话，不依赖官方 DLL。
- 新增 `kyocera_monitor/kmscn_raw.py`，按官方状态机实现暗/亮校准、
  阴影校正、三颜色平面合并和 24 位 BMP 输出。
- MA2000w 真机完成单页扫描：RAW 28,275,026 字节，成功输出 2496×3520 BMP；
  `close_session=SUCCESS`。
- 新增 32 位 MinGW 官方 DLL 诊断宿主、回环捕获服务器，以及包含 Wine
  安装、隔离前缀和端口绕法的逆向工具文档。
- 验证：`python3 -m unittest discover -s tests -v` → 170/170 通过；
  公开树检查通过。

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
