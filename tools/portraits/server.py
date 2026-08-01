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
from urllib.parse import unquote, urlparse

import requests

from tools.cards.style_pipeline import StyleStore

from .generation import DEFAULT_LIVE_MODEL_ID, fetch_model_catalogue, simulation_model, unavailable_live_model
from .pexels import STARTER_PHOTO_IDS, get_pexels_photo, has_pexels_api_key, is_plausible_portrait, search_pexels
from .production import CardProductionManager
from .workspace import WorkspaceError, WorkspaceStore, new_id


_models_cache: tuple[list[dict[str, Any]], float] | None = None


def fetch_models() -> list[dict[str, Any]]:
    global _models_cache
    import time
    if _models_cache and time.time() - _models_cache[1] < 3600:
        return _models_cache[0]
    if not os.environ.get("OPENROUTER_API_KEY"):
        return [simulation_model(), unavailable_live_model(DEFAULT_LIVE_MODEL_ID)]
    try:
        models = fetch_model_catalogue()
        if len(models) > 1:
            _models_cache = (models, time.time())
            return models
    except requests.RequestException:
        pass
    return [simulation_model(), unavailable_live_model(DEFAULT_LIVE_MODEL_ID)]


def _models_for_store(store: WorkspaceStore, styles: StyleStore) -> list[dict[str, Any]]:
    models = fetch_models()
    known = {str(item.get("id")) for item in models}
    stale = [str(styles.active().get("generation", {}).get("model_id"))]
    if styles.draft():
        stale.append(str(styles.draft().get("generation", {}).get("model_id")))
    return [*models, *(unavailable_live_model(model_id) for model_id in dict.fromkeys(stale) if model_id and model_id not in known)]


def _find_item(data: dict[str, Any], collection: str, item_id: str) -> dict[str, Any]:
    item = next((candidate for candidate in data.get(collection, []) if str(candidate.get("id")) == item_id), None)
    if not item:
        raise ValueError(f"unknown {collection[:-1]} {item_id}")
    return item


def _parse_upload(body: bytes, content_type: str) -> tuple[dict[str, str], str, bytes, str]:
    message = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body)
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


def _import_source(store: WorkspaceStore, candidate: dict[str, Any], include_in_selection: bool = True) -> dict[str, Any]:
    photo_id = candidate.get("pexels_photo_id")
    if photo_id is None:
        raise ValueError("Pexels result is missing its photo ID")
    existing = next((source for source in store.read().get("sources", []) if str((source.get("provenance") or {}).get("photo_id")) == str(photo_id)), None)
    if existing:
        if include_in_selection:
            store.mutate(lambda data: data["benchmark_source_ids"].append(existing["id"]) if existing["id"] not in data["benchmark_source_ids"] else None)
        return {"photo_id": photo_id, "status": "deduplicated", "source_id": existing["id"]}
    url = str(candidate.get("selected_image_url") or candidate.get("original_image_url") or "")
    if not url:
        raise ValueError("Pexels result has no downloadable image")
    response = requests.get(url, timeout=60); response.raise_for_status()
    record = store.add_image_record("source", str(candidate.get("photographer") or f"Pexels {photo_id}"), f"pexels-{photo_id or new_id('source')}.jpg", response.content, response.headers.get("Content-Type"))
    def annotate(data: dict[str, Any]) -> None:
        source = _find_item(data, "sources", str(record["id"]))
        source["provenance"] = {"kind": "pexels", "photo_id": photo_id, "photographer": candidate.get("photographer"), "photographer_url": candidate.get("photographer_url"), "photo_page_url": candidate.get("photo_page_url"), "license_page": candidate.get("license_page"), "query": candidate.get("query"), "original_image_url": candidate.get("original_image_url")}
        if include_in_selection and source["id"] not in data["benchmark_source_ids"]:
            data["benchmark_source_ids"].append(source["id"])
    store.mutate(annotate)
    return {"photo_id": photo_id, "status": "imported", "source_id": record["id"]}


def bulk_import_sources(store: WorkspaceStore, candidates: list[dict[str, Any]], include_in_selection: bool = True) -> dict[str, Any]:
    results = []
    for candidate in candidates:
        try:
            results.append(_import_source(store, dict(candidate), include_in_selection))
        except Exception as exc:
            results.append({"photo_id": candidate.get("pexels_photo_id"), "status": "failed", "error": str(exc)})
    return {"results": results, "imported": sum(item["status"] == "imported" for item in results), "deduplicated": sum(item["status"] == "deduplicated" for item in results), "failed": sum(item["status"] == "failed" for item in results)}


def _cards(manager: CardProductionManager) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for batch in manager.list():
        try:
            detail = manager.get(str(batch["batch_id"]))
        except ValueError:
            continue
        generation = detail.get("style_snapshot", {}).get("generation", {})
        live = generation.get("execution_mode") == "live"
        strategy = {
            "strategy_id": "interpretive-redraw" if live else "direct-render",
            "strategy_label": "Interpretive redraw" if live else "Direct render",
            "strategy_description": "Image-model redraw followed by Amiga rendering" if live else "Source-led deterministic rendering baseline",
        }
        for item in detail.get("items", []):
            if item.get("status") == "ready":
                identity = detail.get("style_snapshot", {}).get("identity", {})
                cards.append({
                    **item,
                    "batch_id": detail["batch_id"],
                    "batch_created_at": detail["created_at"],
                    "purpose": detail["purpose"],
                    "style_version_id": detail["style_version_id"],
                    "style_checksum_sha256": detail["style_checksum_sha256"],
                    "pipeline_label": identity.get("label") or detail["style_version_id"],
                    "pipeline_version": identity.get("version"),
                    **strategy,
                })
    return cards


def _bootstrap(store: WorkspaceStore, styles: StyleStore, manager: CardProductionManager) -> dict[str, Any]:
    styles.ensure_initial()
    workspace = store.payload()
    style = styles.bootstrap()
    return {
        "ok": True,
        "workspace": workspace,
        "sources": workspace["sources"],
        "selected_source_ids": list(workspace.get("benchmark_source_ids", [])),
        "style": style,
        "batches": manager.list(),
        "cards": _cards(manager),
        "models": _models_for_store(store, styles),
        "integrations": {"pexels": {"configured": has_pexels_api_key()}, "openrouter": {"configured": bool(os.environ.get("OPENROUTER_API_KEY"))}},
        "starter": {"photo_ids": list(STARTER_PHOTO_IDS)},
    }


class WorkbenchHandler(BaseHTTPRequestHandler):
    store: WorkspaceStore = WorkspaceStore()
    styles: StyleStore
    manager: CardProductionManager

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def _json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0")); raw = self.rfile.read(length)
        try:
            value = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, dict): raise ValueError("request body must be an object")
        return value

    def error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path in {"", "/api/workspace"}:
                self.send_json(_bootstrap(self.store, self.styles, self.manager)); return
            if path == "/api/models":
                self.send_json({"models": _models_for_store(self.store, self.styles)}); return
            if path == "/api/styles/bootstrap":
                self.send_json({"style": self.styles.bootstrap()}); return
            if path == "/api/production":
                self.send_json({"batches": self.manager.list()}); return
            match = re.fullmatch(r"/api/production/([^/]+)", path)
            if match:
                self.send_json({"batch": self.manager.get(match.group(1))}); return
            match = re.fullmatch(r"/api/cards/([^/]+)", path)
            if match:
                item_id = match.group(1)
                for batch in self.manager.list():
                    detail = self.manager.get(str(batch["batch_id"]))
                    item = next((candidate for candidate in detail.get("items", []) if candidate.get("item_id") == item_id), None)
                    if item:
                        self.send_json({"card": {**item, "batch_id": detail["batch_id"], "style_version_id": detail["style_version_id"], "style_checksum_sha256": detail["style_checksum_sha256"]}}); return
                raise ValueError(f"card {item_id} does not exist")
            if path.startswith("/asset/"):
                self.serve_asset(unquote(path.removeprefix("/asset/"))); return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc), HTTPStatus.NOT_FOUND if "does not exist" in str(exc) else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path == "/api/sources/search":
                payload = self._json(); query = str(payload.get("query") or "").strip()
                if not query: raise ValueError("search query is required")
                count, page = min(40, max(1, int(payload.get("count", 12)))), max(1, int(payload.get("page", 1)))
                results = [{**candidate, "preview_url": candidate.get("selected_image_url"), "provenance": {"kind": "pexels", "photographer": candidate.get("photographer"), "photo_page_url": candidate.get("photo_page_url"), "license_page": candidate.get("license_page")}} for candidate in search_pexels(query, count, "portrait", page=page, per_page=count) if is_plausible_portrait(candidate)]
                self.send_json({"results": results, "page": page, "has_more": len(results) == count}); return
            if path == "/api/sources/import":
                payload = self._json(); result = bulk_import_sources(self.store, [dict(payload.get("candidate") or {})], bool(payload.get("include_in_selection", True)))
                if result["failed"]: raise ValueError(result["results"][0]["error"])
                self.send_json({"workspace": self.store.payload(), **result}); return
            if path == "/api/sources/import-bulk":
                payload = self._json(); candidates = payload.get("candidates") or []
                if not isinstance(candidates, list) or not candidates: raise ValueError("select at least one search result to import")
                self.send_json({"workspace": self.store.payload(), **bulk_import_sources(self.store, [dict(item) for item in candidates], bool(payload.get("include_in_selection", True)))}); return
            if path == "/api/sources/starter":
                candidates, failures = [], []
                for photo_id in STARTER_PHOTO_IDS:
                    try: candidates.append(get_pexels_photo(photo_id))
                    except Exception as exc: failures.append({"photo_id": photo_id, "status": "failed", "error": str(exc)})
                result = bulk_import_sources(self.store, candidates, True); result["results"].extend(failures); result["failed"] += len(failures)
                self.send_json({"workspace": self.store.payload(), **result}); return
            if path == "/api/sources/upload":
                fields, filename, content, content_type = _parse_upload(self.rfile.read(int(self.headers.get("Content-Length", "0"))), self.headers.get("Content-Type", ""))
                record = self.store.add_image_record("source", fields.get("label", ""), filename, content, content_type)
                self.store.mutate(lambda data: data["benchmark_source_ids"].append(record["id"]) if record["id"] not in data["benchmark_source_ids"] else None)
                self.send_json({"workspace": self.store.payload(), "record": record}); return
            if path == "/api/sources/selection":
                payload = self._json(); requested = [str(item) for item in payload.get("source_ids", [])]; known = {str(item["id"]) for item in self.store.read().get("sources", [])}
                if len(requested) != len(set(requested)) or any(item not in known for item in requested): raise ValueError("source selection contains an unknown or duplicate image")
                self.store.mutate(lambda data: data.update({"benchmark_source_ids": requested})); self.send_json({"workspace": self.store.payload(), "selected_source_ids": requested}); return
            if path == "/api/production":
                payload = self._json(); style_id = str(payload.get("style_version_id") or self.styles.active_id()); style = self.styles.raw_version(style_id)
                if style_id != self.styles.active_id(): raise ValueError("normal card production must use the active locked style version")
                batch = self.manager.create([str(item) for item in payload.get("source_ids") or []], style, _models_for_store(self.store, self.styles), purpose="card-production", consent=bool(payload.get("consent")))
                self.send_json({"batch": batch}, HTTPStatus.ACCEPTED); return
            if path == "/api/styles/draft":
                self.send_json({"style": self.styles.create_or_resume_draft()}); return
            if path == "/api/styles/draft/references":
                _, filename, content, content_type = _parse_upload(self.rfile.read(int(self.headers.get("Content-Length", "0"))), self.headers.get("Content-Type", ""))
                self.send_json({"style": self.styles.add_draft_reference(filename.rsplit(".", 1)[0], filename, content, content_type)}); return
            if path == "/api/styles/draft/lock":
                self.send_json({"style": self.styles.lock_draft()}); return
            match = re.fullmatch(r"/api/production/([^/]+)/(retry|try-another|render|approve|bundle)", path)
            if match:
                batch_id, action = match.groups(); payload = self._json()
                if action == "retry": result = {"batch": self.manager.retry_failed(batch_id, consent=bool(payload.get("consent")))}
                elif action == "try-another": result = {"batch": self.manager.try_another(batch_id, str(payload.get("source_id") or ""), consent=bool(payload.get("consent")))}
                elif action == "render": result = {"batch": self.manager.rerender(batch_id, str(payload.get("item_id") or ""), dict(payload.get("framing") or {}))}
                elif action == "approve": result = {"approval": self.manager.approve(batch_id, str(payload.get("item_id") or ""))}
                else: result = self.manager.bundle(batch_id)
                self.send_json(result); return
            if path == "/api/styles/trials":
                payload = self._json(); draft = self.styles.draft()
                if not draft: raise ValueError("create a draft style before starting a trial")
                source_ids = [str(item) for item in payload.get("source_ids") or self.store.read().get("benchmark_source_ids", [])][:3]
                if not source_ids: raise ValueError("pin at least one calibration source")
                trial = self.manager.create(source_ids, self.styles.raw_draft() or {}, _models_for_store(self.store, self.styles), purpose="style-trial", consent=bool(payload.get("consent")))
                self.send_json({"batch": trial}, HTTPStatus.ACCEPTED); return
            match = re.fullmatch(r"/api/styles/trials/([^/]+)/activate", path)
            if match:
                trial = self.manager.get(match.group(1))
                if trial["purpose"] != "style-trial" or trial["status"] != "ready" or any(item.get("status") != "ready" for item in trial.get("items", [])): raise ValueError("only a complete style trial can be activated")
                if trial.get("model_capabilities", {}).get("execution_mode") != "live": raise ValueError("simulation trials are previews and cannot activate a production style")
                draft = self.styles.draft()
                if not draft or draft["checksums"]["style_sha256"] != trial["style_checksum_sha256"]: raise ValueError("the draft changed after this trial; run it again before activation")
                locked = self.styles.lock_draft(); self.styles.activate(locked["identity"]["style_version_id"]); self.send_json({"style": self.styles.bootstrap()}); return
            self.send_error(HTTPStatus.NOT_FOUND)
        except requests.RequestException as exc:
            self.error(f"External image request failed: {exc}", HTTPStatus.BAD_GATEWAY)
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc))
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path == "/api/styles/draft":
                self.send_json({"style": self.styles.update_draft(self._json())}); return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc))
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    do_PATCH = do_PUT

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            match = re.fullmatch(r"/api/sources/([^/]+)", path)
            if not match: self.send_error(HTTPStatus.NOT_FOUND); return
            source_id = match.group(1); payload = self._json()
            def remove(data: dict[str, Any]) -> dict[str, Any]:
                source = _find_item(data, "sources", source_id)
                if not payload.get("confirm"): raise ValueError("deletion needs explicit confirmation")
                if source_id in data.get("benchmark_source_ids", []): raise ValueError("remove this image from the selected sources before deleting it")
                data["sources"] = [item for item in data["sources"] if item.get("id") != source_id]; return source
            deleted = self.store.mutate(remove); self.store.absolute_path(deleted["relative_path"]).unlink(missing_ok=True); self.send_json({"workspace": self.store.payload()})
        except (ValueError, WorkspaceError) as exc:
            self.error(str(exc), HTTPStatus.CONFLICT if "before deleting" in str(exc) else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_asset(self, relative_path: str) -> None:
        try: path = self.store.absolute_path(relative_path)
        except WorkspaceError: self.send_error(HTTPStatus.BAD_REQUEST); return
        if not path.is_file(): self.send_error(HTTPStatus.NOT_FOUND); return
        data = path.read_bytes(); self.send_response(HTTPStatus.OK); self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_workbench_server(host: str = "127.0.0.1", port: int = 8765, library_dir: Path = Path("portrait-library")) -> None:
    store = WorkspaceStore(library_dir); styles = StyleStore(store); styles.ensure_initial(); manager = CardProductionManager(store, styles)
    handler = type("ConfiguredWorkbenchHandler", (WorkbenchHandler,), {"store": store, "styles": styles, "manager": manager})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Portrait Workbench API: http://{host}:{port}"); server.serve_forever()
