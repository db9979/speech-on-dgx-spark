// Apps und Schnittstellen als Kacheln (plaene/einstellungen-neu.md, Paket 5): the addresses stay on top, every app
// below is a tile with its name and one sentence; a tap opens it over the full width with its steps and code. Tiles
// of a function (MCP server, own MCP services, Pebble) show whether its switch is on and lead to it under Funktionen
// (Anordnung, Umzug 8). Only the look changes: the cards, their ids and what loadInt fills in stay as they are.
(()=>{
const sec=$('apps');if(!sec)return;
const cards=[...sec.querySelectorAll(':scope>.card,:scope>.two>.card')].slice(1);if(!cards.length)return;
const grid=document.createElement('div');grid.className='atiles';cards[0].closest('.two')?cards[0].closest('.two').before(grid):cards[0].before(grid);
cards.forEach(c=>{const two=c.parentElement.classList.contains('two')?c.parentElement:null;grid.appendChild(c);if(two&&!two.children.length)two.remove();
  c.classList.add('atile');const sum=c.querySelector(':scope>.mut');if(sum)sum.classList.add('atsum');const h=c.querySelector(':scope>h2');if(!h)return;
  const b=document.createElement('button');b.type='button';b.className='atbtn';b.setAttribute('aria-expanded','false');b.textContent=h.textContent;h.textContent='';h.appendChild(b);
  b.onclick=()=>{const on=!c.classList.contains('open');grid.querySelectorAll('.atile.open').forEach(x=>{x.classList.remove('open');x.querySelector('.atbtn').setAttribute('aria-expanded','false')});
    c.classList.toggle('open',on);b.setAttribute('aria-expanded',on?'true':'false');if(on)c.scrollIntoView({block:'nearest',behavior:'smooth'})}});
// the state of the functions behind a tile, from the same list as Gesperrte Funktionen
async function state(){let d;try{d=await (await api('/api/admin/features')).json()}catch{return}
  grid.querySelectorAll('.atile[data-sw]').forEach(c=>{const f=d.features.find(x=>x.switch===c.dataset.sw);let s=c.querySelector(':scope>.atstate');
    if(!f){if(s)s.remove();return}
    if(!s){s=document.createElement('button');s.type='button';s.className='atstate';c.querySelector(':scope>h2').after(s);s.onclick=()=>{if(typeof whoOpen==='function')whoOpen({switch:c.dataset.sw})}}
    s.classList.toggle('on',!!f.spark);s.textContent=(f.spark?t('Funktion an','Function on'):t('Funktion aus','Function off'))+' · '+t('unter Funktionen','under Functions')})}
window.appTiles=state;
})();
