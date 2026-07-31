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

from tools.cards.pipeline import card_detail, create_card_draft, list_card_drafts, list_templates, update_card_draft

from .generation import FALLBACK_MODELS
from .pexels import is_plausible_portrait, search_pexels
from .recipes import STARTER_RECIPE, recipe_from_payload, resolve_recipe_instruction
from .runs import RunManager
from .workspace import WorkspaceError, WorkspaceStore, new_id, now_iso


_models_cache: tuple[list[dict[str, Any]], float] | None = None


def fetch_models() -> list[dict[str, Any]]:
    global _models_cache
    import time

    if _models_cache and time.time() - _models_cache[1] < 3600:
        return _models_cache[0]
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return FALLBACK_MODELS
    try:
        response = requests.get("https://openrouter.ai/api/v1/images/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        response.raise_for_status()
        models = []
        for item in response.json().get("data", []):
            params = item.get("supported_parameters") or {}
            refs = params.get("input_references") or {}
            if "input_references" not in params:
                continue
            models.append({
                "id": item.get("id"), "name": item.get("name") or item.get("id"), "description": item.get("description"),
                "max_input_references": refs.get("max", 0) if isinstance(refs, dict) else 0,
                "aspect_ratios": ["5:4", "4:3", "3:2"], "qualities": ["low", "medium", "high"],
                "supports_negative_prompt": "negative_prompt" in params, "supports_reference_roles": False,
            })
        if models:
            _models_cache = (models, time.time())
            return models
    except requests.RequestException:
        pass
    return FALLBACK_MODELS


def _workspace_response(store: WorkspaceStore, manager: RunManager) -> dict[str, Any]:
    _ensure_starter_recipe(store)
    return {"ok": True, "workspace": store.payload(), "runs": manager.list(), "cards": list_card_drafts(store), "models": fetch_models()}


def _ensure_starter_recipe(store: WorkspaceStore) -> None:
    data = store.read()
    if data.get("recipes"):
        return
    recipe = recipe_from_payload(STARTER_RECIPE, new_id("recipe"), now_iso())
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
                self.send_json({"ok": True, "models": fetch_models()})
                return
            if path == "/api/templates":
                self.send_json({"ok": True, "templates": list_templates()})
                return
            if path == "/api/runs":
                self.send_json({"ok": True, "runs": self.manager.list()})
                return
            if path == "/api/cards":
                include_discarded = parse_qs(parsed.query).get("include_discarded", ["false"])[0] == "true"
                self.send_json({"ok": True, "cards": list_card_drafts(self.store, include_discarded)})
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
                    for candidate in search_pexels(query, int(payload.get("count", 8)), "portrait")
                    if is_plausible_portrait(candidate)
                ]
                self.send_json({"ok": True, "results": results})
                return
            if path == "/api/sources/import":
                payload = self._json()
                candidate = dict(payload.get("candidate") or {})
                url = str(candidate.get("selected_image_url") or candidate.get("original_image_url") or "")
                if not url:
                    raise ValueError("Pexels result has no downloadable image")
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                record = self.store.add_image_record("source", str(candidate.get("photographer") or "Pexels source"), f"pexels-{candidate.get('pexels_photo_id', new_id('source'))}.jpg", response.content, response.headers.get("Content-Type"))
                def annotate(data: dict[str, Any]) -> None:
                    source = _find_item(data, "sources", record["id"])
                    source["provenance"] = {"kind": "pexels", "photo_id": candidate.get("pexels_photo_id"), "photographer": candidate.get("photographer"), "photographer_url": candidate.get("photographer_url"), "photo_page_url": candidate.get("photo_page_url"), "license_page": candidate.get("license_page"), "query": candidate.get("query"), "original_image_url": candidate.get("original_image_url")}
                self.store.mutate(annotate)
                self.send_json({"ok": True, "workspace": self.store.payload()})
                return
            if path == "/api/sources/upload" or path == "/api/references/upload":
                fields, filename, content, content_type = _parse_upload(self.rfile.read(int(self.headers.get("Content-Length", "0"))), self.headers.get("Content-Type", ""))
                kind = "source" if path.startswith("/api/sources") else "reference"
                record = self.store.add_image_record(kind, fields.get("label", ""), filename, content, content_type)
                self.send_json({"ok": True, "workspace": self.store.payload(), "record": record})
                return
            if path == "/api/benchmark":
                payload = self._json()
                requested = [str(item) for item in payload.get("source_ids", [])]
                def update(data: dict[str, Any]) -> None:
                    ids = {str(item["id"]) for item in data["sources"]}
                    if any(item not in ids for item in requested):
                        raise ValueError("benchmark contains an unknown source")
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
                run = self.manager.create(payload.get("recipe_id"), int(payload.get("outputs_per_source", 1)))
                self.send_json({"ok": True, "run": run})
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
                card = create_card_draft(self.store, str(payload.get("run_id") or ""), str(payload.get("run_item_id") or ""), str(payload.get("label") or "Experimental claimant"), str(payload.get("preset") or "bust"))
                self.send_json({"ok": True, "card": card})
                return
            match = re.fullmatch(r"/api/cards/([^/]+)/decision", path)
            if match:
                payload = self._json()
                self.send_json({"ok": True, "card": update_card_draft(self.store, match.group(1), {"decision": payload.get("decision")})})
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
                    raise ValueError("remove this source from the benchmark before deleting it")
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
