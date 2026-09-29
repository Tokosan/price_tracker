"""Smoke test en vivo de un procesador (fuera de CI).

Uso:
    python -m tracker.check <procesador> <url> [--save-fixture [NOMBRE]]

Imprime el ScrapeResult y las variantes. Con --save-fixture guarda la respuesta
cruda en tests/fixtures/<procesador>/<NOMBRE>.<ext> (por defecto el external_id).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from tracker.processors import PROCESSORS

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


async def _run(args: argparse.Namespace) -> int:
    proc = PROCESSORS.get(args.processor)
    if proc is None:
        print(f"procesador desconocido: {args.processor} (hay: {', '.join(PROCESSORS)})")
        return 2
    if not proc.matches(args.url):
        print(f"la URL no corresponde al procesador {proc.name}")
        return 2
    ref = proc.normalize(args.url)
    print(f"ref: {ref}")
    raw = await proc.fetch_raw(ref)
    result = proc.parse(raw, ref)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    variants = proc.parse_variants(raw, ref)
    if variants:
        print("variantes:")
        for v in variants:
            mark = "*" if v.selected else " "
            print(f"  {mark} {v.external_id:>10}  {v.label}  {v.url}")
    if args.save_fixture is not None:
        name = args.save_fixture or ref.external_id
        path = FIXTURES / proc.name / f"{name}.{proc.fixture_ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        print(f"fixture guardada en {path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tracker.check", description=__doc__)
    parser.add_argument("processor")
    parser.add_argument("url")
    parser.add_argument("--save-fixture", nargs="?", const="", default=None, metavar="NOMBRE")
    sys.exit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
