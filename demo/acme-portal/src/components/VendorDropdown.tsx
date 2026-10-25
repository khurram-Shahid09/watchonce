"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { makeUi, type Mutation } from "@/lib/variant";

interface Option {
  id: string;
  name: string;
}

/**
 * Custom (non-native) dropdown, the kind legacy portals build themselves: a button with
 * role="combobox" plus a popup listbox. Replaying it needs "click to open, click the option".
 * The chosen value is submitted through a hidden input.
 */
export function VendorDropdown({
  mutations,
  id,
  labelId,
  name,
  options,
  defaultValue,
}: {
  mutations: Mutation[];
  id: string;
  labelId: string;
  name: string;
  options: Option[];
  defaultValue?: string;
}) {
  const ui = makeUi(mutations);
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(defaultValue ?? "");
  const [active, setActive] = useState(0);
  const selected = options.find((o) => o.id === value);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const choose = (option: Option) => {
    setValue(option.id);
    setOpen(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) setOpen(true);
      setActive((i) => (e.key === "ArrowDown" ? Math.min(i + 1, options.length - 1) : Math.max(i - 1, 0)));
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (options[active]) choose(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key.length === 1 && /\S/.test(e.key)) {
      const i = options.findIndex((o) => o.name.toLowerCase().startsWith(e.key.toLowerCase()));
      if (i >= 0) {
        setOpen(true);
        setActive(i);
      }
    }
  };

  return (
    <div className={ui.cls("dropdown")} ref={root}>
      <input type="hidden" name={name} value={value} />
      <button
        type="button"
        id={id}
        role="combobox"
        aria-labelledby={labelId}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        className={ui.cls("btn form-control dropdown-toggle")}
        data-testid={ui.testid("vendor-dropdown")}
        onClick={() => {
          setActive(Math.max(0, options.findIndex((o) => o.id === value)));
          setOpen((o) => !o);
        }}
        onKeyDown={onKeyDown}
      >
        <span>{selected ? selected.name : "— Select —"}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open ? (
        <ul id={listId} role="listbox" aria-labelledby={labelId} className={ui.cls("dropdown-menu")}>
          {options.map((o, i) => (
            <li
              key={o.id}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              className={ui.cls("dropdown-item")}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(o)}
            >
              {o.name}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
