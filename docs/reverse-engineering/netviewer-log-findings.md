# NetViewer 历史运行日志分析

## 1. 来源与处理

本地样本：`Kyocera/NetViewer/KNV/log/kmnv.log`

- 大小约 2.98 MB，18241 行，文件时间 `2026-09-20 15:25:40 +0800`。
- 内容包含设备序列号、主机名、网络地址，以及加密后的 SNMPv3 用户名/密码块。
- **该日志不纳入版本控制，也不应公开分发。** 本文只保留脱敏后的 OID、属性名和
  非敏感值。

日志显示 NetViewer 对同一台 MA2000w（`192.168.0.220`）完成了发现和轮询。

## 2. 发现流程（已验证的部分）

日志中的关键顺序：

1. `Network discovery started`。
2. `BroadcastCollector` 向 `20.20.20.255:161` 发送 SNMP 请求，同时对
   `20.20.20.x` 做单播探测（该网段与当前测试网段不同，属于历史环境）。
3. 对目标执行 `GETNEXT 1.3.6.1.2.1.25.3.2.1.4`，读取 `hrDeviceDescr` 类型信息；
   返回的厂商 OID 包括 `1.3.6.1.4.1.1347.43.1.2.1`、`...44.1.2.1`、
   `...46.1.2.1`。
4. 读取型号：
   - `1.3.6.1.4.1.1347.43.5.1.1.36.1` → `MA2000w`（Base Model Name）
   - `1.3.6.1.4.1.1347.43.5.1.1.1.1` → `MA2000w`（Model Name）
5. 读取序列号 `1.3.6.1.4.1.1347.43.5.1.1.28.1`（本文脱敏）。
6. 读取 MAC `1.3.6.1.2.1.2.2.1.6`（`ifPhysAddress`）→ `0017C8XXXXXX`（已脱敏）。
7. 以 `1.3.6.1.4.1.1347.43.5.4.1.5.1.1` 读取系统固件。
8. 设备被识别为 `PD_KY<serial>`，随后启动 `PollingManager` 周期轮询。

2026-10-18 对当前设备用只读 SNMP GET 复核，上述 OID 的返回值与日志一致：
型号 `MA2000w`、固件 `2YW_2000.001.101`、MAC `0017C8XXXXXX`（已脱敏）。

## 3. 轮询属性

日志中的 `Extended Error Message` 列出了 112 个属性 ID。已确认有值的包括：

| 属性 ID | 名称 | 值 |
| --- | --- | --- |
| 5001 | `DEV_STATUS` | `Ready` |
| 8005 | `DEV_ALERT_CODE` | `0` |
| 5003 | `DEV_MODELNAME` | `MA2000w` |
| 5004 | `DEV_BASEDMODELNAME` | `MA2000w` |
| 5012 | `DEV_SERIALNUMBER` | 已脱敏 |
| 5014 | `DEV_SYSTEMFIRMWARE` | `2YW_2000.001.101` |
| 5015 | `DEV_ENGINEFIRMWARE` | `2Y8_1000.001.302` |
| 5016 | `DEV_MACADDRESS` | `0017C8XXXXXX`（已脱敏） |
| 5017 | `DEV_SYSUPTIME` | `1290091` |
| 5021 | `DEV_HOSTNAME` | `KMD4****`（脱敏） |
| 5030 | `DEV_SLEEPTIMER` | `1` |
| 5036 | `DEV_PAGECOUNT` | `53` |
| 5041 | `DEV_BRANDNAME` | `Kyocera` |
| 5046 | `DEV_DEFAULTINPUTNAME` | `Cassette 1` |
| 5047 | `DEV_PANELLANGUAGENAME` | `English` |
| 5005 | `DEV_PRINTSPEED` | `20` |
| 5010 | `DEV_MEMORY` | `65536` |
| 5105 | `DEV_TOTALSCANNEDPAGECOUNT` | `2` |
| 5033 | `DEV_DEFAULTINPUT` | `Cassette 1` |

许多属性返回 `Not supported` 或 `UNEXPECTED_RESPONSE`，说明不同型号/固件的属性
覆盖范围不同；不能把 112 个 ID 都视为 MA2000w 已实现。

其中 `DEV_PAGECOUNT`（5036）与 `DEV_TOTALSCANNEDPAGECOUNT`（5105）并不是
通过 SNMP 读取的。`system/Device.Base/conf/property-map.xml` 把它们映射到
`CounterInformationService`：

```xml
<CounterInformationService
    namespace="Kmnv.Core.Services.Soap.LogManagement.CouterInformation">
  <method name="counter" validator="CounterValidator" login="No">
    <section name="ACCOUNTING_PRINT_TOTAL_COUNTER">
      <property id="5036"
        path="counter_data.accounting_counter.accounting_print_total_counter.counter"
        convertor="ToIntConvertor"/>
    </section>
```

对应的 KM-WSDL 命名空间是
`http://www.kyoceramita.com/ws/km-wsdl/log/counter_information`（该字符串
可在 `Core.CoreServices.dll` 中直接读到）。这说明 NetViewer 的属性 5036
走 SOAP 计数器服务；但设备同时通过标准 Printer MIB 暴露
`prtMarkerLifeCount`（完整实例
`1.3.6.1.2.1.43.10.2.1.4.1.1`，2026-10-18 实测 `129`）。因此
`kyocera_monitor --snmp` 可以直接读取 `page_count`；此前记录为空是查询
OID 少了最后一级实例，详见 `protocol-notes.md` 第 5.4.1 节。
`counter_information` 的设备端 WSDL/SOAP 端点目前仍未取得响应，详见
`kmws-soap.md`。

轮询使用的标准 Printer MIB OID 包括（日志可见）：

```text
1.3.6.1.2.1.43.5.1.1.3.1
1.3.6.1.2.1.43.7.1.1.2 / .3
1.3.6.1.2.1.43.8.2.1.15 / .18
1.3.6.1.2.1.43.9.2.1.9 / .12 / .20
1.3.6.1.2.1.43.10.2.1.4
1.3.6.1.2.1.43.11.1.1.5 / .6 / .8 / .9
1.3.6.1.2.1.43.13.4.1.2 / .4
1.3.6.1.2.1.43.16.5.1.2
1.3.6.1.2.1.43.18.1.1.2 / .3 / .4 / .5 / .6 / .7 / .8
1.3.6.1.4.1.1347.43.5.1.1.1.1
1.3.6.1.4.1.1347.43.5.1.1.28.1
1.3.6.1.4.1.1347.43.5.1.1.36.1
1.3.6.1.4.1.1347.43.5.4.1.5.1.1
1.3.6.1.4.1.1347.46.10.1.1.5.3
```

这些 OID 的完整字段语义仍需逐项验证；此处只保留日志直接出现的地址。

## 4. 配置与 SOAP 线索

日志中的 `KmwsDeviceController` 显示：

- `adaptorParams.AdaptorSoapParams.IsUseSSL = False`（发现阶段）
- `adaptorParams.AdaptorSoapParams.IsUseSSL = True`（轮询/配置阶段）
- 设备控制器带有大量属性验证器（如 `RangeValidator`、`StringArrayValidator`），
  说明设置读写通过 SOAP/HTTP(S) 的 KMWS 接口，而不是 PJL。

日志没有记录 SOAP 请求体或响应体，因此不能据此编写配置写入实现。后续静态
分析已确认：SOAP 客户端不在 `KMSTMNW.exe`/`ClientTool.dll`，而在 NetViewer
的 .NET 程序集（`Device.Controllers.*`、`Core.CoreServices.dll`）。KM-WSDL
命名空间、默认端口和 MA2000w 的 SNMP 回退证据见
`docs/reverse-engineering/kmws-soap.md`。

对 MA2000w，日志中的 `KM-WSDL version` 为空，登录通过 SNMP OID 完成；
因此该型号的只读配置应优先使用 SNMP，SOAP 仅作为其他型号/固件的可选路径。
下一步需要在 Windows 环境抓取 HTTPS/SOAP 流量，确认 `UseWSDL` 和认证流程。

## 5. SNMP 版本行为

2026-10-18 实测：

- SNMPv2c `GET` 正常；
- SNMPv1 `GETNEXT` 正常；
- SNMPv2c `GETNEXT` 在后续复核中正常；此前“未收到响应”的结果无法复现，
  不再视为设备限制；
- SNMPv2c `GETBULK` 仍然超时，因此复刻实现默认使用 SNMPv1。

历史日志中的 `GETNEXT` 请求正常返回，与当前 v1/v2c GETNEXT 均可用的结果一致。
复刻程序若实现 SNMP 发现，可继续默认使用 SNMPv1 GETNEXT，并保留可配置版本。

## 6. 证据等级

- 已验证：日志顺序、OID 字符串、属性值、当前设备 GET 返回一致。
- 较高可信度：NetViewer 通过 SNMP 做发现/轮询，通过 SOAP/HTTPS 做配置。
- 待验证假设：属性 ID 与 OID 的一一映射、SOAP 端点、写入字段及权限模型。
