/* "새 세션" — start a Claude session from the dashboard.
 *
 * Three things the phone could not do before: open a session for a project
 * that has none, make a new project, and branch off a worktree. All of it goes
 * through POST /api/sessions/create, which is control-token gated like every
 * other write.
 *
 * The naming rules are duplicated from session_create.py on purpose: the
 * server is the authority and rejects anything invalid, but a name that will
 * be refused should be visible as refused before a round trip, next to the
 * field you would fix. The server's answer still wins -- nothing here decides
 * whether a create happens.
 *
 * Requires control-token.js (window.ctbControl). No inline handlers: the page
 * runs under a CSP with a nonce.
 */
(function () {
  'use strict';

  /* The VSCode webview is a different origin: the extension hands it this
   * page's markup as a string, so a relative '/api/...' resolves against
   * vscode-webview:// and never reaches the server. The extension sets
   * CTB_API_BASE; in a browser it is unset and nothing changes. */
  function api(path) { return (window.CTB_API_BASE || '') + path; }


  /* --- pure logic (tested through node; see test_session_create_js.py) ---- */

  var PROJECT_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
  var WORKTREE_RE = /^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$/;

  function sessionNameFor(project, worktree) {
    return worktree ? 'claude_' + project + '_wt_' + worktree
                    : 'claude_' + project;
  }

  /* Turn the form state into a request body, or an error to show.
   * Returns {payload, session, worktree} or {error}. */
  function buildRequest(s) {
    s = s || {};
    var isNew = s.mode === 'new';
    var project = ((isNew ? s.newProject : s.project) || '').trim();

    if (!project) {
      return { error: isNew ? '새 프로젝트 이름을 입력하세요'
                            : '프로젝트를 선택하세요' };
    }
    if (!PROJECT_RE.test(project)) {
      return { error: "프로젝트 이름은 영문자/숫자로 시작하고 영문자, 숫자, '.', '_', '-'만 쓸 수 있습니다" };
    }

    var worktree = null;
    if (s.wtMode === 'existing') {
      worktree = (s.wtExisting || '').trim();
      if (!worktree) return { error: '워크트리를 선택하세요' };
    } else if (s.wtMode === 'new') {
      worktree = (s.wtNew || '').trim();
      if (!worktree) return { error: '새 워크트리 이름을 입력하세요' };
      if (!WORKTREE_RE.test(worktree)) {
        return { error: "워크트리 이름은 '-'로 시작할 수 없고 영문자, 숫자, '_', '-'만 쓸 수 있습니다" };
      }
    }

    /* A worktree needs a repo to branch from. Caught here so the reason is
     * visible while the checkbox that causes it is still on screen. */
    if (worktree && isNew && !s.gitInit) {
      return { error: 'git 저장소로 초기화해야 워크트리를 만들 수 있습니다' };
    }
    if (worktree && !isNew && s.projectIsGit === false) {
      return { error: '이 프로젝트는 git 저장소가 아니라 워크트리를 만들 수 없습니다' };
    }

    var payload = {};
    if (isNew) {
      payload.new_project = project;
      payload.git_init = s.gitInit !== false;
    } else {
      payload.project = project;
    }
    if (worktree) payload.worktree = worktree;

    return {
      payload: payload,
      session: sessionNameFor(project, worktree),
      worktree: worktree,
    };
  }

  /* Where the session will run -- shown before creating so a wrong pick is
   * obvious. Mirrors the path convention in session_create.py. */
  function previewPath(root, project, worktree) {
    var base = (root || '~/projects').replace(/\/$/, '') + '/' + project;
    return worktree ? base + '/.claude/worktrees/' + worktree : base;
  }

  function filterProjects(projects, query) {
    var q = (query || '').trim().toLowerCase();
    if (!q) return projects.slice();
    return projects.filter(function (p) {
      return p.name.toLowerCase().indexOf(q) !== -1;
    });
  }

  /* --- state ------------------------------------------------------------- */

  var state = {
    mode: 'existing',
    project: '',
    projectIsGit: null,
    newProject: '',
    gitInit: true,
    wtMode: 'none',
    wtExisting: '',
    wtNew: '',
    root: '',
    projects: [],
    worktrees: [],
    busy: false,
  };

  var el = {};

  /* --- markup ------------------------------------------------------------ */

  function btnCss(bg) {
    return [
      'border:1px solid rgba(255,255,255,0.12)', 'border-radius:10px',
      'background:' + bg, 'color:inherit', 'cursor:pointer',
      'font-size:13px', 'padding:7px 14px',
    ].join(';') + ';';
  }

  function inputCss() {
    return [
      /* 16px: anything smaller makes iOS zoom in on focus and stay there. */
      'width:100%', 'box-sizing:border-box', 'font-size:16px', 'padding:8px 11px',
      'border-radius:10px', 'background:rgba(255,255,255,0.06)',
      'border:1px solid rgba(255,255,255,0.12)', 'color:inherit', 'outline:none',
    ].join(';') + ';';
  }

  function labelCss() {
    return 'font-size:11px;color:#9b95b0;margin:12px 0 6px;display:block;';
  }

  function build() {
    if (el.root) return;

    var root = document.createElement('div');
    root.id = 'new-session-modal';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', '새 세션');
    root.style.cssText = 'display:none;position:fixed;inset:0;z-index:1000;' +
      'background:rgba(0,0,0,0.55);backdrop-filter:blur(2px);' +
      'align-items:center;justify-content:center;padding:16px;';

    var box = document.createElement('div');
    box.style.cssText = 'max-width:460px;width:100%;max-height:88vh;overflow:auto;' +
      'border-radius:18px;padding:20px;background:#1c1628;' +
      'border:1px solid rgba(255,255,255,0.1);box-shadow:0 20px 60px rgba(0,0,0,0.5);' +
      'color:#e2dff0;font-family:ui-sans-serif,system-ui,sans-serif;';

    var title = document.createElement('div');
    title.textContent = '새 세션';
    title.style.cssText = 'font-size:15px;font-weight:700;margin-bottom:14px;';

    /* mode switch */
    var modes = document.createElement('div');
    modes.style.cssText = 'display:flex;gap:6px;margin-bottom:4px;';
    el.modeBtns = {};
    [['existing', '기존 프로젝트'], ['new', '새 프로젝트']].forEach(function (m) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = m[1];
      b.style.cssText = btnCss('rgba(255,255,255,0.06)') + 'flex:1;';
      b.addEventListener('click', function () { setMode(m[0]); });
      el.modeBtns[m[0]] = b;
      modes.appendChild(b);
    });

    /* existing-project pane */
    el.existingPane = document.createElement('div');
    el.search = document.createElement('input');
    el.search.type = 'text';
    el.search.placeholder = '🔎 프로젝트 검색';
    el.search.setAttribute('aria-label', '프로젝트 검색');
    el.search.autocomplete = 'off';
    el.search.style.cssText = inputCss() + 'margin-top:12px;';
    el.search.addEventListener('input', renderProjectList);

    el.list = document.createElement('div');
    el.list.id = 'new-session-projects';
    el.list.style.cssText = 'margin-top:8px;max-height:190px;overflow:auto;' +
      'border:1px solid rgba(255,255,255,0.08);border-radius:12px;';
    el.existingPane.appendChild(el.search);
    el.existingPane.appendChild(el.list);

    /* new-project pane */
    el.newPane = document.createElement('div');
    el.newPane.style.display = 'none';
    var nameLabel = document.createElement('label');
    nameLabel.textContent = '프로젝트 이름';
    nameLabel.style.cssText = labelCss();
    el.newName = document.createElement('input');
    el.newName.type = 'text';
    el.newName.placeholder = 'my-project';
    el.newName.autocomplete = 'off';
    el.newName.style.cssText = inputCss();
    el.newName.addEventListener('input', function () {
      state.newProject = el.newName.value;
      renderPreview();
    });
    nameLabel.setAttribute('for', 'new-session-name');
    el.newName.id = 'new-session-name';

    var gitRow = document.createElement('label');
    gitRow.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12px;color:#c9c4dc;cursor:pointer;';
    el.gitInit = document.createElement('input');
    el.gitInit.type = 'checkbox';
    el.gitInit.checked = true;
    el.gitInit.addEventListener('change', function () {
      state.gitInit = el.gitInit.checked;
      renderPreview();
    });
    gitRow.appendChild(el.gitInit);
    gitRow.appendChild(document.createTextNode('git 저장소로 초기화 (.gitignore + 최초 커밋)'));

    el.newPane.appendChild(nameLabel);
    el.newPane.appendChild(el.newName);
    el.newPane.appendChild(gitRow);

    /* worktree — hidden until a git project (or new-project) is active */
    el.wtSection = document.createElement('div');
    el.wtSection.style.display = 'none';

    var wtLabel = document.createElement('div');
    wtLabel.textContent = '워크트리';
    wtLabel.style.cssText = labelCss();

    var wtModes = document.createElement('div');
    wtModes.style.cssText = 'display:flex;gap:6px;';
    el.wtBtns = {};
    [['none', '없음'], ['existing', '기존 선택'], ['new', '새로 만들기']].forEach(function (m) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = m[1];
      b.style.cssText = btnCss('rgba(255,255,255,0.06)') + 'flex:1;font-size:12px;padding:6px 8px;';
      b.addEventListener('click', function () { setWtMode(m[0]); });
      el.wtBtns[m[0]] = b;
      wtModes.appendChild(b);
    });
    el.wtSection.appendChild(wtLabel);
    el.wtSection.appendChild(wtModes);

    el.wtSelect = document.createElement('select');
    el.wtSelect.setAttribute('aria-label', '기존 워크트리');
    el.wtSelect.style.cssText = inputCss() + 'margin-top:8px;display:none;';
    el.wtSelect.addEventListener('change', function () {
      state.wtExisting = el.wtSelect.value;
      renderPreview();
    });

    el.wtInput = document.createElement('input');
    el.wtInput.type = 'text';
    el.wtInput.placeholder = '워크트리 이름 (예: refactor)';
    el.wtInput.setAttribute('aria-label', '새 워크트리 이름');
    el.wtInput.autocomplete = 'off';
    el.wtInput.style.cssText = inputCss() + 'margin-top:8px;display:none;';
    el.wtInput.addEventListener('input', function () {
      state.wtNew = el.wtInput.value;
      renderPreview();
    });

    /* preview + error */
    el.preview = document.createElement('div');
    el.preview.style.cssText = "margin-top:14px;padding:10px 12px;border-radius:10px;" +
      'background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);' +
      "font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.6;color:#c9c4dc;" +
      'word-break:break-all;';

    el.error = document.createElement('div');
    el.error.setAttribute('role', 'alert');
    el.error.style.cssText = 'margin-top:10px;font-size:12px;color:#f87171;display:none;';

    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;justify-content:flex-end;gap:8px;margin-top:18px;';
    el.cancel = document.createElement('button');
    el.cancel.type = 'button';
    el.cancel.textContent = '취소';
    el.cancel.style.cssText = btnCss('rgba(255,255,255,0.07)');
    el.cancel.addEventListener('click', hide);

    el.submit = document.createElement('button');
    el.submit.type = 'button';
    el.submit.textContent = '세션 시작';
    el.submit.style.cssText = btnCss('rgba(129,140,248,0.22)') +
      'font-weight:600;border-color:rgba(129,140,248,0.5);';
    el.submit.addEventListener('click', submit);

    actions.appendChild(el.cancel);
    actions.appendChild(el.submit);

    box.appendChild(title);
    box.appendChild(modes);
    box.appendChild(el.existingPane);
    box.appendChild(el.newPane);
    box.appendChild(el.wtSection);
    box.appendChild(el.wtSelect);
    box.appendChild(el.wtInput);
    box.appendChild(el.preview);
    box.appendChild(el.error);
    box.appendChild(actions);
    root.appendChild(box);

    /* Backdrop click closes; a click inside must not. */
    root.addEventListener('click', function (e) {
      if (e.target === root) hide();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && root.style.display === 'flex') hide();
    });

    document.body.appendChild(root);
    el.root = root;
  }

  /* --- rendering --------------------------------------------------------- */

  /* Show the worktree row only when there is a git context to branch from. */
  function renderWtSection() {
    var visible = state.mode === 'new'
      || (state.mode === 'existing' && !!state.project && state.projectIsGit !== false);
    el.wtSection.style.display = visible ? '' : 'none';
    /* Disable "기존 선택" when no worktrees have loaded yet. */
    if (el.wtBtns['existing']) {
      el.wtBtns['existing'].disabled = state.worktrees.length === 0;
      el.wtBtns['existing'].style.opacity = state.worktrees.length ? '1' : '0.4';
    }
  }

  function setMode(mode) {
    state.mode = mode;
    el.existingPane.style.display = mode === 'existing' ? '' : 'none';
    el.newPane.style.display = mode === 'new' ? '' : 'none';
    Object.keys(el.modeBtns).forEach(function (k) {
      var on = k === mode;
      el.modeBtns[k].style.background = on ? 'rgba(129,140,248,0.22)' : 'rgba(255,255,255,0.06)';
      el.modeBtns[k].style.borderColor = on ? 'rgba(129,140,248,0.5)' : 'rgba(255,255,255,0.12)';
    });
    /* A new project has no worktrees to pick from. */
    if (mode === 'new' && state.wtMode === 'existing') setWtMode('none');
    renderWtSection();
    renderPreview();
  }

  function setWtMode(mode) {
    state.wtMode = mode;
    el.wtSelect.style.display = mode === 'existing' ? '' : 'none';
    el.wtInput.style.display = mode === 'new' ? '' : 'none';
    Object.keys(el.wtBtns).forEach(function (k) {
      var on = k === mode;
      el.wtBtns[k].style.background = on ? 'rgba(129,140,248,0.22)' : 'rgba(255,255,255,0.06)';
      el.wtBtns[k].style.borderColor = on ? 'rgba(129,140,248,0.5)' : 'rgba(255,255,255,0.12)';
    });
    renderPreview();
  }

  function renderProjectList() {
    var items = filterProjects(state.projects, el.search.value);
    el.list.textContent = '';
    if (!items.length) {
      var empty = document.createElement('div');
      empty.textContent = state.projects.length ? '검색 결과 없음' : '프로젝트를 불러오는 중…';
      empty.style.cssText = 'padding:14px;font-size:12px;color:#8b85a0;text-align:center;';
      el.list.appendChild(empty);
      return;
    }
    items.forEach(function (p) {
      var row = document.createElement('button');
      row.type = 'button';
      row.style.cssText = 'display:flex;align-items:center;gap:8px;width:100%;' +
        'text-align:left;padding:8px 11px;background:transparent;border:0;' +
        'border-bottom:1px solid rgba(255,255,255,0.05);color:inherit;cursor:pointer;' +
        "font-family:'JetBrains Mono',monospace;font-size:12px;";
      if (p.name === state.project) row.style.background = 'rgba(129,140,248,0.18)';

      var nm = document.createElement('span');
      nm.textContent = p.name;
      nm.style.cssText = 'flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      row.appendChild(nm);

      if (!p.is_git) row.appendChild(tag('no-git', '#8b85a0'));
      if (p.session_exists) row.appendChild(tag('세션 있음', '#34d399'));

      row.addEventListener('click', function () { selectProject(p); });
      el.list.appendChild(row);
    });
  }

  function tag(text, color) {
    var s = document.createElement('span');
    s.textContent = text;
    s.style.cssText = 'flex-shrink:0;font-size:10px;padding:1px 6px;border-radius:6px;' +
      'border:1px solid ' + color + '55;color:' + color + ';';
    return s;
  }

  function selectProject(p) {
    state.project = p.name;
    state.projectIsGit = !!p.is_git;
    state.worktrees = [];
    state.wtExisting = '';
    /* Reset any worktree mode — section may be hidden for non-git projects and
     * a stale 'new'/'existing' would produce a payload the UI isn't showing. */
    if (state.wtMode !== 'none') setWtMode('none');
    renderProjectList();
    renderWtSection();
    renderPreview();
    if (p.is_git) loadWorktrees(p.name);
  }

  function renderPreview() {
    var r = buildRequest(state);
    var project = (state.mode === 'new' ? state.newProject : state.project).trim();
    if (r.error) {
      el.preview.textContent = project
        ? '→ ' + previewPath(state.root, project, null)
        : '프로젝트를 고르거나 새로 만드세요.';
      showError(null);
      el.submit.disabled = false;
      return;
    }
    el.preview.textContent = '';
    var line1 = document.createElement('div');
    line1.textContent = r.session;
    line1.style.cssText = 'color:#a5b4fc;font-weight:600;';
    var line2 = document.createElement('div');
    line2.textContent = previewPath(state.root, project, r.worktree);
    el.preview.appendChild(line1);
    el.preview.appendChild(line2);
    if (state.mode === 'existing') {
      var exists = state.projects.some(function (p) {
        return p.session === r.session && p.session_exists;
      }) || state.worktrees.some(function (w) {
        return w.session === r.session && w.session_exists;
      });
      if (exists) {
        var note = document.createElement('div');
        note.textContent = '이미 있는 세션입니다 — 새로 만들지 않고 콘솔만 엽니다.';
        note.style.cssText = 'color:#fbbf24;margin-top:4px;';
        el.preview.appendChild(note);
      }
    }
    showError(null);
  }

  function showError(msg) {
    el.error.textContent = msg || '';
    el.error.style.display = msg ? '' : 'none';
  }

  /* --- data -------------------------------------------------------------- */

  function loadProjects() {
    return fetch(api('/api/projects'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) throw new Error('projects');
        state.root = d.root || '';
        state.projects = d.projects || [];
        renderProjectList();
        renderPreview();
      })
      .catch(function () {
        state.projects = [];
        renderProjectList();
        showError('프로젝트 목록을 불러오지 못했습니다.');
      });
  }

  function _clearWorktreeState() {
    state.worktrees = [];
    state.wtExisting = '';
    if (state.wtMode === 'existing') setWtMode('none');
  }

  function loadWorktrees(project) {
    return fetch(api('/api/projects/' + encodeURIComponent(project) + '/worktrees'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) {
          /* Network or server error — wipe stale state so payload stays honest. */
          _clearWorktreeState();
          renderWtSection();
          return;
        }
        /* Ignore a response for a project the user has since moved off. */
        if (d.project !== state.project) return;
        el.wtSelect.textContent = '';
        state.worktrees = d.worktrees || [];
        state.projectIsGit = !!d.is_git;
        state.worktrees.forEach(function (w) {
          var o = document.createElement('option');
          o.value = w.name;
          o.textContent = w.name + (w.session_exists ? '  (세션 있음)' : '');
          el.wtSelect.appendChild(o);
        });
        if (state.worktrees.length && !state.wtExisting) {
          state.wtExisting = state.worktrees[0].name;
          el.wtSelect.value = state.wtExisting;
        }
        if (!state.worktrees.length && state.wtMode === 'existing') setWtMode('none');
        renderWtSection();
        renderPreview();
      })
      .catch(function () { /* the create call reports the real problem */ });
  }

  /* --- submit ------------------------------------------------------------ */

  var _submitGen = 0;  /* incremented on each open; callbacks check they belong to current gen */

  function submit() {
    if (state.busy) return;
    var r = buildRequest(state);
    if (r.error) {
      showError(r.error);
      return;
    }
    var gen = _submitGen;
    setBusy(true);
    showError(null);
    window.ctbControl.send('/api/sessions/create', {
      method: 'POST',
      body: JSON.stringify(r.payload),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        return { ok: res.ok, status: res.status, body: body };
      });
    }).then(function (res) {
      if (gen !== _submitGen) return;  /* dialog was closed/reopened — abandon */
      setBusy(false);
      if (!res.ok) {
        showError(res.body && res.body.detail
          ? String(res.body.detail)
          : '세션 생성에 실패했습니다 (' + res.status + ').');
        return;
      }
      hide();
      if (window.ctbConsole && res.body.session) window.ctbConsole.open(res.body.session);
    }).catch(function (e) {
      if (gen !== _submitGen) return;
      setBusy(false);
      showError('요청 실패: ' + e);
    });
  }

  function setBusy(busy) {
    state.busy = busy;
    el.submit.disabled = busy;
    el.submit.textContent = busy ? '시작 중…' : '세션 시작';
    el.submit.style.opacity = busy ? '0.6' : '1';
  }

  /* --- open / close ------------------------------------------------------ */

  function show() {
    build();
    _submitGen++;          /* invalidate any in-flight request from a prior open */
    el.root.style.display = 'flex';
    setMode(state.mode);
    setWtMode(state.wtMode);
    setBusy(false);
    loadProjects();
    /* Re-fetch worktrees for the persisted project so stale data doesn't linger. */
    if (state.project && state.mode === 'existing' && state.projectIsGit) {
      loadWorktrees(state.project);
    }
    /* Not on touch: focusing a text field there pops the keyboard over the
     * list the user came here to read. */
    if (!window.matchMedia || !window.matchMedia('(pointer: coarse)').matches) {
      el.search.focus();
    }
  }

  function hide() {
    if (el.root) el.root.style.display = 'none';
  }

  function wire() {
    var btn = document.getElementById('btn-new-session');
    if (btn) btn.addEventListener('click', show);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  window.ctbNewSession = {
    open: show,
    close: hide,
    /* exposed for tests */
    buildRequest: buildRequest,
    sessionNameFor: sessionNameFor,
    previewPath: previewPath,
    filterProjects: filterProjects,
    _state: state,
  };
})();
