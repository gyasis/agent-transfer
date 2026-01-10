# Import Preview UI - Visual Reference

## Initial Display (Pre-selected NEW + CHANGED)

```
╭───────────────────────────────────────────────────╮
│  2 agent(s) selected                              │
╰───────────────────────────────────────────────────╯

╭──────────────────────── Import Preview ────────────────────────╮
│   ✓  │  #  │ Name          │ Description                       │ Status    │ Diff       │ Type    │
├──────┼─────┼───────────────┼───────────────────────────────────┼───────────┼────────────┼─────────┤
│   ✓  │  1  │ data-analyst  │ Analyzes data and generates...    │    NEW    │            │  User   │
│   ✓  │  2  │ frontend-dev  │ Frontend development specialist..│  CHANGED  │ +12 -5 ~3  │  User   │
│      │  3  │ backend-api   │ Backend API developer             │ IDENTICAL │            │ Project │
╰──────┴─────┴───────────────┴───────────────────────────────────┴───────────┴────────────┴─────────╯

Options:
  1-N    - Toggle agent by number
  a      - Select all (in current filter)
  d      - Deselect all
  n      - Select NEW only
  c      - Select CHANGED only
  f      - Filter view (cycle: ALL → NEW → CHANGED → IDENTICAL)
  v      - View unified diff for agent
  s      - View side-by-side for agent
  i      - Show details for agent
  enter  - Confirm selection
  q      - Quit without selecting

Your choice:
```

## Filter: NEW Only

```
╭───────────────────────────────────────────────────╮
│  1 agent(s) selected | Filter: NEW               │
╰───────────────────────────────────────────────────╯

╭──────────────────────── Import Preview ────────────────────────╮
│   ✓  │  #  │ Name          │ Description                       │ Status    │ Diff  │ Type  │
├──────┼─────┼───────────────┼───────────────────────────────────┼───────────┼───────┼───────┤
│   ✓  │  1  │ data-analyst  │ Analyzes data and generates...    │    NEW    │       │ User  │
╰──────┴─────┴───────────────┴───────────────────────────────────┴───────────┴───────┴───────╯
```

## Unified Diff View (Command: v)

```
Enter agent number to view diff: 2

  1   # Frontend Developer
  2
  3   You are a frontend developer specializing in React.
  4
- 5   Use React 17 with class components
+ 5   Use React 18 with functional components and hooks
  6
- 7   ## Tools
+ 7   ## Tools & Stack
+ 8   - TypeScript for type safety
  9   - Vite for fast builds
```

## Side-by-Side Comparison (Command: s)

```
╭──────────────────────────── Comparison: frontend-dev ────────────────────────────╮
│  #  │ Existing                                │ Incoming                           │
├─────┼─────────────────────────────────────────┼────────────────────────────────────┤
│  1  │ # Frontend Developer                    │ # Frontend Developer               │
│  2  │                                         │                                    │
│  3  │ You are a frontend developer...         │ You are a frontend developer...    │
│  4  │                                         │                                    │
│  5  │ Use React 17 with class components      │ Use React 18 with functional...    │
│  6  │                                         │                                    │
│  7  │ ## Tools                                │ ## Tools & Stack                   │
│  8  │ - Vite for fast builds                  │ - TypeScript for type safety       │
│  9  │                                         │ - Vite for fast builds             │
╰─────┴─────────────────────────────────────────┴────────────────────────────────────╯
```

## Agent Details View (Command: i)

```
Enter agent number to view details: 2

╭──────────────────────────────── Agent Details ────────────────────────────────╮
│  frontend-dev                                                                  │
│                                                                                │
│  Description: Frontend development specialist with React expertise            │
│  Type: User-level                                                             │
│  Status: CHANGED                                                              │
│  File: frontend-dev.md                                                        │
│  Tools: Read, Edit, Bash, WebSearch                                           │
│  Permission Mode: full                                                        │
│  Model: claude-sonnet-4                                                       │
│  Local Path: /home/user/.claude/agents/frontend-dev.md                        │
│  Diff: +12 -5 ~3                                                              │
╰────────────────────────────────────────────────────────────────────────────────╯

Press Enter to continue...
```

## Command Flow Examples

### Scenario 1: Accept Pre-selected Defaults
```
User sees: 2 agent(s) selected (NEW + CHANGED)
User action: Press Enter
Result: Installs 2 agents, skips IDENTICAL
```

### Scenario 2: Select Only NEW Agents
```
User sees: 2 agent(s) selected
User action: Press 'n'
Screen updates: 1 agent(s) selected (only NEW)
User action: Press Enter
Result: Installs only the new agent
```

### Scenario 3: Review Changes Before Installing
```
User sees: 2 agent(s) selected
User action: Press 'v', enter '2'
Screen shows: Unified diff of changes
User action: Press Enter to go back
User action: Press 's', enter '2'
Screen shows: Side-by-side comparison
User action: Press Enter to confirm selection
Result: Installs both agents after review
```

### Scenario 4: Filter and Select Specific Agents
```
User sees: 2 agent(s) selected
User action: Press 'f' (cycle to NEW filter)
Screen shows: Only NEW agents visible
User action: Press 'a' (select all in filter)
User action: Press 'f' (cycle to CHANGED filter)
Screen shows: Only CHANGED agents visible
User action: Press '1' (toggle first changed agent)
User action: Press 'f' (cycle back to ALL)
Screen shows: All agents with updated selection
User action: Press Enter
Result: Installs selected subset
```

## Color Coding

- **NEW**: Green bold text - clear indication of new agents
- **CHANGED**: Yellow bold text - highlights modified agents
- **IDENTICAL**: Dimmed text - de-emphasizes unchanged agents
- **Selected row**: Checkmark (✓) in first column
- **Diff summary**: Shows changes like "+12 -5 ~3" (added, removed, modified)

## Status Messages

### NEW Agent
```
[yellow]This is a new agent (no local version to compare)[/yellow]
```

### IDENTICAL Agent
```
[green]This agent is identical to the local version[/green]
```

### CHANGED Agent
```
Shows unified diff or side-by-side comparison
```

## Pre-selection Benefits

1. **Zero-thought imports**: For typical use cases, user just presses Enter
2. **Smart defaults**: NEW + CHANGED are what users usually want
3. **Safe defaults**: IDENTICAL agents excluded to avoid unnecessary overwrites
4. **Clear feedback**: Visual indicators show what will be installed
5. **Easy customization**: Simple commands to adjust selection if needed
