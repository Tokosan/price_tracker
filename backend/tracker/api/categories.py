"""Categorías del usuario para organizar sus Watches.

Privacidad: toda consulta filtra por `user_id` (el admin las ve en `/api/admin/watches`).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tracker.api.deps import current_user
from tracker.api.watches import (
    categories_of,
    get_own_watch,
    own_categories,
    own_category,
    watch_out,
)
from tracker.db import get_db
from tracker.models import Category, User, Watch, WatchCategory

router = APIRouter(prefix="/api", tags=["categories"])

# Claves de la paleta del frontend (`format.js`, CATEGORY_COLORS); cada tema pone su tono.
COLORS = ("gray", "red", "orange", "yellow", "green", "blue", "purple", "pink")


def category_out(category: Category, count: int) -> dict:
    return {"id": category.id, "name": category.name, "color": category.color, "count": count}


def _count(db: DbSession, category: Category) -> int:
    return db.scalar(
        select(func.count())
        .select_from(WatchCategory)
        .where(WatchCategory.category_id == category.id)
    )


def _clean(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(422, "La categoría necesita un nombre.")
    return name


def _check_unique(db: DbSession, user: User, name: str, skip: int | None = None) -> None:
    q = select(Category).where(
        Category.user_id == user.id, func.lower(Category.name) == name.lower()
    )
    if skip is not None:
        q = q.where(Category.id != skip)
    if db.scalar(q) is not None:
        raise HTTPException(409, f"Ya tienes una categoría «{name}».")


def _next_color(db: DbSession, user: User) -> str:
    """El primer color que el usuario no usa; si los usa todos, en ronda."""
    used = list(db.scalars(select(Category.color).where(Category.user_id == user.id)))
    free = [c for c in COLORS if c not in used]
    return free[0] if free else COLORS[len(used) % len(COLORS)]


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = None


class CategoryPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None


def _check_color(color: str | None) -> None:
    if color is not None and color not in COLORS:
        raise HTTPException(422, f"Color desconocido: {color}.")


@router.get("/categories")
def list_categories(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> list:
    counts = dict(
        db.execute(
            select(WatchCategory.category_id, func.count())
            .join(Category, Category.id == WatchCategory.category_id)
            .where(Category.user_id == user.id)
            .group_by(WatchCategory.category_id)
        ).all()
    )
    categories = db.scalars(
        select(Category).where(Category.user_id == user.id).order_by(func.lower(Category.name))
    )
    return [category_out(c, counts.get(c.id, 0)) for c in categories]


@router.post("/categories", status_code=201)
def create_category(
    body: CategoryIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    name = _clean(body.name)
    _check_color(body.color)
    _check_unique(db, user, name)
    category = Category(user_id=user.id, name=name, color=body.color or _next_color(db, user))
    db.add(category)
    db.commit()
    return category_out(category, 0)


@router.patch("/categories/{category_id}")
def update_category(
    category_id: int,
    body: CategoryPatchIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    category = own_category(db, user, category_id)
    if body.name is not None:
        name = _clean(body.name)
        _check_unique(db, user, name, skip=category.id)
        category.name = name
    if body.color is not None:
        _check_color(body.color)
        category.color = body.color
    db.commit()
    return category_out(category, _count(db, category))


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> None:
    # Los productos no se tocan: solo pierden la etiqueta (cascada en watch_categories).
    db.delete(own_category(db, user, category_id))
    db.commit()


class WatchCategoriesIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=200)


@router.put("/watches/{watch_id}/categories")
def set_watch_categories(
    watch_id: int,
    body: WatchCategoriesIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    watch = get_own_watch(db, user, watch_id)
    watch.categories = own_categories(db, user, body.ids)
    db.commit()
    db.refresh(watch)
    return watch_out(db, watch)


class BulkIn(BaseModel):
    watch_ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(add|remove)$")


@router.post("/categories/{category_id}/watches")
def bulk_assign(
    category_id: int,
    body: BulkIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    """Agrega o quita la categoría a varios productos (modo selección de la lista)."""
    category = own_category(db, user, category_id)
    watches: list[Watch] = [get_own_watch(db, user, i) for i in dict.fromkeys(body.watch_ids)]
    for watch in watches:
        if body.action == "add" and category not in watch.categories:
            watch.categories.append(category)
        elif body.action == "remove" and category in watch.categories:
            watch.categories.remove(category)
    db.commit()
    return {
        "category": category_out(category, _count(db, category)),
        "watches": [{"id": w.id, "categories": categories_of(w)} for w in watches],
    }
