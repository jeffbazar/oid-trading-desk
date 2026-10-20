#!/usr/bin/env python3
"""Secret scrub + scan for mini-oid-collector. Never prints secret values.

--scrub DIR : replace any KNOWN secret value (read from the mini's secret stores)
              found in DIR's files with a ${NAME} placeholder, then run the regex scan.
--check DIR : known-value + regex scan only (no changes). Exit 2 on any finding.
Findings are reported as file:line + kind, with values masked.
"""
import argparse, os, re, sys

HOME = os.path.expanduser("~")
SECRET_SOURCES = [  # paths only; contents are never printed
    "oid-data/secrets", "oid-quote/secrets", "oid-live-page/secrets",
    "oid-desk/desk/secrets", "oid-desk/env", ".oid",
]
SKIP_DIRS = {".git"}

def env_name(path):
    rel = os.path.relpath(path, HOME)
    base = os.path.basename(path)
    if "read-tokens" in rel:
        base = "OID_READ_TOKEN_" + base
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper()

def load_known():
    known = {}  # value -> NAME
    for src in SECRET_SOURCES:
        root = os.path.join(HOME, src)
        if not os.path.isdir(root):
            continue
        for dp, _, fns in os.walk(root, followlinks=True):
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                name = env_name(p)
                whole = txt.strip()
                if len(whole) >= 12 and "\n" not in whole:
                    known.setdefault(whole, name)
                for line in txt.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line and re.match(r"^(export\s+)?[A-Za-z_][A-Za-z0-9_]*=", line):
                        k, v = line.split("=", 1)
                        k = k.replace("export", "").strip()
                        v = v.strip().strip("'\"")
                        if len(v) >= 12 and not v.startswith("http"):
                            known.setdefault(v, k)
                        elif v.startswith("http") and "?" in v:  # url with query secret
                            known.setdefault(v, k)
                    elif len(line) >= 12:
                        known.setdefault(line, name)
    return known

PATTERNS = [
    ("bearer-literal", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("apca-assign", re.compile(r"APCA[A-Z_]*['\"]?\s*[:=]\s*['\"][A-Za-z0-9/+]{12,}['\"]")),
    ("sk-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("key/token assignment", re.compile(
        r"(?i)\b[\w-]*(api[_-]?key|secret|token|password|passwd|bearer|auth)[\w-]*['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-+/=.]{16,})['\"]")),
    ("url key= param", re.compile(r"(?i)[?&](api[_-]?key|key|token|apikey|access_token)=([A-Za-z0-9_\-]{12,})")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("long hex (>=40)", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
    ("long base64 (>=40)", re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9+/])")),
]
# patterns that are reported but don't fail by themselves (reviewed manually)
SOFT = {"long hex (>=40)", "long base64 (>=40)"}
MINIFIED = re.compile(r"\.min\.js$")
PLACEHOLDER = re.compile(r"^\$\{[A-Z0-9_]+\}$|^<[^>]+>$|^(x+|X+|\*+|changeme|example.*|your[_-].*)$", re.I)

def benign(val, line, m):
    """Obvious non-secrets: identifiers, env-var/file NAMES, paths, slugs, test fixtures, rulers."""
    if re.fullmatch(r"[A-Z][A-Z0-9_]+", val):            # env var / secret-file name
        return True
    if re.fullmatch(r"[a-z][a-z0-9_]*", val):            # snake_case identifier
        return True
    if val.startswith(("/", "~", "http://", "https://", "./", "$")) and "?" not in val:
        return True
    if set(val) <= set("-=_#*~+"):                       # comment rulers
        return True
    if re.fullmatch(r"#?[a-z0-9]+(-[a-z0-9]+)+", val):   # html anchor / slug / kebab ids
        if not re.search(r"[0-9]{6,}", val) or re.search(r"test|fake|dummy|example|sample", val):
            return True
    start = m.start(m.lastindex) if m.lastindex else m.start()
    if start > 0 and line[start - 1] == "/":              # hash segment inside a filesystem path
        return True
    if re.search(r"(?i)(_file|_path|_dir|token_key|_name)['\"]?\s*[:=]", m.group(0)):
        return True
    return False

def iter_files(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn in (".excludes", ".scan-report.txt", "SCAN-REPORT.txt"):
                continue
            yield os.path.join(dp, fn)

def is_text(p):
    try:
        b = open(p, "rb").read(4096)
    except OSError:
        return False
    return b"\x00" not in b

def mask(s):
    return "<masked %d chars>" % len(s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrub"); ap.add_argument("--check"); ap.add_argument("--report")
    a = ap.parse_args()
    root = a.scrub or a.check
    known = load_known()
    scrubbed, hard, soft, binfiles = [], [], [], 0
    for p in iter_files(root):
        rel = os.path.relpath(p, root)
        if not is_text(p):
            binfiles += 1
            data = open(p, "rb").read()
            for v, name in known.items():
                if v.encode() in data:
                    hard.append((rel, 0, "known secret value (%s) in binary" % name))
            continue
        txt = open(p, encoding="utf-8", errors="ignore").read()
        new = txt
        for v, name in known.items():
            if v in new:
                if a.scrub:
                    new = new.replace(v, "${%s}" % name)
                    scrubbed.append((rel, name))
                else:
                    hard.append((rel, 0, "known secret value (%s)" % name))
        if new != txt:
            open(p, "w", encoding="utf-8").write(new)
        if MINIFIED.search(rel):
            continue  # vendored minified libs: known-value check only
        for i, line in enumerate(new.splitlines(), 1):
            for kind, rx in PATTERNS:
                for m in rx.finditer(line):
                    val = m.group(m.lastindex) if m.lastindex else m.group(0)
                    if PLACEHOLDER.match(val) or "${" in m.group(0) or "os.environ" in line:
                        continue
                    if benign(val, line, m):
                        continue
                    if kind in SOFT:
                        # ignore paths/identifiers that are obviously not secrets
                        if "/" in val and not re.search(r"[0-9]", val.replace("/", "")[:8]):
                            continue
                        if re.fullmatch(r"[a-z_]+", val):
                            continue
                        soft.append((rel, i, kind, mask(val)))
                    else:
                        hard.append((rel, i, kind + " " + mask(val)))
    out = []
    out.append("known secret values loaded: %d (from %d secret stores; values never printed)" % (len(known), len(SECRET_SOURCES)))
    out.append("binary files checked for known values: %d" % binfiles)
    out.append("scrubbed (file -> placeholder): %d" % len(scrubbed))
    out += ["  %s -> ${%s}" % s for s in sorted(set(scrubbed))]
    out.append("HARD findings (fail): %d" % len(hard))
    out += ["  %s:%s %s" % h for h in hard]
    out.append("soft findings (review; long hex/base64): %d" % len(soft))
    out += ["  %s:%s %s %s" % s for s in soft]
    rep = "\n".join(out) + "\n"
    if a.report:
        open(a.report, "w").write(rep)
    print(rep)
    sys.exit(2 if hard else 0)

if __name__ == "__main__":
    main()
