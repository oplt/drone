import droneIconUrl from "../../../../assets/Drone.svg?url";

export function makeMarkerElement(label: string, color: string) {
  const el = document.createElement("div");
  el.textContent = label;
  el.style.width = "26px";
  el.style.height = "26px";
  el.style.borderRadius = "50%";
  el.style.background = "#fff";
  el.style.border = `2px solid ${color}`;
  el.style.color = color;
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.fontSize = "12px";
  el.style.fontWeight = "700";
  el.style.boxShadow = "0 2px 6px rgba(0,0,0,0.24)";
  return el;
}

export function makeDroneMarkerElement() {
  const el = document.createElement("div");
  el.style.width = "40px";
  el.style.height = "40px";
  el.style.filter = "drop-shadow(0 2px 4px rgba(0,0,0,0.35))";

  const img = document.createElement("img");
  img.src = droneIconUrl;
  img.alt = "Drone";
  img.style.width = "40px";
  img.style.height = "40px";
  img.style.display = "block";
  el.appendChild(img);

  return el;
}
