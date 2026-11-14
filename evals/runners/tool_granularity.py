"""R&D question A: does tool granularity change agent behaviour?

  python -m evals.runners.tool_granularity --model openai/gpt-oss-20b       # 40 tasks x 3 tool sets
  python -m evals.runners.tool_granularity --resume                          # continue after a quota stop

Tool sets (same model, same system prompt agent/prompts/tool_study.md, one forced tool call per task):
  fine        our 13 real MCP tools with their real schemas and descriptions (marketplace + portfolio servers)
  coarse      3 tools: marketplace_read / portfolio_read / marketplace_write, each = operation enum + params object
  rewritten   the 13 fine tools with rewritten descriptions (when to use, when not, argument hints):
              evals/datasets/tool_descriptions_rewritten.json
Tasks: evals/datasets/tool_tasks.json (40 requests with the known correct call).
Metrics: tool-selection accuracy, argument accuracy (all gold arguments right; ids, numbers and booleans exact,
free-text queries by keyword overlap), and tokens per task (prompt + completion, which includes the tool schemas).
Writes evals/results/tool_granularity_results.json and _table.md
"""
import argparse
import asyncio
import json
import os
import re
import statistics
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from agent.config import cfg  # noqa: E402
from agent.nodes.common import prompt  # noqa: E402
from mcp_servers.marketplace import server as market  # noqa: E402
from mcp_servers.portfolio import server as portfolio  # noqa: E402

TASKS = Path("evals/datasets/tool_tasks.json")
REWRITTEN = Path("evals/datasets/tool_descriptions_rewritten.json")
OUT = Path("evals/results")
GROUPS = {
    "marketplace_read": ["search_jobs", "get_job", "get_client_history", "get_connects_balance", "get_price_stats",
                         "list_messages", "list_proposals"],
    "portfolio_read": ["search_evidence", "get_case_study", "list_skills"],
    "marketplace_write": ["create_proposal_draft", "submit_proposal", "send_message"],
}


async def real_tools() -> dict[str, dict]:
    out = {}
    for srv in (market, portfolio):
        async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
            for t in (await s.list_tools()).tools:
                out[t.name] = {"name": t.name, "description": t.description or "", "parameters": t.inputSchema}
    return out


def toolsets(real: dict[str, dict]) -> dict[str, list[dict]]:
    fine = [{"type": "function", "function": t} for t in real.values()]
    rw = json.loads(REWRITTEN.read_text(encoding="utf-8"))
    rewritten = [{"type": "function", "function": {**t, "description": rw.get(t["name"], t["description"])}} for t in real.values()]
    coarse = []
    for group, ops in GROUPS.items():
        sig = "; ".join(f"{op}({', '.join((real[op]['parameters'].get('properties') or {}).keys())})" for op in ops)
        coarse.append({"type": "function", "function": {
            "name": group,
            "description": f"{'Write' if 'write' in group else 'Read'} operations on the {group.split('_')[0]}. "
                           f"Choose one operation and pass its arguments in params. Operations: {sig}.",
            "parameters": {"type": "object", "required": ["operation", "params"], "properties": {
                "operation": {"type": "string", "enum": ops},
                "params": {"type": "object", "description": "Arguments of the chosen operation"}}}}})
    return {"fine": fine, "coarse": coarse, "rewritten": rewritten}


def _words(s) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(s).lower()))


def arg_ok(name: str, gold, got, fuzzy: bool) -> bool:
    if got is None:
        return name == "dry_run" and gold is True          # dry_run defaults to true on every write tool
    if fuzzy:
        g = _words(gold)
        return len(g & _words(got)) / max(len(g), 1) >= 0.5
    if isinstance(gold, bool):
        return str(got).lower() == str(gold).lower()
    if isinstance(gold, (int, float)):
        try:
            return float(got) == float(gold)
        except (TypeError, ValueError):
            return False
    if isinstance(gold, list):
        return isinstance(got, list) and {str(x).lower() for x in gold} <= {str(x).lower() for x in got}
    return str(got).strip().lower() == str(gold).strip().lower()


def score(task: dict, call: dict | None, coarse: bool) -> dict:
    if not call:
        return {"tool_ok": False, "args_ok": False, "picked": None}
    name, args = call["name"], call.get("args") or {}
    if coarse:
        op = args.get("operation")
        tool_ok = op == task["tool"] and task["tool"] in GROUPS.get(name, [])
        args = args.get("params") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        picked = f"{name}.{op}"
    else:
        tool_ok, picked = name == task["tool"], name
    ok = tool_ok and all(arg_ok(k, v, args.get(k), k in task["fuzzy"]) for k, v in task["args"].items())
    return {"tool_ok": tool_ok, "args_ok": ok, "picked": picked, "args": args}


async def run(model_name: str, done: list[dict], save) -> tuple[list[dict], str | None]:
    p = cfg()["profiles"][cfg()["profile"]]
    llm = ChatOpenAI(model=model_name, base_url=p["base_url"], api_key=os.getenv(p["api_key_env"]), temperature=0,
                     timeout=90, max_retries=6)
    sets = toolsets(await real_tools())
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    rows, finished = list(done), {(r["set"], r["id"]) for r in done}
    system = prompt("tool_study")
    for t in tasks:                                   # task-major: a partial run is still a paired comparison
        for name, tools in sets.items():
            if (name, t["id"]) in finished:
                continue
            try:
                msg = await llm.bind_tools(tools, tool_choice="required").ainvoke([SystemMessage(system), HumanMessage(t["task"])])
            except Exception as e:  # noqa: BLE001
                s = str(e)
                if "429" in s and ("per day" in s or "(TPD)" in s):
                    return rows, s[:200]
                rows.append({"set": name, "id": t["id"], "tool": t["tool"], "valid": False, "error": s[:200]})
                save(rows)
                continue
            call = (msg.tool_calls or [None])[0]
            usage = msg.usage_metadata or {}
            rows.append({"set": name, "id": t["id"], "tool": t["tool"], "valid": True, **score(t, call, name == "coarse"),
                         "tokens": usage.get("total_tokens", 0), "input_tokens": usage.get("input_tokens", 0)})
            save(rows)
            r = rows[-1]
            print(f"{t['id']} {name:9s} gold={t['tool']:22s} picked={r['picked']} tool_ok={r['tool_ok']} args_ok={r['args_ok']} tok={r['tokens']}",
                  flush=True)
    return rows, None


def table(rows: list[dict], tag: str) -> str:
    ids = set.intersection(*({r["id"] for r in rows if r["set"] == s and r["valid"]} for s in ("fine", "coarse", "rewritten"))) \
        if rows else set()
    md = [f"### R&D question A: tool granularity ({tag})", "",
          f"Paired on the {len(ids)} tasks (of 40) that all three tool sets completed. One forced tool call per task.", "",
          "| Tool set | Tools | Tool-selection accuracy | Argument accuracy | Tokens per task | Input tokens per task |",
          "|---|---|---|---|---|---|"]
    for s, n in (("fine", 13), ("coarse", 3), ("rewritten", 13)):
        rr = [r for r in rows if r["set"] == s and r["valid"] and r["id"] in ids]
        if rr:
            md.append(f"| {s} | {n} | {sum(r['tool_ok'] for r in rr)}/{len(rr)} = {sum(r['tool_ok'] for r in rr) / len(rr):.0%} | "
                      f"{sum(r['args_ok'] for r in rr)}/{len(rr)} = {sum(r['args_ok'] for r in rr) / len(rr):.0%} | "
                      f"{statistics.mean(r['tokens'] for r in rr):.0f} | {statistics.mean(r['input_tokens'] for r in rr):.0f} |")
    wrong = [r for r in rows if r["valid"] and r["id"] in ids and not r["args_ok"]]
    if wrong:
        md += ["", "**Errors (tool or arguments wrong)**", "", "| Task | Set | Gold tool | Picked | Arguments given |", "|---|---|---|---|---|"]
        md += [f"| {r['id']} | {r['set']} | {r['tool']} | {r['picked']} | {json.dumps(r.get('args'))[:110].replace('|', '/')} |"
               for r in sorted(wrong, key=lambda x: (x["id"], x["set"]))]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai/gpt-oss-20b")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    res_file = OUT / "tool_granularity_results.json"
    done = [r for r in json.loads(res_file.read_text(encoding="utf-8"))["rows"] if r["valid"]] if a.resume and res_file.exists() else []
    tag = f"model={a.model}, temperature 0"
    OUT.mkdir(parents=True, exist_ok=True)
    save = lambda rows: res_file.write_text(json.dumps({"tag": tag + " (in progress)", "rows": rows}, indent=1), encoding="utf-8")  # noqa: E731
    rows, stopped = asyncio.run(run(a.model, done, save))
    if stopped:
        print(f"STOPPED: daily token limit ({stopped[:120]}). Re-run with --resume later.")
        tag += "; PARTIAL (daily token limit)"
    res_file.write_text(json.dumps({"tag": tag, "rows": rows}, indent=1), encoding="utf-8")
    md = table(rows, tag)
    (OUT / "tool_granularity_table.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
