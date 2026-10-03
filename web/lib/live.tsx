"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type {
  Inspection,
  Alert,
  StatsMessage,
  StationStatus,
  CalibrationState,
  WsMessage,
} from "./types";
import { isWsMessage } from "./types";
import { wsUrl } from "./api";

// ── Writer state (from "writer" WS messages) ────────
interface WriterState {
  lastWriteTime: number | null;
  pendingCount: number;
  blocked: boolean;
}

// ── Live context value ───────────────────────────────
interface LiveContextValue {
  connected: boolean;
  stats: StatsMessage | null;
  writer: WriterState;
  latestInspection: Inspection | null;
  latestAlert: Alert | null;
  calibration: CalibrationState | null;
  status: StationStatus | null;
  inspections: Inspection[];
  alerts: Alert[];
}

const defaultWriter: WriterState = {
  lastWriteTime: null,
  pendingCount: 0,
  blocked: false,
};

const LiveContext = createContext<LiveContextValue>({
  connected: false,
  stats: null,
  writer: defaultWriter,
  latestInspection: null,
  latestAlert: null,
  calibration: null,
  status: null,
  inspections: [],
  alerts: [],
});

const MAX_INSPECTIONS = 200;
const MAX_ALERTS = 100;

interface LiveProviderProps {
  children: React.ReactNode;
}

function LiveProvider({ children }: LiveProviderProps) {
  const [connected, setConnected] = useState(false);
  const [stats, setStats] = useState<StatsMessage | null>(null);
  const [writer, setWriter] = useState<WriterState>(defaultWriter);
  const [latestInspection, setLatestInspection] = useState<Inspection | null>(null);
  const [latestAlert, setLatestAlert] = useState<Alert | null>(null);
  const [calibration, setCalibration] = useState<CalibrationState | null>(null);
  const [status, setStatus] = useState<StationStatus | null>(null);
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const url = wsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (mountedRef.current) setConnected(true);
    };

    ws.onclose = () => {
      if (mountedRef.current) {
        setConnected(false);
        // Reconnect after 2s
        reconnectTimer.current = setTimeout(connect, 2000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (ev: MessageEvent) => {
      if (!mountedRef.current) return;
      let data: unknown;
      try {
        data = JSON.parse(String(ev.data));
      } catch {
        return;
      }

      // Handle writer messages (not in WsMessage union)
      if (
        typeof data === "object" &&
        data !== null &&
        "type" in data &&
        (data as Record<string, unknown>)["type"] === "writer"
      ) {
        const w = data as Record<string, unknown>;
        setWriter({
          lastWriteTime: typeof w["last_write_time"] === "number" ? w["last_write_time"] : null,
          pendingCount: typeof w["pending_count"] === "number" ? w["pending_count"] : 0,
          blocked: typeof w["blocked"] === "boolean" ? w["blocked"] : false,
        });
        return;
      }

      if (!isWsMessage(data)) return;

      const msg: WsMessage = data;

      switch (msg.type) {
        case "stats":
          setStats(msg);
          break;
        case "inspection":
          setLatestInspection(msg.inspection);
          setInspections((prev) => [msg.inspection, ...prev].slice(0, MAX_INSPECTIONS));
          break;
        case "alert":
          setLatestAlert(msg.alert);
          setAlerts((prev) => [msg.alert, ...prev].slice(0, MAX_ALERTS));
          break;
        case "calibration":
          setCalibration(msg.calibration);
          break;
        case "status":
          setStatus(msg.status);
          break;
      }
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const value: LiveContextValue = {
    connected,
    stats,
    writer,
    latestInspection,
    latestAlert,
    calibration,
    status,
    inspections,
    alerts,
  };

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

function useLive(): LiveContextValue {
  return useContext(LiveContext);
}

export { LiveProvider, useLive };
export type { LiveContextValue, WriterState };
