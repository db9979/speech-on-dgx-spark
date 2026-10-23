// KI-Dungeon-Master: the wait between turns (dungeon_warten.py, 5j). While the Dungeon Master narrates the feed shows
// the steps with a fixed sentence, the panel's dice before the narration, lore cards of the world and a hint; a new
// narration appears sentence by sentence; „X schreibt …“ and the table talk are only between the players. Every
// text here is fixed or the players' own, the panel picks it; the model never sees the table talk.
const DMWT={seen:{},talk:{p:false,g:false},ping:0};
function dmWait(v){const w=v.warten;if(!v.dm||!w)return '';
  const st={lesen:t('Lesen','Reading'),wuerfeln:t('Würfeln','Dice'),erzaehlen:t('Erzählen','Narrating')},cur=w.s==='nachbessern'?'erzaehlen':w.s,ix=w.folge.indexOf(cur);
  const steps=`<ol class="dm-wsteps">${w.folge.map((s,i)=>`<li class="${i<ix?'ok':i===ix?'on':''}">${esc(st[s])}</li>`).join('')}</ol>`;
  const dice=w.w.length?`<div class="dm-wdice">${w.w.map(x=>`<div class="dm-wurf ${x.ok?'ok':'bad'}"><span class="dm-d20">${x.w}</span>${esc(x.name)} · ${esc((v.werte||{})[x.wert]||x.wert)} = <b>${x.gesamt}</b> ${esc(t('gegen','vs'))} ${x.schwer} · <b>${esc(x.ok?t('geschafft','success'):t('nicht geschafft','failed'))}</b></div>`).join('')}</div>`:'';
  const cards=w.karten.length?`<div class="dm-wkarten">${w.karten.map(k=>`<div class="dm-wkarte"><b>${esc(k.titel)}</b><small>${esc(k.text)}</small></div>`).join('')}</div>`:'';
  return `<div class="dm-warten" role="status">${steps}<p class="dm-wsatz"><span class="dm-wpunkte" aria-hidden="true"></span>${esc(w.satz)}</p>${dice}${cards}${w.tipp?`<small class="dm-wtipp">💡 ${esc(t('Während du wartest: ','While you wait: '))}${esc(w.tipp)}</small>`:''}</div>`}
// a new narration comes sentence by sentence; the time counts from when this page first saw it, so a repaint goes on
function dmSaetze(v,e){const key=v.rid+':'+(e.prolog?'p':'')+(e.n||1),S=DMWT.seen[v.rid]||(DMWT.seen[v.rid]={});
  if(!(key in S))S[key]=S._ready?Date.now():0;S._ready=true;
  const parts=String(e.text||'').match(/[^.!?…]+(?:[.!?…]+["“”»«')]*\s*|$)/g)||[e.text||''],el=S[key]?(Date.now()-S[key])/1000:1e9;
  if(el>parts.length*0.9+1)return esc(e.text);
  return parts.map((p,i)=>`<span class="dm-satz" style="animation-delay:${(i*0.9-el).toFixed(2)}s">${esc(p)}</span>`).join('')}
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
