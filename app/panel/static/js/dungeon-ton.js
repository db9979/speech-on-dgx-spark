// KI-Dungeon-Master: music, sounds and the d20 at the table (dungeon_musik.py, plan „5f“, Dominik 2026-10-23 „1a, 2a, 3a, 4a“).
// The panel names everything (field „musik“ of the round: the mood and its pieces, the place's sound, the turns of the
// last victory and door; the log's throws and events), this file only plays it: a quiet loop that fades into the next
// piece of the same mood (never one of the last three), every sound made here with WebAudio (no files), the d20 rolls
// 0.8 s and always stops on the panel's number. Each device keeps its own choice (music, sounds, volume).
// „👎 Nervt“ (Dominik 2026-10-24): any seat marks the piece playing, it is never played again, the night makes a new one.
const DMT={ctx:null,out:null,amb:null,ambK:'',noise:null,el:[null,null],g:[null,null],cur:-1,id:'',st:'',last:[],urls:{},v:null,mode:'',
  seen:{p:null,g:null},sieg:{p:null,g:null},tuer:{p:null,g:null},rid:{p:'',g:''},busy:false,duck:1};
const DMT_FADE=12,DMT_LAUT=20,DMT_URLS=4;
function dmtPref(k,d){try{const x=localStorage.getItem('dm-'+k);return x===null?d:x}catch{return d}}
function dmtSet(k,x){try{localStorage.setItem('dm-'+k,String(x))}catch{}}
const dmtMusik=()=>dmtPref('musik','1')==='1',dmtFx=()=>dmtPref('fx','1')==='1',dmtLaut=()=>Math.max(0,Math.min(100,+dmtPref('laut',DMT_LAUT)||0));
function dmtCtx(){if(DMT.ctx)return DMT.ctx;const C=window.AudioContext||window.webkitAudioContext;if(!C)return null;
  DMT.ctx=new C();DMT.out=DMT.ctx.createGain();DMT.out.connect(DMT.ctx.destination);
  const n=DMT.ctx.createBuffer(1,DMT.ctx.sampleRate*2,DMT.ctx.sampleRate),d=n.getChannelData(0);for(let i=0;i<d.length;i++)d[i]=Math.random()*2-1;DMT.noise=n;return DMT.ctx}
// the browser lets sound start only after a tap: the first tap at the table wakes it
document.addEventListener('pointerdown',e=>{if(e.target.closest&&e.target.closest('.dm')){const c=dmtCtx();if(c&&c.state==='suspended')c.resume()}},true);
const dmtNow=()=>DMT.ctx.currentTime;
function dmtGain(v,t0,a,d,to){const g=DMT.ctx.createGain();g.gain.setValueAtTime(0.0001,t0);g.gain.exponentialRampToValueAtTime(Math.max(0.0002,v),t0+a);g.gain.exponentialRampToValueAtTime(0.0001,t0+a+d);g.connect(to||DMT.out);return g}
function dmtTone(f,t0,a,d,v,type,to){const o=DMT.ctx.createOscillator();o.type=type||'sine';o.frequency.setValueAtTime(f,t0);o.connect(dmtGain(v,t0,a,d,to));o.start(t0);o.stop(t0+a+d+.05);return o}
function dmtNoise(t0,len,v,kind,f,q){const s=DMT.ctx.createBufferSource();s.buffer=DMT.noise;const b=DMT.ctx.createBiquadFilter();b.type=kind||'bandpass';b.frequency.value=f||2000;b.Q.value=q||1;
  s.connect(b);b.connect(dmtGain(v,t0,.004,len));s.start(t0,Math.random()*1.5);s.stop(t0+len+.05)}
// the sounds, all made here (3a): name -> function(volume)
const DMT_FX={
  wuerfel:(v,w)=>{const t=dmtNow();[0,.13,.29,.41,.55,.66].forEach((x,i)=>dmtNoise(t+x+Math.random()*.03,.05,v*(i<5?.5:.8),'bandpass',1800+Math.random()*1800,3));
    if(w===20){dmtTone(1320,t+.75,.01,.5,v*.35);dmtTone(1760,t+.82,.01,.6,v*.3)}else if(w===1)dmtTone(98,t+.72,.01,.5,v*.6,'triangle')},
  tuer:v=>{const t=dmtNow(),o=DMT.ctx.createOscillator(),b=DMT.ctx.createBiquadFilter();o.type='sawtooth';o.frequency.setValueAtTime(90,t);
    for(let i=1;i<9;i++)o.frequency.linearRampToValueAtTime(80+Math.random()*70,t+i*.1);b.type='bandpass';b.frequency.value=900;b.Q.value=4;o.connect(b);b.connect(dmtGain(v*.5,t,.08,.9));o.start(t);o.stop(t+1.05);
    dmtNoise(t+1,.25,v*.6,'lowpass',300)},
  klingen:v=>{const t=dmtNow();[2400,3170,4130,5210].forEach((f,i)=>dmtTone(f,t,.002,.5-i*.08,v*.12));dmtNoise(t,.08,v*.4,'highpass',3000)},
  treffer:v=>{const t=dmtNow(),o=dmtTone(140,t,.003,.25,v*.6,'sine');o.frequency.exponentialRampToValueAtTime(45,t+.25);dmtNoise(t,.12,v*.5,'lowpass',500)},
  heilung:v=>{const t=dmtNow();[523,659,784,1047].forEach((f,i)=>dmtTone(f,t+i*.09,.03,.6,v*.18))},
  muenzen:v=>{const t=dmtNow();for(let i=0;i<6;i++)dmtTone(2200+Math.random()*1600,t+i*.07+Math.random()*.03,.002,.18,v*.12)},
  zauber:v=>{const t=dmtNow(),o=dmtTone(600,t,.15,1,v*.15);o.frequency.exponentialRampToValueAtTime(1800,t+1);dmtTone(1200,t+.1,.2,.9,v*.08,'triangle')},
  klack:v=>{const t=dmtNow();dmtNoise(t,.04,v*.7,'bandpass',1400+Math.random()*900,4);dmtTone(180+Math.random()*60,t,.002,.08,v*.25,'triangle')},
  dran:v=>{const t=dmtNow();dmtTone(784,t,.01,.18,v*.12,'sine');dmtTone(1175,t+.12,.01,.3,v*.1,'sine')},
  stufe:v=>{const t=dmtNow();[392,494,587,784].forEach((f,i)=>dmtTone(f,t+i*.12,.02,i===3?.9:.25,v*.14,'triangle'))}};
function dmtPlay(k,w){if(!dmtFx())return;const c=dmtCtx();if(!c||c.state!=='running')return;try{DMT_FX[k](dmtLaut()/100,w)}catch{}}
// the place's sound in the background: a filtered noise loop (regen, wind, feuer, wasser), quiet under the music
function dmtAmb(k){if(!dmtFx())k='';if(k===DMT.ambK)return;DMT.ambK=k;if(DMT.amb){const a=DMT.amb;a.g.gain.setTargetAtTime(0.0001,dmtNow(),.6);setTimeout(()=>{try{a.s.stop();clearInterval(a.tick)}catch{}},2500);DMT.amb=null}
  const c=dmtCtx();if(!k||!c)return;const s=c.createBufferSource();s.buffer=DMT.noise;s.loop=true;const f=c.createBiquadFilter(),g=c.createGain();
  const set={regen:['highpass',900,.12],wind:['lowpass',420,.18],feuer:['lowpass',800,.09],wasser:['lowpass',360,.16]}[k]||['lowpass',500,.1];
  f.type=set[0];f.frequency.value=set[1];g.gain.value=0.0001;s.connect(f);f.connect(g);g.connect(DMT.out);s.start();
  g.gain.setTargetAtTime(set[2]*dmtLaut()/100,dmtNow(),1.2);const a={s,g,k,lvl:set[2],tick:0};
  if(k==='wind'){const l=c.createOscillator(),lg=c.createGain();l.frequency.value=.12;lg.gain.value=220;l.connect(lg);lg.connect(f.frequency);l.start()}
  if(k==='feuer')a.tick=setInterval(()=>{if(DMT.ctx.state==='running'&&Math.random()<.5)dmtNoise(dmtNow(),.02,dmtLaut()/100*.25,'highpass',2500)},260);
  if(k==='wasser')a.tick=setInterval(()=>{if(DMT.ctx.state==='running'&&Math.random()<.3){const t=dmtNow(),o=dmtTone(1300,t,.002,.12,dmtLaut()/100*.06);o.frequency.exponentialRampToValueAtTime(600,t+.12)}},700);
  DMT.amb=a}
// ---------------------------------------------------------------- music: two players that fade into each other
async function dmtUrl(id){if(DMT.urls[id])return DMT.urls[id];let r;
  if(DMT.mode==='p')r=await api(`/api/profile/dungeon/${DMT.v.rid}/musik/${id}`);
  else r=await /*raw: public route of a guest seat, api() would open the login on a 401*/fetch('/api/dungeon/musik',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,s:id})});
  if(!r.ok)return '';const u=URL.createObjectURL(await r.blob());DMT.urls[id]=u;const ks=Object.keys(DMT.urls);
  for(const k of ks.slice(0,Math.max(0,ks.length-DMT_URLS)))if(k!==DMT.id){URL.revokeObjectURL(DMT.urls[k]);delete DMT.urls[k]}return u}
function dmtPick(list){const fresh=list.filter(x=>!DMT.last.includes(x));const a=fresh.length?fresh:list;return a[Math.floor(Math.random()*a.length)]||''}
function dmtLevel(){return dmtLaut()/100*DMT.duck}
async function dmtStart(list,once){if(DMT.busy)return;const c=dmtCtx();if(!c||!list.length)return;DMT.busy=true;
  try{const id=dmtPick(list),u=await dmtUrl(id);if(!u)return;const i=DMT.cur===0?1:0,el=new Audio(u);el.preload='auto';
    const src=c.createMediaElementSource(el),g=c.createGain();g.gain.value=0.0001;src.connect(g);g.connect(DMT.out);
    const old=DMT.cur>=0?{el:DMT.el[DMT.cur],g:DMT.g[DMT.cur]}:null;DMT.el[i]=el;DMT.g[i]=g;DMT.cur=i;DMT.id=id;DMT.once=!!once;
    DMT.last=[id,...DMT.last.filter(x=>x!==id)].slice(0,3);await el.play();g.gain.setTargetAtTime(dmtLevel(),dmtNow(),DMT_FADE/4);
    if(old&&old.el){old.g.gain.setTargetAtTime(0.0001,dmtNow(),DMT_FADE/4);setTimeout(()=>{try{old.el.pause()}catch{}},DMT_FADE*1000+500)}
    el.ontimeupdate=()=>{if(DMT.el[DMT.cur]===el&&el.duration&&el.currentTime>el.duration-DMT_FADE&&!el.dmtNext){el.dmtNext=1;dmtNext()}}}
  catch{}finally{DMT.busy=false}}
function dmtNext(){const m=DMT.v&&DMT.v.musik;if(!m||!m.an||!dmtMusik())return;dmtStart(m.stuecke||[])}
function dmtStop(){DMT.el.forEach((el,i)=>{if(el){try{DMT.g[i].gain.setTargetAtTime(0.0001,dmtNow(),.4)}catch{}setTimeout(()=>{try{el.pause()}catch{}},1200)}});DMT.cur=-1;DMT.id='';DMT.st=''}
// ---------------------------------------------------------------- the table (called by dmTable after each drawing)
function dmtBar(v){const m=v.musik||{},on=dmtMusik(),n=(m.stuecke||[]).length,i=(m.stuecke||[]).indexOf(DMT.id);
  const txt=m.an?(n?`♪ ${m.name}${on&&i>=0?' · '+t('Stück','piece')+' '+(i+1)+' '+t('von','of')+' '+n:''}`:`♪ ${m.name} · ${t('Musik wird vorbereitet …','music is being prepared …')}`):'';
  return `<div class="dm-ton">${txt?`<span class="dm-eq${on&&DMT.id?' on':''}" aria-hidden="true"><b></b><b></b><b></b><b></b></span><span class="dm-tontxt">${esc(txt)}</span>`:''}<span class="dm-tonsp"></span>
    ${m.an?`<button type="button" class="b${on?' p':''}" data-dmton="musik" aria-pressed="${on}">${esc(t('Musik','Music'))}</button>`:''}<button type="button" class="b${dmtFx()?' p':''}" data-dmton="fx" aria-pressed="${dmtFx()}">${esc(t('Geräusche','Sounds'))}</button>
    <input type="range" class="dm-laut" min="0" max="100" step="5" value="${dmtLaut()}" aria-label="${esc(t('Lautstärke','Volume'))}">${m.an&&on&&n>1?`<button type="button" class="b" data-dmton="weiter" title="${esc(t('Nächstes Stück','Next piece'))}" aria-label="${esc(t('Nächstes Stück','Next piece'))}">⏭</button>`:''}${m.an&&on&&DMT.id?`<button type="button" class="b" data-dmton="nervt" title="${esc(t('Nervt: nie mehr spielen, nachts kommt ein neues','Annoying: never play it again, a new one comes at night'))}" aria-label="${esc(t('Stück nervt','Piece is annoying'))}">👎</button>`:''}</div>`}
// „👎 Nervt“: the panel marks the piece for every table, here it leaves the list at once and the next one fades in
async function dmtNervt(){const id=DMT.id,v=DMT.v;if(!id||!v)return;
  try{if(DMT.mode==='p'){const {r}=await apiTry(`/api/profile/dungeon/${v.rid}/musik/${id}/nervt`,xjson('POST',{}));if(!r.ok)return}
    else await dgPub('/api/dungeon/musik/nervt',{code:DG.code,s:id})}catch{return}
  const m=v.musik||{};['stuecke','sieg'].forEach(k=>{if(m[k])m[k]=m[k].filter(x=>x!==id)});
  if(DMT.urls[id]){URL.revokeObjectURL(DMT.urls[id]);delete DMT.urls[id]}sayToast(t('Kommt nicht wieder, nachts gibt es ein neues','Will not come again, a new one comes at night'));
  if((m.stuecke||[]).length)dmtStart(m.stuecke);else dmtStop()}
const DMT_EVENT={folge:e=>e.was==='heilung'?'heilung':'treffer',beute:()=>'muenzen',handel:()=>'muenzen',zauber:()=>'zauber',stufe:()=>'stufe'};
function dmtRoll(w,news){const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dice=[...w.querySelectorAll('.dm-feed .dm-wurf .dm-d20')].slice(-news.length);
  dice.forEach(d=>{const real=d.textContent;if(reduce)return;d.classList.add('dm-rollt');let k=0;const iv=setInterval(()=>{d.textContent=String(1+Math.floor(Math.random()*20));if(++k>=12){clearInterval(iv);d.textContent=real;d.classList.remove('dm-rollt')}},66)})}
window.dmTon=(w,v,mode)=>{DMT.v=v;DMT.mode=mode;const m=v.musik||{an:false};
  if(DMT.rid[mode]!==v.rid){DMT.rid[mode]=v.rid;DMT.seen[mode]=null;DMT.sieg[mode]=null;DMT.tuer[mode]=null}
  const head=w.querySelector('.dm-head .dm-htitle');if(head)head.insertAdjacentHTML('afterend',dmtBar(v));   // in the head, no own row (Punkt 9)
  // the log's new entries since the last drawing: the dice roll, the events sound (the first drawing only counts)
  const log=v.log||[],key=log.length?JSON.stringify(log[log.length-1]):'';
  if(DMT.seen[mode]!==null&&DMT.seen[mode]!==key){let i=log.length-1;while(i>=0&&JSON.stringify(log[i])!==DMT.seen[mode])i--;
    const news=i>=0?log.slice(i+1):[],wuerfe=news.filter(e=>e.art==='wurf'&&!(window.dmWurfGesehen&&dmWurfGesehen(v,e)));   // a die thrown in the wait rolls no more (dungeonwarten.js)
    if(wuerfe.length){dmtRoll(w,wuerfe);dmtPlay('wuerfel',wuerfe[wuerfe.length-1].w)}
    const ev=[...new Set(news.map(e=>DMT_EVENT[e.art]&&DMT_EVENT[e.art](e)).filter(Boolean))];ev.forEach((k,i)=>setTimeout(()=>dmtPlay(k),(wuerfe.length?900:0)+i*400))}
  DMT.seen[mode]=key;
  if(DMT.tuer[mode]!==null&&m.tuer_zug>DMT.tuer[mode])dmtPlay('tuer');DMT.tuer[mode]=m.tuer_zug;
  dmtAmb(v.status==='laeuft'?m.klang||'':'');
  if(!m.an||!dmtMusik()||v.status!=='laeuft'){if(DMT.cur>=0)dmtStop();DMT.sieg[mode]=m.sieg_zug;return}
  if(DMT.sieg[mode]!==null&&m.sieg_zug>DMT.sieg[mode]&&(m.sieg||[]).length){DMT.sieg[mode]=m.sieg_zug;DMT.st=m.st;dmtStart(m.sieg,true);return}
  DMT.sieg[mode]=m.sieg_zug;
  if(m.st!==DMT.st||DMT.cur<0){if((m.stuecke||[]).length){DMT.st=m.st;dmtStart(m.stuecke)}}};
// the bar's buttons and the volume, and a reading-aloud turn (dungeon.js DMA) makes the music quieter
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmton]');if(!b)return;const k=b.dataset.dmton,c=dmtCtx();if(c&&c.state==='suspended')c.resume();
  if(k==='musik'){dmtSet('musik',dmtMusik()?'0':'1');if(!dmtMusik())dmtStop()}
  else if(k==='fx'){dmtSet('fx',dmtFx()?'0':'1');if(!dmtFx())dmtAmb('')}
  else if(k==='weiter'){dmtNext();return}
  else if(k==='nervt'){dmtNervt();return}
  const w=b.closest('.dm');if(w&&DMT.v){const old=w.querySelector('.dm-ton');if(old)old.remove();window.dmTon(w,DMT.v,DMT.mode)}});
document.body.addEventListener('input',e=>{const r=e.target.closest('.dm-laut');if(!r)return;dmtSet('laut',r.value);
  if(DMT.cur>=0&&DMT.g[DMT.cur])DMT.g[DMT.cur].gain.setTargetAtTime(dmtLevel(),dmtNow(),.1);if(DMT.amb)DMT.amb.g.gain.setTargetAtTime(DMT.amb.lvl*dmtLaut()/100,dmtNow(),.2)});
setInterval(()=>{if(!DMT.ctx)return;const table=document.querySelector('.dm .dm-ton');
  if(!table||!table.offsetParent){if(DMT.cur>=0)dmtStop();if(DMT.ambK)dmtAmb('');return}
  const reading=['p','g'].some(k=>typeof DMA!=='undefined'&&DMA[k]&&DMA[k].el&&!DMA[k].el.paused),d=reading?.35:1;
  if(d!==DMT.duck){DMT.duck=d;if(DMT.cur>=0&&DMT.g[DMT.cur])DMT.g[DMT.cur].gain.setTargetAtTime(dmtLevel(),dmtNow(),.3)}
  const el=DMT.cur>=0&&DMT.el[DMT.cur];if(el&&el.ended&&DMT.once){DMT.once=false;DMT.st='';dmtNext()}},700);
// the admin's card under Funktionen → Dungeon-Master → Regeln anpassen: on/off, pieces per field, megabytes, the fields
async function dmMusikAdm(){const c=$('dmmusikadm');if(!c)return;const {r,d}=await apiTry('/api/admin/dungeon/musik?lang='+(L==='en'?'en':'de'));if(!r.ok){c.textContent='';return}dmMusikDraw(d,'')}
function dmMusikDraw(d,err){const c=$('dmmusikadm');if(!c)return;const s=d.einstellung,L2=d.live;
  c.innerHTML=`<h3 class="sec">${esc(t('Musik am Tisch','Music at the table'))}</h3>
    <div class="pintro">${esc(t('Das eigene Musikmodell macht Stücke je Welt und Stimmung, beim Start einer Runde und vor jedem neuen Akt im Voraus, nachts bis zur Zahl je Feld. Sprache und andere schwere Aufträge gehen vor. Geräusche und Würfel gibt es immer, auch ohne Musik.','The own music model makes pieces per world and mood, ahead when a round starts and before each new act, at night up to the number per field. Speech and other heavy jobs go first. Sounds and dice are always there, even without music.'))}</div>
    ${d.installiert?'':`<div class="ic-note"><div class="ic-mid"><b>${esc(t('Kein Musikmodell installiert.','No music model installed.'))}</b><span>${esc(t('Ohne Musikmodell gibt es am Tisch nur Geräusche und Würfel.','Without a music model the table has sounds and dice only.'))}</span></div></div>`}
    <div class="dm-two"><div><label for="dmmusikn">${esc(t('Stücke je Welt und Stimmung','Pieces per world and mood'))}</label><input id="dmmusikn" type="number" min="${d.spanne.stuecke[0]}" max="${d.spanne.stuecke[1]}" value="${s.stuecke}"></div>
      <div><label for="dmmusikmb">${esc(t('Speicherplatz (MB)','Storage (MB)'))}</label><input id="dmmusikmb" type="number" min="${d.spanne.mb[0]}" max="${d.spanne.mb[1]}" step="50" value="${s.mb}"></div></div>
    ${s.mb<d.mb_noetig?`<small class="dm-wrest">${esc(t(`Für ${s.stuecke} Stücke je Feld braucht der Vorrat etwa ${d.mb_noetig} MB; mit ${s.mb} MB gehen die meistgespielten früher.`,`For ${s.stuecke} pieces per field the store needs about ${d.mb_noetig} MB; with ${s.mb} MB the most played go sooner.`))}</small>`:''}
    <label class="chk"><input type="checkbox" id="dmmusikan"${s.an?' checked':''}> ${esc(t('Musik vorbereiten','Prepare music'))}</label>
    <div class="dm-mfeld"><i></i>${d.stimmungen.map(m=>`<b title="${esc(m.name)}">${esc(m.name)}</b>`).join('')}${d.felder.map(f=>`<b>${esc((f.zeichen?f.zeichen+' ':'')+f.name)}</b>${d.stimmungen.map(m=>`<span class="${f.n[m.id]>=s.stuecke?'ok':'warn'}">${f.n[m.id]}${f.wartet.includes(m.id)?' ⏳':''}</span>`).join('')}`).join('')}</div>
    ${(d.markiert||[]).length?`<h4>${esc(t(`${d.markiert.length} markiert (👎 Nervt)`,`${d.markiert.length} marked (👎 annoying)`))}</h4><div class="pintro">${esc(t('Diese Stücke spielt kein Tisch mehr; nachts macht der Spark neue. Bis dahin lässt sich eine Markierung zurücknehmen.','No table plays these pieces any more; at night the Spark makes new ones. Until then a mark can be taken back.'))}</div>
      ${d.markiert.map(x=>`<div class="setrow"><div class="lbl"><b>${esc(x.welt+' · '+x.st)}</b><span>${esc(t(`${x.s} s · ${x.nervt}× markiert`,`${x.s} s · marked ${x.nervt}×`))}</span></div><button type="button" class="b" data-dmmusik="zurueck" data-id="${esc(x.id)}">${esc(t('Zurücknehmen','Take back'))}</button></div>`).join('')}`:''}
    <small class="mut">${esc(t(`${L2.stuecke} Stücke, ${L2.mb} MB · heute ${L2.gemacht} gemacht, ${L2.weg} nicht gekommen`,`${L2.stuecke} pieces, ${L2.mb} MB · today ${L2.gemacht} made, ${L2.weg} did not come`))}${L2.macht?' · '+esc(t('macht gerade ein Stück','making a piece now')):''}</small>
    ${err?`<div class="err">${esc(err)}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmmusik="save">${esc(t('Speichern','Save'))}</button><button type="button" class="b" data-dmmusik="jetzt"${s.an&&d.installiert?'':' disabled'}>${esc(t('Musik jetzt vorbereiten','Prepare music now'))}</button><button type="button" class="b danger" data-dmmusik="weg">${esc(t('Alle Stücke löschen','Delete all pieces'))}</button></div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmmusikadm [data-dmmusik]');if(!b)return;const k=b.dataset.dmmusik,q='?lang='+(L==='en'?'en':'de');
  if(k==='weg'&&b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich alle löschen?','Really delete all?');return}
  if(k==='zurueck'){const {r,d}=await apiTry(`/api/admin/dungeon/musik/${encodeURIComponent(b.dataset.id)}/zurueck${q}`,{method:'POST'});if(r.ok){dmMusikDraw(d,'');sayToast(t('Spielt wieder','Plays again'))}return}
  const o=k==='save'?{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({an:$('dmmusikan').checked,stuecke:+$('dmmusikn').value,mb:+$('dmmusikmb').value})}:k==='jetzt'?{method:'POST'}:{method:'DELETE'};
  const {r,d}=await apiTry('/api/admin/dungeon/musik'+(k==='jetzt'?'/jetzt':'')+q,o);if(r.ok){dmMusikDraw(d,'');if(k==='save')sayToast(t('Gespeichert','Saved'));return}
  const g=await apiTry('/api/admin/dungeon/musik'+q);if(g.r.ok)dmMusikDraw(g.d,errSay(r.status,d.detail,''))});
// ---------------------------------------------------------------- the own throw (Dominik 2026-10-25 „1a 2a 3 4a b c“)
// The die flies over the card, hits the table with its shadow, hops once, rolls out and lands on the panel's number
// (the number was rolled before, this only shows it). Held longer before letting go it flies further (4b, display
// only); landing buzzes the phone (4a); a die that waits for its seat chimes once (4c). Everything drawn here, no files.
const DMT_D20='<svg viewBox="0 0 100 100" aria-hidden="true"><polygon class="dm-d20o" points="50,3 93,27 93,73 50,97 7,73 7,27"/><polygon class="dm-d20f" points="50,24 75,66 25,66"/><polyline class="dm-d20k" points="50,3 50,24 93,27 75,66 93,73 50,97 25,66 7,73 25,66 7,27 50,24"/><polygon class="dm-d20h" points="50,3 93,27 50,24"/><polygon class="dm-d20s" points="7,73 25,66 50,97"/><polygon class="dm-d20s2" points="93,73 75,66 50,97"/></svg>';
const DMT_HOLD={t:0},DMT_DRAN={},DMT_WURF_MS=1400;
document.addEventListener('pointerdown',e=>{if(e.target.closest&&e.target.closest('[data-dmwurf]'))DMT_HOLD.t=Date.now()},true);
function dmtKraft(){const k=DMT_HOLD.t?Math.min(1,(Date.now()-DMT_HOLD.t)/900):0;DMT_HOLD.t=0;return k}
function dmtBrumm(w){try{if(navigator.vibrate)navigator.vibrate(w===20?[25,40,25,40,70]:w===1?[90]:[35])}catch{}}
function dmtDran(k){if(!k||DMT_DRAN[k])return;DMT_DRAN[k]=1;dmtPlay('dran');try{if(navigator.vibrate)navigator.vibrate(15)}catch{}}
const dmtErgebnis=x=>x.w===20?'dm-wkrit':x.w===1?'dm-wpatzer':x.ok?'dm-wok':'dm-wbad';   // 3: the landing's colour
function dmtWurf(el,num,x,kraft,done){const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fin=()=>{num.textContent=x.w;el.classList.add(dmtErgebnis(x));dmtBrumm(x.w);done()};
  if(reduce||!el.animate){fin();return}
  const d=40+70*(kraft||0),h=70+50*(kraft||0),sh=document.createElement('i');sh.className='dm-wschatten';el.appendChild(sh);el.classList.add('dm-wfliegt');
  const k=[{transform:`translate(${-d}px,30px) rotate(-30deg) scale(.85)`,offset:0,easing:'cubic-bezier(.3,.6,.4,1)'},
    {transform:`translate(${-d*.3}px,${-h}px) rotate(260deg) scale(1.05)`,offset:.3,easing:'cubic-bezier(.6,0,.9,.5)'},
    {transform:'translate(0,0) rotate(400deg) scale(1.14,.84)',offset:.48,easing:'cubic-bezier(.2,.7,.4,1)'},
    {transform:`translate(${d*.15}px,-26px) rotate(500deg) scale(1)`,offset:.62,easing:'cubic-bezier(.6,0,.9,.5)'},
    {transform:`translate(${d*.2}px,0) rotate(560deg) scale(1.07,.93)`,offset:.76,easing:'ease-out'},
    {transform:`translate(${d*.08}px,0) rotate(700deg) scale(1)`,offset:.9,easing:'ease-out'},
    {transform:'translate(0,0) rotate(720deg) scale(1)',offset:1}];
  const ks=[{transform:`translateX(${-d}px) scale(.7)`,opacity:.5},{transform:`translateX(${-d*.3}px) scale(.45)`,opacity:.2,offset:.3},{transform:'scale(1.15)',opacity:.6,offset:.48},
    {transform:`translateX(${d*.15}px) scale(.8)`,opacity:.35,offset:.62},{transform:`translateX(${d*.2}px) scale(1.05)`,opacity:.55,offset:.76},{transform:'scale(1)',opacity:.5}];
  el.animate(k,{duration:DMT_WURF_MS,fill:'none'});sh.animate(ks,{duration:DMT_WURF_MS});
  [.48,.76,.9].forEach((o,i)=>setTimeout(()=>dmtPlay('klack'),DMT_WURF_MS*o-(i?0:20)));
  const iv=setInterval(()=>{let f=1+Math.floor(Math.random()*20);if(f===x.w)f=f%20+1;num.textContent=String(f)},70);
  setTimeout(()=>{clearInterval(iv);num.textContent=x.w},DMT_WURF_MS*.9);
  setTimeout(()=>{sh.remove();el.classList.remove('dm-wfliegt');fin()},DMT_WURF_MS+40)}

