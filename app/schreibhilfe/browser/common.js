// Spark Schreibhilfe – shared helpers (background, options page and content script).
// Pure functions only: no DOM access at load time, no network, no logging.
(() => {
  'use strict';
  if (globalThis.SparkCommon) return;

  // What the menu offers and how it maps onto the Spark API (POST /api/write/assist).
  const ARTS = [
    { key: 'korrigieren', label: 'Korrigieren', art: 'korrigieren' },
    { key: 'glaetten', label: 'Glätten', art: 'glaetten' },
    { key: 'kuerzer', label: 'Kürzer', art: 'kuerzer' },
    { key: 'freundlicher', label: 'Freundlicher', art: 'freundlicher' },
    { key: 'foermlicher', label: 'Förmlicher', art: 'foermlicher' },
    { key: 'en', label: 'Ins Englische', art: 'uebersetzen', sprache: 'en' },
    { key: 'de', label: 'Ins Deutsche', art: 'uebersetzen', sprache: 'de' },
  ];
  const DEFAULT_ART = 'korrigieren';
  const MAX_TEXT = 20000;
  const CODE_ALPHABET = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{8}$/;

  function artByKey(key) {
    return ARTS.find((a) => a.key === key) || null;
  }

  // Private / home-network host names: the only ones where plain http is accepted.
  function isPrivateHost(hostname) {
    let h = String(hostname || '').toLowerCase().replace(/\.$/, '');
    if (h.startsWith('[') && h.endsWith(']')) h = h.slice(1, -1);
    if (!h) return false;
    if (h === 'localhost' || h.endsWith('.localhost') || h.endsWith('.local')) return true;
    const m = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (m) {
      const [a, b] = [Number(m[1]), Number(m[2])];
      if (m.slice(1).some((x) => Number(x) > 255)) return false;
      return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
    }
    if (h.includes(':')) {
      // IPv6: loopback and unique-local (fc00::/7)
      return h === '::1' || /^f[cd][0-9a-f]{0,2}:/.test(h);
    }
    return false;
  }

  // "https://host[:port]" -> { base, pattern, insecure }. Throws Error with a German message.
  function parseBase(input) {
    const s = String(input || '').trim();
    if (!s) throw new Error('Bitte die Adresse des Spark angeben.');
    if (!/^https?:\/\//i.test(s)) throw new Error('Die Adresse muss mit https:// (oder im Heimnetz http://) beginnen.');
    let u;
    try { u = new URL(s); } catch (_) { throw new Error('Die Adresse ist ungültig.'); }
    if (u.username || u.password) throw new Error('Die Adresse darf keinen Benutzernamen enthalten.');
    if (u.protocol !== 'https:' && u.protocol !== 'http:') throw new Error('Nur https:// oder http:// ist erlaubt.');
    const insecure = u.protocol === 'http:';
    if (insecure && !isPrivateHost(u.hostname)) {
      throw new Error('Unverschlüsseltes http:// geht nur im Heimnetz (z. B. 192.168.x.x). Bitte https:// verwenden.');
    }
    // Host permission pattern without port: match patterns in Firefox do not take ports.
    return { base: u.origin, pattern: `${u.protocol}//${u.hostname}/*`, insecure };
  }

  // Code as typed (trimmed); validates the 8 characters, dash/spaces optional, any case.
  function parseCode(input) {
    const typed = String(input || '').trim();
    const norm = typed.replace(/[\s-]/g, '').toUpperCase();
    if (!CODE_ALPHABET.test(norm)) throw new Error('Der Code hat 8 Zeichen, z. B. ABCD-EFGH.');
    return typed;
  }

  // "<base>#schreib=XXXX-XXXX" -> { base, pattern, insecure, code } or null if it is no setup line.
  function parseSetupLine(input) {
    const s = String(input || '').trim();
    const i = s.indexOf('#schreib=');
    if (i < 0) return null;
    const b = parseBase(s.slice(0, i));
    return Object.assign(b, { code: parseCode(decodeURIComponent(s.slice(i + 9))) });
  }

  function validName(name) {
    const n = String(name || '').trim();
    return /^[\p{L}\p{N} ._-]{1,40}$/u.test(n) ? n : null;
  }

  // Server "detail" may be a string or (validation errors) a list: always give a short German text.
  function detailText(data, status) {
    const d = data && data.detail;
    if (typeof d === 'string' && d.trim()) return d.trim();
    if (status === 401) return 'Dieses Gerät ist nicht (mehr) gekoppelt.';
    if (status === 429) return 'Der Spark ist gerade beschäftigt. Bitte gleich noch einmal versuchen.';
    if (status === 503) return 'Der Spark ist gerade nicht verfügbar.';
    if (status === 413) return 'Der Text ist zu lang.';
    return `Der Spark meldet einen Fehler (${status}).`;
  }

  globalThis.SparkCommon = Object.freeze({
    ARTS, DEFAULT_ART, MAX_TEXT, artByKey, isPrivateHost, parseBase, parseCode, parseSetupLine, validName, detailText,
  });
})();
