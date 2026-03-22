/**
 * Error Tracking Utility
 *
 * Provides a unified interface for reporting errors across the application.
 * Currently logs to the console, but can be easily extended to support
 * services like Sentry, LogRocket, or a custom backend endpoint.
 */

export const errorTracker = {
  /**
   * Reports an error to the tracking service.
   * @param {Error|string} error - The error object or message to track.
   * @param {Object} [metadata] - Additional context about the error.
   */
  reportError: (error, metadata = {}) => {
    // In a real-world scenario, you would send this to Sentry or similar:
    // Sentry.captureException(error, { extra: metadata });

    if (process.env.NODE_ENV !== 'production') {
      console.group('Error Reported:');
      console.error(error);
      if (Object.keys(metadata).length > 0) {
        console.info('Metadata:', metadata);
      }
      console.groupEnd();
    } else {
      // Production logging logic
      console.error(error);
    }
  },

  /**
   * Tracks a custom message or event.
   * @param {string} message - The message to track.
   * @param {string} [level='info'] - The severity level (info, warning, error).
   */
  log: (message, level = 'info') => {
    if (process.env.NODE_ENV !== 'production') {
      console.log(`[${level.toUpperCase()}] ${message}`);
    }
    // Potential integration: Sentry.addBreadcrumb({ message, level });
  }
};

export default errorTracker;
