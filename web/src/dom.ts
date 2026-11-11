// The only way this page builds DOM. Strings always become text nodes, never HTML, so
// file names, headers, cell values and messages from an upload cannot run as markup.
// tests/workspace/test_web_source.py fails if any other file reaches for innerHTML.

export type Child = Node | string | number | null | undefined | false;

export interface Props {
  class?: string;
  attrs?: Record<string, string>;
  on?: { [K in keyof HTMLElementEventMap]?: (event: HTMLElementEventMap[K]) => void };
}

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Props = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (props.class) el.className = props.class;
  for (const [name, value] of Object.entries(props.attrs ?? {})) {
    if (name.toLowerCase().startsWith("on")) throw new Error(`refusing attribute ${name}`);
    el.setAttribute(name, value);
  }
  for (const [name, handler] of Object.entries(props.on ?? {})) {
    el.addEventListener(name, handler as EventListener);
  }
  append(el, ...children);
  return el;
}

export function append(parent: Node, ...children: Child[]): void {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(
      typeof child === "string" || typeof child === "number"
        ? document.createTextNode(String(child))
        : child,
    );
  }
}

export function clear(el: Element): void {
  el.replaceChildren();
}
