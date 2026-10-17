// Phone side of the Spark-Zifferblatt: when the face asks (REFRESH, every 15 minutes and at the start) it fetches
// GET /api/watch/blick with the watch key and sends the parts. Pairing and the two addresses work like in the
// watch app "Spark" (a setup code of its own from Ich → Pebble-Uhr).
var configPage = require('./config');
var keys = require('message_keys');

var PROBE_MS = 4000;   // a try at an address that may not answer (at home vs. on the road)
var TEXT_MAX = 60;

function settings() {
  var s = {};
  try { s = JSON.parse(localStorage.getItem('settings') || '{}'); } catch (e) { s = {}; }
  return {
    server: String(s.server || '').replace(/\/+$/, ''),
    out: /^https:\/\/[A-Za-z0-9.\-]+(:\d{1,5})?\/?$/.test(String(s.server_out || '')) ? String(s.server_out).replace(/\/+$/, '') : '',
    key: String(s.device_key || '').trim()
  };
}

function send(m) {
  Pebble.sendAppMessage(m, function () {}, function () {
    setTimeout(function () { Pebble.sendAppMessage(m, function () {}, function () {}); }, 1000);
  });
}

function status(text) {
  var m = {};
  m[keys.STATUS] = text;
  send(m);
}

function tryOnce(server, path, timeout, cb) {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', server + path, true);
  xhr.timeout = timeout;
  xhr.setRequestHeader('X-Speech-Device', settings().key);
  xhr.onload = function () {
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
    cb(xhr.status >= 200 && xhr.status < 300 && data ? null : xhr.status || 'error', data, xhr.status);
  };
  xhr.onerror = function () { cb('down', null, 0); };
  xhr.ontimeout = function () { cb('slow', null, 0); };
  xhr.send(null);
}

// home first, then the address for on the road (https only), like the watch app
function fetch(path, cb) {
  var s = settings();
  var list = [{name: 'home', url: s.server}];
  if (s.out) list.push({name: 'out', url: s.out});
  var at = 0;
  function one() {
    tryOnce(list[at].url, path, list.length > 1 && at === 0 ? PROBE_MS : 20000, function (err, data, st) {
      if (err && st === 0 && at + 1 < list.length) {
        at++;
        return one();
      }
      cb(err, data, st, list[at].name);
    });
  }
  one();
}

function short(v) {
  return String(v || '').replace(/[\x00-\x1f]/g, ' ').substr(0, TEXT_MAX);
}

function zone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; }
}

function refresh() {
  var s = settings();
  if (!s.server || !s.key) return status('Einstellungen öffnen');
  fetch('/api/watch/blick?tz=' + encodeURIComponent(zone()), function (err, d, st, where) {
    if (err) return status(st === 403 ? 'Im Panel ausgeschaltet' : st === 401 ? 'Neu koppeln' : 'Spark nicht erreicht');
    var m = {};
    m[keys.NEXT_T] = d.next && !d.next.allday ? d.next.start | 0 : 0;
    m[keys.NEXT] = d.next ? (d.next.allday ? 'Heute: ' : '') + short(d.next.title) : '';
    m[keys.REM_T] = d.rem ? d.rem.due | 0 : 0;
    m[keys.REM] = d.rem ? short(d.rem.text) : '';
    m[keys.WX] = d.wx ? (d.wx.temp | 0) + '° ' + short(d.wx.word) : '';
    m[keys.ALERT] = short(d.alert);
    m[keys.TIP] = short(d.tip);
    m[keys.WHERE] = where === 'out' && s.out ? 1 : 0;
    send(m);
  });
}

function pair(line, done) {
  var m = /^\s*(https?:\/\/[A-Za-z0-9.\-]+(?::\d{1,5})?)\/?#pebble=([A-Za-z0-9_\-]{20,40})(?:&aussen=(https:\/\/[A-Za-z0-9.\-]+(?::\d{1,5})?)\/?)?\s*$/.exec(line || '');
  if (!m) return done('Der Einrichtungscode passt nicht.');
  var xhr = new XMLHttpRequest();
  xhr.open('POST', m[1] + '/api/pebble/pair', true);
  xhr.timeout = 15000;
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = function () {
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
    if (xhr.status === 200 && data && data.token) return done(null, m[1], data.token, m[3] || '');
    done('Spark: ' + xhr.status);
  };
  xhr.onerror = function () { done('Spark nicht erreichbar'); };
  xhr.ontimeout = function () { done('Spark antwortet nicht'); };
  xhr.send(JSON.stringify({code: m[2]}));
}

Pebble.addEventListener('ready', refresh);

Pebble.addEventListener('appmessage', function (e) {
  if (e.payload && (e.payload.REFRESH !== undefined || e.payload[keys.REFRESH] !== undefined)) refresh();
});

Pebble.addEventListener('showConfiguration', function () {
  var s = {};
  try { s = JSON.parse(localStorage.getItem('settings') || '{}'); } catch (e) { s = {}; }
  Pebble.openURL(configPage(s));
});

Pebble.addEventListener('webviewclosed', function (e) {
  if (!e || !e.response) return;
  var s;
  try { s = JSON.parse(decodeURIComponent(e.response)); } catch (err) { return; }
  var setup = String(s.setup || '').trim();
  delete s.setup;
  if (!setup) {
    localStorage.setItem('settings', JSON.stringify(s));
    return refresh();
  }
  pair(setup, function (err, server, token, outside) {
    if (err) return status('Kopplung fehlgeschlagen');
    s.server = server;
    s.server_out = outside || s.server_out || '';
    s.device_key = token;
    localStorage.setItem('settings', JSON.stringify(s));
    refresh();
  });
});
