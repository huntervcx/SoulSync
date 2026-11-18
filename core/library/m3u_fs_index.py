"""Filesystem fallback for M3U path resolution.

The M3U exporter normally resolves tracks through the media-server library DB,
which is empty until Plex/Jellyfin/Navidrome has scanned the new files (and
stays empty when no media server is configured). This indexes the audio
files already in the Transfer folder by their embedded artist/title tags, so a
playlist's M3U can be written right after its tracks are downloaded.
"""
import os
import re
import threading
from collections import defaultdict

AUDIO_EXTS = {'.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wav', '.aiff', '.aif', '.wma', '.aac'}

_lock = threading.Lock()
_cache = {}  # root -> (signature, {artist_key: [(title_norm, title_clean, path)]})


def _norm(text):
    return re.sub(r'\s+', ' ', (text or '').lower().strip())


def _clean(text):
    s = _norm(text)
    s = re.sub(r'\s*[\[\(].*?[\]\)]', '', s)
    s = re.sub(r'\s*-\s*', ' ', s)
    s = re.sub(r'\s*(feat\.|featuring|ft\.).*', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def _read_tags(path):
    try:
        import mutagen
        audio = mutagen.File(path, easy=True)
        if not audio:
            return None, []
        titles = audio.get('title') or []
        artists = list(audio.get('artist') or []) + list(audio.get('albumartist') or [])
        return (titles[0] if titles else None), artists
    except Exception:
        return None, []


def _scan(root):
    files = []
    for dirpath, _dirs, names in os.walk(root):
        for n in names:
            if os.path.splitext(n)[1].lower() in AUDIO_EXTS:
                p = os.path.join(dirpath, n)
                try:
                    files.append((p, os.stat(p).st_mtime_ns))
                except OSError:
                    pass
    return files


def build_index(root):
    """Return {clean artist: [(title_norm, title_clean, path)]}, cached by file mtimes."""
    files = _scan(root)
    signature = hash(tuple(sorted(files)))
    with _lock:
        cached = _cache.get(root)
        if cached and cached[0] == signature:
            return cached[1]
    index = defaultdict(list)
    for path, _mtime in files:
        title, artists = _read_tags(path)
        if not title:
            continue
        for a in artists:
            index[_clean(a)].append((_norm(title), _clean(title), path))
    with _lock:
        _cache[root] = (signature, index)
    return index
