import type { APIRoute } from 'astro';

// The same five-by-five pixel mark as the atlas header, on a tab-sized surface.
export const GET: APIRoute = () => {
  const pixels = Array.from({length: 25}, (_, index) => {
    const number = index + 1;
    if (number % 4 === 0) return '';
    const opacity = number % 3 === 0 ? ' opacity=".3"' : '';
    return `<rect x="${index % 5 * 10}" y="${Math.floor(index / 5) * 10}" width="8" height="8"${opacity}/>`;
  }).join('');
  return new Response(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><title>Атлас расселения</title><rect width="64" height="64" rx="10" fill="#F4F6FF"/><g fill="#244CFF" transform="translate(8 12) skewY(-8)">${pixels}</g></svg>`, {
    headers: {'Content-Type': 'image/svg+xml; charset=utf-8'},
  });
};
