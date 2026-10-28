#!/usr/bin/env python3
"""通过 Dify 服务 API 和「喵青天·鸡毛蒜皮法庭」对话，用于复现验证样例（只依赖 Python 3.9+ 标准库）。

单个会话（每个位置参数是同一会话里的一轮发言）：
    python3 scripts/play.py --api-key app-xxxx --player 阿强 \
        "我要起诉我家的闹钟，周六早上七点就把我吵醒" "法官大人，我按了三次贪睡键，这根猫条请您笑纳"

按剧本跑全部验证样例，并把对话记录写成 Markdown：
    python3 scripts/play.py --api-key app-xxxx --scenarios samples/scenarios.json --out samples/transcripts

API Key 在 Dify 应用的「访问 API」页面创建；也可以用环境变量 DIFY_API_KEY / DIFY_API_BASE 传入。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def chat(base: str, api_key: str, query: str, player: str, conversation_id: str, user: str) -> dict:
    body = json.dumps({"inputs": {"player": player}, "query": query, "response_mode": "streaming",
                       "conversation_id": conversation_id, "user": user}).encode()
    req = urllib.request.Request(f"{base.rstrip('/')}/chat-messages", data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    started = time.time()
    result = {"answer": "", "nodes": [], "conversation_id": conversation_id, "error": None}
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                kind = event.get("event")
                result["conversation_id"] = event.get("conversation_id") or result["conversation_id"]
                if kind == "message":
                    result["answer"] += event.get("answer", "")
                elif kind == "node_finished":
                    data = event["data"]
                    result["nodes"].append({"title": data.get("title"), "status": data.get("status"),
                                            "seconds": round(data.get("elapsed_time") or 0, 2),
                                            "error": data.get("error")})
                elif kind == "error":
                    result["error"] = event.get("message") or event
                elif kind == "workflow_finished" and event["data"].get("status") != "succeeded":
                    result["error"] = event["data"].get("error")
    except urllib.error.HTTPError as exc:
        result["error"] = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
    result["seconds"] = round(time.time() - started, 1)
    return result


def run_conversation(args, player: str, turns: list[str], title: str = "") -> list[str]:
    md = [f"## {title}" if title else f"## 原告：{player}", "", f"- 原告昵称（Start 输入 `player`）：`{player}`"]
    conversation_id = ""
    for i, query in enumerate(turns, start=1):
        print(f"\n>>> [{player}] {query}", flush=True)
        r = chat(args.base, args.api_key, query, player, conversation_id, args.user)
        conversation_id = r["conversation_id"]
        for n in r["nodes"]:
            flag = f"  !! {n['error']}" if n["error"] else ""
            print(f"    [{n['status']:>9}] {n['seconds']:>7}s  {n['title']}{flag}")
        print(f"--- {r['seconds']}s, conversation {conversation_id}, error={r['error']}\n")
        print(r["answer"], flush=True)
        if i == 1:
            md.append(f"- Dify 会话 ID：`{conversation_id}`")
        md += ["", f"### 第 {i} 轮 · 原告", "", "> " + query, "", f"### 第 {i} 轮 · 法庭（耗时 {r['seconds']} 秒）", "",
               r["answer"] if not r["error"] else f"**出错**：{r['error']}", "",
               "<details><summary>执行的工作流节点</summary>", "", "| 节点 | 状态 | 耗时(s) |", "|---|---|---|"]
        md += [f"| {n['title']} | {n['status']} | {n['seconds']} |" for n in r["nodes"]]
        md += ["", "</details>", ""]
        if r["error"]:
            print("!! 本轮出错，停止该会话", file=sys.stderr)
            break
    return md


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("turns", nargs="*", help="同一会话中依次发送的消息")
    p.add_argument("--api-key", default=os.environ.get("DIFY_API_KEY"), help="Dify 应用 API Key（app-...）")
    p.add_argument("--base", default=os.environ.get("DIFY_API_BASE", "http://localhost/v1"),
                   help="Dify 服务 API 地址，默认 http://localhost/v1")
    p.add_argument("--player", default="阿强", help="原告昵称：同一昵称共享同一份 PowerContext 案底")
    p.add_argument("--user", default="reviewer", help="Dify 终端用户标识")
    p.add_argument("--scenarios", help="验证剧本 JSON 文件（见 samples/scenarios.json）")
    p.add_argument("--only", help="只运行指定 id 的剧本，逗号分隔")
    p.add_argument("--out", help="把对话记录写成 Markdown 的目录")
    args = p.parse_args()
    if not args.api_key:
        p.error("需要 --api-key 或环境变量 DIFY_API_KEY")

    if args.scenarios:
        scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
        wanted = set(args.only.split(",")) if args.only else None
        for sc in scenarios:
            if wanted and sc["id"] not in wanted:
                continue
            md = [f"# {sc['id']} · {sc['title']}", "", sc.get("purpose", ""), "",
                  f"- 运行时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", f"- Dify API：`{args.base}`", ""]
            for conv in sc["conversations"]:
                md += run_conversation(args, conv["player"], conv["turns"], conv.get("title", ""))
            if args.out:
                Path(args.out).mkdir(parents=True, exist_ok=True)
                path = Path(args.out) / f"{sc['id']}.md"
                path.write_text("\n".join(md) + "\n", encoding="utf-8")
                print(f"\n=== 已写入 {path}")
        return 0

    if not args.turns:
        p.error("请给出至少一条消息，或使用 --scenarios")
    md = run_conversation(args, args.player, args.turns)
    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / f"play-{int(time.time())}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
