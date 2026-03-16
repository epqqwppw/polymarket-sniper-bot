import { useEffect, useRef, useState, useCallback } from "react";
import { io } from "socket.io-client";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

/**
 * Hook that manages the Socket.IO connection to the backend.
 * Returns: { socket, connected }
 */
export function useSocket() {
  const socketRef = useRef(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const socket = io(BACKEND_URL, {
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: Infinity,
    });

    socket.on("connect", () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));

    socketRef.current = socket;

    return () => {
      socket.disconnect();
    };
  }, []);

  const emit = useCallback((event, data) => {
    if (socketRef.current) {
      socketRef.current.emit(event, data);
    }
  }, []);

  return { socket: socketRef.current, connected, emit };
}
