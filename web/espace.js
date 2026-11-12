/* =========================================================================
   Scribouille : espace disque, ressources et effacement complet

   Reglages, Avance, Espace disque. Ce que Scribouille occupe reellement, poste
   par poste, ce que l'on peut liberer sans rien perdre, la memoire et le
   processeur pendant l'usage, et l'effacement complet precede d'un apercu
   detaille. Les transcriptions vivent a part et ne sont jamais effacees sans
   demande explicite.

   Contrat de passerelle (branche « moteur ») :
     espace_inventaire()  -> { postes: [{ cle, libelle, octets, liberable,
                              description, chemins }], total_octets,
                              transcriptions_octets }
     espace_liberer(cles) -> { ok, octets_liberes?, message? }
     effacement_apercu(garder_transcriptions)
                          -> { ok, jeton, elements: [{ libelle, chemin, octets }],
                               total_octets, conserves?: [{ libelle, chemin }] }
     effacement_executer(jeton) -> { ok, message? }
     moteur_etat()        -> { etat, modele? } ou null
     usage_instantane()   -> { fenetre: { memoire_octets, processeur_pct },
                               moteur: { ... } ou null } ou null
   ========================================================================= */

'use strict';

const espace = { inventaire: null, minuterie: 0, apercu: null, enCours: false };

function ouvrirEspace() {
  mesurerEspace();
  clearInterval(espace.minuterie);
  majRessources();
  espace.minuterie = setInterval(majRessources, 2000);
}

function quitterEspace() {
  clearInterval(espace.minuterie);
  espace.minuterie = 0;
}

async function mesurerEspace() {
  if (espace.enCours) return;
  espace.enCours = true;
  $('#espace-bilan').innerHTML = `<span class="aide">${ech(t('ui.espace.mesure'))}</span>`;
  $('#espace-postes').innerHTML = '';
  $('#btn-espace-liberer').disabled = true;
  $('#btn-espace-liberer').textContent = t('ui.espace.liberer_rien');
  let inventaire = null;
  try { inventaire = await appelPasserelle('espace_inventaire'); } catch (e) { inventaire = null; }
  espace.enCours = false;
  if (!inventaire || !Array.isArray(inventaire.postes)) {
    $('#espace-bilan').innerHTML = encartAttention(t('ui.espace.echec'));
    return;
  }
  espace.inventaire = inventaire;
  dessinerEspace();
}

function dessinerEspace() {
  const inv = espace.inventaire;
  const liberable = inv.postes.reduce((s, p) => s + (Number(p.liberable) || 0), 0);
  const chiffre = (valeur, etiquette, classe) => `<div class="chiffre ${classe || ''}">
    <span class="valeur">${ech(valeur)}</span><span class="etiquette">${ech(etiquette)}</span></div>`;
  $('#espace-bilan').innerHTML = chiffre(formaterOctets(inv.total_octets), t('ui.espace.total'))
    + chiffre(formaterOctets(liberable), t('ui.espace.liberable'), 'liberable')
    + chiffre(typeof inv.transcriptions_octets === 'number' ? formaterOctets(inv.transcriptions_octets)
      : t('ui.espace.non_mesure'), t('ui.espace.transcriptions'));

  const postes = inv.postes.slice().sort((a, b) => (b.octets || 0) - (a.octets || 0));
  $('#espace-postes').innerHTML = postes.map((p) => {
    const lib = Number(p.liberable) || 0;
    const chemins = (p.chemins || []).filter(Boolean);
    const id = 'poste-' + String(p.cle).replace(/[^a-z0-9_-]/gi, '');
    return `<div class="poste-espace">
      ${lib > 0 ? `<input type="checkbox" id="${ech(id)}" data-cle="${ech(p.cle)}" data-octets="${lib}">` : '<span></span>'}
      <div>
        <label class="libelle" ${lib > 0 ? `for="${ech(id)}"` : ''}>${ech(p.libelle)}</label>
        ${p.description ? `<div class="description">${ech(p.description)}</div>` : ''}
      </div>
      <div>
        <div class="octets">${ech(formaterOctets(p.octets))}</div>
        ${lib > 0 ? `<div class="liberable">${ech(t('ui.espace.liberable_poste', { taille: formaterOctets(lib) }))}</div>` : ''}
      </div>
      ${chemins.length ? `<details><summary>${ech(tn('ui.espace.emplacements', chemins.length))}</summary>
        ${chemins.map((c) => `<div class="chemin">${ech(c)}</div>`).join('')}</details>` : ''}
    </div>`;
  }).join('') || `<p class="vide">${ech(t('ui.espace.vide'))}</p>`;
  majBoutonLiberer();
}

function selectionEspace() {
  return $$('#espace-postes input[data-cle]:checked');
}

function majBoutonLiberer() {
  const choisis = selectionEspace();
  const octets = choisis.reduce((s, c) => s + Number(c.dataset.octets || 0), 0);
  const bouton = $('#btn-espace-liberer');
  bouton.disabled = !choisis.length;
  bouton.textContent = choisis.length
    ? t('ui.espace.liberer', { taille: formaterOctets(octets) })
    : t('ui.espace.liberer_rien');
}

async function libererEspace() {
  const cles = selectionEspace().map((c) => c.dataset.cle);
  if (!cles.length) return;
  $('#btn-espace-liberer').disabled = true;
  let r = null;
  try { r = await appelPasserelle('espace_liberer', cles); } catch (e) { r = null; }
  if (!r || !r.ok) {
    $('#espace-retour').innerHTML = encartAttention((r && r.message) || t('ui.espace.code.' + ((r && r.code) || 'echec')));
    majBoutonLiberer();
    return;
  }
  const message = r.message || t('ui.espace.libere', { taille: formaterOctets(r.octets_liberes || 0) });
  $('#espace-retour').innerHTML = encartSucces(message);
  journaliser('ok', message);
  await mesurerEspace();
}

/* Memoire et processeur, de la fenetre et du moteur, toutes les deux secondes
   tant que la section est ouverte. Rien n'est affiche si la mesure manque. */
async function majRessources() {
  let usage = null;
  let moteur = null;
  try { usage = await appelPasserelle('usage_instantane'); } catch (e) { usage = null; }
  try { moteur = await appelPasserelle('moteur_etat'); } catch (e) { moteur = null; }
  const bloc = $('#bloc-ressources');
  if (!usage) { bloc.hidden = true; return; }
  bloc.hidden = false;
  const carte = (titre, valeur) => `<div class="ressource"><div class="titre">${ech(titre)}</div>
    <div class="valeur">${ech(valeur)}</div></div>`;
  const mesure = (u) => t('ui.espace.mesure_ressource', {
    memoire: formaterOctets(u.memoire_octets || 0),
    processeur: nombreLocal(u.processeur_pct || 0, 0),
  });
  const cartes = [];
  if (usage.fenetre) cartes.push(carte(t('ui.espace.fenetre'), mesure(usage.fenetre)));
  const etatMoteur = moteur && moteur.etat ? t('ui.espace.moteur_etat.' + moteur.etat) : '';
  cartes.push(carte(t('ui.espace.moteur') + (moteur && moteur.modele ? ` (${moteur.modele})` : ''),
    usage.moteur ? mesure(usage.moteur) : (etatMoteur || t('ui.espace.moteur_etat.arrete'))));
  $('#ressources').innerHTML = cartes.join('');
}

/* ------------------------------------------------------ Effacement complet */

async function apercuEffacement() {
  const garder = !$('#eff-transcriptions').checked;
  let r = null;
  try { r = await appelPasserelle('effacement_apercu', garder); } catch (e) { r = null; }
  if (!r || !r.ok) {
    $('#espace-retour').innerHTML = encartAttention((r && r.message) || t('ui.espace.code.' + ((r && r.code) || 'echec')));
    return;
  }
  espace.apercu = r;
  const elements = r.elements || [];
  const total = typeof r.total_octets === 'number' ? r.total_octets
    : elements.reduce((s, x) => s + (Number(x.octets) || 0), 0);
  const conserves = r.conserves || [];
  $('#eff-contenu').innerHTML = `
    <p>${ech(tn('ui.eff.liste', elements.length, { taille: formaterOctets(total) }))}</p>
    <div class="eff-liste">${elements.map((x) => `<div class="eff-ligne">
      <span>${ech(x.libelle || '')}</span><span class="chemin">${ech(x.chemin || '')}</span>
      <span class="octets">${ech(formaterOctets(x.octets))}</span></div>`).join('')}</div>
    ${garder ? encartSucces(conserves.length
      ? t('ui.eff.gardees_ou', { ou: conserves.map((c) => c.chemin || c.libelle).join(', ') })
      : t('ui.eff.gardees')) : encartAttention(t('ui.eff.aussi_transcriptions_avis'))}`;
  $('#eff-compris').checked = false;
  $('#btn-eff-executer').disabled = true;
  $('#btn-eff-executer').textContent = t('ui.eff.executer_taille', { taille: formaterOctets(total) });
  $('#eff-retour').innerHTML = '';
  ouvrirModale('#modale-effacement');
}

async function executerEffacement() {
  if (!espace.apercu || !$('#eff-compris').checked) return;
  $('#btn-eff-executer').disabled = true;
  let r = null;
  try { r = await appelPasserelle('effacement_executer', espace.apercu.jeton); } catch (e) { r = null; }
  if (!r || !r.ok) {
    $('#eff-retour').innerHTML = encartAttention((r && r.message) || t('ui.espace.code.' + ((r && r.code) || 'echec')));
    $('#btn-eff-executer').disabled = !$('#eff-compris').checked;
    return;
  }
  $('#eff-retour').innerHTML = encartSucces(r.message || t('ui.eff.fait'));
  journaliser('ok', r.message || t('ui.eff.fait'));
  espace.apercu = null;
}

document.addEventListener('DOMContentLoaded', () => {
  $('#espace-postes').addEventListener('change', majBoutonLiberer);
  $('#btn-espace-liberer').addEventListener('click', libererEspace);
  $('#btn-espace-mesurer').addEventListener('click', mesurerEspace);
  $('#btn-eff-apercu').addEventListener('click', apercuEffacement);
  $('#eff-compris').addEventListener('change', (e) => { $('#btn-eff-executer').disabled = !e.target.checked; });
  $('#btn-eff-executer').addEventListener('click', executerEffacement);
});
