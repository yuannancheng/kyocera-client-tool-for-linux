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
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, urlsplit

from .config_snapshot import ConfigSnapshotError
from .config_web import ConfigWorkbench, ConfigWorkbenchError
from .config_write_executor import ConfigWriteExecutionError
from .config_write_plan import ConfigWritePlanError
from .parser import PrinterSnapshot
from .preferences import (
    SettingsError,
    SettingsStore,
    merge_scan_payload,
    normalize_host,
    preset_payload,
)
from .reporting import counters_csv
from .scan import (
    ScanArtifact,
    ScanBusyError,
    ScanJob,
    ScanJobManager,
    ScanOptions,
)

Collector = Callable[[], PrinterSnapshot]

_SCAN_JOB_PATH_RE = re.compile(r"^/api/scans/([0-9a-f]{32})$")
_SCAN_FILE_PATH_RE = re.compile(
    r"^/api/scans/([0-9a-f]{32})/files/([0-9]+)$"
)


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


def content_disposition(filename: str) -> str:
    """Return a portable attachment header for ASCII and Unicode names."""
    fallback = (
        filename.encode("ascii", "replace")
        .decode("ascii")
        .replace("\\", "_")
        .replace('"', "'")
    ) or "kyocera-download"
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


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
          background: #d8dee6; color: #1b1f24; }
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
  a.button { padding: 6px 12px; border-radius: 8px; border: 1px solid #b9c1c9;
             background: #fff; color: inherit; text-decoration: none; }
  label.notify { display: inline-flex; align-items: center; gap: 6px;
                 font-size: .9rem; }
  form.add { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
  form.add input { flex: 1 1 220px; min-width: 180px; padding: 8px 10px;
                   border-radius: 8px; border: 1px solid #b9c1c9;
                   background: #fff; color: inherit; font: inherit; }
  form.add button { margin-left: 0; }
  @media (prefers-color-scheme: dark) {
    body { background: #14181c; color: #e7ebef; }
    a.card { background: #1c2228; border-color: #2b333b; }
    .addr, .label, .muted { color: #9aa4ae; }
    .pill { background: #303842; color: #e7ebef; }
    .pill.ok { background: #1d3f22; color: #d3f2d8; }
    .pill.warn { background: #4a2326; color: #f6c8c8; }
    button, a.button, form.add input { background: #1c2228; color: inherit;
                                        border-color: #3a444e; }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1>KYOCERA 打印机</h1>
    <span id="count" class="pill">加载中</span>
    <a class="button" href="/api/counters.csv">导出计数 CSV</a>
    <label class="notify"><input id="notify" type="checkbox"> 状态通知</label>
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
let previousStates = {};

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
  notifyChanges(devices);
  byId("meta").textContent = "更新于 " + new Date().toLocaleTimeString();
}

function deviceState(device) {
  if (device.error || !device.snapshot) return "unavailable";
  if (device.snapshot.normal === true) return "normal";
  if (device.snapshot.normal === false) return "warning";
  return "unknown";
}

function notifyChanges(devices) {
  const next = {};
  for (const device of devices) next[device.device] = deviceState(device);
  if (byId("notify").checked && "Notification" in window &&
      Notification.permission === "granted") {
    for (const [device, state] of Object.entries(next)) {
      const before = previousStates[device];
      if (before && before !== state &&
          (state === "warning" || state === "unavailable")) {
        const name = (devices.find((item) => item.device === device)?.snapshot?.model)
          || device;
        new Notification("京瓷打印机状态变化", {
          body: `${name} (${device}) 状态变为 ${state}`
        });
      }
    }
  }
  previousStates = next;
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
  const error = byId("error");
  button.disabled = true;
  button.textContent = "正在搜索…";
  error.style.display = "none";
  try {
    const response = await fetch("/api/discover", { cache: "no-store" });
    const data = await response.json();
    if (data.error) {
      error.textContent = data.error;
      error.style.display = "block";
      return;
    }
    await load();
    byId("meta").textContent = data.warning
      ? data.warning
      : `发现 ${data.printers?.length || 0} 台打印机，结果已保存`;
  } catch (err) {
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
    byId("meta").textContent = `已添加并保存打印机 ${host}`;
  } catch (err) {
    error.textContent = String(err);
    error.style.display = "block";
  }
}

byId("discover").addEventListener("click", discover);
byId("add").addEventListener("submit", addDevice);
byId("notify").checked = localStorage.getItem("kyocera-notify") === "1";
byId("notify").addEventListener("change", async () => {
  const enabled = byId("notify").checked;
  localStorage.setItem("kyocera-notify", enabled ? "1" : "0");
  if (enabled && "Notification" in window &&
      Notification.permission === "default") {
    await Notification.requestPermission();
  }
});
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
          background: #d8dee6; color: #1b1f24; }
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
  form.scan label, .settings label { display: grid; gap: 6px; color: #5c6670;
                                      font-size: .82rem; }
  form.scan select, .settings input { padding: 8px 10px; border-radius: 8px;
                                      border: 1px solid #b9c1c9; background: #fff;
                                      color: inherit; font: inherit; }
  form.scan button { margin: 0; min-height: 38px; }
  .settings { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
              gap: 12px; margin-top: 12px; align-items: end; }
  .settings .wide { grid-column: span 2; }
  .inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .inline label { display: inline-flex; align-items: center; gap: 6px; color: inherit; }
  .inline button { margin: 0; }
  .config-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                 gap: 10px; margin-top: 12px; }
  .config-item { padding: 10px; border-radius: 8px; background: #f4f6f8;
                 border: 1px solid #e1e5e9; }
  .config-item .name { font-size: .9rem; font-weight: 600; }
  .config-item .reading { margin-top: 5px; }
  .warning-box { margin-top: 12px; padding: 10px 12px; border-radius: 8px;
                 background: #fff3cf; color: #624600; border: 1px solid #e6cc82; }
  .plan-box { margin-top: 12px; padding: 10px 12px; border-radius: 8px;
              border: 1px solid #b9c1c9; white-space: pre-wrap;
              font-family: monospace; font-size: .86rem; display: none; }
  .config-table-wrap { max-height: 360px; overflow: auto; margin-top: 10px; }
  .config-table-wrap table { margin-top: 0; }
  .config-table-wrap tr.unreadable td { color: #8b3d3d; }
  .config-write { margin-top: 14px; padding-top: 14px; border-top: 1px solid #dfe3e8; }
  .progress { margin-top: 12px; padding: 10px 12px; border-radius: 8px;
              background: #eef3f7; color: #1b1f24; border: 1px solid #d7e0e7;
              display: none; }
  .progress.active { display: block; }
  .progress.success { display: block; background: #e5f4e7; color: #174c22;
                      border-color: #b8ddbf; }
  .progress.warning { display: block; background: #fff3cf; color: #624600;
                      border-color: #e6cc82; }
  .progress.failure { display: block; background: #ffe1e1; color: #751a1a;
                      border-color: #e7b1b1; }
  .downloads { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .downloads a { padding: 7px 10px; border-radius: 8px; background: #dfeefa;
                 color: #174b74; text-decoration: none; cursor: pointer; }
  @media (prefers-color-scheme: dark) {
    body { background: #14181c; color: #e7ebef; }
    .card { background: #1c2228; border-color: #2b333b; }
    .pill { background: #303842; color: #e7ebef; }
    .pill.ok { background: #1d3f22; color: #d3f2d8; }
    .pill.warn { background: #4a2326; color: #f6c8c8; }
    .bar { background: #2b333b; }
    th, td { border-color: #2b333b; }
    button, form.scan select, .settings input { background: #1c2228; color: inherit;
                                                border-color: #3a444e; }
    form.scan label, .settings label { color: #9aa4ae; }
    .progress { background: #202a32; color: #e7ebef; border-color: #35414c; }
    .progress.success { background: #1d3523; color: #d3f2d8;
                        border-color: #356943; }
    .progress.warning { background: #3d331b; color: #f6dfaa;
                        border-color: #735d2b; }
    .progress.failure { background: #3c2022; color: #f6c8c8;
                        border-color: #74393d; }
    .downloads a { background: #203b50; color: #cce7ff; }
    .config-item { background: #182027; border-color: #2d3842; }
    .plan-box { border-color: #3a444e; background: #11171c; color: #e7ebef; }
    .config-write { border-color: #2b333b; }
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
    <div class="label">扫描预设与保存目录</div>
    <div class="settings">
      <label>预设
        <select id="preset-select">
          <option value="">不使用预设</option>
        </select>
      </label>
      <label>预设名称
        <input id="preset-name" maxlength="80" placeholder="例如：A4 彩扫">
      </label>
      <label class="wide">保存目录
        <input id="scan-directory" maxlength="4096" placeholder="/home/user/Pictures/Kyocera Scans">
      </label>
    </div>
    <div class="inline">
      <label><input id="save-folder" type="checkbox"> 扫描完成后自动保存到该目录</label>
      <button id="preset-save" type="button">保存当前设置为预设</button>
      <button id="preset-delete" type="button">删除所选预设</button>
      <button id="settings-save" type="button">保存目录设置</button>
      <span id="settings-status" class="muted"></span>
    </div>
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
          <option value="4">最多 4 页</option>
          <option value="5">最多 5 页</option>
          <option value="6">最多 6 页</option>
          <option value="7">最多 7 页</option>
          <option value="8">最多 8 页</option>
          <option value="9">最多 9 页</option>
          <option value="10">最多 10 页</option>
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
    <div class="label">配置、面板与 Wi-Fi</div>
    <div class="inline">
      <button id="config-read" type="button">读取 147 项配置</button>
      <button id="config-baseline-save" type="button">保存当前为基线</button>
      <button id="config-baseline-compare" type="button">与基线比较</button>
      <span id="config-status" class="muted"></span>
    </div>
    <div id="config-baseline-info" class="muted"></div>
    <div id="config-status-grid" class="config-grid"></div>
    <div id="config-changes"></div>
    <details style="margin-top:12px">
      <summary>查看已读取的配置对象</summary>
      <div class="config-table-wrap">
        <table>
          <thead><tr><th>ID</th><th>名称</th><th>状态</th><th>值</th><th>写权限</th></tr></thead>
          <tbody id="config-objects"></tbody>
        </table>
      </div>
    </details>
    <div class="config-write">
      <div class="label">安全回滚实验</div>
      <div class="warning-box">
        只允许 Auto error clear 或 Quiet mode 的 OFF → ON → OFF。
        生成计划会重新读取全部配置；执行前仍必须勾选明确授权。
      </div>
      <div class="settings">
        <label>字段
          <select id="config-write-item">
            <option value="">先读取配置</option>
          </select>
        </label>
        <label>目标值
          <input id="config-write-value" value="ON" readonly>
        </label>
      </div>
      <div class="inline">
        <button id="config-plan" type="button" disabled>生成写入与回滚计划</button>
        <button id="config-apply" type="button" disabled>执行 OFF → ON → OFF</button>
        <label><input id="config-authorize" type="checkbox" disabled>
          我已阅读计划并授权本次回滚实验</label>
      </div>
      <div id="config-plan-result" class="plan-box"></div>
      <div id="config-execution-result" class="plan-box"></div>
    </div>
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
let userSettings = null;
let configPlan = null;
let configOverview = null;

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
  save: "保存文件",
  close_session: "关闭会话",
  complete: "完成",
  unexpected: "内部错误"
};

function setScanStatus(message, state) {
  const box = byId("scan-progress");
  box.textContent = message;
  box.className = "progress active " + state;
}

function showScanError(message) {
  setScanStatus("扫描失败：" + message, "failure");
  byId("scan-start").disabled = false;
  byId("scan-start").textContent = "重新扫描";
}

function nativeDownload(output) {
  const bridge = window.webkit &&
    window.webkit.messageHandlers &&
    window.webkit.messageHandlers.kyoceraDownload;
  if (!bridge) return false;
  bridge.postMessage({
    url: output.download_url,
    filename: output.filename
  });
  return true;
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
    link.title = "下载 " + output.filename;
    link.addEventListener("click", (event) => {
      if (!nativeDownload(output)) return;
      event.preventDefault();
      setScanStatus("正在下载 " + output.filename, "active");
    });
    downloads.append(link);
  }
  let message = `扫描完成：${result.pages || outputs.length || 0} 页` +
    ` · 设备请求 ${result.requested_device_format || "?"}` +
    ` / 设备返回 ${result.effective_device_format || "?"}` +
    ` / 本地 ${(job.output_format || "?").toUpperCase()}`;
  const saved = job.saved_paths || [];
  if (saved.length) {
    const folder = byId("scan-directory").value || "所选目录";
    message += ` · 已保存 ${saved.length} 个文件到 ${folder}`;
  }
  if (result.close_error) message += `；关闭会话警告：${result.close_error}`;
  setScanStatus(message, result.close_error ? "warning" : "success");
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
    setScanStatus(stage + " · " + (job.message || "请稍候"), "active");
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
  setScanStatus("正在创建扫描任务", "active");
  const payload = {
    host: currentHost,
    preset_id: byId("preset-select").value || null,
    save_to_folder: byId("save-folder").checked,
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

function setSettingsStatus(message, error = false) {
  const status = byId("settings-status");
  status.textContent = message;
  status.style.color = error ? "#a12222" : "";
}

function renderPresets(selectedId = "") {
  const select = byId("preset-select");
  select.replaceChildren();
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "不使用预设";
  select.append(none);
  for (const preset of (userSettings?.presets || [])) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = preset.name;
    select.append(option);
  }
  select.value = selectedId;
}

function applyPreset() {
  const selected = byId("preset-select").value;
  const preset = (userSettings?.presets || []).find((item) => item.id === selected);
  if (!preset) return;
  byId("scan-color").value = preset.color || "";
  byId("scan-resolution").value = preset.resolution || "";
  byId("scan-original-image").value = preset.original_image || "";
  byId("scan-pages").value = String(preset.max_pages || 1);
  byId("scan-format").value = preset.output_format || "png";
  byId("preset-name").value = preset.name || "";
}

async function loadSettings() {
  try {
    const response = await fetch("/api/settings", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || String(response.status));
    userSettings = payload;
    byId("scan-directory").value = payload.scan_directory || "";
    renderPresets();
    setSettingsStatus("");
  } catch (err) {
    setSettingsStatus("设置加载失败：" + String(err), true);
  }
}

async function persistSettings(message) {
  try {
    const payload = {
      version: 1,
      scan_directory: byId("scan-directory").value.trim(),
      presets: userSettings?.presets || []
    };
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const saved = await response.json();
    if (!response.ok) throw new Error(saved.error || String(response.status));
    userSettings = saved;
    byId("scan-directory").value = saved.scan_directory || "";
    setSettingsStatus(message);
  } catch (err) {
    setSettingsStatus("保存失败：" + String(err), true);
  }
}

async function saveFolderSettings() {
  await persistSettings("保存目录已更新");
}

async function savePreset() {
  const name = byId("preset-name").value.trim();
  if (!name) {
    setSettingsStatus("请先输入预设名称", true);
    return;
  }
  if (!userSettings) await loadSettings();
  if (!userSettings) return;
  let presetId = byId("preset-select").value;
  if (!presetId) {
    presetId = "preset-" + Date.now().toString(36);
  }
  const preset = {
    id: presetId,
    name,
    color: byId("scan-color").value || null,
    resolution: byId("scan-resolution").value || null,
    original_image: byId("scan-original-image").value || null,
    max_pages: Number(byId("scan-pages").value),
    output_format: byId("scan-format").value
  };
  const presets = (userSettings.presets || []).filter((item) => item.id !== presetId);
  presets.push(preset);
  userSettings = {...userSettings, presets};
  await persistSettings("预设已保存");
  renderPresets(presetId);
}

async function deletePreset() {
  const presetId = byId("preset-select").value;
  if (!presetId || !userSettings) return;
  userSettings = {
    ...userSettings,
    presets: (userSettings.presets || []).filter((item) => item.id !== presetId)
  };
  await persistSettings("预设已删除");
  renderPresets();
  byId("preset-name").value = "";
}

function setConfigStatus(message, error = false) {
  const status = byId("config-status");
  status.textContent = message;
  status.style.color = error ? "#a12222" : "";
}

function configUrl(path) {
  return path + (currentHost ? "?host=" + encodeURIComponent(currentHost) : "");
}

async function configRequest(path, options = {}) {
  const response = await fetch(configUrl(path), {
    cache: "no-store",
    ...options
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || String(response.status));
  return payload;
}

function renderConfigObjects(objects) {
  const body = byId("config-objects");
  body.replaceChildren();
  for (const object of objects || []) {
    const row = document.createElement("tr");
    if (!object.readable) row.className = "unreadable";
    for (const value of [
      object.item_id,
      object.label,
      object.readable ? "可读" : "不可读",
      object.sensitive ? "已隐藏" : (object.display ?? "-"),
      object.write_policy === "reversible_experiment" ? "可回滚实验" : "只读"
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value == null || value === "" ? "-" : String(value);
      row.append(cell);
    }
    body.append(row);
  }
}

function renderConfigStatusObjects(objects) {
  const grid = byId("config-status-grid");
  grid.replaceChildren();
  for (const object of objects || []) {
    const item = document.createElement("div");
    item.className = "config-item";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = object.label;
    const reading = document.createElement("div");
    reading.className = "reading";
    reading.textContent = object.sensitive
      ? "已隐藏"
      : (object.readable ? (object.display ?? "-") : "不可用");
    item.append(name, reading);
    grid.append(item);
  }
}

function renderConfigCandidates(candidates, available) {
  const select = byId("config-write-item");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = candidates.length ? "选择字段" : "没有可用写入字段";
  select.append(placeholder);
  for (const candidate of candidates || []) {
    const option = document.createElement("option");
    option.value = String(candidate.item_id);
    option.textContent = `${candidate.item_id} · ${candidate.label}`;
    select.append(option);
  }
  byId("config-plan").disabled = !available || candidates.length === 0;
  byId("config-plan-result").style.display = "none";
  byId("config-execution-result").style.display = "none";
  byId("config-apply").disabled = true;
  byId("config-authorize").disabled = true;
  byId("config-authorize").checked = false;
  configPlan = null;
}

function renderConfigOverview(data) {
  configOverview = data;
  const baseline = data.baseline || {};
  byId("config-baseline-info").textContent = baseline.available
    ? `基线：${baseline.created_at} · 可读 ${baseline.read}/${baseline.total}`
    : (baseline.error ? "基线不可用：" + baseline.error : "尚未保存基线");
  renderConfigStatusObjects(data.status_objects);
  renderConfigObjects(data.objects);
  renderConfigCandidates(data.candidates, data.write_execution_available);
  byId("config-changes").replaceChildren();
  setConfigStatus(`读取完成：${data.read}/${data.total} 项可读`);
}

async function runConfigAction(button, message, action) {
  const original = button.textContent;
  button.disabled = true;
  setConfigStatus(message);
  try {
    await action();
  } catch (err) {
    setConfigStatus(String(err), true);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function readConfiguration() {
  await runConfigAction(
    byId("config-read"),
    "正在通过 SNMP 读取 147 项配置…",
    async () => {
      const data = await configRequest("/api/config");
      renderConfigOverview(data);
    }
  );
}

async function saveConfigurationBaseline() {
  if (!window.confirm("保存当前完整配置为新基线？敏感值会以 0600 权限保存在本机。")) {
    return;
  }
  await runConfigAction(
    byId("config-baseline-save"),
    "正在读取并保存私有基线…",
    async () => {
      await configRequest("/api/config/baseline", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({host: currentHost})
      });
      await readConfiguration();
      setConfigStatus("配置基线已保存");
    }
  );
}

function appendChange(box, title, changes) {
  if (!changes || !changes.length) return;
  const heading = document.createElement("div");
  heading.textContent = `${title}：${changes.length}`;
  heading.style.fontWeight = "600";
  box.append(heading);
  for (const change of changes) {
    const row = document.createElement("div");
    const before = change.sensitive ? "已隐藏" : (change.before?.display ?? "-");
    const after = change.sensitive ? "已隐藏" : (change.after?.display ?? "-");
    row.textContent = `${change.item_id} · ${change.label}：${before} → ${after}`;
    box.append(row);
  }
}

async function compareConfigurationBaseline() {
  await runConfigAction(
    byId("config-baseline-compare"),
    "正在读取当前配置并与基线比较…",
    async () => {
      const data = await configRequest("/api/config/compare");
      const comparison = data.comparison;
      const box = byId("config-changes");
      box.replaceChildren();
      appendChange(box, "配置变化", comparison.changes);
      appendChange(box, "易变遥测变化", comparison.volatile_changes);
      appendChange(box, "读取状态变化", comparison.read_status_changes);
      if (!box.children.length) {
        box.textContent = "没有配置或读取状态变化";
      }
      setConfigStatus(
        `比较完成：${comparison.changed} 个配置变化，` +
        `${comparison.read_status_changed} 个读取状态变化`
      );
    }
  );
}

function showPlan(planData) {
  const plan = planData.plan;
  configPlan = plan;
  const box = byId("config-plan-result");
  const blockers = plan.review.blockers || [];
  const lines = [
    `目标：${plan.object.item_id} ${plan.object.label}`,
    `当前：${plan.current.display ?? "-"}`,
    `实验：${plan.before.display} → ${plan.requested.display} → ${plan.rollback.display}`,
    `SNMP：${plan.commands.snmp_set.oid} Integer ${plan.commands.snmp_set.value}`,
    `回滚：${plan.commands.snmp_rollback.oid} Integer ${plan.commands.snmp_rollback.value}`,
    `确认令牌：sha256:${plan.confirmation.token}`
  ];
  if (blockers.length) lines.push("阻断：" + blockers.join(", "));
  if (!planData.write_execution_available) {
    lines.push("当前连接未开放写入执行器");
  }
  box.textContent = lines.join("\\n");
  box.style.display = "block";
  const executable = planData.write_execution_available &&
    plan.execution.allowed && blockers.length === 0;
  byId("config-authorize").disabled = !executable;
  byId("config-authorize").checked = false;
  byId("config-apply").disabled = true;
  setConfigStatus(executable ? "计划有效，等待明确授权" : "计划已生成但当前不可执行", !executable);
}

async function planConfigurationExperiment() {
  const itemId = Number(byId("config-write-item").value);
  if (!itemId) {
    setConfigStatus("请先选择字段", true);
    return;
  }
  await runConfigAction(
    byId("config-plan"),
    "正在重新读取完整配置并生成回滚计划…",
    async () => {
      const data = await configRequest("/api/config/plan", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          host: currentHost,
          item_id: itemId,
          value: "ON"
        })
      });
      showPlan(data);
    }
  );
}

async function applyConfigurationExperiment() {
  if (!configPlan || !byId("config-authorize").checked) return;
  const itemId = configPlan.object.item_id;
  const label = configPlan.object.label;
  if (!window.confirm(
    `确认执行 ${label} OFF → ON → OFF？工具会立即尝试恢复原值。`
  )) {
    return;
  }
  await runConfigAction(
    byId("config-apply"),
    "正在执行受控写入、回读和回滚…",
    async () => {
      const data = await configRequest("/api/config/apply", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          host: currentHost,
          item_id: itemId,
          value: "ON",
          confirmation_token: "sha256:" + configPlan.confirmation.token
        })
      });
      const execution = data.execution;
      const box = byId("config-execution-result");
      box.textContent = [
        `状态：${execution.status}`,
        `写入并回读：${execution.verify_on.ok ? "成功" : "失败"}`,
        `恢复并回读：${execution.verify_off.ok ? "成功" : "失败"}`,
        `回滚值：${execution.rollback_value}`
      ].join("\\n");
      box.style.display = "block";
      setConfigStatus(
        execution.status === "success" ? "回滚实验完成" : "回滚实验未完全成功",
        execution.status !== "success"
      );
      byId("config-apply").disabled = true;
      byId("config-authorize").checked = false;
    }
  );
  byId("config-apply").disabled = true;
  byId("config-authorize").checked = false;
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
      box.textContent = data.warning || "没有发现打印机";
      return;
    }
    if (data.warning) {
      const warning = document.createElement("div");
      warning.className = "warning-box";
      warning.textContent = data.warning;
      box.append(warning);
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
    const saved = document.createElement("div");
    saved.className = "muted";
    saved.textContent = "发现结果已保存，下次启动无需重新搜索";
    box.append(saved);
  } catch (err) {
    box.textContent = String(err);
  }
}

byId("refresh").addEventListener("click", load);
byId("discover").addEventListener("click", discover);
byId("scan-form").addEventListener("submit", startScan);
byId("preset-select").addEventListener("change", applyPreset);
byId("settings-save").addEventListener("click", saveFolderSettings);
byId("preset-save").addEventListener("click", savePreset);
byId("preset-delete").addEventListener("click", deletePreset);
byId("config-read").addEventListener("click", readConfiguration);
byId("config-baseline-save").addEventListener("click", saveConfigurationBaseline);
byId("config-baseline-compare").addEventListener("click", compareConfigurationBaseline);
byId("config-plan").addEventListener("click", planConfigurationExperiment);
byId("config-apply").addEventListener("click", applyConfigurationExperiment);
byId("config-authorize").addEventListener("change", () => {
  byId("config-apply").disabled = !(
    byId("config-authorize").checked &&
    configPlan &&
    configPlan.execution.allowed
  );
});
byId("config-write-item").addEventListener("change", () => {
  configPlan = null;
  byId("config-plan-result").style.display = "none";
  byId("config-apply").disabled = true;
  byId("config-authorize").disabled = true;
  byId("config-authorize").checked = false;
});
text("current-host", currentHost ? "当前: " + currentHost : "当前: 默认设备");
setConfigStatus("尚未读取配置");
loadSettings();
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
    settings_store: SettingsStore | None = None,
    config_workbench: ConfigWorkbench | None = None,
) -> type[BaseHTTPRequestHandler]:
    manager = scan_manager or ScanJobManager()
    settings = settings_store or SettingsStore()
    try:
        for saved_host in settings.load()["saved_printers"]:
            registry.allow(saved_host)
    except SettingsError:
        # Keep the dashboard available; the settings API reports the exact
        # load failure when the user opens or changes preferences.
        pass

    def persist_registry_printers() -> None:
        settings.update_saved_printers(registry.hosts())

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
            elif path == "/api/counters.csv":
                readings = registry.read_many()
                devices = [
                    reading_payload(reading, key)
                    for key, reading in readings.items()
                ]
                body = counters_csv(devices)
                self._respond(
                    200,
                    "text/csv; charset=utf-8",
                    body,
                    headers={
                        "Content-Disposition": (
                            "attachment; filename=\"kyocera-counters.csv\""
                        ),
                        "X-Content-Type-Options": "nosniff",
                    },
                )
            elif path == "/api/settings":
                try:
                    payload = settings.load()
                except SettingsError as exc:
                    self._json_error(500, str(exc))
                    return
                body = json.dumps(
                    payload, ensure_ascii=False
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif path in {"/api/config", "/api/config/baseline", "/api/config/compare"}:
                requested = (parse_qs(parsed.query).get("host") or [None])[0]
                try:
                    host = registry.resolve(requested)
                except KeyError:
                    self._json_error(
                        404 if requested is not None else 400,
                        (
                            f"unknown device: {requested}"
                            if requested is not None
                            else "no printer selected"
                        ),
                    )
                    return
                if config_workbench is None:
                    self._json_error(
                        409,
                        "configuration is unavailable for this connection",
                    )
                    return
                try:
                    if path == "/api/config":
                        payload = config_workbench.overview(host)
                    elif path == "/api/config/baseline":
                        payload = {
                            "host": host,
                            "baseline": config_workbench.baseline_info(host),
                        }
                    else:
                        payload = config_workbench.compare_baseline(host)
                except ConfigWorkbenchError as exc:
                    self._json_error(502, str(exc))
                    return
                except (ConfigSnapshotError, ConfigWritePlanError) as exc:
                    self._json_error(409, str(exc))
                    return
                body = json.dumps(
                    payload, ensure_ascii=False
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
                    try:
                        registry.add_host(printer.address)
                    except ValueError:
                        continue
                warning = None
                try:
                    persist_registry_printers()
                except (SettingsError, OSError) as exc:
                    warning = (
                        "printers were found but could not be saved: "
                        f"{type(exc).__name__}: {exc}"
                    )
                body = json.dumps(
                    {
                        "printers": [printer.to_dict() for printer in printers],
                        "error": None,
                        "warning": warning,
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
            if parsed.path not in {
                "/api/devices",
                "/api/scans",
                "/api/settings",
                "/api/config/baseline",
                "/api/config/plan",
                "/api/config/apply",
            }:
                self._respond(404, "text/plain; charset=utf-8", b"not found\n")
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = 0
            maximum = 64 * 1024 if parsed.path == "/api/settings" else 4096
            if length <= 0 or length > maximum:
                self._json_error(
                    400,
                    f"request body must be 1-{maximum} bytes",
                )
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json_error(400, "request body must be JSON")
                return
            if not isinstance(payload, dict):
                self._json_error(400, "request body must be a JSON object")
                return
            if parsed.path == "/api/settings":
                try:
                    if "saved_printers" not in payload:
                        current = settings.load()
                        payload["saved_printers"] = current["saved_printers"]
                    saved = settings.save(payload)
                except SettingsError as exc:
                    self._json_error(400, str(exc))
                    return
                body = json.dumps(
                    saved, ensure_ascii=False
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
                return
            if parsed.path.startswith("/api/config/"):
                self._config_operation(parsed.path, payload, config_workbench)
                return
            if parsed.path == "/api/scans":
                self._start_scan(payload)
                return
            try:
                host = registry.add_host(payload.get("host"))
            except ValueError as exc:
                self._json_error(400, str(exc))
                return
            try:
                persist_registry_printers()
            except (SettingsError, OSError) as exc:
                self._json_error(
                    500,
                    "device was added for this session but could not be saved: "
                    f"{type(exc).__name__}: {exc}",
                )
                return
            body = json.dumps(
                {"device": host, "devices": registry.hosts()},
                ensure_ascii=False,
            ).encode("utf-8")
            self._respond(200, "application/json; charset=utf-8", body)

        def _config_operation(
            self,
            path: str,
            payload: dict[str, object],
            workbench: ConfigWorkbench | None,
        ) -> None:
            if workbench is None:
                self._json_error(
                    409,
                    "configuration is unavailable for this connection",
                )
                return
            requested = payload.get("host")
            if requested is not None and not isinstance(requested, str):
                self._json_error(400, "host must be a string or null")
                return
            try:
                host = registry.resolve(requested)
            except KeyError:
                self._json_error(
                    404 if requested is not None else 400,
                    (
                        f"unknown device: {requested}"
                        if requested is not None
                        else "no printer selected"
                    ),
                )
                return
            try:
                if path == "/api/config/baseline":
                    result = workbench.save_baseline(host)
                else:
                    item_id = payload.get("item_id")
                    value = payload.get("value")
                    if isinstance(item_id, bool) or not isinstance(item_id, int):
                        raise ValueError("item_id must be an integer")
                    if not isinstance(value, str):
                        raise ValueError("value must be a string")
                    if path == "/api/config/plan":
                        result = workbench.plan(host, item_id, value)
                    else:
                        confirmation = payload.get("confirmation_token")
                        if not isinstance(confirmation, str):
                            raise ValueError(
                                "confirmation_token must be a string"
                            )
                        result = workbench.apply(
                            host,
                            item_id,
                            value,
                            confirmation,
                        )
            except ConfigWorkbenchError as exc:
                self._json_error(409, str(exc))
                return
            except (
                ConfigSnapshotError,
                ConfigWritePlanError,
                ConfigWriteExecutionError,
                ValueError,
            ) as exc:
                self._json_error(400, str(exc))
                return
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
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
                current_settings = settings.load()
                selected_preset = preset_payload(
                    current_settings, payload.get("preset_id")
                )
                options = ScanOptions.from_payload(
                    merge_scan_payload(payload, selected_preset)
                )
                save_to_folder = payload.get("save_to_folder", False)
                if not isinstance(save_to_folder, bool):
                    raise SettingsError("save_to_folder must be a boolean")
                output_directory = (
                    Path(current_settings["scan_directory"])
                    if save_to_folder
                    else None
                )
                job = manager.start(
                    host,
                    options,
                    output_directory=output_directory,
                )
            except ScanBusyError as exc:
                self._json_error(409, str(exc))
                return
            except (SettingsError, ValueError) as exc:
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
                    "Content-Disposition": content_disposition(
                        artifact.filename
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
    settings_store: SettingsStore | None = None,
    config_workbench: ConfigWorkbench | None = None,
) -> None:
    server = create_server(
        registry,
        bind=bind,
        port=port,
        discover_fn=discover_fn,
        scan_manager=scan_manager,
        settings_store=settings_store,
        config_workbench=config_workbench,
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
    settings_store: SettingsStore | None = None,
    config_workbench: ConfigWorkbench | None = None,
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
            settings_store=settings_store,
            config_workbench=config_workbench,
        ),
    )
