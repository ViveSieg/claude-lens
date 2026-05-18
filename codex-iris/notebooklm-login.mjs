import fs from 'node:fs';
import path from 'node:path';
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
const notebookUrl = notebookId
  ? `https://notebooklm.google.com/notebook/${notebookId}`
  : 'https://notebooklm.google.com/';

const home = path.join(process.env.USERPROFILE, '.notebooklm');
const storageStatePath = path.join(home, 'storage-state.json');
const proxy =
  process.env.CODEX_TUTOR_PROXY ||
  process.env.HTTPS_PROXY ||
  process.env.HTTP_PROXY ||
  'http://127.0.0.1:7890';

fs.mkdirSync(home, { recursive: true });

function browserLaunchOptions() {
  const chromePath = detectChromePath();
  return {
    headless: false,
    executablePath: chromePath,
    proxy: proxy ? { server: proxy } : undefined,
    args: [
      '--disable-quic',
      '--no-first-run',
      '--no-default-browser-check',
    ],
  };
}

async function waitForTokens(page, timeout = 120000) {
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

async function extractSession(context, page) {
  await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await waitForTokens(page);

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
  const cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join('; ');

  if (!data.at || !data.bl || !cookieStr) {
    throw new Error('NotebookLM session is incomplete. Make sure the browser is on a logged-in NotebookLM page.');
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

const browser = await chromium.launch(browserLaunchOptions());
const context = await browser.newContext();
const page = await context.newPage();

try {
  console.log(`Proxy: ${proxy || 'none'}`);
  console.log(`Opening: ${notebookUrl}`);
  await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 }).catch((error) => {
    console.error(`Initial navigation failed: ${error.message}`);
    console.error('Keep the browser open, finish Google login manually, then press Enter here.');
  });

  console.log('');
  console.log('Please complete Google login in the opened browser.');
  console.log('If possible, open the target NotebookLM notebook in that browser tab.');
  const rl = readline.createInterface({ input, output });
  await rl.question('Once NotebookLM is visible, press Enter here to save the login session...');
  rl.close();

  const result = await extractSession(context, page);
  console.log('');
  console.log(`Saved Playwright state: ${result.storageStatePath}`);
  console.log(`Saved NotebookLM session: ${result.sessionPath}`);
  console.log(`Cookies: ${result.cookieCount}`);
  console.log(`Language: ${result.language}`);
} finally {
  await context.close().catch(() => {});
  await browser.close().catch(() => {});
}
