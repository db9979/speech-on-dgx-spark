// Zustand → Live and the monitor page /live (live.py, plan „Live-Übersicht“, design 1 Fluss, V01.0.312): which device asks
// right now, the way of each request through the Spark with its times, where it is now, what the Wächter decides and why,
// who came in from the internet, what the services gave back, channels and numbers. Only fixed words and numbers come
// from the panel; everything is put in with lvE() or textContent. The admin page asks /api/admin/live every second while
// the tab is open; the monitor (body.kiosk) asks /api/live/state and pairs once with a 6-digit code.
(()=>{
const KIOSK=document.body.classList.contains('kiosk');
const LV={sel:'',data:null,timer:0,gsel:0,dsel:0,rot:0,lastSel:0,lastKey:'',fail:0};
const lvE=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tt=(de,en)=>typeof t==='function'?t(de,en):de;
const num=(v,d=1)=>v==null?'–':Number(v).toFixed(d).replace('.',',');
const secs=ms=>num(ms/1000,ms<10000?1:0)+' s';
const kb=n=>n==null?'–':n<1024?n+' Z.':num(n/1024,n<10240?1:0)+' kB';
const hm=t=>{const d=new Date(t*1000);return d.toTimeString().slice(0,8)};
const COLS=['var(--c1)','var(--c2)','var(--c3)','var(--c4)','var(--c5)','var(--c6)'];
const col=id=>COLS[parseInt(String(id).slice(0,4),16)%COLS.length]||COLS[0];
const STAGES=[['asr',tt('Hören','Listening'),'ASR · 31001'],['weiche',tt('Weiche','Switch'),tt('Absicht','Intent')],['llm',tt('Sprachmodell','Language model'),'qwen38'],
  ['tool',tt('Werkzeuge','Tools'),'chat_tools'],['tts',tt('Sprechen','Speaking'),'TTS · 31002']];
const SNAME=Object.fromEntries(STAGES.map(s=>[s[0],s[1]]));
const KIND={in:tt('Eingang','Arrival'),prep:tt('Vorbereitung','Preparation'),weiche:tt('Weiche','Switch'),llm:tt('Modell','Model'),tool:tt('Werkzeug','Tool'),check:tt('Prüfung','Check'),tts:tt('Sprechen','Speaking'),err:tt('Abbruch','Stopped'),done:tt('fertig','done')};
const ZONE={spark:[tt('im Spark','on the Spark'),'loc'],lan:[tt('Heimnetz','Home network'),'lan'],net:['Internet','net']};
const PH=()=>matchMedia('(max-width:760px)').matches;
let tip=null;
function el(id){return document.getElementById(id)}
const op=(r,d)=>r.last?'.85':Math.max(.15,(r.left||0)/d.fade).toFixed(2);
const ago=n=>n<60?n+' s':n<3600?Math.floor(n/60)+' min':Math.floor(n/3600)+' h';
const doneTxt=r=>r.last?tt(`letzte Aktion · vor ${ago(r.ago)}`,`last action · ${ago(r.ago)} ago`):tt(`fertig · weg in ${r.left} s`,`done · gone in ${r.left} s`);
function tgt(id){return ((LV.data||{}).targets||[]).find(x=>x.id===id)}
function zoneOf(id){const x=tgt(id);return x?x.zone:'spark'}

// ------------------------------------------------------------------ skeleton
function skeleton(root){
  const way=`<div class="card way"><h3>${tt('Weg der Anfrage','Way of the request')} <small class="mut">${KIOSK?tt('wechselt alle 8 s zur nächsten laufenden Anfrage','moves on to the next request every 8 s'):tt('Gerät oder Zeile antippen zum Wechseln','tap a device or row to switch')}</small></h3><div id="lvway"></div></div>`;
  const gd=`<div class="card" id="lvguardc"><h3>${tt('Wächter: was nach außen geht und warum','Wächter: what goes out and why')}<span class="kdots"></span></h3><div id="lvguard"></div></div>`;
  const dr=`<div class="card" id="lvdoorc"><h3>${tt('Eingang: wer von außen hereinkommt und warum','Entrance: who comes in from outside and why')}<span class="kdots"></span></h3><div id="lvdoor"></div></div>`;
  const rt=`<div class="card" id="lvretc"><h3>${tt('Was die Dienste zurückgeben','What the services return')} <small class="mut">${tt('neueste oben','newest first')}</small><span class="kdots"></span></h3><div id="lvret"></div></div>`;
  const run=`<div class="card"><h3>${tt('Läuft gerade','Running now')} <span class="n" id="lvnrq"></span></h3><div id="lvrq"></div></div>`;
  const ev=`<div class="card"><h3>${tt('Ereignisse','Events')}</h3><div class="mono ev" id="lvev"></div></div>`;
  const cn=`<div class="card" id="lvcnc"><h3>${tt('Offene Verbindungen','Open connections')} <span class="n" id="lvncn"></span><span class="kdots"></span></h3><table id="lvcn"></table></div>`;
  const flow=`<div class="card flow"><h3 style="padding:4px 10px 0">${tt('Wohin die Anfragen gerade gehen','Where the requests go right now')} <small class="mut hideph">${tt('Geräte erscheinen bei einer Anfrage; die letzte bleibt stehen, bis eine neue kommt, dann blendet sie in 10 s aus · oben Heimnetz, unten Internet','devices show while they ask; the last one stays until a new one comes, then fades in 10 s · home network above, internet below')}</small></h3><div id="lvflow"></div></div>`;
  if(KIOSK)root.innerHTML=`<div class="kpis" id="lvkpi"></div>${flow}<div class="kside">${run}${ev}</div><div class="kbot">${way}<div class="krot">${gd}${dr}${rt}${cn}</div></div>`;
  else root.innerHTML=`<div class="kpis" id="lvkpi"></div>${flow}${way}<div class="gates">${gd}${dr}</div><div style="margin-bottom:14px">${rt}</div><div class="grid2">${run}<div class="split">${cn}${ev}</div></div>`;
  if(!tip){tip=document.createElement('div');tip.id='lvtip';document.body.appendChild(tip)}
  const fl=el('lvflow');
  fl.addEventListener('mousemove',e=>{const x=e.target.closest('[data-tip]');if(!x){tip.style.display='none';return}
    tip.textContent=x.dataset.tip;tip.style.display='block';tip.style.left=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(e.clientY+16)+'px'});
  fl.addEventListener('mouseleave',()=>tip.style.display='none');
  root.addEventListener('click',e=>{const d=e.target.closest('[data-req]');if(d){LV.sel=d.dataset.req;LV.lastSel=Date.now();LV.lastKey='';draw();return}
    const g=e.target.closest('[data-gd]');if(g){LV.gsel=+g.dataset.gd;guardList();return}
    const o=e.target.closest('[data-dr]');if(o){LV.dsel=+o.dataset.dr;doorList();return}
    if(!KIOSK&&e.target.closest('[data-gate=guard]'))el('lvguardc').scrollIntoView({behavior:'smooth',block:'start'});
    if(!KIOSK&&e.target.closest('[data-gate=door]'))el('lvdoorc').scrollIntoView({behavior:'smooth',block:'start'})});
}

// ------------------------------------------------------------------ numbers on top
function spark(a,c){a=(a||[]).filter(x=>x!=null);if(a.length<2)return '<svg></svg>';const w=100,h=24,mx=Math.max(...a,1);
  const pts=a.map((v,i)=>`${(i*w/(a.length-1)).toFixed(1)} ${(h-v/mx*h*.9).toFixed(1)}`);
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="M0 ${h} L${pts.join(' L')} L${w} ${h}Z" fill="color-mix(in srgb,${c} 18%,transparent)"/><path d="M${pts.join(' L')}" fill="none" stroke="${c}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`}
function kpis(d){const s=d.sys||{},h=s.hist||{},run=d.reqs.filter(r=>!r.done);
  const net=run.filter(r=>r.net||r.steps.some(x=>zoneOf(x.to)==='net')).length;
  const k=[[tt('Laufende Anfragen','Running requests'),run.length,'',null,'var(--c1)'],[tt('Offene Verbindungen','Open connections'),d.conns.reduce((a,c)=>a+c.n,0),'',null,'var(--c2)'],
    [tt('Internet jetzt','Internet now'),net,tt('Anfr.','req.'),null,'var(--c4)'],['GPU',num(s.gpu,0),'%',h.gpu,'var(--c3)'],[tt('Speicher frei','Memory free'),num(s.free),'GiB',h.avail,'var(--c5)'],
    ['CPU',num(s.cpu,0),'%',h.cpu,'var(--c6)'],[tt('Wächter heute','Wächter today'),d.guard.bad,tt('geblockt','blocked'),null,'var(--bad)']];
  el('lvkpi').innerHTML=k.map(x=>`<div class="card kpi"><div class="l">${lvE(x[0])}</div><div class="v">${lvE(x[1])}<small>${lvE(x[2])}</small></div>${x[3]?spark(x[3],x[4]):''}</div>`).join('')}

// ------------------------------------------------------------------ the flow picture
function layout(d,ph){const W=ph?360:1140,pos={},reqs=d.reqs.slice(-7),lan=reqs.filter(r=>!r.net).slice(-4),net=reqs.filter(r=>r.net).slice(-3);
  const T=d.targets,order=[...T.filter(x=>x.zone!=='net'),...T.filter(x=>x.zone==='net')];let H;
  if(!ph){H=520;const NETY=300;
    lan.forEach((r,i)=>pos['r'+r.id]={x:10,y:34+i*54,w:190,h:44});net.forEach((r,i)=>pos['r'+r.id]={x:10,y:NETY+14+i*54,w:190,h:44});
    STAGES.forEach((s,i)=>{const step=(H-40)/5;pos[s[0]]={x:470,y:34+step*i+(step-58)/2,w:200,h:58}});
    const th=Math.min(40,(H-40)/order.length-6),step=(H-40)/order.length;order.forEach((x,i)=>pos[x.id]={x:940,y:34+i*step+(step-th)/2,w:190,h:th});
    pos.door={x:300,y:NETY+60,w:30,h:34};
    const n1=order.find(x=>x.zone==='net');pos.guard=n1?{x:865,y:pos[n1.id].y+20,w:30,h:34}:null;pos._nety=NETY;pos._net1=n1?pos[n1.id].y-8:null}
  else{const row=(arr,y,h,per)=>{arr.forEach((n,i)=>{const r=Math.floor(i/per),c=i%per,cnt=Math.min(per,arr.length-r*per),w=(W-8*(cnt+1))/cnt;pos[n.k]={x:8+c*(w+8),y:y+r*(h+8),w,h}});return y+Math.ceil(arr.length/per)*(h+8)};
    let y=row(reqs.map(r=>({k:'r'+r.id})),26,52,3);y=Math.max(y,84)+30;const sy=y;y=row(STAGES.map(s=>({k:s[0]})),y,48,3);y+=30;const ty=y;y=row(order.map(x=>({k:x.id})),y,44,3);H=y+40;pos._sy=sy;pos._ty=ty}
  return {pos,W,H,reqs,order}}
function curve(a,b,ph){return ph?`M${a.x+a.w/2} ${a.y+a.h} C${a.x+a.w/2} ${(a.y+a.h+b.y)/2} ${b.x+b.w/2} ${(a.y+a.h+b.y)/2} ${b.x+b.w/2} ${b.y}`
  :`M${a.x+a.w} ${a.y+a.h/2} C${(a.x+a.w+b.x)/2} ${a.y+a.h/2} ${(a.x+a.w+b.x)/2} ${b.y+b.h/2} ${b.x} ${b.y+b.h/2}`}
const entry=r=>r.voice?'asr':'weiche';
// the way of one request as hops between nodes of the picture: d = done, c = here now, p = still to come
function hops(r){const H=[],at=['r'+r.id];const go=(n,t,st,what)=>{const a=at[at.length-1];if(a!==n)H.push([a,n,t||'',st,what||'']);at.push(n)};
  if(r.net)go('door','','d');go(entry(r),'','d');
  r.steps.forEach(s=>{if(s.k==='weiche')go('weiche',secs(s.d),'d');else if(s.k==='llm'){go('llm',secs(s.d),'d')}
    else if(s.k==='tool'){go('tool','','d');if(s.to&&tgt(s.to)){if(zoneOf(s.to)==='net')go('guard','','d');go(s.to,secs(s.d),'d');
      const ret=((LV.data||{}).rets||[]).find(x=>x.req===r.id&&x.tool===s.n);go('tool','↩ '+(s.ok?'ok':tt('nicht ok','not ok'))+(ret&&ret.size!=null?' · '+kb(ret.size):''),'d')}}
    else if(s.k==='tts')go('tts',secs(s.d),'d')});
  if(r.done)return H;
  const last=r.steps.length?r.steps[r.steps.length-1]:null,since=Math.max(0,r.age*1000-(last?last.a+last.d:0));
  const now=secs(since);
  if(r.stage==='tool'&&r.to&&tgt(r.to)){go('tool','','d');if(zoneOf(r.to)==='net')go('guard','','d');go(r.to,now,'c',tt('wartet auf ','waiting for ')+tgt(r.to).name);go('tool','↩ '+tt('erwartet','expected'),'p')}
  else if(r.stage==='tool')go('tool',now,'c',r.tool||'');
  else if(r.stage==='llm'){go('llm',now,'c',tt('denkt nach oder streamt','thinking or streaming'))}
  else if(r.stage==='tts')go('tts',now,'c',tt('spricht','speaking'));
  else if(r.stage==='weiche')go('weiche',now,'c',tt('wählt Werkzeuge','picks tools'));
  if(r.stage!=='tts'){go('llm','','p');go('tts','','p')}
  go('r'+r.id,'','p');return H}
function route(r,pos,W,H,ph){const c=col(r.id);let o='',lab='',call='';const ctr=p=>({x:p.x+p.w/2,y:p.y+p.h/2});
  hops(r).forEach(([a,b,t,st,what],i)=>{const A=pos[a],B=pos[b];if(!A||!B)return;const ca=ctr(A),cb=ctr(B);let d,mx,my;
    if(Math.abs(ca.x-cb.x)<40){const down=cb.y>ca.y,x=down?A.x+A.w:A.x,k=down?70:-70;d=`M${x} ${ca.y} C${x+k} ${ca.y} ${x+k} ${cb.y} ${x} ${cb.y}`;mx=x+k*.75;my=(ca.y+cb.y)/2}
    else{const fw=cb.x>ca.x,off=fw?0:9,x1=fw?A.x+A.w:A.x,x2=fw?B.x:B.x+B.w,y1=ca.y+off,y2=cb.y+off;d=`M${x1} ${y1} C${(x1+x2)/2} ${y1} ${(x1+x2)/2} ${y2} ${x2} ${y2}`;mx=(x1+x2)/2;my=(y1+y2)/2}
    const ret=t.startsWith('↩');
    o+=`<path id="lvr${i}" d="${d}" fill="none" stroke="${st==='p'?'var(--mut)':c}" stroke-width="${st==='c'?4:3}" ${st==='p'?'stroke-dasharray="5 5" opacity=".7"':''} stroke-linecap="round" data-tip="${lvE(r.id+' · '+(i+1)+': '+nm(a)+' → '+nm(b)+(t?' · '+t:'')+(what?' · '+what:''))}"/>`;
    if(st==='c')o+=[0,1,2].map(k=>`<circle r="6" fill="${c}" stroke="var(--card)" stroke-width="2"><animateMotion dur="1.2s" begin="${-k*.4}s" repeatCount="indefinite"><mpath href="#lvr${i}"/></animateMotion></circle>`).join('');
    if(t){if(ret){my+=26;mx+=(cb.x<ca.x?-30:30)}const s=st==='c'?'● '+t:t,w=s.length*6.2+14;
      lab+=`<g><rect x="${mx-w/2}" y="${my-10}" width="${w}" height="20" rx="${ret?4:10}" fill="${st==='c'?c:'var(--card)'}" stroke="${st==='p'?'var(--mut)':c}" ${ret?'stroke-dasharray="3 2"':''}/><text x="${mx}" y="${my+4}" text-anchor="middle" style="font-size:11px;font-weight:700;fill:${st==='c'?'#fff':'var(--fg)'}">${lvE(s)}</text></g>`}
    if(st==='c')call=`${r.id} ${tt('ist jetzt','is now')}: ${nm(a)} → ${nm(b)} · ${t}${what?' · '+what:''}`});
  if(r.done)call=r.last?`${tt('Letzte Aktion','Last action')} ${r.id} · ${secs(r.age*1000)}`:`${r.id} ${tt('ist fertig','is done')} · ${secs(r.age*1000)}`;
  if(call){const mw=ph?W-16:520,w=Math.min(call.length*6.6+26,mw),y=H-30,x=8;
    lab+=`<g><rect x="${x}" y="${y}" width="${w}" height="26" rx="13" fill="color-mix(in srgb,${c} 16%,var(--card))" stroke="${c}"/><circle cx="${x+13}" cy="${y+13}" r="4" fill="${c}"><animate attributeName="opacity" values="1;.2;1" dur="1s" repeatCount="indefinite"/></circle><text x="${x+24}" y="${y+17}" style="font-size:${ph?10.5:11.5}px;font-weight:600;fill:var(--fg)" ${call.length*6.6+26>mw?`textLength="${mw-34}" lengthAdjust="spacingAndGlyphs"`:''}>${lvE(call)}</text></g>`}
  return ph?`<g>${lab.slice(lab.lastIndexOf('<g><rect'))}</g>`:`<g>${o}${lab}</g>`}
function nm(id){if(id==='door')return tt('Eingang','Entrance');if(id==='guard')return tt('Wächter','Wächter');if(SNAME[id])return SNAME[id];if(tgt(id))return tgt(id).name;
  const r=((LV.data||{}).reqs||[]).find(x=>'r'+x.id===id);return r?r.dev:id}
function flow(){const d=LV.data,ph=PH(),{pos,W,H,reqs,order}=layout(d,ph);
  const key=[LV.sel,ph,...reqs.map(r=>r.id+r.stage+r.steps.length+(r.done?'d':'')),...order.map(x=>x.id)].join('|');
  if(key===LV.lastKey){reqs.filter(r=>r.done).forEach(r=>{const g=el('lvd'+r.id);if(g){g.style.opacity=op(r,d);const b=g.querySelector('.cd');if(b)b.textContent=doneTxt(r)}});return}
  LV.lastKey=key;
  const act=new Set(['qwen']),cnt={};const inc=k=>cnt[k]=(cnt[k]||0)+1;reqs.filter(r=>!r.done).forEach(r=>{act.add(r.stage);inc(r.stage);if(r.to){act.add(r.to);inc(r.to)}});
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${lvE(tt('Fluss der Anfragen','Flow of the requests'))}">`;
  if(!ph)s+=`<text class="colh" x="12" y="18">${tt('Geräte mit Anfrage · Heimnetz','Devices asking · home network')}</text><text class="colh" x="472" y="18">${tt('Im Spark','In the Spark')}</text><text class="colh" x="942" y="18">${tt('Dienste und Ziele','Services and targets')}</text>
    <line class="netline" x1="10" x2="330" y1="${pos._nety-8}" y2="${pos._nety-8}"/><text x="12" y="${pos._nety+6}" style="font-size:10px;fill:var(--c4);font-weight:700;letter-spacing:.08em">${tt('ÜBER DAS INTERNET · PROXY ↓','THROUGH THE INTERNET · PROXY ↓')}</text>`;
  else s+=`<text class="colh" x="8" y="16">${tt('Geräte mit Anfrage','Devices asking')}</text><text class="colh" x="8" y="${pos._sy-10}">${tt('Im Spark','In the Spark')}</text><text class="colh" x="8" y="${pos._ty-10}">${tt('Dienste und Ziele','Services and targets')}</text>`;
  if(!reqs.length)s+=`<text class="b" x="12" y="${ph?60:120}" style="font-size:12px;fill:var(--mut)">${tt('Gerade fragt kein Gerät.','No device is asking right now.')}</text>`;
  else if(!ph&&!reqs.some(r=>r.net))s+=`<text x="12" y="${pos._nety+36}" style="font-size:11.5px;fill:var(--mut)">${tt('gerade niemand von außen','nobody from outside right now')}</text>`;
  for(let i=0;i<STAGES.length-1;i++){const a=pos[STAGES[i][0]],b=pos[STAGES[i+1][0]];s+=ph?`<path class="lnk" d="M${a.x+a.w} ${a.y+a.h/2} L${b.x} ${b.y+b.h/2}" stroke-dasharray="3 3"/>`:`<path class="lnk" d="M${a.x+a.w/2} ${a.y+a.h} L${b.x+b.w/2} ${b.y}" stroke-dasharray="3 3"/>`}
  const sel=reqs.find(r=>r.id===LV.sel);
  let links=[];reqs.forEach(r=>{const on=r.done?'':col(r.id),k='r'+r.id;if(r.net&&!ph){links.push([k,'door',on,r.done]);links.push(['door',entry(r),on,r.done])}else links.push([k,entry(r),on,r.done])});
  const netOn=reqs.find(r=>!r.done&&r.to&&zoneOf(r.to)==='net');if(!ph&&pos.guard)links.push(['tool','guard',netOn?col(netOn.id):'',false]);
  order.forEach(x=>{const r=reqs.find(q=>!q.done&&q.to===x.id);links.push([x.id==='qwen'?'llm':(x.zone==='net'&&!ph&&pos.guard?'guard':'tool'),x.id,r?col(r.id):'',false])});
  s+=`<g class="${sel&&!ph?'dim':''}">`;links.forEach(([a,b,on,fade],i)=>{if(!pos[a]||!pos[b])return;s+=`<path id="lvp${i}" class="lnk${on?' on':''}" d="${curve(pos[a],pos[b],ph)}" ${on?`style="stroke:${on}"`:fade?'style="opacity:.5"':''} data-tip="${lvE(nm(a)+' → '+nm(b))}"/>`;
    if(on)for(let k=0;k<3;k++)s+=`<circle r="${ph?3.5:4.5}" fill="${on}"><animateMotion dur="1.8s" begin="${-k*.6}s" repeatCount="indefinite"><mpath href="#lvp${i}"/></animateMotion></circle>`});s+='</g>';
  const node=(id,a,b,on,o={})=>{const p=pos[id];if(!p)return '';const k=cnt[id];
    return `<g class="node${on?' act':''}${o.cls||''}" ${o.attrs||''} data-tip="${lvE(o.tip||a)}"><rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="10" ${o.stroke?`style="stroke:${o.stroke}"`:''}/>${o.dot?`<circle cx="${p.x+p.w-14}" cy="${p.y+14}" r="4" fill="${o.dot}"/>`:''}
      <text class="a" x="${p.x+10}" y="${p.y+(ph?20:Math.min(p.h/2-1,24))}">${lvE(a)}</text><text class="b${o.cd?' cd':''}" x="${p.x+10}" y="${p.y+(ph?36:Math.min(p.h/2+13,38))}">${lvE(b)}</text>
      ${k&&!ph&&!o.dev?`<circle class="badge" cx="${p.x+p.w-16}" cy="${p.y+p.h/2}" r="10"/><text class="bt" text-anchor="middle" x="${p.x+p.w-16}" y="${p.y+p.h/2+3.5}">${k}</text>`:''}</g>`};
  reqs.forEach(r=>{const sub=r.done?doneTxt(r):(ph?(r.net?'Internet':r.who):`${r.who}${r.intent?' · '+r.intent:''}${r.net?' · Internet':''}`);
    s+=node('r'+r.id,ph?r.dev.slice(0,12):r.dev,sub,!r.done,{dev:1,cd:r.done,stroke:r.done?'':col(r.id),dot:r.done?'var(--mut)':col(r.id),cls:' dv'+(r.age<1.2?' pop':''),
      attrs:`id="lvd${r.id}" data-req="${lvE(r.id)}" ${r.done?`style="opacity:${op(r,d)}"`:''}`,
      tip:`${r.dev} · ${r.who} · ${r.id}${r.intent?' · '+r.intent:''}${r.net?' · '+tt('kam über das Internet','came through the internet'):''} · ${r.done?tt('fertig','done'):KIND[r.stage]||r.stage}`})});
  STAGES.forEach(x=>s+=node(x[0],x[1],ph?'':x[2],act.has(x[0])));
  order.forEach(x=>s+=node(x.id,ph?x.name.split(' ')[0]:x.name,ph?ZONE[x.zone][0]:x.sub,act.has(x.id),{tip:`${x.name} · ${x.sub}`}));
  if(!ph&&pos.guard){const G=pos.guard,gx=G.x+15,gy=G.y+17;s+=`<g class="gate" data-gate="guard" data-tip="${lvE(tt(`Wächter (netguard) · prüft jede Verbindung nach außen · heute ${d.guard.ok} erlaubt, ${d.guard.bad} geblockt · antippen für die Gründe`,`Wächter · checks every outgoing connection · today ${d.guard.ok} allowed, ${d.guard.bad} blocked`))}"><path d="M${gx} ${gy-17} l15 6 v10 c0 11 -8 18 -15 21 c-7 -3 -15 -10 -15 -21 v-10z" fill="var(--card)" stroke="${netOn?'var(--ok)':'var(--mut)'}" stroke-width="2"/><text x="${gx}" y="${gy+5}" text-anchor="middle" style="font-size:12px;font-weight:700;fill:var(--ok)">✓</text>
    <text x="${gx}" y="${gy+34}" text-anchor="middle" style="font-size:10px;font-weight:600;fill:var(--fg)">${tt('Wächter','Wächter')}</text><text x="${gx}" y="${gy+46}" text-anchor="middle" style="font-size:10px;fill:var(--bad)">${d.guard.bad} ${tt('geblockt','blocked')}</text></g>`;
    s+=`<line class="netline" x1="925" x2="1135" y1="${pos._net1}" y2="${pos._net1}"/><text x="920" y="${pos._net1+4}" text-anchor="end" style="font-size:10px;fill:var(--c4);font-weight:700;letter-spacing:.08em">INTERNET ↓</text>`}
  if(!ph){const D=pos.door,dx=D.x+15,dy=D.y+17,on=reqs.find(r=>!r.done&&r.net);
    s+=`<g class="gate" data-gate="door" data-tip="${lvE(tt(`Eingang aus dem Internet · prüft Anmeldung, Schlüssel und Versuche · heute ${d.door.in} herein, ${d.door.out} abgewiesen`,`Entrance from the internet · today ${d.door.in} in, ${d.door.out} refused`))}"><rect x="${D.x}" y="${D.y}" width="30" height="34" rx="6" fill="var(--card)" stroke="${on?col(on.id):'var(--mut)'}" stroke-width="2"/><path d="M${dx-6} ${dy+2} h12 v8 h-12z M${dx-4} ${dy+2} v-4 a4 4 0 0 1 8 0 v4" fill="none" stroke="var(--ok)" stroke-width="1.8"/>
    <text x="${dx}" y="${D.y+48}" text-anchor="middle" style="font-size:10px;font-weight:600;fill:var(--fg)">${tt('Eingang','Entrance')}</text><text x="${dx}" y="${D.y+60}" text-anchor="middle" style="font-size:10px;fill:var(--bad)">${d.door.out} ${tt('abgewiesen','refused')}</text></g>`}
  if(!ph&&d.speaking){const q=pos.tts;s+=`<text x="${q.x+10}" y="${q.y-7}" style="font-size:10.5px;fill:var(--warn)">${tt('spricht gerade · Sprache hat Vorrang','speaking · speech goes first')}</text>`}
  if(sel)s+=route(sel,pos,W,H,ph);
  el('lvflow').innerHTML=s+'</svg>'}

// ------------------------------------------------------------------ cards
function way(){const r=LV.data.reqs.find(x=>x.id===LV.sel),box=el('lvway');
  if(!r){box.innerHTML=`<div class="mut">${tt('Gerade läuft keine Anfrage. Sobald ein Gerät fragt, steht hier ihr Weg Schritt für Schritt.','No request is running. As soon as a device asks, its way shows here step by step.')}</div>`;return}
  const items=r.steps.filter(s=>s.k!=='prep').map(s=>{const z=s.k==='tool'&&s.to?zoneOf(s.to):s.k==='in'&&r.net?'net':s.k==='llm'?'spark':'spark';
    const name=s.k==='in'?r.dev:s.k==='tool'?s.n:s.k==='weiche'?(r.intent||s.n.replace(/^Weiche: ?/,'')):s.n;
    return {k:KIND[s.k]||s.k,n:name,d:`${secs(s.d)}${s.k==='tool'?' · '+(s.ok?'ok':tt('nicht ok','not ok'))+(s.to&&tgt(s.to)?' · '+tgt(s.to).name:''):''}`,z,ms:s.d,cur:false}});
  if(!r.done){const last=r.steps[r.steps.length-1],since=Math.max(0,r.age*1000-(last?last.a+last.d:0));
    items.push({k:KIND[r.stage]||r.stage,n:r.stage==='tool'?(r.tool||KIND.tool):SNAME[r.stage]||r.stage,d:tt('läuft seit ','running for ')+secs(since)+(r.to&&tgt(r.to)?' · '+tgt(r.to).name:''),z:r.to?zoneOf(r.to):'spark',ms:since,cur:true});
    if(r.stage!=='tts')items.push({k:KIND.tts,n:SNAME.tts,d:tt('kommt noch','still to come'),z:'spark',ms:0,todo:true})}
  const usesNet=r.net||r.steps.some(s=>zoneOf(s.to)==='net'),tot=items.reduce((a,x)=>a+x.ms,0)||1;
  let h=`<div class="hd"><span class="lvc" style="background:${col(r.id)}"></span><span class="who">${lvE(r.who)}</span><span class="mut">${lvE(r.dev)}${r.voice?' · '+tt('Stimme','voice'):''}</span>
    ${r.intent?`<span class="pill">${lvE(r.intent)}</span>`:''}<span class="pill ${usesNet?'net':'lan'}">${usesNet?tt('nutzt Internet','uses the internet'):tt('bleibt im Heimnetz','stays at home')}</span>${r.err?`<span class="pill bad">${tt('Fehler','error')}</span>`:''}
    <span class="mono mut" style="margin-left:auto">${lvE(r.id)} · ${secs(r.age*1000)}${r.done?' · '+tt('fertig','done'):''}</span></div><div class="hops">`;
  items.forEach((x,i)=>{h+=`${i?'<div class="arrow">›</div>':''}<div class="hop${x.cur?' cur':''}${x.z==='net'?' net':''}${x.todo?' todo':''}"><span class="pill ${ZONE[x.z][1]}">${ZONE[x.z][0]}</span><div class="k">${lvE(x.k)}</div><div class="nn">${lvE(x.n)}</div><div class="d">${lvE(x.d)}</div></div>`});
  h+='</div><div class="gantt">';let o=0;items.forEach((x,i)=>{if(!x.ms)return;const w=x.ms/tot*100;h+=`<i style="left:${o}%;width:${w}%;background:${x.z==='net'?'var(--c4)':COLS[i%COLS.length]}">${w>9?`<span>${lvE(x.k)} ${secs(x.ms)}</span>`:''}</i>`;o+=w});
  box.innerHTML=h+`</div><div class="mut" style="font-size:11.5px;margin-top:6px">${tt('Wohin die Zeit ging · gelb = Internet. Inhalte werden nie gezeigt, nur Schritte, Zahlen und Ziele.','Where the time went · yellow = internet. Contents never show, only steps, numbers and targets.')}</div>`}
function guardList(){const g=LV.data.guard;el('lvguard').innerHTML=`<div class="gsum"><span><b>${g.ok}</b> ${tt('erlaubt','allowed')}</span><span style="color:var(--bad)"><b>${g.bad}</b> ${tt('geblockt','blocked')}</span><span style="color:var(--warn)"><b>${g.cut}</b> ${tt('gekappt','cut')}</span><span class="mut">${tt('heute','today')}</span></div>`+
  (g.items.length?g.items.map((x,i)=>`<div class="gd${i===LV.gsel?' sel':''}" data-gd="${i}"><span class="t mono">${hm(x.t)}</span><span class="pill ${x.ok?'ok':x.ok===false?'bad':'warn'}">${x.ok?tt('erlaubt','allowed'):x.ok===false?tt('geblockt','blocked'):tt('gekappt','cut')}</span>
    <span class="mono"><b>${lvE(x.to)}</b></span><span class="mut gw">${lvE(x.level)}</span><span class="why">${tt('Warum','Why')}: ${lvE(x.why)}</span>${i===LV.gsel?`<ol>${x.steps.map(s=>`<li>${lvE(s)}</li>`).join('')}</ol>`:''}</div>`).join('')
  :`<div class="mut">${tt('Noch keine Verbindung nach außen seit dem Start.','No outgoing connection since the start.')}</div>`)}
function doorList(){const g=LV.data.door;el('lvdoor').innerHTML=`<div class="gsum"><span><b>${g.in}</b> ${tt('herein','in')}</span><span style="color:var(--bad)"><b>${g.out}</b> ${tt('abgewiesen','refused')}</span><span class="mut">${tt('heute · Absender gekürzt','today · senders shortened')}</span></div>`+
  (g.items.length?g.items.map((x,i)=>`<div class="gd${i===LV.dsel?' sel':''}" data-dr="${i}"><span class="t mono">${hm(x.t)}</span><span class="pill ${x.ok?'ok':'bad'}">${x.ok?tt('herein','in'):tt('abgewiesen','refused')}</span>
    <b>${lvE(x.who)}</b><span class="mut gw mono">${lvE(x.from)}</span><span class="why">${tt('Warum','Why')}: ${lvE(x.why)}</span>${i===LV.dsel?`<ol>${x.steps.map(s=>`<li>${lvE(s)}</li>`).join('')}</ol>`:''}</div>`).join('')
  :`<div class="mut">${tt('Seit dem Start kam niemand von außen und niemand wurde abgewiesen.','Since the start nobody came from outside and nobody was refused.')}</div>`)}
function rets(){const R=LV.data.rets;el('lvret').innerHTML=(R.length?R.map(x=>`<div class="rt${x.req===LV.sel?' sel':''}" data-req="${lvE(x.req)}"><span class="mut mono">${hm(x.t)}</span><b>${lvE(tgt(x.to)?tgt(x.to).name:x.to?x.to:'Spark')}</b><span class="mono mut">${lvE(x.req)}</span>
    <span class="pill ${x.ok?'ok':'bad'}">${x.ok?'ok':tt('Fehler','error')}</span><span>↩ ${lvE(x.tool)} · ${lvE(x.what)}</span><span class="num mut">${kb(x.size)}</span><span class="num">${secs(x.ms)}</span></div>`).join('')
  :`<div class="mut">${tt('Noch kein Werkzeug seit dem Start.','No tool since the start.')}</div>`)+`<div class="mut" style="font-size:11.5px;margin-top:8px">${tt('Nur Art, Größe, Status und Dauer. Termintitel, Mailtexte und Texte aus Treffern erscheinen hier nie.','Only kind, size, status and time. Appointment titles, mail texts and hit texts never show here.')}</div>`}
function running(){const R=LV.data.reqs;el('lvnrq').textContent=R.filter(r=>!r.done).length;
  const all=['in','asr','weiche','llm','tool','tts'],lab={in:tt('Ein','In'),asr:SNAME.asr,weiche:SNAME.weiche,llm:tt('Modell','Model'),tool:tt('Werkzeug','Tool'),tts:SNAME.tts};
  el('lvrq').innerHTML=R.length?R.slice().reverse().map(r=>{const ks=all.filter(k=>k!=='asr'||r.voice),cur=r.done?'tts':r.stage,ci=ks.indexOf(cur);
    return `<div class="rq${r.id===LV.sel?' sel':''}" data-req="${lvE(r.id)}"><span class="c" style="background:${col(r.id)}"></span><span class="mono mut">${lvE(r.id)}</span>
    <span><b>${lvE(r.dev)}</b> <span class="mut">· ${lvE(r.who)}</span> ${r.intent?`<span class="pill">${lvE(r.intent)}</span>`:''}${r.net?' <span class="pill net">Internet</span>':''}${r.done?` <span class="pill ok">${tt('fertig','done')}</span>`:''}</span><span class="t">${secs(r.age*1000)}</span>
    <div class="beads">${ks.map((k,i)=>`${i?`<i class="${i<=ci?'d':''}"></i>`:''}<b class="${!r.done&&i===ci?'n':i<=ci?'d':''}"></b>${!PH()||i===ci?`<span${i===ci?' style="color:var(--fg);font-weight:600"':''}>${lab[k]}</span>`:''}`).join('')}</div></div>`}).join('')
   :`<div class="mut">${tt('Gerade nichts.','Nothing right now.')}</div>`}
function conns(){const C=LV.data.conns;el('lvncn').textContent=C.reduce((a,c)=>a+c.n,0);
  el('lvcn').innerHTML=C.length?C.map(c=>`<tr><td><span class="pill ${c.dir==='ein'?'':'ok'}">${c.dir==='ein'?'↘ '+tt('ein','in'):'↗ '+tt('aus','out')}</span></td><td><b>${lvE(c.name)}</b></td><td class="mut">${lvE(c.proto)}</td><td class="num">${c.n}</td></tr>`).join('')
   :`<tr><td class="mut">${tt('Keine offene Verbindung.','No open connection.')}</td></tr>`}
function events(){el('lvev').innerHTML=LV.data.events.length?LV.data.events.map(x=>`<div><span class="t">${hm(x.t)}</span><b>${lvE(x.area)}</b> <span class="mut">${lvE(x.text)}</span></div>`).join('')
  :`<div class="mut">${tt('Noch nichts seit dem Start.','Nothing since the start.')}</div>`}

// ------------------------------------------------------------------ loop
function pickSel(){const R=LV.data.reqs,run=R.filter(r=>!r.done);
  if(KIOSK&&run.length&&Date.now()-LV.lastSel>8000){const i=run.findIndex(r=>r.id===LV.sel);LV.sel=run[(i+1)%run.length].id;LV.lastSel=Date.now()}
  if(!R.some(r=>r.id===LV.sel))LV.sel=(run[run.length-1]||R[R.length-1]||{}).id||''}
function draw(){if(!LV.data)return;pickSel();kpis(LV.data);flow();way();guardList();doorList();rets();running();conns();events();if(KIOSK)rotate()}
function rotate(){const cards=['lvguardc','lvdoorc','lvretc','lvcnc'],i=Math.floor(Date.now()/10000)%cards.length;
  cards.forEach((c,k)=>{const x=el(c);if(x)x.classList.toggle('on',k===i)});document.querySelectorAll('.kdots').forEach(d=>d.innerHTML=cards.map((_,k)=>`<i class="${k===i?'on':''}"></i>`).join(''));
  const s=el('lvshow');if(s)s.textContent=LV.sel?tt('zeigt gerade: ','showing: ')+LV.sel:''}
function visible(){return KIOSK||(el('live')&&el('live').classList.contains('on'))}
async function tick(){clearTimeout(LV.timer);LV.timer=0;if(!visible())return;
  if(!document.hidden){try{const r=await fetch(KIOSK?'/api/live/state':'/api/admin/live',{cache:'no-store',credentials:'same-origin'});
      if(r.ok){LV.data=await r.json();LV.fail=0;if(!el('lvkpi'))skeleton(el('lvroot'));draw();status(true,KIOSK?LV.data.monitor:'')}
      else{LV.fail++;if(stopped(r.status))return}}
    catch(e){LV.fail++;status(false)}}
  LV.timer=setTimeout(tick,LV.fail>3?5000:1000)}
function status(ok,name){const d=el('lvdot');if(d)d.classList.toggle('bad',!ok);const c=el('lvclock');if(c)c.textContent=ok?new Date().toTimeString().slice(0,8):tt('Verbindung weg, versuche neu …','connection lost, retrying …');
  const m=el('lvname');if(m&&name)m.textContent=name}
function stopped(code){const root=el('lvroot');LV.lastKey='';
  if(!KIOSK&&code===404){root.innerHTML=`<div class="card off"><b>${tt('Die Live-Seite ist aus.','The live page is off.')}</b><div class="mut">${tt('Einschalten unter Einstellungen → Spark → Betrieb → Logs „Live-Seite“. Sie zeigt nur Wege, Werkzeugnamen und Zahlen, nie Inhalte.','Switch it on under Settings → Spark → Operation → Logs “Live page”. It shows ways, tool names and numbers only, never contents.')}</div></div>`;return true}
  if(KIOSK&&code===401){pairForm();return true}
  if(KIOSK&&(code===403||code===404)){root.innerHTML=`<div class="pairbox"><h1>Spark Live</h1><div class="mut">${code===403?tt('Der Monitor geht nur im Heimnetz.','The monitor works in the home network only.'):tt('Der Live-Monitor ist ausgeschaltet.','The live monitor is switched off.')}</div></div>`;return true}
  if(KIOSK&&code===429){status(false);el('lvclock').textContent=tt('zu viele Bildschirme gleichzeitig','too many screens at once')}
  return false}
function pairForm(){el('lvroot').innerHTML=`<div class="pairbox"><h1>Spark Live · ${tt('Monitor koppeln','pair the monitor')}</h1>
  <div class="mut">${tt('Den 6-stelligen Code zeigt der Spark unter Einstellungen → Spark → Betrieb → Logs „Neuer Monitor“. Er gilt 10 Minuten und nur einmal.','The Spark shows the 6-digit code under Settings → Spark → Operation → Logs “New monitor”. It lasts 10 minutes, once.')}</div>
  <input id="lvcode" inputmode="numeric" autocomplete="one-time-code" maxlength="7" aria-label="Code"><button type="button" id="lvpair">${tt('Koppeln','Pair')}</button><div id="lvpmsg" class="mut"></div>
  <ul><li>${tt('Danach merkt sich dieser Bildschirm die Kopplung (nur lesen). In der Adresse steht kein Schlüssel.','Afterwards this screen remembers the pairing (read only). No key in the address.')}</li><li>${tt('Nur aus dem Heimnetz.','Home network only.')}</li><li>${tt('Nach mehreren falschen Codes ist diese Adresse eine Weile gesperrt.','After several wrong codes this address is locked for a while.')}</li></ul></div>`;
  const go=async()=>{const m=el('lvpmsg');m.textContent='…';try{const r=await fetch('/api/live/pair',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({code:el('lvcode').value})});
      if(r.ok){m.textContent=tt('Gekoppelt.','Paired.');el('lvroot').innerHTML='';tick();return}
      m.textContent=r.status===429?tt('Zu viele Versuche, bitte später.','Too many tries, please wait.'):tt('Code falsch oder abgelaufen.','Wrong or expired code.')}catch(e){m.textContent=tt('Keine Verbindung.','No connection.')}};
  el('lvpair').addEventListener('click',go);el('lvcode').addEventListener('keydown',e=>{if(e.key==='Enter')go()});el('lvcode').focus()}
window.liveOpen=()=>{if(!el('lvroot'))return;if(!LV.timer)tick()};
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&visible()&&!LV.timer)tick()});

// ------------------------------------------------------------------ Einstellungen → Betrieb: the monitors (admin)
async function mons(){const box=el('livemons');if(!box||typeof apiTry!=='function')return;const {r,d}=await apiTry('/api/admin/live/monitors');
  if(!r.ok){box.innerHTML=`<div class="mut">${lvE(d.detail||'')}</div>`;return}
  const rows=d.items.map(m=>`<div class="setrow"><div class="lbl"><b>${lvE(m.name)}</b><span>${m.watching?`<span class="pill ok">${tt('zeigt gerade','showing now')}</span> `:''}${tt('gekoppelt','paired')} ${m.created?new Date(m.created*1000).toLocaleDateString():''}${m.last?' · '+tt('zuletzt','last')+' '+new Date(m.last*1000).toLocaleString():''}${m.from?' · '+lvE(m.from):''}</span></div><button class="b" type="button" ${onAttr('lvMonDel',m.id,m.name)}>${tt('Löschen','Delete')}</button></div>`).join('');
  box.innerHTML=(rows||`<div class="mut">${tt('Noch kein Monitor gekoppelt.','No monitor paired yet.')}</div>`)+
    (d.on?`<div class="setrow"><div class="lbl"><b>${tt('Neuer Monitor','New monitor')}</b><span>${tt('Gibt einen 6-stelligen Code (10 Minuten, einmal). Am Bildschirm im Heimnetz die Adresse des Spark mit /live öffnen und den Code eingeben.','Gives a 6-digit code (10 minutes, once). On the screen in the home network open the Spark’s address with /live and enter the code.')}</span><div id="livecode"></div></div><div class="ctl"><input class="wide" id="livename" maxlength="30" placeholder="${tt('Name, z. B. Flur','Name, e.g. hall')}" style="width:150px"><button class="b p" type="button" ${onAttr('lvMonNew')}>${tt('Code holen','Get code')}</button></div></div>`
    :`<div class="mut" style="margin-top:6px">${tt('Zum Koppeln „Live-Monitor“ einschalten und speichern.','To pair, switch on “Live monitor” and save.')}</div>`)}
window.liveMons=mons;
if(typeof ON!=='undefined'){
  ON.lvMonNew=async()=>{const {r,d}=await apiTry('/api/admin/live/monitors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:(el('livename').value||'Monitor').trim()})});
    const c=el('livecode');if(!c)return;if(!r.ok){c.textContent=d.detail||'';return}
    c.innerHTML=`<div style="font:700 28px ui-monospace,Menlo,monospace;letter-spacing:.12em;margin-top:6px">${lvE(d.code.slice(0,3)+' '+d.code.slice(3))}</div><div class="mut">${tt('gilt bis','valid until')} ${new Date(d.until*1000).toLocaleTimeString()} · ${lvE(location.origin+d.path)}</div>`};
  ON.lvMonDel=async(b,id,name)=>{if(!confirm(tt(`Monitor „${name}“ löschen? Er zeigt sofort nichts mehr.`,`Delete monitor “${name}”? It stops at once.`)))return;await apiTry('/api/admin/live/monitors/'+encodeURIComponent(id),{method:'DELETE'});mons()};
}

// ------------------------------------------------------------------ the monitor page starts by itself
if(KIOSK){document.documentElement.dataset.theme=new URLSearchParams(location.search).get('theme')==='light'?'light':'dark';
  document.body.insertAdjacentHTML('afterbegin',`<header class="kh"><h1><span class="logo"></span>Spark Live</h1><span class="pill loc" id="lvname">Monitor</span><span class="pill ok">${tt('nur lesen','read only')}</span>
    <span class="mut" id="lvshow" style="font-size:12px;margin-left:10px"></span><span class="mut hideph" style="font-size:12px">${tt('keine Inhalte, nur Schritte, Zahlen und Ziele','no contents, only steps, numbers and targets')}</span><div class="live"><span class="dot" id="lvdot"></span><span id="lvclock">…</span></div></header>`);
  tick()}
})();
