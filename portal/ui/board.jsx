import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { flushSync, createPortal } from "react-dom";
import {
  MantineProvider,
  createTheme,
  ActionIcon,
  Avatar,
  Badge,
  Button,
  Checkbox,
  Drawer,
  Group,
  Stack,
  Text,
  Textarea,
  TextInput,
  NativeSelect,
  NumberInput,
  Paper,
  Progress,
  SimpleGrid,
  Alert,
  Anchor,
  Divider,
  Accordion,
  Loader,
  Modal,
} from "@mantine/core";
import "./board.css";

const board = document.getElementById("kanban");
const types = {
  task: ["Aufgabe", "list-check", "blue"],
  checklist: ["Checkliste", "square-check", "teal"],
  idea: ["Idee", "lightbulb", "orange"],
  note: ["Notiz", "note-sticky", "gray"],
  decision: ["Entscheidung", "scale-balanced", "grape"],
  milestone: ["Meilenstein", "flag", "pink"],
};
const quickDrafts = new Map(),
  drafts = new Map();
let uiRoot;
let editor,
  inspector,
  editingId = null;
const icon = (name) => (
  <i className={`fa-solid fa-${name}`} aria-hidden="true" />
);
const options = (object) =>
  Object.entries(object).map(([value, label]) => ({ value, label }));
const theme = createTheme({
  fontFamily: getComputedStyle(document.body).fontFamily,
  primaryColor: "blue",
  defaultRadius: "md",
  fontSizes: { sm: ".8125rem", md: ".875rem" },
  components: {
    Button: { defaultProps: { size: "sm" } },
    TextInput: { defaultProps: { size: "sm" } },
    Textarea: { defaultProps: { size: "sm" } },
    NativeSelect: { defaultProps: { size: "sm" } },
  },
});
function Provider({ children }) {
  const [scheme, setScheme] = useState(
    document.documentElement.dataset.bsTheme || "light",
  );
  useEffect(() => {
    const observer = new MutationObserver(() =>
      setScheme(document.documentElement.dataset.bsTheme || "light"),
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-bs-theme"],
    });
    return () => observer.disconnect();
  }, []);
  return (
    <MantineProvider
      theme={theme}
      forceColorScheme={scheme}
      cssVariablesSelector="#kanban"
      withGlobalClasses={false}
    >
      {children}
    </MantineProvider>
  );
}
// HTML comes exclusively from tasks.markdown with raw HTML disabled.
function Markdown({ html }) {
  return (
    <div className="kb-markdown" dangerouslySetInnerHTML={{ __html: html }} />
  );
}
function Card({ card: c }) {
  const [editing, setEditing] = useState(quickDrafts.has(c.id)),
    [title, setTitle] = useState(quickDrafts.get(c.id) ?? c.title),
    [saving, setSaving] = useState(false),
    [error, setError] = useState("");
  const canEdit = Number(board.dataset.level) >= 2,
    kind = types[c.type] || [c.type_label, "link", "blue"];
  const open = () => editor.open(c.id);
  const inspectBadge = (section, label, iconName, count) => (
    <Badge
      component="button"
      type="button"
      variant="light"
      size="xs"
      className="kb-inspect-badge"
      aria-label={`${label}${count !== undefined ? ": " + count : ""} · ${c.title}`}
      title={label}
      onClick={() => inspector.open(c.id, section)}
    >
      {icon(iconName)}
      {count !== undefined && <span>{count}</span>}
    </Badge>
  );
  async function submit(e) {
    e.preventDefault();
    e.stopPropagation();
    setSaving(true);
    setError("");
    const data = new FormData();
    Object.entries({
      action: "edit",
      card: c.id,
      version: c.version,
      title,
      quick_title: "1",
    }).forEach(([k, v]) => data.set(k, v));
    const ok = await window.TaskBoardActions.save(data);
    if (ok !== true) {
      setError(
        ok === null
          ? "Speicherergebnis unklar. Bitte zuerst den aktuellen Stand prüfen."
          : "Titel konnte nicht gespeichert werden. Bitte die Meldung oben prüfen.",
      );
      setSaving(false);
    }
  }
  function cancel() {
    quickDrafts.delete(c.id);
    editingId = null;
    setTitle(c.title);
    setEditing(false);
    setError("");
    requestAnimationFrame(() =>
      document.getElementById(`kb-title-${c.id}`)?.focus(),
    );
  }
  return (
    <div
      className="kb-compact"
      onClick={(e) => {
        if (!e.target.closest("button,a,input,textarea,form")) open();
      }}
    >
      {c.cover && (
        <div
          className={`kb-cover kb-cover-${c.cover}`}
          aria-label={`Kartenfarbe: ${c.cover}`}
        />
      )}
      <div className="kb-card-top">
        <Badge
          variant="light"
          color={kind[2]}
          size="xs"
          leftSection={icon(kind[1])}
        >
          {kind[0]}
        </Badge>
        <ActionIcon
          className="kb-pencil"
          variant="subtle"
          color="gray"
          size={28}
          aria-label={`${canEdit ? "Karte bearbeiten" : "Kartendetails"}: ${c.title}`}
          title={canEdit ? "Alle Details bearbeiten" : "Details ansehen"}
          onClick={open}
        >
          {icon(canEdit ? "pencil" : "eye")}
        </ActionIcon>
      </div>
      {editing ? (
        <form
          className="kb-quick-form"
          onSubmit={submit}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              cancel();
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.requestSubmit();
            }
          }}
        >
          <Textarea
            autoFocus
            autosize
            minRows={2}
            maxRows={5}
            label="Titel schnell bearbeiten"
            value={title}
            onChange={(e) => {
              setTitle(e.currentTarget.value);
              quickDrafts.set(c.id, e.currentTarget.value);
            }}
            maxLength={300}
            required
            disabled={saving}
          />
          <Group gap="xs" mt="xs">
            <Button type="submit" size="compact-xs" loading={saving}>
              Speichern
            </Button>
            <Button
              variant="subtle"
              color="gray"
              size="compact-xs"
              onClick={cancel}
              disabled={saving}
            >
              Abbrechen
            </Button>
          </Group>
          {error && (
            <Text c="red" size="xs" role="alert" mt="xs">
              {error}
            </Text>
          )}
        </form>
      ) : (
        <button
          id={`kb-title-${c.id}`}
          type="button"
          className="kb-card-title"
          title={`${c.title} · ${c.native && canEdit ? "Titel direkt bearbeiten" : "Kartendetails öffnen"}`}
          onClick={() => {
            if (c.native && canEdit) {
              if (editingId && editingId !== c.id) {
                window.TaskBoardActions.error(
                  "Bitte den geöffneten Titel zuerst speichern oder abbrechen.",
                );
                return;
              }
              editingId = c.id;
              quickDrafts.set(c.id, c.title);
              setEditing(true);
            } else open();
          }}
        >
          {c.title}
        </button>
      )}
      {c.native && c.tags.length > 0 && (
        <div className="kb-labels">
          {c.tags.slice(0, 3).map((tag) => (
            <Badge
              key={tag}
              variant="light"
              size="xs"
              color={kind[2]}
              title={tag}
            >
              {tag}
            </Badge>
          ))}
          {c.tags.length > 3 && (
            <Text size="xs" c="dimmed">
              +{c.tags.length - 3}
            </Text>
          )}
        </div>
      )}
      <div className="kb-card-footer">
        <span
          className="kb-status-dot"
          data-status={c.status}
          title={c.status_label}
        >
          <span />
          {c.status_label}
        </span>
        {c.native && c.priority !== "normal" && c.priority !== "low" && (
          <span
            className={`kb-priority-mark kb-priority-${c.priority}`}
            title={c.priority_label}
          >
            {icon("flag")}
          </span>
        )}
        {c.due && (
          <span
            className={c.overdue ? "kb-due-overdue" : "kb-due"}
            title={c.overdue ? "Überfällig" : "Fällig am"}
          >
            {icon("clock")} {c.due}
          </span>
        )}
        {c.description &&
          inspectBadge("description", "Beschreibung", "align-left")}
        {!!c.checks &&
          inspectBadge(
            "checks",
            "Checkliste",
            "square-check",
            `${c.checked}/${c.checks}`,
          )}
        {!!c.comments &&
          inspectBadge("comments", "Kommentare", "comment", c.comments)}
        {!!c.files && inspectBadge("files", "Anhänge", "paperclip", c.files)}
        {c.responsible && (
          <Avatar
            size={22}
            radius="xl"
            color="blue"
            className="kb-card-avatar"
            title={c.responsible}
            aria-label={`Verantwortlich: ${c.responsible}`}
          >
            {c.responsible
              .split(" ")
              .map((x) => x[0])
              .slice(0, 2)
              .join("")}
          </Avatar>
        )}
      </div>
    </div>
  );
}
function Editor() {
  const [opened, setOpened] = useState(false),
    [data, setData] = useState(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [draft, setDraft] = useState({});
  let id = data?.card.id;
  useEffect(() => {
    let sequence = 0,
      active = null;
    editor = {
      isOpen: () => active !== null,
      open: async (cardId, refresh = false) => {
        if (editingId) {
          window.TaskBoardActions.error(
            "Bitte den geöffneten Titel zuerst speichern oder abbrechen.",
          );
          return;
        }
        const seq = ++sequence;
        active = cardId;
        if (!refresh) setData(null);
        setError("");
        setOpened(true);
        if (!refresh) setLoading(true);
        try {
          const response = await fetch(
            `/tasks/boards/${board.dataset.board}/cards/${cardId}`,
            {
              credentials: "same-origin",
              headers: { Accept: "application/json" },
            },
          );
          if (!response.ok || response.redirected)
            throw Error(
              "Die Karte ist nicht mehr zugänglich. Bitte das Board aktualisieren.",
            );
          const next = await response.json();
          if (seq !== sequence) return;
          setData(next);
          setDraft(drafts.get(cardId) || {});
        } catch (e) {
          if (seq === sequence) setError(e.message);
        } finally {
          if (seq === sequence) setLoading(false);
        }
      },
      close: () => {
        ++sequence;
        active = null;
        setOpened(false);
        setLoading(false);
      },
    };
    return () => {
      ++sequence;
      editor = null;
    };
  }, []);
  const update = (key, value) => {
    setDraft((previous) => {
      const next = { ...previous, [key]: value };
      drafts.set(id, next);
      return next;
    });
  };
  async function action(event, name, extra = {}) {
    event.preventDefault();
    event.stopPropagation();
    if (saving) return;
    setSaving(true);
    setError("");
    const form = event.currentTarget;
    const payload = new FormData(form);
    Object.entries({
      action: name,
      card: id,
      version: data.card.version,
      ...extra,
    }).forEach(([k, v]) => payload.set(k, v));
    if (name === "edit") {
      // Keep closed accordion fields and the original workflow settings intact.
      Object.entries(values).forEach(([key, value]) =>
        payload.set(key, value ?? ""),
      );
      payload.set("card_type", values.card_type ?? data.card.type);
      payload.set("cover_color", values.cover_color ?? data.card.cover);
      payload.set("version", draft.editVersion ?? data.card.version);
    }
    const ok = await window.TaskBoardActions.save(payload);
    if (ok === true) {
      const next = { ...draft };
      if (name === "edit") {
        delete next.values;
        delete next.editVersion;
      }
      if (name === "comment") delete next.comment;
      if (name === "check_add") delete next.check_title;
      if (name === "status") delete next.reason;
      drafts.set(id, next);
      if (name === "remove") editor.close();
      else await editor.open(id, true);
    } else
      setError(
        ok === null
          ? "Das Speicherergebnis ist unklar. Ihre Eingaben bleiben erhalten. Prüfen Sie vor erneutem Speichern den aktuellen Stand."
          : "Die Änderung wurde nicht gespeichert. Ihre Eingaben bleiben erhalten. Prüfen Sie die Meldung im Board.",
      );
    setSaving(false);
  }
  const values = draft.values || data?.values || {};
  const change = (key, value) => {
    const next = {
      ...draft,
      editVersion: draft.editVersion ?? data.card.version,
      values: { ...values, [key]: value },
    };
    drafts.set(id, next);
    setDraft(next);
  };
  const write = Number(board.dataset.level) >= 2 && data?.level >= 2;
  const form = (name, children, extra = {}) => (
    <form onSubmit={(e) => action(e, name, extra)}>
      <fieldset disabled={saving} className="kb-editor-fieldset">
        {children}
      </fieldset>
    </form>
  );
  return (
    <Drawer
      opened={opened}
      onClose={() => {
        if (!saving) editor.close();
      }}
      closeOnEscape={!saving}
      closeOnClickOutside={!saving}
      position="bottom"
      size="min(88dvh, 960px)"
      withinPortal={false}
      zIndex={1200}
      title={
        <div>
          <Text size="xs" c="dimmed" fw={600}>
            AUFGABENBOARD · KARTENDETAILS
          </Text>
          <Text fw={700}>{data?.card.title || "Karte öffnen"}</Text>
        </div>
      }
      closeButtonProps={{
        "aria-label": "Kartendetails schließen",
        disabled: saving,
      }}
      classNames={{
        inner: "kb-overlay-inner",
        content: "kb-sheet",
        header: "kb-sheet-header",
        body: "kb-sheet-body",
      }}
      transitionProps={{
        duration: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 0
          : 220,
      }}
    >
      {loading && (
        <Group justify="center" p="xl" role="status">
          <Loader size="sm" />
          <Text>Kartendetails werden geladen …</Text>
        </Group>
      )}
      {error && (
        <Alert color="red" role="alert" mb="md">
          {error}
        </Alert>
      )}
      {data && !loading && (
        <div className="kb-editor-grid">
          <Stack gap="lg">
            <Group justify="space-between">
              <Badge variant="light">
                {data.card.native
                  ? types[data.card.type]?.[0]
                  : data.card.type_label}
              </Badge>
              <Anchor href={data.href || data.card.href} size="sm">
                Original öffnen {icon("arrow-up-right-from-square")}
              </Anchor>
            </Group>
            {data.card.native ? (
              write ? (
                form(
                  "edit",
                  <Stack gap="md">
                    <TextInput
                      label="Titel"
                      id="drawer-title"
                      name="title"
                      value={values.title}
                      onChange={(e) => change("title", e.currentTarget.value)}
                      required
                      maxLength={300}
                    />
                    <Textarea
                      label="Beschreibung"
                      description="Markdown wird unterstützt"
                      id="drawer-description"
                      name="description"
                      value={values.description}
                      onChange={(e) =>
                        change("description", e.currentTarget.value)
                      }
                      autosize
                      minRows={4}
                      maxRows={12}
                    />
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      <NativeSelect
                        label="Kartentyp"
                        name="card_type"
                        value={values.card_type ?? data.card.type}
                        data={options(data.types)}
                        onChange={(e) =>
                          change("card_type", e.currentTarget.value)
                        }
                      />
                      <NativeSelect
                        label="Farbstreifen"
                        name="cover_color"
                        value={values.cover_color ?? data.card.cover}
                        data={options(data.colors)}
                        onChange={(e) =>
                          change("cover_color", e.currentTarget.value)
                        }
                      />
                    </SimpleGrid>
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      <NativeSelect
                        label="Verantwortlich"
                        id="drawer-assignee"
                        name="assignee_id"
                        value={values.assignee_id}
                        data={[
                          { value: "", label: "Externe Person" },
                          ...data.people,
                        ]}
                        onChange={(e) =>
                          change("assignee_id", e.currentTarget.value)
                        }
                      />
                      <NativeSelect
                        label="Priorität"
                        id="drawer-priority"
                        name="priority"
                        value={values.priority}
                        data={options(data.priorities)}
                        onChange={(e) =>
                          change("priority", e.currentTarget.value)
                        }
                      />
                      <TextInput
                        label="Fällig am"
                        id="drawer-due"
                        name="due_date"
                        type="date"
                        value={values.due_date}
                        onChange={(e) =>
                          change("due_date", e.currentTarget.value)
                        }
                      />
                      <TextInput
                        label="Uhrzeit (optional)"
                        id="drawer-time"
                        name="due_time"
                        type="time"
                        value={values.due_time}
                        onChange={(e) =>
                          change("due_time", e.currentTarget.value)
                        }
                      />
                    </SimpleGrid>
                    <Accordion variant="contained">
                      <Accordion.Item value="external">
                        <Accordion.Control>
                          Externe Zuständigkeit
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Stack gap="sm">
                            <input
                              type="hidden"
                              name="external"
                              value={values.external || "0"}
                            />
                            <Checkbox
                              label="Externe Person zuweisen"
                              checked={values.external === "1"}
                              onChange={(e) =>
                                change(
                                  "external",
                                  e.currentTarget.checked ? "1" : "0",
                                )
                              }
                            />
                            <TextInput
                              label="Name"
                              name="external_name"
                              value={values.external_name}
                              onChange={(e) =>
                                change("external_name", e.currentTarget.value)
                              }
                            />
                            <TextInput
                              label="E-Mail"
                              name="external_email"
                              type="email"
                              value={values.external_email}
                              onChange={(e) =>
                                change("external_email", e.currentTarget.value)
                              }
                            />
                          </Stack>
                        </Accordion.Panel>
                      </Accordion.Item>
                    </Accordion>
                    <TextInput
                      label="Labels"
                      description="Mit Komma trennen"
                      id="drawer-tags"
                      name="tags"
                      value={values.tags}
                      onChange={(e) => change("tags", e.currentTarget.value)}
                    />
                    <Group>
                      <Button type="submit" loading={saving}>
                        Änderungen speichern
                      </Button>
                      {draft.values && (
                        <Button
                          variant="subtle"
                          color="gray"
                          onClick={() => {
                            const next = { ...draft };
                            delete next.values;
                            delete next.editVersion;
                            drafts.set(id, next);
                            editor.open(id);
                          }}
                        >
                          Entwurf verwerfen
                        </Button>
                      )}
                    </Group>
                  </Stack>,
                )
              ) : (
                <Paper withBorder p="md">
                  <Text fw={600}>{data.card.title}</Text>
                  <Text style={{ whiteSpace: "pre-wrap" }} mt="md">
                    {data.values.description || "Keine Beschreibung."}
                  </Text>
                </Paper>
              )
            ) : (
              <Paper withBorder p="md">
                <Text fw={600}>{data.card.type_label}</Text>
                <Text mt="xs">{data.source}</Text>
                <Badge mt="md" variant="light">
                  {data.card.status_label}
                </Badge>
                <Text size="sm" c="dimmed" mt="md">
                  Dieser Inhalt bleibt mit seinem Fachmodul verknüpft.
                  Änderungen nehmen Sie im Original vor.
                </Text>
              </Paper>
            )}
            {data.card.native && (
              <>
                <Divider />
                <section aria-label="Checkliste">
                  <Text component="h3" size="md" fw={650}>
                    Checkliste{" "}
                    {data.checks.length
                      ? `· ${data.checks.filter((c) => c.done).length}/${data.checks.length}`
                      : ""}
                  </Text>
                  {!!data.checks.length && (
                    <Progress
                      size={4}
                      value={
                        (data.checks.filter((c) => c.done).length /
                          data.checks.length) *
                        100
                      }
                      my="sm"
                    />
                  )}
                  <Stack gap="xs">
                    {data.checks.map((check) => (
                      <Group
                        key={check.id}
                        justify="space-between"
                        wrap="nowrap"
                      >
                        {form(
                          "check",
                          <Checkbox
                            label={check.title}
                            checked={check.done}
                            disabled={
                              !write ||
                              ["done", "cancelled"].includes(data.card.status)
                            }
                            onChange={(e) =>
                              e.currentTarget.form.requestSubmit()
                            }
                          />,
                          { check: check.id },
                        )}
                        {write &&
                          form(
                            "check_remove",
                            <ActionIcon
                              variant="subtle"
                              color="gray"
                              type="submit"
                              aria-label={`Checklistenpunkt entfernen: ${check.title}`}
                            >
                              {icon("xmark")}
                            </ActionIcon>,
                            { check: check.id },
                          )}
                      </Group>
                    ))}
                    {!data.checks.length && (
                      <Text c="dimmed" size="sm">
                        Noch keine Checklistenpunkte.
                      </Text>
                    )}
                  </Stack>
                  {write &&
                    form(
                      "check_add",
                      <Group mt="md" align="end" wrap="nowrap">
                        <TextInput
                          label="Neuer Checklistenpunkt"
                          id="drawer-check"
                          name="check_title"
                          value={draft.check_title || ""}
                          onChange={(e) =>
                            update("check_title", e.currentTarget.value)
                          }
                          required
                          maxLength={500}
                          style={{ flex: 1 }}
                        />
                        <Button type="submit" variant="light">
                          Hinzufügen
                        </Button>
                      </Group>,
                    )}
                </section>
                <Divider />
                <section>
                  <Text component="h3" size="md" fw={650}>
                    Kommentare
                  </Text>
                  <Stack gap="sm">
                    {data.comments.map((comment, index) => (
                      <Paper key={index} withBorder p="sm">
                        <Text size="xs" c="dimmed">
                          {comment.author} · {comment.date}
                        </Text>
                        <Markdown html={comment.html} />
                      </Paper>
                    ))}
                    {!data.comments.length && (
                      <Text size="sm" c="dimmed">
                        Noch keine Kommentare.
                      </Text>
                    )}
                  </Stack>
                  {write &&
                    form(
                      "comment",
                      <Stack gap="sm" mt="md">
                        <Textarea
                          label="Kommentar schreiben"
                          id="drawer-comment"
                          name="comment"
                          value={draft.comment || ""}
                          onChange={(e) =>
                            update("comment", e.currentTarget.value)
                          }
                          autosize
                          minRows={2}
                          required
                          maxLength={10000}
                        />
                        <Button
                          type="submit"
                          variant="light"
                          style={{ alignSelf: "start" }}
                        >
                          Kommentieren
                        </Button>
                      </Stack>,
                    )}
                </section>
              </>
            )}
          </Stack>
          <Stack gap="lg" className="kb-editor-aside">
            <Paper withBorder p="md" radius="lg">
              <Text fw={650} size="sm" mb="sm">
                Organisation
              </Text>
              {data.card.native &&
                (write ? (
                  form(
                    "status",
                    <Stack gap="sm">
                      <NativeSelect
                        label="Aufgabenstatus"
                        id="drawer-status"
                        name="status"
                        data={options({
                          [data.card.status]: data.card.status_label,
                          ...data.statuses,
                        })}
                      />
                      <TextInput
                        label="Kommentar zur Statusänderung"
                        description="Bei Rückgabe erforderlich"
                        name="comment"
                        value={draft.reason || ""}
                        onChange={(e) =>
                          update("reason", e.currentTarget.value)
                        }
                      />
                      <Button variant="light" type="submit">
                        Status ändern
                      </Button>
                    </Stack>,
                  )
                ) : (
                  <Text size="sm">
                    {data.card.status_label} · {data.card.responsible}
                  </Text>
                ))}
              {write && (
                <>
                  <Divider my="md" />
                  {form(
                    "move",
                    <Stack gap="sm">
                      <NativeSelect
                        label="Verschieben nach"
                        name="column"
                        data={data.columns}
                        defaultValue={data.card.column}
                      />
                      <NumberInput
                        label="Position (ab 0)"
                        name="position"
                        defaultValue={0}
                        min={0}
                        allowDecimal={false}
                      />
                      <Button type="submit" variant="light">
                        Verschieben
                      </Button>
                    </Stack>,
                  )}
                </>
              )}
            </Paper>
            {data.card.native && (
              <Paper withBorder p="md" radius="lg">
                <Text component="h3" fw={650} size="sm">
                  Dateien
                </Text>
                <Stack gap="xs" my="sm">
                  {data.files.map((file) => (
                    <Anchor
                      key={file.id}
                      size="sm"
                      href={`${data.href}/dateien/${file.id}`}
                    >
                      {icon("paperclip")} {file.name}
                    </Anchor>
                  ))}
                  {!data.files.length && (
                    <Text size="sm" c="dimmed">
                      Keine Anhänge.
                    </Text>
                  )}
                </Stack>
                {write &&
                  form(
                    "upload",
                    <Stack gap="sm">
                      <TextInput
                        label="Dateien hinzufügen"
                        id="drawer-files"
                        name="files"
                        type="file"
                        multiple
                        required
                      />
                      <Button type="submit" variant="light">
                        Dateien hochladen
                      </Button>
                    </Stack>,
                  )}
              </Paper>
            )}
            {data.card.native && (
              <Accordion variant="contained">
                <Accordion.Item value="activity">
                  <Accordion.Control>Aktivitätsverlauf</Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="sm">
                      {data.activity.map((a, i) => (
                        <div key={i}>
                          <Text size="xs" c="dimmed">
                            {a.actor} · {a.date}
                          </Text>
                          <Text size="sm">{a.text}</Text>
                        </div>
                      ))}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            )}
            {write &&
              form(
                "remove",
                <Button color="red" variant="subtle" type="submit" fullWidth>
                  Nur aus diesem Board entfernen
                </Button>,
              )}
          </Stack>
        </div>
      )}
    </Drawer>
  );
}

function Inspector() {
  const [opened, setOpened] = useState(false),
    [data, setData] = useState(null),
    [section, setSection] = useState("comments"),
    [error, setError] = useState("");
  useEffect(() => {
    let sequence = 0,
      active = false;
    inspector = {
      isOpen: () => active,
      open: async (id, kind) => {
        const seq = ++sequence;
        active = true;
        setData(null);
        setError("");
        setSection(kind);
        setOpened(true);
        try {
          const response = await fetch(
            `/tasks/boards/${board.dataset.board}/cards/${id}`,
            {
              credentials: "same-origin",
              headers: { Accept: "application/json" },
            },
          );
          if (!response.ok || response.redirected)
            throw Error(
              "Dieser Inhalt ist nicht mehr zugänglich. Bitte das Board aktualisieren.",
            );
          const next = await response.json();
          if (seq === sequence) setData(next);
        } catch (e) {
          if (seq === sequence) setError(e.message);
        }
      },
      close: () => {
        ++sequence;
        active = false;
        setOpened(false);
      },
    };
    return () => {
      ++sequence;
      inspector = null;
    };
  }, []);
  const headings = {
    comments: "Kommentare",
    files: "Anhänge",
    checks: "Checkliste",
    description: "Beschreibung",
  };
  return (
    <Modal
      opened={opened}
      onClose={() => inspector.close()}
      withinPortal={false}
      centered
      size="lg"
      zIndex={1250}
      title={
        <Text fw={650}>
          {headings[section]}
          {data ? ` · ${data.card.title}` : ""}
        </Text>
      }
      closeButtonProps={{ "aria-label": "Vorschau schließen" }}
      classNames={{
        inner: "kb-overlay-inner",
        content: "kb-inspect-modal",
        header: "kb-inspect-header",
      }}
    >
      {error ? (
        <Alert color="red" role="alert">
          {error}
        </Alert>
      ) : !data ? (
        <Group justify="center" p="xl" role="status">
          <Loader size="sm" />
          <Text>Inhalte werden geladen …</Text>
        </Group>
      ) : (
        <Stack gap="md">
          {section === "description" && (
            <Markdown
              html={data.description_html || "<p>Keine Beschreibung.</p>"}
            />
          )}
          {section === "comments" &&
            (data.comments?.length ? (
              data.comments.map((comment, i) => (
                <Paper key={i} withBorder p="md" radius="md">
                  <Group gap="sm" mb="xs">
                    <Avatar size="sm" radius="xl">
                      {comment.author[0]}
                    </Avatar>
                    <div>
                      <Text fw={600} size="sm">
                        {comment.author}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {comment.date}
                      </Text>
                    </div>
                  </Group>
                  <Markdown html={comment.html} />
                </Paper>
              ))
            ) : (
              <Text c="dimmed">Noch keine Kommentare.</Text>
            ))}
          {section === "files" &&
            (data.files?.length ? (
              data.files.map((file) => (
                <Paper key={file.id} withBorder p="md">
                  <Group gap="sm">
                    {icon("paperclip")}
                    <Anchor href={`${data.href}/dateien/${file.id}`} size="sm">
                      {file.name}
                    </Anchor>
                  </Group>
                </Paper>
              ))
            ) : (
              <Text c="dimmed">Keine Anhänge.</Text>
            ))}
          {section === "checks" && (
            <>
              <Text size="sm" c="dimmed">
                {data.checks?.filter((c) => c.done).length} von{" "}
                {data.checks?.length} erledigt
              </Text>
              <Progress
                size="sm"
                value={
                  data.checks?.length
                    ? (data.checks.filter((c) => c.done).length /
                        data.checks.length) *
                      100
                    : 0
                }
              />
              {data.checks?.map((check) => (
                <Group key={check.id} gap="sm">
                  <span aria-label={check.done ? "Erledigt" : "Offen"}>
                    {icon(check.done ? "square-check" : "square")}
                  </span>
                  <Text size="sm" td={check.done ? "line-through" : undefined}>
                    {check.title}
                  </Text>
                </Group>
              ))}
            </>
          )}
          <Divider />
          <Group justify="space-between">
            <Button
              variant="subtle"
              color="gray"
              onClick={() => inspector.close()}
            >
              Schließen
            </Button>
            <Button
              variant="light"
              leftSection={icon("pencil")}
              onClick={() => {
                const id = data.card.id;
                inspector.close();
                setTimeout(() => editor.open(id), 200);
              }}
            >
              Alle Kartendetails
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

// One provider and theme observer serve all cards, including large boards.
function renderCards(cards) {
  flushSync(() =>
    uiRoot.render(
      <Provider>
        {cards.map(({ node, card }) =>
          createPortal(<Card card={card} />, node, String(card.id)),
        )}
        <Editor key="editor" />
        <Inspector key="inspector" />
      </Provider>,
    ),
  );
}
function mountCards() {
  const cards = [...board.querySelectorAll("[data-kb-card-ui]")].map((node) => {
    const card = JSON.parse(node.dataset.cardJson);
    node.replaceChildren();
    return { node, card };
  });
  renderCards(cards);
}
if (board) {
  const host = document.createElement("div");
  host.id = "kb-mantine-editor";
  board.append(host);
  uiRoot = createRoot(host);
  window.TaskBoardUI = {
    mountCards,
    unmountCards: () => renderCards([]),
    isOpen: () => editor?.isOpen() || inspector?.isOpen(),
    hasQuickDraft: () => quickDrafts.size > 0,
    clearQuickDraft: (id) => {
      quickDrafts.delete(Number(id));
      editingId = null;
    },
  };
  mountCards();
}
