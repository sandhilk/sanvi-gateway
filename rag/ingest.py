#!/usr/bin/env python3
"""SanVi Docs Assistant, step 1: build the knowledge base.

Splits SanVi's own documentation (README sections + script docstrings) into chunks and stores
them in a local Chroma vector database (rag/.chroma) with sentence embeddings (all-MiniLM-L6-v2,
run locally, so documents never leave the machine to be embedded).
"""
import ast, pathlib, re, chromadb

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "rag" / ".chroma"


def readme_chunks():
    text = (ROOT / "README.md").read_text()
    parts = re.split(r"(?m)^(#{1,3} .+)$", text)
    title, out = "README intro", []
    for p in parts:
        if re.match(r"^#{1,3} ", p):
            title = p.lstrip("# ").strip()
            continue
        body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", p).strip()
        # split long sections into ~1200-char windows on paragraph breaks
        buf = ""
        for para in body.split("\n\n"):
            if len(buf) + len(para) > 1200 and buf:
                out.append((f"README > {title}", buf.strip())); buf = ""
            buf += para + "\n\n"
        if buf.strip():
            out.append((f"README > {title}", buf.strip()))
    return out


def script_chunks():
    out = []
    for f in sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "agent").glob("*.py")):
        try:
            doc = ast.get_docstring(ast.parse(f.read_text()))
        except SyntaxError:
            doc = None
        if doc:
            out.append((f"{f.relative_to(ROOT)}", doc))
    for f in sorted((ROOT / "scripts").glob("*.sh")) + sorted((ROOT / "agent").glob("*.sh")):
        head = [l[1:].strip() for l in f.read_text().splitlines()[1:25] if l.startswith("#")]
        if len(" ".join(head)) > 60:
            out.append((f"{f.relative_to(ROOT)}", "\n".join(head)))
    return out


def main():
    chunks = readme_chunks() + script_chunks()
    client = chromadb.PersistentClient(path=str(DB))
    try:
        client.delete_collection("sanvi_docs")
    except Exception:
        pass
    col = client.create_collection("sanvi_docs", metadata={"hnsw:space": "cosine"})
    col.add(ids=[f"c{i}" for i in range(len(chunks))],
            documents=[f"{src}\n{txt}" for src, txt in chunks],
            metadatas=[{"source": src} for src, _ in chunks])
    print(f"indexed {len(chunks)} chunks from {len({s for s, _ in chunks})} sources into {DB}")


if __name__ == "__main__":
    main()
