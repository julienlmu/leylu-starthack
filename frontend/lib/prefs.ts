"use client";
// Per-browser UI preferences (view, theme). Storage can be missing or throw (private mode): defaults then.
import { useCallback, useEffect, useState } from "react";

const readPref = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

export const writePref = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
  } catch {
    // not stored: the choice holds for this page view only
  }
};

// A remembered choice: the default on the server and the first render, the stored value right after mount.
export function usePref<T extends string>(key: string, fallback: T, allowed: readonly T[]): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(fallback);
  useEffect(() => {
    const stored = readPref(key);
    if (stored && (allowed as readonly string[]).includes(stored)) setValue(stored as T);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = useCallback(
    (v: T) => {
      setValue(v);
      writePref(key, v);
    },
    [key],
  );
  return [value, set];
}

export type View = "simple" | "detailed";
export const VIEWS = ["simple", "detailed"] as const;
