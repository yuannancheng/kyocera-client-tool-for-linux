"""Local web dashboard for printer status, scanning and reviewed writes.

The dashboard serves the same ``PrinterSnapshot`` data as ``--json``. It binds
to loopback by default. Configuration, Wi-Fi and scan actions require explicit
API confirmation where they change device state.
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
from .config_web import (
    ConfigCategoryError,
    ConfigWorkbench,
    ConfigWorkbenchError,
)
from .i18n import (
    LANGUAGE_AUTO,
    normalize_language_preference,
    render_localized_page,
    resolve_language,
)
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
from .updates import (
    UpdateCheckError,
    UpdateChecker,
    render_update_runtime,
)
from .wifi import SECURITY_MODES, WifiError, WifiWorkbench

Collector = Callable[[], PrinterSnapshot]

_SCAN_JOB_PATH_RE = re.compile(r"^/api/scans/([0-9a-f]{32})$")
_SCAN_FILE_PATH_RE = re.compile(
    r"^/api/scans/([0-9a-f]{32})/files/([0-9]+)$"
)


def _is_usb_device(value: str) -> bool:
    return value.startswith("libusb:") or value.startswith("/dev/")


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
<title data-i18n="KYOCERA 打印机">KYOCERA 打印机</title>
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
  .toast-stack { position: fixed; top: 18px; right: 18px; z-index: 1000;
                 display: grid; gap: 10px; width: min(390px, calc(100vw - 36px));
                 pointer-events: none; }
  .toast { pointer-events: auto; padding: 12px 14px; border-radius: 10px;
           border: 1px solid #d99b9b; border-left: 5px solid #b73535;
           background: #fff1f1; color: #681515;
           box-shadow: 0 10px 30px rgba(25, 31, 36, .18);
           overflow-wrap: anywhere; animation: toast-in .18s ease-out; }
  .toast.success { border-color: #9bc6a1; border-left-color: #2f7d32;
                   background: #edf8ef; color: #194d20; }
  .toast.info { border-color: #a7bfd3; border-left-color: #356f9f;
                background: #edf5fb; color: #174b74; }
  @keyframes toast-in {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .muted { color: #6b747d; font-size: .85rem; margin-top: 14px; }
  button { margin-left: auto; padding: 6px 12px; border-radius: 8px;
           border: 1px solid #b9c1c9; background: #fff; cursor: pointer; }
  a.button { padding: 6px 12px; border-radius: 8px; border: 1px solid #b9c1c9;
             background: #fff; color: inherit; text-decoration: none; }
  label.notify { display: inline-flex; align-items: center; gap: 6px;
                 font-size: .9rem; }
  label.language { display: inline-flex; align-items: center; gap: 6px;
                   margin-left: auto; font-size: .9rem; }
  label.language select { padding: 5px 8px; border-radius: 8px;
                          border: 1px solid #b9c1c9; background: #fff;
                          color: inherit; font: inherit; }
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
    .toast { background: #3c2022; color: #f6c8c8; border-color: #74393d;
             border-left-color: #db6868; }
    .toast.success { background: #1d3523; color: #d3f2d8;
                     border-color: #356943; border-left-color: #64b56f; }
    .toast.info { background: #1b3042; color: #cce7ff;
                  border-color: #35566f; border-left-color: #5c9bd1; }
    button, a.button, form.add input, label.language select {
      background: #1c2228; color: inherit; border-color: #3a444e;
    }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1 data-i18n="KYOCERA 打印机">KYOCERA 打印机</h1>
    <span id="count" class="pill" data-i18n="加载中">加载中</span>
    <label class="language"><span data-i18n="语言">语言</span>
      <select id="language-select" data-i18n-aria-label="语言">
        <option value="auto" data-i18n="自动（设备语言）">自动（设备语言）</option>
        <option value="zh-CN" data-i18n="简体中文">简体中文</option>
        <option value="en-US">English</option>
      </select>
    </label>
    <button id="version-check" type="button" data-i18n="检查更新">检查更新</button>
    <a class="button" href="/api/counters.csv" data-i18n="导出计数 CSV">导出计数 CSV</a>
    <label class="notify"><input id="notify" type="checkbox">
      <span data-i18n="状态通知">状态通知</span></label>
    <button id="discover" type="button" data-i18n="发现打印机">发现打印机</button>
  </header>
  <form id="add" class="add" autocomplete="off">
    <input id="host" name="host" inputmode="url"
           data-i18n-placeholder="手动添加打印机 IP，例如 192.168.0.220"
           placeholder="手动添加打印机 IP，例如 192.168.0.220" required>
    <button type="submit" data-i18n="添加设备">添加设备</button>
  </form>
  <div id="devices" class="grid"></div>
  <div id="meta" class="muted"></div>
</main>
<div id="toasts" class="toast-stack" role="status" aria-live="polite"></div>
<script>
const byId = (id) => document.getElementById(id);
const tr = (source, vars = {}) => window.I18n.translate(source, vars);
const tv = (value) => window.I18n.value(value);
I18n.applyStatic();
const statusClass = (normal) => normal === true ? "pill ok"
  : normal === false ? "pill warn" : "pill";
let previousStates = {};

function showToast(message, kind = "error") {
  const stack = byId("toasts");
  const text = message == null || message === ""
    ? tr("发生未知错误") : String(message);
  const duplicate = Array.from(stack.children).some(
    (item) => item.dataset.message === text
  );
  if (duplicate) return;
  const toast = document.createElement("div");
  toast.className = "toast " + kind;
  toast.dataset.message = text;
  toast.textContent = text;
  stack.append(toast);
  window.setTimeout(() => toast.remove(), kind === "error" ? 8000 : 4500);
}

function line(label, value) {
  const div = document.createElement("div");
  div.className = "line";
  const span = document.createElement("span");
  span.className = "label";
  span.textContent = tr(label) + ": ";
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
  name.textContent = (snapshot && snapshot.model) || tr("未知打印机");
  const pill = document.createElement("span");
  pill.className = statusClass(snapshot ? snapshot.normal : null);
  pill.textContent = snapshot
    ? (snapshot.normal === true ? tr("正常")
      : snapshot.normal === false ? tr("警告") : tr("未知"))
    : tr("不可用");
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
    ? tr("缓存 · {time}", {time: device.collected_at})
    : tr("读取耗时 {ms} ms", {ms: device.elapsed_ms});
  link.append(meta);
  return link;
}

function render(data) {
  const box = byId("devices");
  box.replaceChildren();
  const devices = data.devices || [];
  byId("count").textContent = tr("{count} 台设备", {
    count: devices.length
  });
  byId("count").className = devices.length ? "pill ok" : "pill";
  if (!devices.length) {
    byId("meta").textContent = tr(
      "还没有设备。点击“发现打印机”，或手动输入 IP。"
    );
    return;
  }
  for (const device of devices) {
    box.append(card(device));
  }
  notifyChanges(devices);
  byId("meta").textContent = tr("更新于 {time}", {
    time: new Date().toLocaleTimeString(window.KYOCERA_LOCALE)
  });
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
        const stateLabel = {
          normal: tr("正常"),
          warning: tr("警告"),
          unknown: tr("未知"),
          unavailable: tr("不可用")
        }[state] || tr(state);
        new Notification(tr("京瓷打印机状态变化"), {
          body: tr("{name} ({device}) 状态变为 {state}", {
            name, device, state: stateLabel
          })
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
    showToast(String(err));
  }
}

async function discover() {
  const button = byId("discover");
  button.disabled = true;
  button.textContent = tr("正在搜索…");
  try {
    const response = await fetch("/api/discover", { cache: "no-store" });
    const data = await response.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    await load();
    byId("meta").textContent = data.warning
      ? data.warning
      : tr("发现 {count} 台打印机，结果已保存", {
          count: data.printers?.length || 0
        });
  } catch (err) {
    showToast(String(err));
  } finally {
    button.disabled = false;
    button.textContent = tr("发现打印机");
  }
}

async function addDevice(event) {
  event.preventDefault();
  const input = byId("host");
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
    await load();
    byId("meta").textContent = tr("已添加并保存打印机 {host}", {host});
    showToast(tr("已添加打印机 {host}", {host}), "success");
  } catch (err) {
    showToast(String(err));
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
<title data-i18n="KYOCERA 打印机状态">KYOCERA 打印机状态</title>
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
  .push-result.ready { color: #145014; }
  .push-result.warning { color: #7a4d00; }
  .push-result.failure { color: #751a1a; }
  .toast-stack { position: fixed; top: 18px; right: 18px; z-index: 1000;
                 display: grid; gap: 10px; width: min(410px, calc(100vw - 36px));
                 pointer-events: none; }
  .toast { pointer-events: auto; padding: 12px 14px; border-radius: 10px;
           border: 1px solid #d99b9b; border-left: 5px solid #b73535;
           background: #fff1f1; color: #681515;
           box-shadow: 0 10px 30px rgba(25, 31, 36, .18);
           overflow-wrap: anywhere; animation: toast-in .18s ease-out; }
  .toast.success { border-color: #9bc6a1; border-left-color: #2f7d32;
                   background: #edf8ef; color: #194d20; }
  .toast.info { border-color: #a7bfd3; border-left-color: #356f9f;
                background: #edf5fb; color: #174b74; }
  @keyframes toast-in {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  button { margin-left: auto; padding: 6px 12px; border-radius: 8px;
           border: 1px solid #b9c1c9; background: #fff; cursor: pointer; }
  button:disabled { cursor: wait; opacity: .65; }
  header button { margin-left: 0; }
  label.language { display: inline-flex; align-items: center; gap: 6px;
                   margin-left: auto; font-size: .9rem; }
  label.language select { padding: 5px 8px; border-radius: 8px;
                          border: 1px solid #b9c1c9; background: #fff;
                          color: inherit; font: inherit; }
  form.scan { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
              gap: 12px; margin-top: 12px; align-items: end; }
  form.scan label, .settings label { display: grid; gap: 6px; color: #5c6670;
                                      font-size: .82rem; }
  form.scan select, .settings input, .settings select {
    padding: 8px 10px; border-radius: 8px;
    border: 1px solid #b9c1c9; background: #fff;
    color: inherit; font: inherit;
  }
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
  .config-layout { display: grid; grid-template-columns: 190px minmax(0, 1fr);
                   gap: 16px; margin-top: 14px; align-items: start; }
  .config-nav { display: grid; gap: 6px; position: sticky; top: 12px; }
  .config-tab { margin: 0; text-align: left; padding: 9px 11px; border: 1px solid transparent;
                background: transparent; color: inherit; border-radius: 8px; }
  .config-tab:hover { background: #eef2f5; }
  .config-tab.active { background: #e2edf7; border-color: #b8cee0;
                       color: #174b74; font-weight: 650; }
  .config-tab small { display: block; margin-top: 2px; color: #6b747d;
                      font-size: .74rem; font-weight: 400; }
  .config-pane { min-width: 0; border: 1px solid #dfe3e8; border-radius: 10px;
                 padding: 14px; background: #fbfcfd; }
  .config-pane-head { display: grid; grid-template-columns: minmax(0, 1fr) max-content;
                      gap: 12px; align-items: start; }
  .config-pane-head > div { min-width: 0; }
  .config-pane-head h2 { font-size: 1.08rem; margin: 0 0 4px; }
  .config-pane-head p { margin: 0; color: #6b747d; font-size: .84rem; }
  .config-pane-head button { margin: 0; white-space: nowrap;
                             justify-self: end; align-self: start; }
  .config-setting-grid { display: grid; gap: 10px; margin-top: 12px; }
  .config-setting { display: grid; grid-template-columns: minmax(0, 1fr) auto;
                    gap: 12px; padding: 12px; border-radius: 9px;
                    border: 1px solid #e1e5e9; background: #fff; }
  .config-setting .description { margin-top: 4px; color: #6b747d;
                                 font-size: .82rem; }
  .config-setting .current { margin-top: 8px; font-size: .9rem; }
  .config-setting .current strong { font-size: 1rem; }
  .config-readonly-grid { display: grid; gap: 10px; margin-top: 12px;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
  .config-readonly-item { padding: 11px; border-radius: 8px;
    border: 1px solid #e2e6ea; background: #f8fafb; }
  .config-readonly-item strong { display: block; margin-bottom: 5px; }
  .config-readonly-item .value { color: #28323b; font-size: 1rem; }
  .config-readonly-item .kind { margin-top: 5px; color: #7a838c;
    font-size: .78rem; }
  .config-setting-actions { display: flex; align-items: end; gap: 8px; }
  .config-setting-actions select, .config-setting-actions input {
    min-width: 118px; padding: 8px 10px; border-radius: 8px;
    border: 1px solid #b9c1c9; background: #fff; color: inherit; font: inherit;
  }
  .config-setting-actions button { margin: 0; white-space: nowrap; }
  .config-setting-actions button:not(:disabled) { border-color: #83a9c9;
                                                   background: #edf5fb; color: #174b74; }
  .config-subheading { margin: 16px 0 8px; font-size: .92rem;
                       color: #3f4d58; }
  .config-help { margin: 6px 0 0; }
  .config-maintenance { margin-top: 14px; padding-top: 12px;
                        border-top: 1px solid #e5e9ed; }
  .config-maintenance summary { cursor: pointer; color: #4c5964; font-weight: 600; }
  .config-maintenance .inline { margin-top: 10px; }
  .warning-box { margin-top: 12px; padding: 10px 12px; border-radius: 8px;
                 background: #fff3cf; color: #624600; border: 1px solid #e6cc82; }
  .config-table-wrap { max-height: 360px; overflow: auto; margin-top: 10px; }
  .config-table-wrap table { margin-top: 0; }
  .config-table-wrap tr.unreadable td { color: #8b3d3d; }
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
  @media (max-width: 720px) {
    body { padding: 14px; }
    .config-layout { grid-template-columns: 1fr; }
    .config-nav { position: static; display: flex; overflow-x: auto;
                  padding-bottom: 4px; }
    .config-tab { min-width: 132px; white-space: nowrap; }
    .config-setting { grid-template-columns: 1fr; }
    .config-setting-actions { flex-wrap: wrap; }
    .config-setting-actions select, .config-setting-actions input {
      flex: 1 1 140px;
    }
  }
  @media (prefers-color-scheme: dark) {
    body { background: #14181c; color: #e7ebef; }
    .card { background: #1c2228; border-color: #2b333b; }
    .pill { background: #303842; color: #e7ebef; }
    .pill.ok { background: #1d3f22; color: #d3f2d8; }
    .pill.warn { background: #4a2326; color: #f6c8c8; }
    .toast { background: #3c2022; color: #f6c8c8; border-color: #74393d;
             border-left-color: #db6868; }
    .toast.success { background: #1d3523; color: #d3f2d8;
                     border-color: #356943; border-left-color: #64b56f; }
    .toast.info { background: #1b3042; color: #cce7ff;
                  border-color: #35566f; border-left-color: #5c9bd1; }
    .bar { background: #2b333b; }
    th, td { border-color: #2b333b; }
    button, form.scan select, .settings input, .settings select,
    label.language select {
      background: #1c2228; color: inherit; border-color: #3a444e;
    }
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
    .config-pane { background: #181e24; border-color: #2d3842; }
    .config-tab:hover { background: #202a32; }
    .config-tab.active { background: #20384b; border-color: #355a78; color: #cce7ff; }
    .config-tab small, .config-pane-head p, .config-setting .description {
      color: #9aa4ae;
    }
    .config-setting { background: #1c2228; border-color: #2d3842; }
    .config-readonly-item { background: #1c2228; border-color: #2d3842; }
    .config-readonly-item .value { color: #e4edf5; }
    .config-readonly-item .kind { color: #9aa4ae; }
    .config-setting-actions select, .config-setting-actions input {
      background: #14191e; border-color: #3a444e;
    }
    .config-setting-actions button:not(:disabled) {
      background: #203b50; color: #cce7ff; border-color: #456b86;
    }
    .config-maintenance { border-color: #2d3842; }
    .config-maintenance summary { color: #b8c2cc; }
    .config-subheading { color: #c5ced7; }
    .push-result.ready { color: #d3f2d8; }
    .push-result.warning { color: #f6dfaa; }
    .push-result.failure { color: #f6c8c8; }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1 id="model" data-i18n="KYOCERA 打印机">KYOCERA 打印机</h1>
    <span id="status" class="pill" data-i18n="加载中">加载中</span>
    <a href="/" data-i18n="返回总览">返回总览</a>
    <label class="language"><span data-i18n="语言">语言</span>
      <select id="language-select" data-i18n-aria-label="语言">
        <option value="auto" data-i18n="自动（设备语言）">自动（设备语言）</option>
        <option value="zh-CN" data-i18n="简体中文">简体中文</option>
        <option value="en-US">English</option>
      </select>
    </label>
    <button id="version-check" type="button" data-i18n="检查更新">检查更新</button>
    <button id="refresh" type="button" data-i18n="刷新">刷新</button>
  </header>
  <div class="grid">
    <div class="card"><div class="label" data-i18n="序列号">序列号</div><div id="serial" class="value">-</div></div>
    <div class="card"><div class="label" data-i18n="固件">固件</div><div id="firmware" class="value">-</div></div>
    <div class="card"><div class="label" data-i18n="地址">地址</div><div id="address" class="value">-</div></div>
    <div class="card"><div class="label" data-i18n="面板显示">面板显示</div><div id="display" class="value">-</div></div>
    <div class="card">
      <div class="label" data-i18n="碳粉">碳粉</div>
      <div id="toner" class="value">-</div>
      <div class="bar"><span id="toner-bar"></span></div>
    </div>
    <div class="card"><div class="label" data-i18n="累计打印页数">累计打印页数</div><div id="lifetime" class="value">-</div></div>
    <div class="card"><div class="label" data-i18n="扫描计数">扫描计数</div><div id="scan" class="value">-</div></div>
    <div class="card"><div class="label" data-i18n="感光鼓计数">感光鼓计数</div><div id="drum" class="value">-</div></div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="纸盒">纸盒</div>
    <table><thead><tr><th data-i18n="名称">名称</th><th data-i18n="状态">状态</th><th data-i18n="纸张">纸张</th><th data-i18n="余量">余量</th></tr></thead>
    <tbody id="trays"></tbody></table>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="告警">告警</div>
    <div id="alerts" class="value">-</div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="扫描预设与保存目录">扫描预设与保存目录</div>
    <div class="settings">
      <label><span data-i18n="预设">预设</span>
        <select id="preset-select">
          <option value="" data-i18n="不使用预设">不使用预设</option>
        </select>
      </label>
      <label><span data-i18n="预设名称">预设名称</span>
        <input id="preset-name" maxlength="80"
               data-i18n-placeholder="例如：A4 彩扫"
               placeholder="例如：A4 彩扫">
      </label>
      <label><span data-i18n="Push Scan 槽位">Push Scan 槽位</span>
        <select id="preset-push-slot">
          <option value="" data-i18n="不绑定">不绑定</option>
        </select>
      </label>
      <label class="wide"><span data-i18n="保存目录">保存目录</span>
        <input id="scan-directory" maxlength="4096" placeholder="/home/user/Pictures/Kyocera Scans">
      </label>
    </div>
    <div class="inline">
      <label><input id="save-folder" type="checkbox">
        <span data-i18n="扫描完成后自动保存到该目录">扫描完成后自动保存到该目录</span></label>
      <button id="preset-save" type="button" data-i18n="保存当前设置为预设">保存当前设置为预设</button>
      <button id="preset-delete" type="button" data-i18n="删除所选预设">删除所选预设</button>
      <button id="settings-save" type="button" data-i18n="保存目录设置">保存目录设置</button>
      <span id="settings-status" class="muted"></span>
    </div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="扫描">扫描</div>
    <form id="scan-form" class="scan" autocomplete="off">
      <label><span data-i18n="颜色">颜色</span>
        <select id="scan-color">
          <option value="" data-i18n="使用设备当前设置">使用设备当前设置</option>
          <option value="FULL_COLOR" data-i18n="彩色">彩色</option>
          <option value="GRAYSCALE" data-i18n="灰度">灰度</option>
          <option value="BLACK_AND_WHITE" data-i18n="黑白">黑白</option>
          <option value="AUTO_BLACK_AND_WHITE" data-i18n="自动黑白">自动黑白</option>
          <option value="AUTO_GRAYSCALE" data-i18n="自动灰度">自动灰度</option>
        </select>
      </label>
      <label><span data-i18n="分辨率">分辨率</span>
        <select id="scan-resolution">
          <option value="" data-i18n="使用设备当前设置">使用设备当前设置</option>
          <option value="RESOLUTION_150X150">150 × 150 dpi</option>
          <option value="RESOLUTION_200X200">200 × 200 dpi</option>
          <option value="RESOLUTION_300X300">300 × 300 dpi</option>
          <option value="RESOLUTION_400X400">400 × 400 dpi</option>
          <option value="RESOLUTION_600X600">600 × 600 dpi</option>
        </select>
      </label>
      <label><span data-i18n="原稿类型">原稿类型</span>
        <select id="scan-original-image">
          <option value="" data-i18n="使用设备当前设置">使用设备当前设置</option>
          <option value="TEXT" data-i18n="文字">文字</option>
          <option value="TEXT_AND_PHOTO" data-i18n="文字和照片">文字和照片</option>
          <option value="PHOTO" data-i18n="照片">照片</option>
          <option value="FOR_OCR">OCR</option>
          <option value="MAP" data-i18n="地图">地图</option>
          <option value="LIGHT_TEXT" data-i18n="浅色文字">浅色文字</option>
        </select>
      </label>
      <label><span data-i18n="页数">页数</span>
        <select id="scan-pages">
          <option value="1" data-i18n="1 页">1 页</option>
          <option value="2" data-i18n="最多 2 页">最多 2 页</option>
          <option value="3" data-i18n="最多 3 页">最多 3 页</option>
          <option value="4" data-i18n="最多 4 页">最多 4 页</option>
          <option value="5" data-i18n="最多 5 页">最多 5 页</option>
          <option value="6" data-i18n="最多 6 页">最多 6 页</option>
          <option value="7" data-i18n="最多 7 页">最多 7 页</option>
          <option value="8" data-i18n="最多 8 页">最多 8 页</option>
          <option value="9" data-i18n="最多 9 页">最多 9 页</option>
          <option value="10" data-i18n="最多 10 页">最多 10 页</option>
        </select>
      </label>
      <label><span data-i18n="输出格式">输出格式</span>
        <select id="scan-format">
          <option value="png">PNG</option>
          <option value="pdf">PDF</option>
          <option value="jpeg">JPEG</option>
          <option value="tiff">TIFF</option>
          <option value="high_compression_pdf" data-i18n="高压缩 PDF">高压缩 PDF</option>
          <option value="xps">XPS</option>
          <option value="bmp">BMP</option>
          <option value="raw" data-i18n="RAW（高级）">RAW（高级）</option>
        </select>
      </label>
      <button id="scan-start" type="submit" data-i18n="开始扫描">开始扫描</button>
    </form>
    <div id="scan-progress" class="progress"></div>
    <div id="scan-downloads" class="downloads"></div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="设备配置">设备配置</div>
    <p class="muted" style="margin-top:6px"
       data-i18n="按官方工具的分类逐页读取和修改。读取或应用设置时只访问当前分区；提交单个属性后会回读该属性，失败时自动尝试恢复原值。网络、凭据和重置类对象仍保持只读，避免误改后断开设备。">
      按官方工具的分类逐页读取和修改。读取或应用设置时只访问当前分区；
      提交单个属性后会回读该属性，失败时自动尝试恢复原值。网络、凭据和
      重置类对象仍保持只读，避免误改后断开设备。
    </p>
    <div class="config-layout">
      <nav id="config-categories" class="config-nav"
           data-i18n-aria-label="设备配置" aria-label="设备配置分类"></nav>
      <section class="config-pane" aria-live="polite">
        <div class="config-pane-head">
          <div>
            <h2 id="config-category-title" data-i18n="设备默认值">设备默认值</h2>
            <p id="config-category-description" data-i18n="选择分类后读取。">选择分类后读取。</p>
          </div>
          <button id="config-read" type="button" data-i18n="读取此分区">读取此分区</button>
        </div>
        <div id="config-status" class="muted" data-i18n="尚未读取当前分区">尚未读取当前分区</div>
        <div id="config-mode-note" class="muted config-help"></div>
        <section id="config-status-block" hidden>
          <h3 class="config-subheading" data-i18n="设备当前状态">设备当前状态</h3>
          <div id="config-status-grid" class="config-grid"></div>
        </section>
        <section id="config-readonly-block" hidden>
          <h3 class="config-subheading" data-i18n="当前设备设置">当前设备设置</h3>
          <div id="config-readonly-items" class="config-readonly-grid"></div>
        </section>
        <section id="config-edit-block" hidden>
          <h3 class="config-subheading" data-i18n="可修改设置">可修改设置</h3>
          <div id="config-edit-status" class="muted"></div>
          <div id="config-edit-items" class="config-setting-grid"></div>
        </section>
        <section id="wifi-settings" hidden>
          <h3 class="config-subheading" data-i18n="Wi-Fi 连接配置">Wi-Fi 连接配置</h3>
          <p class="muted config-help"
             data-i18n="此分类使用官方 Wi-Fi Setup Tool 的 KGETOBJ/KSETOBJ 顺序。扫描附近网络或手动填写 SSID；密码只发送到本机服务，不写入设置文件或日志。连接失败时可能需要用打印机面板恢复网络。">
            此分类使用官方 Wi-Fi Setup Tool 的 KGETOBJ/KSETOBJ 顺序。
            扫描附近网络或手动填写 SSID；密码只发送到本机服务，不写入设置
            文件或日志。连接失败时可能需要用打印机面板恢复网络。
          </p>
          <div class="inline">
            <button id="wifi-scan" type="button" data-i18n="扫描附近网络">扫描附近网络</button>
            <span id="wifi-op-status" class="muted" data-i18n="尚未执行 Wi-Fi 操作">尚未执行 Wi-Fi 操作</span>
          </div>
          <div class="settings" style="margin-top:10px">
            <label class="wide"><span data-i18n="附近网络">附近网络</span>
              <select id="wifi-ap-select">
                <option value="" data-i18n="先扫描附近网络，或手动输入">先扫描附近网络，或手动输入</option>
              </select>
            </label>
            <label>SSID
              <input id="wifi-ssid" maxlength="32" autocomplete="off">
            </label>
            <label><span data-i18n="安全模式">安全模式</span>
              <select id="wifi-security">
                <option value="4">WPA2 PSK (AES)</option>
                <option value="3">WPA/WPA2 PSK (Auto)</option>
                <option value="2">WPA/WPA2 PSK (AES)</option>
                <option value="1">WEP</option>
                <option value="0" data-i18n="开放网络">开放网络</option>
              </select>
            </label>
            <label><span data-i18n="密码">密码</span>
              <input id="wifi-password" type="password" autocomplete="new-password">
            </label>
          </div>
          <div class="inline">
            <label><input id="wifi-connect-confirm" type="checkbox">
              <span data-i18n="确认更改设备 Wi-Fi；连接失败可能需要用打印机面板恢复网络">确认更改设备 Wi-Fi；连接失败可能需要用打印机面板恢复网络</span></label>
            <button id="wifi-connect" type="button" data-i18n="连接 Wi-Fi">连接 Wi-Fi</button>
          </div>
        </section>
        <div id="config-changes"></div>
        <details style="margin-top:12px">
          <summary><span data-i18n="技术详情：当前分区全部对象">技术详情：当前分区全部对象</span>
            <span id="config-object-count" class="muted"></span></summary>
          <p class="muted config-help"
             data-i18n="名称和状态来自官方对象表。未生成编辑器的对象可能是只读状态、凭据、网络可达性相关设置，或尚未完成写入回读验证。">
            名称和状态来自官方对象表。未生成编辑器的对象可能是只读状态、
            凭据、网络可达性相关设置，或尚未完成写入回读验证。
          </p>
          <div class="config-table-wrap">
            <table>
              <thead><tr><th data-i18n="ID">ID</th><th data-i18n="名称">名称</th><th data-i18n="状态">状态</th><th data-i18n="值">值</th></tr></thead>
              <tbody id="config-objects"></tbody>
            </table>
          </div>
        </details>
      </section>
    </div>
    <details class="config-maintenance">
      <summary data-i18n="配置基线与全量维护">配置基线与全量维护</summary>
      <p class="muted"
         data-i18n="基线和差异检查需要完整读取 147 项配置，因此只在明确执行这些维护操作时使用。">
        基线和差异检查需要完整读取 147 项配置，因此只在明确执行这些维护操作时使用。
      </p>
      <div class="inline">
        <button id="config-baseline-save" type="button" data-i18n="保存完整配置为基线">保存完整配置为基线</button>
        <button id="config-baseline-compare" type="button" data-i18n="与完整基线比较">与完整基线比较</button>
        <span id="config-baseline-info" class="muted"></span>
      </div>
    </details>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="Push Scan 状态与本地预设映射">Push Scan 状态与本地预设映射</div>
    <div class="inline">
      <button id="push-scan-read" type="button" data-i18n="读取 Push Scan 状态">读取 Push Scan 状态</button>
      <span id="push-scan-status" class="muted" data-i18n="尚未读取">尚未读取</span>
    </div>
    <div id="push-scan-grid" class="config-grid"></div>
    <div id="push-scan-note" class="muted"></div>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="label" data-i18n="设备发现">设备发现</div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px">
      <button id="discover" type="button" data-i18n="发现打印机">发现打印机</button>
      <span id="current-host" class="muted"></span>
    </div>
    <div id="devices" class="value" data-i18n="尚未搜索">尚未搜索</div>
  </div>
  <div id="meta" class="muted"></div>
</main>
<div id="toasts" class="toast-stack" role="status" aria-live="polite"></div>
<script>
const byId = (id) => document.getElementById(id);
const text = (id, value) => { byId(id).textContent = value == null || value === "" ? "-" : String(value); };
const tr = (source, vars = {}) => window.I18n.translate(source, vars);
const tv = (value) => window.I18n.value(value);
I18n.applyStatic();
const currentHost = new URLSearchParams(location.search).get("host");
let userSettings = null;
let configCategories = [];
let selectedConfigCategory = "general";
let configLoadSequence = 0;
let lastStatusError = null;
const configStatusLabels = {
  "Default paper size": "默认纸张尺寸",
  "Default media type": "默认介质类型",
  "Sleep mode": "睡眠模式",
  "Sleep time": "睡眠时间",
  "Power off timer": "关机定时器",
  "Auto error clear": "自动错误清除",
  "Auto error clear timeout": "自动错误清除等待时间",
  "Form feed timeout": "送纸超时",
  "Print density": "打印浓度",
  "Quiet mode": "静音模式",
  "Units": "长度单位",
  "Auto clear panel": "自动清除面板",
  "Auto clear panel time": "面板自动清除时间",
  "Wi-Fi connection state": "Wi-Fi 连接状态",
  "Wi-Fi enable state": "Wi-Fi 启用状态",
  "Wi-Fi SSID": "Wi-Fi 名称（SSID）",
  "Wi-Fi security mode": "Wi-Fi 安全模式",
  "Wi-Fi channel": "Wi-Fi 信道",
  "Wi-Fi RSSI": "Wi-Fi 信号强度"
};
const friendlyConfigLabel = (label) =>
  tv(configStatusLabels[label] || label);

function showToast(message, kind = "error") {
  const stack = byId("toasts");
  const text = message == null || message === ""
    ? tr("发生未知错误") : String(message);
  const duplicate = Array.from(stack.children).some(
    (item) => item.dataset.message === text
  );
  if (duplicate) return;
  const toast = document.createElement("div");
  toast.className = "toast " + kind;
  toast.dataset.message = text;
  toast.textContent = text;
  stack.append(toast);
  window.setTimeout(() => toast.remove(), kind === "error" ? 8000 : 4500);
}

function trayRows(trays) {
  const body = byId("trays");
  body.replaceChildren();
  if (!trays || trays.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4; cell.textContent = tr("无纸盒数据");
    row.append(cell); body.append(row); return;
  }
  for (const tray of trays) {
    const row = document.createElement("tr");
    for (const value of [
      tray.display_name || tray.name,
      tray.display_status || tray.status,
      tray.display_paper || tray.paper || tray.media,
      tray.display_remain || tray.remain
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value == null || value === "" ? "-" : String(value);
      row.append(cell);
    }
    body.append(row);
  }
}

function render(payload) {
  if (payload.error) {
    if (payload.error !== lastStatusError) {
      showToast(payload.error);
      lastStatusError = payload.error;
    }
  } else {
    lastStatusError = null;
  }
  const snapshot = payload.snapshot;
  if (!snapshot) {
    byId("status").textContent = tr("不可用");
    byId("status").className = "pill warn";
    byId("meta").textContent = tr("最近尝试: {time}", {
      time: payload.collected_at
    });
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
  const net = snapshot.network || {};
  text("address", net.ip);

  const status = byId("status");
  if (snapshot.normal === true) {
    status.textContent = snapshot.status_code != null
      ? String(snapshot.status_code) + " " + tr("正常") : tr("正常");
    status.className = "pill ok";
  } else if (snapshot.normal === false) {
    status.textContent = snapshot.status_code != null
      ? String(snapshot.status_code) + " " + tr("警告") : tr("警告");
    status.className = "pill warn";
  } else {
    status.textContent = tr("未知");
    status.className = "pill";
  }

  if (snapshot.toner_level != null) {
    text("toner", snapshot.toner_level + "%");
    byId("toner-bar").style.width = Math.max(0, Math.min(100, snapshot.toner_level)) + "%";
  } else {
    text("toner", tr("未知"));
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
    : tr("无告警");
  byId("meta").textContent =
    tr("设备 {device} · 读取于 {time}，耗时 {ms} ms", {
      device: payload.device || "-",
      time: payload.collected_at,
      ms: payload.elapsed_ms
    }) + (payload.cached ? tr("（缓存）") : "");
}

function statusUrl() {
  return "/api/status" + (currentHost ? "?host=" + encodeURIComponent(currentHost) : "");
}

async function load() {
  try {
    const response = await fetch(statusUrl(), { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    showToast(String(err));
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
  setScanStatus(tr("扫描失败：{error}", {error: message}), "failure");
  byId("scan-start").disabled = false;
  byId("scan-start").textContent = tr("重新扫描");
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
    link.title = tr("下载 {filename}", {filename: output.filename});
    link.addEventListener("click", (event) => {
      if (!nativeDownload(output)) return;
      event.preventDefault();
      setScanStatus(
        tr("正在下载 {filename}", {filename: output.filename}),
        "active"
      );
    });
    downloads.append(link);
  }
  let message = tr("扫描完成：{pages} 页", {
    pages: result.pages || outputs.length || 0
  }) + tr(" · 设备请求 {requested} / 设备返回 {effective} / 本地 {local}", {
    requested: result.requested_device_format || "?",
    effective: result.effective_device_format || "?",
    local: (job.output_format || "?").toUpperCase()
  });
  const saved = job.saved_paths || [];
  if (saved.length) {
    const folder = byId("scan-directory").value || tr("所选目录");
    message += tr(" · 已保存 {count} 个文件到 {folder}", {
      count: saved.length,
      folder
    });
  }
  if (result.close_error) {
    message += tr("；关闭会话警告：{error}", {
      error: result.close_error
    });
  }
  setScanStatus(message, result.close_error ? "warning" : "success");
  byId("scan-start").disabled = false;
  byId("scan-start").textContent = tr("再次扫描");
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
      const stage = tr(
        scanStageLabels[job.stage] || job.stage || "未知阶段"
      );
      const detail = (job.error && job.error.error) || job.message
        || tr("未知错误");
      showScanError(stage + " · " + detail);
      return;
    }
    const stage = tr(scanStageLabels[job.stage] || job.stage || "处理中");
    setScanStatus(
      stage + " · " + (job.message || tr("请稍候")),
      "active"
    );
    setTimeout(() => pollScan(jobId), 800);
  } catch (err) {
    showScanError(String(err));
  }
}

async function startScan(event) {
  event.preventDefault();
  const button = byId("scan-start");
  button.disabled = true;
  button.textContent = tr("正在扫描…");
  byId("scan-downloads").replaceChildren();
  setScanStatus(tr("正在创建扫描任务"), "active");
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
  none.textContent = tr("不使用预设");
  select.append(none);
  for (const preset of (userSettings?.presets || [])) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = preset.push_scan_slot == null
      ? preset.name
      : preset.name + tr("（Push {slot}）", {
          slot: preset.push_scan_slot
        });
    select.append(option);
  }
  select.value = selectedId;
}

function populatePushScanSlots() {
  const select = byId("preset-push-slot");
  if (select.options.length > 1) return;
  for (let slot = 0; slot <= 30; slot += 1) {
    const option = document.createElement("option");
    option.value = String(slot);
    option.textContent = tr("设备预设 {slot}（状态码 {code}）", {
      slot,
      code: 89000 + slot
    });
    select.append(option);
  }
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
  byId("preset-push-slot").value =
    preset.push_scan_slot == null ? "" : String(preset.push_scan_slot);
}

async function loadSettings() {
  try {
    const response = await fetch("/api/settings", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || String(response.status));
    userSettings = payload;
    byId("scan-directory").value = payload.scan_directory || "";
    populatePushScanSlots();
    renderPresets();
    setSettingsStatus("");
  } catch (err) {
    setSettingsStatus(
      tr("设置加载失败：{error}", {error: String(err)}),
      true
    );
  }
}

async function persistSettings(message) {
  try {
    const payload = {
      version: 1,
      language: userSettings?.language || window.KYOCERA_LANGUAGE_PREFERENCE,
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
    setSettingsStatus(
      tr("保存失败：{error}", {error: String(err)}),
      true
    );
  }
}

async function saveFolderSettings() {
  await persistSettings(tr("保存目录已更新"));
}

async function savePreset() {
  const name = byId("preset-name").value.trim();
  if (!name) {
    setSettingsStatus(tr("请先输入预设名称"), true);
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
    output_format: byId("scan-format").value,
    push_scan_slot: byId("preset-push-slot").value === ""
      ? null
      : Number(byId("preset-push-slot").value)
  };
  const presets = (userSettings.presets || []).filter((item) => item.id !== presetId);
  presets.push(preset);
  userSettings = {...userSettings, presets};
  await persistSettings(tr("预设已保存"));
  renderPresets(presetId);
}

async function deletePreset() {
  const presetId = byId("preset-select").value;
  if (!presetId || !userSettings) return;
  userSettings = {
    ...userSettings,
    presets: (userSettings.presets || []).filter((item) => item.id !== presetId)
  };
  await persistSettings(tr("预设已删除"));
  renderPresets();
  byId("preset-name").value = "";
  byId("preset-push-slot").value = "";
}

function setConfigStatus(message, error = false) {
  const status = byId("config-status");
  status.textContent = message;
  status.style.color = error ? "#a12222" : "";
}

function configUrl(path, params = {}) {
  const query = new URLSearchParams();
  if (currentHost) query.set("host", currentHost);
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== "") query.set(key, String(value));
  }
  const suffix = query.toString();
  return path + (suffix ? "?" + suffix : "");
}

async function configRequest(path, options = {}, params = {}) {
  let response;
  try {
    response = await fetch(configUrl(path, params), {
      cache: "no-store",
      ...options
    });
  } catch (_err) {
    throw new Error(
      tr("无法连接本机后台服务；请确认 GUI/Web 服务仍在运行后重试。")
    );
  }
  let payload;
  try {
    payload = await response.json();
  } catch (_err) {
    throw new Error(
      tr("本机后台返回了无法解析的响应（HTTP {status}）。", {
        status: response.status
      })
    );
  }
  if (!response.ok) throw new Error(payload.error || String(response.status));
  return payload;
}

function selectedCategoryInfo() {
  return configCategories.find(
    (category) => category.key === selectedConfigCategory
  ) || null;
}

function renderConfigCategories() {
  const nav = byId("config-categories");
  nav.replaceChildren();
  for (const category of configCategories) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "config-tab" +
      (category.key === selectedConfigCategory ? " active" : "");
    button.dataset.category = category.key;
    const title = document.createElement("span");
    title.textContent = tv(category.label);
    const count = document.createElement("small");
    if (category.editor === "dedicated") {
      count.textContent = tr("（{count} 项）", {
        count: category.item_count
      });
    } else if (category.editable_count) {
      count.textContent = tr("{editable}/{total} 项可修改", {
        editable: category.editable_count,
        total: category.item_count
      });
    } else {
      count.textContent = tr("{count} 项 · 只读", {
        count: category.item_count
      });
    }
    button.append(title, count);
    button.addEventListener(
      "click",
      () => selectConfigCategory(category.key)
    );
    nav.append(button);
  }
}

function updateConfigCategoryHeading() {
  const category = selectedCategoryInfo();
  byId("config-category-title").textContent =
    tv(category?.label) || tr("设备配置");
  byId("config-category-description").textContent =
    tv(category?.description) || tr("选择分类后读取。");
  byId("wifi-settings").hidden =
    selectedConfigCategory !== "wifi";
}

function clearConfigCategoryView() {
  byId("config-status-block").hidden = true;
  byId("config-readonly-block").hidden = true;
  byId("config-edit-block").hidden = true;
  byId("config-mode-note").textContent = "";
  byId("config-status-grid").replaceChildren();
  byId("config-readonly-items").replaceChildren();
  byId("config-edit-items").replaceChildren();
  byId("config-objects").replaceChildren();
  byId("config-changes").replaceChildren();
  byId("config-object-count").textContent = "";
  setEditConfigStatus("");
}

async function selectConfigCategory(key) {
  if (key === selectedConfigCategory &&
      byId("config-edit-items").childElementCount) {
    return;
  }
  selectedConfigCategory = key;
  renderConfigCategories();
  updateConfigCategoryHeading();
  clearConfigCategoryView();
  await readConfiguration();
}

async function loadConfigCategories() {
  try {
    const data = await configRequest("/api/config/categories");
    configCategories = data.categories || [];
    if (!configCategories.some(
      (category) => category.key === selectedConfigCategory
    )) {
      selectedConfigCategory = configCategories[0]?.key || "general";
    }
    renderConfigCategories();
    updateConfigCategoryHeading();
    if (configCategories.length) {
      await selectConfigCategory(selectedConfigCategory);
    }
  } catch (err) {
    setConfigStatus(
      tr("配置分类不可用：{error}", {error: String(err)}),
      true
    );
  }
}

function renderConfigObjects(objects) {
  const body = byId("config-objects");
  body.replaceChildren();
  for (const object of objects || []) {
    const row = document.createElement("tr");
    if (!object.readable) row.className = "unreadable";
    for (const value of [
      object.item_id,
      friendlyConfigLabel(object.label),
      object.readable ? tr("可读") : tr("不可读"),
      object.sensitive ? tr("已隐藏") : tv(object.display ?? "-")
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
    name.textContent = friendlyConfigLabel(object.label);
    const reading = document.createElement("div");
    reading.className = "reading";
    reading.textContent = object.sensitive
      ? tr("已隐藏")
      : (object.readable ? tv(object.display ?? "-") : tr("不可用"));
    item.append(name, reading);
    grid.append(item);
  }
}

function renderReadonlyConfigObjects(objects) {
  const grid = byId("config-readonly-items");
  grid.replaceChildren();
  for (const object of objects || []) {
    const item = document.createElement("div");
    item.className = "config-readonly-item";
    const name = document.createElement("strong");
    name.textContent = friendlyConfigLabel(object.label);
    const reading = document.createElement("div");
    reading.className = "value";
    reading.textContent = tv(object.display ?? "—");
    const kind = document.createElement("div");
    kind.className = "kind";
    kind.textContent = tr("只读");
    item.append(name, reading, kind);
    grid.append(item);
  }
}

function controlDeviceValue(control) {
  const value = Number(control.value);
  if (!Number.isFinite(value)) return null;
  const scale = Number(control.dataset.configScale || "1");
  const stored = scale === 1 ? value : value / scale;
  return Number.isInteger(stored) ? stored : null;
}

function updateConfigSettingState(card) {
  const control = card.querySelector("[data-config-control]");
  const button = card.querySelector("[data-config-apply]");
  if (!control || !button) return;
  const value = controlDeviceValue(control);
  const expected = Number(card.dataset.currentValue);
  button.disabled = control.disabled || value == null || value === expected;
}

function applyEditedConfig(itemId) {
  const card = document.querySelector(
    `#config-edit-items [data-item-id="${itemId}"]`
  );
  if (!card) return;
  const control = card.querySelector("[data-config-control]");
  const button = card.querySelector("[data-config-apply]");
  const value = controlDeviceValue(control);
  const expected = Number(card.dataset.currentValue);
  if (value == null) {
    setEditConfigStatus(tr("请输入设备支持的有效整数值"), true);
    return;
  }
  const rawUnit = control.dataset.configUnit || "";
  const unit = rawUnit ? " " + tv(rawUnit) : "";
  if (!window.confirm(
    tr(
      "确认把「{label}」从当前值改为 {value}？提交后会读取设备验证，失败时尝试恢复原值。",
      {
        label: tv(card.dataset.label),
        value: control.value + unit
      }
    )
  )) return;
  button.disabled = true;
  setEditConfigStatus(tr("正在写入并回读设备…"));
  fetch(configUrl("/api/config/apply"), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      host: currentHost,
      item_id: itemId,
      value,
      expected_value: expected,
      confirm: true
    })
  }).then(async response => {
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || String(response.status));
    card.dataset.currentValue = String(payload.requested);
    const current = card.querySelector("[data-config-current]");
    current.textContent = tv(
      payload.observed_display || String(payload.observed)
    );
    control.value = String(payload.observed);
    setEditConfigStatus(tr("属性 {id} 已写入并回读成功", {id: itemId}));
    showToast(tr("「{label}」已应用并回读成功", {
      label: tv(card.dataset.label)
    }), "success");
  }).catch(err => {
    const message = tr("写入失败：{error}", {error: String(err)});
    setEditConfigStatus(message, true);
    showToast(message);
  }).finally(() => {
    updateConfigSettingState(card);
  });
}

function setEditConfigStatus(message, error = false) {
  const status = byId("config-edit-status");
  status.textContent = message;
  status.style.color = error ? "#a12222" : "";
}

function renderConfigEditing(editing) {
  const body = byId("config-edit-items");
  body.replaceChildren();
  if (!editing?.available) {
    setEditConfigStatus(tr("当前连接不提供设备写入通道"));
    return;
  }
  const items = editing.items || [];
  if (!items.length) {
    setEditConfigStatus(tr("没有可显示的已审核属性"));
    return;
  }
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "config-setting";
    card.dataset.itemId = String(item.item_id);
    card.dataset.currentValue = String(item.current_value);
    card.dataset.label = item.label;

    const identity = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = tv(item.label);
    const detail = document.createElement("div");
    detail.className = "description";
    detail.textContent = tv(item.description);
    const current = document.createElement("div");
    current.className = "current";
    current.append(document.createTextNode(tr("当前值：")));
    const currentValue = document.createElement("strong");
    currentValue.dataset.configCurrent = "";
    currentValue.textContent = tv(item.current_display || tr("不可读"));
    current.append(currentValue);
    identity.append(label, detail, current);

    const actions = document.createElement("div");
    actions.className = "config-setting-actions";
    let control;
    if (item.choices?.length) {
      control = document.createElement("select");
      for (const choice of item.choices) {
        const option = document.createElement("option");
        option.value = String(choice.value);
        option.textContent = tv(choice.label);
        control.append(option);
      }
    } else {
      control = document.createElement("input");
      control.type = "number";
      control.min = "0";
      const scale = Number(item.scale || 1);
      control.step = String(scale);
      control.value = item.current_value == null
        ? "" : String(item.current_value * scale);
    }
    control.dataset.configControl = "";
    control.dataset.configScale = String(item.scale || 1);
    control.dataset.configUnit = item.choices?.length ? "" : (item.unit || "");
    control.disabled = !item.readable;
    if (item.choices?.length) {
      control.value = item.current_value == null
        ? "" : String(item.current_value);
    }
    control.addEventListener("input", () => updateConfigSettingState(card));
    control.addEventListener("change", () => updateConfigSettingState(card));
    actions.append(control);
    if (control.dataset.configUnit) {
      const unit = document.createElement("span");
      unit.className = "muted";
      unit.textContent = tv(control.dataset.configUnit);
      actions.append(unit);
    }

    const button = document.createElement("button");
    button.type = "button";
    button.dataset.configApply = "";
    button.textContent = tr("应用此设置");
    button.disabled = !item.readable;
    button.addEventListener("click", () => applyEditedConfig(item.item_id));
    actions.append(button);

    card.append(identity, actions);
    body.append(card);
    updateConfigSettingState(card);
  }
  setEditConfigStatus("");
}

function renderConfigOverview(data) {
  const category = data.category || {};
  if (category.key) selectedConfigCategory = category.key;
  byId("config-category-title").textContent =
    tv(category.label) || tr("设备配置");
  byId("config-category-description").textContent =
    tv(category.description) || "";
  renderConfigCategories();
  const baseline = data.baseline || {};
  byId("config-baseline-info").textContent = baseline.available
    ? tr("基线：{time} · 可读 {read}/{total}", {
        time: baseline.created_at,
        read: baseline.read,
        total: baseline.total
      })
    : (baseline.error
        ? tr("基线不可用：{error}", {error: baseline.error})
        : tr("尚未保存基线"));
  renderConfigStatusObjects(data.status_objects);
  renderReadonlyConfigObjects(data.read_only_objects);
  renderConfigObjects(data.objects);
  renderConfigEditing(data.editing);
  const statusObjects = data.status_objects || [];
  const readonlyObjects = data.read_only_objects || [];
  const editableItems = data.editing?.available
    ? (data.editing.items || [])
    : [];
  byId("config-status-block").hidden = statusObjects.length === 0;
  byId("config-readonly-block").hidden = readonlyObjects.length === 0;
  byId("config-edit-block").hidden = editableItems.length === 0;
  byId("config-mode-note").textContent = data.editing?.available
    ? (editableItems.length
        ? tr("下列属性已通过官方映射和可逆写入审计；其余对象保持只读。")
        : (selectedConfigCategory === "wifi"
            ? tr("Wi-Fi 使用本分类内的专用连接流程；通用属性编辑器不对凭据类对象开放。")
            : tr("此分类没有已审核的通用属性编辑器，仅显示设备状态。")))
    : (selectedConfigCategory === "wifi"
        ? tr("当前连接的通用配置写入不可用；本分类的 Wi-Fi 连接仍使用专用 KSETOBJ 流程。")
        : tr("当前连接未提供配置写入通道；这里仅展示设备读取结果。"));
  byId("config-changes").replaceChildren();
  byId("config-object-count").textContent = data.hidden_count
    ? tr("（显示 {shown} 项，{hidden} 项设备不支持已隐藏）", {
        shown: data.objects?.length || 0,
        hidden: data.hidden_count
      })
    : tr("（{count} 项）", {count: data.objects?.length || 0});
  setConfigStatus(
    tr("“{category}”读取完成：{read}/{total} 项可读", {
      category: tv(category.label || selectedConfigCategory),
      read: data.read,
      total: data.total
    })
  );
}

async function runConfigAction(button, message, action) {
  const original = button.textContent;
  button.disabled = true;
  setConfigStatus(message);
  try {
    await action();
  } catch (err) {
    setConfigStatus(String(err), true);
    showToast(String(err));
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function readConfiguration() {
  const sequence = ++configLoadSequence;
  const category = selectedCategoryInfo();
  const label = tv(category?.label || selectedConfigCategory);
  const count = category?.item_count
    ? tr("（{count} 项）", {count: category.item_count}) : "";
  await runConfigAction(
    byId("config-read"),
    tr("正在读取“{category}”{count}…", {
      category: label,
      count
    }),
    async () => {
      const data = await configRequest(
        "/api/config",
        {},
        {category: selectedConfigCategory}
      );
      if (sequence !== configLoadSequence) return;
      renderConfigOverview(data);
    }
  );
}

async function saveConfigurationBaseline() {
  if (!window.confirm(tr("保存当前完整配置为新基线？敏感值会以 0600 权限保存在本机。"))) {
    return;
  }
  await runConfigAction(
    byId("config-baseline-save"),
    tr("正在读取并保存私有基线…"),
    async () => {
      const data = await configRequest("/api/config/baseline", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({host: currentHost})
      });
      const baseline = data.baseline || {};
      byId("config-baseline-info").textContent = baseline.available
        ? tr("基线：{time} · 可读 {read}/{total}", {
            time: baseline.created_at,
            read: baseline.read,
            total: baseline.total
          })
        : tr("基线已保存");
      setConfigStatus(tr("完整配置基线已保存"));
      showToast(tr("完整配置基线已保存"), "success");
    }
  );
}

function appendChange(box, title, changes) {
  if (!changes || !changes.length) return;
  const heading = document.createElement("div");
  heading.textContent = `${tr(title)}: ${changes.length}`;
  heading.style.fontWeight = "600";
  box.append(heading);
  for (const change of changes) {
    const row = document.createElement("div");
    const before = change.sensitive
      ? tr("已隐藏") : tv(change.before?.display ?? "-");
    const after = change.sensitive
      ? tr("已隐藏") : tv(change.after?.display ?? "-");
    row.textContent = `${change.item_id} · ${tv(change.label)}: ${before} → ${after}`;
    box.append(row);
  }
}

async function compareConfigurationBaseline() {
  await runConfigAction(
    byId("config-baseline-compare"),
    tr("正在读取当前配置并与基线比较…"),
    async () => {
      const data = await configRequest("/api/config/compare");
      const comparison = data.comparison;
      const box = byId("config-changes");
      box.replaceChildren();
      appendChange(box, "配置变化", comparison.changes);
      appendChange(box, "易变遥测变化", comparison.volatile_changes);
      appendChange(box, "读取状态变化", comparison.read_status_changes);
      if (!box.children.length) {
        box.textContent = tr("没有配置或读取状态变化");
      }
      setConfigStatus(
        tr("比较完成：{changed} 个配置变化，{status} 个读取状态变化", {
          changed: comparison.changed,
          status: comparison.read_status_changed
        })
      );
    }
  );
}

function renderPushScan(data) {
  const grid = byId("push-scan-grid");
  grid.replaceChildren();
  const objects = data.objects || {};
  const entries = [
    [tr("接口"), tv(objects.interface?.display || "未知")],
    [tr("地址类型"), tv(objects.address_type?.display || "未知")],
    [tr("目标"), tv(data.target || "未配置")],
    [tr("目标匹配本机"), data.target_matches_local === true ? tr("是")
      : data.target_matches_local === false ? tr("否") : tr("未知")],
    [tr("上次报告结果"), tv(objects.result?.display || "未知")],
    [tr("待机入口"), "--push-scan-listen"]
  ];
  for (const [name, value] of entries) {
    const item = document.createElement("div");
    item.className = "config-item";
    const label = document.createElement("div");
    label.className = "name";
    label.textContent = name;
    const reading = document.createElement("div");
    reading.className = "reading";
    reading.textContent = value;
    item.append(label, reading);
    grid.append(item);
  }
  const readiness = data.readiness || {};
  const status = byId("push-scan-status");
  status.textContent = tv(readiness.summary || readiness.state || "未知状态");
  status.className = "muted push-result " +
    (readiness.ready === true ? "ready"
      : readiness.ready === false ? "warning" : "");
  const note = byId("push-scan-note");
  note.textContent = tr(
    "设备侧 Push Scan 目标由打印机面板/Scan Destination 设置；官方 Client Tool 只读取这组状态 OID，未提供可复现的 SET 路径，因此这里不会盲写接口或目标地址。“Push Scan 槽位”只保存 Linux 本地预设映射。命令行 --push-scan-listen 可报告 89xxx；显式加上 --push-scan-run 会执行匹配的本地预设，结果 OID 回写仍未启用。"
  );
}

async function readPushScan() {
  const button = byId("push-scan-read");
  const status = byId("push-scan-status");
  button.disabled = true;
  status.textContent = tr("正在通过 SNMP 读取…");
  try {
    const data = await configRequest("/api/push-scan");
    renderPushScan(data);
  } catch (err) {
    status.textContent = tr("读取失败：{error}", {error: String(err)});
    status.className = "muted push-result failure";
  } finally {
    button.disabled = false;
  }
}

async function scanWifi() {
  const status = byId("wifi-op-status");
  const button = byId("wifi-scan");
  const select = byId("wifi-ap-select");
  button.disabled = true;
  status.textContent = tr("正在通过设备扫描附近网络；通常需要数秒…");
  try {
    const points = await configRequest("/api/wifi/scan");
    select.replaceChildren();
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = points.length
      ? tr("选择一个网络") : tr("未发现网络");
    select.append(empty);
    for (const point of points) {
      const option = document.createElement("option");
      option.value = String(point.index);
      option.dataset.ssid = point.ssid || "";
      option.dataset.security = String(point.security ?? 4);
      option.dataset.bssid = point.bssid || "";
      const signal = point.rssi == null ? "" : ` · ${point.rssi} dBm`;
      option.textContent = `${point.ssid || tr("隐藏网络")} · ${point.security_name}${signal}`;
      select.append(option);
    }
    status.textContent = tr("扫描完成，共 {count} 个网络", {
      count: points.length
    });
  } catch (err) {
    status.textContent = tr("扫描失败：{error}", {error: String(err)});
  } finally {
    button.disabled = false;
  }
}

function chooseWifiAccessPoint() {
  const select = byId("wifi-ap-select");
  const option = select.selectedOptions[0];
  if (!option || !option.value) return;
  byId("wifi-ssid").value = option.dataset.ssid || "";
  byId("wifi-security").value = option.dataset.security || "4";
  byId("wifi-password").focus();
}

async function connectWifi() {
  const status = byId("wifi-op-status");
  if (!byId("wifi-connect-confirm").checked) {
    status.textContent = tr("请先勾选确认框");
    return;
  }
  const ssid = byId("wifi-ssid").value.trim();
  const security = Number(byId("wifi-security").value);
  const password = byId("wifi-password").value;
  const option = byId("wifi-ap-select").selectedOptions[0];
  const selectedMatches = Boolean(
    option?.value
    && option.dataset.ssid === ssid
    && Number(option.dataset.security) === security
  );
  if (!ssid) {
    status.textContent = tr("SSID 不能为空");
    return;
  }
  if (!confirm(tr("确认把打印机切换到 Wi-Fi「{ssid}」？", {ssid}))) return;
  const button = byId("wifi-connect");
  button.disabled = true;
  status.textContent = tr("正在写入官方 Wi-Fi 配置并等待关联…");
  try {
    const result = await configRequest("/api/wifi/connect", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        confirm: true,
        ssid,
        security,
        password,
        bssid: selectedMatches ? (option?.dataset.bssid || "") : ""
      })
    });
    byId("wifi-password").value = "";
    byId("wifi-connect-confirm").checked = false;
    status.textContent = tr("已连接到 {ssid}（{security}）", {
      ssid: result.ssid,
      security: result.security_name
    });
    await readConfiguration();
  } catch (err) {
    status.textContent = tr("配置失败：{error}", {error: String(err)});
  } finally {
    button.disabled = false;
  }
}

async function discover() {
  const box = byId("devices");
  box.textContent = tr("正在搜索…");
  try {
    const response = await fetch("/api/discover", { cache: "no-store" });
    const data = await response.json();
    box.replaceChildren();
    if (data.error) { box.textContent = data.error; return; }
    if (!data.printers || data.printers.length === 0) {
      box.textContent = data.warning || tr("没有发现打印机");
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
    saved.textContent = tr("发现结果已保存，下次启动无需重新搜索");
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
byId("push-scan-read").addEventListener("click", readPushScan);
byId("wifi-scan").addEventListener("click", scanWifi);
byId("wifi-ap-select").addEventListener("change", chooseWifiAccessPoint);
byId("wifi-connect").addEventListener("click", connectWifi);
text("current-host", currentHost
  ? tr("当前: {host}", {host: currentHost})
  : tr("当前: 默认设备"));
setConfigStatus(tr("正在加载配置分类…"));
loadSettings();
load();
loadConfigCategories();
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
    push_scan_reader: Callable[[str], dict] | None = None,
    wifi_workbench: WifiWorkbench | None = None,
    update_checker: UpdateChecker | None = None,
) -> type[BaseHTTPRequestHandler]:
    manager = scan_manager or ScanJobManager()
    settings = settings_store or SettingsStore()
    updates = update_checker or UpdateChecker()
    try:
        for saved_host in settings.load()["saved_printers"]:
            registry.allow(saved_host)
    except SettingsError:
        # Keep the dashboard available; the settings API reports the exact
        # load failure when the user opens or changes preferences.
        pass

    def persist_registry_printers() -> None:
        settings.update_saved_printers(
            [
                host
                for host in registry.hosts()
                if not _is_usb_device(host)
            ]
        )

    class Handler(BaseHTTPRequestHandler):
        server_version = "kyocera-monitor"

        def _language_context(self) -> tuple[str, str]:
            try:
                preference = settings.load().get("language", LANGUAGE_AUTO)
            except SettingsError:
                preference = LANGUAGE_AUTO
            try:
                normalized = normalize_language_preference(preference)
            except ValueError:
                normalized = LANGUAGE_AUTO
            effective = resolve_language(
                normalized,
                self.headers.get("Accept-Language"),
            )
            return normalized, effective

        def _render_page(self, html: str) -> bytes:
            preference, effective = self._language_context()
            rendered = render_localized_page(
                html,
                preference=preference,
                effective=effective,
            )
            rendered = rendered.replace(
                "</body>",
                render_update_runtime(updates.current) + "</body>",
                1,
            )
            return rendered.encode("utf-8")

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            parsed = urlsplit(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                body = self._render_page(OVERVIEW_HTML)
                self._respond(200, "text/html; charset=utf-8", body)
            elif path == "/device":
                body = self._render_page(DEVICE_HTML)
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
            elif path == "/api/update":
                force = (parse_qs(parsed.query).get("force") or [""])[0] == "1"
                try:
                    result = updates.check(force=force)
                except UpdateCheckError as exc:
                    self._json_error(502, str(exc))
                    return
                body = json.dumps(
                    result.to_dict(),
                    ensure_ascii=False,
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif path in {"/api/wifi/status", "/api/wifi/scan"}:
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
                if wifi_workbench is None:
                    self._json_error(
                        409,
                        "Wi-Fi operations are unavailable for this connection",
                    )
                    return
                try:
                    payload = (
                        wifi_workbench.status(host)
                        if path.endswith("/status")
                        else wifi_workbench.scan(host)
                    )
                except (WifiError, OSError, TimeoutError, ValueError) as exc:
                    self._json_error(502, str(exc))
                    return
                body = json.dumps(
                    payload, ensure_ascii=False
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif path == "/api/push-scan":
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
                if push_scan_reader is None:
                    self._json_error(
                        409,
                        "Push Scan inspection is unavailable for this connection",
                    )
                    return
                try:
                    payload = push_scan_reader(host)
                except Exception as exc:
                    self._json_error(
                        502,
                        f"{type(exc).__name__}: {exc}",
                    )
                    return
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            elif path in {
                "/api/config",
                "/api/config/categories",
                "/api/config/baseline",
                "/api/config/compare",
            }:
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
                    if path == "/api/config/categories":
                        categories = config_workbench.category_catalog()
                        payload = {
                            "host": host,
                            "categories": categories,
                            "total": sum(
                                int(category["item_count"])
                                for category in categories
                            ),
                        }
                    elif path == "/api/config":
                        category = (
                            parse_qs(parsed.query).get("category")
                            or ["general"]
                        )[0]
                        payload = config_workbench.overview(
                            host,
                            category=category,
                        )
                    elif path == "/api/config/baseline":
                        payload = {
                            "host": host,
                            "baseline": config_workbench.baseline_info(host),
                        }
                    else:
                        payload = config_workbench.compare_baseline(host)
                except ConfigCategoryError as exc:
                    self._json_error(400, str(exc))
                    return
                except ConfigWorkbenchError as exc:
                    self._json_error(502, str(exc))
                    return
                except ConfigSnapshotError as exc:
                    self._json_error(409, str(exc))
                    return
                except Exception as exc:
                    self._json_error(
                        502,
                        f"{type(exc).__name__}: {exc}",
                    )
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
                "/api/language",
                "/api/scans",
                "/api/settings",
                "/api/config/baseline",
                "/api/config/apply",
                "/api/wifi/connect",
            }:
                self._respond(404, "text/plain; charset=utf-8", b"not found\n")
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = 0
            maximum = (
                64 * 1024
                if parsed.path in {"/api/settings", "/api/wifi/connect"}
                else 4096
            )
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
            if parsed.path == "/api/language":
                try:
                    saved = settings.update_language(payload.get("language"))
                except SettingsError as exc:
                    self._json_error(400, str(exc))
                    return
                preference = saved["language"]
                effective = resolve_language(
                    preference,
                    self.headers.get("Accept-Language"),
                )
                body = json.dumps(
                    {
                        "language": preference,
                        "effective": effective,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
                return
            if parsed.path == "/api/settings":
                try:
                    if "saved_printers" not in payload:
                        current = settings.load()
                        payload["saved_printers"] = current["saved_printers"]
                    if "language" not in payload:
                        current = settings.load()
                        payload["language"] = current["language"]
                    saved = settings.save(payload)
                except SettingsError as exc:
                    self._json_error(400, str(exc))
                    return
                body = json.dumps(
                    saved, ensure_ascii=False
                ).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
                return
            if parsed.path == "/api/config/baseline":
                self._config_baseline_operation(payload, config_workbench)
                return
            if parsed.path == "/api/config/apply":
                self._config_apply_operation(payload, config_workbench)
                return
            if parsed.path == "/api/wifi/connect":
                self._wifi_connect_operation(payload, wifi_workbench)
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

        def _wifi_connect_operation(
            self,
            payload: dict[str, object],
            workbench: WifiWorkbench | None,
        ) -> None:
            if workbench is None:
                self._json_error(
                    409,
                    "Wi-Fi operations are unavailable for this connection",
                )
                return
            client = getattr(self, "client_address", ("127.0.0.1", 0))[0]
            if client not in {"127.0.0.1", "::1"}:
                self._json_error(
                    403,
                    "Wi-Fi credential changes are limited to loopback clients",
                )
                return
            if payload.get("confirm") is not True:
                self._json_error(400, "Wi-Fi change requires confirm=true")
                return
            requested = payload.get("host")
            if requested is not None and not isinstance(requested, str):
                self._json_error(400, "host must be a string or null")
                return
            ssid = payload.get("ssid")
            security = payload.get("security")
            password = payload.get("password")
            bssid = payload.get("bssid", "")
            wep_index = payload.get("wep_index", 0)
            if not isinstance(ssid, str) or not ssid:
                self._json_error(400, "ssid must be a non-empty string")
                return
            if isinstance(security, bool) or not isinstance(security, int):
                self._json_error(400, "security must be an integer")
                return
            if security not in SECURITY_MODES:
                self._json_error(400, "unsupported Wi-Fi security mode")
                return
            if password is not None and not isinstance(password, str):
                self._json_error(400, "password must be a string or null")
                return
            if not isinstance(bssid, str):
                self._json_error(400, "bssid must be a string")
                return
            if isinstance(wep_index, bool) or not isinstance(wep_index, int):
                self._json_error(400, "wep_index must be an integer")
                return
            if wep_index < 0:
                self._json_error(400, "wep_index must be non-negative")
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
                result = workbench.connect(
                    host,
                    ssid=ssid,
                    security=security,
                    password=password,
                    bssid=bssid,
                    wep_index=wep_index,
                )
            except (WifiError, OSError, TimeoutError, ValueError) as exc:
                self._json_error(502, str(exc))
                return
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._respond(200, "application/json; charset=utf-8", body)

        def _config_baseline_operation(
            self,
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
                result = workbench.save_baseline(host)
            except ConfigWorkbenchError as exc:
                self._json_error(409, str(exc))
                return
            except ConfigSnapshotError as exc:
                self._json_error(400, str(exc))
                return
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._respond(200, "application/json; charset=utf-8", body)

        def _config_apply_operation(
            self,
            payload: dict[str, object],
            workbench: ConfigWorkbench | None,
        ) -> None:
            if workbench is None:
                self._json_error(
                    409,
                    "configuration is unavailable for this connection",
                )
                return
            if payload.get("confirm") is not True:
                self._json_error(400, "configuration write requires confirm=true")
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
                result = workbench.apply_integer(
                    host,
                    payload.get("item_id"),
                    payload.get("value"),
                    payload.get("expected_value"),
                )
            except ConfigWorkbenchError as exc:
                self._json_error(409, str(exc))
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
    push_scan_reader: Callable[[str], dict] | None = None,
    wifi_workbench: WifiWorkbench | None = None,
    update_checker: UpdateChecker | None = None,
) -> None:
    server = create_server(
        registry,
        bind=bind,
        port=port,
        discover_fn=discover_fn,
        scan_manager=scan_manager,
        settings_store=settings_store,
        config_workbench=config_workbench,
        push_scan_reader=push_scan_reader,
        wifi_workbench=wifi_workbench,
        update_checker=update_checker,
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
    push_scan_reader: Callable[[str], dict] | None = None,
    wifi_workbench: WifiWorkbench | None = None,
    update_checker: UpdateChecker | None = None,
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
            push_scan_reader=push_scan_reader,
            wifi_workbench=wifi_workbench,
            update_checker=update_checker,
        ),
    )
