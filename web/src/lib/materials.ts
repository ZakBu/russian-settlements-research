/** Shared catalog metadata. Scientific context stays in the original material. */
import tagData from '../../content/tags.json';
import {visuals} from './content';
import type {Material, Visual} from './content';
export type MaterialTag={id:string;label:string;aliases?:string[]};
export const tags=tagData as MaterialTag[];
export const tagLabels:Record<string,string>=Object.fromEntries(tags.map(t=>[t.id,t.label]));
export const kindLabels:Record<string,string>={finding:'Результат',method:'Метод и понятия',note:'Ход исследования',correction:'Исправление'};
export const formatLabels:Record<string,string>={map:'Карта',chart:'График',table:'Таблица',image:'Иллюстрация', 'map-link':'Переход к карте'};
export const territoryLabels:Record<string,string>={russia:'Россия',bashkortostan:'Башкортостан',uchaly:'Учалинский район',saratov:'Саратовская область',simferopol:'Симферополь',unspecified:'Территория не уточнена'};
const fold=(text:string)=>text.toLocaleLowerCase('ru').replace(/ё/g,'е');
const unique=(values:string[])=>[...new Set(values)];
/** Existing publications choose registry IDs. Untagged agent notes remain searchable. */
export function getMaterialTags(m:Material):string[]{
 if(m.tags?.length)return unique(m.tags.filter(id=>id in tagLabels));
 if(m.kind==='note')return ['research-progress'];
 const topic=fold(m.topic);
 return tags.filter(t=>[t.label,...(t.aliases||[])].some(label=>topic.includes(fold(label)))).map(t=>t.id);
}
/** No location is inferred from an incidental mention or a research's geographic scope. */
export function getMaterialTerritories(m:Material):string[]{
 const text=fold(m.territory);const ids:string[]=[];
 if(/росси/.test(text))ids.push('russia');
 if(/башкортостан|учалинск/.test(text))ids.push('russia','bashkortostan');
 if(/учалинск/.test(text))ids.push('uchaly');
 if(/саратовск/.test(text))ids.push('russia','saratov');
 if(/симферопол/.test(text))ids.push('simferopol');
 return ids.length?unique(ids):['unspecified'];
}
/** Formats reflect actual figures/tables, never the subject tag alone. */
export function getMaterialFormats(m:Material,registry:Visual[]=visuals):string[]{
 const found:string[]=[];
 for(const id of m.visualIds){const visual=registry.find(v=>v.id===id);if(!visual)continue;
  if(visual.template==='settlement-map')found.push('map');
  else if(visual.template==='table')found.push('table');
  else if(visual.template==='service-links')found.push('map-link');
  else found.push('chart');
 }
 // Ignore literal examples. Images are available even without an interactive visual record.
 const body=m.body.replace(/^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[^\n]*$/gm,'').replace(/`[^`\n]+`/g,'');
 if(/^\s*\|.*\|\s*\n\s*\|[\s:|\-]+\|/m.test(body))found.push('table');
 const images=[...body.matchAll(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)(?:\s+"[^"]*")?\)/g)];
 if(images.length)found.push('image');
 for(const image of images){
  const preceding=body.slice(0,image.index).split('\n').filter(line=>/^#{1,6}\s/.test(line)).at(-1)||'';
  const description=fold(`${preceding} ${image[1]}`);
  if(/(?:^|[\s:])карт[аыуе](?:[\s,.:]|$)|на карт|точки.*россии|где находятся|географическ/.test(description))found.push('map');
  if(/график|диаграмм|сравнивается число/.test(description))found.push('chart');
 }
 return unique(found);
}
export function getMaterialSearchText(m:Material):string{
 return fold([m.title,m.summary,m.topic,m.territory,m.period,m.body,kindLabels[m.kind],...getMaterialTags(m).flatMap(id=>{const tag=tags.find(t=>t.id===id)!;return [tag.label,...(tag.aliases||[])]})].join(' '));
}
