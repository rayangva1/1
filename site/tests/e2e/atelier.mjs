// Tests navigateur de la landing « Atelier » (Node + Playwright + Chromium, facultatifs) : lancés par
// scripts/run_all_tests.sh quand Node et Playwright sont présents (sinon le lanceur le signale bruyamment).
// Équivalent étendu de site/tests/test_landing_e2e.py (Playwright pour Python, absent de certains postes).
//
//   node site/tests/e2e/atelier.mjs               tous les contrôles (code 1 si un contrôle échoue)
//   node site/tests/e2e/atelier.mjs --disponible  code 0 si Playwright et Chromium sont utilisables, 2 sinon
//   E2E_FILTRE=fil node site/tests/e2e/atelier.mjs   seulement les contrôles dont le nom correspond
//
// Garde-fous : formulaire (désactivé sans webhook, consentement non pré-coché, champ piège, envoi réel intercepté),
// mouvement (pause mémorisée, défilement doux coupé, prefers-reduced-motion), sans JavaScript, clavier, images
// indisponibles (masquées mais lues : A11Y-03), WebP budgété (variante intermédiaire du héro mobile : PERF-01), contraste
// AA des textes posés sur une illustration (images remplacées par du noir et du blanc purs), aucun débordement ni erreur
// console, et les corrections des critiques : bouton du héro au-dessus du pli, aucun renard fantôme pendant la pose,
// aucun mot coupé dans un titre, fil orange jamais sur un texte, hiérarchie des titres, longueur de page bornée, boîte
// du drop légendée comme un symbole (HON-02).
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import zlib from 'node:zlib';
import { chargerPlaywright, lancer, servir, routerPolices, SITE } from './commun.mjs';

const chromium = await chargerPlaywright();
if (process.argv.includes('--disponible')) {
  if (!chromium) process.exit(2);
  try { const b = await lancer(chromium); await b.close(); process.exit(0); } catch (e) { process.exit(2); }
}
if (!chromium) { console.error('Playwright introuvable (module « playwright », PLAYWRIGHT_MJS ou /opt/node-tools).'); process.exit(2); }

const WEBHOOK = 'https://n8n.exemple.invalid/webhook/alertes-inscription';
const PAGES = ['landing/index.html', 'landing/merci.html', 'landing/inscription-confirmee.html', 'landing/desinscription.html',
  'landing/confidentialite.html', 'maquettes/drop.html', 'maquettes/fiche-produit.html'];

function copie(webhook) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atelier-e2e-'));
  fs.cpSync(path.join(SITE, 'landing'), path.join(dir, 'landing'), { recursive: true });
  fs.cpSync(path.join(SITE, 'maquettes'), path.join(dir, 'maquettes'), { recursive: true });
  if (webhook) {
    const f = path.join(dir, 'landing/js/config.js');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('webhookUrl: ""', `webhookUrl: "${webhook}"`));
  }
  return dir;
}

// PNG 8 × 8 d'une couleur unie (pire cas de contraste : image noire ou blanche).
function png(rgb) {
  const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  const crc = (b) => { let x = 0xffffffff; for (const v of b) x = t[(x ^ v) & 0xff] ^ (x >>> 8); return (x ^ 0xffffffff) >>> 0; };
  const bloc = (type, data) => { const l = Buffer.alloc(4); l.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(8, 0); ihdr.writeUInt32BE(8, 4); ihdr[8] = 8; ihdr[9] = 2;
  const ligne = Buffer.concat([Buffer.from([0]), Buffer.from(Array(8).fill(rgb).flat())]);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), bloc('IHDR', ihdr), bloc('IDAT', zlib.deflateSync(Buffer.concat(Array(8).fill(ligne)))), bloc('IEND', Buffer.alloc(0))]);
}

const b = await lancer(chromium);
let ok = 0, ko = 0; const echecs = [];
const FILTRE = process.env.E2E_FILTRE ? new RegExp(process.env.E2E_FILTRE, 'i') : null;  // ex. E2E_FILTRE=contraste
async function test(nom, fn) {
  if (FILTRE && !FILTRE.test(nom)) return;
  try { await fn(); ok++; console.log('OK   ', nom); } catch (e) { ko++; echecs.push(nom); console.log('ÉCHEC', nom, '—', e.message); }
}
function assert(c, m) { if (!c) throw new Error(m || 'assertion'); }

async function ouvrir(url, page = 'landing/index.html?utm_source=Instagram&utm_campaign=lancement', opts = {}, requetes = [], statut = 200) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, ...opts });
  await routerPolices(ctx);
  const p = await ctx.newPage();
  const erreurs = [];
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') erreurs.push(m.text()); });
  p.on('pageerror', e => erreurs.push(e.message));
  await p.route('https://n8n.exemple.invalid/**', r => {
    requetes.push({ m: r.request().method(), corps: new URLSearchParams(r.request().postData() || '') });
    r.fulfill({ status: statut, body: '{"ok": true}', headers: { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' } });
  });
  await p.goto(url + page, { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  return { p, ctx, erreurs };
}

const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };

// ---------------------------------------------------------------- sans webhook
{
  const { srv, url } = await servir(copie(null));

  await test('formulaire désactivé sans webhook (message clair)', async () => {
    const { p, ctx } = await ouvrir(url);
    assert(await p.isDisabled('#lp-envoyer')); assert((await p.innerText('#lp-statut')).includes('pas encore ouvertes'));
    assert(await p.getAttribute('#lp-formulaire', 'data-etat') === 'desactive'); await ctx.close();
  });

  await test('consentement non pré-coché, lien confidentialité, champ piège hors tabulation, champs facultatifs repliés', async () => {
    const { p, ctx } = await ouvrir(url);
    assert(!(await p.isChecked('#lp-consentement'))); assert(await p.$('#lp-consentement-aide a[href="confidentialite.html"]'));
    assert(await p.getAttribute('#lp-site-web', 'tabindex') === '-1');
    assert(!(await p.evaluate("document.querySelector('.lp-preciser').open")), 'champs facultatifs repliés');
    assert(await p.isVisible('#lp-consentement') && await p.isVisible('#lp-email'), 'email et consentement visibles');
    await ctx.close();
  });

  for (const [l, h] of [[390, 844], [768, 1024], [1024, 768], [1440, 900], [1920, 1080]]) {
    await test(`aucun défilement horizontal ni erreur console à ${l}px (landing, pages secondaires, maquettes)`, async () => {
      for (const page of PAGES) {
        const { p, ctx, erreurs } = await ouvrir(url, page, { viewport: { width: l, height: h } });
        await p.waitForTimeout(250);
        assert(await p.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), `${page} déborde à ${l}px`);
        assert(erreurs.length === 0, `${page} : ${erreurs.join(' | ')}`);
        await ctx.close();
      }
    });
  }

  await test('pause des animations : mémorisée, fige le fil et les tirets, coupe le défilement doux (A11Y-01)', async () => {
    const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: 1440, height: 900 } });
    assert(await p.getAttribute('html', 'data-ambiance') === 'atelier');
    await p.waitForFunction("document.documentElement.classList.contains('lp-fil-pret')");
    assert(await p.evaluate("document.querySelectorAll('.lp-fil__trait:not(.lp-fil__branche)').length") === 5, 'cinq tronçons : héro → Braise → drop → Léman → alertes → pied');
    assert(await p.evaluate("document.querySelectorAll('.lp-fil__branche').length") >= 5, 'branches vers les numéros et les filets des photos');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-fil__trait')].some(t => getComputedStyle(t).strokeDasharray !== 'none')"), 'fil dessiné au défilement');
    assert(await p.evaluate("getComputedStyle(document.documentElement).scrollBehavior") === 'smooth', 'défilement doux hors pause');
    assert(await p.getAttribute('#lp-animations', 'aria-pressed') === 'false');
    await p.click('#lp-animations');
    assert(await p.getAttribute('html', 'data-animations') === 'pause'); assert(await p.getAttribute('#lp-animations', 'aria-pressed') === 'true');
    assert(await p.evaluate("getComputedStyle(document.documentElement).scrollBehavior") === 'auto', 'défilement doux coupé par la pause');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-fil__trait')].every(t => getComputedStyle(t).strokeDasharray === 'none')"), 'fil entier en pause');
    assert(await p.evaluate("[...document.querySelectorAll('[data-apparition]')].every(e => getComputedStyle(e).opacity === '1')"), 'tout visible en pause');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-numero__chiffre')].every(e => getComputedStyle(e, '::before').transform === 'none')"), 'tirets entiers en pause');
    assert(await p.evaluate("getComputedStyle(document.querySelector('.lp-hero__img')).animationName") === 'none');
    // Le saut vers une ancre est immédiat en pause.
    await p.click('.lp-nav a[href="#faq"]'); await p.waitForTimeout(60);
    const y = await p.evaluate('scrollY'); assert(y > 5000, `saut immédiat attendu (scrollY ${y})`);
    await p.reload(); assert(await p.getAttribute('html', 'data-animations') === 'pause', 'mémorisé');
    assert(await p.getAttribute('.lp-lien-bouton', 'aria-pressed') === 'true', 'bouton du pied synchronisé');
    await p.click('#lp-animations'); assert(await p.getAttribute('html', 'data-animations') === null);
    await ctx.close();
  });

  await test('prefers-reduced-motion : aucune animation, fil entier, tirets entiers, tout visible', async () => {
    const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    await p.waitForFunction("document.documentElement.classList.contains('lp-fil-pret')");
    assert(await p.evaluate("getComputedStyle(document.querySelector('.lp-hero__img')).animationName") === 'none');
    assert(await p.evaluate("getComputedStyle(document.documentElement).scrollBehavior") === 'auto');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-fil__trait')].every(t => getComputedStyle(t).strokeDasharray === 'none' && t.getTotalLength() > 20)"), 'fil entier');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-fil__trait:not(.lp-fil__branche)')].every(t => t.getTotalLength() > 300)"), 'tronçons complets');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-numero__chiffre')].every(e => getComputedStyle(e, '::before').transform === 'none')"), 'tirets entiers');
    assert(await p.evaluate("[...document.querySelectorAll('[data-apparition]')].every(e => getComputedStyle(e).opacity === '1' && getComputedStyle(e).transform === 'none')"));
    assert(await p.evaluate("getComputedStyle(document.querySelector('.lp-btn')).transitionDuration.split(',').every(d => parseFloat(d) === 0)"), 'aucune transition');
    await ctx.close();
  });

  await test('aucun renard fantôme pendant la pose du héro (DA-03)', async () => {
    for (const [l, h] of [[1440, 900], [390, 844]]) {
      const ctx = await b.newContext({ viewport: { width: l, height: h }, reducedMotion: 'no-preference' });
      await routerPolices(ctx); const p = await ctx.newPage();
      await p.goto(url + 'landing/index.html');
      await p.waitForFunction("document.querySelector('.lp-hero__img').complete && document.querySelector('.lp-hero__img').naturalWidth > 0");
      for (const t of [150, 600]) {
        await p.waitForTimeout(t === 150 ? 150 : 450);
        const etat = await p.evaluate(() => {
          const s = document.querySelector('.lp-hero__image .lp-secours');
          const img = document.querySelector('.lp-hero__img');
          return { visible: getComputedStyle(s).visibility !== 'hidden', opacite: getComputedStyle(img).opacity };
        });
        assert(!etat.visible, `${l}px, ${t} ms : décor de secours visible derrière l'illustration chargée`);
        assert(etat.opacite === '1', `${l}px, ${t} ms : l'illustration se pose en transparence (${etat.opacite})`);
      }
      const keyframes = await p.evaluate(() => [...document.styleSheets].flatMap(s => { try { return [...s.cssRules]; } catch (e) { return []; } })
        .flatMap(r => r.cssRules ? [...r.cssRules] : [r]).filter(r => r.type === 7 && r.name === 'lp-pose').map(r => r.cssText).join(''));
      assert(keyframes && !/opacity/.test(keyframes), 'lp-pose sans opacité');
      await ctx.close();
    }
  });

  await test('images indisponibles : masquées à l’écran, texte alternatif gardé dans l’arbre d’accessibilité (A11Y-03)', async () => {
    for (const [l, h] of [[390, 844], [1440, 900]]) {
      const ctx = await b.newContext({ viewport: { width: l, height: h }, reducedMotion: 'reduce' });
      await routerPolices(ctx); const p = await ctx.newPage();
      await p.route('**/assets/visuels/**', r => r.abort());
      await p.goto(url + 'landing/index.html'); await p.waitForTimeout(400);
      // Toutes les images paresseuses sont demandées (et refusées) : défilement jusqu'au pied de page.
      await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { scrollTo(0, y); await new Promise(r => setTimeout(r, 25)); } });
      await p.waitForTimeout(400);
      for (const pause of [false, true]) {
        if (pause) { await p.click(l < 700 ? '.lp-lien-bouton' : '#lp-animations'); await p.waitForTimeout(100); }
        const etat = await p.evaluate(() => [...document.querySelectorAll('.lp-media img[data-visuel]')].filter(i => i.closest('.lp-media').getClientRects().length > 0).map(i => {
          const s = getComputedStyle(i);
          return { cle: i.dataset.visuel, indispo: i.classList.contains('est-indisponible'), visibilite: s.visibility, affichage: s.display,
            masquee: s.opacity === '0' || s.clipPath !== 'none', alt: i.alt };
        }));
        assert(etat.length >= 9 && etat.every(e => e.indispo), `${l}px : images non marquées indisponibles ${etat.filter(e => !e.indispo).map(e => e.cle)}`);
        // Masquée à l'écran (aucune icône d'image cassée, même en pause où l'opacité est forcée à 1)…
        assert(etat.every(e => e.masquee), `${l}px${pause ? ' (pause)' : ''} : image cassée visible ${etat.filter(e => !e.masquee).map(e => e.cle)}`);
        // … mais jamais retirée de l'arbre d'accessibilité : le texte alternatif reste lu (le secours est aria-hidden).
        assert(etat.every(e => e.visibilite !== 'hidden' && e.affichage !== 'none'), `${l}px : image retirée de l'arbre d'accessibilité`);
      }
      const nommees = await p.getByRole('img', { name: /assis à côté d’une boîte noire vierge|assis à côté d'une boîte noire vierge/ }).count();
      assert(nommees >= 1, `${l}px : texte alternatif du héro absent de l'arbre d'accessibilité`);
      assert(await p.getByRole('img', { name: /symbole du drop/ }).count() === 1, `${l}px : texte alternatif du drop absent`);
      assert(await p.isVisible('.lp-hero .lp-secours'), `${l}px : silhouette de secours absente`);
      assert(await p.getAttribute('.lp-hero .lp-secours', 'aria-hidden') === 'true');
      await ctx.close();
    }
  });

  await test('sans JavaScript : tout visible, ligne CSS du fil, en-tête plein, formulaire désactivé avec message', async () => {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, javaScriptEnabled: false });
    await routerPolices(ctx); const p = await ctx.newPage();
    await p.goto(url + 'landing/index.html', { waitUntil: 'networkidle' });
    assert(await p.evaluate("[...document.querySelectorAll('[data-apparition]')].every(e => getComputedStyle(e).opacity === '1')"));
    assert(await p.evaluate("getComputedStyle(document.querySelector('#mascotte'), '::before').backgroundColor") === 'rgb(242, 106, 27)', 'ligne CSS orange');
    assert(await p.evaluate("getComputedStyle(document.querySelector('.lp-entete')).backgroundColor") !== 'rgba(0, 0, 0, 0)', 'en-tête opaque sans script');
    assert(await p.evaluate("[...document.querySelectorAll('.lp-numero__chiffre')].every(e => getComputedStyle(e, '::before').transform === 'none')"), 'tirets visibles');
    assert(await p.isDisabled('#lp-envoyer')); assert(await p.isVisible('.lp-statut--info'), 'message sans JavaScript visible');
    assert(await p.$('.lp-fil__trait') === null);
    await ctx.close();
  });

  await test('navigation au clavier : évitement, logo, nav, focus charbon, champs repliés atteignables', async () => {
    const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: 1440, height: 900 } });
    await p.keyboard.press('Tab'); assert(await p.evaluate('document.activeElement.className') === 'lp-evitement');
    assert(await p.evaluate("parseFloat(getComputedStyle(document.activeElement).top)") >= 0, 'évitement visible');
    await p.keyboard.press('Tab'); assert(await p.evaluate('document.activeElement.className') === 'lp-logo');
    assert(await p.evaluate("getComputedStyle(document.activeElement).outlineStyle") !== 'none', 'contour');
    assert(await p.evaluate("getComputedStyle(document.activeElement).outlineColor") === 'rgb(29, 27, 25)', 'focus charbon');
    await p.keyboard.press('Tab'); assert(await p.evaluate("document.activeElement.getAttribute('href')") === '#mascotte');
    await p.focus('#lp-email');
    const vus = [];
    for (let i = 0; i < 30 && await p.evaluate('document.activeElement.id') !== 'lp-consentement'; i++) { await p.keyboard.press('Tab'); vus.push(await p.evaluate("document.activeElement.tagName")); }
    assert(await p.evaluate('document.activeElement.id') === 'lp-consentement', 'consentement atteint au clavier');
    assert(vus.includes('SUMMARY'), 'le résumé « Préciser mes alertes » est atteignable');
    await ctx.close();
  });

  await test('lien vers une question fréquente : elle s’ouvre', async () => {
    const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: 1440, height: 900 } });
    await p.click('a[href="#faq-reservation"]'); assert(await p.evaluate("document.getElementById('faq-reservation').open"));
    await ctx.close();
  });

  // PERF-01 : sur mobile en densité 3 (390 et 393 px), la variante intermédiaire de 1180 px, jamais celle de 1520 px.
  for (const [l, h, d, attendu] of [[390, 844, 3, '-1180.webp'], [393, 852, 3, '-1180.webp'], [1440, 900, 2, '-2688.webp'], [1280, 720, 1, '-1280.webp'], [1440, 900, 1, '-1920.webp']]) {
    await test(`image principale en WebP budgétée (${l}×${h} @${d}x → ${attendu}), jamais de PNG`, async () => {
      const images = [];
      const ctx = await b.newContext({ viewport: { width: l, height: h }, deviceScaleFactor: d });
      await routerPolices(ctx); const p = await ctx.newPage();
      p.on('request', r => { if (r.resourceType() === 'image') images.push(r.url()); });
      await p.goto(url + 'landing/index.html', { waitUntil: 'networkidle' });
      const choisie = await p.evaluate("document.querySelector('.lp-hero__img').currentSrc");
      assert(choisie.endsWith(attendu), choisie);
      assert(!images.some(u => u.endsWith('.png') && u.includes('/assets/visuels/')), 'PNG chargée');
      const poids = await p.evaluate("fetch(document.querySelector('.lp-hero__img').currentSrc).then(r => r.arrayBuffer()).then(b => b.byteLength)");
      const largeur = +choisie.split('-').pop().replace('.webp', '');
      assert(poids <= (largeur <= 1600 ? 250 : 450) * 1024, `poids ${poids}`);
      await ctx.close();
    });
  }

  await test('héro ordinateur : bouton visible au-dessus du pli, renard en grand (DA-01)', async () => {
    for (const [l, h] of [[1280, 720], [1366, 768], [1440, 900], [1536, 864], [1920, 1080]]) {
      const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: l, height: h }, reducedMotion: 'reduce' });
      const r = await p.evaluate(() => {
        const btn = document.querySelector('.lp-hero__actions .lp-btn').getBoundingClientRect();
        const img = document.querySelector('.lp-hero__image').getBoundingClientRect();
        const intro = getComputedStyle(document.querySelector('.lp-hero__intro')).color;
        return { bas: btn.bottom, img: img.height, encre: getComputedStyle(document.body).color, intro };
      });
      assert(r.bas <= h, `${l}×${h} : bouton sous le pli (${Math.round(r.bas)})`);
      assert(r.img >= Math.min(640, h - 76) - 1, `${l}×${h} : illustration trop basse (${Math.round(r.img)})`);
      assert(r.intro === r.encre, `${l}×${h} : introduction en ${r.intro}, charbon attendu sur le voile`);
      await ctx.close();
    }
  });

  await test('jour du drop : la boîte ouverte est légendée comme un symbole, sous l’illustration (HON-02)', async () => {
    for (const [l, h] of [[390, 844], [1024, 768], [1440, 900]]) {
      const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: l, height: h }, reducedMotion: 'reduce' });
      const r = await p.evaluate(() => {
        const img = document.querySelector('.lp-drop__image').getBoundingClientRect();
        const lg = document.querySelector('.lp-drop__legende');
        const b = lg.getBoundingClientRect();
        return { haut: b.top - img.bottom, gauche: b.left - img.left, texte: lg.textContent, h: b.height, couleur: getComputedStyle(lg).color };
      });
      assert(r.h > 0 && r.haut >= 0 && r.haut <= 40, `${l}px : légende à ${Math.round(r.haut)} px sous l'illustration`);
      assert(Math.abs(r.gauche) <= 1, `${l}px : légende décalée de l'illustration (${Math.round(r.gauche)} px)`);
      assert(/symbole du drop, pas un produit ouvert/.test(r.texte) && /cartes posées au sol sont vierges/.test(r.texte));
      assert(r.couleur === 'rgb(184, 175, 164)', `${l}px : légende en ${r.couleur} (gris chaud sur charbon attendu)`);
      await ctx.close();
    }
  });

  await test('hiérarchie : le héro domine, chapitres récit et utilitaires distincts (DA-07)', async () => {
    const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: 1440, height: 900 } });
    const t = await p.evaluate(() => ({
      h1: parseFloat(getComputedStyle(document.querySelector('.lp-hero__accroche')).fontSize),
      recit: parseFloat(getComputedStyle(document.querySelector('#titre-mascotte')).fontSize),
      utile: parseFloat(getComputedStyle(document.querySelector('#titre-faq')).fontSize),
    }));
    assert(t.h1 >= 1.6 * t.recit, `h1 ${t.h1} / h2 ${t.recit}`);
    assert(t.recit > t.utile, `récit ${t.recit} / utilitaire ${t.utile}`);
    await ctx.close();
  });

  await test('aucun mot coupé dans un titre (DA-08)', async () => {
    for (const [l, h] of [[390, 844], [900, 800], [1024, 768], [1100, 800], [1280, 800], [1440, 900]]) {
      for (const page of ['landing/index.html', 'landing/merci.html', 'maquettes/drop.html', 'maquettes/fiche-produit.html']) {
        const { p, ctx } = await ouvrir(url, page, { viewport: { width: l, height: h }, reducedMotion: 'reduce' });
        const coupes = await p.evaluate(() => {
          const out = [];
          for (const t of document.querySelectorAll('h1, h2, h3')) {
            const marcheur = document.createTreeWalker(t, NodeFilter.SHOW_TEXT);
            for (let n = marcheur.nextNode(); n; n = marcheur.nextNode()) {
              const re = /\S+/g; let m;
              while ((m = re.exec(n.data))) {
                const r = document.createRange(); r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
                const tops = new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top)));
                if (tops.size > 1) out.push(m[0]);
              }
            }
          }
          return out;
        });
        assert(coupes.length === 0, `${page} à ${l}px : ${coupes.join(', ')}`);
        await ctx.close();
      }
    }
  });

  await test('fil orange : jamais sur un texte, entre dans les filets, passe sous les images pleine largeur (DA-02)', async () => {
    for (const [l, h] of [[1024, 768], [1440, 900], [1920, 1080]]) {
      const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: l, height: h }, reducedMotion: 'reduce' });
      await p.waitForFunction("document.documentElement.classList.contains('lp-fil-pret')");
      await p.waitForTimeout(300);
      const r = await p.evaluate(() => {
        const corps = document.body.getBoundingClientRect();
        const boites = [];
        const marcheur = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: n => n.data.trim() && !n.parentElement.closest('.lp-fil, script, style, noscript, .lp-apercu, .lp-piege, [hidden]') ? 1 : 3 });
        for (let n = marcheur.nextNode(); n; n = marcheur.nextNode()) {
          const rg = document.createRange(); rg.selectNodeContents(n);
          for (const x of rg.getClientRects()) if (x.width > 1 && x.height > 1) boites.push([x.left - corps.left, x.top - corps.top, x.right - corps.left, x.bottom - corps.top, n.data.trim().slice(0, 24)]);
        }
        const touches = [];
        let points = 0;
        for (const t of document.querySelectorAll('.lp-fil__trait')) {
          const L = t.getTotalLength();
          // Points masqués (sous une illustration pleine largeur) : invisibles, donc ignorés.
          const masque = t.closest('g[mask]');
          const caches = masque ? [...document.querySelectorAll(masque.getAttribute('mask').replace(/^url\(|\)$/g, '') + ' rect[fill="black"]')].map(c => [+c.getAttribute('x'), +c.getAttribute('y'), +c.getAttribute('x') + +c.getAttribute('width'), +c.getAttribute('y') + +c.getAttribute('height')]) : [];
          for (let s = 0; s <= L; s += 3) {
            const q = t.getPointAtLength(s); points++;
            if (caches.some(c => q.x >= c[0] && q.x <= c[2] && q.y >= c[1] && q.y <= c[3])) continue;
            const b = boites.find(x => q.x > x[0] + 1 && q.x < x[2] - 1 && q.y > x[1] + 1 && q.y < x[3] - 1);
            if (b) { touches.push(`${Math.round(q.x)},${Math.round(q.y)} « ${b[4]} »`); break; }
          }
        }
        return { touches, points, effiles: document.querySelectorAll('.lp-fil__effile').length };
      });
      assert(r.points > 500, `${l}px : fil trop court (${r.points} points)`);
      assert(r.touches.length === 0, `${l}px : fil sur un texte — ${r.touches.join(' ; ')}`);
      assert(r.effiles >= 6, `${l}px : raccords effilés manquants (${r.effiles})`);
      await ctx.close();
    }
    // Mobile : pas de fil dans la marge (trop proche du texte), seulement des prolongements effilés.
    const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    await p.waitForFunction("document.documentElement.classList.contains('lp-fil-pret')");
    assert(await p.evaluate("document.querySelectorAll('.lp-fil__trait').length") === 0, 'aucun rail sur mobile');
    assert(await p.evaluate("document.querySelectorAll('.lp-fil__effile').length") >= 2, 'prolongements effilés sur mobile');
    await ctx.close();
  });

  await test('page resserrée : longueur bornée (DA-09)', async () => {
    for (const [l, h, max] of [[1440, 900, 11800], [390, 844, 14500]]) {
      const { p, ctx } = await ouvrir(url, 'landing/index.html', { viewport: { width: l, height: h }, reducedMotion: 'reduce' });
      await p.evaluate(() => document.querySelector('.lp-apercu')?.remove());
      const hauteur = await p.evaluate('document.documentElement.scrollHeight');
      assert(hauteur <= max, `${l}px : ${hauteur} px (au plus ${max})`);
      await ctx.close();
    }
  });

  // Contraste : chaque visuel remplacé par du noir puis du blanc purs ; mesure sous chaque texte posé sur une illustration.
  const SELECTEURS = ['.lp-hero .lp-surtitre', '.lp-hero__seo', '.lp-hero__accroche .lp-ligne', '.lp-hero__accroche .lp-accent',
    '.lp-hero__intro', '.lp-hero__actions .lp-lien-fleche', '.lp-nav a', '#titre-mascotte', '#titre-alertes', '.lp-alertes__entete .lp-numero',
    '.lp-alertes__entete .lp-intro', '#titre-promesse', '.lp-geneve .lp-numero', '.lp-geneve__intro'];
  for (const [nom, rgb] of [['noire', [0, 0, 0]], ['blanche', [255, 255, 255]]]) {
    for (const [l, h] of [[1920, 1080], [1440, 900], [1280, 800], [1024, 768], [390, 844]]) {
      await test(`textes posés sur une illustration AA sur image ${nom} (${l}px)`, async () => {
        const ctx = await b.newContext({ viewport: { width: l, height: h }, reducedMotion: 'reduce' });
        await routerPolices(ctx);
        await ctx.route('**/assets/visuels/**', r => r.fulfill({ status: 200, contentType: 'image/png', body: png(rgb) }));
        const p = await ctx.newPage(); await p.goto(url + 'landing/index.html', { waitUntil: 'networkidle' });
        await p.evaluate(() => document.querySelector('.lp-apercu')?.remove());
        const insuffisants = [];
        for (const s of SELECTEURS) for (const el of await p.$$(s)) {
          if (!(await el.isVisible())) continue;
          await el.scrollIntoViewIfNeeded();
          await p.waitForTimeout(30);
          const info = await el.evaluate(e => {
            const r = document.createRange(); r.selectNodeContents(e); const rs = [...r.getClientRects()].filter(x => x.width > 2 && x.height > 2);
            const x0 = Math.max(0, Math.min(...rs.map(x => x.left))), y0 = Math.max(0, Math.min(...rs.map(x => x.top))); const cs = getComputedStyle(e);
            return { x: x0, y: y0, w: Math.min(innerWidth, Math.max(...rs.map(x => x.right))) - x0, h: Math.min(innerHeight, Math.max(...rs.map(x => x.bottom))) - y0,
              couleur: cs.color, taille: parseFloat(cs.fontSize), graisse: parseInt(cs.fontWeight), texte: e.textContent.trim().slice(0, 24) };
          });
          const masque = await p.addStyleTag({ content: 'body *, body *::after { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; text-decoration-color: transparent !important; } .lp-fil, .lp-lien-fleche::after { display: none !important; } .lp-numero__chiffre::before { visibility: hidden !important; }' });
          const buf = await p.screenshot({ clip: { x: info.x, y: info.y, width: Math.max(1, info.w), height: Math.max(1, info.h) } });
          await masque.evaluate(t => t.remove());
          const fonds = await p.evaluate(async (b64) => {
            const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
            const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const x = c.getContext('2d'); x.drawImage(img, 0, 0);
            const d = x.getImageData(0, 0, c.width, c.height).data; const out = []; for (let i = 0; i < d.length; i += 4) out.push([d[i], d[i + 1], d[i + 2]]); return out;
          }, buf.toString('base64'));
          const ls = fonds.map(lum).sort((a, z) => a - z);
          const t = info.couleur.match(/[\d.]+/g).slice(0, 3).map(Number); const lt = lum(t);
          const fond = lt < 0.2 ? ls[Math.floor(ls.length * 0.01)] : ls[Math.floor(ls.length * 0.99) - 1];
          const ratio = (Math.max(lt, fond) + 0.05) / (Math.min(lt, fond) + 0.05);
          const seuil = info.taille >= 24 || (info.taille >= 18.66 && info.graisse >= 700) ? 3 : 4.5;
          if (ratio < seuil) insuffisants.push(`${s} « ${info.texte} » ${ratio.toFixed(2)} < ${seuil}`);
        }
        assert(insuffisants.length === 0, insuffisants.join(' ; '));
        await ctx.close();
      });
    }
  }
  srv.close();
}

// ---------------------------------------------------------------- avec webhook (intercepté)
{
  const { srv, url } = await servir(copie(WEBHOOK));
  await test('inscription envoyée (champs facultatifs dépliés) et confirmation affichée', async () => {
    const req = []; const { p, ctx } = await ouvrir(url, undefined, {}, req);
    assert(await p.isEnabled('#lp-envoyer'));
    await p.fill('#lp-email', 'lea@exemple.ch'); await p.fill('#lp-prenom', 'Léa');
    await p.click('.lp-preciser > summary');
    await p.check('input[value="etb"]'); await p.check('input[value="displays"]'); await p.check('input[value="30-60"]');
    await p.selectOption('#lp-canton', 'GE'); await p.check('#lp-consentement'); await p.click('#lp-envoyer');
    await p.waitForSelector('.lp-confirmation');
    assert(req.length === 1 && req[0].m === 'POST'); const c = req[0].corps;
    assert(c.get('email') === 'lea@exemple.ch' && c.get('prenom') === 'Léa' && c.get('formats') === 'displays,etb' && c.get('budget') === '30-60' && c.get('canton') === 'GE');
    assert(c.get('consentement') === 'oui' && c.get('utm_source') === 'instagram' && c.get('utm_campaign') === 'lancement' && c.get('source') === 'landing');
    assert(c.get('consentement_texte').startsWith("J'accepte de recevoir l'alerte d'ouverture")); assert(!c.has('site_web'));
    assert((await p.evaluate('document.activeElement.textContent')).startsWith('Merci')); await ctx.close();
  });
  await test('inscription sans déplier les champs facultatifs', async () => {
    const req = []; const { p, ctx } = await ouvrir(url, undefined, {}, req);
    await p.fill('#lp-email', 'lea@exemple.ch'); await p.check('#lp-consentement'); await p.click('#lp-envoyer');
    await p.waitForSelector('.lp-confirmation');
    assert(req.length === 1 && req[0].corps.get('email') === 'lea@exemple.ch' && !req[0].corps.get('formats')); await ctx.close();
  });
  await test('erreurs de saisie annoncées, focus sur le premier champ, aucun envoi', async () => {
    const req = []; const { p, ctx } = await ouvrir(url, undefined, {}, req);
    await p.fill('#lp-email', 'pas-un-email'); await p.click('#lp-envoyer');
    assert(await p.getAttribute('#lp-email', 'aria-invalid') === 'true' && await p.getAttribute('#lp-consentement', 'aria-invalid') === 'true');
    assert(await p.isVisible('#lp-email-erreur') && await p.isVisible('#lp-consentement-erreur'));
    assert(await p.evaluate('document.activeElement.id') === 'lp-email'); assert(req.length === 0); await ctx.close();
  });
  await test('échec du webhook annoncé et bouton réactivé', async () => {
    const req = []; const { p, ctx } = await ouvrir(url, undefined, {}, req, 500);
    await p.fill('#lp-email', 'lea@exemple.ch'); await p.check('#lp-consentement'); await p.click('#lp-envoyer');
    await p.waitForSelector('.lp-statut--erreur'); assert((await p.innerText('#lp-statut')).includes("n'a pas pu être envoyée")); assert(await p.isEnabled('#lp-envoyer')); await ctx.close();
  });
  await test('champ piège : succès simulé sans envoi', async () => {
    const req = []; const { p, ctx } = await ouvrir(url, undefined, {}, req);
    await p.fill('#lp-email', 'robot@exemple.ch'); await p.check('#lp-consentement');
    await p.evaluate("document.getElementById('lp-site-web').value = 'http://spam.exemple'"); await p.click('#lp-envoyer');
    await p.waitForSelector('.lp-confirmation'); assert(req.length === 0); await ctx.close();
  });
  srv.close();
}

await b.close();
console.log(`\n${ok} contrôles réussis, ${ko} échoués${ko ? ' : ' + echecs.join(' ; ') : ''}`);
process.exit(ko ? 1 : 0);
