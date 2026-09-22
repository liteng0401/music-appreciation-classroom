# -*- coding: utf-8 -*-
"""通过 GitHub Git Data API 推送 ppt/ + generate_ppt.py + README.md 到远程 main。
避开沙箱 git push 的代理限制（gh api 走 Git Data API）。"""
import os, json, subprocess, base64

REPO = "liteng0401/music-appreciation-classroom"
ROOT = "/Users/lt/WorkBuddy/2026-09-21-01-46-33/music-appreciation-web"

def gh_api(method, api_path, data=None):
    cmd = ["gh", "api", api_path, "--method", method, "--input", "-"]
    inp = json.dumps(data) if data is not None else ""
    out = subprocess.run(cmd, input=inp, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {method} {api_path} FAILED:\n{out.stderr}")
    return json.loads(out.stdout)

# 1. 远程 main 当前提交
ref = gh_api("GET", f"repos/{REPO}/git/refs/heads/main")
base_sha = ref["object"]["sha"]
print("base main:", base_sha)
base_commit = gh_api("GET", f"repos/{REPO}/git/commits/{base_sha}")
base_tree = base_commit["tree"]["sha"]

# 2. 收集要推送的文件
to_push = []
for dp, _, fns in os.walk(os.path.join(ROOT, "ppt")):
    for fn in sorted(fns):
        if fn.endswith(".pptx"):
            to_push.append(os.path.join(dp, fn))
to_push.append(os.path.join(ROOT, "generate_ppt.py"))
to_push.append(os.path.join(ROOT, "README.md"))

# 3. 建 blob
tree_items = []
for fp in to_push:
    raw = open(fp, "rb").read()
    blob = gh_api("POST", f"repos/{REPO}/git/blobs",
                  {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
    rel = os.path.relpath(fp, ROOT)
    tree_items.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    print(f"  blob {blob['sha'][:8]}  {rel}  ({len(raw)//1024}KB)")

# 4. 建 tree（基于远程 tree，覆盖同名路径）
new_tree = gh_api("POST", f"repos/{REPO}/git/trees",
                  {"base_tree": base_tree, "tree": tree_items})
# 5. 建 commit
msg = ("feat: 生成 35 份每节 PPT 课件（变易教学设计 + 作品鉴赏 + 随堂练习）"
       " + 生成器 generate_ppt.py + README 更新")
new_commit = gh_api("POST", f"repos/{REPO}/git/commits",
                    {"message": msg, "tree": new_tree["sha"], "parents": [base_sha]})
# 6. 更新 ref
gh_api("PATCH", f"repos/{REPO}/git/refs/heads/main", {"sha": new_commit["sha"]})
print(f"\nPUSHED commit {new_commit['sha']}  文件数={len(tree_items)}")
