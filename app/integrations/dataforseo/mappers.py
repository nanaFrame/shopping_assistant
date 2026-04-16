"""Field mappers: DataForSEO raw responses -> internal domain models."""

from __future__ import annotations

from typing import Any

from app.domain.identifiers import generate_product_ref


# ── Products endpoint ─────────────────────────────────────────


def map_products_response(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Products endpoint items to internal product_card dicts.

    DataForSEO returns two possible structures:
    - google_shopping_carousel: a category group with nested items[]
    - google_shopping_carousel_element / product-level: a flat product
    We flatten carousels so every element becomes a product card.
    """
    results: list[dict[str, Any]] = []
    seen_refs: set[str] = set()

    flat_items: list[dict[str, Any]] = []
    for item in raw_items:
        if item.get("type") == "google_shopping_carousel" and item.get("items"):
            for sub in item["items"]:
                sub["_carousel_title"] = item.get("title", "")
                flat_items.append(sub)
        elif item.get("type") in (
            "google_shopping_carousel_element",
            "google_shopping_product",
            "product_item",
        ):
            flat_items.append(item)
        elif item.get("product_id") or item.get("gid") or item.get("title"):
            flat_items.append(item)

    for item in flat_items:
        product_id = str(item.get("product_id", "")) or None
        gid = str(item.get("gid", "")) or None
        data_docid = str(item.get("data_docid", "")) or None

        ref = generate_product_ref(
            product_id=product_id, gid=gid, data_docid=data_docid,
            title=item.get("title"), seller=item.get("seller"), url=item.get("url"),
        )

        if ref in seen_refs:
            continue
        seen_refs.add(ref)

        images = item.get("product_images") or []
        rating = item.get("product_rating") or {}
        reviews_count = (
            rating.get("votes_count")
            or item.get("reviews_count")
        )

        card: dict[str, Any] = {
            "product_ref": ref,
            "title": item.get("title", ""),
            "brand": None,
            "description_excerpt": item.get("description", ""),
            "image_url": images[0] if images else None,
            "product_url": item.get("shopping_url") or item.get("url"),
            "platform": "Google Shopping",
            "domain": item.get("domain"),
            "seller_name": item.get("seller"),
            "price_current": item.get("price"),
            "price_old": item.get("old_price"),
            "currency": item.get("currency", "USD"),
            "rank_absolute": item.get("rank_absolute"),
            "reviews_count": reviews_count,
            "product_rating_value": rating.get("value") if rating else None,
            "product_rating_max": rating.get("rating_max", 5) if rating else 5,
            "source_stage": "products",
            "product_id": product_id,
            "gid": gid,
            "data_docid": data_docid,
        }
        results.append(card)

    return results


# ── Product Info endpoint ─────────────────────────────────────


def map_product_info_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Product Info response to supplementary fields dict."""
    result: dict[str, Any] = {"_source": "product_info"}

    if raw.get("title"):
        result["title"] = raw["title"]
    if raw.get("description"):
        result["description_full"] = raw["description"]
    if raw.get("image_url"):
        result["image_url"] = raw["image_url"]
    if raw.get("images"):
        result["images"] = raw["images"]
        if not result.get("image_url"):
            result["image_url"] = raw["images"][0]
    if raw.get("features"):
        result["feature_bullets"] = raw["features"]

    # Specifications
    specs = raw.get("specifications") or []
    spec_dict: dict[str, str] = {}
    brand = None
    for key, val in _iter_product_info_specifications(specs):
        spec_dict[key] = val
        if key.lower() in ("brand", "manufacturer"):
            brand = val
    if spec_dict:
        result["spec_highlights"] = spec_dict
    if brand:
        result["brand"] = brand

    # Variations
    if raw.get("variations"):
        result["variations"] = raw["variations"]

    # Identifiers
    if raw.get("gid"):
        result["gid"] = str(raw["gid"])
    if raw.get("data_docid"):
        result["data_docid"] = str(raw["data_docid"])

    return result


def _iter_product_info_specifications(
    specs: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue

        # Current DataForSEO Product Info Advanced docs use a flat shape:
        # specification_name + specification_value.
        key = str(spec.get("specification_name") or "").strip()
        val = str(spec.get("specification_value") or "").strip()
        if key and val:
            pairs.append((key, val))
            continue

        # Keep backward compatibility if older responses nest specs under items.
        for item in spec.get("items") or []:
            if not isinstance(item, dict):
                continue
            nested_key = str(item.get("name") or "").strip()
            nested_val = str(item.get("value") or "").strip()
            if nested_key and nested_val:
                pairs.append((nested_key, nested_val))
    return pairs


# ── Sellers endpoint ──────────────────────────────────────────


def map_sellers_response(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Sellers endpoint items to seller_summary dicts."""
    results: list[dict[str, Any]] = []
    for item in raw_items:
        seller: dict[str, Any] = {
            "seller_name": item.get("seller_name"),
            "domain": item.get("domain"),
            "url": item.get("url"),
            "base_price": item.get("base_price"),
            "shipping_price": item.get("shipping_price"),
            "total_price": item.get("total_price"),
            "currency": item.get("currency", "USD"),
            "details": item.get("details"),
            "annotation": item.get("product_annotation"),
        }
        rating = item.get("rating") or {}
        seller["rating_value"] = rating.get("value")
        seller["rating_max"] = rating.get("rating_max", 5)
        results.append(seller)
    return results


# ── Reviews endpoint ──────────────────────────────────────────


def map_reviews_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Reviews response to review_summary dict."""
    rating = raw.get("rating") or {}
    result: dict[str, Any] = {
        "total_reviews": raw.get("reviews_count"),
        "average_rating": rating.get("value"),
        "rating_max": rating.get("rating_max", 5),
        "rating_groups": raw.get("rating_groups", []),
        "top_keywords": [
            kw.get("keyword", "") for kw in (raw.get("top_keywords") or [])
        ],
        "sample_reviews": [],
    }

    for item in (raw.get("items") or [])[:10]:
        review: dict[str, Any] = {
            "title": item.get("title"),
            "text": item.get("review_text"),
            "provided_by": item.get("provided_by"),
            "author": item.get("author"),
            "publication_date": item.get("publication_date"),
            "images": item.get("images", []),
        }
        item_rating = item.get("rating") or {}
        review["rating_value"] = item_rating.get("value")
        result["sample_reviews"].append(review)

    return result
