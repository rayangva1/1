/*
 * Configuration de la landing. Écrite par site/outils/publication.py ; modifiable à la main (README, § « Sans outil »).
 *
 * webhookUrl  : URL https du webhook n8n « inscription alertes » (workflow décrit dans site/landing/README.md).
 *               Vide ou invalide => formulaire désactivé avec un message clair. Aucun autre service n'est appelé.
 * mode        : "apercu" (bandeau d'aperçu, page non indexée) ou "publication".
 * emailSupport: adresse affichée en cas d'échec d'envoi (vide = message sans adresse).
 */
window.LANDING_CONFIG = {
  mode: "apercu",
  webhookUrl: "",
  emailSupport: "",
  consentVersion: "alertes-v1-2026-10-04",
  timeoutMs: 15000
};
