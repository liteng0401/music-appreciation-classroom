#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地文件上传到微云（走宿主的本地 MCP 代理，不需要额外授权）。

微云上传是两阶段协议：预上传（可能秒传）→ 循环分片上传。分块哈希必须本地算，
复用微云 Skill 自带的实现，避免协议细节写错。

用法：
  python3 tools/weiyun_put.py <file> [<file> ...] [--pdir_key <目录key>] [--out result.json]

结果写入 --out（默认 tools/weiyun_uploaded.json），已是「文件名 → {file_id,size}」，
重复运行会跳过已上传成功的文件（按文件名 + 大小匹配）。
"""
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/Users/lt/.workbuddy/connectors/skills/connector-tencent-weiyun/scripts")

from mcp_weiyun import server_cfg, rpc  # noqa: E402

# 微云 Skill 的脚本在 import 阶段就会检查 requests；我们只用它的分块哈希实现，
# 不用它的网络部分（网络走宿主本地代理），所以这里塞一个空壳模块顶过去。
import types  # noqa: E402
sys.modules.setdefault("requests", types.ModuleType("requests"))

from upload_to_weiyun import calc_upload_params  # noqa: E402  (微云 Skill 自带的哈希实现)

MAX_ROUNDS = 5000


class Client:
    """一次 initialize，后续复用 session 调 tools/call。"""

    def __init__(self, name="tencent-weiyun"):
        self.srv = server_cfg(name)
        _, self.sid = rpc(self.srv, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "wb-uploader", "version": "1.0"}})
        try:
            rpc(self.srv, "notifications/initialized", None, sid=self.sid, notify=True)
        except Exception:
            pass

    def call(self, tool, args, retries=3):
        last = None
        for i in range(retries):
            try:
                res, _ = rpc(self.srv, "tools/call",
                             {"name": tool, "arguments": args}, sid=self.sid)
            except Exception as e:                     # 网络抖动
                last = {"error": "transport: %s" % e}
                time.sleep(2 + 2 * i)
                continue
            payload = None
            if isinstance(res, dict):
                payload = res.get("structuredContent")
                if payload is None:
                    for it in (res.get("result", {}) or {}).get("content", []):
                        if it.get("type") == "text":
                            try:
                                payload = json.loads(it["text"])
                            except Exception:
                                pass
                if payload is None and "error" in res:
                    payload = {"error": json.dumps(res["error"], ensure_ascii=False)}
            if isinstance(payload, dict) and payload.get("retcode", 0) == 50000:
                last = payload
                time.sleep(3)
                continue
            return payload or {}
        return last or {}


def upload_one(cli, path, pdir_key=None, workers=4, quiet=False):
    """一轮预上传会返回若干个 512KB 通道，必须**一轮内把所有通道都传掉**再去要下一轮，
    否则每次只传一个通道，速度只有 1/4。"""
    size = os.path.getsize(path)
    name = os.path.basename(path)
    params = calc_upload_params(path)
    pre = {"filename": params["filename"], "file_size": params["file_size"],
           "file_sha": params["file_sha"], "file_md5": params["file_md5"],
           "block_sha_list": params["block_sha_list"], "check_sha": params["check_sha"],
           "check_data": params["check_data"]}
    if pdir_key:
        pre["pdir_key"] = pdir_key
    with open(path, "rb") as f:
        blob = f.read()
    rnd = 0
    done_bytes = 0
    while rnd < MAX_ROUNDS:
        rnd += 1
        r = cli.call("weiyun.upload", pre)
        if r.get("error"):
            raise RuntimeError("预上传失败: %s" % r["error"])
        if str(r.get("file_exist")).lower() in ("true", "1"):
            return {"file_id": r.get("file_id", ""), "size": size, "mode": "秒传"}
        # file_id 在「预上传」响应里就有了，别等最后一轮的分片响应（那里是空的）
        file_id = r.get("file_id", "") or ""
        chs = [c for c in (r.get("channel_list") or []) if int(c.get("len", 0)) > 0
               and int(c.get("offset", 0)) < size]
        if not chs:
            if int(r.get("upload_state", 0)) == 2:
                return {"file_id": file_id, "size": size, "mode": "完成"}
            raise RuntimeError("无可上传通道 upload_state=%s" % r.get("upload_state"))
        cl = [{"id": int(c["id"]), "offset": int(c["offset"]), "len": int(c["len"])} for c in chs]

        def send(c):
            off = int(c["offset"]); real = min(int(c["len"]), size - off)
            up = cli.call("weiyun.upload", {
                "filename": name, "file_size": size, "file_sha": params["file_sha"],
                "block_sha_list": [], "check_sha": params["check_sha"],
                "upload_key": r.get("upload_key", ""), "channel_list": cl,
                "channel_id": int(c["id"]), "ex": r.get("ex", ""),
                "file_data": base64.b64encode(blob[off:off + real]).decode()})
            if up.get("error"):
                raise RuntimeError("分片失败(ch=%s): %s" % (c["id"], up["error"]))
            return real, up

        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for fut in [pool.submit(send, c) for c in chs]:
                results.append(fut.result())
        done_bytes += sum(x[0] for x in results)
        if not quiet:
            print("    %5.1f%%  round=%-5d 通道=%d  累计 %.1f/%.1f MB"
                  % (min(100, done_bytes * 100.0 / size), rnd, len(chs),
                     done_bytes / 1048576, size / 1048576), flush=True)
        if any(int(u.get("upload_state", 0)) == 2 for _, u in results):
            fid = next((u.get("file_id") for _, u in results if u.get("file_id")), file_id)
            return {"file_id": fid, "size": size, "mode": "完成"}
    raise RuntimeError("轮数超限未完成")


def main():
    argv = sys.argv[1:]
    pdir, out = None, os.path.join(HERE, "weiyun_uploaded.json")
    files = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--pdir_key":
            pdir = argv[i + 1]; i += 2
        elif a == "--out":
            out = argv[i + 1]; i += 2
        else:
            files.append(a); i += 1
    done = {}
    if os.path.exists(out):
        done = json.load(open(out, encoding="utf-8"))
    cli = Client()
    for p in files:
        name = os.path.basename(p)
        size = os.path.getsize(p)
        if done.get(name, {}).get("size") == size and done[name].get("file_id"):
            print("SKIP %s（已上传 file_id=%s）" % (name, done[name]["file_id"]), flush=True)
            continue
        t0 = time.time()
        print("UP   %s  (%.1f MB)" % (name, size / 1048576), flush=True)
        try:
            res = upload_one(cli, p, pdir)
        except Exception as e:
            print("FAIL %s -> %s" % (name, e), flush=True)
            continue
        res["pdir_key"] = pdir or ""
        done[name] = res
        json.dump(done, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("OK   %s  file_id=%s  %s  %.1fs" % (name, res["file_id"], res["mode"], time.time() - t0), flush=True)
    print("---- 完成 %d / %d" % (len([k for k in done if os.path.basename(k) in [os.path.basename(f) for f in files]]), len(files)), flush=True)


if __name__ == "__main__":
    main()
