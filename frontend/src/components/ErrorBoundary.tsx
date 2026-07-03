import { Component, type ComponentType, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { reportError } from '@/lib/errorTracking';

interface ErrorBoundaryProps {
  children: ReactNode;
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

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
          <h1 className="text-lg font-semibold text-foreground">Something went wrong</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            An unexpected error occurred. Reloading the page usually fixes this.
          </p>
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </div>
      );
    }
    return this.props.children;
  }
}

// eslint-disable-next-line react-refresh/only-export-components
export function withErrorBoundary<P extends object>(
  WrappedComponent: ComponentType<P>
): ComponentType<P> {
  function ComponentWithErrorBoundary(props: P) {
    return (
      <ErrorBoundary>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  }
  ComponentWithErrorBoundary.displayName = `withErrorBoundary(${
    WrappedComponent.displayName ?? WrappedComponent.name ?? 'Component'
  })`;
  return ComponentWithErrorBoundary;
}
