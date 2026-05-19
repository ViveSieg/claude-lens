const proxy =
  process.env.CODEX_TUTOR_PROXY ||
  process.env.HTTPS_PROXY ||
  process.env.HTTP_PROXY ||
  process.env.ALL_PROXY;

if (proxy) {
  try {
    const { ProxyAgent, setGlobalDispatcher } = require("undici");
    setGlobalDispatcher(
      new ProxyAgent({
        uri: proxy,
        requestTls: {
          secureProtocol: "TLSv1_2_method",
          ALPNProtocols: ["http/1.1"],
        },
      })
    );
  } catch (error) {
    console.error(`[codex-tutor] failed to configure proxy ${proxy}: ${error.message}`);
  }
}
