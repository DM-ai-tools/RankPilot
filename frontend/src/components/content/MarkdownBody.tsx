import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const mdClass =
  "text-[12px] leading-relaxed text-rp-tmid [&_h1]:mb-2 [&_h1]:mt-0 [&_h1]:text-[15px] [&_h1]:font-bold [&_h1]:text-navy " +
  "[&_h2]:mb-1.5 [&_h2]:mt-3 [&_h2]:text-[13px] [&_h2]:font-bold [&_h2]:text-navy [&_h3]:mb-1 [&_h3]:mt-2 [&_h3]:text-[12px] [&_h3]:font-semibold [&_h3]:text-navy " +
  "[&_p]:mb-2 [&_p:last-child]:mb-0 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:mb-0.5 " +
  "[&_strong]:font-semibold [&_strong]:text-navy [&_a]:font-medium [&_a]:text-[#72C219] [&_a]:hover:underline " +
  "[&_code]:rounded [&_code]:bg-rp-light [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px] " +
  "[&_blockquote]:border-l-2 [&_blockquote]:border-rp-border [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-rp-tlight";

export function MarkdownBody({ markdown, className = "" }: { markdown: string; className?: string }) {
  if (!markdown.trim()) return null;
  return (
    <div className={`${mdClass} ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={(u) => u}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
