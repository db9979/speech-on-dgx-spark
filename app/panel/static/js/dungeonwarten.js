// KI-Dungeon-Master: the wait between turns (dungeon_warten.py, 5j). While the Dungeon Master narrates the feed shows
// the steps with a fixed sentence, the panel's dice before the narration, lore cards of the world and a hint; a new
// narration appears sentence by sentence; „X schreibt …“ and the table talk are only between the players. Every
// text here is fixed or the players' own, the panel picks it; the model never sees the table talk.
const DMWT={seen:{},talk:{p:false,g:false},ping:0,thrown:{},shown:{},landT:{},shake:0};
function dmWait(v){const w=v.warten;if(!v.dm||!w)return '';
  const st={lesen:t('Lesen','Reading'),wuerfeln:t('Würfeln','Dice'),erzaehlen:t('Erzählen','Narrating')},cur=w.s==='nachbessern'?'erzaehlen':w.s,ix=w.folge.indexOf(cur);
  const steps=`<ol class="dm-wsteps">${w.folge.map((s,i)=>`<li class="${i<ix?'ok':i===ix?'on':''}">${esc(st[s])}</li>`).join('')}</ol>`;
  const dice=w.w.length?`<div class="dm-wdice">${w.w.map(x=>dmWDie(v,x)).join('')}</div>`:'';
  const cards=w.karten.length?`<div class="dm-wkarten">${w.karten.map(k=>`<div class="dm-wkarte"><b>${esc(k.titel)}</b><small>${esc(k.text)}</small></div>`).join('')}</div>`:'';
  return `<div class="dm-warten" role="status">${steps}<p class="dm-wsatz"><span class="dm-wpunkte" aria-hidden="true"></span>${esc(w.satz)}</p>${dice}${cards}${w.tipp?`<small class="dm-wtipp">💡 ${esc(t('Während du wartest: ','While you wait: '))}${esc(w.tipp)}</small>`:''}</div>`}
// throwing the own die (Dominik 2026-10-23 „1 und 2 aber mit funken bei 20 und eigenes geräusch beim würfel ergebniss“):
// the panel rolled the number already (dungeon.roll); the tap or a shake only rolls it into view, then the bar shows how
// close it was. Another seat's die shows „X würfelt …“ until it is thrown (or WURF_S passed, dungeon_warten).
const dmWKey=(v,x)=>v.rid+':'+x.name+':'+x.wert+':'+x.schwer;
function dmWDie(v,x){const W=v.werte||{},k=dmWKey(v,x),wert=esc(W[x.wert]||x.wert);
  if(x.ich&&!DMWT.thrown[k]&&!x.geworfen)return `<div class="dm-wselbst" data-dmwkey="${esc(k)}"><b>${esc(x.name)} · ${wert}-${esc(t('Probe','check'))}</b><small class="mut">${esc(t('Schwierigkeit','Difficulty'))} ${x.schwer}${x.werkzeug?' · 🔧 '+esc(x.werkzeug):''}</small>
    <button type="button" class="dm-wgross" data-dmwurf="1" aria-label="${esc(t('Würfel werfen','Throw the die'))}">${DMD20}<span>?</span></button><small class="mut">${esc(t('🎲 Antippen oder Handy schütteln','🎲 Tap or shake your phone'))}</small></div>`;
  if(!('w' in x))return `<div class="dm-wurf"><span class="dm-d20 dm-wdreht">?</span>${esc(x.name)} ${esc(t('würfelt …','is rolling …'))} · ${wert}</div>`;
  const el=Date.now()-(DMWT.landT[k]||0),land=el<1300,fun=land&&x.w===20?`<span class="dm-funken" aria-hidden="true">${Array.from({length:14},(_,i)=>`<i style="--a:${i*360/14}deg;--d:${30+(i%3)*14}px;animation-delay:${(-el/1000).toFixed(2)}s"></i>`).join('')}</span>`:'';
  if(land)setTimeout(()=>{if(Date.now()-DMWT.landT[k]>=1300)(v.mode==='g'?dgDraw:dmDraw)()},1350-el);
  return `<div class="dm-wurf ${x.ok?'ok':'bad'}${x.w===20?' dm-krit':''}${land?' dm-wland':''}" data-dmwkey="${esc(k)}"><span class="dm-d20">${x.w}${fun}</span>${dmTool(x)}${esc(x.name)} · ${wert} = <b>${x.gesamt}</b> ${esc(t('gegen','vs'))} ${x.schwer} · <b>${esc(x.ok?t('geschafft','success'):t('nicht geschafft','failed'))}</b></div>${dmLeiste(x,v.werkzeug_bonus,el)}`}
const DMD20='<svg viewBox="0 0 100 100" aria-hidden="true"><polygon points="50,3 93,27 93,73 50,97 7,73 7,27"/><polygon class="dm-d20f" points="50,22 76,66 24,66"/></svg>';
// the bar of a check: the die, the bonus (with the tool's part) up to the red line of the difficulty
function dmLeiste(x,wz,el){if(!('w' in x))return '';const an=el!=null&&el<1300,dl=i=>an?` animation-delay:${([0,.35,.6][i]-el/1000).toFixed(2)}s`:'';const tool=x.werkzeug?(wz||0):0,rest=x.bonus-tool,max=Math.max(20,x.schwer,x.gesamt)+2,pc=n=>(100*Math.max(0,n)/max).toFixed(1)+'%';
  const seg=rest>=0?`<em class="dm-lw" style="width:${pc(x.w)};${dl(0)}"></em><em class="dm-lb" style="width:${pc(rest)};${dl(1)}"></em>${tool?`<em class="dm-lt" style="width:${pc(tool)};${dl(2)}"></em>`:''}`
    :`<em class="dm-lw" style="width:${pc(x.gesamt-tool)};${dl(0)}"></em><em class="dm-lm" style="width:${pc(-rest)};${dl(1)}"></em>${tool?`<em class="dm-lt" style="width:${pc(tool)};${dl(2)}"></em>`:''}`;
  const knapp=Math.abs(x.gesamt-x.schwer)<=1;
  return `<div class="dm-leiste${x.ok?' ok':' bad'}${an?' dm-lan':''}" role="img" aria-label="${esc(t('Würfel ','Die ')+x.w+', Bonus '+dmSign(x.bonus)+' = '+x.gesamt+t(', Ziel ',', target ')+x.schwer)}"><div class="dm-lbar">${seg}<i class="dm-lziel" style="left:${pc(x.schwer)}"></i></div>
    <small class="mut">🎲 ${x.w} · ${esc(t('Bonus','bonus'))} ${dmSign(rest)}${tool?' · 🔧 +'+tool:''} = <b>${x.gesamt}</b> · ${esc(t('Ziel','target'))} ${x.schwer}${knapp?' · '+esc(x.ok?t('ganz knapp!','just made it!'):t('knapp daneben','just missed')):''}</small></div>`}
// the throw: the big die rolls about a second, lands on the panel's number with its sound, a 20 throws sparks
function dmThrow(el){const box=el.closest('[data-dmwkey]'),mode=el.closest('#dgcard')?'g':'p',v=mode==='g'?DG.v:DM.v;if(!box||!v||!v.warten)return;
  const k=box.dataset.dmwkey,x=v.warten.w.find(d=>dmWKey(v,d)===k);if(!x||DMWT.thrown[k])return;DMWT.thrown[k]=true;
  const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches,num=el.querySelector('span');
  if(typeof dmtCtx==='function'){const c=dmtCtx();if(c&&c.state==='suspended')c.resume();if(typeof dmtPlay==='function')dmtPlay('wuerfel',0)}
  el.disabled=true;el.classList.add('dm-rollt');let n=0;
  const done=()=>{DMWT.shown[k]=true;dmWHit(x);(mode==='g'?dgPub('/api/dungeon/wurf',{code:DG.code}).then(d=>{DG.v=d;dgDraw()}):apiTry(`/api/profile/dungeon/${DM.rid}/wurf`,xjson('POST',{})).then(({r,d})=>{if(r.ok){DM.v=d;dmDraw()}})).catch(()=>{});
    DMWT.landT[k]=Date.now();mode==='g'?dgDraw():dmDraw()};
  if(reduce){num.textContent=x.w;done();return}
  const iv=setInterval(()=>{num.textContent=String(1+Math.floor(Math.random()*20));if(++n>=14){clearInterval(iv);done()}},70)}
// the landing (dmWDie draws it for 1.3 s, across repaints): the sound of the result, sparks on a 20, a shake on a 1
function dmWHit(x){if(typeof dmtPlay==='function')setTimeout(()=>dmtPlay(x.w===20?'krit':x.w===1?'patzer':x.ok?'geschafft':'verfehlt'),80)}
// another seat's die shows up: it rolls once here too, with the sound; a die seen once rolls no more (log included)
function dmWOthers(w,v){const ws=(v.warten&&v.warten.w)||[];ws.forEach(x=>{if(!('w' in x))return;const k=dmWKey(v,x);if(DMWT.shown[k])return;DMWT.shown[k]=true;
  if(x.ich)return;const el=w.querySelector(`.dm-wurf[data-dmwkey="${CSS.escape(k)}"]`);if(!el)return;dmWHit(x);const d=el.querySelector('.dm-d20');
  if(d&&!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)){d.classList.add('dm-rollt');setTimeout(()=>{DMWT.landT[k]=Date.now();(v.mode==='g'?dgDraw:dmDraw)()},800)}})}
window.dmWurfGesehen=(v,e)=>!!DMWT.shown[dmWKey(v,e)];
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
// a new narration comes sentence by sentence; the time counts from when this page first saw it, so a repaint goes on
function dmSaetze(v,e){const key=v.rid+':'+(e.prolog?'p':'')+(e.n||1),S=DMWT.seen[v.rid]||(DMWT.seen[v.rid]={});
  if(!(key in S))S[key]=S._ready?Date.now():0;S._ready=true;
  const parts=String(e.text||'').match(/[^.!?…]+(?:[.!?…]+["“”»«')]*\s*|$)/g)||[e.text||''],el=S[key]?(Date.now()-S[key])/1000:1e9;
  if(el>parts.length*0.9+1)return dmFx(e.text);
  return parts.map((p,i)=>`<span class="dm-satz" style="animation-delay:${(i*0.9-el).toFixed(2)}s">${dmFx(p)}</span>`).join('')}
function dmTyping(v){const n=v.tippt||[];return n.length&&!v.dm?`<small class="dm-wait dm-tippt">✎ ${esc(n.join(', '))} ${esc(n.length===1?t('schreibt …','is typing …'):t('schreiben …','are typing …'))}</small>`:''}
function dmTalk(v,mode){if(!v.ich||v.status==='ende')return '';const l=v.tisch||[];
  return `<details class="dm-talk" data-dmtalk="1"${DMWT.talk[mode]?' open':''}><summary>💬 ${esc(t('Tischgespräch','Table talk'))}${l.length?` <span class="pill">${l.length}</span>`:''} <small class="mut">${esc(t('nur unter euch, der Dungeon-Master liest nicht mit','just between you, the Dungeon Master does not read it'))}</small></summary>
    <div class="dm-talk-l">${l.slice(-12).map(x=>`<div class="${x.ich?'me':''}"><b>${esc(x.name)}</b> ${esc(x.text)}</div>`).join('')||`<small class="mut">${esc(t('Noch ist es still am Tisch.','Quiet at the table so far.'))}</small>`}</div>
    <div class="dm-inp"><input class="dm-talk-in" maxlength="200" placeholder="${esc(t('Etwas zu den anderen sagen …','Say something to the others …'))}" aria-label="${esc(t('Tischgespräch','Table talk'))}"><button type="button" class="b" data-dmtalksend="1">${esc(t('Sagen','Say'))}</button></div></details>`}
// the talk field keeps its text and focus across the table's repaints
function dmTalkKeep(w){const i=w.querySelector('.dm-talk-in'),val=i?i.value:'',f=!!i&&document.activeElement===i;
  return ()=>{const n=w.querySelector('.dm-talk-in');if(n){if(val)n.value=val;if(f)n.focus({preventScroll:true})}}}
async function dmTalkSend(el){const mode=el.closest('#dgcard')?'g':'p',box=el.closest('.dm-talk'),inp=box&&box.querySelector('.dm-talk-in'),text=inp?inp.value.trim():'';if(!text)return;
  try{if(mode==='g'){DG.v=await dgPub('/api/dungeon/tisch',{code:DG.code,text});DG.at=Date.now();inp.value='';dgDraw()}
    else{const {r,d}=await apiTry(`/api/profile/dungeon/${DM.rid}/tisch`,xjson('POST',{text}));if(!r.ok)throw new Error();DM.v=d;DM.at=Date.now();inp.value='';dmDraw()}
    const n=document.querySelector(mode==='g'?'#dgcard .dm-talk-in':'#dmview .dm-talk-in');if(n)n.focus({preventScroll:true})}
  catch(e){dmSay(mode==='g'?DG:DM,t('Das hat nicht geklappt.','That did not work.'),true)}}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmtalksend],#dgcard [data-dmtalksend]');if(b)dmTalkSend(b)});
document.body.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.closest&&e.target.closest('#dmview .dm-talk-in,#dgcard .dm-talk-in')){e.preventDefault();dmTalkSend(e.target)}});
document.body.addEventListener('toggle',e=>{const d=e.target;if(d.matches&&d.matches('.dm-talk'))DMWT.talk[d.closest('#dgcard')?'g':'p']=d.open},true);
// a keystroke in the own action field tells the others, at most every 4 s
document.body.addEventListener('input',e=>{const ta=e.target.closest&&e.target.closest('#dmview .dm-in,#dgcard .dm-in');if(!ta||!ta.value.trim()||Date.now()-DMWT.ping<4000)return;DMWT.ping=Date.now();
  if(ta.closest('#dgcard'))dgPub('/api/dungeon/tippt',{code:DG.code}).catch(()=>{});else if(DM.rid)apiTry(`/api/profile/dungeon/${DM.rid}/tippt`,xjson('POST',{})).catch(()=>{})});
