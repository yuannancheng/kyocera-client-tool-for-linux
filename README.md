# KYOCERA Client Tool for Linux

独立的、非官方 Linux 打印机客户端，面向 Kyocera 设备（当前验证机型
MA2000w）。项目通过公开的 PJL/SNMP 行为和互操作性测试实现状态读取与网络
扫描：支持 TCP 9100、USB `usblp`、只读 SNMP 和 KM-WSDL 扫描路径。

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

官方 Client Tool 30 项用户功能的证据、当前复刻状态和交付顺序见
[`docs/official-feature-parity-plan.md`](docs/official-feature-parity-plan.md)。

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
python3 -m kyocera_monitor --host 192.168.0.220 --scan \
  --scan-color FULL_COLOR --scan-format png --scan-output /tmp/scan.png
python3 -m kyocera_monitor --host 192.168.0.220 --scan \
  --scan-color GRAYSCALE --scan-format jpeg --scan-output /tmp/scan.jpg
python3 -m kyocera_monitor --host 192.168.0.220 --config
python3 -m kyocera_monitor --host 192.168.0.220 --config --json
python3 -m kyocera_monitor --host 192.168.0.220 --config --snmp
python3 -m kyocera_monitor --host 192.168.0.220 --push-scan \
  --snmp-version 2c --json
python3 -m kyocera_monitor --host 192.168.0.220 --web
python3 -m kyocera_monitor --web --web-open
python3 -m kyocera_monitor --host 192.168.0.220 --snmp --web --web-port 8080
python3 -m kyocera_monitor --discover
python3 -m kyocera_monitor --discover --json
python3 -m kyocera_monitor --discover --discover-subnet 192.168.0.0/24
python3 tools/kmscn_probe.py 192.168.0.220
python3 tools/kmscn_probe.py 192.168.0.220 --capability --json
python3 tools/kmscn_probe.py 192.168.0.220 --preflight --json --raw
python3 tools/kmscn_probe.py 192.168.0.220 --https --insecure --json
python3 tools/kmscn_scan.py 192.168.0.220 \
  --local-format png --decoded-output /tmp/kyocera-scan.png
python3 tools/kmscn_scan.py 192.168.0.220 \
  --color GRAYSCALE --local-format jpeg \
  --decoded-output /tmp/kyocera-gray.jpg
```

退出码：`0` 状态正常，`1` 未发现打印机或配置导出没有读到任何对象，`2` 连接或
协议错误，`3` 设备返回警告状态码，`4` 型号不匹配。

`tools/kmscn_probe.py` 是网络扫描协议的只读探测工具。它复现原厂网络 TWAIN
驱动的 `get_service_information` 和 `get_capability` 请求，用于验证 HTTP 9090
或 HTTPS 9091 上的 KM-WSDL 服务及三类扫描能力。能力响应会保留完整 XML
层级，不提前把未知的重复元素解释为数组。探针不会打开扫描会话、开始扫描、
取图或修改设备设置。MA2000w 上已实测服务信息、能力、默认配置、打开会话、
开始扫描、取图和关闭会话。详细边界和复现记录见
[`docs/reverse-engineering/scan-workflow.md`](docs/reverse-engineering/scan-workflow.md)。
`--preflight` 复刻驱动的顺序：只有服务信息成功后才发送 capability；网络异常
会以结构化 JSON 报告失败阶段，并明确 capability 未发送。
该探针的退出码为 `0` 请求成功、`1` 被测服务拒绝请求、返回 Fault 或没有返回
任何可识别能力项、`2` 连接或协议错误。

扫描编排位于 `kyocera_monitor.scan`，不加载官方 DLL。主程序和 Web/GUI 先执行
与原厂驱动一致的预检，读取设备默认扫描配置，再执行
`open_session -> start_scan -> retrieve_image -> ALL_GET_COMPLETE ->
close_session`。MA2000w 返回私有 RAW 分带流；`kyocera_monitor/kmscn_raw.py`
按原厂解析状态机还原校准、三颜色平面分带和阴影校正。灰度 RAW 使用单一颜色值
`1` 平面，也已按同一官方校准公式解码。

设备请求格式和本地导出格式分开。MA2000w 固定请求已验证的 RAW，用户可以下载
PNG、PDF、JPEG、TIFF、高压缩 PDF、XPS、BMP 或原始 RAW；`tools/kmscn_scan.py`
只保留为兼容适配器。PNG/PDF/BMP/RAW 使用标准库；JPEG、TIFF 以及内嵌 JPEG
的 PDF/XPS 使用 Pillow。官方实现中的 `retrieve_imageResponse/file_size`
只被反序列化和清零，没有作为传输总长使用；客户端因此以 HTTP 响应上限和实际
`image_data` 长度保护读取，不校验该设备报告值。

扫描参数只接受官方 DLL 枚举表中的 token，包括颜色、分辨率、单双面、
`AUTO/PLATEN/ADF` 原稿位置、连续扫描 `OFF/ON`、原稿类型和输出格式。
多页取图处理 `CONTINUE_SCAN`、`IMAGE_CREATING_NOW`、每页 `SUCCESS` 和最终
`ALL_GET_COMPLETE`，可用 `--max-pages` 限制保存页数。解码依据设备响应中的
`file_type`，不依据请求参数；MA2000w 请求 JPEG 时仍实测返回 RAW，因此 JPEG
文件由 Linux 本地从 RAW 图像导出，不宣称与设备原生 JPEG 逐字节一致。
单次取图默认最多接受 64 MiB；需要更高分辨率/更大响应时，可用
`--max-response-bytes` 显式提高内存上限。

MA2000w 当前验证了 2496×3520 RGB 和灰度平板单页扫描。该机型没有输稿器，
因此 ADF、双面和多页字段已按官方协议实现并完成模拟状态机测试，但尚未在
具备相应硬件的其他机型上验证，不能表述为跨机型兼容已验证。
PNG/PDF/BMP/RAW 路径只需要 Python 标准库；JPEG/TIFF/高压缩 PDF/XPS 路径
使用 Pillow。Wine、MinGW 和官方 DLL 仅用于受控逆向对照，环境与复现步骤见
[`docs/reverse-engineering/tooling.md`](docs/reverse-engineering/tooling.md)。

## 图形界面

`./kyocera-gui` 或 `python3 -m kyocera_monitor --gui` 打开原生 GTK3 窗口。
窗口内部是同一个本地 Web 仪表盘，服务只监听 `127.0.0.1` 的随机端口，关闭窗口即
退出。详情页可选择扫描参数、查看阶段进度并下载结果。启动时不需要先指定
打印机：可以在页面顶部手动输入 IP，或点击
“发现打印机”使用 SNMP 广播/WS-Discovery 搜索。启动时也可以加
`--host 192.168.0.220` 直接进入该设备。

原生窗口依赖 GTK3 与 WebKit2 4.1（Debian/Ubuntu 包名通常为
`gir1.2-gtk-3.0`、`gir1.2-webkit2-4.1`）。缺少依赖时 `--gui` 会返回退出码 2
并提示改用 `--web`。

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

安装会从 Python 包索引取得 Pillow，并生成 `kyocera-monitor`、
`kyocera-gui` 和 `kyocera-kmscn-probe` 三个入口。

已经存在且内容不同的文件默认不会被覆盖；确认要替换时加 `--force`。

## Debian 安装包

仓库可直接构建不包含原厂程序的架构无关 Debian 包：

```bash
python3 tools/build_deb.py
sudo apt install ./dist/kyocera-monitor_0.2.3-1_all.deb
```

构建过程只使用本地 Python 和 `dpkg-deb`，不联网。包的运行依赖声明为
`python3`、`python3-pil`、`python3-gi`、`gir1.2-gtk-3.0` 和
`gir1.2-webkit2-4.1`，由 APT 按发行版提供。构建与验证边界见
[`packaging/README.md`](packaging/README.md)。AppImage 是后续便携目标，需要
另外封装 Python、GTK 和 WebKitGTK；当前首发产物为 `.deb`。

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

配置文件读取可以保存为完整性受保护的本地基线：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-save kyocera-config-baseline.json

kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-compare kyocera-config-baseline.json
```

快照以 `0600` 权限原子写入，默认不覆盖已有文件；`--config-force` 可显式替换。
比较会绑定传输通道和目标地址，只在确认同一目标后报告差异；目标明确变更时可
使用 `--config-allow-target-mismatch`。快照含设备原始配置，可能包括 SNMP
community、Wi-Fi SSID、系统联系人或位置，不能提交到公开仓库。比较发现差异时
退出码为 `1`，一致时为 `0`。Wi-Fi 连接状态、RSSI 和信道作为只读易变观测
单独列出，不把自然变化计为配置差异；配置值变化和读取状态变化仍返回 `1`。
当前不发送 PJL `KSETOBJ`。研究用途的 CLI 仍可在用户显式确认后，通过
SNMPv2c 执行 `Auto error clear` 或 `Quiet mode` 的 `OFF -> ON -> OFF`
回滚实验；正式 Web/GUI 不暴露这些测试入口。写入边界见
`docs/reverse-engineering/config-write-safety.md`。

下一个写入候选可先做只读资格审查：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-candidates
```

报告当前只评估 item 50 `Quiet mode`（`1001.2.1.1.1.14.1`）。它核对对象是否
可读、类型是否为整数、当前值是否落在已记录的 `OFF/ON` 范围，并把“当前读取
有效”和“允许写入”分开。官方静态路径已确认 `0x455` 控件值经模型 `+0x18`
序列化为该 OID 的整数 `0/1`，网络和 USB 写入器都消费同一记录；原厂 item 50
差异分支不设置控制器重启请求。MA2000w 已通过 SNMPv2c 写为 `ON`、回读 `1`、
恢复 `OFF` 并回读 `0`；随后 147 项比较无持久配置变化或读取状态变化。
`mapping_confidence` 因而是 `device_verified`，但候选报告不构成后续写入授权，
`write.allowed` 仍固定为 `false`，并保留失败恢复和再次明确授权的边界。
`--json` 只输出 `candidate_report` 摘要，不附带完整 147 项对象表；该模式不
直接生成写入计划，也不发送任何 `KSETOBJ` 或 SNMP SET。

Push Scan 可通过一次只读 SNMP GET 检查当前接口、地址类型、目标和上次结果：

```bash
kyocera-monitor --host 192.168.0.220 --push-scan \
  --snmp-version 2c --json
```

官方 OID 语义把接口 `0` 定义为 USB、`1` 定义为 NETWORK，地址类型
`1/2/3` 分别为 IPv4、IPv6 和 HostName，结果 `0/1` 为 OK/NG。Linux 会进一步
比较目标是否匹配本机接口或主机名，并区分 `usb_destination`、
`not_configured`、`ready` 和 `other_host`。MA2000w 真机当前返回
`interface=USB`、IPv4 `0.0.0.0`、IPv4 地址类型和上次结果 `OK`，因此网络
Push Scan 明确未配置。该探针不接收设备触发器、不执行预设、不回写结果；
官方预设号选择和完整触发时序仍是待验证项。

可基于基线生成单字段写入预演。计划器支持：

- item 2 `Auto error clear`：可继续交给获准的 SNMPv2c 回滚执行器；
- item 50 `Quiet mode`：可交给相同令牌、相同基线和同 OID 回读约束的一次性
  回滚执行器。

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-plan kyocera-config-baseline.json --config-set 2=OFF

kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-plan kyocera-config-baseline.json --config-set 50=ON
```

计划会检查目标、传输、全表配置漂移和读取状态变化，并给出当前值、目标值、
回滚值、官方 `KMUTLCFG.exe` 命令预览、SNMP 参数预览和 SHA-256 确认令牌。
`--json` 输出完整的 `write_plan`。令牌、基线、目标、旧值和新值必须完全一致，
执行器才允许发出 SET。

获准的真机实验使用同一基线、同一赋值和计划返回的令牌：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-apply kyocera-config-baseline.json \
  --config-set 2=ON --config-confirm sha256:<token>
```

执行器仅支持 SNMPv2c、item 2 `Auto error clear` 和 item 50 `Quiet mode`
的 `OFF -> ON -> OFF`。SET 后必须读到 `1`，随后立即写回 `0` 并再次读到
`0`；即使正向写入或回读失败也会尝试回滚。其他对象、反向操作、PJL 写入和
设备重置均被拒绝。

无害整数字段可用固定白名单做可恢复批量审计：

```bash
kyocera-monitor --host 192.168.0.220 --config --snmp \
  --config-audit-safe kyocera-config-baseline.json
```

该模式覆盖睡眠、超时、纸张重量、打印浓度、单位和面板自动清除等 25 个字段，
逐项执行“改值、回读、恢复、回读”。网络、Wi-Fi、SNMP 凭据、传真、重置触发、
字符串及未知语义字段均排除。任一恢复失败会停止后续字段，命令返回非零。

`tools/clienttool_ui_strings.py` 只提取控件 ID、字符串资源 ID、文本是否存在
及其长度，不输出本地化标签或组合框选项，生成
`docs/reverse-engineering/data/clienttool-ui-controls.tsv`。结合模型偏移后，
`43.5.1.1.23.1` 标为睡眠时间、`42.5.1.1.43.1` 标为关机定时器、
`1001.2.1.1.1.14.1` 标为 Quiet mode；Quiet mode 已通过真机写入回读，
另外两项仍标记为 `confidence: "inferred"`。

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

`--web` 启动本地状态与扫描页，默认监听 `127.0.0.1:8080`，可以不带 `--host`
启动。
`/` 是设备总览页，
`/device?host=<地址>` 是单设备详情页；`/api/devices` 返回所有已知设备的快照，
`POST /api/devices`（JSON `{"host": "192.168.0.220"}`）把手动输入的主机加入
已保存设备并写入
`$XDG_CONFIG_HOME/kyocera-monitor/settings.json`；重启 Web/GUI 后自动恢复，
`/api/status?host=<地址>` 返回单个设备，`/healthz` 用于存活检查。
`POST /api/scans` 创建后台扫描任务，任务 ID 可通过 `/api/scans/<id>` 查询
阶段，成功后的文件由 `/api/scans/<id>/files/<序号>` 下载。
总览最多用 4 个线程并行取快照，单设备缓存 1 秒，页面每 10–15 秒刷新。
总览页上的“发现打印机”会调用 `/api/discover`，发现结果自动加入已保存设备、
出现在总览中，并在下次启动时恢复；手动输入的主机使用同一持久化列表。
详情页展示 Lifetime/Scan/Drum 计数、睡眠模式、自动错误清除和表单超时；
其中 Lifetime counter 已由 PJL/SNMP 双向核对为页计数。扫描区提供颜色、
分辨率、原稿类型、页数和输出格式，并显示设备请求格式、设备返回格式和本地
最终格式，避免把 RAW 请求误认为 RAW 文件。用户可把当前扫描参数保存为
本地预设，并指定一个绝对目录在扫描完成后自动保存。总览页可导出全部已知
设备的计数 CSV，并可显式开启浏览器状态通知；通知只观察页面已经读取的状态，
不是设备主动推送。
详情页的统一配置区可只读采集 147 项配置，展示面板与 Wi‑Fi 状态，保存
`0600` 私有基线并比较差异；SNMP community、Wi‑Fi SSID 等敏感值在页面中
隐藏。Web/GUI 不提供配置写入、写入计划或回滚实验入口，也不注册
`/api/config/plan` 和 `/api/config/apply`；受控实验只保留在研究用途的 CLI
工作流中。详情页的 Push Scan 区通过 `/api/push-scan` 显示只读就绪状态，
不会启动扫描或写结果 OID。
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

当前 276 个测试覆盖 PJL 解析/帧格式、分段补发与合并、KGETOBJ 结构化字段、
147 项配置对象表与 CLI 配置导出、`KMUTLCFG` UI 控件字符串提取、
147 项对象→模型偏移映射与首批控件→OID 对照、
配置 SNMP 后备读取、
桌面菜单安装/卸载、
SNMP 编码与 walk/行读取边界、SNMP 到 `PrinterSnapshot` 的字段映射、USB
sysfs 发现、PTY 假设备往返、SNMP/WSD 发现与结果合并，以及 Web 快照缓存、
设备持久化列表与手动添加、重启恢复、多设备并发读取、JSON、页面自包含性、
无默认设备启动
和 GUI 依赖缺失时的回退、KM-WSDL 扫描多页/ADF 状态机、灰度 RAW 解码、
PNG/PDF/JPEG/TIFF/高压缩 PDF/XPS 导出、扫描后台任务与下载、设备忙保护、
`file_size` 不作为传输长度、截断 chunked 响应处理、扫描预设/保存目录、
计数 CSV、配置工作台/敏感值脱敏/写入令牌、Debian 包内容和公开树合规检查。
Push Scan 专项测试覆盖 IPv4/IPv6/主机名匹配、USB 与未配置状态、缺失对象、
上次结果语义、CLI 只读读取和 Web API。

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
