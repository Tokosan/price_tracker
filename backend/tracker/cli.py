"""CLI de administración (se corre dentro del contenedor).

python -m tracker.cli create-admin <usuario>
python -m tracker.cli invite <usuario> [--hours 48]
python -m tracker.cli delete-user <usuario>
python -m tracker.cli list-users
python -m tracker.cli telegram-check
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from tracker.db import SessionLocal
from tracker.models import Product, User, WatchItem
from tracker.security import create_invite


def _get(db, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username.lower()))
    if user is None:
        sys.exit(f"no existe el usuario {username}")
    return user


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tracker.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="crea un admin sin contraseña (usa `invite`)")
    p.add_argument("username")
    p = sub.add_parser("create-user", help="crea un usuario normal sin contraseña")
    p.add_argument("username")
    p = sub.add_parser("invite", help="genera un link de invitación/reset de un solo uso")
    p.add_argument("username")
    p.add_argument("--hours", type=int, default=48)
    p = sub.add_parser("delete-user", help="borra un usuario y todos sus datos")
    p.add_argument("username")
    p.add_argument(
        "--purge-orphan-products",
        action="store_true",
        help="borra también los productos que queden sin nadie que los siga (y su historial)",
    )
    sub.add_parser("list-users")
    sub.add_parser("telegram-check", help="verifica el token con getMe (no lo imprime)")
    args = parser.parse_args()

    if args.cmd == "telegram-check":
        from tracker.notifications import telegram

        if telegram.bot is None:
            sys.exit("Telegram no configurado (TELEGRAM_BOT_TOKEN vacío)")
        me = asyncio.run(telegram.bot.get_me())
        print(f"ok: bot @{me.get('username')} (id {me.get('id')})")
        return

    with SessionLocal() as db:
        if args.cmd in ("create-admin", "create-user"):
            if db.scalar(select(User).where(User.username == args.username.lower())):
                sys.exit(f"ya existe el usuario {args.username}")
            role = "admin" if args.cmd == "create-admin" else "user"
            db.add(User(username=args.username.lower(), role=role, active=True))
            db.commit()
            print(f"{role} {args.username} creado; genera su acceso con: invite {args.username}")
        elif args.cmd == "invite":
            link = create_invite(db, _get(db, args.username), hours=args.hours)
            db.commit()
            print(link)
        elif args.cmd == "delete-user":
            db.delete(_get(db, args.username))
            db.commit()
            print(f"usuario {args.username} borrado")
            if args.purge_orphan_products:
                orphans = db.scalars(
                    select(Product).where(~Product.id.in_(select(WatchItem.product_id)))
                ).all()
                for product in orphans:
                    db.delete(product)
                db.commit()
                print(f"{len(orphans)} producto(s) sin seguidores borrados")
        elif args.cmd == "list-users":
            for u in db.scalars(select(User).order_by(User.id)):
                print(
                    u.id,
                    u.username,
                    u.role,
                    "activo" if u.active else "inactivo",
                    "con contraseña" if u.password_hash else "sin contraseña",
                )


if __name__ == "__main__":
    main()
