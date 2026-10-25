import type { Ui } from "./variant";

/**
 * The portal's stylesheet, emitted with class names passed through ui.cls(), so under M2
 * (class churn) the CSS follows the churned names and the page still looks the same.
 * The look is intentionally "enterprise legacy": dense, bordered, Tahoma, blue header bar.
 */
export function stylesheet(ui: Ui): string {
  const c = (name: string) => `.${ui.cls(name)}`;
  return `
*{box-sizing:border-box}
body{margin:0;background:#e9edf2;color:#1d2733;font:13px/1.45 Tahoma,Verdana,Segoe UI,sans-serif}
a{color:#1a5296}
h1{font-size:18px;margin:0 0 12px}
h2{font-size:15px;margin:0 0 10px}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{border:1px solid #c5ced8;padding:5px 8px;text-align:left;vertical-align:middle}
th{background:#dfe6ee;font-weight:bold}
tr:nth-child(even) td{background:#f6f8fa}
${c("header")}{background:linear-gradient(#2b5f94,#1f4e79);color:#fff;display:flex;align-items:center;gap:24px;padding:0 16px;height:44px;border-bottom:3px solid #f2a900}
${c("brand")}{font-weight:bold;font-size:15px;letter-spacing:.3px;color:#fff;text-decoration:none}
${c("brand")} small{font-weight:normal;opacity:.75;margin-left:6px}
${c("nav")}{display:flex;gap:2px;flex:1}
${c("nav-link")}{color:#dce8f5;text-decoration:none;padding:12px 12px;display:block}
${c("nav-link")}:hover,${c("nav-link")}${c("active")}{background:#173d61;color:#fff}
${c("userbox")}{display:flex;align-items:center;gap:10px;color:#dce8f5}
${c("container")}{max-width:1080px;margin:16px auto;padding:0 16px}
${c("card")}{background:#fff;border:1px solid #b9c4d0;border-radius:2px;padding:14px;margin-bottom:14px}
${c("card-title")}{font-weight:bold;border-bottom:1px solid #d5dce4;margin:-14px -14px 12px;padding:8px 14px;background:#f1f4f7}
${c("btn")}{display:inline-block;font:inherit;padding:4px 12px;border:1px solid #8a99a8;border-radius:2px;background:linear-gradient(#fff,#e3e8ee);color:#1d2733;cursor:pointer;text-decoration:none}
${c("btn")}:hover{border-color:#5b6b7b}
${c("btn-primary")}{background:linear-gradient(#3d7cc0,#245d99);border-color:#1d4d80;color:#fff}
${c("btn-danger")}{background:linear-gradient(#d9534f,#b52b27);border-color:#9c2622;color:#fff}
${c("btn-sm")}{padding:2px 8px;font-size:12px}
${c("toolbar")}{display:flex;gap:6px;align-items:center;margin-bottom:10px}
${c("toolbar")} form{margin:0}
${c("spacer")}{flex:1}
${c("form-grid")}{display:grid;grid-template-columns:160px 320px;gap:10px 12px;align-items:center}
${c("form-label")}{font-weight:bold;text-align:right}
${c("form-control")}{font:inherit;padding:4px 6px;border:1px solid #8a99a8;border-radius:2px;width:100%;background:#fff}
${c("form-control")}:focus{outline:2px solid #f2a900;outline-offset:0}
${c("help")}{grid-column:2;color:#5b6b7b;font-size:11px;margin-top:-6px}
${c("form-actions")}{grid-column:2;display:flex;gap:6px}
${c("alert")}{padding:8px 12px;border:1px solid;border-radius:2px;margin-bottom:12px}
${c("alert-success")}{background:#e6f4e6;border-color:#8cc28c;color:#1e5b1e}
${c("alert-danger")}{background:#fbe9e9;border-color:#e0a2a0;color:#8a1f1c}
${c("alert-warning")}{background:#fff6dc;border-color:#e6cb7a;color:#6b5100}
${c("badge")}{display:inline-block;padding:1px 6px;border-radius:2px;font-size:11px;border:1px solid}
${c("badge-pending")}{background:#fff6dc;border-color:#e6cb7a}
${c("badge-approved")}{background:#e6f0fb;border-color:#9dbbe0}
${c("badge-paid")}{background:#e6f4e6;border-color:#8cc28c}
${c("badge-rejected")}{background:#fbe9e9;border-color:#e0a2a0}
${c("pagination")}{display:flex;gap:4px;margin-top:10px;align-items:center}
${c("tiles")}{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
${c("tile")}{background:#fff;border:1px solid #b9c4d0;padding:12px}
${c("tile-value")}{font-size:22px;font-weight:bold;color:#1f4e79}
${c("layout-2col")}{display:grid;grid-template-columns:1fr 240px;gap:14px;align-items:start}
${c("dropdown")}{position:relative;width:100%}
${c("dropdown-toggle")}{width:100%;text-align:left;display:flex;justify-content:space-between}
${c("dropdown-menu")}{position:absolute;z-index:10;top:100%;left:0;right:0;max-height:220px;overflow:auto;margin:2px 0 0;padding:2px 0;list-style:none;background:#fff;border:1px solid #8a99a8;box-shadow:0 3px 8px rgba(0,0,0,.18)}
${c("dropdown-item")}{padding:4px 10px;cursor:pointer;white-space:nowrap}
${c("dropdown-item")}[aria-selected=true],${c("dropdown-item")}:hover{background:#245d99;color:#fff}
${c("modal-backdrop")}{position:fixed;inset:0;background:rgba(20,30,45,.45);display:flex;align-items:flex-start;justify-content:center;padding-top:90px;z-index:20}
${c("modal")}{background:#fff;border:1px solid #5b6b7b;width:440px;box-shadow:0 8px 24px rgba(0,0,0,.3)}
${c("modal-title")}{background:#1f4e79;color:#fff;padding:8px 12px;font-weight:bold}
${c("modal-body")}{padding:14px}
${c("banner")}{background:#fff3cd;border:1px solid #e6cb7a;padding:8px 12px;margin-bottom:12px}
${c("footer")}{max-width:1080px;margin:24px auto;padding:0 16px;color:#6b7a89;font-size:11px;display:flex;justify-content:space-between}
${c("login-box")}{width:380px;margin:80px auto}
${c("invoice-number")}{font-family:Consolas,monospace;font-weight:bold}
${c("muted")}{color:#6b7a89}
`;
}
