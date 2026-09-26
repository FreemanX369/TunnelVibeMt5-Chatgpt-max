"""Inline MCP Apps viewer for the PNG returned by capture_live_chart.

The widget reads the existing MCP ImageContent. It does not take a second capture,
persist a VPS copy, or claim to create a native ChatGPT file attachment.
"""

LIVE_CHART_WIDGET_URI = "ui://vibemql5/live-chart-r1.html"
LIVE_CHART_WIDGET_SCHEMA_VERSION = "1.0"

LIVE_CHART_WIDGET_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>VibeMQL5 chart capture</title>
<style>
:root{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark}
*{box-sizing:border-box}body{margin:0;padding:12px;background:transparent}
.card{max-width:960px;margin:auto;border:1px solid rgba(127,127,127,.28);border-radius:14px;overflow:hidden;background:rgba(127,127,127,.05)}
.header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px}
h1{font-size:14px;margin:0}.detail{font-size:12px;opacity:.75;margin-top:3px}
a{font-size:12px;font-weight:650;border:1px solid rgba(127,127,127,.35);border-radius:8px;padding:7px 10px;color:inherit;text-decoration:none;white-space:nowrap}
a[hidden],img[hidden]{display:none}.status{padding:12px;font-size:12px;white-space:pre-wrap}
img{width:100%;height:auto;display:block;background:#111}
</style>
</head>
<body>
<div class="card">
  <div class="header"><div><h1 id="title">MT5-2 chart</h1><div id="detail" class="detail"></div></div><a id="download" hidden>Download PNG</a></div>
  <div id="status" class="status">Waiting for chart image…</div>
  <img id="chart" alt="Captured MT5-2 chart" hidden />
</div>
<script>
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function show(result) {
    if (!result || result.isError || result.is_error) return;
    const content = result.content;
    if (!Array.isArray(content)) return;
    const png = content.find((item) => item && item.type === "image" &&
      (item.mimeType || item.mime_type) === "image/png" &&
      typeof item.data === "string" && /^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(item.data));
    if (!png) return;
    const meta = result.structuredContent || result.structured_content || {};
    const chart = meta.chart || {};
    const safe = (value) => String(value == null ? "" : value).replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 64);
    const chartId = safe(chart.chart_id || "chart");
    const symbol = safe(chart.symbol || "MT5-2");
    const period = safe(chart.timeframe || chart.period || "chart");
    const name = `MT5-2_${symbol}_${period}_${chartId}.png`;
    const src = `data:image/png;base64,${png.data}`;
    $("title").textContent = `${chart.symbol || "MT5-2"} · ${chart.timeframe || chart.period || "chart"}`;
    $("detail").textContent = `${meta.image_width || "?"}×${meta.image_height || "?"} · ${meta.aspect_ratio || "PNG"} · chart ${chartId}`;
    $("chart").src = src;
    $("chart").hidden = false;
    $("download").href = src;
    $("download").download = name;
    $("download").hidden = false;
    $("status").hidden = true;
  }
  function hostResult() {
    const host = window.openai;
    const metadata = host && host.toolResponseMetadata;
    return metadata && (metadata.mcp_tool_result || metadata.call_tool_result || metadata);
  }
  show(hostResult());
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.jsonrpc !== "2.0" || message.method !== "ui/notifications/tool-result") return;
    show(message.params);
  }, {passive:true});
})();
</script>
</body>
</html>'''
