# -*- coding: utf-8 -*-
"""把「腾讯问卷」的投稿回答回填成网页用的 supplementary.js。

流程：老师填问卷 → 我用 MCP 拉回答存成 survey_answers.json → 跑本脚本 → supplementary.js 更新 → 推送上线。

用法：
    python3 ingest_supplement.py answers.json \
        --submit-url https://wj.qq.com/s2/123456/abcdef \
        [--links link_map.json] [--only-approved] [--dry-run]

参数：
    answers.json     MCP list_answers 的返回原样存盘即可（支持 {"list":[...]} 或裸数组）
    --submit-url     写进网页「＋ 提交补充材料」按钮的问卷链接
    --links          可选。{标题: 分享链接} 的 JSON，用于给附件未给出直链的条目补链接
                     （比如老师把文件传到了微云，我再补一条分享外链）
    --only-approved  只收录 approved.txt 里列出的标题（一行一个），用于人工审核
    --dry-run        只打印解析结果，不写文件

为什么不直接手改 supplementary.js：投稿内容来自外部，需要统一做类型归一、
链接校验、转义和单元归属解析；走脚本才不会漏项、不会写坏 JS。
"""
import argparse
import datetime
import json
import os
import re
import sys

from course_meta import PLACEHOLDER, resolve_unit

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "supplementary.js")

Q_UNIT = ("单元", "哪一课", "课次")
Q_TYPE = ("材料类型", "资料类型", "类型")
Q_TITLE = ("名称", "标题")
Q_NOTE = ("补充说明", "说明", "备注", "推荐用法")
Q_FILE = ("上传", "附件", "文件")
Q_LINK = ("链接", "网址", "网盘")
Q_BY = ("投稿人", "姓名", "称呼")

TYPE_RULES = [("音频", "audio"), ("视频", "video"), ("PPT", "ppt"),
              ("课件", "ppt"), ("文本", "text"), ("文档", "text"), ("文字", "text")]


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def q_title(q):
    for k in ("title", "text", "question", "name", "label"):
        v = q.get(k)
        if isinstance(v, str) and v.strip():
            return strip_html(v)
    return ""


def q_values(q):
    """按不同题型从各地取候选值：选项题给 options，填空题给 blanks，联动题给 groups。"""
    vals = []
    for k in ("options", "choices", "values", "blanks", "texts", "answers", "groups", "levels", "path"):
        v = q.get(k)
        if isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    vals.append(it)
                elif isinstance(it, dict):
                    for kk in ("text", "value", "name", "content", "answer"):
                        t = it.get(kk)
                        if isinstance(t, str) and t.strip():
                            vals.append(t)
                            break
    for k in ("value", "answer", "content"):
        v = q.get(k)
        if isinstance(v, str):
            vals.append(v)
        elif isinstance(v, dict):
            for kk in ("text", "value", "name"):
                t = v.get(kk)
                if isinstance(t, str) and t.strip():
                    vals.append(t)
                    break
    return [strip_html(x) for x in vals if isinstance(x, str) and x.strip()]


def iter_questions(ans):
    """回答结构是 页面[] → 题目[]，页面字段名在不同版本里叫 questions/question。"""
    pages = ans.get("answer") or ans.get("answers") or ans.get("pages") or []
    if isinstance(pages, dict):
        pages = [pages]
    for pg in pages or []:
        if not isinstance(pg, dict):
            continue
        qs = pg.get("questions") or pg.get("question") or []
        if not qs and ("title" in pg or "text" in pg):
            qs = [pg]
        for q in qs or []:
            if isinstance(q, dict):
                yield q


def hit(title, keys):
    return any(k in title for k in keys)


def norm_type(vals):
    blob = " ".join(vals)
    for kw, t in TYPE_RULES:
        if kw.lower() in blob.lower():
            return t
    return "text"


def pick_url(vals, links, title):
    """只接受 http(s) 直链；附件题若只给了文件名则到 --links 里找。"""
    for v in vals:
        m = re.search(r"https?://[^\s\"'<>]+", v or "")
        if m:
            return m.group(0)
    if links:
        for k, u in links.items():
            if k and (k in (title or "") or (title or "") in k):
                m = re.search(r"https?://[^\s\"'<>]+", str(u))
                if m:
                    return m.group(0)
    return ""


def parse_answer(ans, links):
    """把一条回答拆成 (单元ID, entry)；err 非空表示该条不被收录。"""
    fields = {}
    for q in iter_questions(ans):
        t = q_title(q)
        vals = q_values(q)
        if not t and not vals:
            continue
        if hit(t, Q_UNIT):
            fields.setdefault("unit", []).extend(vals)
        elif hit(t, Q_TYPE):
            fields.setdefault("type", []).extend(vals)
        elif hit(t, Q_NOTE):
            fields.setdefault("note", []).extend(vals)
        elif hit(t, Q_FILE):
            fields.setdefault("file", []).extend(vals)
        elif hit(t, Q_LINK):
            fields.setdefault("link", []).extend(vals)
        elif hit(t, Q_BY):
            fields.setdefault("by", []).extend(vals)
        elif hit(t, Q_TITLE):
            fields.setdefault("title", []).extend(vals)
        else:
            fields.setdefault("other", []).extend(vals)

    unit_vals = [v for v in fields.get("unit", []) if v and PLACEHOLDER not in v]
    uid = resolve_unit(unit_vals[0]) if unit_vals else None
    if not uid:
        return None, None, f"单元无法识别（原始值：{fields.get('unit')}）"

    course = unit_vals[1] if len(unit_vals) > 1 else ""
    title_vals = fields.get("title") or []
    name = title_vals[0] if title_vals else ""
    if name:
        # 老师填的「资料名称」优先；课次名若没出现在里面，就括注在后面做定位
        title = name if (not course or course in name) else f"{name}（{course}）"
    else:
        title = course or "（未命名）"

    t = norm_type(fields.get("type", []))
    url = pick_url(fields.get("file", []) + fields.get("link", []), links, title)
    note = " ".join(fields.get("note", [])).strip()
    by = (fields.get("by") or [""])[0].strip()

    entry = {"t": t, "title": title, "by": by}
    if url:
        entry["url"] = url
    if note:
        entry["note"] = note
    if t == "text" and not url and not note:
        return None, None, "文本类条目既没有正文也没有链接"
    return uid, entry, ""


def js_escape(s):
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\r", "").replace("</", "<\\/"))


def render(units, submit_url, note_tip):
    lines = []
    for uid in sorted(units):
        lines.append(f'    {json.dumps(uid)}: [')
        for e in units[uid]:
            parts = [f'"t": "{e["t"]}"']
            for k in ("title", "by", "size", "date", "url", "note"):
                if e.get(k):
                    parts.append(f'"{k}": "{js_escape(e[k])}"')
            lines.append("      {" + ", ".join(parts) + "},")
        lines.append("    ],")
    body = "\n".join(lines) if lines else ""
    return f'''/* ============================================================================
 * 补充资料区数据（教师投稿）—— 本文件由 ingest_supplement.py 自动生成，请勿手改。
 * 数据来源：腾讯问卷《音乐鉴赏》补充资料投稿
 * 生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M}
 * 共收录 {sum(len(v) for v in units.values())} 条，覆盖 {len(units)} 个单元。
 * ========================================================================== */
window.SUPPLEMENTARY = {{
  updated: "{datetime.date.today():%Y-%m-%d}",

  /* 投稿入口：腾讯问卷投放链接 */
  submit: {{
    url: "{submit_url}",
    tip: "{js_escape(note_tip)}"
  }},

  units: {{
{body}
  }}
}};
'''


DEFAULT_TIP = ("欢迎把你手上好用的音频、视频、PPT 或文字资料投到对应单元——按「单元 + 课次」和"
               "「材料类型」填写即可。审核通过后，全组老师都能在本页看到并使用。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("answers", help="list_answers 的 JSON（原样存盘即可）")
    ap.add_argument("--submit-url", default="", help="问卷投放链接，写进页面按钮")
    ap.add_argument("--links", default="", help="{标题: 链接} JSON，补充附件缺失的直链")
    ap.add_argument("--tip", default=DEFAULT_TIP)
    ap.add_argument("--only-approved", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    raw = json.load(open(a.answers, encoding="utf-8"))
    answers = raw.get("list") or raw.get("answers") or raw if isinstance(raw, (list, dict)) else []
    if isinstance(raw, dict) and "list" not in raw and "answers" not in raw:
        answers = raw.get("list", [])
    if not isinstance(answers, list):
        answers = []

    links = {}
    if a.links:
        links = json.load(open(a.links, encoding="utf-8"))

    approved = None
    if a.only_approved:
        p = os.path.join(ROOT, "approved.txt")
        approved = {l.strip() for l in open(p, encoding="utf-8") if l.strip()} if os.path.exists(p) else set()

    units, skipped = {}, []
    for ans in answers:
        uid, e, err = parse_answer(ans, links)
        if not e:
            skipped.append(err)
            continue
        if approved is not None and e["title"] not in approved:
            skipped.append(f"未在 approved.txt 中：{e['title']}")
            continue
        units.setdefault(uid, []).append(e)

    print(f"读到回答 {len(answers)} 条 → 收录 {sum(len(v) for v in units.values())} 条，"
          f"跳过 {len(skipped)} 条")
    for s in skipped:
        print("   跳过：" + s)
    for uid in sorted(units):
        for e in units[uid]:
            print(f"   {uid}  [{e['t']:5}] {e['title']}"
                  + (f"  ← {e['url']}" if e.get("url") else "  ← 链接待补"))

    if a.dry_run:
        print("（--dry-run，未写文件）")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(units, a.submit_url, a.tip))
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    sys.exit(main())
