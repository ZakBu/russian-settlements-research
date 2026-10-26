import {createHash} from 'node:crypto';
import {visuals,datasets,type Material} from './content';
// Reading progress follows scientific content, not theme/tag/bibliographic formatting edits.
export function publicationVersion(m:Material):string{
 const payload={title:m.title,summary:m.summary,body:m.body,evidence:m.evidence,currency:m.currency,supersedes:m.supersedes,
  visuals:m.visualIds.map(id=>visuals.find(v=>v.id===id)),datasets:m.datasetIds.map(id=>{const d=datasets.find(d=>d.id===id);return d?{id:d.id,release:d.release,url:d.url}:id})};
 return createHash('sha256').update(JSON.stringify(payload)).digest('hex').slice(0,20);
}
