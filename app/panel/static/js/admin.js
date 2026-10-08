// Admin pages: monitoring, settings, tests, voices, logs, guides, system and the update lock.
const btns=(n,st)=>`<button class="b" onclick="act('${escq(n)}','restart',this)">${t('Neustart','Restart')}</button>`+(st==='active'||st==='activating'?`<button class="b" onclick="act('${escq(n)}','stop',this)">${t('Stopp','Stop')}</button>`:`<button class="b" onclick="act('${escq(n)}','start',this)">Start</button>`);
async function act(n,a,btn){btn.disabled=true;try{await api(`/api/service/${n}/${a}`,{method:'POST'})}catch(e){alert(e.message)}btn.disabled=false;refresh()}
window.act=act;

async function refresh(){
  let s;try{s=await (await api('/api/status')).json()}catch(e){$('hdr').textContent=t('Panel nicht erreichbar','Panel not reachable');return}
  const g=s.gpu||{},sy=s.system,H=s.history;
  $('hdr').textContent=(g.name||t('keine GPU','no GPU'))+' · '+new Date(s.time*1000).toLocaleTimeString();
  $('m-gpu').textContent=fmt(g.util,' %');$('m-mem').textContent=fmt(sy.mem_avail_gib,' GiB',1)+' / '+sy.mem_total_gib;
  $('m-temp').textContent=fmt(g.temp,' °C')+' · '+fmt(g.power,' W');$('m-cpu').textContent=fmt(sy.cpu,' %');
  spark($('c-gpu'),H.map(x=>x.gpu),100);spark($('c-mem'),H.map(x=>x.avail),sy.mem_total_gib);spark($('c-temp'),H.map(x=>x.temp),100);spark($('c-cpu'),H.map(x=>x.cpu),100);
  showAlerts(s.alerts);zustand(s);
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

// Zustand (design „Klar“, V01.0.146): one sentence on top (all fine / what is wrong) and "Braucht dich" with
// what waits for the admin, each with a button to the place; the dot next to "Zustand" in the menus follows it.
// Built only from what the page already fetched (services, alerts, memory, update, unsaved settings pages).
const SVCNAME={asr:t('Spracherkennung','Speech recognition'),tts:t('Sprachausgabe','Speech output'),wyoming:'Wyoming'};
let ZLAST=null;
function zustand(s){if(s)ZLAST=s;s=ZLAST;if(!s)return;
  const need=[],bad=[],sy=s.system||{};
  for(const [n,v] of Object.entries(s.services||{})){const h=v.health||{},name=SVCNAME[n]||n.toUpperCase();
    if(['failed','error'].includes(v.state)||h.error)bad.push(name);
    else if(v.enabled&&['inactive','deactivating'].includes(v.state))need.push({lvl:'bad',text:t(`${name} ist aus.`,`${name} is off.`),go:'svc',btn:t('Ansehen','View')})}
  for(const n of bad)need.push({lvl:'bad',text:t(`${n} meldet einen Fehler.`,`${n} reports an error.`),go:'svc',btn:t('Ansehen','View')});
  const u=window.UPD;if(u&&u.behind&&u.behind!==0)need.push({lvl:'warn',text:t('Update bereit','Update ready')+(u.version?': '+u.version:'')+'.',go:'sys',btn:t('Zum Update','To the update')});
  const dirty=[...document.querySelectorAll('.pane.dirty')].map(p=>{const b=document.querySelector(`#cfgnav button[data-p="${p.id.slice(5)}"]`);return b?b.textContent.trim():p.id});
  if(dirty.length)need.push({lvl:'warn',text:t(`Nicht gespeichert: ${dirty.join(', ')}.`,`Not saved: ${dirty.join(', ')}.`),go:'cfg',btn:t('Öffnen','Open')});
  // running = systemd says active or the service itself answers; neither = no answer (counts as "needs you")
  const ok=([,v])=>v.state==='active'||['ready','ok'].includes((v.health||{}).status),nm=([n])=>SVCNAME[n]||n.toUpperCase();
  const all=Object.entries(s.services||{}).filter(e=>!bad.includes(nm(e))),run=all.filter(ok).map(nm),unk=all.filter(e=>!ok(e)&&e[1].enabled!==false).map(nm);
  const low=sy.mem_avail_gib!=null&&sy.mem_avail_gib<12;
  const al=s.alerts||[],lvl=bad.length||need.some(x=>x.lvl==='bad')||al.some(x=>x.level==='bad')?'bad':need.length||unk.length||low||al.length?'warn':'ok';
  $('ztitle').textContent=lvl==='ok'?t('Alles läuft.','Everything is running.'):lvl==='bad'?t('Etwas läuft nicht.','Something is not running.'):!run.length&&unk.length?t('Die Dienste melden sich nicht.','The services do not answer.'):t('Läuft, aber etwas braucht dich.','Running, but something needs you.');
  $('ztext').textContent=(bad.length?t('Fehler: ','Errors: ')+bad.join(', ')+'. ':'')+(run.length?run.join(t(' und ',' and '))+(run.length>1?t(' laufen. ',' are running. '):t(' läuft. ',' is running. ')):'')+(unk.length?t('Ohne Rückmeldung: ','No answer from: ')+unk.join(', ')+'. ':'')
    +(sy.mem_avail_gib!=null?t(`${fmt(sy.mem_avail_gib,' GiB',1)} Speicher frei`,`${fmt(sy.mem_avail_gib,' GiB',1)} memory free`)+(low?t(' (wenig)',' (low)'):'')+'.':'')+(al.length?' '+t('Hinweise stehen oben.','Notes are shown above.'):'');
  $('zhead').dataset.lvl=lvl;$('zicon').textContent=lvl==='ok'?'✓':'!';
  document.querySelectorAll('.hdot').forEach(d=>d.className='hdot '+lvl);
  $('zneed').hidden=!need.length;const L=$('zlist');L.textContent='';
  for(const x of need){const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill '+x.lvl;sp.textContent=x.lvl==='bad'?t('Fehler','Error'):t('Offen','Open');
    const tx=document.createElement('span');tx.textContent=x.text;const b=document.createElement('button');b.type='button';b.className='b';b.textContent=x.btn;
    b.onclick=()=>{if(x.go==='svc')$('svc').closest('.card').scrollIntoView({behavior:'smooth'});else if(x.go==='cfg'){goSec('cfg');const d=document.querySelector('.pane.dirty');if(d){const nb=document.querySelector(`#cfgnav button[data-p="${d.id.slice(5)}"]`);if(nb)nb.click()}}else goSec(x.go)};
    r.append(sp,tx,b);L.appendChild(r)}}
window.zustand=zustand;

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
  asrRec();cfgDeps();if(typeof guidesCount==='function')guidesCount();if(typeof tgAdmin==='function')tgAdmin();if(typeof espAdmin==='function')espAdmin();document.querySelectorAll('.pane').forEach(p=>markDirty(p,false));document.querySelectorAll('.savemsg').forEach(m=>m.textContent='')}
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
document.querySelectorAll('#cfgnav button').forEach(b=>b.onclick=()=>{cfgPane(b.dataset.p);if(b.dataset.p==='voices')loadClone();document.querySelector('.cfgwrap').classList.add('sub');window.scrollTo(0,0)});
$('cfgback').onclick=()=>{document.querySelector('.cfgwrap').classList.remove('sub');window.scrollTo(0,0)};
try{const p=localStorage.getItem('cfgpane');if(p&&$('pane-'+p))cfgPane(p)}catch{}
// Details of a feature show only while it is on (they sit right below its switch).
function cfgDeps(){const on=id=>{const e=$(id);return !e||e.checked};
  document.querySelectorAll('#pane-cfg [data-show],[data-show]').forEach(x=>x.style.display=on(x.dataset.show)?'':'none');
}
['chat.search','chat.speaker_id','chat.mail'].forEach(id=>$(id).addEventListener('change',cfgDeps));
// every switch with details shows them at once when switched on (not only after saving)
[...new Set([...document.querySelectorAll('[data-show]')].map(x=>x.dataset.show))].forEach(id=>{const e=$(id);if(e&&!['chat.search','chat.speaker_id','chat.mail'].includes(id))e.addEventListener('change',cfgDeps)});
// Wyoming answers only listed addresses: suggest the Home Assistant address when switched on
async function wySuggest(auto){const inp=$('chat.wyoming_allow'),msg=$('wymsg');
  try{const d=await (await api('/api/admin/wyoming/suggest')).json();
    const have=inp.value.split(/[\s,;]+/).filter(Boolean),add=d.ha.map(x=>x.ip).filter(ip=>!have.includes(ip));
    if(add.length){inp.value=have.concat(add).join(', ');inp.dispatchEvent(new Event('input',{bubbles:true}));
      msg.textContent=t('Eingetragen: ','Filled in: ')+d.ha.map(x=>x.ip+' ('+x.host+')').join(', ')+t('. Prüfen, dann Speichern.','. Check it, then save.')}
    else if(!auto)msg.textContent=d.ha.length?t('Die Adresse steht schon drin.','The address is already there.'):t('Keine Home-Assistant-Adresse im Heimnetz gefunden (in keinem Profil eingerichtet, oder nur über einen Reverse-Proxy erreichbar). Trag die Adresse deines Home Assistant von Hand ein, z. B. 192.168.1.20.','No Home Assistant address in the home network found (not set up in any profile, or only reachable through a reverse proxy). Enter your Home Assistant address by hand, e.g. 192.168.1.20.');
    if(d.knocked.length)msg.textContent+=' '+t('Zuletzt abgewiesen: ','Refused lately: ')+d.knocked.join(', ')+t(' (wenn das dein Home Assistant ist, diese Adresse eintragen).',' (if that is your Home Assistant, enter this address).')}
  catch(e){if(!auto)msg.textContent=e.message}}
$('wysuggest').onclick=()=>wySuggest(false);
$('chat.wyoming').addEventListener('change',e=>{if(e.target.checked&&!$('chat.wyoming_allow').value.trim())wySuggest(true)});
const markDirty=(pane,on)=>{const b=document.querySelector(`#cfgnav button[data-p="${pane.id.slice(5)}"]`);if(b)b.classList.toggle('dirty',on);
  pane.classList.toggle('dirty',on);const bar=pane.querySelector('.savebar');if(bar)bar.classList.toggle('dirty',on);
  const n=document.querySelectorAll('.pane.dirty').length,c=$('dirtycnt');c.hidden=!n;c.textContent=n;zustand()};
// unsaved changes: the save bar says so and offers "Verwerfen"; leaving the page or the settings asks first
const dirtyPanes=()=>[...document.querySelectorAll('.pane.dirty')];
const leaveOk=()=>!dirtyPanes().length||confirm(t('Es gibt ungespeicherte Änderungen. Trotzdem verlassen? Sie gehen dann verloren.','There are unsaved changes. Leave anyway? They will be lost.'));
window.addEventListener('beforeunload',e=>{if(dirtyPanes().length){e.preventDefault();e.returnValue=''}});
document.querySelectorAll('.savebar').forEach(bar=>{if(!bar.querySelector('.savebtn'))return;
  const n=document.createElement('span');n.className='unsaved';n.textContent=t('Ungespeicherte Änderungen','Unsaved changes');
  const d=document.createElement('button');d.type='button';d.className='b undo';d.textContent=t('Verwerfen','Discard');
  d.onclick=()=>{if(confirm(t('Änderungen auf dieser Seite verwerfen?','Discard the changes on this page?')))loadCfg()};
  bar.prepend(n);bar.querySelector('.savebtn').after(d)});
// leaving the settings with unsaved changes: ask (capture phase, before the menu switches the page)
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('nav button[data-s],.subnav button');
  if(b&&b.dataset.s!=='cfg'&&document.getElementById('cfg').classList.contains('on')&&!leaveOk()){e.stopImmediatePropagation();e.preventDefault()}},true);
document.querySelectorAll('.pane').forEach(pane=>{if(!pane.querySelector('.savebtn'))return;const f=e=>{if(/^pw/.test(e.target.id))return;markDirty(pane,true)};pane.addEventListener('input',f);pane.addEventListener('change',f)});
document.querySelectorAll('.savebtn').forEach(btn=>btn.onclick=async()=>{const pane=$('pane-'+btn.dataset.p),msg=btn.nextElementSibling;
  const n=JSON.parse(JSON.stringify(CFG));if(getDefaults&&pane.contains($('chatdefaults')))n.chat.defaults=getDefaults();
  for(const[sec,o]of Object.entries(n))for(const k of Object.keys(o)){const el=$(sec+'.'+k);if(!el||!pane.contains(el))continue;
    o[k]=el.type==='checkbox'?el.checked:el.dataset.list?el.value.split(/[\s,;]+/).filter(Boolean):el.type==='number'||el.dataset.num?Number(el.value):el.value}
  if(pane.contains($('chat.wyoming'))&&$('chat.wyoming').checked&&!$('chat.wyoming_allow').value.trim()){
    const m=t('Wyoming braucht die Adresse deines Home Assistant, z. B. 192.168.1.20 (oder „Adresse von Home Assistant übernehmen“).','Wyoming needs your Home Assistant address, e.g. 192.168.1.20 (or "Take the Home Assistant address").');
    $('wymsg').innerHTML=`<span class="err">${esc(m)}</span>`;msg.innerHTML=`<span class="err">${esc(m)}</span>`;$('chat.wyoming_allow').focus();return}
  msg.textContent=t('Speichere…','Saving…');
  try{const r=await (await api('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(n)})).json();
    msg.innerHTML=t('Gespeichert.','Saved.')+(r.restarted.length?t(' Neu gestartet: ',' Restarted: ')+r.restarted.join(', ').toUpperCase()+t(' (Modell lädt neu).',' (model reloads).'):'')+(r.stopped&&r.stopped.length?t(' Gestoppt: ',' Stopped: ')+r.stopped.join(', ').toUpperCase()+'.':'')+(r.errors&&r.errors.length?`<div class="err">${esc(r.errors.join('\n'))}</div>`:'')+(r.panel_restart_needed?t(' Panel-Port ändert sich nach: ',' Panel port changes after: ')+'sudo systemctl restart speech-spark-panel':'');CFG=n;markDirty(pane,false)}
  catch(e){msg.innerHTML=`<span class="err">${esc(e.message)}</span>`}});

// the whole prompt as the model gets it (fixed parts marked) and the shipped system prompt
$('promptdef').onclick=async()=>{try{const d=await (await api('/api/admin/prompt')).json();const el=$('chat.system_prompt');
    el.value=d.default;el.dispatchEvent(new Event('input',{bubbles:true}));$('promptmsg').textContent=t('Standard eingesetzt, noch nicht gespeichert.','Default filled in, not saved yet.')}
  catch(e){$('promptmsg').textContent=e.message}};
$('promptshow').onclick=async()=>{const v=$('promptview');if(v.style.display!=='none'){v.style.display='none';return}
  try{const d=await (await api('/api/admin/prompt')).json();
    v.innerHTML=`<div class="fh">${esc(t('So bekommt das Modell den Prompt, in dieser Reihenfolge (gespeicherter Stand). Feste Teile kann keine Einstellung und kein Prompt abschalten.','This is how the model gets the prompt, in this order (saved state). No setting and no prompt can switch off the fixed parts.'))}</div>`
      +d.parts.map(p=>`<div style="margin-top:8px"><b>${esc(p.label)}</b> <span class="pill ${p.fixed?'ok':'warn'}">${p.fixed?esc(t('fest','fixed')):esc(t('änderbar','changeable'))}</span><pre style="white-space:pre-wrap;margin:4px 0 0">${esc(p.text||'–')}</pre></div>`).join('');
    v.style.display=''}
  catch(e){$('promptmsg').textContent=e.message}};
$('asrgo').onclick=async()=>{const f=$('asrfile').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);fd.append('language',$('asrlang').value);
  $('asrmsg').textContent=t('läuft…','running…');$('asrout').style.display='none';
  try{const r=await (await api('/api/test/asr',{method:'POST',body:fd})).json();$('asrmsg').textContent=`${r.processing_s}s ${t('für','for')} ${fmt(r.duration,' s',1)} Audio`;
    $('asrout').textContent=`[${r.language||'auto'}] ${r.text}`;$('asrout').style.display='block'}catch(e){$('asrmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
async function loadVoices(){const v=await (await api('/api/tts/voices')).json(),vs=v.voices||[];   // no list while the TTS loads
  $('ttsvoice').innerHTML=vs.length?vs.map(x=>`<option>${esc(x)}</option>`).join(''):`<option value="">${t('(Standard)','(default)')}</option>`;
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
  $('vlist').innerHTML=l.map(n=>`<tr><td>${esc(n)}</td><td style="text-align:right;white-space:nowrap"><button class="b" type="button" data-vprobe="${esc(n)}">${t('Probe sprechen','Speak a sample')}</button> <button class="b" type="button" data-vref="${esc(n)}">${t('Referenz anhören','Play reference')}</button> <button class="b" type="button" data-vexp="${esc(n)}">${t('Exportieren','Export')}</button> <button class="b" type="button" data-vdel="${esc(n)}">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine.','None yet.')}</td></tr>`}
// names travel in data attributes, never inside inline JavaScript
$('vlist').onclick=e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;
  if(d.vprobe!=null)probeVoice(d.vprobe,b);else if(d.vref!=null)playRef(d.vref);
  else if(d.vexp!=null)location.href='/api/clone-voices-export?names='+encodeURIComponent(d.vexp);else if(d.vdel!=null)delVoice(d.vdel)};
$('vexpall').onclick=()=>{location.href='/api/clone-voices-export'};
$('vimpbtn').onclick=()=>$('vimpfile').click();
$('vimpfile').onchange=async()=>{const f=$('vimpfile').files[0];if(!f)return;$('vimpfile').value='';
  const fd=new FormData();fd.append('file',f);fd.append('conflict',$('vimpconflict').value);$('vimpmsg').textContent=t('Importiere …','Importing …');
  try{const r=await (await api('/api/clone-voices-import',{method:'POST',body:fd})).json();
    const ok=r.voices.filter(v=>v.result==='imported'),sk=r.voices.filter(v=>v.result==='skipped');
    $('vimpmsg').textContent=t('Importiert: ','Imported: ')+(ok.map(v=>v.as===v.name?v.name:`${v.name} → ${v.as}`).join(', ')||'–')+
      (sk.length?' · '+t('übersprungen: ','skipped: ')+sk.map(v=>v.name).join(', '):'');loadClone()}
  catch(e){$('vimpmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
function playRef(n){const a=new Audio('/api/clone-voices/'+encodeURIComponent(n)+'.wav');a.play()}
async function delVoice(n){if(!confirm(t(`Stimme ${n} löschen?`,`Delete voice ${n}?`)))return;await api('/api/clone-voices/'+encodeURIComponent(n),{method:'DELETE'});loadClone()}
// One short sentence with exactly this voice, through the same admin test route as Zustand → Prüfen.
// Cloned voices only sound like themselves with a Base model; otherwise the engine's answer says why.
const PROBE={de:'Hallo, so klinge ich als Stimme des Spark.',en:'Hello, this is how I sound as the voice of the Spark.'};
async function probeVoice(n,btn){const lang=$('vreadlang').value==='en'?'en':'de',msg=$('vprobemsg');btn.disabled=true;msg.textContent=t('Spreche …','Speaking …');
  try{const r=await api('/api/test/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:PROBE[lang],voice:n,language:lang==='en'?'English':'German',instruct:null})});
    const a=new Audio(URL.createObjectURL(await r.blob()));a.play();msg.textContent=''}
  catch(e){msg.textContent=t('Probe ging nicht: ','Sample failed: ')+e.message+((CFG&&CFG.tts&&!/Base/.test(CFG.tts.model||''))?t(' (geklonte Stimmen brauchen ein Base-Modell unter Sprachausgabe)',' (cloned voices need a Base model under Speech output)'):'')}
  btn.disabled=false}
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
function diagUrl(){const f=[...document.querySelectorAll('[data-lf]')].filter(x=>x.checked).map(x=>x.dataset.lf).join(',');
  return '/api/logfilter?f='+encodeURIComponent(f)+'&minutes='+$('logmin').value+'&lines='+$('loglines').value}
let diagAt=0;
async function loadLogs(){const v=$('logsvc').value,el=$('logout');$('logdiag').style.display=v==='diag'?'':'none';if(v==='diag')diagAt=Date.now();
  const txt=(v==='audit'?await auditText():await (await api(v==='diag'?diagUrl():'/api/logs/'+v+'?lines=300')).text())||t('(leer)','(empty)');
  if(el.textContent!==txt)el.textContent=txt;if($('logfollow').checked)el.scrollTop=1e9}
try{$('logfollow').checked=localStorage.getItem('logfollow')!=='0'}catch{}
$('logfollow').onchange=()=>{try{localStorage.setItem('logfollow',$('logfollow').checked?'1':'0')}catch{}if($('logfollow').checked)loadLogs()};
setInterval(()=>{if($('logfollow').checked&&$('logs').classList.contains('on')&&!document.hidden&&($('logsvc').value!=='diag'||Date.now()-diagAt>10000))loadLogs().catch(()=>{})},3000);
try{const d=JSON.parse(localStorage.getItem('logdiag')||'null');if(d){document.querySelectorAll('[data-lf]').forEach(x=>x.checked=d.f.includes(x.dataset.lf));$('logmin').value=d.m;$('loglines').value=d.l}}catch{}
document.querySelectorAll('#logdiag input,#logdiag select').forEach(x=>x.onchange=()=>{
  try{localStorage.setItem('logdiag',JSON.stringify({f:[...document.querySelectorAll('[data-lf]')].filter(x=>x.checked).map(x=>x.dataset.lf),m:$('logmin').value,l:$('loglines').value}))}catch{}loadLogs()});
$('tts.model').addEventListener('change',()=>instrHint(true));$('logload').onclick=loadLogs;$('logsvc').onchange=loadLogs;


function kv(rows){return rows.map(([k,v])=>`<tr><td class="mut" style="width:40%">${k}</td><td><code>${esc(v)}</code> <button class="b" style="padding:1px 6px;font-size:12px" onclick="copyString(this.previousElementSibling.textContent,this)">${t('kopieren','copy')}</button></td></tr>`).join('')}
async function loadInt(){const c=await (await api('/api/config')).json();const v=await (await api('/api/tts/voices')).json();
  const host=location.hostname,asr=`http://${host}:${c.asr.port}/v1`,tts=`http://${host}:${c.tts.port}/v1`,key=c.api.key||t('beliebig, z. B. sk-local','anything, e.g. sk-local');
  const voice=c.tts.default_voice||((v.voices||[])[0]||'ryan');
  $('int-ep').innerHTML=kv([[t('Spracherkennung (STT)','Speech recognition (STT)'),asr+'/audio/transcriptions'],[t('Sprachausgabe (TTS)','Speech output (TTS)'),tts+'/audio/speech'],[t('API-Schlüssel','API key'),c.api.key||t('(keiner gesetzt)','(none set)')]]);
  $('int-owui-stt').innerHTML=kv([['Speech-to-Text Engine','OpenAI'],['API Base URL',asr],['API Key',key],['STT Model',c.asr.model]]);
  $('int-owui-tts').innerHTML=kv([['Text-to-Speech Engine','OpenAI'],['API Base URL',tts],['API Key',key],['TTS Model',c.tts.model],['TTS Voice',voice],[t('Zusätzliche TTS-Parameter (JSON, optional)','Additional TTS parameters (JSON, optional)'),JSON.stringify({temperature:c.tts.temperature,top_p:c.tts.top_p,seed:c.tts.seed})],[t('Antwort aufteilen','Response splitting'),t('Absätze (Paragraphs)','Paragraphs')]]);
  const panelUrl=`http://${host}:${(c.panel&&c.panel.port)||31080}`;
  $('int-pebble').innerHTML=kv([[t('Spark-Adresse in der Uhr-App','Spark address in the watch app'),panelUrl],[t('App-Datei','App file'),panelUrl+'/pebble/speech-spark.pbw']]);
  $('int-pbw').href=panelUrl+'/pebble/speech-spark.pbw';
  const siriBase=location.protocol==='https:'?location.origin:panelUrl;
  $('int-siri').innerHTML=kv([['URL',siriBase+'/api/siri/ask'],[t('Methode','Method'),'POST'],['Header','X-Speech-Device: sd_…'],[t('Haupttext (JSON)','Request body (JSON)'),'{"text": "…"}'],[t('Antwort','Answer'),'{"answer": "…"}']]);
  $('int-voices').textContent=v.model_kind==='voice_design'?t('VoiceDesign-Modell: die Stimme wird über die Standard-Anweisung beschrieben.','VoiceDesign model: the voice is described by the default instruction.'):((v.voices||[]).join(', ')||t('(Dienst lädt noch)','(service still loading)'));
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
$('adminout').onclick=async()=>{if(!confirm(t('Admin in allen Browsern abmelden, auch hier?','Log the admin out in every browser, this one too?')))return;
  try{await api('/api/logout-everywhere',{method:'POST'});location.reload()}catch(e){alert(e.message)}};
$('genkey').onclick=()=>{const a=new Uint8Array(18);crypto.getRandomValues(a);$('api.key').value='sk-'+[...a].map(x=>x.toString(16).padStart(2,'0')).join('')};

let updPoll=null;
async function loadSys(check=false){let u;try{u=await (await api('/api/update'+(check?'?check=true':''))).json()}catch(e){$('updstate').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  const i=u.installed||{},r=u.remote||{};
  $('sysver').innerHTML=kvp([[t('Installiert','Installed'),i.short?`${i.short} · ${new Date(i.date).toLocaleString()}`:'–'],[t('Änderung','Change'),i.subject||'–'],['Engines',i.engine||'–'],[t('Quelle','Source'),i.remote||'–'],[t('Zuletzt geprüft','Last checked'),r.checked?new Date(r.checked*1000).toLocaleTimeString():'–']]);
  updBadge(r);loadBak();
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
function updBadge(r){window.UPD=r;updBanner(r);zustand();const on=r&&r.behind&&r.behind!==0;$('updbadge').style.display=on?'inline-block':'none';
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
  if(d&&d.running){$('qmsg').textContent=t('läuft … (zwei bis vier Minuten)','running … (two to four minutes)');$('qgo').disabled=true;qTimer=setTimeout(loadQuality,5000)}
  else{$('qgo').disabled=false;$('qmsg').textContent=r?new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):''):''}
  if(!r){$('qsum').innerHTML=`<span class="mut">${t('Noch nicht geprüft.','Not tested yet.')}</span>`;$('qlist').innerHTML='';return}
  if(r.error){$('qsum').innerHTML=`<span class="err">${esc(r.error)}</span>`;$('qlist').innerHTML='';return}
  const bad=r.cases.filter(x=>!x.ok),flaky=r.cases.filter(x=>x.ok&&x.flaky),held=r.cases.filter(x=>x.ok&&!x.flaky&&x.held&&x.held.length);
  $('qsum').innerHTML=`<span class="pill ${bad.length?'warn':'ok'}">${r.passed} / ${r.total}</span> <span class="mut">${esc(r.model||'')} · ${t('Temperatur','temperature')} ${r.temperature}${r.tool_temperature!=null?' / '+r.tool_temperature+t(' bei der Werkzeugwahl',' choosing tools'):''} · ${r.seconds} s</span>`
    +(flaky.length?` <span class="pill warn">${flaky.length} ${t('erst im zweiten Versuch','only on the second try')}</span>`:'');
  const mark=x=>(x.new?` <span class="pill warn">${t('neu kaputt','newly broken')}</span>`:'')
    +(x.wobbly?` <span class="mut">${t('wackelt','wobbles')} (${x.wobbly} ${t('von','of')} ${x.runs})</span>`:'');
  const extra=x=>(x.flaky&&x.first?`<div class="mut">${t('Erster Versuch','First try')}: ${esc(x.first.why.join('; '))}</div>`:'')
    +(x.held&&x.held.length?`<div class="mut">${t('Antwort-Prüfung hat zurückgehalten','Answer check held back')}: ${esc(x.held.join(', '))}${x.raw?' · „'+esc(x.raw)+'“':''}</div>`:'')
    +(x.retried?`<div class="mut">${t('Ohne Werkzeug geantwortet, neu gefragt','Answered without a tool, asked again')}</div>`:'');
  const rows=bad.length||flaky.length||held.length?[...bad,...flaky,...held]:r.cases;
  $('qlist').innerHTML=rows.map(x=>`<tr><td style="width:36%">${x.ok?'✅':'❌'} ${esc(x.q)}${mark(x)}<div class="mut">${esc(x.tools.join(', ')||t('kein Werkzeug','no tool'))}</div></td><td>${x.ok?'':`<b>${esc(x.why.join('; '))}</b><br>`}<span class="mut">${esc(x.answer||'–')}</span>${extra(x)}</td></tr>`).join('')}
function qOwn(l){if(!l)return;$('qownbox').style.display=l.length?'':'none';
  $('qown').innerHTML=l.map(x=>`<li><span>${esc(x.q)}</span><button class="b" type="button" data-qdrop="${esc(x.id)}">${t('Löschen','Delete')}</button></li>`).join('')}
$('qown').addEventListener('click',async e=>{const b=e.target.closest('[data-qdrop]');if(!b)return;
  try{qOwn((await (await api('/api/quality/cases/'+encodeURIComponent(b.dataset.qdrop),{method:'DELETE'})).json()).own)}catch(err){$('qmsg').innerHTML=`<span class="err">${esc(err.message)}</span>`}});
async function loadQuality(){try{const d=await (await api('/api/quality')).json();qRender(d);qOwn(d.own)}catch{}}
$('qgo').onclick=async()=>{try{qRender(await (await api('/api/quality',{method:'POST'})).json())}catch(e){$('qmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('livego').onclick=async()=>{$('livego').disabled=true;$('livemsg').textContent=t('prüft … (bis zu einer Minute)','checking … (up to a minute)');
  try{liveRender(await (await api('/api/livecheck',{method:'POST'})).json())}catch(e){$('livemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('livego').disabled=false;refresh()};
const WHY={daily:t('täglich','daily'),manual:t('von Hand','manual'),'before-update':t('vor Update','before update'),'before-rollback':t('vor Rückkehr','before rollback'),'before-restore':t('vor Wiederherstellung','before restore')};
const mb=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
function bakRender(l){$('baklist').innerHTML=l.map(b=>`<tr><td>${new Date(b.created*1000).toLocaleString()}<div class="mut">${esc(WHY[b.why]||b.why)} · ${mb(b.size)}</div></td><td style="text-align:right;white-space:nowrap"><button class="b" onclick="bakLoad('${escq(b.name)}')">${t('Laden','Download')}</button> <button class="b" onclick="bakRestore('${escq(b.name)}')">${t('Wiederherstellen','Restore')}</button> <button class="b" onclick="bakDel('${escq(b.name)}')">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine Sicherung.','No backup yet.')}</td></tr>`}
async function loadBak(){try{bakRender((await (await api('/api/backups')).json()).backups)}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}}
const bakAsk=()=>confirm(t('Wiederherstellen? Profile, Stimmen und Einstellungen werden durch die Sicherung ersetzt (der jetzige Stand wird vorher gesichert). Geänderte Einstellungen der Dienste wirken nach deren Neustart.','Restore? Profiles, voices and settings are replaced by the backup (the current state is backed up first). Changed service settings take effect after their restart.'));
const bakDone=r=>{$('bakmsg').textContent=t('Wiederhergestellt: ','Restored: ')+r.restored.join(', ');loadBak()};
window.bakRestore=async n=>{if(!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  try{bakDone(await (await api('/api/backups/'+encodeURIComponent(n)+'/restore',{method:'POST'})).json())}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.bakLoad=async n=>{try{const r=await (await api('/api/backups/'+encodeURIComponent(n)+'/ticket',{method:'POST'})).json();
  const a=document.createElement('a');a.href=r.url;a.download=n;document.body.appendChild(a);a.click();a.remove()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.bakDel=async n=>{if(!confirm(t('Diese Sicherung löschen?','Delete this backup?')))return;bakRender((await (await api('/api/backups/'+encodeURIComponent(n),{method:'DELETE'})).json()).backups)};
$('bakgo').onclick=async()=>{$('bakmsg').textContent=t('sichere …','backing up …');try{const b=await (await api('/api/backups',{method:'POST'})).json();$('bakmsg').textContent=t('Gesichert: ','Saved: ')+mb(b.size);loadBak()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('bakup').onclick=()=>$('bakfile').click();
$('bakfile').onchange=async()=>{const f=$('bakfile').files[0];$('bakfile').value='';if(!f||!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  const fd=new FormData();fd.append('file',f,f.name);try{bakDone(await (await api('/api/backups-upload',{method:'POST',body:fd})).json())}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// alerts on top of every admin page: memory, watchdog, failed live check
function showAlerts(a){$('alerts').innerHTML=(a||[]).map(x=>`<div class="note ${x.level==='bad'?'bad':''}">${esc(x.text)}</div>`).join('')}
