// Listen (Dominik 2026-10-20 „1a 2a“, plan listen-teilen/plan.md Stufe 1): the shopping list, the to-do list and own
// lists as a page of its own in the menu, like Kalender and E-Mail. „Listen“ shows the lists on the left and the one
// tapped on the right (GET /api/profile/tasks, tasks.py): a field to add at once, the entries with who put them on,
// when and from where, the shop's departments, „Zuletzt erledigt“ with „Zurückholen“. „Einstellungen“ holds where the
// two fixed lists live and the iPhone shortcut (the box #taskbox, a page of Ich until Listen came). Entries and
// names are the person's words: only through esc().
// Stufe 2 (Listen teilen, plan „3a“): „Teilen“ on an own list gives each other profile Aus, Sehen or Mitschreiben;
// lists others share come under „Mit mir geteilt“ ("<owner>.<list>"), see-only ones without field and ticks, and
// deleting stays with the owner. The panel checks every call (tasks.where); the page only leaves out what it may not.
// Apple-Stil Stufe 4 (Dominik 2026-10-20 „7a“, plan apple-stil/plan.md, board 4-listen.png): like Apple's Reminders.
// On the left the search, four tiles counted here from the entries (Heute: due today or before, Geplant: with a date,
// Alle: open, Markiert: flagged) and the lists with colour and symbol, dragged into the own order. On the right the
// list with an empty row at its end (type, Enter, the next one), entries dragged to sort or onto another list on the
// left, and ⓘ per entry: title, note, date, time with „Erinnern“ (a reminder of Timer und Erinnerungen), flag,
// priority, list. Every change answers with the whole state (tasks.get_lists); the info card stays open meanwhile.
const LST={data:null,sel:'',seq:0,busy:false,err:'',msg:'',form:null,ask:false,allDone:false,share:false,q:'',info:null,showDone:false,drag:null};
// the menu entry only for a signed-in profile that may use lists (start.js, like Kalender)
window.lstStart=who=>{const on=!!(who&&who.profile&&who.tasks);document.querySelectorAll('nav button[data-s=listen]').forEach(b=>b.hidden=!on)};
const lstWhen=s=>{if(!s)return '';const d=new Date(s*1000),n=new Date(),y=new Date(n.getFullYear(),n.getMonth(),n.getDate()-1),
    tm=d.toLocaleTimeString(kalLoc(),{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===n.toDateString()?t('heute ','today ')+tm:d.toDateString()===y.toDateString()?t('gestern ','yesterday ')+tm
    :n-d<6*864e5?d.toLocaleDateString(kalLoc(),{weekday:'short'})+' '+tm:d.toLocaleDateString(kalLoc(),{day:'numeric',month:'short'})};
// today as „JJJJ-MM-TT“ in the browser's time (the tiles and the red date)
const lstToday=(add=0)=>{const n=new Date();n.setDate(n.getDate()+add);return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}-${String(n.getDate()).padStart(2,'0')}`};
// a date as said: „Heute“, „Morgen“, „Fr 24.10.“; with the time „Morgen, 17:00“
function lstDay(due,at){if(!due)return '';const d=new Date(due+'T12:00');if(isNaN(d))return '';
  const w=due===lstToday()?t('Heute','Today'):due===lstToday(1)?t('Morgen','Tomorrow'):due===lstToday(-1)?t('Gestern','Yesterday')
    :d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{weekday:'short',day:'2-digit',month:'2-digit'});
  return w+(at?', '+at:'')}
// „bis“ of an entry: the date (and time) as a chip, red once it has passed
function lstDue(x){const w=lstDay(x.due,x.at);if(!w)return '';
  return ` <span class="lstdue${x.due<lstToday()?' late':''}">${esc(w)}${x.remind?' '+ic('bell'):''}</span>`}
// „Dominik · heute 08:15 · per Stimme“: who, when, from where (the source is a fixed word, tasks.SOURCES)
function lstWho(x){const d=LST.data,src=d&&d.sources&&d.sources[x.src];
  return [x.by_name&&PROFILE&&x.by_name===PROFILE.name?t('ich','me'):x.by_name,lstWhen(x.t),src?t(src[0],src[1]):''].filter(Boolean).join(' · ')}
const lstName=l=>L==='en'?l.name_en:l.name;
const lstList=()=>LST.data&&LST.data.lists[LST.sel];
const lstMay=l=>!!l&&!l.target&&(!l.shared||l.shared.level==='add');   // put on, tick off, sort, info
// the four tiles: key, icon, colour, name; what each counts (open entries of every list, also the shared ones)
const LST_SMART=[['@heute','today','blau',['Heute','Today'],x=>x.due&&x.due<=lstToday()],['@geplant','cal','rot',['Geplant','Scheduled'],x=>!!x.due],
  ['@alle','listen','grau',['Alle','All'],()=>true],['@markiert','flag','orange',['Markiert','Flagged'],x=>x.flag]];
function lstAll(){const d=LST.data,out=[];if(!d)return out;for(const k of d.order){const l=d.lists[k];for(const x of l.items)out.push({x,k,l})}return out}
const lstSmart=k=>LST_SMART.find(s=>s[0]===k);
async function lstLoad(){if(!PROFILE||!TASK_ON)return;const seq=++LST.seq;LST.busy=true;lstDraw();
  const {r,d}=await apiTry('/api/profile/tasks');if(seq!==LST.seq)return;
  if(r.ok){LST.data=d;LST.err='';if(!d.lists[LST.sel]&&!lstSmart(LST.sel)&&!NARROW())LST.sel=d.order[0]||''}else LST.err=errSay(r.status,d.detail,'');
  LST.busy=false;lstDraw()}
// every change answers with the whole state (tasks.get_lists): drawn at once, no second request
async function lstSend(path,method,body){const {r,d}=await apiTry(path,method==='DELETE'?{method}:xjson(method,body));
  if(!r.ok){LST.msg=errSay(r.status,d.detail,'');lstDraw();return null}
  LST.data=d;LST.msg='';if(!d.lists[LST.sel]&&!lstSmart(LST.sel))LST.sel=NARROW()?'':d.order[0]||'';lstDraw();return d}
const lstPath=(k,rest='')=>'/api/profile/tasks/'+encodeURIComponent(k)+rest;
const LST_BOX=$('taskbox');   // the tab „Einstellungen“ shows it; kept in the section between visits (see POST_BOXES)
function lstOpen(){if(!PROFILE)return;const root=$('lstroot');if(LST_BOX){LST_BOX.hidden=true;$('listen').appendChild(LST_BOX)}root.textContent='';
  root.appendChild(icTabs('listen',[{k:'show',label:OWN_PAGES.taskbox[2],body:lstBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('taskbox');b.hidden=false;lzb(b,showTasks,{auth:true}).catch(()=>{});return b}}]));
  lstLoad()}
function lstBody(){const w=document.createElement('div');w.className='ld-box ld-frame lst';w.id='lstview';lstPaint(w);return w}
function lstDraw(){const w=$('lstview');if(w)lstPaint(w)}
// one list in the left column: its colour circle with the symbol, the name, how many are open
function lstRow(k){const d=LST.data,l=d.lists[k],n=l.items.length,ppl=Object.keys(l.shares||{}).length,
    sub=l.shared?t('von ','from ')+l.shared.owner:ppl?t('geteilt mit ','shared with ')+ppl:l.target?t('in ','in ')+l.target.name:l.error?t('nicht erreichbar','not reachable'):'';
  return `<div class="ld-row lstrow lc-${esc(l.color||'blau')}${k===LST.sel?' on':''}" role="button" tabindex="0" draggable="true" data-l="${esc(k)}"><span class="ld-ico lstico" aria-hidden="true">${esc(l.icon)}</span>`+
    `<span class="ld-mid"><b>${esc(lstName(l))}</b>${sub?`<small>${esc(sub)}</small>`:''}</span><span class="ld-right"><b class="lstcnt">${n}</b></span></div>`}
function lstPaint(w){const d=LST.data;w.classList.toggle('ld-sel',!!LST.sel);
  if(!w.querySelector('.ld-split')){w.innerHTML=`<div class="lstwarn"></div><div class="ld-split"><div class="ld-list"></div><div class="ld-detail lstdet" hidden></div></div><div class="lstpop" hidden></div>`}
  w.querySelector('.lstwarn').innerHTML=LST.err?`<div class="note warn">${esc(t('Die Listen kamen nicht an: ','The lists did not arrive: ')+LST.err)}</div>`:'';
  const list=w.querySelector('.ld-list');list.classList.toggle('busy',LST.busy&&!d);
  if(!d){list.innerHTML=LST.busy?`<div class="ld-empty mut">${esc(t('Lade die Listen …','Loading the lists …'))}</div>`:'';return}
  const f=list.querySelector('[data-k=find]'),fkeep=f&&document.activeElement===f;
  const all=lstAll(),tile=([k,icon,col,name,fit])=>`<button type="button" class="lsttile lc-${col}${k===LST.sel?' on':''}" data-l="${k}"><span class="lsttic" aria-hidden="true">${ic(icon)}</span><b>${all.filter(e=>fit(e.x)).length}</b><span>${esc(t(name[0],name[1]))}</span></button>`;
  const mine=d.order.filter(k=>!d.lists[k].shared),theirs=d.order.filter(k=>d.lists[k].shared),own=mine.filter(k=>d.lists[k].own);
  list.innerHTML=`<div class="lstfind"><input type="search" data-k="find" maxlength="80" autocomplete="off" value="${esc(LST.q)}" placeholder="${esc(t('Suchen','Search'))}" aria-label="${esc(t('In allen Listen suchen','Search all lists'))}"></div>`+
    `<div class="lsttiles">${LST_SMART.map(tile).join('')}</div>`+
    `<div class="ld-grp"><span>${esc(t('Meine Listen','My lists'))}</span><span>${mine.length}</span></div>`+mine.map(lstRow).join('')+
    (theirs.length?`<div class="ld-grp"><span>${esc(t('Mit mir geteilt','Shared with me'))}</span><span>${theirs.length}</span></div>`+theirs.map(lstRow).join(''):'')+
    (own.length<d.max_lists?`<div class="ld-more"><button class="ic-lnk" type="button" data-k="new">${ic('plus')} ${esc(t('Liste hinzufügen','Add list'))}</button></div>`:'')+
    (LST.form&&LST.form.make?lstFormHtml():'');
  const fi=list.querySelector('[data-k=find]');if(fkeep){fi.focus();fi.setSelectionRange(fi.value.length,fi.value.length)}
  fi.oninput=()=>{LST.q=fi.value;LST.info=null;lstDetail(w)};
  const go=k=>{LST.sel=k;LST.ask=false;LST.form=null;LST.msg='';LST.allDone=false;LST.share=false;LST.info=null;LST.q='';lstDraw()};
  list.querySelectorAll('[data-l]').forEach(r=>{r.onclick=()=>go(r.dataset.l);r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go(r.dataset.l)}}});
  lstDragLists(list);
  const nb=list.querySelector('[data-k=new]');if(nb)nb.onclick=()=>{LST.form={make:true,name:'',icon:d.icons[0],color:'blau'};lstDraw();const i=list.querySelector('[data-f=name]');if(i)i.focus()};
  if(LST.form&&LST.form.make)lstFormBind(list);
  lstDetail(w)}
// the card for a new list, a new name or only a new colour (the fixed lists): a name, a colour and a symbol from the
// fixed choice (tasks.COLORS, tasks.ICONS)
function lstFormHtml(){const f=LST.form,d=LST.data;
  return `<div class="lstform">`+(f.fixed?'':`<label>${esc(t('Name der Liste','Name of the list'))}</label><input data-f="name" maxlength="40" autocomplete="off" value="${esc(f.name)}" placeholder="${esc(t('z. B. Baumarkt','e.g. Hardware store'))}">`)+
    `<div class="lstcols" role="radiogroup" aria-label="${esc(t('Farbe','Colour'))}">${d.colors.map(c=>`<button type="button" class="lstcol lc-${esc(c)}${c===f.color?' on':''}" data-c="${esc(c)}" aria-pressed="${c===f.color}" aria-label="${esc(c)}"></button>`).join('')}</div>`+
    (f.fixed?'':`<div class="lsticons" role="radiogroup" aria-label="${esc(t('Symbol','Symbol'))}">${d.icons.map(i=>`<button type="button" class="ld-chip${i===f.icon?' on':''}" data-i="${esc(i)}" aria-pressed="${i===f.icon}">${esc(i)}</button>`).join('')}</div>`)+
    `<div class="row"><button class="b p" type="button" data-f="save">${esc(f.make?t('Anlegen','Create'):t('Speichern','Save'))}</button><button class="b" type="button" data-f="cancel">${esc(t('Abbrechen','Cancel'))}</button></div></div>`}
function lstFormBind(box){const f=LST.form,i=box.querySelector('[data-f=name]');
  if(i){i.oninput=()=>{f.name=i.value};i.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();box.querySelector('[data-f=save]').click()}}}
  const pick=(sel,key,attr)=>box.querySelectorAll(sel).forEach(b=>b.onclick=()=>{f[key]=b.dataset[attr];box.querySelectorAll(sel).forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',String(on))})});
  pick('[data-i]','icon','i');pick('[data-c]','color','c');
  box.querySelector('[data-f=cancel]').onclick=()=>{LST.form=null;lstDraw()};
  box.querySelector('[data-f=save]').onclick=async()=>{if(!f.fixed&&!f.name.trim())return;
    const d=f.make?await lstSend('/api/profile/listen','POST',{name:f.name,icon:f.icon,color:f.color})
      :await lstSend('/api/profile/listen/'+encodeURIComponent(LST.sel),'PUT',f.fixed?{color:f.color}:{name:f.name,icon:f.icon,color:f.color});
    if(d){if(f.make&&d.made)LST.sel=d.made;LST.form=null;lstDraw()}}}
// one entry: the round box, the title (with „!“ for its priority, the amount), a grey line (note, date, who and when),
// the flag and ⓘ; it can be dragged when the list may be written
function lstItem(x,k,l,head){const write=lstMay(l),pr=x.prio?'!'.repeat(x.prio)+' ':'';
  const sub=[x.note?x.note.split('\n')[0].slice(0,80):'',lstWho(x)].filter(Boolean).join(' · ');
  return `<div class="lstitem lc-${esc(l.color||'blau')}${LST.info&&LST.info.id===x.id?' on':''}" data-id="${esc(x.id)}" data-l="${esc(k)}"${write?' draggable="true"':''}>`+
    (write?`<button type="button" class="lstck" data-tick="${esc(x.id)}" aria-label="${esc(t('Abhaken: ','Tick off: ')+x.text)}"></button>`:'<span class="lstck" aria-hidden="true"></span>')+
    `<span class="lstit"><b>${pr?`<span class="lstprio">${pr}</span>`:''}${esc(x.text)}</b>${x.qty?` <span class="lstqty">${esc(x.qty)}</span>`:''}${lstDue(x)}`+
    `${head?` <span class="lstin">${esc(lstName(l))}</span>`:''}<small>${esc(sub)}</small></span>`+
    (x.flag?`<span class="lstflag" title="${esc(t('Markiert','Flagged'))}">${ic('flag')}</span>`:'')+
    (write?`<button type="button" class="ic-ib lstinf" data-info="${esc(x.id)}" title="${esc(t('Info','Info'))}" aria-label="${esc(t('Info: ','Info: ')+x.text)}">${ic('info')}</button>`:'')+`</div>`}
// the right side: a list, a tile or the search
function lstDetail(w){const box=w.querySelector('.lstdet'),d=LST.data,sm=lstSmart(LST.sel),q=LST.q.trim().toLowerCase(),l=lstList();
  box.hidden=!(l||sm||q);if(box.hidden){lstPop(w);return}
  const shown=NARROW(),back=shown?`<button type="button" class="b ld-back" data-k="back">‹ ${esc(t('Listen','Lists'))}</button>`:'';
  if(q||sm){   // across the lists: grouped by list (Geplant: by day), each entry with its own list
    const hits=lstAll().filter(e=>q?(e.x.text+' '+(e.x.note||'')).toLowerCase().includes(q):sm[4](e.x));
    const groups=new Map();
    for(const e of hits){const g=sm&&sm[0]==='@geplant'&&!q?(e.x.due<lstToday()?t('Überfällig','Overdue'):lstDay(e.x.due)):e.k;
      if(!groups.has(g))groups.set(g,[]);groups.get(g).push(e)}
    let keys=[...groups.keys()];if(sm&&sm[0]==='@geplant'&&!q)keys.sort((a,b)=>groups.get(a)[0].x.due.localeCompare(groups.get(b)[0].x.due));
    if(sm&&sm[0]==='@geplant'&&!q)for(const g of keys)groups.get(g).sort((a,b)=>(a.x.due+(a.x.at||'')).localeCompare(b.x.due+(b.x.at||'')));
    const byDay=sm&&sm[0]==='@geplant'&&!q;
    box.innerHTML=back+`<div class="lsthead ${q?'':'lc-'+sm[2]}"><div class="ld-mid"><h3>${esc(q?t('Suche','Search'):t(sm[3][0],sm[3][1]))}</h3></div><b class="lstbig">${hits.length}</b></div>`+
      (keys.map(g=>`<div class="ld-grp${byDay?'':' lc-'+esc(d.lists[g].color||'blau')}"><span>${esc(byDay?g:lstName(d.lists[g]))}</span><span>${groups.get(g).length}</span></div>`+
        groups.get(g).map(e=>lstItem(e.x,e.k,e.l,byDay)).join('')).join('')||
       `<div class="ld-empty mut">${esc(q?t('Nichts gefunden.','Nothing found.'):t('Keine Einträge.','No entries.'))}</div>`)+
      (LST.msg?`<div class="fh err">${esc(LST.msg)}</div>`:'');
    lstBindItems(box,w);lstPop(w);return}
  const qi0=box.querySelector('[data-k=q]'),keep=qi0?qi0.value:'',focus=qi0&&document.activeElement===qi0;
  const write=lstMay(l),mine=!l.shared;   // Mitschreiben: put on, tick off, sort; deleting: the owner
  let body='';
  if(l.shop){const groups=new Map();for(const x of l.items){const k=L==='en'?x.dept_en:x.dept;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(x)}
    const order=(d.depts||[]).map(g=>L==='en'?g[1]:g[0]);
    body=[...groups.keys()].sort((a,b)=>order.indexOf(a)-order.indexOf(b)).map(k=>`<div class="ld-grp"><span>${esc(k)}</span><span>${groups.get(k).length}</span></div>`+groups.get(k).map(x=>lstItem(x,LST.sel,l)).join('')).join('')}
  else body=l.items.map(x=>lstItem(x,LST.sel,l)).join('');
  const done=l.done||[],more=LST.allDone?done:done.slice(0,10);
  box.innerHTML=back+
    `<div class="lsthead lc-${esc(l.color||'blau')}"><div class="ld-mid"><h3>${esc(lstName(l))}</h3><small class="mut">${esc(lstSub(l))}</small></div><b class="lstbig">${l.items.length}</b></div>`+
    (LST.share&&mine?lstShareHtml(l):'')+
    (LST.form&&!LST.form.make?lstFormHtml():'')+
    (LST.ask?`<div class="ic-danger"><div class="ic-mid"><b>${esc(t('Liste löschen?','Delete the list?'))}</b><span>${esc(t('„','"')+l.name+t('“ und ihre ','" and its ')+(l.items.length+(l.done||[]).length)+t(' Einträge sind dann weg.',' entries are gone then.'))}</span></div><button class="b ic-red" type="button" data-k="dropyes">${esc(t('Löschen','Delete'))}</button><button class="b" type="button" data-k="dropno">${esc(t('Abbrechen','Cancel'))}</button></div>`:'')+
    (l.error?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+l.error)}</div>`:'')+
    (!write&&!l.target?`<div class="fh">${esc(t('Diese Liste ist mit dir nur zum Ansehen geteilt.','This list is shared with you to look at only.'))}</div>`:'')+
    body+
    // the empty row at the end: type, Enter, and the next one (several at once with commas)
    (write||l.target?`<div class="lstitem lstquick lc-${esc(l.color||'blau')}"><span class="lstck dash" aria-hidden="true"></span><span class="lstit"><input data-k="q" maxlength="400" autocomplete="off" enterkeyhint="next" aria-label="${esc(t('Neuer Eintrag','New entry'))}" placeholder="${esc(t('Neuer Eintrag','New entry'))}"><small>${esc(t('Enter: nächster Eintrag · mehrere mit Komma, z. B. „2 Milch, Brot“','Enter: next entry · several with commas, e.g. "2 milk, bread"'))}</small></span></div>`:'')+
    (LST.msg?`<div class="fh err">${esc(LST.msg)}</div>`:'')+
    (!body&&!write?`<div class="ld-empty mut">${esc(t('Noch nichts auf der Liste.','Nothing on the list yet.'))}</div>`:'')+
    (done.length?`<div class="lstdone"><span>${esc(done.length+t(' erledigt',' done'))}</span> · <button class="ic-lnk" type="button" data-k="showdone">${esc(LST.showDone?t('Ausblenden','Hide'):t('Einblenden','Show'))}</button></div>`:'')+
    (done.length&&LST.showDone?more.map(x=>
      `<div class="lstitem done"><span class="lstck on" aria-hidden="true">✓</span><span class="lstit"><b>${esc(x.text)}</b>${x.qty?` <span class="lstqty">${esc(x.qty)}</span>`:''}<small>${esc([x.by_name?t('eingetragen von ','put on by ')+x.by_name:'',t('abgehakt','ticked off')+(x.done_name?t(' von ',' by ')+x.done_name:'')+', '+lstWhen(x.done)].filter(Boolean).join(' · '))}</small></span>`+
      (write?`<button type="button" class="b" data-undo="${esc(x.id)}">${esc(t('Zurückholen','Bring back'))}</button>`:'')+
      (mine?`<button type="button" class="ic-ib lstdel" data-del="${esc(x.id)}" title="${esc(t('Löschen','Delete'))}" aria-label="${esc(t('Löschen: ','Delete: ')+x.text)}">${ic('x')}</button>`:'')+`</div>`).join('')+
      (done.length>more.length?`<div class="ld-more"><button class="ic-lnk" type="button" data-k="alldone">${esc(t('Weitere ','Show ')+(done.length-more.length)+t(' zeigen',' more'))}</button></div>`:''):'')+
    `<div class="fh">${esc(l.target?t('Diese Liste liegt in deiner CalDAV-Aufgabenliste; dort steht nicht, wer etwas eingetragen hat.','This list lives in your CalDAV task list; it does not keep who put something on.')
      :t('Erledigte Einträge bleiben 14 Tage hier, dann sind sie weg.','Ticked off entries stay here for 14 days, then they are gone.'))}</div>`;
  const qi=box.querySelector('[data-k=q]');if(qi){qi.value=keep;if(focus)qi.focus()}
  const add=async()=>{const v=qi.value.trim();if(!v)return;qi.value='';const r=await lstSend(lstPath(LST.sel),'POST',{text:v});
    const again=$('lstview')&&$('lstview').querySelector('[data-k=q]');if(!r&&again)again.value=v;if(again)again.focus()};
  if(qi)qi.onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();add()}};
  lstBindItems(box,w);
  box.querySelectorAll('[data-undo]').forEach(b=>b.onclick=()=>lstSend(lstPath(LST.sel,'/undo'),'POST',{ids:[b.dataset.undo]}));
  box.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>lstSend(lstPath(LST.sel,'/'+encodeURIComponent(b.dataset.del)),'DELETE'));
  const sd=box.querySelector('[data-k=showdone]');if(sd)sd.onclick=()=>{LST.showDone=!LST.showDone;lstDraw()};
  const ad=box.querySelector('[data-k=alldone]');if(ad)ad.onclick=()=>{LST.allDone=true;lstDraw()};
  // „⋯“: sharing a list of the profile's own (on the Spark), name, colour and symbol, deleting an own one (asked in
  // the page, never with confirm())
  const acts=[];
  if(mine&&(d.sharing||d.linking)&&!l.target)acts.push({label:t('Teilen …','Share …'),act:()=>{LST.ask=false;LST.form=null;LST.share=!LST.share;lstDraw()}});
  if(l.own)acts.push({label:t('Name, Farbe, Symbol','Name, colour, symbol'),act:()=>{LST.ask=false;LST.share=false;LST.form={make:false,name:l.name,icon:l.icon,color:l.color};lstDraw()}},
    {label:t('Liste löschen','Delete list'),danger:true,act:()=>{LST.form=null;LST.share=false;LST.ask=true;lstDraw()}});
  else if(mine)acts.push({label:t('Farbe','Colour'),act:()=>{LST.ask=false;LST.share=false;LST.form={make:false,fixed:true,color:l.color};lstDraw()}});
  if(acts.length)box.querySelector('.lsthead').appendChild(icMenu(acts));
  if(LST.share&&mine)lstShareBind(box,l);
  const dy=box.querySelector('[data-k=dropyes]');if(dy)dy.onclick=()=>{LST.ask=false;lstSend('/api/profile/listen/'+encodeURIComponent(LST.sel),'DELETE')};
  const dn=box.querySelector('[data-k=dropno]');if(dn)dn.onclick=()=>{LST.ask=false;lstDraw()};
  if(LST.form&&!LST.form.make)lstFormBind(box);
  lstPop(w)}
// ticking off, ⓘ, the back button and dragging, for a list and for the tiles alike
function lstBindItems(box,w){
  box.querySelectorAll('[data-tick]').forEach(b=>b.onclick=()=>{const r=b.closest('[data-l]');b.classList.add('on');if(LST.info&&LST.info.id===b.dataset.tick)LST.info=null;
    lstSend(lstPath(r.dataset.l,'/done'),'POST',{ids:[b.dataset.tick]})});
  box.querySelectorAll('[data-info]').forEach(b=>b.onclick=()=>{const r=b.closest('[data-l]'),same=LST.info&&LST.info.id===b.dataset.info;
    LST.info=same?null:{id:b.dataset.info,k:r.dataset.l,drawn:''};lstDraw()});
  const bk=box.querySelector('[data-k=back]');if(bk)bk.onclick=()=>{LST.sel='';LST.q='';LST.form=null;LST.ask=false;LST.info=null;lstDraw()};
  lstDragItems(box)}
// ---- dragging (only with a mouse; on a phone the info's „Liste“ moves an entry)
// an entry onto another entry of its list: the new order (PUT …/order); onto a list on the left: moved there
function lstDragItems(box){
  box.querySelectorAll('.lstitem[draggable=true]').forEach(r=>{
    r.ondragstart=e=>{LST.drag={kind:'item',id:r.dataset.id,k:r.dataset.l};e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',r.dataset.id);r.classList.add('drag')};
    r.ondragend=()=>{LST.drag=null;r.classList.remove('drag');document.querySelectorAll('.lstover').forEach(x=>x.classList.remove('lstover'))};
    r.ondragover=e=>{const g=LST.drag;if(!g||g.kind!=='item'||g.k!==r.dataset.l||g.id===r.dataset.id||lstSmart(LST.sel)||LST.q)return;e.preventDefault();r.classList.add('lstover')};
    r.ondragleave=()=>r.classList.remove('lstover');
    r.ondrop=e=>{const g=LST.drag;r.classList.remove('lstover');if(!g||g.kind!=='item'||g.k!==r.dataset.l||g.id===r.dataset.id)return;e.preventDefault();
      const l=LST.data.lists[g.k],ids=l.items.map(x=>x.id).filter(x=>x!==g.id),at=ids.indexOf(r.dataset.id);ids.splice(at<0?ids.length:at,0,g.id);
      l.items.sort((a,b)=>ids.indexOf(a.id)-ids.indexOf(b.id));lstDraw();   // at once, the answer follows
      lstSend(lstPath(g.k,'/order'),'PUT',{ids})}})}
// a list onto another list on the left: the new order of the lists (PUT /api/profile/listen/order); an entry onto a
// list: moved there (only from the owner's own list onto one the person may write)
function lstDragLists(list){
  list.querySelectorAll('.lstrow').forEach(r=>{
    r.ondragstart=e=>{LST.drag={kind:'list',k:r.dataset.l};e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',r.dataset.l);r.classList.add('drag')};
    r.ondragend=()=>{LST.drag=null;r.classList.remove('drag');document.querySelectorAll('.lstover').forEach(x=>x.classList.remove('lstover'))};
    const fits=()=>{const g=LST.drag,to=LST.data.lists[r.dataset.l];if(!g||g.k===r.dataset.l)return false;
      if(g.kind==='list')return true;const from=LST.data.lists[g.k];return !from.shared&&!from.target&&lstMay(to)};
    r.ondragover=e=>{if(!fits())return;e.preventDefault();r.classList.add('lstover')};
    r.ondragleave=()=>r.classList.remove('lstover');
    r.ondrop=e=>{r.classList.remove('lstover');if(!fits())return;e.preventDefault();const g=LST.drag;LST.drag=null;
      if(g.kind==='list'){const o=LST.data.order.filter(k=>k!==g.k);o.splice(o.indexOf(r.dataset.l),0,g.k);LST.data.order=o;lstDraw();
        lstSend('/api/profile/listen/order','PUT',{order:o})}
      else{if(LST.info&&LST.info.id===g.id)LST.info=null;lstSend(lstPath(g.k,'/'+encodeURIComponent(g.id)),'PUT',{to:r.dataset.l})}}})}
// ---- ⓘ: the info of one entry beside it (computer) or as a sheet from below (phone). Every field saves on its own
// (PUT …/<entry>), the card stays open and is drawn again only for another entry, so typing is never lost.
function lstFind(k,id){const l=LST.data&&LST.data.lists[k];return l&&l.items.find(x=>x.id===id)}
function lstPop(w){const pop=w.querySelector('.lstpop'),i=LST.info,x=i&&lstFind(i.k,i.id);
  if(!x){pop.hidden=true;pop.textContent='';if(i)LST.info=null;return}
  const l=LST.data.lists[i.k];
  if(i.drawn===i.k+'/'+i.id&&!pop.hidden){lstPopPlace(w,pop);return}
  i.drawn=i.k+'/'+i.id;pop.hidden=false;
  const d=LST.data,mine=!l.shared,seg=(v,lbl)=>`<button type="button" class="${x.prio===v?'on':''}" data-prio="${v}" aria-pressed="${x.prio===v}">${esc(lbl)}</button>`;
  const targets=d.order.filter(k=>k===i.k||(mine&&lstMay(d.lists[k])));
  const src=d.sources&&d.sources[x.src];
  pop.innerHTML=`<div class="lstpophead"><input data-p="text" maxlength="120" value="${esc(x.text+(x.qty?' '+x.qty:''))}" aria-label="${esc(t('Titel','Title'))}"><button type="button" class="b p" data-p="close">${esc(t('Fertig','Done'))}</button></div>`+
    `<textarea data-p="note" rows="2" data-zeilen="6" maxlength="400" placeholder="${esc(t('Notiz','Note'))}" aria-label="${esc(t('Notiz','Note'))}">${esc(x.note||'')}</textarea>`+
    `<div class="lstprow"><span>${esc(t('Datum','Date'))}</span><input type="date" data-p="due" value="${esc(x.due||'')}"></div>`+
    `<div class="lstprow"><span>${esc(t('Uhrzeit','Time'))}</span><input type="time" data-p="at" value="${esc(x.at||'')}"${x.due?'':' disabled'}></div>`+
    `<div class="lstprow"><span>${esc(t('Erinnern','Remind'))}<small>${esc(d.reminders?t('zur Uhrzeit als Erinnerung auf deinen Geräten','at the time as a reminder on your devices')
      :t('Braucht Funktionen → Timer und Erinnerungen','Needs Functions → Timers and reminders'))}</small></span>${tglIn('data-p="remind"'+(d.reminders&&x.due&&x.at?'':' disabled'),x.remind)}</div>`+
    `<div class="lstprow"><span>${esc(t('Markiert','Flagged'))}</span>${tglIn('data-p="flag"',x.flag)}</div>`+
    `<div class="lstprow"><span>${esc(t('Priorität','Priority'))}</span><div class="segc lstseg" role="radiogroup" aria-label="${esc(t('Priorität','Priority'))}">${seg(0,t('Keine','None'))+seg(1,'!')+seg(2,'!!')+seg(3,'!!!')}</div></div>`+
    (targets.length>1?`<div class="lstprow"><span>${esc(t('Liste','List'))}</span><select data-p="to" aria-label="${esc(t('Liste','List'))}">${targets.map(k=>`<option value="${esc(k)}"${k===i.k?' selected':''}>${esc(lstName(d.lists[k]))}</option>`).join('')}</select></div>`:'')+
    `<div class="lstpopfoot"><small>${esc([x.by_name?t('eingetragen von ','put on by ')+x.by_name:'',lstWhen(x.t),src?t(src[0],src[1]):''].filter(Boolean).join(' · '))}</small>`+
    (mine?`<button type="button" class="b ic-red" data-p="del">${esc(t('Löschen','Delete'))}</button>`:'')+`</div>`;
  const put=async body=>{const r=await lstSend(lstPath(i.k,'/'+encodeURIComponent(i.id)),'PUT',body);
    if(r&&body.to){LST.info=null;lstDraw()}else if(r){i.drawn='';lstDraw()}};
  const q=s=>pop.querySelector(`[data-p=${s}]`);
  q('close').onclick=()=>{LST.info=null;lstDraw()};
  q('text').onchange=()=>{if(q('text').value.trim())put({text:q('text').value})};
  q('text').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();q('text').blur()}};
  q('note').onchange=()=>put({note:q('note').value});
  q('due').onchange=()=>put({due:q('due').value||''});
  q('at').onchange=()=>put({at:q('at').value||''});
  q('remind').onchange=()=>put({remind:q('remind').checked});
  q('flag').onchange=()=>put({flag:q('flag').checked});
  pop.querySelectorAll('[data-prio]').forEach(b=>b.onclick=()=>put({prio:+b.dataset.prio}));
  if(q('to'))q('to').onchange=()=>put({to:q('to').value});
  if(q('del'))q('del').onclick=()=>{const k=i.k;LST.info=null;lstSend(lstPath(k,'/'+encodeURIComponent(i.id)),'DELETE')};
  pop.onkeydown=e=>{if(e.key==='Escape'){LST.info=null;lstDraw()}};
  lstPopPlace(w,pop)}
// beside its row on a computer, as a sheet from below on a phone (CSS); placed once per drawing
function lstPopPlace(w,pop){if(NARROW()){pop.style.top='';return}
  const row=w.querySelector(`.lstdet .lstitem[data-id="${CSS.escape(LST.info.id)}"]`);if(!row)return;
  const top=row.getBoundingClientRect().top-w.getBoundingClientRect().top;pop.style.top=Math.max(0,top-8)+'px'}
// the line under the name: how many are open, the newest entry and who put it on
function lstSub(l){const n=l.items.length,last=[...l.items].sort((a,b)=>(b.t||0)-(a.t||0))[0];
  return [l.shared?t('von ','from ')+l.shared.owner+', '+(l.shared.level==='add'?t('Mitschreiben','writing along'):t('nur sehen','see only')):'',
    n===1?t('1 offen','1 open'):n+t(' offen',' open'),last&&last.by_name?last.by_name+t(' hat „',' put "')+last.text+t('“ eingetragen, ','" on, ')+lstWhen(last.t):'',
    l.sent?l.sent+t(' ans iPhone übergeben',' handed to the iPhone'):''].filter(Boolean).join(' · ')}
// „Teilen“: each other profile Aus, Sehen or Mitschreiben (tasks.set_share); the own wish for a note when others put
// something on (preference list_note, features „listnote“)
function lstShareHtml(l){const d=LST.data,sh=l.shares||{},opt=(v,lbl,cur)=>`<option value="${v}"${v===cur?' selected':''}>${esc(lbl)}</option>`;
  return `<div class="lstform lstshare">`+(d.sharing?`<b>${esc(t('Teilen mit','Share with'))}</b>`+
    ((d.people||[]).map(p=>`<div class="setrow"><div class="lbl"><b>${esc(p.name)}</b></div><select data-share="${esc(p.id)}" aria-label="${esc(t('Freigabe für ','Sharing with ')+p.name)}">`+
      opt('',t('Aus','Off'),sh[p.id]||'')+opt('see',t('Sehen','See'),sh[p.id]||'')+opt('add',t('Mitschreiben','Write along'),sh[p.id]||'')+`</select></div>`).join('')
      ||`<div class="fh">${esc(t('Es gibt noch kein anderes Profil.','There is no other profile yet.'))}</div>`)+
    `<div class="fh">${esc(t('Mitschreiben heißt eintragen und abhaken; löschen und teilen kannst nur du.','Writing along means putting on and ticking off; only you delete and share.'))}</div>`+
    `<label class="lstnote"><input type="checkbox" data-k="note"${d.note?' checked':''}> ${esc(t('Hinweis, wenn andere etwas eintragen','A note when others put something on'))}</label>`:'')+
    (d.linking&&window.mitLinkHtml?mitLinkHtml(l):'')+   // Mitschreib-Link (mitschreib.js)
    `<div class="row"><button class="b" type="button" data-k="shareclose">${esc(t('Fertig','Done'))}</button></div></div>`}
function lstShareBind(box,l){
  box.querySelectorAll('[data-share]').forEach(s=>s.onchange=()=>lstSend('/api/profile/listen/'+encodeURIComponent(LST.sel)+'/share','PUT',{to:s.dataset.share,level:s.value}));
  const n=box.querySelector('[data-k=note]');if(n)n.onchange=async()=>{const {r}=await apiTry('/api/profile/settings',xjson('PUT',{'list_note':n.checked}));
    if(r.ok)LST.data.note=n.checked;else{n.checked=!n.checked;LST.msg=t('Nicht gespeichert.','Not saved.');lstDraw()}};
  const c=box.querySelector('[data-k=shareclose]');if(c)c.onclick=()=>{LST.share=false;lstDraw()};
  if(LST.data.linking&&window.mitLinkBind)mitLinkBind(box,l)}
