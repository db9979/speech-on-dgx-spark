// ---------------------------------------------------------------- Zustand → Praxistest (admin)
// The points of the hands-on test (praxistest.py, praxistest.json): what is new and still to try in daily use, in
// three tiers the panel counts (stufe): „Jetzt wichtig“ open on top, „Bei Gelegenheit“ and „Durch Selbsttest
// abgedeckt“ folded, in each the newest first. Per point „Klappt“, „Problem“, „Später“; old points nobody marked are folded away with one button
// „Alle erledigt“. A way in a step becomes a jump link by itself (way.js). Text only through textContent.
const PT_STAND={ok:['klappt','works'],problem:['Problem','problem'],spaeter:['später','later'],erledigt:['erledigt','done']};
const PT_CLS={ok:'pt-ok',problem:'pt-problem',spaeter:'pt-spaeter',erledigt:'pt-erledigt'};
// a point's version: v = middle number × 1000 + patch (V01.0.999 = 999, V01.1.000 = 1000, Dominik 2026-10-24 „2“)
const ptVer=v=>'V01.'+Math.floor(v/1000)+'.'+String(v%1000).padStart(3,'0');
function ptEl(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function ptBtn(label,cls,go){const b=ptEl('button','b sm'+(cls?' '+cls:''),label);b.type='button';b.onclick=go;return b}
async function ptMark(id,stand){const msg=$('ptmsg');msg.textContent='';
  try{await api('/api/admin/praxistest/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stand})});
    await loadPraxis();if(stand==='problem')ptProblem(id)}catch(e){msg.textContent=e.message}}
// a problem: the way to the log lines to copy for the thread, with the point's number in front
function ptProblem(id){const msg=$('ptmsg');msg.textContent='';
  msg.append(t(`${id} hat ein Problem: `,`${id} has a problem: `),
    wayEl(t('Zustand → Logs → Diagnose','Status → Logs → Diagnosis'),t('Zustand → Logs → Diagnose','Status → Logs → Diagnosis')),
    t(` öffnen, „Kopieren für Thread“ und den Text mit „${id}“ in den Thread geben.`,` open, „Copy for thread“ and give the text with „${id}“ to the thread.`))}
function ptRow(p){const row=ptEl('div','pt-row');row.dataset.id=p.id;
  row.append(ptEl('div','pt-v',p.v?ptVer(p.v):p.id));
  const tx=ptEl('div','pt-t'),h=ptEl('b',null,p.titel);tx.append(h);
  if(p.stand){const c=ptEl('span','pt-chip '+PT_CLS[p.stand],t(...PT_STAND[p.stand]));h.append(' ',c)}
  tx.append(ptEl('div','pt-steps',p.text));
  tx.append(ptEl('small','mut',p.id+(p.thread?' · '+t('Thread','Thread')+' „'+p.thread+'“':'')+(p.test&&!p.stand?' · '+t('Selbsttest','Self-test')+' '+p.test:'')));
  const bs=ptEl('div','pt-btns');
  if(p.stand!=='ok'&&p.stand!=='erledigt')bs.append(ptBtn(p.stand==='problem'?t('Doch klappt','Works after all'):t('Klappt','Works'),'pt-ok',()=>ptMark(p.id,'ok')));
  if(!p.stand||p.stand==='spaeter')bs.append(ptBtn(t('Problem','Problem'),'pt-bad',()=>ptMark(p.id,'problem')));
  if(!p.stand)bs.append(ptBtn(t('Später','Later'),'',()=>ptMark(p.id,'spaeter')));
  if(p.stand)bs.append(ptBtn(t('Wieder offen','Open again'),'',()=>ptMark(p.id,'offen')));
  row.append(tx,bs);return row}
function ptGroup(title,list,open){const d=ptEl('details','card pt-grp');d.open=!!open;
  const s=ptEl('summary',null,`${title} (${list.length})`);d.append(s);list.forEach(p=>d.append(ptRow(p)));return d}
async function loadPraxis(){const main=$('ptmain'),msg=$('ptmsg');if(!main)return;
  const d=await (await api('/api/admin/praxistest')).json();const n=d.zahlen,ps=d.punkte;main.replaceChildren();
  const sum=ptEl('div','pt-sum');
  for(const [k,de,en] of [['wichtig','jetzt wichtig','important now'],['gelegenheit','bei Gelegenheit','when there is time'],['problem','Problem','problem'],['spaeter','später','later'],['ok','klappt','works'],['abgedeckt','durch Selbsttest abgedeckt','covered by a self-test'],['alt','alt, eingeklappt','old, folded']]){
    const c=ptEl('div','pt-n');c.append(ptEl('b',null,String(n[k]||0)),ptEl('small',null,t(de,en)));sum.append(c)}
  main.append(sum);
  if(L==='en')main.append(ptEl('div','mut vb-note','The steps are written in German by the threads that build each function.'));
  const by=f=>ps.filter(f);
  // an older panel names no tier: everything open is important then
  const offen=by(p=>!p.alt&&(!p.stand||p.stand==='problem')),wichtig=offen.filter(p=>!p.stufe||p.stufe==='wichtig');
  if(wichtig.length)main.append(ptGroup(t('Jetzt wichtig','Important now'),wichtig,true));
  else main.append(ptEl('div','card mut',t('Nichts ist jetzt wichtig: das Neueste ist geprüft.','Nothing is important now: the newest is checked.')));
  const gel=offen.filter(p=>p.stufe==='gelegenheit');if(gel.length)main.append(ptGroup(t('Bei Gelegenheit','When there is time'),gel,false));
  const spaeter=by(p=>p.stand==='spaeter');if(spaeter.length)main.append(ptGroup(t('Später','Later'),spaeter,false));
  const abg=offen.filter(p=>p.stufe==='abgedeckt');
  if(abg.length){const g=ptGroup(t('Durch Selbsttest abgedeckt','Covered by a self-test'),abg,false);
    g.insertBefore(ptEl('div','mut',t('Ein Selbsttest prüft bei jeder Version dieselben Sätze. Ausprobieren musst du diese Punkte nicht.','A self-test checks the same sentences with every version. You need not try these points.')),g.children[1]);main.append(g)}
  const alt=by(p=>p.alt);
  if(alt.length){const g=ptGroup(t(`Alt, vor ${ptVer(d.alt_bis)}, vermutlich erledigt`,`Old, before ${ptVer(d.alt_bis)}, probably done`),alt,false);
    const b=ptBtn(t('Alle alten erledigt','All old ones done'),'',async()=>{if(!confirm(t(`${alt.length} alte Prüfpunkte als erledigt markieren?`,`Mark ${alt.length} old points as done?`)))return;
      try{await api('/api/admin/praxistest/alt',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});loadPraxis()}catch(e){msg.textContent=e.message}});
    g.insertBefore(b,g.children[1]);main.append(g)}
  const fertig=by(p=>p.stand==='ok'||p.stand==='erledigt');if(fertig.length)main.append(ptGroup(t('Erledigt','Done'),fertig,false))}
