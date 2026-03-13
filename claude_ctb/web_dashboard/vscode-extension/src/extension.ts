import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';

const STATE_FILE = '/tmp/ctb-sessions.json';
const DASHBOARD_URL = 'http://127.0.0.1:8420';
const POLL_INTERVAL = 5000; // 5 seconds

interface SessionData {
  name: string;
  state: string;
  last_activity: number;
  updated_at: number;
  notification_sent?: boolean;
}

interface SharedState {
  version: number;
  updated_at: number;
  sessions: SessionData[];
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

  refresh(): void {
    const state = readStateFile();
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
      this.item.color = new vscode.ThemeColor('statusBarItem.prominentForeground');
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

    const stateIcons: Record<string, string> = {
      working: '$(sync~spin)',
      waiting: '$(bell)',
      idle: '$(circle-outline)',
      error: '$(error)',
      context_limit: '$(warning)',
      unknown: '$(question)',
    };

    this.description = session.state;
    this.iconPath = new vscode.ThemeIcon(
      session.state === 'working' ? 'sync~spin' :
      session.state === 'waiting' ? 'bell' :
      session.state === 'error' ? 'error' :
      session.state === 'context_limit' ? 'warning' :
      'circle-outline'
    );

    const age = formatAge(session.last_activity);
    this.tooltip = `${session.name}\nState: ${session.state}\nActivity: ${age}`;
  }
}

class SessionTreeProvider implements vscode.TreeDataProvider<SessionItem> {
  private _onDidChange = new vscode.EventEmitter<SessionItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChange.event;
  private timer: NodeJS.Timeout | undefined;

  constructor() {
    this.timer = setInterval(() => this._onDidChange.fire(undefined), POLL_INTERVAL);
  }

  getTreeItem(element: SessionItem): vscode.TreeItem { return element; }

  getChildren(): SessionItem[] {
    const state = readStateFile();
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
      DashboardPanel.panel.reveal();
      return;
    }

    DashboardPanel.panel = vscode.window.createWebviewPanel(
      'claudeCtbDashboard',
      'Claude-CTB Dashboard',
      vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    DashboardPanel.panel.webview.html = getWebviewContent();
    DashboardPanel.panel.onDidDispose(() => { DashboardPanel.panel = undefined; });
  }
}

function getWebviewContent(): string {
  // Try to load the static HTML from the Python package
  const htmlPath = path.join(__dirname, '..', '..', 'static', 'index.html');
  try {
    if (fs.existsSync(htmlPath)) {
      let html = fs.readFileSync(htmlPath, 'utf-8');
      // Rewrite API URLs to point at the local server
      html = html.replace(/fetch\('\/api/g, `fetch('${DASHBOARD_URL}/api`);
      html = html.replace(/EventSource\('\/api/g, `EventSource('${DASHBOARD_URL}/api`);
      return html;
    }
  } catch { /* fall through */ }

  // Fallback: iframe to the running server
  return `<!DOCTYPE html>
<html><head><style>body{margin:0;overflow:hidden}iframe{width:100%;height:100vh;border:none}</style></head>
<body><iframe src="${DASHBOARD_URL}"></iframe></body></html>`;
}

// --- Helpers ---

function readStateFile(): SharedState | null {
  try {
    const raw = fs.readFileSync(STATE_FILE, 'utf-8');
    return JSON.parse(raw) as SharedState;
  } catch {
    return null;
  }
}

function formatAge(ts: number): string {
  if (!ts) { return '—'; }
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 0) { return 'just now'; }
  if (diff < 60) { return `${diff}s ago`; }
  if (diff < 3600) { return `${Math.floor(diff / 60)}m ago`; }
  if (diff < 86400) { return `${Math.floor(diff / 3600)}h ago`; }
  return `${Math.floor(diff / 86400)}d ago`;
}

// --- Activation ---

export function activate(context: vscode.ExtensionContext): void {
  const statusBar = new StatusBarManager();
  const treeProvider = new SessionTreeProvider();

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('claudeCtbSessions', treeProvider),
    vscode.commands.registerCommand('claudeCtb.openDashboard', () => DashboardPanel.show(context)),
    vscode.commands.registerCommand('claudeCtb.refreshSessions', () => {
      statusBar.refresh();
      treeProvider.refresh();
    }),
    { dispose: () => { statusBar.dispose(); treeProvider.dispose(); } },
  );
}

export function deactivate(): void {}
