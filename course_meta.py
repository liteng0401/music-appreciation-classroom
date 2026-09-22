# -*- coding: utf-8 -*-
"""共享工具：读取 data.js 里的课程结构（单元 / 作品），供问卷生成与投稿回填脚本复用。
这样「问卷里的单元名称」和「网页上的单元 ID」永远来自同一份真源，不会漂移。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
UNIT_INDEX_FILE = os.path.join(ROOT, "unit_index.json")


def load_course():
    """解析 data.js（形如 `window.COURSE_DATA = {...};`）并返回 dict。"""
    raw = open(os.path.join(ROOT, "data.js"), encoding="utf-8").read()
    return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])


def clean_paren(t):
    """去掉标题尾部的「（书7–16页）」这类括注。"""
    return re.sub(r"（[^）]*）\s*$", "", t or "").strip()


def unit_label(u):
    """单元在问卷里显示的名字：序篇统一叫「序篇」，其余去掉书页括注。"""
    return "序篇" if u.get("group") == "序篇" else clean_paren(u.get("title"))


def work_label(w):
    """作品在问卷里显示的名字：去掉书名号。"""
    return re.sub(r"[《》]", "", w.get("name") or "").strip()


PLACEHOLDER = "（本单元整体资料）"


def build_index():
    """生成 {单元标签: {id, courses:[课程标签...]}}，并落盘 unit_index.json。"""
    D = load_course()
    idx = {}
    for u in D["units"]:
        idx[unit_label(u)] = {
            "id": u["id"],
            "courses": [PLACEHOLDER] + [work_label(w) for w in u.get("works", [])],
        }
    with open(UNIT_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    return idx


def resolve_unit(label, index=None):
    """把问卷里的单元名称解析回 chXX。宽容匹配：全等 → 去空格 → 包含。"""
    index = index or json.load(open(UNIT_INDEX_FILE, encoding="utf-8"))
    label = (label or "").strip()
    if label in index:
        return index[label]["id"]
    compact = re.sub(r"\s", "", label)
    for k, v in index.items():
        if re.sub(r"\s", "", k) == compact:
            return v["id"]
    for k, v in index.items():
        if compact and (compact in re.sub(r"\s", "", k) or re.sub(r"\s", "", k) in compact):
            return v["id"]
    m = re.search(r"第([一二三四五六七八九十]+)单元", label)
    if m:
        for k, v in index.items():
            if m.group(0) in k:
                return v["id"]
    return None


if __name__ == "__main__":
    idx = build_index()
    total_courses = sum(len(v["courses"]) for v in idx.values())
    print(f"单元 {len(idx)} 个，课程行 {total_courses} 行 → {UNIT_INDEX_FILE}")
    for k, v in list(idx.items())[:3]:
        print(f"  {v['id']}  {k}  课程 {len(v['courses'])} 个")
