// "Ich" → Lautsprecher (esp32.py): own ESP32-S3 speakers. Set up over USB from Chrome/Edge (Web Serial,
// esptool.js) or by the 6-digit code a board shows. The Wi-Fi password only goes into the board's
// settings block (NVS), which is put together here in the browser; the Spark never sees it.
let ESP_ON=false;
// ---------------------------------------------------------------- NVS image (ESP-IDF format version 2)
// Same bytes as Espressif's nvs_partition_gen for the same entries (checked when this was written).
const NVS_CRC=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
// zlib.crc32(data, 0xFFFFFFFF), as ESP-IDF computes it for NVS
function crc32le(b){let c=0;for(const x of b)c=NVS_CRC[(c^x)&255]^(c>>>8);return (~c)>>>0}
function nvsImage(size,spaces){
  const PAGE=4096,img=new Uint8Array(size).fill(0xFF),enc=new TextEncoder(),ents=[];let ns=0;
  const entry=(nsi,type,key,data,span=1)=>{const e=new Uint8Array(32).fill(0xFF);e[0]=nsi;e[1]=type;e[2]=span;
    const k=enc.encode(key);if(k.length>15)throw new Error('NVS key too long: '+key);e.fill(0,8,24);e.set(k,8);e.set(data,24);
    new DataView(e.buffer).setUint32(4,crc32le(new Uint8Array([...e.slice(0,4),...e.slice(8,32)])),true);return e};
  for(const [name,items] of Object.entries(spaces)){ns++;
    const d=new Uint8Array(8).fill(0xFF);d[0]=ns;ents.push([entry(0,0x01,name,d)]);
    for(const [key,val] of Object.entries(items)){
      if(typeof val==='number'){const d=new Uint8Array(8).fill(0xFF);new DataView(d.buffer).setInt32(0,val,true);ents.push([entry(ns,0x14,key,d)]);continue}
      const s=enc.encode(String(val)+'\0');if(s.length>4000)throw new Error('NVS value too long: '+key);
      const n=Math.ceil(s.length/32),body=new Uint8Array(n*32).fill(0xFF);body.set(s);
      const d=new Uint8Array(8).fill(0xFF),v=new DataView(d.buffer);v.setUint16(0,s.length,true);v.setUint32(4,crc32le(s),true);
      const list=[entry(ns,0x21,key,d,n+1)];for(let i=0;i<n;i++)list.push(body.slice(i*32,i*32+32));ents.push(list)}}
  let page=0,slot=0;const pages=[0];
  for(const list of ents){if(slot+list.length>126){page++;slot=0;if((page+2)*PAGE>size)throw new Error('NVS full');pages.push(page)}
    for(const e of list){img.set(e,page*PAGE+64+slot*32);img[page*PAGE+32+(slot>>2)]&=~(1<<((slot&3)*2))&0xFF;slot++}}
  for(const p of pages){const h=new Uint8Array(32).fill(0xFF),v=new DataView(h.buffer);
    v.setUint32(0,p<page?0xFFFFFFFC:0xFFFFFFFE,true);v.setUint32(4,p,true);h[8]=0xFE;v.setUint32(28,crc32le(h.slice(4,28)),true);img.set(h,p*PAGE)}
  return img}
// the NVS partition of the firmware's own partition table (type data, subtype nvs)
function nvsPartition(table){const v=new DataView(table.buffer,table.byteOffset,table.byteLength);
  for(let o=0;o+32<=table.length;o+=32){if(v.getUint16(o,true)!==0x50AA)break;if(table[o+2]===1&&table[o+3]===2)return {offset:v.getUint32(o+4,true),size:v.getUint32(o+8,true)}}
  throw new Error(t('Keine NVS-Partition in der Firmware.','No NVS partition in the firmware.'))}
async function sha256hex(u8){const h=new Uint8Array(await crypto.subtle.digest('SHA-256',u8));return [...h].map(x=>x.toString(16).padStart(2,'0')).join('')}
// ---------------------------------------------------------------- USB
function espLog(x,err){const m=$('espflog');if(!m)return;m.textContent=x;m.className='fh'+(err?' err':'')}
function espBar(p){const b=$('espbar');if(b){b.style.display=p==null?'none':'block';b.firstElementChild.style.width=Math.round((p||0)*100)+'%'}}
async function espConnect(){
  if(!('serial' in navigator))throw new Error(t('Dieser Browser kann nicht per USB flashen. Bitte Chrome oder Edge am PC oder Mac nehmen.','This browser cannot flash over USB. Please use Chrome or Edge on a PC or Mac.'));
  if(!window.isSecureContext)throw new Error(t('Nur über https (oder localhost) erlaubt der Browser USB.','The browser only allows USB over https (or localhost).'));
  const port=await navigator.serial.requestPort({});
  const {ESPLoader,Transport}=await import('/static/js/esptool.js?v='+encodeURIComponent(SPARK_VER));
  const transport=new Transport(port,true);
  const term={clean(){},writeLine(){},write(){}};
  const loader=new ESPLoader({transport,baudrate:460800,romBaudrate:115200,terminal:term});
  espLog(t('Verbinde mit dem Board … (klappt es nicht: BOOT gedrückt halten, kurz RESET drücken, BOOT loslassen)','Connecting to the board … (if it fails: hold BOOT, press RESET briefly, release BOOT)'));
  const chip=await loader.main();
  const mac=await loader.chip.readMac(loader).catch(()=>'');
  const flashKB=await loader.getFlashSize().catch(()=>0);
  return {port,transport,loader,chip,mac,flashMB:flashKB?flashKB/1024:0}}
async function espParts(parts){const out=[];let i=0;
  for(const p of parts){espLog(t('Lade Firmware vom Spark … ','Loading firmware from the Spark … ')+(++i)+'/'+parts.length);
    const r=await fetch(p.url);if(!r.ok)throw new Error(p.file+': '+r.status);const u8=new Uint8Array(await r.arrayBuffer());
    if(await sha256hex(u8)!==p.sha256)throw new Error(p.file+t(': Prüfsumme passt nicht.',': checksum does not match.'));out.push({address:p.address,u8,file:p.file})}
  return out}
async function espWrite(c,files){espBar(0);
  await c.loader.writeFlash({fileArray:files.map(f=>({address:f.address,data:c.loader.ui8ToBstr(f.u8)})),flashSize:'keep',flashMode:'keep',flashFreq:'keep',
    eraseAll:false,compress:true,reportProgress:(i,w,tot)=>{espBar((i+w/tot)/files.length);espLog(t('Schreibe ','Writing ')+(i+1)+'/'+files.length+' … '+Math.round(w/tot*100)+' %')}});
  await c.loader.after('hard_reset');await c.transport.disconnect().catch(()=>{});espBar(null)}
function espChip(c,need){if(!/ESP32-S3/i.test(c.chip))throw new Error(t('Das ist ein ','This is an ')+c.chip+t(', gebraucht wird ein ESP32-S3.',', an ESP32-S3 is needed.'));
  const mb=parseInt(need)||16;if(c.flashMB&&c.flashMB<mb)throw new Error(t('Das Board hat ','The board has ')+c.flashMB+t(' MB Flash, die Firmware braucht ',' MB flash, the firmware needs ')+mb+' MB.')}
// a self-signed certificate (port 31443) is refused by the board
function espBaseHint(b){if(/^https:\/\/[^/]*:31443$/.test(b)||/^https:\/\/\d+\.\d+\.\d+\.\d+/.test(b))
  return t('Achtung: Diese Adresse hat ein selbst signiertes Zertifikat, das nimmt das Board nicht an. Nimm die Adresse deines Reverse Proxys oder http://<Spark-IP>:31080 im Heimnetz.','Careful: this address has a self-signed certificate, the board refuses it. Use your reverse proxy address or http://<Spark IP>:31080 at home.');
  if(/^http:\/\//.test(b))return t('Ohne https: Der Geräteschlüssel geht im Heimnetz unverschlüsselt. Unterwegs geht es so nicht.','Without https: the device key travels unencrypted in your home network. It does not work away from home.');
  return ''}
// ---------------------------------------------------------------- the page
async function showEsp(){const box=$('espbox');if(!box)return;if(!PROFILE||!ESP_ON){box.innerHTML='';return}
  let d={on:false,devices:[],firmware:null,base:location.origin};try{d=await (await api('/api/profile/esp32')).json()}catch{}
  const fw=d.firmware,vars=fw?Object.entries(fw.variants):[];
  const when=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'–';
  const hm=ms=>new Date(ms).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  // room mode per speaker (room.py): the switch, how long, how much it may say, its room in Home Assistant
  const room=x=>`<div class="row" style="gap:6px;flex-wrap:wrap;margin-top:4px">
      <label class="chk" title="${t('Raum-Modus: hört eine Weile dem Gespräch zu und hilft in einer Pause','Room mode: listens to the conversation for a while and helps in a pause')}"><input type="checkbox" data-eroom="${x.id}"${x.room?' checked':''}> ${t('Raum','Room')}</label>
      <select data-ermins="${x.id}" aria-label="${t('Dauer','Duration')}">${[15,30,60,120,240].map(n=>`<option value="${n}"${n===x.room_mins?' selected':''}>${n} ${t('Min.','min')}</option>`).join('')}</select>
      <select data-erlevel="${x.id}" aria-label="${t('Wie viel er sagen darf','How much it may say')}"><option value="questions"${x.room_level==='questions'?' selected':''}>${t('nur Fragen','questions only')}</option><option value="hints"${x.room_level==='hints'?' selected':''}>${t('auch Hinweise','also hints')}</option><option value="all"${x.room_level==='all'?' selected':''}>${t('auch Kommentare','also comments')}</option></select>
      ${RV_ON?`<select data-ervoices="${x.id}" aria-label="${t('Wem er zuhört','Who it listens to')}"><option value="all"${x.room_voices==='all'?' selected':''}>${t('hört allen zu','listens to everybody')}</option><option value="tv"${x.room_voices==='tv'?' selected':''}>${t('bekannte Stimmen, wenn TV läuft','known voices while the TV is on')}</option><option value="known"${x.room_voices==='known'?' selected':''}>${t('nur bekannte Stimmen','only known voices')}</option></select>
      <label class="chk" title="${t('Probelauf: überhört noch nichts, zählt nur (Ergebnis im Protokoll und unter Prüfen)','Trial: ignores nothing yet, only counts (result in the log and under Check)')}"><input type="checkbox" data-erprobe="${x.id}"${x.room_probe!==false?' checked':''}> ${t('Probelauf','Trial')}</label>`:''}
      <label class="chk" title="${t('Genauer erkennen: Das Sprachmodell sucht höchstens alle zwei Minuten nach Fragen, Terminen und Einkäufen, die die festen Regeln übersehen. Kostet Rechenzeit.','Detect more: the language model looks at most every two minutes for questions, appointments and shopping the fixed rules missed. Costs GPU time.')}"><input type="checkbox" data-erdetect="${x.id}"${x.room_detect?' checked':''}> ${t('genauer','detect more')}</label>
      <input data-erarea="${x.id}" value="${esc(x.room_area||'')}" placeholder="${t('Raum in Home Assistant','Room in Home Assistant')}" style="max-width:180px" autocomplete="off">
      <small class="mut">${x.room_until?t('hört zu bis ','listening until ')+hm(x.room_until):x.room_waits?t('startet beim nächsten Weckwort','starts at the next wake word'):''}</small></div>`;
  // the profile's voice through this speaker's own microphone (speakers.py: its own voiceprint)
  const voice=x=>`<div class="row" style="gap:6px;flex-wrap:wrap;margin-top:4px;align-items:center">
      <button class="b" type="button" data-evoice="${x.id}">${t('Stimme hier anlernen','Teach my voice here')}</button>
      <small class="mut">${x.voice_waits?t('vorgemerkt: sag „Jarvis“ oder drück den Knopf, dann drei Sätze','queued: say "Jarvis" or press the button, then three sentences'):x.voice_here?t('angelernt (','taught (')+x.voice_here+t(' Aufnahmen)',' recordings)'):t('noch nicht angelernt: „nur bekannte Stimmen“ hört hier allen zu','not taught yet: "only known voices" listens to everybody here')}</small></div>`;
  const dev=x=>`<li><span><b>${esc(x.name)}</b> ${x.online?`<span style="color:var(--ok)">● ${t('verbunden','connected')}</span>`:''}<br><small class="mut">${t('zuletzt','last')} ${when(x.seen)} · Firmware ${esc(x.fw||'?')}${x.newer?' · '+t('Update da','update available'):''}${x.update?' · '+t('beim nächsten Start','at next start'):''}</small>
      <div class="row" style="gap:6px;flex-wrap:wrap;margin-top:4px">
        <label class="mut" style="font-size:13px">${t('Lautstärke','Volume')} <input type="range" min="0" max="100" step="5" value="${x.volume??70}" data-evol="${x.id}" style="vertical-align:middle;width:120px"> <span data-evolv="${x.id}">${x.volume??t('wie am Board','as on the board')}</span></label>
        <select data-emic="${x.id}" aria-label="${t('Mikrofon','Microphone')}"><option value="low"${x.mic==='low'?' selected':''}>${t('Mikrofon: weniger empfindlich','Microphone: less sensitive')}</option><option value="normal"${x.mic==='normal'?' selected':''}>${t('Mikrofon: normal','Microphone: normal')}</option><option value="high"${x.mic==='high'?' selected':''}>${t('Mikrofon: empfindlicher','Microphone: more sensitive')}</option></select></div>${d.room?room(x):''}${d.speaker_id?voice(x):''}</span>
      <span class="row" style="gap:6px;flex-wrap:wrap;justify-content:flex-end">${x.newer&&!x.update?`<button class="b" type="button" data-eup="${x.id}">${t('Aktualisieren','Update')}</button>`:''}
      <label class="chk" title="${t('Updates beim Start von selbst','Updates at start by themselves')}"><input type="checkbox" data-eauto="${x.id}"${x.auto?' checked':''}> ${t('auto','auto')}</label>
      <button class="b" type="button" data-ediag="${x.id}">${t('Prüfen','Check')}</button><button class="b" type="button" data-eren="${x.id}">${t('Umbenennen','Rename')}</button><button class="b" type="button" data-edel="${x.id}">${t('Entfernen','Remove')}</button></span></li>`;
  box.innerHTML=`<div class="intro">${t('Eigene kleine Lautsprecher mit Mikrofon (ESP32-S3-Boards) für jeden Raum. Sie hören auf das Weckwort oder den Knopf, fragen den Spark und antworten in deiner Stimme, mit deinem Gedächtnis und deinem Smart Home (mit Codewort). Kein Cloud-Dienst.','Own small speakers with a microphone (ESP32-S3 boards) for every room. They listen for the wake word or the button, ask the Spark and answer in your voice, with your memory and your smart home (with code word). No cloud service.')}</div>
    ${d.room&&d.on?`<div class="fh">${t('„Raum“: Der Lautsprecher hört für die gewählte Zeit dem Gespräch im Raum zu und hilft in einer Pause, mit einem leisen Ton vorher; geändert wird nur nach „Ja“. Per Sprache: „Jarvis … Raummodus an“ und „Raummodus aus“. Schläft er gerade, startet der Schalter beim nächsten Weckwort. In deinen Ruhezeiten schweigt er. Das Gehörte bleibt nur wenige Minuten auf dem Spark.','"Room": the speaker listens to the conversation in the room for the chosen time and helps in a pause, with a soft tone first; it changes something only after a "yes". By voice: "Jarvis … Raummodus an" and "Raummodus aus". When it sleeps, the switch starts at its next wake word. In your quiet hours it stays silent. What it hears stays on the Spark for a few minutes only.')}</div>`:''}
    ${xsw('esp_on',t('Eigene Lautsprecher für mich','Own speakers for me'),t('Ohne diesen Schalter nimmt der Spark keine Verbindung deiner Lautsprecher an.','Without this switch the Spark accepts no connection from your speakers.'))}
    ${d.on?`<ul class="facts">${d.devices.map(dev).join('')||`<li class="mut">${t('Noch kein Lautsprecher eingerichtet.','No speaker set up yet.')}</li>`}</ul>
    <div id="espdiag"></div>
    ${!fw?`<div class="fh err">${t('Auf dem Spark liegt noch keine Firmware. Der Admin holt sie unter Einstellungen → Funktionen → Eigene Lautsprecher.','There is no firmware on the Spark yet. The admin fetches it under Settings → Features → Own speakers.')}</div>`:''}
    <details style="margin-top:10px"${d.devices.length?'':' open'}><summary>${t('Neuen Lautsprecher per USB einrichten (Chrome oder Edge)','Set up a new speaker over USB (Chrome or Edge)')}</summary>
      <div class="fh">${t('Board mit einem Datenkabel (nicht nur Ladekabel) an diesen PC stecken. Alles darauf wird überschrieben.','Plug the board into this PC with a data cable (not a charge-only cable). Everything on it is overwritten.')}</div>
      <label>${t('Name','Name')}</label><input id="espname" placeholder="${t('z. B. Küche','e.g. Kitchen')}" autocomplete="off">
      <label>${t('Board','Board')}</label><select id="espvar">${vars.map(([k,v])=>`<option value="${esc(k)}">${esc(v.label)}</option>`).join('')}</select>
      <div class="two2"><div><label>${t('WLAN-Name','Wi-Fi name')}</label><input id="espssid" autocomplete="off" autocapitalize="off"></div><div><label>${t('WLAN-Passwort','Wi-Fi password')}</label><input id="esppw" type="password" autocomplete="new-password"></div></div>
      <div class="fh">${t('Nur 2,4-GHz-WLAN. Das Passwort geht nur aufs Board, nicht an den Spark.','2.4 GHz Wi-Fi only. The password only goes onto the board, not to the Spark.')}</div>
      <label>${t('Adresse des Spark für das Gerät','Spark address for the device')}</label><input id="espbase" value="${esc(d.base)}"${d.fixed_base?' readonly':''} autocapitalize="off" autocomplete="off">
      <div class="fh" id="espbasehint"></div>
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="espflash"${fw?'':' disabled'}>${t('Board verbinden und einrichten','Connect board and set up')}</button></div>
    </details>
    <details style="margin-top:8px"><summary>${t('Lautsprecher mit Code koppeln','Pair a speaker with a code')}</summary>
      <div class="fh">${t('Für ein Board, das schon die Spark-Firmware hat: Beim Start zeigt oder sagt es einen 6-stelligen Code.','For a board that already has the Spark firmware: at start it shows or says a 6-digit code.')}</div>
      <div class="two2"><div><label>${t('Code','Code')}</label><input id="espcode" inputmode="numeric" maxlength="7" autocomplete="off"></div><div><label>${t('Name','Name')}</label><input id="espcname" autocomplete="off"></div></div>
      <div class="row" style="margin-top:8px"><button class="b" type="button" id="esppair">${t('Koppeln','Pair')}</button></div></details>
    <details style="margin-top:8px"><summary>${t('Board per USB reparieren oder aktualisieren','Repair or update a board over USB')}</summary>
      <div class="fh">${t('Schreibt nur die Firmware neu, WLAN und Kopplung bleiben. Für ein Board, das nicht mehr startet oder kein Update über WLAN bekommt.','Rewrites only the firmware, Wi-Fi and pairing stay. For a board that no longer starts or gets no update over Wi-Fi.')}</div>
      <label>${t('Board','Board')}</label><select id="espvar2">${vars.map(([k,v])=>`<option value="${esc(k)}">${esc(v.label)}</option>`).join('')}</select>
      <div class="row" style="margin-top:8px"><button class="b" type="button" id="esprepair"${fw?'':' disabled'}>${t('Board verbinden und Firmware schreiben','Connect board and write firmware')}</button></div></details>
    <details style="margin-top:8px" id="espserbox"><summary>${t('Protokoll vom Board lesen (USB)','Read the board\'s log (USB)')}</summary>
      <div class="fh">${t('Board per USB an diesen PC stecken. Es startet neu und die Seite liest 45 Sekunden lang mit, was es meldet: WLAN, Spark-Adresse, Zertifikat, Abstürze. Der Text bleibt in diesem Browser.','Plug the board into this PC over USB. It restarts and the page reads for 45 seconds what it reports: Wi-Fi, Spark address, certificate, crashes. The text stays in this browser.')}</div>
      <div class="row" style="margin-top:8px"><button class="b" type="button" id="espser">${t('Board verbinden und mitlesen','Connect board and read')}</button><button class="b" type="button" id="espserstop" style="display:none">${t('Aufhören','Stop')}</button><button class="b" type="button" id="espsercopy" style="display:none">${t('Kopieren','Copy')}</button></div>
      <ul class="facts small" id="espserres"></ul><pre id="espserlog" style="display:none;max-height:40vh"></pre></details>
    <div id="espbar" class="ulbar" style="display:none;margin-top:10px"><i style="width:0"></i></div><div class="fh" id="espflog"></div>`:''}`;
  xbind(box,showEsp);if(!d.on)return;
  const hint=()=>{$('espbasehint').textContent=espBaseHint($('espbase').value.trim().replace(/\/$/,''))};$('espbase').oninput=hint;hint();
  box.querySelectorAll('[data-edel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Lautsprecher entfernen? Sein Schlüssel gilt dann nicht mehr.','Remove the speaker? Its key stops working.')))return;await api('/api/profile/esp32/'+b.dataset.edel,{method:'DELETE'});showEsp()});
  box.querySelectorAll('[data-eren]').forEach(b=>b.onclick=async()=>{const n=prompt(t('Neuer Name','New name'));if(!n)return;try{await api('/api/profile/esp32/'+b.dataset.eren,xjson('PUT',{name:n}));showEsp()}catch(e){espLog(e.message,true)}});
  box.querySelectorAll('[data-eauto]').forEach(b=>b.onchange=async()=>{try{await api('/api/profile/esp32/'+b.dataset.eauto,xjson('PUT',{auto:b.checked}))}catch(e){espLog(e.message,true)}});
  const eput=(id,o)=>api('/api/profile/esp32/'+id,xjson('PUT',o)).then(()=>showEsp()).catch(e=>espLog(e.message,true));
  box.querySelectorAll('[data-evol]').forEach(b=>{b.oninput=()=>{const v=box.querySelector(`[data-evolv="${b.dataset.evol}"]`);if(v)v.textContent=b.value};
    b.onchange=()=>api('/api/profile/esp32/'+b.dataset.evol,xjson('PUT',{volume:Number(b.value)})).catch(e=>espLog(e.message,true))});
  box.querySelectorAll('[data-emic]').forEach(b=>b.onchange=()=>api('/api/profile/esp32/'+b.dataset.emic,xjson('PUT',{mic:b.value})).catch(e=>espLog(e.message,true)));
  box.querySelectorAll('[data-eroom]').forEach(b=>b.onchange=()=>eput(b.dataset.eroom,{room:b.checked}));
  box.querySelectorAll('[data-ermins]').forEach(b=>b.onchange=()=>eput(b.dataset.ermins,{room_mins:Number(b.value)}));
  box.querySelectorAll('[data-erlevel]').forEach(b=>b.onchange=()=>eput(b.dataset.erlevel,{room_level:b.value}));
  box.querySelectorAll('[data-ervoices]').forEach(b=>b.onchange=()=>eput(b.dataset.ervoices,{room_voices:b.value}));
  box.querySelectorAll('[data-erprobe]').forEach(b=>b.onchange=()=>eput(b.dataset.erprobe,{room_probe:b.checked}));
  box.querySelectorAll('[data-evoice]').forEach(b=>b.onclick=async()=>{try{const r=await (await api('/api/profile/esp32/'+b.dataset.evoice+'/voice',xjson('POST'))).json();
    espLog(r.now?t('Der Lautsprecher bittet jetzt um drei Sätze.','The speaker now asks for three sentences.'):t('Vorgemerkt: sag „Jarvis“ oder drück den Knopf, dann sprich drei Sätze.','Queued: say "Jarvis" or press the button, then speak three sentences.'));showEsp()}catch(e){espLog(e.message,true)}});
  box.querySelectorAll('[data-erdetect]').forEach(b=>b.onchange=()=>eput(b.dataset.erdetect,{room_detect:b.checked}));
  box.querySelectorAll('[data-erarea]').forEach(b=>b.onchange=()=>eput(b.dataset.erarea,{room_area:b.value.trim().slice(0,60)}));
  box.querySelectorAll('[data-eup]').forEach(b=>b.onclick=async()=>{try{const r=await (await api('/api/profile/esp32/'+b.dataset.eup+'/update',xjson('POST'))).json();await showEsp();
    espLog(r.restarted?t('Der Lautsprecher startet neu und holt das Update.','The speaker restarts and fetches the update.'):t('Das Update kommt beim nächsten Start (Stecker kurz ziehen genügt).','The update comes at the next start (unplugging briefly is enough).'))}catch(e){espLog(e.message,true)}});
  $('esppair').onclick=async()=>{try{await api('/api/profile/esp32/pair',xjson('POST',{code:$('espcode').value,name:$('espcname').value}));await showEsp();espLog(t('Gekoppelt. Der Lautsprecher verbindet sich gleich.','Paired. The speaker connects in a moment.'))}catch(e){espLog(e.message,true)}};
  $('espflash').onclick=()=>espSetup(fw).catch(e=>{espBar(null);espLog(t('Nicht eingerichtet: ','Not set up: ')+e.message,true)});
  box.querySelectorAll('[data-ediag]').forEach(b=>b.onclick=()=>espDiag(b.dataset.ediag));
  $('espser').onclick=()=>espSerial().catch(e=>espSerShow(null,[[false,e.message]]));
  $('esprepair').onclick=()=>espRepair(fw).catch(e=>{espBar(null);espLog(t('Nicht geschrieben: ','Not written: ')+e.message,true)})}
async function espSetup(fw){
  const name=$('espname').value.trim(),variant=$('espvar').value,ssid=$('espssid').value,pw=$('esppw').value,base=$('espbase').value.trim().replace(/\/$/,'');
  if(!name)throw new Error(t('Bitte einen Namen eingeben.','Please enter a name.'));
  if(!ssid)throw new Error(t('Bitte den WLAN-Namen eingeben.','Please enter the Wi-Fi name.'));
  const v=fw.variants[variant];
  const c=await espConnect();espChip(c,v.flash);
  espLog(c.chip+(c.mac?' · '+c.mac:'')+(c.flashMB?' · '+c.flashMB+' MB':''));
  const files=await espParts(v.parts.map(p=>Object.assign({},p,{url:`/api/esp32/fw/${fw.version}/${p.file}`})));
  const table=files.find(f=>f.address===0x8000);if(!table)throw new Error(t('Partitionstabelle fehlt.','Partition table missing.'));
  const nvs=nvsPartition(table.u8);
  const r=await (await api('/api/profile/esp32/setup',xjson('POST',{name,variant,base}))).json();
  const img=nvsImage(nvs.size,{wifi:{ssid,password:pw,ota_url:r.ota_url},websocket:{url:r.ws_url,token:r.token,version:1},board:{uuid:r.uuid}});
  try{await espWrite(c,files.concat([{address:nvs.offset,u8:img,file:'nvs'}]))}
  catch(e){await api('/api/profile/esp32/'+r.device,{method:'DELETE'}).catch(()=>{});throw e}
  $('esppw').value='';
  espLog(t('Fertig. Das Board startet neu, verbindet sich mit dem WLAN und meldet sich beim Spark. Sag dann „Jarvis“ oder drück den Knopf.','Done. The board restarts, joins the Wi-Fi and checks in with the Spark. Then say "Jarvis" or press the button.'));
  setTimeout(showEsp,15000)}
async function espRepair(fw){const v=fw.variants[$('espvar2').value];
  const c=await espConnect();espChip(c,v.flash);
  const files=await espParts(v.parts.map(p=>Object.assign({},p,{url:`/api/esp32/fw/${fw.version}/${p.file}`})));
  await espWrite(c,files);espLog(t('Firmware geschrieben. Das Board startet neu.','Firmware written. The board restarts.'))}
// ---------------------------------------------------------------- diagnosis ("Prüfen")
const espWhen=s=>new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const espMark=ok=>ok===true?'<b style="color:var(--ok)">✓</b>':ok===false?'<b style="color:var(--bad)">✗</b>':'<b class="mut">·</b>';
function espDiagShow(id,d,results){const box=$('espdiag');if(!box)return;
  const li=x=>`<li>${espMark(x.ok)}<span>${esc(x.text)}</span></li>`;
  box.innerHTML=`<div style="margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-radius:12px">
    <div class="row" style="justify-content:space-between"><b>${t('Prüfen','Check')}${d.online?' · <span style="color:var(--ok)">● '+t('verbunden','connected')+'</span>':''}</b><button class="b" type="button" id="espdclose">${t('Schließen','Close')}</button></div>
    <ul class="facts small">${d.checks.map(li).join('')}${(results||[]).map(li).join('')}</ul>
    <div class="fh">${t('Adresse im Board','Address in the board')}: <b>${esc(d.base)}</b>${d.base_known?'':' '+t('(nicht gespeichert, eingerichtet vor dieser Version; geprüft wird die Adresse dieser Seite)','(not stored, set up before this version; the address of this page is checked)')}</div>
    <div class="row" style="margin-top:8px"><button class="b" type="button" id="espdnet">${t('Netz prüfen','Check network')}</button>
      <button class="b" type="button" id="espdtest">${t('Test: Ton und Mikrofon','Test: sound and microphone')}</button>
      <button class="b" type="button" id="espdser">${t('Protokoll vom Board lesen (USB)','Read the board\'s log (USB)')}</button>
      <button class="b" type="button" id="espdre">${t('Aktualisieren','Refresh')}</button></div>
    <div class="fh">${d.test?t('Test ist vorgemerkt: Sag „Jarvis“ oder drück den Knopf. Er spielt einen Ton und einen Satz, dann sagst du etwas und er sagt, was er verstanden hat.','Test is queued: say "Jarvis" or press the button. It plays a tone and a sentence, then you say something and it tells you what it understood.'):t('„Netz prüfen“ fragt die Adresse vom Spark aus ab, wie es das Board tut. „Test“ spielt beim nächsten Weckwort Ton und Satz und prüft danach das Mikrofon.','"Check network" asks the address from the Spark, as the board does. "Test" plays a tone and a sentence at the next wake word and then checks the microphone.')}</div>
    <div style="margin-top:8px"><b>${t('Was der Lautsprecher zuletzt gemacht hat','What the speaker did lately')}</b> <small class="mut">${t('(live)','(live)')}</small></div>
    <ul class="facts small">${d.events.map(e=>`<li><small class="mut" style="white-space:nowrap">${espWhen(e.t)}</small><span>${esc(e.text)}</span></li>`).join('')||`<li class="mut">${t('Seit dem letzten Neustart des Spark nichts. Das Board hat sich nicht gemeldet.','Nothing since the Spark last restarted. The board has not checked in.')}</li>`}</ul></div>`;
  $('espdclose').onclick=()=>{box.innerHTML='';clearInterval(ESP_LIVE)};
  $('espdre').onclick=()=>espDiag(id);
  $('espdnet').onclick=async()=>{$('espdnet').disabled=true;$('espdnet').textContent=t('Prüfe …','Checking …');
    try{const r=await (await api('/api/profile/esp32/'+id+'/check',xjson('POST'))).json();espDiagShow(id,r,r.results)}catch(e){espDiagShow(id,d,[{ok:false,text:e.message}])}};
  $('espdtest').onclick=async()=>{try{const r=await (await api('/api/profile/esp32/'+id+'/test',xjson('POST'))).json();espDiagShow(id,r,[{ok:null,text:r.now?t('Der Lautsprecher spielt jetzt den Test.','The speaker plays the test now.'):t('Vorgemerkt: beim nächsten „Jarvis“ oder Knopfdruck.','Queued: at the next "Jarvis" or button press.')}])}catch(e){espDiagShow(id,d,[{ok:false,text:e.message}])}};
  $('espdser').onclick=()=>{const b=$('espserbox');if(b){b.open=true;b.scrollIntoView({block:'nearest'})}espSerial().catch(e=>espSerShow(null,[[false,e.message]]))}}
async function espDiag(id){try{espDiagShow(id,await (await api('/api/profile/esp32/'+id+'/diag')).json());espLive(id)}catch(e){espLog(e.message,true)}}
// "live": while the check is open and the page visible, the list follows what the speaker does (every 2 s)
let ESP_LIVE=null;
function espLive(id){clearInterval(ESP_LIVE);ESP_LIVE=setInterval(async()=>{const box=$('espdiag');
  if(!box||!box.firstElementChild){clearInterval(ESP_LIVE);return}
  if(document.hidden||box.contains(document.activeElement)&&document.activeElement.tagName!=='BUTTON')return;
  try{const d=await (await api('/api/profile/esp32/'+id+'/diag')).json();const ul=box.querySelectorAll('ul.facts')[1];
    if(ul)ul.innerHTML=d.events.map(e=>`<li><small class="mut" style="white-space:nowrap">${espWhen(e.t)}</small><span>${esc(e.text)}</span></li>`).join('')||`<li class="mut">–</li>`}catch{}},2000)}
// ---------------------------------------------------------------- the board's own log over USB
// What XiaoZhi prints at start (see its main/application.cc, ota.cc, esp-wifi-connect), in plain words.
const ESP_SIGNS=[
  [/Brownout detector was triggered/i,false,()=>t('Die Spannung bricht ein. Anderes Netzteil oder kürzeres Kabel nehmen.','The voltage drops. Use another power supply or a shorter cable.')],
  [/Guru Meditation Error|abort\(\) was called|assert failed|Backtrace:/,false,()=>t('Das Board stürzt ab. Meist passt die Board-Variante oder die Pinbelegung nicht. Schick mir den Text.','The board crashes. Usually the board variant or the pins do not match. Send me the text.')],
  [/NVS namespace wifi doesn't exist/,false,()=>t('Auf dem Board stehen keine WLAN-Daten. Per USB neu einrichten.','There is no Wi-Fi data on the board. Set it up again over USB.')],
  [/Connecting to WiFi (\S+)/,null,m=>t('Verbinde mit dem WLAN „','Connecting to the Wi-Fi "')+m[1]+t('“','"')],
  [/Got IP:\s*([\d.]+)/,true,m=>t('Im WLAN, Adresse ','On the Wi-Fi, address ')+m[1]],
  [/WiFi connection timeout|WiFi config mode entered|Access Point started with SSID/,false,()=>t('Das WLAN klappt nicht: Name oder Passwort falsch, oder nur 5 GHz. Das Board macht jetzt ein eigenes WLAN auf. Per USB mit richtigen Daten neu einrichten.','The Wi-Fi does not work: wrong name or password, or 5 GHz only. The board now opens its own Wi-Fi. Set it up again over USB with the right data.')],
  [/Current version: ([\d.]+)/,null,m=>'Firmware '+m[1]],
  [/Check version URL is not properly set/,false,()=>t('Im Board steht keine Spark-Adresse.','There is no Spark address in the board.')],
  [/Failed to open HTTP connection: (.*)/,false,m=>(/cert|x509|ssl|tls/i.test(m[1])?t('Das Board lehnt das Zertifikat des Spark ab. Adresse des Reverse Proxys oder http://<Spark-IP>:31080 nehmen. ','The board refuses the Spark\'s certificate. Use the reverse proxy address or http://<Spark IP>:31080. '):/dns|resolve|host/i.test(m[1])?t('Das Board findet den Namen der Spark-Adresse nicht. ','The board cannot resolve the Spark address. '):t('Das Board erreicht den Spark nicht. ','The board cannot reach the Spark. '))+'('+m[1].slice(0,120)+')'],
  [/Failed to check version, status code: (\d+)/,false,m=>t('Der Spark antwortet mit ','The Spark answers with ')+m[1]+(m[1]==='403'?t(': Lautsprecher sind in Funktionen ausgeschaltet.',': speakers are switched off in Features.'):'')],
  [/Check new version failed/,false,()=>t('Die Start-Prüfung beim Spark ist fehlgeschlagen, das Board versucht es weiter.','The start check at the Spark failed, the board keeps trying.')],
  [/Alert \[link\]/,null,()=>t('Das Board zeigt einen Kopplungscode: Es kennt den Spark noch nicht. Code unter „Lautsprecher mit Code koppeln“ eingeben.','The board shows a pairing code: it does not know the Spark yet. Enter it under "Pair a speaker with a code".')],
  [/No websocket section found/,false,()=>t('Der Spark hat keine Gesprächsadresse geschickt.','The Spark sent no conversation address.')],
  [/Connecting to websocket server: (\S+)/,null,m=>t('Verbinde zum Gespräch: ','Connecting for the conversation: ')+m[1]],
  [/Failed to connect to websocket server/,false,()=>t('Die Gesprächsverbindung klappt nicht: Reverse Proxy ohne WebSockets oder Schlüssel abgelehnt. „Prüfen“ beim Lautsprecher zeigt den Grund.','The conversation connection fails: reverse proxy without WebSockets or key refused. "Check" at the speaker shows why.')],
  [/Session ID:/,true,()=>t('Gespräch mit dem Spark steht.','Conversation with the Spark is up.')],
  [/Wake word detected/,true,()=>t('Weckwort erkannt.','Wake word detected.')],
  [/Failed to create audio (?:de|en)coder|Read Failed!/,false,()=>t('Ton-Fehler auf dem Board (Mikrofon oder Verstärker). Board-Variante und Pins prüfen.','Sound error on the board (microphone or amplifier). Check board variant and pins.')],
  [/rst:0x[0-9a-f]+ \((\w+)\)/i,null,m=>t('Board startet (','Board starts (')+m[1]+')']];
function espAnalyse(text){const out=[],seen=new Set();
  for(const line of text.split('\n'))for(const [re,ok,msg] of ESP_SIGNS){const m=line.match(re);if(!m)continue;const s=msg(m);if(seen.has(s))continue;seen.add(s);out.push([ok,s])}
  if(text.length>200&&!/Current version|Connecting to WiFi|ESP-ROM|rst:0x/i.test(text))out.push([false,t('Das Board schreibt etwas, aber nichts Bekanntes. Schick mir den Text.','The board writes something, but nothing known. Send me the text.')]);
  return out}
// never show what looks like a key or a password, even if a firmware should print one
const espMask=s=>s.replace(/((?:token|password|passwd|authorization|bearer)[^:=\s]*\s*[:=]?\s*)\S+/gi,'$1•••');
function espSerShow(text,res){const r=$('espserres'),l=$('espserlog');if(!r)return;
  r.innerHTML=(res||[]).map(([ok,s])=>`<li>${espMark(ok)}<span>${esc(s)}</span></li>`).join('');
  if(text!=null){l.style.display='block';l.textContent=text.split('\n').slice(-300).join('\n');l.scrollTop=l.scrollHeight;$('espsercopy').style.display=''}}
let ESP_SER=null;
async function espSerial(){
  if(!('serial' in navigator))throw new Error(t('Dieser Browser kann nicht per USB lesen. Bitte Chrome oder Edge am PC oder Mac nehmen.','This browser cannot read over USB. Please use Chrome or Edge on a PC or Mac.'));
  if(!window.isSecureContext)throw new Error(t('Nur über https (oder localhost) erlaubt der Browser USB.','The browser only allows USB over https (or localhost).'));
  if(ESP_SER)return;
  let port=await navigator.serial.requestPort({});const info=port.getInfo();
  const st=ESP_SER={stop:false,text:''};const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  $('espser').disabled=true;$('espserstop').style.display='';$('espserstop').onclick=()=>{st.stop=true;st.reader&&st.reader.cancel().catch(()=>{})};
  $('espsercopy').onclick=()=>navigator.clipboard.writeText(espMask(st.text)).catch(()=>{});
  espSerShow('',[[null,t('Verbunden, starte das Board neu …','Connected, restarting the board …')]]);
  const end=Date.now()+45000,dec=new TextDecoder();let reset=false;
  try{while(!st.stop&&Date.now()<end){
      try{await port.open({baudRate:115200})}catch(e){if(!/already open/i.test(e.message))throw e}
      if(!reset){reset=true;   // restart into the firmware: boot pin high (DTR off), reset pulse on RTS
        await port.setSignals({dataTerminalReady:false,requestToSend:true}).catch(()=>{});await sleep(150);await port.setSignals({requestToSend:false}).catch(()=>{})}
      st.reader=port.readable.getReader();
      const timer=setInterval(()=>{if(Date.now()>end)st.reader.cancel().catch(()=>{})},500);
      try{while(true){const {value,done}=await st.reader.read();if(done)break;
          st.text=(st.text+dec.decode(value,{stream:true})).slice(-200000);espSerShow(espMask(st.text),espAnalyse(st.text))}}
      catch(e){}   // a board with its own USB vanishes for a moment when it restarts
      finally{clearInterval(timer);try{st.reader.releaseLock()}catch{}await port.close().catch(()=>{})}
      if(st.stop||Date.now()>end)break;
      await sleep(1200);   // find the same board again after it came back
      const again=(await navigator.serial.getPorts()).find(p=>{const i=p.getInfo();return i.usbVendorId===info.usbVendorId&&i.usbProductId===info.usbProductId});
      if(again)port=again}}
  finally{ESP_SER=null;$('espser').disabled=false;$('espserstop').style.display='none'}
  const res=espAnalyse(st.text);
  if(!st.text.trim())res.push([false,t('Vom Board kam nichts. Anderes Kabel (Datenkabel) oder die andere USB-Buchse des Boards versuchen.','Nothing came from the board. Try another (data) cable or the board\'s other USB socket.')]);
  espSerShow(espMask(st.text),res)}
// ---------------------------------------------------------------- admin (Funktionen)
async function espAdmin(){if(!$('espadmin'))return;let d={};try{d=await (await api('/api/admin/esp32')).json()}catch{return}
  const fw=d.firmware;
  $('espstate').textContent=(fw?t('Firmware ','Firmware ')+fw.version+' ('+Object.keys(fw.variants).length+t(' Boards)',' boards)'):t('Noch keine Firmware auf dem Spark.','No firmware on the Spark yet.'))
    +' · '+d.speakers+t(' Lautsprecher, ',' speakers, ')+d.online+t(' verbunden',' connected')+(d.error?' · ⚠ '+d.error:'');
  $('espfetch').onclick=async()=>{$('espstate').textContent=t('Hole die Firmware von GitHub …','Fetching the firmware from GitHub …');
    try{await api('/api/admin/esp32/fetch',xjson('POST'));espAdmin()}catch(e){$('espstate').textContent=e.message}}}
