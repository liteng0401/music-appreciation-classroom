#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已上传到微云的单元课件包生成分享链接，并写出页面用的 ppt_mirror.js。

输入：tools/weiyun_uploaded.json（weiyun_put.py 的产物：文件名 → {file_id,size,pdir_key}）
输出：ppt_mirror.js（window.PPT_MIRROR）+ tools/pptshare_links.json（缓存，避免重复建分享）

用法：
  python3 tools/gen_ppt_mirror.py            # 只处理还没建过分享的单元
  python3 tools/gen_ppt_mirror.py --rebuild  # 忽略缓存，全部重建分享链接
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from mcp_weiyun import server_cfg, rpc  # noqa: E402

UP = os.path.join(HERE, "weiyun_uploaded.json")
CACHE = os.path.join(HERE, "pptshare_links.json")
OUT = os.path.join(ROOT, "ppt_mirror.js")
PPT_SRC = os.path.join(ROOT, "media", "ppt")


def unit_of(name):
    m = re.match(r"^(ch\d\d)\s", name)
    return m.group(1) if m else None


def file_count(uid):
    d = os.path.join(PPT_SRC, uid)
    if not os.path.isdir(d):
        return None
    return len([f for f in os.listdir(d) if not f.startswith(".")])


def main():
    rebuild = "--rebuild" in sys.argv
    up = json.load(open(UP, encoding="utf-8")) if os.path.exists(UP) else {}
    cache = {}
    if os.path.exists(CACHE) and not rebuild:
        cache = json.load(open(CACHE, encoding="utf-8"))
    srv = server_cfg()
    _, sid = rpc(srv, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "mirror", "version": "1"}})

    units = {}
    for fname, info in sorted(up.items()):
        uid = unit_of(fname)
        if not uid:
            print("跳过（认不出单元）:", fname)
            continue
        if not info.get("file_id"):
            print("跳过（没有 file_id，需重传）:", fname)
            continue
        c = cache.get(uid)
        if c and c.get("file_id") == info["file_id"] and c.get("url"):
            url = c["url"]
        else:
            res, _ = rpc(srv, "tools/call", {
                "name": "weiyun.gen_share_link",
                "arguments": {"file_list": [{"file_id": info["file_id"],
                                             "pdir_key": info.get("pdir_key", "")}],
                              "share_name": "音乐鉴赏课件-%s" % uid}},
                sid=sid)
            # 微云整个连接器按日限流：配额用尽时返回的是 {error:{code:-32603,...}}，
            # 没有 result。这种情况**不要抛异常**，跳过该单元继续跑，
            # 否则已经建好的链接会被这次失败连累、整个文件都写不出来。
            if "result" not in res:
                msg = json.dumps(res.get("error", res), ensure_ascii=False)[:200]
                print("!! 拿不到分享 %s（跳过，保留其余）：%s" % (uid, msg))
                continue
            d = res["result"].get("structuredContent")
            if d is None:
                d = json.loads(res["result"]["content"][0]["text"])
            if d.get("error"):
                print("!! 分享失败 %s：%s" % (uid, d["error"]))
                continue
            url = d["short_url"]
            cache[uid] = {"file_id": info["file_id"], "url": url, "zip": fname}
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("分享 %s -> %s" % (uid, url), flush=True)
        units[uid] = {"url": url, "size": info["size"], "files": file_count(uid) or 0,
                      "zip": fname, "sha_file_id": info["file_id"]}

    js = [
        "// 自动生成：tools/gen_ppt_mirror.py —— 请勿手工编辑。",
        "// 课件 PPT 的微云镜像：每个单元一个打包 zip。国内网络直连下载，无需科学上网，",
        "// 但微云分享要求登录后才能下载（微信/QQ 扫码，登录一次长期有效）。",
        "window.PPT_MIRROR = {",
        '  "updated": "%s",' % __import__("datetime").date.today().isoformat(),
        '  "note": "微云分享，国内直连可用；下载需登录微云（微信/QQ 扫码，一次即可）",',
        '  "units": {',
    ]
    for uid in sorted(units):
        u = units[uid]
        js.append('    "%s": {"url": "%s", "size": %d, "files": %d, "zip": "%s"},'
                  % (uid, u["url"], u["size"], u["files"], u["zip"].replace('"', '\\"')))
    js.append("  }")
    js.append("};")
    open(OUT, "w", encoding="utf-8").write("\n".join(js) + "\n")
    print("写出 %s：%d 个单元" % (OUT, len(units)))


if __name__ == "__main__":
    main()
