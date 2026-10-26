import type {APIRoute} from 'astro';

export const prerender=true;

// Same 5 × 5 pixel pattern and skew as .pixel-logo in the shared header.
// A light backing keeps the cobalt mark legible in both light and dark browser tabs.
export const GET:APIRoute=()=>{
 const pixels=Array.from({length:25},(_,index)=>{
  const n=index+1;
  if(n%4===0)return '';
  return `<rect x="${index%5*5}" y="${Math.floor(index/5)*5}" width="4" height="4"${n%3===0?' opacity=".3"':''}/>`;
 }).join('');
 return new Response(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><title>Атлас расселения</title><rect width="32" height="32" rx="6" fill="#f4f6ff"/><g transform="translate(4 6) skewY(-8)" fill="#244cff">${pixels}</g></svg>`,{headers:{'Content-Type':'image/svg+xml; charset=utf-8'}});
};
