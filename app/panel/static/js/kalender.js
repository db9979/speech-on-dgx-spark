// Kalender (Dominik 2026-10-18, plan kalender-mail/plan.md 1a 4a): the profile's calendars as a page of its own in the
// menu. „Termine“ shows a day, a week, a month or a list (GET /api/profile/calendar/view); „Einstellungen“ holds
// everything set up for calendars (the box #calbox, a page of Ich until V01.0.804). Ich, Heute, the apps and every
// way „Kalender → …“ lead here. Titles and places come from the calendars: only through esc().
const KAL={view:'',day:null,data:null,sel:null,seq:0,busy:false,form:null};
const KAL_VIEWS=[['day',t('Tag','Day'),1],['week',t('Woche','Week'),7],['month',t('Monat','Month'),42],['list',t('Liste','List'),14]];
const KAL_H=44;   // pixels per hour in the day and week view
// pages of their own outside Ich: the id of the old Ich page (still the place in every way, card and app) → section
// (features.OWN_PAGES, test_app_gleichstand keeps both equal)
const OWN_PAGES={calbox:['cal',t('Kalender','Calendar'),t('Termine','Appointments')],mailbox:['post',t('E-Mail','E-mail'),t('Posteingang','Inbox'),[['fuer',t('Für dich','For you'),()=>typeof FUER_ON!=='undefined'&&FUER_ON],['regeln',t('Regeln','Rules'),()=>typeof ORD_ON!=='undefined'&&ORD_ON]]]};
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
    (d&&d.notes&&d.notes.length?`<div class="note warn">${esc(t('Nicht gespeichert, der Kalender hat abgelehnt (es gilt die Fassung dort): ','Not saved, the calendar refused (its version stands): ')+d.notes.map(x=>x||t('ein Termin','an appointment')).join(', '))}</div>`:'')+
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'')+
    (d&&d.loading&&d.loading.length?`<div class="note">${esc(t('Lädt noch: ','Still loading: ')+d.loading.join(', '))}</div>`:'')+
    (d&&d.add&&d.add.length?`<div class="kalquick"><input data-q maxlength="200" autocomplete="off" placeholder="${esc(t('Schnell eintragen, z. B. „Zahnarzt morgen 10 Uhr bei Dr. Weber“','Quick add, e.g. "Dentist tomorrow 10am at Dr. Weber"'))}" aria-label="${esc(t('Schnell eintragen','Quick add'))}"><span class="kqchips"></span><button class="b p" type="button" data-k="quick" disabled>${esc(t('Eintragen','Add'))}</button><button class="b" type="button" data-k="more" hidden>${esc(t('Mehr …','More …'))}</button><div class="kalqmsg fh"></div></div>`:'')+
    `<div class="kalundo"></div>`+
    (d&&d.connected===false?`<div class="empty">${esc(t('Noch kein Kalender verbunden. Unter Einstellungen verbindest du iCloud, Nextcloud, einen anderen CalDAV-Server oder einen Abo-Link.','No calendar connected yet. Under Settings you connect iCloud, Nextcloud, another CalDAV server or a subscription link.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Kalender verbinden','Connect a calendar'))}</button></div></div>`
      :`<div class="kalmain${KAL.busy?' busy':''}"></div><div class="kalshade" hidden></div><div class="kaldet" role="dialog" hidden></div>`+
       (d&&d.calendars&&d.calendars.length>1?`<div class="kallegend">${d.calendars.map((n,i)=>`<span><i class="${kalKc(i)}"></i>${esc(n)}</span>`).join('')}</div>`:''));
  const m=w.querySelector('.kalmain');if(m)(KAL.view==='month'?kalMonth:KAL.view==='list'?kalList:kalGrid)(m);
  kalDetail(w);kalQuick(w);kalUndo(w);
  w.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{const k=b.dataset.k;
    if(k==='set'){icTabSet('cal','set');kalOpen();return}
    if(k==='new'){KAL.sel=null;KAL.form={mode:'new'};KAL.at='[data-k=new]';kalDraw();return}
    if(k==='quick'){kalQuickSave(w);return}
    if(k==='more'){const q=KAL.qi;if(!q)return;const ep=v=>new Date(q.allday?v+'T00:00':v).getTime()/1000;
      KAL.sel=null;KAL.form={mode:'new',x:{title:q.title,location:q.location,allday:q.allday,start:ep(q.start),end:ep(q.end)}};KAL.at='[data-k=quick]';kalDraw();return}
    if(k==='today')KAL.day=kalDay(new Date());
    else{const s=k==='prev'?-1:1;KAL.day=KAL.view==='month'?new Date(KAL.day.getFullYear(),KAL.day.getMonth()+s,1):kalAdd(KAL.day,s*(KAL.view==='week'?7:KAL.view==='list'?14:1))}
    KAL.sel=null;KAL.form=null;kalLoad()});
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
  m.appendChild(g);kalBind(m);kalDrag(g);
  g.querySelectorAll('button.kh').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.day+'T00:00');KAL.view='day';KAL.sel=null;kalLoad()});
  const nowCol=g.querySelector(`.kcol[data-day="${today}"]`);if(nowCol){const d=new Date(),y=(d.getHours()+d.getMinutes()/60-h0)*KAL_H;
    if(y>=0&&y<=(h1-h0)*KAL_H){const l=document.createElement('i');l.className='know';l.style.top=y+'px';nowCol.appendChild(l)}}}
function kalLanes(day,h0){const evs=kalOn(day).filter(x=>!x.allday).sort((x,y)=>x.start-y.start),lanes=[],out=[];
  const top=day.getTime()/1000+h0*3600;
  for(const x of evs){let i=lanes.findIndex(end=>end<=x.start);if(i<0){i=lanes.length;lanes.push(0)}lanes[i]=Math.max(x.end,x.start+900);out.push([x,i])}
  return out.map(([x,i])=>{const s=Math.max(x.start,day.getTime()/1000),e=Math.min(Math.max(x.end,x.start+900),kalAdd(day,1).getTime()/1000),
    y=(s-top)/3600*KAL_H,hgt=Math.max((e-s)/3600*KAL_H-2,18),w=100/lanes.length;
    return `<button type="button" class="kev ${kalKc(x.cal)}${KAL.sel===x?' on':''}${x.edit?' move':''}" data-i="${KAL.data.events.indexOf(x)}" style="top:${y}px;height:${hgt}px;left:${i*w}%;width:${w}%"><b>${esc(x.title)}</b><small>${esc(kalTime(x.start)+(x.location?' · '+x.location:''))}</small></button>`}).join('')}
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
function kalBind(m){m.querySelectorAll('[data-i]').forEach(b=>b.onclick=e=>{e.stopPropagation();if(KAL.dragged){KAL.dragged=false;return}
  const x=KAL.data.events[Number(b.dataset.i)];KAL.sel=KAL.sel===x?null:x;KAL.form=null;KAL.at='';kalDraw()})}
// the details of the appointment tapped (Dominik 2026-10-19 „1a“): a card floating beside it over the view on
// computers, a sheet from below on phones; the view keeps its whole width. Esc closes, E changes, Entf deletes.
function kalDetail(w){const box=w.querySelector('.kaldet'),x=KAL.sel;if(!box)return;
  if(KAL.form){kalForm(box);kalPlace(w,box);return}
  if(!x){box.hidden=true;w.querySelector('.kalshade').hidden=true;return}
  const d=KAL.data,when=x.allday?new Date(x.start*1000).toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'long'})+' · '+t('ganztägig','all day')
    :new Date(x.start*1000).toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'long'})+', '+kalTime(x.start)+'–'+kalTime(x.end);
  box.innerHTML=`<button type="button" class="kalx" data-close="1" aria-label="${esc(t('Schließen','Close'))}">✕</button><div class="mut"><i class="kdot ${kalKc(x.cal)}"></i>${esc((d.calendars||[])[x.cal]||'')}</div><h3>${esc(x.title)}</h3>`+
    `<dl class="ld-facts"><dt>${esc(t('Wann','When'))}</dt><dd>${esc(when)}</dd>${x.location?`<dt>${esc(t('Wo','Where'))}</dt><dd>${esc(x.location)}</dd>`:''}</dl>`+
    (x.edit?`<div class="row kalacts"><button class="b p" type="button" data-act="edit">${esc(t('Ändern','Change'))}</button><button class="b" type="button" data-act="day">${esc(t('+1 Tag','+1 day'))}</button><button class="b" type="button" data-act="week">${esc(t('+1 Woche','+1 week'))}</button><button class="b" type="button" data-act="del">${esc(t('Löschen','Delete'))}</button></div><div class="kalmsg fh"></div>`
      :`<div class="fh">${esc(x.title==='belegt'&&(d.shared||[]).includes(x.cal)?t('Privater Termin aus einem geteilten Kalender.','Private appointment from a shared calendar.')
        :t('Dieser Termin lässt sich hier nicht ändern (Abo-Link, geteilter oder wiederholter Termin).','This appointment cannot be changed here (subscription link, shared or repeating).'))}</div>`);
  box.querySelector('[data-close]').onclick=kalClose;
  const on=(k,f)=>{const b=box.querySelector(`[data-act=${k}]`);if(b)b.onclick=f};
  on('edit',()=>{KAL.form={mode:'edit',x};kalDraw()});
  on('day',()=>kalShift(x,1,0));on('week',()=>kalShift(x,7,0));
  on('del',()=>{if(!confirm(t('Termin „','Delete "')+x.title+t('“ löschen?','"?')))return;
    kalSend('PUT',{change:'delete',cal:x.cal,title:x.title,start:x.start},box.querySelector('.kalmsg'))});
  kalPlace(w,box)}
function kalClose(){KAL.sel=null;KAL.form=null;kalDraw()}
// beside what was tapped, inside the view (it scrolls along); on a phone the sheet from below with a shade
function kalPlace(w,box){box.hidden=false;const shade=w.querySelector('.kalshade'),x=KAL.sel||(KAL.form&&KAL.form.mode==='edit'&&KAL.form.x);
  shade.hidden=!NARROW();shade.onclick=kalClose;box.classList.toggle('sheet',NARROW());box.style.left=box.style.top='';
  if(NARROW())return;
  const a=(x&&w.querySelector(`.kalmain [data-i="${KAL.data.events.indexOf(x)}"]`))||(KAL.at&&w.querySelector(KAL.at));
  const wr=w.getBoundingClientRect(),bw=box.offsetWidth,bh=box.offsetHeight;
  if(!a){box.style.left=Math.max(0,wr.width-bw)+'px';box.style.top='60px';return}
  const r=a.getBoundingClientRect();let left=r.right-wr.left+10;
  if(left+bw>wr.width)left=r.left-wr.left-bw-10;
  if(left<0)left=Math.max(0,Math.min(wr.width-bw,r.left-wr.left));
  let top=r.top-wr.top;const vis=-wr.top+innerHeight-bh-12;   // keep it on the screen where possible
  if(top>vis)top=Math.max(vis,0);
  if(left===Math.max(0,Math.min(wr.width-bw,r.left-wr.left)))top=r.bottom-wr.top+8;
  box.style.left=left+'px';box.style.top=Math.max(0,top)+'px'}
document.addEventListener('keydown',e=>{if(!(KAL.sel||KAL.form)||!$('kalview')||!$('cal').classList.contains('on'))return;
  const typing=/^(INPUT|TEXTAREA|SELECT)$/.test((e.target&&e.target.tagName)||'');
  if(e.key==='Escape'){kalClose();return}
  if(typing||KAL.form||!KAL.sel||!KAL.sel.edit||e.metaKey||e.ctrlKey||e.altKey)return;
  const b=$('kalview').querySelector(e.key==='e'||e.key==='E'?'.kaldet [data-act=edit]':e.key==='Delete'?'.kaldet [data-act=del]':'_');
  if(b){e.preventDefault();b.click()}});
// moved: a day, a week, or dragged (days and minutes); „Rückgängig“ puts it back where it was
const kalHm2=d=>String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
function kalMove(x,days,mins){const s=new Date(x.start*1000),e=new Date(Math.max(x.end,x.start)*1000);
  s.setDate(s.getDate()+days);e.setDate(e.getDate()+days);s.setMinutes(s.getMinutes()+mins);e.setMinutes(e.getMinutes()+mins);
  return {at:Math.round(s.getTime()/1000),item:{title:x.title,allday:!!x.allday,location:x.location||'',
    start:x.allday?kalIso(s):kalIso(s)+'T'+kalHm2(s),end:x.allday?kalIso(e):kalIso(e)+'T'+kalHm2(e)}}}
async function kalShift(x,days,mins){const to=kalMove(x,days,mins),back=kalMove(x,0,0).item,msg=$('kalview').querySelector('.kalmsg')||$('kalview').querySelector('.kalundo');
  const ok=await kalSend('PUT',{change:'edit',cal:x.cal,title:x.title,start:x.start,new:to.item},msg);
  if(ok)KAL.undo={text:t('Verschoben: ','Moved: ')+x.title,at:Date.now(),body:{change:'edit',cal:x.cal,title:x.title,start:to.at,new:back}}}
function kalUndo(w){const u=KAL.undo,box=w.querySelector('.kalundo');if(!box)return;box.innerHTML='';
  if(!u||Date.now()-u.at>60000){KAL.undo=null;return}
  box.innerHTML=`<div class="note">${esc(u.text)} <button class="b" type="button" data-u="1">${esc(t('Rückgängig','Undo'))}</button></div>`;
  box.querySelector('[data-u]').onclick=()=>{KAL.undo=null;kalSend('PUT',u.body,box)}}
// week and day: an own appointment is dragged with the mouse to another time (quarter hours) or day; on a phone
// the card's +1 Tag and +1 Woche move it (a finger scrolls the view)
function kalDrag(g){g.querySelectorAll('.kev.move').forEach(b=>{const x=KAL.data.events[Number(b.dataset.i)];if(!x||x.allday)return;
  b.title=t('Ziehen zum Verschieben','Drag to move');
  b.onpointerdown=e=>{if(e.pointerType==='touch'||e.button)return;const y0=e.clientY,x0=e.clientX,col0=b.parentElement;let moved=false,dm=0,col=col0;
    const mv=ev=>{if(!moved&&Math.abs(ev.clientY-y0)<5&&Math.abs(ev.clientX-x0)<5)return;moved=true;b.classList.add('drag');ev.preventDefault();
      dm=Math.round((ev.clientY-y0)/KAL_H*4)*15;
      const over=document.elementsFromPoint(ev.clientX,ev.clientY).find(n=>n.classList&&n.classList.contains('kcol'));
      if(over&&over!==col){col=over;over.appendChild(b)}
      b.style.transform=`translateY(${dm/60*KAL_H}px)`;
      const days=Math.round((new Date(col.dataset.day+'T12:00')-new Date(col0.dataset.day+'T12:00'))/864e5);
      const sm=b.querySelector('small');if(sm)sm.textContent=kalTime(kalMove(x,days,dm).at)};
    const up=()=>{removeEventListener('pointermove',mv);removeEventListener('pointerup',up);if(!moved)return;KAL.dragged=true;
      setTimeout(()=>{KAL.dragged=false},0);
      const days=Math.round((new Date(col.dataset.day+'T12:00')-new Date(col0.dataset.day+'T12:00'))/864e5);
      if(!days&&!dm){kalDraw();return}
      KAL.sel=null;kalShift(x,days,dm)};
    addEventListener('pointermove',mv);addEventListener('pointerup',up)}})}
// Schnell eintragen (Dominik 2026-10-19 „2a“): the panel reads the line by fixed rules (GET …/calendar/quick) and
// shows what it understood as chips; saved only with „Eintragen“ (or Enter), into the first own calendar
let KAL_QT=0;
function kalQuick(w){const q=w.querySelector('[data-q]');if(!q)return;const had=KAL.qfocus;q.value=KAL.q||'';kalQChips(w);
  if(KAL.q&&!KAL.qi)kalQRead(w);   // brought along (E-Mail → „Als Termin“): read it at once
  if(had){q.focus();q.setSelectionRange(q.value.length,q.value.length)}
  q.onfocus=()=>{KAL.qfocus=true};q.onblur=()=>{KAL.qfocus=false};
  q.oninput=()=>{KAL.q=q.value;clearTimeout(KAL_QT);KAL_QT=setTimeout(()=>kalQRead(w),280)};
  q.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(KAL_QT);kalQRead(w).then(()=>{if(KAL.qi)kalQuickSave(w)})}}}
async function kalQRead(w){const text=(KAL.q||'').trim();if(!text){KAL.qi=null;kalQChips(w);return}
  const {r,d}=await apiTry('/api/profile/calendar/quick?'+new URLSearchParams({text,tz:TZ()}));
  if((KAL.q||'').trim()!==text)return;KAL.qi=r.ok?d:null;kalQChips(w)}
function kalQChips(w){const q=KAL.qi,box=w.querySelector('.kqchips');if(!box)return;
  w.querySelector('[data-k=quick]').disabled=!q;w.querySelector('[data-k=more]').hidden=!q;
  if(!q){box.innerHTML='';return}
  const s=new Date(q.allday?q.start+'T00:00':q.start),e=new Date(q.allday?q.end+'T00:00':q.end),o={weekday:'short',day:'numeric',month:'short'};
  const when=s.toLocaleDateString(kalLoc(),o)+(q.allday?' · '+t('ganztägig','all day'):' · '+kalHm2(s)+'–'+kalHm2(e));
  box.innerHTML=`<span class="kq t">${esc(q.title)}</span><span class="kq d">${esc(when)}</span>`+(q.location?`<span class="kq l">${esc(q.location)}</span>`:'')}
async function kalQuickSave(w){const q=KAL.qi;if(!q)return;
  const ok=await kalSend('POST',{title:q.title,start:q.start,end:q.end,allday:q.allday,location:q.location,calendar:''},w.querySelector('.kalqmsg'));
  if(ok){KAL.q='';KAL.qi=null;KAL.undo=null}}
// the form for a new appointment or a change: „Speichern“ is the yes (the server checks like the assistant's way)
const kalHm=s=>{const d=new Date(s*1000);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')};
function kalForm(box){const f=KAL.form,x=f.x,d=KAL.data,day=x?new Date(x.start*1000):KAL.day,end=x?new Date(Math.max(x.end-(x.allday?86400:0),x.start)*1000):day;
  const add=(d.add||[]).map(i=>[i,d.calendars[i]]);
  box.innerHTML=`<button type="button" class="kalx" data-close="1" aria-label="${esc(t('Schließen','Close'))}">✕</button><h3>${esc(f.mode==='new'?t('Neuer Termin','New appointment'):t('Termin ändern','Change appointment'))}</h3>`+
    `<label>${esc(t('Titel','Title'))}</label><input data-f="title" maxlength="200" value="${esc(x?x.title:'')}">`+
    `<label class="kalad"><input type="checkbox" data-f="allday"${x&&x.allday?' checked':''}> ${esc(t('ganztägig','all day'))}</label>`+
    `<div class="two2"><div><label>${esc(t('Von','From'))}</label><input type="date" data-f="sd" value="${kalIso(day)}"><input type="time" data-f="st" value="${x?kalHm(x.start):'10:00'}"></div>`+
    `<div><label>${esc(t('Bis','To'))}</label><input type="date" data-f="ed" value="${kalIso(end)}"><input type="time" data-f="et" value="${x?kalHm(x.end):'11:00'}"></div></div>`+
    `<label>${esc(t('Ort','Place'))}</label><input data-f="location" maxlength="200" value="${esc(x?x.location||'':'')}">`+
    (f.mode==='new'&&add.length>1?`<label>${esc(t('Kalender','Calendar'))}</label><select data-f="cal">${add.map(([i,n])=>`<option value="${i}">${esc(n)}</option>`).join('')}</select>`:'')+
    `<div class="row" style="margin-top:8px"><button class="b p" type="button" data-act="save">${esc(t('Speichern','Save'))}</button></div><div class="kalmsg fh"></div>`;
  const v=k=>box.querySelector(`[data-f=${k}]`),sync=()=>{const a=v('allday').checked;v('st').hidden=a;v('et').hidden=a};sync();v('allday').onchange=sync;
  box.querySelector('[data-close]').onclick=()=>{KAL.form=null;if(f.mode!=='edit')KAL.sel=null;kalDraw()};
  box.querySelector('[data-act=save]').onclick=()=>{const a=v('allday').checked,
    item={title:v('title').value.trim(),allday:a,location:v('location').value.trim(),
      start:a?v('sd').value:v('sd').value+'T'+v('st').value,end:a?kalIso(kalAdd(new Date(v('ed').value+'T00:00'),1)):v('ed').value+'T'+v('et').value};
    if(f.mode==='new'){const c=v('cal')?Number(v('cal').value):add.length?add[0][0]:-1;
      kalSend('POST',Object.assign(item,{calendar:c>=0&&(c!==add[0][0]||(d.shared||[]).includes(c))?d.calendars[c]:''}),box.querySelector('.kalmsg'))}
    else kalSend('PUT',{change:'edit',cal:x.cal,title:x.title,start:x.start,new:item},box.querySelector('.kalmsg'))}}
async function kalSend(method,body,msg){const cls=msg.className.split(' ')[0];msg.className=cls+' fh';msg.textContent=t('Speichere im Kalender …','Saving to the calendar …');
  const {r,d}=await apiTry('/api/profile/calendar/event',{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign(body,{tz:TZ()}))});
  if(!r.ok){msg.className=cls+' err';msg.textContent=r.status===409?t('Der Termin ist so nicht mehr da (woanders geändert, oder er wiederholt sich). Die Seite lädt neu.','The appointment is no longer there like this (changed elsewhere, or repeating). The page reloads.'):errSay(r.status,d.detail,'');if(r.status===409)kalLoad();return false}
  // Spark-Kalender Stufe 2: saved in the Spark's copy, the server gets it behind; a look a little later shows a refusal
  KAL.form=null;KAL.sel=null;kalLoad();setTimeout(()=>{if($('kalview'))kalLoad(true)},KAL_BEHIND_MS);return true}
const KAL_BEHIND_MS=5000
