"""Local suggestion pool for first-load prompt chips."""

from __future__ import annotations

import random
import re

SUGGESTION_POOL: list[dict[str, str]] = [
    {
        "label": "Noise-Canceling Headphones",
        "query": "What are the best noise-canceling wireless headphones under $200?",
    },
    {
        "label": "Large Air Fryers",
        "query": "I'm looking for a large capacity air fryer for a family of four.",
    },
    {
        "label": "Men's Running Shoes",
        "query": "Can you find highly-rated men's running shoes for marathon training?",
    },
    {
        "label": "Sensitive Skincare",
        "query": "What are some recommended facial moisturizers for sensitive skin?",
    },
    {
        "label": "Gaming Laptops",
        "query": "Show me gaming laptops with an RTX 4070 graphics card.",
    },
    {
        "label": "Programmable Coffee Makers",
        "query": "I need a programmable drip coffee maker with a thermal carafe.",
    },
    {
        "label": "Thick Yoga Mats",
        "query": "Find me extra thick yoga mats with good grip for hot yoga.",
    },
    {
        "label": "Fitness Smartwatches",
        "query": "Compare the latest features of top-rated fitness smartwatches.",
    },
    {
        "label": "Ergonomic Office Chairs",
        "query": "What are the best ergonomic office chairs for lower back support?",
    },
    {
        "label": "Pet Hair Vacuums",
        "query": "I'm looking for a robot vacuum that handles pet hair well.",
    },
    {
        "label": "4-Person Camping Tents",
        "query": "Show me 4-person waterproof camping tents for summer trips.",
    },
    {
        "label": "Electric Toothbrushes",
        "query": "What are the top-rated electric toothbrushes with pressure sensors?",
    },
    {
        "label": "Quiet Mechanical Keyboards",
        "query": "Find me quiet mechanical keyboards suitable for an office environment.",
    },
    {
        "label": "Portable Power Banks",
        "query": "I need a high-capacity portable power bank for fast charging.",
    },
    {
        "label": "Multi-Cooker Options",
        "query": "What is the best multi-cooker for pressure cooking and air frying?",
    },
    {
        "label": "Ergonomic Wireless Mice",
        "query": "Show me ergonomic wireless mice for long hours of computer work.",
    },
    {
        "label": "Floral Summer Dresses",
        "query": "I'm looking for floral midi dresses for a summer wedding.",
    },
    {
        "label": "Orthopedic Dog Beds",
        "query": "Find me orthopedic dog beds for large senior dogs.",
    },
    {
        "label": "Waterproof Bluetooth Speakers",
        "query": "What are the best waterproof portable Bluetooth speakers for the beach?",
    },
    {
        "label": "Adjustable Standing Desks",
        "query": "Show me electric height-adjustable standing desks with memory presets.",
    },
    {
        "label": "Kitchen Knife Sets",
        "query": "I need a high-quality stainless steel kitchen knife set with a block.",
    },
    {
        "label": "Travel Backpacks",
        "query": "Find me carry-on sized backpacks with a dedicated laptop compartment.",
    },
    {
        "label": "Ionic Hair Dryers",
        "query": "What are the best ionic hair dryers for reducing frizz?",
    },
    {
        "label": "Strategy Board Games",
        "query": "Recommend some popular strategy board games for 2 to 4 players.",
    },
    {
        "label": "Beginner Mirrorless Cameras",
        "query": "Show me mirrorless cameras that are good for beginner photography.",
    },
    {
        "label": "Cooling Weighted Blankets",
        "query": "I'm looking for a 15-pound cooling weighted blanket.",
    },
    {
        "label": "Men's Leather Watches",
        "query": "Find me classic leather strap watches for men under $500.",
    },
    {
        "label": "Cordless Power Drills",
        "query": "What are the best cordless power drill sets for home DIY projects?",
    },
    {
        "label": "Video Baby Monitors",
        "query": "Show me video baby monitors with night vision and long range.",
    },
    {
        "label": "Compact Patio Grills",
        "query": "I need a compact liquid propane gas grill for a small patio.",
    },
    {
        "label": "Drawing Tablets",
        "query": "Compare the latest tablets for drawing and graphic design.",
    },
    {
        "label": "High-Power Blenders",
        "query": "What are the most powerful blenders for making green smoothies?",
    },
    {
        "label": "Women's Hiking Boots",
        "query": "Find me waterproof hiking boots for women with good ankle support.",
    },
    {
        "label": "Smart Home Hubs",
        "query": "Show me smart home hubs that are compatible with Matter.",
    },
    {
        "label": "Convection Toaster Ovens",
        "query": "I'm looking for a convection toaster oven that can fit a 12-inch pizza.",
    },
    {
        "label": "Polarized Sunglasses",
        "query": "What are some stylish polarized sunglasses for driving?",
    },
    {
        "label": "Gooseneck Electric Kettles",
        "query": "Find me gooseneck electric kettles with precise temperature control.",
    },
    {
        "label": "Slim Fitness Trackers",
        "query": "Show me slim fitness trackers that monitor sleep and heart rate.",
    },
    {
        "label": "Hardside Luggage Sets",
        "query": "I need a 3-piece hardside luggage set with TSA-approved locks.",
    },
    {
        "label": "Low-Light Indoor Plants",
        "query": "What are some low-maintenance indoor plants that thrive in low light?",
    },
]


def sample_suggestions(count: int) -> list[dict[str, str]]:
    limit = max(1, min(count, len(SUGGESTION_POOL)))
    return [dict(item) for item in random.sample(SUGGESTION_POOL, limit)]


def related_suggestions(seed_query: str, count: int) -> list[dict[str, str]]:
    normalized = (seed_query or "").strip().lower()
    if not normalized:
        return sample_suggestions(count)

    query_tokens = set(re.findall(r"[a-z0-9]+", normalized))
    scored: list[tuple[int, dict[str, str]]] = []

    for item in SUGGESTION_POOL:
        haystack = f"{item['label']} {item['query']}".lower()
        haystack_tokens = set(re.findall(r"[a-z0-9]+", haystack))
        overlap = len(query_tokens & haystack_tokens)
        if overlap > 0 and item["query"].casefold() != normalized.casefold():
            scored.append((overlap, item))

    if not scored:
        return sample_suggestions(count)

    scored.sort(key=lambda pair: (-pair[0], pair[1]["label"]))
    deduped: list[dict[str, str]] = []
    seen_queries: set[str] = set()
    for _, item in scored:
        query_key = item["query"].casefold()
        if query_key in seen_queries:
            continue
        seen_queries.add(query_key)
        deduped.append(dict(item))
        if len(deduped) >= count:
            break

    if len(deduped) < count:
        for item in sample_suggestions(count):
            query_key = item["query"].casefold()
            if query_key in seen_queries:
                continue
            seen_queries.add(query_key)
            deduped.append(item)
            if len(deduped) >= count:
                break

    return deduped
