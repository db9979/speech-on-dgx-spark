// Ich starts with "Heute" (plan „Bedienung gesamt“ B1/B3, V01.0.286): cards for what is due today (next
// appointments, reminders, unread messages, documents, memory) from /api/profile/today and "Probier mal" with
// sentences of the functions this profile may use (the say lines of guides.js, the functions from /api/features).
// What is still to set up is "Los geht's" (join.js, onboard.py). On computers on top of Überblick, on phones above
// the list of pages. Only numbers and short titles; a tap opens the page or asks the sentence.
let TODAY=null;
const TD_GO=(id)=>()=>{if(ME_ITEMS.some(x=>x[0]===id)){meLast=id;ptab(id)}};
const tdTime=s=>{const d=new Date(s*1000),n=new Date(),tm=new Date(n.getFullYear(),n.getMonth(),n.getDate()+1);
  const day=d.toDateString()===n.toDateString()?t('Heute','Today'):d.toDateString()===tm.toDateString()?t('Morgen','Tomorrow'):d.toLocaleDateString([],{weekday:'short',day:'numeric',month:'numeric'});
  return day+' '+d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})};
function tdEl(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function tdCard(title,big,small,go){const b=tdEl('button','tcard');b.type='button';b.append(tdEl('span','tct',title),tdEl('b','',big));if(small)b.appendChild(tdEl('small','',small));
  if(go)b.onclick=TD_GO(go);return b}
// the sentences to try: one per function the profile may use, from its guide (only the ones in „…“)
function tdTry(){if(typeof GUIDES==='undefined'||!FEATS)return[];const can=new Set(FEATS.features.filter(f=>f.can&&f.guide).map(f=>f.guide)),out=[];
  for(const g of GUIDES){if(!can.has(g.id)||!g.say)continue;const s=g.say.map(x=>x[L==='en'?1:0]).find(x=>/^[„"]/.test(x));
    if(s)out.push(s.replace(/^[„"]|[“"]$/g,'').replace(/^(Hey Spark|Jarvis|Computer),\s*/i,'').replace(/^./,c=>c.toUpperCase()));if(out.length>=6)break}
  return out}
function tdAsk(x){if(window.closeProf)closeProf();document.querySelector('nav button[data-s=chat]').click();$('chattext').value=x;$('chatsend').click()}
async function meToday(){if(!PROFILE)return;const ph=PHONE.matches,host=ph?$('ptabs').parentNode:$('overbox');if(!host)return;
  let box=$('metoday');if(!box||box.parentNode!==host){if(box)box.remove();box=tdEl('div','metoday');box.id='metoday';if(ph)$('ptabs').before(box);else host.prepend(box)}
  try{let tz='';try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||''}catch{}
    TODAY=await (await api('/api/profile/today?'+new URLSearchParams({tz}))).json()}catch{box.remove();return}
  if(!FEATS&&typeof loadFeats==='function')await loadFeats();
  box.textContent='';const c=TODAY.cards,cards=tdEl('div','tcards');
  if(c.calendar){const n=c.calendar.next||[];
    cards.appendChild(c.calendar.connected===false?tdCard(t('Termine','Appointments'),t('Kalender verbinden','Connect a calendar'),'',  'calbox')
      :tdCard(t('Termine','Appointments'),n.length?(n[0].allday?t('Heute ganztägig','Today all day'):tdTime(n[0].start)):t('Heute und morgen frei','Free today and tomorrow'),
        n.length?n.map(x=>x.title).join(' · '):c.calendar.error?t('Ein Kalender war nicht erreichbar.','A calendar could not be reached.'):'','calbox'))}
  if(c.reminders)cards.appendChild(tdCard(t('Erinnerungen','Reminders'),String(c.reminders.count),c.reminders.next?tdTime(c.reminders.next.due)+' · '+c.reminders.next.text:t('Keine offen','None open'),'notebox'));
  if(c.messages)cards.appendChild(tdCard(t('Nachrichten','Messages'),String(c.messages.unread),c.messages.unread?t('ungelesen','unread'):t('Alles gelesen','All read'),'msgbox'));
  if(c.documents)cards.appendChild(tdCard(t('Dokumente','Documents'),String(c.documents.count),c.documents.waiting?c.documents.waiting+t(' Seiten warten aufs Lesen',' pages waiting to be read'):'','docbox'));
  if(c.memory)cards.appendChild(tdCard(t('Gedächtnis','Memory'),String(c.memory.facts),t('gemerkte Fakten','remembered facts'),'factbox'));
  // Mein Zustand (hintergrund.js, own switch my_status): the short line here, the whole card under Ich → Mein Zustand
  if(typeof MYST_ON!=='undefined'&&MYST_ON&&typeof S!=='undefined'&&S&&S.my_status){try{const r=await fetch('/api/profile/hintergrund?brief=1',{cache:'no-store'});
    if(r.ok){const s=(await r.json()).sum||{};cards.appendChild(tdCard(t('Im Hintergrund','In the background'),
      s.need?t(`${s.need} brauchen dich`,`${s.need} need you`):s.run?t('läuft','running'):t('in Ordnung','fine'),bgLine(s)||t('Für dich läuft nichts.','Nothing runs for you.'),'bgbox'))}}catch{}}
  if(cards.children.length){box.append(tdEl('div','mgrp',t('Heute','Today')),cards)}
  const tr=tdTry();if(tr.length){const tb=tdEl('div','ttry');tb.appendChild(tdEl('div','mgrp',t('Probier mal','Try saying')));
    const chips=tdEl('div','tchips');for(const x of tr){const b=tdEl('button','chip',x);b.type='button';b.onclick=()=>tdAsk(x);chips.appendChild(b)}tb.appendChild(chips);box.appendChild(tb)}
  if(!box.children.length)box.remove()}
window.meToday=meToday;
