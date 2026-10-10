// Spark Schreibhilfe – background (Chrome/Edge: service worker, Firefox: event page).
// Only this file talks to the Spark. No texts or keys are logged, nothing is sent anywhere else.
'use strict';

if (!globalThis.SparkCommon && typeof importScripts === 'function') importScripts('common.js');

const api = globalThis.browser ?? globalThis.chrome;
const { ARTS, DEFAULT_ART, MAX_TEXT, artByKey, detailText } = globalThis.SparkCommon;
const TIMEOUT_MS = 180000;
const MENU_ROOT = 'spark-root';

// ---------- context menu ----------

async function buildMenus() {
  try {
    await api.contextMenus.removeAll();
    api.contextMenus.create({ id: MENU_ROOT, title: 'Mit Spark verbessern', contexts: ['selection', 'editable'] });
    for (const a of ARTS) {
      api.contextMenus.create({ id: `spark-${a.key}`, parentId: MENU_ROOT, title: a.label, contexts: ['selection', 'editable'] });
    }
  } catch (_) { /* menus already there */ }
}

api.runtime.onInstalled.addListener(() => { buildMenus(); });
api.runtime.onStartup.addListener(() => { buildMenus(); });

api.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || typeof tab.id !== 'number' || !String(info.menuItemId).startsWith('spark-')) return;
  const key = String(info.menuItemId).slice(6);
  if (!artByKey(key)) return;
  run(tab, typeof info.frameId === 'number' ? info.frameId : 0, key);
});

api.commands.onCommand.addListener(async (command, tab) => {
  if (command !== 'verbessern') return;
  run(tab || (await activeTab()), null, await defaultArt());
});

api.action.onClicked.addListener(async (tab) => {
  run(tab, null, await defaultArt());
});

async function activeTab() {
  const tabs = await api.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function defaultArt() {
  const { defaultArt: d } = await api.storage.local.get('defaultArt');
  return artByKey(d) ? d : DEFAULT_ART;
}

async function flag(tabId, text, title) {
  try {
    await api.action.setBadgeBackgroundColor({ tabId, color: '#c62828' });
    await api.action.setBadgeText({ tabId, text });
    await api.action.setTitle({ tabId, title });
    setTimeout(() => {
      api.action.setBadgeText({ tabId, text: '' }).catch(() => {});
      api.action.setTitle({ tabId, title: 'Spark Schreibhilfe – markierten Text verbessern' }).catch(() => {});
    }, 6000);
  } catch (_) { /* tab gone */ }
}

// Inject the content script on demand and start it in the frame that holds the selection.
async function run(tab, frameId, key) {
  if (!tab || typeof tab.id !== 'number') return;
  const tabId = tab.id;
  const { key: deviceKey } = await api.storage.local.get('key');
  if (!deviceKey) {
    api.runtime.openOptionsPage();
    return;
  }
  try {
    if (frameId === null) {
      // Keyboard shortcut / toolbar button: find the frame with focus and a selection.
      try {
        await api.scripting.executeScript({ target: { tabId, allFrames: true }, files: ['common.js', 'content.js'] });
      } catch (_) { /* some frames may be off limits; probe what we can */ }
      const results = await api.scripting.executeScript({
        target: { tabId, allFrames: true },
        func: () => (globalThis.__sparkSchreib ? globalThis.__sparkSchreib.probe() : null),
      });
      let best = null;
      let bestScore = -1;
      for (const r of results || []) {
        const p = r && r.result;
        if (!p) continue;
        const score = (p.sel ? 4 : 0) + (p.focus ? 2 : 0) + (p.editable ? 1 : 0);
        if (score > bestScore) { best = r; bestScore = score; }
      }
      frameId = best && typeof best.frameId === 'number' ? best.frameId : 0;
    } else {
      await api.scripting.executeScript({ target: { tabId, frameIds: [frameId] }, files: ['common.js', 'content.js'] });
    }
    await api.scripting.executeScript({
      target: { tabId, frameIds: [frameId] },
      func: (k) => { if (globalThis.__sparkSchreib) globalThis.__sparkSchreib.start(k); },
      args: [key],
    });
  } catch (_) {
    flag(tabId, '!', 'Spark Schreibhilfe: Auf dieser Seite nicht möglich (geschützte Seite oder eingebetteter Rahmen).');
  }
}

// ---------- talking to the Spark ----------

async function assist(msg) {
  const a = artByKey(msg && msg.art);
  const text = msg && typeof msg.text === 'string' ? msg.text : '';
  if (!a) return { ok: false, code: 'bad', detail: 'Unbekannte Aktion.' };
  if (!text.trim()) return { ok: false, code: 'bad', detail: 'Kein Text markiert.' };
  if (text.length > MAX_TEXT) return { ok: false, code: 'bad', detail: `Der Text ist zu lang (höchstens ${MAX_TEXT} Zeichen).` };

  const { base, key } = await api.storage.local.get(['base', 'key']);
  if (!base || !key) return { ok: false, code: 'unpaired', detail: 'Noch nicht gekoppelt. Bitte in den Einstellungen koppeln.' };

  const body = { text, art: a.art };
  if (a.sprache) body.sprache = a.sprache;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(`${base}/api/write/assist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Speech-Device': key },
      body: JSON.stringify(body),
      signal: ctrl.signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
    });
    let data = null;
    try { data = await r.json(); } catch (_) { data = null; }
    if (r.status === 401) {
      return { ok: false, code: 'auth', detail: 'Dieses Gerät ist beim Spark nicht mehr gekoppelt. Bitte in den Einstellungen neu koppeln.' };
    }
    if (!r.ok) return { ok: false, code: 'http', status: r.status, detail: detailText(data, r.status) };
    if (!data || typeof data.text !== 'string') return { ok: false, code: 'http', detail: 'Unerwartete Antwort vom Spark.' };
    return {
      ok: true,
      data: {
        text: data.text,
        diff: Array.isArray(data.diff) ? data.diff : null,
        changes: typeof data.changes === 'number' ? data.changes : null,
        ms: typeof data.ms === 'number' ? data.ms : null,
      },
    };
  } catch (e) {
    if (e && e.name === 'AbortError') {
      return { ok: false, code: 'timeout', detail: 'Der Spark hat nicht rechtzeitig geantwortet (3 Minuten). Bitte später noch einmal versuchen.' };
    }
    return { ok: false, code: 'net', detail: `Der Spark ist nicht erreichbar (${base}). Ist das Gerät im selben Netz und die Seitenberechtigung erteilt?` };
  } finally {
    clearTimeout(timer);
  }
}

api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!sender || sender.id !== api.runtime.id || !msg || typeof msg.type !== 'string') return false;
  if (msg.type === 'schreib-assist') {
    assist(msg).then(sendResponse, () => sendResponse({ ok: false, code: 'net', detail: 'Unbekannter Fehler.' }));
    return true;
  }
  if (msg.type === 'schreib-options') {
    api.runtime.openOptionsPage();
    sendResponse({ ok: true });
    return false;
  }
  if (msg.type === 'schreib-default') {
    defaultArt().then((d) => sendResponse({ ok: true, art: d }));
    return true;
  }
  return false;
});
