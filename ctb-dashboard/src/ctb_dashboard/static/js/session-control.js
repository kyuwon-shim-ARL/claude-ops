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

  var TAIL_LINES = 40;
  var POLL_MS = 2000;

  var state = { session: null, timer: null, busy: false,
                lines: null, selStart: null, selEnd: null, order: null,
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
    var shiftHeld = false;
    input.addEventListener('keydown', function (e) {
      shiftHeld = e.shiftKey;
      var imeIsHandlingIt = e.isComposing || e.keyCode === 229;
      if (e.key === 'Enter' && !e.shiftKey && !imeIsHandlingIt) {
        e.preventDefault();
        submit();
      }
    });
    /* Mirror keydown: clears shiftHeld when Shift is released, so a prior
     * Shift press (e.g. for a tense consonant ㄲ) does not survive until the
     * next Enter on iOS where keydown events are sometimes skipped. */
    input.addEventListener('keyup', function (e) {
      shiftHeld = e.shiftKey;
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

    root.appendChild(strip);
    root.appendChild(header);
    root.appendChild(tail);
    root.appendChild(bar);
    root.appendChild(keys);
    root.appendChild(row);
    document.body.appendChild(root);

    el = { root: root, strip: strip, title: title, status: status, tail: tail,
           bar: bar, barLabel: barLabel, input: input, send: send };

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
    /* top:0 pins the head; moving the foot up by the keyboard overlap is what
     * shrinks the box, and the tail (flex:1) gives back the space. */
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
    fetch('/api/sessions', { headers: { 'Accept': 'application/json' } })
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
    list.forEach(function (item) {
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

  function updateBar() {
    var range = selectionRange();
    if (!range) {
      el.bar.style.display = 'none';
      return;
    }
    el.bar.style.display = 'flex';
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
    /* Selection was what paused the tail; resume now. */
    if (state.session && !state.timer) startPolling();
  }

  function pollTail() {
    if (!state.session) return;
    var name = state.session;
    fetch('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + TAIL_LINES, {
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
    if (!text.trim()) return;
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

  /* --- open / close ----------------------------------------------------- */

  function show(name) {
    build();
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
    }
    state.session = name;
    state.selStart = null;
    state.selEnd = null;
    state.lines = null;
    if (el.bar) el.bar.style.display = 'none';
    el.title.textContent = name.replace(/^claude[_-]/, '');
    el.tail.textContent = '불러오는 중…';
    setStatus('');
    el.root.style.display = 'flex';
    renderStrip();
    fetchOrder();
    fitViewport();
    startPolling();
    // Do not autofocus: on iOS that pops the keyboard before the pane is read.
  }

  function hide() {
    stopPolling();
    if (el.input && state.session) state.drafts[state.session] = el.input.value;
    state.session = null;
    state.selStart = null;
    state.selEnd = null;
    state.lines = null;
    if (el.bar) el.bar.style.display = 'none';
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
  document.addEventListener('click', function (e) {
    var chip = e.target.closest && e.target.closest('[data-switch-session]');
    if (!chip) return;
    e.preventDefault();
    e.stopPropagation();
    var name = chip.getAttribute('data-switch-session');
    if (name && name !== state.session) show(name);
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
