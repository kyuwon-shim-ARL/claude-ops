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
                lines: null, selStart: null, selEnd: null, order: null,
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
      '#ctb-console .con-rail{background:var(--con-tray);border-radius:14px;padding:4px}',
      /* The mic while it listens: a red key, pulsing, so a held finger can
       * see the recording is on without reading the status line. */
      '@keyframes con-listen{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.45)}50%{box-shadow:0 0 0 6px rgba(239,68,68,0)}}',
      '#ctb-console .con-mic[data-listening]{background:#ef4444!important;color:#fff!important;animation:con-listen 1.2s ease-out infinite}',
      '@media(prefers-reduced-motion:reduce){#ctb-console .con-mic[data-listening]{animation:none}}',
      '#ctb-console .con-recbar{position:absolute;left:0;right:0;top:0;bottom:0;z-index:3;',
      'display:flex;align-items:center;justify-content:center;gap:10px;border-radius:14px;',
      'font:700 15px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.01em;pointer-events:none;',
      'color:#fff;background:rgba(239,68,68,0.94);box-shadow:0 0 0 2px rgba(239,68,68,0.35)}',
      '#ctb-console .con-recbar[data-phase="transcribing"]{background:rgba(245,158,11,0.94);box-shadow:0 0 0 2px rgba(245,158,11,0.35)}',
      '#ctb-console .con-recbar b{font-family:\'JetBrains Mono\',monospace;font-weight:700;min-width:3.2em;text-align:left}',
      '#ctb-console .con-recbar i{width:10px;height:10px;border-radius:50%;background:#fff;animation:con-blink 1s steps(2,start) infinite}',
      '@keyframes con-blink{to{visibility:hidden}}',
      '@media(prefers-reduced-motion:reduce){#ctb-console .con-recbar i{animation:none}}',
      /* The mic and send keys stay clickable through the bar: it covers only the box. */
      '#ctb-console .con-recbar{right:96px}',
      '@media(max-width:480px){#ctb-console .con-recbar{right:88px}}',
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
      'overflow-x:auto', 'overflow-y:hidden',
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
    header.appendChild(find);
    header.appendChild(copy);
    header.appendChild(close);

    var tail = document.createElement('pre');
    tail.setAttribute('aria-live', 'polite');
    tail.className = 'con-well';
    tail.style.cssText = [
      'flex:1', 'min-height:120px', 'overflow:auto', 'margin:0 0 10px',
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

    /* Tap-to-select range. Tapping a line marks the start, tapping another
     * marks the end, and the bar offers a one-tap copy of exactly that span.
     * No drag, and -- unlike the marker convention this replaces -- nothing
     * the session's Claude has to cooperate with. */
    var bar = document.createElement('div');
    bar.style.cssText =
      'display:none;align-items:center;gap:8px;margin-bottom:8px;flex-shrink:0;' +
      'font-size:11px;color:var(--con-muted);';

    var barLabel = document.createElement('span');
    barLabel.style.cssText = 'flex:1;min-width:0;';

    var barCopy = document.createElement('button');
    barCopy.type = 'button';
    barCopy.textContent = '\ubcf5\uc0ac';
    styleBtn(barCopy, 'ok');
    barCopy.addEventListener('click', copySelection);

    var barClear = document.createElement('button');
    barClear.type = 'button';
    barClear.textContent = '\ud574\uc81c';
    styleBtn(barClear, '');
    barClear.addEventListener('click', clearSelection);

    bar.appendChild(barLabel);
    bar.appendChild(barCopy);
    bar.appendChild(barClear);

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
      ['y', 'y', '예'], ['n', 'n', '아니오'],
      ['1', '1', '1번'], ['2', '2', '2번'], ['3', '3', '3번'],
      ['4', '4', '4번'], ['5', '5', '5번'],
      [icon('up'), 'Up', '위'], [icon('down'), 'Down', '아래'],
      [icon('left'), 'Left', '왼쪽'], [icon('right'), 'Right', '오른쪽'],
      [icon('backspace'), 'BSpace', '한 글자 지우기'], [icon('tab'), 'Tab', 'Tab'],
      [icon('enter'), 'Enter', 'Enter'], ['esc', 'Escape', 'Escape — 진행 중인 작업 중단 · 메뉴 닫기'],
    ].forEach(function (spec) {
      var b = document.createElement('button');
      b.type = 'button';
      if (typeof spec[0] === 'string') b.textContent = spec[0];
      else b.appendChild(spec[0]);
      b.title = spec[2];
      b.setAttribute('aria-label', spec[2] + ' 키 전송');
      styleBtn(b, 'key');
      b.addEventListener('click', function () { sendKey(spec[1]); });
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
    keys.appendChild(clearLine);

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
        submit();
      }
    });
    input.addEventListener('keyup', function (e) {
      if (e.key === 'Enter' || e.key === 'Shift') shiftHeld = e.shiftKey;
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
    mic.className = 'con-mic';
    mic.appendChild(icon('mic', 18));
    mic.title = '누르고 말하기 · 짧게 탭하면 녹음 시작/정지 · 결과는 입력창에 초안으로만';
    mic.setAttribute('aria-label', '음성 입력');
    styleBtn(mic, '');
    mic.style.display = 'none';
    mic.style.minWidth = '44px';
    mic.style.touchAction = 'manipulation';
    bindMic(mic);

    row.appendChild(input);
    row.appendChild(mic);
    row.appendChild(send);

    /* The recording state, where the eye is: a red bar over the input row
     * with a running clock, not a line of small text elsewhere. Amber while
     * the clip is being transcribed. */
    row.style.position = 'relative';
    var recBar = document.createElement('div');
    recBar.className = 'con-recbar';
    recBar.setAttribute('role', 'status');
    recBar.setAttribute('aria-live', 'polite');
    recBar.style.display = 'none';
    row.appendChild(recBar);

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

    tailWrap.appendChild(tail);
    tailWrap.appendChild(frozen);

    root.appendChild(strip);
    sttInit();
    root.appendChild(header);
    root.appendChild(tailWrap);
    root.appendChild(bar);
    root.appendChild(status);
    root.appendChild(keys);
    root.appendChild(row);
    keepCaret(root, input);
    document.body.appendChild(root);

    el = { root: root, strip: strip, title: title, status: status, tail: tail, mic: mic, recBar: recBar,
           frozen: frozen, bar: bar, barLabel: barLabel, input: input,
           send: send, silent: silent };

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
    /* Delegated: 'click' (not touchstart) so a scroll gesture never selects. */
    tail.addEventListener('click', function (e) {
      /* A link click is a navigation, not the start of a copy range: without
       * this the tap opened the page AND froze the tail behind it. */
      if (e.target.closest && e.target.closest('[data-tail-link]')) return;
      var line = e.target.closest && e.target.closest('[data-line]');
      if (line) onLineTap(parseInt(line.getAttribute('data-line'), 10));
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
      if (e.key === 'Escape' && state.session) {
        if (searchOpen()) closeSearch();
        else if (state.selStart !== null) clearSelection();
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
    var typing = document.activeElement === el.input;
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
    error: '#ef4444', context_limit: '#a78bfa', idle: '#6b7280',
  };

  /* The dashboard publishes the order it renders; without it (a console opened
   * before the first paint, or from a deep link) fall back to the raw snapshot,
   * which is at least a list of live sessions. */
  function sessionOrder() {
    var list = window.ctbSessionOrder;
    if (Array.isArray(list) && list.length) return list;
    return state.order || [];
  }

  /* Every session, not just the ones the grid's filter left showing. The strip
   * and the number shortcuts mirror the grid on purpose -- they are the grid's
   * own shortcuts -- but a search that inherits a filter set behind a
   * full-bleed sheet, where it can be neither seen nor cleared, is a search
   * that lies about what exists. */
  function sessionCatalog() {
    var all = window.ctbSessionAll;
    if (Array.isArray(all) && all.length) return all;
    return sessionOrder();
  }

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

  function renderStrip() {
    paintSilentBadge();
    if (!el.strip) return;
    var list = sessionOrder();
    el.strip.textContent = '';
    if (!list.length) {
      el.strip.style.display = 'none';
      return;
    }
    el.strip.style.display = 'flex';

    var current = null;
    list.forEach(function (item, index) {
      var active = item.name === state.session;
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.setAttribute('data-switch-session', item.name);
      chip.setAttribute('aria-label', item.label + ' 세션으로 전환');
      if (active) chip.setAttribute('aria-current', 'true');
      /* Content-sized, not one-third of the sheet: three fixed slots wasted the
       * row on short names and forced a scroll to reach the fourth session.
       * Capped so one long name cannot take the whole bar. */
      chip.className = 'con-chip';
      var quad = window.ctbQuadOf && window.ctbQuadOf[item.name];
      if (quad) chip.setAttribute('data-quad', quad);

      var dot = document.createElement('span');
      dot.style.cssText = 'width:7px;height:7px;border-radius:50%;flex-shrink:0;' +
        'background:' + (STATE_DOT[item.state] || '#6b7280') + ';';

      var text = document.createElement('span');
      text.style.cssText = 'min-width:0;white-space:nowrap;overflow:hidden;' +
        'text-overflow:ellipsis;';
      text.textContent = item.branch ? item.label + ' ⎇' + item.branch : item.label;
      chip.title = quad ? item.name + ' · ' + (QUAD_LABELS[quad] || quad) : item.name;

      chip.appendChild(dot);
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
      el.strip.appendChild(chip);
      if (active) current = chip;
    });

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
    /* The palette owns the keyboard while it is up. Without this the digit
     * switched the console UNDERNEATH the overlay and put the caret in a
     * textarea nobody could see -- so the next Enter, typed at what looked
     * like a search box, would send a prompt to a live session. */
    if (searchOpen()) return;
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

  /* Ctrl/Cmd+` walks UP the rail one session at a time, from wherever the open one sits, wrapping at the top.
   * Ctrl/Cmd+Shift+` does the same over the 긴급+중요 (Q1) sessions only.
   *
   * The digits are for jumping to a session you can see; this is for working
   * through them. The board sorts what needs attention to the top, so starting
   * at the bottom of the numbered range and stepping down means the queue is
   * taken in order, without choosing at each step -- and with nothing open it
   * starts at the last numbered session rather than the first, which is where
   * that walk begins.
   *
   * The order is the same frozen snapshot the digits use, and this handler
   * deliberately does NOT release it: holding the accelerator and pressing `
   * repeatedly walks one list, instead of re-deriving the numbering from a
   * board that re-sorts under every step. */
  function stepDownSession(urgentOnly) {
    var list = hintOrder || sessionOrder();
    /* With Shift held the walk visits only the 긴급+중요 (Q1) sessions, in
     * rail order: the ones worth taking first, without stepping over the
     * rest by hand. From a session that is not Q1 it goes to the nearest Q1
     * above it. */
    if (urgentOnly) {
      var quadOf = window.ctbQuadOf || {};
      var here0 = -1;
      for (var k = 0; k < list.length; k++) {
        if (list[k].name === state.session) { here0 = k; break; }
      }
      var q1 = list.filter(function (it, idx) {
        return quadOf[it.name] === 'Q1' && idx !== here0;
      });
      if (!q1.length) return null;
      if (here0 === -1) return q1[q1.length - 1];
      var above = null;
      for (var j = 0; j < list.length && j < here0; j++) {
        if (quadOf[list[j].name] === 'Q1') above = list[j];
      }
      return above || q1[q1.length - 1];
    }
    var n = list.length;
    if (!n) return null;
    var here = -1;
    for (var i = 0; i < n; i++) {
      if (list[i].name === state.session) { here = i; break; }
    }
    /* From wherever the open session sits in the rail -- the whole rail,
     * not only the nine that carry numbers. It used to jump to slot 9 from
     * anything past it, which with a dozen sessions meant the tenth and
     * eleventh were skipped over every time. Nothing open: start at the end. */
    var next = here === -1 ? n - 1 : (here - 1 + n) % n;
    return list[next];
  }

  document.addEventListener('keydown', function (e) {
    if (searchOpen()) return;
    /* `code` as well as `key`: a layout where the key is not backquote still
     * reports Backquote for the physical key, and a dead-key layout may give
     * no `key` at all. Shifted, a US layout reports '~'. */
    if (e.key !== '`' && e.key !== '~' && e.code !== 'Backquote') return;
    if (!accelHeld(e)) return;
    e.preventDefault();
    /* Ctrl/Cmd+Shift+` walks the 긴급+중요 sessions only. */
    var item = stepDownSession(e.shiftKey);
    if (!item || (hintOrder && !inCatalog(item.name))) return;
    if (item.name === state.session) return;
    /* Closed console in the VSCode webview: the same rule the digits follow --
     * bring that session's terminal up, since the console there is read-only. */
    if (!state.session && IS_VSCODE && window.ctbFocusSession
        && window.ctbFocusSession(item.name)) return;
    show(item.name, true);
  });

  /* Ctrl/Cmd+Tab bounces between the last two sessions, the way Alt+Tab does.
   * It sits on the same modifier as the Ctrl+` walk on purpose: moving between
   * sessions is one gesture with the accelerator held down, and the hand never
   * has to swap modifiers mid-thought to get back to where it was.
   *
   * A browser tab keeps this chord for its own tab switching and the page
   * never sees it; an installed PWA window and the VSCode webview have no tab
   * strip, so there it arrives. In a plain browser tab the Ctrl+` walk is the
   * one that always gets through. */
  document.addEventListener('keydown', function (e) {
    if (!state.session || searchOpen() || e.key !== 'Tab') return;
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
    if (!state.session || searchOpen() || e.key !== 'Tab' || !e.shiftKey) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229) return;   /* the IME's key, not ours */
    e.preventDefault();
    sendKey('Tab', 'Shift+Tab');
  });

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
      var score = -1;
      if (label.indexOf(q) === 0) score = 0;
      else if (label.indexOf(q) !== -1) score = 1;
      else if (branch.indexOf(q) !== -1 || name.indexOf(q) !== -1) score = 2;
      else if (isSubsequence(q, label + ' ' + branch)) score = 3;
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

  var search = { root: null, input: null, list: null, hits: [], cursor: 0 };

  function searchOpen() {
    return !!(search.root && search.root.style.display !== 'none');
  }

  function buildSearch() {
    if (search.root) return;

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
    input.placeholder = '\uc138\uc158 \uac80\uc0c9 (\u2191\u2193 \uc120\ud0dd \u00b7 Enter \uc774\ub3d9 \u00b7 Esc \ub2eb\uae30)';
    input.style.cssText = [
      'width:100%', 'box-sizing:border-box', 'padding:12px 14px',
      'background:var(--con-well)', 'color:var(--con-text)', 'border:0',
      'border-bottom:1px solid var(--con-line)', 'outline:none',
      /* 16px keeps iOS from zooming the page in on focus. */
      'font-size:16px', "font-family:'JetBrains Mono',monospace",
    ].join(';');
    input.addEventListener('input', function () { renderResults(); });
    input.addEventListener('keydown', onSearchKey);

    var list = document.createElement('div');
    list.style.cssText =
      'overflow-y:auto;max-height:min(52vh,420px);-webkit-overflow-scrolling:touch;';
    list.addEventListener('click', function (e) {
      var row = e.target.closest && e.target.closest('[data-search-session]');
      if (row) pick(row.getAttribute('data-search-session'));
    });

    box.appendChild(input);
    box.appendChild(list);
    root.appendChild(box);
    document.body.appendChild(root);
    search.root = root;
    search.input = input;
    search.list = list;
  }

  function openSearch() {
    buildSearch();
    search.root.style.display = 'flex';
    search.input.value = '';
    search.cursor = 0;
    renderResults();
    search.input.focus();
  }

  function closeSearch() {
    if (!search.root) return;
    search.root.style.display = 'none';
    /* Give the caret back to the box the user was typing in. */
    if (el.input && state.session) el.input.focus();
  }

  function renderResults() {
    search.hits = matchSessions(sessionCatalog(), search.input.value);
    if (search.cursor >= search.hits.length) search.cursor = 0;
    search.list.textContent = '';

    if (!search.hits.length) {
      var empty = document.createElement('div');
      empty.textContent = '\uc77c\uce58\ud558\ub294 \uc138\uc158 \uc5c6\uc74c';
      empty.style.cssText =
        'padding:14px;color:var(--con-dim);font-size:12px;text-align:center;';
      search.list.appendChild(empty);
      return;
    }

    search.hits.forEach(function (item, i) {
      var active = i === search.cursor;
      var row = document.createElement('div');
      row.setAttribute('data-search-session', item.name);
      row.setAttribute('role', 'option');
      if (active) row.setAttribute('aria-selected', 'true');
      row.style.cssText = [
        'display:flex', 'align-items:center', 'gap:8px',
        'padding:9px 14px', 'cursor:pointer',
        "font-family:'JetBrains Mono',monospace", 'font-size:12px',
        'color:' + (active ? 'var(--con-text)' : 'var(--con-muted)'),
        'background:' + (active ? 'var(--con-active)' : 'transparent'),
      ].join(';');

      var dot = document.createElement('span');
      dot.style.cssText = 'width:7px;height:7px;border-radius:50%;flex-shrink:0;' +
        'background:' + (STATE_DOT[item.state] || '#6b7280') + ';';

      var text = document.createElement('span');
      text.style.cssText =
        'flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      text.textContent = item.branch
        ? item.label + ' \u2387' + item.branch : item.label;

      row.appendChild(dot);
      row.appendChild(text);
      if (item.name === state.session) {
        var here = document.createElement('span');
        here.textContent = '\ud604\uc7ac';
        here.style.cssText =
          'font-size:10px;color:var(--con-info);flex-shrink:0;';
        row.appendChild(here);
      }
      search.list.appendChild(row);
      if (active && row.scrollIntoView) {
        row.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function onSearchKey(e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!search.hits.length) return;
      var step = e.key === 'ArrowDown' ? 1 : -1;
      search.cursor =
        (search.cursor + step + search.hits.length) % search.hits.length;
      renderResults();
      return;
    }
    if (e.key === 'Enter') {
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
    closeSearch();
    if (name && name !== state.session) show(name, true);
  }

  document.addEventListener('keydown', function (e) {
    /* Only over an open console: on the grid, Ctrl+F stays the browser's find,
     * which is what searches the card labels there. */
    if (!state.session) return;
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
    if (!state.session || searchOpen()) return;
    if (e.key !== 'u' && e.key !== 'U') return;
    if (!e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (e.isComposing || e.keyCode === 229) return;
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

  }

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
   * -> {index, text} for the pending input, or null. Pure; tested. */
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
      return { index: i, text: text };
    }
    return null;
  }

  function renderTail(text) {
    var lines = text.split('\n');
    state.lines = lines;
    state.pending = findPendingInput(lines);
    el.tail.textContent = '';
    var frag = document.createDocumentFragment();
    var segments = linkifyLines(lines, state.cols);
    lines.forEach(function (line, i) {
      var div = document.createElement('div');
      div.setAttribute('data-line', String(i));
      div.style.cssText = 'padding:1px 3px;border-radius:3px;min-height:1.45em;';
      var parts = segments[i];
      if (parts.length === 1 && !parts[0].url) {
        div.textContent = line;
      } else {
        parts.forEach(function (part) {
          if (!part.url) {
            div.appendChild(document.createTextNode(part.text));
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
          div.appendChild(a);
        });
      }
      frag.appendChild(div);
    });
    el.tail.appendChild(frag);
    paintSelection();
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

  function selectionRange() {
    if (state.selStart === null) return null;
    var end = state.selEnd === null ? state.selStart : state.selEnd;
    return [Math.min(state.selStart, end), Math.max(state.selStart, end)];
  }

  function paintSelection() {
    var range = selectionRange();
    var pending = state.pending;
    var nodes = el.tail.querySelectorAll('[data-line]');
    for (var i = 0; i < nodes.length; i++) {
      var inRange = range && i >= range[0] && i <= range[1];
      /* A copy range the reader made outranks the marking: it is the thing
       * they are doing right now. */
      if (inRange) {
        nodes[i].style.background = 'rgba(52,211,153,0.18)';
        nodes[i].style.boxShadow = 'inset 2px 0 0 #34d399';
        nodes[i].title = '';
        continue;
      }
      /* Blue: text is sitting in the box, unsent. Green: the last key
       * changed what sits there (a Tab took the prefill, a key cleared it),
       * held until the box changes again -- so before and after a key look
       * different, not just "something is there" both times. Amber is the
       * board's waiting colour and had nothing to do with either. */
      if (pending && i === pending.index) {
        var touched = state.boxTouched !== null && state.boxTouched === pending.text;
        /* Grey, dashed edge: a ghost suggestion, not yet anyone's -- a Tab
         * would take it. Blue: real text waiting to be sent. Green: the
         * last key changed the box. The server reads the dim attribute the
         * plain capture drops, so ghost and typed no longer look the same. */
        var ghost = !touched && state.ghost;
        nodes[i].style.background = touched ? 'rgba(16,185,129,0.14)'
          : ghost ? 'rgba(107,114,128,0.10)' : 'rgba(37,99,235,0.10)';
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

  function onLineTap(index) {
    if (isNaN(index)) return;

    /* A completed range: the next tap starts a new one rather than extending
     * an old selection the user has probably forgotten about. */
    if (state.selStart === null || state.selEnd !== null) {
      state.selStart = index;
      state.selEnd = null;
      /* Freeze the tail: lines must not shift under a finger mid-selection. */
      stopPolling();
    } else {
      state.selEnd = index;
    }
    paintSelection();
    updateBar();
  }

  /* Called from every path that starts or ends a selection -- clearing it,
   * switching session, closing the sheet -- so none of them can leave the
   * console looking frozen while it is in fact live. */
  function setFrozen(on) {
    if (el.frozen) el.frozen.style.display = on ? 'inline-flex' : 'none';
    /* The well has no border; the freeze shows as an amber ring in the
     * shadow channel, on top of the well's own edge. */
    if (el.tail) el.tail.style.boxShadow = on
      ? 'var(--con-well-edge), inset 0 0 0 2px rgba(245,158,11,0.55)' : '';
  }

  function updateBar() {
    var range = selectionRange();
    if (!range) {
      el.bar.style.display = 'none';
      setFrozen(false);
      return;
    }
    el.bar.style.display = 'flex';
    setFrozen(true);
    var count = range[1] - range[0] + 1;
    el.barLabel.textContent = state.selEnd === null
      ? '\uc2dc\uc791 \uc9c0\uc815\ub428 \u2014 \ub05d\ub098\ub294 \uc904\uc744 \ud0ed\ud558\uc138\uc694 (\uac31\uc2e0 \uc77c\uc2dc\uc815\uc9c0)'
      : count + '\uc904 \uc120\ud0dd\ub428 (\uac31\uc2e0 \uc77c\uc2dc\uc815\uc9c0)';
  }

  function copySelection() {
    var range = selectionRange();
    if (!range || !state.lines) return;
    var text = cleanLines(state.lines.slice(range[0], range[1] + 1));
    copyText(text, (range[1] - range[0] + 1) + '\uc904 \ubcf5\uc0ac\ub428');
  }

  function clearSelection() {
    state.selStart = null;
    state.selEnd = null;
    if (el.tail) paintSelection();
    if (el.bar) el.bar.style.display = 'none';
    setFrozen(false);
    /* Selection was what paused the tail; resume now. */
    if (state.session && !state.timer) startPolling();
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
        state.hash = data.hash || '';
        /* A live selection wins over a refresh: repainting would move the
         * chosen lines out from under the user. */
        if (state.selStart !== null) return;
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
  function growTail() {
    if (!state.session || state.growing || state.exhausted) return;
    if (state.selStart !== null) return;   /* a frozen selection stays frozen */
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
          if (state.session !== name || state.selStart !== null) return;
          state.cols = data.cols || 0;
          state.hash = data.hash || '';
          var before = state.lines ? state.lines.length : 0;
          var fromBottom = el.tail.scrollHeight - el.tail.scrollTop;
          renderTail(data.log || '');
          rememberTail(name, data);
          el.tail.scrollTop = el.tail.scrollHeight - fromBottom;
          var gained = (state.lines ? state.lines.length : 0) - before;
          if (gained <= 0) {
            /* The pane has no more history: stop asking on every scroll. */
            state.exhausted = true;
            state.depth = was;
            setStatus('더 이상 이전 내용이 없습니다', 'var(--con-muted)');
          } else {
            setStatus('이전 ' + gained + '줄 불러옴', 'var(--con-ok)');
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

  /* --- speech to text ---------------------------------------------------- */

  /* Hold the key and talk; let go and the clip goes to /api/stt. A short tap
   * (under 350ms) starts a recording that the next tap stops -- a long
   * sentence with the finger off the glass. Either way the words land in the
   * input box as a draft, appended at the caret, and nothing is sent: the
   * transcript can be wrong, and Enter is the check. */
  var stt = { rec: null, stream: null, chunks: [], startedAt: 0, holding: false,
              enabled: false, busy: false };

  var recTick = null;
  function recBarShow(phase, text) {
    var bar = el.recBar;
    if (!bar) return;
    bar.textContent = '';
    bar.setAttribute('data-phase', phase);
    if (phase === 'recording') {
      var blink = document.createElement('i');
      var clock = document.createElement('b');
      clock.textContent = '0:00';
      bar.appendChild(blink);
      bar.appendChild(clock);
      bar.appendChild(document.createTextNode(text));
      if (recTick) clearInterval(recTick);
      var paintClock = function () {
        var sec = Math.floor((Date.now() - stt.startedAt) / 1000);
        clock.textContent = Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
      };
      recTick = setInterval(paintClock, 250);
    } else {
      bar.appendChild(document.createTextNode(text));
    }
    bar.style.display = 'flex';
  }
  function recBarHide() {
    if (recTick) { clearInterval(recTick); recTick = null; }
    if (el.recBar) el.recBar.style.display = 'none';
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
      if (el.mic) el.mic.setAttribute('data-listening', '');
      recBarShow('recording', stt.holding ? '녹음 중 · 손을 떼면 전사' : '녹음 중 · 탭하면 정지');
      if (navigator.vibrate) { try { navigator.vibrate(15); } catch (e) { /* no haptics */ } }
      setStatus('듣는 중…', 'var(--con-err)');
    }).catch(function (err) {
      stt.busy = false;
      var denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
      setStatus(denied ? '마이크 권한이 거부됨' : '마이크를 열 수 없음', 'var(--con-err)');
    });
  }

  function sttStop() {
    var rec = stt.rec;
    if (!rec) return;
    if (el.mic) el.mic.removeAttribute('data-listening');
    if (rec.state !== 'inactive') rec.stop(); else sttFinish();
  }

  /* Closing or switching mid-recording: drop the clip, it was for a session
   * that is no longer in front of the user. */
  function sttAbort() {
    var rec = stt.rec;
    if (!rec) return;
    if (el.mic) el.mic.removeAttribute('data-listening');
    recBarHide();
    stt.holding = false;
    rec.removeEventListener('stop', sttFinish);
    if (rec.state !== 'inactive') { try { rec.stop(); } catch (e) { /* already */ } }
    sttRelease();
  }

  function sttRelease() {
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
    if (held < 400 || blob.size < 1200) { recBarHide(); setStatus('', ''); return; }
    recBarShow('transcribing', '전사 중…');
    setStatus('전사 중…', 'var(--con-muted)');
    window.ctbControl.send('/api/stt?session=' + encodeURIComponent(forSession), {
      method: 'POST', body: blob, headers: { 'Content-Type': mime },
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        return { status: res.status, body: body };
      });
    }).then(function (r) {
      recBarHide();
      if (state.session !== forSession) return;   /* switched away meanwhile */
      if (r.status !== 200) {
        setStatus('전사 실패 (' + r.status + ')' + (r.body.detail ? ' · ' + String(r.body.detail).slice(0, 80) : ''), 'var(--con-err)');
        return;
      }
      var text = (r.body.text || '').trim();
      if (!text) { setStatus('들리는 말이 없음', 'var(--con-warn)'); return; }
      sttDraft(text);
      setStatus('초안 삽입됨 · 확인 후 Enter', 'var(--con-ok)');
    }).catch(function () {
      recBarHide();
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
    box.focus();
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
        if (stt.rec) recBarShow('recording', '녹음 중 · 탭하면 정지');
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
    var node = el.tail.children[state.pending.index];
    if (!node) return;
    node.classList.remove('con-flash');
    void node.offsetWidth;   /* restart the animation if it is still running */
    node.classList.add('con-flash');
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
    state.session = name;
    state.selStart = null;
    state.selEnd = null;
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
    if (el.bar) el.bar.style.display = 'none';
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
    renderStrip();
    fetchOrder();
    fitViewport();
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
    state.selStart = null;
    state.selEnd = null;
    state.lines = null;
    if (el.bar) el.bar.style.display = 'none';
    setFrozen(false);
    hideHints();
    if (el.root) el.root.style.display = 'none';
  }

  /* Stop polling when the tab is hidden -- a backgrounded phone should not keep
   * spawning capture-pane on the server. */
  document.addEventListener('visibilitychange', function () {
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
    /* The dashboard's own shortcuts sit behind this sheet; they ask. */
    isOpen: function () { return !!state.session; },
    /* exposed for tests / debugging */
    _state: state,
    _openFromQuery: openFromQuery,
    _cleanLines: cleanLines,
    _splitLinks: splitLinks,
    _findPendingInput: findPendingInput,
    _stepDownSession: stepDownSession,
    _linkifyLines: linkifyLines,
    _whenSettled: whenSettled,
    _renderStrip: renderStrip,
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
