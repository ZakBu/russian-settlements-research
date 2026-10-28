import test from 'node:test';
import assert from 'node:assert/strict';
import {researchLegendEntries,researchValueLabel,researchCategoryPalette, renderResearchLayer, type ResearchLayer} from '../src/components/custom-map-layers.ts';
const base: ResearchLayer={id:'example',researchId:'sgrt',title:'Time',description:'',geometry:'polygon',path:'custom-layers/example.geojson',palette:'categorical',unit:'class',period:'2021',evidence:'model',source:{title:'Source',url:'https://example.test/v1/geojson'}};
const labels={'0':'0–10 мин','1':'10–20 мин','2':'20–30 мин','3':'30–60 мин','4':'Unused class'};
const data={type:'FeatureCollection' as const,features:[0,1,2,3,null].map(value=>({properties:{value}}))};
test('named legend shows actual classes and four contrasting colors without an unused fifth class',()=>{
 const entries=researchLegendEntries({...base,valueLabels:labels},data);
 assert.deepEqual(entries.map(r=>r.label),['0–10 мин','10–20 мин','20–30 мин','30–60 мин']);
 assert.equal(new Set(entries.map(r=>r.color)).size,4);
 assert.deepEqual(entries.map(r=>r.color),researchCategoryPalette(false).slice(0,4));
});
test('class labels replace numeric codes in popups and do not turn missing data into class zero',()=>{
 const meta={...base,valueLabels:labels};
 assert.equal(researchValueLabel(meta,0),'0–10 мин');
 assert.equal(researchValueLabel(meta,3),'30–60 мин');
 assert.equal(researchValueLabel(meta,null),undefined);
 assert.equal(researchValueLabel(meta,NaN),undefined);
 assert.equal(researchValueLabel(meta,99),undefined);
});
test('old unlabeled layers keep their numeric legend and labels have matching dark colors',()=>{
 assert.deepEqual(researchLegendEntries(base,data),[]);
 assert.equal(researchValueLabel(base,2),undefined);
 const entries=researchLegendEntries({...base,valueLabels:labels},data,true);
 assert.deepEqual(entries.map(r=>r.color),researchCategoryPalette(true).slice(0,4));
});

test('one remaining categorical band retains the color in its named legend',()=>{
 const paints: Record<string,unknown>={};
 const map={getSource:()=>true,getLayer:()=>true,
  setPaintProperty:(_id:string,key:string,value:unknown)=>{paints[key]=value},
  setLayoutProperty:()=>{}};
 const meta={...base,valueLabels:labels};
 renderResearchLayer(map as any,meta,{type:'FeatureCollection',features:[{properties:{value:3}}]},true,false);
 const expression=paints['fill-color'] as any[];
 assert.equal(expression[0],'case');
 assert.equal(expression[3][0],'match');
 assert.equal(expression[3][9],researchCategoryPalette(false)[3]);
});

test('named zones use stronger matching fills and outlines while ordinary maps keep their style',()=>{
 const paints:Record<string,unknown>={};
 const map={getSource:()=>true,getLayer:()=>true,setLayoutProperty:()=>{},
  setPaintProperty:(id:string,key:string,value:unknown)=>{paints[id+':'+key]=value}};
 renderResearchLayer(map as any,{...base,valueLabels:labels},data,true,false);
 assert.equal(paints['research-example-fill:fill-opacity'],.6);
 assert.deepEqual(paints['research-example-outline:line-color'],paints['research-example-fill:fill-color']);
 assert.equal(paints['research-example-outline:line-width'],1);
 renderResearchLayer(map as any,base,data,true,false);
 assert.equal(paints['research-example-fill:fill-opacity'],.3);
 assert.equal(paints['research-example-outline:line-color'],'#244CFF');
 assert.equal(paints['research-example-outline:line-width'],1.5);
});
