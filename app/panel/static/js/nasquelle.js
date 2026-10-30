// "Ich → Speicher → Wofür → Wissensordner" (nasquelle.py, plan synology-bauplan.md S2): folders at a place that the
// Spark reads into Dokumente (only reading; nothing changes there). Per folder: what is read (groups; sub folders
// are left out under Ich → Dokumente → Ausgelassene Ordner, auslassen.js), numbers, state, "Jetzt abgleichen", "Entfernen". New folders: type or browse the path, preview, add.
// When the admin blocks the profile the folders stay visible and can be removed (own data). Server text is text (esc).
// An admin profile can mark a new folder "Für alle im Haushalt" (Haushaltsordner, S5): every profile finds it then.
let NQ=null;
const NQ_PATH={webdav:'/',smb:'',sftp:'/volume1/'};
const nqWhy=k=>t(...((NQ&&NQ.why_words||{})[k]||NAS_WHY[k]||NAS_WHY.other));
async function nqLoad(){NQ=null;try{const d=await (await api('/api/profile/nasquelle')).json();d.haus=d.haus||{may:false,sources:[],count:0,max:0};if(d.on||d.sources.length||d.haus.sources.length)NQ=d}catch{NQ=null}return NQ}
function nqGroups(pre,picked){return `<div class="nqgrp">${NQ.groups.map(g=>{const off=g.id==='bilder'&&!NQ.pictures;
  return `<label class="chk"><input type="checkbox" data-nqg="${esc(pre)}" value="${esc(g.id)}"${picked.includes(g.id)&&!off?' checked':''}${off?' disabled':''}> ${esc(t(g.name[0],g.name[1]))} <small class="mut">${esc(g.ends.join(' '))}</small></label>`}).join('')}
  ${NQ.pictures?'':`<div class="fh">${esc(t('Bilder und Scans braucht unter Funktionen „Bilder in Dokumenten“.','Pictures and scans need "Pictures in documents" under Features.'))}</div>`}</div>`}
function nqOut(out){const k=Object.keys(out||{}).filter(x=>out[x]);if(!k.length)return '';
  return `<details><summary>${esc(t('Ausgelassen','Left out'))}</summary>${k.map(x=>`<div class="mut">${esc(t(...(NQ.out_words[x]||[x,x])))}: ${esc(String(out[x]))}</div>`).join('')}</details>`}
function nqState(x){if(x.running)return ['warn',t('liest gerade','reading now')];if(x.fail)return [x.fail.kind==='offline'?'warn':'bad',nqWhy(x.fail.kind)];
  return x.last?['ok',t('aktuell','up to date')]:['',t('noch nicht gelesen','not read yet')]}
function nqOne(x){const [cls,word]=nqState(x),on=NQ.on&&(!x.haus||NQ.haus.may);
  return `<div class="use"><div class="use-h"><span><b>${esc(x.haus?t('Haushaltsordner (für alle)','Household folder (for everyone)'):t('Wissensordner','Knowledge folder'))}</b> <em class="pill ${cls}">${esc(word)}</em>
      <small>${esc(x.path)} · ${esc(t(`${x.docs} Dokumente`,`${x.docs} documents`))} · ${esc(t(`${x.seen} im Ordner`,`${x.seen} in the folder`))}${x.left?' · '+esc(t(`${x.left} warten`,`${x.left} waiting`)):''} · ${esc(t('zuletzt','last'))} ${esc(spWhen(x.last&&x.last.t))}</small></span></div>
    ${on?'':`<div class="fh">${esc(t('Vom Admin ausgeschaltet oder für dich gesperrt: der Ordner wird nicht mehr gelesen. Entfernen geht weiter.','Switched off or blocked for you by the admin: the folder is not read any more. Removing still works.'))}</div>`}
    ${nqOut(x.out)}
    ${on?`<div class="row" style="margin-top:6px"><button class="b" type="button" data-nqnow="${esc(x.id)}">${esc(t('Jetzt abgleichen','Read now'))}</button></div>
    <details><summary>${esc(t('Was gelesen wird','What is read'))}</summary>${nqGroups(x.id,x.groups)}
      <div class="fh">${esc(t('Unterordner auslassen: Ich → Dokumente → Ausgelassene Ordner','Leave out sub folders: Me → Documents → Left-out folders'))}</div>
      <div class="row"><button class="b p" type="button" data-nqsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button></div></details>`:''}
    <div class="row"><button class="b" type="button" data-nqdel="${esc(x.id)}">${esc(t('Entfernen','Remove'))}</button></div></div>`}
// the Wissensordner part of one place under "Wofür" (nas.js)
function nqUse(place){if(!NQ)return '';const id=place.id,hs=NQ.haus.sources.filter(x=>x.nas===id).map(x=>Object.assign({haus:true},x));
  const mine=NQ.sources.filter(x=>x.nas===id).concat(hs),may=NQ.haus.may&&NQ.haus.count<NQ.haus.max;
  const add=NQ.on&&(NQ.sources.length<NQ.max||may)?`<div class="use"><div class="use-h"><span><b>${esc(mine.length?t('Weiterer Wissensordner','Another knowledge folder'):t('Wissensordner','Knowledge folder'))}</b><small>${esc(t('Der Spark liest Dokumente aus einem Ordner dort und findet sie bei Fragen; dort ändert sich nichts.','The Spark reads documents from a folder there and finds them when asked; nothing changes there.'))}</small></span>${tglIn(`data-nqon="${esc(id)}" aria-label="${esc(t('Wissensordner','Knowledge folder'))}"`,false)}</div>
    <div class="useform" data-nqform="${esc(id)}" hidden><label>${esc(t('Ordner dort','Folder there'))}</label><input data-nqpath="${esc(id)}" maxlength="300" value="${esc(NQ_PATH[place.kind]??'/')}" autocomplete="off">
      <div class="fh">${esc(place.kind==='smb'?t('Freigabe und Ordner, z. B. /home/Dokumente','Share and folder, e.g. /home/Documents'):t('Pfad dort, z. B. /home/Dokumente','Path there, e.g. /home/Documents'))}</div>
      <div class="row"><button class="b" type="button" data-nqtree="${esc(id)}">${esc(t('Ordner durchsuchen','Browse folders'))}</button></div><div class="nqtree" data-nqdirs="${esc(id)}"></div>
      <label style="margin-top:8px">${esc(t('Was gelesen wird','What is read'))}</label>${nqGroups('new-'+id,NQ.groups.filter(g=>g.on).map(g=>g.id))}
      ${may?`<label class="chk"><input type="checkbox" data-nqhaus="${esc(id)}"${NQ.sources.length<NQ.max?'':' checked disabled'}> ${esc(t('Für alle im Haushalt (Haushaltsordner): jedes Profil findet die Dokumente, Gäste und fremde Stimmen nie','For everyone in the household (household folder): every profile finds the documents, guests and unknown voices never'))}</label>`:''}
      <div class="row" style="margin-top:8px"><button class="b" type="button" data-nqprev="${esc(id)}">${esc(t('Vorschau','Preview'))}</button><button class="b p" type="button" data-nqadd="${esc(id)}">${esc(t('Hinzufügen','Add'))}</button></div>
      <div class="fh" data-nqprevmsg="${esc(id)}" role="status"></div></div></div>`:'';
  return mine.map(nqOne).join('')+add}
function nqBind(box,after,say){if(!NQ)return;
  const picked=pre=>[...box.querySelectorAll(`[data-nqg="${pre}"]`)].filter(c=>c.checked).map(c=>c.value);
  const q=(a,id)=>box.querySelector(`[${a}="${id}"]`);
  const haus=id=>{const c=q('data-nqhaus',id);return !!(c&&c.checked)};
  const go=async(url,opts,ok)=>{try{const r=await (await api(url,opts)).json();await after();if(ok)say(ok(r))}catch(e){await after();say(e.message,true)}};
  box.querySelectorAll('[data-nqon]').forEach(c=>c.onchange=()=>{const f=q('data-nqform',c.dataset.nqon);if(f)f.hidden=!c.checked});
  box.querySelectorAll('[data-nqtree]').forEach(b=>b.onclick=async()=>{const id=b.dataset.nqtree,p=q('data-nqpath',id),out=q('data-nqdirs',id);
    out.textContent=t('Lese die Ordner …','Reading the folders …');
    try{const d=await (await api('/api/profile/nasquelle/tree?nas='+encodeURIComponent(id)+'&path='+encodeURIComponent(p.value.trim()))).json();
      out.textContent='';const pick=(label,path)=>{const x=document.createElement('button');x.type='button';x.className='b';x.textContent=label;x.onclick=()=>{p.value=path;b.click()};out.appendChild(x)};
      const here=d.path==='/'?'':d.path.replace(/\/$/,'');if(here)pick('↑ '+t('nach oben','up'),here.split('/').slice(0,-1).join('/')||'/');
      d.dirs.forEach(n=>pick(n+'/',here+'/'+n));
      const m=document.createElement('div');m.className='fh';m.textContent=t(`${d.files} Dateien direkt hier`,`${d.files} files right here`)+(d.more?' · '+t('nur die ersten 500 Ordner','only the first 500 folders'):'');out.appendChild(m)}
    catch(e){out.textContent='';say(e.message,true)}});
  box.querySelectorAll('[data-nqprev]').forEach(b=>b.onclick=async()=>{const id=b.dataset.nqprev,m=q('data-nqprevmsg',id);m.className='fh';m.textContent=t('Zähle, was gelesen würde …','Counting what would be read …');
    try{const d=await (await api('/api/profile/nasquelle/preview',xjson('POST',{nas:id,path:q('data-nqpath',id).value.trim(),groups:picked('new-'+id),haus:haus(id)}))).json();
      const per=Object.entries(d.groups).map(([g,n])=>{const x=NQ.groups.find(y=>y.id===g);return (x?t(x.name[0],x.name[1]):g)+' '+n}).join(', ');
      // Dominik 2026-10-14 ("was bedeutet diese info"): what will be read, what stays out and why, how to change it
      m.textContent=t(`${d.files} Dateien passen zur Auswahl (${spSize(d.bytes)})`,`${d.files} files fit the choice (${spSize(d.bytes)})`)+(per?': '+per:'')+'. '
        +(d.left_out?t(`Gelesen werden davon höchstens ${d.read}, ${d.left_out} bleiben ungelesen: Pro Profil gehen ${d.limit} Dokumente von Orten in die Suche (stellt der Admin ein unter Funktionen → Speicher und NAS → Wissensordner). Zuerst kommen Dokumente, Tabellen und Text, dann Bilder und Scans, jeweils die neuesten zuerst.`,
            `At most ${d.read} of them are read, ${d.left_out} stay unread: each profile gets ${d.limit} documents from places into the search (set by the admin under Features → Storage and NAS → Knowledge folders). Documents, tables and text come first, then pictures and scans, the newest first each.`)
            +(d.groups.bilder?' '+t('Tipp: „Bilder und Scans“ abwählen oder einen Unterordner wählen.','Tip: untick "Pictures and scans" or pick a sub folder.'):'')+' '
          :t('Alle werden gelesen. ','All of them are read. '))
        +(d.read?t(`Das erste Lesen braucht etwa ${d.rounds} Runden zu höchstens 200 Dateien, in ruhigen Minuten eine nach der anderen; danach schaut der Spark alle ${d.every} Minuten nach Neuem.`,
            `The first reading takes about ${d.rounds} rounds of up to 200 files, one after another in quiet minutes; then the Spark looks for new files every ${d.every} minutes.`):'')
        +(d.complete?'':' '+t(`Der Ordner ist sehr groß: gezählt wurde nur bis ${d.seen_most} Einträge oder eine Minute lang, es sind also noch mehr.`,`The folder is very large: only up to ${d.seen_most} entries or one minute were counted, so there are more.`))}
    catch(e){m.className='fh err';m.textContent=e.message}});
  box.querySelectorAll('[data-nqadd]').forEach(b=>b.onclick=async()=>{const id=b.dataset.nqadd;b.disabled=true;say(t('Prüfe den Ordner …','Checking the folder …'));
    try{await api('/api/profile/nasquelle',xjson('POST',{nas:id,path:q('data-nqpath',id).value.trim(),groups:picked('new-'+id),haus:haus(id)}));await after();say(t('Hinzugefügt. Der Spark liest jetzt; große Ordner brauchen mehrere Runden.','Added. The Spark is reading now; large folders take several rounds.'))}
    catch(e){b.disabled=false;say(e.message,true)}});
  box.querySelectorAll('[data-nqnow]').forEach(b=>b.onclick=()=>{b.disabled=true;say(t('Lese den Ordner …','Reading the folder …'));
    go('/api/profile/nasquelle/'+encodeURIComponent(b.dataset.nqnow)+'/now',{method:'POST'},r=>t(`${r.new} neu, ${r.gone} weg, ${r.left} warten.`,`${r.new} new, ${r.gone} gone, ${r.left} waiting.`))});
  box.querySelectorAll('[data-nqsave]').forEach(b=>b.onclick=()=>{const id=b.dataset.nqsave;
    go('/api/profile/nasquelle/'+encodeURIComponent(id),xjson('PUT',{groups:picked(id)}),()=>t('Gespeichert. Der nächste Abgleich folgt dem.','Saved. The next reading follows it.'))});
  box.querySelectorAll('[data-nqdel]').forEach(b=>b.onclick=()=>{if(!confirm(t('Diesen Wissensordner entfernen? Seine Dokumente verschwinden aus der Suche; am Ort bleibt alles, wie es ist.','Remove this knowledge folder? Its documents leave the search; everything at the place stays as it is.')))return;
    go('/api/profile/nasquelle/'+encodeURIComponent(b.dataset.nqdel),{method:'DELETE'},r=>t(`Entfernt, ${r.removed} Dokumente aus der Suche.`,`Removed, ${r.removed} documents out of the search.`))})}
// Zustand → Speicher und NAS (admin): per profile numbers and state, never a path or a name of a file
async function zNasquelle(){const box=$('znasquelle');if(!box||document.hidden)return;let d;
  try{const r=await /*raw: timer poll, a 401/503 must stay silent*/fetch('/api/admin/nasquelle',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;
  $('znasquellelist').innerHTML=d.rows.length?d.rows.map(x=>`<div class="zrow"><span class="pill ${x.fail?(x.fail==='offline'?'warn':'bad'):'ok'}">${esc(x.fail?t(...(NAS_WHY[x.fail]||NAS_WHY.other)):t('aktuell','up to date'))}</span><span><b>${esc(x.haus?t('Haushalt','Household'):x.profile)}</b><div class="mut">${esc(t(`${x.files} Dokumente`,`${x.files} documents`))}${x.left?' · '+esc(t(`${x.left} warten`,`${x.left} waiting`)):''} · ${esc(t('zuletzt','last'))} ${esc(spWhen(x.last))}</div></span></div>`).join('')
    :`<div class="mut">${esc(t('Noch kein Profil liest einen Ordner.','No profile reads a folder yet.'))}</div>`}
