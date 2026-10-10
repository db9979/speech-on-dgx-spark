// ---------------------------------------------------------------- Spark-Begleiter (begleiter.py, tools/begleiter)
// Ich → Begleiter: the own switch, the programs for Windows and Mac, "Gerät koppeln" (setup line), and per paired
// device which parts it has (writing help, questions, dictation, notes, state, Notaus button) plus the writing
// help's defaults. A change reaches the program with its next poll. Hotkeys are set in the program itself.
let DESK_ON=false;
const DESK_PARTS=[['write',['Schreibhilfe','Writing help'],['Markierten Text verbessern (Tastenkürzel).','Improve marked text (hotkey).']],
  ['ask',['Frag Spark','Ask Spark'],['Fenster für Fragen, per Tastenkürzel.','A window for questions, by hotkey.']],
  ['dictate',['Diktieren','Dictation'],['Sprechen, der Text landet an der Schreibmarke. Nimmt nur auf, solange du es willst.','Speak, the text lands at the cursor. Records only while you want it to.']],
  ['notes',['Meldungen','Notes'],['Hinweise des Spark als Systemmitteilung.','The Spark\'s notes as system notifications.']],
  ['status',['Zustandspunkt','State dot'],['Das Symbol zeigt, ob der Spark erreichbar ist oder ein Notaus gilt.','The icon shows whether the Spark answers or a Notaus holds.']],
  ['notaus',['Mein Notaus','My kill switch'],['Knopf, der dein Profil sofort stilllegt. Aufheben nur hier im Browser.','A button that stops your profile at once. Lifting only here in the browser.']]];
function deskTime(s){return new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',year:'numeric'})}
async function showDesk(){const box=$('deskbox');if(!box)return;if(!PROFILE||!DESK_ON){box.innerHTML='';return}
  let d={on:false,allowed:{},devices:[],minutes:10,downloads:{},arts:[],langs:[]};try{d=await (await api('/api/profile/desk')).json()}catch{}
  const tt=a=>t(a[0],a[1]);
  const dev=x=>{const c=x.cfg;
    const parts=DESK_PARTS.map(([k,n,h])=>`<div class="setrow"><div class="lbl"><b>${esc(tt(n))}</b><span>${esc(d.allowed[k]?tt(h):k==='write'?t('Erst die Schreibhilfe einschalten (Funktionen und Ich → Schreibhilfe).','Turn on the writing help first (Features and Me → Writing help).'):'')}</span></div><label class="tgl"><input type="checkbox" data-dk="${esc(k)}"${c.parts[k]?' checked':''}${d.allowed[k]?'':' disabled'}><i></i></label></div>`).join('');
    const arts=d.arts.map(a=>`<label class="chk"><input type="checkbox" data-dart="${esc(a.id)}"${c.write.arts.includes(a.id)?' checked':''}> ${esc(L==='en'?a.en:a.de)}</label>`).join(' ');
    const opt=(list,sel)=>list.map(a=>`<option value="${esc(a.id)}"${a.id===sel?' selected':''}>${esc(L==='en'?a.en:a.de)}</option>`).join('');
    return `<div class="card" data-desk="${esc(x.id)}"><div class="rowin"><b>${esc(x.name.replace(/^Begleiter /,''))}</b><span class="mut">${esc(x.online?t('verbunden','connected'):t('nicht verbunden','not connected'))} · ${esc(t('seit ','since ')+(x.created?deskTime(x.created):'–'))}</span></div>
      ${parts}
      <details><summary>${esc(t('Schreibhilfe: Voreinstellungen','Writing help: defaults'))}</summary>
        <div class="two2"><div><label>${esc(t('Art','Kind'))}</label><select data-dw="art">${opt(d.arts,c.write.art)}</select></div>
        <div><label>${esc(t('Sprache beim Übersetzen','Language for translating'))}</label><select data-dw="sprache">${opt(d.langs,c.write.sprache)}</select></div></div>
        <label>${esc(t('Fester Wunsch (z. B. „mit Du“)','Fixed wish (e.g. "informal")'))}</label><input data-dw="wunsch" maxlength="300" value="${esc(c.write.wunsch)}">
        <label>${esc(t('Im Menü','In the menu'))}</label><div>${arts}</div>
        <div class="setrow"><div class="lbl"><b>${esc(t('Vorschlag erst zeigen','Show the suggestion first'))}</b><span>${esc(t('Aus: der verbesserte Text ersetzt die Markierung sofort.','Off: the improved text replaces the selection at once.'))}</span></div><label class="tgl"><input type="checkbox" data-dw="preview"${c.write.preview?' checked':''}><i></i></label></div>
      </details>
      <div class="two2"><div><label>${esc(t('Diktat-Sprache','Dictation language'))}</label><select data-dd="sprache"><option value="auto">${esc(t('Automatisch','Automatic'))}</option>${opt(d.langs,c.dictate.sprache)}</select></div>
      <div class="setrow"><div class="lbl"><b>${esc(t('Mit dem Rechner starten','Start with the computer'))}</b></div><label class="tgl"><input type="checkbox" data-da="1"${c.autostart?' checked':''}><i></i></label></div></div>
      <div class="row"><button class="b p" type="button" data-dsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button><button class="b" type="button" data-ddel="${esc(x.id)}">${esc(t('Entfernen','Remove'))}</button></div>
      <div class="fh" data-dmsg="${esc(x.id)}"></div></div>`};
  box.innerHTML=`<div class="intro">${esc(t('Ein kleines Programm in der Windows-Taskleiste und der Mac-Menüleiste: Schreibhilfe, Frag Spark, Diktieren, Meldungen, Zustand und dein Notaus, jedes mit eigenem Tastenkürzel. Was ein Gerät darf, stellst du hier ein; es gilt beim nächsten Abruf (spätestens nach einer halben Minute).','A small program in the Windows taskbar and the Mac menu bar: writing help, Ask Spark, dictation, notes, state and your kill switch, each with its own hotkey. What a device may do is set here; it applies with its next check (within half a minute).'))}</div>
    ${xsw('desk_on',t('Spark-Begleiter für mich','Spark companion for me'),t('Aus: alle gekoppelten Geräte ruhen.','Off: all paired devices rest.'))}
    ${d.on?`<ul class="facts">
      <li><span><b>Windows (x64 und ARM)</b><br><small class="mut">${esc(t('Nicht signiert: beim ersten Start „Weitere Informationen“ → „Trotzdem ausführen“.','Not signed: at first start "More info" → "Run anyway".'))}</small></span><a class="b" href="${esc(d.downloads.windows||'')}" target="_blank" rel="noopener">${esc(t('Zur Seite','Open page'))}</a></li>
      <li><span><b>Mac</b><br><small class="mut">${esc(t('Beim ersten Start Rechtsklick → Öffnen. Für Tastenkürzel mit Markieren fragt der Mac einmal nach „Bedienungshilfen“.','At first start right-click → Open. For hotkeys that mark text the Mac asks once for "Accessibility".'))}</small></span><a class="b" href="${esc(d.downloads.mac||'')}" target="_blank" rel="noopener">${esc(t('Zur Seite','Open page'))}</a></li></ul>
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="dkpair">${esc(t('Gerät koppeln','Pair a device'))}</button></div>
    <div id="dksetupbox" hidden><label>${esc(t('Einrichtungszeile','Setup line'))}</label><div class="rowin"><code id="dksetup" style="overflow-wrap:anywhere"></code><button class="b" type="button" id="dksetupcopy">${esc(t('Kopieren','Copy'))}</button></div></div>
    <div class="fh" id="dkmsg"></div>
    <label>${esc(t('Gekoppelte Geräte','Paired devices'))}</label>
    ${d.devices.map(dev).join('')||`<div class="fh mut">${esc(t('Noch keins.','None yet.'))}</div>`}`:''}`;
  xbind(box,showDesk);
  if(!d.on)return;
  $('dkpair').onclick=async()=>{xmsg('dkmsg','…');
    try{const r=await (await api('/api/profile/desk/pair',xjson('POST',{base:location.origin}))).json();
      $('dksetup').textContent=r.setup;$('dksetupbox').hidden=false;
      xmsg('dkmsg',t('Diese Zeile ins Programm einfügen (gilt '+r.minutes+' Minuten, einmal).','Paste this line into the program (works '+r.minutes+' minutes, once).'))}
    catch(e){xmsg('dkmsg',e.message,true)}};
  $('dksetupcopy').onclick=()=>copyString($('dksetup').textContent,$('dksetupcopy'));
  box.querySelectorAll('[data-dsave]').forEach(b=>b.onclick=async()=>{const id=b.dataset.dsave,c=box.querySelector(`[data-desk="${CSS.escape(id)}"]`);
    const parts={};c.querySelectorAll('[data-dk]').forEach(i=>parts[i.dataset.dk]=i.checked);
    const w={};c.querySelectorAll('[data-dw]').forEach(i=>w[i.dataset.dw]=i.type==='checkbox'?i.checked:i.value);
    w.arts=[...c.querySelectorAll('[data-dart]')].filter(i=>i.checked).map(i=>i.dataset.dart);
    const cfg={parts,write:w,dictate:{sprache:c.querySelector('[data-dd]').value},autostart:c.querySelector('[data-da]').checked};
    try{await api('/api/profile/desk/devices/'+encodeURIComponent(id),xjson('PUT',{cfg}));
      const m=c.querySelector(`[data-dmsg="${CSS.escape(id)}"]`);if(m)m.textContent=t('Gespeichert. Das Gerät übernimmt es beim nächsten Abruf.','Saved. The device takes it with its next check.')}
    catch(e){xmsg('dkmsg',e.message,true)}});
  box.querySelectorAll('[data-ddel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Gerät entfernen? Sein Schlüssel gilt dann nicht mehr.','Remove the device? Its key stops working.')))return;
    try{await api('/api/profile/desk/devices/'+encodeURIComponent(b.dataset.ddel),{method:'DELETE'});showDesk()}catch(e){xmsg('dkmsg',e.message,true)}})}
