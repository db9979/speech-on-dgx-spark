// KI-Dungeon-Master: big windows over the table (5k). The side column keeps a short card of the own hero with
// buttons; the hero sheet, the merchant and a single item open as a window in the table's look. The window is
// drawn with the table on every repaint (dmTable), so it always shows the panel's current state; ✕, Esc or a tap
// beside it closes it, a new turn shows a line „zum Tisch“. Only the view lives here, every action is the
// table's own (data-dmhero, data-dmtx), the panel checks it as before.
const DMW={p:{w:'',ding:'',zug:0},g:{w:'',ding:'',zug:0}};
function dmMeKurz(v,mode){const h=v.ich;if(!h)return '';const open=v.status!=='ende',m=v.markt&&open,mir=(v.angebote||[]).filter(o=>o.mir).length,boden=open?(v.boden||[]).length:0;
  return `<div class="dm-me dm-mek"><div class="dm-mek-k">${h.bild?`<span class="dm-mek-b">${dmImg(mode,v,'p',v.pid,h.stufe)}</span>`:''}<div><h4>${esc(h.name)}</h4><small class="mut">${esc(h.volk)} ${esc(h.klasse)} · ${esc(t('Stufe','Level'))} ${h.stufe}</small></div></div>
    <div class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${h.leben}/${h.leben_max}</span></div>${dmBar(h.leben,h.leben_max,h.leben*3<h.leben_max?'low':'')}
    <div class="dm-line"><span>${esc(t('Gold','Gold'))} <b>${h.gold}</b></span><span>${esc(t('Tasche','Bag'))} ${h.tasche.length}/${h.tasche_max}</span></div>
    ${h.punkte||h.wahl.length?`<div class="dm-hint">${esc(t('Neue Stufe: im Heldenbogen verteilen.','New level: spend it in the hero sheet.'))}</div>`:''}
    ${mir?`<div class="dm-hint">${esc(mir===1?t('Ein Tauschangebot wartet.','A trade offer is waiting.'):t(mir+' Tauschangebote warten.',mir+' trade offers are waiting.'))}</div>`:''}
    ${boden?`<small class="mut">${esc(boden===1?t('Hier liegt 1 Ding.','1 thing lies here.'):t('Hier liegen '+boden+' Dinge.',boden+' things lie here.'))}</small>`:''}
    <div class="dm-fknoepfe"><button type="button" class="b p" data-dmfen="bogen">📜 ${esc(t('Heldenbogen','Hero sheet'))}</button>${m?`<button type="button" class="b" data-dmfen="haendler">⚖ ${esc(t('Händler','Merchant'))}</button>`:''}${v.karte?`<button type="button" class="b" data-dmfen="karte">🗺 ${esc(t('Karte','Map'))}</button>`:''}</div></div>`}
// the merchant as big cards: picture in the rarity's frame, lines, price; below what the own bag can sell or have named
function dmShop(v){const h=v.ich,m=v.markt;
  const ware=m.ware.map(it=>`<div class="dm-ware ${DMSEL[it.selten]||''}" data-dmi="${esc(it.i)}"><span class="dm-ware-b">${dmDing(it)}</span><b>${esc(it.name)}</b><small>${esc(it.selten_name)}${it.kg?' · '+String(it.kg).replace('.',L==='en'?'.':',')+' kg':''}</small>${it.satz?`<small class="dm-isatz">„${esc(it.satz)}“</small>`:''}${it.info?`<small class="dm-iinfo">${esc(it.info)}</small>`:''}<small>${it.zeilen.map(esc).join(' · ')}</small>
    <button type="button" class="b p" data-dmhero="kaufen" data-i="${esc(it.i)}"${h.gold<it.preis?' disabled':''}>${esc(t('Kaufen','Buy'))} · ${it.preis} ${esc(t('Gold','gold'))}</button></div>`).join('');
  const mine=h.tasche.filter(it=>m.verkauf[it.i]||m.erkennen[it.i]).map(it=>dmItem(it,`<div class="dm-iacts">${m.verkauf[it.i]?`<button type="button" class="b" data-dmhero="verkaufen" data-i="${esc(it.i)}">${esc(t('Verkaufen','Sell'))} · ${m.verkauf[it.i]} ${esc(t('Gold','gold'))}</button>`:''}${m.erkennen[it.i]?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}"${h.gold<m.erkennen[it.i]?' disabled':''}>${esc(t('Erkennen lassen','Have it named'))} · ${m.erkennen[it.i]} ${esc(t('Gold','gold'))}</button>`:''}</div>`)).join('');
  return `${m.satz?`<p class="dm-isatz">„${esc(m.satz)}“</p>`:''}<small class="mut">${esc(t('Preise legt das Panel fest.','The panel sets the prices.'))}${m.rabatt?' '+esc(t('Dein Charisma: '+m.rabatt+' % Rabatt.','Your Charisma: '+m.rabatt+' % off.')):''} · ${esc(t('Dein Gold','Your gold'))}: <b>${h.gold}</b></small>
    <div class="dm-waren">${ware||`<small class="mut">${esc(t('Ausverkauft.','Sold out.'))}</small>`}</div>
    ${mine?`<h5>${esc(t('Aus deiner Tasche','From your bag'))}</h5><div class="dm-bag dm-bag-k">${mine}</div>`:''}`}
// one item by its key: bag, equipment slot („an:<slot>“), merchant or ground
function dmFind(v,key){const h=v.ich;if(!h||!key)return null;
  if(key.startsWith('an:')){const k=key.slice(3),it=h.an[k];return it?{it,wo:'an',k}:null}
  const a=[['tasche',h.tasche],['ware',v.markt&&v.status!=='ende'?v.markt.ware:[]],['boden',v.status!=='ende'?v.boden||[]:[]]];
  for(const [wo,l] of a){const it=(l||[]).find(x=>x.i===key);if(it)return {it,wo}}return null}
function dmDetail(v,f){const it=f.it,h=v.ich,open=v.status!=='ende',kg=it.kg?String(it.kg).replace('.',L==='en'?'.':',')+' kg':'';
  const acts=!open?'':f.wo==='tasche'?dmActs(v,it):f.wo==='an'?`<div class="dm-iacts"><button type="button" class="b" data-dmhero="ablegen" data-platz="${esc(f.k)}">${esc(t('Ablegen','Unequip'))}</button></div>`
    :f.wo==='ware'?`<div class="dm-iacts"><button type="button" class="b p" data-dmhero="kaufen" data-i="${esc(it.i)}"${h.gold<it.preis?' disabled':''}>${esc(t('Kaufen','Buy'))} · ${it.preis} ${esc(t('Gold','gold'))}</button></div>`
    :`<div class="dm-iacts"><button type="button" class="b" data-dmhero="aufheben" data-i="${esc(it.i)}">${esc(t('Aufheben','Pick up'))}</button></div>`;
  const wo={tasche:t('In deiner Tasche','In your bag'),an:t('Angelegt','Equipped'),ware:t('Beim Händler','At the merchant'),boden:t('Liegt hier','Lying here')}[f.wo];
  return `<div class="dm-detail ${DMSEL[it.selten]||''}"><span class="dm-detail-b">${dmDing(it)}</span><div class="dm-detail-t"><small class="mut">${esc(wo)}</small>
    <div><b class="dm-detail-n">${esc(it.name)}</b>${it.n>1?` <span class="pill">×${it.n}</span>`:''}</div><small>${esc(it.selten_name||'')}${kg?' · '+kg:''}</small>
    ${it.satz?`<p class="dm-isatz">„${esc(it.satz)}“</p>`:''}${it.info?`<p class="dm-iinfo">${esc(it.info)}</p>`:''}${(it.zeilen||[]).length?`<ul class="dm-detail-w">${it.zeilen.map(z=>`<li>${esc(z)}</li>`).join('')}</ul>`:''}
    ${it.u?`<small class="mut">${esc(t('Noch nicht erkannt: was es kann, zeigt sich erst, wenn es jemand erkennt.','Not yet identified: what it does shows only once someone identifies it.'))}</small>`:''}${acts}</div></div>`}
const DMFENK={bogen:'dm-fen dm-fen-bogen',haendler:'dm-fen dm-fen-haendler',ding:'dm-fen dm-fen-ding'};
function dmFenBox(kind,title,body,neu){return `<div class="${DMFENK[kind]}" data-dmfenbg="${kind==='ding'?'ding':'w'}"><div class="dm-fen-box" role="dialog" aria-modal="true" aria-label="${esc(title)}">
  <div class="dm-fen-kopf"><h3>${esc(title)}</h3><button type="button" class="ic-ib" data-dmfenzu="${kind==='ding'?'ding':'w'}" title="${esc(t('Schließen','Close'))}" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>${neu||''}<div class="dm-fen-body">${body}</div></div></div>`}
function dmFenster(v,mode){const W=DMW[mode],h=v.ich;if(!h){W.w=W.ding='';return ''}
  if(W.w==='haendler'&&!(v.markt&&v.status!=='ende'))W.w='';
  const f=dmFind(v,W.ding);if(!f)W.ding='';if(!W.w&&!W.ding)return '';
  const neu=W.zug&&v.zug>W.zug?`<div class="dm-fen-neu" role="status">${esc(t('Neuer Zug '+v.zug+': der Dungeon-Master hat weitererzählt.','New turn '+v.zug+': the Dungeon Master has told on.'))}<button type="button" class="b" data-dmfenzu="alle">${esc(t('Zum Tisch','To the table'))}</button></div>`:'';
  const main=W.w==='bogen'?dmFenBox('bogen','📜 '+h.name,dmMe(v,mode),neu):W.w==='haendler'?dmFenBox('haendler','⚖ '+v.markt.name,dmShop(v),neu):'';
  return main+(f?dmFenBox('ding',f.it.name,dmDetail(v,f),main?'':neu):'')}
// the window's own scroll stays across the table's repaints
function dmFenKeep(w){const s=[...w.querySelectorAll('.dm-fen-body')].map(x=>[x.closest('.dm-fen').className,x.scrollTop]);
  return ()=>s.forEach(([c,y])=>{const b=w.querySelector(`.dm-fen[class="${c}"] .dm-fen-body`);if(b)b.scrollTop=y})}
const dmFenMode=el=>el.closest('#dgcard')?'g':'p';
const dmFenDraw=mode=>mode==='g'?dgDraw():dmDraw();
const dmFenV=mode=>mode==='g'?DG.v:DM.v;
function dmFenZu(mode,was){const W=DMW[mode];if(was==='ding'&&W.ding)W.ding='';else{W.w='';W.ding=''}if(!W.w&&!W.ding)W.zug=0;dmFenDraw(mode)}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmfen],#dgcard [data-dmfen],#dmview [data-dmfenzu],#dgcard [data-dmfenzu]');
  const mode=b?dmFenMode(b):'';
  if(b&&b.dataset.dmfen){const W=DMW[mode],v=dmFenV(mode);
    if(b.dataset.dmfen==='karte'){DMK.gross=true;dmFenDraw(mode);return}
    W.w=b.dataset.dmfen;W.ding='';W.zug=v?v.zug:0;dmFenDraw(mode);return}
  if(b){dmFenZu(mode,b.dataset.dmfenzu);return}
  const bg=e.target.closest('.dm-fen');if(bg&&e.target===bg){dmFenZu(dmFenMode(bg),bg.dataset.dmfenbg);return}
  // a tap on an item (not on its buttons) opens its window: bag, equipment, merchant, ground
  const it=e.target.closest('#dmview [data-dmi],#dgcard [data-dmi],#dmview .dm-pl.voll,#dgcard .dm-pl.voll');
  if(!it||e.target.closest('button,select,input,label,a,textarea'))return;const m=dmFenMode(it),v=dmFenV(m),key=it.dataset.dmi||'an:'+it.dataset.dmslot;
  if(!v||!dmFind(v,key))return;const W=DMW[m];W.ding=key;if(!W.zug)W.zug=v.zug;dmFenDraw(m)});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;
  for(const m of ['g','p']){const W=DMW[m];if((W.w||W.ding)&&document.querySelector(m==='g'?'#dgcard .dm-fen':'#dmview .dm-fen')){dmFenZu(m,W.ding?'ding':'w');return}}
  const k=document.querySelector('.dmk.gross');if(k){DMK.gross=false;k.classList.remove('gross')}});
// a tap on a value, life, level, protection or a worn thing explains it right below (Dominik 2026-10-23 „bei klicken
// auf werte etc. soll erklärt werden was das ist und wofür“); one open per table, a second tap closes it
const DMERK={p:'',g:''};
function dmErkFix(){return {leben:t('Leben: sinkt durch Treffer und Fallen, Schutz mindert jeden Treffer. Heiltränke, Heilzauber und eine neue Stufe füllen es wieder auf.','Life: drops with hits and traps, protection softens every hit. Healing potions, healing spells and a new level fill it up again.'),
  stufe:t('Stufe: wächst mit Erfahrung (EP) für gelungene Proben, besiegte Gegner und erreichte Ziele. Jede neue Stufe bringt mehr Leben und einen Punkt für einen Wert.','Level: grows with experience (XP) for checks passed, foes beaten and goals reached. Every new level brings more life and a point for a value.'),
  schutz:t('Schutz: alles, was du an Rüstung, Helm, Schild, Handschuhen und Stiefeln trägst. Jeder Treffer kostet so viel weniger Leben, mindestens 1.','Protection: all the armour, helmet, shield, gloves and boots you wear. Every hit costs that much less life, at least 1.'),
  gold:t('Gold: zum Kaufen beim Händler und zum Tauschen. Ein hoher Charisma-Bonus gibt Rabatt.','Gold: for buying from the merchant and for trading. A high Charisma bonus gives a discount.')}}
function dmErkWert(x,bonus){return `<b>${esc(x.name)} ${x.wert}</b> · ${esc(x.info||'')} <small class="mut">${esc(t('Bei jeder Probe kommt ','On every check ')+dmSign(bonus)+t(' zum Würfel (W20) dazu, mit Ausrüstung und Segen.',' is added to the d20, with equipment and blessings.'))}</small>`}
function dmErkBtn(mode,key,inner,label){const on=DMERK[mode]===key;return `<button type="button" class="dm-erkb${on?' on':''}" data-dmerk="${esc(key)}" aria-expanded="${on}" aria-label="${esc(label)}">${inner}</button>`}
function dmErkBox(mode,prefix,map){const k=DMERK[mode];return k&&k.startsWith(prefix)&&map[k.slice(prefix.length)]?`<div class="dm-erk" role="note">${map[k.slice(prefix.length)]}</div>`:''}
// what a seat card can explain: the six values, protection, life, level and every worn thing
function dmErkSeat(p){const f=dmErkFix(),m={leben:esc(f.leben),stufe:esc(f.stufe),schutz:esc(f.schutz)};
  if(p.karte){p.karte.werte.forEach(x=>{m['w:'+x.kurz]=dmErkWert(x,x.mod)});p.karte.dinge.forEach((d,i)=>{m['d:'+i]=`<b>${esc(d.name)}</b> · ${esc(d.info||'')}${d.zeilen.length?` <small class="mut">${d.zeilen.map(esc).join(' · ')}</small>`:''}`})}
  return m}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmerk],#dgcard [data-dmerk]');if(!b)return;
  const mode=b.closest('#dgcard')?'g':'p',k=b.dataset.dmerk;DMERK[mode]=DMERK[mode]===k?'':k;mode==='g'?dgDraw():dmDraw()});
// a tool that helped a check, or broke on a natural 1
function dmTool(e){return e.werkzeug?`<small class="pill ${e.kaputt?'warn':'ok'}">🔧 ${esc(e.werkzeug)} ${esc(e.kaputt?t('zerbrochen','broke'):t('hilft','helps'))}</small> `:''}
