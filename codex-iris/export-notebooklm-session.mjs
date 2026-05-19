import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import { DEFAULT_PROFILE_DIR, detectChromePath } from '../node_modules/notebooklm-client/dist/browser.js';
import { saveSession } from '../node_modules/notebooklm-client/dist/session-store.js';

const home = path.join(process.env.USERPROFILE, '.notebooklm');
const statePath = path.join(home, 'storage-state.json');

if (!fs.existsSync(statePath)) {
  throw new Error(`Missing ${statePath}. Run tutor.ps1 login first.`);
}

const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
const localProxy = process.env.CODEX_TUTOR_PROXY || 'http://127.0.0.1:7890';

async function waitForNotebookTokens(page) {
  await page.waitForFunction(
    () => {
      const bl = globalThis.WIZ_global_data?.cfb2h ?? '';
      return (
        location.hostname.includes('notebooklm.google.com') &&
        !!globalThis.WIZ_global_data?.SNlM0e &&
        bl.includes('labs-tailwind')
      );
    },
    { timeout: 90000, polling: 2000 },
  );
}

async function extractSession() {
  const attempts = [
    {
      name: 'system-proxy',
      launchOptions: { headless: true, args: ['--disable-quic'] },
    },
    {
      name: 'direct',
      launchOptions: { headless: true, args: ['--disable-quic', '--no-proxy-server'] },
    },
    {
      name: 'local-proxy',
      launchOptions: {
        headless: true,
        proxy: { server: localProxy },
        args: ['--disable-quic'],
      },
    },
  ];

  let lastError = null;

  for (const attempt of attempts) {
    let browser = null;
    let context = null;

    try {
      browser = await chromium.launch(attempt.launchOptions);
      context = await browser.newContext({ storageState: statePath });
      const page = await context.newPage();

      await page.goto('https://notebooklm.google.com/', {
        waitUntil: 'domcontentloaded',
        timeout: 90000,
      });
      await waitForNotebookTokens(page);

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
        throw new Error('Incomplete NotebookLM session extracted.');
      }

      return { data, cookieStr, cookieCount: cookies.length, attempt: attempt.name };
    } catch (error) {
      lastError = error;
      console.error(`Session export attempt failed (${attempt.name}): ${error.message}`);
    } finally {
      if (context) {
        await context.close().catch(() => {});
      }
      if (browser) {
        await browser.close().catch(() => {});
      }
    }
  }

  throw lastError || new Error('NotebookLM session export failed.');
}

async function seedBrowserProfile() {
  const chromePath = detectChromePath();
  if (!chromePath) {
    console.error('Chrome not found; skipping notebooklm-client browser profile seeding.');
    return;
  }

  fs.mkdirSync(DEFAULT_PROFILE_DIR, { recursive: true });
  const attempts = [
    {
      name: 'system-proxy',
      options: {
        executablePath: chromePath,
        headless: true,
        args: ['--no-first-run', '--no-default-browser-check', '--disable-quic'],
      },
    },
    {
      name: 'local-proxy',
      options: {
        executablePath: chromePath,
        headless: true,
        proxy: { server: localProxy },
        args: ['--no-first-run', '--no-default-browser-check', '--disable-quic'],
      },
    },
  ];

  for (const attempt of attempts) {
    let context = null;

    try {
      context = await chromium.launchPersistentContext(DEFAULT_PROFILE_DIR, attempt.options);
      await context.addCookies(state.cookies ?? []);
      const page = await context.newPage();
      await page.goto('https://notebooklm.google.com/', {
        waitUntil: 'domcontentloaded',
        timeout: 90000,
      });
      await waitForNotebookTokens(page);
      console.error(`Seeded browser profile: ${DEFAULT_PROFILE_DIR}`);
      return;
    } catch (error) {
      console.error(`Profile seed attempt failed (${attempt.name}): ${error.message}`);
    } finally {
      if (context) {
        await context.close().catch(() => {});
      }
    }
  }

  console.error('Browser profile seeding skipped after retries. HTTP mode can still work with session.json.');
}

const session = await extractSession();
const saved = await saveSession({ ...session.data, cookies: session.cookieStr });

console.log(JSON.stringify({
  ok: true,
  saved,
  cookieCount: session.cookieCount,
  language: session.data.language,
  attempt: session.attempt,
}));

await seedBrowserProfile();
