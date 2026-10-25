// KI-Dungeon-Master: big windows over the table (5k). The side column keeps a short card of the own hero with
// buttons; the hero sheet, the merchant, a single item and a power of „Das kann ich“ open as a window in the table's look. The window is
// drawn with the table on every repaint (dmTable), so it always shows the panel's current state; ✕, Esc or a tap
// beside it closes it, a new turn shows a line „zum Tisch“. Only the view lives here, every action is the
// table's own (data-dmhero, data-dmtx), the panel checks it as before.
const DMW={p:{w:'',ding:'',zug:0},g:{w:'',ding:'',zug:0}};
function dmMeKurz(v,mode){const h=v.ich;if(!h)return '';const open=v.status!=='ende',m=v.markt&&open,mir=(v.angebote||[]).filter(o=>o.mir).length,boden=open?(v.boden||[]).length+(v.boden_gold?1:0):0;
  return `<div class="dm-me dm-mek"><div class="dm-mek-k">${h.bild?`<span class="dm-mek-b">${dmImg(mode,v,'p',v.pid,h.stufe)}</span>`:''}<div><h4>${esc(h.name)}</h4><small class="mut">${esc(h.volk)} ${esc(h.klasse)} · ${esc(t('Stufe','Level'))} ${h.stufe}</small></div></div>
    <div class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${h.leben}/${h.leben_max}</span></div>${dmBar(h.leben,h.leben_max,h.leben*3<h.leben_max?'low':'')}${dmZust(h)}${h.ep_tisch?`<small class="dm-eptisch">+${h.ep_tisch} ${esc(t('EP noch am Tisch','EP still at the table'))}</small>`:''}
    <div class="dm-line"><span>${esc(t('Gold','Gold'))} <b>${h.gold}</b></span><span>${esc(t('Tasche','Bag'))} ${h.tasche.length}/${h.tasche_max}</span></div>
    ${h.punkte||h.wahl.length?`<button type="button" class="dm-hint dm-hintb" data-dmfen="bogen" data-dmbt="werte">${esc(t('Neue Stufe: im Heldenbogen verteilen.','New level: spend it in the hero sheet.'))}</button>`:''}
    ${mir?`<div class="dm-hint">${esc(mir===1?t('Ein Tauschangebot wartet.','A trade offer is waiting.'):t(mir+' Tauschangebote warten.',mir+' trade offers are waiting.'))}</div>`:''}
    ${boden?`<small class="mut">${esc(boden===1?t('Hier liegt 1 Ding.','1 thing lies here.'):t('Hier liegen '+boden+' Dinge.',boden+' things lie here.'))}</small>`:''}
    <div class="dm-fknoepfe"><button type="button" class="b p" data-dmfen="bogen">📜 ${esc(t('Heldenbogen','Hero sheet'))}</button>${m?`<button type="button" class="b" data-dmfen="haendler">⚖ ${esc(t('Händler','Merchant'))}</button>`:''}${v.siedlung?`<button type="button" class="b" data-dmfen="siedlung">🏘 ${esc(t('Siedlung','Settlement'))}</button>`:''}</div></div>`}
// Gold mit Zweck (Idee 9): the settlement's fixed offers, priced by the panel; every button is the hero's own move (data-dmhero)
const DMDIENST={gasthaus:'🛏',schmied:'🔨',lehre:'📖',geruecht:'🗣'};
function dmSiedlung(v){const s=v.siedlung,W=v.werte||{},knopf=(d,attr,label)=>`<button type="button" class="b p" data-dmhero="dienst" data-id="${d.id}"${attr||''}${!d.frei||s.gold<d.preis?' disabled':''}>${esc(label||t('Bezahlen','Pay'))} · ${d.preis} ${esc(t('Gold','gold'))}</button>`;
  const card=d=>`<div class="dm-ware dm-dienstk"><span class="dm-ware-b" aria-hidden="true">${DMDIENST[d.id]}</span><b>${esc(d.name)}</b><small>${esc(d.satz)}</small>${
    d.id==='schmied'?(s.kaputt.length?s.kaputt.map(it=>knopf(d,` data-i="${esc(it.i)}"`,t('Flicken: ','Mend: ')+it.name)).join(''):`<small class="mut">${esc(t('Nichts zerbrochen.','Nothing broken.'))}</small>`)
    :d.id==='lehre'?`<div class="dm-iacts">${Object.keys(W).map(k=>knopf(Object.assign({},d,{frei:s.lehre!==k}),` data-wert="${esc(k)}"`,W[k])).join('')}</div>${s.lehre?`<small class="mut">${esc(t('Jetzt: '+(W[s.lehre]||s.lehre)+' +1','Now: '+(W[s.lehre]||s.lehre)+' +1'))}</small>`:''}`
    :knopf(d)}</div>`;
  return `<small class="mut">${esc(t('Preise legt das Panel nach der Stufe der Gruppe fest.','The panel sets the prices by the group\'s level.'))} · ${esc(t('Dein Gold','Your gold'))}: <b>${s.gold}</b></small><div class="dm-waren">${s.dienste.map(card).join('')}</div>`}
// the merchant as big cards: picture in the rarity's frame, lines, price; below what the own bag can sell or have named
function dmShop(v){const h=v.ich,m=v.markt;
  const ware=m.ware.map(it=>`<div class="dm-ware ${DMSEL[it.selten]||''}" data-dmi="${esc(it.i)}"><span class="dm-ware-b">${dmDing(it)}</span><b>${esc(it.name)}</b>${dmCmp(it)}<small>${esc(it.selten_name)}${it.kg?' · '+String(it.kg).replace('.',L==='en'?'.':',')+' kg':''}</small>${it.satz?`<small class="dm-isatz">„${esc(it.satz)}“</small>`:''}${it.info?`<small class="dm-iinfo">${esc(it.info)}</small>`:''}<small>${it.zeilen.map(esc).join(' · ')}</small>
    <button type="button" class="b p" data-dmhero="kaufen" data-i="${esc(it.i)}"${h.gold<it.preis?' disabled':''}>${esc(t('Kaufen','Buy'))} · ${it.preis} ${esc(t('Gold','gold'))}</button></div>`).join('');
  const mine=h.tasche.filter(it=>m.verkauf[it.i]||m.erkennen[it.i]).map(it=>dmItem(it,`<div class="dm-iacts">${m.verkauf[it.i]?`<button type="button" class="b" data-dmhero="verkaufen" data-i="${esc(it.i)}">${esc(t('Verkaufen','Sell'))} · ${m.verkauf[it.i]} ${esc(t('Gold','gold'))}</button>`:''}${m.erkennen[it.i]?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}"${h.gold<m.erkennen[it.i]?' disabled':''}>${esc(t('Erkennen lassen','Have it named'))} · ${m.erkennen[it.i]} ${esc(t('Gold','gold'))}</button>`:''}</div>`)).join('');
  return `${m.satz?`<p class="dm-isatz">„${esc(m.satz)}“</p>`:''}<small class="mut">${esc(t('Preise legt das Panel fest.','The panel sets the prices.'))}${m.rabatt?' '+esc(t('Dein Charisma: '+m.rabatt+' % Rabatt.','Your Charisma: '+m.rabatt+' % off.')):''} · ${esc(t('Dein Gold','Your gold'))}: <b>${h.gold}</b></small>
    <div class="dm-waren">${ware||`<small class="mut">${esc(t('Ausverkauft.','Sold out.'))}</small>`}</div>
    ${mine?`<h5>${esc(t('Aus deiner Tasche','From your bag'))}</h5><div class="dm-bag dm-bag-k">${mine}</div>`:''}`}
// one item by its key: bag, equipment slot („an:<slot>“), merchant or ground; a power of „Das kann ich“ („k:kf:<id>“, „k:kz:<id>“)
function dmFind(v,key){const h=v.ich;if(!h||!key)return null;
  if(key.startsWith('g:')||key.startsWith('kg:'))return dmFoeFind(v,key);
  if(key.startsWith('b:')){const [n,i]=key.slice(2).split(':'),e=[...(v.log||[])].reverse().find(x=>x.art==='beute'&&String(x.n)===n&&x.item&&x.item.i===i);if(!e)return null;
    const mine=h.tasche.find(x=>x.i===i),boden=v.status!=='ende'&&(v.boden||[]).find(x=>x.i===i);   // still in the own bag or on the ground: its buttons
    return mine?{it:mine,wo:'tasche'}:boden?{it:boden,wo:'boden'}:{it:e.item,wo:'beute',wer:e.name}}
  if(key.startsWith('k:')){const k=h.kann||{faehigkeiten:[],zauber:[]},id=key.slice(5),x=(key.startsWith('k:kf:')?k.faehigkeiten:k.zauber).find(y=>y.id===id);
    return x?{kann:x,it:x,wo:'kann',zauber:key.startsWith('k:kz:')}:null}
  if(key.startsWith('an:')){const k=key.slice(3),it=h.an[k];return it?{it,wo:'an',k}:null}
  if(key.startsWith('s:')){const [pid,k]=key.slice(2).split('|'),p=(v.plaetze||[]).find(x=>x.pid===pid),it=p&&p.karte&&p.karte.dinge.find(d=>d.platz===k);return it?{it,wo:'fremd',wer:p.name}:null}
  const a=[['tasche',h.tasche],['ware',v.markt&&v.status!=='ende'?v.markt.ware:[]],['boden',v.status!=='ende'?v.boden||[]:[]]];
  for(const [wo,l] of a){const it=(l||[]).find(x=>x.i===key);if(it)return {it,wo}}return null}
// a foe to look at closely (Dominik 2026-10-24 „click auf beute etc. sollte ein fenster aufgehen lassen um es genauer zu
// betrachten - auch gegener“, 1a): its card from an encounter („g:<turn>:<n>“) or the fight („kg:<k>“), with the others to page through
function dmFoeFind(v,key){let list=[];
  if(key.startsWith('kg:'))list=((v.kampf||{}).gegner||[]).map(g=>({g,key:'kg:'+g.k}));
  else{const [n]=key.slice(2).split(':'),e=[...(v.log||[])].reverse().find(x=>x.art==='begegnung'&&String(x.n)===n);list=e?(e.gegner||[]).map((g,j)=>({g,key:'g:'+n+':'+j})):[]}
  const i=list.findIndex(x=>x.key===key);return i<0?null:{gegner:list[i].g,it:list[i].g,wo:'gegner',list:list.map(x=>x.key),at:i}}
function dmFoeDet(f){const g=f.gegner,n=f.list.length,fx=x=>(x>=0?'+':'')+x,chip=(k,a,b)=>`<span class="dm-pchip${k?' '+k:''}"><small>${esc(a)}</small><b>${esc(String(b))}</b></span>`;
  const blatt=n>1?`<div class="dm-blatt"><button type="button" class="b" data-dmblatt="-1" aria-label="${esc(t('Voriger Gegner','Previous foe'))}">‹</button><small>${f.at+1} / ${n}</small><button type="button" class="b" data-dmblatt="1" aria-label="${esc(t('Nächster Gegner','Next foe'))}">›</button></div>`:'';
  const gr={winzig:t('winzig','tiny'),klein:t('klein','small'),mittel:t('mittelgroß','medium'),gross:t('groß','large'),riesig:t('riesig','huge'),gigantisch:t('gigantisch','gargantuan')}[g.groesse]||'';
  const leben=g.max?`<div class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${g.leben} / ${g.max}</span></div>${dmBar(g.leben,g.max,g.leben*3<g.max?'low':'')}`:'';
  return `<div class="dm-detail dm-gdet"><span class="dm-detail-b">${dmDing(g)}</span><div class="dm-detail-t">${blatt}
    <div><b class="dm-detail-n">${esc(g.name)}</b>${g.anzahl>1?` <span class="pill">×${g.anzahl}</span>`:''}${g.aus?` <span class="pill">${esc(g.aus==='besiegt'?t('besiegt','defeated'):t('geflohen','fled'))}</span>`:''}</div>
    ${gr?`<small>${esc(gr)}</small>`:''}${g.info?`<p class="dm-iinfo">${esc(g.info)}</p>`:''}${leben}
    ${g.rk!=null?`<div class="dm-pchips">${chip('',t('Stufe','Level'),dmCr(g.stufe))}${g.max?'':chip('leben','❤',g.leben)}${chip('',t('RK','AC'),g.rk)}${chip('kraft',t('Angriff','Attack'),fx(g.angriff))}${chip('',t('Schaden','Damage'),g.schaden)}${chip('up',t('EP','XP'),g.ep)}</div>`:''}
    ${(g.werte||[]).length?`<div class="dm-gwerte">${g.werte.map(w=>`<span title="${esc(w.name)}"><small>${esc(w.kurz)}</small><b>${w.wert}</b><i>${esc(fx(w.mod))}</i></span>`).join('')}</div>`:''}
    ${g.boss?`<p class="dm-gboss">👑 ${esc(t('Boss: mehr Leben je Held, ab halbem Leben eine zweite Phase, zwei Angriffe je Zug, bessere Beute.','Boss: more life per hero, a second phase from half life, two attacks a turn, a better find.'))}${g.phase===2?' <b>'+esc(t('Zweite Phase!','Second phase!'))+'</b>':''}</p>`:''}
    ${g.art?`<small>${esc(t('Schaden: ','Damage: ')+g.art)}</small>`:''}${[['schwaeche','💥',t('Schwach gegen','Weak against'),'dm-gres dm-gres-schwaeche'],['resistenz','🛡',t('Widersteht','Resists'),'dm-gres'],['immun','⛔',t('Immun gegen','Immune to'),'dm-gres dm-gres-immun']].filter(([k])=>(g[k]||[]).length).map(([k,i,l,c])=>`<div class="${c}">${i} ${esc(l)}: ${esc(g[k].join(', '))}</div>`).join('')}
    ${(g.zustaende||[]).length?`<h5>${esc(t('Kann bewirken','Can cause'))}</h5><ul class="dm-detail-w">${g.zustaende.map(z=>`<li><b>${esc(z.name)}</b>: ${esc(z.info)}</li>`).join('')}</ul>`:''}</div></div>`}
function dmDetail(v,f){const it=f.it,h=v.ich,open=v.status!=='ende',kg=it.kg?String(it.kg).replace('.',L==='en'?'.':',')+' kg':'';
  const acts=!open||f.wo==='fremd'?'':f.wo==='tasche'?dmActs(v,it):f.wo==='an'?`<div class="dm-iacts"><button type="button" class="b" data-dmhero="ablegen" data-platz="${esc(f.k)}">${esc(t('Ablegen','Unequip'))}</button></div>`
    :f.wo==='ware'?`<div class="dm-iacts"><button type="button" class="b p" data-dmhero="kaufen" data-i="${esc(it.i)}"${h.gold<it.preis?' disabled':''}>${esc(t('Kaufen','Buy'))} · ${it.preis} ${esc(t('Gold','gold'))}</button></div>`
    :f.wo==='beute'?'':`<div class="dm-iacts"><button type="button" class="b" data-dmhero="aufheben" data-i="${esc(it.i)}">${esc(t('Aufheben','Pick up'))}</button></div>`;
  const wo={tasche:t('In deiner Tasche','In your bag'),an:t('Angelegt','Equipped'),ware:t('Beim Händler','At the merchant'),boden:t('Liegt hier','Lying here'),fremd:t('Trägt '+f.wer,'Worn by '+f.wer),beute:t('Beute für '+f.wer,'Loot for '+f.wer)}[f.wo];
  return `<div class="dm-detail ${DMSEL[it.selten]||''}"><span class="dm-detail-b">${dmDing(it)}</span><div class="dm-detail-t"><small class="mut">${esc(wo)}</small>
    <div><b class="dm-detail-n">${esc(it.name)}</b>${dmCmp(it)}${it.n>1?` <span class="pill">×${it.n}</span>`:''}</div><small>${esc(it.selten_name||'')}${kg?' · '+kg:''}</small>
    ${it.fund?`<p class="dm-ifund">${esc(t('Gefunden in: ','Found in: ')+it.fund)}</p>`:''}${it.satz?`<p class="dm-isatz">„${esc(it.satz)}“</p>`:''}${it.info?`<p class="dm-iinfo">${esc(it.info)}</p>`:''}${(it.zeilen||[]).length?`<ul class="dm-detail-w">${it.zeilen.map(z=>`<li>${dmFx(z)}</li>`).join('')}</ul>`:''}
    ${it.u?`<small class="mut">${esc(t('Noch nicht erkannt: was es kann, zeigt sich erst, wenn es jemand erkennt.','Not yet identified: what it does shows only once someone identifies it.'))}</small>`:''}${acts}</div></div>`}
const DMFENK={bogen:'dm-fen dm-fen-bogen',haendler:'dm-fen dm-fen-haendler',siedlung:'dm-fen dm-fen-haendler',ding:'dm-fen dm-fen-ding'};
function dmFenBox(kind,title,body,neu){return `<div class="${DMFENK[kind]}" data-dmfenbg="${kind==='ding'?'ding':'w'}"><div class="dm-fen-box" role="dialog" aria-modal="true" aria-label="${esc(title)}">
  <div class="dm-fen-kopf"><h3>${esc(title)}</h3><button type="button" class="ic-ib" data-dmfenzu="${kind==='ding'?'ding':'w'}" title="${esc(t('Schließen','Close'))}" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>${neu||''}<div class="dm-fen-body">${body}</div></div></div>`}
function dmFenster(v,mode){DMCMP=v.vergleich||{};const W=DMW[mode],h=v.ich;if(!h){W.w=W.ding='';return ''}
  if(W.w==='haendler'&&!(v.markt&&v.status!=='ende')||W.w==='siedlung'&&!v.siedlung)W.w='';
  const f=dmFind(v,W.ding);if(!f)W.ding='';if(!W.w&&!W.ding)return '';
  const neu=W.zug&&v.zug>W.zug?`<div class="dm-fen-neu" role="status">${esc(t('Neuer Zug '+v.zug+': der Dungeon-Master hat weitererzählt.','New turn '+v.zug+': the Dungeon Master has told on.'))}<button type="button" class="b" data-dmfenzu="alle">${esc(t('Zum Tisch','To the table'))}</button></div>`:'';
  const main=W.w==='bogen'?dmFenBox('bogen','📜 '+h.name,dmMe(v,mode),neu):W.w==='haendler'?dmFenBox('haendler','⚖ '+v.markt.name,dmShop(v),neu):W.w==='siedlung'?dmFenBox('siedlung','🏘 '+v.siedlung.name,dmSiedlung(v),neu):'';
  const det=f&&(f.gegner?dmFoeDet(f):f.kann?dmKtDet(f.kann,v.status!=='ende'&&f.kann.rest!==0?dmKannSay(f.kann,f.zauber):''):dmDetail(v,f));
  return main+(f?dmFenBox('ding',f.it.name,det,main?'':neu):'')}
// the window's own scroll stays across the table's repaints
function dmFenKeep(w){const s=[...w.querySelectorAll('.dm-fen-body')].map(x=>[x.closest('.dm-fen').className,x.scrollTop]);
  return ()=>s.forEach(([c,y])=>{const b=w.querySelector(`.dm-fen[class="${c}"] .dm-fen-body`);if(b)b.scrollTop=y})}
const dmFenMode=el=>el.closest('#dgcard')?'g':'p';
const dmFenDraw=mode=>mode==='g'?dgDraw():dmDraw();
const dmFenV=mode=>mode==='g'?DG.v:DM.v;
function dmFenZu(mode,was){if(was==='hilfe'){DMA.hilfe=false;dmFenDraw(mode);return}const W=DMW[mode];if(was==='ding'&&W.ding)W.ding='';else{W.w='';W.ding=''}if(!W.w&&!W.ding)W.zug=0;dmFenDraw(mode)}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmfen],#dgcard [data-dmfen],#dmview [data-dmfenzu],#dgcard [data-dmfenzu]');
  const mode=b?dmFenMode(b):'';
  if(b&&b.dataset.dmfen){const W=DMW[mode],v=dmFenV(mode);
    W.w=b.dataset.dmfen;W.ding='';W.zug=v?v.zug:0;dmFenDraw(mode);return}
  if(b){dmFenZu(mode,b.dataset.dmfenzu);return}
  const bg=e.target.closest('.dm-fen');if(bg&&e.target===bg){dmFenZu(dmFenMode(bg),bg.dataset.dmfenbg);return}
  // a tap on an item (not on its buttons) opens its window: bag, equipment, merchant, ground
  // a worn thing on a seat card: the own one as „an:<slot>“ (with its buttons), another hero's to look at
  const gb=e.target.closest('#dmview [data-dmgeg],#dgcard [data-dmgeg],#dmview [data-dmbeute],#dgcard [data-dmbeute]');
  if(gb&&!e.target.closest('button')){const m=dmFenMode(gb),v=dmFenV(m),key=gb.dataset.dmgeg||gb.dataset.dmbeute;if(!v||!dmFind(v,key))return;
    const W=DMW[m];W.ding=key;if(!W.zug)W.zug=v.zug;dmFenDraw(m);return}
  const bl=e.target.closest('#dmview [data-dmblatt],#dgcard [data-dmblatt]');if(bl){dmBlatt(dmFenMode(bl),+bl.dataset.dmblatt);return}
  const sd=e.target.closest('#dmview [data-dmsding],#dgcard [data-dmsding]');
  if(sd){const m=dmFenMode(sd),v=dmFenV(m),[pid,k]=sd.dataset.dmsding.split('|'),key=v&&v.pid===pid?'an:'+k:'s:'+pid+'|'+k;
    if(!v||!dmFind(v,key))return;const W=DMW[m];W.ding=key;if(!W.zug)W.zug=v.zug;dmFenDraw(m);return}
  const kt=e.target.closest('#dmview .dm-bogen [data-dmkt],#dgcard .dm-bogen [data-dmkt]');   // a power of „Das kann ich“: its window
  if(kt){const m=dmFenMode(kt),v=dmFenV(m),key='k:'+kt.dataset.dmkt;if(!v||!dmFind(v,key))return;const W=DMW[m];W.ding=key;if(!W.zug)W.zug=v.zug;dmFenDraw(m);return}
  const it=e.target.closest('#dmview [data-dmi],#dgcard [data-dmi],#dmview .dm-pl.voll,#dgcard .dm-pl.voll');
  if(!it||e.target.closest('button,select,input,label,a,textarea'))return;const m=dmFenMode(it),v=dmFenV(m),key=it.dataset.dmi||'an:'+it.dataset.dmslot;
  if(!v||!dmFind(v,key))return;const W=DMW[m];W.ding=key;if(!W.zug)W.zug=v.zug;dmFenDraw(m)});
// page through the foes of the open window: ‹ › and the arrow keys
function dmBlatt(m,d){const W=DMW[m],v=dmFenV(m),f=v&&dmFind(v,W.ding);if(!f||!f.list||f.list.length<2)return;W.ding=f.list[(f.at+d+f.list.length)%f.list.length];dmFenDraw(m)}
document.addEventListener('keydown',e=>{if(/^Arrow(Left|Right)$/.test(e.key)&&!e.target.closest('input,textarea,select')){for(const m of ['g','p']){const W=DMW[m];
    if(W.ding&&(W.ding.startsWith('g:')||W.ding.startsWith('kg:'))&&document.querySelector(m==='g'?'#dgcard .dm-fen-ding':'#dmview .dm-fen-ding')){dmBlatt(m,e.key==='ArrowRight'?1:-1);return}}}
  if((e.key==='Enter'||e.key===' ')&&e.target.closest&&e.target.closest('[data-dmgeg]')){e.preventDefault();e.target.click();return}});
document.addEventListener('keydown',e=>{const hf=document.querySelector('#dmview .dm-fen-hilfe,#dgcard .dm-fen-hilfe');
  if(hf&&/^Arrow(Left|Right)$/.test(e.key)){dmHilfeAuf(DMA.hilfe+(e.key==='ArrowRight'?1:-1));dmFenDraw(dmFenMode(hf));return}   // the guide pages with the arrow keys
  if(e.key!=='Escape')return;if(hf){dmFenZu(dmFenMode(hf),'hilfe');return}
  for(const m of ['g','p']){const W=DMW[m];if((W.w||W.ding)&&document.querySelector(m==='g'?'#dgcard .dm-fen':'#dmview .dm-fen')){dmFenZu(m,W.ding?'ding':'w');return}}
  const k=document.querySelector('.dmk.gross');if(k){DMK.gross=false;k.classList.remove('gross')}});
// a tap on a value, life, level, armour class or a worn thing explains it right below (Dominik 2026-10-23 „bei klicken
// auf werte etc. soll erklärt werden was das ist und wofür“); one open per table, a second tap closes it
const DMERK={p:'',g:''};
function dmErkFix(){return {leben:t('Leben: sinkt durch Treffer und Fallen, je höher die Rüstungsklasse, desto seltener trifft dich etwas. Heiltränke, Heilzauber, eine neue Stufe und die Rast vor jedem Tisch füllen es wieder auf. Bei 0 liegst du am Boden: 3 erzählte Züge ohne Heilung, dann ist dein Held gefallen (am Kindertisch nur ohnmächtig bis zum nächsten Kapitel).','Life: drops with hits and traps, the higher your armour class, the less often something hits you. Healing potions, healing spells, a new level and the rest before every table fill it up again. At 0 you are down: 3 told turns without healing and your hero has fallen (at the children\'s table only unconscious until the next chapter).'),
  stufe:t('Stufe: wächst mit Erfahrung (EP) für gelungene Proben, besiegte Gegner und erreichte Ziele. Die EP sammeln sich am Tisch und zählen am Ende der Runde oder des Kapitels; wer vorher geht, nimmt sie nicht mit. Jede neue Stufe bringt mehr Leben und einen Punkt für einen Wert.','Level: grows with experience (XP) for checks passed, foes beaten and goals reached. The XP gather at the table and count at the end of the round or chapter; whoever leaves before takes none along. Every new level brings more life and a point for a value.'),
  rk:t('Rüstungsklasse (RK): 10 + doppelt die Rüstung am Körper + Helm, Schild, Handschuhe und Stiefel + dein Geschick-Bonus (in mittlerer Rüstung höchstens +2, in schwerer keiner). Ein Gegner trifft nur, wenn sein W20 mit seinem Angriff mindestens deine RK erreicht.','Armour class (AC): 10 + twice the body armour + helmet, shield, gloves and boots + your Dexterity bonus (at most +2 in medium armour, none in heavy). A foe hits only when its d20 plus its attack reaches at least your AC.'),
  gold:t('Gold: zum Kaufen beim Händler und zum Tauschen. Ein hoher Charisma-Bonus gibt Rabatt.','Gold: for buying from the merchant and for trading. A high Charisma bonus gives a discount.')}}
function dmErkWert(x,bonus){return `<b>${esc(x.name)} ${x.wert}</b> · ${esc(x.info||'')} <small class="mut">${esc(t('Bei jeder Probe kommt ','On every check '))}${dmBo(bonus)}${dmFx(t(' zum Würfel (W20) dazu, mit Ausrüstung und Segen.',' is added to the d20, with equipment and blessings.'))}</small>`}
function dmErkBtn(mode,key,inner,label){const on=DMERK[mode]===key;return `<button type="button" class="dm-erkb${on?' on':''}" data-dmerk="${esc(key)}" aria-expanded="${on}" aria-label="${esc(label)}">${inner}</button>`}
function dmErkBox(mode,prefix,map){const k=DMERK[mode];return k&&k.startsWith(prefix)&&map[k.slice(prefix.length)]?`<div class="dm-erk" role="note">${map[k.slice(prefix.length)]}</div>`:''}
// what a seat card can explain: the six values, armour class, life and level (a worn thing opens its window)
function dmErkSeat(p){const f=dmErkFix(),m={leben:esc(f.leben),stufe:esc(f.stufe),rk:esc(f.rk)};
  if(p.karte)p.karte.werte.forEach(x=>{m['w:'+x.kurz]=dmErkWert(x,x.mod)});
  return m}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmerk],#dgcard [data-dmerk]');if(!b)return;
  const mode=b.closest('#dgcard')?'g':'p',k=b.dataset.dmerk;DMERK[mode]=DMERK[mode]===k?'':k;mode==='g'?dgDraw():dmDraw()});
// a tool that helped a check, or broke on a natural 1
// advantage or disadvantage: both dice and which one counts, so a 14 next to a 9 is never a riddle (Dominik 2026-10-24)
function dmVt(e){const ws=e.ws||[];return (e.vt&&ws.length===2?`<small class="pill ${e.vt==='vorteil'?'ok':'warn'}">${esc(e.vt==='vorteil'?t('Vorteil','Advantage'):t('Nachteil','Disadvantage'))}: ${ws[0]} ${esc(t('und','and'))} ${ws[1]}, ${esc(t('es zählt die','counts:'))} ${e.w}</small> `:'')+(e.belastet?`<small class="pill warn">${esc(t('belastet','burdened'))}</small> `:'')}
function dmTool(e){return e.werkzeug?`<small class="pill ${e.kaputt?'warn':'ok'}">🔧 ${esc(e.werkzeug)}${e.werkzeug_plus?' +'+e.werkzeug_plus:''} ${esc(e.kaputt?t('zerbrochen','broke'):t('hilft','helps'))}</small> `:''}
