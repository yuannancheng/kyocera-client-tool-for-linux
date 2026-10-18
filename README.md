# KYOCERA Client Tool for Linux

独立的、非官方 Linux 打印机状态监视器，面向 Kyocera 设备（当前验证机型
MA2000w）。项目通过公开的 PJL/SNMP 行为和互操作性测试实现只读状态读取：
支持 TCP 9100、USB `usblp` 和只读 SNMP 路径。

本项目与 Kyocera Corporation 及其关联公司没有隶属、授权、赞助或背书关系，
不是京瓷官方产品。Kyocera、KYOCERA、ECOSYS、MA2000w 等名称是其各自权利人的
商标，仅用于说明兼容对象。

## 许可证与免责声明

本项目代码采用 MIT License，完整文本见 [LICENSE](LICENSE)。软件按“现状”
提供，不附带任何明示或默示担保，包括但不限于适销性、特定用途适用性和
不侵权担保。在适用法律允许的范围内，作者和贡献者不对因使用本软件产生的
任何索赔、损害或其他责任负责。

This project is independent and unofficial. It is not affiliated with Kyocera
Corporation. THE SOFTWARE IS
PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. TO THE
MAXIMUM EXTENT PERMITTED BY LAW, THE AUTHORS AND CONTRIBUTORS DISCLAIM ALL
LIABILITY FOR ANY CLAIM, DAMAGE OR OTHER LIABILITY ARISING FROM USE OF THE
SOFTWARE.

仓库只包含独立编写的实现代码、协议标识符与行为摘要、经过脱敏的测试数据，
不包含原厂安装包、可执行文件、DLL、资源文件、完整反编译输出、成规模逐字
复制的界面文本、维护包密钥或设备凭据。第三方依赖和商标说明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [NOTICE](NOTICE)。

## 使用

```bash
./kyocera-gui
python3 -m kyocera_monitor --gui
python3 -m kyocera_monitor --gui --host 192.168.0.220
python3 -m kyocera_monitor --host 192.168.0.220
python3 -m kyocera_monitor --host 192.168.0.220 --json
python3 -m kyocera_monitor --device /dev/usb/lp0
python3 -m kyocera_monitor --list-usb
python3 -m kyocera_monitor --usb --json
python3 -m kyocera_monitor --host 192.168.0.220 --watch 30
python3 -m kyocera_monitor --host 192.168.0.220 --snmp
python3 -m kyocera_monitor --host 192.168.0.220 --snmp --json
python3 -m kyocera_monitor --host 192.168.0.220 --config
python3 -m kyocera_monitor --host 192.168.0.220 --config --json
python3 -m kyocera_monitor --host 192.168.0.220 --config --snmp
python3 -m kyocera_monitor --host 192.168.0.220 --web
python3 -m kyocera_monitor --web --web-open
python3 -m kyocera_monitor --host 192.168.0.220 --snmp --web --web-port 8080
python3 -m kyocera_monitor --discover
python3 -m kyocera_monitor --discover --json
python3 -m kyocera_monitor --discover --discover-subnet 192.168.0.0/24
```

退出码：`0` 状态正常，`1` 未发现打印机或配置导出没有读到任何对象，`2` 连接或
协议错误，`3` 设备返回警告状态码，`4` 型号不匹配。

## 图形界面

`./kyocera-gui` 或 `python3 -m kyocera_monitor --gui` 打开原生 GTK3 窗口。
窗口内部是同一个只读 Web 仪表盘，服务只监听 `127.0.0.1` 的随机端口，关闭窗口即
退出。启动时不需要先指定打印机：可以在页面顶部手动输入 IP，或点击
“发现打印机”使用 SNMP 广播/WS-Discovery 搜索。启动时也可以加
`--host 192.168.0.220` 直接进入该设备。

原生窗口依赖 GTK3 与 WebKit2 4.1（Debian/Ubuntu 包名通常为
`gir1.2-gtk-3.0`、`gir1.2-webkit2-4.1`）。缺少依赖时 `--gui` 会返回退出码 2
并提示改用 `--web`；`--web` 本身只需要 Python 标准库。

```bash
# 无桌面环境或不想装 GTK 时，在浏览器中打开
python3 -m kyocera_monitor --web --web-open
```

## 桌面菜单安装

仓库提供 `.desktop` 菜单项、SVG 图标和无需 root 的安装脚本：

```bash
# 安装到 ~/.local/share（默认）
python3 tools/install_desktop.py

# 安装到自定义前缀（例如打包或系统级安装）
python3 tools/install_desktop.py --prefix /usr/local

# 卸载
python3 tools/install_desktop.py --uninstall
```

安装脚本写入
`share/applications/kyocera-monitor.desktop` 和
`share/icons/hicolor/scalable/apps/kyocera-monitor.svg`。菜单项的
`Exec` 为 `kyocera-gui`，因此需要先把 Python 包安装到当前用户环境：

```bash
python3 -m pip install --user .
```

已经存在且内容不同的文件默认不会被覆盖；确认要替换时加 `--force`。

JSON 输出同时保留原始 `kgetobj`，并在 `kgetobj_known` 中提供已确认的结构化
字段（Scan count、Drum counter、Drum counter max、Auto error clear 及其
超时）。`2.10.2.1.4.1.1` 以 `lifetime_counter` 暴露为累计打印页数，单位为
`pages`，并标记 `confidence: "verified"`；设备 SNMP
`prtMarkerLifeCount`（`1.3.6.1.2.1.43.10.2.1.4.1.1`）返回相同值。
`Form feed timeout` 和 `Sleep mode` 的解析映射也已具备，但默认刷新序列不
查询这两个对象，可用 SNMP 路径读取。`2.5.1.1.10.1` 已确认映射到标准
Printer MIB `prtConsoleLocalization`，MA2000w 返回索引 `1`，对应本地化表中的
`en`/`US`；`1.42.5.1.1.16.1` 是面板固件版本对象，MA2000w 返回
`STATUS=2` 和空值。

`--snmp` 使用只读 SNMP 读取型号、序列号、固件、网络、耗材、纸盒、面板显示、
告警、扫描计数、Sleep mode、Auto error clear/超时和 Form feed timeout。
MA2000w 的 SNMPv2c `GETNEXT` 已验证可用，但 `GETBULK` 无响应，因此默认使用
SNMPv1；单次采集实测约 2.6–3.6 秒，偶发丢包时 5–9 秒。实现按行读取表的
所需列，并顺序执行以避免设备在并发请求下丢包。告警 `1001` 是标准 Printer MIB
的 `markerFuserUnderTemperature`，设备睡眠时以非关键告警形式存在；设备显示的
“Sleeping...” 对应同一告警行的厂商显示字段，不能把 `1001` 直接当成睡眠模式。
SNMP 路径没有 PJL `CODE`，不能把 `hrDeviceStatus` 或告警代码直接当作 PJL
状态码。页计数使用标准
`prtMarkerLifeCount` 的完整实例 OID，MA2000w 返回 `Counter32`；注意实例是
`.4.1.1`，少写最后一级会得到 `NoSuchInstance`。

PJL 采集按响应回显分段：设备漏答某几段时只补发缺失命令，再按原查询顺序合并，
不再重发整包；尾部连续 `--idle` 秒无数据即结束本轮接收。

`--config` 按项目中经过互操作性验证的 147 行对象表发送只读 `KGETOBJ` 批量查询，
输出每项的 item id、OID、`STATUS` 和解码后的值；`--json` 额外给出
`read`/`total` 与 `label`、`confidence` 等字段。支持 PJL 与 SNMP 两种只读
读取，不发送 `KSETOBJ`，也不能与 `--web`、`--gui` 或 `--watch` 组合。
MA2000w 实测 96/147 项返回 `STATUS=0`；其余多为 `STATUS=2`，集中在
`45.*`（传真相关）和 `43.7.1.1.3.1.2..12`（本地化语言表），应视为该机型
不提供这些对象，而不是传输失败。字符串按 `TYPE=4` 的十六进制解码，去掉
定长字段尾部的 NUL，并按 UTF-8 解码（Wi‑Fi SSID 实测为中文名称；仓库
不记录实际网络名）；`TYPE=64` 需要先解十六进制，再把得到的 8 位十六进制
IPv4 转成点分十进制。

设备睡眠时 TCP 9100 PJL 可能完全没有响应（`printer returned no PJL response`），
而 SNMP 仍可读。此时使用 `--config --snmp`：它按同一张 147 行对象表转换成
绝对 OID，以 SNMPv2c 分批只读 GET，默认每批 16 个对象。MA2000w 睡眠状态下
实测同样返回 96/147 项，耗时约 8.6 秒；缺失对象显示为 `-` 和
`no such object`。`--config-snmp-version` 可选择 `1` 或 `2c`，默认 `2c`
以避免 SNMPv1 对单个不存在对象的整包失败。

`tools/clienttool_ui_strings.py` 只提取控件 ID、字符串资源 ID、文本是否存在
及其长度，不输出本地化标签或组合框选项，生成
`docs/reverse-engineering/data/clienttool-ui-controls.tsv`。结合模型偏移后，
`43.5.1.1.23.1` 标为睡眠时间、`42.5.1.1.43.1` 标为关机定时器、
`1001.2.1.1.1.14.1` 标为 Quiet mode；三者仍标记为
`confidence: "inferred"`，尚未做写入回读验证。

`tools/clienttool_config_offsets.py` 读取本地静态分析导出，提取 147 项对象
到界面模型偏移的映射，生成
`docs/reverse-engineering/data/clienttool-config-offsets.tsv`；当前 147/147
项均有偏移。`tools/clienttool_dialogs.py` 只输出对话框和控件的结构、类名、
几何位置及文本长度，不发布标题或控件文字，生成
`docs/reverse-engineering/data/clienttool-dialogs.tsv`。两者与控件绑定表合并后得到
`docs/reverse-engineering/data/clienttool-control-oids.tsv`：主对话框、Panel
options、Communication、SNMP trap、Wi‑Fi 状态、音量与 FAX notification
共 69 个控件已建立“控件 → 模型偏移 → OID”对照；其中 64 个设置控件标记为
`confidence: "inferred"`（尚未做写入回读），5 个 Wi‑Fi 只读状态字段
标记为 `verified`（静态绑定 + 真机值）。

`tools/clienttool_config_names.py` 合并 Client Tool 自带的两份
`snmp-oid.xml`（Wi‑Fi setup 与 remotefax），为 147 项配置对象匹配厂商
符号名，生成 `docs/reverse-engineering/data/clienttool-config-names.tsv`：
127 项有名称，包括完整 `45.*` 传真组；其余 20 项在两份 XML 中都没有描述，
保持 OID-only。工具同时生成
`docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv`，保留
`oid`/`symbol`/`source` 全量索引。`--config` 的 JSON 和文本输出会带出
`vendor_name`，人工标签优先。

`--web` 启动只读状态页，默认监听 `127.0.0.1:8080`，可以不带 `--host` 启动。
`/` 是设备总览页，
`/device?host=<地址>` 是单设备详情页；`/api/devices` 返回所有已知设备的快照，
`POST /api/devices`（JSON `{"host": "192.168.0.220"}`）把手动输入的主机加入
允许列表，`/api/status?host=<地址>` 返回单个设备，`/healthz` 用于存活检查。
总览最多用 4 个线程并行取快照，单设备缓存 1 秒，页面每 10–15 秒刷新。
总览页上的“发现打印机”会调用 `/api/discover`，发现结果加入允许列表后
自动出现在总览中。
详情页展示 Lifetime/Scan/Drum 计数、睡眠模式、自动错误清除和表单超时；
其中 Lifetime counter 已由 PJL/SNMP 双向核对为页计数。
服务没有认证，默认只绑定回环地址；使用 `--web-bind 0.0.0.0` 暴露到局域网时
需要自行增加访问控制。

`--discover` 通过 SNMP 广播查找 Kyocera 打印机，并用 WS-Discovery 并行补充
端点信息；广播响应者再用单播 GET 补全序列号和固件。默认收集窗口 2.5 秒，
ARP 表作为附加候选；`--discover-subnet <CIDR>` 显式扫描 IPv4 网段（最大 /22）。
发现到设备返回 0，未发现返回 1，参数错误返回 2。

`--list-usb` 扫描 `/dev/usb/lp*` 并从 sysfs 读取 VID/PID；`--usb` 自动选择
Kyocera MA2000w（`0482:0d51`）或其他唯一可用的 USB 打印机。Linux USB 路径使用
内核 `usblp` 直接发送 UEL PJL 帧；Windows 原程序实际通过 Kyocera 语言监视器
转发，因此 USB 原始帧的完全一致性仍需硬件接入后验证。`--list-usb` 在找不到
`/dev/usb/lp*` 时返回退出码 2。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 tools/check_publication.py
```

当前 140 个测试覆盖 PJL 解析/帧格式、分段补发与合并、KGETOBJ 结构化字段、
147 项配置对象表与 CLI 配置导出、`KMUTLCFG` UI 控件字符串提取、
147 项对象→模型偏移映射与首批控件→OID 对照、
配置 SNMP 后备读取、
桌面菜单安装/卸载、
SNMP 编码与 walk/行读取边界、SNMP 到 `PrinterSnapshot` 的字段映射、USB
sysfs 发现、PTY 假设备往返、SNMP/WSD 发现与结果合并，以及 Web 快照缓存、
设备允许列表与手动添加、多设备并发读取、JSON、页面自包含性、无默认设备启动
和 GUI 依赖缺失时的回退，以及公开树合规检查。

## 研究资料

- `PROJECT_PROGRESS.md`：当前进度与后续任务
- `docs/reverse-engineering/progress-history.md`：压缩前的完整里程碑与轮次记录
- `docs/reverse-engineering/program-structure.md`：程序结构与关键函数
- `docs/reverse-engineering/clienttool-protocol.md`：仅 ClientTool 范围的
  网络/配置/预设/维护协议拆解与对象表
- `docs/reverse-engineering/data/clienttool-maintenance-requests.tsv`：
  维护 request id、item id、数据类型和来源序号（不含菜单标题或条目文字）
- `docs/reverse-engineering/data/clienttool-maintenance-request-ids.tsv`：
  维护 request id 的符号名与数值映射
- `tools/clienttool_ui_strings.py`：提取控件资源 ID 和文本长度，
  不发布本地化标签或选项
- `docs/reverse-engineering/data/clienttool-ui-controls.tsv`：
  `control_id`、字符串资源 ID、文本是否存在及长度
- `tools/clienttool_config_offsets.py`：从本地分析导出提取
  对象索引到模型偏移的映射
- `docs/reverse-engineering/data/clienttool-config-offsets.tsv`：
  147 项配置对象的模型偏移
- `docs/reverse-engineering/data/clienttool-control-oids.tsv`：
  主对话框、Panel options、Communication、SNMP trap、Wi‑Fi 状态、音量与
  FAX notification 的控件、模型偏移与 OID 对照
- `tools/clienttool_dialogs.py`：解析对话框结构并输出脱敏元数据
- `docs/reverse-engineering/data/clienttool-dialogs.tsv`：
  对话框 ID、控件 ID、类、几何位置和文本长度
- `tools/clienttool_config_names.py`：合并两份 `snmp-oid.xml`，把 147 项
  配置 OID 对齐到厂商符号名并生成完整 OID 索引
- `docs/reverse-engineering/data/clienttool-snmp-oid-index.tsv`：
  两份 XML 的 `oid`、`symbol`、`source` 索引
- `tools/clienttool_oid_sources.py`：扫描 ClientTool 中所有带 `oid` 属性的
  XML，区分绝对/相对 OID
- `docs/reverse-engineering/data/clienttool-oid-mapping-sources.tsv`：
  OID 映射源清单（两份 `snmp-oid.xml`、`JobSnmpOid.xml`、`Support.xml`、
  `snmp-discovery.xml`）
- `tools/clienttool_job_oids.py`：把 `JobSnmpOid.xml` 的相对 OID 树展开为
  绝对 OID
- `docs/reverse-engineering/data/clienttool-job-oids.tsv`：
  205 个作业符号、绝对 OID、树路径与 `oid_kind`
- `tools/clienttool_fax_ini.py`：解析 `FAX/KMSNMP4.INI` 的
  `INFO_*` 名称、OID、size/type
- `docs/reverse-engineering/data/clienttool-fax-snmp-oids.tsv`：
  144 行传真 SNMP 名称映射
- `tools/clienttool_all_oids.py`：扫描 ClientTool 全部文件的 ASCII/UTF‑16
  OID，并合并所有名称源
- `docs/reverse-engineering/data/clienttool-all-oids.tsv`：
  827 个唯一 OID 的全量清单（来源、名称、设备/库分类、147 项关联；
  不含原始字节或周边厂商文本）
- `docs/reverse-engineering/data/clienttool-config-names.tsv`：
  127 项厂商名称与匹配到的 XML 前缀
- `docs/reverse-engineering/protocol-notes.md`：PJL/SNMP 协议证据
- `docs/reverse-engineering/scan-workflow.md`：扫描与 Push Scan 调用链
- `docs/reverse-engineering/kmws-soap.md`：KM-WSDL/SOAP 调查与边界
- `docs/reverse-engineering/usb-path.md`：USB 打印/语言监视器链路与 Linux
  `usblp` 实现边界
- `tools/wsd_probe.py`：只读 WS-Discovery 探测工具
- `docs/architecture.md`：Linux 实现架构

## 内容边界

公开仓库不提交以下内容：

- 原厂安装包、EXE/DLL、固件、驱动、图标或其他资源文件；
- 完整反编译输出、伪代码导出或大段原厂代码；
- 本地化界面文本、对话框标题、菜单描述等成规模逐字提取内容；
- 维护包或其他加密容器的密钥、凭据和解包工具；
- 设备序列号、MAC、Wi-Fi 名称、密码、令牌等个人或设备敏感信息。

协议 OID、请求 ID、字段类型和高层行为摘要属于互操作性研究记录。原始厂商文件、
本地解包结果和分析工作目录应放在被 `.gitignore` 排除的 `analysis/` 下，不得
强制加入版本库。贡献规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，发布前检查见
[docs/legal/compliance.md](docs/legal/compliance.md)。

原始文本导出、维护包解包等研究辅助脚本保留在 `analysis/local-only/`，不会进入
公开仓库，因此不影响后续本地分析。公开发布前还必须清理旧 Git 历史中的受限
文件；仅删除当前工作树中的文件不够。

本仓库不包含原厂二进制；`Kyocera/`、`Kyocera.zip`、`.tools/` 与
`analysis/` 目录均被忽略。
