// KI-Dungeon-Master: the admin's side (Prüfung 15.11., Punkt 10, dungeon.js split): the tab „Regeln“ with the
// catalog, the own stories and the story planner. Loaded by dungeonlader.js right after dungeon.js, so it uses that
// file's helpers (DM, dgAct, dmLang, …); the game itself never needs this file's names before a click.
// ---------------------------------------------------------------- the admin's rules: the tab „Regeln“ (dungeon_regelseite.py)
// Dominik 2026-10-24 „die regel seite sollte für den admin hier sein“, „unübersichtlich“: the sections on the left,
// the chosen one on the right; a part of the catalog as a list with picture, values and the balance mark, the
// detail below it. Without a profile (admin only) the same page opens as a card from Funktionen.
const DMR={teil:'geschichten',k:{},sel:'',q:'',f:'alle',m:'alle',gw:'alle',edit:null,err:'',neu:{},busy:'',v:1,welt:{},st:null};
const DMRKAT=['gegenstaende','gegner','klassen','voelker','hintergruende','welten','toene','zustaende','tabellen',
  'runen','runenwoerter','effekte','ortsarten','raeume','fallen','raetsel','begegnungen','stillstand','zahlen'];
const DMRTRENN=new Set(['runen','ortsarten','zahlen']);   // a line in the menu before these (Dominik 2026-10-28 „fehlt sonst noch etwas unter den regeln?“)
// the parts with a list and a detail: the rules, and the people of the catalog while it is on (Personen-Katalog 1)
const dmRKats=()=>{const k=DMRKAT.slice();if(DMP.d&&DMP.d.personen_an)k.splice(k.indexOf('tabellen')+1,0,'personen');return k};
const dmRNamen=()=>({geschichten:t('Geschichten','Stories'),personen:t('Personen (NSC)','People (NPC)'),gegenstaende:t('Gegenstände','Items'),gegner:t('Gegner (Bestiarium)','Foes (bestiary)'),klassen:t('Klassen','Classes'),
  voelker:t('Völker','Peoples'),hintergruende:t('Hintergründe','Backgrounds'),welten:t('Welten','Worlds'),toene:t('Töne','Tones'),zustaende:t('Zustände','Conditions'),tabellen:t('Tabellen','Tables'),
  runen:t('Runen','Runes'),runenwoerter:t('Runenwörter','Runewords'),effekte:t('Effekte','Effects'),ortsarten:t('Ortsarten der Karte','Place kinds of the map'),raeume:t('Räume der Gewölbe','Rooms of the vaults'),
  fallen:t('Fallen','Traps'),raetsel:t('Rätsel','Riddles'),begegnungen:t('Begegnungen unterwegs','Encounters on the way'),stillstand:t('Stillstand-Ereignisse','Stall events'),zahlen:t('Zahlen und Tabellen','Numbers and tables'),
  stimmen:t('Stimmen','Voices'),bilder:t('Bilder','Pictures'),musik:t('Musik','Music'),gaeste:t('Gäste mit E-Mail','Guests with e-mail'),ankommt:t('Wie es ankommt','How it lands'),pruefstand:t('Balance-Prüfstand','Balance bench'),erzaehlstand:t('Erzähler-Prüfstand','Narrator bench'),erzaehlfehler:t('Erzähler-Fehler','Narrator errors'),json:t('Für Fortgeschrittene (JSON)','Advanced (JSON)')});
const dmRTab=()=>!!(PROFILE&&DM.on&&ADMIN);
async function dmRules(){if(dmRTab()&&$('dmroot')){icTabSet('dungeon','regeln');goSec('dungeon');return}
  let m=$('dmadm');if(!m){m=document.createElement('div');m.id='dmadm';m.className='modal';
    m.innerHTML='<div class="card modalcard dmadmcard" id="dmadmcard"></div>';document.body.appendChild(m)}
  m.style.display='grid';dmRulesLoad()}
function dmRulesBox(){const w=document.createElement('div');w.className='dm-regeln';w.innerHTML='<div class="dm-rcard" id="dmadmcard"></div>';setTimeout(dmRulesLoad,0);return w}
async function dmRulesLoad(){const c=$('dmadmcard');if(!c)return;c.innerHTML=`<div class="mut">${esc(t('Lade die Regeln …','Loading the rules …'))}</div>`;
  DMP.g=null;const {r,d}=await apiTry('/api/admin/dungeon?lang='+dmLang());if(!$('dmadmcard'))return;if(!r.ok){$('dmadmcard').innerHTML=`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`;return}
  try{DMA.voices=((await (await api('/api/tts/voices')).json()).voices||[]).filter(x=>typeof x==='string')}catch{DMA.voices=[]}dmRulesDraw(d,'')}
// „Gäste mit E-Mail“ (dungeon_gast.py): the mailbox the codes and „Du bist dran“ go from, and the numbers
function dmGastAdm(g){if(!g||!g.an)return `<div class="fh">${esc(t('Aus. Gäste mit E-Mail sind nicht freigegeben.','Off. Guests with e-mail are not released.'))}</div>`;
  return `<div class="pintro">${esc(t('Gäste bekommen einen Code und auf Wunsch „Du bist dran“ von diesem Postfach. Der Spark speichert nur einen Hash der Adresse, die Adresse selbst nur versiegelt, wenn ein Gast Zug-Mails will.','Guests get a code and, if they want, "Your turn" from this mailbox. The Spark keeps only a hash of the address, the address itself only sealed when a guest wants turn mails.'))}</div>
    <div class="row"><select id="dmgastpf" aria-label="${esc(t('Postfach','Mailbox'))}"><option value="">${esc(t('Kein Postfach','No mailbox'))}</option>${g.postfaecher.map(x=>`<option value="${esc(x.k)}"${x.k===g.absender?' selected':''}>${esc(x.name)}</option>`).join('')}</select><button type="button" class="b" data-dmadm="mailpf">${esc(t('Sichern','Save'))}</button></div>
    <div class="dm-sum"><span class="pill${g.bereit?' ok':' warn'}">${esc(g.bereit?t('bereit','ready'):t('kein Postfach mit Ausgangsserver','no mailbox with outgoing server'))}</span> <span class="pill">${esc(t('Gast-Konten','Guest accounts'))} ${g.konten}</span> <span class="pill">${esc(t('mit Zug-Mail','with turn mail'))} ${g.zugmail}</span> <span class="pill">${esc(t('Helden','heroes'))} ${g.helden}</span> <span class="pill">${esc(t('Mails heute','mails today'))} ${g.mails_heute}</span></div>`}
function dmRulesDraw(d,err){const c=$('dmadmcard');if(!c)return;DMP.d=d;const S=d.summe,N=dmRNamen(),tab=!!c.closest('.dm-regeln');
  const n={geschichten:(d.geschichten||[]).length,gegenstaende:S.gegenstaende,klassen:S.klassen,voelker:S.voelker,welten:S.welten,toene:S.toene};
  for(const k of dmRKats())if(DMR.k[k])n[k]=DMR.k[k].zeilen.length;
  const nb=k=>`<button type="button" class="${DMR.teil===k?'on':''}" data-dmrteil="${k}"${DMR.teil===k?' aria-current="true"':''}><span>${esc(N[k])}</span>${n[k]!=null?`<small>${n[k]}</small>`:''}</button>`;
  const nav=`<nav class="dm-rnav" aria-label="${esc(t('Teile der Regeln','Parts of the rules'))}">${nb('geschichten')}${dmRKats().map(k=>(DMRTRENN.has(k)?'<hr>':'')+nb(k)).join('')}<hr>${['stimmen','bilder','musik','gaeste','ankommt','pruefstand','erzaehlstand','erzaehlfehler'].map(nb).join('')}<hr>${nb('json')}</nav>`;
  c.innerHTML=`<div class="dm-rhead"><h2>${esc(t('Dungeon-Master: Regeln','Dungeon Master: rules'))}</h2>${tab?'':`<button type="button" class="b" data-dmadm="close">${esc(t('Schließen','Close'))}</button>`}</div>
    <div class="dm-rlay">${nav}<div class="dm-rin">${dmRTeil(d,err)}</div></div>`;
  if(DMR.teil==='musik'&&window.dmMusikAdm)dmMusikAdm();
  if(DMR.teil==='pruefstand')dmPruefLook();
  if(DMR.teil==='erzaehlstand')dmErzLook();
  if(DMR.teil==='erzaehlfehler')dmFallLook();
  if(dmRKats().includes(DMR.teil)&&!DMR.k[DMR.teil])dmKatLoad(DMR.teil)}
function dmRTeil(d,err){const k=DMR.teil,N=dmRNamen(),h=`<h3 class="sec">${esc(N[k])}</h3>`,E=err?`<div class="err dm-adm-err">${err}</div>`:'';
  if(k==='geschichten')return DMP.g?dmPlanForm(d):dmPlans(d)+E;
  if(dmRKats().includes(k))return dmKat(k);
  if(k==='stimmen')return h+`<div class="fh">${esc(t('Drei feste Stimmen, alle verschieden: der Erzähler, NPCs (Männer) und NPCs (Frauen). Sie sprechen, wenn keine beschriebene Stimme (VoiceDesign) da ist; wörtliche Rede in der Erzählung spricht immer die Figur, nie der Erzähler.','Three fixed voices, all different: the narrator, NPCs (men) and NPCs (women). They speak when no described voice (VoiceDesign) is there; quoted speech in the narration is always spoken by the character, never by the narrator.'))}</div>
    <div class="dm-two">${[['erzaehler',t('Stimme des Erzählers','Narrator voice')],['npc',t('NPCs (Männer)','NPCs (men)')],['npc_w',t('NPCs (Frauen)','NPCs (women)')]].map(([v,nm])=>{const cur=((d.eigene||{}).stimmen||{})[v]||'',grund=((d.standard||{}).stimmen||{})[v]||'';
      return `<div><label>${esc(nm)}</label><select class="dmadm-voice" data-k="${v}"><option value="">${esc(grund?t('Voreinstellung','Preset')+' ('+grund+')':t('Standardstimme','Default voice'))}</option>${[...new Set([cur,...(DMA.voices||[])].filter(Boolean))].map(x=>`<option${x===cur?' selected':''}>${esc(x)}</option>`).join('')}</select></div>`}).join('')}</div>
    ${E}<div class="row"><button type="button" class="b p" data-dmadm="save">${esc(t('Speichern','Save'))}</button></div>`;
  if(k==='bilder')return dmThumbsPics(d);
  if(k==='musik')return '<div id="dmmusikadm"></div>';
  if(k==='pruefstand')return h+`<div id="dmpruef"><div class="mut">${esc(t('Lade …','Loading …'))}</div></div>`;
  if(k==='erzaehlstand')return h+`<div id="dmerzst"><div class="mut">${esc(t('Lade …','Loading …'))}</div></div>`;
  if(k==='erzaehlfehler')return h+`<div id="dmfall"><div class="mut">${esc(t('Lade …','Loading …'))}</div></div>`;
  if(k==='gaeste')return h+dmGastAdm(d.gastmail)+E;
  if(k==='ankommt')return h+(dmThumbsAdmin(d.daumen)||`<div class="fh">${esc(t('Noch keine 👍 oder 👎 in einer Runde.','No 👍 or 👎 in a round yet.'))}</div>`);
  const names={welten:t('Welten','Worlds'),toene:t('Töne','Tones'),voelker:t('Völker','Peoples'),klassen:t('Klassen','Classes'),faehigkeiten:t('Fähigkeiten','Abilities'),gegenstaende:t('Gegenstände','Items'),seltenheit:t('Seltenheiten','Rarities'),effekte:t('Effekte','Effects'),werte:t('Werte','Values')};
  return h+`<div class="pintro">${esc(t('Ergänze oder ändere Welten, Töne, Völker, Klassen mit Fähigkeiten, Gegenstände, Effekte, Kurven und den Standard-Prompt. Ein Eintrag mit derselben id ersetzt den mitgelieferten, "aus": true nimmt ihn heraus. Das Panel prüft alles, bevor es gilt.','Add or change worlds, tones, peoples, classes with abilities, items, effects, curves and the default prompt. An entry with the same id replaces the shipped one, "aus": true takes it out. The panel checks everything before it counts.'))}</div>
    <div class="dm-sum">${Object.entries(names).map(([x,nm])=>`<span class="pill">${esc(nm)} ${d.summe[x]}</span>`).join(' ')}</div>
    <label for="dmadmtxt">${esc(t('Deine Ergänzungen (JSON)','Your additions (JSON)'))}</label><textarea id="dmadmtxt" rows="14" data-fest spellcheck="false" class="mono">${esc(JSON.stringify(d.eigene||{},null,2))}</textarea>${E}
    <details class="adv"><summary>${esc(t('Mitgelieferte Regeln ansehen (zum Kopieren)','See the shipped rules (to copy)'))}</summary><pre class="dm-pre">${esc(JSON.stringify(d.standard,null,2))}</pre></details>
    <div class="row"><button type="button" class="b p" data-dmadm="save">${esc(t('Prüfen und speichern','Check and save'))}</button><button type="button" class="b" data-dmadm="reset">${esc(t('Zurück auf Standard','Back to default'))}</button></div>`}
const dmThumbsPics=d=>`<div id="dmbilder">${dmDingAdmin(d.dingbilder)||`<div class="fh">${esc(t('Bilder für Ausrüstung und Zauber sind aus.','Pictures for gear and spells are off.'))}</div>`}</div>`;
// ---- one part of the catalog: search, filters, the list with picture and mark, the detail with „Ändern“ and „Nochmal malen“
// peoples, classes and backgrounds are shown and painted in the world chosen above the list (DMR.welt per part)
const dmRWelt=teil=>DMR.welt[teil]?'&welt='+encodeURIComponent(DMR.welt[teil]):'';
async function dmKatLoad(teil){const {r,d}=await apiTry('/api/admin/dungeon/katalog/'+teil+'?lang='+dmLang()+dmRWelt(teil));
  if(!r.ok){DMR.k[teil]={zeilen:[],eintraege:{},fehler:dmErr(r.status,d.detail)}}else DMR.k[teil]=d;if(DMR.teil===teil&&DMP.d)dmRulesDraw(DMP.d,'')}
const DMRMARKE={schwach:'',ok:'ok',stark:'warn',zu_stark:'bad'};
const DMRSTAND=()=>({runde:t('aus einer Runde','from a round'),grund:t('Grundregel','Base'),srd:'SRD',eigen:t('eigen','own'),geaendert:t('geändert','changed'),aus:t('ausgeblendet','hidden')});
function dmRFilter(teil){if(teil==='gegenstaende')return [['alle',t('Alle','All')],['waffe',t('Waffen','Weapons')],['ruestung',t('Rüstung','Armour')],['zauber',t('Zauber','Spells')],['trank',t('Tränke','Potions')],['werkzeug',t('Werkzeug','Tools')],['schatz',t('Schätze','Treasure')]];
  if(teil==='gegner')return [['alle',t('Alle','All')],['s0',t('Stufe 0-4','Level 0-4')],['s5',t('Stufe 5-10','Level 5-10')],['s11',t('Stufe 11+','Level 11+')],['boss',t('Bosse','Bosses')],['frisch',t('Neu','New')]];return null}
function dmRPass(x){const f=DMR.f,q=DMR.q.trim().toLowerCase();
  if(q&&!(x.name.toLowerCase().includes(q)||String(x.id).toLowerCase().includes(q)))return false;
  if(DMR.m!=='alle'&&!(x.marke&&(DMR.m==='stark'?['stark','zu_stark'].includes(x.marke.marke):x.marke.marke===DMR.m)))return false;
  if(x.welten&&DMR.gw!=='alle'&&!x.welten.includes(DMR.gw))return false;
  if(f==='alle')return true;if(f==='boss')return !!x.boss;if(f==='frisch')return !!x.frisch;
  if(f==='zauber')return ['zauber','rolle'].includes(x.art);if(f==='schatz')return ['schatz','schmuck'].includes(x.art);
  if(f[0]==='s'&&x.stufe!=null){const s=+x.stufe;return f==='s0'?s<5:f==='s5'?s>=5&&s<=10:s>10}
  return x.art===f}
// a foe's damage kind and what hurts it more (▲ double), less (▼ half) or not at all (✕), as symbols (Bestiarium-Punkt 9)
function dmRArt(K,x){const A=K.arten||{},a=x.arten,z=i=>A[i]?`<span title="${esc(A[i].name)}">${A[i].zeichen}</span>`:'';if(!a)return '';
  const g=(k,s,l)=>a[k]&&a[k].length?`<span class="dm-rak" title="${esc(l)}">${s}${a[k].map(z).join('')}</span>`:'';
  return `<span class="dm-rart">${z(a.art)}${g('schwaeche','▲',t('Schwäche: doppelter Schaden','Weak: double damage'))}${g('resistenz','▼',t('Widerstand: halber Schaden','Resists: half damage'))}${g('immun','✕',t('Immun: kein Schaden','Immune: no damage'))}</span>`}
// v: the picture's own version (row bv/nv, its file time) so the browser keeps it; k: the small copy for the list
const dmRImg=(n,v,k)=>`<img alt="" loading="lazy" decoding="async" src="/api/admin/dungeon/bild/${encodeURIComponent(n)}?v=${v||DMR.v}${k?'&klein=1':''}">`;
// an item's picture in its rarity's frame, as in the bag (DMSEL; Dominik 2026-10-24 „farblich anders umrandet“)
function dmRThumb(x,K){const s=x.selten?' '+(DMSEL[x.selten]||''):'selten' in x?' dm-sx':'';
  if(!K.bilder_an&&!x.bild||!('bild' in x))return `<span class="dm-rth dm-dz${s}" aria-hidden="true">${esc(x.zeichen||'·')}</span>`;
  return x.bild?`<span class="dm-rth${s}">${dmRImg(x.bild,x.bv,1)}</span>`:`<span class="dm-rth dm-rno${s}" aria-hidden="true">${esc(x.zeichen||'')}</span>`}
function dmKat(teil){const K=DMR.k[teil],N=dmRNamen(),St=DMRSTAND();
  if(!K)return `<h3 class="sec">${esc(N[teil])}</h3><div class="mut">${esc(t('Lade …','Loading …'))}</div>`;
  if(K.fehler)return `<h3 class="sec">${esc(N[teil])}</h3><div class="err">${esc(K.fehler)}</div>`;
  const F=dmRFilter(teil),hasM=K.zeilen.some(x=>x.marke),rows=K.zeilen.filter(dmRPass),MAX=200;
  const nm={alle:t('Alle','All'),stark:t('stark und zu stark','strong and too strong'),zu_stark:t('zu stark','too strong'),schwach:t('schwach','weak')};
  const list=rows.slice(0,MAX).map(x=>{const m=x.marke&&x.marke.marke!=='ok'?`<span class="pill ${DMRMARKE[x.marke.marke]}" title="${esc(x.marke.grund)}">${esc(x.marke.name)}</span>`:'';
    return `<div class="dm-rrow${String(x.id)===DMR.sel?' on':''}${x.stand==='aus'?' dm-raus':''}${x.selten?' dm-rsel '+(DMSEL[x.selten]||''):'selten' in x?' dm-rsel dm-sx':''}"><button type="button" class="dm-rmain" data-dmrsel="${esc(x.id)}">${dmRThumb(x,K)}<span class="dm-rtxt"><b>${esc(x.name)}</b><small>${esc(x.zeile)}</small>${dmRArt(K,x)}</span></button>
      <span class="dm-rpills">${x.boss?`<span class="pill warn">👑 ${esc(t('Boss','Boss'))}</span>`:''}${x.frisch?`<span class="pill ok">${esc(t('neu','new'))}</span>`:''}${m}${x.stand!=='grund'&&x.stand!=='srd'?`<span class="pill">${esc(St[x.stand])}</span>`:''}${x.neu?`<span class="pill warn">${esc(t('neues Bild','new picture'))}</span>`:''}</span>
      ${'bild' in x&&!x.bild&&K.bilder_an?`<button type="button" class="b" data-dmrbild="malen" data-id="${esc(x.id)}"${DMR.busy?' disabled':''}>🖌 ${esc(t('Malen','Paint'))}</button>`:''}</div>`}).join('');
  const wsel=K.welten?`<select class="dmr-w" aria-label="${esc(t('Bilder in der Welt','Pictures in the world'))}">${K.welten.map(w=>`<option value="${esc(w.id)}"${w.id===K.welt?' selected':''}>${esc(t('Bilder in: ','Pictures in: ')+w.name)}</option>`).join('')}</select>`:'';
  const gsel=K.weltfilter?`<select class="dmr-gw" aria-label="${esc(t('Welt','World'))}"><option value="alle">${esc(t('Alle Welten','All worlds'))}</option>${K.weltfilter.map(w=>`<option value="${esc(w.id)}"${w.id===DMR.gw?' selected':''}>${esc(w.name)}</option>`).join('')}</select>`:'';
  return `<h3 class="sec">${esc(N[teil])} · ${K.zeilen.length}${K.neu?` <button type="button" class="b" data-dmrneu="1">＋ ${esc(t('Neue Person','New person'))}</button>`:''}</h3>
    <div class="dm-rsrch">${wsel}${gsel}<input type="search" class="dmr-q" value="${esc(DMR.q)}" placeholder="${esc(t('Suchen …','Search …'))}" aria-label="${esc(t('Suchen','Search'))}">
      ${F?`<div class="lseg dm-rseg">${F.map(([v,l])=>`<button type="button" class="${DMR.f===v?'on':''}" data-dmrf="${v}">${esc(l)}</button>`).join('')}</div>`:''}
      ${hasM?`<select class="dmr-m" aria-label="${esc(t('Gleichgewicht','Balance'))}">${['alle','stark','zu_stark','schwach'].map(v=>`<option value="${v}"${DMR.m===v?' selected':''}>${esc(v==='alle'?t('Gleichgewicht: alle','Balance: all'):nm[v])}</option>`).join('')}</select>`:''}</div>
    ${K.kasten?dmRKasten(K.kasten):''}${K.seltenheiten?dmRSelLeg(K):''}<div class="dm-rkat"><div class="dm-rlist" role="list">${list||`<div class="ic-empty">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`}${rows.length>MAX?`<div class="mut dm-rmehr">${esc(t(`${rows.length-MAX} weitere, bitte genauer suchen`,`${rows.length-MAX} more, please search more closely`))}</div>`:''}</div>
    <div class="dm-rdet" id="dmrdet">${dmRDet(teil)}</div></div>`}
// the fixed rules around a part (runes: sockets, caps, the switch with its way; stall events; the numbers)
function dmRKasten(k){const s=k.schalter;
  return `<details class="dm-rkasten" open><summary>${esc(t('Feste Regeln dazu','Fixed rules around it'))}</summary>${s?`<div class="fh"><span class="pill${s.an?' ok':''}">${esc(s.name+': '+(s.an?t('an','on'):t('aus','off')))}</span> <a href="#" class="wayl" data-way="${esc(s.weg)}">${esc(s.weg)}</a></div>`:''}
    <dl class="dm-rwerte">${k.zeilen.map(([a,v])=>`<dt>${esc(a)}</dt><dd>${esc(v)}</dd>`).join('')}</dl></details>`}
// a table with its own columns (the numbers: levels, find table, prices, budget)
function dmRTabelle(x){const T=x.tabelle;
  return `<div class="dm-rtafel dm-rtab" role="region" tabindex="0" aria-label="${esc(x.name)}"><table><thead><tr>${T.kopf.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead>
    <tbody>${T.zeilen.map(z=>`<tr>${z.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
// a table of the catalog in full (Dominik 2026-10-25 „ich sehe gar nicht die tabellen“): the die, every row, the worlds of a row
function dmRTafel(x){const w=x.tafel.some(z=>z.w);
  return `<div class="dm-rtafel" role="region" tabindex="0" aria-label="${esc(t('Tabelle','Table'))}"><table><thead><tr><th>${esc(t('W','d')+x.tafel.length)}</th><th>${esc(t('Ergebnis','Result'))}</th>${w?`<th>${esc(t('Nur in','Only in'))}</th>`:''}</tr></thead>
    <tbody>${x.tafel.map(z=>`<tr><td>${z.n}</td><td>${esc(z.t)}</td>${w?`<td>${esc(z.w)}</td>`:''}</tr>`).join('')}</tbody></table></div>`}
// the rarities as frames: a fixed one shows its colour, a rolled item (most of them) gets it when it is found
function dmRSelLeg(K){return `<div class="dm-rsleg" aria-label="${esc(t('Seltenheit','Rarity'))}">${K.seltenheiten.map(s=>`<span class="dm-rsl"><i class="dm-rth ${DMSEL[s.id]||''}"></i>${esc(s.name)}</span>`).join('')}<span class="dm-rsl"><i class="dm-rth dm-sx"></i>${esc(t('gewürfelt beim Fund','rolled when found'))}</span></div>`}
function dmRSelLadder(K,x){if(!K.seltenheiten)return '';
  if(x.selten){const s=K.seltenheiten.find(z=>z.id===x.selten);return s?`<div class="fh dm-rsfest"><i class="dm-rth ${DMSEL[s.id]||''}"></i>${esc(x.preis==null?t(`Immer ${s.name}: +${s.bonus}, Preis ×${s.preis}`,`Always ${s.name}: +${s.bonus}, price ×${s.preis}`):x.preis?t(`Immer ${s.name}: +${s.bonus}, Preis ${x.preis} Gold`,`Always ${s.name}: +${s.bonus}, price ${x.preis} gold`):t(`Immer ${s.name}: +${s.bonus}, unverkäuflich`,`Always ${s.name}: +${s.bonus}, not for sale`))}</div>`:''}
  return `<div class="dm-rsleiter"><div class="fh">${esc(t('Die Seltenheit wird beim Fund gewürfelt (W100 nach einer festen Tabelle je Stufe, Truhen und Bosse würfeln höher) und gibt den Rahmen:','The rarity is rolled when it is found (d100 by a fixed table per level, chests and bosses roll higher) and gives the frame:'))}</div>
    ${K.seltenheiten.map(s=>`<div class="dm-rsl"><i class="dm-rth ${DMSEL[s.id]||''}"></i><b>${esc(s.name)}</b><small>${esc(t(`+${s.bonus} · Preis ×${s.preis}${s.stufe>1?` · ab Stufe ${s.stufe}`:s.stufe?'':' · nie'}`,`+${s.bonus} · price ×${s.preis}${s.stufe>1?` · from level ${s.stufe}`:s.stufe?'':' · never'}`))}</small></div>`).join('')}</div>`}
// a person's voice (Dominik 2026-10-27 „stimmen verändern, die genutzt werden wenn diese etwas sagen“): five fixed
// lists, „▶ Probe“ before saving, „Nach dem Namen“ gives the voice back to the name; only the panel's fixed words
// VoiceDesign not running (Dominik 2026-10-27 „stimme klang bei alles gleich“): every person speaks in the fixed voice, said with the way to switch it on
function dmDesignAus(){return `<div class="fh dm-designaus">${esc(t('Stimmen aus Beschreibung laufen gerade nicht: jede Person spricht in der festen Stimme. Einschalten (Admin): ','Voices from a description are not running right now: every person speaks in the fixed voice. Switch on (admin): '))}<a href="#" class="wayl" data-way="Einstellungen → Sprachausgabe → „VoiceDesign zusätzlich bereitstellen“">${esc(t('Einstellungen → Sprachausgabe → „VoiceDesign zusätzlich bereitstellen“','Settings → Speech output → "Also serve VoiceDesign"'))}</a>.</div>`}
function dmRStimme(K,x,e){const cur=(DMR.st&&DMR.st.id===String(x.id))?DMR.st.t:(e.stimme_jetzt||{});
  return `<div class="dm-voice dm-rstimme"><label>${esc(t('🎙 Stimme, wenn die Person spricht','🎙 Voice when the person speaks'))}</label>${K.stimme_design===false?dmDesignAus():''}
    <div class="dm-rstw">${(K.stimmwahl||[]).map(m=>`<select data-dmrst="${esc(m.k)}" aria-label="${esc(m.name)}">${m.werte.map(([v,w])=>`<option value="${esc(v)}"${v===cur[m.k]?' selected':''}>${esc(m.name+': '+w)}</option>`).join('')}</select>`).join('')}</div>
    <div class="row"><button type="button" class="b" data-dmrstimme="probe">${esc('▶ '+t('Probe','Sample'))}</button><button type="button" class="b p" data-dmrstimme="setzen">${esc(t('Stimme speichern','Save voice'))}</button>${Object.keys(e.stimme||{}).length?`<button type="button" class="b" data-dmrstimme="name">${esc(t('Nach dem Namen','By the name'))}</button>`:''}</div></div>`}
function dmRDet(teil){const K=DMR.k[teil],St=DMRSTAND(),x=K.zeilen.find(z=>String(z.id)===DMR.sel)||(DMR.edit&&DMR.edit.neu?{id:DMR.edit.e.id,name:t('Neue Person','New person')}:null);
  if(!x)return `<div class="ic-empty">${esc(t('Tippe links einen Eintrag an.','Tap an entry on the left.'))}</div>`;
  const e=K.eintraege[String(x.id)]||{},li=L==='en'?1:0,tx=v=>Array.isArray(v)?v[li]||v[0]:v||'';
  if(DMR.edit)return `<b class="dm-rname">${esc(DMR.edit.kopie?t('Eigene Kopie','Own copy'):t('Ändern','Edit'))}: ${esc(x.name)}</b>
    <div class="fh">${esc(t('Der ganze Eintrag; das Panel prüft ihn wie alle Regeln. „Zu stark“ ist nur ein Hinweis.','The whole entry; the panel checks it like every rule. "Too strong" is only a hint.'))}</div>
    <textarea class="mono dmr-txt" rows="16" data-fest spellcheck="false">${esc(JSON.stringify(DMR.edit.e,null,2))}</textarea>${DMR.err?`<div class="err dm-adm-err">${DMR.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmrdo="setzen">${esc(t('Prüfen und speichern','Check and save'))}</button><button type="button" class="b" data-dmrdo="abbrechen">${esc(t('Abbrechen','Cancel'))}</button></div>`;
  const m=x.marke,neu=DMR.neu[String(x.id)]||x.neu,b='bild' in x;
  const pic=b?`<div class="dm-rbild${x.selten?' '+(DMSEL[x.selten]||''):''}">${neu?`<div class="dm-rvgl"><figure>${x.bild?dmRImg(x.bild,x.bv):`<span class="dm-rno">${esc(x.zeichen||'')}</span>`}<figcaption>${esc(t('jetzt','now'))}</figcaption></figure><figure>${dmRImg(neu,DMR.neu[String(x.id)]?DMR.v:x.nv)}<figcaption>${esc(t('neu gemalt','painted again'))}</figcaption></figure></div>
      <div class="row"><button type="button" class="b p" data-dmrbild="neu" data-id="${esc(x.id)}">${esc(t('Neues behalten','Keep the new one'))}</button><button type="button" class="b" data-dmrbild="alt" data-id="${esc(x.id)}">${esc(t('Altes behalten','Keep the old one'))}</button></div>`
      :`<div class="dm-rvgl"><figure>${x.bild?dmRImg(x.bild,x.bv):`<span class="dm-rno">${esc(x.zeichen||'')}</span>`}<figcaption>${esc(x.bild?t('jetzt','now'):t('noch kein Bild','no picture yet'))}</figcaption></figure></div>`}
      <div class="row">${K.bilder_an?`<button type="button" class="b" data-dmrbild="malen" data-id="${esc(x.id)}"${DMR.busy?' disabled':''}>🖌 ${esc(DMR.busy===String(x.id)?t('Malt gerade …','Painting …'):x.bild?t('Nochmal malen','Paint again'):t('Malen','Paint'))}</button>`:`<small class="mut">${esc(t('Die Bilder sind aus; einschalten im Abschnitt „Bilder“.','Pictures are off; switch them on in the part "Pictures".'))}</small>`}</div></div>`:'';
  return `<div class="dm-rdkopf"><div><b class="dm-rname">${esc(x.zeichen||'')} ${esc(x.name)}</b> <span class="pill">${esc(St[x.stand])}</span>${m?` <span class="pill ${DMRMARKE[m.marke]}">${esc(m.name)}</span>`:''}</div></div>
    <div class="dm-rdgrid"><div><div class="dm-rzeile">${esc(x.zeile)}</div>${(x.werte||[]).length?`<dl class="dm-rwerte">${x.werte.map(([a,v])=>`<dt>${esc(a)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`:''}${dmRSelLadder(K,x)}${x.tafel?dmRTafel(x):''}${x.tabelle?dmRTabelle(x):''}${m&&m.grund?`<div class="fh dm-rgrund">${esc(m.grund)}</div>`:''}${tx(e.info||e.satz)?`<p class="dm-rinfo">${esc(tx(e.info||e.satz))}</p>`:''}${teil==='personen'&&K.stimmwahl?dmRStimme(K,x,e):''}
      ${K.fest?`<div class="fh">${esc(t('Nur zum Ansehen. Ändern unter „Für Fortgeschrittene (JSON)“.','Only to look at. Change it under "Advanced (JSON)".'))}</div>`:`<div class="row"><button type="button" class="b" data-dmrdo="aendern">${esc(t('Ändern','Edit'))}</button><button type="button" class="b" data-dmrdo="kopie">${esc(t('Eigene Kopie','Own copy'))}</button>
      ${x.stand==='aus'||x.stand==='geaendert'?`<button type="button" class="b" data-dmrdo="zurueck">${esc(t('Zurück auf mitgeliefert','Back to shipped'))}</button>`:''}
      ${x.stand==='eigen'||teil==='personen'?`<button type="button" class="b danger" data-dmrdo="zurueck">${esc(teil==='personen'?t('Person löschen','Delete person'):t('Eigenen Eintrag löschen','Delete own entry'))}</button>`:x.stand!=='aus'?`<button type="button" class="b" data-dmrdo="aus">${esc(t('Ausblenden','Hide'))}</button>`:''}</div>`}</div>${pic}</div>`}
// the list keeps its place when it is drawn again (Dominik 2026-10-24 „beim Klicken hüpft die Liste“)
function dmRDraw(){const c=$('dmadmcard');if(!c||!DMP.d)return;const l=c.querySelector('.dm-rlist'),top=l?l.scrollTop:0;
  dmRulesDraw(DMP.d,'');const n=c.querySelector('.dm-rlist');if(n)n.scrollTop=top}
// a tap on an entry: only the mark and the detail change, the list stays as it is
function dmRPick(){const c=$('dmadmcard'),det=$('dmrdet');if(!c||!det||!DMR.k[DMR.teil])return dmRDraw();
  c.querySelectorAll('.dm-rrow').forEach(r=>{const b=r.querySelector('[data-dmrsel]');r.classList.toggle('on',!!b&&b.dataset.dmrsel===DMR.sel)});
  det.innerHTML=dmRDet(DMR.teil)}
async function dmRDo(teil,was,id,eintrag){const {r,d}=await apiTry('/api/admin/dungeon/katalog/'+teil+'?lang='+dmLang()+dmRWelt(teil),xjson('POST',{was,id,eintrag}));
  if(!r.ok){DMR.err=Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>'):esc(dmErr(r.status,d.detail));dmRDraw();return false}
  DMR.k[teil]=d;DMR.edit=null;DMR.err='';if(eintrag)DMR.sel=String(eintrag.id);dmRDraw();
  if(d.hinweis)sayToast(t('Gespeichert. Hinweis: ','Saved. Hint: ')+d.hinweis.name+' · '+d.hinweis.grund);else sayToast(t('Gespeichert','Saved'));return true}
const DMRWARUM=()=>({aus:t('Die Bilder sind aus.','Pictures are off.'),tag:t('Das Tageslimit für Bilder ist erreicht.','The day limit for pictures is reached.'),pruefung:t('Die Bildbeschreibung hat die Prüfung nicht bestanden.','The picture prompt did not pass the check.'),
  missing:t('Das Bildmodell fehlt.','The picture model is missing.'),ohne_pruefung:t('Die Bildprüfung fehlt.','The image check is missing.'),belegt:t('Das Bildmodell ist gerade belegt.','The picture model is busy right now.')});
document.body.addEventListener('input',e=>{const q=e.target.closest('#dmadmcard .dmr-q');if(!q)return;DMR.q=q.value;const p=q.selectionStart;dmRDraw();const n=document.querySelector('#dmadmcard .dmr-q');if(n){n.focus();n.setSelectionRange(p,p)}});
document.body.addEventListener('change',e=>{const w=e.target.closest('#dmadmcard .dmr-w');if(w){DMR.welt[DMR.teil]=w.value;DMR.neu={};dmKatLoad(DMR.teil);return}
  const g=e.target.closest('#dmadmcard .dmr-gw');if(g){DMR.gw=g.value;dmRDraw();return}
  const s=e.target.closest('#dmadmcard .dmr-m');if(!s)return;DMR.m=s.value;dmRDraw()});
document.body.addEventListener('click',async e=>{const c=e.target.closest('#dmadmcard');if(!c)return;const teil=DMR.teil;
  const nb=e.target.closest('[data-dmrteil]');if(nb){DMR.teil=nb.dataset.dmrteil;DMR.sel='';DMR.q='';DMR.f='alle';DMR.m='alle';DMR.gw='alle';DMR.edit=null;DMR.err='';DMP.g=null;dmRDraw();return}
  const fb=e.target.closest('[data-dmrf]');if(fb){DMR.f=fb.dataset.dmrf;dmRDraw();return}
  const sb=e.target.closest('[data-dmrsel]');if(sb){DMR.sel=sb.dataset.dmrsel;DMR.edit=null;DMR.err='';dmRPick();const d=$('dmrdet');if(d&&window.innerWidth<900)d.scrollIntoView({block:'start',behavior:'smooth'});return}
  const nn=e.target.closest('[data-dmrneu]');if(nn){const K=DMR.k[teil],w=((K&&K.weltfilter)||[])[0];   // a new person of the catalog: an empty card to fill
    DMR.edit={neu:true,e:{id:'p'+Math.random().toString(16).slice(2,10).padEnd(8,'0'),name:'',welt:w?w.id:'',rolle:'',ziel:'',karte:{aussehen:['',''],art:['',''],beruf:['',''],wunsch:['',''],geheimnis:['','']},wesen:{}}};DMR.sel='';DMR.err='';dmRDraw();return}
  const db=e.target.closest('[data-dmrdo]');if(db){const K=DMR.k[teil],x=K&&K.zeilen.find(z=>String(z.id)===DMR.sel);if(!x&&!(DMR.edit&&DMR.edit.neu))return;const was=db.dataset.dmrdo;
    if(was==='abbrechen'){DMR.edit=null;DMR.err='';dmRDraw();return}
    if(was==='aendern'||was==='kopie'){const e0=JSON.parse(JSON.stringify(K.eintraege[String(x.id)]||{}));
      if(was==='kopie'){const ids=new Set(K.zeilen.map(z=>String(z.id)));let n=2;while(ids.has(`${x.id}_${n}`))n++;e0.id=typeof x.id==='number'?Math.max(...K.zeilen.map(z=>+z.id||0))+1:`${x.id}_${n}`;}
      DMR.edit={e:e0,kopie:was==='kopie'};DMR.err='';dmRDraw();return}
    if(was==='setzen'){let ent;try{ent=JSON.parse(c.querySelector('.dmr-txt').value)}catch{DMR.edit.e=c.querySelector('.dmr-txt').value;DMR.err=esc(t('Das ist kein gültiges JSON.','This is not valid JSON.'));dmRDraw();return}
      DMR.edit.e=ent;await dmRDo(teil,'setzen',String(ent.id),ent);return}
    if(db.classList.contains('danger')&&db.dataset.sure!=='1'){db.dataset.sure='1';db.textContent=t('Wirklich löschen?','Really delete?');return}
    await dmRDo(teil,was,String(x.id));return}
  const vb=e.target.closest('[data-dmrstimme]');if(vb){const id=DMR.sel,was=vb.dataset.dmrstimme,st={};
    c.querySelectorAll('[data-dmrst]').forEach(s=>{st[s.dataset.dmrst]=s.value});
    if(was==='probe'){DMR.st={id,t:st};try{const r=await api('/api/admin/dungeon/personen/probe',xjson('POST',{stimme:st,lang:dmLang()}));
        if(!r.ok){sayToast(t('Die Sprachausgabe ist gerade belegt.','The speech output is busy right now.'));return}
        if(r.headers.get('X-Stimme')==='fest')sayToast(t('Stimmen aus Beschreibung laufen gerade nicht, die Probe kommt in der festen Stimme.','Voices from a description are not running right now, the sample uses the fixed voice.'));
        const A=DMA.p;if(A.el)A.el.pause();if(A.url)URL.revokeObjectURL(A.url);A.url=URL.createObjectURL(await r.blob());A.el=new Audio(A.url);await A.el.play()}catch(err){}return}
    DMR.st=null;await dmRDo(teil,'stimme',id,{id,stimme:was==='name'?{}:st});return}
  const pb=e.target.closest('[data-dmrbild]');if(pb){const id=pb.dataset.id,was=pb.dataset.dmrbild;if(DMR.busy)return;
    if(was==='malen'){DMR.busy=id;dmRDraw()}
    const {r,d}=await apiTry('/api/admin/dungeon/katalog/'+teil+'/bild',xjson('POST',{id,was,welt:DMR.welt[teil]||(DMR.k[teil]||{}).welt||''}));DMR.busy='';
    if(!r.ok){sayToast(DMRWARUM()[d.detail]||dmErr(r.status,d.detail));dmRDraw();return}
    if(was==='malen'&&d.neu)DMR.neu[id]=d.neu;else delete DMR.neu[id];DMR.v=Date.now();DMR.sel=id;
    await dmKatLoad(teil);return}});
document.body.addEventListener('click',async e=>{if(e.target.closest('#dmrules')){dmRules();return}
  const b=e.target.closest('#dmadmcard [data-dmadm]');if(!b)return;const k=b.dataset.dmadm;
  if(k==='close'){$('dmadm').style.display='none';return}
  if(k==='mailpf'){const {r,d}=await apiTry('/api/admin/dungeon/gastmail',xjson('PUT',{absender:$('dmgastpf').value}));
    if(r.ok)dmRulesDraw(d,'');else dmRulesDraw(DMP.d,esc(dmErr(r.status,d.detail)));return}
  if(k[0]==='g'){await dmPlanClick(b,k);return}
  if(k==='reset'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich auf Standard?','Really back to default?');return}
    const {r,d}=await apiTry('/api/admin/dungeon',{method:'DELETE'});if(r.ok){DMR.k={};dmRulesDraw(d,'')}return}
  // „Speichern“ in Stimmen keeps the own rules as they are, the JSON part reads them from its field
  const ta=$('dmadmtxt');let own;
  if(ta){try{own=JSON.parse(ta.value||'{}')}catch{dmRulesDraw(DMP.d,esc(t('Das ist kein gültiges JSON.','This is not valid JSON.')));$('dmadmtxt').value=ta.value;return}}else own=JSON.parse(JSON.stringify(DMP.d.eigene||{}));
  const sv={},vs=document.querySelectorAll('#dmadmcard .dmadm-voice');vs.forEach(x=>{sv[x.dataset.k]=x.value});
  if(vs.length){Object.keys(sv).forEach(x=>{if(!sv[x])delete sv[x]});if(Object.keys(sv).length)own.stimmen=sv;else delete own.stimmen}   // empty: the preset
  const keep=ta&&ta.value;const {r,d}=await apiTry('/api/admin/dungeon',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({eigene:own})});
  if(r.ok){DMR.k={};dmRulesDraw(d,'');sayToast(t('Regeln gespeichert','Rules saved'));return}
  dmRulesDraw(DMP.d,Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>'):esc(dmErr(r.status,d.detail)));if(keep&&$('dmadmtxt'))$('dmadmtxt').value=keep});
// 👍/👎 per narration over all rounds, per world and tone (numbers only; the model learns nothing from them)
function dmThumbsAdmin(x){if(!x||!x.length)return '';const n=a=>a[L==='en'?1:0];
  return `<h3 class="sec">${esc(t('Wie die Erzählungen ankommen','How the narrations land'))}</h3><div class="dm-sum">${x.map(r=>`<span class="pill">${esc(n(r.welt))} · ${esc(n(r.ton))}: 👍 ${r.hoch} · 👎 ${r.runter}</span>`).join(' ')}</div>`}
// Bilder für Ausrüstung und Zauber (dungeon_dingbild.py): how many there are, the last run, „Bilder jetzt erstellen“ and „Anhalten“
function dmDingAdmin(x){if(!x)return '';const L0=x.letzter||{},warum={fertig:t('alle fertig','all done'),morgen:t('Nacht vorbei','night over'),tag:t('Tageslimit erreicht','day limit reached'),angehalten:t('angehalten','stopped'),aus:t('ausgeschaltet','switched off'),notaus:'Notaus',voll:t('Warteschlange voll','queue full'),missing:t('Bildmodell fehlt','picture model missing'),ohne_pruefung:t('Bildprüfung fehlt','image check missing')};
  return `<div id="dmding"><h3 class="sec">${esc(t('Bilder für Ausrüstung und Zauber','Pictures for gear and spells'))} · ${x.fertig}/${x.von}</h3>
    <div class="fh">${esc(x.an?(x.bilder?t(`Ein Bild je Gegenstand und Zauber im Stil jeder Welt (${x.stile} Stile). Der Spark malt fehlende Bilder nachts von ${x.nacht[0]} bis ${x.nacht[1]} Uhr, höchstens ${x.tag_max} am Tag; bis dahin zeigt der Tisch das Zeichen der Art.`,`One picture per item and spell in the style of each world (${x.stile} styles). The Spark paints missing pictures at night from ${x.nacht[0]} to ${x.nacht[1]}, at most ${x.tag_max} a day; until then the table shows the kind's sign.`):t('Dafür muss auch „Bilder malen“ freigegeben sein.','“Painting pictures” must be released for this too.')):t('Aus. Einschalten unter Funktionen → KI-Dungeon-Master → Bilder und Heldenlied.','Off. Switch it on under Features → AI Dungeon Master → Pictures and hero song.'))}</div>
    <div class="dm-sum"><span class="pill">${esc(t('heute','today'))} ${x.heute}</span> <span class="pill">${esc(t('Fundstücke','Finds'))} ${x.funde}</span>${x.abgelehnt?` <span class="pill warn">${esc(t('abgelehnt','refused'))} ${x.abgelehnt}</span>`:''}${x.laeuft?` <span class="pill on">${esc(x.grund==='alle'?t('malt alle, ohne Tageslimit','painting all, no day limit'):t('malt gerade','painting now'))} · ${x.gemalt} · ${esc(t('noch','left'))} ${x.offen}</span>`:L0.ende?` <span class="pill">${esc(t('zuletzt','last'))} ${esc(new Date(L0.ende*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))} · ${L0.gemalt} · ${esc(warum[L0.warum]||L0.warum||'')}</span>`:''}</div>
    <div class="row">${x.laeuft?`<button type="button" class="b" data-dmding="stop">${esc(x.grund==='alle'?t('Abbrechen','Cancel'):t('Anhalten','Stop'))}</button>`:`<button type="button" class="b p" data-dmding="start"${!x.an||!x.bilder||!x.offen?' disabled':''}>${esc(t('Bilder jetzt erstellen','Create pictures now'))}</button>
      <button type="button" class="b" data-dmding="alle" title="${esc(t('Malt alle fehlenden Bilder (Gegenstände, Zauber, Gegner, Orts- und Raumarten, Völker, Klassen) ohne Tageslimit, eins nach dem anderen über die Warteschlange.','Paints every missing picture (items, spells, foes, kinds of places and rooms, peoples, classes) without the day limit, one after the other through the queue.'))}"${!x.an||!x.bilder||!x.offen?' disabled':''}>${esc(t('Alle Bilder malen','Paint all pictures'))} · ${x.offen}</button>`}</div></div>`}
// Balance-Prüfstand (dungeon_pruefstand.py): how often a group wins a fight of „mittel“, per level, for the group size
// chosen; the aim as a green band, a bar outside it red. Numbers from the panel's own fights, never the model.
const DMPS={g:4,t:0};
function dmPruefBox(x){const z=x.zellen||{},G=DMPS.g,lv=Object.keys(z).map(k=>k.split('/')).filter(([,g])=>+g===G).map(([s])=>+s).sort((a,b)=>a-b);
  const [lo,hi]=x.ziel,W=520,H=230,B=196,sc=1.7,bw=Math.min(40,(W-60)/Math.max(1,lv.length)-8);
  const bars=lv.map((s,i)=>{const c=z[s+'/'+G],hgt=c.siege*sc,xx=48+i*(bw+8),off=c.siege<lo||c.siege>hi;
    return `<rect x="${xx}" y="${B-hgt}" width="${bw}" height="${hgt}" rx="4" class="${off?'dm-ps-aus':'dm-ps-in'}"><title>${esc(t('Stufe','Level'))} ${s}: ${c.siege} %</title></rect><text x="${xx+bw/2}" y="${B-hgt-5}" text-anchor="middle" class="dm-ps-z">${c.siege}</text><text x="${xx+bw/2}" y="${B+15}" text-anchor="middle">${s}</text>`}).join('');
  const chart=lv.length?`<svg viewBox="0 0 ${W} ${H}" class="dm-ps-svg" role="img" aria-label="${esc(t(`Siege je Stufe, Gruppe aus ${G}`,`Wins per level, group of ${G}`))}"><rect x="40" y="${B-hi*sc}" width="${W-44}" height="${(hi-lo)*sc}" class="dm-ps-ziel"/><line x1="40" y1="${B}" x2="${W-4}" y2="${B}" class="dm-ps-ax"/><text x="2" y="${B-hi*sc+4}">${hi} %</text><text x="2" y="${B-lo*sc+4}">${lo} %</text><text x="2" y="${B+4}">0 %</text>${bars}<text x="${W/2}" y="${H-2}" text-anchor="middle">${esc(t('Stufe der Gruppe','Level of the group'))}</text></svg>`
    :`<div class="fh">${esc(t('Noch kein Durchlauf.','No run yet.'))}</div>`;
  const zr=x.runen||{},mr=Object.keys(zr).length>0,rp=mr?(x.runen_plus>0?'+':'')+(L==='en'?String(x.runen_plus):String(x.runen_plus).replace('.',',')):'';
  const zh=x.herr||{},zb=x.boss||{},mb=Object.keys(zh).length>0,pc=c=>c?c.siege+' %':'–';
  const mean=o=>{const v=Object.keys(o).filter(k=>+k.split('/')[1]===G).map(k=>o[k].siege);return v.length?Math.round(v.reduce((a,b)=>a+b,0)/v.length):null};
  const rows=lv.map(s=>{const c=z[s+'/'+G],cr=zr[s+'/'+G];return `<tr><td>${s}</td><td>${c.siege} %</td>${mr?`<td>${pc(cr)}</td>`:''}${mb?`<td>${pc(zh[s+'/'+G])}</td><td>${pc(zb[s+'/'+G])}</td>`:''}<td>${c.leben} %</td><td${c.runden>x.zuege_max?' class="dm-ps-lang"':''}>${c.runden}</td></tr>`}).join('');
  const mh=mean(zh),mo=mean(zb);
  return `<div class="fh">${esc(x.an?t(`Der Spark spielt nachts je Stufe und Gruppengröße ${x.kaempfe||200} Kämpfe der Gefahr „mittel“ mit den echten Regeln und Würfeln durch, ohne Modell. Ziel: ${lo} bis ${hi} % Siege, ein Kampf im Mittel höchstens ${x.zuege_max} Runden.`,`At night the Spark plays ${x.kaempfe||200} fights of danger "medium" per level and group size with the real rules and dice, without the model. Aim: ${lo} to ${hi} % wins, a fight at most ${x.zuege_max} turns on average.`):t('Aus. Einschalten unter Funktionen → KI-Dungeon-Master → Prüfstände.','Off. Switch it on under Features → AI Dungeon Master → Test benches.'))}</div>
    <div class="row dm-ps-g" role="group" aria-label="${esc(t('Gruppengröße','Group size'))}">${Array.from({length:x.gruppe_max},(_,i)=>i+1).map(g=>`<button type="button" class="b${g===G?' on':''}" data-dmps="${g}"${g===G?' aria-pressed="true"':' aria-pressed="false"'}>${g} ${esc(g===1?t('Held','hero'):t('Helden','heroes'))}</button>`).join('')}</div>
    ${chart}${rows?`<table class="dm-ps-t"><thead><tr><th>${esc(t('Stufe','Level'))}</th><th>${esc(t('Siege','Wins'))}</th>${mr?`<th>${esc(t('mit Runen','with runes'))}</th>`:''}${mb?`<th>${esc(t('Herr','Master'))}</th><th>${esc(t('Boss allein','Lone boss'))}</th>`:''}<th>${esc(t('Leben verloren','Life lost'))}</th><th>${esc(t('Runden','Turns'))}</th></tr></thead><tbody>${rows}</tbody></table>`:''}
    ${mr?`<div class="fh">${esc(t(`Mit Runen gewinnt die Gruppe im Mittel ${rp} Punkte öfter (Ziel: höchstens +${x.runen_ziel}).`,`With runes the group wins ${rp} points more often on average (aim: at most +${x.runen_ziel}).`))}</div>`:''}
    ${mb?`<div class="fh">${esc(t(`Gegen den Herrn eines Gewölbes gewinnt die Gruppe im Mittel ${mh??'–'} %, gegen einen Boss allein ${mo??'–'} % (Ziel: mindestens ${x.boss_ziel} %).`,`Against the master of a vault the group wins ${mh??'–'} % on average, against a lone boss ${mo??'–'} % (aim: at least ${x.boss_ziel} %).`))}</div>`:''}
    ${dmPruefGeld(x)}
    <div class="dm-sum">${x.zeit?`<span class="pill">${esc(t('zuletzt','last'))} ${esc(new Date(x.zeit*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))}</span>`:''}${x.laeuft?` <span class="pill on">${esc(t('spielt gerade','playing now'))}</span>`:''}</div>
    <div class="row"><button type="button" class="b p" data-dmps="los"${!x.an||x.laeuft?' disabled':''}>${esc(t('Jetzt durchspielen','Play it through now'))}</button></div>`}
// the economy (Wirtschaft Punkt 6): income ÷ expenses of a hero per level as bars, the aim as a green band
function dmPruefGeld(x){const w=x.wirtschaft||{},lv=Object.keys(w).map(Number).sort((a,b)=>a-b);if(!lv.length)return '';
  const [lo,hi]=x.wirtschaft_ziel,W=520,H=200,B=166,sc=60,bw=Math.min(40,(W-60)/lv.length-8);
  const bars=lv.map((s,i)=>{const c=w[s],v=Math.min(2.6,c.verhaeltnis),xx=48+i*(bw+8),off=c.verhaeltnis<lo||c.verhaeltnis>hi;
    return `<rect x="${xx}" y="${B-v*sc}" width="${bw}" height="${v*sc}" rx="4" class="${off?'dm-ps-aus':'dm-ps-in'}"><title>${esc(t('Stufe','Level'))} ${s}: ${c.verhaeltnis}</title></rect><text x="${xx+bw/2}" y="${B-v*sc-5}" text-anchor="middle" class="dm-ps-z">${String(c.verhaeltnis).replace('.',L==='en'?'.':',')}</text><text x="${xx+bw/2}" y="${B+15}" text-anchor="middle">${s}</text>`}).join('');
  const rows=lv.map(s=>{const c=w[s];return `<tr><td>${s}</td><td>${c.kaempfe}</td><td>${c.einnahmen}</td><td>${c.zehntel}</td><td>${c.ausgaben}</td><td>${String(c.verhaeltnis).replace('.',L==='en'?'.':',')}</td><td>${c.fund_max}</td></tr>`}).join('');
  return `<h3 class="sec">${esc(t('Wirtschaft je Stufe','Economy per level'))}</h3><div class="fh">${esc(t(`Gold eines Helden je Stufe: Münzen und Verkäufe beim Händler gegen Gasthaus, Heiltränke, Gerüchte und Schmied. Ziel: ${lo} bis ${hi} mal so viel Einnahmen wie Ausgaben, der Rest ist für Lehrstunden und „Ausrüstung verbessern“.`,`A hero's gold per level: coins and sales to merchants against inn, healing potions, rumours and smith. Aim: ${lo} to ${hi} times as much income as expenses; the rest is for lessons and "Improve gear".`))}</div>
    <svg viewBox="0 0 ${W} ${H}" class="dm-ps-svg" role="img" aria-label="${esc(t('Einnahmen geteilt durch Ausgaben je Stufe','Income divided by expenses per level'))}"><rect x="40" y="${B-hi*sc}" width="${W-44}" height="${(hi-lo)*sc}" class="dm-ps-ziel"/><line x1="40" y1="${B}" x2="${W-4}" y2="${B}" class="dm-ps-ax"/><text x="2" y="${B-hi*sc+4}">${hi}×</text><text x="2" y="${B-lo*sc+4}">${lo}×</text>${bars}<text x="${W/2}" y="${H-2}" text-anchor="middle">${esc(t('Stufe der Gruppe','Level of the group'))}</text></svg>
    <div class="dm-ps-w"><table class="dm-ps-t"><thead><tr><th>${esc(t('Stufe','Level'))}</th><th>${esc(t('Kämpfe','Fights'))}</th><th>${esc(t('Einnahmen','Income'))}</th><th>${esc(t('schlechtestes Zehntel','worst tenth'))}</th><th>${esc(t('Ausgaben','Expenses'))}</th><th>${esc(t('Verhältnis','Ratio'))}</th><th>${esc(t('größter Fund','biggest find'))}</th></tr></thead><tbody>${rows}</tbody></table></div>`}
async function dmPruefLook(){clearTimeout(DMPS.t);if(!$('dmpruef'))return;const {r,d}=await apiTry('/api/admin/dungeon/pruefstand');
  if(!$('dmpruef'))return;if(!r.ok){$('dmpruef').innerHTML=`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`;return}
  DMPS.d=d;$('dmpruef').innerHTML=dmPruefBox(d);if(d.laeuft)DMPS.t=setTimeout(dmPruefLook,3000)}
document.addEventListener('click',async e=>{const b=e.target.closest('#dmpruef [data-dmps]');if(!b)return;const k=b.dataset.dmps;
  if(k!=='los'){DMPS.g=+k;if(DMPS.d)$('dmpruef').innerHTML=dmPruefBox(DMPS.d);return}
  b.disabled=true;const {r,d}=await apiTry('/api/admin/dungeon/pruefstand',xjson('POST',{}));
  if(!r.ok){sayToast(dmErr(r.status,d.detail));b.disabled=false;return}DMPS.d=d;$('dmpruef').innerHTML=dmPruefBox(d);DMPS.t=setTimeout(dmPruefLook,3000)});
// Erzähler-Prüfstand (dungeon_erzaehlstand.py, Tabletop-Punkt 4): fixed scenes through the running model, points by fixed
// rules per scene and model side by side; the model's own Einordnung only as a hint beside it; why a scene lost points stands beside it, not
// only in the tooltip (Prüfstand 28.10.: a phone has no tooltip)
const DMES={t:0};
function dmErzBox(x){const ms=Object.entries(x.modelle||{}).sort((a,b)=>b[1].zeit-a[1].zeit),mx=2*x.szenen.length;
  const dot=s=>s?`<span class="dm-es-p" data-p="${s.punkte}" title="${esc(s.grund)}${s.erst?' · '+esc(t('zuerst','first'))+' '+esc(s.erst):''}${s.versuche?' · '+s.versuche+' '+esc(t('Versuche','tries')):''} · ${s.sekunden} s">${s.punkte}</span>${s.punkte<2&&s.grund?`<small class="dm-es-g"> ${esc(s.punkte?t('zuerst','first')+' '+(s.erst||''):s.grund)}${s.fehlt&&s.fehlt.length?' ('+esc(s.fehlt.join(', '))+')':''}</small>`:''}${s.einordnung?`<small class="mut" title="${esc(t('eigene Einschätzung des Modells','the model\'s own view'))}"> ${Math.round(s.einordnung.lebendig*100)}/${Math.round(s.einordnung.folgt*100)}</small>`:''}`:'–';
  const tab=ms.length?`<div class="dm-ps-w"><table class="dm-ps-t dm-es-t"><thead><tr><th>${esc(t('Szene','Scene'))}</th>${ms.map(([n])=>`<th>${esc(n)}</th>`).join('')}</tr></thead><tbody>
    ${x.szenen.map(([id,nm])=>`<tr><td>${esc(nm[L==='en'?1:0])}</td>${ms.map(([,m])=>`<td>${dot((m.szenen||{})[id])}</td>`).join('')}</tr>`).join('')}
    <tr class="dm-es-sum"><td>${esc(t('Punkte','Points'))}</td>${ms.map(([,m])=>`<td><b>${m.punkte}</b> / ${m.max||mx}</td>`).join('')}</tr>
    <tr><td>${esc(t('Dauer','Time'))}</td>${ms.map(([,m])=>`<td>${Math.round(m.sekunden)} s</td>`).join('')}</tr>
    <tr><td>${esc(t('zuletzt','last'))}</td>${ms.map(([,m])=>`<td>${esc(new Date(m.zeit*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))}</td>`).join('')}</tr></tbody></table></div>`
    :`<div class="fh">${esc(t('Noch kein Lauf.','No run yet.'))}</div>`;
  return `<div class="fh">${esc(x.an?t(`Der Spark spielt ${x.szenen.length} feste Szenen durch das laufende Sprachmodell, mit denselben Regeln wie am Tisch. Je Szene 2 Punkte, wenn der erste Versuch passt, 1 nach dem Nachbessern, 0 sonst.`,`The Spark plays ${x.szenen.length} fixed scenes through the running language model, with the same rules as at the table. Per scene 2 points when the first try passes, 1 after a rewrite, 0 otherwise.`):t('Aus. Einschalten unter Funktionen → KI-Dungeon-Master → Prüfstände.','Off. Switch it on under Features → AI Dungeon Master → Test benches.'))}${x.einordnung?' '+esc(t('Die kleinen Zahlen sind die eigene Einschätzung des Modells (lebendig / folgt den Aktionen, in Prozent), sie geben keine Punkte.','The small numbers are the model\'s own view (vivid / follows the actions, in per cent), they give no points.')):''}</div>
    ${tab}<div class="dm-sum">${x.laeuft?`<span class="pill on">${esc(t('prüft gerade','checking now'))}</span>`:''}</div>
    <div class="row"><button type="button" class="b p" data-dmes="los"${!x.an||x.laeuft?' disabled':''}>${esc(t('Jetzt prüfen','Check now'))}</button></div>`}
async function dmErzLook(){clearTimeout(DMES.t);if(!$('dmerzst'))return;const {r,d}=await apiTry('/api/admin/dungeon/erzaehlstand');
  if(!$('dmerzst'))return;if(!r.ok){$('dmerzst').innerHTML=`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`;return}
  $('dmerzst').innerHTML=dmErzBox(d);if(d.laeuft)DMES.t=setTimeout(dmErzLook,5000)}
document.addEventListener('click',async e=>{const b=e.target.closest('#dmerzst [data-dmes]');if(!b)return;b.disabled=true;
  const {r,d}=await apiTry('/api/admin/dungeon/erzaehlstand',xjson('POST',{}));
  if(!r.ok){sayToast(dmErr(r.status,d.detail));b.disabled=false;return}$('dmerzst').innerHTML=dmErzBox(d);DMES.t=setTimeout(dmErzLook,5000)});
// „Erzähler-Fehler“ (dungeon_erzaehlstand.py): the turns a seat gave a 👎 with a fixed reason, heroes with the bench's
// names; „Als Prüfstand-Szene übernehmen“ makes one a scene of the narrator bench
function dmFallBox(x){const G=x.gruende||{},gl=k=>(G[k]||G.sonst||['',''])[L==='en'?1:0],when=z=>new Date(z*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'});
  const taken=new Set((x.szenen||[]).map(s=>s.id.slice(1)));
  const fall=f=>`<details class="dm-fall"><summary><b>${esc(gl(f.grund))}</b> <span class="mut">${esc(when(f.zeit))} · ${esc(f.lang==='en'?'English':'Deutsch')}</span>${taken.has(f.id)?` <span class="pill ok">${esc(t('im Prüfstand','in the bench'))}</span>`:''}</summary>
    ${f.taten.map(a=>`<div class="dm-fall-tat"><b>${esc((x.namen||[])[a.held]||'')}</b>: ${esc(a.text)}</div>`).join('')}
    ${f.wuerfe.length?`<div class="dm-sum">${f.wuerfe.map(w=>`<span class="pill${w.ok?' ok':' warn'}">${esc(w.wofuer||w.wert)}: ${w.w} ${esc(w.ok?t('geschafft','passed'):t('misslungen','failed'))}</span>`).join(' ')}</div>`:''}
    <p class="dm-fall-text">${esc(f.text)}</p>
    <div class="row">${taken.has(f.id)?'':`<button type="button" class="b p" data-dmfall="szene" data-id="${esc(f.id)}"${x.an?'':' disabled'}>${esc(t('Als Prüfstand-Szene übernehmen','Take over as a bench scene'))}</button>`}<button type="button" class="b" data-dmfall="loeschen" data-id="${esc(f.id)}">${esc(t('Löschen','Delete'))}</button></div></details>`;
  const own=(x.szenen||[]).length?`<h4>${esc(t('Eigene Szenen im Erzähler-Prüfstand','Own scenes in the narrator bench'))} <small class="mut">${x.szenen.length} / ${x.eigene_max}</small></h4>${x.szenen.map(s=>`<div class="dm-fall-sz"><span>${esc(s.name[L==='en'?1:0])}</span><button type="button" class="b" data-dmfall="szeneweg" data-id="${esc(s.id)}">${esc(t('Entfernen','Remove'))}</button></div>`).join('')}`:'';
  return `<div class="fh">${esc(x.an||x.beheben?t(`Hier landet jeder Zug, den ein Platz mit 👎 und einem Grund markiert hat (höchstens ${x.max}, die neuesten zuerst). Die Helden heißen hier wie im Prüfstand, Namen von Spielern stehen nie darin. „Als Prüfstand-Szene übernehmen“ spielt den Zug bei jedem Lauf des Erzähler-Prüfstands nach, mit demselben Ausgang jeder Probe.`,`Every turn a seat marked with 👎 and a reason lands here (at most ${x.max}, the newest first). The heroes carry the bench's names, players' names never stand here. "Take over as a bench scene" replays the turn on every run of the narrator bench, with the same outcome of every check.`):t('Fälle entstehen, solange der Erzähler-Prüfstand oder „Erzähler-Fehler beheben“ an ist (Funktionen → KI-Dungeon-Master). Als Prüfstand-Szene übernehmen geht nur mit dem Prüfstand, Löschen immer.','Cases come while the narrator bench or "Fix narrator errors" is on (Features → AI Dungeon Master). Taking over as a bench scene needs the bench, deleting always works.'))}</div>
    ${dmFallWochen(x)}${(x.faelle||[]).length?x.faelle.map(fall).join(''):`<div class="fh">${esc(t('Noch kein Fall.','No case yet.'))}</div>`}${own}`}
// the reports per week and reason, and the reasons that became standing hints of a world (numbers only)
function dmFallWochen(x){const G=x.gruende||{},gl=k=>(G[k]||['',''])[L==='en'?1:0],W=x.wochen||[];if(!W.length)return '';
  const ks=Object.keys(G).filter(k=>W.some(w=>w.gruende[k]));
  const welt=Object.entries(x.welten||{}).filter(([,g])=>g.length);
  return `<h4>${esc(t('Meldungen je Woche','Reports per week'))}</h4><div class="dm-ps-w"><table class="dm-ps-t"><thead><tr><th>${esc(t('Grund','Reason'))}</th>${W.map(w=>`<th>${esc(w.woche)}</th>`).join('')}</tr></thead><tbody>
    ${ks.map(k=>`<tr><td>${esc(gl(k))}</td>${W.map(w=>`<td>${w.gruende[k]||'–'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${welt.length?`<div class="fh">${esc(x.beheben?t('Feste Hinweise für den Erzähler, weil sie in dieser Welt oft gemeldet wurden:','Fixed hints for the narrator, because they were reported often in this world:'):t('Oft gemeldet (feste Hinweise gibt es erst mit „Erzähler-Fehler beheben“):','Reported often (fixed hints only come with "Fix narrator errors"):'))}</div><div class="dm-sum">${welt.map(([w,g])=>`<span class="pill">${esc(w)}: ${esc(g.map(gl).join(', '))}</span>`).join(' ')}</div>`:''}`}
async function dmFallLook(){if(!$('dmfall'))return;const {r,d}=await apiTry('/api/admin/dungeon/erzaehlfehler');if(!$('dmfall'))return;
  $('dmfall').innerHTML=r.ok?dmFallBox(d):`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`}
document.addEventListener('click',async e=>{const b=e.target.closest('#dmfall [data-dmfall]');if(!b)return;const a=b.dataset.dmfall;b.disabled=true;
  const body=a==='szeneweg'?{szene:b.dataset.id,aktion:'loeschen'}:{fall:b.dataset.id,aktion:a};
  const {r,d}=await apiTry('/api/admin/dungeon/erzaehlfehler',xjson('POST',body));
  if(!r.ok){sayToast(r.status===409&&d.detail==='voll'?t('Schon so viele eigene Szenen, wie der Prüfstand nimmt. Entferne erst eine.','Already as many own scenes as the bench takes. Remove one first.'):dmErr(r.status,d.detail));b.disabled=false;return}
  $('dmfall').innerHTML=dmFallBox(d)});
let DMDT=0;
async function dmDingLook(){clearTimeout(DMDT);const box=$('dmding');if(!box)return;const {r,d}=await apiTry('/api/admin/dungeon/dingbilder');
  if(!r.ok||!$('dmding'))return;$('dmding').outerHTML=dmDingAdmin(d);if(d.laeuft)DMDT=setTimeout(dmDingLook,5000)}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmding [data-dmding]');if(!b)return;b.disabled=true;
  const k=b.dataset.dmding,{r,d}=await apiTry('/api/admin/dungeon/dingbilder',k==='stop'?{method:'DELETE'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alle:k==='alle'})});
  if(!r.ok){b.disabled=false;sayToast(dmErr(r.status,d.detail));return}$('dmding').outerHTML=dmDingAdmin(d);if(d.laeuft)DMDT=setTimeout(dmDingLook,5000)});
// ---------------------------------------------------------------- the admin's stories (Geschichten-Planer)
// a story: idea, goal, foe, places, taboos and 3 to 5 acts with a turning point; „Vorschlag erzeugen“ lets the model
// write all of it from keywords, „↻“ one act again; the panel checks both like typed text before anything is kept
const DMP={d:null,g:null,gid:'',err:'',stich:'',hint:'',busy:false,host:false};
// the same form for a host's own story (Eigene Geschichten, dungeon_geschichten): DMP.host, its own sheet and endpoints
const dmPBox=()=>$(DMP.host?'dmgscard':'dmadmcard');
const dmPBase=()=>DMP.host?'/api/profile/dungeon/geschichten/':'/api/admin/dungeon/geschichte/';
function dmPDraw(d){if(DMP.host)dmGSheet();else dmRulesDraw(d,'')}
function dmPlans(d){const gs=d.geschichten||[],P=d.planer,own=gs.filter(g=>!g.von).length;   // a host's own (von) counts with the host
  return `<h3 class="sec">${esc(t('Geschichten','Stories'))} · ${own}/${P.max}</h3>
    <div class="fh">${esc(t('Lege fest, wie eine Geschichte verläuft. Wer eine Runde anlegt, wählt sie aus; den Plan sehen nur du und der Gastgeber.','Set how a story runs. Whoever starts a round picks it; only you and the host see the plan.'))}</div>
    ${gs.length?`<div class="ld-list dm-rl">${gs.map(g=>`<div class="ld-row"><div class="ld-mid"><b>${esc(g.titel)}</b><small>${esc(g.welt_name)} · ${esc(g.ton_name)} · ${g.akte.length} ${esc(t('Akte','acts'))}${g.von?' · '+esc(t('von '+g.von_name,'by '+g.von_name)):''}</small></div><div class="ld-right"><button type="button" class="b" data-dmadm="gedit" data-gid="${esc(g.gid)}">${esc(t('Bearbeiten','Edit'))}</button></div></div>`).join('')}</div>`:''}
    <div class="row"><button type="button" class="b"${own>=P.max?' disabled':''} data-dmadm="gneu">${esc(t('Neue Geschichte','New story'))}</button></div>`}
function dmPlanForm(d){const g=DMP.g,P=d.planer,w=d.wahl;
  const opt=(a,cur)=>a.map(x=>`<option value="${esc(x.id)}"${String(x.id)===String(cur)?' selected':''}>${esc(x.name)}</option>`).join('');
  const nums=[];for(let n=P.akte[0];n<=P.akte[1];n++)nums.push(n);
  const akt=(a,i)=>`<div class="dmp-akt" data-i="${i}"><div class="dm-khead"><b>${esc(t('Akt','Act'))} ${i+1}</b><span><button type="button" class="b" data-dmadm="gakt" data-n="${i+1}"${DMP.busy?' disabled':''} title="${esc(t('Diesen Akt vom Modell neu schreiben lassen','Let the model write this act again'))}">↻ ${esc(t('Neu schreiben','Write again'))}</button>${g.akte.length>P.akte[0]?`<button type="button" class="b" data-dmadm="gminus" data-n="${i}">${esc(t('Entfernen','Remove'))}</button>`:''}</span></div>
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-at" maxlength="60" value="${esc(a.titel||'')}">
    <label>${esc(t('Was geschieht','What happens'))}</label><textarea class="dmp-ai" rows="3" maxlength="${P.inhalt}">${esc(a.inhalt||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Wendepunkt am Ende','Turning point at the end'))}</label><input class="dmp-aw" maxlength="${P.wende}" value="${esc(a.wende||'')}"></div>
    <div><label>${esc(t('Geplante Züge','Planned turns'))}</label><input class="dmp-az" type="number" min="${P.zuege[0]}" max="${P.zuege[1]}" value="${a.zuege||6}"></div></div>
    ${P.quest?`<label>✦ ${esc(t('Besonderes Ding des Akts (frei lassen: keins)','The act\'s special thing (leave empty: none)'))}</label><input class="dmp-ad" maxlength="${P.quest}" value="${esc(a.ding||'')}" placeholder="${esc(t('zum Beispiel der Messingschlüssel','for example the brass key'))}">`:''}
    ${P.spuren?`<label>🔎 ${esc(t('Spuren zum Wendepunkt (eine je Zeile, bis zu '+P.spuren[0]+')','Clues to the turning point (one per line, up to '+P.spuren[0]+')'))}</label><textarea class="dmp-asp" rows="3" maxlength="${P.spuren[0]*(P.spuren[1]+1)}" placeholder="${esc(t('frische Wachsspuren am Turm','fresh wax on the tower'))}">${esc((a.spuren||[]).join('\n'))}</textarea>`:''}</div>`;
  const I=P.import||{};
  return `<h2>${esc(DMP.gid?t('Geschichte bearbeiten','Edit the story'):t('Neue Geschichte','New story'))}</h2><div class="dm-form dmp-form">
    ${I.an?`<div class="dm-k"><div class="lbl">📄 ${esc(t('Abenteuer aus einer Datei','Adventure from a file'))}</div>
      <div class="row"><input type="file" class="dmp-datei" accept="${esc(I.typen.join(','))}" aria-label="${esc(t('Datei mit dem Abenteuer','File with the adventure'))}"><button type="button" class="b p" data-dmadm="gimp"${DMP.busy?' disabled':''}>${esc(DMP.busy?t('Das Modell liest …','The model is reading …'):t('Übernehmen','Import'))}</button></div>
      <small class="mut">${esc(t(`PDF, Word, OpenDocument, Markdown, Text oder HTML bis ${I.mb} MB. Welt, Ton, Tabus und die Zahl der Akte unten gelten; das Modell fasst die Kapitel zu Akten zusammen, das Panel prüft den Entwurf. Erst „Speichern“ behält ihn, die Datei behält der Spark nicht.`,`PDF, Word, OpenDocument, Markdown, text or HTML up to ${I.mb} MB. World, tone, taboos and the number of acts below count; the model joins the chapters into acts, the panel checks the draft. Only "Save" keeps it, the Spark does not keep the file.`))}</small></div>`:''}
    ${DMP.host?'':`<div class="dm-k"><div class="lbl">✨ ${esc(t('Vom Sprachmodell entwerfen lassen','Let the language model draft it'))}</div>
      <textarea class="dmp-stich" rows="2" maxlength="${P.stichworte}" placeholder="${esc(t('verfluchtes Bergdorf, ein Drache, der nur bewacht, eher düster','a cursed mountain village, a dragon that only guards, rather dark'))}">${esc(DMP.stich)}</textarea>
      <div class="row"><select class="dmp-n" aria-label="${esc(t('Akte','Acts'))}">${nums.map(n=>`<option value="${n}"${n===g.akte.length?' selected':''}>${n} ${esc(t('Akte','acts'))}</option>`).join('')}</select><button type="button" class="b p" data-dmadm="gvor"${DMP.busy?' disabled':''}>${esc(DMP.busy?t('Das Modell schreibt …','The model is writing …'):t('Vorschlag erzeugen','Create a proposal'))}</button></div>
      <small class="mut">${esc(t('Das Modell füllt alle Felder; das Panel prüft Länge, Ton und Tabus. Erst „Speichern“ behält die Geschichte.','The model fills every field; the panel checks length, tone and taboos. Only "Save" keeps the story.'))}</small></div>`}
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-titel" maxlength="60" value="${esc(g.titel||'')}">
    <div class="dm-two"><div><label>${esc(t('Welt','World'))}</label><select class="dmp-welt">${opt(w.welten,g.welt)}</select></div><div><label>${esc(t('Ton','Tone'))}</label><select class="dmp-ton">${opt(w.toene,g.ton)}</select></div></div>
    <label>${esc(t('Grundidee','Idea'))}</label><textarea class="dmp-idee" rows="3" maxlength="${P.idee}">${esc(g.idee||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Ziel der Helden','The heroes\' goal'))}</label><input class="dmp-ziel" maxlength="${P.ziel}" value="${esc(g.ziel||'')}"></div><div><label>${esc(t('Gegenspieler','Foe'))}</label><input class="dmp-gegner" maxlength="${P.ziel}" value="${esc(g.gegner||'')}"></div></div>
    <label>${esc(t('Schauplätze (mit Komma, bis zu '+P.orte+')','Places (comma separated, up to '+P.orte+')'))}</label><input class="dmp-orte" value="${esc((g.orte||[]).join(', '))}">
    <label>${esc(t('Tabus: kommt nie vor (mit Komma, bis zu '+P.tabus+')','Taboos: never happens (comma separated, up to '+P.tabus+')'))}</label><input class="dmp-tabus" value="${esc((g.tabus||[]).join(', '))}" placeholder="${esc(t('Spinnen, Folter','spiders, torture'))}">
    ${(P.personen||[]).length?dmPLeute(P,g):''}
    ${g.akte.map(akt).join('')}
    ${g.akte.length<P.akte[1]?`<div class="row"><button type="button" class="b" data-dmadm="gplus">${esc(t('Akt dazu','Add an act'))}</button></div>`:''}
    <label>${esc(t('Hinweis fürs Neuschreiben eines Akts (frei)','Hint for writing an act again (optional)'))}</label><input class="dmp-hint" maxlength="${P.stichworte}" value="${esc(DMP.hint)}" placeholder="${esc(t('mehr Rätsel, weniger Kampf','more riddles, less fighting'))}">
    ${DMP.err?`<div class="err dm-adm-err">${DMP.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmadm="gsave"${DMP.busy?' disabled':''}>${esc(t('Prüfen und speichern','Check and save'))}</button>${DMP.gid?`<button type="button" class="b danger" data-dmadm="gdel">${esc(DMP.host&&DMP.von!=='eigen'?t('Ausblenden','Hide'):t('Löschen','Delete'))}</button>`:''}<button type="button" class="b" data-dmadm="gback">${esc(t('Zurück','Back'))}</button></div></div>`}
// Personen-Katalog 2: known people of the story's world to tick (name and occupation only), up to P.personen_max
function dmPLeute(P,g){const xs=P.personen.filter(p=>p.welt===g.welt),on=g.personen||[],li=dmLang()==='en'?1:0;
  return `<label>${esc(t('Bekannte Personen aus dem Katalog (bis zu '+P.personen_max+')','Known people from the catalog (up to '+P.personen_max+')'))}</label><div class="dmp-leute" data-max="${P.personen_max}">${xs.map(p=>`<label class="dm-check"><input type="checkbox" class="dmp-p" value="${esc(p.id)}"${on.includes(p.id)?' checked':''}> ${esc(p.name)}${p.beruf[li]?` <small class="mut">${esc(p.beruf[li])}</small>`:''}</label>`).join('')||`<small class="mut">${esc(t('In dieser Welt kennt der Katalog noch niemanden.','The catalog knows nobody in this world yet.'))}</small>`}</div>`}
document.body.addEventListener('change',e=>{const x=e.target;if(!x.closest('#dmadmcard .dmp-form,#dmgscard .dmp-form'))return;
  if(x.matches('.dmp-welt')){DMP.g=dmPlanRead();dmPDraw(DMP.d);return}
  if(x.matches('.dmp-p')&&x.checked){const box=x.closest('.dmp-leute');if(box.querySelectorAll('.dmp-p:checked').length>+box.dataset.max)x.checked=false}});
function dmPlanRead(){const c=dmPBox(),q=x=>(c.querySelector(x)||{}).value||'',list=x=>q(x).split(',').map(s=>s.trim()).filter(Boolean);
  DMP.stich=q('.dmp-stich');DMP.hint=q('.dmp-hint');
  const ton=q('.dmp-ton');
  return {titel:q('.dmp-titel').trim(),welt:q('.dmp-welt'),ton:/^\d+$/.test(ton)?+ton:ton,lang:dmLang(),idee:q('.dmp-idee').trim(),ziel:q('.dmp-ziel').trim(),
    gegner:q('.dmp-gegner').trim(),orte:list('.dmp-orte'),tabus:list('.dmp-tabus'),personen:[...c.querySelectorAll('.dmp-p:checked')].map(x=>x.value),
    akte:[...c.querySelectorAll('.dmp-akt')].map(a=>({titel:a.querySelector('.dmp-at').value.trim(),inhalt:a.querySelector('.dmp-ai').value.trim(),
      wende:a.querySelector('.dmp-aw').value.trim(),zuege:Math.floor(+a.querySelector('.dmp-az').value||0),...(a.querySelector('.dmp-ad')&&a.querySelector('.dmp-ad').value.trim()?{ding:a.querySelector('.dmp-ad').value.trim()}:{}),
      ...(a.querySelector('.dmp-asp')?{spuren:a.querySelector('.dmp-asp').value.split('\n').map(s=>s.trim()).filter(Boolean)}:{})}))}}
const dmPlanErr=(r,d)=>Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>')
  :d.detail==='kein vorschlag'?esc(t('Das Modell hat keinen brauchbaren Vorschlag geliefert. Bitte noch einmal oder mit anderen Stichworten.','The model gave no usable proposal. Please try again or with other keywords.'))
  :d.detail==='sprachmodell pausiert'?esc(t('Das Sprachmodell ist gerade pausiert.','The language model is paused right now.'))
  :d.detail==='unlesbar'?esc(t('Die Datei ist nicht lesbar (ein PDF ohne Textschicht oder eine kaputte Datei).','The file cannot be read (a PDF without a text layer or a broken file).'))
  :d.detail==='leer'?esc(t('In der Datei steht zu wenig Text für ein Abenteuer.','The file holds too little text for an adventure.'))
  :d.detail==='zu gross'?esc(t('Die Datei ist zu groß.','The file is too big.'))
  :d.detail==='dateiart'?esc(t('Diese Dateiart geht nicht: PDF, Word, OpenDocument, Markdown, Text oder HTML.','This file type does not work: PDF, Word, OpenDocument, Markdown, text or HTML.')):esc(dmErr(r.status,d.detail));
async function dmPlanClick(b,k){const d=DMP.d,w=d.wahl;if(DMP.busy)return;
  if(k==='gneu'){DMP.gid='';DMP.err='';DMP.stich='';DMP.hint='';DMP.g={titel:'',welt:w.welten[0].id,ton:(w.toene[1]||w.toene[0]).id,idee:'',ziel:'',gegner:'',orte:[],tabus:[],
    akte:Array.from({length:d.planer.akte[0]},()=>({titel:'',inhalt:'',wende:'',zuege:6}))};dmPDraw(d);return}
  if(k==='gedit'){const g=(d.geschichten||[]).find(x=>x.gid===b.dataset.gid);if(!g)return;DMP.gid=g.gid;DMP.err='';DMP.stich='';DMP.hint='';DMP.g=JSON.parse(JSON.stringify(g));dmPDraw(d);return}
  if(k==='gback'){DMP.g=null;dmPDraw(d);return}
  const g=dmPlanRead();DMP.g=g;
  if(k==='gplus'){g.akte.push({titel:'',inhalt:'',wende:'',zuege:6});dmPDraw(d);return}
  if(k==='gminus'){g.akte.splice(+b.dataset.n,1);dmPDraw(d);return}
  if(k==='gdel'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich löschen?','Really delete?');return}
    if(DMP.host){await dmGWas('loeschen',DMP.gid);return}
    const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+DMP.gid+'?lang='+dmLang(),{method:'DELETE'});if(r.ok){DMP.g=null;dmPDraw(x)}return}
  if(k==='gsave'){const {r,d:x}=await apiTry(dmPBase()+(DMP.gid||'neu')+'?lang='+dmLang(),xjson('PUT',g));
    if(r.ok){DMP.g=null;if(DMP.host)dmGDone(x);else dmPDraw(x);sayToast(t('Geschichte gespeichert','Story saved'));return}DMP.err=dmPlanErr(r,x);dmPDraw(d);return}
  const n=Math.floor(+(((dmPBox().querySelector('.dmp-n'))||{}).value||g.akte.length));
  if(k==='gimp'){const f=((dmPBox().querySelector('.dmp-datei')||{}).files||[])[0];
    if(!f){DMP.err=esc(t('Bitte zuerst eine Datei wählen.','Please pick a file first.'));dmPDraw(d);return}
    const fd=new FormData();fd.append('file',f,f.name);fd.append('welt',g.welt);fd.append('ton',String(g.ton));fd.append('akte',String(n));fd.append('tabus',g.tabus.join(','));fd.append('lang',g.lang);
    DMP.busy=true;DMP.err='';dmPDraw(d);
    const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/import',{method:'POST',body:fd});DMP.busy=false;
    if(r.ok&&x.plan){DMP.g=Object.assign(x.plan,{lang:g.lang});sayToast(t(`Entwurf aus ${x.kapitel} Kapiteln, bitte prüfen und speichern`,`Draft from ${x.kapitel} chapters, please check and save`))}else DMP.err=dmPlanErr(r,x);
    if(DMP.g&&dmPBox())dmPDraw(DMP.d);return}
  const body=k==='gvor'?{welt:g.welt,ton:g.ton,akte:n,stichworte:DMP.stich,tabus:g.tabus,lang:g.lang}:{plan:g,n:+b.dataset.n,hinweis:DMP.hint};
  if(k==='gvor'&&DMP.stich.trim().length<3){DMP.err=esc(t('Bitte ein paar Stichworte eingeben.','Please enter a few keywords.'));dmPDraw(d);return}
  DMP.busy=true;DMP.err='';dmPDraw(d);
  const {r,d:x}=await apiTry(DMP.host?'/api/profile/dungeon/geschichten/akt':'/api/admin/dungeon/geschichte/'+(k==='gvor'?'vorschlag':'akt'),xjson('POST',body));DMP.busy=false;
  if(r.ok&&x.plan){DMP.g=Object.assign(x.plan,{lang:g.lang})}else DMP.err=dmPlanErr(r,x);
  if(DMP.g&&dmPBox())dmPDraw(DMP.d)}
// ---------------------------------------------------------------- Eigene Geschichten (dungeon_geschichten): Bearbeiten in
// the planner's form on its own sheet, Kopieren, Löschen / Ausblenden, „＋ Neue Geschichte“ (tone, keywords, „Erstellen“)
const DMG={neu:null,busy:false,err:''};
const dmGBase='/api/profile/dungeon/geschichten/';
function dmGModal(){let m=$('dmgs');if(!m){m=document.createElement('div');m.id='dmgs';m.className='modal';
  m.innerHTML='<div class="card modalcard dmadmcard" id="dmgscard"></div>';document.body.appendChild(m)}m.style.display='grid';return m}
function dmGClose(){const m=$('dmgs');if(m)m.style.display='none';DMP.host=false;DMP.g=null;DMG.neu=null;DMG.busy=false}
function dmGSheet(){const c=$('dmgscard');if(!c)return;if(DMG.neu)c.innerHTML=dmGNeu();else if(DMP.g)c.innerHTML=dmPlanForm(DMP.d)}
function dmGNeu(){const w=DM.data.wahl,N=DMG.neu;
  return `<h2>＋ ${esc(t('Neue Geschichte','New story'))}</h2><div class="dm-form">
    <div class="lbl">${esc(t('Ton','Tone'))}</div><div class="dm-cards dm-klein">${w.toene.map(x=>`<button type="button" class="dm-card${String(x.id)===String(N.ton)?' on':''}" data-dmgton="${esc(String(x.id))}" aria-pressed="${String(x.id)===String(N.ton)}"><b>${esc((x.zeichen||'')+' '+x.name)}</b></button>`).join('')}</div>
    <label>${esc(t('Stichworte (frei)','Keywords (optional)'))}</label><textarea class="dmg-stich" rows="2" maxlength="${w.eigene.planer.stichworte}" placeholder="${esc(t('verfluchtes Bergdorf, ein Drache, der nur bewacht','a cursed mountain village, a dragon that only guards'))}">${esc(N.stich||'')}</textarea>
    <small class="mut">${esc(t('Das Sprachmodell schreibt Titel, Grundidee und Akte in der gewählten Welt, das Panel prüft den Entwurf mit festen Regeln. Danach kannst du sie über ⋯ bearbeiten.','The language model writes title, idea and acts in the chosen world, the panel checks the draft by fixed rules. Afterwards you can edit it with ⋯.'))}</small>
    ${DMG.err?`<div class="err dm-adm-err">${DMG.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmgnw="erstellen"${DMG.busy?' disabled':''}>${esc(DMG.busy?t('Das Modell schreibt …','The model is writing …'):t('Erstellen','Create'))}</button><button type="button" class="b" data-dmgnw="selbst"${DMG.busy?' disabled':''}>${esc(t('Selbst schreiben','Write it yourself'))}</button><button type="button" class="b" data-dmgnw="zu">${esc(t('Abbrechen','Cancel'))}</button></div></div>`}
const dmGWelt=()=>{const w=$('dmview'),b=w&&w.querySelector('.dmf-welt .on');return b?b.dataset.dmseg:DM.welt};
function dmGDone(x){const D=DM.data;D.wahl.geschichten=x.geschichten||D.wahl.geschichten;if(D.wahl.eigene)D.wahl.eigene.aus=x.aus||0;dmGClose();
  const w=$('dmview'),f=w&&w.querySelector('.dm-form');if(!f||!f.querySelector('.dmf-gesch'))return;
  f.querySelector('.dmf-gesch').innerHTML=dmStories(D.wahl,dmGWelt());
  dmStory(w,(x.gid&&f.querySelector(`.dmf-gesch [data-dmgs="${x.gid}"]`))||f.querySelector('.dmf-gesch [data-dmgs=""]'))}
function dmGForm(g,gid,von){const D=DM.data;DMP.host=true;DMG.neu=null;DMP.gid=gid;DMP.von=von;DMP.err='';DMP.stich='';DMP.hint='';
  DMP.d={planer:D.wahl.eigene.planer,wahl:D.wahl};DMP.g=g;dmGModal();dmGSheet()}
async function dmGWas(was,gid){const L='?lang='+dmLang();
  if(was==='bearbeiten'){const {r,d}=await apiTry(dmGBase+gid+L);if(!r.ok){sayToast(dmErr(r.status,d.detail));return}dmGForm(d,gid,d.von);return}
  const {r,d}=was==='kopieren'?await apiTry(dmGBase+gid+'/kopie',xjson('POST',{lang:dmLang()}))
    :was==='zeigen'?await apiTry(dmGBase+'zeigen',xjson('POST',{lang:dmLang()})):await apiTry(dmGBase+gid+L,{method:'DELETE'});
  if(!r.ok){sayToast(dmErr(r.status,d.detail));return}dmGDone(d);
  sayToast(was==='kopieren'?t('Kopie angelegt','Copy made'):was==='zeigen'?t('Wieder da','Back again'):t('Erledigt','Done'))}
document.body.addEventListener('click',async e=>{const m=e.target.closest('#dmview [data-dmgmehr]');
  if(m){const p=m.parentNode.querySelector('.ic-pop'),open=!p.hidden;document.querySelectorAll('.ic-pop').forEach(x=>x.hidden=true);p.hidden=open;return}
  const a=e.target.closest('#dmview [data-dmgwas]');
  if(a){if(a.dataset.dmgwas==='loeschen'&&a.dataset.sure!=='1'){a.dataset.sure='1';a.textContent=t('Wirklich?','Really?');return}
    a.closest('.ic-pop').hidden=true;await dmGWas(a.dataset.dmgwas,a.dataset.gid);return}
  if(e.target.closest('#dmview [data-dmgzeigen]')){await dmGWas('zeigen','');return}
  if(e.target.closest('#dmview [data-dmgneu]')){const w=$('dmview'),on=w&&w.querySelector('.dmf-ton .on');
    DMG.neu={ton:on?on.dataset.dmseg:String((DM.data.wahl.toene[1]||DM.data.wahl.toene[0]).id),stich:''};DMG.err='';DMG.busy=false;DMP.host=true;dmGModal();dmGSheet();return}
  const c=e.target.closest('#dmgscard [data-dmgton],#dmgscard [data-dmgnw],#dmgscard [data-dmadm]');if(!c)return;const N=DMG.neu,box=$('dmgscard');
  if(N)N.stich=(box.querySelector('.dmg-stich')||{}).value||N.stich;
  if(c.dataset.dmgton){N.ton=c.dataset.dmgton;dmGSheet();return}
  const k=c.dataset.dmgnw;
  if(k==='zu'||c.dataset.dmadm==='gback'){dmGClose();return}
  if(c.dataset.dmadm){if(c.dataset.dmadm[0]==='g')await dmPlanClick(c,c.dataset.dmadm);return}
  const ton=/^\d+$/.test(N.ton)?+N.ton:N.ton,P=DM.data.wahl.eigene.planer;
  if(k==='selbst'){dmGForm({titel:'',welt:dmGWelt(),ton,idee:'',ziel:'',gegner:'',orte:[],tabus:[],akte:Array.from({length:P.akte[0]},()=>({titel:'',inhalt:'',wende:'',zuege:6}))},'','eigen');return}
  if(k==='erstellen'){if(DMG.busy)return;DMG.busy=true;DMG.err='';dmGSheet();
    const {r,d}=await apiTry(dmGBase+'erstellen',xjson('POST',{welt:dmGWelt(),ton,stichworte:N.stich,lang:dmLang()}));DMG.busy=false;
    if(r.ok){dmGDone(d);sayToast(t('Geschichte erstellt','Story created'));return}DMG.err=dmPlanErr(r,d);dmGSheet()}});
