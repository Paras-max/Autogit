import { useEffect, useState } from 'react';

export interface SSEEvent {
  id?: number;
  event: string;
  repository_id?: number | null;
  timestamp: string;
  data: any;
}

export function useSSE(onEvent?: (event: SSEEvent) => void) {
  const [connected, setConnected] = useState<boolean>(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let retryTimeout: any = null;

    function connect() {
      eventSource = new EventSource('/api/v1/events/stream');

      eventSource.onopen = () => {
        setConnected(true);
      };

      eventSource.onerror = () => {
        setConnected(false);
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        // Auto-reconnect after 3 seconds
        retryTimeout = setTimeout(connect, 3000);
      };

      // Listen for message events
      eventSource.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data);
          setLastEvent(parsed);
          if (onEvent) onEvent(parsed);
        } catch {
          // ignore keepalive comments
        }
      };

      // Generic custom events listener
      const eventTypes = [
        'file_change',
        'notification_created',
        'notification_read',
        'notifications_all_read',
        'proposal_created',
        'commit_created',
        'sync_completed',
        'scheduled_session_active',
      ];

      eventTypes.forEach((type) => {
        eventSource?.addEventListener(type, (e: any) => {
          try {
            const parsed = JSON.parse(e.data);
            setLastEvent(parsed);
            if (onEvent) onEvent(parsed);
          } catch {
            // ignore
          }
        });
      });
    }

    connect();

    return () => {
      if (retryTimeout) clearTimeout(retryTimeout);
      if (eventSource) eventSource.close();
    };
  }, []);

  return { connected, lastEvent };
}

