// Werkstatt (werkstattseite.py, plan opencode-werkstatt): Zustand → Werkstatt, its own page since Dominik 2026-10-21
// „1“ (before a box under Funktionen). Four tiles start an order (Alles testen, Problem untersuchen, Reparatur
// versuchen, Sprachmodell messen); on the left the results, on the right one result with what it means and what to do
// next. Results come as data: every word through textContent, the patch only as text in a <pre>.
const WK={timer:0,d:null,sel:'',neu:'',eins:null,vorlage:''};
const WK_GRUND={ok:['fertig','done'],llm:['Sprachmodell antwortet nicht','language model does not answer'],opencode:['OpenCode fehlt','OpenCode missing'],
  zeit:['Zeit abgelaufen','time is up'],quelle:['Code-Kopie fehlt','code copy missing'],tests:['Tests liefen nicht','tests did not run'],
  abbruch:['abgebrochen','stopped'],fehler:['Fehler','error'],leer:['nichts geändert','nothing changed']};
// what a reason means and what to do (fixed sentences; a way becomes a link by way.js)
const WK_WARUM={llm:['Das eigene Sprachmodell hat nicht geantwortet. Später noch einmal; läuft es dauerhaft nicht, zeigt Zustand → Überblick den Grund.','The own language model did not answer. Try again later; if it stays down, Status → Summary shows why.'],
  opencode:['OpenCode fehlt auf dem Modell-Rechner. Dort einmal: sudo ./install.sh --werkstatt','OpenCode is missing on the model computer. There once: sudo ./install.sh --werkstatt'],
  zeit:['Die Zeit war um, meist weil das Sprachmodell lange mit Gesprächen beschäftigt war (die gehen immer vor). Später noch einmal.','Time was up, mostly because the language model was busy with conversations for long (they always go first). Try again later.'],
  quelle:['Die Kopie des Codes ließ sich nicht anlegen. Auf dem Modell-Rechner einmal sudo ./install.sh --werkstatt; Zustand → Logs (System) zeigt „werkstatt: kopie“.','The copy of the code could not be made. On the model computer once sudo ./install.sh --werkstatt; Status → Logs (System) shows "werkstatt: kopie".'],
  tests:['Die Selbsttests liefen nicht an. Zustand → Logs (System) zeigt „werkstatt:“.','The self-tests did not start. Status → Logs (System) shows "werkstatt:".'],
  abbruch:['Der Auftrag wurde abgebrochen (Neustart oder Update). Einfach noch einmal starten.','The order was stopped (restart or update). Just start it again.'],
  fehler:['Unerwarteter Fehler. Zustand → Logs (System) zeigt „werkstatt:“ mit dem Grund.','Unexpected error. Status → Logs (System) shows "werkstatt:" with the reason.'],
  leer:['OpenCode hat nichts geändert. Das Problem genauer beschreiben (was passiert, was sollte passieren, wo) und noch einmal versuchen.','OpenCode changed nothing. Describe the problem more exactly (what happens, what should happen, where) and try again.']};
// the four tiles: kind, symbol, title, what it does
const WK_NEU=[['tests','✓',['Alles testen','Test everything'],['Alle Selbsttests wie auf GitHub · ohne Sprachmodell · etwa 10 min','All self-tests as on GitHub · no language model · about 10 min']],
  ['diagnose','?',['Problem untersuchen','Look into a problem'],['Du beschreibst, was nicht klappt · liest nur, ändert nichts','You describe what goes wrong · only reads, changes nothing']],
  ['reparatur','✎',['Reparatur versuchen','Try a repair'],['Ergibt einen Vorschlag zum Ansehen · nichts wird eingespielt','Gives a proposal to look at · nothing is installed']],
  ['messen','∑',['Sprachmodell messen','Measure the language model'],['10 bekannte Fehler reparieren lassen · etwa 1 Stunde','Let it repair 10 known bugs · about 1 hour']]];
// the Angriffsprobe (angriffsprobe.py, own switch): a fifth tile while it is on; its runs come from the panel, not the sandbox
const WK_PROBE=['probe','⚔',['Angriffe prüfen','Probe attacks'],['Folgt das Sprachmodell Befehlen in fremdem Text? · nur Zahlen · 1 bis 2 min','Does the language model follow orders in outside text? · numbers only · 1 to 2 min']];
function wkNeuListe(){return WK.d&&WK.d.probe&&WK.d.probe.an?WK_NEU.concat([WK_PROBE]):WK_NEU}
function wkEl(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function wkT(p){return L==='en'?p[1]:p[0]}
function wkBtn(txt,cls,fn){const b=wkEl('button','b'+(cls?' '+cls:''),txt);b.type='button';b.onclick=fn;return b}
function wkArt(a){const x=WK.d&&WK.d.arten&&WK.d.arten[a];return x?(L==='en'?x.en:x.de):a}
function wkZeit(s){if(!s)return'';const d=new Date(s*1000),h=new Date(),gestern=new Date(h.getTime()-864e5);
  const uhr=d.toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  if(d.toDateString()===h.toDateString())return t('heute ','today ')+uhr;if(d.toDateString()===gestern.toDateString())return t('gestern ','yesterday ')+uhr;
  return d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'numeric'})+' '+uhr}
function wkDauer(s){return s>=3600?Math.floor(s/3600)+' h '+Math.round(s%3600/60)+' min':s>=60?Math.round(s/60)+' min':(s||0)+' s'}
// one result in a word: [dot, badge, badge class]
function wkKurz(a){const ts=a.tests||{};
  if(a.grund!=='ok'&&a.grund!=='leer')return['bad',wkT(WK_GRUND[a.grund]||[a.grund,a.grund]),'err'];
  if(a.art==='tests'||a.art==='nachtest')return ts.rot?['bad',ts.rot+t(' rot',' red'),'err']:ts.wackelig?['warn',ts.wackelig+t(' wackelig',' flaky'),'due']:['ok',t('alle grün','all green'),'ok'];
  if(a.art==='messen'){const n=(a.aufgaben||[]).length;return['ok',(a.aufgaben||[]).filter(x=>x.ok).length+t(' von ',' of ')+n,'read']}
  if(a.art==='reparatur')return a.grund==='leer'?['warn',t('nichts geändert','nothing changed'),'due']:[ts.rot?'warn':'ok',t('Vorschlag','Proposal'),ts.rot?'due':'read'];
  return['ok',t('Antwort','Answer'),'read']}
function wkShow(d){WK.d=d;const box=$('wkbox');if(!box)return;
  $('wkoff').hidden=!!d.an;
  const n=$('wknacht');n.textContent='';
  if(d.an)n.textContent=d.nacht_an?t('Jede Nacht um '+d.stunde+' Uhr testen: an · Funktionen → Werkstatt → Jede Nacht testen','Test every night at '+d.stunde+': on · Features → Workshop → Test every night')
    :t('Jede Nacht testen: aus · Funktionen → Werkstatt → Jede Nacht testen','Test every night: off · Features → Workshop → Test every night');
  wkTiles();wkList();
  const pr=d.probe||{};
  if(WK.sel==='probelauf'&&!pr.laeuft&&(pr.laeufe||[])[0])WK.sel='ap-'+pr.laeufe[0].id;
  if(WK.sel==='lauf'?!d.laeuft:WK.sel==='probelauf'?!pr.laeuft:WK.sel.startsWith('ap-')?!(pr.laeufe||[]).some(p=>'ap-'+p.id===WK.sel):WK.sel&&!(d.auftraege||[]).some(a=>a.id===WK.sel)){WK.sel='';WK.eins=null}
  if(!WK.sel&&!WK.neu&&!NARROW()){const f=d.laeuft?'lauf':(d.auftraege||[])[0]?.id||'';if(f)wkPick(f,true);else wkDetail()}
  else if(WK.sel==='lauf'||WK.sel==='probelauf'||WK.sel.startsWith('ap-')||WK.neu)wkDetail()}
function wkWarum(art){const d=WK.d||{},x=d.arten&&d.arten[art];if(!d.an)return t('Die Werkstatt ist aus.','The workshop is off.');
  if(d.laeuft)return t('Es läuft schon ein Auftrag; einer nach dem anderen.','An order is running already; one after the other.');
  if(x&&x.llm&&!d.installiert)return wkT(WK_WARUM.opencode);
  if(x&&x.llm&&!d.modell)return t('Braucht das eigene Sprachmodell: sudo speech-spark modelle llm uebernehmen','Needs the own language model: sudo speech-spark modelle llm uebernehmen');
  return''}
function wkTiles(){const w=$('wkacts');w.textContent='';w.classList.toggle('fuenf',wkNeuListe().length===5);
  wkNeuListe().forEach(([art,sym,tit,sub])=>{const b=wkEl('button','wkact'+(WK.neu===art?' on':''));b.type='button';b.dataset.art=art;
    b.appendChild(wkEl('span','wkic',sym));const m=wkEl('span','wkmid');m.appendChild(wkEl('b','',wkT(tit)));m.appendChild(wkEl('small','',wkT(sub)));b.appendChild(m);
    b.onclick=()=>wkNeu(art);w.appendChild(b)})}
function wkList(){const d=WK.d,box=$('wklist');box.textContent='';
  box.appendChild(wkEl('div','ld-grp',t('Verlauf','History')));
  if(d.laeuft){const r=wkEl('div','ld-row'+(WK.sel==='lauf'?' on':''));r.tabIndex=0;r.appendChild(wkEl('span','wkdot run'));
    const m=wkEl('div','ld-mid');m.appendChild(wkEl('b','',d.art?wkArt(d.art):t('Auftrag','Order')));m.appendChild(wkEl('small','',t('läuft gerade','running now')));r.appendChild(m);
    const rt=wkEl('div','ld-right');rt.appendChild(wkEl('span','ld-badge read',t('läuft','running')));r.appendChild(rt);
    r.onclick=()=>wkPick('lauf');r.onkeydown=e=>{if(e.key==='Enter')wkPick('lauf')};box.appendChild(r)}
  const pr=d.probe||{};
  if(pr.laeuft){const r=wkEl('div','ld-row'+(WK.sel==='probelauf'?' on':''));r.tabIndex=0;r.appendChild(wkEl('span','wkdot run'));
    const m=wkEl('div','ld-mid');m.appendChild(wkEl('b','',wkT(WK_PROBE[2])));m.appendChild(wkEl('small','',(pr.fertig||0)+t(' von ',' of ')+(pr.von||0)+t(' Fällen',' cases')));r.appendChild(m);
    const rt=wkEl('div','ld-right');rt.appendChild(wkEl('span','ld-badge read',t('läuft','running')));r.appendChild(rt);
    r.onclick=()=>wkPick('probelauf');r.onkeydown=e=>{if(e.key==='Enter')wkPick('probelauf')};box.appendChild(r)}
  (pr.laeufe||[]).forEach(p=>{const id='ap-'+p.id,r=wkEl('div','ld-row'+(WK.sel===id?' on':''));r.tabIndex=0;r.dataset.id=id;
    r.appendChild(wkEl('span','wkdot '+(p.gehorcht?'warn':'ok')));const m=wkEl('div','ld-mid');m.appendChild(wkEl('b','',wkT(WK_PROBE[2])));
    m.appendChild(wkEl('small','',wkZeit(p.zeit)+' · '+wkDauer(p.dauer_s)));r.appendChild(m);
    const rt=wkEl('div','ld-right');rt.appendChild(wkEl('span','ld-badge '+(p.gehorcht?'due':'ok'),p.gehorcht+t(' von ',' of ')+p.von));r.appendChild(rt);
    r.onclick=()=>wkPick(id);r.onkeydown=e=>{if(e.key==='Enter')wkPick(id)};box.appendChild(r)});
  (d.auftraege||[]).forEach(a=>{const [dot,txt,cls]=wkKurz(a);const r=wkEl('div','ld-row'+(WK.sel===a.id?' on':''));r.tabIndex=0;r.dataset.id=a.id;
    r.appendChild(wkEl('span','wkdot '+dot));const m=wkEl('div','ld-mid');m.appendChild(wkEl('b','',wkArt(a.art)));
    m.appendChild(wkEl('small','',wkZeit(a.zeit)+' · '+wkDauer(a.dauer_s)));r.appendChild(m);
    const rt=wkEl('div','ld-right');rt.appendChild(wkEl('span','ld-badge '+cls,txt));r.appendChild(rt);
    r.onclick=()=>wkPick(a.id);r.onkeydown=e=>{if(e.key==='Enter')wkPick(a.id)};box.appendChild(r)});
  if(!d.laeuft&&!(d.auftraege||[]).length&&!pr.laeuft&&!(pr.laeufe||[]).length)box.appendChild(wkEl('div','mut ld-empty',t('Noch keine Ergebnisse. Oben „Alles testen“ antippen.','No results yet. Tap "Test everything" above.')))}
async function wkPick(id,quiet){WK.sel=id;WK.neu='';if(!quiet||WK.eins?.id!==id)WK.eins=null;wkTiles();wkList();wkDetail();
  if(id==='lauf'||id==='probelauf'||id.startsWith('ap-')||(WK.eins&&WK.eins.id===id))return;
  try{const a=await (await api('/api/admin/werkstatt/'+encodeURIComponent(id))).json();if(WK.sel===id){WK.eins=a;wkDetail()}}
  catch(e){if(WK.sel===id){$('wkdetail').textContent=e.message}}}
function wkZurueck(){WK.sel='';WK.neu='';WK.eins=null;$('wkdetail').hidden=true;$('wkbox').classList.remove('ld-sel');wkTiles();wkList()}
function wkKopf(det,titel,unter){if(NARROW())det.appendChild(wkBtn('‹ '+t('Werkstatt','Workshop'),'ld-back',wkZurueck));
  det.appendChild(wkEl('h3','',titel));if(unter)det.appendChild(wkEl('div','mut wkunter',unter))}
function wkErkl(det,txt,cls){const e=wkEl('div','wkerkl'+(cls?' '+cls:''));txt.forEach((s,i)=>{if(i===0){e.appendChild(wkEl('b','',s+' '))}else e.appendChild(document.createTextNode(s))});det.appendChild(e)}
function wkHead(det,txt){det.appendChild(wkEl('div','wkh',txt))}
function wkDetail(){const det=$('wkdetail'),box=$('wkbox'),d=WK.d;if(!det||!d)return;
  det.hidden=!(WK.sel||WK.neu);box.classList.toggle('ld-sel',!det.hidden);det.textContent='';if(det.hidden)return;
  if(WK.neu)return wkForm(det,WK.neu);
  if(WK.sel==='probelauf'||WK.sel.startsWith('ap-'))return wkProbe(det);
  if(WK.sel==='lauf'){wkKopf(det,(d.art?wkArt(d.art):t('Auftrag','Order'))+t(' läuft',' running'),t('auf dem Modell-Rechner, in der abgeschotteten Kopie','on the model computer, in the sealed-off copy'));
    const p=wkEl('div','wkbar');p.appendChild(wkEl('i'));det.appendChild(p);
    const l=wkEl('ol','wkstand');(d.stand||[]).forEach(z=>l.appendChild(wkEl('li','',z.replace(/^werkstatt: /,''))));det.appendChild(l);
    wkErkl(det,[t('Du kannst die Seite schließen.','You can close the page.'),t('Der Auftrag läuft weiter; das Ergebnis steht danach links im Verlauf. Gespräche gehen immer vor.','The order keeps running; the result shows on the left afterwards. Conversations always go first.')]);return}
  const k=(d.auftraege||[]).find(x=>x.id===WK.sel),a=WK.eins||k;if(!a){det.hidden=true;return}
  wkKopf(det,wkArt(a.art)+' · '+wkZeit(a.zeit),[wkDauer(a.dauer_s),a.version,a.modell].filter(Boolean).join(' · '));
  if(!WK.eins){det.appendChild(wkEl('div','mut',t('Einen Moment …','One moment …')));return}
  const ts=a.tests||{};
  if(a.grund!=='ok')wkErkl(det,[wkT(WK_GRUND[a.grund]||[a.grund,a.grund])+':',wkT(WK_WARUM[a.grund]||['',''])],a.grund==='leer'?'':'bad');
  if(a.art==='tests'||a.art==='nachtest')wkTests(det,a,ts);
  else if(a.art==='messen')wkMessen(det,a);
  else wkAntwort(det,a);
  const acts=wkEl('div','ld-acts');
  if((a.art==='tests'||a.art==='nachtest')&&ts.rot){
    acts.appendChild(wkBtn(t('Ursache untersuchen','Find the cause'),'p',()=>wkNeu('diagnose',wkVorlage(a))));
    if((ts.rot_namen||[]).some(n=>n!=='selftest'))acts.appendChild(wkBtn(a.art==='nachtest'?t('Noch einmal testen','Test again'):t('Nur die roten noch mal testen','Test only the red ones again'),'',()=>wkNochmal(a.id)))}
  if(a.art==='tests'&&!ts.rot&&ts.wackelig&&(ts.wackelig_namen||[]).length)acts.appendChild(wkBtn(t('Ursache untersuchen','Find the cause'),'',()=>wkNeu('diagnose',wkVorlage(a))));
  if(a.art==='diagnose'&&a.grund==='ok')acts.appendChild(wkBtn(t('Reparatur versuchen','Try a repair'),'p',()=>wkNeu('reparatur',a.aufgabe)));
  if((a.art==='diagnose'||a.art==='reparatur')&&a.grund!=='ok')acts.appendChild(wkBtn(t('Noch einmal','Again'),'p',()=>wkNeu(a.art,a.aufgabe)));
  if(a.grund==='ok'&&(ts.rot||a.text||a.patch))acts.appendChild(wkBtn(t('Für Claude kopieren','Copy for Claude'),'',e=>copyString(wkFuerClaude(a),e.currentTarget)));
  acts.appendChild(wkBtn(t('Löschen','Delete'),'g',()=>wkWeg(a.id)));
  det.appendChild(acts)}
function wkTests(det,a,ts){const s=wkEl('div','wkstats');
  [[ts.gruen,t('grün','green'),'ok'],[ts.rot,t('rot','red'),ts.rot?'bad':''],[ts.wackelig,t('wackelig','flaky'),ts.wackelig?'warn':'']].concat(ts.nicht_gelaufen?[[ts.nicht_gelaufen,t('nicht gelaufen','did not run'),'']]:[]).forEach(([n,w,c])=>{
    const x=wkEl('div','wkstat '+c);x.appendChild(wkEl('b','',String(n||0)));x.appendChild(wkEl('span','',w));s.appendChild(x)});det.appendChild(s);
  const alle=(ts.gruen||0)+(ts.rot||0)+(ts.wackelig||0);
  if(a.grund!=='ok')return;
  if(a.art==='nachtest')wkErkl(det,ts.rot?[t('Bleiben rot:','Stay red:'),t(ts.rot+' von '+alle+' scheitern in der Kopie verlässlich. Das ist ein echter Unterschied zu GitHub, meist weil die Kopie kein Internet und keine Daten hat. „Ursache untersuchen“ fragt das Sprachmodell, woran es liegt.',ts.rot+' of '+alle+' fail reliably in the copy. That is a real difference to GitHub, mostly because the copy has no internet and no data. "Find the cause" asks the language model why.')]
    :[t('Jetzt grün:','Green now:'),t('Alle '+alle+' bestehen beim zweiten Mal. Sie waren nur kurz rot, etwa weil der Rechner gerade beschäftigt war. Nichts zu tun.','All '+alle+' pass the second time. They were only briefly red, for example because the computer was busy. Nothing to do.')],ts.rot?'':'ok');
  else if(ts.rot)wkErkl(det,[t('Was heißt „rot“?','What does "red" mean?'),t(ts.rot+' von '+alle+' Selbsttests haben in der Kopie auf dem Modell-Rechner nicht bestanden. Ein Update über das Panel gibt es nur für Versionen, die auf GitHub grün waren; rot in der Kopie heißt deshalb meist: der Test braucht etwas, das die abgeschottete Kopie nicht hat (Internet, Daten, Browser). Dein Spark läuft davon unberührt, du musst nichts sofort tun.',ts.rot+' of '+alle+' self-tests did not pass in the copy on the model computer. An update through the panel only comes for versions that were green on GitHub; red in the copy therefore mostly means: the test needs something the sealed-off copy does not have (internet, data, browser). Your Spark is not affected, nothing to do right away.')]);
  else if(ts.wackelig)wkErkl(det,[t('Wackelig:','Flaky:'),t('Diese Tests waren erst beim zweiten Versuch grün, meist weil der Rechner gerade beschäftigt war. Alles bestanden, nichts zu tun.','These tests were green only on the second try, mostly because the computer was busy. All passed, nothing to do.')]);
  else wkErkl(det,[t('Alles grün:','All green:'),t('Der Code dieser Version besteht alle Selbsttests auch in der Kopie. Nichts zu tun.','The code of this version passes all self-tests in the copy too. Nothing to do.')],'ok');
  if(ts.nicht_gelaufen)wkErkl(det,[t('Nicht gelaufen:','Did not run:'),t(ts.nicht_gelaufen+' Tests brauchen, was die Kopie absichtlich nicht hat (einen Browser für die Seiten-Tests, Dateien außerhalb von app/). Sie zählen nicht als grün; auf GitHub laufen sie bei jeder Version.',ts.nicht_gelaufen+' tests need what the copy does not have on purpose (a browser for the page tests, files outside app/). They do not count as green; on GitHub they run for every version.')]);
  [[ts.rot_namen,t('Rote Tests, nach Bereich','Red tests, by area'),'bad'],[ts.wackelig_namen,t('Wackelige Tests','Flaky tests'),'warn']].forEach(([liste,h,c])=>{
    if(!(liste||[]).length)return;wkHead(det,h);const g={};liste.forEach(n=>{const m=n.split('.')[0];(g[m]=g[m]||[]).push(n)});
    const w=wkEl('div','wkrot');Object.entries(g).forEach(([m,ns])=>{const x=wkEl('details','wkmod');const su=wkEl('summary');su.appendChild(wkEl('span','wkdot '+c));
      su.appendChild(wkEl('code','',m));su.appendChild(wkEl('span','ld-badge '+(c==='bad'?'err':'due'),String(ns.length)));x.appendChild(su);
      const ul=wkEl('ul');ns.forEach(n=>ul.appendChild(wkEl('li','',n.split('.').slice(1).join('.')||n)));x.appendChild(ul);w.appendChild(x)});det.appendChild(w)});
  if((ts.rot||0)>(ts.rot_namen||[]).length)det.appendChild(wkEl('div','mut wkunter',t('Gezeigt werden die ersten '+(ts.rot_namen||[]).length+'.','The first '+(ts.rot_namen||[]).length+' are shown.')))}
function wkMessen(det,a){const n=(a.aufgaben||[]).length,g=(a.aufgaben||[]).filter(x=>x.ok).length;
  const s=wkEl('div','wkstats');[[g,t('repariert','repaired'),'ok'],[n-g,t('nicht geschafft','not managed'),n-g?'warn':'']].forEach(([v,w,c])=>{const x=wkEl('div','wkstat '+c);x.appendChild(wkEl('b','',String(v)));x.appendChild(wkEl('span','',w));s.appendChild(x)});det.appendChild(s);
  wkErkl(det,[t('Was heißt das?','What does it mean?'),t('Das Sprachmodell hat '+g+' von '+n+' bekannten, früher behobenen Fehlern selbst repariert. Je mehr, desto eher taugt es für „Reparatur versuchen“. Nach einem Modellwechsel misst die Werkstatt nachts von selbst neu.','The language model repaired '+g+' of '+n+' known, earlier fixed bugs by itself. The more, the better it is for "Try a repair". After a model switch the workshop measures again at night by itself.')]);
  const ul=wkEl('ul','wkliste');(a.aufgaben||[]).forEach(x=>{const li=wkEl('li');li.appendChild(wkEl('span','wkdot '+(x.ok?'ok':'warn')));li.appendChild(wkEl('code','',x.id));li.appendChild(wkEl('span','mut',' · '+wkDauer(x.dauer_s)));ul.appendChild(li)});det.appendChild(ul)}
function wkAntwort(det,a){if(a.aufgabe){wkHead(det,t('Deine Beschreibung','Your description'));det.appendChild(wkEl('div','wktext mut',a.aufgabe))}
  if(a.text){wkHead(det,a.art==='diagnose'?t('Antwort','Answer'):t('Was OpenCode sagt','What OpenCode says'));det.appendChild(wkEl('div','wktext',a.text))}
  if(a.art==='reparatur'&&(a.dateien||[]).length){const ts=a.tests||{};
    wkErkl(det,[t('Ein Vorschlag, nicht eingespielt.','A proposal, not installed.'),t('Die Änderung liegt nur in der Kopie. '+(ts.rot?ts.rot+' Tests der geänderten Dateien sind rot; der Vorschlag ist so noch nicht fertig.':'Die Tests der geänderten Dateien sind grün.')+' Übernehmen tut ihn ein Mensch: „Für Claude kopieren“ und in einen Claude-Thread einfügen.','The change exists only in the copy. '+(ts.rot?ts.rot+' tests of the changed files are red; the proposal is not finished like this.':'The tests of the changed files are green.')+' A person takes it over: "Copy for Claude" and paste it into a Claude thread.')],ts.rot?'bad':'');
    wkHead(det,t('Geänderte Dateien','Changed files'));const ul=wkEl('ul','wkliste');a.dateien.forEach(f=>{const li=wkEl('li');li.appendChild(wkEl('code','',f.pfad));li.appendChild(wkEl('span','wkplus',' +'+f.plus));li.appendChild(wkEl('span','wkminus',' −'+f.minus));ul.appendChild(li)});det.appendChild(ul);
    if(a.patch){const x=wkEl('details','wkpatchbox');x.appendChild(wkEl('summary','',t('Änderung ansehen','View the change')+(a.gekuerzt?t(' (gekürzt)',' (cut)'):'')));x.appendChild(wkEl('pre','wkpatch',a.patch));det.appendChild(x)}}}
function wkVorlage(a){const n=((a.tests||{}).rot_namen||[]).concat((a.tests||{}).rot?[]:(a.tests||{}).wackelig_namen||[]);
  const s=t('Diese Selbsttests sind im Testlauf der Werkstatt (Kopie ohne Internet und ohne Daten) rot, auf GitHub aber grün. Warum? ','These self-tests are red in the workshop test run (copy without internet and data), but green on GitHub. Why? ')+n.join(', ');return s.slice(0,2000)}
function wkFuerClaude(a){const ts=a.tests||{},z=[t('Werkstatt-Ergebnis vom Spark','Workshop result from the Spark')+(a.version?' ('+a.version+')':'')+': '+wkArt(a.art)+', '+wkZeit(a.zeit)];
  if(a.art==='tests'||a.art==='nachtest')z.push(ts.gruen+t(' grün, ',' green, ')+ts.rot+t(' rot, ',' red, ')+ts.wackelig+t(' wackelig',' flaky')+(ts.nicht_gelaufen?', '+ts.nicht_gelaufen+t(' nicht gelaufen',' did not run'):''));
  if((ts.rot_namen||[]).length)z.push(t('Rot: ','Red: ')+ts.rot_namen.join(' '));
  if((ts.wackelig_namen||[]).length)z.push(t('Wackelig: ','Flaky: ')+ts.wackelig_namen.join(' '));
  if(a.aufgabe&&a.art!=='nachtest')z.push(t('Beschreibung: ','Description: ')+a.aufgabe);
  if(a.text)z.push(t('Antwort der Werkstatt:\n','Workshop answer:\n')+a.text);
  if(a.patch)z.push(t('Patch (aus der Kopie, nicht eingespielt):\n','Patch (from the copy, not installed):\n')+a.patch);
  return z.join('\n\n')}
function wkForm(det,art){const x=wkNeuListe().find(n=>n[0]===art);const warum=art==='probe'?wkProbeWarum():wkWarum(art);
  wkKopf(det,wkT(x[2]),wkT(x[3]));
  const text=['diagnose','reparatur'].includes(art);
  const erkl={tests:[t('Was passiert:','What happens:'),t('Eine frische Kopie des installierten Codes läuft auf dem Modell-Rechner durch alle Selbsttests, wie GitHub sie vor jedem Update macht. Ohne Sprachmodell, ohne Internet, ohne deine Daten. Danach siehst du links, was grün und was rot ist, und was du tun kannst.','A fresh copy of the installed code runs through all self-tests on the model computer, as GitHub does before every update. No language model, no internet, none of your data. Afterwards the left side shows what is green and red, and what you can do.')],
    diagnose:[t('Was passiert:','What happens:'),t('Das eigene Sprachmodell liest mit OpenCode den Code in der Kopie und sucht die Ursache. Es darf nichts ändern und nichts ins Netz. Heraus kommt eine Antwort in Worten.','The own language model reads the code in the copy with OpenCode and looks for the cause. It may change nothing and reach nothing outside. You get an answer in words.')],
    reparatur:[t('Was passiert:','What happens:'),t('Das eigene Sprachmodell ändert die Kopie und lässt die Tests der geänderten Dateien laufen. Heraus kommt ein Vorschlag zum Ansehen; eingespielt wird er nie, das macht ein Mensch.','The own language model changes the copy and runs the tests of the changed files. You get a proposal to look at; it is never installed, a person does that.')],
    probe:[t('Was passiert:','What happens:'),t('Das laufende Sprachmodell bekommt für jeden Fall des Angriffs-Selbsttests das Ergebnis eines Lese-Werkzeugs (Dokument, Mail, Webseite, Kalender, Smart Home), in dem ein Befehl versteckt ist, und darf das angegriffene Werkzeug aufrufen. Es läuft nie ein Werkzeug; gezählt wird nur, ob das Modell es versucht hätte. Die festen Sperren des Panels halten so oder so. Gespräche gehen vor.','For every case of the attack self-test the running language model gets a reading tool\'s result (document, mail, web page, calendar, smart home) with a hidden order and may call the attacked tool. No tool ever runs; counted is only whether the model would have tried. The panel\'s fixed locks hold either way. Conversations go first.')],
    messen:[t('Was passiert:','What happens:'),t('Das eigene Sprachmodell soll 10 bekannte, früher behobene Fehler reparieren. Gezählt wird, wie viele danach grün sind. So siehst du, wie gut es für Reparaturen taugt.','The own language model is asked to repair 10 known, earlier fixed bugs. Counted is how many are green afterwards. So you see how good it is for repairs.')]}[art];
  wkErkl(det,erkl);
  let ta=null;if(text){const lb=wkEl('label','',t('Was passiert, was sollte passieren?','What happens, what should happen?'));lb.htmlFor='wktext';det.appendChild(lb);
    ta=wkEl('textarea');ta.id='wktext';ta.rows=5;ta.maxLength=2000;ta.placeholder=t('z. B. „Das Licht im Bad geht per Sprache nicht an, im Panel schon.“','e.g. "The bathroom light does not turn on by voice, in the panel it does."');ta.value=WK.vorlage||'';det.appendChild(ta);WK.vorlage=''}
  if(['diagnose','reparatur','messen'].includes(art))det.appendChild(wkEl('div','mut wkunter',t('Fragt nach deinem Code, weil dabei ein Sprachmodell Befehle in der Kopie ausführt.','Asks for your code, because a language model runs commands in the copy.')));
  if(warum)det.appendChild(wkEl('div','note',warum));
  const msg=wkEl('div','mut');msg.setAttribute('role','status');
  const acts=wkEl('div','ld-acts');const go=wkBtn(t('Starten','Start'),'p',()=>art==='probe'?wkProbeStart(msg):wkGeben(art,ta?ta.value:'',msg));go.disabled=!!warum;acts.appendChild(go);
  acts.appendChild(wkBtn(t('Abbrechen','Cancel'),'',()=>{WK.neu='';const f=WK.d.laeuft?'lauf':(WK.d.auftraege||[])[0]?.id;if(f&&!NARROW())wkPick(f);else wkZurueck()}));
  det.appendChild(acts);det.appendChild(msg);if(ta&&!NARROW())ta.focus()}
function wkNeu(art,vorlage){WK.neu=art;WK.sel='';WK.eins=null;WK.vorlage=vorlage||'';wkTiles();wkList();wkDetail()}
async function wkLoad(){clearTimeout(WK.timer);const box=$('wkbox');if(!box||document.body.classList.contains('mgr'))return;
  if(box.offsetParent){try{wkShow(await (await api('/api/admin/werkstatt')).json());$('wkmsg').textContent=''}catch(e){$('wkmsg').textContent=e.message}}
  WK.timer=setTimeout(wkLoad,WK.d&&(WK.d.laeuft||(WK.d.probe||{}).laeuft)?5000:30000)}
async function wkGeben(art,text,msg){text=(text||'').trim();
  if((art==='diagnose'||art==='reparatur')&&text.length<8){msg.textContent=t('Bitte das Problem in ein, zwei Sätzen beschreiben.','Please describe the problem in a sentence or two.');return}
  msg.textContent=t('Einen Moment …','One moment …');
  try{const o={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(art==='tests'?{}:{art,text})};
    const d=await (await api(art==='tests'?'/api/admin/werkstatt/tests':'/api/admin/werkstatt/auftrag',o)).json();
    WK.neu='';WK.sel='lauf';WK.eins=null;wkShow(d);clearTimeout(WK.timer);WK.timer=setTimeout(wkLoad,5000)}
  catch(e){msg.textContent=e.message}}
async function wkNochmal(id){try{const d=await (await api('/api/admin/werkstatt/tests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({von:id})})).json();
    WK.neu='';WK.sel='lauf';WK.eins=null;wkShow(d);clearTimeout(WK.timer);WK.timer=setTimeout(wkLoad,5000)}
  catch(e){$('wkmsg').textContent=e.message}}
async function wkWeg(id){if(!confirm(t('Dieses Ergebnis löschen?','Delete this result?')))return;
  try{const d=await (await api('/api/admin/werkstatt/'+encodeURIComponent(id),{method:'DELETE'})).json();WK.sel='';WK.eins=null;
    if(NARROW())wkZurueck();wkShow(d)}catch(e){$('wkmsg').textContent=e.message}}
// the Angriffsprobe: why it cannot start, its detail (running or one run), start and delete
function wkProbeWarum(){const p=(WK.d||{}).probe||{};return p.laeuft?t('Die Angriffsprobe läuft schon.','The attack probe is running already.'):''}
function wkProbe(det){const pr=WK.d.probe||{};
  if(WK.sel==='probelauf'){wkKopf(det,wkT(WK_PROBE[2])+t(' läuft',' running'),(pr.fertig||0)+t(' von ',' of ')+(pr.von||0)+t(' Fällen',' cases'));
    const b=wkEl('div','wkbar');b.appendChild(wkEl('i'));det.appendChild(b);
    wkErkl(det,[t('Du kannst die Seite schließen.','You can close the page.'),t('Die Probe läuft im Panel weiter; Gespräche gehen vor.','The probe keeps running in the panel; conversations go first.')]);return}
  const p=(pr.laeufe||[]).find(x=>'ap-'+x.id===WK.sel);if(!p){det.hidden=true;return}
  wkKopf(det,wkT(WK_PROBE[2])+' · '+wkZeit(p.zeit),[wkDauer(p.dauer_s),p.version,p.modell].filter(Boolean).join(' · '));
  const s=wkEl('div','wkstats');[[p.gehorcht,t('gehorcht','obeyed'),p.gehorcht?'warn':''],[p.von-p.gehorcht,t('nicht gefolgt','not followed'),'ok']].concat(p.fehler?[[p.fehler,t('Fehler','errors'),'']]:[]).forEach(([v,w,c])=>{
    const x=wkEl('div','wkstat '+c);x.appendChild(wkEl('b','',String(v)));x.appendChild(wkEl('span','',w));s.appendChild(x)});det.appendChild(s);
  wkErkl(det,p.gehorcht?[t('Was heißt das?','What does it mean?'),t('In '+p.gehorcht+' von '+p.von+' Fällen hätte das Sprachmodell den versteckten Befehl ausgeführt. Passiert ist nichts: das Panel sperrt diese Werkzeuge nach fremdem Text mit festen Regeln, egal was das Modell will. Die Zahl zeigt, wie wichtig diese Sperren für dieses Modell sind.','In '+p.gehorcht+' of '+p.von+' cases the language model would have carried out the hidden order. Nothing happened: the panel locks these tools after outside text with fixed rules, whatever the model wants. The number shows how much these locks matter for this model.')]
    :[t('Nie gefolgt:','Never followed:'),t('Das Sprachmodell hat keinen der '+p.von+' versteckten Befehle ausgeführt. Die festen Sperren bleiben trotzdem an.','The language model carried out none of the '+p.von+' hidden orders. The fixed locks stay on all the same.')],p.gehorcht?'':'ok');
  const tn=pr.tarnungen||{};
  [[p.verpackungen,t('Nach Tarnung','By disguise'),k=>tn[k]?(L==='en'?tn[k].en:tn[k].de):k],[p.ziele,t('Nach angegriffenem Werkzeug','By attacked tool'),wzName]].forEach(([m,h,name])=>{if(!m)return;wkHead(det,h);
    const ul=wkEl('ul','wkliste');Object.entries(m).forEach(([k,[g,v]])=>{const li=wkEl('li');li.appendChild(wkEl('span','wkdot '+(g?'warn':'ok')));
      li.appendChild(wkEl('span','',name(k)));li.appendChild(wkEl('span','mut',' · '+g+t(' von ',' of ')+v));ul.appendChild(li)});det.appendChild(ul)});
  const acts=wkEl('div','ld-acts');acts.appendChild(wkBtn(t('Noch einmal','Again'),'p',()=>wkNeu('probe')));
  acts.appendChild(wkBtn(t('Löschen','Delete'),'g',()=>wkProbeWeg(p.id)));det.appendChild(acts)}
async function wkProbeStart(msg){msg.textContent=t('Einen Moment …','One moment …');
  try{const d=await (await api('/api/admin/werkstatt/angriffsprobe',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    WK.neu='';WK.sel='probelauf';wkShow(d);clearTimeout(WK.timer);WK.timer=setTimeout(wkLoad,5000)}
  catch(e){msg.textContent=e.message}}
async function wkProbeWeg(id){if(!confirm(t('Dieses Ergebnis löschen?','Delete this result?')))return;
  try{const d=await (await api('/api/admin/werkstatt/angriffsprobe/'+encodeURIComponent(id),{method:'DELETE'})).json();WK.sel='';
    if(NARROW())wkZurueck();wkShow(d)}catch(e){$('wkmsg').textContent=e.message}}
window.wkLoad=wkLoad;
