"""Checkpoint history and replay for one job (C6), from the terminal. Uses the same persistence as the API
(Postgres if DATABASE_URL is set, else SQLite).

  python scripts/replay.py job-00044                       # list every checkpoint of the job's thread
  python scripts/replay.py job-00044 <checkpoint_id>       # replay from that checkpoint (stops at approval)

Replaying is safe: the graph still pauses at human approval, and submit reuses the thread's idempotency key,
so a replay can never send a proposal twice or spend Connects twice.
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agent.config import cfg  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.mcp_client import open_toolbox  # noqa: E402
from agent.persistence import backend, open_persistence  # noqa: E402


async def main():
    job_id, ckpt = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"persistence: {backend()}")
    async with open_persistence() as (saver, store), open_toolbox() as tb:
        g = build_bid_graph(saver, store)
        conf = {"configurable": {"toolbox": tb, "thread_id": job_id}, "recursion_limit": cfg()["budgets"]["max_steps"]}
        snaps = [s async for s in g.aget_state_history(conf)]
        if not snaps:
            return print(f"no checkpoints for {job_id}: analyse it first")
        if not ckpt:
            print(f"{'step':>4}  {'checkpoint_id':<38} {'after':<28} next")
            for i, s in enumerate(snaps):
                after = ",".join(snaps[i + 1].next) if i + 1 < len(snaps) else "__start__"
                print(f"{s.metadata.get('step', -1):>4}  {s.config['configurable']['checkpoint_id']:<38} "
                      f"{after:<28} {','.join(s.next) or '(end)'}")
            return
        conf["configurable"]["checkpoint_id"] = ckpt
        async for chunk in g.astream(None, conf, stream_mode="updates"):
            for node in chunk:
                print(f"  ran: {node}")
        final = await g.aget_state({"configurable": {"thread_id": job_id}})
        print(f"status: {final.values.get('status')} | next: {list(final.next)}")


if __name__ == "__main__":
    asyncio.run(main())
