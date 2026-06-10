import { useEffect, useState } from "react";
import { useApp } from "@/lib/store";
import { toast } from "sonner";
import type { Article } from "@/lib/types";

export function useArticleListNav(list: Article[], openArticle: (a: Article) => void) {
  const [focused, setFocused] = useState(0);
  const { setState, toggleStar, sendLater, restore } = useApp.getState();

  useEffect(() => {
    if (focused >= list.length) setFocused(Math.max(0, list.length - 1));
  }, [list.length, focused]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable) return;
      const cur = list[focused];
      if (e.key === "j") { setFocused((f) => Math.min(list.length - 1, f + 1)); e.preventDefault(); }
      else if (e.key === "k") { setFocused((f) => Math.max(0, f - 1)); e.preventDefault(); }
      else if (e.key === "Enter" && cur) { openArticle(cur); e.preventDefault(); }
      else if ((e.key === "r" || e.key === "d") && cur) {
        const snap = setState(cur.id, "done");
        if (snap) toast("Done", { action: { label: "Undo", onClick: () => restore(snap) } });
      } else if (e.key === "l" && cur) {
        const snap = sendLater(cur.id);
        if (snap) toast("Snoozed to tomorrow", { action: { label: "Undo", onClick: () => restore(snap) } });
      } else if (e.key === "s" && cur) {
        const snap = toggleStar(cur.id);
        toast(cur.starred ? "Unstarred" : "Starred", { action: { label: "Undo", onClick: () => restore(snap) } });
      } else if (e.key === "x" && cur) {
        if (cur.starred) { toast.error("Starred articles can't be skipped"); return; }
        const snap = setState(cur.id, "skipped");
        if (snap) toast("Skipped", { action: { label: "Undo", onClick: () => restore(snap) } });
      } else if (e.key === "e" && cur) {
        const snap = setState(cur.id, "archived");
        if (snap) toast("Archived", { action: { label: "Undo", onClick: () => restore(snap) } });
      } else if (e.key === "o" && cur) {
        window.open(cur.url, "_blank");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [list, focused, openArticle, setState, toggleStar, sendLater, restore]);

  return { focused, setFocused };
}
