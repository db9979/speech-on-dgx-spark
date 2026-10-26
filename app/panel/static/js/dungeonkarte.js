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
// what grows around a kind of place (the nearest known place decides, its land l from dungeon_karte.LAND), drawn as small ink signs
function dmkGelaende(k,u,frei){const R=dmkRng(k),b=k.box||[0,0,k.w,k.h],out=[],S=Math.max(.9,u*.75),step=36;
  const nahe=(x,y,d)=>k.orte.some(o=>Math.hypot(o.x-x,o.y-y)<d)||k.wege.some(([x1,y1,x2,y2])=>{const L=Math.hypot(x2-x1,y2-y1)||1,q=Math.max(0,Math.min(1,((x-x1)*(x2-x1)+(y-y1)*(y2-y1))/L/L));return Math.hypot(x1+q*(x2-x1)-x,y1+q*(y2-y1)-y)<d*.5});
  for(let gy=-200;gy<k.h+200;gy+=step)for(let gx=-300;gx<k.w+300;gx+=step){const x=gx+R()*step,y=gy+R()*step,roll=R(),s=S*(.85+R()*.4);
    if(x<b[0]||x>b[0]+b[2]||y<b[1]||y>b[1]+b[3]||roll<.35)continue;
    if(nahe(x,y,30*S+18)||dmkNass(k,x,y,14*S)||frei.some(q=>x>q[0]-8*S&&x<q[2]+8*S&&y>q[1]-4*S&&y<q[3]+14*S))continue;
    let best=null,bd=1e9;for(const o of k.orte){const d=Math.hypot(o.x-x,o.y-y);if(d<bd){bd=d;best=o}}
    const art=bd<200&&best?best.l||(roll<.5?'gras':roll<.8?'huegel':'wald'):roll<.5?'gras':roll<.72?'huegel':'wald';
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
// the faction's arms on its banner (dungeonwappen.js, D&D-Idee 10: a checked SVG as an image, which runs nothing); a plain disc without them
function dmkWappen(fr,u){const h=typeof dmWappenHref==='function'?dmWappenHref(DMK.v,dmWappenCode(DMK.v,fr)):'';
  return h?`<image href="${esc(h)}" x="${-4.6*u}" y="${-11.8*u}" width="${9.2*u}" height="${11*u}" class="dmk-wappenbild"/>`:`<circle cy="${-5*u}" r="${2.4*u}" class="dmk-wappen"/>`}
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
    return `<g class="dmk-ort${o.s===2?' on':''}${hier?' hier':''}${neu.includes(o)?' dmk-auf':''}">${hier?`<circle cx="${o.x}" cy="${o.y}" r="${R+7*u}" class="dmk-schein"/>`:''}<circle cx="${o.x}" cy="${o.y}" r="${R}" class="dmk-c"/><circle cx="${o.x}" cy="${o.y}" r="${R-2.6*u}" class="dmk-ring"/>${o.b?`<clipPath id="dmkc-${o.id}"><circle cx="${o.x}" cy="${o.y}" r="${R-1.5*u}"/></clipPath><image data-dmkb="${esc(o.b)}"${dmkHref(o.b)} x="${o.x-R}" y="${o.y-R}" width="${2*R}" height="${2*R}" preserveAspectRatio="xMidYMid slice" clip-path="url(#dmkc-${o.id})" class="dmk-bild"/>`:`<text x="${o.x}" y="${o.y+5*u}" class="dmk-z">${esc(o.z)}</text>`}${o.gw?`<g transform="translate(${o.x+R*.85},${o.y-R*.85})"><circle r="${6.5*u}" class="dmk-gwk"/><text y="${3*u}" class="dmk-gw">⚔</text></g>`:''}${o.fr?`<g transform="translate(${(o.x-R-8*u).toFixed(1)},${(o.y+2*u).toFixed(1)})" class="dmk-banner"><title>${esc(t('Besetzt von ','Held by ')+o.fr)}</title><path d="M${-7*u},${-13*u}h${14*u}M0,${-13*u}V${-15*u}"/><path d="M${-6*u},${-13*u}h${12*u}v${17*u}l${-6*u},${-4.5*u}l${-6*u},${4.5*u}z" class="dmk-wimpel"/>${dmkWappen(o.fr,u)}</g>`:''}${name}</g>`}).join('');
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
  const tueren=g.gaenge.map(([a,b,s,zu])=>{const A=R[a],B=R[b],mx=(cx(A)+cx(B))/2,my=(cy(A)+cy(B))/2;
    return (A.y===B.y?`<rect x="${mx-5}" y="${my-14}" width="10" height="28" rx="2" class="dmk-tuer"/>`:`<rect x="${mx-14}" y="${my-5}" width="28" height="10" rx="2" class="dmk-tuer"/>`)+(zu?`<text x="${mx}" y="${my+8}" class="dmk-schloss">🔒</text>`:'')}).join('');
  const raeume=g.raeume.map(r=>{const on=r.s===2,sz=r.a==='gang'&&on?50:92,hier=r.id===g.hier,x=cx(r)-sz/2,y=cy(r)-sz/2;
    if(!on)return `<g class="dmk-raum"><rect x="${x}" y="${y}" width="${sz}" height="${sz}" rx="6"/><text x="${cx(r)}" y="${cy(r)+10}" class="dmk-frage">?</text></g>`;
    return `<g class="dmk-raum on${hier?' hier':''}${r.f?'':' offen'}"><rect x="${x-6}" y="${y-6}" width="${sz+12}" height="${sz+12}" rx="8" class="dmk-wand"/><rect x="${x}" y="${y}" width="${sz}" height="${sz}" rx="4" class="dmk-boden"/>${DMK_TON[r.a]?`<rect x="${x}" y="${y}" width="${sz}" height="${sz}" rx="4" class="dmk-ton ${DMK_TON[r.a]}"/>`:''}
      ${r.b?`<clipPath id="dmkc-${r.id}"><rect x="${x+3}" y="${y+3}" width="${sz-6}" height="${sz-6}" rx="3"/></clipPath><image data-dmkb="${esc(r.b)}"${dmkHref(r.b)} x="${x}" y="${y}" width="${sz}" height="${sz}" preserveAspectRatio="xMidYMid slice" clip-path="url(#dmkc-${r.id})" class="dmk-bild"/>`:`<text x="${cx(r)}" y="${cy(r)+(sz>60?4:10)}" class="dmk-z">${esc(r.z||DMK_ART[r.a]||'')}</text>`}
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
// the vault as a hand-drawn plan (Dominik 2026-10-25, idea 17), the look of the One-Page Dungeons: ink walls on paper,
// crosshatching in the rock around them, a dotted grid, things drawn into the rooms, numbers and a key below. The
// crosshatch follows benjcooley/dungeongen (MIT, © 2024 Benjamin Cooley): Poisson-spread clusters of three parallel
// strokes, each turned away from its neighbours and cut where it meets one of theirs. The torch look stays one tap away.
function dmpRng(s){let h=2166136261;for(const c of s)h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;
  return ()=>{h=h+0x6D2B79F5>>>0;let x=Math.imul(h^h>>>15,h|1);x^=x+Math.imul(x^x>>>7,x|61);return((x^x>>>14)>>>0)/4294967296}}
function dmpLook(){if(!DMK.look)try{DMK.look=localStorage.getItem('dm-gwlook')||''}catch(e){}return DMK.look==='fackel'?'fackel':'plan'}
function dmpSchnitt(a,b){const r=[a[2]-a[0],a[3]-a[1]],s=[b[2]-b[0],b[3]-b[1]],d=r[0]*s[1]-r[1]*s[0];if(Math.abs(d)<1e-9)return null;
  const qx=b[0]-a[0],qy=b[1]-a[1],t=(qx*s[1]-qy*s[0])/d,u=(qx*r[1]-qy*r[0])/d;return t>=0&&t<=1&&u>=0&&u<=1?t:null}
function dmpSchraffur(boxes,B,R){const sp=6,rd=sp*2,L=rd*2,minL=L*.35,X0=Math.min(...boxes.map(b=>b[0]))-B,Y0=Math.min(...boxes.map(b=>b[1]))-B,X1=Math.max(...boxes.map(b=>b[2]))+B,Y1=Math.max(...boxes.map(b=>b[3]))+B;
  const weg=(x,y)=>{let m=1e9;for(const b of boxes){const dx=Math.max(b[0]-x,0,x-b[2]),dy=Math.max(b[1]-y,0,y-b[3]);if(!dx&&!dy)return -1;m=Math.min(m,Math.hypot(dx,dy))}return m};
  const cs=rd/Math.SQRT2,gw=Math.ceil((X1-X0)/cs)+1,gh=Math.ceil((Y1-Y0)/cs)+1,grid=new Int32Array(gw*gh).fill(-1),pts=[],act=[];
  const frei=(x,y)=>{if(x<X0||y<Y0||x>X1||y>Y1)return false;const gx=(x-X0)/cs|0,gy=(y-Y0)/cs|0;
    for(let j=Math.max(0,gy-2);j<=Math.min(gh-1,gy+2);j++)for(let i=Math.max(0,gx-2);i<=Math.min(gw-1,gx+2);i++){const p=grid[j*gw+i];if(p>=0&&Math.hypot(pts[p][0]-x,pts[p][1]-y)<rd)return false}return true};
  const add=(x,y)=>{grid[((y-Y0)/cs|0)*gw+((x-X0)/cs|0)]=pts.length;act.push(pts.length);pts.push([x,y])};
  add(X0+R()*(X1-X0),Y0+R()*(Y1-Y0));
  while(act.length){const k=R()*act.length|0,[px,py]=pts[act[k]];let neu=false;
    for(let n=0;n<30&&!neu;n++){const a=R()*6.2832,r=rd*(1+R()),x=px+Math.cos(a)*r,y=py+Math.sin(a)*r;if(frei(x,y)){add(x,y);neu=true}}if(!neu)act.splice(k,1)}
  const C=pts.filter(([x,y])=>{const d=weg(x,y);return d>0&&d<=B}).map(p=>({p,a:0,s:[]})),mx=(X0+X1)/2,my=(Y0+Y1)/2;
  C.forEach((c,i)=>{const nb=C.slice(0,i).filter(o=>Math.hypot(o.p[0]-c.p[0],o.p[1]-c.p[1])<=rd*1.5).map(o=>o.a);c.a=R()*6.2832;
    for(let n=0;n<20;n++){const a=R()*6.2832;if(!nb.some(b=>Math.abs(Math.cos(a-b))>.9)){c.a=a;break}}});
  const fertig=[];
  for(const c of C.slice().sort((a,b)=>Math.hypot(a.p[0]-mx,a.p[1]-my)-Math.hypot(b.p[0]-mx,b.p[1]-my))){const ux=Math.cos(c.a),uy=Math.sin(c.a),[px,py]=c.p,
      nah=fertig.filter(o=>Math.hypot(o.p[0]-px,o.p[1]-py)<L*1.3);
    for(let i=0;i<3;i++){const o=(i-1)*sp,h=L/2+(R()*2-1)*.1*L,s=[px+o*uy-ux*h,py-o*ux-uy*h,px+o*uy+ux*h,py-o*ux+uy*h];let t0=0,t1=1;
      for(const n of nah)for(const e of n.s){const t=dmpSchnitt(s,e);if(t!==null){if(t<.5)t0=Math.max(t0,t);else t1=Math.min(t1,t)}}
      if((t1-t0)*Math.hypot(s[2]-s[0],s[3]-s[1])>=minL)c.s.push([s[0]+(s[2]-s[0])*t0,s[1]+(s[3]-s[1])*t0,s[0]+(s[2]-s[0])*t1,s[1]+(s[3]-s[1])*t1])}
    fertig.push(c)}
  return fertig.map(c=>c.s.map(s=>`M${s[0].toFixed(1)},${s[1].toFixed(1)}L${s[2].toFixed(1)},${s[3].toFixed(1)}`).join('')).join('')}
function dmpGlatt(p){const n=p.length,f=v=>v.toFixed(1);let d=`M${f(p[0][0])},${f(p[0][1])}`;
  for(let i=0;i<n;i++){const a=p[(i-1+n)%n],b=p[i],c=p[(i+1)%n],e=p[(i+2)%n];d+=`C${f(b[0]+(c[0]-a[0])/6)},${f(b[1]+(c[1]-a[1])/6)} ${f(c[0]-(e[0]-b[0])/6)},${f(c[1]-(e[1]-b[1])/6)} ${f(c[0])},${f(c[1])}`}return d+'Z'}
function dmpSaeule(x,y,r){return `<circle cx="${x}" cy="${y}" r="${r}" class="dmp-ding"/><circle cx="${x}" cy="${y}" r="${(r*.45).toFixed(1)}" class="dmp-fein"/>`}
function dmpFels(x,y,r,R){return `<path d="${dmpGlatt([...Array(6)].map((_,i)=>{const a=i/6*6.2832+R(),f=r*(.7+R()*.5);return [x+Math.cos(a)*f,y+Math.sin(a)*f]}))}" class="dmp-ding"/>`}
const dmpFass=(a,b)=>`<circle cx="${a}" cy="${b}" r="6.5" class="dmp-ding"/><path d="M${a-6.5},${b}h13M${a},${b-6.5}v13" class="dmp-fein"/>`;
const dmpKiste=(a,b,s=13)=>`<rect x="${a-s/2}" y="${b-s/2}" width="${s}" height="${s}" class="dmp-ding"/><path d="M${a-s/2},${b-s/2}l${s},${s}M${a+s/2},${b-s/2}l${-s},${s}" class="dmp-fein"/>`;
const dmpBett=(a,b)=>`<rect x="${a-8}" y="${b-14}" width="16" height="28" class="dmp-ding"/><rect x="${a-5}" y="${b-11}" width="10" height="6" class="dmp-fein"/>`;
const dmpReihe=(x0,y0,w,h,n,quer)=>{let d='';for(let i=1;i<n;i++)d+=quer?`M${(x0+w*i/n).toFixed(1)},${y0}v${h}`:`M${x0},${(y0+h*i/n).toFixed(1)}h${w}`;return `<rect x="${x0}" y="${y0}" width="${w}" height="${h}" class="dmp-ding"/><path d="${d}" class="dmp-fein"/>`};
const dmpSarg=(X,Y)=>`<path d="M${X-6},${Y-17}L${X+6},${Y-17}L${X+10},${Y-9}L${X+6},${Y+17}L${X-6},${Y+17}L${X-10},${Y-9}Z" class="dmp-ding"/><path d="M${X},${Y-12}v22M${X-5},${Y-5}h10" class="dmp-fein"/>`;
const dmpPodest=({x,y,w,h})=>{const i=15;return `<rect x="${x+i}" y="${y+i}" width="${w-2*i}" height="${h-2*i}" class="dmp-fein"/><rect x="${x+i+5}" y="${y+i+5}" width="${w-2*i-10}" height="${h-2*i-10}" class="dmp-fein"/>`+[[x+i,y+i],[x+w-i,y+i],[x+i,y+h-i],[x+w-i,y+h-i]].map(([a,b])=>dmpSaeule(a,b,7)).join('')};
const dmpKern=(X,Y,o)=>`<circle cx="${X}" cy="${Y}" r="${o}" class="dmp-ding"/><circle cx="${X}" cy="${Y}" r="${o*.6}" class="dmp-fein"/><path d="M${X},${Y-o*.6}v${-o*.4}M${X-o*.52},${Y+o*.3}l${-o*.35},${o*.2}M${X+o*.52},${Y+o*.3}l${o*.35},${o*.2}" class="dmp-fein"/><circle cx="${X}" cy="${Y}" r="${o*.2}" class="dmp-dunkel"/>`;
// the rooms of the room table by their id, so a library looks like one; a room the admin added gets the drawing of its kind
const DMP_RAUM={
  kammer:({X,Y,x,y,w,h})=>`<rect x="${X-12}" y="${Y-8}" width="24" height="16" class="dmp-ding"/>`+[[x+w-16,y+16],[x+16,y+h-16],[x+w-16,y+h-16]].map(([a,b])=>`<circle cx="${a}" cy="${b}" r="4.5" class="dmp-ding"/><circle cx="${a}" cy="${b}" r="1.6" class="dmp-dunkel"/>`).join(''),
  halle:({x,y,w,h})=>[.32,.54,.76].flatMap(f=>[[x+w*f,y+h*.32],[x+w*f,y+h*.72]]).map(([a,b])=>dmpSaeule(a.toFixed(1),b.toFixed(1),5.5)).join(''),
  brunnen:({X,Y})=>`<circle cx="${X}" cy="${Y}" r="17" class="dmp-ding"/><circle cx="${X}" cy="${Y}" r="11" class="dmp-wasser"/><path d="M${X-17},${Y}h-6M${X+17},${Y}h6" class="dmp-fein"/>`,
  waffenkammer:({x,y,w,h})=>dmpReihe(x+30,y+h-16,w-44,8,6,true)+dmpReihe(x+w-16,y+30,8,h-52,4,false),
  bibliothek:({X,Y,x,y,w,h})=>dmpReihe(x+30,y+7,w-37,9,5,true)+dmpReihe(x+w-16,y+22,9,h-30,4,false)+`<rect x="${X-12}" y="${Y-3}" width="22" height="13" class="dmp-ding"/><circle cx="${X-1}" cy="${Y+18}" r="4" class="dmp-ding"/>`,
  gefaengnis:({x,y,w,h})=>{const c=(w-14)/3;let d='';for(let i=0;i<=3;i++)d+=`M${(x+7+c*i).toFixed(1)},${y+h-7}v-26`;return `<path d="${d}" class="dmp-ding"/><path d="M${x+7},${y+h-33}h${w-14}" class="dmp-gitterstab"/>`},
  pilze:({x,y,w,h,R})=>[...Array(6)].map((_,i)=>{const a=x+18+R()*(w-30),b=y+30+R()*(h-40),o=3+R()*3.5;return `<circle cx="${a.toFixed(1)}" cy="${b.toFixed(1)}" r="${o.toFixed(1)}" class="dmp-ding"/><circle cx="${a.toFixed(1)}" cy="${b.toFixed(1)}" r="1.2" class="dmp-dunkel"/>`}).join(''),
  gebeine:q=>dmpSarg(q.X-14,q.Y)+dmpSarg(q.X+14,q.Y)+dmpFels(q.x+q.w-18,q.y+q.h-16,5,q.R),
  kinderzimmer:({X,Y,x,y,w,h})=>dmpBett(x+w-18,Y)+dmpKiste(x+20,y+h-18)+`<circle cx="${X-4}" cy="${Y+4}" r="13" class="dmp-fein"/>`,
  speisesaal:({X,Y,w})=>{const tw=w*.56;let s=`<rect x="${X-tw/2}" y="${Y-8}" width="${tw}" height="16" class="dmp-ding"/>`;for(let i=0;i<4;i++){const a=X-tw/2+tw*(i+.5)/4-3;s+=`<rect x="${a.toFixed(1)}" y="${Y-17}" width="6" height="6" class="dmp-ding"/><rect x="${a.toFixed(1)}" y="${Y+11}" width="6" height="6" class="dmp-ding"/>`}return s},
  spiegelsaal:({x,y,w,h})=>[[x+w-12,y+28],[x+w-12,y+h/2+8],[x+32,y+h-12],[x+w/2+10,y+h-12]].map(([a,b],i)=>i<2?`<rect x="${a-2}" y="${b-10}" width="4" height="20" class="dmp-wasser"/>`:`<rect x="${a-10}" y="${b-2}" width="20" height="4" class="dmp-wasser"/>`).join(''),
  kryo:({X,Y})=>[-20,0,20].map(o=>`<rect x="${X+o-7}" y="${Y-15}" width="14" height="30" rx="7" class="dmp-ding"/><path d="M${X+o-3},${Y-8}v16M${X+o+3},${Y-8}v16" class="dmp-fein"/>`).join(''),
  reaktor:({X,Y})=>dmpKern(X,Y,21),
  bruecke_s:({X,Y,x,y,w})=>[.42,.62,.82].map(f=>`<rect x="${(x+w*f-8).toFixed(1)}" y="${y+8}" width="16" height="9" class="dmp-ding"/>`).join('')+`<path d="M${X-24},${Y+8}q24,-26 48,0" class="dmp-fein"/><circle cx="${X}" cy="${Y+12}" r="6" class="dmp-ding"/>`,
  schacht:({X,Y})=>`<rect x="${X-10}" y="${Y-10}" width="20" height="20" class="dmp-grube"/><path d="M${X-5},${Y-10}v20M${X},${Y-10}v20M${X+5},${Y-10}v20" class="dmp-fein"/>`,
  schleuse:({X,Y})=>`<path d="M${X-7},${Y-15}v30M${X+7},${Y-15}v30" class="dmp-schleuse"/>`,
  kombuese:({X,Y,x,y,w,h})=>`<rect x="${X-11}" y="${Y-11}" width="22" height="22" class="dmp-ding"/><circle cx="${X-4}" cy="${Y-3}" r="3.5" class="dmp-fein"/><circle cx="${X+4}" cy="${Y+4}" r="3.5" class="dmp-fein"/>`+dmpFass(x+w-16,y+h-16)+dmpFass(x+w-30,y+h-14),
  pulver:({x,y,w,h})=>[[x+w-16,y+16],[x+w-30,y+18],[x+w-17,y+31],[x+18,y+h-16],[x+32,y+h-15],[x+w-16,y+h-17]].map(([a,b])=>dmpFass(a,b)).join(''),
  kapitaen:({X,Y,x,w})=>`<rect x="${X-15}" y="${Y-10}" width="30" height="20" class="dmp-ding"/><rect x="${X-10}" y="${Y-6}" width="20" height="12" class="dmp-fein"/>`+dmpBett(x+w-16,Y),
  unterwasser:({x,y,w,h})=>`<rect x="${x+3}" y="${y+3}" width="${w-6}" height="${h-6}" class="dmp-wasser"/><path d="M${x+8},${y+h*.4}q${w/4-4},-5 ${w/2-8},0t${w/2-8},0M${x+8},${y+h*.7}q${w/4-4},-5 ${w/2-8},0t${w/2-8},0" class="dmp-welle"/>`,
  treppe:({X,Y})=>`<rect x="${X-12}" y="${Y-12}" width="24" height="24" class="dmp-ding"/><path d="M${X-12},${Y-6}h24M${X-12},${Y}h24M${X-12},${Y+6}h24" class="dmp-fein"/>`,
  quelle_s:({X,Y,x,w})=>dmpBett(x+w*.3,Y+4)+dmpBett(x+w*.7,Y+4)+`<path d="M${X},${Y-32}v12M${X-6},${Y-26}h12" class="dmp-kreuz"/>`,
  schatz_s:({X,Y})=>dmpKiste(X-8,Y-8)+dmpKiste(X+8,Y-8)+dmpKiste(X-8,Y+8)+dmpKiste(X+10,Y+10,10),
  waechter_s:({X,Y,w})=>dmpSaeule(X-w*.3,Y,6)+dmpSaeule(X+w*.3,Y,6)+`<circle cx="${X}" cy="${Y}" r="9" class="dmp-ding"/><circle cx="${X}" cy="${Y}" r="3" class="dmp-dunkel"/>`,
  boss_s:q=>dmpPodest(q)+dmpKern(q.X,q.Y+4,17),
  boss_p:q=>dmpPodest(q)+DMP_RAUM.brunnen({X:q.X,Y:q.Y+4}),
  altar_s:({X,Y})=>dmpKern(X,Y,15)};
// what stands in a room, by its kind: the panel decides the kind, this only draws it
function dmpDinge(r,q){const {x,y,w,h,R}=q,X=x+w/2,Y=y+h/2,m=Math.min(w,h);
  if(DMP_RAUM[r.t])return DMP_RAUM[r.t]({...q,X,Y});
  if(r.a==='eingang'){const sw=w*.46,sh=h*.32,sx=X-sw/2,sy=y+h-sh-8;let d='';for(let i=1;i<6;i++)d+=`M${sx},${(sy+sh*i/6).toFixed(1)}h${sw.toFixed(1)}`;
    return `<rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" class="dmp-ding"/><path d="${d}" class="dmp-fein"/>`}
  if(r.a==='quelle'){const p=[...Array(14)].map((_,i)=>{const a=i/14*6.2832,f=.82+R()*.3;return [X+Math.cos(a)*w*.3*f,Y+Math.sin(a)*h*.28*f]}),z=k=>p.map(([a,b])=>[X+(a-X)*k,Y+(b-Y)*k]);
    return `<path d="${dmpGlatt(p)}" class="dmp-wasser"/><path d="${dmpGlatt(z(.68))}" class="dmp-welle"/><path d="${dmpGlatt(z(.38))}" class="dmp-welle"/>`}
  if(r.a==='falle'){const a=m*.22;let d='';for(let c=-2*a+7;c<2*a;c+=7){const x1=Math.max(-a,-a+c),x2=Math.min(a,a+c);if(x2>x1)d+=`M${(X+x1).toFixed(1)},${(Y+x1-c).toFixed(1)}L${(X+x2).toFixed(1)},${(Y+x2-c).toFixed(1)}`}
    return `<rect x="${X-a}" y="${Y-a}" width="${2*a}" height="${2*a}" class="dmp-grube"/><path d="${d}" class="dmp-fein"/>`}
  if(r.a==='raetsel'){const o=m*.27;let d='';for(let i=0;i<10;i++){const a=i/10*6.2832,c=Math.cos(a),s=Math.sin(a);d+=`M${(X+c*o*.74).toFixed(1)},${(Y+s*o*.74).toFixed(1)}L${(X+c*o*.92).toFixed(1)},${(Y+s*o*.92).toFixed(1)}`}
    return `<circle cx="${X}" cy="${Y}" r="${o}" class="dmp-ding"/><circle cx="${X}" cy="${Y}" r="${(o*.66).toFixed(1)}" class="dmp-fein"/><path d="${d}" class="dmp-fein"/><path d="M${X},${Y-7}l6,7l-6,7l-6,-7z" class="dmp-dunkel"/>`}
  if(r.a==='schatz'){const t=(R()*30-15).toFixed(0),c=[[-15,14],[-9,18],[13,15],[18,9]].slice(0,2+(R()*3|0)).map(([a,b])=>`<circle cx="${X+a}" cy="${Y+b}" r="3" class="dmp-ding"/>`).join('');
    return `<g transform="rotate(${t} ${X} ${Y})"><rect x="${X-14}" y="${Y-10}" width="28" height="18" class="dmp-ding"/><path d="M${X-14},${Y-4}h28" class="dmp-fein"/><rect x="${X-3}" y="${Y-6}" width="6" height="5" class="dmp-dunkel"/></g>${c}`}
  if(r.a==='altar')return `<rect x="${X-22}" y="${Y-14}" width="44" height="28" class="dmp-fein"/><rect x="${X-16}" y="${Y-8}" width="32" height="16" class="dmp-ding"/><circle cx="${X-11}" cy="${Y}" r="2.5" class="dmp-dunkel"/><circle cx="${X+11}" cy="${Y}" r="2.5" class="dmp-dunkel"/>`;
  if(r.a==='waechter')return dmpSaeule(X-w*.3,Y,6)+dmpSaeule(X+w*.3,Y,6)+`<rect x="${X-9}" y="${Y-9}" width="18" height="18" class="dmp-ding"/><rect x="${X-4}" y="${Y-4}" width="8" height="8" class="dmp-dunkel"/>`;
  if(r.a==='boss')return dmpPodest(q)+`<rect x="${X-10}" y="${y+25}" width="20" height="16" class="dmp-ding"/><rect x="${X-12}" y="${y+22}" width="24" height="5" class="dmp-dunkel"/>`;
  if(r.a==='kammer'){const v=R()*4|0;
    if(v===0)return [...Array(2+(R()*3|0))].map((_,i)=>dmpFels(x+30+R()*(w-40),i%2?y+10+R()*12:y+h-10-R()*12,5+R()*4,R)).join('');
    if(v===1)return `<g transform="rotate(${R()<.5?0:90} ${X} ${Y})">${dmpSarg(X,Y)}</g>`;
    if(v===2)return [[x+16,y+h-16],[x+30,y+h-15],[x+17,y+h-30]].slice(0,2+(R()*2|0)).map(([a,b])=>dmpFass(a,b)).join('')}
  return ''}
function dmpRaum(g,r,cx,cy){const R=dmpRng(g.name+r.id),w=r.s!==2?84:r.a==='gang'?44:r.a==='boss'?104:76+4*(R()*7|0),h=r.s!==2?84:r.a==='gang'?44:r.a==='boss'?104:76+4*(R()*7|0);
  return {x:cx-w/2,y:cy-h/2,w,h,R}}
function dmpPlan(g,stil){const C=120,pad=52,B=24,R={},Q={};
  g.raeume.forEach(r=>{R[r.id]=r;Q[r.id]=dmpRaum(g,r,pad+r.x*C+C/2,pad+r.y*C+C/2)});const cx=id=>Q[id].x+Q[id].w/2,cy=id=>Q[id].y+Q[id].h/2,G=13;
  const gang=g.gaenge.map(([a,b,s,zu])=>{const H=R[a].y===R[b].y,x=Math.min(cx(a),cx(b)),y=Math.min(cy(a),cy(b));return H?[x,cy(a)-G,Math.max(cx(a),cx(b)),cy(a)+G,s,a,b,H,zu]:[cx(a)-G,y,cx(a)+G,Math.max(cy(a),cy(b)),s,a,b,H,zu]});
  const on=g.raeume.filter(r=>r.s===2),boxes=on.map(r=>{const q=Q[r.id];return [q.x,q.y,q.x+q.w,q.y+q.h]}).concat(gang.map(e=>e.slice(0,4))),key=g.name+JSON.stringify(boxes);
  const S=DMK.schraffur||(DMK.schraffur={});if(!(key in S))S[key]=dmpSchraffur(boxes,B,dmpRng(g.name));
  const rect=([x0,y0,x1,y1],c,e=0)=>`<rect x="${x0-e}" y="${y0-e}" width="${x1-x0+2*e}" height="${y1-y0+2*e}"${e?` rx="${e*.7}"`:''} class="${c}"/>`;
  const flaeche=c=>boxes.map(b=>rect(b,c)).join('');
  const tueren=gang.map(([x0,y0,x1,y1,s,a,b,H,zu])=>{const [p,n]=(H?cx(a)<cx(b):cy(a)<cy(b))?[Q[a],Q[b]]:[Q[b],Q[a]],mx=H?(p.x+p.w+n.x)/2:(x0+x1)/2,my=H?(y0+y1)/2:(p.y+p.h+n.y)/2;return (H?`<rect x="${mx-4.5}" y="${my-G-3}" width="9" height="${2*G+6}" class="dmp-tuer${s===2?' on':''}"/>`:`<rect x="${mx-G-3}" y="${my-4.5}" width="${2*G+6}" height="9" class="dmp-tuer${s===2?' on':''}"/>`)
    +(zu?`<g transform="translate(${mx},${my})" class="dmp-schloss"><path d="M-4,-2v-4a4,4 0 0 1 8,0v4"/><rect x="-6.5" y="-2" width="13" height="10" rx="1.5"/></g>`:'')}).join('');
  const fremd=g.raeume.filter(r=>r.s!==2).map(r=>{const q=Q[r.id];return `<rect x="${q.x}" y="${q.y}" width="${q.w}" height="${q.h}" class="dmp-unbekannt"/><text x="${q.x+q.w/2}" y="${q.y+q.h/2+11}" class="dmp-frage">?</text>`}).join('');
  const dinge=on.map(r=>{const q=Q[r.id],n=r.id.slice(1),hier=r.id===g.hier;const X=q.x+q.w/2,Y=q.y+q.h/2,d=dmpDinge(r,q);return `<g class="dmp-raum${r.f?'':' offen'}">${r.a==='gang'&&d?`<g transform="translate(${X+4},${Y+5}) scale(.62) translate(${-X},${-Y})">${d}</g>`:d}<text x="${r.a==='gang'?q.x+4:q.x+(r.a==='boss'?2:11)}" y="${r.a==='gang'?q.y+15:r.a==='boss'?q.y+q.h/2+7:q.y+22}" class="dmp-nr${r.a==='gang'?' klein':''}">${n}</text>`
    +(hier?`<rect x="${q.x-10}" y="${q.y-10}" width="${q.w+20}" height="${q.h+20}" rx="8" class="dmp-hier"/><g transform="translate(${r.a==='boss'?q.x+q.w/2:q.x+q.w-(r.a==='gang'?22:17)},${r.a==='boss'?q.y+q.h/2+14:r.a==='gang'?q.y+q.h-22:q.y+17})" class="dmp-figur"><circle r="9"/><circle r="3.5" cy="-1"/></g>`:'')+'</g>'}).join('');
  const all=boxes.concat(g.raeume.filter(r=>r.s!==2).map(r=>{const q=Q[r.id];return [q.x,q.y,q.x+q.w,q.y+q.h]})),m=B+14,
    vx=Math.min(...all.map(b=>b[0]))-m,vy=Math.min(...all.map(b=>b[1]))-m,vw=Math.max(...all.map(b=>b[2]))+m-vx,vh=Math.max(...all.map(b=>b[3]))+m-vy;
  return `<svg viewBox="${vx.toFixed(0)} ${vy.toFixed(0)} ${vw.toFixed(0)} ${vh.toFixed(0)}" class="dmk-svg dmp ${stil}" role="img" aria-label="${esc(t('Plan des Gewölbes','Plan of the vault'))}"><defs>
    <pattern id="dmpf-raster" width="20" height="20" patternUnits="userSpaceOnUse" x="${pad}" y="${pad}"><path d="M0,0H20M0,0V20" class="dmp-raster"/></pattern></defs>
    <rect x="${vx}" y="${vy}" width="${vw}" height="${vh}" rx="14" class="dmp-papier"/>${boxes.map(b=>rect(b,'dmp-schatten',B)).join('')}<path d="${S[key]}" class="dmp-strich"/>
    ${flaeche('dmp-wand')}${flaeche('dmp-boden')}${flaeche('dmp-gitter')}${fremd}${tueren}${dinge}<rect x="${vx+5}" y="${vy+5}" width="${vw-10}" height="${vh-10}" rx="10" class="dmp-rahmen"/></svg>`}
function dmpLegende(g){const on=g.raeume.filter(r=>r.s===2&&r.n).sort((a,b)=>a.id.slice(1)-b.id.slice(1));
  return on.length?`<div class="dmp-legende">${on.map(r=>`<span${r.id===g.hier?' class="on"':''}><b>${r.id.slice(1)}</b> ${esc(r.n)}</span>`).join('')}</div>`:''}
function dmKarte(v,mode){const k=v.karte;if(!k)return '';if(DMK.rid!==v.rid){DMK.rid=v.rid;DMK.wo=null;DMK.gesehen=null}const gin=k.gewoelbe?k.gewoelbe.name:'';if(gin!==DMK.gin){DMK.gin=gin;if(gin)DMK.tab=''}DMK.k=k;DMK.v=v;DMK.mode=mode;DMK.titel=v.titel||'';setTimeout(dmkMerk,1500);setTimeout(dmkNach,0);const g=k.gewoelbe,tab=g&&DMK.tab!=='welt'?'gw':'welt';
  const look=dmpLook(),seg=g?`<div class="lseg dmk-seg"><button type="button" class="${tab==='welt'?'on':''}" data-dmktab="welt">${esc(t('Welt','World'))}</button><button type="button" class="${tab==='gw'?'on':''}" data-dmktab="gw">${esc(t('Gewölbe','Vault'))}</button></div>`:'';
  const head=tab==='gw'?`<small class="mut">📍 ${esc(g.name)}${((g.raeume.find(r=>r.id===g.hier)||{}).n)?' · '+esc(g.raeume.find(r=>r.id===g.hier).n):''} · ${g.zahl} ${esc(t('Räume','rooms'))}${g.geschafft?' · ✓ '+esc(t('bezwungen','conquered')):''}</small>`:`<small class="mut">📍 ${esc(t('Ihr seid in ','You are at ')+((k.orte.find(o=>o.id===k.hier)||{}).n||''))} · ${k.gesehen} ${esc(t(k.gesehen===1?'Ort besucht':'Orte besucht',k.gesehen===1?'place visited':'places visited'))}</small>`;
  const q=k.raetsel?`<div class="dmk-raetsel"><small class="mut">${esc(t('Inschrift','Inscription'))}</small><p>„${esc(k.raetsel.frage)}“</p><small class="mut">${esc(k.raetsel.fertig?'✓ '+t('Gelöst','Solved'):t('Die Antwort steht einfach in eurer Aktion.','Just put the answer in your action.')+' '+t('Versuch','Try')+' '+Math.min(k.raetsel.versuche+1,k.raetsel.max)+'/'+k.raetsel.max)}</small>${k.raetsel.hinweis?`<small class="dmk-hint">💡 ${esc(k.raetsel.hinweis)}</small>`:''}</div>`:'';
  const zu=k.zu?`<small class="mut dmk-zu">🔒 ${esc(k.zu)}</small>`:'';
  // Alarm und Fackeln (dungeon_alarm): the vault's alarm 0-6 and the light, only while the switch is on
  const al=tab==='gw'&&k.alarm!=null?`<small class="mut dmk-zu" data-dmkalarm="${k.alarm}">🔔 ${esc(t('Alarm','Alarm'))} ${k.alarm}/6 · ${k.fackel===0?'🌑 '+esc(t('Dunkel, Proben mit Nachteil ohne Dunkelsicht','Dark, checks at a disadvantage without darkvision')):'🔥 '+esc((k.licht_von||t('Licht','Light'))+(k.fackel>0?': '+k.fackel+' '+t(k.fackel===1?'Raum':'Räume',k.fackel===1?'room':'rooms'):''))}</small>`:'';
  const fr=(k.orte.find(o=>o.id===k.hier)||{}).fr,frz=tab!=='gw'&&fr?`<small class="mut dmk-zu">${typeof dmWappenFr==='function'&&dmWappenFr(v,fr)||'⚑'} ${esc(t('Besetzt von ','Held by ')+fr)}</small>`:'';
  const bleibt=tab!=='gw'&&k.bleibt?`<small class="mut dmk-zu">⚠ ${esc(t('Ort nicht gewechselt: „'+k.bleibt+'“ ist noch nicht erreicht, wählt den Weg unter „Von hier aus“.','Place not changed: '+k.bleibt+' is not reached yet, pick the way under „From here“.'))}</small>`:'';
  const open=v.status!=='ende'&&v.ich&&!v.dm;
  const wege=(k.von_hier||[]).length?`<h5>${esc(t('Von hier aus','From here'))}</h5><div class="dm-pills dmk-wege">${k.von_hier.map(w=>`<button type="button" class="b" data-dmkweg="${esc(w.b||w.id[0]==='o'?w.n:'')}" data-dmkr="${esc(w.r)}" data-dmkid="${esc(w.id)}"${open?'':' disabled'}>${w.zu?'🔒 ':''}${esc((w.r?w.r+': ':'')+w.n)}${w.b?' ✓':''}${w.fr?' ⚑':''}</button>`).join('')}</div>`:'';
  const host=mode==='p'&&v.gastgeber&&v.status!=='ende'&&(k.neu||k.gw_knopf)?`<div class="dm-hostb">${k.gw_knopf?`<button type="button" class="b" data-dmkarte="gewoelbe"${v.dm?' disabled':''}>${esc(t('🎲 Gewölbe würfeln','🎲 Roll a vault'))}</button>`:''}${k.neu?`<button type="button" class="b" data-dmkarte="neu"${v.dm?' disabled':''}>${esc(t('↻ Karte neu würfeln','↻ Roll the map again'))}</button>`:''}</div>`:'';
  return DMK.html=`<div class="dmk${DMK.gross?' gross':''}"><div class="dmk-kopf"><h5>${esc(t('Karte','Map'))}</h5>${seg}${tab==='gw'?`<button type="button" class="ic-ib" data-dmklook="1" title="${esc(look==='plan'?t('Fackelschein','Torchlight'):t('Gezeichneter Plan','Drawn plan'))}" aria-label="${esc(look==='plan'?t('Fackelschein','Torchlight'):t('Gezeichneter Plan','Drawn plan'))}">${look==='plan'?'🔥':'📜'}</button>`:''}<button type="button" class="ic-ib dmk-gross" data-dmkgross="1" title="${esc(t('Karte groß','Large map'))}" aria-label="${esc(t('Karte groß','Large map'))}">⤢</button></div>${head}
    ${tab==='gw'?(look==='plan'?dmpPlan(g,DMK_STIL[k.welt]||'dmk-pergament')+dmpLegende(g):dmkGewoelbe(g)):dmkWelt(k,0,true)}${tab==='gw'?al+q+zu:frz+bleibt}${wege}${host}</div>`}
// what the last drawing showed: where the flag stood, which places were known (the next change moves from there)
function dmkMerk(){const k=DMK.k;if(!k)return;const h=k.orte.find(o=>o.id===k.hier);if(h)DMK.wo=[h.x,h.y];DMK.gesehen=new Set(k.orte.map(o=>o.id))}
function dmkNach(){document.querySelectorAll('.dmk-land').forEach(e=>{const px=e.clientWidth,was=+e.dataset.px;if(DMK.k&&px&&Math.abs(px-was)>was*.15)e.outerHTML=dmkWelt(DMK.k,px)});dmkFill()}
// the pictures of places and rooms (dungeon_dingbild, the same as the items'): a profile loads them itself, a guest's seat as a blob;
// a picture already known is written into the drawing, so a redraw never shows the place without it for a moment
const dmkHref=b=>{const h=DMK.mode==='p'?'/api/profile/dungeon/ding/'+encodeURIComponent(b):(typeof DMI!=='undefined'&&DMI['d'+b])||'';return h?` href="${esc(h)}"`:''};
// the map stays the same node while its drawing is the same (Dominik 2026-10-26 „die karte blinkt immer wieder“): the
// table is written anew on every refresh (dmTable), the map's old node goes back in place of the new one when its HTML
// did not change, with its pictures, its scroll and nothing drawn again
function dmkKeep(w){const old=w.querySelector('.dmk'),h=DMK.html;
  return ()=>{const neu=w.querySelector('.dmk');if(old&&neu&&h&&h===DMK.html&&old!==neu)neu.replaceWith(old)}}
async function dmkFill(){for(const im of document.querySelectorAll('.dmk image[data-dmkb]:not([href])')){const n=im.dataset.dmkb,key='d'+n;
    if(DMK.mode==='p'){im.setAttribute('href','/api/profile/dungeon/ding/'+encodeURIComponent(n));continue}
    if(key in DMI){if(DMI[key])im.setAttribute('href',DMI[key]);continue}DMI[key]='';
    try{const r=await /*raw: a guest seat's picture as a blob, api() would open the login on a 401*/fetch('/api/dungeon/ding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,name:n})});
      if(!r.ok){delete DMI[key];continue}DMI[key]=URL.createObjectURL(await r.blob())}catch(e){delete DMI[key];continue}
    document.querySelectorAll(`.dmk image[data-dmkb="${n}"]`).forEach(x=>x.setAttribute('href',DMI[key]))}}
addEventListener('resize',()=>{clearTimeout(DMK.rz);DMK.rz=setTimeout(dmkNach,200)});
document.body.addEventListener('click',async e=>{const b=e.target.closest('.dmk [data-dmktab],.dmk [data-dmkgross],.dmk [data-dmkid],.dmk [data-dmkarte],.dmk [data-dmklook]');if(!b)return;const B=b.dataset;
  if(B.dmktab){DMK.tab=B.dmktab;if(typeof DG!=='undefined'&&DG.v&&b.closest('#dgcard'))dgDraw();else dmDraw();return}
  if(B.dmklook){DMK.look=dmpLook()==='plan'?'fackel':'plan';try{localStorage.setItem('dm-gwlook',DMK.look)}catch(x){}if(typeof DG!=='undefined'&&DG.v&&b.closest('#dgcard'))dgDraw();else dmDraw();return}
  if(B.dmkgross){DMK.gross=!DMK.gross;b.closest('.dmk').classList.toggle('gross',DMK.gross);setTimeout(dmkNach,0);return}
  if(B.dmkid){const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
    const s=B.dmkid==='aus'?t('Wir verlassen das Gewölbe.','We leave the vault.'):B.dmkid==='ein'?t('Wir gehen ins Gewölbe.','We go into the vault.')
      :B.dmkweg?t('Wir gehen weiter zu „'+B.dmkweg+'“.','We go on to '+B.dmkweg+'.'):t('Wir gehen nach '+B.dmkr+' in den nächsten Raum.','We go '+B.dmkr+' into the next room.');
    ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+s;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus();return}
  if(B.dmkarte){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/karte`,{was:B.dmkarte},DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}});
