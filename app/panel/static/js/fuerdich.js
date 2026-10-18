// „Für dich“ (fuerdich.py, plan persoenlicher-assistent, stage 1): what the Spark found in the own mails by fixed
// rules (bill, contract, order, offer, open reply, phishing). Every card names the mail it comes from; nothing happens
// until the person presses. Sender names and subjects are outside text: shown with textContent only, never as a link.
let FUER_ON=false,FUER=null;
const FUER_ICON={verdacht:'x',rechnung:'pdf',vertrag:'pen',antwort:'mail',bestellung:'folder',angebot:'spark'};
const FUER_KIND={verdacht:t('Verdacht','Suspicious'),rechnung:t('Rechnung','Bill'),vertrag:t('Vertrag','Contract'),
  antwort:t('Antwort offen','Reply missing'),bestellung:t('Bestellung','Order'),angebot:t('Angebot','Offer')};
const fuerMsg=(x,err)=>{const m=$('fuermsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
async function showFuerDich(fresh){const box=$('fuerbox');if(!box)return;if(!PROFILE||!FUER_ON){box.textContent='';return}
  if(!FUER){box.textContent='';box.appendChild(icEl('div','fh',t('Lese deine Mails …','Reading your mails …')))}
  try{FUER=await (await api('/api/profile/fuerdich'+(fresh?'?fresh=1':''))).json()}catch(e){FUER=null;box.textContent='';box.appendChild(icEl('div','fh err',e.message));return}
  fuerRender()}
async function fuerMark(id,as){try{await api('/api/profile/fuerdich/mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,as})})}
  catch(e){fuerMsg(e.message,true);return}
  FUER.items=FUER.items.filter(x=>x.id!==id);fuerRender();fuerMsg(as==='done'?t('Als erledigt markiert.','Marked as done.'):t('Kommt nicht wieder.','Will not come back.'))}
function fuerItem(x){const E=icEl,meta=[FUER_KIND[x.kind]||x.kind,x.line,t('aus ','from ')+x.who+(x.subject?' · „'+x.subject+'“':'')].filter(Boolean).join(' · ');
  const ok=icBtn('check',t('Erledigt','Done'),()=>fuerMark(x.id,'done'));ok.dataset.fuerDone=x.id;
  const no=icBtn('x',x.kind==='verdacht'?t('Ist echt','Is genuine'):t('Nicht interessant','Not interesting'),()=>fuerMark(x.id,'no'));no.dataset.fuerNo=x.id;
  const lead=E('span','fd-ico'+(x.urgent?' hot':''));lead.appendChild(icSvg(FUER_ICON[x.kind]||'mail',16));
  const r=icRow(x.title,meta,[ok,no],lead);r.dataset.fuerKind=x.kind;return r}
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
  for(const e of d.errors||[])box.appendChild(E('div','fh err','⚠ '+t('Postfach nicht lesbar: ','Mailbox not readable: ')+e));
  if(!d.items.length){box.appendChild(icEmpty(t('Gerade nichts, was dich braucht.','Nothing that needs you right now.')));return}
  if(urgent.length){box.appendChild(icGroup(t('Braucht dich','Needs you'),urgent.length));box.appendChild(icList(urgent.map(fuerItem)))}
  if(rest.length){box.appendChild(icGroup(t('Gut zu wissen','Good to know'),rest.length));box.appendChild(icList(rest.map(fuerItem)))}}
