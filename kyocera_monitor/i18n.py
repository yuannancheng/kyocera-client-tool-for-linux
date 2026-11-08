"""Language negotiation and browser-side translations for the local UI."""

from __future__ import annotations

import json
from typing import Iterable

LANGUAGE_AUTO = "auto"
LANGUAGE_ZH = "zh-CN"
LANGUAGE_EN = "en-US"
SUPPORTED_LANGUAGES = (LANGUAGE_ZH, LANGUAGE_EN)
LANGUAGE_PREFERENCES = (LANGUAGE_AUTO, *SUPPORTED_LANGUAGES)

ENGLISH_TRANSLATIONS = {
    "KYOCERA 打印机": "KYOCERA Printer",
    "KYOCERA 打印机状态": "KYOCERA Printer Status",
    "语言": "Language",
    "自动（设备语言）": "Automatic (device language)",
    "简体中文": "Simplified Chinese",
    "English": "English",
    "语言设置保存失败：{error}": "Could not save language setting: {error}",
    "检查更新": "Check update",
    "正在检查…": "Checking…",
    "已是最新": "Up to date",
    "发现新版本": "New version available",
    "检查更新失败": "Update check failed",
    "发现新版本 v{latest}，当前版本 v{current}。": (
        "Version v{latest} is available; the current version is v{current}."
    ),
    "前往发布页": "View release",
    "关闭": "Close",
    "检查更新失败：{error}": "Update check failed: {error}",
    "加载中": "Loading",
    "导出计数 CSV": "Export counters CSV",
    "状态通知": "Status notifications",
    "发现打印机": "Discover printers",
    "手动添加打印机 IP，例如 192.168.0.220": (
        "Printer IP, for example 192.168.0.220"
    ),
    "添加设备": "Add device",
    "发生未知错误": "An unknown error occurred",
    "未知打印机": "Unknown printer",
    "正常": "Normal",
    "警告": "Warning",
    "未知": "Unknown",
    "不可用": "Unavailable",
    "序列号": "Serial number",
    "碳粉": "Toner",
    "面板": "Panel",
    "告警": "Alerts",
    "{count} 台设备": "{count} devices",
    "还没有设备。点击“发现打印机”，或手动输入 IP。": (
        "No devices yet. Discover printers or enter an IP address manually."
    ),
    "更新于 {time}": "Updated {time}",
    "缓存 · {time}": "Cached · {time}",
    "读取耗时 {ms} ms": "Read time {ms} ms",
    "京瓷打印机状态变化": "KYOCERA printer status changed",
    "{name} ({device}) 状态变为 {state}": (
        "{name} ({device}) changed to {state}"
    ),
    "正在搜索…": "Searching…",
    "发现 {count} 台打印机，结果已保存": (
        "Found {count} printers and saved the result"
    ),
    "已添加并保存打印机 {host}": "Added and saved printer {host}",
    "已添加打印机 {host}": "Added printer {host}",
    "刷新": "Refresh",
    "返回总览": "Back to overview",
    "固件": "Firmware",
    "地址": "Address",
    "面板显示": "Panel display",
    "累计打印页数": "Lifetime printed pages",
    "扫描计数": "Scan count",
    "感光鼓计数": "Drum count",
    "纸盒": "Trays",
    "名称": "Name",
    "状态": "Status",
    "纸张": "Paper",
    "余量": "Remaining",
    "无纸盒数据": "No tray data",
    "无告警": "No alerts",
    "最近尝试: {time}": "Last attempt: {time}",
    "设备 {device} · 读取于 {time}，耗时 {ms} ms": (
        "Device {device} · read at {time}, took {ms} ms"
    ),
    "（缓存）": " (cached)",
    "扫描预设与保存目录": "Scan presets and output folder",
    "预设": "Preset",
    "不使用预设": "No preset",
    "预设名称": "Preset name",
    "例如：A4 彩扫": "For example: A4 color scan",
    "Push Scan 槽位": "Push Scan slot",
    "不绑定": "Unbound",
    "保存目录": "Output folder",
    "扫描完成后自动保存到该目录": (
        "Save scans to this folder when complete"
    ),
    "保存当前设置为预设": "Save current settings as preset",
    "删除所选预设": "Delete selected preset",
    "保存目录设置": "Save output folder",
    "扫描": "Scan",
    "颜色": "Color",
    "使用设备当前设置": "Use current device setting",
    "彩色": "Color",
    "灰度": "Grayscale",
    "黑白": "Black and white",
    "自动黑白": "Auto black and white",
    "自动灰度": "Auto grayscale",
    "分辨率": "Resolution",
    "原稿类型": "Original type",
    "文字": "Text",
    "文字和照片": "Text and photo",
    "照片": "Photo",
    "地图": "Map",
    "浅色文字": "Light text",
    "页数": "Pages",
    "1 页": "1 page",
    "最多 {count} 页": "Up to {count} pages",
    "最多 2 页": "Up to 2 pages",
    "最多 3 页": "Up to 3 pages",
    "最多 4 页": "Up to 4 pages",
    "最多 5 页": "Up to 5 pages",
    "最多 6 页": "Up to 6 pages",
    "最多 7 页": "Up to 7 pages",
    "最多 8 页": "Up to 8 pages",
    "最多 9 页": "Up to 9 pages",
    "最多 10 页": "Up to 10 pages",
    "输出格式": "Output format",
    "高压缩 PDF": "High-compression PDF",
    "RAW（高级）": "RAW (advanced)",
    "开始扫描": "Start scan",
    "设备配置": "Device configuration",
    "按官方工具的分类逐页读取和修改。读取或应用设置时只访问当前分区；提交单个属性后会回读该属性，失败时自动尝试恢复原值。网络、凭据和重置类对象仍保持只读，避免误改后断开设备。": (
        "Browse and edit settings by category using the official tool's "
        "grouping. Reads and writes touch only the current section. Each "
        "submitted property is read back, with automatic rollback if "
        "verification fails. Network, credential, and reset objects remain "
        "read-only to avoid disconnecting the device."
    ),
    "设备默认值": "Device defaults",
    "选择分类后读取。": "Choose a category to read it.",
    "读取此分区": "Read this section",
    "尚未读取当前分区": "Current section not read yet",
    "设备当前状态": "Current device state",
    "当前设备设置": "Current device settings",
    "可修改设置": "Editable settings",
    "Wi-Fi 连接配置": "Wi-Fi connection",
    "此分类使用官方 Wi-Fi Setup Tool 的 KGETOBJ/KSETOBJ 顺序。扫描附近网络或手动填写 SSID；密码只发送到本机服务，不写入设置文件或日志。连接失败时可能需要用打印机面板恢复网络。": (
        "This section follows the official Wi-Fi Setup Tool's KGETOBJ/"
        "KSETOBJ sequence. Scan for nearby networks or enter an SSID "
        "manually. The password is sent only to the local service and is "
        "not written to settings or logs. A failed change may require "
        "restoring Wi-Fi from the printer panel."
    ),
    "扫描附近网络": "Scan nearby networks",
    "尚未执行 Wi-Fi 操作": "No Wi-Fi operation yet",
    "附近网络": "Nearby networks",
    "先扫描附近网络，或手动输入": "Scan nearby networks or enter manually",
    "安全模式": "Security mode",
    "开放网络": "Open network",
    "密码": "Password",
    "确认更改设备 Wi-Fi；连接失败可能需要用打印机面板恢复网络": (
        "Confirm the Wi-Fi change; a failed connection may require "
        "restoring the network from the printer panel"
    ),
    "连接 Wi-Fi": "Connect Wi-Fi",
    "技术详情：当前分区全部对象": "Technical details: all objects in this section",
    "名称和状态来自官方对象表。未生成编辑器的对象可能是只读状态、凭据、网络可达性相关设置，或尚未完成写入回读验证。": (
        "Names and states come from the official object table. Objects "
        "without an editor may be read-only state, credentials, network "
        "reachability settings, or fields awaiting write/readback review."
    ),
    "ID": "ID",
    "值": "Value",
    "配置基线与全量维护": "Configuration baseline and full maintenance",
    "基线和差异检查需要完整读取 147 项配置，因此只在明确执行这些维护操作时使用。": (
        "Baseline and comparison commands read all 147 configuration items, "
        "so they run only when explicitly requested."
    ),
    "保存完整配置为基线": "Save full configuration as baseline",
    "与完整基线比较": "Compare with full baseline",
    "Push Scan 状态与本地预设映射": "Push Scan status and local preset mapping",
    "读取 Push Scan 状态": "Read Push Scan status",
    "尚未读取": "Not read yet",
    "设备发现": "Device discovery",
    "尚未搜索": "Not searched yet",
    "当前: {host}": "Current: {host}",
    "当前: 默认设备": "Current: default device",
    "排队": "Queued",
    "预检": "Preflight",
    "读取配置": "Reading configuration",
    "打开会话": "Opening session",
    "启动扫描": "Starting scan",
    "取图": "Retrieving image",
    "解码": "Decoding",
    "生成文件": "Generating file",
    "保存文件": "Saving file",
    "关闭会话": "Closing session",
    "完成": "Complete",
    "内部错误": "Internal error",
    "扫描失败：{error}": "Scan failed: {error}",
    "重新扫描": "Scan again",
    "下载 {filename}": "Download {filename}",
    "正在下载 {filename}": "Downloading {filename}",
    "扫描完成：{pages} 页": "Scan complete: {pages} pages",
    " · 设备请求 {requested} / 设备返回 {effective} / 本地 {local}": (
        " · requested {requested} / device returned {effective} / local {local}"
    ),
    " · 已保存 {count} 个文件到 {folder}": (
        " · saved {count} files to {folder}"
    ),
    "所选目录": "selected folder",
    "；关闭会话警告：{error}": "; close-session warning: {error}",
    "再次扫描": "Scan again",
    "未知阶段": "Unknown stage",
    "未知错误": "Unknown error",
    "处理中": "Processing",
    "请稍候": "Please wait",
    "正在扫描…": "Scanning…",
    "正在创建扫描任务": "Creating scan job",
    "设备预设 {slot}（状态码 {code}）": (
        "Device preset {slot} (status code {code})"
    ),
    "设置加载失败：{error}": "Could not load settings: {error}",
    "保存失败：{error}": "Save failed: {error}",
    "保存目录已更新": "Output folder updated",
    "请先输入预设名称": "Enter a preset name first",
    "预设已保存": "Preset saved",
    "预设已删除": "Preset deleted",
    "（Push {slot}）": " (Push {slot})",
    "配置打开失败：{error}": "Could not open configuration: {error}",
    "配置分类不可用：{error}": "Configuration categories unavailable: {error}",
    "正在加载配置分类…": "Loading configuration categories…",
    "{editable}/{total} 项可修改": "{editable}/{total} editable",
    "{count} 项 · 只读": "{count} items · read-only",
    "可读": "Readable",
    "不可读": "Unreadable",
    "已隐藏": "Hidden",
    "只读": "Read-only",
    "当前值：": "Current value: ",
    "应用此设置": "Apply setting",
    "请输入设备支持的有效整数值": "Enter a valid integer supported by the device",
    "确认把「{label}」从当前值改为 {value}？提交后会读取设备验证，失败时尝试恢复原值。": (
        "Change “{label}” from its current value to {value}? The device "
        "will be read back for verification and the original value "
        "restored if verification fails."
    ),
    "正在写入并回读设备…": "Writing and reading back the device…",
    "属性 {id} 已写入并回读成功": (
        "Property {id} was written and read back successfully"
    ),
    "「{label}」已应用并回读成功": (
        "“{label}” was applied and read back successfully"
    ),
    "写入失败：{error}": "Write failed: {error}",
    "当前连接不提供设备写入通道": (
        "The current connection does not provide a device write channel"
    ),
    "没有可显示的已审核属性": "No reviewed editable properties are available",
    "基线：{time} · 可读 {read}/{total}": (
        "Baseline: {time} · {read}/{total} readable"
    ),
    "基线不可用：{error}": "Baseline unavailable: {error}",
    "尚未保存基线": "No baseline saved",
    "下列属性已通过官方映射和可逆写入审计；其余对象保持只读。": (
        "These properties passed official mapping and reversible-write "
        "review. Other objects remain read-only."
    ),
    "Wi-Fi 使用本分类内的专用连接流程；通用属性编辑器不对凭据类对象开放。": (
        "Wi-Fi uses the dedicated connection flow in this section. The "
        "generic property editor does not expose credential objects."
    ),
    "此分类没有已审核的通用属性编辑器，仅显示设备状态。": (
        "This section has no reviewed generic property editor, so only "
        "device state is shown."
    ),
    "当前连接的通用配置写入不可用；本分类的 Wi-Fi 连接仍使用专用 KSETOBJ 流程。": (
        "Generic configuration writes are unavailable on this connection. "
        "Wi-Fi still uses the dedicated KSETOBJ flow in this section."
    ),
    "当前连接未提供配置写入通道；这里仅展示设备读取结果。": (
        "The current connection does not provide a configuration write "
        "channel; only device reads are shown here."
    ),
    "（显示 {shown} 项，{hidden} 项设备不支持已隐藏）": (
        " ({shown} shown, {hidden} unsupported hidden)"
    ),
    "（{count} 项）": " ({count} items)",
    "“{category}”读取完成：{read}/{total} 项可读": (
        "“{category}” read complete: {read}/{total} readable"
    ),
    "正在读取“{category}”{count}…": "Reading “{category}”{count}…",
    "保存当前完整配置为新基线？敏感值会以 0600 权限保存在本机。": (
        "Save the current full configuration as the new baseline? "
        "Sensitive values are stored locally with mode 0600."
    ),
    "正在读取并保存私有基线…": "Reading and saving a private baseline…",
    "正在读取当前配置并与基线比较…": (
        "Reading the current configuration and comparing it with the baseline…"
    ),
    "基线已保存": "Baseline saved",
    "完整配置基线已保存": "Full configuration baseline saved",
    "配置变化": "Configuration changes",
    "易变遥测变化": "Volatile telemetry changes",
    "读取状态变化": "Read-status changes",
    "没有配置或读取状态变化": "No configuration or read-status changes",
    "比较完成：{changed} 个配置变化，{status} 个读取状态变化": (
        "Comparison complete: {changed} configuration changes and "
        "{status} read-status changes"
    ),
    "接口": "Interface",
    "地址类型": "Address type",
    "目标": "Target",
    "未配置": "Not configured",
    "目标匹配本机": "Target matches this computer",
    "是": "Yes",
    "否": "No",
    "上次报告结果": "Last reported result",
    "待机入口": "Listener entry point",
    "未知状态": "Unknown state",
    "设备未提供必要的 Push Scan 接口状态。": (
        "Required Push Scan interface state is unavailable."
    ),
    "设备当前选择 USB Push Scan 目标。": (
        "The device currently selects a USB Push Scan destination."
    ),
    "Push Scan 地址类型不可用或无法识别。": (
        "The Push Scan address type is unavailable or unrecognized."
    ),
    "已选择网络 Push Scan，但尚未配置目标。": (
        "Network Push Scan is selected but no target is configured."
    ),
    "已配置的 Push Scan 目标与本机匹配。": (
        "The configured Push Scan target matches this computer."
    ),
    "已配置的 Push Scan 目标与本机不匹配。": (
        "The configured Push Scan target does not match this computer."
    ),
    "无法验证已配置的 Push Scan 目标。": (
        "The configured Push Scan target could not be validated."
    ),
    "设备侧 Push Scan 目标由打印机面板/Scan Destination 设置；官方 Client Tool 只读取这组状态 OID，未提供可复现的 SET 路径，因此这里不会盲写接口或目标地址。“Push Scan 槽位”只保存 Linux 本地预设映射。命令行 --push-scan-listen 可报告 89xxx；显式加上 --push-scan-run 会执行匹配的本地预设，结果 OID 回写仍未启用。": (
        "The device-side Push Scan target is configured on the printer "
        "panel or Scan Destination page. The official Client Tool only "
        "reads these status OIDs and exposes no reproducible SET path, so "
        "this page never writes the interface or target. The Push Scan "
        "slot stores only a local Linux preset mapping. "
        "--push-scan-listen reports 89xxx; adding --push-scan-run executes "
        "a matching local preset. Result OID write-back remains disabled."
    ),
    "正在通过 SNMP 读取…": "Reading over SNMP…",
    "读取失败：{error}": "Read failed: {error}",
    "正在通过设备扫描附近网络；通常需要数秒…": (
        "Scanning for nearby networks through the device; this usually "
        "takes a few seconds…"
    ),
    "选择一个网络": "Choose a network",
    "未发现网络": "No networks found",
    "隐藏网络": "Hidden network",
    "扫描完成，共 {count} 个网络": (
        "Scan complete: {count} networks"
    ),
    "请先勾选确认框": "Select the confirmation checkbox first",
    "SSID 不能为空": "SSID cannot be empty",
    "确认把打印机切换到 Wi-Fi「{ssid}」？": (
        "Switch the printer to Wi-Fi “{ssid}”?"
    ),
    "正在写入官方 Wi-Fi 配置并等待关联…": (
        "Writing the official Wi-Fi configuration and waiting for association…"
    ),
    "已连接到 {ssid}（{security}）": (
        "Connected to {ssid} ({security})"
    ),
    "配置失败：{error}": "Configuration failed: {error}",
    "没有发现打印机": "No printers found",
    "发现结果已保存，下次启动无需重新搜索": (
        "Discovery results saved; no new search is needed next time"
    ),
    "无法连接本机后台服务；请确认 GUI/Web 服务仍在运行后重试。": (
        "Could not reach the local service. Confirm the GUI/Web service is "
        "still running and try again."
    ),
    "本机后台返回了无法解析的响应（HTTP {status}）。": (
        "The local service returned an invalid response (HTTP {status})."
    ),
    "纸张与介质": "Paper and media",
    "通信设置": "Communication settings",
    "SNMP Trap": "SNMP Traps",
    "面板与扫描": "Panel and scanning",
    "传真设置": "Fax settings",
    "Wi‑Fi": "Wi-Fi",
    "自定义纸张名称、重量、类型和纸路设置。": (
        "Custom paper names, weights, media types, and paper-path settings."
    ),
    "认证 Trap、两个收件人及其事件通知；对应官方 Trap 页。": (
        "Authentication traps, two recipients, and event notifications; "
        "corresponds to the official Trap page."
    ),
    "扬声器、报告、接收模式、转发及通信参数。": (
        "Speaker, reports, receive mode, forwarding, and communication "
        "parameters."
    ),
    "连接状态、SSID、安全模式、信号与信道；对应官方 Wi‑Fi 页。": (
        "Connection state, SSID, security, signal, and channel; corresponds "
        "to the official Wi-Fi page."
    ),
    "睡眠、错误清除、打印浓度、送纸与常用默认值；对应官方主设置页。": (
        "Sleep, error clearing, print density, paper feed, and common "
        "defaults; corresponds to the official main settings page."
    ),
    "主机名、IPv4、DHCP、LPD/Raw/WSD 和 SNMP 社区；对应官方 Communication 页。": (
        "Hostname, IPv4, DHCP, LPD/Raw/WSD, and SNMP community; corresponds "
        "to the official Communication page."
    ),
    "面板语言、默认画面、自动清除和扫描纸张尺寸；对应官方 Panel options 与扫描默认值。": (
        "Panel language, home screen, automatic clearing, and scan paper "
        "size; corresponds to official Panel options and scan defaults."
    ),
    "睡眠时间": "Sleep time",
    "自动错误清除": "Auto error clear",
    "自动错误清除超时": "Auto error clear timeout",
    "忽略纸张尺寸不匹配": "Ignore paper size mismatch",
    "打印浓度": "Print density",
    "静音模式": "Quiet mode",
    "长度单位": "Units",
    "送纸超时": "Form feed timeout",
    "自动清除面板": "Auto clear panel",
    "面板自动清除时间": "Auto clear panel time",
    "设备进入睡眠前等待的分钟数。": (
        "Minutes the device waits before entering sleep."
    ),
    "设备自动清除可恢复错误。": "Automatically clear recoverable errors.",
    "官方控件以 5 秒为单位保存。": "The official control stores units of 5 seconds.",
    "MA2000w 已验证设备值 0 与 1 可写入并恢复；界面文字含义仍待确认。": (
        "MA2000w values 0 and 1 were verified as writable and restorable; "
        "the UI label meaning still needs confirmation."
    ),
    "MA2000w 已验证设备值 11、12、13 可写入并恢复；显示名称来自 Client Tool 1.4.11.2 的纸张重量表。": (
        "MA2000w values 11, 12, and 13 were verified as writable and "
        "restorable. Display names come from the Client Tool 1.4.11.2 "
        "paper-weight table."
    ),
    "值范围为 1–5。": "Valid range: 1–5.",
    "降低打印过程噪声。": "Reduce printing noise.",
    "设备显示长度时使用的单位。": "Unit used when the device displays lengths.",
    "设备自动清除面板输入或提示。": (
        "Automatically clear panel input or messages."
    ),
    "关闭": "Off",
    "开启": "On",
    "设备值 0": "Device value 0",
    "设备值 1": "Device value 1",
    "普通 1": "Plain 1",
    "普通 2": "Plain 2",
    "普通 3": "Plain 3",
    "普通纸": "Plain paper",
    "再生纸": "Recycled paper",
    "厚纸": "Thick paper",
    "轻": "Light",
    "重 1": "Heavy 1",
    "重 2": "Heavy 2",
    "重 3": "Heavy 3",
    "预印纸": "Preprinted paper",
    "公函信笺": "Letterhead",
    "标签纸": "Labels",
    "铜版纸": "Coated paper",
    "彩色纸": "Colored paper",
    "预打孔纸": "Prepunched paper",
    "卡片纸": "Cardstock",
    "粗糙纸": "Rough paper",
    "精细纸": "Fine paper",
    "高质量纸": "High-quality paper",
    "牛皮纸": "Kraft paper",
    "信封纸": "Envelope",
    "信封 #6": "Envelope #6",
    "信封 #9": "Envelope #9",
    "信封 #10": "Envelope #10",
    "信封 DL": "Envelope DL",
    "信封 C5": "Envelope C5",
    "信封 Monarch": "Envelope Monarch",
    "自定义": "Custom",
    "自定义 1": "Custom 1",
    "自定义 2": "Custom 2",
    "自定义 3": "Custom 3",
    "自定义 4": "Custom 4",
    "自定义 5": "Custom 5",
    "自定义 6": "Custom 6",
    "自定义 7": "Custom 7",
    "自定义 8": "Custom 8",
    "自定义尺寸": "Custom size",
    "未识别的纸张尺寸": "Unknown paper size",
    "未识别的介质类型": "Unknown media type",
    "未识别的纸张重量": "Unknown paper weight",
    "毫米": "Millimeters",
    "英寸": "Inches",
    "分钟": "minutes",
    "秒": "seconds",
    "默认纸张尺寸": "Default paper size",
    "默认介质类型": "Default media type",
    "睡眠模式": "Sleep mode",
    "关机定时器": "Power off timer",
    "自动错误清除等待时间": "Auto error clear timeout",
    "Wi-Fi 连接状态": "Wi-Fi connection state",
    "Wi-Fi 启用状态": "Wi-Fi enable state",
    "Wi-Fi 名称（SSID）": "Wi-Fi SSID",
    "Wi-Fi 安全模式": "Wi-Fi security mode",
    "Wi-Fi 信道": "Wi-Fi channel",
    "Wi-Fi 信号强度": "Wi-Fi RSSI",
}


def normalize_language_preference(value: object) -> str:
    """Return one supported language preference or raise ``ValueError``."""

    if value is None:
        return LANGUAGE_AUTO
    if not isinstance(value, str):
        raise ValueError("language must be a string")
    normalized = value.strip()
    aliases = {
        "auto": LANGUAGE_AUTO,
        "zh": LANGUAGE_ZH,
        "zh-cn": LANGUAGE_ZH,
        "zh-hans": LANGUAGE_ZH,
        "en": LANGUAGE_EN,
        "en-us": LANGUAGE_EN,
    }
    result = aliases.get(normalized.lower())
    if result is None:
        raise ValueError(
            "language must be one of auto, zh-CN or en-US"
        )
    return result


def _accepted_languages(header: str | None) -> Iterable[tuple[str, float]]:
    if not header:
        return ()
    weighted: list[tuple[str, float]] = []
    for index, part in enumerate(header.split(",")):
        fields = [field.strip() for field in part.split(";")]
        tag = fields[0].lower()
        if not tag or tag == "*":
            continue
        quality = 1.0
        for field in fields[1:]:
            if not field.lower().startswith("q="):
                continue
            try:
                quality = float(field[2:])
            except ValueError:
                quality = 0.0
        if quality <= 0:
            continue
        weighted.append((tag, quality))
    return sorted(weighted, key=lambda item: item[1], reverse=True)


def match_language(header: str | None) -> str | None:
    """Match an ``Accept-Language`` header to a supported UI language."""

    for tag, _quality in _accepted_languages(header):
        primary = tag.split("-", 1)[0]
        if primary == "zh":
            return LANGUAGE_ZH
        if primary == "en":
            return LANGUAGE_EN
    return None


def resolve_language(
    preference: object,
    accept_language: str | None,
) -> str:
    """Resolve ``auto`` or a manual preference, falling back to Chinese."""

    normalized = normalize_language_preference(preference)
    if normalized != LANGUAGE_AUTO:
        return normalized
    return match_language(accept_language) or LANGUAGE_ZH


def preferred_language_from_environment() -> str:
    """Resolve the GTK shell language from standard Unix locale variables."""

    import os

    value = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    return match_language(value.replace("_", "-")) or LANGUAGE_ZH


I18N_RUNTIME = r"""
<script>
(() => {
  const data = window.KYOCERA_I18N || {
    locale: "zh-CN",
    preference: "auto",
    translations: {}
  };
  const reverse = {};
  for (const [source, translated] of Object.entries(data.translations || {})) {
    if (!(translated in reverse)) reverse[translated] = source;
  }
  const interpolate = (template, vars = {}) =>
    String(template).replace(/\{([A-Za-z0-9_]+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(vars, name)
        ? String(vars[name])
        : match
    );
  const localizePattern = (value) => {
    if (data.locale !== "en-US") return value;
    let match = /^(.+)纸张重量$/.exec(value);
    if (match) return `${translate(match[1])} paper weight`;
    match = /^(.+)重量$/.exec(value);
    if (match) return `${translate(match[1])} weight`;
    match = /^(.+)（设备值 (\d+)）$/.exec(value);
    if (match) {
      return `${localizePattern(match[1])} (device value ${match[2]})`;
    }
    match = /^(\d+(?:\.\d+)?) 分钟$/.exec(value);
    if (match) return `${match[1]} minutes`;
    match = /^(\d+(?:\.\d+)?) 秒$/.exec(value);
    if (match) return `${match[1]} seconds`;
    match = /^(\d+(?:\.\d+)?) 毫米$/.exec(value);
    if (match) return `${match[1]} millimeters`;
    match = /^(\d+(?:\.\d+)?) 英寸$/.exec(value);
    if (match) return `${match[1]} inches`;
    return value;
  };
  function translate(source, vars = {}) {
    if (source == null) return "";
    const text = String(source);
    const localized = data.locale === "zh-CN"
      ? (reverse[text] || text)
      : ((data.translations || {})[text] || localizePattern(text));
    return interpolate(localized, vars);
  }
  function translateValue(value) {
    if (value == null) return "";
    const text = String(value);
    if (data.locale === "zh-CN" && reverse[text]) return reverse[text];
    if (data.locale === "en-US") {
      return (data.translations || {})[text] || localizePattern(text);
    }
    return text;
  }
  function applyStatic(root = document) {
    document.documentElement.lang = data.locale;
    root.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = translate(element.dataset.i18n);
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = translate(element.dataset.i18nPlaceholder);
    });
    root.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      element.setAttribute(
        "aria-label",
        translate(element.dataset.i18nAriaLabel)
      );
    });
    if (document.title) document.title = translate(document.title);
  }
  async function saveLanguage(select) {
    const previous = data.preference;
    select.disabled = true;
    try {
      const response = await fetch("/api/language", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({language: select.value})
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || response.status);
      location.reload();
    } catch (error) {
      select.value = previous;
      select.disabled = false;
      alert(translate("语言设置保存失败：{error}", {error: String(error)}));
    }
  }
  function bindLanguageSelector() {
    const select = document.getElementById("language-select");
    if (!select) return;
    select.value = data.preference;
    select.addEventListener("change", () => saveLanguage(select));
  }
  window.KYOCERA_LOCALE = data.locale;
  window.KYOCERA_LANGUAGE_PREFERENCE = data.preference;
  window.I18n = {
    locale: data.locale,
    preference: data.preference,
    applyStatic,
    bindLanguageSelector,
    translate,
    value: translateValue
  };
  window.t = translate;
  window.tv = translateValue;
  window.addEventListener("DOMContentLoaded", bindLanguageSelector);
})();
</script>
"""


def render_i18n_bootstrap(preference: str, effective: str) -> str:
    """Return one JSON bootstrap script for a rendered page."""

    payload = json.dumps(
        {
            "locale": effective,
            "preference": preference,
            "translations": ENGLISH_TRANSLATIONS,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return (
        f"<script>window.KYOCERA_I18N={payload};</script>\n"
        + I18N_RUNTIME
    )


def render_localized_page(
    html: str,
    *,
    preference: str,
    effective: str,
) -> str:
    """Inject locale metadata and browser translations into a page."""

    bootstrap = render_i18n_bootstrap(preference, effective)
    return html.replace(
        '<html lang="zh-CN">',
        f'<html lang="{effective}">',
        1,
    ).replace("</head>", bootstrap + "</head>", 1)
