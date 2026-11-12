/* =========================================================================
   Scribouille : relecture plein cadre

   Un ecran entier, d'abord sonore. Regle d'or : le texte affiche, le fichier
   et le presse-papiers sont identiques. Le texte vient de app/lecture.py, mot
   par mot avec ce qui precede chaque mot dans le fichier ; rien n'est
   reconstruit ici.

   - ecoute : clic sur un mot pour s'y placer, lecture qui suit le texte,
     vitesses, Espace, fleches ;
   - recherche (Ctrl+F) avec surlignage de tous les resultats et navigation ;
   - points a verifier : mots douteux, remplacements du vocabulaire, silences,
     passages longs, de l'un a l'autre (N, Maj+N) ;
   - correction d'un endroit ou de plusieurs, avec apercu et annulation ;
   - renommage des locuteurs ; exports.

   Une reunion d'une heure et demie fait 15 000 a 20 000 mots : un seul rendu
   en chaine, des paragraphes en « content-visibility: auto » (le navigateur ne
   met en page que ce qui est visible), et des surlignages par l'API Highlight,
   qui ne touchent pas au document.
   ========================================================================= */

'use strict';

const lect = {
  d: null,
  chemin: '',
  mots: [],          // { d: debut, k: paragraphe, doute: 0|1|2 } pour chaque mot affiche
  spans: [],
  textes: [],        // texte affiche de chaque paragraphe
  normalises: [],
  courant: -1,       // mot en cours de lecture
  vise: -1,          // mot atteint par la navigation
  recherche: { terme: '', resultats: [], i: -1 },
  points: { categorie: '', listes: {}, i: -1 },
  audio: false,
  boucle: 0,
  selection: null,   // { source, avant, apres }
  correction: { nombre: 0, extraits: [], choisie: -1 },
  locuteur: '',
  mesures: {},
  pret: false,
};

const SEUIL_SILENCE = 5;     // secondes entre deux mots
const SEUIL_PASSAGE = 90;    // duree d'un paragraphe

/* ------------------------------------------------------------ Ouverture */

async function ouvrirLecture(chemin) {
  lect.pret = false;
  lect.chemin = chemin;
  afficherVue('relecture', { focus: false });
  $('#rl-titre').textContent = String(chemin).split(/[\\/]/).pop();
  $('#rl-meta').textContent = '';
  $('#rl-avis').innerHTML = '';
  $('#rl-texte').innerHTML = `<p class="vide">${ech(t('ui.lecture.chargement'))}</p>`;
  statutRelecture('');
  arreterAudio();
  const debut = performance.now();
  await chargerLecture(chemin, false);
  lect.mesures.ouverture_ms = Math.round(performance.now() - debut);
  $('#rl-titre').focus({ preventScroll: true });
  chargerAudio(chemin);
  clearInterval(lect.veille);
  lect.veille = setInterval(verifierFichier, 4000);
}

/* Un fichier retouche ailleurs (editeur de texte) pendant la relecture : il
   est relu, et on le dit. Verifie toutes les 4 s et au retour dans la
   fenetre, jamais pendant une ecriture de l'application. */
async function verifierFichier() {
  if (etat.vue !== 'relecture' || !lect.d || !lect.pret || lect.ecriture || document.hidden) return;
  const chemin = lect.chemin;
  let empreinte = '';
  try { empreinte = await appelPasserelle('empreinte_transcription', chemin); } catch (e) { return; }
  if (lect.ecriture || chemin !== lect.chemin || !lect.d || !empreinte || empreinte === lect.d.empreinte) return;
  await chargerLecture(chemin, true);
  statutRelecture(t('ui.rl.modifie_dehors'), 'attention');
  journaliser('attention', t('ui.rl.modifie_dehors'));
}

/* Ecritures de la relecture : la verification du fichier se tait pendant
   qu'elles tournent, et un refus « modifie ailleurs » relit le texte. */
async function ecrireRelecture(appel) {
  lect.ecriture = true;
  try {
    const r = await appel();
    if (r && !r.ok && r.code === 'modifie_dehors') await chargerLecture(lect.chemin, true);
    return r;
  } finally {
    lect.ecriture = false;
  }
}

/* Recharge apres une correction, en gardant la position de lecture. */
async function chargerLecture(chemin, garderPosition) {
  const zone = $('#rl-defilement');
  const haut = garderPosition ? zone.scrollTop : 0;
  let d;
  const t0 = performance.now();
  try {
    d = await pywebview.api.lire_transcription(chemin);
  } catch (e) {
    console.error(e);
    d = { ok: false, message: t('ui.lecture.non_lue') };
  }
  const t1 = performance.now();
  if (!d || !d.ok) {
    lect.d = null;
    $('#rl-texte').innerHTML = '';
    $('#rl-avis').innerHTML = encartAttention((d && d.message) || t('ui.lecture.impossible'));
    return;
  }
  lect.d = d;
  dessinerRelecture();
  zone.scrollTop = haut;
  majAnnulation();
  lect.mesures.appel_ms = Math.round(t1 - t0);
  lect.mesures.rendu_ms = Math.round(performance.now() - t1);
  lect.mesures.mots = lect.mots.length;
  lect.pret = true;
}

function dessinerRelecture() {
  const d = lect.d;
  const m = d.meta || {};
  $('#rl-titre').textContent = d.nom;
  // « 3 locuteurs détectés » se suffit ; « non séparés » a besoin de son sujet.
  $('#rl-meta').innerHTML = [m.duree, m.date, m.modele,
    m.locuteurs ? m.locuteurs_texte
      : (m.locuteurs_texte ? t('ui.rl.meta_locuteurs', { texte: m.locuteurs_texte }) : '')]
    .filter(Boolean).map((x) => `<span>${ech(x)}</span>`).join('');
  dessinerTexte();
  calculerPoints();
  dessinerAvis();
  if (lect.recherche.terme) chercher(lect.recherche.terme, true);
  if (lect.courant >= 0) marquerLu(lect.courant, false);
}

function dessinerTexte() {
  const d = lect.d;
  const seuils = d.seuils || { faible: 0.5, tres_faible: 0.3 };
  const morceaux = [];
  const mots = [];
  const textes = [];
  (d.paragraphes || []).forEach((p, k) => {
    let corps = '';
    let texte = '';
    p.mots.forEach((mot, j) => {
      const ecart = mot.e !== undefined ? mot.e : (j ? ' ' : '');
      corps += ech(ecart);
      texte += ecart;
      if (!mot.t) return;
      let classe = 'm';
      let doute = 0;
      if (mot.c) classe += ' mc';
      else if (mot.p >= 0 && mot.p < seuils.tres_faible) { classe += ' mf'; doute = 2; }
      else if (mot.p >= 0 && mot.p < seuils.faible) { classe += ' md'; doute = 1; }
      corps += `<span class="${classe}" data-i="${mots.length}">${ech(mot.t)}</span>`;
      texte += mot.t;
      mots.push({ d: Number(mot.d) || p.debut || 0, k: k, doute: doute, c: !!mot.c, p: mot.p });
    });
    textes.push(texte);
    const heure = formaterSecondes(p.debut);
    morceaux.push(`<div class="rl-para" data-p="${k}"><div class="rl-marge">`
      + `<button class="rl-heure" data-p="${k}" aria-label="${ech(t('ui.rl.ecouter_depuis', { heure: heure }))}">${heure}</button>`
      + (p.locuteur ? `<button class="rl-locuteur" data-loc="${ech(p.locuteur)}" title="${ech(t('ui.loc.renommer'))}">${ech(p.locuteur)}</button>` : '')
      + `</div><p class="rl-corps">${corps}</p></div>`);
  });
  const zone = $('#rl-texte');
  zone.innerHTML = morceaux.join('')
    || `<p class="vide">${ech(t('ui.lecture.sans_texte'))}</p>`;
  lect.mots = mots;
  lect.spans = Array.from(zone.querySelectorAll('.m'));
  lect.textes = textes;
  lect.normalises = textes.map(normaliserRecherche);
  lect.courant = -1;
  lect.vise = -1;
  zone.classList.toggle('ecoutable', lect.audio);
}

function formaterSecondes(valeur) {
  const total = Math.max(0, Math.round(valeur || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const deux = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${deux(m)}:${deux(s)}` : `${m}:${deux(s)}`;
}

function horodatage(valeur) {
  const total = Math.max(0, Math.floor(valeur || 0));
  const deux = (n) => String(n).padStart(2, '0');
  return `${deux(Math.floor(total / 3600))}:${deux(Math.floor((total % 3600) / 60))}:${deux(total % 60)}`;
}

/* Une ligne d'avis au plus : ce que la vue peut signaler et ce qu'elle ne peut
   pas, l'audio s'il manque. Pas de legende generale. */
function dessinerAvis() {
  const d = lect.d;
  const stats = d.statistiques || {};
  const avis = [];
  if (d.message) avis.push(encartInfo(d.message));
  if (d.compagnon && !stats.mots && stats.sans_confiance) {
    avis.push(encartInfo(t('ui.rl.sans_confiance')));
  }
  if (lect.audioAvis) avis.push(encartInfo(lect.audioAvis));
  $('#rl-avis').innerHTML = avis.join('');
}

function statutRelecture(texte, classe) {
  const zone = $('#rl-statut');
  zone.textContent = texte;
  zone.className = 'rl-statut ' + (classe || '');
  clearTimeout(lect.minuterieStatut);
  if (texte) lect.minuterieStatut = setTimeout(() => { if (zone.textContent === texte) zone.textContent = ''; }, 8000);
}

function relectureLangueChangee() {
  if (etat.vue === 'relecture' && lect.d) chargerLecture(lect.chemin, true);
}

function quitterRelecture() {
  clearInterval(lect.veille);
  arreterAudio();
  masquerBoutonCorrection();
  fermerMenuExport();
  if (window.CSS && CSS.highlights) { CSS.highlights.delete('rl-trouve'); CSS.highlights.delete('rl-courant'); }
}

/* ---------------------------------------------------------------- Audio */

const son = () => $('#rl-son');

async function chargerAudio(chemin) {
  lect.audio = false;
  lect.audioAvis = '';
  activerLecteur(false);
  let r = null;
  try { r = await appelPasserelle('audio_relecture', chemin); } catch (e) { r = null; }
  if (lect.chemin !== chemin) return;
  if (!r || !r.ok || !r.url) {
    lect.audioAvis = t('ui.rl.audio.' + ((r && r.code) || 'audio_illisible'));
    if (lect.d) dessinerAvis();
    return;
  }
  const s = son();
  s.src = r.url;
  s.playbackRate = Number($('#rl-vitesse').value) || 1;
  s.load();
}

function activerLecteur(actif) {
  ['#rl-lire', '#rl-reculer', '#rl-avancer', '#rl-position', '#rl-vitesse'].forEach((s) => { $(s).disabled = !actif; });
  $('#rl-texte').classList.toggle('ecoutable', actif);
}

function arreterAudio() {
  const s = son();
  if (!s) return;
  s.pause();
  s.removeAttribute('src');
  s.load();
  cancelAnimationFrame(lect.boucle);
  majBoutonLire(false);
  $('#rl-temps').textContent = '0:00';
}

function majBoutonLire(enLecture) {
  $('#rl-lire').setAttribute('aria-pressed', enLecture ? 'true' : 'false');
  $('#rl-lire-icone').innerHTML = `<use href="#${enLecture ? 'i-pause' : 'i-lecture'}"></use>`;
  $('#rl-lire-texte').textContent = t(enLecture ? 'ui.rl.pause' : 'ui.rl.lire');
}

function basculerLecture() {
  const s = son();
  if (!lect.audio) return;
  if (s.paused) s.play().catch(() => { /* lecture refusee, sans consequence */ });
  else s.pause();
}

function deplacer(secondes) {
  const s = son();
  if (!lect.audio) return;
  s.currentTime = Math.max(0, Math.min(s.duration || 0, s.currentTime + secondes));
  suivreLecture(true);
}

function placerA(secondes) {
  const s = son();
  if (!lect.audio) return;
  s.currentTime = Math.max(0, Math.min(s.duration || secondes, secondes));
  suivreLecture(true);
}

function changerVitesse(pas) {
  const choix = $('#rl-vitesse');
  const valeurs = Array.from(choix.options).map((o) => Number(o.value));
  const i = Math.max(0, Math.min(valeurs.length - 1, valeurs.indexOf(Number(choix.value)) + pas));
  choix.value = String(valeurs[i]);
  son().playbackRate = valeurs[i];
  statutRelecture(t('ui.rl.vitesse_choisie', { v: choix.options[i].textContent }));
}

/* Mot lu : le dernier mot commence avant la position de lecture. */
function motA(secondes) {
  const mots = lect.mots;
  let bas = 0;
  let haut = mots.length - 1;
  let trouve = -1;
  while (bas <= haut) {
    const milieu = (bas + haut) >> 1;
    if (mots[milieu].d <= secondes + 0.05) { trouve = milieu; bas = milieu + 1; } else { haut = milieu - 1; }
  }
  return trouve;
}

function marquerLu(i, defiler) {
  if (lect.courant >= 0 && lect.spans[lect.courant]) lect.spans[lect.courant].classList.remove('lu');
  const avant = lect.courant >= 0 ? lect.mots[lect.courant] : null;
  lect.courant = i;
  if (i < 0 || !lect.spans[i]) return;
  const span = lect.spans[i];
  span.classList.add('lu');
  if (!avant || avant.k !== lect.mots[i].k) {
    $$('#rl-texte .rl-para.courant').forEach((p) => p.classList.remove('courant'));
    const para = span.closest('.rl-para');
    if (para) para.classList.add('courant');
  }
  if (defiler && $('#rl-suivre').checked) {
    const zone = $('#rl-defilement').getBoundingClientRect();
    const r = span.getBoundingClientRect();
    if (r.top < zone.top + 40 || r.bottom > zone.bottom - 40) span.scrollIntoView({ block: 'center' });
  }
}

function suivreLecture(defiler) {
  const s = son();
  const temps = s.currentTime || 0;
  $('#rl-temps').textContent = `${formaterSecondes(temps)} / ${formaterSecondes(s.duration || 0)}`;
  if (!lect.glisse) $('#rl-position').value = String(temps);
  const i = motA(temps);
  if (i !== lect.courant) marquerLu(i, defiler);
}

function boucleLecture() {
  suivreLecture(true);
  if (!son().paused) lect.boucle = requestAnimationFrame(boucleLecture);
}

/* ------------------------------------------------------------- Recherche

   Sans casse ni accents. Tous les resultats sont surlignes, le courant plus
   fort ; Entree et F3 passent au suivant, Maj au precedent. */

function chercher(terme, garderIndex) {
  const brut = String(terme || '');
  lect.recherche.terme = brut;
  const cle = normaliserRecherche(brut.trim());
  const resultats = [];
  if (cle.length >= 1 && lect.d) {
    lect.normalises.forEach((texte, k) => {
      let pos = texte.indexOf(cle);
      while (pos >= 0 && resultats.length < 5000) {
        resultats.push({ k: k, debut: pos, fin: pos + cle.length });
        pos = texte.indexOf(cle, pos + cle.length);
      }
    });
  }
  lect.recherche.resultats = resultats;
  if (!garderIndex || lect.recherche.i >= resultats.length) lect.recherche.i = -1;
  surlignerRecherche();
  if (!garderIndex && resultats.length) allerResultat(premierApres(), false);
  majCompteRecherche();
}

/* Premier resultat a partir de l'endroit lu ou atteint, sinon du haut. */
function premierApres() {
  const repere = lect.vise >= 0 ? lect.mots[lect.vise] : (lect.courant >= 0 ? lect.mots[lect.courant] : null);
  if (!repere) return 0;
  const i = lect.recherche.resultats.findIndex((r) => r.k >= repere.k);
  return i < 0 ? 0 : i;
}

function majCompteRecherche() {
  const n = lect.recherche.resultats.length;
  $('#rl-compte').textContent = lect.recherche.terme.trim()
    ? (n ? t(n >= 5000 ? 'ui.rl.position_sur_plus' : 'ui.rl.position_sur', { i: lect.recherche.i + 1, n: n })
      : t('ui.rl.aucun_resultat'))
    : '';
}

/* Plage du document pour un morceau de texte d'un paragraphe : on parcourt les
   noeuds de texte du paragraphe en cumulant leurs longueurs. */
function plagePour(k, debut, fin) {
  const corps = document.querySelector(`#rl-texte .rl-para[data-p="${k}"] .rl-corps`);
  if (!corps) return null;
  const marcheur = document.createTreeWalker(corps, NodeFilter.SHOW_TEXT);
  const plage = document.createRange();
  let cumul = 0;
  let pose = false;
  let noeud;
  while ((noeud = marcheur.nextNode())) {
    const long = noeud.nodeValue.length;
    if (!pose && debut <= cumul + long) { plage.setStart(noeud, debut - cumul); pose = true; }
    if (pose && fin <= cumul + long) { plage.setEnd(noeud, fin - cumul); return plage; }
    cumul += long;
  }
  return null;
}

function surlignerRecherche() {
  if (!(window.CSS && CSS.highlights && window.Highlight)) return;
  const plages = lect.recherche.resultats.slice(0, 3000)
    .map((r) => plagePour(r.k, r.debut, r.fin)).filter(Boolean);
  CSS.highlights.set('rl-trouve', new Highlight(...plages));
  CSS.highlights.delete('rl-courant');
}

function allerResultat(i, place) {
  const liste = lect.recherche.resultats;
  if (!liste.length) return;
  lect.recherche.i = (i + liste.length) % liste.length;
  const r = liste[lect.recherche.i];
  const plage = plagePour(r.k, r.debut, r.fin);
  majCompteRecherche();
  if (!plage) return;
  if (window.CSS && CSS.highlights && window.Highlight) CSS.highlights.set('rl-courant', new Highlight(plage));
  montrer(plage);
  // L'ecoute se place au mot trouve : Espace le fait entendre.
  const mot = motDePlage(plage);
  if (mot >= 0 && place !== false) placerSansJouer(mot);
}

function montrer(plage) {
  const element = plage.startContainer.parentElement;
  const para = element && element.closest('.rl-para');
  if (para) para.scrollIntoView({ block: 'center' });
  requestAnimationFrame(() => {
    const zone = $('#rl-defilement');
    const r = plage.getBoundingClientRect();
    const z = zone.getBoundingClientRect();
    if (r.top < z.top + 30 || r.bottom > z.bottom - 30) zone.scrollTop += r.top - (z.top + z.height / 2);
  });
}

function motDePlage(plage) {
  let el = plage.startContainer.nodeType === 3 ? plage.startContainer.parentElement : plage.startContainer;
  if (el && el.classList && el.classList.contains('m')) return Number(el.dataset.i);
  // Debut dans un ecart : le mot suivant du meme paragraphe.
  let noeud = plage.startContainer;
  while (noeud && !(noeud.nodeType === 1 && noeud.classList.contains('m'))) noeud = noeud.nextSibling;
  return noeud ? Number(noeud.dataset.i) : -1;
}

function placerSansJouer(i) {
  if (!lect.audio || i < 0) return;
  const s = son();
  s.currentTime = Math.max(0, lect.mots[i].d - 0.3);
  suivreLecture(false);
}

/* ------------------------------------------------------ Points a verifier */

function calculerPoints() {
  const d = lect.d;
  const mots = lect.mots;
  const stats = d.statistiques || {};
  const listes = { doute: [], remplacement: [], silence: [], long: [] };
  mots.forEach((m, i) => {
    if (m.doute) listes.doute.push({ i: i });
    if (i && m.d - mots[i - 1].d >= SEUIL_SILENCE && mots[i - 1].d > 0) {
      listes.silence.push({ i: i, duree: m.d - mots[i - 1].d });
    }
  });
  (d.paragraphes || []).forEach((p, k) => {
    if ((p.fin || 0) - (p.debut || 0) >= SEUIL_PASSAGE) {
      const i = mots.findIndex((m) => m.k === k);
      if (i >= 0) listes.long.push({ i: i, duree: p.fin - p.debut });
    }
  });
  // Remplacements du vocabulaire : le mot marque « corrige » le plus proche
  // de l'instant du remplacement.
  const corriges = mots.map((m, i) => (m.c ? i : -1)).filter((i) => i >= 0);
  (d.remplacements || []).forEach((r) => {
    let meilleur = -1;
    let ecart = Infinity;
    const candidats = corriges.length ? corriges : mots.map((_, i) => i);
    candidats.forEach((i) => {
      const e = Math.abs(mots[i].d - r.debut);
      if (e < ecart) { ecart = e; meilleur = i; }
    });
    if (meilleur >= 0) listes.remplacement.push({ i: meilleur, rang: r.rang, avant: r.avant, apres: r.apres });
  });
  listes.remplacement.sort((a, b) => a.i - b.i);
  lect.points.listes = listes;
  lect.points.sansConfiance = !!(d.compagnon && !stats.mots && stats.sans_confiance);

  const choix = $('#rl-categorie');
  const options = [];
  options.push(lect.points.sansConfiance || !d.compagnon
    ? `<option value="doute" disabled>${ech(t(d.compagnon ? 'ui.rl.cat.doute_absent' : 'ui.rl.cat.doute_sans_compagnon'))}</option>`
    : `<option value="doute">${ech(tn('ui.rl.cat.doute', listes.doute.length))}</option>`);
  options.push(`<option value="remplacement">${ech(tn('ui.rl.cat.remplacement', listes.remplacement.length))}</option>`);
  options.push(`<option value="silence">${ech(tn('ui.rl.cat.silence', listes.silence.length, { s: SEUIL_SILENCE }))}</option>`);
  options.push(`<option value="long">${ech(tn('ui.rl.cat.long', listes.long.length, { s: SEUIL_PASSAGE }))}</option>`);
  choix.innerHTML = options.join('');
  let categorie = lect.points.categorie;
  const utilisable = (c) => c && !(c === 'doute' && (lect.points.sansConfiance || !d.compagnon));
  if (!utilisable(categorie) || (!listes[categorie].length && !lect.points.choisieParUtilisateur)) {
    categorie = ['doute', 'remplacement', 'silence', 'long'].find((c) => utilisable(c) && listes[c].length)
      || (utilisable('doute') ? 'doute' : 'remplacement');
  }
  lect.points.categorie = categorie;
  choix.value = categorie;
  lect.points.i = -1;
  majPoint();
}

function majPoint() {
  const liste = lect.points.listes[lect.points.categorie] || [];
  const i = lect.points.i;
  $('#rl-point').textContent = liste.length && i >= 0
    ? t('ui.rl.position_sur', { i: i + 1, n: liste.length }) : '';
  $('#rl-point-prec').disabled = !liste.length;
  $('#rl-point-suiv').disabled = !liste.length;
  $('#rl-annuler-remplacement').hidden = !(lect.points.categorie === 'remplacement' && i >= 0 && liste[i]);
}

function allerPoint(pas) {
  const liste = lect.points.listes[lect.points.categorie] || [];
  if (!liste.length) { statutRelecture(t('ui.rl.aucun_point')); return; }
  let i = lect.points.i;
  if (i < 0) {
    // Premier point apres l'endroit lu, ou le premier tout court.
    const repere = lect.vise >= 0 ? lect.vise : lect.courant;
    i = pas > 0 ? liste.findIndex((p) => p.i > repere) : liste.length - 1 - liste.slice().reverse().findIndex((p) => p.i < repere);
    if (i < 0 || i >= liste.length) i = pas > 0 ? 0 : liste.length - 1;
  } else {
    i = (i + pas + liste.length) % liste.length;
  }
  lect.points.i = i;
  viser(liste[i].i);
  majPoint();
  const point = liste[i];
  if (lect.points.categorie === 'silence' || lect.points.categorie === 'long') {
    statutRelecture(t('ui.rl.point_duree', { duree: formaterDuree(point.duree) }));
  } else if (lect.points.categorie === 'remplacement') {
    statutRelecture(t('ui.rl.point_remplacement', { avant: point.avant, apres: point.apres }));
  } else {
    const p = lect.mots[point.i].p;
    statutRelecture(t('ui.lecture.confiance', { pct: Math.round((p || 0) * 100) }));
  }
}

function viser(i) {
  if (lect.vise >= 0 && lect.spans[lect.vise]) lect.spans[lect.vise].classList.remove('vise');
  lect.vise = i;
  const span = lect.spans[i];
  if (!span) return;
  span.classList.add('vise');
  span.scrollIntoView({ block: 'center' });
  // Une seconde avant le mot : on entend ce qui l'amene.
  if (lect.audio) {
    son().currentTime = Math.max(0, lect.mots[i].d - 1);
    suivreLecture(false);
  }
}

async function annulerRemplacementCourant() {
  const liste = lect.points.listes.remplacement || [];
  const point = liste[lect.points.i];
  if (!point || !lect.d) return;
  const r = await ecrireRelecture(() => pywebview.api.annuler_remplacement(lect.chemin, Number(point.rang)));
  if (r.ok) {
    journaliser('ok', r.message);
    await chargerLecture(lect.chemin, true);
  }
  statutRelecture(r.message, r.ok ? 'ok' : 'erreur');
}

/* ----------------------------------------------------- Correction en place */

function masquerBoutonCorrection() {
  $('#btn-corriger-selection').classList.remove('visible');
}

/* Selection dans un seul paragraphe, courte : le bouton « Corriger » se pose
   dessous, et Entree fait la meme chose. */
function lireSelection() {
  const selection = window.getSelection();
  const zone = $('#rl-texte');
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const plage = selection.getRangeAt(0);
  if (!zone.contains(plage.startContainer) || !zone.contains(plage.endContainer)) return null;
  const debutCorps = (plage.startContainer.nodeType === 3 ? plage.startContainer.parentElement : plage.startContainer).closest('.rl-corps');
  const finCorps = (plage.endContainer.nodeType === 3 ? plage.endContainer.parentElement : plage.endContainer).closest('.rl-corps');
  if (!debutCorps || debutCorps !== finCorps) return null;
  const brut = selection.toString();
  const source = brut.trim().replace(/\s+/g, ' ');
  if (!source || source.length > 80) return null;
  const avant = document.createRange();
  avant.setStart(debutCorps, 0);
  avant.setEnd(plage.startContainer, plage.startOffset);
  const apres = document.createRange();
  apres.setStart(plage.endContainer, plage.endOffset);
  apres.setEnd(debutCorps, debutCorps.childNodes.length);
  const tete = brut.length - brut.trimStart().length;
  const queue = brut.length - brut.trimEnd().length;
  // Position exacte dans le texte du paragraphe : la correction « ici » vise
  // cet endroit et lui seul, meme au milieu d'un mot ou a partir d'une
  // apostrophe.
  const debut = avant.toString().length + tete;
  const para = debutCorps.closest('.rl-para');
  return {
    source: source,
    avant: avant.toString() + brut.slice(0, tete),
    apres: brut.slice(brut.length - queue) + apres.toString(),
    position: para ? { k: Number(para.dataset.p), debut: debut, fin: debut + brut.trim().length } : null,
    rect: plage.getBoundingClientRect(),
  };
}

function positionnerBoutonCorrection() {
  const bouton = $('#btn-corriger-selection');
  const sel = lireSelection();
  if (!sel) { bouton.classList.remove('visible'); lect.selection = null; return; }
  lect.selection = sel;
  const largeur = (etat.config.zoom || 1);
  bouton.style.left = Math.max(8, Math.min(window.innerWidth / largeur - 150, sel.rect.left)) + 'px';
  bouton.style.top = (sel.rect.bottom + 6) + 'px';
  bouton.classList.add('visible');
}

function ouvrirCorrection() {
  masquerBoutonCorrection();
  const sel = lect.selection || lireSelection();
  if (!sel || !lect.d) return;
  lect.selection = sel;
  $('#correction-source').value = sel.source;
  $('#correction-cible').value = sel.source;
  // La regle vaut pour toutes les transcriptions a venir : c'est un choix
  // explicite, jamais coche d'office.
  $('#correction-regle').checked = false;
  $('#case-regle').hidden = etat.config.corrections_apprises === false;
  $('#retour-correction').innerHTML = '';
  $('#apercu-correction').innerHTML = '';
  lect.correction = { nombre: 0, extraits: [], choisie: -1 };
  majQuestionRegle();
  majBoutonCorrection();
  ouvrirModale('#modale-correction');
  setTimeout(() => { $('#correction-cible').focus(); $('#correction-cible').select(); }, 50);
}

function majQuestionRegle() {
  const source = $('#correction-source').value.trim();
  const cible = $('#correction-cible').value.trim();
  $('#correction-question').textContent = t('ui.correction.question_detaillee', {
    source: source, cible: cible || t('ui.correction.attente'),
  });
  clearTimeout(lect.minuterieApercu);
  lect.minuterieApercu = setTimeout(majApercuCorrection, 200);
}

/* Avant d'appliquer : les endroits du fichier qui contiennent la forme, celui
   de la selection coche, les autres a cocher si on le veut. */
async function majApercuCorrection() {
  const zone = $('#apercu-correction');
  const source = $('#correction-source').value.trim();
  const cible = $('#correction-cible').value.trim();
  if (!lect.d || !cible || cible === source) {
    zone.innerHTML = '';
    lect.correction = { nombre: 0, extraits: [], choisie: -1 };
    majBoutonCorrection();
    return;
  }
  let r;
  try {
    r = await appelPasserelle('occurrences_correction', lect.chemin, source, cible,
      lect.selection ? lect.selection.avant : '', lect.selection ? lect.selection.apres : '',
      lect.selection ? lect.selection.position : null);
  } catch (e) { console.error(e); zone.innerHTML = ''; return; }
  if ($('#correction-cible').value.trim() !== cible) return;   // saisie depassee
  if (!r.ok) {
    zone.innerHTML = encartAttention(r.message || t('ui.rl.code.' + (r.code || 'echec')));
    lect.correction = { nombre: 0, extraits: [], choisie: -1 };
    majBoutonCorrection();
    return;
  }
  lect.correction = { nombre: r.nombre, extraits: r.extraits || [], choisie: r.choisie };
  const lignes = lect.correction.extraits.map((x) => {
    const ici = x.rang === r.choisie;
    return `<li class="${ici ? 'ici' : ''}"><label><input type="checkbox" data-rang="${x.rang}" ${ici ? 'checked' : ''}>
      <span>${x.debut_coupe ? '…' : ''}${ech(x.avant)}<mark>${ech(x.forme)}</mark>${ech(x.apres)}${x.fin_coupee ? '…' : ''}${
        ici ? `<span class="etiquette-ici">${ech(t('ui.correction.ici'))}</span>` : ''}</span></label></li>`;
  });
  const reste = r.nombre - lect.correction.extraits.length;
  if (reste > 0) lignes.push(`<li class="reste">${ech(tn('ui.correction.autres', reste))}</li>`);
  const titre = r.choisie < 0
    ? t('ui.correction.non_situe')
    : tn('ui.correction.endroits', r.nombre);
  zone.innerHTML = `<div class="apercu-titre"><span>${ech(titre)}</span>
      ${r.nombre > 1 ? `<button class="bouton-lien" data-cocher="tout">${ech(t('ui.correction.tout_cocher'))}</button>` : ''}
      ${r.nombre > 1 && r.choisie >= 0 ? `<button class="bouton-lien" data-cocher="ici">${ech(t('ui.correction.seulement_ici'))}</button>` : ''}
    </div><ul>${lignes.join('')}</ul>`;
  majBoutonCorrection();
}

function rangsCoches() {
  return $$('#apercu-correction input[data-rang]:checked').map((c) => Number(c.dataset.rang));
}

function majBoutonCorrection() {
  const bouton = $('#btn-appliquer-correction');
  const total = lect.correction.nombre;
  const coches = rangsCoches().length + (lect.correction.tous ? Math.max(0, total - lect.correction.extraits.length) : 0);
  bouton.disabled = !coches;
  bouton.textContent = coches && coches === total && total > 1
    ? tn('ui.correction.appliquer_tous', total)
    : tn('ui.correction.appliquer_n', Math.max(coches, 1));
}

async function appliquerCorrection() {
  if (!lect.d) return;
  const bouton = $('#btn-appliquer-correction');
  if (bouton.disabled) return;
  const source = $('#correction-source').value.trim();
  const cible = $('#correction-cible').value.trim();
  const coches = rangsCoches();
  const tous = coches.length === lect.correction.extraits.length
    && (lect.correction.tous || lect.correction.nombre === coches.length);
  bouton.disabled = true;
  try {
    const r = await ecrireRelecture(() => appelPasserelle('corriger_occurrences', lect.chemin, source, cible,
      tous ? 'tous' : coches, $('#correction-regle').checked,
      lect.selection ? lect.selection.position : null, lect.d.empreinte || ''));
    if (!r.ok) {
      $('#retour-correction').innerHTML = encartAttention(r.message || t('ui.rl.code.' + (r.code || 'echec')));
      return;
    }
    fermerModale($('#modale-correction'));
    if (r.nb_corrections !== undefined) majCorrections({ nb: r.nb_corrections, erreurs: [] });
    const message = tn('ui.correction.faite', r.remplacements || 1, { source: source, cible: cible })
      + (r.regle_ajoutee ? ' ' + t('ui.correction.regle_memorisee') : '');
    journaliser('ok', message);
    majCompteurVocabulaire();
    await chargerLecture(lect.chemin, true);
    statutRelecture(message, 'ok');
  } catch (e) {
    console.error(e);
    $('#retour-correction').innerHTML = encartAttention(t('ui.correction.echec'));
  } finally {
    majBoutonCorrection();
  }
}

function majAnnulation() {
  const niveaux = (lect.d && lect.d.niveaux) || 0;
  const bouton = $('#rl-annuler');
  bouton.hidden = !(lect.d && lect.d.annulable);
  bouton.title = niveaux > 1 ? tn('ui.rl.annuler_niveaux', niveaux) : '';
  const original = !!(lect.d && lect.d.original);
  $('#rl-original').hidden = !original;
  $('#rl-sep-original').hidden = !original;
}

async function annulerCorrection() {
  if (!lect.d) return;
  if (!lect.d.annulable) { statutRelecture(t('ui.rl.rien_a_annuler')); return; }
  const r = await ecrireRelecture(() => pywebview.api.annuler_correction(lect.chemin));
  if (r.nb_corrections !== undefined) majCorrections({ nb: r.nb_corrections, erreurs: [] });
  journaliser(r.ok ? 'ok' : 'attention', r.message);
  majCompteurVocabulaire();
  await chargerLecture(lect.chemin, true);
  statutRelecture(r.message, r.ok ? 'ok' : 'erreur');
}

/* -------------------------------------------------------------- Locuteurs */

function ouvrirRenommage(nom) {
  lect.locuteur = nom;
  $('#titre-locuteur').textContent = t('ui.loc.renommer_titre', { nom: nom });
  $('#locuteur-nom').value = /^(Locuteur|Speaker)\s+\d+$/.test(nom) ? '' : nom;
  $('#locuteur-nom').placeholder = nom;
  const n = (lect.d.paragraphes || []).filter((p) => p.locuteur === nom).length;
  $('#locuteur-aide').textContent = tn('ui.loc.renommer_aide', n);
  $('#retour-locuteur').innerHTML = '';
  ouvrirModale('#modale-locuteur');
}

async function renommerLocuteur() {
  const nouveau = $('#locuteur-nom').value.trim();
  if (!nouveau) return;
  const r = await ecrireRelecture(() => appelPasserelle('renommer_locuteur', lect.chemin, lect.locuteur, nouveau,
    lect.d.empreinte || ''));
  if (!r.ok) {
    $('#retour-locuteur').innerHTML = encartAttention(t('ui.rl.code.' + (r.code || 'echec')));
    return;
  }
  fermerModale($('#modale-locuteur'));
  const message = tn('ui.loc.renomme', r.paragraphes || r.segments || 1, { ancien: lect.locuteur, nouveau: nouveau });
  journaliser('ok', message);
  await chargerLecture(lect.chemin, true);
  statutRelecture(message, 'ok');
}

/* ---------------------------------------------------------------- Exports */

function paragraphesAvecHeures() {
  return (lect.d.paragraphes || []).map((p) =>
    `[${horodatage(p.debut)}] ` + (p.locuteur ? p.locuteur + ' : ' : '') + p.texte).join('\n\n');
}

function markdown() {
  const d = lect.d;
  const m = d.meta || {};
  const entete = [`# ${String(d.nom || m.fichier || '').replace(/\.txt$/i, '')}`, '',
    `*${[m.duree, m.date, m.locuteurs_texte].filter(Boolean).join(' · ')}*`, ''];
  const corps = (d.paragraphes || []).map((p) =>
    `**[${horodatage(p.debut)}]${p.locuteur ? ' ' + p.locuteur : ''}** ${p.texte}`);
  return entete.concat(corps.join('\n\n')).join('\n') + '\n';
}

async function exporter(nature) {
  fermerMenuExport();
  if (!lect.d) return;
  if (nature === 'texte') {
    // Le corps du fichier, en-tete retire : ce que l'on a relu, a la lettre.
    await copier(typeof lect.d.corps === 'string' ? lect.d.corps : paragraphesAvecHeures());
    statutRelecture(t('ui.rl.copie.texte'), 'ok');
  } else if (nature === 'heures') {
    await copier(paragraphesAvecHeures());
    statutRelecture(t('ui.rl.copie.heures'), 'ok');
  } else if (nature === 'markdown') {
    await copier(markdown());
    statutRelecture(t('ui.rl.copie.markdown'), 'ok');
  } else if (nature === 'enregistrer_md') {
    const r = await appelPasserelle('enregistrer_export', lect.chemin, '.md', markdown());
    statutRelecture(r.ok ? t('ui.rl.export_ecrit', { nom: r.nom }) : t('ui.rl.code.' + (r.code || 'echec')),
      r.ok ? 'ok' : 'erreur');
    if (r.ok) journaliser('ok', t('ui.rl.export_ecrit', { nom: r.chemin }));
  } else if (nature === 'ouvrir') {
    pywebview.api.ouvrir(lect.chemin);
  } else if (nature === 'dossier') {
    appelPasserelle('ouvrir_dossier_de', lect.chemin).catch(() => pywebview.api.ouvrir_dossier_sortie());
  } else if (nature === 'original') {
    // Annulable comme une correction : pas de confirmation.
    const r = await ecrireRelecture(() => appelPasserelle('revenir_original', lect.chemin));
    journaliser(r.ok ? 'ok' : 'attention', r.message);
    await chargerLecture(lect.chemin, true);
    statutRelecture(r.message, r.ok ? 'ok' : 'erreur');
  }
}

async function copier(texte) {
  try { await navigator.clipboard.writeText(texte); }
  catch (e) { pywebview.api.copier(texte); }
}

async function copierPourIA() {
  if (!lect.d) return;
  const bouton = $('#btn-copier-ia');
  bouton.disabled = true;
  try {
    const r = await pywebview.api.copier_pour_ia(lect.chemin);
    if (!r.ok) { statutRelecture(r.message || t('ui.lecture.copie_impossible'), 'erreur'); return; }
    statutRelecture(t('ui.lecture.ia_copie'), 'ok');
    journaliser('ok', r.message);
  } catch (e) {
    console.error(e);
    statutRelecture(t('ui.lecture.copie_impossible'), 'erreur');
  } finally {
    bouton.disabled = false;
  }
}

function basculerMenuExport() {
  const menu = $('#rl-menu-export');
  const ouvrir = menu.hidden;
  menu.hidden = !ouvrir;
  $('#rl-exporter').setAttribute('aria-expanded', ouvrir ? 'true' : 'false');
  if (ouvrir) menu.querySelector('button').focus();
}

function fermerMenuExport() {
  const menu = $('#rl-menu-export');
  if (menu.hidden) return false;
  menu.hidden = true;
  $('#rl-exporter').setAttribute('aria-expanded', 'false');
  return true;
}

/* ---------------------------------------------------------------- Clavier */

/* Echap dans la relecture : d'abord ce qui est ouvert dedans (menu, selection,
   recherche), ensuite seulement le retour a l'ecran des reunions. */
function echapRelecture() {
  if (fermerMenuExport()) { $('#rl-exporter').focus(); return true; }
  if ($('#btn-corriger-selection').classList.contains('visible')) {
    masquerBoutonCorrection();
    window.getSelection().removeAllRanges();
    return true;
  }
  const champ = $('#rl-chercher');
  if (document.activeElement === champ && champ.value) {
    champ.value = '';
    chercher('');
    return true;
  }
  return false;
}

function dansUnChamp(cible) {
  return !!(cible && cible.closest && cible.closest('input, textarea, select, [contenteditable]'));
}

function clavierRelecture(e) {
  if (etat.vue !== 'relecture' || $('.voile.ouvert')) return;
  const cible = e.target;
  const champ = dansUnChamp(cible);
  const touche = e.key;
  if (e.ctrlKey && (touche === 'f' || touche === 'F')) {
    e.preventDefault();
    $('#rl-chercher').focus();
    $('#rl-chercher').select();
    return;
  }
  if (touche === 'F3') {
    e.preventDefault();
    allerResultat(lect.recherche.i + (e.shiftKey ? -1 : 1));
    return;
  }
  if (e.ctrlKey && (touche === 'z' || touche === 'Z') && !champ) {
    e.preventDefault();
    annulerCorrection();
    return;
  }
  if (champ) return;
  if (touche === 'Enter' && lireSelection()) {
    e.preventDefault();
    ouvrirCorrection();
    return;
  }
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (touche === ' ' && !cible.closest('button')) {
    e.preventDefault();
    basculerLecture();
  } else if (touche === 'ArrowLeft' || touche === 'ArrowRight') {
    if (cible.closest('[role=menu]')) return;
    e.preventDefault();
    deplacer(touche === 'ArrowLeft' ? -5 : 5);
  } else if (touche === '[' || touche === ']') {
    e.preventDefault();
    changerVitesse(touche === '[' ? -1 : 1);
  } else if (touche === 'n' || touche === 'N') {
    e.preventDefault();
    allerPoint(e.shiftKey ? -1 : 1);
  }
}

/* ----------------------------------------------------------------- Cablage */

document.addEventListener('DOMContentLoaded', () => {
  const s = son();
  s.addEventListener('loadedmetadata', () => {
    lect.audio = true;
    activerLecteur(true);
    $('#rl-position').max = String(s.duration || 0);
    suivreLecture(false);
  });
  s.addEventListener('error', () => {
    if (!s.getAttribute('src')) return;
    lect.audio = false;
    activerLecteur(false);
    lect.audioAvis = t('ui.rl.audio.audio_illisible');
    if (lect.d) dessinerAvis();
  });
  s.addEventListener('play', () => {
    majBoutonLire(true);
    cancelAnimationFrame(lect.boucle);
    lect.boucle = requestAnimationFrame(boucleLecture);
  });
  s.addEventListener('pause', () => { majBoutonLire(false); suivreLecture(false); });
  s.addEventListener('ended', () => majBoutonLire(false));
  s.addEventListener('seeked', () => suivreLecture(false));

  $('#rl-retour').addEventListener('click', retourPrincipale);
  $('#rl-lire').addEventListener('click', basculerLecture);
  $('#rl-reculer').addEventListener('click', () => deplacer(-5));
  $('#rl-avancer').addEventListener('click', () => deplacer(5));
  $('#rl-vitesse').addEventListener('change', (e) => { son().playbackRate = Number(e.target.value) || 1; });
  const position = $('#rl-position');
  position.addEventListener('input', () => {
    lect.glisse = true;
    $('#rl-temps').textContent = `${formaterSecondes(Number(position.value))} / ${formaterSecondes(s.duration || 0)}`;
  });
  position.addEventListener('change', () => { lect.glisse = false; placerA(Number(position.value)); });

  let minuterie = 0;
  $('#rl-chercher').addEventListener('input', (e) => {
    clearTimeout(minuterie);
    minuterie = setTimeout(() => chercher(e.target.value), 120);
  });
  $('#rl-chercher').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      clearTimeout(minuterie);
      if (lect.recherche.terme !== e.target.value) chercher(e.target.value);
      else allerResultat(lect.recherche.i + (e.shiftKey ? -1 : 1));
    }
  });
  $('#rl-chercher-prec').addEventListener('click', () => allerResultat(lect.recherche.i - 1));
  $('#rl-chercher-suiv').addEventListener('click', () => allerResultat(lect.recherche.i + 1));

  $('#rl-categorie').addEventListener('change', (e) => {
    lect.points.categorie = e.target.value;
    lect.points.choisieParUtilisateur = true;
    lect.points.i = -1;
    majPoint();
  });
  $('#rl-point-prec').addEventListener('click', () => allerPoint(-1));
  $('#rl-point-suiv').addEventListener('click', () => allerPoint(1));
  $('#rl-annuler-remplacement').addEventListener('click', annulerRemplacementCourant);

  $('#rl-annuler').addEventListener('click', annulerCorrection);
  $('#rl-exporter').addEventListener('click', basculerMenuExport);
  $('#rl-menu-export').addEventListener('click', (e) => {
    const b = e.target.closest('[data-export]');
    if (b) exporter(b.dataset.export);
  });
  $('#rl-menu-export').addEventListener('keydown', (e) => {
    const items = $$('#rl-menu-export [role=menuitem]');
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
    } else if (e.key === 'Tab') {
      fermerMenuExport();
    }
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.menu-conteneur')) fermerMenuExport();
    if (!e.target.closest || !e.target.closest('#btn-corriger-selection')) masquerBoutonCorrection();
  });
  $('#btn-copier-ia').addEventListener('click', copierPourIA);

  // Texte : un mot clique place l'ecoute ; l'heure d'un paragraphe le fait
  // entendre ; un locuteur se renomme.
  const texte = $('#rl-texte');
  texte.addEventListener('click', (e) => {
    const heure = e.target.closest('.rl-heure');
    if (heure) {
      const p = lect.d.paragraphes[Number(heure.dataset.p)];
      if (lect.audio && p) { placerA(p.debut); son().play().catch(() => {}); }
      return;
    }
    const loc = e.target.closest('.rl-locuteur');
    if (loc) { ouvrirRenommage(loc.dataset.loc); return; }
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) return;   // l'utilisateur selectionne
    const mot = e.target.closest('.m');
    if (mot && lect.audio) {
      const i = Number(mot.dataset.i);
      placerA(Math.max(0, lect.mots[i].d - 0.05));
      marquerLu(i, false);
    }
  });
  texte.addEventListener('mouseover', (e) => {
    const mot = e.target.closest && e.target.closest('.md, .mf');
    if (!mot || mot.title) return;
    const p = lect.mots[Number(mot.dataset.i)].p;
    mot.title = t('ui.lecture.confiance', { pct: Math.round((p || 0) * 100) });
  });
  texte.addEventListener('mouseup', () => setTimeout(positionnerBoutonCorrection, 0));
  texte.addEventListener('keyup', () => setTimeout(positionnerBoutonCorrection, 0));
  $('#rl-defilement').addEventListener('scroll', masquerBoutonCorrection, { passive: true });
  $('#btn-corriger-selection').addEventListener('mousedown', (e) => e.preventDefault());
  $('#btn-corriger-selection').addEventListener('click', ouvrirCorrection);

  // Correction
  $('#correction-cible').addEventListener('input', majQuestionRegle);
  $('#correction-cible').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); appliquerCorrection(); }
  });
  $('#apercu-correction').addEventListener('change', () => {
    // Une case decochee a la main : « tout » ne vaut plus pour les endroits non listes.
    if (rangsCoches().length < lect.correction.extraits.length) lect.correction.tous = false;
    majBoutonCorrection();
  });
  $('#apercu-correction').addEventListener('click', (e) => {
    const b = e.target.closest('[data-cocher]');
    if (!b) return;
    const tout = b.dataset.cocher === 'tout';
    lect.correction.tous = tout;
    $$('#apercu-correction input[data-rang]').forEach((c) => {
      c.checked = tout || Number(c.dataset.rang) === lect.correction.choisie;
    });
    majBoutonCorrection();
  });
  $('#btn-appliquer-correction').addEventListener('click', appliquerCorrection);

  // Locuteurs
  $('#btn-renommer-locuteur').addEventListener('click', renommerLocuteur);
  $('#locuteur-nom').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); renommerLocuteur(); }
  });

  document.addEventListener('keydown', clavierRelecture);
  window.addEventListener('focus', () => { verifierFichier(); });
});
