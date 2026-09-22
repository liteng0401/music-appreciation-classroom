#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探查微云预上传返回的通道结构：一次预上传最多给几个通道、每个多大。"""
import json, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.modules.setdefault("requests", types.ModuleType("requests"))
sys.path.insert(0, "/Users/lt/.workbuddy/connectors/skills/connector-tencent-weiyun/scripts")
from mcp_weiyun import server_cfg, rpc
from upload_to_weiyun import calc_upload_params

p = sys.argv[1]
pdir = sys.argv[2] if len(sys.argv) > 2 else None
srv = server_cfg()
_, sid = rpc(srv, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "probe", "version": "1"}})
params = calc_upload_params(p)
args = {"filename": params["filename"], "file_size": params["file_size"],
        "file_sha": params["file_sha"], "file_md5": params["file_md5"],
        "block_sha_list": params["block_sha_list"], "check_sha": params["check_sha"],
        "check_data": params["check_data"]}
if pdir:
    args["pdir_key"] = pdir
res, _ = rpc(srv, "tools/call", {"name": "weiyun.upload", "arguments": args}, sid=sid)
d = res.get("structuredContent") or json.loads(res["result"]["content"][0]["text"])
chs = d.get("channel_list") or []
print("file_size   =", d.get("file_size"), "(%.1f MB)" % (d.get("file_size", 0) / 1048576))
print("file_exist  =", d.get("file_exist"))
print("upload_state=", d.get("upload_state"))
print("upload_key  =", str(d.get("upload_key"))[:40], "…")
print("ex          =", str(d.get("ex"))[:40], "…")
print("通道数       =", len(chs))
for c in chs:
    print("   id=%-12s offset=%-12s len=%-10s (%.2f MB)" % (c.get("id"), c.get("offset"), c.get("len"), int(c.get("len", 0)) / 1048576))
print("其它字段:", {k: str(v)[:60] for k, v in d.items() if k not in
                ("channel_list", "block_sha_list", "check_data", "ex", "upload_key")})
