"use client";

type ResourceNode = {
  id: string;
  name: string;
  path: string;
  kind: "dir" | "file";
  depth: number;
  excluded: boolean;
  selected: boolean;
  children: ResourceNode[];
  hasMore: boolean;
};

export function CodeResourceTree({
  nodes,
  busy,
  onToggle,
  onExpand,
  onOpenFile,
  readOnly = false,
}: {
  nodes: ResourceNode[];
  busy: boolean;
  onToggle?: (path: string, checked: boolean) => void;
  onExpand: (path: string) => void;
  onOpenFile?: (path: string, name: string) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="code-tree" data-testid="resource-tree">
      {nodes.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          busy={busy}
          readOnly={readOnly}
          onToggle={onToggle}
          onExpand={onExpand}
          onOpenFile={onOpenFile}
        />
      ))}
      {nodes.length === 0 && (
        <p className="muted" style={{ padding: 16 }}>
          트리를 불러오는 중이거나 경로가 없습니다.
        </p>
      )}
    </div>
  );
}

function TreeNode({
  node,
  busy,
  readOnly,
  onToggle,
  onExpand,
  onOpenFile,
}: {
  node: ResourceNode;
  busy: boolean;
  readOnly: boolean;
  onToggle?: (path: string, checked: boolean) => void;
  onExpand: (path: string) => void;
  onOpenFile?: (path: string, name: string) => void;
}) {
  const checked = !node.excluded && node.selected;
  const ext = node.kind === "file" ? extOf(node.name) : "";
  return (
    <div className="code-tree-node">
      <div className="code-tree-row" style={{ paddingLeft: 12 + (node.depth - 1) * 16 }}>
        <span className="code-tree-guide" aria-hidden />
        {!readOnly && (
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => onToggle?.(node.path, e.target.checked)}
            aria-label={`${node.path} 포함`}
          />
        )}
        <span className={`file-icon ${node.kind === "dir" ? "is-dir" : `is-file is-${ext || "txt"}`}`}>
          {node.kind === "dir" ? (
            <FolderIcon />
          ) : (
            <FileIcon label={ext || "file"} />
          )}
        </span>
        <button
          type="button"
          className={`code-tree-name ${node.kind === "file" ? "is-file-name" : "is-dir-name"}`}
          onClick={() => {
            if (node.kind === "file") onOpenFile?.(node.path, node.name);
            else if (node.hasMore || node.children.length === 0) onExpand(node.path);
          }}
        >
          {node.name}
        </button>
        {node.kind === "file" && <span className="code-ext">{ext || "file"}</span>}
        {node.kind === "dir" && (node.hasMore || node.children.length === 0) && (
          <button
            type="button"
            className="ghost-btn tree-expand"
            disabled={busy}
            onClick={() => onExpand(node.path)}
          >
            펼치기
          </button>
        )}
      </div>
      {node.children?.length > 0 && (
        <div className="code-tree-children">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              busy={busy}
              readOnly={readOnly}
              onToggle={onToggle}
              onExpand={onExpand}
              onOpenFile={onOpenFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function extOf(name: string) {
  const i = name.lastIndexOf(".");
  if (i < 0) return "";
  return name.slice(i + 1).toLowerCase();
}

function FolderIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M2 4.5A1.5 1.5 0 0 1 3.5 3H6l1.2 1.2H12.5A1.5 1.5 0 0 1 14 5.7v5.8A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.5v-7Z"
        fill="#F6C177"
        stroke="#D4A017"
        strokeWidth="0.8"
      />
    </svg>
  );
}

function FileIcon({ label }: { label: string }) {
  const color =
    label === "ts" || label === "tsx"
      ? "#3178C6"
      : label === "js" || label === "jsx"
        ? "#F0DB4F"
        : label === "java"
          ? "#E76F00"
          : label === "py"
            ? "#3572A5"
            : label === "json"
              ? "#CBCB41"
              : label === "yml" || label === "yaml"
                ? "#CB171E"
                : label === "md"
                  ? "#083FA1"
                  : label === "css" || label === "scss"
                    ? "#563D7C"
                    : "#6F717B";
  return (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden>
      <path
        d="M3 1h5l4 4v9.5A1.5 1.5 0 0 1 10.5 16h-7A1.5 1.5 0 0 1 2 14.5v-12A1.5 1.5 0 0 1 3.5 1H3Z"
        fill="#fff"
        stroke={color}
        strokeWidth="1"
      />
      <path d="M8 1v3.5A.5.5 0 0 0 8.5 5H12" stroke={color} strokeWidth="1" />
      <rect x="4" y="8" width="6" height="1.2" rx="0.4" fill={color} opacity="0.75" />
      <rect x="4" y="10.5" width="4.5" height="1.2" rx="0.4" fill={color} opacity="0.45" />
    </svg>
  );
}

export function mapNodes(
  nodes: ResourceNode[],
  path: string,
  checked: boolean,
): ResourceNode[] {
  return nodes.map((n) => {
    if (n.path === path || n.path.startsWith(`${path}/`)) {
      return {
        ...n,
        excluded: !checked,
        selected: checked,
        children: mapNodes(n.children ?? [], path, checked),
      };
    }
    return { ...n, children: mapNodes(n.children ?? [], path, checked) };
  });
}

export function attachChildren(
  nodes: ResourceNode[],
  path: string,
  children: ResourceNode[],
): ResourceNode[] {
  return nodes.map((n) => {
    if (n.path === path) return { ...n, children, hasMore: false };
    return { ...n, children: attachChildren(n.children ?? [], path, children) };
  });
}

export type { ResourceNode };
