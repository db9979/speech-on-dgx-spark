// KI-Dungeon-Master: the map of the round (dungeon_karte.py). The panel rolls and keeps it; this only draws what the
// seat may see: visited and known places, ways into the unknown as stubs with „?“, the vault where the group is.
// Tapping a way writes it into the own action (it stays the player's text); the host rolls the map again or a vault.
const DMK={tab:'',gross:false};
const DMK_ART={raetsel:'❓',waechter:'👹',boss:'💀',falle:'⚠',schatz:'💰',quelle:'💧',altar:'🔆',eingang:'🚪'};
function dmkDeko(k){const d=k.deko||{},P=a=>a.map(p=>p.join(',')).join(' ');
  if(d.fluss)return `<polyline points="${P(d.fluss)}" class="dmk-fluss"/>`;
  if(d.see)return `<ellipse cx="${d.see[0]}" cy="${d.see[1]}" rx="${d.see[2]}" ry="${d.see[3]}" class="dmk-wasser"/>`;
  if(d.grenze)return `<polyline points="${P(d.grenze)}" class="dmk-grenze"/>`;
  if(d.kueste)return `<polygon points="${P(d.kueste)} ${k.w},${k.h} 0,${k.h}" class="dmk-wasser"/><polyline points="${P(d.kueste)}" class="dmk-ufer"/>`;
  return ''}
function dmkWelt(k){
  const wege=k.wege.map(w=>w[4]===0?`<line x1="${w[0]}" y1="${w[1]}" x2="${w[2]}" y2="${w[3]}" class="dmk-stub"/><text x="${w[2]}" y="${w[3]+10}" class="dmk-frage">?</text>`
    :`<line x1="${w[0]}" y1="${w[1]}" x2="${w[2]}" y2="${w[3]}" class="${w[4]===2?'dmk-weg on':'dmk-weg'}"/>`).join('');
  const orte=k.orte.map(o=>{const hier=o.id===k.hier;
    return `<g class="dmk-ort${o.s===2?' on':''}${hier?' hier':''}"><circle cx="${o.x}" cy="${o.y}" r="${hier?40:34}"/><text x="${o.x}" y="${o.y+13}" class="dmk-z">${esc(o.z)}</text>${o.gw?`<text x="${o.x+34}" y="${o.y-26}" class="dmk-gw">⚔</text>`:''}<text x="${o.x}" y="${o.y+76}" class="dmk-n">${esc(o.n)}</text></g>`}).join('');
  const h=k.orte.find(o=>o.id===k.hier),pin=h?`<g class="dmk-pin"><rect x="${h.x-105}" y="${h.y-100}" width="210" height="44" rx="22"/><text x="${h.x}" y="${h.y-70}">📍 ${esc(t('Ihr seid hier','You are here'))}</text></g>`:'';
  const b=k.box||[0,0,k.w,k.h];
  return `<svg viewBox="${b.join(' ')}" class="dmk-svg dmk-land" role="img" aria-label="${esc(t('Karte der Orte','Map of the places'))}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" class="dmk-grund"/>${dmkDeko(k)}${wege}${orte}${pin}</svg>`}
function dmkGewoelbe(g){const C=120,pad=30,w=Math.max(4,Math.max(...g.raeume.map(r=>r.x))+1),h=Math.max(2,Math.max(...g.raeume.map(r=>r.y))+1),R={};
  g.raeume.forEach(r=>R[r.id]=r);const cx=r=>pad+r.x*C+C/2,cy=r=>pad+r.y*C+C/2;
  const gaenge=g.gaenge.map(([a,b,s])=>`<line x1="${cx(R[a])}" y1="${cy(R[a])}" x2="${cx(R[b])}" y2="${cy(R[b])}" class="dmk-gang${s===2?' on':''}"/>`).join('');
  const raeume=g.raeume.map(r=>{const sz=r.a==='gang'&&r.s===2?44:88,hier=r.id===g.hier;
    return `<g class="dmk-raum${r.s===2?' on':''}${hier?' hier':''}${r.f?'':' offen'}"><rect x="${cx(r)-sz/2}" y="${cy(r)-sz/2}" width="${sz}" height="${sz}" rx="10"/>${r.s===2?`<text x="${cx(r)}" y="${cy(r)+(sz>50?4:10)}" class="dmk-z">${esc(r.z||DMK_ART[r.a]||'')}</text>${sz>50?`<text x="${cx(r)}" y="${cy(r)+34}" class="dmk-rn">${esc(r.n)}</text>`:''}`:`<text x="${cx(r)}" y="${cy(r)+10}" class="dmk-frage">?</text>`}</g>`}).join('');
  const hr=R[g.hier],pin=hr?`<g class="dmk-pin"><rect x="${cx(hr)-90}" y="${cy(hr)-84}" width="180" height="34" rx="17"/><text x="${cx(hr)}" y="${cy(hr)-60}">📍 ${esc(t('Ihr seid hier','You are here'))}</text></g>`:'';
  return `<svg viewBox="0 0 ${w*C+2*pad} ${h*C+2*pad}" class="dmk-svg dmk-tief" role="img" aria-label="${esc(t('Karte des Gewölbes','Map of the vault'))}"><rect width="${w*C+2*pad}" height="${h*C+2*pad}" rx="20" class="dmk-fels"/>${gaenge}${raeume}${pin}</svg>`}
function dmKarte(v,mode){const k=v.karte;if(!k)return '';const g=k.gewoelbe,tab=g&&DMK.tab!=='welt'?'gw':'welt';
  const seg=g?`<div class="lseg dmk-seg"><button type="button" class="${tab==='welt'?'on':''}" data-dmktab="welt">${esc(t('Welt','World'))}</button><button type="button" class="${tab==='gw'?'on':''}" data-dmktab="gw">${esc(t('Gewölbe','Vault'))}</button></div>`:'';
  const head=tab==='gw'?`<small class="mut">${esc(g.name)} · ${g.zahl} ${esc(t('Räume','rooms'))}${g.geschafft?' · ✓ '+esc(t('bezwungen','conquered')):''}</small>`:`<small class="mut">${k.gesehen} ${esc(t(k.gesehen===1?'Ort besucht':'Orte besucht',k.gesehen===1?'place visited':'places visited'))}</small>`;
  const q=k.raetsel?`<div class="dmk-raetsel"><small class="mut">${esc(t('Inschrift','Inscription'))}</small><p>„${esc(k.raetsel.frage)}“</p><small class="mut">${esc(k.raetsel.fertig?'✓ '+t('Gelöst','Solved'):t('Die Antwort steht einfach in eurer Aktion.','Just put the answer in your action.')+' '+t('Versuch','Try')+' '+Math.min(k.raetsel.versuche+1,k.raetsel.max)+'/'+k.raetsel.max)}</small>${k.raetsel.hinweis?`<small class="dmk-hint">💡 ${esc(k.raetsel.hinweis)}</small>`:''}</div>`:'';
  const zu=k.zu?`<small class="mut dmk-zu">🔒 ${esc(k.zu)}</small>`:'';
  const open=v.status!=='ende'&&v.ich&&!v.dm;
  const wege=(k.von_hier||[]).length?`<h5>${esc(t('Von hier aus','From here'))}</h5><div class="dm-pills dmk-wege">${k.von_hier.map(w=>`<button type="button" class="b" data-dmkweg="${esc(w.b||w.id[0]==='o'?w.n:'')}" data-dmkr="${esc(w.r)}" data-dmkid="${esc(w.id)}"${open?'':' disabled'}>${esc((w.r?w.r+': ':'')+w.n)}${w.b?' ✓':''}</button>`).join('')}</div>`:'';
  const host=mode==='p'&&v.gastgeber&&v.status!=='ende'&&(k.neu||k.gw_knopf)?`<div class="dm-hostb">${k.gw_knopf?`<button type="button" class="b" data-dmkarte="gewoelbe"${v.dm?' disabled':''}>${esc(t('🎲 Gewölbe würfeln','🎲 Roll a vault'))}</button>`:''}${k.neu?`<button type="button" class="b" data-dmkarte="neu"${v.dm?' disabled':''}>${esc(t('↻ Karte neu würfeln','↻ Roll the map again'))}</button>`:''}</div>`:'';
  return `<div class="dmk${DMK.gross?' gross':''}"><div class="dmk-kopf"><h5>${esc(t('Karte','Map'))}</h5>${seg}<button type="button" class="ic-ib dmk-gross" data-dmkgross="1" title="${esc(t('Karte groß','Large map'))}" aria-label="${esc(t('Karte groß','Large map'))}">⤢</button></div>${head}
    ${tab==='gw'?dmkGewoelbe(g):dmkWelt(k)}${tab==='gw'?q+zu:''}${wege}${host}</div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('.dmk [data-dmktab],.dmk [data-dmkgross],.dmk [data-dmkid],.dmk [data-dmkarte]');if(!b)return;const B=b.dataset;
  if(B.dmktab){DMK.tab=B.dmktab;if(typeof DG!=='undefined'&&DG.v&&b.closest('#dgcard'))dgDraw();else dmDraw();return}
  if(B.dmkgross){DMK.gross=!DMK.gross;b.closest('.dmk').classList.toggle('gross',DMK.gross);return}
  if(B.dmkid){const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
    const s=B.dmkid==='aus'?t('Wir verlassen das Gewölbe.','We leave the vault.'):B.dmkid==='ein'?t('Wir gehen ins Gewölbe.','We go into the vault.')
      :B.dmkweg?t('Wir gehen weiter zu „'+B.dmkweg+'“.','We go on to '+B.dmkweg+'.'):t('Wir gehen nach '+B.dmkr+' in den nächsten Raum.','We go '+B.dmkr+' into the next room.');
    ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+s;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus();return}
  if(B.dmkarte){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/karte`,{was:B.dmkarte},DM);if(d){DM.v=d;DM.at=Date.now();if(B.dmkarte==='gewoelbe')DMK.tab='gw'}dmDraw()}});
