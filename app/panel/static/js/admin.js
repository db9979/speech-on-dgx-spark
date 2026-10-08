// Admin pages: monitoring, settings, tests, voices, logs, guides, system and the update lock.
const btns=(n,st)=>`<button class="b" onclick="act('${n}','restart',this)">${t('Neustart','Restart')}</button>`+(st==='active'||st==='activating'?`<button class="b" onclick="act('${n}','stop',this)">${t('Stopp','Stop')}</button>`:`<button class="b" onclick="act('${n}','start',this)">Start</button>`);
async function act(n,a,btn){btn.disabled=true;try{await api(`/api/service/${n}/${a}`,{method:'POST'})}catch(e){alert(e.message)}btn.disabled=false;refresh()}
window.act=act;

async function refresh(){
  let s;try{s=await (await api('/api/status')).json()}catch(e){$('hdr').textContent=t('Panel nicht erreichbar','Panel not reachable');return}
  const g=s.gpu||{},sy=s.system,H=s.history;
  $('hdr').textContent=(g.name||t('keine GPU','no GPU'))+' · '+new Date(s.time*1000).toLocaleTimeString();
  $('m-gpu').textContent=fmt(g.util,' %');$('m-mem').textContent=fmt(sy.mem_avail_gib,' GiB',1)+' / '+sy.mem_total_gib;
  $('m-temp').textContent=fmt(g.temp,' °C')+' · '+fmt(g.power,' W');$('m-cpu').textContent=fmt(sy.cpu,' %');
  spark($('c-gpu'),H.map(x=>x.gpu),100);spark($('c-mem'),H.map(x=>x.avail),sy.mem_total_gib);spark($('c-temp'),H.map(x=>x.temp),100);spark($('c-cpu'),H.map(x=>x.cpu),100);
  showAlerts(s.alerts);
  $('memnote').innerHTML=sy.mem_avail_gib<12&&!(s.alerts||[]).some(x=>x.kind==='memory')?`<div class="note">${t(`Nur noch ${fmt(sy.mem_avail_gib,' GiB',1)} frei. Unter ~8 GiB beendet DGX OS (earlyoom) Prozesse. Kleinere Modelle wählen oder einen Dienst stoppen.`,`Only ${fmt(sy.mem_avail_gib,' GiB',1)} free. Below ~8 GiB DGX OS (earlyoom) kills processes. Choose smaller models or stop a service.`)}</div>`:'';
  $('svc').innerHTML=Object.entries(s.services).map(([n,v])=>{const h=v.health||{};
    const st=h.status?pill(h.status):'';const err=h.error?`<div class="err">${esc(h.error)}</div>`:(h.last_error?`<div class="err mut">${t('letzter Fehler','last error')}: ${esc(h.last_error.error)}</div>`:'');
    return `<tr><td><b>${n.toUpperCase()}</b><div class="mut">:${v.port}</div></td><td>${pill(v.state)} ${st}${v.enabled?'':` <span class="pill">${t('deaktiviert','disabled')}</span>`}</td>
    <td>${esc(h.model||'')}<div class="mut">${t('geschätzt','estimated')} ~${v.estimate_gib} GiB${h.load_seconds?` · ${t('geladen in','loaded in')} ${h.load_seconds}s`:''}</div>${err}</td>
    <td>${h.requests??'–'}${h.failures?` <span class="err">(${h.failures} ${t('Fehler','errors')})</span>`:''}${h.busy?` <span class="pill warn">${t('arbeitet','busy')}</span>`:''}</td>
    <td>${fmt(h.avg_latency_s,' s',2)}</td><td>${fmt(h.avg_ttfa_s??h.avg_ttft_s,' s',2)}${h.streams?`<div class="mut">${h.streams} Streams</div>`:''}</td><td>${fmt(h.avg_rtf,'',2)}</td><td>${fmt(h.torch_cuda_reserved_gb,' GB',1)}</td>
    <td class="row">${btns(n,v.state)}</td></tr>`+(v.engines||[]).map(e=>`<tr><td class="mut" style="padding-left:20px">↳ ${e.name==='tts-design'?'VoiceDesign-Engine':'Engine'}<div>127.0.0.1:${e.port}</div></td><td>${pill(e.state)}</td>
    <td>${esc(e.model)}<div class="mut">${e.kind} · ${t('reserviert','reserves')} ~${e.estimate_gib} GiB</div></td><td colspan=5></td><td class="row">${btns(e.name,e.state)}</td></tr>`).join('')}).join('');
  $('q38none').style.display=s.qwen38.length?'none':'block';
  $('q38').innerHTML=s.qwen38.map(q=>`<tr><td>${esc(q.unit)}</td><td>${pill(q.state)}</td><td>${q.mem_fraction!=null?(q.mem_fraction*100).toFixed(0)+t(' % des Pools',' % of the pool'):'–'}</td></tr>`).join('');
  $('gp').innerHTML=(g.processes||[]).map(p=>`<tr><td>${esc(p.pid)}</td><td>${esc(p.name)}</td><td>${p.mem_mib!=null?fmt(p.mem_mib/1024,' GiB',1):'–'}</td></tr>`).join('')||'<tr><td class="mut" colspan=3>–</td></tr>';
}

let CFG=null;
async function loadLangs(){const l=await (await api('/api/languages')).json();document.querySelectorAll('select.langs').forEach(s=>s.innerHTML=l.map(x=>`<option>${x}</option>`).join(''))}
async function instrHint(sel){if(!CFG)try{CFG=await (await api('/api/config')).json()}catch{return}const m=(sel?$('tts.model').value:CFG.tts.model)||'';const small=/0\.6B/i.test(m);
  document.querySelectorAll('.instrhint').forEach(e=>e.innerHTML=small?t('<b>Hinweis:</b> '+m.split('/').pop()+' wertet Anweisungen nicht aus (laut Qwen nur die 1.7B-Modelle). Für Stilsteuerung Qwen3-TTS-12Hz-1.7B-CustomVoice wählen; braucht etwa 2 bis 3 GiB mehr Speicher.','<b>Note:</b> '+m.split('/').pop()+' ignores instructions (per Qwen only the 1.7B models follow them). For style control choose Qwen3-TTS-12Hz-1.7B-CustomVoice; it needs about 2 to 3 GiB more memory.'):t('Beschreibung in normaler Sprache, z. B. Tonfall, Tempo, Emotion, Rolle. Deutsch oder Englisch.','Plain-language description, e.g. tone, pace, emotion, role. German or English.'))}
async function loadCfg(){CFG=await (await api('/api/config')).json();
  const vo=CFG.tts.backend==='vllm-omni';$('ttsbackend').textContent=CFG.tts.backend;
  $('ttsbackendnote').textContent=vo?t('(gestreamte Ausgabe)','(streamed output)'):t('(ohne Streaming; umstellen mit sudo ./install.sh --tts-backend vllm-omni)','(no streaming; switch with sudo ./install.sh --tts-backend vllm-omni)');
  $('enginecfg').style.display=vo?'block':'none';$('ttsdtype').style.display=vo?'none':'block';
  const av=CFG.asr.backend==='vllm';$('asrbackend').textContent=CFG.asr.backend;
  $('asrbackendnote').textContent=av?t('(viele Anfragen gleichzeitig, gestreamter Text)','(many concurrent requests, streamed text)'):t('(eine Anfrage nach der anderen; umstellen mit sudo ./install.sh --asr-backend vllm)','(one request at a time; switch with sudo ./install.sh --asr-backend vllm)');
  $('asrengine').style.display=av?'block':'none';$('asrtf').style.display=av?'none':'block';
  for(const[sec,o]of Object.entries(CFG))for(const[k,v]of Object.entries(o)){const el=$(sec+'.'+k);if(!el)continue;
    if(el.type==='checkbox')el.checked=v;else{if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value==v))el.add(new Option(v));el.value=Array.isArray(v)?v.join(', '):v}};instrHint();
  getDefaults=await renderSet($('chatdefaults'),{...SDEF,...(CFG.chat.defaults||{})},null);
  asrRec();cfgDeps();document.querySelectorAll('.pane').forEach(p=>markDirty(p,false));document.querySelectorAll('.savemsg').forEach(m=>m.textContent='')}
let getDefaults=null;
// Parakeet has no model choice and no engine: hide those settings while it is chosen.
function asrRec(){const qw=$('asr.recognizer').value!=='parakeet';$('asrqwen').style.display=qw?'':'none';
  $('asrengine').style.display=qw&&CFG.asr.backend==='vllm'?'block':'none'}
$('asr.recognizer').addEventListener('change',asrRec);
// Configuration in sub-tabs; each one saves only its own fields (the server restarts only
// the services whose settings changed).
const cfgPane=p=>{document.querySelectorAll('#cfgnav button').forEach(b=>b.classList.toggle('on',b.dataset.p===p));
  document.querySelectorAll('.pane').forEach(x=>x.classList.toggle('on',x.id==='pane-'+p));try{localStorage.setItem('cfgpane',p)}catch{}};
// phones: the settings open as a list of pages; a tapped page fills the screen with "back" on top
document.querySelectorAll('#cfgnav button').forEach(b=>b.onclick=()=>{cfgPane(b.dataset.p);document.querySelector('.cfgwrap').classList.add('sub');window.scrollTo(0,0)});
$('cfgback').onclick=()=>{document.querySelector('.cfgwrap').classList.remove('sub');window.scrollTo(0,0)};
try{const p=localStorage.getItem('cfgpane');if(p&&$('pane-'+p))cfgPane(p)}catch{}
// Details of a feature show only while it is on (Websuche pane, speaker strictness).
function cfgDeps(){const on=id=>{const e=$(id);return !e||e.checked};
  document.querySelectorAll('#pane-cfg [data-show],[data-show]').forEach(x=>x.style.display=on(x.dataset.show)?'':'none');
  const kb=document.querySelector('#cfgnav button[data-p="know"]');kb.style.display=on('chat.search')?'':'none';
  if(!on('chat.search')&&$('pane-know').classList.contains('on'))cfgPane('feat')}
['chat.search','chat.speaker_id'].forEach(id=>$(id).addEventListener('change',cfgDeps));
const markDirty=(pane,on)=>{const b=document.querySelector(`#cfgnav button[data-p="${pane.id.slice(5)}"]`);if(b)b.classList.toggle('dirty',on)};
document.querySelectorAll('.pane').forEach(pane=>{const f=e=>{if(/^pw/.test(e.target.id))return;markDirty(pane,true)};pane.addEventListener('input',f);pane.addEventListener('change',f)});
document.querySelectorAll('.savebtn').forEach(btn=>btn.onclick=async()=>{const pane=$('pane-'+btn.dataset.p),msg=btn.nextElementSibling;
  const n=JSON.parse(JSON.stringify(CFG));if(getDefaults&&pane.contains($('chatdefaults')))n.chat.defaults=getDefaults();
  for(const[sec,o]of Object.entries(n))for(const k of Object.keys(o)){const el=$(sec+'.'+k);if(!el||!pane.contains(el))continue;
    o[k]=el.type==='checkbox'?el.checked:el.dataset.list?el.value.split(/[\s,;]+/).filter(Boolean):el.type==='number'||el.dataset.num?Number(el.value):el.value}
  msg.textContent=t('Speichere…','Saving…');
  try{const r=await (await api('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(n)})).json();
    msg.innerHTML=t('Gespeichert.','Saved.')+(r.restarted.length?t(' Neu gestartet: ',' Restarted: ')+r.restarted.join(', ').toUpperCase()+t(' (Modell lädt neu).',' (model reloads).'):'')+(r.stopped&&r.stopped.length?t(' Gestoppt: ',' Stopped: ')+r.stopped.join(', ').toUpperCase()+'.':'')+(r.errors&&r.errors.length?`<div class="err">${esc(r.errors.join('\n'))}</div>`:'')+(r.panel_restart_needed?t(' Panel-Port ändert sich nach: ',' Panel port changes after: ')+'sudo systemctl restart speech-spark-panel':'');CFG=n;markDirty(pane,false)}
  catch(e){msg.innerHTML=`<span class="err">${esc(e.message)}</span>`}});

$('asrgo').onclick=async()=>{const f=$('asrfile').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);fd.append('language',$('asrlang').value);
  $('asrmsg').textContent=t('läuft…','running…');$('asrout').style.display='none';
  try{const r=await (await api('/api/test/asr',{method:'POST',body:fd})).json();$('asrmsg').textContent=`${r.processing_s}s ${t('für','for')} ${fmt(r.duration,' s',1)} Audio`;
    $('asrout').textContent=`[${r.language||'auto'}] ${r.text}`;$('asrout').style.display='block'}catch(e){$('asrmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
async function loadVoices(){const v=await (await api('/api/tts/voices')).json();
  $('ttsvoice').innerHTML=v.voices.length?v.voices.map(x=>`<option>${esc(x)}</option>`).join(''):`<option value="">${t('(Standard)','(default)')}</option>`;
  $('ttsvoice').disabled=v.model_kind==='voice_design'}
$('ttsgo').onclick=async()=>{const body={input:$('ttstext').value,voice:$('ttsvoice').value||null,language:$('ttslang').value,instruct:$('ttsinstr').value||null};
  if($('ttstask').value)body.task_type=$('ttstask').value;
  $('ttsmsg').textContent=t('läuft…','running…');$('ttsgo').disabled=true;
  try{if($('ttsstream').checked)await ttsStream(body);else{
    const r=await api('/api/test/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const b=await r.blob();$('ttsaudio').src=URL.createObjectURL(b);$('ttsaudio').style.display='block';$('ttsaudio').play();$('ttsmsg').textContent=`${t('fertig nach','done after')} ${r.headers.get('x-processing-seconds')||'?'} s`}}
  catch(e){$('ttsmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}
  $('ttsgo').disabled=false};
// Plays the SSE stream (base64 PCM 16 bit mono 24 kHz) as it arrives, like a streaming client would.
async function ttsStream(body){const t0=performance.now();const r=await api('/api/test/tts-stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const AC=window.AudioContext||window.webkitAudioContext;let ctx;try{ctx=new AC({sampleRate:24000})}catch{ctx=new AC()}let at=ctx.currentTime+0.05,first=null,bytes=0,buf='';
  const rd=r.body.getReader(),dec=new TextDecoder();$('ttsaudio').style.display='none';
  const play=b64=>{const bin=atob(b64),n=bin.length>>1;if(!n)return;const f=new Float32Array(n);
    for(let i=0;i<n;i++){let v=bin.charCodeAt(2*i)|(bin.charCodeAt(2*i+1)<<8);if(v>=32768)v-=65536;f[i]=v/32768}
    const ab=ctx.createBuffer(1,n,24000);ab.copyToChannel(f,0);const src=ctx.createBufferSource();src.buffer=ab;src.connect(ctx.destination);
    at=Math.max(at,ctx.currentTime);src.start(at);at+=ab.duration;bytes+=n*2};
  for(;;){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
    while((i=buf.indexOf('\n\n'))>=0){const ev=buf.slice(0,i);buf=buf.slice(i+2);const line=ev.split('\n').find(l=>l.startsWith('data:'));if(!line)continue;
      const d=JSON.parse(line.slice(5));if(d.type==='speech.audio.delta'){if(first===null){first=(performance.now()-t0)/1000;$('ttsmsg').textContent=`${t('erster Ton nach','first audio after')} ${first.toFixed(2)} s …`}play(d.audio)}
      else if(d.type==='speech.audio.error')throw new Error(d.error&&d.error.message||t('Fehler im Stream','error in stream'))}}
  $('ttsmsg').textContent=`${t('erster Ton nach','first audio after')} ${first!=null?first.toFixed(2):'?'} s · ${(bytes/48000).toFixed(1)} s ${t('Audio in','audio in')} ${((performance.now()-t0)/1000).toFixed(2)} s`}

async function loadClone(){const l=await (await api('/api/clone-voices')).json();
  $('vlist').innerHTML=l.map(n=>`<tr><td>${esc(n)}</td><td style="text-align:right;white-space:nowrap"><button class="b" onclick="playRef('${escq(n)}')">${t('Referenz anhören','Play reference')}</button> <button class="b" onclick="location.href='/api/clone-voices-export?names='+encodeURIComponent('${escq(n)}')">${t('Exportieren','Export')}</button> <button class="b" onclick="delVoice('${escq(n)}')">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine.','None yet.')}</td></tr>`}
$('vexpall').onclick=()=>{location.href='/api/clone-voices-export'};
$('vimpbtn').onclick=()=>$('vimpfile').click();
$('vimpfile').onchange=async()=>{const f=$('vimpfile').files[0];if(!f)return;$('vimpfile').value='';
  const fd=new FormData();fd.append('file',f);fd.append('conflict',$('vimpconflict').value);$('vimpmsg').textContent=t('Importiere …','Importing …');
  try{const r=await (await api('/api/clone-voices-import',{method:'POST',body:fd})).json();
    const ok=r.voices.filter(v=>v.result==='imported'),sk=r.voices.filter(v=>v.result==='skipped');
    $('vimpmsg').textContent=t('Importiert: ','Imported: ')+(ok.map(v=>v.as===v.name?v.name:`${v.name} → ${v.as}`).join(', ')||'–')+
      (sk.length?' · '+t('übersprungen: ','skipped: ')+sk.map(v=>v.name).join(', '):'');loadClone()}
  catch(e){$('vimpmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.playRef=n=>{const a=new Audio('/api/clone-voices/'+encodeURIComponent(n)+'.wav');a.play()};
window.delVoice=async n=>{if(!confirm(t(`Stimme ${n} löschen?`,`Delete voice ${n}?`)))return;await api('/api/clone-voices/'+encodeURIComponent(n),{method:'DELETE'});loadClone()};
// Record the reference with the microphone: 24 kHz mono WAV, transcript filled in by the ASR.
const vr={rec:null,stream:null,blob:null,iv:null};
// The reading text sets the language the cloned voice speaks best, independent of the panel language.
const READ_TEXT={de:'Guten Tag. Ich spreche diesen Text in ruhigem Ton und normalem Tempo, damit meine Stimme gut nachgebildet werden kann. Danach klingt die Sprachausgabe so wie ich.',en:'Hello. I am reading this text in a calm voice and at a normal pace, so that my voice can be reproduced well. After that, the speech output will sound like me.'};
function setReadLang(l){$('vreadlang').value=l;$('vread').textContent=READ_TEXT[l];try{localStorage.setItem('vreadlang',l)}catch{}}
{let l='de';try{l=localStorage.getItem('vreadlang')||'de'}catch{}setReadLang(READ_TEXT[l]?l:'de')}
$('vreadlang').onchange=e=>setReadLang(e.target.value);
$('vrec').onclick=async()=>{
  if(vr.rec){vr.rec.stop();return}
  if(!window.isSecureContext||!navigator.mediaDevices){const port=CFG&&CFG.panel&&CFG.panel.https_port,u=`https://${location.hostname}:${port||31443}/`;
    $('vsecure').style.display='block';const a=document.querySelector('.vhttps');a.href=u;a.textContent=u;return}
  try{vr.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:true,autoGainControl:true,channelCount:1}})}
  catch(e){$('vmsg').innerHTML=`<span class="err">${esc(t('Kein Zugriff aufs Mikrofon: ','No microphone access: ')+e.message)}</span>`;return}
  const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m=>window.MediaRecorder&&MediaRecorder.isTypeSupported(m))||'';
  const rec=new MediaRecorder(vr.stream,mime?{mimeType:mime}:{}),parts=[];vr.rec=rec;
  const ctx=audioCtx(),src=ctx.createMediaStreamSource(vr.stream),an=ctx.createAnalyser();an.fftSize=1024;src.connect(an);const buf=new Float32Array(an.fftSize);
  const t0=performance.now();let peak=0;
  vr.iv=setInterval(()=>{an.getFloatTimeDomainData(buf);let m=0;for(const v of buf)m=Math.max(m,Math.abs(v));peak=Math.max(peak,m);
    $('vlevel').style.width=Math.min(100,m*140)+'%';const s=(performance.now()-t0)/1000;$('vtime').textContent=s.toFixed(1).replace('.',L==='en'?'.':',')+' s';
    if(s>=20)rec.stop()},60);
  rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};
  rec.onstop=async()=>{clearInterval(vr.iv);src.disconnect();vr.stream.getTracks().forEach(x=>x.stop());vr.rec=null;$('vlevel').style.width='0';
    $('vrec').classList.remove('rec');$('vrec').textContent=t('Neu aufnehmen','Record again');
    const secs=(performance.now()-t0)/1000;
    try{vr.blob=await toWav(new Blob(parts,{type:rec.mimeType||'audio/webm'}),24000)}catch(e){$('vmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
    $('vplay').src=URL.createObjectURL(vr.blob);$('vplay').style.display='block';$('vfile').value='';
    const warn=secs<4?t('Etwas kurz, 5–15 Sekunden klonen besser. ','A bit short, 5–15 seconds clone better. '):peak<0.08?t('Sehr leise, näher ans Mikrofon. ','Very quiet, move closer to the microphone. '):'';
    $('vmsg').textContent=warn+t('Erkenne den gesprochenen Text …','Transcribing what you said …');
    const fd=new FormData();fd.append('file',vr.blob,'ref.wav');fd.append('language',$('vreadlang').value==='en'?'English':'German');
    try{const r=await (await api('/api/test/asr',{method:'POST',body:fd})).json();if((r.text||'').trim())$('vtext').value=r.text.trim();
      $('vmsg').textContent=warn+t('Bitte das Transkript prüfen, dann „Hinzufügen“.','Check the transcript, then "Add".')}
    catch(e){$('vtext').value=$('vtext').value||$('vread').textContent.trim();$('vmsg').textContent=warn+t('Spracherkennung nicht erreichbar, Vorlesetext als Transkript übernommen.','Speech recognition unavailable, used the reading text as transcript.')}};
  rec.start();$('vrec').classList.add('rec');$('vrec').textContent=t('Aufnahme beenden','Stop recording');$('vmsg').textContent='';$('vplay').style.display='none';vr.blob=null};
$('vfile').onchange=()=>{vr.blob=null;$('vplay').style.display='none'};
$('vadd').onclick=async()=>{const f=vr.blob||$('vfile').files[0];if(!f||!$('vname').value){$('vmsg').textContent=t('Name und Aufnahme (oder Datei) fehlen.','Name and recording (or file) are missing.');return}const fd=new FormData();fd.append('name',$('vname').value);fd.append('text',$('vtext').value);fd.append('file',f,vr.blob?'ref.wav':f.name);
  try{await api('/api/clone-voices',{method:'POST',body:fd});$('vmsg').textContent=t('Hinzugefügt.','Added.');loadClone()}catch(e){$('vmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};

const AUDIT={admin_login:t('Admin angemeldet','admin signed in'),admin_login_failed:t('Admin-Passwort falsch','wrong admin password'),
  admin_basic_failed:t('Admin-Passwort (Skript) falsch','wrong admin password (script)'),admin_password_failed:t('altes Passwort falsch','wrong current password'),
  admin_password_changed:t('Admin-Passwort geändert','admin password changed'),profile_login:t('Profil angemeldet','profile signed in'),
  profile_login_failed:t('PIN falsch','wrong PIN'),profile_logout_all:t('überall abgemeldet','logged out everywhere'),
  profile_device_removed:t('Gerät gesperrt','device blocked'),foreign_page_refused:t('fremde Seite abgewiesen','foreign page refused'),
  backup:t('Sicherung','backup'),restore:t('Wiederherstellung','restore'),watchdog:t('Wächter','watchdog')};
async function auditText(){const d=await (await api('/api/audit?limit=500')).json();
  return d.events.slice().reverse().map(e=>{const who=e.who||(e.uid&&d.names[e.uid])||e.name||'';
    const what=e.event==='change'?`${e.method} ${e.path} → ${e.status}`:(AUDIT[e.event]||e.event)+(e.locked?t(` – gesperrt für ${e.locked} s`,` – locked for ${e.locked} s`):'')+(e.detail?' – '+e.detail:'');
    return `${new Date(e.t*1000).toLocaleString()}  ${(e.ip||'').padEnd(15)}  ${who?who+': ':''}${what}`}).join('\n')}
async function loadLogs(){const el=$('logout'),txt=($('logsvc').value==='audit'?await auditText():await (await api('/api/logs/'+$('logsvc').value+'?lines=300')).text())||t('(leer)','(empty)');
  if(el.textContent!==txt)el.textContent=txt;if($('logfollow').checked)el.scrollTop=1e9}
try{$('logfollow').checked=localStorage.getItem('logfollow')!=='0'}catch{}
$('logfollow').onchange=()=>{try{localStorage.setItem('logfollow',$('logfollow').checked?'1':'0')}catch{}if($('logfollow').checked)loadLogs()};
setInterval(()=>{if($('logfollow').checked&&$('logs').classList.contains('on')&&!document.hidden)loadLogs().catch(()=>{})},3000);
$('tts.model').addEventListener('change',()=>instrHint(true));$('logload').onclick=loadLogs;$('logsvc').onchange=loadLogs;


function kv(rows){return rows.map(([k,v])=>`<tr><td class="mut" style="width:40%">${k}</td><td><code>${esc(v)}</code> <button class="b" style="padding:1px 6px;font-size:12px" onclick="copyString(this.previousElementSibling.textContent,this)">${t('kopieren','copy')}</button></td></tr>`).join('')}
async function loadInt(){const c=await (await api('/api/config')).json();const v=await (await api('/api/tts/voices')).json();
  const host=location.hostname,asr=`http://${host}:${c.asr.port}/v1`,tts=`http://${host}:${c.tts.port}/v1`,key=c.api.key||t('beliebig, z. B. sk-local','anything, e.g. sk-local');
  const voice=c.tts.default_voice||(v.voices[0]||'ryan');
  $('int-ep').innerHTML=kv([[t('Spracherkennung (STT)','Speech recognition (STT)'),asr+'/audio/transcriptions'],[t('Sprachausgabe (TTS)','Speech output (TTS)'),tts+'/audio/speech'],[t('API-Schlüssel','API key'),c.api.key||t('(keiner gesetzt)','(none set)')]]);
  $('int-owui-stt').innerHTML=kv([['Speech-to-Text Engine','OpenAI'],['API Base URL',asr],['API Key',key],['STT Model',c.asr.model]]);
  $('int-owui-tts').innerHTML=kv([['Text-to-Speech Engine','OpenAI'],['API Base URL',tts],['API Key',key],['TTS Model',c.tts.model],['TTS Voice',voice],[t('Zusätzliche TTS-Parameter (JSON, optional)','Additional TTS parameters (JSON, optional)'),JSON.stringify({temperature:c.tts.temperature,top_p:c.tts.top_p,seed:c.tts.seed})],[t('Antwort aufteilen','Response splitting'),t('Absätze (Paragraphs)','Paragraphs')]]);
  const panelUrl=`http://${host}:${(c.panel&&c.panel.port)||31080}`;
  $('int-pebble').innerHTML=kv([[t('Spark-Adresse in der Uhr-App','Spark address in the watch app'),panelUrl],[t('App-Datei','App file'),panelUrl+'/pebble/speech-spark.pbw']]);
  $('int-pbw').href=panelUrl+'/pebble/speech-spark.pbw';
  const siriBase=location.protocol==='https:'?location.origin:panelUrl;
  $('int-siri').innerHTML=kv([['URL',siriBase+'/api/siri/ask'],[t('Methode','Method'),'POST'],['Header','X-Speech-Device: sd_…'],[t('Haupttext (JSON)','Request body (JSON)'),'{"text": "…"}'],[t('Antwort','Answer'),'{"answer": "…"}']]);
  $('int-voices').textContent=v.model_kind==='voice_design'?t('VoiceDesign-Modell: die Stimme wird über die Standard-Anweisung beschrieben.','VoiceDesign model: the voice is described by the default instruction.'):(v.voices.join(', ')||t('(Dienst lädt noch)','(service still loading)'));
  const auth=c.api.key?` \\\n  -H "Authorization: Bearer ${c.api.key}"`:'';
  const hello=t('Hallo aus der Spark.','Hello from the Spark.'),lng=t('German','English'),code=t('de','en'),fn=t('hallo','hello');
  $('int-curl').textContent=`# ${t('Text -> Sprache','Text -> speech')} (mp3)
curl ${tts}/audio/speech${auth} \\
  -H "Content-Type: application/json" \\
  -d '{"model":"qwen3-tts","input":"${hello}","voice":"${voice}","language":"${lng}"}' -o ${fn}.mp3

# ${t('Sprache -> Text','Speech -> text')}
curl ${asr}/audio/transcriptions${auth} \\
  -F file=@${fn}.mp3 -F language=${code}`;
  $('int-py').textContent=`from openai import OpenAI

tts = OpenAI(base_url="${tts}", api_key="${c.api.key||'sk-local'}")
stt = OpenAI(base_url="${asr}", api_key="${c.api.key||'sk-local'}")

with tts.audio.speech.with_streaming_response.create(
        model="qwen3-tts", voice="${voice}", input="${hello}") as r:
    r.stream_to_file("${fn}.mp3")

with open("${fn}.mp3", "rb") as f:
    print(stt.audio.transcriptions.create(model="qwen3-asr", file=f, language="${code}").text)`;}
$('genkey').onclick=()=>{const a=new Uint8Array(18);crypto.getRandomValues(a);$('api.key').value='sk-'+[...a].map(x=>x.toString(16).padStart(2,'0')).join('')};

let updPoll=null;
async function loadSys(check=false){let u;try{u=await (await api('/api/update'+(check?'?check=true':''))).json()}catch(e){$('updstate').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  const i=u.installed||{},r=u.remote||{};
  $('sysver').innerHTML=kvp([[t('Installiert','Installed'),i.short?`${i.short} · ${new Date(i.date).toLocaleString()}`:'–'],[t('Änderung','Change'),i.subject||'–'],['Engines',i.engine||'–'],[t('Quelle','Source'),i.remote||'–'],[t('Zuletzt geprüft','Last checked'),r.checked?new Date(r.checked*1000).toLocaleTimeString():'–']]);
  updBadge(r);loadBench();loadLive();loadBak();
  const pv=u.previous;$('updprevrow').style.display=pv&&!u.running?'flex':'none';
  if(pv)$('updprevtxt').textContent=(pv.version||pv.short||'')+(pv.subject?' · '+pv.subject:'');
  if(u.running){$('updstate').innerHTML=t('<span class="pill warn">Update läuft</span> Die Seite lädt neu, wenn das Panel neu startet.','<span class="pill warn">Update running</span> The page reloads when the panel restarts.');$('updgo').disabled=true;$('updstop').style.display='inline-block';
    if(!updPoll)updPoll=setInterval(()=>loadSys(),3000)}
  else{if(updPoll){clearInterval(updPoll);updPoll=null}$('updstop').style.display='none';
    $('updstate').innerHTML=r.error?`<span class="err">${esc(r.error)}</span>`:r.behind===0?`<span class="pill ok">${t('aktuell','up to date')}</span>`:
      `<span class="pill warn">${t('Update verfügbar','Update available')}</span> ${r.behind>0?r.behind+t(' Änderung(en)',' change(s)'):''}`+(u.last_result&&u.last_result!=='success'&&u.last_finished?` <span class="err">${t('Letztes Update fehlgeschlagen','Last update failed')} (${esc(u.last_result)}), ${t('siehe Protokoll','see log')}.</span>`:'');
    $('updgo').disabled=!(r.behind&&r.behind!==0)}
  $('updcommits').innerHTML=(r.commits||[]).length?'<table>'+r.commits.slice().reverse().map(c=>`<tr><td class="mut" style="width:70px"><code>${esc(c.sha)}</code></td><td>${esc(c.title)}</td></tr>`).join('')+'</table>':'';
  $('updlog').textContent=await (await api('/api/logs/update?lines=200')).text()||t('(noch kein Update gelaufen)','(no update has run yet)');$('updlog').scrollTop=1e9}
const kvp=rows=>rows.map(([k,v])=>`<tr><td class="mut" style="width:35%">${k}</td><td>${esc(v)}</td></tr>`).join('');
// Update notice on top of every page, also the assistant, for the logged-in admin only; "✕" hides
// it until a newer version appears.
function updBanner(r){const on=ADMIN&&r&&r.behind&&r.behind!==0&&r.latest;let hid='';try{hid=localStorage.getItem('updhide')||''}catch{}
  $('updbanner').style.display=on&&hid!==r.latest?'flex':'none';if(!on)return;
  $('updbtext').textContent=t('Update verfügbar','Update available')+(r.version?': '+r.version:'')+(r.behind>0?t(` (${r.behind} Änderung${r.behind>1?'en':''})`,` (${r.behind} change${r.behind>1?'s':''})`):'');
  $('updbx').onclick=()=>{try{localStorage.setItem('updhide',r.latest)}catch{}$('updbanner').style.display='none'}}
$('updbgo').onclick=()=>{$('updbanner').style.display='none';goSec('sys')};
function updBadge(r){window.UPD=r;updBanner(r);const on=r&&r.behind&&r.behind!==0;$('updbadge').style.display=on?'inline-block':'none';
  document.querySelectorAll('.subbadge').forEach(x=>x.style.display=on?'inline-block':'none')}
$('updcheck').onclick=()=>loadSys(true);
let benchPoll=null;
async function loadBench(){let b;try{b=await (await api('/api/bench')).json()}catch(e){$('benchmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  $('benchgo').disabled=b.running;
  $('benchmsg').textContent=b.running?t('läuft…','running…'):b.result?t('letzte Messung: ','last measurement: ')+new Date(b.result.time*1000).toLocaleString():'';
  $('benchout').textContent=b.running?b.log.join('\n'):(b.report||t('(noch nicht gemessen)','(not measured yet)'));
  if(b.running&&!benchPoll)benchPoll=setInterval(loadBench,2000);
  if(!b.running&&benchPoll){clearInterval(benchPoll);benchPoll=null}}
$('benchgo').onclick=async()=>{try{await api('/api/bench',{method:'POST'});loadBench()}catch(e){$('benchmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('updstop').onclick=async()=>{if(!confirm(t('Update abbrechen? Was schon installiert ist, bleibt. Ein späteres Update holt den Rest nach.','Cancel the update? What is already installed stays. A later update installs the rest.')))return;
  try{await api('/api/update',{method:'DELETE'});$('updmsg').textContent=t('abgebrochen','cancelled');loadSys()}
  catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// Update lock: a progress window over the whole page; the server refuses changes meanwhile.
const ul={iv:null,clicked:0,miss:0};
function ulShow(){$('updlock').style.display='grid';$('updlock').className='modal updlock busy';$('ulbtns').style.display='none';$('ullog').style.display='none';
  $('ulhead').textContent=t('Update läuft','Update running');if(!ul.iv){ul.iv=setInterval(ulPoll,2000);ulPoll()}}
function ulStop(){clearInterval(ul.iv);ul.iv=null}
function ulFail(head,text,log,cancel){ulStop();$('updlock').className='modal updlock fail';$('ulhead').textContent=head;$('ultext').textContent=text;
  $('ulnote').textContent=t('Schlägt ein Schritt vor dem Umschalten fehl, läuft die bisherige Version weiter; danach wird sie wieder eingespielt. Die Zeile oben sagt, was passiert ist.','If a step before the switch fails, the previous version keeps running; after it, the previous version is installed again. The line above says what happened.');
  if(log&&log.length){$('ullog').textContent=log.join('\n');$('ullog').style.display='block'}
  $('ulbtns').style.display='flex';$('ulcancel').style.display=cancel?'':'none'}
async function ulPoll(){let p;try{const r=await fetch('/api/update/progress');if(!r.ok)throw 0;p=await r.json();ul.miss=0}
  catch{ul.miss++;$('ultext').textContent=t('Verbinde neu … (das Panel startet neu)','Reconnecting … (the panel restarts)');return}
  const fresh=p.started&&p.started*1000>=ul.clicked-60000;
  if(p.done&&fresh){if(p.ok){ulStop();$('ulfill').style.width='100%';$('ultext').textContent=t('Fertig, lade neu …','Done, reloading …');
      try{sessionStorage.setItem('upddone',p.version||'1')}catch{}setTimeout(()=>location.reload(),1200)}
    else ulFail(t('Update fehlgeschlagen','Update failed'),p.text||'',p.log,false);return}
  if(!p.running){if(Date.now()-ul.clicked>15000){ulStop();   // nothing to do (already up to date) or ended without a report
      if(!fresh){$('updlock').style.display='none';loadSys&&loadSys()}else location.reload()}return}
  $('ulfill').style.width=(fresh?p.percent:3)+'%';$('ultext').textContent=fresh?p.text:t('Starte …','Starting …');
  if(p.started){const s=Math.max(0,p.now-p.started);$('ultime').textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
    if(s>p.timeout)ulFail(t('Update dauert zu lange','Update is taking too long'),t(`Nach ${Math.round(p.timeout/60)} Minuten nicht fertig. Neu laden zeigt den aktuellen Stand; du kannst das Update auch abbrechen.`,`Not finished after ${Math.round(p.timeout/60)} minutes. Reload shows the current state; you can also cancel the update.`),p.log,true)}}
$('ulreload').onclick=()=>location.reload();
$('ulclose').onclick=()=>{$('updlock').style.display='none';ulStop();if(ADMIN)loadSys()};
$('ulcancel').onclick=async()=>{try{await api('/api/update',{method:'DELETE'})}catch{}location.reload()};
async function ulWatch(){if(ul.iv)return;try{const p=await (await fetch('/api/update/progress?log=false')).json();if(p.running){ul.clicked=(p.started||0)*1000;ulShow()}}catch{}}
setInterval(()=>{if(ADMIN)ulWatch()},8000);   // an update started from another tab or device locks this one too
async function ulCheck(){await ulWatch();
  let v=null;try{v=sessionStorage.getItem('upddone');sessionStorage.removeItem('upddone')}catch{}
  if(v){const e=$('updtoast');e.textContent=t('Update fertig','Update finished')+(v!=='1'?': '+v:'')+'.';e.style.display='block';setTimeout(()=>e.style.display='none',6000)}}
$('updgo').onclick=async()=>{if(!confirm(t('Update jetzt installieren? Die Dienste starten dabei kurz neu.','Install the update now? The services restart briefly.')))return;
  try{ul.clicked=Date.now();await api('/api/update',{method:'POST'});ulShow()}
  catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
setInterval(()=>{if(ADMIN)api('/api/update').then(r=>r.json()).then(u=>updBadge(u.remote)).catch(()=>{})},600000);
// ---------------------------------------------------------------- previous version, live check, backups
$('updprev').onclick=async()=>{if(!confirm(t('Die vorige Version wieder installieren? Vorher wird automatisch gesichert. Gilt die vorige Version vor V01.0.37, müssen Kalender-Passwörter und Home-Assistant-Tokens danach neu eingegeben werden.','Install the previous version again? A backup is made first. If the previous version is older than V01.0.37, calendar passwords and Home Assistant tokens have to be entered again afterwards.')))return;
  try{ul.clicked=Date.now();await api('/api/update/rollback',{method:'POST'});ulShow()}catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
const LIVE={llm:t('Sprachmodell','Language model'),tts:t('Sprachausgabe','Speech output'),asr:t('Spracherkennung','Speech recognition')};
function liveRender(r){if(!r||!r.steps){$('livesteps').innerHTML=`<tr><td class="mut">${t('Noch nicht geprüft.','Not checked yet.')}</td></tr>`;$('livemsg').textContent='';return}
  $('livesteps').innerHTML=r.steps.map(s=>`<tr><td style="width:34%">${s.ok===true?'✅':s.ok===false?'❌':'➖'} ${esc(LIVE[s.name]||s.name)}</td><td><span class="mut">${s.seconds} s</span> ${esc(s.detail||'')}</td></tr>`).join('');
  $('livemsg').textContent=new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):'')}
async function loadLive(){try{liveRender(await (await api('/api/livecheck')).json())}catch{}loadQuality()}
// quality test of the language model (sandbox questions, see quality.py)
let qTimer=null;
function qRender(d){const r=d&&d.last;clearTimeout(qTimer);
  if(d&&d.running){$('qmsg').textContent=t('läuft … (ein bis drei Minuten)','running … (one to three minutes)');$('qgo').disabled=true;qTimer=setTimeout(loadQuality,5000)}
  else{$('qgo').disabled=false;$('qmsg').textContent=r?new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):''):''}
  if(!r){$('qsum').innerHTML=`<span class="mut">${t('Noch nicht geprüft.','Not tested yet.')}</span>`;$('qlist').innerHTML='';return}
  if(r.error){$('qsum').innerHTML=`<span class="err">${esc(r.error)}</span>`;$('qlist').innerHTML='';return}
  const bad=r.cases.filter(x=>!x.ok);
  $('qsum').innerHTML=`<span class="pill ${bad.length?'warn':'ok'}">${r.passed} / ${r.total}</span> <span class="mut">${esc(r.model||'')} · ${t('Temperatur','temperature')} ${r.temperature} · ${r.seconds} s</span>`;
  $('qlist').innerHTML=(bad.length?bad:r.cases).map(x=>`<tr><td style="width:36%">${x.ok?'✅':'❌'} ${esc(x.q)}<div class="mut">${esc(x.tools.join(', ')||t('kein Werkzeug','no tool'))}</div></td><td>${x.ok?'':`<b>${esc(x.why.join('; '))}</b><br>`}<span class="mut">${esc(x.answer||'–')}</span></td></tr>`).join('')}
async function loadQuality(){try{qRender(await (await api('/api/quality')).json())}catch{}}
$('qgo').onclick=async()=>{try{qRender(await (await api('/api/quality',{method:'POST'})).json())}catch(e){$('qmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('livego').onclick=async()=>{$('livego').disabled=true;$('livemsg').textContent=t('prüft … (bis zu einer Minute)','checking … (up to a minute)');
  try{liveRender(await (await api('/api/livecheck',{method:'POST'})).json())}catch(e){$('livemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('livego').disabled=false;refresh()};
const WHY={daily:t('täglich','daily'),manual:t('von Hand','manual'),'before-update':t('vor Update','before update'),'before-rollback':t('vor Rückkehr','before rollback'),'before-restore':t('vor Wiederherstellung','before restore')};
const mb=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
function bakRender(l){$('baklist').innerHTML=l.map(b=>`<tr><td>${new Date(b.created*1000).toLocaleString()}<div class="mut">${esc(WHY[b.why]||b.why)} · ${mb(b.size)}</div></td><td style="text-align:right;white-space:nowrap"><a class="b" href="/api/backups/${encodeURIComponent(b.name)}" download>${t('Laden','Download')}</a> <button class="b" onclick="bakRestore('${escq(b.name)}')">${t('Wiederherstellen','Restore')}</button> <button class="b" onclick="bakDel('${escq(b.name)}')">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine Sicherung.','No backup yet.')}</td></tr>`}
async function loadBak(){try{bakRender((await (await api('/api/backups')).json()).backups)}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}}
const bakAsk=()=>confirm(t('Wiederherstellen? Profile, Stimmen und Einstellungen werden durch die Sicherung ersetzt (der jetzige Stand wird vorher gesichert). Geänderte Einstellungen der Dienste wirken nach deren Neustart.','Restore? Profiles, voices and settings are replaced by the backup (the current state is backed up first). Changed service settings take effect after their restart.'));
const bakDone=r=>{$('bakmsg').textContent=t('Wiederhergestellt: ','Restored: ')+r.restored.join(', ');loadBak()};
window.bakRestore=async n=>{if(!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  try{bakDone(await (await api('/api/backups/'+encodeURIComponent(n)+'/restore',{method:'POST'})).json())}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.bakDel=async n=>{if(!confirm(t('Diese Sicherung löschen?','Delete this backup?')))return;bakRender((await (await api('/api/backups/'+encodeURIComponent(n),{method:'DELETE'})).json()).backups)};
$('bakgo').onclick=async()=>{$('bakmsg').textContent=t('sichere …','backing up …');try{const b=await (await api('/api/backups',{method:'POST'})).json();$('bakmsg').textContent=t('Gesichert: ','Saved: ')+mb(b.size);loadBak()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('bakup').onclick=()=>$('bakfile').click();
$('bakfile').onchange=async()=>{const f=$('bakfile').files[0];$('bakfile').value='';if(!f||!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  const fd=new FormData();fd.append('file',f,f.name);try{bakDone(await (await api('/api/backups-upload',{method:'POST',body:fd})).json())}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// alerts on top of every admin page: memory, watchdog, failed live check
function showAlerts(a){$('alerts').innerHTML=(a||[]).map(x=>`<div class="note ${x.level==='bad'?'bad':''}">${esc(x.text)}</div>`).join('')}
