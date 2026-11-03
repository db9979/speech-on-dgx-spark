// „Für dich“ (fuerdich.py, plan persoenlicher-assistent, stages 1 and 2): what the Spark found in the own mails by fixed
// rules (bill, contract, order, offer, open reply, phishing). Every card names the mail it comes from; nothing happens
// until the person presses. Sender names and subjects are outside text: shown with textContent only, never as a link.
let FUER_ON=false,FUER=null,FUER_TRIES=0;
const FUER_ICON={verdacht:'x',rechnung:'pdf',vertrag:'pen',antwort:'mail',bestellung:'folder',angebot:'spark'};
const FUER_KIND={verdacht:t('Verdacht','Suspicious'),rechnung:t('Rechnung','Bill'),vertrag:t('Vertrag','Contract'),
  antwort:t('Antwort offen','Reply missing'),bestellung:t('Bestellung','Order'),angebot:t('Angebot','Offer')};
const fuerMsg=(x,err)=>{const m=$('fuermsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
// the server answers at once with the last reading; the first one ever may still be loading: then asked again after
// 3 s (at most 5 times) while it reads in the background (fuerdich.api_get)
async function showFuerDich(fresh,again){const box=$('fuerbox');if(!box)return;if(!PROFILE||!FUER_ON){box.textContent='';return}
  if(!FUER){box.textContent='';box.appendChild(icEl('div','fh',t('Lese deine Mails …','Reading your mails …')))}
  let d;try{d=await (await api('/api/profile/fuerdich'+(fresh?'?fresh=1':''))).json()}catch(e){FUER=null;box.textContent='';box.appendChild(icEl('div','fh err',e.message));return}
  FUER_TRIES=again?FUER_TRIES+1:0;
  if(d.loading){if(FUER_TRIES<5)setTimeout(()=>{if(box.isConnected&&!box.hidden)showFuerDich(false,true)},3000);
    if(FUER)return;box.textContent='';box.appendChild(icEl('div','fh',t('Lese deine Mails … das dauert beim ersten Mal etwas, die Seite zeigt sie von selbst.','Reading your mails … the first time takes a moment, the page shows them by itself.')));return}
  FUER=d;fuerRender()}
async function fuerMark(id,as){try{await api('/api/profile/fuerdich/mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,as})})}
  catch(e){fuerMsg(e.message,true);return}
  FUER.items=FUER.items.filter(x=>x.id!==id);fuerRender();fuerMsg(as==='done'?t('Als erledigt markiert.','Marked as done.'):t('Kommt nicht wieder.','Will not come back.'))}
// stage 2 (Dominik 2026-10-18 „5a“): the buttons the panel allows for a card (fuerdich.acts, fixed rules). Erinnern sets
// a reminder with a fixed text, Eintragen hands a fixed line to „Schnell eintragen“ of the page Kalender (only its
// „Eintragen“ saves), Antwort and Kündigung open the mail page; there only the preview sheet sends
async function fuerAct(x,b){b.disabled=true;
  try{const r=await api('/api/profile/fuerdich/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:x.id,do:'remind'})});const d=await r.json();
    fuerMsg(t('Erinnerung gesetzt: ','Reminder set: ')+d.text+' · '+new Date(d.due).toLocaleString(kalLoc(),{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))}
  catch(e){b.disabled=false;fuerMsg(e.message,true)}}
async function fuerCancel(x,b){b.disabled=true;
  try{const d=await (await api('/api/profile/fuerdich/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:x.id,do:'cancel'})})).json();
    await postFromFuer('',d)}catch(e){fuerMsg(e.message,true)}b.disabled=false}
// stage 3 („3a“): „Mehr davon“ makes the shop of an order or offer a confirmed interest (Ich → Was ich über dich weiß)
async function fuerMore(x,b){b.disabled=true;
  try{const d=await (await api('/api/profile/fuerdich/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:x.id,do:'more'})})).json();
    for(const y of FUER.items)if(y.who===x.who){y.fits=d.name;y.acts=(y.acts||[]).filter(a=>a!=='more')}fuerRender();
    fuerMsg(t('Gemerkt: „','Noted: "')+d.name+t('“ interessiert dich. Ändern unter Ich → Was ich über dich weiß.','" interests you. Change it under Me → What I know about you.'))}
  catch(e){b.disabled=false;fuerMsg(e.message,true)}}
function fuerEvent(x){KAL.q=x.event;KAL.qi=null;KAL.qfocus=true;icTabSet('cal','show');goSec('cal')}
function fuerButtons(x){const a=x.acts||[],out=[];
  if(a.includes('remind')){const b=icBtn('bell',t('Erinnern','Remind me'),b=>fuerAct(x,b));b.dataset.fuerRemind=x.id;out.push(b)}
  if(a.includes('event')&&x.event&&typeof KAL!=='undefined'){const b=icBtn('cal',t('Eintragen','Add to calendar'),()=>fuerEvent(x));b.dataset.fuerEvent=x.id;out.push(b)}
  if(a.includes('reply')&&window.postFromFuer){const b=icBtn('reply',t('Antwort entwerfen','Draft a reply'),()=>postFromFuer(x.ref));b.dataset.fuerReply=x.id;out.push(b)}
  if(a.includes('cancel')&&window.postFromFuer){const b=icBtn('pen',t('Kündigung entwerfen','Draft a cancellation'),b=>fuerCancel(x,b));b.dataset.fuerCancel=x.id;out.push(b)}
  if(a.includes('more')){const b=icBtn('spark',t('Mehr davon','More of this'),b=>fuerMore(x,b));b.dataset.fuerMore=x.id;out.push(b)}
  return out}
function fuerItem(x){const E=icEl,meta=[FUER_KIND[x.kind]||x.kind,x.fits?t('passt zu „','fits "')+x.fits+t('“','"'):'',x.line,t('aus ','from ')+x.who+(x.subject?' · „'+x.subject+'“':'')].filter(Boolean).join(' · ');
  const ok=icBtn('check',t('Erledigt','Done'),()=>fuerMark(x.id,'done'));ok.dataset.fuerDone=x.id;
  const no=icBtn('x',x.kind==='verdacht'?t('Ist echt','Is genuine'):t('Nicht interessant','Not interesting'),()=>fuerMark(x.id,'no'));no.dataset.fuerNo=x.id;
  const lead=E('span','fd-ico'+(x.urgent?' hot':''));lead.appendChild(icSvg(FUER_ICON[x.kind]||'mail',16));
  const r=icRow(x.title,meta,[...fuerButtons(x),ok,no],lead);r.dataset.fuerKind=x.kind;return r}
function fuerRender(){const d=FUER,box=$('fuerbox'),E=icEl;if(!box||!d)return;box.textContent='';
  box.appendChild(E('h3','sec',t('Für dich','For you')));
  box.appendChild(E('div','intro',t('Was der Spark in deinen Mails gefunden hat: Rechnungen mit Frist, Verträge, die sich verlängern, Bestellungen, Angebote, Fragen ohne Antwort und Mails, die sich als Bank oder Shop ausgeben. Feste Regeln, kein Modell; die Mails bleiben ungelesen und unverändert. Links aus Mails öffnet der Spark nie.',
    'What the Spark found in your mails: bills with a deadline, contracts that renew, orders, offers, questions without an answer and mails that pretend to be a bank or shop. Fixed rules, no model; the mails stay unread and unchanged. The Spark never opens links from mails.')));
  if(d.nomail){box.appendChild(E('div','fh',t('Erst unter E-Mail → Einstellungen ein Postfach verbinden.','Connect a mailbox under E-mail → Settings first.')));return}
  const urgent=d.items.filter(x=>x.urgent),rest=d.items.filter(x=>!x.urgent);
  const again=E('button','b',t('Neu lesen','Read again'));again.type='button';again.id='fuerfresh';
  again.onclick=async()=>{again.disabled=true;fuerMsg(t('Lese deine Mails …','Reading your mails …'));await showFuerDich(true);fuerMsg('')};
  const menu=[{label:t('Markierungen vergessen','Forget the marks'),danger:true,act:async()=>{if(!confirm(t('Alle als erledigt oder uninteressant markierten Karten wieder zeigen?','Show every card marked as done or not interesting again?')))return;
    try{await api('/api/profile/fuerdich',{method:'DELETE'})}catch(e){fuerMsg(e.message,true);return}await showFuerDich(true)}}];
  box.appendChild(icCard('mail',t('Für dich','For you'),t(`${urgent.length} brauchen dich · ${rest.length} gut zu wissen`,`${urgent.length} need you · ${rest.length} good to know`),[again],menu));
  const m=E('div','fh');m.id='fuermsg';box.appendChild(m);
  for(const e of d.errors||[])box.appendChild(E('div','fh err',t('Postfach nicht lesbar: ','Mailbox not readable: ')+e));
  // stage 4 („7a“, „4a“): this month's sum from checked amounts and the tip of the day; the tip's address only as an
  // https link in a new tab without the Spark's address (noreferrer), its title as text
  if(d.month)box.appendChild(E('div','fh',d.month.line));
  if(d.tip&&d.tip.url){const a=E('a','b',t('Öffnen','Open'));a.href=d.tip.url;a.target='_blank';a.rel='noopener noreferrer';
    box.appendChild(icList([icRow(d.tip.title,t('Tipp aus dem Netz zu „','Tip from the web for "')+d.tip.name+t('“ · ','" · ')+d.tip.domain,[a])]))}
  if(!d.items.length){box.appendChild(icEmpty(t('Gerade nichts, was dich braucht.','Nothing that needs you right now.')));return}
  if(urgent.length){box.appendChild(icGroup(t('Braucht dich','Needs you'),urgent.length));box.appendChild(icList(urgent.map(fuerItem)))}
  if(rest.length){box.appendChild(icGroup(t('Gut zu wissen','Good to know'),rest.length));box.appendChild(icList(rest.map(fuerItem)))}}
