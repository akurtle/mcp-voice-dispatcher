import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  buildNotionCreatePageBody,
  buildRawEmail,
  fetchJsonWithRetry,
  logServerEvent,
} from "./lib.js";

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

async function createNotionPage({ title, contentMarkdown, databaseId }) {
  const notionToken = requireEnv("NOTION_API_TOKEN");
  const resolvedDatabaseId = databaseId || process.env.NOTION_DATABASE_ID;
  if (!resolvedDatabaseId) {
    throw new Error("NOTION_DATABASE_ID is required when databaseId is not provided.");
  }
  const titleProperty = process.env.NOTION_TITLE_PROPERTY || "Name";
  const body = buildNotionCreatePageBody({
    title,
    contentMarkdown,
    databaseId: resolvedDatabaseId,
    titleProperty,
  });
  const payload = await fetchJsonWithRetry(
    "https://api.notion.com/v1/pages",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${notionToken}`,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
    {
      backend: "notion",
      action: "create_page",
    },
  );
  return {
    id: payload.id,
    url: payload.url ?? null,
  };
}

async function sendGmailMessage({ to, cc, subject, bodyText }) {
  const accessToken = requireEnv("GMAIL_ACCESS_TOKEN");
  const from = requireEnv("GMAIL_FROM_EMAIL");
  const userId = process.env.GMAIL_USER_ID || "me";
  const raw = buildRawEmail({ from, to, cc, subject, bodyText });
  const payload = await fetchJsonWithRetry(
    `https://gmail.googleapis.com/gmail/v1/users/${encodeURIComponent(userId)}/messages/send`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ raw }),
    },
    {
      backend: "gmail",
      action: "send_message",
    },
  );
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
  logServerEvent("mcp_server_ready", { name: "mcp-voice-dispatcher-tools" });
  await server.connect(transport);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
