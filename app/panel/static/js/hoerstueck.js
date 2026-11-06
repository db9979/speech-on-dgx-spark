// Hörstück aus einer Mappe (hoerstueck.py, plan open-notebook Stufe 5, Push 5a): the tab „Hörstück“ of a Mappe
// (mappen.js mpDetail calls hsFor and hsShow; Mappen ruhiger, plan mappen-layout). Length 5/10/20 min, 2 or 3 voices,
// „Erstellen“ in one row; the chosen (else the newest finished) Hörstück as a card with its player, ⋯ (Herunterladen,
// An Telegram, Löschen) and the script folded below; the others as rows with their state and progress (the script,
// then line by line in quiet minutes). In the script every line with its voice (A Moderation, B Fachstimme,
// C Nachfrage, the panel's fixed roles) and, for a line with a place, a chip that opens the document. The panel checked
// every line by fixed rules; titles and lines are the model's or the documents' words: only through esc(), never markup.
// Push 5b: the line being heard is marked while the player plays (the start "ab" of every line, .ld-row.on), its time
// chip plays from there; „An Telegram" sends it to the own linked chat; the script comes in the page's language (L).
// „Sofort erstellen" (only when the server says the admin asks, D.sofort; the server checks it again): a new one at
// once, or „Jetzt erstellen" for one that waits or speaks; without the quiet minutes and the day's limit, speech first.
const HS={mid:'',data:null,sel:'',one:null,laenge:5,stimmen:2,msg:'',seq:0,timer:null};
const HS_STAND={wartet:['wartet','waiting'],sprechen:['spricht','speaking'],fertig:['fertig','done'],leer:['zu wenig','too little'],x:['ging nicht','did not work']};
const HS_WEG={sprecher:['Sprecher nicht aus der Liste','speaker not from the list'],stelle:['ohne gültige Fundstelle','without a valid place'],
  zahl:['Zahl nicht im Dokument','number not in the document'],form:['Form, Link oder Befehl','form, link or command'],
  ueberleitung:['Überleitung mit Zahl, Name oder fremdem Wort','transition with a number, name or unknown word'],
  anteil:['zu viele Überleitungen','too many transitions'],lang:['zu lang','too long'],doppelt:['doppelt','twice']};
const hsUrl=(mid,hid,x)=>hid?'/api/profile/hoerstueck/'+encodeURIComponent(hid)+(x||''):'/api/profile/mappen/'+encodeURIComponent(mid)+'/hoerstuecke';
const hsMin=s=>{s=Math.max(0,Math.round(s||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
const hsAva=(sp,R)=>`<span class="ld-ava" title="${esc(R&&R[sp]?t(R[sp][0],R[sp][1]):sp)}" aria-hidden="true">${esc(sp)}</span>`;
// what the work on it waits for right now (hoerstueck._warten, fixed words of the server) and why a broken one broke
const HS_WARTEN={gespraech:['wartet: jemand spricht (echte Sprache geht vor)','waits: somebody speaks (real speech goes first)'],
  wartung:['wartet: Wartung des Sprachmodells','waits: language model maintenance'],andere:['wartet: andere Hintergrundarbeit läuft','waits: other background work runs'],
  sprachausgabe:['wartet: Sprachausgabe fehlt','waits: speech output missing']};
const HS_FEHLER={modell:['das Sprachmodell lieferte kein brauchbares Drehbuch','the language model gave no usable script'],
  ffmpeg:['Zusammensetzen ging nicht','putting it together failed'],mappe:['die Mappe ist weg','the collection is gone'],
  'kein text':['kein Text in der Mappe','no text in the collection'],'zu wenig':['zu wenig geprüfte Zeilen','too few checked lines']};
function hsSub(s){const st=t(...(HS_STAND[s.stand]||HS_STAND.x));const w=HS_WARTEN[s.warten]?' · '+t(...HS_WARTEN[s.warten]):'';
  if(s.erzwungen&&s.stand==='wartet')return t('Wird sofort erstellt · ','Being made now · ')+(w?w.slice(3):t('Drehbuch entsteht','script being written'));
  if(s.erzwungen&&s.stand==='sprechen')return t(`Wird sofort erstellt · ${s.fertig_zeilen} von ${s.zeilen} Zeilen gesprochen`,`Being made now · ${s.fertig_zeilen} of ${s.zeilen} lines spoken`)+w;
  if(s.stand==='wartet')return s.laeuft?t('Drehbuch entsteht','Script being written')+w:t('Drehbuch folgt, sobald niemand spricht','Script follows as soon as nobody speaks');
  if(s.stand==='sprechen')return t(`Drehbuch fertig · ${s.fertig_zeilen} von ${s.zeilen} Zeilen gesprochen · wartet auf ruhige Minuten`,`Script done · ${s.fertig_zeilen} of ${s.zeilen} lines spoken · waits for quiet minutes`);
  if(s.stand==='leer')return t('Daraus lässt sich kein Hörstück machen: zu wenig geprüfte Zeilen','No audio overview can be made of it: too few checked lines');
  if(s.stand==='x')return (HS_FEHLER[s.fehler]?t(...HS_FEHLER[s.fehler])+' · ':'')+t('ging nicht; „Löschen“ und neu erstellen','did not work; delete and make again');
  const weg=Object.values(s.verworfen||{}).reduce((a,b)=>a+b,0);
  return [docDate(s.made),hsMin(s.dauer_s)+' min',t(`${s.stimmen} Stimmen`,`${s.stimmen} voices`),t(`${s.zeilen} Zeilen, ${weg} verworfen`,`${s.zeilen} lines, ${weg} dropped`)].join(' · ')||st}
function hsRow(s){const kind=s.stand==='fertig'?'ok':s.stand==='leer'||s.stand==='x'?'bad':'warn';
  const pct=s.zeilen?Math.round(100*s.fertig_zeilen/s.zeilen):0;
  return `<div class="ld-row${s.id===HS.sel?' on':''}" role="button" tabindex="0" data-hssel="${esc(s.id)}"><span class="ld-ico" aria-hidden="true">${ic('speaker')}</span><span class="ld-mid"><b>${esc(s.titel||t('Hörstück','Audio overview'))}</b><small>${esc(hsSub(s))}</small>`+
    (s.geaendert?`<small>${esc(t('Die Mappe hat sich seitdem geändert.','The collection has changed since.'))}</small>`:'')+
    (s.stand==='sprechen'?`<div class="mpbar" aria-hidden="true"><i style="width:${pct}%"></i></div>`:'')+
    `</span><span class="ld-right"><span class="ld-st ${kind}">${esc(t(...(HS_STAND[s.stand]||HS_STAND.x)))}</span></span></div>`}
function hsLine(x,R,i){const at=typeof x.ab==='number'?`<button type="button" class="ld-chip" data-hsab="${x.ab}" title="${esc(t('Ab hier anhören','Listen from here'))}">${esc(hsMin(x.ab))}</button>`:'';
  const right=at+(x.art==='inhalt'?(x.da?`<button type="button" class="ld-chip" data-hsdoc="${esc(x.doc)}" title="${esc(t('Dokument öffnen','Open the document'))}">${esc([x.dok,x.page?t('S. ','p. ')+x.page:'',x.part].filter(Boolean).join(' · '))}</button>`:`<span class="ld-badge off">${esc(t('Dokument weg','document gone'))}</span>`)
    :`<span class="ld-badge off">${esc(x.art==='fest'?t('fest','fixed'):t('Überleitung','transition'))}</span>`);
  return `<div class="ld-row" data-hsi="${i}">${hsAva(x.sprecher,R)}<span class="ld-mid"><span>${esc(x.text)}</span></span><span class="ld-right">${right}</span></div>`}
// the chosen Hörstück (else the newest finished one) as a card: title, date · length · voices, ⋯ (Herunterladen,
// An Telegram, Löschen), the player and the script folded („Drehbuch · N Zeilen“) with the roles and what was dropped
function hsCard(){const o=HS.one;if(!o||o.id!==HS.sel)return'';const R=o.rollen;
  const weg=Object.entries(o.verworfen||{}).filter(([,n])=>n).map(([k,n])=>n+' '+t(...(HS_WEG[k]||[k,k])));
  const sub=o.stand==='fertig'?[docDate(o.made),hsMin(o.dauer_s)+' min',t(`${o.stimmen} Stimmen`,`${o.stimmen} voices`)].filter(Boolean).join(' · '):hsSub(o);
  const ton=hsUrl('',o.id,'/ton'),kind=o.stand==='fertig'?'ok':o.stand==='leer'||o.stand==='x'?'bad':'warn';
  const pct=o.zeilen?Math.round(100*o.fertig_zeilen/o.zeilen):0;
  const roles=['A','B','C'].filter(sp=>R&&R[sp]&&o.drehbuch.some(x=>x.sprecher===sp)).map(sp=>`${hsAva(sp,R)} ${esc(t(R[sp][0],R[sp][1]))}`).join(' ');
  const menu=`<span class="ic-menu"><button type="button" class="b mpmore" data-mpmenu="1" aria-haspopup="true" aria-expanded="false" aria-label="${esc(t('Mehr zum Hörstück','More on the audio overview'))}" title="${esc(t('Mehr zum Hörstück','More on the audio overview'))}">${ic('more')}</button><div class="ic-pop" hidden>`+
    (o.ton?`<a href="${esc(ton)}" download="hoerstueck.ogg">${ic('download')}${esc(t('Herunterladen','Download'))}</a>`:'')+
    (o.ton&&o.telegram?`<button type="button" data-hstg="${esc(o.id)}">${ic('send')}${esc(t('An Telegram','To Telegram'))}</button>`:'')+
    (HS.data&&HS.data.sofort&&!o.erzwungen&&(o.stand==='wartet'||o.stand==='sprechen')?`<button type="button" data-hsnow="${esc(o.id)}"${HS.data.sofort_frei?'':' disabled'}>${ic('bolt')}${esc(t('Jetzt erstellen','Make it now'))}</button>`:'')+
    `<button type="button" class="danger" data-hsdel="${esc(o.id)}">${ic('trash')}${esc(t('Löschen','Delete'))}</button></div></span>`;
  return `<div class="mpcard"><div class="mptop"><span class="mpname"><b>${esc(o.titel||t('Hörstück','Audio overview'))}</b><small>${esc(sub)}</small></span>`+
    (o.stand==='fertig'?'':`<span class="ld-st ${kind}">${esc(t(...(HS_STAND[o.stand]||HS_STAND.x)))}</span>`)+menu+`</div>`+
    (o.geaendert?`<p class="mut ld-note">${esc(t('Die Mappe hat sich seitdem geändert.','The collection has changed since.'))}</p>`:'')+
    (o.ton?`<audio controls preload="none" src="${esc(ton)}"></audio>`:'')+
    (o.stand==='sprechen'?`<div class="mpbar" aria-hidden="true"><i style="width:${pct}%"></i></div>`:'')+
    (o.ton&&!o.telegram&&typeof TG_ON!=='undefined'&&TG_ON?`<p class="mut ld-note">${esc(t('„An Telegram“ geht, sobald Telegram verknüpft ist und Persönliches dort erlaubt ist: Ich → Telegram','"To Telegram" works once Telegram is linked and personal data is allowed there: Me → Telegram'))}</p>`:'')+
    (o.drehbuch.length?`<details class="hsscript"${HS.script?' open':''}><summary>${esc(t(`Drehbuch · ${o.drehbuch.length} Zeilen`,`Script · ${o.drehbuch.length} lines`)+(o.stand==='sprechen'?t(` · ${o.fertig_zeilen} gesprochen`,` · ${o.fertig_zeilen} spoken`):''))}</summary>`+
      (roles?`<div class="hsroles">${roles}</div>`:'')+o.drehbuch.map((x,i)=>hsLine(x,R,i)).join('')+
      (weg.length?`<p class="mut ld-note">${esc(t('Verworfen: ','Dropped: ')+weg.join(', '))}</p>`:'')+`</details>`:'')+`</div>`}
// the tab Hörstück of a Mappe: length · voices · Erstellen (a normal button, 2a) · today's count in one row, the card,
// then the other Hörstücke as rows with their state
function hsPaint(box){const D=HS.data;if(!box)return;
  if(!D){box.innerHTML=`<p class="mut ld-note">${esc(HS.msg||t('Lade die Hörstücke …','Loading the audio overviews …'))}</p>`;return}
  const seg=(k,vals,lab)=>`<span class="segc" role="group" aria-label="${esc(lab)}">${vals.map(v=>`<button type="button" class="${HS[k]===v?'on':''}" aria-pressed="${HS[k]===v}" data-hs${k}="${v}">${esc(k==='laenge'?v+' min':String(v))}</button>`).join('')}</span>`;
  const full=D.alle>=D.max,limit=!D.frei&&D.heute>=D.grenze;
  box.innerHTML=`<div class="hsmake"><span class="hsopt"><span>${esc(t('Länge','Length'))}</span>${seg('laenge',D.laengen,t('Länge','Length'))}</span>`+
    `<span class="hsopt"><span>${esc(t('Stimmen','Voices'))}</span>${seg('stimmen',D.stimmen,t('Stimmen','Voices'))}</span>`+
    `<button type="button" class="b" data-hsmake="1"${full||limit?' disabled':''} title="${esc(t('läuft in ruhigen Minuten','runs in quiet minutes'))}">${ic('play')}${esc(t('Erstellen','Make'))}</button>`+
    (D.sofort?`<button type="button" class="b" data-hsmake="sofort"${full||!D.sofort_frei?' disabled':''} title="${esc(t('Nur Admin: ohne ruhige Minuten und Tagesgrenze; echte Sprache geht trotzdem vor','Admin only: without quiet minutes and the day limit; real speech still goes first'))}">${ic('bolt')}${esc(t('Sofort erstellen','Make now'))}</button>`:'')+
    `<small>${esc(full?t(`Höchstens ${D.max} Hörstücke; lösch erst eins.`,`At most ${D.max} audio overviews; delete one first.`):limit?t('Für heute ist die Grenze erreicht.','The limit for today is reached.'):D.frei?t(`heute ${D.heute} · ohne Tageslimit`,`today ${D.heute} · no daily limit`):t(`heute ${D.heute} von ${D.grenze}`,`today ${D.heute} of ${D.grenze}`))}</small></div>`+
    `<p class="mut ld-note hsmsg" role="status"${HS.msg?'':' hidden'}>${esc(HS.msg)}</p>`+
    (D.stuecke.length?`<div class="ld-grp"><span>${esc(t(`${D.stuecke.length} Hörstücke`,`${D.stuecke.length} audio overviews`))}</span></div>`+hsCard()+D.stuecke.filter(s=>s.id!==HS.sel).map(hsRow).join('')
      :`<div class="ld-empty mut">${esc(t('Noch kein Hörstück aus dieser Mappe.','No audio overview of this collection yet.'))}</div>`)}
async function hsLoad(){const mid=HS.mid,seq=++HS.seq;const {r,d}=await apiTry(hsUrl(mid));if(seq!==HS.seq||mid!==HS.mid)return;
  if(r.ok){HS.data=d;HS.msg=HS.msg||''}else{HS.data=null;HS.msg=errSay(r.status,d.detail,'')}
  // the card shows the chosen one, else the newest finished one
  if(HS.data&&!HS.data.stuecke.some(s=>s.id===HS.sel)){const f=HS.data.stuecke.find(s=>s.stand==='fertig');HS.sel=f?f.id:'';HS.one=null}
  if(HS.sel){const x=await apiTry(hsUrl('',HS.sel));if(seq!==HS.seq)return;HS.one=x.r.ok?x.d:null;if(!x.r.ok)HS.sel=''}
  hsPaint(document.querySelector('#mpview .hsbox'));if(typeof mpSeg==='function')mpSeg();clearTimeout(HS.timer);
  // something waits or speaks: look again while the part is on screen
  if(HS.data&&HS.data.stuecke.some(s=>s.stand==='wartet'||s.stand==='sprechen'))HS.timer=setTimeout(()=>{const b=document.querySelector('#mpview .hsbox');
    const a=b&&b.querySelector('audio');if(b&&b.offsetParent!==null&&!document.hidden&&HS.mid===mid&&!(a&&!a.paused))hsLoad()},30e3)}
// mappen.js mpDetail calls hsFor with the shown Mappe (only while the admin released Hörstücke, o.hoerstueck), the
// tab Hörstück then hsShow with its box; hsN is the count in the segment
window.hsFor=o=>{if(!o||!o.hoerstueck){HS.mid='';clearTimeout(HS.timer);return}
  if(HS.mid!==o.id){HS.mid=o.id;HS.data=null;HS.sel='';HS.one=null;HS.msg='';HS.script=false;hsLoad()}};
window.hsN=mid=>HS.mid===mid&&HS.data?HS.data.stuecke.length:'';
window.hsShow=(box,o)=>{if(!box||!o||!o.hoerstueck)return;hsFor(o);hsPaint(box)};
document.body.addEventListener('toggle',e=>{if(e.target.matches&&e.target.matches('#mpview .hsbox details.hsscript'))HS.script=e.target.open},true);
document.body.addEventListener('click',async e=>{const b=e.target.closest('#mpview .hsbox [data-hslaenge],#mpview .hsbox [data-hsstimmen],#mpview .hsbox [data-hsmake],#mpview .hsbox [data-hssel],#mpview .hsbox [data-hsdel],#mpview .hsbox [data-hsdoc],#mpview .hsbox [data-hsab],#mpview .hsbox [data-hstg],#mpview .hsbox [data-hsnow]');if(!b)return;
  const D=b.dataset,box=b.closest('.hsbox');
  if(D.hslaenge){HS.laenge=+D.hslaenge;hsPaint(box);return}
  if(D.hsstimmen){HS.stimmen=+D.hsstimmen;hsPaint(box);return}
  if(D.hsdoc){if(typeof docView==='function')docView(D.hsdoc);return}
  if(D.hssel){HS.sel=HS.sel===D.hssel?'':D.hssel;HS.one=null;await hsLoad();return}
  if(D.hsab){const a=box.querySelector('audio');if(a){a.currentTime=+D.hsab;a.play().catch(()=>{})}return}
  if(D.hstg){b.disabled=true;const {r,d}=await apiTry(hsUrl('',D.hstg,'/telegram'),xjson('POST',{}));
    HS.msg=r.ok?t('An deinen Telegram-Chat geschickt.','Sent to your Telegram chat.'):errSay(r.status,d.detail,'');b.disabled=false;
    const m=box.querySelector('.hsmsg');if(m){m.textContent=HS.msg;m.hidden=!HS.msg}return}   // no new paint: the player keeps playing
  if(D.hsnow){b.disabled=true;const {r,d}=await apiTry(hsUrl('',D.hsnow,'/sofort'),xjson('POST',{}));
    HS.msg=r.ok?t('Wird jetzt erstellt; echte Sprache geht vor.','Being made now; real speech goes first.'):errSay(r.status,d.detail,'');await hsLoad();return}
  if(D.hsmake){b.disabled=true;const now=D.hsmake==='sofort';
    const {r,d}=await apiTry(hsUrl(HS.mid)+(now?'/sofort':''),xjson('POST',{laenge:HS.laenge,stimmen:HS.stimmen,sprache:L==='en'?'en':'de'}));
    HS.msg=r.ok?(now?t('Wird jetzt erstellt; echte Sprache geht vor.','Being made now; real speech goes first.'):t('Eingereiht: das Drehbuch entsteht in der nächsten ruhigen Minute, dann Zeile für Zeile.','Queued: the script is made in the next quiet minute, then line by line.')):errSay(r.status,d.detail,'');
    if(r.ok)HS.sel=d.id;await hsLoad();return}
  if(D.hsdel){if(!confirm(t('Hörstück löschen?','Delete the audio overview?')))return;b.disabled=true;
    const {r,d}=await apiTry(hsUrl('',D.hsdel),{method:'DELETE'});HS.msg=r.ok?t('Gelöscht.','Deleted.'):errSay(r.status,d.detail,'');
    if(r.ok){HS.sel='';HS.one=null}await hsLoad()}});
// the line being heard: the last one whose start lies behind the player's time (timeupdate does not bubble: capture)
function hsMark(a){const o=HS.one,box=a.closest('.hsbox');if(!o||!box)return;let cur=-1;
  o.drehbuch.forEach((x,i)=>{if(typeof x.ab==='number'&&x.ab<=a.currentTime+0.05)cur=i});
  box.querySelectorAll('[data-hsi]').forEach(r=>{const on=+r.dataset.hsi===cur&&!a.paused;if(r.classList.contains('on')!==on){r.classList.toggle('on',on);
    if(on){r.setAttribute('aria-current','true');if(r.getBoundingClientRect().bottom>innerHeight||r.getBoundingClientRect().top<0)r.scrollIntoView({block:'nearest'})}else r.removeAttribute('aria-current')}})}
['timeupdate','pause','seeked','ended'].forEach(k=>document.body.addEventListener(k,e=>{const a=e.target;if(a&&a.matches&&a.matches('#mpview .hsbox audio'))hsMark(a)},true));
document.body.addEventListener('keydown',e=>{const r=e.target.closest&&e.target.closest('#mpview .hsbox [data-hssel]');
  if(r&&(e.key==='Enter'||e.key===' ')){e.preventDefault();r.click()}});

// Admin (Funktionen → Eigene Dokumente → Mappen → Hörstück aus einer Mappe): the three voices fill the hidden list field
// chat.hoerstueck_stimmen (saved with the other settings; „-“ = the standard voice, with VoiceDesign its description)
async function hsVoicesAdmin(){const box=$('hsvoices'),el=$('chat.hoerstueck_stimmen');if(!box||!el||document.body.classList.contains('mgr'))return;
  let vs=[];try{vs=((await (await api('/api/tts/voices')).json()).voices||[]).filter(x=>typeof x==='string'&&/^[A-Za-z0-9_\-]{1,40}$/.test(x))}catch{}
  const R={A:['Moderation','Host'],B:['Fachstimme','Expert'],C:['Nachfrage','Questions']};
  const paint=()=>{const cur=el.value.split(/[\s,;]+/).filter(Boolean);
    box.innerHTML=['A','B','C'].map((sp,i)=>{const v=cur[i]||'-',opts=['-',...vs];if(v!=='-'&&!opts.includes(v))opts.push(v);
      return `<label class="row">${esc(sp+' · '+t(...R[sp]))} <select data-hsvoice="${i}" aria-label="${esc(t('Stimme ','Voice ')+sp)}">${opts.map(x=>`<option value="${esc(x)}"${x===v?' selected':''}>${esc(x==='-'?t('Standardstimme','Standard voice'):x)}</option>`).join('')}</select></label>`}).join('')};
  paint();box.onchange=e=>{const s=e.target.closest('[data-hsvoice]');if(!s)return;
    const cur=el.value.split(/[\s,;]+/).filter(Boolean);while(cur.length<3)cur.push('-');cur[+s.dataset.hsvoice]=s.value||'-';
    el.value=cur.join(', ');el.dispatchEvent(new Event('input',{bubbles:true}))};
  el.addEventListener('change',paint)}
window.hsVoicesAdmin=hsVoicesAdmin;
