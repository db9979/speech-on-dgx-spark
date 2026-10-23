// KI-Dungeon-Master: the map of the round (dungeon_karte.py). The panel rolls and keeps it; this only draws what the
// seat may see: visited and known places, ways into the unknown as stubs with „?“, the vault where the group is;
// a place or room shows its picture once painted (dungeon_dingbild), its sign until then.
// Tapping a way writes it into the own action (it stays the player's text); the host rolls the map again or a vault.
const DMK={tab:'',gross:false};
const DMK_ART={raetsel:'❓',waechter:'👹',boss:'💀',falle:'⚠',schatz:'💰',quelle:'💧',altar:'🔆',eingang:'🚪'};
function dmkDeko(k){const d=k.deko||{},P=a=>a.map(p=>p.join(',')).join(' ');
  if(d.fluss)return `<polyline points="${P(d.fluss)}" class="dmk-fluss"/>`;
  if(d.see)return `<ellipse cx="${d.see[0]}" cy="${d.see[1]}" rx="${d.see[2]}" ry="${d.see[3]}" class="dmk-wasser"/>`;
  if(d.grenze)return `<polyline points="${P(d.grenze)}" class="dmk-grenze"/>`;
  if(d.kueste)return `<polygon points="${P(d.kueste)} ${k.w},${k.h} 0,${k.h}" class="dmk-wasser"/><polyline points="${P(d.kueste)}" class="dmk-ufer"/>`;
  return ''}
// a name in at most two lines (long story places like „Quarantäneviertel, Velmar“), each line about 14 letters
function dmkZeilen(n){if(n.length<=14)return [n];const w=n.split(/(?<=[ ,-])/);let a='',i=0;
  while(i<w.length&&(a+w[i]).trim().length<=Math.max(14,Math.ceil(n.length/2)))a+=w[i++];
  if(!a){a=w[0];i=1}const r=w.slice(i).join('').trim();return r?[a.trim().replace(/,$/,''),r.length>18?r.slice(0,17)+'…':r]:[a.trim()]}
// each name goes below, above, right or left of its place, wherever it hits no other place, name or edge first
function dmkLagen(k,rad,F){const b=k.box||[0,0,k.w,k.h],boxes=k.orte.map(o=>{const R=rad(o)*1.2;return [o.x-R,o.y-R,o.x+R,o.y+R]}),out={};
  const hit=(q,p)=>q[0]<p[2]&&q[2]>p[0]&&q[1]<p[3]&&q[3]>p[1];
  const order=[...k.orte].sort((x,y)=>(y.id===k.hier)-(x.id===k.hier)||(y.s||0)-(x.s||0));
  order.forEach(o=>{const R=rad(o),L=dmkZeilen(o.n),w=Math.max(...L.map(l=>l.length))*F*.56+F*.4,h=L.length*F*1.15;
    const g=F*.4,tries=[[o.x,o.y+R+g+F*.85,'middle'],[o.x,o.y-R-g-h+F*.85,'middle'],[o.x+R+g,o.y+F*.35-(h-F*1.15)/2,'start'],[o.x-R-g,o.y+F*.35-(h-F*1.15)/2,'end']];
    const rect=([x,y,a])=>{const x0=a==='middle'?x-w/2:a==='start'?x:x-w;return [x0,y-F*.85,x0+w,y-F*.85+h]};
    const inside=q=>q[0]>=b[0]&&q[2]<=b[0]+b[2]&&q[1]>=b[1]&&q[3]<=b[1]+b[3];
    let best=tries[0],bad=1e9;
    for(const t of tries){const q=rect(t),n=boxes.filter(p=>hit(q,p)).length+(inside(q)?0:2);if(n<bad){bad=n;best=t}if(!n)break}
    boxes.push(rect(best));out[o.id]={x:best[0],y:best[1],a:best[2],L}});
  return out}
// sizes in screen pixels whatever the box: u = map units per pixel of the drawn width (the last drawn map, else a guess)
function dmkPx(){const e=document.querySelector(DMK.gross?'.dmk.gross .dmk-land':'#dmview .dmk-land,#dgcard .dmk-land');
  return e&&e.clientWidth||(DMK.gross?Math.min(innerWidth-60,1100):innerWidth<760?innerWidth-40:300)}
function dmkWelt(k,px){const b=k.box||[0,0,k.w,k.h],u0=b[2]/(px||dmkPx()),u=u0*(DMK.gross?1.3:1),F=12.5*u,rad=o=>(o.b?21:13)*u;
  const wege=k.wege.map(w=>w[4]===0?`<line x1="${w[0]}" y1="${w[1]}" x2="${w[2]}" y2="${w[3]}" class="dmk-stub"/><text x="${w[2]}" y="${w[3]+5*u}" class="dmk-frage">?</text>`
    :`<line x1="${w[0]}" y1="${w[1]}" x2="${w[2]}" y2="${w[3]}" class="${w[4]===2?'dmk-weg on':'dmk-weg'}"/>`).join('');
  const lage=dmkLagen(k,rad,F);
  const orte=k.orte.map(o=>{const hier=o.id===k.hier,l=lage[o.id],R=rad(o);
    const name=`<text x="${l.x}" y="${l.y}" text-anchor="${l.a}" class="dmk-n">${l.L.map((z,i)=>`<tspan x="${l.x}" dy="${i?F*1.15:0}">${esc(z)}</tspan>`).join('')}</text>`;
    return `<g class="dmk-ort${o.s===2?' on':''}${hier?' hier':''}"><circle cx="${o.x}" cy="${o.y}" r="${R}"/>${o.b?`<clipPath id="dmkc-${o.id}"><circle cx="${o.x}" cy="${o.y}" r="${R-1.5*u}"/></clipPath><image data-dmkb="${esc(o.b)}" x="${o.x-R}" y="${o.y-R}" width="${2*R}" height="${2*R}" preserveAspectRatio="xMidYMid slice" clip-path="url(#dmkc-${o.id})" class="dmk-bild"/>`:`<text x="${o.x}" y="${o.y+5*u}" class="dmk-z">${esc(o.z)}</text>`}${o.gw?`<text x="${o.x+R}" y="${o.y-R+3*u}" class="dmk-gw">⚔</text>`:''}${hier?`<text x="${o.x-R}" y="${o.y-R+3*u}" class="dmk-pin">📍</text>`:''}${name}</g>`}).join('');
  return `<svg viewBox="${b.join(' ')}" class="dmk-svg dmk-land" style="--u:${u.toFixed(3)}" data-px="${Math.round(b[2]/u0)}" role="img" aria-label="${esc(t('Karte der Orte','Map of the places'))}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" class="dmk-grund"/>${dmkDeko(k)}${wege}${orte}</svg>`}
function dmkGewoelbe(g){const C=120,pad=30,w=Math.max(4,Math.max(...g.raeume.map(r=>r.x))+1),h=Math.max(2,Math.max(...g.raeume.map(r=>r.y))+1),R={};
  g.raeume.forEach(r=>R[r.id]=r);const cx=r=>pad+r.x*C+C/2,cy=r=>pad+r.y*C+C/2;
  const gaenge=g.gaenge.map(([a,b,s])=>`<line x1="${cx(R[a])}" y1="${cy(R[a])}" x2="${cx(R[b])}" y2="${cy(R[b])}" class="dmk-gang${s===2?' on':''}"/>`).join('');
  const raeume=g.raeume.map(r=>{const sz=r.a==='gang'&&r.s===2?44:88,hier=r.id===g.hier;
    return `<g class="dmk-raum${r.s===2?' on':''}${hier?' hier':''}${r.f?'':' offen'}"><rect x="${cx(r)-sz/2}" y="${cy(r)-sz/2}" width="${sz}" height="${sz}" rx="10"/>${r.s===2?`${r.b?`<clipPath id="dmkc-${r.id}"><rect x="${cx(r)-sz/2+3}" y="${cy(r)-sz/2+3}" width="${sz-6}" height="${sz-6}" rx="8"/></clipPath><image data-dmkb="${esc(r.b)}" x="${cx(r)-sz/2}" y="${cy(r)-sz/2}" width="${sz}" height="${sz}" preserveAspectRatio="xMidYMid slice" clip-path="url(#dmkc-${r.id})" class="dmk-bild"/>`:`<text x="${cx(r)}" y="${cy(r)+(sz>50?4:10)}" class="dmk-z">${esc(r.z||DMK_ART[r.a]||'')}</text>`}${sz>50?`<text x="${cx(r)}" y="${cy(r)+34}" class="dmk-rn">${esc(r.n)}</text>`:''}`:`<text x="${cx(r)}" y="${cy(r)+10}" class="dmk-frage">?</text>`}</g>`}).join('');
  const hr=R[g.hier],pin=hr?`<text x="${cx(hr)-40}" y="${cy(hr)-30}" class="dmk-pin">📍</text>`:'';
  return `<svg viewBox="0 0 ${w*C+2*pad} ${h*C+2*pad}" class="dmk-svg dmk-tief" role="img" aria-label="${esc(t('Karte des Gewölbes','Map of the vault'))}"><rect width="${w*C+2*pad}" height="${h*C+2*pad}" rx="20" class="dmk-fels"/>${gaenge}${raeume}${pin}</svg>`}
function dmKarte(v,mode){const k=v.karte;if(!k)return '';DMK.k=k;DMK.mode=mode;setTimeout(dmkNach,0);const g=k.gewoelbe,tab=g&&DMK.tab!=='welt'?'gw':'welt';
  const seg=g?`<div class="lseg dmk-seg"><button type="button" class="${tab==='welt'?'on':''}" data-dmktab="welt">${esc(t('Welt','World'))}</button><button type="button" class="${tab==='gw'?'on':''}" data-dmktab="gw">${esc(t('Gewölbe','Vault'))}</button></div>`:'';
  const head=tab==='gw'?`<small class="mut">📍 ${esc(g.name)}${((g.raeume.find(r=>r.id===g.hier)||{}).n)?' · '+esc(g.raeume.find(r=>r.id===g.hier).n):''} · ${g.zahl} ${esc(t('Räume','rooms'))}${g.geschafft?' · ✓ '+esc(t('bezwungen','conquered')):''}</small>`:`<small class="mut">📍 ${esc(t('Ihr seid in ','You are at ')+((k.orte.find(o=>o.id===k.hier)||{}).n||''))} · ${k.gesehen} ${esc(t(k.gesehen===1?'Ort besucht':'Orte besucht',k.gesehen===1?'place visited':'places visited'))}</small>`;
  const q=k.raetsel?`<div class="dmk-raetsel"><small class="mut">${esc(t('Inschrift','Inscription'))}</small><p>„${esc(k.raetsel.frage)}“</p><small class="mut">${esc(k.raetsel.fertig?'✓ '+t('Gelöst','Solved'):t('Die Antwort steht einfach in eurer Aktion.','Just put the answer in your action.')+' '+t('Versuch','Try')+' '+Math.min(k.raetsel.versuche+1,k.raetsel.max)+'/'+k.raetsel.max)}</small>${k.raetsel.hinweis?`<small class="dmk-hint">💡 ${esc(k.raetsel.hinweis)}</small>`:''}</div>`:'';
  const zu=k.zu?`<small class="mut dmk-zu">🔒 ${esc(k.zu)}</small>`:'';
  const open=v.status!=='ende'&&v.ich&&!v.dm;
  const wege=(k.von_hier||[]).length?`<h5>${esc(t('Von hier aus','From here'))}</h5><div class="dm-pills dmk-wege">${k.von_hier.map(w=>`<button type="button" class="b" data-dmkweg="${esc(w.b||w.id[0]==='o'?w.n:'')}" data-dmkr="${esc(w.r)}" data-dmkid="${esc(w.id)}"${open?'':' disabled'}>${esc((w.r?w.r+': ':'')+w.n)}${w.b?' ✓':''}</button>`).join('')}</div>`:'';
  const host=mode==='p'&&v.gastgeber&&v.status!=='ende'&&(k.neu||k.gw_knopf)?`<div class="dm-hostb">${k.gw_knopf?`<button type="button" class="b" data-dmkarte="gewoelbe"${v.dm?' disabled':''}>${esc(t('🎲 Gewölbe würfeln','🎲 Roll a vault'))}</button>`:''}${k.neu?`<button type="button" class="b" data-dmkarte="neu"${v.dm?' disabled':''}>${esc(t('↻ Karte neu würfeln','↻ Roll the map again'))}</button>`:''}</div>`:'';
  return `<div class="dmk${DMK.gross?' gross':''}"><div class="dmk-kopf"><h5>${esc(t('Karte','Map'))}</h5>${seg}<button type="button" class="ic-ib dmk-gross" data-dmkgross="1" title="${esc(t('Karte groß','Large map'))}" aria-label="${esc(t('Karte groß','Large map'))}">⤢</button></div>${head}
    ${tab==='gw'?dmkGewoelbe(g):dmkWelt(k)}${tab==='gw'?q+zu:''}${wege}${host}</div>`}
function dmkNach(){document.querySelectorAll('.dmk-land').forEach(e=>{const px=e.clientWidth,was=+e.dataset.px;if(DMK.k&&px&&Math.abs(px-was)>was*.15)e.outerHTML=dmkWelt(DMK.k,px)});dmkFill()}
// the pictures of places and rooms (dungeon_dingbild, the same as the items'): a profile loads them itself, a guest's seat as a blob
async function dmkFill(){for(const im of document.querySelectorAll('.dmk image[data-dmkb]:not([href])')){const n=im.dataset.dmkb,key='d'+n;
    if(DMK.mode==='p'){im.setAttribute('href','/api/profile/dungeon/ding/'+encodeURIComponent(n));continue}
    if(key in DMI){if(DMI[key])im.setAttribute('href',DMI[key]);continue}DMI[key]='';
    try{const r=await /*raw: a guest seat's picture as a blob, api() would open the login on a 401*/fetch('/api/dungeon/ding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,name:n})});
      if(!r.ok){delete DMI[key];continue}DMI[key]=URL.createObjectURL(await r.blob())}catch(e){delete DMI[key];continue}
    document.querySelectorAll(`.dmk image[data-dmkb="${n}"]`).forEach(x=>x.setAttribute('href',DMI[key]))}}
addEventListener('resize',()=>{clearTimeout(DMK.rz);DMK.rz=setTimeout(dmkNach,200)});
document.body.addEventListener('click',async e=>{const b=e.target.closest('.dmk [data-dmktab],.dmk [data-dmkgross],.dmk [data-dmkid],.dmk [data-dmkarte]');if(!b)return;const B=b.dataset;
  if(B.dmktab){DMK.tab=B.dmktab;if(typeof DG!=='undefined'&&DG.v&&b.closest('#dgcard'))dgDraw();else dmDraw();return}
  if(B.dmkgross){DMK.gross=!DMK.gross;b.closest('.dmk').classList.toggle('gross',DMK.gross);setTimeout(dmkNach,0);return}
  if(B.dmkid){const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
    const s=B.dmkid==='aus'?t('Wir verlassen das Gewölbe.','We leave the vault.'):B.dmkid==='ein'?t('Wir gehen ins Gewölbe.','We go into the vault.')
      :B.dmkweg?t('Wir gehen weiter zu „'+B.dmkweg+'“.','We go on to '+B.dmkweg+'.'):t('Wir gehen nach '+B.dmkr+' in den nächsten Raum.','We go '+B.dmkr+' into the next room.');
    ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+s;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus();return}
  if(B.dmkarte){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/karte`,{was:B.dmkarte},DM);if(d){DM.v=d;DM.at=Date.now();if(B.dmkarte==='gewoelbe')DMK.tab='gw'}dmDraw()}});
