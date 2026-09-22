import { useMemo } from "react";
import { renderMarkdown } from "../markdown";

interface MarkdownPreviewProps {
  value: string;
  emptyText?: string;
}

export function MarkdownPreview({
  value,
  emptyText = "还没有题目描述",
}: MarkdownPreviewProps) {
  const html = useMemo(() => renderMarkdown(value), [value]);
  if (!value.trim()) {
    return <p className="empty-copy">{emptyText}</p>;
  }
  return (
    <div
      className="markdown-body"
      // The source is HTML-escaped before Markdown parsing and sanitized after.
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
