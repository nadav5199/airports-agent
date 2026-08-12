import { Fragment } from "react";

/** Render `**bold**` spans within a line of plain text. */
function renderInline(text: string, keyPrefix: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={`${keyPrefix}-${i}`}>{part}</Fragment>;
  });
}

/**
 * Minimal markdown-ish renderer for assistant replies: bold spans and
 * `-`/numbered list lines. Intentionally not a full markdown parser --
 * covers the formatting an LLM reply plausibly emits, nothing more.
 */
export function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let listItems: string[] | null = null;
  let listKey = 0;

  function flushList() {
    if (listItems) {
      blocks.push(
        <ul key={`list-${listKey++}`} className="chat-list">
          {listItems.map((item, i) => (
            <li key={i}>{renderInline(item, `li-${listKey}-${i}`)}</li>
          ))}
        </ul>
      );
      listItems = null;
    }
  }

  lines.forEach((line, idx) => {
    const bulletMatch = /^\s*[-*]\s+(.*)/.exec(line);
    const numberedMatch = /^\s*\d+[.)]\s+(.*)/.exec(line);
    const itemText = bulletMatch?.[1] ?? numberedMatch?.[1];

    if (itemText !== undefined) {
      if (!listItems) listItems = [];
      listItems.push(itemText);
      return;
    }

    flushList();
    if (line.trim() === "") {
      blocks.push(<br key={`br-${idx}`} />);
    } else {
      blocks.push(<span key={`line-${idx}`}>{renderInline(line, `l-${idx}`)}</span>);
      blocks.push(<br key={`br-${idx}`} />);
    }
  });
  flushList();

  return blocks;
}
