#!/usr/bin/env python3
"""Публікує особистий репозиторій модів VCMI на GitHub.

Що робить:
  1. для кожної папки mods/<id>/ (крім тих, що починаються з «_») пакує мод у dist/<id>.zip;
  2. якщо вміст мода змінився, а версія в mod.json та сама — автоматично піднімає останню цифру версії
     (щоб лаунчери на всіх пристроях побачили «є оновлення»);
  3. генерує індекс vcmi-repo.json у форматі репозиторію VCMI;
  4. робить git commit і push.

У кожному лаунчері (Mac / Windows / Android) один раз вкажи в Налаштуваннях → «Додатковий репозиторій»:
    https://raw.githubusercontent.com/<github_user>/<repo>/<branch>/vcmi-repo.json

Запуск:  python3 publish.py            (або з «--no-push», щоб лише зібрати локально)
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
MODS = ROOT / "mods"
DIST = ROOT / "dist"
STATE = ROOT / ".state.json"   # хеші вмісту модів, щоб знати, що змінилося


def lenient(t):
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return json.loads(t, strict=False)


def content_hash(moddir):
    h = hashlib.sha1()
    for p in sorted(moddir.rglob("*")):
        if p.is_file() and p.name != ".DS_Store":
            rel = p.relative_to(moddir).as_posix()
            data = p.read_bytes()
            if rel == "mod.json":  # версію не враховуємо, інакше хеш міняється від самого підняття версії
                data = re.sub(rb'"version"\s*:\s*"[^"]*"', b'"version":""', data)
            h.update(rel.encode() + b"\0" + data)
    return h.hexdigest()


def bump(version):
    parts = version.split(".")
    parts[-1] = str(int(re.sub(r"\D", "", parts[-1]) or 0) + 1)
    return ".".join(parts)


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    user, repo, branch = cfg["github_user"], cfg["repo"], cfg["branch"]
    if not user:
        sys.exit("Заповни github_user у config.json")
    raw = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}"
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    DIST.mkdir(exist_ok=True)
    index, changed = {}, []

    for moddir in sorted(p for p in MODS.iterdir() if p.is_dir() and not p.name.startswith("_")):
        mid = moddir.name.lower()
        mj_path = moddir / "mod.json"
        text = mj_path.read_text(encoding="utf-8-sig")
        mj = lenient(text)
        h = content_hash(moddir)
        old = state.get(mid, {})
        ver = mj.get("version", "1.0.0")
        if old and old.get("hash") != h and old.get("version") == ver:
            ver = bump(ver)
            text = re.sub(r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{ver}\g<2>", text, count=1)
            mj_path.write_text(text, encoding="utf-8")
            print(f"  {mid}: вміст змінився → версія {ver}")
        if old.get("hash") != h or old.get("version") != ver:
            changed.append(f"{mid} {ver}")
        state[mid] = {"hash": h, "version": ver}

        z = DIST / f"{mid}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(moddir.rglob("*")):
                if p.is_file() and p.name != ".DS_Store":
                    zf.write(p, f"{mid}/{p.relative_to(moddir).as_posix()}")
        shots = sorted((moddir / "screenshots").glob("*.png")) if (moddir / "screenshots").exists() else []
        index[mid] = {
            "mod": f"{raw}/mods/{moddir.name}/mod.json",
            "download": f"{raw}/dist/{mid}.zip",
            "downloadSize": round(z.stat().st_size / 1024 / 1024, 3),
            "screenshots": [f"{raw}/mods/{moddir.name}/screenshots/{s.name}" for s in shots],
        }

    (ROOT / "vcmi-repo.json").write_text(json.dumps({"availableMods": index}, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE.write_text(json.dumps(state, indent=1))
    print(f"Модів у репозиторії: {len(index)}; змінено: {', '.join(changed) or 'нічого'}")

    if "--no-push" in sys.argv:
        return
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        print("Змін для публікації немає.")
        return
    msg = "Оновлення модів: " + (", ".join(changed) or "індекс")
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)
    print("\nОпубліковано. На кожному пристрої: лаунчер → «Обновити репозиторії» → оновити моди.")


if __name__ == "__main__":
    main()
