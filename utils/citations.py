"""
Turns OpenAlex reference IDs cited by the agents (e.g. [W2741809807]) into
numbered citations [1], [2] ... and builds the reference list from the real
metadata the scholarly_search tool retrieved.

Safety rule: an ID is only accepted if the tool actually returned that paper
in this run. Anything else the model wrote is removed, so a fabricated
reference can never reach the report.
"""

import re

_ID = re.compile(r"\[?\b(W\d{5,})\b\]?")


def format_reference(meta: dict) -> str:
    authors = meta.get("authors") or []
    if not authors:
        who = "Unknown authors"
    elif len(authors) > 3:
        who = ", ".join(authors[:3]) + ", et al."
    else:
        who = ", ".join(authors)
    venue = f" {meta['venue']}." if meta.get("venue") else ""
    return f"{who} ({meta.get('year', 'n.d.')}). {meta.get('title', '').rstrip('.')}.{venue}"


def apply_citations(investigation: dict, registry: dict) -> dict:
    registry = registry or {}
    order = []

    def number_for(wid):
        if wid not in registry:
            return None
        if wid not in order:
            order.append(wid)
        return order.index(wid) + 1

    def sub_text(text):
        def repl(m):
            n = number_for(m.group(1))
            return f"[{n}]" if n else ""
        out = _ID.sub(repl, str(text))
        out = re.sub(r"\s{2,}", " ", out).replace(" .", ".").replace(" ,", ",")
        return out.strip()

    # Evidence items
    for e in investigation.get("evidence", []):
        rid_match = _ID.search(str(e.get("reference_id", "")))
        n = number_for(rid_match.group(1)) if rid_match else None
        if n:
            meta = registry[rid_match.group(1)]
            e["citation"] = n
            e["source_type"] = "academic"
            e["source_title"] = meta["title"]
            e["source_url"] = meta["url"]
        else:
            e["citation"] = None
            e["source_type"] = "web" if str(e.get("source_url", "")).startswith("http") else "unverified"
        e.pop("reference_id", None)
        e["finding"] = sub_text(e.get("finding", ""))
        if e.get("citation"):
            # the citation number is shown next to the finding, so avoid "[1] [1]"
            e["finding"] = re.sub(r"\s*\[" + str(e["citation"]) + r"\]", "", e["finding"]).strip()

    # In-text citations in specialist findings
    for s in investigation.get("specialist_results", []):
        if s.get("parse_error"):
            continue
        for field in ("possible_root_causes", "cause_basis", "proposed_solutions", "risks_of_proposed_solutions"):
            s[field] = [sub_text(x) for x in s.get(field, [])]

    cr = investigation.get("critical_review", {})
    if not cr.get("parse_error"):
        for field in ("critical_findings", "alternative_explanations", "unresolved_uncertainty"):
            cr[field] = [sub_text(x) for x in cr.get(field, [])]
        if cr.get("overall_confidence_assessment"):
            cr["overall_confidence_assessment"] = sub_text(cr["overall_confidence_assessment"])

    investigation["references"] = [
        {"number": i + 1, "id": wid, "text": format_reference(registry[wid]),
         "url": registry[wid]["url"], "cited_by": registry[wid].get("cited_by", 0)}
        for i, wid in enumerate(order)
    ]
    investigation["related_literature"] = [
        {"id": wid, "text": format_reference(meta), "url": meta["url"]}
        for wid, meta in registry.items() if wid not in order
    ][:5]
    return investigation
