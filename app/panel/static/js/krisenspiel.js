// IT-Krisenspiel (krisenspiel.py, plan krisenspiel/plan.md, Paket 1): a page of its own in the menu. „Spiel“ is the
// crisis dashboard: the values on top, the systems with their state, the chronicle and the moves the panel offers;
// „Neues Spiel“ picks scenario, level and seed; „Inspector“ shows every step of a move (input, fixed rule, rolls from
// the seed, narrator); „Bisherige Spiele“ the results, achievements and „Meine Daten löschen“. Every value comes from
// the panel; texts from the scenarios and the narrator are only ever text (esc), never markup.
const KS={data:null,msg:'',err:false,busy:false,seq:0,turn:-1,hist:-1,con:null,focus:false,at:0,guide:null,ticked:0,big:false,ed:null,team:null,teamAt:0,made:null,an:''};
const KS_CHRON=6;   // chronicle entries shown above the console, the older ones fold away
let KS_ON=false;
const ksP=p=>Array.isArray(p)?p[L==='en'?1:0]:String(p??'');
// the grade's colour (app.css), named here in full so every class is found
const KSNOTE={A:'nA',B:'nB',E:'nE',F:'nF'};
const ksEur=v=>Number(v||0).toLocaleString(L==='en'?'en-GB':'de-DE')+' €';
const ksWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const KSSTAT={Online:['läuft','running','ok'],Degraded:['gestört','degraded','warn'],Critical:['kritisch','critical','bad'],
  Offline:['aus','off','bad'],Isolated:['isoliert','isolated','iso']};
const KSART={start:['Lage','Situation'],zug:['Zug','Move'],team:['Team','Team'],folge:['Folge','Consequence'],neben:['Nebenschauplatz','Side issue'],ende:['Ende','End']};
const KSSTEP={eingabe:['Eingabe','Input'],regel:['Feste Regel','Fixed rule'],zufall:['Zufall aus dem Seed','Chance from the seed'],
  modell:['Sprachmodell','Language model'],team:['Team','Team'],antwort:['Antwort','Answer'],ende:['Ende','End']};
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
  const keep=w.querySelector('.ks-in'),kv=keep?keep.value:'',kf=!!keep&&document.activeElement===keep;   // a redraw (a move of a co-player) keeps what is typed
  w.innerHTML=(tab==='neu'?ksNew(D):tab==='inspector'?ksInspector(D):tab==='bisher'?ksPast(D):ksGame(D))+`<div class="ksmsg ${KS.err?'err':'mut'}" role="status">${esc(KS.msg)}</div>`;
  const con=w.querySelector('.ks-con');if(con)con.scrollTop=con.scrollHeight;
  const det=w.querySelector('.ks-condet');if(det)det.ontoggle=()=>{KS.con=det.open};
  const inp=w.querySelector('.ks-in');if(inp){if(kv)inp.value=kv;if(KS.focus||kf)inp.focus({preventScroll:true});
    inp.onkeydown=e=>{const h=KS.data.spiel.konsole.verlauf;
      if(e.key==='Enter'){e.preventDefault();ksType(inp)}
      else if(e.key==='Tab'){e.preventDefault();ksTab(inp)}
      else if(e.key==='ArrowUp'&&h.length){e.preventDefault();KS.hist=KS.hist<0?h.length-1:Math.max(0,KS.hist-1);inp.value=h[KS.hist]}
      else if(e.key==='ArrowDown'&&KS.hist>=0){e.preventDefault();KS.hist++;inp.value=KS.hist<h.length?h[KS.hist]:'';if(KS.hist>=h.length)KS.hist=-1}}}
  const an=w.querySelector('.ks-an');if(an)an.onchange=()=>{KS.an=an.value;ksDraw()};
  ksEdBind(w)}
// Esc leaves the large console (not while an editor is open: there Esc belongs to vi)
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&KS.big&&!document.querySelector('#ksview .ks-ed')){KS.big=false;ksDraw()}});
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
  const head0=`<div class="ks-head"><div><h3>${esc(ksP(g.titel))}</h3><div class="mut">${esc(ksP(stufe))}${g.modus==='konsole'?esc(t(' · nur Konsole',' · console only')):''}${g.lernen?esc(t(' · Lernmodus',' · learning mode')):''}${g.heraus?esc(t(' · Herausforderung',' · challenge')):''}${(g.mutatoren||[]).length?' · '+esc(g.mutatoren.map(x=>ksMutName(D,x)).join(', ')):''} · Seed ${esc(String(g.seed))} · ${esc(t(`Zug ${g.zug} · Minute ${g.min}`,`Move ${g.zug} · minute ${g.min}`))}</div></div>
    ${g.ende?'':`<button type="button" class="b" data-ksgive="1">${esc(t('Aufgeben','Give up'))}</button>`}</div>`;
  const left=ksLeft(g),u=g.uhr;
  const clock=u&&!g.ende?`<div class="ks-uhr"><span class="mut">${esc(u.pause?t('Uhr angehalten','Clock paused'):t(`Uhr läuft: ${u.s} s = 1 min`,`Clock running: ${u.s} s = 1 min`))}</span>${u.pause_ok?`<button type="button" class="b" data-ksuhr="${u.pause?'weiter':'pause'}">${esc(u.pause?t('Weiter','Go on'):t('Pause','Pause'))}</button>`:''}</div>`:'';
  const mets=`<div class="ks-mets">${ksBar(t('Zeit','Time'),left,m.zeit_start,t(`${left} min`,`${left} min`),left*4<m.zeit_start,'ks-time')}
    ${ksBar(t('Stress','Stress'),m.stress,100,m.stress+' %',m.stress>=75)}${ksBar(t('Vertrauen','Trust'),m.vertrauen,100,m.vertrauen+' %',m.vertrauen<30)}
    ${ksBar(t('Moral','Morale'),m.moral,100,m.moral+' %',m.moral<30)}${ksBar(t('Budget','Budget'),m.budget,m.budget_start,ksEur(m.budget),m.budget*5<m.budget_start)}
    <div class="ks-met dmg"><span>${esc(t('Schaden','Damage'))}</span><b>${esc(ksEur(m.kosten))}</b></div></div>`;
  // Lernmodus: the panel's hint (krisenspiel.tipp); the ghost: the own best run of this scenario and level
  const hint=g.tipp?`<div class="ks-tipp"><b>${esc(t('Tipp','Hint'))}:</b> ${esc(ksP(g.tipp.label))} <small class="mut">${esc(ksP(g.tipp.warum))}</small></div>`:'';
  const gh=g.geist?`<div class="ks-geist mut">${esc(t(`Geist (dein bester Lauf, Note ${g.geist.note}, ${g.geist.punkte} Punkte)`,`Ghost (your best run, grade ${g.geist.note}, ${g.geist.punkte} points)`))}${g.geist.bei?esc(t(`: nach ${g.geist.bei.zug} Zügen Minute ${g.geist.bei.min}, Schaden ${ksEur(g.geist.bei.kosten)}; du: Minute ${g.min}, ${ksEur(m.kosten)}`,`: after ${g.geist.bei.zug} moves minute ${g.geist.bei.min}, damage ${ksEur(g.geist.bei.kosten)}; you: minute ${g.min}, ${ksEur(m.kosten)}`)):''}</div>`:'';
  const head=head0+clock+gh+hint;
  const assets=`<div class="ks-assets">${g.assets.map(a=>{const s=KSSTAT[a.status]||[a.status,a.status,''];
    return `<div class="ks-asset ${s[2]}"><b>${esc(a.name)}</b><small class="mut">${esc(ksP(a.typ))}</small><span class="pill ${s[2]}">${esc(t(s[0],s[1]))}</span><small>${esc(ksP(a.details))}</small></div>`}).join('')}</div>`;
  const ev=c=>`<div class="ks-ev ${esc(c.art)}"><small class="mut">${esc(t(...(KSART[c.art]||[c.art,c.art])))} · ${esc(t('Minute ','minute '))}${c.min}${c.wer?' · '+esc(ksP(D.rollen[c.wer.rolle]||[c.wer.rolle,c.wer.rolle]))+(c.wer.name?' ('+esc(c.wer.name)+')':''):''}</small><p>${esc(c.erzaehlt&&c.lang===(L==='en'?'en':'de')?c.erzaehlt:ksP(c.text))}</p>${c.erzaehlt&&c.lang===(L==='en'?'en':'de')?`<details><summary>${esc(t('Feste Fakten','Fixed facts'))}</summary><small>${esc(ksP(c.text))}</small></details>`:''}</div>`;
  const all=g.chronik.slice().reverse(),old=all.slice(KS_CHRON);
  const chron=`<div class="ks-chron" aria-live="polite">${all.slice(0,KS_CHRON).map(ev).join('')}${old.length?`<details class="ks-old"><summary>${esc(t(`Ältere (${old.length})`,`Older (${old.length})`))}</summary>${old.map(ev).join('')}</details>`:''}</div>`;
  const cost=a=>Object.entries(a.kosten).map(([k,v])=>k==='budget'?ksEur(v):k==='zeit'?v+' min':(v>0?'+':'')+v+' '+t({stress:'Stress',vertrauen:'Vertrauen',moral:'Moral'}[k]||k,{stress:'stress',vertrauen:'trust',moral:'morale'}[k]||k)).join(' · ');
  const kol=g.kollegen||[],me=kol.find(k=>k.id===KS.an&&!k.auftrag&&k.muede<100);if(!me)KS.an='';
  const team=kol.length?`<h4>${esc(t('Dein Team','Your team'))}</h4><div class="ks-kol">${kol.map(k=>`<div class="ks-k${k.auftrag?' busy':''}"><b>${esc(k.name)}</b><small class="mut">${esc(k.faecher.map(f=>ksP(D.faecher[f]||[f,f])).join(', '))}</small>
      ${ksBar(t('Müde','Tired'),k.muede,100,k.muede+' %',k.muede>=70)}<small>${k.auftrag?esc(t(`arbeitet: ${ksP(k.auftrag.label)} · noch ${k.rest} min`,`working: ${ksP(k.auftrag.label)} · ${k.rest} min left`)):esc(t('frei','free'))}</small></div>`).join('')}</div>`:'';
  const who=kol.length&&!g.ende&&g.modus!=='konsole'?`<label class="ks-who">${esc(t('Wer übernimmt?','Who takes it?'))} <select class="ks-an">${[['',t('Ich selbst','Myself')]].concat(kol.filter(k=>!k.auftrag&&k.muede<100).map(k=>[k.id,k.name+' ('+k.faecher.map(f=>ksP(D.faecher[f]||[f,f])).join(', ')+')'])).map(([v,l])=>`<option value="${esc(v)}"${v===KS.an?' selected':''}>${esc(l)}</option>`).join('')}</select></label>`:'';
  const acts=g.ende?ksEnd(D,g):g.modus==='konsole'?`<div class="ks-only mut">${esc(t('Nur Konsole: jeder Zug wird getippt. „help“ zeigt die Befehle, „hosts“ die Rechner.','Console only: every move is typed. "help" shows the commands, "hosts" the machines.'))}</div>`:`<h4>${esc(t('Deine Züge','Your moves'))}</h4>${who}<div class="ks-acts">${g.aktionen.map(a=>{const off=!a.frei||KS.an&&!a.fach;
    return `<button type="button" class="b ks-act${g.tipp&&g.tipp.aktion===a.id?' ks-hint':''}" data-ksmove="${esc(a.id)}"${off?' disabled':''} title="${esc(!a.frei?ksP(a.warum):KS.an&&!a.fach?t('Bleibt bei der Leitung','Stays with the lead'):'')}"><b>${esc(ksP(a.label))}</b><small>${esc(KS.an&&a.fach?t('Fach: ','Subject: ')+ksP(D.faecher[a.fach]||[a.fach,a.fach]):cost(a))}</small></button>`}).join('')}</div>`;
  return head+mets+`<div class="ks-grid"><div>${assets}${acts}${team}${D.team?`<div class="ks-team">${ksTeamBox(g)}</div>`:''}</div><div><h4>${esc(t('Chronik','Chronicle'))}</h4>${chron}${ksCon(g)}</div></div>`}
// the simulated console (krisenkonsole.py): nothing typed here ever runs; the Spark cuts each line by fixed rules and
// answers from the game. A phone shows it folded unless the game is console only; ↑/↓ the last lines, Tab completes.
const KSCON={err:'kc-err',zug:'kc-zug'};   // the kinds of console lines and their style
function ksCon(g){const k=g.konsole;if(!k)return '';
  const open=KS.big||(KS.con!==null?KS.con:(g.modus==='konsole'||!matchMedia('(max-width:700px)').matches));
  const rows=k.zeilen.map(z=>z.k==='in'?`<div class="kc-in"><span class="kc-p">admin@${esc(z.h||'')}:~$</span> ${esc(z.s)}</div>`:`<div class="${KSCON[z.k]||'kc-out'}">${esc(z.s)}</div>`).join('');
  const ed=!g.ende&&k.editor?ksEd(k.editor):'';
  return `<details class="ks-condet${KS.big?' ks-big':''}"${open?' open':''}><summary>${esc(t('Konsole','Console'))} <small class="mut">${esc(k.host)}${k.lesen?esc(t(` · ${k.lesen} min gelesen`,` · ${k.lesen} min read`)):''}</small>
    <button type="button" class="b ks-bigbtn" data-ksbig="1" title="${esc(KS.big?t('Zurück in die Seite (Esc)','Back into the page (Esc)'):t('Groß: Konsole füllt das Fenster','Large: the console fills the window'))}">${esc(KS.big?t('Klein','Small'):t('Groß','Large'))}</button></summary>
    ${ed||`<div class="ks-con" role="log">${rows||`<div class="kc-out mut">${esc(t('Tippe help für die Befehle. Nichts hier läuft wirklich.','Type help for the commands. Nothing here really runs.'))}</div>`}</div>
    ${g.ende?'':`<div class="ks-cline"><span class="kc-p">admin@${esc(k.host)}:${esc(ksShort(k.cwd))}$</span><input class="ks-in" type="text" maxlength="200" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="${esc(t('Befehl','Command'))}"><button type="button" class="b ks-tabkey" data-kstabkey="1" title="${esc(t('Vervollständigen (Tab)','Complete (Tab)'))}">⇥</button></div>`}`}</details>`}
const ksShort=c=>!c?'~':c==='/home/admin'?'~':c.startsWith('/home/admin/')?'~'+c.slice(11):c;
async function ksType(inp){const z=inp.value;if(!z.trim()||KS.busy||!KS.data||!KS.data.spiel)return;KS.hist=-1;KS.focus=true;
  inp.value='';await ksSend('/api/profile/krisenspiel/konsole','POST',{zeile:z,zug:KS.data.spiel.zug})}
// Tab like bash: the first word from the commands, after ssh the machines, after man and help the commands, else
// files and directories of the machine (relative to the working directory); several hits complete their common
// start and are listed
function ksTab(inp){const k=KS.data.spiel.konsole,v=inp.value,parts=v.split(' '),last=parts[parts.length-1],first=parts[0].replace(/^sudo$/,'')||parts[1]||'';
  let pool,base='',word=last;
  if(parts.length===1||parts.length===2&&parts[0]==='sudo')pool=k.befehle;
  else if(['ssh','ping','traceroute','tracert','nmap','telnet','nc'].includes(first.toLowerCase()))pool=k.hosts;
  else if(['man','help','which','whereis','type'].includes(first.toLowerCase())&&parts.length===2)pool=k.befehle;
  else{const abs=last.startsWith('/')?last:last.startsWith('~/')?'/home/admin/'+last.slice(2):(k.cwd==='/'?'':k.cwd)+'/'+last;
    const cut=abs.lastIndexOf('/')+1,dir=abs.slice(0,cut);base=last.slice(0,last.length-(abs.length-cut));word=abs.slice(cut);
    pool=k.pfade.filter(p=>p.startsWith(dir)&&p.length>dir.length&&!p.slice(dir.length).replace(/\/$/,'').includes('/')).map(p=>p.slice(dir.length))}
  const hit=(pool||[]).filter(x=>x.startsWith(word));if(!hit.length)return;
  let pre=hit[0];for(const h of hit)while(!h.startsWith(pre))pre=pre.slice(0,-1);
  parts[parts.length-1]=base+pre+(hit.length===1&&!pre.endsWith('/')?' ':'');inp.value=parts.join(' ');
  if(hit.length>1&&pre===word)ksSay(hit.join('  '))}
// nano, vi and vim (krisenlinux._edit): the text lives in the page until it is written; the Spark keeps it in the
// game's simulated files (POST …/datei), nothing reaches a disk. nano: Ctrl+O writes, Ctrl+X leaves (asks first when
// changed); vi and vim: i, a, o, A to write, Esc back, x and dd, h j k l, :w :q :wq :x :q!
function ksEdSync(e){if(!KS.ed||KS.ed.pfad!==e.pfad||KS.ed.art!==e.art){const text=e.zeilen.join('\n')+(e.zeilen.length?'\n':'');KS.ed={pfad:e.pfad,art:e.art,text,saved:text,mode:'normal',cmd:null,ask:false,note:e.neu?t('[ Neue Datei ]','[ New File ]'):'',d:false}}return KS.ed}
function ksEd(e){const E=ksEdSync(e),vi=E.art!=='nano',dirty=E.text!==E.saved;
  const head=vi?'':`<div class="ks-edhead"><span>GNU nano 7.2</span><b>${esc(e.pfad)}</b><span>${dirty?esc(t('Geändert','Modified')):''}</span></div>`;
  const ro=!e.schreiben?esc(t(' [nur lesen: sudo davor zum Speichern]',' [read-only: put sudo in front to write]')):'';
  const foot=vi?`<div class="ks-edfoot vi">${E.cmd!==null?`<span>:</span><input class="ks-edcmd" type="text" maxlength="40" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="${esc(t('vi-Befehl','vi command'))}" value="${esc(E.cmd)}">`
      :`<span>${esc(E.mode==='insert'?'-- INSERT --':(E.note||`"${e.pfad}"${e.neu?' [New]':''} ${E.text.split('\n').length-(E.text.endsWith('\n')?1:0)}L`))}${ro}</span>`}</div>`
    :`<div class="ks-edfoot">${E.ask?`<span>${esc(t('Geänderten Puffer speichern? J Ja · N Nein · Esc Abbrechen','Save modified buffer? Y Yes · N No · Esc Cancel'))}</span>`
      :`<span>${esc(E.note)}${ro}</span><button type="button" class="b" data-ksed="save">^O ${esc(t('Speichern','Write Out'))}</button><button type="button" class="b" data-ksed="exit">^X ${esc(t('Beenden','Exit'))}</button>`}</div>`;
  const viKeys=vi?`<div class="ks-edkeys">${[['i','i'],['esc','Esc'],['w',':w'],['q',':q'],['wq',':wq'],['qq',':q!']].map(([k,l])=>`<button type="button" class="b" data-ksvi="${k}">${esc(l)}</button>`).join('')}</div>`:'';
  return `<div class="ks-ed ${vi?'vi':'nano'}">${head}<textarea class="ks-edtext" spellcheck="false" autocapitalize="off" autocomplete="off" aria-label="${esc(e.pfad)}"${vi&&E.mode!=='insert'?' readonly':''}>${esc(E.text)}</textarea>${foot}${viKeys}</div>`}
async function ksEdSave(){const E=KS.ed,g=KS.data.spiel;const d=await ksSend('/api/profile/krisenspiel/datei','POST',{aktion:'speichern',text:E.text,zug:g.zug});
  if(!d)return false;const z=d.spiel.konsole.zeilen,last=z.length?z[z.length-1]:null;
  if(last&&last.k==='err'){E.note=last.s;ksDraw();return false}E.saved=E.text;E.note=last?last.s:'';ksDraw();return true}
async function ksEdClose(){KS.ed=null;KS.focus=true;await ksSend('/api/profile/krisenspiel/datei','POST',{aktion:'schliessen',zug:KS.data.spiel.zug})}
async function ksViCmd(c){const E=KS.ed,dirty=E.text!==E.saved;E.cmd=null;c=c.trim();
  if(c==='w')await ksEdSave();
  else if(c==='wq'||c==='x'){if(await ksEdSave())await ksEdClose()}
  else if(c==='q'){if(dirty){E.note='E37: No write since last change (add ! to override)';ksDraw()}else await ksEdClose()}
  else if(c==='q!')await ksEdClose();
  else if(/^\d+$/.test(c)){ksDraw();const ta=document.querySelector('#ksview .ks-edtext');if(ta){const ls=E.text.split('\n'),n=Math.min(+c,ls.length)-1;ta.selectionStart=ta.selectionEnd=ls.slice(0,Math.max(0,n)).join('\n').length+(n>0?1:0)}}
  else{E.note=`E492: Not an editor command: ${c}`;ksDraw()}}
function ksEdBind(w){const ta=w.querySelector('.ks-edtext');if(!ta||!KS.ed)return;const E=KS.ed,vi=E.art!=='nano';
  ta.oninput=()=>{E.text=ta.value;E.note=''};
  if(E.pos!=null){ta.selectionStart=ta.selectionEnd=Math.min(E.pos,ta.value.length);E.pos=null}
  if(!w.querySelector('.ks-edcmd'))ta.focus({preventScroll:true});
  const line=()=>{const p=ta.selectionStart,s=ta.value.lastIndexOf('\n',p-1)+1,e0=ta.value.indexOf('\n',p);return [s,e0<0?ta.value.length:e0]};
  const mode=m=>{E.mode=m;E.note='';E.pos=ta.selectionStart;ksDraw()};
  ta.onkeydown=async ev=>{const k=ev.key;
    if(!vi){if(E.ask){ev.preventDefault();if(/^[yj]$/i.test(k)){E.ask=false;if(await ksEdSave())await ksEdClose()}else if(/^n$/i.test(k)){E.ask=false;await ksEdClose()}else if(k==='Escape'||ev.ctrlKey&&k==='c'){E.ask=false;ksDraw()}return}
      if(ev.ctrlKey&&(k==='o'||k==='s')){ev.preventDefault();await ksEdSave()}
      else if(ev.ctrlKey&&k==='x'){ev.preventDefault();if(E.text!==E.saved){E.ask=true;ksDraw()}else await ksEdClose()}
      else if(k==='Tab'){ev.preventDefault();document.execCommand('insertText',false,'\t')}
      return}
    if(E.mode==='insert'){if(k==='Escape'){ev.preventDefault();mode('normal')}else if(k==='Tab'){ev.preventDefault();document.execCommand('insertText',false,'\t')}return}
    if(ev.ctrlKey||ev.metaKey||ev.altKey||k.startsWith('Arrow')||k.startsWith('Page')||k==='Home'||k==='End')return;
    ev.preventDefault();const p=ta.selectionStart,[s,e0]=line();
    if(k==='d'){if(E.d){E.d=false;const end=Math.min(e0+1,ta.value.length);E.text=ta.value.slice(0,s)+ta.value.slice(end);E.pos=s;ksDraw()}else E.d=true;return}
    E.d=false;
    if(k===':'){E.cmd='';E.pos=p;ksDraw();const c=document.querySelector('#ksview .ks-edcmd');if(c)c.focus();return}
    if(k==='i')mode('insert');
    else if(k==='a'){ta.selectionStart=ta.selectionEnd=Math.min(p+1,e0);mode('insert')}
    else if(k==='A'){ta.selectionStart=ta.selectionEnd=e0;mode('insert')}
    else if(k==='I'){ta.selectionStart=ta.selectionEnd=s;mode('insert')}
    else if(k==='o'){E.text=ta.value.slice(0,e0)+'\n'+ta.value.slice(e0);E.pos=e0+1;E.mode='insert';ksDraw()}
    else if(k==='x'&&p<e0){E.text=ta.value.slice(0,p)+ta.value.slice(p+1);E.pos=p;ksDraw()}
    else if(k==='h')ta.selectionStart=ta.selectionEnd=Math.max(s,p-1);
    else if(k==='l')ta.selectionStart=ta.selectionEnd=Math.min(e0,p+1);
    else if(k==='j'||k==='k'){const col=p-s;if(k==='j'&&e0<ta.value.length){const n2=ta.value.indexOf('\n',e0+1);ta.selectionStart=ta.selectionEnd=Math.min(e0+1+col,n2<0?ta.value.length:n2)}
      else if(k==='k'&&s>0){const s2=ta.value.lastIndexOf('\n',s-2)+1;ta.selectionStart=ta.selectionEnd=Math.min(s2+col,s-1)}}};
  const c=w.querySelector('.ks-edcmd');if(c){c.focus();c.onkeydown=ev=>{if(ev.key==='Enter'){ev.preventDefault();ksViCmd(c.value)}else if(ev.key==='Escape'){ev.preventDefault();E.cmd=null;ksDraw()}};c.oninput=()=>{E.cmd=c.value}}}
// Gemeinsam spielen (krisenteam.py): seats with a role by an invitation link; the link and its QR code only right
// after making it. While seats are open the page asks every poll seconds for the move and redraws on a new one.
function ksTeamBox(g){const T=KS.team,R=KS.data.rollen;
  if(!T)return `<h4>${esc(t('Mitspieler','Players'))}</h4><div class="mut">${esc(t('Lädt …','Loading …'))}</div>`;
  const rows=T.plaetze.map(p=>`<div class="setrow"><div class="lbl"><b>${esc(ksP(R[p.rolle]))}${p.name?' · '+esc(p.name):''}</b><span>${p.online?`<span class="pill ok">${esc(t('dabei','here'))}</span>`:esc(p.name?t('gerade nicht da','not here right now'):t('noch nicht beigetreten','not joined yet'))}</span></div><button type="button" class="b" data-ksseat="${esc(p.id)}">${esc(t('Entfernen','Remove'))}</button></div>`).join('');
  const made=KS.made?`<div class="mitmade"><div class="jqr">${KS.made.qr||''}</div><div class="sp"><input readonly value="${esc(KS.made.link)}" aria-label="${esc(t('Der Link','The link'))}" class="ks-teamlink">
    <div class="row"><button type="button" class="b" data-kscopy="1">${esc(t('Kopieren','Copy'))}</button></div><div class="fh">${esc(t('Nur jetzt sichtbar: weitergeben oder den QR-Code zeigen.','Visible only now: pass it on or show the QR code.'))}</div></div></div>`:'';
  const add=!g.ende&&T.plaetze.length<T.max?`<div class="row"><select class="ks-rolle" aria-label="${esc(t('Rolle','Role'))}">${T.rollen.map(r=>`<option value="${esc(r.id)}">${esc(ksP(r.name))}</option>`).join('')}</select><button type="button" class="b" data-ksinvite="1">${esc(t('Einladen','Invite'))}</button></div>`:'';
  return `<h4>${esc(t('Mitspieler','Players'))}</h4><div class="mut">${esc(t(`Du spielst als Leitung. Bis zu ${T.max} Mitspieler per Link, mit oder ohne Profil; der Link gilt nur für dieses Spiel und höchstens ${T.stunden} Stunden.`,`You play as Lead. Up to ${T.max} players by link, with or without a profile; the link works only for this game and at most ${T.stunden} hours.`))}</div>${rows}${made}${add}`}
async function ksTeamLoad(){const g=KS.data&&KS.data.spiel;if(!KS.data||!KS.data.team)return;KS.teamAt=Date.now();
  const {r,d}=await apiTry('/api/profile/krisenspiel/team');if(!r.ok)return;const before=KS.team;KS.team=d;
  if(g&&(d.spiel!==g.id||d.zug!==g.zug||d.ende!==!!g.ende)){await ksLoad();return}
  const box=document.querySelector('#ksview .ks-team');if(box&&JSON.stringify(before)!==JSON.stringify(d))box.innerHTML=ksTeamBox(g)}
async function ksTeamClick(B,b){const g=KS.data.spiel;
  if(B.kscopy){const f=document.querySelector('#ksview .ks-teamlink');try{await navigator.clipboard.writeText(f.value);b.textContent=t('Kopiert','Copied')}catch{f.select()}return}
  const o=B.ksinvite?xjson('POST',{rolle:document.querySelector('#ksview .ks-rolle').value,base:location.origin}):{method:'DELETE'};
  const {r,d}=await apiTry('/api/profile/krisenspiel/team'+(B.ksseat?'/'+encodeURIComponent(B.ksseat):''),o);
  if(!r.ok){ksSay(errSay(r.status,d.detail,''),true);return}
  KS.team=d;KS.made=B.ksinvite?{link:d.link,qr:d.qr}:null;const box=document.querySelector('#ksview .ks-team');if(box)box.innerHTML=ksTeamBox(g)}
setInterval(()=>{const D=KS.data,w=$('ksview');if(!D||!D.team||!D.spiel||!w||w.dataset.tab!=='spiel'||w.offsetParent===null||document.visibilityState!=='visible'||KS.busy)return;
  const T=KS.team;if(T&&(!T.plaetze.length||D.spiel.ende)&&Date.now()-KS.teamAt<60000)return;   // nobody invited: once a minute
  if(Date.now()-KS.teamAt>=(T?T.poll:4)*1000)ksTeamLoad()},1000);
function ksEnd(D,g){const e=g.ende,names=Object.fromEntries(D.erfolge.map(x=>[x.id,x.name]));
  return `<div class="ks-end"><div class="ks-note ${KSNOTE[e.note]||''}">${esc(e.note)}</div><div><h4>${esc(t(`${e.punkte} von 100 Punkten`,`${e.punkte} of 100 points`))}</h4>
    <ul class="facts small">${e.gruende.map(x=>`<li><span>${esc(ksP(x))}</span></li>`).join('')}</ul>
    ${(e.erfolge||[]).length?`<div>${e.erfolge.map(k=>`<span class="pill ok">${esc(ksP(names[k]||[k,k]))}</span>`).join(' ')}</div>`:''}
    ${(e.lehren||[]).length?`<h4>${esc(t('Nachbesprechung','Debrief'))}</h4><ul class="ks-lehren">${e.lehren.map(x=>`<li class="${x.gut?'gut':'besser'}"><span>${esc(x.gut?t('Gut: ','Good: '):t('Besser: ','Better: '))}${esc(ksP(x.text))}</span><small class="mut">${esc(x.bezug)}</small></li>`).join('')}</ul>`:''}
    <div class="row"><button type="button" class="b p" data-ksagain="${esc(g.szenario)}" data-ksstufe="${esc(g.stufe)}" data-ksseed="${esc(String(g.seed))}" data-ksmodus="${esc(g.modus||'knoepfe')}" data-ksclock="${g.uhr?1:''}" data-kslearn="${g.lernen?1:''}" data-ksmuts="${esc((g.heraus?[]:g.mutatoren||[]).join(','))}">${esc(t('Nochmal mit diesem Seed','Again with this seed'))}</button><button type="button" class="b" data-kstab="neu">${esc(t('Neues Spiel','New game'))}</button></div></div></div>`}
// Herausforderungen (Paket 6): the same game for every profile on one day or week, with mutators; the board shows
// first tries (by name only where the profile wants it)
const ksMutName=(D,id)=>{const m=D.mutatoren.find(x=>x.id===id);return m?ksP(m.name):id};
function ksHeraus(D){const H=D.herausforderungen||[];if(!H.length)return '';
  const card=h=>`<div class="ks-her"><b>${esc(ksP(h.name))}</b><small>${esc(ksP(h.titel))} · ${esc(h.mutatoren.map(x=>ksMutName(D,x)).join(', '))} · Seed ${h.seed}</small>
    <small class="mut">${esc(h.ich?t(`Dein erster Versuch: ${h.ich.punkte} Punkte, Note ${h.ich.note}. Weitere Versuche zählen nicht für die Liste.`,`Your first try: ${h.ich.punkte} points, grade ${h.ich.note}. More tries do not count for the board.`):t('Noch nicht gespielt: der erste Versuch zählt.','Not played yet: the first try counts.'))}</small>
    ${h.liste.length?`<ol class="ks-board">${h.liste.map(r=>`<li class="${r.ich?'ich':''}"><span>${esc(r.ich?t('Du','You'):r.name||t('Ein Profil','A profile'))}</span><span>${r.punkte} · ${esc(r.note)} · ${r.minuten} min</span></li>`).join('')}</ol>`:''}
    <button type="button" class="b" data-ksheraus="${esc(h.art)}">${esc(t('Annehmen','Accept'))}</button></div>`;
  return `<h4>${esc(t('Herausforderungen','Challenges'))}</h4><div class="ks-hers">${H.map(card).join('')}</div>
    <label>${esc(t('In den Bestenlisten','On the boards'))} <select class="ksboard">${[['anonym',t('ohne Namen','without name')],['name',t('mit meinem Namen','with my name')],['aus',t('gar nicht','not at all')]].map(([v,l])=>`<option value="${v}"${D.bestenliste===v?' selected':''}>${esc(l)}</option>`).join('')}</select></label>`}
function ksNew(D){const run=D.spiel&&!D.spiel.ende;
  return `<h3>${esc(t('Neues Spiel','New game'))}</h3>${run?`<div class="mut">${esc(t('Ein neues Spiel ersetzt das laufende.','A new game replaces the running one.'))}</div>`:''}
    ${ksHeraus(D)}<h4>${esc(t('Frei spielen','Free play'))}</h4>
    <div class="ks-pick">${D.szenarien.map((s,i)=>`<label class="ks-sz"><input type="radio" name="kssz" value="${esc(s.id)}"${i?'':' checked'}><b>${esc(ksP(s.titel))}</b><small>${esc(ksP(s.kurz))}</small><small class="mut">${esc(t(`${s.systeme} Systeme`,`${s.systeme} systems`))}${D.stats.beste[s.id]?esc(t(` · bisher bestes Ergebnis ${D.stats.beste[s.id]} Punkte`,` · best so far ${D.stats.beste[s.id]} points`)):''}</small></label>`).join('')}<label class="ks-sz"><input type="radio" name="kssz" value="zufall"><b>${esc(t('🎲 Überraschung','🎲 Surprise'))}</b><small>${esc(t('Eines der Szenarien per Zufall: Was passiert, siehst du erst im Spiel.','One of the scenarios by chance: you see what happens only in the game.'))}</small></label></div>
    <div class="row"><label>${esc(t('Stufe','Level'))} <select class="ksstufe">${D.stufen.map(s=>`<option value="${esc(s.id)}"${s.id==='normal'?' selected':''}>${esc(ksP(s.name))} (${s.zeit} min)</option>`).join('')}</select></label>
    <label>Seed <input class="ksseed" type="number" min="0" max="999999" inputmode="numeric" placeholder="${esc(t('zufällig','random'))}"></label></div>
    <div class="row"><label>${esc(t('Spielweise','How to play'))} <select class="ksmodus"><option value="knoepfe">${esc(t('Knöpfe und Konsole','Buttons and console'))}</option><option value="konsole">${esc(t('Nur Konsole (+5 Punkte beim Sieg)','Console only (+5 points when won)'))}</option></select></label>
    <label class="chk"><input type="checkbox" class="kslernen"> ${esc(t('Lernmodus (vor jedem Zug ein Tipp, dafür keine Erfolge)','Learning mode (a hint before every move, no achievements)'))}</label>
    <label class="chk"><input type="checkbox" class="ksuhr"> ${esc(t('Uhr läuft (10 Sekunden = 1 Spielminute, +5 Punkte beim Sieg)','Clock running (10 seconds = 1 game minute, +5 points when won)'))}</label></div>
    <div class="row ks-muts">${D.mutatoren.map(m=>`<label class="chk" title="${esc(ksP(m.text))}"><input type="checkbox" class="ksmut" value="${esc(m.id)}"> ${esc(ksP(m.name))} (+${m.bonus})</label>`).join('')}</div>
    <div class="mut">${esc(t('Gleicher Seed, gleiche Züge: gleiches Spiel. So könnt ihr euch vergleichen.','Same seed, same moves: the same game. That way you can compare.'))}</div>
    <div class="mut">${esc(t(`Dein Rang: ${ksP(D.laufbahn.name)} · ${D.laufbahn.team} Kollegen im Team · Budget ×${D.laufbahn.budget}`,`Your rank: ${ksP(D.laufbahn.name)} · ${D.laufbahn.team} colleagues on the team · budget ×${D.laufbahn.budget}`))}</div>
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
// Laufbahn (krisenspiel.laufbahn): the rank from the own results, what the next one takes, the whole ladder
function ksCareer(D){const L0=D.laufbahn,n=L0.naechster;
  return `<div class="ks-career"><h4>${esc(t('Laufbahn','Career'))}: ${esc(ksP(L0.name))}</h4>
    <div class="mut">${esc(n?t(`Nächster Rang ${ksP(n.name)}: ${n.gewonnen} gewonnene Spiele (du hast ${L0.gewonnen})${n.note_a?' und einmal Note A':''}.`,`Next rank ${ksP(n.name)}: ${n.gewonnen} games won (you have ${L0.gewonnen})${n.note_a?' and one grade A':''}.`):t('Höchster Rang erreicht.','Highest rank reached.'))}</div>
    ${n?ksBar(t('Fortschritt','Progress'),Math.min(L0.gewonnen,n.gewonnen),n.gewonnen||1,`${Math.min(L0.gewonnen,n.gewonnen)} / ${n.gewonnen}`,false):''}
    <ol class="ks-ladder">${L0.raenge.map(r=>`<li class="${r.rang===L0.rang?'on':''}"><b>${esc(ksP(r.name))}</b> <small class="mut">${esc(t(`ab ${r.gewonnen} Siegen${r.note_a?' und Note A':''} · ${r.team} Kollegen · Budget ×${r.budget}`,`from ${r.gewonnen} wins${r.note_a?' and grade A':''} · ${r.team} colleagues · budget ×${r.budget}`))}</small></li>`).join('')}</ol></div>`}
// Statistik je Szenario (Paket 5): played, won, average and best points, average minutes; the grades
function ksStats(D){const je=D.stats.je||{},rows=D.szenarien.filter(s=>je[s.id]);if(!rows.length)return '';
  const no=D.stats.noten||{};
  return `<h4>${esc(t('Statistik','Statistics'))}</h4><table class="ks-tab"><thead><tr>${[['Szenario','Scenario'],['Gespielt','Played'],['Gewonnen','Won'],['Schnitt','Average'],['Beste','Best'],['Minuten','Minutes']].map(x=>`<th>${esc(t(...x))}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(s=>{const x=je[s.id];return `<tr><td>${esc(ksP(s.titel))}</td><td>${x.gespielt}</td><td>${x.gewonnen}</td><td>${Math.round(x.summe/x.gespielt)}</td><td>${D.stats.beste[s.id]??'–'}</td><td>${Math.round(x.minuten/x.gespielt)}</td></tr>`}).join('')}</tbody></table>
    <div class="mut">${esc(t('Noten: ','Grades: '))}${['A','B','C','D','E','F'].map(n=>`${n} ${no[n]||0}`).join(' · ')}</div>`}
function ksPast(D){const st=D.stats,have=D.erfolge.filter(e=>e.t).length;
  return `<h3>${esc(t('Bisherige Spiele','Past games'))}</h3>${ksCareer(D)}${ksStats(D)}<div class="mut">${esc(t(`${st.gespielt} gespielt · ${st.gewonnen} gewonnen · ${have} von ${D.erfolge.length} Erfolgen`,`${st.gespielt} played · ${st.gewonnen} won · ${have} of ${D.erfolge.length} achievements`))}</div>
    <ul class="facts">${D.verlauf.map(v=>`<li><span><b>${esc(ksP(v.titel))}</b> · ${esc(ksWhen(v.t))}<br><small class="mut">${esc(t(`${v.zuege} Züge · ${v.minuten} min · Seed ${v.seed}`,`${v.zuege} moves · ${v.minuten} min · seed ${v.seed}`))}${v.lernen?esc(t(' · Lernmodus',' · learning mode')):''}${v.heraus?esc(t(' · Herausforderung',' · challenge')):''}${(v.mutatoren||[]).length?' · '+esc(v.mutatoren.map(x=>ksMutName(D,x)).join(', ')):''}</small></span><b class="ks-note small ${KSNOTE[v.note]||''}">${esc(v.note)}</b></li>`).join('')||`<li><span class="mut">${esc(t('Noch keine.','None yet.'))}</span></li>`}</ul>
    <h4>${esc(t('Erfolge','Achievements'))}</h4><div class="ks-ach">${D.erfolge.map(e=>`<div class="ks-a${e.t?' on':''}"><b>${esc(ksP(e.name))}</b><small>${esc(ksP(e.text))}</small>${e.t?`<small class="mut">${esc(ksWhen(e.t))}</small>`:''}</div>`).join('')}</div>
    <div class="row"><button type="button" class="b" data-ksclear="1">${esc(t('Meine Spieldaten löschen','Delete my game data'))}</button></div>`}
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#ksview [data-ksbig],#ksview [data-kstabkey],#ksview [data-ksed],#ksview [data-ksvi],#ksview [data-ksinvite],#ksview [data-ksseat],#ksview [data-kscopy],#ksview [data-ksuhr],#ksview [data-ksmove],#ksview [data-ksnew],#ksview [data-ksheraus],#ksview [data-ksagain],#ksview [data-ksgive],#ksview [data-ksclear],#ksview [data-kstab]');if(!b)return;const B=b.dataset;KS.focus=false;
  const go=k=>{icTabSet('spiel',k);ksOpen()};
  if(B.kstab){go(B.kstab);return}
  if(B.ksbig){e.preventDefault();KS.big=!KS.big;KS.con=true;ksDraw();return}
  if(B.kstabkey){const i=document.querySelector('#ksview .ks-in');if(i){ksTab(i);i.focus()}return}
  if(B.ksed){if(B.ksed==='save')await ksEdSave();else if(KS.ed.text!==KS.ed.saved){KS.ed.ask=true;ksDraw()}else await ksEdClose();return}
  if(B.ksvi){const E=KS.ed,ta=document.querySelector('#ksview .ks-edtext');if(ta)E.pos=ta.selectionStart;
    if(B.ksvi==='i'){E.mode='insert';ksDraw()}else if(B.ksvi==='esc'){E.mode='normal';E.cmd=null;ksDraw()}else await ksViCmd({w:'w',q:'q',wq:'wq',qq:'q!'}[B.ksvi]);return}
  if(B.ksinvite||B.ksseat||B.kscopy){await ksTeamClick(B,b);return}
  if(B.ksuhr){await ksSend('/api/profile/krisenspiel/uhr','POST',{aktion:B.ksuhr});return}
  if(B.ksmove){const an=KS.an;KS.an='';await ksSend('/api/profile/krisenspiel/zug','POST',Object.assign({aktion:B.ksmove,zug:KS.data.spiel.zug},an?{an}:{}));return}
  if(B.ksnew||B.ksagain||B.ksheraus){const w=$('ksview');let body;
    if(B.ksheraus)body={herausforderung:B.ksheraus,modus:w.querySelector('.ksmodus').value,uhr:w.querySelector('.ksuhr').checked};
    else if(B.ksagain)body={szenario:B.ksagain,stufe:B.ksstufe,seed:+B.ksseed,modus:B.ksmodus,uhr:!!B.ksclock,lernen:!!B.kslearn,mutatoren:B.ksmuts?B.ksmuts.split(','):[]};
    else{const sz=w.querySelector('input[name=kssz]:checked'),sd=w.querySelector('.ksseed').value.trim();body={szenario:sz&&sz.value,stufe:w.querySelector('.ksstufe').value,modus:w.querySelector('.ksmodus').value,uhr:w.querySelector('.ksuhr').checked,lernen:w.querySelector('.kslernen').checked,mutatoren:[...w.querySelectorAll('.ksmut:checked')].map(x=>x.value)};
      if(sd!==''){const n=+sd;if(!Number.isInteger(n)||n<0||n>999999){ksSay(t('Der Seed ist eine Zahl von 0 bis 999999.','The seed is a number from 0 to 999999.'),true);return}body.seed=n}}
    if(await ksSend('/api/profile/krisenspiel/neu','POST',body))go('spiel');return}
  if(B.ksgive){if(!confirm(t('Aufgeben? Das Spiel zählt als F.','Give up? The game counts as F.')))return;await ksSend('/api/profile/krisenspiel','DELETE');return}
  if(B.ksclear){if(!confirm(t('Alle Spieldaten löschen: laufendes Spiel, bisherige Spiele und Erfolge?','Delete all game data: the running game, past games and achievements?')))return;
    if(await ksSend('/api/profile/krisenspiel/daten','DELETE')){await ksLoad();ksSay(t('Gelöscht.','Deleted.'))}}})}
document.body.addEventListener('change',e=>{if(e.target.matches('#ksview .ksboard'))ksSend('/api/profile/krisenspiel/bestenliste','POST',{zeigen:e.target.value}).then(d=>{if(d)ksSay(t('Gespeichert.','Saved.'))})});
