// Anrufe (anrufe.py, plan messenger-d-v2.md, Dominik 2026-10-14 „1a 2b 3a 4a“): voice and video in a chat of two.
// The Spark only brings the two devices together (start, answer, signal, end over /api/anrufe/*, its news over the
// Chats stream); sound and picture go from device to device (WebRTC, DTLS-SRTP), from outside through the Vermittler.
// One device id per page (AN.dev): a signal is meant for exactly one device of the other person.
// Nothing here goes to the model; the Spark sees who called whom, when and how long.
const AN={dev:'',call:'',cid:'',name:'',video:false,role:'',pc:null,local:null,servers:[],pend:[],cands:[],t0:0,tick:0,ring:null,tone:0};
AN.dev=Array.from(crypto.getRandomValues(new Uint8Array(6)),b=>b.toString(16).padStart(2,'0')).join('');
const anEl=id=>document.getElementById(id);
const anFmt=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');

// ---------------------------------------------------------------- the window of a call
function anShow(state){const w=anEl('ancall');w.hidden=false;w.classList.toggle('vid',AN.video);
  anEl('anname').textContent=AN.name||'';anState(state);
  const inc=AN.role==='in'&&!AN.pc;
  anEl('anincoming').hidden=!inc;anEl('anctl').hidden=inc;anEl('anokv').hidden=!AN.video;
  anEl('ancam').hidden=!AN.video}
function anState(s){anEl('anstate').textContent=s}
function anHide(){const w=anEl('ancall');w.hidden=true;anEl('anremote').srcObject=null;anEl('anlocal').srcObject=null}
// a soft tone with WebAudio: ringing for the called one, the ring back for the caller (no audio file, nothing loaded)
function anTone(kind){anToneStop();try{const C=window.AudioContext||window.webkitAudioContext;if(!C)return;const ctx=new C();AN.ring=ctx;
  const beep=()=>{const o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=kind==='in'?620:440;g.gain.value=0.0001;
    o.connect(g);g.connect(ctx.destination);const t0=ctx.currentTime;g.gain.exponentialRampToValueAtTime(0.15,t0+0.05);
    g.gain.setValueAtTime(0.15,t0+(kind==='in'?0.9:1.4));g.gain.exponentialRampToValueAtTime(0.0001,t0+(kind==='in'?1.0:1.5));o.start(t0);o.stop(t0+1.6)};
  beep();AN.tone=setInterval(beep,kind==='in'?2000:4000)}catch{}}
function anToneStop(){clearInterval(AN.tone);AN.tone=0;if(AN.ring){try{AN.ring.close()}catch{}AN.ring=null}}

// ---------------------------------------------------------------- media and the connection
async function anMedia(video){if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia)
    throw new Error(t('Anrufe brauchen eine Seite über https und ein Mikrofon.','Calls need a page over https and a microphone.'));
  try{return await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:video?{facingMode:'user',width:{ideal:1280},height:{ideal:720}}:false})}
  catch(e){if(video){try{return await navigator.mediaDevices.getUserMedia({audio:true,video:false})}catch{}}
    throw new Error(t('Kein Zugriff auf Mikrofon oder Kamera. Bitte im Browser erlauben.','No access to the microphone or camera. Please allow it in the browser.'))}}
function anPc(){const pc=new RTCPeerConnection({iceServers:AN.servers||[]});AN.pc=pc;
  for(const tr of AN.local.getTracks())pc.addTrack(tr,AN.local);
  pc.onicecandidate=e=>{if(e.candidate)anSend({ice:e.candidate.toJSON()})};
  pc.ontrack=e=>{const v=anEl('anremote');if(v.srcObject!==e.streams[0]){v.srcObject=e.streams[0];v.play().catch(()=>{})}};
  pc.onconnectionstatechange=()=>{const s=pc.connectionState;
    if(s==='connected'&&!AN.t0){AN.t0=Date.now();anToneStop();AN.tick=setInterval(()=>anState(anFmt((Date.now()-AN.t0)/1000)),1000);anState('0:00')}
    else if(s==='failed')anState(t('Verbindung bricht ab …','Connection drops …'))};
  anEl('anlocal').srcObject=AN.video?AN.local:null;
  const q=AN.pend;AN.pend=[];for(const ev of q)anSig(ev);return pc}
async function anSend(data){if(!AN.call)return;try{await cxApi('/api/anrufe/signal',{call:AN.call,dev:AN.dev,data})}catch{}}
async function anSig(ev){const d=ev.data||{};if(!AN.pc){AN.pend.push(ev);return}const pc=AN.pc;
  try{if(d.sdp){await pc.setRemoteDescription(d.sdp);
      if(d.sdp.type==='offer'){await pc.setLocalDescription(await pc.createAnswer());anSend({sdp:{type:'answer',sdp:pc.localDescription.sdp}})}
      for(const c of AN.cands.splice(0))await pc.addIceCandidate(c).catch(()=>{})}
    else if(d.ice){if(pc.remoteDescription)await pc.addIceCandidate(d.ice).catch(()=>{});else AN.cands.push(d.ice)}}
  catch{anState(t('Verbindung klappt nicht.','The connection does not work.'))}}
function anClean(text){anToneStop();clearInterval(AN.tick);
  if(AN.pc){try{AN.pc.close()}catch{}}if(AN.local)AN.local.getTracks().forEach(x=>x.stop());
  Object.assign(AN,{call:'',cid:'',pc:null,local:null,pend:[],cands:[],t0:0,tick:0,role:''});
  if(text){anState(text);anEl('anincoming').hidden=true;anEl('anctl').hidden=true;setTimeout(()=>{if(!AN.call)anHide()},2500)}else anHide()}

// ---------------------------------------------------------------- calling
window.anStart=async video=>{if(AN.call)return;const cid=CX.cur,d=CX.data;if(!cid||!d)return;
  Object.assign(AN,{cid,name:cxTitle(d.title),video,role:'out'});
  try{AN.local=await anMedia(video);AN.video=video&&AN.local.getVideoTracks().length>0;anShow(t('Verbinde …','Connecting …'));
    const r=await cxApi('/api/anrufe/start',{id:cid,video:AN.video,dev:AN.dev});AN.servers=r.servers||[];
    if(r.state!=='ring'){anClean(r.state==='busy'?t('Besetzt.','Busy.'):t('Nimmt gerade nicht ab.','Not answering right now.'));return}
    AN.call=r.call;anState(t('Klingelt …','Ringing …'));anTone('out')}
  catch(e){anClean();cxSay(cxTr(e.message))}};
// ---------------------------------------------------------------- Anrufe per Assistent (rufen.py)
// After the person's yes the answer brings {type:'anruf', id, name, video}: Chats opens that chat and the ordinary call
// starts there (its news come over the Chats stream). A call the assistant sent from a device without a screen waits on
// the Spark (/api/chats "ruf"): a bar with „Anrufen“ (one tap starts it) and „Nicht jetzt“ (gone on every device).
const anCid=/^c[0-9a-f]{12}$/;
window.anFromAssistant=async ev=>{if(AN.call||!ev||!anCid.test(String(ev.id||'')))return;anBar(null);
  showSec('chats');await cxOpen(ev.id);if(CX.cur!==ev.id||!CX.data)return;anStart(!!ev.video)};
window.anBar=r=>{const b=anEl('anbar');if(!r||AN.call||!anCid.test(String(r.id||''))){b.hidden=true;AN.bar=null;return}
  AN.bar=r;anEl('anbartext').textContent=(r.video?t('Video: ','Video: '):'')+String(r.name||'').slice(0,60)+t(' anrufen?',': call now?');b.hidden=false};
anEl('anbargo').addEventListener('click',()=>{const r=AN.bar;if(r)anFromAssistant(r)});
anEl('anbarno').addEventListener('click',async()=>{anBar(null);try{await api('/api/anrufe/bereit',{method:'DELETE'})}catch{}});
async function anAnswer(video){const call=AN.call;if(!call||AN.pc)return;anToneStop();
  try{AN.servers=(await cxApi('/api/anrufe/ice')).servers||[];AN.local=await anMedia(video);AN.video=video&&AN.local.getVideoTracks().length>0;
    if(AN.call!==call)return;anPc();anShow(t('Verbinde …','Connecting …'));
    await cxApi('/api/anrufe/answer',{call,dev:AN.dev})}
  catch(e){const m=cxTr(e.message);anClean(m)}}
async function anEnd(why){const call=AN.call;if(!call){anClean();return}
  anClean(why==='reject'?t('Abgelehnt.','Declined.'):t('Aufgelegt.','Hung up.'));
  try{await cxApi('/api/anrufe/end',{call,dev:AN.dev,why})}catch{}}

// ---------------------------------------------------------------- news from the Spark (chats.js passes them on)
window.anEvent=async ev=>{const ty=ev.type;
  if(ty==='call'){if(AN.call)return;   // already in a call here: the Spark lets the other one hear "besetzt" next time
    Object.assign(AN,{call:ev.call,cid:ev.id,name:String(ev.name||''),video:!!ev.video,role:'in'});
    anShow(ev.video?t('Videoanruf','Video call'):t('Anruf','Call'));anTone('in');return}
  if(ev.call!==AN.call)return;
  if(ty==='call_taken'&&ev.dev!==AN.dev&&!AN.pc){anClean(t('Auf einem anderen Gerät angenommen.','Answered on another device.'));return}
  if(ty==='call_ok'&&AN.role==='out'&&!AN.pc){anToneStop();anState(t('Verbinde …','Connecting …'));const pc=anPc();
    try{await pc.setLocalDescription(await pc.createOffer());anSend({sdp:{type:'offer',sdp:pc.localDescription.sdp}})}catch{anEnd('hangup')}return}
  if(ty==='call_sig'&&ev.to===AN.dev){anSig(ev);return}
  if(ty==='call_end'){const w=ev.why;anClean(w==='reject'?t('Abgelehnt.','Declined.'):w==='missed'?t('Nicht angenommen.','Not answered.')
      :w==='busy'||w==='quiet'?t('Nimmt gerade nicht ab.','Not answering right now.'):t('Aufgelegt.','Hung up.'))}};

// ---------------------------------------------------------------- buttons
anEl('anok').addEventListener('click',()=>anAnswer(false));
anEl('anokv').addEventListener('click',()=>anAnswer(true));
anEl('anno').addEventListener('click',()=>anEnd('reject'));
anEl('anhang').addEventListener('click',()=>anEnd('hangup'));
anEl('anmute').addEventListener('click',e=>{if(!AN.local)return;const a=AN.local.getAudioTracks()[0];if(!a)return;a.enabled=!a.enabled;
  e.currentTarget.classList.toggle('off',!a.enabled);e.currentTarget.setAttribute('aria-pressed',String(!a.enabled))});
anEl('ancam').addEventListener('click',e=>{if(!AN.local)return;const v=AN.local.getVideoTracks()[0];if(!v)return;v.enabled=!v.enabled;
  e.currentTarget.classList.toggle('off',!v.enabled);e.currentTarget.setAttribute('aria-pressed',String(!v.enabled))});
window.addEventListener('pagehide',()=>{if(AN.call){const b=JSON.stringify({call:AN.call,dev:AN.dev,why:'hangup'});
  api('/api/anrufe/end',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:b}).catch(()=>{})}});
