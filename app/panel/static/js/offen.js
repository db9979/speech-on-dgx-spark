// Alles Offene im Assistenten (vorgaenge.py, plan assistent-zentrale/plan.md Stufe 1+2, Dominik 2026-10-20 „ok“): one
// store of this profile's Vorgänge for the card in the conversation, the line „Noch offen“ above it and the page Offen
// (Braucht dich · Später · Erledigt, list left, card right). A message of the conversation carries only the number
// ("vg"); the card is drawn from the store, so a button pressed on one device changes the card on every one (stream
// /api/profile/vorgaenge/stream sends only numbers, then ?seit=<rev>). The buttons are names the Spark sent
// (vorgaenge.AKTIONEN) and the Spark checks each again (rev: 409 when another device was quicker). Titles are the
// panel's words, a sender from a mail is outside text: everything through textContent (icEl), never innerHTML.
let VG_ON=false;
const VG={items:new Map(),rev:0,counts:{braucht:0,spaeter:0,erledigt:0},spaeter:{},seq:0,es:null,sel:'',grp:'braucht',art:'',msg:'',open:false,busy:''};
// the menu entry and the store only for a signed-in profile that may use it (start.js, like Listen)
window.vgStart=who=>{VG_ON=!!(who&&who.profile&&who.vorgaenge);document.querySelectorAll('nav button[data-s=offen]').forEach(b=>b.hidden=!VG_ON);
  if(VG_ON){vgLoad(true);vgStream()}else{if(VG.es){VG.es.close();VG.es=null}VG.items.clear();vgPaint()}};
async function vgLoad(all){if(!VG_ON)return;const seq=++VG.seq;
  const {r,d}=await apiTry('/api/profile/vorgaenge?seit='+(all?0:VG.rev));if(seq!==VG.seq||!r.ok)return;
  if(all)VG.items.clear();for(const x of d.items)VG.items.set(x.id,x);
  VG.rev=d.rev;VG.counts=d.counts;VG.spaeter=d.spaeter||{};vgPaint()}
// only numbers come: the changed ones are fetched; a new card is in today's conversation (convoLook shows it)
function vgStream(){if(VG.es||typeof EventSource==='undefined')return;const es=new EventSource('/api/profile/vorgaenge/stream');VG.es=es;
  es.onmessage=e=>{let d;try{d=JSON.parse(e.data)}catch{return}if(!d||d.type!=='vorgang'||d.rev<=VG.rev)return;
    vgLoad(!!d.weg);if(d.neu&&typeof convoLook==='function')convoLook(true)};
  es.onerror=()=>{if(es.readyState===2){VG.es=null;setTimeout(()=>{if(VG_ON)vgStream()},30e3)}}}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&VG_ON)vgLoad(false)});
const vgName=x=>L==='en'?x.art_en:x.art_de;
const vgWhen=s=>{if(!s)return '';const d=new Date(s*1000),n=new Date(),tm=new Date(n.getFullYear(),n.getMonth(),n.getDate()+1),
    hm=d.toLocaleTimeString(kalLoc(),{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===n.toDateString()?t('heute ','today ')+hm:d.toDateString()===tm.toDateString()?t('morgen ','tomorrow ')+hm
    :d.toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'numeric'})+' '+hm};
const vgFrist=f=>{if(!f)return null;const d=new Date(f+'T12:00'),n=new Date(),days=Math.round((d-new Date(n.getFullYear(),n.getMonth(),n.getDate(),12))/864e5);
  return [days<=0?t('heute fällig','due today'):days===1?t('morgen fällig','due tomorrow'):t('fällig ','due ')+d.toLocaleDateString(kalLoc(),{day:'numeric',month:'numeric'}),days<=1]};
const WO_EN={Rechner:'computer',Handy:'phone',iPhone:'iPhone',Begleiter:'companion',Telegram:'Telegram'};
// how a proposal's card („Wartet auf dein Ja“, Stufe 2) ended when not by its yes
const VG_WIE={vs_nein:['Abgebrochen','Cancelled'],vs_aendern:['Weiter auf der Seite','Continued on the page'],beantwortet:['Im Gespräch beantwortet','Answered in the conversation'],
  ersetzt:['Neuer Vorschlag','New proposal'],fehler:['Nicht ausgeführt','Not done'],cx_gelesen:['Gelesen','Read'],
  geantwortet:['Beantwortet','Answered'],bestaetigt:['Bestätigt','Confirmed'],abgelehnt:['Abgelehnt','Declined'],wieder_da:['Läuft wieder','Running again']};
const VG_SYMS=new Set(['bell','check','mail','chat','share','warn','spark']),vgSym=x=>VG_SYMS.has(x.sym)?x.sym:'mail';
// the line under a card: what happened, where and when
function vgState(x){if(x.zustand==='spaeter')return x.spaeter_bis?t('Später: wieder da ','Later: back ')+vgWhen(x.spaeter_bis):t('Später, ohne Zeit','Later, no time');
  if(x.zustand==='erledigt'||x.zustand==='weg'){const how=x.wie==='abgelaufen'?t('Abgelaufen','Expired'):x.wie==='vs_ja'&&x.fertig?(L==='en'?x.fertig[1]:x.fertig[0])
      :VG_WIE[x.wie]?t(...VG_WIE[x.wie]):x.zustand==='weg'?t('Nicht wichtig','Not important')
      :x.wie==='fd_remind'?t('Erinnerung gesetzt','Reminder set'):x.wie==='fd_more'?t('Mehr davon gemerkt','More of this noted'):t('Erledigt','Done');
    return how+(x.wo?' · '+t('am ','on the ')+(L==='en'?WO_EN[x.wo]||x.wo:x.wo):'')+' · '+vgWhen(x.ge)}
  return ''}
// ---------------------------------------------------------------- the card
function vgCard(x,where){const el=icEl,c=el('div','vk'+(x.dringend?' hot':''));c.dataset.vg=x.id;
  if(x.gruppe==='erledigt'){c.className='vk-zu';c.append(el('span','vk-sym','✓'),el('span','',x.titel),el('small','mut',vgState(x)));
    if(VG.msg&&VG.msgId===x.id&&where!=='list')c.appendChild(el('div','fh'+(VG.msgOk?'':' err'),VG.msg));
    const b=el('button','b',t('Zurückholen','Bring back'));b.type='button';b.onclick=()=>vgAct(x,'zurueck','',b);if(x.acts.some(a=>a.k==='zurueck'))c.appendChild(b);return c}
  const k=el('div','vk-k'),sym=el('span','vk-sym');sym.appendChild(icSvg(vgSym(x),14));k.append(sym,el('b','',vgName(x)));
  const f=vgFrist(x.frist);if(f)k.appendChild(el('span','frist'+(f[1]?' warn':''),f[0]));
  c.append(k,el('b','vk-t',x.titel));if(x.zeile)c.appendChild(el('div','vk-z',x.zeile));
  if(x.felder&&x.felder.length){const dl=el('dl','vk-f');for(const [a,b] of x.felder){dl.append(el('dt','',t(a,{Von:'From',Betrag:'Amount'}[a]||a)),el('dd','',b))}c.appendChild(dl)}
  const bar=el('div','vk-b');let first=true;
  for(const a of x.acts.filter(a=>a.k!=='spaeter'&&a.k!=='zurueck')){const b=el('button','b'+(first?' p':''),L==='en'?a.en:a.de);b.type='button';first=false;
    b.onclick=()=>vgAct(x,a.k,'',b);bar.appendChild(b)}
  if(x.zustand==='spaeter'&&x.acts.some(a=>a.k==='zurueck')){const b=el('button','b',t('Jetzt zeigen','Show now'));b.type='button';b.onclick=()=>vgAct(x,'zurueck','',b);bar.appendChild(b)}
  if(x.acts.some(a=>a.k==='spaeter'))bar.appendChild(vgLater(x));
  c.appendChild(bar);const st=vgState(x);if(st)c.appendChild(el('div','vk-fuss',st));
  if(VG.msg&&VG.msgId===x.id&&where!=='list')c.appendChild(el('div','fh'+(VG.msgOk?'':' err'),VG.msg));
  return c}
// „Später ▾“: the four choices of vorgaenge.SPAETER, the time it comes back beside each
function vgLater(x){const el=icEl,w=el('span','vk-sp'),b=el('button','b',t('Später ▾','Later ▾'));b.type='button';b.setAttribute('aria-haspopup','true');
  const pop=el('div','ic-pop vk-pop');pop.hidden=true;
  for(const [k,[de,en]] of Object.entries(VG.spaeter)){const o=el('button','',L==='en'?en:de);o.type='button';o.onclick=()=>{pop.hidden=true;vgAct(x,'spaeter',k,b)};pop.appendChild(o)}
  b.onclick=e=>{e.stopPropagation();const open=!pop.hidden;document.querySelectorAll('.ic-pop').forEach(p=>p.hidden=true);pop.hidden=open};
  w.classList.add('ic-menu');w.append(b,pop);return w}
// one button: the Spark checks and answers with the card as it is now; "seite" opens the place where it goes on
async function vgAct(x,k,wann,btn){if(btn)btn.disabled=true;VG.msg='';VG.msgOk=false;
  const {r,d}=await apiTry('/api/profile/vorgaenge/act',xjson('POST',{id:x.id,act:k,rev:x.rev,wann,view:document.body.classList.contains('appview')?'app':undefined}));
  if(btn)btn.disabled=false;
  const det=d&&d.detail;
  if(r.status===409&&det&&det.item){VG.items.set(x.id,det.item);VG.msg=det.text;VG.msgId=x.id;vgPaint();return}
  if(!r.ok){VG.msg=errSay(r.status,det,"");VG.msgId=x.id;vgPaint();return}
  VG.items.set(x.id,d.item);VG.rev=Math.max(VG.rev,d.rev||0);
  if(d.text){VG.msg=d.text;VG.msgOk=!!d.gelungen;VG.msgId=x.id}   // the yes of a proposal: the checked result in the panel's words
  const a=x.acts.find(a=>a.k===k);if(a&&a.stufe==='seite')vgGo(x,k,d);
  vgLoad(false)}
function vgGo(x,k,d){const z=x.daten||{};
  if(k==='fd_event'&&typeof fuerEvent==='function'&&typeof KAL!=='undefined')fuerEvent({event:z.event});
  else if(k==='fd_reply'&&window.postFromFuer)postFromFuer(z.ref);
  else if(k==='fd_cancel'&&window.postFromFuer&&d.draft)postFromFuer('',d.draft)
  else if(k==='vs_aendern'&&d.event&&typeof fuerEvent==='function'&&typeof KAL!=='undefined')fuerEvent({event:d.event})   // the Kalender's form, filled
  else if(k==='vs_aendern'&&d.draft&&window.postFromFuer)postFromFuer('',d.draft)   // the writing window, filled; only its sheet sends
  else if(k==='oeffnen'&&z.weg)wayGo(z.weg)   // stages 3+4: only the place where it goes on (a fixed way of the panel)
  else if(k==='cx_antworten'&&z.chat&&typeof cxOpen==='function'){goSec('chats');cxOpen(z.chat)}
  else if(k==='ml_lesen'&&z.ref&&typeof postRead==='function'){icTabSet('post','show');goSec('post');postRead(z.ref)}}
// ---------------------------------------------------------------- in the conversation (chat.js openConvo)
window.vgMount=(b,m)=>{const d=b.parentNode;d.classList.add('vgmsg');d.dataset.vg=m.vg;vgFill(d)};
function vgFill(d){const x=VG.items.get(d.dataset.vg),b=d.querySelector('.bubble');if(!x||!b)return;   // unknown: the sentence stays
  b.textContent='';b.classList.remove('typing');b.classList.add('vgb');b.appendChild(vgCard(x,'chat'))}
// a proposal of this answer (chat.js, Stufe 2): its card under the answer, the Ja/Nein card until the store knows it
window.vgAttach=(id,fallback)=>{const d=icEl('div','vgatt');d.dataset.vg=id;d.appendChild(fallback);vgLoad(false).then(()=>vgFillAtt(d));return d};
function vgFillAtt(d){const x=VG.items.get(d.dataset.vg);if(!x)return;d.textContent='';d.appendChild(vgCard(x,'chat'))}
// a note of Von selbst or a reminder that rang with a card: the card here at once, the saved one comes with convoLook
window.vgLive=(id,text)=>{if(!document.querySelector('#chatlog .vgmsg[data-vg="'+id+'"]')){const b=chatLog('assistant',text);b.classList.add('pro');vgMount(b,{vg:id})}
  vgLoad(false).then(()=>{if(typeof convoLook==='function')convoLook(true)})};
// „Noch offen: 3“ above the conversation; open it for the titles, a tap opens the card on the page Offen
function vgStrip(){const log=$('chatlog');if(!log)return;let s=$('vgstrip');
  const need=[...VG.items.values()].filter(x=>x.gruppe==='braucht').sort((a,b)=>b.t-a.t);
  if(!VG_ON||!need.length){if(s)s.remove();return}
  if(!s){s=icEl('div','vgstrip');s.id='vgstrip';log.before(s)}
  s.textContent='';const head=icEl('button','vgs-h');head.type='button';head.setAttribute('aria-expanded',String(VG.open));
  head.append(icEl('b','',t('Noch offen: ','Still open: ')+need.length),icEl('span','mut',VG.counts.spaeter?' · '+VG.counts.spaeter+t(' später',' later'):''),icEl('span','vgs-c',VG.open?'▴':'▾'));
  head.onclick=()=>{VG.open=!VG.open;vgStrip()};s.appendChild(head);
  if(VG.open){for(const x of need.slice(0,6)){const r=icEl('button','vgs-r');r.type='button';r.append(icEl('span','mut',vgName(x)),icEl('span','',x.titel));r.onclick=()=>vgShow(x.id);s.appendChild(r)}
    s.appendChild(icLink(t('Alles auf der Seite Offen','Everything on the page Open'),()=>vgShow('')))}}
function vgShow(id){VG.sel=id;if(id){const x=VG.items.get(id);if(x)VG.grp=x.gruppe}icTabSet('offen','show');goSec('offen')}
// ---------------------------------------------------------------- the page Offen (OWN_PAGES vgbox)
const VG_GRP=[['braucht',t('Braucht dich','Needs you')],['spaeter',t('Später','Later')],['erledigt',t('Erledigt','Done')]];
window.vgOpen=()=>{if(!PROFILE)return;const root=$('vgroot'),box=$('vgbox');if(box){box.hidden=true;$('offen').appendChild(box)}root.textContent='';
  root.appendChild(icTabs('offen',[{k:'show',label:OWN_PAGES.vgbox[2],n:VG.counts.braucht||'',hot:!!VG.counts.braucht,body:vgBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('vgbox');b.hidden=false;vgSettings(b);return b}}]));
  vgLoad(true)};
function vgBody(){const w=document.createElement('div');w.className='ld-box ld-frame vg';w.id='vgview';vgPage(w);return w}
function vgPage(w){w.classList.toggle('ld-sel',!!VG.sel);
  if(!w.querySelector('.ld-split'))w.innerHTML='<div class="ld-split"><div class="ld-list"></div><div class="ld-detail vgdet" hidden></div></div>';
  const list=w.querySelector('.ld-list');list.textContent='';
  const chips=icEl('div','ld-chips');for(const [k,l] of VG_GRP)chips.appendChild(icChip(l+' '+(VG.counts[k]||0),VG.grp===k,()=>{VG.grp=k;VG.sel='';vgPaint()}));
  const arts=[...new Set([...VG.items.values()].map(x=>x.art))];
  if(arts.length>1)for(const a of arts){const x=[...VG.items.values()].find(y=>y.art===a);chips.appendChild(icChip(vgName(x),VG.art===a,()=>{VG.art=VG.art===a?'':a;vgPaint()},'vg-art'))}
  list.appendChild(chips);
  const rows=[...VG.items.values()].filter(x=>x.gruppe===VG.grp&&(!VG.art||x.art===VG.art))
    .sort(VG.grp==='spaeter'?(a,b)=>(a.spaeter_bis||9e9)-(b.spaeter_bis||9e9):VG.grp==='erledigt'?(a,b)=>b.ge-a.ge:(a,b)=>(b.dringend-a.dringend)||(b.t-a.t));
  if(!rows.length)list.appendChild(icEl('div','ld-empty mut',VG.grp==='braucht'?t('Nichts offen. Was dich braucht, kommt als Karte ins Gespräch und steht dann hier.','Nothing open. What needs you comes as a card into the conversation and then stands here.')
    :VG.grp==='spaeter'?t('Nichts für später.','Nothing for later.'):t('In den letzten 7 Tagen nichts erledigt.','Nothing done in the last 7 days.')));
  for(const x of rows){const r=icEl('div','ld-row'+(x.id===VG.sel?' on':''));r.setAttribute('role','button');r.tabIndex=0;
    const ic=icEl('span','ld-ico vk-sym');ic.appendChild(icSvg(vgSym(x),15));const mid=icEl('span','ld-mid');
    mid.append(icEl('b','',x.titel),icEl('small','',[vgName(x),vgState(x)||x.zeile].filter(Boolean).join(' · ')));
    const right=icEl('span','ld-right');const f=vgFrist(x.frist);if(f)right.appendChild(icEl('span','frist'+(f[1]?' warn':''),f[0]));
    r.append(ic,mid,right);const go=()=>{VG.sel=x.id;VG.msg='';vgPaint()};r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}};list.appendChild(r)}
  const det=w.querySelector('.vgdet'),x=VG.items.get(VG.sel);det.hidden=!x;det.textContent='';if(!x)return;
  if(NARROW()){const bk=icEl('button','b ld-back','‹ '+t('Offen','Open'));bk.type='button';bk.onclick=()=>{VG.sel='';vgPaint()};det.appendChild(bk)}
  det.appendChild(vgCard(x,'page'));
  const dl=icEl('dl','vk-f vg-facts'),add=(a,b)=>{if(b)dl.append(icEl('dt','',a),icEl('dd','',b))};
  add(t('Seit','Since'),vgWhen(x.t));add(t('Zustand','State'),{offen:t('offen','open'),gesehen:t('gesehen','seen'),spaeter:t('später','later'),erledigt:t('erledigt','done'),weg:t('weg','gone')}[x.zustand]);
  add(t('Gesehen','Seen'),x.zustand==='gesehen'?t('auf einem Gerät','on one device'):'');det.appendChild(dl);
  const ch=icLink(t('Im Gespräch zeigen','Show in the conversation'),()=>{goSec('chat');setTimeout(()=>{const m=document.querySelector('#chatlog .vgmsg[data-vg="'+x.id+'"]');if(m)m.scrollIntoView({block:'center'})},200)});
  det.appendChild(ch)}
// „Einstellungen“: what lands here and taking the done ones (or all) away; the switch itself is the admin's
async function vgSettings(b){b.textContent='';const c=VG.counts;
  b.appendChild(icEl('div','intro',t('Was dich braucht, kommt als Karte ins Gespräch des Tages: dringende Funde aus „Für dich“ (Rechnung, Vertrag, Antwort, Verdacht) und Erinnerungen, die geklingelt haben, dazu Vorschläge des Assistenten, die auf dein Ja warten (Termin, Mail, Aufräumen). Jede Karte hat feste Knöpfe; „Später“ legt sie hierher, sie kommt zur gewählten Zeit wieder. Erledigt ist auf jedem Gerät erledigt.',
    'What needs you comes as a card into the day\'s conversation: urgent finds from "For you" (bill, contract, reply, suspicion) and reminders that rang, and the assistant\'s proposals waiting for your yes (appointment, mail, tidy-up). Every card has fixed buttons; "Later" puts it here and it comes back at the chosen time. Done is done on every device.')));
  b.appendChild(icStats([[c.braucht||0,t('brauchen dich','need you'),!!c.braucht],[c.spaeter||0,t('später','later')],[c.erledigt||0,t('erledigt (7 Tage)','done (7 days)')]]));
  b.appendChild(icEl('div','fh',t('Ob eine Karte auch als Mitteilung kommt, stellst du unter Ich → Von selbst ein.','Whether a card also comes as a notification is set under Me → By itself.')));
  const msg=icEl('div','fh');
  const drop=async(nur,btn)=>{btn.disabled=true;const {r,d}=await apiTry('/api/profile/vorgaenge'+(nur?'?nur=erledigt':''),{method:'DELETE'});btn.disabled=false;
    msg.textContent=r.ok?(d.n===1?t('1 Vorgang entfernt.','1 item removed.'):d.n+t(' Vorgänge entfernt.',' items removed.')):errSay(r.status,d.detail,'');vgLoad(true)};
  const done=icEl('button','b',t('Erledigte entfernen','Remove the done ones'));done.type='button';done.onclick=()=>drop(true,done);
  const row=icEl('div','row');row.append(done,msg);b.appendChild(row);
  b.appendChild(icDanger(t('Alles Offene löschen','Delete everything open'),t('Die Karten und die Später-Liste sind dann weg. Mails und Erinnerungen bleiben, wo sie sind.','The cards and the later list are gone then. Mails and reminders stay where they are.'),
    t('Alles löschen','Delete all'),e=>{const btn=e.currentTarget;if(btn.dataset.sure){drop(false,btn);delete btn.dataset.sure;btn.textContent=t('Alles löschen','Delete all')}else{btn.dataset.sure='1';btn.textContent=t('Wirklich löschen?','Really delete?')}}))}
// ---------------------------------------------------------------- every place at once
function vgPaint(){document.querySelectorAll('#chatlog .vgmsg').forEach(vgFill);document.querySelectorAll('#chatlog .vgatt').forEach(vgFillAtt);vgStrip();
  const n=VG_ON?VG.counts.braucht||0:0;
  document.querySelectorAll('nav button[data-s=offen]').forEach(b=>{let s=b.querySelector('.ncnt');if(!s){s=icEl('span','ncnt');b.append(' ',s)}s.hidden=!n;s.textContent=n>99?'99+':String(n)});
  const w=$('vgview');if(w)vgPage(w)}
