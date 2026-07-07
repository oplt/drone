# User location normalization

Behavior before `useUserLocation` extraction:

| Consumer | One-shot guard | Timeout | maximumAge | High accuracy | Permission denied | Fallback center | Logging | Visible error |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| Field Survey | ref guard | 5000 ms | 0 | yes | warning only | Brussels | warning | denied hidden; other browser message/default copy |
| Photogrammetry | effect only | 5000 ms | 0 | yes | generic failure | Brussels | error | `Failed to get location: <message>` |
| Private Patrol | effect only | 5000 ms | 0 | yes | generic failure | Brussels | error | `Failed to get location: <message>` |
| Controlled Flight | effect only | 5000 ms | 0 | yes | generic failure | Brussels | none | `Failed to get location: <message>` |
| Animal Farm | effect only | 5000 ms | 0 | yes | generic failure | Brussels | error | `Failed to get location: <message>` |

Normalized behavior: one request per hook mount, fixed browser options, Brussels remains page-owned fallback, and late callbacks after unmount are ignored. Map refs, engines, zoom, overlays, drawing tools, and video state remain outside this hook. One error-policy callback owns domain-specific logging and visible error reporting.
