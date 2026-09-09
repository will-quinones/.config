export function signature(source) {
  return JSON.stringify({tabs:source.tabs.map(t=>({url:t.url,pinned:!!t.pinned,group:t.group})),
    groups:source.groups.map(g=>({title:g.title,color:g.color}))});
}
export function validate(source, profile) {
  if (!source || source.kind !== 'chrome-window' || source.profile !== profile ||
      !/^[a-f0-9]{32}$/.test(source.token)) throw Error('Perfil/origen Chrome inválido');
  if (!Array.isArray(source.tabs) || !source.tabs.length || source.tabs.length>500 ||
      !Array.isArray(source.groups) || source.groups.length>200 ||
      !Number.isInteger(source.active) || source.active<0 || source.active>=source.tabs.length)
    throw Error('Ventana Chrome inválida');
  const colors=['grey','blue','red','yellow','green','pink','purple','cyan','orange'];
  for (const g of source.groups) if (typeof g.title!=='string' || g.title.length>1000 ||
      !colors.includes(g.color) || typeof g.collapsed!=='boolean') throw Error('Grupo inválido');
  let unpinned=false;
  source.tabs.forEach(t=>{
    if (typeof t.url!=='string' || t.url.length>32000 ||
        !(/^(https?:\/\/)/.test(t.url) || ['chrome://newtab/','about:blank'].includes(t.url)))
      throw Error('URL no admitida; solo HTTP(S), nueva pestaña y about:blank');
    if (typeof t.pinned!=='boolean' || !Number.isInteger(t.group) || t.group < -1 || t.group>=source.groups.length ||
        (t.pinned && (t.group!==-1 || unpinned))) throw Error('Orden de pestañas inválido');
    if (!t.pinned) unpinned=true;
  });
  source.groups.forEach((_,g)=>{
    const indices=source.tabs.flatMap((t,i)=>t.group===g?[i]:[]);
    if (!indices.length || indices.at(-1)-indices[0]+1!==indices.length) throw Error('Grupo no contiguo');
  });
  return source;
}
export function overlaps(a,b) {
  const urls = new Set(a.tabs.map(t=>t.url).filter(u=>/^https?:\/\//.test(u)));
  return b.tabs.some(t=>urls.has(t.url));
}
