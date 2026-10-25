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
    <div class="dm-fknoepfe"><button type="button" class="b p" data-dmfen="bogen">📜 ${esc(t('Heldenbogen','Hero sheet'))}</button>${m?`<button type="button" class="b" data-dmfen="haendler">⚖ ${esc(t('Händler','Merchant'))}</button>`:''}${v.siedlung?`<button type="button" class="b" data-dmfen="siedlung">🏘 ${esc(t('Siedlung','Settlement'))}</button>`:''}${v.nsc?`<button type="button" class="b" data-dmfen="leute">👥 ${esc(t('Leute und Chronik','People and chronicle'))}</button>`:''}${v.fraktionen&&(v.fraktionen.uhren.length||v.fraktionen_geheim)?`<button type="button" class="b" data-dmfen="fraktionen">⏳ ${esc(t('Fraktionen','Factions'))}</button>`:''}${v.grenzen?`<button type="button" class="b" data-dmfen="grenzen">🛡 ${esc(t('Grenzen','Lines'))}</button>${dmXKnopf(v)}`:''}</div></div>`}
// Grenzen, Schleier und X-Karte (Tabletop-Punkt 18): the seat's own two lists, the table's together without names, the
// X-Karte one tap without a question (the panel checks everything by fixed word lists, dungeon_grenzen.py)
const dmXKnopf=v=>{const x=v.grenzen&&v.grenzen.x,l=t('Die letzte Szene war zu viel: sie wird ruhiger neu erzählt. Niemand sieht, wer sie gelegt hat.','The last scene was too much: it is told again more calmly. Nobody sees who laid it.');
  return `<button type="button" class="b dm-xkarte" data-dmx="1" title="${esc(l)}"${x&&x.laeuft?' disabled':''}>${esc(x&&x.laeuft?'✖ '+t('Wird neu erzählt …','Being told again …'):'✖ '+t('X-Karte','X-card'))}</button>`};
function dmGrenzen(v){const g=v.grenzen,T=g.tisch,chips=l=>l.length?l.map(w=>`<span class="pill">${esc(w)}</span>`).join(' '):`<small class="mut">${esc(t('noch nichts','nothing yet'))}</small>`;
  const feld=(k,l,sub)=>`<label class="dm-grenze"><b>${esc(l)}</b><small class="mut">${esc(sub)}</small><input data-dmgfeld="${k}" maxlength="${(g.laenge+2)*g.max}" value="${esc((g.meine[k]||[]).join(', '))}" placeholder="${esc(t('mit Komma getrennt','separated by commas'))}"></label>`;
  return `<p class="mut">${esc(t('Was du hier einträgst, gilt für den ganzen Tisch. Die anderen sehen die Wörter, nie, von wem sie sind. Bis zu '+g.max+' je Liste.','What you enter here counts for the whole table. The others see the words, never whose they are. Up to '+g.max+' per list.'))}</p>
    ${feld('linien',t('Grenzen: kommt nie vor','Lines: never appears'),t('Eine Aktion damit geht nicht, eine Erzählung damit wird neu erzählt.','An action with it does not work, a narration with it is told again.'))}
    ${feld('schleier',t('Schleier: nur angedeutet','Veils: only hinted at'),t('Darf geschehen, aber die Szene blendet ab.','May happen, but the scene fades out.'))}
    <div class="dm-hostb"><button type="button" class="b p" data-dmgrenzen="1">${esc(t('Für mich speichern','Save for me'))}</button></div>
    <h5>${esc(t('Am Tisch gilt','At the table'))}</h5><div class="dm-line"><span>${esc(t('Nie','Never'))}</span><span>${chips(T.linien)}</span></div><div class="dm-line"><span>${esc(t('Nur angedeutet','Only hinted'))}</span><span>${chips(T.schleier)}</span></div>
    <h5>✖ ${esc(t('X-Karte','X-card'))}</h5><p class="mut">${esc(t('Ein Tipp genügt, ohne Begründung: die letzte Szene wird ruhiger neu erzählt, ihre Bilder und das Vorlesen fallen weg, und die Geschichte führt davon weg. Niemand sieht, wer sie gelegt hat.','One tap is enough, without a reason: the last scene is told again more calmly, its pictures and the reading go, and the story leads away from it. Nobody sees who laid it.'))}</p>${dmXKnopf(v)}`}
// NSC-Gedächtnis, Chronik und Ruf (Tabletop-Punkt 5): the people met with their card and attitude to each hero, the
// heroes' reputation and the chronicle by chapter; the host also sees wish, secret and relations (nsc_geheim)
function dmLeute(v){const N=v.nsc,G=v.nsc_geheim||{},chip=h=>`<span class="dm-haltung" data-h="${h[2]}">${esc(h[0])}: ${esc(h[1])}</span>`,
    zeile=(a,b)=>b?`<div class="dm-line"><span>${esc(a)}</span><span>${esc(b)}</span></div>`:'';
  const leute=N.leute.length?N.leute.map(p=>{const g=G[p.name];return `<div class="dm-nsc"><b>${esc(p.name)}</b>${p.beruf?` <small class="mut">${esc(p.beruf)}</small>`:''}
    ${zeile(t('Aussehen','Looks'),p.aussehen)}${zeile(t('Art','Manner'),p.art)}<div>${p.haltung.length?p.haltung.map(chip).join(' '):`<small class="mut">${esc(t('kennt euch noch kaum','hardly knows you yet'))}</small>`}</div>
    ${g?`<div class="dm-geheim"><small class="mut">🔒 ${esc(t('nur du als Gastgeber','only you as host'))}</small>${zeile(t('Wunsch','Wish'),g.wunsch)}${zeile(t('Geheimnis','Secret'),g.geheimnis)}${zeile(t('Beziehungen','Relations'),g.kanten.join(', '))}${zeile(t('Wesen','Traits'),(g.wesen||[]).join(', '))}${(g.ziele||[]).map(z=>`<div class="dm-line"><span>${esc(z[0])}</span><span>${esc(z[1])} <small class="dm-ziel" title="${z[2]}/${z[3]}">${'▰'.repeat(Math.min(z[2],z[3]))+'▱'.repeat(Math.max(0,z[3]-z[2]))}</small></span></div>`).join('')}</div>`:''}</div>`}).join('')
    :`<p class="mut">${esc(t('Ihr habt noch niemanden getroffen.','You have not met anyone yet.'))}</p>`;
  const fern=Object.entries(G).filter(([,g])=>!g.gesehen).map(([n])=>n);
  const ruf=N.ruf.length?`<h5>${esc(t('Ruf','Reputation'))}</h5>`+N.ruf.map(([h,w])=>zeile(h,w)).join(''):'';
  let k=0;const chronik=N.chronik.length?N.chronik.map(c=>(c.k!==k?(k=c.k,`<h6>${esc(t('Kapitel ','Chapter '))}${c.k}</h6>`):'')+`<div class="dm-sys">📖 ${esc(c.t)}</div>`).join(''):`<p class="mut">${esc(t('Noch steht nichts in der Chronik.','Nothing in the chronicle yet.'))}</p>`;
  return `<h5>${esc(t('Leute','People'))}</h5>${leute}${fern.length?`<p class="mut">🔒 ${esc(t('Noch nicht getroffen: ','Not met yet: ')+fern.join(', '))}</p>`:''}${ruf}<h5>${esc(t('Chronik','Chronicle'))}</h5>${chronik}`}
// Fraktionen mit Uhren (Tabletop-Punkt 7): a clock per faction the table knows (a ring of fields); the host sees every
// faction with what it wants and changes it here (data-dmfrak, dungeon_fraktionen.host checks it)
function dmFrakRing(s,n,voll){const r=15,c=18,seg=[...Array(n)].map((_,i)=>{const a=i/n*2*Math.PI-Math.PI/2,b=(i+1)/n*2*Math.PI-Math.PI/2,
    p=(x,y)=>`${(c+r*Math.cos(x)).toFixed(2)} ${(c+r*Math.sin(x)).toFixed(2)}`;
    return `<path d="M${c} ${c}L${p(a)}A${r} ${r} 0 0 1 ${p(b)}Z" class="${i<s?'an':''}"/>`}).join('');
  return `<svg class="dm-uhr${voll?' voll':''}" viewBox="0 0 36 36" width="36" height="36" role="img" aria-label="${esc(t(s+' von '+n+' Feldern',s+' of '+n+' fields'))}">${seg}</svg>`}
function dmFraktionen(v){const F=v.fraktionen,G=v.fraktionen_geheim,D=DMA.frak||{name:'',will:'',felder:6};
  const offen=F.uhren.length?F.uhren.map(u=>`<div class="dm-frak">${dmFrakRing(u.stand,u.felder,u.voll)}<div><b>${esc(u.name)}</b><small class="mut">${u.voll?esc(t('am Ziel','at their goal')):u.stand+' / '+u.felder}</small></div></div>`).join('')
    :`<p class="mut">${esc(t('Noch kennt ihr keine Gruppe mit eigenen Zielen.','You do not know any group with goals of its own yet.'))}</p>`;
  if(!G)return `<p class="mut">${esc(t('Jede Gruppe verfolgt ihr Ziel, auch ohne euch. Ist eine Uhr voll, ändert sich die Welt.','Every group pursues its goal, also without you. When a clock is full, the world changes.'))}</p>${offen}`;
  const opt=cur=>G.felder.map(n=>`<option value="${n}"${n===cur?' selected':''}>${n} ${esc(t('Felder','fields'))}</option>`).join('');
  const alle=G.alle.map(x=>`<div class="dm-frak dm-frakh" data-dmfrakn="${esc(x.name)}">${dmFrakRing(x.stand,x.felder,x.voll)}<div class="dm-frakt"><b>${esc(x.name)}</b>${x.eigen?' <small class="mut">✎</small>':''}${x.bekannt?'':` <small class="mut">🔒 ${esc(t('noch unbekannt','not known yet'))}</small>`}
    <input data-dmfrakw maxlength="${G.will_max}" value="${esc(x.will)}" placeholder="${esc(t('Was sie wollen','What they want'))}" aria-label="${esc(t('Was '+x.name+' will','What '+x.name+' wants'))}">
    <div class="dm-hostb"><button type="button" class="b" data-dmfrak="-1" aria-label="${esc(t('Ein Feld zurück','One field back'))}">−</button><span>${x.stand} / ${x.felder}</span><button type="button" class="b" data-dmfrak="1" aria-label="${esc(t('Ein Feld vor','One field on'))}">+</button>
    <select data-dmfrakf aria-label="${esc(t('Felder','Fields'))}">${opt(x.felder)}</select><button type="button" class="b" data-dmfrak="w">${esc(t('Ziel speichern','Save goal'))}</button><button type="button" class="b danger" data-dmfrak="weg">${esc(t('Entfernen','Remove'))}</button></div></div></div>`).join('');
  const neu=G.alle.length<G.max?`<h5>${esc(t('Eigene Gruppe','Own group'))}</h5><div class="dm-frakneu"><input data-dmfrakneu="name" maxlength="${G.name_max}" value="${esc(D.name)}" placeholder="${esc(t('Name, z. B. Die Rabengilde','Name, e.g. The Raven Guild'))}" aria-label="${esc(t('Name','Name'))}">
    <input data-dmfrakneu="will" maxlength="${G.will_max}" value="${esc(D.will)}" placeholder="${esc(t('Was sie wollen','What they want'))}" aria-label="${esc(t('Was sie wollen','What they want'))}">
    <div class="dm-hostb"><select data-dmfrakneu="felder" aria-label="${esc(t('Felder','Fields'))}">${opt(D.felder)}</select><button type="button" class="b p" data-dmfrak="neu">${esc(t('Anlegen','Add'))}</button></div></div>`:'';
  return `<p class="mut">${esc(t('Nur du als Gastgeber siehst die Ziele und die Gruppen, die die Erzählung noch nicht genannt hat. Das Panel dreht die Uhren zwischen den Zügen; die Erzählung meldet, wenn die Helden helfen oder stören.','Only you as host see the goals and the groups the narration has not named yet. The panel turns the clocks between turns; the narration reports when the heroes help or hinder.'))}</p>
    <h5>${esc(t('Was die Spieler sehen','What the players see'))}</h5>${offen}<h5>${esc(t('Alle Gruppen','All groups'))}</h5>${alle||`<p class="mut">${esc(t('Die Geschichte hat noch keine Gruppen.','The story has no groups yet.'))}</p>`}${neu}`}
document.body.addEventListener('input',e=>{const b=e.target.closest('#dmview [data-dmfrakneu]');if(!b)return;const box=b.closest('.dm-frakneu');
  DMA.frak={name:box.querySelector('[data-dmfrakneu=name]').value,will:box.querySelector('[data-dmfrakneu=will]').value,felder:+box.querySelector('[data-dmfrakneu=felder]').value}});
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmfrakf]');if(!s||!DM.rid)return;const name=s.closest('[data-dmfrakn]').dataset.dmfrakn;
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/fraktion`,{name,felder:+s.value},DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmfrak]');if(!b||!DM.rid)return;const k=b.dataset.dmfrak;let body;
  if(k==='neu'){const D=DMA.frak||{};if(!(D.name||'').trim())return;body={name:D.name.trim(),will:(D.will||'').trim(),felder:D.felder||6}}
  else{const row=b.closest('[data-dmfrakn]'),name=row.dataset.dmfrakn;
    body=k==='weg'?{name,weg:true}:k==='w'?{name,will:row.querySelector('[data-dmfrakw]').value.trim()}:{name,schritt:+k}}
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/fraktion`,body,DM);if(d){DM.v=d;DM.at=Date.now();if(k==='neu')DMA.frak=null}dmDraw()});
// Gold mit Zweck (Idee 9): the settlement's fixed offers, priced by the panel; every button is the hero's own move (data-dmhero)
const DMDIENST={gasthaus:'🛏',schmied:'🔨',lehre:'📖',geruecht:'🗣',verbessern:'⚒'};
// Siedlung mit Leben (Dominik 2026-10-25 „so umsetzten“, 1a 2a 3a 4a 5b): a head with the place's picture, time of day and
// purse; a card per service with its picture on top and a line of life; the price's calculation small above a verb
// button; what the hero cannot pay is grey with how much is missing; the lesson as six values before → after
const DMVERB={gasthaus:['Übernachten','Stay the night'],schmied:['Flicken','Mend'],lehre:['Lernen','Learn'],geruecht:['Zuhören','Listen'],verbessern:['Verbessern','Improve']};
const DMZEIT={morgen:['🌅','Morgen','Morning'],tag:['☀️','Tag','Day'],abend:['🌇','Abend','Evening'],nacht:['🌙','Nacht','Night']};
const dmPlus=n=>(n>=0?'+':'')+n;
function dmSiedlung(v){const s=v.siedlung,G=t('Gold','gold'),fehlt=p=>Math.max(0,p-s.gold),
    knopf=(d,attr,label,preis)=>{const p=preis==null?d.preis:preis,f=d.frei?fehlt(p):0;
      return `<button type="button" class="b p" data-dmhero="dienst" data-id="${d.id}"${attr||''}${!d.frei||f?' disabled':''}>${esc(label||t(...DMVERB[d.id]))} · ${p} ${esc(G)}</button>${f?`<small class="dm-fehlt">${esc(t(`Es fehlen ${f} Gold`,`${f} gold short`))}</small>`:''}`},
    rech=d=>d.je?`<small class="mut dm-rech">${d.je} × ${esc(t('Stufe','level'))} ${s.stufe}${d.id==='gasthaus'?` × ${s.helden} ${esc(t('Helden','heroes'))}`:''} = ${d.preis} ${esc(G)}</small>`:'',
    werte=(v.ich&&v.ich.werte)||[],
    lehre=d=>{const f=fehlt(d.preis);return `<small class="mut">${esc(t('Lernen: tippe auf einen Wert.','Learn: tap a value.'))}</small><div class="dm-lehre">${werte.map(w=>{const an=s.lehre===w.id;
      return `<button type="button" class="b dm-lwert${an?' an':''}" data-dmhero="dienst" data-id="lehre" data-wert="${esc(w.id)}" title="${esc(w.name)}"${an||f?' disabled':''}><b>${esc(w.kurz)}</b><span>${an?esc(t('gelernt','learned')):dmPlus(w.gesamt)+' → '+dmPlus(w.gesamt+1)}</span></button>`}).join('')}</div>${rech(d)}${f?`<small class="dm-fehlt">${esc(t(`Es fehlen ${f} Gold`,`${f} gold short`))}</small>`:''}`},
    card=d=>`<div class="dm-ware dm-dienstk${d.frei?'':' dm-zu'}" data-dmdienst="${d.id}">${d.bild?`<span class="dm-dienst-bild">${dmDing({bild:d.bild},1)}</span>`:`<span class="dm-dienst-bild dm-dz" aria-hidden="true">${DMDIENST[d.id]}</span>`}<b>${esc(d.name)}</b>${d.zeile?`<small class="dm-isatz">„${esc(d.zeile)}“</small>`:''}<small>${esc(d.satz)}</small>${
    d.id==='schmied'?(s.kaputt.length?rech(d)+s.kaputt.map(it=>knopf(d,` data-i="${esc(it.i)}"`,t('Flicken: ','Mend: ')+it.name)).join(''):`<small class="mut">${esc(t('Nichts zerbrochen.','Nothing broken.'))}</small>`)
    :d.id==='verbessern'?(s.verbessern.length?s.verbessern.map(it=>knopf(Object.assign({},d,{frei:true}),` data-i="${esc(it.i)}"`,it.name+' → '+it.neu,it.preis)).join(''):`<small class="mut">${esc(t('Nichts, was der Schmied besser machen kann.','Nothing the smith can make better.'))}</small>`)
    :d.id==='lehre'?lehre(d)
    :rech(d)+knopf(d)}</div>`,
    z=DMZEIT[s.tageszeit]||DMZEIT.tag;
  return `<div class="dm-sied-kopf${s.kopf?'':' leer'}">${s.kopf?dmDing({bild:s.kopf},1):''}<div class="dm-sied-titel"><b>${esc(s.name)}</b><span>${z[0]} ${esc(t(z[1],z[2]))}</span><span>💰 ${esc(t('Dein Gold','Your gold'))}: <b>${s.gold}</b> · ${esc(t('Gruppe','Group'))}: ${s.gold_gruppe}</span></div></div>
    <small class="mut">${esc(t('Preise legt das Panel nach der Stufe der Gruppe fest. Jeder zahlt aus seinem eigenen Gold.','The panel sets the prices by the group\'s level. Everyone pays from their own gold.'))}</small><div class="dm-waren">${s.dienste.map(card).join('')}</div>`}
// the merchant as big cards: picture in the rarity's frame, lines, price; below what the own bag can sell or have named
function dmShop(v){const h=v.ich,m=v.markt;
  const ware=m.ware.map(it=>`<div class="dm-ware ${DMSEL[it.selten]||''}" data-dmi="${esc(it.i)}"><span class="dm-ware-b">${dmDing(it,1)}</span><b>${esc(it.name)}</b>${dmCmp(it)}<small>${esc(it.selten_name)}${it.kg?' · '+String(it.kg).replace('.',L==='en'?'.':',')+' kg':''}</small>${it.satz?`<small class="dm-isatz">„${esc(it.satz)}“</small>`:''}${it.info?`<small class="dm-iinfo">${esc(it.info)}</small>`:''}<small>${it.zeilen.map(esc).join(' · ')}</small>
    <button type="button" class="b p" data-dmhero="kaufen" data-i="${esc(it.i)}"${h.gold<it.preis?' disabled':''}>${esc(t('Kaufen','Buy'))} · ${it.preis} ${esc(t('Gold','gold'))}</button></div>`).join('');
  const mine=h.tasche.filter(it=>m.verkauf[it.i]||m.erkennen[it.i]).map(it=>dmItem(it,`<div class="dm-iacts">${m.verkauf[it.i]?`<button type="button" class="b" data-dmhero="verkaufen" data-i="${esc(it.i)}"${m.verkauf[it.i]>m.kasse?` disabled title="${esc(t('So viel Gold hat der Händler nicht mehr.','The merchant has no more gold for that.'))}"`:''}>${esc(t('Verkaufen','Sell'))} · ${m.verkauf[it.i]} ${esc(t('Gold','gold'))}</button>`:''}${m.erkennen[it.i]?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}"${h.gold<m.erkennen[it.i]?' disabled':''}>${esc(t('Erkennen lassen','Have it named'))} · ${m.erkennen[it.i]} ${esc(t('Gold','gold'))}</button>`:''}</div>`)).join('');
  return `${m.satz?`<p class="dm-isatz">„${esc(m.satz)}“</p>`:''}<small class="mut">${esc(t('Preise legt das Panel fest.','The panel sets the prices.'))}${m.rabatt?' '+esc(t('Dein Charisma: '+m.rabatt+' % Rabatt.','Your Charisma: '+m.rabatt+' % off.')):''} · ${esc(t('Dein Gold','Your gold'))}: <b>${h.gold}</b></small>
    ${m.art?`<small class="mut dm-hart">${esc(t(`${m.art}: zahlt für ${m.kauft.join(', ')} den halben Wert, für anderes ein Viertel`,`${m.art}: pays half the worth for ${m.kauft.join(', ')}, a quarter for anything else`))} · ${esc(t('Kasse','Purse'))}: <b>${m.kasse}</b> ${esc(t('Gold','gold'))}</small>`:''}
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
  const leben=g.max?`<div class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${g.leben} / ${g.max}</span></div>${dmBar(g.leben,g.max,g.leben*3<g.max?'low':'')}`:g.lage_name?`<div class="dm-line"><span>${esc(t('Zustand','State'))}</span><span class="dm-lage" data-lage="${esc(g.lage)}">${esc(g.lage_name)}</span></div>`:'';
  return `<div class="dm-detail dm-gdet"><span class="dm-detail-b">${dmDing(g,1)}</span><div class="dm-detail-t">${blatt}
    <div><b class="dm-detail-n">${esc(g.name)}</b>${g.anzahl>1?` <span class="pill">×${g.anzahl}</span>`:''}${g.aus?` <span class="pill">${esc(g.aus==='besiegt'?t('besiegt','defeated'):t('geflohen','fled'))}</span>`:''}</div>
    ${gr?`<small>${esc(gr)}</small>`:''}${g.info?`<p class="dm-iinfo">${esc(g.info)}</p>`:''}${leben}
    ${g.rk!=null?`<div class="dm-pchips">${chip('',t('Stufe','Level'),dmCr(g.stufe))}${g.max||g.leben==null?'':chip('leben','❤',g.leben)}${chip('',t('RK','AC'),g.rk)}${chip('kraft',t('Angriff','Attack'),fx(g.angriff))}${chip('',t('Schaden','Damage'),(g.angriffe>1?g.angriffe+' × ':'')+g.schaden)}${chip('up',t('EP','XP'),g.ep)}</div>`:''}
    ${(g.werte||[]).length?`<div class="dm-gwerte">${g.werte.map(w=>`<span title="${esc(w.name)}"><small>${esc(w.kurz)}</small><b>${w.wert}</b><i>${esc(fx(w.mod))}</i></span>`).join('')}</div>`:''}
    ${g.boss?`<p class="dm-gboss">👑 ${esc(t('Boss: mehr Leben je Held, ab halbem Leben eine zweite Phase, mindestens zwei Angriffe je Zug, bessere Beute.','Boss: more life per hero, a second phase from half life, at least two attacks a turn, a better find.'))}${g.phase===2?' <b>'+esc(t('Zweite Phase!','Second phase!'))+'</b>':''}</p>`:''}
    ${g.art?`<small>${esc(t('Schaden: ','Damage: ')+g.art)}</small>`:''}${[['schwaeche','💥',t('Schwach gegen','Weak against'),'dm-gres dm-gres-schwaeche'],['resistenz','🛡',t('Widersteht','Resists'),'dm-gres'],['immun','⛔',t('Immun gegen','Immune to'),'dm-gres dm-gres-immun']].filter(([k])=>(g[k]||[]).length).map(([k,i,l,c])=>`<div class="${c}">${i} ${esc(l)}: ${esc(g[k].join(', '))}</div>`).join('')}${g.unbekannt?`<div class="dm-gres dm-gres-unb">❔ ${esc(g.unbekannt===1?t('Eine Schwäche oder ein Widerstand ist noch unbekannt: ein Treffer oder eine gelungene Intelligenz-Probe im Kampf zeigt es.','One weakness or resistance is still unknown: a hit or a passed Intelligence check in a fight shows it.'):t(g.unbekannt+' Schwächen oder Widerstände sind noch unbekannt: Treffer oder eine gelungene Intelligenz-Probe im Kampf zeigen sie.',g.unbekannt+' weaknesses or resistances are still unknown: hits or a passed Intelligence check in a fight show them.'))}</div>`:''}
    ${(g.zustaende||[]).length?`<h5>${esc(t('Kann bewirken','Can cause'))}</h5><ul class="dm-detail-w">${g.zustaende.map(z=>`<li><b>${esc(z.name)}</b>: ${esc(z.info)}</li>`).join('')}</ul>`:''}</div></div>`}
function dmDetail(v,f){const it=f.it,h=v.ich,open=v.status!=='ende',kg=it.kg?String(it.kg).replace('.',L==='en'?'.':',')+' kg':'';
  const acts=!open||f.wo==='fremd'?'':f.wo==='tasche'?dmActs(v,it):f.wo==='an'?`<div class="dm-iacts"><button type="button" class="b" data-dmhero="ablegen" data-platz="${esc(f.k)}">${esc(t('Ablegen','Unequip'))}</button></div>`
    :f.wo==='ware'?`<div class="dm-iacts"><button type="button" class="b p" data-dmhero="kaufen" data-i="${esc(it.i)}"${h.gold<it.preis?' disabled':''}>${esc(t('Kaufen','Buy'))} · ${it.preis} ${esc(t('Gold','gold'))}</button></div>`
    :f.wo==='beute'?'':`<div class="dm-iacts"><button type="button" class="b" data-dmhero="aufheben" data-i="${esc(it.i)}">${esc(t('Aufheben','Pick up'))}</button></div>`;
  const wo={tasche:t('In deiner Tasche','In your bag'),an:t('Angelegt','Equipped'),ware:t('Beim Händler','At the merchant'),boden:t('Liegt hier','Lying here'),fremd:t('Trägt '+f.wer,'Worn by '+f.wer),beute:t('Beute für '+f.wer,'Loot for '+f.wer)}[f.wo];
  return `<div class="dm-detail ${DMSEL[it.selten]||''}"><span class="dm-detail-b">${dmDing(it,1)}</span><div class="dm-detail-t"><small class="mut">${esc(wo)}</small>
    <div><b class="dm-detail-n">${esc(it.name)}</b>${dmCmp(it)}${it.n>1?` <span class="pill">×${it.n}</span>`:''}</div><small>${esc(it.selten_name||'')}${kg?' · '+kg:''}</small>
    ${it.fund?`<p class="dm-ifund">${esc(t('Gefunden in: ','Found in: ')+it.fund)}</p>`:''}${it.satz?`<p class="dm-isatz">„${esc(it.satz)}“</p>`:''}${it.info?`<p class="dm-iinfo">${esc(it.info)}</p>`:''}${(it.zeilen||[]).length?`<ul class="dm-detail-w">${it.zeilen.map(z=>`<li>${dmFx(z)}</li>`).join('')}</ul>`:''}
    ${it.u?`<small class="mut">${esc(t('Noch nicht erkannt: was es kann, zeigt sich erst, wenn es jemand erkennt.','Not yet identified: what it does shows only once someone identifies it.'))}</small>`:''}${acts}</div></div>`}
const DMFENK={bogen:'dm-fen dm-fen-bogen',haendler:'dm-fen dm-fen-haendler',siedlung:'dm-fen dm-fen-haendler',grenzen:'dm-fen dm-fen-haendler',leute:'dm-fen dm-fen-haendler',fraktionen:'dm-fen dm-fen-haendler',ding:'dm-fen dm-fen-ding'};
function dmFenBox(kind,title,body,neu){return `<div class="${DMFENK[kind]}" data-dmfenbg="${kind==='ding'?'ding':'w'}"><div class="dm-fen-box" role="dialog" aria-modal="true" aria-label="${esc(title)}">
  <div class="dm-fen-kopf"><h3>${esc(title)}</h3><button type="button" class="ic-ib" data-dmfenzu="${kind==='ding'?'ding':'w'}" title="${esc(t('Schließen','Close'))}" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>${neu||''}<div class="dm-fen-body">${body}</div></div></div>`}
function dmFenster(v,mode){DMCMP=v.vergleich||{};const W=DMW[mode],h=v.ich;if(!h){W.w=W.ding='';return ''}
  if(W.w==='haendler'&&!(v.markt&&v.status!=='ende')||W.w==='siedlung'&&!v.siedlung||W.w==='grenzen'&&!v.grenzen||W.w==='leute'&&!v.nsc||W.w==='fraktionen'&&!v.fraktionen)W.w='';
  const f=dmFind(v,W.ding);if(!f)W.ding='';if(!W.w&&!W.ding)return '';
  const neu=W.zug&&v.zug>W.zug?`<div class="dm-fen-neu" role="status">${esc(t('Neuer Zug '+v.zug+': der Dungeon-Master hat weitererzählt.','New turn '+v.zug+': the Dungeon Master has told on.'))}<button type="button" class="b" data-dmfenzu="alle">${esc(t('Zum Tisch','To the table'))}</button></div>`:'';
  // the table's last message also in the window, so an answer (a refused portrait, a full bag) is never hidden behind it
  const S=mode==='g'?DG:DM,say=`<div class="dmmsg ${S.err?'err':'mut'}" role="status">${esc(S.msg||'')}</div>`;
  const main=W.w==='bogen'?dmFenBox('bogen','📜 '+h.name,say+dmMe(v,mode),neu):W.w==='haendler'?dmFenBox('haendler','⚖ '+v.markt.name,say+dmShop(v),neu):W.w==='siedlung'?dmFenBox('siedlung','🏘 '+v.siedlung.name,dmSiedlung(v),neu):W.w==='grenzen'?dmFenBox('grenzen','🛡 '+t('Grenzen und X-Karte','Lines and X-card'),say+dmGrenzen(v),neu):W.w==='leute'?dmFenBox('leute','👥 '+t('Leute und Chronik','People and chronicle'),dmLeute(v),neu):W.w==='fraktionen'?dmFenBox('fraktionen','⏳ '+t('Fraktionen','Factions'),say+dmFraktionen(v),neu):'';
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
function dmErkFix(){return {leben:t('Leben: sinkt durch Treffer und Fallen, je höher die Rüstungsklasse, desto seltener trifft dich etwas. Heiltränke, Heilzauber, eine neue Stufe und die Rast vor jedem Tisch füllen es wieder auf. Bei 0 liegst du am Boden und das Panel würfelt jeden Zug einen Rettungswurf: drei gelungene oder eine 20 und du stehst auf, drei misslungene und dein Held ist gefallen (am Kindertisch nur ohnmächtig bis zum nächsten Kapitel, als einziger Held am Tisch rettet dich ein Fremder).','Life: drops with hits and traps, the higher your armour class, the less often something hits you. Healing potions, healing spells, a new level and the rest before every table fill it up again. At 0 you are down and the panel rolls a death save each turn: three successes or a 20 and you get up, three failures and your hero has fallen (at the children\'s table only unconscious until the next chapter, as the only hero at the table a stranger saves you).'),
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
// the two lists and the X-Karte: the own seat's call, the answer is the table's view
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmgrenzen],#dgcard [data-dmgrenzen],#dmview [data-dmx],#dgcard [data-dmx]');if(!b)return;
  const mode=dmFenMode(b),S=mode==='g'?DG:DM,box=b.closest('.dm-fen-box'),val=k=>{const i=box&&box.querySelector(`[data-dmgfeld="${k}"]`);return i?i.value:''};
  const body=b.dataset.dmx?{x:true}:{linien:val('linien'),schleier:val('schleier')};b.disabled=true;
  try{let d;if(mode==='g')d=await dgPub('/api/dungeon/grenzen',Object.assign({code:DG.code},body));else{d=await dmSend(`/api/profile/dungeon/${DM.rid}/grenzen`,body,DM);if(!d){b.disabled=false;return}}
    S.v=d;S.at=Date.now();if(b.dataset.dmx)dmLesStopp(mode);dmSay(S,b.dataset.dmx?t('Die X-Karte liegt. Die letzte Szene wird neu erzählt.','The X-card is laid. The last scene is told again.'):t('Gespeichert. Das gilt jetzt am ganzen Tisch.','Saved. It now counts at the whole table.'),false);dmFenDraw(mode)}
  catch(x){b.disabled=false;dmSay(S,dgErr(x),true);dmFenDraw(mode)}});
