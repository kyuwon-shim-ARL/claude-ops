/* STT Lab: scores GPT transcription against iOS dictation on a fixed eval
 * set, per sentence. Never touches a live session -- every POST here is
 * /api/stt or /api/stt/eval*, and every write goes through
 * window.ctbControl.send so the control token is attached the same way the
 * console attaches it. */
(function () {
  'use strict';

  var LS_KEY = 'ctb.sttlab.index';

  var state = {
    items: [],
    idx: 0,
    hints: true,
    stt: { rec: null, stream: null, chunks: [], startedAt: 0, holding: false, busy: false },
    enabled: false,
  };

  var el = {};

  function $(id) { return document.getElementById(id); }

  function loadIdx() {
    try {
      var v = parseInt(localStorage.getItem(LS_KEY), 10);
      return isNaN(v) ? 0 : v;
    } catch (e) { return 0; }
  }

  function saveIdx() {
    try { localStorage.setItem(LS_KEY, String(state.idx)); } catch (e) { /* private mode */ }
  }

  var CAT_LABEL = { mixed: '한영 혼용', ko: '순한국어', en: '영어 위주', session: '세션명 포함' };

  function setStatus(text, color) {
    if (!el.status) return;
    el.status.textContent = text || '';
    el.status.style.color = color || 'var(--muted)';
  }

  function currentItem() {
    return state.items[state.idx] || null;
  }

  function renderItem() {
    var item = currentItem();
    if (el.progress) el.progress.textContent = state.items.length
      ? (state.idx + 1) + ' / ' + state.items.length : '0 / 0';
    if (!item) {
      if (el.sentence) el.sentence.textContent = '평가 문장이 없습니다.';
      if (el.category) el.category.textContent = '';
      if (el.sessionName) { el.sessionName.textContent = ''; el.sessionName.hidden = true; }
      return;
    }
    if (el.sentence) el.sentence.textContent = item.text;
    if (el.category) el.category.textContent = CAT_LABEL[item.category] || item.category || '';
    if (el.sessionName) {
      if (item.session) { el.sessionName.textContent = item.session; el.sessionName.hidden = false; }
      else { el.sessionName.textContent = ''; el.sessionName.hidden = true; }
    }
    if (el.iosBox) el.iosBox.value = '';
    hideResult();
    setStatus('', '');
  }

  function next() {
    if (!state.items.length) return;
    state.idx = (state.idx + 1) % state.items.length;
    saveIdx();
    renderItem();
  }

  function skip() { next(); }

  function hideResult() {
    if (el.result) el.result.hidden = true;
  }

  /* --- config + eval set load --------------------------------------- */

  function loadConfig() {
    fetch(window.ctbControl.api('/api/stt/config'), { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (cfg) {
        state.enabled = !!(cfg && cfg.enabled);
        if (!state.enabled) {
          if (el.notice) {
            el.notice.hidden = false;
            el.notice.textContent = 'OPENAI_API_KEY 미설정 · 마이크 채점 비활성';
          }
          if (el.mic) el.mic.disabled = true;
        } else if (el.notice) {
          el.notice.hidden = true;
        }
      })
      .catch(function () {
        if (el.notice) { el.notice.hidden = false; el.notice.textContent = 'STT 설정을 불러오지 못했습니다.'; }
      });
  }

  function loadSet() {
    fetch(window.ctbControl.api('/api/stt/eval/set'), { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (r.status === 503) { setStatus('서버 기능 비활성 (503)', 'var(--err)'); return null; }
        return r.ok ? r.json() : null;
      })
      .then(function (body) {
        if (!body) return;
        state.items = body.items || [];
        var saved = loadIdx();
        state.idx = (state.items.length && saved < state.items.length) ? saved : 0;
        renderItem();
      })
      .catch(function () { setStatus('평가셋을 불러오지 못했습니다.', 'var(--err)'); });
  }

  /* --- mic (mirrors session-control.js sttStart/sttStop/sttFinish) --- */

  function sttMime() {
    var picks = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    for (var i = 0; i < picks.length; i++) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(picks[i])) return picks[i];
    }
    return '';
  }

  function sttStart() {
    var stt = state.stt;
    if (stt.rec || stt.busy || !state.enabled) return;
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
      setStatus('듣는 중… 손을 떼면 전사', 'var(--err)');
    }).catch(function (err) {
      stt.busy = false;
      var denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
      setStatus(denied ? '마이크 권한이 거부됨' : '마이크를 열 수 없음', 'var(--err)');
    });
  }

  function sttStop() {
    var rec = state.stt.rec;
    if (!rec) return;
    if (el.mic) el.mic.removeAttribute('data-listening');
    if (rec.state !== 'inactive') rec.stop(); else sttFinish();
  }

  function sttRelease() {
    var stt = state.stt;
    if (stt.stream) stt.stream.getTracks().forEach(function (t) { t.stop(); });
    stt.stream = null; stt.rec = null; stt.chunks = [];
  }

  function sttFinish() {
    var stt = state.stt;
    var rec = stt.rec;
    if (!rec) return;
    var mime = rec.mimeType || sttMime() || 'audio/webm';
    var blob = new Blob(stt.chunks, { type: mime });
    var held = Date.now() - stt.startedAt;
    var item = currentItem();
    sttRelease();
    if (held < 400 || blob.size < 1200) { setStatus('', ''); return; }
    if (!item) return;
    setStatus('전사 중…', 'var(--muted)');
    var qs = '?hints=' + (state.hints ? '1' : '0') +
      (item.session ? '&session=' + encodeURIComponent(item.session) : '');
    var startedAt = Date.now();
    window.ctbControl.send('/api/stt' + qs, {
      method: 'POST', body: blob, headers: { 'Content-Type': mime },
    }).then(function (res) {
      if (res.status === 403) { setStatus('토큰 거부됨 (403)', 'var(--err)'); return null; }
      if (res.status === 503) { setStatus('STT 비활성 (503)', 'var(--err)'); return null; }
      return res.json().catch(function () { return {}; }).then(function (body) {
        return { status: res.status, body: body };
      });
    }).then(function (r) {
      if (!r) return;
      if (r.status !== 200) {
        setStatus('전사 실패 (' + r.status + ')', 'var(--err)');
        return;
      }
      var text = (r.body.text || '').trim();
      var seconds = typeof r.body.seconds === 'number' ? r.body.seconds : (Date.now() - startedAt) / 1000;
      if (!text) { setStatus('들리는 말이 없음', 'var(--warn)'); return; }
      score(item, text, 'gpt', seconds);
    }).catch(function () { setStatus('전사 실패 · 네트워크', 'var(--err)'); });
  }

  function bindMic(btn) {
    if (!btn) return;
    var pressedAt = 0;
    btn.addEventListener('pointerdown', function (e) {
      if (e.button && e.button !== 0) return;
      if (!state.enabled) return;
      e.preventDefault();
      pressedAt = Date.now();
      if (state.stt.rec) { sttStop(); pressedAt = 0; return; }
      state.stt.holding = true;
      sttStart();
    });
    var up = function () {
      if (!state.stt.holding) return;
      state.stt.holding = false;
      if (Date.now() - pressedAt < 350) { setStatus('녹음 중 · 탭하면 정지', 'var(--err)'); return; }
      sttStop();
    };
    btn.addEventListener('pointerup', up);
    btn.addEventListener('pointercancel', up);
    btn.addEventListener('pointerleave', function () { if (state.stt.holding) up(); });
    btn.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  }

  /* --- scoring -------------------------------------------------------- */

  /* Character-level LCS diff so ref vs hyp shows insertions/deletions inline
   * -- this is purely visual, the CER number itself comes from the server. */
  function diffChars(a, b) {
    var n = a.length, m = b.length;
    var dp = new Array(n + 1);
    for (var i = 0; i <= n; i++) dp[i] = new Array(m + 1).fill(0);
    for (i = 1; i <= n; i++) {
      for (var j = 1; j <= m; j++) {
        dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
    var ops = [];
    i = n; var j = m;
    while (i > 0 && j > 0) {
      if (a[i - 1] === b[j - 1]) { ops.push(['eq', a[i - 1]]); i--; j--; }
      else if (dp[i - 1][j] >= dp[i][j - 1]) { ops.push(['del', a[i - 1]]); i--; }
      else { ops.push(['ins', b[j - 1]]); j--; }
    }
    while (i > 0) { ops.push(['del', a[i - 1]]); i--; }
    while (j > 0) { ops.push(['ins', b[j - 1]]); j--; }
    ops.reverse();
    return ops;
  }

  function renderDiff(target, ref, hyp) {
    if (!target) return;
    target.innerHTML = '';
    diffChars(ref, hyp).forEach(function (op) {
      var span = document.createElement('span');
      span.textContent = op[1];
      if (op[0] === 'del') span.className = 'stt-diff-del';
      else if (op[0] === 'ins') span.className = 'stt-diff-ins';
      target.appendChild(span);
    });
  }

  function score(item, hyp, engine, seconds) {
    setStatus('채점 중…', 'var(--muted)');
    window.ctbControl.send('/api/stt/eval', {
      method: 'POST',
      body: JSON.stringify({
        id: item.id, ref: item.text, hyp: hyp, engine: engine,
        hints: state.hints, seconds: seconds === undefined ? null : seconds,
        category: item.category,
      }),
    }).then(function (res) {
      if (res.status === 403) { setStatus('토큰 거부됨 (403)', 'var(--err)'); return null; }
      if (res.status === 503) { setStatus('서버 기능 비활성 (503)', 'var(--err)'); return null; }
      return res.json().catch(function () { return {}; }).then(function (body) {
        return { status: res.status, body: body };
      });
    }).then(function (r) {
      if (!r) return;
      if (r.status !== 200) { setStatus('채점 실패 (' + r.status + ')', 'var(--err)'); return; }
      showResult(item, hyp, r.body);
      loadStats(r.body.stats);
      setStatus('채점 완료', 'var(--ok)');
    }).catch(function () { setStatus('채점 실패 · 네트워크', 'var(--err)'); });
  }

  function showResult(item, hyp, body) {
    if (!el.result) return;
    el.result.hidden = false;
    if (el.refText) el.refText.textContent = item.text;
    if (el.hypText) el.hypText.textContent = hyp;
    renderDiff(el.diff, item.text, hyp);
    var cer = typeof body.cer === 'number' ? body.cer : 0;
    if (el.cer) el.cer.textContent = (cer * 100).toFixed(1) + '%';
    if (el.missed) {
      el.missed.innerHTML = '';
      (body.missed || []).forEach(function (term) {
        var chip = document.createElement('span');
        chip.className = 'stt-chip';
        chip.textContent = term;
        el.missed.appendChild(chip);
      });
      if (el.missedNote) el.missedNote.hidden = !(body.missed && body.missed.length);
    }
  }

  function submitIosScore() {
    var item = currentItem();
    var hyp = el.iosBox ? el.iosBox.value.trim() : '';
    if (!item || !hyp) return;
    score(item, hyp, 'ios', null);
  }

  /* --- stats panel ------------------------------------------------------ */

  function pct(x) { return typeof x === 'number' ? (x * 100).toFixed(1) + '%' : '--'; }

  function loadStats(preloaded) {
    if (preloaded) { renderStats(preloaded); return; }
    fetch(window.ctbControl.api('/api/stt/eval/results'), { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (body) { if (body) renderStats(body); })
      .catch(function () { /* stats are a nicety */ });
  }

  function renderStats(body) {
    if (el.statN) el.statN.textContent = body.n != null ? String(body.n) : '--';
    var byEngine = body.by_engine || {};
    if (el.statGpt) el.statGpt.textContent = pct(byEngine.gpt && byEngine.gpt.cer) + ' (n=' + (byEngine.gpt ? byEngine.gpt.n : 0) + ')';
    if (el.statIos) el.statIos.textContent = pct(byEngine.ios && byEngine.ios.cer) + ' (n=' + (byEngine.ios ? byEngine.ios.n : 0) + ')';
    if (el.statCategory) {
      el.statCategory.innerHTML = '';
      var byCat = body.by_category || {};
      Object.keys(byCat).forEach(function (cat) {
        var row = document.createElement('div');
        row.className = 'stt-stat-row';
        row.textContent = (CAT_LABEL[cat] || cat) + ': ' + pct(byCat[cat].cer) + ' (n=' + byCat[cat].n + ')';
        el.statCategory.appendChild(row);
      });
    }
    if (el.statMissed) {
      el.statMissed.innerHTML = '';
      (body.top_missed || []).forEach(function (pair) {
        var chip = document.createElement('span');
        chip.className = 'stt-chip';
        chip.textContent = pair[0] + ' ×' + pair[1];
        el.statMissed.appendChild(chip);
      });
    }
    if (el.statGlossary) el.statGlossary.textContent = body.glossary_size != null ? String(body.glossary_size) : '--';
  }

  function rebuild() {
    setStatus('용어집·평가셋 재생성 중…', 'var(--muted)');
    window.ctbControl.send('/api/stt/eval/rebuild', { method: 'POST', body: JSON.stringify({}) })
      .then(function (res) {
        if (res.status === 403) { setStatus('토큰 거부됨 (403)', 'var(--err)'); return null; }
        if (res.status === 503) { setStatus('서버 기능 비활성 (503)', 'var(--err)'); return null; }
        return res.json().catch(function () { return {}; });
      })
      .then(function (body) {
        if (!body) return;
        setStatus('재생성 완료', 'var(--ok)');
        loadSet();
        loadStats();
      })
      .catch(function () { setStatus('재생성 실패 · 네트워크', 'var(--err)'); });
  }

  /* --- wiring ------------------------------------------------------- */

  function init() {
    el.status = $('stt-status');
    el.progress = $('stt-progress');
    el.notice = $('stt-notice');
    el.sentence = $('stt-sentence');
    el.category = $('stt-category');
    el.sessionName = $('stt-session-name');
    el.mic = $('stt-mic');
    el.iosBox = $('stt-ios-box');
    el.iosScore = $('stt-ios-score');
    el.hintsToggle = $('stt-hints-toggle');
    el.result = $('stt-result');
    el.refText = $('stt-ref-text');
    el.hypText = $('stt-hyp-text');
    el.diff = $('stt-diff');
    el.cer = $('stt-cer');
    el.missed = $('stt-missed');
    el.missedNote = $('stt-missed-note');
    el.retry = $('stt-retry');
    el.nextBtn = $('stt-next');
    el.skipBtn = $('stt-skip');
    el.statsToggle = $('stt-stats-toggle');
    el.statsPanel = $('stt-stats-panel');
    el.statN = $('stt-stat-n');
    el.statGpt = $('stt-stat-gpt');
    el.statIos = $('stt-stat-ios');
    el.statCategory = $('stt-stat-category');
    el.statMissed = $('stt-stat-missed');
    el.statGlossary = $('stt-stat-glossary');
    el.rebuildBtn = $('stt-rebuild');

    bindMic(el.mic);
    if (el.iosScore) el.iosScore.addEventListener('click', submitIosScore);
    if (el.retry) el.retry.addEventListener('click', function () { hideResult(); if (el.iosBox) el.iosBox.value = ''; });
    if (el.nextBtn) el.nextBtn.addEventListener('click', next);
    if (el.skipBtn) el.skipBtn.addEventListener('click', skip);
    if (el.hintsToggle) {
      el.hintsToggle.checked = state.hints;
      el.hintsToggle.addEventListener('change', function () { state.hints = !!el.hintsToggle.checked; });
    }
    if (el.statsToggle && el.statsPanel) {
      el.statsToggle.addEventListener('click', function () {
        el.statsPanel.hidden = !el.statsPanel.hidden;
      });
    }
    if (el.rebuildBtn) el.rebuildBtn.addEventListener('click', rebuild);

    loadConfig();
    loadSet();
    loadStats();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
