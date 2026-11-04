// Zustand → System-Updates (systemupdates.py, admin): the card under Bereiche and its page with one column per
// computer (Pi = Panel, tars = Modelle): 1 Betriebssystem (apt: count, security, name old → new), 2 OpenCode and the
// pinned Python packages (OSV), 3 firmware and drivers (only shown, by hand with the guide), 4 Zeitpunkt (the night
// switch). Only package names, versions, counts and fixed words, all through esc(); every button goes to a fixed
// endpoint, the run itself is fixed on the server. Einspielen and Neustart ask for a fresh code (stufen.py, 428).
let SU=null,SU_T=0;
const suAgo=s=>s?new Date(s*1000).toLocaleString([], {weekday:'short',hour:'2-digit',minute:'2-digit'}):t('noch nie','never');
const suDays=s=>s==null?'':s<86400?t('läuft seit heute','up since today'):t(`läuft seit ${Math.floor(s/86400)} Tagen`,`up for ${Math.floor(s/86400)} days`);
const suIc=(n,c)=>typeof ic==='function'?ic(n,c):'';
const suRun=r=>!!(r.unit||r.lauf&&r.lauf.laeuft);
// one line under the computer's name in the card and on top of its column
function suShort(r){if(!r.da)return t('antwortet nicht','does not answer');if(!r.t)return t('noch nicht geprüft','not checked yet');
  if(suRun(r))return t(`läuft · ${r.lauf.n} von ${r.lauf.m}`,`running · ${r.lauf.n} of ${r.lauf.m}`);
  if(!r.anzahl)return t('aktuell','up to date');
  return r.sicherheit?t(`${r.anzahl} Updates, davon ${r.sicherheit} Sicherheit`,`${r.anzahl} updates, ${r.sicherheit} for security`):t(`${r.anzahl} Updates`,`${r.anzahl} updates`)}
function suMore(r,d){const p=[];if(r.wartet)p.push(t('wartet auf eine Sprechpause','waits for a pause in speech'));
  if(r.neustart&&!suRun(r))p.push(t('Neustart nötig','restart needed'));
  if(r.opencode&&d.opencode.neuer)p.push(t(`OpenCode neu: ${d.opencode.neu}`,`OpenCode new: ${d.opencode.neu}`));
  if(r.rolle==='panel'&&d.osv.warn.length)p.push(t(`Python: ${d.osv.warn.length} Warnungen`,`Python: ${d.osv.warn.length} warnings`));
  const fw=suFirmware(r).filter(x=>x[2]);if(fw.length)p.push(t(`${fw.map(x=>x[0]).join(', ')} von Hand`,`${fw.map(x=>x[0]).join(', ')} by hand`));
  if(!p.length&&r.anzahl&&!r.sicherheit)p.push(t('keine Sicherheit','none for security'));
  return p.join(' · ')}
const suPill=r=>!r.da?'bad':r.sicherheit?'bad':r.anzahl||r.neustart?'warn':'ok';
// [name, now, newer] of the firmware and drivers this computer has
function suFirmware(r){const out=[],v=x=>x&&x.jetzt?x:null;
  if(r.familie==='debian'&&v(r.eeprom))out.push(['EEPROM',r.eeprom.jetzt,r.eeprom.neu&&r.eeprom.neu!==r.eeprom.jetzt?r.eeprom.neu:'']);
  if(v(r.treiber))out.push([t('NVIDIA-Treiber','NVIDIA driver'),r.treiber.jetzt,r.treiber.neu&&r.treiber.neu!==r.treiber.jetzt?r.treiber.neu:'']);
  if(v(r.dgx))out.push(['DGX OS',r.dgx.jetzt,r.dgx.neu&&r.dgx.neu!==r.dgx.jetzt?r.dgx.neu:'']);
  return out}
// ---------------------------------------------------------------- the card under Zustand → Überblick
async function zSysup(d){const box=$('zsysup');if(!box||document.hidden)return;
  if(!d){try{d=await (await api('/api/admin/sysup?lang='+L,{cache:'no-store'})).json()}catch{return}}
  SU=d;box.hidden=!d.on;window.SUNEED=[];if(!d.on){suClose();return}
  const sec=d.rechner.reduce((a,r)=>a+(r.sicherheit||0),0),all=d.rechner.reduce((a,r)=>a+(r.anzahl||0),0),b=$('zsubadge');
  b.hidden=false;b.className='pill subadge '+(sec?'bad':all?'warn':'ok');b.textContent=sec?t(`${sec} Sicherheit`,`${sec} security`):all?t(`${all} Updates`,`${all} updates`):t('aktuell','up to date');
  setHtml($('zsulist'),d.rechner.map(r=>`<div class="zrow sutap"><span class="pill ${suPill(r)}">${esc(r.name)}</span><span><b>${esc(suShort(r))}</b><small>${esc(suMore(r,d))}</small></span>${suIc('chev','zch')}</div>`).join(''));
  $('zsumsg').textContent=t(`zuletzt geprüft ${suAgo(d.checked)}`,`last checked ${suAgo(d.checked)}`);
  // „Braucht dich“ (admin.js zustand): security updates waiting, a restart only the admin may start
  for(const r of d.rechner){if(r.sicherheit)SUNEED.push({lvl:'warn',text:t(`${r.sicherheit} Sicherheitsupdates für ${r.name}.`,`${r.sicherheit} security updates for ${r.name}.`),go:t('Zustand → System-Updates','Status → System updates'),btn:t('Ansehen','View')});
    if(r.neustart&&!suRun(r))SUNEED.push({lvl:'warn',text:t(`${r.name} braucht einen Neustart.`,`${r.name} needs a restart.`),go:t('Zustand → System-Updates','Status → System updates'),btn:t('Ansehen','View')})}
  if(!$('zsudet').hidden)suDraw();
  // while a run goes on, the page follows it every 5 s
  clearTimeout(SU_T);if(d.rechner.some(suRun)&&!$('zsudet').hidden)SU_T=setTimeout(()=>zSysup(),5e3)}
window.zSysup=zSysup;
// ---------------------------------------------------------------- the page Zustand → System-Updates
function suOpen(){const p=$('zsudet');if(!p)return;p.hidden=false;document.body.classList.add('sudet');suDraw();if(!SU)zSysup()}
function suClose(){const p=$('zsudet');if(!p||p.hidden)return;p.hidden=true;document.body.classList.remove('sudet');clearTimeout(SU_T)}
const suSec=(n,de,en,sub)=>`<h3 class="sec"><i class="sunum">${n}</i>${esc(t(de,en))}${sub?`<span class="mut">${esc(sub)}</span>`:''}</h3>`;
const suBtn=(act,r,de,en,cls,more)=>`<button class="b${cls?' '+cls:''}" type="button" data-su="${act}" data-r="${esc(r)}"${more||''}>${esc(t(de,en))}</button>`;
function suPkgs(r){const l=r.pakete||[];if(!l.length)return '';
  const row=x=>`<div class="dvcommit"><span class="sun"><b>${esc(x.n)}</b><small><code>${esc(x.alt||'–')}</code> → <code>${esc(x.neu)}</code></small></span>${
    x.s?`<span class="ld-badge err">${esc(t('Sicherheit','Security'))}</span>`:''}${x.hand?`<span class="ld-badge">${esc(t('von Hand','by hand'))}</span>`:''}${x.fremd?`<span class="ld-badge">${esc(t('andere Quelle','other source'))}</span>`:''}</div>`;
  return `<details class="supk"${l.length<=8?' open':''}><summary>${esc(t(`Pakete (${l.length}) · alt → neu`,`Packages (${l.length}) · old → new`))}</summary><div class="dvcommits">${l.map(row).join('')}</div></details>`}
function suOs(r){const q=r.quellen||{eigen:[],fremd:0};let h=suSec(1,'Betriebssystem','Operating system','apt');
  if(!r.da)return h+`<div class="wkerkl bad">${esc(t('Der Rechner antwortet gerade nicht.','The computer does not answer right now.'))}</div>`;
  if(!r.t)return h+`<div class="mut">${esc(t('Noch nicht geprüft. „Jetzt prüfen“ fragt seine Quellen.','Not checked yet. "Check now" asks its sources.'))}</div>`;
  h+=`<div class="dvtiles su2"><div class="dvtile"><span class="dvtk">${esc(t('Verfügbar','Available'))}</span><b class="dvtw ${r.sicherheit?'bad':r.anzahl?'warn':'ok'}"><i></i><span class="dvtv">${esc(r.anzahl?t(`${r.anzahl} Updates`,`${r.anzahl} updates`):t('aktuell','up to date'))}</span></b><small>${esc(r.sicherheit?t(`davon ${r.sicherheit} Sicherheit`,`${r.sicherheit} for security`):t('keine Sicherheit','none for security'))}</small></div>`
    +`<div class="dvtile"><span class="dvtk">${esc(t('Quellen','Sources'))}</span><b class="dvtw"><span class="dvtv">${esc(t(`${q.eigen.length} feste`,`${q.eigen.length} fixed`))}</span></b><small>${esc(q.eigen.join(t(' und ',' and '))||'–')}${q.fremd?esc(t(` · ${q.fremd} andere bleiben stehen`,` · ${q.fremd} others stay as they are`)):''}</small></div></div>`;
  if(r.update==='fehler')h+=`<div class="wkerkl bad">${esc(t('Die Quellen ließen sich zuletzt nicht abfragen; gezeigt ist der Stand davor.','The sources could not be asked last time; shown is the state before.'))}</div>`;
  const L0=r.lauf||{};
  if(suRun(r)){const pct=L0.m?Math.round(100*L0.n/L0.m):0,done=(L0.fertig||[]).slice(-5);
    h+=`<div class="suprog"><div class="suph"><span class="pill warn sulive">${esc(t(`läuft · ${L0.n} von ${L0.m}`,`running · ${L0.n} of ${L0.m}`))}</span><span class="mut">${esc(t(`seit ${suAgo(L0.seit)}`,`since ${suAgo(L0.seit)}`))}</span></div>`
      +`<div class="subar"><i style="width:${pct}%"></i></div><div class="dvcommits sulog">${done.map(n=>`<div class="dvcommit"><span class="suok">${suIc('check')}</span><span class="sun"><b>${esc(n)}</b></span></div>`).join('')}`
      +(L0.jetzt&&!done.includes(L0.jetzt)?`<div class="dvcommit sunow"><span class="suspin"></span><span class="sun"><b>${esc(L0.jetzt)}</b><small>${esc(t('wird eingespielt','being installed'))}</small></span></div>`:'')
      +(L0.m>L0.n?`<div class="dvcommit sumore">${esc(t(`noch ${L0.m-L0.n} Pakete`,`${L0.m-L0.n} packages to go`))}</div>`:'')+`</div>`
      +`<div class="wkerkl">${esc(t('Begonnen hat er in einer Sprechpause; er läuft mit niedrigster Priorität. Abbrechen geht nicht mitten in einem Paket.','It started in a pause in speech and runs at the lowest priority. It cannot be stopped in the middle of a package.'))}</div></div>`;
    return h}
  if(r.wartet)h+=`<div class="wkerkl suwait"><b>${esc(t('Wartet, Sprache läuft.','Waiting, speech is on.'))}</b> ${esc(t(`Um ${suAgo(r.wartet)} angestoßen, beginnt in der nächsten Pause von mindestens ${Math.round(SU.pause_s/60)} Minuten.`,`Asked at ${suAgo(r.wartet)}, starts in the next pause of at least ${Math.round(SU.pause_s/60)} minutes.`))}</div>`
    +`<div class="row su-act">${suBtn('nichtwarten',r.rolle,'Nicht mehr warten','Stop waiting')}</div>`;
  else if(L0.ende&&!r.neustart)h+=`<div class="wkerkl${L0.ok===false?' bad':''}">${esc(L0.ok===false?t(`Der letzte Lauf (${suAgo(L0.ende)}) endete mit einem Fehler nach ${L0.n} von ${L0.m} Paketen; der Rest bleibt angeboten.`,`The last run (${suAgo(L0.ende)}) ended with an error after ${L0.n} of ${L0.m} packages; the rest stays on offer.`)
    :t(`Zuletzt eingespielt ${suAgo(L0.ende)}: ${L0.n} von ${L0.m}, ohne Fehler.`,`Last installed ${suAgo(L0.ende)}: ${L0.n} of ${L0.m}, without errors.`))}</div>`;
  if(r.neustart){h+=`<div class="wkerkl bad"><b>${esc(t('Neustart nötig.','Restart needed.'))}</b> ${esc(r.rolle==='panel'?t('Kernel und Bibliotheken gelten erst danach. Das Panel ist dabei etwa eine Minute weg.','Kernel and libraries count only after it. The panel is gone for about a minute.'):t('Kernel und Bibliotheken gelten erst danach. Die Modelle sind dabei einige Minuten weg.','Kernel and libraries count only after it. The models are gone for a few minutes.'))}</div>`;
    h+=r.neustart_nacht?`<div class="row su-act"><span class="pill warn">${esc(t('heute Nacht, 03–05 Uhr','tonight, 03–05'))}</span>${suBtn('nichtwarten',r.rolle,'Doch nicht','Cancel')}</div>`
      :`<div class="row su-act">${suBtn('neustart-jetzt',r.rolle,'Jetzt neu starten','Restart now','p needcode2')}${suBtn('neustart-nacht',r.rolle,'Heute Nacht','Tonight','needcode2')}</div><div class="fh">${esc(t('„Heute Nacht“ startet zwischen 03 und 05 Uhr neu, nur wenn gerade niemand spricht. Ohne deine Wahl startet nichts neu.','"Tonight" restarts between 03 and 05, only while nobody talks. Nothing restarts without your choice.'))}</div>`}
  h+=suPkgs(r);
  if(r.anzahl&&!r.wartet)h+=`<div class="row su-act">${suBtn('einspielen',r.rolle,'Jetzt einspielen','Install now','p needcode2')}<span class="mut">${esc(t('fragt nach frischem Code','asks for a fresh code'))}</span></div><div class="suask" data-ask="${esc(r.rolle)}" hidden></div>`
    +`<div class="fh">${esc(t('Ein fester Ablauf als root, nur aus den festen Quellen, ohne etwas zu entfernen. Nie, solange jemand mit dem Spark spricht: dann wartet er bis zur nächsten Pause.','A fixed run as root, only from the fixed sources, without removing anything. Never while somebody talks with the Spark: then it waits for the next pause.'))}</div>`;
  return h}
function suCode(r,d){const oc=d.opencode,o=d.osv;let h=suSec(2,'OpenCode und Python-Pakete','OpenCode and Python packages',t('gepinnt','pinned'));
  h+='<div class="sulist2">';
  h+=r.opencode?`<div class="zrow"><span class="pill ${oc.neuer?'warn':'ok'}">OpenCode</span><span><b>${esc(oc.neuer?t(`${oc.alt} · neu: ${oc.neu}`,`${oc.alt} · new: ${oc.neu}`):oc.neu?t(`${oc.alt} · aktuell`,`${oc.alt} · up to date`):oc.alt)}</b><small>${esc(oc.fehler&&!oc.neu?t('nicht geprüft, kein Internet','not checked, no internet'):t('fest im Spark, nicht von npm','fixed in the Spark, not from npm'))}</small></span></div>`
    :`<div class="zrow"><span class="pill">OpenCode</span><span><b>${esc(t('nicht auf diesem Rechner','not on this computer'))}</b><small>${esc(t('gepinnt im Spark','pinned in the Spark'))}</small></span></div>`;
  const off=!d.internet||o.fehler&&!o.t;
  h+=`<div class="zrow"><span class="pill ${off||!o.t?'':o.warn.length?'bad':'ok'}">${esc(t('Python-Pakete','Python packages'))}</span><span><b>${esc(off?t('nicht geprüft, kein Internet','not checked, no internet'):!o.t?t('noch nicht geprüft','not checked yet'):o.warn.length?t(`${o.warn.length} Sicherheitswarnungen (OSV)`,`${o.warn.length} security warnings (OSV)`):t('keine Warnung (OSV)','no warning (OSV)'))}</b><small>${
    o.warn.map(w=>`<code>${esc(w.n)} ${esc(w.v)}</code> ${esc(w.ids.join(', '))}`).join(' · ')}${o.warn.length?' · ':''}${esc(t(`${o.n} Pakete gepinnt`,`${o.n} packages pinned`))}${o.t?esc(t(` · geprüft ${suAgo(o.t)}`,` · checked ${suAgo(o.t)}`)):''}</small></span></div></div>`;
  if(r.rolle!=='panel')return h;
  const can=o.warn.length||oc.neuer;
  if(d.pruefbitte)h+=`<div class="wkerkl"><b>${esc(t('Prüfbitte offen','Check request open'))}</b> ${esc(t(`seit ${suAgo(d.pruefbitte.t)}. In einen Claude-Thread kopieren:`,`since ${suAgo(d.pruefbitte.t)}. Copy into a Claude thread:`))}</div><pre class="supb">${esc(d.pruefbitte.text)}</pre>`
    +`<div class="row su-act">${suBtn('kopieren','panel','Kopieren','Copy')}${suBtn('pb-weg','panel','Löschen','Delete')}</div>`;
  else h+=`<div class="row su-act"><button class="b" type="button" data-su="pruefbitte" data-r="panel"${can?'':' disabled'}>${esc(t('Von Claude prüfen lassen','Have Claude check it'))}</button>${can?'':`<span class="mut">${esc(t('nichts zu prüfen','nothing to check'))}</span>`}</div>`;
  return h+`<div class="fh">${esc(t('Legt eine Prüfbitte für einen Claude-Thread an: er pinnt neu und lässt die Tests laufen. Kommt mit dem nächsten Spark-Update, nie ungeprüft.','Makes a check request for a Claude thread: it pins anew and runs the tests. Comes with the next Spark update, never unchecked.'))}</div>`}
function suFw(r){const fw=suFirmware(r);let h=suSec(3,'Firmware und Treiber','Firmware and drivers',t('nur Anzeige','display only'));
  h+='<div class="sulist2">'+(fw.length?fw.map(([n,a,b])=>`<div class="zrow"><span class="pill ${b?'warn':'ok'}">${esc(n)}</span><span><b>${esc(b?t(`${a} · neu: ${b}`,`${a} · new: ${b}`):t(`${a} · aktuell`,`${a} · up to date`))}</b></span></div>`).join('')
    :`<div class="zrow"><span class="pill">–</span><span><b>${esc(t('nichts gemeldet','nothing reported'))}</b></span></div>`)
    +(r.hand?`<div class="zrow"><span class="pill warn">${esc(t('Pakete','Packages'))}</span><span><b>${esc(t(`${r.hand} bleiben stehen`,`${r.hand} stay as they are`))}</b><small>${esc(t('Firmware, Kernel und Treiber nur von Hand','firmware, kernel and drivers only by hand'))}</small></span></div>`:'')+'</div>';
  return h+`<div class="row su-act">${suBtn('hand',r.rolle,'Von Hand einspielen','Install by hand')}<span class="mut">${esc(t('öffnet die Anleitung','opens the guide'))}</span></div>`
    +`<div class="fh">${esc(r.rolle==='panel'?t('Ein Fehler hier legt das Panel lahm. Darum nie von selbst, Schritt für Schritt unter Funktionen → Anleitungen → Firmware von Hand.','A mistake here stops the panel. So never by itself, step by step under Features → Guides → Firmware by hand.'):t('Ein Fehler hier legt die Modelle lahm. Darum nie von selbst, Schritt für Schritt unter Funktionen → Anleitungen → Firmware von Hand.','A mistake here stops the models. So never by itself, step by step under Features → Guides → Firmware by hand.'))}</div>`}
function suZeit(r,d){return suSec(4,'Zeitpunkt','Timing')+`<div class="setrow"><div class="lbl"><b>${esc(t('Nachts einspielen (03–05 Uhr)','Install at night (03–05)'))}</b><span>${esc(t('Nur Betriebssystem-Updates, nie Firmware. Neu gestartet wird erst nach deiner Freigabe.','Only operating system updates, never firmware. A restart only after your release.'))}</span></div><label class="tgl"><input type="checkbox" data-su="nacht" data-r="${esc(r.rolle)}"${r.nacht?' checked':''} aria-label="${esc(t('Nachts einspielen','Install at night'))}"><i></i></label></div>`
  +`<div class="sumeta"><span>${esc(t(`zuletzt geprüft ${suAgo(r.t||d.checked)}`,`last checked ${suAgo(r.t||d.checked)}`))}</span><span>${esc(t(`nächste Prüfung ${suAgo(d.next)}`,`next check ${suAgo(d.next)}`))}</span></div>`}
function suComp(r,d){return `<div class="card sucomp"><div class="suhd"><h3>${esc(r.name)}</h3><span class="pill ${suPill(r)} subadge">${esc(suShort(r))}</span></div><div class="mut sudev">${esc([r.os,suDays(r.seit)].filter(Boolean).join(' · '))}</div>`
  +suOs(r)+suCode(r,d)+suFw(r)+suZeit(r,d)+`<div class="mut sumsg" data-msg="${esc(r.rolle)}"></div></div>`}
function suDraw(){const d=SU,p=$('zsudet');if(!d||!p||!d.on)return;
  const sec=d.rechner.filter(r=>r.sicherheit),lvl=d.rechner.some(r=>!r.da)||sec.length?'bad':d.rechner.some(r=>r.anzahl||r.neustart)?'warn':'ok';
  const top=p.querySelector('.sutop');top.dataset.lvl=lvl;
  p.querySelector('.sutopt').textContent=sec.length?sec.map(r=>t(`${r.sicherheit} Sicherheitsupdates auf ${r.name}.`,`${r.sicherheit} security updates on ${r.name}.`)).join(' '):lvl==='warn'?t('Updates warten.','Updates are waiting.'):lvl==='ok'?t('Alles aktuell.','Everything up to date.'):t('Ein Rechner antwortet nicht.','A computer does not answer.');
  p.querySelector('.sutopx').textContent=d.rechner.map(r=>r.name+': '+suShort(r)).join(' · ')+(d.talking?' · '+t('gerade spricht jemand','somebody is talking right now'):'');
  setHtml(p.querySelector('.sumeta'),`<span>${esc(t(`zuletzt geprüft ${suAgo(d.checked)}`,`last checked ${suAgo(d.checked)}`))}</span><span>${esc(t(`nächste Prüfung ${suAgo(d.next)}`,`next check ${suAgo(d.next)}`))}</span>`);
  // the open questions (einspielen) and messages stay while the page is drawn again
  const keep={};p.querySelectorAll('.suask:not([hidden]),.sumsg').forEach(x=>{keep[(x.dataset.ask?'a':'m')+(x.dataset.ask||x.dataset.msg)]=x.hidden?null:x.innerHTML});
  setHtml($('zsugrid'),d.rechner.map(r=>suComp(r,d)).join(''));
  for(const [k,v] of Object.entries(keep)){const x=p.querySelector(k[0]==='a'?`.suask[data-ask="${k.slice(1)}"]`:`.sumsg[data-msg="${k.slice(1)}"]`);if(x&&v!=null){x.innerHTML=v;x.hidden=false}}
  const S=d.spark||{};
  setHtml(p.querySelector('.sunebenlist'),`<div class="zrow" data-way="${esc(t('Einstellungen → Update','Settings → Update'))}"><span class="pill ok">${esc(t('Spark-Update','Spark update'))}</span><span><b>${esc(S.version||'')}</b><small>${esc(t('der Code des Spark selbst, mit Tests auf GitHub','the Spark\'s own code, with tests on GitHub'))}</small></span></div>`
    +(S.geraete==null?'':`<div class="zrow" data-way="${esc(t('Zustand → Überblick → Geräte-Updates','Status → Summary → Device updates'))}"><span class="pill ${S.geraete?'warn':'ok'}">${esc(t('Geräte-Updates','Device updates'))}</span><span><b>${esc(S.geraete?t(`${S.geraete} warten`,`${S.geraete} waiting`):t('aktuell','up to date'))}</b><small>${esc(t('Lautsprecher, Android, Pebble, Begleiter','speakers, Android, Pebble, companion'))}</small></span></div>`));
  if(typeof codeLock==='function')p.querySelectorAll('.needcode2').forEach(b=>codeLock(b,'protect'))}
// the question before the run: what happens, and why apt upgrade and not full-upgrade
function suAsk(rolle){const r=SU.rechner.find(x=>x.rolle===rolle),box=document.querySelector(`.suask[data-ask="${rolle}"]`);if(!r||!box)return;
  box.hidden=false;box.innerHTML=`<ul class="facts small"><li>${esc(t(`${r.anzahl-r.hand-r.fremd} Pakete aus ${(r.quellen.eigen||[]).join(t(' und ',' and '))}, davon ${r.sicherheit} Sicherheit.`,`${r.anzahl-r.hand-r.fremd} packages from ${(r.quellen.eigen||[]).join(' and ')}, ${r.sicherheit} for security.`))}</li>`
    +`<li>${esc(t('apt upgrade, nicht full-upgrade: nimmt neue Abhängigkeiten dazu, entfernt aber nie ein Paket. Was nur mit Entfernen ginge, bleibt angeboten.','apt upgrade, not full-upgrade: takes new dependencies in but never removes a package. What would need a removal stays on offer.'))}</li>`
    +((r.hand+r.fremd)?`<li>${esc(t(`${r.hand+r.fremd} bleiben stehen (Firmware, Kernel, Treiber, andere Quellen).`,`${r.hand+r.fremd} stay as they are (firmware, kernel, drivers, other sources).`))}</li>`:'')
    +`<li>${esc(t('Beginnt erst nach 2 Minuten ohne Sprache, läuft mit niedrigster Priorität; ein Neustart nur, wenn du ihn wählst.','Starts only after 2 minutes without speech, runs at the lowest priority; a restart only when you choose it.'))}</li></ul>`
    +`<div class="row">${suBtn('einspielen-ja',rolle,'Einspielen','Install','p needcode2')}${suBtn('einspielen-nein',rolle,'Abbrechen','Cancel')}</div>`;
  if(typeof codeLock==='function')box.querySelectorAll('.needcode2').forEach(b=>codeLock(b,'protect'))}
function suMsg(rolle,text){const m=document.querySelector(`.sumsg[data-msg="${rolle}"]`);if(m)m.textContent=text;else $('zsumsg').textContent=text}
async function suPost(path,body,rolle,method){try{const d=await (await api(path+'?lang='+L,{method:method||'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();return d}
  catch(e){suMsg(rolle,e.message);return null}}
async function suCheck(){suMsg('panel','');$('zsumsg').textContent=t('Prüfe …','Checking …');const d=await suPost('/api/admin/sysup/pruefen',{}, 'panel');
  if(d){$('zsumsg').textContent=t('Geprüft.','Checked.');zSysup(d)}else $('zsumsg').textContent=$('zsumsg').textContent||t('Ging nicht.','Did not work.')}
async function suAct(b){const a=b.dataset.su,r=b.dataset.r;let d=null;
  if(a==='einspielen'){suAsk(r);return}
  if(a==='einspielen-nein'){const x=document.querySelector(`.suask[data-ask="${r}"]`);if(x){x.hidden=true;x.textContent=''}return}
  if(a==='hand'){wayGo(t('Funktionen → Anleitungen → Firmware von Hand','Features → Guides → Firmware by hand'));return}
  if(a==='kopieren'){try{await navigator.clipboard.writeText(SU.pruefbitte.text);suMsg(r,t('Kopiert.','Copied.'))}catch{suMsg(r,t('Kopieren ging nicht; den Text oben markieren.','Copying did not work; select the text above.'))}return}
  b.disabled=true;
  if(a==='einspielen-ja'){d=await suPost('/api/admin/sysup/einspielen',{rechner:r},r);if(d)suMsg(r,d.wartet?t('Wartet auf eine Sprechpause.','Waits for a pause in speech.'):t('Läuft.','Running.'))}
  else if(a==='nichtwarten')d=await suPost('/api/admin/sysup/nicht-warten',{rechner:r},r);
  else if(a==='neustart-jetzt'){d=await suPost('/api/admin/sysup/neustart',{rechner:r,wann:'jetzt'},r);if(d){suMsg(r,t('Startet neu.','Restarting.'));d=null}}
  else if(a==='neustart-nacht')d=await suPost('/api/admin/sysup/neustart',{rechner:r,wann:'nacht'},r);
  else if(a==='pruefbitte'){d=await suPost('/api/admin/sysup/pruefbitte',{},r);if(d)suMsg(r,t('Prüfbitte angelegt.','Check request made.'))}
  else if(a==='pb-weg')d=await suPost('/api/admin/sysup/pruefbitte',{},r,'DELETE');
  b.disabled=false;if(d)zSysup(d)}
{const p=$('zsudet');
 if(p){p.addEventListener('click',e=>{const b=e.target.closest('button[data-su]');if(b)suAct(b)});
  p.addEventListener('change',async e=>{const x=e.target.closest('input[data-su="nacht"]');if(!x)return;const want=x.checked;x.disabled=true;
    const d=await suPost('/api/admin/sysup/nacht',{rechner:x.dataset.r,an:want},x.dataset.r);x.disabled=false;if(d)zSysup(d);else x.checked=!want});
  $('zsuback').onclick=suClose;$('zsucheck2').onclick=suCheck;
  // a way into the page (Zustand → System-Updates) shows it; a way to anything else under Zustand leaves it
  $('mon').addEventListener('wayopen',e=>{if(p.contains(e.target))suOpen();else suClose()});
  new MutationObserver(()=>{if(!$('mon').classList.contains('on'))suClose()}).observe($('mon'),{attributes:true,attributeFilter:['class']});
  document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('nav [data-s="mon"],#subnav [data-s="mon"]'))suClose()},true)}
 if($('zsucheck'))$('zsucheck').onclick=suCheck;
 if($('zsuopen'))$('zsuopen').onclick=()=>{suOpen();scrollTo(0,0)}}
