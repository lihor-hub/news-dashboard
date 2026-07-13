import { createContext, useContext, useState, type ReactNode } from 'react';
import type { WorkflowArticle } from '@/lib/workflowTypes';

interface FocusedArticleCtx {
  article: WorkflowArticle | null;
  set: (a: WorkflowArticle | null) => void;
}

const Ctx = createContext<FocusedArticleCtx>({ article: null, set: (_a) => {} });

export function FocusedArticleProvider({ children }: { children: ReactNode }) {
  const [article, set] = useState<WorkflowArticle | null>(null);
  return <Ctx.Provider value={{ article, set }}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useFocusedArticle() {
  return useContext(Ctx);
}
