// Enhanced Dashboard JavaScript
// This file contains all dashboard functionality

// Global state
let dashboardState = {
    map: null,
    charts: {},
    telemetryData: {
        timestamps: [],
        altitude: [],
        latitude: [],
        longitude: [],
        battery: [],
        batteryVoltage: [],
        batteryCurrent: [],
        speed: [],
        heading: []
    },
    currentFlight: null,
    waypoints: [],
    flightPath: null,
    droneMarker: null,
    pollInterval: null,
    maxDataPoints: 50,
    updateFrequency: 2000, // Reduced from 1000ms to 2000ms (2 seconds) - WebSocket handles real-time updates
    isDarkMode: false,
    // Map markers and coordinates
    startMarker: null,
    endMarker: null,
    startCoordinates: null,
    endCoordinates: null,
    isSettingStart: false,
    isSettingEnd: false,
    isAddingWaypoint: false,
    routePolyline: null,
    // Home location tracking
    homeLocation: null,
    hasZoomedToHome: false,
    // Pending telemetry for when map isn't ready yet
    pendingTelemetry: null,
    // New features
    flightStartTime: null,
    lastAltitude: 0,
    lastUpdateTime: null,
    compassCanvas: null,
    compassCtx: null,
    waypointMarkers: [],
    isRecording: false,
    snapshots: [],
    selectedFlightId: null,
    keyboardShortcuts: {}
};

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initDashboard();
});

function initDashboard() {
    initTabs();
    initDarkMode();
    initStatusBar();
    initCharts();
    initCompass();
    // initMap will be called by Google Maps callback, or manually if maps already loaded
    if (typeof google !== 'undefined' && google.maps) {
        initMap();
    }
    initQuickActions();
    initTelemetryPolling();
    initAlertSystem();
    initGraphControls();
    initVideoFeed();
    loadFlightStats();
    // Refresh flight stats periodically (every 30 seconds)
    setInterval(loadFlightStats, 30000);
    initFlightTaskControls();
    checkFlightTaskStatus();
    initMissionPlanning();
    initKeyboardShortcuts();
    initExportFeatures();
    initFlightReplay();
    initBatteryWarnings();
}

// Initialize Flight Task Controls
function initFlightTaskControls() {
    const startForm = document.getElementById('startFlightTaskForm');

    // Before submitting, copy map coordinates into hidden inputs
    startForm?.addEventListener('submit', function(e) {
        if (!dashboardState.startCoordinates || !dashboardState.endCoordinates) {
            e.preventDefault();
            addAlert('error', 'Please set both start and end points on the map');
            return;
        }

        // Sync hidden inputs
        document.getElementById('form_start_lat').value = dashboardState.startCoordinates.lat;
        document.getElementById('form_start_lon').value = dashboardState.startCoordinates.lon;
        document.getElementById('form_start_alt').value = dashboardState.startCoordinates.alt ?? 35.0;

        document.getElementById('form_dest_lat').value = dashboardState.endCoordinates.lat;
        document.getElementById('form_dest_lon').value = dashboardState.endCoordinates.lon;
        document.getElementById('form_dest_alt').value = dashboardState.endCoordinates.alt ?? 35.0;
    });

    // Keep server-driven status checks (still fine)
    setInterval(checkFlightTaskStatus, 5000);
}

// Check Flight Task Status
function checkFlightTaskStatus() {
    fetch('/api/flight/status')
        .then(response => response.json())
        .then(data => {
            updateTaskStatus(data.running);
        })
        .catch(error => {
            console.error('Error checking flight task status:', error);
        });
}

// Update Task Status
function updateTaskStatus(isRunning) {
    const startBtn = document.getElementById('startFlightTaskBtn');
    const stopBtn = document.getElementById('stopFlightTaskBtn');
    const taskStatus = document.getElementById('taskStatus');
    
    if (isRunning) {
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
        if (taskStatus) {
            taskStatus.innerHTML = '<span class="status-indicator status-connected">Running</span>';
        }
    } else {
        // Validate coordinates before enabling start button
        const canStart = dashboardState.startCoordinates && dashboardState.endCoordinates;
        if (startBtn) {
            startBtn.disabled = !canStart;
        }
        if (stopBtn) stopBtn.disabled = true;
        if (taskStatus) {
            taskStatus.innerHTML = '<span class="status-indicator status-disconnected">Not Running</span>';
        }
    }
}

// Load Flight Statistics
function loadFlightStats() {
    fetch('/api/flight/stats')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Flight stats loaded:', data);
            if (data.total_flight_time) {
                const totalTimeEl = document.getElementById('totalFlightTime');
                if (totalTimeEl) {
                    totalTimeEl.textContent = data.total_flight_time;
                }
            }
            if (data.max_altitude !== undefined && data.max_altitude !== null && !isNaN(data.max_altitude)) {
                const maxAltEl = document.getElementById('maxAltitude');
                if (maxAltEl) {
                    maxAltEl.textContent = Math.round(data.max_altitude) + ' m';
                }
            }
            if (data.total_distance !== undefined && data.total_distance !== null && !isNaN(data.total_distance)) {
                const totalDistEl = document.getElementById('totalDistance');
                if (totalDistEl) {
                    totalDistEl.textContent = data.total_distance.toFixed(2) + ' km';
                }
            }
            if (data.max_speed !== undefined && data.max_speed !== null && !isNaN(data.max_speed)) {
                const maxSpeedEl = document.getElementById('maxSpeed');
                if (maxSpeedEl) {
                    maxSpeedEl.textContent = data.max_speed.toFixed(1) + ' m/s';
                }
            }
            if (data.avg_duration !== undefined && data.avg_duration !== null && !isNaN(data.avg_duration)) {
                const avgDurationEl = document.getElementById('avgDuration');
                if (avgDurationEl) {
                    avgDurationEl.textContent = Math.round(data.avg_duration) + ' min';
                }
            }
        })
        .catch(error => {
            console.error('Error loading flight stats:', error);
            // Don't show alert for stats - it's not critical
        });
}

// Tab Navigation (simplified - only Overview and Settings)
function initTabs() {
    // Initialize Tasks toggle
    const tasksToggle = document.getElementById('tasksToggle');
    const tasksGroup = tasksToggle?.closest('.nav-group');
    
    if (tasksToggle && tasksGroup) {
        // Expand Tasks by default since Flight Task is active
        tasksGroup.classList.add('expanded');
        tasksToggle.classList.add('active');
        
        tasksToggle.addEventListener('click', function(e) {
            e.preventDefault();
            tasksGroup.classList.toggle('expanded');
            tasksToggle.classList.toggle('active');
        });
    }
    
    // Handle tab navigation
    const tabLinks = document.querySelectorAll('.sidebar-nav .nav-link[data-tab]');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    tabLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetTab = this.getAttribute('data-tab');
            
            // Update active states
            tabLinks.forEach(l => l.classList.remove('active'));
            tabPanes.forEach(p => {
                p.classList.remove('active');
                p.style.display = 'none';
            });
            
            this.classList.add('active');
            const targetPane = document.getElementById(targetTab + '-tab');
            if (targetPane) {
                targetPane.classList.add('active');
                targetPane.style.display = 'block';
            }
        });
    });
}

// Dark Mode Toggle
function initDarkMode() {
    const toggle = document.getElementById('darkModeToggle');
    const isDark = localStorage.getItem('darkMode') === 'true';
    
    if (isDark) {
        document.body.classList.add('dark-mode');
        dashboardState.isDarkMode = true;
        toggle.innerHTML = '<i class="fas fa-sun"></i> Light Mode';
    }
    
    toggle.addEventListener('click', function() {
        document.body.classList.toggle('dark-mode');
        dashboardState.isDarkMode = !dashboardState.isDarkMode;
        localStorage.setItem('darkMode', dashboardState.isDarkMode);
        
        if (dashboardState.isDarkMode) {
            toggle.innerHTML = '<i class="fas fa-sun"></i> Light Mode';
        } else {
            toggle.innerHTML = '<i class="fas fa-moon"></i> Dark Mode';
        }
    });
}

// Status Bar Updates
function initStatusBar() {
    // Status bar will be updated via telemetry polling
}

function updateStatusBar(telemetry) {
    if (!telemetry) return;
    
    // Vehicle Status
    const vehicleStatus = document.getElementById('vehicleStatus');
    // Update based on armed status (would need to be in telemetry)
    
    // Flight Mode
    const flightModeEl = document.getElementById('flightMode');
    if (telemetry.mode && flightModeEl) {
        flightModeEl.textContent = telemetry.mode;
    }
    
    // Battery with progress bar
    if (telemetry.battery_percentage !== null && telemetry.battery_percentage !== undefined) {
        const batteryPercent = Math.round(telemetry.battery_percentage);
        const batteryPercentEl = document.getElementById('batteryPercent');
        if (batteryPercentEl) {
            batteryPercentEl.textContent = batteryPercent;
        }
        
        // Update progress bar
        const batteryProgress = document.getElementById('batteryProgress');
        if (batteryProgress) {
            batteryProgress.style.width = batteryPercent + '%';
        }
        
        const batteryStatus = document.getElementById('batteryStatus');
        if (batteryPercent < 20) {
            batteryStatus.className = 'status-value status-critical';
            if (batteryProgress) batteryProgress.className = 'battery-progress-fill battery-critical';
        } else if (batteryPercent < 50) {
            batteryStatus.className = 'status-value status-warning';
            if (batteryProgress) batteryProgress.className = 'battery-progress-fill battery-warning';
        } else {
            batteryStatus.className = 'status-value status-normal';
            if (batteryProgress) batteryProgress.className = 'battery-progress-fill battery-normal';
        }
    }
    
    // Flight Time Counter
    if (telemetry.timestamp) {
        updateFlightTimeCounter(telemetry.timestamp);
    }
    
    // Distance from Home
    if (telemetry.latitude && telemetry.longitude && dashboardState.homeLocation) {
        const distance = calculateDistance(
            dashboardState.homeLocation.lat,
            dashboardState.homeLocation.lng,
            telemetry.latitude,
            telemetry.longitude
        );
        const distanceEl = document.getElementById('distanceFromHome');
        if (distanceEl) distanceEl.textContent = distance.toFixed(1);
    }
    
    // GPS (would need GPS data in telemetry)
    // Signal (would need signal data)
}

// Initialize Charts
function initCharts() {
    const chartConfig = {
        type: 'line',
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            plugins: {
                legend: { display: false },
                zoom: {
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x'
                    },
                    pan: {
                        enabled: true,
                        mode: 'x'
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    title: { display: true, text: 'Time' },
                    ticks: { maxTicksLimit: 10 }
                },
                y: {
                    display: true,
                    beginAtZero: false
                }
            }
        }
    };
    
    // Altitude Chart
    dashboardState.charts.altitude = new Chart(
        document.getElementById('altitudeChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Altitude (m)',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1
                }]
            },
            options: {
                ...chartConfig.options,
                scales: {
                    ...chartConfig.options.scales,
                    y: { ...chartConfig.options.scales.y, title: { display: true, text: 'Altitude (m)' } }
                }
            }
        }
    );
    
    // Latitude Chart
    dashboardState.charts.latitude = new Chart(
        document.getElementById('latitudeChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Latitude',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    tension: 0.1
                }]
            }
        }
    );
    
    // Longitude Chart
    dashboardState.charts.longitude = new Chart(
        document.getElementById('longitudeChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Longitude',
                    data: [],
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    tension: 0.1
                }]
            }
        }
    );
    
    // Battery Chart
    dashboardState.charts.battery = new Chart(
        document.getElementById('batteryChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Battery (%)',
                    data: [],
                    borderColor: 'rgb(255, 206, 86)',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                    tension: 0.1
                }]
            },
            options: {
                ...chartConfig.options,
                scales: {
                    ...chartConfig.options.scales,
                    y: { ...chartConfig.options.scales.y, min: 0, max: 100, title: { display: true, text: 'Battery (%)' } }
                }
            }
        }
    );
    
    // Battery Voltage Chart
    dashboardState.charts.batteryVoltage = new Chart(
        document.getElementById('batteryVoltageChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Voltage (V)',
                    data: [],
                    borderColor: 'rgb(153, 102, 255)',
                    backgroundColor: 'rgba(153, 102, 255, 0.2)',
                    tension: 0.1
                }]
            }
        }
    );
    
    // Battery Current Chart
    dashboardState.charts.batteryCurrent = new Chart(
        document.getElementById('batteryCurrentChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Current (A)',
                    data: [],
                    borderColor: 'rgb(255, 159, 64)',
                    backgroundColor: 'rgba(255, 159, 64, 0.2)',
                    tension: 0.1
                }]
            }
        }
    );
    
    // Speed Chart
    dashboardState.charts.speed = new Chart(
        document.getElementById('speedChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Groundspeed',
                        data: [],
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.1
                    }
                ]
            },
            options: {
                ...chartConfig.options,
                plugins: {
                    ...chartConfig.options.plugins,
                    legend: { display: true }
                }
            }
        }
    );
    
    // Heading Chart
    dashboardState.charts.heading = new Chart(
        document.getElementById('headingChart'),
        {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    label: 'Heading (°)',
                    data: [],
                    borderColor: 'rgb(201, 203, 207)',
                    backgroundColor: 'rgba(201, 203, 207, 0.2)',
                    tension: 0.1
                }]
            },
            options: {
                ...chartConfig.options,
                scales: {
                    ...chartConfig.options.scales,
                    y: { ...chartConfig.options.scales.y, min: 0, max: 360, title: { display: true, text: 'Heading (°)' } }
                }
            }
        }
    );
    
    // Combined Overview Chart (Altitude, Speed, Battery)
    const combinedCtx = document.getElementById('combinedChart');
    if (combinedCtx) {
        dashboardState.charts.combined = new Chart(combinedCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Altitude (m)',
                        data: [],
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        yAxisID: 'y',
                        tension: 0.1
                    },
                    {
                        label: 'Speed (m/s)',
                        data: [],
                        borderColor: 'rgb(54, 162, 235)',
                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                        yAxisID: 'y1',
                        tension: 0.1
                    },
                    {
                        label: 'Battery (%)',
                        data: [],
                        borderColor: 'rgb(255, 206, 86)',
                        backgroundColor: 'rgba(255, 206, 86, 0.2)',
                        yAxisID: 'y2',
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 300 },
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: { display: true },
                    zoom: {
                        zoom: {
                            wheel: { enabled: true },
                            pinch: { enabled: true },
                            mode: 'x'
                        },
                        pan: {
                            enabled: true,
                            mode: 'x'
                        }
                    }
                },
                scales: {
                    x: {
                        display: true,
                        title: { display: true, text: 'Time' }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: 'Altitude (m)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: { display: true, text: 'Speed (m/s)' },
                        grid: { drawOnChartArea: false }
                    },
                    y2: {
                        type: 'linear',
                        display: false,
                        position: 'right',
                        title: { display: true, text: 'Battery (%)' },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }
}

// Initialize Compass
function initCompass() {
    const canvas = document.getElementById('compassCanvas');
    if (!canvas) return;
    
    dashboardState.compassCanvas = canvas;
    dashboardState.compassCtx = canvas.getContext('2d');
    drawCompass(0);
}

// Draw Compass
function drawCompass(heading) {
    if (!dashboardState.compassCtx) return;
    
    const ctx = dashboardState.compassCtx;
    const centerX = 50;
    const centerY = 50;
    const radius = 40;
    
    ctx.clearRect(0, 0, 100, 100);
    
    // Draw compass circle
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.stroke();
    
    // Draw cardinal directions
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#333';
    ctx.fillText('N', centerX, centerY - radius + 5);
    ctx.fillText('E', centerX + radius - 5, centerY);
    ctx.fillText('S', centerX, centerY + radius - 5);
    ctx.fillText('W', centerX - radius + 5, centerY);
    
    // Draw heading arrow
    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.rotate((heading * Math.PI) / 180);
    ctx.fillStyle = '#FF0000';
    ctx.beginPath();
    ctx.moveTo(0, -radius);
    ctx.lineTo(-10, 0);
    ctx.lineTo(0, 10);
    ctx.lineTo(10, 0);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
}

// Update Charts with New Data
function updateCharts(telemetry) {
    if (!telemetry) {
        console.warn('updateCharts called with no telemetry data');
        return;
    }
    
    // Update charts even if we don't have position data - use available data
    const timestamp = new Date().toLocaleTimeString();
    
    // Add data points (use defaults for missing values)
    dashboardState.telemetryData.timestamps.push(timestamp);
    dashboardState.telemetryData.altitude.push(telemetry.altitude !== undefined && telemetry.altitude !== null ? telemetry.altitude : 0);
    dashboardState.telemetryData.latitude.push(telemetry.latitude !== undefined && telemetry.latitude !== null ? telemetry.latitude : 0);
    dashboardState.telemetryData.longitude.push(telemetry.longitude !== undefined && telemetry.longitude !== null ? telemetry.longitude : 0);
    dashboardState.telemetryData.battery.push(telemetry.battery_percentage !== undefined && telemetry.battery_percentage !== null ? telemetry.battery_percentage : null);
    dashboardState.telemetryData.batteryVoltage.push(telemetry.battery_voltage !== undefined && telemetry.battery_voltage !== null ? telemetry.battery_voltage : null);
    dashboardState.telemetryData.batteryCurrent.push(telemetry.battery_current !== undefined && telemetry.battery_current !== null ? telemetry.battery_current : null);
    dashboardState.telemetryData.speed.push(telemetry.groundspeed !== undefined && telemetry.groundspeed !== null ? telemetry.groundspeed : 0);
    dashboardState.telemetryData.heading.push(telemetry.heading !== undefined && telemetry.heading !== null ? telemetry.heading : 0);
    
    // Limit data points
    Object.keys(dashboardState.telemetryData).forEach(key => {
        if (dashboardState.telemetryData[key].length > dashboardState.maxDataPoints) {
            dashboardState.telemetryData[key].shift();
        }
    });
    
    // Update all charts with animation for smooth updates
    Object.keys(dashboardState.charts).forEach(chartName => {
        const chart = dashboardState.charts[chartName];
        if (chart && chart.data) {
            // Ensure labels array matches data length
            if (dashboardState.telemetryData.timestamps.length > 0) {
                chart.data.labels = dashboardState.telemetryData.timestamps;
            }
            
            if (chartName === 'combined') {
                // Update combined chart with multiple datasets
                if (chart.data.datasets && chart.data.datasets.length >= 3) {
                    chart.data.datasets[0].data = dashboardState.telemetryData.altitude;
                    chart.data.datasets[1].data = dashboardState.telemetryData.speed;
                    chart.data.datasets[2].data = dashboardState.telemetryData.battery;
                }
            } else {
                const dataKey = chartName === 'batteryVoltage' ? 'batteryVoltage' :
                               chartName === 'batteryCurrent' ? 'batteryCurrent' :
                               chartName === 'speed' ? 'speed' :
                               chartName === 'heading' ? 'heading' :
                               chartName;
                if (chart.data.datasets && chart.data.datasets.length > 0) {
                    chart.data.datasets[0].data = dashboardState.telemetryData[dataKey] || [];
                }
            }
            
            // Use 'none' animation for faster updates, but ensure chart refreshes
            try {
                chart.update('none');
            } catch (error) {
                console.error(`Error updating chart ${chartName}:`, error);
            }
        } else {
            console.warn(`Chart ${chartName} not initialized or missing data`);
        }
    });
}

// Initialize Map (global function for Google Maps callback)
function initMap() {
    // Prevent double initialization
    if (dashboardState.map) {
        return;
    }
    
    if (typeof google === 'undefined' || !google.maps) {
        console.warn('Google Maps not loaded yet');
        return;
    }
    
    // Show loading message while getting location
    const mapElement = document.getElementById('flightMap');
    if (mapElement) {
        mapElement.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; background: #f0f0f0;"><p>Loading map and detecting your location...</p></div>';
    }
    
    // Helper function to initialize map with a center location
    function initializeMapWithCenter(center, zoom = 12) {
        // Clear any loading message
        const mapElement = document.getElementById('flightMap');
        if (mapElement && mapElement.innerHTML.includes('Loading')) {
            mapElement.innerHTML = ''; // Clear loading message
        }
        
        dashboardState.map = new google.maps.Map(mapElement, {
            center: center,
            zoom: zoom,
            mapTypeId: 'roadmap',
            streetViewControl: false,
            fullscreenControl: true
        });
        
        // Initialize map event handlers
        initMapEventHandlers();
        
        // Process any pending telemetry now that map is ready
        if (dashboardState.pendingTelemetry && dashboardState.pendingTelemetry.length > 0) {
            console.log('Map initialized, processing', dashboardState.pendingTelemetry.length, 'pending telemetry updates');
            const pending = dashboardState.pendingTelemetry;
            dashboardState.pendingTelemetry = [];
            // Process the most recent one
            if (pending.length > 0) {
                setTimeout(() => {
                    updateDronePosition(pending[pending.length - 1]);
                }, 100);
            }
        }
    }
    
    // Function to get location from IP as fallback
    function getLocationFromIP(callback) {
        // Try to get approximate location from IP using a free service
        fetch('https://ipapi.co/json/')
            .then(response => response.json())
            .then(data => {
                if (data.latitude && data.longitude) {
                    callback({
                        lat: parseFloat(data.latitude),
                        lng: parseFloat(data.longitude)
                    }, 'ip');
                } else {
                    callback(null, 'ip_failed');
                }
            })
            .catch(error => {
                console.warn('IP geolocation failed:', error);
                callback(null, 'ip_failed');
            });
    }
    
    // Function to initialize map with location
    function initializeWithLocation(location, source) {
        console.log(`Initializing map with location from ${source}:`, location);
        
        // Initialize map with user location
        initializeMapWithCenter(location, 11); // Start with city-level zoom
        
        // Use Geocoding API to get city name and fine-tune zoom
        const geocoder = new google.maps.Geocoder();
        geocoder.geocode({ location: location }, function(results, status) {
            if (status === 'OK' && results && results.length > 0 && results[0].address_components) {
                // Find city-level component
                let cityName = null;
                const components = results[0].address_components || [];
                for (let component of components) {
                    if (component.types && component.types.includes('locality')) {
                        cityName = component.long_name;
                        console.log('City found:', cityName);
                        // Zoom to city level (zoom 12-13 is good for city view)
                        if (dashboardState.map) {
                            dashboardState.map.setZoom(12);
                        }
                        break;
                    } else if (component.types && component.types.includes('administrative_area_level_1') && !cityName) {
                        cityName = component.long_name;
                    }
                }
                
                // If city not found, use administrative area or country
                if (!cityName && components.length > 0) {
                    for (let component of components) {
                        if (component.types && component.types.includes('administrative_area_level_1')) {
                            cityName = component.long_name;
                            break;
                        }
                    }
                }
                
                if (cityName) {
                    console.log(`Map focused on: ${cityName}`);
                }
                
                // Ensure proper zoom level
                if (dashboardState.map) {
                    dashboardState.map.setZoom(12);
                }
            } else {
                console.warn('Geocoding failed, using default zoom');
                if (dashboardState.map) {
                    dashboardState.map.setZoom(12);
                }
            }
        });
    }
    
    // Try to get user location using browser geolocation
    if (navigator.geolocation) {
        console.log('Requesting browser geolocation...');
        
        // Request geolocation with longer timeout and better options
        navigator.geolocation.getCurrentPosition(
            position => {
                const userLocation = {
                    lat: position.coords.latitude,
                    lng: position.coords.longitude
                };
                
                console.log('Browser geolocation successful:', userLocation);
                initializeWithLocation(userLocation, 'browser');
            },
            error => {
                console.warn('Browser geolocation error:', error.message, error.code);
                
                // Error codes:
                // 1 = PERMISSION_DENIED
                // 2 = POSITION_UNAVAILABLE
                // 3 = TIMEOUT
                
                if (error.code === 1) {
                    console.log('Geolocation permission denied, trying IP-based location...');
                } else {
                    console.log('Geolocation unavailable, trying IP-based location...');
                }
                
                // Fallback to IP-based location
                getLocationFromIP(function(location, source) {
                    if (location) {
                        initializeWithLocation(location, source);
                    } else {
                        // Last resort: Use a very wide view that shows most of the world
                        // This is better than defaulting to a specific city
                        console.warn('All location methods failed, using world view');
                        initializeMapWithCenter({ lat: 20, lng: 0 }, 2); // World view
                    }
                });
            },
            {
                enableHighAccuracy: false, // Set to false for faster response
                timeout: 15000, // 15 second timeout (increased)
                maximumAge: 300000 // Accept cached position up to 5 minutes old
            }
        );
    } else {
        // Browser doesn't support geolocation, try IP-based
        console.warn('Geolocation not supported, trying IP-based location...');
        getLocationFromIP(function(location, source) {
            if (location) {
                initializeWithLocation(location, source);
                    } else {
                        // Last resort: World view (better than defaulting to a specific city)
                        console.warn('IP geolocation failed, using world view');
                        initializeMapWithCenter({ lat: 20, lng: 0 }, 2);
                    }
                });
    }
    
    // Set a timeout to ensure map initializes even if all location methods fail
    setTimeout(function() {
        if (!dashboardState.map) {
            console.warn('Map initialization timeout - initializing with world view');
            const mapElement = document.getElementById('flightMap');
            if (mapElement && mapElement.innerHTML.includes('Loading')) {
                initializeMapWithCenter({ lat: 20, lng: 0 }, 2);
            }
        }
    }, 20000); // 20 second timeout
}

// Initialize map event handlers (separated to avoid duplication)
function initMapEventHandlers() {
    if (!dashboardState.map) return;
    
    // Map click handlers for start/end points and waypoints
    dashboardState.map.addListener('click', function(event) {
        if (dashboardState.isAddingWaypoint) {
            const waypoint = {
                lat: event.latLng.lat(),
                lng: event.latLng.lng(),
                alt: 35.0,
                id: Date.now()
            };
            dashboardState.waypoints.push(waypoint);
            addWaypointMarker(waypoint);
            updateWaypointList();
            updateMissionPreview();
            dashboardState.isAddingWaypoint = false;
            const addWaypointBtn = document.getElementById('addWaypointBtn');
            if (addWaypointBtn) {
                addWaypointBtn.classList.remove('active');
            }
            dashboardState.map.setOptions({ cursor: '' });
            return;
        }
        
        if (dashboardState.isSettingStart) {
            setStartPoint(event.latLng);
            dashboardState.isSettingStart = false;
            document.getElementById('setStartBtn')?.classList.remove('active');
        } else if (dashboardState.isSettingEnd) {
            setEndPoint(event.latLng);
            dashboardState.isSettingEnd = false;
            document.getElementById('setEndBtn')?.classList.remove('active');
        }
    });
    
    // Button event listeners for map controls
    document.getElementById('setStartBtn')?.addEventListener('click', function() {
        dashboardState.isSettingStart = !dashboardState.isSettingStart;
        dashboardState.isSettingEnd = false;
        this.classList.toggle('active');
        document.getElementById('setEndBtn')?.classList.remove('active');
        if (dashboardState.isSettingStart) {
            dashboardState.map.setOptions({ cursor: 'crosshair' });
        } else {
            dashboardState.map.setOptions({ cursor: '' });
        }
    });
    
    document.getElementById('setEndBtn')?.addEventListener('click', function() {
        dashboardState.isSettingEnd = !dashboardState.isSettingEnd;
        dashboardState.isSettingStart = false;
        this.classList.toggle('active');
        document.getElementById('setStartBtn')?.classList.remove('active');
        if (dashboardState.isSettingEnd) {
            dashboardState.map.setOptions({ cursor: 'crosshair' });
        } else {
            dashboardState.map.setOptions({ cursor: '' });
        }
    });
    
    document.getElementById('clearRouteBtn')?.addEventListener('click', function() {
        clearRoute();
    });
    
    // Waypoint button
    document.getElementById('addWaypointBtn')?.addEventListener('click', function() {
        dashboardState.isAddingWaypoint = !dashboardState.isAddingWaypoint;
        this.classList.toggle('active');
        if (dashboardState.isAddingWaypoint) {
            dashboardState.isSettingStart = false;
            dashboardState.isSettingEnd = false;
            document.getElementById('setStartBtn')?.classList.remove('active');
            document.getElementById('setEndBtn')?.classList.remove('active');
            dashboardState.map.setOptions({ cursor: 'crosshair' });
        } else {
            dashboardState.map.setOptions({ cursor: '' });
        }
    });
    
    // Initialize task info display
    updateTaskInfo();
}

// Make initMap globally accessible for Google Maps callback
window.initMap = initMap;

// Set Start Point
function setStartPoint(location) {
    // Remove existing start marker
    if (dashboardState.startMarker) {
        dashboardState.startMarker.setMap(null);
    }
    
    // Store coordinates
    dashboardState.startCoordinates = {
        lat: location.lat(),
        lon: location.lng(),
        alt: 35.0 // Default altitude
    };
    
    // Create new start marker (green)
    dashboardState.startMarker = new google.maps.Marker({
        position: location,
        map: dashboardState.map,
        title: 'Start Point',
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: '#28a745',
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 2
        },
        label: {
            text: 'S',
            color: '#ffffff',
            fontWeight: 'bold'
        }
    });
    
    // Update start location info
    getLocationName(location, function(name) {
        const startLocationEl = document.getElementById('startLocation');
        if (startLocationEl) {
            startLocationEl.textContent = name;
        }
        updateTaskInfo();
    });
    
    // Draw route if end point exists
    if (dashboardState.endMarker) {
        drawRoute(dashboardState.startMarker.getPosition(), dashboardState.endMarker.getPosition());
    }
}

// Set End Point
function setEndPoint(location) {
    // Remove existing end marker
    if (dashboardState.endMarker) {
        dashboardState.endMarker.setMap(null);
    }
    
    // Store coordinates
    dashboardState.endCoordinates = {
        lat: location.lat(),
        lon: location.lng(),
        alt: 35.0 // Default altitude
    };
    
    // Create new end marker (red)
    dashboardState.endMarker = new google.maps.Marker({
        position: location,
        map: dashboardState.map,
        title: 'End Point',
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: '#dc3545',
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 2
        },
        label: {
            text: 'E',
            color: '#ffffff',
            fontWeight: 'bold'
        }
    });
    
    // Update end location info
    getLocationName(location, function(name) {
        const endLocationEl = document.getElementById('endLocation');
        if (endLocationEl) {
            endLocationEl.textContent = name;
        }
        updateTaskInfo();
    });
    
    // Draw route if start point exists
    if (dashboardState.startMarker) {
        drawRoute(dashboardState.startMarker.getPosition(), dashboardState.endMarker.getPosition());
    }
}

// Draw Route
function drawRoute(start, end) {
    // Remove existing route
    if (dashboardState.routePolyline) {
        if (dashboardState.routePolyline.setDirections) {
            dashboardState.routePolyline.setDirections({ routes: [] });
            dashboardState.routePolyline.setMap(null);
        } else {
            dashboardState.routePolyline.setMap(null);
        }
    }
    
    // Create route using Directions Service
    const directionsService = new google.maps.DirectionsService();
    const directionsRenderer = new google.maps.DirectionsRenderer({
        map: dashboardState.map,
        suppressMarkers: true
    });
    
    directionsService.route({
        origin: start,
        destination: end,
        travelMode: 'DRIVING'
    }, function(response, status) {
        if (status === 'OK') {
            directionsRenderer.setDirections(response);
            dashboardState.routePolyline = directionsRenderer;
        } else {
            console.error('Directions request failed:', status);
            // Fallback: draw straight line
            dashboardState.routePolyline = new google.maps.Polyline({
                path: [start, end],
                geodesic: true,
                strokeColor: '#FF0000',
                strokeOpacity: 0.8,
                strokeWeight: 3,
                map: dashboardState.map
            });
        }
    });
}

// Clear Route
function clearRoute() {
    if (dashboardState.startMarker) {
        dashboardState.startMarker.setMap(null);
        dashboardState.startMarker = null;
    }
    if (dashboardState.endMarker) {
        dashboardState.endMarker.setMap(null);
        dashboardState.endMarker = null;
    }
    if (dashboardState.routePolyline) {
        if (dashboardState.routePolyline.setDirections) {
            dashboardState.routePolyline.setDirections({ routes: [] });
            dashboardState.routePolyline.setMap(null);
        } else {
            dashboardState.routePolyline.setMap(null);
        }
        dashboardState.routePolyline = null;
    }
    
    dashboardState.startCoordinates = null;
    dashboardState.endCoordinates = null;
    
    const startLocationEl = document.getElementById('startLocation');
    const endLocationEl = document.getElementById('endLocation');
    if (startLocationEl) startLocationEl.textContent = 'Not set';
    if (endLocationEl) endLocationEl.textContent = 'Not set';
    
    dashboardState.isSettingStart = false;
    dashboardState.isSettingEnd = false;
    document.getElementById('setStartBtn')?.classList.remove('active');
    document.getElementById('setEndBtn')?.classList.remove('active');
    dashboardState.map.setOptions({ cursor: '' });
    updateTaskInfo();
}

// Get Location Name
function getLocationName(location, callback) {
    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ location: location }, function(results, status) {
        if (status === 'OK' && results && results.length > 0 && results[0].formatted_address) {
            callback(results[0].formatted_address);
        } else {
            callback(location.lat().toFixed(6) + ', ' + location.lng().toFixed(6));
        }
    });
}

// Update Task Info
function updateTaskInfo() {
    const taskInfo = document.getElementById('taskInfo');
    const taskStartInfo = document.getElementById('taskStartInfo');
    const taskEndInfo = document.getElementById('taskEndInfo');
    
    if (dashboardState.startCoordinates) {
        if (taskStartInfo) {
            taskStartInfo.textContent = `${dashboardState.startCoordinates.lat.toFixed(6)}, ${dashboardState.startCoordinates.lon.toFixed(6)}`;
        }
        if (taskInfo) taskInfo.style.display = 'block';
    }
    
    if (dashboardState.endCoordinates) {
        if (taskEndInfo) {
            taskEndInfo.textContent = `${dashboardState.endCoordinates.lat.toFixed(6)}, ${dashboardState.endCoordinates.lon.toFixed(6)}`;
        }
        if (taskInfo) taskInfo.style.display = 'block';
    }
    
    // Enable/disable start button
    const startBtn = document.getElementById('startFlightTaskBtn');
    if (startBtn) {
        if (dashboardState.startCoordinates && dashboardState.endCoordinates) {
            startBtn.disabled = false;
        } else {
            startBtn.disabled = true;
        }
    }
}

// Update Map with Drone Position
function updateDronePosition(telemetry) {
    // Validate inputs
    if (!telemetry) {
        console.warn('updateDronePosition: No telemetry data');
        return;
    }
    
    // Validate position data - be more lenient, only reject truly invalid data
    const lat = parseFloat(telemetry.latitude);
    const lng = parseFloat(telemetry.longitude);
    
    if (isNaN(lat) || isNaN(lng) || 
        lat < -90 || lat > 90 || 
        lng < -180 || lng > 180 ||
        (lat === 0 && lng === 0)) {
        console.warn('updateDronePosition: Invalid position data', { lat, lng, telemetry });
        return;
    }
    
    // Ensure map is initialized
    if (!dashboardState.map) {
        console.warn('updateDronePosition: Map not initialized yet, will retry on next update');
        // Store telemetry for when map is ready
        if (!dashboardState.pendingTelemetry) {
            dashboardState.pendingTelemetry = [];
        }
        dashboardState.pendingTelemetry.push(telemetry);
        return;
    }
    
    // Process any pending telemetry now that map is ready
    if (dashboardState.pendingTelemetry && dashboardState.pendingTelemetry.length > 0) {
        console.log('Processing', dashboardState.pendingTelemetry.length, 'pending telemetry updates');
        const pending = dashboardState.pendingTelemetry;
        dashboardState.pendingTelemetry = [];
        // Process the most recent one
        if (pending.length > 0) {
            updateDronePosition(pending[pending.length - 1]);
        }
    }
    
    const position = new google.maps.LatLng(lat, lng);
    
    // Set home location on first telemetry update (when drone connects)
    if (!dashboardState.homeLocation) {
        dashboardState.homeLocation = {
            lat: lat,
            lng: lng
        };
        console.log('Home location set from first telemetry:', dashboardState.homeLocation);
        
        // Zoom to home location when drone first connects
        if (!dashboardState.hasZoomedToHome) {
            zoomToHomeLocation();
        }
    }
    
    // Create or update drone marker
    if (!dashboardState.droneMarker) {
        console.log('Creating drone marker at:', position.lat(), position.lng());
        dashboardState.droneMarker = new google.maps.Marker({
            position: position,
            map: dashboardState.map,
            icon: {
                path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                scale: 5,
                rotation: telemetry.heading || 0,
                fillColor: '#FF0000',
                fillOpacity: 1,
                strokeColor: '#FFFFFF',
                strokeWeight: 2
            },
            title: 'Drone Position',
            zIndex: 1000 // Ensure marker is on top
        });
    } else {
        // Update existing marker position
        dashboardState.droneMarker.setPosition(position);
        // Update heading/rotation
        if (telemetry.heading !== undefined && !isNaN(telemetry.heading)) {
            dashboardState.droneMarker.setIcon({
                path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                scale: 5,
                rotation: telemetry.heading,
                fillColor: '#FF0000',
                fillOpacity: 1,
                strokeColor: '#FFFFFF',
                strokeWeight: 2
            });
        }
    }
    
    // Update flight path
    if (!dashboardState.flightPath) {
        console.log('Creating flight path at:', lat, lng);
        dashboardState.flightPath = new google.maps.Polyline({
            path: [position],
            geodesic: true,
            strokeColor: '#FF0000',
            strokeOpacity: 1.0, // Full opacity for better visibility
            strokeWeight: 4, // Thicker line
            map: dashboardState.map,
            zIndex: 500,
            visible: true
        });
        console.log('Flight path created with', dashboardState.flightPath.getPath().getLength(), 'points');
    } else {
        // Get current path and add new position
        const path = dashboardState.flightPath.getPath();
        
        // Check if position has changed significantly (avoid duplicate points)
        const lastPoint = path.getAt(path.getLength() - 1);
        if (lastPoint) {
            let distance = 0;
            // Use geometry library if available, otherwise use simple haversine
            if (google.maps.geometry && google.maps.geometry.spherical) {
                distance = google.maps.geometry.spherical.computeDistanceBetween(
                    lastPoint,
                    position
                );
            } else {
                // Fallback: simple distance calculation
                const lat1 = lastPoint.lat();
                const lng1 = lastPoint.lng();
                const lat2 = position.lat();
                const lng2 = position.lng();
                const R = 6371000; // Earth radius in meters
                const dLat = (lat2 - lat1) * Math.PI / 180;
                const dLng = (lng2 - lng1) * Math.PI / 180;
                const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                          Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                          Math.sin(dLng/2) * Math.sin(dLng/2);
                const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                distance = R * c;
            }
            // Only add point if moved more than 0.5 meters (more sensitive)
            if (distance < 0.5) {
                // Still update marker position even if path doesn't change
                return; // Skip path update if position hasn't changed much
            }
        }
        
        // Add new position to path
        path.push(position);
        console.log('Flight path updated, now has', path.getLength(), 'points');
        
        // Limit path length to prevent memory issues (keep last 2000 points)
        if (path.getLength() > 2000) {
            // Remove oldest points, keep last 2000
            const removeCount = path.getLength() - 2000;
            for (let i = 0; i < removeCount; i++) {
                path.removeAt(0);
            }
        }
        
        // Ensure path is visible
        dashboardState.flightPath.setOptions({
            visible: true,
            strokeOpacity: 1.0
        });
    }
    
    // Center map on drone (but don't zoom out if we've zoomed to home)
    if (dashboardState.hasZoomedToHome) {
        // Only pan to drone, don't change zoom (keep zoom level from home location)
        dashboardState.map.panTo(position);
    } else {
        // First update - if we have home location, zoom to it first
        if (dashboardState.homeLocation) {
            zoomToHomeLocation();
            // Then center on current drone position
            dashboardState.map.panTo(position);
        } else {
            // No home location yet, just center on drone with reasonable zoom
            dashboardState.map.setCenter(position);
            dashboardState.map.setZoom(15); // Close zoom for drone operations
        }
    }
}

// Zoom to home location
function zoomToHomeLocation() {
    if (!dashboardState.map || !dashboardState.homeLocation) {
        return;
    }
    
    console.log('Zooming to home location:', dashboardState.homeLocation);
    
    // Zoom to home location with appropriate zoom level
    dashboardState.map.setCenter(dashboardState.homeLocation);
    dashboardState.map.setZoom(16); // Close zoom to see drone operations clearly
    
    dashboardState.hasZoomedToHome = true;
    
    // Add a home marker if it doesn't exist
    if (!dashboardState.homeMarker) {
        dashboardState.homeMarker = new google.maps.Marker({
            position: dashboardState.homeLocation,
            map: dashboardState.map,
            title: 'Home Location',
            icon: {
                path: google.maps.SymbolPath.CIRCLE,
                scale: 8,
                fillColor: '#00FF00',
                fillOpacity: 0.8,
                strokeColor: '#FFFFFF',
                strokeWeight: 2
            },
            label: {
                text: 'H',
                color: '#FFFFFF',
                fontWeight: 'bold'
            }
        });
    }
}

// Quick Actions
function initQuickActions() {
    document.getElementById('armBtn')?.addEventListener('click', () => sendCommand('ARM'));
    document.getElementById('disarmBtn')?.addEventListener('click', () => sendCommand('DISARM'));
    document.getElementById('takeoffBtn')?.addEventListener('click', () => sendCommand('TAKEOFF'));
    document.getElementById('landBtn')?.addEventListener('click', () => sendCommand('LAND'));
    document.getElementById('rtlBtn')?.addEventListener('click', () => sendCommand('RTL'));
    document.getElementById('holdBtn')?.addEventListener('click', () => sendCommand('HOLD'));
    document.getElementById('emergencyStopBtn')?.addEventListener('click', () => sendCommand('EMERGENCY_STOP'));
}

function sendCommand(command) {
    // Send command to backend
    fetch('/api/commands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: command })
    })
    .then(response => response.json())
    .then(data => {
        addAlert('success', `Command sent: ${command}`);
        addToCommandHistory(command);
    })
    .catch(error => {
        addAlert('error', `Failed to send command: ${error.message}`);
    });
}

function addToCommandHistory(command) {
    const history = document.getElementById('commandHistory');
    const item = document.createElement('div');
    item.className = 'command-item';
    item.textContent = `${new Date().toLocaleTimeString()} - ${command}`;
    history.insertBefore(item, history.firstChild);
    
    // Limit history
    while (history.children.length > 50) {
        history.removeChild(history.lastChild);
    }
}

// Socket.IO Connection
let socket = null;
let socketConnected = false;

function initSocketIO() {
    // Connect to Socket.IO server with reconnection options
    socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: Infinity,
        timeout: 20000,
    });
    
    socket.on('connect', function() {
        console.log('Connected to telemetry stream');
        socketConnected = true;
        // Clear any error alerts on successful connection
        addAlert('success', 'Connected to real-time telemetry');
        
        // Request initial telemetry
        socket.emit('request_telemetry');
    });
    
    socket.on('disconnect', function(reason) {
        console.log('Disconnected from telemetry stream:', reason);
        socketConnected = false;
        if (reason === 'io server disconnect') {
            // Server disconnected, reconnect manually
            socket.connect();
        } else {
            addAlert('warning', 'Disconnected from telemetry stream - using fallback polling');
        }
    });
    
    socket.on('connect_error', function(error) {
        console.error('Socket.IO connection error:', error);
        socketConnected = false;
    });
    
    socket.on('telemetry_update', function(data) {
        // Update dashboard with real-time telemetry (only if WebSocket is connected)
        if (socketConnected && data && data.telemetry) {
            console.log('Telemetry update received:', data.telemetry);
            
            // Validate telemetry data has at least some fields
            if (!data.telemetry.latitude && !data.telemetry.longitude && !data.telemetry.altitude) {
                console.warn('Telemetry update has no position data, skipping chart update');
                // Still update status bar and panel with available data
                if (data.telemetry.mode || data.telemetry.battery_percentage !== undefined) {
                    updateStatusBar(data.telemetry);
                    updateTelemetryPanel(data.telemetry);
                }
                return;
            }
            
            updateStatusBar(data.telemetry);
            updateCharts(data.telemetry);
            updateTelemetryPanel(data.telemetry);
            updateDronePosition(data.telemetry);
            
            // Update compass
            if (data.telemetry.heading !== undefined && data.telemetry.heading !== null) {
                drawCompass(data.telemetry.heading);
            }
            
            // If home location is provided in the data, use it
            if (data.home_location && !dashboardState.homeLocation) {
                dashboardState.homeLocation = {
                    lat: data.home_location.lat,
                    lng: data.home_location.lon
                };
                console.log('Home location received from server:', dashboardState.homeLocation);
                
                // Zoom to home location if not already zoomed
                if (!dashboardState.hasZoomedToHome && dashboardState.map) {
                    zoomToHomeLocation();
                }
            }
        } else {
            console.warn('Telemetry update skipped - socketConnected:', socketConnected, 'hasData:', !!data, 'hasTelemetry:', !!(data && data.telemetry));
        }
    });
}

// Telemetry Polling (fallback if WebSocket fails)
function initTelemetryPolling() {
    loadTelemetryHistory();
    
    // Try WebSocket first (preferred method)
    if (typeof io !== 'undefined') {
        initSocketIO();
        // Use slower polling as backup only (every 5 seconds)
        dashboardState.pollInterval = setInterval(fetchTelemetry, 5000);
    } else {
        // Fallback to polling only (slower frequency to reduce load)
        fetchTelemetry();
        dashboardState.pollInterval = setInterval(fetchTelemetry, dashboardState.updateFrequency);
    }
}

async function fetchTelemetry() {
    // Skip polling if WebSocket is connected (reduces server load)
    if (socketConnected) {
        return;
    }
    
    try {
        const response = await fetch('/api/telemetry/latest');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        if (data.telemetry) {
            console.log('Telemetry fetched via polling:', data.telemetry);
            
            // Validate telemetry data has at least some fields
            if (!data.telemetry.latitude && !data.telemetry.longitude && !data.telemetry.altitude) {
                console.warn('Polling telemetry has no position data, updating status only');
                // Still update status bar and panel with available data
                if (data.telemetry.mode || data.telemetry.battery_percentage !== undefined) {
                    updateStatusBar(data.telemetry);
                    updateTelemetryPanel(data.telemetry);
                }
                return;
            }
            
            updateStatusBar(data.telemetry);
            updateCharts(data.telemetry);
            updateTelemetryPanel(data.telemetry);
            updateDronePosition(data.telemetry);
            
            // Update compass
            if (data.telemetry.heading !== undefined && data.telemetry.heading !== null) {
                drawCompass(data.telemetry.heading);
            }
            
            // If home location is provided in the data, use it
            if (data.home_location && !dashboardState.homeLocation) {
                dashboardState.homeLocation = {
                    lat: data.home_location.lat,
                    lng: data.home_location.lon
                };
                console.log('Home location received from polling:', dashboardState.homeLocation);
                
                // Zoom to home location if not already zoomed
                if (!dashboardState.hasZoomedToHome && dashboardState.map) {
                    zoomToHomeLocation();
                }
            }
        } else {
            console.warn('No telemetry data in polling response:', data);
        }
    } catch (error) {
        console.error('Error fetching telemetry:', error);
        // Only show error if WebSocket is also disconnected
        if (!socketConnected) {
            console.warn('Both WebSocket and polling failed - telemetry updates may be delayed');
        }
    }
}

async function loadTelemetryHistory() {
    try {
        const response = await fetch('/api/telemetry/history?limit=50');
        const data = await response.json();
        
        if (data.data && data.data.timestamps) {
            const timestamps = data.data.timestamps.map(ts => {
                return new Date(ts).toLocaleTimeString();
            });
            
            dashboardState.telemetryData.timestamps = timestamps;
            dashboardState.telemetryData.altitude = data.data.altitude || [];
            dashboardState.telemetryData.latitude = data.data.latitude || [];
            dashboardState.telemetryData.longitude = data.data.longitude || [];
            dashboardState.telemetryData.battery = data.data.battery_percentage || [];
            
            // Update charts with historical data
            Object.keys(dashboardState.charts).forEach(chartName => {
                const chart = dashboardState.charts[chartName];
                if (chart) {
                    chart.data.labels = dashboardState.telemetryData.timestamps;
                    const dataKey = chartName === 'batteryVoltage' ? 'batteryVoltage' :
                                   chartName === 'batteryCurrent' ? 'batteryCurrent' :
                                   chartName === 'speed' ? 'speed' :
                                   chartName === 'heading' ? 'heading' :
                                   chartName;
                    chart.data.datasets[0].data = dashboardState.telemetryData[dataKey] || [];
                    chart.update();
                }
            });
        }
    } catch (error) {
        console.error('Error loading telemetry history:', error);
    }
}

// Update Telemetry Panel - Enhanced version with all new features
function updateTelemetryPanel(telemetry) {
    if (!telemetry) return;
    
    // Update all telemetry values with null checks
    const airspeedEl = document.getElementById('airspeedValue');
    const groundspeedEl = document.getElementById('groundspeedValue');
    const altitudeEl = document.getElementById('altitudeValue');
    const headingEl = document.getElementById('headingValue');
    const batteryVoltageEl = document.getElementById('batteryVoltage');
    const batteryCurrentEl = document.getElementById('batteryCurrent');
    const estimatedFlightTimeEl = document.getElementById('estimatedFlightTime');
    const homeDistanceEl = document.getElementById('homeDistance');
    const waypointDistanceEl = document.getElementById('waypointDistance');
    const batteryPercentValueEl = document.getElementById('batteryPercentValue');
    const batteryVoltageValueEl = document.getElementById('batteryVoltageValue');
    const gpsSatCountValueEl = document.getElementById('gpsSatCountValue');
    
    if (airspeedEl) airspeedEl.textContent = (telemetry.groundspeed || 0).toFixed(1);
    if (groundspeedEl) groundspeedEl.textContent = (telemetry.groundspeed || 0).toFixed(1);
    if (altitudeEl) altitudeEl.textContent = (telemetry.altitude || 0).toFixed(1);
    if (headingEl) {
        const heading = Math.round(telemetry.heading || 0);
        headingEl.textContent = heading + '°';
        drawCompass(heading);
    }
    if (batteryVoltageEl) batteryVoltageEl.textContent = (telemetry.battery_voltage || 0).toFixed(2);
    if (batteryCurrentEl) batteryCurrentEl.textContent = (telemetry.battery_current || 0).toFixed(2);
    if (batteryPercentValueEl) batteryPercentValueEl.textContent = Math.round(telemetry.battery_percentage || 0) + '%';
    if (batteryVoltageValueEl) batteryVoltageValueEl.textContent = (telemetry.battery_voltage || 0).toFixed(1) + 'V';
    
    // Update altitude trend
    if (dashboardState.lastAltitude !== undefined && dashboardState.lastUpdateTime) {
        const timeDiff = (new Date(telemetry.timestamp || Date.now()) - dashboardState.lastUpdateTime) / 1000;
        const altDiff = (telemetry.altitude || 0) - dashboardState.lastAltitude;
        const trend = altDiff / timeDiff;
        
        const trendEl = document.getElementById('altitudeTrend');
        if (trendEl && !isNaN(trend) && isFinite(trend)) {
            const icon = trend >= 0 ? 'fa-arrow-up' : 'fa-arrow-down';
            const color = trend >= 0 ? '#28a745' : '#dc3545';
            trendEl.innerHTML = `<i class="fas ${icon}"></i> ${Math.abs(trend).toFixed(1)} m/s`;
            trendEl.style.color = color;
        }
    }
    
    dashboardState.lastAltitude = telemetry.altitude || 0;
    dashboardState.lastUpdateTime = new Date(telemetry.timestamp || Date.now());
    
    // Calculate distance from home
    if (homeDistanceEl && telemetry.latitude && telemetry.longitude && dashboardState.homeLocation) {
        const distance = calculateDistance(
            dashboardState.homeLocation.lat,
            dashboardState.homeLocation.lng,
            telemetry.latitude,
            telemetry.longitude
        );
        homeDistanceEl.textContent = distance.toFixed(1);
    }
    
    // Calculate estimated flight time (simplified)
    if (estimatedFlightTimeEl && telemetry.battery_percentage && telemetry.battery_current) {
        const estimatedMinutes = Math.round((telemetry.battery_percentage / 100) * 20); // Rough estimate
        estimatedFlightTimeEl.textContent = 
            `${Math.floor(estimatedMinutes / 60)}:${String(estimatedMinutes % 60).padStart(2, '0')}`;
    }
    
    // Update battery icon
    const batteryIcon = document.getElementById('batteryIcon');
    if (batteryIcon && telemetry.battery_percentage !== null) {
        const percent = telemetry.battery_percentage;
        if (percent > 75) {
            batteryIcon.className = 'fas fa-battery-full';
        } else if (percent > 50) {
            batteryIcon.className = 'fas fa-battery-three-quarters';
        } else if (percent > 25) {
            batteryIcon.className = 'fas fa-battery-half';
        } else if (percent > 10) {
            batteryIcon.className = 'fas fa-battery-quarter';
        } else {
            batteryIcon.className = 'fas fa-battery-empty';
        }
    }
}

// Alert System
function initAlertSystem() {
    // Alert system initialized
}

function addAlert(type, message) {
    const alertPanel = document.getElementById('alertPanel');
    const alertList = document.getElementById('alertList');
    
    alertPanel.style.display = 'block';
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type === 'error' ? 'danger' : type}`;
    alert.innerHTML = `
        <span>${message}</span>
        <button class="btn btn-sm btn-link" onclick="this.parentElement.remove(); checkAlertsEmpty();">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    alertList.insertBefore(alert, alertList.firstChild);
    
    // Limit alerts
    while (alertList.children.length > 10) {
        alertList.removeChild(alertList.lastChild);
    }
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (alert.parentElement) {
            alert.remove();
            checkAlertsEmpty();
        }
    }, 5000);
}

function clearAlerts() {
    const alertList = document.getElementById('alertList');
    if (alertList) {
        alertList.innerHTML = '';
    }
    checkAlertsEmpty();
}

function checkAlertsEmpty() {
    const alertList = document.getElementById('alertList');
    const alertPanel = document.getElementById('alertPanel');
    if (alertList && alertList.children.length === 0 && alertPanel) {
        alertPanel.style.display = 'none';
    }
}

// Graph Controls
function initGraphControls() {
    document.getElementById('timeRangeSelector')?.addEventListener('change', function() {
        const range = this.value;
        // Filter data based on time range
        // Implementation would filter dashboardState.telemetryData
    });
    
    document.getElementById('exportGraphsBtn')?.addEventListener('click', function() {
        // Export graphs as images or data
        exportGraphs();
    });
}

function exportGraphs() {
    // Export functionality
    alert('Export functionality coming soon');
}

// Video Feed Initialization
function initVideoFeed() {
    fetch('/api/video/stream')
        .then(response => response.json())
        .then(data => {
            if (data.stream_url) {
                const videoFeed = document.getElementById('videoFeed');
                if (videoFeed) {
                    videoFeed.innerHTML = `
                        <video id="droneVideo" width="100%" height="auto" controls autoplay muted>
                            <source src="${data.stream_url}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    `;
                }
            } else {
                const videoFeed = document.getElementById('videoFeed');
                if (videoFeed) {
                    videoFeed.innerHTML = `
                        <div class="video-placeholder">
                            <i class="fas fa-video fa-3x"></i>
                            <p>Video stream not available</p>
                        </div>
                    `;
                }
            }
        })
        .catch(error => {
            console.error('Error loading video stream:', error);
            const videoFeed = document.getElementById('videoFeed');
            if (videoFeed) {
                videoFeed.innerHTML = `
                    <div class="video-placeholder">
                        <i class="fas fa-exclamation-triangle fa-3x"></i>
                        <p>Error loading video feed</p>
                    </div>
                `;
            }
        });
    
    // Initialize video controls
    document.getElementById('startRecordingBtn')?.addEventListener('click', startRecording);
    document.getElementById('stopRecordingBtn')?.addEventListener('click', stopRecording);
    document.getElementById('takeSnapshotBtn')?.addEventListener('click', takeSnapshot);
    document.getElementById('pipModeBtn')?.addEventListener('click', togglePIPMode);
    document.getElementById('videoQualitySelect')?.addEventListener('change', changeVideoQuality);
}

// Start Recording
function startRecording() {
    dashboardState.isRecording = true;
    const startBtn = document.getElementById('startRecordingBtn');
    const stopBtn = document.getElementById('stopRecordingBtn');
    const statusEl = document.getElementById('recordingStatus');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;
    if (statusEl) statusEl.style.display = 'inline-flex';
    addAlert('info', 'Recording started');
}

// Stop Recording
function stopRecording() {
    dashboardState.isRecording = false;
    const startBtn = document.getElementById('startRecordingBtn');
    const stopBtn = document.getElementById('stopRecordingBtn');
    const statusEl = document.getElementById('recordingStatus');
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
    if (statusEl) statusEl.style.display = 'none';
    addAlert('info', 'Recording stopped');
}

// Take Snapshot
function takeSnapshot() {
    const video = document.getElementById('droneVideo');
    if (!video || video.readyState !== 4) {
        addAlert('warning', 'Video not ready');
        return;
    }
    
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    
    const dataURL = canvas.toDataURL('image/png');
    const snapshot = {
        id: Date.now(),
        dataURL: dataURL,
        timestamp: new Date().toISOString()
    };
    
    dashboardState.snapshots.push(snapshot);
    updateSnapshotGallery();
    addAlert('success', 'Snapshot captured');
}

// Update Snapshot Gallery
function updateSnapshotGallery() {
    const gallery = document.getElementById('snapshotGallery');
    const list = document.getElementById('snapshotList');
    
    if (!gallery || !list) return;
    
    if (dashboardState.snapshots.length === 0) {
        gallery.style.display = 'none';
        return;
    }
    
    gallery.style.display = 'block';
    list.innerHTML = '';
    
    dashboardState.snapshots.forEach(snapshot => {
        const item = document.createElement('div');
        item.className = 'snapshot-item';
        item.innerHTML = `<img src="${snapshot.dataURL}" alt="Snapshot ${new Date(snapshot.timestamp).toLocaleTimeString()}">`;
        item.addEventListener('click', () => {
            // Open full size in new window
            const newWindow = window.open();
            newWindow.document.write(`<img src="${snapshot.dataURL}" style="max-width: 100%; height: auto;">`);
        });
        list.appendChild(item);
    });
}

// Toggle PIP Mode
function togglePIPMode() {
    const video = document.getElementById('droneVideo');
    if (!video) return;
    
    if (video.requestPictureInPicture) {
        if (document.pictureInPictureElement) {
            document.exitPictureInPicture();
            addAlert('info', 'Exited picture-in-picture mode');
        } else {
            video.requestPictureInPicture();
            addAlert('info', 'Entered picture-in-picture mode');
        }
    } else {
        addAlert('warning', 'Picture-in-picture not supported by your browser');
    }
}

// Change Video Quality
function changeVideoQuality() {
    const select = document.getElementById('videoQualitySelect');
    const quality = select.value;
    addAlert('info', `Video quality set to ${quality}`);
    // TODO: Implement actual quality change
}


// Calculate Distance (Haversine formula)
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; // Earth radius in meters
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

// Update Flight Time Counter
function updateFlightTimeCounter(timestamp) {
    if (!dashboardState.flightStartTime) {
        dashboardState.flightStartTime = new Date(timestamp);
    }
    
    const now = new Date(timestamp);
    const elapsed = Math.floor((now - dashboardState.flightStartTime) / 1000);
    
    const hours = Math.floor(elapsed / 3600);
    const minutes = Math.floor((elapsed % 3600) / 60);
    const seconds = elapsed % 60;
    
    const timeString = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    
    const flightTimeEl = document.getElementById('flightTimeCounter');
    if (flightTimeEl) flightTimeEl.textContent = timeString;
    
    const flightTimeValueEl = document.getElementById('flightTime');
    if (flightTimeValueEl) flightTimeValueEl.textContent = timeString;
}

// Update Telemetry Panel with enhanced features
function updateTelemetryPanel(telemetry) {
    if (!telemetry) return;
    
    // Update all telemetry values with null checks
    const airspeedEl = document.getElementById('airspeedValue');
    const groundspeedEl = document.getElementById('groundspeedValue');
    const altitudeEl = document.getElementById('altitudeValue');
    const headingEl = document.getElementById('headingValue');
    const batteryVoltageEl = document.getElementById('batteryVoltage');
    const batteryCurrentEl = document.getElementById('batteryCurrent');
    const estimatedFlightTimeEl = document.getElementById('estimatedFlightTime');
    const homeDistanceEl = document.getElementById('homeDistance');
    const waypointDistanceEl = document.getElementById('waypointDistance');
    const batteryPercentValueEl = document.getElementById('batteryPercentValue');
    const batteryVoltageValueEl = document.getElementById('batteryVoltageValue');
    const gpsSatCountValueEl = document.getElementById('gpsSatCountValue');
    
    if (airspeedEl) airspeedEl.textContent = (telemetry.groundspeed || 0).toFixed(1);
    if (groundspeedEl) groundspeedEl.textContent = (telemetry.groundspeed || 0).toFixed(1);
    if (altitudeEl) altitudeEl.textContent = (telemetry.altitude || 0).toFixed(1);
    if (headingEl) {
        const heading = Math.round(telemetry.heading || 0);
        headingEl.textContent = heading + '°';
        drawCompass(heading);
    }
    if (batteryVoltageEl) batteryVoltageEl.textContent = (telemetry.battery_voltage || 0).toFixed(2);
    if (batteryCurrentEl) batteryCurrentEl.textContent = (telemetry.battery_current || 0).toFixed(2);
    if (batteryPercentValueEl) batteryPercentValueEl.textContent = Math.round(telemetry.battery_percentage || 0) + '%';
    if (batteryVoltageValueEl) batteryVoltageValueEl.textContent = (telemetry.battery_voltage || 0).toFixed(1) + 'V';
    
    // Update altitude trend
    if (dashboardState.lastAltitude !== undefined && dashboardState.lastUpdateTime) {
        const timeDiff = (new Date(telemetry.timestamp || Date.now()) - dashboardState.lastUpdateTime) / 1000;
        const altDiff = (telemetry.altitude || 0) - dashboardState.lastAltitude;
        const trend = altDiff / timeDiff;
        
        const trendEl = document.getElementById('altitudeTrend');
        if (trendEl) {
            const icon = trend >= 0 ? 'fa-arrow-up' : 'fa-arrow-down';
            const color = trend >= 0 ? '#28a745' : '#dc3545';
            trendEl.innerHTML = `<i class="fas ${icon}"></i> ${Math.abs(trend).toFixed(1)} m/s`;
            trendEl.style.color = color;
        }
    }
    
    dashboardState.lastAltitude = telemetry.altitude || 0;
    dashboardState.lastUpdateTime = new Date(telemetry.timestamp || Date.now());
    
    // Calculate distance from home
    if (homeDistanceEl && telemetry.latitude && telemetry.longitude && dashboardState.homeLocation) {
        const distance = calculateDistance(
            dashboardState.homeLocation.lat,
            dashboardState.homeLocation.lng,
            telemetry.latitude,
            telemetry.longitude
        );
        homeDistanceEl.textContent = distance.toFixed(1);
    }
    
    // Calculate estimated flight time (simplified)
    if (estimatedFlightTimeEl && telemetry.battery_percentage && telemetry.battery_current) {
        const estimatedMinutes = Math.round((telemetry.battery_percentage / 100) * 20); // Rough estimate
        estimatedFlightTimeEl.textContent = 
            `${Math.floor(estimatedMinutes / 60)}:${String(estimatedMinutes % 60).padStart(2, '0')}`;
    }
    
    // Update battery icon
    const batteryIcon = document.getElementById('batteryIcon');
    if (batteryIcon && telemetry.battery_percentage !== null) {
        const percent = telemetry.battery_percentage;
        if (percent > 75) {
            batteryIcon.className = 'fas fa-battery-full';
        } else if (percent > 50) {
            batteryIcon.className = 'fas fa-battery-three-quarters';
        } else if (percent > 25) {
            batteryIcon.className = 'fas fa-battery-half';
        } else if (percent > 10) {
            batteryIcon.className = 'fas fa-battery-quarter';
        } else {
            batteryIcon.className = 'fas fa-battery-empty';
        }
    }
}

// Initialize Mission Planning
function initMissionPlanning() {
    document.getElementById('addWaypointEditorBtn')?.addEventListener('click', addWaypointFromEditor);
    document.getElementById('clearWaypointsBtn')?.addEventListener('click', clearAllWaypoints);
    document.getElementById('missionPreviewBtn')?.addEventListener('click', showMissionPreview);
    document.getElementById('saveMissionBtn')?.addEventListener('click', saveMission);
    document.getElementById('loadMissionBtn')?.addEventListener('click', loadMission);
    
    updateMissionPreview();
}

// Add Waypoint from Editor
function addWaypointFromEditor() {
    if (!dashboardState.map) {
        addAlert('error', 'Map not initialized');
        return;
    }
    
    const center = dashboardState.map.getCenter();
    const waypoint = {
        lat: center.lat(),
        lng: center.lng(),
        alt: 35.0,
        id: Date.now()
    };
    
    dashboardState.waypoints.push(waypoint);
    addWaypointMarker(waypoint);
    updateWaypointList();
    updateMissionPreview();
}

// Add Waypoint Marker
function addWaypointMarker(waypoint) {
    if (!dashboardState.map) return;
    
    const marker = new google.maps.Marker({
        position: { lat: waypoint.lat, lng: waypoint.lng },
        map: dashboardState.map,
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: '#007bff',
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 2
        },
        label: {
            text: String(dashboardState.waypoints.length),
            color: '#ffffff',
            fontWeight: 'bold'
        },
        title: `Waypoint ${dashboardState.waypoints.length}`
    });
    
    dashboardState.waypointMarkers.push(marker);
}

// Update Waypoint List
function updateWaypointList() {
    const list = document.getElementById('waypointList');
    if (!list) return;
    
    list.innerHTML = '';
    
    dashboardState.waypoints.forEach((wp, index) => {
        const item = document.createElement('div');
        item.className = 'waypoint-item';
        item.innerHTML = `
            <div class="waypoint-info">
                <strong>Waypoint ${index + 1}</strong>
                <div>Lat: ${wp.lat.toFixed(6)}, Lng: ${wp.lng.toFixed(6)}</div>
                <div>Alt: ${wp.alt.toFixed(1)} m</div>
            </div>
            <div class="waypoint-item-actions">
                <button class="btn btn-sm btn-outline-primary edit-waypoint-btn" data-index="${index}">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger delete-waypoint-btn" data-index="${index}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        item.querySelector('.delete-waypoint-btn').addEventListener('click', () => {
            deleteWaypoint(index);
        });
        
        list.appendChild(item);
    });
}

// Delete Waypoint
function deleteWaypoint(index) {
    if (index >= 0 && index < dashboardState.waypoints.length) {
        dashboardState.waypoints.splice(index, 1);
        
        if (index < dashboardState.waypointMarkers.length) {
            dashboardState.waypointMarkers[index].setMap(null);
            dashboardState.waypointMarkers.splice(index, 1);
        }
        
        updateWaypointList();
        updateMissionPreview();
    }
}

// Clear All Waypoints
function clearAllWaypoints() {
    dashboardState.waypointMarkers.forEach(marker => marker.setMap(null));
    dashboardState.waypointMarkers = [];
    dashboardState.waypoints = [];
    updateWaypointList();
    updateMissionPreview();
}

// Update Mission Preview
function updateMissionPreview() {
    const count = dashboardState.waypoints.length;
    const countEl = document.getElementById('previewWaypointCount');
    if (countEl) countEl.textContent = count;
    
    let totalDistance = 0;
    for (let i = 1; i < dashboardState.waypoints.length; i++) {
        const prev = dashboardState.waypoints[i - 1];
        const curr = dashboardState.waypoints[i];
        totalDistance += calculateDistance(prev.lat, prev.lng, curr.lat, curr.lng);
    }
    
    const distanceEl = document.getElementById('previewDistance');
    if (distanceEl) distanceEl.textContent = totalDistance.toFixed(1);
    
    // Estimate time (assuming 5 m/s average speed, avoid division by zero)
    const estimatedSeconds = totalDistance > 0 && 5 > 0 ? totalDistance / 5 : 0;
    const minutes = Math.floor(estimatedSeconds / 60);
    const seconds = Math.floor(estimatedSeconds % 60);
    const timeEl = document.getElementById('previewTime');
    if (timeEl) timeEl.textContent = `${minutes}:${String(seconds).padStart(2, '0')}`;
    
    // Estimate battery (rough: 1% per 100m)
    const estimatedBattery = Math.min(100, Math.round(totalDistance / 100));
    const batteryEl = document.getElementById('previewBattery');
    if (batteryEl) batteryEl.textContent = estimatedBattery + '%';
}

// Show Mission Preview
function showMissionPreview() {
    if (dashboardState.waypoints.length === 0) {
        addAlert('warning', 'No waypoints to preview');
        return;
    }
    
    const distanceEl = document.getElementById('previewDistance');
    const distance = distanceEl ? distanceEl.textContent : '0.0';
    addAlert('info', `Mission preview: ${dashboardState.waypoints.length} waypoints, ${distance} m`);
}

// Save Mission
function saveMission() {
    if (dashboardState.waypoints.length === 0) {
        addAlert('warning', 'No waypoints to save');
        return;
    }
    
    const mission = {
        waypoints: dashboardState.waypoints,
        created_at: new Date().toISOString()
    };
    
    localStorage.setItem('saved_mission', JSON.stringify(mission));
    addAlert('success', 'Mission saved to browser storage');
}

// Load Mission
function loadMission() {
    const saved = localStorage.getItem('saved_mission');
    if (!saved) {
        addAlert('warning', 'No saved mission found');
        return;
    }
    
    try {
        const mission = JSON.parse(saved);
        clearAllWaypoints();
        dashboardState.waypoints = mission.waypoints || [];
        
        dashboardState.waypoints.forEach(wp => {
            addWaypointMarker(wp);
        });
        
        updateWaypointList();
        updateMissionPreview();
        addAlert('success', 'Mission loaded');
    } catch (e) {
        addAlert('error', 'Failed to load mission: ' + e.message);
    }
}

// Initialize Keyboard Shortcuts
function initKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Only trigger if not typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        // Ctrl/Cmd + key combinations
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 's':
                    e.preventDefault();
                    saveMission();
                    break;
                case 'l':
                    e.preventDefault();
                    loadMission();
                    break;
                case 'e':
                    e.preventDefault();
                    document.getElementById('exportLogsBtn')?.click();
                    break;
            }
        }
        
        // Function keys
        switch(e.key) {
            case 'F11':
                e.preventDefault();
                document.getElementById('fullscreenMapBtn')?.click();
                break;
        }
    });
}

// Initialize Export Features
function initExportFeatures() {
    document.getElementById('exportLogsBtn')?.addEventListener('click', exportFlightLogs);
    document.getElementById('exportKmlBtn')?.addEventListener('click', exportKML);
    document.getElementById('exportGraphsBtn')?.addEventListener('click', exportGraphs);
}

// Export Flight Logs
function exportFlightLogs() {
    if (!dashboardState.telemetryData.timestamps.length) {
        addAlert('warning', 'No telemetry data to export');
        return;
    }
    
    const csv = generateCSV();
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flight_log_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    
    addAlert('success', 'Flight logs exported');
}

// Generate CSV
function generateCSV() {
    const headers = ['Timestamp', 'Latitude', 'Longitude', 'Altitude', 'Heading', 'Speed', 'Battery %', 'Battery Voltage', 'Battery Current'];
    const rows = [headers.join(',')];
    
    for (let i = 0; i < dashboardState.telemetryData.timestamps.length; i++) {
        const row = [
            dashboardState.telemetryData.timestamps[i],
            dashboardState.telemetryData.latitude[i] || '',
            dashboardState.telemetryData.longitude[i] || '',
            dashboardState.telemetryData.altitude[i] || '',
            dashboardState.telemetryData.heading[i] || '',
            dashboardState.telemetryData.speed[i] || '',
            dashboardState.telemetryData.battery[i] || '',
            dashboardState.telemetryData.batteryVoltage[i] || '',
            dashboardState.telemetryData.batteryCurrent[i] || ''
        ];
        rows.push(row.join(','));
    }
    
    return rows.join('\n');
}

// Export KML
function exportKML() {
    if (!dashboardState.telemetryData.latitude.length) {
        addAlert('warning', 'No flight path data to export');
        return;
    }
    
    let kml = '<?xml version="1.0" encoding="UTF-8"?>\n';
    kml += '<kml xmlns="http://www.opengis.net/kml/2.2">\n';
    kml += '<Document>\n';
    kml += '<name>Flight Path</name>\n';
    kml += '<Placemark>\n';
    kml += '<name>Flight Path</name>\n';
    kml += '<LineString>\n';
    kml += '<tessellate>1</tessellate>\n';
    kml += '<coordinates>\n';
    
    for (let i = 0; i < dashboardState.telemetryData.latitude.length; i++) {
        const lon = dashboardState.telemetryData.longitude[i] || 0;
        const lat = dashboardState.telemetryData.latitude[i] || 0;
        const alt = dashboardState.telemetryData.altitude[i] || 0;
        kml += `${lon},${lat},${alt} `;
    }
    
    kml += '\n</coordinates>\n';
    kml += '</LineString>\n';
    kml += '</Placemark>\n';
    kml += '</Document>\n';
    kml += '</kml>';
    
    const blob = new Blob([kml], { type: 'application/vnd.google-earth.kml+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flight_path_${new Date().toISOString().split('T')[0]}.kml`;
    a.click();
    URL.revokeObjectURL(url);
    
    addAlert('success', 'KML file exported');
}

// Export Graphs
function exportGraphs() {
    const canvas = document.getElementById('altitudeChart');
    if (!canvas) {
        addAlert('warning', 'No charts to export');
        return;
    }
    
    // Export all charts as images
    Object.keys(dashboardState.charts).forEach(chartName => {
        const chart = dashboardState.charts[chartName];
        if (chart && chart.canvas) {
            const url = chart.canvas.toDataURL('image/png');
            const a = document.createElement('a');
            a.href = url;
            a.download = `${chartName}_chart.png`;
            a.click();
        }
    });
    
    addAlert('success', 'Charts exported');
}

// Initialize Flight Replay
function initFlightReplay() {
    const replayBtn = document.getElementById('replayFlightBtn');
    if (replayBtn) {
        replayBtn.addEventListener('click', replaySelectedFlight);
    }
    
    // Make flight items selectable
    document.querySelectorAll('.flight-item').forEach(item => {
        item.addEventListener('click', function() {
            document.querySelectorAll('.flight-item').forEach(i => i.classList.remove('selected'));
            this.classList.add('selected');
            dashboardState.selectedFlightId = this.dataset.flightId;
            const replayBtn = document.getElementById('replayFlightBtn');
            if (replayBtn) replayBtn.disabled = false;
        });
    });
}

// Replay Selected Flight
function replaySelectedFlight() {
    if (!dashboardState.selectedFlightId) {
        addAlert('warning', 'Please select a flight to replay');
        return;
    }
    
    const replayBtn = document.getElementById('replayFlightBtn');
    if (replayBtn) replayBtn.disabled = true;
    addAlert('info', 'Flight replay feature coming soon');
    // TODO: Implement flight replay
}

// Initialize Battery Warnings
function initBatteryWarnings() {
    // Battery warnings are handled in updateStatusBar
}

// Update Charts with Combined Chart
function updateCharts(telemetry) {
    if (!telemetry) return;
    
    // Only update if we have valid position data
    if (telemetry.latitude === undefined || telemetry.longitude === undefined) {
        return;
    }
    
    const timestamp = new Date().toLocaleTimeString();
    
    // Add data points
    dashboardState.telemetryData.timestamps.push(timestamp);
    dashboardState.telemetryData.altitude.push(telemetry.altitude || 0);
    dashboardState.telemetryData.latitude.push(telemetry.latitude);
    dashboardState.telemetryData.longitude.push(telemetry.longitude);
    dashboardState.telemetryData.battery.push(telemetry.battery_percentage || null);
    dashboardState.telemetryData.batteryVoltage.push(telemetry.battery_voltage || null);
    dashboardState.telemetryData.batteryCurrent.push(telemetry.battery_current || null);
    dashboardState.telemetryData.speed.push(telemetry.groundspeed || 0);
    dashboardState.telemetryData.heading.push(telemetry.heading || 0);
    
    // Limit data points
    Object.keys(dashboardState.telemetryData).forEach(key => {
        if (dashboardState.telemetryData[key].length > dashboardState.maxDataPoints) {
            dashboardState.telemetryData[key].shift();
        }
    });
    
    // Update all charts with animation for smooth updates
    Object.keys(dashboardState.charts).forEach(chartName => {
        const chart = dashboardState.charts[chartName];
        if (chart) {
            chart.data.labels = dashboardState.telemetryData.timestamps;
            
            if (chartName === 'combined') {
                // Update combined chart with multiple datasets
                chart.data.datasets[0].data = dashboardState.telemetryData.altitude;
                chart.data.datasets[1].data = dashboardState.telemetryData.speed;
                chart.data.datasets[2].data = dashboardState.telemetryData.battery;
            } else {
                const dataKey = chartName === 'batteryVoltage' ? 'batteryVoltage' :
                               chartName === 'batteryCurrent' ? 'batteryCurrent' :
                               chartName === 'speed' ? 'speed' :
                               chartName === 'heading' ? 'heading' :
                               chartName;
                chart.data.datasets[0].data = dashboardState.telemetryData[dataKey] || [];
            }
            
            // Use 'none' animation for faster updates, but ensure chart refreshes
            chart.update('none');
        }
    });
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (dashboardState.pollInterval) {
        clearInterval(dashboardState.pollInterval);
    }
});
