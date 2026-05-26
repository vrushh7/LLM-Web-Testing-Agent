import { useEffect, useRef, useState } from 'react';

export function useRunSocket(url, onEvent) {
  const [connected, setConnected] = useState(false);
  const callbackRef = useRef(onEvent);

  useEffect(() => {
    callbackRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!url) {
      setConnected(false);
      return undefined;
    }

    const socket = new WebSocket(url);
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (message) => {
      try {
        callbackRef.current?.(JSON.parse(message.data));
      } catch {
        callbackRef.current?.({ type: 'log', message: message.data, timestamp: new Date().toISOString() });
      }
    };

    return () => socket.close();
  }, [url]);

  return connected;
}

