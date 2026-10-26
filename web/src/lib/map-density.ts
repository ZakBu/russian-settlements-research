/** Cartographic visibility only: the complete census collection stays available to search/statistics. */
export function settlementPopulationCutoff(zoom:number):number{
 return zoom<4?100000:zoom<5?50000:zoom<7?10000:zoom<9?1000:zoom<11?100:0;
}
export function settlementMagnitude(properties:Record<string,unknown>):number{
 return Math.max(...['p02','p10','p21'].map(key=>{const n=properties[key];return typeof n==='number'&&Number.isFinite(n)?n:0}));
}
export function settlementVisibilityFilter(zoom:number):unknown[]{
 return ['>=',['max',...['p02','p10','p21'].map(key=>['coalesce',['get',key],0])],settlementPopulationCutoff(zoom)];
}
