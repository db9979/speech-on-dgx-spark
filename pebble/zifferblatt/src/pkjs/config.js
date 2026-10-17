// Settings page of the Spark-Zifferblatt, opened as a data: URL; saving returns the values through
// pebblejs://close#<json> (or the return_to URL the app passes).
function esc(v) {
  return String(v === undefined || v === null ? '' : v)
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

module.exports = function (s) {
  var html = '<!doctype html><html><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Spark-Zifferblatt</title><style>' +
    'body{font-family:-apple-system,Roboto,sans-serif;margin:0;padding:16px;background:#14161c;color:#e8eaf0}' +
    'h1{font-size:22px;margin:0 0 4px}p{color:#9aa0ad;font-size:14px;margin:0 0 16px}' +
    'label{display:block;margin:14px 0 6px;font-weight:600}' +
    'input{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;' +
    'border:1px solid #3a3f4b;background:#1e2129;color:#e8eaf0;font-size:16px}small{color:#9aa0ad;display:block;margin-top:4px}' +
    'button{margin-top:24px;width:100%;padding:14px;border:0;border-radius:10px;background:#3d6df2;' +
    'color:#fff;font-size:17px;font-weight:600}</style></head><body>' +
    '<h1>Spark-Zifferblatt</h1><p>Uhrzeit, nächster Termin, Erinnerung und Wetter vom Spark.</p>' +
    '<label for="setup">Einrichtungscode</label>' +
    '<input id="setup" type="text" autocapitalize="off" autocorrect="off" placeholder="http://…#pebble=…">' +
    '<small>Im Panel unter Ich → Pebble-Uhr einen neuen Code holen (einen eigenen, nicht den der Uhr-App) und hier einfügen.</small>' +
    '<label for="server">Spark-Adresse</label>' +
    '<input id="server" type="url" autocapitalize="off" autocorrect="off" value="' + esc(s.server) + '">' +
    '<label for="out">Adresse unterwegs</label>' +
    '<input id="out" type="url" autocapitalize="off" autocorrect="off" placeholder="https://…" value="' + esc(s.server_out) + '">' +
    '<small>Nur https. Leer: nur zu Hause.</small>' +
    '<label for="key">Geräteschlüssel</label>' +
    '<input id="key" type="text" autocapitalize="off" autocorrect="off" value="' + esc(s.device_key) + '">' +
    '<button id="save">Speichern</button>' +
    '<script>' +
    'var g=function(i){return document.getElementById(i)};' +
    'g("save").onclick=function(){var r={setup:g("setup").value.trim(),server:g("server").value.trim(),' +
    'server_out:g("out").value.trim(),device_key:g("key").value.trim()};' +
    'var m=/[?&]return_to=([^&]*)/.exec(location.search);' +
    'location.href=(m?decodeURIComponent(m[1]):"pebblejs://close#")+encodeURIComponent(JSON.stringify(r))};' +
    '</script></body></html>';
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
};
