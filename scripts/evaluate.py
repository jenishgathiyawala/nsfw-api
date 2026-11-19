"""Measure accuracy on your own labelled images.

Put images in two sub-folders and run:
    uv run python scripts/evaluate.py path/to/dataset
where path/to/dataset contains `sfw/` and `nsfw/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import NSFWClassifier  # noqa: E402
from app.config import Settings  # noqa: E402
from app.detector import NudeDetector  # noqa: E402
from app.preprocessing import InvalidImageError  # noqa: E402

THRESHOLDS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def score_folder(model: NSFWClassifier, folder: Path):
    """[(filename, open_nsfw score, nudenet score, nudenet label)], [errors]"""
    scores, errors = [], []
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in EXTENSIONS:
            continue
        try:
            r = model.classify(path.read_bytes(), threshold=0.5)
            nude = r.nudenet.score if r.nudenet else 0.0
            scores.append((path.name, r.scores.nsfw, nude, r.nudenet.label if r.nudenet else None))
        except InvalidImageError as exc:
            errors.append(f"{path.name}: {exc}")
    return scores, errors


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path, help="folder containing sfw/ and nsfw/")
    parser.add_argument("--threshold", type=float, default=settings.default_threshold,
                        help="Open_NSFW threshold for the list of mistakes (default: server default)")
    parser.add_argument("--nudenet-threshold", type=float, default=settings.nudenet_threshold,
                        help="NudeNet threshold (default: server default)")
    parser.add_argument("--no-nudenet", action="store_true", help="test Open_NSFW alone")
    args = parser.parse_args()

    folders = {label: args.dataset / label for label in ("sfw", "nsfw")}
    for folder in folders.values():
        if not folder.is_dir():
            sys.exit(f"Missing folder: {folder}")

    detector = None if args.no_nudenet else NudeDetector(settings.nudenet_model_path)
    model = NSFWClassifier(settings.model_path, num_interpreters=1, detector=detector,
                           max_pixels=settings.max_pixels, max_frames=settings.max_frames)

    sfw, sfw_errors = score_folder(model, folders["sfw"])
    nsfw, nsfw_errors = score_folder(model, folders["nsfw"])
    for err in sfw_errors + nsfw_errors:
        print(f"skipped  {err}")
    if not sfw or not nsfw:
        sys.exit("Need at least one readable image in each folder.")

    nt = args.nudenet_threshold
    use_nude = detector is not None

    def flagged(open_score, nude_score, t):
        return open_score >= t or (use_nude and nude_score >= nt)

    def row(title, pred):
        caught = sum(pred(o, n) for _, o, n, _ in nsfw)
        wrong = sum(pred(o, n) for _, o, n, _ in sfw)
        correct = (caught + len(sfw) - wrong) / (len(sfw) + len(nsfw))
        return (f"{title:<34} | {caught:>3}/{len(nsfw):<3} {caught / len(nsfw):>5.0%} | "
                f"{wrong:>3}/{len(sfw):<3} {wrong / len(sfw):>5.0%} | {correct:>7.0%}")

    print(f"\nImages: {len(nsfw)} NSFW, {len(sfw)} SFW")
    header = f"{'rule':<34} | {'NSFW caught':>14} | {'SFW wrong':>14} | {'correct':>7}"
    print("\n" + header + "\n" + "-" * len(header))
    for t in THRESHOLDS:
        title = f"Open_NSFW >= {t}" + (f"  OR NudeNet >= {nt}" if use_nude else "")
        marker = "  <- current" if abs(t - args.threshold) < 1e-9 else ""
        print(row(title, lambda o, n, t=t: flagged(o, n, t)) + marker)
    if use_nude:
        print()
        print(row(f"Open_NSFW alone >= {args.threshold}", lambda o, n: o >= args.threshold))
        for t in (0.4, 0.5, 0.6, 0.7):
            print(row(f"NudeNet alone >= {t}", lambda o, n, t=t: n >= t))

    rule = f"Open_NSFW >= {args.threshold}" + (f" OR NudeNet >= {nt}" if use_nude else "")
    missed = sorted((o, n, name, lab) for name, o, n, lab in nsfw if not flagged(o, n, args.threshold))
    wrong = sorted(((o, n, name, lab) for name, o, n, lab in sfw if flagged(o, n, args.threshold)), reverse=True)
    print(f"\nWith {rule}:")
    for title, items in ((f"NSFW images missed ({len(missed)})", missed),
                         (f"SFW images wrongly flagged ({len(wrong)})", wrong)):
        print(f"  {title}:")
        for o, n, name, lab in items:
            extra = f"  nudenet={n:.3f} ({lab or '-'})" if use_nude else ""
            print(f"    open_nsfw={o:.3f}{extra}  {name}")


if __name__ == "__main__":
    main()
