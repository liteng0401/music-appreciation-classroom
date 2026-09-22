#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「人音版 素材」的 音频MP3 / PPT课件 / 教案 对应到网页各单元，并生成 resources.js。
用法：
  python3 import_resources.py --dry     # 只打印对应关系与缺口（默认）
  python3 import_resources.py           # 真正拷贝文件 + 生成 resources.js + audio.js
配置：见下方 SRC_* ；源目录默认取桌面「人音版 素材」。
"""
import os, re, json, sys, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.expanduser("~/Desktop")
BASE = os.path.join(DESK, "人音版 素材")
SRC_MP3  = os.path.join(BASE, "2019版 高中 音乐 人音版 必修 音频mp3")
SRC_PPT  = os.path.join(BASE, "01音乐人音版高中必修 音乐鉴赏 课件PPT 54（2020年）")
SRC_JIAO = os.path.join(BASE, "0010音乐人音版高中必修 音乐鉴赏 教案word2019")

DATA = os.path.join(ROOT, "data.js")
AUDIO_DIR = os.path.join(ROOT, "audio")
PPT_DIR   = os.path.join(ROOT, "media", "ppt")
JIAO_DIR  = os.path.join(ROOT, "media", "jiaoan")
AUDIO_JS  = os.path.join(ROOT, "audio.js")
RES_JS    = os.path.join(ROOT, "resources.js")
EXTRA_JS  = os.path.join(ROOT, "audio_extra.js")
PPT_URLS  = os.path.join(ROOT, "ppt_urls.json")   # publish_ppt.py 生成：附件名 + Release 下载链接

DRY = "--dry" in sys.argv

# ---------- 复用语在 import_audio.py 里的匹配逻辑 ----------
sys.path.insert(0, ROOT)
import import_audio as A

# ---------- PPT / 教案 → 单元 关键词表（按顺序，先具体后笼统）----------
UNIT_KEYWORDS = [
    ("ch00", ["序篇", "不忘初心", "音乐与人生"]),
    ("ch01", ["音乐要素及音乐语言", "音乐情感及情绪", "要素及音乐语言", "情感及情绪"]),
    ("ch02", ["汉族民歌", "独特的民族风", "民歌"]),
    ("ch03", ["丝竹相和", "鼓乐铿锵", "地花鼓"]),
    ("ch04", ["京剧", "唱脸谱", "四大行当", "脸谱"]),
    ("ch05", ["合唱曲", "独唱曲", "歌曲"]),
    ("ch06", ["中国影视音乐", "外国影视音乐", "影视"]),
    ("ch07", ["中国舞蹈音乐", "外国舞蹈音乐", "舞蹈"]),
    ("ch08", ["亚洲与非洲音乐", "欧洲与拉丁美洲音乐", "非洲音乐", "拉丁美洲"]),
    ("ch09", ["高山流水志家国", "西出阳关无故人"]),
    ("ch10", ["学堂乐歌", "人民音乐家", "沈心工", "李叔同", "聂耳", "冼星海", "金蛇狂舞"]),
    ("ch11", ["峥嵘岁月", "共筑中国梦"]),
    ("ch12", ["巴赫"]),
    ("ch13", ["莫扎特", "贝多芬"]),
    ("ch14", ["舒伯特", "艺术歌曲的成熟", "肖邦", "柏辽兹", "威尔第", "鳟鱼"]),
    ("ch15", ["斯美塔那", "西贝柳斯", "格林卡", "穆索尔斯基"]),
    ("ch16", ["德彪西"]),
    ("ch17", ["勋伯格"]),
    ("ch18", ["流行精粹", "爵士"]),
]

def fullname_ok(fn):
    return not fn.startswith("._") and not fn.startswith(".")

def match_unit(fn):
    base = fn.rsplit(".", 1)[0]
    for uid, kws in UNIT_KEYWORDS:
        for kw in kws:
            if kw in base:
                return uid
    return None

def safe(fn):
    stem, ext = os.path.splitext(fn)
    stem = re.sub(r'[\\/:*?"<>|（）()\s]', '_', stem)
    return stem + ext

def load_data():
    t = open(DATA, encoding="utf-8").read().split("=", 1)[1].strip().rstrip(";")
    return json.loads(t)

def scan(d):
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if fullname_ok(f) and os.path.isfile(os.path.join(d, f)):
                out.append(f)
    return out

def main():
    data = load_data()
    ppt_urls = {}
    if os.path.exists(PPT_URLS):
        ppt_urls = json.load(open(PPT_URLS, encoding="utf-8"))
        print(f"已读取 {PPT_URLS}（{len(ppt_urls)} 条 PPT 下载链接）")
    # --------- 1) MP3 → 作品 ---------
    mp3s = scan(SRC_MP3)
    wav_info = [(f, os.path.join(SRC_MP3, f)) for f in mp3s]  # (完整文件名, 路径)
    audio_map = {}   # "unit|work" -> 完整文件名
    used = set()
    unmatched_works = []
    for u in data["units"]:
        for w in u["works"]:
            key = u["id"] + "|" + w["name"]
            bestf = None
            if key in A.OVERRIDE:
                for fn, p in wav_info:
                    if p not in used and A.OVERRIDE[key] in fn:
                        bestf = (fn, p); break
            else:
                wk = A.core_of(w["name"]); best = None
                for fn, p in wav_info:
                    if p in used: continue
                    sc = A.score(A.norm(os.path.splitext(fn)[0]), wk)
                    if sc >= 70 and (best is None or sc > best):
                        best = sc; bestf = (fn, p)
            if bestf:
                audio_map[key] = bestf[0]; used.add(bestf[1])
            else:
                unmatched_works.append((u["id"], w["name"], w.get("author", ""), w.get("genre", "")))
    unmatched_mp3 = [f for f in mp3s if os.path.join(SRC_MP3, f) not in used]

    # --------- 1b) 未被正文作品占用的 MP3 → 按编号就近归入单元（拓展与探究·课外聆听）----------
    def num_of(fn):
        m = re.match(r"^(\d+)\.", fn)
        return int(m.group(1)) if m else None
    units_order = [u["id"] for u in data["units"]]
    unit_max = {}
    for key, fn in audio_map.items():
        n = num_of(fn)
        if n:
            uid = key.split("|", 1)[0]
            unit_max[uid] = max(unit_max.get(uid, 0), n)
    extra_map = {}   # unit -> [(完整文件名, 展示名)]
    for f in sorted(unmatched_mp3, key=lambda x: (num_of(x) or 9999, x)):
        n = num_of(f)
        if n is None:
            continue
        owner = None
        for uid in units_order:          # 取"最后一个已结束的单元"= 编号最大的 min<=n 的单元
            if unit_max.get(uid) and unit_max[uid] <= n:
                owner = uid
        if owner is None:
            owner = units_order[0]
        unit_max[owner] = n
        stem = os.path.splitext(f)[0]
        disp = re.sub(r'^\d+\.', '', stem)
        disp = re.sub(r'^拓展与探究\d*\.', '', disp) or stem
        extra_map.setdefault(owner, []).append((f, disp))

    # --------- 2) PPT / 教案 → 单元 ---------
    ppts = scan(SRC_PPT); jiaos = scan(SRC_JIAO)
    ppt_map, jiao_map = {}, {}
    for f in ppts:
        uid = match_unit(f)
        (ppt_map.setdefault(uid, []) if uid else ppt_map.setdefault("__none__", [])).append(f)
    for f in jiaos:
        uid = match_unit(f)
        (jiao_map.setdefault(uid, []) if uid else jiao_map.setdefault("__none__", [])).append(f)

    # --------- 报告 ---------
    print("== MP3 → 作品 ==")
    print(f"  MP3 文件 {len(mp3s)} 个；匹配到作品 {len(audio_map)} 条；未匹配作品 {len(unmatched_works)} 条；未用上的 MP3 {len(unmatched_mp3)} 个")
    for uid, name, au, ge in unmatched_works:
        print(f"   [缺音频] {uid} 《{name}》 {au} {ge}")
    if unmatched_mp3:
        print("   剩余 MP3 归入「拓展聆听」：")
        for uid in units_order:
            for fn, disp in extra_map.get(uid, []):
                print(f"     {uid} <- {fn}   （显示为：{disp}）")
        left = [f for f in unmatched_mp3 if num_of(f) is None]
        for f in left:
            print("     [丢弃·无编号]", f)
    print()
    print("== PPT / 教案 → 单元 ==")
    print(f"  {'单元':5} {'音频(作品)':10} {'PPT':4} {'教案':4}   PPT文件 / 教案文件")
    for u in data["units"]:
        uid = u["id"]
        na = sum(1 for k in audio_map if k.startswith(uid + "|"))
        pl = ppt_map.get(uid, []); jl = jiao_map.get(uid, [])
        print(f"  {uid:5} {na:<10} {len(pl):<4} {len(jl):<4}")
        for f in pl: print(f"          PPT  : {f}")
        for f in jl: print(f"          教案 : {f}")
    print()
    if ppt_map.get("__none__"):
        print("  ⚠ PPT 未对应上任何单元：")
        for f in ppt_map["__none__"]: print("     -", f)
    if jiao_map.get("__none__"):
        print("  ⚠ 教案未对应上任何单元：")
        for f in jiao_map["__none__"]: print("     -", f)

    if DRY:
        return

    # --------- 3) 拷贝 + 生成 js ---------
    aud_out = {}
    for key, fn in audio_map.items():
        unit = key.split("|")[0]
        outdir = os.path.join(AUDIO_DIR, unit); os.makedirs(outdir, exist_ok=True)
        dst = os.path.join(outdir, safe(fn))
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(SRC_MP3, fn), dst)
        aud_out[key] = os.path.relpath(dst, ROOT).replace("\\", "/")
    # --------- 3b) 拓展聆听音频 ---------
    extra_out = {}
    for uid, items in extra_map.items():
        outdir = os.path.join(AUDIO_DIR, uid); os.makedirs(outdir, exist_ok=True)
        for fn, disp in items:
            dst = os.path.join(outdir, safe(fn))
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(SRC_MP3, fn), dst)
            extra_out.setdefault(uid, []).append(
                {"name": disp, "path": os.path.relpath(dst, ROOT).replace("\\", "/")})
    res = {}
    for src, sub, mp in [(SRC_PPT, PPT_DIR, ppt_map), (SRC_JIAO, JIAO_DIR, jiao_map)]:
        for uid, files in mp.items():
            if uid == "__none__": continue
            for f in files:
                outdir = os.path.join(sub, uid); os.makedirs(outdir, exist_ok=True)
                dst = os.path.join(outdir, safe(f))
                if not os.path.exists(dst):
                    shutil.copy2(os.path.join(src, f), dst)
                kind = "ppt" if sub == PPT_DIR else "jiaoan"
                disp = os.path.splitext(f)[0]
                rel = os.path.relpath(dst, ROOT).replace("\\", "/")
                ent = {"name": disp, "file": f, "path": rel, "size": os.path.getsize(dst)}
                if kind == "ppt":
                    info = ppt_urls.get(f"{uid}/{f}")
                    if info:                      # PPT 走 Release 附件下载（原始画质）
                        ent["asset"] = info["asset"]
                        ent["url"] = info["url"]
                res.setdefault(uid, {"ppt": [], "jiaoan": []})[kind].append(ent)
    with open(AUDIO_JS, "w", encoding="utf-8") as fp:
        fp.write("// 自动生成：import_resources.py\nwindow.AUDIO_MAP = ")
        json.dump(aud_out, fp, ensure_ascii=False, indent=1); fp.write(";\n")
    with open(RES_JS, "w", encoding="utf-8") as fp:
        fp.write("// 自动生成：import_resources.py\nwindow.RESOURCES = ")
        json.dump(res, fp, ensure_ascii=False, indent=1); fp.write(";\n")
    with open(EXTRA_JS, "w", encoding="utf-8") as fp:
        fp.write("// 自动生成：import_resources.py\nwindow.AUDIO_EXTRA = ")
        json.dump(extra_out, fp, ensure_ascii=False, indent=1); fp.write(";\n")
    n_ex = sum(len(v) for v in extra_out.values())
    print(f"\n已拷贝音频 {len(aud_out)} 条 + 拓展聆听 {n_ex} 条 -> audio/；资源 -> media/")
    print("生成 audio.js / resources.js / audio_extra.js")

if __name__ == "__main__":
    main()
