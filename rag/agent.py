#!/usr/bin/env python3
r"""SanVi Docs Assistant, step 2: a LangGraph agent that answers questions about SanVi from its docs.

Graph:  retrieve -> generate -> check --(not grounded, 1 retry)--> generate
                                     \--(grounded or retries used)--> END
- retrieve: top-k chunks from the Chroma vector database (built by ingest.py)
- generate: the model answers ONLY from the retrieved context and cites the source headers it used
- check:    a guardrail; the answer must cite at least one retrieved source, or honestly say it is not in the docs
All model calls go through the SanVi gateway's OpenAI-compatible API, so per-team keys, budgets,
rate limits and spend logs apply to this agent like any other client.

Usage: SANVI_AGENT_KEY=... python3 rag/agent.py "How do I add a new team?"
"""
import os, pathlib, re, sys, time
from typing import List, TypedDict
import chromadb
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATEWAY = os.environ.get("SANVI_GATEWAY", "http://localhost:4000").rstrip("/")
MODEL = os.environ.get("SANVI_RAG_MODEL", "sanvi-fast")
TOP_K = int(os.environ.get("SANVI_RAG_TOP_K", "4"))
NOT_FOUND = "I can't find that in the SanVi docs."


class State(TypedDict, total=False):
    question: str
    docs: List[dict]
    answer: str
    attempts: int
    grounded: bool


_col = None
def collection():
    global _col
    if _col is None:
        _col = chromadb.PersistentClient(path=str(ROOT / "rag" / ".chroma")).get_collection("sanvi_docs")
    return _col


def llm():
    key = os.environ.get("SANVI_AGENT_KEY")
    if not key:
        sys.exit("set SANVI_AGENT_KEY (read -s SANVI_AGENT_KEY && export SANVI_AGENT_KEY)")
    return ChatOpenAI(model=MODEL, base_url=f"{GATEWAY}/v1", api_key=key, temperature=0, max_tokens=500)


def retrieve(s: State) -> State:
    r = collection().query(query_texts=[s["question"]], n_results=TOP_K)
    docs = [{"source": m["source"], "text": d} for d, m in zip(r["documents"][0], r["metadatas"][0])]
    return {"docs": docs, "attempts": s.get("attempts", 0)}


def generate(s: State) -> State:
    ctx = "\n\n".join(f"[{d['source']}]\n{d['text']}" for d in s["docs"])
    strict = ("\nYour previous answer did not cite a source. Every claim MUST end with a source tag "
              "copied exactly from the context, e.g. [<source header>].") if s.get("attempts") else ""
    prompt = (f"You answer questions about the SanVi platform using ONLY the context below.\n"
              f"Cite the source of each claim in square brackets, copied exactly from the context headers.\n"
              f"If the answer is not in the context, reply exactly: \"{NOT_FOUND}\"{strict}\n\n"
              f"CONTEXT:\n{ctx}\n\nQUESTION: {s['question']}\nANSWER (max 120 words):")
    ans = llm().invoke(prompt).content.strip()
    return {"answer": ans, "attempts": s.get("attempts", 0) + 1}


def check(s: State) -> State:
    sources = {d["source"] for d in s["docs"]}
    cited = set(re.findall(r"\[([^\]]+)\]", s["answer"]))
    return {"grounded": NOT_FOUND in s["answer"] or bool(cited & sources)}


def route(s: State) -> str:
    return END if s["grounded"] or s["attempts"] >= 2 else "generate"


def build():
    g = StateGraph(State)
    g.add_node("retrieve", retrieve); g.add_node("generate", generate); g.add_node("check", check)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "generate"); g.add_edge("generate", "check")
    g.add_conditional_edges("check", route, {"generate": "generate", END: END})
    return g.compile()


def ask(q: str) -> State:
    return build().invoke({"question": q})


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How do I add a new team to SanVi?"
    t0 = time.time(); out = ask(q)
    print(out["answer"])
    print(f"\n-- grounded: {out['grounded']} | attempts: {out['attempts']} | sources: "
          f"{', '.join(d['source'] for d in out['docs'])} | {time.time() - t0:.1f}s")
