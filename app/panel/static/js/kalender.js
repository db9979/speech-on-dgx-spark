// Kalender (Dominik 2026-10-18, plan kalender-mail/plan.md 1a 4a): the profile's calendars as a page of its own in the
// menu. „Termine“ shows a day, a week, a month or a list (GET /api/profile/calendar/view); „Einstellungen“ holds
// everything set up for calendars (the box #calbox, a page of Ich until V01.0.804). Ich, Heute, the apps and every
// way „Kalender → …“ lead here. Titles and places come from the calendars: only through esc().
const KAL={view:'',day:null,data:null,sel:null,seq:0,busy:false,form:null};
const KAL_VIEWS=[['day',t('Tag','Day'),1],['week',t('Woche','Week'),7],['month',t('Monat','Month'),42],['list',t('Liste','List'),14]];
const KAL_H=44;   // pixels per hour in the day and week view
// pages of their own outside Ich: the id of the old Ich page (still the place in every way, card and app) → section
// (features.OWN_PAGES, test_app_gleichstand keeps both equal)
const OWN_PAGES={calbox:['cal',t('Kalender','Calendar'),t('Termine','Appointments')],mailbox:['post',t('E-Mail','E-mail'),t('Posteingang','Inbox'),[['fuer',t('Für dich','For you'),()=>typeof FUER_ON!=='undefined'&&FUER_ON]]]};
// [section, name, first tab, [more tabs: key, name, shown?]]; every page ends with the tab „Einstellungen“
function ownPage(id){const p=OWN_PAGES[id];if(!p)return false;
  if($('profmodal').style.display==='grid'&&window.closeProf)closeProf();
  icTabSet(p[0],'set');goSec(p[0]);return true}
// the menu entry only for a signed-in profile that may use calendars (start.js, like Chats)
window.kalStart=who=>{const on=!!(who&&who.profile&&who.calendar!==false);document.querySelectorAll('nav button[data-s=cal]').forEach(b=>b.hidden=!on)};
const kalLoc=()=>L==='en'?'en-GB':'de-DE';
const kalIso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const kalDay=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate());
const kalAdd=(d,n)=>new Date(d.getFullYear(),d.getMonth(),d.getDate()+n);
const kalMon=d=>kalAdd(d,-((d.getDay()+6)%7));
const kalTime=s=>new Date(s*1000).toLocaleTimeString(kalLoc(),{hour:'2-digit',minute:'2-digit'});
// the first day the view shows and how many days
function kalRange(){const v=KAL_VIEWS.find(x=>x[0]===KAL.view),d=KAL.day;
  if(KAL.view==='week')return [kalMon(d),7];
  if(KAL.view==='month'){const first=new Date(d.getFullYear(),d.getMonth(),1);return [kalMon(first),42]}
  return [d,v[2]]}
function kalTitle(){const [a,n]=kalRange(),o={day:'numeric',month:'long',year:'numeric'};
  if(KAL.view==='day')return KAL.day.toLocaleDateString(kalLoc(),{weekday:'long',...o});
  if(KAL.view==='month')return KAL.day.toLocaleDateString(kalLoc(),{month:'long',year:'numeric'});
  const b=kalAdd(a,n-1);return a.toLocaleDateString(kalLoc(),{day:'numeric',month:'short'})+' – '+b.toLocaleDateString(kalLoc(),o)}
// the appointments of one day (an all-day one counts on every day it covers)
function kalOn(day){const a=day.getTime()/1000,b=kalAdd(day,1).getTime()/1000;
  return ((KAL.data&&KAL.data.events)||[]).filter(x=>x.allday?x.start<b&&Math.max(x.end,x.start+1)>a:x.start<b&&Math.max(x.end,x.start+60)>a)}
// again: a calendar still loading in the background (calendars.view) is asked for once more after 3 s, at most 5 times
async function kalLoad(again){if(!PROFILE||!CAL_ON)return;const [a,n]=kalRange(),seq=++KAL.seq;KAL.busy=!again;KAL.tries=again?(KAL.tries||0)+1:0;kalDraw();
  try{const d=await (await api('/api/profile/calendar/view?'+new URLSearchParams({start:kalIso(a),days:n,tz:TZ()}))).json();
    if(seq!==KAL.seq)return;KAL.data=d;KAL.err='';
    if(d.loading&&d.loading.length&&KAL.tries<5)setTimeout(()=>{if(seq===KAL.seq&&$('kalview'))kalLoad(true)},3000)}
  catch(e){if(seq!==KAL.seq)return;KAL.err=e.message||t('Nicht erreicht','Not reached')}
  KAL.busy=false;kalDraw()}
const KAL_BOX=$('calbox');   // the tab „Einstellungen“ shows it; kept in the section between visits
function kalOpen(){if(!PROFILE)return;if(!KAL.day)KAL.day=kalDay(new Date());if(!KAL.view)KAL.view=NARROW()?'list':'week';
  const root=$('kalroot');if(KAL_BOX){KAL_BOX.hidden=true;$('cal').appendChild(KAL_BOX)}root.textContent='';   // see POST_BOXES (post.js)
  root.appendChild(icTabs('cal',[{k:'show',label:OWN_PAGES.calbox[2],body:kalBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('calbox');b.hidden=false;lzb(b,showCal,{auth:true}).catch(()=>{});proIn('procal').catch(()=>{});return b}}]));
  kalLoad()}
// the tab „Termine“: tools, the view, the details of the appointment tapped
function kalBody(){const w=document.createElement('div');w.className='kal';w.id='kalview';kalPaint(w);return w}
function kalDraw(){const w=$('kalview');if(w)kalPaint(w)}
function kalPaint(w){const d=KAL.data;
  w.innerHTML=`<div class="kaltools"><span class="kalnav"><button class="b" type="button" data-k="prev" aria-label="${esc(t('Zurück','Back'))}">‹</button><button class="b" type="button" data-k="today">${esc(t('Heute','Today'))}</button><button class="b" type="button" data-k="next" aria-label="${esc(t('Weiter','Next'))}">›</button></span>`+
    `<b class="kaltitle">${esc(kalTitle())}</b>${d&&d.add&&d.add.length?`<button class="b p" type="button" data-k="new">${esc(t('+ Termin','+ Appointment'))}</button>`:''}<span class="segc" role="radiogroup">${KAL_VIEWS.map(([k,l])=>`<button type="button" data-v="${k}" class="${k===KAL.view?'on':''}" aria-pressed="${k===KAL.view}">${esc(l)}</button>`).join('')}</span></div>`+
    (KAL.err?`<div class="note warn">${esc(t('Die Termine kamen nicht an: ','The appointments did not arrive: ')+KAL.err)}</div>`:'')+
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'')+
    (d&&d.loading&&d.loading.length?`<div class="note">${esc(t('Lädt noch: ','Still loading: ')+d.loading.join(', '))}</div>`:'')+
    (d&&d.connected===false?`<div class="empty">${esc(t('Noch kein Kalender verbunden. Unter Einstellungen verbindest du iCloud, Nextcloud, einen anderen CalDAV-Server oder einen Abo-Link.','No calendar connected yet. Under Settings you connect iCloud, Nextcloud, another CalDAV server or a subscription link.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Kalender verbinden','Connect a calendar'))}</button></div></div>`
      :`<div class="kalsplit"><div class="kalmain${KAL.busy?' busy':''}"></div><div class="ld-detail kaldet" hidden></div></div>`+
       (d&&d.calendars&&d.calendars.length>1?`<div class="kallegend">${d.calendars.map((n,i)=>`<span><i class="${kalKc(i)}"></i>${esc(n)}</span>`).join('')}</div>`:''));
  const m=w.querySelector('.kalmain');if(m)(KAL.view==='month'?kalMonth:KAL.view==='list'?kalList:kalGrid)(m);
  kalDetail(w);
  w.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{const k=b.dataset.k;
    if(k==='set'){icTabSet('cal','set');kalOpen();return}
    if(k==='new'){KAL.sel=null;KAL.form={mode:'new'};kalDraw();return}
    if(k==='today')KAL.day=kalDay(new Date());
    else{const s=k==='prev'?-1:1;KAL.day=KAL.view==='month'?new Date(KAL.day.getFullYear(),KAL.day.getMonth()+s,1):kalAdd(KAL.day,s*(KAL.view==='week'?7:KAL.view==='list'?14:1))}
    KAL.sel=null;kalLoad()});
  w.querySelectorAll('.segc [data-v]').forEach(b=>b.onclick=()=>{KAL.view=b.dataset.v;KAL.sel=null;kalLoad()})}
// day and week: hours as rows, all-day appointments on top, overlapping ones side by side
function kalGrid(m){const [a,n]=kalRange(),days=[...Array(n)].map((_,i)=>kalAdd(a,i)),today=kalIso(new Date());
  let h0=7,h1=20;for(const day of days)for(const x of kalOn(day))if(!x.allday){const s=new Date(Math.max(x.start*1000,day.getTime())),e=new Date(Math.min(x.end*1000,kalAdd(day,1).getTime()));
    h0=Math.min(h0,s.getHours());h1=Math.max(h1,e.getHours()+(e.getMinutes()?1:0)||24)}
  h1=Math.min(Math.max(h1,h0+1),24);
  const g=document.createElement('div');g.className='kalgrid';g.style.setProperty('--n',n);
  g.innerHTML=`<div class="kh"></div>`+days.map(day=>`<button type="button" class="kh${kalIso(day)===today?' now':''}" data-day="${kalIso(day)}">${esc(day.toLocaleDateString(kalLoc(),{weekday:'short'}))}<b>${day.getDate()}</b></button>`).join('')+
    `<div class="kad mut">${esc(t('ganztägig','all day'))}</div>`+days.map(day=>`<div class="kad">${kalOn(day).filter(x=>x.allday).map(x=>kalChip(x)).join('')}</div>`).join('')+
    `<div class="khours">${[...Array(h1-h0)].map((_,i)=>`<span>${String(h0+i).padStart(2,'0')}:00</span>`).join('')}</div>`+
    days.map(day=>`<div class="kcol" data-day="${kalIso(day)}" style="height:${(h1-h0)*KAL_H}px">${kalLanes(day,h0)}</div>`).join('');
  m.appendChild(g);kalBind(m);
  g.querySelectorAll('button.kh').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.day+'T00:00');KAL.view='day';KAL.sel=null;kalLoad()});
  const nowCol=g.querySelector(`.kcol[data-day="${today}"]`);if(nowCol){const d=new Date(),y=(d.getHours()+d.getMinutes()/60-h0)*KAL_H;
    if(y>=0&&y<=(h1-h0)*KAL_H){const l=document.createElement('i');l.className='know';l.style.top=y+'px';nowCol.appendChild(l)}}}
function kalLanes(day,h0){const evs=kalOn(day).filter(x=>!x.allday).sort((x,y)=>x.start-y.start),lanes=[],out=[];
  const top=day.getTime()/1000+h0*3600;
  for(const x of evs){let i=lanes.findIndex(end=>end<=x.start);if(i<0){i=lanes.length;lanes.push(0)}lanes[i]=Math.max(x.end,x.start+900);out.push([x,i])}
  return out.map(([x,i])=>{const s=Math.max(x.start,day.getTime()/1000),e=Math.min(Math.max(x.end,x.start+900),kalAdd(day,1).getTime()/1000),
    y=(s-top)/3600*KAL_H,hgt=Math.max((e-s)/3600*KAL_H-2,18),w=100/lanes.length;
    return `<button type="button" class="kev ${kalKc(x.cal)}${KAL.sel===x?' on':''}" data-i="${KAL.data.events.indexOf(x)}" style="top:${y}px;height:${hgt}px;left:${i*w}%;width:${w}%"><b>${esc(x.title)}</b><small>${esc(kalTime(x.start)+(x.location?' · '+x.location:''))}</small></button>`}).join('')}
// a short line: in the month only the title (a narrow day shows no room for the time)
// one colour per calendar, written out so the style check finds every class
const KAL_KC=['kc0','kc1','kc2','kc3','kc4','kc5','kc6','kc7'],kalKc=i=>KAL_KC[i%8];
const kalChip=(x,month)=>`<button type="button" class="kchip ${kalKc(x.cal)}${KAL.sel===x?' on':''}" data-i="${KAL.data.events.indexOf(x)}">${esc(x.allday||month===true?x.title:kalTime(x.start)+' '+x.title)}</button>`;
// month: six weeks, at most three appointments a day and how many more
function kalMonth(m){const [a]=kalRange(),mon=KAL.day.getMonth(),today=kalIso(new Date());
  const g=document.createElement('div');g.className='kalmonth';
  g.innerHTML=[0,1,2,3,4,5,6].map(i=>`<div class="kmh">${esc(kalAdd(a,i).toLocaleDateString(kalLoc(),{weekday:'short'}))}</div>`).join('')+
    [...Array(42)].map((_,i)=>{const day=kalAdd(a,i),evs=kalOn(day);
      return `<div class="kmd${day.getMonth()!==mon?' other':''}${kalIso(day)===today?' now':''}"><button type="button" class="kmn" data-day="${kalIso(day)}">${day.getDate()}</button>${evs.slice(0,3).map(x=>kalChip(x,true)).join('')}${evs.length>3?`<button type="button" class="kmore" data-day="${kalIso(day)}">${esc(t(`+${evs.length-3} weitere`,`+${evs.length-3} more`))}</button>`:''}</div>`}).join('');
  m.appendChild(g);kalBind(m);
  g.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.day+'T00:00');KAL.view='day';KAL.sel=null;kalLoad()})}
// list: the days with appointments, two weeks at a time
function kalList(m){const [a,n]=kalRange();let html='';
  for(let i=0;i<n;i++){const day=kalAdd(a,i),evs=kalOn(day);if(!evs.length)continue;
    html+=`<div class="ld-grp"><span>${esc(day.toLocaleDateString(kalLoc(),{weekday:'long',day:'numeric',month:'long'}))}</span><span>${evs.length}</span></div>`+
      evs.map(x=>`<button type="button" class="kli${KAL.sel===x?' on':''}" data-i="${KAL.data.events.indexOf(x)}"><span class="kt">${esc(x.allday?t('ganztägig','all day'):kalTime(x.start))}${x.allday?'':`<small>${esc(kalTime(x.end))}</small>`}</span><i class="kbar ${kalKc(x.cal)}"></i><span class="kx"><b>${esc(x.title)}</b>${x.location?`<small>${esc(x.location)}</small>`:''}</span></button>`).join('')}
  m.innerHTML=html||(KAL.busy?'':`<div class="empty">${esc(t('In diesen zwei Wochen steht nichts an.','Nothing planned in these two weeks.'))}</div>`);kalBind(m)}
function kalBind(m){m.querySelectorAll('[data-i]').forEach(b=>b.onclick=e=>{e.stopPropagation();const x=KAL.data.events[Number(b.dataset.i)];KAL.sel=KAL.sel===x?null:x;kalDraw()})}
// the details of the appointment tapped: beside the view on computers, below it on phones
function kalDetail(w){const box=w.querySelector('.kaldet'),x=KAL.sel;if(!box)return;
  if(KAL.form){box.hidden=false;kalForm(box);return}
  box.hidden=!x;if(!x)return;
  const d=KAL.data,when=x.allday?new Date(x.start*1000).toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'long'})+' · '+t('ganztägig','all day')
    :new Date(x.start*1000).toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'long'})+', '+kalTime(x.start)+'–'+kalTime(x.end);
  box.innerHTML=`<button type="button" class="b ld-back" data-close="1">‹ ${esc(t('Zurück','Back'))}</button><div class="mut">${esc((d.calendars||[])[x.cal]||'')}</div><h3>${esc(x.title)}</h3>`+
    `<dl class="ld-facts"><dt>${esc(t('Wann','When'))}</dt><dd>${esc(when)}</dd>${x.location?`<dt>${esc(t('Wo','Where'))}</dt><dd>${esc(x.location)}</dd>`:''}</dl>`+
    (x.edit?`<div class="row"><button class="b" type="button" data-act="edit">${esc(t('Ändern','Change'))}</button><button class="b" type="button" data-act="del">${esc(t('Löschen','Delete'))}</button></div><div class="kalmsg fh"></div>`
      :`<div class="fh">${esc(x.title==='belegt'&&(d.shared||[]).includes(x.cal)?t('Privater Termin aus einem geteilten Kalender.','Private appointment from a shared calendar.')
        :t('Dieser Termin lässt sich hier nicht ändern (Abo-Link, geteilter oder wiederholter Termin).','This appointment cannot be changed here (subscription link, shared or repeating).'))}</div>`);
  box.querySelector('[data-close]').onclick=()=>{KAL.sel=null;kalDraw()};
  const ed=box.querySelector('[data-act=edit]');if(ed)ed.onclick=()=>{KAL.form={mode:'edit',x};kalDraw()};
  const del=box.querySelector('[data-act=del]');if(del)del.onclick=async()=>{if(!confirm(t('Termin „','Delete "')+x.title+t('“ löschen?','"?')))return;
    kalSend('PUT',{change:'delete',cal:x.cal,title:x.title,start:x.start},box.querySelector('.kalmsg'))}}
// the form for a new appointment or a change: „Speichern“ is the yes (the server checks like the assistant's way)
const kalHm=s=>{const d=new Date(s*1000);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')};
function kalForm(box){const f=KAL.form,x=f.x,d=KAL.data,day=x?new Date(x.start*1000):KAL.day,end=x?new Date(Math.max(x.end-(x.allday?86400:0),x.start)*1000):day;
  const add=(d.add||[]).map(i=>[i,d.calendars[i]]);
  box.innerHTML=`<button type="button" class="b ld-back" data-close="1">‹ ${esc(t('Zurück','Back'))}</button><h3>${esc(f.mode==='new'?t('Neuer Termin','New appointment'):t('Termin ändern','Change appointment'))}</h3>`+
    `<label>${esc(t('Titel','Title'))}</label><input data-f="title" maxlength="200" value="${esc(x?x.title:'')}">`+
    `<label class="kalad"><input type="checkbox" data-f="allday"${x&&x.allday?' checked':''}> ${esc(t('ganztägig','all day'))}</label>`+
    `<div class="two2"><div><label>${esc(t('Von','From'))}</label><input type="date" data-f="sd" value="${kalIso(day)}"><input type="time" data-f="st" value="${x?kalHm(x.start):'10:00'}"></div>`+
    `<div><label>${esc(t('Bis','To'))}</label><input type="date" data-f="ed" value="${kalIso(end)}"><input type="time" data-f="et" value="${x?kalHm(x.end):'11:00'}"></div></div>`+
    `<label>${esc(t('Ort','Place'))}</label><input data-f="location" maxlength="200" value="${esc(x?x.location||'':'')}">`+
    (f.mode==='new'&&add.length>1?`<label>${esc(t('Kalender','Calendar'))}</label><select data-f="cal">${add.map(([i,n])=>`<option value="${i}">${esc(n)}</option>`).join('')}</select>`:'')+
    `<div class="row" style="margin-top:8px"><button class="b p" type="button" data-act="save">${esc(t('Speichern','Save'))}</button></div><div class="kalmsg fh"></div>`;
  const v=k=>box.querySelector(`[data-f=${k}]`),sync=()=>{const a=v('allday').checked;v('st').hidden=a;v('et').hidden=a};sync();v('allday').onchange=sync;
  box.querySelector('[data-close]').onclick=()=>{KAL.form=null;kalDraw()};
  box.querySelector('[data-act=save]').onclick=()=>{const a=v('allday').checked,
    item={title:v('title').value.trim(),allday:a,location:v('location').value.trim(),
      start:a?v('sd').value:v('sd').value+'T'+v('st').value,end:a?kalIso(kalAdd(new Date(v('ed').value+'T00:00'),1)):v('ed').value+'T'+v('et').value};
    if(f.mode==='new'){const c=v('cal')?Number(v('cal').value):add.length?add[0][0]:-1;
      kalSend('POST',Object.assign(item,{calendar:c>=0&&(c!==add[0][0]||(d.shared||[]).includes(c))?d.calendars[c]:''}),box.querySelector('.kalmsg'))}
    else kalSend('PUT',{change:'edit',cal:x.cal,title:x.title,start:x.start,new:item},box.querySelector('.kalmsg'))}}
async function kalSend(method,body,msg){msg.className='kalmsg fh';msg.textContent=t('Speichere im Kalender …','Saving to the calendar …');
  const {r,d}=await apiTry('/api/profile/calendar/event',{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign(body,{tz:TZ()}))});
  if(!r.ok){msg.className='kalmsg err';msg.textContent=r.status===409?t('Der Termin ist so nicht mehr da (woanders geändert, oder er wiederholt sich). Die Seite lädt neu.','The appointment is no longer there like this (changed elsewhere, or repeating). The page reloads.'):errSay(r.status,d.detail,'');if(r.status===409)kalLoad();return}
  KAL.form=null;KAL.sel=null;kalLoad()}
