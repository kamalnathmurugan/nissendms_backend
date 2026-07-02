"""In-memory store for the stub backend.

Builds the folder tree from the declarative template, supports adding vessels
(which clones the per-ship sub-tree under all three main folders), and fakes the
upload + month-folder behaviour so the UI can be built against realistic data.
"""
import itertools
import re
from datetime import date

from . import template

class DuplicateFile(Exception):
    """Raised when a file with the same name already exists in the target folder."""


_ids = itertools.count(1)


def _new_id():
    return str(next(_ids))


class Store:
    def __init__(self):
        # Flat map: id -> node dict.
        self.nodes = {}
        # Ordered list of vessel ids.
        self.vessels = []
        # id -> job dict.
        self.jobs = {}
        self._job_ids = itertools.count(1)
        self._build_roots()

    # ------------------------------------------------------------------ build
    def _make_node(self, name, kind, parent_id, *, month_children=None, ext=None):
        node = {
            "id": _new_id(),
            "name": name,
            "kind": kind,
            "parent_id": parent_id,
            "children": [],
            "upload": kind in ("leaf", "month_driven"),
            "month_driven": kind == "month_driven",
        }
        if month_children is not None:
            node["month_children"] = month_children
        if ext is not None:
            node["ext"] = ext  # for file nodes
        self.nodes[node["id"]] = node
        if parent_id is not None:
            self.nodes[parent_id]["children"].append(node["id"])
        return node

    def _build_subtree(self, spec, parent_id):
        node = self._make_node(
            spec["name"],
            spec["kind"],
            parent_id,
            month_children=spec.get("month_children"),
        )
        for child in spec.get("children", []):
            self._build_subtree(child, node["id"])
        return node

    def _build_roots(self):
        self.roots = []
        self.main_folders = {}  # name -> node
        for name in template.MAIN_FOLDERS:
            main = self._make_node(name, "main", None)
            self.roots.append(main["id"])
            self.main_folders[name] = main
            # The "Common for all ships" branch lives once per main folder.
            self._build_subtree(template.COMMON_TEMPLATE[name], main["id"])

    # ----------------------------------------------------------------- vessels
    def add_vessel(self, name, imo=None):
        ship_folder_ids = {}
        for main_name, main in self.main_folders.items():
            ship = self._make_node(name, "ship", main["id"])
            ship["vessel"] = name
            for spec in template.SHIP_TEMPLATE[main_name]:
                self._build_subtree(spec, ship["id"])
            ship_folder_ids[main_name] = ship["id"]
        vessel = {
            "id": _new_id(),
            "name": name,
            "imo": imo,
            "ship_folders": ship_folder_ids,
        }
        self.vessels.append(vessel)
        # Pre-seed the current + next month folders to showcase scheduled creation.
        today = date.today()
        for ship_id in ship_folder_ids.values():
            for md in self._descendant_month_driven(ship_id):
                self.ensure_month_folder(md["id"], today.year, today.month)
                nm_year, nm_month = _next_month(today.year, today.month)
                self.ensure_month_folder(md["id"], nm_year, nm_month)
        return vessel

    def _descendant_month_driven(self, root_id):
        out = []
        stack = [root_id]
        while stack:
            nid = stack.pop()
            node = self.nodes[nid]
            if node["month_driven"]:
                out.append(node)
            stack.extend(node["children"])
        return out

    # ----------------------------------------------------------------- folders
    def get_node(self, node_id):
        return self.nodes.get(node_id)

    def serialize(self, node, depth=1):
        """Return a node with `depth` levels of nested children (depth<0 = all)."""
        out = {
            "id": node["id"],
            "name": node["name"],
            "kind": node["kind"],
            "upload": node["upload"],
            "month_driven": node["month_driven"],
            "has_children": bool(node["children"]),
        }
        if "ext" in node:
            out["ext"] = node["ext"]
        if node["month_driven"]:
            out["categories"] = [c["name"] for c in node.get("month_children", [])]
        if depth != 0:
            out["children"] = [
                self.serialize(self.nodes[c], depth - 1) for c in node["children"]
            ]
        return out

    def tree(self):
        return [self.serialize(self.nodes[r], depth=-1) for r in self.roots]

    def children(self, node_id):
        node = self.nodes[node_id]
        return [self.serialize(self.nodes[c], depth=1) for c in node["children"]]

    # ------------------------------------------------------------ month folders
    def ensure_month_folder(self, month_driven_id, year, month):
        """Create `{Month YYYY}` (+ its category children) under a month_driven
        folder if absent; return the month folder node."""
        md = self.nodes[month_driven_id]
        label = f"{_MONTHS[month - 1]} {year}"
        for cid in md["children"]:
            if self.nodes[cid]["name"] == label:
                return self.nodes[cid]
        month_node = self._make_node(label, "month", md["id"])
        month_node["is_month"] = True
        for cat in md.get("month_children", []):
            self._build_subtree(cat, month_node["id"])
        return month_node

    # ----------------------------------------------------------------- uploads
    def _add_file(self, parent_id, filename, content=b"", content_type=""):
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        node = self._make_node(filename, "file", parent_id, ext=ext)
        node["content"] = content
        node["content_type"] = content_type or "application/octet-stream"
        node["size"] = len(content)
        return node

    def _has_child_named(self, parent_id, name):
        return any(
            self.nodes[c]["name"].lower() == name.lower()
            for c in self.nodes[parent_id]["children"]
        )

    def _path_of(self, node_id):
        parts = []
        nid = node_id
        while nid is not None:
            n = self.nodes[nid]
            parts.append(n["name"])
            nid = n["parent_id"]
        return " / ".join(reversed(parts))

    def upload(self, folder_id, filename, content=b"", content_type=""):
        """Plain leaf upload — place the file directly in the folder."""
        if self._has_child_named(folder_id, filename):
            raise DuplicateFile(filename)
        self._add_file(folder_id, filename, content, content_type)
        path = self._path_of(folder_id)
        return self._make_job(filename, "done", path, detected_month=None)

    def month_upload(
        self, month_driven_id, filename, category=None, content=b"", content_type=""
    ):
        """Special upload: fake OCR month detection, ensure the month folder,
        then file the doc into the chosen category (or `To be Classified`)."""
        year, month = _detect_month(filename)
        md = self.nodes[month_driven_id]
        if year is None:
            # No confident date -> month-agnostic "To be Classified".
            target = self._ensure_unclassified(md)
            detected = None
        else:
            month_node = self.ensure_month_folder(month_driven_id, year, month)
            target = month_node
            cat_name = category or "To be Classified"
            for cid in month_node["children"]:
                if self.nodes[cid]["name"] == cat_name:
                    target = self.nodes[cid]
                    break
            detected = f"{_MONTHS[month - 1]} {year}"
        if self._has_child_named(target["id"], filename):
            raise DuplicateFile(filename)
        self._add_file(target["id"], filename, content, content_type)
        return self._make_job(
            filename, "done", self._path_of(target["id"]), detected_month=detected
        )

    # ----------------------------------------------------------- files / search
    def get_file(self, node_id):
        node = self.nodes.get(node_id)
        if not node or node["kind"] != "file":
            return None
        return node["content"], node["content_type"], node["name"]

    def delete_file(self, node_id):
        node = self.nodes.get(node_id)
        if not node or node["kind"] != "file":
            return False
        pid = node["parent_id"]
        if pid is not None and node_id in self.nodes[pid]["children"]:
            self.nodes[pid]["children"].remove(node_id)
        self.nodes.pop(node_id, None)
        return True

    def search(self, query):
        ql = query.lower().strip()
        if not ql:
            return []
        results = []

        def walk(nid, trail):
            node = self.nodes[nid]
            t2 = trail + [{"id": nid, "name": node["name"]}]
            if node["kind"] != "main" and ql in node["name"].lower():
                results.append(
                    {
                        "id": nid,
                        "name": node["name"],
                        "kind": node["kind"],
                        "trail": t2,
                        "path": self._path_of(nid),
                    }
                )
            for c in node["children"]:
                walk(c, t2)

        for r in self.roots:
            walk(r, [])
        return results[:50]

    def _ensure_unclassified(self, md):
        for cid in md["children"]:
            if self.nodes[cid]["name"] == "To be Classified":
                return self.nodes[cid]
        return self._make_node("To be Classified", "leaf", md["id"])

    # -------------------------------------------------------------------- jobs
    def _make_job(self, filename, status, dest_path, detected_month):
        job = {
            "id": str(next(self._job_ids)),
            "filename": filename,
            "status": "processing",  # flips to `status` after first poll
            "final_status": status,
            "destination": dest_path,
            "detected_month": detected_month,
            "polls": 0,
        }
        self.jobs[job["id"]] = job
        return self.public_job(job)

    def get_job(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            return None
        # Simulate async processing: first poll still "processing", then done.
        job["polls"] += 1
        if job["polls"] >= 2:
            job["status"] = job["final_status"]
        return self.public_job(job)

    @staticmethod
    def public_job(job):
        return {
            "id": job["id"],
            "filename": job["filename"],
            "status": job["status"],
            "destination": job["destination"],
            "detected_month": job["detected_month"],
        }


# --------------------------------------------------------------------- helpers
_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTH_LOOKUP = {m.lower(): i + 1 for i, m in enumerate(_MONTHS)}
_MONTH_LOOKUP.update({m[:3].lower(): i + 1 for i, m in enumerate(_MONTHS)})


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _detect_month(filename):
    """Fake the PaddleOCR step by parsing a month/year out of the filename.

    Recognises `2026-07`, `2026_07`, `07-2026`, and month names (`July 2026`,
    `Jul-2026`). Returns (year, month) or (None, None)."""
    name = filename.lower()
    m = re.search(r"(20\d{2})[-_.](0[1-9]|1[0-2])", name)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(0[1-9]|1[0-2])[-_.](20\d{2})", name)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_ ]?(20\d{2})", name)
    if m:
        return int(m.group(2)), _MONTH_LOOKUP[m.group(1)]
    return None, None


store = Store()
