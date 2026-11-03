/*
 * Dictée vocale pour les champs commentaire (français).
 *
 * Ajoute automatiquement un bouton 🎤 dans chaque <textarea> de la page.
 * Un clic : on parle, le texte s'écrit à l'endroit du curseur. Un 2e clic : arrêt.
 * L'enregistrement s'arrête aussi tout seul après quelques secondes de silence.
 *
 * Exclure un champ    : <textarea data-dictee="off">
 * Ajouter sur un input: <input type="text" data-dictee>
 * Champs readonly / disabled : ignorés.
 *
 * Moteur : Web Speech API du navigateur (Chrome, Edge, Safari, Chrome Android).
 * Non disponible sur Firefox : le bouton n'apparaît pas, la saisie au clavier reste normale.
 * Le micro exige HTTPS (ou http://localhost).
 */
(function () {
  'use strict';

  var Reco = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Reco) return; // navigateur non compatible : on ne touche à rien

  var LANG = document.documentElement.getAttribute('data-dictee-lang') || 'fr-FR';
  var SILENCE_MS = 8000;

  // Ponctuation dictée à voix haute (Chrome ne la convertit pas toujours en français)
  var PONCTUATION = [
    [/\s*\bpoint à la ligne\b\s*/gi, '.\n'],
    [/\s*\b(?:à la ligne|nouvelle ligne|retour à la ligne)\b\s*/gi, '\n'],
    [/\s*\bpoint d'interrogation\b/gi, ' ?'],
    [/\s*\bpoint d'exclamation\b/gi, ' !'],
    [/\s*\bpoint virgule\b/gi, ' ;'],
    [/\s*\bvirgule\b/gi, ','],
    [/\s*\bpoint final\b/gi, '.']
  ];

  var CSS = '' +
    '.dictee-wrap{position:relative;display:block;}' +
    '.dictee-wrap>textarea,.dictee-wrap>input{padding-right:50px !important;width:100%;box-sizing:border-box;}' +
    '.dictee-btn{position:absolute;right:12px;bottom:8px;width:32px;height:32px;border-radius:50%;' +
      'border:1.5px solid var(--border,#cbd5e1);background:var(--surface,#fff);color:var(--text-muted,#64748b);' +
      'display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;line-height:1;z-index:2;' +
      'transition:background .15s,color .15s,border-color .15s;}' +
    '.dictee-wrap>input+.dictee-btn{top:50%;bottom:auto;transform:translateY(-50%);width:28px;height:28px;}' +
    '.dictee-btn:hover{border-color:var(--primary,#2563eb);color:var(--primary,#2563eb);}' +
    '.dictee-btn svg{width:16px;height:16px;}' +
    '.dictee-btn.is-on{background:var(--danger,#dc2626);border-color:var(--danger,#dc2626);color:#fff;' +
      'animation:dictee-pulse 1.2s ease-in-out infinite;}' +
    '@keyframes dictee-pulse{0%{box-shadow:0 0 0 0 rgba(220,38,38,.45)}70%{box-shadow:0 0 0 9px rgba(220,38,38,0)}100%{box-shadow:0 0 0 0 rgba(220,38,38,0)}}' +
    '.dictee-live{position:absolute;left:8px;right:52px;bottom:8px;font-size:12px;font-style:italic;' +
      'color:var(--text-muted,#64748b);background:var(--surface,#fff);padding:2px 4px;border-radius:4px;' +
      'pointer-events:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.95;}' +
    '.dictee-live:empty{display:none;}' +
    '.dictee-msg{font-size:12px;color:var(--danger,#dc2626);margin-top:4px;}';

  var MIC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="17" x2="12" y2="22"/></svg>';

  var actif = null; // { field, btn, live, reco, timer }

  function injecterCss() {
    if (document.getElementById('dictee-css')) return;
    var s = document.createElement('style');
    s.id = 'dictee-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function nettoyer(txt) {
    PONCTUATION.forEach(function (p) { txt = txt.replace(p[0], p[1]); });
    txt = txt.replace(/[ \t]+/g, ' ').replace(/ +([,.])/g, '$1').replace(/ *\n */g, '\n');
    // Majuscule après un point, ? ! ou un retour à la ligne
    return txt.replace(/([.!?]\s+|\n)(\p{Ll})/gu, function (m, sep, c) { return sep + c.toUpperCase(); });
  }

  // Assemble les résultats définitifs en supprimant les répétitions.
  // Chrome (surtout Android) renvoie souvent la même phrase plusieurs fois,
  // ou une version qui reprend la précédente en la complétant.
  function assembler(results) {
    var morceaux = [];
    for (var i = 0; i < results.length; i++) {
      if (!results[i] || !results[i].isFinal) continue;
      var t = results[i][0].transcript.trim();
      if (!t) continue;
      var dernier = morceaux.length ? morceaux[morceaux.length - 1] : null;
      var tl = t.toLowerCase(), dl = dernier && dernier.toLowerCase();
      if (dernier !== null && tl.indexOf(dl) === 0) morceaux[morceaux.length - 1] = t; // version complétée
      else if (dernier !== null && dl.indexOf(tl) === 0) continue;                    // doublon plus court
      else morceaux.push(t);
    }
    return morceaux.join(' ');
  }

  // Écrit le texte dicté entre "avant" et "apres" (figés au démarrage), avec espace et majuscule
  function ecrire(a, brut) {
    var field = a.field, avant = a.avant, apres = a.apres;
    var texte = nettoyer(brut).trim();
    if (texte) {
      if (avant.replace(/\s+$/, '') === '' || /[.!?\n]$/.test(avant.replace(/ +$/, ''))) {
        texte = texte.charAt(0).toUpperCase() + texte.slice(1);
      }
      if (avant && !/\s$/.test(avant) && !/^[,.;?!\n]/.test(texte)) texte = ' ' + texte;
      if (apres && !/^\s/.test(apres) && !/\n$/.test(texte)) texte = texte + ' ';
    }
    if (avant + texte + apres === field.value) return;
    field.value = avant + texte + apres;
    var pos = (avant + texte).length;
    try { field.setSelectionRange(pos, pos); } catch (e) {}
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function message(field, txt) {
    var wrap = field.parentNode;
    var m = wrap.nextElementSibling;
    if (!m || !m.classList.contains('dictee-msg')) {
      m = document.createElement('div');
      m.className = 'dictee-msg';
      wrap.parentNode.insertBefore(m, wrap.nextSibling);
    }
    m.textContent = txt;
    clearTimeout(m._t);
    m._t = setTimeout(function () { m.remove(); }, 6000);
  }

  function arreter() {
    if (!actif) return;
    var a = actif;
    actif = null;
    clearTimeout(a.timer);
    try { a.reco.stop(); } catch (e) {}
    a.btn.classList.remove('is-on');
    a.btn.setAttribute('aria-pressed', 'false');
    a.btn.title = 'Dicter (micro)';
    a.live.textContent = '';
  }

  function demarrer(field, btn, live) {
    if (actif) {
      var memeChamp = actif.field === field;
      arreter();
      if (memeChamp) return;
    }
    var reco = new Reco();
    reco.lang = LANG;
    reco.continuous = true;
    reco.interimResults = true;
    reco.maxAlternatives = 1;

    var val = field.value;
    var focus = document.activeElement === field;
    var deb = focus && typeof field.selectionStart === 'number' ? field.selectionStart : val.length;
    var fin = focus && typeof field.selectionEnd === 'number' ? field.selectionEnd : val.length;
    var a = { field: field, btn: btn, live: live, reco: reco, timer: null,
              avant: val.slice(0, deb), apres: val.slice(fin) };
    actif = a;

    function relancerMinuteur() {
      clearTimeout(a.timer);
      a.timer = setTimeout(function () { if (actif === a) arreter(); }, SILENCE_MS);
    }

    reco.onresult = function (ev) {
      if (actif !== a) return;
      // On relit toute la liste à chaque fois (au lieu de resultIndex, peu fiable sur Android)
      ecrire(a, assembler(ev.results));
      var provisoire = '';
      for (var i = 0; i < ev.results.length; i++) {
        if (ev.results[i] && !ev.results[i].isFinal) provisoire = ev.results[i][0].transcript;
      }
      live.textContent = provisoire ? '… ' + provisoire : '';
      relancerMinuteur();
    };
    reco.onerror = function (ev) {
      var txt = {
        'not-allowed': "Accès au micro refusé. Autorisez le micro pour ce site (icône à gauche de l'adresse).",
        'service-not-allowed': "Accès au micro refusé. Le site doit être ouvert en HTTPS.",
        'audio-capture': 'Aucun micro détecté.',
        'network': 'La dictée a besoin d’une connexion Internet.',
        'language-not-supported': 'Le français n’est pas disponible pour la dictée sur ce navigateur.'
      }[ev.error];
      if (txt) message(field, txt);
      if (actif === a) arreter();
    };
    reco.onend = function () { if (actif === a) arreter(); };

    try {
      reco.start();
    } catch (e) {
      actif = null;
      message(field, 'Impossible de démarrer la dictée.');
      return;
    }
    btn.classList.add('is-on');
    btn.setAttribute('aria-pressed', 'true');
    btn.title = 'Arrêter la dictée';
    field.focus();
    relancerMinuteur();
  }

  function equiper(field) {
    if (field.dataset.dicteeOk || field.dataset.dictee === 'off') return;
    if (field.readOnly || field.disabled || field.type === 'hidden') return;
    if (field.tagName === 'INPUT' && !field.hasAttribute('data-dictee')) return;
    field.dataset.dicteeOk = '1';

    var wrap = document.createElement('span');
    wrap.className = 'dictee-wrap';
    field.parentNode.insertBefore(wrap, field);
    wrap.appendChild(field);

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dictee-btn';
    btn.title = 'Dicter (micro)';
    btn.setAttribute('aria-label', 'Dicter le texte');
    btn.setAttribute('aria-pressed', 'false');
    btn.innerHTML = MIC;
    wrap.appendChild(btn);

    var live = document.createElement('span');
    live.className = 'dictee-live';
    live.setAttribute('aria-live', 'polite');
    wrap.appendChild(live);

    // mousedown : évite que le textarea perde la position du curseur
    btn.addEventListener('mousedown', function (e) { e.preventDefault(); });
    btn.addEventListener('click', function () { demarrer(field, btn, live); });
  }

  function scanner(racine) {
    (racine || document).querySelectorAll('textarea, input[data-dictee]').forEach(equiper);
  }

  function init() {
    injecterCss();
    scanner();
    // Champs ajoutés plus tard (modales, formulaires dynamiques)
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType !== 1) return;
          if (n.matches && n.matches('textarea, input[data-dictee]')) equiper(n);
          else if (n.querySelectorAll) scanner(n);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
    // Arrêter si on quitte la page ou si on envoie le formulaire
    document.addEventListener('submit', arreter, true);
    window.addEventListener('pagehide', arreter);
  }

  window.Dictee = { scanner: scanner, arreter: arreter };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
