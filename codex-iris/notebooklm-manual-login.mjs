import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import readline from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import { chromium } from 'playwright';
import { detectChromePath } from '../node_modules/notebooklm-client/dist/browser.js';
import { saveSession } from '../node_modules/notebooklm-client/dist/session-store.js';

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i], process.argv[i + 1]);
}

const notebookId = args.get('--notebook-id') || '';
const port = Number(args.get('--port') || process.env.CODEX_TUTOR_CHROME_PORT || 9333);
const proxy =
  process.env.CODEX_TUTOR_PROXY ||
  process.env.HTTPS_PROXY ||
  process.env.HTTP_PROXY ||
  'http://127.0.0.1:7890';

const home = path.join(process.env.USERPROFILE, '.notebooklm');
const profileDir = process.env.CODEX_TUTOR_PROFILE_DIR ||
  path.join(home, 'manual-chrome-profile');
const storageStatePath = path.join(home, 'storage-state.json');
const notebookUrl = notebookId
  ? `https://notebooklm.google.com/notebook/${notebookId}`
  : 'https://notebooklm.google.com/';

fs.mkdirSync(profileDir, { recursive: true });

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function canReachDebugPort() {
  try {
    await getCdpEndpoint();
    return true;
  } catch {
    return false;
  }
}

async function getCdpEndpoint() {
  const response = await fetch(`http://127.0.0.1:${port}/json/version`);

  if (!response.ok) {
    throw new Error(`DevTools version endpoint returned HTTP ${response.status}`);
  }

  const data = await response.json();
  const wsUrl = data.webSocketDebuggerUrl;

  if (!wsUrl || typeof wsUrl !== 'string') {
    throw new Error('DevTools version endpoint did not return webSocketDebuggerUrl.');
  }

  return wsUrl;
}

async function waitForDebugPort() {
  for (let i = 0; i < 60; i += 1) {
    if (await canReachDebugPort()) {
      return;
    }
    await sleep(1000);
  }
  throw new Error(`Chrome remote debugging port did not open: ${port}`);
}

function launchChrome() {
  const chromePath = detectChromePath();
  if (!chromePath) {
    throw new Error('Chrome not found. Install Google Chrome first.');
  }

  const chromeArgs = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-quic',
    '--new-window',
  ];

  if (proxy) {
    chromeArgs.push(`--proxy-server=${proxy}`);
  }

  chromeArgs.push(notebookUrl);

  const child = spawn(chromePath, chromeArgs, {
    detached: true,
    stdio: 'ignore',
    windowsHide: false,
  });
  child.unref();
}

async function waitForNotebookTokens(page, timeout = 90000) {
  await page.waitForFunction(
    () => {
      const bl = globalThis.WIZ_global_data?.cfb2h ?? '';
      return (
        location.hostname.includes('notebooklm.google.com') &&
        !!globalThis.WIZ_global_data?.SNlM0e &&
        bl.includes('labs-tailwind')
      );
    },
    { timeout, polling: 2000 },
  );
}

async function extractSession(browser) {
  const contexts = browser.contexts();
  const context = contexts[0] || (await browser.newContext());
  let page = context.pages().find((candidate) =>
    notebookId && candidate.url().includes(notebookId),
  ) || context.pages().find((candidate) =>
    candidate.url().includes('notebooklm.google.com'),
  );

  if (!page) {
    page = await context.newPage();
  }

  await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });

  await waitForNotebookTokens(page);

  const pageState = await page.evaluate(() => ({
    href: location.href,
    title: document.title,
    text: document.body?.innerText?.replace(/\s+/g, ' ').slice(0, 500) ?? '',
  }));

  if (notebookId && !pageState.href.includes(notebookId)) {
    throw new Error(
      [
        `The target notebook did not open for the current Google account.`,
        `Expected notebook id: ${notebookId}`,
        `Current URL: ${pageState.href}`,
        `Page title: ${pageState.title}`,
        `Page text: ${pageState.text}`,
        `Log in with the account that can open ${notebookUrl}, or share/copy the notebook to this account.`,
      ].join('\n'),
    );
  }

  const data = await page.evaluate(() => ({
    at: globalThis.WIZ_global_data?.SNlM0e ?? '',
    bl: globalThis.WIZ_global_data?.cfb2h ?? '',
    fsid: globalThis.WIZ_global_data?.FdrFJe ?? '',
    userAgent: navigator.userAgent,
    language: navigator.language?.split('-')[0] ?? 'en',
  }));

  const cookies = await context.cookies([
    'https://notebooklm.google.com',
    'https://google.com',
    'https://accounts.google.com',
  ]);
  const cookieStr = cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; ');

  if (!data.at || !data.bl || !cookieStr) {
    throw new Error('NotebookLM session is incomplete. Confirm the Chrome window is on a logged-in NotebookLM page.');
  }

  await context.storageState({ path: storageStatePath });
  const sessionPath = await saveSession({ ...data, cookies: cookieStr });

  return {
    sessionPath,
    storageStatePath,
    cookieCount: cookies.length,
    language: data.language,
  };
}

async function openNotebookPage(browser) {
  const contexts = browser.contexts();
  const context = contexts[0] || (await browser.newContext());
  const page = await context.newPage();
  await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 }).catch((error) => {
    console.error(`Initial navigation failed: ${error.message}`);
    console.error('Use the Chrome address bar to open the NotebookLM URL manually.');
  });
  await page.bringToFront().catch(() => {});
  return page;
}

console.log(`Opening real Chrome on remote debugging port ${port}.`);
console.log(`Profile: ${profileDir}`);
console.log(`Proxy: ${proxy || 'none'}`);
console.log(`URL: ${notebookUrl}`);

if (!(await canReachDebugPort())) {
  launchChrome();
  await waitForDebugPort();
} else {
  console.log(`Reusing existing Chrome remote debugging port ${port}.`);
}

const cdpEndpoint = await getCdpEndpoint();
const browser = await chromium.connectOverCDP(cdpEndpoint);
await openNotebookPage(browser);

console.log('');
console.log('Use the opened Chrome window to log in to Google.');
console.log('Make sure the target NotebookLM notebook is visible in that Chrome window.');

const rl = readline.createInterface({ input, output });
await rl.question('After NotebookLM is visible, press Enter here to save the session...');
rl.close();

try {
  const result = await extractSession(browser);
  console.log('');
  console.log(`Saved Playwright state: ${result.storageStatePath}`);
  console.log(`Saved NotebookLM session: ${result.sessionPath}`);
  console.log(`Cookies: ${result.cookieCount}`);
  console.log(`Language: ${result.language}`);
} finally {
  await browser.close().catch(() => {});
}
