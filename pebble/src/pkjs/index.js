// Phone side of the Spark watch app: takes the dictated question from the watch, asks the
// Spark (/api/watch/ask), polls text and audio (/api/watch/poll) and passes both on.
var configPage = require('./config');
var keys = require('message_keys');

var CHUNK = 1500;      // audio bytes per AppMessage
var TEXT_CHUNK = 400;  // answer characters per AppMessage
var MAX_TURNS = 6;     // earlier question/answer pairs sent along as context

var history = [];
var job = null;        // the running answer
var queue = [];        // messages for the watch, sent one at a time
var sending = false;

function settings() {
  var s = {};
  try { s = JSON.parse(localStorage.getItem('settings') || '{}'); } catch (e) { s = {}; }
  return {
    server: String(s.server || 'http://tars:31080').replace(/\/+$/, ''),
    key: String(s.device_key || '').trim(),
    speak: s.SPEAK !== false
  };
}

// ------------------------------------------------------------ sending to the watch

function send(msg, onDone) {
  queue.push({msg: msg, done: onDone, tries: 0});
  pump();
}

function pump() {
  if (sending || !queue.length) return;
  var item = queue[0];
  sending = true;
  Pebble.sendAppMessage(item.msg, function () {
    queue.shift();
    sending = false;
    if (item.done) item.done();
    pump();
  }, function () {
    sending = false;
    if (++item.tries > 5) {
      queue.shift();  // the watch app is gone
    }
    setTimeout(pump, 200);
  });
}

function sendText(text) {
  for (var i = 0; i < text.length; i += TEXT_CHUNK) {
    var m = {};
    m[keys.ANSWER] = text.substr(i, TEXT_CHUNK);
    send(m);
  }
}

// ------------------------------------------------------------ talking to the Spark

function request(method, path, body, cb) {
  var s = settings();
  var xhr = new XMLHttpRequest();
  xhr.open(method, s.server + path, true);
  xhr.timeout = 30000;
  xhr.setRequestHeader('Content-Type', 'application/json');
  if (s.key) xhr.setRequestHeader('X-Speech-Device', s.key);
  xhr.onload = function () {
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
    if (xhr.status >= 200 && xhr.status < 300 && data) {
      cb(null, data);
    } else {
      var detail = data && data.detail ? data.detail : xhr.status;
      cb(xhr.status === 401 ? 'Spark verlangt eine Anmeldung (Geräteschlüssel prüfen).' : 'Spark: ' + detail);
    }
  };
  xhr.onerror = function () { cb('Spark nicht erreichbar: ' + s.server); };
  xhr.ontimeout = function () { cb('Spark antwortet nicht.'); };
  xhr.send(body ? JSON.stringify(body) : null);
}

var B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function b64bytes(s) {
  var out = [], buf = 0, bits = 0;
  for (var i = 0; i < s.length; i++) {
    var v = B64.indexOf(s.charAt(i));
    if (v < 0) continue;
    buf = (buf << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push((buf >> bits) & 255);
    }
  }
  return out;
}

function cancel() {
  if (!job) return;
  job.cancelled = true;
  if (job.id) request('DELETE', '/api/watch/' + job.id, null, function () {});
  job = null;
  queue = queue.filter(function (q) { return q.msg[keys.AUDIO] === undefined; });
}

function ask(question, credit) {
  cancel();
  var s = settings();
  var j = {id: null, t: 0, a: 0, text: '', audio: [], credit: credit || 0, inFlight: 0,
           pollDone: false, speak: s.speak && credit > 0, cancelled: false, question: question};
  job = j;
  var hist = [];
  history.slice(-MAX_TURNS).forEach(function (x) {
    hist.push({role: 'user', content: x.q});
    hist.push({role: 'assistant', content: x.a});
  });
  request('POST', '/api/watch/ask', {text: question, history: hist, speak: j.speak}, function (err, data) {
    if (j.cancelled) return;
    if (err) return fail(j, err);
    j.id = data.id;
    poll(j);
  });
}

function fail(j, message) {
  var m = {};
  m[keys.ERROR] = message;
  send(m);
  if (job === j) job = null;
}

function poll(j) {
  if (j.cancelled) return;
  // hold back while plenty of audio waits for the watch
  if (j.audio.length > 12000) {
    setTimeout(function () { poll(j); }, 300);
    return;
  }
  request('GET', '/api/watch/poll?id=' + encodeURIComponent(j.id) + '&t=' + j.t + '&a=' + j.a, null, function (err, d) {
    if (j.cancelled) return;
    if (err) return fail(j, err);
    if (d.text) {
      j.text += d.text;
      sendText(d.text);
    }
    j.t = d.t;
    j.a = d.a;
    if (d.audio && j.speak) {
      j.audio = j.audio.concat(b64bytes(d.audio));
      feed(j);
    }
    if (d.error) {
      var m = {};
      m[keys.ERROR] = d.error;
      send(m);
    }
    if (d.done) {
      j.pollDone = true;
      history.push({q: j.question, a: j.text});
      if (history.length > MAX_TURNS) history.shift();
      feed(j);
      var done = {};
      done[keys.DONE] = 1;
      send(done);
      return;
    }
    poll(j);
  });
}

// Audio goes to the watch only as far as its buffer has room (CREDIT from the watch).
function feed(j) {
  if (j.cancelled || j.inFlight) return;
  if (j.audio.length && j.credit > 0) {
    var n = Math.min(CHUNK, j.credit, j.audio.length);
    var m = {};
    m[keys.AUDIO] = j.audio.splice(0, n);
    j.credit -= n;
    j.inFlight = 1;
    send(m, function () {
      j.inFlight = 0;
      feed(j);
    });
    return;
  }
  if (j.pollDone && !j.audio.length && j.speak && !j.ended) {
    j.ended = true;
    var e = {};
    e[keys.AUDIO_END] = 1;
    send(e);
  }
}

// ------------------------------------------------------------ events

Pebble.addEventListener('ready', function () {
  var s = {};
  try { s = JSON.parse(localStorage.getItem('settings') || '{}'); } catch (e) { s = {}; }
  if (!s.server) {
    var m = {};
    m[keys.STATUS] = 'Einstellungen öffnen';
    send(m);
  }
});

Pebble.addEventListener('appmessage', function (e) {
  var p = e.payload;
  if (p.QUESTION !== undefined || p[keys.QUESTION] !== undefined) {
    var q = p.QUESTION !== undefined ? p.QUESTION : p[keys.QUESTION];
    var c = p.CREDIT !== undefined ? p.CREDIT : p[keys.CREDIT];
    ask(String(q), c || 0);
    return;
  }
  if (p.CANCEL !== undefined || p[keys.CANCEL] !== undefined) {
    cancel();
  }
  if (p.RESET !== undefined || p[keys.RESET] !== undefined) {
    history = [];
  }
  var credit = p.CREDIT !== undefined ? p.CREDIT : p[keys.CREDIT];
  if (credit !== undefined && job) {
    job.credit += credit;
    feed(job);
  }
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
  localStorage.setItem('settings', JSON.stringify(s));
  var m = {};
  m[keys.SPEAK] = s.SPEAK === false ? 0 : 1;
  m[keys.VOLUME] = parseInt(s.VOLUME, 10) || 100;
  m[keys.AUTOLISTEN] = s.AUTOLISTEN === false ? 0 : 1;
  m[keys.STATUS] = 'Gespeichert';
  send(m);
});
