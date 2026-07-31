from __future__ import annotations

import json
import mimetypes
import os
import re
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from tools.cards.pipeline import card_detail, card_previews, create_card_draft, create_card_from_set_item, ensure_set_card_drafts, list_card_drafts, list_templates, update_card_draft

from .generation import DEFAULT_LIVE_MODEL_ID, fetch_model_catalogue, simulation_model, unavailable_live_model
from .pexels import STARTER_PHOTO_IDS, get_pexels_photo, has_pexels_api_key, is_plausible_portrait, search_pexels
from .recipes import STARTER_RECIPE, recipe_from_payload
from .runs import RunManager
from .workspace import WorkspaceError, WorkspaceStore, new_id, now_iso
from .workflow import BASELINE_RUN_ID, CandidateSelectionStore, FinishStore, SetManager, SetStore, create_finish_trial, lock_finish, run_purpose, stage_eligibility


_models_cache: tuple[list[dict[str, Any]], float] | None = None


def fetch_models() -> list[dict[str, Any]]:
    global _models_cache
    import time

    if _models_cache and time.time() - _models_cache[1] < 3600:
        return _models_cache[0]
    try:
        models = fetch_model_catalogue()
        if len(models) > 1:
            _models_cache = (models, time.time())
            return models
    except requests.RequestException:
        pass
    return [simulation_model(), unavailable_live_model(DEFAULT_LIVE_MODEL_ID)]


def _models_for_store(store: WorkspaceStore) -> list[dict[str, Any]]:
    models = fetch_models()
    known = {str(item.get("id")) for item in models}
    stale = [str(recipe.get("model")) for recipe in store.read().get("recipes", []) if recipe.get("model") not in known]
    return [*models, *(unavailable_live_model(model_id) for model_id in dict.fromkeys(stale))]


def _workspace_response(store: WorkspaceStore, manager: RunManager) -> dict[str, Any]:
    _ensure_starter_recipe(store)
    finish_store = FinishStore(store)
    set_manager = SetManager(store, manager)
    sets = set_manager.list()
    workspace = store.payload()
    selection = workspace.get("candidate_selection")
    baseline = BASELINE_RUN_ID if any(item.get("run_id") == BASELINE_RUN_ID and item.get("purpose") == "exploration" for item in manager.list()) else next((item.get("run_id") for item in manager.list() if item.get("purpose") == "exploration" and item.get("status") == "complete"), None)
    return {
        "ok": True,
        "workspace": workspace,
        "runs": manager.list(),
        "cards": list_card_drafts(store),
        "candidate_selection": selection,
        "finishes": finish_store.list(),
        "sets": sets,
        "active_set_id": workspace.get("active_set_id"),
        "baseline_exploration_run_id": baseline,
        "models": _models_for_store(store),
        "integrations": {
            "pexels": {"configured": has_pexels_api_key()},
            "openrouter": {"configured": bool(os.environ.get("OPENROUTER_API_KEY"))},
        },
        "starter": {"photo_ids": list(STARTER_PHOTO_IDS)},
    }


def _ensure_starter_recipe(store: WorkspaceStore) -> None:
    bundled_reference_ids = store.ensure_bundled_references()
    data = store.read()
    if data.get("recipes"):
        return
    recipe = recipe_from_payload({**STARTER_RECIPE, "reference_ids": bundled_reference_ids}, new_id("recipe"), now_iso())
    store.mutate(lambda current: (current["recipes"].append(recipe), current.update({"active_recipe_id": recipe["id"]})))


def _find_item(data: dict[str, Any], collection: str, item_id: str) -> dict[str, Any]:
    item = next((candidate for candidate in data.get(collection, []) if str(candidate.get("id")) == item_id), None)
    if not item:
        raise ValueError(f"unknown {collection[:-1]} {item_id}")
    return item


def _parse_upload(body: bytes, content_type: str) -> tuple[dict[str, str], str, bytes, str]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    fields: dict[str, str] = {}
    filename, file_content, file_type = "", b"", ""
    for part in message.iter_attachments():
        name = part.get_param("name", header="content-disposition")
        value = part.get_payload(decode=True) or b""
        if part.get_filename():
            filename, file_content, file_type = part.get_filename(), value, part.get_content_type()
        elif name:
            fields[str(name)] = value.decode("utf-8", errors="replace")
    if not file_content:
        raise ValueError("multipart request did not include an image file")
    return fields, filename, file_content, file_type


def _import_source(store: WorkspaceStore, candidate: dict[str, Any], include_in_benchmark: bool = True) -> dict[str, Any]:
    photo_id = candidate.get("pexels_photo_id")
    if photo_id is None:
        raise ValueError("Pexels result is missing its photo ID")
    existing = next(
        (
            source for source in store.read().get("sources", [])
            if str((source.get("provenance") or {}).get("photo_id")) == str(photo_id)
        ),
        None,
    )
    if existing:
        if include_in_benchmark:
            store.mutate(lambda data: data["benchmark_source_ids"].append(existing["id"]) if existing["id"] not in data["benchmark_source_ids"] else None)
        return {"photo_id": photo_id, "status": "deduplicated", "source_id": existing["id"]}
    url = str(candidate.get("selected_image_url") or candidate.get("original_image_url") or "")
    if not url:
        raise ValueError("Pexels result has no downloadable image")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    record = store.add_image_record(
        "source", str(candidate.get("photographer") or f"Pexels {photo_id}"),
        f"pexels-{photo_id or new_id('source')}.jpg", response.content, response.headers.get("Content-Type"),
    )

    def annotate(data: dict[str, Any]) -> None:
        source = _find_item(data, "sources", str(record["id"]))
        if not record.get("deduplicated"):
            source["provenance"] = {
                "kind": "pexels", "photo_id": photo_id, "photographer": candidate.get("photographer"),
                "photographer_url": candidate.get("photographer_url"), "photo_page_url": candidate.get("photo_page_url"),
                "license_page": candidate.get("license_page"), "query": candidate.get("query"),
                "original_image_url": candidate.get("original_image_url"),
            }
        if include_in_benchmark and source["id"] not in data["benchmark_source_ids"]:
            data["benchmark_source_ids"].append(source["id"])

    store.mutate(annotate)
    return {"photo_id": photo_id, "status": "deduplicated" if record.get("deduplicated") else "imported", "source_id": record["id"]}


def bulk_import_sources(store: WorkspaceStore, candidates: list[dict[str, Any]], include_in_benchmark: bool = True) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            results.append(_import_source(store, dict(candidate), include_in_benchmark))
        except Exception as exc:
            results.append({"photo_id": candidate.get("pexels_photo_id"), "status": "failed", "error": str(exc)})
    return {
        "results": results,
        "imported": sum(item["status"] == "imported" for item in results),
        "deduplicated": sum(item["status"] == "deduplicated" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
    }


class WorkbenchHandler(BaseHTTPRequestHandler):
    store: WorkspaceStore = WorkspaceStore()
    manager: RunManager

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            if path in {"", "/api/workspace"}:
                self.send_json(_workspace_response(self.store, self.manager))
                return
            if path == "/api/models":
                self.send_json({"ok": True, "models": _models_for_store(self.store)})
                return
            if path == "/api/templates":
                self.send_json({"ok": True, "templates": list_templates()})
                return
            if path == "/api/runs":
                self.send_json({"ok": True, "runs": self.manager.list()})
                return
            if path == "/api/cards":
                include_discarded = parse_qs(parsed.query).get("include_discarded", ["false"])[0] == "true"
                cards = list_card_drafts(self.store, include_discarded)
                if parse_qs(parsed.query).get("active_set", ["false"])[0] == "true":
                    active_set_id = self.store.read().get("active_set_id")
                    cards = [card for card in cards if card.get("set_id") == active_set_id]
                self.send_json({"ok": True, "cards": cards})
                return
            if path == "/api/candidate-selection":
                selection = CandidateSelectionStore(self.store).current()
                self.send_json({"ok": True, "candidate_selection": selection})
                return
            if path == "/api/finishes":
                self.send_json({"ok": True, "finishes": FinishStore(self.store).list()})
                return
            match = re.fullmatch(r"/api/finish-trials/([^/]+)/compare", path)
            if match:
                other = parse_qs(parsed.query).get("with", [""])[0]
                if not other:
                    raise ValueError("cohort comparison requires a second trial id")
                self.send_json({"ok": True, "comparison": self.manager.compare_finish_trials(match.group(1), other)})
                return
            match = re.fullmatch(r"/api/finishes/([^/]+)", path)
            if match:
                self.send_json({"ok": True, "finish": FinishStore(self.store).payload(FinishStore(self.store).read(match.group(1)))})
                return
            if path == "/api/sets":
                self.send_json({"ok": True, "sets": SetManager(self.store, self.manager).list(), "active_set_id": self.store.read().get("active_set_id")})
                return
            if path == "/api/stages":
                workspace = self.store.read()
                selection = CandidateSelectionStore(self.store).current()
                finishes = [FinishStore(self.store).read(item["finish_id"]) for item in FinishStore(self.store).list()]
                sets = [SetManager(self.store, self.manager).get(item["set_id"]) for item in SetManager(self.store, self.manager).list()]
                self.send_json({"ok": True, "stages": [stage_eligibility(stage, workspace, selection, finishes, sets) for stage in ("sources", "explore", "finish", "set", "frames", "completed")]})
                return
            match = re.fullmatch(r"/api/sets/([^/]+)", path)
            if match:
                self.send_json({"ok": True, "set": SetManager(self.store, self.manager).get(match.group(1))})
                return
            match = re.fullmatch(r"/api/runs/([^/]+)/compare", path)
            if match:
                other = parse_qs(parsed.query).get("with", [""])[0]
                if not other:
                    raise ValueError("compare requires a second run id")
                self.send_json({"ok": True, "comparison": self.manager.compare(match.group(1), other)})
                return
            match = re.fullmatch(r"/api/runs/([^/]+)", path)
            if match:
                self.send_json({"ok": True, "run": self.manager.get(match.group(1))})
                return
            match = re.fullmatch(r"/api/cards/([^/]+)", path)
            if match:
                self.send_json({"ok": True, "card": card_detail(self.store, match.group(1))})
                return
            if path.startswith("/asset/"):
                self.serve_asset(unquote(path.removeprefix("/asset/")))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.error(str(exc), HTTPStatus.NOT_FOUND if "does not exist" in str(exc) else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            if path == "/api/sources/search":
                payload = self._json()
                query = str(payload.get("query") or "").strip()
                if not query:
                    raise ValueError("search query is required")
                results = [
                    {**candidate, "preview_url": candidate.get("selected_image_url"), "provenance": {"kind": "pexels", "photographer": candidate.get("photographer"), "photo_page_url": candidate.get("photo_page_url"), "license_page": candidate.get("license_page")}}
                    for candidate in search_pexels(
                        query, int(payload.get("count", 12)), "portrait",
                        page=max(1, int(payload.get("page", 1))), per_page=min(40, max(1, int(payload.get("count", 12)))),
                    )
                    if is_plausible_portrait(candidate)
                ]
                self.send_json({"ok": True, "results": results, "page": max(1, int(payload.get("page", 1))), "has_more": len(results) == int(payload.get("count", 12))})
                return
            if path == "/api/sources/import":
                payload = self._json()
                candidate = dict(payload.get("candidate") or {})
                result = bulk_import_sources(self.store, [candidate], bool(payload.get("include_in_benchmark", True)))
                if result["failed"]:
                    raise ValueError(result["results"][0]["error"])
                self.send_json({"ok": True, "workspace": self.store.payload(), **result})
                return
            if path == "/api/sources/import-bulk":
                payload = self._json()
                candidates = payload.get("candidates") or []
                if not isinstance(candidates, list) or not candidates:
                    raise ValueError("select at least one search result to import")
                result = bulk_import_sources(self.store, [dict(item) for item in candidates], bool(payload.get("include_in_benchmark", True)))
                self.send_json({"ok": True, "workspace": self.store.payload(), **result})
                return
            if path == "/api/sources/starter":
                candidates: list[dict[str, Any]] = []
                lookup_failures: list[dict[str, Any]] = []
                for photo_id in STARTER_PHOTO_IDS:
                    try:
                        candidates.append(get_pexels_photo(photo_id))
                    except Exception as exc:
                        lookup_failures.append({"photo_id": photo_id, "status": "failed", "error": str(exc)})
                result = bulk_import_sources(self.store, candidates, True)
                result["results"] = [*result["results"], *lookup_failures]
                result["failed"] += len(lookup_failures)
                self.send_json({"ok": True, "workspace": self.store.payload(), **result})
                return
            match = re.fullmatch(r"/api/references/([^/]+)/replace", path)
            if match:
                _, filename, content, content_type = _parse_upload(
                    self.rfile.read(int(self.headers.get("Content-Length", "0"))), self.headers.get("Content-Type", "")
                )
                record = self.store.replace_reference_image(match.group(1), filename, content, content_type)
                self.send_json({"ok": True, "workspace": self.store.payload(), "record": record})
                return
            if path == "/api/sources/upload" or path == "/api/references/upload":
                fields, filename, content, content_type = _parse_upload(self.rfile.read(int(self.headers.get("Content-Length", "0"))), self.headers.get("Content-Type", ""))
                kind = "source" if path.startswith("/api/sources") else "reference"
                record = self.store.add_image_record(kind, fields.get("label", ""), filename, content, content_type)
                if kind == "source":
                    self.store.mutate(
                        lambda data: data["benchmark_source_ids"].append(record["id"])
                        if record["id"] not in data["benchmark_source_ids"] else None
                    )
                self.send_json({"ok": True, "workspace": self.store.payload(), "record": record})
                return
            if path == "/api/benchmark":
                payload = self._json()
                requested = [str(item) for item in payload.get("source_ids", [])]
                def update(data: dict[str, Any]) -> None:
                    ids = {str(item["id"]) for item in data["sources"]}
                    if any(item not in ids for item in requested):
                        raise ValueError("source selection contains an unknown image")
                    data["benchmark_source_ids"] = requested
                self.store.mutate(update)
                self.send_json({"ok": True, "workspace": self.store.payload()})
                return
            if path == "/api/recipes":
                payload = self._json()
                recipe = recipe_from_payload(payload, new_id("recipe"), now_iso())
                def add(data: dict[str, Any]) -> None:
                    known = {str(item["id"]) for item in data["references"]}
                    if any(item not in known for item in recipe["reference_ids"]):
                        raise ValueError("recipe contains an unknown style reference")
                    data["recipes"].append(recipe)
                    if data.get("active_recipe_id") is None:
                        data["active_recipe_id"] = recipe["id"]
                self.store.mutate(add)
                self.send_json({"ok": True, "workspace": self.store.payload(), "recipe": recipe})
                return
            match = re.fullmatch(r"/api/recipes/([^/]+)/duplicate", path)
            if match:
                source = _find_item(self.store.read(), "recipes", match.group(1))
                recipe = recipe_from_payload({**source, "name": f"{source['name']} copy"}, new_id("recipe"), now_iso())
                self.store.mutate(lambda data: data["recipes"].append(recipe))
                self.send_json({"ok": True, "workspace": self.store.payload(), "recipe": recipe})
                return
            match = re.fullmatch(r"/api/recipes/([^/]+)/select", path)
            if match:
                recipe_id = match.group(1)
                self.store.mutate(lambda data: data.update({"active_recipe_id": _find_item(data, "recipes", recipe_id)["id"]}))
                self.send_json({"ok": True, "workspace": self.store.payload()})
                return
            if path == "/api/runs":
                payload = self._json()
                run = self.manager.create(
                    dict(payload.get("recipe") or {}),
                    [str(item) for item in payload.get("source_ids") or []],
                    int(payload.get("outputs_per_source", 1)),
                    str(payload.get("execution_mode") or ""),
                    _models_for_store(self.store),
                    purpose=str(payload.get("purpose") or "exploration"),
                )
                self.send_json({"ok": True, "run": run, "workspace": self.store.payload()})
                return
            if path == "/api/candidate-selection":
                payload = self._json()
                refs = payload.get("items") or payload.get("selected_items") or []
                selection = CandidateSelectionStore(self.store).save([dict(item) for item in refs])
                self.send_json({"ok": True, "candidate_selection": selection, "workspace": self.store.payload()})
                return
            match = re.fullmatch(r"/api/candidate-selection/(remove|reorder)", path)
            if match:
                payload = self._json()
                selection_store = CandidateSelectionStore(self.store)
                if match.group(1) == "remove":
                    selection = selection_store.clear_item(str(payload.get("run_id") or ""), str(payload.get("item_id") or payload.get("run_item_id") or ""))
                else:
                    selection = selection_store.reorder([dict(item) for item in payload.get("items") or []])
                self.send_json({"ok": True, "candidate_selection": selection, "workspace": self.store.payload()})
                return
            if path == "/api/finish-trials":
                payload = self._json()
                selection = CandidateSelectionStore(self.store).current()
                if not selection or int(payload.get("selection_revision", -1)) != int(selection.get("revision", -2)):
                    raise ValueError("the current candidate selection revision is required")
                trial = create_finish_trial(self.store, self.manager, selection, dict(payload.get("recipe") or {}), _models_for_store(self.store))
                self.send_json({"ok": True, "run": trial})
                return
            match = re.fullmatch(r"/api/(?:finishes|finish-trials)/([^/]+)/lock", path)
            if match:
                finish_store = FinishStore(self.store)
                selection = CandidateSelectionStore(self.store).current()
                if not selection:
                    raise ValueError("candidate selection no longer exists")
                finish = lock_finish(self.store, self.manager._read(match.group(1)), selection, finish_store)
                self.send_json({"ok": True, "finish": finish})
                return
            if path == "/api/sets":
                payload = self._json()
                result = SetManager(self.store, self.manager).build(str(payload.get("name") or ""), str(payload.get("finish_id") or ""), [str(item) for item in payload.get("source_ids")] if payload.get("source_ids") is not None else None, _models_for_store(self.store), str(payload.get("execution_mode") or "") or None)
                self.send_json({"ok": True, "set": result, "workspace": self.store.payload()})
                return
            match = re.fullmatch(r"/api/sets/([^/]+)/(retry|switch|drafts)", path)
            if match:
                set_manager = SetManager(self.store, self.manager)
                if match.group(2) == "retry":
                    result = set_manager.retry(match.group(1), _models_for_store(self.store))
                elif match.group(2) == "switch":
                    result = set_manager.switch(match.group(1))
                else:
                    result = {"items": ensure_set_card_drafts(self.store, match.group(1))}
                self.send_json({"ok": True, "set": result if match.group(2) != "drafts" else set_manager.get(match.group(1)), **({"cards": result["items"]} if match.group(2) == "drafts" else {})})
                return
            match = re.fullmatch(r"/api/runs/([^/]+)/review", path)
            if match:
                payload = self._json()
                run = self.manager.update_review(match.group(1), str(payload.get("verdict") or ""), str(payload.get("note") or ""))
                self.send_json({"ok": True, "run": run})
                return
            match = re.fullmatch(r"/api/runs/([^/]+)/duplicate-recipe", path)
            if match:
                self.send_json({"ok": True, "recipe": self.manager.duplicate_recipe(match.group(1)), "workspace": self.store.payload()})
                return
            if path == "/api/cards":
                payload = self._json()
                if payload.get("set_id") and payload.get("set_item_id"):
                    card = create_card_from_set_item(self.store, str(payload["set_id"]), str(payload["set_item_id"]), str(payload.get("label") or ""), str(payload.get("preset") or "bust"), str(payload.get("treatment") or "painterly"))
                else:
                    # Deprecated compatibility endpoint for existing saved URLs.
                    card = create_card_draft(self.store, str(payload.get("run_id") or ""), str(payload.get("run_item_id") or ""), str(payload.get("label") or "Experimental claimant"), str(payload.get("preset") or "bust"), str(payload.get("treatment") or "painterly"))
                self.send_json({"ok": True, "card": card})
                return
            match = re.fullmatch(r"/api/cards/([^/]+)/decision", path)
            if match:
                payload = self._json()
                self.send_json({"ok": True, "card": update_card_draft(self.store, match.group(1), {"decision": payload.get("decision")})})
                return
            match = re.fullmatch(r"/api/cards/([^/]+)/previews", path)
            if match:
                self.send_json({"ok": True, "previews": card_previews(self.store, match.group(1))})
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except requests.RequestException as exc:
            self.error(f"External image request failed: {exc}", HTTPStatus.BAD_GATEWAY)
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc))
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            payload = self._json()
            match = re.fullmatch(r"/api/recipes/([^/]+)", path)
            if match:
                recipe_id = match.group(1)
                def update(data: dict[str, Any]) -> dict[str, Any]:
                    current = _find_item(data, "recipes", recipe_id)
                    recipe = recipe_from_payload({**current, **payload, "created_at": current.get("created_at")}, recipe_id, now_iso())
                    known = {str(item["id"]) for item in data["references"]}
                    if any(item not in known for item in recipe["reference_ids"]):
                        raise ValueError("recipe contains an unknown style reference")
                    data["recipes"] = [recipe if item.get("id") == recipe_id else item for item in data["recipes"]]
                    return recipe
                self.store.mutate(update)
                self.send_json({"ok": True, "workspace": self.store.payload()})
                return
            match = re.fullmatch(r"/api/references/([^/]+)", path)
            if match:
                reference_id = match.group(1)
                def update_reference(data: dict[str, Any]) -> None:
                    reference = _find_item(data, "references", reference_id)
                    if "label" in payload:
                        reference["label"] = str(payload["label"]).strip()[:100] or reference["label"]
                    if "position" in payload:
                        references = sorted(data["references"], key=lambda item: int(item.get("position", 0)))
                        references.remove(reference)
                        target = max(0, min(int(payload["position"]), len(references)))
                        references.insert(target, reference)
                        for index, item in enumerate(references):
                            item["position"] = index
                        data["references"] = references
                self.store.mutate(update_reference)
                self.send_json({"ok": True, "workspace": self.store.payload()})
                return
            match = re.fullmatch(r"/api/cards/([^/]+)", path)
            if match:
                self.send_json({"ok": True, "card": update_card_draft(self.store, match.group(1), payload)})
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc))
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    do_PATCH = do_PUT

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            payload = self._json()
            match = re.fullmatch(r"/api/sources/([^/]+)", path)
            collection = "sources" if match else None
            if not collection:
                match = re.fullmatch(r"/api/references/([^/]+)", path)
                collection = "references" if match else None
            if not match or not collection:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            item_id = match.group(1)
            def remove(data: dict[str, Any]) -> dict[str, Any]:
                item = _find_item(data, collection, item_id)
                if not payload.get("confirm"):
                    raise ValueError("deletion needs explicit confirmation")
                if collection == "sources" and item_id in data.get("benchmark_source_ids", []):
                    raise ValueError("remove this image from the project selection before deleting it")
                if collection == "references" and any(item_id in recipe.get("reference_ids", []) for recipe in data.get("recipes", [])):
                    raise ValueError("remove this reference from recipes before deleting it")
                data[collection] = [candidate for candidate in data[collection] if candidate.get("id") != item_id]
                return item
            deleted = self.store.mutate(remove)
            self.store.absolute_path(deleted["relative_path"]).unlink(missing_ok=True)
            self.send_json({"ok": True, "workspace": self.store.payload()})
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc), HTTPStatus.CONFLICT if "before deleting" in str(exc) else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_asset(self, relative_path: str) -> None:
        try:
            path = self.store.absolute_path(relative_path)
        except WorkspaceError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_workbench_server(host: str = "127.0.0.1", port: int = 8765, library_dir: Path = Path("portrait-library")) -> None:
    store = WorkspaceStore(library_dir)
    _ensure_starter_recipe(store)
    manager = RunManager(store)
    handler = type("ConfiguredWorkbenchHandler", (WorkbenchHandler,), {"store": store, "manager": manager})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Portrait Workbench API: http://{host}:{port}")
    server.serve_forever()
