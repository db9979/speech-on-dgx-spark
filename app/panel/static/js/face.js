// The assistant's face (eyes, mouth, moods); swap this file to change the face.
// ---------------------------------------------------------------- assistant face
// One animation drives both faces (chat tab and the floating button); its mood follows the chat state.
const FACE_SVG=`<svg viewBox="0 0 200 200" aria-hidden="true"><defs><linearGradient id="fhead" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:var(--acc)"/><stop offset="1" style="stop-color:var(--acc2)"/></linearGradient><radialGradient id="fshine" cx=".35" cy=".25" r=".8"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></radialGradient><filter id="fglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><filter id="fsoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter></defs><circle class="fhalo" cx="100" cy="104" r="80" fill="url(#fhead)" opacity=".25" filter="url(#fsoft)"/><circle class="spin" cx="100" cy="104" r="90" fill="none" stroke="url(#fhead)" stroke-width="3" stroke-linecap="round" stroke-dasharray="60 505"/><g class="fbody"><line x1="100" y1="34" x2="100" y2="18" stroke="url(#fhead)" stroke-width="4" stroke-linecap="round"/><circle class="fant" cx="100" cy="15" r="6" style="fill:var(--acc2)" filter="url(#fglow)"/><rect x="26" y="34" width="148" height="136" rx="56" fill="url(#fhead)"/><rect x="26" y="34" width="148" height="136" rx="56" fill="url(#fshine)"/><rect x="18" y="86" width="12" height="34" rx="6" fill="url(#fhead)"/><rect x="170" y="86" width="12" height="34" rx="6" fill="url(#fhead)"/><rect x="44" y="62" width="112" height="82" rx="38" style="fill:var(--visor)"/><g class="fcheeks" opacity=".0"><ellipse cx="62" cy="124" rx="9" ry="5" fill="#ff7aa8" opacity=".55"/><ellipse cx="138" cy="124" rx="9" ry="5" fill="#ff7aa8" opacity=".55"/></g><g class="feyes" filter="url(#fglow)" fill="#bff6ff"><rect class="feyeL" x="66" y="84" width="18" height="24" rx="9"/><rect class="feyeR" x="116" y="84" width="18" height="24" rx="9"/></g><path class="fmouth" d="M86 122 Q100 130 114 122" fill="#bff6ff" stroke="#bff6ff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" filter="url(#fglow)"/></g></svg>`;
const faces=[];
function mountFace(el,sfx){el.innerHTML=FACE_SVG.replace(/\b(fhead|fshine|fglow|fsoft)\b/g,'$1'+sfx);
  const q=c=>el.querySelector('.'+c);faces.push({el,eyeL:q('feyeL'),eyeR:q('feyeR'),mouth:q('fmouth'),halo:q('fhalo'),ant:q('fant'),cheeks:q('fcheeks'),body:q('fbody')})}
mountFace($('face'),'A');mountFace($('fabface'),'B');
const F={open:0,smile:1,eyeH:24,lx:0,ly:0,halo:.25,cheeks:.6,blink:0,next:performance.now()+2500,mx:-1,my:-1};
document.addEventListener('pointermove',e=>{F.mx=e.clientX;F.my=e.clientY});
function faceMode(){if(chat.rec)return'listen';if(playing())return'speak';if(chat.ctrl||chat.asrBusy)return'think';
  if(chat.errAt&&performance.now()-chat.errAt<5000)return'sad';return'idle'}
const lerp=(a,b,k)=>a+(b-a)*k;
let outBuf=null;
function faceFrame(now){requestAnimationFrame(faceFrame);
  const vis=faces.filter(f=>f.el.offsetParent);if(!vis.length)return;
  const mode=faceMode();let out=0;
  if(chat.out&&mode==='speak'){outBuf=outBuf||new Float32Array(chat.out.fftSize);chat.out.getFloatTimeDomainData(outBuf);let e=0;for(const v of outBuf)e+=v*v;out=Math.min(1,Math.sqrt(e/outBuf.length)*6)}
  const mic=chat.micLevel||0;
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
