/* Control-token plumbing for the dashboard's mutating endpoints.
 *
 * The server gates every write (delete / pin / focus / prompt) behind an
 * X-CTB-Secret header. This keeps the token in localStorage and attaches it,
 * so the UI does not have to thread it through every call site.
 *
 * localStorage is per browsing context, so the home-screen PWA and Safari each
 * ask once -- that is expected, not a bug, and the prompt is what makes it
 * recoverable.
 */
(function () {
  'use strict';

  var KEY = 'ctb.controlToken';

  function stored() {
    try {
      return localStorage.getItem(KEY) || '';
    } catch (e) {
      return ''; // private mode / storage disabled
    }
  }

  function store(value) {
    try {
      if (value) localStorage.setItem(KEY, value);
      else localStorage.removeItem(KEY);
    } catch (e) {
      /* non-persistent session; the in-memory value below still works */
    }
  }

  var memo = stored();

  function ask(reason) {
    var msg = reason
      ? reason + '\n\n제어 토큰을 입력하세요 (.env의 CTB_CONTROL_SECRET):'
      : '제어 토큰을 입력하세요 (.env의 CTB_CONTROL_SECRET):';
    var entered = window.prompt(msg, '');
    if (entered) {
      entered = entered.trim();
      memo = entered;
      store(entered);
    }
    return memo;
  }

  function token(opts) {
    if (!memo && !(opts && opts.silent)) ask(null);
    return memo;
  }

  function headers(extra) {
    var h = Object.assign({ 'Content-Type': 'application/json' }, extra || {});
    var t = token();
    if (t) h['X-CTB-Secret'] = t;
    return h;
  }

  /* Turn an auth failure into something the user can fix, instead of a silent
   * no-op. Returns true when the caller should retry the request. */
  function recover(res) {
    if (!res) return false;
    if (res.status === 403) {
      memo = '';
      store('');
      return !!ask('제어 토큰이 거부되었습니다 (403).');
    }
    if (res.status === 503) {
      window.alert(
        '서버에서 제어 기능이 비활성 상태입니다 (503).\n' +
        '.env에 CTB_CONTROL_SECRET을 설정하고 ' +
        'systemctl --user restart ctb-dashboard 를 실행하세요.'
      );
      return false;
    }
    return false;
  }

  /* The VSCode webview is a different origin: the extension hands it this
   * page's markup as a string, so a relative '/api/...' resolves against
   * vscode-webview:// and never reaches the server. The extension sets
   * CTB_API_BASE; in a browser it is unset and nothing changes. */
  function api(path) { return (window.CTB_API_BASE || '') + path; }

  /* fetch wrapper: attaches the token and retries once after a 403 re-prompt. */
  function send(url, options) {
    var target = api(url);
    var opts = Object.assign({}, options || {});
    opts.headers = headers(opts.headers);
    return fetch(target, opts).then(function (res) {
      if (res.status !== 403 && res.status !== 503) return res;
      if (!recover(res)) return res;
      var retry = Object.assign({}, options || {});
      retry.headers = headers(retry.headers);
      return fetch(target, retry);
    });
  }

  window.ctbControl = {
    api: api,
    token: token,
    headers: headers,
    recover: recover,
    send: send,
    clear: function () {
      memo = '';
      store('');
    },
  };
})();
