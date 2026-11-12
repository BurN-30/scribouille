/* =========================================================================
   Doublure de passerelle : A RETIRER A LA FUSION avec la branche « moteur ».

   La branche « moteur » apporte espace_inventaire, espace_liberer,
   effacement_apercu, effacement_executer, moteur_etat et usage_instantane
   (contrat dans web/espace.js). Tant qu'elles manquent, `appelPasserelle`
   (web/app.js) se rabat sur ces stand-ins :

     - mode reel (par defaut) : l'inventaire vient de la mesure existante
       (`mesurer_stockage`, trois postes, rien de liberable) ; liberer et
       effacer refusent ; memoire et moteur ne sont pas affiches ;
     - mode fictif (`window.DOUBLURE_FICTIVE = true`, pour les essais a
       l'ecran) : un inventaire plausible, liberation et effacement simules,
       rien n'est touche sur le disque.

   Pour retirer : supprimer ce fichier et sa balise <script> dans index.html.
   Rien d'autre n'y fait reference.
   ========================================================================= */

(function () {
  'use strict';

  const fictif = () => !!window.DOUBLURE_FICTIVE;
  const Go = 1024 ** 3;
  const Mo = 1024 ** 2;

  let attente = null;
  // La mesure existante repond par un rappel de Python : on l'attend ici.
  window.onStockage = function (mesure) {
    if (attente) { const r = attente; attente = null; r(mesure); }
  };
  function mesurer() {
    return new Promise((resoudre) => {
      attente = resoudre;
      window.pywebview.api.mesurer_stockage();
      setTimeout(() => { if (attente === resoudre) { attente = null; resoudre(null); } }, 60000);
    });
  }

  const inventaireFictif = {
    postes: [
      { cle: 'modeles', libelle: 'Modèles de transcription', octets: 4.7 * Go, liberable: 3.1 * Go,
        description: 'large-v3 (3,1 Go) n’est pas utilisé par le réglage en service.',
        chemins: ['%LOCALAPPDATA%\\Scribouille\\modeles'] },
      { cle: 'locuteurs', libelle: 'Séparation des locuteurs', octets: 3.6 * Go, liberable: 0,
        description: 'Moteur optionnel installé.', chemins: ['%LOCALAPPDATA%\\Scribouille\\extensions'] },
      { cle: 'cache_openvino', libelle: 'Cache du moteur Intel', octets: 410 * Mo, liberable: 410 * Mo,
        description: 'Recréé au premier usage, au prix d’une minute de préparation.',
        chemins: ['%LOCALAPPDATA%\\Scribouille\\cache-openvino'] },
      { cle: 'programme', libelle: 'Programme', octets: 257 * Mo, liberable: 0,
        description: 'Fichiers de l’application.', chemins: ['%LOCALAPPDATA%\\Programs\\Scribouille'] },
      { cle: 'mesures', libelle: 'Mesures et campagnes', octets: 85 * Mo, liberable: 85 * Mo,
        description: 'Rapports du banc d’essai et des campagnes.', chemins: ['%LOCALAPPDATA%\\Scribouille\\campagnes'] },
      { cle: 'journaux', libelle: 'Journaux', octets: 12 * Mo, liberable: 11 * Mo,
        description: 'Les sept derniers jours sont gardés.', chemins: ['%LOCALAPPDATA%\\Scribouille\\logs'] },
      { cle: 'reglages', libelle: 'Réglages et vocabulaire', octets: 46 * 1024, liberable: 0,
        description: 'Configuration, vocabulaire, gabarit pour l’IA.', chemins: ['%LOCALAPPDATA%\\Scribouille'] },
    ],
    transcriptions_octets: 3.4 * Mo,
  };
  const total = (inv) => inv.postes.reduce((s, p) => s + p.octets, 0);

  window.DOUBLURE_PASSERELLE = {
    async espace_inventaire() {
      if (fictif()) {
        const copie = JSON.parse(JSON.stringify(inventaireFictif));
        copie.total_octets = total(copie);
        return copie;
      }
      const m = await mesurer();
      if (!m || m.erreur) return null;
      return {
        postes: (m.postes || []).map((p) => ({
          cle: p.cle, libelle: p.libelle, octets: p.octets, liberable: 0,
          description: p.detail, chemins: [p.chemin],
        })),
        total_octets: m.total,
        transcriptions_octets: null,
      };
    },
    async espace_liberer(cles) {
      if (!fictif()) return { ok: false, code: 'indisponible' };
      let libere = 0;
      inventaireFictif.postes.forEach((p) => {
        if (cles.includes(p.cle)) { libere += p.liberable; p.octets -= p.liberable; p.liberable = 0; }
      });
      return { ok: true, octets_liberes: libere };
    },
    async effacement_apercu(garder) {
      const inv = await this.espace_inventaire();
      if (!inv) return { ok: false, code: 'echec' };
      const elements = inv.postes.map((p) => ({ libelle: p.libelle, chemin: (p.chemins || [])[0] || '', octets: p.octets }));
      if (!garder) elements.push({ libelle: 'Transcriptions', chemin: '%USERPROFILE%\\Documents\\Transcriptions', octets: inv.transcriptions_octets || 0 });
      return {
        ok: true, jeton: 'doublure', elements: elements,
        conserves: garder ? [{ libelle: 'Transcriptions', chemin: '%USERPROFILE%\\Documents\\Transcriptions' }] : [],
      };
    },
    async effacement_executer() {
      return fictif() ? { ok: true } : { ok: false, code: 'indisponible' };
    },
    async moteur_etat() {
      return fictif() ? { etat: 'pret', modele: 'large-v3-turbo' } : null;
    },
    async usage_instantane() {
      if (!fictif()) return null;
      return {
        fenetre: { memoire_octets: 168 * Mo + Math.random() * 4 * Mo, processeur_pct: Math.random() * 2 },
        moteur: { memoire_octets: 1.9 * Go, processeur_pct: 0 },
      };
    },
  };
})();
