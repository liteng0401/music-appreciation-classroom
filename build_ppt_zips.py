#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 media/ppt/chXX/ 下每个单元的课件 PPT 打成 zip，便于放到微云给老师一键下载。

输出到 .ppt_zip/ ；文件名形如 "ch01 第一单元 学会聆听.zip"（保留中文，微云不像
GitHub Release 那样会吞掉非 ASCII 名）。
单元标题取自 unit_index.json（course_meta.py 生成的单元/课次真源）。

用法：
  python3 build_ppt_zips.py            # 全部 19 个单元
  python3 build_ppt_zips.py ch12       # 只做指定单元（试通用）
"""
import os, sys, json, zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "media", "ppt")
OUT = os.path.join(ROOT, ".ppt_zip")
IDX = os.path.join(ROOT, "unit_index.json")


def unit_titles():
    d = json.load(open(IDX, encoding="utf-8"))
    units = d.get("units", d)
    out = {}
    for name, v in units.items():
        out[v["id"]] = name
    return out


def main():
    want = [a for a in sys.argv[1:] if a.startswith("ch")]
    titles = unit_titles()
    os.makedirs(OUT, exist_ok=True)
    units = sorted(d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d)))
    if want:
        units = [u for u in units if u in want]
    total = 0
    for uid in units:
        d = os.path.join(SRC, uid)
        files = sorted(f for f in os.listdir(d) if not f.startswith("."))
        if not files:
            print("SKIP", uid, "空目录")
            continue
        zname = "%s %s.zip" % (uid, titles.get(uid, uid))
        zpath = os.path.join(OUT, zname)
        if os.path.exists(zpath):
            os.remove(zpath)
        # PPTX 本身已是 zip，再做 deflate 收益极小 → 用 STORED，速度快
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for f in files:
                z.write(os.path.join(d, f), f)
        sz = os.path.getsize(zpath)
        total += sz
        print("OK  %-34s %6.1f MB  (%d 个文件)" % (zname, sz / 1048576, len(files)), flush=True)
    print("---- 合计 %.2f GB" % (total / 1073741824), flush=True)


if __name__ == "__main__":
    main()
