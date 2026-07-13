import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { reportError } from '@/lib/errorTracking';
import { isChunkLoadError } from '@/lib/chunkError';

interface ErrorBoundaryProps {
  children: ReactNode;
  /** When this value changes (e.g. the route pathname), the boundary resets. */
  resetKey?: unknown;
  /** Render the fallback inline instead of filling the viewport, so the app shell stays visible. */
  compact?: boolean;
  /** Report the error but render nothing — for nonessential overlays that must not disrupt navigation. */
  silent?: boolean;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    reportError(error, { componentStack: errorInfo.componentStack });
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  handleRetry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      if (this.props.silent) return null;
      const chunkError = isChunkLoadError(error);
      const containerClass = this.props.compact
        ? 'flex flex-col items-center justify-center gap-4 p-8 text-center'
        : 'flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center';

      return (
        <div className={containerClass}>
          <h1 className="text-lg font-semibold text-foreground">
            {chunkError ? 'A new version is available' : 'Something went wrong'}
          </h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            {chunkError
              ? 'This page was updated since it loaded. Reload to get the latest version.'
              : 'An unexpected error occurred.'}
          </p>
          <div className="flex items-center gap-3">
            {!chunkError && (
              <Button variant="outline" onClick={this.handleRetry}>
                Try again
              </Button>
            )}
            <Button onClick={() => window.location.reload()}>Reload</Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
