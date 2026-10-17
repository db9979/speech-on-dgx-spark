// Phone side of the Spark watch app: takes the dictated question from the watch, asks the
// Spark (/api/watch/ask), polls text and audio (/api/watch/poll) and passes both on.
//
// Reliability: every answer part carries the question's number (SEQ), so the watch drops parts of a
// cancelled answer. Messages that fail are repeated, text goes before audio, and audio flows only as
// far as the watch reported free buffer (FREED, a running total, so a lost report does no harm).
//
// Since 2.0: two addresses (at home, and https for on the road: the one that answers is used), the watch's list of
// quick commands and reminders (/api/watch/sync, agenda.c keeps them as wake-ups), the ring and the buttons of a
// reminder (/api/watch/reminder), follow-ups and a proposal's yes or no under an answer.
var configPage = require('./config');
var keys = require('message_keys');

var CHUNK_MAX = 3800;  // audio bytes per AppMessage (fewer Bluetooth round trips)
var CHUNK_OLD = 1500;  // for watch apps that do not tell their inbox size
var TEXT_CHUNK = 400;  // answer characters per AppMessage
var APP_VERSION = '2.0.0';  // same as package.json; the Spark says when it serves a newer one
var MAX_TURNS = 6;     // earlier question/answer pairs sent along as context
var TRIES = 10;        // attempts per message before the answer is given up
var KEEPALIVE = 10000; // ms: tell the watch the answer is still coming
var PROBE_MS = 4000;   // a try at an address that may not answer (at home vs. on the road)
var VIA_KEEP = 300000; // ms the address that answered stays the first choice
var ACTS = ['played', 'snooze', 'stop', 'plus', 'cancel'];   // REM_ACT from the watch (agenda.h)

var history = [];
var job = null;        // the running answer
var prio = [];         // text, status, end: sent first
var audioq = [];       // audio, sent when nothing in prio waits
var sending = null;
var via = '';          // 'home' or 'out': the address that answered last
var viaAt = 0;

function settings() {
  var s = {};
  try { s = JSON.parse(localStorage.getItem('settings') || '{}'); } catch (e) { s = {}; }
  return {
    server: String(s.server || 'http://tars:31080').replace(/\/+$/, ''),
    // the address for on the road, https only (the key travels through the internet there)
    out: /^https:\/\/[A-Za-z0-9.\-]+(:\d{1,5})?\/?$/.test(String(s.server_out || '')) ? String(s.server_out).replace(/\/+$/, '') : '',
    key: String(s.device_key || '').trim(),
    speak: s.SPEAK !== false
  };
}

// ------------------------------------------------------------ sending to the watch

function send(msg, opts) {
  opts = opts || {};
  var item = {msg: msg, done: opts.done, job: opts.job || null, tries: 0};
  (opts.audio ? audioq : prio).push(item);
  pump();
}

function pump() {
  if (sending) return;
  var item = prio.length ? prio.shift() : audioq.shift();
  if (!item) return;
  if (item.job && item.job.cancelled) return pump();
  sending = item;
  if (item.job) item.job.lastSent = Date.now();
  Pebble.sendAppMessage(item.msg, function () {
    sending = null;
    if (item.done) item.done();
    pump();
  }, function () {
    sending = null;
    item.tries++;
    if (item.job) item.job.retries++;
    if (item.tries >= TRIES) {
      // the watch does not take it: an answer with a gap is worse than none
      if (item.job) {
        item.job.outcome = 'send';
        stop(item.job);
      }
      return pump();
    }
    // back to the front of its lane, after a pause that grows with each attempt
    ((item.msg[keys.AUDIO] !== undefined || item.msg[keys.AUDIO_END] !== undefined) ? audioq : prio).unshift(item);
    setTimeout(pump, 100 * item.tries);
  });
}

function forJob(j, m) {
  m[keys.SEQ] = j.seq;
  return m;
}

function sendText(j, text) {
  for (var i = 0; i < text.length; i += TEXT_CHUNK) {
    var m = {};
    m[keys.ANSWER] = text.substr(i, TEXT_CHUNK);
    send(forJob(j, m), {job: j, done: function () {
      if (!j.firstText) j.firstText = Date.now();
    }});
  }
}

// ------------------------------------------------------------ talking to the Spark

// The addresses in the order to try: the one that answered lately first.
function bases(s) {
  var list = [{name: 'home', url: s.server}];
  if (s.out) list.push({name: 'out', url: s.out});
  if (via === 'out' && Date.now() - viaAt < VIA_KEEP && list.length > 1) list.reverse();
  return list;
}

function answered(name) {
  var changed = name !== via;
  via = name;
  viaAt = Date.now();
  if (changed && settings().out) {
    var m = {};
    m[keys.WHERE] = name === 'out' ? 1 : 0;
    send(m);
  }
}

// One request to the Spark. With two addresses a failed try moves on to the other one: always when nothing was
// reached (network error), on a timeout only for reading requests (a question that timed out may be running).
function request(method, path, body, cb) {
  var s = settings();
  var list = bases(s);
  var probe = list.length > 1 && !(via && Date.now() - viaAt < VIA_KEEP);
  var at = 0;
  function next(err, data, status, timedOut) {
    at++;
    if (at < list.length && status === 0 && (!timedOut || method === 'GET')) return one();
    cb(err, data, status);
  }
  function one() {
    var base = list[at];
    tryOnce(method, base.url, path, body, probe && at < list.length - 1 ? PROBE_MS : 30000, function (err, data, status, timedOut) {
      if (!err || status) answered(base.name);
      if (err) return next(err, data, status, timedOut);
      cb(null, data, status);
    });
  }
  one();
}

function tryOnce(method, server, path, body, timeout, cb) {
  var s = settings();
  var xhr = new XMLHttpRequest();
  xhr.open(method, server + path, true);
  xhr.timeout = timeout;
  xhr.setRequestHeader('Content-Type', 'application/json');
  if (s.key) xhr.setRequestHeader('X-Speech-Device', s.key);
  xhr.onload = function () {
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
    if (xhr.status >= 200 && xhr.status < 300 && data) {
      cb(null, data);
    } else {
      var detail = data && data.detail ? data.detail : xhr.status;
      cb(xhr.status === 401 ? 'Spark verlangt eine Anmeldung (Geräteschlüssel prüfen).' : 'Spark: ' + detail, null, xhr.status);
    }
  };
  xhr.onerror = function () { cb('Spark nicht erreichbar: ' + server, null, 0, false); };
  xhr.ontimeout = function () { cb('Spark antwortet nicht.', null, 0, true); };
  xhr.send(body ? JSON.stringify(body) : null);
}

var B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function b64bytes(s, out) {
  var buf = 0, bits = 0;
  for (var i = 0; i < s.length; i++) {
    var v = B64.indexOf(s.charAt(i));
    if (v < 0) continue;
    buf = ((buf << 6) | v) & 0xffffff;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push((buf >> bits) & 255);
    }
  }
}

// Times and the outcome of one answer go to the Spark's log (Zustand → Logs), so a slow or broken
// answer can be traced: dictation on the watch, first text and first sound on the watch, the end.
function report(j) {
  if (j.reported || !j.id) return;
  j.reported = true;
  var t = function (x) { return x ? x - j.start : 0; };
  request('POST', '/api/watch/report', {
    id: j.id, dictation_ms: j.dictMs, text_ms: t(j.firstText), audio_ms: t(j.firstAudio), done_ms: t(Date.now()),
    retries: j.retries, chunk: j.chunk, stalls: j.stalls || 0, outcome: j.outcome || 'ok'
  }, function () {});
}

function stop(j) {
  if (j.cancelled) return;
  j.cancelled = true;
  clearInterval(j.alive);
  if (j.id && !j.pollDone) request('DELETE', '/api/watch/' + j.id, null, function () {});
  report(j);
  if (job === j) job = null;
  audioq = audioq.filter(function (q) { return q.job !== j; });
  prio = prio.filter(function (q) { return q.job !== j; });
}

function ask(question, p) {
  if (job) {
    job.outcome = job.outcome || 'replaced';
    stop(job);
  }
  var s = settings();
  var credit = p.CREDIT || 0;
  var inbox = p.INBOX || 0;
  var j = {id: null, seq: p.SEQ || 0, t: 0, a: 0, text: '', audio: [], window: credit, sent: 0, freed: 0,
           inFlight: false, pollDone: false, speak: s.speak && credit > 0, cancelled: false, question: question,
           chunk: inbox ? Math.max(200, Math.min(CHUNK_MAX, inbox - 120)) : CHUNK_OLD,
           start: Date.now(), dictMs: p.DICT_MS || 0, retries: 0, lastSent: Date.now()};
  job = j;
  // a sign of life for the watch while the Spark thinks, so it does not give up too early
  j.alive = setInterval(function () {
    if (!j.cancelled && Date.now() - j.lastSent > KEEPALIVE - 500) send(forJob(j, {}), {job: j});
  }, KEEPALIVE);
  var hist = [];
  history.slice(-MAX_TURNS).forEach(function (x) {
    hist.push({role: 'user', content: x.q});
    hist.push({role: 'assistant', content: x.a});
  });
  request('POST', '/api/watch/ask', {text: question, history: hist, speak: j.speak, app: APP_VERSION}, function (err, data) {
    if (j.cancelled) return;
    if (err) return fail(j, err, 'ask');
    j.id = data.id;
    setFace(data.face);
    j.appNew = !!data.app_new;
    poll(j);
  });
}

function fail(j, message, outcome) {
  var m = {};
  m[keys.ERROR] = message;
  send(forJob(j, m));    // not tied to the job's fate: the watch must hear about it
  j.outcome = outcome;
  j.pollDone = true;
  stop(j);
}

function poll(j) {
  if (j.cancelled) return;
  // hold back while plenty of audio waits for the watch
  if (j.audio.length > 16000) {
    setTimeout(function () { poll(j); }, 300);
    return;
  }
  request('GET', '/api/watch/poll?id=' + encodeURIComponent(j.id) + '&t=' + j.t + '&a=' + j.a, null, function (err, d, status) {
    if (j.cancelled) return;
    if (err) {
      // one network hiccup is not the end of the answer: try again a few times
      if (status !== 404 && (j.pollErrors = (j.pollErrors || 0) + 1) <= 3) {
        setTimeout(function () { poll(j); }, 500 * j.pollErrors);
        return;
      }
      return fail(j, err, 'poll');
    }
    j.pollErrors = 0;
    if (d.text) {
      j.text += d.text;
      sendText(j, d.text);
    }
    j.t = d.t;
    j.a = d.a;
    if (d.audio && j.speak) {
      b64bytes(d.audio, j.audio);
      feed(j);
    }
    if (d.audio_end && !j.audioDone) {   // all speech is in; the follow-ups may still come
      j.audioDone = true;
      feed(j);
    }
    if (d.error && !j.errSent) {
      j.errSent = true;
      var m = {};
      m[keys.ERROR] = d.error;
      send(forJob(j, m), {job: j});
      j.outcome = 'spark';
    }
    if (d.done) {
      j.pollDone = true;
      j.audioDone = true;
      // under the answer: follow-ups to tap, a proposal's ✓ and ✕; a changed reminder: the watch's list again
      if (d.follow && d.follow.length) {
        var f = {};
        f[keys.FOLLOW] = d.follow.slice(0, 3).map(function (x) { return String(x).substr(0, 50); }).join('\n');
        send(forJob(j, f), {job: j});
      }
      if (d.proposal) {
        var pr = {};
        pr[keys.PROPOSAL] = String(d.proposal).substr(0, 290);
        send(forJob(j, pr), {job: j});
      }
      if (d.agenda) sync();
      history.push({q: j.question, a: j.text});
      if (history.length > MAX_TURNS) history.shift();
      // a newer watch app waits in the panel: say so under the answer, at most once a day
      var today = new Date().toDateString();
      if (j.appNew && localStorage.getItem('appNote') !== today) {
        localStorage.setItem('appNote', today);
        sendText(j, '\n\nNeue Uhr-App: im Panel unter Ich > Pebble-Uhr installieren.');
      }
      var done = {};
      // 2: speech follows (the watch then waits for AUDIO_END)
      done[keys.DONE] = j.speak ? 2 : 1;
      send(forJob(j, done), {job: j, done: function () {
        j.doneSent = true;
        if (!j.speak || j.ended) finish(j);
      }});
      feed(j);
      return;
    }
    poll(j);
  });
}

function finish(j) {
  clearInterval(j.alive);
  report(j);
  if (job === j) job = null;
}

// Audio goes to the watch only as far as its buffer has room: the watch may hold `window` bytes
// more than it has played (FREED).
function feed(j) {
  if (j.cancelled || j.inFlight || !j.speak) return;
  var room = j.freed + j.window - j.sent;
  if (j.audio.length && room > 0) {
    var n = Math.min(j.chunk, room, j.audio.length);
    var m = {};
    m[keys.AUDIO] = j.audio.splice(0, n);
    j.sent += n;
    j.inFlight = true;
    send(forJob(j, m), {job: j, audio: true, done: function () {
      j.inFlight = false;
      if (!j.firstAudio) j.firstAudio = Date.now();
      feed(j);
    }});
    return;
  }
  if (j.audioDone && !j.audio.length && !j.ended) {
    j.ended = true;
    var e = {};
    e[keys.AUDIO_END] = 1;
    send(forJob(j, e), {job: j, audio: true, done: function () {
      if (j.doneSent || !j.id) finish(j);
    }});
  }
}

// ------------------------------------------------------------ setting up with a code from the panel

// The panel (Ich → Pebble-Uhr → Pebble koppeln) gives a line like "http://tars:31080#pebble=CODE", with an
// address for on the road "…&aussen=https://spark.example".
function pair(line, done) {
  var m = /^\s*(https?:\/\/[A-Za-z0-9.\-]+(?::\d{1,5})?)\/?#pebble=([A-Za-z0-9_\-]{20,40})(?:&aussen=(https:\/\/[A-Za-z0-9.\-]+(?::\d{1,5})?)\/?)?\s*$/.exec(line || '');
  if (!m) return done('Der Einrichtungscode passt nicht. Im Panel einen neuen holen.');
  var outside = m[3] || '';
  var xhr = new XMLHttpRequest();
  xhr.open('POST', m[1] + '/api/pebble/pair', true);
  xhr.timeout = 15000;
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = function () {
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
    if (xhr.status === 200 && data && data.token) return done(null, m[1], data.token, data.profile, data.face, outside);
    done(data && data.detail ? String(data.detail) : 'Spark: ' + xhr.status);
  };
  xhr.onerror = function () { done('Spark nicht erreichbar: ' + m[1]); };
  xhr.ontimeout = function () { done('Spark antwortet nicht.'); };
  xhr.send(JSON.stringify({code: m[2]}));
}

// The face the admin picked in the panel; the watch keeps it, so it is only sent when it changes.
var FACES = {robot: 0, comic: 1, comic_woman: 2};

function setFace(name, always) {
  if (!Object.prototype.hasOwnProperty.call(FACES, name)) return;
  if (!always && localStorage.getItem('face') === name) return;
  localStorage.setItem('face', name);
  var m = {};
  m[keys.FACE] = FACES[name];
  send(m);
}

// ------------------------------------------------------------ quick commands and reminders on the watch

var syncing = false;

// The watch keeps the quick commands and the next reminders itself (agenda.c): fetched at the start, after an
// answer that set or cancelled one, when a list opens and after each button on a reminder.
function sync() {
  if (syncing || !settings().key) return;
  syncing = true;
  request('GET', '/api/watch/sync', null, function (err, d) {
    syncing = false;
    if (err || !d) return;
    var m = {};
    m[keys.QUICK] = (d.quick || []).slice(0, 12).map(function (x) { return String(x).substr(0, 60); }).join('\n');
    if (d.agenda === null || d.agenda === undefined) {
      m[keys.REMIND] = 0;
    } else {
      m[keys.REMIND] = 1;
      m[keys.AGENDA] = agendaLines(d.agenda);
    }
    send(m);
  });
}

function agendaLines(list) {
  return (list || []).slice(0, 8).map(function (x) {
    return [String(x.id).replace(/[^0-9a-f]/g, ''), x.due | 0, x.made | 0, x.rep ? 1 : 0,
            String(x.text || '').replace(/[|\n]/g, ' ').substr(0, 60)].join('|');
  }).join('\n');
}

function reminderAct(id, act, text) {
  var word = ACTS[act];
  if (!word || !/^[0-9a-f]{1,16}$/.test(id)) return;
  request('POST', '/api/watch/reminder', {id: id, act: word, text: String(text || '').substr(0, 200)}, function (err, d) {
    if (err || !d || !d.agenda) return;
    var m = {};
    m[keys.REMIND] = 1;
    m[keys.AGENDA] = agendaLines(d.agenda);
    send(m);
  });
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
  var face = localStorage.getItem('face');
  if (face) setFace(face, true);   // a reinstalled watch app starts with the robot
  sync();
});

function val(p, name) {
  return p[name] !== undefined ? p[name] : p[keys[name]];
}

Pebble.addEventListener('appmessage', function (e) {
  var p = e.payload;
  var rid = val(p, 'REM_ID');
  if (rid !== undefined) {
    reminderAct(String(rid), val(p, 'REM_ACT') | 0, val(p, 'REM_TEXT'));
    return;
  }
  if (val(p, 'SYNC') !== undefined) {
    sync();
    return;
  }
  var seq = val(p, 'SEQ');
  var q = val(p, 'QUESTION');
  if (q !== undefined) {
    ask(String(q), {SEQ: seq, CREDIT: val(p, 'CREDIT'), INBOX: val(p, 'INBOX'), DICT_MS: val(p, 'DICT_MS')});
    return;
  }
  if (val(p, 'CANCEL') !== undefined && job && (seq === undefined || seq === job.seq)) {
    job.outcome = 'cancel';
    stop(job);
  }
  if (val(p, 'RESET') !== undefined) {
    history = [];
  }
  var stalls = val(p, 'STALLS');
  if (stalls !== undefined && job && seq === job.seq && stalls > (job.stalls || 0)) job.stalls = stalls;
  var freed = val(p, 'FREED');
  if (freed !== undefined && job && seq === job.seq && freed > job.freed) {
    job.freed = freed;
    feed(job);
  }
  var credit = val(p, 'CREDIT');   // watch app 1.1 and older: freed space as steps
  if (credit !== undefined && job && seq === undefined) {
    job.freed += credit;
    feed(job);
  }
});

Pebble.addEventListener('showConfiguration', function () {
  var s = {};
  try { s = JSON.parse(localStorage.getItem('settings') || '{}'); } catch (e) { s = {}; }
  Pebble.openURL(configPage(s));
});

function saved(s, note) {
  localStorage.setItem('settings', JSON.stringify(s));
  var m = {};
  m[keys.SPEAK] = s.SPEAK === false ? 0 : 1;
  m[keys.VOLUME] = parseInt(s.VOLUME, 10) || 100;
  m[keys.AUTOLISTEN] = s.AUTOLISTEN === false ? 0 : 1;
  m[keys.STATUS] = note || 'Gespeichert';
  send(m);
}

Pebble.addEventListener('webviewclosed', function (e) {
  if (!e || !e.response) return;
  var s;
  try { s = JSON.parse(decodeURIComponent(e.response)); } catch (err) { return; }
  var setup = String(s.setup || '').trim();
  delete s.setup;
  if (!setup) {
    saved(s);
    return sync();
  }
  pair(setup, function (err, server, token, profile, face, outside) {
    if (err) {
      var m = {};
      m[keys.STATUS] = 'Kopplung fehlgeschlagen';
      send(m);
      console.log('pair: ' + err);
      return;
    }
    s.server = server;
    s.server_out = outside || s.server_out || '';
    s.device_key = token;
    setFace(face, true);
    saved(s, profile ? 'Gekoppelt: ' + String(profile).substr(0, 30) : 'Gekoppelt');
    sync();
  });
});
