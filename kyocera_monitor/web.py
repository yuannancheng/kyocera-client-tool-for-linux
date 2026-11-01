"""Read-only local web dashboard for a printer status snapshot.

The dashboard serves the same ``PrinterSnapshot`` data as ``--json``. It binds
to loopback by default and never sends write commands to the printer.
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, quote, urlsplit

from .parser import PrinterSnapshot
from .scan import (
    ScanArtifact,
    ScanBusyError,
    ScanJob,
    ScanJobManager,
    ScanOptions,
)

Collector = Callable[[], PrinterSnapshot]

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_SCAN_JOB_PATH_RE = re.compile(r"^/api/scans/([0-9a-f]{32})$")
_SCAN_FILE_PATH_RE = re.compile(
    r"^/api/scans/([0-9a-f]{32})/files/([0-9]+)$"
)


def normalize_host(value: object) -> str:
    """Return a safe printer host key or raise ``ValueError``.

    Only IPv4 addresses and DNS hostnames are accepted.  The dashboard never
    accepts a port, URL, path, or USB device path through the HTTP API.
    """

    if not isinstance(value, str):
        raise ValueError("host must be a string")
    host = value.strip()
    if not host:
        raise ValueError("host is empty")
    if len(host) > 253 or not _HOSTNAME_RE.fullmatch(host):
        raise ValueError(f"invalid host: {value!r}")
    labels = host.split(".")
    if len(labels) == 4 and all(label.isdigit() for label in labels):
        if any(int(label) > 255 for label in labels):
            raise ValueError(f"invalid IPv4 address: {value!r}")
        return ".".join(str(int(label)) for label in labels)
    return host.lower()


@dataclass
class Reading:
    snapshot: PrinterSnapshot | None
    collected_at: float
    elapsed_ms: int
    error: str | None = None
    cached: bool = False
    monotonic_at: float = 0.0


class SnapshotCache:
    """Serialize device reads and briefly cache the last result."""

    def __init__(
        self,
        collector: Collector,
        *,
        min_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ):
        self._collector = collector
        self._min_interval = max(0.0, min_interval)
        self._clock = clock
        self._wall_clock = wall_clock
        self._lock = threading.Lock()
        self._last: Reading | None = None

    def read(self) -> Reading:
        with self._lock:
            now = self._clock()
            if (
                self._last is not None
                and now - self._last.monotonic_at < self._min_interval
            ):
                return Reading(
                    snapshot=self._last.snapshot,
                    collected_at=self._last.collected_at,
                    elapsed_ms=self._last.elapsed_ms,
                    error=self._last.error,
                    cached=True,
                    monotonic_at=self._last.monotonic_at,
                )
            started = self._clock()
            try:
                snapshot = self._collector()
                finished = self._clock()
                reading = Reading(
                    snapshot=snapshot,
                    collected_at=self._wall_clock(),
                    elapsed_ms=round((finished - started) * 1000),
                    monotonic_at=finished,
                )
            except Exception as exc:  # keep the dashboard alive on device errors
                finished = self._clock()
                reading = Reading(
                    snapshot=None,
                    collected_at=self._wall_clock(),
                    elapsed_ms=round((finished - started) * 1000),
                    error=f"{type(exc).__name__}: {exc}",
                    monotonic_at=finished,
                )
            self._last = reading
            return reading


class DeviceRegistry:
    """Per-device caches restricted to the default and discovered hosts."""

    def __init__(
        self,
        factory: Callable[[str], Collector],
        default: str | None,
        *,
        min_interval: float = 1.0,
    ):
        self._factory = factory
        self._default = default
        self._min_interval = min_interval
        self._caches: dict[str, SnapshotCache] = {}
        self._allowed = {default} if default else set()
        self._lock = threading.Lock()

    @property
    def default(self) -> str | None:
        return self._default

    def allow(self, host: str) -> None:
        if host:
            with self._lock:
                self._allowed.add(host)

    def add_host(self, host: object) -> str:
        key = normalize_host(host)
        self.allow(key)
        return key

    def hosts(self) -> list[str]:
        with self._lock:
            return sorted(self._allowed, key=_address_key)

    def resolve(self, host: str | None = None) -> str:
        """Resolve an optional host to one allowed device key."""

        with self._lock:
            key = host or self._default
            if key is None and len(self._allowed) == 1:
                key = next(iter(self._allowed))
            if key is None or key not in self._allowed:
                raise KeyError(host)
            return key

    def read(self, host: str | None = None) -> Reading:
        key = self.resolve(host)
        with self._lock:
            cache = self._caches.get(key)
            if cache is None:
                cache = SnapshotCache(
                    lambda host=key: self._factory(host),
                    min_interval=self._min_interval,
                )
                self._caches[key] = cache
        return cache.read()

    def read_many(
        self, hosts: list[str] | None = None, *, max_workers: int = 4
    ) -> dict[str, Reading]:
        keys = self.hosts() if hosts is None else list(hosts)
        if not keys:
            return {}
        results: dict[str, Reading] = {}
        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(keys))
        ) as pool:
            futures = {pool.submit(self.read, key): key for key in keys}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as exc:
                    results[key] = Reading(
                        snapshot=None,
                        collected_at=time.time(),
                        elapsed_ms=0,
                        error=f"{type(exc).__name__}: {exc}",
                    )
        return {key: results[key] for key in keys if key in results}


def _address_key(value: str) -> tuple:
    parts = value.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return (0, tuple(int(part) for part in parts))
    return (1, value)


def reading_payload(reading: Reading, device: str | None = None) -> dict:
    return {
        "device": device,
        "collected_at": datetime.fromtimestamp(
            reading.collected_at, tz=timezone.utc
        )
        .astimezone()
        .isoformat(timespec="seconds"),
        "elapsed_ms": reading.elapsed_ms,
        "cached": reading.cached,
        "error": reading.error,
        "snapshot": (
            reading.snapshot.to_dict() if reading.snapshot is not None else None
        ),
    }


def scan_job_payload(job: ScanJob) -> dict[str, object]:
    """Serialize a job and add stable same-origin download links."""
    payload = job.metadata()
    result = payload["result"]
    if isinstance(result, dict):
        outputs = result.get("outputs")
        if isinstance(outputs, list):
            for index, output in enumerate(outputs):
                if isinstance(output, dict):
                    output["download_url"] = (
                        f"/api/scans/{job.job_id}/files/{index}"
                    )
    return payload


OVERVIEW_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KYOCERA 打印机</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 24px;
         background: #f5f6f8; color: #1b1f24; }
  main { max-width: 980px; margin: 0 auto; }
  header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  h1 { font-size: 1.5rem; margin: 0; }
  .pill { padding: 2px 10px; border-radius: 999px; font-size: .85rem;
          background: #d8dee6; }
  .pill.ok { background: #cdeccd; color: #145014; }
  .pill.warn { background: #ffd9d9; color: #6b1111; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 12px; margin-top: 18px; }
  a.card { display: block; background: #fff; border: 1px solid #dfe3e8;
           border-radius: 10px; padding: 14px; color: inherit;
           text-decoration: none; }
  a.card:hover { border-color: #9fb0c0; }
  .row { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .name { font-size: 1.1rem; font-weight: 600; }
  .addr { color: #5c6670; font-size: .9rem; }
  .line { margin-top: 8px; font-size: .92rem; }
  .label { color: #5c6670; }
  .error { background: #ffd9d9; color: #6b1111; padding: 10px 12px;
           border-radius: 8px; margin-top: 14px; display: none; }
  .muted { color: #6b747d; font-size: .85rem; margin-top: 14px; }
  button { margin-left: auto; padding: 6px 12px; border-radius: 8px;
           border: 1px solid #b9c1c9; background: #fff; cursor: pointer; }
  form.add { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
  form.add input { flex: 1 1 220px; min-width: 180px; padding: 8px 10px;
                   border-radius: 8px; border: 1px solid #b9c1c9;
                   background: #fff; color: inherit; font: inherit; }
  form.add button { margin-left: 0; }
  @media (prefers-color-scheme: dark) {
    body { background: #14181c; color: #e7ebef; }
    a.card { background: #1c2228; border-color: #2b333b; }
    .addr, .label, .muted { color: #9aa4ae; }
    button, form.add input { background: #1c2228; color: inherit;
                             border-color: #3a444e; }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1>KYOCERA 打印机</h1>
    <span id="count" class="pill">加载中</span>
    <button id="discover" type="button">发现打印机</button>
  </header>
  <form id="add" class="add" autocomplete="off">
    <input id="host" name="host" inputmode="url"
           placeholder="手动添加打印机 IP，例如 192.168.0.220" required>
    <button type="submit">添加设备</button>
  </form>
  <div id="error" class="error"></div>
  <div id="devices" class="grid"></div>
  <div id="meta" class="muted"></div>
</main>
<script>
const byId = (id) => document.getElementById(id);
const statusClass = (normal) => normal === true ? "pill ok"
  : normal === false ? "pill warn" : "pill";

function line(label, value) {
  const div = document.createElement("div");
  div.className = "line";
  const span = document.createElement("span");
  span.className = "label";
  span.textContent = label + ": ";
  div.append(span);
  div.append(document.createTextNode(
    value == null || value === "" ? "-" : String(value)));
  return div;
}

function card(device) {
  const snapshot = device.snapshot;
  const link = document.createElement("a");
  link.className = "card";
  link.href = "/device?host=" + encodeURIComponent(device.device);
  const row = document.createElement("div");
  row.className = "row";
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = (snapshot && snapshot.model) || "未知打印机";
  const pill = document.createElement("span");
  pill.className = statusClass(snapshot ? snapshot.normal : null);
  pill.textContent = snapshot
    ? (snapshot.normal === true ? "正常"
      : snapshot.normal === false ? "警告" : "未知")
    : "不可用";
  const addr = document.createElement("span");
  addr.className = "addr";
  addr.textContent = device.device;
  row.append(name, pill, addr);
  link.append(row);

  if (device.error) {
    const error = document.createElement("div");
    error.className = "line";
    error.textContent = device.error;
    link.append(error);
  } else if (snapshot) {
    link.append(line("序列号", snapshot.serial));
    link.append(line("碳粉", snapshot.toner_level == null
      ? null : snapshot.toner_level + "%"));
    link.append(line("面板", snapshot.display));
    const alerts = (snapshot.snmp && snapshot.snmp.alerts) || [];
    if (alerts.length) {
      link.append(line("告警", alerts.length));
    }
  }
  const meta = document.createElement("div");
  meta.className = "line label";
  meta.textContent = device.cached
    ? "缓存 · " + device.collected_at
    : "读取耗时 " + device.elapsed_ms + " ms";
  link.append(meta);
  return link;
}

function render(data) {
  const box = byId("devices");
  box.replaceChildren();
  const devices = data.devices || [];
  byId("count").textContent = devices.length +
    " 台设备";
  byId("count").className = devices.length ? "pill ok" : "pill";
  if (!devices.length) {
    byId("meta").textContent = "还没有设备。点击“发现打印机”，或手动输入 IP。";
    return;
  }
  for (const device of devices) {
    box.append(card(device));
  }
  byId("meta").textContent = "更新于 " + new Date().toLocaleTimeString();
}

async function load() {
  try {
    const response = await fetch("/api/devices", { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    const error = byId("error");
    error.textContent = String(err);
    error.style.display = "block";
  }
}

async function discover() {
  const button = byId("discover");
  button.disabled = true;
  button.textContent = "正在搜索…";
  try {
    const response = await fetch("/api/discover", { cache: "no-store" });
    const data = await response.json();
    if (data.error) {
      const error = byId("error");
      error.textContent = data.error;
      error.style.display = "block";
    }
    await load();
  } catch (err) {
    const error = byId("error");
    error.textContent = String(err);
    error.style.display = "block";
  } finally {
    button.disabled = false;
    button.textContent = "发现打印机";
  }
}

async function addDevice(event) {
  event.preventDefault();
  const input = byId("host");
  const error = byId("error");
  const host = input.value.trim();
  if (!host) return;
  try {
    const response = await fetch("/api/devices", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({host})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.status);
    input.value = "";
    error.style.display = "none";
    await load();
  } catch (err) {
    error.textContent = String(err);
    error.style.display = "block";
  }
}

byId("discover").addEventListener("click", discover);
byId("add").addEventListener("submit", addDevice);
load();
setInterval(load, 15000);
</script>
</body>
</html>
"""


DEVICE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KYOCERA 打印机状态</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 24px;
         background: #f5f6f8; color: #1b1f24; }
  main { max-width: 860px; margin: 0 auto; }
  header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  h1 { font-size: 1.5rem; margin: 0; }
  .pill { padding: 2px 10px; border-radius: 999px; font-size: .85rem;
          background: #d8dee6; }
  .pill.ok { background: #cdeccd; color: #145014; }
  .pill.warn { background: #ffd9d9; color: #6b1111; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 12px; margin-top: 18px; }
  .card { background: #fff; border: 1px solid #dfe3e8; border-radius: 10px;
          padding: 14px; }
  .label { font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;
           color: #5c6670; }
  .value { font-size: 1.05rem; margin-top: 4px; word-break: break-word; }
  .bar { height: 10px; border-radius: 999px; background: #e4e8ec;
         overflow: hidden; margin-top: 8px; }
  .bar > span { display: block; height: 100%; background: #2f7d32; width: 0; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eceff2;
           font-size: .92rem; }
  .muted { color: #6b747d; font-size: .85rem; margin-top: 14px; }
  .error { background: #ffd9d9; color: #6b1111; padding: 10px 12px;
           border-radius: 8px; margin-top: 14px; display: none; }
  button { margin-left: auto; padding: 6px 12px; border-radius: 8px;
           border: 1px solid #b9c1c9; background: #fff; cursor: pointer; }
  button:disabled { cursor: wait; opacity: .65; }
  form.scan { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
              gap: 12px; margin-top: 12px; align-items: end; }
  form.scan label { display: grid; gap: 6px; color: #5c6670; font-size: .82rem; }
  form.scan select { padding: 8px 10px; border-radius: 8px;
                     border: 1px solid #b9c1c9; background: #fff;
                     color: inherit; font: inherit; }
  form.scan button { margin: 0; min-height: 38px; }
  .progress { margin-top: 12px; padding: 10px 12px; border-radius: 8px;
              background: #eef3f7; display: none; }
  .progress.active { display: block; }
  .downloads { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .downloads a { padding: 7px 10px; border-radius: 8px; background: #dfeefa;
                 color: #174b74; text-decoration: none; }
  @media (prefers-color-scheme: dark) {
    body { background: #14181c; color: #e7ebef; }
    .card { background: #1c2228; border-color: #2b333b; }
    .bar { background: #2b333b; }
    th, td { border-color: #2b333b; }
    button, form.scan select { background: #1c2228; color: inherit;
                               border-color: #3a444e; }
    form.scan label { color: #9aa4ae; }
    .progress { background: #202a32; }
    .downloads a { background: #203b50; color: #cce7ff; }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1 id="model">KYOCERA 打印机</h1>
    <span id="status" class="pill">加载中</span>
    <a href="/">返回总览</a>
    <button id="refresh" type="button">刷新</button>
  </header>
  <div id="error" class="error"></div>
  <div class="grid">
    <div class="card"><div class="label">序列号</div><div id="serial" class="value">-</div></div>
    <div class="card"><div class="label">固件</div><div id="firmware" class="value">-</div></div>
    <div class="card"><div class="label">地址</div><div id="address" class="value">-</div></div>
    <div class="card"><div class="label">面板显示</div><div id="display" class="value">-</div></div>
    <div class="card">
      <div class="label">碳粉</div>
      <div id="toner" class="value">-</div>
      <div class="bar"><span id="toner-bar"></span></div>
    </div>
    <div class="card"><div class="label">累计打印页数</div><div id="lifetime" class="value">-</div></div>
    <div class="card"><div class="label">扫描计数</div><div id="scan" class="value">-</div></div>
    <div class="card"><div class="label">感光鼓计数</div><div id="drum" class="value">-</div></div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label">纸盒</div>
    <table><thead><tr><th>名称</th><th>状态</th><th>纸张</th><th>余量</th></tr></thead>
    <tbody id="trays"></tbody></table>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label">告警</div>
    <div id="alerts" class="value">-</div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label">扫描</div>
    <form id="scan-form" class="scan" autocomplete="off">
      <label>颜色
        <select id="scan-color">
          <option value="">设备默认</option>
          <option value="FULL_COLOR">彩色</option>
          <option value="GRAYSCALE">灰度</option>
          <option value="BLACK_AND_WHITE">黑白</option>
          <option value="AUTO_BLACK_AND_WHITE">自动黑白</option>
          <option value="AUTO_GRAYSCALE">自动灰度</option>
        </select>
      </label>
      <label>分辨率
        <select id="scan-resolution">
          <option value="">设备默认</option>
          <option value="RESOLUTION_150X150">150 × 150 dpi</option>
          <option value="RESOLUTION_200X200">200 × 200 dpi</option>
          <option value="RESOLUTION_300X300">300 × 300 dpi</option>
          <option value="RESOLUTION_400X400">400 × 400 dpi</option>
          <option value="RESOLUTION_600X600">600 × 600 dpi</option>
        </select>
      </label>
      <label>原稿类型
        <select id="scan-original-image">
          <option value="">设备默认</option>
          <option value="TEXT">文字</option>
          <option value="TEXT_AND_PHOTO">文字和照片</option>
          <option value="PHOTO">照片</option>
          <option value="FOR_OCR">OCR</option>
          <option value="MAP">地图</option>
          <option value="LIGHT_TEXT">浅色文字</option>
        </select>
      </label>
      <label>页数
        <select id="scan-pages">
          <option value="1">1 页</option>
          <option value="2">最多 2 页</option>
          <option value="3">最多 3 页</option>
          <option value="5">最多 5 页</option>
        </select>
      </label>
      <label>输出格式
        <select id="scan-format">
          <option value="png">PNG</option>
          <option value="pdf">PDF</option>
          <option value="jpeg">JPEG</option>
          <option value="tiff">TIFF</option>
          <option value="high_compression_pdf">高压缩 PDF</option>
          <option value="xps">XPS</option>
          <option value="bmp">BMP</option>
          <option value="raw">RAW（高级）</option>
        </select>
      </label>
      <button id="scan-start" type="submit">开始扫描</button>
    </form>
    <div id="scan-progress" class="progress"></div>
    <div id="scan-downloads" class="downloads"></div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label">设备设置</div>
    <div id="settings" class="value">-</div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label">设备发现</div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px">
      <button id="discover" type="button">发现打印机</button>
      <span id="current-host" class="muted"></span>
    </div>
    <div id="devices" class="value">尚未搜索</div>
  </div>
  <div id="meta" class="muted"></div>
</main>
<script>
const byId = (id) => document.getElementById(id);
const text = (id, value) => { byId(id).textContent = value == null || value === "" ? "-" : String(value); };
const currentHost = new URLSearchParams(location.search).get("host");

function trayRows(trays) {
  const body = byId("trays");
  body.replaceChildren();
  if (!trays || trays.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4; cell.textContent = "无纸盒数据";
    row.append(cell); body.append(row); return;
  }
  for (const tray of trays) {
    const row = document.createElement("tr");
    for (const value of [tray.name, tray.status, tray.paper || tray.media, tray.remain]) {
      const cell = document.createElement("td");
      cell.textContent = value == null || value === "" ? "-" : String(value);
      row.append(cell);
    }
    body.append(row);
  }
}

function render(payload) {
  const error = byId("error");
  if (payload.error) {
    error.textContent = payload.error;
    error.style.display = "block";
  } else {
    error.style.display = "none";
  }
  const snapshot = payload.snapshot;
  if (!snapshot) {
    byId("status").textContent = "不可用";
    byId("status").className = "pill warn";
    byId("meta").textContent = "最近尝试: " + payload.collected_at;
    return;
  }
  text("model", snapshot.model);
  text("serial", snapshot.serial);
  text("firmware", snapshot.firmware);
  text("display", snapshot.display);
  const known = snapshot.kgetobj_known || {};
  const knownValue = (name) => (known[name] ? known[name].value : null);
  const snmpScan = snapshot.snmp && snapshot.snmp.scan_count;
  text("scan", snmpScan != null ? snmpScan : knownValue("scan_count"));
  text("lifetime", knownValue("lifetime_counter"));
  const drum = knownValue("drum_counter");
  const drumMax = knownValue("drum_counter_max");
  text("drum", drum != null
    ? (drumMax != null ? `${drum} / ${drumMax}` : drum)
    : null);
  const settings = [];
  const sleepMode = (snapshot.snmp && snapshot.snmp.sleep_mode) ||
    knownValue("sleep_mode");
  if (sleepMode) settings.push(`Sleep mode: ${sleepMode}`);
  const autoClear = (snapshot.snmp && snapshot.snmp.auto_error_clear) ||
    knownValue("auto_error_clear");
  if (autoClear) {
    const timeout = (snapshot.snmp &&
      snapshot.snmp.auto_error_clear_timeout_seconds) ||
      knownValue("auto_error_clear_timeout");
    settings.push(`Auto error clear: ${autoClear}` +
      (timeout != null ? ` (${timeout} s)` : ""));
  }
  const formFeed = (snapshot.snmp &&
    snapshot.snmp.form_feed_timeout_seconds) || snapshot.timeout ||
    knownValue("form_feed_timeout");
  if (formFeed != null) settings.push(`Form feed timeout: ${formFeed} s`);
  byId("settings").textContent = settings.length ? settings.join(" · ") : "-";
  const net = snapshot.network || {};
  text("address", net.ip);

  const status = byId("status");
  if (snapshot.normal === true) {
    status.textContent = snapshot.status_code != null
      ? String(snapshot.status_code) + " 正常" : "正常";
    status.className = "pill ok";
  } else if (snapshot.normal === false) {
    status.textContent = snapshot.status_code != null
      ? String(snapshot.status_code) + " 警告" : "警告";
    status.className = "pill warn";
  } else {
    status.textContent = "未知";
    status.className = "pill";
  }

  if (snapshot.toner_level != null) {
    text("toner", snapshot.toner_level + "%");
    byId("toner-bar").style.width = Math.max(0, Math.min(100, snapshot.toner_level)) + "%";
  } else {
    text("toner", "未知");
    byId("toner-bar").style.width = "0%";
  }

  const trays = (snapshot.tray_status && snapshot.tray_status.length)
    ? snapshot.tray_status : snapshot.input_trays;
  trayRows(trays);

  const alerts = (snapshot.snmp && snapshot.snmp.alerts) || [];
  byId("alerts").textContent = alerts.length
    ? alerts.map((a) => {
        const severity = a.severity_name || a.severity;
        const group = a.group_name ? `, group ${a.group_name}` : "";
        const code = a.code_name ? `${a.code} (${a.code_name})` : a.code;
        return `severity ${severity}${group}, code ${code}`;
      }).join("; ")
    : "无告警";
  byId("meta").textContent =
    `设备 ${payload.device || "-"} · 读取于 ${payload.collected_at}，耗时 ${payload.elapsed_ms} ms` +
    (payload.cached ? "（缓存）" : "");
}

function statusUrl() {
  return "/api/status" + (currentHost ? "?host=" + encodeURIComponent(currentHost) : "");
}

async function load() {
  try {
    const response = await fetch(statusUrl(), { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    const error = byId("error");
    error.textContent = String(err);
    error.style.display = "block";
  }
}

const scanStageLabels = {
  queued: "排队",
  preflight: "预检",
  default_configuration: "读取配置",
  open_session: "打开会话",
  start_scan: "启动扫描",
  retrieve_image: "取图",
  decode_raw: "解码",
  export: "生成文件",
  close_session: "关闭会话",
  complete: "完成",
  unexpected: "内部错误"
};

function showScanStatus(message, active) {
  const box = byId("scan-progress");
  box.textContent = message;
  box.style.display = "block";
  box.style.background = active ? "" : (
    message.includes("失败") ? "#ffd9d9" : "#e8f4e8");
}

function showScanError(message) {
  showScanStatus("扫描失败：" + message, false);
  byId("scan-start").disabled = false;
  byId("scan-start").textContent = "重新扫描";
}

function renderScanResult(job) {
  const progress = byId("scan-progress");
  const downloads = byId("scan-downloads");
  downloads.replaceChildren();
  const result = job.result || {};
  const outputs = result.outputs || [];
  for (const output of outputs) {
    const link = document.createElement("a");
    link.href = output.download_url;
    link.download = output.filename;
    const size = output.bytes >= 1048576
      ? (output.bytes / 1048576).toFixed(1) + " MB"
      : Math.max(1, Math.round(output.bytes / 1024)) + " KB";
    link.textContent = `${output.filename} · ${size}`;
    downloads.append(link);
  }
  let message = `扫描完成：${result.pages || outputs.length || 0} 页` +
    ` · 设备请求 ${result.requested_device_format || "?"}` +
    ` / 设备返回 ${result.effective_device_format || "?"}` +
    ` / 本地 ${(job.output_format || "?").toUpperCase()}`;
  if (result.close_error) message += `；关闭会话警告：${result.close_error}`;
  progress.textContent = message;
  progress.style.display = "block";
  progress.style.background = result.close_error ? "#fff0c2" : "#e8f4e8";
  byId("scan-start").disabled = false;
  byId("scan-start").textContent = "再次扫描";
}

async function pollScan(jobId) {
  try {
    const response = await fetch(
      "/api/scans/" + encodeURIComponent(jobId), {cache: "no-store"});
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || String(response.status));
    if (job.state === "succeeded") {
      renderScanResult(job);
      return;
    }
    if (job.state === "failed") {
      const stage = scanStageLabels[job.stage] || job.stage || "未知阶段";
      const detail = (job.error && job.error.error) || job.message || "未知错误";
      showScanError(stage + " · " + detail);
      return;
    }
    const stage = scanStageLabels[job.stage] || job.stage || "处理中";
    showScanStatus(stage + " · " + (job.message || "请稍候"), true);
    setTimeout(() => pollScan(jobId), 800);
  } catch (err) {
    showScanError(String(err));
  }
}

async function startScan(event) {
  event.preventDefault();
  const button = byId("scan-start");
  button.disabled = true;
  button.textContent = "正在扫描…";
  byId("scan-downloads").replaceChildren();
  showScanStatus("正在创建扫描任务", true);
  const payload = {
    host: currentHost,
    color: byId("scan-color").value || null,
    resolution: byId("scan-resolution").value || null,
    original_image: byId("scan-original-image").value || null,
    max_pages: Number(byId("scan-pages").value),
    output_format: byId("scan-format").value
  };
  try {
    const response = await fetch("/api/scans", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || String(response.status));
    pollScan(job.job_id);
  } catch (err) {
    showScanError(String(err));
  }
}

async function discover() {
  const box = byId("devices");
  box.textContent = "正在搜索…";
  try {
    const response = await fetch("/api/discover", { cache: "no-store" });
    const data = await response.json();
    box.replaceChildren();
    if (data.error) { box.textContent = data.error; return; }
    if (!data.printers || data.printers.length === 0) {
      box.textContent = "没有发现打印机";
      return;
    }
    for (const printer of data.printers) {
      const row = document.createElement("div");
      const link = document.createElement("a");
      const label = [printer.address, printer.model, printer.serial]
        .filter(Boolean).join(" · ");
      link.href = "?host=" + encodeURIComponent(printer.address);
      link.textContent = label;
      row.append(link);
      box.append(row);
    }
  } catch (err) {
    box.textContent = String(err);
  }
}

byId("refresh").addEventListener("click", load);
byId("discover").addEventListener("click", discover);
byId("scan-form").addEventListener("submit", startScan);
text("current-host", currentHost ? "当前: " + currentHost : "当前: 默认设备");
load();
setInterval(load, 10000);
</script>
</body>
</html>
"""


def make_handler(
    registry: DeviceRegistry,
    discover_fn: Callable[[], list] | None = None,
    scan_manager: ScanJobManager | None = None,
) -> type[BaseHTTPRequestHandler]:
    manager = scan_manager or ScanJobManager()

    class Handler(BaseHTTPRequestHandler):
        server_version = "kyocera-monitor"

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            parsed = urlsplit(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                body = OVERVIEW_HTML.encode("utf-8")
                self._respond(200, "text/html; charset=utf-8", body)
            elif path == "/device":
                body = DEVICE_HTML.encode("utf-8")
                self._respond(200, "text/html; charset=utf-8", body)
            elif path == "/api/status":
                requested = (parse_qs(parsed.query).get("host") or [None])[0]
                try:
                    host = registry.resolve(requested)
                    reading = registry.read(host)
                except KeyError:
                    message = (
                        "no printer selected"
                        if requested is None
                        else f"unknown device: {requested}"
                    )
                    body = json.dumps(
                        {"error": message}
                    ).encode("utf-8")
                    status = 400 if requested is None else 404
                    self._respond(status, "application/json; charset=utf-8", body)
                    return
                body = json.dumps(
                    reading_payload(reading, host),
                    ensure_ascii=False,
                ).encode("utf-8")
                status = 502 if reading.error else 200
                self._respond(status, "application/json; charset=utf-8", body)
            elif path == "/api/devices":
                readings = registry.read_many()
                devices = [
                    reading_payload(reading, key)
                    for key, reading in readings.items()
                ]
                body = json.dumps(
                    {"devices": devices}, ensure_ascii=False
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif match := _SCAN_JOB_PATH_RE.fullmatch(path):
                try:
                    job = manager.get(match.group(1))
                except KeyError:
                    self._json_error(404, "scan job not found")
                    return
                body = json.dumps(
                    scan_job_payload(job), ensure_ascii=False
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif match := _SCAN_FILE_PATH_RE.fullmatch(path):
                try:
                    artifact = manager.output(
                        match.group(1), int(match.group(2))
                    )
                except (KeyError, IndexError):
                    self._json_error(404, "scan output not found")
                    return
                self._respond_artifact(artifact)
            elif path == "/api/discover":
                if discover_fn is None:
                    body = json.dumps(
                        {"printers": [], "error": "discovery is unavailable"}
                    ).encode("utf-8")
                    self._respond(400, "application/json; charset=utf-8", body)
                    return
                try:
                    printers = discover_fn()
                except Exception as exc:
                    body = json.dumps(
                        {
                            "printers": [],
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    ).encode("utf-8")
                    self._respond(502, "application/json; charset=utf-8", body)
                    return
                for printer in printers:
                    registry.allow(printer.address)
                body = json.dumps(
                    {
                        "printers": [printer.to_dict() for printer in printers],
                        "error": None,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif path == "/healthz":
                self._respond(200, "text/plain; charset=utf-8", b"ok\n")
            else:
                self._respond(404, "text/plain; charset=utf-8", b"not found\n")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if parsed.path not in {"/api/devices", "/api/scans"}:
                self._respond(404, "text/plain; charset=utf-8", b"not found\n")
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = 0
            if length <= 0 or length > 4096:
                self._json_error(400, "request body must be 1-4096 bytes")
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json_error(400, "request body must be JSON")
                return
            if not isinstance(payload, dict):
                self._json_error(400, "request body must be a JSON object")
                return
            if parsed.path == "/api/scans":
                self._start_scan(payload)
                return
            try:
                host = registry.add_host(payload.get("host"))
            except ValueError as exc:
                self._json_error(400, str(exc))
                return
            body = json.dumps(
                {"device": host, "devices": registry.hosts()},
                ensure_ascii=False,
            ).encode("utf-8")
            self._respond(200, "application/json; charset=utf-8", body)

        def _start_scan(self, payload: dict[str, object]) -> None:
            requested = payload.get("host")
            if requested is not None and not isinstance(requested, str):
                self._json_error(400, "host must be a string or null")
                return
            try:
                host = registry.resolve(requested)
            except KeyError:
                message = (
                    "no printer selected"
                    if requested is None
                    else f"unknown device: {requested}"
                )
                self._json_error(404 if requested is not None else 400, message)
                return
            try:
                options = ScanOptions.from_payload(payload)
                job = manager.start(host, options)
            except ScanBusyError as exc:
                self._json_error(409, str(exc))
                return
            except ValueError as exc:
                self._json_error(400, str(exc))
                return
            body = json.dumps(
                scan_job_payload(job), ensure_ascii=False
            ).encode("utf-8")
            self._respond(202, "application/json; charset=utf-8", body)

        def _json_error(self, status: int, message: str) -> None:
            body = json.dumps({"error": message}, ensure_ascii=False).encode(
                "utf-8"
            )
            self._respond(status, "application/json; charset=utf-8", body)

        def do_HEAD(self) -> None:  # noqa: N802
            if urlsplit(self.path).path in ("/", "/index.html", "/device"):
                self._respond(200, "text/html; charset=utf-8", b"", head=True)
            else:
                self._respond(404, "text/plain; charset=utf-8", b"", head=True)

        def _respond(
            self,
            status: int,
            content_type: str,
            body: bytes,
            *,
            head: bool = False,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if not head:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    # Browsers close speculative connections routinely.
                    pass

        def _respond_artifact(self, artifact: ScanArtifact) -> None:
            self._respond(
                200,
                artifact.media_type,
                artifact.data,
                headers={
                    "Content-Disposition": (
                        "attachment; filename*=UTF-8''"
                        f"{quote(artifact.filename)}"
                    ),
                    "X-Content-Type-Options": "nosniff",
                },
            )

        def log_message(self, fmt: str, *args) -> None:
            # Keep the console quiet; device errors are visible in the JSON.
            return

    return Handler


def run_server(
    registry: DeviceRegistry,
    *,
    bind: str = "127.0.0.1",
    port: int = 8080,
    discover_fn: Callable[[], list] | None = None,
    on_listen: Callable[[str], None] | None = None,
    scan_manager: ScanJobManager | None = None,
) -> None:
    server = create_server(
        registry,
        bind=bind,
        port=port,
        discover_fn=discover_fn,
        scan_manager=scan_manager,
    )
    if on_listen is not None:
        actual_port = server.server_address[1]
        url_host = "127.0.0.1" if bind in ("0.0.0.0", "::") else bind
        on_listen(f"http://{url_host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def create_server(
    registry: DeviceRegistry,
    *,
    bind: str = "127.0.0.1",
    port: int = 8080,
    discover_fn: Callable[[], list] | None = None,
    scan_manager: ScanJobManager | None = None,
) -> ThreadingHTTPServer:
    """Create (but do not start) the dashboard HTTP server.

    ``port=0`` selects an ephemeral port, which the native GTK wrapper uses to
    avoid clashing with a dashboard the user already runs on 8080.
    """

    return ThreadingHTTPServer(
        (bind, port),
        make_handler(
            registry,
            discover_fn,
            scan_manager=scan_manager,
        ),
    )
