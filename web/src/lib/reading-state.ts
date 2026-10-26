const key='atlas-read-versions';
export function readVersions():Record<string,string>{
 try{const value=JSON.parse(localStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{}}catch{return {}}
}
export function isUnread(id:string,version:string){return readVersions()[id]!==version}
export function markVersions(items:{id:string;version:string}[]):boolean{
 try{const value=readVersions();for(const item of items)value[item.id]=item.version;localStorage.setItem(key,JSON.stringify(value));window.dispatchEvent(new Event('atlas-reading-change'));return true}catch{return false}
}
