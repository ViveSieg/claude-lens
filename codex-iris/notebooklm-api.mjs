import { NotebookClient } from 'notebooklm-client';
import { chromium } from 'playwright';
import { appendFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { parseListNotebooks, parseNotebookDetail, parseChatStream } from '../node_modules/notebooklm-client/dist/parser.js';
import { NB_RPC, NB_URLS, PLATFORM_WEB } from '../node_modules/notebooklm-client/dist/rpc-ids.js';

const [, , command, ...args] = process.argv;

function writeJson(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function debug(message) {
  if (process.env.CODEX_TUTOR_DEBUG === '1') {
    const line = `[codex-tutor] ${message}\n`;
    process.stderr.write(line);
    if (process.env.CODEX_TUTOR_DEBUG_FILE) {
      try {
        appendFileSync(process.env.CODEX_TUTOR_DEBUG_FILE, line);
      } catch {}
    }
  }
}

function withTimeout(promise, ms, label) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      const error = new Error(`${label} timed out after ${Math.round(ms / 1000)} seconds.`);
      error.code = 'CODEX_TUTOR_TIMEOUT';
      reject(error);
    }, ms);
  });

  return Promise.race([promise, timeout]).finally(() => clearTimeout(timeoutId));
}

function getProxy() {
  return (
    process.env.CODEX_TUTOR_PROXY ||
    process.env.HTTPS_PROXY ||
    process.env.HTTP_PROXY ||
    ''
  );
}

function nextReqId() {
  return String(Math.floor(Math.random() * 900000) + 100000);
}

function prefersCdp() {
  return (
    process.env.CODEX_TUTOR_TRANSPORT === 'cdp' ||
    (!!process.env.CODEX_TUTOR_CHROME_PORT && process.env.CODEX_TUTOR_TRANSPORT !== 'http')
  );
}

function connectOptions(transport) {
  const options = { transport };

  if (transport === 'browser') {
    const proxy = getProxy();
    options.profileDir =
      process.env.CODEX_TUTOR_PROFILE_DIR ||
      path.join(homedir(), '.notebooklm', 'manual-chrome-profile');
    options.headless = process.env.CODEX_TUTOR_BROWSER_HEADLESS === 'false'
      ? false
      : true;
    options.args = ['--disable-quic'];
    if (proxy) {
      options.args.push(`--proxy-server=${proxy}`);
    }
  }

  return options;
}

async function getCdpEndpoint() {
  const ports = [
    process.env.CODEX_TUTOR_CHROME_PORT,
    '9555',
    '9333',
  ].filter(Boolean);

  const errors = [];

  for (const port of ports) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);

      if (!response.ok) {
        errors.push(`${port}: HTTP ${response.status}`);
        continue;
      }

      const data = await response.json();

      if (data.webSocketDebuggerUrl) {
        return data.webSocketDebuggerUrl;
      }

      errors.push(`${port}: missing webSocketDebuggerUrl`);
    } catch (error) {
      errors.push(`${port}: ${error.message}`);
    }
  }

  throw new Error(`No Chrome DevTools endpoint found. Tried: ${errors.join('; ')}`);
}

class CdpNotebookTransport {
  constructor(browser, page, session, ownsPage = false) {
    this.browser = browser;
    this.page = page;
    this.session = session;
    this.ownsPage = ownsPage;
  }

  static async create(notebookId = '') {
    debug(`CDP create start notebook=${notebookId || '(none)'}`);
    const endpoint = await getCdpEndpoint();
    debug(`CDP endpoint resolved`);
    const browser = await chromium.connectOverCDP(endpoint);
    debug(`CDP connected`);
    const contexts = browser.contexts();
    const context = contexts[0] || (await browser.newContext());
    const notebookUrl = notebookId
      ? `https://notebooklm.google.com/notebook/${notebookId}`
      : 'https://notebooklm.google.com/';

    let ownsPage = false;
    let page = context.pages().find((candidate) =>
      notebookId && candidate.url().includes(notebookId),
    ) || context.pages().find((candidate) =>
      candidate.url().includes('notebooklm.google.com'),
    );

    if (!page) {
      debug(`CDP opening new NotebookLM page`);
      page = await context.newPage();
      ownsPage = true;
      await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
    } else if (!page.url().includes('notebooklm.google.com')) {
      debug(`CDP navigating existing page to NotebookLM`);
      await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
    } else {
      debug(`CDP using existing page ${page.url()}`);
    }

    try {
      debug(`CDP waiting for tokens on selected page`);
      await CdpNotebookTransport.waitForTokens(page, 15000);
    } catch (error) {
      if (ownsPage) {
        throw error;
      }

      debug(`CDP selected page had no tokens, opening a fresh page`);
      page = await context.newPage();
      ownsPage = true;
      await page.goto(notebookUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
      await CdpNotebookTransport.waitForTokens(page);
    }
    const session = await CdpNotebookTransport.extractSession(context, page);
    debug(`CDP session extracted`);
    process.stderr.write(`NotebookLM: Connected via existing Chrome CDP (bl=${session.bl.slice(0, 40)}...)\n`);

    return new CdpNotebookTransport(browser, page, session, ownsPage);
  }

  static async waitForTokens(page, timeout = 90000) {
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

  static async extractSession(_context, page) {
    const data = await page.evaluate(() => ({
      at: globalThis.WIZ_global_data?.SNlM0e ?? '',
      bl: globalThis.WIZ_global_data?.cfb2h ?? '',
      fsid: globalThis.WIZ_global_data?.FdrFJe ?? '',
      userAgent: navigator.userAgent,
      language: navigator.language?.split('-')[0] ?? 'en',
    }));

    if (!data.at || !data.bl) {
      throw new Error('NotebookLM session is incomplete in the connected Chrome window.');
    }

    return { ...data, cookies: '' };
  }

  async execute(req) {
    debug(`CDP execute start ${req.url}`);
    const text = await this.page.evaluate(async (params) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), params.timeoutMs);

      let res;
      try {
        res = await fetch(`${params.url}?${params.qp}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
          body: params.body,
          credentials: 'include',
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      return res.text();
    }, {
      url: req.url,
      qp: new URLSearchParams(req.queryParams).toString(),
      body: new URLSearchParams(req.body).toString(),
      timeoutMs: Number(process.env.CODEX_TUTOR_FETCH_TIMEOUT_MS || 180000),
    });
    debug(`CDP execute end ${req.url} length=${text.length}`);
    return text;
  }

  getSession() {
    return this.session;
  }

  async refreshSession() {
    await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
    await CdpNotebookTransport.waitForTokens(this.page, 60000);
    const context = this.page.context();
    this.session = await CdpNotebookTransport.extractSession(context, this.page);
  }

  async dispose() {
    if (this.ownsPage) {
      await this.page.close().catch(() => {});
    }
    await this.browser.close().catch(() => {});
  }
}

async function withCdpTransport(notebookId, callback) {
  debug(`withCdpTransport start`);
  const transport = await withTimeout(
    CdpNotebookTransport.create(notebookId),
    Number(process.env.CODEX_TUTOR_CONNECT_TIMEOUT_MS || 90000),
    'NotebookLM CDP connect',
  );

  try {
    debug(`withCdpTransport callback start`);
    return await callback(transport);
  } finally {
    debug(`withCdpTransport dispose start`);
    await withTimeout(
      transport.dispose().catch(() => {}),
      5000,
      'NotebookLM CDP dispose',
    ).catch(() => {});
  }
}

async function callCdpBatchExecute(transport, rpcId, payload, sourcePath = '/') {
  const { at, bl, fsid, language } = transport.getSession();
  const fReq = JSON.stringify([[[rpcId, JSON.stringify(payload), null, 'generic']]]);
  return transport.execute({
    url: NB_URLS.BATCH_EXECUTE,
    queryParams: {
      rpcids: rpcId,
      'source-path': sourcePath,
      bl,
      hl: language ?? 'en',
      _reqid: nextReqId(),
      rt: 'c',
      ...(fsid ? { 'f.sid': fsid } : {}),
    },
    body: { 'f.req': fReq, at },
  });
}

async function callCdpChatStream(transport, notebookId, message, sourceIds) {
  const { at, bl, fsid, language } = transport.getSession();
  const sourceIdArrays = sourceIds.map((id) => [[id]]);
  const innerPayload = [
    sourceIdArrays,
    message,
    [],
    [2, null, [1], [1]],
    null,
    null,
    null,
    notebookId,
    1,
  ];

  return transport.execute({
    url: NB_URLS.CHAT_STREAM,
    queryParams: {
      bl,
      hl: language ?? 'en',
      _reqid: nextReqId(),
      rt: 'c',
      ...(fsid ? { 'f.sid': fsid } : {}),
    },
    body: {
      'f.req': JSON.stringify([null, JSON.stringify(innerPayload)]),
      at,
    },
  });
}

async function listNotebooksViaCdp() {
  debug(`list via cdp start`);
  return withCdpTransport('', async (transport) => {
    const raw = await withTimeout(
      callCdpBatchExecute(transport, NB_RPC.LIST_NOTEBOOKS, [null, 1, null, [...PLATFORM_WEB]], '/'),
      Number(process.env.CODEX_TUTOR_DETAIL_TIMEOUT_MS || 90000),
      'NotebookLM list',
    );
    return parseListNotebooks(raw);
  });
}

async function getNotebookDetailViaCdp(notebookId) {
  debug(`detail via cdp start`);
  return withCdpTransport(notebookId, async (transport) => {
    const raw = await withTimeout(
      callCdpBatchExecute(
        transport,
        NB_RPC.GET_NOTEBOOK,
        [notebookId, null, [...PLATFORM_WEB], null, 1],
        `/notebook/${notebookId}`,
      ),
      Number(process.env.CODEX_TUTOR_DETAIL_TIMEOUT_MS || 90000),
      'NotebookLM detail',
    );
    debug(`detail via cdp raw length ${raw.length}`);
    return parseNotebookDetail(raw);
  });
}

async function askNotebookViaCdp(notebookId, question) {
  debug(`ask via cdp start`);
  return withCdpTransport(notebookId, async (transport) => {
    const detailRaw = await withTimeout(
      callCdpBatchExecute(
        transport,
        NB_RPC.GET_NOTEBOOK,
        [notebookId, null, [...PLATFORM_WEB], null, 1],
        `/notebook/${notebookId}`,
      ),
      Number(process.env.CODEX_TUTOR_DETAIL_TIMEOUT_MS || 90000),
      'NotebookLM detail',
    );
    debug(`ask detail raw length ${detailRaw.length}`);
    const detail = parseNotebookDetail(detailRaw);
    const sourceIds = detail.sources.map((source) => source.id);

    if (sourceIds.length === 0) {
      throw new Error('The selected notebook has no sources.');
    }

    const chatRaw = await withTimeout(
      callCdpChatStream(transport, notebookId, question, sourceIds),
      Number(process.env.CODEX_TUTOR_ASK_TIMEOUT_MS || 180000),
      'NotebookLM ask',
    );
    debug(`ask chat raw length ${chatRaw.length}`);
    return parseChatStream(chatRaw);
  });
}

function isTlsHandshakeFailure(error) {
  const message = error?.message || String(error);
  return /handshake failure|SSL routines|tls alert/i.test(message);
}

async function withClient(callback) {
  const requestedTransport = process.env.CODEX_TUTOR_TRANSPORT ||
    (process.env.CODEX_TUTOR_CHROME_PORT ? 'cdp' : 'http');
  const transports = [requestedTransport];
  const connectTimeoutMs = Number(process.env.CODEX_TUTOR_CONNECT_TIMEOUT_MS || 90000);

  if (requestedTransport !== 'browser' && process.env.CODEX_TUTOR_DISABLE_BROWSER_FALLBACK !== '1') {
    transports.push('cdp');
  }

  let lastError = null;

  for (const transport of transports) {
    const client = new NotebookClient();

    try {
      if (transport === 'cdp') {
        client.transport = await withTimeout(
          CdpNotebookTransport.create(args[0] || ''),
          connectTimeoutMs,
          'NotebookLM CDP connect',
        );
        client.transportMode = 'cdp';
      } else {
        await withTimeout(
          client.connect(connectOptions(transport)),
          connectTimeoutMs,
          `NotebookLM ${transport} connect`,
        );
      }
      return await callback(client);
    } catch (error) {
      lastError = error;

      if (transport !== 'http' || !isTlsHandshakeFailure(error)) {
        throw error;
      }

      process.stderr.write('NotebookLM HTTP transport hit TLS handshake failure; retrying with existing Chrome CDP transport.\n');
    } finally {
      await withTimeout(
        client.disconnect().catch(() => {}),
        5000,
        'NotebookLM disconnect',
      ).catch(() => {});
    }
  }

  throw lastError || new Error('NotebookLM connection failed.');
}

try {
  if (command === 'list') {
    if (prefersCdp()) {
      const notebooks = await listNotebooksViaCdp();
      writeJson({
        ok: true,
        notebooks: notebooks.map((notebook) => ({
          id: notebook.id,
          title: notebook.title || '(untitled)',
          sourceCount: notebook.sourceCount || 0,
          updatedAt: notebook.updatedAt,
        })),
      });
    } else {
      await withClient(async (client) => {
        const notebooks = await client.listNotebooks();
        writeJson({
          ok: true,
          notebooks: notebooks.map((notebook) => ({
            id: notebook.id,
            title: notebook.title || '(untitled)',
            sourceCount: notebook.sourceCount || 0,
            updatedAt: notebook.updatedAt,
          })),
        });
      });
    }
  } else if (command === 'detail') {
    const [notebookId] = args;

    if (!notebookId) {
      throw new Error('Usage: notebooklm-api.mjs detail <notebook-id>');
    }

    if (prefersCdp()) {
      const detail = await getNotebookDetailViaCdp(notebookId);
      writeJson({
        ok: true,
        notebook: {
          id: notebookId,
          title: detail.title || '',
          sourceCount: detail.sources.length,
          sources: detail.sources.map((source) => ({
            id: source.id,
            title: source.title || '',
            wordCount: source.wordCount || 0,
            url: source.url || '',
          })),
        },
      });
    } else {
      await withClient(async (client) => {
        const detail = await withTimeout(
          client.getNotebookDetail(notebookId),
          Number(process.env.CODEX_TUTOR_DETAIL_TIMEOUT_MS || 90000),
          'NotebookLM detail',
        );
        writeJson({
          ok: true,
          notebook: {
            id: notebookId,
            title: detail.title || '',
            sourceCount: detail.sources.length,
            sources: detail.sources.map((source) => ({
              id: source.id,
              title: source.title || '',
              wordCount: source.wordCount || 0,
              url: source.url || '',
            })),
          },
        });
      });
    }
  } else if (command === 'ask') {
    const [notebookId, ...questionParts] = args;
    const question = questionParts.join(' ').trim();

    if (!notebookId || !question) {
      throw new Error('Usage: notebooklm-api.mjs ask <notebook-id> <question>');
    }

    if (prefersCdp()) {
      const response = await askNotebookViaCdp(notebookId, question);
      writeJson({
        ok: true,
        answer: response.text || '',
        references: [],
        conversationId: response.threadId,
      });
    } else {
      await withClient(async (client) => {
        const detail = await withTimeout(
          client.getNotebookDetail(notebookId),
          Number(process.env.CODEX_TUTOR_DETAIL_TIMEOUT_MS || 90000),
          'NotebookLM detail',
        );
        const sourceIds = detail.sources.map((source) => source.id);

        if (sourceIds.length === 0) {
          throw new Error('The selected notebook has no sources.');
        }

        const response = await withTimeout(
          client.sendChat(notebookId, question, sourceIds),
          Number(process.env.CODEX_TUTOR_ASK_TIMEOUT_MS || 180000),
          'NotebookLM ask',
        );
        writeJson({
          ok: true,
          answer: response.text,
          references: [],
          conversationId: response.threadId,
        });
      });
    }
  } else {
    throw new Error(`Unknown command: ${command || ''}`);
  }
} catch (error) {
  writeJson({
    ok: false,
    error: error?.message || String(error),
    name: error?.name || 'Error',
    rpcId: error?.rpcId,
    code: error?.code,
  });
  process.exit(1);
}
