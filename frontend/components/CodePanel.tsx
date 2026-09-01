"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Chip, Panel, TimeAgo } from "@/components/ui";

type FileEntry = { path: string; name: string; is_dir: boolean; size: number };
type FileContent = { path: string; content: string; size: number; truncated: boolean };
type Commit = { sha: string; subject: string; author: string; when: string };

export function CodePanel({ projectId, refreshKey }: { projectId: string; refreshKey?: number }) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<FileContent | null>(null);
  const [diff, setDiff] = useState<string | null>(null);
  const [tab, setTab] = useState<"files" | "history">("files");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<FileEntry[]>(`/projects/${projectId}/files`).then(setFiles).catch(() => setFiles([]));
    api<Commit[]>(`/projects/${projectId}/git/log`).then(setCommits).catch(() => setCommits([]));
  }, [projectId, refreshKey]);

  async function openFile(path: string) {
    setSelected(path);
    setDiff(null);
    setBusy(true);
    try {
      setContent(await api<FileContent>(`/projects/${projectId}/files/content?path=${encodeURIComponent(path)}`));
    } catch {
      setContent(null);
    } finally {
      setBusy(false);
    }
  }

  async function openDiff(sha: string) {
    setSelected(sha.slice(0, 10));
    setContent(null);
    setBusy(true);
    try {
      const res = await api<{ diff: string }>(`/projects/${projectId}/git/diff?sha=${sha}`);
      setDiff(res.diff);
    } catch {
      setDiff(null);
    } finally {
      setBusy(false);
    }
  }

  const fileList = useMemo(() => files.filter((f) => !f.is_dir), [files]);

  return (
    <Panel
      title="Code"
      note={`${fileList.length} file${fileList.length === 1 ? "" : "s"} · ${commits.length} commit${
        commits.length === 1 ? "" : "s"
      }`}
      action={
        <div className="flex gap-1">
          {(["files", "history"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-2xs px-2 py-0.5 rounded-md border transition-colors ${
                tab === t
                  ? "border-accent-emeraldBright/50 text-accent-emeraldBright"
                  : "border-base-border text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,15rem)_1fr] min-h-[22rem]">
        <div className="border-b md:border-b-0 md:border-r border-base-border/70 max-h-[30rem] overflow-y-auto">
          {tab === "files" ? (
            fileList.length === 0 ? (
              <p className="px-4 py-6 text-2xs text-neutral-600">
                Nothing written yet. Files appear here as the Coder works.
              </p>
            ) : (
              fileList.map((f) => (
                <button
                  key={f.path}
                  onClick={() => openFile(f.path)}
                  className={`w-full text-left px-3 py-1.5 flex items-baseline gap-2 transition-colors ${
                    selected === f.path
                      ? "bg-accent-emerald/15 text-accent-emeraldBright"
                      : "text-neutral-400 hover:bg-base-graphite hover:text-neutral-200"
                  }`}
                >
                  <span className="text-2xs font-mono truncate flex-1">{f.path}</span>
                  <span className="text-2xs text-neutral-700 num shrink-0">{formatSize(f.size)}</span>
                </button>
              ))
            )
          ) : commits.length === 0 ? (
            <p className="px-4 py-6 text-2xs text-neutral-600">No commits yet.</p>
          ) : (
            commits.map((c) => (
              <button
                key={c.sha}
                onClick={() => openDiff(c.sha)}
                className={`w-full text-left px-3 py-2 transition-colors ${
                  selected === c.sha.slice(0, 10)
                    ? "bg-accent-emerald/15"
                    : "hover:bg-base-graphite"
                }`}
              >
                <div className="text-2xs text-neutral-300 leading-snug line-clamp-2">{c.subject}</div>
                <div className="text-2xs text-neutral-700 font-mono mt-0.5">
                  {c.sha.slice(0, 7)} · <TimeAgo iso={c.when} />
                </div>
              </button>
            ))
          )}
        </div>

        <div className="min-w-0 max-h-[30rem] overflow-auto bg-base-black/60">
          {busy && <div className="px-4 py-3 text-2xs text-neutral-600">Loading…</div>}
          {!busy && !content && !diff && (
            <div className="px-4 py-8 text-2xs text-neutral-600">
              Select a {tab === "files" ? "file" : "commit"} to view it.
            </div>
          )}
          {!busy && content && (
            <>
              <div className="sticky top-0 flex items-center gap-2 px-3 py-1.5 bg-base-near border-b border-base-border">
                <span className="text-2xs font-mono text-neutral-300 truncate">{content.path}</span>
                {content.truncated && <Chip label="truncated" tone="text-status-warning border-status-warning/40" />}
              </div>
              <pre className="px-3 py-2 text-2xs font-mono leading-relaxed text-neutral-300 whitespace-pre">
                {content.content}
              </pre>
            </>
          )}
          {!busy && diff !== null && <DiffView diff={diff} />}
        </div>
      </div>
    </Panel>
  );
}

/** Colours a unified diff by line role, so what changed reads at a glance instead of as a
 *  wall of monospace. */
function DiffView({ diff }: { diff: string }) {
  if (!diff.trim()) {
    return <div className="px-4 py-8 text-2xs text-neutral-600">No changes in this commit.</div>;
  }
  return (
    <pre className="text-2xs font-mono leading-relaxed whitespace-pre">
      {diff.split("\n").map((line, i) => {
        const tone = line.startsWith("+++") || line.startsWith("---")
          ? "text-neutral-500"
          : line.startsWith("+")
            ? "text-status-success bg-status-success/10"
            : line.startsWith("-")
              ? "text-status-critical bg-status-critical/10"
              : line.startsWith("@@")
                ? "text-accent-irisBright"
                : line.startsWith("commit ") || line.startsWith("Author:") || line.startsWith("Date:")
                  ? "text-neutral-500"
                  : "text-neutral-400";
        return (
          <div key={i} className={`px-3 ${tone}`}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}b`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}k`;
  return `${(bytes / 1024 / 1024).toFixed(1)}M`;
}
