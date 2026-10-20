// Kalender (Dominik 2026-10-18, plan kalender-mail/plan.md 1a 4a): the profile's calendars as a page of its own in the
// menu. „Termine“ shows a day, a week, a month, the year or a list (GET /api/profile/calendar/view); „Einstellungen“
// holds everything set up for calendars (the box #calbox, a page of Ich until V01.0.804). Ich, Heute, the apps and
// every way „Kalender → …“ lead here. Titles and places come from the calendars: only through esc().
// Wie Apple Kalender (Apple-Stil „4a“ „5a“, Dominik 2026-10-20): a column on the left (small month, calendars on and
// off), drag or double-click into free time makes an appointment, its lower edge sets the length, the inspector
// holds every field and saves when it closes, „Rückgängig“ asks the Spark to put it back; a repeating appointment
// asks „Nur dieser Termin“ or „Alle künftigen“. A phone shows the day under its week strip and turns it by swiping.
const KAL={view:'',day:null,data:null,sel:null,seq:0,busy:false,form:null,side:null,mini:null};
const KAL_VIEWS=[['day',t('Tag','Day'),1],['week',t('Woche','Week'),7],['month',t('Monat','Month'),42],['year',t('Jahr','Year'),1],['list',t('Liste','List'),14]];
const KAL_H=44;   // pixels per hour in the day and week view
// pages of their own outside Ich: the id of the old Ich page (still the place in every way, card and app) → section
// (features.OWN_PAGES, test_app_gleichstand keeps both equal)
const OWN_PAGES={calbox:['cal',t('Kalender','Calendar'),t('Termine','Appointments')],mailbox:['post',t('E-Mail','E-mail'),t('Posteingang','Inbox'),[['fuer',t('Für dich','For you'),()=>typeof FUER_ON!=='undefined'&&FUER_ON],['regeln',t('Regeln','Rules'),()=>typeof ORD_ON!=='undefined'&&ORD_ON]]],
  taskbox:['listen',t('Listen','Lists'),t('Listen','Lists')],vgbox:['offen',t('Offen','Open'),t('Offen','Open')]};
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
const kalHm2=d=>String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
const kalHm=s=>kalHm2(new Date(s*1000));
// the column on the left: always beside the view on a wide screen (unless closed), a sheet on a phone
const kalWide=()=>matchMedia('(min-width:1000px)').matches;
const kalSideOn=()=>kalWide()?KAL.side!==false:KAL.side===true;
// calendars switched off in the column: per browser, a view choice like Apple's ticks (nothing on the Spark changes)
const KAL_HIDE=new Set((()=>{try{return JSON.parse(localStorage.getItem('kal.hide')||'[]')}catch{return []}})());
function kalHideSet(n,off){if(off)KAL_HIDE.add(n);else KAL_HIDE.delete(n);try{localStorage.setItem('kal.hide',JSON.stringify([...KAL_HIDE]))}catch{}}
const kalShown=x=>!KAL_HIDE.has(((KAL.data&&KAL.data.calendars)||[])[x.cal]);
// the first day the view loads and how many days (a phone's day loads its week: the strip shows the dots)
function kalRange(){const v=KAL_VIEWS.find(x=>x[0]===KAL.view),d=KAL.day;
  if(KAL.view==='week'||(KAL.view==='day'&&NARROW()))return [kalMon(d),7];
  if(KAL.view==='month'){const first=new Date(d.getFullYear(),d.getMonth(),1);return [kalMon(first),42]}
  if(KAL.view==='year')return [new Date(d.getFullYear(),0,1),1];
  return [d,v[2]]}
function kalTitle(){const [a,n]=kalRange(),o={day:'numeric',month:'long',year:'numeric'};
  if(KAL.view==='day')return KAL.day.toLocaleDateString(kalLoc(),{weekday:'long',...o});
  if(KAL.view==='month')return KAL.day.toLocaleDateString(kalLoc(),{month:'long',year:'numeric'});
  if(KAL.view==='year')return String(KAL.day.getFullYear());
  const b=kalAdd(a,n-1);return a.toLocaleDateString(kalLoc(),{day:'numeric',month:'short'})+' – '+b.toLocaleDateString(kalLoc(),o)}
// the appointments of one day (an all-day one counts on every day it covers), without the calendars switched off
function kalOn(day){const a=day.getTime()/1000,b=kalAdd(day,1).getTime()/1000;
  return ((KAL.data&&KAL.data.events)||[]).filter(x=>kalShown(x)&&(x.allday?x.start<b&&Math.max(x.end,x.start+1)>a:x.start<b&&Math.max(x.end,x.start+60)>a))}
// again: a calendar still loading in the background (calendars.view) is asked for once more after 3 s, at most 5 times;
// while the inspector is open such a look only keeps the data (what is being typed stays)
async function kalLoad(again){if(!PROFILE||!CAL_ON)return;const [a,n]=kalRange(),seq=++KAL.seq;KAL.busy=!again;KAL.tries=again?(KAL.tries||0)+1:0;if(!again)kalDraw();
  try{const d=await (await api('/api/profile/calendar/view?'+new URLSearchParams({start:kalIso(a),days:n,tz:TZ()}))).json();
    if(seq!==KAL.seq)return;KAL.data=d;KAL.err='';if(KAL.sel)KAL.sel=d.events.find(x=>kalSame(x,KAL.sel))||null;
    if(d.loading&&d.loading.length&&KAL.tries<5)setTimeout(()=>{if(seq===KAL.seq&&$('kalview'))kalLoad(true)},3000)}
  catch(e){if(seq!==KAL.seq)return;KAL.err=e.message||t('Nicht erreicht','Not reached')}
  KAL.busy=false;if(!(again&&KAL.form))kalDraw()}
const kalSame=(x,y)=>x.cal===y.cal&&x.start===y.start&&x.title===y.title;
const KAL_BOX=$('calbox');   // the tab „Einstellungen“ shows it; kept in the section between visits
function kalOpen(){if(!PROFILE)return;if(!KAL.day)KAL.day=kalDay(new Date());if(!KAL.view)KAL.view=NARROW()?'day':'week';
  const root=$('kalroot');if(KAL_BOX){KAL_BOX.hidden=true;$('cal').appendChild(KAL_BOX)}root.textContent='';   // see POST_BOXES (post.js)
  root.appendChild(icTabs('cal',[{k:'show',label:OWN_PAGES.calbox[2],body:kalBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('calbox');b.hidden=false;lzb(b,showCal,{auth:true}).catch(()=>{});proIn('procal').catch(()=>{});return b}}]));
  kalLoad()}
// the tab „Termine“: tools, the column, the view, the inspector of the appointment tapped
function kalBody(){const w=document.createElement('div');w.className='kal';w.id='kalview';kalPaint(w);return w}
function kalDraw(){const w=$('kalview');if(w)kalPaint(w)}
const kalCanAdd=()=>!!(KAL.data&&KAL.data.add&&KAL.data.add.length);
function kalPaint(w){const d=KAL.data,side=d&&d.connected!==false&&d.calendars&&kalSideOn();w.style.minHeight='';
  w.innerHTML=`<div class="kaltools"><button class="b kalsideb" type="button" data-k="side" aria-pressed="${!!side}" aria-label="${esc(t('Kalender ein- und ausblenden','Show and hide calendars'))}">☰</button><span class="kalnav"><button class="b" type="button" data-k="prev" aria-label="${esc(t('Zurück','Back'))}">‹</button><button class="b" type="button" data-k="today">${esc(t('Heute','Today'))}</button><button class="b" type="button" data-k="next" aria-label="${esc(t('Weiter','Next'))}">›</button></span>`+
    `<b class="kaltitle">${esc(kalTitle())}</b>${kalCanAdd()?`<button class="b p" type="button" data-k="new" aria-label="${esc(t('Neuer Termin','New appointment'))}">${esc(t('+ Termin','+ Appointment'))}</button>`:''}<span class="segc" role="radiogroup">${KAL_VIEWS.map(([k,l])=>`<button type="button" data-v="${k}" class="${k===KAL.view?'on':''}" aria-pressed="${k===KAL.view}">${esc(l)}</button>`).join('')}</span></div>`+
    (KAL.err?`<div class="note warn">${esc(t('Die Termine kamen nicht an: ','The appointments did not arrive: ')+KAL.err)}</div>`:'')+
    (d&&d.notes&&d.notes.length?`<div class="note warn">${esc(t('Nicht gespeichert, der Kalender hat abgelehnt (es gilt die Fassung dort): ','Not saved, the calendar refused (its version stands): ')+d.notes.map(x=>x||t('ein Termin','an appointment')).join(', '))}</div>`:'')+
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'')+
    (d&&d.loading&&d.loading.length?`<div class="note">${esc(t('Lädt noch: ','Still loading: ')+d.loading.join(', '))}</div>`:'')+
    (kalCanAdd()?`<div class="kalquick"><input data-q maxlength="200" autocomplete="off" placeholder="${esc(t('Schnell eintragen, z. B. „Zahnarzt morgen 10 Uhr bei Dr. Weber“','Quick add, e.g. "Dentist tomorrow 10am at Dr. Weber"'))}" aria-label="${esc(t('Schnell eintragen','Quick add'))}"><span class="kqchips"></span><button class="b p" type="button" data-k="quick" disabled>${esc(t('Eintragen','Add'))}</button><button class="b" type="button" data-k="more" hidden>${esc(t('Mehr …','More …'))}</button><div class="kalqmsg fh"></div></div>`:'')+
    `<div class="kalundo"></div>`+
    (d&&d.connected===false?`<div class="empty">${esc(t('Noch kein Kalender verbunden. Unter Einstellungen verbindest du iCloud, Nextcloud, einen anderen CalDAV-Server oder einen Abo-Link.','No calendar connected yet. Under Settings you connect iCloud, Nextcloud, another CalDAV server or a subscription link.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Kalender verbinden','Connect a calendar'))}</button></div></div>`
      :`<div class="kalbody${side?' side':''}">${side?`<aside class="kalside${kalWide()?'':' sheet'}" aria-label="${esc(t('Kalender','Calendars'))}"></aside>`:''}<div class="kalmain${KAL.busy?' busy':''}"></div></div><div class="kalshade" hidden></div><div class="kaldet" role="dialog" hidden></div><div class="kalask" role="dialog" aria-modal="true" hidden></div>`);
  const m=w.querySelector('.kalmain');if(m){({month:kalMonth,list:kalList,year:kalYear}[KAL.view]||kalGrid)(m);kalSwipe(m)}
  const a=w.querySelector('.kalside');if(a)kalSide(w,a);
  kalDetail(w);kalQuick(w);kalUndo(w);
  w.querySelectorAll('.kaltools [data-k],.empty [data-k],.kalquick [data-k]').forEach(b=>b.onclick=()=>{const k=b.dataset.k;
    if(k==='set'){icTabSet('cal','set');kalOpen();return}
    if(k==='side'){KAL.side=!kalSideOn();kalDraw();return}
    if(k==='new'){const h=new Date().getHours()+1,day=kalIso(KAL.day);kalNew(day,Math.min(h,22)*60,Math.min(h,22)*60+60,false,'[data-k=new]');return}
    if(k==='quick'){kalQuickSave(w);return}
    if(k==='more'){const q=KAL.qi;if(!q)return;const ep=v=>new Date(q.allday?v+'T00:00':v).getTime()/1000;
      kalFormOpen('new',{title:q.title,location:q.location,allday:q.allday,start:ep(q.start),end:ep(q.end)},'[data-k=quick]');return}
    kalStep(k==='today'?0:k==='prev'?-1:1)});
  w.querySelectorAll('.segc [data-v]').forEach(b=>b.onclick=()=>{KAL.view=b.dataset.v;KAL.sel=null;KAL.form=null;kalLoad()})}
// ‹ Heute ›: one step of the view (a day, a week, two weeks, a month, a year)
function kalStep(s){if(!s)KAL.day=kalDay(new Date());
  else if(KAL.view==='month')KAL.day=new Date(KAL.day.getFullYear(),KAL.day.getMonth()+s,1);
  else if(KAL.view==='year')KAL.day=new Date(KAL.day.getFullYear()+s,0,1);
  else KAL.day=kalAdd(KAL.day,s*(KAL.view==='week'?7:KAL.view==='list'?14:1));
  KAL.sel=null;KAL.form=null;KAL.ghost=null;kalLoad()}
// a phone turns the view by swiping sideways (a finger moving up and down still scrolls)
function kalSwipe(m){let x0=0,y0=0;m.ontouchstart=e=>{const p=e.touches[0];x0=p.clientX;y0=p.clientY};
  m.ontouchend=e=>{const p=e.changedTouches[0],dx=p.clientX-x0,dy=p.clientY-y0;if(Math.abs(dx)>70&&Math.abs(dy)<45&&!KAL.form)kalStep(dx<0?1:-1)}}
// the column: a small month (a tap goes to that day) and the calendars with their colour, each switched on or off
function kalMini(month,mode){const first=new Date(month.getFullYear(),month.getMonth(),1),a=kalMon(first),today=kalIso(new Date()),sel=kalIso(KAL.day);
  const name=first.toLocaleDateString(kalLoc(),{month:'long',year:mode==='side'?'numeric':undefined});
  return `<div class="kmini">`+(mode==='side'?`<div class="kmhd"><button type="button" class="kmnav" data-mnav="-1" aria-label="${esc(t('Monat zurück','Month back'))}">‹</button><b>${esc(name)}</b><button type="button" class="kmnav" data-mnav="1" aria-label="${esc(t('Monat weiter','Month forward'))}">›</button></div>`
    :`<button type="button" class="kmhd kmon" data-mon="${first.getMonth()}">${esc(name)}</button>`)+
    `<div class="kmg">${[0,1,2,3,4,5,6].map(i=>`<span>${esc(kalAdd(a,i).toLocaleDateString(kalLoc(),{weekday:'narrow'}))}</span>`).join('')}`+
    [...Array(42)].map((_,i)=>{const d=kalAdd(a,i),iso=kalIso(d);return `<button type="button" data-mday="${iso}" class="${d.getMonth()!==first.getMonth()?'other':''}${iso===today?' now':''}${iso===sel&&mode==='side'?' sel':''}">${d.getDate()}</button>`}).join('')+`</div></div>`}
function kalSide(w,a){const d=KAL.data,mini=KAL.mini||KAL.day;
  a.innerHTML=kalMini(mini,'side')+`<div class="kcals"><b>${esc(t('Kalender','Calendars'))}</b>`+d.calendars.map((n,i)=>{const ro=!(d.edit||[]).includes(i)&&!(d.add||[]).includes(i);
    return `<label class="kcal ${kalKc(i)}"><input type="checkbox" data-cal="${i}"${KAL_HIDE.has(n)?'':' checked'}><i></i><span>${esc(n)}</span>${(d.shared||[]).includes(i)?`<small>${esc(t('geteilt','shared'))}</small>`:ro?`<small aria-label="${esc(t('nur lesen','read only'))}">🔒</small>`:''}</label>`}).join('')+`</div>`;
  a.querySelectorAll('[data-mnav]').forEach(b=>b.onclick=()=>{KAL.mini=new Date(mini.getFullYear(),mini.getMonth()+Number(b.dataset.mnav),1);kalSide(w,a)});
  a.querySelectorAll('[data-mday]').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.mday+'T00:00');KAL.mini=null;if(KAL.view==='year')KAL.view='day';if(!kalWide())KAL.side=false;KAL.sel=null;KAL.form=null;kalLoad()});
  a.querySelectorAll('[data-cal]').forEach(c=>c.onchange=()=>{kalHideSet(d.calendars[Number(c.dataset.cal)],!c.checked);KAL.mini=mini;kalDraw()});
  if(!kalWide()){const s=w.querySelector('.kalshade');s.hidden=false;s.onclick=()=>{KAL.side=false;kalDraw()}}}
// the year: twelve small months; a month's name opens the month, a day the day
function kalYear(m){const y=KAL.day.getFullYear();m.innerHTML=`<div class="kalyear">${[...Array(12)].map((_,i)=>kalMini(new Date(y,i,1),'year')).join('')}</div>`;
  m.querySelectorAll('[data-mon]').forEach(b=>b.onclick=()=>{KAL.day=new Date(y,Number(b.dataset.mon),1);KAL.view='month';kalLoad()});
  m.querySelectorAll('[data-mday]').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.mday+'T00:00');KAL.view='day';kalLoad()})}
// day and week: hours as rows, all-day appointments on top, overlapping ones side by side; a phone's day sits under
// the strip of its week (a dot for a day with appointments)
function kalGrid(m){const [a,n]=kalRange(),one=KAL.view==='day',days=one?[KAL.day]:[...Array(n)].map((_,i)=>kalAdd(a,i)),today=kalIso(new Date());
  let h0=7,h1=20;for(const day of days)for(const x of kalOn(day))if(!x.allday){const s=new Date(Math.max(x.start*1000,day.getTime())),e=new Date(Math.min(x.end*1000,kalAdd(day,1).getTime()));
    h0=Math.min(h0,s.getHours());h1=Math.max(h1,e.getHours()+(e.getMinutes()?1:0)||24)}
  const gh=KAL.ghost;if(gh&&!gh.allday){h0=Math.min(h0,Math.floor(gh.a/60));h1=Math.max(h1,Math.ceil(gh.b/60))}
  h1=Math.min(Math.max(h1,h0+1),24);KAL.h0=h0;
  if(one&&NARROW()){const s=document.createElement('div');s.className='kweek';const sel=kalIso(KAL.day);
    s.innerHTML=[...Array(7)].map((_,i)=>{const d=kalAdd(kalMon(KAL.day),i),iso=kalIso(d);return `<button type="button" data-wd="${iso}" class="${iso===sel?'on':''}${iso===today?' now':''}" aria-pressed="${iso===sel}"><small>${esc(d.toLocaleDateString(kalLoc(),{weekday:'narrow'}))}</small><b>${d.getDate()}</b><i${kalOn(d).length?'':' hidden'}></i></button>`}).join('');
    s.querySelectorAll('[data-wd]').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.wd+'T00:00');KAL.sel=null;KAL.form=null;kalDraw()});
    m.appendChild(s)}
  const g=document.createElement('div');g.className='kalgrid'+(one?' one':'');g.style.setProperty('--n',days.length);
  g.innerHTML=`<div class="kh"></div>`+days.map(day=>`<button type="button" class="kh${kalIso(day)===today?' now':''}" data-day="${kalIso(day)}">${esc(day.toLocaleDateString(kalLoc(),{weekday:'short'}))}<b>${day.getDate()}</b></button>`).join('')+
    `<div class="kad mut">${esc(t('ganztägig','all day'))}</div>`+days.map(day=>`<div class="kad" data-day="${kalIso(day)}">${kalOn(day).filter(x=>x.allday).map(x=>kalChip(x)).join('')}${gh&&gh.allday&&gh.day===kalIso(day)?`<i class="kchip kghost">${esc(t('Neuer Termin','New appointment'))}</i>`:''}</div>`).join('')+
    `<div class="khours">${[...Array(h1-h0)].map((_,i)=>`<span>${String(h0+i).padStart(2,'0')}:00</span>`).join('')}</div>`+
    days.map(day=>`<div class="kcol" data-day="${kalIso(day)}" style="height:${(h1-h0)*KAL_H}px">${kalLanes(day,h0)}</div>`).join('');
  m.appendChild(g);kalBind(m);kalDrag(g);kalCreate(g);
  g.querySelectorAll('button.kh').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.day+'T00:00');KAL.view='day';KAL.sel=null;kalLoad()});
  const nowCol=g.querySelector(`.kcol[data-day="${today}"]`);if(nowCol){const d=new Date(),y=(d.getHours()+d.getMinutes()/60-h0)*KAL_H;
    if(y>=0&&y<=(h1-h0)*KAL_H){const l=document.createElement('i');l.className='know';l.style.top=y+'px';nowCol.appendChild(l)}}}
function kalLanes(day,h0){const evs=kalOn(day).filter(x=>!x.allday).sort((x,y)=>x.start-y.start),lanes=[],out=[];
  const top=day.getTime()/1000+h0*3600,gh=KAL.ghost;
  for(const x of evs){let i=lanes.findIndex(end=>end<=x.start);if(i<0){i=lanes.length;lanes.push(0)}lanes[i]=Math.max(x.end,x.start+900);out.push([x,i])}
  return out.map(([x,i])=>{const s=Math.max(x.start,day.getTime()/1000),e=Math.min(Math.max(x.end,x.start+900),kalAdd(day,1).getTime()/1000),
    y=(s-top)/3600*KAL_H,hgt=Math.max((e-s)/3600*KAL_H-2,18),w=100/lanes.length;
    return `<button type="button" class="kev ${kalKc(x.cal)}${KAL.sel===x?' on':''}${x.edit?' move':''}" data-i="${KAL.data.events.indexOf(x)}" style="top:${y}px;height:${hgt}px;left:${i*w}%;width:${w}%"><b>${x.edit?'':'<span class="kro" aria-label="'+esc(t('nur lesen','read only'))+'">🔒</span>'}${x.rule?'<span class="krep" aria-label="'+esc(t('wiederholt sich','repeats'))+'">↻</span>':''}${esc(x.title)}</b><small>${esc(kalTime(x.start)+(x.location?' · '+x.location:''))}</small>${x.edit&&!x.allday?`<i class="kres" title="${esc(t('Ziehen ändert die Länge','Drag to change the length'))}"></i>`:''}</button>`}).join('')+
    (gh&&!gh.allday&&gh.day===kalIso(day)?`<div class="kev kghost ${kalKc((KAL.form&&KAL.form.v&&KAL.form.v.cal)||0)}" style="top:${(gh.a-h0*60)/60*KAL_H}px;height:${Math.max((gh.b-gh.a)/60*KAL_H-2,18)}px;left:0;width:100%"><b>${esc((KAL.form&&KAL.form.v&&KAL.form.v.title)||t('Neuer Termin','New appointment'))}</b><small>${esc(kalHm2(new Date(2000,0,1,0,gh.a))+'–'+kalHm2(new Date(2000,0,1,0,gh.b)))}</small></div>`:'')}
// one colour per calendar, written out so the style check finds every class
const KAL_KC=['kc0','kc1','kc2','kc3','kc4','kc5','kc6','kc7'],kalKc=i=>KAL_KC[i%8];
const kalChip=(x,month)=>`<button type="button" class="kchip ${kalKc(x.cal)}${KAL.sel===x?' on':''}" data-i="${KAL.data.events.indexOf(x)}">${esc(x.allday||month===true?x.title:kalTime(x.start)+' '+x.title)}</button>`;
// month: six weeks, at most three appointments a day and how many more; a double click makes one on that day
function kalMonth(m){const [a]=kalRange(),mon=KAL.day.getMonth(),today=kalIso(new Date());
  const g=document.createElement('div');g.className='kalmonth';
  g.innerHTML=[0,1,2,3,4,5,6].map(i=>`<div class="kmh">${esc(kalAdd(a,i).toLocaleDateString(kalLoc(),{weekday:'short'}))}</div>`).join('')+
    [...Array(42)].map((_,i)=>{const day=kalAdd(a,i),evs=kalOn(day);
      return `<div class="kmd${day.getMonth()!==mon?' other':''}${kalIso(day)===today?' now':''}" data-new="${kalIso(day)}"><button type="button" class="kmn" data-day="${kalIso(day)}">${day.getDate()}</button>${evs.slice(0,3).map(x=>kalChip(x,true)).join('')}${evs.length>3?`<button type="button" class="kmore" data-day="${kalIso(day)}">${esc(t(`+${evs.length-3} weitere`,`+${evs.length-3} more`))}</button>`:''}</div>`}).join('');
  m.appendChild(g);kalBind(m);
  g.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>{KAL.day=new Date(b.dataset.day+'T00:00');KAL.view='day';KAL.sel=null;kalLoad()});
  if(kalCanAdd())g.querySelectorAll('[data-new]').forEach(c=>c.ondblclick=e=>{if(e.target!==c)return;kalNew(c.dataset.new,600,660,false)})}
// list: the days with appointments, two weeks at a time
function kalList(m){const [a,n]=kalRange();let html='';
  for(let i=0;i<n;i++){const day=kalAdd(a,i),evs=kalOn(day);if(!evs.length)continue;
    html+=`<div class="ld-grp"><span>${esc(day.toLocaleDateString(kalLoc(),{weekday:'long',day:'numeric',month:'long'}))}</span><span>${evs.length}</span></div>`+
      evs.map(x=>`<button type="button" class="kli${KAL.sel===x?' on':''}" data-i="${KAL.data.events.indexOf(x)}"><span class="kt">${esc(x.allday?t('ganztägig','all day'):kalTime(x.start))}${x.allday?'':`<small>${esc(kalTime(x.end))}</small>`}</span><i class="kbar ${kalKc(x.cal)}"></i><span class="kx"><b>${x.edit?'':'<span class="kro" aria-label="'+esc(t('nur lesen','read only'))+'">🔒</span>'}${x.rule?'<span class="krep" aria-label="'+esc(t('wiederholt sich','repeats'))+'">↻</span>':''}${esc(x.title)}</b>${x.location?`<small>${esc(x.location)}</small>`:''}</span></button>`).join('')}
  m.innerHTML=html||(KAL.busy?'':`<div class="empty">${esc(t('In diesen zwei Wochen steht nichts an.','Nothing planned in these two weeks.'))}</div>`);kalBind(m)}
// a tap: an own appointment opens the inspector at once (Apple), one that is read-only its details
function kalBind(m){m.querySelectorAll('[data-i]').forEach(b=>b.onclick=e=>{e.stopPropagation();if(KAL.dragged){KAL.dragged=false;return}
  const x=KAL.data.events[Number(b.dataset.i)];if(KAL.sel===x&&!KAL.form){kalClose();return}
  if(KAL.form){kalClose();return}   // the first tap closes (and saves) the open inspector
  KAL.ghost=null;KAL.at='';if(x.edit)kalFormOpen('edit',x);else{KAL.sel=x;KAL.form=null;kalDraw()}})}
// why an appointment is read-only (calendars._why): a fixed word from the panel, the text is ours
const KAL_WHY={abo:['Nur lesen: der Kalender ist ein Abo-Link (iCal), Änderungen gehen nur beim Anbieter.','Read only: the calendar is a subscription link (iCal), changes only at its provider.'],
  geteilt:['Nur lesen: ein Kalender, den dir jemand geteilt hat; ändern kann ihn nur, wem er gehört.','Read only: a calendar someone shared with you; only its owner can change it.'],
  lesen:['Nur lesen: dieser Kalender lässt sich hier nicht ändern.','Read only: this calendar cannot be changed here.']};
// repeat and alert as the page names them (kalserie.RULES, kalserie.ALARMS)
const KAL_RULES=[['',t('Nie','Never')],['daily',t('Täglich','Every day')],['weekly',t('Wöchentlich','Every week')],['biweekly',t('Alle 2 Wochen','Every 2 weeks')],['monthly',t('Monatlich','Every month')],['yearly',t('Jährlich','Every year')]];
const KAL_ALARMS=[0,5,10,15,30,60,120,1440,2880];
function kalAlarmName(n){if(!n)return t('Keine','None');if(n%1440===0)return n===1440?t('1 Tag vorher','1 day before'):t(`${n/1440} Tage vorher`,`${n/1440} days before`);
  if(n%60===0)return n===60?t('1 Std. vorher','1 hour before'):t(`${n/60} Std. vorher`,`${n/60} hours before`);return t(`${n} Min. vorher`,`${n} min before`)}
const kalRuleName=(r,u)=>(r==='custom'?t('Eigene Regel','Own rule'):(KAL_RULES.find(x=>x[0]===r)||KAL_RULES[0])[1])+(u?' · '+t('bis ','until ')+new Date(u+'T00:00').toLocaleDateString(kalLoc(),{day:'numeric',month:'short',year:'numeric'}):'');
const kalWho=p=>p.name?`${p.name} <${p.mail}>`:p.mail;
// the details of a read-only appointment (Dominik 2026-10-19 „1a“): a card beside it on computers, a sheet on phones
function kalDetail(w){const box=w.querySelector('.kaldet'),x=KAL.sel;if(!box)return;
  if(KAL.form){kalForm(box);kalPlace(w,box);return}
  if(!x){box.hidden=true;if(!(KAL.side&&!kalWide()))w.querySelector('.kalshade').hidden=true;return}
  const d=KAL.data,when=x.allday?new Date(x.start*1000).toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'long'})+' · '+t('ganztägig','all day')
    :new Date(x.start*1000).toLocaleDateString(kalLoc(),{weekday:'short',day:'numeric',month:'long'})+', '+kalTime(x.start)+'–'+kalTime(x.end);
  box.innerHTML=`<button type="button" class="kalx" data-close="1" aria-label="${esc(t('Schließen','Close'))}">✕</button><div class="mut"><i class="kdot ${kalKc(x.cal)}"></i>${esc((d.calendars||[])[x.cal]||'')}</div><h3>${esc(x.title)}</h3>`+
    `<dl class="ld-facts"><dt>${esc(t('Wann','When'))}</dt><dd>${esc(when)}</dd>${x.location?`<dt>${esc(t('Wo','Where'))}</dt><dd>${esc(x.location)}</dd>`:''}${x.rule?`<dt>${esc(t('Wiederholen','Repeat'))}</dt><dd>${esc(kalRuleName(x.rule,x.until))}</dd>`:''}${x.alarm?`<dt>${esc(t('Erinnerung','Alert'))}</dt><dd>${esc(kalAlarmName(x.alarm))}</dd>`:''}${x.link?`<dt>${esc(t('Link','Link'))}</dt><dd class="kallink">${esc(x.link)}</dd>`:''}</dl>`+
    (x.note?`<div class="kalnote${x.note.length>400||x.note.split('\n').length>8?' cut':''}">${esc(x.note)}</div>${x.note.length>400||x.note.split('\n').length>8?`<button type="button" class="b kalmore" data-act="more">${esc(t('Weiter lesen','Read on'))}</button>`:''}`:'')+
    `<div class="kalro">🔒 ${esc(x.title==='belegt'&&(d.shared||[]).includes(x.cal)?t('Privater Termin aus einem geteilten Kalender.','Private appointment from a shared calendar.'):t(...(KAL_WHY[x.why]||KAL_WHY.lesen)))}</div>`;
  box.querySelector('[data-close]').onclick=()=>kalClose();
  const more=box.querySelector('[data-act=more]');if(more)more.onclick=()=>{box.querySelector('.kalnote').classList.remove('cut');more.remove()};
  kalPlace(w,box)}
// beside what was tapped, inside the view (it scrolls along); on a phone the sheet from below with a shade
function kalPlace(w,box){box.hidden=false;const shade=w.querySelector('.kalshade'),x=KAL.sel||(KAL.form&&KAL.form.mode==='edit'&&KAL.form.x);
  shade.hidden=!NARROW();shade.onclick=()=>kalClose();box.classList.toggle('sheet',NARROW());box.style.left=box.style.top='';
  if(NARROW())return;
  const a=(x&&w.querySelector(`.kalmain [data-i="${KAL.data.events.indexOf(x)}"]`))||w.querySelector('.kalmain .kghost')||(KAL.at&&w.querySelector(KAL.at));
  const wr=w.getBoundingClientRect(),bw=box.offsetWidth,bh=box.offsetHeight;
  if(!a){box.style.left=Math.max(0,wr.width-bw)+'px';box.style.top='60px';return}
  const r=a.getBoundingClientRect();let left=r.right-wr.left+10;
  if(left+bw>wr.width)left=r.left-wr.left-bw-10;
  if(left<0)left=Math.max(0,Math.min(wr.width-bw,r.left-wr.left));
  let top=r.top-wr.top;const vis=-wr.top+innerHeight-bh-12;   // keep it on the screen where possible
  if(top>vis)top=Math.max(vis,0);
  if(left===Math.max(0,Math.min(wr.width-bw,r.left-wr.left)))top=r.bottom-wr.top+8;
  box.style.left=left+'px';box.style.top=Math.max(0,top)+'px';
  w.style.minHeight=Math.max(0,top)+bh+16+'px'}   // a tall inspector low in the view: the page grows, nothing is cut
// closing saves what changed (Apple); a new appointment without a title goes away again
async function kalClose(){if(KAL.form){const ok=await kalFormSave();if(!ok)return}
  KAL.sel=null;KAL.form=null;KAL.ghost=null;kalDraw()}
document.addEventListener('keydown',e=>{if(!(KAL.sel||KAL.form||KAL.asking)||!$('kalview')||!$('cal').classList.contains('on'))return;
  if(e.key==='Escape'){e.preventDefault();if(KAL.asking)KAL.asking(null);else kalClose();return}
  const typing=/^(INPUT|TEXTAREA|SELECT)$/.test((e.target&&e.target.tagName)||'');
  if(typing||!KAL.form||KAL.form.mode!=='edit'||e.metaKey||e.ctrlKey||e.altKey)return;
  if(e.key==='Delete'){e.preventDefault();kalDelete(KAL.form.x)}});
// a click beside the open inspector (on a computer) closes it, and closing saves
document.addEventListener('pointerdown',e=>{if(!KAL.form||KAL.asking||NARROW()||!$('kalview')||!$('cal').classList.contains('on'))return;
  const n=e.target;if(!n||!n.closest||n.closest('.kaldet,.kalask,.kghost,.kaltools,.kalquick'))return;
  if(n.closest('#kalview'))kalClose()},true);
// „Nur dieser Termin“ or „Alle künftigen“ for a repeating appointment (Apple-Stil „5a“); only "future" when the repeat
// itself changes. Resolves "one", "future" or null.
function kalAsk(only,del){const w=$('kalview'),box=w&&w.querySelector('.kalask');if(!box)return Promise.resolve(null);
  return new Promise(res=>{const done=v=>{KAL.asking=null;box.hidden=true;res(v)};KAL.asking=done;
    box.innerHTML=`<div class="kaskc"><b>${esc(del?t('Wiederholten Termin löschen','Delete a repeating appointment'):t('Wiederholten Termin ändern','Change a repeating appointment'))}</b><p>${esc(del?t('Nur diesen Termin löschen oder alle künftigen?','Delete only this appointment or all future ones?'):only==='future'?t('Die Wiederholung gilt ab diesem Termin für alle künftigen.','The repeat applies from this appointment to all future ones.'):t('Nur diesen Termin ändern oder alle künftigen?','Change only this appointment or all future ones?'))}</p>`+
      `<div class="row">${only==='future'?'':`<button class="b" type="button" data-s="one">${esc(del?t('Nur diesen löschen','Delete only this one'):t('Nur dieser Termin','Only this appointment'))}</button>`}<button class="b p" type="button" data-s="future">${esc(del?t('Alle künftigen löschen','Delete all future ones'):t('Alle künftigen','All future ones'))}</button><button class="b" type="button" data-s="">${esc(t('Abbrechen','Cancel'))}</button></div></div>`;
    box.hidden=false;box.querySelectorAll('[data-s]').forEach(b=>b.onclick=()=>done(b.dataset.s||null));
    const f=box.querySelector('[data-s=future]');if(f)f.focus()})}
// every change of an own appointment: the fields that changed (a move sends only times, the rest stays as it is),
// a series with the scope asked; „Rückgängig“ after it asks the Spark to put the old version back
async function kalChange(x,item,msg){let scope='';
  if(x.rid){scope=await kalAsk(('rule' in item)&&(item.rule!==(x.rule||'')||item.until!==(x.until||''))?'future':'',false);if(!scope)return false}
  const body={change:'edit',cal:x.cal,title:x.title,start:x.start,new:item};if(x.rid)Object.assign(body,{uid:x.uid,rid:x.rid,scope});
  const d=await kalSend('PUT',body,msg);if(!d)return false;
  KAL.undo={text:(scope==='future'?t('Alle künftigen geändert: ','All future ones changed: '):t('Gespeichert: ','Saved: '))+item.title,token:d.undo,at:Date.now()};return true}
async function kalDelete(x){const msg=$('kalview').querySelector('.kaldet .kalmsg')||$('kalview').querySelector('.kalundo');let scope='';
  if(x.rid){scope=await kalAsk('',true);if(!scope)return}
  else if(!confirm(t('Termin „','Delete "')+x.title+t('“ löschen?','"?')))return;
  const body={change:'delete',cal:x.cal,title:x.title,start:x.start};if(x.rid)Object.assign(body,{uid:x.uid,rid:x.rid,scope});
  const d=await kalSend('PUT',body,msg);if(d)KAL.undo={text:t('Gelöscht: ','Deleted: ')+x.title,token:d.undo,at:Date.now()}}
// moved: a day, a week, or dragged (days and minutes); the lower edge dragged changes only the end
function kalMove(x,days,mins,endOnly){const s=new Date(x.start*1000),e=new Date(Math.max(x.end,x.start)*1000);
  if(!endOnly){s.setDate(s.getDate()+days);s.setMinutes(s.getMinutes()+mins)}
  e.setDate(e.getDate()+days);e.setMinutes(e.getMinutes()+mins);if(e<=s)e.setTime(s.getTime()+900000);
  return {at:Math.round(s.getTime()/1000),end:Math.round(e.getTime()/1000),item:{title:x.title,allday:!!x.allday,location:x.location||'',
    start:x.allday?kalIso(s):kalIso(s)+'T'+kalHm2(s),end:x.allday?kalIso(e):kalIso(e)+'T'+kalHm2(e)}}}
function kalShift(x,days,mins,endOnly){const msg=$('kalview').querySelector('.kaldet .kalmsg')||$('kalview').querySelector('.kalundo');
  return kalChange(x,kalMove(x,days,mins,endOnly).item,msg)}
function kalUndo(w){const u=KAL.undo,box=w.querySelector('.kalundo');if(!box)return;box.innerHTML='';
  if(!u||Date.now()-u.at>60000||!u.token){KAL.undo=null;return}
  box.innerHTML=`<div class="note">${esc(u.text)} <button class="b" type="button" data-u="1">${esc(t('Rückgängig','Undo'))}</button></div>`;
  box.querySelector('[data-u]').onclick=async()=>{KAL.undo=null;box.innerHTML=`<div class="note fh">${esc(t('Nehme zurück …','Taking it back …'))}</div>`;
    const {r,d}=await apiTry('/api/profile/calendar/undo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({undo:u.token})});
    if(!r.ok){box.innerHTML=`<div class="note warn">${esc(r.status===410?t('Zu spät zum Zurücknehmen.','Too late to take it back.'):errSay(r.status,d.detail,''))}</div>`;return}
    KAL.sel=null;KAL.form=null;kalLoad();setTimeout(()=>{if($('kalview'))kalLoad(true)},KAL_BEHIND_MS)}}
// week and day: an own appointment is dragged with the mouse to another time (quarter hours) or day, its lower edge
// to another length; on a phone the inspector's +1 Tag and +1 Woche move it (a finger scrolls the view)
function kalDrag(g){g.querySelectorAll('.kev.move').forEach(b=>{const x=KAL.data.events[Number(b.dataset.i)];if(!x||x.allday)return;
  b.title=t('Ziehen zum Verschieben','Drag to move');
  b.onpointerdown=e=>{if(e.pointerType==='touch'||e.button)return;const res=e.target.classList.contains('kres');e.stopPropagation();
    const y0=e.clientY,x0=e.clientX,col0=b.parentElement,h0=b.offsetHeight;let moved=false,dm=0,col=col0;
    const mv=ev=>{if(!moved&&Math.abs(ev.clientY-y0)<5&&Math.abs(ev.clientX-x0)<5)return;moved=true;b.classList.add('drag');ev.preventDefault();
      dm=Math.round((ev.clientY-y0)/KAL_H*4)*15;
      if(res){b.style.height=Math.max(18,h0+dm/60*KAL_H)+'px';const sm=b.querySelector('small');if(sm)sm.textContent=kalTime(x.start)+'–'+kalTime(kalMove(x,0,dm,true).end);return}
      const over=document.elementsFromPoint(ev.clientX,ev.clientY).find(n=>n.classList&&n.classList.contains('kcol'));
      if(over&&over!==col){col=over;over.appendChild(b)}
      b.style.transform=`translateY(${dm/60*KAL_H}px)`;
      const days=Math.round((new Date(col.dataset.day+'T12:00')-new Date(col0.dataset.day+'T12:00'))/864e5);
      const sm=b.querySelector('small');if(sm)sm.textContent=kalTime(kalMove(x,days,dm).at)};
    const up=()=>{removeEventListener('pointermove',mv);removeEventListener('pointerup',up);if(!moved)return;KAL.dragged=true;
      setTimeout(()=>{KAL.dragged=false},0);
      const days=res?0:Math.round((new Date(col.dataset.day+'T12:00')-new Date(col0.dataset.day+'T12:00'))/864e5);
      if(!days&&!dm){kalDraw();return}
      KAL.sel=null;kalShift(x,days,dm,res).then(ok=>{if(!ok)kalDraw()})};
    addEventListener('pointermove',mv);addEventListener('pointerup',up)}})}
// free time in the week or the day: drag with the mouse (quarter hours) or double-click makes an appointment and opens
// its inspector with the title to type; on a phone a long press; a double click in the all-day row makes an all-day one
function kalCreate(g){if(!kalCanAdd())return;
  g.querySelectorAll('.kcol').forEach(col=>{const at=ev=>{const r=col.getBoundingClientRect();return KAL.h0*60+Math.max(0,Math.floor((ev.clientY-r.top)/KAL_H*4))*15};
    col.ondblclick=e=>{if(e.target!==col)return;const m=at(e);kalNew(col.dataset.day,m,m+60,false)};
    col.onpointerdown=e=>{if(e.target!==col||e.button)return;
      if(e.pointerType==='touch'){const p0=[e.clientX,e.clientY],m=at(e),tm=setTimeout(()=>{stop();kalNew(col.dataset.day,m,m+60,false)},550);
        const mv=ev=>{if(Math.abs(ev.clientX-p0[0])>8||Math.abs(ev.clientY-p0[1])>8)stop()},stop=()=>{clearTimeout(tm);col.removeEventListener('pointermove',mv);col.removeEventListener('pointerup',stop);col.removeEventListener('pointercancel',stop)};
        col.addEventListener('pointermove',mv);col.addEventListener('pointerup',stop);col.addEventListener('pointercancel',stop);return}
      const m0=at(e);let ghost=null,m1=m0;
      const mv=ev=>{m1=at(ev);if(m1===m0&&!ghost)return;ev.preventDefault();
        if(!ghost){ghost=document.createElement('div');ghost.className='kev kghost '+kalKc((KAL.data.add||[0])[0]);col.appendChild(ghost)}
        const a=Math.min(m0,m1),b=Math.max(m0,m1)+15;ghost.style.cssText=`top:${(a-KAL.h0*60)/60*KAL_H}px;height:${(b-a)/60*KAL_H-2}px;left:0;width:100%`;
        ghost.textContent=kalHm2(new Date(2000,0,1,0,a))+'–'+kalHm2(new Date(2000,0,1,0,b))};
      const up=()=>{removeEventListener('pointermove',mv);removeEventListener('pointerup',up);if(!ghost)return;
        KAL.dragged=true;setTimeout(()=>{KAL.dragged=false},0);kalNew(col.dataset.day,Math.min(m0,m1),Math.max(m0,m1)+15,false)};
      addEventListener('pointermove',mv);addEventListener('pointerup',up)}});
  g.querySelectorAll('.kad[data-day]').forEach(c=>c.ondblclick=e=>{if(e.target!==c)return;kalNew(c.dataset.day,0,1440,true)})}
// a new appointment at day (YYYY-MM-DD) from minute a to b: the ghost in the view and the inspector beside it
function kalNew(day,a,b,allday,at){const d0=new Date(day+'T00:00'),s=new Date(d0.getTime()+a*60000),e=new Date(d0.getTime()+b*60000);
  KAL.ghost=(KAL.view==='week'||KAL.view==='day')?{day,a,b,allday}:null;
  kalFormOpen('new',{title:'',allday:!!allday,location:'',start:s.getTime()/1000,end:allday?kalAdd(d0,1).getTime()/1000:e.getTime()/1000},at||'')}
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
  const d=await kalSend('POST',{title:q.title,start:q.start,end:q.end,allday:q.allday,location:q.location,calendar:''},w.querySelector('.kalqmsg'));
  if(d){KAL.q='';KAL.qi=null;KAL.undo={text:t('Eingetragen: ','Added: ')+q.title,token:d.undo,at:Date.now()}}}
// the inspector (Apple-Stil „4a“): every field of a new or an own appointment in groups; the values live in
// KAL.form.v, so a look at the calendar meanwhile never loses what is being typed. Closing saves what changed.
function kalFormOpen(mode,x,at){const add=(KAL.data&&KAL.data.add)||[],s=new Date(x.start*1000),e=new Date(Math.max(x.end-(x.allday?86400:0),x.start)*1000);
  const v={title:x.title||'',location:x.location||'',allday:!!x.allday,sd:kalIso(s),st:x.allday?'10:00':kalHm2(s),ed:kalIso(e),et:x.allday?'11:00':kalHm2(new Date(x.end*1000)),
    rule:x.rule||'',until:x.until||'',alarm:x.alarm||0,people:(x.people||[]).map(p=>({name:p.name||'',mail:p.mail})),note:x.note||'',link:x.link||'',cal:mode==='new'?add[0]:x.cal};
  KAL.sel=mode==='edit'?x:null;KAL.at=at||'';KAL.form={mode,x:mode==='edit'?x:null,v,orig:JSON.stringify(v)};kalDraw();
  const ti=$('kalview')&&$('kalview').querySelector('.kaldet [data-f=title]');if(ti&&mode==='new')ti.focus()}
function kalItem(v,full){const item={title:v.title.trim(),allday:v.allday,location:v.location.trim(),
  start:v.allday?v.sd:v.sd+'T'+v.st,end:v.allday?kalIso(kalAdd(new Date(v.ed+'T00:00'),1)):v.ed+'T'+v.et};
  if(full)Object.assign(item,{rule:v.rule,until:v.rule&&v.rule!=='custom'?v.until:'',alarm:Number(v.alarm)||0,people:v.people,note:v.note.trim(),link:v.link.trim()});
  return item}
function kalForm(box){const f=KAL.form,v=f.v,x=f.x,d=KAL.data,add=(d.add||[]).map(i=>[i,d.calendars[i]]);
  const opt=(list,cur)=>list.map(([k,l])=>`<option value="${esc(String(k))}"${String(k)===String(cur)?' selected':''}>${esc(l)}</option>`).join('');
  const rules=KAL_RULES.concat(v.rule==='custom'?[['custom',t('Eigene Regel (bleibt)','Own rule (stays)')]]:[]),alarms=KAL_ALARMS.concat(KAL_ALARMS.includes(Number(v.alarm))?[]:[Number(v.alarm)]).map(n=>[n,kalAlarmName(n)]);
  box.innerHTML=`<button type="button" class="kalx" data-close="1" aria-label="${esc(t('Schließen und sichern','Close and save'))}">✕</button>`+
    `<input class="kalti" data-f="title" maxlength="200" placeholder="${esc(t('Neuer Termin','New appointment'))}" aria-label="${esc(t('Titel','Title'))}" value="${esc(v.title)}">`+
    `<input data-f="location" maxlength="200" placeholder="${esc(t('Ort oder Videoanruf','Place or video call'))}" aria-label="${esc(t('Ort','Place'))}" value="${esc(v.location)}">`+
    `<div class="kgrp"><label class="kalad"><input type="checkbox" data-f="allday"${v.allday?' checked':''}> ${esc(t('ganztägig','all day'))}</label>`+
    `<div class="krow"><span>${esc(t('Beginn','Starts'))}</span><input type="date" data-f="sd" value="${esc(v.sd)}"><input type="time" data-f="st" value="${esc(v.st)}"${v.allday?' hidden':''}></div>`+
    `<div class="krow"><span>${esc(t('Ende','Ends'))}</span><input type="date" data-f="ed" value="${esc(v.ed)}"><input type="time" data-f="et" value="${esc(v.et)}"${v.allday?' hidden':''}></div></div>`+
    `<div class="kgrp"><div class="krow"><span>${esc(t('Wiederholen','Repeat'))}</span><select data-f="rule">${opt(rules,v.rule)}</select></div>`+
    `<div class="krow"${v.rule&&v.rule!=='custom'?'':' hidden'}><span>${esc(t('Endet','Ends'))}</span><input type="date" data-f="until" value="${esc(v.until)}" aria-label="${esc(t('Wiederholung endet (leer: nie)','Repeat ends (empty: never)'))}"></div>`+
    `<div class="krow"><span>${esc(t('Erinnerung','Alert'))}</span><select data-f="alarm">${opt(alarms,v.alarm)}</select></div>`+
    (f.mode==='new'&&add.length>1?`<div class="krow"><span>${esc(t('Kalender','Calendar'))}</span><select data-f="cal">${opt(add,v.cal)}</select></div>`
      :`<div class="krow"><span>${esc(t('Kalender','Calendar'))}</span><b class="kcalname"><i class="kdot ${kalKc(v.cal||0)}"></i>${esc((d.calendars||[])[v.cal]||'')}</b></div>`)+`</div>`+
    `<div class="kgrp"><span class="kglab">${esc(t('Personen','People'))}</span><div class="kpeople">${v.people.map((p,i)=>`<span class="kpp">${esc(kalWho(p))}<button type="button" data-pp="${i}" aria-label="${esc(t('Entfernen','Remove'))}">✕</button></span>`).join('')}</div>`+
    `<input data-f="pin" maxlength="300" autocomplete="off" placeholder="${esc(t('Name <anna@beispiel.de> und Enter','Name <anna@example.org> and Enter'))}" aria-label="${esc(t('Person hinzufügen','Add a person'))}"><small class="mut">${esc(t('Nur eine Liste im Termin: es geht keine Einladung raus.','Only a list in the appointment: no invitation goes out.'))}</small></div>`+
    `<div class="kgrp"><textarea data-f="note" maxlength="2000" rows="3" placeholder="${esc(t('Notiz','Note'))}" aria-label="${esc(t('Notiz','Note'))}">${esc(v.note)}</textarea>`+
    `<input data-f="link" maxlength="300" type="url" placeholder="${esc(t('Link (https://…)','Link (https://…)'))}" aria-label="${esc(t('Link','Link'))}" value="${esc(v.link)}"></div>`+
    `<div class="row kalacts"><button class="b p" type="button" data-act="save">${esc(f.mode==='new'?t('Hinzufügen','Add'):t('Fertig','Done'))}</button>`+
    (f.mode==='edit'?`<button class="b" type="button" data-act="day">${esc(t('+1 Tag','+1 day'))}</button><button class="b" type="button" data-act="week">${esc(t('+1 Woche','+1 week'))}</button><button class="b" type="button" data-act="del">${esc(t('Löschen','Delete'))}</button>`:'')+
    `</div><div class="kalmsg fh"></div>`;
  const q=k=>box.querySelector(`[data-f=${k}]`);
  ['title','location','sd','st','ed','et','until','note','link'].forEach(k=>{const n=q(k);if(n)n.oninput=()=>{v[k]=n.value;
    if(k==='sd'&&v.ed<v.sd){v.ed=v.sd;q('ed').value=v.ed}if(k==='title'){const g=document.querySelector('#kalview .kghost b');if(g)g.textContent=v.title||t('Neuer Termin','New appointment')}}});
  q('allday').onchange=()=>{v.allday=q('allday').checked;q('st').hidden=q('et').hidden=v.allday};
  q('rule').onchange=()=>{v.rule=q('rule').value;q('until').parentElement.hidden=!v.rule||v.rule==='custom'};
  q('alarm').onchange=()=>{v.alarm=Number(q('alarm').value)};
  if(q('cal'))q('cal').onchange=()=>{v.cal=Number(q('cal').value)};
  const pin=q('pin'),addP=()=>{const s=pin.value.trim().replace(/[,;]$/,'');if(!s)return true;const m=s.match(/^(.*?)\s*<\s*([^<>\s]+@[^<>\s]+\.[A-Za-z]{2,24})\s*>$/)||s.match(/^()([^<>\s,;]+@[^<>\s,;]+\.[A-Za-z]{2,24})$/);
    if(!m){kalMsg(box,t('Bitte eine Adresse wie anna@beispiel.de.','Please an address like anna@example.org.'),true);return false}
    if(v.people.length>=20){kalMsg(box,t('Höchstens 20 Personen.','At most 20 people.'),true);return false}
    if(!v.people.some(p=>p.mail.toLowerCase()===m[2].toLowerCase()))v.people.push({name:m[1].replace(/^"|"$/g,'').trim(),mail:m[2]});pin.value='';kalForm(box);box.querySelector('[data-f=pin]').focus();return true};
  pin.onkeydown=e=>{if(e.key==='Enter'||e.key===','){e.preventDefault();addP()}};
  box.querySelectorAll('[data-pp]').forEach(b=>b.onclick=()=>{v.people.splice(Number(b.dataset.pp),1);kalForm(box)});
  q('title').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();kalClose()}};
  box.querySelector('[data-close]').onclick=()=>kalClose();
  box.querySelector('[data-act=save]').onclick=()=>kalClose();
  const on=(k,fn)=>{const b=box.querySelector(`[data-act=${k}]`);if(b)b.onclick=fn};
  on('day',()=>kalShift(x,1,0));on('week',()=>kalShift(x,7,0));on('del',()=>kalDelete(x))}
const kalMsg=(box,text,bad)=>{const m=box.querySelector('.kalmsg');if(m){m.className='kalmsg '+(bad?'err':'fh');m.textContent=text}};
// the inspector's save: nothing changed or a new one without a title closes; else POST (new) or PUT (own, a series
// with its scope); true when the inspector may close
async function kalFormSave(){const f=KAL.form,box=$('kalview')&&$('kalview').querySelector('.kaldet');if(!f)return true;const v=f.v;
  const pin=box&&box.querySelector('[data-f=pin]');if(pin&&pin.value.trim()){kalMsg(box,t('Die Person ist noch nicht hinzugefügt (Enter).','The person is not added yet (Enter).'),true);return false}
  if(JSON.stringify(v)===f.orig||(f.mode==='new'&&!v.title.trim()))return true;
  if(!v.title.trim()){kalMsg(box,t('Der Titel fehlt.','The title is missing.'),true);return false}
  const item=kalItem(v,true),msg=box.querySelector('.kalmsg');
  if(f.mode==='new'){const d=KAL.data,add=d.add||[],c=add.includes(v.cal)?v.cal:add[0];
    const r=await kalSend('POST',Object.assign(item,{calendar:c!==add[0]||(d.shared||[]).includes(c)?d.calendars[c]:''}),msg);
    if(r)KAL.undo={text:t('Hinzugefügt: ','Added: ')+item.title,token:r.undo,at:Date.now()};return !!r}
  const o=JSON.parse(f.orig);if(o.rule===v.rule&&o.until===v.until){delete item.rule;delete item.until}   // a series keeps its rule as it is
  return kalChange(f.x,item,msg)}
async function kalSend(method,body,msg){const cls=msg.className.split(' ')[0];msg.className=cls+' fh';msg.textContent=t('Speichere im Kalender …','Saving to the calendar …');
  const {r,d}=await apiTry('/api/profile/calendar/event',{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign(body,{tz:TZ()}))});
  if(!r.ok){msg.className=cls+' err';msg.textContent=r.status===409?t('Der Termin ist so nicht mehr da (woanders geändert). Die Seite lädt neu.','The appointment is no longer there like this (changed elsewhere). The page reloads.'):errSay(r.status,d.detail,'');if(r.status===409)kalLoad();return false}
  // Spark-Kalender Stufe 2: saved in the Spark's copy, the server gets it behind; a look a little later shows a refusal
  KAL.form=null;KAL.sel=null;KAL.ghost=null;kalLoad();setTimeout(()=>{if($('kalview'))kalLoad(true)},KAL_BEHIND_MS);return d||{}}
const KAL_BEHIND_MS=5000
