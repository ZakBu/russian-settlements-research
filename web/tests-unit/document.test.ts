import test from 'node:test';
import assert from 'node:assert/strict';
import {renderDocument} from '../src/lib/document.ts';

test('Russian headings have stable unique anchors and a useful H2/H3 outline',()=>{
 const doc=renderDocument('# Обзор\n\n## Где **растёт** население?\n\n### Данные & ограничения\n\n## Где растёт население?\n\n#### Подробность');
 assert.deepEqual(doc.headings,[{id:'обзор',text:'Обзор',depth:2},{id:'где-растёт-население',text:'Где растёт население?',depth:2},{id:'данные-ограничения',text:'Данные & ограничения',depth:3},{id:'где-растёт-население-2',text:'Где растёт население?',depth:2}]);
 assert.doesNotMatch(doc.html,/<h1/);assert.match(doc.html,/aria-label="Ссылка на раздел: Где растёт население\?"/);
 assert.deepEqual(renderDocument('## Где растёт население?').headings,[doc.headings[1]]);
});

test('links and quotes render, unsafe URLs and raw HTML never become executable markup',()=>{
 const doc=renderDocument('> Цитата **автора**\n\n[Источник](https://example.org "Описание") [Опасно](javascript:alert%281%29) [Внешний](//evil.test)\n\n<script>alert(1)</script>\n\n![<img src=x onerror=alert(1)>](https://example.org/image.png)\n\n[Схема](java&#x73;cript:alert)');
 assert.match(doc.html,/<blockquote>/);assert.match(doc.html,/<strong>автора<\/strong>/);assert.match(doc.html,/href="https:\/\/example.org" title="Описание"/);
 assert.doesNotMatch(doc.html,/<script|href="(?:javascript:|java&|\/\/evil)/i);assert.match(doc.html,/alt="&lt;img src=x onerror=alert\(1\)&gt;"/);
});

test('scientific images use escaped lazy markup and local images respect the deployment prefix',()=>{
 const doc=renderDocument('![Карта "области" & сравнение](https://example.org/release/map.png "Источник & метод")\n\n![Локальная карта](/images/map.svg)\n\n![Уже с префиксом](/research/images/map.svg)',{basePath:'/research/'});
 assert.match(doc.html,/<img class="document-image" src="https:\/\/example.org\/release\/map.png" alt="Карта &quot;области&quot; &amp; сравнение" loading="lazy" decoding="async" title="Источник &amp; метод">/);
 assert.equal((doc.html.match(/src="\/research\/images\/map.svg"/g)||[]).length,2);
 assert.doesNotMatch(doc.html,/<figure|<figcaption|\/research\/research\//);
});

test('images cannot use executable or protocol-relative sources or inject attributes through alt/title',()=>{
 const blocked=renderDocument('![JS](javascript:alert%281%29) ![Data](data:image/png;base64,abc) ![Внешний](//evil.test/map.png) ![Почта](mailto:test@example.org) ![Относительный](map.png)');
 assert.doesNotMatch(blocked.html,/<img/);assert.match(blocked.html,/JS/);
 const escaped=renderDocument(`![<img src=x onerror="bad">](https://example.org/map.png '" onload="bad')`);
 assert.match(escaped.html,/<img class="document-image" src="https:\/\/example.org\/map.png" alt="&lt;img src=x onerror=&quot;bad&quot;&gt;" loading="lazy" decoding="async" title="&quot; onload=&quot;bad">/);
 assert.doesNotMatch(escaped.html,/onerror="bad"|onload="bad"|<img src=x/);
});

test('wiki and ordinary material links share the deployment prefix and collect backlinks',()=>{
 const doc=renderDocument('[[population-base|Переписная база]] и [метод](/materials/model-and-observation/#данные). [[draft|Черновик]]', {basePath:'/research/',materialIds:['population-base','model-and-observation']});
 assert.match(doc.html,/href="\/research\/materials\/population-base\/"/);assert.match(doc.html,/href="\/research\/materials\/model-and-observation\/#данные"/);
 assert.deepEqual(doc.links,['population-base','model-and-observation']);assert.deepEqual(doc.unresolvedLinks,['draft']);assert.doesNotMatch(doc.html,/href="[^"]*draft/);
});

test('ready alert and footnote extensions render Russian labels and safe back references',()=>{
 const doc=renderDocument('> [!WARNING]\n> Неизвестное — не ноль.\n\nВывод[^source].\n\n[^source]: [Источник](https://example.org)');
 assert.match(doc.html,/markdown-alert-warning/);assert.match(doc.html,/Ограничение/);assert.match(doc.html,/class="footnotes"/);assert.match(doc.html,/Примечания/);assert.match(doc.html,/href="#doc-footnote-source"/);assert.match(doc.html,/aria-label="Вернуться к упоминанию сноски"/);
 const hostile=renderDocument('Текст[^x"onclick="bad].\n\n[^x"onclick="bad]: Сноска');
 assert.doesNotMatch(hostile.html,/onclick="bad/);
});

test('native disclosures contain Markdown, nested disclosures and fenced examples, not executable HTML',()=>{
 const doc=renderDocument('## Вывод\n\n:::details Как получено <img>\n### Скрытый заголовок\n\n**Метод**\n\n```text\n:::\n```\n\n:::details Уточнение\nОтвет\n:::\n:::\n\n## Дальше');
 assert.equal((doc.html.match(/<details/g)||[]).length,2);assert.match(doc.html,/<summary>Как получено &lt;img&gt;<\/summary>/);assert.match(doc.html,/<strong>Метод<\/strong>/);assert.match(doc.html,/<code class="language-text">:::/);
 assert.deepEqual(doc.headings.map(h=>h.text),['Вывод','Дальше']);
});

test('registered top-level visuals become Astro blocks; nested or unregistered visuals cannot inject components',()=>{
 const doc=renderDocument('До карты.\n\n:::visual population-map\n:::\n\nПосле карты.\n\n:::details Ещё\n:::visual population-map\n:::\n:::\n\n:::visual unknown\n:::',{basePath:'/research/',visualIds:['population-map']});
 assert.deepEqual(doc.blocks.map(b=>b.type),['markdown','visual','markdown']);assert.deepEqual(doc.visualIds,['population-map']);
 assert.match(doc.html,/href="\/research\/visuals\/population-map\/"/);assert.match(doc.html,/Визуализация недоступна: unknown/);
 assert.equal(doc.blocks.filter(b=>b.type==='visual').length,1);
});

test('GFM tables, checklists and code remain usable; directives in code are literal',()=>{
 const doc=renderDocument('| Показатель | Значение |\n|---|---:|\n| Население | 100 |\n\n- [x] Есть источник\n- [ ] Проверить дату\n\n```md\n:::visual population-map\n:::\n```',{visualIds:['population-map']});
 assert.match(doc.html,/<table>/);assert.match(doc.html,/type="checkbox"/);assert.match(doc.html,/<pre><code class="language-md">:::visual/);assert.deepEqual(doc.visualIds,[]);
});
