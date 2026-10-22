// IT-Krisenspiel (krisenspiel.py, plan krisenspiel/plan.md, Paket 1): a page of its own in the menu. „Spiel“ is the
// crisis dashboard: the values on top, the systems with their state, the chronicle and the moves the panel offers;
// „Neues Spiel“ picks scenario, level and seed; „Inspector“ shows every step of a move (input, fixed rule, rolls from
// the seed, narrator); „Bisherige Spiele“ the results, achievements and „Meine Daten löschen“. Every value comes from
// the panel; texts from the scenarios and the narrator are only ever text (esc), never markup.
const KS={data:null,msg:'',err:false,busy:false,seq:0,turn:-1,hist:-1,con:null,focus:false,at:0,guide:null,ticked:0};
const KS_CHRON=6;   // chronicle entries shown above the console, the older ones fold away
let KS_ON=false;
const ksP=p=>Array.isArray(p)?p[L==='en'?1:0]:String(p??'');
// the grade's colour (app.css), named here in full so every class is found
const KSNOTE={A:'nA',B:'nB',E:'nE',F:'nF'};
const ksEur=v=>Number(v||0).toLocaleString(L==='en'?'en-GB':'de-DE')+' €';
const ksWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const KSSTAT={Online:['läuft','running','ok'],Degraded:['gestört','degraded','warn'],Critical:['kritisch','critical','bad'],
  Offline:['aus','off','bad'],Isolated:['isoliert','isolated','iso']};
const KSART={start:['Lage','Situation'],zug:['Zug','Move'],folge:['Folge','Consequence'],neben:['Nebenschauplatz','Side issue'],ende:['Ende','End']};
const KSSTEP={eingabe:['Eingabe','Input'],regel:['Feste Regel','Fixed rule'],zufall:['Zufall aus dem Seed','Chance from the seed'],
  modell:['Sprachmodell','Language model'],antwort:['Antwort','Answer'],ende:['Ende','End']};
// the menu entry only for a signed-in profile the admin released the game for (start.js, like the Wissensbuch)
window.ksStart=who=>{KS_ON=!!(who&&who.profile&&who.krisenspiel);
  document.querySelectorAll('nav button[data-s=spiel]').forEach(b=>b.hidden=!KS_ON)};
function ksOpen(){if(!PROFILE)return;const root=$('ksroot'),box=$('ksbox');if(box){box.hidden=true;$('spiel').appendChild(box)}root.textContent='';
  const tabs=OWN_PAGES.ksbox[3],body=k=>()=>{const w=document.createElement('div');w.className='ks';w.id='ksview';w.dataset.tab=k;ksPaint(w);return w};
  root.appendChild(icTabs('spiel',[{k:'spiel',label:OWN_PAGES.ksbox[2],body:body('spiel')}].concat(tabs.map(([k,l])=>({k,label:l,body:body(k)})))));
  ksLoad()}
window.ksOpen=ksOpen;
async function ksLoad(){if(!KS_ON)return;const seq=++KS.seq;const {r,d}=await apiTry('/api/profile/krisenspiel');if(seq!==KS.seq)return;
  if(r.ok){KS.data=d;KS.at=Date.now();KS.err=false;KS.msg=''}else{KS.msg=errSay(r.status,d.detail,'');KS.err=true}ksDraw()}
function ksDraw(){const w=$('ksview');if(w)ksPaint(w)}
function ksSay(x,err){KS.msg=String(x||'').slice(0,300);KS.err=!!err;const m=document.querySelector('#ksview .ksmsg');if(m){m.className='ksmsg '+(err?'err':'mut');m.textContent=KS.msg}}
async function ksSend(p,method,b){if(KS.busy)return null;KS.busy=true;document.querySelectorAll('#ksview button').forEach(x=>x.disabled=true);
  const o={method};if(b)Object.assign(o,{headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({lang:L==='en'?'en':'de'},b))});
  const {r,d}=await apiTry(p,o);KS.busy=false;KS.seq++;   // a read that started before this answer is older: dropped
  if(!r.ok){if(r.status===409)await ksLoad();ksDraw();ksSay(r.status===409?t('Das Spiel war schon einen Zug weiter; jetzt ist es aktuell.','The game was a move further already; it is current now.'):d.detail,true);return null}
  if(d&&d.on){KS.data=d;KS.at=Date.now()}ksDraw();return d}
function ksPaint(w){const D=KS.data,tab=w.dataset.tab;
  if(!D){w.innerHTML=`<div class="ld-empty mut">${esc(KS.err?KS.msg:t('Lade das Krisenspiel …','Loading the crisis game …'))}</div>`;return}
  if(tab==='anleitung'){ksGuide(w);return}
  w.innerHTML=(tab==='neu'?ksNew(D):tab==='inspector'?ksInspector(D):tab==='bisher'?ksPast(D):ksGame(D))+`<div class="ksmsg ${KS.err?'err':'mut'}" role="status">${esc(KS.msg)}</div>`;
  const con=w.querySelector('.ks-con');if(con)con.scrollTop=con.scrollHeight;
  const det=w.querySelector('.ks-condet');if(det)det.ontoggle=()=>{KS.con=det.open};
  const inp=w.querySelector('.ks-in');if(inp){if(KS.focus)inp.focus({preventScroll:true});
    inp.onkeydown=e=>{const h=KS.data.spiel.konsole.verlauf;
      if(e.key==='Enter'){e.preventDefault();ksType(inp)}
      else if(e.key==='Tab'){e.preventDefault();ksTab(inp)}
      else if(e.key==='ArrowUp'&&h.length){e.preventDefault();KS.hist=KS.hist<0?h.length-1:Math.max(0,KS.hist-1);inp.value=h[KS.hist]}
      else if(e.key==='ArrowDown'&&KS.hist>=0){e.preventDefault();KS.hist++;inp.value=KS.hist<h.length?h[KS.hist]:'';if(KS.hist>=h.length)KS.hist=-1}}}}
function ksBar(label,val,max,shown,bad,cls){const pc=Math.max(0,Math.min(100,Math.round(100*val/(max||1))));
  return `<div class="ks-met${bad?' bad':''}${cls?' '+cls:''}"><span>${esc(label)}</span><b>${esc(shown)}</b><i><em style="width:${pc}%"></em></i></div>`}
// „Uhr läuft“ (krisenspiel.uhr_ticken): the minutes the clock took since the last answer count down here, the panel
// counts them on the next request with the same rule; the open, visible page asks every u.poll seconds
function ksLeft(g){const u=g.uhr;if(!u||g.ende)return g.m.zeit;
  const sec=u.rest+(u.pause?0:Math.min(u.seit+(Date.now()-KS.at)/1000,u.luecke));
  return Math.max(0,g.m.zeit-u.offen-Math.floor(sec/u.s))}
async function ksTick(){const g=KS.data&&KS.data.spiel,w=$('ksview');
  if(!g||!g.uhr||g.ende||g.uhr.pause||!w||w.offsetParent===null||document.visibilityState!=='visible'||KS.busy)return;
  const el=w.querySelector('.ks-time');if(el){const left=ksLeft(g);el.querySelector('b').textContent=t(`${left} min`,`${left} min`);
    el.querySelector('em').style.width=Math.max(0,Math.min(100,Math.round(100*left/(g.m.zeit_start||1))))+'%';el.classList.toggle('bad',left*4<g.m.zeit_start)}
  if(Date.now()-KS.ticked<g.uhr.poll*1000||Date.now()-KS.at<g.uhr.poll*1000)return;KS.ticked=Date.now();
  const seq=KS.seq,{r,d}=await apiTry('/api/profile/krisenspiel/uhr',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aktion:'tick',lang:L==='en'?'en':'de'})});
  if(seq!==KS.seq||!r.ok||!d||!d.on)return;const turn=g.zug;KS.data=d;KS.at=Date.now();
  if(!d.spiel||d.spiel.zug!==turn||d.spiel.ende)ksDraw()}
setInterval(ksTick,1000);
function ksGame(D){const g=D.spiel;
  if(!g)return `<div class="ld-empty mut">${esc(t('Noch kein Spiel. Unter „Neues Spiel“ wählst du ein Szenario.','No game yet. Pick a scenario under "New game".'))}</div><div class="row"><button type="button" class="b p" data-kstab="neu">${esc(t('Neues Spiel','New game'))}</button></div>`;
  const m=g.m,stufe=(D.stufen.find(s=>s.id===g.stufe)||{name:[g.stufe,g.stufe]}).name;
  const head0=`<div class="ks-head"><div><h3>${esc(ksP(g.titel))}</h3><div class="mut">${esc(ksP(stufe))}${g.modus==='konsole'?esc(t(' · nur Konsole',' · console only')):''} · Seed ${esc(String(g.seed))} · ${esc(t(`Zug ${g.zug} · Minute ${g.min}`,`Move ${g.zug} · minute ${g.min}`))}</div></div>
    ${g.ende?'':`<button type="button" class="b" data-ksgive="1">${esc(t('Aufgeben','Give up'))}</button>`}</div>`;
  const left=ksLeft(g),u=g.uhr;
  const clock=u&&!g.ende?`<div class="ks-uhr"><span class="mut">${esc(u.pause?t('Uhr angehalten','Clock paused'):t(`Uhr läuft: ${u.s} s = 1 min`,`Clock running: ${u.s} s = 1 min`))}</span>${u.pause_ok?`<button type="button" class="b" data-ksuhr="${u.pause?'weiter':'pause'}">${esc(u.pause?t('Weiter','Go on'):t('Pause','Pause'))}</button>`:''}</div>`:'';
  const mets=`<div class="ks-mets">${ksBar(t('Zeit','Time'),left,m.zeit_start,t(`${left} min`,`${left} min`),left*4<m.zeit_start,'ks-time')}
    ${ksBar(t('Stress','Stress'),m.stress,100,m.stress+' %',m.stress>=75)}${ksBar(t('Vertrauen','Trust'),m.vertrauen,100,m.vertrauen+' %',m.vertrauen<30)}
    ${ksBar(t('Moral','Morale'),m.moral,100,m.moral+' %',m.moral<30)}${ksBar(t('Budget','Budget'),m.budget,m.budget_start,ksEur(m.budget),m.budget*5<m.budget_start)}
    <div class="ks-met dmg"><span>${esc(t('Schaden','Damage'))}</span><b>${esc(ksEur(m.kosten))}</b></div></div>`;
  const head=head0+clock;
  const assets=`<div class="ks-assets">${g.assets.map(a=>{const s=KSSTAT[a.status]||[a.status,a.status,''];
    return `<div class="ks-asset ${s[2]}"><b>${esc(a.name)}</b><small class="mut">${esc(ksP(a.typ))}</small><span class="pill ${s[2]}">${esc(t(s[0],s[1]))}</span><small>${esc(ksP(a.details))}</small></div>`}).join('')}</div>`;
  const ev=c=>`<div class="ks-ev ${esc(c.art)}"><small class="mut">${esc(t(...(KSART[c.art]||[c.art,c.art])))} · ${esc(t('Minute ','minute '))}${c.min}</small><p>${esc(c.erzaehlt&&c.lang===(L==='en'?'en':'de')?c.erzaehlt:ksP(c.text))}</p>${c.erzaehlt&&c.lang===(L==='en'?'en':'de')?`<details><summary>${esc(t('Feste Fakten','Fixed facts'))}</summary><small>${esc(ksP(c.text))}</small></details>`:''}</div>`;
  const all=g.chronik.slice().reverse(),old=all.slice(KS_CHRON);
  const chron=`<div class="ks-chron" aria-live="polite">${all.slice(0,KS_CHRON).map(ev).join('')}${old.length?`<details class="ks-old"><summary>${esc(t(`Ältere (${old.length})`,`Older (${old.length})`))}</summary>${old.map(ev).join('')}</details>`:''}</div>`;
  const cost=a=>Object.entries(a.kosten).map(([k,v])=>k==='budget'?ksEur(v):k==='zeit'?v+' min':(v>0?'+':'')+v+' '+t({stress:'Stress',vertrauen:'Vertrauen',moral:'Moral'}[k]||k,{stress:'stress',vertrauen:'trust',moral:'morale'}[k]||k)).join(' · ');
  const acts=g.ende?ksEnd(D,g):g.modus==='konsole'?`<div class="ks-only mut">${esc(t('Nur Konsole: jeder Zug wird getippt. „help“ zeigt die Befehle, „hosts“ die Rechner.','Console only: every move is typed. "help" shows the commands, "hosts" the machines.'))}</div>`:`<h4>${esc(t('Deine Züge','Your moves'))}</h4><div class="ks-acts">${g.aktionen.map(a=>`<button type="button" class="b ks-act" data-ksmove="${esc(a.id)}"${a.frei?'':' disabled'} title="${esc(a.frei?'':ksP(a.warum))}"><b>${esc(ksP(a.label))}</b><small>${esc(cost(a))}</small></button>`).join('')}</div>`;
  return head+mets+`<div class="ks-grid"><div>${assets}${acts}</div><div><h4>${esc(t('Chronik','Chronicle'))}</h4>${chron}${ksCon(g)}</div></div>`}
// the simulated console (krisenkonsole.py): nothing typed here ever runs; the Spark cuts each line by fixed rules and
// answers from the game. A phone shows it folded unless the game is console only; ↑/↓ the last lines, Tab completes.
const KSCON={err:'kc-err',zug:'kc-zug'};   // the kinds of console lines and their style
function ksCon(g){const k=g.konsole;if(!k)return '';
  const open=KS.con!==null?KS.con:(g.modus==='konsole'||!matchMedia('(max-width:700px)').matches);
  const rows=k.zeilen.map(z=>z.k==='in'?`<div class="kc-in"><span class="kc-p">admin@${esc(z.h||'')}:~$</span> ${esc(z.s)}</div>`:`<div class="${KSCON[z.k]||'kc-out'}">${esc(z.s)}</div>`).join('');
  return `<details class="ks-condet"${open?' open':''}><summary>${esc(t('Konsole','Console'))} <small class="mut">${esc(k.host)}${k.lesen?esc(t(` · ${k.lesen} min gelesen`,` · ${k.lesen} min read`)):''}</small></summary>
    <div class="ks-con" role="log">${rows||`<div class="kc-out mut">${esc(t('Tippe help für die Befehle. Nichts hier läuft wirklich.','Type help for the commands. Nothing here really runs.'))}</div>`}</div>
    ${g.ende?'':`<div class="ks-cline"><span class="kc-p">admin@${esc(k.host)}:~$</span><input class="ks-in" type="text" maxlength="200" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="${esc(t('Befehl','Command'))}"></div>`}</details>`}
async function ksType(inp){const z=inp.value;if(!z.trim()||KS.busy||!KS.data||!KS.data.spiel)return;KS.hist=-1;KS.focus=true;
  inp.value='';await ksSend('/api/profile/krisenspiel/konsole','POST',{zeile:z,zug:KS.data.spiel.zug})}
function ksTab(inp){const k=KS.data.spiel.konsole,v=inp.value,parts=v.split(' '),last=parts[parts.length-1].toLowerCase();
  const pool=parts.length===1?k.befehle:k.hosts,hit=pool.filter(x=>x.startsWith(last));
  if(hit.length===1){parts[parts.length-1]=hit[0];inp.value=parts.join(' ')+' '}
  else if(hit.length>1)ksSay(hit.join('  '))}
function ksEnd(D,g){const e=g.ende,names=Object.fromEntries(D.erfolge.map(x=>[x.id,x.name]));
  return `<div class="ks-end"><div class="ks-note ${KSNOTE[e.note]||''}">${esc(e.note)}</div><div><h4>${esc(t(`${e.punkte} von 100 Punkten`,`${e.punkte} of 100 points`))}</h4>
    <ul class="facts small">${e.gruende.map(x=>`<li><span>${esc(ksP(x))}</span></li>`).join('')}</ul>
    ${(e.erfolge||[]).length?`<div>${e.erfolge.map(k=>`<span class="pill ok">${esc(ksP(names[k]||[k,k]))}</span>`).join(' ')}</div>`:''}
    <div class="row"><button type="button" class="b p" data-ksagain="${esc(g.szenario)}" data-ksstufe="${esc(g.stufe)}" data-ksseed="${esc(String(g.seed))}" data-ksmodus="${esc(g.modus||'knoepfe')}" data-ksclock="${g.uhr?1:''}">${esc(t('Nochmal mit diesem Seed','Again with this seed'))}</button><button type="button" class="b" data-kstab="neu">${esc(t('Neues Spiel','New game'))}</button></div></div></div>`}
function ksNew(D){const run=D.spiel&&!D.spiel.ende;
  return `<h3>${esc(t('Neues Spiel','New game'))}</h3>${run?`<div class="mut">${esc(t('Ein neues Spiel ersetzt das laufende.','A new game replaces the running one.'))}</div>`:''}
    <div class="ks-pick">${D.szenarien.map((s,i)=>`<label class="ks-sz"><input type="radio" name="kssz" value="${esc(s.id)}"${i?'':' checked'}><b>${esc(ksP(s.titel))}</b><small>${esc(ksP(s.kurz))}</small><small class="mut">${esc(t(`${s.systeme} Systeme`,`${s.systeme} systems`))}${D.stats.beste[s.id]?esc(t(` · bisher bestes Ergebnis ${D.stats.beste[s.id]} Punkte`,` · best so far ${D.stats.beste[s.id]} points`)):''}</small></label>`).join('')}<label class="ks-sz"><input type="radio" name="kssz" value="zufall"><b>${esc(t('🎲 Überraschung','🎲 Surprise'))}</b><small>${esc(t('Eines der Szenarien per Zufall: Was passiert, siehst du erst im Spiel.','One of the scenarios by chance: you see what happens only in the game.'))}</small></label></div>
    <div class="row"><label>${esc(t('Stufe','Level'))} <select class="ksstufe">${D.stufen.map(s=>`<option value="${esc(s.id)}"${s.id==='normal'?' selected':''}>${esc(ksP(s.name))} (${s.zeit} min)</option>`).join('')}</select></label>
    <label>Seed <input class="ksseed" type="number" min="0" max="999999" inputmode="numeric" placeholder="${esc(t('zufällig','random'))}"></label></div>
    <div class="row"><label>${esc(t('Spielweise','How to play'))} <select class="ksmodus"><option value="knoepfe">${esc(t('Knöpfe und Konsole','Buttons and console'))}</option><option value="konsole">${esc(t('Nur Konsole (+5 Punkte beim Sieg)','Console only (+5 points when won)'))}</option></select></label>
    <label class="chk"><input type="checkbox" class="ksuhr"> ${esc(t('Uhr läuft (10 Sekunden = 1 Spielminute, +5 Punkte beim Sieg)','Clock running (10 seconds = 1 game minute, +5 points when won)'))}</label></div>
    <div class="mut">${esc(t('Gleicher Seed, gleiche Züge: gleiches Spiel. So könnt ihr euch vergleichen.','Same seed, same moves: the same game. That way you can compare.'))}</div>
    <div class="row"><button type="button" class="b p" data-ksnew="1">${esc(t('Spiel starten','Start the game'))}</button></div>`}
// the guide (krisenanleitung.py): sections of fixed blocks, loaded once; **x** is the only emphasis, all text through esc
const ksB=x=>esc(ksP(x)).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');
async function ksGuide(w){if(!KS.guide){w.innerHTML=`<div class="ld-empty mut">${esc(t('Lade die Anleitung …','Loading the guide …'))}</div>`;
    const {r,d}=await apiTry('/api/profile/krisenspiel/anleitung');if(!r.ok){w.innerHTML=`<div class="ld-empty err">${esc(errSay(r.status,d.detail,''))}</div>`;return}KS.guide=d.abschnitte}
  const G=KS.guide,blk=b=>b.art==='p'?`<p>${ksB(b.text)}</p>`:b.art==='liste'?`<ul>${b.punkte.map(x=>`<li>${ksB(x)}</li>`).join('')}</ul>`
    :b.art==='code'?`<pre class="ks-code">${esc(b.zeilen.join('\n'))}</pre>`
    :`<table class="ks-tab"><thead><tr>${b.kopf.map(x=>`<th>${esc(ksP(x))}</th>`).join('')}</tr></thead><tbody>${b.zeilen.map(r=>`<tr>${r.map((x,i)=>i===0&&!Array.isArray(x)?`<td><code>${esc(x)}</code></td>`:`<td>${esc(ksP(x))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  w.innerHTML=`<div class="ks-guide"><h3>${esc(t('Anleitung','Guide'))}</h3><nav class="ks-toc">${G.map(s=>`<a href="#ksg-${esc(s.id)}" data-ksgo="${esc(s.id)}">${esc(ksP(s.titel))}</a>`).join('')}</nav>
    ${G.map(s=>`<section id="ksg-${esc(s.id)}"><h4>${esc(ksP(s.titel))}</h4>${s.bloecke.map(blk).join('')}</section>`).join('')}</div>`;
  w.querySelectorAll('[data-ksgo]').forEach(a=>a.onclick=e=>{e.preventDefault();const x=document.getElementById('ksg-'+a.dataset.ksgo);if(x)x.scrollIntoView({behavior:'smooth',block:'start'})})}
function ksInspector(D){const g=D.spiel;if(!g)return `<div class="ld-empty mut">${esc(t('Noch kein Spiel.','No game yet.'))}</div>`;
  return `<h3>${esc(t('Inspector','Inspector'))}</h3><div class="mut">${esc(t('Jeder Zug Schritt für Schritt: was du gewählt hast, welche feste Regel gegriffen hat, welche Würfe aus dem Seed kamen und was das Sprachmodell erzählt hat. Werte ändert nur die Regel.','Every move step by step: what you chose, which fixed rule applied, which rolls came from the seed and what the language model told. Only the rule changes values.'))}</div>
    ${g.trace.slice().reverse().map(z=>`<details class="ks-tr"${z.zug===g.zug?' open':''}><summary>${esc(t(`Zug ${z.zug}`,`Move ${z.zug}`))} · ${z.steps.length} ${esc(t('Schritte','steps'))}</summary>
      <ol>${z.steps.map(s=>`<li class="ks-st ${esc(s.art)}"><b>${esc(t(...(KSSTEP[s.art]||[s.art,s.art])))}</b> · ${esc(ksP(s.titel))}${s.ms?` <small class="mut">${s.ms} ms</small>`:''}<pre>${esc(JSON.stringify(s.daten,null,1))}</pre></li>`).join('')}</ol></details>`).join('')}`}
function ksPast(D){const st=D.stats,have=D.erfolge.filter(e=>e.t).length;
  return `<h3>${esc(t('Bisherige Spiele','Past games'))}</h3><div class="mut">${esc(t(`${st.gespielt} gespielt · ${st.gewonnen} gewonnen · ${have} von ${D.erfolge.length} Erfolgen`,`${st.gespielt} played · ${st.gewonnen} won · ${have} of ${D.erfolge.length} achievements`))}</div>
    <ul class="facts">${D.verlauf.map(v=>`<li><span><b>${esc(ksP(v.titel))}</b> · ${esc(ksWhen(v.t))}<br><small class="mut">${esc(t(`${v.zuege} Züge · ${v.minuten} min · Seed ${v.seed}`,`${v.zuege} moves · ${v.minuten} min · seed ${v.seed}`))}</small></span><b class="ks-note small ${KSNOTE[v.note]||''}">${esc(v.note)}</b></li>`).join('')||`<li><span class="mut">${esc(t('Noch keine.','None yet.'))}</span></li>`}</ul>
    <h4>${esc(t('Erfolge','Achievements'))}</h4><div class="ks-ach">${D.erfolge.map(e=>`<div class="ks-a${e.t?' on':''}"><b>${esc(ksP(e.name))}</b><small>${esc(ksP(e.text))}</small>${e.t?`<small class="mut">${esc(ksWhen(e.t))}</small>`:''}</div>`).join('')}</div>
    <div class="row"><button type="button" class="b" data-ksclear="1">${esc(t('Meine Spieldaten löschen','Delete my game data'))}</button></div>`}
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#ksview [data-ksuhr],#ksview [data-ksmove],#ksview [data-ksnew],#ksview [data-ksagain],#ksview [data-ksgive],#ksview [data-ksclear],#ksview [data-kstab]');if(!b)return;const B=b.dataset;KS.focus=false;
  const go=k=>{icTabSet('spiel',k);ksOpen()};
  if(B.kstab){go(B.kstab);return}
  if(B.ksuhr){await ksSend('/api/profile/krisenspiel/uhr','POST',{aktion:B.ksuhr});return}
  if(B.ksmove){await ksSend('/api/profile/krisenspiel/zug','POST',{aktion:B.ksmove,zug:KS.data.spiel.zug});return}
  if(B.ksnew||B.ksagain){const w=$('ksview');let body;
    if(B.ksagain)body={szenario:B.ksagain,stufe:B.ksstufe,seed:+B.ksseed,modus:B.ksmodus,uhr:!!B.ksclock};
    else{const sz=w.querySelector('input[name=kssz]:checked'),sd=w.querySelector('.ksseed').value.trim();body={szenario:sz&&sz.value,stufe:w.querySelector('.ksstufe').value,modus:w.querySelector('.ksmodus').value,uhr:w.querySelector('.ksuhr').checked};
      if(sd!==''){const n=+sd;if(!Number.isInteger(n)||n<0||n>999999){ksSay(t('Der Seed ist eine Zahl von 0 bis 999999.','The seed is a number from 0 to 999999.'),true);return}body.seed=n}}
    if(await ksSend('/api/profile/krisenspiel/neu','POST',body))go('spiel');return}
  if(B.ksgive){if(!confirm(t('Aufgeben? Das Spiel zählt als F.','Give up? The game counts as F.')))return;await ksSend('/api/profile/krisenspiel','DELETE');return}
  if(B.ksclear){if(!confirm(t('Alle Spieldaten löschen: laufendes Spiel, bisherige Spiele und Erfolge?','Delete all game data: the running game, past games and achievements?')))return;
    if(await ksSend('/api/profile/krisenspiel/daten','DELETE')){await ksLoad();ksSay(t('Gelöscht.','Deleted.'))}}})}
