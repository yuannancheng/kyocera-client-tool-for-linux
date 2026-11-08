# KYOCERA Client Tool for Linux

简体中文 | [English](README.en.md)

独立的、非官方 Linux 京瓷打印机客户端。项目以官方 Windows Client Tool 的
可复现静态证据、真实设备响应和互操作性测试为依据，通过 Linux 原生路径实现
状态读取、设备配置、Wi-Fi 设置和扫描。

当前重点验证机型为 **KYOCERA MA2000w**。主要能力包括：

- PJL/TCP 9100、USB `usblp`、无 root libusb Printer-class 回退；
- SNMPv1/v2c 状态、设备发现和 Wi-Fi 状态/AP 扫描；
- KM-WSDL 网络扫描、RAW 解码和多种本地格式导出；
- Web/GUI 设备管理、扫描预设、配置基线及已审核属性写入；
- 简体中文/英文界面、手动版本检查和显式标签发布流程。

[最新版本](https://github.com/yuannancheng/kyocera-client-tool-for-linux/releases/latest)
· [项目进度](PROJECT_PROGRESS.md)
· [功能覆盖](docs/official-feature-parity-plan.md)

> This project is independent and unofficial. It is not affiliated with
> Kyocera Corporation. The software is provided under the MIT License without
> warranty, and the authors disclaim liability to the extent permitted by law.

Kyocera、KYOCERA、ECOSYS、MA2000w 等名称属于各自权利人，仅用于说明兼容对象。

## 当前状态

| 模块 | 状态 |
| --- | --- |
| 网络/SNMP/USB 状态 | MA2000w 已验证 |
| 设备发现与多设备总览 | 已验证 |
| KM-WSDL 扫描与 RAW 解码 | MA2000w 真机通过 |
| PNG/PDF/JPEG 导出 | MA2000w 真机通过 |
| TIFF/XPS/BMP/高级 PDF | 本地编码和结构测试通过 |
| 147 项配置读取与基线 | MA2000w 读取 96/147 |
| 27 项已审核整数配置写入 | 网络真机通过；USB 写路径待物理设备复验 |
| USB 打印/Wi-Fi 操作 | MA2000w 真机通过 |
| Push Scan 触发监听 | 只读检测和本地执行已实现；真实网络触发未闭环 |
| ADF/双面/其他机型 | 无对应硬件，待验证 |
| 版本检查与发布构建 | v0.3.3 已验证 |

## 安装

### Python wheel 或源码安装

```bash
python3 -m pip install --user .
kyocera-gui
```

运行时会从 Python 包索引安装 Pillow。GTK/WebKit 属于可选系统依赖：

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

没有 GTK/WebKit 时仍可使用浏览器模式：

```bash
python3 -m kyocera_monitor --web --web-open
```

### Debian 包

```bash
python3 tools/build_deb.py
PROJECT_VERSION=$(python3 tools/release.py version)
sudo apt install "./dist/kyocera-monitor_${PROJECT_VERSION}-1_all.deb"
```

Debian 构建只使用本地 Python 和 `dpkg-deb`，不联网，不包含京瓷官方 Windows
程序、DLL 或安装包。包依赖由 APT 提供，详见
[`packaging/README.md`](packaging/README.md)。

### 桌面菜单

```bash
python3 tools/install_desktop.py
python3 tools/install_desktop.py --uninstall
```

## 快速开始

```bash
# GUI；未指定打印机时可自动枚举 USB 设备
kyocera-gui

# Web 仪表盘
python3 -m kyocera_monitor --web --web-open

# 指定网络打印机
python3 -m kyocera_monitor --host 192.168.0.220 --gui
python3 -m kyocera_monitor --host 192.168.0.220 --json

# USB
python3 -m kyocera_monitor --list-usb
python3 -m kyocera_monitor --usb --json

# 自动发现
python3 -m kyocera_monitor --discover
python3 -m kyocera_monitor --discover --json
```

CLI 退出码：

- `0`：查询成功且状态正常；
- `1`：未发现设备、配置为空或比较发现差异；
- `2`：连接、协议或参数错误；
- `3`：设备返回警告状态；
- `4`：`--expect-model` 不匹配。

## Web/GUI 功能

### 设备与状态

- 手动输入 IP，或通过 SNMP 广播/WS-Discovery 发现设备；
- 多设备状态总览、持久化设备列表和计数 CSV；
- 型号、序列号、固件、网络、耗材、纸盒、面板、告警和计数；
- 可关闭的浏览器状态通知；
- 未指定网络目标时自动枚举 USB 打印机。

### 扫描

```bash
python3 -m kyocera_monitor --host 192.168.0.220 --scan \
  --scan-color FULL_COLOR --scan-format png --scan-output /tmp/scan.png

python3 -m kyocera_monitor --host 192.168.0.220 --scan \
  --scan-color GRAYSCALE --scan-format jpeg --scan-output /tmp/scan.jpg
```

Web/GUI 可创建后台扫描任务、显示阶段并下载：

- PNG、PDF、JPEG、TIFF、高压缩 PDF、XPS、BMP、RAW；
- 多页任务、设备忙保护、超时和关会话错误报告；
- 本地扫描预设、绝对保存目录和 Push Scan 槽位映射。

设备返回格式与本地导出格式分开记录。MA2000w 请求 JPEG 时仍返回私有 RAW，
因此 JPEG 由 Linux 本地从 RAW 生成，不宣称与设备原生 JPEG 逐字节一致。

### 设备配置

设备页按官方对话框拆分为：

- 设备默认值；
- 纸张与介质；
- 通信设置；
- SNMP Trap；
- 面板与扫描；
- 传真设置；
- Wi-Fi。

支持 147 项分区只读、私有基线、差异比较和 27 个已审核整数属性编辑。单个
属性提交携带页面旧值、目标值和明确确认；写入后回读同一 OID，失败时尝试恢复。
网络使用 SNMP SET，USB 使用官方 `KSETOBJ`。

配置快照以 `0600` 原子写入，可能包含 community、SSID、联系人或位置信息，不得
提交到公开仓库。写入边界见
[`docs/reverse-engineering/config-write-safety.md`](docs/reverse-engineering/config-write-safety.md)。

### Wi-Fi 与 USB

```bash
python3 -m kyocera_monitor --usb --wifi-status --json
python3 -m kyocera_monitor --usb --wifi-scan --json

KYOCERA_WIFI_PASSWORD='...' python3 -m kyocera_monitor \
  --usb --wifi-connect SSID --wifi-security 4
```

- Wi-Fi 状态、AP 扫描和连接顺序复刻官方 Wi-Fi Setup Tool；
- 密码只存在单次请求中，不写入设置文件；
- Web 凭据写入 API 只接受回环客户端；
- USB 状态和 Wi-Fi 在 MA2000w 真机验证；
- USB ScanReq 图像取回仍是实验路径，正式扫描推荐 KM-WSDL。

连接已知 Kyocera USB 打印机后，可检查并创建 CUPS 队列：

```bash
python3 tools/install_linux_driver.py
python3 tools/install_linux_driver.py --apply
```

## 多语言与版本检查

Web/GUI 默认按设备浏览器语言自动选择：

- `auto`：匹配 `Accept-Language` 中的 `zh*`、`en*`；
- 无法匹配时回退简体中文；
- 可手动选择“简体中文”或“English”；
- 偏好保存在 `settings.json`，总览页和设备页共享。

版本检查只在用户点击或显式运行 CLI 时联网：

```bash
kyocera-monitor --check-update
kyocera-monitor --check-update --json
```

检查使用语义版本比较，前后端各缓存 60 秒。优先读取 `updater/update.json`；
下载域不可用时回退 GitHub Releases API。发布页链接必须是 HTTPS。

## 发布与版本管理

`pyproject.toml` 的 `[project].version` 是唯一版本源，格式为
`MAJOR.MINOR.PATCH`；标签格式为 `vX.Y.Z`。

```bash
python3 tools/release.py bump patch
NEXT_VERSION=$(python3 tools/release.py version)

python3 tools/release.py check --tag "v${NEXT_VERSION}"
git tag -a "v${NEXT_VERSION}" -m "KYOCERA Client Tool v${NEXT_VERSION}"
git push origin main "v${NEXT_VERSION}"
```

- 普通 `main` 推送和 PR 只运行测试；
- 推送匹配标签才构建 wheel、sdist、Debian 包和 GitHub Release；
- 发布 workflow 同时更新固定 `updater` Release 的 `update.json`；
- 支持 `workflow_dispatch` 的 `release_tag` 输入作为显式重试入口；
- 已发布标签不移动、不重建。

构建流见
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) 和
[`.github/workflows/release.yml`](.github/workflows/release.yml)。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 tools/check_publication.py
```

当前 390 项测试覆盖：

- PJL/SNMP/USB/Wi-Fi/KM-WSDL 协议和设备映射；
- 扫描多页状态机、RAW 解码和多格式导出；
- Web/GUI 缓存、设置、配置基线、写入回读和错误恢复；
- 中英文协商、版本检查、语义版本和发布 workflow；
- Debian 包、桌面文件、公开树合规和敏感内容边界。

需要本地 `Kyocera/ClientTool` 原厂样本的研究回归在样本缺失时会跳过；已提交的
TSV、生成模块和独立实现测试仍在 CI 运行。

## 研究资料

- [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md)：当前状态、阻塞和下一步；
- [`docs/official-feature-parity-plan.md`](docs/official-feature-parity-plan.md)：
  官方 30 项功能覆盖；
- [`docs/architecture.md`](docs/architecture.md)：Linux 模块与数据流；
- [`docs/reverse-engineering/scan-workflow.md`](docs/reverse-engineering/scan-workflow.md)：
  网络扫描和 Push Scan；
- [`docs/reverse-engineering/usb-path.md`](docs/reverse-engineering/usb-path.md)：
  USB 打印/扫描路径；
- [`docs/reverse-engineering/wifi.md`](docs/reverse-engineering/wifi.md)：
  Wi-Fi 协议与真机证据；
- [`docs/reverse-engineering/clienttool-protocol.md`](docs/reverse-engineering/clienttool-protocol.md)：
  Client Tool 配置/对象表；
- [`docs/reverse-engineering/progress-history.md`](docs/reverse-engineering/progress-history.md)：
  历史交接与实验记录。

## 内容与安全边界

- 仅分析 `Kyocera/ClientTool` 及该程序主动使用的同目录文件；
- 正式 Linux 功能不在运行时加载或分发京瓷 DLL/EXE；
- 未知字段、未验证状态和不支持的机型必须明确标记，不能表述为官方兼容；
- 仓库不包含原厂安装包、二进制、完整反编译输出、凭据或真实设备站点数据；
- Web 服务默认只监听 `127.0.0.1`；使用 `--web-bind 0.0.0.0` 时必须自行增加
  访问控制。

第三方依赖和商标说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
与 [NOTICE](NOTICE)。

## 许可证

本项目采用 [MIT License](LICENSE)。软件按“现状”提供，不附带任何明示或默示
担保。详细边界见 [LICENSE](LICENSE)、
[docs/legal/compliance.md](docs/legal/compliance.md) 和
[CONTRIBUTING.md](CONTRIBUTING.md)。
