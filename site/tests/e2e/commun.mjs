// Outils communs des tests navigateur (Node + Playwright, facultatifs) : serveur statique local, polices servies en
// local (aucun appel réseau), chargement de Playwright depuis l'installation disponible.
//
// Playwright : module « playwright » résolu normalement, sinon le chemin de PLAYWRIGHT_MJS, sinon l'installation
// partagée /opt/node-tools (environnement de l'équipe). Chromium doit déjà être installé (jamais « playwright install »
// ici) ; CHROMIUM peut désigner un exécutable précis.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

export const ICI = path.dirname(new URL(import.meta.url).pathname);
export const SITE = path.resolve(ICI, '..', '..');
const POLICES = path.join(ICI, 'polices');
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.json': 'application/json', '.woff2': 'font/woff2',
};

export async function chargerPlaywright() {
  const essais = ['playwright', process.env.PLAYWRIGHT_MJS, '/opt/node-tools/node_modules/playwright/index.mjs'].filter(Boolean);
  for (const nom of essais) {
    try {
      const module = await import(nom);
      return module.chromium || (module.default && module.default.chromium);
    } catch (e) {
      /* essai suivant */
    }
  }
  return null;
}

export async function lancer(chromium) {
  return process.env.CHROMIUM ? chromium.launch({ executablePath: process.env.CHROMIUM }) : chromium.launch();
}

export function servir(racine) {
  const srv = http.createServer((q, r) => {
    let f = path.join(racine, decodeURIComponent(q.url.split('?')[0]));
    if (!f.startsWith(racine)) { r.writeHead(403); return r.end(); }
    if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
    if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
    r.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
    fs.createReadStream(f).pipe(r);
  });
  return new Promise(res => srv.listen(0, '127.0.0.1', () => res({ srv, url: `http://127.0.0.1:${srv.address().port}/` })));
}

/** Google Fonts servies depuis polices/ (mêmes fichiers, licence OFL) : rendu fidèle sans réseau. */
export async function routerPolices(ctx) {
  const css = fs.readFileSync(path.join(POLICES, 'fonts.css'), 'utf8');
  await ctx.route('https://fonts.googleapis.com/**', r => r.fulfill({ status: 200, contentType: 'text/css', body: css, headers: { 'access-control-allow-origin': '*' } }));
  await ctx.route('https://fonts.gstatic.com/**', r => {
    const nom = new URL(r.request().url()).pathname.slice(1).replace(/\//g, '_');
    const f = path.join(POLICES, nom);
    if (!fs.existsSync(f)) return r.abort();
    r.fulfill({ status: 200, contentType: 'font/woff2', body: fs.readFileSync(f), headers: { 'access-control-allow-origin': '*' } });
  });
}
