"""Declarative folder template — the single source of truth for the DMS hierarchy.

Node kinds
----------
- "leaf":         a final folder that exposes an upload button.
- "folder":       an intermediate container of children (no direct upload).
- "month_driven": special folder whose upload button lives at its root; uploads
                  are routed into auto-created `{Month YYYY}` sub-folders, each of
                  which contains the `month_children` categories.

The same template is consumed by the stub here and (in Phase B) by the real
SharePoint Embedded provisioner.
"""


def leaf(name):
    return {"name": name, "kind": "leaf"}


def folder(name, children):
    return {"name": name, "kind": "folder", "children": children}


def month_driven(name, month_children):
    return {"name": name, "kind": "month_driven", "month_children": month_children}


# The three top-level main folders.
MAIN_FOLDERS = [
    "Technical & Crewing",
    "Commercial & Chartering",
    "Insurance",
]

# ---------------------------------------------------------------------------
# Per-ship sub-tree for each main folder.
# ---------------------------------------------------------------------------
SHIP_TEMPLATE = {
    "Technical & Crewing": [
        month_driven(
            "Month End Reports",
            [
                leaf("Main Engine"),
                leaf("Aux Engine"),
                leaf("Cooling Water"),
                leaf("Inspection Reports"),
                leaf("Defect Reports"),
                leaf("Guarantee Claims"),
                leaf("To be Classified"),
            ],
        ),
        folder(
            "Service Agreements",
            [
                leaf("Technical Management"),
                leaf("Crew Management"),
                leaf("Vendor & Service Provider"),
                leaf("To be Classified"),
            ],
        ),
        folder(
            "Registration",
            [
                leaf("Flag & MPA"),
                leaf("Ship Builder"),
                leaf("Radio & Telecom"),
                leaf("Crewing & SMOU"),
                leaf("Novation"),
                leaf("To be Classified"),
            ],
        ),
        folder(
            "Drawings and Manuals",
            [leaf("Drawing"), leaf("Manual"), leaf("To be Classified")],
        ),
        folder("PO & Invoice", [leaf("Purchase Order"), leaf("Vendor Invoice")]),
        leaf("Incidents"),
        leaf("Crewing"),
        leaf("To be Classified"),
    ],
    "Commercial & Chartering": [
        folder(
            "Agreements",
            [
                leaf("Charter Party"),
                leaf("Pool Agreement"),
                leaf("Commission Agreement"),
                leaf("To be Classified"),
            ],
        ),
        month_driven(
            "Invoices & Payments",
            [leaf("Invoice"), leaf("Payments"), leaf("To be Classified")],
        ),
        month_driven(
            "Claims & Disputes",
            [leaf("Disputes"), leaf("Claims"), leaf("To be Classified")],
        ),
        leaf("To be Classified"),
    ],
    "Insurance": [
        leaf("P&I"),
        leaf("H&M"),
        leaf("War Risk"),
        leaf("Flag / MPA"),
        leaf("USA Related"),
    ],
}

# ---------------------------------------------------------------------------
# "Common for all ships" sub-tree for each main folder.
# ---------------------------------------------------------------------------
COMMON_TEMPLATE = {
    "Technical & Crewing": folder(
        "Common for all ships",
        [
            folder(
                "Vendor & Service Agreements",
                [leaf("Vendor & Service Provider Agreement"), leaf("To be Classified")],
            ),
            leaf("Vendor Management"),
            leaf("To be Classified"),
        ],
    ),
    "Commercial & Chartering": folder(
        "Common Agreements (Not Ship Specific)",
        [
            folder(
                "Agreements",
                [
                    leaf("Charter Party"),
                    leaf("Pool Agreement"),
                    leaf("Commission Agreement"),
                    leaf("To be Classified"),
                ],
            ),
            leaf("To be Classified"),
        ],
    ),
    "Insurance": folder(
        "Common (Not Ship Specific)",
        [leaf("Agreements"), leaf("Miscellaneous")],
    ),
}
