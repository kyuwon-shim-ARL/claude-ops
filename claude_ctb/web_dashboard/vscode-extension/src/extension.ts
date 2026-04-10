import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';

const DASHBOARD_URL = 'http://127.0.0.1:8420';
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

  static show(context: vscode.ExtensionContext): void {
    if (DashboardPanel.panel) {
      // Always refresh HTML so file changes take effect without closing the panel
      DashboardPanel.panel.webview.html = getWebviewContent(context);
      DashboardPanel.panel.reveal();
      return;
    }

    DashboardPanel.panel = vscode.window.createWebviewPanel(
      'claudeCtbDashboard',
      'Claude-CTB Dashboard',
      vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    DashboardPanel.panel.webview.html = getWebviewContent(context);

    // Handle messages from webview (card click → terminal focus)
    DashboardPanel.panel.webview.onDidReceiveMessage((message: { type: string; session?: string }) => {
      if (message.type === 'focusSession' && message.session) {
        const found = focusTerminalForSession(message.session);
        if (!found) {
          vscode.window.showWarningMessage(`Terminal not found for: ${message.session}`);
        }
      }
    });

    DashboardPanel.panel.onDidDispose(() => { DashboardPanel.panel = undefined; });
  }
}

function getWebviewContent(context: vscode.ExtensionContext): string {
  // Try to load the static HTML from the extension's bundled files
  const possiblePaths = [
    path.join(context.extensionPath, 'static', 'index.html'),
    path.join(context.extensionPath, '..', 'static', 'index.html'),
  ];

  for (const htmlPath of possiblePaths) {
    try {
      if (fs.existsSync(htmlPath)) {
        let html = fs.readFileSync(htmlPath, 'utf-8');
        // Rewrite API URLs to point at the local server
        html = html.replace(/fetch\('\/api/g, `fetch('${DASHBOARD_URL}/api`);
        html = html.replace(/EventSource\('\/api/g, `EventSource('${DASHBOARD_URL}/api`);
        return html;
      }
    } catch { /* fall through */ }
  }

  // Fallback: iframe to the running server
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

  // 1. Exact match (terminal name === session name or stripped name)
  const exact = terminals.find(t =>
    t.name === sessionName || t.name === stripped
  );
  if (exact) {
    activateTerminal(exact);
    return true;
  }

  // 2. Contains match: terminal name includes session name or stripped name
  const containsFull = terminals.find(t =>
    t.name.includes(sessionName) || t.name.includes(stripped)
  );
  if (containsFull) {
    activateTerminal(containsFull);
    return true;
  }

  // 3. Case-insensitive partial match
  const lowerStripped = stripped.toLowerCase();
  const partial = terminals.find(t =>
    t.name.toLowerCase().includes(lowerStripped)
  );
  if (partial) {
    activateTerminal(partial);
    return true;
  }

  return false;
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
      const found = focusTerminalForSession(session);
      if (!found) {
        vscode.window.showWarningMessage(`Terminal not found for session: ${session}`);
      }
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
        const found = focusTerminalForSession(signal.session);
        if (!found) {
          vscode.window.showWarningMessage(`Terminal not found for: ${signal.session}`);
        }
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
      const found = focusTerminalForSession(item.session.name);
      if (!found) {
        vscode.window.showWarningMessage(`Terminal not found for: ${item.session.name}`);
      }
    }),
    vscode.window.registerUriHandler(new CTBUriHandler()),
    { dispose: () => { statusBar.dispose(); treeProvider.dispose(); focusWatcher.dispose(); } },
  );
}

export function deactivate(): void {}
