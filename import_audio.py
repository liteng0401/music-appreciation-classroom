#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从课本 U 盘(WAV)映射并转换音频到人音版《音乐鉴赏》网页。

流程：
  1. 扫描 U 盘 WAV 列表
  2. 按曲名模糊匹配到 data.js 的每首作品（只匹配网页列出来的曲子）
  3. 仅把匹配到的 WAV 用系统 afconvert 转成 AAC(.m4a)，存入 audio/<unit>/
  4. 生成 audio.js（window.AUDIO_MAP）："单元id|曲名" -> "audio/<unit>/<文件>.m4a"

用法：
  python3 import_audio.py --src "<U盘 NLLastF 目录>" [--dry] [--bitrate 192000]
  --dry        只打印匹配结果，不转换、不写文件（用来先核对）
  --bitrate    输出 AAC 码率(bps)，默认 192000；想更小可设 128000
"""
import os, re, json, sys, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data.js")
OUT  = os.path.join(ROOT, "audio.js")
AUDIO_DIR = os.path.join(ROOT, "audio")
SRC = None
DRY = "--dry" in sys.argv
BITRATE = 192000
if "--bitrate" in sys.argv:
    BITRATE = int(sys.argv[sys.argv.index("--bitrate") + 1])
if "--src" in sys.argv:
    SRC = sys.argv[sys.argv.index("--src") + 1]

# 自动匹配漏掉时的手工兜底："单元id|曲名" -> 源文件名中的关键片段
OVERRIDE = {
    "ch04|忽听得万岁宣包拯": "万岁宣包拯",
    "ch04|看大王在帐中和衣睡稳": "看大王在",
    "ch13|《费加罗的婚礼》序曲": "85.序曲",
}

def norm(s):
    # 只保留 小写字母/数字/中日韩统一表意文字，其余（书名号、引号、括号、标点、空白）全去掉
    s = (s or "").lower()
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]', '', s)

def load_data():
    t = open(DATA, encoding="utf-8").read().split("=", 1)[1].strip()
    if t.endswith(";"):
        t = t[:-1]
    return json.loads(t)

def load_wavs(src):
    out = []
    for root, _, fs in os.walk(src):
        for f in fs:
            if f.lower().endswith(".wav"):
                out.append(os.path.join(root, f))
    return out

def core_of(workname):
    # 取主曲名：去掉 （选自…）/（片段）等括号注释
    n = re.sub(r'（[^（）]*）', '', workname)
    n = re.sub(r'\([^()]*\)', '', n)
    return norm(n)

def score(base, wk):
    if not base or not wk:
        return 0
    if base == wk:
        return 100
    if wk in base:
        return 96
    if base in wk:
        return 92
    def bg(x):
        return set(x[i:i+2] for i in range(len(x)-1)) if len(x) > 1 else set([x])
    b1, b2 = bg(base), bg(wk)
    if not b1 or not b2:
        return 0
    return round(55 * len(b1 & b2) / len(b1 | b2), 1)

def main():
    data = load_data()
    wavs = load_wavs(SRC) if SRC else []
    wav_info = [(os.path.basename(w)[:-4], w) for w in wavs]
    mapping = {}
    used = set()
    unmatched = []
    for u in data["units"]:
        for w in u["works"]:
            key = u["id"] + "|" + w["name"]
            wk = core_of(w["name"])
            best = None
            bestf = None
            if key in OVERRIDE:
                sub = OVERRIDE[key]
                for fn, path in wav_info:
                    if path not in used and sub in fn:
                        bestf = (fn, path)
                        break
            else:
                for fn, path in wav_info:
                    if path in used:
                        continue
                    base = norm(fn)
                    sc = score(base, wk)
                    if sc >= 70 and (best is None or sc > best):
                        best = sc
                        bestf = (fn, path)
            if bestf:
                mapping[key] = bestf
                used.add(bestf[1])
            else:
                unmatched.append((u["id"], w["name"]))
    print(f"扫描 WAV：{len(wavs)} 个")
    print(f"匹配作品：{len(mapping)} 个；未匹配：{len(unmatched)} 个")
    for k, (fn, _) in mapping.items():
        print(f"  [匹配] {k}  <-  {fn}.wav")
    for uid, name in unmatched:
        print(f"  [未匹配] {uid} 《{name}》")
    if DRY:
        return
    # 真正转换
    os.makedirs(AUDIO_DIR, exist_ok=True)
    aud_map = {}
    for key, (fn, path) in mapping.items():
        unit = key.split("|")[0]
        safe = re.sub(r'[\\/:*?"<>|（）()\s]', '_', fn)
        outdir = os.path.join(AUDIO_DIR, unit)
        os.makedirs(outdir, exist_ok=True)
        outp = os.path.join(outdir, safe + ".m4a")
        rel = os.path.relpath(outp, ROOT).replace("\\", "/")
        if not os.path.exists(outp):
            r = subprocess.run(
                ["afconvert", "-f", "m4af", "-d", "aac", "-b", str(BITRATE), path, outp],
                capture_output=True, text=True)
            if r.returncode != 0:
                print("转换失败:", fn, r.stderr[:200])
                continue
        aud_map[key] = rel
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// 自动生成：python3 import_audio.py --src <U盘路径>\n")
        f.write("window.AUDIO_MAP = ")
        json.dump(aud_map, f, ensure_ascii=False, indent=1)
        f.write(";\n")
    print("已写入", OUT, "映射", len(aud_map), "条")

if __name__ == "__main__":
    main()
