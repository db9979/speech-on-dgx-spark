// KI-Dungeon-Master: Runen und Sockel, the picture part (dungeon_dingbild.py, plan dungeon-runen 11a): an item's sockets
// as glowing dots over its picture, no new picture. A set rune glows in its fixed colour (it.ru_farbe, by the rune's
// rank, dungeon_dingbild.RUNE_FARBE), a free socket stays dark. dmDing calls dmSockel(it); nothing without sockets (it.so).
function dmSockel(it){const n=it&&+it.so||0;if(!n)return '';const ru=it.ru||[],f=it.ru_farbe||[];
  const l=t('Sockel','Sockets')+' '+ru.length+'/'+n+(ru.length?': '+ru.join(', '):'');
  return `<span class="dm-sockel" role="img" aria-label="${esc(l)}" title="${esc(l)}">${Array.from({length:n},(_,k)=>k<ru.length?`<i class="on" style="--rf:${esc(f[k]||'#ffd27a')}"></i>`:'<i></i>').join('')}</span>`}
