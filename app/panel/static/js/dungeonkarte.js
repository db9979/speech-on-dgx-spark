// KI-Dungeon-Master: the map of the round (dungeon_karte.py). The panel rolls and keeps it; this only draws what the
// seat may see: visited and known places, ways into the unknown as stubs with „?“, the vault where the group is;
// a place or room shows its picture once painted (dungeon_dingbild), its sign until then.
// Tapping a way writes it into the own action (it stays the player's text); the host rolls the map again or a vault.
const DMK={tab:'',gross:false};
const DMK_ART={raetsel:'❓',waechter:'👹',boss:'💀',falle:'⚠',schatz:'💰',quelle:'💧',altar:'🔆',eingang:'🚪'};
// the land (Dominik 2026-10-24 „1, 3, 4, 6“): water from the panel's deko, drawn as ink on parchment
function dmkDeko(k,u){const d=k.deko||{},P=a=>a.map(p=>p.join(',')).join(' ');
  if(d.fluss)return `<polyline points="${P(d.fluss)}" class="dmk-fluss"/><polyline points="${P(d.fluss)}" class="dmk-stroemung" transform="translate(0,${-3*u})"/>`;
  if(d.see){const [x,y,rx,ry]=d.see;return `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" class="dmk-wasser"/>`+[1,2,3].map(i=>`<ellipse cx="${x}" cy="${y}" rx="${rx+i*7*u}" ry="${ry+i*7*u}" class="dmk-welle" style="opacity:${.5-i*.13}"/>`).join('')}
  if(d.grenze)return `<polyline points="${P(d.grenze)}" class="dmk-grenze"/>`;
  if(d.kueste)return `<polygon points="${P(d.kueste)} ${k.w+400},${k.h+400} ${-400},${k.h+400}" class="dmk-wasser"/>`+[1,2,3,4].map(i=>`<polyline points="${P(d.kueste)}" class="dmk-welle" transform="translate(0,${i*7*u})" style="opacity:${.55-i*.12}"/>`).join('')+`<polyline points="${P(d.kueste)}" class="dmk-ufer"/>`;
  return ''}
// a fixed random of the map (the same trees on every repaint): seeded by the panel's land
function dmkRng(k){let h=2166136261;for(const c of JSON.stringify([k.form,k.deko,k.w]))h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;
  return()=>{h=(Math.imul(h,1664525)+1013904223)>>>0;return h/4294967296}}
function dmkNass(k,x,y,m){const d=k.deko||{},on=(pts,f)=>{for(let i=1;i<pts.length;i++){const [a,b]=pts[i-1],[c,e]=pts[i];if(x>=a&&x<=c)return f(b+(e-b)*(x-a)/(c-a))}return false};
  if(d.fluss&&on(d.fluss,yy=>Math.abs(yy-y)<m))return true;
  if(d.see&&((x-d.see[0])/(d.see[2]+m))**2+((y-d.see[1])/(d.see[3]+m))**2<1)return true;
  return !!(d.kueste&&on(d.kueste,yy=>y>yy-m))}
// what grows around a kind of place (the nearest known place decides), drawn as small ink signs
const DMK_LAND={wald:'wald',lager:'wald',dschungel:'wald',muehle:'wald',berg:'berg',hoehle:'berg',mine:'berg',krater:'berg',festung:'berg',ruine:'huegel',krypta:'huegel',turm:'huegel',gruft:'huegel',friedhof:'huegel',sumpf:'sumpf',lagune:'sumpf'};
function dmkGelaende(k,u,frei){const R=dmkRng(k),b=k.box||[0,0,k.w,k.h],out=[],S=Math.max(.9,u*.75),step=36;
  const nahe=(x,y,d)=>k.orte.some(o=>Math.hypot(o.x-x,o.y-y)<d)||k.wege.some(([x1,y1,x2,y2])=>{const L=Math.hypot(x2-x1,y2-y1)||1,q=Math.max(0,Math.min(1,((x-x1)*(x2-x1)+(y-y1)*(y2-y1))/L/L));return Math.hypot(x1+q*(x2-x1)-x,y1+q*(y2-y1)-y)<d*.5});
  for(let gy=-200;gy<k.h+200;gy+=step)for(let gx=-300;gx<k.w+300;gx+=step){const x=gx+R()*step,y=gy+R()*step,roll=R(),s=S*(.85+R()*.4);
    if(x<b[0]||x>b[0]+b[2]||y<b[1]||y>b[1]+b[3]||roll<.35)continue;
    if(nahe(x,y,30*S+18)||dmkNass(k,x,y,14*S)||frei.some(q=>x>q[0]-8*S&&x<q[2]+8*S&&y>q[1]-4*S&&y<q[3]+14*S))continue;
    let best=null,bd=1e9;for(const o of k.orte){const d=Math.hypot(o.x-x,o.y-y);if(d<bd){bd=d;best=o}}
    const art=bd<200&&best?DMK_LAND[best.a]||(roll<.5?'gras':roll<.8?'huegel':'wald'):roll<.5?'gras':roll<.72?'huegel':'wald';
    if(art==='wald'){out.push(dmkBaum(x,y,s));if(roll>.6)out.push(dmkBaum(x+9*s,y+4*s,s*.8))}
    else if(art==='berg')out.push(`<g transform="translate(${x.toFixed(1)},${y.toFixed(1)}) scale(${s.toFixed(2)})" class="dmk-berg"><path d="M-14,8 L-2,-11 L3,-3 L7,-8 L16,8Z"/><path d="M-2,-11 L1,-6 L-1,-4 L-4,-7Z" class="dmk-schnee"/></g>`);
    else if(art==='sumpf')out.push(`<path d="M${x-8*s},${y} h${6*s} M${x+2*s},${y+3*s} h${7*s} M${x-3*s},${y-5*s} l1,${-5*s} m3,${5*s} l1,${-6*s}" class="dmk-strich"/>`);
    else if(art==='huegel')out.push(`<path d="M${x-11*s},${y} Q${x},${y-10*s} ${x+11*s},${y}" class="dmk-strich"/>`);
    else out.push(`<path d="M${x-3*s},${y} l1.5,${-5*s} M${x},${y} l0,${-6.5*s} M${x+3*s},${y} l-1.5,${-5*s}" class="dmk-strich dmk-gras"/>`)}
  return out.join('')}
const dmkBaum=(x,y,s)=>`<path transform="translate(${x.toFixed(1)},${y.toFixed(1)}) scale(${s.toFixed(2)})" d="M0,-11 C6,-11 8,-5 6,-1 C9,1 8,6 3,6 L1,6 L1,10 L-1,10 L-1,6 L-3,6 C-8,6 -9,1 -6,-1 C-8,-5 -6,-11 0,-11Z" class="dmk-baum"/>`;
// a way as a slightly bent ink line (bent the same on every repaint)
function dmkBogen(x1,y1,x2,y2){const n=Math.abs(Math.sin(x1*.013+y1*.007+x2*.011+y2*.017)),bx=(x1+x2)/2+(y2-y1)*.08*(n-.5),by=(y1+y2)/2-(x2-x1)*.08*(n-.5);return `M${x1},${y1} Q${bx.toFixed(1)},${by.toFixed(1)} ${x2},${y2}`}
// a name in at most two lines (long story places like „Quarantäneviertel, Velmar“), each line about 14 letters
function dmkZeilen(n){if(n.length<=14)return [n];const w=n.split(/(?<=[ ,-])/);let a='',i=0;
  while(i<w.length&&(a+w[i]).trim().length<=Math.max(14,Math.ceil(n.length/2)))a+=w[i++];
  if(!a){a=w[0];i=1}const r=w.slice(i).join('').trim();return r?[a.trim().replace(/,$/,''),r.length>18?r.slice(0,17)+'…':r]:[a.trim()]}
// each name goes below, above, right or left of its place, wherever it hits no other place, name or edge first
function dmkLagen(k,rad,F,frei){const b=k.box||[0,0,k.w,k.h],boxes=k.orte.map(o=>{const R=rad(o)*1.2;return [o.x-R,o.y-R,o.x+R,o.y+R]}).concat(frei||[]),out={};
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
// the look per world (3): the table's colours (welten[].farben, the admin's) and the world's map: parchment, the pale
// paper of horror, a sea chart, a star chart; the motion (6) only once per change, never with „weniger Bewegung“
const DMK_STIL={fantasy:'dmk-pergament',horror:'dmk-fahl',piraten:'dmk-see',scifi:'dmk-sterne'};
const dmkRuhig=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function dmkWelt(k,px,zieh){const b=k.box||[0,0,k.w,k.h],u0=b[2]/(px||dmkPx()),u=u0*(DMK.gross?1.3:1),F=12.5*u,rad=o=>(o.b?21:o.id===k.hier?15:13)*u,[x0,y0,W,H]=b;
  const stil=DMK_STIL[k.welt]||'dmk-pergament',tw=DMK.titel?Math.min(W*.6,Math.min(DMK.titel.length,34)*F*.5+F*1.6):0;
  const lage=dmkLagen(k,rad,F,[[x0+W-64*u,y0,x0+W,y0+70*u]].concat(tw?[[x0,y0+H-12*u-F*1.6,x0+12*u+tw,y0+H]]:[]));
  const frei=Object.values(lage).map(l=>{const w=Math.max(...l.L.map(z=>z.length))*F*.56,x=l.a==='middle'?l.x-w/2:l.a==='start'?l.x:l.x-w;return [x,l.y-F,x+w,l.y-F+l.L.length*F*1.15]});
  const wege=k.wege.map(w=>w[4]===0?`<path d="${dmkBogen(w[0],w[1],w[2],w[3])}" class="dmk-stub"/><text x="${w[2]}" y="${w[3]+5*u}" class="dmk-frage">?</text>`
    :`<path d="${dmkBogen(w[0],w[1],w[2],w[3])}" class="${w[4]===2?'dmk-weg on':'dmk-weg'}"/>`).join('');
  // fog (1): beyond what is known the land lies under clouds; the clouds follow the known places
  const sicht=k.orte.map(o=>`<circle cx="${o.x}" cy="${o.y}" r="${(o.s===2?170:120)+18*u}"/>`).join('')+k.wege.filter(w=>w[4]===0).map(w=>`<circle cx="${w[2]}" cy="${w[3]}" r="${40+10*u}"/>`).join('');
  const neu=DMK.gesehen&&!dmkRuhig()?k.orte.filter(o=>!DMK.gesehen.has(o.id)):[];
  const orte=k.orte.map(o=>{const hier=o.id===k.hier,l=lage[o.id],R=rad(o);
    const name=`<text x="${l.x}" y="${l.y}" text-anchor="${l.a}" class="dmk-n">${l.L.map((z,i)=>`<tspan x="${l.x}" dy="${i?F*1.15:0}">${esc(z)}</tspan>`).join('')}</text>`;
    return `<g class="dmk-ort${o.s===2?' on':''}${hier?' hier':''}${neu.includes(o)?' dmk-auf':''}">${hier?`<circle cx="${o.x}" cy="${o.y}" r="${R+7*u}" class="dmk-schein"/>`:''}<circle cx="${o.x}" cy="${o.y}" r="${R}" class="dmk-c"/><circle cx="${o.x}" cy="${o.y}" r="${R-2.6*u}" class="dmk-ring"/>${o.b?`<clipPath id="dmkc-${o.id}"><circle cx="${o.x}" cy="${o.y}" r="${R-1.5*u}"/></clipPath><image data-dmkb="${esc(o.b)}" x="${o.x-R}" y="${o.y-R}" width="${2*R}" height="${2*R}" preserveAspectRatio="xMidYMid slice" clip-path="url(#dmkc-${o.id})" class="dmk-bild"/>`:`<text x="${o.x}" y="${o.y+5*u}" class="dmk-z">${esc(o.z)}</text>`}${o.gw?`<g transform="translate(${o.x+R*.85},${o.y-R*.85})"><circle r="${6.5*u}" class="dmk-gwk"/><text y="${3*u}" class="dmk-gw">⚔</text></g>`:''}${name}</g>`}).join('');
  const h=k.orte.find(o=>o.id===k.hier),R=h?rad(h):0,vor=zieh&&DMK.wo&&h&&(DMK.wo[0]!==h.x||DMK.wo[1]!==h.y)&&!dmkRuhig()?DMK.wo:null;
  const fahne=h?`<g class="dmk-fahne" transform="translate(${h.x},${h.y-R-2*u})">${vor?`<animateTransform attributeName="transform" type="translate" from="${vor[0]},${vor[1]-R-2*u}" to="${h.x},${h.y-R-2*u}" dur="1.4s" calcMode="spline" keySplines=".4 0 .2 1" keyTimes="0;1" fill="freeze"/>`:''}<path d="M0,0 V${-20*u}"/><path d="M0,${-20*u} L${14*u},${-16.5*u} L0,${-12.5*u}Z" class="dmk-tuch"/></g>`:'';
  const ko=`<g transform="translate(${x0+W-32*u},${y0+38*u}) scale(${(u*.62).toFixed(2)})" class="dmk-kompass"><circle r="30"/><circle r="24" class="dmk-ring"/><path d="M0,-38 L6,-6 L0,0 L-6,-6Z M0,38 L6,6 L0,0 L-6,6Z"/><path d="M-38,0 L-6,-6 L0,0 L-6,6Z M38,0 L6,-6 L0,0 L6,6Z" class="dmk-halb"/><text y="-42">N</text></g>`;
  const ti=DMK.titel?`<g transform="translate(${x0+12*u},${y0+H-12*u})" class="dmk-titel"><rect y="${-F*1.5}" width="${tw}" height="${F*1.9}"/><text x="${tw/2}" y="${-F*.15}">${esc(DMK.titel.length>34?DMK.titel.slice(0,33)+'…':DMK.titel)}</text></g>`:'';
  return `<svg viewBox="${b.join(' ')}" class="dmk-svg dmk-land ${stil}" style="--u:${u.toFixed(3)}" data-px="${Math.round(b[2]/u0)}" role="img" aria-label="${esc(t('Karte der Orte','Map of the places'))}"><defs>
    <filter id="dmkf-papier" x="0" y="0" width="1" height="1"><feTurbulence type="fractalNoise" baseFrequency=".8" numOctaves="3" seed="4"/><feColorMatrix values="0 0 0 0 .45  0 0 0 0 .33  0 0 0 0 .18  0 0 0 .18 0"/><feComposite in2="SourceGraphic" operator="in"/><feBlend in="SourceGraphic" mode="multiply"/></filter>
    <filter id="dmkf-wolke" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency=".012" numOctaves="3" seed="9"/><feDisplacementMap in="SourceGraphic" scale="60"/><feGaussianBlur stdDeviation="8"/></filter>
    <radialGradient id="dmkf-rand" r="75%"><stop offset="62%" stop-opacity="0" class="dmk-rand"/><stop offset="100%" stop-opacity=".5" class="dmk-rand"/></radialGradient>
    <mask id="dmkf-nebel" maskUnits="userSpaceOnUse" x="${x0-60}" y="${y0-60}" width="${W+120}" height="${H+120}"><rect x="${x0-60}" y="${y0-60}" width="${W+120}" height="${H+120}" fill="#fff"/><g filter="url(#dmkf-wolke)" fill="#000">${sicht}</g></mask></defs>
    <clipPath id="dmkf-box"><rect x="${x0+4*u}" y="${y0+4*u}" width="${W-8*u}" height="${H-8*u}"/></clipPath>
    <rect x="${x0}" y="${y0}" width="${W}" height="${H}" class="dmk-grund" filter="url(#dmkf-papier)"/><g clip-path="url(#dmkf-box)">${dmkDeko(k,u)}${dmkGelaende(k,u,frei)}</g>${wege}${orte}${fahne}
    <rect x="${x0}" y="${y0}" width="${W}" height="${H}" class="dmk-nebel" mask="url(#dmkf-nebel)"/><rect x="${x0}" y="${y0}" width="${W}" height="${H}" fill="url(#dmkf-rand)"/>${ko}${ti}
    <rect x="${x0+4*u}" y="${y0+4*u}" width="${W-8*u}" height="${H-8*u}" class="dmk-rahmen"/><rect x="${x0+7.5*u}" y="${y0+7.5*u}" width="${W-15*u}" height="${H-15*u}" class="dmk-rahmen dmk-fein"/></svg>`}
// the vault (4): stone floor, thick walls, doors between the rooms, a colour per kind of room, torches in the rooms
// gone through, light around the group and darkness towards the edge
const DMK_TON={boss:'dmk-ton-boss',schatz:'dmk-ton-schatz',falle:'dmk-ton-falle',raetsel:'dmk-ton-raetsel',waechter:'dmk-ton-waechter',quelle:'dmk-ton-quelle',altar:'dmk-ton-altar'};
function dmkGewoelbe(g){const C=120,pad=34,w=Math.max(4,Math.max(...g.raeume.map(r=>r.x))+1),h=Math.max(2,Math.max(...g.raeume.map(r=>r.y))+1),R={};
  g.raeume.forEach(r=>R[r.id]=r);const cx=r=>pad+r.x*C+C/2,cy=r=>pad+r.y*C+C/2,WW=w*C+2*pad,HH=h*C+2*pad;
  const gaenge=g.gaenge.map(([a,b,s])=>{const A=R[a],B=R[b],x=Math.min(cx(A),cx(B)),y=Math.min(cy(A),cy(B));
    return A.y===B.y?`<rect x="${x}" y="${cy(A)-15}" width="${Math.abs(cx(B)-cx(A))}" height="30" class="dmk-gang${s===2?' on':''}"/>`:`<rect x="${cx(A)-15}" y="${y}" width="30" height="${Math.abs(cy(B)-cy(A))}" class="dmk-gang${s===2?' on':''}"/>`}).join('');
  const tueren=g.gaenge.map(([a,b])=>{const A=R[a],B=R[b],mx=(cx(A)+cx(B))/2,my=(cy(A)+cy(B))/2;
    return A.y===B.y?`<rect x="${mx-5}" y="${my-14}" width="10" height="28" rx="2" class="dmk-tuer"/>`:`<rect x="${mx-14}" y="${my-5}" width="28" height="10" rx="2" class="dmk-tuer"/>`}).join('');
  const raeume=g.raeume.map(r=>{const on=r.s===2,sz=r.a==='gang'&&on?50:92,hier=r.id===g.hier,x=cx(r)-sz/2,y=cy(r)-sz/2;
    if(!on)return `<g class="dmk-raum"><rect x="${x}" y="${y}" width="${sz}" height="${sz}" rx="6"/><text x="${cx(r)}" y="${cy(r)+10}" class="dmk-frage">?</text></g>`;
    return `<g class="dmk-raum on${hier?' hier':''}${r.f?'':' offen'}"><rect x="${x-6}" y="${y-6}" width="${sz+12}" height="${sz+12}" rx="8" class="dmk-wand"/><rect x="${x}" y="${y}" width="${sz}" height="${sz}" rx="4" class="dmk-boden"/>${DMK_TON[r.a]?`<rect x="${x}" y="${y}" width="${sz}" height="${sz}" rx="4" class="dmk-ton ${DMK_TON[r.a]}"/>`:''}
      ${r.b?`<clipPath id="dmkc-${r.id}"><rect x="${x+3}" y="${y+3}" width="${sz-6}" height="${sz-6}" rx="3"/></clipPath><image data-dmkb="${esc(r.b)}" x="${x}" y="${y}" width="${sz}" height="${sz}" preserveAspectRatio="xMidYMid slice" clip-path="url(#dmkc-${r.id})" class="dmk-bild"/>`:`<text x="${cx(r)}" y="${cy(r)+(sz>60?4:10)}" class="dmk-z">${esc(r.z||DMK_ART[r.a]||'')}</text>`}
      ${sz>60?`<text x="${cx(r)}" y="${cy(r)+36}" class="dmk-rn">${esc(r.n)}</text><g transform="translate(${x+9},${y+12})" class="dmk-fackel"><rect x="-1.5" y="-1" width="3" height="10"/><circle cy="-4" r="4.5" class="dmk-flamme"/></g>`:''}
      ${hier?`<rect x="${x-3}" y="${y-3}" width="${sz+6}" height="${sz+6}" rx="6" class="dmk-hier"/>`:''}</g>`}).join('');
  const hr=R[g.hier]||g.raeume[0],lx=cx(hr)/WW,ly=cy(hr)/HH;
  return `<svg viewBox="0 0 ${WW} ${HH}" class="dmk-svg dmk-tief" role="img" aria-label="${esc(t('Karte des Gewölbes','Map of the vault'))}"><defs>
    <pattern id="dmkf-stein" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" class="dmk-stein"/><path d="M0,0 H32 M0,16 H32 M16,0 V16 M8,16 V32 M24,16 V32" class="dmk-fuge"/><rect x="2" y="2" width="12" height="12" class="dmk-stein2"/><rect x="18" y="18" width="12" height="12" class="dmk-stein2" opacity=".6"/></pattern>
    <filter id="dmkf-fels"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="4" seed="3"/><feColorMatrix values="0 0 0 0 .1  0 0 0 0 .08  0 0 0 0 .12  0 0 0 .9 0"/></filter>
    <radialGradient id="dmkf-licht" cx="${lx}" cy="${ly}" r="${Math.max(.35,(C*3.2)/WW)}"><stop offset="0" stop-opacity="0"/><stop offset=".6" stop-opacity=".08"/><stop offset="1" stop-opacity=".55"/></radialGradient>
    <radialGradient id="dmkf-schein"><stop offset="0" class="dmk-glut" stop-opacity=".4"/><stop offset="1" class="dmk-glut" stop-opacity="0"/></radialGradient></defs>
    <rect width="${WW}" height="${HH}" rx="18" class="dmk-fels"/><rect width="${WW}" height="${HH}" rx="18" filter="url(#dmkf-fels)"/>
    ${gaenge}${raeume}${tueren}<circle cx="${cx(hr)}" cy="${cy(hr)}" r="${C*1.25}" fill="url(#dmkf-schein)" class="dmk-glow"/><rect width="${WW}" height="${HH}" rx="18" fill="url(#dmkf-licht)"/></svg>`}
function dmKarte(v,mode){const k=v.karte;if(!k)return '';if(DMK.rid!==v.rid){DMK.rid=v.rid;DMK.wo=null;DMK.gesehen=null}const gin=k.gewoelbe?k.gewoelbe.name:'';if(gin!==DMK.gin){DMK.gin=gin;if(gin)DMK.tab=''}DMK.k=k;DMK.mode=mode;DMK.titel=v.titel||'';setTimeout(dmkMerk,1500);setTimeout(dmkNach,0);const g=k.gewoelbe,tab=g&&DMK.tab!=='welt'?'gw':'welt';
  const seg=g?`<div class="lseg dmk-seg"><button type="button" class="${tab==='welt'?'on':''}" data-dmktab="welt">${esc(t('Welt','World'))}</button><button type="button" class="${tab==='gw'?'on':''}" data-dmktab="gw">${esc(t('Gewölbe','Vault'))}</button></div>`:'';
  const head=tab==='gw'?`<small class="mut">📍 ${esc(g.name)}${((g.raeume.find(r=>r.id===g.hier)||{}).n)?' · '+esc(g.raeume.find(r=>r.id===g.hier).n):''} · ${g.zahl} ${esc(t('Räume','rooms'))}${g.geschafft?' · ✓ '+esc(t('bezwungen','conquered')):''}</small>`:`<small class="mut">📍 ${esc(t('Ihr seid in ','You are at ')+((k.orte.find(o=>o.id===k.hier)||{}).n||''))} · ${k.gesehen} ${esc(t(k.gesehen===1?'Ort besucht':'Orte besucht',k.gesehen===1?'place visited':'places visited'))}</small>`;
  const q=k.raetsel?`<div class="dmk-raetsel"><small class="mut">${esc(t('Inschrift','Inscription'))}</small><p>„${esc(k.raetsel.frage)}“</p><small class="mut">${esc(k.raetsel.fertig?'✓ '+t('Gelöst','Solved'):t('Die Antwort steht einfach in eurer Aktion.','Just put the answer in your action.')+' '+t('Versuch','Try')+' '+Math.min(k.raetsel.versuche+1,k.raetsel.max)+'/'+k.raetsel.max)}</small>${k.raetsel.hinweis?`<small class="dmk-hint">💡 ${esc(k.raetsel.hinweis)}</small>`:''}</div>`:'';
  const zu=k.zu?`<small class="mut dmk-zu">🔒 ${esc(k.zu)}</small>`:'';
  const bleibt=tab!=='gw'&&k.bleibt?`<small class="mut dmk-zu">⚠ ${esc(t('Ort nicht gewechselt: „'+k.bleibt+'“ ist noch nicht erreicht, wählt den Weg unter „Von hier aus“.','Place not changed: '+k.bleibt+' is not reached yet, pick the way under „From here“.'))}</small>`:'';
  const open=v.status!=='ende'&&v.ich&&!v.dm;
  const wege=(k.von_hier||[]).length?`<h5>${esc(t('Von hier aus','From here'))}</h5><div class="dm-pills dmk-wege">${k.von_hier.map(w=>`<button type="button" class="b" data-dmkweg="${esc(w.b||w.id[0]==='o'?w.n:'')}" data-dmkr="${esc(w.r)}" data-dmkid="${esc(w.id)}"${open?'':' disabled'}>${esc((w.r?w.r+': ':'')+w.n)}${w.b?' ✓':''}</button>`).join('')}</div>`:'';
  const host=mode==='p'&&v.gastgeber&&v.status!=='ende'&&(k.neu||k.gw_knopf)?`<div class="dm-hostb">${k.gw_knopf?`<button type="button" class="b" data-dmkarte="gewoelbe"${v.dm?' disabled':''}>${esc(t('🎲 Gewölbe würfeln','🎲 Roll a vault'))}</button>`:''}${k.neu?`<button type="button" class="b" data-dmkarte="neu"${v.dm?' disabled':''}>${esc(t('↻ Karte neu würfeln','↻ Roll the map again'))}</button>`:''}</div>`:'';
  return `<div class="dmk${DMK.gross?' gross':''}"><div class="dmk-kopf"><h5>${esc(t('Karte','Map'))}</h5>${seg}<button type="button" class="ic-ib dmk-gross" data-dmkgross="1" title="${esc(t('Karte groß','Large map'))}" aria-label="${esc(t('Karte groß','Large map'))}">⤢</button></div>${head}
    ${tab==='gw'?dmkGewoelbe(g):dmkWelt(k,0,true)}${tab==='gw'?q+zu:bleibt}${wege}${host}</div>`}
// what the last drawing showed: where the flag stood, which places were known (the next change moves from there)
function dmkMerk(){const k=DMK.k;if(!k)return;const h=k.orte.find(o=>o.id===k.hier);if(h)DMK.wo=[h.x,h.y];DMK.gesehen=new Set(k.orte.map(o=>o.id))}
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
  if(B.dmkarte){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/karte`,{was:B.dmkarte},DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}});
