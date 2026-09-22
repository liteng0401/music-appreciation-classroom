#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小 MCP streamable-HTTP 客户端：从 CODEBUDDY_MCP_CONFIG 里取连接器的本地代理地址与
会话令牌，直接调用微云 MCP 工具。令牌只在内存中使用，不打印。

用法：python3 mcp_weiyun.py <tool_name> '<json_args>'
"""
import json, os, sys, threading, urllib.request

_id_lock = threading.Lock()
_id_seq = [0]


def _next_id():
    with _id_lock:
        _id_seq[0] += 1
        return _id_seq[0]


def server_cfg(name="tencent-weiyun"):
    raw = os.environ.get("CODEBUDDY_MCP_CONFIG", "")
    if not raw:
        raise SystemExit("CODEBUDDY_MCP_CONFIG 不存在")
    cfg = json.loads(raw)
    srv = cfg.get("mcpServers", cfg)
    if name not in srv:
        raise SystemExit("找不到服务 " + name)
    return srv[name]


def rpc(srv, method, params, sid=None, notify=False):
    body = {"jsonrpc": "2.0", "method": method}
    if not notify:
        body["id"] = _next_id()
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(
        srv["url"], data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "Authorization": srv["headers"]["Authorization"],
                 "X-WorkBuddy-MCP-Context": srv["headers"]["X-WorkBuddy-MCP-Context"]},
        method="POST")
    if sid:
        req.add_header("Mcp-Session-Id", sid)
    with urllib.request.urlopen(req, timeout=120) as r:
        sid = r.headers.get("Mcp-Session-Id") or sid
        txt = r.read().decode("utf-8", "replace")
    return parse(txt), sid


def parse(txt):
    # 同时兼容 application/json 与 text/event-stream(data: 行)
    if txt.lstrip().startswith("{"):
        return json.loads(txt)
    out = None
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out = json.loads(line[5:].strip())
    return out


def call(tool, args):
    srv = server_cfg()
    init, sid = rpc(srv, "initialize", {"protocolVersion": "2025-06-18",
                                        "capabilities": {},
                                        "clientInfo": {"name": "wb-script", "version": "1.0"}})
    rpc(srv, "notifications/initialized", None, sid=sid, notify=True)
    res, _ = rpc(srv, "tools/call", {"name": tool, "arguments": args}, sid=sid)
    return res


if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    out = call(tool, args)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
