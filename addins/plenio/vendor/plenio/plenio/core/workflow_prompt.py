"""A workflow as ComfyUI's API prompt, without a browser (the Song API's runs, owner's request 2026-10-25).

ComfyUI's server runs an *API prompt* - ``{"<id>": {"class_type", "inputs", "_meta"}}`` - and leaves turning the
graph one sees into one to its frontend. A program that starts a template by itself has to do that work: this
module does it in plain Python, from the workflow file and the node definitions of the ComfyUI that runs it (what
``/object_info`` gives: the inputs in their order, which of them are widgets, a DynamicCombo's options).

What the frontend does, done the same way:

* **Widgets** - ``widgets_values`` holds one value per widget in the order the node definition makes them: its
  inputs (required, then optional) that are widgets, a seed control after a number that has one (saved, never
  sent), a DynamicCombo followed by the widgets of the option chosen (``vocals.language``). A widget input that is
  linked takes the link.
* **Subgraphs** - a node whose type is a subgraph's id is replaced by the subgraph's nodes, with ids
  ``<node>:<inner node>`` (deeper ones ``a:b:c``). An inner input linked to the subgraph's input takes what the
  subgraph node has there: its link, or the value of its widget (a promoted widget).
* **Modes** - a muted node (mode 2) is left out and so is what it gives; a bypassed node (mode 4) is left out and
  passes on the input of the type asked for (the input of the same slot when it has the type, else the first that
  has it); a bypassed subgraph node does the same for the subgraph as a whole.
* **Frontend nodes** - notes are skipped; a reroute passes its input on; a primitive node (the old kind) gives its
  value.

Pure Python: no ComfyUI import. ComfyUI's own code is not copied; the format is the workflow JSON.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

NodeInfo = Mapping[str, Any]
"""A node definition as ``/object_info`` gives it."""
InfoLookup = Callable[[str], NodeInfo | None]

ALWAYS, NEVER, BYPASS = 0, 2, 4
SUBGRAPH_INPUT, SUBGRAPH_OUTPUT = -10, -20
NOTE_TYPES = frozenset({"MarkdownNote", "Note"})
REROUTE = "Reroute"
PRIMITIVE = "PrimitiveNode"
"""The frontend's own primitive node (the old kind, widgets converted to inputs): its value goes into the input."""
DYNAMIC_COMBO = "COMFY_DYNAMICCOMBO_V3"
WIDGET_TYPES = frozenset({"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"})
CUSTOM_WIDGETS = frozenset({"PLENIO_SHEET_STATE", "PLENIO_FINISH_SWITCH"})
"""Input types the Plenio extension draws as widgets of its own (a value each, like a built-in widget)."""
CONTROL = "#control"
"""The key of a seed control's value (``seed#control``): saved with the workflow, not sent."""
SEED_LIMIT = 2**32
"""Seeds drawn here stay below 2^32, as the extension's (every sampler and model server takes them)."""


class WorkflowError(ValueError):
    """A workflow that cannot be turned into a prompt (a node type the server does not know, a broken link)."""


@dataclass(frozen=True)
class Widget:
    """One widget of a node: ``name`` is the input it sets (``vocals.language`` inside a DynamicCombo);
    ``control`` marks the seed control after a number (its key is ``name + CONTROL``)."""

    name: str
    spec_type: Any
    options: Mapping[str, Any]
    control: bool = False

    @property
    def key(self) -> str:
        return self.name + CONTROL if self.control else self.name


# --- widgets ------------------------------------------------------------------------------------------------


def _spec_of(inputs: Mapping[str, Any], name: str) -> tuple[Any, Mapping[str, Any]]:
    for section in ("required", "optional"):
        entry = (inputs.get(section) or {}).get(name)
        if entry is not None:
            entry = list(entry) if isinstance(entry, (list, tuple)) else [entry]
            options = entry[1] if len(entry) > 1 and isinstance(entry[1], Mapping) else {}
            return entry[0], options
    raise KeyError(name)


def _ordered(inputs: Mapping[str, Any], order: Mapping[str, Any] | None) -> list[str]:
    names = [*((order or {}).get("required") or []), *((order or {}).get("optional") or [])]
    if names:
        return [str(n) for n in names]
    return [*(inputs.get("required") or {}), *(inputs.get("optional") or {})]


def is_widget(spec_type: Any, options: Mapping[str, Any]) -> bool:
    """Whether an input is drawn as a widget (and so has a value in ``widgets_values``)."""
    if options.get("forceInput"):
        return False
    return isinstance(spec_type, list) or spec_type in WIDGET_TYPES or spec_type in CUSTOM_WIDGETS


def has_control(spec_type: Any, options: Mapping[str, Any]) -> bool:
    """A seed control follows the widget (``control_after_generate``: true or the control's first value)."""
    return bool(options.get("control_after_generate")) and is_widget(spec_type, options)


def option_keys(options: Mapping[str, Any]) -> list[str]:
    """The choices of a DynamicCombo."""
    return [str(o.get("key")) for o in options.get("options") or [] if isinstance(o, Mapping)]


def default_choice(options: Mapping[str, Any]) -> str:
    """A DynamicCombo's choice when none is given: its default, else its first option."""
    keys = option_keys(options)
    default = options.get("default")
    return str(default) if default in keys else (keys[0] if keys else "")


def _dynamic_option(options: Mapping[str, Any], chosen: Any) -> Mapping[str, Any] | None:
    return next(
        (o for o in options.get("options") or [] if isinstance(o, Mapping) and o.get("key") == chosen), None
    )


def _layout(
    inputs: Mapping[str, Any],
    order: Mapping[str, Any] | None,
    values: Sequence[Any],
    start: int,
    prefix: str,
    out: list[Widget],
    chosen: Callable[[str, int], Any],
) -> int:
    at = start
    for name in _ordered(inputs, order):
        try:
            spec_type, options = _spec_of(inputs, name)
        except KeyError:
            continue
        full = prefix + name
        if spec_type == DYNAMIC_COMBO:
            out.append(Widget(full, spec_type, options))
            selected = chosen(full, at)
            at += 1
            option = _dynamic_option(options, selected) or _dynamic_option(options, default_choice(options))
            if option is not None:
                nested = option.get("inputs") or {}
                at = _layout(nested, None, values, at, full + ".", out, chosen)
            continue
        if not is_widget(spec_type, options):
            continue
        out.append(Widget(full, spec_type, options))
        at += 1
        if has_control(spec_type, options):
            out.append(Widget(full, spec_type, options, control=True))
            at += 1
    return at


def widget_layout(info: NodeInfo, values: Sequence[Any] = ()) -> list[Widget]:
    """The node's widgets in the order of ``widgets_values`` (a DynamicCombo's choice read from ``values``)."""
    out: list[Widget] = []
    _layout(
        info.get("input") or {},
        info.get("input_order"),
        values,
        0,
        "",
        out,
        lambda _name, at: values[at] if at < len(values) else None,
    )
    return out


def default_value(widget: Widget) -> Any:
    """What a new widget starts with: the definition's default, else the first choice, 0, false or empty."""
    if widget.control:
        return "fixed"
    options = widget.options
    if widget.spec_type == DYNAMIC_COMBO:
        return default_choice(options)
    if "default" in options:
        return options["default"]
    if isinstance(widget.spec_type, list):
        return widget.spec_type[0] if widget.spec_type else ""
    if widget.spec_type == "COMBO":
        choices = options.get("options") or []
        return choices[0] if choices else ""
    if widget.spec_type in ("INT", "FLOAT"):
        return options.get("min", 0) if isinstance(options.get("min", 0), (int, float)) else 0
    if widget.spec_type == "BOOLEAN":
        return False
    return ""


def decode_widgets(info: NodeInfo, values: Sequence[Any]) -> dict[str, Any]:
    """``widgets_values`` by widget key (``vocals.language``, ``seed#control``)."""
    return {w.key: values[k] for k, w in enumerate(widget_layout(info, values)) if k < len(values)}


def encode_widgets(info: NodeInfo, named: Mapping[str, Any]) -> list[Any]:
    """``widgets_values`` for the widgets the values in ``named`` make (a DynamicCombo's choice included): a widget
    without a value in ``named`` gets its default."""
    out: list[Widget] = []
    _layout(
        info.get("input") or {},
        info.get("input_order"),
        (),
        0,
        "",
        out,
        lambda name, _at: named.get(name),
    )
    return [named[w.key] if w.key in named else default_value(w) for w in out]


# --- the graph ----------------------------------------------------------------------------------------------


_Link = tuple[int, int, Any]
"""(origin node, origin slot, the link's type)."""


def _links(graph: Mapping[str, Any]) -> dict[int, _Link]:
    """Link id -> (origin node, origin slot, type); list links ``[id, origin, slot, target, slot, type]`` and the
    subgraphs' object links alike."""
    found: dict[int, _Link] = {}
    for link in graph.get("links") or []:
        if isinstance(link, Mapping):
            found[int(link["id"])] = (int(link["origin_id"]), int(link["origin_slot"]), link.get("type"))
        elif isinstance(link, (list, tuple)) and len(link) >= 3:
            found[int(link[0])] = (int(link[1]), int(link[2]), link[5] if len(link) > 5 else None)
    return found


def _output_links(graph: Mapping[str, Any]) -> dict[int, _Link]:
    """A subgraph's output slot -> (inner origin node, slot, type): its links into the output node (-20)."""
    found: dict[int, _Link] = {}
    for link in graph.get("links") or []:
        if isinstance(link, Mapping) and int(link.get("target_id", 0)) == SUBGRAPH_OUTPUT:
            found[int(link["target_slot"])] = (
                int(link["origin_id"]),
                int(link["origin_slot"]),
                link.get("type"),
            )
        elif isinstance(link, (list, tuple)) and len(link) >= 5 and int(link[3]) == SUBGRAPH_OUTPUT:
            found[int(link[4])] = (int(link[1]), int(link[2]), link[5] if len(link) > 5 else None)
    return found


def _wanted(link_type: Any, fallback: Any) -> Any:
    """The type a link asks a bypassed node for: the link's own (a frontend resolves a *match type* input to it),
    else the input's."""
    return link_type if link_type not in (None, "", "*") else fallback


def _mode(node: Mapping[str, Any]) -> int:
    try:
        return int(node.get("mode") or ALWAYS)
    except (TypeError, ValueError):
        return ALWAYS


@dataclass
class _Scope:
    """One graph as it is used: the workflow itself, or a subgraph inside a node (``instance``) of ``parent``."""

    graph: Mapping[str, Any]
    prefix: str
    parent: _Scope | None = None
    instance: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        self.nodes: dict[int, Mapping[str, Any]] = {
            int(n["id"]): n for n in self.graph.get("nodes") or [] if isinstance(n, Mapping) and "id" in n
        }
        self.links = _links(self.graph)
        self.outputs = _output_links(self.graph)


_Source = tuple[str, Any] | None
"""Where an input's value comes from: ``("link", [id, slot])``, ``("value", v)`` or nothing."""


class Converter:
    """Turns one workflow into an API prompt (``convert``); ``info`` gives the node definitions."""

    def __init__(self, workflow: Mapping[str, Any], info: InfoLookup, *, rng: random.Random | None = None):
        self.workflow = workflow
        self.info = info
        self.rng = rng or random.Random()
        self.definitions: dict[str, Mapping[str, Any]] = {
            str(d["id"]): d
            for d in (workflow.get("definitions") or {}).get("subgraphs") or []
            if isinstance(d, Mapping) and d.get("id")
        }
        self._scopes: dict[str, _Scope] = {}

    # --- scopes ---
    def _inner(self, scope: _Scope, node: Mapping[str, Any]) -> _Scope:
        key = f"{scope.prefix}{node['id']}:"
        if key not in self._scopes:
            self._scopes[key] = _Scope(self.definitions[str(node["type"])], key, scope, node)
        return self._scopes[key]

    def _node_info(self, node_type: str) -> NodeInfo:
        found = self.info(node_type)
        if found is None:
            raise WorkflowError(
                f"ComfyUI does not know the node type {node_type!r} (a custom node not installed?)."
            )
        return found

    # --- values of a node ---
    def _widget_values(self, node: Mapping[str, Any]) -> dict[str, Any]:
        info = self._node_info(str(node["type"]))
        return decode_widgets(info, list(node.get("widgets_values") or []))

    def _promoted(self, scope: _Scope) -> list[int]:
        """The subgraph's inputs that are widgets on its node (they lead to a widget inside), in order: the node's
        ``widgets_values`` follow them. (A frontend that saved the workflow leaves an unlinked one out of the node's
        input slots - its value stays.)"""
        inner_slots: dict[int, list[Any]] = {
            int(n["id"]): list(n.get("inputs") or [])
            for n in scope.graph.get("nodes") or []
            if isinstance(n, Mapping)
        }
        targets: dict[int, list[tuple[int, int]]] = {}
        for link in scope.graph.get("links") or []:
            if isinstance(link, Mapping) and int(link.get("origin_id", 0)) == SUBGRAPH_INPUT:
                targets.setdefault(int(link["origin_slot"]), []).append(
                    (int(link["target_id"]), int(link["target_slot"]))
                )
            elif isinstance(link, (list, tuple)) and len(link) >= 5 and int(link[1]) == SUBGRAPH_INPUT:
                targets.setdefault(int(link[2]), []).append((int(link[3]), int(link[4])))
        promoted = []
        for index, _entry in enumerate(scope.graph.get("inputs") or []):
            for target, slot in targets.get(index, []):
                slots = inner_slots.get(target, [])
                if slot < len(slots) and isinstance(slots[slot], Mapping) and slots[slot].get("widget"):
                    promoted.append(index)
                    break
        return promoted

    def _instance_value(self, scope: _Scope, index: int) -> _Source:
        """The value of the widget the subgraph's input ``index`` is on its node."""
        instance = scope.instance or {}
        promoted = self._promoted(scope)
        values = list(instance.get("widgets_values") or [])
        if index in promoted and promoted.index(index) < len(values):
            return ("value", values[promoted.index(index)])
        return None

    # --- following links upstream ---
    def _upstream(self, scope: _Scope, origin: int, slot: int, want: Any, depth: int = 0) -> _Source:
        if depth > 256:
            raise WorkflowError("The workflow's links go round in a circle.")
        if origin == SUBGRAPH_INPUT:
            instance, parent = scope.instance, scope.parent
            if instance is None or parent is None:
                return None
            # the subgraph's input by its name on the node (the node's slots need not be in the inputs' order)
            declared = list(scope.graph.get("inputs") or [])
            name = (
                declared[slot].get("name")
                if slot < len(declared) and isinstance(declared[slot], Mapping)
                else None
            )
            entry = next(
                (s for s in instance.get("inputs") or [] if isinstance(s, Mapping) and s.get("name") == name),
                None,
            )
            link = entry.get("link") if isinstance(entry, Mapping) else None
            if link is not None and int(link) in parent.links:
                up = parent.links[int(link)]
                return self._upstream(parent, up[0], up[1], _wanted(up[2], want), depth + 1)
            return self._instance_value(scope, slot)
        node = scope.nodes.get(origin)
        if node is None:
            return None
        node_type = str(node.get("type"))
        if node_type in NOTE_TYPES:
            return None
        if node_type == REROUTE:
            return self._follow_input(scope, node, 0, want, depth)
        if node_type == PRIMITIVE:
            values = list(node.get("widgets_values") or [])
            return ("value", values[0]) if values else None
        mode = _mode(node)
        if mode == NEVER:
            return None
        if mode == BYPASS:
            return self._bypass(scope, node, slot, want, depth)
        if node_type in self.definitions:
            inner = self._inner(scope, node)
            # the node's output by its name in the subgraph's outputs (by its place when it has no name)
            outputs = list(node.get("outputs") or [])
            name = (
                outputs[slot].get("name")
                if slot < len(outputs) and isinstance(outputs[slot], Mapping)
                else None
            )
            declared = [
                o.get("name") if isinstance(o, Mapping) else None for o in inner.graph.get("outputs") or []
            ]
            if name is not None and name in declared:
                slot = declared.index(name)
            found = inner.outputs.get(slot)
            if found is None:
                return None
            return self._upstream(inner, found[0], found[1], _wanted(found[2], want), depth + 1)
        return ("link", [f"{scope.prefix}{node['id']}", slot])

    def _follow_input(
        self, scope: _Scope, node: Mapping[str, Any], index: int, want: Any, depth: int
    ) -> _Source:
        inputs = list(node.get("inputs") or [])
        entry = inputs[index] if index < len(inputs) else None
        link = entry.get("link") if isinstance(entry, Mapping) else None
        if link is None or int(link) not in scope.links:
            return None
        origin, slot, link_type = scope.links[int(link)]
        return self._upstream(scope, origin, slot, _wanted(link_type, want), depth + 1)

    def _bypass(self, scope: _Scope, node: Mapping[str, Any], slot: int, want: Any, depth: int) -> _Source:
        """A bypassed node gives the input of the type asked for: the same slot's when it has it, else the first."""
        inputs = list(node.get("inputs") or [])
        if want in (None, "", "*"):
            index = slot if slot < len(inputs) else 0
        else:
            same = inputs[slot] if slot < len(inputs) else None
            if isinstance(same, Mapping) and str(same.get("type")) == str(want):
                index = slot
            else:
                index = next(
                    (
                        k
                        for k, entry in enumerate(inputs)
                        if isinstance(entry, Mapping) and str(entry.get("type")) == str(want)
                    ),
                    -1,
                )
        if index < 0 or index >= len(inputs):
            return None
        return self._follow_input(scope, node, index, want, depth)

    # --- the prompt ---
    def _nodes(self, scope: _Scope) -> Iterator[tuple[_Scope, Mapping[str, Any]]]:
        for node in scope.graph.get("nodes") or []:
            if not isinstance(node, Mapping) or "id" not in node:
                continue
            node_type = str(node.get("type"))
            if node_type in NOTE_TYPES or node_type in (REROUTE, PRIMITIVE) or _mode(node) in (NEVER, BYPASS):
                continue
            if node_type in self.definitions:
                yield from self._nodes(self._inner(scope, node))
                continue
            yield scope, node

    def _title(self, node: Mapping[str, Any], info: NodeInfo) -> str:
        return str(node.get("title") or info.get("display_name") or node.get("type"))

    def convert(self) -> dict[str, dict[str, Any]]:
        top = _Scope(self.workflow, "")
        prompt: dict[str, dict[str, Any]] = {}
        for scope, node in self._nodes(top):
            node_type = str(node["type"])
            info = self._node_info(node_type)
            layout = widget_layout(info, list(node.get("widgets_values") or []))
            values = list(node.get("widgets_values") or [])
            inputs: dict[str, Any] = {}
            for k, widget in enumerate(layout):
                if widget.control or k >= len(values):
                    continue
                inputs[widget.name] = _serialised(widget, values[k], self.rng)
            for entry in node.get("inputs") or []:
                if not isinstance(entry, Mapping) or entry.get("link") is None:
                    continue
                name = str(entry.get("name"))
                link = int(entry["link"])
                if link not in scope.links:
                    continue
                origin, slot, link_type = scope.links[link]
                source = self._upstream(scope, origin, slot, _wanted(link_type, entry.get("type")))
                if source is None:
                    continue  # a link from a muted node, or a bypass without a matching input: left out
                inputs[name] = source[1]
            prompt[f"{scope.prefix}{node['id']}"] = {
                "inputs": inputs,
                "class_type": node_type,
                "_meta": {"title": self._title(node, info)},
            }
        return prompt


_CHOICE = re.compile(r"\{([^{}]*)\}")


def _serialised(widget: Widget, value: Any, rng: random.Random) -> Any:
    """A widget's value as sent: a text with *dynamic prompts* gets its ``{a|b}`` choices made, as the frontend
    makes them for such a widget before a run."""
    if widget.options.get("dynamicPrompts") and isinstance(value, str) and "{" in value:
        text = value
        for _ in range(64):
            changed = _CHOICE.sub(lambda m: rng.choice(m.group(1).split("|")), text)
            if changed == text:
                break
            text = changed
        return text
    return value


def to_prompt(
    workflow: Mapping[str, Any], info: InfoLookup, *, rng: random.Random | None = None
) -> dict[str, dict[str, Any]]:
    """The API prompt of ``workflow`` (see the module's text)."""
    return Converter(workflow, info, rng=rng).convert()


def randomise_controls(workflow: dict[str, Any], info: InfoLookup, rng: random.Random) -> list[str]:
    """A widget whose seed control says *randomize* gets a new number, as the frontend gives it once per run
    (in the workflow and in its subgraphs; a linked one keeps its link). The widgets changed, as
    ``<node>.<input>``."""
    changed: list[str] = []
    graphs: list[Mapping[str, Any]] = [
        workflow,
        *((workflow.get("definitions") or {}).get("subgraphs") or []),
    ]
    for graph in graphs:
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict) or str(node.get("type")) in NOTE_TYPES:
                continue
            found = info(str(node.get("type")))
            if found is None:
                continue
            values = list(node.get("widgets_values") or [])
            layout = widget_layout(found, values)
            linked = {
                str(e.get("name"))
                for e in node.get("inputs") or []
                if isinstance(e, Mapping) and e.get("link") is not None
            }
            for k, widget in enumerate(layout):
                if (
                    not widget.control
                    or k >= len(values)
                    or values[k] != "randomize"
                    or widget.name in linked
                ):
                    continue
                low = widget.options.get("min", 0)
                high = widget.options.get("max", SEED_LIMIT - 1)
                low = int(low) if isinstance(low, (int, float)) else 0
                high = min(int(high) if isinstance(high, (int, float)) else SEED_LIMIT - 1, SEED_LIMIT - 1)
                values[k - 1] = rng.randint(low, max(low, high))
                changed.append(f"{node.get('id')}.{widget.name}")
            node["widgets_values"] = values
    return changed
