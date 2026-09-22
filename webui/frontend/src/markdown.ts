import DOMPurify from "dompurify";
import { marked } from "marked";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export function renderMarkdown(value: string): string {
  const rendered = marked.parse(escapeHtml(value), {
    async: false,
    breaks: true,
    gfm: true,
  });
  return DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
  });
}
