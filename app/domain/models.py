"""Core domain models — product cards, sellers, reviews, identifiers."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Identifier bundle ─────────────────────────────────────────


class IdentifierBundle(BaseModel):
    product_ref: str
    provider: str = "dataforseo"
    channel: str = "google_shopping"
    product_id: str | None = None
    gid: str | None = None
    data_docid: str | None = None
    additional_specifications: list[dict] | None = None


# ── Price snapshot ────────────────────────────────────────────


class PriceSnapshot(BaseModel):
    source: str = "products"
    current: float | None = None
    old: float | None = None
    base_price: float | None = None
    shipping_price: float | None = None
    total_price: float | None = None
    currency: str = "USD"
    displayed_price: str | None = None
    is_price_range: bool = False


# ── Product card ──────────────────────────────────────────────


class ProductCard(BaseModel):
    # Basic fields (from Products endpoint)
    product_ref: str
    title: str = ""
    brand: str | None = None
    description_excerpt: str | None = None
    description_full: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    platform: str = "Google Shopping"
    domain: str | None = None
    seller_name: str | None = None
    price_current: float | None = None
    price_old: float | None = None
    currency: str = "USD"
    rank_absolute: int | None = None
    reviews_count: int | None = None
    product_rating_value: float | None = None
    product_rating_max: float | None = 5
    source_stage: str = "products"

    # Supplementary fields (from Product Info / Sellers / Reviews)
    feature_bullets: list[str] = Field(default_factory=list)
    spec_highlights: dict[str, str] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    variations: list[dict] = Field(default_factory=list)
    price_range: dict | None = None
    seller_count: int | None = None


# ── Seller summary ────────────────────────────────────────────


class SellerSummary(BaseModel):
    seller_name: str | None = None
    domain: str | None = None
    url: str | None = None
    base_price: float | None = None
    shipping_price: float | None = None
    total_price: float | None = None
    currency: str = "USD"
    rating_value: float | None = None
    rating_max: float | None = 5
    details: str | None = None
    annotation: str | None = None


# ── Review item ───────────────────────────────────────────────


class ReviewItem(BaseModel):
    title: str | None = None
    text: str | None = None
    provided_by: str | None = None
    author: str | None = None
    publication_date: str | None = None
    rating_value: float | None = None
    images: list[str] = Field(default_factory=list)


class ReviewSummary(BaseModel):
    total_reviews: int | None = None
    average_rating: float | None = None
    rating_max: float | None = 5
    rating_groups: list[dict] = Field(default_factory=list)
    top_keywords: list[str] = Field(default_factory=list)
    sample_reviews: list[ReviewItem] = Field(default_factory=list)


# ── Presentation card (derived, not stored in cache) ──────────


class PresentationCard(BaseModel):
    rank: int | None = None
    badge: str | None = None
    summary: str | None = None


# ── Cache entry ───────────────────────────────────────────────


class ProductCacheEntry(BaseModel):
    product_ref: str
    identifiers: IdentifierBundle
    base_card: dict = Field(default_factory=dict)
    product_info_snapshot: dict = Field(default_factory=dict)
    sellers_snapshot: dict = Field(default_factory=dict)
    reviews_snapshot: dict = Field(default_factory=dict)
    freshness: dict = Field(default_factory=lambda: {
        "base_card_at": None,
        "product_info_at": None,
        "sellers_at": None,
        "reviews_at": None,
    })
