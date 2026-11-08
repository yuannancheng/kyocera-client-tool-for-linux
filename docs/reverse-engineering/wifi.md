# Wi-Fi 配置协议与 Linux 实现

## 1. 范围与样本

本文记录 MA2000w 的 Wi-Fi 状态、AP 扫描和连接流程。协议证据来自：

| 文件/样本 | SHA-256 | 用途 |
| --- | --- | --- |
| `WifiSetupToolModels.dll` | `d7aa7eb4cf0d9a3f100056a863b445864a3aa947fad36affe695ac809dcf4e4c` | 47 个 OID 常量 |
| `WifiSetupToolViewModels.dll` | `d85062a2d4076c6a817cd5ae4d2739298d59346f5f298184d11a537615c21347` | KGETOBJ/KSETOBJ 调用顺序和状态判断 |
| `DeviceWifiSettingsService.dll` | `4ec5aed4b934003e422b8bf4e856193c39a754c1935c4364a4b7d904f80951b2` | AP 列表字段解析 |
| MA2000w USB/网络真机 | USB `0482:0d51`，固件 `2022.08.22 2YW_2000.001.101` | 状态与扫描验收 |

公开文档不记录实际 SSID、BSSID、PSK 或序列号。

## 2. 应用层请求

官方 Wi-Fi Setup Tool 的 ViewModel 最终调用 Windows mailslot；应用层参数为：

```text
GET:<operation>:<absolute OID>
SET:<operation>:<absolute OID>:<value>
```

Linux 使用设备已经验证的同一 PJL 对象接口：

```text
@PJL KGETOBJ OBJ="1.<relative OID>"
@PJL KSETOBJ OBJ="1.<relative OID>" VALUE =<value>
```

字符串 SET 值使用双引号。SSID、WEP key 和 PSK 在发送前转成 UTF-8 十六进制
文本；设备上的当前 SSID 也以无分隔符的大写十六进制返回。

## 3. 状态对象

| 相对 OID | 语义 | 观测/枚举 |
| --- | --- | --- |
| `40.42.1.1.1.1` | 连接状态 | `3=Connected`，其它值不是已确认的 connected |
| `40.42.1.1.3.1` | 启用/检查状态 | MA2000w 连接时为 `2`；其它值语义未由当前方法调用方确认 |
| `40.42.1.1.4.1` | 当前 SSID | UTF-8 十六进制文本 |
| `40.42.1.1.5.1` | 安全模式 | `0` Open、`1` WEP、`2` WPA/WPA2 PSK AES、`3` WPA/WPA2 PSK Auto、`4` WPA2 PSK AES |
| `40.42.1.1.6.1` | 信道 | 整数 |
| `40.42.1.1.7.1` | RSSI | dBm 整数 |

MA2000w 真机在 TCP 9100 和 USB 打印接口两条路径返回一致的已连接状态、
安全模式、信道和 RSSI。

## 4. AP 扫描

官方 `GetAccessPointsList()` 首先：

1. 将 `40.39.1.1.10.1.1` 设置为 `1`，触发 AP 扫描；
2. 读取同一对象作为结果数量；扫描期间可暂时返回 `-1`；
3. 对每个 `1..N` 实例读取 SSID、安全模式、BSSID 和 RSSI；
4. SSID 字段按十六进制解码为 UTF-8。

列 OID：

| 列 | 相对 OID 前缀 |
| --- | --- |
| SSID | `40.39.1.1.1.1` |
| security | `40.39.1.1.2.1` |
| BSSID | `40.39.1.1.3.1` |
| RSSI | `40.39.1.1.6.1` |

MA2000w 真机扫描从 `-1` 转为非负数量并返回 AP 列表。USB 和 TCP 9100 均已
完成只读结果验收；本文不记录本次环境的网络标识。

## 5. 连接顺序

官方 `ConnectToAccessPoint()` 按以下顺序逐项发送 `WIFI_SET_AP`：

| 顺序 | 相对 OID | 值 |
| --- | --- | --- |
| 1 | `40.40.1.1.1.1` | SSID 的 UTF-8 十六进制文本 |
| 2 | `40.40.1.1.2.1` | security 整数 |
| 3 | `40.40.1.1.3.1` | BSSID 文本 |
| 4 | `40.40.1.1.7.1` | WEP key index |
| 5 | `40.40.1.1.8.1` | WEP key 十六进制文本 |
| 6 | `40.40.1.1.9.1` | WPA/WPA2 PSK 十六进制文本 |

每一步的 `STATUS` 必须为 `0`。随后轮询 `40.40.1.1.10.1`；当前代码只把
`STATUS=0` 且 `VALUE=0` 视为设置成功，并要求连接状态对象变为 `3`。

Linux `kyocera_monitor.wifi.connect_access_point` 复刻该顺序。CLI 和 Web API
不会持久化密码；Web API 只接受回环客户端并打印阶段名称，不打印 secret。
本次未用新凭据覆盖现有可用网络，因此真实“更换 AP”仍未做破坏性验收。

## 6. Linux 入口

```bash
python3 -m kyocera_monitor --usb --wifi-status --json
python3 -m kyocera_monitor --usb --wifi-scan --json
python3 -m kyocera_monitor --host 192.168.0.220 --wifi-status --json
KYOCERA_WIFI_PASSWORD='...' python3 -m kyocera_monitor \
  --usb --wifi-connect SSID --wifi-security 4
```

Web/GUI 设备页提供状态、扫描和连接控件；连接要求显式确认框。

该页面可用于 Wi-Fi 尚未配置、没有可用 IP 地址的首次初始化场景：默认
GUI/Web 会枚举 USB 打印机，并允许直接以 `/dev/usb/lp*` 或临时
`libusb:<bus>:<address>` 选择设备。设备页再把该选择传给
`WifiWorkbench`，由 USB Printer interface 执行同一套 KGETOBJ/KSETOBJ。
USB 动态地址只存在于当前进程，不写入保存的打印机列表。

密码仍只在当前 HTTP 请求和短生命周期 USB 命令中处理，不持久化。连接会改变
设备网络，UI 要求勾选确认；若新 AP 不可用，设备可能需要通过面板或 USB
重新配置。
