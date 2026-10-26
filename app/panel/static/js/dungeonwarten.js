// KI-Dungeon-Master: the wait between turns (dungeon_warten.py, 5j). While the Dungeon Master narrates the feed shows
// the steps with a fixed sentence, the panel's dice before the narration, lore cards of the world and a hint; a new
// narration appears sentence by sentence; „X schreibt …“ and the table talk are only between the players. Every
// text here is fixed or the players' own, the panel picks it; the model never sees the table talk.
const DMWT={seen:{},talk:{p:false,g:false},ping:0,thrown:{},shown:{},landT:{},shake:0,auto:{}};
function dmWait(v){const w=v.warten;if(!v.dm||!w)return '';
  if(w.wt&&w.wt!==DMWT.wt){DMWT.wt=w.wt;DMWT.thrown={};DMWT.shown={};DMWT.landT={}}   // a new turn's dice: the same check again is a new throw
  const st={lesen:t('Lesen','Reading'),wuerfeln:t('Würfeln','Dice'),erzaehlen:t('Erzählen','Narrating')},cur=w.s==='nachbessern'?'erzaehlen':w.s,ix=w.folge.indexOf(cur);
  const steps=`<ol class="dm-wsteps">${w.folge.map((s,i)=>`<li class="${i<ix?'ok':i===ix?'on':''}">${esc(st[s])}</li>`).join('')}</ol>`;
  const dice=v.echt?dmEcht(v):w.w.length?`<div class="dm-wdice">${w.w.map(x=>dmWDie(v,x)).join('')}</div>`:'';
  const cards=w.karten.length?`<div class="dm-wkarten">${w.karten.map(k=>`<div class="dm-wkarte"><b>${esc(k.titel)}</b><small>${esc(k.text)}</small></div>`).join('')}</div>`:'';
  return `<div class="dm-warten" role="status">${steps}<p class="dm-wsatz"><span class="dm-wpunkte" aria-hidden="true"></span>${esc(w.satz)}</p>${dice}${cards}${w.tipp?`<small class="dm-wtipp">💡 ${esc(t('Während du wartest: ','While you wait: '))}${esc(w.tipp)}</small>`:''}</div>`}
// throwing the own die (Dominik 2026-10-23 „1 und 2 aber mit funken bei 20 und eigenes geräusch beim würfel ergebniss“):
// the panel rolled the number already (dungeon.roll); the tap or a shake only rolls it into view, then the bar shows how
// close it was. Another seat's die shows „X würfelt …“ until it is thrown (or WURF_S passed, dungeon_warten).
const dmWKey=(v,x)=>v.rid+':'+x.name+':'+x.wert+':'+x.schwer;
function dmWDie(v,x){const W=v.werte||{},k=dmWKey(v,x),wert=esc(W[x.wert]||x.wert);
  if(x.ich&&!DMWT.thrown[k]&&!x.geworfen)return dmWBox(v,x,k,-1);
  if(!('w' in x))return dmPK(v,x,'<span class="dm-d20 dm-wdreht">?</span>');
  const el=Date.now()-(DMWT.landT[k]||0),land=el<1300,fun=land&&x.w===20?`<span class="dm-funken" aria-hidden="true">${Array.from({length:14},(_,i)=>`<i style="--a:${i*360/14}deg;--d:${30+(i%3)*14}px;animation-delay:${(-el/1000).toFixed(2)}s"></i>`).join('')}</span>`:'';
  if(land)setTimeout(()=>{if(Date.now()-DMWT.landT[k]>=1300)(v.mode==='g'?dgDraw:dmDraw)()},1350-el);
  const tab=x.krit_tabelle||x.patzer_tabelle;   // D&D idea 2: a table's entry turns the card over on landing
  return dmPK(v,x,`<span class="dm-d20">${x.w}${fun}</span>`,`${x.w===20?' dm-krit':''}${land?' dm-wland '+(typeof dmtErgebnis==='function'?dmtErgebnis(x):'')+(tab?' dm-wumdreh':''):''}`,` data-dmwkey="${esc(k)}"`)
    +(tab?`<b class="dm-wtab${x.patzer_tabelle?' dm-wtabp':''}">${esc((x.krit_tabelle?t('Kritisch: ','Critical: '):t('Patzer: ','Fumble: '))+tab)}</b>`:'')
    +(x.knapp?`<b class="dm-wknapp${land?' dm-wland':''}">${esc(t('Knapp geschafft, mit Preis','Just made it, at a price')+(x.preis_t?': '+x.preis_t:''))}</b>`:'')+dmLeiste(x,el)}   // D&D round 2 idea 1: missed by 1 or 2, passed at a price (dungeon_knapp)
const DMD20=typeof DMT_D20==='string'?DMT_D20:'<svg viewBox="0 0 100 100" aria-hidden="true"><polygon points="50,3 93,27 93,73 50,97 7,73 7,27"/><polygon class="dm-d20f" points="50,22 76,66 24,66"/></svg>';
// the own die waiting for its tap: in the wait (rest -1) or in the feed after the narration came (1a, rest = seconds
// left, a ring runs down and then it throws itself); never the number, only what is checked
function dmWBox(v,x,k,rest){const W=v.werte||{},wert=esc(W[x.wert]||x.wert);if(typeof dmtDran==='function')setTimeout(()=>dmtDran(k),0);   // 4c: a chime once per die
  const ring=rest>=0?`<svg class="dm-wring" viewBox="0 0 118 118" aria-hidden="true"><circle cx="59" cy="59" r="54"/><circle class="dm-wringlauf" cx="59" cy="59" r="54" style="animation-duration:${WURF_MAX}s;animation-delay:${rest-WURF_MAX}s"/></svg>`:'';
  return `<div class="dm-wselbst${rest>=0?' dm-wwartet':''}" data-dmwkey="${esc(k)}"><b>${esc(x.name)} · ${wert}-${esc(t('Probe','check'))}</b>${x.wofuer?`<b class="dm-pkwas">${esc(x.wofuer)}</b>`:''}<small class="mut">${esc(t('Schwierigkeit','Difficulty'))} ${x.schwer}${x.werkzeug?' · 🔧 '+esc(x.werkzeug):''}${x.vt?' · '+esc(x.vt==='vorteil'?t('Vorteil: zwei Würfel, der höhere zählt','advantage: two dice, the higher counts'):t('Nachteil: zwei Würfel, der niedrigere zählt','disadvantage: two dice, the lower counts')):''}</small>
    <span class="dm-wgrosswrap">${ring}<button type="button" class="dm-wgross" data-dmwurf="1" aria-label="${esc(t('Würfel werfen','Throw the die'))}">${DMD20}<span>?</span></button></span><small class="mut">${esc(t('🎲 Antippen, gedrückt halten für einen weiten Wurf, oder Handy schütteln','🎲 Tap, hold for a long throw, or shake your phone'))}</small>${rest>=0?`<small class="dm-wrest">${esc(t(`Wirft sich nach ${WURF_MAX} s von selbst`,`Throws itself after ${WURF_MAX} s`))}</small>`:''}</div>`}
const WURF_MAX=30;   // dungeon_warten.WURF_MAX_S
// the feed (dmTable): an own die not thrown when the narration came stays at its place, what follows is veiled until
// the throw (1a); a die landing just now shows like in the wait (sparks, colour, the bar running up)
const dmWOffen=(v,e)=>e.art==='wurf'&&!DMWT.thrown[dmWKey(v,e)]&&(v.wurf_offen||[]).find(o=>o.name===e.name&&o.wert===e.wert&&o.schwer===e.schwer&&o.n===e.n);
function dmWFeed(v,col){let out='',veil='';
  for(const e of v.log||[]){const k=e.art==='wurf'?dmWKey(v,e):'',o=k&&!veil?dmWOffen(v,e):null;
    if(o){out+=dmWBox(v,e,k,o.rest);veil=' ';dmWAuto(v,k,o.rest);continue}
    const h=k&&DMWT.landT[k]&&Date.now()-DMWT.landT[k]<1300?dmWDie(v,Object.assign({},e,{ich:true,geworfen:true})):dmLog(v,e,col);
    if(veil)veil+=h;else out+=h}
  return veil?out+`<div class="dm-verhuellt"><div aria-hidden="true">${veil}</div><em>🎲 ${esc(t('Erst würfeln, dann geht es weiter','Throw first, then it goes on'))}</em></div>`:out}
function dmWAuto(v,k,rest){if(DMWT.auto[k])return;DMWT.auto[k]=setTimeout(()=>{const b=document.querySelector(`[data-dmwkey="${CSS.escape(k)}"] [data-dmwurf]`);if(b&&!b.disabled)dmThrow(b)},Math.max(0,rest)*1000)}
// the bar of a check: the die, the bonus (with the tool's part) up to the red line of the difficulty
function dmLeiste(x,el){if(!('w' in x))return '';const an=el!=null&&el<1300,dl=i=>an?` animation-delay:${([0,.35,.6][i]-el/1000).toFixed(2)}s`:'';const tool=x.werkzeug?(x.werkzeug_plus||0):0,rest=x.bonus-tool,max=Math.max(20,x.schwer,x.gesamt)+2,pc=n=>(100*Math.max(0,n)/max).toFixed(1)+'%';
  const seg=rest>=0?`<em class="dm-lw" style="width:${pc(x.w)};${dl(0)}"></em><em class="dm-lb" style="width:${pc(rest)};${dl(1)}"></em>${tool?`<em class="dm-lt" style="width:${pc(tool)};${dl(2)}"></em>`:''}`
    :`<em class="dm-lw" style="width:${pc(x.gesamt-tool)};${dl(0)}"></em><em class="dm-lm" style="width:${pc(-rest)};${dl(1)}"></em>${tool?`<em class="dm-lt" style="width:${pc(tool)};${dl(2)}"></em>`:''}`;
  const knapp=Math.abs(x.gesamt-x.schwer)<=1,nat=x.w===20?t('natürliche 20: immer geschafft','natural 20: always a success'):x.w===1?t('natürliche 1: immer daneben','natural 1: always a miss'):'';
  return `<div class="dm-leiste${x.ok?' ok':' bad'}${an?' dm-lan':''}" role="img" aria-label="${esc(t('Würfel ','Die ')+x.w+', Bonus '+dmSign(x.bonus)+' = '+x.gesamt+t(', Ziel ',', target ')+x.schwer)}"><div class="dm-lbar">${seg}<i class="dm-lziel" style="left:${pc(x.schwer)}"></i></div>
    <small class="mut">🎲 ${x.w} · ${esc(t('Bonus','bonus'))} ${dmSign(rest)}${tool?' · 🔧 +'+tool:''} = <b>${x.gesamt}</b> · ${esc(t('Ziel','target'))} ${x.schwer}${nat?' · '+esc(nat):knapp?' · '+esc(x.ok?t('ganz knapp!','just made it!'):t('knapp daneben','just missed')):''}</small></div>`}
// the throw: the big die rolls about a second, lands on the panel's number with its sound, a 20 throws sparks
function dmThrow(el){const box=el.closest('[data-dmwkey]'),mode=el.closest('#dgcard')?'g':'p',v=mode==='g'?DG.v:DM.v;if(!box||!v)return;
  const k=box.dataset.dmwkey,x=((v.warten&&v.warten.w)||[]).find(d=>dmWKey(v,d)===k)||(v.log||[]).find(e=>e.art==='wurf'&&dmWKey(v,e)===k);if(!x||DMWT.thrown[k])return;DMWT.thrown[k]=true;clearTimeout(DMWT.auto[k]);
  const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches,num=el.querySelector('span');
  if(typeof dmtCtx==='function'){const c=dmtCtx();if(c&&c.state==='suspended')c.resume();if(typeof dmtPlay==='function')dmtPlay('wuerfel',0)}
  el.disabled=true;el.classList.add('dm-rollt');let n=0;
  const done=()=>{DMWT.shown[k]=true;dmWHit(x);(mode==='g'?dgPub('/api/dungeon/wurf',{code:DG.code}).then(d=>{DG.v=d;dgDraw()}):apiTry(`/api/profile/dungeon/${DM.rid}/wurf`,xjson('POST',{})).then(({r,d})=>{if(r.ok){DM.v=d;dmDraw()}})).catch(()=>{});
    DMWT.landT[k]=Date.now();mode==='g'?dgDraw():dmDraw()};
  if(typeof dmtWurf==='function'){dmtWurf(el,num,x,dmtKraft(),done);return}   // 2a: flies, hits, hops, rolls out (dungeon-ton.js)
  if(reduce){num.textContent=x.w;done();return}
  // it slows down and its last face is the panel's number, never a random one (Dominik 2026-10-24 „zeigt 14, dann 9“)
  const tick=()=>{n++;if(n>=14){num.textContent=x.w;setTimeout(done,260);return}
    let f=1+Math.floor(Math.random()*20);if(f===x.w)f=f%20+1;num.textContent=String(f);setTimeout(tick,n<9?60:60+(n-8)*45)};tick()}
// the landing (dmWDie draws it for 1.3 s, across repaints): the sound of the result, sparks on a 20, a shake on a 1
function dmWHit(x){if(typeof dmtPlay==='function')setTimeout(()=>dmtPlay(x.w===20?'krit':x.w===1?'patzer':x.ok?'geschafft':'verfehlt'),80)}
// another seat's die shows up: it rolls once here too, with the sound; a die seen once rolls no more (log included)
function dmWOthers(w,v){const ws=(v.warten&&v.warten.w)||[];ws.forEach(x=>{if(!('w' in x))return;const k=dmWKey(v,x);if(DMWT.shown[k])return;DMWT.shown[k]=true;
  if(x.ich)return;const el=w.querySelector(`.dm-wurf[data-dmwkey="${CSS.escape(k)}"]`);if(!el)return;dmWHit(x);const d=el.querySelector('.dm-d20');
  if(d&&!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)){d.classList.add('dm-rollt');setTimeout(()=>{DMWT.landT[k]=Date.now();(v.mode==='g'?dgDraw:dmDraw)()},800)}})}
window.dmWurfGesehen=(v,e)=>!!DMWT.shown[dmWKey(v,e)]||!!dmWOffen(v,e);   // a die waiting for its own tap rolls only then
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmwurf],#dgcard [data-dmwurf]');if(b)dmThrow(b)});
// a shake throws too where the browser gives motion without asking (Android); the iPhone needs the tap
window.addEventListener('devicemotion',e=>{const a=e.accelerationIncludingGravity||e.acceleration;if(!a)return;const f=Math.abs(a.x||0)+Math.abs(a.y||0)+Math.abs(a.z||0);
  if(f<38||Date.now()-DMWT.shake<1500)return;const b=document.querySelector('#dmview [data-dmwurf]:not(:disabled),#dgcard [data-dmwurf]:not(:disabled)');if(b&&b.offsetParent){DMWT.shake=Date.now();dmThrow(b)}});
// the result sounds, synthesized like the others of the table (dungeon-ton.js), only when sounds are on
if(typeof DMT_FX!=='undefined')Object.assign(DMT_FX,{
  geschafft:v=>{const t=dmtNow();dmtTone(660,t,.01,.25,v*.16,'triangle');dmtTone(990,t+.11,.01,.45,v*.16,'triangle')},
  verfehlt:v=>{const t=dmtNow(),o=dmtTone(330,t,.02,.55,v*.16,'triangle');o.frequency.exponentialRampToValueAtTime(220,t+.5)},
  krit:v=>{const t=dmtNow();[523,659,784,1047,1319].forEach((f,i)=>dmtTone(f,t+i*.08,.01,i===4?1.1:.3,v*.14,'triangle'));for(let i=0;i<8;i++)dmtTone(2600+Math.random()*2400,t+.45+i*.06,.002,.2,v*.06)},
  patzer:v=>{const t=dmtNow();[[294,0],[277,.22],[262,.44],[247,.66]].forEach(([f,d],i)=>{const o=dmtTone(f,t+d,.02,i===3?.8:.2,v*.14,'sawtooth');if(i===3)o.frequency.exponentialRampToValueAtTime(180,t+1.4)});dmtNoise(t+.66,.3,v*.25,'lowpass',260)}});
// own dice at the real table (dungeon_echt.py, D&D idea 5): before the panel rolls, the seat throws its d20 and taps or
// says the number; the panel checks it (1 to 20, own seat, this turn) and rolls on. Nothing comes: after max seconds the
// panel rolls itself. The others see who still throws. The numbers are only kept here until „Übernehmen“.
const DMECHT={zug:-1,z:[]};
function dmEcht(v){const e=v.echt,W=v.werte||{};if(DMECHT.zug!==e.zug){DMECHT.zug=e.zug;DMECHT.z=[]}
  const andere=e.andere.length?`<small class="mut">🎲 ${esc(e.andere.join(', '))} ${esc(e.andere.length===1?t('würfelt am Tisch …','is throwing at the table …'):t('würfeln am Tisch …','are throwing at the table …'))}</small>`:'';
  if(!e.fragen.length)return `<div class="dm-echt">${e.fertig?`<b>✓ ${esc(t('Deine Zahl ist da, der Spark rechnet.','Your number is in, the Spark does the maths.'))}</b>`:''}${andere}</div>`;
  const n=e.fragen.reduce((a,f)=>a+f.n,0),z=DMECHT.z,voll=z.length>=n;
  const was=e.fragen.map(f=>`<b class="dm-echtwas">${esc(f.n>1?t('Wirf 2 W20','Throw 2 d20'):t('Wirf W20','Throw a d20'))} ${esc(t('für','for'))} ${esc(W[f.wert]||f.wert)} ${esc(t('gegen','against'))} ${f.schwer}</b>`).join('');
  const pad=Array.from({length:e.seiten},(_,i)=>`<button type="button" class="b" data-dmechtz="${i+1}"${voll?' disabled':''}>${i+1}</button>`).join('');
  const mic=typeof dmMic==='function'&&dmMic.length>1?`<button type="button" class="b" data-dmechtmic="1" aria-label="${esc(t('Zahl sagen','Say the number'))}">🎤</button>`:'';
  return `<div class="dm-echt" role="group" aria-label="${esc(t('Eigener Würfel','Own die'))}">${was}
    <div class="dm-echtz" aria-live="polite">${Array.from({length:n},(_,i)=>`<span class="dm-d20">${z[i]||'·'}</span>`).join('')}</div>
    <div class="dm-echtpad">${pad}</div>
    <div class="row">${mic}<button type="button" class="b" data-dmechtzur="1"${z.length?'':' disabled'}>↶ ${esc(t('Zurück','Back'))}</button><button type="button" class="b p" data-dmechtok="1"${voll?'':' disabled'}>${esc(t('Übernehmen','Take it'))}</button></div>
    <i class="dm-echtzeit" style="animation-duration:${e.max}s;animation-delay:${e.rest-e.max}s" aria-hidden="true"></i>
    <small class="mut">${esc(t(`Noch ${e.rest} s, dann würfelt der Spark selbst.`,`${e.rest} s left, then the Spark rolls itself.`))}</small>${andere}</div>`}
// spoken numbers: digits or the words one to twenty (German and English), in the order said
const DMECHT_W={eins:1,ein:1,eine:1,zwei:2,drei:3,vier:4,fuenf:5,fünf:5,sechs:6,sieben:7,acht:8,neun:9,zehn:10,elf:11,zwoelf:12,zwölf:12,dreizehn:13,vierzehn:14,
  fuenfzehn:15,fünfzehn:15,sechzehn:16,siebzehn:17,achtzehn:18,neunzehn:19,zwanzig:20,one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,
  eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,twenty:20};
function dmEchtZahlen(text){return (String(text||'').toLowerCase().match(/\d+|[a-zäöü]+/g)||[]).map(x=>/^\d+$/.test(x)?+x:DMECHT_W[x]).filter(x=>x>=1&&x<=20)}
function dmEchtDraw(mode){mode==='g'?dgDraw():dmDraw()}
async function dmEchtSend(mode){const v=mode==='g'?DG.v:DM.v;if(!v||!v.echt)return;const body={zug:v.echt.zug,zahlen:DMECHT.z.slice()};
  try{if(mode==='g'){DG.v=await dgPub('/api/dungeon/echt',Object.assign({code:DG.code},body));DG.at=Date.now()}
    else{const {r,d}=await apiTry(`/api/profile/dungeon/${DM.rid}/echt`,xjson('POST',body));if(!r.ok){dmSay(DM,dmErr(r.status,d.detail),true);return}DM.v=d;DM.at=Date.now()}
    if(typeof dmtPlay==='function')dmtPlay('wuerfel',0)}
  catch(e){dmSay(mode==='g'?DG:DM,mode==='g'?dgErr(e):t('Das hat nicht geklappt.','That did not work.'),true)}
  dmEchtDraw(mode)}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview .dm-echt [data-dmechtz],#dgcard .dm-echt [data-dmechtz],#dmview .dm-echt [data-dmechtzur],#dgcard .dm-echt [data-dmechtzur],#dmview .dm-echt [data-dmechtok],#dgcard .dm-echt [data-dmechtok],#dmview .dm-echt [data-dmechtmic],#dgcard .dm-echt [data-dmechtmic]');
  if(!b)return;const mode=b.closest('#dgcard')?'g':'p',v=mode==='g'?DG.v:DM.v,n=v&&v.echt?v.echt.fragen.reduce((a,f)=>a+f.n,0):0;
  if(b.dataset.dmechtz){if(DMECHT.z.length<n)DMECHT.z.push(+b.dataset.dmechtz)}
  else if(b.dataset.dmechtzur)DMECHT.z.pop();
  else if(b.dataset.dmechtok){if(DMECHT.z.length===n)dmEchtSend(mode);return}
  else if(b.dataset.dmechtmic){dmMic(mode,text=>{DMECHT.z=DMECHT.z.concat(dmEchtZahlen(text)).slice(0,n);dmEchtDraw(mode)});return}
  dmEchtDraw(mode)});
// a new narration comes sentence by sentence; the time counts from when this page first saw it, so a repaint goes on
function dmSaetze(v,e){const key=v.rid+':'+(e.prolog?'p':'')+(e.n||1),S=DMWT.seen[v.rid]||(DMWT.seen[v.rid]={});
  if(!(key in S))S[key]=S._ready?Date.now():0;S._ready=true;
  const parts=String(e.text||'').match(/[^.!?…]+(?:[.!?…]+["“”»«')]*\s*|$)/g)||[e.text||''],el=S[key]?(Date.now()-S[key])/1000:1e9;
  if(el>parts.length*0.9+1)return dmFx(e.text);
  return parts.map((p,i)=>`<span class="dm-satz" style="animation-delay:${(i*0.9-el).toFixed(2)}s">${dmFx(p)}</span>`).join('')}
function dmTyping(v){const n=v.tippt||[];return n.length&&!v.dm?`<small class="dm-wait dm-tippt">✎ ${esc(n.join(', '))} ${esc(n.length===1?t('schreibt …','is typing …'):t('schreiben …','are typing …'))}</small>`:''}
function dmTalk(v,mode){if(!v.ich||v.status==='ende')return '';const l=v.tisch||[];
  return `<details class="dm-talk" data-dmtalk="1"${DMWT.talk[mode]?' open':''}><summary>💬 ${esc(t('Tischgespräch','Table talk'))}${l.length?` <span class="pill">${l.length}</span>`:''} <small class="mut">${esc(t('nur unter euch, der Dungeon-Master liest nicht mit','just between you, the Dungeon Master does not read it'))}</small></summary>
    <div class="dm-talk-l">${l.slice(-12).map(x=>`<div class="${x.ich?'me':''}"><b>${esc(x.name)}</b> ${esc(x.text)}${dmHide(v,'tisch',x.n)}</div>`).join('')||`<small class="mut">${esc(t('Noch ist es still am Tisch.','Quiet at the table so far.'))}</small>`}</div>
    ${(v.plaetze||[]).some(p=>p.ich&&p.stumm)?`<small class="mut">🔇 ${esc(t(...DMGRUND.stumm))}</small>`:`<div class="dm-inp"><input class="dm-talk-in" maxlength="200" placeholder="${esc(t('Etwas zu den anderen sagen …','Say something to the others …'))}" aria-label="${esc(t('Tischgespräch','Table talk'))}"><button type="button" class="b" data-dmtalksend="1">${esc(t('Sagen','Say'))}</button></div>`}</details>`}
// the talk field keeps its text and focus across the table's repaints
function dmTalkKeep(w){const i=w.querySelector('.dm-talk-in'),val=i?i.value:'',f=!!i&&document.activeElement===i;
  return ()=>{const n=w.querySelector('.dm-talk-in');if(n){if(val)n.value=val;if(f)n.focus({preventScroll:true})}}}
async function dmTalkSend(el){const mode=el.closest('#dgcard')?'g':'p',box=el.closest('.dm-talk'),inp=box&&box.querySelector('.dm-talk-in'),text=inp?inp.value.trim():'';if(!text)return;
  try{if(mode==='g'){DG.v=await dgPub('/api/dungeon/tisch',{code:DG.code,text});DG.at=Date.now();inp.value='';dgDraw()}
    else{const {r,d}=await apiTry(`/api/profile/dungeon/${DM.rid}/tisch`,xjson('POST',{text}));if(!r.ok){dmSay(DM,dmErr(r.status,d.detail),true);return}DM.v=d;DM.at=Date.now();inp.value='';dmDraw()}
    const n=document.querySelector(mode==='g'?'#dgcard .dm-talk-in':'#dmview .dm-talk-in');if(n)n.focus({preventScroll:true})}
  catch(e){dmSay(mode==='g'?DG:DM,mode==='g'?dgErr(e):t('Das hat nicht geklappt.','That did not work.'),true)}}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmtalksend],#dgcard [data-dmtalksend]');if(b)dmTalkSend(b)});
document.body.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.closest&&e.target.closest('#dmview .dm-talk-in,#dgcard .dm-talk-in')){e.preventDefault();dmTalkSend(e.target)}});
document.body.addEventListener('toggle',e=>{const d=e.target;if(d.matches&&d.matches('.dm-talk'))DMWT.talk[d.closest('#dgcard')?'g':'p']=d.open},true);
// a keystroke in the own action field tells the others, at most every 4 s
document.body.addEventListener('input',e=>{const ta=e.target.closest&&e.target.closest('#dmview .dm-in,#dgcard .dm-in');if(!ta||!ta.value.trim()||Date.now()-DMWT.ping<4000)return;DMWT.ping=Date.now();
  if(ta.closest('#dgcard'))dgPub('/api/dungeon/tippt',{code:DG.code}).catch(()=>{});else if(DM.rid)apiTry(`/api/profile/dungeon/${DM.rid}/tippt`,xjson('POST',{})).catch(()=>{})});
