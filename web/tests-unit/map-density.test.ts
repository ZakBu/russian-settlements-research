import test from 'node:test';
import assert from 'node:assert/strict';
import {settlementPopulationCutoff,settlementMagnitude,settlementVisibilityFilter} from '../src/lib/map-density.ts';
test('map visibility progressively reveals settlements and fully opens at local zoom',()=>{
 const cutoffs=[2.6,4,5,7,9,11,16].map(settlementPopulationCutoff);
 assert.deepEqual(cutoffs,[100000,50000,10000,1000,100,0,0]);
 assert.ok(cutoffs.every((value,i)=>!i||value<=cutoffs[i-1]));
});
test('decluttering keeps historically large declining places and never rewrites missing observations',()=>{
 const data={p02:100000,p10:50000,p21:null};const copy={...data};
 assert.equal(settlementMagnitude(data),100000);assert.deepEqual(data,copy);
 assert.equal(settlementMagnitude({p02:null,p10:null,p21:null}),0);
 const filter=settlementVisibilityFilter(3);assert.equal(filter.at(-1),100000);
 assert.deepEqual(filter[1],['max',['coalesce',['get','p02'],0],['coalesce',['get','p10'],0],['coalesce',['get','p21'],0]]);
});
