import { Component } from "react";
import { reportError } from "@/lib/crashReporter";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info);
    reportError(error, { componentStack: info?.componentStack, source: "ErrorBoundary" });
  }

  render() {
    if (this.state.hasError) {
      const msg = this.state.error?.message || "Something went wrong";
      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-8 text-center">
          <div className="w-12 h-12 rounded-full bg-danger/10 flex items-center justify-center">
            <span className="text-2xl text-danger">!</span>
          </div>
          <h2 className="text-lg font-semibold text-foreground">Page Error</h2>
          <p className="text-sm text-muted-foreground max-w-md">{msg}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
