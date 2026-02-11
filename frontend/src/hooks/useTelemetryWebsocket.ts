import { useState, useEffect, useCallback, useRef } from "react";

type TelemetryWebSocketOptions = {
	/**
	 * When false, the hook will NOT open a WebSocket and will actively disconnect
	 * any existing connection. This prevents background connections when a page/tab
	 * mounts without an active mission/drone session.
	 */
	enabled?: boolean;
};

export const useTelemetryWebSocket = (
	options: TelemetryWebSocketOptions = {},
) => {
	const enabled = options.enabled ?? false;
	const [telemetry, setTelemetry] = useState<any | null>(null);
	const [isConnected, setIsConnected] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [reconnectAttempt, setReconnectAttempt] = useState(0);

	const wsRef = useRef<WebSocket | null>(null);
	const shouldReconnectRef = useRef(true);
	const reconnectTimerRef = useRef<number | null>(null);
	const maxReconnectAttemptsRef = useRef(10); // Max 10 reconnection attempts

	const latestRef = useRef<any | null>(null);
	const rafRef = useRef<number | null>(null);

	// useTelemetryWebsocket.ts (update connectWebSocket function)
	const connectWebSocket = useCallback(
		(attempt = 1) => {
			if (!enabled) return;
			shouldReconnectRef.current = true;

			// Close existing connection
			if (wsRef.current) {
				try {
					wsRef.current.close(1000, "Reconnecting");
				} catch (e) {
					// Ignore errors
				}
			}

			const apiBaseRaw = (
				import.meta.env.VITE_API_BASE_URL as string | undefined
			)?.trim();
			const apiBase =
				apiBaseRaw && apiBaseRaw.includes("://")
					? apiBaseRaw
					: "http://localhost:8000";

			const u = new URL(apiBase);
			u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
			u.pathname = "/ws/telemetry/public";
			u.search = "";

			console.log(
				`🔗 Connecting to WebSocket: ${u.toString()} (attempt ${attempt})`,
			);

			try {
				const ws = new WebSocket(u.toString());
				ws.binaryType = "arraybuffer";
				wsRef.current = ws;

				ws.onopen = () => {
					console.log(`✅ WebSocket connected (attempt ${attempt})`);
					setIsConnected(true);
					setError(null);
					setReconnectAttempt(0);

					// Send initial ping to confirm connection
					setTimeout(() => {
						if (ws.readyState === WebSocket.OPEN) {
							ws.send("ping");
						}
					}, 1000);
				};

				ws.onmessage = async (event) => {
					// Telemetry server sends JSON text frames
					try {
          const readText = async (data: any): Promise<string> => {
            if (typeof data === "string") return data;
            // Some browsers deliver text frames as Blob
            if (typeof Blob !== "undefined" && data instanceof Blob) {
              return await data.text();
            }
            // Or as ArrayBuffer when binaryType is set
            if (data instanceof ArrayBuffer) {
              return new TextDecoder("utf-8").decode(new Uint8Array(data));
            }
            return "";
          };

          const raw = await readText(event.data);
						if (!raw) return;

						// Some servers may send plain "pong"
						if (raw === "pong") return;

						const msg = JSON.parse(raw);
						if (!msg) return;

						if (msg.type === "telemetry" && msg.data) {
							latestRef.current = msg.data;

							// Batch UI updates to reduce flicker / rerender storms
							if (rafRef.current == null) {
								rafRef.current = window.requestAnimationFrame(() => {
									rafRef.current = null;
									setTelemetry(latestRef.current);
								});
							}
						}
					} catch (e) {
						// Ignore non-JSON frames
					}
				};

				ws.onerror = () => {
					console.error(`❌ WebSocket connection error (attempt ${attempt})`);
					setError("WebSocket connection error");
					setIsConnected(false);
				};

				ws.onclose = (ev) => {
					console.log(
						`🔌 WebSocket closed (attempt ${attempt}, code: ${ev.code}, reason: ${ev.reason})`,
					);
					setIsConnected(false);

					// Don't reconnect on normal closes
					if (!shouldReconnectRef.current) return;
					if (ev.code === 1000) return;

					// Exponential backoff reconnect, bounded + capped attempts
					if (attempt >= maxReconnectAttemptsRef.current) {
						setError(`WebSocket disconnected (max retries reached)`);
						return;
					}

					const delay = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
					setReconnectAttempt(attempt);
					reconnectTimerRef.current = window.setTimeout(() => {
						connectWebSocket(attempt + 1);
					}, delay);
				};
			} catch (error) {
				console.error(`❌ Failed to create WebSocket: ${error}`);
				// Retry with backoff
				const delay = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
				reconnectTimerRef.current = window.setTimeout(() => {
					connectWebSocket(attempt + 1);
				}, delay);
			}
		},
		[enabled],
	);

	const disconnectWebSocket = useCallback(() => {
		console.log("🛑 Disconnecting WebSocket...");
		shouldReconnectRef.current = false;

		// Clear any pending reconnect timer
		if (reconnectTimerRef.current) {
			window.clearTimeout(reconnectTimerRef.current);
			reconnectTimerRef.current = null;
		}

		// Close WebSocket connection
		if (wsRef.current) {
			wsRef.current.close(1000, "Manual disconnect"); // Normal closure
			wsRef.current = null;
		}

		setIsConnected(false);
		setReconnectAttempt(0);
	}, []);

	// Manual reconnect function (for external calls)
	const manualReconnect = useCallback(() => {
		if (!enabled) return;
		console.log("🔄 Manual reconnect requested");
		disconnectWebSocket(); // Clean up first
		setTimeout(() => {
			connectWebSocket(1);
		}, 500);
	}, [enabled, connectWebSocket, disconnectWebSocket]);

	// Initial connection
	useEffect(() => {
		if (!enabled) {
			disconnectWebSocket();
			return;
		}

		console.log("🔗 Initializing WebSocket connection...");
		connectWebSocket(1);

		return () => {
			console.log("🧹 Cleaning up WebSocket hook");
			disconnectWebSocket();
		};
	}, [enabled, connectWebSocket, disconnectWebSocket]);

	return {
		telemetry,
		isConnected,
		error,
		reconnect: manualReconnect,
		disconnect: disconnectWebSocket,
		reconnectAttempt,
	};
};

export default useTelemetryWebSocket;
