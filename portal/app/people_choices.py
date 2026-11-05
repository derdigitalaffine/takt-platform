"""Small presentation records for the shared, progressively enhanced selection UI."""


def users(people, *, targets=False, hints=None):
    hints = hints or {}
    return [
        dict(
            value=("user:" + str(p.id)) if targets else str(p.id),
            label=p.name,
            detail=" · ".join(v for v in (p.email, hints.get(p.id, "")) if v),
            kind="person",
            disabled=False,
        )
        for p in people
        if p.active
    ]


def groups(items):
    return [
        dict(
            value="group:" + str(g.id),
            label=g.name,
            detail="Gruppe · gilt für ihre Mitglieder",
            kind="group",
            disabled=False,
        )
        for g in items
    ]
