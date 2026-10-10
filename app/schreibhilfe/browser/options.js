// Spark Schreibhilfe – options page: pairing, default action, optional all-sites permission.
'use strict';

const api = globalThis.browser ?? globalThis.chrome;
const C = globalThis.SparkCommon;
const $ = (id) => document.getElementById(id);
const ALL_SITES = ['https://*/*', 'http://*/*'];

function say(node, text, kind) {
  node.textContent = text || '';
  node.className = `msg${kind ? ` ${kind}` : ''}`;
}

// Base + code from the form (setup line preferred). Throws Error with German text.
function readForm() {
  const line = $('setup').value.trim();
  let parsed = line ? C.parseSetupLine(line) : null;
  if (line && !parsed) {
    // A bare address in the setup field: take the code from the separate field.
    parsed = Object.assign(C.parseBase(line), { code: C.parseCode($('code').value) });
  }
  if (!parsed) {
    parsed = Object.assign(C.parseBase($('base').value), { code: C.parseCode($('code').value) });
  }
  const name = C.validName($('name').value);
  if (!name) throw new Error('Der Gerätename darf 1–40 Zeichen haben: Buchstaben, Ziffern, Leerzeichen und . - _');
  parsed.name = name;
  return parsed;
}

function updateWarning() {
  let info = null;
  try { info = readForm(); } catch (_) { info = null; }
  const w = $('warn');
  if (info && info.insecure) {
    w.textContent = 'Achtung: http:// ist unverschlüsselt. Das geht nur im Heimnetz – unterwegs bitte die https-Adresse verwenden.';
    w.hidden = false;
  } else {
    w.hidden = true;
  }
}

async function render() {
  const s = await api.storage.local.get(['base', 'key', 'profile', 'deviceName', 'defaultArt']);
  const paired = !!(s.base && s.key);
  $('paired').hidden = !paired;
  $('pairing').querySelector('h2').textContent = paired ? 'Neu koppeln' : 'Mit dem Spark koppeln';
  if (paired) $('state').textContent = `Gekoppelt mit ${s.profile || '?'} auf ${s.base}`;
  if (s.deviceName) $('name').value = s.deviceName;

  const sel = $('defaultArt');
  if (!sel.options.length) {
    for (const a of C.ARTS) {
      const o = document.createElement('option');
      o.value = a.key;
      o.textContent = a.label;
      sel.appendChild(o);
    }
  }
  sel.value = C.artByKey(s.defaultArt) ? s.defaultArt : C.DEFAULT_ART;

  try {
    const all = await api.permissions.contains({ origins: ALL_SITES });
    $('allSites').hidden = all;
    $('noAllSites').hidden = !all;
  } catch (_) { /* ignore */ }

  try {
    const cmds = await api.commands.getAll();
    const c = cmds.find((x) => x.name === 'verbessern');
    $('shortcut').textContent = c && c.shortcut ? c.shortcut : 'kein Kürzel gesetzt';
  } catch (_) { /* ignore */ }
}

async function pairWith(info) {
  const r = await fetch(`${info.base}/api/write/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: info.code, name: info.name, kind: 'browser' }),
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    referrerPolicy: 'no-referrer',
  });
  let data = null;
  try { data = await r.json(); } catch (_) { data = null; }
  if (!r.ok) {
    if (r.status === 429) throw new Error(C.detailText(data, 429) + ' (Zu viele Versuche – bitte kurz warten.)');
    throw new Error(C.detailText(data, r.status));
  }
  if (!data || typeof data.key !== 'string' || !data.key) throw new Error('Unerwartete Antwort vom Spark.');
  return data;
}

$('pair').addEventListener('click', () => {
  const msg = $('msg');
  let info;
  try {
    info = readForm();
  } catch (e) {
    say(msg, e.message, 'err');
    return;
  }
  // Must be called directly in the click handler (Firefox: user gesture).
  const asked = api.permissions.request({ origins: [info.pattern] });
  const btn = $('pair');
  btn.disabled = true;
  say(msg, 'Koppeln …');
  Promise.resolve(asked)
    .then(async (granted) => {
      if (!granted) throw new Error('Ohne Zugriff auf die Adresse des Spark geht es nicht. Bitte die Berechtigung erlauben.');
      let data;
      try {
        data = await pairWith(info);
      } catch (e) {
        if (e instanceof TypeError) throw new Error(`Der Spark ist unter ${info.base} nicht erreichbar.`);
        throw e;
      }
      const old = await api.storage.local.get('base');
      await api.storage.local.set({ base: info.base, key: data.key, profile: String(data.profile || ''), deviceName: info.name });
      if (old.base && old.base !== info.base) await dropOrigin(old.base);
      $('setup').value = '';
      $('code').value = '';
      say(msg, `Gekoppelt mit ${data.profile || '?'} – fertig. Text markieren, Rechtsklick → „Mit Spark verbessern“.`, 'ok');
      await render();
    })
    .catch(async (e) => {
      say(msg, e && e.message ? e.message : 'Koppeln ging nicht.', 'err');
    })
    .finally(() => { btn.disabled = false; });
});

async function dropOrigin(base) {
  try {
    const p = C.parseBase(base).pattern;
    if (await api.permissions.contains({ origins: ALL_SITES })) return; // the all-sites grant covers it anyway
    await api.permissions.remove({ origins: [p] });
  } catch (_) { /* ignore */ }
}

$('unpair').addEventListener('click', async () => {
  const s = await api.storage.local.get('base');
  await api.storage.local.remove(['key', 'profile', 'base']);
  if (s.base) await dropOrigin(s.base);
  say($('msg'), 'Entkoppelt. Im Spark-Panel unter Ich → Schreibhilfe kannst du das Gerät auch dort entfernen.', 'ok');
  await render();
});

$('test').addEventListener('click', async () => {
  const out = $('pairedMsg');
  const s = await api.storage.local.get(['base', 'key']);
  if (!s.base || !s.key) return;
  say(out, 'Prüfe …');
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 15000);
  try {
    const r = await fetch(`${s.base}/api/write`, {
      headers: { 'X-Speech-Device': s.key },
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      signal: ctrl.signal,
    });
    let data = null;
    try { data = await r.json(); } catch (_) { data = null; }
    if (r.status === 401) say(out, 'Dieses Gerät ist nicht mehr gekoppelt. Bitte neu koppeln.', 'err');
    else if (!r.ok) say(out, C.detailText(data, r.status), 'err');
    else if (data && data.on === false) say(out, 'Verbunden, aber die Schreibhilfe ist für dich ausgeschaltet.', 'err');
    else say(out, 'Verbindung in Ordnung.', 'ok');
  } catch (_) {
    say(out, `Der Spark ist unter ${s.base} nicht erreichbar.`, 'err');
  } finally {
    clearTimeout(t);
  }
});

$('defaultArt').addEventListener('change', (ev) => {
  const v = ev.target.value;
  if (C.artByKey(v)) api.storage.local.set({ defaultArt: v });
});

$('allSites').addEventListener('click', () => {
  Promise.resolve(api.permissions.request({ origins: ALL_SITES }))
    .then((ok) => {
      say($('allMsg'), ok ? 'Erlaubt.' : 'Nicht erlaubt.', ok ? 'ok' : 'err');
      return render();
    })
    .catch(() => say($('allMsg'), 'Ging nicht.', 'err'));
});

$('noAllSites').addEventListener('click', async () => {
  try {
    await api.permissions.remove({ origins: ALL_SITES });
    const s = await api.storage.local.get('base');
    const keeps = s.base ? await api.permissions.contains({ origins: [C.parseBase(s.base).pattern] }) : true;
    say($('allMsg'), keeps ? 'Zurückgenommen.' : 'Zurückgenommen. Der Zugriff auf den Spark ging dabei mit verloren – bitte neu koppeln.', keeps ? 'ok' : 'err');
  } catch (_) {
    say($('allMsg'), 'Ging nicht.', 'err');
  }
  await render();
});

for (const id of ['setup', 'base', 'code']) $(id).addEventListener('input', updateWarning);

render();
