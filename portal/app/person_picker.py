"""Reusable surname-ordered, organization-aware presentation of portal users.

Only identities already included by a page's authorised controller are
annotated with organizational memberships. This prevents a directory API from
turning limited user pickers into an unrestricted employee search endpoint.
"""
import re
from collections.abc import Mapping
from sqlalchemy import select

from .db import Group, GroupMember, Organization, SessionLocal, User
from .org_models import OrgMembership

PERSON_KEYS = frozenset({
    "users", "people", "staff", "providers", "persons", "employees",
    "participants", "colleagues", "candidates", "teachers", "lecturers",
    "members", "assignees", "available_users", "person_options",
})


def surname_key(value):
    name = str(getattr(value, "name", value) or "").strip()
    name = re.sub(r"\s*<[^>]*>\s*$|\s*\([^)]*@[^)]*\)\s*$", "", name)
    if "," in name:
        last, first = name.split(",", 1)
    else:
        parts = name.split()
        last, first = (parts[-1], " ".join(parts[:-1])) if parts else ("", "")
    return (last.casefold(), first.casefold(), name.casefold(),
            getattr(value, "id", 0))


def sort_people(items):
    return sorted(items, key=surname_key)


def _collect(value):
    if isinstance(value, User):
        return [value]
    if isinstance(value, Mapping):
        return [v for v in value.values() if isinstance(v, User)]
    if isinstance(value, (tuple, list)):
        return [v for v in value if isinstance(v, User)]
    return []


def prepare_context(ctx):
    """Sort user lists for all shared render() templates without touching other lists."""
    ids = {}
    for key in PERSON_KEYS:
        if key not in ctx:
            continue
        value = ctx[key]
        users = _collect(value)
        if not users:
            continue
        for person in users:
            if person.active:
                ids[person.id] = person
        if isinstance(value, (list, tuple)) and len(users) == len(value):
            ctx[key] = sort_people(value)
        elif isinstance(value, dict) and len(users) == len(value):
            ctx[key] = dict(sorted(value.items(), key=lambda entry: surname_key(entry[1])))
    if not ids:
        return {"people": {}, "organizations": []}

    with SessionLocal() as db:
        memberships = list(db.execute(select(
            OrgMembership.user_id, OrgMembership.org_id
        ).where(OrgMembership.user_id.in_(list(ids)))).all())
        # Real TAKT groups are organizational nodes; annotate their users in
        # the existing smart picker without copying them into HR memberships.
        memberships.extend(db.execute(select(
            GroupMember.user_id, Group.org_id
        ).join(Group, GroupMember.group_id == Group.id).where(
            GroupMember.user_id.in_(list(ids)), Group.org_id.is_not(None)
        )).all())
        membership_map = {uid: [] for uid in ids}
        required = set()
        for uid, org_id in memberships:
            membership_map[uid].append(org_id)
            required.add(org_id)
        if not required:
            return {"people": {str(uid): {"orgs": []} for uid in ids}, "organizations": []}
        all_orgs = {o.id: o for o in db.scalars(select(Organization))}
        ancestors = {}
        for org_id in required:
            path = []
            current = org_id
            visited = set()
            while current and current in all_orgs and current not in visited:
                visited.add(current)
                path.append(current)
                current = all_orgs[current].parent_id
            ancestors[org_id] = list(reversed(path))
        used = {oid for path in ancestors.values() for oid in path}
        def org_path(org_id):
            path = []
            seen = set()
            while org_id and org_id in all_orgs and org_id not in seen:
                seen.add(org_id)
                path.append(all_orgs[org_id].name)
                org_id = all_orgs[org_id].parent_id
            return " / ".join(reversed(path))
        orgs = [
            {"id": org.id, "parent_id": org.parent_id if org.parent_id in used else None,
             "name": org.name, "path": org_path(org.id)}
            for org in all_orgs.values() if org.id in used and org.active
        ]
        # The information is limited to the persons actually passed to this template.
        people = {str(uid): {
            "orgs": sorted({ancestor for oid in membership_map[uid]
                             for ancestor in ancestors.get(oid, [])})
        } for uid in ids}
        return {"people": people, "organizations": sorted(
            orgs, key=lambda org: (org["path"].casefold(), org["id"]))}
