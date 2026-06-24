# 0002. In-browser React/JSX via Babel standalone, pinned to v7

- **Status:** Accepted

## Context
Interactive pages (character sheet, agency sheet, star map, settings) use **React 18 with JSX compiled in the browser** by `@babel/standalone` — deliberately no Node build step or bundler. Babel 8's `preset-react` defaults to the *automatic* JSX runtime, which injects `import { jsx } from "react/jsx-runtime"` into the compiled output; Babel appends that as a classic `<script>`, so the browser throws `Cannot use import statement outside a module` and **every `text/babel` page breaks**. This happened in production when the unpinned CDN tag floated from 7.x to 8.0.0 with no deploy on our side (fixed in v0.15.39).

## Decision
Load **`@babel/standalone@7`** (major-locked), mirroring React being pinned to `react@18`. v7 keeps the classic `React.createElement` runtime, so no `import` is emitted.

## Consequences
- (+) Stable JSX compilation with zero build toolchain; fast to author.
- (+) Immune to the Babel 8 automatic-runtime breakage.
- (−) In-browser compile cost on each page load (acceptable at this scale).
- (−) Bound to the v7 line; a future move to a real build pipeline would supersede this.
