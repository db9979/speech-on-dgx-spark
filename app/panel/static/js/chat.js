// The voice assistant: listening, asking, streaming answers and audio.
// ---------------------------------------------------------------- voice chat
// Record -> /api/test/asr -> /api/chat (LLM text and streamed TTS audio as one SSE stream) -> play.
// Conversation settings (see renderSet). Profiles keep them on the Spark, guests in this browser.
let S={hands:false,auto:true,turn:true,daily:true,live:true,barge:true,barge_level:'mid',voice:'',speed:1,length:'normal',timing:true},SDEF={...S};
const BARGE={low:[0.05,6,0.8],mid:[0.03,4,0.5],high:[0.02,3,0.35]};   // min level, x noise floor, x own output
const chat={live:{busy:false,want:false,last:null},msgs:[],rec:null,stream:null,ctrl:null,ctx:null,sources:[],playEnd:0,vad:null,cancelRec:false,busy:false};
const chatSay=x=>{$('chatstate').textContent=x;$('fabstate').textContent=x};
function chatLog(role,text){const d=document.createElement('div');d.className='msg '+(role==='user'?'user':'bot');
  d.innerHTML=role==='user'?'<div class="bubble"></div>':'<div class="av"><i></i></div><div class="bubble"></div>';
  const b=d.lastChild;if(text)b.textContent=text;else b.classList.add('typing');$('chatlog').appendChild(d);$('chatlog').scrollTop=1e9;return b}
function audioCtx(){if(!chat.ctx)chat.ctx=new (window.AudioContext||window.webkitAudioContext)();
  if(chat.ctx.state==='suspended')chat.ctx.resume();playCtx();return chat.ctx}
// Speech plays in its own context running at the TTS rate (24 kHz). In a 44.1/48 kHz context every
// streamed piece would be resampled on its own, and the seams between the pieces click.
function playCtx(){const AC=window.AudioContext||window.webkitAudioContext;
  if(!chat.pctx){try{chat.pctx=new AC({sampleRate:24000,latencyHint:'interactive'})}catch{chat.pctx=new AC()}
    chat.out=chat.pctx.createAnalyser();chat.out.fftSize=512;chat.out.connect(chat.pctx.destination)}   /* the face's mouth follows this level */
  if(chat.pctx.state==='suspended')chat.pctx.resume();return chat.pctx}
function playPcm(b64){const ctx=playCtx(),bin=atob(b64),n=bin.length>>1;if(!n)return;const f=new Float32Array(n);
  for(let i=0;i<n;i++){let v=bin.charCodeAt(2*i)|(bin.charCodeAt(2*i+1)<<8);if(v>=32768)v-=65536;f[i]=v/32768}
  // after a gap (first piece, or the stream fell behind) start a little ahead and fade in, so the
  // next pieces join seamlessly and the restart does not click
  // 0.25 s head start: a reserve for when the GPU is busy with the LLM at the same time
  const gap=chat.playEnd<=ctx.currentTime,at=gap?ctx.currentTime+0.25:chat.playEnd;
  if(gap)for(let i=0,m=Math.min(n,96);i<m;i++)f[i]*=i/m;
  if(gap&&chat.ctrl){if(chat.firstPlay==null)chat.firstPlay=at;else chat.gaps.push(at-chat.firstPlay)}   // stalls, shown under the answer
  if(chat.ctrl&&chat.blocks){chat.t0b=chat.t0b??ctx.currentTime;chat.blocks.push(`${(n/24000).toFixed(2)}@${(ctx.currentTime-chat.t0b).toFixed(2)}${gap&&chat.firstPlay!==at?'!':''}`)}
  const ab=ctx.createBuffer(1,n,24000);ab.copyToChannel(f,0);const src=ctx.createBufferSource();src.buffer=ab;src.connect(chat.out);
  src.start(at);chat.playEnd=at+ab.duration;chat.sources.push(src);
  src.onended=()=>{chat.sources=chat.sources.filter(x=>x!==src)}}
function stopAnswer(){stopBarge();if(chat.ctrl){chat.ctrl.abort();chat.ctrl=null}chat.sources.forEach(x=>{try{x.stop()}catch{}});chat.sources=[];chat.playEnd=0;$('chatstop').disabled=!chat.rec}
const playing=()=>chat.pctx&&chat.playEnd>chat.pctx.currentTime;
function setTalk(){$('talklbl').textContent=chat.rec?t('Fertig','Done'):t('Sprechen','Speak');$('talk').classList.toggle('rec',!!chat.rec);$('talk').classList.toggle('ans',!chat.rec&&!!(chat.ctrl||playing()));$('chatstop').disabled=!(chat.rec||chat.ctrl||playing())}
function showSecure(){const port=CFG&&CFG.panel&&CFG.panel.https_port;const u=`https://${location.hostname}:${port}/`;
  $('chatsecure').style.display='block';$('chathttps').href=u;$('chathttps').textContent=port?u:t('https (im Panel unter Konfiguration einschalten)','https (enable it under Configuration)')}
async function chatTab(){if(!CFG)try{CFG=await (await api('/api/config')).json()}catch{}
  if(!window.isSecureContext)showSecure();setTalk()}
$('chatlog').dataset.empty=t('Sag etwas oder tippe unten eine Frage.','Say something or type a question below.');

// Simple voice activity detection: stop after ~0.8 s of silence once speech was heard.
function startVad(o={}){const ctx=audioCtx(),src=ctx.createMediaStreamSource(chat.stream),an=ctx.createAnalyser();
  an.fftSize=1024;src.connect(an);const buf=new Float32Array(an.fftSize);let floor=o.floor||0.01,heard=o.speaking?300:0,quiet=0,last=performance.now(),paused=false,lastSnap=last;
  const t0=o.floor?last-300:last;   // after a barge-in the room noise is already known and the user is talking
  const iv=setInterval(()=>{an.getFloatTimeDomainData(buf);let e=0;for(const v of buf)e+=v*v;const rms=Math.sqrt(e/buf.length);
    const now=performance.now(),dt=now-last;last=now;
    if(now-t0<300){floor=Math.max(floor*0.8,rms);chat.floor=floor;return}   // learn the room noise first
    chat.micLevel=Math.min(1,Math.max(0,rms-floor)*12);if(!S.auto)return;
    if(rms>Math.max(0.015,floor*2.5)){heard+=dt;quiet=0;chat.lastVoice=now}else quiet+=dt;
    if(heard>200&&(S.live||S.turn)){   // transcript every ~1.2 s (live view), and once at each pause
      if(quiet>=250){if(!paused){paused=true;liveSnap(true)}}
      else{paused=false;chat.turnWait=null;if(S.live&&now-lastSnap>1200){lastSnap=now;liveSnap()}}}
    if(heard>200&&quiet>(chat.turnWait||800))stopListening(false);
    else if(!heard&&now-t0>8000)stopListening(true);                 // nobody spoke
    else if(now-t0>60000)stopListening(false)},50);
  chat.vad={iv,src}}
function stopVad(){chat.micLevel=0;if(chat.vad){clearInterval(chat.vad.iv);try{chat.vad.src.disconnect()}catch{}chat.vad=null}}

async function startListening(o={}){stopBarge();stopAnswer();chat.turnWait=null;
  if(!window.isSecureContext||!navigator.mediaDevices){showSecure();chatSay(t('Mikrofon braucht https, siehe Hinweis oben.','The microphone needs https, see the note above.'));return}
  try{if(!chat.stream)chat.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
  catch(e){chatSay(t('Kein Zugriff aufs Mikrofon: ','No microphone access: ')+e.message);return}
  const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m=>window.MediaRecorder&&MediaRecorder.isTypeSupported(m))||'';
  const rec=o.rec||new MediaRecorder(chat.stream,mime?{mimeType:mime}:{}),parts=o.parts||[];
  rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};chat.parts=parts;chat.live.last=null;chat.lastVoice=o.speaking?performance.now():null;
  rec.onstop=()=>{stopVad();chat.rec=null;setTalk();const cancel=chat.cancelRec;chat.cancelRec=false;
    if(cancel){clearLive();chatSay(t('Bereit.','Ready.'));return}
    transcribe(new Blob(parts,{type:rec.mimeType||'audio/webm'}),performance.now(),rec)};
  if(rec.state==='inactive')rec.start();chat.rec=rec;setTalk();chatSay(o.speaking?t('Unterbrochen, ich höre zu …','Interrupted, listening …'):t('Ich höre zu …','Listening …'));startVad(o)}
// Barge-in: while the answer plays, the microphone keeps listening (the browser's echo
// cancellation removes most of the assistant's own voice). A recorder starts at the first sign of
// speech so the beginning is not lost; if the speech holds for 250 ms the answer stops and that
// recording becomes the next question, otherwise it is thrown away.
function startBarge(){if(chat.barge||!chat.stream||!S.barge)return;
  const ctx=audioCtx(),src=ctx.createMediaStreamSource(chat.stream),an=ctx.createAnalyser();an.fftSize=1024;src.connect(an);
  const buf=new Float32Array(an.fftSize),ob=new Float32Array(chat.out.fftSize),floor=Math.max(chat.floor||0.01,0.005);
  const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m=>window.MediaRecorder&&MediaRecorder.isTypeSupported(m))||'';
  let voiced=0,pre=null,parts=[],last=performance.now();
  const rms=(a,b)=>{a.getFloatTimeDomainData(b);let e=0;for(const v of b)e+=v*v;return Math.sqrt(e/b.length)};
  const iv=setInterval(()=>{const now=performance.now(),dt=now-last;last=now;
    if(!playing()&&!chat.ctrl){stopBarge();return}
    const m=rms(an,buf),out=rms(chat.out,ob),b=BARGE[S.barge_level]||BARGE.mid,thr=Math.max(b[0],floor*b[1],out*b[2]);
    chat.micLevel=Math.min(1,Math.max(0,m-floor)*12);
    if(m>thr*0.7){voiced+=dt;
      if(!pre){parts=[];pre=new MediaRecorder(chat.stream,mime?{mimeType:mime}:{});pre.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};pre.start()}}
    else{voiced=Math.max(0,voiced-dt*0.5);if(pre&&voiced===0){pre.onstop=null;try{pre.stop()}catch{}pre=null}}
    if(voiced>=250&&m>thr*0.5){const rec=pre;pre=null;stopBarge();
      startListening({rec,parts,floor,speaking:true})}},40);
  chat.barge={iv,src,stopPre:()=>{if(pre){pre.onstop=null;try{pre.stop()}catch{}pre=null}}}}
function stopBarge(){if(chat.barge){clearInterval(chat.barge.iv);try{chat.barge.src.disconnect()}catch{}chat.barge.stopPre();chat.barge=null;if(!chat.rec)chat.micLevel=0}}
function stopListening(cancel){if(chat.rec&&chat.rec.state!=='inactive'){chat.cancelRec=!!cancel;chat.rec.stop()}}

// The recording is sent as 16 kHz mono WAV: every ASR backend reads it, whatever the browser recorded.
async function toWav(blob,rate=16000){const raw=await audioCtx().decodeAudioData(await blob.arrayBuffer());
  const n=Math.max(1,Math.ceil(raw.duration*rate)),off=new OfflineAudioContext(1,n,rate),src=off.createBufferSource();
  src.buffer=raw;src.connect(off.destination);src.start();const pcm=(await off.startRendering()).getChannelData(0);
  const buf=new ArrayBuffer(44+pcm.length*2),v=new DataView(buf),w=(o,x)=>{for(let i=0;i<x.length;i++)v.setUint8(o+i,x.charCodeAt(i))};
  w(0,'RIFF');v.setUint32(4,36+pcm.length*2,true);w(8,'WAVEfmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);w(36,'data');v.setUint32(40,pcm.length*2,true);
  for(let i=0;i<pcm.length;i++)v.setInt16(44+2*i,Math.max(-1,Math.min(1,pcm[i]))*32767,true);
  return new Blob([buf],{type:'audio/wav'})}
async function transcribe(blob,tEnd,rec){chat.asrBusy=true;try{await transcribe2(blob,tEnd,rec)}finally{chat.asrBusy=false}}
async function asrText(blob){
  let file=blob,name='frage.'+(blob.type.includes('mp4')?'m4a':blob.type.includes('ogg')?'ogg':'webm');
  try{file=await toWav(blob);name='frage.wav'}catch{}            // fall back to the original recording
  const fd=new FormData();fd.append('file',file,name);fd.append('language',(CFG&&CFG.asr.default_language)||'auto');
  const d=await (await api('/api/test/asr',{method:'POST',body:fd})).json();
  // recognized voice: a signed one-time token the chat request sends back, kept with its own text
  return {text:(d.text||'').trim(),speaker:d.speaker||null}}
async function transcribe2(blob,tEnd,rec){chatSay(t('Erkenne Sprache …','Transcribing …'));
  // a live snapshot taken after the last voiced moment already holds the whole question
  const last=chat.live.last;chat.live.last=null;let r=null;
  if(last&&last.rec===rec&&chat.lastVoice!=null&&last.at>chat.lastVoice+150)r=await last.p;
  clearLive();
  if(!r)try{r=await asrText(blob)}catch(e){chatSay(t('Spracherkennung: ','Speech recognition: ')+e.message);return}
  if(!r.text){chatSay(t('Nichts verstanden.','Did not catch that.'));return}
  chat.asrBusy=false;ask(r.text,(performance.now()-tEnd)/1000,r.speaker)}
// Live transcript: the recording so far is transcribed about every second and shown as a pale
// bubble. requestData() flushes the recorder first so the snapshot holds the last moments too.
function liveSnap(pause){const rec=chat.rec,parts=chat.parts;if(!rec||rec.state!=='recording')return;
  if(chat.live.busy){chat.live.want=true;chat.live.pause=chat.live.pause||pause;return}
  chat.live.busy=true;chat.live.want=false;pause=pause||chat.live.pause;chat.live.pause=false;let started=false;
  const go=()=>{if(started)return;started=true;const at=performance.now(),n=parts.length;
    const p=asrText(new Blob(parts.slice(0,n),{type:rec.mimeType||'audio/webm'}))
      .then(r=>{const x=r.text;if(chat.rec===rec&&x){if(S.live)showLive(x);if(pause&&S.turn)turnCheck(x,at,rec)}return r}).catch(()=>null)
      .finally(()=>{chat.live.busy=false;if(chat.live.want&&chat.rec===rec)liveSnap()});
    chat.live.last={at,p,rec}};
  rec.addEventListener('dataavailable',go,{once:true});try{rec.requestData()}catch{go()}setTimeout(go,400)}
// Natural turn-taking: the pause transcript tells whether the sentence is finished. A finished
// one ends the turn right away (its transcript becomes the question, no second recognition);
// one that stops on "und", "weil", "ähm", a comma ... gets up to 2 s to go on.
const OPEN_WORDS=new Set(('und oder aber denn weil dass ob wenn falls obwohl sondern sowie bzw beziehungsweise entweder weder sowohl '+
  'ein eine einen einem einer eines mein meine meinen meinem meiner dein deine deinen deinem deiner sein seine seinen seinem '+
  'unser unsere unseren dem den des im ins zum zur für von vom bei beim über unter zwischen gegen ohne bis wegen während '+
  'äh ähm ehm öhm hm mhm also halt sozusagen quasi '+
  'and or but because that if when whether although unless than the a my your our their to of for with from at about into '+
  'um uh uhm er erm like which who whose').split(' '));
function turnState(x){const s=String(x).trim().replace(/["'»«“”„)\]]+$/u,'');if(!s)return '';
  const w=(s.match(/[\p{L}\p{N}]+(?=[^\p{L}\p{N}]*$)/u)||[''])[0].toLowerCase();
  if(OPEN_WORDS.has(w)||/(,|;|:|-|–|\.\.\.|…)$/.test(s))return 'open';
  return /[.?!]$/.test(s)?'done':''}
function turnCheck(x,at,rec){if(chat.rec!==rec||(chat.lastVoice||0)>at)return;   // talking again meanwhile
  const st=turnState(x);if(st==='done')stopListening(false);else if(st==='open')chat.turnWait=2000}
function showLive(x){if(!chat.liveEl){chat.liveEl=chatLog('user',x);chat.liveEl.classList.add('live')}else chat.liveEl.textContent=x;$('chatlog').scrollTop=1e9}
function clearLive(){if(chat.liveEl){chat.liveEl.parentNode.remove();chat.liveEl=null}}

async function ask(text,asrS,spk){
  if(S.daily&&chat.cid&&!chat.picked){const c=convos.load().find(x=>x.id===chat.cid);if(c&&c.updated<today0())openConvo(null)}   // past midnight
const ub=chatLog('user',text);const um={role:'user',content:text};chat.msgs.push(um);deletable(ub,um);let foreign=false;
  const el=chatLog('assistant','');$('fabtext').textContent='';let full='',llmS=null,audioS=null,err='';const searches=[],sources=[],mems=[],docs=[];
  const ctrl=new AbortController();chat.ctrl=ctrl;chat.firstPlay=null;chat.gaps=[];chat.blocks=[];chat.t0b=null;setTalk();chatSay(t('Antwort kommt …','Answer coming …'));
  try{const r=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify({messages:chat.msgs.slice(-20),tz:(()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch{return ''}})(),voice:PROFILE&&S.voice||undefined,speed:S.speed,length:S.length,reminders:PROFILE?undefined:rem.list,convo:chat.cid||undefined,speaker:spk&&spk.token||undefined})});
    const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
    for(;;){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
      while((i=buf.indexOf('\n\n'))>=0){const line=buf.slice(0,i).split('\n').find(l=>l.startsWith('data:'));buf=buf.slice(i+2);if(!line)continue;
        const ev=JSON.parse(line.slice(5));
        if(ev.type==='text'){full+=ev.delta;el.classList.remove('typing');el.textContent=full;$('fabtext').textContent=full;$('chatlog').scrollTop=1e9}
        else if(ev.type==='tts_request'){chat.blocks.push('| '+ev.chars+t(' Zeichen:',' chars:'))}
        else if(ev.type==='audio'){playPcm(ev.audio);chatSay(t('Spricht …','Speaking …'));startBarge()}
        else if(ev.type==='truncated'){full=full.slice(0,full.length-ev.drop).trimEnd();el.textContent=full+' … '+t('(Längenlimit erreicht: Konfiguration → Assistent → Max. Tokens)','(length limit reached: Configuration → Assistant → Max. tokens)')}
        else if(ev.type==='search'){chatSay(t('Suche im Netz: ','Searching the web: ')+ev.query);searches.push(ev.query)}
        else if(ev.type==='sources'){sources.push(...ev.items)}
        else if(ev.type==='calendar'){chatSay(t('Schaue in deinen Kalender …','Checking your calendar …'))}
        else if(ev.type==='briefing'){chatSay(t('Stelle dein Tagesbriefing zusammen …','Putting your daily briefing together …'))}
        else if(ev.type==='home'){chatSay('🏠 '+ev.command)}
        else if(ev.type==='home_done'){mems.push('🏠 '+(ev.ok?'':'⚠ ')+(ev.targets&&ev.targets.length?ev.targets.join(', ')+': ':'')+ev.text)}
        else if(ev.type==='historysearch'){chatSay(t('Schaue in früheren Gesprächen nach …','Looking through earlier conversations …'))}
        else if(ev.type==='docsearch'){chatSay(t('Suche in deinen Dokumenten: ','Searching your documents: ')+ev.query)}
        else if(ev.type==='docsources'){for(const n of ev.items)if(!docs.includes(n))docs.push(n)}
        else if(ev.type==='speaker'){const w=document.createElement('div');w.className='who';foreign=!!ev.foreign;
          w.textContent='🎙 '+ev.name+(foreign?t(' · nicht in diesem Verlauf gespeichert',' · not kept in this history'):'');ub.parentNode.appendChild(w)}
        else if(ev.type==='reminder'){rem.event(ev);mems.push(ev.action==='set'?t('Erinnerung: ','Reminder: ')+rem.when(ev.item.due)+' '+ev.item.text:t('Erinnerung gelöscht','Reminder cancelled'))}
        else if(ev.type==='memory'){mems.push((ev.action==='saved'?t('Gemerkt: ','Remembered: '):t('Vergessen: ','Forgotten: '))+ev.text)}
        else if(ev.type==='search_error'){chatSay(t('Websuche fehlgeschlagen: ','Web search failed: ')+ev.message)}
        else if(ev.type==='timing'){if(ev.llm_first_token!=null)llmS=ev.llm_first_token;if(ev.first_audio!=null)audioS=ev.first_audio}
        else if(ev.type==='error'){err=ev.code==='llm_auth'?t('Das LLM lehnt den API-Key ab (401). Trage den qwen38-Key unter Konfiguration → Assistent ein (steht auf dem Spark in ~/.config/qwen38/api-key) oder führe das Update aus, das ihn automatisch übernimmt.','The LLM rejected the API key (401). Enter the qwen38 key under Configuration → Assistant (on the Spark it is in ~/.config/qwen38/api-key) or run the update, which imports it automatically.'):ev.message}}}}
  catch(e){if(e.name!=='AbortError')err=e.message}
  const aborted=ctrl.signal.aborted;if(chat.ctrl===ctrl)chat.ctrl=null;
  // another person's voice: the exchange is theirs, so it stays out of this browser's history and context
  if(foreign){const i=chat.msgs.indexOf(um);if(i>=0)chat.msgs.splice(i,1)}
  else if(full.trim()){chat.msgs.push({role:'assistant',content:full.trim()});deletable(el,chat.msgs.at(-1))}else chat.msgs.pop();saveConvo();
  el.classList.remove('typing');if(!full.trim())el.textContent=aborted?t('(abgebrochen)','(cancelled)'):'–';
  if(sources.length){const d=document.createElement('div');d.className='src';
    d.innerHTML=`<span>${t('Gesucht','Searched')}: ${esc(searches.join(' · '))}</span>`+sources.slice(0,5).map((s,i)=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${i+1}. ${esc(s.title.slice(0,70))}</a>`).join('');el.appendChild(d)}
  if(docs.length){const d=document.createElement('div');d.className='mem';d.textContent=t('Aus deinen Dokumenten: ','From your documents: ')+docs.join(' · ');el.appendChild(d)}
  if(mems.length){const d=document.createElement('div');d.className='mem';d.textContent=mems.join(' · ');el.appendChild(d)}
  const f=v=>v==null?'–':v.toFixed(2)+' s';
  const chip=(k,v,hi)=>`<span class="chip${hi?' hi':''}">${k} <b>${f(v)}</b></span>`;
  $('chattiming').innerHTML=(asrS!=null?chip(t('Spracherkennung','Recognition'),asrS):'')+chip(t('LLM erstes Wort','LLM first word'),llmS)+chip(t('erster Ton','first audio'),audioS)+
    (asrS!=null&&audioS!=null?chip(t('hörbar nach','audible after'),asrS+audioS,true):'')+
    (chat.gaps.length?`<span class="chip" title="${t('Die Sprachausgabe kam nicht schnell genug nach','Speech output fell behind')}">${t('Aussetzer bei','stalls at')} <b>${chat.gaps.map(x=>x.toFixed(1)+' s').join(', ')}</b></span>`+
      `<div class="blocks">${t('Tonblöcke (Länge@Ankunft, ! = Aussetzer)','Audio blocks (length@arrival, ! = stall)')}: ${esc(chat.blocks.join(' '))}</div>`:'');
  if(err){chat.errAt=performance.now();chatSay(err);setTalk();return}
  if(aborted){setTalk();return}
  while(playing()&&!chat.ctrl&&!chat.rec)await new Promise(res=>setTimeout(res,100));   // wait until it has finished speaking
  setTalk();if(chat.ctrl||chat.rec)return;
  chatSay(t('Bereit.','Ready.'));if(S.hands)startListening()}


// Wake word "Hey Spark": while the assistant is idle the microphone keeps a short ring buffer of
// raw audio. Each burst of speech (up to 5 s) goes to the speech recognition on the Spark, told to
// expect the phrase; if the burst starts with it, the assistant listens, or answers right away
// when the question followed in the same breath. Nothing leaves the local network.
const wake={on:false,node:null,src:null,ring:[],seg:null,quiet:0,voiced:0,floor:0.01,busy:false,lock:null};
const wakeIdle=()=>!chat.rec&&!chat.ctrl&&!playing()&&!chat.asrBusy&&!wake.busy;
function matchWake(text){const tok=[...String(text).matchAll(/[\p{L}\p{N}]+/gu)].slice(0,6);
  const lev=(a,b)=>{const d=Array.from({length:b.length+1},(_,i)=>i);for(let i=1;i<=a.length;i++){let p=d[0];d[0]=i;
    for(let j=1;j<=b.length;j++){const q=d[j];d[j]=Math.min(d[j]+1,d[j-1]+1,p+(a[i-1]===b[j-1]?0:1));p=q}}return d[b.length]};
  const spark=w=>{w=w.toLowerCase();return lev(w,'spark')<=1||lev(w,'sparks')<=1||/^spar[ck]/.test(w)};
  const hey=w=>/^(hey|hei|hej|he|hi|ey|hallo|hello|ok|okay|oh)$/i.test(w);
  for(let i=0;i<tok.length;i++){const w=tok[i][0];let end=-1;
    if(/^he[yij]?spar[ck]/i.test(w))end=tok[i].index+w.length;
    else if(hey(w)&&tok[i+1]&&spark(tok[i+1][0]))end=tok[i+1].index+tok[i+1][0].length;
    if(end>=0){const r=String(text).slice(end).replace(/^[\s,.!?:;-]+/,'').trim();return {rest:r.charAt(0).toUpperCase()+r.slice(1)}}}
  return null}
function pcmWav(chunks,rate){let n=0;for(const c of chunks)n+=c.length;const f=new Float32Array(n);let o=0;for(const c of chunks){f.set(c,o);o+=c.length}
  const r=16000,m=Math.floor(n*r/rate),buf=new ArrayBuffer(44+m*2),v=new DataView(buf);
  const w=(p,s)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i))};
  w(0,'RIFF');v.setUint32(4,36+m*2,true);w(8,'WAVEfmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,r,true);v.setUint32(28,r*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);w(36,'data');v.setUint32(40,m*2,true);
  for(let i=0;i<m;i++){const s=Math.max(-1,Math.min(1,f[Math.floor(i*rate/r)]));v.setInt16(44+i*2,s*32767,true)}
  return new Blob([buf],{type:'audio/wav'})}
function chime(){try{const ctx=audioCtx(),o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=880;o.connect(g);g.connect(ctx.destination);
  g.gain.setValueAtTime(0.0001,ctx.currentTime);g.gain.exponentialRampToValueAtTime(0.2,ctx.currentTime+0.02);g.gain.exponentialRampToValueAtTime(0.0001,ctx.currentTime+0.18);
  o.start();o.stop(ctx.currentTime+0.2)}catch{}}
async function checkWake(chunks,rate){wake.busy=true;try{
  const fd=new FormData();fd.append('file',pcmWav(chunks,rate),'wake.wav');fd.append('language',(CFG&&CFG.asr.default_language)||'auto');fd.append('wake','Hey Spark');
  const text=((await (await api('/api/test/asr',{method:'POST',body:fd})).json()).text||'').trim();
  const m=text&&matchWake(text);if(!m||!wake.on)return;
  if(m.rest.split(/\s+/).filter(Boolean).length>=2){wake.busy=false;ask(m.rest,null)}
  else{chime();wake.busy=false;startListening()}}
  catch{}finally{wake.busy=false}}
async function startWake(){if(wake.on)return;
  if(!window.isSecureContext||!navigator.mediaDevices){showSecure();$('chatwake').checked=false;return}
  try{if(!chat.stream)chat.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
  catch(e){chatSay(t('Kein Zugriff aufs Mikrofon: ','No microphone access: ')+e.message);$('chatwake').checked=false;return}
  const ctx=audioCtx();wake.on=true;wake.src=ctx.createMediaStreamSource(chat.stream);wake.node=ctx.createScriptProcessor(4096,1,1);
  wake.src.connect(wake.node);wake.node.connect(ctx.destination);
  wake.node.onaudioprocess=e=>{const x=new Float32Array(e.inputBuffer.getChannelData(0)),dt=x.length/ctx.sampleRate;
    let s=0;for(const v of x)s+=v*v;const rms=Math.sqrt(s/x.length);
    if(!wakeIdle()){wake.seg=null;wake.ring=[];wake.voiced=0;return}
    const thr=Math.max(0.02,wake.floor*3);
    if(!wake.seg){wake.ring.push(x);if(wake.ring.length>4)wake.ring.shift();     // ~0.35 s before the speech
      if(rms>thr){wake.voiced+=dt;if(wake.voiced>=0.08){wake.seg=wake.ring.slice();wake.quiet=0;wake.len=0}}
      else{wake.voiced=0;wake.floor=wake.floor*0.95+rms*0.05}}
    else{wake.seg.push(x);wake.len+=dt;wake.quiet=rms>thr?0:wake.quiet+dt;
      if(wake.quiet>0.7||wake.len>5){const seg=wake.seg;wake.seg=null;wake.voiced=0;if(wake.len>0.4)checkWake(seg,ctx.sampleRate)}}};
  if(ctx.state==='suspended'){chatSay(t('Einmal tippen, dann lauscht der Assistent.','Tap once, then the assistant listens.'));document.addEventListener('pointerdown',()=>ctx.resume(),{once:true})}
  keepAwake();$('wakeind').hidden=false}
function stopWake(){wake.on=false;if(wake.node){wake.node.onaudioprocess=null;try{wake.src.disconnect();wake.node.disconnect()}catch{}}wake.node=wake.src=wake.seg=null;
  if(wake.lock){wake.lock.release().catch(()=>{});wake.lock=null}$('wakeind').hidden=true}
async function keepAwake(){if(wake.on&&'wakeLock' in navigator&&!document.hidden)try{wake.lock=await navigator.wakeLock.request('screen')}catch{}}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)keepAwake()});
setInterval(()=>{$('wakeind').classList.toggle('paused',!wakeIdle())},300);
try{$('chatwake').checked=localStorage.getItem('wake')==='1'}catch{}
$('chatwake').onchange=()=>{try{localStorage.setItem('wake',$('chatwake').checked?'1':'0')}catch{}if($('chatwake').checked)startWake();else stopWake()};
if($('chatwake').checked)startWake();
$('talk').onclick=()=>{audioCtx();if(MOBILE.matches&&$('talk').classList.contains('ans')){$('chatstop').click();return}if(chat.rec)stopListening(false);else startListening()};
$('chatstop').onclick=()=>{stopListening(true);stopAnswer();setTalk();chatSay(t('Gestoppt.','Stopped.'))};
$('searchtest').onclick=async()=>{$('searchmsg').textContent=t('Teste …','Testing …');
  try{const r=await (await api('/api/search-test?url='+encodeURIComponent($('chat.search_url').value.trim()))).json();$('searchmsg').textContent=`${r.results} ${t('Treffer in','results in')} ${r.seconds} s: ${r.first.map(x=>x.title).join(' · ').slice(0,120)}`}
  catch(e){$('searchmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('chatnew').onclick=()=>{stopListening(true);stopAnswer();openConvo(null);setTalk();chatSay(t('Bereit.','Ready.'))};
// Conversations are kept in this browser (localStorage), at most 30, newest first.
// Conversations stay in this browser, kept apart per profile (guests: "convos").
let PROFILE=null;
// Logged in, conversations live in the profile on the Spark (same list on every device); this
// page keeps a copy in convos.cache. Guests keep theirs in this browser only.
const convos={cache:[],
  load(){if(PROFILE)return this.cache;try{return JSON.parse(localStorage.getItem('convos')||'[]')}catch{return []}},
  local(l){try{localStorage.setItem('convos',JSON.stringify(l.slice(0,30)))}catch{}},
  put(c){if(PROFILE){this.cache=[c,...this.cache.filter(x=>x.id!==c.id)];
      api('/api/profile/convos',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)}).catch(()=>{})}
    else this.local([c,...this.load().filter(x=>x.id!==c.id)])},
  del(id){if(PROFILE){this.cache=this.cache.filter(x=>x.id!==id);api('/api/profile/convos/'+encodeURIComponent(id),{method:'DELETE'}).catch(()=>{})}
    else this.local(this.load().filter(x=>x.id!==id))},
  async sync(){if(!PROFILE){this.cache=[];return}
    // conversations this browser kept for the profile before they moved to the Spark
    let old=[];try{old=JSON.parse(localStorage.getItem('convos:'+PROFILE.id)||'[]')}catch{}
    for(const c of old)await api('/api/profile/convos',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)}).catch(()=>{});
    try{localStorage.removeItem('convos:'+PROFILE.id)}catch{}
    try{this.cache=await (await api('/api/profile/convos')).json()}catch{this.cache=[]}}};
function saveConvo(){if(!chat.msgs.length)return;
  if(!chat.cid)chat.cid=Date.now().toString(36);const first=chat.msgs.find(m=>m.role==='user');
  convos.put({id:chat.cid,title:(first?first.content:'').slice(0,60),updated:Date.now(),msgs:chat.msgs.slice(-60)});fillConvos()}
function fillConvos(){const l=convos.load(),d=x=>new Date(x).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  $('convosel').innerHTML=(chat.cid?'':`<option value="">${t('Neues Gespräch','New conversation')}</option>`)+
    l.map(c=>`<option value="${c.id}"${c.id===chat.cid?' selected':''}>${d(c.updated)} · ${esc(c.title||'…')}</option>`).join('');
  $('convodel').disabled=!chat.cid}
function openConvo(id,picked){const c=id&&convos.load().find(x=>x.id===id);chat.cid=c?c.id:null;chat.picked=!!(c&&picked);chat.msgs=c?c.msgs.slice():[];
  $('chatlog').innerHTML='';$('chattiming').textContent='';chat.msgs.forEach(m=>deletable(chatLog(m.role,m.content),m));fillConvos()}
// Speaks a text with this profile's voice (reminders, "read again"); Stop and barge-in end it.
async function sayText(text){stopAnswer();const ctrl=new AbortController();chat.ctrl=ctrl;chat.firstPlay=null;chat.gaps=[];chat.blocks=null;setTalk();chatSay(t('Spricht …','Speaking …'));
  try{const r=await api('/api/assistant/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal:ctrl.signal});
    const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
    for(;;){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
      while((i=buf.indexOf('\n\n'))>=0){const l=buf.slice(0,i);buf=buf.slice(i+2);if(!l.startsWith('data:'))continue;
        const ev=JSON.parse(l.slice(5));if(ev.type==='audio'){playPcm(ev.audio);startBarge()}}}}catch{}
  if(chat.ctrl!==ctrl)return;chat.ctrl=null;setTalk();
  while(playing()&&!chat.ctrl&&!chat.rec)await new Promise(r=>setTimeout(r,100));
  setTalk();if(!chat.ctrl&&!chat.rec)chatSay(t('Bereit.','Ready.'))}
// Deleting messages: a small button on each saved message (on hover, or after a tap on phones).
// A question goes together with its answer; the conversation is saved again without them.
function deletable(bubble,m){const d=bubble.parentNode;d._m=m;if(d.querySelector('.mdel'))return;
  const b=document.createElement('button');b.className='mdel';b.type='button';b.title=t('Löschen','Delete');
  b.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>';
  b.onclick=e=>{e.stopPropagation();deleteMsg(d)};
  if(m.role==='assistant'){const r=document.createElement('button');r.className='mdel mplay';r.type='button';r.title=t('Nochmal vorlesen','Read again');
    r.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>';
    r.onclick=e=>{e.stopPropagation();audioCtx();stopListening(true);sayText(d._m.content)};d.appendChild(r)}
  d.appendChild(b);
  bubble.addEventListener('click',()=>{if(window.getSelection&&String(window.getSelection()))return;
    document.querySelectorAll('#chatlog .msg.sel').forEach(x=>{if(x!==d)x.classList.remove('sel')});d.classList.toggle('sel')})}
function deleteMsg(d){if(chat.ctrl||chat.rec)return;   // not while an answer is running
  const i=chat.msgs.indexOf(d._m),gone=new Set([d._m]);
  if(i>=0&&chat.msgs[i].role==='user'&&chat.msgs[i+1]&&chat.msgs[i+1].role==='assistant')gone.add(chat.msgs[i+1]);
  chat.msgs=chat.msgs.filter(m=>!gone.has(m));
  for(const x of [...$('chatlog').children])if(x===d||gone.has(x._m))x.remove();
  if(chat.msgs.length)saveConvo();else if(chat.cid){convos.del(chat.cid);openConvo(null)}}
$('convosel').onchange=()=>{stopListening(true);stopAnswer();openConvo($('convosel').value||null,true);setTalk();chatSay(t('Bereit.','Ready.'))};
$('convodel').onclick=()=>{if(!chat.cid||!confirm(t('Dieses Gespräch löschen?','Delete this conversation?')))return;
  convos.del(chat.cid);stopListening(true);stopAnswer();openConvo(null)};
// A new day starts a new conversation (setting "daily"); older ones stay in the history.
const today0=()=>new Date().setHours(0,0,0,0);
const latestConvo=()=>{const c=convos.load()[0];return c&&(!S.daily||c.updated>=today0())?c.id:null};
openConvo(latestConvo());
