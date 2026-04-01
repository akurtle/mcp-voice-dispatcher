export function logServerEvent(event, fields = {}) {
  console.error(JSON.stringify({ event, ...fields }));
}

export function chunkText(text, limit = 1800) {
  const chunks = [];
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return [];
  }
  for (let offset = 0; offset < normalized.length; offset += limit) {
    chunks.push(normalized.slice(offset, offset + limit));
  }
  return chunks;
}

export function notionParagraph(text) {
  return {
    object: "block",
    type: "paragraph",
    paragraph: {
      rich_text: [
        {
          type: "text",
          text: {
            content: text,
          },
        },
      ],
    },
  };
}

export function buildNotionCreatePageBody({ title, contentMarkdown, databaseId, titleProperty = "Name" }) {
  return {
    parent: { database_id: databaseId },
    properties: {
      [titleProperty]: {
        title: [
          {
            type: "text",
            text: {
              content: title,
            },
          },
        ],
      },
    },
    children: chunkText(contentMarkdown).map(notionParagraph),
  };
}

export function buildRawEmail({ from, to, cc, subject, bodyText }) {
  const headers = [
    `From: ${from}`,
    `To: ${to.join(", ")}`,
    cc.length ? `Cc: ${cc.join(", ")}` : null,
    "MIME-Version: 1.0",
    'Content-Type: text/plain; charset="UTF-8"',
    `Subject: ${subject}`,
    "",
    bodyText,
  ].filter(Boolean);
  return Buffer.from(headers.join("\r\n"), "utf8").toString("base64url");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseBody(rawBody) {
  if (!rawBody) {
    return {};
  }
  try {
    return JSON.parse(rawBody);
  } catch {
    return { raw: rawBody };
  }
}

export async function fetchJsonWithRetry(
  url,
  options,
  {
    backend,
    action,
    retries = 2,
    retryDelayMs = 150,
    retryStatusCodes = [429, 500, 502, 503, 504],
    fetchImpl = globalThis.fetch,
  },
) {
  let lastError = null;
  for (let attempt = 1; attempt <= retries + 1; attempt += 1) {
    const startedAt = Date.now();
    try {
      const response = await fetchImpl(url, options);
      const rawBody = await response.text();
      const payload = parseBody(rawBody);
      const latencyMs = Date.now() - startedAt;
      logServerEvent("backend_http", {
        backend,
        action,
        attempt,
        status_code: response.status,
        latency_ms: latencyMs,
      });
      if (response.ok) {
        return payload;
      }
      const error = new Error(`${backend} API ${response.status}: ${JSON.stringify(payload)}`);
      error.statusCode = response.status;
      lastError = error;
      if (!retryStatusCodes.includes(response.status) || attempt > retries) {
        break;
      }
    } catch (error) {
      lastError = error;
      logServerEvent("backend_http_failure", {
        backend,
        action,
        attempt,
        failure_type: error?.name ?? "Error",
      });
      if (attempt > retries) {
        break;
      }
    }
    await sleep(retryDelayMs * attempt);
  }
  throw lastError ?? new Error(`${backend} API request failed.`);
}
