// Chats (chats.py, plan messenger.md Schritt A): writing with other profiles like in a messenger, one to one and in
// groups. Left the list (newest first, unread count, muted), right the open chat with bubbles, ticks (✓ sent, ✓✓ on
// a device, blue ✓✓ read), answers, reactions, change and take back; ⓘ shows mute, "verschwinden", members and
// leave. Narrow (phone) the list and the chat are two pages with "‹" back. While the page is open and visible an
// event stream brings changes (only ids, never a text; the texts come with the next list or chat call); otherwise
// the unread count is asked every minute. Every text from others goes into the page as text (esc), never as HTML.
const CX={menu:'',S:null,cur:'',data:null,reply:null,edit:null,es:null,poll:0,shown:false,pane:'',typing:{},typeSent:0,pick:new Set(),q:'',hits:null,busy:false};
const cxEl=id=>$(id);
const cxMe=()=>(typeof PROFILE!=='undefined'&&PROFILE&&PROFILE.id)||'';
const cxHm=ts=>new Date(ts*1000).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
function cxDay(ts){const d=new Date(ts*1000),n=new Date(),y=new Date(n);y.setDate(n.getDate()-1);
  if(d.toDateString()===n.toDateString())return t('Heute','Today');if(d.toDateString()===y.toDateString())return t('Gestern','Yesterday');
  return d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{weekday:'long',day:'numeric',month:'long'})}
function cxWhen(ts){const d=new Date(ts*1000),n=new Date();
  if(d.toDateString()===n.toDateString())return cxHm(ts);
  if(n-d<6*864e5)return d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{weekday:'short'});
  return d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit'})}
// a colour per person from its id (same person, same colour on every device); the letter from its name
const cxHue=id=>{let h=0;for(const c of String(id||''))h=(h*31+c.charCodeAt(0))%360;return h};
const cxAva=(id,name,group)=>`<span class="cx-ava${group?' grp':''}" data-hue="${cxHue(id)}">${group?'👥':esc((name||'?').trim().charAt(0).toUpperCase()||'?')}</span>`;
// the panel's German sentences (why, titles) in English; the two with a name by pattern
const cxTr=s=>{if(L!=='en')return s;if(typeof EN!=='undefined'&&EN[s])return EN[s];let m=/^(.+) nimmt gerade keine Nachrichten von dir an\.$/.exec(s);
  if(m)return m[1]+' does not take messages from you right now.';m=/^(.+) hat Chats nicht eingeschaltet\.$/.exec(s);
  if(m)return (m[1]==='Diese Person'?'This person':m[1])+' has not switched chats on.';return s};
const cxTitle=s=>cxTr(s||'');
const CX_VANISH=[[0,t('aus','off')],[86400,t('nach 24 Stunden','after 24 hours')],[604800,t('nach 7 Tagen','after 7 days')],[7776000,t('nach 90 Tagen','after 90 days')]];
const CX_MUTE=[[0,t('aus','off')],[3600,t('1 Stunde','1 hour')],[28800,t('8 Stunden','8 hours')],[-1,t('immer','always')]];
async function cxApi(path,body){const r=await api(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json()}
function cxHues(root){root.querySelectorAll('[data-hue]').forEach(e=>e.style.setProperty('--h',e.dataset.hue))}   // no style attribute (strict CSP)

// ---------------------------------------------------------------- start, menu entry, unread count
window.cxStart=who=>{const on=!!(who&&who.chats_use);
  document.querySelectorAll('nav button[data-s=chats],#mbar button[data-m=chats]').forEach(b=>b.hidden=!on);
  window.CHATS_ON=on;
  if(!on)return;cxLoad();
  // invited into a chat (join.js): straight into it after the first sign-in
  let go='';try{go=sessionStorage.getItem('gochat')||'';sessionStorage.removeItem('gochat')}catch{}
  if(/^c[0-9a-f]{12}$/.test(go)){CX.cur=go;showSec('chats')}
  // the count beside "Chats" while the page is elsewhere: once a minute, only while this tab is visible
  CX.poll=setInterval(()=>{if(!document.hidden&&!(CX.shown&&CX.es))cxLoad()},60e3)};
function cxBadge(){const n=(CX.S&&CX.S.chats||[]).reduce((a,c)=>a+(c.mute?0:c.unread),0),txt=n>99?'99+':String(n);
  for(const e of [cxEl('cxcnt'),document.querySelector('#mbar button[data-m=chats] .ncnt'),document.querySelector('#aptabs [data-tab=chats] .apcnt')])
    if(e){e.hidden=!n;e.textContent=txt}}
async function cxLoad(){try{CX.S=await cxApi('/api/chats')}catch(e){return}
  cxBadge();if(!CX.shown)return;
  if(!CX.S.on){cxOff();return}
  cxEl('cxoff').hidden=true;cxEl('cxsplit').hidden=false;cxList()}
function cxOff(){const o=cxEl('cxoff');cxEl('cxsplit').hidden=true;o.hidden=false;
  o.textContent=CX.S&&CX.S.enabled===false?t('Chats sind auf dem Spark ausgeschaltet (Funktionen → Chats).','Chats are switched off on the Spark (Features → Chats).')
    :t('Chats sind für dich aus. Einschalten unter Ich → Gespräch → Chats.','Chats are off for you. Switch them on under Me → Conversation → Chats.')}
// base.js showSec: the page was opened (true) or left (false)
window.cxShown=on=>{if(!CX.S&&!on)return;CX.shown=on;
  if(on){cxLoad().then(()=>{if(CX.cur)cxOpen(CX.cur,true)});cxStream()}else{cxStreamStop();cxRecStop(false)}};
document.addEventListener('visibilitychange',()=>{if(!CX.shown)return;if(document.hidden)cxStreamStop();else{cxStream();cxLoad();if(CX.cur)cxOpen(CX.cur,true)}});

// ---------------------------------------------------------------- the event stream (only while the page is visible)
// The Spark sends no notification to a device while a page of this profile listens; so it listens only while
// the page is really open and visible.
function cxStream(){if(CX.es||document.hidden||!CX.shown||typeof EventSource==='undefined')return;
  const es=new EventSource('/api/chats/stream');CX.es=es;
  es.onmessage=e=>{let ev;try{ev=JSON.parse(e.data)}catch{return}cxEvent(ev)};
  es.onerror=()=>{if(es.readyState===2){if(CX.es===es)CX.es=null;setTimeout(cxStream,15e3)}}}
function cxStreamStop(){if(CX.es){CX.es.close();CX.es=null}}
let cxLater=0;
function cxEvent(ev){if(!ev||typeof ev.id!=='string')return;
  if(ev.type==='typing'){if(ev.id===CX.cur){CX.typing[ev.id]={name:String(ev.name||''),until:Date.now()+1000*Math.min(10,+ev.secs||6)};cxTop()}return}
  if(ev.type==='gone'&&ev.id===CX.cur){cxClose()}
  clearTimeout(cxLater);cxLater=setTimeout(()=>{cxLoad();if(CX.cur&&CX.pane!=='info')cxOpen(CX.cur,true)},150)}
setInterval(()=>{const tp=CX.typing[CX.cur];if(tp&&tp.until<Date.now()){delete CX.typing[CX.cur];cxTop()}},1000);

// ---------------------------------------------------------------- the list
function cxPreview(c){const l=c.last;if(!l)return '';
  if(l.gone)return t('Nachricht zurückgenommen','Message taken back');
  if(l.kind==='sys')return l.sys==='joined'?(l.name||'')+' '+t('ist dazugekommen','joined'):t('Änderung in der Gruppe','Change in the group');
  const who=l.mine?t('Du: ','You: '):c.kind==='group'&&l.name?l.name+': ':'';
  if(l.kind==='photo')return who+'📷 '+(l.text||t('Foto','Photo'));
  if(l.kind==='file')return who+'📄 '+(l.text||t('Datei','File'));
  if(l.kind==='voice')return who+'🎤 '+t('Sprachnachricht','Voice message')+(l.secs?' ('+cxDur(l.secs)+')':'');
  return who+(l.text||'')}
const cxDur=s=>Math.floor((+s||0)/60)+':'+String(Math.round(+s||0)%60).padStart(2,'0');
const cxSize=b=>b>=1048576?(b/1048576).toFixed(1).replace('.',L==='en'?'.':',')+' MB':Math.max(1,Math.round((+b||0)/1024))+' KB';
const cxKindWord=k=>k==='photo'?t('📷 Foto','📷 Photo'):k==='file'?t('📄 Datei','📄 File'):k==='voice'?t('🎤 Sprachnachricht','🎤 Voice message'):'';
function cxList(){const box=cxEl('cxlist');if(!box)return;const S=CX.S||{chats:[]};
  if(CX.hits){cxHitsShow();return}
  if(!S.chats.length){box.innerHTML=`<div class="cx-none mut">${esc(t('Noch keine Chats. Mit „＋ Neuer Chat“ schreibst du jemandem.','No chats yet. With "＋ New chat" you write to someone.'))}</div>`;return}
  box.innerHTML=S.chats.map(c=>`<button type="button" class="cx-row${c.id===CX.cur?' on':''}" data-cx="${esc(c.id)}">${cxAva(c.with||c.id,cxTitle(c.title),c.kind==='group')}`+
    `<span class="cx-mid"><b>${esc(cxTitle(c.title))}</b><small>${esc(cxPreview(c))}</small></span>`+
    `<span class="cx-right"><span class="cx-when">${c.last?esc(cxWhen(c.last.t)):''}</span>`+
    `<span class="cx-flags">${c.mute?`<i class="cx-mute" title="${esc(t('stumm','muted'))}">🔕</i>`:''}${c.unread?`<em class="cx-un${c.mute?' quiet':''}">${c.unread>99?'99+':c.unread}</em>`:''}</span></span></button>`).join('');
  cxHues(box)}
cxEl('cxlist').addEventListener('click',e=>{const h=e.target.closest('[data-hit]');if(h){const mid=h.dataset.mid;cxFindReset();cxOpen(h.dataset.hit).then(()=>cxJump(mid));return}
  const b=e.target.closest('[data-cx]');if(b)cxOpen(b.dataset.cx)});
// search: only in the own chats, on the Spark (the texts are sealed there)
let cxFindT=0;
cxEl('cxfind').addEventListener('input',()=>{clearTimeout(cxFindT);const q=cxEl('cxfind').value.trim();
  if(q.length<2){if(CX.hits){CX.hits=null;cxList()}return}
  cxFindT=setTimeout(async()=>{try{CX.hits=(await cxApi('/api/chats/find',{q})).hits||[];CX.q=q;cxList()}catch{}},350)});   // POST: no words in the address (access log)
function cxFindReset(){cxEl('cxfind').value='';CX.hits=null;cxList()}
function cxHitsShow(){const box=cxEl('cxlist');
  box.innerHTML=`<div class="cx-grp">${esc(t('Treffer','Matches'))}</div>`+(CX.hits.length?CX.hits.map(h=>`<button type="button" class="cx-row" data-hit="${esc(h.id)}" data-mid="${esc(h.mid)}">`+
    `<span class="cx-mid"><b>${esc(cxTitle(h.title))}</b><small>${esc((h.name?h.name+': ':'')+(h.text||''))}</small></span><span class="cx-right"><span class="cx-when">${h.t?esc(cxWhen(h.t)):''}</span></span></button>`).join('')
    :`<div class="cx-none mut">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`)}

// ---------------------------------------------------------------- one chat
const box=()=>cxEl('cxbox');
async function cxOpen(cid,quiet){if(!cid)return;const first=CX.cur!==cid;
  if(first){cxRecStop(false);CX.cur=cid;CX.menu='';CX.reply=null;CX.edit=null;CX.pane='';CX.data=null;cxEl('cxtext').value='';cxGrow()}
  box().classList.add('sel');if(first||!quiet)cxPane('');
  let d;try{d=await cxApi('/api/chats/items?id='+encodeURIComponent(cid))}catch(e){if(!quiet)cxSay(e.message);if(e.status===404)cxClose();return}
  if(CX.cur!==cid)return;
  if(CX.pane){CX.data=d;return}   // a refresh from elsewhere while info, new chat or invite is open: the pane stays
  const log=cxEl('cxlog'),atEnd=log.scrollHeight-log.scrollTop-log.clientHeight<80;
  CX.data=d;cxTop();cxLog();if(first||atEnd)log.scrollTop=log.scrollHeight;
  cxEl('cxlist').querySelectorAll('.cx-row').forEach(r=>r.classList.toggle('on',r.dataset.cx===cid));
  const c=(CX.S&&CX.S.chats||[]).find(x=>x.id===cid);
  if(c&&c.unread&&!document.hidden){c.unread=0;cxBadge();cxList();try{await cxApi('/api/chats/read',{id:cid})}catch{}}
  if(first&&!matchMedia('(pointer:coarse)').matches)cxEl('cxtext').focus()}
function cxClose(){cxRecStop(false);CX.cur='';CX.data=null;CX.pane='';box().classList.remove('sel');
  for(const id of ['cxtop','cxlog','cxpane','cxwhy','cxreply','cxcomp'])cxEl(id).hidden=true;cxEl('cxempty').hidden=false;cxList()}
cxEl('cxback').addEventListener('click',()=>{if(CX.pane==='invite'){cxPane('new');return}if(CX.pane&&CX.cur&&CX.data){cxPane('');return}if(CX.pane&&!CX.cur){cxPane('');cxClose();return}cxClose()});
function cxTop(){const d=CX.data;if(!d)return;cxEl('cxempty').hidden=true;cxEl('cxtop').hidden=false;
  const tp=CX.typing[CX.cur],sub=tp&&tp.until>Date.now()?(d.kind==='group'?tp.name+' '+t('schreibt …','is typing …'):t('schreibt …','typing …'))
    :d.kind==='group'?d.members.map(m=>m.name).filter(Boolean).join(', '):'';
  cxEl('cxinfo').hidden=false;
  const tt=cxEl('cxtitle');tt.querySelector('b').textContent=cxTitle(d.title);tt.querySelector('small').textContent=sub;tt.querySelector('small').hidden=!sub;
  const why=cxEl('cxwhy');why.hidden=d.can_send;why.textContent=d.can_send?'':cxTr(d.why||t('Hier kannst du gerade nicht schreiben.','You cannot write here right now.'));
  cxEl('cxcomp').hidden=!d.can_send||!!CX.pane||!!CXR.rec;cxEl('cxreply').hidden=!CX.reply&&!CX.edit||!!CX.pane;
  const md=!!(CX.S&&CX.S.media)&&!CX.edit;cxEl('cxatt').hidden=!md;cxEl('cxmic').hidden=!md}
const CX_SYS={add:['fügte hinzu: ','added: '],remove:['nahm heraus: ','took out: '],admin:['machte zum Admin: ','made admin: '],leave:['hat die Gruppe verlassen','left the group'],
  name:['nannte die Gruppe ','named the group '],vanish:['',''],made:['hat die Gruppe erstellt','created the group']};
function cxSysLine(x){const who=x.mine?t('Du','You'):x.name||t('Jemand','Someone');
  if(x.sys==='joined')return x.mine?t('Du bist mit einer Einladung dazugekommen','You joined with an invitation'):who+' '+t('ist mit deiner Einladung dazugekommen','joined with your invitation');
  if(x.sys==='vanish'){const v=CX_VANISH.find(([s])=>s===x.secs);return who+' '+(x.secs?t('stellte ein: Nachrichten verschwinden ','set: messages disappear ')+(v?v[1]:''):t('schaltete „Nachrichten verschwinden“ aus','switched off "messages disappear"'))}
  const s=CX_SYS[x.sys]||['',''];if(x.sys==='name')return who+' '+t(s[0],s[1])+'„'+(x.text||'')+'“';
  if(x.sys==='leave')return who+' '+t(s[0],s[1]);return who+' '+t(s[0],s[1])+(x.who||[]).join(', ')}
function cxTick(k){return k==='read'?`<i class="cx-tk read" title="${esc(t('gelesen','read'))}">✓✓</i>`:k==='got'?`<i class="cx-tk" title="${esc(t('zugestellt','delivered'))}">✓✓</i>`:`<i class="cx-tk" title="${esc(t('gesendet','sent'))}">✓</i>`}
function cxLog(){const d=CX.data,log=cxEl('cxlog');log.hidden=!!CX.pane;let html='',day='',prev='';
  if(d.more)html+=`<div class="cx-more"><button type="button" class="b" data-cxa="more">${esc(t('Ältere Nachrichten','Older messages'))}</button></div>`;
  if(d.vanish){const v=CX_VANISH.find(([s])=>s===d.vanish);html+=`<div class="cx-sys">⏱ ${esc(t('Nachrichten verschwinden ','Messages disappear ')+(v?v[1]:''))}</div>`}
  for(const x of d.items){const dy=cxDay(x.t);if(dy!==day){html+=`<div class="cx-day"><span>${esc(dy)}</span></div>`;day=dy;prev=''}
    if(x.kind==='sys'){html+=`<div class="cx-sys">${esc(cxSysLine(x))}</div>`;prev='';continue}
    const head=d.kind==='group'&&!x.mine&&prev!==x.from?`<b class="cx-who" data-hue="${cxHue(x.from)}">${esc(x.name||t('Gelöschtes Profil','Deleted profile'))}</b>`:'';prev=x.from;
    const rep=x.reply?`<button type="button" class="cx-quote" data-cxa="jump" data-mid="${esc(x.reply.id)}"><b>${esc(x.reply.name||'')}</b><span>${esc(x.reply.gone?t('Nachricht zurückgenommen','Message taken back'):x.reply.text||cxKindWord(x.reply.kind))}</span></button>`:'';
    const body=x.gone?`<span class="cx-gone">${esc(x.mine?t('Du hast diese Nachricht zurückgenommen.','You took this message back.'):t('Diese Nachricht wurde zurückgenommen.','This message was taken back.'))}</span>`
      :cxMediaHtml(x)+(x.text?`<span class="cx-txt${x.kind==='voice'?' cx-said':''}">${esc(x.text)}</span>`:'');
    const meta=`<span class="cx-meta">${x.via==='spark'?`<i title="${esc(t('über den Assistenten','via the assistant'))}">🎙</i> `:''}${x.edited?esc(t('bearbeitet','edited'))+' · ':''}${esc(cxHm(x.t))}${x.tick?' '+cxTick(x.tick):''}</span>`;
    const re=(x.react||[]).length?`<span class="cx-reacts">${x.react.map(r=>`<button type="button" class="cx-rc${r.me?' me':''}" data-cxa="react" data-mid="${esc(x.id)}" data-e="${esc(r.e)}">${esc(r.e)}${r.n>1?' '+r.n:''}</button>`).join('')}</span>`:'';
    html+=`<div class="cx-msg${x.mine?' mine':''}" data-mid="${esc(x.id)}"><div class="cx-bub" tabindex="0" role="button" aria-haspopup="true">${head}${rep}${body}${meta}</div>${re}</div>`}
  if(!d.items.length)html+=`<div class="cx-sys">${esc(d.kind==='group'?t('Die Gruppe ist da. Schreib die erste Nachricht.','The group is ready. Write the first message.'):t('Schreib die erste Nachricht.','Write the first message.'))}</div>`;
  log.innerHTML=html;cxHues(log);
  // a change from elsewhere draws the chat again: an open menu stays open
  const m=CX.menu&&log.querySelector(`.cx-msg[data-mid="${CSS.escape(CX.menu)}"]`);CX.menu='';if(m)cxMenu(m)}
// tap on a bubble: reactions and what can be done with it, right below
function cxMenu(msg){const old=cxEl('cxlog').querySelector('.cx-acts');const same=old&&old.parentNode===msg;if(old)old.remove();CX.menu='';if(same||!CX.data)return;
  const x=CX.data.items.find(y=>y.id===msg.dataset.mid);if(!x||x.gone||x.kind==='sys')return;CX.menu=x.id;
  const a=document.createElement('div');a.className='cx-acts';
  a.innerHTML=(CX.data.can_send?`<span class="cx-emo">${(CX.data.reactions||[]).map(e=>`<button type="button" data-cxa="react" data-mid="${esc(x.id)}" data-e="${esc(e)}" aria-label="${esc(e)}">${esc(e)}</button>`).join('')}</span>`:'')+
    `<span class="cx-do">`+(CX.data.can_send?`<button type="button" class="b" data-cxa="reply" data-mid="${esc(x.id)}">${esc(t('Antworten','Reply'))}</button>`:'')+
    (x.text?`<button type="button" class="b" data-cxa="copy" data-mid="${esc(x.id)}">${esc(t('Kopieren','Copy'))}</button>`:'')+
    (x.can_edit?`<button type="button" class="b" data-cxa="edit" data-mid="${esc(x.id)}">${esc(t('Ändern','Change'))}</button>`:'')+
    (x.can_back?`<button type="button" class="b danger" data-cxa="back" data-mid="${esc(x.id)}">${esc(t('Für alle zurücknehmen','Take back for all'))}</button>`:'')+`</span>`;
  msg.appendChild(a)}
cxEl('cxlog').addEventListener('click',async e=>{const b=e.target.closest('[data-cxa]');
  if(!b){if(e.target.closest('audio,.cx-file'))return;const bub=e.target.closest('.cx-bub');if(bub)cxMenu(bub.parentNode);return}
  const a=b.dataset.cxa,mid=b.dataset.mid,x=CX.data&&CX.data.items.find(y=>y.id===mid);if(b.closest('.cx-acts'))CX.menu='';
  try{if(a==='more'){const first=CX.data.items[0];if(!first)return;const d=await cxApi('/api/chats/items?id='+encodeURIComponent(CX.cur)+'&before='+encodeURIComponent(first.id));
      const log=cxEl('cxlog'),h=log.scrollHeight;CX.data.items=d.items.concat(CX.data.items);CX.data.more=d.more;cxLog();log.scrollTop=log.scrollHeight-h}
    else if(a==='jump')cxJump(mid);
    else if(a==='photo'&&x)cxBig(x);
    else if(a==='react'){const mine=(x&&x.react||[]).some(r=>r.me&&r.e===b.dataset.e);await cxApi('/api/chats/react',{id:CX.cur,mid,emoji:mine?'':b.dataset.e});cxOpen(CX.cur,true)}
    else if(a==='reply'&&x){CX.edit=null;CX.reply={id:x.id,name:x.mine?t('Du','You'):x.name,text:x.text||cxKindWord(x.kind)};cxReplyBar();cxEl('cxtext').focus()}
    else if(a==='edit'&&x){CX.reply=null;CX.edit={id:x.id};cxEl('cxtext').value=x.text||'';cxGrow();cxReplyBar();cxEl('cxtext').focus()}
    else if(a==='copy'&&x){copyString(x.text||'',b)}
    else if(a==='back'&&x){if(!confirm(t('Diese Nachricht für alle zurücknehmen?','Take this message back for everybody?')))return;await cxApi('/api/chats/back',{id:CX.cur,mid});cxOpen(CX.cur,true)}}
  catch(err){cxSay(err.message)}});
cxEl('cxlog').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('cx-bub')){e.preventDefault();cxMenu(e.target.parentNode)}});
function cxJump(mid){const m=mid&&cxEl('cxlog').querySelector(`.cx-msg[data-mid="${CSS.escape(mid)}"]`);
  if(m){m.scrollIntoView({block:'center'});m.classList.add('flash');setTimeout(()=>m.classList.remove('flash'),1200)}}
function cxReplyBar(){const r=cxEl('cxreply'),s=r.querySelector('span');
  if(CX.edit){s.textContent=t('Nachricht ändern','Change message');r.hidden=false}
  else if(CX.reply){s.textContent=t('Antwort an ','Reply to ')+(CX.reply.name||'')+': '+CX.reply.text.slice(0,80);r.hidden=false}
  else r.hidden=true}
cxEl('cxreplyx').addEventListener('click',()=>{if(CX.edit)cxEl('cxtext').value='';CX.reply=null;CX.edit=null;cxReplyBar();cxGrow()});
// the composer: Enter sends (Shift+Enter a new line; on a phone the key makes a new line, the arrow sends)
function cxGrow(){const ta=cxEl('cxtext');ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,160)+'px'}
cxEl('cxtext').addEventListener('input',()=>{cxGrow();const now=Date.now();
  if(CX.cur&&now-CX.typeSent>4000&&cxEl('cxtext').value.trim()){CX.typeSent=now;cxApi('/api/chats/typing',{id:CX.cur}).catch(()=>{})}});
cxEl('cxtext').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&!matchMedia('(pointer:coarse)').matches){e.preventDefault();cxEl('cxcomp').requestSubmit()}
  if(e.key==='Escape'&&(CX.reply||CX.edit))cxEl('cxreplyx').click()});
cxEl('cxcomp').addEventListener('submit',async e=>{e.preventDefault();if(CX.busy)return;const ta=cxEl('cxtext'),text=ta.value.trim();if(!text||!CX.cur)return;
  CX.busy=true;cxEl('cxsend').disabled=true;
  try{if(CX.edit)await cxApi('/api/chats/edit',{id:CX.cur,mid:CX.edit.id,text});
    else await cxApi('/api/chats/send',{id:CX.cur,text,reply:CX.reply?CX.reply.id:''});
    ta.value='';CX.reply=null;CX.edit=null;cxReplyBar();cxGrow();CX.typeSent=0;
    await cxOpen(CX.cur,true);const log=cxEl('cxlog');log.scrollTop=log.scrollHeight;cxLoad()}
  catch(err){cxSay(err.message)}finally{CX.busy=false;cxEl('cxsend').disabled=false}});
// a short line above the composer for what did not work (the panel's sentence)
let cxSayT=0;
function cxSay(text){const w=cxEl('cxwhy');w.hidden=false;w.textContent=cxTr(text);w.classList.add('err');clearTimeout(cxSayT);
  cxSayT=setTimeout(()=>{w.classList.remove('err');if(CX.data)cxTop();else w.hidden=true},6000)}

// ---------------------------------------------------------------- new chat, new group, info (one pane in the right part)
function cxPane(k){CX.pane=k;const p=cxEl('cxpane');p.hidden=!k;if(!k){p.innerHTML='';if(CX.data){cxEl('cxlog').hidden=false;cxTop()}return}
  box().classList.add('sel');cxEl('cxempty').hidden=true;cxEl('cxlog').hidden=true;cxEl('cxcomp').hidden=true;cxEl('cxreply').hidden=true;cxEl('cxwhy').hidden=true;
  cxEl('cxtop').hidden=false;const tt=cxEl('cxtitle');tt.querySelector('small').hidden=true;
  cxEl('cxinfo').hidden=k==='new'||k==='group'||k==='invite'||!CX.data;
  tt.querySelector('b').textContent=k==='new'?t('Neuer Chat','New chat'):k==='group'?t('Neue Gruppe','New group'):k==='invite'?t('Jemanden einladen','Invite someone'):t('Chat-Info','Chat info');
  if(k==='new')cxNew();else if(k==='group')cxGroup();else if(k==='invite')cxInvite();else if(k==='info')cxInfo();else if(k==='add')cxAdd()}
const cxPeople=(list,sel)=>list.length?`<div class="cx-people">${list.map(p=>`<label class="cx-pp">${sel?`<input type="checkbox" data-pp="${esc(p.id)}"${CX.pick.has(p.id)?' checked':''}>`:''}`+
  `${cxAva(p.id,p.name)}<span>${esc(p.name)}</span>${sel?'':`<button type="button" class="b" data-cxn="one" data-to="${esc(p.id)}">${esc(t('Schreiben','Write'))}</button>`}</label>`).join('')}</div>`
  :`<div class="cx-none mut">${esc(t('Niemand nimmt gerade Nachrichten von dir an. Jede Person schaltet das unter Ich → Gespräch → Chats selbst ein.','Nobody takes messages from you right now. Each person switches that on under Me → Conversation → Chats.'))}</div>`;
function cxNew(){const S=CX.S||{contacts:[]},p=cxEl('cxpane');
  p.innerHTML=(S.groups?`<button type="button" class="cx-bigrow" data-cxn="group">${cxAva('g','',true)}<b>${esc(t('Neue Gruppe','New group'))}</b></button>`:'')+
    (S.invite||S.invite_switch?`<button type="button" class="cx-bigrow" data-cxn="invite"><span class="cx-ava inv">✉️</span><b>${esc(t('Jemanden einladen','Invite someone'))}</b></button>`:'')+
    `<div class="cx-grp">${esc(t('Personen','People'))}</div>`+cxPeople(S.contacts||[],false);cxHues(p)}
function cxGroup(){const S=CX.S||{contacts:[]},p=cxEl('cxpane');CX.pick.clear();
  p.innerHTML=`<label class="cx-lbl" for="cxgname">${esc(t('Name der Gruppe','Name of the group'))}</label><input id="cxgname" maxlength="40" autocomplete="off" placeholder="${esc(t('z. B. Familie','e.g. Family'))}">`+
    `<div class="cx-grp">${esc(t('Wer ist dabei?','Who is in?'))}</div>`+cxPeople(S.contacts||[],true)+
    `<div class="cx-acts2"><button type="button" class="b p" data-cxn="make">${esc(t('Gruppe erstellen','Create group'))}</button><button type="button" class="b" data-cxn="cancel">${esc(t('Abbrechen','Cancel'))}</button></div><div class="cx-msgline mut" id="cxpmsg"></div>`;
  cxHues(p);cxEl('cxgname').focus()}
function cxAdd(){const d=CX.data,S=CX.S||{contacts:[]},p=cxEl('cxpane');CX.pick.clear();const inn=new Set(d.members.map(m=>m.id));
  p.innerHTML=`<div class="cx-grp">${esc(t('Hinzufügen','Add'))}</div>`+cxPeople((S.contacts||[]).filter(x=>!inn.has(x.id)),true)+
    `<div class="cx-acts2"><button type="button" class="b p" data-cxn="addgo">${esc(t('Hinzufügen','Add'))}</button><button type="button" class="b" data-cxn="info">${esc(t('Zurück','Back'))}</button></div><div class="cx-msgline mut" id="cxpmsg"></div>`;cxHues(p)}
function cxInfo(){const d=CX.data,p=cxEl('cxpane');if(!d){cxPane('');return}
  const sel=(id,list,val,dis)=>`<select id="${id}"${dis?' disabled':''}>${list.map(([v,l])=>`<option value="${v}"${v===val?' selected':''}>${esc(l)}</option>`).join('')}</select>`;
  const muteV=d.mute===-1?-1:d.mute?(d.mute-Date.now()/1000>3*3600?28800:3600):0,may=d.kind==='one'||d.admin;
  let h=`<div class="cx-ihead">${cxAva(d.kind==='group'?d.id:(d.members.find(m=>m.id!==cxMe())||{}).id,cxTitle(d.title),d.kind==='group')}<b>${esc(cxTitle(d.title))}</b>`+
    `<small class="mut">${esc(d.kind==='group'?d.members.length+' '+t('Personen','people'):t('Chat zu zweit','Chat for two'))}</small></div>`;
  if(d.kind==='group'&&d.admin)h+=`<div class="cx-sw"><label for="cxname">${esc(t('Name','Name'))}</label><span class="cx-inl"><input id="cxname" maxlength="40" value="${esc(cxTitle(d.title))}"><button type="button" class="b" data-cxn="rename">${esc(t('Speichern','Save'))}</button></span></div>`;
  h+=`<div class="cx-sw"><label for="cxmute">${esc(t('Stumm','Mute'))}<small class="mut">${esc(t('Keine Mitteilungen aufs Handy, nur für dich','No notifications to the phone, only for you'))}</small></label>${sel('cxmute',CX_MUTE,muteV)}</div>`+
    `<div class="cx-sw"><label for="cxvan">${esc(t('Nachrichten verschwinden','Messages disappear'))}<small class="mut">${esc(may?t('Für alle in diesem Chat','For everybody in this chat'):t('Stellen die Admins der Gruppe ein','Set by the group\'s admins'))}</small></label>${sel('cxvan',CX_VANISH,d.vanish,!may)}</div>`;
  if(d.kind==='group'){h+=`<div class="cx-grp">${esc(t('Mitglieder','Members'))}</div><div class="cx-people">`+d.members.map(m=>`<div class="cx-pp">${cxAva(m.id,m.name)}<span>${esc(m.name||t('Gelöschtes Profil','Deleted profile'))}${m.admin?` <small class="mut">${esc(t('Admin','admin'))}</small>`:''}</span>`+
      (d.admin&&m.id!==cxMe()?`<span class="cx-mact">${m.admin?'':`<button type="button" class="b" data-cxn="mkadm" data-to="${esc(m.id)}">${esc(t('Zum Admin','Make admin'))}</button>`}<button type="button" class="b danger" data-cxn="rm" data-to="${esc(m.id)}">${esc(t('Entfernen','Remove'))}</button></span>`:'')+`</div>`).join('')+`</div>`;
    if(d.admin)h+=`<div class="cx-acts2"><button type="button" class="b" data-cxn="add">${esc(t('Personen hinzufügen','Add people'))}</button></div>`}
  h+=`<div class="cx-acts2"><button type="button" class="b danger" data-cxn="clear">${esc(t('Chat für mich leeren','Clear chat for me'))}</button>`+
    (d.kind==='group'?`<button type="button" class="b danger" data-cxn="leave">${esc(t('Gruppe verlassen','Leave group'))}</button>`:'')+`</div>`+
    `<div class="cx-msgline mut" id="cxpmsg"></div><div class="cx-acts2"><button type="button" class="b p" data-cxn="done">${esc(t('Fertig','Done'))}</button></div>`;
  p.innerHTML=h;cxHues(p)}
cxEl('cxnew').addEventListener('click',()=>{cxFindReset();if(!CX.cur){CX.data=null}cxPane('new')});
cxEl('cxinfo').addEventListener('click',()=>{if(CX.pane==='info'){cxPane('');return}if(CX.data)cxPane('info')});
cxEl('cxtitle').addEventListener('click',()=>{if(CX.data&&!CX.pane)cxPane('info')});
cxEl('cxpane').addEventListener('change',async e=>{const el=e.target;
  if(el.dataset.pp){if(el.checked)CX.pick.add(el.dataset.pp);else CX.pick.delete(el.dataset.pp);return}
  try{if(el.id==='cxmute')await cxApi('/api/chats/opts',{id:CX.cur,mute:+el.value});
    else if(el.id==='cxvan')await cxApi('/api/chats/opts',{id:CX.cur,vanish:+el.value});else return;
    await cxRefresh();cxPmsg(t('Gespeichert.','Saved.'))}catch(err){cxPmsg(err.message,true)}});
function cxPmsg(text,bad){const m=cxEl('cxpmsg');if(m){m.textContent=cxTr(text);m.classList.toggle('err',!!bad)}}
async function cxRefresh(){try{CX.data=await cxApi('/api/chats/items?id='+encodeURIComponent(CX.cur))}catch{}cxLoad()}
const cxLeft=l=>l&&l.length?' '+t('Nicht dabei, weil sie gerade keine Nachrichten von dir annehmen: ','Not in, because they do not take messages from you right now: ')+l.join(', '):'';
cxEl('cxpane').addEventListener('click',async e=>{const b=e.target.closest('[data-cxn]');if(!b)return;const a=b.dataset.cxn;
  try{if(a==='group')cxPane('group');
    else if(a==='invite')cxPane('invite');
    else if(a==='invmake'){const name=(cxEl('cxinvname')||{}).value||'';b.disabled=true;
      try{const r=await cxApi('/api/chats/invite',{name:name.trim(),base:location.origin});cxInvite(r)}finally{b.disabled=false}}
    else if(a==='invcopy')copyString(cxEl('cxinvlink').value,b);
    else if(a==='invshare'){try{await navigator.share({title:'Spark',text:t('Komm in meinen Chat auf dem Spark:','Join my chat on the Spark:'),url:cxEl('cxinvlink').value})}catch{}}
    else if(a==='invnew')cxInvite();
    else if(a==='invback'){if(!confirm(t('Diese Einladung zurückziehen? Der Link geht dann nicht mehr.','Withdraw this invitation? The link stops working.')))return;
      await cxApi('/api/chats/invite/back',{id:b.dataset.id});cxInvite()}
    else if(a==='cancel'){cxPane(CX.cur?'':'');if(!CX.cur)cxClose()}
    else if(a==='done')cxPane('');
    else if(a==='info')cxPane('info');
    else if(a==='add')cxPane('add');
    else if(a==='one'){const r=await cxApi('/api/chats/open',{to:b.dataset.to});CX.pane='';await cxOpen(r.id)}
    else if(a==='make'){const name=cxEl('cxgname').value.trim();if(!name){cxPmsg(t('Der Gruppe fehlt ein Name.','The group needs a name.'),true);return}
      if(!CX.pick.size){cxPmsg(t('Wähle mindestens eine Person.','Pick at least one person.'),true);return}
      const r=await cxApi('/api/chats/group',{name,members:[...CX.pick]});CX.pane='';await cxLoad();await cxOpen(r.id);if(r.left_out&&r.left_out.length)cxSay(cxLeft(r.left_out).trim())}
    else if(a==='addgo'){if(!CX.pick.size)return;const r=await cxApi('/api/chats/members',{id:CX.cur,add:[...CX.pick]});await cxRefresh();cxPane('info');cxPmsg(t('Hinzugefügt.','Added.')+cxLeft(r.left_out))}
    else if(a==='rm'){if(!confirm(t('Diese Person aus der Gruppe nehmen?','Take this person out of the group?')))return;await cxApi('/api/chats/members',{id:CX.cur,remove:[b.dataset.to]});await cxRefresh();cxInfo()}
    else if(a==='mkadm'){await cxApi('/api/chats/members',{id:CX.cur,admin:[b.dataset.to]});await cxRefresh();cxInfo()}
    else if(a==='rename'){await cxApi('/api/chats/opts',{id:CX.cur,name:cxEl('cxname').value});await cxRefresh();cxPmsg(t('Gespeichert.','Saved.'))}
    else if(a==='clear'){if(!confirm(t('Alle Nachrichten dieses Chats nur bei dir löschen? Die anderen behalten sie.','Delete all messages of this chat only for you? The others keep them.')))return;
      await cxApi('/api/chats/clear',{id:CX.cur});cxClose();cxLoad()}
    else if(a==='leave'){if(!confirm(t('Die Gruppe verlassen? Du bekommst danach keine Nachrichten mehr aus ihr.','Leave the group? You get no more messages from it afterwards.')))return;
      await cxApi('/api/chats/leave',{id:CX.cur});cxClose();cxLoad()}}
  catch(err){cxPmsg(err.message,true)}});
// ---------------------------------------------------------------- photos, files, voice messages (Schritt B)
// The file goes as the raw body, its name in the header X-Chat-Name (never in the address: access log). The Spark
// checks everything again (content, not name; photos saved anew without place data) and keeps it sealed.
const cxMediaUrl=(mid,part)=>'/api/chats/media?'+new URLSearchParams({id:CX.cur,mid,part});
function cxMediaHtml(x){const m=x.media||{};
  if(x.kind==='photo'){const w=+m.w||4,h=+m.h||3,f=Math.min(1,240/Math.max(w,h));
    return `<button type="button" class="cx-ph" data-cxa="photo" data-mid="${esc(x.id)}" aria-label="${esc(t('Foto groß zeigen','Show photo large'))}"><img loading="lazy" src="${esc(cxMediaUrl(x.id,'t'))}" width="${Math.round(w*f)}" height="${Math.round(h*f)}" alt="${esc(t('Foto','Photo'))}"></button>`}
  if(x.kind==='voice')return `<span class="cx-voice"><audio controls preload="none" src="${esc(cxMediaUrl(x.id,'f'))}"></audio><small class="mut">🎤 ${esc(cxDur(m.secs))}</small></span>`;
  if(x.kind==='file')return `<a class="cx-file" href="${esc(cxMediaUrl(x.id,'f'))}" download="${esc(m.name||'')}"><span class="cx-fi">📄</span><span><b>${esc(m.name||t('Datei','File'))}</b><small class="mut">${esc((m.ext||'').toUpperCase()+' · '+cxSize(m.size))}</small></span></a>`;
  return ''}
function cxBig(x){cxEl('cxbigimg').src=cxMediaUrl(x.id,'f');cxEl('cxbig').hidden=false;cxEl('cxbigx').focus()}
function cxBigClose(){const b=cxEl('cxbig');if(b.hidden)return false;b.hidden=true;cxEl('cxbigimg').removeAttribute('src');return true}
cxEl('cxbig').addEventListener('click',cxBigClose);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&CX.shown)cxBigClose()});
function cxNote(text){const w=cxEl('cxwhy');if(text){w.hidden=false;w.classList.remove('err');w.textContent=text}else if(CX.data)cxTop()}
async function cxUpload(kind,blob,name){if(!CX.cur||CX.busy)return;const L2=(CX.S&&CX.S.limits)||{},mb=kind==='photo'?L2.photo_mb:kind==='file'?L2.file_mb:0;
  if(mb&&blob.size>mb*1048576){cxSay(t('Zu groß: höchstens ','Too large: at most ')+mb+' MB.');return}
  CX.busy=true;cxNote(kind==='voice'?t('Sprachnachricht wird gesendet …','Sending voice message …'):t('Wird gesendet …','Sending …'));
  try{const q=new URLSearchParams({id:CX.cur,kind,reply:CX.reply?CX.reply.id:''}),h={'Content-Type':'application/octet-stream'};
    if(name)h['X-Chat-Name']=encodeURIComponent(String(name).slice(0,200));
    await api('/api/chats/media?'+q,{method:'POST',headers:h,body:blob});
    CX.reply=null;cxReplyBar();cxNote('');await cxOpen(CX.cur,true);const log=cxEl('cxlog');log.scrollTop=log.scrollHeight;cxLoad()}
  catch(err){cxSay(err.message)}finally{CX.busy=false}}
cxEl('cxatt').addEventListener('click',()=>cxEl('cxfile').click());
cxEl('cxfile').addEventListener('change',()=>{const f=cxEl('cxfile').files[0];cxEl('cxfile').value='';if(!f)return;
  cxUpload(/^image\//.test(f.type)?'photo':'file',f,f.name)});
// a voice message: tap 🎤, speak, ➤ sends (✕ throws it away); at most voice_secs, then it sends by itself
const CXR={rec:null,chunks:[],t0:0,tick:0,send:false};
async function cxRecStart(){if(CXR.rec||CX.busy||!CX.cur)return;
  if(!navigator.mediaDevices||!window.MediaRecorder){cxSay(t('Dieser Browser kann keine Sprachnachricht aufnehmen.','This browser cannot record a voice message.'));return}
  let st;try{st=await navigator.mediaDevices.getUserMedia({audio:true})}
  catch{cxSay(t('Kein Mikrofon: Die Seite braucht https und deine Erlaubnis im Browser.','No microphone: the page needs https and your permission in the browser.'));return}
  const mt=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(m=>MediaRecorder.isTypeSupported&&MediaRecorder.isTypeSupported(m))||'';
  let r;try{r=new MediaRecorder(st,mt?{mimeType:mt}:undefined)}catch{st.getTracks().forEach(x=>x.stop());cxSay(t('Aufnahme geht hier nicht.','Recording does not work here.'));return}
  CXR.rec=r;CXR.chunks=[];CXR.send=false;
  r.ondataavailable=e=>{if(e.data&&e.data.size)CXR.chunks.push(e.data)};
  r.onstop=()=>{st.getTracks().forEach(x=>x.stop());clearInterval(CXR.tick);const send=CXR.send,blob=new Blob(CXR.chunks,{type:r.mimeType||'audio/webm'});
    CXR.rec=null;CXR.chunks=[];cxRecBar(false);if(send&&blob.size)cxUpload('voice',blob,'')};
  r.start(1000);CXR.t0=Date.now();cxRecBar(true);CXR.tick=setInterval(cxRecTime,250)}
function cxRecTime(){const s=Math.floor((Date.now()-CXR.t0)/1000),max=(CX.S&&CX.S.limits&&CX.S.limits.voice_secs)||300;
  cxEl('cxrect').textContent=cxDur(s);if(s>=max)cxRecStop(true)}
function cxRecStop(send){if(!CXR.rec)return;CXR.send=!!send;try{CXR.rec.stop()}catch{}}
function cxRecBar(on){cxEl('cxrec').hidden=!on;if(on)cxRecTime();if(CX.data)cxTop();else cxEl('cxcomp').hidden=true}
cxEl('cxmic').addEventListener('click',cxRecStart);
cxEl('cxrecx').addEventListener('click',()=>cxRecStop(false));
cxEl('cxrecgo').addEventListener('click',()=>cxRecStop(true));

// ---------------------------------------------------------------- invite someone who has no profile yet
async function cxInvite(made){const p=cxEl('cxpane');let d;
  try{d=await cxApi('/api/chats/invites')}catch(e){p.innerHTML=`<div class="cx-msgline err">${esc(cxTr(e.message))}</div>`;return}
  if(CX.pane!=='invite')return;
  if(!d.on){p.innerHTML=`<div class="cx-none mut">${esc(t('Einladungen gehen erst, wenn der Admin unter Personen und Geräte → Neue Personen „nur mit Einladung“ einstellt.','Invitations only work once the admin sets "only by invitation" under People and devices → New people.'))}</div>`;return}
  const until=ts=>new Date(ts*1000).toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'short'});
  let h=`<div class="intro sm">${esc(t('Für jemanden, der noch kein Profil hat: Link oder QR-Code schicken. Die Person wählt Name und PIN und ist sofort im Chat mit dir. Jede Einladung gilt '+d.days+' Tage und nur einmal.',
    'For someone who has no profile yet: send the link or QR code. They pick a name and PIN and are in the chat with you at once. Each invitation works '+d.days+' days and only once.'))}</div>`;
  if(made)h+=`<div class="cx-inv"><div class="cx-qr">${made.qr}</div><label class="cx-lbl" for="cxinvlink">${esc(t('Link','Link'))}</label><input id="cxinvlink" readonly value="${esc(made.link)}">`+
    `<div class="cx-acts2"><button type="button" class="b p" data-cxn="invcopy">${esc(t('Link kopieren','Copy link'))}</button>`+
    (navigator.share?`<button type="button" class="b" data-cxn="invshare">${esc(t('Teilen','Share'))}</button>`:'')+
    `<button type="button" class="b" data-cxn="invnew">${esc(t('Fertig','Done'))}</button></div><div class="mut sm">${esc(t('Der Link ist nur jetzt zu sehen.','The link is shown only now.'))}</div></div>`;
  else if(d.open.length<d.max)h+=`<label class="cx-lbl" for="cxinvname">${esc(t('Name (Vorschlag, die Person kann ihn ändern)','Name (a suggestion, the person can change it)'))}</label>`+
    `<input id="cxinvname" maxlength="40" autocomplete="off" placeholder="${esc(t('z. B. Oma','e.g. Grandma'))}">`+
    `<div class="cx-acts2"><button type="button" class="b p" data-cxn="invmake">${esc(t('Einladung erstellen','Make invitation'))}</button></div>`;
  else h+=`<div class="cx-none mut">${esc(t('Du hast schon '+d.max+' offene Einladungen. Zieh eine zurück, um eine neue zu machen.','You already have '+d.max+' open invitations. Withdraw one to make a new one.'))}</div>`;
  if(d.open.length)h+=`<div class="cx-grp">${esc(t('Offene Einladungen','Open invitations'))}</div><div class="cx-people">`+d.open.map(i=>`<div class="cx-pp"><span>${esc(i.name||t('ohne Namen','no name'))} · ${esc(t('bis ','until ')+until(i.until))}</span>`+
    `<button type="button" class="b" data-cxn="invback" data-id="${esc(i.id)}">${esc(t('Zurückziehen','Withdraw'))}</button></div>`).join('')+`</div>`;
  h+=`<div class="cx-msgline mut" id="cxpmsg"></div>`;p.innerHTML=h;if(cxEl('cxinvname'))cxEl('cxinvname').focus()}

// the app view (appview.js): one level back on a phone closes the open chat
window.cxDepth=()=>CX.shown&&(!cxEl('cxbig').hidden||box().classList.contains('sel'))?1:0;
window.cxBackStep=()=>{if(cxBigClose())return true;if(!window.cxDepth())return false;cxEl('cxback').click();return true};
