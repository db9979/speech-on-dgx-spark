// The assistant's faces (eyes, mouth, moods). The admin picks one for everybody (chat.face, whoami "face"):
// "robot" (the first face) or "comic" (a caricature of Dominik). A new face is one more drawing here,
// one more name in core.FACES and one more option under Einstellungen → Vorgaben.
// ---------------------------------------------------------------- assistant face
// One animation drives both faces (chat tab and the floating button); its mood follows the chat state.
const FACE_SVG=`<svg viewBox="0 0 200 200" aria-hidden="true"><defs><linearGradient id="fhead" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:var(--acc)"/><stop offset="1" style="stop-color:var(--acc2)"/></linearGradient><radialGradient id="fshine" cx=".35" cy=".25" r=".8"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></radialGradient><filter id="fglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><filter id="fsoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter></defs><circle class="fhalo" cx="100" cy="104" r="80" fill="url(#fhead)" opacity=".25" filter="url(#fsoft)"/><circle class="spin" cx="100" cy="104" r="90" fill="none" stroke="url(#fhead)" stroke-width="3" stroke-linecap="round" stroke-dasharray="60 505"/><g class="fbody"><line x1="100" y1="34" x2="100" y2="18" stroke="url(#fhead)" stroke-width="4" stroke-linecap="round"/><circle class="fant" cx="100" cy="15" r="6" style="fill:var(--acc2)" filter="url(#fglow)"/><rect x="26" y="34" width="148" height="136" rx="56" fill="url(#fhead)"/><rect x="26" y="34" width="148" height="136" rx="56" fill="url(#fshine)"/><rect x="18" y="86" width="12" height="34" rx="6" fill="url(#fhead)"/><rect x="170" y="86" width="12" height="34" rx="6" fill="url(#fhead)"/><rect x="44" y="62" width="112" height="82" rx="38" style="fill:var(--visor)"/><g class="fcheeks" opacity=".0"><ellipse cx="62" cy="124" rx="9" ry="5" fill="#ff7aa8" opacity=".55"/><ellipse cx="138" cy="124" rx="9" ry="5" fill="#ff7aa8" opacity=".55"/></g><g class="feyes" filter="url(#fglow)" fill="#bff6ff"><rect class="feyeL" x="66" y="84" width="18" height="24" rx="9"/><rect class="feyeR" x="116" y="84" width="18" height="24" rx="9"/></g><path class="fmouth" d="M86 122 Q100 130 114 122" fill="#bff6ff" stroke="#bff6ff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" filter="url(#fglow)"/></g></svg>`;
// The comic face: one drawing in a 200 × 200 box, the moving parts (iris, lids, brows, mouth,
// mustache, head, ring) are found by data-p and moved every frame. Shapes and colours are the same
// as in the iPhone app (ios/Spark), so both look alike.
const COMIC={skin:'#f0b48c',lid:'#e09d77',shade:'#c9825e',hair:'#2b2626',stache:'#382c27',line:'#22180f',lw:2.6,bg:'#d9e6f5',
  top:36,hw:47,cheekY:92,chinW:23,chinY:167,eyeX:21,eyeY:90,eRx:10.5,eRy:6.5,lidBase:.36,noseLen:29,noseW:10,stacheS:1.06,mouthW:8,
  shirt:'#f6e27a',chain:'#c9cdd2',
  ring:{idle:'#94a3b8',listen:'#3b82f6',think:'#f59e0b',speak:'#22c55e',sad:'#ef4444',
    search:'#f59e0b',calendar:'#f59e0b',mail:'#f59e0b',home:'#f59e0b',memory:'#f59e0b',happy:'#22c55e',error:'#ef4444',sleep:'#94a3b8'}};
// hair tips, fixed so the face never changes between loads
const COMIC_HAIR=[[-6,1],[-12.8,1.31],[-19.7,1],[-26.5,1.19],[-33.3,1],[-40.2,1.33],[-47,1],[-53.8,1.22],[-60.7,1],[-67.5,1.3],[-74.3,1],
  [-81.2,1.2],[-88,1],[-94.8,1.34],[-101.7,1],[-108.5,1.21],[-115.3,1],[-122.2,1.3],[-129,1],[-135.8,1.18],[-142.7,1],[-149.5,1.32],[-156.3,1],[-163.2,1.24],[-170,1]];
function comicSvg(sfx){const s=COMIC,r=n=>Math.round(n*100)/100,m=s.eyeY+s.noseLen+6,mcy=m+15*s.stacheS,L=s.line,lw=s.lw;
  const st=`stroke="${L}" stroke-width="${lw}" stroke-linejoin="round" stroke-linecap="round"`;
  const face=`M100 ${s.top} C${r(100+s.hw*.72)} ${s.top} ${100+s.hw} ${s.top+22} ${100+s.hw} ${s.cheekY} C${100+s.hw} ${s.cheekY+36} ${100+s.chinW+13} ${s.chinY-15} ${100+s.chinW} ${s.chinY-5} Q100 ${s.chinY+6} ${100-s.chinW} ${s.chinY-5} C${100-s.chinW-13} ${s.chinY-15} ${100-s.hw} ${s.cheekY+36} ${100-s.hw} ${s.cheekY} C${100-s.hw} ${s.top+22} ${r(100-s.hw*.72)} ${s.top} 100 ${s.top}Z`;
  const cy=s.top+44,rx=s.hw+4;let hair=`M${100+s.hw+2} ${cy}`;
  for(const[a,k]of COMIC_HAIR)hair+=` L${r(100+Math.cos(a*Math.PI/180)*rx*k)} ${r(cy+Math.sin(a*Math.PI/180)*50*k)}`;
  hair+=` L${100-s.hw-2} ${cy} L${100-s.hw+3} ${s.top+38} Q${r(100-s.hw*.45)} ${s.top+13} 100 ${s.top+18} Q${r(100+s.hw*.45)} ${s.top+13} ${100+s.hw-3} ${s.top+38}Z`;
  // short and bushy, only above the upper lip (Dominik's pick 2026-10-09; was hanging down to the chin)
  const stache=`M100 ${m} C106.33 ${m-2} 115.2 ${m+2} 119 ${m+4.5} C120.9 ${m+6.7} 120.33 ${m+9} 118.43 ${m+10} C116.53 ${m+7.8} 111.4 ${m+11} 105.13 ${m+10} Q100 ${m+8} 94.87 ${m+10} C88.6 ${m+11} 83.47 ${m+7.8} 81.57 ${m+10} C79.67 ${m+9} 79.1 ${m+6.7} 81 ${m+4.5} C84.8 ${m+2} 93.67 ${m-2} 100 ${m}Z`;
  const c=s.chinY,ny=s.eyeY,nl=s.noseLen,nw=s.noseW;
  let o=`<svg viewBox="0 0 200 200" aria-hidden="true"><defs><clipPath id="cc${sfx}"><circle cx="100" cy="100" r="95"/></clipPath>`;
  for(const[k,d]of[[-1,'L'],[1,'R']])o+=`<clipPath id="ce${d}${sfx}"><ellipse cx="${100+k*s.eyeX}" cy="${s.eyeY}" rx="${s.eRx}" ry="${s.eRy}"/></clipPath>`;
  o+=`<clipPath id="cf${sfx}"><path d="${face}"/></clipPath></defs><circle cx="100" cy="100" r="96" fill="${s.bg}"/><g clip-path="url(#cc${sfx})">
<path d="M80 ${c-26} L78 200 L122 200 L120 ${c-26}Z" fill="${s.skin}" ${st}/>
<path d="M0 200 L0 ${c+30} Q30 ${c+14} 78 ${c+11} Q100 ${c+27} 122 ${c+11} Q170 ${c+14} 200 ${c+30} L200 200Z" fill="${s.shirt}" ${st}/>
<path d="M83 ${c+8} Q100 ${c+24} 117 ${c+8}" fill="none" stroke="${s.chain}" stroke-width="2.2" stroke-dasharray="1.8 1.3" stroke-linecap="round"/><g data-p="head">`;
  for(const k of[-1,1]){const ex=100+k*(s.hw+1);o+=`<ellipse cx="${ex}" cy="${s.eyeY+8}" rx="7" ry="13" fill="${s.skin}" ${st}/><path d="M${ex-k} ${s.eyeY+1} q${k*3} 6 0 13" fill="none" stroke="${s.shade}" stroke-width="1.3" stroke-linecap="round"/>`}
  o+=`<path d="${face}" fill="${s.skin}" ${st}/><g clip-path="url(#cf${sfx})"><ellipse cx="100" cy="${m+30}" rx="${s.hw-2}" ry="36" fill="${s.hair}" opacity=".13"/></g>
<path d="M100 ${c-9} q-6 3 -9 -1 M100 ${c-9} q6 3 9 -1" fill="none" stroke="${s.shade}" stroke-width="1.2" stroke-linecap="round" opacity=".6"/>`;
  for(const[k,d]of[[-1,'L'],[1,'R']]){const x=100+k*s.eyeX,y=s.eyeY,by=y-s.eRy-7;
    o+=`<g clip-path="url(#ce${d}${sfx})"><ellipse cx="${x}" cy="${y}" rx="${s.eRx}" ry="${s.eRy}" fill="#fbfbf8"/><g data-p="iris${d}"><circle cx="${x}" cy="${y}" r="5.53" fill="#6b6a3e"/><circle cx="${x}" cy="${y}" r="2.76" fill="#141414"/><circle cx="${x+1.6}" cy="${y-1.8}" r="1.1" fill="#fff"/></g>
<rect data-p="lid${d}" x="${x-s.eRx-1}" y="${y-s.eRy-1}" width="${2*s.eRx+2}" height="0" fill="${s.lid}"/></g><ellipse cx="${x}" cy="${y}" rx="${s.eRx}" ry="${s.eRy}" fill="none" stroke="${L}" stroke-width="${r(lw*.7)}"/>
<path data-p="ll${d}" d="" fill="none" stroke="${L}" stroke-width="${r(lw*.95)}" stroke-linecap="round"/>
<g data-p="brow${d}"><path d="M${x-k*12} ${by+1} Q${x+k} ${by-5} ${x+k*13} ${by+2}" fill="none" stroke="${s.hair}" stroke-width="5" stroke-linecap="round"/></g>`}
  o+=`<path d="M${100-nw*.5} ${ny+nl-6} C${100-nw-1} ${ny+nl-3} ${100-nw} ${ny+nl+5} 97 ${ny+nl+4} Q100 ${ny+nl+6} 103 ${ny+nl+4} C${100+nw} ${ny+nl+5} ${100+nw+1} ${ny+nl-3} ${100+nw*.5} ${ny+nl-6}" fill="${s.shade}" opacity=".35"/>
<path d="M97 ${ny+4} C97 ${ny+nl*.5} ${100-nw*.5} ${ny+nl*.75} ${100-nw*.6} ${ny+nl-4} C${100-nw-1} ${ny+nl} ${100-nw+1} ${ny+nl+5} 96 ${ny+nl+4} Q100 ${ny+nl+6} 104 ${ny+nl+4} C${100+nw-1} ${ny+nl+5} ${100+nw+1} ${ny+nl} ${100+nw*.6} ${ny+nl-4}" fill="none" ${st}/>
<path data-p="mo" d="" fill="#5a2320" stroke="${L}" stroke-width="${r(lw*.7)}" stroke-linejoin="round"/><path data-p="ml" d="" fill="none" stroke="${L}" stroke-width="${r(lw*.9)}" stroke-linecap="round"/>
<path data-p="lip" d="" fill="none" stroke="${s.shade}" stroke-width="1.4" stroke-linecap="round" opacity=".7"/>
<g data-p="st"><g transform="translate(100 ${m}) scale(${s.stacheS}) translate(-100 ${-m})"><path d="${stache}" fill="${s.stache}" ${st}/><path transform="translate(100 ${m}) scale(.63 .77) translate(-100 ${-m})" d="M88 ${m+3} l-3 7 M95 ${m+2} l-1 7 M105 ${m+2} l1 7 M112 ${m+3} l3 7 M80 ${m+7} l-4 7 M120 ${m+7} l4 7" stroke="#000" stroke-width=".9" opacity=".25" stroke-linecap="round"/></g></g>
<path d="${hair}" fill="${s.hair}" ${st}/></g></g><circle data-p="ring" cx="100" cy="100" r="96" fill="none" stroke="${s.ring.idle}" stroke-width="5"/></svg>`;
  return {svg:o,mcy}}

const faces=[];let FACE_KIND='robot',FACE_LIFE=false;
// ---------------------------------------------------------------- "Gesicht zeigt, was es tut" (V01.0.294)
// Admin switch chat.face_life (default off, whoami "face_life"). With it the face shows what the answer is
// doing, taken only from the panel's own chat events (never from the model's text): a magnifier while it
// searches, a calendar sheet, a letter, a light bulb, a note pad, think bubbles; a wink after something was
// done, a puzzled "?" when something went wrong, and "zzz" after 5 minutes without anything going on.
const PROP_INK='#1e2433',SLEEP_MS=5*60*1000;
const PROP_SVG=`<g data-p="props" pointer-events="none">
<g data-p="badge" opacity="0"><circle cx="166" cy="40" r="22" fill="#fff" stroke="${PROP_INK}" stroke-width="2.5"/>
<g data-p="i-calendar" opacity="0"><rect x="154" y="31" width="24" height="21" rx="3" fill="#fff" stroke="${PROP_INK}" stroke-width="2.2"/><rect x="154" y="31" width="24" height="7" rx="3" fill="#ef4444"/><path d="M159 28v6M173 28v6" stroke="${PROP_INK}" stroke-width="2.2" stroke-linecap="round"/><g data-p="cal-page"><rect x="157" y="40" width="4" height="4" fill="${PROP_INK}"/><rect x="164" y="40" width="4" height="4" fill="#ef4444"/><rect x="171" y="40" width="4" height="4" fill="${PROP_INK}"/><rect x="157" y="46" width="4" height="3" fill="${PROP_INK}"/></g></g>
<g data-p="i-mail" opacity="0"><rect x="152" y="31" width="28" height="19" rx="3" fill="#fff" stroke="${PROP_INK}" stroke-width="2.2"/><path data-p="flap" d="M152 31 L166 43 L180 31" fill="none" stroke="${PROP_INK}" stroke-width="2.2" stroke-linejoin="round"/></g>
<g data-p="i-home" opacity="0"><circle data-p="glow" cx="166" cy="37" r="13" fill="#fde047" opacity="0"/><path data-p="bulb" d="M159 38a7 7 0 1 1 14 0c0 3-2.5 4.5-3 7h-8c-.5-2.5-3-4-3-7z" fill="#fff" stroke="${PROP_INK}" stroke-width="2.2" stroke-linejoin="round"/><path d="M162.5 49h7M163.5 52h5" stroke="${PROP_INK}" stroke-width="2.2" stroke-linecap="round"/></g>
<g data-p="i-memory" opacity="0"><rect x="155" y="28" width="20" height="25" rx="2" fill="#fff" stroke="${PROP_INK}" stroke-width="2.2"/><path d="M159 35h12M159 40h12" stroke="${PROP_INK}" stroke-width="1.6" stroke-linecap="round" opacity=".5"/><path data-p="write" d="M159 45h0" stroke="#4f52d6" stroke-width="2" stroke-linecap="round"/><path data-p="pen" d="M171 41 l7 -9 l3 2 l-7 9 z" fill="#f59e0b" stroke="${PROP_INK}" stroke-width="1.4" stroke-linejoin="round"/></g>
<g data-p="i-happy" opacity="0"><path d="M156 41 l7 7 l13 -15" fill="none" stroke="#16a34a" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>
<g data-p="i-error" opacity="0"><path d="M159.5 33.5a6.5 6.5 0 1 1 9.5 5.8c-2 1-3 2.2-3 4.7" fill="none" stroke="#ef4444" stroke-width="4.2" stroke-linecap="round"/><circle cx="166" cy="50.5" r="2.6" fill="#ef4444"/></g></g>
<g data-p="dots" opacity="0"><circle data-p="d1" cx="150" cy="58" r="4" fill="#fff" stroke="${PROP_INK}" stroke-width="2"/><circle data-p="d2" cx="160" cy="44" r="6" fill="#fff" stroke="${PROP_INK}" stroke-width="2"/><ellipse cx="176" cy="26" rx="14" ry="10" fill="#fff" stroke="${PROP_INK}" stroke-width="2"/><g data-p="dd"><circle cx="170" cy="26" r="1.8" fill="${PROP_INK}"/><circle cx="176" cy="26" r="1.8" fill="${PROP_INK}"/><circle cx="182" cy="26" r="1.8" fill="${PROP_INK}"/></g></g>
<g data-p="zzz" opacity="0" fill="${PROP_INK}" stroke="#fff" stroke-width="2.5" stroke-linejoin="round" paint-order="stroke"><path data-p="z1" d="M146 42h9l-9 9h9" fill="none" stroke="${PROP_INK}" stroke-width="2.6"/><path data-p="z2" d="M160 26h12l-12 12h12" fill="none" stroke="${PROP_INK}" stroke-width="3"/><path data-p="z3" d="M176 6h15l-15 15h15" fill="none" stroke="${PROP_INK}" stroke-width="3.4"/></g>
<g data-p="lens" opacity="0"><circle cx="0" cy="0" r="17" fill="#cfe9ff" fill-opacity=".35" stroke="${PROP_INK}" stroke-width="4.5"/><path d="M12 12 L27 27" stroke="${PROP_INK}" stroke-width="7" stroke-linecap="round"/><path d="M-8 -8 a11 11 0 0 1 8 -4" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/></g></g>`;
// which chat event shows which sign; only these fixed names ever reach the drawing
const FACE_ACTS={search:'search',docsearch:'search',historysearch:'search',calendar:'calendar',briefing:'calendar',mail:'mail',home:'home'};
const FL={act:'',actAt:0,textAt:0,happyUntil:0,happyNext:false,quiet:performance.now()};
window.faceEvent=ev=>{if(!FACE_LIFE||!ev)return;const now=performance.now(),k=FACE_ACTS[ev.type];
  if(k){FL.act=k;FL.actAt=now}
  else if(ev.type==='text'||ev.type==='tts_request')FL.textAt=now;
  else if((ev.type==='memory'&&ev.action==='saved')||(ev.type==='reminder'&&ev.action==='set')){FL.act='memory';FL.actAt=now;FL.happyNext=true}
  else if(ev.type==='home_done'){if(ev.ok)FL.happyNext=true;else chat.errAt=now}};
// the face's own state on top of faceMode(): signs while a tool runs, then happy, puzzled, asleep
function lifeMode(m,now){if(m!=='idle'&&m!=='sad')FL.quiet=now;if(m!=='think')FL.act='';
  if(m==='sad')return'error';
  if(m==='think'){if(FL.act&&(FL.actAt>FL.textAt||now-FL.actAt<1600))return FL.act;
    if(FL.happyNext){FL.happyNext=false;FL.happyUntil=now+2200}return now<FL.happyUntil?'happy':'think'}
  if(m==='idle'){if(FL.happyNext){FL.happyNext=false;FL.happyUntil=now+2200}
    if(now<FL.happyUntil){FL.quiet=now;return'happy'}return now-FL.quiet>SLEEP_MS?'sleep':'idle'}
  return m}
// where the eyes look in each state (-1 … 1), null = look around as usual
function lifeGaze(m,t){if(m==='search')return[Math.sin(t*2.4)*.85,.05];if(m==='calendar'||m==='home')return(t%2.6)<1.7?[.75,-.6]:[.1,0];
  if(m==='mail')return[.35+Math.sin(t*3)*.35,.45];if(m==='memory')return[.55,.55];if(m==='sleep'||m==='happy')return[0,0];return null}
// lids, brows [up L, up R, angle L, angle R], tilt, nod, smile (comic) for the new states
const LIFE_POSE={search:{lid:.12,b:[-1,-1,2,2],tilt:0,nod:2,smile:0},calendar:{lid:-.04,b:[-2.5,-1,-2,0],tilt:-3,smile:.1},
  mail:{lid:.14,b:[-.5,-.5,0,0],tilt:2,nod:2,smile:0},home:{lid:-.08,b:[-3,-3,-2,-2],tilt:-3,smile:.4},memory:{lid:.1,b:[-1,-2,0,0],tilt:4,nod:1.5,smile:.2},
  happy:{lid:.3,b:[-3,-3,-2,-2],tilt:4,smile:1},error:{lid:.12,b:[-1,-1,-10,-10],tilt:-7,smile:-1},sleep:{lid:1,b:[1,1,0,0],tilt:6,nod:5,smile:.1}};
const winkOn=(m,t)=>m==='happy'&&(t%1.8)>.5&&(t%1.8)<.85;
function drawProps(vis,mode,t,dt){const k=n=>Math.min(1,dt*n),r2=n=>Math.round(n*100)/100,on=x=>x?1:0;
  for(const f of vis){const pp=f.pp,c=f.pc;if(!pp)continue;
    c.badge=lerp(c.badge,on(['calendar','mail','home','memory','happy','error'].includes(mode)),k(10));c.dots=lerp(c.dots,on(mode==='think'),k(8));
    c.zzz=lerp(c.zzz,on(mode==='sleep'),k(6));c.lens=lerp(c.lens,on(mode==='search'),k(10));
    pp.badge.setAttribute('opacity',r2(c.badge));pp.badge.setAttribute('transform',`translate(166 40) scale(${r2(.6+.4*c.badge)}) translate(-166 -40)`);
    for(const n of['calendar','mail','home','memory','happy','error'])pp[n].setAttribute('opacity',on(mode===n));
    if(c.badge>.01){pp.calp.setAttribute('opacity',(t%1.3)<1.05?1:.15);pp.flap.setAttribute('d',`M152 31 L166 ${r2(43-((Math.sin(t*2.2)+1)/2)*16)} L180 31`);
      const lit=(t%2.6)>1;pp.glow.setAttribute('opacity',lit?.85:0);pp.bulb.setAttribute('fill',lit?'#fde047':'#fff');
      const wl=(t*9)%12;pp.write.setAttribute('d',`M159 45h${r2(wl)}`);pp.pen.setAttribute('transform',`translate(${r2(wl-12)} 0)`);
      pp.happy.setAttribute('transform',`translate(166 40) scale(${r2(.9+.1*Math.sin(t*6))}) translate(-166 -40)`);pp.error.setAttribute('transform',`rotate(${r2(Math.sin(t*3)*10)} 166 40)`)}
    pp.dots.setAttribute('opacity',r2(c.dots));
    if(c.dots>.01){const ph=t*1.6;pp.d1.setAttribute('opacity',r2(.4+.6*((Math.sin(ph)+1)/2)));pp.d2.setAttribute('opacity',r2(.4+.6*((Math.sin(ph-1)+1)/2)));pp.dd.setAttribute('opacity',(t%1.2)<.9?1:.3)}
    pp.zzz.setAttribute('opacity',r2(c.zzz));
    if(c.zzz>.01)for(const[i,z]of[[0,pp.z1],[1,pp.z2],[2,pp.z3]]){const q=(t*.5+i/3)%1;z.setAttribute('opacity',r2(Math.sin(q*Math.PI)));z.setAttribute('transform',`translate(${r2(q*6)} ${r2(-q*8)})`)}
    pp.lens.setAttribute('opacity',r2(c.lens));pp.lens.setAttribute('transform',`translate(${r2(100+Math.sin(t*2.4)*30)} 96)`)}}
function mountFace(el,sfx){const f=FACE_KIND==='comic'?mountComic(el,sfx):mountRobot(el,sfx);
  if(FACE_LIFE){const svg=el.querySelector('svg');svg.insertAdjacentHTML('beforeend',PROP_SVG);const q=n=>svg.querySelector(`[data-p="${n}"]`);
    f.pp={badge:q('badge'),dots:q('dots'),zzz:q('zzz'),lens:q('lens'),calendar:q('i-calendar'),calp:q('cal-page'),mail:q('i-mail'),flap:q('flap'),home:q('i-home'),glow:q('glow'),
      bulb:q('bulb'),memory:q('i-memory'),write:q('write'),pen:q('pen'),happy:q('i-happy'),error:q('i-error'),d1:q('d1'),d2:q('d2'),dd:q('dd'),z1:q('z1'),z2:q('z2'),z3:q('z3')};
    f.pc={badge:0,dots:0,zzz:0,lens:0}}
  faces.push(f)}
function mountRobot(el,sfx){el.innerHTML=FACE_SVG.replace(/\b(fhead|fshine|fglow|fsoft)\b/g,'$1'+sfx);
  const q=c=>el.querySelector('.'+c);return {el,eyeL:q('feyeL'),eyeR:q('feyeR'),mouth:q('fmouth'),halo:q('fhalo'),ant:q('fant'),cheeks:q('fcheeks'),body:q('fbody')}}
function mountComic(el,sfx){const b=comicSvg(sfx);el.innerHTML=b.svg;const q=n=>el.querySelector(`[data-p="${n}"]`);
  return {el,comic:1,mcy:b.mcy,p:{head:q('head'),iL:q('irisL'),iR:q('irisR'),lL:q('lidL'),lR:q('lidR'),llL:q('llL'),llR:q('llR'),bL:q('browL'),bR:q('browR'),mo:q('mo'),ml:q('ml'),lip:q('lip'),st:q('st'),ring:q('ring')}}}
function mountAll(){faces.length=0;mountFace($('face'),'A');mountFace($('fabface'),'B')}
// called with whoami's "face" and after the admin saved another one; unknown names keep the robot
// the small picture before each answer (chat.js .av) follows the face: a still of the comic face,
// drawn once from the same drawing (lids at rest, mouth closed)
let COMIC_ICON='';
function comicIcon(){if(COMIC_ICON)return COMIC_ICON;const box=document.createElement('div'),s=COMIC,b=comicSvg('I');box.innerHTML=b.svg;
  const q=n=>box.querySelector(`[data-p="${n}"]`),h=(2*s.eRy+2)*s.lidBase;
  for(const[k,d]of[[-1,'L'],[1,'R']]){const x=100+k*s.eyeX,ly=s.eyeY-s.eRy-1+h;q('lid'+d).setAttribute('height',h.toFixed(2));
    q('ll'+d).setAttribute('d',`M${x-s.eRx-.5} ${ly.toFixed(2)} Q${x} ${(ly+1.6).toFixed(2)} ${x+s.eRx+.5} ${ly.toFixed(2)}`)}
  q('ml').setAttribute('d',`M${100-s.mouthW} ${b.mcy} Q100 ${b.mcy+.6} ${100+s.mouthW} ${b.mcy}`);q('ring').setAttribute('stroke-width','0');box.firstElementChild.setAttribute('viewBox','36 24 128 128');   // the head fills the small circle
  COMIC_ICON=`url("data:image/svg+xml,${encodeURIComponent(new XMLSerializer().serializeToString(box.firstElementChild))}")`;return COMIC_ICON}
function faceIcon(){document.body.dataset.face=FACE_KIND;if(FACE_KIND==='comic')document.documentElement.style.setProperty('--avface',comicIcon())}
window.setFaceKind=k=>{k=k==='comic'?'comic':'robot';if(k===FACE_KIND)return;FACE_KIND=k;mountAll();faceIcon()};
window.setFaceLife=on=>{on=on===true;if(on===FACE_LIFE)return;FACE_LIFE=on;FL.act='';FL.happyNext=false;FL.happyUntil=0;FL.quiet=performance.now();mountAll()};
mountAll();
const F={open:0,smile:1,eyeH:24,lx:0,ly:0,halo:.25,cheeks:.6,blink:0,next:performance.now()+2500,mx:-1,my:-1};
// the comic face's own life: looking around, heavy lids, brows, head tilt (one state for both places)
const C={gx:0,gy:0,tx:0,ty:0,look:0,lid:COMIC.lidBase,bL:0,bR:0,aL:0,aR:0,tilt:0,nod:0,open:0,wide:0,last:0};
document.addEventListener('pointermove',e=>{F.mx=e.clientX;F.my=e.clientY;if(e.target.closest&&e.target.closest('.face'))FL.quiet=performance.now()});
for(const n of['pointerdown','keydown'])document.addEventListener(n,()=>{FL.quiet=performance.now()},true);
function faceMode(){if(chat.rec)return'listen';if(playing())return'speak';if(chat.ctrl||chat.asrBusy)return'think';
  if(chat.errAt&&performance.now()-chat.errAt<5000)return'sad';return'idle'}
const lerp=(a,b,k)=>a+(b-a)*k;
let outBuf=null;
function comicFrame(vis,mode,out,mic,now){const s=COMIC,dt=Math.min(.05,(now-(C.last||now))/1000),k=n=>Math.min(1,dt*n),r2=n=>Math.round(n*100)/100;C.last=now;
  const lg=lifeGaze(mode,now/1000);if(lg){C.tx=lg[0];C.ty=lg[1]}
  else if(now>C.look){let tx=(Math.random()-.5)*.4,ty=(Math.random()-.5)*.25;
    if(mode==='think'){tx=.55+Math.random()*.3;ty=-.75+Math.random()*.2}
    else if(mode==='speak'&&Math.random()<.45){tx=(Math.random()-.5)*.8;ty=(Math.random()-.5)*.4}
    else if(mode==='idle'&&F.mx>=0){const b=vis[0].el.getBoundingClientRect(),dx=F.mx-(b.left+b.width/2),dy=F.my-(b.top+b.height/2),d=Math.hypot(dx,dy)||1,m=Math.min(1,d/240);
      tx=dx/d*m+(Math.random()-.5)*.2;ty=dy/d*m*.8+(Math.random()-.5)*.15}
    C.tx=Math.max(-1,Math.min(1,tx));C.ty=Math.max(-1,Math.min(1,ty));C.look=now+500+Math.random()*(mode==='idle'?2600:1800)}
  C.gx=lerp(C.gx,C.tx,k(mode==='search'?40:22));C.gy=lerp(C.gy,C.ty,k(22));
  if(now>F.next){F.blink=now;F.next=now+2200+Math.random()*3800}
  const bt=(now-F.blink)/170,blink=mode!=='sleep'&&bt>=0&&bt<1?Math.sin(bt*Math.PI):0,P=LIFE_POSE[mode],wink=winkOn(mode,now/1000);
  C.lid=lerp(C.lid,Math.min(1,s.lidBase+(P?P.lid:{listen:-.14,think:.06,speak:-.06,idle:.1,sad:.18}[mode])),k(6));const lid=Math.min(1,Math.max(0,C.lid+(1-C.lid)*blink));
  const open=mode==='speak'?Math.min(1,out*1.3):0,emph=open>.8?1:0;C.open=lerp(C.open,open,k(30));C.wide=lerp(C.wide,mode==='speak'?out:0,k(14));
  let tL=0,tR=0,aL=0,aR=0;
  if(mode==='listen'){tL=tR=-2.6-mic*2;aL=aR=-3}else if(mode==='think'){tL=-4.5;tR=1;aL=-6;aR=4}
  else if(mode==='speak'){tL=tR=-1-emph*2.2-C.open*1.2}else if(mode==='sad'){tL=tR=-1;aL=aR=-9}else if(P){[tL,tR,aL,aR]=P.b}
  C.bL=lerp(C.bL,tL,k(9));C.bR=lerp(C.bR,tR,k(9));C.aL=lerp(C.aL,aL,k(8));C.aR=lerp(C.aR,aR,k(8));
  let tilt=0,nod=Math.sin(now/650)*.5;
  if(mode==='listen')tilt=5;else if(mode==='think')tilt=-4+Math.sin(now/1250)*1.5;else if(mode==='speak'){tilt=Math.sin(now/830)*1.6;nod+=emph*1.6+C.open*.8}
  else if(P){tilt=P.tilt;nod=(P.nod||0)+(mode==='sleep'?Math.sin(now/830)*1.4:nod)}
  C.smile=lerp(C.smile||0,P?P.smile:0,k(6));
  C.tilt=lerp(C.tilt,tilt,k(4));C.nod=lerp(C.nod,nod,k(8));
  const thinkL=FACE_LIFE&&mode==='think',o=C.open*7*s.stacheS,w=s.mouthW*(1+C.wide*.35-C.open*.15+(mode==='happy'?.3:0))*(thinkL?.7:1),mx=thinkL?105:100,ix=r2(C.gx*s.eRx*.45),iy=r2(C.gy*s.eRy*.38);
  for(const f of vis){const p=f.p,cy=f.mcy;
    p.head.setAttribute('transform',`rotate(${r2(C.tilt)} 100 175) translate(0 ${r2(C.nod)})`);
    p.iL.setAttribute('transform',`translate(${ix} ${iy})`);p.iR.setAttribute('transform',`translate(${ix} ${iy})`);
    for(const[kk,d]of[[-1,'L'],[1,'R']]){const x=100+kk*s.eyeX,y0=s.eyeY-s.eRy-1,h=(2*s.eRy+2)*lid,ly=y0+h,by=s.eyeY-s.eRy-7;
      const wh=wink&&d==='L'?2*s.eRy+2:h,wy=y0+wh;
      p['l'+d].setAttribute('height',r2(wh));p['ll'+d].setAttribute('d',`M${r2(x-s.eRx-.5)} ${r2(wy)} Q${x} ${r2(wy+(mode==='happy'?-2.4:1.6))} ${r2(x+s.eRx+.5)} ${r2(wy)}`);
      p['b'+d].setAttribute('transform',`translate(0 ${r2(d==='L'?C.bL:C.bR)}) rotate(${r2(kk*(d==='L'?C.aL:C.aR))} ${x} ${by})`)}
    const sad=mode==='sad'?1.6:.6,sm=C.smile*3.2;
    p.mo.setAttribute('d',o>.4?`M${r2(mx-w)} ${r2(cy)} Q${mx} ${r2(cy-o*.35)} ${r2(mx+w)} ${r2(cy)} Q${mx} ${r2(cy+o*2)} ${r2(mx-w)} ${r2(cy)}Z`:'');
    p.ml.setAttribute('d',P?`M${r2(mx-w)} ${r2(cy-sm*.5)} Q${mx} ${r2(cy+sm)} ${r2(mx+w)} ${r2(cy-sm*.5)}`
      :`M${r2(mx-w)} ${r2(cy+(mode==='sad'?1.5:0))} Q${mx} ${r2(cy+(mode==='sad'?-sad:sad))} ${r2(mx+w)} ${r2(cy+(mode==='sad'?1.5:0))}`);
    const ly=cy+o*1.7+4;p.lip.setAttribute('d',`M${r2(mx-w*.55)} ${r2(ly)} Q${mx} ${r2(ly+2.4)} ${r2(mx+w*.55)} ${r2(ly)}`);
    p.st.setAttribute('transform',`translate(0 ${r2(-C.open*1.3-Math.max(0,C.smile)*.8)})`);
    p.ring.setAttribute('stroke',s.ring[mode]);p.ring.setAttribute('stroke-width',r2(mode==='listen'?5+mic*4:5));
    f.el.dataset.mode=mode}}
function faceFrame(now){requestAnimationFrame(faceFrame);
  const vis=faces.filter(f=>f.el.offsetParent);if(!vis.length)return;
  let mode=faceMode();if(FACE_LIFE)mode=lifeMode(mode,now);let out=0;
  if(chat.out&&mode==='speak'){outBuf=outBuf||new Float32Array(chat.out.fftSize);chat.out.getFloatTimeDomainData(outBuf);let e=0;for(const v of outBuf)e+=v*v;out=Math.min(1,Math.sqrt(e/outBuf.length)*6)}
  const mic=chat.micLevel||0;
  if(FACE_LIFE){drawProps(vis,mode,now/1000,Math.min(.05,(now-(FL.last||now))/1000));FL.last=now}
  if(vis[0].comic)return comicFrame(vis,mode,out,mic,now);
  const T={idle:{open:0,smile:1,eyeH:24,halo:.22,cheeks:.6},listen:{open:0,smile:.5,eyeH:28,halo:.3+mic*.7,cheeks:.35},
    think:{open:1.5,smile:0,eyeH:20,halo:.3,cheeks:.2},speak:{open:out*16,smile:.7,eyeH:24,halo:.25+out*.6,cheeks:.5},
    sad:{open:0,smile:-1,eyeH:16,halo:.15,cheeks:0},search:{open:1,smile:0,eyeH:20,halo:.3,cheeks:.2},calendar:{open:0,smile:.1,eyeH:24,halo:.25,cheeks:.3},
    mail:{open:0,smile:0,eyeH:20,halo:.25,cheeks:.2},home:{open:0,smile:.4,eyeH:26,halo:.3,cheeks:.4},memory:{open:0,smile:.2,eyeH:22,halo:.25,cheeks:.3},
    happy:{open:0,smile:1,eyeH:9,halo:.3,cheeks:.9},error:{open:0,smile:-1,eyeH:18,halo:.15,cheeks:0},sleep:{open:0,smile:.1,eyeH:3,halo:.08,cheeks:0}}[mode];
  const P=LIFE_POSE[mode],wink=winkOn(mode,now/1000),lg=lifeGaze(mode,now/1000);F.tilt=lerp(F.tilt||0,P?P.tilt:0,.06);
  F.open=lerp(F.open,T.open,.45);F.smile=lerp(F.smile,T.smile,.15);F.eyeH=lerp(F.eyeH,T.eyeH,.2);F.halo=lerp(F.halo,T.halo,.2);F.cheeks=lerp(F.cheeks,T.cheeks,.1);
  if(now>F.next){F.blink=now;F.next=now+2200+Math.random()*3800}
  const bl=mode!=='sleep'&&now-F.blink<150?Math.max(.08,Math.abs(1-(now-F.blink)/75)):1;
  for(const f of vis){let tx=0,ty=0;
    if(lg){tx=lg[0]*7;ty=lg[1]*6}else if(mode==='think'){tx=6;ty=-6}
    else if(F.mx>=0){const r=f.el.getBoundingClientRect(),dx=F.mx-(r.left+r.width/2),dy=F.my-(r.top+r.height/2),d=Math.hypot(dx,dy)||1;
      const m=Math.min(6,d/40);tx=dx/d*m;ty=dy/d*m*.7}
    f.lx=lerp(f.lx||0,tx,.12);f.ly=lerp(f.ly||0,ty,.12);
    const h=F.eyeH*bl,y=96-h/2+f.ly;
    f.eyeL.setAttribute('x',66+f.lx);f.eyeR.setAttribute('x',116+f.lx);
    for(const e of[f.eyeL,f.eyeR]){const eh=wink&&e===f.eyeL?3:Math.max(3,h);e.setAttribute('y',96-eh/2+f.ly);e.setAttribute('height',eh);e.setAttribute('rx',Math.min(9,eh/2))}
    const w=13+F.open*.35,my=124+f.ly*.4,c=F.smile*8,o=F.open,mx=100+f.lx*.6;
    f.mouth.setAttribute('d',`M${mx-w} ${my} Q${mx} ${my+c-o*.3} ${mx+w} ${my} Q${mx} ${my+c+o*1.7} ${mx-w} ${my}Z`);
    f.halo.setAttribute('opacity',F.halo.toFixed(3));f.halo.setAttribute('r',(78+F.halo*14).toFixed(1));
    f.cheeks.setAttribute('opacity',F.cheeks.toFixed(2));
    f.ant.style.fill=mode==='listen'?'#ff6b6b':mode==='sad'||mode==='error'?'#f59e0b':'var(--acc2)';
    f.ant.setAttribute('opacity',['think','search','calendar','mail','home','memory'].includes(mode)?(.4+.6*Math.abs(Math.sin(now/220))).toFixed(2):1);
    f.body.setAttribute('transform',`${F.tilt?`rotate(${F.tilt.toFixed(2)} 100 170) `:''}translate(0 ${(Math.sin(now/(mode==='sleep'?1300:900))*1.6+(mode==='speak'?out*-1.5:0)+(P&&P.nod||0)*.8).toFixed(2)})`);
    f.el.dataset.mode=mode}}
requestAnimationFrame(faceFrame);
$('face').onclick=()=>$('talk').click();
// floating button: talk from any tab, the conversation is the same as in the chat tab
$('fabface').onclick=e=>{e.stopPropagation();$('fab').classList.add('open');if(!CFG)api('/api/config').then(r=>r.json()).then(c=>CFG=CFG||c).catch(()=>{});$('talk').click()};
$('fabopen').onclick=()=>{$('fab').classList.remove('open');document.querySelector('nav button[data-s=chat]').click()};
$('fabstop').onclick=()=>$('chatstop').click();
document.addEventListener('click',e=>{if(!$('fab').contains(e.target)&&faceMode()==='idle')$('fab').classList.remove('open')});
