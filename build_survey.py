# -*- coding: utf-8 -*-
"""生成「补充资料投稿」腾讯问卷的纯文本定义。

用途：腾讯问卷 MCP 的 create_survey 接收一段纯文本 DSL。
本脚本按 data.js 的真实单元/作品结构生成这段 DSL，避免手写出错。

用法：
    python3 build_survey.py              # 生成两种版本（默认）
    python3 build_survey.py --mode linked    # 只生成「单元+课程」联动题版
    python3 build_survey.py --mode twodropdown  # 只生成两个下拉题的兜底版

产物：
    survey_text_linked.txt      —— 单元+课程 用「联动题」（推荐，选完单元课程自动过滤）
    survey_text_twodropdown.txt —— 退化为两个独立下拉题（联动题若不被接受就用这份）
    unit_index.json             —— 单元标签 → chXX 映射（由 course_meta 生成，回填脚本共用）
"""
import argparse
import os

from course_meta import PLACEHOLDER, build_index, load_course, unit_label, work_label

ROOT = os.path.dirname(os.path.abspath(__file__))

TITLE = "《音乐鉴赏》补充资料投稿"
INTRO = (
    "本表用于向「人音版必修《音乐鉴赏》互动课堂」（河北峰峰第一中学）投稿补充材料。"
    "请先选择资料对应的【单元】和【课次】，再选择【材料类型】，然后上传文件或粘贴网盘分享链接。"
    "经审核后会展示在对应单元的「补充资料区」，供全组老师上课使用。"
)


def survey_text(mode="linked"):
    D = load_course()
    units = D["units"]
    lines = [TITLE, "", INTRO, ""]

    if mode == "linked":
        lines.append("您投稿的资料属于哪个单元、哪一课？[联动题][必答]")
        lines.append("单元 课程")
        for u in units:
            label = unit_label(u)
            lines.append(f"{label}+{PLACEHOLDER}")
            for w in u.get("works", []):
                lines.append(f"{label}+{work_label(w)}")
        lines.append("其他+跨单元 / 综合资料")
    else:
        lines.append("您投稿的资料属于哪个单元？[下拉题][必答]")
        for u in units:
            lines.append(unit_label(u))
        lines.append("其他（跨单元 / 综合资料）")
        lines.append("")
        lines.append("对应哪一课或哪首作品？（选填，可写作品名）[单行文本题]")

    lines.append("")
    lines.append("资料名称（标题）[单行文本题][必答]")
    lines.append("")
    lines.append("材料类型[单选题][必答]")
    lines.append("音频")
    lines.append("视频")
    lines.append("PPT / 课件")
    lines.append("文本 / 文档")
    lines.append("")
    lines.append("上传资料文件（音频、视频、PPT、文本均可）[附件题]")
    lines.append("")
    lines.append("文件太大不便上传？可粘贴微云／网盘分享链接（选填）[单行文本题]")
    lines.append("")
    lines.append("补充说明：来源、时长、版本、推荐用法等（选填）[多行文本题]")
    lines.append("")
    lines.append("投稿人姓名或称呼（选填）[单行文本题]")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["linked", "twodropdown", "both"], default="both")
    a = ap.parse_args()

    build_index()  # 顺带刷新 unit_index.json

    modes = ["linked", "twodropdown"] if a.mode == "both" else [a.mode]
    for m in modes:
        text = survey_text(m)
        path = os.path.join(ROOT, f"survey_text_{m}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        qs = [l for l in text.splitlines() if l.strip().endswith("]") or "[" in l and "]" in l]
        print(f"[{m}] {path}  行数={len(text.splitlines())}  含题型标记的行={len(qs)}")
        for l in qs:
            print("    · " + l.strip())


if __name__ == "__main__":
    main()
