import { Link } from "@tanstack/react-router";
import { Star } from "lucide-react";
import type { Article } from "@/lib/types";
import { relativeTime, signalLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SwipeableRow } from "./SwipeableRow";
import { useApp } from "@/lib/store";
import { toast } from "sonner";

interface Props {
  article: Article;
  focused?: boolean;
  onClick?: () => void;
  showLaterUntil?: boolean;
}

export function ArticleRow({ article, focused, onClick, showLaterUntil }: Props) {
  const { toggleStar, setState, restore } = useApp.getState();

  const handleStar = () => {
    const snap = toggleStar(article.id);
    toast(article.starred ? "Unstarred" : "Starred", {
      action: { label: "Undo", onClick: () => restore(snap) },
    });
  };
  const handleSkip = () => {
    if (article.starred) {
      toast.error("Starred articles can't be skipped");
      return;
    }
    const snap = setState(article.id, "skipped");
    if (snap) toast("Skipped", { action: { label: "Undo", onClick: () => restore(snap) } });
  };

  const signalColor =
    article.signal === "high" ? "text-signal-high" : article.signal === "mid" ? "text-signal-mid" : "text-signal-low";

  return (
    <SwipeableRow onSwipeRight={handleStar} onSwipeLeft={handleSkip} disableLeft={article.starred}>
      <Link
        to="/a/$id"
        params={{ id: article.id }}
        onClick={onClick}
        className={cn(
          "block px-4 py-3 border-b border-border transition-colors hover:bg-surface md:px-5",
          focused && "focus-row",
        )}
      >
        <div className="flex items-baseline justify-between gap-3 mb-1">
          <div className="flex items-baseline gap-1.5 min-w-0 text-[11px] text-subtle">
            <span className="truncate font-medium text-muted-foreground">{article.sourceName}</span>
            <span>·</span>
            <span className="shrink-0">{relativeTime(article.publishedAt)}</span>
            <span>·</span>
            <span className="truncate">{article.category}</span>
          </div>
          {article.starred && <Star className="size-3.5 shrink-0 fill-star text-star" strokeWidth={1.5} />}
        </div>
        <h3 className="text-[15px] leading-snug font-semibold tracking-tight text-foreground mb-1.5">
          {article.title}
        </h3>
        <p className="text-[13px] leading-snug text-foreground/80 line-clamp-1">
          {article.reason}
        </p>
        <div className="mt-1.5 flex items-center gap-2 text-[11px]">
          <span className={cn("font-medium", signalColor)}>{signalLabel(article.signal)}</span>
          {showLaterUntil && article.later_until && (
            <>
              <span className="text-subtle">·</span>
              <span className="text-subtle">returns {relativeTime(article.later_until)}</span>
            </>
          )}
        </div>
      </Link>
    </SwipeableRow>
  );
}
