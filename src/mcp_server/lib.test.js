import assert from "node:assert/strict";

import { buildNotionCreatePageBody, buildRawEmail, fetchJsonWithRetry } from "./lib.js";

async function run() {
  const encoded = buildRawEmail({
    from: "sender@example.com",
    to: ["alpha@example.com"],
    cc: ["beta@example.com"],
    subject: "Launch update",
    bodyText: "Deployment moved to Friday.",
  });
  const decoded = Buffer.from(encoded, "base64url").toString("utf8");
  assert.match(decoded, /From: sender@example.com/);
  assert.match(decoded, /To: alpha@example.com/);
  assert.match(decoded, /Cc: beta@example.com/);
  assert.match(decoded, /Subject: Launch update/);
  assert.match(decoded, /Deployment moved to Friday\./);

  const body = buildNotionCreatePageBody({
    title: "Sprint Retro",
    contentMarkdown: "- wins\n- blockers",
    databaseId: "db_123",
    titleProperty: "Name",
  });
  assert.equal(body.parent.database_id, "db_123");
  assert.equal(body.properties.Name.title[0].text.content, "Sprint Retro");
  assert.equal(body.children[0].paragraph.rich_text[0].text.content, "- wins\n- blockers");

  let attempts = 0;
  const payload = await fetchJsonWithRetry(
    "https://example.test",
    { method: "POST" },
    {
      backend: "gmail",
      action: "send_message",
      retryDelayMs: 1,
      fetchImpl: async () => {
        attempts += 1;
        if (attempts === 1) {
          return {
            ok: false,
            status: 503,
            text: async () => JSON.stringify({ error: "temporary" }),
          };
        }
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ id: "msg_123" }),
        };
      },
    },
  );
  assert.equal(attempts, 2);
  assert.equal(payload.id, "msg_123");

  console.log("mcp_server helper tests passed");
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
