// Voraussetzungen (Dominik 2026-10-12: "eine Info geben, wenn jemand Funktionen einschaltet, die andere
// voraussetzen, auch mit einschalten"). features.py gives every function its chain of Spark switches
// (/api/admin/features: chain, states, snames, switchable). Switching on asks whether the missing ones go on
// too; switching off says which functions that are on now go off with it.
// Funktionen: the switches are checkboxes chat.<switch> saved with the page (only checked here, saving stays
// with the page); Wer darf was: who.js asks needsOn/needsOff and switches over /api/admin/features/<key>/enable.
let NEEDS=null,NEEDS_AT=0,NEEDS_QUIET=false;
async function needsLoad(force){
  if(NEEDS&&!force&&Date.now()-NEEDS_AT<30e3)return NEEDS;
  try{needsSet(await (await api('/api/admin/features')).json())}catch{NEEDS=null}
  return NEEDS}
function needsSet(d){NEEDS=d;NEEDS_AT=Date.now()}       // who.js hands over what it loaded anyway
const needsName=sw=>{const n=NEEDS&&NEEDS.snames&&NEEDS.snames[sw];return n?n[L==='en'?1:0]:sw};
const needsFName=f=>f.name[L==='en'?1:0];
// „A“, „B“ und „C“
function needsList(names){const q=names.map(n=>t('„'+n+'“','"'+n+'"'));
  return q.length<2?q.join(''):q.slice(0,-1).join(', ')+t(' und ',' and ')+q[q.length-1]}
// the switches of f's chain that are off (isOn(sw) says whether a switch is on now), without f's own one
function needsMissing(f,isOn,own){return (f.chain||[]).filter(sw=>sw!==own&&!isOn(sw))}
// the functions that are on now and go off with sw (not the one sw belongs to)
function needsAffected(sw,isOn){
  return ((NEEDS&&NEEDS.features)||[]).filter(f=>f.switch!==sw&&(f.chain||[]).includes(sw)&&(f.chain||[]).every(s=>s===sw||isOn(s)))}
function needsAskOn(f,miss){
  return confirm(t(`„${needsFName(f)}“ braucht auch ${needsList(miss.map(needsName))}. Mit einschalten?`,
                   `"${needsFName(f)}" also needs ${needsList(miss.map(needsName))}. Switch them on too?`))}
function needsAskOff(sw,aff){
  return confirm(t(`Damit sind auch ${needsList(aff.map(needsFName))} aus. Trotzdem ausschalten?`,
                   `This also switches off ${needsList(aff.map(needsFName))}. Switch off anyway?`))}
// what the Spark could not switch itself (switches only the main admin sets, addresses): one note with ways
function needsNote(d){const ways=[...(d.manual||[]).map(m=>m.way[L==='en'?1:0]),...(d.setup||[]).map(w=>w[L==='en'?1:0])];
  if(ways.length)alert(t('Noch selbst erledigen: ','Still to do yourself: ')+ways.join(', '))}
// Wer darf was: the Spark column. true when the caller may go on with its own switching.
async function needsSpark(f,on,isOn){
  await needsLoad();
  if(on){const miss=needsMissing(f,isOn,f.switch);if(!miss.length)return true;
    if(!needsAskOn(f,miss))return true;            // only its own switch, as before
    const d=await (await api(`/api/admin/features/${encodeURIComponent(f.key)}/enable`,xjson('POST',{}))).json();
    needsNote(d);return false}
  const aff=needsAffected(f.switch,isOn);return !aff.length||needsAskOff(f.switch,aff)}
// Funktionen: a switch on the page changed
async function needsCfg(el){
  if(NEEDS_QUIET||!el||!el.id||!el.id.startsWith('chat.')||el.type!=='checkbox')return;
  const sw=el.id.slice(5);await needsLoad();if(!NEEDS)return;
  const isOn=s=>{const e=$('chat.'+s);return e&&e.type==='checkbox'?e.checked:!!(NEEDS.states&&NEEDS.states[s])};
  const set=(list,v)=>{NEEDS_QUIET=true;try{list.forEach(s=>{const e=$('chat.'+s);if(e&&e.type==='checkbox'&&e.checked!==v){
    e.checked=v;e.dispatchEvent(new Event('change',{bubbles:true}));e.dispatchEvent(new Event('input',{bubbles:true}))}})}finally{NEEDS_QUIET=false}};
  if(el.checked){
    const f=NEEDS.features.find(x=>x.switch===sw);if(!f)return;
    const miss=needsMissing(f,isOn,sw);if(!miss.length)return;
    if(!needsAskOn(f,miss))return;
    const here=miss.filter(s=>{const e=$('chat.'+s);return e&&e.type==='checkbox'});set(here,true);
    const away=miss.filter(s=>!here.includes(s));
    if(away.length)alert(t('Noch selbst einschalten: ','Still switch on yourself: ')+away.map(s=>t('Funktionen → ','Features → ')+needsName(s)).join(', '))
  }else{
    const aff=needsAffected(sw,s=>s===sw||isOn(s));if(!aff.length)return;
    if(!needsAskOff(sw,aff))set([sw],true)}}
document.addEventListener('change',e=>{const el=e.target;if(el&&el.id&&el.id.startsWith('chat.')&&el.closest&&el.closest('#pane-feat'))needsCfg(el)});
window.needsSet=needsSet;window.needsSpark=needsSpark;window.needsLoad=needsLoad;
