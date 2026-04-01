import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({
  name: "mcp-voice-dispatcher-tools",
  version: "0.1.0",
});

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required for this tool call.`);
  }
  return value;
}

function chunkText(text, limit = 1800) {
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

function notionParagraph(text) {
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

async function createNotionPage({ title, contentMarkdown, databaseId }) {
  const notionToken = requireEnv("NOTION_API_TOKEN");
  const resolvedDatabaseId = databaseId || process.env.NOTION_DATABASE_ID;
  if (!resolvedDatabaseId) {
    throw new Error("NOTION_DATABASE_ID is required when databaseId is not provided.");
  }
  const titleProperty = process.env.NOTION_TITLE_PROPERTY || "Name";
  const body = {
    parent: { database_id: resolvedDatabaseId },
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
  const response = await fetch("https://api.notion.com/v1/pages", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${notionToken}`,
      "Notion-Version": "2022-06-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Notion API ${response.status}: ${JSON.stringify(payload)}`);
  }
  return {
    id: payload.id,
    url: payload.url ?? null,
  };
}

function buildRawEmail({ from, to, cc, subject, bodyText }) {
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

async function sendGmailMessage({ to, cc, subject, bodyText }) {
  const accessToken = requireEnv("GMAIL_ACCESS_TOKEN");
  const from = requireEnv("GMAIL_FROM_EMAIL");
  const userId = process.env.GMAIL_USER_ID || "me";
  const raw = buildRawEmail({ from, to, cc, subject, bodyText });
  const response = await fetch(
    `https://gmail.googleapis.com/gmail/v1/users/${encodeURIComponent(userId)}/messages/send`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ raw }),
    },
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Gmail API ${response.status}: ${JSON.stringify(payload)}`);
  }
  return {
    id: payload.id,
    threadId: payload.threadId,
    labelIds: payload.labelIds ?? [],
  };
}

server.registerTool(
  "notion_create_page",
  {
    title: "Notion Create Page",
    description: "Create a page in a Notion database using REST APIs.",
    inputSchema: {
      title: z.string().min(1),
      contentMarkdown: z.string().min(1),
      databaseId: z.string().optional(),
    },
  },
  async ({ title, contentMarkdown, databaseId }) => {
    try {
      const result = await createNotionPage({ title, contentMarkdown, databaseId });
      return {
        content: [
          {
            type: "text",
            text: `Created Notion page "${title}" (${result.id}).`,
          },
        ],
        structuredContent: result,
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Notion page creation failed: ${error.message}`,
          },
        ],
        isError: true,
      };
    }
  },
);

server.registerTool(
  "gmail_send_email",
  {
    title: "Gmail Send Email",
    description: "Send a plain-text email through the Gmail REST API.",
    inputSchema: {
      to: z.array(z.string().email()).min(1),
      cc: z.array(z.string().email()).optional(),
      subject: z.string().min(1),
      bodyText: z.string().min(1),
    },
  },
  async ({ to, cc = [], subject, bodyText }) => {
    try {
      const result = await sendGmailMessage({ to, cc, subject, bodyText });
      return {
        content: [
          {
            type: "text",
            text: `Sent Gmail message "${subject}" (${result.id}).`,
          },
        ],
        structuredContent: result,
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Gmail send failed: ${error.message}`,
          },
        ],
        isError: true,
      };
    }
  },
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
