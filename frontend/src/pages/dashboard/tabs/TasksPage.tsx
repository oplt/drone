import { useEffect, useRef, useState, useCallback } from "react";
import { Box, Button, Paper, Stack, Typography, Divider, TextField } from "@mui/material";
import Header from "../components/Header";
import { GoogleMap, LoadScript, Marker, Polyline, OverlayView } from "@react-google-maps/api";
import { getToken } from "../../../auth"; // adjust path if needed
import FlightIcon from "@mui/icons-material/Flight";
import RoomIcon from "@mui/icons-material/Room";   // optional for user marker

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt: number };

const containerStyle = { width: "100%", height: "400px" };

// Default to Brussels as fallback
const defaultCenter = { lat: 50.8503, lng: 4.3517 }; // Brussels

export default function TasksPage() {
  const mapRef = useRef<google.maps.Map | null>(null);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [droneCenter, setDroneCenter] = useState<LatLng | null>(null);
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [alt, setAlt] = useState<number>(30);
  const [name, setName] = useState<string>("mission-1");
  const [sending, setSending] = useState(false);
  const [center, setCenter] = useState<LatLng>(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);
  const [droneConnected, setDroneConnected] = useState(false);

  // Only need one API key variable
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";


  // Initialize map reference callback
  const onMapLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
  }, []);

  // Get user's location on component mount
  useEffect(() => {
    if (!navigator.geolocation) {
      console.warn("Geolocation is not supported by this browser.");
      setLoadingLocation(false);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const userLocation = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        setUserCenter(userLocation);
        setCenter(userLocation);
        setLoadingLocation(false);
      },
      (error) => {
        console.error("Error getting location:", error);
        // Fallback to default center if user denies location or error occurs
        setLoadingLocation(false);
      },
      {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 0,
      }
    );
  }, []);

  /* Poll for drone connection status */
  useEffect(() => {
    let mounted = true;

    const checkDroneConnection = async () => {
      try {
        const res = await fetch("/tasks/home_location");
        if (!res.ok) {
          // If response is not OK, drone is not connected
          if (mounted) {
            setDroneConnected(false);
            setDroneCenter(null);
          }
          return;
        }

        const data = await res.json();

        if (mounted) {
          setDroneConnected(data.connected || false);
          if (data.connected && data.lat !== 0 && data.lon !== 0) {
            setDroneCenter({ lat: data.lat, lng: data.lon });
          } else {
            setDroneCenter(null);
          }
        }
      } catch (error) {
        console.log("Drone not connected yet");
        if (mounted) {
          setDroneConnected(false);
          setDroneCenter(null);
        }
      }
    };

    // Check immediately
    checkDroneConnection();

    // Poll every 3 seconds to check if drone connected
    const interval = setInterval(checkDroneConnection, 3000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  /* Zoom to drone when available */
  useEffect(() => {
    if (!mapRef.current || !droneCenter) return;

    mapRef.current.panTo(droneCenter);
    mapRef.current.setZoom(18);
  }, [droneCenter]);

  const onMapClick = useCallback((e: google.maps.MapMouseEvent) => {
    if (!e.latLng) return;
    const lat = e.latLng.lat();
    const lng = e.latLng.lng();

    setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
  }, [alt]);

  const undo = () => setWaypoints((prev) => prev.slice(0, -1));
  const clear = () => setWaypoints([]);

  const sendMission = async () => {
    const token = getToken();
    if (!token) {
      alert("Not authenticated");
      return;
    }
    if (waypoints.length < 2) {
      alert("Select at least 2 points.");
      return;
    }
    if (!name.trim()) {
      alert("Please enter a mission name.");
      return;
    }

    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/tasks/missions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: name.trim(),
          cruise_alt: alt,
          waypoints,
        }),
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || "Failed to create mission");
      }

      const data = await res.json();
      alert(`Mission created: ${data.id}`);
      // Optionally clear the mission after successful creation
      // clear();
    } catch (err: any) {
      alert(err?.message ?? "Error");
    } finally {
      setSending(false);
    }
  };

  const polylinePath = waypoints.map((p) => ({ lat: p.lat, lng: p.lon }));

  // Determine what to use as map center
  const mapCenter = waypoints.length > 0
    ? { lat: waypoints[0].lat, lng: waypoints[0].lon }
    : (droneCenter || userCenter || center);

  return (
    <>
      <Header />
      <Paper sx={{ width: "100%", p: 2 }}>
        <Typography variant="h4" sx={{ mb: 2 }}>Tasks</Typography>

        {!apiKey ? (
          <Typography color="error" sx={{ mb: 2 }}>
            Missing Google Maps API Key. Please set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
          </Typography>
        ) : (
          <>
            <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 3 }}>
              {/* Left side: Map */}
              <Box sx={{ flex: 1, minHeight: 200 }}>
                {loadingLocation ? (
                  <Box
                    sx={{
                      width: "100%",
                      height: 400,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      bgcolor: "#f5f5f5",
                    }}
                  >
                    <Typography>Loading your location...</Typography>
                  </Box>
                ) : (
                  <LoadScript googleMapsApiKey={apiKey}>
                    <GoogleMap
                      mapContainerStyle={containerStyle}
                      center={mapCenter}
                      zoom={waypoints.length ? 16 : 12}
                      onClick={onMapClick}
                      onLoad={onMapLoad}
                      options={{
                        streetViewControl: false,
                        mapTypeControl: false,
                        fullscreenControl: true,
                      }}
                    >
                      {/* Drone icon - only show when connected */}
                      {droneConnected && droneCenter && (
                        <OverlayView
                          position={droneCenter}
                          mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
                        >
                          <div style={{ transform: "translate(-50%, -50%)", color: "#1976d2" }}>
                            <FlightIcon fontSize="large" />
                          </div>
                        </OverlayView>
                      )}

                      {/* User location icon (optional) */}
                      {userCenter && (
                        <OverlayView
                          position={userCenter}
                          mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
                        >
                          <div style={{ transform: "translate(-50%, -50%)", color: "#4caf50" }}>
                            <RoomIcon fontSize="large" />
                          </div>
                        </OverlayView>
                      )}

                      {waypoints.map((p, idx) => (
                        <Marker
                          key={`${p.lat}-${p.lon}-${idx}`}
                          position={{ lat: p.lat, lng: p.lon }}
                          label={`${idx + 1}`}
                        />
                      ))}

                      {waypoints.length >= 2 && (
                        <Polyline
                          path={polylinePath}
                          options={{
                            strokeColor: "#1976d2",
                            strokeOpacity: 0.8,
                            strokeWeight: 3,
                          }}
                        />
                      )}
                    </GoogleMap>
                  </LoadScript>
                )}
                <Typography variant="body2" sx={{ mt: 1 }}>
                  Click on the map to add waypoints. Markers are ordered (1..N).
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  Drone Status: {droneConnected ? "Connected" : "Disconnected"}
                </Typography>
              </Box>

              {/* Right side: Controls */}
              <Box sx={{ width: { xs: "100%", md: 300 } }}>
                <Stack spacing={2}>
                  <TextField
                    label="Mission name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    size="small"
                    fullWidth
                  />
                  <TextField
                    label="Cruise altitude (m)"
                    type="number"
                    value={alt}
                    onChange={(e) => setAlt(Number(e.target.value))}
                    size="small"
                    fullWidth
                    inputProps={{ min: 1, max: 500 }}
                  />

                  <Typography variant="subtitle2">
                    Waypoints: {waypoints.length}
                  </Typography>

                  <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                    <Button
                      variant="outlined"
                      onClick={undo}
                      disabled={waypoints.length === 0 || sending}
                      fullWidth
                    >
                      Undo Last
                    </Button>
                    <Button
                      variant="outlined"
                      onClick={clear}
                      disabled={waypoints.length === 0 || sending}
                      fullWidth
                      color="error"
                    >
                      Clear All
                    </Button>
                  </Stack>

                  <Button
                    variant="contained"
                    onClick={sendMission}
                    disabled={sending || waypoints.length < 2 || !name.trim()}
                    fullWidth
                    sx={{ mt: 2 }}
                  >
                    {sending ? "Sending..." : "Create Mission"}
                  </Button>
                </Stack>
              </Box>
            </Stack>

            <Divider sx={{ mb: 2 }} />

            {/* Display waypoints list */}
            {waypoints.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Waypoints</Typography>
                <Stack spacing={1}>
                  {waypoints.map((wp, idx) => (
                    <Typography key={idx} variant="body2">
                      {idx + 1}. Lat: {wp.lat.toFixed(6)}, Lon: {wp.lon.toFixed(6)}, Alt: {wp.alt || alt}m
                    </Typography>
                  ))}
                </Stack>
              </Box>
            )}
          </>
        )}
      </Paper>
    </>
  );
}