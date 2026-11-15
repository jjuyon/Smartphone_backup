"""Smartphone Backup : sauvegarde iPhone / Android et rangement des photos (Linux, Windows)."""
__version__ = "1.0.2"

try:  # version exacte écrite par la fabrication (ex. « 1.0.0-dev.3 »), absente des sources
    from ._build import VERSION as __version__  # noqa: F401
except ImportError:
    pass


def version_text():
    """Version affichée : celle de la fabrication, ou « 1.0.0 (abc1234) » depuis un clone git."""
    from pathlib import Path
    git = Path(__file__).resolve().parent.parent / ".git"
    try:
        head = (git / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            p = git / ref
            if p.exists():
                head = p.read_text().strip()
            else:  # référence rangée dans packed-refs
                head = next(l.split()[0] for l in (git / "packed-refs").read_text().splitlines()
                            if l.endswith(" " + ref))
        return f"{__version__} ({head[:7]})"
    except (OSError, StopIteration, IndexError):
        return __version__
