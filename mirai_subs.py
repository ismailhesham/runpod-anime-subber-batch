"""Find and fetch ready Arabic subtitle packs from miraianime.net (public pages, no login).

Flow: search the anime by name -> read its /subtitle/<slug>/ page -> list the packs (translator,
episode range, release) -> choose one that covers the episode -> download the zip/7z/rar once ->
extract the file for that episode number. Nothing here translates. The burn step restyles the
file to our visual style, so the translator's words and timing stay as they are.
"""
import html as _html
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

BASE = "https://miraianime.net"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
PREFERRED_TRANSLATORS = ["celestial dragons"]
SUB_EXT = (".ass", ".srt")
ARCHIVE_EXT = (".zip", ".7z", ".rar")


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def search_anime(name: str, limit: int = 8) -> List[Dict[str, str]]:
    """Return [{title, slug}] for an anime name."""
    q = urllib.parse.quote(name.strip())
    data = json.loads(_get(f"{BASE}/wp-json/wp/v2/anime?search={q}&per_page={limit}&_fields=title,slug").decode("utf8"))
    return [{"title": _html.unescape(d["title"]["rendered"]), "slug": d["slug"]} for d in data]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def best_match(name: str, hits: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Exact normalised title first, then the shortest title that contains the name."""
    n = _norm(name)
    for h in hits:
        if _norm(h["title"]) == n or _norm(h["slug"]) == n:
            return h
    contains = [h for h in hits if n and n in _norm(h["title"])]
    return min(contains, key=lambda h: len(h["title"])) if contains else None


def list_packs(slug: str) -> List[Dict]:
    """Packs on /subtitle/<slug>/: translator, first/last episode, release, archive url."""
    page = _get(f"{BASE}/subtitle/{slug}/").decode("utf8", "replace")
    chunks = page.split("معلومات عن الملف")[1:]
    packs = []
    for chunk in chunks:
        row_nums = re.search(r"ارقام الحلقات المتوفرة</th>(.*?)</tr>", chunk, re.S)
        translator = re.search(r"<th>المترجم</th>(.*?)</tr>", chunk, re.S)
        release = re.search(r"الاصدار المتوافق</th>(.*?)</tr>", chunk, re.S)
        # The download button sits after the info table, before the next pack's table.
        link = re.search(r'href=["\'](https?://[^"\']+?\.(?:zip|7z|rar))["\']', chunk, re.I)
        if not (row_nums and link):
            continue
        nums = [int(x) for x in re.findall(r"(\d+)", _text(row_nums.group(1)))]
        if not nums:
            continue
        size = re.search(r"حجم الملف</th>(.*?)</tr>", chunk, re.S)
        size_text = _text(size.group(1)) if size else ""
        size_num = re.search(r"([\d.]+)", size_text)
        size_mb = float(size_num.group(1)) if size_num else 0.0
        if "كيلو" in size_text:
            size_mb /= 1024.0
        elif "جيجا" in size_text:
            size_mb *= 1024.0
        packs.append({
            "size_mb": size_mb,
            "first": nums[0], "last": nums[-1] if len(nums) > 1 else nums[0],
            "translator": _text(translator.group(1)) if translator else "",
            "release": _text(release.group(1)) if release else "",
            "url": _html.unescape(link.group(1)),
        })
    return packs


def release_hint(video_name: str) -> str:
    """BD or WEB guess from the video file name. Timing differs between releases, so match it when we can."""
    n = (video_name or "").lower()
    if re.search(r"\bbd\b|blu-?ray|bdrip|bdmv", n):
        return "BD"
    if re.search(r"\bweb\b|web-?dl|webrip|crunchyroll|\bcr\b|\bnf\b", n):
        return "WEB"
    return ""


def pick_pack(packs: List[Dict], episode: int, release: str = "") -> Optional[Dict]:
    """Covering packs ranked: preferred translator (Celestial Dragons), then the same release as the video
    (BD/WEB), then the smallest download."""
    covering = [p for p in packs if p["first"] <= episode <= p["last"]]
    if not covering:
        return None
    def rank(p):
        pref = 0 if any(w in p["translator"].lower() for w in PREFERRED_TRANSLATORS) else 1
        rel = 0 if (release and release.lower() in p["release"].lower()) else 1
        return (pref, rel, p.get("size_mb", 0.0))
    return sorted(covering, key=rank)[0]


def download_pack(pack: Dict, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = urllib.parse.unquote(pack["url"].rsplit("/", 1)[-1])
    dest = cache_dir / re.sub(r"[^\w.\-]+", "_", name)
    if not dest.is_file() or dest.stat().st_size == 0:
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(_get(pack["url"], timeout=120))
        tmp.replace(dest)
    return dest


def _list_archive(archive: Path) -> List[str]:
    out = subprocess.run(["7z", "l", "-slt", "-ba", str(archive)], capture_output=True, text=True, timeout=60)
    if out.returncode not in (0, 1):
        raise RuntimeError("7z failed: install p7zip-full on the pod")
    return [l[7:] for l in out.stdout.splitlines() if l.startswith("Path = ")]


def episode_number_in_name(name: str) -> Optional[int]:
    """Episode number from a subtitle file name: the last number that is not a year or a resolution."""
    stem = re.sub(r"\.(ass|srt)$", "", Path(name).name, flags=re.I)
    stem = re.sub(r"\[[0-9A-Fa-f]{8}\]", " ", stem)
    stem = re.sub(r"\b(?:480|576|720|1080|2160)p?\b|\b(?:x|h)26[45]\b", " ", stem, flags=re.I)
    stem = re.sub(r"(?<=\d)v\d\b", " ", stem, flags=re.I)
    nums = re.findall(r"(?<![\d.])(\d{1,4})(?![\d.])", stem)
    return int(nums[-1]) if nums else None


def extract_episode(archive: Path, episode: int, out_dir: Path, _depth: int = 0) -> Optional[Path]:
    """Extract only this episode's subtitle file. Returns None if the pack has no file for it."""
    all_names = _list_archive(archive)
    names = [n for n in all_names if n.lower().endswith(SUB_EXT)]
    matches = [n for n in names if episode_number_in_name(n) == episode]
    if not matches:
        nested = [n for n in all_names if n.lower().endswith(ARCHIVE_EXT)]
        if nested and _depth < 1:  # some packs are a zip holding one rar/7z
            inner_dir = out_dir / "_inner"
            shutil.rmtree(inner_dir, ignore_errors=True)
            inner_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["7z", "e", "-y", "-spd", f"-o{inner_dir}", str(archive), nested[0]], capture_output=True, text=True, timeout=300)
            inner = next(iter(inner_dir.glob("*")), None)
            result = extract_episode(inner, episode, out_dir, _depth + 1) if inner else None
            shutil.rmtree(inner_dir, ignore_errors=True)
            return result
        return None
    matches.sort(key=lambda n: (not n.lower().endswith(".ass"), len(n)))  # ASS first
    chosen = matches[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_x"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    r = subprocess.run(["7z", "e", "-y", "-spd", f"-o{tmp}", str(archive), chosen], capture_output=True, text=True, timeout=120)
    got = list(tmp.glob("*"))
    if (r.returncode not in (0, 1) or not got) and shutil.which("unrar") and archive.suffix.lower() == ".rar":
        # p7zip 16 cannot read some RAR5 files; the real unrar can.
        r = subprocess.run(["unrar", "e", "-y", "-o+", str(archive), chosen, str(tmp) + "/"], capture_output=True, text=True, timeout=120)
        got = list(tmp.glob("*"))
    if r.returncode not in (0, 1) or not got:
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    dest = out_dir / f"ep{episode:04d}{got[0].suffix.lower()}"
    shutil.move(str(got[0]), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    return dest


def fetch_subtitle(anime_name: str, episode: int, work_dir: Path, log=lambda m: None, packs_cache: Optional[Dict] = None, video_name: str = "") -> Optional[Dict]:
    """Full lookup for one episode. Returns {path, translator, release, pack_url} or None when not found.
    Never raises on 'not found' or a network hiccup: the caller then falls back to the AI translation."""
    packs_cache = packs_cache if packs_cache is not None else {}
    try:
        if anime_name not in packs_cache:
            hit = best_match(anime_name, search_anime(anime_name))
            if not hit:
                packs_cache[anime_name] = (None, [])
            else:
                packs_cache[anime_name] = (hit, list_packs(hit["slug"]))
        hit, packs = packs_cache[anime_name]
        if not hit:
            log(f"miraianime: no anime named '{anime_name}'")
            return None
        # Try the best pack first, then the other packs that cover the episode.
        tried = []
        while True:
            left = [p for p in packs if p not in tried]
            pack = pick_pack(left, episode, release_hint(video_name))
            if not pack:
                log(f"miraianime: '{hit['title']}' has no subtitle file for episode {episode}")
                return None
            tried.append(pack)
            archive = download_pack(pack, work_dir / "_packs" / hit["slug"])
            path = extract_episode(archive, episode, work_dir / "_subs" / hit["slug"])
            if path:
                return {"path": str(path), "translator": pack["translator"], "release": pack["release"], "pack_url": pack["url"], "title": hit["title"]}
    except Exception as exc:  # network / archive problems: fall back to the AI translation
        log(f"miraianime: lookup failed for episode {episode}: {exc}")
        return None
