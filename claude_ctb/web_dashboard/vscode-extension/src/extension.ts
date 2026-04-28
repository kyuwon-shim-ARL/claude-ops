import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';

// Use localhost (not 127.0.0.1) so VSCode webview portMapping rewrites to the
// extension host. Required for Remote SSH: webview runs on local machine,
// CTB server runs on the remote — without portMapping the webview's localhost
// resolves to the user's local machine, not the server.
const DASHBOARD_PORT = 8420;
const DASHBOARD_URL = `http://localhost:${DASHBOARD_PORT}`;
const API_SESSIONS_URL = `${DASHBOARD_URL}/api/sessions`;
const POLL_INTERVAL = 5000; // 5 seconds

interface SessionData {
  name: string;
  state: string;
  path: string;
  updated_at: number;
}

interface SharedState {
  version: number;
  updated_at: number;
  sessions: SessionData[];
}

// --- Shared Data Fetcher (single HTTP call shared by StatusBar + TreeView) ---

let _cachedState: SharedState | null = null;

function fetchSessions(): Promise<SharedState | null> {
  return new Promise((resolve) => {
    const req = http.get(API_SESSIONS_URL, { timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', (chunk: string) => { data += chunk; });
      res.on('end', () => {
        try {
          _cachedState = JSON.parse(data) as SharedState;
          resolve(_cachedState);
        } catch {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

// --- Status Bar ---

class StatusBarManager {
  private item: vscode.StatusBarItem;
  private timer: NodeJS.Timeout | undefined;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
    this.item.command = 'claudeCtb.openDashboard';
    this.item.tooltip = 'Click to open Claude-CTB Dashboard';
    this.item.show();
    this.refresh();
    this.timer = setInterval(() => this.refresh(), POLL_INTERVAL);
  }

  async refresh(): Promise<void> {
    const state = _cachedState;
    if (!state) {
      this.item.text = '$(terminal) CTB: offline';
      this.item.color = undefined;
      return;
    }

    const sessions = state.sessions;
    const working = sessions.filter(s => s.state === 'working').length;
    const waiting = sessions.filter(s => s.state === 'waiting').length;
    const total = sessions.length;

    const parts: string[] = [`$(terminal) CTB: ${total}`];
    if (working > 0) { parts.push(`$(sync~spin) ${working}`); }
    if (waiting > 0) { parts.push(`$(bell) ${waiting}`); }

    this.item.text = parts.join(' ');

    if (waiting > 0) {
      this.item.color = new vscode.ThemeColor('statusBarItem.warningForeground');
    } else if (working > 0) {
      this.item.color = undefined; // default color for working
    } else {
      this.item.color = undefined;
    }
  }

  dispose(): void {
    if (this.timer) { clearInterval(this.timer); }
    this.item.dispose();
  }
}

// --- TreeView ---

class SessionItem extends vscode.TreeItem {
  constructor(public readonly session: SessionData) {
    super(session.name.replace(/^claude[_-]/, ''), vscode.TreeItemCollapsibleState.None);

    this.description = session.state;
    this.iconPath = new vscode.ThemeIcon(
      session.state === 'working' ? 'sync~spin' :
      session.state === 'waiting' ? 'bell' :
      session.state === 'error' ? 'error' :
      session.state === 'context_limit' ? 'warning' :
      'circle-outline'
    );

    const age = formatAge(session.updated_at);
    this.tooltip = `${session.name}\nState: ${session.state}\nPath: ${session.path || 'unknown'}\nUpdated: ${age}`;
    this.command = {
      command: 'claudeCtb.focusSession',
      title: 'Focus Terminal',
      arguments: [this],
    };
  }
}

class SessionTreeProvider implements vscode.TreeDataProvider<SessionItem> {
  private _onDidChange = new vscode.EventEmitter<SessionItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChange.event;
  private timer: NodeJS.Timeout | undefined;

  constructor() {
    // Unified poll: fetch once, then refresh both tree and status bar
    this.timer = setInterval(async () => {
      await fetchSessions();
      this._onDidChange.fire(undefined);
    }, POLL_INTERVAL);
    // Initial fetch
    fetchSessions().then(() => this._onDidChange.fire(undefined));
  }

  getTreeItem(element: SessionItem): vscode.TreeItem { return element; }

  getChildren(): SessionItem[] {
    const state = _cachedState;
    if (!state) { return []; }

    const order: Record<string, number> = { working: 0, waiting: 1, context_limit: 2, error: 3, idle: 4, unknown: 5 };
    const sorted = [...state.sessions].sort((a, b) => (order[a.state] ?? 9) - (order[b.state] ?? 9));
    return sorted.map(s => new SessionItem(s));
  }

  refresh(): void {
    this._onDidChange.fire(undefined);
  }

  dispose(): void {
    if (this.timer) { clearInterval(this.timer); }
    this._onDidChange.dispose();
  }
}

// --- WebView Panel ---

class DashboardPanel {
  private static panel: vscode.WebviewPanel | undefined;

  static async show(context: vscode.ExtensionContext): Promise<void> {
    if (DashboardPanel.panel) {
      // Always refresh HTML so server-side changes are picked up without reopening
      DashboardPanel.panel.webview.html = await getWebviewContent(context);
      DashboardPanel.panel.reveal();
      return;
    }

    DashboardPanel.panel = vscode.window.createWebviewPanel(
      'claudeCtbDashboard',
      'Claude-CTB Dashboard',
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        // Remote SSH: route webview's localhost:8420 → extension host's 8420
        // so the webview can reach the CTB server running on the remote.
        portMapping: [{ webviewPort: DASHBOARD_PORT, extensionHostPort: DASHBOARD_PORT }],
      }
    );

    DashboardPanel.panel.webview.html = await getWebviewContent(context);

    // Handle messages from webview (card click → terminal focus)
    DashboardPanel.panel.webview.onDidReceiveMessage((message: { type: string; session?: string; url?: string }) => {
      if (message.type === 'focusSession' && message.session) {
        focusOrCreateTerminalForSession(message.session);
      } else if (message.type === 'openUrl' && message.url) {
        // Load the URL in-panel as an iframe so Projects view stays in the webview.
        // The proxy script forwards child-iframe postMessages to the extension so that
        // the Sessions page loaded inside the iframe can still use the VSCode API
        // (acquireVsCodeApi is only available in the top-level webview frame).
        const _va = `acquireVsCodeApi()`;
        DashboardPanel.panel!.webview.html =
          `<!DOCTYPE html><html><head><style>` +
          `body{margin:0;overflow:hidden}iframe{width:100%;height:100vh;border:none}` +
          `</style></head><body><iframe src="${message.url}"></iframe>` +
          `<script>const _va=${_va};window.addEventListener('message',e=>{if(e.data&&e.data.type)_va.postMessage(e.data);});</script>` +
          `</body></html>`;
      }
    });

    DashboardPanel.panel.onDidDispose(() => { DashboardPanel.panel = undefined; });
  }
}

/** Fetch the dashboard HTML directly from the running server. */
function fetchServerHtml(): Promise<string | null> {
  return new Promise((resolve) => {
    const req = http.get(DASHBOARD_URL, { timeout: 2000 }, (res) => {
      let data = '';
      res.on('data', (chunk: string) => { data += chunk; });
      res.on('end', () => { resolve(data); });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

/** Rewrite relative /api URLs so they reach the CTB server from inside the webview. */
function applyUrlRewrites(html: string): string {
  html = html.replace(/fetch\('\/api/g, `fetch('${DASHBOARD_URL}/api`);
  html = html.replace(/EventSource\('\/api/g, `EventSource('${DASHBOARD_URL}/api`);
  return html;
}

/**
 * Patch server HTML nav links for the webview context:
 *  - Replace real hrefs with '#' (navigation must go through postMessage)
 *  - Inject nav-projects click handler
 * NOTE: _vscodeApi is already declared in the server HTML — do NOT re-declare it here.
 */
function applyNavPatches(html: string): string {
  html = html.replace('<a href="/" style=', '<a href="#" style=');
  html = html.replace('<a href="/projects" style=', '<a id="nav-projects" href="#" style=');
  // Inject click handler before </body>; references _vscodeApi from the main script tag
  html = html.replace('</body>', `<script>
document.getElementById('nav-projects')?.addEventListener('click', function(e) {
  e.preventDefault();
  if (typeof _vscodeApi !== 'undefined' && _vscodeApi) {
    _vscodeApi.postMessage({ type: 'openUrl', url: '${DASHBOARD_URL}/projects' });
  }
});
</script>
</body>`);
  return html;
}

async function getWebviewContent(context: vscode.ExtensionContext): Promise<string> {
  // 1. Prefer live server HTML — always up-to-date, no manual sync needed
  const serverHtml = await fetchServerHtml();
  if (serverHtml) {
    return applyNavPatches(applyUrlRewrites(serverHtml));
  }

  // 2. Fall back to bundled static file when server is offline
  //    Static file already has nav patches baked in; only rewrite URLs.
  const possiblePaths = [
    path.join(context.extensionPath, 'static', 'index.html'),
    path.join(context.extensionPath, '..', 'static', 'index.html'),
  ];
  for (const htmlPath of possiblePaths) {
    try {
      if (fs.existsSync(htmlPath)) {
        return applyUrlRewrites(fs.readFileSync(htmlPath, 'utf-8'));
      }
    } catch { /* fall through */ }
  }

  // 3. Last resort: iframe
  return `<!DOCTYPE html>
<html><head><style>body{margin:0;overflow:hidden}iframe{width:100%;height:100vh;border:none}</style></head>
<body><iframe src="${DASHBOARD_URL}"></iframe></body></html>`;
}

// --- Terminal Focus ---

// Debounce timer for activateTerminal — prevents rapid-click focus thrash
let _focusTimer: NodeJS.Timeout | undefined;

function focusTerminalForSession(sessionName: string): boolean {
  const terminals = vscode.window.terminals;
  const stripped = sessionName.replace(/^claude[_-]/, '');

  // Strict exact match only. Substring matching previously caused wrong-terminal
  // focus regressions: e.g. clicking "claude_research" would match an existing
  // "omc-research-skills" terminal because the latter contained "research".
  // If no exact match is found, the caller creates a new terminal.
  const exact = terminals.find(t =>
    t.name === sessionName || t.name === stripped
  );
  if (exact) {
    activateTerminal(exact);
    return true;
  }

  // Worktree pattern: claude_{project}_wt_{leaf} → match against leaf only (exact)
  const wtMatch = sessionName.match(/^claude_.*?_wt_(.+)$/);
  if (wtMatch) {
    const leaf = wtMatch[1];
    const wt = terminals.find(t => t.name === leaf);
    if (wt) { activateTerminal(wt); return true; }
  }

  return false;
}

/**
 * Create a new VSCode terminal attached to the given tmux session.
 * Used as fallback when focusTerminalForSession finds no existing terminal.
 */
function createTerminalForSession(sessionName: string): vscode.Terminal {
  // Derive a clean display name: worktree leaf or stripped prefix
  const wtMatch = sessionName.match(/^claude_.*?_wt_(.+)$/);
  const displayName = wtMatch ? wtMatch[1] : sessionName.replace(/^claude[_-]/, '');

  const terminal = vscode.window.createTerminal({ name: displayName });
  // If only a shell is running in the pane (no Claude Code), start it before attaching.
  // The check runs in the new terminal's shell before handing control to tmux.
  const sn = sessionName.replace(/'/g, "'\\''"); // safe single-quote escape
  const claudeCmd = 'claude --continue --dangerously-skip-permissions';
  const wrapper = `bash --login -c '${claudeCmd}; exec bash --login'`;
  // Handles three pane states:
  //   pane_dead=1  → respawn-pane with claude wrapper (remain-on-exit killed pane)
  //   bash/zsh/…   → send claude cmd only when no claude child (ps --ppid guard)
  //   claude       → just attach, already running
  const cmd =
    `if ! tmux has-session -t '=${sn}' 2>/dev/null; then ` +
    `echo "Session not found: ${sn}"; exit 1; fi; ` +
    `_dead=$(tmux display-message -p -t '=${sn}' '#{pane_dead}' 2>/dev/null); ` +
    `_pid=$(tmux display-message -p -t '=${sn}' '#{pane_pid}' 2>/dev/null); ` +
    `_cmd=$(tmux display-message -p -t '=${sn}' '#{pane_current_command}' 2>/dev/null); ` +
    `if [[ "$_dead" == "1" ]]; then ` +
    `tmux respawn-pane -k -t '=${sn}' "${wrapper}"; ` +
    `elif [[ "$_cmd" =~ ^(bash|zsh|sh|fish|dash|ksh|tcsh)$ ]]; then ` +
    `if ! ps --ppid "$_pid" -o comm --no-headers 2>/dev/null | grep -q claude; then ` +
    `tmux send-keys -t '=${sn}' '${claudeCmd}' Enter; fi; fi; ` +
    `tmux attach-session -t '=${sn}'`;
  terminal.sendText(cmd, true);
  return terminal;
}

/** Focus an existing terminal for the session, or create one if none exists. */
function focusOrCreateTerminalForSession(sessionName: string): void {
  const found = focusTerminalForSession(sessionName);
  if (!found) {
    const t = createTerminalForSession(sessionName);
    activateTerminal(t);
  }
}

/**
 * Reveal a terminal and ensure it receives keyboard focus.
 * terminal.show(false) reveals the panel but may not always route keyboard
 * input (especially when called from file-watcher or URI handler contexts).
 * We follow up with workbench.action.terminal.focus to guarantee input routing.
 */
function activateTerminal(terminal: vscode.Terminal): void {
  terminal.show(false); // preserveFocus=false → request focus
  // Debounce: cancel any pending focus command before scheduling a new one.
  // Rapid card clicks would otherwise queue N focus commands, causing VSCode
  // UI focus-thrash and WebView unresponsiveness.
  if (_focusTimer) { clearTimeout(_focusTimer); }
  _focusTimer = setTimeout(() => {
    _focusTimer = undefined;
    vscode.commands.executeCommand('workbench.action.terminal.focus');
  }, 150);
}

// --- URI Handler (vscode://claude-ctb.claude-ctb-dashboard/focus?session=name) ---

class CTBUriHandler implements vscode.UriHandler {
  handleUri(uri: vscode.Uri): vscode.ProviderResult<void> {
    const params = new URLSearchParams(uri.query);
    const session = params.get('session');
    if (uri.path === '/focus' && session) {
      focusOrCreateTerminalForSession(session);
    }
  }
}

// --- Helpers ---

function formatAge(ts: number): string {
  if (!ts) { return '—'; }
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 0) { return 'just now'; }
  if (diff < 60) { return `${diff}s ago`; }
  if (diff < 3600) { return `${Math.floor(diff / 60)}m ago`; }
  if (diff < 86400) { return `${Math.floor(diff / 3600)}h ago`; }
  return `${Math.floor(diff / 86400)}d ago`;
}

// --- Focus Signal Watcher (IPC: dashboard server → extension) ---

const FOCUS_SIGNAL_PATH = '/tmp/ctb-focus-signal.json';

class FocusSignalWatcher {
  private watcher: fs.FSWatcher | undefined;
  private pollTimer: NodeJS.Timeout | undefined;
  private disposed = false;

  start(): void {
    // Ensure signal file exists so fs.watch has something to watch
    try {
      if (!fs.existsSync(FOCUS_SIGNAL_PATH)) {
        fs.writeFileSync(FOCUS_SIGNAL_PATH, '', { mode: 0o666 });
      }
    } catch { /* ignore */ }

    try {
      this.watcher = fs.watch(FOCUS_SIGNAL_PATH, () => this.onSignal());
    } catch { /* ignore — polling backup below covers this */ }

    // Always poll as backup: fs.watch on Linux can silently stop firing events
    this.pollTimer = setInterval(() => this.onSignal(), 800);
  }

  private onSignal(): void {
    if (this.disposed) { return; }
    try {
      const raw = fs.readFileSync(FOCUS_SIGNAL_PATH, 'utf-8').trim();
      if (!raw) { return; }
      const signal = JSON.parse(raw);
      if (signal.session && signal.ts) {
        // Clear signal immediately to prevent re-triggering
        fs.writeFileSync(FOCUS_SIGNAL_PATH, '', { mode: 0o666 });
        focusOrCreateTerminalForSession(signal.session);
      }
    } catch { /* ignore parse errors, empty file, etc. */ }
  }

  dispose(): void {
    this.disposed = true;
    if (this.watcher) { this.watcher.close(); }
    if (this.pollTimer) { clearInterval(this.pollTimer); }
  }
}

// --- Activation ---

export function activate(context: vscode.ExtensionContext): void {
  const statusBar = new StatusBarManager();
  const treeProvider = new SessionTreeProvider();
  const focusWatcher = new FocusSignalWatcher();
  focusWatcher.start();

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('claudeCtbSessions', treeProvider),
    vscode.commands.registerCommand('claudeCtb.openDashboard', () => DashboardPanel.show(context)),
    vscode.commands.registerCommand('claudeCtb.refreshSessions', async () => {
      await fetchSessions();
      statusBar.refresh();
      treeProvider.refresh();
    }),
    vscode.commands.registerCommand('claudeCtb.focusSession', (item: SessionItem) => {
      focusOrCreateTerminalForSession(item.session.name);
    }),
    vscode.window.registerUriHandler(new CTBUriHandler()),
    { dispose: () => { statusBar.dispose(); treeProvider.dispose(); focusWatcher.dispose(); } },
  );
}

export function deactivate(): void {}
