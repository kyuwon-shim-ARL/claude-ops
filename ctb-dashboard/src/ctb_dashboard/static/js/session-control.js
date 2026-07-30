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

  var state = { session: null, timer: null, busy: false };
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

    var close = document.createElement('button');
    close.type = 'button';
    close.textContent = '✕';
    close.setAttribute('aria-label', '콘솔 닫기');
    close.style.cssText = btnCss('#1f2937', '36px');
    close.addEventListener('click', hide);

    header.appendChild(title);
    header.appendChild(status);
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
    ].join(';');

    /* Keys first: answering a permission prompt is the thing you most often
     * need in a hurry, and send_prompt refuses while one is pending. */
    var keys = document.createElement('div');
    keys.style.cssText =
      'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;flex-shrink:0;';
    [
      ['y', 'y', '예'], ['n', 'n', '아니오'],
      ['1', '1', '1번'], ['2', '2', '2번'],
      ['↵', 'Enter', 'Enter'], ['esc', 'Escape', 'Escape'],
      ['↑', 'Up', '위'], ['↓', 'Down', '아래'],
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
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
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
    root.appendChild(keys);
    root.appendChild(row);
    document.body.appendChild(root);

    el = { root: root, title: title, status: status, tail: tail, input: input, send: send };

    // The keyboard shrinks the visual viewport; sit on top of it, not under.
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', fitViewport);
      window.visualViewport.addEventListener('scroll', fitViewport);
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && state.session) hide();
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

  function pollTail() {
    if (!state.session) return;
    var name = state.session;
    fetch('/api/sessions/' + encodeURIComponent(name) + '/log?lines=' + TAIL_LINES, {
      headers: { 'Accept': 'application/json' },
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || state.session !== name) return;
        var atBottom =
          el.tail.scrollTop + el.tail.clientHeight >= el.tail.scrollHeight - 24;
        el.tail.textContent = data.log || '';
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
    SESSION_NAME_RE: SESSION_NAME_RE,
    POLL_MS: POLL_MS,
  };
})();
