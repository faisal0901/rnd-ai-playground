import { Check, Copy } from "lucide-react";
import { Children, isValidElement, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function CodeBlock({ language, code }: { language?: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (await copyText(code)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };
  return (
    <div className="code">
      <div className="code-head">
        <span>{language ?? "kode"}</span>
        <button type="button" onClick={copy}>
          {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Tersalin" : "Salin"}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** Model output is untrusted: react-markdown builds React elements and never injects raw HTML. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          pre: ({ children }) => {
            const code = Children.toArray(children)[0];
            const props = (isValidElement(code) ? code.props : {}) as { className?: string; children?: ReactNode };
            const language = /language-(\S+)/.exec(props.className ?? "")?.[1];
            return <CodeBlock language={language} code={String(props.children ?? "").replace(/\n$/, "")} />;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
