from __future__ import annotations

EX5_INGRESS_WIDGET_URI = "ui://vibemql5/ex5-ingress-r1.html"
EX5_INGRESS_WIDGET_SCHEMA_VERSION = "1.0"

# Self-contained widget: no external JS/CSS dependencies, no arbitrary fetch, and no
# persistence/logging of temporary download URLs. Server-side validation remains authority.
EX5_INGRESS_WIDGET_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>VibeMQL5 EX5 Ingress</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark}
*{box-sizing:border-box}body{margin:0;padding:14px;background:transparent}.card{max-width:760px;margin:0 auto;border:1px solid rgba(127,127,127,.28);border-radius:16px;padding:16px;background:rgba(127,127,127,.06)}
h1{font-size:18px;margin:0 0 6px}.sub{font-size:12px;opacity:.72;margin-bottom:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.full{grid-column:1/-1}label{font-size:12px;display:block;margin-bottom:4px;opacity:.8}input{width:100%;padding:9px 10px;border-radius:9px;border:1px solid rgba(127,127,127,.32);background:transparent}button{padding:9px 12px;border-radius:9px;border:1px solid rgba(127,127,127,.32);font-weight:650;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.status{margin-top:12px;padding:10px;border-radius:9px;background:rgba(127,127,127,.09);font-size:12px;white-space:pre-wrap;word-break:break-word}.ok{font-weight:700}.err{font-weight:700}.file{font-size:12px;margin-top:8px;opacity:.85}@media(max-width:620px){.grid{grid-template-columns:1fr}.full{grid-column:1}}
</style>
</head>
<body>
<div class="card">
  <h1>Import EX5 to VibeMQL5</h1>
  <div class="sub">Controlled EX5 ingress · max 16 MiB · SHA-256 verified on VPS · no base64</div>
  <div class="grid">
    <div><label>Workspace</label><input id="workspace" value="BD" autocomplete="off" /></div>
    <div><label>Destination</label><input id="destination" value="Experts/WSLOW public v1.12.ex5" autocomplete="off" /></div>
    <div class="full"><label>Expected SHA-256 (recommended)</label><input id="sha" value="" maxlength="64" autocomplete="off" spellcheck="false" /></div>
    <div class="full"><label>Local EX5 file</label><input id="file" type="file" accept=".ex5,application/octet-stream" /></div>
  </div>
  <div id="chosen" class="file">No file selected.</div>
  <div class="actions">
    <button id="upload">Upload & import</button>
    <button id="library" type="button">Choose from ChatGPT library</button>
  </div>
  <div id="status" class="status">Ready.</div>
</div>
<script>
(() => {
  "use strict";
  const MAX_BYTES = 16777216;
  const $ = (id) => document.getElementById(id);
  let selectedLibraryFile = null;

  function fail(message){ $("status").className="status err"; $("status").textContent=message; }
  function info(message){ $("status").className="status"; $("status").textContent=message; }
  function ok(message){ $("status").className="status ok"; $("status").textContent=message; }
  function api(){ return window.openai || null; }
  function fileNameOf(file){ return String((file && (file.fileName || file.name)) || ""); }
  function fileIdOf(file){ return String((file && file.fileId) || ""); }
  function mimeOf(file){ return String((file && (file.mimeType || file.type)) || "application/octet-stream"); }
  function safeShape(value){
    if(value===null) return "null";
    if(Array.isArray(value)) return `array(len=${value.length})`;
    const t=typeof value;
    if(t!=="object") return t;
    let keys=[];
    try{ keys=Object.keys(value).slice(0,16); }catch(_e){}
    return `object keys=[${keys.join(",")}]`;
  }
  function validateName(name){ if(!name.toLowerCase().endsWith(".ex5")) throw new Error("Only .ex5 files are allowed."); }
  function validateLocal(file){ validateName(file.name); if(file.size<=0) throw new Error("EX5 file is empty."); if(file.size>MAX_BYTES) throw new Error("EX5 exceeds 16 MiB."); }
  function defaultsFromTool(){
    const src=(api() && (api().toolOutput || api().toolInput)) || {};
    if(src.workspace) $("workspace").value=String(src.workspace);
    if(src.destination_path) $("destination").value=String(src.destination_path);
    if(src.expected_sha256) $("sha").value=String(src.expected_sha256);
  }
  async function importAuthorized(fileId, fileName, mimeType){
    validateName(fileName);
    const host=api();
    if(!host || !host.getFileDownloadUrl || !host.callTool) throw new Error("ChatGPT file/tool APIs are unavailable in this host.");
    info("Resolving authorized temporary file URL…");
    const urlResult=await host.getFileDownloadUrl({fileId});
    const downloadUrl=String((urlResult && urlResult.downloadUrl) || "");
    if(!downloadUrl) throw new Error("ChatGPT did not return an authorized download URL.");
    info("Importing and verifying bytes on VibeMQL5…");
    const result=await host.callTool("import_ex5_authorized_file", {
      workspace: $("workspace").value.trim(),
      file_id: fileId,
      download_url: downloadUrl,
      file_name: fileName,
      mime_type: mimeType || "application/octet-stream",
      destination_path: $("destination").value.trim(),
      expected_sha256: $("sha").value.trim().toLowerCase(),
      overwrite: false
    });
    const data=(result && (result.structuredContent || result.structured_content)) || result || {};
    const ref=String(data.ea_binary_ref || data.immutable_binary_ref || "");
    if(!ref) throw new Error("Import finished without an immutable BIN reference.");
    ok(`IMPORT ${data.status || "OK"}\n${data.file_name || fileName}\n${data.bytes || "?"} bytes\nSHA256 ${data.sha256 || "?"}\n${ref}\n${data.import_id || ""}`);
    if(host.setWidgetState){
      await host.setWidgetState({modelContent:`VibeMQL5 imported ${fileName}`,privateContent:{ea_binary_ref:ref,import_id:data.import_id,sha256:data.sha256,bytes:data.bytes,workspace:data.workspace,path:data.path}});
    }
    if(host.sendFollowUpMessage){
      await host.sendFollowUpMessage({prompt:`VibeMQL5 EX5 import succeeded. Continue the requested TIP-026R2 qualification using ea_binary_ref=${ref} and import_id=${data.import_id || ""}. Do not recompile the EX5. Preserve coverage classifier output exactly.`});
    }
    return data;
  }
  async function uploadLocal(){
    try{
      const host=api();
      if(!host || !host.uploadFile) throw new Error("ChatGPT uploadFile API is unavailable.");
      const file=$("file").files && $("file").files[0];
      if(!file) throw new Error("Select an EX5 file first.");
      validateLocal(file);
      info("Uploading file to ChatGPT…");
      const uploaded=await host.uploadFile(file);
      const fileId=fileIdOf(uploaded);
      if(!fileId) throw new Error(`ChatGPT upload returned no fileId (${safeShape(uploaded)}).`);
      await importAuthorized(fileId,file.name,file.type || "application/octet-stream");
    }catch(e){ fail(String((e && e.message) || e)); }
  }
  async function chooseLibrary(){
    try{
      const host=api();
      if(!host || !host.selectFiles) throw new Error("ChatGPT file library picker is unavailable in this host.");
      const files=await host.selectFiles();
      if(!Array.isArray(files) || !files.length) return;
      const picked=files[0];
      const name=fileNameOf(picked); validateName(name);
      selectedLibraryFile=picked;
      $("chosen").textContent=`Library: ${name}`;
      await importAuthorized(fileIdOf(picked),name,mimeOf(picked));
    }catch(e){ fail(String((e && e.message) || e)); }
  }
  $("file").addEventListener("change",()=>{ selectedLibraryFile=null; const f=$("file").files && $("file").files[0]; $("chosen").textContent=f?`${f.name} · ${f.size} bytes`:"No file selected."; });
  $("upload").addEventListener("click",uploadLocal);
  $("library").addEventListener("click",chooseLibrary);
  if(!api() || !api().selectFiles) $("library").disabled=true;
  defaultsFromTool();
})();
</script>
</body>
</html>'''
