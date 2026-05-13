#!/usr/bin/env python3
"""
knowledge_base.py — MOYU Knowledge Base (V2.0.3)

Lets users store reusable knowledge as markdown files, then retrieve them
by keyword on demand. Think of it as "static memory" — workflows, rules,
notes, docs that don't change often but need to be found when relevant.

Usage:
    python3 knowledge_base.py index          # Rebuild keyword index
    python3 knowledge_base.py search <q>     # Search by keyword
    python3 knowledge_base.py list           # List all knowledge files
    python3 knowledge_base.py read <file>    # Read a specific file content

Design:
    - Users put .md files in knowledge/ directory (alongside moyu_toolkit/)
    - Files can have YAML frontmatter with `triggers: [keyword1, keyword2]`
    - Index is built from frontmatter triggers + content keyword extraction
    - Pure Python, no API key required, no new dependencies
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# ── Paths ──
TOOLKIT_DIR = Path(__file__).parent.resolve()
DEFAULT_KNOWLEDGE_DIR = TOOLKIT_DIR.parent / "workflow-recipes"
INDEX_FILE = Path(os.environ.get("MOYU_STORAGE", str(TOOLKIT_DIR / "memory_data"))) / "kb_index.json"

# Rebuild this when knowledge/ files change
_INDEX_VERSION = "1.0"


def _knowledge_dir() -> Path:
    """Get the knowledge directory path."""
    return Path(os.environ.get("MOYU_KNOWLEDGE_DIR", str(DEFAULT_KNOWLEDGE_DIR)))


def _ensure_knowledge_dir():
    """Create knowledge/ if it doesn't exist."""
    kdir = _knowledge_dir()
    kdir.mkdir(parents=True, exist_ok=True)
    return kdir


def _scan_md_files() -> List[Path]:
    """List all .md files in the knowledge directory."""
    kdir = _knowledge_dir()
    if not kdir.exists():
        return []
    return sorted(kdir.glob("*.md"))


# ── Frontmatter parser ──
_FM_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)


def _parse_frontmatter(content: str) -> dict:
    """Simple YAML-ish frontmatter parser (triggers, tags, title only)."""
    m = _FM_RE.match(content)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            # Parse list: [item1, item2]
            if val.startswith("[") and val.endswith("]"):
                items = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
                fm[key] = items
            else:
                fm[key] = val.strip('"').strip("'")
    return fm


def _strip_frontmatter(content: str) -> str:
    """Remove frontmatter, return pure markdown body."""
    return _FM_RE.sub("", content, count=1).strip()


def _extract_content_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from markdown body for search indexing."""
    text = _strip_frontmatter(text)
    keywords = set()

    # Headings — most important
    for m in re.finditer(r'^#{1,4}\s+(.+)$', text, re.MULTILINE):
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', m.group(1))
        for w in words:
            if len(w) >= 2:
                keywords.add(w.lower())

    # Bold/strong text
    for m in re.finditer(r'\*\*(.+?)\*\*', text):
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', m.group(1))
        for w in words:
            if len(w) >= 2:
                keywords.add(w.lower())

    # List items (often contain key terms)
    for m in re.finditer(r'^[*-]\s+(.+)$', text, re.MULTILINE):
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', m.group(1))
        for w in words[:3]:  # First 3 significant words per list item
            if len(w) >= 2:
                keywords.add(w.lower())

    # Code block labels
    for m in re.finditer(r'```(\w+)', text):
        if m.group(1).lower() not in {'text', 'bash', 'sh', 'shell', 'python', 'yaml', 'json', 'md', 'markdown'}:
            keywords.add(m.group(1).lower())

    return list(keywords)


def _index_all_files() -> Dict:
    """Build/rebuild the keyword index from all knowledge files."""
    files = _scan_md_files()
    if not files:
        return {"version": _INDEX_VERSION, "files": [], "updated": datetime.now().isoformat()}

    indexed = []
    for fpath in files:
        try:
            content = fpath.read_text(encoding='utf-8')
        except Exception:
            continue

        frontmatter = _parse_frontmatter(content)
        triggers = frontmatter.get("triggers", []) or []
        title = frontmatter.get("title", fpath.stem)
        tags = frontmatter.get("tags", []) or []

        # Combine triggers + extracted content keywords
        keywords = set()
        for t in triggers:
            keywords.add(t.lower())
        for t in tags:
            keywords.add(t.lower())

        # Content keywords
        content_kw = _extract_content_keywords(content)
        for kw in content_kw:
            keywords.add(kw)

        indexed.append({
            "path": str(fpath.relative_to(_knowledge_dir().parent)),
            "filename": fpath.name,
            "title": title,
            "triggers": list(keywords),
            "size": len(content),
            "updated": datetime.fromtimestamp(fpath.stat().st_mtime).isoformat(),
        })

    index = {
        "version": _INDEX_VERSION,
        "files": indexed,
        "total": len(indexed),
        "updated": datetime.now().isoformat(),
    }
    return index


def index(force: bool = False):
    """Build keyword index and save to memory_data/."""
    idx = _index_all_files()
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    return idx


def _load_index() -> Dict:
    """Load saved index, or build if missing."""
    if not INDEX_FILE.exists():
        return _index_all_files()
    try:
        with open(INDEX_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return _index_all_files()


def search(query: str, top_k: int = 3) -> List[Dict]:
    """Search knowledge files by keyword. Returns matching files with relevance info.

    Matching strategy:
    1. Exact trigger match (highest priority)
    2. Trigger contains query word (partial match)
    3. Filename contains query word
    """
    if not query:
        return []

    idx = _load_index()
    q_words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', query.lower()))
    if not q_words:
        return []

    scored = []
    for f in idx.get("files", []):
        score = 0
        triggers = [t.lower() for t in f["triggers"]]
        filename_lower = f["filename"].lower().replace(".md", "")

        for qw in q_words:
            # Exact match in triggers
            if qw in triggers:
                score += 10
            # Partial match — trigger contains query word
            for t in triggers:
                if qw in t or t in qw:
                    score += 5
                    break
            # Filename match
            if qw in filename_lower:
                score += 3

        if score > 0:
            scored.append({
                "path": f["path"],
                "filename": f["filename"],
                "title": f["title"],
                "score": score,
                "triggers": f["triggers"][:8],  # Show top triggers
            })

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def read(filename: str) -> Optional[str]:
    """Read a knowledge file by filename (returns markdown body, no frontmatter)."""
    kdir = _knowledge_dir()
    fpath = kdir / filename
    if not fpath.exists():
        # Try matching by partial name
        matches = list(kdir.glob(f"*{filename}*"))
        if not matches:
            return None
        fpath = matches[0]
    try:
        content = fpath.read_text(encoding='utf-8')
        return _strip_frontmatter(content)
    except Exception:
        return None


def list_files() -> List[Dict]:
    """List all knowledge files with their triggers."""
    idx = _load_index()
    return idx.get("files", [])


def record(title: str, triggers: list, body: str) -> str:
    """Record a completed workflow as a knowledge file.
    
    Called after successfully completing any multi-step task,
    preserving only the correct path (no false starts or errors).
    
    The AI provides:
    - title: short name (e.g. "GitHub Release 发布流程")
    - triggers: keywords that will match future queries (e.g. ["发布", "release", "tag"])
    - body: the markdown content with only the correct steps, commands, and notes
    
    Returns the filename created.
    """
    kdir = _ensure_knowledge_dir()
    # Sanitize title to filename
    safe_name = re.sub(r'[^\u4e00-\u9fff\w\-]', '_', title)[:30].strip('_').lower() or "workflow"
    fname = f"{safe_name}.md"
    fpath = kdir / fname
    
    # Avoid overwriting: add counter suffix
    counter = 1
    while fpath.exists():
        fname = f"{safe_name}_{counter:02d}.md"
        fpath = kdir / fname
        counter += 1
    
    content = f"---\ntitle: {title}\ntriggers: {json.dumps(triggers, ensure_ascii=False)}\n---\n\n{body.strip()}\n"
    fpath.write_text(content, encoding='utf-8')
    
    # Rebuild index
    try:
        index()
    except Exception:
        pass
    
    return fname


def stats():
    """Print human-readable index stats."""
    idx = _load_index()
    files = idx.get("files", [])
    print(f"\n📚 MOYU Knowledge Base")
    print("=" * 50)
    print(f"  Files:       {idx.get('total', len(files))}")
    print(f"  Index dir:   {INDEX_FILE}")
    print(f"  Knowlege:    {_knowledge_dir()}")
    print(f"  Last index:  {idx.get('updated', 'never')[:19]}")
    print()
    for f in files:
        triggers = f.get("triggers", [])[:5]
        trigger_str = ", ".join(triggers[:5])
        print(f"  📄 {f['filename']}")
        if trigger_str:
            print(f"     ↳ triggers: {trigger_str}")
    print()


def demo() -> dict:
    return {
        "capability": 16,
        "title": "Knowledge Base (V2.0.3)",
        "output": """\
📚 V2.0.3 FEATURE — Knowledge Base

  Store your workflows, rules, and docs as .md files in the
  knowledge/ directory. MOYU indexes their headings and keywords,
  then retrieves them on demand.

  Commands:
    moyu kb index          → Rebuild keyword index
    moyu kb search <q>     → Find relevant knowledge files
    moyu kb list           → Show all files with triggers
    moyu kb read <file>    → Read a file's content

  Example:
    echo '---
    triggers: [deploy, nginx, server]
    ---

    # Deployment Checklist
    1. Copy files to /var/www/
    2. Restart nginx: sudo systemctl restart nginx' > knowledge/deploy.md
    moyu kb search deploy  → Finds deploy.md""",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]

    if cmd == "index":
        idx = index()
        print(f"Indexed {idx['total']} knowledge files")
    elif cmd == "search":
        query = " ".join(sys.argv[2:])
        if not query:
            print("Usage: python3 knowledge_base.py search <query>")
            sys.exit(1)
        results = search(query)
        if results:
            for r in results:
                print(f"  📄 {r['filename']} (score: {r['score']})")
                print(f"     {r['path']}")
                if r.get("triggers"):
                    print(f"     triggers: {', '.join(r['triggers'][:5])}")
                print()
        else:
            print(f"No results for '{query}'")
    elif cmd == "list":
        files = list_files()
        if files:
            print(f"\n{'Filename':30s} {'Triggers'}")
            print("-" * 60)
            for f in files:
                triggers = ", ".join(f.get("triggers", [])[:5])
                print(f"{f['filename']:30s} {triggers}")
            print()
        else:
            print("No knowledge files found. Create .md files in the knowledge/ directory.")
    elif cmd == "read":
        fname = " ".join(sys.argv[2:])
        content = read(fname)
        if content:
            print(content)
        else:
            print(f"File not found: {fname}")
    else:
        stats()
