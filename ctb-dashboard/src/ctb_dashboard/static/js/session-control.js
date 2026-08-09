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
                lines: null, selStart: null, selEnd: null };
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
      'position:fixed', 'left:0', 'right:0', 'bottom:0', 'z-index:60',
      'display:none', 'flex-direction:column',
      'max-height:88vh', 'padding:10px 12px 14px',
      'border-radius:18px 18px 0 0',
      'background:#0b1220', 'color:#e5e7eb',
      'border-top:1px solid #1f2937',
      'box-shadow:0 -12px 40px rgba(0,0,0,0.55)',
      'font-family:ui-sans-serif,system-ui,sans-serif',
    ].join(';');

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
      'font-size:15px', // >=16px avoids iOS zoom-on-focus; 15 + no-zoom meta is fine
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
    input.addEventListener('beforeinput', function (e) {
      var breaksLine = e.inputType === 'insertLineBreak'
        || (e.inputType === 'insertText' && e.data === '\n');
      if (!breaksLine || shiftHeld) return;
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

    root.appendChild(header);
    root.appendChild(tail);
    root.appendChild(bar);
    root.appendChild(keys);
    root.appendChild(row);
    document.body.appendChild(root);

    el = { root: root, title: title, status: status, tail: tail,
           bar: bar, barLabel: barLabel, input: input, send: send };

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
    var overlap = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop));
    el.root.style.bottom = overlap + 'px';
    el.root.style.maxHeight = Math.max(220, vv.height * 0.88) + 'px';
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

    state.busy = true;
    el.send.disabled = true;
    setStatus('전송 중…', '#9ca3af');

    post('/prompt', { text: text })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (r) {
        if (r.status === 200) {
          el.input.value = '';
          // confirmed:false means tmux accepted it but the pane did not change.
          // Say so instead of implying it landed.
          if (r.body.confirmed === false) {
            setStatus('전송됨 · 화면 변화 없음', '#fbbf24');
          } else {
            setStatus('전송됨', '#34d399');
          }
          pollTail();
        } else if (r.status === 409) {
          setStatus('거부: ' + (r.body.reason || ''), '#fbbf24');
          if (r.body.message) window.alert(r.body.message);
        } else if (r.status === 400) {
          setStatus('차단됨', '#ef4444');
          window.alert('위험 명령 패턴으로 차단되었습니다.');
        } else {
          setStatus('실패 (' + r.status + ')', '#ef4444');
          if (r.body.detail) window.alert(String(r.body.detail));
        }
      })
      .catch(function () { setStatus('네트워크 오류', '#ef4444'); })
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
    state.session = name;
    state.selStart = null;
    state.selEnd = null;
    state.lines = null;
    if (el.bar) el.bar.style.display = 'none';
    el.title.textContent = name.replace(/^claude[_-]/, '');
    el.tail.textContent = '불러오는 중…';
    setStatus('');
    el.root.style.display = 'flex';
    fitViewport();
    startPolling();
    // Do not autofocus: on iOS that pops the keyboard before the pane is read.
  }

  function hide() {
    stopPolling();
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
