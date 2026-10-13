// Chats mit anderen Sparks (verbund.py, plan spark-verbund.md): in Chats the own Spark address with QR code, a request
// to an address on another Spark, the requests to me (Annehmen, Ablehnen, Sperren) and the contacts; for the admin the
// pairing code, the list of Sparks with key fingerprints, allow, block and remove. Every name and address that comes
// from another Spark goes into the page as text (esc), never as HTML.
const VERB={d:null};
const VB_STATE={in:['möchte mit dir schreiben','wants to write with you'],out:['wartet auf Antwort','waiting for an answer'],
  ok:['Kontakt','contact'],block:['gesperrt','blocked']};

// ---------------------------------------------------------------- Chats → ＋ Neuer Chat → „Jemand auf einem anderen Spark“
async function vbPane(){const p=$('cxpane');if(!p||CX.pane!=='far')return;let d;
  try{d=await (await api('/api/verbund')).json()}catch(e){p.innerHTML=`<div class="cx-msgline err">${esc(cxTr(e.message))}</div>`;return}
  if(CX.pane!=='far')return;VERB.d=d;vbDraw()}
function vbRow(c){const who=c.name||c.addr,sub=c.name?c.addr:'';
  const btn=(a,label,cls)=>`<button type="button" class="b${cls?' '+cls:''}" data-vb="${a}" data-id="${esc(c.id)}">${esc(label)}</button>`;
  const acts=c.state==='in'?btn('ok',t('Annehmen','Accept'),'p')+btn('no',t('Ablehnen','Decline'))+btn('block',t('Sperren','Block'),'danger')
    :c.state==='ok'?btn('open',t('Schreiben','Write'))+btn('remove',t('Entfernen','Remove'),'danger')
    :c.state==='out'?btn('remove',t('Zurückziehen','Withdraw'))
    :btn('unblock',t('Entsperren','Unblock'));
  return `<div class="cx-pp vb-c">${cxAva(c.id,who)}<span class="vb-who"><b>🌐 ${esc(who)}</b><small class="mut">${esc((sub?sub+' · ':'')+t(...VB_STATE[c.state]||['','']))}</small></span><span class="cx-mact">${acts}</span></div>`}
function vbDraw(){const d=VERB.d,p=$('cxpane');if(!d||!p)return;
  const groups=[['in',t('Anfragen an dich','Requests to you')],['ok',t('Kontakte auf anderen Sparks','Contacts on other Sparks')],
    ['out',t('Deine offenen Anfragen','Your open requests')],['block',t('Gesperrt','Blocked')]];
  let h=`<div class="intro sm">${esc(t('Mit Personen auf einem anderen Spark schreiben: Adresse eintragen, Anfrage senden. Erst wenn die Person annimmt, kommt eine Nachricht durch. Zuerst nur Text; Fotos, Dateien und Sprache kommen später.',
    'Write with people on another Spark: enter their address, send a request. Only once the person accepts does a message get through. Text only for now; photos, files and voice come later.'))}</div>`;
  h+=`<div class="cx-grp">${esc(t('Deine Spark-Adresse','Your Spark address'))}</div>`;
  if(d.address)h+=`<div class="cx-inv vb-me">${d.qr?`<div class="cx-qr">${d.qr}</div>`:''}<input id="vbme" readonly value="${esc(d.address)}" aria-label="${esc(t('Deine Spark-Adresse','Your Spark address'))}">`+
    `<div class="cx-acts2"><button type="button" class="b" data-vb="copy">${esc(t('Kopieren','Copy'))}</button>${navigator.share?`<button type="button" class="b" data-vb="share">${esc(t('Teilen','Share'))}</button>`:''}</div></div>`;
  h+=`<label class="cx-lbl" for="vbaddr">${esc(t('Jemanden anfragen','Ask someone'))}</label><input id="vbaddr" maxlength="240" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="name@spark.example.de">`+
    `<div class="cx-acts2"><button type="button" class="b p" data-vb="ask">${esc(t('Anfrage senden','Send request'))}</button></div><div class="cx-msgline mut" id="vbmsg" role="status"></div>`;
  for(const [st,title] of groups){const list=(d.contacts||[]).filter(c=>c.state===st);if(!list.length)continue;
    h+=`<div class="cx-grp">${esc(title)}</div><div class="cx-people">${list.map(vbRow).join('')}</div>`}
  p.innerHTML=h;cxHues(p)}
function vbMsg(text,bad){const m=$('vbmsg');if(m){m.textContent=cxTr(text);m.classList.toggle('err',!!bad)}}
$('cxpane').addEventListener('click',async e=>{const b=e.target.closest('[data-vb]');if(!b||CX.pane!=='far')return;const a=b.dataset.vb,id=b.dataset.id;
  try{if(a==='copy')copyString(VERB.d.address,b);
    else if(a==='share'){try{await navigator.share({title:'Spark',text:VERB.d.address})}catch{}}
    else if(a==='ask'){const addr=$('vbaddr').value.trim();if(!addr){vbMsg(t('Adresse eintragen, z. B. anna@spark.example.de','Enter an address, e.g. anna@spark.example.de'),true);return}
      b.disabled=true;try{VERB.d=await (await api('/api/verbund/ask',xjson('POST',{addr}))).json();vbDraw();vbMsg(t('Anfrage gesendet. Sobald die Person annimmt, steht sie unter Kontakte.','Request sent. Once the person accepts, they show under contacts.'))}finally{b.disabled=false}}
    else if(a==='open'){const r=await (await api('/api/verbund/open',xjson('POST',{id}))).json();CX.pane='';await cxLoad();await cxOpen(r.id)}
    else if(a==='ok'){const r=await (await api('/api/verbund/answer',xjson('POST',{id,act:'ok'}))).json();CX.pane='';await cxLoad();if(r.chat)await cxOpen(r.chat)}
    else if(a==='no'||a==='block'||a==='unblock'){if(a==='block'&&!confirm(t('Diese Person sperren? Von ihr kommt dann keine Anfrage und keine Nachricht mehr an.','Block this person? No request and no message from them reaches you any more.')))return;
      VERB.d=await (await api('/api/verbund/answer',xjson('POST',{id,act:a}))).json();vbDraw();cxLoad()}
    else if(a==='remove'){if(!confirm(t('Aus deinen Kontakten nehmen? Der Chat bleibt zum Lesen, schreiben geht erst nach einer neuen Anfrage.','Remove from your contacts? The chat stays to read; writing needs a new request.')))return;
      VERB.d=await (await api('/api/verbund/remove',xjson('POST',{id}))).json();vbDraw();cxLoad()}}
  catch(err){vbMsg(err.message,true)}});
$('cxpane').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='vbaddr'){e.preventDefault();const b=$('cxpane').querySelector('[data-vb="ask"]');if(b)b.click()}});
window.vbPane=vbPane;

// ---------------------------------------------------------------- admin: Funktionen → Chats → Chats mit anderen Sparks
const VB_PEER={paired:['gekoppelt','paired'],open:['offen verbunden','connected (open)'],blocked:['gesperrt','blocked']};
const vdWhen=ts=>ts?new Date(ts*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'–';
async function vbAdmin(code){const box=$('vbadmin');if(!box)return;let d;
  try{d=await (await api('/api/admin/verbund')).json()}catch{box.innerHTML='';return}
  let h=`<div class="fh">${esc(t('Schlüssel dieses Sparks (Fingerabdruck): ','This Spark\'s key (fingerprint): '))}<code>${esc(d.key)}</code></div>`;
  if(!d.domain)h+=`<div class="fh err">${esc(t('Zuerst oben die Adresse von außen eintragen und speichern; ohne sie bleibt die Funktion aus.','First enter the address from outside above and save; without it the function stays off.'))}`+
    (d.suggest?` <button class="b" type="button" id="vbsuggest">${esc(t('Vorschlag: ','Suggestion: ')+d.suggest)}</button>`:'')+`</div>`;
  else{
    h+=`<div class="row" style="margin-top:6px"><button class="b" type="button" id="vbpair">${esc(t('Kopplungs-Code erstellen','Make a pairing code'))}</button><span class="mut">${esc(t('Für den Admin des anderen Sparks; gilt einen Tag und einmal.','For the other Spark\'s admin; works one day and once.'))}</span></div>`;
    if(code)h+=`<div class="rowin"><input id="vbcode" readonly value="${esc(code)}" aria-label="${esc(t('Kopplungs-Code','Pairing code'))}"><button class="b" type="button" id="vbcodecopy">${esc(t('Kopieren','Copy'))}</button></div><div class="fh">${esc(t('Nur jetzt zu sehen. Auf sicherem Weg weitergeben (persönlich, Signal).','Shown only now. Pass it on safely (in person, Signal).'))}</div>`;
    h+=`<label for="vbuse">${esc(t('Code eines anderen Sparks','Code of another Spark'))}</label><div class="rowin"><input id="vbuse" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="spark.example.de#…"><button class="b" type="button" id="vbconnect">${esc(t('Koppeln','Pair'))}</button></div>`}
  h+=`<div class="fh" id="vbamsg" role="status"></div>`;
  h+=`<div class="fh"><b>${esc(t('Verbundene Sparks','Connected Sparks'))}</b></div>`+(d.peers.length?`<div class="vb-peers">${d.peers.map(x=>`<div class="card vb-peer" data-vbp="${esc(x.domain)}"><b>${esc(x.domain)}</b> <small class="mut">${esc(t(...VB_PEER[x.state]||['','']))}</small>`+
    `<div class="fh">${esc(t('Fingerabdruck ','Fingerprint '))}<code>${esc(x.fingerprint)}</code><br>${esc(x.contacts+' '+t('Kontakte','contacts')+' · '+t('rein ','in ')+x.in+' · '+t('raus ','out ')+x.out+(x.waiting?' · '+x.waiting+' '+t('warten','waiting'):'')+' · '+t('zuletzt ','last ')+vdWhen(x.last))}</div>`+
    `<div class="row">${x.state!=='paired'?`<button class="b" type="button" data-vbact="allow">${esc(t('Erlauben','Allow'))}</button>`:''}${x.state!=='blocked'?`<button class="b danger" type="button" data-vbact="block">${esc(t('Sperren','Block'))}</button>`:''}<button class="b" type="button" data-vbact="remove">${esc(t('Entfernen','Remove'))}</button></div></div>`).join('')}</div>`
    :`<div class="fh mut">${esc(t('Noch keiner.','None yet.'))}</div>`);
  box.innerHTML=h;
  const say=(text,bad)=>{const m=$('vbamsg');if(m){m.textContent=text;m.classList.toggle('err',!!bad)}};
  if($('vbsuggest'))$('vbsuggest').onclick=()=>{const i=$('chat.verbund_domain');if(i){i.value=d.suggest;i.dispatchEvent(new Event('input',{bubbles:true}))}};
  if($('vbpair'))$('vbpair').onclick=async()=>{try{const r=await (await api('/api/admin/verbund/pair',xjson('POST',{}))).json();await vbAdmin(r.code)}catch(e){say(e.message,true)}};
  if($('vbcodecopy'))$('vbcodecopy').onclick=e=>copyString($('vbcode').value,e.target);
  if($('vbconnect'))$('vbconnect').onclick=async()=>{const c=$('vbuse').value.trim();if(!c)return;say(t('Einen Moment …','One moment …'));
    try{const r=await (await api('/api/admin/verbund/connect',xjson('POST',{code:c}))).json();await vbAdmin();say(t('Gekoppelt mit ','Paired with ')+r.domain+' · '+t('Fingerabdruck ','fingerprint ')+r.fingerprint)}catch(e){say(e.message,true)}};
  box.querySelectorAll('[data-vbact]').forEach(b=>b.onclick=async()=>{const dom=b.closest('[data-vbp]').dataset.vbp,act=b.dataset.vbact;
    if(act!=='allow'&&!confirm(act==='block'?t('Diesen Spark sperren? Nichts geht mehr hin und nichts kommt mehr an.','Block this Spark? Nothing goes there and nothing comes in any more.'):t('Diesen Spark entfernen? Danach muss neu gekoppelt werden.','Remove this Spark? It has to be paired again afterwards.')))return;
    try{await api('/api/admin/verbund/peer',xjson('POST',{domain:dom,act}));await vbAdmin()}catch(e){say(e.message,true)}})}
window.vbAdmin=vbAdmin;
