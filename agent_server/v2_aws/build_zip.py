"""AgentCore Runtime 用の zip を作る（Windows / Mac / Linux 共通）。
リポジトリのルートで：  python v2_aws/build_zip.py
"""
import os, shutil, subprocess, sys, zipfile

OUT = "build_agentcore"
PKG = os.path.join(OUT, "pkg")
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(PKG)
reqs = [l for l in open("v2_aws/requirements.txt", encoding="utf-8") if "colorama" not in l]
open(os.path.join(OUT, "req.txt"), "w", encoding="utf-8").writelines(reqs)
subprocess.run([sys.executable, "-m", "uv", "pip", "install", "--python-platform", "aarch64-manylinux2014",
                "--python-version", "3.12", "--target", PKG, "--only-binary=:all:",
                "-r", os.path.join(OUT, "req.txt")], check=True)
shutil.copy("v2_aws/app.py", os.path.join(PKG, "app.py"))
shutil.copytree("core", os.path.join(PKG, "core"), ignore=shutil.ignore_patterns("__pycache__"))
zpath = os.path.join(OUT, "deployment_package.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            full = os.path.join(root, f)
            zi = zipfile.ZipInfo.from_file(full, os.path.relpath(full, PKG).replace(os.sep, "/"))
            zi.external_attr = 0o644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as fh:
                z.writestr(zi, fh.read())
print(f"できた：{zpath}  {os.path.getsize(zpath)/1e6:.0f}MB（上限 250MB）")