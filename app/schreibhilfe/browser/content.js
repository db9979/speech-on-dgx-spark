// Spark Schreibhilfe – content script, injected on demand (after common.js) into the frame with the selection.
// It never talks to the Spark itself: the background does. No texts are logged or stored.
(() => {
  'use strict';
  if (globalThis.__sparkSchreib) return;
  const api = globalThis.browser ?? globalThis.chrome;
  const C = globalThis.SparkCommon;

  // ---------- pure helpers (kept free of page state) ----------

  // Server diff [["=", s], ["-", s], ["+", s]] -> DocumentFragment (whitespace is part of the tokens).
  function buildDiff(doc, diff) {
    const frag = doc.createDocumentFragment();
    if (!Array.isArray(diff)) return frag;
    for (const part of diff) {
      if (!Array.isArray(part) || part.length < 2) continue;
      const op = part[0];
      const text = String(part[1] == null ? '' : part[1]);
      let node;
      if (op === '-') {
        node = doc.createElement('del');
        node.className = 'rm';
        node.textContent = text;
      } else if (op === '+') {
        node = doc.createElement('ins');
        node.className = 'add';
        node.textContent = text;
      } else {
        node = doc.createTextNode(text);
      }
      frag.appendChild(node);
    }
    return frag;
  }

  // Where to put a w×h box next to rect inside a vw×vh viewport (below if it fits, else above, else clamped).
  function placeBox(rect, vw, vh, w, h) {
    const gap = 8;
    const margin = 8;
    const r = rect && (rect.width || rect.height) ? rect : { left: (vw - w) / 2, top: vh / 3, bottom: vh / 3, width: 0, height: 0 };
    let top = r.bottom + gap;
    if (top + h > vh - margin) {
      const above = r.top - gap - h;
      top = above >= margin ? above : Math.max(margin, vh - margin - h);
    }
    let left = Math.min(Math.max(margin, r.left), Math.max(margin, vw - margin - w));
    return { left: Math.round(left), top: Math.round(Math.max(margin, top)) };
  }

  // Replace [start,end) of value with text, as long as the old part is still the same text.
  function spliceField(value, start, end, oldText, text) {
    let s = start;
    let e = end;
    if (value.slice(s, e) !== oldText) {
      const i = oldText ? value.indexOf(oldText) : -1;
      if (i < 0) return null;
      s = i;
      e = i + oldText.length;
    }
    return { value: value.slice(0, s) + text + value.slice(e), caret: s + text.length };
  }

  // ---------- reading the selection ----------

  const FIELD_TYPES = new Set(['text', 'search', 'url', 'tel', 'email', '']);

  function deepActive() {
    let el = document.activeElement;
    while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement;
    return el;
  }

  function isField(el) {
    if (!el) return false;
    if (el.tagName === 'TEXTAREA') return !el.readOnly && !el.disabled;
    if (el.tagName === 'INPUT') return FIELD_TYPES.has((el.getAttribute('type') || '').toLowerCase()) && !el.readOnly && !el.disabled;
    return false;
  }

  function fieldRange(el) {
    try {
      if (typeof el.selectionStart === 'number' && typeof el.selectionEnd === 'number') {
        return [el.selectionStart, el.selectionEnd];
      }
    } catch (_) { /* e.g. type=email has no selection API */ }
    return null;
  }

  function editableRoot(node) {
    let n = node && node.nodeType === 1 ? node : node && node.parentElement;
    let root = null;
    while (n) {
      if (n.isContentEditable) root = n;
      else if (root) break;
      n = n.parentElement;
    }
    return root;
  }

  function probe() {
    const el = deepActive();
    let sel = false;
    let editable = false;
    if (isField(el)) {
      editable = true;
      sel = el.value.trim().length > 0;
    } else {
      const s = window.getSelection();
      sel = !!(s && s.rangeCount && !s.isCollapsed && s.toString().trim());
      editable = !!(el && el.isContentEditable);
    }
    return { focus: document.hasFocus(), sel, editable };
  }

  function capture() {
    const el = deepActive();
    if (isField(el)) {
      let r = fieldRange(el);
      let whole = false;
      if (!r || r[0] === r[1]) {
        r = [0, el.value.length];
        whole = true;
      }
      const text = el.value.slice(r[0], r[1]);
      if (!text.trim()) return null;
      return { kind: 'field', el, start: r[0], end: r[1], text, whole, rect: el.getBoundingClientRect() };
    }
    const s = window.getSelection();
    if (s && s.rangeCount && !s.isCollapsed) {
      const range = s.getRangeAt(0).cloneRange();
      const text = s.toString();
      if (!text.trim()) return null;
      const root = editableRoot(range.commonAncestorContainer);
      let rect = range.getBoundingClientRect();
      if (!rect.width && !rect.height && root) rect = root.getBoundingClientRect();
      return { kind: root ? 'rich' : 'page', range, root, text, rect };
    }
    return null;
  }

  // ---------- writing the result back ----------

  function setNativeValue(el, value) {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
  }

  function applyField(c, text) {
    const el = c.el;
    if (!el.isConnected) throw new Error('Das Textfeld gibt es nicht mehr. Bitte „Kopieren“ verwenden.');
    const out = spliceField(el.value, c.start, c.end, c.text, text);
    if (!out) throw new Error('Der Text im Feld wurde inzwischen geändert. Bitte „Kopieren“ verwenden.');
    el.focus({ preventScroll: true });
    setNativeValue(el, out.value);
    el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, inputType: 'insertReplacementText', data: text }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    try { el.setSelectionRange(out.caret, out.caret); } catch (_) { /* not supported */ }
  }

  function textFragment(text) {
    const frag = document.createDocumentFragment();
    text.split('\n').forEach((line, i) => {
      if (i) frag.appendChild(document.createElement('br'));
      if (line) frag.appendChild(document.createTextNode(line));
    });
    return frag;
  }

  const squash = (s) => String(s).replace(/\s+/g, ' ').trim();

  function applyRich(c, text) {
    if (!c.root || !c.root.isConnected) throw new Error('Das Eingabefeld gibt es nicht mehr. Bitte „Kopieren“ verwenden.');
    const range = c.range;
    if (squash(range.toString()) !== squash(c.text)) {
      throw new Error('Der markierte Text wurde inzwischen geändert. Bitte „Kopieren“ verwenden.');
    }
    c.root.focus({ preventScroll: true });
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    let ok = false;
    try { ok = document.execCommand('insertText', false, text); } catch (_) { ok = false; }
    if (!ok) {
      range.deleteContents();
      const frag = textFragment(text);
      const last = frag.lastChild;
      range.insertNode(frag);
      if (last) {
        const after = document.createRange();
        after.setStartAfter(last);
        after.collapse(true);
        sel.removeAllRanges();
        sel.addRange(after);
      }
      c.root.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, inputType: 'insertText', data: text }));
    }
  }

  // ---------- overlay ----------

  const CSS = `
:host { all: initial; }
.box { position: fixed; z-index: 2147483647; box-sizing: border-box; width: min(540px, calc(100vw - 16px));
  max-height: calc(100vh - 16px); overflow: auto; padding: 14px 16px; border-radius: 12px;
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: #1b1f24; background: #ffffff; border: 1px solid #c9d1db; box-shadow: 0 10px 32px rgba(0,0,0,.22); }
.head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.title { font-weight: 600; flex: 1; }
select, button, textarea { font: inherit; color: inherit; }
select { padding: 3px 6px; border-radius: 6px; border: 1px solid #c9d1db; background: #f6f8fa; }
.x { border: 0; background: transparent; font-size: 18px; line-height: 1; padding: 2px 6px; border-radius: 6px; cursor: pointer; }
.status { margin: 6px 0; color: #4b5563; }
.status.busy::before { content: ""; display: inline-block; width: 10px; height: 10px; margin-right: 8px; border-radius: 50%;
  border: 2px solid #2f6fe4; border-right-color: transparent; vertical-align: -1px; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .status.busy::before { animation: none; } }
.err { margin: 6px 0; padding: 8px 10px; border-radius: 8px; background: #fdecea; color: #8a1c1c; }
.label { font-size: 12px; color: #4b5563; margin: 8px 0 4px; }
.diff { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 30vh; overflow: auto; padding: 8px 10px;
  border-radius: 8px; background: #f6f8fa; border: 1px solid #e3e8ee; }
.rm { color: #b42318; background: #fde7e7; text-decoration: line-through; }
.add { color: #0f6b2f; background: #e3f6e8; text-decoration: none; }
textarea { box-sizing: border-box; width: 100%; min-height: 96px; max-height: 40vh; resize: vertical; padding: 8px 10px;
  border-radius: 8px; border: 1px solid #c9d1db; background: #ffffff; }
.row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; align-items: center; }
.btn { padding: 6px 12px; border-radius: 8px; border: 1px solid #c9d1db; background: #f6f8fa; cursor: pointer; }
.btn.primary { background: #2f6fe4; border-color: #2f6fe4; color: #ffffff; }
.btn:disabled { opacity: .5; cursor: default; }
.hint { font-size: 12px; color: #6b7280; margin-left: auto; }
:focus-visible { outline: 2px solid #2f6fe4; outline-offset: 2px; }
@media (prefers-color-scheme: dark) {
  .box { color: #e6e9ee; background: #1f242b; border-color: #3a424d; }
  select, .btn, .diff { background: #2a3038; border-color: #3a424d; }
  textarea { background: #171b20; border-color: #3a424d; }
  .status, .label { color: #a8b1bd; } .hint { color: #8b95a3; }
  .err { background: #4a1f1f; color: #ffd7d7; }
  .rm { color: #ffb4ab; background: #4a1f1f; } .add { color: #a6e3b5; background: #183824; }
  .btn.primary { background: #4c84ee; border-color: #4c84ee; color: #0b1020; }
}`;

  let ui = null; // current overlay state

  function el(tag, props, children) {
    const n = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (k === 'text') n.textContent = v;
        else if (k === 'class') n.className = v;
        else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v);
      }
    }
    for (const ch of children || []) if (ch) n.appendChild(ch);
    return n;
  }

  function addStyles(shadow) {
    try {
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(CSS);
      shadow.adoptedStyleSheets = [sheet];
      return;
    } catch (_) { /* fall back to a style element */ }
    const st = document.createElement('style');
    st.textContent = CSS;
    shadow.appendChild(st);
  }

  function close() {
    if (!ui) return;
    const { host, cap } = ui;
    ui.gen += 1;
    window.removeEventListener('resize', ui.onResize);
    host.remove();
    ui = null;
    try {
      if (cap && cap.kind === 'field' && cap.el.isConnected) cap.el.focus({ preventScroll: true });
      else if (cap && cap.root && cap.root.isConnected) cap.root.focus({ preventScroll: true });
    } catch (_) { /* ignore */ }
  }

  function position() {
    if (!ui) return;
    const b = ui.box.getBoundingClientRect();
    const p = placeBox(ui.cap ? ui.cap.rect : null, window.innerWidth, window.innerHeight, b.width, b.height);
    ui.box.style.left = `${p.left}px`;
    ui.box.style.top = `${p.top}px`;
  }

  function open(cap, key) {
    close();
    const host = document.createElement('spark-schreibhilfe');
    host.style.setProperty('all', 'initial', 'important');
    const shadow = host.attachShadow({ mode: 'closed' });
    addStyles(shadow);

    const artSel = el('select', { 'aria-label': 'Art der Verbesserung' });
    for (const a of C.ARTS) {
      const o = el('option', { value: a.key, text: a.label });
      if (a.key === key) o.selected = true;
      artSel.appendChild(o);
    }
    const status = el('div', { class: 'status', role: 'status', 'aria-live': 'polite' });
    const err = el('div', { class: 'err', role: 'alert' });
    const diffLabel = el('div', { class: 'label', text: 'Änderungen' });
    const diffBox = el('div', { class: 'diff' });
    const resLabel = el('label', { class: 'label', text: 'Ergebnis (bearbeitbar)' });
    const result = el('textarea', { spellcheck: 'true' });
    resLabel.htmlFor = 'r';
    result.id = 'r';
    const applyBtn = el('button', { class: 'btn primary', type: 'button', text: 'Übernehmen' });
    const copyBtn = el('button', { class: 'btn', type: 'button', text: 'Kopieren' });
    const cancelBtn = el('button', { class: 'btn', type: 'button', text: 'Abbrechen' });
    const optBtn = el('button', { class: 'btn', type: 'button', text: 'Einstellungen öffnen' });
    const hint = el('span', { class: 'hint' });
    const xBtn = el('button', { class: 'x', type: 'button', 'aria-label': 'Schließen', title: 'Schließen (Esc)', text: '×' });
    const title = el('div', { class: 'title', id: 't', text: 'Spark Schreibhilfe' });
    const box = el('div', { class: 'box', role: 'dialog', 'aria-labelledby': 't' }, [
      el('div', { class: 'head' }, [title, artSel, xBtn]),
      status, err, diffLabel, diffBox, resLabel, result,
      el('div', { class: 'row' }, [applyBtn, copyBtn, cancelBtn, optBtn, hint]),
    ]);
    shadow.appendChild(box);

    ui = { host, shadow, box, cap, gen: 0, onResize: () => position() };
    const st = ui;

    const show = (node, on) => { node.style.display = on ? '' : 'none'; };
    const setError = (text, withOptions) => {
      err.textContent = text || '';
      show(err, !!text);
      show(optBtn, !!withOptions);
    };

    if (cap && cap.kind === 'page') hint.textContent = 'Nicht bearbeitbar – nur Kopieren möglich.';
    else if (cap && cap.whole) hint.textContent = 'Ohne Markierung: ganzes Feld.';
    else hint.textContent = 'Strg+Enter übernimmt';

    async function go(k) {
      const a = C.artByKey(k);
      const myGen = ++st.gen;
      setError('');
      show(diffLabel, false); show(diffBox, false); show(resLabel, false); show(result, false);
      applyBtn.disabled = true; copyBtn.disabled = true;
      status.className = 'status busy';
      status.textContent = 'Der Spark schreibt …';
      show(status, true);
      position();
      let res;
      try {
        res = await api.runtime.sendMessage({ type: 'schreib-assist', text: cap.text, art: a.key });
      } catch (_) {
        res = { ok: false, code: 'net', detail: 'Die Erweiterung wurde neu geladen. Bitte die Seite neu laden.' };
      }
      if (ui !== st || st.gen !== myGen) return; // closed or superseded
      status.className = 'status';
      if (!res || !res.ok) {
        show(status, false);
        const needsPair = res && (res.code === 'auth' || res.code === 'unpaired');
        let msg = (res && res.detail) || 'Unbekannter Fehler.';
        if (res && res.code === 'auth') msg = 'Bitte in den Einstellungen neu koppeln. (Dieses Gerät ist beim Spark nicht mehr bekannt.)';
        setError(msg, needsPair);
        position();
        (needsPair ? optBtn : cancelBtn).focus();
        return;
      }
      const d = res.data;
      const changes = typeof d.changes === 'number' ? d.changes : null;
      if (d.text === cap.text || changes === 0) status.textContent = 'Keine Änderungen nötig.';
      else if (changes !== null) status.textContent = changes === 1 ? '1 Änderung' : `${changes} Änderungen`;
      else status.textContent = `${a.label} – fertig.`;
      if (d.diff && d.diff.length) {
        diffBox.replaceChildren(buildDiff(document, d.diff));
        show(diffLabel, true); show(diffBox, true);
      }
      result.value = d.text;
      show(resLabel, true); show(result, true);
      applyBtn.disabled = cap.kind === 'page';
      copyBtn.disabled = false;
      position();
      result.focus({ preventScroll: true });
      result.setSelectionRange(0, 0);
    }

    async function copy() {
      const t = result.value;
      try {
        await navigator.clipboard.writeText(t);
      } catch (_) {
        result.focus();
        result.select();
        try { document.execCommand('copy'); } catch (__) { /* ignore */ }
      }
      status.textContent = 'In die Zwischenablage kopiert.';
      show(status, true);
    }

    function apply() {
      if (applyBtn.disabled) return;
      const t = result.value;
      try {
        if (cap.kind === 'field') applyField(cap, t);
        else if (cap.kind === 'rich') applyRich(cap, t);
        else return;
        const c = cap;
        ui.cap = null; // do not move focus back over the inserted text
        close();
        if (c.kind === 'field') c.el.focus({ preventScroll: true });
      } catch (e) {
        setError(e && e.message ? e.message : 'Übernehmen ging nicht. Bitte „Kopieren“ verwenden.');
        position();
      }
    }

    artSel.addEventListener('change', () => go(artSel.value));
    applyBtn.addEventListener('click', apply);
    copyBtn.addEventListener('click', copy);
    cancelBtn.addEventListener('click', close);
    xBtn.addEventListener('click', close);
    optBtn.addEventListener('click', () => { api.runtime.sendMessage({ type: 'schreib-options' }).catch(() => {}); });

    // Keyboard: Esc closes, Ctrl/Cmd+Enter applies, Tab stays inside. Keys never reach page shortcuts.
    const stopKeys = (ev) => ev.stopPropagation();
    shadow.addEventListener('keydown', (ev) => {
      ev.stopPropagation();
      if (ev.key === 'Escape') { ev.preventDefault(); close(); return; }
      if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); apply(); return; }
      if (ev.key === 'Tab') {
        const items = [artSel, xBtn, result, applyBtn, copyBtn, cancelBtn, optBtn]
          .filter((n) => n.style.display !== 'none' && !n.disabled && n.offsetParent !== null);
        if (!items.length) return;
        const i = items.indexOf(shadow.activeElement);
        const next = ev.shiftKey ? (i <= 0 ? items.length - 1 : i - 1) : (i < 0 || i === items.length - 1 ? 0 : i + 1);
        ev.preventDefault();
        items[next].focus();
      }
    });
    shadow.addEventListener('keyup', stopKeys);
    shadow.addEventListener('keypress', stopKeys);
    window.addEventListener('resize', ui.onResize);

    (document.body || document.documentElement).appendChild(host);
    setError('');
    show(diffLabel, false); show(diffBox, false); show(resLabel, false); show(result, false);
    applyBtn.disabled = true; copyBtn.disabled = true;
    position();
    artSel.focus({ preventScroll: true });

    if (!cap) {
      show(status, false);
      setError('Bitte zuerst Text markieren (oder in ein Textfeld klicken) und dann noch einmal versuchen.');
      cancelBtn.focus();
      return;
    }
    if (cap.text.length > C.MAX_TEXT) {
      show(status, false);
      setError(`Der Text ist zu lang (${cap.text.length} Zeichen, höchstens ${C.MAX_TEXT}).`);
      cancelBtn.focus();
      return;
    }
    go(key);
  }

  function start(key) {
    const k = C.artByKey(key) ? key : C.DEFAULT_ART;
    const previous = ui ? ui.cap : null;
    close();
    open(capture() || previous, k);
  }

  globalThis.__sparkSchreib = Object.freeze({ probe, start, util: { buildDiff, placeBox, spliceField } });
})();
