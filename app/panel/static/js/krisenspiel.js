// IT-Krisenspiel (krisenspiel.py, plan krisenspiel/plan.md, Paket 1): a page of its own in the menu. „Spiel“ is the
// crisis dashboard: the values on top, the systems with their state, the chronicle and the moves the panel offers;
// „Neues Spiel“ picks scenario, level and seed; „Inspector“ shows every step of a move (input, fixed rule, rolls from
// the seed, narrator); „Bisherige Spiele“ the results, achievements and „Meine Daten löschen“. Every value comes from
// the panel; texts from the scenarios and the narrator are only ever text (esc), never markup.
const KS={data:null,msg:'',err:false,busy:false,seq:0,turn:-1};
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
  if(r.ok){KS.data=d;KS.err=false;KS.msg=''}else{KS.msg=errSay(r.status,d.detail,'');KS.err=true}ksDraw()}
function ksDraw(){const w=$('ksview');if(w)ksPaint(w)}
function ksSay(x,err){KS.msg=String(x||'').slice(0,300);KS.err=!!err;const m=document.querySelector('#ksview .ksmsg');if(m){m.className='ksmsg '+(err?'err':'mut');m.textContent=KS.msg}}
async function ksSend(p,method,b){if(KS.busy)return null;KS.busy=true;document.querySelectorAll('#ksview button').forEach(x=>x.disabled=true);
  const o={method};if(b)Object.assign(o,{headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({lang:L==='en'?'en':'de'},b))});
  const {r,d}=await apiTry(p,o);KS.busy=false;KS.seq++;   // a read that started before this answer is older: dropped
  if(!r.ok){if(r.status===409)await ksLoad();ksDraw();ksSay(r.status===409?t('Das Spiel war schon einen Zug weiter; jetzt ist es aktuell.','The game was a move further already; it is current now.'):d.detail,true);return null}
  if(d&&d.on)KS.data=d;ksDraw();return d}
function ksPaint(w){const D=KS.data,tab=w.dataset.tab;
  if(!D){w.innerHTML=`<div class="ld-empty mut">${esc(KS.err?KS.msg:t('Lade das Krisenspiel …','Loading the crisis game …'))}</div>`;return}
  w.innerHTML=(tab==='neu'?ksNew(D):tab==='inspector'?ksInspector(D):tab==='bisher'?ksPast(D):ksGame(D))+`<div class="ksmsg ${KS.err?'err':'mut'}" role="status">${esc(KS.msg)}</div>`}
function ksBar(label,val,max,shown,bad){const pc=Math.max(0,Math.min(100,Math.round(100*val/(max||1))));
  return `<div class="ks-met${bad?' bad':''}"><span>${esc(label)}</span><b>${esc(shown)}</b><i><em style="width:${pc}%"></em></i></div>`}
function ksGame(D){const g=D.spiel;
  if(!g)return `<div class="ld-empty mut">${esc(t('Noch kein Spiel. Unter „Neues Spiel“ wählst du ein Szenario.','No game yet. Pick a scenario under "New game".'))}</div><div class="row"><button type="button" class="b p" data-kstab="neu">${esc(t('Neues Spiel','New game'))}</button></div>`;
  const m=g.m,stufe=(D.stufen.find(s=>s.id===g.stufe)||{name:[g.stufe,g.stufe]}).name;
  const head=`<div class="ks-head"><div><h3>${esc(ksP(g.titel))}</h3><div class="mut">${esc(ksP(stufe))} · Seed ${esc(String(g.seed))} · ${esc(t(`Zug ${g.zug} · Minute ${g.min}`,`Move ${g.zug} · minute ${g.min}`))}</div></div>
    ${g.ende?'':`<button type="button" class="b" data-ksgive="1">${esc(t('Aufgeben','Give up'))}</button>`}</div>`;
  const mets=`<div class="ks-mets">${ksBar(t('Zeit','Time'),m.zeit,m.zeit_start,t(`${m.zeit} min`,`${m.zeit} min`),m.zeit*4<m.zeit_start)}
    ${ksBar(t('Stress','Stress'),m.stress,100,m.stress+' %',m.stress>=75)}${ksBar(t('Vertrauen','Trust'),m.vertrauen,100,m.vertrauen+' %',m.vertrauen<30)}
    ${ksBar(t('Moral','Morale'),m.moral,100,m.moral+' %',m.moral<30)}${ksBar(t('Budget','Budget'),m.budget,m.budget_start,ksEur(m.budget),m.budget*5<m.budget_start)}
    <div class="ks-met dmg"><span>${esc(t('Schaden','Damage'))}</span><b>${esc(ksEur(m.kosten))}</b></div></div>`;
  const assets=`<div class="ks-assets">${g.assets.map(a=>{const s=KSSTAT[a.status]||[a.status,a.status,''];
    return `<div class="ks-asset ${s[2]}"><b>${esc(a.name)}</b><small class="mut">${esc(ksP(a.typ))}</small><span class="pill ${s[2]}">${esc(t(s[0],s[1]))}</span><small>${esc(ksP(a.details))}</small></div>`}).join('')}</div>`;
  const chron=`<div class="ks-chron" aria-live="polite">${g.chronik.slice().reverse().map(c=>`<div class="ks-ev ${esc(c.art)}"><small class="mut">${esc(t(...(KSART[c.art]||[c.art,c.art])))} · ${esc(t('Minute ','minute '))}${c.min}</small><p>${esc(c.erzaehlt&&c.lang===(L==='en'?'en':'de')?c.erzaehlt:ksP(c.text))}</p>${c.erzaehlt&&c.lang===(L==='en'?'en':'de')?`<details><summary>${esc(t('Feste Fakten','Fixed facts'))}</summary><small>${esc(ksP(c.text))}</small></details>`:''}</div>`).join('')}</div>`;
  const cost=a=>Object.entries(a.kosten).map(([k,v])=>k==='budget'?ksEur(v):k==='zeit'?v+' min':(v>0?'+':'')+v+' '+t({stress:'Stress',vertrauen:'Vertrauen',moral:'Moral'}[k]||k,{stress:'stress',vertrauen:'trust',moral:'morale'}[k]||k)).join(' · ');
  const acts=g.ende?ksEnd(D,g):`<h4>${esc(t('Deine Züge','Your moves'))}</h4><div class="ks-acts">${g.aktionen.map(a=>`<button type="button" class="b ks-act" data-ksmove="${esc(a.id)}"${a.frei?'':' disabled'} title="${esc(a.frei?'':ksP(a.warum))}"><b>${esc(ksP(a.label))}</b><small>${esc(cost(a))}</small></button>`).join('')}</div>`;
  return head+mets+`<div class="ks-grid"><div>${assets}${acts}</div><div><h4>${esc(t('Chronik','Chronicle'))}</h4>${chron}</div></div>`}
function ksEnd(D,g){const e=g.ende,names=Object.fromEntries(D.erfolge.map(x=>[x.id,x.name]));
  return `<div class="ks-end"><div class="ks-note ${KSNOTE[e.note]||''}">${esc(e.note)}</div><div><h4>${esc(t(`${e.punkte} von 100 Punkten`,`${e.punkte} of 100 points`))}</h4>
    <ul class="facts small">${e.gruende.map(x=>`<li><span>${esc(ksP(x))}</span></li>`).join('')}</ul>
    ${(e.erfolge||[]).length?`<div>${e.erfolge.map(k=>`<span class="pill ok">${esc(ksP(names[k]||[k,k]))}</span>`).join(' ')}</div>`:''}
    <div class="row"><button type="button" class="b p" data-ksagain="${esc(g.szenario)}" data-ksstufe="${esc(g.stufe)}" data-ksseed="${esc(String(g.seed))}">${esc(t('Nochmal mit diesem Seed','Again with this seed'))}</button><button type="button" class="b" data-kstab="neu">${esc(t('Neues Spiel','New game'))}</button></div></div></div>`}
function ksNew(D){const run=D.spiel&&!D.spiel.ende;
  return `<h3>${esc(t('Neues Spiel','New game'))}</h3>${run?`<div class="mut">${esc(t('Ein neues Spiel ersetzt das laufende.','A new game replaces the running one.'))}</div>`:''}
    <div class="ks-pick">${D.szenarien.map((s,i)=>`<label class="ks-sz"><input type="radio" name="kssz" value="${esc(s.id)}"${i?'':' checked'}><b>${esc(ksP(s.titel))}</b><small>${esc(ksP(s.kurz))}</small><small class="mut">${esc(t(`${s.systeme} Systeme`,`${s.systeme} systems`))}${D.stats.beste[s.id]?esc(t(` · bisher bestes Ergebnis ${D.stats.beste[s.id]} Punkte`,` · best so far ${D.stats.beste[s.id]} points`)):''}</small></label>`).join('')}</div>
    <div class="row"><label>${esc(t('Stufe','Level'))} <select class="ksstufe">${D.stufen.map(s=>`<option value="${esc(s.id)}"${s.id==='normal'?' selected':''}>${esc(ksP(s.name))} (${s.zeit} min)</option>`).join('')}</select></label>
    <label>Seed <input class="ksseed" type="number" min="0" max="999999" inputmode="numeric" placeholder="${esc(t('zufällig','random'))}"></label></div>
    <div class="mut">${esc(t('Gleicher Seed, gleiche Züge: gleiches Spiel. So könnt ihr euch vergleichen.','Same seed, same moves: the same game. That way you can compare.'))}</div>
    <div class="row"><button type="button" class="b p" data-ksnew="1">${esc(t('Spiel starten','Start the game'))}</button></div>`}
function ksInspector(D){const g=D.spiel;if(!g)return `<div class="ld-empty mut">${esc(t('Noch kein Spiel.','No game yet.'))}</div>`;
  return `<h3>${esc(t('Inspector','Inspector'))}</h3><div class="mut">${esc(t('Jeder Zug Schritt für Schritt: was du gewählt hast, welche feste Regel gegriffen hat, welche Würfe aus dem Seed kamen und was das Sprachmodell erzählt hat. Werte ändert nur die Regel.','Every move step by step: what you chose, which fixed rule applied, which rolls came from the seed and what the language model told. Only the rule changes values.'))}</div>
    ${g.trace.slice().reverse().map(z=>`<details class="ks-tr"${z.zug===g.zug?' open':''}><summary>${esc(t(`Zug ${z.zug}`,`Move ${z.zug}`))} · ${z.steps.length} ${esc(t('Schritte','steps'))}</summary>
      <ol>${z.steps.map(s=>`<li class="ks-st ${esc(s.art)}"><b>${esc(t(...(KSSTEP[s.art]||[s.art,s.art])))}</b> · ${esc(ksP(s.titel))}${s.ms?` <small class="mut">${s.ms} ms</small>`:''}<pre>${esc(JSON.stringify(s.daten,null,1))}</pre></li>`).join('')}</ol></details>`).join('')}`}
function ksPast(D){const st=D.stats,have=D.erfolge.filter(e=>e.t).length;
  return `<h3>${esc(t('Bisherige Spiele','Past games'))}</h3><div class="mut">${esc(t(`${st.gespielt} gespielt · ${st.gewonnen} gewonnen · ${have} von ${D.erfolge.length} Erfolgen`,`${st.gespielt} played · ${st.gewonnen} won · ${have} of ${D.erfolge.length} achievements`))}</div>
    <ul class="facts">${D.verlauf.map(v=>`<li><span><b>${esc(ksP(v.titel))}</b> · ${esc(ksWhen(v.t))}<br><small class="mut">${esc(t(`${v.zuege} Züge · ${v.minuten} min · Seed ${v.seed}`,`${v.zuege} moves · ${v.minuten} min · seed ${v.seed}`))}</small></span><b class="ks-note small ${KSNOTE[v.note]||''}">${esc(v.note)}</b></li>`).join('')||`<li><span class="mut">${esc(t('Noch keine.','None yet.'))}</span></li>`}</ul>
    <h4>${esc(t('Erfolge','Achievements'))}</h4><div class="ks-ach">${D.erfolge.map(e=>`<div class="ks-a${e.t?' on':''}"><b>${esc(ksP(e.name))}</b><small>${esc(ksP(e.text))}</small>${e.t?`<small class="mut">${esc(ksWhen(e.t))}</small>`:''}</div>`).join('')}</div>
    <div class="row"><button type="button" class="b" data-ksclear="1">${esc(t('Meine Spieldaten löschen','Delete my game data'))}</button></div>`}
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#ksview [data-ksmove],#ksview [data-ksnew],#ksview [data-ksagain],#ksview [data-ksgive],#ksview [data-ksclear],#ksview [data-kstab]');if(!b)return;const B=b.dataset;
  const go=k=>{icTabSet('spiel',k);ksOpen()};
  if(B.kstab){go(B.kstab);return}
  if(B.ksmove){await ksSend('/api/profile/krisenspiel/zug','POST',{aktion:B.ksmove,zug:KS.data.spiel.zug});return}
  if(B.ksnew||B.ksagain){const w=$('ksview');let body;
    if(B.ksagain)body={szenario:B.ksagain,stufe:B.ksstufe,seed:+B.ksseed};
    else{const sz=w.querySelector('input[name=kssz]:checked'),sd=w.querySelector('.ksseed').value.trim();body={szenario:sz&&sz.value,stufe:w.querySelector('.ksstufe').value};
      if(sd!==''){const n=+sd;if(!Number.isInteger(n)||n<0||n>999999){ksSay(t('Der Seed ist eine Zahl von 0 bis 999999.','The seed is a number from 0 to 999999.'),true);return}body.seed=n}}
    if(await ksSend('/api/profile/krisenspiel/neu','POST',body))go('spiel');return}
  if(B.ksgive){if(!confirm(t('Aufgeben? Das Spiel zählt als F.','Give up? The game counts as F.')))return;await ksSend('/api/profile/krisenspiel','DELETE');return}
  if(B.ksclear){if(!confirm(t('Alle Spieldaten löschen: laufendes Spiel, bisherige Spiele und Erfolge?','Delete all game data: the running game, past games and achievements?')))return;
    if(await ksSend('/api/profile/krisenspiel/daten','DELETE')){await ksLoad();ksSay(t('Gelöscht.','Deleted.'))}}})}
