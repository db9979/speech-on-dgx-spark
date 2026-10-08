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
  ring:{idle:'#94a3b8',listen:'#3b82f6',think:'#f59e0b',speak:'#22c55e',sad:'#ef4444'}};
// hair tips, fixed so the face never changes between loads
const COMIC_HAIR=[[-6,1],[-12.8,1.31],[-19.7,1],[-26.5,1.19],[-33.3,1],[-40.2,1.33],[-47,1],[-53.8,1.22],[-60.7,1],[-67.5,1.3],[-74.3,1],
  [-81.2,1.2],[-88,1],[-94.8,1.34],[-101.7,1],[-108.5,1.21],[-115.3,1],[-122.2,1.3],[-129,1],[-135.8,1.18],[-142.7,1],[-149.5,1.32],[-156.3,1],[-163.2,1.24],[-170,1]];
function comicSvg(sfx){const s=COMIC,r=n=>Math.round(n*100)/100,m=s.eyeY+s.noseLen+6,mcy=m+15*s.stacheS,L=s.line,lw=s.lw;
  const st=`stroke="${L}" stroke-width="${lw}" stroke-linejoin="round" stroke-linecap="round"`;
  const face=`M100 ${s.top} C${r(100+s.hw*.72)} ${s.top} ${100+s.hw} ${s.top+22} ${100+s.hw} ${s.cheekY} C${100+s.hw} ${s.cheekY+36} ${100+s.chinW+13} ${s.chinY-15} ${100+s.chinW} ${s.chinY-5} Q100 ${s.chinY+6} ${100-s.chinW} ${s.chinY-5} C${100-s.chinW-13} ${s.chinY-15} ${100-s.hw} ${s.cheekY+36} ${100-s.hw} ${s.cheekY} C${100-s.hw} ${s.top+22} ${r(100-s.hw*.72)} ${s.top} 100 ${s.top}Z`;
  const cy=s.top+44,rx=s.hw+4;let hair=`M${100+s.hw+2} ${cy}`;
  for(const[a,k]of COMIC_HAIR)hair+=` L${r(100+Math.cos(a*Math.PI/180)*rx*k)} ${r(cy+Math.sin(a*Math.PI/180)*50*k)}`;
  hair+=` L${100-s.hw-2} ${cy} L${100-s.hw+3} ${s.top+38} Q${r(100-s.hw*.45)} ${s.top+13} 100 ${s.top+18} Q${r(100+s.hw*.45)} ${s.top+13} ${100+s.hw-3} ${s.top+38}Z`;
  const stache=`M100 ${m} C110 ${m-2} 124 ${m+2} 130 ${m+12} C133 ${m+18} 132 ${m+24} 129 ${m+27} C126 ${m+21} 118 ${m+14} 108 ${m+13} Q100 ${m+11} 92 ${m+13} C82 ${m+14} 74 ${m+21} 71 ${m+27} C68 ${m+24} 67 ${m+18} 70 ${m+12} C76 ${m+2} 90 ${m-2} 100 ${m}Z`;
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
<g data-p="st"><g transform="translate(100 ${m}) scale(${s.stacheS}) translate(-100 ${-m})"><path d="${stache}" fill="${s.stache}" ${st}/><path d="M88 ${m+3} l-3 7 M95 ${m+2} l-1 7 M105 ${m+2} l1 7 M112 ${m+3} l3 7 M80 ${m+7} l-4 7 M120 ${m+7} l4 7" stroke="#000" stroke-width=".9" opacity=".25" stroke-linecap="round"/></g></g>
<path d="${hair}" fill="${s.hair}" ${st}/></g></g><circle data-p="ring" cx="100" cy="100" r="96" fill="none" stroke="${s.ring.idle}" stroke-width="5"/></svg>`;
  return {svg:o,mcy}}

const faces=[];let FACE_KIND='robot';
function mountFace(el,sfx){faces.push(FACE_KIND==='comic'?mountComic(el,sfx):mountRobot(el,sfx))}
function mountRobot(el,sfx){el.innerHTML=FACE_SVG.replace(/\b(fhead|fshine|fglow|fsoft)\b/g,'$1'+sfx);
  const q=c=>el.querySelector('.'+c);return {el,eyeL:q('feyeL'),eyeR:q('feyeR'),mouth:q('fmouth'),halo:q('fhalo'),ant:q('fant'),cheeks:q('fcheeks'),body:q('fbody')}}
function mountComic(el,sfx){const b=comicSvg(sfx);el.innerHTML=b.svg;const q=n=>el.querySelector(`[data-p="${n}"]`);
  return {el,comic:1,mcy:b.mcy,p:{head:q('head'),iL:q('irisL'),iR:q('irisR'),lL:q('lidL'),lR:q('lidR'),llL:q('llL'),llR:q('llR'),bL:q('browL'),bR:q('browR'),mo:q('mo'),ml:q('ml'),lip:q('lip'),st:q('st'),ring:q('ring')}}}
function mountAll(){faces.length=0;mountFace($('face'),'A');mountFace($('fabface'),'B')}
// called with whoami's "face" and after the admin saved another one; unknown names keep the robot
window.setFaceKind=k=>{k=k==='comic'?'comic':'robot';if(k===FACE_KIND)return;FACE_KIND=k;mountAll()};
mountAll();
const F={open:0,smile:1,eyeH:24,lx:0,ly:0,halo:.25,cheeks:.6,blink:0,next:performance.now()+2500,mx:-1,my:-1};
// the comic face's own life: looking around, heavy lids, brows, head tilt (one state for both places)
const C={gx:0,gy:0,tx:0,ty:0,look:0,lid:COMIC.lidBase,bL:0,bR:0,aL:0,aR:0,tilt:0,nod:0,open:0,wide:0,last:0};
document.addEventListener('pointermove',e=>{F.mx=e.clientX;F.my=e.clientY});
function faceMode(){if(chat.rec)return'listen';if(playing())return'speak';if(chat.ctrl||chat.asrBusy)return'think';
  if(chat.errAt&&performance.now()-chat.errAt<5000)return'sad';return'idle'}
const lerp=(a,b,k)=>a+(b-a)*k;
let outBuf=null;
function comicFrame(vis,mode,out,mic,now){const s=COMIC,dt=Math.min(.05,(now-(C.last||now))/1000),k=n=>Math.min(1,dt*n),r2=n=>Math.round(n*100)/100;C.last=now;
  if(now>C.look){let tx=(Math.random()-.5)*.4,ty=(Math.random()-.5)*.25;
    if(mode==='think'){tx=.55+Math.random()*.3;ty=-.75+Math.random()*.2}
    else if(mode==='speak'&&Math.random()<.45){tx=(Math.random()-.5)*.8;ty=(Math.random()-.5)*.4}
    else if(mode==='idle'&&F.mx>=0){const b=vis[0].el.getBoundingClientRect(),dx=F.mx-(b.left+b.width/2),dy=F.my-(b.top+b.height/2),d=Math.hypot(dx,dy)||1,m=Math.min(1,d/240);
      tx=dx/d*m+(Math.random()-.5)*.2;ty=dy/d*m*.8+(Math.random()-.5)*.15}
    C.tx=Math.max(-1,Math.min(1,tx));C.ty=Math.max(-1,Math.min(1,ty));C.look=now+500+Math.random()*(mode==='idle'?2600:1800)}
  C.gx=lerp(C.gx,C.tx,k(22));C.gy=lerp(C.gy,C.ty,k(22));
  if(now>F.next){F.blink=now;F.next=now+2200+Math.random()*3800}
  const bt=(now-F.blink)/170,blink=bt>=0&&bt<1?Math.sin(bt*Math.PI):0;
  C.lid=lerp(C.lid,s.lidBase+({listen:-.14,think:.06,speak:-.06,idle:.1,sad:.18}[mode]),k(6));const lid=Math.min(1,Math.max(0,C.lid+(1-C.lid)*blink));
  const open=mode==='speak'?Math.min(1,out*1.3):0,emph=open>.8?1:0;C.open=lerp(C.open,open,k(30));C.wide=lerp(C.wide,mode==='speak'?out:0,k(14));
  let tL=0,tR=0,aL=0,aR=0;
  if(mode==='listen'){tL=tR=-2.6-mic*2;aL=aR=-3}else if(mode==='think'){tL=-4.5;tR=1;aL=-6;aR=4}
  else if(mode==='speak'){tL=tR=-1-emph*2.2-C.open*1.2}else if(mode==='sad'){tL=tR=-1;aL=aR=-9}
  C.bL=lerp(C.bL,tL,k(9));C.bR=lerp(C.bR,tR,k(9));C.aL=lerp(C.aL,aL,k(8));C.aR=lerp(C.aR,aR,k(8));
  let tilt=0,nod=Math.sin(now/650)*.5;
  if(mode==='listen')tilt=5;else if(mode==='think')tilt=-4+Math.sin(now/1250)*1.5;else if(mode==='speak'){tilt=Math.sin(now/830)*1.6;nod+=emph*1.6+C.open*.8}
  C.tilt=lerp(C.tilt,tilt,k(4));C.nod=lerp(C.nod,nod,k(8));
  const o=C.open*7*s.stacheS,w=s.mouthW*(1+C.wide*.35-C.open*.15),ix=r2(C.gx*s.eRx*.45),iy=r2(C.gy*s.eRy*.38);
  for(const f of vis){const p=f.p,cy=f.mcy;
    p.head.setAttribute('transform',`rotate(${r2(C.tilt)} 100 175) translate(0 ${r2(C.nod)})`);
    p.iL.setAttribute('transform',`translate(${ix} ${iy})`);p.iR.setAttribute('transform',`translate(${ix} ${iy})`);
    for(const[kk,d]of[[-1,'L'],[1,'R']]){const x=100+kk*s.eyeX,y0=s.eyeY-s.eRy-1,h=(2*s.eRy+2)*lid,ly=y0+h,by=s.eyeY-s.eRy-7;
      p['l'+d].setAttribute('height',r2(h));p['ll'+d].setAttribute('d',`M${r2(x-s.eRx-.5)} ${r2(ly)} Q${x} ${r2(ly+1.6)} ${r2(x+s.eRx+.5)} ${r2(ly)}`);
      p['b'+d].setAttribute('transform',`translate(0 ${r2(d==='L'?C.bL:C.bR)}) rotate(${r2(kk*(d==='L'?C.aL:C.aR))} ${x} ${by})`)}
    const sad=mode==='sad'?1.6:.6;
    p.mo.setAttribute('d',o>.4?`M${r2(100-w)} ${r2(cy)} Q100 ${r2(cy-o*.35)} ${r2(100+w)} ${r2(cy)} Q100 ${r2(cy+o*2)} ${r2(100-w)} ${r2(cy)}Z`:'');
    p.ml.setAttribute('d',`M${r2(100-w)} ${r2(cy+(mode==='sad'?1.5:0))} Q100 ${r2(cy+(mode==='sad'?-sad:sad))} ${r2(100+w)} ${r2(cy+(mode==='sad'?1.5:0))}`);
    const ly=cy+o*1.7+4;p.lip.setAttribute('d',`M${r2(100-w*.55)} ${r2(ly)} Q100 ${r2(ly+2.4)} ${r2(100+w*.55)} ${r2(ly)}`);
    p.st.setAttribute('transform',`translate(0 ${r2(-C.open*1.3)})`);
    p.ring.setAttribute('stroke',s.ring[mode]);p.ring.setAttribute('stroke-width',r2(mode==='listen'?5+mic*4:5));
    f.el.dataset.mode=mode}}
function faceFrame(now){requestAnimationFrame(faceFrame);
  const vis=faces.filter(f=>f.el.offsetParent);if(!vis.length)return;
  const mode=faceMode();let out=0;
  if(chat.out&&mode==='speak'){outBuf=outBuf||new Float32Array(chat.out.fftSize);chat.out.getFloatTimeDomainData(outBuf);let e=0;for(const v of outBuf)e+=v*v;out=Math.min(1,Math.sqrt(e/outBuf.length)*6)}
  const mic=chat.micLevel||0;
  if(vis[0].comic)return comicFrame(vis,mode,out,mic,now);
  const T={idle:{open:0,smile:1,eyeH:24,halo:.22,cheeks:.6},listen:{open:0,smile:.5,eyeH:28,halo:.3+mic*.7,cheeks:.35},
    think:{open:1.5,smile:0,eyeH:20,halo:.3,cheeks:.2},speak:{open:out*16,smile:.7,eyeH:24,halo:.25+out*.6,cheeks:.5},
    sad:{open:0,smile:-1,eyeH:16,halo:.15,cheeks:0}}[mode];
  F.open=lerp(F.open,T.open,.45);F.smile=lerp(F.smile,T.smile,.15);F.eyeH=lerp(F.eyeH,T.eyeH,.2);F.halo=lerp(F.halo,T.halo,.2);F.cheeks=lerp(F.cheeks,T.cheeks,.1);
  if(now>F.next){F.blink=now;F.next=now+2200+Math.random()*3800}
  const bl=now-F.blink<150?Math.max(.08,Math.abs(1-(now-F.blink)/75)):1;
  for(const f of vis){let tx=0,ty=0;
    if(mode==='think'){tx=6;ty=-6}
    else if(F.mx>=0){const r=f.el.getBoundingClientRect(),dx=F.mx-(r.left+r.width/2),dy=F.my-(r.top+r.height/2),d=Math.hypot(dx,dy)||1;
      const m=Math.min(6,d/40);tx=dx/d*m;ty=dy/d*m*.7}
    f.lx=lerp(f.lx||0,tx,.12);f.ly=lerp(f.ly||0,ty,.12);
    const h=F.eyeH*bl,y=96-h/2+f.ly;
    f.eyeL.setAttribute('x',66+f.lx);f.eyeR.setAttribute('x',116+f.lx);for(const e of[f.eyeL,f.eyeR]){e.setAttribute('y',y);e.setAttribute('height',h)}
    const w=13+F.open*.35,my=124+f.ly*.4,c=F.smile*8,o=F.open,mx=100+f.lx*.6;
    f.mouth.setAttribute('d',`M${mx-w} ${my} Q${mx} ${my+c-o*.3} ${mx+w} ${my} Q${mx} ${my+c+o*1.7} ${mx-w} ${my}Z`);
    f.halo.setAttribute('opacity',F.halo.toFixed(3));f.halo.setAttribute('r',(78+F.halo*14).toFixed(1));
    f.cheeks.setAttribute('opacity',F.cheeks.toFixed(2));
    f.ant.style.fill=mode==='listen'?'#ff6b6b':mode==='sad'?'#f59e0b':'var(--acc2)';
    f.ant.setAttribute('opacity',mode==='think'?(.4+.6*Math.abs(Math.sin(now/220))).toFixed(2):1);
    f.body.setAttribute('transform',`translate(0 ${(Math.sin(now/900)*1.6+(mode==='speak'?out*-1.5:0)).toFixed(2)})`);
    f.el.dataset.mode=mode}}
requestAnimationFrame(faceFrame);
$('face').onclick=()=>$('talk').click();
// floating button: talk from any tab, the conversation is the same as in the chat tab
$('fabface').onclick=e=>{e.stopPropagation();$('fab').classList.add('open');if(!CFG)api('/api/config').then(r=>r.json()).then(c=>CFG=CFG||c).catch(()=>{});$('talk').click()};
$('fabopen').onclick=()=>{$('fab').classList.remove('open');document.querySelector('nav button[data-s=chat]').click()};
$('fabstop').onclick=()=>$('chatstop').click();
document.addEventListener('click',e=>{if(!$('fab').contains(e.target)&&faceMode()==='idle')$('fab').classList.remove('open')});
