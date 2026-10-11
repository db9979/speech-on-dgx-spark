// ---------------------------------------------------------------- Spark-Begleiter (begleiter.py, tools/begleiter)
// Ich → Begleiter: the own switch, the programs for Windows and Mac, "Gerät koppeln" (setup line), and per paired
// device which parts it has (writing help, questions, dictation, notes, state, Notaus button) plus the writing
// help's defaults. A change reaches the program with its next poll. Hotkeys are set in the program itself.
let DESK_ON=false;
const DESK_COFFEE='https://buymeacoffee.com/zquu1xu570';
const DESK_PARTS=[['write',['Schreibhilfe','Writing help'],['Markierten Text verbessern (Tastenkürzel).','Improve marked text (hotkey).']],
  ['ask',['Frag Spark','Ask Spark'],['Fenster für Fragen, per Tastenkürzel.','A window for questions, by hotkey.']],
  ['dictate',['Diktieren','Dictation'],['Sprechen, der Text landet an der Schreibmarke. Nimmt nur auf, solange du es willst.','Speak, the text lands at the cursor. Records only while you want it to.']],
  ['notes',['Meldungen','Notes'],['Hinweise des Spark als Systemmitteilung.','The Spark\'s notes as system notifications.']],
  ['status',['Zustandspunkt','State dot'],['Das Symbol zeigt, ob der Spark erreichbar ist oder ein Notaus gilt.','The icon shows whether the Spark answers or a Notaus holds.']],
  ['notaus',['Mein Notaus','My kill switch'],['Knopf, der dein Profil sofort stilllegt. Aufheben nur hier im Browser.','A button that stops your profile at once. Lifting only here in the browser.']],
  ['files',['Rechtsklick auf Dateien','Right-click on files'],['„Mit Spark“ im Explorer und Finder: zusammenfassen, übersetzen, erklären, ins Wissen übernehmen.','"With Spark" in Explorer and Finder: summarize, translate, explain, add to knowledge.']],
  ['screen',['Bildschirm fragen','Ask about the screen'],['Tastenkürzel, Bereich aufziehen, fragen. Das Bild wird gelesen und nicht aufbewahrt.','Hotkey, drag a region, ask. The picture is read and not kept.']],
  ['context',['App erkennen','Know the app'],['Die Schreibhilfe erfährt, aus welcher Art Programm der Text kommt (Mail, Word, Chat …), nie Namen oder Fenstertitel.','The writing help learns which kind of program the text comes from (mail, Word, chat …), never names or window titles.']],
  ['mail',['Antwort entwerfen','Draft a reply'],['Zur offenen Mail in Outlook (Windows) oder Apple Mail eine Antwort als Entwurf. Gesendet wird nie.','A reply draft to the open mail in Outlook (Windows) or Apple Mail. Never sent.']],
  ['folder',['Ordner Spark-Wissen','Spark knowledge folder'],['Was du in den Ordner „Spark-Wissen“ legst, kommt in deine Dokumente.','What you put into the folder "Spark-Wissen" goes into your documents.']],
  ['actions',['Knöpfe in Meldungen','Buttons in notes'],['Antworten, Später oder Panel öffnen direkt in der Mitteilung.','Reply, Later or Open panel right in the notification.']],
  ['act',['Am PC handeln','Act on the PC'],['Der Spark darf eine Seite oder ein freigegebenes Programm öffnen, Musik und Lautstärke steuern oder sperren. Jedes Mal fragt der Rechner vorher.','The Spark may open a page or a released program, control music and volume or lock. The computer asks every time.']],
  ['wake',['Weckwort am PC','Wake word on the PC'],['„Hey Spark“ über das Mikrofon des Rechners. Hört nur, solange es an ist; das Symbol zeigt es.','"Hey Spark" through the computer\'s microphone. Listens only while on; the icon shows it.']],
  ['speak',['Vorlesen','Read aloud'],['Markierten Text in deiner Spark-Stimme vorlesen (Strg+Alt+L, Mac ⌥⌘L).','Read marked text aloud in your Spark voice (Ctrl+Alt+L, Mac ⌥⌘L).']],
  ['inbox',['Vom Handy auf den PC','From the phone to the PC'],['Text, Link oder Datei vom Spark auf diesen Rechner: Text in die Zwischenablage, Links nur nach Rückfrage, Dateien in „Downloads/Vom Spark“.','Text, link or file from the Spark to this computer: text into the clipboard, links only after asking, files into "Downloads/Vom Spark".']],
  ['agenda',['Termine im Begleiter','Appointments in the companion'],['Die nächsten Termine und Erinnerungen im Begleiter, Hinweis 10 Minuten vorher; „In 20 Min erinnern“ an Meldungen.','The next appointments and reminders in the companion, a note 10 minutes before; "Remind me in 20 min" on notes.']],
  ['quiet',['Nicht stören erkennen','Recognise do not disturb'],['Bei Anruf (Mikrofon oder Kamera in Gebrauch) oder Präsentation warten Meldungen; danach kommt eine Zusammenfassung.','During a call (microphone or camera in use) or a presentation notes wait; a summary follows afterwards.']],
  ['meeting',['Besprechung mitschreiben','Write along in meetings'],['Nur auf Klick, mit sichtbarer Leiste: Zusammenfassung und Aufgaben danach. Alle Beteiligten müssen einverstanden sein.','Only on a click, with a visible bar: summary and tasks afterwards. Everybody taking part must agree.']],
  ['home',['Smart-Home-Knöpfe','Smart home buttons'],['Knöpfe für Licht, Schalter und Szenen deines Home Assistant im Begleiter; das Codewort gilt wie bei der Stimme.','Buttons for lights, switches and scenes of your Home Assistant in the companion; the code word applies as by voice.']],
  ['daily',['Tagesstart und Feierabend','Start and end of the day'],['Morgens dein Tagesüberblick, abends die Termine von morgen und was offen ist.','In the morning your daily overview, in the evening tomorrow\'s appointments and what is open.']]];
// the parts of an open device in small sections (Dominik 2026-10-11: clear with several devices)
const DESK_GROUPS=[['Schreiben und Fragen','Writing and asking',['write','ask','dictate','speak','context','mail']],
  ['Am Rechner','On the computer',['files','screen','folder','act','wake','inbox']],
  ['Meldungen und Tag','Notes and the day',['notes','actions','agenda','daily','quiet','meeting']],
  ['Zuhause','Home',['home']],['Zustand und Sicherheit','State and safety',['status','notaus']]];
let deskOpen=null;try{deskOpen=localStorage.getItem('deskOpen')}catch{}
const deskWhy=(k,d)=>k==='write'||k==='context'||k==='mail'?t('Erst die Schreibhilfe einschalten (Funktionen und Ich → Schreibhilfe).','Turn on the writing help first (Features and Me → Writing help).'):
  k==='folder'?t('Erst eigene Dokumente einschalten.','Turn on own documents first.'):k==='act'?t('Erst unter Funktionen → Spark-Begleiter „Darf am PC handeln“ einschalten.','Turn on "May act on the PC" under Features → Spark companion first.'):
  k==='meeting'?t('Erst unter Funktionen → Spark-Begleiter „Besprechungen mitschreiben“ einschalten.','Turn on "Write along in meetings" under Features → Spark companion first.'):
  k==='home'?t('Erst Home Assistant verbinden (Funktionen und Ich → Home Assistant).','Connect Home Assistant first (Features and Me → Home Assistant).'):'';
// a smart home button row: name and one of the entities the profile may switch (GET /api/profile/desk/entities)
const deskBtn=(b,ents)=>`<div class="two2" data-dbtn><div><input data-bn maxlength="40" placeholder="${esc(t('Name','Name'))}" value="${esc(b.name||'')}"></div><div><select data-be><option value="">${esc(t('– Gerät wählen –','– pick a device –'))}</option>${ents.map(e=>`<option value="${esc(e.entity)}" data-kind="${esc(e.kind)}"${e.entity===b.entity?' selected':''}>${esc(e.name)} (${esc(e.entity)})</option>`).join('')}${b.entity&&!ents.some(e=>e.entity===b.entity)?`<option value="${esc(b.entity)}" data-kind="${esc(b.kind)}" selected>${esc(b.entity)}</option>`:''}</select></div></div>`;
function deskTime(s){return new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',year:'numeric'})}
async function showDesk(){const box=$('deskbox');if(!box)return;if(!PROFILE||!DESK_ON){box.innerHTML='';return}
  let d={on:false,allowed:{},devices:[],minutes:10,downloads:{},arts:[],langs:[]};try{d=await (await api('/api/profile/desk')).json()}catch{}
  let ents=[];if(d.allowed&&d.allowed.home&&d.devices.length){try{ents=(await (await api('/api/profile/desk/entities')).json()).entities||[]}catch{}}
  const tt=a=>t(a[0],a[1]);
  let ndev=0;
  const dev=x=>{const c=x.cfg,inst=x.installed||[],dl='dkinst'+(ndev++);
    const row=([k,n,h])=>`<div class="setrow"><div class="lbl"><b>${esc(tt(n))}</b><span>${esc(d.allowed[k]?tt(h):deskWhy(k,d))}</span></div><label class="tgl"><input type="checkbox" data-dk="${esc(k)}"${c.parts[k]?' checked':''}${d.allowed[k]?'':' disabled'}><i></i></label></div>`;
    const parts=DESK_GROUPS.map(([de,en,keys])=>`<div class="dkgrp"><h4>${esc(t(de,en))}</h4>${keys.map(k=>row(DESK_PARTS.find(p=>p[0]===k))).join('')}</div>`).join('');
    const on=DESK_PARTS.filter(([k])=>c.parts[k]&&d.allowed[k]).length,others=d.devices.filter(o=>o.id!==x.id);
    const arts=d.arts.map(a=>`<label class="chk"><input type="checkbox" data-dart="${esc(a.id)}"${c.write.arts.includes(a.id)?' checked':''}> ${esc(L==='en'?a.en:a.de)}</label>`).join(' ');
    const opt=(list,sel)=>list.map(a=>`<option value="${esc(a.id)}"${a.id===sel?' selected':''}>${esc(L==='en'?a.en:a.de)}</option>`).join('');
    return `<div class="card dkdev" data-desk="${esc(x.id)}"><button type="button" class="dkhead" data-dopen="${esc(x.id)}" aria-expanded="false">
      <span class="dkkind">${esc(x.kind==='mac'?'Mac':'Windows')}</span><span class="dkname"><b>${esc(x.name.replace(/^Begleiter (Windows|Mac) · /,''))}</b>
      <small class="mut"><i class="dkdot${x.online?' on':''}"></i>${esc(x.online?t('verbunden','connected'):t('nicht verbunden','not connected')+(x.last?' · '+t('zuletzt ','last ')+deskTime(x.last):''))}${x.version?' · '+esc(x.version):''}${x.update?' · <span class="dkupd">'+esc(t('Update da','Update ready'))+'</span>':''}</small>
      <small class="mut">${esc(t(on+' von '+DESK_PARTS.length+' Teilen an',on+' of '+DESK_PARTS.length+' parts on'))}</small></span><span class="dkchev" aria-hidden="true">›</span></button>
      <div class="dkbody" hidden>
      ${others.length?`<div class="dkcopy"><label>${esc(t('Einstellungen übernehmen von','Take the settings of'))}</label><select data-dcopy="${esc(x.id)}"><option value="">${esc(t('– Gerät wählen –','– pick a device –'))}</option>${others.map(o=>`<option value="${esc(o.id)}">${esc(o.name.replace(/^Begleiter /,''))}</option>`).join('')}</select></div>`:''}
      ${parts}
      <details><summary>${esc(t('Schreibhilfe: Voreinstellungen','Writing help: defaults'))}</summary>
        <div class="two2"><div><label>${esc(t('Art','Kind'))}</label><select data-dw="art">${opt(d.arts,c.write.art)}</select></div>
        <div><label>${esc(t('Sprache beim Übersetzen','Language for translating'))}</label><select data-dw="sprache">${opt(d.langs,c.write.sprache)}</select></div></div>
        <label>${esc(t('Fester Wunsch (z. B. „mit Du“)','Fixed wish (e.g. "informal")'))}</label><input data-dw="wunsch" maxlength="300" value="${esc(c.write.wunsch)}">
        <label>${esc(t('Im Menü','In the menu'))}</label><div>${arts}</div>
        <div class="setrow"><div class="lbl"><b>${esc(t('Vorschlag erst zeigen','Show the suggestion first'))}</b><span>${esc(t('Aus: der verbesserte Text ersetzt die Markierung sofort.','Off: the improved text replaces the selection at once.'))}</span></div><label class="tgl"><input type="checkbox" data-dw="preview"${c.write.preview?' checked':''}><i></i></label></div>
      </details>
      ${d.allowed.act?`<details><summary>${esc(t('Am PC handeln: freigegebene Programme','Act on the PC: released programs'))}</summary>
        <div class="fh">${esc(t('Nur diese Programme darf der Spark öffnen, je mit Rückfrage am Rechner. Name, wie du ihn sagst; Pfad, wie der Rechner das Programm startet (z. B. C:\\Windows\\notepad.exe oder /Applications/Safari.app).','Only these programs may the Spark open, each with a question at the computer. Name as you say it; path as the computer starts it (e.g. C:\\Windows\\notepad.exe or /Applications/Safari.app).'))}</div>
        <label>${esc(t('Programm suchen','Find a program'))}</label>${inst.length?`<input data-dfind list="${dl}" maxlength="40" placeholder="${esc(t('Name eintippen, dann wählen','Type a name, then pick'))}"><datalist id="${dl}">${inst.map(a=>`<option value="${esc(a.name)}"></option>`).join('')}</datalist>`:`<div class="fh mut">${esc(t('Liste kommt vom Rechner, sobald der Begleiter läuft.','The list comes from the computer once the companion runs.'))}</div>`}
        <div data-dapps>${(c.act.apps.length?c.act.apps:[{name:'',path:''}]).map(a=>`<div class="two2" data-dapp><div><input data-an maxlength="40" placeholder="${esc(t('Name','Name'))}" value="${esc(a.name)}"></div><div><input data-ap maxlength="300" placeholder="${esc(t('Pfad','Path'))}" value="${esc(a.path)}"></div></div>`).join('')}</div>
        <button class="b" type="button" data-daddapp="${esc(x.id)}">${esc(t('Weiteres Programm','Another program'))}</button></details>`:''}
      ${d.allowed.home?`<details><summary>${esc(t('Smart-Home-Knöpfe','Smart home buttons'))}</summary>
        <div class="fh">${esc(t('Bis zu 12 Knöpfe im Begleiter: Licht, Schalter, Lüfter, Klima (an/aus) und Szenen deines Home Assistant. Schlösser, Alarm und Skripte nie. Mit Codewort fragt der Begleiter danach.','Up to 12 buttons in the companion: lights, switches, fans, climate (on/off) and scenes of your Home Assistant. Never locks, alarms or scripts. With a code word the companion asks for it.'))}</div>
        <div data-dbtns>${(c.home.buttons.length?c.home.buttons:[{}]).map(b=>deskBtn(b,ents)).join('')}</div>
        <button class="b" type="button" data-daddbtn="${esc(x.id)}">${esc(t('Weiterer Knopf','Another button'))}</button></details>`:''}
      ${d.allowed.inbox&&c.parts.inbox?`<details><summary>${esc(t('An PC schicken','Send to the PC'))}</summary>
        <div class="fh">${esc(t('Text kommt dort in die Zwischenablage, ein Link wird nach Rückfrage geöffnet (nur http/https), eine Datei (höchstens 20 MB) landet in „Downloads/Vom Spark“. Wartet bis zu 24 Stunden.','Text goes into the clipboard there, a link is opened after asking (only http/https), a file (at most 20 MB) lands in "Downloads/Vom Spark". Waits up to 24 hours.'))}</div>
        <div class="two2"><div><label>${esc(t('Was','What'))}</label><select data-skind><option value="text">${esc(t('Text','Text'))}</option><option value="link">${esc(t('Link','Link'))}</option><option value="file">${esc(t('Datei','File'))}</option></select></div>
        <div><label>${esc(t('Datei','File'))}</label><input type="file" data-sfile></div></div>
        <textarea data-stext rows="3" maxlength="10000" placeholder="${esc(t('Text oder https://…','Text or https://…'))}"></textarea>
        <div class="row"><button class="b" type="button" data-dsend="${esc(x.id)}">${esc(t('An PC schicken','Send to the PC'))}</button></div></details>`:''}
      <details><summary>${esc(t('Diktat und Start','Dictation and start'))}</summary>
      <div class="two2"><div><label>${esc(t('Diktat-Sprache','Dictation language'))}</label><select data-dd="sprache"><option value="auto">${esc(t('Automatisch','Automatic'))}</option>${opt(d.langs,c.dictate.sprache)}</select></div>
      <div class="setrow"><div class="lbl"><b>${esc(t('Mit dem Rechner starten','Start with the computer'))}</b></div><label class="tgl"><input type="checkbox" data-da="1"${c.autostart?' checked':''}><i></i></label></div></div></details>
      <div class="row"><button class="b p" type="button" data-dsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button><button class="b" type="button" data-ddel="${esc(x.id)}">${esc(t('Entfernen','Remove'))}</button></div>
      <div class="fh" data-dmsg="${esc(x.id)}"></div></div></div>`};
  box.innerHTML=`<div class="intro">${esc(t('Ein kleines Programm in der Windows-Taskleiste und der Mac-Menüleiste: Schreibhilfe, Frag Spark, Diktieren, Meldungen, Zustand und dein Notaus, jedes mit eigenem Tastenkürzel. Was ein Gerät darf, stellst du hier ein; es gilt beim nächsten Abruf (spätestens nach einer halben Minute).','A small program in the Windows taskbar and the Mac menu bar: writing help, Ask Spark, dictation, notes, state and your kill switch, each with its own hotkey. What a device may do is set here; it applies with its next check (within half a minute).'))}</div>
    ${xsw('desk_on',t('Spark-Begleiter für mich','Spark companion for me'),t('Aus: alle gekoppelten Geräte ruhen.','Off: all paired devices rest.'))}
    ${d.on?`<ul class="facts">
      <li><span><b>Windows (x64 und ARM)</b><br><small class="mut">${esc(t('Nicht signiert: beim ersten Start „Weitere Informationen“ → „Trotzdem ausführen“.','Not signed: at first start "More info" → "Run anyway".'))}</small></span><a class="b" href="${esc(d.downloads.windows||'')}" target="_blank" rel="noopener">${esc(t('Zur Seite','Open page'))}</a></li>
      <li><span><b>Mac</b><br><small class="mut">${esc(t('Beim ersten Start Rechtsklick → Öffnen. Für Tastenkürzel mit Markieren fragt der Mac einmal nach „Bedienungshilfen“.','At first start right-click → Open. For hotkeys that mark text the Mac asks once for "Accessibility".'))}</small></span><a class="b" href="${esc(d.downloads.mac||'')}" target="_blank" rel="noopener">${esc(t('Zur Seite','Open page'))}</a></li></ul>
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="dkpair">${esc(t('Gerät koppeln','Pair a device'))}</button></div>
    <div id="dksetupbox" hidden><label>${esc(t('Einrichtungszeile','Setup line'))}</label><div class="rowin"><code id="dksetup" style="overflow-wrap:anywhere"></code><button class="b" type="button" id="dksetupcopy">${esc(t('Kopieren','Copy'))}</button></div></div>
    <div class="fh" id="dkmsg"></div>
    <label>${esc(t('Gekoppelte Geräte','Paired devices'))}</label>
    ${d.devices.map(dev).join('')||`<div class="fh mut">${esc(t('Noch keins.','None yet.'))}</div>`}
    <div class="fh">${esc(t('Neue Versionen holt der Spark selbst; das Programm zeigt sie an und installiert erst nach deinem Klick. Der Spark ist kostenlos: ','The Spark fetches new versions itself; the program shows them and installs only after your click. The Spark is free: '))}<a href="${DESK_COFFEE}" target="_blank" rel="noopener">☕ ${esc(t('Spark unterstützen','Support Spark'))}</a></div>`:''}`;
  xbind(box,showDesk);
  if(!d.on)return;
  $('dkpair').onclick=async()=>{xmsg('dkmsg','…');
    try{const r=await (await api('/api/profile/desk/pair',xjson('POST',{base:location.origin}))).json();
      $('dksetup').textContent=r.setup;$('dksetupbox').hidden=false;
      xmsg('dkmsg',t('Diese Zeile ins Programm einfügen (gilt '+r.minutes+' Minuten, einmal).','Paste this line into the program (works '+r.minutes+' minutes, once).'))}
    catch(e){xmsg('dkmsg',e.message,true)}};
  $('dksetupcopy').onclick=()=>copyString($('dksetup').textContent,$('dksetupcopy'));
  // one device open at a time (remembered per browser); with a single device it is open at once
  const openDev=id=>{box.querySelectorAll('.dkdev').forEach(c=>{const me=c.dataset.desk===id;c.querySelector('.dkbody').hidden=!me;
      c.classList.toggle('open',me);c.querySelector('.dkhead').setAttribute('aria-expanded',me?'true':'false')});
    deskOpen=id;try{id?localStorage.setItem('deskOpen',id):localStorage.removeItem('deskOpen')}catch{}};
  box.querySelectorAll('[data-dopen]').forEach(b=>b.onclick=()=>openDev(deskOpen===b.dataset.dopen&&d.devices.length>1?null:b.dataset.dopen));
  if(d.devices.length===1)openDev(d.devices[0].id);else if(d.devices.some(x=>x.id===deskOpen))openDev(deskOpen);
  // "Einstellungen übernehmen von": fills the open form only; programs and buttons only from the same kind of computer
  box.querySelectorAll('[data-dcopy]').forEach(sel=>sel.onchange=()=>{const src=d.devices.find(o=>o.id===sel.value);if(!src)return;
    const me=d.devices.find(o=>o.id===sel.dataset.dcopy),c=box.querySelector(`[data-desk="${CSS.escape(me.id)}"]`),sc=src.cfg;
    c.querySelectorAll('[data-dk]').forEach(i=>{if(!i.disabled)i.checked=!!sc.parts[i.dataset.dk]});
    c.querySelectorAll('[data-dw]').forEach(i=>{const v=sc.write[i.dataset.dw];if(i.type==='checkbox')i.checked=!!v;else if(v!=null)i.value=v});
    c.querySelectorAll('[data-dart]').forEach(i=>i.checked=sc.write.arts.includes(i.dataset.dart));
    const dd=c.querySelector('[data-dd]');if(dd)dd.value=sc.dictate.sprache;const da=c.querySelector('[data-da]');if(da)da.checked=!!sc.autostart;
    if(src.kind===me.kind){const l=c.querySelector('[data-dapps]');if(l&&sc.act.apps.length){const tpl=l.firstElementChild;
        l.replaceChildren(...sc.act.apps.map(a=>{const r=tpl.cloneNode(true);r.querySelector('[data-an]').value=a.name;r.querySelector('[data-ap]').value=a.path;return r}))}
      const bl=c.querySelector('[data-dbtns]');if(bl&&sc.home.buttons.length){const tpl=bl.firstElementChild;
        bl.replaceChildren(...sc.home.buttons.map(b=>{const r=tpl.cloneNode(true);r.querySelector('[data-bn]').value=b.name;r.querySelector('[data-be]').value=b.entity;return r}))}}
    const m=c.querySelector(`[data-dmsg="${CSS.escape(me.id)}"]`);if(m)m.textContent=t('Übernommen, noch nicht gespeichert.','Taken over, not saved yet.');sel.value=''});
  box.querySelectorAll('[data-dsave]').forEach(b=>b.onclick=async()=>{const id=b.dataset.dsave,c=box.querySelector(`[data-desk="${CSS.escape(id)}"]`);
    const parts={};c.querySelectorAll('[data-dk]').forEach(i=>parts[i.dataset.dk]=i.checked);
    const w={};c.querySelectorAll('[data-dw]').forEach(i=>w[i.dataset.dw]=i.type==='checkbox'?i.checked:i.value);
    w.arts=[...c.querySelectorAll('[data-dart]')].filter(i=>i.checked).map(i=>i.dataset.dart);
    const apps=[...c.querySelectorAll('[data-dapp]')].map(r=>({name:r.querySelector('[data-an]').value.trim(),path:r.querySelector('[data-ap]').value.trim()})).filter(a=>a.name&&a.path);
    const buttons=[...c.querySelectorAll('[data-dbtn]')].map((r,i)=>{const sel=r.querySelector('[data-be]'),o=sel.selectedOptions[0];
      return {id:'b'+(i+1),name:r.querySelector('[data-bn]').value.trim(),entity:sel.value,kind:o?o.dataset.kind||'':''}}).filter(b=>b.name&&b.entity);
    const cfg={parts,write:w,dictate:{sprache:c.querySelector('[data-dd]').value},autostart:c.querySelector('[data-da]').checked,act:{apps},home:{buttons}};
    try{await api('/api/profile/desk/devices/'+encodeURIComponent(id),xjson('PUT',{cfg}));
      const m=c.querySelector(`[data-dmsg="${CSS.escape(id)}"]`);if(m)m.textContent=t('Gespeichert. Das Gerät übernimmt es beim nächsten Abruf.','Saved. The device takes it with its next check.')}
    catch(e){xmsg('dkmsg',e.message,true)}});
  box.querySelectorAll('[data-daddapp]').forEach(b=>b.onclick=()=>{const l=b.parentNode.querySelector('[data-dapps]');if(l.children.length>=20)return;
    const r=l.firstElementChild.cloneNode(true);r.querySelectorAll('input').forEach(i=>i.value='');l.appendChild(r)});
  // picking an installed program fills the first empty row (or a new one) with its name and path; typing stays possible
  box.querySelectorAll('[data-dfind]').forEach(inp=>inp.onchange=()=>{const id=inp.closest('[data-desk]').dataset.desk;
    const x=d.devices.find(v=>v.id===id),a=x&&(x.installed||[]).find(v=>v.name===inp.value);if(!a)return;
    const l=inp.parentNode.querySelector('[data-dapps]');let r=[...l.children].find(e=>!e.querySelector('[data-an]').value&&!e.querySelector('[data-ap]').value);
    if(!r){if(l.children.length>=20)return;r=l.firstElementChild.cloneNode(true);l.appendChild(r)}
    r.querySelector('[data-an]').value=a.name;r.querySelector('[data-ap]').value=a.path;inp.value=''});
  box.querySelectorAll('[data-daddbtn]').forEach(b=>b.onclick=()=>{const l=b.parentNode.querySelector('[data-dbtns]');if(l.children.length>=12)return;
    const r=l.firstElementChild.cloneNode(true);r.querySelector('[data-bn]').value='';r.querySelector('[data-be]').value='';l.appendChild(r)});
  box.querySelectorAll('[data-dsend]').forEach(b=>b.onclick=async()=>{const id=b.dataset.dsend,c=box.querySelector(`[data-desk="${CSS.escape(id)}"]`);
    const m=c.querySelector(`[data-dmsg="${CSS.escape(id)}"]`),kind=c.querySelector('[data-skind]').value,fd=new FormData();
    fd.append('did',id);fd.append('kind',kind);
    if(kind==='file'){const f=c.querySelector('[data-sfile]').files[0];if(!f){if(m)m.textContent=t('Erst eine Datei wählen.','Pick a file first.');return}fd.append('file',f)}
    else fd.append('text',c.querySelector('[data-stext]').value);
    try{await api('/api/profile/desk/send',{method:'POST',body:fd});c.querySelector('[data-stext]').value='';c.querySelector('[data-sfile]').value='';
      if(m)m.textContent=t('Liegt bereit; der Rechner holt es beim nächsten Abruf.','Ready; the computer takes it with its next check.')}
    catch(e){if(m)m.textContent=e.message}});
  box.querySelectorAll('[data-ddel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Gerät entfernen? Sein Schlüssel gilt dann nicht mehr.','Remove the device? Its key stops working.')))return;
    try{await api('/api/profile/desk/devices/'+encodeURIComponent(b.dataset.ddel),{method:'DELETE'});showDesk()}catch(e){xmsg('dkmsg',e.message,true)}})}
// Admin: Funktionen → Spark-Begleiter shows which program versions the Spark keeps for updates and fetches them now.
async function deskAdmin(){if(!$('deskadmin'))return;let d={};try{d=await (await api('/api/admin/desk')).json()}catch{return}
  // a platform without a paired computer is not fetched on its own: say so instead of a bare "none yet"
  const st=$('deskstate'),paired=d.paired||[],part=(n,p,x)=>n+' '+(x&&x.version?x.version:
    paired.includes(p)?t('noch keine','none yet'):t('noch keine (kein Rechner gekoppelt)','none yet (no computer paired)'))+(x&&x.error?' ('+x.error+')':'');
  st.textContent=t('Für Updates auf dem Spark: ','Kept on the Spark for updates: ')+part('Windows','windows',d.windows)+' · '+part('Mac','mac',d.mac);
  $('deskfetch').onclick=async()=>{st.textContent=t('Hole die Programme von GitHub …','Fetching the programs from GitHub …');
    try{await api('/api/admin/desk/fetch',xjson('POST'));deskAdmin()}catch(e){st.textContent=e.message}}}
