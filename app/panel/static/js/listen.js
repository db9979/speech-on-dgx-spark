// Listen (Dominik 2026-10-20 „1a 2a“, plan listen-teilen/plan.md Stufe 1): the shopping list, the to-do list and own
// lists as a page of its own in the menu, like Kalender and E-Mail. „Listen“ shows the lists on the left and the one
// tapped on the right (GET /api/profile/tasks, tasks.py): a field to add at once, the entries with who put them on,
// when and from where, the shop's departments, „Zuletzt erledigt“ with „Zurückholen“. „Einstellungen“ holds where the
// two fixed lists live and the iPhone shortcut (the box #taskbox, a page of Ich until Listen came). Entries and
// names are the person's words: only through esc().
const LST={data:null,sel:'',seq:0,busy:false,err:'',msg:'',form:null,ask:false,allDone:false};
// the menu entry only for a signed-in profile that may use lists (start.js, like Kalender)
window.lstStart=who=>{const on=!!(who&&who.profile&&who.tasks);document.querySelectorAll('nav button[data-s=listen]').forEach(b=>b.hidden=!on)};
const lstWhen=s=>{if(!s)return '';const d=new Date(s*1000),n=new Date(),y=new Date(n.getFullYear(),n.getMonth(),n.getDate()-1),
    tm=d.toLocaleTimeString(kalLoc(),{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===n.toDateString()?t('heute ','today ')+tm:d.toDateString()===y.toDateString()?t('gestern ','yesterday ')+tm
    :n-d<6*864e5?d.toLocaleDateString(kalLoc(),{weekday:'short'})+' '+tm:d.toLocaleDateString(kalLoc(),{day:'numeric',month:'short'})};
// „Dominik · heute 08:15 · per Stimme“: who, when, from where (the source is a fixed word, tasks.SOURCES)
function lstWho(x){const d=LST.data,src=d&&d.sources&&d.sources[x.src];
  return [x.by_name&&PROFILE&&x.by_name===PROFILE.name?t('ich','me'):x.by_name,lstWhen(x.t),src?t(src[0],src[1]):''].filter(Boolean).join(' · ')}
const lstName=l=>L==='en'?l.name_en:l.name;
const lstList=()=>LST.data&&LST.data.lists[LST.sel];
async function lstLoad(){if(!PROFILE||!TASK_ON)return;const seq=++LST.seq;LST.busy=true;lstDraw();
  const {r,d}=await apiTry('/api/profile/tasks');if(seq!==LST.seq)return;
  if(r.ok){LST.data=d;LST.err='';if(!d.lists[LST.sel]&&!NARROW())LST.sel=d.order[0]||''}else LST.err=errSay(r.status,d.detail,'');
  LST.busy=false;lstDraw()}
// every change answers with the whole state (tasks.get_lists): drawn at once, no second request
async function lstSend(path,method,body){const {r,d}=await apiTry(path,method==='DELETE'?{method}:xjson(method,body));
  if(!r.ok){LST.msg=errSay(r.status,d.detail,'');lstDraw();return null}
  LST.data=d;LST.msg='';if(!d.lists[LST.sel])LST.sel=NARROW()?'':d.order[0]||'';lstDraw();return d}
const LST_BOX=$('taskbox');   // the tab „Einstellungen“ shows it; kept in the section between visits (see POST_BOXES)
function lstOpen(){if(!PROFILE)return;const root=$('lstroot');if(LST_BOX){LST_BOX.hidden=true;$('listen').appendChild(LST_BOX)}root.textContent='';
  root.appendChild(icTabs('listen',[{k:'show',label:OWN_PAGES.taskbox[2],body:lstBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('taskbox');b.hidden=false;lzb(b,showTasks,{auth:true}).catch(()=>{});return b}}]));
  lstLoad()}
function lstBody(){const w=document.createElement('div');w.className='ld-box ld-frame lst';w.id='lstview';lstPaint(w);return w}
function lstDraw(){const w=$('lstview');if(w)lstPaint(w)}
function lstPaint(w){const d=LST.data;w.classList.toggle('ld-sel',!!LST.sel);
  if(!w.querySelector('.ld-split')){w.innerHTML=`<div class="lstwarn"></div><div class="ld-split"><div class="ld-list"></div><div class="ld-detail lstdet" hidden></div></div>`}
  w.querySelector('.lstwarn').innerHTML=LST.err?`<div class="note warn">${esc(t('Die Listen kamen nicht an: ','The lists did not arrive: ')+LST.err)}</div>`:'';
  const list=w.querySelector('.ld-list');list.classList.toggle('busy',LST.busy&&!d);
  if(!d){list.innerHTML=LST.busy?`<div class="ld-empty mut">${esc(t('Lade die Listen …','Loading the lists …'))}</div>`:'';return}
  const row=k=>{const l=d.lists[k],n=l.items.length,sub=l.target?t('in ','in ')+l.target.name:l.error?t('nicht erreichbar','not reachable')
      :n?l.items.slice(0,3).map(x=>x.text).join(', ')+(n>3?' …':''):t('leer','empty');
    return `<div class="ld-row${k===LST.sel?' on':''}" role="button" tabindex="0" data-l="${esc(k)}"><span class="ld-ico lstico" aria-hidden="true">${esc(l.icon)}</span>`+
      `<span class="ld-mid"><b>${esc(lstName(l))}</b><small>${esc(sub)}</small></span><span class="ld-right"><b class="lstcnt">${n}</b></span></div>`};
  const own=d.order.filter(k=>d.lists[k].own);
  list.innerHTML=`<div class="ld-grp"><span>${esc(t('Meine Listen','My lists'))}</span><span>${d.order.length}</span></div>`+
    d.order.filter(k=>!d.lists[k].own).map(row).join('')+own.map(row).join('')+
    (own.length<d.max_lists?`<div class="ld-more"><button class="b" type="button" data-k="new">${esc(t('+ Neue Liste','+ New list'))}</button></div>`:'')+
    (LST.form&&LST.form.make?lstFormHtml():'');
  list.querySelectorAll('[data-l]').forEach(r=>{const go=()=>{LST.sel=r.dataset.l;LST.ask=false;LST.form=null;LST.msg='';LST.allDone=false;lstDraw()};
    r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  const nb=list.querySelector('[data-k=new]');if(nb)nb.onclick=()=>{LST.form={make:true,name:'',icon:d.icons[0]};lstDraw();const i=list.querySelector('[data-f=name]');if(i)i.focus()};
  if(LST.form&&LST.form.make)lstFormBind(list);
  lstDetail(w)}
// the card for a new list or a new name: a name and a symbol from the fixed choice (tasks.ICONS)
function lstFormHtml(){const f=LST.form,d=LST.data;
  return `<div class="lstform"><label>${esc(t('Name der Liste','Name of the list'))}</label><input data-f="name" maxlength="40" autocomplete="off" value="${esc(f.name)}" placeholder="${esc(t('z. B. Baumarkt','e.g. Hardware store'))}">`+
    `<div class="lsticons" role="radiogroup" aria-label="${esc(t('Symbol','Symbol'))}">${d.icons.map(i=>`<button type="button" class="ld-chip${i===f.icon?' on':''}" data-i="${esc(i)}" aria-pressed="${i===f.icon}">${esc(i)}</button>`).join('')}</div>`+
    `<div class="row"><button class="b p" type="button" data-f="save">${esc(f.make?t('Anlegen','Create'):t('Speichern','Save'))}</button><button class="b" type="button" data-f="cancel">${esc(t('Abbrechen','Cancel'))}</button></div></div>`}
function lstFormBind(box){const f=LST.form,i=box.querySelector('[data-f=name]');
  i.oninput=()=>{f.name=i.value};i.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();box.querySelector('[data-f=save]').click()}};
  box.querySelectorAll('[data-i]').forEach(b=>b.onclick=()=>{f.icon=b.dataset.i;box.querySelectorAll('[data-i]').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',String(on))})});
  box.querySelector('[data-f=cancel]').onclick=()=>{LST.form=null;lstDraw()};
  box.querySelector('[data-f=save]').onclick=async()=>{if(!f.name.trim())return;
    const d=f.make?await lstSend('/api/profile/listen','POST',{name:f.name,icon:f.icon}):await lstSend('/api/profile/listen/'+encodeURIComponent(LST.sel),'PUT',{name:f.name,icon:f.icon});
    if(d){if(f.make&&d.made)LST.sel=d.made;LST.form=null;lstDraw()}}}
// the list tapped: add at once, the entries (by department on a shopping list), the ones ticked off lately
function lstDetail(w){const box=w.querySelector('.lstdet'),l=lstList();box.hidden=!l;if(!l)return;
  const shown=NARROW(),q=box.querySelector('[data-k=q]'),keep=q?q.value:'',focus=q&&document.activeElement===q;
  const who=x=>`<small>${esc(lstWho(x))}</small>`;
  const item=x=>`<div class="lstitem"><button type="button" class="lstck" data-tick="${esc(x.id)}" aria-label="${esc(t('Abhaken: ','Tick off: ')+x.text)}"></button>`+
    `<span class="lstit"><b>${esc(x.text)}</b>${x.qty?` <span class="lstqty">${esc(x.qty)}</span>`:''}${who(x)}</span>`+
    `<button type="button" class="ic-ib lstdel" data-del="${esc(x.id)}" title="${esc(t('Löschen','Delete'))}" aria-label="${esc(t('Löschen: ','Delete: ')+x.text)}">✕</button></div>`;
  let body='';
  if(l.shop){const groups=new Map();for(const x of l.items){const k=L==='en'?x.dept_en:x.dept;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(x)}
    const order=(LST.data.depts||[]).map(g=>L==='en'?g[1]:g[0]);
    body=[...groups.keys()].sort((a,b)=>order.indexOf(a)-order.indexOf(b)).map(k=>`<div class="ld-grp"><span>${esc(k)}</span><span>${groups.get(k).length}</span></div>`+groups.get(k).map(item).join('')).join('')}
  else body=l.items.map(item).join('');
  const done=l.done||[],more=LST.allDone?done:done.slice(0,10);
  box.innerHTML=(shown?`<button type="button" class="b ld-back" data-k="back">‹ ${esc(t('Listen','Lists'))}</button>`:'')+
    `<div class="lsthead"><span class="ld-ico lstico" aria-hidden="true">${esc(l.icon)}</span><div class="ld-mid"><h3>${esc(lstName(l))}</h3><small class="mut">${esc(lstSub(l))}</small></div>`+
+`</div>`+
    (LST.form&&!LST.form.make?lstFormHtml():'')+
    (LST.ask?`<div class="ic-danger"><div class="ic-mid"><b>${esc(t('Liste löschen?','Delete the list?'))}</b><span>${esc(t('„','"')+l.name+t('“ und ihre ','" and its ')+(l.items.length+(l.done||[]).length)+t(' Einträge sind dann weg.',' entries are gone then.'))}</span></div><button class="b ic-red" type="button" data-k="dropyes">${esc(t('Löschen','Delete'))}</button><button class="b" type="button" data-k="dropno">${esc(t('Abbrechen','Cancel'))}</button></div>`:'')+
    (l.error?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+l.error)}</div>`:'')+
    `<div class="lstquick"><input data-k="q" maxlength="400" autocomplete="off" enterkeyhint="done" aria-label="${esc(t('Eintrag hinzufügen','Add an entry'))}" placeholder="${esc(t('Eintrag hinzufügen … (mehrere mit Komma, z. B. „2 Milch, Brot“)','Add an entry … (several with commas, e.g. "2 milk, bread")'))}"><button class="b p" type="button" data-k="add">${esc(t('Hinzufügen','Add'))}</button></div>`+
    (LST.msg?`<div class="fh err">${esc(LST.msg)}</div>`:'')+
    (body||`<div class="ld-empty mut">${esc(t('Noch nichts auf der Liste. Sag auch „Setz Milch auf die Einkaufsliste“.','Nothing on the list yet. You can also say "Put milk on the shopping list".'))}</div>`)+
    (done.length?`<div class="ld-grp"><span>${esc(t('Zuletzt erledigt','Done lately'))}</span><span>${done.length}</span></div>`+more.map(x=>
      `<div class="lstitem done"><span class="lstck on" aria-hidden="true">✓</span><span class="lstit"><b>${esc(x.text)}</b>${x.qty?` <span class="lstqty">${esc(x.qty)}</span>`:''}<small>${esc([x.by_name?t('eingetragen von ','put on by ')+x.by_name:'',t('abgehakt','ticked off')+(x.done_name?t(' von ',' by ')+x.done_name:'')+', '+lstWhen(x.done)].filter(Boolean).join(' · '))}</small></span>`+
      `<button type="button" class="b" data-undo="${esc(x.id)}">${esc(t('Zurückholen','Bring back'))}</button></div>`).join('')+
      (done.length>more.length?`<div class="ld-more"><button class="lnk" type="button" data-k="alldone">${esc(t('Weitere ','Show ')+(done.length-more.length)+t(' zeigen',' more'))}</button></div>`:''):'')+
    `<div class="fh">${esc(l.target?t('Diese Liste liegt in deiner CalDAV-Aufgabenliste; dort steht nicht, wer etwas eingetragen hat.','This list lives in your CalDAV task list; it does not keep who put something on.')
      :t('Erledigte Einträge bleiben 14 Tage hier, dann sind sie weg.','Ticked off entries stay here for 14 days, then they are gone.'))}</div>`;
  const qi=box.querySelector('[data-k=q]');qi.value=keep;if(focus)qi.focus();
  const add=async()=>{const v=qi.value.trim();if(!v)return;qi.value='';const d=await lstSend('/api/profile/tasks/'+encodeURIComponent(LST.sel),'POST',{text:v});
    const again=$('lstview')&&$('lstview').querySelector('[data-k=q]');if(!d&&again)again.value=v;if(again)again.focus()};
  box.querySelector('[data-k=add]').onclick=add;qi.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add()}};
  box.querySelectorAll('[data-tick]').forEach(b=>b.onclick=()=>{b.classList.add('on');lstSend('/api/profile/tasks/'+encodeURIComponent(LST.sel)+'/done','POST',{ids:[b.dataset.tick]})});
  box.querySelectorAll('[data-undo]').forEach(b=>b.onclick=()=>lstSend('/api/profile/tasks/'+encodeURIComponent(LST.sel)+'/undo','POST',{ids:[b.dataset.undo]}));
  box.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>lstSend('/api/profile/tasks/'+encodeURIComponent(LST.sel)+'/'+encodeURIComponent(b.dataset.del),'DELETE'));
  const ad=box.querySelector('[data-k=alldone]');if(ad)ad.onclick=()=>{LST.allDone=true;lstDraw()};
  const bk=box.querySelector('[data-k=back]');if(bk)bk.onclick=()=>{LST.sel='';LST.form=null;LST.ask=false;lstDraw()};
  // an own list: „⋯“ with a new name or symbol and deleting it (asked in the page, never with confirm())
  if(l.own)box.querySelector('.lsthead').appendChild(icMenu([{label:t('Umbenennen','Rename'),act:()=>{LST.ask=false;LST.form={make:false,name:l.name,icon:l.icon};lstDraw()}},
    {label:t('Liste löschen','Delete list'),danger:true,act:()=>{LST.form=null;LST.ask=true;lstDraw()}}]));
  const dy=box.querySelector('[data-k=dropyes]');if(dy)dy.onclick=()=>{LST.ask=false;lstSend('/api/profile/listen/'+encodeURIComponent(LST.sel),'DELETE')};
  const dn=box.querySelector('[data-k=dropno]');if(dn)dn.onclick=()=>{LST.ask=false;lstDraw()};
  if(LST.form&&!LST.form.make)lstFormBind(box)}
// the line under the name: how many are open, the newest entry and who put it on
function lstSub(l){const n=l.items.length,last=[...l.items].sort((a,b)=>(b.t||0)-(a.t||0))[0];
  return [n===1?t('1 offen','1 open'):n+t(' offen',' open'),last&&last.by_name?last.by_name+t(' hat „',' put "')+last.text+t('“ eingetragen, ','" on, ')+lstWhen(last.t):'',
    l.sent?l.sent+t(' ans iPhone übergeben',' handed to the iPhone'):''].filter(Boolean).join(' · ')}
