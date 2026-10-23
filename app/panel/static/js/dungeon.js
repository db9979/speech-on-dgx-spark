// KI-Dungeon-Master (dungeon.py, plan dungeon-master/plan.md): a page of its own in the menu. „Runden“ lists the own
// rounds and starts a new one; an open round is the table: the group on the left, the story in the middle, the round
// and the own hero on the right (a phone shows them one below the other). „Helden“ holds the kept heroes. A seat link
// (#spiel=<code>) opens the same table in a window, for a guest without a profile through /api/dungeon/*, for a
// signed-in profile with „Mit meinem Profil“. Every value comes from the panel; names, actions and the narration are
// only ever text (esc), never markup. Funktionen → KI-Dungeon-Master, button „Regeln anpassen“, is the admin's rules editor.
const DM={on:false,data:null,rid:'',v:null,seq:0,busy:false,msg:'',err:false,made:null,at:0,ende:false,form:{},edit:'',kap:false};
const DG={code:'',v:null,info:null,busy:false,msg:'',err:false,at:0,figur:''};
// read aloud (the last turn's WAV, the host's device plays it by itself) and the microphone of a seat
const DMA={p:{n:0,el:null,url:''},g:{n:0,el:null,url:''},rec:null,parts:[],mode:'',t0:0,voll:false,hilfe:null};
// the short guide for players at the table: opens by itself once on this device, then by its button
const DMHILFE=[['Was du schreibst','What you write','Was deine Figur tut oder sagt, in ein, zwei Sätzen: „Ich schleiche zur Tür und lausche.“ Der Dungeon-Master erzählt, was daraus wird.','What your character does or says, in a sentence or two: "I sneak to the door and listen." The Dungeon Master tells what comes of it.'],
  ['Wann es weitergeht','When it goes on','Alle schreiben gleichzeitig. Haben alle gehandelt oder ist die Zugzeit um, erzählt der Dungeon-Master. „Warten auf“ zeigt, wer noch fehlt; bis dahin kannst du deine Aktion ändern.','Everyone writes at the same time. Once all have acted or the turn time is up, the Dungeon Master narrates. "Waiting for" shows who is still missing; until then you can change your action.'],
  ['Würfeln','Dice','Würfeln musst du nicht, das macht das Panel: ein W20 plus der Bonus deines Werts (16 gibt +3) gegen eine Schwierigkeit. Bei Vorteil würfelt es zweimal und nimmt den besseren Wurf, bei Nachteil den schlechteren.','You never roll yourself, the panel does: a d20 plus your value\'s bonus (16 gives +3) against a difficulty. With advantage it rolls twice and keeps the better roll, with disadvantage the worse.'],
  ['Leben, Beute, Tauschen','Life, loot, trading','Der Balken zeigt dein Leben. Beute landet in deiner Tasche (bis 12 Dinge); Tränke und Zauber nutzt du dort. Tauschen geht per Angebot: erst wenn der andere annimmt, tauscht das Panel.','The bar shows your life. Loot lands in your bag (up to 12 things); you use potions and spells from there. Trading works by offer: only when the other one accepts does the panel swap.'],
  ['Hören und Sprechen','Listen and speak','„🔊 Hören“ liest die Erzählung vor. Mit 🎤 sprichst du deine Aktion; der Text landet im Feld, abgeschickt wird mit „Handeln“.','"🔊 Listen" reads the narration aloud. With 🎤 you speak your action; the text lands in the field, "Act" sends it.'],
  ['Als Gast','As a guest','Am Ende bekommst du einen Figur-Code. Damit spielt dein Held beim nächsten Mal weiter, auch in einem eigenen Profil. Schreib ihn dir auf.','At the end you get a hero code. With it your hero plays on next time, also in a profile of your own. Write it down.']];
function dmHilfe(){if(DMA.hilfe===null){let seen=false;try{seen=localStorage.getItem('dm-hilfe')==='1';localStorage.setItem('dm-hilfe','1')}catch(e){}DMA.hilfe=!seen}
  return DMA.hilfe?`<div class="dm-guide"><div class="dm-gtop"><h5>${esc(t('So spielst du','How to play'))}</h5><button type="button" class="b" data-dmhilfe="0">${esc(t('Schließen','Close'))}</button></div><div class="dm-gl">${DMHILFE.map(x=>`<div><b>${esc(t(x[0],x[1]))}</b><small>${esc(t(x[2],x[3]))}</small></div>`).join('')}</div></div>`:''}
// the table alone, filling the screen (the button again, Esc or leaving the browser's full screen ends it; without the browser's full screen, as on the iPhone, it fills the window)
function dmVoll(on){DMA.voll=on;const w=document.querySelector('.dm.dm-tisch');if(w)w.classList.toggle('dm-voll',on);
  try{if(on&&w&&w.requestFullscreen&&!document.fullscreenElement)w.requestFullscreen().catch(()=>{});if(!on&&document.fullscreenElement)document.exitFullscreen()}catch(e){}
  document.querySelectorAll('.dm-tisch [data-dmvoll]').forEach(b=>{b.dataset.dmvoll=on?0:1;b.textContent=on?'✕ '+t('Vollbild aus','Exit full screen'):'⛶ '+t('Vollbild','Full screen')})}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&DMA.voll)dmVoll(false)});
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&DMA.voll)dmVoll(false)});
const dmWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const dmLang=()=>L==='en'?'en':'de';
// the colour of a rarity (app.css), named here in full so every class is found
const DMSEL={gewoehnlich:'dm-s0',selten:'dm-s1',rar:'dm-s2',episch:'dm-s3',legendaer:'dm-s4'};
// the menu entry only for a signed-in profile the admin released the game for (start.js, like the Wissensbuch)
window.dmStart=who=>{DM.on=!!(who&&who.profile&&who.dungeon);
  document.querySelectorAll('nav button[data-s=dungeon]').forEach(b=>b.hidden=!DM.on)};
function dmOpen(){if(!PROFILE)return;const root=$('dmroot'),box=$('dmbox');if(box){box.hidden=true;$('dungeon').appendChild(box)}root.textContent='';
  const body=k=>()=>{const w=document.createElement('div');w.className='dm';w.id='dmview';w.dataset.tab=k;dmPaint(w);return w};
  root.appendChild(icTabs('dungeon',[{k:'runden',label:OWN_PAGES.dmbox[2],body:body('runden')},{k:'helden',label:t('Helden','Heroes'),body:body('helden')}]));
  dmLoad()}
window.dmOpen=dmOpen;
async function dmLoad(){if(!DM.on)return;const seq=++DM.seq;const {r,d}=await apiTry('/api/profile/dungeon?lang='+dmLang());if(seq!==DM.seq)return;
  if(r.ok){DM.data=d;DM.err=false;DM.msg=''}else{DM.msg=errSay(r.status,d.detail,'');DM.err=true}
  if(DM.rid&&!(DM.data&&DM.data.runden||[]).some(x=>x.rid===DM.rid)){DM.rid='';DM.v=null}
  if(DM.rid)await dmRound();else dmDraw()}
async function dmRound(){if(!DM.rid)return;const seq=++DM.seq;const {r,d}=await apiTry('/api/profile/dungeon/'+DM.rid);if(seq!==DM.seq)return;
  if(r.ok){DM.v=d;DM.at=Date.now()}else{DM.rid='';DM.v=null;DM.msg=errSay(r.status,d.detail,'');DM.err=true}dmDraw()}
function dmDraw(){const w=$('dmview');if(w)dmPaint(w)}
function dmPaint(w){const D=DM.data;w.classList.remove('dm-tisch','dm-voll');w.style.cssText='';
  if(!D){w.innerHTML=`<div class="ld-empty mut">${esc(DM.err?DM.msg:t('Lade den Dungeon-Master …','Loading the Dungeon Master …'))}</div>`;return}
  if(w.dataset.tab==='helden'){w.innerHTML=dmHeroes(D)+dmMsg(DM);return}
  if(DM.v){dmTable(w,DM.v,'p');return}
  w.innerHTML=dmRounds(D)+dmCampaigns(D)+dmNew(D)+dmMsg(DM)}
const dmMsg=S=>`<div class="dmmsg ${S.err?'err':'mut'}" role="status">${esc(S.msg)}</div>`;
function dmSay(S,x,err){S.msg=String(x||'').slice(0,300);S.err=!!err;document.querySelectorAll(S===DM?'#dmview .dmmsg':'#dgcard .dmmsg').forEach(m=>{m.className='dmmsg '+(err?'err':'mut');m.textContent=S.msg})}
function dmRounds(D){const st={laeuft:t('läuft','running'),ende:t('beendet','ended')};
  if(!D.runden.length)return `<div class="ic-empty">${esc(t('Noch keine Runde. Leg unten eine an und lade bis zu vier Mitspieler ein, auch Leute ohne Profil.','No round yet. Start one below and invite up to four players, also people without a profile.'))}</div>`;
  return `<h3 class="sec">${esc(t('Deine Runden','Your rounds'))}</h3><div class="ic-list">${D.runden.map(x=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(x.titel)}</span><small class="ic-meta">${esc(st[x.status]||x.status)} · ${esc(t('Zug','Turn'))} ${x.zug} · ${x.spieler} ${esc(t('Spieler','players'))}${x.held?' · '+esc(x.held):''}${x.gastgeber?' · '+esc(t('du leitest','you host')):''}</small></div><button type="button" class="b p" data-dmopen="${esc(x.rid)}">${esc(t('Öffnen','Open'))}</button></div>`).join('')}</div>`}
// campaigns (Stufe 2): a chapter closed keeps „Bisher geschah“, the heroes and the guests' heroes for the next one
function dmCampaigns(D){const ks=D.kampagnen||[];if(!ks.length)return '';
  return `<h3 class="sec">${esc(t('Kampagnen','Campaigns'))} · ${ks.length}/${D.kampagnen_max}</h3><div class="dm-kamp">${ks.map(k=>{const ed=DM.edit===k.kid;
    const who=[...k.helden,...k.gaeste.map(n=>n+' ('+t('Gast','guest')+')')].join(', ');
    return `<div class="dm-k"><div class="dm-khead"><div><b>${esc(k.titel)}</b><small class="mut">${esc(k.welt)} · ${esc(t('Kapitel','Chapter'))} ${k.kapitel}${who?' · '+esc(who):''}</small></div></div>
    <div class="lbl">${esc(t('Bisher geschah','The story so far'))}${k.entwurf&&!k.schreibt?' · '+esc(t('Entwurf','draft')):''}</div>
    ${k.schreibt?`<p class="mut dm-bisher">${esc(t('Der Dungeon-Master schreibt die Zusammenfassung …','The Dungeon Master is writing the summary …'))}</p>`
      :ed?`<textarea class="dm-kedit" rows="5" maxlength="${D.bisher_max}" aria-label="${esc(t('Bisher geschah','The story so far'))}">${esc(k.bisher)}</textarea>`
      :`<p class="dm-bisher">${esc(k.bisher)}</p>`}
    <div class="dm-hostb">${ed?`<button type="button" class="b p" data-dmksave="${esc(k.kid)}">${esc(t('Speichern','Save'))}</button><button type="button" class="b" data-dmkedit="">${esc(t('Abbrechen','Cancel'))}</button>`
      :`<button type="button" class="b p" data-dmkweiter="${esc(k.kid)}"${k.schreibt?' disabled':''}>▶ ${esc(t('Kapitel '+(k.kapitel+1)+' beginnen','Start chapter '+(k.kapitel+1)))}</button><button type="button" class="b" data-dmkedit="${esc(k.kid)}"${k.schreibt?' disabled':''}>${esc(t('Ändern','Edit'))}</button><button type="button" class="b" data-dmkneu="${esc(k.kid)}"${k.schreibt?' disabled':''}>${esc(t('Neu schreiben lassen','Write it again'))}</button><button type="button" class="b danger" data-dmkdel="${esc(k.kid)}">${esc(t('Löschen','Delete'))}</button>`}</div></div>`}).join('')}</div>`}
function dmHeroForm(w,heroes,pre){const opt=(a)=>a.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('');
  return `${heroes&&heroes.length?`<label>${esc(t('Held','Hero'))}</label><select class="${pre}held"><option value="">${esc(t('Neuer Held …','New hero …'))}</option>${heroes.map(h=>`<option value="${esc(h.hid)}">${esc(h.name)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}</option>`).join('')}</select>`:''}
    <div class="${pre}neu dm-neu"><label>${esc(t('Name deiner Figur','Name of your character'))}</label><input class="${pre}name" maxlength="24" autocomplete="off">
    <div class="dm-two"><div><label>${esc(t('Volk','People'))}</label><select class="${pre}volk">${opt(w.voelker)}</select></div><div><label>${esc(t('Klasse','Class'))}</label><select class="${pre}klasse">${opt(w.klassen)}</select></div></div>
    <label>${esc(t('Werte','Values'))}</label><small class="mut">${esc(t('Die Zahlen 15, 14, 13, 12, 10 und 8 verteilen: ziehen oder zwei antippen tauscht sie. Dahinter das Volk, der Wert und der Bonus für Würfe.','Lay out 15, 14, 13, 12, 10 and 8: drag, or tap two to swap them. After it the people\'s bonus, the value and the bonus for rolls.'))}</small>
    <div class="${pre}vert dm-vert">${w.verteilung?dmVert(w,w.klassen[0].id,w.voelker[0].id):''}</div>
    <label>${esc(t('Ein Satz zu deiner Figur (frei)','One sentence about your character (optional)'))}</label><input class="${pre}satz" maxlength="120" autocomplete="off"></div>`}
function dmHeroBody(box,pre){const sel=box.querySelector('.'+pre+'held');if(sel&&sel.value)return sel.value;
  const v=c=>(box.querySelector('.'+pre+c)||{}).value||'';const vt=box.querySelector('.'+pre+'vert');return {name:v('name').trim(),volk:v('volk'),klasse:v('klasse'),satz:v('satz').trim(),verteilung:vt?dmVertOf(vt):undefined}}
// the six values of a new hero: the fixed row (15 14 13 12 10 8) laid out by the class, the player drags or taps two numbers to swap them
const dmSign=m=>(m<0?'−':'+')+Math.abs(m);
function dmVert(w,kid,vid,cur){const k=w.klassen.find(x=>x.id===kid)||w.klassen[0],vo=w.voelker.find(x=>x.id===vid)||w.voelker[0];
  const val=cur||Object.fromEntries(k.reihe.map((id,i)=>[id,w.verteilung[i]])),md=s=>dmSign(Math.floor((s-10)/2));
  return w.werte.map(x=>{const v=val[x.id],b=(vo.werte||{})[x.id]||0;
    return `<div class="dm-vslot" data-w="${esc(x.id)}" title="${esc(x.name)}"><small>${esc(x.kurz)}</small><button type="button" class="dm-vchip" draggable="true" data-dmv="${esc(x.id)}" aria-label="${esc(x.name+' '+v)}">${v}</button><small class="dm-vsum">${b?'+'+b+' ':''}= <b>${v+b}</b> · ${md(v+b)}</small></div>`}).join('')}
function dmVertOf(box){const o={};box.querySelectorAll('.dm-vchip').forEach(c=>o[c.dataset.dmv]=+c.textContent);return o}
function dmVertWahl(box){return box.closest('#dgcard')?DG.info&&DG.info.wahl:DM.data&&DM.data.wahl}
function dmVertDraw(f,keep){const w=dmVertWahl(f),pre=f.querySelector('.dmf-vert')?'dmf-':'dgf-',v=f.querySelector('.'+pre+'vert');if(!w||!v)return;
  v.innerHTML=dmVert(w,(f.querySelector('.'+pre+'klasse')||{}).value,(f.querySelector('.'+pre+'volk')||{}).value,keep?dmVertOf(v):null)}
function dmVertSwap(v,a,b){if(a===b)return;const o=dmVertOf(v);[o[a],o[b]]=[o[b],o[a]];const f=v.closest('.dm-neu');
  v.innerHTML=dmVert(dmVertWahl(v),(f.querySelector('.dmf-klasse,.dgf-klasse')||{}).value,(f.querySelector('.dmf-volk,.dgf-volk')||{}).value,o);
  const c=v.querySelector(`[data-dmv="${CSS.escape(b)}"]`);if(c)c.focus({preventScroll:true})}
document.body.addEventListener('change',e=>{const s=e.target.closest('.dm-neu .dmf-klasse,.dm-neu .dgf-klasse,.dm-neu .dmf-volk,.dm-neu .dgf-volk');if(!s)return;
  dmVertDraw(s.closest('.dm-neu'),/volk$/.test(s.className))});
document.body.addEventListener('click',e=>{const c=e.target.closest('.dm-vchip');if(!c)return;const v=c.closest('.dm-vert'),on=v.querySelector('.dm-vchip.on');
  if(on&&on!==c){dmVertSwap(v,on.dataset.dmv,c.dataset.dmv);return}c.classList.toggle('on')});
document.body.addEventListener('dragstart',e=>{const c=e.target.closest&&e.target.closest('.dm-vchip');if(c){e.dataTransfer.setData('text/plain',c.dataset.dmv);e.dataTransfer.effectAllowed='move'}});
document.body.addEventListener('dragover',e=>{if(e.target.closest&&e.target.closest('.dm-vslot'))e.preventDefault()});
document.body.addEventListener('drop',e=>{const s=e.target.closest&&e.target.closest('.dm-vslot');if(!s)return;e.preventDefault();
  const a=e.dataTransfer.getData('text/plain');if(a)dmVertSwap(s.closest('.dm-vert'),a,s.dataset.w)});
function dmNew(D){const w=D.wahl;if(D.runden.filter(x=>x.gastgeber&&x.status!=='ende').length>=D.runden_max)return `<div class="ic-note"><div class="ic-mid"><b>${esc(t('Du leitest schon '+D.runden_max+' Runden.','You host '+D.runden_max+' rounds already.'))}</b><span>${esc(t('Beende eine, um eine neue anzulegen.','End one to start a new one.'))}</span></div></div>`;
  const min=s=>s>=3600?Math.round(s/3600)+' h':s>=60?Math.round(s/60)+' min':s+' s';
  return `<h3 class="sec">${esc(t('Neue Runde','New round'))}</h3><div class="dm-form">
    <label>${esc(t('Titel','Title'))}</label><input class="dmf-titel" maxlength="60" placeholder="${esc(t('Die Glocke von Hallstein','The bell of Hallstein'))}">
    ${(w.geschichten||[]).length?`<label>${esc(t('Geschichte des Admins (frei)','The admin\'s story (optional)'))}</label><select class="dmf-gesch"><option value="">${esc(t('Keine, der Dungeon-Master erzählt frei','None, the Dungeon Master tells freely'))}</option>${w.geschichten.map(g=>`<option value="${esc(g.gid)}">${esc(g.titel)} · ${g.akte} ${esc(t('Akte','acts'))}</option>`).join('')}</select>`:''}
    <label>${esc(t('Welt','World'))}</label><div class="lseg dm-seg dmf-welt">${w.welten.map((x,i)=>`<button type="button" data-dmseg="${esc(x.id)}" title="${esc(x.satz)}"${i===0?' class="on"':''}>${esc(x.name)}</button>`).join('')}</div>
    <label>${esc(t('Einstieg (frei)','Opening (optional)'))}</label><textarea class="dmf-einstieg" rows="2" maxlength="400" placeholder="${esc(t('Ein Dorf, dessen Glocke nachts von selbst läutet.','A village whose bell rings by itself at night.'))}"></textarea>
    <label>${esc(t('Ton','Tone'))}</label><div class="lseg dm-seg dmf-ton">${w.toene.map((x,i)=>`<button type="button" data-dmseg="${x.id}"${i===1||w.toene.length===1?' class="on"':''}>${esc(x.name)}</button>`).join('')}</div>
    <div class="dm-two"><div><label>${esc(t('Zeit je Zug','Time per turn'))}</label><select class="dmf-zug">${w.zug_s.map(s=>`<option value="${s}"${s===w.zug_standard?' selected':''}>${esc(min(s))}</option>`).join('')}</select></div>
    <div><label>${esc(t('Die Runde gilt','The round lasts'))}</label><select class="dmf-stunden">${w.stunden.map(h=>`<option value="${h}">${esc(min(h*3600))}</option>`).join('')}</select></div></div>
    ${dmHeroForm(w,D.helden,'dmf-')}
    <label class="dm-check"><input type="checkbox" class="dmf-vorlesen"> ${esc(t('Erzählung vorlesen (Erzähler und NPC mit eigener Stimme)','Read the story aloud (narrator and NPCs in their own voices)'))}</label>
    <details class="adv"><summary>${esc(t('Dungeon-Master-Prompt','Dungeon Master prompt'))}</summary><div class="fh">${esc(t('Dahinter stehen immer die festen Regeln des Panels: JSON, Namen, Ton, keine erfundenen Werte.','The panel\'s fixed rules always stand behind it: JSON, names, tone, no invented values.'))}</div><textarea class="dmf-prompt" rows="6" maxlength="4000">${esc(w.prompt)}</textarea></details>
    <div class="row"><button type="button" class="b p" data-dmmake="1">${esc(t('Runde starten','Start the round'))}</button></div></div>`}
function dmHeroes(D){const hs=D.helden;
  const list=hs.length?`<div class="ic-list">${hs.map(h=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(h.name)}</span><small class="ic-meta">${esc(h.volk)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe} · ${h.ep} EP · ${esc(t('Leben','life'))} ${h.leben}/${h.leben_max} · ${h.gold} ${esc(t('Gold','gold'))}</small></div><button type="button" class="b" data-dmdelhero="${esc(h.hid)}">${esc(t('Löschen','Delete'))}</button></div>`).join('')}</div>`
    :`<div class="ic-empty">${esc(t('Noch keine Helden. Ein Held entsteht mit deiner ersten Runde und behält Stufe, Werte und Beute.','No heroes yet. A hero comes with your first round and keeps level, values and loot.'))}</div>`;
  return `<h3 class="sec">${esc(t('Deine Helden','Your heroes'))} · ${hs.length}/${D.helden_max}</h3>${list}
    <div class="ic-danger"><div class="ic-mid"><b>${esc(t('Alle Spieldaten löschen','Delete all game data'))}</b><span>${esc(t('Deine Helden, Kampagnen, Runden und deine Plätze in fremden Runden.','Your heroes, campaigns, rounds and your seats in other rounds.'))}</span></div><button type="button" class="b danger" data-dmwipe="1">${esc(t('Löschen …','Delete …'))}</button></div>`}
// ---------------------------------------------------------------- the table (own page and guest window)
function dmBar(v,max,cls){const pc=Math.max(0,Math.min(100,Math.round(100*v/(max||1))));return `<i class="dm-bar ${cls||''}"><em style="width:${pc}%"></em></i>`}
function dmItem(it,acts){return `<div class="dm-item ${DMSEL[it.selten]||''}"><div><b>${esc(it.name)}</b> <small>${esc(it.selten_name)}</small></div>${it.satz?`<small class="dm-isatz">„${esc(it.satz)}“</small>`:''}<small>${it.zeilen.map(esc).join(' · ')}</small>${acts||''}</div>`}
function dmLog(v,e,col){const W=v.werte||{},sys=Array.isArray(e.text)?e.text[L==='en'?1:0]:e.text;
  if(e.art==='dm')return `<div class="dm-dm"><div class="dm-n">${esc(t('Zug','Turn'))} ${e.n||1}</div><p>${esc(e.text)}</p>${(e.npc||[]).map(n=>`<div class="dm-npc"><em>${esc(n.name)}</em><p>„${esc(n.sagt)}“</p></div>`).join('')}</div>`;
  if(e.art==='aktion')return `<div class="dm-act"><span class="dm-av" data-c="${col?col(e.pid):0}">${esc((e.name||'?').slice(0,1).toUpperCase())}</span><div class="dm-bub"><b>${esc(e.name)}</b><p>${esc(e.text)}</p></div></div>`;
  if(e.art==='wurf')return `<div class="dm-wurf ${e.ok?'ok':'bad'}"><span class="dm-d20">${e.w}</span>${e.vt&&(e.ws||[]).length===2?`<small class="pill ${e.vt==='vorteil'?'ok':'warn'}">${esc(e.vt==='vorteil'?t('Vorteil','Advantage'):t('Nachteil','Disadvantage'))} ${e.ws[0]}/${e.ws[1]}</small> `:''}${esc(e.name)} · ${esc(W[e.wert]||e.wert)} +${e.bonus} = <b>${e.gesamt}</b> ${esc(t('gegen','vs'))} ${e.schwer} · <b>${esc(e.ok?t('geschafft','success'):t('nicht geschafft','failed'))}</b></div>`;
  if(e.art==='folge')return `<div class="dm-sys ${e.was==='heilung'?'ok':'bad'}">${esc(e.name)}: ${e.was==='heilung'?'+':'−'}${e.zahl} ${esc(t('Leben','life'))} (${esc(t('jetzt','now'))} ${e.leben})</div>`;
  if(e.art==='beute')return `<div class="dm-beute"><div class="dm-n">${esc(t('Beute für ','Loot for '))}${esc(e.name)}</div>${dmItem(e.item)}${e.gold?`<small class="mut">${esc(t('Gold für jeden: ','Gold for everyone: '))}${e.gold}</small>`:''}</div>`;
  if(e.art==='zauber')return `<div class="dm-zauber">✦ ${esc(e.name)} ${esc(t('wirkt','casts'))} <b>${esc(e.zauber)}</b>${e.gruppe?' '+esc(t('auf die Gruppe','on the group')):''}: ${esc(e.satz)}</div>`;
  if(e.art==='ooc')return `<div class="dm-ooc">(OOC: ${esc(e.text)})</div>`;
  if(e.art==='akt')return `<div class="dm-akt">❖ ${esc(sys||'')}</div>`;
  if(e.art==='ep')return `<div class="dm-sys mut">${esc(e.name)} +${e.zahl} EP</div>`;
  if(e.art==='stufe')return `<div class="dm-stufe">★ ${esc(e.name)} ${esc(t('erreicht Stufe','reaches level'))} ${e.stufe}!</div>`;
  return `<div class="dm-sys mut">${esc(sys||'')}</div>`}
function dmMe(v,mode){const h=v.ich;if(!h)return '';const others=v.plaetze.filter(p=>!p.frei&&!p.ich);
  const give=it=>others.length?`<select data-dmgive="${esc(it.i)}" aria-label="${esc(t('Geben an','Give to'))}"><option value="">${esc(t('Geben …','Give …'))}</option>${others.map(p=>`<option value="${esc(p.pid)}">${esc(p.name)}</option>`).join('')}</select>`:'';
  const acts=it=>`<div class="dm-iacts">${['waffe','ruestung','schmuck'].includes(it.art)?`<button type="button" class="b" data-dmhero="anlegen" data-i="${esc(it.i)}">${esc(t('Anlegen','Equip'))}</button>`:''}${it.art==='trank'?`<button type="button" class="b" data-dmhero="trinken" data-i="${esc(it.i)}">${esc(t('Trinken','Drink'))}</button>`:''}${it.art==='zauber'?`<button type="button" class="b" data-dmhero="wirken" data-i="${esc(it.i)}">${esc(t('Wirken','Cast'))}</button>`:''}${give(it)}</div>`;
  const slot={waffe:t('Waffe','Weapon'),ruestung:t('Rüstung','Armour'),schmuck:t('Schmuck','Jewellery')};
  return `<div class="dm-me"><h4>${esc(h.name)} · ${esc(h.volk)} ${esc(h.klasse)}</h4>${h.satz?`<small class="mut">${esc(h.satz)}</small>`:''}
    <div class="dm-line"><span>${esc(t('Stufe','Level'))} ${h.stufe}</span><span>${h.ep}${h.ep_naechste?' / '+h.ep_naechste:''} EP</span></div>${h.ep_naechste?dmBar(h.ep,h.ep_naechste,'ep'):''}
    <div class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${h.leben}/${h.leben_max}</span></div>${dmBar(h.leben,h.leben_max,h.leben*3<h.leben_max?'low':'')}
    <div class="dm-werte">${h.werte.map(x=>`<span title="${esc(x.name+': '+x.wert+t(', Bonus für Würfe ',', bonus for rolls ')+dmSign(x.gesamt))}">${esc(x.kurz)} <b>${x.wert}</b> <small class="mut">${dmSign(x.gesamt)}</small>${h.punkte&&x.wert<h.wert_max?`<button type="button" class="b dm-plus" data-dmhero="punkt" data-wert="${esc(x.id)}" title="${esc(t('Wertpunkt hierhin','Value point here'))}">+1</button>`:''}</span>`).join('')}<span>${esc(t('Schutz','Protection'))} <b>${h.schutz}</b></span><span>${esc(t('Gold','Gold'))} <b>${h.gold}</b></span></div>
    ${(v.stimmen||[]).length?`<div class="dm-voice"><label>${esc(t('Stimme deines Helden','Your hero\'s voice'))}</label><div class="dm-inp"><select data-dmvoice="1" aria-label="${esc(t('Stimme deines Helden','Your hero\'s voice'))}"><option value="">${esc(t('Keine, nur der Erzähler','None, only the narrator'))}</option>${[...new Set([h.stimme,...v.stimmen].filter(Boolean))].map(x=>`<option${x===h.stimme?' selected':''}>${esc(x)}</option>`).join('')}</select><button type="button" class="b" data-dmprobe="1"${h.stimme?'':' disabled'}>${esc('▶ '+t('Probe','Sample'))}</button></div><small class="mut">${esc(t('Ist Vorlesen an, spricht diese Stimme, was dein Held in Anführungszeichen sagt: „Halt, wer da?“','When reading aloud is on, this voice speaks what your hero says in quotes: "Halt, who goes there?"'))}</small></div>`:''}
    ${(h.segen||[]).length?`<div class="dm-segen">${h.segen.map(x=>`<span class="pill ok">${esc(x.wert)} +${x.bonus} · ${esc(x.zuege===1?t('noch 1 Zug','1 turn left'):t('noch '+x.zuege+' Züge',x.zuege+' turns left'))}${x.name?' · '+esc(x.name):''}</span>`).join(' ')}</div>`:''}
    ${h.punkte?`<div class="dm-hint">${esc(t('Neue Stufe: verteile '+h.punkte+' Wertpunkt'+(h.punkte>1?'e':'')+'.','New level: spend '+h.punkte+' value point'+(h.punkte>1?'s':'')+'.'))}</div>`:''}
    ${h.wahl.length?`<div class="dm-hint">${esc(t('Neue Fähigkeit wählen:','Pick a new ability:'))}</div>${h.wahl.map(f=>`<button type="button" class="b dm-fa" data-dmhero="faehigkeit" data-id="${esc(f.id)}"><b>${esc(f.name)}</b><small>${esc(f.satz)}</small></button>`).join('')}`:''}
    ${h.faehigkeiten.length?`<h5>${esc(t('Fähigkeiten','Abilities'))}</h5>${h.faehigkeiten.map(f=>`<div class="dm-fa-own"><b>${esc(f.name)}</b> <small>${esc(f.satz)}</small></div>`).join('')}`:''}
    <h5>${esc(t('Ausrüstung','Equipment'))}</h5>${Object.entries(h.slots).map(([k,it])=>`<div class="dm-slot"><small class="mut">${esc(slot[k])}</small>${it?dmItem(it,`<div class="dm-iacts"><button type="button" class="b" data-dmhero="ablegen" data-art="${esc(k)}">${esc(t('Ablegen','Unequip'))}</button></div>`):`<small class="mut">–</small>`}</div>`).join('')}
    <h5>${esc(t('Tasche','Bag'))} · ${h.tasche.length}</h5>${h.tasche.map(it=>dmItem(it,acts(it))).join('')||`<small class="mut">${esc(t('leer','empty'))}</small>`}
    ${dmTrade(v,mode)}
    ${mode==='g'?`<div class="dm-figur"><button type="button" class="b" data-dmfigur="1">${esc(t('Figur-Code holen','Get a hero code'))}</button>${DG.figur?`<input readonly value="${esc(DG.figur)}" aria-label="${esc(t('Figur-Code','Hero code'))}"><small class="mut">${esc(t('Nur einmal zu sehen. Damit nimmst du deinen Helden in eine andere Runde mit (30 Tage, einmal).','Shown once. Take your hero into another round with it (30 days, once).'))}</small>`:''}</div>`:''}</div>`}
// a trade: the offer form keeps its picks across repaints (one per page kind), the panel checks and swaps
const TX={p:null,g:null};
function dmTrade(v,mode){const h=v.ich,others=v.plaetze.filter(p=>!p.frei&&!p.ich),x=TX[mode];
  const its=a=>a.length?a.map(it=>`<span class="dm-tx-it dm-s${it.selten}">${esc(it.name)}</span>`).join(''):'';
  const side=(a,g)=>[its(a),g?`<span class="dm-tx-it">${g} ${esc(t('Gold','gold'))}</span>`:''].join('')||'–';
  const list=(v.angebote||[]).map(o=>`<div class="dm-tx"><div><small class="mut">${esc(o.mir?t(o.von_name+' bietet dir','Offer from '+o.von_name):t('Dein Angebot an '+o.an_name,'Your offer to '+o.an_name))}</small></div>
    <div class="dm-tx-row"><div>${side(o.gebe,o.gold)}</div><span aria-hidden="true">⇄</span><div>${side(o.will,o.will_gold)}</div></div>
    <div class="dm-iacts">${o.mir?`<button type="button" class="b p" data-dmtx="annehmen" data-t="${esc(o.t)}">${esc(t('Annehmen','Accept'))}</button><button type="button" class="b" data-dmtx="ablehnen" data-t="${esc(o.t)}">${esc(t('Ablehnen','Decline'))}</button>`
      :`<button type="button" class="b" data-dmtx="ablehnen" data-t="${esc(o.t)}">${esc(t('Zurückziehen','Withdraw'))}</button>`}</div></div>`).join('');
  if(!others.length&&!list)return '';
  let form='';
  if(x){const o=others.find(p=>p.pid===x.an)||others[0];if(o)x.an=o.pid;
    const pick=(a,set,k)=>a.map(it=>`<label class="dm-tx-pick"><input type="checkbox" data-dmtxpick="${k}" value="${esc(it.i)}"${set.includes(it.i)?' checked':''}>${dmItem(it)}</label>`).join('')||`<small class="mut">${esc(t('leer','empty'))}</small>`;
    form=o?`<div class="dm-txform"><label>${esc(t('Mit','With'))} <select data-dmtxan>${others.map(p=>`<option value="${esc(p.pid)}"${p.pid===o.pid?' selected':''}>${esc(p.name)}</option>`).join('')}</select></label>
      <h6>${esc(t('Du gibst','You give'))}</h6>${pick(h.tasche,x.gebe,'gebe')}<label>${esc(t('Gold','Gold'))} <input type="number" min="0" max="${h.gold}" value="${x.gold}" data-dmtxgold="gold"></label>
      <h6>${esc(t('Du bekommst von '+o.name,'You get from '+o.name))}</h6>${pick(o.tasche||[],x.will,'will')}<label>${esc(t('Gold','Gold'))} <input type="number" min="0" value="${x.will_gold}" data-dmtxgold="will_gold"></label>
      <small class="mut">${esc(t('Bis zu '+v.tausch_teile+' Dinge je Seite. Erst wenn '+o.name+' annimmt, tauscht das Panel.','Up to '+v.tausch_teile+' things per side. The panel swaps only when '+o.name+' accepts.'))}</small>
      <div class="dm-iacts"><button type="button" class="b p" data-dmtx="tauschen">${esc(t('Angebot senden','Send offer'))}</button><button type="button" class="b" data-dmtx="zu">${esc(t('Abbrechen','Cancel'))}</button></div></div>`:'';}
  return `<h5>${esc(t('Tauschen','Trade'))}</h5>${list}${form||(others.length&&v.status!=='ende'?`<button type="button" class="b" data-dmtx="auf">${esc(t('Tausch anbieten','Offer a trade'))}</button>`:'')}`}
async function dmTx(B,mode,post){const x=TX[mode];
  if(B.dmtx==='auf'){TX[mode]={an:'',gebe:[],will:[],gold:0,will_gold:0};return true}
  if(B.dmtx==='zu'){TX[mode]=null;return true}
  if(B.dmtx==='tauschen'){if(!x)return true;if(!(x.gebe.length||x.gold)||!(x.will.length||x.will_gold)){return t('Wähle auf beiden Seiten etwas.','Pick something on both sides.')}
    if(await post({was:'tauschen',an:x.an,gebe:x.gebe,will:x.will,gold:x.gold,will_gold:x.will_gold}))TX[mode]=null;return true}
  await post({was:B.dmtx,t:B.t});return true}
document.body.addEventListener('change',e=>{const el=e.target.closest('[data-dmtxan],[data-dmtxpick],[data-dmtxgold]');if(!el)return;
  const mode=el.closest('#dgcard')?'g':'p',x=TX[mode];if(!x)return;const D=el.dataset;
  if(D.dmtxan!==undefined){x.an=el.value;x.will=[];x.will_gold=0;mode==='g'?dgDraw():dmDraw();return}
  if(D.dmtxpick){const a=x[D.dmtxpick];const i=a.indexOf(el.value);if(el.checked&&i<0)a.push(el.value);if(!el.checked&&i>=0)a.splice(i,1);return}
  if(D.dmtxgold)x[D.dmtxgold]=Math.max(0,Math.floor(+el.value||0))});
function dmTable(w,v,mode){const keep=w.querySelector('.dm-in'),kv=keep?keep.value:'',kf=!!keep&&document.activeElement===keep;
  const st=v.status==='ende'?t('beendet','ended'):v.dm?t('der Dungeon-Master erzählt …','the Dungeon Master is narrating …'):v.pause?t('Pause','paused'):'';
  const done=v.plaetze.filter(p=>!p.frei&&p.gehandelt).length,all=v.plaetze.filter(p=>!p.frei).length;
  const seats=v.plaetze.filter(p=>!p.frei),col=pid=>Math.max(0,seats.findIndex(p=>p.pid===pid))%5;
  const group=v.plaetze.map(p=>p.frei?`<div class="dm-seat free"><span class="dm-av">+</span><div><b>${esc(t('Platz frei','Free seat'))}</b><small class="mut">${esc(t('Link verschickt ','Link sent '))}${esc(dmWhen(p.made))}</small></div><button type="button" class="b" data-dmseatdel="${esc(p.pid)}">${esc(t('Zurücknehmen','Take back'))}</button></div>`
    :`<div class="dm-seat dm-hero${p.ich?' me':''}"><div class="dm-hhead"><span class="dm-av" data-c="${col(p.pid)}">${esc((p.name||'?').slice(0,1).toUpperCase())}</span><div><b>${esc(p.name)}</b> <i>${esc(p.volk)} ${esc(p.klasse)}</i><small class="mut">${esc(t('Stufe','Level'))} ${p.stufe}${p.gastgeber?' · '+esc(t('leitet','hosts')):p.gast?' · '+esc(t('Gast','guest')):''}</small></div>${mode==='p'&&v.gastgeber&&!p.gastgeber?`<button type="button" class="ic-ib" data-dmseatdel="${esc(p.pid)}" title="${esc(t('Platz zurücknehmen','Take the seat back'))}" aria-label="${esc(t('Platz zurücknehmen','Take the seat back'))}">×</button>`:''}</div>
      <div class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${p.leben} / ${p.leben_max}</span></div>${dmBar(p.leben,p.leben_max,p.leben*3<p.leben_max?'low':'')}
      ${p.karte?`<div class="dm-stats">${p.karte.werte.map(x=>`<span title="${esc(x.name)}"><small>${esc(x.kurz)}</small><b>${x.wert}</b><i>${dmSign(x.mod)}</i></span>`).join('')}<span title="${esc(t('Schutz','Protection'))}"><small>${esc(t('SCH','PRO'))}</small><b>${p.karte.schutz}</b></span></div>
      ${p.karte.dinge.length?`<div class="dm-pills">${p.karte.dinge.map(n=>`<span>${esc(n)}</span>`).join('')}</div>`:''}`:''}
      <small class="dm-state ${p.gehandelt?'ok':p.online?'':'away'}">${esc(p.gehandelt?t('hat gehandelt','acted'):p.online?t('denkt nach','thinking'):t('nicht da','away'))}</small></div>`).join('');
  const sc=v.szene&&(v.szene.ort||v.szene.stimmung)?`<div class="dm-scene"><i>${esc(t('Ort:','Place:'))}</i> ${esc([v.szene.ort,v.szene.stimmung].filter(Boolean).join(' · '))}</div>`:'';
  const wait=seats.filter(p=>!p.gehandelt).map(p=>p.name);
  const S=mode==='p'?DM:DG,sid=mode==='p'?'dmsend':'dgsend';
  const input=v.status==='ende'||!v.ich?'':`${wait.length&&!v.dm?`<small class="dm-wait">${esc(t('Warten auf: ','Waiting for: '))}<b>${esc(wait.join(', '))}</b></small>`:''}<div class="dm-inp"><textarea class="dm-in" rows="1" data-zeilen="4" data-senden="${sid}" maxlength="${v.text_max}" placeholder="${esc(t('Was macht ','What does ')+v.ich.name+t('? ',' do? '))}" aria-label="${esc(t('Deine Aktion','Your action'))}"${v.dm?' disabled':''}></textarea><button type="button" class="b dm-mic${DMA.rec&&DMA.mode===mode?' on':''}" data-dmmic="1" title="${esc(t('Sprechen statt tippen','Speak instead of typing'))}" aria-label="${esc(t('Sprechen statt tippen','Speak instead of typing'))}"${v.dm?' disabled':''}>${DMA.rec&&DMA.mode===mode?'● '+esc(t('Fertig','Done')):'🎤'}</button><button type="button" class="b p" id="${sid}" data-dmsend="1"${v.dm?' disabled':''}>${esc(t('Handeln','Act'))}</button></div>${v.meine_aktion?`<small class="mut dm-mine">${esc(t('Deine Aktion für diesen Zug: ','Your action for this turn: '))}${esc(v.meine_aktion)}</small>`:''}`;
  const host=mode==='p'&&v.gastgeber&&v.status!=='ende'?`<h5>${esc(t('Gastgeber','Host'))}</h5><div class="dm-hostb"><button type="button" class="b" data-dmweiter="1"${done&&!v.dm?'':' disabled'}>${esc(t('Jetzt weiter','Go on now'))}</button><button type="button" class="b" data-dmpause="${v.pause?0:1}">${esc(v.pause?t('Weiter','Resume'):t('Pause','Pause'))}</button><button type="button" class="b" data-dmvorlesen="${v.vorlesen?0:1}">${esc(v.vorlesen?t('🔊 Vorlesen aus','🔊 Reading off'):t('🔊 Vorlesen an','🔊 Read aloud'))}</button>
    ${all<v.max?`<button type="button" class="b" data-dminvite="1">${esc(t('Einladen','Invite'))} (${v.max-all-v.plaetze.filter(p=>p.frei).length} ${esc(t('frei','free'))})</button>`:''}<button type="button" class="b" data-dmkap="1">${esc(DM.kap?t('Kapitel wirklich beenden?','Really end the chapter?'):t('Kapitel beenden','End chapter'))}</button><button type="button" class="b danger" data-dmend="1">${esc(DM.ende?t('Wirklich beenden?','Really end?'):t('Runde beenden','End round'))}</button></div>${dmPlanHost(v)}
    ${DM.made?`<div class="mitmade"><div class="jqr">${DM.made.qr||''}</div><div class="sp"><input readonly value="${esc(DM.made.link)}" aria-label="${esc(t('Der Link','The link'))}"><small class="mut">${esc(t('Nur jetzt zu sehen. Wer ihn öffnet, sitzt auf diesem Platz: als Gast ohne Profil oder mit seinem Profil.','Shown only now. Whoever opens it takes this seat: as a guest without a profile or with their profile.'))}</small></div></div>`:''}`:'';
  const log=v.log.map(e=>dmLog(v,e,col)).join('');
  w.classList.add('dm-tisch');w.classList.toggle('dm-voll',DMA.voll);w.dataset.welt=v.welt_id||'';w.style.cssText=Object.entries(v.farben||{}).filter(([k,x])=>/^#[0-9a-fA-F]{6}$/.test(x)).map(([k,x])=>`--t-${k}:${x}`).join(';');
  w.innerHTML=`<div class="dm-head">${mode==='p'?`<button type="button" class="b" data-dmback="1">${esc(t('← Runden','← Rounds'))}</button>`:''}<div class="dm-htitle"><h3>${esc(v.titel)}</h3>${sc}<small class="mut">${esc(v.welt)} · ${esc(v.ton)}${v.kapitel?' · '+esc(t('Kapitel','Chapter'))+' '+v.kapitel:''}${v.akte?' · '+esc(v.erzaehlt?t('Geschichte erzählt','story told'):t('Akt','Act')+' '+v.akt+'/'+v.akte):''} · ${esc(t('Zug','Turn'))} ${v.zug}${st?' · '+esc(st):''}</small></div>${v.vorlesen?`<button type="button" class="b dm-hear" data-dmhear="1"${v.ton_zug.length?'':' disabled'}>${esc(v.liest?t('🔊 wird gesprochen …','🔊 being spoken …'):t('🔊 Hören','🔊 Listen'))}</button>`:''}${v.ich?`<button type="button" class="b dm-help" data-dmhilfe="${DMA.hilfe?0:1}">${esc('❔ '+t('So spielst du','How to play'))}</button>`:''}<button type="button" class="b dm-full" data-dmvoll="${DMA.voll?0:1}">${esc(DMA.voll?'✕ '+t('Vollbild aus','Exit full screen'):'⛶ '+t('Vollbild','Full screen'))}</button></div>
    ${v.ich?dmHilfe():''}<div class="dm-grid"><div class="dm-col dm-group"><h5>${esc(t('Gruppe','Group'))} · ${all}/${v.max}</h5>${group}</div>
    <div class="dm-col dm-story"><div class="dm-feed" aria-live="polite">${log}</div>${input}</div>
    <div class="dm-col dm-side"><h5>${esc(t('Zug','Turn'))} ${v.zug}</h5><div class="dm-round">${v.plaetze.filter(p=>!p.frei).map(p=>`<span class="${p.gehandelt?'on':''}"></span>`).join('')}</div>
    <small class="mut dm-left">${esc(v.status==='ende'?t('Die Runde ist zu Ende.','The round has ended.'):v.dm?t('Der Dungeon-Master erzählt …','The Dungeon Master is narrating …'):`${done} ${t('von','of')} ${all} ${t('haben gehandelt','have acted')}`+(done&&!v.pause?t(' · weiter spätestens in ',' · goes on at the latest in ')+Math.max(0,Math.round(v.rest-(Date.now()-S.at)/1000))+' s':''))}</small>
    ${host}${dmMe(v,mode)}</div></div>${dmMsg(S)}`;
  const f=w.querySelector('.dm-feed');if(f)f.scrollTop=f.scrollHeight;
  const inp=w.querySelector('.dm-in');if(inp){if(kv)inp.value=kv;if(kf)inp.focus({preventScroll:true})}
  const n=v.ton_zug&&v.ton_zug[0]||0,A=DMA[mode];if(n&&n!==A.n){const first=!A.n;A.n=n;if(!first&&mode==='p'&&v.gastgeber&&v.vorlesen)dmPlay(mode,n)}}
// the admin's story of the round: only the host sees the plan, the players only the act's number
function dmPlanHost(v){const p=v.plan;if(!p)return '';const cur=v.erzaehlt?-1:v.akt-1;
  return `<details class="adv dm-plan"><summary>${esc(t('Geschichte: ','Story: ')+p.titel)} · ${esc(t('nur du siehst das','only you see this'))}</summary><small class="mut">${esc(t('Ziel: ','Goal: ')+p.ziel)}${p.gegner?' · '+esc(t('Gegenspieler: ','Foe: ')+p.gegner):''}</small>
    <ol>${p.akte.map((a,i)=>`<li class="${i===cur?'on':i<cur||cur<0?'mut':''}"><b>${esc(a.titel)}</b> <small>${esc(a.inhalt)}</small><small class="mut">${esc(t('Wendepunkt: ','Turning point: ')+a.wende)} · ${a.zuege} ${esc(t('Züge','turns'))}</small></li>`).join('')}</ol>
    <small class="mut">${esc(t('Der Dungeon-Master entscheidet, wann der nächste Akt beginnt (frühestens nach '+v.akt_min+' Zügen); läuft ein Akt anderthalbmal so lange wie geplant, geht das Panel selbst weiter.','The Dungeon Master decides when the next act begins (after '+v.akt_min+' turns at the earliest); when an act runs one and a half times as long as planned, the panel moves on by itself.'))}</small></details>`}
// the turn read aloud: the same WAV for every seat, fetched when asked (the host's device: by itself)
async function dmPlay(mode,n){const A=DMA[mode];n=n||A.n;if(!n)return;
  try{let blob;if(mode==='p'){const r=await api(`/api/profile/dungeon/${DM.rid}/ton/${n}`);if(!r.ok)return;blob=await r.blob()}
    else{const r=await /*raw: public route of a guest seat*/fetch('/api/dungeon/ton',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,zug:n})});if(!r.ok)return;blob=await r.blob()}
    if(A.el)A.el.pause();if(A.url)URL.revokeObjectURL(A.url);A.url=URL.createObjectURL(blob);A.el=new Audio(A.url);await A.el.play()}
  catch(e){dmSay(mode==='p'?DM:DG,t('Zum Vorlesen bitte einmal „🔊 Hören“ tippen.','Tap "🔊 Listen" once to hear it.'),false)}}
// speak instead of type: up to 30 s, the panel's speech recognition writes it into the own field, sending stays a tap
async function dmMic(mode){const S=mode==='p'?DM:DG;
  if(DMA.rec){DMA.rec.stop();return}
  if(!window.isSecureContext||!navigator.mediaDevices){dmSay(S,t('Das Mikrofon braucht https.','The microphone needs https.'),true);return}
  let st;try{st=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
  catch{dmSay(S,t('Kein Zugriff aufs Mikrofon.','No access to the microphone.'),true);return}
  const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m=>window.MediaRecorder&&MediaRecorder.isTypeSupported(m))||'';
  const rec=new MediaRecorder(st,mime?{mimeType:mime}:{}),parts=[];DMA.rec=rec;DMA.mode=mode;
  rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};
  const stop=setTimeout(()=>rec.state!=='inactive'&&rec.stop(),30000);
  rec.onstop=async()=>{clearTimeout(stop);st.getTracks().forEach(x=>x.stop());DMA.rec=null;mode==='p'?dmDraw():dgDraw();
    dmSay(S,t('Erkenne Sprache …','Transcribing …'),false);
    try{const wav=await toWav(new Blob(parts,{type:rec.mimeType||'audio/webm'}));
      const b64=await new Promise((ok,no)=>{const fr=new FileReader();fr.onload=()=>ok(String(fr.result).split(',')[1]||'');fr.onerror=no;fr.readAsDataURL(wav)});
      let d;if(mode==='p'){const x=await apiTry(`/api/profile/dungeon/${DM.rid}/hoeren`,xjson('POST',{wav:b64}));if(!x.r.ok){dmSay(S,errSay(x.r.status,x.d.detail,''),true);return}d=x.d}
      else d=await dgPub('/api/dungeon/hoeren',{code:DG.code,wav:b64});
      const ta=document.querySelector(mode==='p'?'#dmview .dm-in':'#dgcard .dm-in');
      if(ta&&d.text){ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+d.text;ta.focus()}dmSay(S,d.text?'':t('Nichts verstanden.','Nothing understood.'),false)}
    catch(e){dmSay(S,mode==='p'?t('Das hat nicht geklappt.','That did not work.'):dgErr(e),true)}};
  rec.start();mode==='p'?dmDraw():dgDraw()}
// the open page asks every poll seconds while it is to be seen; a redraw only when something changed (typing stays)
function dmSig(v){return v?[v.zug,v.log.length,v.dm,v.pause,v.status,v.vorlesen,v.liest,(v.ton_zug||[]).join(),v.akt,v.erzaehlt,v.plaetze.map(p=>[p.pid,p.gehandelt,p.online,p.leben,p.stufe].join()).join('|'),v.meine_aktion,JSON.stringify(v.ich),JSON.stringify(v.angebote||[]),v.plaetze.map(p=>(p.tasche||[]).map(x=>x.i).join()).join('|')].join('#'):''}
setInterval(async()=>{if(document.visibilityState!=='visible')return;
  if(DM.v&&$('dmview')&&$('dungeon').classList.contains('on')&&!DM.busy&&Date.now()-DM.at>=DM.v.poll*1000){const old=dmSig(DM.v);DM.at=Date.now();
    const {r,d}=await apiTry('/api/profile/dungeon/'+DM.rid);if(r.ok&&DM.v){DM.v=d;DM.at=Date.now();if(dmSig(d)!==old)dmDraw();else dmLeft(DM)}}
  else if(DM.v)dmLeft(DM);
  else if(!DM.v&&DM.data&&(DM.data.kampagnen||[]).some(k=>k.schreibt)&&$('dmview')&&Date.now()-DM.at>=3000){DM.at=Date.now();dmLoad()}
  const m=$('dgmodal');if(DG.v&&m&&m.style.display==='grid'&&!DG.busy&&Date.now()-DG.at>=DG.v.poll*1000){const old=dmSig(DG.v);DG.at=Date.now();
    try{const d=await dgPub('/api/dungeon/lage',{code:DG.code});DG.v=d;DG.at=Date.now();if(dmSig(d)!==old)dgDraw()}
    catch(e){dmSay(DG,dgErr(e),true)}}},1000);
function dmLeft(S){const v=S.v,el=document.querySelector(S===DM?'#dmview .dm-left':'#dgcard .dm-left');if(!v||!el||v.dm||v.status==='ende')return;
  const done=v.plaetze.filter(p=>!p.frei&&p.gehandelt).length,all=v.plaetze.filter(p=>!p.frei).length;
  el.textContent=`${done} ${t('von','of')} ${all} ${t('haben gehandelt','have acted')}`+(done&&!v.pause?t(' · weiter spätestens in ',' · goes on at the latest in ')+Math.max(0,Math.round(v.rest-(Date.now()-S.at)/1000))+' s':'')}
async function dmSend(path,b,S,x){if(S.busy)return null;S.busy=true;
  const o=x?xjson(x.method,Object.assign({lang:dmLang()},x.body||{})):b===null?{method:'DELETE'}:xjson('POST',Object.assign({lang:dmLang()},b||{}));const {r,d}=await apiTry(path,o);S.busy=false;
  if(!r.ok){dmSay(S,errSay(r.status,d.detail,''),true);return null}S.msg='';S.err=false;return d}
// ---------------------------------------------------------------- clicks of the own page
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmopen],#dmview [data-dmback],#dmview [data-dmmake],#dmview [data-dmseg],#dmview [data-dmsend],#dmview [data-dmhero],#dmview [data-dmweiter],#dmview [data-dmpause],#dmview [data-dminvite],#dmview [data-dmseatdel],#dmview [data-dmend],#dmview [data-dmdelhero],#dmview [data-dmwipe],#dmview [data-dmtx],#dmview [data-dmvorlesen],#dmview [data-dmkap],#dmview [data-dmhear],#dmview [data-dmvoll],#dmview [data-dmhilfe],#dmview [data-dmprobe],#dmview [data-dmmic],#dmview [data-dmkweiter],#dmview [data-dmkedit],#dmview [data-dmksave],#dmview [data-dmkneu],#dmview [data-dmkdel]');
  if(!b)return;const B=b.dataset,w=$('dmview'),rid=DM.rid;
  if(B.dmseg!==undefined){b.parentNode.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));return}
  if(B.dmopen){DM.rid=B.dmopen;DM.made=null;DM.ende=false;DMA.p.n=0;await dmRound();return}
  if(B.dmback){DM.rid='';DM.v=null;DM.made=null;await dmLoad();return}
  if(B.dmmake){const q=c=>w.querySelector(c),D=DM.data,body={titel:q('.dmf-titel').value.trim(),welt:q('.dmf-welt .on').dataset.dmseg,einstieg:q('.dmf-einstieg').value.trim(),
      ton:+q('.dmf-ton .on').dataset.dmseg,zug_s:+q('.dmf-zug').value,stunden:+q('.dmf-stunden').value,held:dmHeroBody(w,'dmf-'),vorlesen:q('.dmf-vorlesen').checked};
    const gs=q('.dmf-gesch');if(gs&&gs.value)body.geschichte=gs.value;
    const p=q('.dmf-prompt').value.trim();if(p&&p!==D.wahl.prompt)body.prompt=p;
    if(body.titel.length<2){dmSay(DM,t('Bitte gib der Runde einen Titel.','Please give the round a title.'),true);return}
    const d=await dmSend('/api/profile/dungeon/runde',body,DM);if(d){DM.rid=d.rid;DM.v=d;DM.at=Date.now();dmDraw()}return}
  if(B.dmtx){const m=await dmTx(B,'p',async b2=>{const d=await dmSend(`/api/profile/dungeon/${rid}/held`,b2,DM);if(d){DM.v=d;DM.at=Date.now()}return !!d});
    if(typeof m==='string')dmSay(DM,m,true);dmDraw();return}
  if(B.dmhear){dmPlay('p');return}
  if(B.dmvoll){dmVoll(B.dmvoll==='1');return}
  if(B.dmhilfe){DMA.hilfe=B.dmhilfe==='1';dmDraw();return}
  if(B.dmprobe){dmProbe('p',(DM.v&&DM.v.ich||{}).stimme);return}
  if(B.dmmic){dmMic('p');return}
  if(B.dmkedit!==undefined){DM.edit=B.dmkedit;dmDraw();return}
  if(B.dmksave||B.dmkneu||B.dmkdel){const kid=B.dmksave||B.dmkneu||B.dmkdel;
    const x=B.dmksave?await dmSend('/api/profile/dungeon/kampagne/'+kid,null,DM,{method:'PUT',body:{bisher:(w.querySelector('.dm-kedit')||{}).value||''}})
      :B.dmkneu?await dmSend(`/api/profile/dungeon/kampagne/${kid}/neu`,{},DM):await dmSend('/api/profile/dungeon/kampagne/'+kid,null,DM);
    if(x){DM.data=x;DM.edit=''}dmDraw();return}
  if(B.dmkweiter){const d=await dmSend(`/api/profile/dungeon/kampagne/${B.dmkweiter}/weiter`,{},DM);if(d){DM.rid=d.rid;DM.v=d;DM.at=Date.now();DMA.p.n=0}dmDraw();return}
  if(B.dmkap){if(!DM.kap){DM.kap=true;dmDraw();return}DM.kap=false;
    const x=await dmSend(`/api/profile/dungeon/${rid}/kapitel`,{},DM);if(x){DM.data=x;DM.rid='';DM.v=null;DM.made=null;DM.at=Date.now();icTabSet('dungeon','runden')}dmDraw();return}
  if(B.dmdelhero){const d=await dmSend('/api/profile/dungeon/held/'+B.dmdelhero,null,DM);if(d){DM.data=d;dmDraw()}return}
  if(B.dmwipe){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich alles löschen?','Really delete everything?');return}
    const d=await dmSend('/api/profile/dungeon/daten',null,DM);if(d){DM.rid='';DM.v=null;await dmLoad()}return}
  let d=null;
  if(B.dmsend){const ta=w.querySelector('.dm-in');const text=(ta&&ta.value||'').trim();if(!text)return;
    d=await dmSend(`/api/profile/dungeon/${rid}/aktion`,{text,zug:DM.v.zug},DM);if(d&&ta)ta.value=''}
  else if(B.dmhero)d=await dmSend(`/api/profile/dungeon/${rid}/held`,{was:B.dmhero,i:B.i,wert:B.wert,id:B.id,art:B.art},DM);
  else if(B.dmweiter)d=await dmSend(`/api/profile/dungeon/${rid}/weiter`,{},DM);
  else if(B.dmpause)d=await dmSend(`/api/profile/dungeon/${rid}/pause`,{an:B.dmpause==='1'},DM);
  else if(B.dmvorlesen)d=await dmSend(`/api/profile/dungeon/${rid}/vorlesen`,{an:B.dmvorlesen==='1'},DM);
  else if(B.dminvite){d=await dmSend(`/api/profile/dungeon/${rid}/platz`,{base:location.origin},DM);if(d)DM.made={link:d.link,qr:d.qr}}
  else if(B.dmseatdel)d=await dmSend(`/api/profile/dungeon/${rid}/platz/${B.dmseatdel}`,null,DM);
  else if(B.dmend){if(!DM.ende){DM.ende=true;dmDraw();return}DM.ende=false;
    const x=await dmSend(`/api/profile/dungeon/${rid}`,null,DM);if(x){DM.data=x;DM.rid='';DM.v=null;DM.made=null;dmDraw()}return}
  if(d){DM.v=d;DM.at=Date.now()}dmDraw()});
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmvoice],#dgcard [data-dmvoice]');if(!s)return;
  const body={was:'stimme',stimme:s.value};
  if(s.closest('#dmview')){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
  else await dgAct('/api/dungeon/held',body)});
// a fixed sentence in the hero's voice, fetched when asked (the same playback as the turn read aloud)
async function dmProbe(mode,voice){const A=DMA[mode];if(!voice)return;
  try{let r;if(mode==='p')r=await api(`/api/profile/dungeon/${DM.rid}/probe?stimme=${encodeURIComponent(voice)}&lang=${L==='en'?'en':'de'}`);
    else r=await /*raw: public route of a guest seat*/fetch('/api/dungeon/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,stimme:voice})});
    if(!r.ok){dmSay(mode==='p'?DM:DG,t('Die Sprachausgabe ist gerade belegt.','The speech output is busy right now.'),1);return}
    if(A.el)A.el.pause();if(A.url)URL.revokeObjectURL(A.url);A.url=URL.createObjectURL(await r.blob());A.el=new Audio(A.url);await A.el.play()}catch(e){}}
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmgive],#dgcard [data-dmgive]');if(!s||!s.value)return;
  const body={was:'schenken',i:s.dataset.dmgive,an:s.value};
  if(s.closest('#dmview')){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
  else await dgAct('/api/dungeon/held',body)});
document.body.addEventListener('change',e=>{const s=e.target.closest('#dmview .dmf-gesch');if(!s)return;
  const g=((DM.data&&DM.data.wahl.geschichten)||[]).find(x=>x.gid===s.value),f=s.closest('.dm-form');if(!g||!f)return;
  [['.dmf-welt',g.welt],['.dmf-ton',g.ton]].forEach(([c,id])=>f.querySelectorAll(c+' button').forEach(x=>x.classList.toggle('on',x.dataset.dmseg===String(id))))});
document.body.addEventListener('change',e=>{const s=e.target.closest('#dmview .dmf-held,#dgcard .dgf-held');if(!s)return;
  const n=s.parentNode.querySelector('.dm-neu');if(n)n.hidden=!!s.value});
// ---------------------------------------------------------------- a seat link (#spiel=<code>): guest or own profile
async function dgPub(p,b){const r=await /*raw: public route of a guest seat, api() would open the login on a 401*/fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  let d={};try{d=await r.json()}catch{}
  if(!r.ok){const e=new Error(typeof d.detail==='string'?d.detail:'');e.status=r.status;throw e}return d}
const dgErr=e=>e.status===404?t('Der Dungeon-Master ist auf diesem Spark gerade aus.','The Dungeon Master is switched off on this Spark right now.')
  :e.status===429?t('Zu viele Versuche. Bitte später noch einmal.','Too many attempts. Please try again later.')
  :e.message==='name doppelt'?t('Diesen Namen hat schon jemand in der Runde.','Someone in the round has this name already.')
  :e.message==='besetzt'?t('Dieser Platz ist schon besetzt.','This seat is taken already.')
  :e.message==='alter zug'?t('Der Zug ist gerade zu; gleich geht es weiter.','The turn is closed right now; it goes on in a moment.')
  :e.message==='figur-code'?t('Der Figur-Code passt nicht oder wurde schon benutzt.','The hero code does not fit or was used already.')
  :e.status===400?t('Der Link passt nicht mehr: abgelaufen, zurückgenommen oder die Runde ist vorbei.','The link does not fit any more: expired, taken back or the round is over.')
  :t('Das hat nicht geklappt.','That did not work.');
window.dmHash=()=>{const m=/^#spiel=([A-Za-z0-9_-]{32})$/.exec(location.hash);if(!m)return false;
  history.replaceState(null,'',location.pathname+location.search);DG.code=m[1];dgStart();return true};
function dgBox(){let m=$('dgmodal');if(!m){m=document.createElement('div');m.id='dgmodal';m.className='modal dgmodal';
  m.innerHTML='<div class="card modalcard dgcard" id="dgcard"></div>';document.body.appendChild(m)}m.style.display='grid';return $('dgcard')}
const DGHEAD=`<div class="row joinbrand"><span class="logo"></span><b>Spark</b><button type="button" class="b dg-leave" data-dgleave="1">${esc(t('Schließen','Close'))}</button></div>`;
async function dgStart(){const box=dgBox();box.innerHTML=DGHEAD+`<div class="mut">${esc(t('Lade die Einladung …','Loading the invitation …'))}</div>`;
  try{DG.info=await dgPub('/api/dungeon/platz',{code:DG.code})}catch(e){box.innerHTML=DGHEAD+`<div class="err">${esc(dgErr(e))}</div>`;return}
  if(!DG.info.frei){try{DG.v=await dgPub('/api/dungeon/lage',{code:DG.code});DG.at=Date.now();dgDraw()}catch(e){box.innerHTML=DGHEAD+`<div class="err">${esc(dgErr(e))}</div>`}return}
  dgForm()}
function dgForm(){const I=DG.info,box=dgBox(),w=I.wahl;let name='';try{name=localStorage.getItem('dgname')||''}catch{}
  const mine=DM.on&&DM.data?DM.data.helden:[];
  box.innerHTML=DGHEAD+`<div class="dm-invite"><small class="mut">${esc(I.von?t('Einladung von ','Invitation from ')+I.von:t('Einladung','Invitation'))}</small><h2>${esc(I.titel)}</h2>
    <div class="mut">${I.spieler} ${esc(t('von','of'))} ${I.max} ${esc(t('Plätzen','seats'))} · ${esc(t('gilt bis ','until '))}${esc(dmWhen(I.until))}</div>
    ${DM.on?`<div class="lseg dm-seg dgf-wie"><button type="button" class="on" data-dgwie="p">${esc(t('Mit meinem Profil','With my profile'))}</button><button type="button" data-dgwie="g">${esc(t('Als Gast','As a guest'))}</button></div>`:''}
    ${(I.kampagne_helden||[]).length?`<label>${esc(t('Deine Figur aus dem letzten Kapitel','Your character from the last chapter'))}</label><select class="dgf-kamp"><option value="">${esc(t('Keine, eine neue Figur','None, a new character'))}</option>${I.kampagne_helden.map(h=>`<option value="${esc(h.hid)}">${esc(h.name)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}</option>`).join('')}</select>`:''}
    <div class="dgf-body">${dmHeroForm(w,DM.on?mine:[],'dgf-')}</div>
    ${`<details class="adv"><summary>${esc(t('Ich habe einen Figur-Code','I have a hero code'))}</summary><input class="dgf-figur" maxlength="32" autocomplete="off" aria-label="${esc(t('Figur-Code','Hero code'))}"></details>`}
    <div class="row joinfoot"><button class="b p" type="button" data-dgjoin="1">${esc(t('Mitspielen','Join'))}</button></div>
    <small class="mut">${esc(DM.on?t('Mit deinem Profil behält dein Held Stufe und Beute. Als Gast speichert der Spark nur Name und Figur in dieser Runde.','With your profile your hero keeps level and loot. As a guest the Spark keeps only name and character in this round.'):t('Kein Konto, keine PIN. Der Spark speichert nur Spielname und Figur in dieser Runde, bis sie endet.','No account, no PIN. The Spark keeps only the name and character in this round until it ends.'))}</small>
    ${dmMsg(DG)}</div>`;
  const n=box.querySelector('.dgf-name');if(n&&!n.value)n.value=name;if(n)n.focus()}
function dgDraw(){const box=dgBox();if(!DG.v)return;let w=box.querySelector('.dm');if(!w){box.innerHTML=DGHEAD+'<div class="dm"></div>';w=box.querySelector('.dm')}dmTable(w,DG.v,'g')}
async function dgAct(path,b){if(DG.busy)return;DG.busy=true;
  try{DG.v=await dgPub(path,Object.assign({code:DG.code},b));DG.at=Date.now();DG.msg='';DG.err=false;dgDraw()}catch(e){dmSay(DG,dgErr(e),true)}DG.busy=false}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dgcard [data-dgleave],#dgcard [data-dgjoin],#dgcard [data-dgwie],#dgcard [data-dmsend],#dgcard [data-dmhero],#dgcard [data-dmfigur],#dgcard [data-dmtx],#dgcard [data-dmhear],#dgcard [data-dmvoll],#dgcard [data-dmhilfe],#dgcard [data-dmprobe],#dgcard [data-dmmic]');if(!b)return;
  const B=b.dataset,box=$('dgcard');
  if(B.dgleave){DG.v=null;$('dgmodal').style.display='none';return}
  if(B.dmhear){dmPlay('g');return}
  if(B.dmvoll){dmVoll(B.dmvoll==='1');return}
  if(B.dmhilfe){DMA.hilfe=B.dmhilfe==='1';dgDraw();return}
  if(B.dmprobe){dmProbe('g',(DG.v&&DG.v.ich||{}).stimme);return}
  if(B.dmmic){dmMic('g');return}
  if(B.dgwie){b.parentNode.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
    box.querySelector('.dgf-body').innerHTML=dmHeroForm(DG.info.wahl,B.dgwie==='p'&&DM.data?DM.data.helden:[],'dgf-');return}
  if(B.dgjoin){const wie=(box.querySelector('.dgf-wie .on')||{dataset:{dgwie:'g'}}).dataset.dgwie,held=dmHeroBody(box,'dgf-');
    const fig=((box.querySelector('.dgf-figur')||{}).value||'').trim(),kamp=wie==='g'&&((box.querySelector('.dgf-kamp')||{}).value||'');
    if(kamp){b.disabled=true;try{DG.v=await dgPub('/api/dungeon/beitreten',{code:DG.code,kampagne:kamp});DG.at=Date.now();dgDraw()}catch(e){dmSay(DG,dgErr(e),true);b.disabled=false}return}
    if(!fig&&typeof held==='object'){if(held.name.length<2){dmSay(DG,t('Bitte gib deiner Figur einen Namen.','Please name your character.'),true);return}try{localStorage.setItem('dgname',held.name)}catch{}}
    b.disabled=true;
    if(wie==='p'){const {r,d}=await apiTry('/api/profile/dungeon/beitreten',xjson('POST',fig?{code:DG.code,figur:fig}:{code:DG.code,held}));b.disabled=false;
      if(!r.ok){dmSay(DG,errSay(r.status,d.detail,''),true);return}
      $('dgmodal').style.display='none';DM.rid=d.rid;DM.v=d;DM.at=Date.now();icTabSet('dungeon','runden');goSec('dungeon');return}
    try{DG.v=await dgPub('/api/dungeon/beitreten',fig?{code:DG.code,figur:fig}:{code:DG.code,held});DG.at=Date.now();dgDraw()}
    catch(e){dmSay(DG,dgErr(e),true);b.disabled=false}return}
  if(B.dmsend){const ta=box.querySelector('.dm-in');const text=(ta&&ta.value||'').trim();if(!text)return;
    await dgAct('/api/dungeon/aktion',{text,zug:DG.v.zug});const t2=box.querySelector('.dm-in');if(t2&&!DG.err)t2.value='';return}
  if(B.dmhero){await dgAct('/api/dungeon/held',{was:B.dmhero,i:B.i,wert:B.wert,id:B.id,art:B.art});return}
  if(B.dmtx){const m=await dmTx(B,'g',async b2=>{await dgAct('/api/dungeon/held',b2);return !DG.err});if(typeof m==='string')dmSay(DG,m,true);dgDraw();return}
  if(B.dmfigur){if(DG.busy)return;DG.busy=true;try{const d=await dgPub('/api/dungeon/figur',{code:DG.code});DG.figur=d.figur;dgDraw()}catch(e){dmSay(DG,dgErr(e),true)}DG.busy=false}});
// ---------------------------------------------------------------- the admin's rules (Funktionen → KI-Dungeon-Master)
async function dmRules(){let m=$('dmadm');if(!m){m=document.createElement('div');m.id='dmadm';m.className='modal';
    m.innerHTML='<div class="card modalcard dmadmcard" id="dmadmcard"></div>';document.body.appendChild(m)}
  m.style.display='grid';const c=$('dmadmcard');c.innerHTML=`<div class="mut">${esc(t('Lade die Regeln …','Loading the rules …'))}</div>`;
  DMP.g=null;const {r,d}=await apiTry('/api/admin/dungeon?lang='+dmLang());if(!r.ok){c.innerHTML=`<div class="err">${esc(errSay(r.status,d.detail,''))}</div>`;return}
  try{DMA.voices=((await (await api('/api/tts/voices')).json()).voices||[]).filter(x=>typeof x==='string')}catch{DMA.voices=[]}dmRulesDraw(d,'')}
function dmRulesDraw(d,err){const c=$('dmadmcard'),S=d.summe,txt=JSON.stringify(d.eigene||{},null,2);DMP.d=d;
  if(DMP.g){c.innerHTML=dmPlanForm(d);return}
  const names={welten:t('Welten','Worlds'),toene:t('Töne','Tones'),voelker:t('Völker','Peoples'),klassen:t('Klassen','Classes'),faehigkeiten:t('Fähigkeiten','Abilities'),gegenstaende:t('Gegenstände','Items'),seltenheit:t('Seltenheiten','Rarities'),effekte:t('Effekte','Effects'),werte:t('Werte','Values')};
  c.innerHTML=`<h2>${esc(t('Dungeon-Master: Regeln anpassen','Dungeon Master: adjust rules'))}</h2>
    <div class="pintro">${esc(t('Ergänze oder ändere Welten, Töne, Völker, Klassen mit Fähigkeiten, Gegenstände, Effekte, Kurven und den Standard-Prompt. Ein Eintrag mit derselben id ersetzt den mitgelieferten, "aus": true nimmt ihn heraus. Das Panel prüft alles, bevor es gilt.','Add or change worlds, tones, peoples, classes with abilities, items, effects, curves and the default prompt. An entry with the same id replaces the shipped one, "aus": true takes it out. The panel checks everything before it counts.'))}</div>
    ${dmPlans(d)}
    <h3 class="sec">${esc(t('Regeln und Katalog','Rules and catalogue'))}</h3>
    <div class="dm-sum">${Object.entries(names).map(([k,n])=>`<span class="pill">${esc(n)} ${S[k]}</span>`).join(' ')}</div>
    <div class="dm-two">${[['erzaehler',t('Stimme des Erzählers','Narrator voice')],['npc',t('Stimme der NPCs','NPC voice')]].map(([k,n])=>{const cur=((d.eigene||{}).stimmen||{})[k]||'';
      return `<div><label>${esc(n)}</label><select class="dmadm-voice" data-k="${k}"><option value="">${esc(t('Standardstimme','Default voice'))}</option>${[...new Set([cur,...(DMA.voices||[])].filter(Boolean))].map(x=>`<option${x===cur?' selected':''}>${esc(x)}</option>`).join('')}</select></div>`}).join('')}</div>
    <label for="dmadmtxt">${esc(t('Deine Ergänzungen (JSON)','Your additions (JSON)'))}</label><textarea id="dmadmtxt" rows="14" data-fest spellcheck="false" class="mono">${esc(txt)}</textarea>
    ${err?`<div class="err dm-adm-err">${err}</div>`:''}
    <details class="adv"><summary>${esc(t('Mitgelieferte Regeln ansehen (zum Kopieren)','See the shipped rules (to copy)'))}</summary><pre class="dm-pre">${esc(JSON.stringify(d.standard,null,2))}</pre></details>
    <div class="row"><button type="button" class="b p" data-dmadm="save">${esc(t('Prüfen und speichern','Check and save'))}</button><button type="button" class="b" data-dmadm="reset">${esc(t('Zurück auf Standard','Back to default'))}</button><button type="button" class="b" data-dmadm="close">${esc(t('Schließen','Close'))}</button></div>`}
document.body.addEventListener('click',async e=>{if(e.target.closest('#dmrules')){dmRules();return}
  const b=e.target.closest('#dmadmcard [data-dmadm]');if(!b)return;const k=b.dataset.dmadm;
  if(k==='close'){$('dmadm').style.display='none';return}
  if(k[0]==='g'){await dmPlanClick(b,k);return}
  if(k==='reset'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich auf Standard?','Really back to default?');return}
    const {r,d}=await apiTry('/api/admin/dungeon',{method:'DELETE'});if(r.ok)dmRulesDraw(d,'');return}
  let own;try{own=JSON.parse($('dmadmtxt').value||'{}')}catch{const {r,d}=await apiTry('/api/admin/dungeon?lang='+dmLang());if(r.ok)dmRulesDraw(Object.assign(d,{eigene:{}}),esc(t('Das ist kein gültiges JSON.','This is not valid JSON.')));return}
  const sv={};document.querySelectorAll('#dmadmcard .dmadm-voice').forEach(x=>{sv[x.dataset.k]=x.value});
  if(Object.values(sv).some(Boolean)||own.stimmen)own.stimmen=sv;
  const keep=$('dmadmtxt').value;const {r,d}=await apiTry('/api/admin/dungeon',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({eigene:own})});
  if(r.ok){dmRulesDraw(d,'');sayToast(t('Regeln gespeichert','Rules saved'));return}
  const g=await apiTry('/api/admin/dungeon?lang='+dmLang());if(!g.r.ok)return;dmRulesDraw(g.d,Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>'):esc(errSay(r.status,d.detail,'')));$('dmadmtxt').value=keep});
// ---------------------------------------------------------------- the admin's stories (Geschichten-Planer)
// a story: idea, goal, foe, places, taboos and 3 to 5 acts with a turning point; „Vorschlag erzeugen“ lets the model
// write all of it from keywords, „↻“ one act again; the panel checks both like typed text before anything is kept
const DMP={d:null,g:null,gid:'',err:'',stich:'',hint:'',busy:false};
function dmPlans(d){const gs=d.geschichten||[],P=d.planer;
  return `<h3 class="sec">${esc(t('Geschichten','Stories'))} · ${gs.length}/${P.max}</h3>
    <div class="fh">${esc(t('Lege fest, wie eine Geschichte verläuft. Wer eine Runde anlegt, wählt sie aus; den Plan sehen nur du und der Gastgeber.','Set how a story runs. Whoever starts a round picks it; only you and the host see the plan.'))}</div>
    ${gs.length?`<div class="ic-list">${gs.map(g=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(g.titel)}</span><small class="ic-meta">${esc(g.welt_name)} · ${esc(g.ton_name)} · ${g.akte.length} ${esc(t('Akte','acts'))}</small></div><button type="button" class="b" data-dmadm="gedit" data-gid="${esc(g.gid)}">${esc(t('Bearbeiten','Edit'))}</button></div>`).join('')}</div>`:''}
    <div class="row"><button type="button" class="b"${gs.length>=P.max?' disabled':''} data-dmadm="gneu">${esc(t('Neue Geschichte','New story'))}</button></div>`}
function dmPlanForm(d){const g=DMP.g,P=d.planer,w=d.wahl;
  const opt=(a,cur)=>a.map(x=>`<option value="${esc(x.id)}"${String(x.id)===String(cur)?' selected':''}>${esc(x.name)}</option>`).join('');
  const nums=[];for(let n=P.akte[0];n<=P.akte[1];n++)nums.push(n);
  const akt=(a,i)=>`<div class="dmp-akt" data-i="${i}"><div class="dm-khead"><b>${esc(t('Akt','Act'))} ${i+1}</b><span><button type="button" class="b" data-dmadm="gakt" data-n="${i+1}"${DMP.busy?' disabled':''} title="${esc(t('Diesen Akt vom Modell neu schreiben lassen','Let the model write this act again'))}">↻ ${esc(t('Neu schreiben','Write again'))}</button>${g.akte.length>P.akte[0]?`<button type="button" class="b" data-dmadm="gminus" data-n="${i}">${esc(t('Entfernen','Remove'))}</button>`:''}</span></div>
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-at" maxlength="60" value="${esc(a.titel||'')}">
    <label>${esc(t('Was geschieht','What happens'))}</label><textarea class="dmp-ai" rows="3" maxlength="${P.inhalt}">${esc(a.inhalt||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Wendepunkt am Ende','Turning point at the end'))}</label><input class="dmp-aw" maxlength="${P.wende}" value="${esc(a.wende||'')}"></div>
    <div><label>${esc(t('Geplante Züge','Planned turns'))}</label><input class="dmp-az" type="number" min="${P.zuege[0]}" max="${P.zuege[1]}" value="${a.zuege||6}"></div></div></div>`;
  return `<h2>${esc(DMP.gid?t('Geschichte bearbeiten','Edit the story'):t('Neue Geschichte','New story'))}</h2><div class="dm-form dmp-form">
    <div class="dm-k"><div class="lbl">✨ ${esc(t('Vom Sprachmodell entwerfen lassen','Let the language model draft it'))}</div>
      <textarea class="dmp-stich" rows="2" maxlength="${P.stichworte}" placeholder="${esc(t('verfluchtes Bergdorf, ein Drache, der nur bewacht, eher düster','a cursed mountain village, a dragon that only guards, rather dark'))}">${esc(DMP.stich)}</textarea>
      <div class="row"><select class="dmp-n" aria-label="${esc(t('Akte','Acts'))}">${nums.map(n=>`<option value="${n}"${n===g.akte.length?' selected':''}>${n} ${esc(t('Akte','acts'))}</option>`).join('')}</select><button type="button" class="b p" data-dmadm="gvor"${DMP.busy?' disabled':''}>${esc(DMP.busy?t('Das Modell schreibt …','The model is writing …'):t('Vorschlag erzeugen','Create a proposal'))}</button></div>
      <small class="mut">${esc(t('Das Modell füllt alle Felder; das Panel prüft Länge, Ton und Tabus. Erst „Speichern“ behält die Geschichte.','The model fills every field; the panel checks length, tone and taboos. Only "Save" keeps the story.'))}</small></div>
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-titel" maxlength="60" value="${esc(g.titel||'')}">
    <div class="dm-two"><div><label>${esc(t('Welt','World'))}</label><select class="dmp-welt">${opt(w.welten,g.welt)}</select></div><div><label>${esc(t('Ton','Tone'))}</label><select class="dmp-ton">${opt(w.toene,g.ton)}</select></div></div>
    <label>${esc(t('Grundidee','Idea'))}</label><textarea class="dmp-idee" rows="3" maxlength="${P.idee}">${esc(g.idee||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Ziel der Helden','The heroes\' goal'))}</label><input class="dmp-ziel" maxlength="${P.ziel}" value="${esc(g.ziel||'')}"></div><div><label>${esc(t('Gegenspieler','Foe'))}</label><input class="dmp-gegner" maxlength="${P.ziel}" value="${esc(g.gegner||'')}"></div></div>
    <label>${esc(t('Schauplätze (mit Komma, bis zu '+P.orte+')','Places (comma separated, up to '+P.orte+')'))}</label><input class="dmp-orte" value="${esc((g.orte||[]).join(', '))}">
    <label>${esc(t('Tabus: kommt nie vor (mit Komma, bis zu '+P.tabus+')','Taboos: never happens (comma separated, up to '+P.tabus+')'))}</label><input class="dmp-tabus" value="${esc((g.tabus||[]).join(', '))}" placeholder="${esc(t('Spinnen, Folter','spiders, torture'))}">
    ${g.akte.map(akt).join('')}
    ${g.akte.length<P.akte[1]?`<div class="row"><button type="button" class="b" data-dmadm="gplus">${esc(t('Akt dazu','Add an act'))}</button></div>`:''}
    <label>${esc(t('Hinweis fürs Neuschreiben eines Akts (frei)','Hint for writing an act again (optional)'))}</label><input class="dmp-hint" maxlength="${P.stichworte}" value="${esc(DMP.hint)}" placeholder="${esc(t('mehr Rätsel, weniger Kampf','more riddles, less fighting'))}">
    ${DMP.err?`<div class="err dm-adm-err">${DMP.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmadm="gsave"${DMP.busy?' disabled':''}>${esc(t('Prüfen und speichern','Check and save'))}</button>${DMP.gid?`<button type="button" class="b danger" data-dmadm="gdel">${esc(t('Löschen','Delete'))}</button>`:''}<button type="button" class="b" data-dmadm="gback">${esc(t('Zurück','Back'))}</button></div></div>`}
function dmPlanRead(){const c=$('dmadmcard'),q=x=>(c.querySelector(x)||{}).value||'',list=x=>q(x).split(',').map(s=>s.trim()).filter(Boolean);
  DMP.stich=q('.dmp-stich');DMP.hint=q('.dmp-hint');
  const ton=q('.dmp-ton');
  return {titel:q('.dmp-titel').trim(),welt:q('.dmp-welt'),ton:/^\d+$/.test(ton)?+ton:ton,lang:dmLang(),idee:q('.dmp-idee').trim(),ziel:q('.dmp-ziel').trim(),
    gegner:q('.dmp-gegner').trim(),orte:list('.dmp-orte'),tabus:list('.dmp-tabus'),
    akte:[...c.querySelectorAll('.dmp-akt')].map(a=>({titel:a.querySelector('.dmp-at').value.trim(),inhalt:a.querySelector('.dmp-ai').value.trim(),
      wende:a.querySelector('.dmp-aw').value.trim(),zuege:Math.floor(+a.querySelector('.dmp-az').value||0)}))}}
const dmPlanErr=(r,d)=>Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>')
  :d.detail==='kein vorschlag'?esc(t('Das Modell hat keinen brauchbaren Vorschlag geliefert. Bitte noch einmal oder mit anderen Stichworten.','The model gave no usable proposal. Please try again or with other keywords.'))
  :d.detail==='sprachmodell pausiert'?esc(t('Das Sprachmodell ist gerade pausiert.','The language model is paused right now.')):esc(errSay(r.status,d.detail,''));
async function dmPlanClick(b,k){const d=DMP.d,w=d.wahl;if(DMP.busy)return;
  if(k==='gneu'){DMP.gid='';DMP.err='';DMP.stich='';DMP.hint='';DMP.g={titel:'',welt:w.welten[0].id,ton:(w.toene[1]||w.toene[0]).id,idee:'',ziel:'',gegner:'',orte:[],tabus:[],
    akte:Array.from({length:d.planer.akte[0]},()=>({titel:'',inhalt:'',wende:'',zuege:6}))};dmRulesDraw(d,'');return}
  if(k==='gedit'){const g=(d.geschichten||[]).find(x=>x.gid===b.dataset.gid);if(!g)return;DMP.gid=g.gid;DMP.err='';DMP.stich='';DMP.hint='';DMP.g=JSON.parse(JSON.stringify(g));dmRulesDraw(d,'');return}
  if(k==='gback'){DMP.g=null;dmRulesDraw(d,'');return}
  const g=dmPlanRead();DMP.g=g;
  if(k==='gplus'){g.akte.push({titel:'',inhalt:'',wende:'',zuege:6});dmRulesDraw(d,'');return}
  if(k==='gminus'){g.akte.splice(+b.dataset.n,1);dmRulesDraw(d,'');return}
  if(k==='gdel'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich löschen?','Really delete?');return}
    const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+DMP.gid+'?lang='+dmLang(),{method:'DELETE'});if(r.ok){DMP.g=null;dmRulesDraw(x,'')}return}
  if(k==='gsave'){const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+(DMP.gid||'neu')+'?lang='+dmLang(),xjson('PUT',g));
    if(r.ok){DMP.g=null;dmRulesDraw(x,'');sayToast(t('Geschichte gespeichert','Story saved'));return}DMP.err=dmPlanErr(r,x);dmRulesDraw(d,'');return}
  const n=Math.floor(+((($('dmadmcard').querySelector('.dmp-n'))||{}).value||g.akte.length));
  const body=k==='gvor'?{welt:g.welt,ton:g.ton,akte:n,stichworte:DMP.stich,tabus:g.tabus,lang:g.lang}:{plan:g,n:+b.dataset.n,hinweis:DMP.hint};
  if(k==='gvor'&&DMP.stich.trim().length<3){DMP.err=esc(t('Bitte ein paar Stichworte eingeben.','Please enter a few keywords.'));dmRulesDraw(d,'');return}
  DMP.busy=true;DMP.err='';dmRulesDraw(d,'');
  const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+(k==='gvor'?'vorschlag':'akt'),xjson('POST',body));DMP.busy=false;
  if(r.ok&&x.plan){DMP.g=Object.assign(x.plan,{lang:g.lang})}else DMP.err=dmPlanErr(r,x);
  if(DMP.g&&$('dmadm').style.display==='grid')dmRulesDraw(DMP.d,'')}
