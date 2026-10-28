const key='atlas-read-versions';
export function readVersions():Record<string,string>{
 try{const value=JSON.parse(localStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{}}catch{return {}}
}
export function isUnread(id:string,version:string){return readVersions()[id]!==version}
export function markVersions(items:{id:string;version:string}[]):boolean{
 try{const value=readVersions();for(const item of items)value[item.id]=item.version;localStorage.setItem(key,JSON.stringify(value));window.dispatchEvent(new Event('atlas-reading-change'));return true}catch{return false}
}

/** One marker contract for catalog rows, cards and navigation links. */
export function bindMaterialReadingState(scope:ParentNode=document){
 const render=()=>{const read=readVersions();for(const dot of scope.querySelectorAll<HTMLElement>('[data-unread-dot]')){
  const owner=dot.closest<HTMLElement>('[data-material-id][data-version]');
  const id=dot.dataset.materialId||owner?.dataset.materialId,version=dot.dataset.version||owner?.dataset.version;
  dot.hidden=!id||!version||read[id]===version;
 }};
 render();window.addEventListener('atlas-reading-change',render);window.addEventListener('storage',render);window.addEventListener('pageshow',render);
 return ()=>{window.removeEventListener('atlas-reading-change',render);window.removeEventListener('storage',render);window.removeEventListener('pageshow',render)};
}
