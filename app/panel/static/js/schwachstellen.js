// Zustand → Schwachstellen (schwachstellen.py, admin; Bild schwachstellen/entwurf.png): the card under Bereiche and its
// page: the light on top with one sentence, a tile per place (Pi, tars, Docker, Apps, Betriebssystem), the filter by
// weight, the findings grouped by what to do and, beside them, the one that is picked. Only names, versions, ids,
// numbers and fixed words, all through esc(); the only button asks the check again (a fixed endpoint).
let SW=null,SW_SEL='',SW_F='alle';
const swAgo=s=>s?new Date(s*1000).toLocaleString([], {weekday:'short',hour:'2-digit',minute:'2-digit'}):t('noch nie','never');
const SW_STUFE={kritisch:['Kritisch','Critical','bad'],hoch:['Hoch','High','warn'],mittel:['Mittel','Medium',''],niedrig:['Niedrig','Low',''],unbekannt:['Unbekannt','Unknown','']};
const SW_ORT={pi:['Pi · Python','Pi · Python'],tars:['tars · Python','tars · Python'],docker:['Docker-Abbilder','Docker images'],apps:['Apps und Begleiter','Apps and companion'],os:['Betriebssystem','Operating system']};
// the fixed groups, in the order of the page: what to do
// the apps' parts (osv.APP_TEILE)
const SW_TEIL={ios:['iPhone-App','iPhone app'],android:['Android-App','Android app'],pebble:['Pebble-App','Pebble app'],begleiter:['Begleiter','Companion'],'panel-js':['Panel (JavaScript)','Panel (JavaScript)']};
// how far the place is reachable (Paket 4, fixed sentences): helps to weigh a hole
const SW_ERREICH={pi:['Läuft im Panel, das Heimnetz und eingetragene Geräte erreichen; von außen nur über den Proxy.','Runs in the panel, reached from the home network and paired devices; from outside only through the proxy.'],
  tars:['Läuft auf tars hinter dem TLS-Tor: nur der Panel-Rechner erreicht es.','Runs on tars behind the TLS-Tor: only the panel computer reaches it.'],
  docker:['Läuft im Abbild auf tars hinter dem TLS-Tor: nur der Panel-Rechner erreicht es.','Runs inside the image on tars behind the TLS-Tor: only the panel computer reaches it.'],
  apps:['Läuft auf den Geräten der Profile (App, Begleiter) oder im Browser.','Runs on the devices of the profiles (app, companion) or in the browser.'],
  os:['Das Betriebssystem des Rechners selbst.','The operating system of the computer itself.']};
const swAkt=f=>f.hin?[t('Bewusst hingenommen','Accepted knowingly'),'']:((SW&&SW.aktionen)||{})[f.aktion]||[f.aktion,f.aktion];
const swPill=s=>{const x=SW_STUFE[s]||SW_STUFE.unbekannt;return `<span class="pill ${x[2]} swpill">${esc(t(x[0],x[1]))}</span>`};
function swLvl(d){const z=d.zahl||{};return z.kritisch?'bad':z.hoch||d.funde.some(f=>['anheben','neu','abbild','os'].includes(f.aktion))?'warn':'ok'}
function swSatz(d){const z=d.zahl||{},neu=d.funde.filter(f=>['anheben','neu','abbild'].includes(f.aktion)).length;
  if(!d.t)return t('Noch nicht geprüft.','Not checked yet.');
  if(!d.funde.length)return t('Keine bekannte Lücke.','No known hole.');
  const a=[];if(z.kritisch)a.push(t(`${z.kritisch} kritische Lücke${z.kritisch>1?'n':''}`,`${z.kritisch} critical hole${z.kritisch>1?'s':''}`));
  if(z.hoch)a.push(t(`${z.hoch} hohe`,`${z.hoch} high`));
  if(neu)a.push(t(`${neu} brauch${neu>1?'en':'t'} ein Update`,`${neu} need${neu>1?'':'s'} an update`));
  return (a.length?a.join(', '):t(`${d.funde.length} Funde`,`${d.funde.length} findings`))+'.'}
// the fixed sentence of what to do (never a text from outside)
function swTun(f){if(f.aktion==='anheben')return t(`Neue Version ${f.behoben} nötig. Ist „Lücke schließen“ auf GitHub eingeschaltet, hebt es das Paket nach grünen Tests an; danach kommt es mit dem nächsten Spark-Update.`,`New version ${f.behoben} needed. When "Lücke schließen" is switched on at GitHub, it raises the package after green tests; then it comes with the next Spark update.`);
  if(f.aktion==='neu'&&f.ort==='apps'){const p=t(...(SW_TEIL[f.wo]||[f.wo,f.wo]));return t(`Neue Version ${f.behoben} nötig. ${p} bringt das Paket mit: ein Mensch oder ein Claude-Thread hebt es an, es kommt mit dem nächsten Bau.`,`New version ${f.behoben} needed. ${p} brings the package along: a person or a Claude thread raises it, it comes with the next build.`)}
  if(f.aktion==='neu'&&f.ort==='pi')return t(`Neue Version ${f.behoben} nötig: ein Mensch oder ein Claude-Thread hebt sie an, sie kommt mit dem nächsten Spark-Update.`,`New version ${f.behoben} needed: a person or a Claude thread raises it, it comes with the next Spark update.`);
  if(f.aktion==='abbild')return t(`Im Abbild steckt ${f.n} ${f.v}, behoben in ${f.behoben}. Ein neueres Abbild (Digest) bringt den Fix: ein Mensch oder ein Claude-Thread pinnt es und testet es auf tars.`,`The image carries ${f.n} ${f.v}, fixed in ${f.behoben}. A newer image (digest) brings the fix: a person or a Claude thread pins it and tests it on tars.`);
  if(f.aktion==='neu')return t(`Neue Version ${f.behoben} nötig. Engines prüfen die Tests auf GitHub nicht: ein Mensch oder ein Claude-Thread zieht sie nach und testet sie auf tars.`,`New version ${f.behoben} needed. GitHub's tests do not check engines: a person or a Claude thread pins it anew and tests it on tars.`);
  if(f.aktion==='alt')return t(`Das Abbild ist ${f.tage} Tage alt (mehr als ${SW.docker_tage}). OSV kennt Abbilder nicht: nach einem neueren Digest sehen.`,`The image is ${f.tage} days old (more than ${SW.docker_tage}). OSV does not know images: look for a newer digest.`);
  if(f.aktion==='os')return t(`${f.anzahl} Sicherheits-Updates warten. Einspielen unter Zustand → System-Updates.`,`${f.anzahl} security updates wait. Install under Status → System updates.`);
  return t('OSV nennt noch keine Version mit Fix. Beobachten; die nächste Prüfung sieht es von selbst.','OSV names no version with a fix yet. Watch; the next check sees it by itself.')}
function swName(f){return f.ort==='os'?t(f.n==='panel'?'Panel-Rechner':'Modell-Rechner',f.n==='panel'?'Panel computer':'Model computer'):f.n}
function swWo(f){if(!f.wo)return '';if(f.ort==='apps')return t(...(SW_TEIL[f.wo]||[f.wo,f.wo]));if(f.ort==='pi'||f.ort==='tars')return /\.lock$/.test(f.wo)||f.wo==='install.sh'?f.wo:'venv-'+f.wo;return f.wo}
function swUnter(f){const o=SW_ORT[f.ort]||[f.ort,f.ort],p=[t(o[0],o[1])];if(f.wo&&f.ort!=='os')p[0]+=' · '+swWo(f);
  if(f.behoben)p.push(t(`behoben in ${f.behoben}`,`fixed in ${f.behoben}`));
  if(f.aktion==='alt')p.push(t(`${f.tage} Tage alt`,`${f.tage} days old`));
  if(f.aktion==='os')p.push(t(`${f.anzahl} Sicherheits-Updates`,`${f.anzahl} security updates`));
  if(f.neu)p.push(t('neu','new'));return p.join(' · ')}
// ---------------------------------------------------------------- the card under Zustand → Überblick
async function zSchwach(d){const box=$('zschwach');if(!box||document.hidden)return;
  if(!d){try{d=await (await api('/api/admin/schwach',{cache:'no-store'})).json()}catch{return}}
  SW=d;box.hidden=!d.on;window.SWNEED=[];if(!d.on){swClose();return}
  const lvl=swLvl(d),b=$('zswbadge'),z=d.zahl||{};b.hidden=false;b.className='pill subadge '+lvl;
  b.textContent=z.kritisch?t(`${z.kritisch} kritisch`,`${z.kritisch} critical`):d.funde.length?t(`${d.funde.length} Funde`,`${d.funde.length} findings`):d.t?t('keine Lücke','no hole'):t('nicht geprüft','not checked');
  $('zswtext').textContent=swSatz(d);
  $('zswmsg').textContent=d.fehler?t(`zuletzt ohne Antwort · Stand ${swAgo(d.t)}`,`no answer last time · state of ${swAgo(d.t)}`):t(`zuletzt geprüft ${swAgo(d.t)}`,`last checked ${swAgo(d.t)}`);
  if(z.kritisch||z.hoch)SWNEED.push({lvl:z.kritisch?'bad':'warn',text:t(`${z.kritisch?z.kritisch+' kritische':z.hoch+' hohe'} Schwachstellen.`,`${z.kritisch?z.kritisch+' critical':z.hoch+' high'} vulnerabilities.`),go:t('Zustand → Schwachstellen','Status → Vulnerabilities'),btn:t('Ansehen','View')});
  if(!$('zswdet').hidden)swDraw()}
window.zSchwach=zSchwach;
// ---------------------------------------------------------------- the page Zustand → Schwachstellen
function swOpen(){const p=$('zswdet');if(!p)return;p.hidden=false;document.body.classList.add('swdet');swDraw();if(!SW)zSchwach()}
function swClose(){const p=$('zswdet');if(!p||p.hidden)return;p.hidden=true;document.body.classList.remove('swdet')}
function swDetail(f){if(!f)return `<div class="mut">${esc(t('Einen Fund antippen.','Tap a finding.'))}</div>`;
  const row=(k,v)=>v?`<dt>${esc(k)}</dt><dd>${v}</dd>`:'';
  return `<div class="swdhd">${swPill(f.stufe)}${f.score!=null?`<span class="mut">CVSS ${esc(String(f.score))}</span>`:''}<b>${esc(swName(f))} ${esc(f.v||'')}</b></div>`
    +`<dl class="swdl">${row(t('Wo','Where'),esc(t(...(SW_ORT[f.ort]||[f.ort,f.ort]))+(f.wo&&f.ort!=='os'?' · '+swWo(f):'')))}${row(t('Behoben in','Fixed in'),esc(f.behoben||t('noch keine Version','no version yet')))}`
    +row(t('Ohne Fix','Without fix'),f.ohne_fix?esc(String(f.ohne_fix)):'')
    +row(t('Kennungen','Ids'),(f.ids||[]).map(i=>`<a class="swid" href="https://osv.dev/vulnerability/${encodeURIComponent(i)}" target="_blank" rel="noopener noreferrer">${esc(i)}</a>`).join(' · '))
    +row(t('Gefunden','Found'),esc(f.neu?t('heute, neu','today, new'):t('früher','earlier')))
    +row(t('Erreichbar','Reachable'),esc(t(...(SW_ERREICH[f.ort]||['','']))))
    +row('Issue',f.issue?`<a href="${esc(f.issue.url)}" target="_blank" rel="noopener noreferrer">#${esc(String(f.issue.nr))}</a>`:'')
    +row(t('Hingenommen','Accepted'),f.hin?esc(t(`bis ${swAgo(f.hin.bis)}: ${f.hin.grund}`,`until ${swAgo(f.hin.bis)}: ${f.hin.grund}`)):'')+`</dl>`
    +`<div class="wkerkl swtun"><b>${esc(t('Was zu tun ist','What to do'))}</b> ${esc(swTun(f))}</div>`
    +`<div class="row swact">${f.ids&&f.ids.length&&!f.issue&&SW.melden?`<button class="b" type="button" data-swa="melden">${esc(t('Als Issue melden','Report as issue'))}</button>`:''}`
    +(f.hin?`<button class="b" type="button" data-swa="zurueck">${esc(t('Nicht mehr hinnehmen','Stop accepting'))}</button>`:`<button class="b" type="button" data-swa="hin">${esc(t('Bewusst hinnehmen','Accept knowingly'))}</button>`)
    +`<span class="mut" id="zswmsg3"></span></div>`
    +(f.ids&&f.ids.length&&!f.issue&&!SW.melden?`<div class="fh">${esc(t('Als Issue melden braucht Probleme melden mit GitHub-Token: ','Reporting as an issue needs Problem reports with a GitHub token: '))}<a href="#" data-way="${esc(t('Funktionen → Zugang → Probleme melden','Features → Access → Reporting problems'))}">${esc(t('Funktionen → Zugang → Probleme melden','Features → Access → Reporting problems'))}</a></div>`:'')
    +`<div class="swhin" hidden><label class="mut" for="zswgrund">${esc(t(`Warum? Gilt ${SW.hin_tage} Tage und nur für diese Version.`,`Why? Holds ${SW.hin_tage} days and only for this version.`))}</label><input id="zswgrund" maxlength="200" autocomplete="off"><button class="b" type="button" data-swa="hin-ok">${esc(t('Hinnehmen','Accept'))}</button></div>`
    +(f.aktion==='os'?`<div class="zrow" data-way="${esc(t('Zustand → System-Updates','Status → System updates'))}"><span class="pill">${esc(t('System-Updates','System updates'))}</span><span><b>${esc(t('Öffnen','Open'))}</b></span></div>`:'')}
function swDraw(){const d=SW,p=$('zswdet');if(!d||!p||!d.on)return;
  const top=p.querySelector('.swtop');top.dataset.lvl=swLvl(d);
  p.querySelector('.swtopt').textContent=swSatz(d);
  p.querySelector('.swtopx').textContent=[t(`${Object.values(d.n||{}).reduce((a,b)=>a+b,0)} Bestandteile geprüft`,`${Object.values(d.n||{}).reduce((a,b)=>a+b,0)} parts checked`),'OSV',
    d.fehler?t(`zuletzt ohne Antwort, Stand ${swAgo(d.t)}`,`no answer last time, state of ${swAgo(d.t)}`):t(`zuletzt ${swAgo(d.t)}`,`last ${swAgo(d.t)}`),t(`nächste Prüfung ${swAgo(d.next)}`,`next check ${swAgo(d.next)}`)].join(' · ');
  const n=d.n||{},orte=d.orte||{};
  setHtml(p.querySelector('.swtiles'),['pi','tars','docker','apps','os'].map(o=>{const c=orte[o]||0,sub=o==='os'?(d.system_updates?t('Sicherheits-Updates','security updates'):t('System-Updates ist aus','System updates is off')):o==='docker'?t(`${n.docker||0} Pakete in ${n.abbilder||0} Abbildern`+(n.ungelesen?`, ${n.ungelesen} noch nicht gelesen`:''),`${n.docker||0} packages in ${n.abbilder||0} images`+(n.ungelesen?`, ${n.ungelesen} not read yet`:'')):o==='tars'&&n.tars_da===false?t(`${n.tars||0} aus install.sh, tars antwortet nicht`,`${n.tars||0} from install.sh, tars does not answer`):t(`${n[o]||0} geprüft`,`${n[o]||0} checked`);
    return `<div class="dvtile swtile"><span class="dvtk">${esc(t(...SW_ORT[o]))}</span><b class="dvtw ${c?(d.funde.some(f=>f.ort===o&&f.stufe==='kritisch')?'bad':'warn'):'ok'}"><span class="dvtv">${c}</span></b><small>${esc(sub)}</small></div>`}).join(''));
  const z=d.zahl||{},F=[['alle',t(`Alle ${d.funde.length}`,`All ${d.funde.length}`)],['kritisch',t(`Kritisch ${z.kritisch||0}`,`Critical ${z.kritisch||0}`)],['hoch',t(`Hoch ${z.hoch||0}`,`High ${z.hoch||0}`)],['mittel',t(`Mittel ${(z.mittel||0)+(z.niedrig||0)+(z.unbekannt||0)}`,`Medium ${(z.mittel||0)+(z.niedrig||0)+(z.unbekannt||0)}`)]];
  setHtml(p.querySelector('.swseg'),F.map(([k,l])=>`<button type="button" class="${SW_F===k?'on':''}" data-swf="${k}" aria-pressed="${SW_F===k}">${esc(l)}</button>`).join(''));
  const pass=f=>SW_F==='alle'||SW_F===f.stufe||SW_F==='mittel'&&['mittel','niedrig','unbekannt'].includes(f.stufe);
  const list=d.funde.filter(pass);let h='',last='';
  for(const f of list){const g=t(...swAkt(f));if(g!==last){h+=`${last?'</div>':''}<h3 class="swgrp">${esc(g)}</h3><div class="swlist">`;last=g}
    h+=`<button type="button" class="swrow${f.key===SW_SEL?' sel':''}" data-swk="${esc(f.key)}">${swPill(f.stufe)}<span><b>${esc(swName(f))} ${esc(f.v||'')}</b><small>${esc(swUnter(f))}</small></span></button>`}
  if(last)h+='</div>';
  if(!list.length)h=`<div class="mut swleer">${esc(d.t?t('Nichts in dieser Auswahl.','Nothing in this selection.'):t('Noch nicht geprüft. „Jetzt prüfen“ fragt OSV.','Not checked yet. "Jetzt prüfen" asks OSV.'))}</div>`;
  setHtml(p.querySelector('.swfunde'),h);
  setHtml(p.querySelector('.swdet'),swDetail(d.funde.find(f=>f.key===SW_SEL)))}
async function swTat(a){const f=SW&&SW.funde.find(x=>x.key===SW_SEL),m=$('zswmsg3');if(!f)return;
  if(a==='hin'){const b=$('zswdet').querySelector('.swhin');b.hidden=false;$('zswgrund').focus();return}
  const post=async(url,body)=>{m.textContent='…';try{const r=await api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});zSchwach(await r.json());return true}catch(e){m.textContent=e.message||t('Ging nicht.','Did not work.');return false}};
  if(a==='melden'){if(await post('/api/admin/schwach/melden',{key:f.key})){const x=$('zswmsg3');if(x)x.textContent=t('Gemeldet.','Reported.')}}
  else if(a==='hin-ok')await post('/api/admin/schwach/hinnehmen',{key:f.key,grund:$('zswgrund').value});
  else if(a==='zurueck')await post('/api/admin/schwach/hinnehmen',{key:f.key,weg:true})}
async function swCheck(){const m=$('zswmsg2');m.textContent=t('Prüfe …','Checking …');
  try{const r=await api('/api/admin/schwach/pruefen',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();
    m.textContent=t('Geprüft.','Checked.');zSchwach(d)}catch(e){m.textContent=e.message||t('Ging nicht.','Did not work.')}}
{const p=$('zswdet');
 if(p){p.addEventListener('click',e=>{const r=e.target.closest('button[data-swk]');if(r){SW_SEL=r.dataset.swk;swDraw();
      if(matchMedia('(max-width:760px)').matches)p.querySelector('.swdet').scrollIntoView({block:'start'});return}
    const a=e.target.closest('button[data-swa]');if(a){swTat(a.dataset.swa);return}
    const f=e.target.closest('button[data-swf]');if(f){SW_F=f.dataset.swf;swDraw()}});
  $('zswback').onclick=swClose;$('zswcheck2').onclick=swCheck;
  // a way into the page (Zustand → Schwachstellen) shows it; a way to anything else under Zustand leaves it
  $('mon').addEventListener('wayopen',e=>{if(p.contains(e.target))swOpen();else swClose()});
  new MutationObserver(()=>{if(!$('mon').classList.contains('on'))swClose()}).observe($('mon'),{attributes:true,attributeFilter:['class']});
  document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('nav [data-s="mon"],#subnav [data-s="mon"]'))swClose()},true)}
 if($('zswopen'))$('zswopen').onclick=()=>{swOpen();scrollTo(0,0)}}
