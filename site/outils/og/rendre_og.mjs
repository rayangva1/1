// Rendu Node du gabarit de l'image de partage (site/outils/og/og-image.html) en PNG 1200 × 630, sans réseau :
// appelé par site/outils/generer_og.py quand Playwright pour Python est absent (Playwright pour Node et Chromium
// déjà installés ; jamais « playwright install » ici). Les polices Google sont servies depuis site/tests/e2e/polices
// (mêmes fichiers, licence OFL) ; toute autre requête externe est refusée.
//
//   node site/outils/og/rendre_og.mjs <sortie.png>
import { chargerPlaywright, lancer, servir, routerPolices, SITE } from '../../tests/e2e/commun.mjs';

const sortie = process.argv[2];
if (!sortie) { console.error('usage : node site/outils/og/rendre_og.mjs <sortie.png>'); process.exit(2); }
const chromium = await chargerPlaywright();
if (!chromium) { console.error('Playwright introuvable (module « playwright », PLAYWRIGHT_MJS ou /opt/node-tools).'); process.exit(3); }

const { srv, url } = await servir(SITE);
const navigateur = await lancer(chromium);
try {
  const ctx = await navigateur.newContext({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await ctx.route(r => !r.href.startsWith(url) && !/^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(r.href), r => r.abort());
  await routerPolices(ctx);
  const page = await ctx.newPage();
  await page.goto(url + 'outils/og/og-image.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const pret = await page.evaluate(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
  if (!pret) throw new Error('image du gabarit non chargée');
  await page.waitForTimeout(300);
  await page.screenshot({ path: sortie, type: 'png', clip: { x: 0, y: 0, width: 1200, height: 630 } });
} finally {
  await navigateur.close();
  srv.close();
}
