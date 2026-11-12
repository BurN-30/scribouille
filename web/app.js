/* =========================================================================
   Scribouille : logique d'interface

   Le Python appelle les fonctions globales onXxx() definies plus bas.
   L'interface appelle Python via pywebview.api.*

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
  extensionEnCours: false,   // installation de la separation des locuteurs en cours
  vitesse: {},               // moteur OpenVINO, reglage de vitesse, banc d'essai
  rythme: {},                // vitesse maximale, equilibre ou discret, adaptation
  ovEnCours: false,          // installation d'OpenVINO en cours
  bancEnCours: false,        // banc d'essai en cours
  modeles: { dossier: '', presets: [] },
  versionInstallee: false,
  enCours: false,
  apercuChemin: null,
  importChemin: null,
  reprises: [],
  lecture: null,          // transcription ouverte dans la vue de lecture
  selection: '',          // expression selectionnee, en attente de correction
  surveillance: { actif: false, dossier: '', probleme: '' },
  maj: null,              // version plus recente annoncee par le bandeau
  version: '',            // version installee, affichee dans l'aide
  majEnCours: false,      // verification demandee a la main, en vol
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

/* ------------------------------------------------------------ Demarrage */

window.addEventListener('pywebviewready', async () => {
  try {
    const donnees = await pywebview.api.etat_initial();
    initialiser(donnees);
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

  // Python fait autorite sur la langue : il l'a detectee au premier lancement
  // et l'a rangee dans la configuration. La langue provisoire posee au
  // chargement du document n'a servi qu'a eviter une fenetre vide.
  if (etat.config.langue_interface) definirLangue(etat.config.langue_interface);
  traduirePage();

  etat.version = String(d.version || '');
  $('#version').textContent = 'v' + d.version;
  $('#aide-maj-version').textContent = etat.version;
  appliquerTheme(etat.config.theme || 'auto');
  appliquerZoom(etat.config.zoom || 1);

  dessinerMateriel(d.materiel, d.recommandation);
  dessinerPresets(d.recommandation);
  remplirModelesAvances(d.modeles_avances || []);
  appliquerConfig();
  majGlossaire(d.glossaire ? d.glossaire.resume : null);
  majCorrections(d.corrections || {});
  majDiarisation();
  majVitesse();
  majRythme();
  if (d.proposition) afficherProposition(d.proposition);
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
    journaliser('info', t('ui.journal.pret', { fichier: d.journal }));
  }

  etat.pret = true;
  majBoutons();
  pywebview.api.charger_historique();
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
  journaliser('info', t('ui.journal.langue'));
}

/* -------------------------------------------------------------- Materiel */

function dessinerMateriel(mat, reco) {
  $('#materiel-resume').textContent = mat.resume;
  $('#materiel-conseil').textContent = reco.phrase;

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
  if (!mat.gpus.length) ajout(t('ui.materiel.gpu'), t('ui.materiel.sans_gpu'));
  ajout(t('ui.materiel.calcul'), mat.peripherique === 'cuda'
    ? t('ui.materiel.calcul_cuda')
    : t('ui.materiel.calcul_cpu'));
  ajout(t('ui.materiel.systeme'), mat.systeme);

  lignes.push('<div style="height:8px"></div>');
  (reco.estimations || []).forEach((e) => {
    /* Une estimation mesuree sur le poste le dit : c'est la difference entre un
       chiffre repris d'ailleurs et un chiffre releve ici. */
    ajout(e.nom, t(e.mesure ? 'ui.materiel.estimation_mesuree' : 'ui.materiel.estimation', {
      duree: e.pour_une_heure, facteur: nb(e.facteur),
    }));
  });
  lignes.push(`<div class="materiel-ligne"><span class="cle"></span>
    <span class="valeur" style="font-size:11.5px">${ech(t('ui.materiel.avis'))}</span></div>`);

  $('#materiel-detail').innerHTML = lignes.join('');
}

function basculerMateriel() {
  const detail = $('#materiel-detail');
  const ouvert = detail.classList.toggle('ouvert');
  $('#materiel-entete').setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  $('#materiel-chevron').style.transform = ouvert ? 'rotate(180deg)' : '';
}

/* --------------------------------------------------------------- Presets */

function dessinerPresets(reco) {
  const conseille = reco ? reco.preset_conseille : null;
  $('#presets').innerHTML = etat.presets.map((p) => `
    <button class="preset" data-preset="${ech(p.cle)}" aria-pressed="false">
      <span class="titre">
        <span class="marqueur"></span>${ech(p.nom)}
        ${p.cle === conseille ? `<span class="conseille">${ech(t('ui.preset.conseille'))}</span>` : ''}
      </span>
      <span class="desc">${ech(p.resume)}</span>
      <span class="chiffres">${ech(t('ui.preset.chiffres', {
        modele: p.modele, duree: p.pour_une_heure, poids: p.telechargement,
      }))}</span>
    </button>`).join('');

  $$('#presets .preset').forEach((b) => {
    b.addEventListener('click', () => {
      etat.config.preset = b.dataset.preset;
      majPresetActif();
      enregistrer({ preset: etat.config.preset });
      rafraichirEstimations();
    });
  });
  majPresetActif();
}

function majPresetActif() {
  $$('#presets .preset').forEach((b) => {
    b.setAttribute('aria-pressed', b.dataset.preset === etat.config.preset ? 'true' : 'false');
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

/* -------------------------------------------------------------- Reglages */

function appliquerConfig() {
  const c = etat.config;
  $('#langue').value = c.langue || 'fr';
  $('#langue-interface').value = langueCourante();
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
  $('#opt-lecture-audio').checked = !!c.lecture_audio;
  $('#motif-sortie').value = c.motif_sortie || '';
  $('#opt-surveillance').checked = !!c.surveillance;
  $('#dossier-surveille').value = c.dossier_surveille || '';
  $('#bloc-surveillance').style.display = c.surveillance ? 'block' : 'none';
  $('#opt-maj').checked = !!c.maj_verifier;
  $('#opt-barre-taches').checked = c.barre_taches !== false;
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

function afficherAvertissements(liste) {
  $('#avertissements').innerHTML = (liste || []).map((m) => `
    <div class="encart encart-attention">${icone('i-alerte', 'icone-s')}<span>${ech(m)}</span></div>`
  ).join('');
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
    el.textContent += t('ui.voc.lignes_erreur', { n: donnees.erreurs.length });
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
   le detail defile. Une seule ligne qui change a chaque paquet serait
   illisible, et ferait perdre de vue ou l'on en est. */
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
      ? t('ui.ov.absent_hors_ligne', { n: ov.hors_ligne })
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
   Visible seulement quand OpenVINO est installe. La page cote a cote reste
   sur le poste ; le rapport de chiffres peut etre copie. */

const comparaison = { fichier: '', reference: '', page: '', enCours: false };

function majComparaison() {
  const ov = (etat.vitesse || {}).openvino || {};
  $('#comp-bloc').style.display = ov.installee ? 'block' : 'none';
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
    b.setAttribute('aria-checked', b.dataset.rythme === choisi ? 'true' : 'false');
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
}

async function rafraichirRythme(partiel) {
  await enregistrer(partiel);
  try {
    etat.rythme = await pywebview.api.etat_rythme();
  } catch (e) { console.error(e); }
  majRythme();
  rafraichirEstimations();
}

/* Reglage propose pour ce poste : au premier lancement, ou sur demande. */

function afficherProposition(p) {
  const bloc = $('#bloc-proposition');
  if (!p) { bloc.style.display = 'none'; return; }
  $('#proposition-phrase').textContent = p.phrase || '';
  $('#proposition-rythme').textContent = t('ui.proposition.rythme', {
    rythme: t('ui.rythme.' + (p.rythme || 'equilibre')),
  });
  const notes = (p.notes || []).map((n) => encartInfo(n));
  if (p.deja) notes.unshift(encartSucces(t('ui.proposition.deja')));
  $('#proposition-notes').innerHTML = notes.join('');
  $('#btn-proposition-appliquer').style.display = p.deja ? 'none' : '';
  bloc.style.display = 'block';
}

async function reconnaitrePoste() {
  const bouton = $('#btn-reconnaitre');
  bouton.disabled = true;
  $('#banc-retour').innerHTML = encartInfo(t('ui.proposition.recherche'));
  try {
    const p = await pywebview.api.proposer_reglage();
    $('#banc-retour').innerHTML = '';
    afficherProposition(p);
    $('#bloc-proposition').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    console.error(e);
    $('#banc-retour').innerHTML = encartAttention(t('ui.ext.echec_lancement'));
  }
  bouton.disabled = false;
}

async function appliquerProposition() {
  const r = await pywebview.api.appliquer_proposition();
  journaliser(r.ok ? 'ok' : 'attention', r.message);
  if (!r.ok) return;
  afficherProposition(null);
  const d = await pywebview.api.etat_initial();
  initialiser(d, true);
}

async function appliquerBanc() {
  const r = await pywebview.api.appliquer_conseil_banc();
  $('#banc-retour').innerHTML = r.ok ? encartSucces(r.message) : encartAttention(r.message);
  journaliser(r.ok ? 'ok' : 'attention', r.message);
  if (r.ok) {
    // Les estimations, la recommandation et la fiche materiel en dependent :
    // tout est redemande a Python, comme apres un changement de langue.
    const d = await pywebview.api.etat_initial();
    initialiser(d, true);
  }
}

async function revenirReglageAuto() {
  const r = await pywebview.api.revenir_reglage_automatique();
  journaliser('info', r.message);
  const d = await pywebview.api.etat_initial();
  initialiser(d, true);
  $('#banc-retour').innerHTML = encartInfo(r.message);
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
   cales sur les taux d'erreur (WER) publies par OpenAI pour large-v3 sur le
   jeu multilingue FLEURS, regroupes en trois classes : sous 5 %, de 5 a 10 %,
   au-dela de 10 %. Aucune proposition d'un autre modele : large-v3 est deja le
   meilleur multilingue disponible, il n'y a rien a conseiller de mieux. */

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

/* ---------------------------------------------------------- Espace utilise */

function onStockage(mesure) {
  const zone = $('#contenu-stockage');
  if (!mesure || mesure.erreur) {
    zone.innerHTML = encartAttention(t('ui.stockage.echec'));
    return;
  }
  zone.innerHTML = (mesure.postes || []).map((p) => `
    <div class="stockage-poste">
      <div class="entete">
        <span class="libelle">${ech(p.libelle)}</span>
        <span class="taille">${ech(p.taille)}</span>
      </div>
      <div class="chemin">${ech(p.chemin)}</div>
      <div class="detail">${ech(p.detail)}</div>
      <div class="actions-poste">
        <button class="bouton bouton-discret" data-ouvrir-dossier="${ech(p.chemin)}"
          ${p.existe ? '' : 'disabled'}>
          ${icone('i-externe', 'icone-s')}
          ${ech(p.existe ? t('ui.stockage.ouvrir') : t('ui.stockage.absent'))}
        </button>
      </div>
    </div>`).join('')
    + `<div class="stockage-total">
         <span>${ech(t('ui.stockage.total'))}</span>
         <span class="valeur">${ech(mesure.total_texte)}</span>
         <span class="pousse"></span>
         <span style="color:var(--texte-faible)">${ech(t('ui.stockage.libre', {
           libre: mesure.libre,
         }))}</span>
       </div>`;

  $$('#contenu-stockage [data-ouvrir-dossier]').forEach((b) => {
    b.onclick = () => pywebview.api.ouvrir(b.dataset.ouvrirDossier);
  });
}
window.onStockage = onStockage;

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

/* Verification demandee a la main depuis la fenetre d'aide.

   Elle ne passe pas par le reglage d'opt-in : celui-ci ne gouverne que la
   verification passive du demarrage, alors qu'ici l'utilisateur clique. Elle
   ignore aussi la garde des 24 heures, cote Python. Le texte des resultats est
   partage avec le bandeau : aucune formulation n'est ecrite deux fois. */

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
  bloc.push(ligne(t('ui.import.glossaire'),
    t('ui.import.termes', { nb: d.glossaire.nb, actuel: d.glossaire.nb_actuel })));
  bloc.push(ligne(t('ui.import.corrections'),
    t('ui.import.regles', { nb: d.corrections.nb, actuel: d.corrections.nb_actuel })));
  if (d.corrections.erreurs && d.corrections.erreurs.length) {
    bloc.push(encartAttention(
      t('ui.import.regles_fautives', { n: d.corrections.erreurs.length })));
  }
  /* Le gabarit pour l'IA n'est annonce que s'il voyage dans l'archive : une
     archive qui n'en porte pas laisse celui du poste intact. */
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
   glossaire et les corrections d'un seul coup, et un redemarrage serait une
   corvee pour rien. */
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

function dessinerFile() {
  const vue = $('#vue-file');
  $('#compteur-file').textContent = String(etat.fichiers.size);
  if (!etat.fichiers.size) {
    vue.innerHTML = `<div class="vide">${icone('i-depot')}
      <div>${ech(t('ui.file.vide'))}</div>
      <div style="font-size:12px;margin-top:4px">${ech(t('ui.file.vide_aide'))}</div>
    </div>`;
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

function ligneHTML(id) {
  const it = etat.fichiers.get(id);
  const [classe, ic] = PASTILLES[it.etat] || PASTILLES.attente;
  const actif = ['decodage', 'transcription', 'locuteurs', 'ecriture'].includes(it.etat);

  let meta = '', classeMeta = '';
  if (it.etat === 'attente') {
    meta = [it.duree, it.taille,
      it.estimation ? t('ui.ligne.calcul', { duree: it.estimation }) : '']
      .filter(Boolean).join(' · ');
  } else if (actif) {
    meta = [it.phase || it.message,
      it.ecoule ? t('ui.ligne.ecoule', { duree: it.ecoule }) : '',
      it.restant ? t('ui.ligne.restant', { duree: it.restant }) : '']
      .filter(Boolean).join(' · ');
  } else if (it.etat === 'termine') {
    classeMeta = 'succes';
    meta = [t('ui.ligne.termine', { duree: it.duree_calcul || '?' }),
      it.facteur ? t('ui.ligne.facteur', { facteur: nb(it.facteur) }) : '',
      it.locuteurs ? t('ui.ligne.locuteurs', { n: it.locuteurs }) : '',
      it.corrections ? t('ui.ligne.corrections', { n: it.corrections }) : '']
      .filter(Boolean).join(' · ');
  } else if (it.etat === 'erreur') {
    classeMeta = 'erreur';
    meta = (it.titre || t('ui.ligne.echec')) + (it.message ? ', ' + it.message : '');
  } else {
    meta = it.message || t('ui.ligne.annule');
  }

  const sorties = (it.sorties || []).map((s) =>
    `<span class="sortie" data-ouvrir="${ech(s.chemin)}">${ech(s.format)} · ${ech(s.nom)}</span>`
  ).join('');

  // Une transcription qui vient de se terminer se relit d'un clic, sans passer
  // par l'onglet des transcriptions ni par un editeur exterieur.
  const texte = (it.sorties || []).find((s) => s.format === 'TXT');

  return `<div class="ligne" data-id="${ech(id)}">
    <span class="pastille ${classe}">${icone(ic, 'icone-s')}</span>
    <div class="infos">
      <div class="nom" title="${ech(it.chemin)}">${ech(it.nom)}</div>
      <div class="meta ${classeMeta}">${ech(meta)}</div>
      ${actif ? `<div class="barre"><span style="width:${it.pct || 0}%"></span></div>` : ''}
      ${sorties ? `<div class="sorties">${sorties}</div>` : ''}
    </div>
    ${texte ? `<button class="bouton-ligne" data-lire="${ech(texte.chemin)}" title="${ech(t('ui.ligne.lire'))}">${icone('i-loupe', 'icone-s')}</button>` : ''}
    ${['annule', 'erreur'].includes(it.etat) ? `<button class="bouton-ligne" data-relancer title="${ech(t('ui.ligne.relancer'))}" aria-label="${ech(t('ui.ligne.relancer'))}">${icone('i-reprise', 'icone-s')}</button>` : ''}
    ${it.etat === 'erreur' ? `<button class="bouton-ligne" data-log title="${ech(t('ui.ligne.journal'))}">${icone('i-info', 'icone-s')}</button>` : ''}
    ${actif ? '' : `<button class="bouton-ligne" data-retirer title="${ech(t('ui.ligne.retirer'))}">${icone('i-croix', 'icone-s')}</button>`}
  </div>`;
}

function majLigne(id) {
  const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
  if (!ligne) { dessinerFile(); return; }
  ligne.outerHTML = ligneHTML(id);
  brancherLignes();
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

/* ------------------------------------------------------------ Historique */

function dessinerHistorique() {
  const vue = $('#vue-historique');
  $('#compteur-historique').textContent = String(etat.historique.length);
  if (!etat.historique.length) {
    vue.innerHTML = `<div class="vide">${icone('i-horloge')}
      <div>${ech(t('ui.historique.vide'))}</div></div>`;
    return;
  }
  /* Une ligne par transcription ; chaque format present s'ouvre a part. */
  vue.innerHTML = etat.historique.map((h) => `
    <div class="ligne" data-chemin="${ech(h.chemin)}">
      <span class="pastille termine">${icone('i-coche', 'icone-s')}</span>
      <div class="infos">
        <div class="nom">${ech(h.nom)}</div>
        <div class="meta">${ech(h.date)} · ${ech(h.taille)}</div>
      </div>
      ${(h.formats || [{ format: h.format, chemin: h.chemin }]).map((f) =>
        `<button class="etiquette-format" data-ouvrir="${ech(f.chemin)}">${ech(f.format)}</button>`).join('')}
    </div>`).join('');
  $$('#vue-historique .ligne').forEach((l) => {
    l.onclick = () => ouvrirSortie(l.dataset.chemin);
  });
  $$('#vue-historique [data-ouvrir]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); ouvrirSortie(b.dataset.ouvrir); };
  });
}

/* Le texte se relit dans la vue de lecture, les sous-titres restent en apercu
   brut : personne ne lit un .srt en paragraphes. */
function ouvrirSortie(chemin) {
  if (/\.txt$/i.test(chemin || '')) ouvrirLecture(chemin);
  else ouvrirApercu(chemin);
}

/* --------------------------------------------------------- Vue de lecture */

function formaterSecondes(valeur) {
  const total = Math.max(0, Math.round(valeur || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const deux = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${deux(m)}:${deux(s)}` : `${m}:${deux(s)}`;
}

async function ouvrirLecture(chemin) {
  ouvrirModale('#modale-lecture');
  $('#titre-lecture').textContent = String(chemin).split(/[\\/]/).pop();
  $('#lecture-texte').innerHTML =
    `<p style="color:var(--texte-faible)">${ech(t('ui.lecture.chargement'))}</p>`;
  $('#lecture-meta').innerHTML = '';
  $('#lecture-avis').innerHTML = '';
  $('#lecture-retour').textContent = '';
  $('#lecture-audio').innerHTML = '';
  $('#lecture-legende').style.display = 'none';
  await chargerLecture(chemin);
}

async function chargerLecture(chemin) {
  let d;
  try {
    d = await pywebview.api.lire_transcription(chemin);
  } catch (e) {
    console.error(e);
    d = { ok: false, message: t('ui.lecture.non_lue') };
  }
  if (!d || !d.ok) {
    etat.lecture = null;
    $('#lecture-texte').innerHTML = '';
    $('#lecture-avis').innerHTML =
      encartAttention((d && d.message) || t('ui.lecture.impossible'));
    return;
  }
  etat.lecture = d;
  dessinerLecture();
  majAnnulation();
}

function dessinerLecture() {
  const d = etat.lecture;
  if (!d) return;
  const m = d.meta || {};

  $('#titre-lecture').textContent = d.nom;
  $('#lecture-meta').innerHTML = [
    [t('ui.lecture.meta_fichier'), m.fichier],
    [t('ui.lecture.meta_duree'), m.duree],
    [t('ui.lecture.meta_date'), m.date],
    [t('ui.lecture.meta_modele'), m.modele],
    [t('ui.lecture.meta_locuteurs'), m.locuteurs_texte],
  ].filter((x) => x[1]).map((x) =>
    `<span><span class="cle">${ech(x[0])}</span> ${ech(x[1])}</span>`).join('');

  $('#lecture-avis').innerHTML = d.message ? encartInfo(d.message) : '';

  const stats = d.statistiques || {};
  const legende = $('#lecture-legende');
  legende.style.display = d.compagnon ? 'flex' : 'none';
  if (d.compagnon && stats.mots) {
    const part = (stats.signales ? nb(stats.signales / stats.mots * 100, 1) : '0')
      + ' ' + t('unite.pourcent');
    $('#lecture-legende-texte').textContent = t('ui.lecture.legende_chiffree', {
      signales: stats.signales, total: stats.mots, part: part,
    });
  } else {
    $('#lecture-legende-texte').textContent = t('ui.lecture.legende');
  }

  // Ecoute de l'extrait : le fichier d'origine peut avoir ete deplace depuis,
  // auquel cas on le dit sobrement au lieu d'afficher un lecteur mort.
  const zoneAudio = $('#lecture-audio');
  zoneAudio.innerHTML = '';
  if (d.lecture_audio) {
    // L'adresse vient du serveur local de l'application : un « file:/// »
    // est refuse par le navigateur integre depuis une page servie en http.
    if (m.source_presente && d.audio_url) {
      zoneAudio.innerHTML = `<audio id="lecture-son" controls preload="metadata"
        src="${ech(d.audio_url)}"></audio>`;
      const son = $('#lecture-son');
      son.addEventListener('error', () => {
        zoneAudio.innerHTML = encartInfo(t('ui.lecture.audio_illisible'));
      });
    } else {
      zoneAudio.innerHTML = encartInfo(t(m.source_presente
        ? 'ui.lecture.audio_illisible' : 'ui.lecture.audio_absent'));
    }
  }

  const seuils = d.seuils || { faible: 0.5, tres_faible: 0.3 };
  const ecoutable = !!(d.lecture_audio && m.source_presente && d.audio_url);
  $('#lecture-texte').innerHTML = (d.paragraphes || []).map((p) => `
    <div class="lecture-para ${ecoutable ? 'ecoutable' : ''}" data-debut="${p.debut || 0}">
      ${p.locuteur ? `<span class="locuteur">${ech(p.locuteur)}
        ${ecoutable || p.debut ? `<span class="horodatage">${formaterSecondes(p.debut)}</span>` : ''}</span>` : ''}
      ${p.mots.map((mot, i) => ech(mot.e !== undefined ? mot.e : (i ? ' ' : ''))
        + motHTML(mot, seuils)).join('')}
    </div>`).join('')
    || `<p style="color:var(--texte-faible)">${ech(t('ui.lecture.sans_texte'))}</p>`;
}

function motHTML(mot, seuils) {
  const texte = ech(mot.t);
  if (mot.p < 0) return texte;   // confiance inconnue : mot ordinaire
  let classe = '';
  if (mot.p < seuils.tres_faible) classe = ' mot-fort';
  else if (mot.p < seuils.faible) classe = ' mot-doux';
  return `<span class="mot${classe}" data-p="${Math.round(mot.p * 100)}">${texte}</span>`;
}

/* L'infobulle est posee au survol, pas a la construction : une reunion d'une
   heure represente plusieurs milliers de mots, autant d'attributs inutiles. */
function infobulleMot(evenement) {
  const cible = evenement.target;
  if (!cible || !cible.classList || !cible.classList.contains('mot')) return;
  if (cible.hasAttribute('title')) return;
  cible.setAttribute('title', t('ui.lecture.confiance', { pct: cible.dataset.p }));
}

/* Le texte copie est celui du fichier, en-tete retire, jamais une reconstruction
   mot a mot : ce qui part dans le presse-papiers est ce que l'on relira. */
function texteLecture() {
  const d = etat.lecture;
  if (!d) return '';
  if (typeof d.corps === 'string') return d.corps;
  return (d.paragraphes || []).map((p) =>
    (p.locuteur ? p.locuteur + ' : ' : '') + p.texte).join('\n\n');
}

function retourLecture(texte, classe) {
  const zone = $('#lecture-retour');
  zone.textContent = texte;
  zone.className = 'lecture-retour ' + (classe || '');
  if (texte) setTimeout(() => { if (zone.textContent === texte) zone.textContent = ''; }, 8000);
}

async function copier(texte) {
  try { await navigator.clipboard.writeText(texte); }
  catch (e) { pywebview.api.copier(texte); }
}

/* ------------------------------------------- Correction depuis la lecture */

function positionnerBoutonCorrection() {
  const bouton = $('#btn-corriger-selection');
  const selection = window.getSelection();
  const zone = $('#lecture-texte');
  if (!selection || selection.isCollapsed || !zone.contains(selection.anchorNode)) {
    bouton.classList.remove('visible');
    return;
  }
  const texte = selection.toString().trim().replace(/\s+/g, ' ');
  if (!texte || texte.length > 80) {
    bouton.classList.remove('visible');
    return;
  }
  etat.selection = texte;
  const rect = selection.getRangeAt(0).getBoundingClientRect();
  bouton.style.left = Math.max(8, Math.min(window.innerWidth - 130, rect.left)) + 'px';
  bouton.style.top = (rect.bottom + 6) + 'px';
  bouton.classList.add('visible');
}

function masquerBoutonCorrection() {
  $('#btn-corriger-selection').classList.remove('visible');
}

function ouvrirCorrection() {
  masquerBoutonCorrection();
  if (!etat.selection || !etat.lecture) return;
  $('#correction-source').value = etat.selection;
  $('#correction-cible').value = etat.selection;
  // La regle vaut pour toutes les transcriptions a venir : c'est un choix
  // explicite, jamais coche d'office.
  $('#correction-regle').checked = false;
  $('#case-regle').style.display = etat.config.corrections_apprises === false ? 'none' : '';
  $('#retour-correction').innerHTML = '';
  $('#apercu-correction').innerHTML = '';
  majQuestionRegle();
  ouvrirModale('#modale-correction');
  setTimeout(() => { $('#correction-cible').focus(); $('#correction-cible').select(); }, 50);
}

function majQuestionRegle() {
  const source = $('#correction-source').value.trim();
  const cible = $('#correction-cible').value.trim();
  $('#correction-question').textContent = t('ui.correction.question_detaillee', {
    source: source, cible: cible || t('ui.correction.attente'),
  });
  clearTimeout(etat.minuterieApercu);
  etat.minuterieApercu = setTimeout(majApercuCorrection, 200);
}

/* Avant d'appliquer : combien d'endroits du fichier changent, et lesquels. */
async function majApercuCorrection() {
  const zone = $('#apercu-correction');
  const source = $('#correction-source').value.trim();
  const cible = $('#correction-cible').value.trim();
  if (!etat.lecture || !cible || cible === source) { zone.innerHTML = ''; return; }
  let r;
  try {
    r = await pywebview.api.apercu_correction(etat.lecture.chemin, source, cible);
  } catch (e) { console.error(e); zone.innerHTML = ''; return; }
  if ($('#correction-cible').value.trim() !== cible) return;   // saisie depassee
  if (!r.ok) { zone.innerHTML = encartAttention(r.message); return; }
  const lignes = (r.extraits || []).map((x) => `<li>${x.debut_coupe ? '…' : ''}${ech(x.avant)}`
    + `<mark>${ech(x.forme)}</mark>${ech(x.apres)}${x.fin_coupee ? '…' : ''}</li>`);
  const reste = r.nombre - (r.extraits || []).length;
  if (reste > 0) lignes.push(`<li class="reste">${ech(tn('ui.correction.autres', reste))}</li>`);
  zone.innerHTML = `<div class="apercu-titre">${ech(r.message)}</div><ul>${lignes.join('')}</ul>`;
}

function majAnnulation() {
  $('#btn-annuler-correction').hidden = !(etat.lecture && etat.lecture.annulable);
}

async function annulerCorrection() {
  if (!etat.lecture || !etat.lecture.annulable) return;
  const r = await pywebview.api.annuler_correction(etat.lecture.chemin);
  if (r.nb_corrections !== undefined) majCorrections({ nb: r.nb_corrections, erreurs: [] });
  journaliser(r.ok ? 'ok' : 'attention', r.message);
  await chargerLecture(etat.lecture.chemin);
  retourLecture(r.message, r.ok ? 'ok' : 'erreur');
}

async function appliquerCorrection() {
  if (!etat.lecture) return;
  const bouton = $('#btn-appliquer-correction');
  const source = $('#correction-source').value.trim();
  const cible = $('#correction-cible').value.trim();
  bouton.disabled = true;
  try {
    const r = await pywebview.api.corriger_transcription(
      etat.lecture.chemin, source, cible, $('#correction-regle').checked);
    if (!r.ok) {
      $('#retour-correction').innerHTML = encartAttention(r.message);
      return;
    }
    fermerModale($('#modale-correction'));
    if (r.nb_corrections !== undefined) majCorrections({ nb: r.nb_corrections, erreurs: [] });
    journaliser('ok', t('ui.correction.journal', {
      source: source, cible: cible, message: r.message,
    }));
    await chargerLecture(etat.lecture.chemin);
    retourLecture(r.message, 'ok');
  } catch (e) {
    console.error(e);
    $('#retour-correction').innerHTML = encartAttention(t('ui.correction.echec'));
  } finally {
    bouton.disabled = false;
  }
}

/* --------------------------------------------------- Reprises en attente */

function dessinerReprises() {
  const zone = $('#bloc-reprises');
  if (!etat.reprises.length) { zone.innerHTML = ''; return; }
  zone.innerHTML = etat.reprises.map((r) => `
    <div class="reprise-carte" data-cle="${ech(r.cle)}">
      ${icone('i-reprise')}
      <div class="infos">
        <div class="nom">${ech(r.nom)}</div>
        <div class="meta">${ech(t('ui.reprise.meta', {
          position: r.position_texte, duree: r.duree_texte, pct: r.pct,
          ecoule: r.ecoule_texte,
        }))}</div>
      </div>
      <button class="bouton" data-reprendre>${ech(t('ui.reprise.reprendre'))}</button>
      <button class="bouton bouton-discret" data-oublier>${ech(t('ui.reprise.oublier'))}</button>
    </div>`).join('');

  $$('#bloc-reprises [data-reprendre]').forEach((b) => {
    b.onclick = async () => {
      const cle = b.closest('.reprise-carte').dataset.cle;
      const r = await pywebview.api.reprendre(cle);
      if (!r.ok) {
        // La carte reste : la reprise est toujours sur le disque, et le refus
        // est dit la ou l'on regarde, pas seulement dans le journal replie.
        journaliser('attention', r.message);
        setEtat(r.message, 'erreur');
        return;
      }
      // La reprise reste sur le disque jusqu'a la fin du calcul, mais elle est
      // maintenant dans la file : la proposer une seconde fois n'a plus de sens.
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

/* --------------------------------------------------------------- Journal */

function journaliser(niveau, texte) {
  const zone = $('#journal-contenu');
  const heure = new Date().toLocaleTimeString(t('format.heure'), { hour12: false });
  const ligne = document.createElement('div');
  ligne.className = 'l';
  ligne.innerHTML = `<span class="h">${heure}</span><span class="${ech(niveau)}">${ech(texte)}</span>`;
  zone.appendChild(ligne);
  while (zone.childElementCount > 500) zone.removeChild(zone.firstChild);
  zone.scrollTop = zone.scrollHeight;
  $('#journal-dernier').textContent = texte;
}

function basculerJournal() {
  const entete = $('#journal-entete');
  const contenu = $('#journal-contenu');
  const ouvert = contenu.classList.toggle('ouvert');
  entete.classList.toggle('ouvert', ouvert);
  entete.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  if (ouvert) contenu.scrollTop = contenu.scrollHeight;
  enregistrer({ journal_ouvert: ouvert });
}

/* ------------------------------------------------------------ Etat global */

function setEtat(texte, classe) {
  $('#etat-texte').textContent = texte;
  $('#etat-global').className = 'etat-global ' + (classe || '');
}

function majBoutons() {
  const enAttente = Array.from(etat.fichiers.values()).filter((f) => f.etat === 'attente').length;
  $('#btn-lancer').disabled = etat.enCours || etat.bancEnCours || !enAttente || !etat.pret;
  $('#btn-arreter').disabled = !etat.enCours;
  $('#btn-lancer').innerHTML = icone('i-lecture', 'icone-s') + ' '
    + ech(enAttente > 1 ? t('ui.bouton.lancer_n', { n: enAttente }) : t('ui.bouton.lancer'));
}

/* ------------------------------------------- Rappels appeles par Python */

/* Un fichier deja liste qui repasse en attente (relance, reprise, nouveau
   depot) repart d'une ligne propre : rien de son passage precedent ne reste. */
function remettreEnAttente(item) {
  etat.fichiers.set(item.id, Object.assign({ pct: 0 }, item));
  majLigne(item.id);
  majBoutons();
}

window.onFichiersAjoutes = function (items) {
  items.forEach((it) => etat.fichiers.set(it.id, Object.assign({ pct: 0 }, it)));
  dessinerFile();
  majBoutons();
  basculerVue('file');
};

window.onDuree = async function (id, secondes, texte) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  it.duree_secs = secondes;
  it.duree = texte;
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

window.onEtat = function (id, nouvelEtat, message) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  it.etat = nouvelEtat;
  it.message = message;
  if (nouvelEtat !== 'attente') it.phase = message;
  majLigne(id);
  if (['decodage', 'transcription', 'locuteurs', 'ecriture'].includes(nouvelEtat)) {
    setEtat(t('ui.etat.en_cours', { message: message, nom: it.nom }), 'actif');
  }
};

window.onProgression = function (id, d) {
  const it = etat.fichiers.get(id);
  if (!it) return;
  Object.assign(it, { pct: d.pct, phase: d.phase, ecoule: d.ecoule, restant: d.restant });
  const ligne = document.querySelector(`#vue-file .ligne[data-id="${CSS.escape(id)}"]`);
  if (ligne) {
    const barre = ligne.querySelector('.barre span');
    if (barre) barre.style.width = d.pct + '%';
    const meta = ligne.querySelector('.meta');
    if (meta) {
      meta.textContent = [d.phase,
        d.ecoule ? t('ui.ligne.ecoule', { duree: d.ecoule }) : '',
        d.restant ? t('ui.ligne.restant', { duree: d.restant }) : '']
        .filter(Boolean).join(' · ');
    }
  } else {
    majLigne(id);
  }
  setEtat(t('ui.etat.progression', { phase: d.phase, pct: d.pct, nom: it.nom }), 'actif');
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
  } else if (d.annule) {
    it.etat = 'annule';
    it.message = t('ui.ligne.arrete');
  } else {
    it.etat = 'erreur';
    it.titre = d.titre;
    it.message = d.message;
  }
  majLigne(id);
  majBoutons();
};

window.onFileTerminee = function (d) {
  etat.enCours = false;
  majBoutons();
  if (d.echecs) {
    setEtat(t('ui.etat.bilan_echecs', { reussis: d.reussis, echecs: d.echecs }), 'erreur');
  } else if (d.annules) {
    setEtat(t('ui.etat.bilan_arrete', { reussis: d.reussis }), '');
  } else {
    setEtat(t('ui.etat.bilan_ok', { reussis: d.reussis }), 'succes');
  }
  journaliser(d.echecs ? 'attention' : 'ok', t('ui.etat.file_terminee', {
    reussis: d.reussis, echecs: d.echecs, annules: d.annules,
  }));
  pywebview.api.charger_historique();
  // Un fichier arrete en route laisse une reprise : elle est proposee tout de
  // suite, sans attendre le prochain demarrage de l'application.
  pywebview.api.liste_reprises().then((liste) => {
    etat.reprises = liste || [];
    dessinerReprises();
  }).catch(() => { /* sans consequence */ });
};

window.onJournal = function (niveau, texte) {
  journaliser(niveau, texte);
};

window.finDepot = function () {
  $('#zone-depot').classList.remove('survol');
};

/* ---------------------------------------------------------------- Modales */

function ouvrirModale(selecteur) { $(selecteur).classList.add('ouvert'); }

function fermerModale(el) {
  el.classList.remove('ouvert');
  if (el.id === 'modale-lecture') {
    masquerBoutonCorrection();
    const son = $('#lecture-son');
    if (son) son.pause();
  }
  if (el.id === 'modale-correction') masquerBoutonCorrection();
}

/* Echap ferme la fenetre du dessus, pas la pile entiere : depuis la correction,
   on revient a la lecture, on n'en est pas ejecte. */
function fermerDerniereModale() {
  const ouvertes = $$('.voile.ouvert');
  if (ouvertes.length) fermerModale(ouvertes[ouvertes.length - 1]);
}


/* ------------------------------------------------------- Theme et zoom */

function appliquerTheme(mode) {
  if (mode === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', mode);
  etat.config.theme = mode;
}

function themeSuivant() {
  /* Bascule sur le theme reellement affiche : l'ancien cycle auto -> clair -> sombre
     produisait un clic sans effet visible quand « clair » coincidait avec le systeme. */
  const affiche = document.documentElement.getAttribute('data-theme')
    || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'sombre' : 'clair');
  const suivant = affiche === 'sombre' ? 'clair' : 'sombre';
  appliquerTheme(suivant);
  enregistrer({ theme: suivant });
  journaliser('info', t('ui.journal.theme', {
    theme: t(suivant === 'sombre' ? 'ui.theme.sombre' : 'ui.theme.clair'),
  }));
}

function appliquerZoom(valeur) {
  etat.config.zoom = Math.min(1.6, Math.max(0.7, valeur));
  document.body.style.zoom = etat.config.zoom;
  mesurerFenetre();
}

/* Taille de la fenetre divisee par le grossissement, publiee en variables CSS.

   « zoom » multiplie tout ce que contient le corps de page, unites vh comprises :
   sans cette division, une fenetre bornee a 85vh depassait par le bas des que le
   grossissement montait, et le panneau d'aide sortait de l'ecran. Voir le
   commentaire de :root dans styles.css. */
function mesurerFenetre() {
  const grossissement = etat.config.zoom || 1;
  const style = document.documentElement.style;
  style.setProperty('--hauteur-fenetre', `${window.innerHeight / grossissement}px`);
  style.setProperty('--largeur-fenetre', `${window.innerWidth / grossissement}px`);
}

window.addEventListener('resize', mesurerFenetre);

/* ------------------------------------------------------------ Cablage UI */

document.addEventListener('DOMContentLoaded', () => {
  // Langue provisoire, le temps que Python reponde : celle du dernier
  // lancement, sinon celle du navigateur integre. Evite une fenetre vide.
  definirLangue(langueProvisoire());
  traduirePage();

  dessinerFile();
  dessinerHistorique();

  $('#materiel-entete').addEventListener('click', basculerMateriel);
  $('#materiel-entete').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); basculerMateriel(); }
  });

  $('#btn-theme').addEventListener('click', themeSuivant);
  $('#btn-aide').addEventListener('click', ouvrirAide);
  $('#btn-aide-maj').addEventListener('click', verifierMajDepuisAide);
  $('#btn-ouvrir-app').addEventListener('click', () => pywebview.api.ouvrir_dossier_application());

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

  // Onglets
  $('#onglet-file').addEventListener('click', () => basculerVue('file'));
  $('#onglet-historique').addEventListener('click', () => basculerVue('historique'));
  $('#btn-vider').addEventListener('click', () => {
    Array.from(etat.fichiers.entries()).forEach(([id, it]) => {
      if (['attente', 'termine', 'erreur', 'annule'].includes(it.etat)) etat.fichiers.delete(id);
    });
    pywebview.api.vider_file();
    dessinerFile();
    majBoutons();
  });

  // Reglages simples
  $('#langue').addEventListener('change', (e) => {
    enregistrer({ langue: e.target.value });
    majQualiteLangue();
  });

  // Langue de l'interface : sans effet sur la langue parlee ci-dessus.
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

  // Espace utilise
  $('#btn-stockage').addEventListener('click', () => {
    $('#contenu-stockage').innerHTML =
      `<p style="color:var(--texte-faible)">${ech(t('ui.stockage.mesure'))}</p>`;
    ouvrirModale('#modale-stockage');
    pywebview.api.mesurer_stockage();
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

  // Glossaire et corrections
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
      : encartSucces(t('ui.voc.regles_enregistrees', { n: r.nb }));
    journaliser('ok', t('ui.voc.regles_enregistrees', { n: r.nb }));
    if (!r.erreurs.length) setTimeout(() => fermerModale($('#modale-corrections')), 700);
  });

  // Relecture
  $('#opt-compagnon').addEventListener('change', (e) =>
    enregistrer({ compagnon_confiance: e.target.checked }));
  $('#opt-apprises').addEventListener('change', (e) =>
    enregistrer({ corrections_apprises: e.target.checked }));
  $('#opt-sauvegarde').addEventListener('change', (e) =>
    enregistrer({ sauvegarde_progressive: e.target.checked }));
  $('#opt-lecture-audio').addEventListener('change', (e) => {
    enregistrer({ lecture_audio: e.target.checked });
    if (etat.lecture) { etat.lecture.lecture_audio = e.target.checked; dessinerLecture(); }
  });

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

  // Vue de lecture
  $('#btn-ouvrir-lecture').addEventListener('click', () => {
    if (etat.lecture) pywebview.api.ouvrir(etat.lecture.chemin);
  });
  $('#btn-copier-lecture').addEventListener('click', async () => {
    await copier(texteLecture());
    retourLecture(t('ui.lecture.texte_copie'), 'ok');
    journaliser('ok', t('ui.lecture.texte_copie_journal'));
  });
  $('#btn-copier-ia').addEventListener('click', async () => {
    if (!etat.lecture) return;
    const bouton = $('#btn-copier-ia');
    bouton.disabled = true;
    try {
      const r = await pywebview.api.copier_pour_ia(etat.lecture.chemin);
      if (!r.ok) {
        retourLecture(r.message || t('ui.lecture.copie_impossible'), 'erreur');
        return;
      }
      retourLecture(t('ui.lecture.ia_copie'), 'ok');
      journaliser('ok', r.message);
    } catch (e) {
      console.error(e);
      retourLecture(t('ui.lecture.copie_impossible'), 'erreur');
    } finally {
      bouton.disabled = false;
    }
  });

  // Confiance au survol, correction sur selection : un seul ecouteur pour tout
  // le texte, quel que soit le nombre de mots affiches.
  $('#lecture-texte').addEventListener('mouseover', infobulleMot);
  $('#lecture-texte').addEventListener('mouseup', () => setTimeout(positionnerBoutonCorrection, 0));
  $('#lecture-texte').addEventListener('keyup', () => setTimeout(positionnerBoutonCorrection, 0));
  $('#modale-lecture .modale-corps').addEventListener('scroll', masquerBoutonCorrection);
  $('#btn-corriger-selection').addEventListener('mousedown', (e) => e.preventDefault());
  $('#btn-corriger-selection').addEventListener('click', ouvrirCorrection);
  $('#correction-cible').addEventListener('input', majQuestionRegle);
  $('#correction-cible').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); appliquerCorrection(); }
  });
  $('#btn-appliquer-correction').addEventListener('click', appliquerCorrection);
  $('#btn-annuler-correction').addEventListener('click', annulerCorrection);

  // Ecoute de l'extrait correspondant au paragraphe clique.
  $('#lecture-texte').addEventListener('click', (e) => {
    const son = $('#lecture-son');
    const para = e.target.closest ? e.target.closest('.lecture-para') : null;
    if (!son || !para) return;
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) return;   // l'utilisateur selectionne
    son.currentTime = parseFloat(para.dataset.debut || '0') || 0;
    son.play().catch(() => { /* pas de lecture possible, sans consequence */ });
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

  // Vitesse de cette machine : moteur OpenVINO et banc d'essai
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
    b.addEventListener('click', () => rafraichirRythme({ rythme: b.dataset.rythme }));
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
  $('#journal-entete').addEventListener('click', (e) => {
    if (e.target.id === 'btn-fichier-log') return;
    basculerJournal();
  });
  $('#btn-fichier-log').addEventListener('click', (e) => {
    e.stopPropagation();
    pywebview.api.ouvrir_journal();
  });

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
    v.addEventListener('mousedown', (e) => { if (e.target === v) fermerModale(v); });
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest || !e.target.closest('#btn-corriger-selection')) masquerBoutonCorrection();
  });

  // Raccourcis. Trois utiles, et rien de plus : parcourir, lancer, fermer.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { fermerDerniereModale(); return; }
    const modaleOuverte = !!$('.voile.ouvert');
    if (e.ctrlKey && (e.key === 'o' || e.key === 'O')) {
      e.preventDefault();
      if (!modaleOuverte) pywebview.api.ajouter_fichiers();
      return;
    }
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      if (!modaleOuverte && !$('#btn-lancer').disabled) lancer();
    }
    // Ctrl+Z dans la relecture : defait la derniere correction, sauf dans un
    // champ de saisie, ou il garde son sens habituel.
    if (e.ctrlKey && (e.key === 'z' || e.key === 'Z')
        && $('#modale-lecture').classList.contains('ouvert')
        && !$('#modale-correction').classList.contains('ouvert')
        && !/^(INPUT|TEXTAREA)$/.test((document.activeElement || {}).tagName || '')) {
      e.preventDefault();
      annulerCorrection();
      return;
    }
    if (e.ctrlKey && (e.key === '+' || e.key === '=')) { e.preventDefault(); zoom(0.1); }
    if (e.ctrlKey && e.key === '-') { e.preventDefault(); zoom(-0.1); }
    if (e.ctrlKey && e.key === '0') { e.preventDefault(); appliquerZoom(1); enregistrer({ zoom: 1 }); }
  });
  document.addEventListener('wheel', (e) => {
    if (e.ctrlKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 0.05 : -0.05); }
  }, { passive: false });
});

function zoom(delta) {
  appliquerZoom((etat.config.zoom || 1) + delta);
  enregistrer({ zoom: etat.config.zoom });
}

function basculerVue(vue) {
  const file = vue === 'file';
  $('#vue-file').style.display = file ? 'flex' : 'none';
  $('#vue-historique').style.display = file ? 'none' : 'flex';
  $('#onglet-file').setAttribute('aria-selected', file ? 'true' : 'false');
  $('#onglet-historique').setAttribute('aria-selected', file ? 'false' : 'true');
  $('#btn-vider').style.display = file ? '' : 'none';
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
  majBoutons();
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
