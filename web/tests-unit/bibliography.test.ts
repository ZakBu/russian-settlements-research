import test from 'node:test';
import assert from 'node:assert/strict';
import {buildPublication,formatBibliography} from '../src/lib/bibliography.ts';

const sources=[{title:'Принятая база',url:'https://example.org/data/v1'},{title:'Документ обслуживания',url:'https://example.org/service'},{title:'Пояснение',url:'https://example.org/method'}];
const datasets=[{id:'census',title:'Переписная база',url:'https://example.org/data/v1#table',release:'census-v1'}];
const visuals=[{id:'map',title:'Распределение населения',template:'settlement-map',datasetId:'census'},{id:'chart',title:'Динамика численности',template:'census-trend',datasetId:'census'},{id:'table',title:'Значения переписей',template:'table',datasetId:'census'},{id:'links',title:'Прикрепления',template:'service-links',datasetId:'census'}];

function publication(body:string,ids=['map','chart']){return buildPublication({id:'example',body,sources,visualIds:ids},{visuals,datasets,basePath:'/research/'})}

test('bibliography follows first use, deduplicates one document and keeps uncited declared evidence',()=>{
 const p=publication('Сначала документ [@source:2].\n\n:::visual map\n:::\n\nПовтор данных [@source:1] и [@data:census].');
 assert.deepEqual(p.bibliography.map(x=>[x.number,x.url]),[[1,'https://example.org/service'],[2,'https://example.org/data/v1'],[3,'https://example.org/method']]);
 assert.match(p.document.html,/href="#source-1"[^>]*>\[1\]<\/a>/);assert.match(p.document.html,/data-citation-url="https:\/\/example.org\/data\/v1"/);
 assert.equal(p.figures.map.sourceNumber,2);assert.equal(p.figures.map.sourceText,'Источник: построено автором по данным Переписная база [2]');
 assert.deepEqual(p.remainingVisualIds,['chart']);assert.deepEqual(p.unresolvedReferences,[]);
});

test('images and registered drawings share continuous numbering; tables and link cards do not consume it',()=>{
 const p=publication('См. [@fig:chart] и [@fig:image-1].\n\n:::visual map\n:::\n\n![Схема из источника](https://example.org/schema.png)\n\n:::visual table\n:::\n\n:::visual links\n:::', ['map','chart','table','links']);
 assert.equal(p.figures.map.number,1);assert.equal(p.images['image-1'].number,2);assert.equal(p.figures.chart.number,3);assert.equal(p.figures.table.number,1);assert.equal(p.figures.table.kind,'table');assert.equal(p.figures.links.kind,'link');assert.equal(p.figures.links.number,undefined);
 assert.match(p.document.html,/data-figure-ref="chart" href="#visual-chart">рисунок 3<\/a>/);assert.match(p.document.html,/href="#illustration-image-1">рисунок 2<\/a>/);
 assert.match(p.document.html,/data-document-image="image-1" data-figure-number="2"/);assert.match(p.document.html,/Рисунок 2 — Схема из источника/);assert.equal(p.images['image-1'].authored,false);assert.doesNotMatch(p.images['image-1'].sourceText,/автором/);
 assert.doesNotMatch(p.document.html,/<p><figure/);assert.equal(p.figures.links.sourceText,'Источник: данные Переписная база [1]');
});

test('literature uses registered metadata and citations do not invent publishers or access dates',()=>{
 const p=buildPublication({id:'note',body:'Метод [@EXAMPLE, с. 35].',sources:[],visualIds:[]},{visuals:[],datasets:[],literature:[{id:'EXAMPLE',title:'Модель',authors:['Иванов И. И.','Петров П. П.'],year:2020,journal:'География',volume:12,issue:3,pages:'34–38',doi:'10.1234/example',url:'https://doi.org/10.1234/example'}]});
 assert.match(p.document.html,/>\[1, с\. 35\]<\/a>/);assert.match(p.bibliography[0].text,/Иванов И\. И\.; Петров П\. П\. Модель \/\/ География\. — 2020\. — Т\. 12, № 3\. — С\. 34–38\./);
 assert.match(p.bibliography[0].text,/DOI: 10\.1234\/example/);assert.doesNotMatch(p.bibliography[0].text,/дата обращения|Москва|Стандартинформ/);
 const online=formatBibliography({title:'Реестр',url:'https://example.org/v1',accessed:'2026-10-26',publisher:'Организация',year:2024,release:'v1'});
 assert.match(online,/Организация, 2024/);assert.match(online,/Версия: v1/);assert.match(online,/дата обращения: 26\.10\.2026/);
 const incomplete=formatBibliography({title:'Реестр',url:'https://example.org/v1'});assert.equal(incomplete,'Реестр. — URL: https://example.org/v1.');
});

test('unresolved references are explicit and hostile labels/locators cannot inject markup',()=>{
 const p=publication('Неизвестные [@source:99] [@data:missing] [@UNKNOWN] [@fig:missing].\n\nСсылка [@source:1, <img src=x onerror=bad>].');
 assert.deepEqual(p.unresolvedReferences,['source:99','data:missing','UNKNOWN','fig:missing']);
 assert.match(p.document.html,/&lt;img src=x onerror=bad&gt;/);assert.doesNotMatch(p.document.html,/<img src=x|onerror="bad"/);
 assert.match(p.document.html,/источник не найден/);assert.match(p.document.html,/рисунок не найден/);
});

test('literal code examples do not consume citation or figure numbers',()=>{
 const p=publication('```md\n[@source:2]\n:::visual map\n:::\n![Пример](https://example.org/image.png)\n```\n\nРеальный источник [@source:1].',[]);
 assert.equal(p.bibliography[0].url,'https://example.org/data/v1');assert.deepEqual(p.figures,{});assert.deepEqual(p.images,{});assert.match(p.document.html,/\[@source:2\]/);
});


test('a dataset citation preserves richer factual metadata declared for the same source URL',()=>{
 const p=buildPublication({id:'note',body:':::visual map\n:::',visualIds:['map'],sources:[{title:'Источник базы',url:'https://example.org/data/v1',authors:'Организация',accessed:'2026-10-26',publisher:'Издатель',year:2024}]},{visuals,datasets});
 assert.equal(p.bibliography.length,1);assert.match(p.bibliography[0].text,/Организация Переписная база/);assert.match(p.bibliography[0].text,/Издатель, 2024/);assert.match(p.bibliography[0].text,/дата обращения: 26\.10\.2026/);assert.match(p.bibliography[0].text,/Версия: census-v1/);
});


test('registered primary reading URLs are usable when the literature entry has no duplicate url field',()=>{
 const p=buildPublication({id:'note',body:'Метод [@PRIMARY_DOC].',sources:[],visualIds:[]},{visuals:[],datasets:[],literature:[{id:'PRIMARY_DOC',title:'Документация метода',reading_url:'https://example.org/primary'}]});
 assert.equal(p.bibliography[0].url,'https://example.org/primary');assert.deepEqual(p.unresolvedReferences,[]);
});
