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


# 宿主连接器未连上时的兜底：官方 mcporter 客户端自己存着直连地址与令牌头。
# 我们只借用它的配置，令牌依旧只存在 mcporter 自己的 ~/.mcporter/mcporter.json 里，
# 不落到本仓库、不打印。
_MCPORTER_FILE = "~/.mcporter/mcporter.json"
_MCPORTER_ALIAS = {"tencent-weiyun": "weiyun"}


def server_cfg(name="tencent-weiyun"):
    raw = os.environ.get("CODEBUDDY_MCP_CONFIG", "")
    if raw:
        cfg = json.loads(raw)
        srv = cfg.get("mcpServers", cfg)
        if name in srv:
            return srv[name]
    fb = _mcporter_cfg(name)
    if fb:
        return fb
    detail = "（CODEBUDDY_MCP_CONFIG 未注入该服务）" if not raw else "（该服务未连接）"
    raise SystemExit("找不到服务 %s %s" % (name, detail))


def _mcporter_cfg(name):
    """从 mcporter 配置里取直连端点；返回 None 表示没有可用兜底。"""
    try:
        path = os.path.expanduser(_MCPORTER_FILE)
        with open(path, encoding="utf-8") as f:
            srv = json.load(f).get("mcpServers", {})
    except Exception:
        return None
    entry = srv.get(_MCPORTER_ALIAS.get(name, name))
    if not entry or not entry.get("baseUrl"):
        return None
    return {"url": entry["baseUrl"], "headers": dict(entry.get("headers") or {})}


def rpc(srv, method, params, sid=None, notify=False):
    body = {"jsonrpc": "2.0", "method": method}
    if not notify:
        body["id"] = _next_id()
    if params is not None:
        body["params"] = params
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    # 宿主代理用 Authorization/X-WorkBuddy-MCP-Context，mcporter 直连用 WyHeader，
    # 所以按配置里实际有什么就发什么。
    headers.update(srv.get("headers") or {})
    req = urllib.request.Request(
        srv["url"], data=json.dumps(body).encode("utf-8"),
        headers=headers, method="POST")
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
