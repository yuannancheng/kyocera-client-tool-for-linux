# 逆向工具与复现环境

## 1. 证据优先级

恢复功能时，优先级如下：

1. 官方二进制在受控环境中的真实输入、输出和状态转换。
2. 官方二进制对应的反编译代码、字符串和常量表。
3. 项目已有的设备实测结果。
4. 文档推断或设计建议。

第 1、2 项冲突时，以可复现的原始证据为准，并同步修正旧文档。终端功能不得
依赖官方 DLL/EXE；Wine 和官方二进制只用于研究及行为对照。

## 2. 已安装环境（2026-10-29）

为加载 32 位官方扫描 DLL，当前主机安装了：

```text
wine        10.0~repack-12ubuntu1
wine64      10.0~repack-12ubuntu1
gcc-mingw-w64-i686  13.2.0-6ubuntu1+26.1
```

安装命令：

```bash
pkexec apt-get install -y wine64 wine gcc-mingw-w64-i686
```

Wine 使用独立前缀，避免污染默认 Windows 环境：

```text
/home/ync/.wine-kyocera-scan
```

正常设置：

```bash
export WINEPREFIX=/home/ync/.wine-kyocera-scan
export WINEDEBUG=-all
```

执行时若出现 `XDG_RUNTIME_DIR ... invalid`，不影响无窗口控制台程序；仍应以
进程退出码和标准输出为准。

## 3. 官方 DLL 诊断宿主

公开源码：

```text
tools/kmscn_driver_harness.c
tools/kmscn_capture_server.py
```

编译官方 DLL 的 32 位 C 调用宿主：

```bash
mkdir -p analysis/local-only/kmscn-harness
i686-w64-mingw32-gcc -O2 -Wall -Wextra \
  -Wno-cast-function-type \
  -o analysis/local-only/kmscn-harness/kmscn_driver_harness.exe \
  tools/kmscn_driver_harness.c
```

宿主支持：

```text
service-info
capability
open-session
open-session-empty
start-scan
scan-sequence
```

该宿主只用于获取官方 DLL 的请求/响应行为，不属于正式 Linux 扫描实现。

## 4. 回环请求捕获

本机 `sing-box` 默认占用 `127.0.0.1:9090`，因此研究捕获使用回环别名：

```bash
pkexec --user ync python3 \
  tools/kmscn_capture_server.py \
  --host 127.0.0.2 --port 9090 --requests 4 \
  --output /tmp/kmscn-official-full-sequence.http
```

另一个终端执行：

```bash
pkexec --user ync env \
  WINEPREFIX=/home/ync/.wine-kyocera-scan \
  WINEDEBUG=-all \
  wine analysis/local-only/kmscn-harness/kmscn_driver_harness.exe \
  analysis/local-only/twain-2.1.4412/Scanner/TWAIN/KMSCNAPI.dll \
  http://127.0.0.2 scan-sequence
```

捕获器按请求体中的 action 返回最小合成响应，用于观察以下操作的 XML：

```text
get_service_information
get_capability
open_session
start_scan
retrieve_image
close_session
```

不要将 `analysis/`、官方 DLL、安装包或含设备凭据的日志提交到公开仓库。

## 5. 已完成的行为对照

- 官方扫描默认使用 SOAP 1.2，并发送 `wsa:Action` SOAP Header。
- HTTP 头为 `gSOAP/2.7`、`application/soap+xml; charset=utf-8`、带引号
  SOAPAction、显式 `Content-Length` 和 `Connection: close`。
- `get_service_informationRequest` 体已逐字节复刻，1657 字节、SHA-256
  `ae4f8f9a43f2f46a3b76e2a1190dd5990d62d1699aaaeb14ac1264def76f3a0c`。
- 官方会话顺序为 `open_session -> start_scan -> retrieve_image* ->
  close_session`；取图必须先等待 `IMAGE_CREATING_NOW` 消失，最后读取
  `ALL_GET_COMPLETE`，再关闭会话。
- MA2000w 返回 XOP multipart 图像；RAW 分带容器由长度、命令、颜色平面、
  宽、高和阴影校准数据组成。

正式实现见 `kyocera_monitor/kmscn.py`、`kyocera_monitor/kmscn_raw.py` 和
`tools/kmscn_scan.py`，不依赖 Wine 或官方 DLL。
