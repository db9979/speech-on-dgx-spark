// Eigene Stimmen gestalten (stimmdesign.py, plan eigene-stimme, Dominik 2026-11-11): under Ich → Gespräch → Antwort the
// row „Eigene Stimme“ opens a box below it with three tabs: the 20 fixed voices (▶ hears the kept sample, a click
// chooses it), „Eigene gestalten“ (fields of the panel's lists, own words, ▶ Probe, Neu würfeln, Übernehmen) and
// „Meine Stimmen“ (▶, choose, delete). The sample is made on the Spark; this page only sends the fields and plays
// what comes back. Names and words go in as text only.
const SD={d:null,tab:'fertig',filt:'',felder:{geschlecht:'w',alter:'mittel',tonlage:'mittel',tempo:'normal',art:['warm']},
  worte:'',name:'',probe:null,busy:false,audio:null,weg:''};
const sdG=g=>({w:t('Frau','Woman'),m:t('Mann','Man'),n:t('Neutral','Neutral')}[g]||'');
function sdPlay(url){try{if(SD.audio){SD.audio.pause()}SD.audio=new Audio(url);SD.audio.play().catch(()=>{})}catch{}}
async function sdHear(name){try{const r=await api('/api/stimmdesign/hoeren/'+encodeURIComponent(name));sdPlay(URL.createObjectURL(await r.blob()))}
  catch(e){sdMsg(e.message)}}
function sdMsg(s){const m=$('sdmsg');if(m)m.textContent=s||''}
async function sdLoad(){try{SD.d=await (await api('/api/stimmdesign')).json()}catch(e){SD.d=null;sdMsg(e.message)}sdDraw()}
async function sdChoose(id){try{await api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({voice:id})});
  S.voice=id;if(SD.d)SD.d.wahl=id;const s=document.querySelector('#setform select[id$="_voice"]');if(s&&id&&!/^(sd|eigen)-/.test(id))s.value=id;sdDraw();
  sdMsg(t('Übernommen: so antwortet der Spark ab jetzt überall.','Taken: the Spark answers like this everywhere from now on.'))}catch(e){sdMsg(e.message)}}
const sdLabel=id=>{const d=SD.d;if(!d||!id)return '';const f=d.fertig.find(x=>x.id===id);if(f)return t(f.de,f.en);const o=d.eigene.find(x=>x.id===id);return o?o.name:''};
function sdTabs(){const d=SD.d;return ldSeg([['fertig',t('Fertige Stimmen','Ready voices'),d.fertig.length],['eigene',t('Eigene gestalten','Design your own')],
  ['meine',t('Meine Stimmen','My voices'),d.eigene.length+'/'+d.max]],SD.tab,k=>{SD.tab=k;sdDraw()},t('Stimme','Voice'))}
function sdCard(x){const on=SD.d.wahl===x.id;const b=el('button','b sdplay');b.type='button';b.appendChild(icSvg('play',14));b.setAttribute('aria-label',t('Anhören','Listen'));
  b.disabled=!x.da;b.onclick=e=>{e.stopPropagation();sdHear(x.id)};
  return ldRow({on,lead:b,title:t(x.de,x.en),sub:x.da?sdG(x.g)+' · '+x.alter:t('wird erstellt …','being made …'),right:[on?ldSt('ok',t('gewählt','chosen')):null],
    act:x.da?()=>sdChoose(x.id):null})}
function sdFertig(box){const d=SD.d;box.appendChild(ldSeg([['',t('Alle','All')],['w',t('Frau','Woman')],['m',t('Mann','Man')],['n',t('Neutral','Neutral')]],SD.filt,k=>{SD.filt=k;sdDraw()},t('Filter','Filter')));
  const g=el('div','sdgrid');d.fertig.filter(x=>!SD.filt||x.g===SD.filt).forEach(x=>g.appendChild(sdCard(x)));box.appendChild(g);
  const n=d.fertig.filter(x=>x.da).length;if(n<d.fertig.length)box.appendChild(el('div','fh',n+t(' von ',' of ')+d.fertig.length+t(' Stimmen sind fertig; der Spark macht die übrigen in ruhigen Minuten.',' voices are ready; the Spark makes the others in quiet minutes.')))}
function sdSeg(k,multi){const d=SD.d,f=SD.felder;const items=d.felder[k].map(y=>[y[0],t(y[1],y[2])]);
  if(!multi)return ldSeg(items,f[k],v=>{f[k]=v;sdDraw()},k);
  const s=el('div','segc ld-seg sdart');items.forEach(([v,l])=>{const b=el('button',f.art.includes(v)?'on':'',l);b.type='button';b.setAttribute('aria-pressed',String(f.art.includes(v)));
    b.onclick=()=>{f.art=f.art.includes(v)?f.art.filter(x=>x!==v):[...f.art,v].slice(-2);if(!f.art.length)f.art=[v];sdDraw()};s.appendChild(b)});return s}
function sdLine(l,ctl){const r=el('div','setrow');const a=el('div','lbl');a.appendChild(el('b','',l));r.append(a,ctl);return r}
async function sdProbe(again){if(SD.busy)return;SD.busy=true;sdDraw();let tries=0;
  for(;;){try{sdMsg(t('Probe wird gemacht …','Making a sample …'));
      const r=await api('/api/stimmdesign/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({felder:SD.felder,worte:SD.worte})});
      SD.probe=URL.createObjectURL(await r.blob());sdPlay(SD.probe);sdMsg('');if(SD.d)SD.d.proben++;break}
    catch(e){if(e.status===503&&/geladen/.test(e.detail||'')&&tries++<8){sdMsg(t('VoiceDesign wird geladen … (bis zu einer Minute)','VoiceDesign is loading … (up to a minute)'));await new Promise(z=>setTimeout(z,15000));continue}
      sdMsg(e.message);break}}
  SD.busy=false;sdDraw()}
async function sdTake(){try{await api('/api/stimmdesign/eigene',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:SD.name.trim()})});
  SD.probe=null;SD.name='';SD.tab='meine';await sdLoad();sdMsg(t('Gespeichert und gewählt.','Saved and chosen.'))}catch(e){sdMsg(e.message)}}
function sdEigene(box){const d=SD.d;
  if(!d.design){box.appendChild(el('div','fh',t('Dafür braucht es VoiceDesign auf dem Spark (Einstellungen → Sprachausgabe).','This needs VoiceDesign on the Spark (Einstellungen → Sprachausgabe).')));return}
  box.append(sdLine(t('Geschlecht','Gender'),sdSeg('geschlecht')),sdLine(t('Alter','Age'),sdSeg('alter')),sdLine(t('Tonlage','Pitch'),sdSeg('tonlage')),
    sdLine(t('Tempo','Pace'),sdSeg('tempo')),sdLine(t('Art (bis 2)','Kind (up to 2)'),sdSeg('art',true)));
  const w=el('textarea','wide');w.rows=2;w.maxLength=120;w.value=SD.worte;w.placeholder=t('z. B. klingt leicht amüsiert','e.g. sounds slightly amused');
  w.oninput=()=>{SD.worte=w.value.replace(/[^A-Za-zÄÖÜäöüß ,.]/g,'')};box.appendChild(sdLine(t('Eigene Worte (optional)','Own words (optional)'),w));
  const bar=el('div','row sdbar');const p=el('button','b',SD.probe?t('Neu würfeln','Roll again'):t('▶ Probe','▶ Sample'));p.type='button';p.disabled=SD.busy;p.onclick=()=>sdProbe(!!SD.probe);bar.appendChild(p);
  if(SD.probe){const h=el('button','b',t('▶ Nochmal hören','▶ Hear again'));h.type='button';h.onclick=()=>sdPlay(SD.probe);bar.appendChild(h)}
  bar.appendChild(el('span','mut',d.frei?t('ohne Tageslimit','no daily limit'):t('Probe ','Sample ')+d.proben+t(' von ',' of ')+d.proben_max+t(' heute',' today')));box.appendChild(bar);
  if(SD.probe){const n=el('input','wide');n.maxLength=30;n.value=SD.name;n.placeholder=t('Name, z. B. Abendstimme','Name, e.g. Evening voice');n.oninput=()=>{SD.name=n.value};
    const k=el('button','b p',t('Übernehmen','Take it'));k.type='button';k.disabled=d.eigene.length>=d.max;k.onclick=sdTake;
    const r=el('div','row sdbar');r.append(n,k);box.appendChild(r);
    if(d.eigene.length>=d.max)box.appendChild(el('div','fh',t('Schon drei eigene Stimmen: lösche zuerst eine unter „Meine Stimmen“.','Already three own voices: delete one under "My voices" first.')))}}
function sdMeine(box){const d=SD.d;if(!d.eigene.length){box.appendChild(ldEmpty('mic',t('Noch keine eigene Stimme. Unter „Eigene gestalten“ machst du eine.','No own voice yet. Make one under "Design your own".')));return}
  d.eigene.forEach(x=>{const on=d.wahl===x.id;const play=el('button','b sdplay');play.type='button';play.appendChild(icSvg('play',14));play.setAttribute('aria-label',t('Anhören','Listen'));play.onclick=e=>{e.stopPropagation();sdHear(x.id)};
    const del=el('button','b',SD.weg===x.id?t('Wirklich löschen?','Really delete?'):t('Löschen','Delete'));del.type='button';
    del.onclick=async e=>{e.stopPropagation();if(SD.weg!==x.id){SD.weg=x.id;sdDraw();return}SD.weg='';
      try{await api('/api/stimmdesign/eigene/'+encodeURIComponent(x.id),{method:'DELETE'});if(S.voice===x.id)S.voice='';await sdLoad();sdMsg(t('Gelöscht.','Deleted.'))}catch(er){sdMsg(er.message)}};
    box.appendChild(ldRow({on,lead:play,title:x.name,sub:(x.felder&&x.felder.art||[]).join(', '),right:[on?ldSt('ok',t('gewählt','chosen')):null,del],act:()=>sdChoose(x.id)}))})}
function sdDraw(){const box=$('sdbox');if(!box)return;box.textContent='';const d=SD.d;
  if(!d){box.appendChild(el('div','fh',t('Lädt …','Loading …')));box.appendChild(el('div','mut','')).id='sdmsg';return}
  const w=sdLabel(d.wahl);box.appendChild(el('div','fh',w?t('Jetzt: ','Now: ')+w:t('Jetzt: eine klassische Stimme (oben).','Now: a classic voice (above).')));
  if(d.klon&&d.klon!=='ready')box.appendChild(el('div','fh',t('Die Sprachausgabe für eigene Stimmen startet noch; bis dahin spricht die Standardstimme.','The speech output for own voices is still starting; until then the standard voice speaks.')));
  box.appendChild(sdTabs());const p=el('div','sdpane');box.appendChild(p);
  ({fertig:sdFertig,eigene:sdEigene,meine:sdMeine}[SD.tab])(p);
  const m=el('div','mut');m.id='sdmsg';box.appendChild(m)}
// called by renderSet (me.js) after it drew the rows: the row's button opens and closes the box below it
window.sdRow=root=>{const b=root.querySelector('button[id$="_sd"]');if(!b)return;const row=b.closest('.setrow');
  if(row.classList.contains('locked')){b.disabled=true;return}   // switched off by the admin: the row only says so
  b.onclick=()=>{let box=$('sdbox');if(box){box.remove();b.textContent=t('Stimmen …','Voices …');return}
    box=el('div','sdbox');box.id='sdbox';row.after(box);b.textContent=t('Schließen','Close');sdDraw();sdLoad()}};
