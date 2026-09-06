# plyunit Naming Convention

> Index: [index.md](index.md)

This document is the naming reference for the entire `plyunit` package. The
goal is simple: one concept must have one canonical name, so the engine API
stays unambiguous both to use and to maintain.

## 1. Core principles

- Use one term for one concept. Do not mix synonyms for the same thing.
- Public names must reflect behavior from the engine user's point of view.
- Internal helpers must be distinguished with the `_` prefix.
- Avoid overly generic names such as `data`, `value`, `temp`, or `current`
  when the context is not clear.
- If there is a typo or questionable spelling, fix it now. A misspelled API
  name will be carried along into new code forever.

## 2. Lifecycle and hooks

### 2.1 Recurring per-frame hooks

Use the following names for callbacks invoked continuously every frame or
every fixed step:

- `update(dt)` for fixed-step node, component, scene, and application logic.
- `fixed_update(dt, step)` for application fixed-step simulation.
- `update(dt)` for application per-frame work (the render pipeline).
- `render_submit(queue)` to enqueue draw calls into the render queue (node/scene level).
- `draw(canvas)` for final drawing operations at the canvas / renderer level.

Practical rules:

- Do not add alternate names such as `on_update` or `on_render_submit` when the canonical hook already exists.
- `update` is the canonical name for the logic loop.
- `render_submit` is the canonical name for the render submission phase.

### 2.2 One-time or event-style callbacks

Use the `on_` prefix only for one-time occurrences or system-event callbacks:

- `on_load`
- `on_unload`
- `on_enter_tree`
- `on_exit_tree`
- `on_attach`
- `on_start`
- `on_destroy`

Practical rules:

- If a method represents an event, use `on_`.
- If a method represents a recurring loop, do not use `on_`.
- If a method is only an internal engine dispatcher, prefer the `_` prefix.

### 2.3 Internal dispatchers

When the engine needs to invoke public hooks while running internal traversal /
orchestration, use private helpers such as:

- `_dispatch_update`
- `dispatch_render`
- `_attach_subtree`
- `_detach_subtree`
- `_destroy_subtree`
- `_apply_pending`

The goal is to keep the public API clean while making it clear that traversal
logic belongs to the engine.

## 3. Variable and field names

- Use specific nouns, not random synonyms.
- Storing the name of the currently active animation? Use `current_clip_name`.
- Storing a frame index? Use `frame_index`.
- Storing a target position? Use `target_position`.
- Storing tree state? Use names that show the domain, e.g. `active_tree` or
  `visible_tree`.

Practical rules:

- Avoid pairs like `current` and `clip_name` used together for the same concept.
- Avoid mixing `index_frame` and `frame_index`.
- Avoid `value` when a more specific domain name is available.
- Use plurals for collections: `children`, `clips`, `groups`, `actions`.

## 4. Method names

### 4.1 Mutators

Use the following prefixes for methods that change state:

- `set_` to replace a value.
- `add_` to add an item.
- `remove_` to remove an item.
- `load_` to load data.
- `save_` to persist data.

### 4.2 Queries

Use these patterns for search and lookup methods:

- `get_` to fetch a single, clearly identified value.
- `find_` for searches that return a list or more than one result.
- `group` may be used as a list query if it is already consistent domain vocabulary.
- `one` for exactly one result.
- `one_or_none` for one result or `None`.

### 4.3 Predicates

Use the following prefixes for boolean methods:

- `is_` for status.
- `has_` for ownership.
- `can_` for capability.
- `should_` for rule-based decisions.

### 4.4 Internal helpers

- Use the `_` prefix for algorithmic helpers, caches, traversals, and bridges to public APIs.
- Do not expose internal helpers as part of the user contract unless truly required.

## 5. Parameter names

Use parameter names consistently across the repository:

- `dt` for delta time.
- `queue` for the render queue.
- `canvas` for the final canvas.
- `unit` for the node/unit being processed.
- `component` for components.
- `scene_factory` for scene factories.

Practical rules:

- Do not rename parameters for the same concept without a strong reason.
- If a parameter name already has an established meaning in the engine, keep it.

## 6. plyunit standard

- `NodeUnit`, `SceneUnit`, and `Component` use `update` and `render_submit` as recurring hooks.
- `SceneUnit` uses `_dispatch_update` and `dispatch_render` for engine orchestration.
- `App` uses `_fixed_step` internally and exposes `fixed_update` and `update` as the two mandatory extension hooks.
- `SceneManager` only forwards lifecycle to the active scene.

## 7. Anti-patterns to avoid

- `render_sumbit` must always be written `render_submit`.
- `transision` must always be written `transition`.
- Do not mix English and Indonesian in the same identifier.
- Do not use overly generic names when the domain context is clear.

## 8. Checklist before naming a new method or field

- Is this a public hook or an internal helper?
- Is this a per-frame hook, a one-time event, or a query?
- Is it a boolean, a collection, or a single value?
- Does this concept already have a canonical name elsewhere in the code?
- Will this name still be clear when read six months from now?

If the answer is unclear, pick a more specific name, not a shorter one.
