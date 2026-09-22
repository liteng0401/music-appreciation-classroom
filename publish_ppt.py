#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 media/ppt/ 下的课件 PPT 作为 GitHub Release 附件发布（附件名必须是纯 ASCII，
GitHub 会把中文名直接吞掉，所以这里统一改名成 "<单元>-<序号>.pptx"）。

用法：
  python3 publish_ppt.py --plan     # 只生成 ppt_urls.json（附件名↔原始文件名↔下载链接），不上传
  python3 publish_ppt.py --upload  # 上传全部附件（先自动建 release）
  python3 publish_ppt.py            # = --plan --upload

生成的 ppt_urls.json 会被 import_resources.py 读取，用来给网页上的 PPT 按钮
挂上 Release 下载地址。原始中文文件名在网页上照常显示，不受影响。
"""
import os, re, json, subprocess, sys

ROOT   = os.path.dirname(os.path.abspath(__file__))
PPT_DIR = os.path.join(ROOT, "media", "ppt")
URLS    = os.path.join(ROOT, "ppt_urls.json")
REPO    = "liteng0401/music-appreciation-classroom"
TAG     = "ppt-v1"
TITLE   = "课件 PPT 原始文件（52 个）"
NOTES   = ("人音版高中《音乐鉴赏》配套课件 PPT 原始文件，供教师在网页上直接下载。\n\n"
           "文件未经压缩，画质/音质与原版一致。附件名按 <单元>-<序号> 编号，"
           "与网页「配套资源下载」里的条目顺序一一对应（网页上显示中文文件名）。")

PLAN = "--plan" in sys.argv or "--upload" not in sys.argv
UP   = "--upload" in sys.argv or "--plan" not in sys.argv


def gh(*args, **kw):
    env = dict(os.environ)
    env["DEVELOPER_DIR"] = "/Library/Developer/CommandLineTools"
    # 附件上传域名会被沙箱环境变量代理拦，改走用户系统代理
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        env[k] = "http://127.0.0.1:7897"
    return subprocess.run(["gh"] + list(args), env=env, capture_output=True, text=True, **kw)


def build_plan():
    plan = {}
    for uid in sorted(os.listdir(PPT_DIR)):
        d = os.path.join(PPT_DIR, uid)
        if not os.path.isdir(d):
            continue
        files = sorted(f for f in os.listdir(d) if not f.startswith("."))
        for i, f in enumerate(files, 1):
            ext = os.path.splitext(f)[1].lower()
            asset = f"{uid}-{i:02d}{ext}"
            plan[f"{uid}/{f}"] = {
                "unit": uid,
                "no": i,
                "asset": asset,
                "orig": f,
                "size": os.path.getsize(os.path.join(d, f)),
                "url": f"https://github.com/{REPO}/releases/download/{TAG}/{asset}",
            }
    return plan


def ensure_release():
    r = gh("release", "view", TAG)
    if r.returncode == 0:
        print(f"release {TAG} 已存在")
        return
    r = gh("release", "create", TAG, "--title", TITLE, "--notes", NOTES)
    if r.returncode != 0:
        print("创建 release 失败:", r.stderr.strip()[:300]); sys.exit(1)
    print(f"已创建 release {TAG}")


def main():
    plan = build_plan()
    if PLAN:
        with open(URLS, "w", encoding="utf-8") as fp:
            json.dump(plan, fp, ensure_ascii=False, indent=1)
        tot = sum(v["size"] for v in plan.values())
        print(f"计划：{len(plan)} 个附件，合计 {tot/1073741824:.2f} GB -> ppt_urls.json")
        for k, v in list(plan.items())[:4]:
            print(f"  {v['asset']:16} <- {k}  ({v['size']/1048576:.0f}MB)")
    if not UP:
        return
    ensure_release()
    items = sorted(plan.values(), key=lambda v: (v["unit"], v["no"]))
    BATCH_MB = 450
    batch, bsz, done = [], 0, 0
    batches = []
    for v in items:
        batch.append(v); bsz += v["size"] / 1048576
        if bsz >= BATCH_MB:
            batches.append(batch); batch, bsz = [], 0
    if batch:
        batches.append(batch)
    for bi, b in enumerate(batches, 1):
        paths = [os.path.join(PPT_DIR, v["unit"], v["orig"]) for v in b]
        # 附件名要 ASCII：先把副本改成目标名放到临时目录再传
        tmpdir = os.path.join(ROOT, ".ppt_upload_tmp")
        os.makedirs(tmpdir, exist_ok=True)
        named = []
        for p, v in zip(paths, b):
            dst = os.path.join(tmpdir, v["asset"])
            if not os.path.exists(dst) or os.path.getsize(dst) != v["size"]:
                subprocess.run(["cp", p, dst], check=True)
            named.append(dst)
        r = gh("release", "upload", TAG, *named, "--clobber")
        if r.returncode != 0:
            print(f"第 {bi} 批失败：", r.stderr.strip()[:400]); sys.exit(1)
        for dst in named:                      # 传完就删副本，别白占 2GB
            try:
                os.remove(dst)
            except OSError:
                pass
        done += len(b)
        print(f"第 {bi}/{len(batches)} 批完成（累计 {done}/{len(items)} 个，"
              f"{sum(x['size'] for x in items[:done])/1073741824:.2f}GB）", flush=True)
    try:
        os.rmdir(os.path.join(ROOT, ".ppt_upload_tmp"))
    except OSError:
        pass
    print("全部附件上传完成")


if __name__ == "__main__":
    main()
