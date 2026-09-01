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
                depth: TAIL_LINES, growing: false, exhausted: false,
                drafts: {} };
  var el = {};

  /* --- markup ------------------------------------------------------------ */

  function build() {
    if (el.root) return;

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
      'background:#0b1220', 'color:#e5e7eb',
      'font-family:ui-sans-serif,system-ui,sans-serif',
    ].join(';');

    /* Switcher strip: the sheet used to open with dead space above it, and
     * changing session meant closing, finding the card, tapping again. Chips
     * are sized to their names and the rail scrolls horizontally, in the grid's
     * own order (recency/state), flat — worktrees are not grouped here.
     * makePannable() adds the wheel and drag affordances a mouse needs. */
    var strip = document.createElement('div');
    strip.style.cssText = [
      'display:flex', 'gap:6px', 'flex-shrink:0', 'margin-bottom:8px',
      'overflow-x:auto', 'overflow-y:hidden',
      'scroll-snap-type:x proximity', '-webkit-overflow-scrolling:touch',
      'scrollbar-width:none',
    ].join(';');
    makePannable(strip);

    var header = document.createElement('div');
    header.style.cssText =
      'display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-shrink:0;';

    var title = document.createElement('div');
    title.style.cssText =
      "flex:1;min-width:0;font-family:'JetBrains Mono',monospace;font-size:13px;" +
      'font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';

    var status = document.createElement('span');
    status.style.cssText = 'font-size:11px;color:#9ca3af;flex-shrink:0;';

    var copy = document.createElement('button');
    copy.type = 'button';
    copy.textContent = '\ud83d\udccb';
    copy.title = '\ud654\uba74 \ub0b4\uc6a9 \ubcf5\uc0ac';
    copy.setAttribute('aria-label', '\ud654\uba74 \ub0b4\uc6a9 \ubcf5\uc0ac');
    copy.style.cssText = btnCss('#1f2937', '36px');
    copy.addEventListener('click', copyTail);

    var close = document.createElement('button');
    close.type = 'button';
    close.textContent = '✕';
    close.setAttribute('aria-label', '콘솔 닫기');
    close.style.cssText = btnCss('#1f2937', '36px');
    close.addEventListener('click', hide);

    header.appendChild(title);
    header.appendChild(status);
    header.appendChild(copy);
    header.appendChild(close);

    var tail = document.createElement('pre');
    tail.setAttribute('aria-live', 'polite');
    tail.style.cssText = [
      'flex:1', 'min-height:120px', 'overflow:auto', 'margin:0 0 8px',
      'padding:8px', 'border-radius:10px', 'background:#020617',
      'border:1px solid #1f2937',
      "font-family:'JetBrains Mono',monospace", 'font-size:11px',
      'line-height:1.45', 'white-space:pre-wrap', 'word-break:break-word',
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
      'font-size:11px;color:#9ca3af;';

    var barLabel = document.createElement('span');
    barLabel.style.cssText = 'flex:1;min-width:0;';

    var barCopy = document.createElement('button');
    barCopy.type = 'button';
    barCopy.textContent = '\ubcf5\uc0ac';
    barCopy.style.cssText = btnCss('#173a2a', 'auto') +
      'padding:6px 14px;font-weight:600;color:#34d399;border-color:rgba(52,211,153,0.45);';
    barCopy.addEventListener('click', copySelection);

    var barClear = document.createElement('button');
    barClear.type = 'button';
    barClear.textContent = '\ud574\uc81c';
    barClear.style.cssText = btnCss('#1f2937', 'auto') + 'padding:6px 12px;';
    barClear.addEventListener('click', clearSelection);

    bar.appendChild(barLabel);
    bar.appendChild(barCopy);
    bar.appendChild(barClear);

    /* Keys first: answering a permission prompt is the thing you most often
     * need in a hurry, and send_prompt refuses while one is pending. */
    var keys = document.createElement('div');
    keys.style.cssText =
      'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;flex-shrink:0;';
    [
      ['y', 'y', '예'], ['n', 'n', '아니오'],
      ['1', '1', '1번'], ['2', '2', '2번'], ['3', '3', '3번'],
      ['4', '4', '4번'], ['5', '5', '5번'],
      ['↵', 'Enter', 'Enter'], ['esc', 'Escape', 'Escape'],
      ['⇥', 'Tab', 'Tab'],
      ['↑', 'Up', '위'], ['↓', 'Down', '아래'],
      ['←', 'Left', '왼쪽'], ['→', 'Right', '오른쪽'],
    ].forEach(function (spec) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = spec[0];
      b.title = spec[2];
      b.setAttribute('aria-label', spec[2] + ' 키 전송');
      b.style.cssText = btnCss('#111827', 'auto') + 'padding:6px 11px;';
      b.addEventListener('click', function () { sendKey(spec[1]); });
      keys.appendChild(b);
    });

    var stop = document.createElement('button');
    stop.type = 'button';
    stop.textContent = '⛔ 중단';
    stop.setAttribute('aria-label', '작업 중단');
    stop.style.cssText =
      btnCss('#3f1d1d', 'auto') + 'padding:6px 11px;margin-left:auto;';
    stop.addEventListener('click', interrupt);
    keys.appendChild(stop);

    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:8px;align-items:flex-end;flex-shrink:0;';

    var input = document.createElement('textarea');
    input.rows = 2;
    input.placeholder = '지시 입력 (Enter 전송 · Shift+Enter 줄바꿈)';
    input.setAttribute('aria-label', '프롬프트 입력');
    input.style.cssText = [
      'flex:1', 'resize:none', 'padding:9px 10px', 'border-radius:10px',
      'background:#020617', 'color:#e5e7eb', 'border:1px solid #374151',
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
    send.textContent = '전송';
    send.setAttribute('aria-label', '프롬프트 전송');
    send.style.cssText = btnCss('#1d4ed8', 'auto') + 'padding:10px 16px;font-weight:600;';
    send.addEventListener('click', submit);

    row.appendChild(input);
    row.appendChild(send);

    /* The pause a selection causes was invisible: the tail simply stopped
     * growing, which reads as a dead console rather than a held one. The badge
     * sits over the tail, where the eye already is -- the bar's own
     * "(갱신 일시정지)" text is below the fold of attention. */
    var tailWrap = document.createElement('div');
    tailWrap.style.cssText =
      'position:relative;display:flex;flex-direction:column;flex:1;min-height:0;';

    var frozen = document.createElement('div');
    frozen.textContent = '\u23f8 \uac31\uc2e0 \uc815\uc9c0\ub428';
    frozen.style.cssText = [
      'display:none', 'position:absolute', 'top:6px', 'right:10px',
      'padding:3px 9px', 'border-radius:99px', 'pointer-events:none',
      'font-size:10px', 'font-weight:700', 'letter-spacing:0.02em',
      'background:rgba(245,158,11,0.16)', 'color:#fbbf24',
      'border:1px solid rgba(245,158,11,0.5)',
      'backdrop-filter:blur(4px)', '-webkit-backdrop-filter:blur(4px)',
    ].join(';');

    tailWrap.appendChild(tail);
    tailWrap.appendChild(frozen);

    root.appendChild(strip);
    root.appendChild(header);
    root.appendChild(tailWrap);
    root.appendChild(bar);
    root.appendChild(keys);
    root.appendChild(row);
    document.body.appendChild(root);

    el = { root: root, strip: strip, title: title, status: status, tail: tail,
           frozen: frozen, bar: bar, barLabel: barLabel, input: input,
           send: send };

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
    /* Reaching the top is the request for more history -- no button to find,
     * and it matches how every chat scrollback behaves. */
    tail.addEventListener('scroll', function () {
      if (tail.scrollTop > 24) return;
      /* Opening a session empties the tail to show '불러오는 중…', which drops
       * scrollTop to 0 and fires this -- a scroll the user never made, which
       * used to deepen the window before the first line had even arrived.
       * A tail with nothing to scroll cannot have been scrolled. */
      if (!state.lines || tail.scrollHeight <= tail.clientHeight + 8) return;
      growTail();
    });
    /* Delegated: 'click' (not touchstart) so a scroll gesture never selects. */
    tail.addEventListener('click', function (e) {
      var line = e.target.closest && e.target.closest('[data-line]');
      if (line) onLineTap(parseInt(line.getAttribute('data-line'), 10));
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && state.session) {
        if (state.selStart !== null) clearSelection();
        else hide();
      }
    });
  }

  function btnCss(bg, size) {
    return [
      'background:' + bg, 'color:#e5e7eb', 'border:1px solid #374151',
      'border-radius:9px', 'cursor:pointer', 'font-size:12px',
      'touch-action:manipulation', 'flex-shrink:0',
      size !== 'auto' ? 'width:' + size + ';height:' + size : '',
      'display:inline-flex', 'align-items:center', 'justify-content:center',
    ].filter(Boolean).join(';') + ';';
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

  function renderStrip() {
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
      chip.style.cssText = [
        'flex:0 0 auto', 'max-width:45%', 'scroll-snap-align:start',
        'display:flex', 'align-items:center', 'gap:5px',
        'padding:5px 8px', 'border-radius:9px', 'cursor:pointer',
        'text-align:left', 'overflow:hidden',
        'touch-action:manipulation',
        'background:' + (active ? '#1e3a8a' : '#111827'),
        'border:1px solid ' + (active ? '#3b82f6' : '#1f2937'),
        'color:' + (active ? '#e5e7eb' : '#9ca3af'),
      ].join(';');

      var dot = document.createElement('span');
      dot.style.cssText = 'width:7px;height:7px;border-radius:50%;flex-shrink:0;' +
        'background:' + (STATE_DOT[item.state] || '#6b7280') + ';';

      var text = document.createElement('span');
      text.style.cssText = "min-width:0;font-family:'JetBrains Mono',monospace;" +
        'font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;' +
        'text-overflow:ellipsis;';
      text.textContent = item.branch ? item.label + ' ⎇' + item.branch : item.label;
      chip.title = item.name;

      chip.appendChild(dot);
      if (index < HINT_MAX) {
        var num = document.createElement('b');
        num.setAttribute('data-numhint', '');
        num.textContent = String(index + 1);
        num.style.cssText = "font-family:'JetBrains Mono',monospace;" +
          'font-size:9px;font-weight:700;color:#fbbf24;flex-shrink:0;' +
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

  function hintsVisible() {
    return accelDown;
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
    var list = sessionOrder();
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
        'color:#fbbf24;padding:2px 7px;border-radius:7px;pointer-events:none;' +
        'background:rgba(15,13,20,0.92);border:1px solid rgba(245,158,11,0.55);';
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
    paintHints();
    if (!hintTimer) hintTimer = setInterval(paintHints, 400);
  }

  function hideHints() {
    if (!accelDown) return;
    accelDown = false;
    if (hintTimer) { clearInterval(hintTimer); hintTimer = null; }
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
    var slot = slotOf(e.key);
    if (slot === -1) return;
    var item = sessionOrder()[slot];
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

  /* Shift+Tab bounces between the last two sessions, the way Alt+Tab does.
   * Bare, with no accelerator: inside the sheet Tab has no job worth keeping --
   * moving focus backwards out of the prompt box leads nowhere useful -- and
   * the ⇥ that the pane needs is sent by its own button, not by the key. */
  document.addEventListener('keydown', function (e) {
    if (!state.session || e.key !== 'Tab' || !e.shiftKey) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    e.preventDefault();
    if (!state.prev || state.prev === state.session) return;
    show(state.prev, true);
  });

  document.addEventListener('keyup', function (e) {
    if (!hintsVisible()) return;
    if (e.key === 'Control' || e.key === 'Meta' || e.key === 'Alt') hideHints();
  });

  /* Alt-tabbing away leaves the modifier "held" forever otherwise. */
  window.addEventListener('blur', hideHints);

  /* --- status line ------------------------------------------------------- */

  function setStatus(text, color) {
    if (!el.status) return;
    el.status.textContent = text || '';
    el.status.style.color = color || '#9ca3af';
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
                ok ? '#34d399' : '#fbbf24');
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

  function renderTail(text) {
    var lines = text.split('\n');
    state.lines = lines;
    el.tail.textContent = '';
    var frag = document.createDocumentFragment();
    lines.forEach(function (line, i) {
      var div = document.createElement('div');
      div.setAttribute('data-line', String(i));
      div.style.cssText = 'padding:1px 3px;border-radius:3px;min-height:1.45em;';
      div.textContent = line;
      frag.appendChild(div);
    });
    el.tail.appendChild(frag);
    paintSelection();
  }

  function selectionRange() {
    if (state.selStart === null) return null;
    var end = state.selEnd === null ? state.selStart : state.selEnd;
    return [Math.min(state.selStart, end), Math.max(state.selStart, end)];
  }

  function paintSelection() {
    var range = selectionRange();
    var nodes = el.tail.querySelectorAll('[data-line]');
    for (var i = 0; i < nodes.length; i++) {
      var inRange = range && i >= range[0] && i <= range[1];
      nodes[i].style.background = inRange ? 'rgba(52,211,153,0.18)' : '';
      nodes[i].style.boxShadow = inRange ? 'inset 2px 0 0 #34d399' : '';
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
    if (el.frozen) el.frozen.style.display = on ? 'block' : 'none';
    if (el.tail) el.tail.style.borderColor = on ? 'rgba(245,158,11,0.55)' : '#1f2937';
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

  function pollTail() {
    if (!state.session) return;
    var name = state.session;
    fetch(api('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + state.depth), {
      headers: { 'Accept': 'application/json' },
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || state.session !== name) return;
        /* A live selection wins over a refresh: repainting would move the
         * chosen lines out from under the user. */
        if (state.selStart !== null) return;
        var atBottom =
          el.tail.scrollTop + el.tail.clientHeight >= el.tail.scrollHeight - 24;
        renderTail(data.log || '');
        if (atBottom) el.tail.scrollTop = el.tail.scrollHeight;
      })
      .catch(function () { /* transient; next tick retries */ });
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
    setStatus('이전 내용 불러오는 중…', '#9ca3af');

    fetch(api('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + state.depth), {
      headers: { 'Accept': 'application/json' },
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || state.session !== name) return;
        var before = state.lines ? state.lines.length : 0;
        var fromBottom = el.tail.scrollHeight - el.tail.scrollTop;
        renderTail(data.log || '');
        el.tail.scrollTop = el.tail.scrollHeight - fromBottom;
        var gained = (state.lines ? state.lines.length : 0) - before;
        if (gained <= 0) {
          /* The pane has no more history: stop asking on every scroll. */
          state.exhausted = true;
          state.depth = was;
          setStatus('더 이상 이전 내용이 없습니다', '#9ca3af');
        } else {
          setStatus('이전 ' + gained + '줄 불러옴', '#34d399');
        }
      })
      .catch(function () { setStatus('불러오기 실패', '#ef4444'); })
      .then(function () { state.growing = false; });
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
    say('전송 중…', '#9ca3af');

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
            say('전송됨 · 화면 변화 없음', '#fbbf24');
          } else {
            say('전송됨', '#34d399');
          }
          pollTail();
        } else if (r.status === 409) {
          say('거부: ' + (r.body.reason || ''), '#fbbf24');
          if (r.body.message) window.alert(r.body.message);
        } else if (r.status === 400) {
          say('차단됨', '#ef4444');
          window.alert('위험 명령 패턴으로 차단되었습니다.');
        } else {
          say('실패 (' + r.status + ')', '#ef4444');
          if (r.body.detail) window.alert(String(r.body.detail));
        }
      })
      .catch(function () { say('네트워크 오류', '#ef4444'); })
      .then(function () {
        state.busy = false;
        el.send.disabled = false;
      });
  }

  function sendKey(key) {
    if (!state.session) return;
    setStatus('키 ' + key + ' 전송…', '#9ca3af');
    post('/key', { key: key })
      .then(function (res) {
        setStatus(res.ok ? '키 ' + key + ' 전송됨' : '키 전송 실패 (' + res.status + ')',
                  res.ok ? '#34d399' : '#ef4444');
        pollTail();
      })
      .catch(function () { setStatus('네트워크 오류', '#ef4444'); });
  }

  function interrupt() {
    if (!state.session) return;
    setStatus('중단 신호 전송…', '#9ca3af');
    post('/interrupt')
      .then(function (res) {
        setStatus(res.ok ? '중단 신호 전송됨' : '중단 실패 (' + res.status + ')',
                  res.ok ? '#34d399' : '#ef4444');
        pollTail();
      })
      .catch(function () { setStatus('네트워크 오류', '#ef4444'); });
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
    /* Remember where we came from so Shift+Tab can bounce back -- the pair you
     * are actually working in is almost always two sessions, not nine. */
    if (state.session && state.session !== name) state.prev = state.session;
    state.session = name;
    state.selStart = null;
    state.selEnd = null;
    state.lines = null;
    state.depth = TAIL_LINES;
    state.growing = false;
    state.exhausted = false;
    if (el.bar) el.bar.style.display = 'none';
    setFrozen(false);
    el.title.textContent = name.replace(/^claude[_-]/, '');
    el.tail.textContent = '불러오는 중…';
    setStatus('');
    el.root.style.display = 'flex';
    renderStrip();
    fetchOrder();
    fitViewport();
    startPolling();
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
    if (el.input && state.session) {
      state.drafts[state.session] = el.input.value;
      saveDrafts();
    }
    state.session = null;
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
    /* exposed for tests / debugging */
    _state: state,
    _openFromQuery: openFromQuery,
    _cleanLines: cleanLines,
    SESSION_NAME_RE: SESSION_NAME_RE,
    POLL_MS: POLL_MS,
  };
})();
