from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import load_settings
from odoo_client import OdooClient


QTY_TOLERANCE = 1e-9
PRODUCTION_BOM_CREATED_BEFORE = "2026-07-26 00:00:00"
CABINET_TYPE_PATTERN = re.compile(r"^CAB\d+$")
GROUP_PATTERN = re.compile(r"^([A-Z]+)")


class ApackHrdTransferError(RuntimeError):
    """Production analogas neleidžia sudaryti vienareikšmio perkėlimo plano."""


def canon(value: Any) -> str:
    return str(value or "").strip().upper()


def m2o_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    if isinstance(value, int):
        return value
    return None


def component_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for row in rows:
        sku = canon(row.get("sku"))
        quantity = float(row.get("quantity") or 0)
        if not sku or quantity <= 0:
            raise ApackHrdTransferError("BOM turi tuščią SKU arba neteisingą kiekį.")
        result[sku] += quantity
    return dict(sorted(result.items()))


def apack_signature(sku: str) -> tuple[str, str, str]:
    """Grąžina rinką, CAB tipą ir produkto grupę iš APACK SKU."""
    parts = canon(sku).split("-")
    market = parts[1] if len(parts) > 1 else ""
    cabinet_index = next(
        (index for index, part in enumerate(parts) if CABINET_TYPE_PATTERN.match(part)),
        None,
    )
    cabinet_type = parts[cabinet_index] if cabinet_index is not None else ""
    group = ""
    if cabinet_index is not None and cabinet_index + 1 < len(parts):
        match = GROUP_PATTERN.match(parts[cabinet_index + 1])
        group = match.group(1) if match else ""
    if not market or not cabinet_type or not group:
        raise ApackHrdTransferError(
            f"Nepavyko nustatyti APACK struktūros požymių: {canon(sku)}."
        )
    return market, cabinet_type, group


def structural_similarity(
    expected: dict[str, float],
    candidate: dict[str, float],
) -> tuple[int, int, int]:
    """Didesnė leksikografinė reikšmė reiškia artimesnę struktūrą."""
    expected_skus = set(expected)
    candidate_skus = set(candidate)
    overlap = len(expected_skus & candidate_skus)
    missing = len(expected_skus - candidate_skus)
    extra = len(candidate_skus - expected_skus)
    return overlap, -missing, -extra


def transfer_profile(
    *,
    new_apack_components: dict[str, float],
    new_hrd_a_components: dict[str, float],
    old_apack_components: dict[str, float],
    old_hrd_a_components: dict[str, float],
) -> tuple[str, ...]:
    """Grąžina analogų palyginimui skirtą komponentų perkėlimo profilį."""
    profile = []
    for sku in sorted(set(old_apack_components) - set(new_apack_components)):
        if new_hrd_a_components.get(sku, 0) <= QTY_TOLERANCE:
            continue
        actual_old_hrd = old_hrd_a_components.get(sku, 0)
        if actual_old_hrd > QTY_TOLERANCE:
            raise ApackHrdTransferError(
                f"{sku}: Production pora dviprasmiška. Komponentas yra "
                f"ir senajame APACK ({old_apack_components[sku]}), ir "
                f"senajame HRD-A ({actual_old_hrd})."
            )
        profile.append(sku)
    return tuple(profile)


def dataset_products(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    products: dict[str, dict[str, Any]] = {}
    for row in dataset.get("products", []):
        sku = canon(row.get("sku"))
        if not sku:
            continue
        if sku in products:
            raise ApackHrdTransferError(f"Dataset SKU kartojasi: {sku}")
        products[sku] = row
    return products


def select_dataset_pair(
    dataset: dict[str, Any],
    apack_sku: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    products = dataset_products(dataset)
    apack = products.get(canon(apack_sku))
    if apack is None:
        raise ApackHrdTransferError(f"Dataset nerastas APACK: {apack_sku}")

    cabinets = []
    for row in products.values():
        components = component_map(list(row.get("components") or []))
        if canon(apack_sku) not in components:
            continue
        hrd_a = [sku for sku in components if "HRD" in sku and sku.endswith("-A")]
        if len(components) == 2 and len(hrd_a) == 1:
            cabinets.append((row, hrd_a[0]))
    if not cabinets:
        raise ApackHrdTransferError(
            f"Dataset nerastas CABINET-A, kuriame yra {canon(apack_sku)}."
        )

    pairs = {hrd_a for _, hrd_a in cabinets}
    if len(pairs) != 1:
        raise ApackHrdTransferError(
            f"{canon(apack_sku)} susietas su keliais HRD-A: "
            + ", ".join(sorted(pairs))
        )
    hrd_a_sku = next(iter(pairs))
    hrd_a = products.get(hrd_a_sku)
    if hrd_a is None:
        raise ApackHrdTransferError(f"Dataset nerastas HRD-A BOM: {hrd_a_sku}")
    return apack, hrd_a, hrd_a_sku


def build_transfer_plan(
    *,
    new_apack: dict[str, Any],
    new_hrd_a: dict[str, Any],
    old_apack_components: dict[str, float],
    old_hrd_a_components: dict[str, float],
) -> list[dict[str, Any]]:
    new_apack_components = component_map(
        list(new_apack.get("components") or [])
    )
    new_hrd_components = component_map(
        list(new_hrd_a.get("components") or [])
    )
    plan = []
    # Senas Production APACK nustato komponento paskirtį: jeigu komponentas
    # buvo APACK, bet jo nėra naujame APACK ir jis yra naujame HRD-A, vadinasi
    # naujoje struktūroje jis turi būti perkeltas iš HRD-A į APACK.
    #
    # Perkeliame naują HRD-A kiekį, o ne seną APACK kiekį. Reform versijoje
    # kiekis galėjo teisėtai pasikeisti.
    for sku in sorted(set(old_apack_components) - set(new_apack_components)):
        available = new_hrd_components.get(sku, 0)
        if available <= QTY_TOLERANCE:
            continue
        actual_old_hrd = old_hrd_a_components.get(sku, 0)
        if actual_old_hrd > QTY_TOLERANCE:
            raise ApackHrdTransferError(
                f"{sku}: Production pora dviprasmiška. Komponentas yra "
                f"ir senajame APACK ({old_apack_components[sku]}), ir "
                f"senajame HRD-A ({actual_old_hrd})."
            )
        plan.append(
            {
                "component_sku": sku,
                "quantity": available,
                "from_hrd_a": canon(new_hrd_a.get("sku")),
                "to_apack": canon(new_apack.get("sku")),
                "production_apack_quantity": old_apack_components[sku],
                "new_hrd_a_quantity": available,
            }
        )
    return plan


def active_sequence_zero_boms(
    client: OdooClient,
) -> tuple[dict[int, str], dict[str, list[int]], dict[int, dict[str, float]]]:
    products = client.search_read_all(
        "product.product",
        [["default_code", "!=", False]],
        ["id", "default_code", "product_tmpl_id"],
        context={"active_test": False},
    )
    product_sku = {
        int(row["id"]): canon(row.get("default_code"))
        for row in products
        if canon(row.get("default_code"))
    }
    template_sku = {
        int(row["product_tmpl_id"][0]): canon(row.get("default_code"))
        for row in products
        if row.get("product_tmpl_id") and canon(row.get("default_code"))
    }
    boms = client.search_read_all(
        "mrp.bom",
        [
            ["active", "=", True],
            ["create_date", "<", PRODUCTION_BOM_CREATED_BEFORE],
        ],
        [
            "id",
            "product_tmpl_id",
            "product_id",
            "sequence",
            "create_date",
            "write_date",
        ],
    )
    candidates_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bom in boms:
        sku = product_sku.get(m2o_id(bom.get("product_id")) or -1, "")
        if not sku:
            sku = template_sku.get(
                m2o_id(bom.get("product_tmpl_id")) or -1,
                "",
            )
        if sku:
            candidates_by_parent[sku].append(bom)

    # Kandidatai jau apriboti iki patikimos Production būsenos:
    # įtraukiami BOM, sukurti iki 2026-07-25 dienos pabaigos. Tik tada
    # parenkamas mažiausias Sequence, o esant lygybei – naujausias Write Date.
    # Jei abu požymiai sutampa, paliekame visus kandidatus, kad one_bom()
    # aiškiai užblokuotų dviprasmį atvejį.
    bom_parent: dict[int, str] = {}
    by_parent: dict[str, list[int]] = defaultdict(list)
    for sku, candidates in candidates_by_parent.items():
        minimum_sequence = min(
            int(row.get("sequence") or 0) for row in candidates
        )
        preferred = [
            row
            for row in candidates
            if int(row.get("sequence") or 0) == minimum_sequence
        ]
        newest_write_date = max(
            str(row.get("write_date") or "") for row in preferred
        )
        selected = [
            row
            for row in preferred
            if str(row.get("write_date") or "") == newest_write_date
        ]
        for bom in selected:
            bom_id = int(bom["id"])
            bom_parent[bom_id] = sku
            by_parent[sku].append(bom_id)

    lines = client.search_read_all(
        "mrp.bom.line",
        [["bom_id", "in", sorted(bom_parent)]],
        ["bom_id", "product_id", "product_qty"],
    )
    components: dict[int, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for line in lines:
        bom_id = m2o_id(line.get("bom_id"))
        component_sku = product_sku.get(
            m2o_id(line.get("product_id")) or -1,
            "",
        )
        if bom_id in bom_parent and component_sku:
            components[bom_id][component_sku] += float(
                line.get("product_qty") or 0
            )
    return bom_parent, dict(by_parent), {
        bom_id: dict(sorted(values.items()))
        for bom_id, values in components.items()
    }


def one_bom(
    by_parent: dict[str, list[int]],
    sku: str,
    components: dict[int, dict[str, float]] | None = None,
) -> int:
    ids = by_parent.get(canon(sku), [])
    if len(ids) > 1 and components is not None:
        compositions = {
            tuple(sorted(components.get(bom_id, {}).items()))
            for bom_id in ids
        }
        if len(compositions) == 1:
            return min(ids)
    if len(ids) != 1:
        raise ApackHrdTransferError(
            f"Production {canon(sku)} turi {len(ids)} vienodai prioritetinių "
            "aktyvių BOM, sukurtų iki 2026-07-25, pagal mažiausią Sequence "
            "ir naujausią Write Date; "
            "tikėtasi 1."
        )
    return ids[0]


def production_cabinet_pairs(
    *,
    bom_parent: dict[int, str],
    components: dict[int, dict[str, float]],
) -> list[dict[str, Any]]:
    pairs = []
    for cabinet_bom_id, cabinet_sku in bom_parent.items():
        values = components.get(cabinet_bom_id, {})
        apacks = [
            sku for sku in values
            if sku.startswith("APACK-") and sku.endswith("-A")
        ]
        hrd_as = [
            sku for sku in values
            if "HRD" in sku and sku.endswith("-A")
        ]
        if len(values) == 2 and len(apacks) == 1 and len(hrd_as) == 1:
            pairs.append(
                {
                    "cabinet_sku": cabinet_sku,
                    "cabinet_bom_id": cabinet_bom_id,
                    "apack_sku": apacks[0],
                    "hrd_a_sku": hrd_as[0],
                }
            )
    return pairs


def choose_production_analog(
    *,
    apack_sku: str,
    new_apack_components: dict[str, float],
    new_hrd_a_components: dict[str, float],
    bom_parent: dict[int, str],
    by_parent: dict[str, list[int]],
    components: dict[int, dict[str, float]],
) -> dict[str, Any]:
    exact_ids = by_parent.get(canon(apack_sku), [])
    pairs = production_cabinet_pairs(
        bom_parent=bom_parent,
        components=components,
    )
    if exact_ids:
        exact_pair = [
            pair for pair in pairs if pair["apack_sku"] == canon(apack_sku)
        ]
        if len({(row["cabinet_sku"], row["hrd_a_sku"]) for row in exact_pair}) != 1:
            raise ApackHrdTransferError(
                f"Production nerasta viena CABINET-A pora APACK {canon(apack_sku)}."
            )
        selected = exact_pair[0]
        return {
            **selected,
            "match_method": "EXACT_SKU",
            "match_signature": apack_signature(apack_sku),
            "similarity": None,
        }

    target_signature = apack_signature(apack_sku)
    candidates = []
    for pair in pairs:
        try:
            signature = apack_signature(pair["apack_sku"])
        except ApackHrdTransferError:
            continue
        if signature[0] != target_signature[0] or signature[2] != target_signature[2]:
            continue
        candidate_bom_id = one_bom(
            by_parent,
            pair["apack_sku"],
            components,
        )
        apack_score = structural_similarity(
            new_apack_components,
            components.get(candidate_bom_id, {}),
        )
        hrd_bom_id = one_bom(by_parent, pair["hrd_a_sku"], components)
        hrd_score = structural_similarity(
            new_hrd_a_components,
            components.get(hrd_bom_id, {}),
        )
        score = apack_score + hrd_score
        profile = transfer_profile(
            new_apack_components=new_apack_components,
            new_hrd_a_components=new_hrd_a_components,
            old_apack_components=components.get(candidate_bom_id, {}),
            old_hrd_a_components=components.get(hrd_bom_id, {}),
        )
        candidates.append(
            {
                **pair,
                "match_method": "STRUCTURAL_ANALOG",
                "match_signature": target_signature,
                "candidate_signature": signature,
                "similarity": score,
                "apack_bom_id": candidate_bom_id,
                "hrd_a_bom_id": hrd_bom_id,
                "transfer_profile": profile,
            }
        )
    if not candidates:
        market, cabinet_type, group = target_signature
        raise ApackHrdTransferError(
            f"Nerastas Production analogas pagal {market}/{group}; "
            f"tikslinė CAB šeima {cabinet_type}."
        )

    same_cabinet = [
        row
        for row in candidates
        if row["candidate_signature"] == target_signature
    ]
    if same_cabinet:
        best_score = max(row["similarity"] for row in same_cabinet)
        best = [
            row for row in same_cabinet
            if row["similarity"] == best_score
        ]
        match_method = (
            "STRUCTURAL_ANALOG"
            if len(best) == 1
            else "PROFILE_CONSENSUS"
        )
    else:
        # Kitos CAB šeimos profilis tinkamas tik tada, kai visi tos pačios
        # rinkos ir grupės Production analogai sutaria. Struktūros panašumas
        # negali būti naudojamas vienam patogiam kandidatui išsirinkti.
        best = candidates
        best_score = None
        match_method = "CROSS_CAB_PROFILE_CONSENSUS"

    profiles = {row["transfer_profile"] for row in best}
    if len(profiles) != 1:
        profile_text = "; ".join(
            f"{row['apack_sku']}={list(row['transfer_profile'])}"
            for row in sorted(best, key=lambda item: item["apack_sku"])
        )
        raise ApackHrdTransferError(
            f"Keli nesutampantys Production perkėlimo profiliai pagal "
            f"{'/'.join(target_signature)}: {profile_text}"
        )
    selected = sorted(
        best,
        key=lambda row: (
            row["candidate_signature"][1],
            row["apack_sku"],
            row["cabinet_sku"],
        ),
    )[0]
    return {
        **selected,
        "match_method": match_method,
        "similarity": best_score,
        "profile_consensus_candidates": len(best),
        "transfer_profile": list(selected["transfer_profile"]),
    }


def production_pair(
    *,
    apack_sku: str,
    expected_hrd_a_sku: str,
    new_apack_components: dict[str, float],
    new_hrd_a_components: dict[str, float],
    bom_parent: dict[int, str],
    by_parent: dict[str, list[int]],
    components: dict[int, dict[str, float]],
) -> tuple[int, int, str, dict[str, Any]]:
    analog = choose_production_analog(
        apack_sku=apack_sku,
        new_apack_components=new_apack_components,
        new_hrd_a_components=new_hrd_a_components,
        bom_parent=bom_parent,
        by_parent=by_parent,
        components=components,
    )
    analog_apack_sku = analog["apack_sku"]
    apack_bom_id = analog.get("apack_bom_id") or one_bom(
        by_parent, analog_apack_sku, components
    )
    hrd_a_sku = analog["hrd_a_sku"]
    return (
        apack_bom_id,
        analog.get("hrd_a_bom_id")
        or one_bom(by_parent, hrd_a_sku, components),
        analog["cabinet_sku"],
        analog,
    )


def analyze(
    *,
    dataset: dict[str, Any],
    apack_sku: str,
    client: OdooClient,
) -> dict[str, Any]:
    new_apack, new_hrd_a, hrd_a_sku = select_dataset_pair(
        dataset,
        apack_sku,
    )
    bom_parent, by_parent, components = active_sequence_zero_boms(client)
    apack_bom_id, hrd_a_bom_id, cabinet_sku, analog = production_pair(
        apack_sku=apack_sku,
        expected_hrd_a_sku=hrd_a_sku,
        new_apack_components=component_map(
            list(new_apack.get("components") or [])
        ),
        new_hrd_a_components=component_map(
            list(new_hrd_a.get("components") or [])
        ),
        bom_parent=bom_parent,
        by_parent=by_parent,
        components=components,
    )
    plan = build_transfer_plan(
        new_apack=new_apack,
        new_hrd_a=new_hrd_a,
        old_apack_components=components.get(apack_bom_id, {}),
        old_hrd_a_components=components.get(hrd_a_bom_id, {}),
    )
    return {
        "status": "TRANSFERRED" if plan else "NO_TRANSFER",
        "odoo_changes": 0,
        "apack_sku": canon(apack_sku),
        "hrd_a_sku": hrd_a_sku,
        "cabinet_a_sku": cabinet_sku,
        "production_analog_apack_sku": analog["apack_sku"],
        "production_analog_hrd_a_sku": analog["hrd_a_sku"],
        "analog_match_method": analog["match_method"],
        "analog_match_signature": analog["match_signature"],
        "analog_similarity": analog["similarity"],
        "analog_transfer_profile": analog.get("transfer_profile"),
        "profile_consensus_candidates": analog.get(
            "profile_consensus_candidates", 1
        ),
        "production_apack_bom_id": apack_bom_id,
        "production_hrd_a_bom_id": hrd_a_bom_id,
        "new_apack_components_before": component_map(
            list(new_apack.get("components") or [])
        ),
        "new_hrd_a_components_before": component_map(
            list(new_hrd_a.get("components") or [])
        ),
        "production_apack_components": components.get(apack_bom_id, {}),
        "production_hrd_a_components": components.get(hrd_a_bom_id, {}),
        "transfer_plan": plan,
    }


def dataset_apack_skus(dataset: dict[str, Any]) -> list[str]:
    return sorted(
        sku
        for sku in dataset_products(dataset)
        if sku.startswith("APACK-") and sku.endswith("-A")
    )


def analyze_all(
    *,
    dataset: dict[str, Any],
    client: OdooClient,
) -> dict[str, Any]:
    bom_parent, by_parent, components = active_sequence_zero_boms(client)
    results: list[dict[str, Any]] = []

    for apack_sku in dataset_apack_skus(dataset):
        try:
            new_apack, new_hrd_a, hrd_a_sku = select_dataset_pair(
                dataset,
                apack_sku,
            )
            apack_bom_id, hrd_a_bom_id, cabinet_sku, analog = production_pair(
                apack_sku=apack_sku,
                expected_hrd_a_sku=hrd_a_sku,
                new_apack_components=component_map(
                    list(new_apack.get("components") or [])
                ),
                new_hrd_a_components=component_map(
                    list(new_hrd_a.get("components") or [])
                ),
                bom_parent=bom_parent,
                by_parent=by_parent,
                components=components,
            )
            plan = build_transfer_plan(
                new_apack=new_apack,
                new_hrd_a=new_hrd_a,
                old_apack_components=components.get(apack_bom_id, {}),
                old_hrd_a_components=components.get(hrd_a_bom_id, {}),
            )
            results.append(
                {
                    "status": "TRANSFERRED" if plan else "NO_TRANSFER",
                    "apack_sku": apack_sku,
                    "hrd_a_sku": hrd_a_sku,
                    "cabinet_a_sku": cabinet_sku,
                    "production_analog_apack_sku": analog["apack_sku"],
                    "production_analog_hrd_a_sku": analog["hrd_a_sku"],
                    "analog_match_method": analog["match_method"],
                    "analog_match_signature": analog["match_signature"],
                    "analog_similarity": analog["similarity"],
                    "analog_transfer_profile": analog.get(
                        "transfer_profile"
                    ),
                    "profile_consensus_candidates": analog.get(
                        "profile_consensus_candidates", 1
                    ),
                    "production_apack_bom_id": apack_bom_id,
                    "production_hrd_a_bom_id": hrd_a_bom_id,
                    "transfer_plan": plan,
                }
            )
        except ApackHrdTransferError as exc:
            results.append(
                {
                    "status": "BLOCKED",
                    "apack_sku": apack_sku,
                    "reason": str(exc),
                    "transfer_plan": [],
                }
            )

    counts = {
        status: sum(row["status"] == status for row in results)
        for status in ("TRANSFERRED", "NO_TRANSFER", "BLOCKED")
    }
    return {
        "status": "PASS" if counts["BLOCKED"] == 0 else "BLOCKED",
        "odoo_changes": 0,
        "statistics": {
            "apack_total": len(results),
            **{key.lower(): value for key, value in counts.items()},
            "component_transfers": sum(
                len(row["transfer_plan"]) for row in results
            ),
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only APACK / HRD-A komponentų perkėlimo analizė."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--apack-sku")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    settings = load_settings()
    client = OdooClient(settings)
    client.authenticate()
    if args.all == bool(args.apack_sku):
        parser.error("Nurodyk tik vieną: --all arba --apack-sku.")
    result = (
        analyze_all(dataset=dataset, client=client)
        if args.all
        else analyze(
            dataset=dataset,
            apack_sku=args.apack_sku,
            client=client,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 80)
    print("APACK / HRD-A TRANSFER ANALYSIS")
    print("=" * 80)
    print("Statusas:", result["status"])
    print("Production BOM sukurti iki: 2026-07-25 imtinai")
    if args.all:
        stats = result["statistics"]
        print("APACK iš viso:", stats["apack_total"])
        print("Su perkėlimais:", stats["transferred"])
        print("Be perkėlimų:", stats["no_transfer"])
        print("Blokuoti:", stats["blocked"])
        print("Komponentų perkėlimai:", stats["component_transfers"])
        for row in result["results"]:
            if row["status"] == "BLOCKED":
                print(f"  BLOCKED {row['apack_sku']}: {row['reason']}")
    else:
        print("APACK:", result["apack_sku"])
        print("HRD-A:", result["hrd_a_sku"])
        print("CABINET-A:", result["cabinet_a_sku"])
        print("Perkeliami komponentai:", len(result["transfer_plan"]))
        for row in result["transfer_plan"]:
            print(
                f"  {row['component_sku']}: {row['quantity']} "
                f"{row['from_hrd_a']} -> {row['to_apack']}"
            )
    print("Failas:", args.output)
    print("Odoo pakeitimai: 0")


if __name__ == "__main__":
    main()
