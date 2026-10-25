import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({site:'https://zakbu.github.io',base:process.env.PUBLIC_BASE_PATH || '/',output:'static',devToolbar:{enabled:false},integrations:[react()],vite:{plugins:[tailwindcss()]}});
