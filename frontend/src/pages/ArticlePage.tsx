import { useParams, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export function ArticlePage() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="min-h-screen bg-background text-foreground p-4 md:p-8 max-w-2xl mx-auto">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="size-4" />
        Back
      </Link>
      <p className="text-sm text-muted-foreground">
        Article reader for {id} — coming in a future slice.
      </p>
    </div>
  );
}
