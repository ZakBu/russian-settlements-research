import test from 'node:test';
import assert from 'node:assert/strict';
import {ancestorsOf,buildHierarchy,flattenHierarchy} from '../src/lib/hierarchy.ts';

test('six article levels retain a complete root-to-parent path and a stable preorder',()=>{
 const pages=Array.from({length:6},(_,i)=>({id:`level-${i}`,title:`Уровень ${i}`,parentId:i?`level-${i-1}`:undefined}));
 assert.deepEqual(ancestorsOf('level-5',pages).map(p=>p.id),pages.slice(0,5).map(p=>p.id));
 assert.deepEqual(flattenHierarchy(buildHierarchy([...pages].reverse())).map(p=>p.id),pages.map(p=>p.id));
 assert.equal(buildHierarchy(pages)[0].children[0].children[0].children[0].children[0].children[0].page.id,'level-5');
});

test('sibling ordering is explicit, then Russian title, and never mutates the input',()=>{
 const pages=[{id:'root',title:'Раздел'}, {id:'b',title:'Бета',parentId:'root',order:2},{id:'a',title:'Альфа',parentId:'root',order:1},{id:'v',title:'Вега',parentId:'root'},{id:'g',title:'Гамма',parentId:'root'}];
 const before=JSON.stringify(pages);assert.deepEqual(buildHierarchy(pages)[0].children.map(n=>n.page.id),['a','b','v','g']);assert.equal(JSON.stringify(pages),before);
});

test('cycles are rejected and a filtered collection never loses an orphaned visible page',()=>{
 assert.throws(()=>buildHierarchy([{id:'a',title:'A',parentId:'b'},{id:'b',title:'B',parentId:'a'}]),/Cyclic/);
 assert.throws(()=>ancestorsOf('a',[{id:'a',title:'A',parentId:'a'}]),/Cyclic/);
 assert.equal(buildHierarchy([{id:'child',title:'Статья',parentId:'outside-filter'}])[0].page.id,'child');
});
