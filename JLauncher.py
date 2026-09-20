# -*- coding: utf-8 -*-
"""
JLauncher — офлайн-лаунчер Minecraft
"""
import concurrent.futures
import http.client
import ssl
import os, re, sys, json, hashlib, threading, subprocess, traceback, zipfile, shutil, time, random, string
import queue
import urllib.request
from pathlib import Path
from urllib.error import URLError, HTTPError
from collections import defaultdict

import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, filedialog, messagebox

COLORS = {
    "bg":       "#1a1a1f",
    "surface":  "#22222c",
    "surface2": "#2c2c38",
    "border":   "#3a3a4a",
    "fg":       "#e8e8f0",
    "fg_dim":   "#8a8a9c",
    "accent":   "#4ea85c",
    "accent_h": "#62c172",
    "accent_p": "#3d8c4a",
    "danger":   "#c75450",
    "danger_h": "#dc6a66",
    "log_bg":   "#0e0e14",
    "log_fg":   "#c8c8d8",
}

DONATE_URL   = "https://pay.cloudtips.ru/p/40c67bec"
DONATE_LABEL = "☕ Поддержать"


def _default_game_dir():
    appdata = os.environ.get("APPDATA")
    if appdata:
        return str(Path(appdata) / ".minecraft")
    return str(Path.home() / "AppData" / "Roaming" / ".minecraft")


DEFAULTS = {
    "game_dir":            _default_game_dir(),
    "username":            "Steve",
    "ram_mb":              4096,
    "last_version":        "",
    "last_java":           "",
    "java_by_version":     {},
    "manual_mc_version":   {},
    "download_libraries":  True,
    "download_assets":     True,
    "window_geometry":     "",
    "min_client_jar_size": 10 * 1024 * 1024,
    "javas_cache_ttl_h":   12,
    "extra_roots":         [],
    "backup_enabled":   True,
    "backup_frequency": "before_launch",
    "backup_keep":      5,
    "backup_include":   ["saves", "options.txt", "servers.dat"],
}

CONFIG_PATH = Path(__file__).with_name("config.json")

JAVA_SEARCH_DIRS = [
    r"C:\Program Files\Java",
    r"C:\Program Files (x86)\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\BellSoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\Amazon Corretto",
    r"C:\Program Files\Semeru",
    r"C:\Program Files\Temurin",
    r"C:\Program Files\OpenJDK",
    r"D:\Java",
    r"D:\Program Files\Java",
    os.path.expanduser(r"~\AppData\Local\Programs\Eclipse Adoptium"),
    os.path.expanduser(r"~\AppData\Local\Programs\Microsoft"),
]

MANIFEST_URL    = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
ASSETS_BASE     = "https://resources.download.minecraft.net/"
FORGE_MAVEN     = "https://maven.minecraftforge.net/net/minecraftforge/forge"
FORGE_METADATA  = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
FABRIC_META     = "https://meta.fabricmc.net/v2/versions/installer"
FABRIC_MAVEN    = "https://maven.fabricmc.net/net/fabricmc/fabric-installer"
MAVEN_CENTRAL   = "https://repo1.maven.org/maven2"

DEMO_FLAGS = {"--demo"}
DEMO_FLAGS_WITH_VALUE = {
    "--quickPlayPath", "--quickPlaySingleplayer",
    "--quickPlayMultiplayer", "--quickPlayRealms",
}

AUTO_DELETE_MOD_PATTERNS = ["tl_skin*", "tl_skin_cape*"]
FABRIC_BAD_MODS = ["optifabric*", "optifine*", "OptiFabric*", "OptiFine*"]

JPMS_PROBLEMATIC_MODS = ["playeranimator", "clientmodpack", "create", "flywheel"]

AIKAR_BASE_FLAGS = [
    "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
    "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
    "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20",
    "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
    "-XX:InitiatingHeapOccupancyPercent=15",
    "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5",
    "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1",
    "-Dusing.aikars.flags=https://mcflags.emc.gs",
    "-Daikars.new.flags=true",
]

ZGC_FLAGS = [
    "-XX:+UseZGC", "-XX:+ZGenerational", "-XX:+AlwaysPreTouch",
    "-XX:+DisableExplicitGC", "-XX:+UseStringDeduplication",
    "-XX:+UseDynamicNumberOfGCThreads", "-XX:+PerfDisableSharedMem",
    "-XX:+UnlockExperimentalVMOptions",
]

JVM_FLAG_MIN_VERSION = [
    ("--sun-misc-unsafe-memory-access", 24),
    ("--enable-native-access",           22),
    ("--illegal-native-access",          22),
    ("-XX:+UseCompactObjectHeaders",     24),
]

FORGE_ADD_OPENS = [
    "--add-opens", "java.base/java.lang.invoke",
    "--add-opens", "java.base/java.lang.reflect",
    "--add-opens", "java.base/java.util",
    "--add-opens", "java.base/java.util.jar",
    "--add-opens", "java.base/java.nio.file",
    "--add-opens", "java.base/java.nio.charset",
    "--add-opens", "java.base/java.lang",
    "--add-opens", "java.base/sun.nio.ch",
    "--add-opens", "java.base/sun.security.util",
    "--add-opens", "java.base/sun.security.action",
    "--add-exports", "java.base/sun.security.util",
    "--add-exports", "java.base/sun.security.action",
]

GAME_DIR            = Path(DEFAULTS["game_dir"])
VERSIONS_DIR        = GAME_DIR / "versions"
LIBRARIES_DIR       = GAME_DIR / "libraries"
ASSETS_DIR          = GAME_DIR / "assets"
ASSETS_INDEXES_DIR  = ASSETS_DIR / "indexes"
ASSETS_OBJECTS_DIR  = ASSETS_DIR / "objects"
CACHE_DIR           = GAME_DIR / ".jlauncher_cache"
CLASSPATH_SEP       = ";" if os.name == "nt" else ":"
GLOBAL_CONFIG       = {}


def make_progress_bar(current, total, width=30, prefix=""):
    if total <= 0:
        return f"{prefix} [" + "." * width + f"] ({current}/{total})"
    pct = int(current * 100 / total)
    filled = int(current * width / total)
    bar = "[" + "-" * filled + "." * (width - filled) + f"] {pct:>3}%"
    tail = f" ({current}/{total})"
    return f"{prefix} {bar}{tail}" if prefix else f"{bar}{tail}"


def total_ram_mb():
    try:
        if os.name == "nt":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys / (1024 * 1024))
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 8192


def recommend_ram_mb(version_id=None):
    total = total_ram_mb()
    half = total // 2
    if version_id and any(kw in version_id.lower() for kw in
                         ("forge", "fabric", "rlcraft", "cave", "dread", "zombie", "city", "cursed")):
        rec = max(4096, min(half, 8192))
    else:
        rec = max(2048, min(half, 4096))
    return min(rec, int(total * 0.75))


def java_major_version(java_path):
    try:
        p = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (p.stderr or "") + (p.stdout or "")
        m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
        if m:
            major = int(m.group(1))
            return int(m.group(2)) if major == 1 else major
    except Exception:
        pass
    return None


def _norm_java_major(v):
    if v is None:
        return None
    try:
        iv = int(float(v))
        return iv if iv > 0 else None
    except (ValueError, TypeError):
        return None


def find_javas():
    result = {}
    paths = set()
    try:
        which = "where" if os.name == "nt" else "which"
        p = subprocess.run([which, "java"], capture_output=True, text=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode == 0:
            for line in p.stdout.strip().splitlines():
                paths.add(line.strip())
    except Exception:
        pass
    jh = os.environ.get("JAVA_HOME")
    if jh:
        jp = Path(jh) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if jp.exists():
            paths.add(str(jp))
    for base in JAVA_SEARCH_DIRS:
        bp = Path(base)
        if bp.exists():
            try:
                for exe in bp.rglob("java.exe"):
                    paths.add(str(exe))
            except Exception:
                pass
    for p in paths:
        v = java_major_version(p)
        if v is not None:
            result.setdefault(v, []).append(p)
    return result


def _cache_dir():
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return CACHE_DIR


def find_javas_cached(ttl_hours=12, log=None):
    cache_file = _cache_dir() / "javas.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            age_h = (time.time() - data.get("ts", 0)) / 3600.0
            if age_h < ttl_hours:
                out = {}
                ok = True
                for k, v in data.get("javas", {}).items():
                    existing = [p for p in v if Path(p).exists()]
                    if not existing:
                        ok = False
                        break
                    out[int(k)] = existing
                if ok and out:
                    if log: log(f"[✓] Java из кэша ({len(out)} шт., кэш {age_h:.1f} ч)")
                    return out
        except Exception:
            pass
    if log: log("[*] Первый скан Java (займёт секунду)...")
    javas = find_javas()
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "ts": time.time(),
                "javas": {str(k): v for k, v in javas.items()},
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return javas


def _classpath_cache_path(vdir):
    return vdir / ".classpath.cache"


def _file_sig(paths):
    h = hashlib.sha1()
    for p in sorted(paths, key=str):
        try:
            st = p.stat()
            h.update(str(p).encode("utf-8")); h.update(b"\x00")
            h.update(str(st.st_mtime_ns).encode()); h.update(b"\x00")
            h.update(str(st.st_size).encode()); h.update(b"\x00")
        except Exception:
            h.update(str(p).encode("utf-8"))
            h.update(b"\x01miss\x00")
    return h.hexdigest()


def _lib_paths_for_sig(version_json, vdir):
    paths = []
    for lib in version_json.get("libraries", []):
        rules = lib.get("rules")
        if rules and not check_rules(rules):
            continue
        p = _get_lib_path(lib)
        if p:
            paths.append(p)
    # client.jar: ровно тот, что пойдёт в classpath — по цепочке inheritsFrom
    try:
        cj = find_vanilla_client_jar(version_json.get("id", ""), log=None)
    except Exception:
        cj = None
    if cj:
        paths.append(cj)
    else:
        # fallback: хоть что-то из папки сборки
        cj2 = sanitize_client_jar(vdir, log=None)
        if cj2:
            paths.append(cj2)
    return paths


def _assets_marker_path(idx_id):
    return ASSETS_DIR / f".ready_{idx_id}"


def offline_uuid(name):
    d = hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest()
    b = bytearray(d)
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    h = bytes(b).hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def fake_access_token():
    return ''.join(random.choices(string.hexdigits.lower(), k=32))


def fake_xuid():
    return str(random.randint(10**15, 10**16 - 1))


def fake_client_id():
    return ''.join(random.choices("0123456789abcdef", k=16))


def mc_tuple(version_id):
    if not version_id:
        return (0, 0, 0)
    for m in re.finditer(r'(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)', version_id):
        major = int(m.group(1))
        minor = int(m.group(2))
        if major == 1 and 7 <= minor <= 30:
            patch = int(m.group(3)) if m.group(3) else 0
            return (major, minor, patch)
    return (0, 0, 0)


def required_java_base(version_id):
    v = mc_tuple(version_id)
    if v >= (1, 20, 5): return 21
    if v >= (1, 17, 0): return 17
    return 8


def find_actual_mc_version(vjson, log=None, depth=0):
    if depth > 5 or not isinstance(vjson, dict):
        return None
    jv = _norm_java_major((vjson.get("javaVersion") or {}).get("majorVersion"))
    if jv:
        if jv >= 21: return "1.20.5"
        if jv >= 17: return "1.17"
    for key in ("inheritsFrom", "jar", "id"):
        val = vjson.get(key)
        if not isinstance(val, str):
            continue
        for m in re.finditer(r'(?<![\d.])1\.(\d+)(?:\.(\d+))?(?![\d.])', val):
            minor = int(m.group(1))
            if minor < 7:
                continue
            ver = f"1.{minor}" + (f".{m.group(2)}" if m.group(2) else "")
            if log: log(f"    Реальная MC-версия: {ver} (из {key}='{val}')")
            return ver
    return None


def required_java_full(version_id, vjson=None, log=None):
    # 1) Явное указание из JSON — самое авторитетное
    if vjson:
        jv = _norm_java_major((vjson.get("javaVersion") or {}).get("majorVersion"))
        if jv:
            if log: log(f"    JSON требует Java {jv}")
            return jv

    # 2) mainClass: knot/modlauncher/bootstraplauncher → 17+
    if vjson:
        mc_cls = (vjson.get("mainClass") or "").lower()
        if any(k in mc_cls for k in ("bootstraplauncher", "modlauncher",
                                      "knotclient", "knot", "fabricmc")):
            if log: log("    mainClass требует Java 17+")
            return 17

    # 3) Forge 26.x+ — Java 25
    m = re.match(r'Forge\s+(\d+)\.', version_id)
    if m and int(m.group(1)) >= 26:
        if log: log(f"    Forge {m.group(1)}.x требует Java 25")
        return 25

    # 4) Теперь ручная MC-версия
    manual = GLOBAL_CONFIG.get("manual_mc_version", {}).get(version_id)
    if manual:
        need = required_java_base(manual)
        if log: log(f"    Ручная MC-версия {manual} → Java {need}+")
        return need

    # 5) fallback
    base = required_java_base(version_id)
    if vjson:
        real = find_actual_mc_version(vjson, log)
        if real:
            real_need = required_java_base(real)
            if real_need > base:
                if log: log(f"    Требуется Java {real_need}+")
                return real_need
    return base

def pick_java(javas, need):
    candidates = [v for v in javas if v >= need]
    if candidates:
        return javas[min(candidates)][0]
    if javas:
        return javas[max(javas.keys())][0]
    return None


def check_rules(rules):
    if not rules:
        return True
    res = False
    for r in rules:
        action = (r.get("action") == "allow")
        match = True
        osr = r.get("os", {})
        if "name" in osr and osr["name"] != "windows":
            match = False
        if match:
            res = action
    return res


def _mods_dirs_for(vdir):
    out = []
    for candidate in (vdir / "mods", vdir / "game" / "mods"):
        if candidate.is_dir():
            out.append(candidate)
    return out


def cleanup_auto_delete_mods(vdir, log=None):
    removed = []
    for mods_dir in _mods_dirs_for(vdir):
        for pattern in AUTO_DELETE_MOD_PATTERNS:
            for jar in mods_dir.glob(pattern):
                if not jar.is_file() or jar.suffix.lower() != ".jar":
                    continue
                try:
                    jar.unlink()
                    removed.append(jar.name)
                except Exception as e:
                    if log: log(f"[!] Не удалить {jar.name}: {e}")
    if removed and log:
        log(f"[✓] Удалено tl_skin/tl_skin_cape модов: {len(removed)}")
        for n in removed:
            log(f"    - {n}")
    return removed


def cleanup_temp_files():
    try:
        for root in _candidate_roots():
            libs = root / "libraries"
            if not libs.is_dir():
                continue
            try:
                for tmp in libs.rglob("*.tmp"):
                    try: tmp.unlink()
                    except Exception: pass
            except Exception:
                pass
    except Exception:
        pass


def cleanup_auto_delete_mods_all(log=None):
    total = 0
    try:
        for root in _candidate_roots():
            versions = root / "versions"
            if not versions.is_dir():
                continue
            try:
                for v in versions.iterdir():
                    if not v.is_dir():
                        continue
                    total += len(cleanup_auto_delete_mods(v, log=None))
            except Exception:
                pass
    except Exception:
        pass
    if total and log:
        log(f"[✓] Автоподчистка (все .minecraft): удалено {total} модов.")
    return total


def check_fabric_bad_mods(vdir, log=None):
    bad = []
    for mods_dir in _mods_dirs_for(vdir):
        for pattern in FABRIC_BAD_MODS:
            for jar in mods_dir.glob(pattern):
                if jar.is_file() and jar.suffix.lower() == ".jar":
                    bad.append(jar)
    if bad and log:
        log("[!] Найдены проблемные моды Fabric (конфликтуют с Fabric API):")
        for j in bad:
            log(f"    - {j.name}")
    return bad


def _normalize_mod_name(stem):
    s = stem
    s = re.sub(r'\s*\(\d+\)\s*$', '', s)
    s = re.sub(r'\s*-\s*copy\s*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*_copy\s*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\.bak$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s+', ' ', s).strip()
    return s.lower()


def remove_duplicate_mods(vdir, log=None):
    removed = []
    for mods_dir in _mods_dirs_for(vdir):
        groups = defaultdict(list)
        for jar in mods_dir.glob("*.jar"):
            if not jar.is_file():
                continue
            try:
                size = jar.stat().st_size
            except Exception:
                continue
            base = _normalize_mod_name(jar.stem)
            groups[(base, size)].append(jar)

        for (base, size), jars in groups.items():
            if len(jars) <= 1:
                continue
            def score(j):
                name = j.name.lower()
                s = 0
                if re.search(r'\(\d+\)', name): s += 100
                if "copy" in name: s += 50
                if name.endswith(".bak"): s += 200
                return s
            jars_sorted = sorted(jars, key=lambda j: (score(j), j.stat().st_mtime))
            keep = jars_sorted[0]
            for j in jars_sorted[1:]:
                try:
                    j.rename(j.with_name(j.name + ".disabled"))
                    removed.append(j.name)
                except Exception as e:
                    if log: log(f"[!] Не отключить дубликат {j.name}: {e}")
            if log:
                log(f"[✓] Дубликат '{base}' ({size} б): оставлен {keep.name}, отключено {len(jars)-1}")

    if removed and log:
        log(f"[✓] Всего отключено дубликатов модов: {len(removed)}")
    return removed


def sanitize_client_jar(vdir, log=None):
    candidates = [j for j in vdir.glob("*.jar") if "installer" not in j.name.lower()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    client_jar = candidates[0]

    if client_jar.name == "clientmodpack.jar":
        return client_jar

    if not re.match(r'^[A-Za-z][A-Za-z0-9_]*\.jar$', client_jar.name):
        new_path = vdir / "clientmodpack.jar"
        if new_path.exists() and new_path != client_jar:
            try: new_path.unlink()
            except Exception: pass
        try:
            client_jar.rename(new_path)
            if log: log(f"[✓] client.jar переименован: {client_jar.name} → clientmodpack.jar")
            return new_path
        except Exception as e:
            if log: log(f"[!] Не переименовать client.jar: {e}")
            return client_jar
    return client_jar


def _http_get_text(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _http_get_json(url, timeout=15):
    text = _http_get_text(url, timeout)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def fetch_manifest_versions(log=None):
    manifest = fetch_manifest(log)
    if not manifest:
        return []
    out = []
    for v in manifest.get("versions", []):
        if v.get("type") != "release":
            continue
        out.append({"id": v.get("id"), "url": v.get("url"),
                    "releaseTime": v.get("releaseTime")})
    return out


def get_latest_forge_version(mc_version):
    xml = _http_get_text(FORGE_METADATA)
    if not xml:
        return None
    pattern = rf'<version>{re.escape(mc_version)}-([^<]+)</version>'
    versions = re.findall(pattern, xml)
    if not versions:
        return None
    def key(v):
        return [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', v)]
    versions.sort(key=key)
    return versions[-1]


def get_forge_versions(mc_version, log=None):
    xml = _http_get_text(FORGE_METADATA)
    if not xml:
        if log: log("[!] Не удалось получить список версий Forge с сервера.")
        return []
    pattern = rf'<version>{re.escape(mc_version)}-([^<]+)</version>'
    versions = re.findall(pattern, xml)
    if not versions:
        if log: log(f"[!] Forge для MC {mc_version} не найден.")
        return []
    def key(v):
        return [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', v)]
    versions.sort(key=key, reverse=True)
    return versions


def get_latest_fabric_loader(mc_version):
    data = _http_get_json(f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}")
    if not data:
        return None
    versions = []
    for entry in data:
        loader = entry.get("loader") or {}
        v = loader.get("version")
        if v:
            versions.append(v)
    if not versions:
        return None
    def key(v):
        return [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-+]', v)]
    versions.sort(key=key)
    return versions[-1]


def get_fabric_versions(mc_version, log=None):
    data = _http_get_json(f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}")
    if not data:
        if log: log(f"[!] Fabric для MC {mc_version} не найден.")
        return []
    out = []
    for entry in data:
        loader = entry.get("loader") or {}
        v = loader.get("version")
        if v:
            out.append(v)
    def key(v):
        return [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-+]', v)]
    out.sort(key=key, reverse=True)
    return out





def detect_loader_type(parent_id):
    if not parent_id:
        return (None, None, None)
    m = re.match(r'fabric-loader-([\d.]+)-(\d+\.\d+(?:\.\d+)?)', parent_id, re.IGNORECASE)
    if m: return ("fabric", m.group(2), m.group(1))
    m = re.match(r'fabric-([\d.]+)-(\d+\.\d+(?:\.\d+)?)', parent_id, re.IGNORECASE)
    if m: return ("fabric", m.group(2), m.group(1))
    m = re.match(r'neoforge-([\d.]+)', parent_id, re.IGNORECASE)
    if m:
        nf_ver = m.group(1)
        parts = nf_ver.split(".")
        mc_ver = None
        if parts[0] == "47":
            mc_ver = "1.20.1"
        elif parts[0].isdigit():
            major = int(parts[0])
            if major >= 20 and len(parts) >= 2:
                mc_ver = f"1.{major}.{parts[1]}"
        return ("neoforge", mc_ver, nf_ver)
    m = re.match(r'([\d.]+)-neoforge-(.+)', parent_id, re.IGNORECASE)
    if m: return ("neoforge", m.group(1), m.group(2))
    m = re.match(r'([\d.]+)-forge-(.+)', parent_id, re.IGNORECASE)
    if m: return ("forge", m.group(1), m.group(2))
    m = re.match(r'([\d.]+)-fabric-(.+)', parent_id, re.IGNORECASE)
    if m: return ("fabric", m.group(1), m.group(2))
    m = re.match(r'([\d.]+)-forge', parent_id, re.IGNORECASE)
    if m: return ("forge", m.group(1), None)
    m = re.match(r'([\d.]+)-fabric', parent_id, re.IGNORECASE)
    if m: return ("fabric", m.group(1), None)
    if re.match(r'^[\d.]+$', parent_id):
        return ("vanilla", parent_id, None)
    return (None, None, None)


def _parent_loader_by_name(parent):
    p = (parent or "").lower()
    if "neoforge" in p:
        return "neoforge"
    if "fabric" in p:
        return "fabric"
    if "forge" in p:
        return "forge"
    return None


def _mod_loader_kind(jar_path):
    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            names = z.namelist()
            has_fabric = "fabric.mod.json" in names
            has_forge = "META-INF/mods.toml" in names
            if has_fabric and not has_forge:
                return "fabric"
            if has_forge and not has_fabric:
                return "forge"
            if has_fabric and has_forge:
                return "both"
    except Exception:
        pass
    name = jar_path.name.lower()
    if "fabric" in name and "forge" not in name:
        return "fabric"
    if "forge" in name and "fabric" not in name:
        return "forge"
    return None


def scan_mods_loader_ratio(vdir, log=None):
    mods_dir = vdir / "mods"
    scan = {"forge": [], "fabric": [], "both": [], "unknown": []}
    if not mods_dir.is_dir():
        return (None, 0, 0, 0, scan)

    for jar in sorted(mods_dir.glob("*.jar")):
        if not jar.is_file():
            continue
        kind = _mod_loader_kind(jar)
        if kind in ("forge", "fabric"):
            scan[kind].append(jar)
        elif kind == "both":
            scan["both"].append(jar)
        else:
            scan["unknown"].append(jar)

    forge_c = len(scan["forge"])
    fabric_c = len(scan["fabric"])
    total = forge_c + fabric_c + len(scan["both"]) + len(scan["unknown"])

    if forge_c > fabric_c:
        loader = "forge"
    elif fabric_c > forge_c:
        loader = "fabric"
    else:
        loader = None

    if log:
        log(f"[*] Скан модов: Forge={forge_c}, Fabric={fabric_c}, "
            f"both={len(scan['both'])}, unknown={len(scan['unknown'])}, всего={total}")
        if loader:
            log(f"    → Большинство: {loader.title()}")

    return (loader, forge_c, fabric_c, total, scan)


def scan_mods_mc_version(vdir, log=None):
    mods_dir = vdir / "mods"
    if not mods_dir.is_dir():
        return None
    candidates = {}
    for jar in mods_dir.glob("*.jar"):
        if not jar.is_file():
            continue
        for m in re.finditer(r'(?<![\d.])1\.(\d{2})(?:\.(\d+))?(?![\d.])', jar.stem):
            minor = int(m.group(1))
            if minor < 12 or minor > 30:
                continue
            patch = int(m.group(2)) if m.group(2) else 0
            ver = f"1.{minor}" + (f".{patch}" if m.group(2) else "")
            candidates[ver] = candidates.get(ver, 0) + 1
    if not candidates:
        return None
    def sort_key(item):
        ver, cnt = item
        parts = [int(x) for x in ver.split(".")]
        while len(parts) < 3:
            parts.append(0)
        return (cnt, parts)
    best_ver, best_cnt = max(candidates.items(), key=sort_key)
    if log:
        top = sorted(candidates.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{v}={c}" for v, c in top)
        log(f"[*] MC по модам: {best_ver} ({best_cnt} упоминаний; топ: {top_str})")
    return best_ver


def _get_lib_artifact(lib, classifier=None):
    downloads = lib.get("downloads") or {}
    if classifier:
        cl = downloads.get("classifiers") or lib.get("classifies") or {}
        art = cl.get(classifier)
        if isinstance(art, dict):
            return art
    art = downloads.get("artifact")
    if isinstance(art, dict):
        return art
    art = lib.get("artifact")
    if isinstance(art, dict):
        return art
    return None


def _get_lib_path(lib, classifier=None):
    art = _get_lib_artifact(lib, classifier)
    if art and art.get("path"):
        return LIBRARIES_DIR / art["path"]
    name = lib.get("name", "")
    parts = name.split(":")
    if len(parts) < 3:
        return None
    g, a, ver = parts[0], parts[1], parts[2]
    if classifier:
        return LIBRARIES_DIR / g.replace(".", "/") / a / ver / f"{a}-{ver}-{classifier}.jar"
    return LIBRARIES_DIR / g.replace(".", "/") / a / ver / f"{a}-{ver}.jar"


def _get_lib_url(lib, classifier=None):
    art = _get_lib_artifact(lib, classifier)
    if art and art.get("url"):
        return art["url"]
    if classifier:
        return None
    base_url = lib.get("url")
    if base_url:
        name = lib.get("name", "")
        parts = name.split(":")
        if len(parts) >= 3:
            g, a, ver = parts[0], parts[1], parts[2]
            return f"{base_url.rstrip('/')}/{g.replace('.', '/')}/{a}/{ver}/{a}-{ver}.jar"
    return None

def _normalize_root_choice(path):
    """Принимает любую папку, возвращает ту, где лежит versions/.
    Возврат: (Path|None, err|None)."""
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return (None, "Путь не существует или это не папка")
    if (p / "versions").is_dir():
        return (p, None)
    if (p / "game" / "versions").is_dir():
        return (p / "game", None)
    if (p / ".minecraft" / "versions").is_dir():
        return (p / ".minecraft", None)
    return (p, "В этой папке нет подпапки 'versions/'")
def _candidate_roots():
    roots = []

    cfg_dir = GLOBAL_CONFIG.get("game_dir")
    if cfg_dir:
        roots.append(Path(cfg_dir))

    for extra in GLOBAL_CONFIG.get("extra_roots", []) or []:
        try:
            roots.append(Path(extra))
        except Exception:
            pass

    appdata = os.environ.get("APPDATA") or ""
    localappdata = os.environ.get("LOCALAPPDATA") or ""

    if appdata:
        roots.append(Path(appdata) / ".minecraft")
        roots.append(Path(appdata) / ".tlauncher" / "legacy" / "Minecraft" / "game")
        roots.append(Path(appdata) / ".tlauncher" / "legacy" / ".minecraft")
    if localappdata:
        roots.append(Path(localappdata) / ".minecraft")

    roots.append(Path("C:/Minecraft/game"))
    roots.append(Path("D:/Minecraft/game"))
    roots.append(Path("C:/Minecraft"))
    roots.append(Path("D:/Minecraft"))

    try:
        launcher_dir = Path(sys.argv[0]).resolve().parent
        roots.append(launcher_dir / ".minecraft")
        roots.append(launcher_dir)
    except Exception:
        pass

    try:
        roots.append(Path.cwd() / ".minecraft")
        roots.append(Path.cwd())
    except Exception:
        pass

    out = []
    seen = set()
    for r in roots:
        try:
            rp = r.resolve()
        except Exception:
            rp = r
        key = str(rp).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if (rp / "versions").is_dir():
                out.append(rp)
        except Exception:
            pass
    return out


def _short_root_name(root):
    try:
        r = str(root).lower()
    except Exception:
        return str(root)
    if ".tlauncher" in r:
        return "TLauncher"
    if "\\.minecraft" in r or "/.minecraft" in r:
        return ".minecraft"
    return root.name or str(root)


def scan_all_versions(log=None):
    roots = _candidate_roots()
    if log:
        log(f"[*] Найдено .minecraft-корней: {len(roots)}")
        for r in roots:
            log(f"    - {r}")
    entries = []
    name_counter = defaultdict(int)
    for root in roots:
        vdir = root / "versions"
        if not vdir.is_dir():
            continue
        try:
            subdirs = sorted([d for d in vdir.iterdir() if d.is_dir()],
                             key=lambda p: p.name.lower())
        except Exception:
            continue
        for d in subdirs:
            base_id = d.name
            name_counter[base_id] += 1
            n = name_counter[base_id]
            display = base_id if n == 1 else f"{base_id} ({n-1})"
            entries.append({
                "display": display,
                "id": base_id,
                "root": root,
                "path": d,
            })
    return entries


def _set_root(root):
    global GAME_DIR, VERSIONS_DIR, LIBRARIES_DIR, ASSETS_DIR
    global ASSETS_INDEXES_DIR, ASSETS_OBJECTS_DIR, CACHE_DIR
    GAME_DIR = Path(root)
    VERSIONS_DIR = GAME_DIR / "versions"
    LIBRARIES_DIR = GAME_DIR / "libraries"
    ASSETS_DIR = GAME_DIR / "assets"
    ASSETS_INDEXES_DIR = ASSETS_DIR / "indexes"
    ASSETS_OBJECTS_DIR = ASSETS_DIR / "objects"
    CACHE_DIR = GAME_DIR / ".jlauncher_cache"


def _current_launcher_root():
    return GAME_DIR


def create_pack_dir(root, pack_name, mc_version, inherits_id, log=None):
    if not pack_name:
        return (False, None)

    pack_name = pack_name.strip()
    if not pack_name:
        return (False, None)

    bad = '<>:"/\\|?*'
    for ch in bad:
        pack_name = pack_name.replace(ch, "_")

    vdir = Path(root) / "versions"
    vdir.mkdir(parents=True, exist_ok=True)

    base_id = pack_name
    real_id = base_id
    n = 0
    while (vdir / real_id).exists():
        n += 1
        real_id = f"{base_id} ({n})"

    target = vdir / real_id
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        if log: log(f"[!] Не создать папку сборки: {e}")
        return (False, None)

    jpath = target / f"{real_id}.json"
    data = {
        "id": real_id,
        "inheritsFrom": inherits_id,
        "type": "release",
    }
    try:
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        if log: log(f"[!] Не записать JSON сборки: {e}")
        return (False, None)

    for sub in ("mods", "config", "saves", "resourcepacks", "shaderpacks"):
        try:
            (target / sub).mkdir(exist_ok=True)
        except Exception:
            pass

    if log:
        log(f"[✓] Сборка '{real_id}' создана (inheritsFrom = {inherits_id})")
    return (True, real_id)


def find_installed_loader_id(mc_version, loader, loader_ver):
    if loader == "vanilla":
        return mc_version
    if loader == "forge":
        return f"{mc_version}-forge-{loader_ver}"
    if loader == "fabric":
        return f"fabric-loader-{loader_ver}-{mc_version}"
    if loader == "neoforge":
        return f"neoforge-{loader_ver}"
    return mc_version


def fix_pack_loader(vdir, version_id, target_loader, scan, log=None, java_path=None):
    other = "fabric" if target_loader == "forge" else "forge"
    mods_dir = vdir / "mods"
    disabled = []
    enabled = []

    for jar in scan.get(other, []):
        new = jar.with_name(jar.name + ".disabled")
        try:
            jar.rename(new)
            disabled.append(jar.name)
        except Exception as e:
            if log: log(f"[!] Не отключить {jar.name}: {e}")

    for djar in mods_dir.glob("*.jar.disabled"):
        stem = djar.name[:-len(".disabled")]
        try:
            with zipfile.ZipFile(djar, "r") as z:
                names = z.namelist()
                is_target = (
                    (target_loader == "forge" and "META-INF/mods.toml" in names) or
                    (target_loader == "fabric" and "fabric.mod.json" in names)
                )
        except Exception:
            is_target = False
        if is_target:
            try:
                djar.rename(djar.with_name(stem))
                enabled.append(stem)
            except Exception as e:
                if log: log(f"[!] Не включить {stem}: {e}")

    if log:
        if disabled:
            log(f"[✓] Отключено {other} модов: {len(disabled)}")
        if enabled:
            log(f"[✓] Включено {target_loader} модов: {len(enabled)}")

    jpath = pick_version_json(vdir, version_id)
    if not jpath:
        return len(disabled), len(enabled)
    try:
        data = load_json_tolerant(jpath)
    except Exception:
        return len(disabled), len(enabled)
    if not isinstance(data, dict):
        return len(disabled), len(enabled)

    parent = data.get("inheritsFrom", "")
    _, mc_ver, _ = detect_loader_type(parent)
    if not mc_ver:
        m = re.search(r'\b(1\.\d+(?:\.\d+)?)\b', parent or "")
        if m:
            mc_ver = m.group(1)
    if not mc_ver:
        return len(disabled), len(enabled)

    new_parent = None
    if target_loader == "forge":
        best_id, _ = find_max_local_forge(mc_ver)
        if best_id:
            new_parent = best_id
    elif target_loader == "fabric":
        best_id, _ = find_max_local_fabric(mc_ver)
        if best_id:
            new_parent = best_id

    if new_parent and new_parent != parent:
        data["inheritsFrom"] = new_parent
        try:
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if log: log(f"[✓] inheritsFrom: {parent} → {new_parent}")
        except Exception as e:
            if log: log(f"[!] Не исправить JSON: {e}")
    return len(disabled), len(enabled)


def fix_pack_mc_and_loader(vdir, version_id, target_mc, target_loader, scan,
                            log=None, java_path=None):
    other = "fabric" if target_loader == "forge" else "forge"
    mods_dir = vdir / "mods"
    disabled = 0
    enabled = 0

    for jar in scan.get(other, []):
        try:
            jar.rename(jar.with_name(jar.name + ".disabled"))
            disabled += 1
        except Exception as e:
            if log: log(f"[!] Не отключить {jar.name}: {e}")

    for djar in mods_dir.glob("*.jar.disabled"):
        stem = djar.name[:-len(".disabled")]
        try:
            with zipfile.ZipFile(djar, "r") as z:
                names = z.namelist()
                is_target = (
                    (target_loader == "forge" and "META-INF/mods.toml" in names) or
                    (target_loader == "fabric" and "fabric.mod.json" in names)
                )
        except Exception:
            is_target = False
        if is_target:
            try:
                djar.rename(djar.with_name(stem))
                enabled += 1
            except Exception as e:
                if log: log(f"[!] Не включить {stem}: {e}")

    if log:
        if disabled: log(f"[✓] Отключено {other} модов: {disabled}")
        if enabled:  log(f"[✓] Включено {target_loader} модов: {enabled}")

    new_parent = None
    if target_loader == "forge":
        best_id, _ = find_max_local_forge(target_mc)
        if best_id:
            new_parent = best_id
        elif java_path:
            if log: log(f"[*] Локальный Forge {target_mc} не найден — устанавливаю...")
            latest = get_latest_forge_version(target_mc)
            if latest and download_and_install_forge(target_mc, latest, java_path, log):
                best_id, _ = find_max_local_forge(target_mc)
                if best_id:
                    new_parent = best_id
    elif target_loader == "fabric":
        best_id, _ = find_max_local_fabric(target_mc)
        if best_id:
            new_parent = best_id
        elif java_path:
            if log: log(f"[*] Локальный Fabric {target_mc} не найден — устанавливаю...")
            latest = get_latest_fabric_loader(target_mc)
            if latest and download_and_install_fabric(target_mc, latest, java_path, log):
                best_id, _ = find_max_local_fabric(target_mc)
                if best_id:
                    new_parent = best_id

    if not new_parent:
        if log: log(f"[!] Не удалось найти/установить {target_loader} для {target_mc}")
        return disabled, enabled, False

    jpath = pick_version_json(vdir, version_id)
    if not jpath:
        return disabled, enabled, False
    try:
        data = load_json_tolerant(jpath)
    except Exception:
        return disabled, enabled, False
    if not isinstance(data, dict):
        return disabled, enabled, False

    old_parent = data.get("inheritsFrom", "")
    if new_parent != old_parent:
        data["inheritsFrom"] = new_parent
        try:
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if log: log(f"[✓] inheritsFrom: {old_parent} → {new_parent}")
        except Exception as e:
            if log: log(f"[!] Не исправить JSON: {e}")
            return disabled, enabled, False

    return disabled, enabled, True


def fix_empty_json(vdir, version_id, target_mc, target_loader, log=None, java_path=None):
    new_parent = None
    if target_loader == "forge":
        best_id, _ = find_max_local_forge(target_mc)
        if best_id:
            new_parent = best_id
        elif java_path:
            if log: log(f"[*] Локальный Forge {target_mc} не найден — устанавливаю...")
            latest = get_latest_forge_version(target_mc)
            if latest and download_and_install_forge(target_mc, latest, java_path, log):
                best_id, _ = find_max_local_forge(target_mc)
                if best_id:
                    new_parent = best_id
    elif target_loader == "fabric":
        best_id, _ = find_max_local_fabric(target_mc)
        if best_id:
            new_parent = best_id
        elif java_path:
            if log: log(f"[*] Локальный Fabric {target_mc} не найден — устанавливаю...")
            latest = get_latest_fabric_loader(target_mc)
            if latest and download_and_install_fabric(target_mc, latest, java_path, log):
                best_id, _ = find_max_local_fabric(target_mc)
                if best_id:
                    new_parent = best_id

    if not new_parent:
        if log: log(f"[!] Не удалось найти/установить {target_loader} {target_mc}")
        return False

    jpath = pick_version_json(vdir, version_id)
    if not jpath:
        return False

    try:
        bak = jpath.with_suffix(jpath.suffix + ".bak")
        if not bak.exists() and jpath.exists():
            shutil.copy(jpath, bak)
            if log: log(f"[✓] Бэкап JSON: {bak.name}")
    except Exception:
        pass

    new_data = {
        "id": version_id,
        "inheritsFrom": new_parent,
        "type": "release",
    }
    try:
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        if log: log(f"[✓] JSON пересоздан: inheritsFrom = {new_parent}")
        return True
    except Exception as e:
        if log: log(f"[!] Не пересоздать JSON: {e}")
        return False


def _versions_sort_key(v):
    return [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', v)]


def find_max_local_forge(mc_version):
    if not VERSIONS_DIR.exists():
        return (None, None)
    best_id = None
    best_ver = None
    for d in VERSIONS_DIR.iterdir():
        if not d.is_dir():
            continue
        m = re.match(rf'^{re.escape(mc_version)}-forge-([\d.]+)$', d.name)
        if m:
            ver = m.group(1)
            if best_ver is None or _versions_sort_key(ver) > _versions_sort_key(best_ver):
                best_ver = ver
                best_id = d.name
    return (best_id, best_ver)


def find_max_local_fabric(mc_version):
    if not VERSIONS_DIR.exists():
        return (None, None)
    best_id = None
    best_ver = None
    for d in VERSIONS_DIR.iterdir():
        if not d.is_dir():
            continue
        m = re.match(rf'^fabric-loader-([\d.]+)-{re.escape(mc_version)}$', d.name)
        if m:
            ver = m.group(1)
            if best_ver is None or _versions_sort_key(ver) > _versions_sort_key(best_ver):
                best_ver = ver
                best_id = d.name
    return (best_id, best_ver)


def force_update_inherits_in_versions_json(log=None):
    changed = []
    if not VERSIONS_DIR.exists():
        return changed

    for vdir in VERSIONS_DIR.iterdir():
        if not vdir.is_dir():
            continue
        if re.match(r'^[\d.]+-forge-', vdir.name) or vdir.name.startswith("fabric-loader-"):
            continue
        if vdir.name.startswith("neoforge-"):
            continue
        for j in vdir.glob("*.json"):
            try:
                data = load_json_tolerant(j)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            parent = data.get("inheritsFrom")
            if not isinstance(parent, str):
                continue
            loader_type, mc_ver, cur_loader = detect_loader_type(parent)
            if loader_type == "forge":
                best_id, best_ver = find_max_local_forge(mc_ver)
                if best_id and best_ver and best_ver != cur_loader:
                    data["inheritsFrom"] = best_id
                    try:
                        with open(j, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        if log: log(f"[✓] {j.name}: {parent} → {best_id}")
                        changed.append((str(j), parent, best_id))
                    except Exception as e:
                        if log: log(f"[!] Не переписать {j.name}: {e}")
            elif loader_type == "fabric":
                best_id, best_ver = find_max_local_fabric(mc_ver)
                if best_id and best_ver and best_ver != cur_loader:
                    data["inheritsFrom"] = best_id
                    try:
                        with open(j, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        if log: log(f"[✓] {j.name}: {parent} → {best_id}")
                        changed.append((str(j), parent, best_id))
                    except Exception as e:
                        if log: log(f"[!] Не переписать {j.name}: {e}")
    return changed


def download_and_install_forge(mc_version, forge_version, java_path, log=None):
    if log: log(f"[*] Установка Forge {mc_version}-{forge_version}...")
    installer_name = f"forge-{mc_version}-{forge_version}-installer.jar"
    installer_url = f"{FORGE_MAVEN}/{mc_version}-{forge_version}/{installer_name}"
    installer_path = GAME_DIR / "installers" / installer_name
    installer_path.parent.mkdir(parents=True, exist_ok=True)
    if not installer_path.exists():
        if not _download(installer_url, installer_path, log):
            if log: log("[!] Не удалось скачать установщик Forge.")
            return False
    try:
        cmd = [java_path, "-jar", str(installer_path), "--installClient", str(GAME_DIR)]
        if log: log("    Запускаю установщик...")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              cwd=str(GAME_DIR))
        if proc.returncode == 0:
            if log: log(f"    ✓ Forge {mc_version}-{forge_version} установлен.")
            return True
        if log:
            log(f"    ✗ Ошибка Forge (код {proc.returncode})")
            if proc.stderr:
                for line in proc.stderr.strip().splitlines()[-5:]:
                    log(f"      {line}")
        return False
    except Exception as e:
        if log: log(f"    ✗ {e}")
        return False


def download_and_install_fabric(mc_version, loader_ver, java_path, log=None):
    if log: log(f"[*] Установка Fabric Loader {loader_ver} для MC {mc_version}...")
    installer_version = "1.0.1"
    try:
        req = urllib.request.Request(FABRIC_META, headers={"User-Agent": "JLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        for entry in data:
            if entry.get("stable"):
                installer_version = entry["version"]
                break
    except Exception:
        pass
    installer_name = f"fabric-installer-{installer_version}.jar"
    installer_url = f"{FABRIC_MAVEN}/{installer_version}/{installer_name}"
    installer_path = GAME_DIR / "installers" / installer_name
    installer_path.parent.mkdir(parents=True, exist_ok=True)
    if not installer_path.exists():
        if not _download(installer_url, installer_path, log):
            if log: log("[!] Не удалось скачать установщик Fabric.")
            return False
    try:
        cmd = [java_path, "-jar", str(installer_path), "client",
               "-dir", str(GAME_DIR), "-mcversion", mc_version,
               "-loader", loader_ver,
               "-noprofile", "-downloadMinecraft"]
        if log: log("    Запускаю установщик...")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              cwd=str(GAME_DIR))
        if proc.returncode == 0:
            if log: log(f"    ✓ Fabric Loader {loader_ver} установлен.")
            return True
        if log: log(f"    ✗ Ошибка Fabric (код {proc.returncode})")
        return False
    except Exception as e:
        if log: log(f"    ✗ {e}")
        return False


def ensure_launcher_profiles(game_dir, username, log=None):
    profiles_path = game_dir / "launcher_profiles.json"
    player_uuid = offline_uuid(username)
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    data = {}
    if profiles_path.exists():
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

    if not isinstance(data.get("profiles"), dict):
        data["profiles"] = {}
    if not isinstance(data.get("settings"), dict):
        data["settings"] = {}

    existing = data["profiles"].get(username, {})
    created = existing.get("created") or now

    data["profiles"][username] = {
        "name": username, "type": "custom", "created": created, "lastUsed": now,
        "icon": "Furnace_4", "lastVersionId": "latest-release",
        "gameDir": str(game_dir), "javaArgs": "-Xmx4G -Xms4G",
        "logConfig": "client-1.12.xml", "logConfigIsXML": True,
        "javaDir": "", "uuid": player_uuid,
        "accessToken": fake_access_token(), "userType": "msa",
        "clientId": fake_client_id(), "xuid": fake_xuid(),
    }

    data["settings"].update({
        "enableSnapshots": False, "enableAdvanced": True,
        "keepLauncherOpen": False, "showGameLog": False,
        "showMenu": False, "soundOn": False,
        "locale": "ru_RU", "profileSorting": "ByLastPlayed",
    })
    data["version"] = 3

    try:
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if log: log("[✓] launcher_profiles.json обновлён")
        return True
    except Exception as e:
        if log: log(f"[!] launcher_profiles.json: {e}")
        return False


def ensure_fresh_log4j(log=None):
    out = []
    for name in ("log4j-api", "log4j-core"):
        rel = f"org/apache/logging/log4j/{name}/2.17.1/{name}-2.17.1.jar"
        dest = LIBRARIES_DIR / rel
        if not dest.exists():
            url = f"{MAVEN_CENTRAL}/org/apache/logging/log4j/{name}/2.17.1/{name}-2.17.1.jar"
            if log: log(f"    Скачиваю {name}-2.17.1.jar...")
            if not _download(url, dest, log=None):
                return []
        out.append(dest)
    return out


def is_demo_client_jar(jar_path, log=None):
    if not jar_path.exists():
        return False
    size = jar_path.stat().st_size
    min_size = GLOBAL_CONFIG.get("min_client_jar_size", DEFAULTS["min_client_jar_size"])
    if size < min_size:
        if log: log(f"[!] client.jar мелкий ({size // 1024} КБ) — ДЕМО")
        return True
    return False


def ensure_valid_client_jar(version_id, vdir, log=None):
    """Ищет client.jar только в папке сборки. Не пробует качать по id сборки —
    id сборки не совпадает с ванильной версией в манифесте Mojang.
    Скачивание ванильного jar — задача find_vanilla_client_jar."""
    client_jar = sanitize_client_jar(vdir, log)
    if client_jar and is_demo_client_jar(client_jar, log):
        if log: log("[*] Удаляю демо client.jar")
        try: client_jar.unlink()
        except Exception: pass
        client_jar = None
    return client_jar


def find_vanilla_client_jar(version_id, log=None, visited=None):
    if visited is None:
        visited = set()
    if not version_id or version_id in visited:
        return None
    visited.add(version_id)

    vdir = VERSIONS_DIR / version_id
    if not vdir.exists():
        return None

    jpath = pick_version_json(vdir, version_id)
    if not jpath:
        return None

    try:
        data = load_json_tolerant(jpath)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    parent = data.get("inheritsFrom")
    if isinstance(parent, str) and parent:
        return find_vanilla_client_jar(parent, log=log, visited=visited)

    jar = vdir / f"{version_id}.jar"
    if jar.exists() and jar.stat().st_size > 10 * 1024 * 1024:
        return jar

    if ensure_official_version(version_id, log):
        if jar.exists():
            return jar
    return None


def filter_jvm_args_for_java(jvm_args, java_major):
    if not java_major:
        return jvm_args, []
    out, skipped = [], []
    for a in jvm_args:
        s = str(a)
        skip = False
        for flag, min_ver in JVM_FLAG_MIN_VERSION:
            if s.startswith(flag) and java_major < min_ver:
                skip = True
                skipped.append(s)
                break
        if not skip:
            out.append(a)
    return out, skipped


def build_jvm_flags(ram_mb, java_major, log=None):
    flags = [f"-Xms{ram_mb}M", f"-Xmx{ram_mb}M"]
    if java_major and java_major >= 21 and ram_mb >= 12288:
        flags += ZGC_FLAGS
        if log: log(f"[*] Выбран ZGC (Java {java_major}, RAM {ram_mb} МБ)")
    else:
        flags += AIKAR_BASE_FLAGS
        if log: log(f"[*] Выбран G1GC / Aikar's Flags (Java {java_major}, RAM {ram_mb} МБ)")
    return flags


def is_forge_need_addopens(version_id, vjson=None):
    mt = mc_tuple(version_id)
    if (1, 19, 0) <= mt <= (1, 20, 1):
        return True
    if vjson:
        for key in ("inheritsFrom", "id"):
            val = vjson.get(key)
            if isinstance(val, str):
                mt2 = mc_tuple(val)
                if (1, 19, 0) <= mt2 <= (1, 20, 1):
                    return True
    return False


def is_forge_need_jpms_mixin(version_id, vjson=None):
    mt = mc_tuple(version_id)
    if mt >= (1, 20, 0):
        return True
    if vjson:
        for key in ("inheritsFrom", "id"):
            val = vjson.get(key)
            if isinstance(val, str):
                mt2 = mc_tuple(val)
                if mt2 >= (1, 20, 0):
                    return True
    return False


def sanitize_addopens(jvm_args, log=None):
    out = []
    i = 0
    removed = 0
    while i < len(jvm_args):
        a = jvm_args[i]
        if a in ("--add-opens", "--add-exports", "--add-modules", "--add-reads", "--patch-module"):
            i += 2
            removed += 1
            continue
        out.append(a)
        i += 1
    if removed and log:
        log(f"[*] Удалено старых --add-opens/--add-exports: {removed}")
    return out


def get_forge_win_args(version_id, vjson=None, log=None):
    forge_ver = None
    for key in ("id", "inheritsFrom"):
        val = None
        if vjson and isinstance(vjson.get(key), str):
            val = vjson.get(key)
        elif isinstance(version_id, str):
            val = version_id
        if val:
            m = re.search(r'(\d+\.\d+(?:\.\d+)?)-forge-([\d.]+)', val)
            if m:
                forge_ver = f"{m.group(1)}-{m.group(2)}"
                break
    if not forge_ver:
        return []
    base = LIBRARIES_DIR / "net" / "minecraftforge" / "forge" / forge_ver
    win_args = base / "win_args.txt"
    if win_args.exists():
        if log: log(f"[*] Найден win_args.txt: {win_args}")
        try:
            with open(win_args, "r", encoding="utf-8") as f:
                args = []
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    args.extend(line.split())
            return args
        except Exception as e:
            if log: log(f"[!] Ошибка чтения win_args.txt: {e}")
            return []
    return []


def _pick_jar(pattern, min_version=None):
    found = []
    for jar in LIBRARIES_DIR.glob(pattern):
        if not jar.is_file():
            continue
        if min_version:
            m = re.search(r'-(\d+\.\d+(?:\.\d+)?)\.jar$', jar.name)
            if not m:
                continue
            try:
                cur = [int(x) for x in m.group(1).split('.')]
                need = [int(x) for x in min_version.split('.')]
                while len(cur) < len(need): cur.append(0)
                while len(need) < len(cur): need.append(0)
                if cur < need:
                    continue
            except Exception:
                pass
        found.append(jar)
    if not found:
        return None
    def key(p):
        m = re.search(r'-(\d+\.\d+(?:\.\d+)?)\.jar$', p.name)
        return [int(x) for x in m.group(1).split('.')] if m else [0]
    found.sort(key=key)
    return found[-1]


def get_forge_module_path(version_id, vjson=None, log=None):
    if log: log("[*] Формирую --module-path вручную...")
    module_jars = []
    for pattern, minv in [
        ("cpw/mods/securejarhandler/*/securejarhandler-*.jar", "2.1.4"),
        ("cpw/mods/bootstraplauncher/*/bootstraplauncher-*.jar", "1.1.2"),
        ("org/ow2/asm/asm/*/asm-*.jar", "9.3"),
        ("org/ow2/asm/asm-commons/*/asm-commons-*.jar", "9.3"),
        ("org/ow2/asm/asm-util/*/asm-util-*.jar", "9.3"),
        ("org/ow2/asm/asm-analysis/*/asm-analysis-*.jar", "9.3"),
        ("org/ow2/asm/asm-tree/*/asm-tree-*.jar", "9.3"),
        ("net/minecraftforge/JarJarFileSystems/*/JarJarFileSystems-*.jar", None),
    ]:
        j = _pick_jar(pattern, minv)
        if j and j not in module_jars:
            module_jars.append(j)
    if not module_jars:
        if log: log("[!] Не найдены JAR-файлы для --module-path")
        return []
    module_path_str = ";".join(str(j) for j in module_jars)

    ignore_base = [
        "bootstraplauncher", "securejarhandler",
        "asm-commons", "asm-util", "asm-analysis", "asm-tree", "asm",
        "JarJarFileSystems",
        "client-extra", "fmlcore", "javafmllanguage", "lowcodelanguage", "mclanguage",
        "forge-",
    ]
    ignore_list = ignore_base + JPMS_PROBLEMATIC_MODS

    args = [
        "--module-path", module_path_str,
        "--add-modules=ALL-MODULE-PATH",
        "-DignoreList=" + ",".join(ignore_list) + ",",
        "-DmergeModules=jna-5.10.0.jar,jna-5.10.0.jar",
        "-DlibraryDirectory=" + str(LIBRARIES_DIR),
    ]
    if log:
        log(f"[✓] Сформировано --module-path с {len(module_jars)} JAR-файлами")
    return args


def load_json_tolerant(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    out_lines = []
    for line in text.splitlines():
        in_str, esc, cut = False, False, None
        i = 0
        while i < len(line) - 1:
            c = line[i]
            if esc: esc = False
            elif c == '\\' and in_str: esc = True
            elif c == '"': in_str = not in_str
            elif not in_str and c == '/' and line[i + 1] == '/':
                cut = i; break
            i += 1
        if cut is not None:
            line = line[:cut]
        out_lines.append(line)
    text = "\n".join(out_lines)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return json.loads(text)


def pick_version_json(vdir, version_id):
    preferred = vdir / f"{version_id}.json"
    if preferred.exists():
        return preferred
    jsons = sorted(vdir.glob("*.json"))
    if not jsons:
        return None
    for j in jsons:
        try:
            with open(j, "r", encoding="utf-8-sig") as f:
                head = f.read(8000)
            if any(k in head for k in ('"mainClass"', '"inheritsFrom"', '"id"')):
                return j
        except Exception:
            continue
    return jsons[0]


def detect_game_dir(vdir, log=None):
    for marker in ["mods", "config", "saves", "resourcepacks", "shaderpacks"]:
        if (vdir / marker).exists():
            if log: log(f"    gameDir = {vdir}")
            return vdir
    game = vdir / "game"
    if game.exists() and any((game / m).exists() for m in ["mods", "saves", "config"]):
        if log: log(f"    gameDir = {game}")
        return game
    game.mkdir(parents=True, exist_ok=True)
    if log: log(f"    gameDir = {game} (создана)")
    return game


_manifest_cache = None


def fetch_manifest(log=None):
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "JLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            _manifest_cache = json.loads(r.read().decode("utf-8"))
        if log: log("[*] Манифест Mojang загружен.")
    except Exception as e:
        if log: log(f"[!] Манифест: {e}")
        _manifest_cache = None
    return _manifest_cache


def _download(url, dest: Path, log=None, retries=2):
    for attempt in range(retries + 1):
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk: break
                    f.write(chunk)
            tmp.replace(dest)
            return True
        except Exception as e:
            if attempt < retries:
                time.sleep(1); continue
            if log: log(f"[!] Скачивание {url}: {e}")
            try: tmp.unlink()
            except Exception: pass
            return False


def ensure_official_version(version_id, log=None):
    vdir = VERSIONS_DIR / version_id
    jpath = vdir / f"{version_id}.json"
    jarpath = vdir / f"{version_id}.jar"
    if jpath.exists() and jarpath.exists():
        return True

    # 1) JSON уже есть локально — качаем client.jar по нему, манифест не нужен.
    #    Это спасает кейс типа MC "26.2" — id не в манифесте, но JSON валидный.
    if jpath.exists():
        try:
            with open(jpath, "r", encoding="utf-8-sig") as f:
                jd = json.load(f)
            client = (jd.get("downloads") or {}).get("client") or {}
            url = client.get("url")
            if url and not jarpath.exists():
                if log: log(f"[*] Скачиваю client.jar {version_id} по локальному JSON...")
                if _download(url, jarpath, log):
                    return True
            elif jarpath.exists():
                return True
        except Exception as e:
            if log: log(f"[!] client.jar по локальному JSON: {e}")

    # 2) Иначе — через манифест Mojang (для ванильных версий)
    manifest = fetch_manifest(log)
    if not manifest:
        return False
    entry = next((v for v in manifest.get("versions", []) if v.get("id") == version_id), None)
    if not entry:
        if log: log(f"[!] '{version_id}' нет в манифесте Mojang и нет client.url в локальном JSON.")
        return False
    vdir.mkdir(parents=True, exist_ok=True)
    if not jpath.exists():
        if not _download(entry["url"], jpath, log):
            return False
    if not jarpath.exists():
        try:
            with open(jpath, "r", encoding="utf-8-sig") as f:
                jd = json.load(f)
            client = (jd.get("downloads") or {}).get("client") or {}
            if client.get("url"):
                _download(client["url"], jarpath, log)
        except Exception as e:
            if log: log(f"[!] client.jar: {e}")
    return True

def detect_loader_by_content(vdir):
    loader, _, _, _, _ = scan_mods_loader_ratio(vdir, log=None)
    return loader


def detect_mc_version_from_dir(vdir, log=None):
    game_dir = detect_game_dir(vdir, log=None)
    for logname in ["logs/latest.log", "logs/fml-client-latest.log", "logs/debug.log"]:
        p = game_dir / logname
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read(200000)
                m = re.search(r'Minecraft (\d+\.\d+(?:\.\d+)?)', text)
                if m:
                    if log: log(f"    Из логов: {m.group(1)}")
                    return m.group(1)
            except Exception:
                pass
    mods_dir = game_dir / "mods"
    if mods_dir.exists():
        candidates = {}
        for jar in mods_dir.glob("*.jar"):
            for m in re.finditer(r'\b(1\.\d+(?:\.\d+)?)\b', jar.stem):
                ver = m.group(1)
                candidates[ver] = candidates.get(ver, 0) + 1
        if candidates:
            best = max(candidates.items(), key=lambda x: x[1])
            if log: log(f"    Из mods: {best[0]}")
            return best[0]
    return None


def repair_broken_json(version_id, java_path, log=None):
    vdir = VERSIONS_DIR / version_id
    jpath = pick_version_json(vdir, version_id)
    if not jpath: return False
    try:
        with open(jpath, "r", encoding="utf-8") as f:
            original = f.read()
    except Exception:
        return False
    try:
        data = load_json_tolerant(jpath)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("mainClass") or data.get("inheritsFrom"):
        return False
    mc_ver = GLOBAL_CONFIG.get("manual_mc_version", {}).get(version_id)
    if not mc_ver:
        mc_ver = detect_mc_version_from_dir(vdir, log)
    if not mc_ver:
        return False
    loader = detect_loader_by_content(vdir) or "forge"
    parent_id = None
    if loader == "forge":
        forge_ver = get_latest_forge_version(mc_ver)
        if not forge_ver: return False
        parent_id = f"{mc_ver}-forge-{forge_ver}"
        if not (VERSIONS_DIR / parent_id).exists():
            if not download_and_install_forge(mc_ver, forge_ver, java_path, log):
                return False
    else:
        loader_ver = get_latest_fabric_loader(mc_ver)
        if not loader_ver: return False
        if not download_and_install_fabric(mc_ver, loader_ver, java_path, log):
            return False
        for d in VERSIONS_DIR.iterdir():
            if d.is_dir() and d.name.startswith("fabric-loader"):
                parent_id = d.name; break
        if not parent_id: return False
    if not (VERSIONS_DIR / parent_id).exists(): return False
    if not data.get("id"): data["id"] = version_id
    if not data.get("type"): data["type"] = "release"
    data["inheritsFrom"] = parent_id
    try:
        bak = jpath.with_suffix(jpath.suffix + ".bak")
        if not bak.exists(): bak.write_text(original, encoding="utf-8")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if log: log(f"[✓] JSON исправлен: inheritsFrom = {parent_id}")
    except Exception:
        return False
    return True


def load_version_json(version_id, visited=None, log=None, depth=0, java_path=None):
    if visited is None: visited = set()
    if version_id in visited:
        if log: log(f"[!] Цикл inheritsFrom: {version_id}")
        return None
    visited.add(version_id)
    indent = "  " * depth
    vdir = VERSIONS_DIR / version_id

    if not vdir.exists():
        loader_type, mc_ver, loader_ver = detect_loader_type(version_id)
        if loader_type == "forge" and mc_ver and java_path:
            if not loader_ver:
                loader_ver = get_latest_forge_version(mc_ver)
            if loader_ver and download_and_install_forge(mc_ver, loader_ver, java_path, log):
                vdir = VERSIONS_DIR / version_id
            else:
                return None
        elif loader_type == "fabric" and mc_ver and java_path:
            loader_ver = get_latest_fabric_loader(mc_ver)
            if loader_ver and download_and_install_fabric(mc_ver, loader_ver, java_path, log):
                vdir = VERSIONS_DIR / version_id
            else:
                return None
        elif loader_type == "vanilla":
            if not ensure_official_version(version_id, log):
                return None
            vdir = VERSIONS_DIR / version_id
        else:
            if not ensure_official_version(version_id, log):
                return None
            vdir = VERSIONS_DIR / version_id

    jpath = pick_version_json(vdir, version_id)
    if not jpath:
        if not ensure_official_version(version_id, log):
            return None
        jpath = pick_version_json(vdir, version_id)
        if not jpath: return None

    if log: log(f"{indent}JSON: {jpath.name}")
    try:
        data = load_json_tolerant(jpath)
    except Exception as e:
        if log: log(f"{indent}[!] Парсинг {jpath.name}: {e}")
        return None
    if not isinstance(data, dict):
        if log: log(f"{indent}[!] JSON не объект: {type(data).__name__}")
        return None

    if not data.get("mainClass") and not data.get("inheritsFrom"):
        if depth == 0 and java_path:
            if repair_broken_json(version_id, java_path, log):
                try: data = load_json_tolerant(jpath)
                except Exception: return None

    parent = data.get("inheritsFrom")
    if parent:
        if log: log(f"{indent}inheritsFrom: {parent}")
        pdata = load_version_json(parent, visited, log, depth + 1, java_path)
        if not pdata:
            loader_type, mc_ver, loader_ver = detect_loader_type(parent)
            if loader_type == "forge" and mc_ver and java_path:
                if not loader_ver:
                    loader_ver = get_latest_forge_version(mc_ver)
                if loader_ver and download_and_install_forge(mc_ver, loader_ver, java_path, log):
                    pdata = load_version_json(parent, visited, log, depth + 1, java_path)
            elif loader_type == "fabric" and mc_ver and java_path:
                loader_ver = get_latest_fabric_loader(mc_ver)
                if loader_ver and download_and_install_fabric(mc_ver, loader_ver, java_path, log):
                    pdata = load_version_json(parent, visited, log, depth + 1, java_path)
            elif loader_type == "vanilla":
                if ensure_official_version(parent, log):
                    pdata = load_version_json(parent, visited, log, depth + 1, java_path)
        if pdata:
            data = merge_versions(pdata, data)
        else:
            if log: log(f"{indent}[!] Родитель '{parent}' не найден.")
    return data


def merge_versions(parent, child):
    out = dict(parent)
    for k, v in child.items():
        if k == "libraries":
            out["libraries"] = parent.get("libraries", []) + v
        elif k == "arguments":
            pa = out.get("arguments", {}) or {}
            ca = v or {}
            out["arguments"] = {
                "game": (pa.get("game") or []) + (ca.get("game") or []),
                "jvm":  (pa.get("jvm") or [])  + (ca.get("jvm") or []),
            }
        else:
            out[k] = v
    return out


def resolve_library_path(lib):
    return _get_lib_path(lib)

# ---------- Оптимизированная загрузка: keep-alive + пул потоков ----------

_tls = threading.local()
_SSL_CTX = ssl.create_default_context()

def _ensure_dir(p: Path):
    cache = getattr(_tls, "dirs", None)
    if cache is None:
        cache = _tls.dirs = set()
    s = str(p)
    if s in cache:
        return
    p.mkdir(parents=True, exist_ok=True)
    cache.add(s)


def _get_conn(scheme, host, port, timeout):
    pool = getattr(_tls, "pool", None)
    if pool is None:
        pool = _tls.pool = {}
    key = (scheme, host, port)
    conn = pool.get(key)
    if conn is not None:
        return conn
    if scheme == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=_SSL_CTX)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    pool[key] = conn
    return conn


def _drop_conn(scheme, host, port):
    pool = getattr(_tls, "pool", None)
    if not pool:
        return
    conn = pool.pop((scheme, host, port), None)
    if conn is not None:
        try: conn.close()
        except Exception: pass


def _http_download(url, dest: Path, timeout=60, retries=3):
    """Скачивает один файл, переиспользуя соединение из thread-local пула.
    Возвращает (ok: bool, err: str|None)."""
    from urllib.parse import urlsplit, urljoin

    parts = urlsplit(url)
    scheme, host = parts.scheme, parts.hostname
    port = parts.port or (443 if scheme == "https" else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    _ensure_dir(dest.parent)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    headers = {
        "User-Agent": "JLauncher/1.0",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    attempt = 0
    redirects = 0
    last_err = None
    while attempt <= retries:
        conn = _get_conn(scheme, host, port, timeout)
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
        except Exception as e:
            last_err = str(e)
            _drop_conn(scheme, host, port)
            attempt += 1
            continue

        if resp.status in (301, 302, 303, 307, 308):
            loc = resp.getheader("Location")
            try: resp.read()
            except Exception: pass
            if not loc or redirects > 5:
                return False, f"redirect loop ({resp.status})"
            redirects += 1
            url = urljoin(url, loc)
            parts = urlsplit(url)
            scheme, host = parts.scheme, parts.hostname
            port = parts.port or (443 if scheme == "https" else 80)
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            continue

        if resp.status != 200:
            try: resp.read()
            except Exception: pass
            return False, f"HTTP {resp.status}"

        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as e:
            last_err = str(e)
            _drop_conn(scheme, host, port)
            try: tmp.unlink()
            except Exception: pass
            attempt += 1
            continue

        try:
            tmp.replace(dest)
        except Exception as e:
            return False, str(e)
        return True, None

    return False, last_err or "unknown error"


def _download(url, dest: Path, log=None, retries=2):
    """Совместимая обёртка. Использует keep-alive пул, при провале — urllib."""
    ok, err = _http_download(url, dest)
    if ok:
        return True
    for attempt in range(retries + 1):
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 65536)
            tmp.replace(dest)
            return True
        except Exception as e:
            if attempt < retries:
                time.sleep(0.8)
                continue
            if log: log(f"[!] Скачивание {url}: {e}")
            try: tmp.unlink()
            except Exception: pass
            return False
    return False


def _download_many(tasks, log=None, progress_cb=None, prefix="Загрузка",
                   max_workers=16):
    """Параллельно скачивает список [(url, dest)]. Дедуп по dest.
    Возвращает (ok_count, fail_count, failures)."""
    # дедуп по dest — иначе гонка на один .tmp
    seen = set()
    uniq = []
    for url, dest in tasks:
        key = str(dest)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((url, dest))
    tasks = uniq

    total = len(tasks)
    if total == 0:
        return 0, 0, []

    workers = min(max_workers, total)
    done = 0
    lock = threading.Lock()
    failures = []
    last_emit = [0.0]

    def emit(force=False):
        if progress_cb is None:
            return
        now = time.time()
        if not force and (now - last_emit[0]) < 0.08:
            return
        last_emit[0] = now
        with lock:
            cur = done
        progress_cb(cur, total, prefix)

    def worker(url, dest):
        nonlocal done
        ok, err = _http_download(url, dest)
        with lock:
            if ok:
                done += 1
            else:
                failures.append((url, err))
        emit()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(worker, u, d) for u, d in tasks]
        concurrent.futures.wait(futs)

    if progress_cb:
        progress_cb(total, total, prefix)

    if log:
        if failures:
            log(f"[!] {prefix}: не удалось {len(failures)}/{total}")
            for u, e in failures[:5]:
                log(f"    - {u}: {e}")
        elif total:
            log(f"[✓] {prefix}: {done}/{total}")
    return done, len(failures), failures
def build_classpath(version_json, vdir, log=None, download=True, progress_cb=None):
    try:
        all_paths = _lib_paths_for_sig(version_json, vdir)
        sig = _file_sig(all_paths)
    except Exception:
        sig = None


    cache_file = _classpath_cache_path(vdir)
    if sig:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("sig") == sig:
                cached_cp = cached.get("classpath", [])
                if cached_cp and all(Path(p).exists() for p in cached_cp):
                    # Проверяем, есть ли в кэше jar из versions/ (client.jar).
                    # Для Fabric/vanilla он обязателен. Для Forge — не нужен.
                    mc_main = (version_json.get("mainClass") or "").lower()
                    is_forge_c = ("forge" in mc_main) or ("modlauncher" in mc_main)
                    has_client = any(
                        "/versions/" in str(p).replace("\\", "/")
                        and str(p).lower().endswith(".jar")
                        for p in cached_cp
                    )
                    if not is_forge_c and not has_client:
                        if log:
                            log("[!] Кэш без client.jar (Fabric/vanilla) — пересобираю")
                    else:
                        if log:
                            log(f"[✓] Classpath из кэша: {len(cached_cp)} JAR (мгновенно)")
                        return cached_cp
        except Exception:
            pass

    cp = []
    total = 0
    missing = []
    for lib in version_json.get("libraries", []):
        rules = lib.get("rules")
        if rules and not check_rules(rules): continue
        total += 1
        path = _get_lib_path(lib)
        if path is None: continue
        if path.exists():
            cp.append(str(path))
        else:
            missing.append((lib, path))
    if missing:
        if download:
            if log: log(f"[*] Докачиваю {len(missing)} библиотек...")
            tasks = []
            for lib, path in missing:
                url = _get_lib_url(lib)
                if url:
                    tasks.append((url, path))
            if tasks:
                _download_many(tasks, log=log, progress_cb=progress_cb,
                               prefix="Библиотеки", max_workers=16)
            # подбираем то, что реально лежит на диске
            for _, path in missing:
                if path.exists():
                    cp.append(str(path))
        else:
            if log: log(f"[!] Нет библиотек: {len(missing)}")

    main_class = (version_json.get("mainClass") or "")
    mc_low = main_class.lower()
    is_forge_client = ("forge" in mc_low) or ("modlauncher" in mc_low)

    client_jar = None
    if not is_forge_client:
        vid = vdir.name

        # 1) Свой jar в папке сборки? Используем его.
        own = sanitize_client_jar(vdir, log=None)
        if own and own.exists():
            if is_demo_client_jar(own, log):
                if log: log(f"[*] Свой jar '{own.name}' — демо, пропускаю")
                try: own.unlink()
                except Exception: pass
                own = None
        if own:
            client_jar = own
            if log: log(f"[*] client.jar: {own.name} (папка сборки)")

        # 2) Нет своего — идём по inheritsFrom к ванильному родителю
        if client_jar is None:
            if log: log(f"[dbg] в папке сборки jar'а нет, иду по inheritsFrom от '{vid}'")
            vanilla = find_vanilla_client_jar(vid, log=log)
            if vanilla and vanilla.exists():
                client_jar = vanilla
                if log: log(f"[*] client.jar: {vanilla.name} (ванильный родитель)")
            elif log:
                log(f"[!] Ванильный client.jar не найден и не скачался")
    if client_jar:
        cp.append(str(client_jar))
    if log: log(f"[*] Classpath: {len(cp)}/{total + 1}")

    if sig:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"sig": sig, "classpath": cp, "created": time.time()},
                          f, ensure_ascii=False, indent=2)
            if log:
                log("[✓] Classpath сохранён в кэш")
        except Exception:
            pass
    return cp


def ensure_assets(version_json, log=None, download=False, progress_cb=None):
    asset_index = version_json.get("assetIndex") or {}
    idx_id = asset_index.get("id") or version_json.get("assets")
    idx_url = asset_index.get("url")
    if not idx_id: return
    ASSETS_INDEXES_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_OBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    idx_path = ASSETS_INDEXES_DIR / f"{idx_id}.json"
    if not idx_path.exists() and idx_url:
        if download:
            if not _download(idx_url, idx_path, log): return
        else:
            if log: log(f"[!] Индекс {idx_id} отсутствует")
            return
    if not idx_path.exists(): return
    if not download: return

    marker = _assets_marker_path(idx_id)
    try:
        idx_mtime = idx_path.stat().st_mtime_ns
    except Exception:
        idx_mtime = 0
    if marker.exists():
        try:
            with open(marker, "r", encoding="utf-8") as f:
                mdata = json.load(f)
            if (mdata.get("idx_mtime") == idx_mtime
                    and mdata.get("count", 0) > 0):
                if log:
                    log(f"[✓] Ассеты готовы ({mdata['count']} шт.) — пропускаю проверку")
                return
        except Exception:
            pass

    try:
        with open(idx_path, "r", encoding="utf-8-sig") as f:
            idx_data = json.load(f)
    except Exception: return
    objects = idx_data.get("objects", {})
    to_download = []
    for name, obj in objects.items():
        h = obj.get("hash")
        if not h: continue
        sub = h[:2]
        dest = ASSETS_OBJECTS_DIR / sub / h
        if dest.exists(): continue
        to_download.append((name, h, sub, dest))
    if log:
        log(f"[*] Ассетов в индексе: {len(objects)}. Уже есть: {len(objects) - len(to_download)}. Скачать: {len(to_download)}")
    tasks = [(ASSETS_BASE + f"{h[:2]}/{h}", dest)
             for (name, h, sub, dest) in to_download]
    _download_many(tasks, log=log, progress_cb=progress_cb,
                   prefix="Ассеты", max_workers=32)
    try:
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"idx_mtime": idx_mtime,
                       "count": len(objects),
                       "ts": time.time()},
                      f, ensure_ascii=False)
        if log:
            log("[✓] Маркер ассетов записан — при следующем запуске проверка будет мгновенной")
    except Exception:
        pass


def _natives_has_lwjgl(natives_dir):
    if not natives_dir or not natives_dir.is_dir():
        return False
    try:
        for f in natives_dir.iterdir():
            if f.is_file() and f.name.lower() in ("lwjgl.dll", "lwjgl64.dll"):
                return True
    except Exception:
        pass
    return False


def find_existing_natives(vdir, log=None):
    n1 = vdir / "natives"
    if n1.is_dir() and _natives_has_lwjgl(n1):
        return n1
    try:
        for d in vdir.iterdir():
            if d.is_dir() and "natives" in d.name.lower() and _natives_has_lwjgl(d):
                if log: log(f"    Natives (готовые): {d}")
                return d
    except Exception:
        pass
    return None


def extract_natives(version_json, vdir, log=None, download=True, progress_cb=None):
    existing = find_existing_natives(vdir, log)
    if existing:
        if log: log("[✓] Natives уже есть и валидны")
        return existing

    natives_dir = vdir / "natives"
    if natives_dir.exists():
        if log: log("[*] Папка natives есть, но lwjgl.dll не найден — пересоздаю")
        try: shutil.rmtree(natives_dir, ignore_errors=True)
        except Exception: pass
    natives_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    candidates = []
    for lib in version_json.get("libraries", []):
        rules = lib.get("rules")
        if rules and not check_rules(rules): continue
        jar_path = None
        natives = lib.get("natives")
        if natives:
            classifier = natives.get("windows")
            if classifier:
                jar_path = _get_lib_path(lib, classifier)
                if jar_path and not jar_path.exists() and download:
                    url = _get_lib_url(lib, classifier)
                    if url:
                        _download(url, jar_path, log)
                if jar_path and not jar_path.exists():
                    jar_path = None
        if not jar_path:
            name = lib.get("name", "")
            parts = name.split(":")
            if len(parts) >= 4 and "natives-windows" in parts[3]:
                p = _get_lib_path(lib)
                if p and p.exists(): jar_path = p
                elif p and download:
                    url = _get_lib_url(lib)
                    if url:
                        _download(url, p, log)
                    if p.exists(): jar_path = p
        if jar_path and jar_path.exists():
            candidates.append(jar_path)

    total = len(candidates)
    for i, jar_path in enumerate(candidates, 1):
        try:
            with zipfile.ZipFile(jar_path, "r") as z:
                for nm in z.namelist():
                    if nm.startswith("META-INF/") or nm.endswith("/"): continue
                    z.extract(nm, natives_dir)
                    count += 1
        except Exception as e:
            if log: log(f"[!] Natives {jar_path.name}: {e}")
        if progress_cb and (i % 2 == 0 or i == total):
            progress_cb(i, total, "Natives")
    if log: log(f"[*] Natives распаковано: {count} файлов из {total} архивов.")
    return natives_dir


def collect_args(arg_list, ctx):
    out = []
    for item in arg_list:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            if "rules" in item and not check_rules(item["rules"]): continue
            v = item.get("value", [])
            if isinstance(v, str): out.append(v)
            else: out.extend(v)
    return out


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if k in cfg: cfg[k] = v
        except Exception: pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception: pass


def make_icon_image(size=64):
    img = tk.PhotoImage(width=size, height=size)
    cell = size // 8
    bg_colors = ["#4a7d4a", "#3d6b3d", "#5a8d5a"]
    dark = "#0a1a0a"
    noise = [
        "11211121", "21112112", "12211221", "21121112",
        "12112121", "21211211", "11122111", "22111221",
    ]
    for y in range(8):
        for x in range(8):
            img.put(bg_colors[int(noise[y][x])],
                    to=(x * cell, y * cell, (x + 1) * cell, (y + 1) * cell))
    face = [
        (1, 1), (2, 1), (5, 1), (6, 1),
        (1, 2), (2, 2), (5, 2), (6, 2),
        (3, 3), (4, 3),
        (2, 4), (3, 4), (4, 4), (5, 4),
        (2, 5), (3, 5), (4, 5), (5, 5),
        (2, 6), (5, 6),
    ]
    for (x, y) in face:
        img.put(dark, to=(x * cell, y * cell, (x + 1) * cell, (y + 1) * cell))
    return img


def apply_dark_titlebar(window):
    if os.name != "nt":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass

class RootsDialog(tk.Toplevel):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.parent = parent
        self.on_change = on_change

        self.title("📂 Корни игры")
        self.configure(bg=COLORS["bg"])
        self.transient(parent)
        try: self.grab_set()
        except Exception: pass
        self.geometry("680x430")
        self.minsize(560, 340)

        try:
            self.iconphoto(False, parent._icon_img)
        except Exception:
            pass

        ttk.Label(self, text="📂 Пользовательские корни",
                  style="H1.TLabel").pack(anchor="w", padx=14, pady=(14, 2))
        ttk.Label(self,
                  text="Папки, где лежит versions/ — можно выбирать .minecraft "
                       "или родителя (где game/versions или .minecraft/versions).",
                  style="Info.TLabel", wraplength=640).pack(anchor="w", padx=14, pady=(0, 8))

        self.listbox = tk.Listbox(
            self, activestyle="none", exportselection=False,
            bg=COLORS["surface2"], fg=COLORS["fg"],
            selectbackground=COLORS["accent"], selectforeground="#ffffff",
            highlightthickness=1, highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            borderwidth=0, relief="flat", font=("Consolas", 10),
        )
        self.listbox.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        btnrow = ttk.Frame(self)
        btnrow.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(btnrow, text="➕ Добавить", style="Accent.TButton",
                   command=self._add).pack(side="left", padx=(0, 4))
        ttk.Button(btnrow, text="✖ Удалить", command=self._remove).pack(side="left", padx=4)
        ttk.Button(btnrow, text="Открыть", command=self._open_selected).pack(side="left", padx=4)
        ttk.Button(btnrow, text="Закрыть", command=self.destroy).pack(side="right")

        self._reload()

    def _reload(self):
        self.listbox.delete(0, "end")
        extras = self.parent.cfg.get("extra_roots", []) or []
        for r in extras:
            marker = "✓" if Path(r).exists() else "✗"
            self.listbox.insert("end", f"  {marker}  {r}")

    def _add(self):
        chosen = filedialog.askdirectory(
            title="Выбери .minecraft или родительскую папку",
            parent=self)
        if not chosen:
            return
        norm, err = _normalize_root_choice(chosen)
        if norm is None:
            messagebox.showerror("Корни", err or "Не получилось", parent=self)
            return
        if err:
            if not messagebox.askyesno(
                "Корни",
                f"{err}\n\nВсё равно добавить:\n{norm}?\n\n"
                f"(Если versions/ появится позже — подхватится.)",
                parent=self):
                return
        s = str(norm)
        extras = self.parent.cfg.setdefault("extra_roots", [])
        if s in extras:
            messagebox.showinfo("Корни", "Эта папка уже в списке.", parent=self)
            return
        extras.append(s)
        save_config(self.parent.cfg)
        GLOBAL_CONFIG["extra_roots"] = list(extras)
        try:
            self.parent.log_line(f"[✓] Корень добавлен: {s}")
        except Exception:
            pass
        self._reload()
        self.on_change()

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        extras = self.parent.cfg.get("extra_roots", []) or []
        idx = sel[0]
        if idx >= len(extras):
            return
        removed = extras.pop(idx)
        save_config(self.parent.cfg)
        GLOBAL_CONFIG["extra_roots"] = list(extras)
        try:
            self.parent.log_line(f"[*] Корень удалён: {removed}")
        except Exception:
            pass
        self._reload()
        self.on_change()

    def _open_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        extras = self.parent.cfg.get("extra_roots", []) or []
        idx = sel[0]
        if idx >= len(extras):
            return
        p = extras[idx]
        try:
            if os.name == "nt":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            messagebox.showerror("Корни", str(e), parent=self)
class BackupsDialog(tk.Toplevel):
    def __init__(self, parent, game_dir):
        super().__init__(parent)
        self.parent = parent
        self.game_dir = Path(game_dir)

        self.title("💾 Бэкапы")
        self.configure(bg=COLORS["bg"])
        self.transient(parent)
        try: self.grab_set()
        except Exception: pass
        self.geometry("700x560")
        self.minsize(600, 460)

        try:
            self.iconphoto(False, parent._icon_img)
        except Exception:
            pass

        cfg = parent.cfg

        ttk.Label(self, text="💾 Бэкапы сохранений",
                  style="H1.TLabel").pack(anchor="w", padx=14, pady=(14, 2))
        ttk.Label(self, text=f"Папка: {self.game_dir}",
                  style="Info.TLabel", wraplength=660).pack(anchor="w", padx=14, pady=(0, 8))

        # --- Включено ---
        self.enabled_var = tk.BooleanVar(value=cfg.get("backup_enabled", True))
        ttk.Checkbutton(self, text="Автоматически создавать бэкапы",
                        variable=self.enabled_var,
                        command=self._save).pack(anchor="w", padx=14, pady=(4, 4))

        # --- Частота ---
        row_freq = ttk.Frame(self); row_freq.pack(fill="x", padx=14, pady=4)
        ttk.Label(row_freq, text="Частота:", width=18).pack(side="left")
        self.freq_var = tk.StringVar(value=cfg.get("backup_frequency", "before_launch"))
        self.freq_combo = ttk.Combobox(
            row_freq, textvariable=self.freq_var, state="readonly", width=32,
            values=["before_launch", "daily", "manual"])
        self.freq_combo.pack(side="left", padx=4)
        self.freq_combo.bind("<<ComboboxSelected>>", lambda e: self._save())
        ttk.Label(row_freq, text="before_launch = при запуске, если что-то менялось",
                  style="Info.TLabel").pack(side="left", padx=6)

        # --- Хранить ---
        row_keep = ttk.Frame(self); row_keep.pack(fill="x", padx=14, pady=4)
        ttk.Label(row_keep, text="Хранить последних:", width=18).pack(side="left")
        self.keep_var = tk.StringVar(value=str(cfg.get("backup_keep", 5)))
        keep_entry = ttk.Entry(row_keep, textvariable=self.keep_var, width=8)
        keep_entry.pack(side="left", padx=4)
        keep_entry.bind("<FocusOut>", lambda e: self._save())
        keep_entry.bind("<Return>", lambda e: self._save())

        # --- Что включать ---
        row_inc = ttk.Frame(self); row_inc.pack(fill="x", padx=14, pady=4)
        ttk.Label(row_inc, text="Что включать:", width=18).pack(side="left")
        inc_list = cfg.get("backup_include") or []
        self.include_var = tk.StringVar(value=", ".join(inc_list))
        inc_entry = ttk.Entry(row_inc, textvariable=self.include_var)
        inc_entry.pack(side="left", fill="x", expand=True, padx=4)
        inc_entry.bind("<FocusOut>", lambda e: self._save())
        inc_entry.bind("<Return>", lambda e: self._save())

        ttk.Label(self, text="Через запятую: папки и файлы относительно gameDir "
                             "(например saves, options.txt, config)",
                  style="Info.TLabel", wraplength=660).pack(anchor="w", padx=14, pady=(0, 6))

        # --- Кнопки действий ---
        act = ttk.Frame(self); act.pack(fill="x", padx=14, pady=(4, 6))
        ttk.Button(act, text="💾 Создать сейчас", style="Accent.TButton",
                   command=self._create_now).pack(side="left", padx=(0, 4))
        ttk.Button(act, text="♻ Восстановить",
                   command=self._restore_selected).pack(side="left", padx=4)
        ttk.Button(act, text="🗑 Удалить",
                   command=self._delete_selected).pack(side="left", padx=4)
        ttk.Button(act, text="Папка",
                   command=self._open_folder).pack(side="left", padx=4)

        # --- Список ---
        ttk.Label(self, text="Существующие бэкапы:",
                  style="Info.TLabel").pack(anchor="w", padx=14)
        self.listbox = tk.Listbox(
            self, activestyle="none", exportselection=False,
            bg=COLORS["surface2"], fg=COLORS["fg"],
            selectbackground=COLORS["accent"], selectforeground="#ffffff",
            highlightthickness=1, highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            borderwidth=0, relief="flat", font=("Consolas", 10),
        )
        self.listbox.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self._reload_list()

    def _save(self):
        cfg = self.parent.cfg
        cfg["backup_enabled"] = bool(self.enabled_var.get())
        cfg["backup_frequency"] = self.freq_var.get()
        try:
            cfg["backup_keep"] = max(1, int(self.keep_var.get()))
        except Exception:
            pass
        inc = [x.strip() for x in self.include_var.get().split(",") if x.strip()]
        cfg["backup_include"] = inc
        save_config(cfg)
        GLOBAL_CONFIG.update(cfg)

    def _reload_list(self):
        self.listbox.delete(0, "end")
        for path, mtime, size in _backup_list(self.game_dir):
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            mb = size / (1024 * 1024)
            self.listbox.insert("end", f"  {ts}   {mb:7.2f} МБ   {path.name}")

    def _create_now(self):
        self._save()
        self.parent.log_line("[*] Создаю бэкап вручную...")
        def worker():
            ok, path, err = create_backup(self.game_dir, log=self.parent.log_line, cfg=self.parent.cfg)
            def done():
                if ok:
                    self.parent.log_line(f"[✓] Бэкап создан: {path.name}")
                else:
                    self.parent.log_line(f"[!] Бэкап не создан: {err}")
                self._reload_list()
            try: self.after(0, done)
            except Exception: pass
        threading.Thread(target=worker, daemon=True).start()

    def _restore_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        backups = _backup_list(self.game_dir)
        idx = sel[0]
        if idx >= len(backups):
            return
        path, mtime, size = backups[idx]
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        if not messagebox.askyesno(
            "Восстановить",
            f"Восстановить из:\n\n  {path.name}\n  от {ts}\n  {size/1024/1024:.2f} МБ\n\n"
            f"Текущие файлы в gameDir будут ПЕРЕЗАПИСАНЫ (не удалены, но заменены).\n"
            f"Продолжить?",
            parent=self):
            return
        self.parent.log_line(f"[*] Восстанавливаю из {path.name}...")
        def worker():
            ok, err = restore_backup(path, self.game_dir, log=self.parent.log_line)
            def done():
                if ok:
                    self.parent.log_line("[✓] Готово. Запусти сборку заново.")
                    messagebox.showinfo("Восстановлено",
                        "Файлы распакованы. Запусти сборку.", parent=self)
                else:
                    self.parent.log_line(f"[!] Не восстановить: {err}")
                    messagebox.showerror("Ошибка", str(err), parent=self)
            try: self.after(0, done)
            except Exception: pass
        threading.Thread(target=worker, daemon=True).start()

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        backups = _backup_list(self.game_dir)
        idx = sel[0]
        if idx >= len(backups):
            return
        path, _, _ = backups[idx]
        if not messagebox.askyesno("Удалить", f"Удалить {path.name}?", parent=self):
            return
        try:
            path.unlink()
            self.parent.log_line(f"[*] Удалён {path.name}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
        self._reload_list()

    def _open_folder(self):
        root = _backup_root(self.game_dir)
        try:
            root.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(root))
            else:
                subprocess.Popen(["xdg-open", str(root)])
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)           
# ---------- Бэкапы ----------

BACKUP_DIR_NAME = ".jlauncher_backups"


def _backup_root(game_dir):
    return Path(game_dir) / BACKUP_DIR_NAME


def _backup_list(game_dir):
    """Список (path, mtime, size) — от новых к старым."""
    root = _backup_root(game_dir)
    if not root.is_dir():
        return []
    out = []
    for f in root.glob("backup_*.zip"):
        try:
            st = f.stat()
            out.append((f, st.st_mtime, st.st_size))
        except Exception:
            pass
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _newest_mtime_in(game_dir, items):
    newest = 0.0
    for item in items:
        p = Path(game_dir) / item
        if not p.exists():
            continue
        try:
            if p.is_file():
                m = p.stat().st_mtime
                if m > newest:
                    newest = m
            elif p.is_dir():
                for f in p.rglob("*"):
                    if not f.is_file():
                        continue
                    if BACKUP_DIR_NAME in f.parts:
                        continue
                    try:
                        m = f.stat().st_mtime
                        if m > newest:
                            newest = m
                    except Exception:
                        pass
        except Exception:
            pass
    return newest


def _backup_should_run(game_dir, cfg):
    if not cfg.get("backup_enabled", True):
        return False
    freq = cfg.get("backup_frequency", "before_launch")
    if freq == "manual":
        return False

    backups = _backup_list(game_dir)
    last_ts = backups[0][1] if backups else 0

    if freq == "daily":
        if last_ts == 0:
            return True
        return (time.time() - last_ts) / 3600.0 >= 24.0

    if freq == "before_launch":
        if last_ts == 0:
            return True
        include = cfg.get("backup_include") or []
        newest = _newest_mtime_in(game_dir, include)
        return newest > last_ts

    return False


def _backup_rotate(game_dir, keep):
    backups = _backup_list(game_dir)
    for path, _, _ in backups[keep:]:
        try:
            path.unlink()
        except Exception:
            pass


def create_backup(game_dir, log=None, cfg=None):
    """Создаёт zip-бэкап. Возвращает (ok, path, err)."""
    if cfg is None:
        cfg = GLOBAL_CONFIG
    game_dir = Path(game_dir)
    if not game_dir.is_dir():
        return (False, None, "gameDir не существует")

    include = [x for x in (cfg.get("backup_include") or []) if x and x.strip()]
    if not include:
        return (False, None, "список пуст")

    root = _backup_root(game_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return (False, None, f"не создать папку бэкапов: {e}")

    ts = time.strftime("%Y-%m-%d_%H-%M-%S")
    out_path = root / f"backup_{ts}.zip"
    tmp_path = out_path.with_suffix(".zip.tmp")

    file_count = 0
    src_bytes = 0
    skipped_missing = []

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for item in include:
                src = game_dir / item
                if not src.exists():
                    skipped_missing.append(item)
                    continue
                if src.is_file():
                    z.write(src, arcname=item)
                    file_count += 1
                    try: src_bytes += src.stat().st_size
                    except Exception: pass
                elif src.is_dir():
                    for f in src.rglob("*"):
                        if not f.is_file():
                            continue
                        if BACKUP_DIR_NAME in f.parts:
                            continue
                        try:
                            rel = f.relative_to(game_dir)
                        except Exception:
                            continue
                        z.write(f, arcname=str(rel))
                        file_count += 1
                        try: src_bytes += f.stat().st_size
                        except Exception: pass
        tmp_path.replace(out_path)
    except Exception as e:
        try: tmp_path.unlink()
        except Exception: pass
        return (False, None, str(e))

    if file_count == 0:
        try: out_path.unlink()
        except Exception: pass
        if log: log("[!] Бэкап не создан — нечего сохранять")
        return (False, None, "нечего сохранять")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    src_mb = src_bytes / (1024 * 1024)
    if log:
        log(f"[✓] Бэкап: {out_path.name} "
            f"({file_count} файлов, {src_mb:.1f} МБ → {size_mb:.1f} МБ)")
        if skipped_missing:
            log(f"    Пропущено (нет в gameDir): {', '.join(skipped_missing)}")

    keep = int(cfg.get("backup_keep", 5) or 5)
    _backup_rotate(game_dir, keep)
    return (True, out_path, None)


def restore_backup(zip_path, game_dir, log=None):
    """Распаковывает бэкап поверх gameDir."""
    zip_path = Path(zip_path)
    game_dir = Path(game_dir)
    if not zip_path.is_file():
        return (False, "файл бэкапа не найден")
    if not game_dir.is_dir():
        return (False, "gameDir не существует")
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                parts = Path(name).parts
                if name.startswith("/") or name.startswith("\\") or ".." in parts:
                    return (False, f"опасный путь в архиве: {name}")
            z.extractall(game_dir)
        if log:
            log(f"[✓] Восстановлено из {zip_path.name}")
        return (True, None)
    except Exception as e:
        return (False, str(e))
class InstallDialog(tk.Toplevel):
    def __init__(self, parent, log_fn, javas, current_java, on_done):
        super().__init__(parent)
        self.log = log_fn
        self.javas = javas
        self.current_java = current_java
        self.on_done = on_done

        self.title("📦 Установить новую версию")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass
        self.geometry("620x450")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        try:
            self.iconphoto(False, parent._icon_img)
        except Exception:
            pass

        self.mc_var = tk.StringVar()
        self.loader_var = tk.StringVar(value="vanilla")
        self.loader_ver_var = tk.StringVar()
        self.java_var = tk.StringVar()
        self.name_var = tk.StringVar(value="")

        self._mc_list = []
        self._loader_list = []
        self._build_ui()

        self.after(50, self._load_manifest_async)

    def _build_ui(self):
        c = COLORS
        style = ttk.Style(self)
        pad = 14

        title = ttk.Label(self, text="📦 Установка новой версии",
                          style="H1.TLabel")
        title.pack(anchor="w", padx=pad, pady=(pad, 4))

        info = ttk.Label(self, text="Выбери MC, загрузчик и имя сборки. "
                                    "Лаунчер скачает всё сам.",
                         style="Info.TLabel")
        info.pack(anchor="w", padx=pad, pady=(0, 10))

        row1 = ttk.Frame(self)
        row1.pack(fill="x", padx=pad, pady=4)
        ttk.Label(row1, text="MC-версия:", width=18).pack(side="left")
        self.mc_combo = ttk.Combobox(row1, textvariable=self.mc_var,
                                     values=[], state="readonly", width=36)
        self.mc_combo.pack(side="left", padx=4)
        self.mc_combo.bind("<<ComboboxSelected>>", lambda e: self._on_mc_change())

        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=pad, pady=4)
        ttk.Label(row2, text="Загрузчик:", width=18).pack(side="left")
        self.loader_combo = ttk.Combobox(row2, textvariable=self.loader_var,
                                          values=["vanilla", "forge", "fabric"],
                                          state="readonly", width=36)
        self.loader_combo.pack(side="left", padx=4)
        self.loader_combo.bind("<<ComboboxSelected>>", lambda e: self._on_loader_change())

        row3 = ttk.Frame(self)
        row3.pack(fill="x", padx=pad, pady=4)
        ttk.Label(row3, text="Версия загрузчика:", width=18).pack(side="left")
        self.loader_ver_combo = ttk.Combobox(row3, textvariable=self.loader_ver_var,
                                              values=[], state="readonly", width=36)
        self.loader_ver_combo.pack(side="left", padx=4)

        row4 = ttk.Frame(self)
        row4.pack(fill="x", padx=pad, pady=4)
        ttk.Label(row4, text="Java:", width=18).pack(side="left")
        self.java_combo = ttk.Combobox(row4, textvariable=self.java_var,
                                        values=[], state="readonly", width=36)
        self.java_combo.pack(side="left", padx=4)
        self._fill_javas()

        row5 = ttk.Frame(self)
        row5.pack(fill="x", padx=pad, pady=4)
        ttk.Label(row5, text="Имя сборки:", width=18).pack(side="left")
        self.name_entry = ttk.Entry(row5, textvariable=self.name_var, width=38)
        self.name_entry.pack(side="left", padx=4)

        hint = ttk.Label(self,
                         text="(необязательно — если пусто, будет имя загрузчика)",
                         style="Info.TLabel")
        hint.pack(anchor="w", padx=pad + 18, pady=(0, 4))

        self.status_var = tk.StringVar(value="Загрузка списка версий...")
        status = ttk.Label(self, textvariable=self.status_var,
                           style="Info.TLabel")
        status.pack(anchor="w", padx=pad, pady=(6, 4))

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=pad, pady=(4, pad))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right")
        self.install_btn = ttk.Button(btns, text="▶  Установить",
                                       style="Accent.TButton",
                                       command=self._do_install,
                                       state="disabled")
        self.install_btn.pack(side="right", padx=6)

    def _fill_javas(self):
        vals = []
        for v in sorted(self.javas.keys()):
            for p in self.javas[v]:
                vals.append(f"Java {v}  ::  {p}")
        self.java_combo.config(values=vals)
        chosen = self.current_java
        if chosen:
            for v, paths in self.javas.items():
                if chosen in paths:
                    self.java_var.set(f"Java {v}  ::  {chosen}")
                    break
        elif vals:
            self.java_var.set(vals[0])

    def _load_manifest_async(self):
        def worker():
            try:
                versions = fetch_manifest_versions(log=None)
            except Exception as e:
                self.log(f"[!] Не удалось получить манифест Mojang: {e}")
                versions = []
            def apply():
                if not self.winfo_exists():
                    return
                self._mc_list = versions
                ids = [v["id"] for v in versions]
                self.mc_combo.config(values=ids)
                if ids:
                    self.mc_var.set(ids[0])
                    self.status_var.set(f"Найдено MC-версий: {len(ids)}. Выбери загрузчик.")
                    self._on_mc_change()
                else:
                    self.status_var.set("Не удалось получить список версий. Проверь интернет.")
            try:
                self.after(0, apply)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _on_mc_change(self):
        loader = self.loader_var.get()
        self._load_loader_versions(loader)

    def _on_loader_change(self):
        self._load_loader_versions(self.loader_var.get())

    def _load_loader_versions(self, loader):
        mc = self.mc_var.get()
        if not mc:
            return
        if loader == "vanilla":
            self.loader_ver_combo.config(values=[])
            self.loader_ver_var.set("")
            self.status_var.set(f"Будет установлена ванильная {mc}.")
            self.install_btn.config(state="normal")
            return

        self.status_var.set(f"Загрузка версий {loader} для MC {mc}...")
        self.install_btn.config(state="disabled")

        def worker():
            if loader == "forge":
                vers = get_forge_versions(mc, log=None)
            elif loader == "fabric":
                vers = get_fabric_versions(mc, log=None)
            else:
                vers = []
            def apply():
                if not self.winfo_exists():
                    return
                self._loader_list = vers
                self.loader_ver_combo.config(values=vers)
                if vers:
                    self.loader_ver_var.set(vers[0])
                    self.status_var.set(f"Найдено версий {loader}: {len(vers)}. "
                                        f"Выбрана последняя.")
                    self.install_btn.config(state="normal")
                else:
                    self.loader_ver_var.set("")
                    self.status_var.set(f"Нет доступных версий {loader} для MC {mc}. "
                                        f"Проверь совместимость.")
                    self.install_btn.config(state="disabled")
            try:
                self.after(0, apply)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _do_install(self):
        mc = self.mc_var.get()
        loader = self.loader_var.get()
        loader_ver = self.loader_ver_var.get()

        if not mc:
            self.status_var.set("Выбери MC-версию.")
            return

        java_val = self.java_var.get()
        m = re.match(r"Java \d+\s+::\s+(.+)$", java_val)
        java_path = m.group(1).strip() if m else self.current_java
        if not java_path or not Path(java_path).exists():
            self.status_var.set("Java не найдена.")
            return

        need = max(17, required_java_base(mc))
        actual = java_major_version(java_path)
        if actual is None or actual < need:
            better = pick_java(self.javas, need)
            if better:
                java_path = better
                actual = java_major_version(java_path)
                self.log(f"[*] Автовыбор Java для инсталлера: {java_path} (Java {actual})")
            else:
                self.status_var.set(f"Нужна Java {need}+.")
                return

        self.install_btn.config(state="disabled")
        self.status_var.set(f"Установка {loader} {loader_ver} для MC {mc}...")

        def worker():
            ok = False
            try:
                if loader == "vanilla":
                    self.log(f"[*] Установка ванильной MC {mc}...")
                    ok = ensure_official_version(mc, self.log)
                    if ok:
                        self.log(f"[✓] Vanilla {mc} установлена. "
                                 f"Библиотеки и ассеты докачаются при первом запуске.")
                elif loader == "forge":
                    if not loader_ver:
                        self.log("[!] Не выбрана версия Forge.")
                    else:
                        ok = download_and_install_forge(mc, loader_ver, java_path, self.log)
                elif loader == "fabric":
                    if not loader_ver:
                        self.log("[!] Не выбрана версия Fabric.")
                    else:
                        ok = download_and_install_fabric(mc, loader_ver, java_path, self.log)

                if ok:
                    pack_name = self.name_var.get().strip()
                    if pack_name:
                        root = _current_launcher_root()
                        inherits_id = find_installed_loader_id(mc, loader, loader_ver)
                        cok, real_id = create_pack_dir(root, pack_name, mc, inherits_id, self.log)
                        if cok:
                            self.log(f"[✓] Сборка '{real_id}' готова к запуску.")
                        else:
                            self.log(f"[!] Не удалось создать папку сборки, "
                                     f"но загрузчик установлен — можешь запустить {inherits_id}")
            except Exception:
                self.log("[!] Ошибка установки:\n" + traceback.format_exc())
                ok = False

            def finish():
                if not self.winfo_exists():
                    return
                if ok:
                    self.status_var.set("✓ Установлено! Обнови список (F5).")
                    self.log("[✓] Установка завершена.")
                    try:
                        self.on_done()
                    except Exception:
                        pass
                    self.after(1500, self.destroy)
                else:
                    self.status_var.set("✗ Не удалось установить. Смотри лог.")
                    self.install_btn.config(state="normal")

            try:
                self.after(0, finish)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        GLOBAL_CONFIG.clear()
        GLOBAL_CONFIG.update(self.cfg)

        initial_root = Path(self.cfg["game_dir"])
        _set_root(initial_root)

        self.title("JLauncher")
        saved_geo = self.cfg.get("window_geometry") or "980x820"
        if saved_geo == "zoomed":
            self.geometry("980x820")
        else:
            self.geometry(saved_geo)
        self.minsize(880, 700)
        self.configure(bg=COLORS["bg"])
        if os.name == "nt":
            try:
                self.state("zoomed")
            except Exception:
                pass

        try:
            self._icon_img = make_icon_image(64)
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        self.javas = {}
        self.versions_info = []
        self._current_java = None
        self._current_version_id = None
        self._current_root = None
        self._progress_mark = None
        self._log_queue = queue.Queue()
        self._last_output_ts = time.time()
        self._running_proc = None
        self._running_pid = None

        self._apply_theme()
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda e: self.refresh())
        self.bind("<Control-k>", lambda e: self.stop_game())
        self.bind("<Control-K>", lambda e: self.stop_game())
        self.after(80, self.refresh)
        self.after(50, self._drain_log_queue)
        self.after(200, lambda: apply_dark_titlebar(self))

    def _apply_theme(self):
        c = COLORS
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        self.option_add("*TCombobox*Listbox.background", c["surface2"])
        self.option_add("*TCombobox*Listbox.foreground", c["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

        style.configure(".",
            background=c["bg"], foreground=c["fg"],
            fieldbackground=c["surface2"], bordercolor=c["border"],
            lightcolor=c["bg"], darkcolor=c["bg"],
            troughcolor=c["surface"],
            focuscolor=c["accent"],
            font=("Segoe UI", 10),
        )
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("Info.TLabel", background=c["bg"], foreground=c["fg_dim"],
                        font=("Segoe UI", 9))
        style.configure("H1.TLabel", background=c["bg"], foreground=c["fg"],
                        font=("Segoe UI", 13, "bold"))

        style.configure("TButton",
            background=c["surface2"], foreground=c["fg"],
            borderwidth=0, relief="flat",
            padding=(12, 7), font=("Segoe UI", 10),
            focuscolor=c["accent"],
        )
        style.map("TButton",
            background=[("active", c["border"]),
                        ("pressed", c["accent_p"]),
                        ("disabled", c["surface"])],
            foreground=[("disabled", c["fg_dim"])],
        )
        style.configure("Accent.TButton",
            background=c["accent"], foreground="#ffffff",
            padding=(16, 8), font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton",
            background=[("active", c["accent_h"]),
                        ("pressed", c["accent_p"]),
                        ("disabled", c["surface2"])],
            foreground=[("disabled", c["fg_dim"])],
        )
        style.configure("Danger.TButton",
            background=c["danger"], foreground="#ffffff",
            padding=(14, 7),
        )
        style.map("Danger.TButton",
            background=[("active", c["danger_h"]),
                        ("pressed", c["danger"]),
                        ("disabled", c["surface2"])],
            foreground=[("disabled", c["fg_dim"])],
        )
        style.configure("Donate.TButton",
            background=c["surface"], foreground=c["fg_dim"],
            padding=(10, 5), font=("Segoe UI", 9),
        )
        style.map("Donate.TButton",
            background=[("active", c["surface2"]),
                        ("pressed", c["border"])],
            foreground=[("active", c["accent_h"])],
        )

        style.configure("TCheckbutton",
            background=c["bg"], foreground=c["fg"],
            focuscolor=c["accent"], padding=(4, 2),
        )
        style.map("TCheckbutton",
            background=[("active", c["bg"])],
            foreground=[("active", c["accent_h"]),
                        ("selected", c["accent"])],
        )
        style.configure("TEntry",
            fieldbackground=c["surface2"], foreground=c["fg"],
            bordercolor=c["border"], insertcolor=c["fg"],
            padding=(8, 6),
        )
        style.map("TEntry",
            bordercolor=[("focus", c["accent"])],
            fieldbackground=[("disabled", c["surface"])],
        )
        style.configure("TCombobox",
            fieldbackground=c["surface2"], background=c["surface2"],
            foreground=c["fg"], arrowcolor=c["fg"],
            bordercolor=c["border"], padding=(8, 5),
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", c["surface2"])],
            bordercolor=[("focus", c["accent"])],
            arrowcolor=[("active", c["accent_h"])],
        )

    def _build_ui(self):
        c = COLORS

        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(12, 6))

        ttk.Label(top, text="Ник:").pack(side="left")
        self.name_var = tk.StringVar(value=self.cfg["username"])
        ttk.Entry(top, textvariable=self.name_var, width=18).pack(side="left", padx=(6, 16))

        ttk.Label(top, text="RAM (МБ):").pack(side="left")
        self.ram_var = tk.StringVar(value=str(self.cfg["ram_mb"]))
        ttk.Entry(top, textvariable=self.ram_var, width=8).pack(side="left", padx=(6, 6))
        ttk.Button(top, text="Auto", command=self.auto_ram).pack(side="left", padx=2)
        ttk.Button(top, text="⟳ Обновить (F5)", command=self.refresh).pack(side="right")

        opts = ttk.Frame(self)
        opts.pack(fill="x", padx=14, pady=(0, 6))
        self.dl_libs_var = tk.BooleanVar(value=self.cfg.get("download_libraries", True))
        ttk.Checkbutton(opts, text="Качать библиотеки", variable=self.dl_libs_var).pack(side="left")
        self.dl_assets_var = tk.BooleanVar(value=self.cfg.get("download_assets", True))
        ttk.Checkbutton(opts, text="Качать ассеты", variable=self.dl_assets_var).pack(side="left", padx=14)

        jrow = ttk.Frame(self)
        jrow.pack(fill="x", padx=14, pady=(0, 6))
        ttk.Label(jrow, text="Java:").pack(side="left")
        self.java_var = tk.StringVar()
        self.java_combo = ttk.Combobox(jrow, textvariable=self.java_var,
                                       values=[], state="readonly")
        self.java_combo.pack(side="left", padx=6, fill="x", expand=True)
        self.java_combo.bind("<<ComboboxSelected>>", self._on_java_chosen)

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=14, pady=(4, 0))
        ttk.Label(mid, text="Версии (со всех .minecraft):", style="Info.TLabel").pack(anchor="w")
        self.listbox = tk.Listbox(
            mid, height=8, activestyle="none", exportselection=False,
            bg=c["surface2"], fg=c["fg"],
            selectbackground=c["accent"], selectforeground="#ffffff",
            highlightthickness=1, highlightbackground=c["border"],
            highlightcolor=c["accent"],
            borderwidth=0, relief="flat",
            font=("Segoe UI", 10),
            selectborderwidth=0,
        )
        self.listbox.pack(fill="both", expand=True, pady=(4, 6))
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._on_version_selected())

        info = ttk.Frame(self)
        info.pack(fill="x", padx=14)
        self.info_var = tk.StringVar(value="")
        ttk.Label(info, textvariable=self.info_var, style="Info.TLabel").pack(anchor="w")

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=14, pady=(8, 8))
        ttk.Button(btns, text="📦 Установить", command=self.open_install_dialog).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Java", command=self.show_javas).pack(side="left", padx=2)
        ttk.Button(btns, text="JSON", command=self.dump_raw).pack(side="left", padx=2)
        ttk.Button(btns, text="MC-версия", command=self.ask_mc_version).pack(side="left", padx=2)
        ttk.Button(btns, text="Папка", command=self._open_game_dir).pack(side="left", padx=2)
        ttk.Button(btns, text="📂 Корни", command=self.open_roots_dialog).pack(side="left", padx=2)
        ttk.Button(btns, text="💾 Бэкапы", command=self.open_backups_dialog).pack(side="left", padx=2)
        ttk.Button(btns, text="Лог", command=self.save_log).pack(side="left", padx=2)
        ttk.Button(btns, text="Копировать", command=self.copy_log).pack(side="left", padx=2)
        ttk.Button(btns, text="Очистить", command=lambda: self.log.delete("1.0", "end")).pack(side="left", padx=2)

        self.stop_btn = ttk.Button(btns, text="■ Остановить", style="Danger.TButton",
                                   command=self.stop_game, state="disabled")
        self.stop_btn.pack(side="right", padx=(6, 0))
        self.launch_btn = ttk.Button(btns, text="▶  ЗАПУСТИТЬ", style="Accent.TButton",
                                     command=self.launch)
        self.launch_btn.pack(side="right")

        self.log = scrolledtext.ScrolledText(
            self, height=16,
            bg=c["log_bg"], fg=c["log_fg"],
            insertbackground=c["log_fg"],
            selectbackground=c["accent"], selectforeground="#ffffff",
            font=("Consolas", 9),
            borderwidth=0, highlightthickness=1,
            highlightbackground=c["border"], highlightcolor=c["accent"],
            relief="flat",
        )
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        donate_row = ttk.Frame(self)
        donate_row.pack(fill="x", padx=14, pady=(0, 10))
        self.donate_btn = ttk.Button(
            donate_row,
            text=DONATE_LABEL,
            style="Donate.TButton",
            command=self.open_donate,
        )
        self.donate_btn.pack(side="right")

    def log_line(self, text=""):
        self._log_queue.put(("line", str(text)))

    def log_progress(self, text):
        self._log_queue.put(("progress", str(text)))

    def log_progress_done(self, final_text=None):
        self._log_queue.put(("progress_done", final_text))

    def _drain_log_queue(self):
        try:
            batch = 0
            last_progress = None
            while batch < 200:
                try:
                    kind, payload = self._log_queue.get_nowait()
                except queue.Empty:
                    break
                batch += 1
                if kind == "progress":
                    last_progress = payload
                    continue
                if last_progress is not None:
                    self._insert_progress(last_progress)
                    last_progress = None
                if kind == "line":
                    self._insert_line(payload)
                elif kind == "progress_done":
                    self._insert_progress_done(payload)
            if last_progress is not None:
                self._insert_progress(last_progress)
            self._trim_log()
        except Exception:
            pass
        finally:
            try:
                self.after(50, self._drain_log_queue)
            except tk.TclError:
                pass

    def _insert_line(self, text):
        try:
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self._progress_mark = None
        except tk.TclError:
            pass

    def _insert_progress(self, text):
        try:
            if self._progress_mark is not None:
                end_mark = self._progress_mark + " lineend + 1c"
                self.log.delete(self._progress_mark, end_mark)
            self._progress_mark = self.log.index("end-1c linestart")
            self.log.insert("end", text + "\n")
            self.log.see("end")
        except tk.TclError:
            self._progress_mark = None
            self._insert_line(text)

    def _insert_progress_done(self, final_text):
        try:
            if self._progress_mark is not None:
                end_mark = self._progress_mark + " lineend + 1c"
                self.log.delete(self._progress_mark, end_mark)
        except tk.TclError:
            pass
        self._progress_mark = None
        if final_text:
            self._insert_line(final_text)

    def _trim_log(self):
        try:
            line_count = int(self.log.index("end-1c").split(".")[0])
            if line_count > 5000:
                self.log.delete("1.0", f"{line_count - 5000}.0")
        except Exception:
            pass

    def open_install_dialog(self):
        if not self.javas:
            self.log_line("[!] Java не найдена. Сначала установи Java.")
            return
        InstallDialog(self, self.log_line, self.javas,
                      self._current_java, on_done=self._on_install_done)

    def _on_install_done(self):
        try:
            self.after(100, self.refresh)
        except Exception:
            pass

    def stop_game(self):
        proc = self._running_proc
        pid = self._running_pid
        if not proc or not pid or proc.poll() is not None:
            self.log_line("[*] Процесс уже завершён.")
            return
        self.log_line(f"[*] Останавливаю Minecraft (PID={pid})...")

        def _killer():
            try:
                try:
                    proc.terminate()
                except Exception:
                    pass
                for _ in range(6):
                    if proc.poll() is not None:
                        self.log_line("[✓] Процесс завершился мягко.")
                        return
                    time.sleep(0.5)
                if proc.poll() is None:
                    self.log_line("[!] Мягко не вышел, убиваю дерево процессов...")
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True, timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                    else:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                if proc.poll() is not None:
                    self.log_line(f"[✓] Процесс убит (код {proc.returncode}).")
                else:
                    self.log_line("[!] Не удалось завершить процесс. Попробуй диспетчер задач.")
            except Exception as e:
                self.log_line(f"[!] Ошибка остановки: {e}")

        threading.Thread(target=_killer, daemon=True).start()

    def open_donate(self):
        try:
            import webbrowser
            webbrowser.open(DONATE_URL, new=2)
            self.log_line(f"[*] Открываю страницу доната: {DONATE_URL}")
        except Exception as e:
            self.log_line(f"[!] Не удалось открыть ссылку: {e}")
            messagebox.showerror("JLauncher",
                                 f"Не удалось открыть браузер.\nСсылка: {DONATE_URL}",
                                 parent=self)

    def ask_yes_no(self, title, message):
        result = {"value": False}
        done = threading.Event()
        def show():
            try:
                result["value"] = messagebox.askyesno(title, message, parent=self)
            finally:
                done.set()
        self.after(0, show)
        done.wait()
        return result["value"]

    def auto_ram(self):
        vid = self._current_version_id
        rec = recommend_ram_mb(vid)
        self.ram_var.set(str(rec))
        self.log_line(f"[*] RAM: {total_ram_mb()} МБ. Рекомендую: {rec} МБ.")

    def refresh(self):
        cleanup_temp_files()
        cleanup_auto_delete_mods_all(log=self.log_line)
        self.log_line("[*] Поиск Java...")
        ttl = self.cfg.get("javas_cache_ttl_h", 12)
        self.javas = find_javas_cached(ttl_hours=ttl, log=self.log_line)
        for v, paths in sorted(self.javas.items()):
            self.log_line(f"    Java {v}: {paths[0]}")
        if not self.javas:
            self.log_line("[!] Java не найдена.")

        self.log_line("[*] Поиск .minecraft-корней...")
        self.versions_info = scan_all_versions(log=self.log_line)

        self.listbox.delete(0, "end")
        for entry in self.versions_info:
            self.listbox.insert("end", entry["display"])
        self.log_line(f"[*] Версий: {len(self.versions_info)}")

        last_display = self.cfg.get("last_version")
        if last_display:
            for i, entry in enumerate(self.versions_info):
                if entry["display"] == last_display:
                    self.listbox.selection_set(i)
                    self.listbox.see(i)
                    self._on_version_selected()
                    break

    def _on_version_selected(self):
        sel = self.listbox.curselection()
        if not sel: return
        entry = self.versions_info[sel[0]]
        version_id = entry["id"]
        root = entry["root"]
        display = entry["display"]

        _set_root(root)
        self._current_root = root
        self.cfg["game_dir"] = str(root)
        self.cfg["last_version"] = display
        self._current_version_id = version_id

        try:
            vjson = load_version_json(version_id, log=None, java_path=self._current_java)
        except Exception:
            vjson = None
        need = required_java_full(version_id, vjson, log=None)

        values = []
        for v in sorted(self.javas.keys()):
            for p in self.javas[v]:
                values.append(f"Java {v}  ::  {p}")
        self.java_combo.config(values=values)

        saved = self.cfg.get("java_by_version", {}).get(version_id)
        if saved and Path(saved).exists():
            chosen = saved
        else:
            chosen = pick_java(self.javas, need)

        if chosen:
            for v, paths in self.javas.items():
                if chosen in paths:
                    self.java_var.set(f"Java {v}  ::  {chosen}")
                    break
        else:
            self.java_var.set("")

        self._current_java = chosen
        short = _short_root_name(root)
        self.info_var.set(f"{display}  [{short}]  •  Java {need}+  •  " +
                          (chosen if chosen else "Java НЕ НАЙДЕНА"))
        save_config(self.cfg)

    def _on_java_chosen(self, *_):
        val = self.java_var.get()
        m = re.match(r"Java \d+\s+::\s+(.+)$", val)
        if not m: return
        path = m.group(1).strip()
        self._current_java = path
        vid = self._current_version_id
        if not vid:
            sel = self.listbox.curselection()
            if sel: vid = self.versions_info[sel[0]]["id"]
        if vid:
            self.cfg.setdefault("java_by_version", {})[vid] = path
            save_config(self.cfg)
            self.info_var.set(f"{vid}   •   Java: {path} (сохранено)")

    def ask_mc_version(self):
        sel = self.listbox.curselection()
        if not sel:
            self.log_line("[!] Выбери версию.")
            return
        entry = self.versions_info[sel[0]]
        version_id = entry["id"]
        current = self.cfg.get("manual_mc_version", {}).get(version_id, "")
        answer = simpledialog.askstring("Указать MC-версию",
            f"Для '{entry['display']}' укажи версию Minecraft\n(например 1.19.2, 1.12.2):",
            initialvalue=current, parent=self)
        if not answer: return
        answer = answer.strip()
        if not re.match(r'^\d+\.\d+(\.\d+)?$', answer):
            self.log_line(f"[!] '{answer}' не похоже на MC.")
            return
        self.cfg.setdefault("manual_mc_version", {})[version_id] = answer
        save_config(self.cfg)
        self.log_line(f"[✓] MC для '{entry['display']}': {answer}")

    def show_javas(self):
        self.log_line("--- Java ---")
        for v, paths in sorted(self.javas.items()):
            for p in paths:
                self.log_line(f"  Java {v}: {p}")
    def open_backups_dialog(self):
        sel = self.listbox.curselection()
        game_dir = None
        if sel:
            entry = self.versions_info[sel[0]]
            vdir = entry["path"]
            game_dir = detect_game_dir(vdir, log=None)
        if game_dir is None:
            game_dir = self._current_root or GAME_DIR
        BackupsDialog(self, game_dir)
    def open_roots_dialog(self):
        RootsDialog(self, on_change=self._on_roots_changed)

    def _on_roots_changed(self):
        try:
            self.refresh()
        except Exception:
            pass
    def _open_game_dir(self):
        try:
            target = self._current_root or GAME_DIR
            if os.name == "nt": os.startfile(str(target))
            else: subprocess.Popen(["xdg-open", str(target)])
        except Exception as e:
            self.log_line(f"[!] {e}")

    def save_log(self):
        text = self.log.get("1.0", "end")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Log", "*.log"), ("All", "*.*")],
            initialfile="jlauncher.log", parent=self)
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.log_line(f"[✓] Лог: {path}")
        except Exception as e:
            self.log_line(f"[!] {e}")

    def copy_log(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.log.get("1.0", "end"))
            self.log_line("[✓] Лог скопирован.")
        except Exception as e:
            self.log_line(f"[!] {e}")

    def dump_raw(self):
        sel = self.listbox.curselection()
        if not sel:
            self.log_line("[!] Выбери версию.")
            return
        entry = self.versions_info[sel[0]]
        version_id = entry["id"]
        root = entry["root"]
        old_root = GAME_DIR
        _set_root(root)
        try:
            vdir = VERSIONS_DIR / version_id
            self.log_line(f"\n--- JSON {entry['display']} [{root}] ---")
            if not vdir.exists():
                self.log_line("[!] Нет папки.")
                return
            for j in sorted(vdir.glob("*.json")):
                self.log_line(f"\n>>> {j.name}")
                try:
                    with open(j, "r", encoding="utf-8-sig", errors="replace") as f:
                        for line in f.read().splitlines()[:60]:
                            self.log_line("  | " + line)
                except Exception as e:
                    self.log_line(f"[!] {e}")
        finally:
            _set_root(old_root)

    def launch(self):
        sel = self.listbox.curselection()
        if not sel:
            self.log_line("[!] Выбери версию.")
            return
        if self._running_proc and self._running_proc.poll() is None:
            self.log_line("[!] Игра уже запущена. Сначала останови (Ctrl+K).")
            return
        entry = self.versions_info[sel[0]]
        version_id = entry["id"]
        root = entry["root"]
        username = self.name_var.get().strip() or "Steve"
        try:
            ram_mb = int(self.ram_var.get())
        except ValueError:
            ram_mb = 4096
        java_path = getattr(self, "_current_java", None)
        if not java_path or not Path(java_path).exists():
            self.log_line("[!] Java не выбрана.")
            return
        self.cfg["username"] = username
        self.cfg["ram_mb"] = ram_mb
        self.cfg["last_version"] = entry["display"]
        self.cfg["download_libraries"] = self.dl_libs_var.get()
        self.cfg["download_assets"] = self.dl_assets_var.get()
        save_config(self.cfg)
        self.launch_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        threading.Thread(target=self._do_launch,
                         args=(version_id, username, ram_mb, java_path, root),
                         daemon=True).start()

    def _do_launch(self, version_id, username, ram_mb, java_path, root):
        _set_root(root)
        try:
            dl_libs = self.dl_libs_var.get()
            dl_assets = self.dl_assets_var.get()
            self.log_line(f"\n=== Запуск {version_id} [{root}] ===")
            self.log_line(f"Java (старт): {java_path}")

            vdir = VERSIONS_DIR / version_id
            cleanup_auto_delete_mods(vdir, log=self.log_line)
            remove_duplicate_mods(vdir, log=self.log_line)

            loader, forge_c, fabric_c, total, scan = scan_mods_loader_ratio(vdir, log=self.log_line)
            if loader and total >= 5:
                jpath = pick_version_json(vdir, version_id)
                cur_parent, cur_loader, cur_mc = "", None, None
                if jpath:
                    try:
                        data = load_json_tolerant(jpath)
                        if isinstance(data, dict):
                            cur_parent = data.get("inheritsFrom", "")
                            cur_loader, cur_mc, _ = detect_loader_type(cur_parent)
                            if cur_loader is None:
                                cur_loader = _parent_loader_by_name(cur_parent)
                    except Exception as e:
                        self.log_line(f"[!] Не прочитать JSON: {e}")

                mods_mc = scan_mods_mc_version(vdir, log=self.log_line)
                manual_mc = self.cfg.get("manual_mc_version", {}).get(version_id)
                if not manual_mc and mods_mc:
                    self.cfg.setdefault("manual_mc_version", {})[version_id] = mods_mc
                    save_config(self.cfg)
                    self.log_line(f"[✓] Автозаписал MC {mods_mc} по модам")
                    manual_mc = mods_mc
                target_mc = manual_mc or mods_mc

                self.log_line(f"[*] JSON inheritsFrom = {cur_parent!r}")
                self.log_line(f"[*] Загрузчик: по JSON {cur_loader or '?'}, по модам {loader}")
                self.log_line(f"[*] MC: по JSON {cur_mc or '?'}, по модам {mods_mc or '?'}"
                              + (f", вручную {manual_mc}" if manual_mc else ""))

                def _mc_norm(v):
                    if not v: return None
                    parts = v.split(".")
                    while len(parts) < 3:
                        parts.append("0")
                    return ".".join(parts[:3])

                loader_mismatch = bool(cur_loader and cur_loader != loader)
                mc_mismatch = bool(target_mc and cur_mc and
                                   _mc_norm(target_mc) != _mc_norm(cur_mc))

                if not cur_parent and target_mc and loader:
                    other_name = "Forge" if loader == "forge" else "Fabric"
                    msg = (f"Сборка «{version_id}» не привязана ни к какому загрузчику\n"
                           f"(в JSON нет поля inheritsFrom).\n\n"
                           f"  • По модам определилось: MC {target_mc} / {other_name}\n"
                           f"  • Forge-модов: {forge_c}, Fabric-модов: {fabric_c}\n\n"
                           f"Пересоздать JSON и привязать сборку к {other_name} {target_mc}?\n"
                           f"(Нужен интернет для скачивания загрузчика.)")
                    if self.ask_yes_no("Сборка без загрузчика", msg):
                        ok = fix_empty_json(vdir, version_id, target_mc, loader,
                                            log=self.log_line, java_path=java_path)
                        if ok:
                            self.log_line(f"[✓] JSON пересоздан. Запусти сборку ещё раз.")
                            return
                        else:
                            self.log_line("[!] Не удалось пересоздать JSON.")
                    else:
                        self.log_line("[*] Оставляю как есть.")

                elif mc_mismatch:
                    other_name = "Forge" if loader == "forge" else "Fabric"
                    cur_name = ("Forge" if cur_loader == "forge"
                                else "Fabric" if cur_loader == "fabric"
                                else str(cur_loader or "?"))
                    msg = (f"Сборка «{version_id}» настроена на MC {cur_mc} / {cur_name},\n"
                           f"но содержимое модов — это MC {target_mc} / {other_name}.\n\n"
                           f"  • MC по JSON:  {cur_mc}\n"
                           f"  • MC по модам: {mods_mc}\n"
                           f"  • Загрузчик по модам: {other_name}\n\n"
                           f"Переключить сборку на MC {target_mc} + {other_name}?")
                    if self.ask_yes_no("Несовпадение MC-версии", msg):
                        d, e, ok = fix_pack_mc_and_loader(
                            vdir, version_id, target_mc, loader, scan,
                            log=self.log_line, java_path=java_path)
                        self.log_line(f"[✓] Отключено: {d}, включено: {e}, успех: {ok}")
                    else:
                        self.log_line("[*] Оставляю как есть.")

                elif loader_mismatch:
                    other_name = "Forge" if loader == "forge" else "Fabric"
                    cur_name = ("Forge" if cur_loader == "forge"
                                else "Fabric" if cur_loader == "fabric"
                                else str(cur_loader))
                    msg = (f"Сборка «{version_id}» сейчас использует {cur_name}, "
                           f"но содержимое модов говорит, что это {other_name}.\n\n"
                           f"Переключить сборку на {other_name}?")
                    if self.ask_yes_no("Несоответствие загрузчика", msg):
                        mc_for_fix = target_mc or cur_mc
                        if mc_for_fix:
                            d, e, ok = fix_pack_mc_and_loader(
                                vdir, version_id, mc_for_fix, loader, scan,
                                log=self.log_line, java_path=java_path)
                            self.log_line(f"[✓] Отключено: {d}, включено: {e}, успех: {ok}")
                        else:
                            d, e = fix_pack_loader(vdir, version_id, loader, scan,
                                                   log=self.log_line, java_path=java_path)
                            self.log_line(f"[✓] Готово: отключено {d}, включено {e}")
                    else:
                        self.log_line("[*] Оставляю как есть.")

            self.log_line("[*] Проверка локально доступных версий загрузчика...")
            changed = force_update_inherits_in_versions_json(log=self.log_line)
            if changed:
                self.log_line(f"[✓] Обновлено сборок: {len(changed)}")
            else:
                self.log_line("[*] Все сборки уже указывают на максимальные локальные версии.")

            self._check_and_prompt_update_early(version_id, java_path)

            vjson = load_version_json(version_id, log=self.log_line, java_path=java_path)
            if not vjson:
                self.log_line("[!] Не собрать JSON версии.")
                return

            need = required_java_full(version_id, vjson, log=self.log_line)
            actual = java_major_version(java_path)
            if actual is None or actual < need:
                self.log_line(f"[!] Java {actual} не подходит (нужна {need}+). Переключаю...")
                better = pick_java(self.javas, need)
                if better:
                    java_path = better
                    actual = java_major_version(java_path)
                    self.log_line(f"[✓] Автовыбор Java: {java_path} (Java {actual})")
                else:
                    self.log_line(f"[!] Нет Java {need}+.")
                    return
            else:
                self.log_line(f"[*] Java {actual} подходит (нужна {need}+)")

            is_fabric = "fabric" in version_id.lower() or "fabric" in str(vjson.get("id", "")).lower()
            if is_fabric:
                check_fabric_bad_mods(vdir, log=self.log_line)

            main_class = vjson.get("mainClass")
            if not main_class:
                self.log_line("[!] mainClass отсутствует.")
                return

            def progress(cur, tot, prefix):
                self.log_progress("    " + make_progress_bar(cur, tot, 30, prefix))

            self.log_line("[*] Сборка classpath...")
            cp = build_classpath(vjson, vdir, log=self.log_line,
                                 download=dl_libs, progress_cb=progress)
            self.log_progress_done()
            if not cp:
                self.log_line("[!] Пустой classpath.")
                return

            mc_ver_str = find_actual_mc_version(vjson) or version_id
            mc_ver_t = mc_tuple(mc_ver_str)
            if (1, 16, 0) <= mc_ver_t <= (1, 16, 5):
                fresh_log4j = ensure_fresh_log4j(log=self.log_line)
                if fresh_log4j:
                    cp = [str(j) for j in fresh_log4j] + cp
                    self.log_line(f"[✓] Forge {mc_ver_str}: log4j 2.17.1 в начале classpath")

            cp_str = CLASSPATH_SEP.join(cp)

            if dl_assets:
                ensure_assets(vjson, log=self.log_line, download=True, progress_cb=progress)
                self.log_progress_done()
            else:
                ensure_assets(vjson, log=self.log_line, download=False)

            natives_dir = extract_natives(vjson, vdir, log=self.log_line,
                                          download=dl_libs, progress_cb=progress)
            self.log_progress_done()

            game_dir = detect_game_dir(vdir, log=self.log_line)
            mods_root = vdir / "mods"
            mods_game = vdir / "game" / "mods"
            if mods_root.is_dir() and any(mods_root.glob("*.jar")):
                game_dir = vdir
                self.log_line(f"[✓] gameDir = {game_dir}")
            elif mods_game.is_dir() and any(mods_game.glob("*.jar")):
                game_dir = vdir / "game"
                self.log_line(f"[✓] gameDir = {game_dir}")

            asset_index = (vjson.get("assetIndex") or {}).get("id") or vjson.get("assets") or "legacy"
            ensure_launcher_profiles(game_dir, username, log=self.log_line)

            player_uuid = offline_uuid(username)
            access_token = fake_access_token()
            xuid = fake_xuid()
            client_id = fake_client_id()

            self.log_line(f"[*] Аккаунт: {username}  UUID={player_uuid}")

            ctx = {
                "auth_player_name":    username,
                "version_name":        version_id,
                "game_directory":      str(game_dir),
                "assets_root":         str(ASSETS_DIR),
                "assets_index_name":   asset_index,
                "auth_uuid":           player_uuid,
                "auth_access_token":   access_token,
                "auth_session":        access_token,
                "user_type":           "msa",
                "version_type":        vjson.get("type", "release"),
                "natives_directory":   str(natives_dir),
                "launcher_name":       "JLauncher",
                "launcher_version":    "1.0",
                "classpath":           cp_str,
                "classpath_separator": CLASSPATH_SEP,
                "resolution_width":    "1280",
                "resolution_height":   "720",
                "auth_xuid":           xuid,
                "clientid":            client_id,
            }

            jvm_args = build_jvm_flags(ram_mb, actual, log=self.log_line)
            jvm_args += [
                f"-Djava.library.path={natives_dir}",
                f"-Dorg.lwjgl.librarypath={natives_dir}",
                "-Dorg.lwjgl.util.Debug=false",
                "-Dminecraft.launcher.brand=JLauncher",
                "-Dminecraft.launcher.version=1.0",
            ]
            if "arguments" in vjson:
                for a in collect_args(vjson["arguments"].get("jvm", []), ctx):
                    a = a.replace("${classpath_separator}", CLASSPATH_SEP)
                    jvm_args.append(a)

            jvm_args, skipped = filter_jvm_args_for_java(jvm_args, actual)
            if skipped:
                self.log_line(f"[*] Вырезано Java {actual}: {len(skipped)} флагов")

            if is_forge_need_addopens(version_id, vjson):
                jvm_args = sanitize_addopens(jvm_args, log=self.log_line)
                module_path_used = False
                win_args = get_forge_win_args(version_id, vjson, log=self.log_line)
                if win_args:
                    for wa in win_args:
                        if wa not in jvm_args:
                            jvm_args.append(wa)
                    self.log_line(f"[✓] Добавлено {len(win_args)} аргументов из win_args.txt")
                    if any("--module-path" in str(a) or a == "-p" for a in win_args):
                        module_path_used = True
                else:
                    module_args = get_forge_module_path(version_id, vjson, log=self.log_line)
                    if module_args:
                        for ma in module_args:
                            if ma not in jvm_args:
                                jvm_args.append(ma)
                        self.log_line(f"[✓] Добавлено {len(module_args)} аргументов --module-path")
                        module_path_used = True
                    else:
                        self.log_line("[!] Не удалось сформировать --module-path.")

                target_module = "cpw.mods.securejarhandler" if module_path_used else "ALL-UNNAMED"
                added = 0
                for i in range(0, len(FORGE_ADD_OPENS), 2):
                    flag = FORGE_ADD_OPENS[i]
                    value = FORGE_ADD_OPENS[i + 1]
                    full = f"{value}={target_module}"
                    if flag not in jvm_args:
                        jvm_args.extend([flag, full])
                        added += 1
                self.log_line(f"[✓] Добавлено {added} --add-opens/--add-exports (цель: {target_module})")

            if is_forge_need_jpms_mixin(version_id, vjson):
                jpms_flags = [
                    "--add-reads=org.spongepowered.mixin=cpw.mods.modlauncher",
                    "--add-reads=org.spongepowered.mixin=cpw.mods.securejarhandler",
                    "--add-reads=ALL-UNNAMED=cpw.mods.modlauncher",
                    "--add-reads=ALL-UNNAMED=cpw.mods.securejarhandler",
                    "--add-opens=cpw.mods.modlauncher/cpw.mods.modlauncher.api=org.spongepowered.mixin",
                    "--add-opens=cpw.mods.modlauncher/cpw.mods.modlauncher.api=ALL-UNNAMED",
                    "--add-exports=cpw.mods.modlauncher/cpw.mods.modlauncher.api=org.spongepowered.mixin",
                    "--add-exports=cpw.mods.modlauncher/cpw.mods.modlauncher.api=ALL-UNNAMED",
                ]
                added = 0
                for f in jpms_flags:
                    if f not in jvm_args:
                        jvm_args.append(f)
                        added += 1
                if added:
                    self.log_line(f"[✓] Добавлено {added} JPMS-флагов")

            if is_fabric:
                fabric_mods = game_dir / "mods"
                if fabric_mods.is_dir():
                    jvm_args.append(f"-Dfabric.addMods={fabric_mods}")
                    self.log_line(f"[✓] fabric.addMods = {fabric_mods}")

            jvm_args += ["-cp", cp_str, main_class]

            if "arguments" in vjson:
                game_args = collect_args(vjson["arguments"].get("game", []), ctx)
            elif "minecraftArguments" in vjson:
                game_args = vjson["minecraftArguments"].split()
            else:
                game_args = []

            cleaned = []
            skip_next = False
            offline_keys = {"--username", "--uuid", "--accessToken", "--userType",
                            "--version", "--gameDir", "--assetsDir", "--assetIndex",
                            "--xuid", "--clientId", "--versionType", "--userProperties"}
            for a in game_args:
                if skip_next:
                    skip_next = False
                    continue
                if a in DEMO_FLAGS:
                    self.log_line(f"[*] Вырезан флаг: {a}")
                    continue
                if a in DEMO_FLAGS_WITH_VALUE:
                    self.log_line(f"[*] Вырезан флаг: {a}")
                    skip_next = True
                    continue
                if a in offline_keys:
                    key = a
                    val = None
                    if key == "--username":       val = username
                    elif key == "--uuid":          val = player_uuid
                    elif key == "--accessToken":   val = access_token
                    elif key == "--userType":      val = "msa"
                    elif key == "--version":       val = version_id
                    elif key == "--gameDir":       val = str(game_dir)
                    elif key == "--assetsDir":     val = str(ASSETS_DIR)
                    elif key == "--assetIndex":    val = asset_index
                    elif key == "--xuid":          val = xuid
                    elif key == "--clientId":      val = client_id
                    elif key == "--versionType":   val = "release"
                    elif key == "--userProperties": val = "{}"
                    cleaned.append(key)
                    cleaned.append(val)
                    skip_next = True
                else:
                    cleaned.append(a)
            game_args = cleaned

            def has(flag): return flag in game_args
            additions = []
            if not has("--username"):    additions += ["--username", username]
            if not has("--uuid"):        additions += ["--uuid", player_uuid]
            if not has("--accessToken"): additions += ["--accessToken", access_token]
            if not has("--userType"):    additions += ["--userType", "msa"]
            if not has("--version"):     additions += ["--version", version_id]
            if not has("--gameDir"):     additions += ["--gameDir", str(game_dir)]
            if not has("--assetsDir"):   additions += ["--assetsDir", str(ASSETS_DIR)]
            if not has("--assetIndex"):  additions += ["--assetIndex", asset_index]
            if not has("--xuid"):        additions += ["--xuid", xuid]
            if not has("--clientId"):    additions += ["--clientId", client_id]
            if not has("--versionType"): additions += ["--versionType", "release"]
            game_args += additions

            def sub(s):
                for k, v in ctx.items():
                    s = s.replace("${%s}" % k, str(v))
                return s
            game_args = [sub(a) for a in game_args]

            while "--demo" in game_args:
                game_args.remove("--demo")
                        # --- Бэкап перед запуском ---
            try:
                if _backup_should_run(game_dir, self.cfg):
                    self.log_line("[*] Создаю бэкап перед запуском...")
                    ok, bpath, berr = create_backup(game_dir, log=self.log_line, cfg=self.cfg)
                    if not ok and berr:
                        self.log_line(f"[!] Бэкап не создан: {berr}")
            except Exception as be:
                self.log_line(f"[!] Ошибка бэкапа: {be}")

            cmd = [java_path] + jvm_args + game_args
            self.log_line(f"gameDir: {game_dir}")
            self.log_line("Команда (сокращённо):")
            self.log_line("  " + " ".join(cmd[:10]) + (" ..." if len(cmd) > 10 else ""))
            self.log_line(f"[i] Всего: {len(cmd)} аргументов")

            if "--demo" in cmd:
                self.log_line("[!] --demo всё ещё в команде!")
            else:
                self.log_line("[✓] --demo отсутствует")

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(cmd, cwd=str(game_dir),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=creationflags)
            self._running_proc = proc
            self._running_pid = proc.pid
            self.log_line(f"PID={proc.pid}\n")
            self._last_output_ts = time.time()

            def _watchdog():
                warned = False
                while proc.poll() is None:
                    time.sleep(5)
                    idle = time.time() - self._last_output_ts
                    if idle > 90 and not warned:
                        self.log_line(f"[!] Процесс молчит {int(idle)} сек — похоже на зависание.")
                        self.log_line(f"    Нажми «Остановить» (Ctrl+K) или сними jstack: "
                                      f"jstack -l {proc.pid}")
                        warned = True
                    elif idle < 30:
                        warned = False

            threading.Thread(target=_watchdog, daemon=True).start()

            for line in proc.stdout:
                self._last_output_ts = time.time()
                self.log_line(line.rstrip())
            proc.wait()
            self.log_line(f"\n[i] Процесс завершён, код {proc.returncode}")
        except Exception:
            self.log_line("[!] Ошибка:\n" + traceback.format_exc())
        finally:
            self._running_proc = None
            self._running_pid = None
            try:
                self.after(0, lambda: (self.launch_btn.config(state="normal"),
                                       self.stop_btn.config(state="disabled")))
            except tk.TclError:
                pass

    def _check_and_prompt_update_early(self, version_id, java_path):
        vdir = VERSIONS_DIR / version_id
        jpath = pick_version_json(vdir, version_id)
        if not jpath:
            return
        try:
            with open(jpath, "r", encoding="utf-8-sig") as f:
                data = load_json_tolerant(jpath)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        parent = data.get("inheritsFrom")
        if not parent:
            return

        loader_type, mc_ver, current_ver = detect_loader_type(parent)
        if not loader_type or not mc_ver or not current_ver:
            return

        self.log_line(f"[*] Проверка интернет-обновлений {loader_type} для MC {mc_ver} (текущая: {current_ver})...")

        latest = None
        if loader_type == "forge":
            latest = get_latest_forge_version(mc_ver)
        elif loader_type == "fabric":
            latest = get_latest_fabric_loader(mc_ver)

        if not latest:
            self.log_line("[!] Не удалось получить список версий с сервера (проверь интернет).")
            return

        if latest == current_ver:
            self.log_line(f"[*] {loader_type.title()} {current_ver} — последняя версия на сервере.")
            return

        self.log_line(f"[!] Доступно обновление: {loader_type.title()} {latest} (у вас {current_ver})")

        title = f"Обновление {loader_type.title()}"
        msg = (f"Доступна новая версия {loader_type.title()}:\n\n"
               f"  • Сейчас: {current_ver}\n"
               f"  • Новая:  {latest}\n"
               f"  • Для MC: {mc_ver}\n\n"
               f"Обновить загрузчик? Это займёт пару минут.\n"
               f"(Игра запустится в любом случае.)")
        answer = self.ask_yes_no(title, msg)

        if not answer:
            self.log_line("[*] Обновление пропущено.")
            return

        self.log_line(f"[*] Устанавливаю {loader_type} {latest}...")
        if loader_type == "forge":
            ok = download_and_install_forge(mc_ver, latest, java_path, log=self.log_line)
        else:
            ok = download_and_install_fabric(mc_ver, latest, java_path, log=self.log_line)

        if not ok:
            self.log_line("[!] Установка не удалась — продолжаю со старой версией.")
            return

        self.log_line("[*] Установка успешна. Обновление inheritsFrom выполнится автоматически.")

    def _on_close(self):
        if self._running_proc and self._running_proc.poll() is None:
            kill = messagebox.askyesno(
                "Minecraft запущен",
                "Игра ещё работает. Завершить Java перед закрытием лаунчера?",
                parent=self)
            if kill:
                self.stop_game()
                for _ in range(12):
                    if self._running_proc is None or self._running_proc.poll() is not None:
                        break
                    time.sleep(0.25)
        try:
            if self.state() != "zoomed":
                self.cfg["window_geometry"] = self.geometry()
            else:
                self.cfg["window_geometry"] = "zoomed"
            self.cfg["username"] = self.name_var.get().strip() or "Steve"
            try: self.cfg["ram_mb"] = int(self.ram_var.get())
            except ValueError: pass
            self.cfg["download_libraries"] = self.dl_libs_var.get()
            self.cfg["download_assets"] = self.dl_assets_var.get()
            save_config(self.cfg)
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    try:
        Launcher().mainloop()
    except Exception:
        print(traceback.format_exc())
        input("Enter to exit...")