/* Session console: read the pane and drive it, from one place.
 *
 * A bottom sheet for a single session rather than an input box on every card.
 * That is not only about clutter -- the tail poll costs a tmux capture-pane per
 * tick, and there are ~70 sessions. One open console means one poll, whatever
 * the grid looks like.
 *
 * Requires control-token.js (window.ctbControl) for the auth header.
 * No inline handlers: the page runs under a CSP with a nonce, and Alpine's CSP
 * build, so everything here is addEventListener + data- attributes.
 */
(function () {
  'use strict';

  /* The VSCode webview is a different origin: the extension hands it this
   * page's markup as a string, so a relative '/api/...' resolves against
   * vscode-webview:// and never reaches the server. The extension sets
   * CTB_API_BASE; in a browser it is unset and nothing changes. */
  function api(path) { return (window.CTB_API_BASE || '') + path; }


  var TAIL_LINES = 40;
  /* Scrollback grows on demand: 40 lines is the right live window, but a long
   * answer runs past it and used to be simply unreachable. Reaching the top
   * asks for more. tmux keeps 50k lines per pane, so the ceiling here is about
   * what is worth shipping and re-rendering, not what exists. */
  var TAIL_STEP = 400;
  var MAX_TAIL_LINES = 5000;
  var POLL_MS = 2000;

  var state = { session: null, prev: null, timer: null, busy: false,
                lines: null, held: false, walk: null, order: null,
                fitted: false, fails: 0, warned: false, cols: 0,
                pending: null, sent: null,
                depth: TAIL_LINES, growing: false, exhausted: false,
                drafts: {}, boxTouched: null, ghost: false, hash: '', cache: {},
                pinned: true, skipped: 0 };
  var el = {};

  /* --- markup ------------------------------------------------------------ */

  /* --- theme ------------------------------------------------------------- */

  /* The sheet used to be dark whatever the board was: a terminal is dark, and
   * a light pane next to a dark board looked like a hole. It now follows the
   * board's toggle instead -- the board's key in localStorage, else the
   * system -- so a light board gets a light console, cool and near-monochrome like it.
   * Everything here paints through these variables; nothing carries a colour
   * of its own. They sit on <html> so the sheet, the search palette and the
   * floating chips all inherit one set, and switching is one write. */
  var THEME_KEY = 'ctb_theme';
  var THEMES = {
    dark: {
      scheme: 'dark',
      sheet: '#0b1220', well: '#020617', text: '#e5e7eb', muted: '#9ca3af',
      dim: '#6b7280', line: '#1f2937', 'tail-weight': '400',
      btn: '#1a2333', 'btn-hover': '#243044', active: '#1e3a8a', tray: '#070c18',
      stop: '#3f1d1d', 'stop-text': '#fca5a5', copybar: '#173a2a',
      accent: '#3b82f6', 'accent-hover': '#4f8ff7', 'accent-soft': 'rgba(59,130,246,0.18)', 'well-edge': 'inset 0 0 0 1px rgba(255,255,255,0.05)',
      ok: '#34d399', warn: '#fbbf24', err: '#ef4444', link: '#7dd3fc', info: '#60a5fa',
      overlay: 'rgba(2,6,23,0.72)', 'hint-bg': 'rgba(15,13,20,0.92)',
      shadow: '0 18px 48px rgba(0,0,0,0.55)',
      'scroll-track': 'rgba(255,255,255,0.05)',
      'scroll-thumb': 'rgba(148,163,184,0.32)',
      'scroll-thumb-hover': 'rgba(148,163,184,0.5)',
      /* The four importance hues, as foregrounds. The wash and the ring are
       * mixed from these, so a theme states each hue once. On black they can
       * be the light tints the grid uses; on paper the same tints fall to
       * about 2:1 against a white key, which is why every theme names its
       * own. */
      q1: '#fb7185', q2: '#f0a500', q3: '#60a5fa', q4: '#a8a2bd',
    },
    light: {
      scheme: 'light',
      /* Monospace that reads fine on black goes pale on paper: light-on-dark
       * bleeds and looks heavier than it is. So the light tail is ink on
       * off-white -- not pure white, which glares on an OLED at full
       * brightness outdoors -- at semibold, and the sheet around the well is
       * a shade darker so the pane has an edge to sit in. */
      sheet: '#eceef2', well: '#fbfbfc', text: '#0b0f14', muted: '#4b5563',
      dim: '#6b7280', line: '#d3d7de', 'tail-weight': '600',
      /* Controls are white shapes on the grey sheet, the way a grouped iOS
       * list sits: the sheet is the ground, everything on it is lighter. */
      btn: '#ffffff', 'btn-hover': '#f5f6f8', active: '#dbe6ff', tray: '#e2e5eb',
      stop: '#fbe1e1', 'stop-text': '#991b1b', copybar: '#d7f1e3',
      accent: '#2563eb', 'accent-hover': '#1d4ed8', 'accent-soft': 'rgba(37,99,235,0.14)', 'well-edge': 'inset 0 1px 2px rgba(16,24,40,0.06)',
      ok: '#047857', warn: '#b45309', err: '#dc2626', link: '#0b63a8', info: '#1d4ed8',
      overlay: 'rgba(17,24,39,0.40)', 'hint-bg': 'rgba(255,255,255,0.95)',
      shadow: '0 18px 48px rgba(16,24,40,0.18)',
      'scroll-track': 'rgba(0,0,0,0.04)',
      'scroll-thumb': 'rgba(17,24,39,0.22)',
      'scroll-thumb-hover': 'rgba(17,24,39,0.38)',
      /* Ink weights, in the same family as this theme's status colours. */
      q1: '#be123c', q2: '#92400e', q3: '#1d4ed8', q4: '#57534e',
    },
    /* 양피지: the board's vellum tile is the sheet itself; the well is a
     * lighter sheet laid on it, ink for text, keys are small vellum cards
     * with a sepia edge, and the seal red is the one accent. Status colours
     * are the muted pigments of an old map so they still mean the same. */
    parchment: {
      scheme: 'light',
      sheet: '#efe6d3', well: '#fbf6ea', text: '#2a1f14', muted: '#6b5a45',
      dim: '#7d6a52', line: '#cdbfa5', 'tail-weight': '600',
      btn: '#fbf6ea', 'btn-hover': '#fffbf1', active: '#e6d3c0', tray: '#e3d7c0',
      stop: '#efd5cf', 'stop-text': '#7b2d26', copybar: '#d9e6dc',
      accent: '#7b2d26', 'accent-hover': '#6a251f', 'accent-soft': 'rgba(123,45,38,0.14)',
      'well-edge': 'inset 0 0 0 1px rgba(90,60,30,0.18)',
      ok: '#2f6f50', warn: '#9a5a12', err: '#a2332b', link: '#2f5648', info: '#5b4636',
      overlay: 'rgba(60,40,20,0.42)', 'hint-bg': 'rgba(251,246,234,0.95)',
      shadow: '0 18px 48px rgba(70,45,20,0.22)',
      'scroll-track': 'rgba(90,60,30,0.06)',
      'scroll-thumb': 'rgba(90,60,30,0.28)',
      'scroll-thumb-hover': 'rgba(90,60,30,0.45)',
      /* Map pigments, like the status colours above: seal red, ochre, ink
       * green, and the sheet's own brown for the quiet one. */
      q1: '#a2332b', q2: '#7c4408', q3: '#2f5648', q4: '#6b5a45',
    },
  };

  function themeName() {
    try {
      var stored = localStorage.getItem(THEME_KEY);
      if (stored === 'parchment') return 'parchment';
      if (stored) return stored === 'dark' ? 'dark' : 'light';
    } catch (e) { /* private mode: fall through to the system */ }
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark' : 'light';
  }

  function applyTheme() {
    var t = THEMES[themeName()] || THEMES.light;
    if (!document.documentElement) return;   /* the test harness has no <html> */
    var st = document.documentElement.style;
    Object.keys(t).forEach(function (k) { st.setProperty('--con-' + k, t[k]); });
    st.setProperty('--con-sheet-img', themeName() === 'parchment' ? 'url(/static/img/parchment.jpg)' : 'none');
  }

  applyTheme();
  /* The board's toggle announces itself; the system can flip on its own. */
  document.addEventListener('ctb-theme', applyTheme);
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) mq.addEventListener('change', applyTheme);
  }

  /* One small icon set, drawn here at one stroke weight so every control
   * reads as the same family. Emoji and text arrows came from three fonts
   * at three weights and were most of what made the sheet look assembled.
   * 24-unit grid, 1.75 stroke, round joins; sized by the CSS around it. */
  var ICONS = {
    search: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM20 20l-4.4-4.4',
    copy: 'M9 9h10v11H9zM5 15V4h10',
    close: 'M6 6l12 12M18 6L6 18',
    up: 'M12 19V5M5 12l7-7 7 7',
    down: 'M12 5v14M5 12l7 7 7-7',
    left: 'M19 12H5M12 5l-7 7 7 7',
    right: 'M5 12h14M12 5l7 7-7 7',
    backspace: 'M8 5h12v14H8L3 12zM11 9l5 6M16 9l-5 6',
    tab: 'M4 12h13M12 7l5 5-5 5M20 6v12',
    enter: 'M20 5v7a2 2 0 0 1-2 2H5M9 10l-4 4 4 4',
    clear: 'M3 12h4M17 12h4M12 3v4M12 17v4M8 8l8 8M16 8l-8 8',
    bellOff: 'M6 17h12l-1.5-2V11a4.5 4.5 0 0 0-7-3.7M6.8 8.7A4.5 4.5 0 0 0 6.5 11v4L5 17M10 20h4M4 4l16 16',
    pause: 'M8 5v14M16 5v14',
    check: 'M5 12.5l4.5 4.5L19 7',
    alert: 'M12 4l9 16H3zM12 10v4M12 17.5v.5',
    dot: 'M12 12m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0',
    pin: 'M9 3h6M12 3v7M12 10l-4 5h8l-4-5zM12 15v6',
    textSearch: 'M4 6h10M4 10h6M4 14h4M14.5 12.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM21 22l-3.2-3.2',
    mic: 'M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM6 11a6 6 0 0 0 12 0M12 17v4M9 21h6',
  };
  function icon(name, size) {
    var svgNS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', String(size || 18));
    svg.setAttribute('height', String(size || 18));
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.style.cssText = 'display:block;flex-shrink:0;';
    var path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', ICONS[name]);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.75');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    return svg;
  }

  /* The sheet's own stylesheet. Inline cssText cannot express :active,
   * :hover, :focus-visible or reduced-motion, and those are where a control
   * stops looking like a painted rectangle and starts feeling like a button.
   * The visual vocabulary is small on purpose -- every control is a tonal
   * shape on the sheet, no 1px borders, one accent, one radius rule: 12px for every control, 16px for the well. */
  function injectStyle() {
    if (document.getElementById('ctb-console-style')) return;
    var css = [
      '#ctb-console .con-btn{display:inline-flex;align-items:center;justify-content:center;',
      'gap:6px;border:0;border-radius:12px;background:var(--con-btn);color:var(--con-text);',
      'font:600 13px/1 ui-sans-serif,system-ui,sans-serif;min-height:44px;padding:0 14px;',
      'cursor:pointer;touch-action:manipulation;flex-shrink:0;-webkit-tap-highlight-color:transparent;',
      'transition:transform .12s ease,background-color .15s ease;user-select:none;-webkit-user-select:none}',
      '#ctb-console .con-btn:active{transform:scale(.95)}',
      '#ctb-console .con-btn:focus-visible{outline:2px solid var(--con-accent);outline-offset:2px}',
      '@media(hover:hover){#ctb-console .con-btn:hover{background:var(--con-btn-hover)}}',
      '#ctb-console .con-btn--icon{width:44px;padding:0}',
      /* Keys are rounded squares, not pills: a pill row reads as a calculator,
       * a row of soft squares reads as keys. One radius for every control. */
      "#ctb-console .con-btn--key{min-width:44px;padding:0 13px;",
      "font:600 14px/1 ui-monospace,'SF Mono',Menlo,monospace}",
      /* The tinted variants restate their ground under :hover: the neutral
       * hover rule above outranks a bare variant class, and 중단 going grey
       * under the pointer is the kind of thing that gets noticed. */
      '#ctb-console .con-btn--primary,#ctb-console .con-btn--primary:hover{background:var(--con-accent);color:#fff;padding:0 18px}',
      '@media(hover:hover){#ctb-console .con-btn--primary:hover{background:var(--con-accent-hover)}}',
      '#ctb-console .con-btn--danger,#ctb-console .con-btn--danger:hover{background:var(--con-stop);color:var(--con-stop-text)}',
      '#ctb-console .con-btn--ok,#ctb-console .con-btn--ok:hover{background:var(--con-copybar);color:var(--con-ok)}',
      '#ctb-console .con-chip{display:flex;align-items:center;gap:6px;flex:0 0 auto;max-width:45%;',
      'scroll-snap-align:start;border:0;border-radius:999px;padding:7px 12px;cursor:pointer;',
      'text-align:left;overflow:hidden;touch-action:manipulation;-webkit-tap-highlight-color:transparent;',
      'background:transparent;color:var(--con-muted);font:500 12px/1 ui-sans-serif,system-ui,sans-serif;',
      'user-select:none;-webkit-user-select:none;min-height:34px;',
      'transition:background-color .15s ease,color .15s ease}',
      /* The active chip is the raised one on the rail -- a white key on the
       * tray -- rather than a tinted one; tint is kept for the accent. */
      '#ctb-console .con-chip[aria-current="true"]{background:var(--con-btn);color:var(--con-text);font-weight:700;',
      'box-shadow:0 1px 2px rgba(16,24,40,0.10)}',
      /* A pinned session wears its quadrant's hue -- the same hue the grid
       * tints its card with -- as a ring and a wash, so importance can be
       * read on the rail. The active chip keeps its raised white key and
       * only the ring stays. Hues match getQuadConfig() in index.html. */
      '#ctb-console .con-chip[data-quad="Q1"]{box-shadow:inset 0 0 0 1px rgba(251,113,133,0.35);background:rgba(220,100,90,0.06)}',
      '#ctb-console .con-chip[data-quad="Q2"]{box-shadow:inset 0 0 0 1px rgba(240,165,0,0.35);background:rgba(217,119,6,0.06)}',
      '#ctb-console .con-chip[data-quad="Q3"]{box-shadow:inset 0 0 0 1px rgba(96,165,250,0.35);background:rgba(37,99,235,0.05)}',
      '#ctb-console .con-chip[data-quad="Q4"]{box-shadow:inset 0 0 0 1px rgba(139,133,160,0.3);background:rgba(107,114,128,0.05)}',
      '#ctb-console .con-chip[aria-current="true"][data-quad="Q1"]{background:var(--con-btn);box-shadow:inset 0 0 0 1.5px rgba(251,113,133,0.5),0 1px 2px rgba(16,24,40,0.10)}',
      '#ctb-console .con-chip[aria-current="true"][data-quad="Q2"]{background:var(--con-btn);box-shadow:inset 0 0 0 1.5px rgba(240,165,0,0.5),0 1px 2px rgba(16,24,40,0.10)}',
      '#ctb-console .con-chip[aria-current="true"][data-quad="Q3"]{background:var(--con-btn);box-shadow:inset 0 0 0 1.5px rgba(96,165,250,0.5),0 1px 2px rgba(16,24,40,0.10)}',
      '#ctb-console .con-chip[aria-current="true"][data-quad="Q4"]{background:var(--con-btn);box-shadow:inset 0 0 0 1.5px rgba(139,133,160,0.45),0 1px 2px rgba(16,24,40,0.10)}',
      /* The importance key wears the same four hues, but louder than a chip
       * does: this one has to answer "which quadrant is this session in"
       * before it is pressed, so the glyph itself takes the colour and the
       * ring closes around it. No quadrant -- which is also "no completion
       * alert" -- stays grey and quiet.
       *
       * Foreground, wash and ring are all mixed from one per-theme variable:
       * the tints that carry on black are pale enough on paper to leave 13px
       * text at about 2:1. The hover wash has to be restated here, because
       * these rules tie .con-btn:hover on specificity and come later -- a
       * pinned key that did not answer the pointer read as disabled. */
      "#ctb-console .con-quad[data-quad='Q1'],#ctb-console .con-quad[data-quad='Q2'],"
        + "#ctb-console .con-quad[data-quad='Q3'],#ctb-console .con-quad[data-quad='Q4']"
        + '{color:var(--q);background:color-mix(in srgb,var(--q) 12%,var(--con-btn));'
        + 'box-shadow:inset 0 0 0 1.5px color-mix(in srgb,var(--q) 55%,transparent)}',
      "#ctb-console .con-quad[data-quad='Q1']{--q:var(--con-q1)}",
      "#ctb-console .con-quad[data-quad='Q2']{--q:var(--con-q2)}",
      "#ctb-console .con-quad[data-quad='Q3']{--q:var(--con-q3)}",
      "#ctb-console .con-quad[data-quad='Q4']{--q:var(--con-q4)}",
      '@media(hover:hover){#ctb-console .con-quad[data-quad]:not([data-quad=""]):hover'
        + '{background:color-mix(in srgb,var(--q) 24%,var(--con-btn))}}',
      '#ctb-console .con-quad[data-quad=""]{color:var(--con-muted);opacity:0.6}',
      /* The number is the second channel: which quadrant must not be a
       * question only colour can answer. Blank when there is no quadrant --
       * the bell-off badge beside it says why. */
      '#ctb-console .con-quad-num{font:700 10px/1 ui-sans-serif,system-ui,sans-serif;'
        + 'margin-left:1px;align-self:flex-start;margin-top:11px}',
      '#ctb-console .con-rail{background:var(--con-tray);border-radius:14px;padding:4px}',
      /* The mic while it listens: a red key, pulsing, so a held finger can
       * see the recording is on without reading the status line. */
      '@keyframes con-listen{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.45)}50%{box-shadow:0 0 0 6px rgba(239,68,68,0)}}',
      '#ctb-console .con-mic[data-listening]{background:#ef4444!important;color:#fff!important;animation:con-listen 1.2s ease-out infinite}',
      '@media(prefers-reduced-motion:reduce){#ctb-console .con-mic[data-listening]{animation:none}}',
      '#ctb-console .con-mic[data-level]{animation:none}',
      /* While the clip is out for transcription the key turns amber and its
       * icon spins slowly; the key is the only indicator, by request. */
      '@keyframes con-spin{to{transform:rotate(360deg)}}',
      '#ctb-console .con-mic[data-transcribing]{background:#f59e0b!important;color:#fff!important}',
      '#ctb-console .con-mic[data-transcribing] svg{animation:con-spin 1.4s linear infinite}',
      '@media(prefers-reduced-motion:reduce){#ctb-console .con-mic[data-transcribing] svg{animation:none}}',
      '#ctb-console .con-tray{background:var(--con-tray);border-radius:16px;padding:8px}',
      /* A phone screen is short, and the pane is what it is for. On narrow
       * screens the keys shrink to the size of the system keyboard's own
       * (38px) and pack nine to a row, so the pad is two rows -- about half
       * the height of the desktop layout -- and the pane keeps the rest. */
      '@media(max-width:480px){',
      '#ctb-console .con-tray{padding:6px;gap:5px!important;border-radius:14px}',
      "#ctb-console .con-btn--key{min-width:36px;min-height:38px;padding:0 9px;font-size:13px;border-radius:10px}",
      '#ctb-console .con-tray .con-btn{min-height:38px;border-radius:10px}',
      '#ctb-console .con-tray .con-btn svg{width:16px;height:16px}',
      /* Icon only on a phone: with the word it was a third row by itself. */
      '#ctb-console .con-key-label{display:none}',
      /* The input row: two 40px keys, the rest is the box. */
      '#ctb-console .con-mic,#ctb-console .con-send{min-width:40px!important;width:40px;padding:0!important;justify-content:center}',
      '}',
      /* A key that changed the input box: the box line pulses once so the
       * eye lands on what the key did, not only on the status text. */
      '@keyframes con-flash{0%{background:rgba(16,185,129,0.35)}100%{background:transparent}}',
      '#ctb-console .con-flash{animation:con-flash 1.2s ease-out}',
      '@media(prefers-reduced-motion:reduce){#ctb-console .con-flash{animation:none}}',
      /* State, told the same way on both surfaces -- the rail at the top of
       * the console and the search palette over it. The board says a session
       * is alive by breathing its dot; these do the same, and both say it in
       * words beside the dot, because colour alone is not a state anyone can
       * read out loud. The dot is decoration to a screen reader: the words
       * are in the row's accessible name. */
      '@keyframes ctb-breathe{0%,100%{transform:scale(1);opacity:.55}50%{transform:scale(1.35);opacity:1}}',
      '.ctb-sdot{width:7px;height:7px;border-radius:50%;flex-shrink:0;background:#6b7280}',
      '.ctb-sdot[data-live]{animation:ctb-breathe 2.8s cubic-bezier(.45,0,.55,1) infinite}',
      '@media(prefers-reduced-motion:reduce){.ctb-sdot[data-live]{animation:none}}',
      /* A lane of its own, wide enough for the longest word (응답없음,
       * 입력대기, 상태미상 -- four characters). Without the reserved width a
       * session going from 유휴 to 응답없음 widens its chip and slides every
       * chip after it sideways, which under a finger already on its way
       * down means pressing the wrong session. */
      /* The one-shot cue. The breathing dot says a session is alive; this
       * says it just became something you have to do something about -- the
       * gap the steady signals leave, which is that you have to be looking
       * to notice a change. An inset ring rather than a background wash: the
       * palette paints its selection with the background, and a cue that
       * fights the selection is a cue that hides where you are. */
      '@keyframes ctb-notice{0%{box-shadow:inset 0 0 0 2px var(--ctb-notice)}'
        + '70%{box-shadow:inset 0 0 0 2px var(--ctb-notice)}'
        + '100%{box-shadow:inset 0 0 0 2px transparent}}',
      '.ctb-notice{animation:ctb-notice 1.2s ease-out}',
      '@media(prefers-reduced-motion:reduce){.ctb-notice{animation:none}}',
      '.ctb-slabel{font-size:10px;font-weight:600;flex-shrink:0;letter-spacing:-.01em;'
        + 'min-width:4em;text-align:right;white-space:nowrap}',
      '#ctb-console .con-chip:active{transform:scale(.97)}',
      '#ctb-console .con-chip:focus-visible{outline:2px solid var(--con-accent);outline-offset:1px}',
      '#ctb-console .con-well{border:0;border-radius:16px;box-shadow:var(--con-well-edge)}',
      '#ctb-console .con-input{border:0;border-radius:14px;background:var(--con-well);color:var(--con-text);',
      'box-shadow:var(--con-well-edge);transition:box-shadow .15s ease;outline:none}',
      '#ctb-console .con-input:focus{box-shadow:var(--con-well-edge),0 0 0 2px var(--con-accent)}',
      '#ctb-console .con-input::placeholder{color:var(--con-dim)}',
      '@media(prefers-reduced-motion:reduce){#ctb-console .con-btn,#ctb-console .con-chip,#ctb-console .con-input{transition:none}',
      '#ctb-console .con-btn:active,#ctb-console .con-chip:active{transform:none}}',
    ].join('');
    var style = document.createElement('style');
    style.id = 'ctb-console-style';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function build() {
    if (el.root) return;
    injectStyle();

    var root = document.createElement('div');
    root.id = 'ctb-console';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', '세션 콘솔');
    root.style.cssText = [
      /* Full-bleed, not a peeking bottom sheet: the band of dashboard that
       * used to show above it served nothing -- no backdrop, no tap-to-close --
       * and a tap there hit the card underneath and opened a second console.
       * Session switching now lives in the strip inside the sheet instead. */
      'position:fixed', 'left:0', 'right:0', 'top:0', 'bottom:0', 'z-index:60',
      'display:none', 'flex-direction:column',
      /* Standalone PWA: top:0 is under the status bar / notch, so inset. */
      'padding:calc(10px + env(safe-area-inset-top)) 12px' +
        ' calc(14px + env(safe-area-inset-bottom))',
      'background:var(--con-sheet-img,none) center/768px repeat, var(--con-sheet)', 'color:var(--con-text)',
      'font-family:ui-sans-serif,system-ui,sans-serif',
      /* The sheet carries its own scrollbar colours, from its own palette:
       * the page's variables are tuned to the board. Custom properties
       * cascade, so this covers the tail and anything else here that scrolls. */
      '--scroll-track:var(--con-scroll-track)',
      '--scroll-thumb:var(--con-scroll-thumb)',
      '--scroll-thumb-hover:var(--con-scroll-thumb-hover)',
      'color-scheme:var(--con-scheme)',
    ].join(';');

    /* Switcher strip: the sheet used to open with dead space above it, and
     * changing session meant closing, finding the card, tapping again. Chips
     * are sized to their names and the rail scrolls horizontally, in the grid's
     * own order (recency/state), flat — worktrees are not grouped here.
     * makePannable() adds the wheel and drag affordances a mouse needs. */
    var strip = document.createElement('div');
    strip.className = 'con-rail';
    strip.style.cssText = [
      'display:flex', 'gap:4px', 'flex-shrink:0', 'margin-bottom:10px',
      'overflow-x:auto', 'overflow-y:hidden', 'overscroll-behavior:contain',
      'scroll-snap-type:x proximity', '-webkit-overflow-scrolling:touch',
      'scrollbar-width:none',
    ].join(';');
    makePannable(strip);

    var header = document.createElement('div');
    header.style.cssText =
      'display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-shrink:0;';

    var title = document.createElement('div');
    title.style.cssText =
      'flex:1;min-width:0;font-size:16px;font-weight:700;letter-spacing:-0.01em;' +
      'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';

    /* Why no notification came, where the question is asked. "핀 고정 아님" is
     * the one reason the page cannot show: the alerts switch reports the
     * browser's side, but completion pushes go out for pinned sessions only,
     * so an unpinned session finishing in silence looks exactly like a push
     * that failed. */
    var silent = document.createElement('span');
    silent.appendChild(icon('bellOff', 16));
    silent.title = '\uc774 \uc138\uc158\uc740 \ud540 \uace0\uc815\uc774 \uc544\ub2c8\ub77c '
      + '\uc644\ub8cc \uc54c\ub9bc\uc774 \uac00\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.\n'
      + '\ubcf4\ub4dc\uc5d0\uc11c \uce74\ub4dc\ub97c \uc0c1\ub2e8 \uc0ac\ubd84\uba74\uc73c\ub85c '
      + '\ub04c\uc5b4\ub2e4 \ub193\uc73c\uba74 \uc54c\ub9bc\uc774 \uc635\ub2c8\ub2e4.';
    silent.setAttribute('aria-label', '\ud540 \uace0\uc815\uc774 \uc544\ub2c8\ub77c \uc54c\ub9bc \uc5c6\uc74c');
    silent.style.cssText =
      'display:none;font-size:12px;flex-shrink:0;cursor:help;opacity:0.75;';

    /* The status line lives between the pane and the key pad, not in the
     * header: the eyes are on the box and the keys when a key is pressed,
     * and a line at the top of the sheet was out of view on a phone and out
     * of focus on a desk. It leads with a glyph so the outcome reads before
     * the words do. */
    var status = document.createElement('div');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    /* Always laid out, shown or not: when this line appeared it took its
     * height from the pane above, the pane's scrollTop stayed put, and the
     * poll's "is the reader at the bottom" check said no from then on -- the
     * console froze on the first status message. Reserving the space keeps
     * the pane's geometry constant. */
    status.style.cssText = 'display:flex;visibility:hidden;align-items:center;gap:6px;min-height:22px;' +
      'margin:-4px 2px 8px;font-size:12px;font-weight:600;color:var(--con-muted);flex-shrink:0;';

    /* The palette had one entrance and it was a chord. On a phone there is no
     * Ctrl and no Cmd unless a keyboard is attached, so with seventy sessions
     * the only way to reach one was to scroll the rail until it appeared. */
    var find = document.createElement('button');
    find.type = 'button';
    find.appendChild(icon('search'));
    find.title = '\uc138\uc158 \uac80\uc0c9 (Ctrl/Cmd+F)';
    find.setAttribute('aria-label', '\uc138\uc158 \uac80\uc0c9 \uc5f4\uae30');
    styleBtn(find, 'icon');
    find.addEventListener('click', function () {
      if (searchOpen()) return;
      hideHints();
      fetchOrder();
      openSearch();
    });

    /* Importance and notifications, where the session is being watched.
     *
     * The quadrant a session sits in is set by dragging its card, and a
     * completion push only goes out for a pinned session -- both live on the
     * board, which the sheet covers. Deciding "this one matters, tell me when
     * it stops" from in here is the same decision, made at the moment it
     * actually comes up. */
    var quad = document.createElement('button');
    quad.type = 'button';
    quad.appendChild(icon('pin'));
    quad.setAttribute('aria-haspopup', 'menu');
    quad.setAttribute('aria-expanded', 'false');
    styleBtn(quad, 'icon');
    quad.className += ' con-quad';
    var quadNum = document.createElement('span');
    quadNum.className = 'con-quad-num';
    quadNum.setAttribute('aria-hidden', 'true');
    quad.appendChild(quadNum);
    /* Grey until the first paint says otherwise: an attribute-less button
     * would take the plain key colour, which is Q4's. */
    quad.setAttribute('data-quad', '');
    quad.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleQuadMenu();
    });

    var findText = document.createElement('button');
    findText.type = 'button';
    findText.appendChild(icon('textSearch'));
    findText.title = '\ucd9c\ub825 \ub0b4\uc6a9 \uac80\uc0c9 (Ctrl/Cmd+Shift+F)';
    findText.setAttribute('aria-label', '\ucd9c\ub825 \ub0b4\uc6a9 \uac80\uc0c9');
    styleBtn(findText, 'icon');
    findText.addEventListener('click', function () { openFind(); });

    var copy = document.createElement('button');
    copy.type = 'button';
    copy.appendChild(icon('copy'));
    copy.title = '\ud654\uba74 \ub0b4\uc6a9 \ubcf5\uc0ac';
    copy.setAttribute('aria-label', '\ud654\uba74 \ub0b4\uc6a9 \ubcf5\uc0ac');
    styleBtn(copy, 'icon');
    copy.addEventListener('click', copyTail);

    var close = document.createElement('button');
    close.type = 'button';
    close.appendChild(icon('close'));
    close.setAttribute('aria-label', '콘솔 닫기');
    styleBtn(close, 'icon');
    close.addEventListener('click', hide);

    header.appendChild(title);
    header.appendChild(silent);
    header.appendChild(quad);
    header.appendChild(find);
    header.appendChild(findText);
    header.appendChild(copy);
    header.appendChild(close);

    var tail = document.createElement('pre');
    tail.setAttribute('aria-live', 'polite');
    tail.className = 'con-well';
    tail.style.cssText = [
      'flex:1', 'min-height:120px', 'overflow:auto', 'margin:0 0 10px',
      /* Without this, a scroll that reaches either end of the tail carries on
       * into the dashboard behind the sheet: the pane stops moving and the
       * grid underneath starts, which reads as the console having died. The
       * page behind is fixed while the console is open (lockPage) and this
       * stops the chain before it gets there. */
      'overscroll-behavior:contain',
      'padding:12px 12px', 'background:var(--con-well)',
      /* The system's own monospace first: SF Mono on an iPhone is cut for
       * that screen and reads at 12px where a web font at 11px went thin
       * and pale, and if the web font never arrives the fallback was Courier,
       * the thinnest face on the device. JetBrains Mono stays for platforms
       * whose ui-monospace is poor. */
      "font-family:ui-monospace,'SF Mono',Menlo,'JetBrains Mono',Consolas,monospace",
      /* A phone is read at arm's length with a thumb on the glass; 12px on a
       * desk is 13px there. Touch is the tell, not the width. */
      'font-size:' + (window.matchMedia && window.matchMedia('(pointer: coarse)').matches ? '13px' : '12px'),
      'font-weight:var(--con-tail-weight)',
      'line-height:1.5', 'white-space:pre-wrap', 'word-break:break-word',
      '-webkit-overflow-scrolling:touch',
      '-webkit-user-select:text', 'user-select:text',
    ].join(';');
    /* The gesture is not guessable from a pane that looks like plain text, and
     * it is the whole copy story now. */
    tail.title = '\ud0ed\ud558\uba74 \uac31\uc2e0\uc774 \uba48\ucda5\ub2c8\ub2e4 \u2014 \uadf8 \uc0c1\ud0dc\ub85c \ub4dc\ub798\uadf8\ud574 \ubcf5\uc0ac\ud558\uc138\uc694. \ub2e4\uc2dc \ud0ed\ud558\uba74 \uc7ac\uac1c';

    /* Keys first: answering a permission prompt is the thing you most often
     * need in a hurry, and send_prompt refuses while one is pending. */
    var keys = document.createElement('div');
    keys.className = 'con-tray';
    keys.style.cssText =
      'display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;flex-shrink:0;';
    [
      /* Answering, then moving, then editing. The keys are grouped by what you
       * are doing with them rather than by how the pane reads them, and the
       * destructive end of the row is the far end: ⌫ ⇥ ↵ esc sit past the
       * arrows, and 입력 지우기 past those. */
      /* The fourth field is what survives a narrow screen: answering a prompt
       * and stopping the work outrank moving a cursor, which outranks the
       * editing keys the on-screen keyboard can do anyway. */
      ['y', 'y', '예', 9], ['n', 'n', '아니오', 9],
      ['1', '1', '1번', 8], ['2', '2', '2번', 8], ['3', '3', '3번', 7],
      ['4', '4', '4번', 3], ['5', '5', '5번', 2],
      [icon('up'), 'Up', '위', 6], [icon('down'), 'Down', '아래', 6],
      [icon('left'), 'Left', '왼쪽', 4], [icon('right'), 'Right', '오른쪽', 4],
      [icon('backspace'), 'BSpace', '한 글자 지우기', 3], [icon('tab'), 'Tab', 'Tab', 5],
      [icon('enter'), 'Enter', 'Enter', 8], ['esc', 'Escape', 'Escape — 진행 중인 작업 중단 · 메뉴 닫기', 9],
    ].forEach(function (spec) {
      var b = document.createElement('button');
      b.type = 'button';
      if (typeof spec[0] === 'string') b.textContent = spec[0];
      else b.appendChild(spec[0]);
      b.title = spec[2];
      b.setAttribute('aria-label', spec[2] + ' 키 전송');
      styleBtn(b, 'key');
      b.addEventListener('click', function () { sendKey(spec[1]); });
      b.setAttribute('data-prio', String(spec[3]));
      keys.appendChild(b);
    });

    /* Clearing what is half-typed in the PANE -- not in the box above, whose
     * own draft is cleared by sending it. Ctrl+U is a kill-line, so it takes
     * the whole input and leaves anything already running alone; Escape-Escape
     * rewinds the conversation and Escape interrupts the work, and neither of those
     * is what "I mistyped, start the line again" should cost. Ctrl+Y in the
     * session pastes it back if the finger was wrong. */
    var clearLine = document.createElement('button');
    clearLine.type = 'button';
    clearLine.appendChild(icon('clear', 16));
    var clearLabel = document.createElement('span');
    clearLabel.className = 'con-key-label';
    clearLabel.textContent = '입력 지우기';
    clearLine.appendChild(clearLabel);
    /* Names the key, not an outcome: Ctrl+U clears the input line in Claude
     * Code and in a readline shell, which is every pane this pad is aimed
     * at, but a pane running vim or less does its own thing with it. What
     * holds everywhere is the half worth promising -- it is an edit, not an
     * interrupt, so nothing that is running stops. */
    clearLine.title = 'Ctrl+U 전송 — 입력 줄 지우기 (진행 중 작업은 중단되지 않음) · 단축키 Ctrl+U';
    clearLine.setAttribute('aria-label', '세션 입력 지우기 키 전송');
    styleBtn(clearLine, '');
    clearLine.addEventListener('click', function () { sendKey('C-u'); });
    clearLine.setAttribute('data-prio', '4');
    keys.appendChild(clearLine);

    /* Escape stops the work but leaves the prompt behind in the transcript,
     * where it cannot be edited. This brings it back down into the box --
     * from the session's own input line when something is sitting there
     * unsent (and clears that line, so the text lives in one place), else
     * from the last request that was actually submitted. */
    var recall = document.createElement('button');
    recall.type = 'button';
    recall.appendChild(icon('copy', 16));
    var recallLabel = document.createElement('span');
    recallLabel.className = 'con-key-label';
    recallLabel.textContent = '\uac00\uc838\uc624\uae30';
    recall.appendChild(recallLabel);
    recall.title = '\ub9c8\uc9c0\ub9c9 \uc694\uccad\uc744 \uc544\ub798 \uc785\ub825\ucc3d\uc73c\ub85c \ubcf5\uc0ac \u2014 \uc138\uc158 \uc785\ub825\ucc3d\uc5d0 \uc548 \ubcf4\ub0b8 \uae00\uc774 \uc788\uc73c\uba74 \uadf8\uac83\uc744 \uc637\uae30\uace0 \ube44\uc6c1\ub2c8\ub2e4';
    recall.setAttribute('aria-label', '\ub9c8\uc9c0\ub9c9 \uc694\uccad \uac00\uc838\uc624\uae30');
    styleBtn(recall, '');
    recall.addEventListener('click', recallLast);
    recall.setAttribute('data-prio', '5');
    keys.appendChild(recall);

    /* Unfolds whatever did not fit. Never folded itself, and only shown when
     * something is behind it. */
    var more = document.createElement('button');
    more.type = 'button';
    more.textContent = '\u22ef';
    more.title = '\uac00\ub824\uc9c4 \ud0a4 \ubcf4\uae30';
    more.setAttribute('aria-label', '\uac00\ub824\uc9c4 \ud0a4 \ubcf4\uae30');
    more.setAttribute('aria-expanded', 'false');
    styleBtn(more, 'key');
    more.style.display = 'none';
    more.addEventListener('click', function () {
      keys.setAttribute('data-expanded', keys.hasAttribute('data-expanded') ? '' : '1');
      if (!keys.getAttribute('data-expanded')) keys.removeAttribute('data-expanded');
      fitKeys();
    });
    keys.appendChild(more);

    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:8px;align-items:flex-end;flex-shrink:0;';

    var input = document.createElement('textarea');
    input.rows = 2;
    input.placeholder = '지시 입력 (Enter 전송 · Shift+Enter 줄바꿈)';
    input.setAttribute('aria-label', '프롬프트 입력');
    input.className = 'con-input';
    input.style.cssText = [
      'flex:1', 'resize:none', 'padding:11px 13px',
      /* 16px, and not a pixel less. Below that, iOS zooms the page in when the
       * field takes focus -- and it does not zoom back out when focus leaves,
       * so every tap on the box left the user pinching to get the screen back.
       * The comment this replaces assumed a no-zoom viewport meta; there is
       * none (index.html sends width=device-width, initial-scale=1 only), and
       * Safari ignores user-scalable=no anyway. */
      'font-size:16px',
      'line-height:1.4', 'font-family:inherit',
    ].join(';');
    /* Sending is decided on the line break, not on the key.
     *
     * A soft-keyboard IME (Hangul, Kana, Pinyin) does not report the return
     * that commits a composition as Enter: it arrives with isComposing set, or
     * as keyCode 229, or under no name at all. A handler watching for
     * key === 'Enter' misses it, the browser inserts a newline instead, and the
     * prompt sits in the box until the user presses return again -- which is
     * exactly what a phone reported. Whatever the keyboard called it, the
     * browser still tells us it is about to break the line, and a line break
     * without Shift is the send gesture.
     *
     * beforeinput carries no modifier state, so the keydown records it. */
    /* Armed by an Enter keydown ONLY -- never by an ordinary keystroke.
     *
     * It used to record e.shiftKey on every keydown, cleared by the following
     * beforeinput or keyup. When either was missed (iOS coalesces them; an IME
     * swallows them) the stale 'true' survived to the next line break, which
     * then read as Shift+Enter: a newline appeared and nothing was sent. Korean
     * made that routine rather than rare -- ㄲㄸㅃㅆㅉ and ㅒㅖ are all Shift
     * combinations, so typing "했어" arms the flag mid-word.
     *
     * Narrowed this way, an ordinary keystroke cannot arm it at all. A soft
     * keyboard that reports no Enter keydown leaves it false, so the line break
     * sends -- which is the intent: Shift+Enter is a hardware-keyboard gesture. */
    var shiftHeld = false;
    input.addEventListener('keydown', function (e) {
      var imeIsHandlingIt = e.isComposing || e.keyCode === 229;
      /* Tab goes to the session, not to the next widget.
       *
       * Accepting a completion and pressing Enter is one gesture, and it was
       * two trips to the ⇥ button with a click in between -- which also cost
       * the caret.
       *
       * Not while an IME is composing: a Hangul or Japanese keyboard uses Tab
       * to commit or cycle a candidate, so taking it there would leave the
       * half-typed word uncommitted in the box AND drop a stray Tab into a
       * live pane. Shift+Tab is not taken here: the document-level handler
       * sends it as a Tab too, from the box or anywhere else in the sheet. */
      if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey
          && !imeIsHandlingIt) {
        e.preventDefault();
        sendKey('Tab');
        return;
      }
      /* Not `|| keyCode === 229`: during Hangul composition every key reports
       * 229, so arming on it would bring the stale flag straight back. */
      if (e.key === 'Enter') shiftHeld = e.shiftKey;
      if (e.key === 'Enter' && !e.shiftKey && !imeIsHandlingIt) {
        e.preventDefault();
        /* The press that recovered the console put the caret in this box.
         * Held down, the OS repeats it here -- and the second repeat would
         * send whatever draft was sitting in the box, on a key the reader
         * pressed to get their bearings. The physical press ends at keyup;
         * until then this box has not been typed into. */
        if (recoveredEnter) return;
        submit();
      }
    });
    input.addEventListener('keyup', function (e) {
      if (e.key === 'Enter' || e.key === 'Shift') shiftHeld = e.shiftKey;
      if (e.key === 'Enter') recoveredEnter = false;
    });
    input.addEventListener('beforeinput', function (e) {
      var breaksLine = e.inputType === 'insertLineBreak'
        || (e.inputType === 'insertText' && e.data === '\n');
      /* Consume the flag: shift state from an earlier key must not bleed into
       * later events when iOS skips the intervening keydown events. */
      var held = shiftHeld;
      shiftHeld = false;
      if (!breaksLine || held) return;
      e.preventDefault();
      submit();
    });
    input.addEventListener('input', function () {
      if (!state.session) return;
      state.drafts[state.session] = input.value;
      saveDrafts();
    });
    // Keep the input visible when the on-screen keyboard opens.
    input.addEventListener('focus', function () {
      setTimeout(function () {
        input.scrollIntoView({ block: 'nearest' });
      }, 250);
    });

    var send = document.createElement('button');
    send.type = 'button';
    /* The word on a desktop, the arrow alone on a phone: with the mic beside
     * it the row was three controls wide and the box had shrunk to a slot.
     * Both keys are 40px on a phone, so the box keeps most of its width. */
    send.className = 'con-send';
    send.appendChild(icon('enter', 16));
    var sendLabel = document.createElement('span');
    sendLabel.className = 'con-key-label';
    sendLabel.textContent = '전송';
    send.appendChild(sendLabel);
    send.setAttribute('aria-label', '프롬프트 전송');
    send.title = '전송 (Enter)';
    styleBtn(send, 'primary');
    send.style.display = 'inline-flex';
    send.style.alignItems = 'center';
    send.style.gap = '6px';
    send.addEventListener('click', submit);

    /* Push-to-talk. Hidden until /api/stt/config says there is a key, and
     * never in the VSCode webview, whose proxy forwards only GET. What comes
     * back is put into the box as a draft; Enter is still the user's. */
    var mic = document.createElement('button');
    mic.type = 'button';
    mic.appendChild(icon('mic', 18));
    mic.title = '누르고 말하기 · 짧게 탭하면 녹음 시작/정지 · 결과는 입력창에 초안으로만';
    mic.setAttribute('aria-label', '음성 입력');
    styleBtn(mic, '');
    mic.classList.add('con-mic');   /* after styleBtn -- it rewrites className */
    mic.style.display = 'none';
    mic.style.minWidth = '44px';
    mic.style.touchAction = 'manipulation';
    bindMic(mic);

    row.appendChild(input);
    row.appendChild(mic);
    row.appendChild(send);


    /* The pause a selection causes was invisible: the tail simply stopped
     * growing, which reads as a dead console rather than a held one. The badge
     * sits over the tail, where the eye already is -- the bar's own
     * "(갱신 일시정지)" text is below the fold of attention. */
    var tailWrap = document.createElement('div');
    tailWrap.style.cssText =
      'position:relative;display:flex;flex-direction:column;flex:1;min-height:0;';

    var frozen = document.createElement('div');
    frozen.appendChild(icon('pause', 12));
    frozen.appendChild(document.createTextNode('\uac31\uc2e0 \uc815\uc9c0\ub428'));
    frozen.style.cssText = [
      'display:none', 'position:absolute', 'top:6px', 'right:10px',
      'align-items:center', 'gap:4px',
      'padding:3px 9px', 'border-radius:99px', 'pointer-events:none',
      'font-size:10px', 'font-weight:700', 'letter-spacing:0.02em',
      'background:rgba(245,158,11,0.16)', 'color:var(--con-warn)',
      'border:1px solid rgba(245,158,11,0.5)',
      'backdrop-filter:blur(4px)', '-webkit-backdrop-filter:blur(4px)',
    ].join(';');

    /* Both overlay the pane rather than sitting above it: a row that appears
     * and disappears changes the pane's height, and the poll reads that height
     * to decide whether the reader is at the bottom -- the console froze on
     * its own status line once already for exactly that reason. */
    var endPill = document.createElement('button');
    endPill.type = 'button';
    endPill.appendChild(icon('down', 14));
    endPill.appendChild(document.createTextNode('\ub05d\uc73c\ub85c'));
    endPill.setAttribute('aria-label', '\ub9e8 \uc544\ub798\ub85c \uac00\uae30');
    endPill.style.cssText = [
      'display:none', 'position:absolute', 'left:50%', 'bottom:14px',
      'transform:translateX(-50%)', 'z-index:3',
      'align-items:center', 'gap:5px', 'min-height:34px', 'padding:0 14px',
      'border:0', 'border-radius:99px', 'cursor:pointer',
      'font:600 12px/1 ui-sans-serif,system-ui,sans-serif',
      'background:var(--con-accent,rgba(129,140,248,0.92))', 'color:#fff',
      'box-shadow:0 6px 18px rgba(16,24,40,0.35)',
    ].join(';');
    endPill.addEventListener('click', function (e) {
      e.stopPropagation();
      resumeLive();
    });

    /* The other direction. Going back means going back to a REQUEST: the turn
     * boundary is where the information is -- a conclusion, and the ask that
     * was built on it -- and it is the only landmark in a pane of output that
     * a reader can name. Scrolling by pages to find one is what this replaces.
     *
     * Right, not centre: the frozen badge is top-right and the find bar takes
     * the full width of the top, so centre would have collided with both. */
    var prevPill = document.createElement('button');
    prevPill.type = 'button';
    prevPill.appendChild(icon('up', 14));
    prevPill.appendChild(document.createTextNode('\uc774\uc804 \uc694\uccad'));
    prevPill.setAttribute('aria-label', '\uc774\uc804 \uc694\uccad\uc73c\ub85c \uac00\uae30');
    prevPill.style.cssText = [
      'display:none', 'position:absolute', 'left:50%', 'top:14px',
      'transform:translateX(-50%)', 'z-index:3',
      'align-items:center', 'gap:5px', 'min-height:34px', 'padding:0 14px',
      'border:0', 'border-radius:99px', 'cursor:pointer',
      'font:600 12px/1 ui-sans-serif,system-ui,sans-serif',
      'background:var(--con-accent,rgba(129,140,248,0.92))', 'color:#fff',
      'box-shadow:0 6px 18px rgba(16,24,40,0.35)',
    ].join(';');
    prevPill.addEventListener('click', function (e) {
      e.stopPropagation();
      gotoPrevPrompt();
    });

    tailWrap.appendChild(tail);
    tailWrap.appendChild(buildFindBar());
    tailWrap.appendChild(endPill);
    tailWrap.appendChild(prevPill);
    tailWrap.appendChild(frozen);

    root.appendChild(strip);
    sttInit();
    root.appendChild(header);
    root.appendChild(tailWrap);
    root.appendChild(status);
    root.appendChild(keys);
    root.appendChild(row);
    keepCaret(root, input);
    document.body.appendChild(root);

    el = { keys: keys, keysMore: more, endPill: endPill, prevPill: prevPill,
           root: root, strip: strip, title: title, status: status, tail: tail, mic: mic,
           frozen: frozen, input: input,
           send: send, silent: silent, quad: quad, quadNum: quadNum };

    /* The keyboard shrinks the visual viewport, and iOS does not always fire a
     * resize that brings it back when the keyboard closes without an edit --
     * the sheet then stays squeezed. Re-measure after the blur settles. */
    input.addEventListener('blur', function () {
      setTimeout(fitViewport, 300);
    });

    // The keyboard shrinks the visual viewport; sit on top of it, not under.
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', fitViewport);
      window.visualViewport.addEventListener('scroll', fitViewport);
    }
    /* Rotation and a split view change the pad's width, and with it how many
     * keys a row holds. The visual viewport moves for the keyboard too, which
     * does not, so this listens to the layout viewport only. */
    var fitPending = 0;
    window.addEventListener('resize', function () {
      if (!state.session || fitPending) return;
      fitPending = requestAnimationFrame(function () {
        fitPending = 0;
        fitKeys();
        updateEndPill();
      });
    });
    window.addEventListener('orientationchange', function () {
      if (state.session) setTimeout(fitKeys, 200);
    });
    /* Scrolling up is the request for more history -- no button to find, and it
     * matches how every chat scrollback behaves.
     *
     * A screenful early, not at the very top. Waiting for the top meant the
     * reader hit the wall first, and on a phone that is what the jump was: the
     * fling is pinned dead at scrollTop 0, then 400 lines land underneath it
     * and the leftover momentum, no longer clamped, carries the view hundreds
     * of lines up in one throw. Loading before the wall arrives means there is
     * never a wall to hit -- the content is simply already there.
     *
     * Only on the way up. The scroll to the bottom that opening a session
     * performs would otherwise trip this on a pane barely taller than the box,
     * and that is not a scroll the reader made. */
    var lastTop = 0;
    tail.addEventListener('scroll', function () {
      var top = tail.scrollTop;
      var goingUp = top < lastTop;
      lastTop = top;
      noteScrolling();
      /* Pinned to the bottom is a reader's intent, recorded when they scroll,
       * not a geometry the poll re-measures: the keyboard, a status line or
       * a rotation can move the numbers without the reader moving at all. */
      state.pinned = top + tail.clientHeight >= tail.scrollHeight - 48;
      updateEndPill();
      if (!goingUp || top > tail.clientHeight) return;
      /* Opening a session empties the tail to show '불러오는 중…', which drops
       * scrollTop to 0 and fires this -- a scroll the user never made, which
       * used to deepen the window before the first line had even arrived.
       * A tail with nothing to scroll cannot have been scrolled. */
      if (!state.lines || tail.scrollHeight <= tail.clientHeight + 8) return;
      growTail();
    });
    /* A finger on the glass counts as scrolling even between events: the
     * fling that follows a lift has not started firing yet. */
    /* touchend cannot be trusted to arrive: it is dispatched to the element
     * the touch STARTED on, and when a poll has since replaced that line the
     * event lands on a detached node and never reaches this listener. A
     * flag set on touchstart and cleared on touchend therefore stuck at
     * "finger down" forever, every poll skipped its repaint, and the console
     * froze until a session switch forced one. So the finger is a lease,
     * renewed by touchstart and every touchmove, expiring on its own. */
    tail.addEventListener('touchstart', function () { touchLease(); noteScrolling(); }, { passive: true });
    tail.addEventListener('touchmove', function () { touchLease(); noteScrolling(); }, { passive: true });
    tail.addEventListener('touchend', function () { touchUntil = 0; noteScrolling(); }, { passive: true });
    tail.addEventListener('touchcancel', function () { touchUntil = 0; noteScrolling(); }, { passive: true });
    /* Delegated: 'click' (not touchstart) so a scroll gesture never toggles. */
    tail.addEventListener('click', function (e) {
      /* A link click is a navigation, not a request to hold the pane: without
       * this the tap opened the page AND froze the tail behind it. */
      if (e.target.closest && e.target.closest('[data-tail-link]')) return;
      /* A drag that selected text is the copy itself, not a second tap: the
       * click that ends it must not thaw the pane the selection was made on.
       * The tap that follows -- which collapses that selection -- is the one
       * that lets go. */
      var sel = window.getSelection && window.getSelection();
      if (sel && !sel.isCollapsed) return;
      toggleHold();
    });

    /* Reading the pane should not cost you the caret. A click in the tail blurs
     * the prompt box, so picking a line to copy meant clicking back into the
     * box before the next word -- and mid-sentence that is the whole gesture
     * again.
     *
     * Focus is handed BACK on the way out rather than never let go: swallowing
     * the mousedown would keep the caret but kill the drag-select the tail is
     * made of. So the tap runs its course, and only then, if it left nothing
     * selected, does the box take focus again -- with its own caret intact,
     * since a textarea remembers where it was.
     *
     *   - a drag that selected text keeps the selection; focusing a textarea
     *     would collapse it, which is the opposite of what the drag asked for
     *   - a pointer that was not already in the box is not pulled into it
     *   - coarse pointers opt out entirely: there, focus means the on-screen
     *     keyboard, and a tap on the tail is how you get it out of the way to
     *     read. Restoring it would fight the reason for the tap. */
    var FINE_POINTER = !!(window.matchMedia
      && window.matchMedia('(pointer: fine)').matches);
    var hadCaret = false;
    tail.addEventListener('pointerdown', function () {
      hadCaret = document.activeElement === input;
    });
    tail.addEventListener('click', function () {
      if (!FINE_POINTER || !hadCaret) return;
      var sel = window.getSelection && window.getSelection();
      if (sel && !sel.isCollapsed) return;
      input.focus();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && state.session && !e.shiftKey) {
        var ns = window.ctbNewSession;
        if (ns && ns.isOpen && ns.isOpen()) return;   /* the sheet's Escape */
        if (findOpen()) closeFind(true);
        else if (searchOpen()) closeSearch();
        else if (state.held) unhold();
        else hide();
      }
    });
  }

  /* A button in the sheet never needs the caret: it does its work on click and
   * has nothing to type into. Letting it take focus meant that answering a
   * prompt with 'y', or sending, or copying a selection, dropped you out of the
   * box you were writing in -- the same cost the tail click used to have, on
   * the controls you press most. Delegated on the root so every button here is
   * covered, and inert unless the box actually has focus to lose. */
  function keepCaret(root, input) {
    root.addEventListener('mousedown', function (e) {
      if (document.activeElement !== input) return;
      var btn = e.target.closest && e.target.closest('button');
      if (btn) e.preventDefault();
    });
  }

  /* Every button is a .con-btn (see injectStyle); `kind` picks the variant,
   * `extra` is the inline layout the spot needs (margins, flex). */
  function styleBtn(b, kind, extra) {
    b.className = 'con-btn' + (kind ? ' con-btn--' + kind : '');
    if (extra) b.style.cssText = extra;
  }

  function fitViewport() {
    if (!el.root || !state.session) return;
    var vv = window.visualViewport;
    /* Only the textarea can raise a keyboard. With it unfocused there is no
     * overlap by definition, so ignore a visual viewport that iOS left short
     * after dismissing the keyboard -- otherwise the sheet stays squeezed. */
    var typing = document.activeElement === el.input
      || (findOpen() && document.activeElement === fnd.input);
    var overlap = typing && vv
      ? Math.max(0, window.innerHeight - (vv.height + vv.offsetTop))
      : 0;
    /* A hardware keyboard raises no soft keyboard but still takes a strip at
     * the foot -- iOS shows its own ↑ ↓ / 완료 accessory bar -- and to keep the
     * focused box clear of it Safari scrolls the *visual* viewport down inside
     * an unchanged layout viewport. position:fixed follows the layout
     * viewport, so the sheet did not come along: its head, the session strip,
     * slid off the top of the screen and the user lost the navigation.
     *
     * Following offsetTop pins the head to the top of what is actually
     * on screen; with the foot already lifted by the overlap the sheet is
     * exactly the visible rectangle. */
    var offsetTop = typing && vv ? Math.max(0, vv.offsetTop) : 0;
    /* Moving the foot up by the keyboard overlap is what shrinks the box, and
     * the tail (flex:1) gives back the space. */
    el.root.style.top = offsetTop + 'px';
    el.root.style.bottom = overlap + 'px';
    /* The pane just changed height without anyone scrolling, and the pill is
     * a statement about the distance to the bottom. */
    updateEndPill();
  }

  /* --- panning the switcher rail ----------------------------------------- */

  /* A mouse has no horizontal wheel and the rail has no visible scrollbar, so
   * on a desktop the sessions past the edge were unreachable without a
   * trackpad. Vertical wheel pans the rail, and dragging it works like grabbing
   * the row itself. Both are desktop affordances: touch already pans natively,
   * so pointer dragging is bound for mouse input only -- claiming touch here
   * would fight the native scroll it is imitating.
   */
  var DRAG_SLOP = 5;  /* px before a press counts as a drag rather than a tap */

  function makePannable(rail) {
    rail.addEventListener('wheel', function (e) {
      /* A trackpad's horizontal gesture already works; only translate when the
       * vertical axis dominates, and only while there is somewhere to go --
       * otherwise the sheet below can no longer be scrolled over the rail. */
      if (e.deltaX !== 0 || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      var max = rail.scrollWidth - rail.clientWidth;
      if (max <= 0) return;
      var next = Math.min(max, Math.max(0, rail.scrollLeft + e.deltaY));
      if (next === rail.scrollLeft) return;
      rail.scrollLeft = next;
      e.preventDefault();
    }, { passive: false });

    var origin = null;

    rail.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' || e.button !== 0) return;
      if (rail.scrollWidth <= rail.clientWidth) return;
      origin = { x: e.clientX, scroll: rail.scrollLeft, dragging: false };
    });

    rail.addEventListener('pointermove', function (e) {
      if (!origin) return;
      var moved = e.clientX - origin.x;
      if (!origin.dragging) {
        if (Math.abs(moved) < DRAG_SLOP) return;
        origin.dragging = true;
        /* Snap fights a drag: the rail jumps to the nearest chip mid-gesture. */
        rail.style.scrollSnapType = 'none';
        rail.style.cursor = 'grabbing';
        rail.style.userSelect = 'none';
        /* Keep receiving moves when the cursor leaves the rail. */
        if (rail.setPointerCapture) rail.setPointerCapture(e.pointerId);
      }
      rail.scrollLeft = origin.scroll - moved;
      e.preventDefault();
    });

    function endDrag(e) {
      if (!origin) return;
      var dragged = origin.dragging;
      origin = null;
      rail.style.scrollSnapType = 'x proximity';
      rail.style.cursor = '';
      rail.style.userSelect = '';
      if (e && e.pointerId != null && rail.releasePointerCapture) {
        try { rail.releasePointerCapture(e.pointerId); } catch (err) { /* already gone */ }
      }
      /* A drag that ends over a chip must not also switch session. The click
       * fires after pointerup, so swallow exactly that one in the capture
       * phase, before the document-level switch handler sees it. */
      if (dragged) {
        var swallow = function (ev) {
          ev.stopPropagation();
          ev.preventDefault();
          done();
        };
        var done = function () {
          window.removeEventListener('click', swallow, true);
          clearTimeout(timer);
        };
        /* A drag that ends off a clickable target produces no click at all.
         * Without the timer that listener would survive to eat an unrelated
         * click somewhere else in the sheet. */
        var timer = setTimeout(done, 300);
        window.addEventListener('click', swallow, true);
      }
    }

    rail.addEventListener('pointerup', endDrag);
    rail.addEventListener('pointercancel', endDrag);
  }

  /* --- switcher strip ---------------------------------------------------- */

  /* Mirrors QUAD_LABELS in index.html. */
  var QUAD_LABELS = { Q1: '긴급+중요', Q2: '중요', Q3: '긴급', Q4: '일반' };

  var STATE_DOT = {
    working: '#34d399', stuck_after_agent: '#f97316', waiting: '#fbbf24',
    error: '#ef4444', context_limit: '#f43f5e', idle: '#6b7280',
  };

  /* The word for each state. "대기" was doing double duty for idle and for
   * waiting-on-you, which are opposite things to do next, so they are named
   * apart here: 입력대기 is waiting for you, 유휴 is waiting for nothing. */
  var STATE_TEXT = {
    working: '작업중', stuck_after_agent: '응답없음', waiting: '입력대기',
    error: '오류', context_limit: '한도', idle: '유휴', unknown: '상태미상',
  };

  /* Which states are a session doing something, or wanting something. Those
   * breathe; the settled ones sit still, so motion on the rail means
   * "something is going on here" rather than "there is a list here". */
  var STATE_LIVE = {
    working: true, waiting: true, stuck_after_agent: true,
    error: true, context_limit: true,
  };

  function stateText(st) { return STATE_TEXT[st] || STATE_TEXT.unknown; }

  /* Transitions worth interrupting for: the ones that end with the session
   * wanting something from you, plus work finishing. Everything else --
   * 유휴 → 작업중 most of all, which is just the machine getting on with it --
   * changes its word and says nothing. With seventy sessions on the rail, a
   * cue that fires for every change is a rail that is always flickering, and
   * a flicker that means nothing in particular is one you stop reading. */
  var STATE_WANTS_YOU = {
    waiting: true, stuck_after_agent: true, error: true, context_limit: true,
  };

  function worthNoticing(from, to) {
    if (STATE_WANTS_YOU[to]) return true;
    return from === 'working' && to === 'idle';   /* it finished */
  }

  /* What each session was doing when the surfaces were last painted. Seeded
   * by the first publication -- which arrives from the board before any
   * console exists -- so opening the console does not set the whole rail
   * flashing at states that have been true for an hour. */
  var lastSeen = {};

  function noticedTransitions() {
    var flash = {};
    var live = sessionCatalog();
    for (var i = 0; i < live.length; i++) {
      var name = live[i].name, now = live[i].state;
      var was = lastSeen[name];
      if (was !== undefined && was !== now && worthNoticing(was, now)) flash[name] = true;
      lastSeen[name] = now;
    }
    return flash;
  }

  /* Removed on a timer rather than on animationend: with reduced motion, or
   * anywhere else the animation does not run, that event never arrives and
   * the class would stay on -- so the NEXT transition would have nothing to
   * re-trigger. */
  function flashElement(node, st) {
    if (!node) return;
    node.style.setProperty('--ctb-notice', STATE_DOT[st] || 'var(--con-accent)');
    node.classList.remove('ctb-notice');
    /* Reading offsetWidth restarts an animation that is already running --
     * two alerts in a row have to be two flashes, not one that never blinks. */
    void node.offsetWidth;
    node.classList.add('ctb-notice');
    window.setTimeout(function () { node.classList.remove('ctb-notice'); }, 1300);
  }

  function makeDot(st) {
    var dot = document.createElement('span');
    dot.className = 'ctb-sdot';
    /* Decoration: the same fact is in the row's text and its accessible
     * name, and a screen reader reading "bullet" adds nothing. */
    dot.setAttribute('aria-hidden', 'true');
    paintDot(dot, st);
    return dot;
  }

  function paintDot(dot, st) {
    dot.style.background = STATE_DOT[st] || '#6b7280';
    if (STATE_LIVE[st]) dot.setAttribute('data-live', '');
    else dot.removeAttribute('data-live');
  }

  function makeStateLabel(st) {
    var lab = document.createElement('span');
    lab.className = 'ctb-slabel';
    lab.setAttribute('aria-hidden', 'true');
    paintStateLabel(lab, st);
    return lab;
  }

  /* The word is text, and text has to be readable: the dot's colours are
   * picked to glow against a dark pane and measure about 1.5:1 against the
   * light one, which is unreadable at 10px -- and painting the word in the
   * state's colour would have made it a second colour channel anyway. The
   * colour is the dot's job. The word's job is to be read, so it takes the
   * theme's own foreground: full strength when something is going on, dimmed
   * when nothing is. */
  function paintStateLabel(lab, st) {
    lab.textContent = stateText(st);
    /* Both of these are foreground colours the theme picks to be read at
     * small sizes. The quiet one is --con-muted, not --con-dim: dim is the
     * placeholder grey, which measures 3.8:1 on the light sheet and 2.1:1 on
     * a selected row -- a word nobody can read is not a state signal, it is
     * decoration with a font. */
    lab.style.color = STATE_LIVE[st] ? 'var(--con-text)' : 'var(--con-muted)';
    lab.style.opacity = '1';
  }

  /* The dashboard publishes the order it renders; without it (a console opened
   * before the first paint, or from a deep link) fall back to the raw snapshot,
   * which is at least a list of live sessions. */
  function sessionOrder() {
    var list = window.ctbSessionOrder;
    /* Same rule as sessionCatalog: published-and-empty means there is
     * nothing, and only nothing-published falls back to the snapshot this
     * console fetched for itself. They have to agree -- with the catalogue
     * saying "no sessions" and the order still naming yesterday's, the rail
     * removed its dead chips and then immediately rebuilt them from the
     * stale list, one repaint later. */
    if (Array.isArray(list)) return list;
    return state.order || [];
  }

  /* Every session, not just the ones the grid's filter left showing. The strip
   * and the number shortcuts mirror the grid on purpose -- they are the grid's
   * own shortcuts -- but a search that inherits a filter set behind a
   * full-bleed sheet, where it can be neither seen nor cleared, is a search
   * that lies about what exists. */
  function sessionCatalog() {
    var all = window.ctbSessionAll;
    /* An empty array is an answer -- the board has data and there are no
     * sessions. Treating it as "no answer yet" and falling back to the last
     * order left the palette offering sessions that had all ended, and Enter
     * on one of those opened a console onto nothing. Only a missing array
     * (nothing published yet) falls back. */
    if (Array.isArray(all)) return all;
    return sessionOrder();
  }

  /* The board tells us it has new session data; both surfaces take it from
   * the globals it has just republished. Kept passive: the console asks for
   * nothing here and repaints nothing that is not already on screen. */
  window.addEventListener('ctb:sessions', function () { syncSurfaces(); });

  function fetchOrder() {
    if (Array.isArray(window.ctbSessionOrder) && window.ctbSessionOrder.length) return;
    fetch(api('/api/sessions'), { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.sessions) return;
        state.order = data.sessions.map(function (s) {
          var stripped = String(s.name).replace(/^claude[_-]/, '');
          var wt = stripped.indexOf('_wt_');
          return {
            name: s.name,
            state: s.state,
            label: wt === -1 ? stripped : stripped.slice(0, wt),
            branch: wt === -1 ? null : stripped.slice(wt + 4),
          };
        });
        renderStrip();
      })
      .catch(function () { /* the strip just stays empty */ });
  }

  /* Pinned is server state the board re-reads on a timer, so this is checked on
   * every render rather than once when the console opens. */
  function paintSilentBadge() {
    if (!el.silent) return;
    var pinned = window.ctbPinned;
    if (!state.session || !Array.isArray(pinned)) {
      el.silent.style.display = 'none';
      return;
    }
    el.silent.style.display = pinned.indexOf(state.session) === -1 ? 'inline' : 'none';
  }

  /* The pin button says which quadrant the open session is in -- or that it is
   * in none, which is the same thing as "no completion alert for this one". */
  function paintQuadBtn() {
    if (!el.quad) return;
    if (!state.session) { el.quad.style.display = 'none'; return; }
    el.quad.style.display = '';
    var qid = (window.ctbQuadOf || {})[state.session] || null;
    var label = qid ? QUAD_LABELS[qid] || qid : '알림 없음';
    el.quad.setAttribute('data-quad', qid || '');
    if (el.quadNum) el.quadNum.textContent = qid ? qid.slice(1) : '';
    el.quad.title = '중요도 / 알림 — 현재: ' + label;
    el.quad.setAttribute('aria-label', '중요도 및 알림 설정, 현재 ' + label);
  }

  function quadMenuOpen() {
    return !!(el.root && el.root.querySelector('[data-quad-menu]'));
  }

  function closeQuadMenu() {
    if (!el.root) return;
    var menu = el.root.querySelector('[data-quad-menu]');
    if (menu) {
      var hadFocus = menu.contains(document.activeElement);
      menu.parentNode.removeChild(menu);
      /* Removing the focused node drops focus on <body>, and the console's
       * key handling has nothing to work with from there. */
      if (hadFocus && el.quad && el.root && el.root.style.display !== 'none') el.quad.focus();
    }
    if (el.quad) el.quad.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', quadMenuAway, true);
  }

  function quadMenuAway(e) {
    if (!el.root) return;
    var menu = el.root.querySelector('[data-quad-menu]');
    if (menu && (menu.contains(e.target) || (el.quad && el.quad.contains(e.target)))) return;
    closeQuadMenu();
  }

  function setQuadrant(qid) {
    var name = state.session;
    closeQuadMenu();
    if (!name) return;
    var setter = window.ctbSetQuadrant;
    if (typeof setter !== 'function') {
      /* The board's pin machinery lives in the page, not here. In a context
       * that never loaded it (a bare console page) say so rather than
       * pretending the tap landed. */
      setStatus('이 화면에서는 중요도를 바꿀 수 없습니다', 'var(--con-err)');
      return;
    }
    var label = qid ? (QUAD_LABELS[qid] || qid) : '알림 없음';
    /* The write is a queued read-modify-write behind an optimistic paint, so
     * the answer can arrive seconds later -- by which time the console may be
     * showing a different session. A result belongs to the session it was
     * asked for, and to nothing else. */
    return Promise.resolve(setter(name, qid)).then(function (ok) {
      /* Repaint regardless of which session is open now: a rejected write is
       * rolled back on the board, and the rail showing the console's *other*
       * session was painted from the optimistic set. Only the spoken result
       * belongs to the session that asked for it. */
      renderStrip();
      if (state.session !== name) return ok;
      if (ok === false) {
        setStatus('중요도를 바꾸지 못했습니다', 'var(--con-err)');
      } else {
        setStatus('중요도: ' + label, 'var(--con-ok)');
      }
      return ok;
    }, function () {
      if (state.session === name) setStatus('중요도를 바꾸지 못했습니다', 'var(--con-err)');
      return false;
    });
  }

  function toggleQuadMenu() {
    if (quadMenuOpen()) { closeQuadMenu(); return; }
    if (!state.session || !el.root) return;
    hideHints();
    var current = (window.ctbQuadOf || {})[state.session] || null;

    var menu = document.createElement('div');
    menu.setAttribute('data-quad-menu', '');
    menu.setAttribute('role', 'menu');
    /* Under the button it belongs to, measured rather than guessed: a fixed
     * offset sat on top of the button on some layouts, and a menu covering
     * its own toggle cannot be dismissed by tapping that toggle. */
    var anchor = el.quad.getBoundingClientRect();
    var rootBox = el.root.getBoundingClientRect();
    var top = Math.round(anchor.bottom - rootBox.top + 6);
    menu.style.cssText = [
      'position:absolute', 'top:' + top + 'px', 'right:10px', 'z-index:5',
      'display:flex', 'flex-direction:column', 'gap:4px', 'padding:6px',
      'border-radius:12px', 'background:var(--con-well)',
      'border:1px solid var(--con-edge)',
      'box-shadow:0 8px 24px rgba(16,24,40,0.28)', 'min-width:168px',
    ].join(';');

    /* No colour dot on the quadrant rows: the row itself is that colour now,
     * and the same hue twice reads as decoration. The off switch keeps its
     * glyph, because "no quadrant" has no hue to speak with. */
    var rows = [
      { qid: 'Q1', text: QUAD_LABELS.Q1 },
      { qid: 'Q2', text: QUAD_LABELS.Q2 },
      { qid: 'Q3', text: QUAD_LABELS.Q3 },
      { qid: 'Q4', text: QUAD_LABELS.Q4 },
      { qid: null, text: '🔕 알림 끄기 (핀 해제)' },
    ];
    rows.forEach(function (r) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('role', 'menuitemradio');
      b.setAttribute('data-quad-set', r.qid === null ? 'none' : r.qid);
      var on = r.qid === current;
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.textContent = (on ? '✓ ' : '') + r.text;
      styleBtn(b);
      b.className += ' con-quad';
      b.setAttribute('data-quad', r.qid || '');
      /* .con-btn centres its content; a menu is a list, so it reads left. */
      b.style.cssText = 'justify-content:flex-start;text-align:left;padding:8px 10px;font-size:13px;white-space:nowrap;'
        + (on ? 'font-weight:700;' : '');
      b.addEventListener('click', function (e) {
        e.stopPropagation();
        setQuadrant(r.qid);
      });
      menu.appendChild(b);
    });

    /* Focus moves into the menu, and the menu answers its own keys.
     * Without this the caret stayed in the prompt box (keepCaret keeps it
     * there through a header tap): Enter would send the draft to the session
     * and Tab would send a tab keystroke to tmux, both while a menu was open
     * on top. Escape here closes the menu only -- the document handler that
     * closes the whole console never sees it. */
    menu.addEventListener('keydown', function (e) {
      var items = Array.prototype.slice.call(menu.querySelectorAll('[data-quad-set]'));
      var at = items.indexOf(document.activeElement);
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closeQuadMenu();
        if (el.quad) el.quad.focus();
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        var step = e.key === 'ArrowDown' ? 1 : -1;
        var next = items[(at + step + items.length) % items.length];
        if (next) next.focus();
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        closeQuadMenu();
        if (el.quad) el.quad.focus();
      }
    });

    el.root.appendChild(menu);
    var first = menu.querySelector('[aria-checked="true"]') || menu.querySelector('[data-quad-set]');
    if (first) first.focus();
    el.quad.setAttribute('aria-expanded', 'true');
    /* Capture phase: the sheet stops clicks of its own, and without this a tap
     * on the tail would leave the menu hanging over the terminal. */
    setTimeout(function () {
      document.addEventListener('click', quadMenuAway, true);
    }, 0);
  }

  /* Something else is holding the keyboard. The palette is ours; the
   * new-session sheet is the board's, opened with Ctrl+N from in here, and
   * while it is up every shortcut below stands down -- otherwise Escape
   * closed the sheet and the console under it in one press, and Ctrl+Tab
   * walked to another session behind a dialog naming this one. */
  function sheetOpen() {
    var ns = window.ctbNewSession;
    return !!(ns && ns.isOpen && ns.isOpen());
  }

  function keysTaken() {
    return searchOpen() || sheetOpen() || findOpen();
  }

  /* The name a screen reader reads: who, which branch, and what it is doing.
   * The chip's visible text can be clipped to an ellipsis and its dot is
   * hidden from assistive tech, so this is the only place the whole answer
   * exists. */
  function paintChipName(chip, item) {
    var who = item.branch ? item.label + ' 워크트리 ' + item.branch : item.label;
    chip.setAttribute('data-who', who);
    paintChipState(chip, stateText(item.state));
  }

  function paintChipState(chip, word) {
    chip.setAttribute('aria-label',
      (chip.getAttribute('data-who') || '') + ', ' + word + ' — 전환');
  }

  /* --- keeping the two surfaces current ---------------------------------
   *
   * The rail used to be drawn when the console opened and then left alone:
   * it was repainted on a switch, on the number-hint hold, on a quadrant
   * write and when a session ended, but NOT when the board got new data. A
   * session could finish, or stall, and its dot would still say 작업중 for as
   * long as the console stayed open -- the surface meant to tell you what is
   * going on was the one surface that had stopped asking.
   *
   * It is fixed by patching, not by redrawing. A full renderStrip() re-sorts
   * the rail by state, and a rail that reorders under the hand costs the
   * thing it is for: the chip you were reaching for moves, the frozen number
   * shortcuts stop matching, and the scroll position jumps. So a data update
   * only ever rewrites the dot and the word on the chips that are already
   * there, adds chips for sessions that appeared, and drops the ones that
   * went away. The ORDER is settled when the rail is built and left alone
   * until something else rebuilds it. */
  function syncSurfaces() {
    /* Worked out once, before either surface is touched: both have to flash
     * the same sessions, and the reckoning also records what was seen, so it
     * can only happen once per publication. */
    var flash = noticedTransitions();
    syncStrip(flash);
    syncPalette(flash);
  }

  function catalogMap() {
    var map = {};
    var all = sessionCatalog();
    for (var i = 0; i < all.length; i++) map[all[i].name] = all[i];
    return map;
  }

  function syncStrip(flash) {
    if (!el.strip) return;
    /* A hidden rail is the empty rail, and it must still be able to come
     * back: the last session ending hides it, and the next one starting has
     * to be able to put it back on screen. */
    if (el.strip.style.display === 'none') {
      if (sessionOrder().length) renderStrip();
      return;
    }
    /* While the accelerator is held the rail is showing a frozen order with
     * numbers on it; the digits fire on that same snapshot. Adding or
     * removing chips under the hold would renumber what the badges promise. */
    if (accelDown) return;
    var map = catalogMap();
    var chips = el.strip.querySelectorAll('[data-switch-session]');
    var seen = {};
    for (var i = 0; i < chips.length; i++) {
      var chip = chips[i];
      var name = chip.getAttribute('data-switch-session');
      var item = map[name];
      if (!item) {
        /* Gone. Keep the one the console is actually showing -- losing it
         * from the rail is how you end up unable to switch away from a
         * session whose pane is still on screen -- but say that it ended.
         * Keeping it AND leaving it saying 작업중 is the worst of both. */
        if (name === state.session) { seen[name] = true; markChipGone(chip); continue; }
        chip.parentNode.removeChild(chip);
        continue;
      }
      seen[name] = true;
      chip.removeAttribute('data-gone');
      chip.style.opacity = '';
      var dot = chip.querySelector('.ctb-sdot');
      var lab = chip.querySelector('.ctb-slabel');
      if (dot) paintDot(dot, item.state);
      if (lab) paintStateLabel(lab, item.state);
      paintChipName(chip, item);
      if (flash && flash[name]) flashElement(chip, item.state);
    }
    /* A session that appeared gets a chip on the end. Not a rebuild: a
     * rebuild replaces every chip with a new node in the newly sorted order
     * and recentres the rail, which between a finger going down and coming
     * up throws away the chip that was being pressed, and mid-drag fights
     * the gesture for the scroll position. The end is the one place a chip
     * can be added without moving anything that is already there; the next
     * open sorts it in.
     *
     * Measured against what the rail is BUILT from (the board's visible
     * order), not the whole catalogue: the catalogue also holds sessions the
     * board's age filter is hiding, which were never on the rail. */
    var railList = sessionOrder();
    for (var j = 0; j < railList.length; j++) {
      if (!seen[railList[j].name]) appendChip(railList[j], j);
    }
  }

  /* The rail's version of 종료됨. The open session keeps its chip when it
   * ends, and this is what stops that chip from going on claiming the state
   * it had at the moment it died. Which of the two signals arrives first --
   * the board dropping it from the list, or its own pane answering 404 --
   * decides nothing: both paths end here. */
  function markChipGone(chip) {
    chip.setAttribute('data-gone', '');
    chip.style.opacity = '0.55';
    var dot = chip.querySelector('.ctb-sdot');
    var lab = chip.querySelector('.ctb-slabel');
    if (dot) paintDot(dot, 'idle');
    if (lab) {
      lab.textContent = '\uc885\ub8cc\ub428';
      lab.style.color = 'var(--con-muted)';
      lab.style.opacity = '1';
    }
    paintChipState(chip, '\uc885\ub8cc\ub428');
  }

  /* The display name for a session the catalogue no longer carries: the same
   * trimming the board does, done here because there is nothing left to ask. */
  function shortLabel(name) {
    var stripped = String(name).replace(/^claude[_-]/, '');
    var wt = stripped.indexOf('_wt_');
    return wt === -1 ? stripped : stripped.slice(0, wt);
  }

  function makeChip(item, index) {
    var chip = document.createElement('button');
    chip.type = 'button';
    chip.setAttribute('data-switch-session', item.name);
    if (item.name === state.session) chip.setAttribute('aria-current', 'true');
    /* Content-sized, not one-third of the sheet: three fixed slots wasted the
     * row on short names and forced a scroll to reach the fourth session.
     * Capped so one long name cannot take the whole bar. */
    chip.className = 'con-chip';
    var quad = window.ctbQuadOf && window.ctbQuadOf[item.name];
    if (quad) chip.setAttribute('data-quad', quad);
    chip.title = quad ? item.name + ' · ' + (QUAD_LABELS[quad] || quad) : item.name;

    var text = document.createElement('span');
    text.style.cssText = 'min-width:0;white-space:nowrap;overflow:hidden;' +
      'text-overflow:ellipsis;';
    text.textContent = item.branch ? item.label + ' ⎇' + item.branch : item.label;

    chip.appendChild(makeDot(item.state));
    /* While the numbers are frozen the chip carries the number that will
     * actually fire, not its position in a rail that may have re-sorted
     * since. Unfrozen, the two are the same thing. */
    var numbered = accelDown ? slotOfName(item.name) : index;
    if (numbered > -1 && numbered < HINT_MAX) {
      var num = document.createElement('b');
      num.setAttribute('data-numhint', '');
      num.textContent = String(numbered + 1);
      num.style.cssText = "font-family:'JetBrains Mono',monospace;" +
        'font-size:9px;font-weight:700;color:var(--con-warn);flex-shrink:0;' +
        'padding:0 3px;border-radius:4px;background:rgba(245,158,11,0.16);' +
        'border:1px solid rgba(245,158,11,0.4);' +
        'display:' + (accelDown ? 'inline-block' : 'none') + ';';
      chip.appendChild(num);
    }
    chip.appendChild(text);
    chip.appendChild(makeStateLabel(item.state));
    paintChipName(chip, item);
    return chip;
  }

  function appendChip(item, index) {
    el.strip.style.display = 'flex';
    el.strip.appendChild(makeChip(item, index));
  }

  function renderStrip() {
    paintSilentBadge();
    paintQuadBtn();
    if (!el.strip) return;
    var list = sessionOrder();
    el.strip.textContent = '';
    /* Empty is not necessarily empty: the board's age filter can hide every
     * session while one of them is open on this very screen, and the rail
     * going dark then takes the only marker of where the user is. The chip
     * for the open session is added below whatever the list says; the rail
     * is hidden only if that leaves nothing either. */
    if (!list.length && !state.session) {
      el.strip.style.display = 'none';
      return;
    }
    el.strip.style.display = 'flex';

    var current = null;
    list.forEach(function (item, index) {
      var chip = makeChip(item, index);
      el.strip.appendChild(chip);
      if (item.name === state.session) current = chip;
    });

    /* The open session, when it is not in the list the rail is built from.
     * sessionGone() rebuilds from that list, so without this the chip for the
     * pane still on screen vanished -- and which signal landed first (the
     * board's update, or this session's own 404) decided whether the user
     * could still see where they were.
     *
     * Whether it ENDED is a different question, and the list cannot answer
     * it: that list is the board's VISIBLE order, which its age filter
     * shortens. Search reaches sessions the filter is hiding and opens them,
     * so a perfectly live session arrives here routinely. The catalogue is
     * what knows, and only the catalogue may write the headstone. */
    if (state.session && !current) {
      var live = null;
      var all = sessionCatalog();
      for (var k = 0; k < all.length; k++) {
        if (all[k].name === state.session) { live = all[k]; break; }
      }
      var chip = makeChip(live || { name: state.session,
                                    label: shortLabel(state.session),
                                    branch: null, state: 'idle' }, -1);
      if (!live) markChipGone(chip);
      el.strip.appendChild(chip);
      current = chip;
    }

    if (!el.strip.children.length) {
      el.strip.style.display = 'none';
      return;
    }

    if (current) {
      /* Keep the open session in view without yanking the page around it. */
      el.strip.scrollLeft = Math.max(0,
        current.offsetLeft - el.strip.clientWidth / 2 + current.offsetWidth / 2);
    }
  }

  /* --- number shortcuts -------------------------------------------------- */

  /* Hold the accelerator and the first nine sessions -- grid order, which the
   * rail also follows -- are numbered 1..9; pressing the digit opens that one.
   * Works with the console open (numbers on the chips) and closed (numbers on
   * the dashboard cards), since the grid is where the choice is usually made.
   *
   * Platform convention decides the accelerator: Cmd on a Mac, Ctrl elsewhere,
   * which is what every tabbed app on each platform uses. Alt (Option) is bound
   * as well, and is the one that always arrives: a browser TAB reserves
   * Ctrl/Cmd+1..8 for its own tab switching and the page never gets to act on
   * it. An installed PWA window has no tab strip, so there the documented
   * chord works. Alt is reserved by nobody, so it covers the tab case.
   */
  var IS_MAC = /Mac|iPhone|iPad|iPod/.test(
    (navigator.userAgentData && navigator.userAgentData.platform) ||
    navigator.platform || navigator.userAgent);
  /* Nine, not ten: Ctrl/Cmd+0 resets the browser zoom, which is how you undo an
   * accidental wheel-zoom. Taking it for a tenth session would cost more than
   * it gives. */
  var HINT_MAX = 9;

  /* acquireVsCodeApi exists only inside a VSCode webview. */
  var IS_VSCODE = typeof acquireVsCodeApi === 'function';

  function accelHeld(e) {
    return (IS_MAC ? e.metaKey : e.ctrlKey) || e.altKey;
  }

  function slotOf(key) {
    if (key >= '1' && key <= '9') return key.charCodeAt(0) - 49;
    return -1;
  }

  /* The number is drawn on the chip that already carries the name -- a separate
   * panel repeated every label for no gain. renderStrip() builds the badges
   * hidden and paintHints() is what reveals them, so a refresh landing mid-hold
   * does not drop them. */
  var accelDown = false;

  /* The list the numbers refer to, frozen while the accelerator is held.
   *
   * The grid re-sorts on every poll -- pinned first, then state, then how
   * recently the session moved -- so a session finishing its work is enough to
   * renumber everything below it. Read live, the map moved between seeing "3"
   * and pressing it, and the digit opened whatever had since taken the slot:
   * the numbers were unreliable exactly when the board was busy, which is when
   * they are wanted. Frozen at the moment the accelerator goes down, what is
   * on screen and what the digit does cannot disagree, and the badges stop
   * shuffling under a held finger. Released with the key. */
  var hintOrder = null;

  function hintsVisible() {
    return accelDown;
  }

  function inCatalog(name) {
    var list = sessionCatalog();
    for (var i = 0; i < list.length; i++) {
      if (list[i].name === name) return true;
    }
    return false;
  }

  function slotOfName(name) {
    if (!hintOrder) return -1;
    for (var i = 0; i < hintOrder.length; i++) {
      if (hintOrder[i].name === name) return i;
    }
    return -1;
  }

  function paintHints() {
    if (el.strip) {
      var badges = el.strip.querySelectorAll('[data-numhint]');
      for (var i = 0; i < badges.length; i++) {
        badges[i].style.display = accelDown ? 'inline-block' : 'none';
      }
    }
    paintGridHints();
  }

  /* The same numbers, on the dashboard's own cards, so the chord does not need
   * a console open first -- the grid is where you are when you decide which
   * session to go to. The badges are drawn onto the cards rather than built
   * into them: the grid re-renders its whole markup on every poll, and a badge
   * baked into that string would have to be threaded through a template that
   * knows nothing about a key being held. Drawn here they cost nothing when no
   * one is holding anything. */
  function clearGridHints() {
    var old = document.querySelectorAll('[data-ctb-gridhint]');
    for (var i = 0; i < old.length; i++) old[i].remove();
  }

  function paintGridHints() {
    clearGridHints();
    /* With the console open the strip carries the numbers, and the grid behind
     * it is not on screen anyway. */
    if (!accelDown || state.session) return;
    var list = hintOrder || sessionOrder();
    for (var i = 0; i < list.length && i < HINT_MAX; i++) {
      var card = cardFor(list[i].name);
      if (!card) continue;
      var b = document.createElement('b');
      b.setAttribute('data-ctb-gridhint', '');
      b.textContent = String(i + 1);
      /* Bottom-left, not beside the pin: up there it sat on the first letters
       * of the session name, which is the one thing you are reading when you
       * pick a number. Down here it covers a corner of the idle timer. */
      b.style.cssText = "position:absolute;bottom:6px;left:6px;z-index:7;" +
        "font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;" +
        'color:var(--con-warn);padding:2px 7px;border-radius:7px;pointer-events:none;' +
        'background:var(--con-hint-bg);border:1px solid rgba(245,158,11,0.55);';
      card.appendChild(b);
    }
  }

  function cardFor(name) {
    var cards = document.querySelectorAll('[data-session-name]');
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].getAttribute('data-session-name') === name) return cards[i];
    }
    return null;
  }

  /* A poll landing mid-hold rewrites the grid and takes the badges with it.
   * Repainting while the key is down is cheaper than watching the DOM. */
  var hintTimer = null;

  function showHints() {
    if (accelDown) return;
    accelDown = true;
    hintOrder = sessionOrder().slice();
    /* The rail is drawn when the console opens and not again on every poll,
     * so its badges carried the numbers of THAT moment's order while the
     * digits fired on the order frozen here. After a re-sort the "1" on the
     * chip and the session Ctrl+1 opened were different sessions. Redraw the
     * rail from the frozen order so the two cannot disagree. */
    renderStrip();
    paintHints();
    if (!hintTimer) hintTimer = setInterval(paintHints, 400);
  }

  function hideHints() {
    if (!accelDown) return;
    accelDown = false;
    hintOrder = null;
    if (hintTimer) { clearInterval(hintTimer); hintTimer = null; }
    /* Back to the live order, with the badges hidden. */
    renderStrip();
    paintHints();
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Control' || e.key === 'Meta' || e.key === 'Alt') {
      /* Only the accelerator for THIS platform opens the panel, so a stray
       * Ctrl on a Mac does not advertise shortcuts that will not fire. */
      if (e.key === 'Alt' || (IS_MAC ? e.key === 'Meta' : e.key === 'Control')) {
        showHints();
      }
      return;
    }
    if (!accelHeld(e) || e.shiftKey) return;
    /* The palette owns the keyboard while it is up, and so does the
     * new-session sheet. Without this the digit switched the console
     * UNDERNEATH the overlay and put the caret in a textarea nobody could
     * see -- so the next Enter, typed at what looked like a search box,
     * would send a prompt to a live session. */
    if (keysTaken()) return;
    var slot = slotOf(e.key);
    if (slot === -1) return;
    var item = (hintOrder || sessionOrder())[slot];
    /* The snapshot is a moment old, and in that moment a session can end. Open
     * one that is gone and the console sits on a pane that will never answer,
     * which is a worse answer than none: the badge was pointing at something
     * that no longer exists. Checked against the full catalog, not the visible
     * list, so a filter typed mid-hold does not read as a disappearance. */
    if (item && hintOrder && !inCatalog(item.name)) item = null;
    hideHints();
    if (!item) return;          /* fewer sessions than the digit pressed */
    e.preventDefault();
    /* In the VSCode webview, switching means bringing that session's terminal
     * up -- the page's own card click already does that, and the console is
     * read-only there because the webview's port proxy forwards only GET.
     * With a console already open the digit switches the console, as
     * everywhere else: that is the surface the user is looking at. */
    if (!state.session && IS_VSCODE && window.ctbFocusSession
        && window.ctbFocusSession(item.name)) return;
    if (item.name !== state.session) show(item.name, true);
  });

  /* Ctrl/Cmd+[ walks UP the rail one session at a time and Ctrl/Cmd+] walks
   * DOWN, from wherever the open one sits, wrapping at either end. With Shift
   * held ({ and }) the walk visits only the 긴급+중요 (Q1) sessions: the ones
   * worth taking first, without stepping over the rest by hand. From a
   * session that is not Q1 it goes to the nearest Q1 in that direction.
   *
   * The digits are for jumping to a session you can see; this is for working
   * through them. The board sorts what needs attention to the top, so with
   * nothing open the up-walk starts at the end of the rail and the down-walk
   * at its head.
   *
   * The order is the same frozen snapshot the digits use, and this handler
   * deliberately does NOT release it: holding the accelerator and pressing
   * the bracket repeatedly walks one list, instead of re-deriving the
   * numbering from a board that re-sorts under every step.
   *
   * Alt is bound as well: Cmd+[ and Cmd+] are history back/forward on a Mac
   * and a browser may take them before the page does. */
  function stepSession(dir, urgentOnly) {
    var list = hintOrder || sessionOrder();
    var n = list.length;
    if (!n) return null;
    var quadOf = window.ctbQuadOf || {};
    var ok = function (it) { return !urgentOnly || quadOf[it.name] === 'Q1'; };
    var here = -1;
    for (var i = 0; i < n; i++) {
      if (list[i].name === state.session) { here = i; break; }
    }
    /* Nothing open: the walk begins at the far end of its direction. */
    var idx = here === -1 ? (dir < 0 ? n : -1) : here;
    for (var step = 1; step <= n; step++) {
      var j = (idx + dir * step + n * step) % n;
      if (j === here) break;
      if (ok(list[j])) return list[j];
    }
    return null;
  }

  /* Page the tail by a screenful, for a keyboard on an iPad or a phone where
   * scrolling otherwise means putting a hand on the glass.
   *
   * The step is measured, not assumed: clientHeight is what this device is
   * actually showing, and dividing it by the computed line height gives the
   * lines on screen. One of them is kept as overlap -- the line you finish on
   * is the line you start the next screen with -- which is what a terminal's
   * own PgUp does and what stops a reader losing their place. A pane too
   * short to hold two lines still moves by one rather than not at all.
   *
   * Nothing here touches focus: the caret stays in the box, so a page-up
   * mid-sentence costs nothing to come back from. -> did it move. */
  function pageTail(dir) {
    var tail = el.tail;
    if (!tail) return false;
    var cs = window.getComputedStyle(tail);
    var lh = parseFloat(cs.lineHeight);
    if (!(lh > 0)) lh = (parseFloat(cs.fontSize) || 12) * 1.5;
    var visible = Math.floor(tail.clientHeight / lh);
    var step = Math.max(1, visible - 1) * lh;
    var max = Math.max(0, tail.scrollHeight - tail.clientHeight);
    var from = tail.scrollTop;
    var to = Math.max(0, Math.min(max, from + dir * step));
    if (Math.abs(to - from) < 1) return false;
    tail.scrollTop = to;
    return true;
  }

  /* Cmd/Ctrl+Shift+Up / Down. Not the bracket keys: those already walk the
   * session rail, and Shift there means "urgent and important only". */
  document.addEventListener('keydown', function (e) {
    if (!state.session || keysTaken()) return;
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    if (e.isComposing || e.keyCode === 229) return;
    if (!accelHeld(e) || !e.shiftKey) return;
    e.preventDefault();
    var dir = e.key === 'ArrowUp' ? -1 : 1;
    if (pageTail(dir)) {
      /* The tail's own scroll handler has already recorded whether this
       * landed at the bottom, so following resumes by itself down there. */
      setStatus(dir < 0 ? '\u2191 \ud55c \ud654\uba74' : '\u2193 \ud55c \ud654\uba74', 'var(--con-muted)');
    } else {
      setStatus(dir < 0 ? '\ub9e8 \uc704' : '\ub9e8 \uc544\ub798 \u00b7 \uc790\ub3d9 \ub530\ub77c\uac00\uae30', 'var(--con-muted)');
    }
  });

  document.addEventListener('keydown', function (e) {
    if (keysTaken()) return;
    /* `code` names the physical key: a shifted US layout reports { and },
     * and another layout may put something else on the cap entirely. */
    var dir = e.code === 'BracketLeft' || e.key === '[' || e.key === '{' ? -1
            : e.code === 'BracketRight' || e.key === ']' || e.key === '}' ? 1 : 0;
    if (!dir) return;
    if (!accelHeld(e)) return;
    e.preventDefault();
    var item = stepSession(dir, e.shiftKey);
    if (!item || (hintOrder && !inCatalog(item.name))) return;
    if (item.name === state.session) return;
    /* Closed console in the VSCode webview: the same rule the digits follow --
     * bring that session's terminal up, since the console there is read-only. */
    if (!state.session && IS_VSCODE && window.ctbFocusSession
        && window.ctbFocusSession(item.name)) return;
    show(item.name, true);
  });

  /* Ctrl/Cmd+Q closes the open session the way the trash does, and as fast as
   * a browser closes a tab: when the same git checks the trash runs say it is
   * safe (clean tree, pushed, and a worktree merged), the session is gone
   * with no dialog and the console moves to the neighbour on the rail. When
   * they do not, nothing happens but a line of reasons -- the forced delete
   * stays where it is, behind the card's trash and its second confirmation.
   *
   * Ctrl/Cmd+Shift+Q brings back the last closed session, one per press,
   * newest first, the way a browser reopens closed tabs. The server kept its
   * directory when it was closed and starts Claude there again; with a
   * transcript in that directory it resumes the conversation.
   *
   * Alt is bound too: Cmd+Q on a Mac and Ctrl+Q in Firefox on Linux quit the
   * browser before the page sees them. */
  var closing = false;

  function neighbourAfterClose(list, name) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].name === name) return list[i + 1] || list[i - 1] || null;
    }
    return null;
  }

  function dropFromOrders(name) {
    var keep = function (it) { return it.name !== name; };
    if (Array.isArray(window.ctbSessionOrder)) window.ctbSessionOrder = window.ctbSessionOrder.filter(keep);
    if (Array.isArray(window.ctbSessionAll)) window.ctbSessionAll = window.ctbSessionAll.filter(keep);
    if (Array.isArray(state.order)) state.order = state.order.filter(keep);
  }

  function closeSession() {
    if (!state.session || closing || state.busy) return;
    var name = state.session;
    closing = true;
    setStatus('닫는 중…', 'var(--con-muted)');
    window.ctbControl.send('/api/sessions/' + encodeURIComponent(name) + '/delete', {
      method: 'POST', body: JSON.stringify({ force: false }),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        return { status: res.status, body: body };
      });
    }).then(function (r) {
      closing = false;
      if (r.status === 200 && r.body.status === 'deleted') {
        var next = neighbourAfterClose(sessionOrder(), name);
        dropFromOrders(name);
        delete state.drafts[name];
        saveDrafts();
        if (next) show(next.name, true); else hide();
        return;
      }
      if (state.session !== name) return;
      if (r.status === 409) {
        var reasons = (r.body.check && r.body.check.reasons) || [];
        setStatus('닫기 보류 · ' + (reasons.join(' · ') || '안전하지 않음') + ' · 강제 삭제는 카드의 🗑', 'var(--con-warn)');
      } else if (r.status === 200) {
        setStatus('닫기 실패 · ' + (r.body.error || r.body.status || ''), 'var(--con-err)');
      } else {
        setStatus('닫기 실패 (' + r.status + ')', 'var(--con-err)');
      }
    }).catch(function () {
      closing = false;
      if (state.session === name) setStatus('닫기 실패 · 네트워크', 'var(--con-err)');
    });
  }

  function restoreSession() {
    if (closing) return;
    closing = true;
    setStatus('복원 중…', 'var(--con-muted)');
    window.ctbControl.send('/api/sessions/restore', { method: 'POST', body: '{}' })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { status: res.status, body: body };
        });
      }).then(function (r) {
        closing = false;
        if (r.status === 200 && r.body.session) {
          show(r.body.session, true);
          setStatus('복원됨 · ' + r.body.session, 'var(--con-ok)');
        } else if (r.status === 404) {
          setStatus('복원할 세션이 없습니다', 'var(--con-warn)');
        } else {
          setStatus('복원 실패 (' + r.status + ')' + (r.body.detail ? ' · ' + r.body.detail : ''), 'var(--con-err)');
        }
      }).catch(function () {
        closing = false;
        setStatus('복원 실패 · 네트워크', 'var(--con-err)');
      });
  }

  document.addEventListener('keydown', function (e) {
    if (keysTaken()) return;
    if (e.code !== 'KeyQ' && String(e.key).toLowerCase() !== 'q') return;
    if (!accelHeld(e)) return;
    /* Restore works with the console closed as well; closing needs one open. */
    if (!e.shiftKey && !state.session) return;
    e.preventDefault();
    if (e.shiftKey) restoreSession(); else closeSession();
  });

  /* Ctrl/Cmd+Tab bounces between the last two sessions, the way Alt+Tab does.
   * It sits on the same modifier as the Ctrl+[ ] walk on purpose: moving between
   * sessions is one gesture with the accelerator held down, and the hand never
   * has to swap modifiers mid-thought to get back to where it was.
   *
   * A browser tab keeps this chord for its own tab switching and the page
   * never sees it; an installed PWA window and the VSCode webview have no tab
   * strip, so there it arrives. In a plain browser tab the Ctrl+[ ] walk is the
   * one that always gets through. */
  document.addEventListener('keydown', function (e) {
    if (!state.session || keysTaken() || e.key !== 'Tab') return;
    if (e.shiftKey || e.altKey) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.isComposing || e.keyCode === 229) return;   /* the IME's key, not ours */
    e.preventDefault();
    if (!state.prev || state.prev === state.session) return;
    show(state.prev, true);
  });

  /* Shift+Tab sends a Tab to the pane from anywhere in the sheet, the prompt
   * box included -- one key that means the same thing wherever the caret is.
   * It used to be left alone in the box as the way to reach the sheet's own
   * buttons by keyboard; that path is given up on purpose. The keys those
   * buttons send are all on the pad or on a chord already, and the number
   * shortcuts and the search land in the box, which is where typing goes. */
  document.addEventListener('keydown', function (e) {
    if (!state.session || keysTaken() || e.key !== 'Tab' || !e.shiftKey) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229) return;   /* the IME's key, not ours */
    e.preventDefault();
    sendKey('Tab', 'Shift+Tab');
  });

  /* Shift+Escape sends Escape to the session, for the same reason Shift+Tab
   * sends Tab: plain Escape over the console is the sheet's own (close the
   * find bar, drop a selection, close the console), and Escape is the key
   * that interrupts Claude Code. The shifted one is unambiguous everywhere --
   * the box included -- so it needs no rule about where the caret is. */
  document.addEventListener('keydown', function (e) {
    if (!state.session || keysTaken() || e.key !== 'Escape' || !e.shiftKey) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    /* Held down the OS repeats this, and every repeat is an interrupt sent to
     * a live session. One press, one Escape. */
    if (e.repeat) return;
    e.preventDefault();
    sendKey('Escape', 'Shift+Esc');
  });

  /* --- one-shot key send ------------------------------------------------- */

  /* The key pad answers a prompt with a tap. From a keyboard there was no way
   * to do the same without reaching for it, and every obvious chord family is
   * spoken for: Ctrl+Alt IS AltGr on most European layouts (it is how @ and €
   * are typed), it is VoiceOver's modifier on a Mac, and the desktop takes
   * Ctrl+Alt+Tab, Ctrl+Alt+arrows and Ctrl+Alt+Escape before a page sees them.
   *
   * So the modifier goes on the FIRST key only. Ctrl/Cmd+. arms, the next
   * plain key is sent to the session, and the arming ends there. The second
   * keystroke carries no modifier at all, which is why the whole set works --
   * y n 1-9, the arrows, Tab, Enter, Escape, Backspace -- with nothing at the
   * OS or browser layer wanting any of it.
   *
   * An armed console that says nothing would be a trap: the next key leaves
   * for a live session. It is on the status line the whole time, it gives up
   * after ten seconds, and it gives up if the window loses focus. */
  var SEND_KEYS = {
    y: 'y', Y: 'Y', n: 'n', N: 'N',
    ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
    Backspace: 'BSpace', Tab: 'Tab', Enter: 'Enter', Escape: 'Escape',
    ' ': 'Space', Spacebar: 'Space',
  };

  function sendKeyName(key) {
    if (key >= '1' && key <= '9') return key;
    return SEND_KEYS[key] || null;
  }

  var armed = false;
  var armTimer = null;
  var ARM_MS = 10000;

  function armSend() {
    disarmSend(true);
    armed = true;
    armTimer = setTimeout(function () { disarmSend(false, '\ud0a4 \uc804\uc1a1 \ucde8\uc18c\ub428'); }, ARM_MS);
    setStatus('\ub2e4\uc74c \ud55c \ud0a4\ub97c \uc138\uc158\uc73c\ub85c \ubcf4\ub0c5\ub2c8\ub2e4 \u00b7 \ucde8\uc18c\ub294 \ub2e4\uc2dc '
      + (IS_MAC ? 'Cmd' : 'Ctrl') + '+.', 'var(--con-warn)');
  }

  function disarmSend(quiet, why) {
    if (armTimer) clearTimeout(armTimer);
    armTimer = null;
    if (!armed) return;
    armed = false;
    if (!quiet) setStatus(why || '', why ? 'var(--con-muted)' : '');
  }

  function sendArmed() { return armed; }

  function isArmChord(e) {
    if (e.key !== '.' && e.code !== 'Period') return false;
    return (IS_MAC ? e.metaKey : e.ctrlKey) && !e.shiftKey && !e.altKey;
  }

  document.addEventListener('keydown', function (e) {
    if (!state.session || keysTaken() || quadMenuOpen()) return;
    if (e.key !== '.' && e.code !== 'Period') return;
    if (!(IS_MAC ? e.metaKey : e.ctrlKey) || e.shiftKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229 || e.repeat) return;
    e.preventDefault();
    /* A toggle: the same chord is how you change your mind, since Escape is
     * one of the keys the mode exists to send. */
    if (armed) { disarmSend(false, '\ud0a4 \uc804\uc1a1 \ucde8\uc18c\ub428'); return; }
    armSend();
  });

  /* Capture phase, on the window, because this has to win against handlers
   * that are already bound to these exact keys and do not check whether the
   * event was cancelled -- the prompt box submits on Enter and sends a Tab of
   * its own, the digits switch session, Escape closes the sheet. Stopping the
   * event dead here is the only thing they all respect. */
  window.addEventListener('keydown', function (e) {
    if (!armed) return;
    if (e.isComposing || e.keyCode === 229) return;   /* the IME's key */
    /* The modifier of a chord arrives as its own keydown; holding Shift to
     * reach a key is not a decision to cancel. */
    if (e.key === 'Shift' || e.key === 'Control' || e.key === 'Alt'
        || e.key === 'Meta' || e.key === 'CapsLock') return;
    /* A chord is not a key to send -- the reader has moved on to something
     * else. Stand down and let it through untouched. The one exception is the
     * arming chord itself: standing down here and letting it reach the
     * handler below would re-arm on the same press, and the toggle would
     * never turn anything off. */
    if (e.ctrlKey || e.metaKey || e.altKey) {
      if (!isArmChord(e)) disarmSend(true);
      return;
    }
    if (e.repeat) { e.preventDefault(); return; }

    var name = sendKeyName(e.key);
    e.preventDefault();
    e.stopImmediatePropagation();
    disarmSend(true);
    if (!name) {
      setStatus('\ubcf4\ub0bc \uc218 \uc5c6\ub294 \ud0a4\uc785\ub2c8\ub2e4 \u2014 \ucde8\uc18c\ub428', 'var(--con-warn)');
      return;
    }
    sendKey(name, (IS_MAC ? 'Cmd' : 'Ctrl') + '+. \u2192 ' + name);
  }, true);

  /* Alt-tabbing away with the console armed would leave the next key typed on
   * the way back going to a session nobody was looking at. */
  window.addEventListener('blur', function () { disarmSend(false, ''); });

  document.addEventListener('keyup', function (e) {
    if (!hintsVisible()) return;
    if (e.key === 'Control' || e.key === 'Meta' || e.key === 'Alt') hideHints();
  });

  /* Alt-tabbing away leaves the modifier "held" forever otherwise. */
  window.addEventListener('blur', hideHints);

  /* --- session search (Ctrl/Cmd+F) --------------------------------------- */

  /* The chips and the 1..9 digits both assume you can see the session you
   * want. With ~70 of them you usually cannot: the rail is a long scroll and
   * the tenth session onward has no shortcut at all. Ctrl+F is the key every
   * hand already reaches for to find something on a screen -- here it searches
   * the session list rather than the pane text, which is the thing you
   * actually want to jump to. Only while the console is open, so the browser's
   * own find still works on the dashboard grid.
   *
   * Matching is substring-first over the label, then the branch and full name,
   * and only then a subsequence ('cops' -> 'claude-ops') so a rough guess still
   * lands. Ranked, never filtered to nothing that a substring would have found.
   */

  /* Pure, so it can be tested without a DOM. */
  function matchSessions(list, query) {
    var q = String(query || '').trim().toLowerCase();
    if (!q) return list.slice();
    var scored = [];
    list.forEach(function (item, index) {
      /* The dashboard strips the shared claude_ prefix when it builds a label;
       * falling back to the raw name has to strip it too, or the fallback
       * behaves differently from every other row. Only the fallback -- a
       * project genuinely called claude-ops keeps its name. */
      var label = (item.label
        ? String(item.label)
        : String(item.name || '').replace(/^claude[_-]/, '')).toLowerCase();
      var branch = String(item.branch || '').toLowerCase();
      /* Every tmux session here is named claude_<something>, so matching the
       * raw name made 'c', 'cl', 'cla'... match all seventy of them. The
       * prefix carries no information; strip it before searching. */
      var name = String(item.name || '').toLowerCase().replace(/^claude[_-]/, '');
      /* What the session is working on -- the board's own description of it
       * and the last prompt it was given. The board's search box read these
       * too, and it is gone; a search that can only match the name cannot
       * find "the one where I was fixing the parser" the way that box could.
       * Scored below the name so a name match always wins the top row. */
      var work = String(item.hay || '').toLowerCase();
      var score = -1;
      if (label.indexOf(q) === 0) score = 0;
      else if (label.indexOf(q) !== -1) score = 1;
      else if (branch.indexOf(q) !== -1 || name.indexOf(q) !== -1) score = 2;
      else if (isSubsequence(q, label + ' ' + branch)) score = 3;
      else if (work.indexOf(q) !== -1) score = 4;
      if (score !== -1) scored.push({ item: item, score: score, index: index });
    });
    scored.sort(function (a, b) {
      return a.score - b.score || a.index - b.index;
    });
    return scored.map(function (s) { return s.item; });
  }

  function isSubsequence(needle, hay) {
    var i = 0;
    for (var j = 0; j < hay.length && i < needle.length; j++) {
      if (hay.charAt(j) === needle.charAt(i)) i++;
    }
    return i === needle.length;
  }

  /* `catalog` is a snapshot taken when the palette opens, and `sel` is a
   * session NAME rather than a row index.
   *
   * Both exist for the same reason. The list used to be rebuilt from the
   * live catalogue on every keystroke AND every arrow press, with the
   * selection kept as a number. The catalogue is sorted by pin, then state,
   * then recency -- so a session changing state re-sorts it -- and the
   * number pointed at whatever had landed in that slot by the time Enter was
   * pressed. Arrow down, a session finishes, press Enter, open a session you
   * were not looking at. Freezing membership and order for the few seconds
   * the palette is up, and naming the selection, removes the race; states
   * are still kept current in place (see syncPalette). */
  var search = { root: null, input: null, list: null, note: null, hits: [],
                 cursor: 0, catalog: null, sel: null, opener: null,
                 openerEl: null };

  function searchOpen() {
    return !!(search.root && search.root.style.display !== 'none');
  }

  function buildSearch() {
    if (search.root) return;
    /* The dots and the state words are styled by the console's stylesheet,
     * which used to be installed only when a console was built. Opened from
     * the board before any console existed, the palette's dots were empty
     * spans with no size at all -- the state signal simply was not there on
     * first use, which is the one use a new surface gets judged on. */
    injectStyle();

    var root = document.createElement('div');
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-label', '\uc138\uc158 \uac80\uc0c9');
    root.style.cssText = [
      'position:fixed', 'left:0', 'right:0', 'top:0', 'bottom:0', 'z-index:80',
      'display:none', 'flex-direction:column', 'align-items:center',
      'padding:calc(48px + env(safe-area-inset-top)) 12px 12px',
      'background:var(--con-overlay)',
      '-webkit-backdrop-filter:blur(3px)', 'backdrop-filter:blur(3px)',
    ].join(';');
    /* A click on the dimmed area closes, the way every palette does. */
    root.addEventListener('mousedown', function (e) {
      if (e.target === root) closeSearch();
    });

    var box = document.createElement('div');
    box.style.cssText = [
      'width:100%', 'max-width:520px', 'display:flex', 'flex-direction:column',
      'min-height:0', 'border-radius:12px', 'overflow:hidden',
      'background:var(--con-sheet)', 'border:1px solid var(--con-line)',
      'box-shadow:var(--con-shadow)',
    ].join(';');

    var input = document.createElement('input');
    input.type = 'text';
    input.setAttribute('aria-label', '\uc138\uc158 \uc774\ub984 \uac80\uc0c9');
    /* The highlight moves with the arrow keys but focus never leaves this
     * box, so without the combobox relationship there is nothing to announce
     * -- the selected row exists only as a colour. */
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'true');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', 'ctb-search-list');
    input.placeholder = '\uc138\uc158 \uac80\uc0c9 (\u2191\u2193 \uc120\ud0dd \u00b7 Enter \uc774\ub3d9 \u00b7 Esc \ub2eb\uae30)';
    input.style.cssText = [
      'width:100%', 'box-sizing:border-box', 'padding:12px 14px',
      'background:var(--con-well)', 'color:var(--con-text)', 'border:0',
      'border-bottom:1px solid var(--con-line)', 'outline:none',
      /* 16px keeps iOS from zooming the page in on focus. */
      'font-size:16px', "font-family:'JetBrains Mono',monospace",
    ].join(';');
    input.addEventListener('input', function () { searchNote(''); renderResults(); });
    input.addEventListener('keydown', onSearchKey);

    var list = document.createElement('div');
    list.id = 'ctb-search-list';
    list.setAttribute('role', 'listbox');
    list.setAttribute('aria-label', '\uac80\uc0c9 \uacb0\uacfc');
    list.style.cssText =
      'overflow-y:auto;overscroll-behavior:contain;' +
      'max-height:min(52vh,420px);-webkit-overflow-scrolling:touch;';
    list.addEventListener('click', function (e) {
      var row = e.target.closest && e.target.closest('[data-search-session]');
      if (row) pick(row.getAttribute('data-search-session'));
    });

    /* The palette's own voice. It used to borrow the console's status line,
     * which does not exist until a console has been built and is off screen
     * once one is closed -- so opened from the board, a refusal was silent.
     * A live region, because the thing it has to say arrives without the
     * user having moved. */
    var note = document.createElement('div');
    note.setAttribute('role', 'status');
    note.setAttribute('aria-live', 'polite');
    note.style.cssText =
      'display:none;padding:8px 14px;font-size:11px;font-weight:600;' +
      'color:var(--con-err);border-top:1px solid var(--con-line);';

    box.appendChild(input);
    box.appendChild(list);
    box.appendChild(note);
    search.note = note;
    root.appendChild(box);
    document.body.appendChild(root);
    search.root = root;
    search.input = input;
    search.list = list;
  }

  function openSearch() {
    /* The palette owns the keyboard while it is up, and closing it hands
     * focus to the prompt box. A menu left open underneath would then take
     * Enter as "send the draft" rather than "choose this quadrant". */
    closeQuadMenu();
    buildSearch();
    /* Where the caret was when this opened, so closing can give it back.
     * Opened from the board there is no prompt box to fall to, and focus
     * landed on <body> -- from where the board's own keys do nothing. */
    /* Not the node: the board rebuilds its grid on every update, so the card
     * that opened this is very often detached by the time it closes, and
     * focus() on a detached node silently does nothing -- leaving the board's
     * arrow keys and Enter dead with no visible reason. Remember WHICH
     * session it was and find it again. */
    var from = document.activeElement;
    search.opener = (from && from.getAttribute
                     && from.getAttribute('data-session-name')) || null;
    search.openerEl = from;
    search.catalog = sessionCatalog().slice();
    search.sel = null;
    searchNote('');
    search.root.style.display = 'flex';
    search.input.value = '';
    search.cursor = 0;
    renderResults();
    search.input.focus();
  }

  function searchNote(text) {
    if (!search.note) return;
    search.note.textContent = text || '';
    search.note.style.display = text ? 'block' : 'none';
  }

  function closeSearch() {
    if (!search.root) return;
    search.root.style.display = 'none';
    search.catalog = null;
    /* Give the caret back to the box the user was typing in -- unless the
     * find bar is up, where the caret belongs to the query. */
    if (findOpen()) { fnd.input.focus(); return; }
    if (el.input && state.session) { el.input.focus(); return; }
    var name = search.opener;
    var node = search.openerEl;
    search.opener = null;
    search.openerEl = null;
    /* focus() on a node that is not displayed is a no-op that reports
     * nothing, and the board hides cards its age filter has aged out -- so
     * "did it land" has to be asked, not assumed. Otherwise Escape leaves the
     * caret nowhere and the board's arrows and Enter are dead. */
    if (name) {
      var card = document.querySelector('[data-session-name="' + name + '"]');
      if (card && card.focus) { card.focus(); if (document.activeElement === card) return; }
    }
    if (node && node !== document.body && document.contains(node) && node.focus) {
      node.focus();
      if (document.activeElement === node) return;
    }
    /* Nothing to go back to: the button that opens this is always there. */
    var launcher = document.getElementById('btn-find-session');
    if (launcher && launcher.focus) launcher.focus();
  }

  /* What the palette lists, and in what order.
   *
   * ORDER comes from the snapshot taken when it opened, so the list cannot
   * rearrange itself between a keystroke and the Enter that follows it.
   * MEMBERSHIP is reconciled here, not frozen: a palette opened while the
   * board was still loading would otherwise say "no sessions" forever, and a
   * session started while it is up would be permanently unfindable without
   * closing and reopening. New names go on the end, where they cannot move a
   * row that is already on screen -- the same rule the rail follows.
   * STATE is never taken from the snapshot; see stateOf(). A snapshot's idea
   * of what a session is doing is exactly as old as the snapshot, and typing
   * one more letter used to bring those stale words back. */
  function searchSource() {
    var live = sessionCatalog();
    if (!search.catalog) return live;
    var have = {};
    for (var i = 0; i < search.catalog.length; i++) have[search.catalog[i].name] = true;
    for (var j = 0; j < live.length; j++) {
      if (!have[live[j].name]) search.catalog.push(live[j]);
    }
    return search.catalog;
  }

  /* The current state of every session, by name. Built once per render
   * rather than scanned once per row: seventy sessions and a row-by-row
   * scan is a square, and this runs on every keystroke in the box. */
  function liveStates() {
    var map = {};
    var live = sessionCatalog();
    for (var i = 0; i < live.length; i++) map[live[i].name] = live[i].state;
    return map;
  }

  function makeRow(item, i, live) {
    var row = document.createElement('div');
    row.id = 'ctb-search-opt-' + i;
    row.setAttribute('data-search-session', item.name);
    row.setAttribute('role', 'option');
    row.style.cssText = [
      'display:flex', 'align-items:center', 'gap:8px',
      'padding:9px 14px', 'cursor:pointer',
      "font-family:'JetBrains Mono',monospace", 'font-size:12px',
    ].join(';');

    var now = live[item.name] || null;
    row.appendChild(makeDot(now || 'idle'));

    var text = document.createElement('span');
    text.style.cssText =
      'flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
    text.textContent = item.branch
      ? item.label + ' \u2387' + item.branch : item.label;
    row.appendChild(text);

    if (item.name === state.session) {
      var here = document.createElement('span');
      here.textContent = '\ud604\uc7ac';
      here.setAttribute('aria-hidden', 'true');
      here.style.cssText =
        'font-size:10px;color:var(--con-info);flex-shrink:0;';
      row.appendChild(here);
    }

    /* The word, last and in a lane of its own, so the eye can run straight
     * down it: every row says what that session is doing, in the same place,
     * whatever the name in front of it is. */
    row.appendChild(makeStateLabel(now || 'idle'));

    paintRowWho(row, item);
    if (now) paintRowState(row, stateText(now));
    else markRowGone(row);
    paintRow(row, false);
    return row;
  }

  function renderResults() {
    search.hits = matchSessions(searchSource(), search.input.value);
    /* The selection is a name; the cursor is wherever that name landed after
     * the query narrowed the list. A selection the query filtered out falls
     * back to the top, which is what the eye expects while typing. */
    var idx = -1;
    if (search.sel) {
      for (var k = 0; k < search.hits.length; k++) {
        if (search.hits[k].name === search.sel) { idx = k; break; }
      }
    }
    search.cursor = idx === -1 ? 0 : idx;
    search.sel = search.hits.length ? search.hits[search.cursor].name : null;
    search.list.textContent = '';

    if (!search.hits.length) {
      search.input.removeAttribute('aria-activedescendant');
      var empty = document.createElement('div');
      empty.setAttribute('data-search-empty', '');
      empty.textContent = '\uc77c\uce58\ud558\ub294 \uc138\uc158 \uc5c6\uc74c';
      empty.style.cssText =
        'padding:14px;color:var(--con-dim);font-size:12px;text-align:center;';
      search.list.appendChild(empty);
      return;
    }

    var live = liveStates();
    search.hits.forEach(function (item, i) {
      var row = makeRow(item, i, live);
      paintRow(row, i === search.cursor);
      search.list.appendChild(row);
    });
    scrollSelectionIntoView();
  }

  /* Who the row is, kept on the row itself. The state part is rewritten
   * whenever the session changes, and reassembling the name by cutting the
   * old label at a comma loses whatever else was in it. */
  function paintRowWho(row, item) {
    var who = item.branch ? item.label + ' \uc6cc\ud06c\ud2b8\ub9ac ' + item.branch : item.label;
    if (item.name === state.session) who += ', \ud604\uc7ac \uc5f4\ub9b0 \uc138\uc158';
    row.setAttribute('data-who', who);
  }

  /* A session that has ended is dimmed and named, not deleted: the row you
   * are pointing at must not vanish as you reach for it, and a list that
   * shortens under the cursor moves every choice below it. */
  function markRowGone(row) {
    row.setAttribute('data-gone', '');
    row.style.opacity = '0.45';
    var dot = row.querySelector('.ctb-sdot');
    var lab = row.querySelector('.ctb-slabel');
    if (dot) paintDot(dot, 'idle');
    if (lab) {
      lab.textContent = '\uc885\ub8cc\ub428';
      lab.style.color = 'var(--con-dim)';
      lab.style.opacity = '1';
    }
    paintRowState(row, '\uc885\ub8cc\ub428');
  }

  function paintRowState(row, word) {
    row.setAttribute('aria-label', (row.getAttribute('data-who') || '') + ', ' + word);
  }

  function paintRow(row, active) {
    row.style.color = active ? 'var(--con-text)' : 'var(--con-muted)';
    row.style.background = active ? 'var(--con-active)' : 'transparent';
    if (active) row.setAttribute('aria-selected', 'true');
    else row.setAttribute('aria-selected', 'false');
  }

  /* Moving the highlight repaints two rows. It does NOT rebuild the list:
   * rebuilding restarts every row's animation, throws away the node under a
   * finger mid-tap, and used to re-read a catalogue that could have re-sorted
   * since the palette opened. */
  function moveSelection(step) {
    if (!search.hits.length) return;
    var rows = search.list.querySelectorAll('[data-search-session]');
    var from = search.cursor;
    search.cursor = (search.cursor + step + search.hits.length) % search.hits.length;
    search.sel = search.hits[search.cursor].name;
    if (rows[from]) paintRow(rows[from], false);
    if (rows[search.cursor]) paintRow(rows[search.cursor], true);
    scrollSelectionIntoView();
  }

  function scrollSelectionIntoView() {
    var row = search.list.querySelector('#ctb-search-opt-' + search.cursor);
    if (!row) return;
    search.input.setAttribute('aria-activedescendant', row.id);
    if (row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
  }

  /* Sessions that have appeared since the list was drawn, added to the end
   * of it. Not a redraw: replacing every row while the palette is up throws
   * away the row under a finger mid-tap and scrolls back to the keyboard
   * selection, and a newcomer that does not even match what is typed would
   * have done both for nothing. Late arrivals land at the bottom rather than
   * in the place a fresh search would have put them -- the list stays where
   * the eye left it, which is worth more here than perfect ranking. */
  function appendNewRows() {
    var rendered = {};
    for (var i = 0; i < search.hits.length; i++) rendered[search.hits[i].name] = true;
    var src = searchSource();
    var q = search.input.value;
    var live = liveStates();
    for (var j = 0; j < src.length; j++) {
      var item = src[j];
      if (rendered[item.name]) continue;
      if (!matchSessions([item], q).length) continue;
      search.list.appendChild(makeRow(item, search.hits.length, live));
      search.hits.push(item);
    }
    if (!search.hits.length) return;
    /* The empty-state line is not a row, and it has to go once there is one. */
    var empty = search.list.querySelector('[data-search-empty]');
    if (empty) {
      empty.parentNode.removeChild(empty);
      search.sel = search.hits[0].name;
      search.cursor = 0;
      paintRow(search.list.querySelector('[data-search-session]'), true);
      scrollSelectionIntoView();
    }
  }

  /* New data while the palette is up. Existing rows keep their places and
   * their identities -- only the dot, the word and the accessible name
   * change -- so a search cannot re-sort itself out from under the Enter
   * key; sessions that have appeared since are added to the end. A session
   * that ended is marked rather than removed, for the same reason: the row
   * you are pointing at must not vanish as you reach for it. */
  function syncPalette(flash) {
    if (!searchOpen() || !search.catalog) return;
    /* Membership first. Patching rows cannot show a session that has no row,
     * so a palette opened before the board had data sat on "일치하는 세션
     * 없음" until the user typed another letter -- the arrival of the very
     * thing it was waiting for changed nothing on screen. searchSource()
     * folds new names onto the end of the frozen order; if it grew, the list
     * is redrawn, which keeps every existing row where it was and keeps the
     * selection, because the selection is a name. */
    appendNewRows();
    var map = catalogMap();
    var rows = search.list.querySelectorAll('[data-search-session]');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var name = row.getAttribute('data-search-session');
      var live = map[name];
      var dot = row.querySelector('.ctb-sdot');
      var lab = row.querySelector('.ctb-slabel');
      if (!live) { markRowGone(row); continue; }
      row.removeAttribute('data-gone');
      row.style.opacity = '';
      if (dot) paintDot(dot, live.state);
      if (lab) paintStateLabel(lab, live.state);
      /* The row keeps the name it was drawn with; only the word changes. */
      paintRowState(row, stateText(live.state));
      if (flash && flash[name]) flashElement(row, live.state);
    }
  }

  function onSearchKey(e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      moveSelection(e.key === 'ArrowDown' ? 1 : -1);
      return;
    }
    if (e.key === 'Enter') {
      /* Mid-Hangul the Enter belongs to the IME: it is confirming the
       * syllable being typed, not choosing a session. Taking it here opened
       * whatever was highlighted while the user was still writing the query
       * -- the same guard the console's other key handlers already carry. */
      if (e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      var hit = search.hits[search.cursor];
      if (hit) pick(hit.name);
      return;
    }
    if (e.key === 'Tab') {
      /* Modal: there is nowhere to tab to. Without this the caret left for
       * whatever sits behind the z-80 overlay, and the palette stayed up with
       * its arrows, its Enter and its typing all dead. */
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      /* The sheet's own Escape handler is on the document and would close the
       * console behind the palette in the same keystroke. */
      e.stopPropagation();
      closeSearch();
    }
  }

  function pick(name) {
    /* The list is a snapshot; a session in it can have ended since it was
     * taken. Opening one is a console that sits on a pane which will never
     * answer, so say so and stay put -- with the list repainted, the row now
     * reads 종료됨 and the next choice is an informed one. */
    if (name && !inCatalog(name)) {
      syncPalette();
      searchNote('\uadf8 \uc138\uc158\uc740 \uc885\ub8cc\ub418\uc5c8\uc2b5\ub2c8\ub2e4');
      /* A click lands on a row, which is not focusable, so focus fell to the
       * dialog and the arrows, the typing and Escape all stopped working --
       * on a board with no console there is no other Escape handler to get
       * out with either. Refusing has to hand the keyboard back. */
      if (search.input) search.input.focus();
      return;
    }
    closeSearch();
    if (!name || name === state.session) return;
    /* Picked from the board in the VSCode webview: bring that session's
     * terminal up instead of opening a console that is read-only there --
     * the same rule the digit shortcuts and the rail walk follow. */
    if (!state.session && IS_VSCODE && window.ctbFocusSession
        && window.ctbFocusSession(name)) return;
    show(name, true);
  }

  document.addEventListener('keydown', function (e) {
    /* The board has no search box of its own: the one search is this palette,
     * which answers "which session" and hands you its console with the caret
     * already in the prompt -- the same move as finding a session in the
     * terminal. The board's own F/Ctrl+F comes through here too. */
    /* Not keysTaken(): this handler deliberately claims the chord while its
     * own palette is up (see below), and standing down for searchOpen() here
     * handed the second press to the browser's find bar. Only the sheet in
     * front of everything makes it let go. */
    if (sheetOpen()) return;
    if (e.key !== 'f' && e.key !== 'F') return;
    if (!(IS_MAC ? e.metaKey : e.ctrlKey) || e.shiftKey || e.altKey) return;
    /* Claimed before the already-open check: letting the second press through
     * opened the browser's own find bar on top of the palette, and typing then
     * went to whichever box the browser felt like. */
    e.preventDefault();
    if (searchOpen()) { search.input.focus(); search.input.select(); return; }
    hideHints();
    fetchOrder();
    openSearch();
  });

  /* --- status line ------------------------------------------------------- */

  /* The colour names the outcome and picks the glyph: ok → check, warn →
   * triangle, err → cross, anything else → a quiet dot for "in progress". */
  var STATUS_ICON = {
    'var(--con-ok)': 'check', 'var(--con-warn)': 'alert', 'var(--con-err)': 'close',
  };
  function setStatus(text, color) {
    if (!el.status) return;
    el.status.textContent = '';
    if (!text) { el.status.style.visibility = 'hidden'; return; }
    var name = STATUS_ICON[color] || 'dot';
    el.status.appendChild(icon(name, 15));
    el.status.appendChild(document.createTextNode(text));
    el.status.style.visibility = 'visible';
    el.status.style.color = color || 'var(--con-muted)';
  }

  /* Ctrl+U — the kill-line every terminal has, and the same key the ⌧ 입력
   * 지우기 button sends. The browser spends it on view-source, which is never
   * what terminal fingers meant over an open console, so it is taken here.
   *
   * Where it lands follows where the half-typed line actually is: with the
   * prompt box focused and holding text, that box IS the line, so it clears
   * the draft (the browser does nothing there natively anyway); anywhere else
   * over the console the line is in the pane, so C-u goes to tmux. Ctrl on a
   * Mac too, not Cmd: the kill-line there is Ctrl+U as well. */
  document.addEventListener('keydown', function (e) {
    if (!state.session || keysTaken()) return;
    if (e.key !== 'u' && e.key !== 'U') return;
    if (!e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    /* Held down, the OS repeats this at 30 a second, and every one of them
     * is a request to tmux. One press, one kill-line. */
    if (e.repeat) return;
    e.preventDefault();
    if (el.input && e.target === el.input && el.input.value) {
      el.input.value = '';
      delete state.drafts[state.session];
      saveDrafts();
      setStatus('입력 지움', 'var(--con-muted)');
      return;
    }
    sendKey('C-u', 'Ctrl+U');
  });

  /* --- tail ------------------------------------------------------------- */

  function copyText(text, okLabel) {
    if (!text) return;

    /* The dashboard is served over plain http on the tailnet, where
     * navigator.clipboard does not exist (secure-context only). The legacy
     * textarea + execCommand path is the one that actually works here; the
     * async API is tried first for any future https deployment. */
    function report(ok) {
      setStatus(ok ? okLabel : '\ubcf5\uc0ac \uc2e4\ud328 \u2014 \uae38\uac8c \ub20c\ub7ec \uc9c1\uc811 \uc120\ud0dd\ud558\uc138\uc694',
                ok ? 'var(--con-ok)' : 'var(--con-warn)');
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { report(true); },
        function () { report(legacyCopy(text)); }
      );
      return;
    }
    report(legacyCopy(text));
  }

  function copyTail() {
    copyText(state.lines ? cleanLines(state.lines.slice()) : '',
             '\ud654\uba74 \ub0b4\uc6a9 \ubcf5\uc0ac\ub428');
  }

  function legacyCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    /* Keep it on-screen but invisible: iOS refuses to copy from elements it
     * considers hidden (display:none / off-viewport can both fail). */
    ta.style.cssText = 'position:fixed;top:0;left:0;width:2em;height:2em;opacity:0;border:none;';
    document.body.appendChild(ta);
    var ok = false;
    try {
      ta.focus();
      ta.setSelectionRange(0, ta.value.length);
      ok = document.execCommand('copy');
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  /* --- line rendering + tap range ---------------------------------------- */

  /* Terminal text carries two kinds of contamination that would otherwise
   * survive into the clipboard: Claude Code indents its output by two columns,
   * and tmux pads every line out to the pane width. Pasting Python or YAML
   * with a spurious global indent actually breaks it, so strip the padding and
   * remove the common indent while keeping relative structure. */
  function cleanLines(lines) {
    var out = lines.map(function (l) { return l.replace(/\s+$/, ''); });
    while (out.length && !out[0].trim()) out.shift();
    while (out.length && !out[out.length - 1].trim()) out.pop();
    if (!out.length) return '';

    var indent = Infinity;
    out.forEach(function (l) {
      if (!l.trim()) return;
      indent = Math.min(indent, l.match(/^ */)[0].length);
    });
    if (indent > 0 && indent !== Infinity) {
      out = out.map(function (l) { return l.slice(indent); });
    }
    return out.join('\n');
  }

  /* A URL in the pane is a dead string otherwise: the terminal it came from
   * offers Ctrl+click, this box offered nothing, and the only way to follow an
   * artifact link was to select it by hand and paste it into the address bar.
   *
   * Trailing punctuation is prose, not the address -- '...see http://x/y.' --
   * so it is trimmed off. A closing bracket is kept only when the URL opened
   * one itself, which is what a wiki-style path needs. */
  /* What may appear in an address, per RFC 3986 -- a whitelist, because the
   * blacklist this replaces only excluded box drawing (U+2500-257F) and so let
   * every other glyph the terminal paints beside a link run into the href:
   * Claude Code's own gutter ▎ (U+258E) is outside that range, as are • and →.
   * A host is required, so a bare 'https://' at the end of a sentence is text.
   *
   * Unicode domains are not linked. That is the safe half of a real tradeoff:
   * they cannot be told apart from an ordinary CJK word running into a URL, and
   * a homograph that looks like a familiar host is exactly what should not be
   * one click away from a pane whose contents nobody audited.
   *
   * The apostrophe stays in, as RFC 3986 has it. In 151 URLs captured from
   * live panes every apostrophe beside a link was the closing quote of a shell
   * argument -- and trimUrl already takes a trailing quote off, which is where
   * all of them were. Excluding it here as well would change nothing. */
  var URL_CHARS = "A-Za-z0-9\\-._~:/?#\\[\\]@!$&'()*+,;=%";
  var URL_RE = new RegExp('https?://[' + URL_CHARS + ']*[A-Za-z0-9]['
                          + URL_CHARS + ']*', 'g');

  /* A continuation is Claude Code's left gutter -- ▎, which it draws down the
   * side of its output -- and then more address. The glyph is the whole
   * signal, and it is required.
   *
   * ▎ only. │ was in here too and is not a gutter: of 485 rows in a 26k-row
   * sample that start with one of the two, 465 start with │ and every one of
   * them is a box border or a table rule. 426 of those sit directly under an
   * exactly-full row, which is the entire glue setup -- and removing │ costs
   * nothing measurable, since the one real join in that sample uses ▎.
   *
   * Measured over 26k rows of live panes. Continuing at column 0, which is
   * what a bare terminal wrap looks like, fires ZERO times: Claude Code always
   * writes its gutter first, and a shell's own wrapping is rejoined by
   * capture-pane -J long before it reaches here. Every glue candidate, on the
   * other hand -- a full row ending in a URL, followed by an ordinary next
   * line -- begins either at column 0 or with plain indentation. So the loose
   * rules cost wrong links and buy nothing measurable, while the strict one
   * fires exactly once in that sample: on a genuinely wrapped artifact link. */
  var GUTTER_RE = /^ ?\u258e ?/;

  /* -> {start, text} for the part of `line` that continues an address, or null.
   * start is where the address resumes, so the gutter is not part of the href
   * and not painted as a link. */
  function continuationOf(line) {
    var gutter = GUTTER_RE.exec(line);
    if (!gutter) return null;
    var rest = new RegExp('^[' + URL_CHARS + ']+').exec(line.slice(gutter[0].length));
    if (!rest) return null;
    return { start: gutter[0].length, text: rest[0] };
  }

  /* How many columns a row occupies -- which is what "filled to the last
   * column" has to mean. JS string length counts UTF-16 units: a Korean row is
   * half its own width by that measure and an emoji is double-counted, so 998
   * genuinely full rows in a 26k-row sample were invisible to a length test.
   * Wide (W/F) is two columns, a combining mark or zero-width joiner is none,
   * and everything else is one -- the same rule tmux itself lays out with. */
  var WIDE = [
    [0x1100, 0x115f], [0x2e80, 0x303e], [0x3041, 0x33ff], [0x3400, 0x4dbf],
    [0x4e00, 0x9fff], [0xa000, 0xa4cf], [0xa960, 0xa97f], [0xac00, 0xd7a3],
    [0xf900, 0xfaff], [0xfe10, 0xfe19], [0xfe30, 0xfe6f], [0xff00, 0xff60],
    [0xffe0, 0xffe6], [0x1f300, 0x1f64f], [0x1f900, 0x1f9ff],
    [0x20000, 0x2fffd], [0x30000, 0x3fffd],
  ];
  /* Zero-width is the direction that has to be right. Under-counting a row can
   * only fail to recognise it as full, which loses a rejoin; over-counting one
   * -- a combining mark or a conjoining jamo billed as a column -- makes a row
   * that is NOT full measure as full, and that is what invents a link or drops
   * a good one. So the marks are enumerated, and the emoji presentation
   * selector's widening effect (⚠ is one column, ⚠️ is two) is knowingly left
   * out: it errs the safe way. */
  var ZERO = [
    [0x0300, 0x036f],    /* combining diacritics -- a decomposed 'á' */
    [0x0483, 0x0489], [0x0591, 0x05bd], [0x0610, 0x061a], [0x064b, 0x065f],
    [0x1160, 0x11ff],    /* conjoining Hangul jamo -- decomposed Korean */
    [0x200b, 0x200f], [0x2060, 0x2064], [0x20d0, 0x20ff],
    [0xfe00, 0xfe0f], [0xfe20, 0xfe2f],
  ];

  function inRanges(cp, ranges) {
    for (var i = 0; i < ranges.length; i++) {
      if (cp >= ranges[i][0] && cp <= ranges[i][1]) return true;
    }
    return false;
  }

  function displayWidth(text) {
    var w = 0;
    for (var i = 0; i < text.length; i++) {
      var cp = text.codePointAt(i);
      if (cp > 0xffff) i++;            /* surrogate pair: one code point */
      if (inRanges(cp, ZERO)) continue;
      w += inRanges(cp, WIDE) ? 2 : 1;
    }
    return w;
  }

  /* A character that means the match stopped short of the real end of the
   * address rather than at it. Two UTF-16 units are handed to it, not one, so
   * a letter outside the basic plane is seen whole; a combining mark counts
   * too, since a decomposed 'á' would otherwise truncate the href at the 'a'. Built at load: an engine too old for Unicode
   * property escapes gets a regex that matches nothing, which links the
   * truncated form -- the behaviour before this check, not a crash. */
  var CUT_RE;
  try {
    CUT_RE = new RegExp('^[\\p{L}\\p{N}\\p{M}]', 'u');
  } catch (e) {
    CUT_RE = /(?!)/;
  }

  function trimUrl(url) {
    var out = url.replace(/[.,;:!?'"“”‘’]+$/, '');
    while (/[)\]}]$/.test(out)) {
      var close = out.charAt(out.length - 1);
      var open = close === ')' ? '(' : (close === ']' ? '[' : '{');
      var depth = 0;
      for (var i = 0; i < out.length; i++) {
        if (out.charAt(i) === open) depth++;
        else if (out.charAt(i) === close) depth--;
      }
      if (depth >= 0) break;   /* the bracket belongs to the URL */
      out = out.slice(0, -1);
    }
    return out;
  }

  /* Rejoining what tmux broke.
   *
   * A pane has no soft wrap: a line longer than the pane is stored as two
   * rows, and capture-pane hands them over with nothing marking the seam. A
   * link long enough to wrap -- which is most artifact URLs on a phone --
   * therefore arrived as two half-links, neither of them followable.
   *
   * The seam has a signature, and it has to be narrow, because the shape it
   * resembles is everywhere: a log line ending in a URL, followed by the next
   * log line. So two conditions, together. The row must be filled to its last
   * column -- the pane width, which the server reports, since capture-pane -J
   * trims the padding that would otherwise show it -- and the next row must
   * begin at column 0, no indent, with more URL characters. Claude Code
   * indents its own wrapped output by two columns and so never qualifies; only
   * a break the terminal made at the margin does.
   *
   * Without a width (an older server, a session tmux will not describe) nothing
   * is joined. A missing link is a nuisance; a link silently glued to the next
   * line's timestamp is a wrong address that looks right.
   *
   * The joined address is one link, but it is drawn as one anchor per row, so
   * the rows stay the rows: line tap-to-select, the copy range, and the
   * scroll anchoring all still count in lines and know nothing about this.
   *
   * -> one array of {text, url} segments per input line. Pure; tested. */
  function linkifyLines(lines, cols) {
    var marks = lines.map(function () { return []; });
    var width = cols > 0 ? cols : 0;   /* 0 = unknown: join nothing */

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      URL_RE.lastIndex = 0;
      var m;
      while ((m = URL_RE.exec(line)) !== null) {
        /* A letter or digit right after the match means the address did not
         * end there -- the whitelist simply cannot spell the next character.
         * A Korean path (…/가나) would otherwise link as …/ : a different
         * page, silently, which is worse than no link at all. A symbol next
         * door is a different matter -- ▎ • → │ are what the terminal paints
         * beside a link, not part of one -- so those still link. */
        if (CUT_RE.test(line.slice(m.index + m[0].length,
                                   m.index + m[0].length + 2))) {
          URL_RE.lastIndex = m.index + m[0].length;
          continue;
        }
        var pieces = [{ line: i, start: m.index, end: m.index + m[0].length }];
        var full = m[0];
        var row = i;
        /* Judged on the address, not on what follows it: a row reaching the
         * margin only because of a shell's closing ')' has not run off the
         * edge -- trimUrl is about to drop that character anyway -- and
         * treating it as cut threw away a complete, working link. */
        var endsFlush = !!width && displayWidth(line) === width
                        && pieces[0].end === line.length
                        && trimUrl(m[0]).length === m[0].length;

        while (endsFlush && row + 1 < lines.length) {
          var cont = continuationOf(lines[row + 1]);
          if (!cont) break;
          row += 1;
          pieces.push({ line: row, start: cont.start,
                        end: cont.start + cont.text.length });
          full += cont.text;
          endsFlush = displayWidth(lines[row]) === width
                      && cont.start + cont.text.length === lines[row].length;
        }

        /* Still flush after the search means the address ran off the last row
         * we were given and the rest of it is not here: the continuation
         * scrolled out of the window, or was written at a different pane
         * width, or the pane has been widened since. Linking the half we have
         * would point at a real but different page -- the same silent
         * substitution a Korean path produced, and the same answer. */
        if (endsFlush) {
          URL_RE.lastIndex = m.index + m[0].length;
          continue;
        }

        /* Trim the prose punctuation off the tail, giving back whatever rows
         * that empties -- a row holding nothing but a full stop is text. */
        var drop = full.length - trimUrl(full).length;
        while (drop > 0 && pieces.length) {
          var last = pieces[pieces.length - 1];
          var span = last.end - last.start;
          if (drop >= span) { pieces.pop(); drop -= span; }
          else { last.end -= drop; drop = 0; }
        }

        var url = trimUrl(full);
        if (url && pieces.length) {
          pieces.forEach(function (pc) {
            marks[pc.line].push({ start: pc.start, end: pc.end, url: url });
          });
        }

        /* Resume after whatever was consumed on THIS row. A continuation row
         * is scanned again on its own turn; anything it finds inside a span
         * already claimed by the joined link is dropped by toSegments, which
         * is the one place that keeps a row's marks from overlapping. */
        if (row !== i) break;
        URL_RE.lastIndex = Math.max(m.index + 1,
                                    pieces.length ? pieces[0].end : m.index + m[0].length);
      }
    }

    return lines.map(function (line, i) { return toSegments(line, marks[i]); });
  }

  function toSegments(line, marks) {
    var out = [];
    var last = 0;
    marks.sort(function (a, b) { return a.start - b.start; });
    marks.forEach(function (mk) {
      if (mk.start < last) return;          /* overlap: first one wins */
      if (mk.start > last) out.push({ text: line.slice(last, mk.start), url: null });
      out.push({ text: line.slice(mk.start, mk.end), url: mk.url });
      last = mk.end;
    });
    if (last < line.length) out.push({ text: line.slice(last), url: null });
    if (!out.length) out.push({ text: line, url: null });
    return out;
  }

  /* One line on its own -- the shape the tests and the single-line case use. */
  function splitLinks(line) {
    return linkifyLines([line], 0)[0];
  }

  /* Which line is the box you type into, and is something sitting in it.
   *
   * Claude Code prefills its own input -- a command it is proposing, left
   * there for you to press Enter on. Seen through this console, hours later,
   * that is indistinguishable from something you typed and forgot to send,
   * and pressing Enter on the wrong one of those is not recoverable.
   *
   * The input box has a shape: a horizontal rule, the ❯ line, a horizontal
   * rule. A menu has the same ❯ -- it is the selection cursor too -- but its
   * siblings are ordinary lines and there is no rule above it. That
   * distinction is the whole test, and it is what keeps "❯ No, exit" on a
   * trust prompt from being painted as unsent input.
   *
   * A box can hold several lines: the ❯ line, then continuation lines
   * indented under it, down to the rule below. All of them are the input,
   * so all of them are marked. -> {index, end, text} or null. Pure; tested. */
  var PROMPT_RE = /^[\s\u00a0]*\u276f[\s\u00a0]*(.*)$/;
  var RULE_RE = /^[\s\u00a0]*[\u2500-\u257f]{10,}[\s\u00a0]*$/;

  function findPendingInput(lines) {
    /* From the bottom: the input box is the last thing drawn. Bounded, so a
     * deep scrollback does not get walked on every render. */
    var floor = Math.max(0, lines.length - 40);
    for (var i = lines.length - 1; i >= floor; i--) {
      var m = PROMPT_RE.exec(lines[i]);
      if (!m) continue;
      var text = m[1].replace(/[\s\u00a0]+$/, '');
      if (!text) return null;          /* an empty box is not pending input */
      /* The rule above, skipping nothing -- the box is drawn tight. */
      if (i === 0 || !RULE_RE.test(lines[i - 1])) return null;
      /* Continuation lines run to the rule below. Without one in reach the
       * box is cut off at the bottom of the capture: mark the ❯ line only. */
      var end = i;
      var parts = [text];
      for (var j = i + 1; j < lines.length && j <= i + 12; j++) {
        if (RULE_RE.test(lines[j])) {
          end = j - 1;
          for (var k = i + 1; k <= end; k++) parts.push(lines[k].replace(/^[\s\u00a0]+|[\s\u00a0]+$/g, ''));
          break;
        }
      }
      return { index: i, end: end, text: parts.join('\n') };
    }
    return null;
  }

  /* The last prompt the user actually submitted, for pulling back in after an
   * Escape. Submitted prompts are drawn flush left; the input box and the
   * menus ("\u276f No, exit") are drawn inside a frame, indented and under a
   * rule -- so column zero plus no rule above is what separates them.
   * Wrapped tails are the indented lines that follow, to the first blank.
   * Pure; tested. */
  /* One line, one question: is line `i` a prompt the user submitted? Column
   * zero, something after the \u276f, and no rule above it. Both readers of
   * this -- recall and the jump-back pill -- must agree on what a turn
   * boundary is, so there is one copy of the test. Pure; tested. */
  function isSubmitted(lines, i) {
    if (lines[i].charAt(0) !== '\u276f') return false;
    if (!lines[i].slice(1).replace(/^[\s\u00a0]+|[\s\u00a0]+$/g, '')) return false;
    return !(i > 0 && RULE_RE.test(lines[i - 1]));        /* that is the box */
  }

  /* Every submitted prompt, top to bottom, as line indices. Pure; tested. */
  function submittedLines(lines) {
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      if (isSubmitted(lines, i)) out.push(i);
    }
    return out;
  }

  function findLastSubmitted(lines) {
    for (var i = lines.length - 1; i >= 0; i--) {
      if (!isSubmitted(lines, i)) continue;
      var text = lines[i].slice(1).replace(/^[\s\u00a0]+|[\s\u00a0]+$/g, '');
      var parts = [text];
      for (var j = i + 1; j < lines.length; j++) {
        if (!/^[\s\u00a0]{2,}\S/.test(lines[j])) break;
        parts.push(lines[j].replace(/^[\s\u00a0]+|[\s\u00a0]+$/g, ''));
      }
      return parts.join(' ');
    }
    return '';
  }

  /* Replaces the box rather than appending: this is "let me edit that one",
   * not "add to what I am writing". A draft already in the box would be lost,
   * so it is kept in front of the recalled text instead. */
  function recallLast() {
    if (!state.session || !el.input) return;
    var pending = state.pending;
    if (pending && pending.text && !state.ghost) {
      putRecalled(pending.text);
      sendKey('C-u', '\uc785\ub825 \uc625\uae30\uae30');
      setStatus('\uc138\uc158 \uc785\ub825\ucc3d\uc5d0\uc11c \uc637\uaca8\uc654\uc2b5\ub2c8\ub2e4 \u00b7 \uc218\uc815 \ud6c4 Enter', 'var(--con-ok)');
      return;
    }
    var last = findLastSubmitted(state.lines || []);
    if (!last) { setStatus('\uac00\uc838\uc62c \uc694\uccad\uc774 \uc5c6\uc2b5\ub2c8\ub2e4', 'var(--con-warn)'); return; }
    putRecalled(last);
    setStatus('\ub9c8\uc9c0\ub9c9 \uc694\uccad\uc744 \uac00\uc838\uc654\uc2b5\ub2c8\ub2e4 \u00b7 \uc218\uc815 \ud6c4 Enter', 'var(--con-ok)');
  }

  function putRecalled(text) {
    var box = el.input;
    var kept = box.value.trim();
    box.value = kept ? kept + '\n' + text : text;
    var caret = box.value.length;
    try { box.setSelectionRange(caret, caret); } catch (e) { /* not focusable yet */ }
    if (state.session) { state.drafts[state.session] = box.value; saveDrafts(); }
    box.classList.remove('con-flash');
    void box.offsetWidth;
    box.classList.add('con-flash');
    box.focus();
  }

  /* --- key pad fit ------------------------------------------------------
   *
   * The pad wraps, so its height is decided by the phone rather than by us:
   * on an iPhone 12 the seventeenth key tipped it from two rows to three,
   * and the third row comes straight out of the pane the console exists to
   * show. Rather than tuning key sizes until it happens to fit one device,
   * the rows are counted from measured widths and the lowest-priority keys
   * are folded away until it fits, with one ⋯ key left to unfold them.
   *
   * How many rows this many keys of these widths need in this much space,
   * laid out the way flex-wrap lays them out. Pure; tested. */
  function rowsNeeded(widths, gap, trayWidth) {
    if (!(trayWidth > 0)) return 1;
    var rows = 1;
    var x = 0;
    for (var i = 0; i < widths.length; i++) {
      var w = widths[i];
      if (x === 0) { x = w; continue; }
      if (x + gap + w > trayWidth + 0.5) { rows++; x = w; }
      else x += gap + w;
    }
    return rows;
  }

  /* Which keys to fold away so the pad fits maxRows. Keys are dropped from
   * the lowest priority up, and once anything is dropped the ⋯ key needs a
   * slot of its own, so its width joins the calculation. Returns the indices
   * to hide, lowest priority first. Pure; tested. */
  function planKeys(widths, prios, gap, trayWidth, maxRows, moreWidth) {
    if (rowsNeeded(widths, gap, trayWidth) <= maxRows) return [];
    /* Least important first, and among equals the later key goes first: the
     * pad reads left to right in the order things are usually needed. */
    var order = [];
    for (var i = 0; i < widths.length; i++) order.push(i);
    order.sort(function (a, b) { return prios[a] - prios[b] || b - a; });
    var hidden = [];
    for (var k = 0; k < order.length; k++) {
      hidden.push(order[k]);
      var kept = [];
      for (var j = 0; j < widths.length; j++) {
        if (hidden.indexOf(j) === -1) kept.push(widths[j]);
      }
      kept.push(moreWidth);
      if (rowsNeeded(kept, gap, trayWidth) <= maxRows) break;
    }
    return hidden;
  }

  /* Measure the pad as it actually renders on this device, then fold. Every
   * key is shown first so its own width is read rather than guessed -- an
   * icon key and 예 are not the same size -- and the plan is applied in one
   * pass. Expanded, nothing is folded and the pad may take a third row,
   * which is then the user's choice rather than ours. */
  var KEY_MAX_ROWS = 2;

  function fitKeys() {
    var tray = el.keys, more = el.keysMore;
    if (!tray || !more) return;
    var buttons = [];
    var kids = tray.children;
    for (var i = 0; i < kids.length; i++) {
      if (kids[i] !== more) buttons.push(kids[i]);
    }
    if (!buttons.length) return;

    /* Unfold everything to measure; offsetWidth of a display:none key is 0. */
    buttons.forEach(function (b) { b.style.display = ''; });
    more.style.display = 'none';
    if (tray.hasAttribute('data-expanded')) {
      more.style.display = '';
      more.setAttribute('aria-expanded', 'true');
      more.textContent = '\u00d7';
      more.title = '\uac00\ub824\uc9c4 \ud0a4 \uc811\uae30';
      more.setAttribute('aria-label', '\uac00\ub824\uc9c4 \ud0a4 \uc811\uae30');
      return;
    }

    var cs = window.getComputedStyle(tray);
    var gap = parseFloat(cs.gap || cs.columnGap);
    if (!(gap >= 0)) gap = 8;
    var pad = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
    var trayWidth = tray.clientWidth - pad;
    var widths = buttons.map(function (b) { return b.getBoundingClientRect().width; });
    var prios = buttons.map(function (b) { return parseFloat(b.getAttribute('data-prio')) || 5; });

    more.style.display = '';
    var moreWidth = more.getBoundingClientRect().width;
    more.style.display = 'none';

    var hidden = planKeys(widths, prios, gap, trayWidth, KEY_MAX_ROWS, moreWidth);
    hidden.forEach(function (idx) { buttons[idx].style.display = 'none'; });
    if (hidden.length) {
      more.style.display = '';
      more.setAttribute('aria-expanded', 'false');
      more.textContent = '\u22ef';
      more.title = hidden.length + '\uac1c \ud0a4 \ub354 \ubcf4\uae30';
      more.setAttribute('aria-label', hidden.length + '\uac1c \ud0a4 \ub354 \ubcf4\uae30');
    }
  }

  function renderTail(text) {
    var lines = text.split('\n');
    state.lines = lines;
    state.pending = findPendingInput(lines);
    el.tail.textContent = '';
    var frag = document.createDocumentFragment();
    var segments = linkifyLines(lines, state.cols);
    var pend = state.pending;
    lines.forEach(function (line, i) {
      var div = document.createElement('div');
      div.setAttribute('data-line', String(i));
      div.style.cssText = 'padding:1px 3px;border-radius:3px;min-height:1.45em;';
      /* Input-box lines carry their text in a span, so the marking can sit on
       * the words alone rather than a full-width bar. */
      var host = div;
      if (pend && i >= pend.index && i <= pend.end) {
        host = document.createElement('span');
        host.setAttribute('data-pending-text', '');
        host.style.cssText = 'border-radius:3px;padding:0 2px;margin:0 -2px;' +
          '-webkit-box-decoration-break:clone;box-decoration-break:clone;';
        div.appendChild(host);
      }
      var parts = segments[i];
      if (parts.length === 1 && !parts[0].url) {
        host.textContent = line;
      } else {
        parts.forEach(function (part) {
          if (!part.url) {
            host.appendChild(document.createTextNode(part.text));
            return;
          }
          var a = document.createElement('a');
          a.href = part.url;
          a.textContent = part.text;
          a.target = '_blank';
          a.rel = 'noopener noreferrer';
          a.setAttribute('data-tail-link', '');
          a.style.cssText =
            'color:var(--con-link);text-decoration:underline;text-underline-offset:2px;' +
            'cursor:pointer;word-break:break-all;';
          host.appendChild(a);
        });
      }
      frag.appendChild(div);
    });
    el.tail.appendChild(frag);
    paintPending();
    if (findOpen()) runFind(fnd.q, fnd.at);
    updateEndPill();
  }

  /* What the console can honestly say about text it finds in the box. It knows
   * one thing for certain -- whether it put it there itself -- and that is the
   * question being asked. Anything else is unattributable: Claude Code's own
   * prefill and a line typed at the terminal look identical from here, so the
   * wording does not pretend to tell them apart. */
  function pendingHint(text) {
    var sent = state.sent;
    var mine = sent && sent.session === state.session
      && sent.text.trim() === String(text).trim();
    return mine
      ? '\ubbf8\uc804\uc1a1 \u2014 \ubc29\uae08 \uc774 \ub300\uc2dc\ubcf4\ub4dc\uc5d0\uc11c \ubcf4\ub0b8 \ub0b4\uc6a9\uc785\ub2c8\ub2e4.'
      : '\ubbf8\uc804\uc1a1 \u2014 \uc774 \ub300\uc2dc\ubcf4\ub4dc\uc5d0\uc11c \ubcf4\ub0b8 \uac83\uc774 \uc544\ub2d9\ub2c8\ub2e4.\n'
        + 'Claude Code\uac00 \ubbf8\ub9ac \ucc44\uc6cc\ub454 \uba85\ub839\uc77c \uc218 \uc788\uc73c\ub2c8 '
        + 'Enter \uc804\uc5d0 \ud655\uc778\ud558\uc138\uc694.';
  }

  function paintPending() {
    var pending = state.pending;
    var nodes = el.tail.querySelectorAll('[data-line]');
    for (var i = 0; i < nodes.length; i++) {
      /* Blue: text is sitting in the box, unsent. Green: the last key
       * changed what sits there (a Tab took the prefill, a key cleared it),
       * held until the box changes again -- so before and after a key look
       * different, not just "something is there" both times. Amber is the
       * board's waiting colour and had nothing to do with either. */
      if (pending && i >= pending.index && i <= pending.end) {
        var touched = state.boxTouched !== null && state.boxTouched === pending.text;
        /* Grey, dashed edge: a ghost suggestion, not yet anyone's -- a Tab
         * would take it. Blue: real text waiting to be sent. Green: the
         * last key changed the box. The server reads the dim attribute the
         * plain capture drops, so ghost and typed no longer look the same.
         * The colour goes on the text span, every line of the box; the row
         * keeps only the thin edge. */
        var ghost = !touched && state.ghost;
        var span = nodes[i].querySelector('[data-pending-text]');
        var wash = touched ? 'rgba(16,185,129,0.18)'
          : ghost ? 'rgba(107,114,128,0.14)' : 'rgba(37,99,235,0.14)';
        if (span) span.style.background = wash;
        nodes[i].style.background = '';
        nodes[i].style.boxShadow = touched ? 'inset 3px 0 0 var(--con-ok)'
          : ghost ? 'inset 3px 0 0 var(--con-dim)' : 'inset 3px 0 0 var(--con-accent)';
        nodes[i].style.opacity = ghost ? '0.7' : '';
        nodes[i].title = ghost ? '제안된 입력 — Tab(⇥)으로 확정' : pendingHint(pending.text);
        continue;
      }
      nodes[i].style.background = '';
      nodes[i].style.opacity = '';
      nodes[i].style.boxShadow = '';
      nodes[i].title = '';
    }
  }

  /* The pane stops updating for more than one reason -- the reader holding
   * it to copy from, a find in progress -- and each has to be able to end
   * without thawing the other. */
  function held() { return !!state.held; }

  function frozen() { return held() || findOpen(); }

  /* Copying from a pane that repaints under the cursor is the problem; a pane
   * that stands still is trivially selectable with the ordinary drag the
   * platform already gives you. So the tap does the one thing the browser
   * cannot do for itself -- stop the repaints -- and the copy is the reader's
   * own. That is why there is no line-range bar here any more: it existed only
   * to work around the motion. */
  var HOLD_MSG = '\uac31\uc2e0 \uc815\uc9c0\ub428 \u2014 \ub4dc\ub798\uadf8\ud574\uc11c \ubcf5\uc0ac\ud558\uc138\uc694. \ub2e4\uc2dc \ud0ed\ud558\uba74 \uc7ac\uac1c';

  function toggleHold() {
    if (!state.session) return;
    if (state.held) { unhold(); return; }
    state.held = true;
    stopPolling();
    setFrozen(true);
    setStatus(HOLD_MSG, 'var(--con-warn)');
  }

  /* Called from every path that ends the hold -- a second tap, a send, a
   * switch, closing the sheet -- so none of them can leave the console
   * looking frozen while it is in fact live. */
  function setFrozen(on) {
    on = !!on && frozen();   /* one reason ending does not thaw the other */
    if (el.frozen) el.frozen.style.display = on ? 'inline-flex' : 'none';
    /* The well has no border; the freeze shows as an amber ring in the
     * shadow channel, on top of the well's own edge. */
    if (el.tail) el.tail.style.boxShadow = on
      ? 'var(--con-well-edge), inset 0 0 0 2px rgba(245,158,11,0.55)' : '';
    /* A freeze changes what the walk can do -- a held pane cannot fetch older
     * history -- and every path that freezes or thaws comes through here. */
    updatePrevPill();
  }

  function unhold() {
    if (!state.held) return;
    state.held = false;
    /* The line that said "다시 탭하면 재개" goes with the hold it was
     * describing. Left up, it told a live pane to do what it had already done,
     * and the next tap -- which is the hold coming back -- then read as the
     * message having been ignored.
     *
     * Unconditional: a thaw on the way to somewhere else -- a key, a prompt --
     * is followed by that somewhere else putting its own line up, so there is
     * nothing here worth keeping. */
    setStatus('', '');
    setFrozen(frozen());
    /* The hold was what paused the tail; resume now -- unless a find is
     * still holding it. */
    if (state.session && !state.timer && !frozen()) startPolling();
  }

  /* How many columns of this font fit across the tail. The server uses it to
   * widen a detached pane so tmux stops wrapping lines far short of the screen
   * -- on a desktop the console is roughly twice the 80 columns a session
   * nobody attached to sits at. */
  function tailCols() {
    if (!el.tail) return 0;
    var probe = document.createElement('span');
    probe.style.cssText =
      'position:absolute;visibility:hidden;white-space:pre;font:inherit;';
    probe.textContent = new Array(101).join('0');
    el.tail.appendChild(probe);
    var per = probe.getBoundingClientRect().width / 100;
    probe.remove();
    var inner = el.tail.clientWidth - 16;   /* the pre's own 8px padding */
    if (!per || inner <= 0) return 0;
    return Math.floor(inner / per);
  }

  /* Sent once per session, not on every tick: a resize is a repaint for the
   * program in the pane, and the width does not change between polls. */
  function fitParam() {
    if (state.fitted) return '';
    var cols = tailCols();
    if (!cols) return '';
    state.fitted = true;
    return '&fit=' + cols;
  }

  /* A poll that never comes back is worse than one that fails: fetch has no
   * timeout of its own, so a request left hanging -- the phone changed network,
   * a keep-alive connection died under Tailscale, the server restarted
   * mid-flight -- never settles and never retries. The tick keeps opening more,
   * and once ~6 of them are stuck the browser's per-host connection pool is
   * full and every later request queues behind them. That is what a console
   * sitting on '불러오는 중…' for minutes actually is, and why it looks like it
   * picked on one session: the one you opened after the pool jammed.
   *
   * Cut them loose, and say so. */
  var FETCH_TIMEOUT_MS = 8000;

  function getJSON(path) {
    var ctl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, FETCH_TIMEOUT_MS) : null;
    var opts = { headers: { 'Accept': 'application/json' } };
    if (ctl) opts.signal = ctl.signal;
    function done(v) { if (timer) clearTimeout(timer); return v; }
    return fetch(api(path), opts).then(
      function (r) {
        done();
        /* The status matters, not just the failure: 404 from these routes is
         * the server saying this session does not exist, which is a fact and
         * not a blip. Everything else stays a blip. */
        if (!r.ok) return { __status: r.status };
        return r.json();
      },
      function (e) { done(); throw e; }
    );
  }

  /* Silence used to be the only report: the catch was empty and a bad status
   * returned early, so a console that could not load looked exactly like one
   * that was still loading -- forever. */
  function pollFailed() {
    state.fails += 1;
    if (state.fails < 3) return;        /* one blip is not an outage */
    state.warned = true;
    if (!state.lines) {
      el.tail.textContent = '불러오지 못했습니다 — 다시 시도하는 중…';
    } else {
      setStatus('연결 끊김 — 다시 시도하는 중…', 'var(--con-warn)');
    }
  }

  /* Retrying a session that has ended is not patience, it is a lie: the tail
   * said "다시 시도하는 중…" forever over a pane that will never answer, and the
   * poll kept a capture-pane request going out every two seconds for it. Say
   * what happened and stop; the strip is still there to switch away with. */
  function sessionGone() {
    stopPolling();
    closeFind();
    /* The pane is replaced by a sentence; hits into it point at nothing. */
    state.lines = null;
    state.exhausted = true;
    el.tail.textContent = '이 세션은 더 이상 없습니다 — 종료되었거나 이름이 바뀌었습니다.';
    setStatus('세션 없음', 'var(--con-err)');
    renderStrip();
  }

  function pollOk() {
    state.fails = 0;
    if (!state.warned) return;
    state.warned = false;
    setStatus('');
  }

  /* `force`: repaint even when the reader is up in history or mid-fling --
   * used once, after a key changed the box, so the colour change is seen
   * wherever the view sits. The view is held by its distance from the
   * bottom, the way growTail holds it. */
  function pollTail(force) {
    if (!state.session) return;
    var name = state.session;
    getJSON('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + state.depth
            + fitParam() + (state.hash && !force ? '&since=' + state.hash : ''))
      .then(function (data) {
        if (state.session !== name) return;
        if (data && data.__status === 404) { sessionGone(); return; }
        if (!data || data.__status) { pollFailed(); return; }
        pollOk();
        /* Same pane as last time: nothing to paint. */
        if (data.unchanged) return;
        /* A frozen pane wins over a refresh: repainting would move the lines
         * out from under whoever is copying from or searching them.
         *
         * The hash is deliberately NOT banked here. It used to be, one line
         * above this check, and the server then answered `unchanged` for a
         * pane this console had never painted: a thaw showed the stale text
         * until something else happened to change the screen. */
        if (frozen()) { state.hash = ''; return; }
        state.hash = data.hash || '';
        state.cols = data.cols || 0;
        state.ghost = data.ghost === true;
        /* Within two lines of the bottom counts as at the bottom: the
         * keyboard, a status line, a rotated phone all move the geometry by
         * a little, and a reader who never scrolled up must not be unpinned
         * by any of them. */
        var atBottom = state.pinned
          || el.tail.scrollTop + el.tail.clientHeight >= el.tail.scrollHeight - 48;
        /* Scrolled up into history: leave the view alone. The window is a
         * fixed number of lines off the end of the pane, so a repaint with
         * fresh output shifts everything above the bottom, and a repaint
         * mid-fling on iOS throws the view (see whenSettled). The reader gets
         * the live tail back the moment they return to the bottom -- the
         * next poll sees atBottom and paints. */
        /* A safety net under all of the above: whatever the reason, three
         * skipped repaints in a row is a frozen screen, and the fourth paints
         * -- holding the view by its distance from the bottom if the reader
         * is up in history. */
        if (!force && (!atBottom || scrollInFlight()) && state.skipped < 3) {
          state.skipped += 1;
          /* Not painted now, so the next poll must bring it again. */
          state.hash = '';
          return;
        }
        state.skipped = 0;
        var fromBottom = el.tail.scrollHeight - el.tail.scrollTop;
        renderTail(data.log || '');
        el.tail.scrollTop = atBottom ? el.tail.scrollHeight : el.tail.scrollHeight - fromBottom;
        if (atBottom) state.pinned = true;
        updateEndPill();
        rememberTail(name, data);
      })
      .catch(function () {
        if (state.session === name) pollFailed();
      });
  }

  /* Is the tail still moving? iOS keeps a fling going for a second or more
   * after the finger lifts, and it drives that animation from the geometry it
   * captured at lift-off. Rebuild the tail underneath it -- 400 lines landing
   * on top, scrollTop reassigned -- and the animation carries on toward its
   * old target in the new coordinate space, which is the throw hundreds of
   * lines up that a reader on a phone kept hitting. So nothing is redrawn
   * while a scroll is in flight: work that arrives mid-fling waits for the
   * tail to come to rest. A scroll event every frame while moving, then
   * silence; SETTLE_MS of silence with no finger down is "at rest". */
  var SETTLE_MS = 120;
  /* Long enough that a finger resting on the glass mid-drag -- no touchmove,
   * no scroll events -- still counts as a scroll in progress: landing 400
   * lines under a resting finger is what threw the view when the drag
   * resumed. Short enough that a lost touchend clears in a second and a bit. */
  var TOUCH_LEASE_MS = 1200;
  var touchUntil = 0;
  var settleTimer = null;
  var onSettled = null;

  function touchLease() { touchUntil = Date.now() + TOUCH_LEASE_MS; }
  function touching() { return Date.now() < touchUntil; }

  function noteScrolling() {
    if (settleTimer) clearTimeout(settleTimer);
    settleTimer = setTimeout(function () {
      settleTimer = null;
      if (!onSettled) return;
      /* Still not at rest (finger resting, or bouncing): look again. */
      if (scrollInFlight()) { noteScrolling(); return; }
      var fn = onSettled;
      onSettled = null;
      fn();
    }, SETTLE_MS);
  }

  function scrollInFlight() {
    /* The rubber band at the top: scrollTop goes negative and springs back
     * with no scroll events on the way, so silence there is not rest. */
    var bouncing = el.tail && el.tail.scrollTop < 0;
    return touching() || settleTimer !== null || bouncing;
  }

  /* Run now if the tail is at rest, otherwise once it is. Only the latest
   * caller is kept: two redraws queued behind one fling would fight. */
  function whenSettled(fn) {
    if (!scrollInFlight()) { fn(); return; }
    onSettled = fn;
    /* A lease or a bounce that ends with no further scroll event would
     * otherwise leave the work queued for good: look again shortly. */
    if (!settleTimer) noteScrolling();
  }

  /* Deepen the window and redraw, keeping the line the user is looking at
   * where it was: the new lines arrive ABOVE, so anchoring to the distance
   * from the bottom is what holds the view still. */
  /* `deliberate` is a request the reader made in so many words -- the find
   * bar's "더 불러오기" -- as opposed to the automatic deepening that scrolling
   * up performs. Only the deliberate kind runs while the pane is frozen.
   *
   * `after` runs once the deeper pane is on screen -- the walk back uses it to
   * continue past the oldest loaded turn. It does not run when the grow was
   * refused or brought nothing back: there is nothing new to walk into. */
  function growTail(deliberate, after) {
    if (!state.session || state.growing || state.exhausted) return;
    /* A frozen pane stays frozen -- including the automatic deepening that
     * scrolling up asks for. Find does its own deepening, on request. */
    /* A hold is never overridden -- the reader is copying off the pane.
     * A find freeze is, but only by the find bar's own button. */
    if (held()) return;
    if (findOpen() && !deliberate) return;
    if (state.depth >= MAX_TAIL_LINES) return;

    var name = state.session;
    var was = state.depth;
    state.depth = Math.min(MAX_TAIL_LINES, state.depth + TAIL_STEP);
    state.growing = true;
    setStatus('이전 내용 불러오는 중…', 'var(--con-muted)');

    getJSON('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + state.depth)
      .then(function (data) {
        if (!data || state.session !== name) { state.growing = false; return; }
        if (data.__status) { state.growing = false; setStatus('불러오기 실패', 'var(--con-err)'); return; }
        /* Fetched at once so the lines are ready early, applied only once the
         * fling has stopped (see whenSettled). `growing` stays up until then:
         * a second request behind a fling still in flight would only queue a
         * redraw that displaces this one. */
        whenSettled(function () {
          state.growing = false;
          /* The freeze may have arrived while this was in flight: a find
           * opened after an automatic grow started must not have the pane
           * rebuilt underneath its matches. */
          if (state.session !== name || held()) return;
          if (findOpen() && !deliberate) return;
          state.cols = data.cols || 0;
          state.hash = data.hash || '';
          var before = state.lines ? state.lines.length : 0;
          var fromBottom = el.tail.scrollHeight - el.tail.scrollTop;
          /* NOT named `held`: `var held` hoists over the held() predicate
           * used above in this same callback, and calling it then threw
           * "held is not a function" -- every scroll-up grow died there. */
          var hit = findOpen() && fnd.hits[fnd.at] ? fnd.hits[fnd.at] : null;
          renderTail(data.log || '');
          rememberTail(name, data);
          el.tail.scrollTop = el.tail.scrollHeight - fromBottom;
          updateEndPill();
          var gained = (state.lines ? state.lines.length : 0) - before;
          /* Older lines arrive above, so every match moved down by `gained`.
           * Re-point at the same one rather than jumping back to the first. */
          if (hit && gained > 0) {
            for (var h = 0; h < fnd.hits.length; h++) {
              if (fnd.hits[h].line === hit.line + gained
                  && fnd.hits[h].start === hit.start) {
                fnd.at = h;
                paintCurrent(false);
                renderFindCount();
                break;
              }
            }
          }
          if (gained <= 0) {
            /* The pane has no more history: stop asking on every scroll. */
            state.exhausted = true;
            state.depth = was;
            /* The pill was last decided while a deepening was still possible.
             * Nothing else repaints on a zero-gain answer, so it would have
             * sat there enabled with nowhere to go. */
            updatePrevPill();
            setStatus('더 이상 이전 내용이 없습니다', 'var(--con-muted)');
          } else {
            setStatus('이전 ' + gained + '줄 불러옴', 'var(--con-ok)');
            if (after) after(gained);
          }
        });
      })
      .catch(function () { state.growing = false; setStatus('불러오기 실패', 'var(--con-err)'); });
  }

  function startPolling() {
    stopPolling();
    pollTail();
    state.timer = setInterval(pollTail, POLL_MS);
  }

  function stopPolling() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
  }

  /* --- back to live ------------------------------------------------------ */

  /* Everything that can leave the console looking dead, undone in one call:
   * a hold freezing the pane, a find holding it, a fling whose
   * lease never expired, a reader parked in history, a poll timer lost to a
   * backgrounded tab. The pill presses it; so does Enter.
   *
   * Exactly one request goes out, whichever path got here: unhold()
   * restarts the poll (which polls immediately) when it is the thing that
   * stopped it, and the branches below cover the cases where it was not. */
  var recoveredEnter = false;

  function resumeLive() {
    if (!state.session) return;
    closeFind();
    /* Whether anything was polling BEFORE the thaw: unhold() restarts
     * the timer only when it was the hold that stopped it, and a timer
     * that was already running has to be given its own poll below. Getting
     * this wrong is silent -- the console comes back and then sits on the
     * same stale pane until the next tick. */
    var hadTimer = !!state.timer;
    unhold();
    state.skipped = 0;
    /* A lost touchend, or a queued repaint waiting on a fling that ended
     * without a final scroll event: both hold repaints off on their own. */
    touchUntil = 0;
    if (settleTimer) { clearTimeout(settleTimer); settleTimer = null; }
    /* Dropping the queued repaint drops the callback that would have cleared
     * this, and a growTail() that never finishes blocks every later one. */
    onSettled = null;
    state.growing = false;
    state.pinned = true;
    endWalk();                      /* back at the end: the walk is over */
    if (el.tail) el.tail.scrollTop = el.tail.scrollHeight;
    updateEndPill();
    if (!state.timer) {
      startPolling();              /* polls at once */
    } else if (hadTimer) {
      /* The timer never stopped, so nothing above has asked for anything.
       * What is on screen may be a pane the poll skipped: ask for the whole
       * thing rather than for the difference. */
      state.hash = '';
      pollTail(true);
    }
    /* else: unhold() restarted the timer, which polled on the way in. */
    if (el.input) {
      el.input.focus();
      var end = el.input.value.length;
      try { el.input.setSelectionRange(end, end); } catch (err) { /* not yet focusable */ }
    }
  }

  /* Enter anywhere over the console that is not a control means "get me back
   * to work". Deliberately NOT taken in the prompt box: an empty Enter there
   * already sends a bare newline to tmux, which is how a Claude Code prompt
   * gets confirmed, and stealing it because the screen happened to be frozen
   * would swallow the one key the reader needed most. Buttons and links keep
   * their Enter too -- there it is the press. */
  function interactiveTarget(node) {
    if (!node || !node.tagName) return false;
    var t = node.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'BUTTON' || t === 'A'
        || t === 'SELECT' || node.isContentEditable;
  }

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.defaultPrevented || e.repeat) return;
    if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    if (!state.session || keysTaken() || quadMenuOpen()) return;
    if (interactiveTarget(e.target)) return;
    e.preventDefault();
    recoveredEnter = true;
    resumeLive();
    setStatus('\uc785\ub825\ucc3d\uc73c\ub85c \ub3cc\uc544\uc654\uc2b5\ub2c8\ub2e4 \u00b7 \uc790\ub3d9 \ub530\ub77c\uac00\uae30', 'var(--con-muted)');
  });

  /* --- jump to the end --------------------------------------------------- */

  /* A phone reopens the console where it was left, which after a day is
   * hundreds of lines up with no sign of how far. The pill appears once the
   * bottom is more than a screenful away and says how to get back in one tap.
   * Half a screen, floor 240px: anything closer is a scroll, not a journey. */
  function endDistance() {
    if (!el.tail) return 0;
    return el.tail.scrollHeight - el.tail.scrollTop - el.tail.clientHeight;
  }

  /* One full pane, not half of one. At half a screen the pill sat over lines
   * the reader could still see the bottom of -- it covered the output to
   * offer a trip you had not left for yet. A page is the point where the
   * bottom is genuinely off-screen and getting back is worth a button. */
  function updateEndPill() {
    if (!el.endPill) return;
    var far = !!state.session && endDistance() > el.tail.clientHeight * 2;
    el.endPill.style.display = far ? 'inline-flex' : 'none';
    updatePrevPill();
  }

  /* --- back to the previous request -------------------------------------- */

  /* Where the walk stands, counted from the NEWEST submitted request: 1 is the
   * last thing the reader sent, 2 the one before it.
   *
   * Not a line number: the pane is a fixed window on a growing transcript, and
   * older history arrives 400 lines at a time ABOVE what is drawn, so an index
   * names a different line a moment later. Not the text either -- the same
   * request sent twice makes two identical lines, and "the nearest occurrence"
   * then handed the walk back the turn it had just left.
   *
   * Counted from the end, neither the window sliding nor a prepend can move it,
   * because both only ever change what is above. A newly SENT request would --
   * so sending clears the walk, which is what going back to work means anyway.
   *
   *   -> the line the walk stands on, or -1 when there is no walk.
   */
  function walkLine() {
    if (!state.walk || !state.lines) return -1;
    var at = submittedLines(state.lines);
    var i = at.length - state.walk;
    return i >= 0 && i < at.length ? at[i] : -1;
  }

  /* Is the walk still the reader's position, or have they moved on?
   *
   * It stays theirs while the landing is anywhere from one pane above the view
   * down to the bottom of it. Above that band, live output has pushed it out of
   * sight over many repaints; below it, the reader has scrolled up past it by
   * hand. Either way their eyes are the mark now, not the last press.
   *
   * Asked only when the reader presses, never while painting: a repaint that
   * prepends history has the new rows in the DOM before the scroll position is
   * restored, and judged in that instant every landing looks hundreds of rows
   * below the view. Answering there deleted walks that were perfectly alive. */
  function walkOwnsView() {
    var line = walkLine();
    if (line < 0) return false;
    var node = el.tail.querySelector('[data-line="' + line + '"]');
    if (!node) return true;             /* not drawn yet; trust the count */
    var box = el.tail.getBoundingClientRect();
    var top = node.getBoundingClientRect().top;
    return top >= box.top - el.tail.clientHeight && top <= box.bottom;
  }

  /* The turn to jump to, or -1.
   *
   * Mid-walk it is simply the turn before the one we stand on -- counted in the
   * transcript, not measured on screen. Geometry cannot do this job: two
   * requests three lines apart both sit inside the pane after a jump, and
   * "above the top edge" then skips the nearer one.
   *
   * Cold, with no walk in progress, geometry is all there is: the nearest turn
   * whose FIRST row is above the top edge. First row, not last -- a long
   * request rejoined by capture-pane -J wraps to most of the pane, and judged
   * by its last row it was unreachable with its opening words already gone. */
  function prevPromptLine() {
    if (!el.tail || !state.lines) return -1;
    var at = submittedLines(state.lines);
    if (!at.length) return -1;
    var k;
    var line = walkLine();
    if (line >= 0) {
      k = at.length - state.walk;
      return k > 0 ? at[k - 1] : -1;
    }
    var nodes = el.tail.querySelectorAll('[data-line]');
    var top = el.tail.getBoundingClientRect().top;
    for (k = at.length - 1; k >= 0; k--) {
      var node = nodes[at[k]];
      if (node && node.getBoundingClientRect().top < top - 2) return at[k];
    }
    return -1;
  }

  /* Older history is fetched a page at a time, so the oldest turn in the window
   * is usually not the oldest turn there is. A reader mid-walk is offered the
   * next page rather than a button that vanishes; a pane that holds no turns at
   * all is offered nothing, because there is nothing to walk.
   *
   * The grow's own refusals are part of the test: a held pane cannot be grown,
   * and a button that does nothing when pressed -- no movement, no fetch, no
   * word -- is worse than an absent one. */
  function canDeepenForWalk() {
    return !state.exhausted && !state.growing && !held()
      && state.depth < MAX_TAIL_LINES
      && !!state.lines && submittedLines(state.lines).length > 0;
  }

  function updatePrevPill() {
    if (!el.prevPill) return;
    /* The find bar owns the top of the pane while it is open, full width. */
    var show = !!state.session && !findOpen()
      && (prevPromptLine() >= 0 || canDeepenForWalk());
    el.prevPill.style.display = show ? 'inline-flex' : 'none';
  }

  /* Clear of the pill itself. Landing the prompt flush at the top edge puts it
   * under the button that was just pressed -- the one line the press was for,
   * hidden by the press. So it lands just below, and what follows it -- the
   * answer to that request -- fills the rest of the pane. */
  var PROMPT_HEAD = 56;

  /* scrollIntoView is not used: it walks up the ancestors and has scrolled the
   * sheet itself out of place. */
  function landOnPrompt(line) {
    var node = el.tail.querySelector('[data-line="' + line + '"]');
    if (!node) return false;
    var at = submittedLines(state.lines);
    var ordinal = at.length - at.indexOf(line);
    if (ordinal <= 0) return false;
    var box = el.tail.getBoundingClientRect();
    /* A pane shorter than the offset would put the prompt below the fold. */
    var head = Math.min(PROMPT_HEAD, Math.max(0, el.tail.clientHeight - 24));
    el.tail.scrollTop += node.getBoundingClientRect().top - box.top - head;
    state.walk = ordinal;
    /* The reader has left the end: the poll must stop dragging them back. */
    state.pinned = false;
    updateEndPill();
    return true;
  }

  /* Bumped by everyone who takes the pane over from the walk. A deferred
   * landing compares it and gives up: the fetch behind a press to deepen is
   * still in flight when Enter takes the reader back to live, and landing then
   * undid that -- scrolled them away, and set pinned back to false. */
  var walkAsk = 0;

  /* One call for "the walk is over": forget where it stood, and refuse the
   * landing of any press still in flight. */
  function endWalk() {
    state.walk = null;
    walkAsk += 1;
  }

  function gotoPrevPrompt() {
    if (!state.session || !state.lines) return;
    /* Asked here, where the layout has settled, and nowhere else. */
    if (state.walk && !walkOwnsView()) state.walk = null;
    var ask = ++walkAsk;
    var name = state.session;
    var line = prevPromptLine();
    if (line >= 0) {
      if (landOnPrompt(line)) {
        setStatus('\uc774\uc804 \uc694\uccad\uc73c\ub85c \uc774\ub3d9\ud588\uc2b5\ub2c8\ub2e4 \u00b7 \ub2e4\uc2dc \ub204\ub974\uba74 \uadf8 \uc804 \uc694\uccad', 'var(--con-muted)');
      }
      return;
    }
    if (!canDeepenForWalk()) return;
    /* Past the oldest loaded turn: fetch a page and carry the walk into it.
     * Deliberate, because this is a press, not a scroll. */
    growTail(true, function () {
      if (ask !== walkAsk || state.session !== name) return;
      if (findOpen() || held()) return;
      var deeper = prevPromptLine();
      if (deeper >= 0) landOnPrompt(deeper);
      updatePrevPill();
    });
  }

  /* --- find in the output ------------------------------------------------ */

  /* The session palette on Ctrl+F answers "which session"; this answers "where
   * in this one". Ctrl/Cmd+Shift+F rather than plain Ctrl+F so the palette
   * keeps the key every hand here already knows, and the header carries a
   * button for the phone, which has no chord at all.
   *
   * The pane freezes while the bar is open -- the same freeze a selection
   * uses, by a different reason -- because a match on line 12 is worth nothing
   * if the next poll shifts line 12 somewhere else. */
  var fnd = { root: null, input: null, count: null, more: null,
              open: false, q: '', hits: [], at: 0 };

  function findOpen() { return fnd.open; }

  function buildFindBar() {
    var bar = document.createElement('div');
    bar.id = 'con-find';
    bar.setAttribute('role', 'search');
    bar.style.cssText = [
      'display:none', 'position:absolute', 'left:8px', 'right:8px', 'top:8px',
      'z-index:4', 'align-items:center', 'gap:6px',
      'padding:6px', 'border-radius:12px',
      'background:var(--con-sheet)', 'box-shadow:0 8px 24px rgba(16,24,40,0.28)',
    ].join(';');

    var input = document.createElement('input');
    input.type = 'text';
    input.id = 'con-find-input';
    input.placeholder = '출력 내용 검색';
    input.setAttribute('aria-label', '출력 내용 검색');
    input.autocomplete = 'off';
    input.autocapitalize = 'off';
    input.spellcheck = false;
    input.style.cssText = [
      /* 16px or iOS zooms the whole sheet in on focus and stays there. */
      'flex:1', 'min-width:0', 'font-size:16px', 'padding:7px 10px',
      'border-radius:9px', 'background:var(--con-well)', 'color:var(--con-text)',
      'border:1px solid var(--con-edge,rgba(128,128,128,0.25))', 'outline:none',
    ].join(';');
    input.addEventListener('input', function () { runFind(input.value, 0); });
    input.addEventListener('keydown', onFindKey);

    var count = document.createElement('span');
    /* aria-live, not role="status": the console already has one status line
     * and the page selects it as `[role=status]`. A second one here shadowed
     * it -- everything the console said went to an element that was not on
     * screen, and the reader was told nothing. */
    count.setAttribute('aria-live', 'polite');
    count.style.cssText = 'flex-shrink:0;font-size:11px;color:var(--con-muted);'
      + 'min-width:52px;text-align:center;';

    var prev = document.createElement('button');
    prev.type = 'button';
    prev.appendChild(icon('up', 15));
    prev.setAttribute('aria-label', '이전 결과');
    styleBtn(prev, 'icon');
    prev.addEventListener('click', function () { stepFind(-1); });

    var next = document.createElement('button');
    next.type = 'button';
    next.appendChild(icon('down', 15));
    next.setAttribute('aria-label', '다음 결과');
    styleBtn(next, 'icon');
    next.addEventListener('click', function () { stepFind(1); });

    /* The pane holds a window off the end of the session, 40 lines to start
     * with. A search that finds nothing there has usually found nothing YET,
     * and saying "0" without offering the rest is a lie by omission. */
    var more = document.createElement('button');
    more.type = 'button';
    more.textContent = '더 불러오기';
    styleBtn(more, '');
    more.style.cssText = 'display:none;min-height:34px;padding:0 10px;font-size:12px;';
    more.addEventListener('click', function () { growTail(true); });

    var close = document.createElement('button');
    close.type = 'button';
    close.appendChild(icon('close', 15));
    close.setAttribute('aria-label', '검색 닫기');
    styleBtn(close, 'icon');
    close.addEventListener('click', function () { closeFind(true); });

    bar.appendChild(input);
    bar.appendChild(count);
    bar.appendChild(prev);
    bar.appendChild(next);
    bar.appendChild(more);
    bar.appendChild(close);

    fnd.root = bar;
    fnd.input = input;
    fnd.count = count;
    fnd.more = more;
    return bar;
  }

  function openFind() {
    build();
    if (!state.session) return;
    /* The palette owns the keyboard when it is up, and two overlays claiming
     * Escape is how one press closed both. */
    closeSearch();
    closeQuadMenu();
    /* Two freeze reasons at once is a state nobody can reason about: the
     * hold and the find bar would each be waiting for the other to let
     * go of the pane. A search replaces a hold. */
    unhold();
    fnd.open = true;
    fnd.root.style.display = 'flex';
    endWalk();                           /* a landing in flight is not wanted */
    updatePrevPill();                    /* the bar covers the pill's slot */
    setFrozen(true);
    stopPolling();
    fnd.input.focus();
    fnd.input.select();
    runFind(fnd.input.value, 0);
  }

  /* `live` is a close the reader asked for: it hands the caret back to the
   * prompt box and lets the pane run again. A close on the way out of the
   * session (hide/show) must not touch either. */
  function closeFind(live) {
    if (!fnd.open) return;
    fnd.open = false;
    fnd.root.style.display = 'none';
    updatePrevPill();
    fnd.hits = [];
    fnd.at = 0;
    fnd.q = '';
    clearMatches();
    setFrozen(held());
    if (!live) return;
    if (el.input && state.session) el.input.focus();
    /* A hold made before the find still owns the freeze. */
    if (state.session && !state.timer && !frozen()) startPolling();
  }

  function onFindKey(e) {
    /* Chords keep going: Ctrl+F is still the session palette and Ctrl+Shift+F
     * still re-selects the query, and swallowing them here made both dead
     * keys whenever the caret sat in this box. What the bar stops is the
     * plain keys the console spends on the session -- Shift+Tab, the digits
     * -- which are letters while a search is being typed. keysTaken() stands
     * the chorded ones down separately. */
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    e.stopPropagation();
    if (e.isComposing || e.keyCode === 229) return;   /* the IME's key */
    if (e.key === 'Enter') {
      e.preventDefault();
      stepFind(e.shiftKey ? -1 : 1);
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      stepFind(e.key === 'ArrowDown' ? 1 : -1);
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      closeFind(true);
    }
  }

  /* Plain case-insensitive substring, not a regex: what is being searched is
   * a terminal's output, where brackets and dots are text. */
  /* Case-folded one character at a time, keeping the string the same length.
   * String.toLowerCase() does not: 'İ' lowercases to two code units, which
   * slid every offset after it and produced hits that pointed at nothing --
   * counted in the bar, impossible to paint. */
  function fold(text) {
    var out = '';
    for (var i = 0; i < text.length; i++) {
      var c = text.charAt(i).toLowerCase();
      out += c.length === 1 ? c : c.charAt(0);
    }
    return out;
  }

  function findMatches(lines, query) {
    var hits = [];
    var q = fold(String(query || ''));
    if (!q || !lines) return hits;
    for (var i = 0; i < lines.length; i++) {
      var hay = fold(lines[i]);
      var from = 0;
      for (;;) {
        var at = hay.indexOf(q, from);
        if (at === -1) break;
        hits.push({ line: i, start: at, end: at + q.length });
        from = at + q.length;   /* no overlapping matches */
        if (hits.length > 2000) return hits;   /* a pane is not a corpus */
      }
    }
    return hits;
  }

  function runFind(query, at) {
    fnd.q = query;
    fnd.hits = findMatches(state.lines, query);
    fnd.at = Math.min(Math.max(0, at || 0), Math.max(0, fnd.hits.length - 1));
    clearMatches();
    paintMatches();
    renderFindCount();
  }

  function stepFind(dir) {
    if (!fnd.hits.length) return;
    fnd.at = (fnd.at + dir + fnd.hits.length) % fnd.hits.length;
    paintCurrent(true);
    renderFindCount();
  }

  function renderFindCount() {
    var n = fnd.hits.length;
    var loaded = state.lines ? state.lines.length : 0;
    fnd.count.textContent = !fnd.q ? String(loaded) + '줄'
                          : n ? (fnd.at + 1) + '/' + n
                          : '없음';
    /* Offered whenever there is more to load, not only at zero results: the
     * match you want may be older than the window as easily as absent. */
    var canGrow = !state.exhausted && state.depth < MAX_TAIL_LINES;
    fnd.more.style.display = (fnd.q && canGrow) ? 'inline-flex' : 'none';
  }

  function clearMatches() {
    if (!el.tail) return;
    var marks = el.tail.querySelectorAll('[data-find-hit]');
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      var parent = m.parentNode;
      if (!parent) continue;
      while (m.firstChild) parent.insertBefore(m.firstChild, m);
      parent.removeChild(m);
      /* Splitting left the line as several text nodes; rejoin them so the
       * next search walks the same offsets it computed against the string. */
      parent.normalize();
    }
  }

  /* Wrap one character range of a rendered line. The line's text nodes
   * concatenate to exactly state.lines[i] -- linkifyLines splits the same
   * string -- so a character offset into the string is a walk over them. */
  function markRange(div, start, end) {
    var walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT, null, false);
    var pos = 0, node, startNode = null, startOff = 0, endNode = null, endOff = 0;
    while ((node = walker.nextNode())) {
      var len = node.nodeValue.length;
      if (startNode === null && pos + len > start) {
        startNode = node;
        startOff = start - pos;
      }
      if (startNode !== null && pos + len >= end) {
        endNode = node;
        endOff = end - pos;
        break;
      }
      pos += len;
    }
    if (startNode === null || endNode === null) return null;
    var range = document.createRange();
    range.setStart(startNode, startOff);
    range.setEnd(endNode, endOff);
    var mark = document.createElement('mark');
    mark.setAttribute('data-find-hit', '');
    mark.style.cssText = 'background:rgba(250,204,21,0.35);color:inherit;'
      + 'border-radius:2px;';
    try {
      range.surroundContents(mark);
    } catch (err) {
      /* The match runs across a link boundary: surroundContents refuses a
       * range that only half-contains an element, so move the contents in. */
      try {
        mark.appendChild(range.extractContents());
        range.insertNode(mark);
      } catch (err2) {
        return null;
      }
    }
    return mark;
  }

  function paintMatches() {
    if (!el.tail || !fnd.hits.length) return;
    var rows = el.tail.querySelectorAll('[data-line]');
    for (var i = 0; i < fnd.hits.length; i++) {
      var hit = fnd.hits[i];
      var row = rows[hit.line];
      if (!row) continue;
      var mark = markRange(row, hit.start, hit.end);
      if (mark) mark.setAttribute('data-find-index', String(i));
    }
    paintCurrent(true);
  }

  function paintCurrent(scroll) {
    if (!el.tail) return;
    var marks = el.tail.querySelectorAll('[data-find-hit]');
    for (var i = 0; i < marks.length; i++) {
      var on = marks[i].getAttribute('data-find-index') === String(fnd.at);
      marks[i].style.background = on ? 'rgba(250,204,21,0.85)' : 'rgba(250,204,21,0.35)';
      marks[i].style.color = on ? '#1f2937' : 'inherit';
      if (on && scroll && marks[i].scrollIntoView) {
        marks[i].scrollIntoView({ block: 'center' });
      }
    }
    updateEndPill();
  }

  document.addEventListener('keydown', function (e) {
    if (!state.session) return;
    if (e.key !== 'f' && e.key !== 'F') return;
    if (!(IS_MAC ? e.metaKey : e.ctrlKey) || !e.shiftKey || e.altKey) return;
    if (sheetOpen() || e.defaultPrevented) return;
    if (e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    if (findOpen()) { fnd.input.focus(); fnd.input.select(); return; }
    hideHints();
    openFind();
  });

  /* --- speech to text ---------------------------------------------------- */

  /* Hold the key and talk; let go and the clip goes to /api/stt. A short tap
   * (under 350ms) starts a recording that the next tap stops -- a long
   * sentence with the finger off the glass. Either way the words land in the
   * input box as a draft, appended at the caret, and nothing is sent: the
   * transcript can be wrong, and Enter is the check. */
  var stt = { rec: null, stream: null, chunks: [], startedAt: 0, holding: false,
              enabled: false, busy: false, tick: null,
              audio: null, raf: 0, level: 0, quiet: false,
              peak: 0, metered: false,
              cap: null, wake: null, wakePending: false };

  /* The key shows the phase: red and pulsing while listening, amber with a
   * turning icon while the clip is being transcribed, plain otherwise. */
  /* A live meter off the local stream: the ring around the key grows with
   * what the mic actually hears. It costs nothing -- no server, no API --
   * and it is the honest answer to "is my voice going in", which a canned
   * pulse cannot give. A mic that is connected but dead (a bad earbud) shows
   * a flat ring, and after a second of that the status line says so. */
  function micLevelStart(stream) {
    micLevelStop();
    stt.metered = false;
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx || !el.mic) return;
    var ctx;
    try { ctx = new Ctx(); } catch (e) { return; }
    if (ctx.resume) { try { ctx.resume(); } catch (e) { /* already running */ } }
    var analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.5;
    try { ctx.createMediaStreamSource(stream).connect(analyser); }
    catch (e) { try { ctx.close(); } catch (e2) { /* gone */ } return; }

    stt.audio = ctx;
    stt.quiet = false;
    stt.peak = 0;
    stt.metered = true;
    el.mic.setAttribute('data-level', '');   /* stands down the canned pulse */

    var buf = new Uint8Array(analyser.fftSize);
    var loudAt = Date.now();
    var frame = function () {
      analyser.getByteTimeDomainData(buf);
      var sum = 0;
      for (var i = 0; i < buf.length; i++) {
        var v = (buf[i] - 128) / 128;
        sum += v * v;
      }
      /* RMS is small for speech; the root spreads the quiet end where the
       * eye needs the resolution. */
      var level = Math.min(1, Math.sqrt(Math.sqrt(sum / buf.length) * 3));
      stt.level = level;
      if (level > stt.peak) stt.peak = level;
      if (level > 0.12) loudAt = Date.now();
      stt.quiet = Date.now() - loudAt > 1500;
      if (el.mic) {
        el.mic.style.boxShadow = '0 0 0 ' + (2 + level * 12).toFixed(1) + 'px rgba(239,68,68,' +
          (0.15 + level * 0.35).toFixed(2) + ')';
      }
      stt.raf = requestAnimationFrame(frame);
    };
    stt.raf = requestAnimationFrame(frame);
  }

  function micLevelStop() {
    if (stt.raf) { cancelAnimationFrame(stt.raf); stt.raf = 0; }
    if (stt.audio) { try { stt.audio.close(); } catch (e) { /* already */ } stt.audio = null; }
    stt.level = 0; stt.quiet = false;
    if (el.mic) { el.mic.style.boxShadow = ''; el.mic.removeAttribute('data-level'); }
  }

  /* Neither recording nor transcribing showed the clock running, so a long
   * upload was indistinguishable from a frozen one. The count ticks in the
   * status line for both. */
  function micTick(label, color, since) {
    micTickStop();
    var paintMicTick = function () {
      var secs = ((Date.now() - since) / 1000).toFixed(1);
      if (stt.quiet) { setStatus('소리가 안 들어옵니다 · 마이크 확인 · ' + secs + '초', 'var(--con-warn)'); return; }
      setStatus(label + ' · ' + secs + '초', color);
    };
    paintMicTick();
    stt.tick = setInterval(paintMicTick, 100);
  }

  function micTickStop() {
    if (stt.tick) { clearInterval(stt.tick); stt.tick = null; }
  }

  function micPhase(phase) {
    if (!phase) micTickStop();
    if (phase !== 'recording') micLevelStop();
    if (!el.mic) return;
    el.mic.removeAttribute('data-listening');
    el.mic.removeAttribute('data-transcribing');
    if (phase === 'recording') el.mic.setAttribute('data-listening', '');
    if (phase === 'transcribing') el.mic.setAttribute('data-transcribing', '');
  }

  function sttAvailable() {
    return stt.enabled && !IS_VSCODE && !!(navigator.mediaDevices
      && navigator.mediaDevices.getUserMedia) && typeof MediaRecorder !== 'undefined';
  }

  function sttInit() {
    fetch(api('/api/stt/config'), { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (cfg) {
        stt.enabled = !!(cfg && cfg.enabled);
        if (el.mic) el.mic.style.display = sttAvailable() ? '' : 'none';
      })
      .catch(function () { /* no mic, no harm */ });
  }

  function sttMime() {
    var picks = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    for (var i = 0; i < picks.length; i++) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(picks[i])) return picks[i];
    }
    return '';
  }

  /* Two minutes is longer than any prompt anyone dictates, and short enough
   * that a mic left on by accident costs a rounding error rather than an
   * hour of billed audio. The recording is stopped, not thrown away: what
   * was said up to the wall still gets transcribed. */
  var STT_MAX_MS = 120000;

  /* A screen that sleeps mid-sentence backgrounds the page, and a backgrounded
   * page stops feeding MediaRecorder -- the recording appears to hang with
   * the key still red. Holding the screen awake for the length of a clip is
   * the fix; where the API is missing (older iOS, a non-secure origin) the
   * hard stop below is still the floor. */
  function wakeDrop(lock) {
    /* release() returns a promise and REJECTS when the lock is already gone,
     * which the browser does on its own every time the page is hidden -- the
     * common path here. A try/catch cannot see an async rejection. */
    if (lock && lock.release) { try { lock.release().catch(function () {}); } catch (e) { /* gone */ } }
  }

  function wakeAcquire() {
    /* wakePending, not just stt.wake: the request takes a moment to resolve,
     * and without this a stop-and-start inside that window issued a second
     * request whose lock overwrote the first -- which was then never
     * released, and the screen never slept again. */
    if (!navigator.wakeLock || stt.wake || stt.wakePending) return;
    stt.wakePending = true;
    try {
      navigator.wakeLock.request('screen').then(function (lock) {
        stt.wakePending = false;
        /* The clip ended, or another lock won, while this was in flight. */
        if (!stt.rec || stt.wake) { wakeDrop(lock); return; }
        stt.wake = lock;
      }).catch(function () { stt.wakePending = false; });
    } catch (e) { stt.wakePending = false; }
  }

  function wakeRelease() {
    var lock = stt.wake;
    stt.wake = null;
    stt.wakePending = false;
    wakeDrop(lock);
  }

  function sttStart() {
    if (stt.rec || stt.busy || !state.session) return;
    stt.busy = true;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      stt.busy = false;
      var mime = sttMime();
      var rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      stt.rec = rec; stt.stream = stream; stt.chunks = []; stt.startedAt = Date.now();
      rec.addEventListener('dataavailable', function (e) {
        if (e.data && e.data.size) stt.chunks.push(e.data);
      });
      rec.addEventListener('stop', sttFinish);
      rec.start();
      micPhase('recording');
      micLevelStart(stream);
      wakeAcquire();
      stt.cap = setTimeout(function () {
        stt.cap = null;
        if (!stt.rec) return;
        setStatus('2\ubd84 \uc81c\ud55c \u00b7 \uc5ec\uae30\uae4c\uc9c0 \uc804\uc0ac\ud569\ub2c8\ub2e4', 'var(--con-warn)');
        stt.holding = false;
        sttStop();
      }, STT_MAX_MS);
      if (navigator.vibrate) { try { navigator.vibrate(15); } catch (e) { /* no haptics */ } }
      micTick('듣는 중', 'var(--con-err)', stt.startedAt);
    }).catch(function (err) {
      stt.busy = false;
      var denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
      setStatus(denied ? '마이크 권한이 거부됨' : '마이크를 열 수 없음', 'var(--con-err)');
    });
  }

  function sttStop() {
    var rec = stt.rec;
    if (!rec) return;
    if (rec.state !== 'inactive') rec.stop(); else sttFinish();
  }

  /* Closing or switching mid-recording: drop the clip, it was for a session
   * that is no longer in front of the user. */
  function sttAbort() {
    var rec = stt.rec;
    if (!rec) return;
    micPhase('');
    stt.holding = false;
    rec.removeEventListener('stop', sttFinish);
    if (rec.state !== 'inactive') { try { rec.stop(); } catch (e) { /* already */ } }
    sttRelease();
  }

  function sttRelease() {
    if (stt.cap) { clearTimeout(stt.cap); stt.cap = null; }
    wakeRelease();
    if (stt.stream) stt.stream.getTracks().forEach(function (t) { t.stop(); });
    stt.stream = null; stt.rec = null; stt.chunks = [];
  }

  function sttFinish() {
    var rec = stt.rec;
    if (!rec) return;
    var mime = rec.mimeType || sttMime() || 'audio/webm';
    var blob = new Blob(stt.chunks, { type: mime });
    var held = Date.now() - stt.startedAt;
    var forSession = state.session;
    sttRelease();
    /* A brush of the key, or a clip too short to hold a word. */
    if (held < 400 || blob.size < 1200) { micPhase(''); setStatus('', ''); return; }
    /* Silence still costs a full round trip to the transcriber -- ten seconds
     * of waiting, and the money, to be told nothing was said. The meter
     * already knows: if it ran and never saw a peak worth a syllable, answer
     * here. The threshold sits below speech and above room noise, and the
     * clip is only dropped when the meter actually ran. */
    if (stt.metered && stt.peak < 0.10) {
      micPhase('');
      setStatus('소리가 안 들어왔습니다 · 전송 안 함', 'var(--con-warn)');
      return;
    }
    micPhase('transcribing');
    micTick('전사 중', 'var(--con-warn)', Date.now());
    window.ctbControl.send('/api/stt?session=' + encodeURIComponent(forSession), {
      method: 'POST', body: blob, headers: { 'Content-Type': mime },
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        return { status: res.status, body: body };
      });
    }).then(function (r) {
      micPhase('');
      if (state.session !== forSession) return;   /* switched away meanwhile */
      if (r.status !== 200) {
        setStatus('전사 실패 (' + r.status + ')' + (r.body.detail ? ' · ' + String(r.body.detail).slice(0, 80) : ''), 'var(--con-err)');
        return;
      }
      var text = (r.body.text || '').trim();
      if (!text) { setStatus('들리는 말이 없음', 'var(--con-warn)'); return; }
      sttDraft(text);
      /* The budget only matters as it runs out, so it is shown from the last
       * quarter on rather than kept as a number nobody reads. */
      var left = (typeof r.body.daily_limit === 'number' && typeof r.body.spent_today === 'number')
        ? r.body.daily_limit - r.body.spent_today : null;
      setStatus('초안 삽입됨 · 확인 후 Enter'
        + (left !== null && left < r.body.daily_limit * 0.25
           ? ' · 오늘 남은 음성 ' + Math.max(0, Math.round(left)) + '초' : ''),
        'var(--con-ok)');
    }).catch(function () {
      micPhase('');
      if (state.session === forSession) setStatus('전사 실패 · 네트워크', 'var(--con-err)');
    });
  }

  /* Into the box at the caret, with a space where two pieces of text meet,
   * saved as the session's draft like typed text, and flashed so the eye
   * finds it. Never submitted. */
  function sttDraft(text) {
    var box = el.input;
    if (!box) return;
    var v = box.value;
    var a = typeof box.selectionStart === 'number' ? box.selectionStart : v.length;
    var b = typeof box.selectionEnd === 'number' ? box.selectionEnd : a;
    var before = v.slice(0, a), after = v.slice(b);
    if (before && !/\s$/.test(before)) text = ' ' + text;
    if (after && !/^\s/.test(after)) text = text + ' ';
    box.value = before + text + after;
    var caret = before.length + text.length;
    try { box.setSelectionRange(caret, caret); } catch (e) { /* not focusable yet */ }
    if (state.session) { state.drafts[state.session] = box.value; saveDrafts(); }
    box.classList.remove('con-flash');
    void box.offsetWidth;
    box.classList.add('con-flash');
    /* A clip recorded before the new-session sheet went up can land after it:
     * focusing here would take the caret out of the sheet and put it in a
     * prompt box nobody can see, where the next Enter sends to a session. The
     * text still lands; the caret stays where the eyes are. */
    if (!sheetOpen()) box.focus();
  }

  function bindMic(btn) {
    var pressedAt = 0;
    btn.addEventListener('pointerdown', function (e) {
      if (e.button && e.button !== 0) return;
      e.preventDefault();
      pressedAt = Date.now();
      if (stt.rec) { sttStop(); pressedAt = 0; return; }   /* tap-toggle: second tap stops */
      stt.holding = true;
      /* The release must reach us even if the thumb drifts off the key while
       * talking; capture makes pointerup ours wherever it lands. */
      if (btn.setPointerCapture && e.pointerId != null) {
        try { btn.setPointerCapture(e.pointerId); } catch (err) { /* mouse without capture */ }
      }
      sttStart();
    });
    /* Keep the caret -- and the soft keyboard -- in the box. A button press
     * blurs the textarea on iOS unless the touch is claimed here, and the
     * keyboard folding away made the whole sheet jump on every recording. */
    btn.addEventListener('touchstart', function (e) { e.preventDefault(); }, { passive: false });
    btn.addEventListener('mousedown', function (e) { e.preventDefault(); });
    var up = function () {
      if (!stt.holding) return;
      stt.holding = false;
      /* A short press is a toggle: leave it recording until the next tap. */
      if (Date.now() - pressedAt < 350) {
        setStatus('녹음 중 · 탭하면 정지', 'var(--con-err)');
        return;
      }
      sttStop();
    };
    btn.addEventListener('pointerup', up);
    btn.addEventListener('pointercancel', up);
    btn.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  }

  /* --- actions ---------------------------------------------------------- */

  function post(path, body) {
    return window.ctbControl.send('/api/sessions/' +
      encodeURIComponent(state.session) + path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  function submit() {
    if (state.busy || !state.session) return;
    unhold();
    endWalk();
    var text = el.input.value;
    /* An empty box means the gesture was not "send this text" but "press
     * Enter" -- answering a prompt, accepting a default, nudging a pane. It
     * used to do nothing at all.
     *
     * It also makes a swallowed send self-correcting: when a line break lands
     * as a newline instead of a send, the box holds only whitespace, so the
     * next Enter is a plain Enter into the session. The whitespace is cleared
     * with it so it cannot pile up or be saved as a draft. */
    if (!text.trim()) {
      if (text) {
        el.input.value = '';
        delete state.drafts[state.session];
        saveDrafts();
      }
      sendKey('Enter');
      return;
    }
    /* The response can land after a switch; everything it touches is keyed to
     * the session the send was for, not to whatever is open when it returns. */
    var sent = state.session;
    /* Status belongs to the console it describes: if the user has switched
     * away by the time the answer lands, do not paint it over another
     * session's header. Alerts still fire -- a refusal is worth interrupting
     * for wherever you are. */
    var say = function (text, color) {
      if (state.session === sent) setStatus(text, color);
    };

    state.busy = true;
    el.send.disabled = true;
    say('전송 중…', 'var(--con-muted)');
    /* Remembered so the pending-input marking can say "this one is yours".
     * Only the last: what is sitting in the box now can only be the last thing
     * that went in, and a longer history would let an old send claim a line
     * that is no longer the same text. */
    state.sent = { session: sent, text: text };

    post('/prompt', { text: text })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (r) {
        if (r.status === 200) {
          delete state.drafts[sent];
          saveDrafts();
          if (state.session === sent) el.input.value = '';
          // confirmed:false means tmux accepted it but the pane did not change.
          // Say so instead of implying it landed.
          if (r.body.confirmed === false) {
            say('전송됨 · 화면 변화 없음', 'var(--con-warn)');
          } else {
            say('전송됨', 'var(--con-ok)');
          }
          pollTail();
        } else if (r.status === 409) {
          say('거부: ' + (r.body.reason || ''), 'var(--con-warn)');
          if (r.body.message) window.alert(r.body.message);
        } else if (r.status === 400) {
          say('차단됨', 'var(--con-err)');
          window.alert('위험 명령 패턴으로 차단되었습니다.');
        } else {
          say('실패 (' + r.status + ')', 'var(--con-err)');
          if (r.body.detail) window.alert(String(r.body.detail));
        }
      })
      .catch(function () { say('네트워크 오류', 'var(--con-err)'); })
      .then(function () {
        state.busy = false;
        el.send.disabled = false;
      });
  }

  /* `label` is what the status line calls the send. A shortcut names the
   * chord that was pressed -- "Shift+Tab 전송됨" -- because a key that does
   * nothing visible in the pane leaves no other sign that it was taken. */
  function sendKey(key, label) {
    if (!state.session) return;
    /* A hold is for reading; sending is the end of reading. Leaving the pane
     * frozen would hide the very thing the key was pressed to cause. */
    unhold();
    endWalk();
    var name = state.session;
    var what = label || ('키 ' + key);
    var before = { text: state.pending ? state.pending.text : '', ghost: state.ghost };
    setStatus(what + ' 전송…', 'var(--con-muted)');
    post('/key', { key: key })
      .then(function (res) {
        if (!res.ok) {
          setStatus(what + ' 전송 실패 (' + res.status + ')', 'var(--con-err)');
          return;
        }
        setStatus(what + ' 전송됨', 'var(--con-ok)');
        pollTail();
        keyEffect(name, what, before);
      })
      .catch(function () { setStatus('네트워크 오류', 'var(--con-err)'); });
  }

  /* What the key DID, not only that it went. "전송됨" says tmux took it; it
   * says nothing about the pane, and for Tab -- which accepts a prefill or
   * completes a path -- the pane is the whole point. The input box is read
   * before and after, and the line reports the difference: what the box
   * held, what it holds now. Read straight from the pane, not from the
   * rendered tail, so a reader scrolled up in history gets the same answer.
   * A few looks, spaced out: the pane redraws a beat after the key lands. */
  function keyEffect(name, what, before) {
    var looks = 0;
    function look() {
      if (state.session !== name) return;
      getJSON('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + TAIL_LINES)
        .then(function (data) {
          if (state.session !== name || !data || data.__status) return;
          var pending = findPendingInput((data.log || '').split('\n'));
          var after = { text: pending ? pending.text : '', ghost: data.ghost === true };
          /* A Tab that takes a ghost leaves the same characters in the box;
           * what changed is that they are now real. That counts. */
          var changed = after.text !== before.text
            || (before.ghost && !after.ghost && after.text);
          if (changed) {
            state.boxTouched = after.text || null;
            state.ghost = after.ghost;
            setStatus(what + ' 반영됨 · 입력창 ' + describeBox(before, after), 'var(--con-ok)');
            /* Repaint first -- forced, so it happens wherever the view sits
             * -- so the flashed line is the new one. */
            pollTail(true);
            setTimeout(flashPending, 400);
            return;
          }
          if (++looks < 3) { setTimeout(look, 500); return; }
          setStatus(what + ' 전송됨 · 입력창 변화 없음', 'var(--con-warn)');
        })
        .catch(function () { /* the status already says it was sent */ });
    }
    setTimeout(look, 350);
  }

  /* One short clause for the change: filled, cleared, or rewritten. The
   * text itself is on the screen a few lines up, so only its shape is named. */
  function describeBox(before, after) {
    if (typeof before === 'string') before = { text: before, ghost: false };
    if (typeof after === 'string') after = { text: after, ghost: false };
    if (!before.text && after.text) return '채워짐';
    if (before.text && !after.text) return '비워짐';
    if (before.text === after.text && before.ghost && !after.ghost) return '제안 확정됨';
    return '바뀜';
  }

  function flashPending() {
    if (!el.tail || !state.pending) return;
    for (var i = state.pending.index; i <= state.pending.end; i++) {
      var node = el.tail.children[i];
      if (!node) continue;
      node.classList.remove('con-flash');
      void node.offsetWidth;   /* restart the animation if it is still running */
      node.classList.add('con-flash');
    }
  }


  /* --- drafts ------------------------------------------------------------ */

  /* Drafts survived a session switch but not a reload: they lived only in
   * state.drafts. On a phone the console is closed by the OS as often as by
   * the user, so a half-typed instruction was routinely lost. Persisted per
   * session, written as it is typed rather than only on switch. */
  var DRAFT_KEY = 'ctb_console_drafts';

  function loadDrafts() {
    try {
      var raw = JSON.parse(localStorage.getItem(DRAFT_KEY));
      if (raw && typeof raw === 'object') state.drafts = raw;
    } catch (e) { /* unreadable or unavailable; start empty */ }
  }

  function saveDrafts() {
    try {
      /* Empty entries are not drafts, and would otherwise accumulate one key
       * per session ever opened. */
      var out = {};
      Object.keys(state.drafts).forEach(function (k) {
        if (state.drafts[k]) out[k] = state.drafts[k];
      });
      localStorage.setItem(DRAFT_KEY, JSON.stringify(out));
    } catch (e) { /* quota or private mode: the in-memory copy still works */ }
  }

  /* --- last-seen panes -------------------------------------------------- */

  /* What the console last painted, per session: in memory for the switch
   * back and forth, and in localStorage so a reopened PWA turns to the page
   * it was on. Text only, forty lines a session, capped at thirty sessions
   * (the oldest goes) -- a few hundred kilobytes at the most. */
  var TAIL_KEY = 'ctb_console_tails';
  var TAIL_KEEP = 30;

  function rememberTail(name, data) {
    var entry = { log: data.log || '', cols: data.cols || 0, ghost: data.ghost === true,
                  depth: state.depth, at: Date.now() };
    state.cache[name] = entry;
    try {
      var all = JSON.parse(localStorage.getItem(TAIL_KEY)) || {};
      all[name] = entry;
      var names = Object.keys(all).sort(function (a, b) { return all[b].at - all[a].at; });
      names.slice(TAIL_KEEP).forEach(function (n) { delete all[n]; });
      localStorage.setItem(TAIL_KEY, JSON.stringify(all));
    } catch (e) { /* quota or private mode: memory still works */ }
  }

  function recallTail(name) {
    if (state.cache[name]) return state.cache[name];
    try {
      var all = JSON.parse(localStorage.getItem(TAIL_KEY)) || {};
      if (all[name] && typeof all[name].log === 'string') return all[name];
    } catch (e) { /* unreadable */ }
    return null;
  }

  /* --- open / close ----------------------------------------------------- */

  /* focusInput: a session switch the user drove -- a chip click, a number
   * shortcut -- should leave them able to type immediately. Opening the
   * console does NOT pass it: on iOS the keyboard would cover the pane before
   * it has been read, which is why there is no autofocus on open. */
/* The sheet is fixed and full-bleed, but a fixed overlay does not stop the
   * document behind it from scrolling: a touch that lands anywhere the sheet
   * does not itself scroll, or that runs past the end of the tail, moves the
   * dashboard instead. Nothing behind the console is meant to be reachable
   * while it is open, so the page is parked -- position:fixed at its current
   * offset, which is the one lock iOS honours -- and put back exactly where
   * it was on close. overscroll-behavior handles the chaining case; this
   * handles the rest. */
  var LOCK_PROPS = ['position', 'top', 'left', 'right', 'width', 'overflow'];
  var pageLock = { active: false, x: 0, y: 0, prev: null };

  function lockPage() {
    if (pageLock.active) return;
    pageLock.x = window.pageXOffset || document.documentElement.scrollLeft || 0;
    pageLock.y = window.pageYOffset || document.documentElement.scrollTop || 0;
    /* Property by property, not the whole style attribute: the board writes
     * its theme colours inline on body, and restoring a snapshot would undo
     * anything set while the console was open. An empty string is a faithful
     * "this was not set". */
    pageLock.prev = {};
    LOCK_PROPS.forEach(function (prop) { pageLock.prev[prop] = document.body.style[prop]; });
    document.body.style.position = 'fixed';
    document.body.style.top = (-pageLock.y) + 'px';
    document.body.style.left = (-pageLock.x) + 'px';
    document.body.style.right = '0';
    document.body.style.width = '100%';
    document.body.style.overflow = 'hidden';
    pageLock.active = true;
  }

  function unlockPage() {
    if (!pageLock.active) return;
    pageLock.active = false;
    var prev = pageLock.prev || {};
    LOCK_PROPS.forEach(function (prop) { document.body.style[prop] = prev[prop] || ''; });
    window.scrollTo(pageLock.x, pageLock.y);
  }

    function show(name, focusInput) {
    build();
    loadDrafts();
    /* A half-typed prompt belongs to the session it was written for. Switching
     * used to leave it in the box, so the next 전송 would deliver it to whoever
     * was open now -- a prompt meant for one session landing in another. Park
     * the draft under its own session and restore that session's draft. */
    if (el.input) {
      if (state.session && state.session !== name) {
        state.drafts[state.session] = el.input.value;
      }
      if (state.session !== name) {
        el.input.value = state.drafts[name] || '';
      }
      saveDrafts();
    }
    /* Remember where we came from so Ctrl+Tab can bounce back -- the pair you
     * are actually working in is almost always two sessions, not nine. */
    if (state.session && state.session !== name) { state.prev = state.session; sttAbort(); }
    state.boxTouched = null;   /* the mark belongs to the box it was made in */
    /* The menu names one session; it must not survive a switch to another. */
    if (state.session !== name) closeQuadMenu();
    state.session = name;
    closeFind();
    /* The armed key was meant for the session that was open when it was
     * armed, not for whatever is open by the time it is pressed. */
    disarmSend(true);
    state.held = false;
    endWalk();
    state.lines = null;
    /* Another session, another pane width -- and the console is about to
     * resize this one. Nothing is joined until the next poll says how wide. */
    state.cols = 0;
    state.depth = TAIL_LINES;
    state.fitted = false;
    state.fails = 0;
    state.warned = false;
    state.growing = false;
    state.exhausted = false;
    state.hash = '';
    state.pinned = true;
    setFrozen(false);
    el.title.textContent = name.replace(/^claude[_-]/, '');
    /* The last pane this console painted for the session, if there is one,
     * goes up at once -- a switch between two sessions should feel like
     * turning a page, not like a first load. The poll that starts below
     * replaces it within a couple of seconds; until then it is marked. */
    var kept = recallTail(name);
    if (kept) {
      state.cols = kept.cols || 0;
      state.ghost = kept.ghost === true;
      state.depth = kept.depth || TAIL_LINES;
      renderTail(kept.log || '');
      el.tail.scrollTop = el.tail.scrollHeight;
      setStatus('마지막으로 본 화면 · 갱신 중…', 'var(--con-muted)');
    } else {
      el.tail.textContent = '불러오는 중…';
    }
    setStatus('');
    el.root.style.display = 'flex';
    lockPage();
    renderStrip();
    fetchOrder();
    fitViewport();
    fitKeys();
    startPolling();
    if (kept) pollTail(true);
    // Do not autofocus on open: on iOS that pops the keyboard before the pane
    // is read. A deliberate switch is different -- see focusInput.
    if (focusInput && el.input) {
      /* Cursor after any restored draft, not before it. */
      el.input.focus();
      var end = el.input.value.length;
      try { el.input.setSelectionRange(end, end); } catch (e) { /* not focusable yet */ }
    }
  }

  function hide() {
    stopPolling();
    sttAbort();
    if (el.input && state.session) {
      state.drafts[state.session] = el.input.value;
      saveDrafts();
    }
    state.session = null;
    /* The palette's lifetime is inside the console's. Left behind it covers the
     * whole grid at z-index 80 with no way out: Escape is gated on an open
     * console, and the ✕ is underneath it. */
    closeSearch();
    closeFind();
    disarmSend(true);
    state.held = false;
    endWalk();
    state.lines = null;
    setFrozen(false);
    hideHints();
    if (el.endPill) el.endPill.style.display = 'none';
    if (el.prevPill) el.prevPill.style.display = 'none';
    if (el.root) el.root.style.display = 'none';
    /* After the sheet is hidden, so it does not hand focus to a button that
     * is no longer on screen. */
    closeQuadMenu();
    unlockPage();
  }

  /* Stop polling when the tab is hidden -- a backgrounded phone should not keep
   * spawning capture-pane on the server. */
  document.addEventListener('visibilitychange', function () {
    /* A recording outlives the page going away, but nothing feeds it there:
     * the key stayed red and the clip never finished. Close it off instead --
     * what was said is transcribed rather than lost, and the mic is handed
     * back. Checked before the session guard: a clip is running or it is not. */
    if (document.hidden && stt.rec) {
      setStatus('\ud654\uba74\uc774 \uaebc\uc838 \ub179\uc74c\uc744 \ub9c8\uac10\ud569\ub2c8\ub2e4', 'var(--con-warn)');
      stt.holding = false;
      sttStop();
    }
    if (!state.session) return;
    if (document.hidden) stopPolling();
    else startPolling();
  });

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest && e.target.closest('[data-console-session]');
    if (!trigger) return;
    e.preventDefault();
    e.stopPropagation();
    show(trigger.getAttribute('data-console-session'));
  });

  /* Strip taps switch the console in place -- same sheet, new session. */
  /* click carries no pointer type, so record it from the press that precedes. */
  var lastPointerType = '';
  document.addEventListener('pointerdown', function (e) {
    lastPointerType = e.pointerType || '';
  }, true);

  document.addEventListener('click', function (e) {
    var chip = e.target.closest && e.target.closest('[data-switch-session]');
    if (!chip) return;
    e.preventDefault();
    e.stopPropagation();
    var name = chip.getAttribute('data-switch-session');
    if (name && name !== state.session) show(name, lastPointerType !== 'touch');
  });

  /* --- deep link -------------------------------------------------------- */

  /* Mirrors server.py _SESSION_NAME_RE. A name outside this set would be
   * rejected by every session route anyway, so opening a console for it would
   * only produce errors. */
  var SESSION_NAME_RE = /^[a-zA-Z0-9_\-:.]{1,64}$/;

  function openFromQuery() {
    var name;
    try {
      name = new URLSearchParams(window.location.search).get('session');
    } catch (e) {
      return;
    }
    if (!name || !SESSION_NAME_RE.test(name)) return;
    show(name);
    /* Drop the parameter so a reload (or a later share of the URL) does not
     * reopen the sheet unexpectedly. */
    if (window.history && window.history.replaceState) {
      window.history.replaceState({}, '', window.location.pathname);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', openFromQuery);
  } else {
    openFromQuery();
  }

  window.ctbConsole = {
    open: show,
    close: hide,
    /* The board's F / Ctrl+F: the palette is the board's search too. */
    openPalette: function () {
      if (searchOpen()) { search.input.focus(); search.input.select(); return; }
      hideHints();
      fetchOrder();
      openSearch();
    },
    paletteOpen: searchOpen,
    /* The dashboard's own shortcuts sit behind this sheet; they ask. */
    isOpen: function () { return !!state.session; },
    /* exposed for tests / debugging */
    _state: state,
    _openFromQuery: openFromQuery,
    _cleanLines: cleanLines,
    _splitLinks: splitLinks,
    _findPendingInput: findPendingInput,
    _findLastSubmitted: findLastSubmitted,
    _submittedLines: submittedLines,
    _pageTail: pageTail,
    _rowsNeeded: rowsNeeded,
    _planKeys: planKeys,
    /* build() reassigns el, so hand back the live object, not the one that
     * happened to be current when this table was built. */
    _els: function () { return el; },
    _lockPage: lockPage,
    _unlockPage: unlockPage,
    _stepSession: stepSession,
    _neighbourAfterClose: neighbourAfterClose,
    _linkifyLines: linkifyLines,
    _whenSettled: whenSettled,
    _renderStrip: renderStrip,
    _renderTail: renderTail,
    _sessionGone: sessionGone,
    _sendKeyName: sendKeyName,
    _sendArmed: sendArmed,
    _findMatches: findMatches,
    _openFind: openFind,
    _sttDraft: sttDraft,
    _setStatus: setStatus,
    /* Two pieces of in-flight state busy() reads, reachable so a test can put
     * the console in that state without a microphone or a live tmux. */
    _stt: function () { return stt; },
    _setClosing: function (v) { closing = !!v; },
    /* Whether something here is already holding the keyboard, the mic, or a
     * request that is going to move the console when it lands: the session
     * palette, the importance menu, a clip being recorded or a mic still
     * being acquired, a close or restore in flight (both call show() on
     * success, which switches session and takes the caret). Ctrl+N asks
     * before drawing the new-session sheet over the top of any of them. */
    busy: function () {
      return searchOpen() || quadMenuOpen() || findOpen()
        || !!stt.rec || stt.busy || closing;
    },
    _toggleQuadMenu: toggleQuadMenu,
    _closeQuadMenu: closeQuadMenu,
    _paintQuadBtn: paintQuadBtn,
    _el: function () { return el; },
    _describeBox: describeBox,
    _THEMES: THEMES,
    _noteScrolling: noteScrolling,
    _scrollInFlight: scrollInFlight,
    _setTouching: function (v) { touchUntil = v ? Date.now() + 60000 : 0; },
    _displayWidth: displayWidth,
    _matchSessions: matchSessions,
    SESSION_NAME_RE: SESSION_NAME_RE,
    POLL_MS: POLL_MS,
  };
})();
