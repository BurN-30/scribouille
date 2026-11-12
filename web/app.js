/* =========================================================================
   Scribouille : logique d'interface

   Le Python appelle les fonctions globales onXxx() definies plus bas.
   L'interface appelle Python via pywebview.api.*

   Quatre ecrans, un seul visible : les reunions (depot, file, transcriptions),
   la relecture (web/relecture.js), les reglages, le vocabulaire. L'espace disque
   et l'effacement sont dans web/espace.js.

   Aucun libelle en dur ici : tout passe par t() et tn(), definis dans
   web/langues.js, jumeau de app/langues.py. Voir outils/verifier_traductions.py.
   ========================================================================= */

'use strict';

const etat = {
  config: {},
  presets: [],
  fichiers: new Map(),   // identifiant -> donnees de la ligne
  historique: [],
  diarisation: { disponible: false, jeton_present: false, guide: {}, extension: {} },
  recents: new Map(),          // transcriptions finies pendant la session : chemin -> details
  extensionEnCours: false,   // installation de la separation des locuteurs en cours
  vitesse: {},               // moteur OpenVINO, reglage de vitesse, banc d'essai
  rythme: {},                // vitesse maximale, equilibre ou discret, adaptation
  materiel: null,
  avertissements: [],
  ovEnCours: false,          // installation d'OpenVINO en cours
  bancEnCours: false,        // banc d'essai en cours
  modeles: { dossier: '', presets: [] },
  versionInstallee: false,
  enCours: false,
  passage: [],               // identifiants lances ensemble, pour « fichier 2 sur 4 »
  apercuChemin: null,
  importChemin: null,
  reprises: [],
  surveillance: { actif: false, dossier: '', probleme: '' },
  maj: null,              // version plus recente annoncee par le bandeau
  version: '',            // version installee, affichee dans l'aide
  majEnCours: false,      // verification demandee a la main, en vol
  vue: 'principale',
  section: 'transcription',
  accueil: false,         // premier lancement : fenetre d'accueil ouverte
  pret: false,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function ech(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function icone(nom, classe) {
  return `<svg class="icone ${classe || ''}"><use href="#${nom}"></use></svg>`;
}

/* Appel d'une fonction de passerelle (pywebview.api), en promesse. */
function appelPasserelle(nom, ...args) {
  const api = window.pywebview && window.pywebview.api;
  if (api && typeof api[nom] === 'function') return Promise.resolve(api[nom](...args));
  return Promise.reject(new Error(nom));
}

/* ------------------------------------------------------------ Demarrage */

window.addEventListener('pywebviewready', async () => {
  try {
    const donnees = await pywebview.api.etat_initial();
    initialiser(donnees);
    // Moment où la fenêtre devient utilisable, noté au journal (mesure du démarrage).
    pywebview.api.interface_prete();
    const accueil = await appelPasserelle('accueil').catch(() => null);
    if (accueil && accueil.premier_lancement) ouvrirAccueil(donnees.proposition);
  } catch (e) {
    journaliser('erreur', t('ui.journal.etat_perdu'));
    console.error(e);
  }
});

function initialiser(d, silencieux) {
  etat.config = d.config || {};
  etat.presets = d.presets || [];
  etat.diarisation = d.diarisation || etat.diarisation;
  etat.modeles = d.modeles || etat.modeles;
  etat.reprises = d.reprises || [];
  etat.surveillance = d.surveillance || etat.surveillance;
  etat.versionInstallee = !!d.version_installee;
  etat.vitesse = d.vitesse || etat.vitesse;
  etat.rythme = d.rythme || etat.rythme;
  etat.materiel = d.materiel || etat.materiel;

  // Python fait autorite sur la langue : il l'a detectee au premier lancement
  // et l'a rangee dans la configuration. La langue provisoire posee au
  // chargement du document n'a servi qu'a eviter une fenetre vide.
  if (etat.config.langue_interface) definirLangue(etat.config.langue_interface);
  traduirePage();
  remplirVitesses();

  etat.version = String(d.version || '');
  $('#version').textContent = 'v' + d.version;
  $('#aide-maj-version').textContent = etat.version;
  appliquerTheme(etat.config.theme || 'auto');
  appliquerZoom(etat.config.zoom || 1);

  dessinerMateriel(d.materiel);
  dessinerPresets();
  remplirModelesAvances(d.modeles_avances || []);
  appliquerConfig();
  majGlossaire(d.glossaire ? d.glossaire.resume : null);
  majCorrections(d.corrections || {});
  majCompteurVocabulaire();
  majDiarisation();
  majVitesse();
  majRythme();
  afficherProposition(d.proposition || null);
  majModeles();
  majSurveillance();
  majQualiteLangue();
  majApercuMotif();
  dessinerReprises();
  dessinerFile();
  dessinerHistorique();
  afficherAvertissements(d.avertissements || []);

  if (!silencieux) {
    if (!d.ffmpeg) journaliser('erreur', t('ui.journal.ffmpeg'));
  }

  etat.pret = true;
  majBoutons();
  pywebview.api.charger_historique();
}

/* Materiel relu en arriere-plan apres l'ouverture (premier lancement, station
   d'accueil, pilote change) : seules les parties qui en dependent sont
   redessinees, le reste de l'ecran ne bouge pas. */
function onMateriel(d) {
  if (!d) return;
  etat.presets = d.presets || etat.presets;
  etat.vitesse = d.vitesse || etat.vitesse;
  etat.rythme = d.rythme || etat.rythme;
  etat.materiel = d.materiel || etat.materiel;
  dessinerMateriel(d.materiel);
  dessinerPresets();
  majVitesse();
  majRythme();
  afficherAvertissements(d.avertissements || []);
  if (d.proposition) afficherProposition(d.proposition);
  if (etat.accueil) dessinerAccueil(d.proposition || null, true);
}

/* --------------------------------------------------- Langue de l'interface

   Sans rapport avec la langue parlee : celle-ci pilote le moteur de
   transcription, celle-la l'affichage. Le changement est immediat, sans
   redemarrage : les libelles du HTML sont reposes ici, et l'etat complet est
   redemande a Python, qui renvoie ses propres textes dans la nouvelle langue. */

async function changerLangueInterface(code) {
  definirLangue(code);
  traduirePage();
  etat.config.langue_interface = langueCourante();
  try {
    await pywebview.api.sauver_config({ langue_interface: langueCourante() });
    const d = await pywebview.api.etat_initial();
    initialiser(d, true);
  } catch (e) {
    console.error(e);
  }
  if (typeof relectureLangueChangee === 'function') relectureLangueChangee();
}

/* ------------------------------------------------------------- Ecrans */

const VUES = ['principale', 'relecture', 'reglages', 'vocabulaire'];

/* Un seul ecran visible. Le pied (file, lancer, arreter) n'appartient qu'a
   l'ecran des reunions ; ailleurs, une pastille de l'en-tete dit qu'une
   transcription tourne et y ramene. */
function afficherVue(nom, options) {
  const opts = options || {};
  const avant = etat.vue;
  if (avant === 'relecture' && nom !== 'relecture' && typeof quitterRelecture === 'function') quitterRelecture();
  etat.vue = nom;
  document.documentElement.dataset.vue = nom;
  VUES.forEach((v) => { $('#vue-' + v).hidden = v !== nom; });
  $('#pied').hidden = nom !== 'principale';
  $$('.bouton-nav').forEach((b) => {
    if (b.dataset.vue === nom) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  majActivite();
  if (nom === 'reglages') afficherSection(opts.section || etat.section, !opts.focus);
  if (nom === 'vocabulaire') chargerVocabulaire();
  if (opts.focus !== false) {
    const cible = nom === 'principale' ? (opts.retourFocus || $('#zone-depot'))
      : $('#vue-' + nom + ' h1');
    if (cible) setTimeout(() => cible.focus({ preventScroll: true }), 0);
  }
}

function retourPrincipale() {
  const origine = etat.vue === 'relecture' && typeof lect !== 'undefined' ? lect.chemin : '';
  const bouton = origine
    ? Array.from(document.querySelectorAll('#vue-principale [data-lire]')).find((b) => b.dataset.lire === origine)
    : null;
  afficherVue('principale', bouton ? { retourFocus: bouton } : {});
}

/* Reglages : trois familles (usage courant, avance, mesures et diagnostic),
   une section a la fois. */
function afficherSection(nom, garderFocus) {
  etat.section = nom;
  $$('.reglages-nav [role=tab]').forEach((b) => {
    const choisi = b.dataset.section === nom;
    b.setAttribute('aria-selected', choisi ? 'true' : 'false');
    b.tabIndex = choisi ? 0 : -1;
  });
  $$('.reglages-section').forEach((s) => { s.hidden = s.dataset.section !== nom; });
  $('#vue-reglages').scrollTop = 0;
  if (nom === 'espace' && typeof ouvrirEspace === 'function') ouvrirEspace();
  if (nom !== 'espace' && typeof quitterEspace === 'function') quitterEspace();
  if (nom === 'journal') { const j = $('#journal-contenu'); j.scrollTop = j.scrollHeight; }
  if (!garderFocus) {
    const tab = $(`.reglages-nav [data-section="${nom}"]`);
    if (tab && document.activeElement && document.activeElement.closest('.reglages-nav')) tab.focus();
  }
}

function ouvrirReglages(section) {
  afficherVue('reglages', { section: section || etat.section });
}

/* Pastille d'activite : la transcription en cours, vue depuis un autre ecran. */
function majActivite() {
  const visible = etat.enCours && etat.vue !== 'principale';
  const dansRelecture = etat.vue === 'relecture';
  $('#indic-activite').hidden = !visible || dansRelecture;
  $('#rl-activite').hidden = !visible || !dansRelecture;
  if (!visible) return;
  const actif = Array.from(etat.fichiers.values()).find((f) => ETATS_ACTIFS.includes(f.etat));
  const prog = actif ? progressionAffichee(actif) : null;
  const texte = !actif ? t('ui.etat.demarrage')
    : (prog.indetermine ? t('ui.activite.phase', { phase: actif.phase || '' })
      : t('ui.activite.texte', { phase: actif.phase || '', pct: prog.pct }));
  $('#indic-activite-texte').textContent = texte;
  $('#rl-activite-texte').textContent = texte;
}

/* -------------------------------------------------------------- Materiel */

function dessinerMateriel(mat) {
  if (!mat) return;
  $('#materiel-resume').textContent = mat.resume;

  const lignes = [];
  const ajout = (cle, valeur, classe) =>
    lignes.push(`<div class="materiel-ligne"><span class="cle">${ech(cle)}</span>
      <span class="valeur ${classe || ''}">${ech(valeur)}</span></div>`);

  ajout(t('ui.materiel.processeur'), mat.cpu_nom);
  ajout(t('ui.materiel.coeurs'), t('ui.materiel.detail_coeurs', {
    physiques: mat.coeurs_physiques ? t('ui.materiel.physiques', { n: mat.coeurs_physiques }) : '',
    logiques: mat.coeurs_logiques,
    fils: mat.fils_calcul,
  }));
  ajout(t('ui.materiel.memoire'), mat.ram_libre_go
    ? t('ui.materiel.ram_libre', { total: nb(mat.ram_go, 1), libre: nb(mat.ram_libre_go, 1) })
    : t('ui.materiel.ram', { total: nb(mat.ram_go, 1) }));
  (mat.gpus || []).forEach((g) => {
    ajout(t('ui.materiel.gpu'), g.memoire_mo
      ? t('ui.materiel.gpu_memoire', { nom: g.nom, go: nb(g.memoire_mo / 1024, 1) })
      : g.nom);
    if (g.note) ajout('', g.note, g.accelere ? '' : 'mention-honnete');
  });
  (mat.npus || []).forEach((n) => {
    ajout(t('ui.materiel.npu'), n.nom);
    if (n.note) ajout('', n.note, 'mention-honnete');
  });
  if (!(mat.gpus || []).length) ajout(t('ui.materiel.gpu'), t('ui.materiel.sans_gpu'));
  ajout(t('ui.materiel.calcul'), mat.peripherique === 'cuda'
    ? t('ui.materiel.calcul_cuda')
    : t('ui.materiel.calcul_cpu'));
  ajout(t('ui.materiel.systeme'), mat.systeme);
  $('#materiel-detail').innerHTML = lignes.join('');
}

/* --------------------------------------------------------------- Presets */

function dessinerPresets() {
  $('#presets').setAttribute('role', 'radiogroup');
  $('#presets').setAttribute('aria-label', t('ui.section.qualite'));
  $('#presets').innerHTML = etat.presets.map((p) => `
    <button class="preset" role="radio" data-preset="${ech(p.cle)}" aria-checked="false">
      <span class="titre"><span class="marqueur"></span>${ech(p.nom)}</span>
      <span class="desc">${ech(p.resume)}</span>
      <span class="chiffres">${ech(t('ui.preset.chiffres', {
        modele: p.modele, duree: p.pour_une_heure, poids: p.telechargement,
      }))}</span>
    </button>`).join('');
  $('#segments-qualite').innerHTML = etat.presets.map((p) => `
    <button class="segment" role="radio" data-preset="${ech(p.cle)}" aria-checked="false">${ech(p.nom)}</button>`).join('');

  $$('[data-preset]').forEach((b) => {
    b.addEventListener('click', () => choisirPreset(b.dataset.preset));
  });
  brancherRadios('#presets');
  brancherRadios('#segments-qualite');
  majPresetActif();
}

function choisirPreset(cle) {
  if (cle === etat.config.preset) return;
  etat.config.preset = cle;
  majPresetActif();
  // Le rythme annonce la duree du preset choisi : tout est recalcule.
  rafraichirRythme({ preset: cle });
}

function majPresetActif() {
  $$('[data-preset]').forEach((b) => {
    const choisi = b.dataset.preset === etat.config.preset;
    b.setAttribute('aria-checked', choisi ? 'true' : 'false');
    b.tabIndex = choisi ? 0 : -1;
  });
}

/* Groupe de boutons radio : fleches pour passer d'un choix a l'autre. */
function brancherRadios(selecteur) {
  const groupe = $(selecteur);
  if (!groupe || groupe.dataset.radios) return;
  groupe.dataset.radios = '1';
  groupe.addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    const boutons = Array.from(groupe.querySelectorAll('[role=radio]'));
    const i = boutons.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const pas = (e.key === 'ArrowLeft' || e.key === 'ArrowUp') ? -1 : 1;
    const suivant = boutons[(i + pas + boutons.length) % boutons.length];
    suivant.focus();
    suivant.click();
  });
}

function remplirModelesAvances(modeles) {
  const sel = $('#modele-avance');
  const choisi = sel.value;
  sel.innerHTML = `<option value="">${ech(t('ui.preset.modele_du_preset'))}</option>`
    + modeles.map((m) => `<option value="${ech(m.cle)}">${ech(t('ui.preset.option_modele', {
      nom: m.nom, taille: m.taille, qualite: String(m.qualite || '').toLowerCase(),
    }))}</option>`).join('');
  if (choisi) sel.value = choisi;
}

/* -------------------------------------------- Bandeau de lancement

   Les deux ou trois choix utiles a chaque lancement, et UNE duree : celle du
   preset choisi au rythme en service, la meme que partout ailleurs. */

function majLancement() {
  const r = etat.rythme || {};
  const choisi = r.choisi || 'vitesse';
  $$('#segments-rythme .segment').forEach((b) => {
    const actif = b.dataset.rythme === choisi;
    b.setAttribute('aria-checked', actif ? 'true' : 'false');
    b.tabIndex = actif ? 0 : -1;
  });
  const duree = (r.pour_une_heure || {})[choisi] || '';
  // Sans duree connue, rien plutot qu'un « -- ». Le moteur OpenVINO ne donne
  // pas la confiance des mots : c'est dit ici, pour les deux qualites.
  $('#lancement-duree').innerHTML = (duree ? t('ui.lance.duree', { duree: `<strong>${ech(duree)}</strong>` })
    + (r.auto && choisi !== 'vitesse' ? ech(t('ui.lance.auto')) : '') : '')
    + (moteurSansConfiance() ? ` <span class="lancement-moteur">${ech(t('ui.lance.sans_confiance'))}</span>` : '');

  // Voix : seulement si la separation est installee et repond.
  const ext = (etat.diarisation || {}).extension || {};
  const posee = !!ext.installee && !!etat.diarisation.disponible;
  $('#choix-voix').hidden = !posee;
  if (posee) {
    const actif = !!etat.config.diarisation;
    $('#opt-voix-lancement').checked = actif;
    $('#voix-lancement-etat').textContent = actif ? t('ui.lance.voix_oui') : t('ui.lance.voix_non');
  }
}

/* Le reglage du poste fait tourner les deux qualites sur OpenVINO : aucun mot
   douteux ne sera signale en relecture. */
function moteurSansConfiance() {
  const r = (etat.config || {}).reglage_machine || {};
  return r.moteur === 'openvino';
}

/* Avertissements : sur l'ecran des reunions, seulement ce qui change le
   prochain lancement (telechargement a venir, memoire). Les notes sur le
   materiel lui-meme (carte graphique non exploitee) vont dans « Poste », et
   la separation non installee est dite par le choix « Voix ». */
function afficherAvertissements(liste) {
  etat.avertissements = liste || [];
  const cartes = ((etat.materiel || {}).gpus || []).map((g) => g.nom).filter(Boolean);
  const materiel = (m) => cartes.some((nom) => m.includes(nom));
  const ext = (etat.diarisation || {}).extension || {};
  const voixAbsente = etat.config.diarisation && !(ext.installee && etat.diarisation.disponible);
  let utiles = etat.avertissements.filter((m) => !materiel(m));
  if (voixAbsente && utiles.length) utiles = utiles.slice(0, -1);
  $('#lancement-avis').innerHTML = utiles.map(encartAttention).join('');
  $('#avertissements').innerHTML = etat.avertissements.filter((m) => !materiel(m)).map(encartAttention).join('');
  $('#avertissements-poste').innerHTML = etat.avertissements.filter(materiel).map(encartAttention).join('');
}

/* -------------------------------------------------------------- Reglages */

function appliquerConfig() {
  const c = etat.config;
  $('#langue').value = c.langue || 'fr';
  $('#langue-interface').value = langueCourante();
  $('#choix-theme').value = c.theme || 'auto';
  $('#dossier-sortie').value = c.dossier_sortie || '';
  const f = c.formats || {};
  $('#fmt-txt').checked = f.txt !== false;
  $('#fmt-srt').checked = !!f.srt;
  $('#fmt-vtt').checked = !!f.vtt;
  $('#fmt-horodatage').checked = !!f.horodatage;
  $('#opt-glossaire').checked = c.utiliser_glossaire !== false;
  $('#opt-corrections').checked = c.appliquer_corrections !== false;
  $('#opt-compagnon').checked = c.compagnon_confiance !== false;
  $('#opt-apprises').checked = c.corrections_apprises !== false;
  $('#opt-sauvegarde').checked = c.sauvegarde_progressive !== false;
  $('#motif-sortie').value = c.motif_sortie || '';
  $('#opt-surveillance').checked = !!c.surveillance;
  $('#dossier-surveille').value = c.dossier_surveille || '';
  $('#bloc-surveillance').style.display = c.surveillance ? 'block' : 'none';
  $('#opt-maj').checked = !!c.maj_verifier;
  $('#opt-barre-taches').checked = c.barre_taches !== false;
  $('#opt-prevenir-fin').checked = c.prevenir_fin !== false;
  $('#opt-diarisation').checked = !!c.diarisation;
  $('#nb-locuteurs').value = String(c.nb_locuteurs || 0);
  $('#opt-avance').checked = !!c.mode_avance;
  $('#modele-avance').value = c.modele_avance || '';
  $('#beam').value = c.beam_size || '';
  $('#opt-contexte').checked = c.condition_on_previous_text !== false;
  $('#opt-salle').checked = !!c.filtres_salle;
  $('#opt-processeur').checked = !!c.forcer_processeur;
  $('#bloc-avance').style.display = c.mode_avance ? 'block' : 'none';
  $('#bloc-locuteurs').style.display = c.diarisation ? 'block' : 'none';
  majPresetActif();
}

async function enregistrer(partiel) {
  Object.assign(etat.config, partiel);
  try {
    const retour = await pywebview.api.sauver_config(partiel);
    if (retour) {
      etat.config = retour.config;
      afficherAvertissements(retour.avertissements || []);
    }
  } catch (e) { console.error(e); }
}

function majGlossaire(resume) {
  if (!resume) return;
  const el = $('#etat-glossaire');
  if (!resume.nb_termes) {
    el.textContent = t('ui.voc.aucun_terme');
  } else {
    el.textContent = tn('ui.voc.termes', resume.nb_retenus)
      + (resume.tronque ? t('ui.voc.tronque', { total: resume.nb_termes }) : '');
  }
}

function majCorrections(donnees) {
  const el = $('#etat-corrections');
  const compte = donnees.nb || 0;
  el.textContent = compte ? tn('ui.voc.regles', compte) : t('ui.voc.aucune_regle');
  if (donnees.erreurs && donnees.erreurs.length) {
    el.textContent += tn('ui.voc.lignes_erreur', donnees.erreurs.length);
  }
}

/* Panneau « Locuteurs » : trois etats successifs, un seul visible a la fois.

   1. les composants ne sont pas la, un bouton les installe ;
   2. l'installation tourne, progression et annulation ;
   3. les composants sont la, on retrouve la bascule, le jeton, et le retrait.

   Le jeton Hugging Face reste une etape distincte, posee apres : ce sont deux
   choses differentes, un telechargement de plusieurs Go et un compte gratuit. */

function majDiarisation() {
  const d = etat.diarisation;
  const ext = d.extension || {};
  const enCours = !!etat.extensionEnCours;
  const posee = !!ext.installee && !!d.disponible;

  $('#ext-absente').style.display = (!posee && !enCours) ? 'block' : 'none';
  $('#ext-en-cours').style.display = enCours ? 'block' : 'none';
  $('#ext-installee').style.display = posee ? 'block' : 'none';
  majLancement();

  if (!posee) {
    // Chiffres annonces avant tout clic : ce qui transite, ce qu'il faut de
    // place, et ce qui reste. On ne telecharge jamais en aveugle.
    $('#ext-chiffres').textContent = chiffresExtension(ext);
    // Dossier present mais composants qui ne se chargent pas : telechargement
    // interrompu, ou fichiers abimes. On le dit, plutot que de proposer une
    // installation sans expliquer pourquoi elle revient.
    if (ext.installee && !enCours && d.indisponibilite) {
      $('#ext-retour').innerHTML = encartAttention(d.indisponibilite);
    }
    return;
  }

  const el = $('#etat-diarisation');
  const bascule = $('#opt-diarisation');
  bascule.disabled = false;
  if (!d.jeton_present) {
    el.textContent = t('ui.loc.jeton_a_saisir');
    $('#libelle-jeton').textContent = t('ui.loc.configurer');
  } else {
    el.textContent = bascule.checked ? t('ui.loc.active') : t('ui.loc.disponible');
    $('#libelle-jeton').textContent = t('ui.loc.modifier_jeton');
  }
  $('#bloc-locuteurs').style.display = bascule.checked ? 'block' : 'none';

  // Le retrait n'a de sens que pour la version installee : depuis les sources,
  // les paquets vivent dans le « .venv », qui ne nous appartient pas.
  const retirable = !!ext.mode_installe;
  $('#btn-retirer-locuteurs').style.display = retirable ? '' : 'none';
  $('#libelle-retirer-locuteurs').textContent = t('ui.ext.retirer', {
    taille: nombreLocal(ext.taille_go || 0, 1),
  });
  $('#ext-note-installee').textContent = retirable
    ? t('ui.ext.note_installee', { variante: t('ui.ext.variante_' + (ext.variante || 'cpu')) })
    : t('ui.ext.note_sources');
}

/* Ce que couterait l'installation, dit une seule fois et de la meme facon
   partout : sur le bouton et dans la modale de confirmation. */
function chiffresExtension(ext) {
  return t('ui.ext.chiffres', {
    telechargement: nombreLocal(ext.telechargement_go || 0.8, 1),
    installee: nombreLocal(ext.taille_attendue_go || 3.6, 1),
    requis: nombreLocal(ext.espace_requis_go || 6, 0),
    libre: nombreLocal(ext.espace_libre_go || 0, 0),
  });
}

/* Nombre decimal au separateur de la langue d'interface, comme le fait Python. */
function nombreLocal(valeur, decimales) {
  return Number(valeur || 0).toFixed(decimales).replace('.', t('format.decimal'));
}

/* Taille lisible, jumelle de langues.octets cote Python (puissances de 1024). */
function formaterOctets(octets) {
  const n = Math.max(0, Number(octets) || 0);
  const unites = [['unite.go', 1024 ** 3], ['unite.mo', 1024 ** 2], ['unite.ko', 1024]];
  for (const [cle, taille] of unites) {
    if (n >= taille) {
      const valeur = n / taille;
      return nombreLocal(valeur, valeur >= 100 || cle === 'unite.ko' ? 0 : 1) + ' ' + t(cle);
    }
  }
  return tn('unite.octets', Math.round(n));
}

/* Le jeton est demande a part, et seulement une fois les composants poses :
   c'est une etape distincte, pas la suite mecanique du telechargement. */
function ouvrirModaleJeton() {
  const d = etat.diarisation;
  $('#etat-diarisation-modale').innerHTML = d.disponible ? '' :
    encartAttention(d.indisponibilite);
  $('#etapes-jeton').innerHTML = (d.guide.etapes || []).map((e) => `<li>${ech(e)}</li>`).join('');
  $('#retour-jeton').innerHTML = '';
  $('#champ-jeton').value = '';
  ouvrirModale('#modale-jeton');
}

/* ------------------------------------ Installation de la separation des locuteurs */

function ouvrirModaleExtension() {
  const ext = (etat.diarisation || {}).extension || {};
  $('#ext-modale-chiffres').textContent = chiffresExtension(ext);
  const assez = (ext.espace_libre_go || 0) >= (ext.espace_requis_go || 6);
  $('#ext-modale-alerte').innerHTML = assez ? '' : encartAttention(t('ui.ext.place_manquante'));
  $('#btn-confirmer-extension').disabled = !assez;
  ouvrirModale('#modale-extension');
}

async function lancerInstallationLocuteurs() {
  fermerModale($('#modale-extension'));
  $('#ext-retour').innerHTML = '';
  $('#ext-message').textContent = t('ui.ext.demarrage');
  $('#ext-detail').textContent = '';
  $('#ext-barre').style.width = '0%';
  etat.extensionEnCours = true;
  majDiarisation();

  const r = await pywebview.api.installer_locuteurs();
  if (!r || !r.ok) {
    etat.extensionEnCours = false;
    majDiarisation();
    $('#ext-retour').innerHTML = encartAttention((r && r.message) || t('ui.ext.echec_lancement'));
  }
}

/* Appelee par Python a chaque etape du processus de fond.

   Deux lignes, deux roles : la grande etape en cours ne bouge presque pas,
   le detail defile. */
function onExtensionLocuteurs(evenement) {
  if (!etat.extensionEnCours) return;
  switch (evenement.phase) {
    case 'debut':
    case 'lot':
      $('#ext-message').textContent = evenement.message || '';
      break;
    case 'paquet':
      $('#ext-detail').textContent = evenement.message || '';
      break;
    case 'octets':
      $('#ext-barre').style.width = Math.max(0, Math.min(100, evenement.pct || 0)) + '%';
      $('#ext-detail').textContent = evenement.message || '';
      break;
    case 'pose':
      $('#ext-barre').style.width = '100%';
      $('#ext-message').textContent = evenement.message || '';
      $('#ext-detail').textContent = '';
      break;
    case 'detail':
      // Ligne d'erreur de pip : elle part au journal, elle n'a rien a faire
      // dans un panneau de reglages.
      if (evenement.message) journaliser('attention', evenement.message);
      break;
    default:
      break;
  }
}

/* Appelee par Python quand le processus de fond se termine, quelle qu'en soit
   l'issue : reussite, echec, ou annulation demandee par l'utilisateur. */
function onFinExtensionLocuteurs(bilan) {
  etat.extensionEnCours = false;
  if (bilan.extension) etat.diarisation.extension = bilan.extension;
  if (bilan.etat === 'installee') {
    etat.diarisation.disponible = !!bilan.chaud;
    etat.diarisation.indisponibilite = bilan.chaud ? '' : bilan.message;
    $('#ext-retour').innerHTML = encartSucces(bilan.message);
    journaliser('ok', bilan.message);
    majDiarisation();
    // Le jeton est l'etape suivante, et elle n'a rien a voir avec les paquets :
    // on l'enchaine seulement quand les composants repondent deja.
    if (bilan.chaud && !etat.diarisation.jeton_present) ouvrirModaleJeton();
    return;
  }
  $('#ext-retour').innerHTML = bilan.etat === 'annulee'
    ? encartInfo(bilan.message) : encartAttention(bilan.message);
  journaliser(bilan.etat === 'annulee' ? 'info' : 'erreur', bilan.message);
  majDiarisation();
}

/* ------------------------------------------- Vitesse de cette machine

   Deux outils, aucun automatisme : le moteur OpenVINO (option, pour les puces
   Intel) s'installe sur demande, et le banc d'essai mesure plusieurs facons
   de transcrire sur ce poste. Son conseil ne s'applique que sur un clic. */

function majVitesse() {
  const v = etat.vitesse || {};
  const ov = v.openvino || {};
  $('#vitesse-reglage').textContent = t('ui.vitesse.actuel', { reglage: v.resume_reglage || '--' });
  const effet = v.effet || {};
  $('#vitesse-alerte').innerHTML = effet.plantage
    ? encartAttention(t('ui.vitesse.plantage', { peripherique: effet.plantage }))
    : (effet.indisponible ? encartAttention(t('ui.vitesse.indisponible')) : '');

  $('#ov-bloc').style.display = (ov.utile || ov.installee) ? 'block' : 'none';
  const enCours = !!etat.ovEnCours;
  $('#ov-en-cours').style.display = enCours ? 'block' : 'none';
  $('#btn-installer-openvino').style.display = (!ov.installee && !enCours) ? '' : 'none';
  $('#btn-retirer-openvino').style.display = (ov.installee && ov.mode_installe && !enCours) ? '' : 'none';
  $('#libelle-installer-openvino').textContent = t('ui.ov.installer', {
    taille: nombreLocal((ov.telechargement_go || 0.09) * 1000, 0),
  });
  if (ov.installee) {
    const noms = (ov.peripheriques || []).map((p) => t('ui.ov.peripherique.' + p.toLowerCase()));
    $('#ov-etat').textContent = t('ui.ov.installe', {
      version: ov.version || '?', peripheriques: noms.join(', ') || '--',
    });
  } else {
    $('#ov-etat').textContent = ov.hors_ligne
      ? tn('ui.ov.absent_hors_ligne', ov.hors_ligne)
      : t('ui.ov.absent');
  }

  const manquants = v.manquants || [];
  $('#banc-manquants').textContent = manquants.length
    ? t('ui.banc.manquants', { liste: manquants.map((m) => `${m.modele} (${m.taille})`).join(', ') })
    : t('ui.banc.rien_a_telecharger');
  $('#opt-banc-telecharger').disabled = !manquants.length;
  $('#ligne-banc-npu').style.display =
    (v.npu && (ov.peripheriques || []).indexOf('NPU') >= 0) ? '' : 'none';

  majComparaison();
  const banc = !!v.banc_en_cours || !!etat.bancEnCours;
  $('#banc-en-cours').style.display = banc ? 'block' : 'none';
  $('#btn-lancer-banc').style.display = banc ? 'none' : '';
  $('#btn-reglage-auto').style.display =
    (v.reglage && Object.keys(v.reglage).length) ? '' : 'none';
  if (v.conseil && Object.keys(v.conseil).length && !banc) {
    $('#banc-resultat').style.display = 'block';
    $('#banc-conseil').textContent = t('ui.banc.conseil', { reglage: v.resume_conseil || '--' });
    if (!$('#banc-rapport').value && v.rapport) $('#banc-rapport').value = v.rapport;
    // Conseil deja en service : rien a appliquer de plus.
    const r = v.reglage || {};
    const c = v.conseil || {};
    const pareil = (k) => (r[k] === undefined ? null : r[k]) === (c[k] === undefined ? null : c[k]);
    $('#btn-appliquer-banc').disabled = !!Object.keys(r).length
      && ['moteur', 'peripherique', 'fils', 'lot'].every(pareil);
  }
}

async function installerOpenvino() {
  $('#ov-retour').innerHTML = '';
  $('#ov-message').textContent = t('ui.ext.demarrage');
  $('#ov-detail').textContent = '';
  $('#ov-barre').style.width = '0%';
  etat.ovEnCours = true;
  majVitesse();
  const r = await pywebview.api.installer_openvino();
  if (!r || !r.ok) {
    etat.ovEnCours = false;
    majVitesse();
    $('#ov-retour').innerHTML = encartAttention((r && r.message) || t('ui.ext.echec_lancement'));
  }
}

function onExtensionOpenvino(evenement) {
  if (!etat.ovEnCours) return;
  if (evenement.phase === 'octets') {
    $('#ov-barre').style.width = Math.max(0, Math.min(100, evenement.pct || 0)) + '%';
    $('#ov-detail').textContent = evenement.message || '';
  } else if (evenement.phase === 'paquet') {
    $('#ov-detail').textContent = evenement.message || '';
  } else if (evenement.phase === 'detail') {
    if (evenement.message) journaliser('attention', evenement.message);
  } else if (evenement.message) {
    $('#ov-message').textContent = evenement.message;
  }
}

function onFinExtensionOpenvino(bilan) {
  etat.ovEnCours = false;
  if (bilan.vitesse) etat.vitesse = bilan.vitesse;
  const ok = bilan.etat === 'installee';
  $('#ov-retour').innerHTML = ok ? encartSucces(bilan.message)
    : (bilan.etat === 'annulee' ? encartInfo(bilan.message) : encartAttention(bilan.message));
  journaliser(ok ? 'ok' : (bilan.etat === 'annulee' ? 'info' : 'erreur'), bilan.message);
  majVitesse();
}

async function lancerBanc() {
  $('#banc-retour').innerHTML = '';
  $('#banc-message').textContent = t('ui.banc.demarrage');
  $('#banc-barre').style.width = '0%';
  $('#banc-resultat').style.display = 'none';
  etat.bancEnCours = true;
  majVitesse();
  const r = await pywebview.api.lancer_banc(
    $('#opt-banc-telecharger').checked, $('#opt-banc-npu').checked);
  if (!r || !r.ok) {
    etat.bancEnCours = false;
    majVitesse();
    $('#banc-retour').innerHTML = encartAttention((r && r.message) || t('ui.ext.echec_lancement'));
    return;
  }
  majBoutons();
}

function onBanc(etape) {
  $('#banc-message').textContent = etape.message || '';
  $('#banc-barre').style.width = Math.max(0, Math.min(100, etape.pct || 0)) + '%';
}

function onFinBanc(bilan) {
  etat.bancEnCours = false;
  if (bilan.vitesse) etat.vitesse = bilan.vitesse;
  if (!bilan.ok) {
    $('#banc-retour').innerHTML = encartAttention(bilan.message || '');
    journaliser('erreur', bilan.message || '');
    majVitesse();
    majBoutons();
    return;
  }
  $('#banc-rapport').value = bilan.rapport || '';
  $('#banc-resultat').style.display = 'block';
  $('#btn-appliquer-banc').disabled = !(bilan.conseil && Object.keys(bilan.conseil).length);
  if (bilan.fichier) {
    $('#banc-retour').innerHTML = encartInfo(t('ui.banc.fichier', { fichier: bilan.fichier }));
  }
  journaliser(bilan.annule ? 'attention' : 'ok',
    t(bilan.annule ? 'ui.banc.arrete' : 'ui.banc.fini'));
  majVitesse();
  majBoutons();
}

/* Comparaison des deux moteurs sur un enregistrement de l'utilisateur.
   Possible seulement quand OpenVINO est installe. La page cote a cote reste
   sur le poste ; le rapport de chiffres peut etre copie. */

const comparaison = { fichier: '', reference: '', page: '', enCours: false };

function majComparaison() {
  const ov = (etat.vitesse || {}).openvino || {};
  $('#comp-bloc').style.display = ov.installee ? 'block' : 'none';
  $('#comp-indisponible').hidden = !!ov.installee;
  $('#comp-en-cours').style.display = comparaison.enCours ? 'block' : 'none';
  $('#btn-comp-lancer').style.display = comparaison.enCours ? 'none' : '';
  $('#btn-comp-lancer').disabled = !comparaison.fichier || etat.enCours || etat.bancEnCours;
}

function onFichierComparaison(choix) {
  if (choix.nature === 'reference') {
    comparaison.reference = choix.chemin;
    $('#comp-reference-nom').textContent = choix.nom;
  } else {
    comparaison.fichier = choix.chemin;
    $('#comp-fichier-nom').textContent = choix.nom;
  }
  majComparaison();
}

async function lancerComparaison() {
  $('#comp-retour').innerHTML = '';
  $('#comp-message').textContent = t('ui.comp.demarrage');
  $('#comp-barre').style.width = '0%';
  $('#comp-resultat').style.display = 'none';
  comparaison.enCours = true;
  majComparaison();
  const r = await pywebview.api.lancer_comparaison(
    comparaison.fichier, comparaison.reference, $('#comp-debut').value,
    parseFloat($('#comp-duree').value) || 10);
  if (!r || !r.ok) {
    comparaison.enCours = false;
    majComparaison();
    $('#comp-retour').innerHTML = encartAttention((r && r.message) || t('ui.ext.echec_lancement'));
  }
}

function onComparaison(etape) {
  $('#comp-message').textContent = etape.message || '';
  $('#comp-barre').style.width = Math.max(0, Math.min(100, etape.pct || 0)) + '%';
}

function onFinComparaison(bilan) {
  comparaison.enCours = false;
  majComparaison();
  if (bilan.message && !bilan.rapport) {
    $('#comp-retour').innerHTML = encartAttention(bilan.message);
    journaliser('erreur', bilan.message);
    return;
  }
  comparaison.page = bilan.page || '';
  $('#comp-rapport').value = bilan.rapport || '';
  $('#comp-resultat').style.display = 'block';
  $('#btn-comp-ouvrir').disabled = !comparaison.page;
  if (bilan.fichier) {
    $('#comp-retour').innerHTML = encartInfo(t('ui.comp.fichiers', { fichier: bilan.fichier }));
  }
  journaliser(bilan.annule ? 'attention' : 'ok', t(bilan.annule ? 'ui.comp.arrete' : 'ui.comp.fini'));
}

/* ------------------------------------------------ Rythme de la transcription

   Trois positions (vitesse maximale par defaut) et l'adaptation automatique.
   Le choix vaut pour la prochaine file : les fils et les lots se fixent au
   chargement du modele. Voir app/rythme.py. */

function majRythme() {
  const r = etat.rythme || {};
  const choisi = r.choisi || 'vitesse';
  $$('#bloc-rythme .rythme').forEach((b) => {
    const actif = b.dataset.rythme === choisi;
    b.setAttribute('aria-checked', actif ? 'true' : 'false');
    b.tabIndex = actif ? 0 : -1;
  });
  const duree = (r.pour_une_heure || {})[choisi] || '--';
  $('#rythme-desc').textContent = t('ui.rythme.desc.' + choisi, { duree });
  const auto = $('#opt-rythme-auto');
  auto.checked = !!r.auto && choisi !== 'vitesse';
  auto.disabled = choisi === 'vitesse';
  $('#rythme-auto-aide').textContent = t(choisi === 'vitesse' ? 'ui.rythme.auto_inutile' : 'ui.rythme.auto_aide');
  const notes = [];
  if (r.auto && r.batterie && choisi !== 'vitesse') notes.push(encartInfo(t('ui.rythme.batterie')));
  if (etat.enCours) notes.push(encartInfo(t('ui.rythme.prochaine')));
  $('#rythme-retour').innerHTML = notes.join('');
  majLancement();
}

/* Preset ou rythme change : toutes les durees affichees en dependent (cartes,
   rythme, bandeau, file). Python les recalcule d'un bloc, avec la meme
   fonction, pour qu'aucune ne reste en retard sur les autres. */
async function rafraichirRythme(partiel) {
  await enregistrer(partiel);
  try {
    const d = await pywebview.api.etat_initial();
    initialiser(d, true);
  } catch (e) { console.error(e); }
  rafraichirEstimations();
}

/* Reglage propose pour ce poste : au premier lancement (accueil), ou sur
   demande depuis Reglages, Poste. Une seule recommandation, dite ici. */

function afficherProposition(p) {
  const bloc = $('#bloc-proposition');
  if (!p) { bloc.hidden = true; return; }
  $('#proposition-phrase').textContent = p.phrase || '';
  $('#proposition-rythme').textContent = t('ui.proposition.rythme', {
    rythme: t('ui.rythme.' + (p.rythme || 'equilibre')),
  });
  const notes = (p.notes || []).map((n) => encartInfo(n));
  if (p.deja) notes.unshift(encartSucces(t('ui.proposition.deja')));
  $('#proposition-notes').innerHTML = notes.join('');
  $('#btn-proposition-appliquer').hidden = !!p.deja;
  bloc.hidden = false;
}

async function reconnaitrePoste() {
  const bouton = $('#btn-reconnaitre');
  bouton.disabled = true;
  $('#vitesse-alerte').innerHTML = encartInfo(t('ui.proposition.recherche'));
  try {
    const p = await pywebview.api.proposer_reglage();
    majVitesse();
    afficherProposition(p);
  } catch (e) {
    console.error(e);
    $('#vitesse-alerte').innerHTML = encartAttention(t('ui.ext.echec_lancement'));
  }
  bouton.disabled = false;
}

async function appliquerProposition() {
  const r = await pywebview.api.appliquer_proposition();
  journaliser(r.ok ? 'ok' : 'attention', r.message);
  if (!r.ok) { setEtat(r.message, 'attention'); return false; }
  afficherProposition(null);
  const d = await pywebview.api.etat_initial();
  initialiser(d, true);
  rafraichirEstimations();   // la file aussi suit le nouveau reglage
  setEtat(t('ui.proposition.appliquee'), 'succes');
  return true;
}

async function appliquerBanc() {
  const r = await pywebview.api.appliquer_conseil_banc();
  $('#banc-retour').innerHTML = r.ok ? encartSucces(r.message) : encartAttention(r.message);
  journaliser(r.ok ? 'ok' : 'attention', r.message);
  if (r.ok) {
    const d = await pywebview.api.etat_initial();
    initialiser(d, true);
    rafraichirEstimations();
  }
}

async function revenirReglageAuto() {
  const r = await pywebview.api.revenir_reglage_automatique();
  journaliser('info', r.message);
  const d = await pywebview.api.etat_initial();
  initialiser(d, true);
  rafraichirEstimations();
  $('#vitesse-alerte').innerHTML = encartInfo(r.message);
}

/* ---------------------------------------------------- Premier lancement

   Court : ce que fait l'application, le reglage propose pour ce poste en une
   phrase, et commencer. Le reste (raisons, notes) est dans Reglages, Poste. */

function ouvrirAccueil(proposition) {
  etat.accueil = true;
  dessinerAccueil(proposition || null, false);
  ouvrirModale('#modale-accueil');
  // Le materiel est relu en arriere-plan : sans nouvelles apres quelques
  // secondes, le reglage en service convient.
  setTimeout(() => { if (etat.accueil && !etat.propositionAccueil) dessinerAccueil(null, true); }, 15000);
}

function dessinerAccueil(p, definitif) {
  const zone = $('#accueil-reglage');
  etat.propositionAccueil = p;
  const appliquer = $('#btn-accueil-appliquer');
  const garder = $('#btn-accueil-garder');
  if (p && !p.deja) {
    // Une phrase : le reglage et sa duree. Les raisons sont dans Reglages, Poste ;
    // ce que l'on y perd, s'il y a lieu, est dit ici.
    const phrase = String(p.phrase || '').split(/ ?: /)[0].replace(/[.\s]+$/, '') + '.';
    const perte = (p.notes || []).find((n) => /confiance|confidence/i.test(n));
    const rythme = p.rythme ? t('ui.proposition.rythme', { rythme: t('ui.rythme.' + p.rythme) }) : '';
    zone.innerHTML = `<span class="titre-section">${ech(t('ui.proposition.titre'))}</span>
      <div>${ech(phrase)}</div>${rythme ? `<div>${ech(rythme)}</div>` : ''}${perte ? `<div class="perte">${ech(perte)}</div>` : ''}`;
    appliquer.hidden = false;
    appliquer.textContent = t('ui.accueil.appliquer');
    // « Garder » dit ce qui est garde, avec sa duree.
    const actuel = (etat.presets.find((x) => x.cle === etat.config.preset) || {}).nom || '';
    const dureeActuelle = ((etat.rythme || {}).pour_une_heure || {})[(etat.rythme || {}).choisi || 'vitesse'] || '';
    garder.textContent = actuel && dureeActuelle
      ? t('ui.accueil.garder_nomme', { preset: actuel, duree: dureeActuelle }) : t('ui.accueil.garder');
    if (document.activeElement && document.activeElement.classList.contains('modale')) appliquer.focus();
    return;
  }
  if (!definitif) {
    zone.innerHTML = `<span class="titre-section">${ech(t('ui.proposition.titre'))}</span>
      <div>${ech(t('ui.proposition.recherche'))}</div>`;
    appliquer.hidden = true;
    garder.textContent = t('ui.accueil.commencer');
    return;
  }
  const preset = (etat.presets.find((x) => x.cle === etat.config.preset) || {}).nom || '';
  const duree = ((etat.rythme || {}).pour_une_heure || {})[(etat.rythme || {}).choisi || 'vitesse'] || '';
  zone.innerHTML = `<span class="titre-section">${ech(t('ui.accueil.reglage_actuel'))}</span>
    <div>${ech(duree ? t('ui.accueil.convient', { preset: preset, duree: duree }) : preset)}</div>`;
  appliquer.hidden = true;
  garder.textContent = t('ui.accueil.commencer');
}

async function fermerAccueil(appliquer) {
  const p = etat.propositionAccueil;
  if (appliquer && p && !p.deja) {
    const ok = await appliquerProposition();
    if (!ok) return;
  } else if (p && !p.deja) {
    pywebview.api.ecarter_proposition();
  }
  etat.accueil = false;
  fermerModale($('#modale-accueil'));
  $('#zone-depot').focus();
}

/* ------------------------------------------------------ Dossier des modeles */

function majModeles() {
  const m = etat.modeles || {};
  const liste = m.presets || [];
  const absents = liste.filter((p) => !p.present);

  $('#etat-modeles').textContent = liste.length
    ? (absents.length === 0
        ? t('ui.modeles.tous', { occupe: m.occupe })
        : t('ui.modeles.partiels', {
            present: liste.length - absents.length, total: liste.length, occupe: m.occupe,
          }))
    : t('ui.modeles.occupe', { occupe: m.occupe });

  const chemin = $('#chemin-modeles');
  chemin.textContent = m.dossier || '--';
  chemin.title = m.dossier || '';

  const tailles = liste.map((p) => p.nom + ' ' + p.taille).join(', ');
  // Un modele incomplet, laisse par un telechargement coupe, n'est pas compte
  // comme present : on le dit, et on dit aussi que l'application s'en charge.
  const incomplets = m.incomplets || [];
  $('#aide-modeles').textContent = t('ui.modeles.aide', {
    tailles: tailles ? t('ui.modeles.tailles', { liste: tailles }) : '',
    libre: m.libre || '--',
  }) + (incomplets.length
    ? ' ' + t('ui.modeles.incomplets', { liste: incomplets.join(', ') })
    : '');
}

function onDossierModeles(retour) {
  if (!retour) return;
  if (retour.modeles) etat.modeles = retour.modeles;
  majModeles();
  $('#retour-modeles').innerHTML = retour.ok
    ? encartSucces(retour.message) : encartAttention(retour.message);
  if (retour.ok) {
    journaliser('ok', retour.message);
    if (retour.avertissements) afficherAvertissements(retour.avertissements);
    setTimeout(() => { $('#retour-modeles').innerHTML = ''; }, 8000);
  }
}
window.onDossierModeles = onDossierModeles;

/* ------------------------------------------------- Qualite selon la langue

   Une mention d'une ligne sous le selecteur, rien de plus. Les paliers sont
   cales sur les taux d'erreur publies par OpenAI pour large-v3 sur le jeu
   multilingue FLEURS, regroupes en trois classes. */

const QUALITE_LANGUES = {
  es: 'excellente', it: 'excellente', pt: 'excellente', en: 'excellente',
  de: 'excellente', fr: 'excellente',
  nl: 'bonne', pl: 'bonne', ro: 'bonne',
  ar: 'variable',
};

function majQualiteLangue() {
  const code = $('#langue').value;
  const zone = $('#qualite-langue');
  if (code === 'auto') {
    zone.textContent = t('ui.qualite.auto');
    return;
  }
  const palier = QUALITE_LANGUES[code];
  zone.textContent = palier ? t('ui.qualite.' + palier) : '';
}

/* ------------------------------------------- Nom des fichiers produits */

let minuteurMotif = null;

async function majApercuMotif() {
  const zone = $('#apercu-motif');
  try {
    const r = await pywebview.api.apercu_motif($('#motif-sortie').value);
    zone.classList.toggle('probleme', !r.ok || !!r.message);
    if (!r.ok) { zone.textContent = r.message; return; }
    zone.textContent = r.message
      ? r.message
      : t(r.defaut ? 'ui.motif.defaut' : 'ui.motif.exemple', { exemple: r.exemple });
  } catch (e) {
    zone.textContent = '';
  }
}

async function enregistrerMotif() {
  const r = await pywebview.api.enregistrer_motif($('#motif-sortie').value);
  if (!r.ok) {
    $('#apercu-motif').classList.add('probleme');
    $('#apercu-motif').textContent = r.message;
    return;
  }
  etat.config.motif_sortie = r.motif;
  $('#motif-sortie').value = r.motif;
  majApercuMotif();
  journaliser('ok', t('ui.motif.enregistre', { motif: r.motif || '{date}-{nom}' }));
}

/* ------------------------------------------------------ Dossier surveille */

function majSurveillance() {
  const s = etat.surveillance || {};
  const indicateur = $('#indic-surveillance');
  const etiquette = $('#etat-surveillance');

  $('#bloc-surveillance').style.display = s.actif ? 'block' : 'none';
  if (!s.actif) {
    indicateur.style.display = 'none';
    etiquette.textContent = t('ui.veille.coupee');
    return;
  }
  indicateur.style.display = '';
  indicateur.classList.toggle('defaut', !!s.probleme);
  indicateur.title = s.probleme || t('ui.veille.titre', { dossier: s.dossier || '' });
  $('#indic-surveillance-texte').textContent = s.probleme
    ? t('ui.veille.indic_defaut') : t('ui.veille.indic_actif');
  etiquette.textContent = s.probleme
    ? t('ui.veille.etat_defaut')
    : t('ui.veille.etat_actif', { n: s.intervalle || 10 });
}

function retourSurveillance(r) {
  if (!r) return;
  if (r.dossier !== undefined) etat.surveillance = r;
  majSurveillance();
  $('#retour-surveillance').innerHTML = r.message
    ? (r.ok ? encartSucces(r.message) : encartAttention(r.message)) : '';
  if (r.ok && r.message) {
    journaliser('ok', r.message);
    setTimeout(() => { $('#retour-surveillance').innerHTML = ''; }, 8000);
  }
}

async function appliquerSurveillance(actif) {
  const r = await pywebview.api.configurer_surveillance($('#dossier-surveille').value, actif);
  if (!r.ok) {
    // Reglage refuse : la bascule ne doit pas rester allumee pour rien.
    $('#opt-surveillance').checked = false;
    etat.config.surveillance = false;
  } else {
    etat.config.surveillance = !!actif;
    etat.config.dossier_surveille = $('#dossier-surveille').value;
  }
  retourSurveillance(r);
}

window.onDossierSurveille = function (chemin) {
  if (!chemin) {
    // Selection annulee : on ne laisse pas la bascule allumee sur rien.
    if (!$('#dossier-surveille').value) {
      $('#opt-surveillance').checked = false;
      $('#bloc-surveillance').style.display = 'none';
    }
    return;
  }
  $('#dossier-surveille').value = chemin;
  appliquerSurveillance($('#opt-surveillance').checked);
};

window.onSurveillance = function (donnees) {
  etat.surveillance = donnees || etat.surveillance;
  majSurveillance();
};

/* ----------------------------------------------------- Mise a jour disponible */

function onMiseAJour(info) {
  if (!info || !info.disponible) return;
  etat.maj = info;
  $('#bandeau-maj-texte').textContent = t(
    info.reinstallation ? 'ui.maj.reinstallation' : 'ui.maj.par_dessus',
    { version: info.version },
  );
  $('#bandeau-maj').style.display = 'flex';
  journaliser('info', t('ui.maj.journal', { version: info.version }));
}
window.onMiseAJour = onMiseAJour;

/* Verification demandee a la main depuis la fenetre d'aide. Elle ne passe pas
   par le reglage d'opt-in, qui ne gouverne que la verification du demarrage. */

function ouvrirAide() {
  $('#aide-maj-version').textContent = etat.version;
  if (!etat.majEnCours) $('#aide-maj-retour').innerHTML = '';
  ouvrirModale('#modale-aide');
}

async function verifierMajDepuisAide() {
  if (etat.majEnCours) return;
  etat.majEnCours = true;

  const bouton = $('#btn-aide-maj');
  const retour = $('#aide-maj-retour');
  bouton.disabled = true;
  $('#btn-aide-maj-texte').textContent = t('ui.aide.maj_en_cours');
  retour.innerHTML = '';

  let r = null;
  try {
    r = await pywebview.api.verifier_maj_manuel();
  } catch (e) {
    console.error(e);
  }

  if (r && r.version_installee) {
    etat.version = String(r.version_installee);
    $('#aide-maj-version').textContent = etat.version;
  }

  if (!r) {
    retour.innerHTML = encartAttention(t('ui.aide.maj_echec'));
  } else if (r.disponible) {
    retour.innerHTML = encartInfo(t(
      r.reinstallation ? 'ui.maj.reinstallation' : 'ui.maj.par_dessus',
      { version: r.version },
    )) + `<button class="bouton bouton-accent" id="btn-aide-maj-page">
        ${icone('i-externe', 'icone-s')}<span>${ech(t('ui.maj.voir'))}</span>
      </button>`;
    const lien = $('#btn-aide-maj-page');
    if (lien) lien.onclick = () => { if (r.url) pywebview.api.ouvrir_lien(r.url); };
  } else if (r.raison === 'indisponible') {
    retour.innerHTML = encartInfo(t('ui.aide.maj_indisponible'));
  } else if (r.raison === 'reseau') {
    retour.innerHTML = encartAttention(t('ui.aide.maj_echec'));
  } else {
    retour.innerHTML = encartSucces(t('ui.aide.maj_a_jour', { version: etat.version }));
  }

  $('#btn-aide-maj-texte').textContent = t('ui.aide.maj_bouton');
  bouton.disabled = false;
  etat.majEnCours = false;
}

/* ------------------------------------------- Import et export des donnees */

function onExportDonnees(retour) {
  if (!retour) return;
  $('#retour-donnees').innerHTML = retour.ok
    ? encartSucces(retour.message) : encartAttention(retour.message);
  journaliser(retour.ok ? 'ok' : 'erreur', retour.message);
  if (retour.ok) setTimeout(() => { $('#retour-donnees').innerHTML = ''; }, 12000);
}
window.onExportDonnees = onExportDonnees;

function onApercuImport(retour) {
  if (!retour) return;
  if (!retour.ok) {
    $('#retour-donnees').innerHTML = encartAttention(retour.message);
    journaliser('erreur', t('ui.import.refuse', { message: retour.message }));
    setEtat(t('ui.import.refuse', { message: retour.message }), 'erreur');
    return;
  }
  etat.importChemin = retour.chemin;
  $('#retour-donnees').innerHTML = '';
  $('#source-import').textContent = t('ui.import.source', {
    nom: retour.nom, date: retour.manifeste.date, version: retour.manifeste.version,
  });
  $('#apercu-import').innerHTML = apercuImportHTML(retour);
  ouvrirModale('#modale-import');
}
window.onApercuImport = onApercuImport;

function apercuImportHTML(d) {
  const bloc = [];
  const ligne = (cle, valeur) =>
    `<div class="materiel-ligne"><span class="cle">${ech(cle)}</span>
      <span class="valeur">${ech(valeur)}</span></div>`;

  bloc.push(`<h3>${ech(t('ui.import.contenu'))}</h3>`);
  /* Le vocabulaire (format 2) n'est annoncé que s'il voyage dans l'archive. */
  if (d.vocabulaire && d.vocabulaire.present) {
    bloc.push(ligne(t('ui.import.vocabulaire'),
      tn('ui.import.termes', d.vocabulaire.nb, { actuel: d.vocabulaire.nb_actuel })));
  }
  if (d.vocabulaire && d.vocabulaire.propositions) {
    bloc.push(encartInfo(tn('ui.import.propositions', d.vocabulaire.propositions)));
  }
  bloc.push(ligne(t('ui.import.glossaire'),
    tn('ui.import.termes', d.glossaire.nb, { actuel: d.glossaire.nb_actuel })));
  bloc.push(ligne(t('ui.import.corrections'),
    tn('ui.import.regles', d.corrections.nb, { actuel: d.corrections.nb_actuel })));
  if (d.corrections.erreurs && d.corrections.erreurs.length) {
    bloc.push(encartAttention(tn('ui.import.regles_fautives', d.corrections.erreurs.length)));
  }
  /* Le gabarit pour l'IA n'est annonce que s'il voyage dans l'archive. */
  if (d.gabarit && d.gabarit.present) bloc.push(encartInfo(d.gabarit.message));

  bloc.push(`<h3>${ech(t('ui.import.reglages'))}</h3>`);
  if (!d.reglages.length) {
    bloc.push(`<p>${ech(t('ui.import.aucun_reglage'))}</p>`);
  } else {
    d.reglages.forEach((r) => bloc.push(ligne(r.libelle,
      t('ui.import.avant', { avant: r.avant, apres: r.apres }))));
  }

  if (d.chemins && d.chemins.length) {
    bloc.push(`<h3>${ech(t('ui.import.chemins'))}</h3>`);
    d.chemins.forEach((c) => {
      bloc.push(c.repris ? encartInfo(c.message) : encartAttention(c.message));
    });
  }

  bloc.push(encartInfo(t('ui.import.filet', {
    dossier: d.dossier_sauvegarde, nom: d.sauvegarde,
  })));
  return bloc.join('');
}

async function confirmerImport() {
  if (!etat.importChemin) return;
  const bouton = $('#btn-confirmer-import');
  bouton.disabled = true;
  try {
    const r = await pywebview.api.appliquer_import(etat.importChemin);
    if (!r.ok) {
      $('#apercu-import').innerHTML = encartAttention(r.message);
      journaliser('erreur', r.message);
      return;
    }
    fermerModale($('#modale-import'));
    etat.importChemin = null;
    const messages = [r.message, r.message_sauvegarde].concat(r.notes || []);
    $('#retour-donnees').innerHTML = encartSucces(r.message)
      + [r.message_sauvegarde].concat(r.notes || []).map(encartInfo).join('');
    messages.forEach((m) => journaliser('ok', m));
    await rechargerApresImport();
  } catch (e) {
    console.error(e);
    $('#apercu-import').innerHTML = encartAttention(t('ui.import.echec'));
  } finally {
    bouton.disabled = false;
  }
}

/* Recharge l'etat complet de l'interface : un import change les reglages, le
   glossaire et les corrections d'un seul coup. */
async function rechargerApresImport() {
  try {
    const d = await pywebview.api.etat_initial();
    initialiser(d, true);
    journaliser('info', t('ui.import.rechargee'));
  } catch (e) {
    console.error(e);
    journaliser('attention', t('ui.import.non_rechargee'));
  }
}

/* Apres chaque fichier, la mesure du poste change : bandeau, cartes et lignes
   en attente sont recalcules d'un bloc, par Python, avec la meme fonction. */
async function rafraichirDurees() {
  try {
    const d = await appelPasserelle('durees_affichees');
    if (d && d.rythme) etat.rythme = d.rythme;
    if (d && d.presets) etat.presets = d.presets;
    dessinerPresets();
    majRythme();
  } catch (e) { /* sans consequence */ }
  rafraichirEstimations();
}

async function rafraichirEstimations() {
  for (const [id, item] of etat.fichiers) {
    if (item.etat !== 'attente' || !item.duree_secs) continue;
    try {
      item.estimation = await pywebview.api.estimation(
        item.duree_secs, etat.config.preset, !!etat.config.diarisation,
        etat.config.mode_avance ? (etat.config.modele_avance || '') : '');
      majLigne(id);
    } catch (e) { /* sans consequence */ }
  }
}

/* ------------------------------------------------------------------ File */

const ETATS_ACTIFS = ['decodage', 'transcription', 'locuteurs', 'ecriture'];

function dessinerFile() {
  const vue = $('#vue-file');
  const lignes = Array.from(etat.fichiers.values());
  const aFaire = lignes.filter((f) => f.etat === 'attente' || ETATS_ACTIFS.includes(f.etat)).length;
  const finis = lignes.filter((f) => ['termine', 'erreur', 'annule'].includes(f.etat)).length;
  $('#compteur-file').textContent = String(aFaire);
  $('#btn-vider').hidden = !finis;
  // Le depot se reduit a une ligne des qu'il y a des fichiers : la file reste
  // visible sans defiler.
  $('#zone-depot').classList.toggle('compacte', !!etat.fichiers.size || !!etat.historique.length);
  vue.closest('section').hidden = !etat.fichiers.size;
  if (!etat.fichiers.size) {
    vue.innerHTML = '';
    return;
  }
  vue.innerHTML = Array.from(etat.fichiers.keys()).map(ligneHTML).join('');
  brancherLignes();
}

const PASTILLES = {
  attente: ['', 'i-fichier'],
  decodage: ['encours', 'i-onde'],
  transcription: ['encours', 'i-onde'],
  locuteurs: ['encours', 'i-personnes'],
  ecriture: ['encours', 'i-fichier'],
  termine: ['termine', 'i-coche'],
  erreur: ['erreur', 'i-alerte'],
  annule: ['annule', 'i-croix'],
};

function boutonLigne(attr, cleTitre, ic) {
  const titre = ech(t(cleTitre));
  return `<button class="bouton-ligne" ${attr} title="${titre}" aria-label="${titre}">${icone(ic, 'icone-s')}</button>`;
}

function ligneHTML(id) {
  const it = etat.fichiers.get(id);
  const [classe, ic] = PASTILLES[it.etat] || PASTILLES.attente;
  const actif = ETATS_ACTIFS.includes(it.etat);

  if (actif) {
    const prog = progressionAffichee(it);
    const pct = prog.indetermine ? '' : (prog.estimee ? t('ui.ligne.pct_environ', { pct: prog.pct }) : `${prog.pct} %`);
    return `<div class="ligne active" data-id="${ech(id)}">
      <span class="pastille ${classe}">${icone(ic, 'icone-s')}</span>
      <div class="infos">
        <div class="nom" title="${ech(it.chemin)}">${ech(it.nom)}</div>
        <div class="progression-tete"><span class="phase">${ech(it.phase || it.message || '')}</span>
          <span class="pourcentage">${ech(pct)}</span></div>
        <div class="barre ${prog.indetermine ? 'indeterminee' : ''}" role="progressbar"
          aria-valuemin="0" aria-valuemax="100" aria-label="${ech(it.nom)}"
          ${prog.indetermine ? '' : `aria-valuenow="${prog.pct}"`}><span style="width:${prog.pct}%"></span></div>
        <div class="temps">${tempsActif(it)}</div>
      </div>
    </div>`;
  }

  let meta = '', classeMeta = '';
  if (it.etat === 'attente') {
    meta = [it.duree, it.taille,
      it.estimation ? t('ui.ligne.calcul', { duree: it.estimation }) : '']
      .filter(Boolean).join(' · ');
  } else if (it.etat === 'termine') {
    // Voix non separees alors que la separation est installee : la ligne passe
    // a l'ambre et le dit. Non installee, ce n'est pas un echec du calcul : le
    // succes reste un succes, Reglages le dit une fois.
    const voixEchouees = voixEchouees_(it);
    classeMeta = voixEchouees ? 'attention' : 'succes';
    meta = [t('ui.ligne.termine', { duree: it.duree_calcul || '?' }),
      voixEchouees ? t('ui.ligne.voix_non_separees') : '',
      it.locuteurs ? tn('ui.ligne.locuteurs', it.locuteurs) : '',
      it.corrections ? tn('ui.ligne.corrections', it.corrections) : '']
      .filter(Boolean).join(' · ');
  } else if (it.etat === 'erreur') {
    classeMeta = 'erreur';
    meta = (it.titre || t('ui.ligne.echec')) + (it.message ? ', ' + it.message : '');
  } else {
    meta = it.message || t('ui.ligne.annule');
  }

  // Une transcription terminee se relit d'un clic : bouton en toutes lettres.
  const texte = (it.sorties || []).find((s) => s.format === 'TXT');
  const autres = (it.sorties || []).filter((s) => s.format !== 'TXT').map((s) =>
    `<button class="etiquette-format" data-ouvrir="${ech(s.chemin)}" title="${ech(s.nom)}">${ech(s.format)}</button>`).join('');
  const actions = [];
  if (texte) actions.push(`<button class="bouton bouton-accent bouton-petit" data-lire="${ech(texte.chemin)}" aria-label="${ech(t('ui.ligne.relire_nom', { nom: it.nom }))}">${icone('i-fichier', 'icone-s')}<span>${ech(t('ui.ligne.relire'))}</span></button>`);
  actions.push(autres);
  // Arrete, ou abandonne apres plantage du moteur : ce qui est transcrit est
  // garde, le bouton le dit (« Reprendre ») ; un autre echec repart de zero.
  if (['annule', 'erreur'].includes(it.etat)) {
    const chemin = String(it.chemin || '').toLowerCase();
    const reprendre = !!it.reprise || (etat.reprises || []).some((r) => String(r.chemin || '').toLowerCase() === chemin);
    actions.push(`<button class="bouton bouton-petit" data-relancer>${icone('i-reprise', 'icone-s')}<span>${ech(t(reprendre ? 'ui.ligne.reprendre' : 'ui.ligne.relancer'))}</span></button>`);
  }
  if (it.etat === 'erreur') actions.push(boutonLigne('data-log', 'ui.ligne.journal', 'i-info'));
  actions.push(boutonLigne('data-retirer', 'ui.ligne.retirer', 'i-croix'));

  return `<div class="ligne" data-id="${ech(id)}">
    <span class="pastille ${classe}">${icone(ic, 'icone-s')}</span>
    <div class="infos">
      <div class="nom" title="${ech(it.chemin)}">${ech(it.nom)}</div>
      <div class="meta ${classeMeta}">${ech(meta)}</div>
    </div>
    <div class="actions-ligne">${actions.join('')}</div>
  </div>`;
}

function voixEchouees_(it) {
  const ext = ((etat.diarisation || {}).extension) || {};
  return !!it.voix_non_separees && !!ext.installee;
}

/* Progression : celle du moteur quand elle arrive ; sinon, quand elle reste
   figee (le moteur habituel decode par lots et ne rend rien avant la fin d'un
   lot), une estimation tiree du temps ecoule et du reste annonce, dite
   « environ » et jamais au-dela de 95 %. */
function progressionAffichee(it) {
  const brute = { pct: it.pct || 0, estimee: false, indetermine: !!it.indetermine };
  // Pas de reste annonce (chargement du modele) : la barre reste indeterminee.
  if (typeof it.restant_s !== 'number' || !it.restant_recu || it.restant_s <= 0) return brute;
  const depuis = (Date.now() - it.restant_recu) / 1000;
  if (depuis < 8) return brute;
  const base = it.indetermine ? 0 : (it.pct || 0);
  const part = Math.min(0.95, depuis / Math.max(depuis + 1, it.restant_s));
  const pct = Math.max(base, Math.min(95, Math.round(base + (100 - base) * part)));
  return pct > base ? { pct: pct, estimee: true, indetermine: false } : brute;
}

/* Temps d'un fichier en cours : ecoule qui avance chaque seconde, reste a
   faire qui decompte entre deux releves de Python, heure de fin prevue. */
function tempsActif(it) {
  const maintenant = Date.now();
  const ecoule = it.depart ? (maintenant - it.depart) / 1000 : 0;
  const ecouleTexte = ecoule >= 1 ? formaterDuree(ecoule) : t('duree.secondes', { s: 0 });
  const morceaux = [t('ui.ligne.ecoule', { duree: `<strong>${ech(ecouleTexte)}</strong>` })];
  if (typeof it.restant_s === 'number') {
    const reste = it.restant_s - (maintenant - (it.restant_recu || maintenant)) / 1000;
    if (reste > 5) {
      morceaux.push(t('ui.ligne.restant', { duree: `<strong>${ech(formaterDuree(reste))}</strong>` }));
      const fin = new Date(maintenant + reste * 1000);
      morceaux.push(ech(t('ui.ligne.fin_vers', { heure: formaterHeure(fin) })));
    } else {
      morceaux.push(ech(t('ui.ligne.bientot')));
    }
  }
  return morceaux.join(' · ');
}

function formaterHeure(date) {
  return t('format.heure_courte', { h: date.getHours(), m: String(date.getMinutes()).padStart(2, '0') });
}

function majLigne(id) {
  const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
  if (!ligne) { dessinerFile(); return; }
  const focus = ligne.contains(document.activeElement)
    ? Array.from(ligne.querySelectorAll('button')).indexOf(document.activeElement) : -1;
  ligne.outerHTML = ligneHTML(id);
  brancherLignes();
  if (focus >= 0) {
    const nouvelle = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
    const bouton = nouvelle && nouvelle.querySelectorAll('button')[focus];
    if (bouton) bouton.focus();
  }
  const lignes = Array.from(etat.fichiers.values());
  $('#compteur-file').textContent = String(lignes.filter((f) => f.etat === 'attente' || ETATS_ACTIFS.includes(f.etat)).length);
  $('#btn-vider').hidden = !lignes.some((f) => ['termine', 'erreur', 'annule'].includes(f.etat));
}

function brancherLignes() {
  $$('#vue-file [data-retirer]').forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      const id = b.closest('.ligne').dataset.id;
      etat.fichiers.delete(id);
      pywebview.api.retirer(id);
      dessinerFile();
      majBoutons();
    };
  });
  $$('#vue-file [data-relancer]').forEach((b) => {
    b.onclick = async (e) => {
      e.stopPropagation();
      const id = b.closest('.ligne').dataset.id;
      const r = await pywebview.api.relancer(id);
      if (!r.ok) { journaliser('attention', r.message); setEtat(r.message, 'erreur'); return; }
      remettreEnAttente(r.element);
      etat.reprises = r.reprises || etat.reprises;
      dessinerReprises();
    };
  });
  $$('#vue-file [data-log]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); pywebview.api.ouvrir_journal(); };
  });
  $$('#vue-file [data-ouvrir]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); ouvrirSortie(b.dataset.ouvrir); };
  });
  $$('#vue-file [data-lire]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); ouvrirLecture(b.dataset.lire); };
  });
}

/* Retire les lignes finies (terminees, en echec, arretees) ; celles qui
   attendent restent, elles se retirent une a une. */
function retirerTermines() {
  Array.from(etat.fichiers.entries()).forEach(([id, it]) => {
    if (['termine', 'erreur', 'annule'].includes(it.etat)) {
      etat.fichiers.delete(id);
      pywebview.api.retirer(id);
    }
  });
  dessinerFile();
  majBoutons();
}

/* ------------------------------------------------------------ Historique */

function dessinerHistorique() {
  const vue = $('#vue-historique');
  $('#compteur-historique').textContent = String(etat.historique.length);
  $('#zone-depot').classList.toggle('compacte', !!etat.fichiers.size || !!etat.historique.length);
  if (!etat.historique.length) {
    vue.innerHTML = `<div class="vide">${ech(t('ui.historique.vide'))}</div>`;
    return;
  }
  const filtre = normaliserRecherche($('#recherche-historique').value.trim());
  const liste = filtre
    ? etat.historique.filter((h) => normaliserRecherche(h.nom).includes(filtre))
    : etat.historique;
  if (!liste.length) {
    vue.innerHTML = `<div class="vide">${ech(t('ui.historique.aucun_resultat'))}</div>`;
    return;
  }
  /* Une ligne par transcription ; « Relire » en toutes lettres, « Exporter »
     ouvre la relecture sur son menu d'export, chaque autre format s'ouvre a
     part. Celles finies pendant cette session passent en tete. */
  const recente = (h) => etat.recents.get(String(h.chemin).toLowerCase());
  const triee = liste.slice().sort((a, b) => ((recente(b) || {}).quand || 0) - ((recente(a) || {}).quand || 0));
  vue.innerHTML = triee.map((h) => {
    const formats = h.formats || [{ format: h.format, chemin: h.chemin }];
    const texte = formats.find((f) => f.format === 'TXT');
    const r = recente(h);
    const meta = [
      // « A l'instant » dix minutes durant, puis l'heure de fin.
      r ? (Date.now() - r.quand < 600000 ? t('ui.historique.a_l_instant', { duree: r.duree || '?' })
        : t('ui.historique.termine_a', { heure: formaterHeure(new Date(r.quand)), duree: r.duree || '?' })) : '',
      h.duree,
      h.reunion ? t('ui.historique.reunion', { date: h.reunion }) : '',
      h.date ? t('ui.historique.transcrite', { date: h.date }) : '',
      r && r.locuteurs ? tn('ui.ligne.locuteurs', r.locuteurs) : '',
      h.relu ? t('ui.historique.relu', { position: h.relu }) : '',
    ].filter(Boolean).join(' · ');
    return `<div class="ligne${r ? ' recente' : ''}" data-chemin="${ech(h.chemin)}">
      <span class="pastille termine">${icone('i-coche', 'icone-s')}</span>
      <div class="infos">
        <div class="nom">${ech(h.nom)}</div>
        <div class="meta ${r ? 'succes' : ''}">${ech(meta)}</div>
      </div>
      <div class="actions-ligne">
        ${texte ? `<button class="bouton ${r ? 'bouton-accent' : ''} bouton-petit" data-lire="${ech(texte.chemin)}" aria-label="${ech(t('ui.ligne.relire_nom', { nom: h.nom }))}">${icone('i-fichier', 'icone-s')}<span>${ech(t('ui.ligne.relire'))}</span></button>` : ''}
        ${texte ? `<button class="bouton bouton-petit" data-exporter="${ech(texte.chemin)}" aria-label="${ech(t('ui.ligne.exporter_nom', { nom: h.nom }))}">${ech(t('ui.ligne.exporter'))}</button>` : ''}
        ${formats.filter((f) => f.format !== 'TXT').map((f) =>
          `<button class="etiquette-format" data-ouvrir="${ech(f.chemin)}">${ech(f.format)}</button>`).join('')}
      </div>
    </div>`;
  }).join('');
  $$('#vue-historique [data-exporter]').forEach((b) => {
    b.onclick = async (e) => {
      e.stopPropagation();
      await ouvrirLecture(b.dataset.exporter);
      if (lect.d && typeof basculerMenuExport === 'function') basculerMenuExport();
    };
  });
  $$('#vue-historique .ligne').forEach((l) => {
    l.onclick = (e) => { if (!e.target.closest('button')) ouvrirSortie(l.dataset.chemin); };
  });
  $$('#vue-historique [data-ouvrir]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); ouvrirSortie(b.dataset.ouvrir); };
  });
  $$('#vue-historique [data-lire]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); ouvrirLecture(b.dataset.lire); };
  });
}

/* Recherche sans casse ni accents : « reunion » trouve « Réunion ». Un
   caractere en donne toujours un : les positions restent celles du texte. */
function normaliserRecherche(texte) {
  let sortie = '';
  for (const c of String(texte || '')) {
    const n = c.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    sortie += n.length === 1 ? n : c.toLowerCase().charAt(0) || c;
  }
  return sortie;
}

/* Le texte se relit dans la relecture, les sous-titres restent en apercu
   brut : personne ne lit un .srt en paragraphes. */
function ouvrirSortie(chemin) {
  if (/\.txt$/i.test(chemin || '')) ouvrirLecture(chemin);
  else ouvrirApercu(chemin);
}

/* ------------------------------------------------- Vocabulaire, format 2

   Un ecran a part, ouvert depuis l'en-tete. Revue par lots au clavier : fleches
   pour parcourir, Espace pour cocher, A accepter, R refuser, M modifier. */

const voc = { donnees: null, onglet: 'propose', edition: null, active: -1 };

function brancherVocabulaire() {
  document.querySelectorAll('[data-voc-onglet]').forEach((b) => b.addEventListener('click', () => {
    voc.onglet = b.dataset.vocOnglet;
    voc.active = -1;
    fermerEditionVocabulaire();
    dessinerVocabulaire();
  }));
  $('#voc-recherche').addEventListener('input', () => { voc.active = -1; dessinerListeVocabulaire(); });
  $('#voc-tout').addEventListener('change', (e) => {
    document.querySelectorAll('.voc-case').forEach((c) => { c.checked = e.target.checked; });
    majSelectionVocabulaire();
  });
  $('#btn-voc-accepter').addEventListener('click', () => deciderSelection('accepter'));
  $('#btn-voc-refuser').addEventListener('click', () => deciderSelection('refuser'));
  $('#btn-voc-ajouter').addEventListener('click', () => ouvrirEditionVocabulaire(null));
  $('#btn-voc-edition-annuler').addEventListener('click', fermerEditionVocabulaire);
  $('#btn-voc-edition-enregistrer').addEventListener('click', () => enregistrerEditionVocabulaire(false));
  $('#btn-voc-edition-accepter').addEventListener('click', () => enregistrerEditionVocabulaire(true));
  $('#btn-voc-importer').addEventListener('click', () => pywebview.api.vocabulaire_importer());
  $('#btn-voc-exporter').addEventListener('click', () => pywebview.api.vocabulaire_exporter());
  $('#btn-voc-partage').addEventListener('click', () => pywebview.api.vocabulaire_ajouter_partage());
  $('#opt-rapprochement').addEventListener('change', (e) =>
    enregistrer({ rapprochement_vocabulaire: e.target.checked }));
  $('#voc-liste').addEventListener('click', actionLigneVocabulaire);
  $('#voc-liste').addEventListener('change', majSelectionVocabulaire);
  $('#voc-liste').addEventListener('keydown', clavierVocabulaire);
  $('#voc-liste').addEventListener('focusin', (e) => {
    const ligne = e.target.closest('.voc-ligne');
    if (ligne) activerLigneVocabulaire(Number(ligne.dataset.rang), false);
  });
  $('#voc-avis').addEventListener('click', async (e) => {
    if (!e.target.closest('#btn-voc-convertir')) return;
    const r = await pywebview.api.vocabulaire_convertir();
    retourVocabulaire(r);
    await chargerVocabulaire();
  });
  $('#voc-partages-liste').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-retirer-partage]');
    if (!b) return;
    await pywebview.api.vocabulaire_retirer_partage(b.dataset.retirerPartage);
    await chargerVocabulaire();
  });
}

async function majCompteurVocabulaire() {
  try {
    const d = await pywebview.api.vocabulaire_etat();
    voc.donnees = d;
    afficherCompteurVocabulaire(d.resume.proposes);
    majSousLibellesVocabulaire(d.resume);
  } catch (e) { console.error(e); }
}

/* Sous les deux bascules du vocabulaire : ce que le vocabulaire effectif
   contient vraiment (format 2, equipe et format 1 compris), pas le seul
   glossaire du format 1, qui disait « Aucun terme » avec des termes actifs. */
function majSousLibellesVocabulaire(resume) {
  if (!resume) return;
  $('#etat-glossaire').textContent = resume.actifs ? tn('ui.voc.termes', resume.actifs) : t('ui.voc.aucun_terme');
  $('#etat-corrections').textContent = resume.fautes ? tn('ui.voc.regles', resume.fautes) : t('ui.voc.aucune_regle');
}

function afficherCompteurVocabulaire(n) {
  const el = $('#voc-compteur-propositions');
  el.hidden = !n;
  el.textContent = String(n || 0);
  el.title = t('ui.voc2.compteur', { n: n || 0 });
  $('#btn-nav-vocabulaire').setAttribute('aria-label',
    t('ui.nav.vocabulaire') + (n ? ', ' + t('ui.voc2.compteur', { n: n }) : ''));
}

function ouvrirVocabulaire() {
  fermerEditionVocabulaire();
  $('#voc-retour').textContent = '';
  afficherVue('vocabulaire');
}

async function chargerVocabulaire() {
  voc.donnees = await pywebview.api.vocabulaire_etat();
  majSousLibellesVocabulaire(voc.donnees.resume);
  if (voc.onglet === 'propose' && !voc.donnees.resume.proposes && voc.donnees.resume.actifs) voc.onglet = 'actif';
  dessinerVocabulaire();
  afficherCompteurVocabulaire(voc.donnees.resume.proposes);
}

function dessinerVocabulaire() {
  const d = voc.donnees;
  if (!d) return;
  const r = d.resume;
  $('#voc-resume').textContent = t('ui.voc2.resume', {
    actifs: tn('ui.voc2.n_actifs', r.actifs), proposes: tn('ui.voc2.n_proposes', r.proposes),
    refuses: tn('ui.voc2.n_refuses', r.refuses), retenus: tn('ui.voc2.n_termes', d.amorce.retenus),
    total: d.amorce.total, jetons: d.amorce.jetons,
  });
  const avis = [];
  if (d.format1) {
    avis.push(`<div class="encart encart-info">${icone('i-info', 'icone-s')}
      <span>${ech(t('ui.voc2.format1'))}</span><span class="pousse"></span>
      <button class="bouton" id="btn-voc-convertir">${ech(t('ui.voc2.convertir'))}</button></div>`);
  }
  if (r.fautes_risquees) avis.push(encartAttention(tn('ui.voc2.risquees', r.fautes_risquees)));
  if (!d.lexique) avis.push(encartAttention(t('ui.voc2.lexique_absent')));
  (d.problemes || []).forEach((p) => avis.push(encartAttention(t('ui.voc2.probleme', { detail: p }))));
  $('#voc-avis').innerHTML = avis.join('');
  const comptes = { propose: 0, actif: 0, refuse: 0 };
  d.entrees.forEach((e) => { comptes[e.etat] = (comptes[e.etat] || 0) + 1; });
  ['propose', 'actif', 'refuse'].forEach((k) => { $('#voc-n-' + k).textContent = comptes[k]; });
  document.querySelectorAll('[data-voc-onglet]').forEach((b) =>
    b.setAttribute('aria-selected', String(b.dataset.vocOnglet === voc.onglet)));
  // Accepter, refuser, tout cocher : seulement quand il y a de quoi relire.
  const revue = voc.onglet === 'propose' && comptes.propose > 0;
  $('#btn-voc-accepter').hidden = !revue;
  $('#btn-voc-refuser').hidden = !revue;
  $('#voc-tout').closest('label').hidden = !revue;
  $('#voc-tout').checked = false;
  $('#opt-rapprochement').checked = d.rapprochement;
  const categories = $('#voc-categorie');
  if (!categories.options.length) {
    categories.innerHTML = d.categories.map((c) =>
      `<option value="${ech(c)}">${ech(t('ui.voc2.cat.' + c))}</option>`).join('');
  }
  $('#voc-partages-liste').innerHTML = d.partages.length
    ? d.partages.map((p) => `<div class="voc-partage"><span class="nom">${ech(p.nom)}</span>
        <span class="meta">${ech(p.ok ? tn('ui.voc2.partage_termes', p.termes) : t('ui.voc2.partage_illisible'))}</span>
        <span class="pousse"></span>
        <button class="bouton-lien" data-retirer-partage="${ech(p.chemin)}">${ech(t('ui.voc2.partages.retirer'))}</button></div>`).join('')
    : `<p class="aide">${ech(t('ui.voc2.aucun_partage'))}</p>`;
  dessinerListeVocabulaire();
}

function texteFaute(f) {
  // Seule la forme risquée est barrée, jamais la note qui la suit.
  let texte = ech(f.forme);
  if (f.risquee && !f.forcer) texte = `<span class="risquee" title="${ech(t('ui.voc2.risquee'))}">${texte}</span>`;
  const notes = [];
  if (f.voisins && f.voisins.length) notes.push(t('ui.voc2.pres_de', { voisins: f.voisins.join(', ') }));
  else if (f.forcer) notes.push(t('ui.voc2.forcee'));
  if (f.vu) notes.push(vuDans(f));
  if (notes.length) texte += ` <span class="note">(${ech(notes.join(' ; '))})</span>`;
  return texte;
}

function vuDans(e) {
  return t('ui.voc2.vu', { vu: tn('ui.voc2.fois', e.vu), reunions: tn('ui.voc2.reunions', e.reunions || 1) });
}

function lignesVocabulaire() {
  const d = voc.donnees;
  const filtre = normaliserRecherche($('#voc-recherche').value.trim());
  return d.entrees.filter((e) => e.etat === voc.onglet
    && (!filtre || normaliserRecherche(e.forme).includes(filtre)
        || e.fautes.some((f) => normaliserRecherche(f.forme).includes(filtre))));
}

function dessinerListeVocabulaire() {
  const d = voc.donnees;
  if (!d) return;
  const lignes = lignesVocabulaire();
  if (!lignes.length) {
    $('#voc-liste').innerHTML = `<p class="vide">${ech(t('ui.voc2.vide.' + voc.onglet))}</p>`;
    return;
  }
  $('#voc-liste').innerHTML = lignes.map((e, rang) => {
    const index = d.entrees.indexOf(e);
    const source = e.source === 'personnel' ? ''
      : (e.source === 'format1' ? t('ui.voc2.source.format1')
        : t('ui.voc2.source.partage', { nom: e.source.replace(/^partage:/, '') }));
    const meta = [t('ui.voc2.cat.' + e.categorie), t('ui.voc2.origine.' + e.origine)];
    if (e.vu) meta.push(vuDans(e));
    if (source) meta.push(source);
    const actions = [];
    if (e.modifiable) {
      if (e.etat === 'propose') {
        actions.push(`<button class="bouton-lien" tabindex="-1" data-voc-action="accepter" data-i="${index}">${ech(t('ui.voc2.accepter'))}</button>`);
        actions.push(`<button class="bouton-lien" tabindex="-1" data-voc-action="refuser" data-i="${index}">${ech(t('ui.voc2.refuser'))}</button>`);
      }
      actions.push(`<button class="bouton-lien" tabindex="-1" data-voc-action="modifier" data-i="${index}">${ech(t('ui.voc2.modifier'))}</button>`);
      if (e.etat !== 'propose') {
        actions.push(`<button class="bouton-lien" tabindex="-1" data-voc-action="supprimer" data-i="${index}">${ech(t('ui.voc2.supprimer'))}</button>`);
      }
    }
    const cochable = e.etat === 'propose' && e.modifiable;
    return `<div class="voc-ligne" role="option" aria-selected="false" tabindex="${rang === Math.max(0, voc.active) ? 0 : -1}" data-rang="${rang}" data-i="${index}">
      ${cochable ? `<input type="checkbox" class="voc-case" tabindex="-1" data-i="${index}" aria-label="${ech(e.forme)}">` : '<span class="voc-case-vide"></span>'}
      <div class="voc-infos">
        <div class="voc-forme">${ech(e.forme)}${e.poids > 1 ? ` <span class="voc-poids">${'+'.repeat(e.poids - 1)}</span>` : ''}</div>
        <div class="voc-fautes">${e.fautes.length ? e.fautes.map(texteFaute).join(', ') : `<span class="note">${ech(t('ui.voc2.sans_faute'))}</span>`}</div>
        <div class="meta">${ech(meta.join(' · '))}</div>
      </div>
      <div class="voc-actions">${actions.join('')}</div>
    </div>`;
  }).join('');
  if (voc.active >= lignes.length) voc.active = lignes.length - 1;
  if (voc.active >= 0) activerLigneVocabulaire(voc.active, true);
}

function activerLigneVocabulaire(rang, focus) {
  const lignes = $$('#voc-liste .voc-ligne');
  if (!lignes.length) return;
  voc.active = Math.max(0, Math.min(lignes.length - 1, rang));
  lignes.forEach((l, i) => {
    l.classList.toggle('active', i === voc.active);
    l.tabIndex = i === voc.active ? 0 : -1;
  });
  if (focus) {
    lignes[voc.active].focus({ preventScroll: true });
    lignes[voc.active].scrollIntoView({ block: 'nearest' });
  }
}

function majSelectionVocabulaire() {
  $$('#voc-liste .voc-ligne').forEach((l) => {
    const c = l.querySelector('.voc-case');
    l.setAttribute('aria-selected', c && c.checked ? 'true' : 'false');
  });
}

/* Revue au clavier : la ligne active porte le focus, les decisions portent sur
   les lignes cochees, ou sur la ligne active s'il n'y en a aucune. */
async function clavierVocabulaire(e) {
  if (e.target.closest('input, textarea, select') && !e.target.classList.contains('voc-case')) return;
  const lignes = $$('#voc-liste .voc-ligne');
  if (!lignes.length) return;
  const touche = e.key.toLowerCase();
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    activerLigneVocabulaire(voc.active + (e.key === 'ArrowDown' ? 1 : -1), true);
  } else if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault();
    activerLigneVocabulaire(e.key === 'Home' ? 0 : lignes.length - 1, true);
  } else if (e.key === ' ') {
    e.preventDefault();
    const c = lignes[voc.active] && lignes[voc.active].querySelector('.voc-case');
    if (c) { c.checked = !c.checked; majSelectionVocabulaire(); }
  } else if ((touche === 'a' || touche === 'r') && !e.ctrlKey && !e.altKey && voc.onglet === 'propose') {
    e.preventDefault();
    const cochees = $$('.voc-case:checked');
    const decision = touche === 'a' ? 'accepter' : 'refuser';
    if (cochees.length) { await deciderSelection(decision); return; }
    const ligne = lignes[voc.active];
    const entree = ligne && voc.donnees.entrees[Number(ligne.dataset.i)];
    if (!entree || !entree.modifiable) return;
    retourVocabulaire(await pywebview.api.vocabulaire_decider([entree.forme], decision));
    await chargerVocabulaire();
    activerLigneVocabulaire(voc.active, true);
  } else if (touche === 'm' && !e.ctrlKey && !e.altKey) {
    e.preventDefault();
    const ligne = lignes[voc.active];
    const entree = ligne && voc.donnees.entrees[Number(ligne.dataset.i)];
    if (entree && entree.modifiable) ouvrirEditionVocabulaire(entree);
  } else if (e.ctrlKey && touche === 'a') {
    e.preventDefault();
    $('#voc-tout').checked = true;
    $$('.voc-case').forEach((c) => { c.checked = true; });
    majSelectionVocabulaire();
  }
}

async function actionLigneVocabulaire(e) {
  const b = e.target.closest('[data-voc-action]');
  if (!b) return;
  const entree = voc.donnees.entrees[Number(b.dataset.i)];
  if (!entree) return;
  const action = b.dataset.vocAction;
  let r;
  if (action === 'accepter' || action === 'refuser') {
    r = await pywebview.api.vocabulaire_decider([entree.forme], action);
  } else if (action === 'supprimer') {
    r = await pywebview.api.vocabulaire_supprimer(entree.forme, entree.etat);
  } else {
    ouvrirEditionVocabulaire(entree);
    return;
  }
  retourVocabulaire(r);
  await chargerVocabulaire();
}

async function deciderSelection(decision) {
  const formes = Array.from(document.querySelectorAll('.voc-case:checked'))
    .map((c) => voc.donnees.entrees[Number(c.dataset.i)].forme);
  if (!formes.length) {
    retourVocabulaire({ ok: false, message: t('ui.voc2.selection_vide') });
    return;
  }
  retourVocabulaire(await pywebview.api.vocabulaire_decider(formes, decision));
  await chargerVocabulaire();
  activerLigneVocabulaire(Math.max(0, voc.active), true);
}

function ouvrirEditionVocabulaire(entree) {
  voc.edition = entree;
  $('#voc-forme').value = entree ? entree.forme : '';
  $('#voc-categorie').value = entree ? entree.categorie : 'autre';
  $('#voc-poids').value = String(entree ? entree.poids : 1);
  $('#voc-fautes').value = entree ? entree.fautes.map((f) =>
    f.forme + (f.voisins && f.voisins.length ? ' | ' + f.voisins.join(', ') : '')).join('\n') : '';
  $('#voc-amorce').checked = entree ? entree.amorce : true;
  $('#btn-voc-edition-accepter').hidden = !(entree && entree.etat === 'propose');
  $('#voc-edition-retour').innerHTML = '';
  $('#voc-edition').hidden = false;
  setTimeout(() => $('#voc-forme').focus(), 30);
}

function fermerEditionVocabulaire() {
  const etaitOuverte = !$('#voc-edition').hidden;
  voc.edition = null;
  $('#voc-edition').hidden = true;
  if (etaitOuverte) activerLigneVocabulaire(Math.max(0, voc.active), true);
}

function lireFautesSaisies() {
  const anciennes = {};
  (voc.edition ? voc.edition.fautes : []).forEach((f) => { anciennes[f.forme.toLowerCase()] = f; });
  return $('#voc-fautes').value.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const [forme, voisins] = l.split('|');
    const propre = forme.trim();
    const ancienne = anciennes[propre.toLowerCase()] || {};
    return {
      forme: propre,
      voisins: (voisins || '').split(',').map((v) => v.trim()).filter(Boolean),
      forcer: !!ancienne.forcer, vu: ancienne.vu || 0, reunions: ancienne.reunions || 0,
    };
  });
}

async function enregistrerEditionVocabulaire(accepter) {
  const modification = {
    forme: $('#voc-forme').value.trim(),
    categorie: $('#voc-categorie').value,
    poids: Number($('#voc-poids').value),
    fautes: lireFautesSaisies(),
    amorce: $('#voc-amorce').checked,
    accepter: accepter,
  };
  const r = voc.edition
    ? await pywebview.api.vocabulaire_modifier(voc.edition.forme, voc.edition.etat, modification)
    : await pywebview.api.vocabulaire_ajouter(modification);
  if (!r.ok) {
    $('#voc-edition-retour').innerHTML = encartAttention(r.message);
    return;
  }
  fermerEditionVocabulaire();
  retourVocabulaire(r);
  await chargerVocabulaire();
}

function retourVocabulaire(r) {
  const zone = $('#voc-retour');
  zone.textContent = (r && r.message) || '';
  zone.className = 'lecture-retour ' + (r && r.ok ? 'ok' : 'erreur');
  if (r && r.message) journaliser(r.ok ? 'ok' : 'attention', r.message);
}

/* Retour des boites de fichiers (import, export, fichier partage). */
window.onVocabulaire = async function (r) {
  retourVocabulaire(r);
  if (etat.vue === 'vocabulaire') await chargerVocabulaire();
  else majCompteurVocabulaire();
};

/* --------------------------------------------------- Reprises en attente */

function dessinerReprises() {
  const zone = $('#bloc-reprises');
  const enFile = new Set(Array.from(etat.fichiers.values()).map((f) => String(f.chemin || '').toLowerCase()));
  const reprises = etat.reprises.filter((r) => !enFile.has(String(r.chemin || '').toLowerCase()));
  if (!reprises.length) { zone.innerHTML = ''; return; }
  zone.innerHTML = reprises.map((r) => `
    <div class="reprise-carte" data-cle="${ech(r.cle)}">
      ${icone('i-reprise')}
      <div class="infos">
        <div class="nom">${ech(r.nom)}</div>
        <div class="meta">${ech(t('ui.reprise.meta', {
          position: r.position_texte, duree: r.duree_texte, pct: r.pct,
          ecoule: r.ecoule_texte,
        }))}</div>
      </div>
      <button class="bouton bouton-petit" data-reprendre>${ech(t('ui.reprise.reprendre'))}</button>
      <button class="bouton bouton-discret bouton-petit" data-oublier>${ech(t('ui.reprise.oublier'))}</button>
    </div>`).join('');

  $$('#bloc-reprises [data-reprendre]').forEach((b) => {
    b.onclick = async () => {
      const cle = b.closest('.reprise-carte').dataset.cle;
      const r = await pywebview.api.reprendre(cle);
      if (!r.ok) {
        // La carte reste : la reprise est toujours sur le disque, et le refus
        // est dit la ou l'on regarde.
        journaliser('attention', r.message);
        setEtat(r.message, 'erreur');
        return;
      }
      etat.reprises = etat.reprises.filter((x) => x.cle !== cle);
      dessinerReprises();
      majBoutons();
    };
  });
  $$('#bloc-reprises [data-oublier]').forEach((b) => {
    b.onclick = async () => {
      const cle = b.closest('.reprise-carte').dataset.cle;
      const r = await pywebview.api.oublier_reprise(cle);
      etat.reprises = (r && r.reprises) || [];
      dessinerReprises();
      journaliser('info', t('ui.reprise.oubliee'));
    };
  });
}

async function ouvrirApercu(chemin) {
  etat.apercuChemin = chemin;
  $('#titre-apercu').textContent = chemin.split(/[\\/]/).pop();
  $('#contenu-apercu').textContent = t('ui.apercu.chargement');
  ouvrirModale('#modale-apercu');
  try {
    const texte = await pywebview.api.lire_texte(chemin);
    $('#contenu-apercu').textContent = texte || t('ui.apercu.vide');
  } catch (e) {
    $('#contenu-apercu').textContent = t('ui.apercu.illisible');
  }
}

/* --------------------------------------------------------------- Journal

   Le journal vit dans Reglages, Journal. Un avertissement ou une erreur est
   aussi dit dans la ligne d'etat, la ou l'on regarde, sauf pendant une
   transcription, ou la ligne d'etat dit la progression. */

function journaliser(niveau, texte) {
  const zone = $('#journal-contenu');
  const heure = new Date().toLocaleTimeString(t('format.heure'), { hour12: false });
  const ligne = document.createElement('div');
  ligne.className = 'l';
  ligne.innerHTML = `<span class="h">${heure}</span><span class="${ech(niveau)}">${ech(texte)}</span>`;
  zone.appendChild(ligne);
  while (zone.childElementCount > 500) zone.removeChild(zone.firstChild);
  zone.scrollTop = zone.scrollHeight;
  if ((niveau === 'attention' || niveau === 'erreur') && !etat.enCours && etat.pret) {
    setEtat(texte, niveau === 'erreur' ? 'erreur' : 'attention');
  }
}

/* ------------------------------------------------------------ Etat global */

function setEtat(texte, classe) {
  $('#etat-texte').textContent = texte;
  $('#etat-texte').title = texte;
  $('#etat-global').className = 'etat-global ' + (classe || '');
}

function majBoutons() {
  const enAttente = Array.from(etat.fichiers.values()).filter((f) => f.etat === 'attente').length;
  $('#btn-lancer').disabled = etat.enCours || etat.bancEnCours || !enAttente || !etat.pret;
  $('#btn-arreter').disabled = !etat.enCours;
  $('#btn-arreter').hidden = !etat.enCours;
  $('#btn-lancer').innerHTML = icone('i-lecture', 'icone-s') + ' '
    + ech(etat.enCours ? t('ui.bouton.en_cours')
      : (enAttente > 1 ? t('ui.bouton.lancer_n', { n: enAttente }) : t('ui.bouton.lancer')));
  majActivite();
}

/* « Fichier 2 sur 4 » : position du fichier en cours dans le lancement. */
function etatPassage(id) {
  const total = etat.passage.length;
  const rang = etat.passage.indexOf(id) + 1;
  return total > 1 && rang > 0 ? t('ui.etat.fichier_n', { rang: rang, total: total }) + ' · ' : '';
}

/* ------------------------------------------- Rappels appeles par Python */

/* Un fichier deja liste qui repasse en attente (relance, reprise, nouveau
   depot) repart d'une ligne propre : rien de son passage precedent ne reste. */
function remettreEnAttente(item) {
  const avant = etat.fichiers.get(item.id) || {};
  etat.fichiers.set(item.id, Object.assign({ pct: 0 }, item,
    { duree: avant.duree, duree_secs: avant.duree_secs, taille: item.taille || avant.taille }));
  majLigne(item.id);
  majBoutons();
  rafraichirEstimations();
}

window.onFichiersAjoutes = function (items) {
  if (!etat.enCours) setEtat('', '');
  // Un fichier deja liste qui repasse en attente garde sa duree, et son
  // estimation est recalculee : la ligne ne perd pas ce qu'elle disait.
  items.forEach((it) => {
    const avant = etat.fichiers.get(it.id) || {};
    etat.fichiers.set(it.id, Object.assign({ pct: 0 }, it,
      avant.duree_secs ? { duree: avant.duree, duree_secs: avant.duree_secs } : {}));
  });
  if (items.some((it) => (etat.fichiers.get(it.id) || {}).duree_secs)) rafraichirEstimations();
  dessinerFile();
  majBoutons();
  if (etat.enCours) items.forEach((it) => { if (!etat.passage.includes(it.id)) etat.passage.push(it.id); });
};

window.onDuree = async function (id, secondes, texte) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  it.duree_secs = secondes;
  it.duree = secondes ? texte : t('ui.ligne.duree_illisible');
  if (!secondes) { it.estimation = ''; majLigne(id); return; }
  try {
    it.estimation = await pywebview.api.estimation(
      secondes, etat.config.preset, !!etat.config.diarisation,
      etat.config.mode_avance ? (etat.config.modele_avance || '') : '');
  } catch (e) { /* sans consequence */ }
  majLigne(id);
};

window.onDossierSortie = function (chemin) {
  $('#dossier-sortie').value = chemin;
  etat.config.dossier_sortie = chemin;
};

window.onHistorique = function (items) {
  etat.historique = items || [];
  dessinerHistorique();
};

/* Duree lisible, jumelle de presets.formater_duree cote Python. */
function formaterDuree(secondes) {
  const total = Math.floor(Math.max(0, secondes || 0));
  if (!total) return t('duree.vide');
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const deux = (n) => String(n).padStart(2, '0');
  if (h) return t('duree.heures', { h: h, m: deux(m) });
  if (m) return t('duree.minutes', { m: m, s: deux(s) });
  return t('duree.secondes', { s: s });
}

/* Une fois par seconde, les lignes en cours se mettent a jour d'elles-memes :
   plus d'horloge figee entre deux paliers ni pendant le chargement du modele. */
setInterval(() => {
  for (const [id, it] of etat.fichiers) {
    if (!ETATS_ACTIFS.includes(it.etat)) continue;
    const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
    const temps = ligne && ligne.querySelector('.temps');
    if (temps) temps.innerHTML = tempsActif(it);
    const prog = progressionAffichee(it);
    if (ligne && prog.estimee) {
      const barre = ligne.querySelector('.barre');
      if (barre.classList.contains('indeterminee')) { majLigne(id); continue; }
      barre.querySelector('span').style.width = prog.pct + '%';
      barre.setAttribute('aria-valuenow', String(prog.pct));
      ligne.querySelector('.pourcentage').textContent = t('ui.ligne.pct_environ', { pct: prog.pct });
    }
  }
  majActivite();
}, 1000);

window.onEtat = function (id, nouvelEtat, message) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  if (nouvelEtat === 'decodage' || !it.depart) it.depart = Date.now();
  if (!ETATS_ACTIFS.includes(nouvelEtat)) { it.restant_s = undefined; it.indetermine = false; }
  const devientActif = ETATS_ACTIFS.includes(nouvelEtat) && !ETATS_ACTIFS.includes(it.etat);
  it.etat = nouvelEtat;
  it.message = message;
  if (nouvelEtat !== 'attente') it.phase = message;
  if (devientActif) it.indetermine = true;
  majLigne(id);
  if (ETATS_ACTIFS.includes(nouvelEtat)) {
    setEtat(etatPassage(id) + t('ui.etat.en_cours', { message: message, nom: it.nom }), 'actif');
  }
};

window.onProgression = function (id, d) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  const changePhase = it.phase !== d.phase || it.indetermine !== !!d.indetermine;
  Object.assign(it, { pct: d.pct, phase: d.phase, ecoule: d.ecoule, restant: d.restant,
    indetermine: !!d.indetermine });
  // Python fait foi pour le temps ecoule (une reprise y ajoute le calcul deja
  // fait) ; l'interface le fait avancer seule entre deux releves.
  if (typeof d.ecoule_s === 'number') it.depart = Date.now() - d.ecoule_s * 1000;
  it.restant_s = typeof d.restant_s === 'number' ? d.restant_s : undefined;
  it.restant_recu = Date.now();
  const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
  if (ligne && ligne.classList.contains('active') && !changePhase) {
    const barre = ligne.querySelector('.barre');
    barre.querySelector('span').style.width = d.pct + '%';
    barre.setAttribute('aria-valuenow', String(d.pct));
    ligne.querySelector('.pourcentage').textContent = `${d.pct} %`;
    ligne.querySelector('.temps').innerHTML = tempsActif(it);
  } else {
    majLigne(id);
  }
  // Un seul pourcentage : celui de la barre, repris tel quel par la ligne d'etat.
  setEtat(etatPassage(id) + (it.indetermine ? t('ui.etat.en_cours', { message: d.phase, nom: it.nom })
    : t('ui.etat.progression', { phase: d.phase, pct: d.pct, nom: it.nom })), 'actif');
  majActivite();
};

window.onFichierTermine = function (id, d) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  if (d.ok) {
    it.etat = 'termine';
    it.sorties = d.sorties || [];
    it.duree_calcul = d.duree;
    it.facteur = d.facteur;
    it.locuteurs = d.locuteurs;
    it.corrections = d.corrections;
    it.voix_non_separees = !!d.voix_non_separees;
    rafraichirDurees();
  } else if (d.annule) {
    it.etat = 'annule';
    it.message = t('ui.ligne.arrete');
  } else {
    it.etat = 'erreur';
    it.titre = d.titre;
    it.message = d.plantage_moteur ? '' : d.message;
    it.reprise = d.reprise || '';
  }
  if (d.ok) {
    // Une transcription finie quitte la file et rejoint « Transcriptions », en
    // tete, marquee « Terminé à l'instant » : plus de doublon entre les deux.
    const texte = (it.sorties || []).find((s) => s.format === 'TXT') || (it.sorties || [])[0];
    if (texte) {
      etat.recents.set(String(texte.chemin).toLowerCase(), {
        quand: Date.now(), duree: it.duree_calcul, locuteurs: it.locuteurs, corrections: it.corrections,
      });
      etat.fichiers.delete(id);
      pywebview.api.retirer(id);
      dessinerFile();
      dessinerHistorique();
      majBoutons();
      return;
    }
  }
  majLigne(id);
  majBoutons();
};

window.onFileTerminee = function (d) {
  etat.enCours = false;
  etat.passage = [];
  majBoutons();
  if (d.echecs) {
    setEtat(t('ui.etat.bilan_echecs', { reussis: tn('ui.etat.reussies', d.reussis), echecs: tn('ui.etat.echecs', d.echecs) }), 'erreur');
  } else if (d.annules) {
    setEtat(tn('ui.etat.bilan_arrete', d.reussis), '');
  } else if (d.voix_non_separees && (((etat.diarisation || {}).extension) || {}).installee) {
    setEtat(tn('ui.etat.bilan_ok_sans_voix', d.reussis), 'attention');
  } else {
    setEtat(tn('ui.etat.bilan_ok', d.reussis), 'succes');
  }
  const bilan = [d.reussis ? tn('ui.etat.reussies', d.reussis) : '', d.echecs ? tn('ui.etat.echecs', d.echecs) : '',
    d.annules ? tn('ui.etat.annulees', d.annules) : ''].filter(Boolean).join(', ');
  journaliser(d.echecs ? 'attention' : 'ok', t('ui.etat.file_terminee', { bilan: bilan }));
  pywebview.api.charger_historique();
  majRythme();
  // Un fichier arrete en route laisse une reprise : elle est proposee tout de
  // suite, sans attendre le prochain demarrage de l'application.
  pywebview.api.liste_reprises().then((liste) => {
    etat.reprises = liste || [];
    dessinerReprises();
    dessinerFile();  // Reprendre ou Relancer, selon ce qui a ete garde
  }).catch(() => { /* sans consequence */ });
};

window.onJournal = function (niveau, texte) {
  journaliser(niveau, texte);
};

window.finDepot = function () {
  $('#zone-depot').classList.remove('survol');
};

/* ---------------------------------------------------------------- Modales */

/* Modales accessibles : chaque fenetre est un dialogue nomme par son titre,
   le reste de la page devient inerte tant qu'elle est ouverte (la tabulation
   ne passe plus derriere), le focus y entre a l'ouverture et revient a
   l'element de depart a la fermeture. */
function preparerModales() {
  $$('.voile .modale').forEach((m, i) => {
    m.setAttribute('role', 'dialog');
    m.setAttribute('aria-modal', 'true');
    const titre = m.querySelector('.modale-entete h2');
    if (titre) {
      if (!titre.id) titre.id = 'titre-modale-' + i;
      m.setAttribute('aria-labelledby', titre.id);
    }
  });
  $$('.voile .bouton-icone[data-fermer]').forEach((b) => {
    if (!b.dataset.i18nAria) b.dataset.i18nAria = 'ui.bouton.fermer';
  });
}

const pileFocus = [];

function majInertie() {
  const ouvertes = $$('.voile.ouvert');
  const dessus = ouvertes[ouvertes.length - 1] || null;
  Array.from(document.body.children).forEach((el) => {
    if (el.tagName === 'SCRIPT' || el.tagName === 'svg' || el.id === 'btn-corriger-selection') return;
    el.inert = !!dessus && el !== dessus;
  });
}

function ouvrirModale(selecteur) {
  const voile = $(selecteur);
  if (!voile.classList.contains('ouvert')) pileFocus.push(document.activeElement);
  voile.classList.add('ouvert');
  majInertie();
  setTimeout(() => {
    if (voile.contains(document.activeElement)) return;
    const cible = voile.querySelector('input:not([readonly]):not([type=hidden]):not([type=checkbox]), textarea, select')
      || voile.querySelector('.modale-pied .bouton-accent:not([hidden])')
      || voile.querySelector('.modale');
    if (cible) {
      if (!cible.hasAttribute('tabindex') && cible.classList.contains('modale')) cible.setAttribute('tabindex', '-1');
      cible.focus({ preventScroll: true });
    }
  }, 30);
}

function fermerModale(el) {
  const etaitOuverte = el.classList.contains('ouvert');
  el.classList.remove('ouvert');
  majInertie();
  if (etaitOuverte) {
    const retour = pileFocus.pop();
    if (retour && retour.focus && document.contains(retour)) retour.focus({ preventScroll: true });
  }
  if (el.id === 'modale-correction' && typeof masquerBoutonCorrection === 'function') masquerBoutonCorrection();
}

/* Piege du focus : Tab et Maj+Tab tournent dans la fenetre du dessus. */
function pieger(e) {
  const ouvertes = $$('.voile.ouvert');
  const voile = ouvertes[ouvertes.length - 1];
  if (!voile || e.key !== 'Tab') return;
  const focusables = Array.from(voile.querySelectorAll(
    'button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])'))
    .filter((x) => !x.disabled && !x.hidden && x.offsetParent !== null);
  if (!focusables.length) return;
  const premier = focusables[0];
  const dernier = focusables[focusables.length - 1];
  if (e.shiftKey && (document.activeElement === premier || !voile.contains(document.activeElement))) {
    e.preventDefault(); dernier.focus();
  } else if (!e.shiftKey && (document.activeElement === dernier || !voile.contains(document.activeElement))) {
    e.preventDefault(); premier.focus();
  }
}

/* Echap ferme la fenetre du dessus, pas la pile entiere : depuis la correction,
   on revient a la relecture, on n'en est pas ejecte. */
function fermerDerniereModale() {
  const ouvertes = $$('.voile.ouvert');
  if (!ouvertes.length) return false;
  const dessus = ouvertes[ouvertes.length - 1];
  if (dessus.id === 'modale-accueil') { fermerAccueil(false); return true; }
  fermerModale(dessus);
  return true;
}


/* ------------------------------------------------------- Theme et zoom */

function appliquerTheme(mode) {
  if (mode === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', mode);
  etat.config.theme = mode;
  const choix = $('#choix-theme');
  if (choix) choix.value = mode;
  const bouton = $('#btn-theme');
  if (bouton) {
    const nom = t(mode === 'auto' ? 'ui.theme.auto' : `ui.theme.${mode}_nom`);
    bouton.title = t('ui.entete.theme_etat', { theme: nom });
    bouton.setAttribute('aria-label', bouton.title);
  }
}

function themeSuivant() {
  /* Comme le systeme, puis sombre, puis clair : les trois choix de Reglages,
     Application, atteignables depuis l'en-tete. */
  const ordre = ['auto', 'sombre', 'clair'];
  const suivant = ordre[(ordre.indexOf(etat.config.theme || 'auto') + 1) % ordre.length];
  appliquerTheme(suivant);
  enregistrer({ theme: suivant });
}

function appliquerZoom(valeur) {
  etat.config.zoom = Math.min(1.6, Math.max(0.7, valeur));
  document.body.style.zoom = etat.config.zoom;
  mesurerFenetre();
}

/* Taille de la fenetre divisee par le grossissement, publiee en variables CSS.
   Voir le commentaire de :root dans styles.css. */
function mesurerFenetre() {
  const grossissement = etat.config.zoom || 1;
  const style = document.documentElement.style;
  style.setProperty('--hauteur-fenetre', `${window.innerHeight / grossissement}px`);
  style.setProperty('--largeur-fenetre', `${window.innerWidth / grossissement}px`);
  // Largeur utile, grossissement compris : elle choisit la disposition etroite.
  const utile = window.innerWidth / grossissement;
  document.documentElement.classList.toggle('etroit', utile < 900);
  document.documentElement.classList.toggle('tres-etroit', utile < 660);
}

window.addEventListener('resize', mesurerFenetre);

/* Vitesses de lecture, au separateur decimal de la langue. */
function remplirVitesses() {
  const choix = $('#rl-vitesse');
  const valeur = choix.value || '1';
  choix.innerHTML = [0.75, 1, 1.25, 1.5, 1.75, 2].map((v) =>
    `<option value="${v}">${ech(t('ui.rl.vitesse_valeur', { v: String(v).replace('.', t('format.decimal')) }))}</option>`).join('');
  choix.value = valeur;
}

/* ------------------------------------------------------------ Cablage UI */

document.addEventListener('DOMContentLoaded', () => {
  // Langue provisoire, le temps que Python reponde : celle du dernier
  // lancement, sinon celle du navigateur integre. Evite une fenetre vide.
  definirLangue(langueProvisoire());
  preparerModales();
  traduirePage();
  remplirVitesses();

  dessinerFile();
  dessinerHistorique();
  brancherRadios('#segments-rythme');
  brancherRadios('#bloc-rythme .rythmes');

  // Navigation
  $('#btn-nav-reglages').addEventListener('click', () =>
    (etat.vue === 'reglages' ? retourPrincipale() : ouvrirReglages()));
  $('#btn-nav-vocabulaire').addEventListener('click', () =>
    (etat.vue === 'vocabulaire' ? retourPrincipale() : ouvrirVocabulaire()));
  $$('[data-retour]').forEach((b) => b.addEventListener('click', retourPrincipale));
  $('#indic-activite').addEventListener('click', retourPrincipale);
  $('#btn-tous-reglages').addEventListener('click', () => ouvrirReglages('transcription'));
  $$('.reglages-nav [role=tab]').forEach((b) => {
    b.addEventListener('click', () => afficherSection(b.dataset.section, true));
  });
  $('.reglages-nav').addEventListener('keydown', (e) => {
    if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    const onglets = $$('.reglages-nav [role=tab]');
    const i = onglets.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    let j = i + ((e.key === 'ArrowDown' || e.key === 'ArrowRight') ? 1 : -1);
    if (e.key === 'Home') j = 0;
    if (e.key === 'End') j = onglets.length - 1;
    const cible = onglets[(j + onglets.length) % onglets.length];
    afficherSection(cible.dataset.section, true);
    cible.focus();
  });

  $('#btn-theme').addEventListener('click', themeSuivant);
  $('#rl-aide').addEventListener('click', ouvrirAide);
  $('#rl-activite').addEventListener('click', retourPrincipale);
  $('#btn-aide').addEventListener('click', ouvrirAide);
  $('#btn-aide-maj').addEventListener('click', verifierMajDepuisAide);
  $('#btn-ouvrir-app').addEventListener('click', () => pywebview.api.ouvrir_dossier_application());
  $('#choix-theme').addEventListener('change', (e) => {
    appliquerTheme(e.target.value);
    enregistrer({ theme: e.target.value });
  });

  // Accueil du premier lancement
  $('#btn-accueil-appliquer').addEventListener('click', () => fermerAccueil(true));
  $('#btn-accueil-garder').addEventListener('click', () => fermerAccueil(false));

  // Depot de fichiers. Le chemin reel est recupere cote Python : un navigateur
  // ne le communique jamais au JavaScript.
  const zone = $('#zone-depot');
  zone.addEventListener('click', () => pywebview.api.ajouter_fichiers());
  zone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pywebview.api.ajouter_fichiers(); }
  });
  ['dragenter', 'dragover'].forEach((evt) => {
    document.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.add('survol');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    document.addEventListener(evt, (e) => {
      e.preventDefault();
      if (evt === 'dragleave' && e.relatedTarget) return;
      zone.classList.remove('survol');
    });
  });

  // File et transcriptions
  $('#btn-vider').addEventListener('click', retirerTermines);
  $('#recherche-historique').addEventListener('input', dessinerHistorique);
  $('#btn-ouvrir-sorties').addEventListener('click', () => pywebview.api.ouvrir_dossier_sortie());

  // Bandeau de lancement
  $$('#segments-rythme .segment').forEach((b) => {
    b.addEventListener('click', () => {
      if ((etat.rythme || {}).choisi !== b.dataset.rythme) rafraichirRythme({ rythme: b.dataset.rythme });
    });
  });
  $('#opt-voix-lancement').addEventListener('change', (e) => {
    $('#opt-diarisation').checked = e.target.checked;
    $('#opt-diarisation').dispatchEvent(new Event('change'));
  });

  // Reglages simples
  $('#langue').addEventListener('change', (e) => {
    enregistrer({ langue: e.target.value });
    majQualiteLangue();
  });

  // Langue de l'interface : sans effet sur la langue parlee.
  $('#langue-interface').addEventListener('change', (e) => {
    changerLangueInterface(e.target.value);
  });

  // Nom des fichiers produits : apercu pendant la frappe, enregistrement quand
  // le champ est quitte ou valide.
  $('#motif-sortie').addEventListener('input', () => {
    clearTimeout(minuteurMotif);
    minuteurMotif = setTimeout(majApercuMotif, 150);
  });
  $('#motif-sortie').addEventListener('change', enregistrerMotif);
  $('#motif-sortie').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
  });

  // Dossier surveille
  $('#opt-surveillance').addEventListener('change', (e) => {
    if (e.target.checked && !$('#dossier-surveille').value) {
      // Rien a surveiller encore : on ouvre directement le selecteur.
      $('#bloc-surveillance').style.display = 'block';
      pywebview.api.choisir_dossier_surveille();
      return;
    }
    appliquerSurveillance(e.target.checked);
  });
  $('#btn-dossier-surveille').addEventListener('click', () =>
    pywebview.api.choisir_dossier_surveille());
  $('#btn-ouvrir-surveille').addEventListener('click', () =>
    pywebview.api.ouvrir_dossier_surveille());
  $('#btn-oublier-surveilles').addEventListener('click', async () => {
    const r = await pywebview.api.oublier_fichiers_surveilles();
    retourSurveillance(r);
  });

  // Verification de mise a jour et barre des taches
  $('#opt-maj').addEventListener('change', async (e) => {
    await enregistrer({ maj_verifier: e.target.checked });
    $('#retour-maj').innerHTML = encartInfo(
      t(e.target.checked ? 'ui.maj.activee' : 'ui.maj.coupee'));
    setTimeout(() => { $('#retour-maj').innerHTML = ''; }, 10000);
    if (e.target.checked) pywebview.api.verifier_maj(true);
    else { $('#bandeau-maj').style.display = 'none'; etat.maj = null; }
  });
  $('#opt-barre-taches').addEventListener('change', (e) =>
    enregistrer({ barre_taches: e.target.checked }));
  $('#opt-prevenir-fin').addEventListener('change', (e) =>
    enregistrer({ prevenir_fin: e.target.checked }));
  $('#btn-maj-page').addEventListener('click', () => {
    if (etat.maj && etat.maj.url) pywebview.api.ouvrir_lien(etat.maj.url);
  });
  $('#btn-maj-fermer').addEventListener('click', () => {
    $('#bandeau-maj').style.display = 'none';
  });

  $('#btn-dossier').addEventListener('click', () => pywebview.api.choisir_dossier_sortie());
  $('#btn-ouvrir-dossier').addEventListener('click', () => pywebview.api.ouvrir_dossier_sortie());

  const formats = () => ({
    txt: $('#fmt-txt').checked, srt: $('#fmt-srt').checked,
    vtt: $('#fmt-vtt').checked, horodatage: $('#fmt-horodatage').checked,
  });
  ['#fmt-txt', '#fmt-srt', '#fmt-vtt', '#fmt-horodatage'].forEach((s) => {
    $(s).addEventListener('change', () => {
      if (!$('#fmt-txt').checked && !$('#fmt-srt').checked && !$('#fmt-vtt').checked) {
        $('#fmt-txt').checked = true;
        journaliser('attention', t('ui.format.un_minimum'));
      }
      enregistrer({ formats: formats() });
    });
  });

  $('#opt-glossaire').addEventListener('change', (e) =>
    enregistrer({ utiliser_glossaire: e.target.checked }));
  $('#opt-corrections').addEventListener('change', (e) =>
    enregistrer({ appliquer_corrections: e.target.checked }));

  $('#opt-diarisation').addEventListener('change', (e) => {
    enregistrer({ diarisation: e.target.checked });
    majDiarisation();
    rafraichirEstimations();
    if (e.target.checked && !etat.diarisation.jeton_present) ouvrirModaleJeton();
  });
  $('#nb-locuteurs').addEventListener('change', (e) =>
    enregistrer({ nb_locuteurs: parseInt(e.target.value, 10) || 0 }));

  // Dossier des modeles
  $('#btn-dossier-modeles').addEventListener('click', () => {
    $('#retour-modeles').innerHTML = '';
    pywebview.api.choisir_dossier_modeles();
  });
  $('#btn-ouvrir-modeles').addEventListener('click', () =>
    pywebview.api.ouvrir_dossier_modeles());

  // Import et export des donnees personnelles
  $('#btn-exporter-donnees').addEventListener('click', () => {
    $('#retour-donnees').innerHTML = '';
    pywebview.api.exporter_donnees();
  });
  $('#btn-importer-donnees').addEventListener('click', () => {
    $('#retour-donnees').innerHTML = '';
    pywebview.api.choisir_import();
  });
  $('#btn-confirmer-import').addEventListener('click', confirmerImport);

  $('#opt-avance').addEventListener('change', (e) => {
    $('#bloc-avance').style.display = e.target.checked ? 'block' : 'none';
    enregistrer({ mode_avance: e.target.checked });
    rafraichirEstimations();
  });
  $('#modele-avance').addEventListener('change', (e) => {
    enregistrer({ modele_avance: e.target.value });
    rafraichirEstimations();
  });
  $('#beam').addEventListener('change', (e) =>
    enregistrer({ beam_size: parseInt(e.target.value, 10) || 0 }));
  $('#opt-contexte').addEventListener('change', (e) =>
    enregistrer({ condition_on_previous_text: e.target.checked }));
  $('#opt-salle').addEventListener('change', (e) =>
    enregistrer({ filtres_salle: e.target.checked }));
  $('#opt-processeur').addEventListener('change', (e) =>
    enregistrer({ forcer_processeur: e.target.checked }));

  // Glossaire et corrections (ancien format)
  $('#btn-glossaire').addEventListener('click', async () => {
    const d = await pywebview.api.etat_initial();
    $('#zone-glossaire').value = d.glossaire.contenu || '';
    $('#retour-glossaire').innerHTML = encartInfo(d.glossaire.resume.message);
    ouvrirModale('#modale-glossaire');
  });
  $('#btn-enregistrer-glossaire').addEventListener('click', async () => {
    const resume = await pywebview.api.sauver_glossaire($('#zone-glossaire').value);
    majGlossaire(resume);
    $('#retour-glossaire').innerHTML = resume.tronque
      ? encartAttention(resume.message) : encartSucces(resume.message);
    journaliser('ok', t('ui.voc.glossaire_enregistre', { message: resume.message }));
    setTimeout(() => fermerModale($('#modale-glossaire')), 700);
  });

  $('#btn-corrections').addEventListener('click', async () => {
    const d = await pywebview.api.etat_initial();
    $('#zone-corrections').value = d.corrections.contenu || '';
    $('#retour-corrections').innerHTML = '';
    ouvrirModale('#modale-corrections');
  });
  $('#btn-enregistrer-corrections').addEventListener('click', async () => {
    const r = await pywebview.api.sauver_corrections($('#zone-corrections').value);
    majCorrections(r);
    $('#retour-corrections').innerHTML = r.erreurs.length
      ? r.erreurs.map(encartAttention).join('')
      : encartSucces(tn('ui.voc.regles_enregistrees', r.nb));
    journaliser('ok', tn('ui.voc.regles_enregistrees', r.nb));
    if (!r.erreurs.length) setTimeout(() => fermerModale($('#modale-corrections')), 700);
  });

  // Vocabulaire, format 2
  brancherVocabulaire();

  // Relecture : options
  $('#opt-compagnon').addEventListener('change', (e) =>
    enregistrer({ compagnon_confiance: e.target.checked }));
  $('#opt-apprises').addEventListener('change', (e) =>
    enregistrer({ corrections_apprises: e.target.checked }));
  $('#opt-sauvegarde').addEventListener('change', (e) =>
    enregistrer({ sauvegarde_progressive: e.target.checked }));

  // Gabarit d'instructions pour l'IA
  $('#btn-gabarit').addEventListener('click', async () => {
    const g = await pywebview.api.lire_gabarit();
    $('#zone-gabarit').value = g.contenu || '';
    $('#retour-gabarit').innerHTML = encartInfo(t('ui.gabarit.fichier', { chemin: g.chemin }));
    ouvrirModale('#modale-gabarit');
  });
  $('#btn-enregistrer-gabarit').addEventListener('click', async () => {
    const r = await pywebview.api.sauver_gabarit($('#zone-gabarit').value);
    $('#retour-gabarit').innerHTML = encartSucces(r.message);
    journaliser('ok', t('ui.gabarit.enregistre'));
    setTimeout(() => fermerModale($('#modale-gabarit')), 700);
  });

  // Installation de la separation des locuteurs
  $('#btn-installer-locuteurs').addEventListener('click', ouvrirModaleExtension);
  $('#btn-confirmer-extension').addEventListener('click', lancerInstallationLocuteurs);
  $('#btn-annuler-locuteurs').addEventListener('click', async () => {
    $('#btn-annuler-locuteurs').disabled = true;
    await pywebview.api.annuler_installation_locuteurs();
    $('#btn-annuler-locuteurs').disabled = false;
  });
  $('#btn-retirer-locuteurs').addEventListener('click', async () => {
    const r = await pywebview.api.retirer_locuteurs();
    if (r.extension) etat.diarisation.extension = r.extension;
    if (r.ok) {
      etat.diarisation.disponible = false;
      etat.diarisation.indisponibilite = '';
      $('#opt-diarisation').checked = false;
      enregistrer({ diarisation: false });
    }
    $('#ext-retour').innerHTML = r.ok ? encartInfo(r.message) : encartAttention(r.message);
    journaliser(r.ok ? 'info' : 'erreur', r.message);
    majDiarisation();
  });

  // Moteur OpenVINO, banc d'essai, poste
  $('#btn-installer-openvino').addEventListener('click', installerOpenvino);
  $('#btn-annuler-openvino').addEventListener('click', () => pywebview.api.annuler_installation_openvino());
  $('#btn-retirer-openvino').addEventListener('click', async () => {
    const r = await pywebview.api.retirer_openvino();
    if (r.vitesse) etat.vitesse = r.vitesse;
    $('#ov-retour').innerHTML = r.ok ? encartInfo(r.message) : encartAttention(r.message);
    journaliser(r.ok ? 'info' : 'erreur', r.message);
    majVitesse();
  });
  $('#btn-lancer-banc').addEventListener('click', lancerBanc);
  $('#btn-arreter-banc').addEventListener('click', () => {
    $('#banc-message').textContent = t('ui.banc.arret_demande');
    pywebview.api.arreter_banc();
  });
  $('#btn-appliquer-banc').addEventListener('click', appliquerBanc);
  $('#btn-copier-banc').addEventListener('click', () => {
    pywebview.api.copier($('#banc-rapport').value || '');
    journaliser('ok', t('ui.banc.copie'));
  });
  $('#btn-reglage-auto').addEventListener('click', revenirReglageAuto);
  $('#btn-reconnaitre').addEventListener('click', reconnaitrePoste);
  $('#btn-proposition-appliquer').addEventListener('click', appliquerProposition);
  $('#btn-proposition-plus-tard').addEventListener('click', () => {
    afficherProposition(null);
    pywebview.api.ecarter_proposition();
  });
  $$('#bloc-rythme .rythme').forEach((b) => {
    b.addEventListener('click', () => {
      if ((etat.rythme || {}).choisi !== b.dataset.rythme) rafraichirRythme({ rythme: b.dataset.rythme });
    });
  });
  $('#opt-rythme-auto').addEventListener('change', (e) =>
    rafraichirRythme({ rythme_auto: e.target.checked }));
  $('#btn-comp-fichier').addEventListener('click', () => pywebview.api.choisir_fichier_comparaison('audio'));
  $('#btn-comp-reference').addEventListener('click', () => pywebview.api.choisir_fichier_comparaison('reference'));
  $('#btn-comp-lancer').addEventListener('click', lancerComparaison);
  $('#btn-comp-arreter').addEventListener('click', () => pywebview.api.arreter_comparaison());
  $('#btn-comp-ouvrir').addEventListener('click', () => {
    if (comparaison.page) pywebview.api.ouvrir(comparaison.page);
  });
  $('#btn-comp-copier').addEventListener('click', () => {
    pywebview.api.copier($('#comp-rapport').value || '');
    journaliser('ok', t('ui.banc.copie'));
  });

  // Jeton Hugging Face
  $('#btn-jeton').addEventListener('click', ouvrirModaleJeton);
  $('#btn-lien-conditions').addEventListener('click', () =>
    pywebview.api.ouvrir_lien(etat.diarisation.guide.url_conditions));
  $('#btn-lien-jeton').addEventListener('click', () =>
    pywebview.api.ouvrir_lien(etat.diarisation.guide.url_jeton));
  $('#btn-enregistrer-jeton').addEventListener('click', async () => {
    const r = await pywebview.api.enregistrer_jeton($('#champ-jeton').value);
    $('#retour-jeton').innerHTML = r.ok ? encartSucces(r.message) : encartAttention(r.message);
    if (r.ok) {
      etat.diarisation.jeton_present = !!$('#champ-jeton').value.trim();
      majDiarisation();
      journaliser('ok', r.message);
    }
  });
  $('#btn-effacer-jeton').addEventListener('click', async () => {
    await pywebview.api.enregistrer_jeton('');
    etat.diarisation.jeton_present = false;
    $('#champ-jeton').value = '';
    $('#retour-jeton').innerHTML = encartInfo(t('ui.modale.jeton.efface'));
    majDiarisation();
  });

  // Apercu
  $('#btn-ouvrir-apercu').addEventListener('click', () => {
    if (etat.apercuChemin) pywebview.api.ouvrir(etat.apercuChemin);
  });
  $('#btn-copier-apercu').addEventListener('click', async () => {
    const texte = $('#contenu-apercu').textContent;
    try { await navigator.clipboard.writeText(texte); }
    catch (e) { pywebview.api.copier(texte); }
    journaliser('ok', t('ui.apercu.copie'));
  });

  // Journal
  $('#btn-fichier-log').addEventListener('click', () => pywebview.api.ouvrir_journal());

  // Actions
  $('#btn-lancer').addEventListener('click', lancer);
  $('#btn-arreter').addEventListener('click', () => {
    pywebview.api.arreter();
    $('#btn-arreter').disabled = true;
    setEtat(t('ui.etat.arret'), '');
  });

  // Modales : fermeture
  $$('[data-fermer]').forEach((b) => {
    b.addEventListener('click', () => fermerModale(b.closest('.voile')));
  });
  $$('.voile').forEach((v) => {
    v.addEventListener('mousedown', (e) => {
      if (e.target === v && v.id !== 'modale-accueil') fermerModale(v);
    });
  });

  // Raccourcis de toute l'application. Ceux de la relecture sont dans
  // web/relecture.js, ceux du vocabulaire sur sa liste.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') { pieger(e); return; }
    if (e.key === 'Escape') {
      if (fermerDerniereModale()) return;
      if (etat.vue === 'relecture' && typeof echapRelecture === 'function' && echapRelecture()) return;
      if (etat.vue === 'vocabulaire' && !$('#voc-edition').hidden) { fermerEditionVocabulaire(); return; }
      if (etat.vue !== 'principale') { retourPrincipale(); return; }
      return;
    }
    const modaleOuverte = !!$('.voile.ouvert');
    if (e.ctrlKey && (e.key === 'o' || e.key === 'O')) {
      e.preventDefault();
      if (!modaleOuverte) pywebview.api.ajouter_fichiers();
      return;
    }
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      if (!modaleOuverte && !$('#btn-lancer').disabled) lancer();
      return;
    }
    if (e.ctrlKey && (e.key === '+' || e.key === '=')) { e.preventDefault(); zoom(0.1); }
    if (e.ctrlKey && e.key === '-') { e.preventDefault(); zoom(-0.1); }
    if (e.ctrlKey && e.key === '0') { e.preventDefault(); appliquerZoom(1); enregistrer({ zoom: 1 }); }
  });
  // Retour sur la fenetre apres une fin de file : le titre redevient normal.
  window.addEventListener('focus', () => {
    try { pywebview.api.titre_normal(); } catch (e) { /* sans consequence */ }
  });
  document.addEventListener('wheel', (e) => {
    if (e.ctrlKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 0.05 : -0.05); }
  }, { passive: false });
});

function zoom(delta) {
  appliquerZoom((etat.config.zoom || 1) + delta);
  enregistrer({ zoom: etat.config.zoom });
}

async function lancer() {
  if (etat.enCours) return;
  const retour = await pywebview.api.demarrer();
  if (!retour.ok) {
    journaliser('erreur', retour.message);
    setEtat(retour.message, 'erreur');
    return;
  }
  etat.enCours = true;
  etat.passage = Array.from(etat.fichiers.entries()).filter(([, f]) => f.etat === 'attente').map(([id]) => id);
  majBoutons();
  majRythme();
  setEtat(t('ui.etat.demarrage'), 'actif');
}

function encartInfo(m) {
  return `<div class="encart encart-info">${icone('i-info', 'icone-s')}<span>${ech(m)}</span></div>`;
}
function encartSucces(m) {
  return `<div class="encart encart-succes">${icone('i-coche', 'icone-s')}<span>${ech(m)}</span></div>`;
}
function encartAttention(m) {
  return `<div class="encart encart-attention">${icone('i-alerte', 'icone-s')}<span>${ech(m)}</span></div>`;
}


/* --------------------------------------------------- Etat du moteur, au pied

   Le processus moteur (app/superviseur.py) : au repos, chargement,
   transcription, arrete, en panne. Montre tant qu'il vit, et apres une panne
   (avec sa cause en infobulle) ; rien quand il est simplement arrete. */
let derniereVueMoteur = '';
/* « deepdml/faster-whisper-large-v3-turbo-ct2 » devient « large-v3-turbo ». */
function nomCourtModele(modele) {
  return String(modele || '').split(/[\\/]/).pop()
    .replace(/^faster-whisper-|^whisper-/i, '').replace(/-ct2$|-int8-ov$|-fp16-ov$|-ov$/i, '');
}
async function majEtatMoteur() {
  if (!etat.pret || !(window.pywebview && window.pywebview.api)) return;
  let m = null;
  try { m = await appelPasserelle('moteur_etat'); } catch (e) { m = null; }
  const el = $('#etat-moteur');
  if (!m || !m.etat || (m.etat === 'arrete' && !etat.enCours)) {
    el.hidden = true;
    derniereVueMoteur = '';
    return;
  }
  const texte = t('ui.moteur.etat', { etat: t('ui.moteur.' + m.etat) })
    + (m.modele && ['chargement', 'transcription', 'repos'].includes(m.etat) ? ` (${nomCourtModele(m.modele)})` : '');
  if (texte === derniereVueMoteur && !el.hidden) return;
  derniereVueMoteur = texte;
  el.hidden = false;
  el.textContent = texte;
  el.className = 'etat-moteur ' + (m.etat === 'panne' ? 'panne' : '');
  el.title = m.etat === 'panne' && m.derniere_panne
    ? t('ui.moteur.panne_detail', { code: m.derniere_panne.code, date: String(m.derniere_panne.date || '').replace('T', ' ') })
    : '';
}
setInterval(majEtatMoteur, 2000);
