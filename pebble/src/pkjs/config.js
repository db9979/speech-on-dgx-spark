// Settings page, opened by the Pebble app as a data: URL. Saving returns the values
// through pebblejs://close#<json> (or the return_to URL the app passes).
function esc(v) {
  return String(v === undefined || v === null ? '' : v)
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

module.exports = function (s) {
  var html = '<!doctype html><html><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Spark</title><style>' +
    'body{font-family:-apple-system,Roboto,sans-serif;margin:0;padding:16px;background:#14161c;color:#e8eaf0}' +
    'h1{font-size:22px;margin:0 0 4px}p{color:#9aa0ad;font-size:14px;margin:0 0 16px}' +
    'label{display:block;margin:14px 0 6px;font-weight:600}' +
    'input[type=text],input[type=url]{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;' +
    'border:1px solid #3a3f4b;background:#1e2129;color:#e8eaf0;font-size:16px}' +
    '.row{display:flex;align-items:center;justify-content:space-between;margin:14px 0}' +
    '.row label{margin:0}input[type=checkbox]{width:22px;height:22px}' +
    'input[type=range]{width:100%}small{color:#9aa0ad;display:block;margin-top:4px}' +
    'button{margin-top:24px;width:100%;padding:14px;border:0;border-radius:10px;background:#3d6df2;' +
    'color:#fff;font-size:17px;font-weight:600}</style></head><body>' +
    '<h1>Spark</h1><p>Sprach-Assistent auf dem DGX Spark.</p>' +
    '<label for="server">Spark-Adresse</label>' +
    '<input id="server" type="url" autocapitalize="off" autocorrect="off" value="' + esc(s.server || 'http://tars:31080') + '">' +
    '<small>Zu Hause z.&nbsp;B. http://tars:31080 oder http://192.168.x.y:31080, unterwegs die Adresse im VPN (Tailscale).</small>' +
    '<label for="key">Geräteschlüssel</label>' +
    '<input id="key" type="text" autocapitalize="off" autocorrect="off" value="' + esc(s.device_key) + '">' +
    '<small>Im Panel unter Profile beim Profil ein Gerät hinzufügen. Ohne Schlüssel fragst du als Gast.</small>' +
    '<div class="row"><label for="speak">Antwort vorlesen</label><input id="speak" type="checkbox"' + (s.SPEAK === false ? '' : ' checked') + '></div>' +
    '<label for="vol">Lautstärke <span id="vv">' + (s.VOLUME || 100) + '</span>%</label>' +
    '<input id="vol" type="range" min="10" max="100" step="10" value="' + (s.VOLUME || 100) + '">' +
    '<div class="row"><label for="auto">Beim Öffnen sofort zuhören</label><input id="auto" type="checkbox"' + (s.AUTOLISTEN === false ? '' : ' checked') + '></div>' +
    '<button id="save">Speichern</button>' +
    '<script>' +
    'var g=function(i){return document.getElementById(i)};' +
    'g("vol").oninput=function(){g("vv").textContent=this.value};' +
    'g("save").onclick=function(){var r={server:g("server").value.trim(),device_key:g("key").value.trim(),' +
    'SPEAK:g("speak").checked,VOLUME:parseInt(g("vol").value,10),AUTOLISTEN:g("auto").checked};' +
    'var m=/[?&]return_to=([^&]*)/.exec(location.search);' +
    'location.href=(m?decodeURIComponent(m[1]):"pebblejs://close#")+encodeURIComponent(JSON.stringify(r))};' +
    '</script></body></html>';
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
};
