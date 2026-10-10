// Messages between the profiles of this Spark (messages.py): "Ich" → Nachrichten and new messages on the
// open page. Off until the admin allows it and the profile switches it on. A message is someone else's
// words: in the conversation it is marked as outside text, so it can never make the assistant act.
let MSG_ON=false;
const msg={since:Date.now()-10*60e3,seen:new Set(),busy:false,
  on(){return MSG_ON&&!!PROFILE&&!!S.msg_on},
  async poll(){if(!this.on()||document.hidden||this.busy)return;this.busy=true;
    try{const r=await fetch('/api/messages/poll?since='+this.since);if(r.ok)for(const x of (await r.json()).items)await this.show(x)}catch{}
    this.busy=false},
  // said on one device only: the first that plays it takes it on the Spark, the others stay silent
  async show(x){if(this.seen.has(x.id))return;this.seen.add(x.id);this.since=Math.max(this.since,x.t*1000);
    try{const r=await api('/api/messages/played',xjson('POST',{id:x.id}));if(!(await r.json()).play)return}catch{return}
    const head=(x.voice?t('Sprachnachricht von ','Voice message from '):t('Nachricht von ','Message from '))+(x.name||'?');
    const text=head+(x.text?': '+x.text:'');
    const b=chatLog('assistant',text);b.classList.add('pro');
    const m={role:'assistant',content:text,outside:true};chat.msgs.push(m);deletable(b,m);saveConvo();chime();
    if(document.hidden)try{if(window.Notification&&Notification.permission==='granted')new Notification('✉️ '+head,{body:x.text||'',tag:'msg-'+x.id})}catch{}
    if($('msgbox')&&$('msgbox').classList.contains('on'))showMsg().catch(()=>{});
    if(chat.rec||chat.ctrl||playing())return;   // a conversation is running: the bubble and the chime suffice
    if(x.voice){msgPlay(x.id);return}
    sayText(text)}};
setInterval(()=>{msg.poll();msgBar()},20000);

// the envelope beside the chat input: pick a profile, type, send. No model in between, so nothing
// earlier in the conversation can lock it; the Spark checks the same rules as for the assistant.
function msgBar(){const on=msg.on();for(const id of ['chatmsg','mmsg'])if($(id))$(id).hidden=!on;if(!on&&$('msgcompose'))$('msgcompose').hidden=true}
// the recipient for many profiles: type a name or Rufname and pick one of at most 8 hits; with nothing typed
// the ★ favourites and the last ones written to (all of them while there are only a few). Only profiles that
// take messages from me are in d.to; the Spark checks the rules again when sending.
const MSG_HITS=8;
function msgPicker(box,id,d){const fav=new Set(d.fav||[]),every=d.all&&d.to.length;
  box.innerHTML=`<input id="${id}q" autocomplete="off" maxlength="40" placeholder="${esc(t('An … (Name tippen)','To … (type a name)'))}" aria-label="${esc(t('Empfänger','Recipient'))}"><input type="hidden" id="${id}"><button class="b" type="button" id="${id}s" hidden title="${esc(t('Favorit','Favourite'))}">☆</button><div class="mlist" id="${id}l"></div>`;
  const q=$(id+'q'),h=$(id),star=$(id+'s'),list=$(id+'l'),by=x=>d.to.find(r=>r.id===x),lab=r=>r.name+(r.call?' ('+r.call+')':'');
  const show=()=>{const s=q.value.trim().toLowerCase();let hits;
    if(!s){hits=[...(d.fav||[]),...(d.recent||[]).filter(x=>!fav.has(x))].map(by).filter(Boolean);if(d.to.length<=MSG_HITS)hits=[...hits,...d.to.filter(r=>!hits.includes(r))]}
    else{const k=r=>[r.name,r.call||''].map(x=>x.toLowerCase());hits=[...d.to.filter(r=>k(r).some(x=>x.startsWith(s))),...d.to.filter(r=>!k(r).some(x=>x.startsWith(s))&&k(r).some(x=>x.includes(s)))]}
    const more=hits.length>MSG_HITS;hits=hits.slice(0,MSG_HITS);
    list.innerHTML=hits.map(r=>`<button class="b" type="button" data-mpk="${esc(r.id)}">${fav.has(r.id)?'★ ':''}${esc(lab(r))}</button>`).join('')
      +(every&&(!s||t('alle','everybody').startsWith(s))?`<button class="b" type="button" data-mpk="all">${esc(t('alle','everybody'))}</button>`:'')
      +(more?`<span class="mut">${t('… weiter tippen','… keep typing')}</span>`:'')+(s&&!hits.length?`<span class="mut">${t('Niemand passt.','Nobody matches.')}</span>`:'')
      +(!s&&!hits.length&&d.to.length?`<span class="mut">${d.to.length} ${t('erreichbar, Namen tippen','reachable, type a name')}</span>`:'');
    list.querySelectorAll('[data-mpk]').forEach(b=>b.onclick=()=>set(b.dataset.mpk))};
  const set=v=>{const r=by(v);if(v!=='all'&&!r)return;h.value=v;q.value=v==='all'?t('alle','everybody'):lab(r);star.hidden=!r;star.textContent=fav.has(v)?'★':'☆';list.innerHTML=''};
  q.oninput=()=>{h.value='';star.hidden=true;show()};q.onfocus=()=>{if(!h.value)show()};
  q.onkeydown=e=>{if(e.key==='Enter'&&!h.value){const b=list.querySelectorAll('[data-mpk]');if(b.length===1){e.preventDefault();b[0].click()}}};
  star.onclick=async()=>{const on=!fav.has(h.value);try{const r=await (await api('/api/messages/fav',xjson('PUT',{id:h.value,on}))).json();
    d.fav=r.fav;fav.clear();r.fav.forEach(x=>fav.add(x));star.textContent=fav.has(h.value)?'★':'☆'}catch(e){star.title=e.message}};
  const first=(d.recent||[]).find(by)||(d.to.length===1?d.to[0].id:'');if(first)set(first);else show();
  return {set}}
const msgOff=r=>r.off.length>MSG_HITS?r.off.length+' '+t('Profile','profiles'):r.off.map(x=>x.name+' '+(x.why==='hat Nachrichten aus'?t('hat Nachrichten aus','has messages off'):t('nimmt keine von dir an','takes none from you'))).join(', ');
async function msgCompose(){const c=$('msgcompose');if(!c.hidden){c.hidden=true;return}
  xmsg('mcmsg','');let d,r;try{[d,r]=await Promise.all([(await api('/api/messages')).json(),(await api('/api/messages/ready')).json()])}catch(e){xmsg('mcmsg',e.message,true);c.hidden=false;return}
  msgPicker($('mcpick'),'mcto',d);
  const off=msgOff(r);
  const can=d.to.length>0;$('mcpick').hidden=$('mctext').hidden=$('mcsend').hidden=!can;
  c.hidden=false;if(can){($('mcto').value?$('mctext'):$('mctoq')).focus();if(off)xmsg('mcmsg',t('Nicht erreichbar: ','Not reachable: ')+off)}
  else xmsg('mcmsg',t('Gerade nimmt kein anderes Profil Nachrichten von dir an.','No other profile takes messages from you right now.')+(off?' '+off+'.':''),true)}
async function msgComposeSend(){const v=$('mctext').value.trim();if(!v)return;
  if(!$('mcto').value){xmsg('mcmsg',t('Erst den Empfänger wählen.','Pick the recipient first.'),true);$('mctoq').focus();return}
  try{const r=await (await api('/api/messages/send',xjson('POST',{to:$('mcto').value,text:v}))).json();$('mctext').value='';
    xmsg('mcmsg',t('Gesendet an ','Sent to ')+r.sent.join(', '));setTimeout(()=>{if(!$('mctext').value)$('msgcompose').hidden=true},2500)}
  catch(e){xmsg('mcmsg',e.message,true)}}
if($('chatmsg')){$('chatmsg').onclick=$('mmsg').onclick=()=>msgCompose();$('mcclose').onclick=()=>$('msgcompose').hidden=true;
  $('mcsend').onclick=msgComposeSend;$('mctext').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();msgComposeSend()}})}
// the admin's "für alle Profile einschalten" (Funktionen)
if($('msgallon'))$('msgallon').onclick=async()=>{if(!confirm(t('Nachrichten für alle Profile einschalten?','Switch messages on for every profile?')))return;
  try{const r=await (await api('/api/admin/messages/enable_all',xjson('POST',{}))).json();xmsg('msgallmsg',t('Für ','Switched on for ')+r.switched+t(' Profil(e) eingeschaltet.',' profile(s).'))}
  catch(e){xmsg('msgallmsg',e.message==='messages are turned off'?t('Erst „Nachrichten an andere“ einschalten und speichern.','First switch on "Messages to others" and save.'):e.message,true)}};
setTimeout(()=>msg.poll(),5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)msg.poll()});

let msgAudio=null;
async function msgPlay(id){try{if(msgAudio){msgAudio.pause();URL.revokeObjectURL(msgAudio.src)}
  const r=await api('/api/messages/audio?id='+encodeURIComponent(id));msgAudio=new Audio(URL.createObjectURL(await r.blob()));await msgAudio.play()}catch(e){xmsg('msgmsg',e.message,true)}}

const MSG_TIME=s=>new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const msgRec={rec:null,chunks:[],timer:null,blob:null,stream:null};
async function showMsg(){const box=$('msgbox');if(!box)return;if(!PROFILE||!MSG_ON){box.innerHTML='';return}
  let d,rd;try{[d,rd]=await Promise.all([(await api('/api/messages')).json(),(await api('/api/messages/ready')).json()])}catch{box.innerHTML='';return}
  const on=!!d.on,set=d.settings;
  const opt=(v,l,cur)=>`<option value="${esc(v)}"${v===cur?' selected':''}>${esc(l)}</option>`;
  const items=d.items.map(x=>`<li${x.read?'':' class="unread"'}><span><b>${esc(x.name||'?')}</b> <small class="mut">${esc(MSG_TIME(x.t))}${x.kind==='all'?t(' · an alle',' · to everybody'):''}${x.voice?' · 🎙 '+esc(x.secs||'')+' s':''}</small><br>${esc(x.text||'')}</span>
      <span class="row">${x.voice?`<button class="b" type="button" data-mplay="${esc(x.id)}">${t('Abspielen','Play')}</button>`:''}${d.to.some(r=>r.id===x.from)?`<button class="b" type="button" data-mre="${esc(x.from)}">${t('Antworten','Reply')}</button>`:''}<button class="b" type="button" data-mdel="${esc(x.id)}">${t('Löschen','Delete')}</button></span></li>`).join('')
    ||`<li class="mut">${t('Keine Nachrichten.','No messages.')}</li>`;
  const pick=(key,list)=>d.others.map(o=>`<label class="chk"><input type="checkbox" data-mwho="${key}" value="${esc(o.id)}"${list.includes(o.id)?' checked':''}> ${esc(o.name)}</label>`).join(' ')||`<span class="mut">${t('Noch kein anderes Profil mit Nachrichten.','No other profile with messages yet.')}</span>`;
  box.innerHTML=`<div class="intro">${t('Schreib anderen Profilen dieses Sparks: „Sag Anna, das Essen ist fertig.“ Der Assistent liest die Nachricht vor und schickt sie nach deinem „Ja“. Neue Nachrichten kommen einmal an: hier auf der Seite, auf deinem Lautsprecher oder als Mitteilung auf dem Gerät, das du zuletzt benutzt hast. Was jemand schreibt, kann nie etwas schalten oder senden.','Write to other profiles of this Spark: "Tell Anna dinner is ready." The assistant reads the message back and sends it after your "Yes". New messages arrive once: here on the page, on your speaker or as a notification on the device you used last. What someone writes can never switch or send anything.')}</div>
    ${msgReady(rd)}
    ${xsw('msg_on',t('Nachrichten für mich nutzen','Use messages for me'),t('Senden und empfangen. Nachrichten bleiben 30 Tage und kommen nicht in Sicherungen.','Send and receive. Messages stay 30 days and are not in backups.'))}
    ${on?`<h3 style="margin:14px 0 4px">${t('Neue Nachricht','New message')}</h3>
    ${d.to.length?`<div class="mpick" id="msgpick"></div>
      <textarea id="msgtext" rows="2" maxlength="${d.max_text}" placeholder="${esc(t('Deine Nachricht','Your message'))}"></textarea>
      <div class="row" style="margin-top:6px"><button class="b p" type="button" id="msgsend">${t('Senden','Send')}</button>
        ${d.voice?`<button class="b" type="button" id="msgrec">🎙 ${t('Aufnehmen','Record')}</button><button class="b" type="button" id="msgvsend" hidden>${t('Sprachnachricht senden','Send voice message')}</button>`:''}</div>
      ${d.voice?`<div class="fh">${t('Sprachnachricht: höchstens ','Voice message: at most ')+d.max_voice+t(' Sekunden.',' seconds.')}</div>`:''}`
    :`<div class="fh">${t('Gerade nimmt kein anderes Profil Nachrichten von dir an.','No other profile takes messages from you right now.')}</div>`}
    ${d.speakers.length?`<h3 style="margin:14px 0 4px">${t('Durchsage','Announcement')}</h3>
      <div class="row" style="flex-wrap:wrap;gap:6px">${d.speakers.map(s=>`<label class="chk"><input type="checkbox" data-mspk value="${esc(s.id)}"> ${esc(s.name)}</label>`).join(' ')}</div>
      <div class="rowin"><input id="msgann" maxlength="300" placeholder="${esc(t('z. B. Essen ist fertig','e.g. Dinner is ready'))}"><button class="b" type="button" id="msgannsend">${t('Durchsagen','Announce')}</button></div>`:''}
    <h3 style="margin:14px 0 4px">${t('Empfangen','Received')}</h3><ul class="facts">${items}</ul>
    ${d.items.length?`<div class="row"><button class="b" type="button" id="msgreadall">${t('Alle als gelesen','Mark all read')}</button><button class="b" type="button" id="msgdelall">${t('Alle löschen','Delete all')}</button></div>`:''}
    <h3 style="margin:14px 0 4px">${t('Wer darf mir schreiben','Who may write to me')}</h3>
    <select id="msgfrom">${opt('all',t('alle Profile mit Nachrichten','every profile with messages'),set.msg_from)}${opt('chosen',t('nur ausgewählte','only picked ones'),set.msg_from)}</select>
    ${set.msg_from==='chosen'?`<div class="row" style="flex-wrap:wrap;gap:6px;margin-top:6px">${pick('allow',d.allow)}</div>`:''}
    <details style="margin-top:6px"${d.block.length?' open':''}><summary>${t('Gesperrt','Blocked')}</summary><div class="row" style="flex-wrap:wrap;gap:6px">${pick('block',d.block)}</div></details>
    <label>${t('Mein Rufname','My call name')}</label><div class="rowin"><input id="msgcall" maxlength="40" value="${esc(d.call||'')}" placeholder="${esc(t('z. B. Tom oder Papa','e.g. Tom or Dad'))}"><button class="b" type="button" id="msgcallsave">${t('Speichern','Save')}</button></div>
    <div class="fh">${t('So können andere dich in Nachrichten nennen („Schreib Tom, …“), wenn Namen sich ähneln. Muss eindeutig sein.','How others can name you in messages ("Tell Tom …") when names are alike. Must be unique.')}</div>
    ${d.all?xsw('msg_all',t('Nachrichten an alle annehmen','Take messages to everybody'),t('„Sag allen …“ von anderen Profilen.','"Tell everybody …" from other profiles.')):''}
    <label>${t('Auf meinen Lautsprechern','On my speakers')}</label>
    <select id="msgspk">${opt('off',t('nichts sagen','say nothing'),set.msg_speaker)}${opt('hint',t('nur sagen, von wem','say only who wrote'),set.msg_speaker)}${opt('text',t('mit Text vorlesen','read with the text'),set.msg_speaker)}</select>
    <div class="fh">${t('Wenn keine Seite offen ist und der Lautsprecher verbunden ist, sonst beim nächsten Weckwort. In deinen Ruhezeiten nie.','When no page is open and the speaker is connected, else at its next wake word. Never in your quiet hours.')}</div>
    ${d.announce?xsw('msg_announce',t('Durchsagen auf meinen Lautsprechern erlauben','Allow announcements on my speakers'),t('Von dir und von Profilen, die dir schreiben dürfen.','From you and from profiles that may write to you.')):''}`:''}
    <div class="fh" id="msgmsg"></div>`;
  xbind(box,showMsg);
  const pk=$('msgpick')?msgPicker($('msgpick'),'msgto',d):null;
  if($('msgcallsave'))$('msgcallsave').onclick=()=>call('/api/messages/call',xjson('PUT',{call:$('msgcall').value}),r=>r.call?t('Rufname gespeichert: ','Call name saved: ')+r.call:t('Rufname entfernt.','Call name removed.'));
  const call=async(p,o,done)=>{try{const r=await (await api(p,o)).json();await showMsg();if(done)xmsg('msgmsg',done(r))}catch(e){xmsg('msgmsg',e.message,true)}};
  if($('msgallon2'))$('msgallon2').onclick=()=>{if(confirm(t('Nachrichten für alle Profile einschalten?','Switch messages on for every profile?')))call('/api/admin/messages/enable_all',xjson('POST',{}),r=>t('Für ','Switched on for ')+r.switched+t(' Profil(e) eingeschaltet.',' profile(s).'))};
  const need=()=>{if($('msgto').value)return true;xmsg('msgmsg',t('Erst den Empfänger wählen.','Pick the recipient first.'),true);$('msgtoq').focus();return false};
  if($('msgsend'))$('msgsend').onclick=()=>{const v=$('msgtext').value.trim();if(!v||!need())return;
    call('/api/messages/send',xjson('POST',{to:$('msgto').value,text:v}),r=>t('Gesendet an ','Sent to ')+r.sent.join(', '))};
  if($('msgrec'))$('msgrec').onclick=()=>msgRecord();
  if($('msgvsend'))$('msgvsend').onclick=async()=>{if(!msgRec.blob||!need())return;xmsg('msgmsg',t('Sende …','Sending …'));
    try{const r=await (await api('/api/messages/voice?to='+encodeURIComponent($('msgto').value),{method:'POST',headers:{'Content-Type':msgRec.blob.type||'application/octet-stream'},body:msgRec.blob})).json();
      msgRec.blob=null;await showMsg();xmsg('msgmsg',t('Gesendet an ','Sent to ')+r.sent.join(', '))}catch(e){xmsg('msgmsg',e.message,true)}};
  if($('msgannsend'))$('msgannsend').onclick=()=>{const ids=[...box.querySelectorAll('[data-mspk]:checked')].map(x=>x.value),v=$('msgann').value.trim();
    if(!ids.length||!v){xmsg('msgmsg',t('Lautsprecher wählen und Text eingeben.','Pick a speaker and enter the text.'),true);return}
    call('/api/messages/announce',xjson('POST',{speakers:ids,text:v}),r=>t('Durchgesagt auf ','Announced on ')+r.sent.join(', '))};
  box.querySelectorAll('[data-mdel]').forEach(b=>b.onclick=()=>call('/api/messages/delete',xjson('POST',{ids:[b.dataset.mdel]})));
  box.querySelectorAll('[data-mplay]').forEach(b=>b.onclick=()=>msgPlay(b.dataset.mplay));
  box.querySelectorAll('[data-mre]').forEach(b=>b.onclick=()=>{if(pk)pk.set(b.dataset.mre);$('msgtext').focus()});
  if($('msgreadall'))$('msgreadall').onclick=()=>call('/api/messages/read',xjson('POST',{}));
  if($('msgdelall'))$('msgdelall').onclick=()=>{if(confirm(t('Alle Nachrichten löschen?','Delete all messages?')))call('/api/messages/delete',xjson('POST',{}))};
  if($('msgfrom'))$('msgfrom').onchange=()=>{saveSet('msg_from',$('msgfrom').value);setTimeout(showMsg,400)};
  if($('msgspk'))$('msgspk').onchange=()=>saveSet('msg_speaker',$('msgspk').value);
  box.querySelectorAll('[data-mwho]').forEach(c=>c.onchange=()=>{const k=c.dataset.mwho;
    call('/api/messages/who',xjson('PUT',{[k]:[...box.querySelectorAll(`[data-mwho="${k}"]:checked`)].map(x=>x.value)}))});
  box.querySelectorAll('[data-mrdy]').forEach(i=>i.oninput=()=>{const s=i.value.trim().toLowerCase();i.nextElementSibling.querySelectorAll('li').forEach(li=>li.hidden=!!s&&!li.textContent.toLowerCase().includes(s))});
  // the open page counts as unread-free once seen
  if(d.unread&&box.classList.contains('on'))api('/api/messages/read',xjson('POST',{ids:d.items.filter(x=>!x.read).map(x=>x.id)})).catch(()=>{})}
// Bereit: is everything on, who can be reached, and why not
// with many profiles: the numbers, the names behind a click (searchable)
function msgReady(r){const ok=(b,l)=>`<li>${b?'✅':'⚠️'} ${l}</li>`;
  const offs=r.off.map(x=>`${esc(x.name)} (${x.why==='hat Nachrichten aus'?t('hat Nachrichten aus','has messages off'):t('nimmt keine von dir an','takes none from you')})`);
  const many=(n,head,names)=>`${n} ${head} <details class="mrdy"><summary>${t('Namen zeigen','Show names')}</summary><input type="search" placeholder="${esc(t('Suchen','Search'))}" data-mrdy maxlength="40"><ul class="facts small">${names.map(x=>`<li><span>${x}</span></li>`).join('')}</ul></details>`;
  const reach=r.reach.length>MSG_HITS?many(r.reach.length,t('erreichbar','reachable'),r.reach.map(x=>esc(x.name))):t('Erreichbar: ','Reachable: ')+r.reach.map(x=>esc(x.name)).join(', ');
  const off=offs.length>MSG_HITS?many(offs.length,t('nicht erreichbar','not reachable'),offs):offs.length?t('Nicht erreichbar: ','Not reachable: ')+offs.join(', '):'';
  return `<h3 style="margin:10px 0 2px">${t('Bereit','Ready')}</h3><ul class="rdy" id="msgready">${ok(r.enabled,t('Vom Admin erlaubt','Allowed by the admin'))}${ok(r.on,t('Für dich eingeschaltet','On for you'))}
    ${r.reach.length?ok(true,reach):ok(false,t('Noch niemand erreichbar','Nobody reachable yet'))}
    ${off?ok(false,off):''}</ul>
    ${r.admin&&r.off_count?`<div class="row"><button class="b" type="button" id="msgallon2">${t('Für alle Profile einschalten','Switch on for every profile')} (${r.off_count})</button></div>`:''}`}
// a voice message: recorded here, at most max_voice seconds, sent only when the person presses send
async function msgRecord(){const btn=$('msgrec');
  if(msgRec.rec){msgRec.rec.stop();return}
  try{msgRec.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
  catch{xmsg('msgmsg',t('Kein Mikrofon (nur über https erlaubt).','No microphone (only allowed over https).'),true);return}
  msgRec.chunks=[];msgRec.blob=null;const rec=new MediaRecorder(msgRec.stream);msgRec.rec=rec;
  rec.ondataavailable=e=>{if(e.data&&e.data.size)msgRec.chunks.push(e.data)};
  rec.onstop=()=>{clearTimeout(msgRec.timer);msgRec.stream.getTracks().forEach(x=>x.stop());msgRec.rec=null;
    msgRec.blob=new Blob(msgRec.chunks,{type:rec.mimeType||'audio/webm'});
    if($('msgrec'))$('msgrec').textContent='🎙 '+t('Neu aufnehmen','Record again');if($('msgvsend'))$('msgvsend').hidden=false;
    xmsg('msgmsg',t('Aufnahme fertig. Jetzt senden oder neu aufnehmen.','Recording done. Send it now or record again.'))};
  rec.start();btn.textContent='■ '+t('Stopp','Stop');xmsg('msgmsg',t('Aufnahme läuft …','Recording …'));
  msgRec.timer=setTimeout(()=>{if(msgRec.rec)msgRec.rec.stop()},30000)}
