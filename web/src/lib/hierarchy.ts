/** One parent per page; nesting is navigation metadata, never a copy or a new URL. */
export type HierarchyPage={id:string;title:string;parentId?:string;order?:number};
export type HierarchyNode<T extends HierarchyPage>={page:T;children:HierarchyNode<T>[]};

export function ancestorsOf<T extends HierarchyPage>(id:string,pages:T[]):T[]{
 const byId=new Map(pages.map(page=>[page.id,page]));
 const result:T[]=[];const seen=new Set([id]);let page=byId.get(id);
 while(page?.parentId){
  if(seen.has(page.parentId))throw new Error(`Cyclic material hierarchy: ${id}`);
  seen.add(page.parentId);const parent=byId.get(page.parentId);
  if(!parent)break; // An archived ancestor can be absent from a filtered public collection.
  result.unshift(parent);page=parent;
 }
 return result;
}

export function buildHierarchy<T extends HierarchyPage>(pages:T[]):HierarchyNode<T>[]{
 const nodes=new Map(pages.map(page=>[page.id,{page,children:[] as HierarchyNode<T>[]} ]));
 const roots:HierarchyNode<T>[]=[];
 for(const page of pages){ancestorsOf(page.id,pages);const node=nodes.get(page.id)!;const parent=page.parentId?nodes.get(page.parentId):undefined;(parent?parent.children:roots).push(node)}
 const sort=(items:HierarchyNode<T>[])=>{items.sort((a,b)=>(a.page.order??Number.MAX_SAFE_INTEGER)-(b.page.order??Number.MAX_SAFE_INTEGER)||a.page.title.localeCompare(b.page.title,'ru')||a.page.id.localeCompare(b.page.id));for(const node of items)sort(node.children)};
 sort(roots);return roots;
}

export function flattenHierarchy<T extends HierarchyPage>(nodes:HierarchyNode<T>[]):T[]{
 return nodes.flatMap(node=>[node.page,...flattenHierarchy(node.children)]);
}
