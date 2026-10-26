// Render overview plates once, at build time. No geographical JSON or React on the reader's path.
import {readFileSync,writeFileSync,mkdirSync,readdirSync,unlinkSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {geoConicEqualArea,geoGraticule,geoPath} from 'd3-geo';
const dir=fileURLToPath(new URL('../public/data/',import.meta.url));
const points=JSON.parse(readFileSync(`${dir}settlements-preview.json`,'utf8'));
const land=JSON.parse(readFileSync(`${dir}country-preview.geojson`,'utf8'));
const coordinates=land.features.flatMap(f=>f.geometry.coordinates.flat());
const projection=geoConicEqualArea().rotate([-105,0]).parallels([50,70]).fitExtent([[20,34],[940,482]],{type:'MultiPoint',coordinates});
const path=geoPath(projection).digits(1);
const outline=path(land);const graticule=path(geoGraticule().step([20,10]).extent([[18,40],[191,84]])());
const n=v=>Number(v.toFixed(1));
const marks={distribution:'',decline:'',stable:'',growth:'',unknown:''};const occupied=new Set();
for(const [lon,lat,change]of points){const [x,y]=projection([lon,lat]);const key=`${Math.floor(x/3)}:${Math.floor(y/3)}`;if(occupied.has(key))continue;occupied.add(key);
 const d=`M${n(x-1.1)} ${n(y-1.1)}h2.2v2.2h-2.2z`;
 marks.distribution+=d;marks[change===null?'unknown':change< -10?'decline':change>10?'growth':'stable']+=d;
}
const cities=[['Москва',37.6173,55.7558],['Екатеринбург',60.5975,56.8389],['Владивосток',131.8855,43.1155]];
const variants={};mkdirSync(dir,{recursive:true});
for(const filename of readdirSync(dir))if(/^overview-(change|distribution)-(light|dark)-[a-f0-9]+\.svg$/.test(filename))unlinkSync(`${dir}${filename}`);
for(const variant of ['change','distribution'])for(const theme of ['light','dark']){
 const dark=theme==='dark';const blue=dark?'#8da8ff':'#244cff',bg=dark?'#111d37':'#fff';
 const colors={distribution:blue,decline:dark?'#ffaa76':'#f17f4f',stable:dark?'#c5d2ff':'#a7bcff',growth:blue,unknown:dark?'#a1aed0':'#8390b3'};
 const labels=cities.map(([name,lon,lat],i)=>{const [x,y]=projection([lon,lat]);const dx=i===2?-18:18,dy=i===2?-35:32;return `<g><circle cx="${n(x)}" cy="${n(y)}" r="4.5" fill="${bg}" stroke="${blue}" stroke-width="1.5"/><path d="M${n(x)} ${n(y)}l${dx} ${dy}h${i===2?-75:75}" fill="none" stroke="${blue}" opacity=".6"/><text x="${n(x+dx)}" y="${n(y+dy-6)}" text-anchor="${i===2?'end':'start'}" class="city">${name}</text><text x="${n(x+dx)}" y="${n(y+dy+12)}" text-anchor="${i===2?'end':'start'}" class="coordinates">${lat.toFixed(2)}° N / ${lon.toFixed(2)}° E</text></g>`}).join('');
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" width="960" height="540"><style>text{font-family:Arial,sans-serif;fill:${blue};paint-order:stroke;stroke:${bg};stroke-width:4;stroke-linejoin:round}.city{font-size:15px;font-weight:600}.coordinates{font-family:monospace;font-size:11px;stroke-width:3}</style><defs><path id="land" d="${outline}"/><pattern id="dots" width="5" height="5" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".6" fill="${blue}" opacity=".28"/></pattern></defs><path d="${graticule}" stroke="${blue}" stroke-width=".6" stroke-dasharray="1 5" fill="none" opacity=".2"/><use href="#land" fill="${blue}" fill-opacity=".07" stroke="${blue}" stroke-width=".5" stroke-opacity=".3"/><use href="#land" fill="url(#dots)"/>${(variant==='change'?['decline','stable','growth','unknown']:['distribution']).map(key=>`<path d="${marks[key]}" fill="${colors[key]}" fill-opacity=".92"/>`).join('')}${labels}</svg>`;
 const hash=createHash('sha256').update(svg).digest('hex').slice(0,12);const filename=`overview-${variant}-${theme}-${hash}.svg`;
 writeFileSync(`${dir}${filename}`,svg);variants[`${variant}.${theme}`]=filename;console.log(`${filename}: ${Buffer.byteLength(svg)} bytes`);
}
writeFileSync(`${dir}map-previews.json`,JSON.stringify(variants));
