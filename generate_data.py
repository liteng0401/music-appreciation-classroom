#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 music-appreciation skill 的章节/术语/速查表解析出网页数据 data.js。"""
import os, re, json, random

SKILL = "/Users/lt/.workbuddy/skills/music-appreciation"
OUT = "/Users/lt/WorkBuddy/2026-09-21-01-46-33/music-appreciation-web/data.js"

GROUP_BY_PREFIX = {
    "ch00": "序篇",
    "ch01": "上篇", "ch02": "上篇", "ch03": "上篇", "ch04": "上篇",
    "ch05": "上篇", "ch06": "上篇", "ch07": "上篇", "ch08": "上篇",
    "ch09": "下篇", "ch10": "下篇", "ch11": "下篇", "ch12": "下篇",
    "ch13": "下篇", "ch14": "下篇", "ch15": "下篇", "ch16": "下篇",
    "ch17": "下篇", "ch18": "下篇",
}

def read(p):
    return open(p, encoding="utf-8").read()

def parse_section(blocks, header):
    return blocks.get(header, "")

def split_sections(md):
    """返回 {header: body} 按 '## ' 切分；保留 '# ' 作为 title。"""
    lines = md.splitlines()
    title = ""
    cur = None
    blocks = {}
    buf = []
    for ln in lines:
        if ln.startswith("# ") and not title:
            title = ln[2:].strip()
            continue
        if ln.startswith("## "):
            if cur is not None:
                blocks[cur] = "\n".join(buf).strip()
            cur = ln[3:].strip()
            buf = []
        else:
            buf.append(ln)
    if cur is not None:
        blocks[cur] = "\n".join(buf).strip()
    return title, blocks

def parse_term_bullets(body):
    """解析 '- **术语**：定义' 及其续行/子项。返回 [(term, def, detail)]。"""
    items = []
    term = None; defin = ""; detail = []
    for ln in body.splitlines():
        m = re.match(r'^- \*\*(.+?)\*\*[\s：:—-]*(.*)$', ln)
        if m:
            if term is not None:
                items.append((term, defin.strip(), "\n".join(detail).strip()))
            term = m.group(1).strip()
            defin = m.group(2).strip()
            detail = []
        elif ln.strip().startswith("- ") and term is not None:
            detail.append(ln.strip()[2:].strip())
        elif term is not None and ln.strip():
            # 续行（非 bullet）
            if not defin:
                defin = ln.strip()
            else:
                detail.append(ln.strip())
    if term is not None:
        items.append((term, defin.strip(), "\n".join(detail).strip()))
    return items

def parse_simple_bullets(body):
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("- "):
            out.append(s[2:].strip())
        elif re.match(r'^\d+\.\s', s):
            out.append(re.sub(r'^\d+\.\s', '', s))
    return out

def parse_table(body):
    rows = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        if re.match(r'^\|[\s\-:|]+\|$', s):
            continue  # separator
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    return rows

def parse_works(body):
    """从作品鉴赏表格提取 (曲名, 作者/来源, 体裁)。"""
    works = []
    for cells in parse_table(body):
        # 去掉空 cell
        cs = [c for c in cells if c]
        if len(cs) < 2:
            continue
        # 跳过表头
        if cs[0] in ("节", "曲名", "书名") or (len(cs) >= 2 and cs[1] in ("作者/来源", "作者·来源")):
            continue
        # 判断哪格是曲名：含《》或较短且不含'词/曲/民歌'
        name = cs[0]
        rest = cs[1:]
        author = rest[0] if rest else ""
        genre = rest[1] if len(rest) > 1 else ""
        # 若第一格像"第一节"标签，则曲名取第二格
        if re.match(r'^第[一二三四五六七八九十]+节', name):
            if len(cs) >= 3:
                name = cs[1]; author = cs[2]; genre = cs[3] if len(cs) > 3 else ""
            else:
                continue
        if not name:
            continue
        works.append({"name": name, "author": author, "genre": genre})
    return works

def extract_works_tables(md):
    """扫描全章所有含「曲名」表头的 markdown 表格，合并为作品列表。
    兼容两种布局：上篇有 `## 作品鉴赏…` 标题；下篇只在正文里写
    `**本单元【作品鉴赏】全部曲目：**` + 表格（无独立标题）。"""
    lines = md.splitlines()
    works = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|") and "曲名" in s:
            rows = []
            j = i + 1
            if j < len(lines) and re.match(r'^\|[\s\-:|]+\|$', lines[j].strip()):
                j += 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(lines[j]); j += 1
            works += parse_works("\n".join(rows))
            i = j
        else:
            i += 1
    seen, out = set(), []
    for w in works:
        if w["name"] and w["name"] not in seen:
            seen.add(w["name"]); out.append(w)
    return out

# ---------- 解析各章 ----------
units = []
all_defs = []  # (term, def) 全局池，用于干扰项
chapter_files = sorted(os.listdir(os.path.join(SKILL, "chapters")))
for fn in chapter_files:
    if not fn.endswith(".md"):
        continue
    prefix = fn.split("-")[0]
    md = read(os.path.join(SKILL, "chapters", fn))
    title, blocks = split_sections(md)
    group = GROUP_BY_PREFIX.get(prefix, "上篇")
    frameworks = parse_term_bullets(blocks.get("Frameworks Introduced", ""))
    concepts = parse_term_bullets(blocks.get("Key Concepts", ""))
    mental = parse_simple_bullets(blocks.get("Mental Models", ""))
    anti = parse_term_bullets(blocks.get("Anti-patterns", ""))  # (mistake, why)
    takeaways = parse_simple_bullets(blocks.get("Key Takeaways", ""))
    worked = blocks.get("Worked Example", "")
    core = blocks.get("Core Idea", "")
    works = extract_works_tables(md)

    concept_pool = frameworks + concepts
    for t, d, _ in concept_pool:
        all_defs.append((t, d))

    units.append({
        "id": prefix,
        "title": title,
        "group": group,
        "core": core,
        "frameworks": [{"term": t, "def": d, "detail": dt} for t, d, dt in frameworks],
        "concepts": [{"term": t, "def": d} for t, d, _ in concepts],
        "mental": mental,
        "anti": [{"mistake": t, "why": d} for t, d, _ in anti],
        "worked": worked,
        "takeaways": takeaways,
        "works": works,
    })

# ---------- 生成练习题 ----------
random.seed(20260921)

def dedup_terms(pairs):
    """按术语去重，保留首次出现（frameworks 与 concepts 常撞名，
    不去重会让 random.sample 抽到同一术语出两道一模一样的题）。"""
    out, seen = [], set()
    for t, d in pairs:
        if t in seen:
            continue
        seen.add(t)
        out.append((t, d))
    return out

def make_def_quiz(unit, n=6):
    pool = dedup_terms(
        [(f["term"], f["def"]) for f in unit["frameworks"]]
        + [(c["term"], c["def"]) for c in unit["concepts"]]
    )
    if len(pool) < 2:
        return []
    chosen = random.sample(pool, min(n, len(pool)))
    qs = []
    for term, correct in chosen:
        # 干扰项按「释义」去重，避免同一题里出现两个字面相同的选项
        distract = []
        for t, d in pool:
            if t == term or d in distract or d == correct:
                continue
            distract.append(d)
        random.shuffle(distract)
        opts = [correct] + distract[:3]
        random.shuffle(opts)
        assert len(set(opts)) == len(opts), f"{unit['id']} 「{term}」选项重复"
        qs.append({
            "type": "choice",
            "q": f"下列关于「{term}」的表述，正确的是？",
            "options": opts,
            "answer": opts.index(correct),
            "explain": correct,
        })
    return qs

def make_work_quiz(unit, n=3):
    qs = []
    works = [w for w in unit["works"] if w["author"]]
    for w in works[:n]:
        # 作者题：干扰作者池同样要按文本去重（如 ch09 两部作品作者都写"古曲"）
        pool_auth = []
        for x in unit["works"]:
            a = x["author"]
            if a and a != w["author"] and a not in pool_auth:
                pool_auth.append(a)
        if len(pool_auth) >= 1:
            opts = [w["author"]] + random.sample(pool_auth, min(3, len(pool_auth)))
            random.shuffle(opts)
            assert len(set(opts)) == len(opts), f"{unit['id']} 《{w['name']}》选项重复"
            qs.append({
                "type": "choice",
                "q": f"《{w['name'].strip('《》')}》的作曲/来源是？",
                "options": opts,
                "answer": opts.index(w["author"]),
                "explain": f"《{w['name'].strip('《》')}》— {w['author']}" + (f"，体裁：{w['genre']}" if w["genre"] else ""),
            })
    return qs

_used_judge = set()          # 跨单元已用过的错误做法，避免两个单元出同一道判断题

def make_judge_quiz(unit, n=2):
    """由 Anti-patterns（易错做法）生成判断题。
    注意 anti 的元素是 dict，必须按键取值——直接 `for a, b in anti` 会把
    dict 当元组解包，解出的是键名 "mistake"/"why"（曾导致 38 道题全废）。"""
    items = unit["anti"] or []
    pick = [a for a in items if a["mistake"] not in _used_judge][:n]
    if len(pick) < n:                                  # 本单元新条目不够，用重复项补足
        pick += [a for a in items if a not in pick][: n - len(pick)]
    qs = []
    for k, a in enumerate(pick):
        mistake, why = a["mistake"], a["why"]
        _used_judge.add(mistake)
        if k % 2 == 0:
            # 反问式：把"错误做法"说成正确 → 答案「错误」
            q, ans = f"判断：{mistake}，这是鉴赏时的正确做法。", 1
        else:
            # 正述式：把"应当避免的错误做法"正面陈述 → 答案「正确」
            q, ans = f"判断：鉴赏时应避免{mistake}。", 0
        qs.append({
            "type": "judge",
            "q": q,
            "options": ["正确", "错误"],
            "answer": ans,
            "explain": why,
        })
    return qs

for u in units:
    quiz = []
    quiz += make_def_quiz(u, 6)
    quiz += make_work_quiz(u, 3)
    quiz += make_judge_quiz(u, 2)
    u["quiz"] = quiz

# ---------- 自检：题干/选项不得重复 ----------
def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def audit_quizzes(units):
    problems = []
    for u in units:
        seen = {}
        for i, q in enumerate(u["quiz"]):
            k = _norm(q["q"])
            if k in seen:
                problems.append(f"{u['id']} 题干重复: 第{seen[k]+1}题 == 第{i+1}题")
            seen[k] = i
            opts = [_norm(o) for o in q["options"]]
            if len(set(opts)) != len(opts):
                problems.append(f"{u['id']} 第{i+1}题选项重复: {q['options']}")
            if len(opts) < 2:
                problems.append(f"{u['id']} 第{i+1}题选项不足: {q['options']}")
            if not (0 <= q["answer"] < len(opts)):
                problems.append(f"{u['id']} 第{i+1}题答案越界")
            if not q.get("explain"):
                problems.append(f"{u['id']} 第{i+1}题缺解析")
    # 跨单元
    g = {}
    for u in units:
        for i, q in enumerate(u["quiz"]):
            g.setdefault(_norm(q["q"]), []).append(u["id"])
    for k, ids in g.items():
        if len(set(ids)) > 1:
            problems.append(f"跨单元题干重复: {'/'.join(ids)} | {k}")
    return problems

_problems = audit_quizzes(units)
if _problems:
    print("!! 习题自检发现问题:")
    for p in _problems:
        print("   -", p)
else:
    print("习题自检: 通过（无重复题干 / 无重复选项 / 答案与解析齐全）")

_judge_dist = {}
for u in units:
    for q in u["quiz"]:
        if q["type"] == "judge":
            _judge_dist[q["answer"]] = _judge_dist.get(q["answer"], 0) + 1
print("判断题答案分布:", {("错误" if k == 1 else "正确"): v for k, v in sorted(_judge_dist.items())})

# ---------- markdown -> html（用于速查表） ----------
def md_to_html(md):
    out = []
    table = []
    def flush():
        if table:
            out.append("<table>" + "".join(table) + "</table>")
            table.clear()
    for ln in md.splitlines():
        s = ln.rstrip()
        if s.startswith("# "):
            flush(); out.append(f"<h2>{s[2:].strip()}</h2>")
        elif s.startswith("## "):
            flush(); out.append(f"<h3>{s[3:].strip()}</h3>")
        elif s.startswith("> "):
            flush(); out.append(f"<p class='note'>{s[2:].strip()}</p>")
        elif s.startswith("|"):
            if re.match(r'^\|[\s\-:|]+\|$', s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            tag = "th" if not table else "td"
            row = "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
            table.append(row)
        elif s.strip() == "":
            flush()
        else:
            flush(); out.append(f"<p>{s.strip()}</p>")
    flush()
    return "\n".join(out)

# ---------- 解析 glossary / cheatsheet ----------
glossary = []
for ln in read(os.path.join(SKILL, "glossary.md")).splitlines():
    m = re.match(r'\*\*(.+?)\*\*[\s—-]+(.*)$', ln.strip())
    if m:
        glossary.append({"term": m.group(1).strip(), "def": m.group(2).strip()})

cheatsheet_html = md_to_html(read(os.path.join(SKILL, "cheatsheet.md")))

def md_to_html(md):
    out = []
    table = []
    def flush():
        if table:
            out.append("<table>" + "".join(table) + "</table>")
            table.clear()
    for ln in md.splitlines():
        s = ln.rstrip()
        if s.startswith("# "):
            flush(); out.append(f"<h2>{s[2:].strip()}</h2>")
        elif s.startswith("## "):
            flush(); out.append(f"<h3>{s[3:].strip()}</h3>")
        elif s.startswith("> "):
            flush(); out.append(f"<p class='note'>{s[2:].strip()}</p>")
        elif s.startswith("|"):
            if re.match(r'^\|[\s\-:|]+\|$', s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            tag = "th" if not table else "td"
            row = "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
            table.append(row)
        elif s.strip() == "":
            flush()
        else:
            flush(); out.append(f"<p>{s.strip()}</p>")
    flush()
    return "\n".join(out)

def md_to_html(md):
    out = []
    table = []
    def flush():
        if table:
            out.append("<table>" + "".join(table) + "</table>")
            table.clear()
    for ln in md.splitlines():
        s = ln.rstrip()
        if s.startswith("# "):
            flush(); out.append(f"<h2>{s[2:].strip()}</h2>")
        elif s.startswith("## "):
            flush(); out.append(f"<h3>{s[3:].strip()}</h3>")
        elif s.startswith("> "):
            flush(); out.append(f"<p class='note'>{s[2:].strip()}</p>")
        elif s.startswith("|"):
            if re.match(r'^\|[\s\-:|]+\|$', s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            tag = "th" if not table else "td"
            row = "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
            table.append(row)
        elif s.strip() == "":
            flush()
        else:
            flush(); out.append(f"<p>{s.strip()}</p>")
    flush()
    return "\n".join(out)

data = {
    "book": "普通高中教科书·音乐·必修·音乐鉴赏（人音版 2019）",
    "units": units,
    "glossary": glossary,
    "cheatsheet": cheatsheet_html,
}

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// 自动生成，请勿手改；重新运行 generate_data.py 可刷新\n")
    f.write("window.COURSE_DATA = ")
    json.dump(data, f, ensure_ascii=False, indent=1)
    f.write(";\n")

print("units:", len(units))
print("glossary:", len(glossary))
tot_q = sum(len(u["quiz"]) for u in units)
print("total quiz questions:", tot_q)
for u in units:
    print(f"  {u['id']} {u['title'][:24]:24} 概念{len(u['concepts'])+len(u['frameworks'])} 作品{len(u['works'])} 题{len(u['quiz'])}")
